import json
import boto3
import uuid
from langgraph.graph import StateGraph
from typing import TypedDict, Annotated, Dict, List
from langgraph.graph.message import add_messages

from agents import credit_check, feedback_planner, financial_strategy
from validation import json_validation

# Initialize DynamoDB
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("credit_ai_sessions")  # Replace with your table name

# Helper function to load state from DynamoDB
def load_state(session_id):
    """ Retrieve session state from DynamoDB """
    response = table.get_item(Key={"session_id": session_id})
    return json.loads(response["Item"]["state"]) if "Item" in response else None

# Helper function to save state to DynamoDB
def save_state(session_id, state):
    """ Store LangGraph session state in DynamoDB """
    table.put_item(
        Item={
            "session_id": session_id,
            "state": json.dumps(state)
        }
    )

# Credit AI State Schema
class CreditAIState(TypedDict):
    session_id: str
    credit_score: int
    financial_data: Dict
    personal_data: Dict
    past_scenarios: List[Dict]  # Stores past iterations
    messages: Annotated[List, add_messages]  # Needed for LangGraph’s LLM


def lambda_handler(event, context):
    # Parse the request body
    body = event.get("body", "{}")

    if isinstance(body, dict):  # Already a dictionary
        parsed_body = body
    elif isinstance(body, str):  # It's a string, parse it
        try:
            parsed_body = json.loads(body)
        except json.JSONDecodeError:
            return {
                "statusCode": 400,
                "headers": {
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Access-Control-Allow-Methods": "POST"
                },
                "body": json.dumps({"message": "Invalid JSON"})
            }
    
    # Extract parameters
    session_id = parsed_body.get("session_id") or str(uuid.uuid4())
    incoming_credit_score = parsed_body.get("credit_score")
    incoming_financial_data = parsed_body.get("financial_data")
    incoming_personal_data = parsed_body.get("personal_data")
    
    json_validation.validate_financial_data(incoming_financial_data)

    # Load existing state if session exists
    state = load_state(session_id)
    
    if not state:
        # First Time Run
        state = {
            "session_id": session_id,
            "credit_score": incoming_credit_score or 650,
            "financial_data": incoming_financial_data or {},
            "personal_data": incoming_personal_data or {},
            "past_scenarios": []
        }
    else:
        # Append current scenario to history before modifying
        state["past_scenarios"].append({
            "credit_score": state["credit_score"],
            "financial_data": state["financial_data"],
            "personal_data": state["personal_data"]
        })

        # Update only if new data is provided
        if incoming_credit_score:
            state["credit_score"] = incoming_credit_score
        if incoming_financial_data:
            state["financial_data"].update(incoming_financial_data)
        if incoming_personal_data:
            state["personal_data"].update(incoming_personal_data)

    # Define LangGraph Workflow
    workflow = StateGraph(CreditAIState)
    workflow.add_node("credit_simulation", credit_check.credit_check_agent)
    workflow.add_node("financial_strategy", financial_strategy.financial_strategy_agent)
    workflow.add_node("feedback", feedback_planner.feedback_agent)

    # Define Execution Order
    workflow.set_entry_point("credit_simulation")
    workflow.add_edge("credit_simulation", "financial_strategy")
    workflow.add_edge("financial_strategy", "feedback")  # Feedback comes last
    workflow.set_finish_point("financial_strategy")
    graph = workflow.compile()

    # Execute LangGraph
    updated_state = graph.invoke(state)

    # Return state and session info
    return {
        "session_id": session_id,
        "updated_state": updated_state
    }
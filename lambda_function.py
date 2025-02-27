import json
import boto3
import uuid
from langgraph.graph import StateGraph
from typing import Dict
from agents import credit_check, feedback_planner, financial_strategy

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
class CreditAIState:
    session_id: str
    credit_score: int
    financial_data: Dict
    personal_data: Dict
    past_scenarios: list  # Stores past iterations

def lambda_handler(event, context):
    # Parse the request body (assuming it's JSON)
    try:
        body = json.loads(event.get("body", "{}"))  # Parse request body
        session_id = body.get("session_id") or str(uuid.uuid4())
        incoming_credit_score = body.get("credit_score")
        incoming_financial_data = body.get("financial_data")
        incoming_personal_data = body.get("personal_data")
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": {
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST"
            },
            "body": json.dumps({"message": "Invalid JSON"})
        }
    
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

    # Execute LangGraph
    updated_state = workflow.invoke(state)

    # Return state and session info
    return {
        "session_id": session_id,
        "updated_state": updated_state
    }
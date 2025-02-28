import json
import boto3
import uuid
import os
from typing import TypedDict, Annotated, Dict, List

from langchain.tools import Tool
from langchain_openai import ChatOpenAI

from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from agents import financial_strategy
from tools import credit_check
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
    credit_check_tool = Tool(
        name="CreditCheck",
        func=credit_check.credit_check_tool,
        description="Calculates a credit score based on financial data."
    )
    tools = [credit_check_tool]
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0,
        max_tokens=None,
        timeout=None,
        max_retries=2,
        api_key=os.getenv("OPEN_AI_KEY")
    )
    llm_with_tools = llm.bind_tools(tools)

    def financial_planner(state: CreditAIState):
        return {"messages": [llm_with_tools.invoke(state["messages"])]}
    
    workflow.add_node("financial_planner", financial_planner)
    tool_node = ToolNode(tools=[credit_check_tool])
    workflow.add_node("tools", tool_node)

    workflow.add_conditional_edges(
        "financial_planner",
        tools_condition,
    )
    
    # Any time a tool is called, we return to the chatbot to decide the next step
    workflow.add_edge("tools", "financial_planner")

    # Define Execution Order
    workflow.set_entry_point("financial_planner")
    workflow.set_finish_point("financial_planner")
    graph = workflow.compile()

    print(state)
    # Add the prompt input message to the message history
    state["messages"]= {
        "role": "user", 
        "content": "What can I do to improve my credit score based on my current situation?"
    }

    # Execute LangGraph
    updated_state = graph.invoke(state)

    # Return state and session info
    return {
        "session_id": session_id,
        "updated_state": updated_state
    }
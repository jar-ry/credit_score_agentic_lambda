import json
import boto3
import uuid
import os
from typing import TypedDict, Annotated, Dict, List

from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage

from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

# from agents import financial_strategy
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
    incoming_financial_data = parsed_body.get("financial_data")
    incoming_personal_data = parsed_body.get("personal_data")
    
    json_validation.validate_financial_data(incoming_financial_data)

    # Load existing state if session exists
    state = load_state(session_id)
    
    if not state:
        # First Time Run
        state = {
            "session_id": session_id,
            "financial_data": incoming_financial_data or {},
            "personal_data": incoming_personal_data or {},
            "past_scenarios": []
        }
    else:
        # Append current scenario to history before modifying
        state["past_scenarios"].append({
            "financial_data": state["financial_data"],
            "personal_data": state["personal_data"]
        })

        # Update only if new data is provided
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
        # Invoke the credit_check tool inside the planner logic
        credit_score_estimate = credit_check_tool.func(state["financial_data"])  # Call the credit check tool
        
        # Update the state with the new credit score
        state["credit_score_estimate"] = credit_score_estimate

        # Include other details (financial_data and personal_data)
        financial_data = state.get("financial_data", {})
        personal_data = state.get("personal_data", {})

        # TODO add some reasoning or strategy using strategy agent
        
        # Prepare the prompt for the LLM, including reasoning and strategy
        llm_input = f"Based on the following details:\n\n\
            Financial Data: {financial_data}\n\
            Personal Data: {personal_data}\n\n\
            What can I do to improve my credit score based on my current situation?"

        # Prepare the output
        messages = [llm_with_tools.invoke(llm_input)]
        
        updated_state = {
            "credit_score_estimate": credit_score_estimate,
            "financial_data": financial_data,
            "personal_data": personal_data,
            "messages": messages
        }

        return updated_state
    
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

    # Execute LangGraph
    updated_state = graph.invoke(state)

    print(updated_state)
    messages = [
        message.content if isinstance(message, HumanMessage) else str(message) for message in updated_state.get("messages", [])
    ]

    # Return state and session info
    return {
        "session_id": session_id,
        "updated_state": {
            **updated_state,
            "messages": messages 
        }
    }
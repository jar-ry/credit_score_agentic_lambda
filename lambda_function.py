import json
import boto3
import uuid
import os
from typing import TypedDict, Annotated, Dict, List

from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage as HumanMessageSchema
from langchain_core.messages import HumanMessage, ToolMessage

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
    credit_score_estimate: int
    financial_data: Dict
    personal_data: Dict
    past_scenarios: List[Dict]  # Stores past iterations
    messages: Annotated[List, add_messages]  # Needed for LangGraph’s LLM

def lambda_handler(event, context):
    print('event')
    print(event)
    # Parse the request body
    body = event.get("body", "{}")
    print('body')
    print(body)
    print(type(body))
    if isinstance(body, dict):  # Already a dictionary
        parsed_body = body
    elif isinstance(body, str):  # It's a string, parse it
        try:
            parsed_body = json.loads(body)
            if "body" in parsed_body:
                parsed_body = parsed_body.get('body', {})
            
        except json.JSONDecodeError:
            return {
                "statusCode": 400,
                "headers": {
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Access-Control-Allow-Methods": "POST"
                },
                "body": json.dumps({"message": "Invalid JSON"})
            }
    print('parsed_body')
    print(parsed_body)
    print(type(parsed_body))
    # Extract parameters
    session_id = parsed_body.get("session_id") or str(uuid.uuid4())
    incoming_financial_data = parsed_body.get("financial_data")
    incoming_personal_data = parsed_body.get("personal_data")
    print(incoming_financial_data)
    print(type(incoming_financial_data))
    json_validation.validate_financial_data(incoming_financial_data)

    # Load existing state if session exists
    state = load_state(session_id)
    
    if not state:
        # First Time Run
        state = {
            "session_id": session_id,
            "financial_data": incoming_financial_data or {},
            "personal_data": incoming_personal_data or {},
            "past_scenarios": [],
            "messages": []
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
        # # Include other details (financial_data and personal_data)
        financial_data = state.get("financial_data", {})
        personal_data = state.get("personal_data", {})

        # TODO add some reasoning or strategy using strategy agent
        
        # Prepare the prompt for the LLM, including reasoning and strategy
        llm_input = f"Based on the following details:\n\n\
            Financial Data: {financial_data}\n\
            Personal Data: {personal_data}\n\n\
            What can I do to improve my credit score?"

        messages = [HumanMessage(content=llm_input)]

        # Prepare the output
        ai_msg = llm_with_tools.invoke(messages)
        print("ai_msg")
        print(ai_msg)
        messages.append(ai_msg)
        tool_calls = ai_msg.tool_calls

        for tool in tool_calls:
            if tool['name'] == 'CreditCheck' and tool['type'] == 'tool_call':
                credit_score_estimate = credit_check_tool.func(financial_data)
                state["credit_score_estimate"] = credit_score_estimate
                print("credit_score_estimate")
                print(credit_score_estimate)
                state["credit_score"] = credit_score_estimate

                messages.append(ToolMessage(
                    name="CreditCheck", 
                    content=f"Credit score details: {credit_score_estimate}",
                    tool_call_id=str(tool['id'])
                ))

        # Get the LLM's response
        ai_response = llm_with_tools.invoke(messages)
        
        print("ai_response")
        print(ai_response)
        messages.append(ai_response.content)

        print("messages")
        print(messages)
        state["messages"] = messages
        return state
    
    workflow.add_node("financial_planner", financial_planner)
    workflow.add_node("tools", ToolNode(tools=[credit_check_tool]))

    workflow.add_conditional_edges(
        "financial_planner",
        tools_condition,
    )
    
    # # Any time a tool is called, we return to the chatbot to decide the next step
    # workflow.add_edge("tools", "financial_planner")

    # Define Execution Order
    workflow.set_entry_point("financial_planner")
    workflow.set_finish_point("financial_planner")
    graph = workflow.compile()

    # Execute LangGraph
    updated_state = graph.invoke(state) or {"messages": []}

    print(updated_state)
    messages = [
        message.content if isinstance(message, HumanMessageSchema) else str(message) for message in updated_state.get("messages", [])
    ]

    # Return state and session info
    return {
        "session_id": session_id,
        "updated_state": {
            **updated_state,
            "messages": messages 
        }
    }
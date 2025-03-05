import json
import boto3
import uuid
import os
from typing import TypedDict, Annotated, Dict, List

from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage as HumanMessageSchema
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage

from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

# from agents import financial_strategy
from tools import credit_check
from validation import json_validation

# Initialize DynamoDB
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("credit_ai_sessions")  # Replace with your table name

# Helper function to deserialize state
def deserialize_state(state):
    """ Convert JSON back into LangGraph-compatible objects """
    if isinstance(state, list):  
        return [deserialize_state(item) for item in state]  # Recursively handle lists
    elif isinstance(state, dict):  
        if "type" in state and "content" in state:  
            # Convert JSON back to Langchain message objects
            if state["type"] == "human":
                return HumanMessage(content=state["content"], additional_kwargs=state.get("additional_kwargs", {}))
            elif state["type"] == "ai":
                return AIMessage(content=state["content"], additional_kwargs=state.get("additional_kwargs", {}))
            elif state["type"] == "tool":
                return ToolMessage(content=state["content"], tool_call_id=state['tool_call_id'], additional_kwargs=state.get("additional_kwargs", {}))
        return {k: deserialize_state(v) for k, v in state.items()}  # Recursively handle dicts
    return state  # Return unchanged for primitive types

# Helper function to load state from DynamoDB
def load_state(session_id):
    """ Retrieve session state from DynamoDB """
    response = table.get_item(Key={"session_id": session_id})
    
    if "Item" in response:
        serialized_state = json.loads(response["Item"]["state"])
        return deserialize_state(serialized_state)  # Convert JSON back to Langchain objects
    return None

def serialize_state(state):
    """ Convert LangGraph state to a JSON-serializable format """
    if isinstance(state, list):  
        return [serialize_state(item) for item in state]  # Recursively handle lists
    elif isinstance(state, dict):  
        return {k: serialize_state(v) for k, v in state.items()}  # Recursively handle dicts
    elif isinstance(state, (HumanMessage, AIMessage, ToolMessage)):  
        return state.model_dump()  # Convert message objects to dictionary
    return state  # Return unchanged for JSON-safe types

# Helper function to save state to DynamoDB
def save_state(session_id, state):
    """ Store LangGraph session state in DynamoDB """
    serialized_state = serialize_state(state)  # Convert before saving
    table.put_item(
        Item={
            "session_id": session_id,
            "state": json.dumps(serialized_state)
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
    try:
        # Parse the request body
        body = event.get("body", "{}")
        print('body')
        print(body)
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
        # Extract parameters
        session_id = parsed_body.get("session_id", None)
        if not session_id:
            session_id = str(uuid.uuid4())
        incoming_financial_data = parsed_body.get("financial_data")
        incoming_personal_data = parsed_body.get("personal_data")
        incoming_message = parsed_body.get("message")

        if not session_id:
            json_validation.validate_financial_data(incoming_financial_data)
        else:
            # Load existing state if session exists
            state = load_state(session_id)
            print("DB state")
            print(state)
        
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
            state["incoming_message"] = incoming_message

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
            incoming_message = state.get("incoming_message", None)
            print("State in financial planner")
            print(state)
            # TODO add some reasoning or strategy using strategy agent
            
            if incoming_message:
                llm_input = incoming_message
            else:
                # Prepare the prompt for the LLM, including reasoning and strategy
                llm_input = f"Based on the following details:\n\n\
                    Financial Data: {financial_data}\n\
                    Personal Data: {personal_data}\n\n\
                    Please only give me 3 recommendations on how to improve my credit score and give me my current credit score"

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
        print("First execution state")
        print(state)
        # Execute LangGraph
        updated_state = graph.invoke(state)

        messages = [
            message.content if isinstance(message, HumanMessage) else str(message) for message in updated_state.get("messages", [])
        ]
        print("SAVING")
        print(updated_state)
        print(messages)
        save_state(session_id, updated_state)
        # Return state and session info
        return {
            "session_id": session_id,
            "updated_state": {
                **updated_state,
                "messages": messages 
            }
        }
    except Exception as e:
        print("ERRROR")
        print(e)
        return {
            "statusCode": 500,
            "headers": {
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST"
            },
            "body": json.dumps({"message": e})
        }
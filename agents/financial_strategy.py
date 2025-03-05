from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage
import os
from typing import TypedDict, Annotated, Dict, List
from langgraph.graph.message import add_messages
import json

# Credit AI State Schema
class CreditAIState(TypedDict):
    session_id: str
    credit_score_estimate: int
    financial_data: Dict
    personal_data: Dict
    past_scenarios: List[Dict]  # Stores past iterations
    messages: Annotated[List, add_messages]  # Needed for LangGraph’s LLM
    incoming_message: str
    
def financial_strategy_agent(state: CreditAIState):
    """
    Processes user intent and modifies financial data accordingly.
    """
    print("At financial_strategy_agent")
    incoming_message = state.get("incoming_message", "")
    financial_data = state.get("financial_data", {})

    # Use an LLM to interpret the message
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0,
        max_tokens=None,
        api_key=os.getenv("OPEN_AI_KEY")
    )
    
    instruction_prompt = f"""
    User said: {incoming_message}
    
    Extract the user's intent and update their financial data accordingly.
    Example outputs:
    - If the user asks "What if I reduced my debt by $2000?", return updated financial data with reduced debt.
    - If the user asks "What if I increased my income?", update the income field.
    
    Current Financial Data:
    {financial_data}
    
    Respond ONLY with a JSON object of the updated financial data.
    """

    response = llm.invoke([HumanMessage(content=instruction_prompt)])
    print("financial_strategy_agent response")
    print(response)
    try:
        updated_financial_data = json.loads(response.content)
        state["financial_data"] = updated_financial_data
    except json.JSONDecodeError:
        print("Error parsing financial data update")
    
    return state

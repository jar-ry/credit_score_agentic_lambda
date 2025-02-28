from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage
import os

llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    api_key=os.getenv("OPEN_AI_KEY")
)

def financial_strategy_agent(credit_score, financial_data):
    prompt = f"""
    The user's credit score is {credit_score}.
    Their financial details are: {financial_data}.
    
    Provide 2-3 actionable financial strategies to improve their credit score and overall financial health.
    """

    messages = [
        (
            "system",
            "You are a highly knowledgeable financial advisor. A client has provided their credit score and financial details.",
        ),
        ("human",  prompt),
    ]
    response = llm.invoke(messages)
    print(response)
    return response.content
# Tool Agent 2: Provides Financial Strategy Advice
def financial_strategy_agent(state):
    print(state)
    advice = "Paying an extra $1,000 could boost your score faster."
    print(f"Financial Advice: {advice}")
    return {"financial_advice": advice}
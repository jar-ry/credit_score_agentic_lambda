# Tool Agent 1: Simulates Credit Score Check
def credit_check_agent(state):
    print(state)
    financial_data = state.get("financial_data", {})

    income = financial_data.get("income", 0)
    expenses = financial_data.get("expenses", 0)
    
    if income < expenses:
        credit_score = 0
    else:
        credit_score = 100
    print(f"New Credit Score: {credit_score}")
    return {"credit_score": credit_score}
import ast

# Tool Agent 1: Simulates Credit Score Check
# def credit_check_tool(income: float, expenses: float, debts: dict, credit_limit: float, missed_payments: int, late_payments:int):
def credit_check_tool(financial_data):
    """Calculates a credit score based on financial data."""
    print("Tool called")
    # Extract financial data
    financial_data = ast.literal_eval(financial_data)
    
    income = financial_data.get("income", 0)
    expenses = financial_data.get("expenses", 0)
    debts = financial_data.get("debts", {})
    credit_limit = financial_data.get("credit_limit", 0)
    missed_payments = financial_data.get("missed_payments", 0)
    late_payments = financial_data.get("late_payments", 0)
    
    BASE_SCORE = 0
    MAX_SCORE = 1000

    # Calculate Net Income
    net_income = max(0, income - expenses)  # Not negative
    
    # Debt-to-Income (DTI) Ratio (Lower is better)
    total_debt = sum(debts.values())
    dti_ratio = (total_debt / net_income) if net_income > 0 else 1
    dti_score = max(0, 250 - (dti_ratio * 250 ))  # High DTI lowers score

    # Loan-to-Income (LTI) Ratio (Lower is better)
    lti_ratio = (total_debt / income) if income > 0 else 1
    lti_score = max(0, 250 - (lti_ratio * 250))  # High LTI lowers score

    # Credit Utilization (Lower is better)
    credit_utilization = (sum(debts.values()) / credit_limit) if credit_limit > 0 else 1
    utilization_score = max(0, 250 - (credit_utilization * 250))

    # Payment History
    missed_penalty = missed_payments * 100
    late_penalty = late_payments * 50

    # Discretionary Income Score (High is better)
    discretionary_income_score = min(250, (net_income / income) * 250) if income > 0 else 0 

    # Calculate Final Credit Score
    credit_score = BASE_SCORE + dti_score + lti_score + utilization_score + discretionary_income_score - (missed_penalty + late_penalty)

    # Ensure score is within range [0, 1000]
    credit_score = max(BASE_SCORE, min(MAX_SCORE, credit_score))

    response = {
        "credit_score": int(credit_score),
        "debt_to_income_ratio": round(dti_ratio, 2),
        "loan_to_income_ratio": round(lti_ratio, 2),
        "credit_utilization": round(credit_utilization * 100, 2),
        "discretionary_income_score": round(discretionary_income_score, 2),
        "missed_payments": missed_payments,
        "late_payments": late_payments
    }
    print("Tool responding")
    print(response)
    return response
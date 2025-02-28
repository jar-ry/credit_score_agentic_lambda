import json

def validate_financial_data(financial_data):
    required_keys = {
        "income": (int, float),
        "expenses": (int, float),
        "debts": dict,
        "credit_limit": (int, float),
        "missed_payments": int,
        "late_payments": int
    }

    if not isinstance(financial_data, dict):
        raise json.JSONDecodeError("Invalid format: financial_data must be a dictionary", doc=str(financial_data), pos=0)

    for key, expected_type in required_keys.items():
        if key not in financial_data:
            raise json.JSONDecodeError(f"Missing key: {key}", doc=str(financial_data), pos=0)
        if not isinstance(financial_data[key], expected_type):
            raise json.JSONDecodeError(
                f"Incorrect type for {key}: expected {expected_type}, got {type(financial_data[key])}",
                doc=str(financial_data), pos=0
            )

    if not all(isinstance(v, (int, float)) for v in financial_data["debts"].values()):
        raise json.JSONDecodeError("All debt values must be numbers", doc=str(financial_data), pos=0)

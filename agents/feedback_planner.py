# Feedback & Refinement Agent (Reasoning Layer)
def feedback_agent(state):
    print(state)
    last_scenario = state["past_scenarios"][-1] if state["past_scenarios"] else {}
    
    # Compare new vs. old inputs
    changes = {}
    for key in ["credit_score", "financial_data", "personal_data"]:
        if key in state and key in last_scenario:
            if state[key] != last_scenario[key]:
                changes[key] = {"before": last_scenario[key], "after": state[key]}

    # Generate response based on changes
    if changes:
        feedback = f"I noticed you adjusted {', '.join(changes.keys())}. Here’s what happens next..."
    else:
        feedback = "No major changes detected. You can tweak more settings for better results."

    print(f"Feedback: {feedback}")

    return {"feedback": feedback}
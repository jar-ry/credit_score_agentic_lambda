import json
import boto3
import uuid

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
    
def lambda_handler(event, context):
    # Use existing session or create new
    session_id = event.get("session_id") or str(uuid.uuid4())

    # Load existing state if session exists
    state = load_state(session_id)
    
    if not state:
        state = {"message":"hi from db"}
        # Save updated state to DynamoDB
        save_state(session_id, state)
        state = {"message":"hi from lambda"}

    # Return state and session info
    return {
        "session_id": session_id,
        "updated_state": state
    }

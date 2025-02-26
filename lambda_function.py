import json

def lambda_handler(event, context):
    return {
        "body": json.dumps({"message": "hi"})
    }

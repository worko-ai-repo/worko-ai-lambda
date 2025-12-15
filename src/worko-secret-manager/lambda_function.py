import json
import boto3
import os
from botocore.exceptions import ClientError

def get_sum(a,b,c):
    return a + b + c


def lambda_handler(event, context):
    """
    Worko Secret Manager Lambda Handler
    
    Operations:
    1. CREATE: Create/update secret in AWS Secrets Manager
    2. GET: Retrieve secret from AWS Secrets Manager
    
    Deployed via CodeCatalyst CI/CD
    """
    
    try:
        operation = event.get('operation', '').upper()
        secret_name = event.get('secret_name')
        
        if not secret_name:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "secret_name is required"})
            }
        
        secrets_client = boto3.client('secretsmanager', region_name='ap-south-1')
        
        if operation == 'CREATE':
            secret_value = event.get('secret_value')
            if not secret_value:
                return {
                    "statusCode": 400,
                    "body": json.dumps({"error": "secret_value is required for CREATE operation"})
                }
            
            try:
                # Try to update existing secret
                response = secrets_client.update_secret(
                    SecretId=secret_name,
                    SecretString=json.dumps(secret_value) if isinstance(secret_value, dict) else str(secret_value)
                )
                message = f"Secret '{secret_name}' updated successfully"
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    # Create new secret
                    response = secrets_client.create_secret(
                        Name=secret_name,
                        SecretString=json.dumps(secret_value) if isinstance(secret_value, dict) else str(secret_value)
                    )
                    message = f"Secret '{secret_name}' created successfully"
                else:
                    raise e
            
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": message,
                    "secret_arn": response['ARN']
                })
            }
        
        elif operation == 'GET':
            try:
                response = secrets_client.get_secret_value(SecretId=secret_name)
                secret_value = response['SecretString']
                
                # Try to parse as JSON, fallback to string
                try:
                    secret_data = json.loads(secret_value)
                except json.JSONDecodeError:
                    secret_data = secret_value
                
                return {
                    "statusCode": 200,
                    "body": json.dumps({
                        "secret_name": secret_name,
                        "secret_value": secret_data
                    })
                }
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    return {
                        "statusCode": 404,
                        "body": json.dumps({"error": f"Secret '{secret_name}' not found"})
                    }
                else:
                    raise e
        
        else:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Invalid operation. Use 'CREATE' or 'GET'"})
            }
    
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
import boto3
import json
import time
from botocore.exceptions import ClientError
from google.oauth2 import service_account
import google.auth.transport.requests
from google import genai
from google.genai import types
import requests

def get_secret(secret_name):
    secrets_client = boto3.client('secretsmanager', region_name='ap-south-1')

    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret_value = response['SecretString']
        
        # Try to parse as JSON, fallback to string
        try:
            secret_data = json.loads(secret_value)
        except json.JSONDecodeError:
            secret_data = secret_value
        return secret_data
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return {
                "statusCode": 404,
                "body": json.dumps({"error": f"Secret '{secret_name}' not found"})
            }
        
def call_GCP_models(prompt, service_account_info,want_json=True, max_try_for_json=1, thinking_mode=False, thinking_budget=None):
    # 1. Service account JSON path
    # SERVICE_ACCOUNT_FILE = r"C:\Users\Administrator\Desktop\worko_working\worko_code_chainged_files\vertex-sa.json"

    # 2. Load and refresh credentials
    credentials = service_account.Credentials.from_service_account_info(
    service_account_info,
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    # credentials = service_account.Credentials.from_service_account_file(
    #     SERVICE_ACCOUNT_FILE,
    #     scopes=["https://www.googleapis.com/auth/cloud-platform"]
    # )
    credentials.refresh(google.auth.transport.requests.Request())

    # 3. Prepare API endpoint
    project_id = "worko-dev"
    location = "us-central1"
    model_name = "gemini-1.5-pro-002"

    url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/publishers/google/models/{model_name}:generateContent"

    # 4. Prepare headers and payload
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json"
    }

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 5000,
            "temperature": 0.7,
            "responseMimeType": "application/json" if want_json else "text/plain",
            "thinkingConfig": {
                "mode": "THINKING_MODE_ENABLED",
                "thinkingBudget": thinking_budget
            } if thinking_mode and thinking_budget else {"mode": "THINKING_MODE_ENABLED"} if thinking_mode else {}
        }
    }

    # 5. Make API call
    try:
        if not want_json:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()  # Raise exception for bad status codes
            result = response.json()
            
            inpute = result["usageMetadata"]["promptTokenCount"]
            output = result["usageMetadata"]["candidatesTokenCount"] + result["usageMetadata"]["thoughtsTokenCount"]
            print("inpute tokens:- ",inpute,"Output tokens",output)
            response = result['candidates'][0]['content']['parts'][0]['text']
            print(response)
            return response

        for attempt in range(max_try_for_json):
            try:
                response = requests.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                text_response = result['candidates'][0]['content']['parts'][0]['text']
                text_response = text_response.strip().removeprefix("```json").removesuffix("```").strip()
                json_result = json.loads(text_response)
                print(json_result)
                return json_result
            except Exception as e:
                remaining = max_try_for_json - attempt - 1
                print(f"JSON parse failed. Retries left: {remaining}")
                print("Error:", e)
                time.sleep(5)
                if remaining == 0:
                    raise
    except requests.exceptions.RequestException as e:
        print(f"Error occured : {e}")
        return f"Error occured : {e}"
        # print(f"Response: {response.usageMetadata}")

        
# env = "dev"
# GCP_secret_name = "GCP-aiplatform-secrect-"+env
# service_account_info = get_secret(GCP_secret_name)
# # print(service_account_info)
# prompt  = "write a prince story of taj mahal"
# response = call_GCP_models(prompt,service_account_info,want_json=False)
# print(response)
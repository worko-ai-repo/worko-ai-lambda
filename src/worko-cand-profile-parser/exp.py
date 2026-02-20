import json
import boto3
import os
from google.cloud import firestore
from google.oauth2 import service_account
from botocore.exceptions import ClientError

event = {'Records': [{'eventVersion': '2.1', 'eventSource': 'aws:s3', 'awsRegion': 'ap-south-1', 'eventTime': '2026-02-20T01:24:11.222Z', 'eventName': 'ObjectCreated:Put', 'userIdentity': {'principalId': 'AWS:AROATCKANHWV2MBXXE3V6:worko-corp-dev-workoCorp'}, 'requestParameters': {'sourceIPAddress': '103.176.210.4'}, 'responseElements': {'x-amz-request-id': '1WYCTB49F0SMNXB7', 'x-amz-id-2': 'u35TkJBAXmfj8KW8tq3impvi9Znl3MtbS99GPbnVoqRxzlZGh02cNfakBp+3v08nHZBHJtuVhWh+U8XJzLEqv/4GLHtRPjMg'}, 's3': {'s3SchemaVersion': '1.0', 'configurationId': '2391fd04-1e04-41f3-9a68-3c5d8a728a02', 'bucket': {'name': 'worko-corporate-cand-profile-dev', 'ownerIdentity': {'principalId': 'A1V0APDMR493SG'}, 'arn': 'arn:aws:s3:::worko-corporate-cand-profile-dev'}, 'object': {'key': 'companies/01JWAQF1G96E0SE9XHXSFGHNWW/bulk-cvs/01KHWABBKWAPE5FD8RD34Z53JG.pdf', 'size': 704958, 'eTag': '765e8d53efdbd7d49f21aed78b22ded0', 'sequencer': '006997B7BB2D483FD3'}}}]}

def get_secret(secret_name):
    secrets_client = boto3.client('secretsmanager', region_name='ap-south-1')
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        return json.loads(response['SecretString'])
    except ClientError as e:
        print(f"Error getting secret: {e}")
        return None

def initialize_firestore(secret_name, db_name):
    creds_dict = get_secret(secret_name)
    credentials = service_account.Credentials.from_service_account_info(creds_dict)
    return firestore.Client(project=creds_dict.get("project_id"), credentials=credentials, database=db_name)

def get_metadata(event):
    s3_client = boto3.client('s3')
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    response = s3_client.head_object(Bucket=bucket, Key=key)
    return response.get('Metadata', {})

def get_counts(db, bulkSourceTypeResumeId):
    doc_ref = db.collection("bulkSourceTypeResumes").document(bulkSourceTypeResumeId)
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        totalResumesUploaded = data.get("totalResumesUploaded", 0)
        totalResumesSucceeded = data.get("totalResumesSucceeded", 0)
        totalResumesFailed = data.get("totalResumesFailed", 0)
        totalResumesDuplicate = data.get("totalResumesDuplicate", 0)
        
        print(f"totalResumesUploaded {totalResumesUploaded}")
        print(f"totalResumesSucceeded {totalResumesSucceeded}")
        print(f"totalResumesFailed {totalResumesFailed}")
        print(f"totalResumesDuplicate {totalResumesDuplicate}")
        return data
    else:
        print(f"Document not found for bulkSourceTypeResumeId: {bulkSourceTypeResumeId}")
        return None

if __name__ == "__main__":
    env = "dev"
    GCP_DATABASE_NAME = f"worko-corp-db-{env}"
    GCP_secret_name = f"GCP-firestore-secret-{env}"
    
    db = initialize_firestore(GCP_secret_name, GCP_DATABASE_NAME)
    metadata = get_metadata(totalResumesUploadedevent)
    bulksourcetyperesumeid = metadata.get("bulksourcetyperesumeid", "")
    
    if bulksourcetyperesumeid:
        get_counts(db, bulksourcetyperesumeid)
    else:
        print("No bulksourcetyperesumeid found in metadata")

# def call_GCP_models(prompt, service_account_info, want_json=True,max_try_for_json=3, thinking_mode=False, thinking_budget=None):


#     # 2. Load and refresh credentials
#     credentials = service_account.Credentials.from_service_account_info(
#     service_account_info,
#     scopes=["https://www.googleapis.com/auth/cloud-platform"]
#     )

#     credentials.refresh(google.auth.transport.requests.Request())

#     # 3. Prepare API endpoint
#     project_id = "worko-dev"
#     location = "us-central1"
#     model_name = "gemini-1.5-pro"

#     url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/publishers/google/models/{model_name}:generateContent"

#     # 4. Prepare headers and payload
#     headers = {
#         "Authorization": f"Bearer {credentials.token}",
#         "Content-Type": "application/json"
#     }

#     payload = {
#         "contents": [
#             {
#                 "role": "user",
#                 "parts": [
#                     {"text": prompt}
#                 ]
#             }
#         ],
#         "generationConfig": {
#             "maxOutputTokens": 5000,
#             "temperature": 0.7,
#             "responseMimeType": "application/json" if want_json else "text/plain",
#             "thinkingConfig": {
#                 "mode": "THINKING_MODE_ENABLED",
#                 "thinkingBudget": thinking_budget
#             } if thinking_mode and thinking_budget else {"mode": "THINKING_MODE_ENABLED"} if thinking_mode else {}
#         }
#     }

#     # 5. Make API call
#     try:
#         if not want_json:
#             response = requests.post(url, headers=headers, json=payload)
#             response.raise_for_status()  # Raise exception for bad status codes
#             result = response.json()
            
#             inpute = result["usageMetadata"]["promptTokenCount"]
#             output = result["usageMetadata"]["candidatesTokenCount"] + result["usageMetadata"]["thoughtsTokenCount"]
#             print("inpute tokens:- ",inpute,"Output tokens",output)
#             response = result['candidates'][0]['content']['parts'][0]['text']
#             print(response)
#             return response

#         for attempt in range(max_try_for_json):
#             try:
#                 response = requests.post(url, headers=headers, json=payload)
#                 response.raise_for_status()
#                 result = response.json()
#                 text_response = result['candidates'][0]['content']['parts'][0]['text']
#                 text_response = text_response.strip().removeprefix("```json").removesuffix("```").strip()
#                 json_result = json.loads(text_response)
#                 print(json_result)
#                 return json_result
#             except Exception as e:
#                 remaining = max_try_for_json - attempt - 1
#                 print(f"JSON parse failed. Retries left: {remaining}")
#                 print("Error:", e)
#                 time.sleep(5)
#                 if remaining == 0:
#                     raise
#     except requests.exceptions.RequestException as e:
#         print(f"Error occured : {e}")
#         return f"Error occured : {e}"

# def clean_and_load(raw: str) -> dict:
#     """
#     Cleans a raw JSON string that may contain ```json ... ``` wrappers
#     and loads it into a Python dictionary.
#     """
#     # 1. Remove ```json or ``` wrappers using regex
#     cleaned = re.sub(r"```json|```", "", raw).strip()

#     # 2. Ensure it's valid JSON and load
#     try:
#         data = json.loads(cleaned)
#         return data
#     except json.JSONDecodeError as e:
#         print("JSON loading error:", e)
#         print("Cleaned JSON:", cleaned)
#         return None

# def call_sonnet4(prompt,creds, max_json_try=3, want_json=True, system_prompt=None):  # ← Add system_prompt parameter


#     PROJECT_ID = "worko-dev"
#     LOCATION="global"
#     # SERVICE_ACCOUNT_FILE = r"C:\Users\Administrator\Desktop\worko_working\worko_code_chainged_files\vertex-sa.json"

#     # Load credentials
#     credentials = service_account.Credentials.from_service_account_info(
#         creds,
#         scopes=["https://www.googleapis.com/auth/cloud-platform"]
#     )

#     # Initialize Anthropic client with Vertex AI
#     client = anthropic.AnthropicVertex(
#         project_id=PROJECT_ID,
#         region=LOCATION,
#         credentials=credentials
#     )
#     # model="claude-sonnet-4-5@20250929"
#     model="claude-sonnet-4@20250514"
    
#     # Build request
#     request_params = {
#         "model": model,
#         "max_tokens": 5000,
#         "temperature": 0.3,
#         "messages": [{"role": "user", "content": prompt}]
#     }
    
#     # ← ADD THIS BLOCK
#     if system_prompt:
#         request_params["system"] = [
#             {
#                 "type": "text",
#                 "text": system_prompt,
#                 "cache_control": {"type": "ephemeral"}
#             }
#         ]
#     # ← END OF NEW BLOCK
    
#     response = client.messages.create(**request_params)  # ← Change this line to use **request_params

#     if not want_json:
#         input_t = response.usage.output_tokens 
#         output_t  = response.usage.input_tokens
#         cache_read_input_tokens  = response.usage.cache_read_input_tokens
        
#         print(f"Input tokens: {input_t}, Output tokens: {output_t}, cashed Token {cache_read_input_tokens}")
#         return response.content[0].text
#     else:
#         for i in range(max_json_try):
#             try:
#                 input_t = response.usage.output_tokens 
#                 output_t  = response.usage.input_tokens
#                 cache_read_input_tokens  = response.usage.cache_read_input_tokens

#                 print(f"Input tokens: {input_t}, Output tokens: {output_t}, cashed Token {cache_read_input_tokens}")
#                 response = response.content[0].text
#                 response = clean_and_load(response)
#                 return response
#             except json.JSONDecodeError as e:
#                 print(f"JSONDecodeError on attempt {i+1}: {e}")
#                 continue
#             except Exception as e:
#                 print(f"Unexpected error on attempt {i+1}: {e}")
#                 continue
#         return None
    
# credentials = get_secret(GCP_secret_name)

# response = call_sonnet4(prompt=dynamic_prompt,creds = credentials,max_json_try=3, want_json=True, system_prompt=prompt)
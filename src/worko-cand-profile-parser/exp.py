import json
import ast
import boto3
import re
import os
import base64
from datetime import datetime
from decimal import Decimal
import time
from docx import Document
import fitz
from io import BytesIO
from urllib.parse import unquote_plus
from botocore.exceptions import ClientError
import requests
import random
from typing import Tuple, Dict, Any, Optional, Union
from google.cloud import firestore
from google.oauth2 import service_account
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1 import Or, And
import uuid
from urllib.parse import unquote_plus

cv_path = r"C:\Users\Administrator\Desktop\worko_working\worko_cv_jd\cv\tech\shaukat_cv.pdf"
event = {'Records': [{'eventVersion': '2.1', 'eventSource': 'aws:s3', 'awsRegion': 'ap-south-1', 'eventTime': '2026-02-20T10:02:48.483Z', 'eventName': 'ObjectCreated:Put', 'userIdentity': {'principalId': 'AWS:AROATCKANHWV2MBXXE3V6:worko-corp-dev-workoCorp'}, 'requestParameters': {'sourceIPAddress': '103.176.210.4'}, 'responseElements': {'x-amz-request-id': '0GV2XM0G06SZCHGF', 'x-amz-id-2': 'x34y2miLD2LyN9AGVFLClux6M3yMIuG1hlWSrLcbegWm8EpI8llJ0nPkekh41t93bJGPpDXQcwDg8HsUEeOpw/dOdQBSNKZU'}, 's3': {'s3SchemaVersion': '1.0', 'configurationId': 'dc878d7e-0a7a-48a3-b24f-e9ca7c67352a', 'bucket': {'name': 'worko-corporate-cand-profile-dev', 'ownerIdentity': {'principalId': 'A1V0APDMR493SG'}, 'arn': 'arn:aws:s3:::worko-corporate-cand-profile-dev'}, 'object': {'key': 'companies/01K47MSBKS79ACY0BM6Z8VS3F5/bulk-cvs/01KHX80Z8F7FE17ZPYSEBAYN0G.pdf', 'size': 554118, 'eTag': 'daaf0aa1cde51652c86a77da2bb54e9e', 'sequencer': '00699831486FA6095A'}}}]}
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
    metadata = get_metadata(event)
    bulksourcetyperesumeid = metadata.get("bulksourcetyperesumeid", "")
    
    if bulksourcetyperesumeid:
        get_counts(db, bulksourcetyperesumeid)
    else:
        print("No bulksourcetyperesumeid found in metadata")



# def get_secret(secret_name):
#     secrets_client = boto3.client('secretsmanager', region_name='ap-south-1')
#     try:
#         response = secrets_client.get_secret_value(SecretId=secret_name)
#         return json.loads(response['SecretString'])
#     except ClientError as e:
#         print(f"Error getting secret: {e}")
#         return None

# def extract_text_from_pdf(pdf_path):
#     text = ""
#     with fitz.open(pdf_path) as pdf_document:
#         for page in pdf_document:
#             text += page.get_text()
#     return text

# class AzureOpenAIClient:
#     def __init__(self, azure_openai_secret, model="gpt-4o"):
#         self.model = model
#         self.endpoint = azure_openai_secret.get("AZURE_OPENAI_ENDPOINT", "")
#         self.api_key = azure_openai_secret.get("AZURE_OPENAI_API_KEY", "")
#         if model == "gpt-4o":
#             self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT_gpt-4o", "")
#             self.api_version = azure_openai_secret.get("AZURE_OPENAI_API_VERSION_gpt-4o", "2024-05-01-preview")
#         elif model == "gpt-4.1-mini":
#             self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT_gpt-4.1-mini", "")
#             self.api_version = azure_openai_secret.get("AZURE_OPENAI_API_VERSION_gpt-4.1-mini", "2024-05-01-preview")
    
#     def invoke_model_with_backoff(self, prompt, Task="Not specified"):
#         print(f"Task: {Task}")
#         url = f"{self.endpoint}/openai/deployments/{self.deployment_name}/chat/completions?api-version={self.api_version}"
#         headers = {"Content-Type": "application/json", "api-key": self.api_key}
#         data = {
#             "messages": [
#                 {"role": "system", "content": "You are a helpful assistant."},
#                 {"role": "user", "content": prompt}
#             ],
#             "temperature": 0.3
#         }
        
#         for attempt in range(3):
#             try:
#                 response = requests.post(url=url, headers=headers, json=data)
#                 response.raise_for_status()
#                 result = response.json()
#                 content = result["choices"][0]["message"]["content"]
#                 content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
#                 return json.loads(content)
#             except json.JSONDecodeError:
#                 if attempt == 2:
#                     raise
#                 time.sleep(2)
#             except requests.exceptions.HTTPError as e:
#                 raise

# def process_cv(processed_text, gpt_model):
#     processed_text = " ".join(processed_text.split())
    
#     parsed_prompt = (
#         f"You are an expert HR specialized in resume analysis and extracting structured data.\n\n"
#         f"Resume text:\n{processed_text}\n\n"
#         f"*** RULE: If you don't find any data in the resume ***\n"
#         f"- If the value is a number → use 0\n"
#         f"- If the value is a boolean → use false\n"
#         f"- If the value is a string → use an empty string \"\"\n"
#         f"- If the candidate is a fresher or not currently working → set candidateCurrentCompany = \"\"\n\n"
#         f"*** Mandatory data to find in the resume ***\n"
#         f"These fields MUST always be present in the output:\n"
#         f"1. candidateName\n2. candidateCurrentDesignation\n3. candidateCurrentCompany\n4. candidateTotalYOE\n5. candidateLocation\n\n"
#         f"*** Output Format (JSON only) ***\n"
#         f"{{{{\n"
#         f"  \"candidateName\": \"\",\n"
#         f"  \"about\":\"extract about me or summary or profile or objective from resume\",\n"
#         f"  \"education\": [{{\"collage\": \"\", \"degree\": \"\", \"startedYear\": \"\", \"passingYear\": \"\"}}],\n"
#         f"  \"multipleCandidateExperience\": [{{\"companyName\": \"\", \"designation\": \"\", \"department\": \"\", \"YOE\": 0, \"startDate\": \"\", \"endDate\": \"\"}}],\n"
#         f"  \"candidateEmail\": \"\",\n"
#         f"  \"candidatePhoneNumber\": \"\",\n"
#         f"  \"candidateNumber\": 0,\n"
#         f"  \"candidatePhoneCountryCode\": 0,\n"
#         f"  \"candidateCurrentCompany\": \"\",\n"
#         f"  \"candidateCurrentDesignation\": \"\",\n"
#         f"  \"candidateExperience\": 0,\n"
#         f"  \"candidateTotalYOE\": 0,\n"
#         f"  \"candidateRelevantYOE\": 0,\n"
#         f"  \"candidateNoticePeriod\": \"\",\n"
#         f"  \"candidateLocation\": \"\",\n"
#         f"  \"candidateReadyToRelocate\": false,\n"
#         f"  \"isNoticePeriodNegotiable\": false\n"
#         f"}}}}\n"
#     )
    
#     cv_extracted_parsed = gpt_model.invoke_model_with_backoff(parsed_prompt, Task="get cvExtractparsed step1")
#     return cv_extracted_parsed

# if __name__ == "__main__":
#     start = time.time()
#     env = "dev"
#     azure_openai_secret_name = f"AZURE-openai-secret-multimodel-{env}"
#     azure_openai_secret = get_secret(azure_openai_secret_name)
    
#     gpt4_1_mini = AzureOpenAIClient(azure_openai_secret, model="gpt-4o")
    
#     processed_text = extract_text_from_pdf(cv_path)
    
#     while True:
#         try:
#             result = process_cv(processed_text, gpt4_1_mini)
#             print(json.dumps(result, indent=2))
#             end = time.time()
#             print(f"\nTotal time taken: {end - start:.2f} seconds")
#             break
#         except Exception as e:
#             error_message = str(e).lower()
#             if any(term in error_message for term in ['throttling', 'throttled', 'rate limit', 'too many requests', '429']):
#                 print(f"Throttling error: {e}. Retrying in 3 seconds...")
#                 time.sleep(3)
#             else:
#                 print(f"Error: {e}")
#                 break

<<<<<<< HEAD
# gpt-4.1-mini confugrations
from importlib import metadata
import requests
=======
>>>>>>> 13ae8e1bd0e6cfb17cdf475ee089b828c78dc6fa
import json
import ast
import boto3
import re
import os
import base64
from datetime import datetime
from decimal import Decimal
import time
<<<<<<< HEAD
import json
from typing import Callable, Any
from lambda_function import *
from google.cloud import firestore
import uuid

def updated_firstore_resume_status(processingStatus,bulkSourceTypeResumeId,update_data,DBManager):
    """this function will update firestore document if a resume is processed successfully with cvExtractedParsed data and also update status of that resume in firestore document"""
    print("updating firestore document with cvExtractedParsed data and status of that resume in firestore document")
    
    doc_id = str(uuid.uuid4())
    update_data["id"] = doc_id
    update_data["bulkSourceTypeResumeId"] = bulkSourceTypeResumeId
    
    # Create document in bulkSourceTypeParseResumes collection
    child_collection_name = "bulkSourceTypeParseResumes"
    DBManager.update_firestore_document_data(child_collection_name, doc_id, update_data, processingStatus)
    
    # Increment totalResumesProcessed in bulkSourceTypeResumes collection if COMPLETED
    if processingStatus == "SUCCESS":
        print(f"Incrementing totalResumesProcessed : {processingStatus} of bulkSourceTypeResumeId {bulkSourceTypeResumeId}")
        
        parent_collection_name = "bulkSourceTypeResumes"
        parent_doc_ref = DBManager.db.collection(parent_collection_name).document(bulkSourceTypeResumeId)
        parent_doc_ref.update({"totalResumesProcessed": firestore.Increment(1)})
        print(f"Incremented totalResumesProcessed for {bulkSourceTypeResumeId}")
    elif processingStatus == "FAILED":
        print(f"Incrementing totalResumesFailed : {processingStatus} of bulkSourceTypeResumeId {bulkSourceTypeResumeId}")
        
        parent_collection_name = "bulkSourceTypeResumes"
        parent_doc_ref = DBManager.db.collection(parent_collection_name).document(bulkSourceTypeResumeId)
        parent_doc_ref.update({"totalResumesFailed": firestore.Increment(1)})
        print(f"Incremented totalResumesFailed for {bulkSourceTypeResumeId}")
        
        
    elif processingStatus == "DUPLICATE":
        print(f"Incrementing totalResumesDuplicate : {processingStatus} of bulkSourceTypeResumeId {bulkSourceTypeResumeId}")
        
        parent_collection_name = "bulkSourceTypeResumes"
        parent_doc_ref = DBManager.db.collection(parent_collection_name).document(bulkSourceTypeResumeId)
        parent_doc_ref.update({"totalResumesDuplicate": firestore.Increment(1)})
        print(f"Incremented totalResumesDuplicate for {bulkSourceTypeResumeId}")
        
    else:
        print(f"Unknown processingStatus: {processingStatus} for bulkSourceTypeResumeId {bulkSourceTypeResumeId}. No increment performed in totalResumesProcessed.")

def get_data_to_update_in_firstore(cvExtractedParsed,bulkSourceTypeResumeId,status):

    # send_final_cv_sqs(cvExtractedParsed,file_name,object_key,DBManager)
    candidateName = cvExtractedParsed.get("candidateName","")
    candidate_email = cvExtractedParsed.get("candidateEmail","")
    candidatePhoneNumber = cvExtractedParsed.get("candidatePhoneNumber","")
    candidateNumber = cvExtractedParsed.get("candidateNumber",0)
    candidatePhoneCountryCode = cvExtractedParsed.get("candidatePhoneCountryCode",0)
    phoneNumberDetails ={"candidatePhoneNumber":candidatePhoneNumber,"candidateNumber":candidateNumber,"candidatePhoneCountryCode":candidatePhoneCountryCode}
    createdAt = datetime.now().isoformat()
    updatedAt = datetime.now().isoformat()
    return {"bulkSourceTypeResumeId":bulkSourceTypeResumeId,
        "candidateName": candidateName,
        "candidateEmail": candidate_email,
        "phoneNumberDetails": phoneNumberDetails,
        "createdAt": createdAt,
        "updatedAt": updatedAt,
        "status":status
    }

def build_status_summary(all_docs: list):
    summary = {
        "SUCCESS": {"count": 0, "candidates": []},
        "FAILED": {"count": 0, "candidates": []},
        "DUPLICATE": {"count": 0, "candidates": []},
    }

    for data in all_docs:
        status = data.get("status")
        name = data.get("candidateName", "")
        email = data.get("candidateEmail", "")

        if status in summary:
            summary[status]["count"] += 1
            summary[status]["candidates"].append({
                "candidateName": name,
                "candidateEmail": email
            })

    return summary

def get_meta_data(event, context):
    s3_client = boto3.client('s3')

    # Extract bucket and key from event
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    # key = "companies/01JWAQF1G96E0SE9XHXSFGHNWW/bulk-cvs/01KH8PX3GBW8N6RP1SBRSXN79P.pdf"
    # bucket = "worko-corporate-cand-profile-dev"
    # Get object metadata
    response = s3_client.head_object(Bucket=bucket, Key=key)
    metadata = response.get('Metadata', {})
    return metadata
    # Extract your values
    # bulk_source_type_resume_id = metadata.get('bulksourcetyperesumeid')
    # company_id = metadata.get('companyid')
=======
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
>>>>>>> 13ae8e1bd0e6cfb17cdf475ee089b828c78dc6fa

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

<<<<<<< HEAD
def send_cv_summary_email(all_cv_parsing_summary, to_address):
    import csv
    from io import StringIO
    
    ses = boto3.client('ses', region_name='ap-south-1')
    source = "no-reply@worko.work"
    
    summary, total_count = all_cv_parsing_summary
    
    csv_buffer = StringIO()
    writer = csv.writer(csv_buffer)
    
    # SUCCESS section
    writer.writerow(["SUCCESS", f"Count: {summary['SUCCESS']['count']}", ""])
    writer.writerow(["Candidate Name", "Candidate Email", ""])
    for candidate in summary['SUCCESS']['candidates']:
        writer.writerow([candidate["candidateName"], candidate["candidateEmail"], ""])
    writer.writerow(["", "", ""])
    
    # FAILED section
    writer.writerow(["FAILED", f"Count: {summary['FAILED']['count']}", ""])
    writer.writerow(["Candidate Name", "Candidate Email", ""])
    for candidate in summary['FAILED']['candidates']:
        writer.writerow([candidate["candidateName"], candidate["candidateEmail"], ""])
    writer.writerow(["", "", ""])
    
    # DUPLICATE section
    writer.writerow(["DUPLICATE", f"Count: {summary['DUPLICATE']['count']}", ""])
    writer.writerow(["Candidate Name", "Candidate Email", ""])
    for candidate in summary['DUPLICATE']['candidates']:
        writer.writerow([candidate["candidateName"], candidate["candidateEmail"], ""])
    
    csv_content = csv_buffer.getvalue()
    
    subject = "Bulk CV Processing Complete - Summary Report"
    body_text = f"""Dear User,

Your bulk CV upload has been successfully processed.

Processing Summary:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total CVs Uploaded: {total_count}
Successfully Processed: {summary['SUCCESS']['count']}
Failed: {summary['FAILED']['count']}
Duplicates Detected: {summary['DUPLICATE']['count']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Please find the detailed report attached as a CSV file.

Best regards,
Worko Team"""
    
    raw_message = f"From: {source}\nTo: {to_address}\nSubject: {subject}\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=\"boundary\"\n\n--boundary\nContent-Type: text/plain\n\n{body_text}\n\n--boundary\nContent-Type: text/csv; name=\"cv_processing_summary.csv\"\nContent-Disposition: attachment; filename=\"cv_processing_summary.csv\"\n\n{csv_content}\n--boundary--"
    
    ses.send_raw_email(
        Source=source,
        Destinations=[to_address],
        RawMessage={"Data": raw_message}
    )
    print(f"Email sent to {to_address}")


cvExtractedParsed  = {
    "candidateName": "Shaukat Shaikh",
    "candidateEmail": "shaukatdatascience@gmail.com",
    "candidatePhoneNumber": "+91-9876543210",
    "candidateNumber": 9876543210,
    "candidatePhoneCountryCode": 91
}
parent_doc_id = "01KH8DQ92Z7PDCQ0QCG83ZN1PS"
# processingStatus ="SUCCESS"
processingStatus ="FAILED"
update_data = get_data_to_update_in_firstore(cvExtractedParsed,parent_doc_id,processingStatus)


parent_collection_name_for_firstore_updating="bulkSourceTypeResumes"
GCP_DATABASE_NAME = "worko-corp-db-dev"
GCP_secret_name = "GCP-firestore-secret-dev"
DBManager = FirestoreManager(GCP_secret_name,GCP_DATABASE_NAME)


# updated_firstore_resume_status(processingStatus,parent_doc_id,update_data,DBManager)
# get_doc ="2cf5b8fd-9192-4e3a-8e06-470d2a90318c"
# result = DBManager.get_document_firstore("bulkSourceTypeResumes","01KH8PX2NX9J5SQAV80A8769FF")
# result = DBManager.get_all_documents_from_collection("bulkSourceTypeParseResumes")
# result = DBManager.get_document_firstore("bulkSourceTypeResumes",parent_doc_id)
# result  = DBManager.get_documents_by_bulkSourceTypeResumeId("bulkSourceTypeParseResumes",parent_doc_id)
# all_cv_parsing_summary =build_status_summary(result)
# # result = get_meta_data(None,None)
# subject = "cv parsing reuslt summary"
# body_text = "see the below csv"
# to_address = "shaukatdatascience@gmail.com"
# send_cv_summary_email(all_cv_parsing_summary, to_address)

# with open(r"output.json", "w") as f:
#     json.dump(result, f, indent=4)
# print("Status summary:", build_status_summary(result))
# print(result)


# import requests

# url = "https://bdwmxdaqll.execute-api.ap-south-1.amazonaws.com/dev/bulk-source-type-resume/01KH8DQ92Z7PDCQ0QCG83ZN1PS"

# response = requests.get(url)

# print("Status Code:", response.status_code)
# print("Response:", response.json())

def get_meta_data(event):
    try:
        s3_client = boto3.client('s3')
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = event['Records'][0]['s3']['object']['key']
        response = s3_client.head_object(Bucket=bucket, Key=key)
        metadata = response.get('Metadata', {})
        
        if not metadata:
            print(f"Warning: No metadata found for s3://{bucket}/{key}")
            return {}
        return metadata
    except Exception as e:
        print(f"Error retrieving metadata: {e}")
        return {}


event = {"Records":[{"eventVersion":"2.1","eventSource":"aws:s3","awsRegion":"ap-south-1","eventTime":"2026-02-13T05:21:25.288Z","eventName":"ObjectCreated:Put","userIdentity":{"principalId":"AWS:AROATCKANHWV2MBXXE3V6:worko-corp-dev-workoCorp"},"requestParameters":{"sourceIPAddress":"103.176.210.127"},"responseElements":{"x-amz-request-id":"A7DP139505J83HYT","x-amz-id-2":"7qLalj01knes4BpKEg5sLH1PjcL91s9OGs69//2J775bV3sZLPXHSwrmOd1NLv3T0+tMFZQL58bR0lLKCVHtJFEc5LKEe1zZmU5N5y6A+Q4="},"s3":{"s3SchemaVersion":"1.0","configurationId":"a6c870b0-fd5d-4747-ac88-27e26b7ecba5","bucket":{"name":"worko-admin-cand-profile-dev","ownerIdentity":{"principalId":"A1V0APDMR493SG"},"arn":"arn:aws:s3:::worko-admin-cand-profile-dev"},"object":{"key":"bulk-cvs/01KHAQ4QXFP0HW6BSFRK926JH1.pdf","size":225212,"eTag":"296eeb83abfe1d84d866db9a55621a78","sequencer":"00698EB4D53FB3565C"}}}]}
print(get_meta_data(event))
#     ############################################################################
# def get_queue_url(queue_name):
#     sqs = boto3.client('sqs')
#     response = sqs.get_queue_url(QueueName=queue_name)
#     return response['QueueUrl']
=======
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
>>>>>>> 13ae8e1bd0e6cfb17cdf475ee089b828c78dc6fa

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

<<<<<<< HEAD
# OpenAIClient = AzureOpenAIClient(azure_openai_secret)    
# prompt   = "tell me about taj mahal in json style"
# output = OpenAIClient.invoke_model_with_backoff(prompt,Task= "get cvExtractparsed step1 " )


# print(output)


# import boto3
# from datetime import datetime

# def download_lambda_logs(function_name, output_file='lambda_logs.txt', max_events=200):
#     """Download last N CloudWatch logs for a Lambda function."""
#     logs_client = boto3.client('logs', region_name='ap-south-1')
#     log_group_name = f'/aws/lambda/{function_name}'
    
#     try:
#         # Get log streams sorted by last event time
#         streams_response = logs_client.describe_log_streams(
#             logGroupName=log_group_name,
#             orderBy='LastEventTime',
#             descending=True,
#             limit=5
#         )
        
#         all_events = []
        
#         # Fetch events from recent streams
#         for stream in streams_response['logStreams']:
#             stream_name = stream['logStreamName']
            
#             events_response = logs_client.get_log_events(
#                 logGroupName=log_group_name,
#                 logStreamName=stream_name,
#                 limit=max_events,
#                 startFromHead=False
#             )
            
#             all_events.extend(events_response['events'])
            
#             if len(all_events) >= max_events:
#                 break
        
#         # Sort by timestamp and take last N
#         all_events.sort(key=lambda x: x['timestamp'])
#         recent_events = all_events[-max_events:]
        
#         # Write to file
#         with open(output_file, 'w', encoding='utf-8') as f:
#             f.write(f"Lambda Function: {function_name}\n")
#             f.write(f"Log Group: {log_group_name}\n")
#             f.write(f"Downloaded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
#             f.write(f"Total Events: {len(recent_events)}\n")
#             f.write("="*80 + "\n\n")
            
#             for event in recent_events:
#                 timestamp = datetime.fromtimestamp(event['timestamp']/1000).strftime('%Y-%m-%d %H:%M:%S')
#                 f.write(f"[{timestamp}] {event['message']}\n")
        
#         print(f"Downloaded {len(recent_events)} log events to {output_file}")
        
#     except Exception as e:
#         print(f"Error downloading logs: {e}")

# # Usage
# download_lambda_logs('worko-bulk-jd-resume-matching-dev', 'lambda_logs.txt', 200)

=======
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
>>>>>>> 13ae8e1bd0e6cfb17cdf475ee089b828c78dc6fa

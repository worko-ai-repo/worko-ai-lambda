# gpt-4.1-mini confugrations
from importlib import metadata
import requests
import json
from typing import Tuple, Dict, Any, Optional, Union
import boto3
import time
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

# def decimal_default(obj):
#     if isinstance(obj, Decimal):
#         return float(obj)
#     raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

# def send_sqs_for_throttling_error(retry_queue_name,message_body):
#     try:
#         retry_counter = message_body.get("retry_counter", "retry_counter not found")
#         from datetime import datetime, timedelta
#         queue_url = get_queue_url(retry_queue_name)
#         sqs = boto3.client('sqs')
        
#         # message_body = {"processed_text": processed_text,"object_key": object_key,"from":"throttling error"}
#         delay_seconds = 5
        
#         current_time = datetime.now()
#         visible_time = current_time + timedelta(seconds=delay_seconds)
        
#         print(f"Sending message to SQS with retry_counter: {retry_counter}")
#         print(f"[SQS SEND] Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
#         print(f"[SQS SEND] Message will be visible at: {visible_time.strftime('%Y-%m-%d %H:%M:%S')}")
#         print(f"[SQS SEND] DelaySeconds: {delay_seconds}")
#         print(f"SQS message body for throttled steps: {json.dumps(str(message_body)[:100])}")
        
#         response = sqs.send_message(
#             QueueUrl=queue_url,
#             MessageBody=json.dumps(message_body, default=decimal_default),
#             DelaySeconds=delay_seconds
#         )
        
#         print(f"[SQS SEND] MessageId: {response.get('MessageId', 'N/A')}")
        
        
#     except Exception as sqs_error:
#         print(f"Error sending send_sqs_for_throttling_error step to SQS: {sqs_error}")
#         print(f"Queue URL attempted: {queue_url}")
#         print(f"Message body: {message_body}")

# retry_queue_name = "worko-cand-profile-parser-retry-queue-dev"

# for i in range(10):
#     message_body = {f"testing_and_test{i}":"7757852171"}
#     # time.sleep(2)
#     send_sqs_for_throttling_error(retry_queue_name,message_body)

    ############################################################################
# def get_queue_url(queue_name):
#     sqs = boto3.client('sqs')
#     response = sqs.get_queue_url(QueueName=queue_name)
#     return response['QueueUrl']





# retry_queue_name = "worko-cand-profile-parser-retry-queue-dev"
# print(get_queue_url(retry_queue_name))
# azure_openai_secret = {"AZURE_OPENAI_API_KEY" :"REDACTED",
#                         "AZURE_OPENAI_API_VERSION" : "2024-12-01-preview",
#                         "AZURE_OPENAI_DEPLOYMENT" : "gpt-4.1-mini",
#                         "AZURE_OPENAI_ENDPOINT":"https://aif-wrk-dev-sin-01.openai.azure.com"}

# def get_secret(secret_name):
#     secrets_client = boto3.client('secretsmanager', region_name='ap-south-1')

#     try:
#         response = secrets_client.get_secret_value(SecretId=secret_name)
#         secret_value = response['SecretString']
        
#         # Try to parse as JSON, fallback to string
#         try:
#             secret_data = json.loads(secret_value)
#         except json.JSONDecodeError:
#             secret_data = secret_value
#         return secret_data
#     except ClientError as e:
#         if e.response['Error']['Code'] == 'ResourceNotFoundException':
#             return {
#                 "statusCode": 404,
#                 "body": json.dumps({"error": f"Secret '{secret_name}' not found"})
#             }

# secret_name = "AZURE-openai-secret-multimodel-dev"
# azure_openai_secret =get_secret(secret_name)
# print(azure_openai_secret)


# class AzureOpenAIClient:
#     """Client for Azure OpenAI API with retry logic."""
    
#     DEFAULT_TEMPERATURE = 0.3
#     DEFAULT_API_VERSION = "2024-05-01-preview"
#     REQUEST_TIMEOUT = 30  # seconds
    
#     def __init__(self, azure_openai_secret: Dict[str, str]):
#         """Initialize Azure OpenAI client.
        
#         Args:
#             azure_openai_secret: Dict containing:
#                 - AZURE_OPENAI_ENDPOINT
#                 - deployment_name
#                 - api_key
#                 - AZURE_OPENAI_API_VERSION (optional)
#         """
#         if not isinstance(azure_openai_secret, dict):
#             raise TypeError("azure_openai_secret must be a dictionary")
        
#         self.endpoint = azure_openai_secret.get("AZURE_OPENAI_ENDPOINT", "")
#         self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT", "")
#         self.api_version = azure_openai_secret.get(
#             "AZURE_OPENAI_API_VERSION", 
#             self.DEFAULT_API_VERSION
#         )
#         self.api_key = azure_openai_secret.get("AZURE_OPENAI_API_KEY", "")
        
#         # Validate required fields
#         if not all([self.endpoint, self.deployment_name, self.api_key]):
#             raise ValueError(
#                 "Missing required Azure OpenAI configuration: "
#                 "AZURE_OPENAI_ENDPOINT, deployment_name, and api_key are required"
#             )
    
#     def invoke_model_with_backoff(
#         self,
#         prompt: str,
#         Task="Not specified",
#         system_content: str = "You are a helpful assistant.",
#         max_retries: int = 10,
#         base_delay: int = 2,
#         want_json: bool = True
#     ) -> Union[str, Dict[Any, Any]]:
#         """Invoke model with exponential backoff for rate limiting.
        
#         Args:
#             prompt: User prompt
#             system_content: System message for the model
#             max_retries: Maximum number of retry attempts
#             base_delay: Base delay for exponential backoff
#             want_json: Whether to parse response as JSON
            
#         Returns:
#             Model response as string or parsed JSON dict
#         """
#         for attempt in range(max_retries):
#             print("Task to Ai is :- ",Task)
#             try:
#                 return self.invoke_model(system_content, prompt, want_json)
            
#             except requests.exceptions.HTTPError as e:
#                 # Check for rate limiting (429) or server errors (5xx)
#                 if e.response.status_code in [500, 502, 503, 504]:
#                     if attempt < max_retries - 1:
#                         delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
#                         print(
#                             f"Rate limit or server error (status {e.response.status_code}). "
#                             f"Retrying in {delay:.2f} seconds..."
#                         )
#                         time.sleep(delay)
#                     else:
#                         raise
#                 else:
#                     # Don't retry for other HTTP errors (auth, not found, etc.)
#                     raise
            
#             except requests.exceptions.RequestException as e:
#                 # Network errors - retry
#                 if attempt < max_retries - 1:
#                     delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
#                     print(f"Network error: {e}. Retrying in {delay:.2f} seconds...")
#                     time.sleep(delay)
#                 else:
#                     raise
    
#     def invoke_model(
#         self,
#         system_content: str,
#         prompt: str,
#         want_json: bool = True,
#         max_json_retries: int = 3,
#         temperature: float = DEFAULT_TEMPERATURE
#     ) -> Union[str, Dict[Any, Any]]:
#         """Invoke Azure OpenAI model.
        
#         Args:
#             system_content: System message
#             prompt: User prompt
#             want_json: Whether to parse response as JSON
#             max_json_retries: Max retries for JSON parsing
#             temperature: Model temperature
            
#         Returns:
#             Model response as string or parsed JSON dict
#         """
#         url = (
#             f"{self.endpoint}/openai/deployments/{self.deployment_name}/"
#             f"chat/completions?api-version={self.api_version}"
#         )
        
#         headers = {
#             "Content-Type": "application/json",
#             "api-key": self.api_key
#         }
        
#         data = {
#             "messages": [
#                 {"role": "system", "content": system_content},
#                 {"role": "user", "content": prompt}
#             ],
#             "temperature": temperature
#         }
        
#         if not want_json:
#             response = requests.post(
#                 url=url, 
#                 headers=headers, 
#                 json=data,
#                 timeout=self.REQUEST_TIMEOUT
#             )
#             response.raise_for_status()
#             result = response.json()
#             return result["choices"][0]["message"]["content"]
        
#         # JSON mode with retries
#         for attempt in range(max_json_retries):
#             try:
#                 response = requests.post(
#                     url=url, 
#                     headers=headers, 
#                     json=data,
#                     timeout=self.REQUEST_TIMEOUT
#                 )
#                 response.raise_for_status()
#                 result = response.json()
#                 try :
#                     tokens = result["usage"]
#                     output_tokens= tokens["completion_tokens"]
#                     input_tokens= tokens["prompt_tokens"]
#                     total = tokens["total_tokens"]
#                     print(" Token usage details input_tokens :-",input_tokens,"output_tokens",output_tokens,"total",total)

#                 except Exception as e :
#                     print("errore occured input output token not found :--",e)
                
#                 # Extract and clean content
#                 content = result["choices"][0]["message"]["content"]
#                 content = content.strip()
                
#                 # Remove markdown code blocks
#                 if content.startswith("```"):
#                     content = content.removeprefix("```json").removeprefix("```")
#                     content = content.removesuffix("```").strip()
                
#                 return json.loads(content)
            
#             except json.JSONDecodeError as e:
#                 remaining = max_json_retries - attempt - 1
#                 print(f"JSON parse failed. Retries left: {remaining}")
#                 print(f"Error: {e}")
                
#                 if remaining == 0:
#                     print(f"Raw content: {content}")
#                     raise ValueError(f"Failed to parse JSON after {max_json_retries} attempts") from e
                
#                 time.sleep(2)  # Brief delay before retry
            
#             except (KeyError, IndexError) as e:
#                 print(f"Unexpected response structure: {result}")
#                 raise ValueError("Invalid response format from Azure OpenAI") from e
       

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



def check_duplicate_with_cv_age(cvExtractedParsed, object_key, DBManager):
    from datetime import datetime, timedelta
    
    email = cvExtractedParsed.get("candidateEmail", "")
    phone_number = cvExtractedParsed.get("candidateNumber", "")
    country_code = cvExtractedParsed.get("candidatePhoneCountryCode", "")
    
    is_corporate = "companies" in object_key
    collection = "corporateCandidateProfiles" if is_corporate else "centralCandidateProfiles"
    company_id = object_key.split("/")[1] if is_corporate else None
    resource_type = "CORP_CAND_BULK_CV_UPLOAD" if is_corporate else "ADMIN_CAND_BULK_CV_UPLOAD"
    
    candidate_profiles = DBManager.get_candidate_profiles(collection, company_id, email, phone_number, country_code)
    
    if not candidate_profiles:
        return None, None
    
    candidate_profile = candidate_profiles[0]
    parsed_cv_id = candidate_profile.get("candidateParsedCvId" if is_corporate else "latestCandidateParsedCvId")
    
    if not parsed_cv_id:
        return None, None
    
    parsed_cv_doc = DBManager.get_document_firstore("candidateParsedCvs", parsed_cv_id)
    
    if not parsed_cv_doc:
        return None, None
    
    cv_tracker = parsed_cv_doc.get("cvAwsS3FileTracker", [])
    matching_cv = next((cv for cv in cv_tracker if cv.get("resourceType") == resource_type), None)
    
    if not matching_cv:
        return None, None
    
    action_date_str = matching_cv.get("actionDate")
    if not action_date_str:
        return None, None
    
    action_date = datetime.fromisoformat(action_date_str.replace("+00:00", ""))
    three_months_ago = datetime.now() - timedelta(days=90)
    
    if action_date >= three_months_ago:
        return "DUPLICATE", None
    else:
        event_name = "OLDER_CV_CORPORATE_CAND_PROFILE_BULK_UPLOAD" if is_corporate else "OLDER_CV_ADMIN_CAND_PROFILE_BULK_UPLOAD"
        return "OLDER_CV", event_name

import json
import os
import re
import boto3
import uuid
from urllib.parse import unquote_plus
from email import policy
from email.parser import BytesParser
from botocore.exceptions import ClientError
from utils import *

def get_secret(secret_name):
    secrets_client = boto3.client('secretsmanager', region_name='ap-south-1')
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret_value = response['SecretString']
        try:
            secret_data = json.loads(secret_value)
        except json.JSONDecodeError:
            secret_data = secret_value
        return secret_data
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"Secret '{secret_name}' not found")
            raise Exception(f"Secret '{secret_name}' not found")
        raise

def send_ses_email(to_address, subject, body_text):
    ses = boto3.client('ses', region_name='ap-south-1')
    source = os.environ.get("SES_SOURCE_EMAIL", "no-reply@worko.work")
    return ses.send_email(
        Source=source,
        Destination={"ToAddresses": [to_address]},
        Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body_text}}}
    )

def extract_email_from_text(text):
    if not text:
        return None
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return m.group(0) if m else None

def extract_urls(text):
    return re.findall(r"https?://[\w\-\.\/~%\?=&+#]+", text)

def parse_company_id(to_header):
    if not to_header:
        return None
    # Try multiple patterns
    patterns = [
        r"([A-Za-z0-9_\-]+)@referral\.worko\.work",  # COMPANYID@referral.worko.work
        r"<([A-Za-z0-9_\-]+)@referral\.worko\.work>",  # <COMPANYID@referral.worko.work>
        r"to:?\s*([A-Za-z0-9_\-]+)@referral\.worko\.work",  # To: COMPANYID@referral.worko.work
    ]
    for pattern in patterns:
        m = re.search(pattern, to_header, re.IGNORECASE)
        if m:
            return m.group(1)
    return None

def get_attachments(email_obj):
    attachments = []
    for part in email_obj.walk():
        content_disposition = part.get_content_disposition()
        if content_disposition == "attachment":
            filename = part.get_filename()
            payload = part.get_payload(decode=True)
            attachments.append({
                "filename": filename,
                "content_type": part.get_content_type(),
                "data": payload,
            })
    return attachments

def update_sqs_queue(message_body):
    try:
        region = os.environ.get("SQS_REGION", "ap-south-1")
        eventQueueName = os.environ.get("EVENT_QUEUE_NAME", "worko-corp-app-event-queue")
        account_id = os.environ.get("ACCOUNT_ID", "211125353899")

        sqs = boto3.client('sqs', region_name=region)
        sqs_url = f"https://sqs.{region}.amazonaws.com/{account_id}/{eventQueueName}"
        print("Event updating in SQS:", message_body)

        message_body_msg = json.dumps(message_body)
        
        response = sqs.send_message(
            QueueUrl=sqs_url,
            MessageBody=message_body_msg
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps('Message sent to SQS!')
        }
    except Exception as e:
        print("Error sending message to SQS:", e)
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error sending message to SQS: {e}')
        }

def lambda_handler(event, context):
    print("Got event:", event)
    
    env = os.environ.get("ENVIRONMENT", "dev")
    secret_name = "AZURE-openai-secret-" + env
    AZURE_openai_secret = get_secret(secret_name)
    GCP_DATABASE_NAME = "worko-corp-db-" + env
    GCP_secret_name = "GCP-firestore-secret-" + env
    DBManager = FirestoreManager(GCP_secret_name, GCP_DATABASE_NAME)
    
    s3_client = boto3.client('s3')
    
    # Get single S3 record
    rec = event['Records'][0]
    s3_event = rec['s3']
    bucket_name = s3_event['bucket']['name']
    object_key = unquote_plus(s3_event['object']['key'])

    print(f"Processing S3 object: {bucket_name}/{object_key}")

    # Download email from S3
    response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
    raw_email_bytes = response['Body'].read()
    
    if not raw_email_bytes:
        return {'statusCode': 400, 'body': json.dumps('Empty email content')}
        
    email_obj = BytesParser(policy=policy.default).parsebytes(raw_email_bytes)
    verification_link = get_verification_link(email_obj)

    # Extract email headers
    subject = str(email_obj.get("subject") or "")
    to_header = str(email_obj.get("to") or "")
    from_header = str(email_obj.get("from") or "")
    delivered_to = str(email_obj.get("delivered-to") or "")
    
    print(f"Subject: {subject}")
    print(f"To: {to_header}")
    print(f"From: {from_header}")
    print(f"Delivered-To: {delivered_to}")
    print(f"All headers: {dict(email_obj.items())}")
    attachments = get_attachments(email_obj)
    # case 1 if it have subject as Gmail Forwarding Confirmation then send email to verify
    if len(attachments) ==0:
        print("Processing Gmail forwarding confirmation")
        To_email = get_email_id_from_subject(subject)
        verification_link = get_verification_link(email_obj)
        send_ses_email(to_address=To_email,body_text=verification_link, subject="Verify Email")
        


    
    
    if not attachments:
        return {'statusCode': 400, 'body': json.dumps('No attachments found')}
    else:

        # Find PDF attachment
        pdf_attachment = None
        for att in attachments:
            filename = (att.get("filename") or "").lower()
            if att.get("content_type") == "application/pdf" or filename.endswith(".pdf"):
                pdf_attachment = att
                break
        
        if not pdf_attachment:
            pdf_attachment = attachments[0]

        pdf_bytes = pdf_attachment.get("data")
        if not pdf_bytes:
            return {'statusCode': 400, 'body': json.dumps('Errore No PDF data found file formate is somthing else')}

        # Extract text from PDF
        resume_text = extract_text_from_pdf(pdf_bytes)
        print(f"Extracted {len(resume_text)} characters from PDF")

        # Parse CV using OpenAI
        OpenAIClient = AzureOpenAIClient(AZURE_openai_secret)
        cvExtractedParsed = process_cv(resume_text, OpenAIClient)
        
        if isinstance(cvExtractedParsed, str):
            return {'statusCode': 500, 'body': json.dumps('CV parsing failed')}
            
        print("CV parsed successfully")
        # print(str(cvExtractedParsed)[:1000] + "...")

        # Extract candidate details
        email = cvExtractedParsed.get("candidateEmail", "")
        phone_number = cvExtractedParsed.get("candidateNumber")
        country_code = cvExtractedParsed.get("candidatePhoneCountryCode")

        # Extract company ID from To/Delivered-To headers
        print(f"Extracting company ID from headers...")
        company_id = to_header.split("@")[0]  # Example extraction, replace with actual logic
        print(f"Company ID from headers: {company_id}")
        
        if not company_id:
            m = re.search(r"companies/([A-Za-z0-9_\-]+)/", object_key)
            company_id = m.group(1) if m else None
            print(f"Company ID from S3 path: {company_id}")

        if not company_id:
            return {'statusCode': 400, 'body': json.dumps('Company ID not found')}

        print(f"Company ID: {company_id}")

        # Check for duplicates
        collection = "corporateCandidateProfiles"
        data = DBManager.get_candidate_profiles(collection, company_id, email, phone_number, country_code)
        
        if data is not None:
            print(f"Duplicate found in {collection}: {data}")
            return {'statusCode': 200, 'body': json.dumps('Duplicate candidate found')}
        
        print("No duplicate found")

        # Upload CV to S3
        file_id = sort_key = str(uuid.uuid4())
        cv_bucket = os.environ.get("CV_UPLOAD_BUCKET", "worko-corporate-referral-source-cv-dev")
        s3_key = f"companies/{company_id}/referral-source-cvs/{file_id}.pdf"
        
        s3_client.put_object(Bucket=cv_bucket, Key=s3_key, Body=pdf_bytes)
        print(f"Uploaded CV to S3: {s3_key}")

        # Send SQS message
        sqs_send_data = {
            "event": "CORPORATE_CAND_PROFILE_REFERRAL_SOURCE",
            "companyId": company_id,
            "candidateCvAwsS3FileName": f"{file_id}.pdf",
            "cvExtractedParsed": cvExtractedParsed
        }
        
        update_sqs_queue(sqs_send_data)
        print("SQS message sent successfully")

        return {
            'statusCode': 200,
            'body': json.dumps('Processing complete')
        }

if __name__ == "__main__":
    # For local testing purposes
    test_event = {
        'Records': [{
            'eventVersion': '2.1',
            'eventSource': 'aws:s3',
            'awsRegion': 'ap-south-1',
            'eventTime': '2026-01-16T11:10:24.783Z',
            'eventName': 'ObjectCreated:Put',
            'userIdentity': {
                'principalId': 'AWS:AROATCKANHWVTQO36WAQQ:shaukat.shaikh@worko.ai'
            },
            'requestParameters': {
                'sourceIPAddress': '202.94.161.171'
            },
            'responseElements': {
                'x-amz-request-id': 'AQ7F1K38HT9K8M0J',
                'x-amz-id-2': 'DajJ+JmB2yrzJ0XOcjGIXgw4/T3w/dds9PLCkwXg3ZAxawPWKytGorJg1MrF1w8FM9FbQ1B1Dhd+jR2E2XWh5ZFEO8xH+I2/'
            },
            's3': {
                's3SchemaVersion': '1.0',
                'configurationId': 'fae01573-f817-4895-87c4-1537d6ba2f85',
                'bucket': {
                    'name': 'worko-referral-email-dev',
                    'ownerIdentity': {'principalId': 'A1V0APDMR493SG'},
                    'arn': ('arn:aws:s3:::worko-referral-email-dev')
                },
                'object': {
                    "key": "referral-sourcetype/h5sr7qn1j2aa12ug5aabbam582ggce6hlef0kd01",
                    "size": 6305,
                    "eTag": "8571e0bb6c1a874285eb1d6b5e9e3806",
                    "sequencer": "00696A1CA0BE95DB35"
                }
            }
        }]
    }
    lambda_handler(test_event, None)

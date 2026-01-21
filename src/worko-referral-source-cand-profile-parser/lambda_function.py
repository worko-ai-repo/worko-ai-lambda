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
    msg_id = event.get("Records")[0].get("ses").get("mail").get("messageId")
    # Get single S3 record
    # rec = event['Records'][0]
    # s3_event = rec['s3']
    # bucket_name = s3_event['bucket']['name']
    # object_key = unquote_plus(s3_event['object']['key'])

    # print(f"Processing S3 object: {bucket_name}/{object_key}")

    bucket_name = "worko-referral-email-"+env
    object_key=f"referral-sourcetype/{msg_id}"
    
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
    x_forwarded_to = str(email_obj.get("x-forwarded-to") or "")
    company_id = x_forwarded_to.split("@")[0]
    print(f"Extracting company ID from headers...")
    print(f"Company ID from headers: {company_id}")
    print(f"Subject: {subject}")
    print(f"To: {to_header}")
    print(f"From: {from_header}")
    print(f"Delivered-To: {delivered_to}")
    print(f"X-Forwarded-To: {x_forwarded_to}")
    print(f"All headers: {dict(email_obj.items())}")
    attachments = get_attachments(email_obj)
    # case 1 if it have subject as Gmail Forwarding Confirmation then send email to verify
    if len(attachments) ==0:
        print("Processing Gmail forwarding confirmation")
        To_email = get_email_id_from_subject(subject)
        verification_link = get_verification_link(email_obj)
        
        # Validate before sending email
        if To_email and verification_link:
            send_ses_email(to_address=To_email, body_text=verification_link, subject="Verify Email")
            print(f"Verification email sent to {To_email}")
            return {'statusCode': 200, 'body': json.dumps('Verification email sent')}
        else:
            print(f"Missing data - To_email: {To_email}, verification_link: {verification_link}")
            return {'statusCode': 400, 'body': json.dumps('Invalid email format or missing verification link')}
        


    
    
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



        # company_id = to_header.split("@")[0]  # old wrong logic Example extraction, replace with actual logic

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
        "Records": [
            {
            "eventSource": "aws:ses",
            "eventVersion": "1.0",
            "ses": {
                "mail": {
                "timestamp": "2026-01-19T12:43:07.914Z",
                "source": "forwarding-noreply@google.com",
                "messageId": "jrtlq5db37hp9ifj50jqj465buv1itm8iktqv481", #"1r9r51shhsn072a7i9fmf56ipgmolk5uhlgf9ig1",
                "destination": [
                    "01JWAQF1G96E0SE9XHXSFGHNWW@referral.worko.work"
                ],
                "headersTruncated": False,
                "headers": [
                    {
                    "name": "Return-Path",
                    "value": "<forwarding-noreply@google.com>"
                    },
                    {
                    "name": "Received",
                    "value": "from mail-yx1-f53.google.com (mail-yx1-f53.google.com [74.125.224.53]) by inbound-smtp.ap-south-1.amazonaws.com with SMTP id vb2gbk6kdmptv9m9n25g8u7df2cjspvb61vunl81 for 01JWAQF1G96E0SE9XHXSFGHNWW@referral.worko.work; Mon, 19 Jan 2026 12:43:07 +0000 (UTC)"
                    },
                    {
                    "name": "X-SES-Spam-Verdict",
                    "value": "PASS"
                    },
                    {
                    "name": "X-SES-Virus-Verdict",
                    "value": "PASS"
                    },
                    {
                    "name": "Received-SPF",
                    "value": "pass (spfCheck: domain of google.com designates 74.125.224.53 as permitted sender)"
                    },
                    {
                    "name": "Authentication-Results",
                    "value": "amazonses.com; spf=pass; dkim=pass; dmarc=pass"
                    },
                    {
                    "name": "X-SES-RECEIPT",
                    "value": "AEFBQUFBQUFBQUFGY05JR25DR1VDeDRrcS9iMlJRZUxtaHVUeHdlT2hITDcxUWhIMXVyYytBZnJ2V3gxSzNiaWxxUEdnWnV1eWtGM1NhV2NKRkpEWTM5SGRMc3hUNnJkWEtQR3V6WjFzdXVJS3VGeEtnNWhiWDNjem9QK3BpblR2UTBNUXd1RThTZk96QVIrYUY5ZkF4c1dnelZMclU1U3MwSkdnQ1Y0YjY0Q0M2Mk56cnd6VEhCdDdZMTZvWU5tMDNrVlo5cjNvMXAwS0ZORExvWTVyQkxUdTFCb3UrMDFkRmwvbndoaGZhNkhMTU1JT2xjWkR2MWREaER3dmNLcVc5RlBOOUJ3SFFwaVp4cUFkclVpNXRQTmVHOXBUQ2YrWUNXNEZpSlJPRTd6STFOVnVVOTdKWGc9PQ=="
                    },
                    {
                    "name": "MIME-Version",
                    "value": "1.0"
                    },
                    {
                    "name": "Date",
                    "value": "Mon, 19 Jan 2026 18:13:04 +0530"
                    },
                    {
                    "name": "Message-ID",
                    "value": "<CAA6HCTj1K1w5V+jJrPiUv8Do6CcztHZ5Hsdq5_kO7uYT0munqg@mail.gmail.com>"
                    },
                    {
                    "name": "Subject",
                    "value": "(Gmail Forwarding confirmation – Receive mail from shaukt1998@gmail.com"
                    },
                    {
                    "name": "From",
                    "value": "Gmail Team <forwarding-noreply@google.com>"
                    },
                    {
                    "name": "To",
                    "value": "01JWAQF1G96E0SE9XHXSFGHNWW@referral.worko.work"
                    },
                    {
                    "name": "Content-Type",
                    "value": "text/plain; charset=\"UTF-8\""
                    }
                ],
                "commonHeaders": {
                    "returnPath": "forwarding-noreply@google.com",
                    "from": [
                    "Gmail Team <forwarding-noreply@google.com>"
                    ],
                    "date": "Mon, 19 Jan 2026 18:13:04 +0530",
                    "to": [
                    "01JWAQF1G96E0SE9XHXSFGHNWW@referral.worko.work"
                    ],
                    "messageId": "<CAA6HCTj1K1w5V+jJrPiUv8Do6CcztHZ5Hsdq5_kO7uYT0munqg@mail.gmail.com>",
                    "subject": "(Gmail Forwarding confirmation – Receive mail from shaukt1998@gmail.com"
                }
                },
                "receipt": {
                "timestamp": "2026-01-19T12:43:07.914Z",
                "processingTimeMillis": 960,
                "recipients": [
                    "01JWAQF1G96E0SE9XHXSFGHNWW@referral.worko.work"
                ],
                "spamVerdict": {
                    "status": "PASS"
                },
                "virusVerdict": {
                    "status": "PASS"
                },
                "spfVerdict": {
                    "status": "PASS"
                },
                "dkimVerdict": {
                    "status": "PASS"
                },
                "dmarcVerdict": {
                    "status": "PASS"
                },
                "action": {
                    "type": "Lambda",
                    "functionArn": "arn:aws:lambda:ap-south-1:211125353899:function:worko-referral-source-cand-profile-parser-dev",
                    "invocationType": "Event"
                }
                }
            }
            }
        ]
        }
    lambda_handler(test_event, None)

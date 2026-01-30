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


    company_id = extract_company_id_from_email(x_forwarded_to)
    if company_id:
        print("Got company ID from X-Forwarded-To header (Gmail forwarded email):", company_id)

    # Priority 2: To header (Direct emails)
    if not company_id:
        company_id = extract_company_id_from_email(to_header)
        if company_id:
            print("Got company ID from To header (Outlook/Direct email):", company_id)

    # Priority 3: Delivered-To or envelope recipient
    if not company_id:
        company_id = extract_company_id_from_email(delivered_to)
        if company_id:
            print("Got company ID from Delivered-To header (Fallback):", company_id)

    # Priority 4: Check SES recipient from event (most reliable)
    if not company_id:
        try:
            ses_recipients = event.get("Records")[0].get("ses").get("receipt").get("recipients", [])
            for recipient in ses_recipients:
                company_id = extract_company_id_from_email(recipient)
                if company_id:
                    print("Got company ID from SES recipient (Event data):", company_id)
                    break
        except:
            pass

    # Priority 5: Parse Received headers for envelope recipient
    if not company_id:
        received_headers = email_obj.get_all("received") or []
        for received in received_headers:
            if "for" in received and "referral.worko.work" in received:
                company_id = extract_company_id_from_email(received)
                if company_id:
                    print("Got company ID from Received header (Envelope recipient):", company_id)
                    break



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
        return {'statusCode': 200, 'body': json.dumps('No attachments found')}
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
        if company_id:
            data = DBManager.get_candidate_profiles(collection, company_id, email, phone_number, country_code)
            
            if data is not None:
                print(f"Duplicate found in {collection}: {data}")
                return {'statusCode': 200, 'body': json.dumps('Duplicate candidate found')}
            
            print("No duplicate found")

            # Upload CV to S3
            file_id = sort_key = str(uuid.uuid4())
            cv_bucket = os.environ.get("CV_UPLOAD_BUCKET", "worko-corporate-referral-source-cv-dev")
            s3_key = f"companies/{company_id}/referral-source-cvs/{file_id}.pdf"
            print(f"Uploading CV to S3: {cv_bucket}/{s3_key}")
            
            s3_client.put_object(Bucket=cv_bucket, Key=s3_key, Body=pdf_bytes, ContentType='application/pdf')
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
        else:
            return {
                'statusCode': 500,
                'body': json.dumps('No comapny id found in email headers')
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
                "timestamp": "2026-01-30T14:38:39.823Z",
                "source": "shaukatdatascience+caf_=01JWAQF1G96E0SE9XHXSFGHNWW=referral.worko.work@gmail.com",
                "messageId": "osfqm2002g0aihailrb1q2g5ll6eor7gcjn7kh01",
                "destination": [
                    "shaukatdatascience@gmail.com"
                ],
                "headersTruncated": False,
                "headers": [
                    {
                    "name": "Return-Path",
                    "value": "<shaukatdatascience+caf_=01JWAQF1G96E0SE9XHXSFGHNWW=referral.worko.work@gmail.com>"
                    },
                    {
                    "name": "Received",
                    "value": "from mail-lj1-f179.google.com (mail-lj1-f179.google.com [209.85.208.179]) by inbound-smtp.ap-south-1.amazonaws.com with SMTP id osfqm2002g0aihailrb1q2g5ll6eor7gcjn7kh01 for 01JWAQF1G96E0SE9XHXSFGHNWW@referral.worko.work; Fri, 30 Jan 2026 14:38:39 +0000 (UTC)"
                    },
                    {
                    "name": "X-SES-Spam-Verdict",
                    "value": "PASS"
                    },
                    {
                    "name": "X-SES-Virus-Verdict",
                    "value": "PASS"
                    }
                ],
                "commonHeaders": {
                    "returnPath": "shaukatdatascience+caf_=01JWAQF1G96E0SE9XHXSFGHNWW=referral.worko.work@gmail.com",
                    "from": [
                    "Shaukat Shaikh <shaukt1998@gmail.com>"
                    ],
                    "date": "Fri, 30 Jan 2026 20:09:43 +0530",
                    "to": [
                    "shaukatdatascience@gmail.com"
                    ],
                    "messageId": "<CAA6HCTh6JcrEqzua+CN29ng26F=uFE6Yx_NpCaC4yXSNGzohYg@mail.gmail.com>",
                    "subject": ""
                }
                },
                "receipt": {
                "timestamp": "2026-01-30T14:38:39.823Z",
                "processingTimeMillis": 1326,
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

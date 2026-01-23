# Worko Referral Source Candidate Profile Parser Lambda - Deployment Guide

## Overview
* This is a completely new flow for handling referral source candidates via email forwarding.
* Lambda function for parsing candidate profiles from referral emails (Gmail/Outlook forwarding), extracting resume attachments, checking for duplicates in Firestore, and triggering SQS events.
* There are 6 steps of prerequisites to check for this lambda

---

## 1. Environment Variables of Lambda Function
These are automatically set in `template.yaml`:
```yaml
COMPANY_ID_PATTERN: prod-->@referral\\.worko\\.ai / dev-->"@referral\\.worko\\.work"  # Email pattern for company ID extraction
ENVIRONMENT: dev/prod  # Deployment environment
SQS_REGION: ap-south-1         # AWS region for SQS
EVENT_QUEUE_NAME: worko-corp-app-event-queue  # SQS queue name
CV_UPLOAD_BUCKET: worko-corporate-referral-source-cv-{env}  # S3 bucket for CVs
SES_SOURCE_EMAIL: no-reply@worko.ai  # SES sender email

```

## 2. AWS Secrets Manager
Create or check if present, following two secrets in AWS Secrets Manager:

### AZURE-openai-secret-{env}
```json
{
  "AZURE_OPENAI_ENDPOINT": "https://aif-wrk-dev-sin-01.openai.azure.com",
  "AZURE_OPENAI_DEPLOYMENT": "gpt-4o",
  "AZURE_OPENAI_API_KEY": "REDACTED",
  "AZURE_OPENAI_API_VERSION": "2025-01-01-preview"
}
```

### GCP-firestore-secret-{env}
```json
{
  "type": "service_account",
  "project_id": "worko-dev",
  "private_key_id": "REDACTED",
  "private_key": "REDACTED",
  "client_email": "worko-gcp-firestore@worko-dev.iam.gserviceaccount.com",
  "client_id": "REDACTED",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/worko-gcp-firestore%40worko-dev.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}
```

---

## 3. S3 Buckets
Ensure these S3 buckets exist:
- `worko-referral-email-{env}` - For storing incoming emails from SES
- `worko-corporate-referral-source-cv-{env}` - For storing extracted CV PDFs

---

## 4. Firestore Collections
Ensure this collection exists in `worko-corp-db-{env}`:
- `corporateCandidateProfiles` - For referral source candidates

---

## 5. IAM Permissions (All Defined in template.yaml)
### IAM Permissions Required
- **S3**: GetObject, ListBucket, PutObject
- **Secrets Manager**: GetSecretValue
- **SQS**: SendMessage, GetQueueUrl
- **SES**: SendEmail, SendRawEmail (for verification emails)

### Lambda Settings
- **Runtime**: Python 3.10
- **Timeout**: 900 seconds (15 minutes)
- **Memory**: 1024 MB
- **Architecture**: x86_64

---

## Dependencies (layer/requirements.txt)
```
boto3>=1.34.0
google-cloud-firestore>=2.14.0
google-auth>=2.27.0
PyMuPDF==1.22.5
requests>=2.31.0
```

---

## Deployment Commands

### Build
1) Navigate to lambda directory and build:
```bash
cd src/worko-referral-source-cand-profile-parser
sam build  # or sam build --use-container
```

2) Deploy using commands below:

### Deploy to Prod
```bash
sam deploy \
  --stack-name worko-referral-source-cand-profile-parser-prod-stack \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=prod \
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \
  --no-confirm-changeset
```

### Deploy to Dev
```bash
sam deploy \
  --stack-name worko-referral-source-cand-profile-parser-dev-stack \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=dev \
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \
  --no-confirm-changeset
```

---

## Functionality of This Lambda

### 1. Email Processing
- Receives emails via SES to `{COMPANY_ID}@referral.worko.work`
- Retrieves email from S3 bucket
- Parses email headers to extract company ID
- Handles both Gmail forwarding and Outlook direct emails

### 2. Company ID Extraction (Priority Order)
1. **X-Forwarded-To** header (Gmail forwarded emails)
2. **To** header (Outlook/Direct emails)
3. **Delivered-To** header (Fallback)
4. **SES recipient** from event data (Most reliable)
5. **Received** headers (Envelope recipient)

### 3. Gmail Forwarding Verification
- Detects Gmail forwarding confirmation emails (no attachments)
- Extracts verification link from email body
- Sends verification link via SES to the user's email

### 4. Resume Parsing
- Extracts PDF attachments from email
- Extracts text from PDF using PyMuPDF
- Parses candidate information using Azure OpenAI (2-step process)

### 5. Duplicate Detection
- Checks `corporateCandidateProfiles` collection
- Filters by: `companyId` AND (`candidateEmail` OR `phone + countryCode`)

### 6. SQS Event Triggering
**If no duplicate found:**

```json
{
  "event": "CORPORATE_CAND_PROFILE_REFERRAL_SOURCE",
  "companyId": "01HZM7MDK1QZCCV7ZD41VGBAVD",
  "candidateCvAwsS3FileName": "{uuid}.pdf",
  "cvExtractedParsed": { ... }
}
```

---

## Extracted Data Structure (cvExtractedParsed)
```json
{
  "candidateName": "John Doe",
  "candidateEmail": "john@example.com",
  "candidatePhoneNumber": "+919876543210",
  "candidateNumber": 9876543210,
  "candidatePhoneCountryCode": 91,
  "candidateCurrentCompany": "Tech Corp",
  "candidateCurrentDesignation": "Senior Engineer",
  "candidateExperience": 5.5,
  "candidateTotalYOE": 5,
  "candidateRelevantYOE": 5,
  "candidateCurrentCTC": 1500000,
  "candidateExpectedCTC": 2000000,
  "candidateNoticePeriod": 60,
  "candidateLocation": "Bangalore",
  "candidateReadyToRelocate": false,
  "isNoticePeriodNegotiable": false,
  "coreSkills": [
    {"skillName": "System Architecture", "years": 5}
  ],
  "technicalSkills": [
    {"skillName": "Python", "years": 5}
  ],
  "softSkills": [
    {"skillName": "Leadership"}
  ],
  "userPreferredDepartments": ["Engineering"],
  "userPreferredIndustries": ["Information Technology"],
  "userPreferredlocations": [],
  "userPreferredRoles": ["Senior Engineer"]
}
```

---

## Email Flow Examples

### Gmail Forwarding Flow
1. User forwards email to `01HZM7MDK1QZCCV7ZD41VGBAVD@referral.worko.work`
2. Gmail sends verification email
3. Lambda detects verification email (no attachments)
4. Lambda sends verification link to user via SES
5. User clicks verification link
6. Future emails are forwarded automatically
7. Lambda extracts company ID from `X-Forwarded-To` header

### Outlook Direct Flow
1. User sends email directly to `01HZM7MDK1QZCCV7ZD41VGBAVD@referral.worko.work`
2. Lambda extracts company ID from `To` header
3. Lambda processes resume attachment

---

## Troubleshooting

### Company ID Not Found
- Check email headers in CloudWatch logs
- Verify email was sent to correct format: `{COMPANY_ID}@referral.worko.work`
- Check `COMPANY_ID_PATTERN` environment variable

### Lambda Timeout
- Increase timeout in `template.yaml` (current: 900s)
- Check Azure OpenAI API response time

### PDF Parsing Errors
- Verify PDF is not corrupted
- Check CloudWatch logs for file size
- Ensure PyMuPDF can read the PDF format

### Duplicate Detection Not Working
- Verify Firestore collection names
- Check GCP credentials in Secrets Manager
- Ensure phone number format is correct (integer without country code)

### SQS Not Triggered
- Verify SQS queue exists
- Check SQS permissions in IAM role
- Verify environment variables (SQS_REGION, EVENT_QUEUE_NAME)

### Gmail Verification Not Sent
- Check SES permissions
- Verify `SES_SOURCE_EMAIL` is verified in SES
- Check CloudWatch logs for SES errors

---

## Stack Information
- **Stack Name**: `worko-referral-source-cand-profile-parser-{env}-stack`
- **Function Name**: `worko-referral-source-cand-profile-parser-{env}`
- **Layer Name**: `worko-referral-source-cand-profile-parser-deps-{env}`
- **Region**: ap-south-1

---

**Deployment Status**: ✅ Active in Dev | ⏳ Pending in Prod

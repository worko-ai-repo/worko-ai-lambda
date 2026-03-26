# Worko Candidate Profile Parser Lambda - Deployment Guide

## Overview
* Lambda function for parsing candidate profiles from PDF/DOCX resumes, checking for duplicates in Firestore, and triggering SQS events for corporate and admin workflows.
* This is completely new flow and does not replace any lambda.
* There are 6 steps of prerequisites to check for this lambda


### 1. Environment Variables of Lambda Function for SQS Queue
These are automatically set in `template.yaml`:
```yaml
ENVIRONMENT: dev/prod  # Deployment environment
SQS_REGION: ap-south-1         # AWS region for SQS
EVENT_QUEUE_NAME: worko-corp-app-event-queue  # SQS queue name

```

## 2. S3 Triggers (2 Manual Setup Required)

### Trigger 1: Corporate Candidate Profiles
- **Source**: S3
- **Bucket**: `worko-corporate-cand-profile-{env}`
- **Event Type**: All object create events (PUT)
- **Prefix**: `companies/`
- **Suffix**: `.pdf`

**Example S3 Path:**
```
s3://worko-corporate-cand-profile-dev/companies/{companyId}/bulk-cvs/{filename}.pdf
```

### Trigger 2: Admin Candidate Profiles
- **Source**: S3
- **Bucket**: `worko-admin-cand-profile-{env}`
- **Event Type**: All object create events (PUT)
- **Prefix**: `bulk-cvs/`
- **Suffix**: `.pdf`

**Example S3 Path:**
```
s3://worko-admin-cand-profile-dev/bulk-cvs/{filename}.pdf
```


### 3. AWS Secrets Manager
Create or check if present, following two secrets in AWS Secrets Manager:

#### AZURE-openai-secret-{env}
```json
{"AZURE_OPENAI_ENDPOINT":"https://aif-wrk-dev-sin-01.openai.azure.com",
"AZURE_OPENAI_DEPLOYMENT":"gpt-4o","AZURE_OPENAI_API_KEY":"REDACTED",
"AZURE_OPENAI_API_VERSION":"2025-01-01-preview"}

```

#### GCP-firestore-secret-{env}
```json
{
  "type": "service_account",
  "project_id": "worko-dev",
  "private_key_id": "REDACTED",
  "private_key": "REDACTED\n",
  "client_email": "worko-gcp-firestore@worko-dev.iam.gserviceaccount.com",
  "client_id": "REDACTED",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/worko-gcp-firestore%40worko-dev.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}
```



### 4. S3 Buckets
Ensure these S3 buckets exist (created by Rohit's code):
- `worko-corporate-cand-profile-{env}` - For corporate candidate profiles
- `worko-admin-cand-profile-{env}` - For admin candidate profiles

### 5. Firestore Collections
Ensure these collections exist in `worko-corp-db-{env}` (created by Rohit's code):
- `corporateCandidateProfiles` - For corporate candidates
- `centralCandidateProfiles` - For admin candidates

### 6. IAM Permissions (All Defined in template.yaml)
### IAM Permissions Required
- **S3**: GetObject, ListBucket, PutObject
- **Bedrock**: InvokeModel (for image-based resume processing)
- **Secrets Manager**: GetSecretValue
- **SQS**: SendMessage, GetQueueUrl

### Lambda Settings
- **Runtime**: Python 3.10
- **Timeout**: 900 seconds (15 minutes)
- **Memory**: 1024 MB
- **Architecture**: x86_64

---

## Dependencies (layer/requirements.txt)
```
boto3==1.35.84
PyMuPDF==1.24.14
requests==2.32.3
google-cloud-firestore==2.19.0
google-auth==2.36.0
python-docx==1.1.2
```

---


---

## Deployment Commands

### Build
1) Navigate to lambda directory and build:
```bash
cd src/worko-cand-profile-parser
sam build  # or sam build --use-container
```

2) Deploy using commands below:


### Deploy to Prod
```bash
sam deploy \
  --stack-name worko-cand-profile-parser-prod-stack \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=prod \
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \
  --no-confirm-changeset
```

### Deploy to Dev
```bash
sam deploy \
  --stack-name worko-cand-profile-parser-dev-stack \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=dev \
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \
  --no-confirm-changeset
```


## ## Functionality of This Lambda

### 1. Resume Parsing
- Extracts text from PDF/DOCX files
- Handles image-based PDFs using AWS Bedrock (Claude)
- Parses candidate information using Azure OpenAI

### 2. Duplicate Detection
**Corporate Path** (`companies/` in S3 key):
- Checks `corporateCandidateProfiles` collection
- Filters by: `companyId` AND (`candidateEmail` OR `phone + countryCode`)

**Admin Path** (no `companies/` in S3 key):
- Checks `centralCandidateProfiles` collection
- Filters by: `candidateEmail` OR `phone + countryCode`

### 3. SQS Event Triggering
**If no duplicate found:**

**Corporate Event:**
```json
{
  "event": "CORPORATE_CAND_PROFILE_BULK_UPLOAD",
  "companyId": "01JWAQF1G96E0SE9XHXSFGHNWW",
  "candidateCvAwsS3FileName": "resume.pdf",
  "cvExtractedParsed": { ... }
}
```

**Admin Event:**
```json
{
  "event": "ADMIN_CAND_PROFILE_BULK_UPLOAD",
  "candidateCvAwsS3FileName": "resume.pdf",
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

## Troubleshooting

### Lambda Timeout
- Increase timeout in `template.yaml` (current: 900s)
- Check Azure OpenAI API response time

### PDF Parsing Errors
- Verify PDF is not corrupted
- Check CloudWatch logs for file size
- Image-based PDFs require Bedrock access

### Duplicate Detection Not Working
- Verify Firestore collection names
- Check GCP credentials in Secrets Manager
- Ensure phone number format is correct (integer without country code)

### SQS Not Triggered
- Verify SQS queue exists
- Check SQS permissions in IAM role
- Verify environment variables (SQS_REGION, EVENT_QUEUE_NAME, ACCOUNT_ID)

---

## Stack Information
- **Stack Name**: `worko-cand-profile-parser-{env}-stack`
- **Function Name**: `worko-cand-profile-parser-{env}`
- **Layer Name**: `worko-cand-profile-parser-deps-{env}`
- **Region**: ap-south-1

---

**Deployment Status**: ✅ Active in Dev | ⏳ Pending in Prod

09/04/2026
just added this line in prompt to make it consistant
f"candidateLocation must be only city name followed by state name examples. Mumbai, Maharahstra,  Bengaluru Karnataka"

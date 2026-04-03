# Worko Candidate Profile Parser Lambda - Deployment Guide

## Overview of lambda
* Lambda function for parsing candidate profiles from PDF/DOCX resumes, checking for duplicates in Firestore, and triggering SQS to store it in firstore.
* This is existing lambda and replace older lambda.

### Deploy to Prod commands
1) Navigate to lambda directory and build:
```bash
cd src/worko-cand-profile-parser
sam build  # or sam build --use-container
```

```bash
sam deploy \
  --stack-name worko-cand-profile-parser-prod-stack \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=prod \
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \
  --no-confirm-changeset
```

### Deploy to Dev commands
```bash
sam deploy \
  --stack-name worko-cand-profile-parser-dev-stack \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=dev \
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \
  --no-confirm-changeset
```

* There are 6 steps of to check for this lambda after you run the deployemnts script
### 1 Manual Configuration Required
**IMPORTANT**: After deployment, manually configure two S3 event notifications:

1. **Corporate Bucket** (`worko-corporate-cand-profile-{env}`):
   - Event type: `ObjectCreated:Put`
   - Destination : SQS queue
   - Choose from your SQS queues : `worko-cand-profile-parser-queue-{env}`


2. **Admin Bucket** (`worko-admin-cand-profile-{env}`):
   - Event type: `ObjectCreated:Put`
   - Destination : SQS queue
   - Destination: SQS queue `worko-cand-profile-parser-queue-{env}`
---

### 2. check trigers are added by script or not if yes the check "worko-cand-profile-parser-queue-{env}"
1) select -> edit -> Activate trigger checkbox
2)                  ->Batch size = 25
3)                  ->Batch window = 15
4)  triger cand-profile-parser-retry-queue-{env} is created

### 3. two SQS are created
worko-cand-profile-parser-queue-{env} -> visiblity delay 5 minutes
cand-profile-parser-retry-queue-{env} 

### 4. Environment Variables of Lambda Function for SQS Queue
These are automatically set in `template.yaml`:
```yaml
ENVIRONMENT: dev/prod  # Deployment environment
SQS_REGION: ap-south-1         # AWS region for SQS
EVENT_QUEUE_NAME: worko-corp-app-event-queue  # SQS queue name
```

### 5. lambda settings 
- **Runtime**: Python 3.11
- **Timeout**: 300 seconds (5 minutes)
- **Memory**: 1024 MB
- **Architecture**: x86_64



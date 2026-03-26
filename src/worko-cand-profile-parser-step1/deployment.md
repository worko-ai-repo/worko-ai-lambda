# Worko Candidate Profile Parser - Step 1

## Purpose
Downloads CVs from cloud storage (Google Drive, OneDrive, Dropbox) and stores them in S3 for processing.

## Trigger
API Gateway POST request from backend when user clicks "Import CVs from database" button.

## Input
```json
{
  "requesterName": "John Doe",
  "platform": "Google Drive",
  "url": "https://drive.google.com/...",
  "accessKey": "token_here",
  "requestId": "01KHGBHW3Y11XS9DFJ9CFRTVMX"
}
```

## Output
```json
{
  "message": "Step 1 completed: CVs downloaded",
  "requestId": "01KHGBHW3Y11XS9DFJ9CFRTVMX",
  "status": "PROCESSING"
}
```

## Deployment

### Build
```bash
cd src/worko-cand-profile-parser-step1
sam build --use-container
```

### Deploy
```bash
sam deploy --stack-name worko-cand-profile-parser-step1-dev-stack \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=dev
```

## Environment Variables
- `ENVIRONMENT`: dev/staging/prod

## IAM Permissions
- S3: Read/Write access to worko-*-{env} buckets
- CloudWatch: Logs

## Next Step
Triggers Step 2: Extract text from CVs

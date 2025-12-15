# Production Deployment Checklist - Repo name:- worko-ai-lambda Repoworko-sourcetype-jd-resume-matching

## Pre-Deployment Verification

### 1. Environment Variables Update
- [ ] Change `ENVIRONMENT` from `dev` to `prod`
- [ ] Update `DYNAMO_TABLE_NAME` to production table (currently: `worko`)
- [ ] Update `JOBS_DYNAMO_TABLE_NAME` to production table (currently: `worko-job-app`)
- [ ] Update `S3_VECTOR_BUCKET_NAME` to production bucket (currently: `worko-s3-vector-bucket`)


### 2. AWS Resources Verification
- [ ] Production S3 bucket exists and is accessible
- [ ] Production DynamoDB tables exist with correct schema
- [ ] Production S3 vector bucket exists
- [ ] IAM role has permissions for all production resources
- [ ] CloudWatch log group created for production

### 3. Dependencies Check
- [ ] Verify all dependencies in `requirements.txt`:
  - `requests>=2.31.0`
  - `PyMuPDF==1.23.26`
  - `google-cloud-firestore>=2.11.0`
  - `google-auth>=2.17.0`
- [ ] Build Lambda layer with production dependencies
- [ ] Test layer compatibility with Python 3.10

### 4. Lambda Configuration
- [ ] Function name: `worko-sourcetype-jd-resume-matching-prod`
- [ ] Runtime: Python 3.10
- [ ] Timeout: 180 seconds (verify if sufficient for prod workload)
- [ ] Memory: 256 MB (consider increasing for prod: 512 MB or 1024 MB)
- [ ] Region: Verify production region

### 5. IAM Permissions
- [ ] S3 read permissions (`s3:GetObject`, `s3:ListBucket`)
- [ ] DynamoDB permissions (`Query`, `GetItem`, `PutItem`, `UpdateItem`, `Scan`)
- [ ] Bedrock model access (`bedrock:InvokeModel`)
- [ ] SQS permissions (`sqs:SendMessage` for `worko-app-event-queue`) for resume parser
- [ ] CloudWatch Logs permissions
- [ ] VPC permissions (if applicable)

### 6. Security Review
- [ ] Remove hardcoded API keys from template.yaml
- [ ] Store `AZURE_OPENAI_API_KEY` in AWS Secrets Manager
- [ ] Store GCP credentials in AWS Secrets Manager
- [ ] Enable encryption at rest for S3 buckets
- [ ] Enable encryption for DynamoDB tables
- [ ] Review IAM policies for least privilege
- [ ] Enable VPC endpoints for AWS services (optional)

### 7. Azure OpenAI Configuration
- [ ] Verify production Azure OpenAI endpoint
- [ ] Confirm `gpt-4o` deployment exists in production
- [ ] Validate API version: `2025-01-01-preview`
- [ ] Test API key validity
- [ ] Check rate limits and quotas

### 8. GCP Firestore Configuration
- [ ] production GCP project: `worko-prod` (update if different)
- [ ] Confirm service account has Firestore permissions
- [ ] Test Firestore connectivity from Lambda
- [ ] Verify collection names match production

### 9. Code Review
- [ ] Remove debug/test code
- [ ] Remove commented code blocks
- [ ] Verify all error handling is production-ready
- [ ] Check logging levels (remove verbose debug logs)


## Deployment Steps

### 1. Build Lambda Layer
```bash
cd layer
mkdir -p python/lib/python3.10/site-packages
pip install -r requirements.txt -t python/lib/python3.10/site-packages/
cd ..
```

### 2. Update template.yaml
```bash
# Change Environment parameter default to 'prod'
# Update all environment variables for production
# Update function name suffix to '-prod'
```

### 3. Deploy with SAM
```bash
sam build --template-file template.yaml
sam deploy \
  --stack-name worko-sourcetype-jd-resume-matching-prod \
  --parameter-overrides Environment=prod \
  --capabilities CAPABILITY_IAM \
  --region <prod-region> \
  --no-confirm-changeset
```

### 4. Verify Deployment
```bash
aws lambda get-function \
  --function-name worko-sourcetype-jd-resume-matching-prod \
  --region <prod-region>
```

## Post-Deployment Verification

### 1. Smoke Tests
- [ ] Invoke Lambda with test event
- [ ] Verify CloudWatch logs are created
- [ ] Check response format is correct
- [ ] Verify DynamoDB updates
- [ ] Confirm Firestore updates

### 2. Monitoring Setup
- [ ] CloudWatch alarms for errors
- [ ] CloudWatch alarms for duration > 150s
- [ ] CloudWatch alarms for throttles
- [ ] CloudWatch alarms for memory usage > 80%
- [ ] Set up SNS notifications for alarms

### 3. Performance Validation
- [ ] Average execution time < 60s
- [ ] Error rate < 1%
- [ ] Memory usage within limits
- [ ] No throttling observed

### 4. Integration Testing
- [ ] Test with real production job descriptions
- [ ] Test with various resume formats
- [ ] Verify scoring accuracy
- [ ] Confirm feedback generation
- [ ] Test rejection scenarios

## Rollback Plan

### If Issues Occur
1. Revert to previous Lambda version:
```bash
aws lambda update-function-code \
  --function-name worko-sourcetype-jd-resume-matching-prod \
  --s3-bucket <backup-bucket> \
  --s3-key <previous-version.zip>
```

2. Update CloudFormation stack to previous version:
```bash
sam deploy --stack-name worko-sourcetype-jd-resume-matching-prod --no-execute-changeset
```






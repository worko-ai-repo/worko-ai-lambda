# Local Deployment Guide

## Prerequisites

### 1. Install Required Tools
- **SAM CLI**: Download from [AWS SAM CLI releases](https://github.com/aws/aws-sam-cli/releases/latest)
- **Docker Desktop only in windows**: Download from [Docker Desktop](https://www.docker.com/products/docker-desktop) only windows
- **AWS CLI**: Already configured with valid credentials
- **Python 3.10**: Required runtime for Lambda functions

### 2. Dependencies Check
Verify all dependencies in `layer/requirements.txt`:
- `requests>=2.31.0`
- `PyMuPDF==1.23.26`
- `google-cloud-firestore>=2.11.0`
- `google-auth>=2.17.0`
- `anthropic` (for Claude models)
- `boto3` (AWS SDK)
- `botocore`

### 3. AWS Resources Required
- S3 bucket for SAM deployments
- DynamoDB tables: `worko`, `worko-job-app`
- S3 vector bucket: `worko-s3-vector-bucket`
- AWS Secrets Manager for API keys and credentials
- CloudWatch log groups

### 4. External Service Dependencies
- **Azure OpenAI**: API key and endpoint access
- **GCP Firestore**: Service account credentials
- **Bedrock**: Model access permissions

### 5. Required IAM Permissions by Lambda

#### Common Deployment Permissions (Both Lambdas):
**CloudFormation:**
- `cloudformation:CreateStack`
- `cloudformation:UpdateStack`
- `cloudformation:DescribeStacks`
- `cloudformation:CreateChangeSet`
- `cloudformation:ExecuteChangeSet`

**Lambda:**
- `lambda:CreateFunction`
- `lambda:UpdateFunctionCode`
- `lambda:GetFunction`
- `lambda:PublishLayerVersion`

**IAM:**
- `iam:CreateRole`
- `iam:AttachRolePolicy`
- `iam:PassRole`
- `iam:PutRolePolicy`

**S3:**
- `s3:GetObject`
- `s3:PutObject`
- `s3:ListBucket`

#### worko-sourcetype-jd-resume-matching Specific Permissions:
**DynamoDB:**
- `dynamodb:Query` (worko table)
- `dynamodb:GetItem` (worko table)
- `dynamodb:PutItem` (worko table)
- `dynamodb:UpdateItem` (worko table)
- `dynamodb:Scan` (worko table)

**Secrets Manager:**
- `secretsmanager:GetSecretValue` (AZURE_OPENAI_API_KEY)
- `secretsmanager:GetSecretValue` (GCP-firestore-secret)

**Bedrock:**
- `bedrock:InvokeModel` (Claude models)

#### worko-resume-parser Specific Permissions:
**DynamoDB:**
- `dynamodb:Query` (worko, worko-job-app tables)
- `dynamodb:GetItem` (worko, worko-job-app tables)
- `dynamodb:PutItem` (worko, worko-job-app tables)
- `dynamodb:UpdateItem` (worko, worko-job-app tables)
- `dynamodb:Scan` (worko, worko-job-app tables)

**S3:**
- `s3:GetObject` (worko-s3-vector-bucket)
- `s3:PutObject` (worko-s3-vector-bucket)

**SQS:**
- `sqs:SendMessage` (worko-app-event-queue)

**Secrets Manager:**
- `secretsmanager:GetSecretValue` (GCP-firestore-secret)

**Bedrock:**
- `bedrock:InvokeModel` (Nova models)

**CloudWatch (Both Lambdas):**
- `logs:CreateLogGroup`
- `logs:CreateLogStream`
- `logs:PutLogEvents`

### 6. Configure AWS Credentials
```bash
# Option 1: SSO (Recommended)
export AWS_PROFILE=your-profile-name
aws configure sso

### 7. Pre-Deployment Checklist

#### Environment Variables Verification:
- [ ] `ENVIRONMENT` set to correct value (prod)
- [ ] `DYNAMO_TABLE_NAME` points to correct table (`worko`)
- [ ] `JOBS_DYNAMO_TABLE_NAME` points to correct table (`worko-job-app`)
- [ ] `S3_VECTOR_BUCKET_NAME` points to correct bucket (`worko-s3-vector-bucket`)
- [ ] `S3_BUCKET_NAME` points to correct bucket (`worko-app-{env}`)

#### AWS Resources Verification:
- [ ] S3 bucket exists and is accessible
- [ ] DynamoDB tables exist with correct schema
- [ ] S3 vector bucket exists
- [ ] IAM role has permissions for all resources
- [ ] CloudWatch log group created

#### Lambda Configuration:
- [ ] Runtime: Python 3.10
- [ ] Timeout: 180 seconds (sourcetype), 120 seconds (resume-parser)
- [ ] Memory: 256 MB (consider 512 MB or 1024 MB for prod)
- [ ] Region: Verify correct region


### 8. Verify Setup
```bash
# Check SAM CLI if not then install
sam --version

# Check Docker do only if using docker
docker --version
docker ps

# Check AWS credentials
aws sts get-caller-identity
```

---

## Lambda 1: worko-sourcetype-jd-resume-matching-prod (NEW LAMBDA)

### Navigate to Directory
```bash
cd src/worko-sourcetype-jd-resume-matching
```

### Build
```bash
mac -->> sam build / windows -->> sam build --use-container 
```

### Deploy
```bash
sam deploy \
  --stack-name worko-sourcetype-jd-resume-matching-dev-stack \ ##your lambda name with suffix stack
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \ 
  --parameter-overrides Environment=prod \ ## put prod here
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \  ## put one s3 bucket name which willl be used by sam
  --no-confirm-changeset
```

## Lambda 2: worko-resume-parser-prod (EXISTING LAMBDA - REPLACEMENT)

### Navigate to Directory
```bash
cd src/worko-resume-parser
```

### Build
```bash
mac -->> sam build / windows -->> sam build --use-container (i am using docker thats why)
```

### Deploy
```bash
sam deploy \
  --stack-name worko-resume-parser-dev-stack \ ##your lambda name with suffix stack
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=prod\ ## put prod here
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \  ## put one s3 bucket name
  --no-confirm-changeset
```


## Quick Commands Reference

### Test Lambda Locally
```bash
# After sam build
sam local invoke --event test-event.json
```

### View Logs
```bash
# Sourcetype Lambda
aws logs tail /aws/lambda/worko-sourcetype-jd-resume-matching-dev --follow --region ap-south-1

# Resume Parser Lambda
aws logs tail /aws/lambda/worko-resume-parser-dev --follow --region ap-south-1
```

### Invoke Deployed Lambda
```bash
# Sourcetype Lambda
aws lambda invoke \
  --function-name worko-sourcetype-jd-resume-matching-dev \
  --region ap-south-1 \
  --payload '{"test":"data"}' \
  response.json

# Resume Parser Lambda
aws lambda invoke \
  --function-name worko-resume-parser-dev \
  --region ap-south-1 \
  --payload '{"test":"data"}' \
  response.json
```

---

## Troubleshooting

### Docker Not Running
**Error**: `Running AWS SAM projects locally requires a container runtime`
**Solution**: Start Docker Desktop and ensure it's running

### Permission Denied
**Error**: `AccessDenied` or `not authorized to perform`
**Solution**: Check AWS credentials and IAM permissions

### S3 Bucket Error
**Error**: `S3 Bucket not specified`
**Solution**: Always include `--s3-bucket` parameter in deploy command

### Build Fails
**Error**: `SAM build failed`
**Solution**: 
1. Ensure Docker is running
2. Check `layer/requirements.txt` exists
3. Verify template.yaml syntax

### Stack Already Exists
**Error**: `Stack already exists`
**Solution**: Use update instead of create, or delete existing stack first

---

## Environment-Specific Deployments

### Change Environment
Simply change the `Environment` parameter:
- `Environment=dev` → Development
- `Environment=staging` → Staging  
- `Environment=prod` → Production

### Resource Naming
Resources are automatically named with environment suffix:
- Lambda: `worko-*-{env}`
- Stack: `worko-*-{env}-stack`
- Layer: `worko-*-deps-{env}`

---

## Notes

- **Docker Required**: `--use-container` flag needs Docker for building layers
- **Permissions**: Ensure your AWS role has CloudFormation and Lambda permissions
- **S3 Bucket**: Must exist and be accessible in your AWS account
- **Region**: All commands use `ap-south-1` region
- **Environment Isolation**: Each environment creates separate AWS resources

---

## Post-Deployment Verification

### 1. Smoke Tests
- [ ] Invoke Lambda with test event
- [ ] Verify CloudWatch logs are created
- [ ] Check response format is correct
- [ ] Verify DynamoDB updates
- [ ] Confirm Firestore updates (if applicable)

### 2. Monitoring Setup
- [ ] CloudWatch alarms for errors
- [ ] CloudWatch alarms for duration > threshold
- [ ] CloudWatch alarms for throttles
- [ ] CloudWatch alarms for memory usage > 80%
- [ ] Set up SNS notifications for alarms

### 3. Performance Validation
- [ ] Average execution time within limits
- [ ] Error rate < 1%
- [ ] Memory usage within limits
- [ ] No throttling observed

### 4. Integration Testing
- [ ] Test with real job descriptions/resumes
- [ ] Verify scoring accuracy (sourcetype matching)
- [ ] Confirm parsing accuracy (resume parser)
- [ ] Test rejection scenarios
- [ ] Verify queue integration (resume parser)

### 5. Rollback Plan
If issues occur:
```bash
# Revert to previous Lambda version
aws lambda update-function-code \
  --function-name worko-{lambda-name}-{env} \
  --s3-bucket {backup-bucket} \
  --s3-key {previous-version.zip}

# Update CloudFormation stack to previous version
sam deploy --stack-name {stack-name} --no-execute-changeset
```

---

**Happy Deploying! 🚀**
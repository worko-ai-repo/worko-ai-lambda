# Resume Signup Skills Parser - Deployment Guide

## Overview
This Lambda function parses resumes during signup to extract core skills, technical skills, soft skills, preferred departments, and years of experience.

## Changes Summary
- **Purpose**: Resume parsing for signup flow with skills extraction
- **AI Model**: Azure OpenAI GPT-4o
- **Dependencies**: PyMuPDF, python-docx, boto3, requests

## Deployment Steps

### 1. Build
Navigate to lambda directory and build:
```bash
cd src/worko-resume-signup-skills-parser
sam build  # or sam build --use-container
```

### 2. Deploy to Prod
```bash
sam deploy \
  --stack-name worko-resume-signup-skills-parser-prod-stack \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=prod \
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \
  --no-confirm-changeset
```

### 3. Deploy to Dev
```bash
sam deploy \
  --stack-name worko-resume-signup-skills-parser-dev-stack \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=dev \
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \
  --no-confirm-changeset
```

## Function Details
- **Function Name**: `worko-resume-signup-skills-parser-{env}`
- **Stack Name**: `worko-resume-signup-skills-parser-{env}-stack`
- **Layer Name**: `worko-resume-signup-skills-parser-deps-{env}`
- **Timeout**: 120 seconds
- **Memory**: 512 MB
- **Runtime**: Python 3.10

## Environment Variables
- `ENVIRONMENT`: Deployment environment (dev/staging/prod)
- `S3_BUCKET_NAME`: S3 bucket for resume storage
- `DYNAMO_TABLE_NAME`: DynamoDB table name
- `AZURE_OPENAI_*`: Azure OpenAI configuration
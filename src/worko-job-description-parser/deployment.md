# Job Description Parser - Deployment Guide

## Overview
This deployment updates the AI model from GCP Vertex AI Claude Sonnet 4 to Azure OpenAI GPT-5.2 due to GCP quota limitations (429 rate limit errors).

## Changes Summary
- **AI Model**: GCP Vertex AI Claude Sonnet 4 → Azure OpenAI GPT-5.2
- **Code Changes**: Updated inference logic in `lambda_function.py`
- **Dependencies**: Added Azure OpenAI client libraries to layer requirements

##  Deployment Steps

### 1. Update Secrets Manager
add new 4 variables in "AZURE-openai-secret-multimodel-"+env from json i given
### 2. Deploy Lambda Function
Since only code and layer dependencies have changed, use the standard deployment process:

#### Build
1) Navigate to lambda directory and build:
```bash
cd src/worko-job-description-parser
sam build  # or sam build --use-container
```

2) Deploy using commands below:

#### Deploy to Prod
```bash
sam deploy \
  --stack-name worko-job-description-parser-prod-stack \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=prod \
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \
  --no-confirm-changeset
```

#### Deploy to Dev
```bash
sam deploy \
  --stack-name worko-job-description-parser-dev-stack \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=dev \
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \
  --no-confirm-changeset
```

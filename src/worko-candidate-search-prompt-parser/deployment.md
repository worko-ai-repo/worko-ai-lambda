
# Worko Candidate Search Prompt Parser - Deployment Guide

Date: 2025-01-15

## Prerequisites

Create `AZURE-openai-secret-multimodel-{env}` in AWS Secrets Manager with the following structure:

```json
{
  "AZURE_OPENAI_API_KEY": "REDACTED",
  "AZURE_OPENAI_ENDPOINT": "https://aif-wrk-dev-sin-01.openai.azure.com",
  "AZURE_OPENAI_DEPLOYMENT_gpt-4.1-mini": "gpt-4.1-mini",
  "AZURE_OPENAI_API_VERSION_gpt-4.1-mini": "2024-12-01-preview",
  "AZURE_OPENAI_DEPLOYMENT_gpt-4o": "gpt-4o",
  "AZURE_OPENAI_API_VERSION_gpt-4o": "2025-01-01-preview"
}
```

## Lambda Function Overview

**Function Name**: `worko-candidate-search-prompt-parser`

**Purpose**: Parses natural language search queries into structured format with experience and CTC threshold adjustments

**Features**:
- Natural language query parsing using GPT-4o
- Experience range adjustment based on role seniority (0-3y, 3-6y, 6-10y, 10+y)
- CTC range adjustment based on salary bands (high/low paying roles)
- Follows check_experience and check_ctc validation logic

## Deployment Commands

### Build

1) Navigate to lambda directory and build:
```bash
cd src/worko-candidate-search-prompt-parser
sam build --use-container
```

### Deploy to Dev
```bash
sam deploy \
  --stack-name worko-candidate-search-prompt-parser-dev-stack \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=dev \
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \
  --no-confirm-changeset
```

### Deploy to Prod
```bash
sam deploy \
  --stack-name worko-candidate-search-prompt-parser-prod-stack \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=prod \
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \
  --no-confirm-changeset
```

## Testing

Test the function using the provided test event:
```bash
aws lambda invoke \
  --function-name worko-candidate-search-prompt-parser-dev \
  --region ap-south-1 \
  --payload file://test-event.json \
  response.json
```

## Threshold Adjustment Logic

### Experience Ranges:
- **0-3 years**: Gap = 1 year
- **3-6 years**: Gap = 1.5 years
- **6-10 years**: Gap = 2 years
- **10+ years**: Follow check_experience logic

### CTC Ranges:
- **High-paying (max * 1.2 > 10 LPA)**: Allow ECTC up to 120% of max
- **Low-paying (max * 1.2 <= 10 LPA)**: Allow ECTC up to 130% of max

## Environment Variables

- `ENVIRONMENT`: Deployment environment (dev/staging/prod)

## IAM Permissions

- `secretsmanager:GetSecretValue`: Access Azure OpenAI credentials
- CloudWatch Logs: Basic execution logging

## Notes

- Uses GPT-4o model for query parsing
- Timeout: 120 seconds
- Memory: 512 MB
- Runtime: Python 3.10

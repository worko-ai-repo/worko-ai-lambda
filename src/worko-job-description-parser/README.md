# Worko Job Description Parser Lambda

Lambda function for parsing job descriptions using AI models (Claude Sonnet 4 via Vertex AI).

## Dependencies

### requirements.txt
```
boto3>=1.28.0
botocore>=1.31.0
anthropic[vertex]>=0.18.0
google-auth>=2.23.0
google-auth-oauthlib>=1.1.0
google-auth-httplib2>=0.1.1
requests>=2.31.0
```

## Environment Variables

```yaml
ENVIRONMENT: dev
S3_BUCKET_NAME: worko-app-dev
DYNAMO_TABLE_NAME: worko
JOBS_DYNAMO_TABLE_NAME: worko-job-app
acc_type: service_account
project_id: worko-dev
client_email: worko-gcp-firestore@worko-dev.iam.gserviceaccount.com
token_uri: https://oauth2.googleapis.com/token
private_key: [GCP private key]
```

## AWS Secrets Manager

**Secret Name**: `GCP-secrect` (region: `ap-south-1`)

```json
{
  "type": "service_account",
  "project_id": "worko-dev",
  "private_key": "REDACTED",
  "client_email": "worko-gcp-firestore@worko-dev.iam.gserviceaccount.com",
  "token_uri": "https://oauth2.googleapis.com/token"
}
```

## IAM Permissions

- `logs:*` - CloudWatch Logs
- `s3:GetObject`, `s3:ListBucket` - S3 access
- `dynamodb:Query`, `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:UpdateItem`, `dynamodb:Scan` - DynamoDB
- `secretsmanager:GetSecretValue` - Secrets Manager
- `bedrock:InvokeModel` - Bedrock AI models

## Deployment

```bash
# Install dependencies
cd layer
mkdir -p python/lib/python3.10/site-packages
pip install -r requirements.txt -t python/lib/python3.10/site-packages/

# Deploy with SAM
sam build --template-file template.yaml
sam deploy --guided --stack-name worko-job-description-parser-stack
```

## Configuration

- **Runtime**: Python 3.10
- **Timeout**: 180 seconds
- **Memory**: 256 MB
- **Region**: ap-south-1
- **AI Model**: Claude Sonnet 4 (`claude-sonnet-4@20250514`)

## Test Event

```json
{
  "JOB_DESC": "Senior Software Engineer with 5+ years Python and AWS experience..."
}
```

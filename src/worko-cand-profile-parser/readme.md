# Worko Candidate Profile Parser Lambda

## 📖 Overview

This Lambda function powers the **bulk CV upload feature** for both admin and corporate users. It processes resumes in parallel, extracts structured data using AI models, checks for duplicates, and sends email summaries upon completion.

---

## 🏗️ Architecture Flow

### 1. **S3 Upload Trigger**
- Frontend uploads CVs to S3 buckets:
  - **Corporate**: `worko-corporate-cand-profile-{env}`
  - **Admin**: `worko-admin-cand-profile-{env}`
- S3 sends event notifications to SQS: `worko-cand-profile-parser-queue-{env}`

### 2. **SQS Batching**
- SQS waits **15 seconds** to collect up to **25 messages** per batch
- Lambda is triggered with batch of 1-25 CV details

### 3. **Lambda Processing**
- **Concurrency**: 30 concurrent executions
- **Parallel Processing**: Uses ThreadPoolExecutor with 10 workers to process CVs in parallel
- **Timeout**: 5 minutes (300 seconds)
- **Memory**: 512 MB

### 4. **AI Model Fallback Chain**
For each CV, the Lambda tries models in this order:
1. **GPT-4**: `gpt-4o`, `gpt-4.1-mini`
2. **GPT-5**: `gpt-5.2` (2 attempts)
3. **Gemini**: `gemini-2.5-flash` (2 attempts)
4. **Retry SQS**: If all models throttle → send to `worko-cand-profile-parser-retry-queue-{env}` with 90-second delay

### 5. **Retry Mechanism**
- Retry SQS: `worko-cand-profile-parser-retry-queue-{env}`
- Delay increases with retry count: `90 * retry_counter` seconds
- Maximum retries: **5 attempts**
- After 5 retries → marked as **FAILED** in Firestore

### 6. **Duplicate Detection**
- After successful parsing, checks Firestore collection: `bulkSourceTypeParseResumes`
- Matches by: `candidateEmail` and `candidatePhoneNumber`
- Status updates:
  - **DUPLICATE**: Found existing record
  - **SUCCESS**: Unique record, sends to backend SQS
  - **FAILED**: Parsing error or max retries exceeded

### 7. **Firestore Tracking**
- Collection: `bulkSourceTypeResumes`
- Tracks counts: `totalUploaded`, `successCount`, `failedCount`, `duplicateCount`
- When `successCount + failedCount + duplicateCount == totalUploaded` → triggers email summary

### 8. **Email Summary**
- Sent via AWS SES when all CVs are processed
- Contains breakdown of SUCCESS, FAILED, DUPLICATE, and LARGE_RESUME_FILE statuses

---

## 🔧 Key Components

### Environment Variables
| Variable | Description | Example |
|----------|-------------|----------|
| `ENVIRONMENT` | Deployment environment | `dev`,`prod` |
| `SQS_REGION` | AWS region for SQS | `ap-south-1` |
| `EVENT_QUEUE_NAME` | Backend event queue | `worko-corp-app-event-queue` |

### S3 Buckets
- **Corporate**: `worko-corporate-cand-profile-{env}`
  - Path: `companies/{companyId}/bulk-cvs/{resumeId}.pdf`

- **Admin**: `worko-admin-cand-profile-{env}`
  - Path: `bulk-cvs/{resumeId}.pdf`

### SQS Queues
| Queue Name | Purpose | Batch Size | Delay |
|------------|---------|------------|-------|
| `worko-cand-profile-parser-queue-{env}` | Main processing queue | 25 | 15s batching window |
| `worko-cand-profile-parser-retry-queue-{env}` | Throttling retry queue | 1 | Dynamic (90s * retry_counter) |

### Firestore Collections
| Collection | Purpose |
|------------|----------|
| `bulkSourceTypeResumes` | Tracks overall upload progress and counts |
| `bulkSourceTypeParseResumes` | Stores individual parsed CV data |

### AI Models Configuration
| Model | Type | Usage |
|-------|------|-------|

| `gpt-4o` | Azure OpenAI | Primary model |
| `gpt-5.2` | Azure OpenAI | Fallback 1 |
| `gpt-4.1-mini` | Azure OpenAI | Fallback 2 |
| `gemini-2.5-flash` | Google Gemini | Final fallback  |

---

## 📊 Processing States

### CV Status Flow
```
S3 Upload → SQS Queue → Lambda Processing
                              |
                              ├─→ SUCCESS (unique) → Backend SQS → Firestore
                              ├─→ DUPLICATE → Firestore only
                              ├─→ FAILED → Firestore
                              ├─→ THROTTLED → Retry SQS (max 5 retries)
                              └─→ LARGE_RESUME_FILE → Firestore
```

### Firestore Status Values
- **SUCCESS**: CV parsed successfully and is unique
- **DUPLICATE**: CV already exists in database
- **FAILED**: Parsing failed or max retries exceeded
- **LARGE_RESUME_FILE**: CV file size exceeds processing limits

---

## 🚀 Deployment

### Automated via CodeCatalyst
- Workflow: `.codecatalyst/workflows/worko-cand-profile-parser.yaml`
- Triggers: Push to `main`, `dev`, or `cand-profile-parser-flow-improvement` branches
- Environment: Configured via `env-config.json` in repository root

### CloudFormation Resources Created
1. **Lambda Function**: `worko-cand-profile-parser-{env}`
2. **IAM Role**: `CandProfileParserRole` with permissions for S3, Bedrock, Secrets Manager, SQS, SES
3. **Lambda Layer**: `worko-cand-profile-parser-deps-{env}` (Python dependencies)
4. **Main SQS Queue**: `worko-cand-profile-parser-queue-{env}`
5. **Retry SQS Queue**: `worko-cand-profile-parser-retry-queue-{env}`
6. **SQS Event Source Mappings**: 2 triggers (main queue + retry queue)
7. **Lambda Permissions**: S3 invoke permissions for both buckets

### Manual Configuration Required
**⚠️ IMPORTANT**: After deployment, manually configure S3 event notifications:

1. **Corporate Bucket** (`worko-corporate-cand-profile-{env}`):
   - Event type: `ObjectCreated:Put`
   - Prefix: `companies/*/bulk-cvs/`
   - Destination: SQS queue `worko-cand-profile-parser-queue-{env}`

2. **Admin Bucket** (`worko-admin-cand-profile-{env}`):
   - Event type: `ObjectCreated:Put`
   - Prefix: `bulk-cvs/`
   - Destination: SQS queue `worko-cand-profile-parser-queue-{env}`

---

## 🔍 Key Features

### Parallel Processing
- Uses `ThreadPoolExecutor` with **10 workers**
- Processes up to 25 CVs simultaneously per Lambda invocation
- Each CV is processed independently

### Error Handling
- **Throttling Errors**: Automatically retried via retry SQS with exponential delay
- **Non-Throttling Errors**: Logged with `ERROR` prefix and marked as FAILED in Firestore
- **Missing Data**: CVs without key elements (name, email) are retried up to 3 times

### Validation
- Checks for key resume elements: `candidateName`, `candidateEmail`
- Retries parsing up to **3 times** if key elements are missing
- Uses `has_key_elements()` function to validate parsed JSON

### Gemini JSON Parsing
- Max output tokens: **8000** (increased from 5000 to handle large resumes)
- Truncation detection: Warns if response is truncated
- Retry logic: Re-invokes API on JSON parse failures with slightly higher temperature

---

## 📝 Metadata Structure

S3 object metadata contains:
```json
{
  "bulksourcetyperesumeid": "01KHBG70MXK0BEWBQ5AMGW3TCX",
  "company_id": "01KCGXV5WPA6C4S0PXFSMRQAQZ",
  "workoadminuseremail": "admin@worko.ai"
}
```

---

## 🔐 Secrets Manager

| Secret Name | Purpose |
|-------------|----------|
| `GCP-firestore-secret-{env}` | Firestore credentials |
| `AZURE-openai-secret-multimodel-{env}` | Azure OpenAI API keys for GPT-4, GPT-5 |

---

## 📈 Performance Metrics

- **Concurrency**: 30 Lambda instances
- **Batch Size**: 25 CVs per invocation
- **Parallel Workers**: 10 threads per invocation
- **Theoretical Throughput**: 30 × 25 = 750 CVs per batch cycle
- **Processing Time**: ~30-60 seconds per CV (depending on AI model response time)

---

## ✅ Best Practices

1. **Monitor CloudWatch Logs**: Check for ERROR prefix messages indicating failed CVs
2. **Track Firestore Counts**: Ensure counts match expected upload totals
3. **Review Retry Queue**: Monitor retry queue depth for throttling issues
4. **Validate S3 Metadata**: Ensure `bulksourcetyperesumeid` is present in all uploads
5. **Test Email Delivery**: Verify SES configuration before bulk uploads

---

## 🔄 Differences from Other Lambdas

Unlike other Lambda functions in this repository:
- **Automated SQS Creation**: Both main and retry queues are created via CloudFormation
- **Dual Event Source Mappings**: Two SQS triggers (main + retry) configured automatically
- **Manual S3 Configuration**: S3 event notifications must be configured manually (not in CloudFormation)
- **Parallel Processing**: Uses ThreadPoolExecutor for concurrent CV processing
- **Complex Retry Logic**: Multi-tier retry system with dynamic delays

---

**Happy Processing! 🚀**
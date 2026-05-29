# Shared Core Layer - Complete Implementation Summary

## 📁 Directory Structure

```
src2/shared-core-layer/
├── utils/
│   ├── __init__.py
│   ├── text_utils.py          # Text processing, JSON extraction
│   ├── score_utils.py         # Score extraction, Decimal handling
│   └── secrets_manager.py     # AWS Secrets Manager operations
├── ai_clients/
│   ├── __init__.py
│   ├── azure_openai_client.py # GPT-4o/4.1-mini with retry
│   └── bedrock_client.py      # Claude, Nova, DeepSeek, Titan
├── compatibility/
│   ├── __init__.py
│   └── ctc_experience_checker.py # CTC/experience validation
├── scoring/
│   ├── __init__.py
│   └── scoring_prompts.py     # 4-step scoring system
├── feedback/
│   ├── __init__.py
│   └── feedback_generator.py  # Recruiter/candidate feedback
├── data_adapters/
│   ├── __init__.py
│   ├── dynamodb_adapter.py    # DynamoDB operations
│   └── firestore_adapter.py   # Firestore operations
├── parsers/
│   ├── __init__.py
│   └── document_parser.py     # PDF/DOCX/image extraction
└── requirements.txt
```

## 📦 Module Overview

### 1. Utils Module
**Purpose**: Common utility functions for text processing, scoring, and secrets

**Files**:
- `text_utils.py`: clean_text(), extract_text_from_nova(), extract_json_from_response(), clean_json_response()
- `score_utils.py`: ensure_decimal(), extract_score_from_OpenAI_response(), extract_experience_level_nova()
- `secrets_manager.py`: get_secret(), get_account_id(), validate_secret_structure()

**Key Features**:
- JSON extraction with multiple fallback strategies
- Decimal conversion for DynamoDB compatibility
- AWS Secrets Manager integration
- Error handling matches source exactly

### 2. AI Clients Module
**Purpose**: Unified interface for AI model invocations

**Files**:
- `azure_openai_client.py`: AzureOpenAIClient class
- `bedrock_client.py`: BedrockClient class

**Azure OpenAI Features**:
- GPT-4o and GPT-4.1-mini support
- Exponential backoff (max 10 retries)
- Rate limiting handling (500, 502, 503, 504)
- JSON parsing with retry (max 3 attempts)
- Token usage logging
- Temperature: 0.3 (default)

**Bedrock Features**:
- Claude 3.5 Sonnet
- Amazon Nova Pro/Lite
- DeepSeek R1
- Titan Embeddings v2
- Single client for all models

### 3. Compatibility Module
**Purpose**: CTC and experience validation logic

**Files**:
- `ctc_experience_checker.py`: check_exp_ctc()

**Validation Rules**:
- ECTC = cv_ctc × 1.25
- Junior roles (≤4 years): Reject if cv_exp > jd_exp_max × 1.6
- Senior roles (>4 years): Reject if cv_exp > jd_exp_max × 1.4
- Underqualified: Reject if cv_exp < jd_exp_min × 0.7
- High CTC (>10 LPA): Reject if ECTC > jd_ctc_max × 1.2
- Low CTC (<10 LPA): Reject if ECTC > jd_ctc_max × 1.3

**Returns**: `{"ctc": False/"above", "experience": False/"above"/"below", "Explanation": "message"}`

### 4. Scoring Module
**Purpose**: 4-step JD-Resume matching scoring system

**Files**:
- `scoring_prompts.py`: get_scoring_steps(), create_prompt()

**4-Step Scoring (Max 90 points)**:
1. **Core Evaluation (27 pts)**: Experience (5), Responsibilities (10), Achievements (5), Skills (10)
2. **Mandatory Skills (40 pts)**: Section A - Skills (24), Section B - Non-skills (16)
3. **Education (9 pts)**: Tier 1 institute, certifications, degree requirements
4. **Top 15 Keywords (18 pts)**: Weighted keyword matching with section placement

**Features**:
- Experience level routing (entry/mid/senior)
- Role type routing (tech/non-tech)
- JSON output format with detailed analysis
- 20+ strict validation rules

### 5. Feedback Module
**Purpose**: Generate recruiter and candidate feedback

**Files**:
- `feedback_generator.py`: generate_feedback_prompt(), generate_email_summary_prompt(), get_reason_from_rejection_data()

**Feedback Types**:
- **High Score (≥70)**: Detailed feedback with 20 strict rules
- **Medium Score (≥40)**: Concise feedback with 10 rules
- **Email Summary**: One-line positive summary (20-25 words)
- **Rejection Reasons**: CTC/experience rejection messages

**Output Format**:
```json
{
  "feedback_Recruiter": {
    "RecruiterNote": "3-5 sentence summary",
    "Strengths": ["2-3 points"],
    "AreasOfConcern": ["2 points"]
  },
  "feedback_Candidate": {
    "CandidateNote": "3-5 sentence summary",
    "Strengths": ["2-3 points"],
    "AreasOfConcern": ["2 points"]
  }
}
```

### 6. Data Adapters Module
**Purpose**: Standardized data access layer

**Files**:
- `dynamodb_adapter.py`: DynamoDBAdapter class
- `firestore_adapter.py`: FirestoreAdapter class

**DynamoDB Operations**:
- Query: SK prefix, exact match, GSI queries
- Update: CV extract, referral response with scoring data
- Key structure: PK/SK, GSI1PK/GSI1SK

**Firestore Operations**:
- AWS Secrets Manager integration for GCP credentials
- Document retrieval from collections
- Service account authentication

### 7. Parsers Module
**Purpose**: Document text and image extraction

**Files**:
- `document_parser.py`: extract_text_from_pdf(), extract_text_from_docx(), extract_images_from_pdf()

**Features**:
- PDF text extraction (PyMuPDF)
- DOCX text extraction (python-docx)
- PDF to PNG images at 150 DPI
- Base64 encoding for images

## 🔧 Dependencies (requirements.txt)

```
# AWS SDK
boto3>=1.26.0
botocore>=1.29.0

# HTTP requests
requests>=2.28.0

# Google Cloud (for Firestore)
google-cloud-firestore>=2.11.0
google-auth>=2.16.0

# PDF processing
PyMuPDF>=1.21.0

# Document processing
python-docx>=0.8.11
```

## ✅ Verification Status

All modules verified against source code:
- ✅ Logic matches exactly
- ✅ Error handling preserved
- ✅ Print statements maintained
- ✅ Function signatures identical
- ✅ Return types consistent
- ✅ Edge cases handled

## 🎯 Usage Example

```python
# Import shared modules
from utils.text_utils import clean_text, extract_json_from_response
from utils.score_utils import ensure_decimal, extract_score_from_OpenAI_response
from utils.secrets_manager import get_secret
from ai_clients import AzureOpenAIClient, BedrockClient
from compatibility import check_exp_ctc
from scoring import get_scoring_steps, create_prompt
from feedback import generate_feedback_prompt, get_reason_from_rejection_data
from data_adapters import DynamoDBAdapter, FirestoreAdapter
from parsers import extract_text_from_pdf, extract_text_from_docx

# Initialize clients
azure_secret = get_secret("azure-openai-secret")
gpt_client = AzureOpenAIClient(azure_secret, model="gpt-4o")
bedrock_client = BedrockClient(region_name="ap-south-1")
dynamo = DynamoDBAdapter()
firestore = FirestoreAdapter("gcp-secret", "worko-db")

# Extract text from resume
resume_text = extract_text_from_pdf(pdf_bytes)
cleaned_text = clean_text(resume_text)

# Check CTC/experience compatibility
ctc_check = check_exp_ctc({
    "cv_ctc": 10.0,
    "cv_exp": 5.0,
    "jd_ctc": {"min": 8.0, "max": 12.0},
    "jd_exp": {"min": 3.0, "max": 7.0}
})

# Run 4-step scoring
steps = get_scoring_steps(experience_level="entry", role_type="tech")
for step in steps:
    prompt = create_prompt(cleaned_text, job_desc, step)
    response = gpt_client.invoke_model_with_backoff(prompt, Task="Scoring")
    score = extract_score_from_OpenAI_response(response)

# Generate feedback
feedback_prompt = generate_feedback_prompt(cleaned_text, job_desc, analysis, score=75)
feedback = gpt_client.invoke_model_with_backoff(feedback_prompt, Task="Feedback")

# Save to DynamoDB
dynamo.update_ref_response(
    table_name="worko",
    partition_key="REF#123",
    sort_key="JD#456",
    score_details=str(feedback["feedback_Recruiter"]),
    score_details_for_applicant=str(feedback["feedback_Candidate"]),
    matching_score=ensure_decimal(75),
    email_feedback="Great match!",
    rejection_feedback="",
    rejection_feedback_for_applicant=""
)
```

## 🚀 Next Steps

**Phase 9-11**: Lambda Refactoring
1. Create thin Lambda wrappers (50-70 lines)
2. Import shared-core-layer as Lambda Layer
3. Maintain independent deployments
4. Test each Lambda function
5. Update CodeCatalyst workflows

**Benefits**:
- 90% code reduction in Lambda functions
- Single source of truth for business logic
- Easy bug fixes (update layer, not 4 Lambdas)
- Consistent behavior across all Lambdas
- Simplified testing and maintenance

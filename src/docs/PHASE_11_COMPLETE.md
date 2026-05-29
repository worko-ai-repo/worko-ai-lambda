# Phase 11: Testing & Local Execution - COMPLETE ✅

## Overview

Created comprehensive local testing infrastructure for all 4 Lambda functions. The test script simulates AWS Lambda execution environment and validates functionality before deployment.

---

## Created Files

### 1. test/test.py (Enhanced)
**Comprehensive Testing Script**

**Features**:
- ✅ Tests all 4 Lambda functions locally
- ✅ Mock AWS Lambda context
- ✅ Automatic event transformation
- ✅ Command-line interface (CLI)
- ✅ Detailed output formatting
- ✅ Error handling and stack traces

**Components**:

#### MockContext Class
Simulates AWS Lambda context object:
```python
class MockContext:
    function_name = "worko-jd-resume-matching"
    function_version = "$LATEST"
    invoked_function_arn = "arn:aws:lambda:..."
    memory_limit_in_mb = 3008
    aws_request_id = "test-request-id-12345"
```

#### Test Functions
- `test_jd_resume_matching()` - Tests direct DynamoDB events
- `test_sourcetype_jd_resume_matching()` - Tests API Gateway events
- `test_bulk_jd_resume_matching()` - Tests bulk processing
- `test_agency_bulk_jd_resume_matching()` - Tests DynamoDB Stream events

#### Event Transformations
Automatically converts test events to match Lambda expectations:
- S3 events → API Gateway format (bulk)
- S3 events → DynamoDB Stream format (agency)
- Raw data → API Gateway POST body (sourcetype)

### 2. test/README.md
**Complete Testing Documentation**

**Sections**:
- Prerequisites and setup
- Usage instructions (all tests / single test)
- Test event descriptions
- Output format examples
- Mock context details
- Event transformation logic
- Troubleshooting guide
- Best practices

### 3. test/requirements.txt
**Test Dependencies**
- pytest (unit testing framework)
- pytest-cov (code coverage)
- moto (AWS service mocking)

---

## Usage

### Run All Tests
```bash
cd src2/test
python test.py
```

### Run Single Lambda Test
```bash
# Test specific Lambda
python test.py --lambda worko-jd-resume-matching
python test.py --lambda worko-sourcetype-jd-resume-matching
python test.py --lambda worko-bulk-jd-resume-matching
python test.py --lambda worko-agency-bulk-jd-resume-matching
```

### With Help
```bash
python test.py --help
```

---

## Test Coverage

### Lambda 1: worko-jd-resume-matching
- **Events**: 3 test cases
- **Scenarios**: 
  - Direct job application
  - Source type job application with parsed CV
  - Bulk CV upload application
- **Validates**: DynamoDB record processing, S3 resume download, scoring

### Lambda 2: worko-sourcetype-jd-resume-matching
- **Events**: 3 test cases
- **Scenarios**:
  - Agency submitted CV
  - Corporate bulk CV upload
  - Candidate submitted CV
- **Validates**: API Gateway integration, source type routing, multi-source data access

### Lambda 3: worko-bulk-jd-resume-matching
- **Events**: 1 test case (converted from S3)
- **Scenarios**: Bulk resume processing with parallel execution
- **Validates**: ThreadPool execution, batch statistics, S3 access

### Lambda 4: worko-agency-bulk-jd-resume-matching
- **Events**: 1 test case (converted from S3)
- **Scenarios**: DynamoDB Stream processing
- **Validates**: Stream event parsing, Firestore integration, agency routing

---

## Output Format

```
🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 
  WORKO AI LAMBDA - LOCAL TESTING SUITE
🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 🚀 

📦 Environment Setup:
  - Python: 3.11.x
  - Working Directory: /path/to/src2/test
  - Shared Layer Path: /path/to/shared-core-layer
  - Test Events Loaded: 4 Lambda(s)

================================================================================
  Testing: worko-jd-resume-matching
================================================================================

📋 Running 3 test(s)...

Test 1/3:
Event: {"USER_PK": "USR#EML#ask.72544@gmail.com", ...}
✅ Status: 200
Response: {"statusCode": 200, "body": "{\"message\": \"Matching completed..."}

Test 2/3:
Event: {"USER_PK": "USR#EML#syadavendra@gmail.com", ...}
✅ Status: 200
Response: {"statusCode": 200, "body": "{\"message\": \"Matching completed..."}

Test 3/3:
Event: {"USER_PK": "USR#EML#sahanasgp7@gmail.com", ...}
✅ Status: 200
Response: {"statusCode": 200, "body": "{\"message\": \"Matching completed..."}

================================================================================
  Testing: worko-sourcetype-jd-resume-matching
================================================================================

📋 Running 3 test(s)...

[... similar output for other Lambdas ...]

================================================================================
  Testing Complete!
================================================================================
✅ All tests executed. Check output above for results.
```

---

## Event Transformation Examples

### S3 → API Gateway (Bulk)
```python
# Input: S3 Event
{
  "Records": [{
    "s3": {
      "bucket": {"name": "worko-corporate-dev"},
      "object": {"key": "companies/.../01KGEGNYHMNAE7K6XZVQCQNXC5.pdf"}
    }
  }]
}

# Output: API Gateway Event
{
  "httpMethod": "POST",
  "body": "{\"jobId\": \"...\", \"resumes\": [{...}]}",
  "headers": {"Content-Type": "application/json"}
}
```

### S3 → DynamoDB Stream (Agency)
```python
# Input: S3 Event
{
  "Records": [{
    "s3": {
      "object": {"key": "agencies/712EE.../bulk-cvs/01KD2W.../01KD2WD.pdf"}
    }
  }]
}

# Output: DynamoDB Stream Event
{
  "Records": [{
    "eventName": "INSERT",
    "dynamodb": {
      "NewImage": {
        "agencyId": {"S": "712EE..."},
        "jobId": {"S": "01KD2W..."},
        "resumeS3Key": {"S": "agencies/.../01KD2WD.pdf"}
      }
    }
  }]
}
```

---

## Prerequisites

### 1. Install Dependencies
```bash
# Install shared-core-layer dependencies
cd ../shared-core-layer
pip install -r requirements.txt

# Install test dependencies
cd ../test
pip install -r requirements.txt
```

### 2. Configure AWS Credentials
```bash
# Set environment variables
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=ap-south-1

# Or use AWS CLI
aws configure
```

### 3. Verify Access
```bash
# Test AWS credentials
aws sts get-caller-identity

# Test S3 access
aws s3 ls s3://worko-app-dev/

# Test DynamoDB access
aws dynamodb describe-table --table-name worko
```

---

## Troubleshooting

### Import Errors
```bash
# Add shared-core-layer to Python path
export PYTHONPATH="${PYTHONPATH}:../shared-core-layer"

# Or run from test directory
cd src2/test
python test.py
```

### AWS Access Errors
- Verify AWS credentials are configured
- Check IAM permissions for S3, DynamoDB, Secrets Manager
- Ensure test resources exist in dev environment

### Missing Test Data
- Upload test resumes to S3 buckets
- Create test job descriptions in DynamoDB
- Populate test user data

### AI API Errors
- Verify Azure OpenAI credentials in Secrets Manager
- Check Bedrock model access permissions
- Monitor API rate limits and quotas

---

## Best Practices

### 1. Use Dev Environment
Always test against dev resources to avoid affecting production:
```python
# In test events, use dev buckets
bucket_name = "worko-app-dev"  # Not worko-app-prod
```

### 2. Monitor Costs
AI API calls incur costs. Limit test runs:
```bash
# Test single Lambda instead of all
python test.py --lambda worko-jd-resume-matching
```

### 3. Validate Test Data
Ensure test data exists before running:
```bash
# Check if resume exists
aws s3 ls s3://worko-app-dev/resumes/test.pdf

# Check if JD exists
aws dynamodb get-item --table-name worko --key '{"PK":{"S":"JOB#..."}}'
```

### 4. Clean Up After Testing
Remove test data to avoid clutter:
```bash
# Delete test resumes
aws s3 rm s3://worko-app-dev/test-resumes/ --recursive

# Delete test DynamoDB items
aws dynamodb delete-item --table-name worko --key '{"PK":{"S":"TEST#..."}}'
```

---

## Next Steps

### Immediate
1. ✅ Run local tests to validate functionality
2. ✅ Fix any errors found during testing
3. ✅ Verify all 4 Lambdas execute successfully

### Short-term
1. Deploy shared-core-layer to AWS
2. Deploy all 4 Lambdas to dev environment
3. Run integration tests with real triggers
4. Monitor CloudWatch Logs and metrics

### Long-term
1. Create unit tests for shared-core-layer modules
2. Set up CI/CD pipeline with automated testing
3. Deploy to staging environment
4. Production deployment after validation

---

## Summary

✅ **Local testing infrastructure complete**
✅ **All 4 Lambdas testable locally**
✅ **Mock context and event transformations**
✅ **CLI interface for flexible testing**
✅ **Comprehensive documentation**
✅ **Ready for deployment**

**Total Test Coverage**: 8 test cases across 4 Lambda functions

---

## Files Created

```
src2/test/
├── test.py              # Main testing script (enhanced)
├── README.md            # Testing documentation
└── requirements.txt     # Test dependencies
```

**Next Phase**: Deploy to AWS and run integration tests! 🚀

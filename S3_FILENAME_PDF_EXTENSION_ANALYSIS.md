# S3 File Name .pdf Extension Analysis Report

## 🔍 Overview
This document analyzes where S3 file names are being used **WITH** and **WITHOUT** the `.pdf` extension across all Lambda functions in the repository.

---

## 📊 Summary

| Lambda Function | Files with .pdf | Files without .pdf | Risk Level |
|----------------|-----------------|-------------------|------------|
| worko-agency-bulk-jd-resume-matching | 1 | 1 | ⚠️ MEDIUM |
| worko-bulk-jd-resume-matching | 0 | 0 | ✅ LOW |
| worko-resume-parser | 4 | 0 | ✅ LOW |
| worko-cand-profile-parser | 2 | 0 | ✅ LOW |
| worko-job-description-parser | 0 | 0 | ✅ N/A |
| worko-referral-source-cand-profile-parser | 1 | 0 | ✅ LOW |
| worko-sourcetype-jd-resume-matching | 1 | 0 | ✅ LOW |

---

## 1️⃣ worko-agency-bulk-jd-resume-matching

### 📁 File: `lambda_function.py`

#### ✅ WITH .pdf Extension

**Line ~1100-1105** - S3 Event Processing:
```python
# Extract IDs from S3 path: agencies/{agencyUserId}/bulk-cvs/{agencyBulkJdId}/{filename}
path_parts = object_key.split('/')
agency_user_id = path_parts[1]
agency_bulk_jd_id = path_parts[3]
filename = path_parts[4]  # ← This includes .pdf extension from S3 event
```
**Status**: ✅ Filename includes `.pdf` from S3 event key
update_doc_id  = Filename.replace(".","")
update_doc_id is used to update data in firstore
---



---

## 2️⃣ worko-bulk-jd-resume-matching

### 📁 File: `lambda_function.py`

#### Analysis:
- **No direct S3 filename manipulation found**
- Uses DynamoDB keys and internal processing
- File reading happens via S3 client with full key path
- **Risk**: ✅ LOW - No extension-related issues detected

**Key Pattern**:
```python
# File is read with full S3 key including extension
response = s3_client.get_object(Bucket=s3_bucket_name, Key=object_key)
```

---

## 3️⃣ worko-resume-parser

### 📁 File: `lambda_function.py`

#### ✅ WITH .pdf Extension (Multiple Locations)

**Location 1 - Line ~250** - Agency User Path:
```python
key = f"agencies/{agencyUserId}/companies/{companyId}/jobs/{jobId}/user-profiles/{candidateParsedCvAwsS3FileName}"
# candidateParsedCvAwsS3FileName includes .pdf
```

**Location 2 - Line ~235** - Candidate Submit CV Path:
```python
key = f"candidate-submit-cvs/companies/{companyId}/jobs/{jobId}/cvs/{candidateParsedCvAwsS3FileName}"
# candidateParsedCvAwsS3FileName includes .pdf
```

**Location 3 - Line ~180** - Source Type Refresh CV:
```python
FileName = event.get("candidateParsedCvAwsS3FileName")
key = f"{cvAwsS3FilePath}/{FileName}"
# FileName includes .pdf
```

**Location 4 - Line ~350** - User Resume Path:
```python
key = "users/" + resumeId + "/resumes/" + cvId
# cvId includes .pdf extension
```

**Status**: ✅ All S3 operations use full filename with `.pdf` extension

---

## 4️⃣ worko-cand-profile-parser

### 📁 File: `lambda_function.py`

#### ✅ WITH .pdf Extension (Multiple Locations)

**Location 1 - Line ~1050** - S3 Event Processing:
```python
bucket_name = s3_event['bucket']['name']
object_key = unquote_plus(s3_event['object']['key'])
file_name = object_key.split("/")[-1]  # ← Includes .pdf from S3 key
print(" file_name,", file_name)
```
**Status**: ✅ Filename includes `.pdf` from S3 event

**Location 2 - Line ~1100** - SQS Message Body:
```python
file_name = body.get("object_key","").split("/")[-1]
# file_name includes .pdf extension
```
**Status**: ✅ Filename maintains `.pdf` extension

**Analysis**: 
- All S3 operations use full paths with `.pdf`
- SQS messages preserve the extension
- Firestore updates use the filename WITH extension
- **Risk**: ✅ LOW - Consistent extension handling

---

## 5️⃣ worko-job-description-parser

### 📁 File: `lambda_function.py`

#### Analysis:
- **No S3 file operations found**
- This Lambda processes job descriptions from event payload
- No file reading/writing operations
- **Risk**: ✅ N/A - Not applicable

---

## 6️⃣ worko-sourcetype-jd-resume-matching

### 📁 File: `lambda_function.py`

#### ✅ WITH .pdf Extension

**Location 1 - Line ~1050** - S3 File Reading:
```python
# Extract from event payload
cvAwsS3FilePath= event.get("cvAwsS3FilePath")
cvAwsS3FileName= event.get("cvAwsS3FileName")

# Construct S3 key with full filename including .pdf
key = cvAwsS3FilePath + '/' + cvAwsS3FileName
s3_client = boto3.client('s3')
response = s3_client.get_object(Bucket=s3_bucket_name, Key=key)
```
**Status**: ✅ Filename includes `.pdf` extension from event payload

**Analysis**:
- Receives filename from event payload with `.pdf` extension
- Uses full filename for S3 operations
- No extension manipulation or removal
- Firestore updates use document IDs from event (not filename-based)
- **Risk**: ✅ LOW - Consistent extension handling

---

## 7️⃣ worko-referral-source-cand-profile-parser

### 📁 File: `lambda_function.py`

#### ✅ WITH .pdf Extension

**Location 1 - Line ~200** - S3 Upload:
```python
file_id = sort_key = str(uuid.uuid4())
cv_bucket = os.environ.get("CV_UPLOAD_BUCKET", "worko-corporate-referral-source-cv-dev")
s3_key = f"companies/{company_id}/referral-source-cvs/{file_id}.pdf"  # ← .pdf added
s3_client.put_object(Bucket=cv_bucket, Key=s3_key, Body=pdf_bytes, ContentType='application/pdf')
```
**Status**: ✅ Explicitly adds `.pdf` extension

**Location 2 - Line ~210** - SQS Message:
```python
sqs_send_data = {
    "event": "CORPORATE_CAND_PROFILE_REFERRAL_SOURCE",
    "companyId": company_id,
    "candidateCvAwsS3FileName": f"{file_id}.pdf",  # ← .pdf included
    "cvExtractedParsed": cvExtractedParsed
}
```
**Status**: ✅ Filename sent WITH `.pdf` extension

**Analysis**:
- Generates new UUID for filename
- Explicitly adds `.pdf` extension when creating S3 key
- SQS messages include the extension
- **Risk**: ✅ LOW - Consistent extension handling

---

## 🎯 Complete Analysis Summary

### ✅ Safe Lambdas (No Issues)
1. **worko-bulk-jd-resume-matching**: No filename manipulation
2. **worko-resume-parser**: All operations use full filename with `.pdf`
3. **worko-cand-profile-parser**: Consistent extension handling
4. **worko-job-description-parser**: No file operations
5. **worko-referral-source-cand-profile-parser**: Explicitly adds `.pdf` to generated filenames
6. **worko-sourcetype-jd-resume-matching**: Uses full filename with `.pdf` from event payload

### ⚠️ Needs Review
1. **worko-agency-bulk-jd-resume-matching**: Removes `.pdf` for Firestore document IDs (Line ~1200)

---

## 🔧 Recommendations

### 1. Standardize Naming Convention
**Decision Required**: Should document/record IDs include file extensions?

**Option A - Without Extension (Current in agency-bulk)**:
```python
# Pros: Cleaner IDs, database-friendly
# Cons: Need to add extension when constructing S3 paths
doc_id = filename.replace('.pdf', '')
```

**Option B - With Extension**:
```python
# Pros: Direct mapping to S3 files
# Cons: Extension in database IDs
doc_id = filename  # Keep .pdf
```

### 2. Add Validation
```python
def ensure_pdf_extension(filename: str) -> str:
    """Ensure filename has .pdf extension"""
    if not filename.endswith('.pdf'):
        return f"{filename}.pdf"
    return filename

def remove_pdf_extension(filename: str) -> str:
    """Remove .pdf extension if present"""
    return filename.replace('.pdf', '')
```

### 3. Document the Pattern
Create a clear rule:
- **S3 Operations**: ALWAYS use full filename with `.pdf`
- **Database IDs**: ALWAYS remove `.pdf` (or keep it - be consistent)
- **API Responses**: Document which format is returned

---

## 📝 Code Patterns Summary

### Pattern 1: S3 File Reading (✅ Correct)
```python
# All functions follow this pattern correctly
response = s3_client.get_object(Bucket=bucket, Key=full_path_with_pdf)
```

### Pattern 2: Document ID Creation (⚠️ Inconsistent)
```python
# worko-agency-bulk-jd-resume-matching
update_doc_id = filename.replace('.pdf', '')  # Removes extension

# Other functions
# May or may not remove extension - needs verification
```

### Pattern 3: Path Construction (✅ Mostly Correct)
```python
# Most functions maintain the extension in paths
key = f"path/to/{filename}"  # filename includes .pdf
```

---

## 🚨 Production Bug Context

**Reported Issue**: "Sending S3 file name without .pdf extension"

**Analysis**:
- The bug likely occurred in **worko-agency-bulk-jd-resume-matching**
- When updating Firestore, the extension is removed: `filename.replace('.pdf', '')`
- If downstream services expect the filename WITH extension, this causes failures

**Affected Code**:
```python
# Line ~1200 in worko-agency-bulk-jd-resume-matching/lambda_function.py
update_doc_id = filename.replace('.pdf', '')
DBManager.update_firestore_document_with_scoring_data(
    update_collection_name, 
    update_doc_id,  # ← This is WITHOUT .pdf
    cv_extracted_parsed,
    processingStatus
)
```

---

## ✅ Action Items

1. **Verify Firestore Schema**: Check if `agencyBulkJdResumes` collection expects document IDs with or without `.pdf`
2. **Check Downstream Services**: Verify what format other services expect when reading from Firestore
3. **Add Tests**: Create tests to ensure filename format consistency
4. **Update Documentation**: Document the expected format in each service
5. **Consider Migration**: If format needs to change, plan data migration for existing records

---

## 📌 Notes

- **S3 Operations**: All are safe - they use full paths with extensions
- **Database Operations**: Need consistency check
- **API Contracts**: Need to verify expected formats between services
- **Error Handling**: Add validation to catch extension mismatches early

---

**Generated**: 2025-02-14  
**Reviewed By**: Code Analysis Tool  
**Status**: Ready for Review

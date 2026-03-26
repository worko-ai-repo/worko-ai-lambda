# Worko Resume Parser - Lambda Function Flows

## Overview
This Lambda function handles resume parsing for three distinct flows in the Worko platform.

---

## Flow 1: External Link Submission (Admin/Recruiter)
**Trigger**: Admin or recruiter clicks on share external link

**Event Type**: `CAND_SUBMIT_CV_JOB`

**Process**:
1. Candidate submits CV through external link
2. Lambda downloads CV from S3
3. CV is parsed and extracted
4. Parsed data is returned

---

## Flow 2: Agency CV Upload
**Trigger**: Agency uploads CV

**Process**:
1. Agency uploads candidate CV
2. Lambda downloads CV from S3
3. CV is parsed and extracted
4. Parsed data is stored

---

## Flow 3: User Signup/CV Update
**Trigger**: User signs up or updates their CV

**Process**:
1. User uploads CV during signup or profile update
2. Lambda downloads CV from S3
3. CV is parsed and extracted
4. User profile is updated with parsed data

---
## Flow 4: User SOURCE_TYPE_REFRESH_CV

```json
{
   "event": "SOURCE_TYPE_REFRESH_CV"
   "candidateParsedCvAwsS3FileName":"UJFGVBGVGHVFGGHCJVNB.pdf",
   "cvAwsS3FilePath": "....",
   "cvAwsS3ResourceType": "CORP_CAND_BULK_CV_UPLOAD",
   "cvAwsS3BucketName": "worko-corporate-cand-profile-dev",
   "cvAwsS3FilePath": "companies/01JWAQF1G96E0SE9XHXSFGHNWW/bulk-cvs"
}

## Common Processing
All flows:
- Download CV from S3
- Extract text and structured data
- Parse resume information
- Return/store parsed results
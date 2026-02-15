# # gpt-4.1-mini confugrations
# from importlib import metadata
# import requests
# import json
# from typing import Tuple, Dict, Any, Optional, Union
# import boto3
# import time
# import json
# from typing import Callable, Any
from lambda_function import *
# from google.cloud import firestore
# import uuid
from datetime import date, datetime, timezone
env=os.environ.get("ENVIRONMENT", "dev")
azure_openai_secret_name = "AZURE-openai-secret-multimodel-"+env
azure_openai_secret = get_secret(azure_openai_secret_name)
# azure_openai_secret["AZURE_OPENAI_DEPLOYMENT_gpt-4.1-mini"] #=azure_openai_secret["ZURE_OPENAI_DEPLOYMENT_gpt-4.1-mini"]
gpt4 = AzureOpenAIClient(azure_openai_secret,model="gpt-4o")
gpt4_1_mini = AzureOpenAIClient(azure_openai_secret,model="gpt-4.1-mini")
print("azure_openai_secret",azure_openai_secret,len(azure_openai_secret))
with open(r"logs/secrect-dev", 'w') as f:
    json.dump(azure_openai_secret, f, indent=4)

# Get today's date in ISO format (YYYY-MM-DD)
# today_iso = date.today()
# print(f"ISO Date: {today_iso}") 
# def send_ses_email(to_address, subject, body_text):
#     ses = boto3.client('ses', region_name='ap-south-1')
#     source = os.environ.get("SES_SOURCE_EMAIL", "no-reply@worko.ai")
#     print("msg gone")
#     return ses.send_email(
#         Source=source,
#         Destination={"ToAddresses": [to_address]},
#         Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body_text}}}
#     )
# to_address = "shaukat.shaikh@worko.ai"
# send_ses_email(to_address, "hii", "This is a test email.")


# def check_duplicate_with_cv_age(cvExtractedParsed, object_key, DBManager):
#     from datetime import datetime, timedelta
    
#     email = cvExtractedParsed.get("candidateEmail", "")
#     phone_number = cvExtractedParsed.get("candidateNumber", "")
#     country_code = cvExtractedParsed.get("candidatePhoneCountryCode", "")
    
#     is_corporate = "companies" in object_key
#     collection = "corporateCandidateProfiles" if is_corporate else "centralCandidateProfiles"
#     company_id = object_key.split("/")[1] if is_corporate else None
#     resource_type = "CORP_CAND_BULK_CV_UPLOAD" if is_corporate else "ADMIN_CAND_BULK_CV_UPLOAD"
    
#     candidate_profiles = DBManager.get_candidate_profiles(collection, company_id, email, phone_number, country_code)
    
#     if not candidate_profiles:
#         return None, None
    
#     candidate_profile = candidate_profiles[0]
#     parsed_cv_id = candidate_profile.get("candidateParsedCvId" if is_corporate else "latestCandidateParsedCvId")
    
#     if not parsed_cv_id:
#         return None, None
    
#     parsed_cv_doc = DBManager.get_document_firstore("candidateParsedCvs", parsed_cv_id)
    
#     if not parsed_cv_doc:
#         return None, None
    
#     cv_tracker = parsed_cv_doc.get("cvAwsS3FileTracker", [])
#     matching_cv = next((cv for cv in cv_tracker if cv.get("resourceType") == resource_type), None)
    
#     if not matching_cv:
#         return None, None
    
#     action_date_str = matching_cv.get("actionDate")
#     if not action_date_str:
#         return None, None
    
#     action_date = datetime.fromisoformat(action_date_str.replace("+00:00", ""))
#     three_months_ago = datetime.now() - timedelta(days=90)
    
#     if action_date >= three_months_ago:
#         return "DUPLICATE", None
#     else:
#         event_name = "OLDER_CV_CORPORATE_CAND_PROFILE_BULK_UPLOAD" if is_corporate else "OLDER_CV_ADMIN_CAND_PROFILE_BULK_UPLOAD"
#         return "OLDER_CV", event_name

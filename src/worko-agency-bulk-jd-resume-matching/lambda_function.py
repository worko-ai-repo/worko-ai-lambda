import boto3
import fitz
import requests
import random
import os
# from dotenv import load_dotenv
# load_dotenv()
import time
import json
from decimal import Decimal
from typing import List, Tuple, Dict, Any, Optional, Union
from boto3.dynamodb.conditions import Key, Attr
import re
from botocore.exceptions import ClientError
from urllib.parse import unquote_plus
# iac deploy 11
dynamodb = boto3.resource('dynamodb')
from google.cloud import firestore
from google.oauth2 import service_account
from datetime import datetime, timezone

def extract_text_from_pdf(pdf_data):
    text = ""
    pdf_document = fitz.open(stream=pdf_data, filetype="pdf")
    for page in pdf_document:
        text += page.get_text()
    return text


class FirestoreManager:
    def __init__(self,GCP_secret_name,GCP_DATABASE_NAME):
        self.GCP_secret_name = GCP_secret_name
        self.GCP_DATABASE_NAME = GCP_DATABASE_NAME
        self.db = self._initialize_firestore()

    def get_secret(self,secret_name):
        secrets_client = boto3.client('secretsmanager', region_name='ap-south-1')

        try:
            response = secrets_client.get_secret_value(SecretId=secret_name)
            secret_value = response['SecretString']
            
            # Try to parse as JSON, fallback to string
            try:
                secret_data = json.loads(secret_value)
            except json.JSONDecodeError:
                secret_data = secret_value
            return secret_data
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return {
                    "statusCode": 404,
                    "body": json.dumps({"error": f"Secret '{secret_name}' not found"})
                }



    def _initialize_firestore(self):
        creds_dict = self.get_secret(self.GCP_secret_name)
        FIRESTORE_PROJECT_ID =creds_dict.get("project_id")

        # GCP_DATABASE_NAME ="worko-corp-db-" +self.env 

        
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        db = firestore.Client(project=FIRESTORE_PROJECT_ID, credentials=credentials, database=self.GCP_DATABASE_NAME)
        print(f"Firestore initialized successfully for project: {FIRESTORE_PROJECT_ID}, database: {self.GCP_DATABASE_NAME}")
        return db

    def update_firestore_document_with_scoring_data(self,collection_name: str, doc_id: str,update_data,status):
        current_datetime = datetime.now()
        # Convert it to an ISO 8601 formatted string
        iso_string = current_datetime.isoformat()


        try:
            if update_data :

                doc_ref = self.db.collection(collection_name).document(doc_id)
                doc_ref.update(update_data)
                print(f"Updated Firestore document {doc_id} isFindMatchingScoreInProgress: False and update_data : {update_data}")
                return True

            else:
                doc_ref = self.db.collection(collection_name).document(doc_id)
                doc_ref.update({

                    "status":InterruptedError

                })
                print(f"Updated Firestore document {doc_id} with  isFindMatchingScoreInProgress :True ")
                return True

        except Exception as e:
            print(f"Error updating Firestore document {doc_id}: {e}")
            return False

    def get_document_firstore(self,collection_name,doc_id):
        doc_ref = self.db.collection(collection_name).document(doc_id)
        return doc_ref.get().to_dict()

def lambda_handler(event, context):
    print(f"got a event : -  {event}")             
    try:
        # Parse S3 event
        s3_event = event['Records'][0]['s3']
        bucket_name = s3_event['bucket']['name']
        object_key = unquote_plus(s3_event['object']['key'])
        
        print(f"Processing S3 object: {bucket_name}/{object_key}")
        
        # Extract IDs from S3 path: agencies/{agencyUserId}/bulk-cvs/{agencyBulkJdId}/{filename}
        path_parts = object_key.split('/')
        if len(path_parts) < 5:
            raise ValueError(f"Invalid S3 path structure: {object_key}")
            
        agency_user_id = path_parts[1]
        agency_bulk_jd_id = path_parts[3]
        filename = path_parts[4]
        
        # Get environment
        env = os.environ.get("ENVIRONMENT", "dev")
        
        # Download PDF from S3
        s3_client = boto3.client('s3')
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
            pdf_data = response['Body'].read()
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                print(f"S3 object not found: {bucket_name}/{object_key}")
                # Try with original encoded key
                original_key = s3_event['object']['key']
                print(f"Trying original key: {bucket_name}/{original_key}")
                response = s3_client.get_object(Bucket=bucket_name, Key=original_key)
                pdf_data = response['Body'].read()
            else:
                raise
        
        # Extract text from PDF
        resume_text = extract_text_from_pdf(pdf_data)
        
        print(f"Successfully processed resume: {resume_text[:50]}..")
        env = "dev"
        GCP_secret_name = "GCP-firestore-secret-"+env
        GCP_DATABASE_NAME = "worko-corp-db-" +env 
        
        DBManager = FirestoreManager(GCP_secret_name,GCP_DATABASE_NAME)



        update_data = {
            "updatedAt": datetime.now().isoformat(),
            "cvExtractedParsed": {
                "candidateName": "",
                "candidateEmail": "",
                "candidatePhoneNumber": "",
                "candidateNumber": 0,
                "candidatePhoneCountryCode": 0,
                "candidateCurrentCompany": "",
                "candidateCurrentDesignation": "",
                "candidateExperience": 0,
                "candidateTotalYOE": 0,
                "candidateRelevantYOE": 0,
                "candidateCurrentCTC": 0,
                "candidateExpectedCTC": 0,
                "candidateNoticePeriod": 0,
                "candidateLocation": "",
                "candidateReadyToRelocate": False,
                "isNoticePeriodNegotiable": False,
                "coreSkills": [],
                "technicalSkills": [],
                "userPreferredDepartments": [],
                "userPreferredIndustries": [],
                "userPreferredlocations": [],
                "userPreferredRoles": []
            },
            "cvExtract": resume_text,
            "matchingScore": 0,
            "jdMatchErrorCode": 200,
            "jdMatchErrorDesc": "",
            "scoreDetails": "",
            "scoreFetchedDate": datetime.now().isoformat(),
            "rejectionFeedbackBySystem": ""
        }
        # Get the Jobdescription from firstore
        
        get_collection_name ="agencyBulkJds"
        job_description = DBManager.get_document_firstore(get_collection_name, agency_bulk_jd_id)
        #exclud agencyRegisteredEmail,companyId,id for cv-jd matching
        print(f"job_description fetched from firestore: {str(job_description)[:100]}...")
        jobTitle = job_description.get("jobTitle","")
        experienceRange = job_description.get("experienceRange","")
        technicalSkills = job_description.get("technicalSkills","")
        jobLocation = job_description.get("jobLocation","")
        softSkills = job_description.get("softSkills","")
        coreSkills = job_description.get("coreSkills","")
        industryPreferences = job_description.get("industryPreferences","")
        jobDescription = job_description.get("jobDescription","")
        mustHaveSkills = job_description.get("mustHaveSkills","")
        mustNotHaveSkills = job_description.get("mustNotHaveSkills","")

      
    
        # update data in firestore
        # doc_id = filename.replace('.pdf', '')
        # isFindMatchingScoreInProgress = False
        # update_collection_name = "agencyBulkJdResumes"
        # DBManager.update_firestore_document_with_scoring_data(update_collection_name, doc_id, update_data, isFindMatchingScoreInProgress)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Resume read successfully",
                "job_description": job_description,
                "resume_text": resume_text
            })
        }
        
    except Exception as e:
        print(f"Error processing resume: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e)
            })
        }
    
# if __name__ == "__main__":
#     event = {
#         "Records": [
#             {
#             "eventVersion": "2.1",
#             "eventSource": "aws:s3",
#             "awsRegion": "ap-south-1",
#             "eventTime": "2024-01-15T10:30:00.000Z",
#             "eventName": "s3:ObjectCreated:Put",
#             "s3": {
#                 "s3SchemaVersion": "1.0",
#                 "configurationId": "lambda-trigger",
#                 "bucket": {
#                 "name": "worko-app-dev",
#                 "arn": "arn:aws:s3:::worko-app-dev"
#                 },
#                 "object": {
#                 "key": "agencies/712EEWMW5HE3NE9K8DGRXXTR53/bulk-cvs/01KD2W640HJS9PZNJMHNH6YE6K/sarvesh.pdf",
#                 "size": 245760,
#                 "eTag": "d41d8cd98f00b204e9800998ecf8427e"
#                 }
#             }
#             }
#         ]

#     }
#     lambda_handler(event,None)
    

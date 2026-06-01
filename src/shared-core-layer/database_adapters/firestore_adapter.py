"""Firestore adapter for data operations."""

import json
import boto3
from botocore.exceptions import ClientError
from google.cloud import firestore
from google.oauth2 import service_account
from typing import Dict, Any, Optional
from datetime import datetime


     
class FirestoreManagerAgency:
    def __init__(self,GCP_secret,GCP_DATABASE_NAME):
        self.GCP_secret = GCP_secret
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
        # creds_dict = self.get_secret(self.GCP_secret_name)
        creds_dict = self.GCP_secret
        FIRESTORE_PROJECT_ID =creds_dict.get("project_id")

        # GCP_DATABASE_NAME ="worko-corp-db-" +self.env 

        
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        db = firestore.Client(project=FIRESTORE_PROJECT_ID, credentials=credentials, database=self.GCP_DATABASE_NAME)
        print(f"Firestore initialized successfully for project: {FIRESTORE_PROJECT_ID}, database: {self.GCP_DATABASE_NAME}")
        return db

    def update_firestore_document_with_scoring_data(self,collection_name: str, doc_id: str,update_data,status:str ):

        if update_data and status == "COMPLETED":
            try:
                doc_ref = self.db.collection(collection_name).document(doc_id)
                doc_ref.update(update_data)
                print(f"Updated Firestore document {doc_id} status : completed and update_data : {update_data}")
                return True
            except Exception as e:
                print("failed to updated 2ed step (score details) data in collection_name :-- ",collection_name,"doc_id :--",doc_id,"error is", e)
                return False


        else:
            try:
                doc_ref = self.db.collection(collection_name).document(doc_id)
                doc_ref.update({
                    "matchingScore" : 0,
                    "cvExtractedParsed":update_data,
                    "processingStatus":status

                })
                print(f"Updated Firestore document {doc_id} with  status :IN PROGRESS")
            except Exception as e:
                print("failed to updated 1st step (cvExtractparsed) data in collection_name :-- ",collection_name,"doc_id :--",doc_id,"error is", e)
                return False

    def get_document_firstore(self,collection_name,doc_id):
        doc_ref = self.db.collection(collection_name).document(doc_id)
        return doc_ref.get().to_dict()
  
class FirestoreManagerSourcetype:
    def __init__(self,GCP_secret_creds,GCP_DATABASE_NAME):
        self.GCP_secret_creds = GCP_secret_creds
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
        creds_dict = self.GCP_secret_creds
        FIRESTORE_PROJECT_ID =creds_dict.get("project_id")

        # GCP_DATABASE_NAME ="worko-corp-db-" +self.env 

        
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        db = firestore.Client(project=FIRESTORE_PROJECT_ID, credentials=credentials, database=self.GCP_DATABASE_NAME)
        print(f"Firestore initialized successfully for project: {FIRESTORE_PROJECT_ID}, database: {self.GCP_DATABASE_NAME}")
        return db

    def update_firestore_document_with_scoring_data(self,collection_name: str, doc_id: str,update_data,isFindMatchingScoreInProgress,jobMatched):
        current_datetime = datetime.now()
        # Convert it to an ISO 8601 formatted string
        iso_string = current_datetime.isoformat()


        try:
            if update_data :
                updatedByUserId = update_data.get("updatedByUserId","")
                updatedByCorporateUserId = update_data.get("updatedByCorporateUserId","")
                matchingScoreDetails = update_data.get("matchingScoreDetails","")

                if jobMatched:
                    doc_ref = self.db.collection(collection_name).document(doc_id)
                    doc_ref.update(update_data)
                    print(f"Updated Firestore document {doc_id} isFindMatchingScoreInProgress: False and update_data : {update_data}")
                    return True

                
                elif updatedByCorporateUserId: #if you receive actionByCorporateUserId in payload then  updatedByCorporateUserId 
                    doc_ref = self.db.collection(collection_name).document(doc_id)
                    doc_ref.update({
                        "matchingScoreDetails" : matchingScoreDetails,
                        "updatedAt": iso_string,
                        "updatedByCorporateUserId":updatedByCorporateUserId,
                        "isFindMatchingScoreInProgress":isFindMatchingScoreInProgress

                    })
                    print(f"Updated Firestore document {doc_id} isFindMatchingScoreInProgress: False and update_data : {matchingScoreDetails}")
                    return True

                elif updatedByUserId: #if you receive actionByUserId in payload then  updatedByUserId 
                    doc_ref = self.db.collection(collection_name).document(doc_id)
                    doc_ref.update({
                        # store as ISO string

                        "matchingScoreDetails" : matchingScoreDetails,
                        "updatedAt": iso_string,
                        "updatedByUserId":updatedByUserId,
                        "isFindMatchingScoreInProgress":isFindMatchingScoreInProgress

                    })
                    print(f"Updated Firestore document {doc_id} isFindMatchingScoreInProgress: False and update_data {matchingScoreDetails}")
                    return True

            else:
                doc_ref = self.db.collection(collection_name).document(doc_id)
                doc_ref.update({

                    "isFindMatchingScoreInProgress":True

                })
                print(f"Updated Firestore document {doc_id} with  isFindMatchingScoreInProgress :True ")
                return True

        except Exception as e:
            print(f"Error updating Firestore document {doc_id}: {e}")
            return False

    def get_document_firstore(self,collection_name,doc_id):
        doc_ref = self.db.collection(collection_name).document(doc_id)
        return doc_ref.get().to_dict()


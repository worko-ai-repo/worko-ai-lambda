import json
import boto3
import os
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1 import Or, And
import uuid

sqs = boto3.client('sqs')

class FirestoreManager:
    def __init__(self, GCP_secret_name, GCP_DATABASE_NAME):
        self.db = self._initialize_firestore(GCP_secret_name, GCP_DATABASE_NAME)
    
    def _initialize_firestore(self, secret_name, db_name):
        secrets_client = boto3.client('secretsmanager', region_name='ap-south-1')
        response = secrets_client.get_secret_value(SecretId=secret_name)
        creds_dict = json.loads(response['SecretString'])
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        return firestore.Client(project=creds_dict.get("project_id"), credentials=credentials, database=db_name)
    
    def get_candidate_profiles(self, collection, company_id, email, phone_number, country_code):
        or_filter = Or([FieldFilter("candidateEmail", "==", email), And([FieldFilter("phoneNumberDetails.number", "==", phone_number), FieldFilter("phoneNumberDetails.countryCode", "==", country_code)])])
        if company_id:
            query = self.db.collection(collection).where(filter=FieldFilter("companyId", "==", company_id)).where(filter=or_filter)
        else:
            query = self.db.collection(collection).where(filter=or_filter)
        docs = query.get()
        return [doc.to_dict() for doc in docs] if docs else None
    
    def update_firestore_document_data(self, collection_name, doc_id, update_data, status):
        self.db.collection(collection_name).document(doc_id).set(update_data)
    
    def increment_counter(self, collection_name, doc_id, field_name):
        self.db.collection(collection_name).document(doc_id).update({field_name: firestore.Increment(1)})

def get_queue_url(queue_name):
    response = sqs.get_queue_url(QueueName=queue_name)
    return response['QueueUrl']

def send_to_sqs(queue_name, body, delay_seconds=0):
    queue_url = get_queue_url(queue_name)
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(body), DelaySeconds=delay_seconds)

def send_final_sqs(body):
    env = os.environ.get("ENVIRONMENT", "dev")
    region = "ap-south-1"
    eventQueueName = "worko-corp-app-event-queue"
    account_id = boto3.client('sts').get_caller_identity()['Account']
    sqs_url = f"https://sqs.{region}.amazonaws.com/{account_id}/{eventQueueName}"
    sqs.send_message(QueueUrl=sqs_url, MessageBody=json.dumps(body))

def check_duplicate(cvExtractedParsed, object_key, DBManager):
    email = cvExtractedParsed.get("candidateEmail", "")
    phone_number = cvExtractedParsed.get("candidatePhoneNumber", "")
    country_code = cvExtractedParsed.get("candidateCountryCode", "")
    if "companies" in object_key:
        collection = "corporateCandidateProfiles"
        company_id = object_key.split("/")[1]
    else:
        collection = "centralCandidateProfiles"
        company_id = None
    return DBManager.get_candidate_profiles(collection, company_id, email, phone_number, country_code)

def lambda_handler(event, context):
    print(f"Step 3: Check duplicates and send to DB")
    env = os.environ.get("ENVIRONMENT", "dev")
    retry_queue = f"state-machine-retry-{env}"
    
    try:
        body = json.loads(event['Records'][0]['body'])
        cvExtractedParsed = body['cvExtractedParsed']
        bucket_name = body['bucket_name']
        object_key = body['object_key']
        metadata = body.get('metadata', {})
        retry_counter = body.get('retry_counter', 0)
        file_name = object_key.split("/")[-1]
        bulksourcetyperesumeid = metadata.get("bulksourcetyperesumeid", "")
        
        if retry_counter >= 5:
            return {'statusCode': 200, 'body': 'Max retries'}
        
        GCP_DATABASE_NAME = f"worko-corp-db-{env}"
        GCP_secret_name = f"GCP-firestore-secret-{env}"
        DBManager = FirestoreManager(GCP_secret_name, GCP_DATABASE_NAME)
        
        duplicate_data = check_duplicate(cvExtractedParsed, object_key, DBManager)
        
        if duplicate_data is None:
            company_id = object_key.split("/")[1] if "companies" in object_key else ""
            sqs_send_data = {"companyId": company_id, "candidateCvAwsS3FileName": file_name, "cvExtractedParsed": cvExtractedParsed}
            send_final_sqs(sqs_send_data)
            status = "SUCCESS"
            cand_data = {"candidateName": cvExtractedParsed.get("candidateName", ""), "candidateEmail": cvExtractedParsed.get("candidateEmail", ""), "status": status, "createdAt": datetime.now().isoformat()}
            doc_id = str(uuid.uuid4())
            cand_data["id"] = doc_id
            cand_data["bulkSourceTypeResumeId"] = bulksourcetyperesumeid
            DBManager.update_firestore_document_data("bulkSourceTypeParseResumes", doc_id, cand_data, status)
            DBManager.increment_counter("bulkSourceTypeResumes", bulksourcetyperesumeid, "totalResumesSucceeded")
        else:
            status = "DUPLICATE"
            cand_data = {"candidateName": cvExtractedParsed.get("candidateName", ""), "candidateEmail": cvExtractedParsed.get("candidateEmail", ""), "status": status, "createdAt": datetime.now().isoformat()}
            doc_id = str(uuid.uuid4())
            cand_data["id"] = doc_id
            cand_data["bulkSourceTypeResumeId"] = bulksourcetyperesumeid
            DBManager.update_firestore_document_data("bulkSourceTypeParseResumes", doc_id, cand_data, status)
            DBManager.increment_counter("bulkSourceTypeResumes", bulksourcetyperesumeid, "totalResumesDuplicate")
        
        return {'statusCode': 200, 'body': 'Step 3 completed'}
        
    except Exception as e:
        print(f"Error in Step 3: {e}")
        retry_counter += 1
        send_to_sqs(retry_queue, {'cvExtractedParsed': cvExtractedParsed, 'bucket_name': bucket_name, 'object_key': object_key, 'metadata': metadata, 'retry_counter': retry_counter, 'step': 3}, delay_seconds=90*retry_counter)
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}

import json
import ast
import boto3
import re
import os
from datetime import datetime
from decimal import Decimal
import time
from docx import Document
import fitz
from io import BytesIO
from urllib.parse import unquote_plus
from botocore.exceptions import ClientError
import requests
from google.cloud import firestore
from google.oauth2 import service_account
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1 import Or, And

start_time = time.time()
# Initialize Bedrock clients
region = 'ap-south-1'
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client(service_name='bedrock', region_name = region)
bedrock_runtime = boto3.client(service_name='bedrock-runtime', region_name = region)
sqs = boto3.client('sqs')


def update_sqs_queue(message_body):

    region =  "ap-south-1"   # add in env variable later
    eventQueueName = "worko-corp-app-event-queue" # add in env variable later
    account_id = "211125353899" # add in env variable later

    message_body ={}

    sqs_url = "https://sqs.ap-south-1.amazonaws.com/{account_id}/{eventQueueName}"
    print("event updating in sqs :-",message_body)

    
    message_body_msg = json.dumps(message_body)
    
    response = sqs.send_message(
        QueueUrl=sqs_url,
        MessageBody=message_body_msg
        )
    
    return {
        'statusCode': 200,
        'body': json.dumps('Message sent to SQS!')
    }

def clean_text(text):
  
    # Step 1: Remove asterisks
    text = text.replace('*', '')

    # Step 2.1: Remove hash symbols (#)
    text = text.replace('#', '')
    
    # Step 2: Remove hyphens that are used as bullet points (surrounded by spaces)
    text = re.sub(r'\s-\s', ' ', text)
    
    # Step 3: Keep hyphens in dates, ranges, and compound words
    # This pattern looks for hyphens between numbers or letters without spaces
    
    # Step 4: Remove multiple spaces and replace with a single space
    text = re.sub(r'\s+', ' ', text)
    
    # Step 5: Remove leading/trailing spaces from each line
    lines = text.split('\n')
    cleaned_lines = [line.strip() for line in lines]
    
    # Step 6: Rejoin lines and remove empty lines
    result = '\n'.join(line for line in cleaned_lines if line)
    
    return result

def extract_images_from_pdf(pdf_bytes):
    print('called extract_images_from_pdf')
   

    images_base64 = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    print('doc opened')

    for page in doc:
        print('started loop')
        pix = page.get_pixmap(dpi=150)
        image_bytes = pix.tobytes("png")
        img_str = base64.b64encode(image_bytes).decode("utf-8")
        images_base64.append(img_str)
    print('images_base64 len',len(images_base64))
    return images_base64

def invoke_claude_with_image(base64_images):                
    print('called invoke_claude_with_image')
    messages = [
        {
            "role": "user",
            "content": []
        }
    ]

    # Add images
    for image_str in base64_images:
        messages[0]["content"].append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": image_str
            }
        })
    # Add resume parsing instructions
    messages[0]["content"].append({
        "type": "text",
        "text": ('Carefully analyze the entire resume shown in the image. Extract all visible information and present it in plain text format, organized topic-wise never miss name and year of experience.\n\n'
            'Name:\nEmail:\nExperience in year:\nAchievements:\nTechnical skills:'
            '\nSoft skills:\nCore skills:\nEducation:\nIndustry experience:\nResponsibilities:'
            '\nAchievements against responsibility:\nCertifications:\nStrength:\n'
            'Experience type (leadership, Mid management, Senior management, Team lead, Individual contributor):'
            '\nTeam handling experience:\nIndustry type(B2B, D2C, C2C, B2C):\n\nAssistant:\" turn'



                
        )
    })

    body = {
        "messages": messages,
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096
    }
    print('model version from prompt body',body['anthropic_version'])
    body = json.dumps(body)
    

    # Send request to Bedrock (Claude)
    response = bedrock_runtime.invoke_model(
        body=body,
        modelId="anthropic.claude-3-haiku-20240307-v1:0",
        # modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        # modelId="anthropic.claude-sonnet-4-20250514-v1:0",
        contentType="application/json",
        accept="application/json"
    )
    print('Result:',response)
    response_body = json.loads(response["body"].read())
    
    return response_body.get("content", [{}])[0].get("text", "")

def extract_text_from_docx(docx_bytes):
    text = ""
    document = Document(BytesIO(docx_bytes))
    for paragraph in document.paragraphs:
        text += paragraph.text + "\n"
    return text

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

    # Example usage for your specific case:
    def get_candidate_profiles(self, collection,company_id, email, phone_number, country_code):
        """
        Get corporate candidate profiles matching company and contact info
        """
        
        # Build the OR filter
        or_filter = Or([
            FieldFilter("candidateEmail", "==", email),
            And([
                FieldFilter("phoneNumberDetails.number", "==", phone_number),
                FieldFilter("phoneNumberDetails.countryCode", "==", country_code)
            ])
        ])
        
        # Query with company filter and OR condition
        if company_id:
            print("query first type of path")
            query = self.db.collection(collection) \
                .where(filter=FieldFilter("companyId", "==", company_id)) \
                .where(filter=or_filter)
        else:
            print("query second type of path")
            query = self.db.collection(collection) \
                .where(filter=or_filter)
        
        docs = query.get()
        if docs:
            return [doc.to_dict() for doc in docs]
        else:
            return "None"


def lambda_handler(event, context):
    # example_path1="s3://worko-corporate-cand-profile-dev/companies/01JWAQF1G96E0SE9XHXSFGHNWW/bulk-cvs/01KD2WDTS7RZKEJ6QFK87MDC0K.pdf"
    # example_path1={'Records': [{'eventVersion': '2.1', 'eventSource': 'aws:s3', 
    #                             'awsRegion': 'ap-south-1', 'eventTime': '2026-01-12T06:21:54.363Z', 
    #                             'eventName': 'ObjectCreated:Put', 
    #                             'userIdentity': {'principalId': 'AWS:AROATCKANHWVTQO36WAQQ:shaukat.shaikh@worko.ai'}, 
    #                             'requestParameters': {'sourceIPAddress': '103.176.210.144'},
    #                              'responseElements': {'x-amz-request-id': 'JQK4A937CPMH8C66', 'x-amz-id-2': 'M51w2m0Fm4VamXUJKKJtOB3jRLYkZgdCRWN7ZCcRyhf6ywE8xNuNBbJDdF+bHnjyJWtVGE2LdUVopT0E9hQhAynzmAuNsEavskmFz9JGg34='}, 
    #                              's3': {'s3SchemaVersion': '1.0', 'configurationId': '2391fd04-1e04-41f3-9a68-3c5d8a728a02', 
    #                             'bucket': {'name': 'worko-corporate-cand-profile-dev', 
    #                                         'ownerIdentity': {'principalId': 'A1V0APDMR493SG'}, 
    #                                         'arn': 'arn:aws:s3:::worko-corporate-cand-profile-dev'}, 
    #                                         'object': {
    #                                             'key': 'companies/01JWAQF1G96E0SE9XHXSFGHNWW/bulk-cvs/shaukat_cv.pdf', 'size': 391471, 'eTag': '94a1271ecae22b95ce462c9ec4e40c5a', 'sequencer': '006964930250E7F22D'
    #                                             }
    #                                         }}]}
    # example_path2= "s3://worko-admin-cand-profile-dev/bulk-cvs/01KEH892ZACXJVV996SPKP0948.pdf"
    print("got event:",event)
    env = os.getenv('ENVIRONMENT', 'dev')
    GCP_DATABASE_NAME = "worko-corp-db-dev"
    GCP_secret_name = "GCP-firestore-secret-"+env
    DBManager = FirestoreManager(GCP_secret_name,GCP_DATABASE_NAME)
    s3_client = boto3.client('s3')
    s3_event = event['Records'][0]['s3']
    bucket_name = s3_event['bucket']['name']
    object_key = unquote_plus(s3_event['object']['key'])

    response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
    data = response['Body'].read()

    

    
    # Extract text from the PDF or DOCX file
    if object_key.lower().endswith('.pdf'):
        processed_text = extract_text_from_pdf(data)
        processed_text = clean_text(processed_text)
        print("Fetched_cv_text",processed_text)
        if not processed_text:
            print('Image Based Resume Processing..')    ######
            base64_images = extract_images_from_pdf(data)
            processed_text = invoke_claude_with_image(base64_images)   
            print('image Based cv process completed')  
        
    elif object_key.lower().endswith('.docx'):
        processed_text = extract_text_from_docx(data)
        processed_text = clean_text(processed_text)
        print("Fetched_cv_text",processed_text)
    else:
        print(f"Unsupported file format: {object_key}")
    



    if "companies" in object_key: #example_path1:
    # query data and check it present or not
        collection = "corporateCandidateProfiles"
        company_id = object_key.split("/")[1]
        email = ""
        phone_number =""
        country_code = ""
        data = DBManager.get_candidate_profiles( collection,company_id, email, phone_number, country_code)
        print("Data.......",data)
        if not data:
            # update_sqs_queue(cvExtractedParsed)
            print("trigring sqs as  do not find any dublicate record in collection corporateCandidateProfiles")
            #trigre sqs
    else:

        
        collection = "centralCandidateProfiles"
        company_id = None
        email = ""
        phone_number =""
        country_code = ""
        data = DBManager.get_candidate_profiles( collection,company_id, email, phone_number, country_code)
        if not data:
            #triger sqs
            print("trigring sqs as  do not find any dublicate record in collectoin centralCandidateProfiles")
            # update_sqs_queue(cvExtractedParsed)





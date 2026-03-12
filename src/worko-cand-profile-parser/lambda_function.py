import json
import ast
import boto3
import re
import os
import base64
from datetime import datetime
from decimal import Decimal
import time
from docx import Document
import fitz
from io import BytesIO
from urllib.parse import unquote_plus
from botocore.exceptions import ClientError
import requests
import random
from typing import Tuple, Dict, Any, Optional, Union
from google.cloud import firestore
from google.oauth2 import service_account
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1 import Or, And
import uuid
from urllib.parse import unquote_plus
# second deployment11
start_time = time.time()
# Initialize Bedrock clients
region = 'ap-south-1'
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client(service_name='bedrock', region_name = region)
bedrock_runtime = boto3.client(service_name='bedrock-runtime', region_name = region)
sqs = boto3.client('sqs')

def get_account_id():
    # Create STS client
    sts_client = boto3.client('sts')

    # Call get-caller-identity
    response = sts_client.get_caller_identity()

    # Extract account ID
    return response['Account']

def send_final_sqs_for_cvExtractparsed(body):
    file_name = body.get("candidateCvAwsS3FileName","")
    cvExtractedParsed = body.get("cvExtractedParsed","")

    if not body.get("companyId",""):
        message_body = {"event":"ADMIN_CAND_PROFILE_BULK_UPLOAD",
                    "candidateCvAwsS3FileName":file_name,
                    "cvExtractedParsed":cvExtractedParsed
                }
    else:
        message_body = {"event": "CORPORATE_CAND_PROFILE_BULK_UPLOAD",
            "companyId": body.get("companyId"),
            "candidateCvAwsS3FileName":file_name,
            "cvExtractedParsed":cvExtractedParsed}
        
    try:
        region = os.environ.get("SQS_REGION", "ap-south-1")
        eventQueueName = os.environ.get("EVENT_QUEUE_NAME", "worko-corp-app-event-queue")
        account_id = get_account_id()

        sqs_url = f"https://sqs.{region}.amazonaws.com/{account_id}/{eventQueueName}"
        print("event updating in sqs :-",message_body)

        
        message_body_msg = json.dumps(message_body)
        
        response = sqs.send_message(
            QueueUrl=sqs_url,
            MessageBody=message_body_msg
            )
        print("Dublicate is not found, sqs (parsed cv) sent to backend")
        return {
            'statusCode': 200,
            'body': json.dumps('Message sent to SQS!')
        }
    except Exception as e:
        print("Error sending message to SQS:", e)
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error sending message to SQS : - {e}')
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
        "text": ('Carefully analyze the entire resume shown in the image. Extract all visible information and present it in plain text format, organized topic-wise never miss name, email, mobile number and year of experience as this will be prsent alwasy in the data.\n\n'
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

class AzureOpenAIClient:
    """Client for Azure OpenAI API with retry logic."""
    
    DEFAULT_TEMPERATURE = 0.3
    DEFAULT_API_VERSION = "2024-05-01-preview"
    # REQUEST_TIMEOUT = 20  # seconds
    
    def __init__(self, azure_openai_secret: Dict[str, str],model="gpt-4o"):
        
        """Initialize Azure OpenAI client.
        
        Args:
            azure_openai_secret: Dict containing:
                - AZURE_OPENAI_ENDPOINT
                - deployment_name
                - api_key
                - AZURE_OPENAI_API_VERSION (optional)
        """
        self.model = model
        if not isinstance(azure_openai_secret, dict):
            raise TypeError("azure_openai_secret must be a dictionary")
        
        self.endpoint = azure_openai_secret.get("AZURE_OPENAI_ENDPOINT", "")
        self.api_key = azure_openai_secret.get("AZURE_OPENAI_API_KEY", "")
        if model=="gpt-4o":
            self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT_gpt-4o", "")
            self.api_version = azure_openai_secret.get(
                "AZURE_OPENAI_API_VERSION_gpt-4o", 
                self.DEFAULT_API_VERSION
            )
        elif model=="gpt-4.1-mini":
            self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT_gpt-4.1-mini", "")
            self.api_version = azure_openai_secret.get(
                "AZURE_OPENAI_API_VERSION_gpt-4.1-mini", 
                self.DEFAULT_API_VERSION
            )

        
        
        # Validate required fields
        if not all([self.endpoint, self.deployment_name, self.api_key]):
            raise ValueError(
                "Missing required Azure OpenAI configuration: "
                "AZURE_OPENAI_ENDPOINT, deployment_name, and api_key are required"
            )
    
    def invoke_model_with_backoff(
        self,
        prompt: str,
        Task="Not specified",
        system_content: str = "You are a helpful assistant.",
        max_retries: int = 10,
        base_delay: int = 2,
        want_json: bool = True
    ) -> Union[str, Dict[Any, Any]]:
        """Invoke model with exponential backoff for rate limiting.
        
        Args:
            prompt: User prompt
            system_content: System message for the model
            max_retries: Maximum number of retry attempts
            base_delay: Base delay for exponential backoff
            want_json: Whether to parse response as JSON
            
        Returns:
            Model response as string or parsed JSON dict
        """
        print("using model :-", self.model)
        for attempt in range(max_retries):
            print("Task to Ai is :- ",Task)
            try:
                return self.invoke_model(system_content, prompt, want_json)
            
            except requests.exceptions.HTTPError as e:
                # Check for rate limiting (429) or server errors (5xx)
                if e.response.status_code in [500, 502, 503, 504]:
                    if attempt < max_retries - 1:
                        delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                        print(
                            f"Rate limit or server error (status {e.response.status_code}). "
                            f"Retrying in {delay:.2f} seconds..."
                        )
                        time.sleep(delay)
                    else:
                        raise
                else:
                    # Don't retry for other HTTP errors (auth, not found, etc.)
                    raise
            
            except requests.exceptions.RequestException as e:
                # Network errors - retry
                if attempt < max_retries - 1:
                    delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                    print(f"Network error: {e}. Retrying in {delay:.2f} seconds...")
                    time.sleep(delay)
                else:
                    raise
    
    def invoke_model(
        self,
        system_content: str,
        prompt: str,
        want_json: bool = True,
        max_json_retries: int = 3,
        temperature: float = DEFAULT_TEMPERATURE
    ) -> Union[str, Dict[Any, Any]]:
        """Invoke Azure OpenAI model.
        
        Args:
            system_content: System message
            prompt: User prompt
            want_json: Whether to parse response as JSON
            max_json_retries: Max retries for JSON parsing
            temperature: Model temperature
            
        Returns:
            Model response as string or parsed JSON dict
        """
        url = (
            f"{self.endpoint}/openai/deployments/{self.deployment_name}/"
            f"chat/completions?api-version={self.api_version}"
        )
        
        headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key
        }
        
        data = {
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature
        }
        
        if not want_json:
            response = requests.post(
                url=url, 
                headers=headers, 
                json=data
                
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        
        # JSON mode with retries
        for attempt in range(max_json_retries):
            try:
                response = requests.post(
                    url=url, 
                    headers=headers, 
                    json=data
                    
                )
                response.raise_for_status()
                result = response.json()
                try :
                    tokens = result["usage"]
                    output_tokens= tokens["completion_tokens"]
                    input_tokens= tokens["prompt_tokens"]
                    total = tokens["total_tokens"]
                    print(" Token usage details input_tokens :-",input_tokens,"output_tokens",output_tokens,"total",total)

                except Exception as e :
                    print("errore occured input output token not found :--",e)
                
                # Extract and clean content
                content = result["choices"][0]["message"]["content"]
                content = content.strip()
                
                # Remove markdown code blocks
                if content.startswith("```"):
                    content = content.removeprefix("```json").removeprefix("```")
                    content = content.removesuffix("```").strip()
                
                return json.loads(content)
            
            except json.JSONDecodeError as e:
                remaining = max_json_retries - attempt - 1
                print(f"JSON parse failed. Retries left: {remaining}")
                print(f"Error: {e}")
                
                if remaining == 0:
                    print(f"Raw content: {content}")
                    raise ValueError(f"Failed to parse JSON after {max_json_retries} attempts") from e
                
                time.sleep(2)  # Brief delay before retry
            
            except (KeyError, IndexError) as e:
                print(f"Unexpected response structure: {result}")
                raise ValueError("Invalid response format from Azure OpenAI") from e
       
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
                print(f"Secret '{secret_name}' not found")
                raise Exception(f"Secret '{secret_name}' not found")
            raise

    def _initialize_firestore(self):
        creds_dict = self.get_secret(self.GCP_secret_name)
        FIRESTORE_PROJECT_ID =creds_dict.get("project_id")

        # GCP_DATABASE_NAME ="worko-corp-db-" +self.env 

        
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        db = firestore.Client(project=FIRESTORE_PROJECT_ID, credentials=credentials, database=self.GCP_DATABASE_NAME)
        print(f"Firestore initialized successfully for project: {FIRESTORE_PROJECT_ID}, database: {self.GCP_DATABASE_NAME}")
        return db

    def update_firestore_document_with_scoring_data(self,collection_name_for_firstore_updating: str, doc_id: str,update_data,status:str ):

        if status:
            try:
                print(f"updating data in firsstore with id {doc_id}")
                doc_ref = self.db.collection(collection_name_for_firstore_updating).document(doc_id)
                doc_ref.update(update_data)
                print(f"Updated Firestore document {doc_id} status : completed and update_data : {update_data}")
                return True
            except Exception as e:
                print("failed to updated 2ed step (score details) data in collection_name_for_firstore_updating :-- ",collection_name_for_firstore_updating,"doc_id :--",doc_id,"error is", e)
                return False


        else:
            try:
                doc_ref = self.db.collection(collection_name_for_firstore_updating).document(doc_id)
                doc_ref.update({
                    "matchingScore" : 0,
                    "cvExtractedParsed":update_data,
                    "processingStatus":status

                })
                print(f"Updated Firestore document {doc_id} with  status :IN PROGRESS")
            except Exception as e:
                print("failed to updated 1st step (cvExtractparsed) data in collection_name_for_firstore_updating :-- ",collection_name_for_firstore_updating,"doc_id :--",doc_id,"error is", e)
                return False

    def get_document_firstore(self,collection_name_for_firstore_updating,doc_id):
        doc_ref = self.db.collection(collection_name_for_firstore_updating).document(doc_id)
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
            print("query corporate type of path")
            query = self.db.collection(collection) \
                .where(filter=FieldFilter("companyId", "==", company_id)) \
                .where(filter=or_filter)
        else:
            print("query admin type of path")
            query = self.db.collection(collection) \
                .where(filter=or_filter)
        
        docs = query.get()
        if docs:
            return [doc.to_dict() for doc in docs]
        else:
            return None

    def update_firestore_document_data(self, collection_name, doc_id, update_data, status):
        doc_ref = self.db.collection(collection_name).document(doc_id)
        doc_ref.set(update_data)
        print(f"Created document {doc_id} in {collection_name} with status {status}")

    def get_documents_by_bulkSourceTypeResumeId(self, collection_name, bulkSourceTypeResumeId):
        docs = self.db.collection(collection_name).where(filter=FieldFilter("bulkSourceTypeResumeId", "==", bulkSourceTypeResumeId)).get()
        return [doc.to_dict() for doc in docs]
    
    def get_documents_by_bulkSourceTypeResumeId_and_status(self, collection_name, bulkSourceTypeResumeId, status):
        docs = self.db.collection(collection_name) \
            .where(filter=FieldFilter("bulkSourceTypeResumeId", "==", bulkSourceTypeResumeId)) \
            .where(filter=FieldFilter("status", "==", status)) \
            .get()
        return [doc.to_dict() for doc in docs]

def process_parsed_cv_json(cv_obj):
    try:
        if not isinstance(cv_obj, dict):
            return cv_obj
        
        # Process education array separately
        education = cv_obj.get("education", [])
        if isinstance(education, list):
            education = [
                {k: v for k, v in item.items() if v not in (None, "", [], {}, "null", "NULL")}
                for item in education
                if isinstance(item, dict)
            ]
        
        # Remove null/empty values from top level
        cv_obj = {k: v for k, v in cv_obj.items() if v not in (None, "", [], {}, "null", "NULL")}
        
        # Add back cleaned education if it has items
        if education:
            cv_obj["education"] = education
        
        try:
            cv_obj["candidateName"] = cv_obj["candidateName"].lower()
            cv_obj["candidateEmail"] = cv_obj["candidateEmail"].lower()
            cv_obj["candidateLocation"] = cv_obj["candidateLocation"].lower()
        except Exception as e:
            print("Error: - failed to lowercase name and email or Location of cv parsed results")
        
        return cv_obj
    except Exception as e:
        print(f"Error processing parsed CV JSON: {e}")
        return cv_obj

def invoke_model_OpenAI(system_content, prompt, want_json=True, max_try_for_json=5):
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")     
    deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")

    if not all([endpoint, deployment_name, api_version, api_key]):
        raise ValueError("Missing Azure OpenAI configuration in environment variables")

    url = f"{endpoint}/openai/deployments/{deployment_name}/chat/completions?api-version={api_version}"

    headers = {
        "Content-Type": "application/json",
        "api-key": api_key
    }

    data = {
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }

    if not want_json:
        response = requests.post(url=url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]

    else:
        for attempt in range(max_try_for_json):
            try:
                response = requests.post(url=url, headers=headers, json=data)
                response.raise_for_status()
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                content = content.strip().removeprefix("```json").removesuffix("```").strip()
                return json.loads(content)

            except json.JSONDecodeError as e:
                remaining = max_try_for_json - attempt - 1
                print(f"JSON parse failed. Retries left: {remaining}")
                print("Error:", e)
                time.sleep(2)
                if remaining == 0:
                    raise

def invoke_model_with_backoff_OpenAI(prompt,Task="Not Specifield" ,max_retries=10, want_json=True, base_delay=2):
    print({"Task to ai":Task})
    system_content = "You are a helpful assistant."
    
    for attempt in range(max_retries):

        return invoke_model_OpenAI(system_content, prompt,want_json)

def get_secret(secret_name):
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

def process_cv(metadata,retry_queue_name, processed_text, gpt_models, bucket_name,object_key,retry_counter) -> Tuple[str, Dict[str, str]]:
    retry_counter +=1
    print("Processing cv for cvexractparesed with retry_counter:", retry_counter)
    try:
        processed_text = " ".join(processed_text.split())

        """
        Process CV text and extract structured information.
        
        Args:
            processed_text: Raw text from CV
            
        Returns:
            Tuple containing:
            - Extracted CV text in template format
            - Parsed CV information as structured JSON
        """

        if not processed_text:
            return "Unfortunately, we are not able to read your resume", processed_text

        

            
        # Second extraction for parsed details
        parsed_prompt = (
            f"You are an expert HR specialized in resume analysis and extracting structured data.\n\n"

            f"Resume text:\n{processed_text}\n\n"

            f"*** RULE: If you don't find any data in the resume ***\n"
            f"- If the value is a number → use 0\n"
            f"- If the value is a boolean → use false\n"
            f"- If the value is a string → use an empty string \"\"\n"
            f"- If the candidate is a fresher or not currently working → set candidateCurrentCompany = \"\"\n\n"

            f"*** Mandatory data to find in the resume ***\n"
            f"These fields MUST always be present in the output:\n"
            f"1. candidateName\n"
            f"2. candidateCurrentDesignation\n"
            f"3. candidateCurrentCompany\n"
            f"4. candidateTotalYOE\n"
            f"5. candidateLocation\n\n"

            f"*** Last Check ***\n"
            f"- All numbers must be integers.\n"
            f"- Ensure ALL mandatory fields are present.\n"
            f"- Output must be valid JSON only.\n"
            f"- candidateExperience must be a numeric value (int or decimal like 6, 6.5, 10.2).\n"
            f"- candidatePhoneNumber must be in format: +91XXXXXXXXXX (no spaces).\n\n"
            f"- if Phone number is give the you must fill all three variables"
            f"1. candidatePhoneNumber: number with country code (string), 2. candidateNumber:  number only without country code (int), 3. candidatePhoneCountryCode (int),4.candidateNoticePeriod int or Null"
            f"Rule to return null values:\n"
            f" if any str key is not given in in resume text just return Null for that partcular fild "
            f" example :candidateNoticePeriod,candidateLocation"
            f"candidateLocation must be only city name followed by state name examples. Mumbai, Maharahstra,  Bengaluru Karnataka"
            f"*** Output Format (JSON only) ***\n"
            f"{{{{\n"
            f"  \"candidateName\": \"\",\n"
            f"  \"about\":\"extract about me or summary or profile or objective from resume\",\n"
            f"  \"education\": [\n"
            f"    {{\n"
            f"      \"collage\": \"[INSTITUTION_NAME or COLLEGE_NAME]\",\n"
            f"      \"degree\": \"[DEGREE_NAME]\",\n"
            f"      \"startedYear\": \"[STARTED_YEAR]\",\n"
            f"      \"passingYear\": \"[GRADUATION_YEAR]\"\n"
            f"    }}\n"
            f"  ],\n"
            f"  \"multipleCandidateExperience\": [\n"
            f"    {{\n"
            f"      \"companyName\": \"[COMPANY_NAME]\",\n"
            f"      \"designation\": \"[JOB_TITLE]\",\n"
            f"      \"department\": \"[DEPARTMENT]\",\n"
            f"      \"YOE\": 0,\n"
            f"      \"startDate\": \"[START_DATE]\",\n"
            f"      \"endDate\": \"[END_DATE or empty string if ongoing]\"\n"
            f"    }}\n"
            f"  ],\n"
            f"  \"candidateEmail\": \"\",\n"
            f"  \"candidatePhoneNumber\": \"\",\n"
            f"  \"candidateNumber\": 0,\n"
            f"  \"candidatePhoneCountryCode\": 0,\n"
            f"  \"candidateCurrentCompany\": \"\",\n"
            f"  \"candidateCurrentDesignation\": \"\",\n"
            f"  \"candidateExperience\": 0,\n"
            f"  \"candidateTotalYOE\": 0,\n"
            f"  \"candidateRelevantYOE\": 0,\n"
            f"  \"candidateNoticePeriod\": \"\",\n"
            f"  \"candidateLocation\": \"\",\n"
            f"  \"candidateReadyToRelocate\": false,\n"
            f"  \"isNoticePeriodNegotiable\": false\n"
            f"}}}}\n"
        )
        cv_extracted_parsed = gpt_models[1].invoke_model_with_backoff(parsed_prompt,Task= "get cvExtractparsed step1 ")
        # cv_extracted_parsed = OpenAIClient.invoke_model_with_backoff(parsed_prompt,Task= "get cvExtractparsed step1 " )
        current_timestamp = datetime.now().isoformat()
        prompt = (
            f"**Extract the following details from the resume extract:**\n"
            f"- Core Skills (max 30 chars each)\n"
            f"- Soft Skills (max 30 chars each)\n"
            f"- Preferred departments (0–5, based on experience & skills)\n"
            f"- Years of Experience (YOE)\n\n"

            f"**Instructions**:\n"
            f"- Use ONLY information explicitly written in the resume.\n"
            f"- Extract ONLY the top 20 Core Skills and top 10 Soft Skills.\n"
            f"- **Core Skills (TECH)** = high-level domains only (System Architecture, Microservices Design).\n"
            f"- **Technical Skills** = tools, languages, frameworks, cloud, DBs, certifications.\n"
            f"- **Core Skills (NON-TECH)** = business/functional domains only.\n"
            f"- **Technical Skills (NON-TECH)** = tools/platforms (Excel, SQL, Salesforce, SAP).\n"
            f"- Soft Skills = interpersonal traits (Communication, Leadership, Problem Solving).\n"
            f"- Add YOE for Core Skills if mentioned, else 0.\n"
            f"- Calculate total YOE from roles or dates.\n\n"

            f"**Mandatory Rules**:\n"
            f"- ALWAYS Soft Skills (never Core): Managing Escalations, Team Mentoring, Leadership, Strategic Planning,\n"
            f"  Stakeholder Management, Goal Setting, Problem Solving, Quick Learner, Data-driven decision-making.\n"
            f"- Core Skills must NOT include:\n"
            f"  • Job titles (Project Manager)\n"
            f"  • Action phrases (Managing Escalations, Driving Initiatives)\n"
            f"  • Interpersonal traits (Leadership, Mentoring)\n"
            f"  • Tools/software (Excel, SAP, Salesforce)\n"
            f"- Use timestamp for createdAt & updatedAt: {current_timestamp}\n\n"

            f"**STRICT Example**:\n"
            f"coreSkills: AWS or Cloud, Web App Design, Sales, Marketing\n"
            f"softSkills: Escalation handling, Strategy & Execution, Team mentoring, Presentation skills,\n"
            f"            Budget Management, Problem Solving, Quick Learner, Time management\n"
            f"technicalSkills: CRM tools\n\n"

            f"**STRICT RULES**:\n"
            f"- If more than 20 skills exist, pick the 20 most relevant.\n"
            f"- Do NOT invent skills.\n"
            f"- A skill MUST appear only once across all categories.\n"
            f"- Never include responsibilities/duties as skills.\n"
            f"- Skills must be concise names.\n"
            f"- For NON-TECH profiles: Core = domain/business expertise only.\n"
            f"- Terms with verbs like Managing/Handling/Driving/Mentoring → Soft Skill.\n\n"

            f"Resume extract:\n\n{processed_text}\n\n"

            f"Return JSON only:\n"
            f"{{{{\n"
            f"  \"coreSkills\": [\n"
            f"    {{{{\"skillName\": \"[CORE_SKILL_NAME]\", \"years\": [YEARS_OF_EXPERIENCE]}}}}\n"
            f"  ],\n"
            f"  \"technicalSkills\": [\n"
            f"    {{{{\"skillName\": \"[TECHNICAL_SKILL_NAME]\", \"years\": [YEARS_OF_EXPERIENCE]}}}}\n"
            f"  ],\n"
            f"  \"softSkills\": [\n"
            f"    {{{{\"skillName\": \"[SOFT_SKILL_NAME]\"}}}}\n"
            f"  ],\n"
            f"  \"userPreferredDepartments\": [\n"
            f"    \"List the department names based on resume designations and core skills\"\n"
            f"  ],\n"
            f"  \"userPreferredIndustries\": [\n"
            f"    \"Extract up to 3 industries such as Information Technology, Banking, Healthcare\"\n"
            f"  ],\n"
            f"  \"userPreferredlocations\": [\n"
            f"    \"Extract if mentioned; else return empty list\"\n"
            f"  ],\n"
            f"  \"userPreferredRoles\": [\n"
            f"    \"Extract roles/designations from resume\"\n"
            f"  ]\n"
            f"}}}}\n"
        )
        cv_extracted_parsed2 = gpt_models[0].invoke_model_with_backoff(prompt,Task = "get cvExtractparsed step2")
        # cv_extracted_parsed2 = OpenAIClient.invoke_model_with_backoff(prompt,Task = "get cvExtractparsed step2")
        merged = {**cv_extracted_parsed, **cv_extracted_parsed2}
        merged = process_parsed_cv_json(merged)
        return merged
        

    except Exception as execution_error:
        error_message = str(execution_error).lower()
        # error_traceback = traceback.format_exc()# Check if this is a throttling error
        if any(term in error_message for term in ['throttling', 'throttled', 'rate limit', 'too many requests', '429']):
            print("Errore of {execution_error} now sending sqs for startuing again in next 60 seconds")
            delay_seconds = 90*retry_counter
            body = {"bucket_name": bucket_name,"object_key": object_key,"from":"SQS throttling error","retry_counter":retry_counter ,"metadata":metadata}
            send_sqs_for_throttling_error(retry_queue_name,body,delay_seconds) #send sqs for throttled error
            return None 
        else:
            # For all other errors, just log and continue
            print(f"Error processing CV: {execution_error}")
            return None 

def get_queue_url(queue_name):
    sqs = boto3.client('sqs')
    response = sqs.get_queue_url(QueueName=queue_name)
    return response['QueueUrl']

def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

def send_sqs_for_throttling_error(retry_queue_name,body,delay_seconds):
    try:
        retry_counter = body.get("retry_counter", "retry_counter not found")
        from datetime import datetime, timedelta
        queue_url = get_queue_url(retry_queue_name)
        sqs = boto3.client('sqs')
        
        # body = {"processed_text": processed_text,"object_key": object_key,"from":"throttling error"}
      
        
        print(f"Sending message to SQS with retry_counter: {retry_counter}")
        print(f"[SQS SEND] DelaySeconds: {delay_seconds}")
        print(f"SQS message body for throttled steps: {json.dumps(str(body)[:100])}")
        
        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(body, default=decimal_default),
            DelaySeconds=delay_seconds
        )
        
        print(f"[SQS SEND] MessageId: {response.get('MessageId', 'N/A')}")
        
        
    except Exception as sqs_error:
        print(f"Error sending send_sqs_for_throttling_error step to SQS: {sqs_error}")
        print(f"Queue URL attempted: {queue_url}")
        print(f"Message body: {body}")

def check_firstore_dubliacy(cvExtractedParsed, object_key, DBManager):
    email = cvExtractedParsed.get("candidateEmail","")
    phone_number = cvExtractedParsed.get("candidatePhoneNumber","") 
    country_code = cvExtractedParsed.get("candidateCountryCode","")
    if "companies" in object_key: 
        # query data and check it present or not
        collection = "corporateCandidateProfiles"
        company_id = object_key.split("/")[1]
        
        data_got_from_firstore_data = DBManager.get_candidate_profiles( collection,company_id, email, phone_number, country_code)
        
        if data_got_from_firstore_data is not None:
            print("Dublicate data from firstore..",data_got_from_firstore_data)
            return data_got_from_firstore_data
    
    else:

        collection = "centralCandidateProfiles"
        company_id = None
        data_got_from_firstore_data = DBManager.get_candidate_profiles( collection,company_id, email, phone_number, country_code)
        
        if data_got_from_firstore_data is not None:
            print("Dublicate data from firstore..",data_got_from_firstore_data)
            return data_got_from_firstore_data


# def send_final_cv_sqs(cvExtractedParsed,file_name,object_key,DBManager):
#     email = cvExtractedParsed.get("candidateEmail","")
#     phone_number = cvExtractedParsed.get("candidatePhoneNumber","") 
#     country_code = cvExtractedParsed.get("candidateCountryCode","")

#     if "companies" in object_key: #example_path1:
#         company_id = object_key.split("/")[1]
#         # query data and check it present or not
#         collection = "corporateCandidateProfiles"
        
        
#         dat_got_from_firstore_data = DBManager.get_candidate_profiles( collection,company_id, email, phone_number, country_code)
#         print("Data.......",dat_got_from_firstore_data)

#         if dat_got_from_firstore_data is not None:
#             print(f"Not trigring sqs as found dublicate record in collection corporateCandidateProfiles : - {dat_got_from_firstore_data}")
#         else:
#             sqs_send_data = {"event": "CORPORATE_CAND_PROFILE_BULK_UPLOAD",
#             "companyId": company_id,
#             "candidateCvAwsS3FileName":file_name,
#             "cvExtractedParsed":cvExtractedParsed}
#             send_final_sqs_for_cvExtractparsed(sqs_send_data)

#             print(f"trigring sqs, as found no dublicate record in collection corporateCandidateProfiles :- {cvExtractedParsed}")
#             #trigre sqs
#     else:

#         collection = "centralCandidateProfiles"
#         company_id = None
#         data = DBManager.get_candidate_profiles( collection,company_id, email, phone_number, country_code)
        
#         if data is not None:
#             print(f"Not trigring sqs as found dublicate record in collection centralCandidateProfiles : - {data}")

#         else:
#             #triger sqs
#             print(f"trigring sqs as  do not found any dublicate record in collectoin centralCandidateProfiles {cvExtractedParsed}")
#             # sqs_send_data = {"event":"ADMIN_CAND_PROFILE_BULK_UPLOAD",
#             #     "candidateCvAwsS3FileName":file_name,
#             #     "cvExtractedParsed":cvExtractedParsed
#             # }
#             send_final_sqs_for_cvExtractparsed(sqs_send_data)


def updated_firstore_resume_status(processingStatus,bulkSourceTypeResumeId,update_data,DBManager):
    """this function will update firestore document if a resume is processed successfully with cvExtractedParsed data and also update status of that resume in firestore document"""
    print("updating firestore document with cvExtractedParsed data and status of that resume in firestore document")
    
    doc_id = str(uuid.uuid4())
    update_data["id"] = doc_id
    update_data["bulkSourceTypeResumeId"] = bulkSourceTypeResumeId
    
    # Create document in bulkSourceTypeParseResumes collection with correct data and bulkSourceTypeResumeId
    collection_name_to_send_doc = "bulkSourceTypeParseResumes"
    DBManager.update_firestore_document_data(collection_name_to_send_doc, doc_id, update_data, processingStatus)

    count_collection_name = "bulkSourceTypeResumes"
    # Increment totalResumesProcessed in bulkSourceTypeResumes collection if COMPLETED
    if processingStatus == "SUCCESS":
        print(f"Incrementing totalResumesSucceeded : {processingStatus} of bulkSourceTypeResumeId {bulkSourceTypeResumeId}")
        parent_doc_ref = DBManager.db.collection(count_collection_name).document(bulkSourceTypeResumeId)
        parent_doc_ref.update({"totalResumesSucceeded": firestore.Increment(1)})
        print(f"Incremented totalResumesSucceeded for {bulkSourceTypeResumeId}")
    
    elif processingStatus == "FAILED":
        print(f"Incrementing totalResumesFailed : {processingStatus} of bulkSourceTypeResumeId {bulkSourceTypeResumeId}")
        parent_doc_ref = DBManager.db.collection(count_collection_name).document(bulkSourceTypeResumeId)
        parent_doc_ref.update({"totalResumesFailed": firestore.Increment(1)})
        print(f"Incremented totalResumesFailed for {bulkSourceTypeResumeId}")
        
        
    elif processingStatus == "DUPLICATE":
        print(f"Incrementing totalResumesDuplicate : {processingStatus} of bulkSourceTypeResumeId {bulkSourceTypeResumeId}")
        parent_doc_ref = DBManager.db.collection(count_collection_name).document(bulkSourceTypeResumeId)
        parent_doc_ref.update({"totalResumesDuplicate": firestore.Increment(1)})
        print(f"Incremented totalResumesDuplicate for {bulkSourceTypeResumeId}")
        
    else:
        print(f"Unknown processingStatus: {processingStatus} for bulkSourceTypeResumeId {bulkSourceTypeResumeId}. No increment performed in totalResumesProcessed.")

def get_data_to_update_in_firstore(cvExtractedParsed,status):

    candidateName = cvExtractedParsed.get("candidateName","")
    candidate_email = cvExtractedParsed.get("candidateEmail","")
    candidatePhoneNumber = cvExtractedParsed.get("candidatePhoneNumber","")
    candidateNumber = cvExtractedParsed.get("candidateNumber",0)
    candidatePhoneCountryCode = cvExtractedParsed.get("candidatePhoneCountryCode",0)
    phoneNumberDetails ={"candidatePhoneNumber":candidatePhoneNumber,"candidateNumber":candidateNumber,"candidatePhoneCountryCode":candidatePhoneCountryCode}
    createdAt = datetime.now().isoformat()
    updatedAt = datetime.now().isoformat()
    return {
        "candidateName": candidateName,
        "candidateEmail": candidate_email,
        "phoneNumberDetails": phoneNumberDetails,
        "createdAt": createdAt,
        "updatedAt": updatedAt,
        "status":status
    }

def get_meta_data(event):
    s3_client = boto3.client('s3')

    # Extract bucket and key from event
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    # key = "companies/01JWAQF1G96E0SE9XHXSFGHNWW/bulk-cvs/01KH8PX3GBW8N6RP1SBRSXN79P.pdf"
    # bucket = "worko-corporate-cand-profile-dev"
    # Get object metadata
    response = s3_client.head_object(Bucket=bucket, Key=key)
    metadata = response.get('Metadata', {})
    return metadata

def get_counts(collection_name_for_firstore_updating_counts,bulkSourceTypeResumeId,DBManager):
#get the document from firestore with bulkSourceTypeResumeId 
    doc = DBManager.get_document_firstore(collection_name_for_firstore_updating_counts,bulkSourceTypeResumeId) 

    totalResumesUploaded = doc.get("totalResumesUploaded","")
    totalResumesSucceeded = doc.get("totalResumesSucceeded","")
    totalResumesFailed = doc.get("totalResumesFailed","")
    totalResumesDuplicate = doc.get("totalResumesDuplicate","")
    if (totalResumesUploaded  - 1) == totalResumesSucceeded+totalResumesFailed +totalResumesDuplicate:
        this_is_last_resume = True
    else:
        this_is_last_resume = False

    if any([totalResumesSucceeded, totalResumesFailed, totalResumesDuplicate,totalResumesUploaded]) is not None:
        print("totalResumesUploaded",totalResumesUploaded)
        print("totalResumesSucceeded",totalResumesSucceeded)
        print("totalResumesFailed",totalResumesFailed)
        print("totalResumesDuplicate",totalResumesDuplicate)
       
    else:
        print(f"totalResumesSucceeded field == {totalResumesSucceeded} in Firestore document for bulkSourceTypeResumeId:",bulkSourceTypeResumeId)
    return doc

def if_last_cv(collection_name_for_firstore_updating_counts,bulkSourceTypeResumeId,DBManager):
#get the document from firestore with bulkSourceTypeResumeId 
    doc = DBManager.get_document_firstore(collection_name_for_firstore_updating_counts,bulkSourceTypeResumeId) 

    totalResumesUploaded = doc.get("totalResumesUploaded","")
    totalResumesSucceeded = doc.get("totalResumesSucceeded","")
    totalResumesFailed = doc.get("totalResumesFailed","")
    totalResumesDuplicate = doc.get("totalResumesDuplicate","")

    if totalResumesUploaded == totalResumesSucceeded+totalResumesFailed +totalResumesDuplicate:
        this_is_last_resume = True
    else:
        this_is_last_resume = False

    if any([totalResumesSucceeded, totalResumesFailed, totalResumesDuplicate,totalResumesUploaded]) is not None:
        print("totalResumesUploaded",totalResumesUploaded)
        print("totalResumesSucceeded",totalResumesSucceeded)
        print("totalResumesFailed",totalResumesFailed)
        print("totalResumesDuplicate",totalResumesDuplicate)
       
    else:
        print(f"totalResumesSucceeded field == {totalResumesSucceeded} in Firestore document for bulkSourceTypeResumeId:",bulkSourceTypeResumeId)
    return this_is_last_resume

def send_cv_summary_email(all_cv_parsing_summary, metadata):
    import csv
    from io import StringIO

    to_address = metadata.get("corporateuseremail") or metadata.get("workoadminuseremail")
    print("sending email summary to",to_address)
    
    ses = boto3.client('ses', region_name='ap-south-1')
    source = "no-reply@worko.ai"
    
    summary, total_count = all_cv_parsing_summary
    
    csv_buffer = StringIO()
    writer = csv.writer(csv_buffer)
    
    # SUCCESS section
    writer.writerow(["SUCCESS", f"Count: {summary['SUCCESS']['count']}", ""])
    writer.writerow(["Candidate Name", "Candidate Email", ""])
    for candidate in summary['SUCCESS']['candidates']:
        writer.writerow([candidate["candidateName"], candidate["candidateEmail"], ""])
    writer.writerow(["", "", ""])
    
    # FAILED section
    writer.writerow(["FAILED", f"Count: {summary['FAILED']['count']}", ""])
    writer.writerow(["Candidate Name", "Candidate Email", ""])
    for candidate in summary['FAILED']['candidates']:
        writer.writerow([candidate["candidateName"], candidate["candidateEmail"], ""])
    writer.writerow(["", "", ""])
    
    # DUPLICATE section
    writer.writerow(["DUPLICATE", f"Count: {summary['DUPLICATE']['count']}", ""])
    writer.writerow(["Candidate Name", "Candidate Email", ""])
    for candidate in summary['DUPLICATE']['candidates']:
        writer.writerow([candidate["candidateName"], candidate["candidateEmail"], ""])
    
    csv_content = csv_buffer.getvalue()
    
    subject = "Bulk CV Processing Complete - Summary Report"
    body_text = f"""Dear User,

Your bulk CV upload has been successfully processed.

Processing Summary:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total CVs Uploaded: {total_count}
Successfully Processed: {summary['SUCCESS']['count']}
Failed: {summary['FAILED']['count']}
Duplicates Detected: {summary['DUPLICATE']['count']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Please find the detailed report attached as a CSV file.

Best regards,
Worko Team"""
    
    raw_message = f"From: {source}\nTo: {to_address}\nSubject: {subject}\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=\"boundary\"\n\n--boundary\nContent-Type: text/plain\n\n{body_text}\n\n--boundary\nContent-Type: text/csv; name=\"cv_processing_summary.csv\"\nContent-Disposition: attachment; filename=\"cv_processing_summary.csv\"\n\n{csv_content}\n--boundary--"
    
    try:
        ses.send_raw_email(
            Source=source,
            Destinations=[to_address],
            RawMessage={"Data": raw_message}
        )
        print(f"Email sent to {to_address}")
    except Exception as e:
        print(f"Failed to send email: {e}")

def build_status_summary(all_docs,large_files_list):
    summary = {
        "SUCCESS": {"count": 0, "candidates": []},
        "FAILED": {"count": 0, "candidates": []},
        "DUPLICATE": {"count": 0, "candidates": []}
    }
    # Add unprocessed large files field if large_files_list has items
    if large_files_list and len(large_files_list) > 0:
        print("large_files_list", large_files_list)
        summary["UNPROCESSED_LARGE_FILES"] = {
            "count": len(large_files_list),
            "files": large_files_list
        }

    for data in all_docs:
        status = data.get("status")
        name = data.get("candidateName", "")
        email = data.get("candidateEmail", "")

        if status in summary:
            summary[status]["count"] += 1
            summary[status]["candidates"].append({
                "candidateName": name,
                "candidateEmail": email
            })

    return summary, len(all_docs)


def get_text_from_cv(s3_bucket_name,key):
    try:
        s3_client = boto3.client('s3')
        # Attempt to fetch the PDF file from S3
        response = s3_client.get_object(Bucket=s3_bucket_name, Key=key)
        data = response['Body'].read()

    except ClientError as error:
        # Check the specific error code
        error_code = error.response['Error']['Code']
        if error_code == 'AccessDenied':
            print("Access denied to the S3 object.")
            return None
        elif error_code == 'NoSuchKey':
            print("The specified key does not exist.")
            return None
        else:
            # Handle other possible exceptions
            print(f"Unexpected error: {error_code}")
            return None
    except Exception as e:
        print(f"Error reading from S3: {e}")
        return None
    
    try:
        if ".pdf" in key:
            processed_text = extract_text_from_pdf(data)
            if not processed_text : 
                print('image Based cv processing..')                        ###
                base64_images = extract_images_from_pdf(data)
                processed_text = invoke_claude_with_image(base64_images)   
                print('image Based cv process completed')   
            return processed_text
        elif ".docx" in key:
            processed_text = extract_text_from_docx(data)
            return processed_text
        else:
            print("The file format is not supported.")
            return None
    except Exception as e:
        print(f"Error extracting text from CV: {e}")
        return None

def lambda_handler(event, context):
    # example_path1="s3://worko-corporate-cand-profile-dev/companies/01JWAQF1G96E0SE9XHXSFGHNWW/bulk-cvs/01KD2WDTS7RZKEJ6QFK87MDC0K.pdf"
    # example_path2= "s3://worko-admin-cand-profile-dev/bulk-cvs/01KEH892ZACXJVV996SPKP0948.pdf"
    print("got event:",event)
    env = os.environ.get("ENVIRONMENT", "dev")
    GCP_DATABASE_NAME = "worko-corp-db-"+env
    GCP_secret_name = "GCP-firestore-secret-"+env
    DBManager = FirestoreManager(GCP_secret_name,GCP_DATABASE_NAME)
    collection_name_for_firstore_updating_counts = "bulkSourceTypeResumes"
    env=os.environ.get("ENVIRONMENT", "dev")
    azure_openai_secret_name = "AZURE-openai-secret-multimodel-"+env
    azure_openai_secret = get_secret(azure_openai_secret_name)
    gpt4 = AzureOpenAIClient(azure_openai_secret,model="gpt-4o")
    gpt4_1_mini = AzureOpenAIClient(azure_openai_secret,model="gpt-4.1-mini")
    gpt_models = [gpt4,gpt4_1_mini]
    retry_queue_name = "worko-cand-profile-parser-retry-queue-"+env
    
    try:
        if 'Records' in event and event.get('Records', []) and 'eventSource' in event['Records'][0] and event['Records'][0]['eventSource'] == 'aws:sqs':
            print("This Event is triggered by SQS...")
            record = event['Records'][0]
            try:
                body = json.loads(record['body'])
                print(f"[DEBUG] Parsed body type: {type(body)}")
                print(f"[DEBUG] Body keys: {body.keys() if isinstance(body, dict) else 'Not a dict'}")
            except Exception as e:
                body = record['body']
                print(f"message body direct loaded: {e}")
            
            ### customise with meta data you will receive from s3 event or sqs event
            metadata = body.get('metadata', {})
            company_id = metadata.get("company_id", "")
            bulksourcetyperesumeid = metadata.get("bulksourcetyperesumeid","")
            s3_bucket_name = body.get("bucket_name","")
            object_key = body.get("object_key","")

            
            if not bulksourcetyperesumeid:
                print(f"Missing bulksourcetyperesumeid in SQS message. Skipping processing.")
                return {'statusCode': 400, 'body': json.dumps('Missing bulksourcetyperesumeid')}
            
            doc = get_counts(collection_name_for_firstore_updating_counts,bulksourcetyperesumeid,DBManager)

        
            retry_counter = body.get("retry_counter", 0)
            print(f"Message receved with retry counter: {retry_counter}")
            
            # processed_text = body.get("processed_text","")
            processed_text = get_text_from_cv(s3_bucket_name,object_key)
            
            file_name = object_key.split("/")[-1]
            
            if retry_counter >= 5:
                print(f"Message received {retry_counter} times, sending to DLQ")
                dlq_name = f"worko-cand-profile-parser-dlq-{env}"
                dlq_url = get_queue_url(dlq_name)
                body["bulksourcetyperesumeid"] =bulksourcetyperesumeid
                sqs.send_message(QueueUrl=dlq_url, MessageBody=json.dumps(body))

                cand_data = {"status": "FAILED"}  # send staus failed in ase of max retry>3
                processingStatus = "FAILED"
                updated_firstore_resume_status(processingStatus,bulksourcetyperesumeid,cand_data,DBManager) 

                return {'statusCode': 200, 'body': json.dumps('Moved to DLQ')}
            
            elif processed_text:
                cvExtractedParsed = process_cv(metadata,retry_queue_name,processed_text,gpt_models,s3_bucket_name,object_key,retry_counter)
                if cvExtractedParsed:
                    # send_final_cv_sqs(cvExtractedParsed,file_name,object_key,DBManager)
                    dublicat_data = check_firstore_dubliacy(cvExtractedParsed, object_key, DBManager)

                    
                    if dublicat_data is None:
                        print(f"this is a unique resume, so trigring sqs for this resume and updasting as SUCCESS in firestore")
                        sqs_send_data = {"companyId": company_id,
                                "candidateCvAwsS3FileName":file_name,
                                "cvExtractedParsed":cvExtractedParsed}
                        send_final_sqs_for_cvExtractparsed(sqs_send_data)
                        status = "SUCCESS"
                        cand_data = get_data_to_update_in_firstore(cvExtractedParsed,status)
                        updated_firstore_resume_status(status,bulksourcetyperesumeid,cand_data,DBManager)   #make this function

                    elif dublicat_data is not None:
                        print(f"Found dublicate record in firstore, Not trigring sqs for this resume and updating status as DUPLICATE in firestore:- {dublicat_data}")
                        status = "DUPLICATE"
                        cand_data = get_data_to_update_in_firstore(cvExtractedParsed,status)
                        updated_firstore_resume_status(status,bulksourcetyperesumeid,cand_data,DBManager)   #make this function

                        # if company_id:
                        #     sqs_send_data = {"event": "CORPORATE_CAND_PROFILE_BULK_UPLOAD",
                        #         "companyId": company_id,
                        #         "candidateCvAwsS3FileName":file_name,
                        #         "cvExtractedParsed":cvExtractedParsed}
                            

                        # else:
                        #     sqs_send_data = {
                        #         "candidateCvAwsS3FileName":file_name,
                        #         "event":"ADMIN_CAND_PROFILE_BULK_UPLOAD",
                        #         "cvExtractedParsed":cvExtractedParsed
                        #     }
                    else:
                        print(f"Error in checking dublicacy in firstore for this resume with email {cvExtractedParsed.get('candidateEmail','')} and phone number {cvExtractedParsed.get('candidatePhoneNumber','')}")    

            else:
                print(f"Missing processed_text in SQS message body. Marking as FAILED.")
                cand_data = {"status": "FAILED"}
                processingStatus = "FAILED"
                updated_firstore_resume_status(processingStatus,bulksourcetyperesumeid,cand_data,DBManager)

        else:
            print("This Event is triggered by S3...")
            
            s3_event = event['Records'][0]['s3']
            bucket_name = s3_event['bucket']['name']
            object_key = unquote_plus(s3_event['object']['key'])
            metadata = get_meta_data(event)
            file_name = object_key.split("/")[-1]  # we need to sent it eith .pdf it will be used for view cv
            
            print(" file_name,", file_name)
            processed_text = get_text_from_cv(bucket_name,object_key)
            
            bulksourcetyperesumeid = metadata.get("bulksourcetyperesumeid","")
            doc = get_counts(collection_name_for_firstore_updating_counts,bulksourcetyperesumeid,DBManager)

            if "companies" in object_key: #example_path1:
                company_id = object_key.split("/")[1]
                metadata["company_id"] = company_id
            else:
                company_id = ""  #check once this work in all cases
            if not processed_text:
                print(f"Failed to extract text from S3, sending to retry queue")
                body = {"bucket_name": bucket_name,"object_key": object_key,"from":"S3 text extraction failed","retry_counter":0,"metadata":metadata}
                send_sqs_for_throttling_error(retry_queue_name,body,30)
                return {'statusCode': 200, 'body': 'Sent to retry queue'}
            
            cvExtractedParsed = process_cv(metadata,retry_queue_name,processed_text,gpt_models,bucket_name,object_key,0)

            if cvExtractedParsed:
                print("cvExtractedParsed",str(cvExtractedParsed)[:100],"...")
                dublicat_data = check_firstore_dubliacy(cvExtractedParsed, object_key, DBManager)
                if dublicat_data is not None:
                    print(f"Found dublicate record in firstore, Not trigring sqs for this resume and updating status as DUPLICATE in firestore:- {dublicat_data}")
                    status = "DUPLICATE"
                    cand_data = get_data_to_update_in_firstore(cvExtractedParsed,status)
                    updated_firstore_resume_status(status,bulksourcetyperesumeid,cand_data,DBManager)
                elif dublicat_data is None:    
                    sqs_send_data = {"companyId": company_id,
                                "candidateCvAwsS3FileName":file_name,
                                "cvExtractedParsed":cvExtractedParsed}
                    send_final_sqs_for_cvExtractparsed(sqs_send_data)
                    status = "SUCCESS"
                    cand_data = get_data_to_update_in_firstore(cvExtractedParsed,status)
                    updated_firstore_resume_status(status,bulksourcetyperesumeid,cand_data,DBManager)
            else:
                print(f"sent the SQS : from s3 event")
                
                

        this_is_last_resume = if_last_cv(collection_name_for_firstore_updating_counts,bulksourcetyperesumeid,DBManager)
        # this_is_last_resume=True  #$$$
        if this_is_last_resume:

            status = "LARGE_RESUME_FILE"
            large_files = DBManager.get_documents_by_bulkSourceTypeResumeId_and_status(collection_name_for_firstore_updating_counts, bulksourcetyperesumeid,status)
            try:
                large_files_list = [i["userResumeFileName"] for i in large_files]
                print("large_files_list",large_files_list)
            except Exception as e:
                print("Got error while getting large files data",e)


            Data_of_cv  = DBManager.get_documents_by_bulkSourceTypeResumeId("bulkSourceTypeParseResumes",bulksourcetyperesumeid)
            print("all parsed cv data in bulk collection",Data_of_cv)
            all_cv_parsing_summary =build_status_summary(Data_of_cv,large_files_list)
            send_cv_summary_email(all_cv_parsing_summary, metadata)


    except Exception as e:
        print(f"Error in lambda_handler: {e}")
        cand_data = {"status": "FAILED"}  # send staus failed in ase of max retry>3
        processingStatus = "FAILED"
        updated_firstore_resume_status(processingStatus,bulksourcetyperesumeid,cand_data,DBManager) 
        return {'statusCode': 500, 'body': json.dumps(f'Error: {e}')}


if __name__ == "__main__":
    # event ={'Records': [{'eventVersion': '2.1', 'eventSource': 'aws:s3', 'awsRegion': 'ap-south-1', 'eventTime': '2026-02-13T10:54:41.817Z', 'eventName': 'ObjectCreated:Put', 'userIdentity': {'principalId': 'AWS:AROATCKANHWV2MBXXE3V6:worko-corp-dev-workoCorp'}, 'requestParameters': {'sourceIPAddress': '103.176.210.127'}, 'responseElements': {'x-amz-request-id': 'A1ZX01WYQJ2Y5JH6', 'x-amz-id-2': 'wnmtopZYMlwdUUFEXUaSsPUXlfUOrsb3JKWieIvgG+zU+Hph9o1vtOaooaRN2iInFw8mWnp2dHqT/iRGvosQet9Nbvr5t1qpjWBXU656KVw='}, 's3': {'s3SchemaVersion': '1.0', 'configurationId': 'a6c870b0-fd5d-4747-ac88-27e26b7ecba5', 'bucket': {'name': 'worko-admin-cand-profile-dev', 'ownerIdentity': {'principalId': 'A1V0APDMR493SG'}, 'arn': 'arn:aws:s3:::worko-admin-cand-profile-dev'}, 'object': {'key': 'bulk-cvs/01KHBA6ZW2MDQWJN4WE2YJXFDV.pdf', 'size': 58816, 'eTag': 'ecdcfaabc0c96728a65b559256cc68f6', 'sequencer': '00698F02F1C38704BF'}}}]}  
    # event = {"Records":[{"eventVersion":"2.1","eventSource":"aws:s3","awsRegion":"ap-south-1","eventTime":"2026-02-13T05:21:25.288Z","eventName":"ObjectCreated:Put","userIdentity":{"principalId":"AWS:AROATCKANHWV2MBXXE3V6:worko-corp-dev-workoCorp"},"requestParameters":{"sourceIPAddress":"103.176.210.127"},"responseElements":{"x-amz-request-id":"A7DP139505J83HYT","x-amz-id-2":"7qLalj01knes4BpKEg5sLH1PjcL91s9OGs69//2J775bV3sZLPXHSwrmOd1NLv3T0+tMFZQL58bR0lLKCVHtJFEc5LKEe1zZmU5N5y6A+Q4="},"s3":{"s3SchemaVersion":"1.0","configurationId":"a6c870b0-fd5d-4747-ac88-27e26b7ecba5","bucket":{"name":"worko-admin-cand-profile-dev","ownerIdentity":{"principalId":"A1V0APDMR493SG"},"arn":"arn:aws:s3:::worko-admin-cand-profile-dev"},"object":{"key":"bulk-cvs/01KHAQ4QXFP0HW6BSFRK926JH1.pdf","size":225212,"eTag":"296eeb83abfe1d84d866db9a55621a78","sequencer":"00698EB4D53FB3565C"}}}]}
    # lambda_handler(event, None)
    # event= {'Records': 
    #         [{'messageId': '200dbd50-972f-4e1f-b649-e08fe263ea26', 'receiptHandle': 'AQEBx+TZ+WFSQcByKvLWnm0JsiPozA1SR65NOIzdGwoCbxABRC0mrB2Uvfy7KHkxaYF0f+USJtXnAv8aZx11XFWdUzXtbv/9820o1PP527vRnQ83pIHwzaKDwNnlJ6Ys1+NKwsgY7XTA4WYXg+uhNMEhCd4V9zWMvQSKGvObghkzaMiHbUDaRAQz614VhthKjHoNvccaKnhhd5a14K1L1q2u/7vs+/9cVF9yam0Boft5Z22dRl3ITbv8A0SAZMJcznSRerL0g4xl4ri/ZYTtrwKVlUwWo8+rSbXvf/wixo8pw339oD9g61YrE3oERfhees9OSstfaDM5UGg+EdOpHvdsxPrVLv+GcHiWPOJzOAN8QoqajpnRuRmG7gtoxvC7fAXCxhPby0Ld2Esiko+MLMV1iR7SEAAo1DklnoPsEHxZ2Z5fVvzZMz2JTqDt2XdQ1IvT', 
    #           'body': '{"bucket_name":"worko-admin-cand-profile-dev","processed_text": "Shatakshi Mishra LinkedIn | +91 6386311282 | mishrashatakshi009@gmail.com WORK EXPERIENCE Zulu Club (0\\u21921 Hyperlocal Fashion & Lifestyle Startup) Gurugram Founding Member & Chief of Staff May 2025- Present Strategy & Growth \\u2022 Acted as Chief of Staff to Founder & CEO, managing strategic initiatives and freeing 15\\u201320% CEO bandwidth for fundraising and external partnerships. \\u2022 Supported pre-seed fundraising, preparing investor materials and analyses that helped secure \\u20b92 crore from early investors \\u2022 Built multi-functional operations from scratch, handling 5+ verticals (partnerships, category management, inventory, marketing, tech, fund-raise, hiring, etc) 0\\u21921 Business Building & GTM \\u2022 Launched \\u201cTry at Home\\u201d model from 0\\u21921 \\u2014 curated assortments across Men\\u2019s, Women\\u2019s, Home D\\u00e9cor, and Beauty (2000+ SKUs), set up dark store operations, and operationalised GTM strategies \\u2022 Built outlet partnerships function from 0\\u21921 \\u2014 identified, pitched, and onboarded 100+ outlets across fashion, lifestyle, and accessories, creating the marketplace\\u2019s initial partner network and contributing 85% of early GMV \\u2022 Piloted AI-based cataloguing (image isolation, upscaling), reducing manual listing effort by 30% and cutting onboarding turnaround from 4 days \\u2192 2 days Marketing & Customer Acquisition \\u2022 Orchestrated gamified Instagram ad campaigns, increasing engagement 2.3x and improving CTR from 0.1% \\u2192 3%, driving 1000+ incremental sign- ups \\u2022 Ran Instagram performance marketing campaigns with \\u20b91 lakh budget, lowering CAC by 75% and scaling reach to 10,000+ users in 2 months \\u2022 Coordinated 30+ content shoots, delivering outlet storytelling campaigns that improved brand discovery and boosted engagement by 30% \\u2022 Planned and executed 45+ BTL activations (pop-ups, offline events), generating 90% uplift in downloads and 25% increase in sales Product \\u2022 Zulu Club App- Collaborated with product & tech teams to execute multiple versions of Zulu Club app, delivering improved content curation and aesthetics, which led to 28% higher session times and 7.5% increase in order conversion rates \\u2022 Zulu Club Website- Conceptualised and executed end-to-end website redesign \\u2014 from user research and content curation to UI/UX design and rollout \\u2014 improving discoverability, boosting average session times, raising lead-to-order conversion \\u2022 Developed Outlet/Seller page product flow on web platform, aligning catalogue design with buyer journeys Samagra Transforming Governance New Delhi Management Consultant, Strategy & Ops for President of India Nov 2023 \\u2013 Oct 2024 Project & Stakeholder Management \\u2022 Identified, conceptualized & led complex projects, played advocate to the President of India; Secretaries, Addl Secretaries and Directors of various Govt Ministries, PSUs \\u2022 Developed a strategic roadmap for administrative reforms for President of India\\u2019s Secretariat, streamlining recruitment, services, transitions, impacting 500+ personnel \\u2022 Reimagined the role of the President of India in Viksit Bharat, crafting a strategic framework for events at Rashtrapati Bhavan, Presidential tours- international and domestic, driving 33% increased public engagement through enhanced outreach \\u2022 Spearheaded the end-to-end planning and management of the 2024 Swearing-in Ceremony for the Union Council of Ministers, Bhartiya Kala Mahotsav, ensuring flawless execution for an audience of 8k+ and 1 lakh+ respectively \\u2022 Designed a blitzkrieg outreach strategy with partners like EaseMyTrip, Tripadvisor, Paytm Insider, increasing footfall at Rashtrapati Bhavan attractions by 45% YoY \\u2022 Contributed to the creation of Goods & Services Procurement Playbook, improving vendor onboarding, reducing turnaround time for critical tenders by 30% \\u2022 Collaborated with the GoI ministries to drive the decolonization and Indianization of 150+ artifacts across Presidential estates, modernizing the historical narrative\\\\ \\u2022 Continuously engaged in creating timelines, milestones, project plans, manage project teams, track success through measurable KPIs & delivering executive reports/ presentations to Govt stakeholders and C-Suite of collaborating private companies Customer Experience and Digital Engagement \\u2022 Led the overhaul of 6 Rashtrapati Bhavan websites optimizing customer journey by conducting user research, A/B Testing, revamp of SEO strategy, intuitiveness and accessibility features of UI/UX, leveraging Google Analytics, Microsoft Clarity, Figma, etc, Boosted Y-O-Y website visitor numbers by 50% and funnel optimization of bookings from 8% to 16% conversion, reducing bounce rate by 20% \\u2022 Optimized digital touchpoints by launching the Rashtrapati Bhavan app through pan-India rollout to all Android and iOS users \\u2022 Data Driven Improvements: Implemented target-based performance management, fostering ownership among junior officers, reviving 20+ languishing projects \\u2022 Process Automation: Strategized and implemented 10+ E-Governance initiatives, optimized process turnaround, reducing bottlenecks between departments by 25% \\u2022 Created strategy for improving product and CX at Rashtrapati Bhavan Main Building, Museum, Amrit Udyan, Rashtrapati Estates-Shimla & Hyderabad Increasing NPS score by 18%, reducing complaints by 24% and increasing self-service adoption rates by 15% Achievements \\u2022 Received Spot Award of Excellence for outstanding project management in finalizing the upcoming Tribal Museum\'s content and curation Ministry of Skill Development & Entrepreneurship New Delhi Consultant, Strategy & Ops for SANKALP Scheme Oct 2021 Oct 2023 \\u2022 Spearheaded the formation and enhancement of District Skill Committees in coordination with district administrations, aligning efforts with line departments to strengthen skill development across the region, leading to a 30% increase in skill training participation \\u2022 Pioneered first-ever Skill Gap Analysis and made District Skill Development Plan \\u201922 for East Delhi, focusing on local demand and supply of skills \\u2022 Mapped tourist potential areas in the district and made plan for drawing more tourists with Tourism & Hospitality Sector Skill Council \\u2022 Facilitated apprenticeship promotion through NAPS, organizing PMNAM at ITIs around Delhi providing apprenticeship offers to 700+ candidates \\u2022 Strengthened National Education Policy (NEP) 2020 through demand aggregation of job roles and institutional mapping in the district, formulated and launched Adult Education Project for educating 140 people of slum areas in the district, in tandem with NIOS \\u2022 Conceptualized and executed marketing strategies for Self-Help Group (SHG) products, leading to the successful Mahila Hunar Haat at Akshardham Metro Station \\u2022 Negotiated and onboarded key CSR partnerships with organizations like Xiaomi, TATA Motors, IBM, and NGOs like Mahindra Pride, Quest Alliance resulting in 22,000+ candidates skilled in a year, driving economic upliftment \\u2022 Orchestrated disaster response efforts during the Delhi Floods 2023, managing the evacuation of 1,500+ individuals and ensuring effective crisis management in flood-prone areas \\u2022 Designed and deployed Project Rahnuma, providing 2500+ individuals with personalized counselling and skilling support to enhance livelihood opportunities. \\u2022 Conceptualised and implemented Project Mohini: Skill Development and 100% Placement of 60+ transgender persons Achievements \\u2022 Handpicked (9/650) by. Secretary, MSDE for developing a Model District Skill Development Plan for the country, by leading a team of 9 to draft the plan based on insights from RDSDE and SANKALP teams \\u2022 Selected (7/650) to be part of Core Team to organise Akhil Bhartiya Shiksha Samagam \\u201823 having a footfall of 1 lakh+ people Certificate of Recognition from CEO, National Skill Development Corporation for contribution in making the event a success LegalXGen Bengaluru Senior Analyst, CEO\\u2019s Office Sep 2017 Dec 2019 \\u2022 Reduced time-to-market of releases by a month through targeted process enhancements, elevating operational efficiency and productivity \\u2022 Elevated SLAs by actively engaging with leadership, configuring new feature requirements and ensuring precise sprint scope \\u2022 Cut revenue leakage by 30% through implementation of billing automation and unpaid invoices reminder features \\u2022 Collaborated with presales, sales and marketing teams in solutioning, drafting sales and marketing pitch to triple the client base Ericsson Noida Engineer, Operations-Service Requirement Fulfillment Jul 2016 Aug 2017 \\u2022 Sprint, USA | Trunk Management Testing: Handled execution of T1 Provisioning, Testing, Install & Disconnect of Normal and 911 calls \\u2022 Digicel, PNG | Back Office: Overhauled the network mapping directory, reducing troubleshooting time by 30% in critical network failures, impacting 2.5mn users LEADERSHIP \\u2022 Chief of Staff to Founder & CEO of Zulu Club, managed 20+ people of 3 verticals- Business, Tech/Product and Marketing \\u2022 Identified, conceptualized & led complex projects, played advocate to the President of India; Secretaries, Addl Secretaries and Directors of various Govt Ministries & PSUs \\u2022 Continuously engaged in creating timelines, milestones, project plans, manage project teams, track success through measurable KPIs & delivering executive reports/presentations to Govt stakeholders and C-Suite of collaborating private companies EDUCATION Indian Institute of Management, Kozhikode 2021-2023 Public Policy & Management Indira Gandhi Delhi Technical University 2012-2016 B.Tech, Information Technology", '
    #           '"object_key": "bulk-cvs/01KHBG74CP2BRYG94V236S8WT0.pdf", '
    #           '"from": "throttling error", "retry_counter": 1, '
    #           '"metadata": {"bulksourcetyperesumeid": "01KHBG70MXK0BEWBQ5AMGW3TCX", '
    #           '"workoadminuseremail": "raj.ghosh@worko.ai"}}',
    #            'attributes': {'ApproximateReceiveCount': '1', 'AWSTraceHeader': 'Root=1-698f1b8b-04a0bf1f422269094319ee89;Parent=48e3c2fe9aae6204;Sampled=0;Lineage=1:3a1bb061:0', 'SentTimestamp': '1770986390226',
    #                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'SenderId': 'AROATCKANHWVU3UAPBTQ2:worko-cand-profile-parser-dev', 'ApproximateFirstReceiveTimestamp': '1770986455912'}, 
    #           'messageAttributes': {}, 'md5OfBody': '30f2f4eb84e8973f7ee78c6be6db1c2b', 'eventSource': 'aws:sqs', 'eventSourceARN': 'arn:aws:sqs:ap-south-1:211125353899:worko-cand-profile-parser-retry-queue-dev', 'awsRegion': 'ap-south-1'}]}
    event = {'Records': [{'eventVersion': '2.1', 'eventSource': 'aws:s3', 'awsRegion': 'ap-south-1', 'eventTime': '2026-03-12T12:41:30.916Z', 'eventName': 'ObjectCreated:Put', 'userIdentity': {'principalId': 'AWS:AROATCKANHWVX5Y5CYHFH:worko-corp-dev-workoCorp-v9'}, 'requestParameters': {'sourceIPAddress': '103.176.210.178'}, 'responseElements': {'x-amz-request-id': '7P1GC355QZBGRPXR', 'x-amz-id-2': 'F6i/THRGLi1mNhBf0HXrJPDGJS2IfLGai11pEMOiJ1GZFwzm0iejQwli0fX/b/U3kXU8vHMvva06ekwhlmMyIEXoe4F0uW6SUv2snFmhlFY='}, 's3': {'s3SchemaVersion': '1.0', 'configurationId': '7bf28bb9-cec6-40ba-8c21-819741898750', 'bucket': {'name': 'worko-corporate-cand-profile-dev', 'ownerIdentity': {'principalId': 'A1V0APDMR493SG'}, 'arn': 'arn:aws:s3:::worko-corporate-cand-profile-dev'}, 'object': {'key': 'companies/01KCGXV5WPA6C4S0PXFSMRQAQZ/bulk-cvs/01KKH11ZP7G0CRX19QG73PNP6K.pdf', 'size': 229644, 'eTag': 'ad3a44d23bab300a83ddb130bf23b098', 'sequencer': '0069B2B47ADDEEA57B'}}}]}
    lambda_handler(event, None)
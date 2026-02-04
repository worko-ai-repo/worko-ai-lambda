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

def update_sqs_queue(message_body):
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
        print("Do dubliact found, sqs (parsed cv) sent to backend")
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

def process_cv(retry_queue_name, processed_text, gpt_models, object_key) -> Tuple[str, Dict[str, str]]:
    print("Processing cv for cvexractparesed")
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
            f"1. candidatePhoneNumber: number with country code (string), 2. candidateNumber:  number only without country code (int), 3. candidatePhoneCountryCode (int)"

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
            f"  \"candidateEmail\": \"\",\n"
            f"  \"candidatePhoneNumber\": \"\",\n"
            f"  \"candidateNumber\": 0,\n"
            f"  \"candidatePhoneCountryCode\": 0,\n"
            f"  \"candidateCurrentCompany\": \"\",\n"
            f"  \"candidateCurrentDesignation\": \"\",\n"
            f"  \"candidateExperience\": 0,\n"
            f"  \"candidateTotalYOE\": 0,\n"
            f"  \"candidateRelevantYOE\": 0,\n"
            f"  \"candidateCurrentCTC\": 0,\n"
            f"  \"candidateExpectedCTC\": 0,\n"
            f"  \"candidateNoticePeriod\": 0,\n"
            f"  \"candidateLocation\": \"\",\n"
            f"  \"candidateReadyToRelocate\": false,\n"
            f"  \"isNoticePeriodNegotiable\": false\n"
            f"}}}}\n"
        )
        cv_extracted_parsed = gpt_models[0].invoke_model_with_backoff(parsed_prompt,Task= "get cvExtractparsed step1 ")
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
        
        return merged
        

    except Exception as execution_error:
        error_message = str(execution_error).lower()
        # error_traceback = traceback.format_exc()# Check if this is a throttling error
        if any(term in error_message for term in ['throttling', 'throttled', 'rate limit', 'too many requests', '429']):
            print("Errore of {execution_error} now sending sqs for startuing again in next 60 seconds")

            send_sqs_for_throttling_error(retry_queue_name,processed_text,object_key) #send sqs for throttled error
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

def send_sqs_for_throttling_error(retry_queue_name,processed_text,object_key):
    try:
        from datetime import datetime, timedelta
        queue_url = get_queue_url(retry_queue_name)
        sqs = boto3.client('sqs')
        
        message_body = {"processed_text": processed_text,"object_key": object_key,"from":"throttling error"}
        delay_seconds = 60
        
        current_time = datetime.now()
        visible_time = current_time + timedelta(seconds=delay_seconds)
        
        print(f"[SQS SEND] Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"[SQS SEND] Message will be visible at: {visible_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"[SQS SEND] DelaySeconds: {delay_seconds}")
        print(f"SQS message body for throttled steps: {json.dumps(str(message_body)[:100])}")
        
        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body, default=decimal_default),
            DelaySeconds=delay_seconds
        )
        
        print(f"[SQS SEND] MessageId: {response.get('MessageId', 'N/A')}")
        
        
    except Exception as sqs_error:
        print(f"Error sending send_sqs_for_throttling_error step to SQS: {sqs_error}")
        print(f"Queue URL attempted: {queue_url}")
        print(f"Message body: {message_body}")

def send_final_cv_sqs(cvExtractedParsed,file_name,object_key,DBManager):
    email = cvExtractedParsed.get("candidateEmail","")
    phone_number = cvExtractedParsed.get("candidatePhoneNumber","") 
    country_code = cvExtractedParsed.get("candidateCountryCode","")

    if "companies" in object_key: #example_path1:
        # query data and check it present or not
        collection = "corporateCandidateProfiles"
        company_id = object_key.split("/")[1]
        
        data = DBManager.get_candidate_profiles( collection,company_id, email, phone_number, country_code)
        print("Data.......",data)

        if data is not None:
            print(f"Not trigring sqs as found dublicate record in collection corporateCandidateProfiles : - {data}")

        else:
            sqs_send_data = {"event": "CORPORATE_CAND_PROFILE_BULK_UPLOAD",
            "companyId": company_id,
            "candidateCvAwsS3FileName":file_name,
            "cvExtractedParsed":cvExtractedParsed}
            update_sqs_queue(sqs_send_data)

            print(f"trigring sqs as  do not found any dublicate record in collection corporateCandidateProfiles :- {cvExtractedParsed}")
            #trigre sqs
    else:

        collection = "centralCandidateProfiles"
        company_id = None
        data = DBManager.get_candidate_profiles( collection,company_id, email, phone_number, country_code)
        
        if data is not None:
            print(f"Not trigring sqs as found dublicate record in collection centralCandidateProfiles : - {data}")

        else:
            #triger sqs
            print(f"trigring sqs as  do not found any dublicate record in collectoin centralCandidateProfiles {cvExtractedParsed}")
            sqs_send_data = {
                "candidateCvAwsS3FileName":file_name,
                "event":"ADMIN_CAND_PROFILE_BULK_UPLOAD",
                "cvExtractedParsed":cvExtractedParsed
            }
            update_sqs_queue(sqs_send_data)

def lambda_handler(event, context):
    # example_path1="s3://worko-corporate-cand-profile-dev/companies/01JWAQF1G96E0SE9XHXSFGHNWW/bulk-cvs/01KD2WDTS7RZKEJ6QFK87MDC0K.pdf"
    # example_path2= "s3://worko-admin-cand-profile-dev/bulk-cvs/01KEH892ZACXJVV996SPKP0948.pdf"
    print("got event:",event)
    env=os.environ.get("ENVIRONMENT", "dev")
    azure_openai_secret_name = "AZURE-openai-secret-multimodel-"+env
    azure_openai_secret = get_secret(azure_openai_secret_name)
    gpt4 = AzureOpenAIClient(azure_openai_secret,model="gpt-4o")
    gpt_models = [gpt4]
    retry_queue_name = "worko-cand-profile-parser-retry-queue-"+env
    
    GCP_DATABASE_NAME = "worko-corp-db-"+env
    GCP_secret_name = "GCP-firestore-secret-"+env
    DBManager = FirestoreManager(GCP_secret_name,GCP_DATABASE_NAME)


    if 'Records' in event and event.get('Records', []) and 'eventSource' in event['Records'][0] and event['Records'][0]['eventSource'] == 'aws:sqs':
        is_sqs_trigger = True
        print("This Event is triggered by SQS...")
        
        record = event['Records'][0]
        receive_count = int(record['attributes'].get('ApproximateReceiveCount', 1))
        print(f"Message receive count: {receive_count}")
        
        message_body = json.loads(record['body'])
        processed_text = message_body.get("processed_text","")
        object_key = message_body.get("object_key","")
        file_name = object_key.split("/")[-1].split(".")[0]
        
        if receive_count >= 3:
            print(f"Message received {receive_count} times, sending to DLQ")
            dlq_name = f"worko-cand-profile-parser-dlq-{env}"
            dlq_url = get_queue_url(dlq_name)
            sqs.send_message(QueueUrl=dlq_url, MessageBody=json.dumps(message_body))
            return {'statusCode': 200, 'body': json.dumps('Moved to DLQ')}
        
        elif processed_text:
            cvExtractedParsed = process_cv(retry_queue_name,processed_text,gpt_models,object_key)
            if cvExtractedParsed:
                send_final_cv_sqs(cvExtractedParsed,file_name,object_key,DBManager)

        return {
            'statusCode': 200,
            'body': json.dumps('Lambda successful for sqs event')
        }

    else:
        print("This Event is triggered by S3...")
        s3_client = boto3.client('s3')
        s3_event = event['Records'][0]['s3']
        bucket_name = s3_event['bucket']['name']
        object_key = unquote_plus(s3_event['object']['key'])
        file_name = object_key.split("/")[-1]
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
        

        
        
        cvExtractedParsed = process_cv(retry_queue_name,processed_text,gpt_models,object_key)

        try:
            if cvExtractedParsed:
                print("cvExtractedParsed",cvExtractedParsed)
                send_final_cv_sqs(cvExtractedParsed,file_name,object_key,DBManager)
        except Exception as e:
            print(f"Error sending final CV to SQS: {e}" )


        return {
            'statusCode': 200,
            'body': json.dumps('Lambda successful for s3 event')
        }

# if __name__ == "__main__":
        
        
#     event = {
    
#     "Records": [
#         {
#         "eventVersion": "2.1",
#         "eventSource": "aws:s3",
#         "awsRegion": "ap-south-1",
#         "eventTime": "2026-01-12T08:49:37.805Z",
#         "eventName": "ObjectCreated:Put",
#         "userIdentity": {
#             "principalId": "AWS:AROATCKANHWVTQO36WAQQ:shaukat.shaikh@worko.ai"
#         },
#         "requestParameters": {
#             "sourceIPAddress": "103.176.210.144"
#         },
#         "responseElements": {
#             "x-amz-request-id": "F031QF2YBESZRM4Q",
#             "x-amz-id-2": "3J8llYeAiPZz/RPXfu1ash0wyQxRs9Ch5m//4X3bN8qS7v4IuEQgdwL68QkrVMItmHqWkssdEzS6jOjKZ7u0rsNz2DD+dF/6"
#         },
#         "s3": {
#             "s3SchemaVersion": "1.0",
#             "configurationId": "2391fd04-1e04-41f3-9a68-3c5d8a728a02",
#             "bucket": {
#             "name": "worko-corporate-cand-profile-dev",
#             "ownerIdentity": {
#                 "principalId": "A1V0APDMR493SG"
#             },
#             "arn": "arn:aws:s3:::worko-corporate-cand-profile-dev"
#             },
#             "object": {
#             "key": "companies/01JWAQF1G96E0SE9XHXSFGHNWW/bulk-cvs/Shubham+prinicipal+engineer.pdf",
#             "size": 225212,
#             "eTag": "296eeb83abfe1d84d866db9a55621a78",
#             "sequencer": "006964B5A1B7FA55DF"
#             }
#         }
#         }
#     ]
#     }

    # event= {'Records':[{"eventSource":"aws:sqs","body":{"object_key":"companies/01JWAQF1G96E0SE9XHXSFGHNWW/bulk-cvs/Shubham+prinicipal+engineer.pdf",
    #                                                     "processed_text":"""SHAUKAT SHAIKH
    #     7757852171 Mumbai, Maharashtra, India shaukatdatascience@gmail.com
    #     github.com/Shaukat-Shaikh
    #     Summary
    #     linkedin.com/in/ShaukatShaikh71/
    #     Data Science profess
    #     ional with 1.5+ years building production ML/ DL solutions and LLM applications. 
    #     Specialized in Generative AI, RAG pipelines, and transformers using cloud platforms, Crew AI, n8n, and 
    #     LangChain. Currently working in the hiring industry while training AI professionals in GenAI. Proven expertise 
    #     in model optimization, financial analytics, and AI automation. Passionate about leveraging cutting-edge AI for 
    #     complex business problems.
    #     Work Experience
    #     Al Engineer Intern, Worko.ai, Bangalore. Remote
    #     •
    #     Improved an Al-driven resume-job matching system using LLMs by 30% adding 
    #     more structured logic and inserting feedback received from recruiter.
    #     •
    #     Implemented rag based job listing for job board using Aws Lambda Vector Store 
    #     Opensearch.
    #     •
    #     Fine-tuned transformer models (e.g., MiniLM, sentence-transformers) on domain
    #     specific data to enhance semantic matching and candidate scoring.
    #     Collaborated with fullstack team to build Ai driven a video interview product.
    #     •
    #     GenAl Trainer, Kalp Academy Remote
    #     •
    #     Delivering training programs on Generative AI, LLMs, and practical AI applications 
    #     to aspiring professionals and developers.
    #     •
    #     Teaching Prompt Engineering techniques including zero-shot, few-shot, and 
    #     chain-of-thought prompting for optimal LLM performance.
    #     •
    #     Conducting hands-on sessions on LangChain framework for building production
    #     grade LLM applications, agents, and memory systems.
    #     •
    #     Training on RAG pipelines, vector databases, embedding models, and semantic 
    #     search optimization.
    #     •
    #     Developing course materials, assignments, and real-world projects for practical 
    #     implementation.
    #     •
    #     Mentoring on GenAI deployment best practices, model selection, cost 
    #     optimization, and ethical AI considerations.
    #     Data science Engineer, Renew Instruments Wadala, Mumbai
    #     •
    #     Developed ML/ DL models using Scikit-learn and Tensorflow, incorporating 
    #     quantitative finance techniques to enhance predictive analytics and risk 
    #     modelling.
    #     •
    #     Applied financial modelling expertise to equity options and futures, contributing 
    #     to data-driven decision-making.
    #     •
    #     Utilized MS Office tools to document findings, create reports, and communicate 
    #     financial insights effectively.
    #     06/2025 – Present
    #     11/2025 – Present
    #     04/2024 – 03/2025
    #     Technical Skills
    #     Analytics
    #     Programming Language
    #     Python. Database Language: SQL MLOPS: CICD, 
    #     GitHub Action. DockerHub
    #     Al
    #     GenAl, LangChain, LangGraph,
    #     PROFESSIONAL COURSES
    #     Numpy and Pandas Tools: Power BI, Advance Fixcel 
    #     Cloud: AWS
    #     Machin Learning
    #     Data Pre-processing, Regression, Naive Bayes, 
    #     Decision Trees, Support Vector Machines, K-Nearest 
    #     Neighbors, Clustering, Principal Component 
    #     Analysis, Boosting, Pytorch, Deep Learning (ANN, 
    #     NLP, CNN)
    #     MASTERS IN DATA SCIENCE WITH AI AND AWS, IT VEDANT, THANE
    #     EDUCATION
    #     2022 – 2023
    #     MUMBAIUNIVERSITY, BSC (SMT.CHM COLLEGE ULHASNAGAR)
    #     MUMBAIUNIVERSITY, HSC (ST.MERRY'S JR COLLEGE THANE)
    #     2019 – 2022
    #     2018 – 2019"""}}]}
    lambda_handler(event, None)





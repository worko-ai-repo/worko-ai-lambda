"""Helper utilities for the referral-source candidate profile parser Lambda.

This module contains small, focused helpers for:
- retrieving and parsing raw email objects stored in S3
- extracting attachments and text from PDF resumes
- lightweight heuristics to extract email/phone/companyId
- optional Firestore duplicate checking
- uploading candidate CVs to S3 and sending SQS/SES messages

The helpers are intentionally small and defensive so they work in the
Lambda runtime whether or not optional dependencies (Firestore, ULID)
are present.
"""

import os
import re
import json
import uuid
from typing import Tuple, Dict, Any, Optional, Union
from google.oauth2 import service_account
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud import firestore
from google.cloud.firestore_v1 import Or, And
import boto3
import requests
import random
import time
from datetime import datetime
# Optional ULID package: fall back to uuid if not available

# PyMuPDF (fitz) for PDF text extraction

source_email = os.environ.get("SES_SOURCE_EMAIL") 
import fitz

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

class AzureOpenAIClient:
    """Client for Azure OpenAI API with retry logic."""
    
    DEFAULT_TEMPERATURE = 0.3
    DEFAULT_API_VERSION = "2024-05-01-preview"
    REQUEST_TIMEOUT = 30  # seconds
    
    def __init__(self, azure_openai_secret: Dict[str, str]):
        """Initialize Azure OpenAI client.
        
        Args:
            azure_openai_secret: Dict containing:
                - AZURE_OPENAI_ENDPOINT
                - deployment_name
                - api_key
                - AZURE_OPENAI_API_VERSION (optional)
        """
        if not isinstance(azure_openai_secret, dict):
            raise TypeError("azure_openai_secret must be a dictionary")
        
        self.endpoint = azure_openai_secret.get("AZURE_OPENAI_ENDPOINT", "")
        self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT", "")
        self.api_version = azure_openai_secret.get(
            "AZURE_OPENAI_API_VERSION", 
            self.DEFAULT_API_VERSION
        )
        self.api_key = azure_openai_secret.get("AZURE_OPENAI_API_KEY", "")
        
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
        for attempt in range(max_retries):
            print("Task to Ai is :- ",Task)
            try:
                return self.invoke_model(system_content, prompt, want_json)
            
            except requests.exceptions.HTTPError as e:
                # Check for rate limiting (429) or server errors (5xx)
                if e.response.status_code in [429, 500, 502, 503, 504]:
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
                json=data,
                timeout=self.REQUEST_TIMEOUT
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
                    json=data,
                    timeout=self.REQUEST_TIMEOUT
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
         
def get_email_id_from_subject(subject):
    email = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', subject)

    if email:
        print(email.group())
    return email.group(0) if email else None

def extract_text_from_pdf(pdf_data: bytes) -> str:
    """Return extracted text from PDF bytes using PyMuPDF.

    Args:
        pdf_data: Raw PDF byte content.

    Returns:
        A single string containing text from all pages.
    """
    text = ""
    pdf_document = fitz.open(stream=pdf_data, filetype="pdf")
    for page in pdf_document:
        text += page.get_text()
    return text

def retrieve_email_from_s3(bucket_name: str, object_key: str):
    """Download an S3 object and parse it as an email.message.Message.

    Returns a tuple (parsed_email_message, raw_bytes).
    Raises ValueError if the object is empty.
    """
    s3 = boto3.client("s3")
    response = s3.get_object(Bucket=bucket_name, Key=object_key)
    raw_email_bytes = response["Body"].read()
    if not raw_email_bytes:
        raise ValueError("No email content found in S3 object")

    # Local import because email package is small and this keeps top-level imports light
    from email import policy
    from email.parser import BytesParser

    parsed_email = BytesParser(policy=policy.default).parsebytes(raw_email_bytes)
    return parsed_email, raw_email_bytes

def get_attachments(email_obj):
    """Walk an email.message object and return attachments as dicts.

    Each attachment dict contains: filename, content_type, size, data(bytes).
    """
    attachments = []
    for part in email_obj.walk():
        content_disposition = part.get_content_disposition()
        if content_disposition == "attachment":
            filename = part.get_filename()
            payload = part.get_payload(decode=True)
            attachments.append({
                "filename": filename,
                "content_type": part.get_content_type(),
                "size": len(payload) if payload else 0,
                "data": payload,
            })
    return attachments

def extract_urls(text: str):
    """Return all http(s) URLs found in `text` (very permissive regex)."""
    return re.findall(r"https?://[\w\-\.\/~%\?=&+#]+", text)

def extract_email_from_text(text: str) -> Optional[str]:
    """Return the first email-like substring found in `text`, or None.

    This is a heuristic; for production consider using a dedicated parser.
    """
    if not text:
        return None
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return m.group(0) if m else None

def extract_phone_from_text(text: str) -> Optional[dict]:
    """Heuristic phone extractor.

    Returns a dict with keys: `raw` (original matched string),
    `number` (normalized local number as int), and `country_code` (int or None).

    Note: This is intentionally simple and will not cover all international formats.
    """
    if not text:
        return None
    # Capture a sequence that looks like a phone number (digits, optional +, spaces/hyphens)
    m = re.search(r"(\+?\d[\d\-\s]{7,}\d)", text)
    if not m:
        return None
    raw = re.sub(r"[^0-9+]", "", m.group(0))
    digits = raw.lstrip("+")
    if len(digits) >= 10:
        # Heuristic: treat last 10 digits as local number, rest as country code
        local = digits[-10:]
        country = digits[: len(digits) - 10] or None
        return {"raw": raw, "number": int(local), "country_code": int(country) if country else None}
    else:
        return {"raw": raw, "number": int(digits), "country_code": None}

def parse_company_id(to_header: str) -> Optional[str]:
    """Extract companyId from a To: header like `SWIGGYCOMPANYID@referral.worko.work`.

    Returns the substring before @referral.worko.work or None.
    """
    if not to_header:
        return None
    m = re.search(r"([A-Za-z0-9_\-]+)@referral\.worko\.work", to_header)
    return m.group(1) if m else None

def generate_id() -> str:
    """Generate an ID for storing files. Prefer ULID if available, otherwise UUID4 hex."""
    if ulid:
        try:
            return str(ulid.new())
        except Exception:
            pass
    return uuid.uuid4().hex

def is_duplicate_firestore(client, company_id: str, email: Optional[str], phone_obj: Optional[dict]) -> bool:
    """Check Firestore for duplicates according to requirements:

    Query matches documents where `companyId==company_id` AND (candidateEmail==email OR
    phoneNumberDetails.number==number AND phoneNumberDetails.countryCode==country).

    If `client` is None function returns False (no-op) to allow processing when Firestore
    isn't available in the runtime.
    """
    if client is None:
        # If Firestore isn't configured, return False to allow processing
        return False
    col = client.collection("corporateCandidateProfiles")
    # Check email match first
    if email:
        q1 = col.where("companyId", "==", company_id).where("candidateEmail", "==", email).limit(1).stream()
        for _ in q1:
            return True
    # Check phone + country code
    if phone_obj and phone_obj.get("number") is not None:
        number = phone_obj.get("number")
        country = phone_obj.get("country_code")
        if country is not None:
            q2 = (
                col.where("companyId", "==", company_id)
                .where("phoneNumberDetails.number", "==", number)
                .where("phoneNumberDetails.countryCode", "==", country)
                .limit(1)
                .stream()
            )
            for _ in q2:
                return True
    return False

def upload_cv_to_s3(bucket: str, company_id: str, file_id: str, data: bytes) -> str:
    """Upload raw CV bytes to S3 using the required path format and return the S3 key.

    Path format: companies/{companyId}/referral-source-cvs/{file_id}.pdf
    """
    key = f"companies/{company_id}/referral-source-cvs/{file_id}.pdf"
    s3 = boto3.client("s3")
    s3.put_object(Bucket=bucket, Key=key, Body=data)
    return key

def send_sqs_message(queue_url: str, body: dict):
    """Send a dict body to SQS as a JSON string."""
    sqs = boto3.client("sqs")
    return sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(body))

def send_ses_email(to_address: str, subject: str, body_text: str,source_email= source_email):
    """Send a simple plain-text email using AWS SES.

    The SES source email can be configured with the `SES_SOURCE_EMAIL` env var.
    """
    ses = boto3.client("ses")
    
    return ses.send_email(
        Source=source_email,
        Destination={"ToAddresses": [to_address]},
        Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body_text}}},
    )

def build_sqs_payload(company_id: str, s3_file_name: str, parsed: dict) -> dict:
    """Compose the SQS payload matching the requirements.md schema (partial fields).

    This returns a dict that will be JSON-serialized by the sender.
    """
    return {"companyId": company_id, "candidateCvAwsS3FileName": s3_file_name, "cvExtractedParsed": parsed}

def process_cv(processed_text: str,OpenAIClient) -> Tuple[str, Dict[str, str]]:
    print("Processing cv for cvexractparesed")

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

    try:

        
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

        cv_extracted_parsed = OpenAIClient.invoke_model_with_backoff(parsed_prompt,Task= "get cvExtractparsed step1 " )
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

        cv_extracted_parsed2 = OpenAIClient.invoke_model_with_backoff(prompt,Task = "get cvExtractparsed step2")
        merged = {**cv_extracted_parsed, **cv_extracted_parsed2}
        
        return merged
        
    except requests.exceptions.HTTPError as e:
        print(" Error occured : from open ai asuure.",e)
        return "Error processing CV"
    except Exception as e:
        print(f"Error processing CV: {str(e)}")
        return "Error processing CV"

def get_verification_link(email_obj):
    body_text = ""
    for part in email_obj.walk():
        if part.get_content_type() == "text/plain":
            body_text = part.get_payload(decode=True).decode(errors="ignore")
            break
    
    lines = body_text.split('\n')
    for i, line in enumerate(lines):
        if "please click the link below to confirm the request:" in line.lower():
            for j in range(i+1, len(lines)):
                if lines[j].strip().startswith('http'):
                    print("Got verification link from email")
                    return lines[j].strip()
    return None

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
import json
import boto3
import os
import re
import ast
import base64
from datetime import datetime
from decimal import Decimal
import fitz
from io import BytesIO
from botocore.exceptions import ClientError
import requests
import random
from typing import Tuple, Dict, Any, Optional, Union
from google.cloud import firestore
from google.oauth2 import service_account
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1 import Or, And
from google import genai
from google.genai import types
from google.oauth2 import service_account
import uuid
from docx import Document
import time
region = 'ap-south-1'
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

class GeminiClient:
    """Client for Google Gemini API with retry logic."""
    
    DEFAULT_TEMPERATURE = 0.3
    DEFAULT_MAX_OUTPUT_TOKENS = 10000
    
    def __init__(self, gcp_credentials: Dict[str, str], env: str, model="gemini-2.5-pro"):
        """Initialize Gemini client.
        
        Args:
            gcp_credentials: Dict containing GCP service account credentials
            env: Environment (dev/staging/prod)
            model: Model name (default: gemini-2.5-pro)
        """
        self.model = model
        self.env = env
        self.project_id = f"worko-{env}"
        self.location = "global"
        
        if not isinstance(gcp_credentials, dict):
            raise TypeError("gcp_credentials must be a dictionary")
        
        # Load credentials
        self.credentials = service_account.Credentials.from_service_account_info(
            gcp_credentials,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        
        # Initialize Google Gen AI client with Vertex AI
        self.client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location=self.location,
            credentials=self.credentials
        )
    
    def clean_and_load(self, raw: str) -> dict:
        """Cleans raw JSON string and loads it into a dictionary."""
        cleaned = re.sub(r"```json|```", "", raw).strip()
        try:
            data = json.loads(cleaned)
            return data
        except json.JSONDecodeError as e:
            print("JSON loading error:", e)
            print("Cleaned JSON (first 500 chars):", cleaned[:500])
            raise ValueError(f"Invalid JSON response from Gemini: {str(e)}") from e
    
    def invoke_model_with_backoff(
        self,
        prompt: str,
        Task="Not specified",
        system_content: str = "You are a helpful assistant.",
        max_retries: int = 10,
        base_delay: int = 2,
        want_json: bool = True
    ) -> Union[str, Dict[Any, Any]]:
        """Invoke model without retry logic - throttling handled at Lambda level.
        
        Args:
            prompt: User prompt
            system_content: System message for the model
            max_retries: Not used (kept for compatibility)
            base_delay: Not used (kept for compatibility)
            want_json: Whether to parse response as JSON
            
        Returns:
            Model response as string or parsed JSON dict
        """
        print("using model :-", self.model)
        print("Task to Ai is :- ", Task)
        return self.invoke_model(system_content, prompt, want_json)
    
    def invoke_model(
        self,
        system_content: str,
        prompt: str,
        want_json: bool = True,
        max_json_retries: int = 3,
        temperature: float = DEFAULT_TEMPERATURE
    ) -> Union[str, Dict[Any, Any]]:
        """Invoke Gemini model.
        
        Args:
            system_content: System message
            prompt: User prompt
            want_json: Whether to parse response as JSON
            max_json_retries: Max retries for JSON parsing
            temperature: Model temperature
            
        Returns:
            Model response as string or parsed JSON dict
        """
        # Build config
        generate_config = types.GenerateContentConfig(
            max_output_tokens=self.DEFAULT_MAX_OUTPUT_TOKENS,
            temperature=temperature,
            system_instruction=system_content if system_content else None,
        )
        
        # Build contents
        contents = [
            types.Content(
                role="user",
                parts=[types.Part(text=prompt)]
            )
        ]
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=generate_config,
        )
        
        response_text = response.text
        input_t = response.usage_metadata.prompt_token_count
        output_t = response.usage_metadata.candidates_token_count
        cached_t = response.usage_metadata.cached_content_token_count or 0
        
        print(f"Token usage details input_tokens :- {input_t}, output_tokens: {output_t}, cached_tokens: {cached_t}")
        
        # Check if response was truncated
        if output_t >= self.DEFAULT_MAX_OUTPUT_TOKENS - 100:
            print(f"WARNING: Response may be truncated (output_tokens: {output_t}, limit: {self.DEFAULT_MAX_OUTPUT_TOKENS})")
        
        if not want_json:
            return response_text
        
        # JSON mode with retries
        for attempt in range(max_json_retries):
            try:
                cleaned = self.clean_and_load(response_text)
                return cleaned
            
            except (json.JSONDecodeError, ValueError) as e:
                remaining = max_json_retries - attempt - 1
                print(f"JSON parse failed. Retries left: {remaining}")
                print(f"Error: {e}")
                
                if remaining == 0:
                    print(f"Raw content (first 500 chars): {response_text[:500]}")
                    print(f"Raw content (last 200 chars): {response_text[-200:]}")
                    raise ValueError(f"Failed to parse JSON after {max_json_retries} attempts: {str(e)}") from e
                
                # Re-invoke model for retry with slightly higher temperature for variation
                retry_config = types.GenerateContentConfig(
                    max_output_tokens=self.DEFAULT_MAX_OUTPUT_TOKENS,
                    temperature=min(temperature + 0.1, 1.0),
                    system_instruction=system_content if system_content else None,
                )
                
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=retry_config,
                )
                response_text = response.text
                print(f"Retry attempt {attempt + 1}: Got new response (output_tokens: {response.usage_metadata.candidates_token_count})")

# class AzureOpenAIClient:
#     """Client for Azure OpenAI API with retry logic."""
    
#     DEFAULT_TEMPERATURE = 0.3
#     DEFAULT_API_VERSION = "2024-05-01-preview"
#     # REQUEST_TIMEOUT = 20  # seconds
    
#     def __init__(self, azure_openai_secret: Dict[str, str],model="gpt-4o"):
        
#         """Initialize Azure OpenAI client.
        
#         Args:
#             azure_openai_secret: Dict containing:
#                 - AZURE_OPENAI_ENDPOINT
#                 - deployment_name
#                 - api_key
#                 - AZURE_OPENAI_API_VERSION (optional)
#         """
#         self.model = model
#         if not isinstance(azure_openai_secret, dict):
#             raise TypeError("azure_openai_secret must be a dictionary")
        
#         self.endpoint = azure_openai_secret.get("AZURE_OPENAI_ENDPOINT", "")
#         self.api_key = azure_openai_secret.get("AZURE_OPENAI_API_KEY", "")
#         if model=="gpt-4o":
#             self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT_gpt-4o", "")
#             self.api_version = azure_openai_secret.get(
#                 "AZURE_OPENAI_API_VERSION_gpt-4o", 
#                 self.DEFAULT_API_VERSION
#             )
#         elif model=="gpt-4.1-mini":
#             self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT_gpt-4.1-mini", "")
#             self.api_version = azure_openai_secret.get(
#                 "AZURE_OPENAI_API_VERSION_gpt-4.1-mini", 
#                 self.DEFAULT_API_VERSION
#             )

        
        
#         # Validate required fields
#         if not all([self.endpoint, self.deployment_name, self.api_key]):
#             raise ValueError(
#                 "Missing required Azure OpenAI configuration: "
#                 "AZURE_OPENAI_ENDPOINT, deployment_name, and api_key are required"
#             )
    
#     def invoke_model_with_backoff(
#         self,
#         prompt: str,
#         Task="Not specified",
#         system_content: str = "You are a helpful assistant.",
#         max_retries: int = 10,
#         base_delay: int = 2,
#         want_json: bool = True
#     ) -> Union[str, Dict[Any, Any]]:
#         """Invoke model with exponential backoff for rate limiting.
        
#         Args:
#             prompt: User prompt
#             system_content: System message for the model
#             max_retries: Maximum number of retry attempts
#             base_delay: Base delay for exponential backoff
#             want_json: Whether to parse response as JSON
            
#         Returns:
#             Model response as string or parsed JSON dict
#         """
#         print("using model :-", self.model)
#         for attempt in range(max_retries):
#             print("Task to Ai is :- ",Task)
#             try:
#                 return self.invoke_model(system_content, prompt, want_json)
            
#             except requests.exceptions.HTTPError as e:
#                 # Check for rate limiting (429) or server errors (5xx)
#                 if e.response.status_code in [500, 502, 503, 504]:
#                     if attempt < max_retries - 1:
#                         delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
#                         print(
#                             f"Rate limit or server error (status {e.response.status_code}). "
#                             f"Retrying in {delay:.2f} seconds..."
#                         )
#                         time.sleep(delay)
#                     else:
#                         raise
#                 else:
#                     # Don't retry for other HTTP errors (auth, not found, etc.)
#                     raise
            
#             except requests.exceptions.RequestException as e:
#                 # Network errors - retry
#                 if attempt < max_retries - 1:
#                     delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
#                     print(f"Network error: {e}. Retrying in {delay:.2f} seconds...")
#                     time.sleep(delay)
#                 else:
#                     raise
    
#     def invoke_model(
#         self,
#         system_content: str,
#         prompt: str,
#         want_json: bool = True,
#         max_json_retries: int = 3,
#         temperature: float = DEFAULT_TEMPERATURE
#     ) -> Union[str, Dict[Any, Any]]:
#         """Invoke Azure OpenAI model.
        
#         Args:
#             system_content: System message
#             prompt: User prompt
#             want_json: Whether to parse response as JSON
#             max_json_retries: Max retries for JSON parsing
#             temperature: Model temperature
            
#         Returns:
#             Model response as string or parsed JSON dict
#         """
#         url = (
#             f"{self.endpoint}/openai/deployments/{self.deployment_name}/"
#             f"chat/completions?api-version={self.api_version}"
#         )
        
#         headers = {
#             "Content-Type": "application/json",
#             "api-key": self.api_key
#         }
        
#         data = {
#             "messages": [
#                 {"role": "system", "content": system_content},
#                 {"role": "user", "content": prompt}
#             ],
#             "temperature": temperature
#         }
        
#         if not want_json:
#             response = requests.post(
#                 url=url, 
#                 headers=headers, 
#                 json=data
                
#             )
#             response.raise_for_status()
#             result = response.json()
#             return result["choices"][0]["message"]["content"]
        
#         # JSON mode with retries
#         for attempt in range(max_json_retries):
#             try:
#                 response = requests.post(
#                     url=url, 
#                     headers=headers, 
#                     json=data
                    
#                 )
#                 response.raise_for_status()
#                 result = response.json()
#                 try :
#                     tokens = result["usage"]
#                     output_tokens= tokens["completion_tokens"]
#                     input_tokens= tokens["prompt_tokens"]
#                     total = tokens["total_tokens"]
#                     print(" Token usage details input_tokens :-",input_tokens,"output_tokens",output_tokens,"total",total)

#                 except Exception as e :
#                     print("errore occured input output token not found :--",e)
                
#                 # Extract and clean content
#                 content = result["choices"][0]["message"]["content"]
#                 content = content.strip()
                
#                 # Remove markdown code blocks
#                 if content.startswith("```"):
#                     content = content.removeprefix("```json").removeprefix("```")
#                     content = content.removesuffix("```").strip()
                
#                 return json.loads(content)
            
#             except json.JSONDecodeError as e:
#                 remaining = max_json_retries - attempt - 1
#                 print(f"JSON parse failed. Retries left: {remaining}")
#                 print(f"Error: {e}")
                
#                 if remaining == 0:
#                     print(f"Raw content: {content}")
#                     raise ValueError(f"Failed to parse JSON after {max_json_retries} attempts") from e
                
#                 time.sleep(2)  # Brief delay before retry
            
#             except (KeyError, IndexError) as e:
#                 print(f"Unexpected response structure: {result}")
#                 raise ValueError("Invalid response format from Azure OpenAI") from e
       

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
        elif model=="gpt-5.2":
            self.endpoint = azure_openai_secret.get("AZURE_OPENAI_ENDPOINT_gpt-5.2", "")
            # Remove trailing slash if present
            if self.endpoint.endswith("/"):
                self.endpoint = self.endpoint.rstrip("/")
            self.api_key = azure_openai_secret.get("AZURE_OPENAI_API_KEY_gpt-5.2", "")
            self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT_gpt-5.2", "")
            self.api_version = azure_openai_secret.get(
                "AZURE_OPENAI_API_VERSION_gpt-5.2", 
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
            
        Returns:RE_OPENAI_API_VERSION_gpt-4.1-mi
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
        url = f"{self.endpoint}/openai/deployments/{self.deployment_name}/chat/completions?api-version={self.api_version}"
        
        headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key
        }
        
        data = {
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt}
            ],
            "max_completion_tokens": 16384
        }
        
        if self.model != "gpt-5.2":
            data["temperature"] = temperature
        
        if not want_json:
            response = requests.post(
                url=url, 
                headers=headers, 
                json=data
                
            )
            response.raise_for_status()
            result = response.json()
            
            # Print token usage for all models
            try:
                tokens = result["usage"]
                output_tokens = tokens["completion_tokens"]
                input_tokens = tokens["prompt_tokens"]
                total = tokens["total_tokens"]
                print(" Token usage details input_tokens :-", input_tokens, "output_tokens :-", output_tokens, "total :-", total)
            except Exception as e:
                print("error occurred input output token not found :--", e)
            
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
                    print(" Token usage details input_tokens :-", input_tokens, "output_tokens :-", output_tokens, "total :-", total)

                except Exception as e :
                    print("errore occured input output token not found :--",e)
                
                # Extract and clean content
                content = result["choices"][0]["message"]["content"]
                content = content.strip()
                
                # Remove markdown code blocks
                if content.startswith("```"):
                    content = content.removeprefix("```json").removeprefix("```")
                    content = content.removesuffix("```").strip()
                
                # Unescape HTML entities
                import html
                content = html.unescape(content)
                
                # Fix formattedHTML field - replace newline+quote pattern
                import re
                content = re.sub(r'"formattedHTML":\s*"[^"]*"\n\s*"[^}]*"', '"formattedHTML": ""', content, flags=re.DOTALL)
                
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

            if cv_obj.get("candidateEmail",""):
                cv_obj["candidateEmail"] = cv_obj["candidateEmail"].lower()

            if cv_obj.get("candidateLocation",""):
                cv_obj["candidateLocation"] = cv_obj["candidateLocation"].lower()
        except Exception as e:
            print(f"Error: -{e} failed to lowercase name and email or Location of cv parsed results : - {cv_obj}")
            return None
        
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

def process_cv(processed_text, gpt_models, gpt5_models, gemini_models) -> Tuple[str, Dict[str, str]]:
    try:
        processed_text = " ".join(processed_text.split())

        if not processed_text:
            print(f"Error : processed_text is not valid {processed_text}")
            return None

        # Prompts
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
            f" -output must always contain candidateName and candidateEmail as it will be always present in given data"
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
        
        current_timestamp = datetime.now().isoformat()
        skills_prompt = (
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
        
        # Try GPT-4 first
        cv_extracted_parsed = None
        cv_extracted_parsed2 = None
        
        try:
            cv_extracted_parsed = gpt_models[1].invoke_model_with_backoff(parsed_prompt, Task="get cvExtractparsed step1")
            cv_extracted_parsed2 = gpt_models[0].invoke_model_with_backoff(skills_prompt, Task="get cvExtractparsed step2")
        except Exception as gpt_error:
            error_message = str(gpt_error).lower()
            if any(term in error_message for term in ['throttling', 'throttled', 'rate limit', 'too many requests', '429']):
                print("GPT-4 throttled, trying GPT-5...")
                try:
                    cv_extracted_parsed = gpt5_models[1].invoke_model_with_backoff(parsed_prompt, Task="get cvExtractparsed step1")
                    cv_extracted_parsed2 = gpt5_models[0].invoke_model_with_backoff(skills_prompt, Task="get cvExtractparsed step2")
                except Exception as gpt5_error:
                    gpt5_error_message = str(gpt5_error).lower()
                    if any(term in gpt5_error_message for term in ['throttling', 'throttled', 'rate limit', 'too many requests', '429']):
                        print("GPT-5 throttled, trying Gemini...")
                        try:
                            cv_extracted_parsed = gemini_models[1].invoke_model_with_backoff(parsed_prompt, Task="get cvExtractparsed step1")
                            cv_extracted_parsed2 = gemini_models[0].invoke_model_with_backoff(skills_prompt, Task="get cvExtractparsed step2")
                        except Exception as gemini_error:
                            gemini_error_message = str(gemini_error).lower()
                            if any(term in gemini_error_message for term in ['throttling', 'throttled', 'rate limit', 'quota', 'resource exhausted', '429']):
                                print("Gemini throttled, sending to retry SQS...")
                                raise
                            else:
                                print(f"Gemini error (non-throttle): {gemini_error}")
                                return None
                    else:
                        print(f"GPT-5 error (non-throttle): {gpt5_error}")
                        return None
            else:
                print(f"GPT-4 error (non-throttle): {gpt_error}")
                return None
        
        if cv_extracted_parsed and cv_extracted_parsed2:
            merged = {**cv_extracted_parsed, **cv_extracted_parsed2}
            merged = process_parsed_cv_json(merged)
            if merged :
                return merged
            else:
                return "Failed"

                
        else:
            return None

    except Exception as execution_error:
        error_message = str(execution_error).lower()
        if any(term in error_message for term in ['throttling', 'throttled', 'rate limit', 'too many requests', '429', 'quota', 'resource exhausted']):
            raise
        else:
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

def send_sqs_for_throttling_error(retry_queue_name, s3_record, retry_counter, delay_seconds):
    try:
        queue_url = get_queue_url(retry_queue_name)
        sqs = boto3.client('sqs')
        
        # Prepare body in correct format matching the example event structure
        body = {
            "retry_counter": retry_counter,
            "eventType": "RetrySQS",
            "records": [s3_record]
        }
        
        print(f"Sending message to SQS with retry_counter: {retry_counter}")
        print(f"[SQS SEND] DelaySeconds: {delay_seconds}")
        print(f"SQS message body for throttled steps: {json.dumps(str(body)[:200])}")
        
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

def get_meta_data(bucket,key):
    s3_client = boto3.client('s3')

    # Extract bucket and key from event
    # bucket = event['Records'][0]['s3']['bucket']['name']
    # key = event['Records'][0]['s3']['object']['key']
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
    # to_address = "shaukatdatascience@gmail.com"
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
    writer.writerow(["", "", ""])
    
    # UNPROCESSED_LARGE_FILES section
    if "UNPROCESSED_LARGE_FILES" in summary:
        writer.writerow(["UNPROCESSED_LARGE_FILES", f"Count: {summary['UNPROCESSED_LARGE_FILES']['count']}", ""])
        writer.writerow(["File Name", "", ""])
        for filename in summary['UNPROCESSED_LARGE_FILES']['files']:
            writer.writerow([filename, "", ""])
        writer.writerow(["", "", ""])
    
    csv_content = csv_buffer.getvalue()
    
    subject = "Bulk CV Processing Complete - Summary Report"
    
    # Build email body with unprocessed files info
    unprocessed_info = ""
    if "UNPROCESSED_LARGE_FILES" in summary:
        unprocessed_info = f"\nUnprocessed Large Files: {summary['UNPROCESSED_LARGE_FILES']['count']}"
    
    body_text = f"""Dear User,

Your bulk CV upload has been successfully processed.

Processing Summary:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total CVs Uploaded: {total_count}
Successfully Processed: {summary['SUCCESS']['count']}
Failed: {summary['FAILED']['count']}
Duplicates Detected: {summary['DUPLICATE']['count']}{unprocessed_info}
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

def has_key_elements(text, key_elements, threshold):
    present_elements = sum(1 for element in key_elements if text.get(element, ""))
    return present_elements >= threshold

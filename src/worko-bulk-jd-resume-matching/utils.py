import boto3
import json
import time
from botocore.exceptions import ClientError
from google.oauth2 import service_account
import google.auth.transport.requests
# from google import genai
# from google.genai import types #
import requests
from typing import Tuple, Dict, Any, Optional, Union
import random ####

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
        
def call_GCP_models(prompt, service_account_info,want_json=True, max_try_for_json=1, thinking_mode=False, thinking_budget=None):
    # 1. Service account JSON path
    # SERVICE_ACCOUNT_FILE = r"C:\Users\Administrator\Desktop\worko_working\worko_code_chainged_files\vertex-sa.json"

    # 2. Load and refresh credentials
    credentials = service_account.Credentials.from_service_account_info(
    service_account_info,
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    # credentials = service_account.Credentials.from_service_account_file(
    #     SERVICE_ACCOUNT_FILE,
    #     scopes=["https://www.googleapis.com/auth/cloud-platform"]
    # )
    credentials.refresh(google.auth.transport.requests.Request())

    # 3. Prepare API endpoint
    project_id = "worko-dev"
    location = "us-central1"
    model_name = "gemini-1.5-pro-002"

    url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/publishers/google/models/{model_name}:generateContent"

    # 4. Prepare headers and payload
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json"
    }

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 5000,
            "temperature": 0.7,
            "responseMimeType": "application/json" if want_json else "text/plain",
            "thinkingConfig": {
                "mode": "THINKING_MODE_ENABLED",
                "thinkingBudget": thinking_budget
            } if thinking_mode and thinking_budget else {"mode": "THINKING_MODE_ENABLED"} if thinking_mode else {}
        }
    }

    # 5. Make API call
    try:
        if not want_json:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()  # Raise exception for bad status codes
            result = response.json()
            
            inpute = result["usageMetadata"]["promptTokenCount"]
            output = result["usageMetadata"]["candidatesTokenCount"] + result["usageMetadata"]["thoughtsTokenCount"]
            print("inpute tokens:- ",inpute,"Output tokens",output)
            response = result['candidates'][0]['content']['parts'][0]['text']
            print(response)
            return response

        for attempt in range(max_try_for_json):
            try:
                response = requests.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                text_response = result['candidates'][0]['content']['parts'][0]['text']
                text_response = text_response.strip().removeprefix("```json").removesuffix("```").strip()
                json_result = json.loads(text_response)
                print(json_result)
                return json_result
            except Exception as e:
                remaining = max_try_for_json - attempt - 1
                print(f"JSON parse failed. Retries left: {remaining}")
                print("Error:", e)
                time.sleep(5)
                if remaining == 0:
                    raise
    except requests.exceptions.RequestException as e:
        print(f"Error occured : {e}")
        return f"Error occured : {e}"
        # print(f"Response: {response.usageMetadata}")

class AzureOpenAIClient:
    """Client for Azure OpenAI API with retry logic."""
    
    DEFAULT_TEMPERATURE = 0.3
    DEFAULT_API_VERSION = "2024-05-01-preview"
    REQUEST_TIMEOUT = 30  # seconds
    
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
         
        
# env = "dev"
# GCP_secret_name = "GCP-aiplatform-secrect-"+env
# service_account_info = get_secret(GCP_secret_name)
# # print(service_account_info)
# prompt  = "write a prince story of taj mahal"
# response = call_GCP_models(prompt,service_account_info,want_json=False)
# print(response)
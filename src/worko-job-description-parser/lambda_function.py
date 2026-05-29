import json
import ast
import boto3
import re
import os
from datetime import datetime
from decimal import Decimal
import time
start_time = time.time()
from botocore.exceptions import ClientError
import anthropic
from google.oauth2 import service_account

from google import genai
from google.genai import types

import requests
from typing import Tuple, Dict, Any, Optional, Union
# Initialize Bedrock clients
region = 'ap-south-1'
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client(service_name='bedrock', region_name = region)
bedrock_runtime = boto3.client(service_name='bedrock-runtime', region_name = region)

import sys
from pathlib import Path

if __name__ == "__main__":
    shared_layer_path = Path(__file__).parent.parent / "shared-core-layer"
    sys.path.insert(0, str(shared_layer_path))
from ai_clients.gcp_client import GeminiClient

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
         
                  
def get_secret(secret_name):
    secrets_client = boto3.client('secretsmanager', region_name='ap-south-1')
    """
    Retrieve individual secrets from AWS Secrets Manager using the get_secret_value API.
    This function assumes the stack mentioned in the source code README has been successfully deployed.
    This stack includes 7 secrets, all of which have names beginning with "mySecret".

    :param secret_name: The name of the secret fetched.
    :type secret_name: str
    """
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret_value = response['SecretString']
        
        # Try to parse as JSON, fallback to string
        try:
            secret_data = json.loads(secret_value)
        except json.JSONDecodeError:
            secret_data = secret_value
        return secret_data
        # return {
        #     "statusCode": 200,
        #     "body": json.dumps({
        #         "secret_name": secret_name,
        #         "secret_value": secret_data
        #     })
        # }
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return {
                "statusCode": 404,
                "body": json.dumps({"error": f"Secret '{secret_name}' not found"})
            }

def call_gemini_pro(prompt, creds, env, max_json_try=3, want_json=True, system_prompt=None):
    PROJECT_ID = "worko-" + env
    LOCATION = "global"

    # Load credentials
    credentials = service_account.Credentials.from_service_account_info(
        creds,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    # Initialize Google Gen AI client with Vertex AI
    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION,
        credentials=credentials
    )

    model = "gemini-2.5-pro"  

    # Build config
    generate_config = types.GenerateContentConfig(
        max_output_tokens=5000,
        temperature=0.3,
        system_instruction=system_prompt if system_prompt else None,
    )

    # Build contents
    contents = [
        types.Content(
            role="user",
            parts=[types.Part(text=prompt)]
        )
    ]

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=generate_config,
    )

    response_text = response.text
    input_t = response.usage_metadata.prompt_token_count
    output_t = response.usage_metadata.candidates_token_count
    cached_t = response.usage_metadata.cached_content_token_count or 0

    print(f"Input tokens: {input_t}, Output tokens: {output_t}, Cached Tokens: {cached_t}")

    if not want_json:
        return response_text
    else:
        for i in range(max_json_try):
            try:
                cleaned = clean_and_load(response_text)
                return cleaned
            except json.JSONDecodeError as e:
                print(f"JSONDecodeError on attempt {i+1}: {e}")
                continue
            except Exception as e:
                print(f"Unexpected error on attempt {i+1}: {e}")
                continue
        return None

def clean_and_load(raw: str) -> dict:
    """
    Cleans a raw JSON string that may contain ```json ... ``` wrappers
    and loads it into a Python dictionary.
    """
    # 1. Remove ```json or ``` wrappers using regex
    cleaned = re.sub(r"```json|```", "", raw).strip()

    # 2. Ensure it's valid JSON and load
    try:
        data = json.loads(cleaned)
        return data
    except json.JSONDecodeError as e:
        print("JSON loading error:", e)
        print("Cleaned JSON:", cleaned)
        return None

def call_sonnet4(prompt,creds, env,max_json_try=3, want_json=True, system_prompt=None):  # ← Add system_prompt parameter
    PROJECT_ID = "worko-"+ env
    LOCATION="global"
    # SERVICE_ACCOUNT_FILE = r"C:\Users\Administrator\Desktop\worko_working\worko_code_chainged_files\vertex-sa.json"

    # Load credentials
    credentials = service_account.Credentials.from_service_account_info(
        creds,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    # Initialize Anthropic client with Vertex AI
    client = anthropic.AnthropicVertex(
        project_id=PROJECT_ID,
        region=LOCATION,
        credentials=credentials
    )
    # model="claude-sonnet-4-5@20250929"
    model="claude-sonnet-4@20250514"
    
    # Build request
    request_params = {
        "model": model,
        "max_tokens": 5000,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    # ← ADD THIS BLOCK
    if system_prompt:
        request_params["system"] = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"}
            }
        ]
    # ← END OF NEW BLOCK
    
    response = client.messages.create(**request_params)  # ← Change this line to use **request_params

    if not want_json:
        input_t = response.usage.output_tokens 
        output_t  = response.usage.input_tokens
        cache_read_input_tokens  = response.usage.cache_read_input_tokens
        
        print(f"Input tokens: {input_t}, Output tokens: {output_t}, cashed Token {cache_read_input_tokens}")
        return response.content[0].text
    else:
        for i in range(max_json_try):
            try:
                input_t = response.usage.output_tokens 
                output_t  = response.usage.input_tokens
                cache_read_input_tokens  = response.usage.cache_read_input_tokens

                print(f"Input tokens: {input_t}, Output tokens: {output_t}, cashed Token {cache_read_input_tokens}")
                response = response.content[0].text
                response = clean_and_load(response)
                return response
            except json.JSONDecodeError as e:
                print(f"JSONDecodeError on attempt {i+1}: {e}")
                continue
            except Exception as e:
                print(f"Unexpected error on attempt {i+1}: {e}")
                continue
        return None

def invoke_model(prompt):
    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 10000,
            "temperature": 0.3,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            ]
        })

        modelId = "arn:aws:bedrock:us-east-1:211125353899:inference-profile/us.anthropic.claude-sonnet-4-20250514-v1:0"

        response = bedrock_runtime.invoke_model(
            body=body,
            modelId=modelId,
            accept='*/*',
            contentType='application/json'
        )

        # Parse the Bedrock envelope
        model_output = json.loads(response['body'].read())
        llm_text = model_output.get("content", [{}])[0].get("text", "").strip()

        if not llm_text:
            raise ValueError("Model returned empty text.")

        # Extract JSON from code block if present
        json_match = re.search(r'```json\s*(.*?)\s*```', llm_text, re.DOTALL)
        json_str = json_match.group(1).strip() if json_match else llm_text.strip()

        if not json_str:
            raise ValueError("No JSON found in model output.")

        # Clean control chars
        json_str = re.sub(r'[\x00-\x1F\x7F]', '', json_str)

        return json.loads(json_str)

    except Exception as e:
        print("Unexpected error:", str(e))
        return {"error": f"Unexpected error: {str(e)}"}

def invoke_model_with_backoff_nova(prompt, max_retries=10, base_delay=2):
    for attempt in range(max_retries):
        try:
            return invoke_model_nova(prompt)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < max_retries - 1:
                delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                print(f"Throttling occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                raise


    bedrock_runtime = boto3.client(service_name='bedrock-runtime', region_name = "ap-south-1")
    body = json.dumps({
        "inferenceConfig": {
            "max_new_tokens": 5000
        },
        "messages": [
            {
                "role": "user", 
                "content": [
                    {
                        "text": prompt  # Wrap the prompt in a text dictionary
                    }
                ]
            }
        ]
    })
    
    # modelId= "amazon.nova-pro-v1:0"
    modelId= "arn:aws:bedrock:ap-south-1:211125353899:inference-profile/global.amazon.nova-2-lite-v1:0"
    print("modelId ------", modelId)

    response = bedrock_runtime.invoke_model(
        body=body,
        modelId=modelId,
        contentType='application/json',
        accept='application/json'
    )   
    response_body = json.loads(response['body'].read())    
    inputTokens = response_body["usage"]["inputTokens"]
    outputTokens = response_body["usage"]["outputTokens"]
    totalTokens = response_body["usage"]["totalTokens"]
    usage = {"inputTokens":inputTokens,
        "outputTokens":outputTokens,
        "totalTokens":totalTokens}
    return response_body["output"]["message"]["content"][0]["text"],usage

def extract_text_from_nova(cv_content):
    try:
        # Parse the JSON string
        # data = json.loads(cv_content.replace("'", '"'))
        
        # Extract the text from the parsed JSON
        extracted_text = cv_content['output']['message']['content'][0]['text']
        
        # Print the extracted text
        return extracted_text
        
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
    except KeyError as e:
        print(f"Error accessing key in JSON structure: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def load_ai_json(response):
    try:
        # Remove markdown code blocks if present
        if '```' in response:
            # Extract content between ```json and ``` or ``` and ```
            match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL)
            if match:
                response = match.group(1)
        
        # Strip whitespace
        if type(response)==str:
            response = response.strip()
        
            # Remove outer quotes if the entire JSON is wrapped in quotes
            if response.startswith('"') and response.endswith('"'):
                response = response[1:-1]
                # Unescape the string
                response = response.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')
        
        # Parse JSON
        return json.loads(response)
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON: {str(e)}")
    except Exception as e:
        raise ValueError(f"Error loading JSON: {str(e)}")

    
    if isinstance(obj, dict):
        cleaned = {}
        for key, value in obj.items():
            cleaned_value = clean_json_values(value)
            # Optionally keep empty strings or convert to None
            # Comment out the next line if you want to keep empty strings
            # if cleaned_value == "":
            #     cleaned_value = None
            cleaned[key] = cleaned_value
        return cleaned
        
    elif isinstance(obj, list):
        return [clean_json_values(item) for item in obj]
        
    elif isinstance(obj, str):
        # Trim whitespace
        return obj.strip()
        
    else:
        # Return primitive values as-is
        return obj

def lambda_handler(event, context):
    print(event)
    env = os.environ.get("ENVIRONMENT","dev")
    
    GCP_secret_name = "GCP-firestore-secret-"+env
    print(GCP_secret_name)

    job_desc = event.get('JOB_DESC', "")
    job_desc = re.sub(r'[\x00-\x1F\x7F]', '', job_desc)  # Remove control characters
    job_desc = re.sub(r'<[^>]+>', '', job_desc)  # Remove HTML tags
    job_desc = re.sub(r'&nbsp;', ' ', job_desc)  # Replace HTML space entity with a space
    job_desc = re.sub(r'\s+', ' ', job_desc).strip()  # Normalize spaces and trim

    print ("Job description",job_desc)
    end_time = time.time()

    print(f"step 1 received and preporcessede the job description time took :- {end_time-start_time}")
     
    # old prompt
    prompt = (
        f"**JOB DESCRIPTION EXTRACTION TASK**\n\n"
        
        f"**STEP 1 - Extract Basic Information:**\n"
        f"- Job Title\n"
        f"- Salary Range (Minimum and Maximum)\n"
        f"- Experience Range (Minimum and Maximum)\n"
        f"- Number of Openings\n"
        f"- Work Mode (WFH, WFO, HYBRID)\n"
        f"- Location\n"
        f"- Notice Period (Days)(Enter a numeric value. If a range is provided, use the higher value.)\n"
        f"- Type of Employment\n"
        f"- Department\n"
        f"- Core Skills (Each skill must be a maximum of 30 characters)\n"
        f"- Soft Skills (Each skill must be a maximum of 30 characters)\n"
        f"- Technical Skills (Include only IT skills as Technical Skill. Each skill must be a maximum of 30 characters)\n"
        f"- Good to Have Skills (Each skill must be a maximum of 30 characters)\n"
        f"- Must Have Skills (These are skills explicitly mentioned as 'must have' in the job description. Each skill must be a maximum of 30 characters)\n"
        f"- Mandatory Requirements (Identify all MANDATORY requirements in the job description - look for terms like \"required,\" \"must have,\" \"X years in [specific industry]\")\n"
        f"- Preferred Requirements (Identify all PREFERRED/NON-MANDATORY experience requirements - look for terms like \"preferred,\" \"nice to have,\" \"desirable\")\n\n"

        f"**STEP 2 - CRITICAL SKILL CLASSIFICATION RULES:**\n"
        f"**CORE SKILLS = Functional/Domain Expertise ONLY**\n"
        f"-INCLUDE in coreSkills: Specific job functions, domain knowledge, industry expertise\n"
        f"-Examples: 'Category Management', 'Supplier Relations', 'E-commerce Operations', 'Revenue Management', 'Market Research'\n"
        f"-EXCLUDE from coreSkills: Management abilities, thinking skills, interpersonal skills\n"
        f"-Examples: 'Team Leadership', 'Strategic Planning', 'Goal Setting', 'Performance Management', 'Stakeholder Management'\n\n"
        
        f"**SOFT SKILLS = Behavioral/Interpersonal Abilities**\n"
        f"-INCLUDE in softSkills: How you work, think, and interact\n"
        f"-Examples: 'Leadership', 'Communication', 'Strategic Thinking', 'Problem Solving', 'Team Management', 'Decision Making'\n\n"
        
        f"**TECHNICAL SKILLS = Tools/Software/Platforms**\n"
        f"INCLUDE in technicalSkills: Specific tools, software, platforms, systems\n"
        f"Examples: 'Microsoft Excel', 'CRM Systems', 'Analytics Tools', 'Database Management'\n\n"
        
        f"**MANDATORY SKILL MOVEMENT RULES:**\n"
        f"- 'Team Leadership' → softSkills (NOT coreSkills)\n"
        f"- 'Strategic Planning' → softSkills (NOT coreSkills)\n"
        f"- 'Stakeholder Management' → softSkills (NOT coreSkills)\n"
        f"- 'Goal Setting' → softSkills (NOT coreSkills)\n"
        f"- 'Performance Management' → softSkills (NOT coreSkills)\n"
        f"- 'Data Analysis' → technicalSkills if tool-based, softSkills if analytical thinking\n"
        f"- 'Process Development' → softSkills (NOT coreSkills)\n"
        f"- 'Problem Resolution' → softSkills (NOT coreSkills)\n"
        f"- 'Business Development' → coreSkills (NOT softSkills)\n"
        f"- 'Financial Analysis' → coreSkills (NOT technicalSkills)\n"
        f"- 'Market Research' → coreSkills (NOT softSkills)\n"
        f"- 'Sales Strategy' → coreSkills (NOT softSkills)\n"
        f"- 'Programming Languages (Python, Java, etc.)' → technicalSkills (NOT coreSkills)\n"
        f"- 'Cloud Platforms (AWS, Azure, GCP)' → technicalSkills (NOT coreSkills)\n"
        f"- 'Version Control (Git, SVN)' → technicalSkills (NOT coreSkills)\n"
        f"- 'Database Design/SQL' → technicalSkills (NOT coreSkills)\n"
        f"- 'Project Management' → softSkills (NOT coreSkills)\n"
        f"- 'Communication Skills' → softSkills (NEVER coreSkills or technicalSkills)\n"
        f"- 'Excel/Power BI/Visualization Tools' → technicalSkills (NOT coreSkills)\n"
        f"- 'Customer Relationship Management (CRM)' → technicalSkills (NOT coreSkills)\n\n"
        
        f"**STEP 3 - MANDATORY vs PREFERRED REQUIREMENTS:**\n"
        f"**Mandatory Requirements:** Look for exact phrases:\n"
        f"- 'Required', 'Must have', 'Necessary', 'Essential'\n"
        f"- Items under 'Requirements', 'Mandatory Requirements', 'Essential Criteria'\n"
        f"- Education requirements (BE/B.Tech Graduate)\n"
        f"- Experience requirements with specific years\n\n"
        
        f"**Preferred Requirements:** Look for exact phrases:\n"
        f"- 'Preferred', 'Nice to have', 'Desirable', 'Good to have'\n"
        f"- Items under 'Preferred Qualifications', 'Additional Skills'\n"
        f"- 'Experience with X is an added advantage'\n\n"
        
        f"**STEP 4 - MUST HAVE vs GOOD TO HAVE SKILLS:**\n"
        f"- mustHaveSkills: Extract skills from mandatory requirements\n"
        f"- goodToHaveSkills: Extract skills from preferred requirements\n\n"
        
        f"**STEP 5 - FINAL VALIDATION (CRITICAL):**\n"
        f"Before generating JSON, perform these checks:\n"
        f"1. Scan coreSkills - remove ANY management/leadership/planning skills\n"
        f"2. Move removed skills to softSkills\n"
        f"3. Check for duplicates across all skill arrays - remove duplicates\n"
        f"4. Ensure each skill is in ONLY ONE category\n"
        f"5. Verify coreSkills contains ONLY functional/domain expertise\n"
        f"6. keep only 20 most relavant skills with respect to job description in each catagory of skills\n"
        f"7. for Salary Range and Experience Range if min is given but max is not then don't put any value in max if both are not given do not return this entire field\n"
        f"8. Remove any redundaundt or repeating data\n\n"
        
        f"**EMPTY FIELD RULE:**\n"
        f"- If information is not explicitly mentioned, leave field empty (not 'Not Mentioned')\n\n"
        
        f"**OUTPUT FORMAT:**\n"
        f"Return ONLY the JSON structure below with extracted values:\n\n"
        '{\n'
        '    "jobTitle": "",\n'
        '    "salaryRange": {"min": "", "max": ""},\n'
        '    "experienceRange": {"min": "", "max": ""},\n'
        '    "numberOfOpenings": "",\n'
        '    "workMode": "",\n'
        '    "location": "",\n'
        '    "noticePeriod": "",\n'
        '    "typeOfEmployment": "",\n'
        '    "department": "",\n'
        '    "coreSkills": [],\n'
        '    "softSkills": [],\n'
        '    "technicalSkills": [],\n'
        '    "goodToHaveSkills": [],\n'
        '    "mustHaveSkills": [],\n'
        '    "mandatoryRequirements": [],\n'
        '    "preferredRequirements": [],\n'
        '    "formattedHTML":  "<div>\\n"\n'
                '        "<section>\\n"\n'
                '        "<h2>Company Overview</h2>\\n"\n'
                '        "<p>[Company information from job description]</p>\\n"\n'
                '        "</section>\\n"\n'
                '        "<section>\\n"\n'
                '        "<h2>Role Overview</h2>\\n"\n'
                '        "<p>[Role information from job description]</p>\\n"\n'
                '        "</section>\\n"\n'
                '        "<section>\\n"\n'
                '        "<h2>Key Responsibilities</h2>\\n"\n'
                '        "<ul>\\n"\n'
                '        "[List of responsibilities from job description]\\n"\n'
                '        "</ul>\\n"\n'
                '        "</section>\\n"\n'
                '        "<section>\\n"\n'
                '        "<h2>Requirements</h2>\\n"\n'
                '        "<ul>\\n"\n'
                '        "[List of requirements from job description]\\n"\n'
                '        "</ul>\\n"\n'
                '        "</section>\\n"\n'
                '        "<section>\\n"\n'
                '        "<h2>Mandatory Requirements</h2>\\n"\n'
                '        "<ul>\\n"\n'
                '        "[List of mandatory requirements from job description]\\n"\n'
                '        "</ul>\\n"\n'
                '        "</section>\\n"\n'
                '        "<section>\\n"\n'
                '        "<h2>Preferred Requirements</h2>\\n"\n'
                '        "<ul>\\n"\n'
                '        "[List of preferred requirements from job description]\\n"\n'
                '        "</ul>\\n"\n'
                '        "</section>\\n"\n'
                '        "<section>\\n"\n'
                '        "<h2>Additional Information</h2>\\n"\n'
                '        "<p>[Additional details from job description]</p>\\n"\n'
                '        "</section>\\n"\n'
                '        "</div>"\n'
                '}'
        
            )

    dynamic_prompt=f"Parse this JD:\n{job_desc}"



    AZURE_secret_name = "AZURE-openai-secret-multimodel-"+env
    azure_secret = get_secret(AZURE_secret_name)
    gpt52_client = AzureOpenAIClient(azure_secret, model="gpt-5.2")

    
    GCP_secret_name ="GCP-aiplatform-secrect-"+env
    gcp_credentials = get_secret(GCP_secret_name)
    gcp = GeminiClient(gcp_credentials,env)


    try:
        # response = gpt52_client.invoke_model_with_backoff(
        #     prompt=dynamic_prompt,
        #     Task="Extract JD info from gpt 5.2",
        #     system_content=prompt,
        #     want_json=True
        # )
        response = gcp.invoke_model_with_backoff(dynamic_prompt, Task="parse the job description", system_content=prompt,want_json=True,)
    except Exception as e:
        print(f"Error in calling AI: {e}")
        response = {"error": str(e)}

    # response = call_sonnet4(prompt=dynamic_prompt,creds = credentials,env=env,max_json_try=3, want_json=True, system_prompt=prompt)
    # response = clean_and_load(content)
    end_time = time.time()
    print(f"step 2 invoked ai and got response time took :- {end_time-start_time}")

    print("Response 2:", response)

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(response)  # Convert the dictionary to a JSON string
    }

if __name__ == "__main__":
    event = {'JOB_DESC': 'Job Title: Full Stack Developer (React.js | Node.js | AWS)\n\nDepartment: Engineering / Technology\n\nRole: Full Stack Web Developer\n\nJob Description:\n\nWe are seeking a results-driven and detail-oriented Full Stack Web Developer with proven experience in architecting, building, deploying, and maintaining high-performance web applications. The ideal candidate will demonstrate deep expertise in modern JavaScript frameworks, RESTful APIs, cloud-native services, and scalable system design. This role requires strong problem-solving skills, hands-on coding experience, and a passion for clean, maintainable code.\n\nKey Responsibilities:\n\nDesign and implement full stack solutions using React.js, Node.js, Express.js, and MongoDB, following agile software development practices.\n\nLead the migration from Angular to React using modular design principles, creating reusable components, custom hooks, and scalable context-based state management.\n\nDevelop and maintain high-performance REST APIs and backend services with Express.js, integrating business logic and authentication workflows using JWT, OAuth 2.0, and AWS Cognito.\n\nArchitect microfrontend-based systems and build proxy applications for seamless coexistence of legacy and new systems, leveraging AWS CloudFront.\n\nIntegrate and optimize third-party services (e.g., Razorpay) and ensure real-time synchronization of transactional and user data.\n\nImplement CMS functionalities, including dynamic dashboards, job posting systems, PDF parsing with pdfjs-dist, and rich text editing using Quill.\n\nEstablish CI/CD pipelines with AWS CodeCatalyst, ensure test coverage using Postman and Jest, and deploy infrastructure with high reliability.\n\nUtilize AWS SES, CloudWatch, and DynamoDB to manage emails, monitor logs, and handle NoSQL storage with Dynamoose ORM.\n\nImprove SEO and web accessibility through dynamic meta tag generation and performance optimization techniques.\n\nLead code reviews, enforce clean code standards, and mentor junior developers in a collaborative, fast-paced environment.\n\nRequired Skills:\n\nFrontend: React.js, React Hook Form, React Query, Context API, SCSS, Tailwind CSS, Bootstrap\n\nBackend: Node.js, Express.js, MVC architecture\n\nCloud & DevOps: AWS Cognito, AWS SES, AWS CloudFront, CloudWatch, CodeCatalyst\n\nDatabases: MongoDB, DynamoDB (Dynamoose)\n\nAuthentication & Security: JWT, OAuth 2.0, role-based access control\n\nAPI Development & Integration: REST APIs, Razorpay, FIX API\n\nTesting: Postman (manual & integration), Jest (unit testing)\n\nVersion Control: Git, GitHub, Git-Bash\n\nPreferred Skills:\n\nMicrofrontend Architecture and Modular Component Design\n\nExperience with FIX API and algorithmic trading environments\n\nBuilding LLM-based applications (e.g., GPT Clone, Mythomist-7B via OpenRoute)\n\nSEO optimization, accessibility standards, and Lighthouse performance improvements\n\nWorking knowledge of legacy frameworks like Angular for transitional projects\n\nEducation:\n\nMaster of Computer Applications – Centre for Development of Advanced Computing\n\nBachelor of Computer Applications – Jamia Hamdard University\n\nCertifications:\n\nAWS Certified Cloud Practitioner (preferred)\n\nFull Stack Web Development (React, Node.js, MongoDB) (preferred)\n\nJavaScript and ES6+ Advanced Programming (optional but relevant)\n\nEmployment Type: Full-time\nExperience Level: 2–4 years\nLocation: Remote / Bangalore / Delhi NCR\nIndustry: SaaS / Product Development / Technology / FinTech / EdTech'}
    lambda_handler(event, None)
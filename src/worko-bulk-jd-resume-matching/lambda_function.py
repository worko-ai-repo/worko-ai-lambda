import json
import boto3
import os
import time
import re
import requests
from decimal import Decimal
from datetime import datetime
import botocore
import random
import string
from typing import Tuple, Dict, Any, Optional, Union
import sys
from pathlib import Path
import base64

# Add shared-core-layer to path for local testing
if __name__ == "__main__":
    shared_layer_path = Path(__file__).parent.parent / "shared-core-layer"
    sys.path.insert(0, str(shared_layer_path))

# Import from shared-core-layer
# from ai_clients import AzureOpenAIClient
from ai_clients.gcp_client import GeminiClient
from parsers import extract_text_from_pdf, extract_text_from_docx

from utils import (
    get_secret,
    get_account_id,
    query_dynamodb_item_with_sk_prefix,
    clean_text,
    extract_images_from_pdf,
    invoke_claude_with_image,
    process_cv,
    jd_resume_matching,
    update_ref_response_in_dynamodb_for_bulk_process
)

# Initialize the AWS service clients
region = 'us-east-1'
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')
bedrock_runtime = boto3.client('bedrock-runtime', region_name=region)
sqs = boto3.client('sqs')
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
        
        return cv_obj
    except Exception as e:
        print(f"Error processing parsed CV JSON: {e}")
        return cv_obj

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            else:
                return float(obj)
        return super(DecimalEncoder, self).default(obj)

def generate_random_string(length):
    return ''.join(random.choices(string.digits, k=length))

def safe_int(value):
    match = re.findall(r'\d+', str(value))
    return match[0] if match else ""

from decimal import Decimal

def convert_numbers_to_decimal(obj):
    """
    Recursively converts ONLY int and float values to Decimal.
    Prevents ConversionSyntax by ignoring strings like '9 years'.
    """
    if isinstance(obj, dict):
        return {k: convert_numbers_to_decimal(v) for k, v in obj.items()}

    elif isinstance(obj, list):
        return [convert_numbers_to_decimal(item) for item in obj]

    # convert ONLY real int/float types
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        return Decimal(str(obj))

    else:
        return obj


def query_dynamodb_item_without_sk_prefix(table_name, partition_key_value, sort_key_prefix, cloud_file_name):
    table = dynamodb.Table(table_name)
    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(partition_key_value) &
                               boto3.dynamodb.conditions.Key('SK').begins_with(sort_key_prefix),
        FilterExpression=boto3.dynamodb.conditions.Attr('cloudFileName').eq(cloud_file_name)
    )
    items = response.get('Items')
    if items:
        return items[0]
    return None

def query_with_retry(table_name, partition_key_value, sort_key_prefix, file_name, max_retries=3, delay=1):
    """
    Query DynamoDB with automatic retry functionality.
    
    Args:
        table_name: The DynamoDB table name
        partition_key_value: The partition key value to query
        sort_key_prefix: The sort key prefix to filter by
        file_name: The cloud file name to look for
        max_retries: Maximum number of retry attempts (default: 3)
        delay: Delay between retries in seconds (default: 1)
        
    Returns:
        The found item or None if not found after all retries
    """
    
    for attempt in range(max_retries + 1):
        # Call your existing query function
        item = query_dynamodb_item_without_sk_prefix(
            table_name, 
            partition_key_value, 
            sort_key_prefix, 
            file_name
        )
        
        if item is not None:
            return item
        
        if attempt < max_retries:
            # Log the retry attempt
            print(f"Attempt {attempt + 1} failed, retrying in {delay} seconds...")
            time.sleep(delay)
            # Optional: Implement exponential backoff by multiplying delay by a factor
            delay = delay * 2
    
    # If we get here, all retries failed
    print(f"Failed to retrieve item after {max_retries + 1} attempts")
    return None

def create_prompt(cv_extract, job_desc, step ):
    return f'Human:\nResume:\n{cv_extract}\nJob Description:\n{job_desc}\n{step}'

def invoke_model_with_backoff_claude(prompt, max_retries=10, base_delay=2):
    for attempt in range(max_retries):
        try:
            return invoke_model_claude(prompt)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < max_retries - 1:
                delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                print(f"Throttling occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                raise

def invoke_model_with_backoff_deepseek(prompt, max_retries=10, base_delay=2):
    for attempt in range(max_retries):
        try:
            return invoke_model_deepseek(prompt)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < max_retries - 1:
                delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                print(f"Throttling occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                raise

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

def invoke_model_with_backoff_nova_lite(prompt, max_retries=10, base_delay=2):
    for attempt in range(max_retries):
        try:
            return invoke_model_nova_lite(prompt)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < max_retries - 1:
                delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                print(f"Throttling occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                raise

def invoke_model_nova_lite(prompt):
    body = json.dumps({
        "inferenceConfig": {
            "max_new_tokens": 2048
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
    
    modelId= "amazon.nova-lite-v1:0"
    print("modelId ------", modelId)

    response = bedrock_runtime.invoke_model(
        body=body,
        modelId=modelId,
        contentType='application/json',
        accept='application/json'
    )   
    response_body = json.loads(response['body'].read())    
    return response_body

    
def invoke_model_with_backoff_mistral(prompt, model_id, max_retries=10, base_delay=2):
    print("model_id:-",model_id)
    for attempt in range(max_retries):
        try:
            return invoke_model_mistral(prompt, model_id)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < max_retries - 1:
                delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                print(f"Throttling occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                raise

def invoke_model_with_backoff_OpenAI(prompt,Task="Not Specifield" ,max_retries=10, want_json=True, base_delay=2):
    print({"Task to ai":Task})
    system_content = "You are a helpful assistant."
    
    for attempt in range(max_retries):
        try:
            return invoke_model_OpenAI(system_content, prompt,want_json)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < max_retries - 1:
                delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                print(f"Throttling occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                raise

def invoke_model_mistral(prompt, model_id):
    # Format the prompt according to Mistral's instruction format
    formatted_prompt = f"<s>[INST] {prompt} [/INST]"
    
    body = json.dumps({
        "prompt": formatted_prompt,
        "max_tokens": 4096,
        "temperature": 0.5,
        "top_p": 0.9
    })
    
    response = bedrock_runtime.invoke_model(
        body=body,
        # modelId='mistral.mistral-large-2402-v1:0',
        # modelId='mistral.mistral-7b-instruct-v0:2',
        # modelId='mistral.mixtral-8x7b-instruct-v0:1',
        modelId= model_id,
        accept='application/json',
        contentType='application/json'
    )
    
    response_body = json.loads(response['body'].read())
    return response_body.get('outputs', [{"text": ""}])[0]["text"]

def invoke_model_claude(prompt):
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2048,
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": ""},
        ],
        "temperature": 0.5,  # Reduced from 0.8 for more focused responses
        "top_p": 0.9,  # Added top_p for more focused sampling
        "top_k": 250,  # Reduced from 500 for more focused responses
        "stop_sequences": ["\n\nAssistant:", "\n\nHuman:"]  # Modified stop sequences
    })

    modelId= "anthropic.claude-3-5-sonnet-20240620-v1:0"
    print("modelId ------", modelId)

    response = bedrock_runtime.invoke_model(
        body=body,
        modelId= modelId,
        accept='*/*',
        contentType='application/json'
    )
    
    response_body = json.loads(response['body'].read())
    return response_body.get('content', [])

def invoke_model_nova(prompt):
    body = json.dumps({
        "inferenceConfig": {
            "max_new_tokens": 2048
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
    
    modelId= "amazon.nova-pro-v1:0"
    print("modelId ------", modelId)

    response = bedrock_runtime.invoke_model(
        body=body,
        modelId=modelId,
        contentType='application/json',
        accept='application/json'
    )   
    response_body = json.loads(response['body'].read())    
    return response_body

def invoke_model_deepseek(prompt):
    try:
        # Handle both direct string prompts and JSON-formatted prompts
        if isinstance(prompt, dict) and 'prompt' in prompt:
            # Regular prompt from API Gateway/JSON input
            prompt = prompt['prompt']
        elif isinstance(prompt, str):
            # Direct string prompt (from SDK/test invoke)
            try:
                # Try to parse as JSON
                event_json = json.loads(prompt)
                prompt = event_json.get('prompt', prompt)  # Fallback to raw string
            except json.JSONDecodeError:
                # Not JSON - use as direct prompt
                prompt = prompt

        # Prepare the request body
        body = {
            "prompt": prompt,
            "max_tokens": 4096,
            "temperature": 0.5,
            "top_p": 0.9
        }

        # Invoke the model
        modelId= "us.deepseek.r1-v1:0"
        print("modelId ------", modelId)

        response = bedrock_runtime.invoke_model(
            modelId=modelId,
            body=json.dumps(body),
            contentType='application/json',
            accept='application/json'
        )

        # Parse and return just the text response
        response_body = json.loads(response['body'].read())
        return response_body['choices'][0]['text']

    except Exception as e:
        raise

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

def extract_text(content):
    completion_text = ""
    for item in content:
        if isinstance(item, dict) and 'text' in item:
            completion_text += item['text'].split('text:', 1)[-1].strip()
    return completion_text

def extract_text_deepseek(content):
    return content.replace("</think>", "")

def extract_json(text):
    # Find the complete JSON object in the text using regex
    json_match = re.search(r'(\{[^{}]*"candidateName":[^{}]*"candidateLocation":[^{}]*\})', text)
    if json_match:
        json_str = json_match.group(1)
        # Parse the string to ensure it's valid JSON and return it
        return json.loads(json_str)
    return None

def extract_json_from_resume(json_data):
    try:
        # Extract the text content from the JSON structure
        text = json_data['output']['message']['content'][0]['text']
        
        # Find JSON within code blocks using regex
        # This pattern looks for content between ```json and ``` markers
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        
        if json_match:
            # Extract the JSON string from within the code block
            json_str = json_match.group(1)
            # Parse and return the JSON object
            return json.loads(json_str)
        else:
            # If no code block is found, try to find a raw JSON object
            json_match = re.search(r'(\{[^{}]*"candidateName":[^{}]*"candidateLocation":[^{}]*\})', text)
            if json_match:
                json_str = json_match.group(1)
                return json.loads(json_str)
            
        return None
    except Exception as e:
        print(f"Error extracting JSON: {e}")
        return None

def print_completion_text(completion_text):
    print("***********************************************************************")
    print(completion_text)
    print("#######################################################################")

def extract_score(completion_text):
    pattern = re.compile(r"Matching Score:\s*(\d+(\.\d+)?)", re.IGNORECASE)
    match = pattern.search(completion_text)
    if match:
        return Decimal(match.group(1))
    return 0
    
def extract_experience_level(content):
    # Extract JSON using regex
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        json_str = json_match.group()
        try:
            data = json.loads(json_str)
            experience_level = data.get("experience_level")
            print(f"Extracted experience_level: {experience_level}")
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}")
    else:
        print("No JSON found in the response.")

    return experience_level

def extract_experience_level_nova(response):
    try:
        # Direct access from the response structure
        text_content = response['output']['message']['content'][0]['text']
        
        # Parse the JSON directly since it appears to be valid JSON
        data = json.loads(text_content)
        experience_level = data.get("experience_level")
        print(f"Extracted experience_level: {experience_level}")
        return experience_level
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error processing response: {e}")
        return None

def extract_score_from_response(response_text):
    try:
        # Find the JSON content between curly braces
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1
        
        # If no valid JSON structure found, return None immediately
        if start_idx == -1 or end_idx <= start_idx:
            return None
            
        json_str = response_text[start_idx:end_idx]
        
        # Try to parse the JSON string
        data = json.loads(json_str)
        
        # Extract and return the score if it exists
        return data.get('score')
        
    except (json.JSONDecodeError, ValueError):
        # Return None for any JSON parsing errors
        return None

def extract_score_from_json_deepseek(text):
    start_pos = text.find('{')
    if start_pos == -1:
        return None
    
    # Track opening and closing braces to find complete JSON objects
    json_candidates = []
    brace_count = 0
    start_idx = None
    
    for i in range(len(text)):
        if text[i] == '{':
            if brace_count == 0:
                start_idx = i
            brace_count += 1
        elif text[i] == '}':
            brace_count -= 1
            if brace_count == 0 and start_idx is not None:
                json_candidates.append(text[start_idx:i+1])
    
    # Try to parse each candidate as JSON
    for candidate in json_candidates:
        try:
            json_data = json.loads(candidate)
            if 'score' in json_data:
                return json_data['score']
        except json.JSONDecodeError:
            continue
    
    return None

def extract_json_from_response(response_text):
    """Extract JSON from response text with advanced cleaning for problematic formats"""
    # Find the JSON block in the response (between triple backticks)
    json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
    
    if not json_match:
        # Fall back to looking for any JSON-like structure
        json_match = re.search(r'{\s*"score":\s*\[?(\d+)\]?,\s*"detailedAnalysis":', response_text, re.DOTALL)
        if json_match:
            # Extract score from simple regex match
            score = int(json_match.group(1))
            return {"score": score}
        return None
    
    json_str = json_match.group(1)
    
    # Fix the score field if it's an array instead of a number
    json_str = re.sub(r'"score":\s*\[(\d+)\]', r'"score": \1', json_str)
    
    # Extract the score directly using regex
    score_match = re.search(r'"score":\s*\[?(\d+)\]?', json_str)
    score = int(score_match.group(1)) if score_match else None
    
    # Simple approach: replace problematic matchingText sections entirely
    skill_keywords = []
    skill_points = []
    
    # Extract skill info using regex
    skill_pattern = re.compile(r'"keyword":\s*"([^"]+)",\s*"weightage":\s*(\d+),\s*"found":\s*(true|false),\s*"points":\s*(\d+)', re.DOTALL)
    skill_matches = skill_pattern.finditer(json_str)
    
    for skill_match in skill_matches:
        keyword = skill_match.group(1)
        weightage = int(skill_match.group(2))
        found = skill_match.group(3) == "true"
        points = int(skill_match.group(4))
        
        skill_keywords.append(keyword)
        if found:
            skill_points.append(points)
    
    # Calculate total score as a double-check
    calculated_score = sum(skill_points)
    
    # Build our own clean JSON structure
    clean_data = {
        "score": score if score is not None else calculated_score,
        "calculatedScore": calculated_score,
        "matchedSkills": skill_keywords,
        "skillPoints": skill_points,
        "message": "Score extracted successfully"
    }
    
    return clean_data

def extract_score_from_OpenAI_response(response):
    """
    Extracts score from different response formats.
    Handles JSON objects, JSON strings, and mixed text/JSON responses.
    
    Args:
        response (str or dict): The response containing score information
        
    Returns:
        float or int: The extracted score value, or None if not found
    """
    temp_score = None
    
    try:
        # If response is already a dictionary
        if isinstance(response, dict):
            temp_score = response.get('score')
            return temp_score
        
        # If response is a string, try different parsing approaches
        if isinstance(response, str):
            # Method 1: Try to parse as direct JSON
            try:
                data = json.loads(response)
                temp_score = data.get('score')
                return temp_score
            except json.JSONDecodeError:
                pass
            
            # Method 2: Extract JSON from mixed content using regex
            # Look for JSON objects that contain "score"
            json_pattern = r'\{[^{}]*"score"[^{}]*\}|\{(?:[^{}]|\{[^{}]*\})*"score"(?:[^{}]|\{[^{}]*\})*\}'
            json_matches = re.findall(json_pattern, response, re.DOTALL)
            
            for match in json_matches:
                try:
                    data = json.loads(match)
                    if 'score' in data:
                        temp_score = data['score']
                        return temp_score
                except json.JSONDecodeError:
                    continue
            
            # Method 3: Look for larger JSON blocks (for nested structures)
            # Find JSON blocks that might contain score in nested structure
            large_json_pattern = r'\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}'
            large_matches = re.findall(large_json_pattern, response, re.DOTALL)
            
            for match in large_matches:
                try:
                    data = json.loads(match)
                    temp_score = data.get('score')
                    if temp_score is not None:
                        return temp_score
                except json.JSONDecodeError:
                    continue
            
            # Method 4: Simple regex pattern for "score": value
            score_pattern = r'"score":\s*([0-9]+\.?[0-9]*)'
            score_match = re.search(score_pattern, response)
            if score_match:
                temp_score = float(score_match.group(1))
                return temp_score
    
    except Exception as e:
        print(f"Error extracting score: {e}")
        return None
    
    return temp_score

def ensure_decimal(value: Union[float, int, str, Decimal, None]) -> Optional[Decimal]:
    """Convert numeric value to Decimal if it isn't already."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))

def update_sqs_queue(queue_url, email, userId, referralId, job_ref_type):

    # Determine the event based on type
        
        if job_ref_type == "JOB":
            event = "JOB_APPLICATION_VALIDATE_MATCHING_SCORE"
            message_body ={
                "event": event,
                "userEmail" : email,
                "userId": userId,
                "context": {
                    "jobApplicationRequestId":referralId
                },
            }
        elif job_ref_type == "BULK":
            event = "CORPORATE_BULK_JD_RESUME_SEND_EMAIL_AND_WHATSAPP_NOTIFICATION"
            message_body ={
                "event": event,
                "userEmail" : "",
                "userId": "",
                "context": {
                    "corporateBulkJdResumeId":referralId
                },
            }
        elif job_ref_type == "REF":
            event = "REFERRAL_VALIDATE_MATCHING_SCORE"
            message_body ={
                "event": event,
                "userEmail" : email,
                "userId": userId,
                "context": {
                    "referralId":referralId
            },
        }
        else:
            event = "unknown"

        print("event:-", event)

        message_body_msg = json.dumps(message_body)
        
        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=message_body_msg
            )
        
        return {
            'statusCode': 200,
            'body': json.dumps('Message sent to SQS!')
        }

def process_response(response_text):
    """Main function to process the response text and extract score information"""
    try:
        # Try to extract JSON data
        parsed_data = extract_json_from_response(response_text)
        
        if not parsed_data:
            # Last resort: direct regex for score
            score_match = re.search(r'total skill matching score is (\d+)', response_text, re.IGNORECASE)
            if score_match:
                score = int(score_match.group(1))
                return {"score": score, "message": "Score extracted from text description"}
            return {"error": "Unable to extract score from response"}
        
        return parsed_data
        
    except Exception as e:
        # Last resort fallback
        try:
            # Try to find score in plain text
            score_match = re.search(r'total skill matching score is (\d+)', response_text, re.IGNORECASE)
            if score_match:
                return {"score": int(score_match.group(1)), "message": "Score extracted from text after error"}
            
            # Try another pattern
            score_match = re.search(r'final score will be (\d+)', response_text, re.IGNORECASE)
            if score_match:
                return {"score": int(score_match.group(1)), "message": "Score extracted from final score text"}
                
            return {"error": f"Failed to extract score: {str(e)}"}
        except:
            return {"error": "Complete failure in processing"}



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

            except Exception as e:
                remaining = max_try_for_json - attempt - 1
                print(f"JSON parse failed. Retries left: {remaining}")
                print("Error:", e)
                time.sleep(2)
                if remaining == 0:
                    raise

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

gcp_credentials = None

def lambda_handler(event, context):
    global gcp_credentials
    print("event-----", event)
    print("got event:",event)
    try:
        metadata = get_meta_data(event)
        if metadata.get("skipparsing","")=="true":
            print("skipParsing as got info to skip in metadata")
            return {'statusCode': 200, 'body': json.dumps(f'skipParsing as got info to skip in metadata')}
        
    except Exception as e:
        print("following normal flow")

    table_name = os.environ.get('table_name',"worko")

    env = os.environ.get("ENVIRONMENT","dev")
    if not gcp_credentials:
        GCP_secret_name ="GCP-aiplatform-secrect-"+env
        gcp_credentials = get_secret(GCP_secret_name)
    else:    
        print("Using cached GCP credentials")


    # GCP_secret_name = "GCP-firestore-secret-"+env
    # GCP_credentials = get_secret(GCP_secret_name)
    # print(GCP_secret_name)

    table_name = "worko"

    queue_name = os.environ.get('queue_name','worko-app-event-queue')
    
    # Extracting the bucket name from the nested 'Records' key
    s3_bucket_name = event['Records'][0]['s3']['bucket']['name']
    
    # Extracting the object key from the nested 'Records' key, which contains the folder prefix
    object_key = event['Records'][0]['s3']['object']['key']
    
    # The folder prefix is usually the first part of the object key before the first '/'
    key_parts = object_key.split('/')

    company_id = key_parts[1]
    bulk_cv_id = key_parts[3]
    cloud_file_name = key_parts[4]
    cv_id, _ = os.path.splitext(cloud_file_name)

    jd_partition_key_value = "COMP#ID#"+ company_id
    jd_sort_key_prefix =  "BJDRM#JD#ID#" + bulk_cv_id

    # Define the SQS queue URL
    account_id = get_account_id()
    
    queue_url = f'https://sqs.{region}.amazonaws.com/{account_id}/{queue_name}'

    # Fetch the file from S3
    response = s3_client.get_object(Bucket=s3_bucket_name, Key=object_key)
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

    # azure_openai_secret_name = "AZURE-openai-secret-multimodel-"+env
    # azure_openai_secret = get_secret(azure_openai_secret_name)
    # gpt4 = AzureOpenAIClient(azure_openai_secret,model="gpt-4o")
    # gpt_models = [gpt4]


    gcp = GeminiClient(gcp_credentials,env,model="gemini-3.5-flash")

    gcp_models = [gcp,gcp]
    cv_extract, cv_extracted_parsed = process_cv(processed_text,gcp_models)
    print(f"CV Extract:\n{cv_extract}")
    print(f"\nParsed Extract:\n{json.dumps(cv_extracted_parsed, indent=2)}")

    # fetch the job details from inDynamoDB
    item = query_dynamodb_item_with_sk_prefix(table_name, jd_partition_key_value, jd_sort_key_prefix)
    print("item",item)

    if item:
        job_desc = item.get('jobDescription')
        goodToHaveSkills = item.get('goodToHaveSkills')
        mustHaveSkills = item.get('mustHaveSkills')
        mustNotHaveSkills = item.get('mustNotHaveSkills')
        otherRequirements = item.get('otherRequirements')
        jdItem_extracted = item.get('jdExtracted', '')

        job_desc = f"{job_desc}\nMust Have Skills: {mustHaveSkills}\nGood To Have Skills: {goodToHaveSkills}\nMust Not Have Skills: {mustNotHaveSkills}"

    job_desc = clean_text(job_desc)
    print("job_desc--------",job_desc)
    
    # Update the parsed resume details inDynamoDB
    cv_partition_key_value = "BJDRM#JD#ID#"+ bulk_cv_id
    cv_sort_key_prefix_value =  "RSM#ID#" + cv_id

    scoreDetails = "IN PROGRESS"
    matchingScore = 0
    rejection_feedback = ""
    processing_status = "PENDING"
    emailFeedback = ""

    update_ref_response_in_dynamodb_for_bulk_process(table_name, cv_partition_key_value, cv_sort_key_prefix_value, cv_extract, cv_extracted_parsed, scoreDetails, matchingScore, rejection_feedback, emailFeedback, processing_status)
    
    
    score = jd_resume_matching(table_name, cv_partition_key_value, gcp_models,cv_sort_key_prefix_value, job_desc, processed_text, cv_extract, cv_extracted_parsed,gcp_models,otherRequirements,jdItem_extracted)
            
    print("Score----",score)

    #Uncomment before deploying in production, uncommented for testing in dev
    try:
        update_sqs_queue(queue_url, "", "", cv_id, "BULK")
    except Exception as sqs_error:
        print(f"SQS notification skipped (likely local testing): {sqs_error}")
    
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'All CV extracts processed and updated successfully'})}

if __name__ == "__main__":
    event = {
    
    "Records": [
        {
        "eventVersion": "2.1",
        "eventSource": "aws:s3",
        "awsRegion": "ap-south-1",
        "eventTime": "2026-02-02T06:29:44.990Z",
        "eventName": "ObjectCreated:Put",
        "userIdentity": {
            "principalId": "AWS:AROATCKANHWVTI7M7W26H:worko-api-dev-app"
        },
        "requestParameters": {
            "sourceIPAddress": "202.94.161.181"
        },
        "responseElements": {
            "x-amz-request-id": "2AEA5J52FRCR4D7Z",
            "x-amz-id-2": "k+8d91OhvVNYGON95mDc6TO3AZpKdKBzd5DKd58VghtdGXL45VqTOFC4LLey7GhkWHuiTQQEpltoRHjRV+OGXVjztLfn9SJ0"
        },
        "s3": {
            "s3SchemaVersion": "1.0",
            "configurationId": "7d404d16-3835-42a5-aa87-119edd0a72f4",
            "bucket": {
            "name": "worko-corporate-dev",
            "ownerIdentity": {
                "principalId": "A1V0APDMR493SG"
            },
            "arn": "arn:aws:s3:::worko-corporate-dev"
            },
            "object": {
            "key": "companies/01JJVRPHNENTTFFF7M3N6HEQ38/bulk-cvs/01KGEGNY9EZBR31KKYZJHAT2HC/01KGEGNYHMNAE7K6XZVQCQNXC5.pdf",
            "size": 217003,
            "eTag": "d0bb5e5b306caa14d2a5175919969d51",
            "sequencer": "0069804458EF01349B"
            }
        }
        }
    ]
    }
    # event = {'Records': [{'eventVersion': '2.1', 'eventSource': 'aws:s3', 'awsRegion': 'ap-south-1', 'eventTime': '2026-04-29T05:50:14.942Z', 'eventName': 'ObjectCreated:Put', 'userIdentity': {'principalId': 'AWS:AROATCKANHWV6VODIDLXB:worko-api-dev-app'}, 'requestParameters': {'sourceIPAddress': '43.251.216.130'}, 'responseElements': {'x-amz-request-id': '56R1Y6AYFXZEKHDC', 'x-amz-id-2': 'vO3EnO+cRp2jljjlqhmR2VArWSygayTCRqkPvIiCjO/4dlaKYIOelyNdmksvrum5PR/GqXcFIeTtSbB1y627XSx8xXaovvt0DA0QwmQg1xg='}, 's3': {'s3SchemaVersion': '1.0', 'configurationId': 'ab738abc-8532-4416-8d0d-b934f5c6c5c1', 'bucket': {'name': 'worko-corporate-dev', 'ownerIdentity': {'principalId': 'A1V0APDMR493SG'}, 'arn': 'arn:aws:s3:::worko-corporate-dev'}, 'object': {'key': 'companies/01JJVRPHNENTTFFF7M3N6HEQ38/bulk-cvs/01KQBWKDJ92748A206JRH8XS3C/01KQBWKE2HXPMXCD9KMHA5QG9W.pdf', 'size': 134930, 'eTag': '6d5fc40db8beaf6a808a59f180fecd96', 'sequencer': '0069F19C16E43D679A'}}}]}
    # event = {'Records': [{'eventVersion': '2.1', 'eventSource': 'aws:s3', 'awsRegion': 'ap-south-1', 'eventTime': '2026-04-30T03:47:14.411Z', 'eventName': 'ObjectCreated:Put', 'userIdentity': {'principalId': 'AWS:AROATCKANHWV6VODIDLXB:worko-api-dev-app'}, 'requestParameters': {'sourceIPAddress': '103.176.210.143'}, 'responseElements': {'x-amz-request-id': 'M8821ANDSJ4SB7CF', 'x-amz-id-2': 'qbxhNoagraibirrxfFHTlmo0/ufxacC9pRw3oATO12gDMXIR5GCHGlv/Hvjlh07UNKMebIe28Ls6GTJg2cfH2yNSrO/rIMDe'}, 's3': {'s3SchemaVersion': '1.0', 'configurationId': 'ab738abc-8532-4416-8d0d-b934f5c6c5c1', 'bucket': {'name': 'worko-corporate-dev', 'ownerIdentity': {'principalId': 'A1V0APDMR493SG'}, 'arn': 'arn:aws:s3:::worko-corporate-dev'}, 'object': {'key': 'companies/01JJVRPHNENTTFFF7M3N6HEQ38/bulk-cvs/01KQE7YWVMS0477JGJV5VPZE94/01KQE7YXJRAKXW2FT58QAXX18E.pdf', 'size': 62948, 'eTag': '6e4d27c08a2336247f2c9f0cdbf707b1', 'sequencer': '0069F2D0C2603EE399'}}}]}
    
    # event = {'Records': [{'eventVersion': '2.1', 'eventSource': 'aws:s3', 'awsRegion': 'ap-south-1', 'eventTime': '2026-04-30T03:47:14.416Z', 'eventName': 'ObjectCreated:Put', 'userIdentity': {'principalId': 'AWS:AROATCKANHWV6VODIDLXB:worko-api-dev-app'}, 'requestParameters': {'sourceIPAddress': '103.176.210.143'}, 'responseElements': {'x-amz-request-id': 'M886D6RQ8X20JZPE', 'x-amz-id-2': 'lNlwDNfGqffcgl41Q6dt+XL8U4E9wfT2NKR/oAw86JXYd2UcpR27b/hCUzWAJja0Q9PqFfKRitYu01SrKwlPfxYULB3wTfnAHdui2VkiPGU='}, 's3': {'s3SchemaVersion': '1.0', 'configurationId': 'ab738abc-8532-4416-8d0d-b934f5c6c5c1', 'bucket': {'name': 'worko-corporate-dev', 'ownerIdentity': {'principalId': 'A1V0APDMR493SG'}, 'arn': 'arn:aws:s3:::worko-corporate-dev'}, 'object': {'key': 'companies/01JJVRPHNENTTFFF7M3N6HEQ38/bulk-cvs/01KQE7YWVMS0477JGJV5VPZE94/01KQE7YXJQ1A1Y1NPWYWR8MNGT.pdf', 'size': 134930, 'eTag': '6d5fc40db8beaf6a808a59f180fecd96', 'sequencer': '0069F2D0C261116E69'}}}]}
    # event = {'Records': [{'eventVersion': '2.1', 'eventSource': 'aws:s3', 'awsRegion': 'ap-south-1', 'eventTime': '2026-04-30T03:47:14.417Z', 'eventName': 'ObjectCreated:Put', 'userIdentity': {'principalId': 'AWS:AROATCKANHWV6VODIDLXB:worko-api-dev-app'}, 'requestParameters': {'sourceIPAddress': '103.176.210.143'}, 'responseElements': {'x-amz-request-id': 'M880315C4TR0RWS6', 'x-amz-id-2': 'yvPay+2CqHPxJDVIoRdb9Q4NI3rZ4anc1UxJfXRTo6m3ouT12fU177Swx0EnYTiRmE1uVHWs546VeRhkh8FguVzAH5T6n/gR'}, 's3': {'s3SchemaVersion': '1.0', 'configurationId': 'ab738abc-8532-4416-8d0d-b934f5c6c5c1', 'bucket': {'name': 'worko-corporate-dev', 'ownerIdentity': {'principalId': 'A1V0APDMR493SG'}, 'arn': 'arn:aws:s3:::worko-corporate-dev'}, 'object': {'key': 'companies/01JJVRPHNENTTFFF7M3N6HEQ38/bulk-cvs/01KQE7YWVMS0477JGJV5VPZE94/01KQE7YXJQ41CF763Z6155M49G.pdf', 'size': 229525, 'eTag': '03dabfe78fd10de052afa62a062abf53', 'sequencer': '0069F2D0C264762FCB'}}}]}
    # event = {'Records': [{'eventVersion': '2.1', 'eventSource': 'aws:s3', 'awsRegion': 'ap-south-1', 'eventTime': '2026-04-30T03:47:14.411Z', 'eventName': 'ObjectCreated:Put', 'userIdentity': {'principalId': 'AWS:AROATCKANHWV6VODIDLXB:worko-api-dev-app'}, 'requestParameters': {'sourceIPAddress': '103.176.210.143'}, 'responseElements': {'x-amz-request-id': 'M886GEAQ1C355BN0', 'x-amz-id-2': 'vtF/bZWDCAdATm+4KzwvV3w1nScZnrYCdwMAS51S+Gn4na+vbNnnE8kI4waURxsv9/sE5KziL2nhZvK7SrLaQeqxgF7Pho9cle82BzDIusw='}, 's3': {'s3SchemaVersion': '1.0', 'configurationId': 'ab738abc-8532-4416-8d0d-b934f5c6c5c1', 'bucket': {'name': 'worko-corporate-dev', 'ownerIdentity': {'principalId': 'A1V0APDMR493SG'}, 'arn': 'arn:aws:s3:::worko-corporate-dev'}, 'object': {'key': 'companies/01JJVRPHNENTTFFF7M3N6HEQ38/bulk-cvs/01KQE7YWVMS0477JGJV5VPZE94/01KQE7YXJQHERK8HMF6CS0XJC5.pdf', 'size': 62956, 'eTag': '7accd93c4430fcbd465da73816a41424', 'sequencer': '0069F2D0C26084D34F'}}}]}
    event =  {'Records': [{'eventVersion': '2.1', 'eventSource': 'aws:s3', 'awsRegion': 'ap-south-1', 'eventTime': '2026-04-30T03:47:14.403Z', 'eventName': 'ObjectCreated:Put', 'userIdentity': {'principalId': 'AWS:AROATCKANHWV6VODIDLXB:worko-api-dev-app'}, 'requestParameters': {'sourceIPAddress': '103.176.210.143'}, 'responseElements': {'x-amz-request-id': 'M88E8FKKT8HW9JGW', 'x-amz-id-2': 'yi+FpeqMT1ox8hpl+PxbqDyuI72j2xJ4Du4v4c6a6ZvsKq7wcDMC9QvYT93GfVFLRR3iMzQgWLteYxiBpzM9CcdCBVLZ1Fi4GVZEb6cBHek='}, 's3': {'s3SchemaVersion': '1.0', 'configurationId': 'ab738abc-8532-4416-8d0d-b934f5c6c5c1', 'bucket': {'name': 'worko-corporate-dev', 'ownerIdentity': {'principalId': 'A1V0APDMR493SG'}, 'arn': 'arn:aws:s3:::worko-corporate-dev'}, 'object': {'key': 'companies/01JJVRPHNENTTFFF7M3N6HEQ38/bulk-cvs/01KQE7YWVMS0477JGJV5VPZE94/01KQE7YXJRQFPB5QT03C54FRQF.pdf', 'size': 83423, 'eTag': 'a647aa9f60fd38433fd4451eb7dabfea', 'sequencer': '0069F2D0C25AFF1497'}}}]}
    lambda_handler(event, None)


import json
import boto3
import re
import os
import time
import random
from datetime import datetime
from decimal import Decimal
import string
from typing import List, Tuple, Dict, Any, Optional, Union
import botocore
import fitz
import requests
import io                    
import base64
from boto3.dynamodb.conditions import Key, Attr
from google.cloud import firestore
from google.oauth2 import service_account
from utils import get_secret, AzureOpenAIClient



# Initialize Bedrock clients
sqs_region = 'ap-south-1'
region = 'us-east-1'
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client(service_name='bedrock', region_name = region)
bedrock_runtime = boto3.client(service_name='bedrock-runtime', region_name = region)
sqs = boto3.client('sqs')
s3_client = boto3.client('s3')

def get_account_id():
    # Create STS client
    sts_client = boto3.client('sts')

    # Call get-caller-identity
    response = sts_client.get_caller_identity()

    # Extract account ID
    return response['Account']

def extract_text_from_pdf(pdf_data):
    text = ""
    pdf_document = fitz.open(stream=pdf_data, filetype="pdf")
    for page in pdf_document:
        text += page.get_text()
    return text

def extract_text_from_docx(docx_bytes):
    text = ""
    document = Document(BytesIO(docx_bytes))
    for paragraph in document.paragraphs:
        text += paragraph.text + "\n"
    return text

def query_dynamodb_item_with_sk_prefix(table_name, partition_key_value, sort_key_prefix):
    table = dynamodb.Table(table_name)
    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(partition_key_value) &
                               boto3.dynamodb.conditions.Key('SK').begins_with(sort_key_prefix)
    )
    items = response.get('Items')
    if items:
        return items[0]
    return None

def query_dynamodb_item_for_ref_with_sk_prefix(table_name, partition_key_value, sort_key_prefix):
    table = dynamodb.Table(table_name)
    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(partition_key_value) &
                               boto3.dynamodb.conditions.Key('SK').eq(sort_key_prefix)
    )
    items = response.get('Items')
    if items:
        return items[0]
    return None

def query_dynamodb_item_with_index_sk_prefix(table_name, index_name, partition_key_value, sort_key_prefix):
    table = dynamodb.Table(table_name)
    response = table.query(
        IndexName=index_name,
        KeyConditionExpression=boto3.dynamodb.conditions.Key('GSI1PK').eq(partition_key_value) &
                               boto3.dynamodb.conditions.Key('GSI1SK').eq(sort_key_prefix)
    )
    items = response.get('Items')
    if items:
        return items[0]
    return None

def update_cv_extract_in_dynamodb(table_name, partition_key_value, sort_key_prefix, message, errorCode, overall_matching_score):
    table = dynamodb.Table(table_name)
    scoreDetails = "none"
    response = table.update_item(
        Key={
            'PK': partition_key_value,
            'SK': sort_key_prefix
        },
        UpdateExpression="set jdMatchErrorDesc=:m, jdMatchErrorCode=:c, scoreDetails=:scoreDetails, matchingScore=:s",
        ExpressionAttributeValues={
            ':scoreDetails': scoreDetails,
            ':m': message,
            ':c': errorCode,
            ':s': overall_matching_score
        },
        ReturnValues="UPDATED_NEW"
    )
    return response
# rejectionFeedbackBySystemForApplicant

def update_ref_response_in_dynamodb(table_name,partition_key,sort_key,scoreDetails,scoreDetailsForApplicant,matchingScore,
    emailFeedback,rejection_feedback,rejectionFeedbackBySystemForApplicant,check_exp_data=False,reject_on_ctc_or_exp=False):

    table = dynamodb.Table(table_name)
    current_datetime = datetime.now().isoformat()
    jdMatchErrorCode = 200
    jdMatchErrorDesc = "Score is generated successfully"

    # Choose UpdateExpression and ExpressionAttributeValues based on condition
    if not reject_on_ctc_or_exp and not check_exp_data:
        update_expr = (
            "SET jdMatchErrorDesc=:jdMatchErrorDesc, "
            "scoreDetails=:scoreDetails, "
            "scoreDetailsForApplicant=:scoreDetailsForApplicant, "
            "matchingScore=:matchingScore, "
            "jdMatchErrorCode=:jdMatchErrorCode, "
            "scoreFetchedDate=:scoreFetchedDate, "
            "emailFeedback=:emailFeedback, "
            "rejectionFeedbackBySystem=:rejectionFeedbackBySystem, "
            "rejectionFeedbackBySystemForApplicant=:rejectionFeedbackBySystemForApplicant"
        )
        expr_values = {
            ":jdMatchErrorDesc": jdMatchErrorDesc,
            ":scoreDetails": scoreDetails,
            ":scoreDetailsForApplicant": scoreDetailsForApplicant,
            ":matchingScore": matchingScore,
            ":jdMatchErrorCode": jdMatchErrorCode,
            ":scoreFetchedDate": current_datetime,
            ":emailFeedback": emailFeedback,
            ":rejectionFeedbackBySystem": rejection_feedback,
            ":rejectionFeedbackBySystemForApplicant": rejectionFeedbackBySystemForApplicant,
        }
        print("finally updating score info in ..table_name :--",table_name,"partition_key:--",partition_key,"sort_key:--",sort_key)
    else:
        update_expr = (
            "SET jdMatchErrorDesc=:jdMatchErrorDesc, "
            "scoreDetails=:scoreDetails, "
            "scoreDetailsForApplicant=:scoreDetailsForApplicant, "
            "matchingScore=:matchingScore, "
            "jdMatchErrorCode=:jdMatchErrorCode, "
            "scoreFetchedDate=:scoreFetchedDate, "
            "emailFeedback=:emailFeedback, "
            "rejectionFeedbackBySystem=:rejectionFeedbackBySystem, "
            "rejectionFeedbackBySystemForApplicant=:rejectionFeedbackBySystemForApplicant, "
            "checkEXPdata=:checkEXPdata, "
            "rejectCTCAndEXP=:rejectCTCAndEXP"
        )
        expr_values = {
            ":jdMatchErrorDesc": jdMatchErrorDesc,
            ":scoreDetails": scoreDetails,
            ":scoreDetailsForApplicant": scoreDetailsForApplicant,
            ":matchingScore": matchingScore,
            ":jdMatchErrorCode": jdMatchErrorCode,
            ":scoreFetchedDate": current_datetime,
            ":emailFeedback": emailFeedback,
            ":rejectionFeedbackBySystem": rejection_feedback,
            ":rejectionFeedbackBySystemForApplicant": rejectionFeedbackBySystemForApplicant,
            ":checkEXPdata": check_exp_data,
            ":rejectCTCAndEXP": reject_on_ctc_or_exp,
        }
        print("finally updating score info in ..table_name :--",table_name,"partition_key:--",partition_key,"sort_key:--",sort_key)

    # Now safely call update_item()
    response = table.update_item(
        Key={"PK": partition_key, "SK": sort_key},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
        ReturnValues="UPDATED_NEW",
    )

    return response

def update_ref_response_in_dynamodb_for_rejected_ctc_experience(table_name, partition_key, sort_key, matchingScore,rejectionFeedbackBySystemForApplicant,rejection_feedback):
    table = dynamodb.Table(table_name)
    
    
    jdMatchErrorCode = 200
    jdMatchErrorDesc = "Score is generated successfully and updated first"
    response = table.update_item(
        Key={
            'PK': partition_key,
            'SK': sort_key
        },
        UpdateExpression="SET jdMatchErrorDesc=:jdMatchErrorDesc, matchingScore=:matchingScore, jdMatchErrorCode=:jdMatchErrorCode,rejectionFeedbackBySystem=:rejectionFeedbackBySystem, rejectionFeedbackBySystemForApplicant=:rejectionFeedbackBySystemForApplicant",
        ExpressionAttributeValues={
            ':jdMatchErrorDesc': jdMatchErrorDesc,
            ':matchingScore': matchingScore,
            ':jdMatchErrorCode': jdMatchErrorCode,
            ':rejectionFeedbackBySystem': rejection_feedback,
            ':rejectionFeedbackBySystemForApplicant':rejectionFeedbackBySystemForApplicant

        },
        ReturnValues="UPDATED_NEW"
    )
    return response
    
def rejection_feedback_in_dynamodb(table_name, partition_key, sort_key, rejection_feedback):
    table = dynamodb.Table(table_name)
    response = table.update_item(
        Key={
            'PK': partition_key,
            'SK': sort_key
        },
        UpdateExpression="SET rejectionFeedbackBySystem=:rejectionFeedbackBySystem",
        ExpressionAttributeValues={
            ':rejectionFeedbackBySystem': rejection_feedback
        },
        ReturnValues="UPDATED_NEW"
    )
    return response
    
def update_sqs_queue(email, userId, referralId, job_ref_type):

    # Determine the event based on type
        
        if job_ref_type == "JOB":
            queue_name = 'worko-job-app-event-queue'
            event = "JOB_APPLICATION_VALIDATE_MATCHING_SCORE"
            message_body ={
                "event": event,
                "userEmail" : email,
                "userId": userId,
                "context": {
                    "jobApplicationRequestId":referralId
                },
            }
        elif job_ref_type == "REF":
            queue_name = 'worko-app-event-queue'
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

        print("sent sqs event successfully:-", event)

        # Define the SQS queue URL
        account_id = get_account_id()
        queue_url = f'https://sqs.{sqs_region}.amazonaws.com/{account_id}/{queue_name}'
        
        message_body_msg = json.dumps(message_body)
        
        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=message_body_msg
            )
        
        return {
            'statusCode': 200,
            'body': json.dumps('Message sent to SQS!')
        }

def has_key_elements(text, key_elements, threshold):
    present_elements = sum(1 for element in key_elements if element.lower() in text.lower())
    return present_elements >= threshold

def create_prompt(cv_extract, job_desc, step ):
    return f'Human:\nResume:\n{cv_extract}\nJob Description:\n{job_desc}\n{step}'

def invoke_model_with_backoff(prompt, max_retries=5, base_delay=1):
    for attempt in range(max_retries):
        try:
            return invoke_model(prompt)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < max_retries - 1:
                delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                print(f"Throttling occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                raise

def invoke_model(prompt):
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

    response = bedrock_runtime.invoke_model(
        body=body,
        # modelId='anthropic.claude-3-sonnet-20240229-v1:0',
        # modelId= 'anthropic.claude-3-haiku-20240307-v1:0',
        modelId= 'anthropic.claude-3-5-sonnet-20240620-v1:0',
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

def print_completion_text(completion_text):
    print("***********************************************************************")
    print(completion_text)
    print("#######################################################################")

def determine_type(input_string):
    if "JOB#" in input_string:
        return "JOB"
    elif "REF#" in input_string:
        return "REF"
    else:
        return "UNKNOWN"

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
    Extracts score from different response formats, including partial/incomplete JSON.
    Handles JSON objects, JSON strings, mixed text/JSON responses, and numeric values.
    
    Args:
        response (str, dict, int, or float): The response containing score information
        
    Returns:
        float or int: The extracted score value, or None if not found
    """
    temp_score = None
    
    try:
        # If response is already a numeric value (int or float), return it directly
        if isinstance(response, (int, float)):
            return response
        
        # If response is already a dictionary
        if isinstance(response, dict):
            temp_score = response.get('score')
            return temp_score if temp_score is not None else None
        
        # If response is a string, try different parsing approaches
        if isinstance(response, str):
            # Method 1: Simple regex pattern for "score": value (most reliable for partial JSON)
            score_pattern = r'"score":\s*([0-9]+\.?[0-9]*)'
            score_match = re.search(score_pattern, response)
            if score_match:
                temp_score = float(score_match.group(1))
                return temp_score
            
            # Method 2: Try to parse as direct JSON (only if it looks complete)
            try:
                # Only try JSON parsing if the string looks like complete JSON
                stripped = response.strip()
                if stripped.startswith('{') and stripped.endswith('}'):
                    data = json.loads(stripped)
                    # Handle case where parsed data is a number
                    if isinstance(data, (int, float)):
                        return data
                    # Handle case where parsed data is a dict
                    if isinstance(data, dict):
                        temp_score = data.get('score')
                        return temp_score if temp_score is not None else None
            except (json.JSONDecodeError, ValueError):
                pass
            
            # Method 3: Extract complete JSON blocks from mixed content
            # Look for complete JSON objects that contain "score"
            json_pattern = r'\{[^{}]*"score"[^{}]*\}'
            json_matches = re.findall(json_pattern, response, re.DOTALL)
            
            for match in json_matches:
                try:
                    data = json.loads(match)
                    if isinstance(data, dict) and 'score' in data:
                        temp_score = data['score']
                        if isinstance(temp_score, (int, float)):
                            return temp_score
                except (json.JSONDecodeError, ValueError):
                    continue
            
            # Method 4: Look for larger complete JSON blocks
            # Find JSON blocks that might contain score in nested structure
            large_json_pattern = r'\{(?:[^{}]|\{[^{}]*\})*\}'
            large_matches = re.findall(large_json_pattern, response, re.DOTALL)
            
            for match in large_matches:
                try:
                    # Only try parsing if it looks like complete JSON
                    if match.count('{') == match.count('}'):
                        data = json.loads(match)
                        if isinstance(data, dict):
                            temp_score = data.get('score')
                            if isinstance(temp_score, (int, float)):
                                return temp_score
                except (json.JSONDecodeError, ValueError):
                    continue
            
            # Method 5: Try to fix partial JSON by finding the score field specifically
            # Look for patterns like: "score": 15, even in incomplete JSON
            partial_score_pattern = r'"score":\s*([0-9]+\.?[0-9]*)[,\s}]?'
            partial_match = re.search(partial_score_pattern, response)
            if partial_match:
                try:
                    temp_score = float(partial_match.group(1))
                    return temp_score
                except ValueError:
                    pass
    
    except Exception as e:
        print(f"Error extracting score: {e}")
        print(f"Response type: {type(response)}")
        print(f"Response content: {str(response)[:200]}...")  # First 200 chars for debugging
        return None
    
    return temp_score

def ensure_decimal(value: Union[float, int, str, Decimal, None]) -> Optional[Decimal]:
    """Convert numeric value to Decimal if it isn't already."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))

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

def extract_education(resume_text):

    # Pattern to match **Education:** followed by content until next ** section or end
    pattern = r'\*\*Education:\*\*\s*(.*?)(?=\*\*[A-Za-z][^*]*:\*\*|$)'
    
    match = re.search(pattern, resume_text, re.DOTALL | re.IGNORECASE)
    
    if match:
        education_content = match.group(1).strip()
        return education_content
    else:
        return None

def invoke_titan_embeddings(input_text, bedrock_runtime):
    body = json.dumps({
        "inputText": input_text
    })
    
    response = bedrock_runtime.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=body,
        contentType='application/json'
    )
    
    response_body = json.loads(response['body'].read())
    return response_body.get('embedding', [])

class S3VectorRetriever:
    def __init__(self):
        self.s3vectors_client = boto3.client('s3vectors', region_name=region)
        self.bedrock_runtime = boto3.client('bedrock-runtime', region_name=region)
    
    def search_vectors(self, query: str, s3_vector_bucket_name: str, s3_vector_index_name: str, top_k: int = 5, similarity_threshold: float = 0.85) -> List[Dict[str, Any]]:
        """Search for similar vectors using query text"""
        try:
            # Generate embedding for the query
            query_embedding = invoke_titan_embeddings(query, self.bedrock_runtime)
            
            if not query_embedding:
                print(f"Failed to generate embedding for query: {query}")
                return []
            
            # Prepare query parameters (matching the working version)
            query_params = {
                'vectorBucketName': s3_vector_bucket_name,
                'indexName': s3_vector_index_name,
                'queryVector': {'float32': query_embedding},
                'topK': top_k,
                'returnMetadata': True,
                'returnDistance': True
            }
            
            # Execute query
            response = self.s3vectors_client.query_vectors(**query_params)
            
            # Extract results from 'vectors' key (not 'matches')
            vectors = response.get('vectors', [])
            print(f"Found {len(vectors)} similar vectors for query: '{query}'")
            
            # Format results and filter by similarity threshold
            results = []
            for vector in vectors:
                similarity_score = 1 - vector.get('distance', 1)  # Convert distance to similarity
                
                # Only include results above threshold
                if similarity_score >= similarity_threshold:
                    result = {
                        'text': vector.get('metadata', {}).get('originalText', ''),
                        'similarity_score': similarity_score,
                        'key': vector.get('key', ''),
                        'metadata': vector.get('metadata', {})
                    }
                    results.append(result)
                else:
                    print(f"Filtered out result with similarity {similarity_score:.3f} (below threshold {similarity_threshold})")
            
            print(f"After filtering: {len(results)} results above similarity threshold {similarity_threshold}")
            return results
            
        except Exception as e:
            print(f"Error searching vectors: {e}")
            return []

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
        "text": ("Carefully analyze the entire resume shown in the image. Extract all visible information and present it in plain text format, organized topic-wise. "
                "Do not miss any content, especially if the image is divided into multiple sections, columns, or panels. "
                "Your goal is to extract every detail under relevant sections such as: "
                "Personal Information (Name, Email, Phone, etc.); Career Objective or Summary; Education; Work Experience; Technical Skills; "
                "Soft Skills; Certifications; Projects; Achievements; Languages; Hobbies or Interests; Declaration. "
                "Maintain the original wording and structure as seen in the image. Do not interpret, rephrase, or summarize anything. "
                "Extract the resume exactly as it appears, grouped clearly by topic. Return the output as clean, readable text."   
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

def extract_colleges_from_response(response_data):
    """
    Extract college names from the nested JSON response structure
    Handles both markdown code blocks and plain JSON responses
    """
    try:
        # Navigate through the nested structure
        content = response_data['output']['message']['content'][0]['text']
        
        # First try to extract JSON from markdown code block
        json_match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
        
        if json_match:
            json_str = json_match.group(1)
        else:
            # If no markdown code block, try to parse the content directly as JSON
            json_str = content.strip()
        
        # Parse the JSON
        colleges_data = json.loads(json_str)
        
        # Extract the colleges list
        colleges = colleges_data.get('colleges', [])
        
        return colleges
            
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"Error extracting data: {e}")
        print(f"Raw content: {content}")
        return []

def clean_json_response(response: str) -> str:
    return response.strip().removeprefix("```json").removesuffix("```").strip()

def check_exp_ctc(inpute):
    # Convert all numeric inputs to float safely
    cv_ctc = float(inpute["cv_ctc"])
    cv_exp = float(inpute["cv_exp"])

    jd_ctc = inpute["jd_ctc"]
    jd_exp = inpute["jd_exp"]

    jd_ctc_min = float(jd_ctc["min"])
    jd_ctc_max = float(jd_ctc["max"])
    jd_exp_min = float(jd_exp["min"])
    jd_exp_max = float(jd_exp["max"])
    ECTC = cv_ctc*1.25

    result = {"ctc": False, "experience": False, "Explanation": False}
    explanations = []  # collect multiple messages
    min_threshhold_ctc = jd_ctc_min*0.7
    max_threshhold_ctc = jd_ctc_max*0.6
    
    if jd_exp_max<=4:
        print(f'exp less the 4 jd exp {jd_exp_max} cv exp {cv_exp}')
        if cv_exp>(jd_exp_max*1.6): #(overqualified exp)
            print("statment 1")
            msg = (
                f"You are overqualified for this role in terms of experience. your total experience is"
                f"{cv_exp} years But this role expected maximum {jd_exp_max} years of experience ."
            )
            result["experience"] = "above"
            explanations.append(msg)
        

    
    elif jd_exp_min*0.3>=3:      # if  30% of minimum exp is grater then 3   (underqualified exp)
        print("Min exp 30% is Greater then 3")
        print("1")
        
        if jd_exp_min-cv_exp>3: # check if candidate exp is 3 years less then min_exp_jd
            print("statment 2")
            print(f"jd_mim {jd_exp_min} cv exp {cv_exp}")
            # print("under qualified rejected")
            msg = (
                f"You are underqualified in terms of experience your total experience is "
                f"{cv_exp} years But this role expected minimum of {jd_exp_min} years of experience ."
            )
            result["experience"] = "below"  # True
            explanations.append(msg)
            
    elif cv_exp < (jd_exp_min * 0.7):
        print("statment 3")
        msg = (
            f"You are underqualified in terms of experience your total experience is "
            f"{cv_exp} years But this role expected minimum of {jd_exp_min} years of experience ."
        )
        result["experience"] = "below" #True
        explanations.append(msg)

            
    if jd_exp_max*0.4>4:  # if  40% of maximum exp is grater then 4  (overqualified exp)
        print("max exp 40% is Greater then 4")
        
        
        if cv_exp - jd_exp_max>4: # check if candidate exp is 4 years greater then max_jd_exp
            print(f"jd_mx {jd_exp_max} cv exp {cv_exp}")
            print("statment 4")
            msg = (
                f"You are overqualified for this role in terms of experience. your total experience is "
                f"{cv_exp} years which exceeds job’s maximum required experience is {jd_exp_max} years."
            )
            result["experience"] = "above" #True
            explanations.append(msg)
    elif cv_exp > jd_exp_max * 1.4 and jd_exp_max>4 :
        print("statment 5")
        msg = (
            f"You are overqualified for this role in terms of experience. your total experience is "
            f"{cv_exp} years which exceeds job’s maximum required experience is {jd_exp_max} years."
        )
        result["experience"] = "above" #True
        explanations.append(msg)

        
    if ECTC > jd_ctc_max * 1.2 and (jd_ctc_max * 1.2)>10 :        # CTC logic
        print("statment 6")
        msg = (
            f"You are overqualified in terms of compensation, as your current CTC "
            f"{cv_ctc} LPA and maximum offered by this role is {jd_ctc_max} LPA."
        )
        result["ctc"] = "above" #True
        explanations.append(msg)
        
    if ECTC > jd_ctc_max * 1.3 and (jd_ctc_max * 1.2)<10:        # CTC logic
        print("statment 7")
        msg = (
            f"You are overqualified in terms of compensation, as your current CTC "
            f"{cv_ctc} LPA and maximum offered by this role is {jd_ctc_max} LPA."
        )
        result["ctc"] = "above" #True
        explanations.append(msg)

        # ---- Combine Explanations ----
    if explanations:
        if len(explanations) > 1:
            result["Explanation"] = ", ".join(explanations[:-1]) + " and " + explanations[-1]
        else:
            result['Explanation'] = explanations[0] 
            
    else:
        result["Explanation"] = False

    return result

def get_reason_from_rejection_data(response):
    data = {i:response[i] for i in response if response[i]!=False and i!="Explanation"}
    reason =[]
    for i in data:
        if len(data)==1:
            reason.append(f'{i} is {data[i]}')
    
        else:
            reason.append(f'{i} is {data[i]}')
            
    reason = " and ".join(reason)
    if reason:
        return reason

def update_exp_ctc_match_in_dynamodb(table_name, partition_key, sort_key, match_obj,reject_candidate_based_on_ctc_or_exp):
    table = dynamodb.Table(table_name)
    response = table.update_item(
        Key={
            'PK': partition_key,
            'SK': sort_key
        },
        UpdateExpression="SET match_obj=:match_obj, reject_candidate_based_on_ctc_or_exp=:reject_candidate_based_on_ctc_or_exp",
        ExpressionAttributeValues={
            ':match_obj': match_obj,
            ':reject_candidate_based_on_ctc_or_exp':reject_candidate_based_on_ctc_or_exp,
        },
        ReturnValues="UPDATED_NEW"
    )
    return response

def quiry_dynamo_for_candidate_feedbacks(partition_key):
    dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')
    table = dynamodb.Table('worko-job-app')
    

    response = table.query(
        KeyConditionExpression=Key('PK').eq(partition_key),
        FilterExpression=Attr('rejectedByUserId').exists() , # Sort descending # Specify which attributes to return
        ProjectionExpression='rejectedByUserId.reason,rejectedByUserId.userComment'
    )
    if response["Items"]:
        output = {}
        for i, item in enumerate(response["Items"], start=1):
            output[f"reason{i}"] = item["rejectedByUserId"]["reason"]
            output[f"recruiterComment{i}"] = item["rejectedByUserId"]["userComment"]
        return output
    else:
        return False
    # return response["Items"]

def quiry_dynamo_for_job_feedbacks(partition_key ,table_name='worko',sort_key_prefix='ID#'):

    partition_key = f'JOB#ID#{partition_key}'
    dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')
    table = dynamodb.Table('worko-job-app')
    index = 'GSI3'
    

    response = table.query(
        IndexName=index,
        KeyConditionExpression=Key('GSI3PK').eq(partition_key),
        FilterExpression=Attr('rejectedByUserId').exists() , # Sort descending # Specify which attributes to return
        ProjectionExpression='rejectedByUserId.reason,rejectedByUserId.userComment,PK,SK'
    )
    Salary_mismatched,Industry_mismatched,Educational_mismatched,Experience_mismatched,Other_mismatched=[],[],[],[],[]
    feedback = []
    if response["Items"]:
        for item in response["Items"]:
            item["rejectedByUserId"]["reason"]
            output ={}
            PK = item['PK']
            User_data = query_dynamodb_item_with_sk_prefix(table_name, PK, sort_key_prefix)
            ctc = User_data.get("CTC","")
            YOE = User_data.get("YOE","")

            output[f"YOE"] = YOE
            output[f"CTC"] = ctc
            output[f"PK"] = PK
            output[f"reason"] = item["rejectedByUserId"]["reason"]
            output[f"recruiterComment"] = item["rejectedByUserId"]["userComment"]
            if output[f"reason"]=="Salary Expectation Mismatch":
                Salary_mismatched.append(output)
            if output[f"reason"]=="Not From The Required Industry ":
                Industry_mismatched.append(output)
            if output[f"reason"]=="Educational Background Expectation Mismatch":
                Educational_mismatched.append(output)
            if output[f"reason"]=="Experience Expectation Mismatch":
                Experience_mismatched.append(output)
            if output[f"reason"]=="other":
                Other_mismatched.append(output)
            feedback.append({"reason":output[f"reason"],"recruiterComment" : output[f"recruiterComment"]})
          

        detaild_feedback = {"Salary_mismatched":Salary_mismatched,"Industry_mismatched":Industry_mismatched,
                "Educational_mismatched":Educational_mismatched,"Experience_mismatched":Experience_mismatched,
                "Other_mismatched":Other_mismatched}

        return feedback,detaild_feedback
    else:
        return False,False

def quiry_dynamo_for_candidate_feedbacks(partition_key='USR#EML#shaukt1998+34@gmail.com'):
    dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')
    table = dynamodb.Table('worko-job-app')
    

    response = table.query(
        KeyConditionExpression=Key('PK').eq(partition_key),
        FilterExpression=Attr('rejectedByUserId').exists() , # Sort descending # Specify which attributes to return
        ProjectionExpression='rejectedByUserId.reason,rejectedByUserId.userComment'
    )
    if response["Items"]:
        output = {}
        for i, item in enumerate(response["Items"], start=1):
            output[f"reason{i}"] = item["rejectedByUserId"]["reason"]
            output[f"recruiterComment{i}"] = item["rejectedByUserId"]["userComment"]
        return output
    else:
        return False

def expRejectCheck(inps):
    new_check = {}
    for inp in inps:
        candidate_exp,job_min,job_max= inp["cv_exp"],inp["jd_exp"]["min"],inp["jd_exp"]["max"]
        if candidate_exp < job_min:
            new_check['min']=candidate_exp
            
            print('below')
        if candidate_exp > job_max:
            new_check['max']=candidate_exp
            print('above')
    return new_check

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

    def get_document_firstore(self,collection_name,doc_id):
        doc_ref = self.db.collection(collection_name).document(doc_id)
        return doc_ref.get().to_dict()

class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        # Check if the object has a method to convert to list (common for vectors)
        if hasattr(obj, 'tolist'):
            return obj.tolist()
        # Fallback for other custom objects: use their dictionary representation
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return super().default(obj)

def lambda_handler(event, context):
    print(event)
    
    # Initialize Azure OpenAI Client
    env = os.environ.get("ENVIRONMENT", "dev")
    azure_openai_secret_name = "AZURE-openai-secret-multimodel-" + env
    azure_openai_secret = get_secret(azure_openai_secret_name)
    gpt4 = AzureOpenAIClient(azure_openai_secret, model="gpt-4o")
    gpt_models = [gpt4]
    
    otherRequirements=""
    table_name = os.environ.get('DYNAMO_TABLE_NAME',"worko")
    jobs_table_name = os.environ.get('JOBS_DYNAMO_TABLE_NAME',"worko-job-app")
    s3_bucket_name = os.environ.get('S3_BUCKET_NAME',"worko-app-dev")
    print(f"DYNAMO_TABLE_NAME {table_name} JOBS_DYNAMO_TABLE_NAME {jobs_table_name} s3_bucket_name {s3_bucket_name}")
    
    # S3 Vector Configuration
    s3_vector_bucket_name = os.environ.get('S3_VECTOR_BUCKET_NAME')
    s3_vector_index_name = os.environ.get('S3_VECTOR_INDEX_NAME')  

    partition_key_value = event.get('USER_PK')
    sort_key_prefix1 = event.get('USER_DETAIL_SK')
    sort_key_prefix2 = event.get('ENTITY_SK')
    MATCHING_ENTITY = event.get("MATCHING_ENTITY","") #"SOURCE_TYPE_JOB_APP"
    candidateParsedCvId = event.get("candidateParsedCvId","")
    sort_key_prefix3 = "REF#"

    # Fetch the resume attributes from the dynamo db
    item = query_dynamodb_item_with_sk_prefix(table_name, partition_key_value, sort_key_prefix1)
    print(f"cv item of the user {item}")
    # Fetch the jd attributes from the dynamo db
    jdItem = query_dynamodb_item_for_ref_with_sk_prefix(table_name, partition_key_value, sort_key_prefix2)
    print(f"jdItem:- table_name : {table_name},partition_key_value:{partition_key_value},sort_key_prefix2:{sort_key_prefix2}",jdItem)   
    email = partition_key_value.split('#')[2]
    userId = item.get('SK')
    userId = userId.split('#')[1]
    jdItem_extracted = jdItem.get('jdExtracted', '') if jdItem else ''

    referralId = sort_key_prefix2.split('#')[-1]
    print("job/ref Id:-", referralId)

    job_ref_type = determine_type(sort_key_prefix2)
    print("job_ref_type:-", job_ref_type)

    # Extracting the CV raw text
    resumeId = item.get('SK').split('#')[-1]
    cvId = item.get('CV')
    print(f"resumeId: {resumeId},cvId:{cvId}")

    if candidateParsedCvId:
        print("get firstore doc here")

        collection_name = "candidateParsedCvs"
        env = os.environ.get("ENVIRONMENT","dev")
        GCP_secret_name = "GCP-firestore-secret-"+env
        GCP_DATABASE_NAME = "worko-corp-db-"+env
        
        db = FirestoreManager(GCP_secret_name,GCP_DATABASE_NAME)
        item = db.get_document_firstore(collection_name,candidateParsedCvId)
        print(f"in case of candidate form submission cv item from firestore {str(item)[:100]}")
    try:
        if MATCHING_ENTITY =="SOURCE_TYPE_JOB_APP":
            sourceTypeCvAwsS3Details = event.get("sourceTypeCvAwsS3Details",{})
            filePath= sourceTypeCvAwsS3Details.get("filePath","")
            fileName= sourceTypeCvAwsS3Details.get("fileName","")
            key = filePath + "/" + fileName
            s3_bucket_name = sourceTypeCvAwsS3Details.get("bucketName")
        else:
            key = "users/" + resumeId + "/resumes/" + cvId
        print("key",key)


        # Attempt to fetch the PDF file from S3
        response = s3_client.get_object(Bucket=s3_bucket_name, Key=key)
        data = response['Body'].read()

    except botocore.exceptions.ClientError as error:
            # Check the specific error code
            error_code = error.response['Error']['Code']
            if error_code == 'AccessDenied':
                print("Access denied to the S3 object.")
                return {
                    'statusCode': 403,
                    'body': json.dumps({'message': 'Access denied to the specified S3 object'})
                }
            elif error_code == 'NoSuchKey':
                print("The specified key does not exist.")
                return {
                    'statusCode': 404,
                    'body': json.dumps({'message': 'The specified key does not exist'})
                }
            else:
                # Handle other possible exceptions
                print(f"Unexpected error: {error_code}")
                return {
                    'statusCode': 500,
                    'body': json.dumps({'message': 'Internal server error'})
                }

    # Extract text from the PDF or DOCX file
    if ".pdf" in key:
        processed_text = extract_text_from_pdf(data)
        if not processed_text : 
            print('image Based cv processing..')
            base64_images = extract_images_from_pdf(data)
            processed_text = invoke_claude_with_image(base64_images)   
            print('image Based cv process completed') 
    elif ".docx" in key:
        processed_text = extract_text_from_docx(data)
    else:
        print("The file format is not supported.")
        return {
            'statusCode': 400,
            'body': json.dumps({'message': 'Unsupported file format. Please upload a PDF or DOCX file.'})
        }

    print("processed_text", str(processed_text)[:100])
    #   Validate the cv
    key_resume_elements = ['multipleCandidateExperience', 'education', 'personalDetails','name', 'email']
    key_jd_elements = ['experience', 'education', 'skills', 'primary responsibility', 'certifications', 'Preferred Skills', 'job description', 'responsibilities', 'role', 'Employment', 'Department', 'Posted', 'Company']
    
    cvExtractParsed = item.get('cvExtractParsed', '')
    CTC_from_cv = item.get('CTC')
    YOE_from_cv = item.get('YOE')
    cv_extract = item.get('cvExtractParsed')

    if candidateParsedCvId:#in case of firstore cv
        cvExtractParsed = item
        CTC_from_cv = cvExtractParsed.get('currentCTC')
        YOE_from_cv = cvExtractParsed.get('totalYOE')
        cv_extract = item
        # with open(r'src/worko-jd-resume-matching/firstore_cv_data.json', 'w') as json_file:
        #     json.dump(item, json_file, indent=4, cls=CustomEncoder)


    if not item or not has_key_elements(str(cvExtractParsed).lower(), key_resume_elements, 2):
        update_cv_extract_in_dynamodb(table_name, partition_key_value, sort_key_prefix2, "No valid resume data found or resume data is not readable", 250, -1)
        # update_sqs_queue(email, userId, referralId, job_ref_type) recently commented
        print("No valid resume data found or resume data is not readable")
        return {"statusCode": 200, "body": "Overall matching score: 0"}



    final_completion_text = ""
    rejection_feedback = ""
    rejectionFeedbackBySystemForApplicant=""   #
    completion_text_approval= ""
    overall_matching_score = 0
    emailFeedback = ""
    overall_Analysis = ""
    scoreDetails = ""
    scoreDetailsForApplicant=""  #
    experienceRange = False
    job_feedbacks = False
    mandatoryRequirementsFromFeedback = False
    feedbackMachingWithCandidate = False

    if "JOB" in job_ref_type:   #it will use to overwrite job_desc if it is from job application and not from reff
        Job_id_item = query_dynamodb_item_for_ref_with_sk_prefix(jobs_table_name, partition_key_value, sort_key_prefix2)
        
        jobs_id = Job_id_item.get('jobId')
        print("jobs_id:-", jobs_id)

        index_name = "GSI1"
        jobs_partition_key_value = "JOBS#"
        job_sort_key_prefix1 = "ID#" + jobs_id

        jdItem = query_dynamodb_item_with_index_sk_prefix(jobs_table_name, index_name, jobs_partition_key_value, job_sort_key_prefix1)
        print("jdItem:-",jdItem)
        
        if jdItem:
            job_desc = jdItem.get('jobDescription')
            experienceRange = jdItem.get('experienceRange')
            softSkills = jdItem.get('softSkills')
            technicalSkills = jdItem.get('technicalSkills')
            coreSkills = jdItem.get('coreSkills')
            otherRequirements = jdItem.get('otherRequirements')

            salaryRange = jdItem.get('salaryRange') # Extract salaryRange, experienceRange, department for first check if these requirements are not met reject candidate directly.
            experienceRange = jdItem.get('experienceRange')
            department = jdItem.get('department')
            jobTitle = jdItem.get("jobTitle")

            jdItem_extracted = f"{job_desc}\nExperience Range: {experienceRange}\nSoft Skills: {softSkills}\nTechnical Skills: {technicalSkills}\nCore Skills: {coreSkills}\nMandatory Requirements: {otherRequirements}"
            print("jdItem_extracted:-",jdItem_extracted)
            
            #get the feedback for further analysis
            candidate_feedbacks = quiry_dynamo_for_candidate_feedbacks(partition_key_value)
            feedbacks ,job_feedbacks = quiry_dynamo_for_job_feedbacks(jobs_id) #(jobs_id)

            print(f"feedbacks got for the job {job_feedbacks}")
            # Experience_mismatched = False
            if job_feedbacks:
                Salary_mismatched = job_feedbacks.get("Salary_mismatched","")
                Industry_mismatched = job_feedbacks.get("Industry_mismatched","")
                Educational_mismatched = job_feedbacks.get("Educational_mismatched","")
                Experience_mismatched = job_feedbacks.get("Experience_mismatched","")
                Other_mismatched = job_feedbacks.get("Other_mismatched","")
              #decide new thresh hold based on past rejection 

                if Experience_mismatched:   #get data if experince is rejected by numbers
                    experienceFeedbackNumericData  = []
                    for i in Experience_mismatched:
                        data = {'cv_exp':i["YOE"],'jd_exp':experienceRange}
                        experienceFeedbackNumericData.append(data)
                    newThreshHoldF_for_exp = expRejectCheck(experienceFeedbackNumericData) 
                
                prompt1 = f"""
                You are an **Expert HR Manager** with **40+ years of experience** in recruitment evaluation and job requirement analysis.

                You are given detailed **interviewer feedback** and a set of **mandatory requirements**.  
                Your job is to **analyze, extract, and structure** all job requirements derived from the feedback — without missing a single one.

                ##  PHASE 1 — Requirement Extraction
                ###  Objective
                Extract and summarize what the feedback **explicitly or implicitly** reveals about:
                - The **skills**, **experience**, or **attributes** the role requires.
                - What the **ideal candidate** should have or demonstrate.

                Every valid insight must be reframed into a clear, standardized **requirement statement**.

                ###  Instructions
                1. **Read every “reason” and “recruiterComment” carefully** — do not skip or omit any entry.
                2. **Derive requirements only from feedback content.**
                - The job description ({jdItem}) can be used **only for context clarification**.
                - Never add, infer, or invent new requirements beyond what feedback implies.
                3. **Reframe all valid insights** as **concise, single-line job requirements** starting with:
                - "Candidate must have..."
                - "Candidate should be skilled in..."
                - "Candidate must be able to..."
                4. **Include every unique feedback-derived requirement** in `"requirements"`.
                5. **Exclude**:
                - General praise (e.g., “Great attitude”).
                - Rejection reasons unrelated to job fit (e.g., “Not confident”).
                - Personal or behavioral opinions not tied to skill or experience.
                6. **Track repetition frequency**:
                - A requirement must appear under `"repeatedmandatoryRequirements"` **only if it occurs 3 or more times** (exactly or as a clear semantic equivalent).
                - If none meet this criterion, return `"repeatedmandatoryRequirements": []`.
                7. Avoid duplicates:
                - If two requirements are **more than 50% semantically similar**, keep only one.
                8. Do **not** include markdown, comments, or explanations.

                ---
                ##  PHASE 2 — Feedback-to-Requirement Matching

                ### Objective
                Identify which feedback statements **exactly or semantically match** the existing **Mandatory Requirements**.

                Only return the **original feedback lines** that clearly correspond to one or more mandatory requirements.

                ---

                ### Logic Rules
                1. Compare **each feedback line** against **all mandatory requirements** ({otherRequirements}).
                2. A feedback line is a **match** only if:
                - It expresses **the same meaning** as a mandatory requirement (≥80% semantic similarity).
                - It does **not** add, remove, or alter key information.
                3. If a feedback line is only partially similar or expands on the requirement — **exclude it**.
                4. Never paraphrase, summarize, or reword feedback.
                5. Include **only the exact original feedback sentences** inside `"feedbackmandatoryRequirements"`.
                6. If **no matches exist**, return `"feedbackmandatoryRequirements": []`.
                **last check**
                evrey feedback must be there in requirements skip only of you are adding it in repeatedmandatoryRequirements or feedbackmandatoryRequirements
                ---

                ## INPUT
                - **Mandatory Requirements:**  
                {otherRequirements}

                - **Feedback Entries (combined):**  
                {feedbacks}

                ---

                ## STRICT OUTPUT FORMAT (JSON ONLY)
                Return **only** a valid JSON object in the exact structure below — no additional text, markdown, or explanations:

                
                {{
                "requirements": [
                    "Candidate must have experience in data analysis.",
                    "Candidate should be skilled in Python and SQL."
                ],
                "repeatedmandatoryRequirements": [
                    "Candidate must have experience in data analysis."
                ],
                "feedbackmandatoryRequirements": [
                    "Candidate must have strong analytical skills."
                ]
                }}"""


                requirementsFormFeedback = gpt_models[0].invoke_model_with_backoff(prompt=prompt1, Task="AI for feedback Extraction.")
                mandatoryRequirementsFromFeedback = requirementsFormFeedback.get("repeatedmandatoryRequirements","") + requirementsFormFeedback.get("feedbackmandatoryRequirements","")
                
                print(f'requirementsFormFeedback :-- {requirementsFormFeedback}')
                print("merged mandatoryRequirementsFromFeedback", mandatoryRequirementsFromFeedback)
                requirementsFormFeedback = requirementsFormFeedback.get("requirements","")

                prompt = f"""
                You are an **Expert HR Manager** with over **40 years of experience** in recruitment evaluation and job analysis.

                Your task is to carefully review **recruiter feedback** and **mandatory requirements**, then **reframe and consolidate** them into a unified list of clear, concise **job requirements**.

                ### Objective
                Transform all recruiter feedback and mandatory requirements into **standardized job requirement statements** that begin with:
                - "Candidate must have..."
                - "Candidate must be..."

                These statements should capture only the **explicit or implicit requirements** derived from the provided inputs.


                ### Step-by-Step Instructions
                1. **Read every recruiter feedback entry carefully** — do not skip or ignore any.
                2. **Extract all implied or explicit job requirements** mentioned or hinted at.
                3. **Reframe** each requirement into a concise, single-line statement using a consistent format:
                -Example1: *"Candidate must have strong analytical skills."*
                -Example2: *"Candidate must be experienced in Python development."*
                4. **Combine** the results from both:
                - Recruiter Feedback  
                - Mandatory Requirements
                5. **Avoid repetition**:
                - If two statements are **more than 50% similar**, **keep only one**.
                - Retain both **only if** each adds **unique or explicit information**.
                6. **Do not add or infer** any new information not clearly supported by the inputs.
                7. Ensure that **every point from both sections** (feedback + mandatory requirements) is **represented** in the final output.

                ### Input Data
                **Recruiter Feedback:**  
                {mandatoryRequirementsFromFeedback}

                **Mandatory Requirements:**  
                {otherRequirements}

                ### Output Format (Strictly JSON)
                Return your final answer **only** in the following JSON structure (no text outside the JSON):

                
                {{
                "feedbackMandatoryRequirements": [
                    "Candidate must have knowledge of Python.",
                    "Candidate must be proficient in software development.",
                    "Candidate must have strong problem-solving skills."
                ]
                }}"""



                mandatoryRequirementsFromFeedback = gpt_models[0].invoke_model_with_backoff(prompt=prompt, Task="AI for feedback summarization.")
                print("mandatoryRequirementsFromFeedback  :--",mandatoryRequirementsFromFeedback)

                mandatoryRequirementsFromFeedback = " ".join(mandatoryRequirementsFromFeedback.get("feedbackMandatoryRequirements",""))
                print("mandatoryRequirementsFromFeedback  :--",mandatoryRequirementsFromFeedback)

                if mandatoryRequirementsFromFeedback:
                    print("adding mandatoryRequirementsFromFeedback  :--",mandatoryRequirementsFromFeedback)
                    # otherRequirements = otherRequirements + mandatoryRequirementsFromFeedback
                    otherRequirements = mandatoryRequirementsFromFeedback

    # print("**********************************Resume*********************************************")
    print("Resume:-", str(cv_extract)[:100])
    # Validate the Job description
    if not jdItem or not has_key_elements(jdItem_extracted.lower(), key_jd_elements, 1):
        update_cv_extract_in_dynamodb(table_name, partition_key_value, sort_key_prefix2, "No valid job description found or job description is not readable", 251, -1)
        print("No valid job description found or job description is not readable")
        # update_sqs_queue(email, userId, referralId, job_ref_type) recently commented
        return {"statusCode": 200, "body": "Overall matching score: 0"}

    print("*****************************Job Description******************************************")
    job_desc = jdItem_extracted
    print("jd:-", job_desc)
#############################################Evaluate candidate based on ctc and exp#########################################################
    department_mismatch =False
    reject_on_ctc_or_exp=False
    if experienceRange:
        data_to_check_ctc_and_exp = {"jd_ctc":salaryRange,"jd_exp":experienceRange,'cv_ctc':CTC_from_cv,'cv_exp':YOE_from_cv}
        check_exp_data = check_exp_ctc(data_to_check_ctc_and_exp)
        reject_on_ctc_or_exp = bool([key for key, value in check_exp_data.items() if value is not False])      

        preff_sort_key = "PREF#"
        if candidateParsedCvId: #in case of firstore cv
            userPreferredDepartments = item.get("userPreferredDepartments","")
            department = jdItem.get("department")
            name_of_the_candidate= item.get("name","")

        else:
            preff_data = query_dynamodb_item_with_sk_prefix(table_name, partition_key_value, preff_sort_key)
            userPreferredDepartments = preff_data.get("userPreferredDepartments")
            department = jdItem.get("department")
            name_of_the_candidate = cvExtractParsed.get('personalDetails').get('name')

        prompt = (
        f"You are an expert HR Manager with 40+ years of experience in both technical and non-technical hiring.\n\n"
        f"Analyze the following job description and its department, then compare it with the candidate’s preferred departments and resume.\n\n"
        f"**Task:**\n"
        f"Your job is to check whether the candidate’s domain is aligned with the job description’s domain or not.\n\n"
        f"**Job Description:** {job_desc}\n"
        f"**Department of Job Description:** {department}\n\n"
        f"**Candidate’s Resume:** {processed_text}\n"
        f"**Candidate’s Preferred Departments:** {userPreferredDepartments}\n\n"
        f"**Considerations for classification:**\n"
        f"- Technical roles typically involve programming, engineering, data analysis, or IT skills.\n"
        f"- Non-technical roles typically focus on business, management, sales, or operations.\n\n"
        f"- **Strict Note** Never provide any extra explanantion apart feom below json"
        f"**Output Format:**\n"
        f"{{\n"
        f'  "AlignedOrNot": "yes" or "no",\n'
        f'  "feedbackforCandidate": "Thank you for applying to {jobTitle}. After reviewing your profile, we found that your department is not aligned with the requirement for this role. We encourage you to explore opportunities better aligned with your background, as we’d love to see you grow in the right role.",\n'
        f'  "feedbackforRecruiter": "{name_of_the_candidate}’s department is not aligned with the requirement for this role."\n'
        f"}}\n\n"
        f"**Example:**\n"
        f"{{\n"
        f'  "AlignedOrNot": "no",\n'
        f'  "feedbackforCandidate": "Thank you for applying to [Job Title]. After reviewing your profile, your department is not aligned with the requirement for this role. We encourage you to explore opportunities better aligned with your background, as we’d love to see you grow in the right role.",\n'
        f'  "feedbackforRecruiter": "[Candidate Name]’s department is not aligned with the requirement for this role."\n'
        f"}}"
        )

        completion_text_rejection =  gpt_models[0].invoke_model_with_backoff(prompt,Task= "check Department id Suitable or not from Ai")
        print(completion_text_rejection)

        if not reject_on_ctc_or_exp and completion_text_rejection['AlignedOrNot'].lower()=='no':
            statment = ' reject_on_ctc_or_exp is False and  is no'
            overall_matching_score = 50
            rejectionFeedbackBySystemForApplicant = completion_text_rejection["feedbackforCandidate"]
            rejection_feedback = completion_text_rejection["feedbackforRecruiter"]
            rejection_feedback = json.dumps({"RecruiterNote":rejection_feedback})
            department_mismatch = True

    if department_mismatch or reject_on_ctc_or_exp:
        prompt = (
            f"You are an expert recruiter. Your only task is to compare the candidate profile against the job description."
            f"Only use details explicitly stated in the provided text. Do not infer, assume, or invent information."
            f"Input:"
            f"- Candidate Profile: {processed_text}"
            f"- Job Description: {job_desc}"
            f"- Extra Analysis: {overall_Analysis}"
            f"Output:"
            f"Provide recruiter feedback in JSON format with three keys: \"RecruiterNote\", \"Strengths\", and \"Areas of Concern\"."
            f"Format Example:"
            f"{{\n"
            f"  \"feedback_Recruiter\": {{\n"
            f"    \"RecruiterNote\": \"3–5 sentence recruiter-friendly summary of candidate fit, overall impression, and readiness for the role.\",\n"
            f"    \"Strengths\": [\n"
            f"      \"[name of candidate] Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
            f"      \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n"
            f"    ],\n"
            f"    \"AreasOfConcern\": [\n"
            f"      \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
            f"    ]\n"
            f"  }},\n"
            f"  \"feedback_Candidate\": {{\n"
            f"    \"CandidateNote\": \"3–5 sentence candidate-friendly summary of fit, strengths, and shortfalls written in direct and clear language.\",\n"
            f"    \"Strengths\": [\n"
            f"      \"You bring X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
            f"      \"You demonstrate proven skills in A and B, which match the mandatory requirement for this role.\"\n"
            f"    ],\n"
            f"    \"AreasOfConcern\": [\n"
            f"      \"You lack explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
            f"    ]\n"
            f"  }}\n"
            f"}}\n"
            f"Strict Rules:"
            f"1. **RecruiterNote** → A concise 2–3 line summary of candidate fit, overall impression, and readiness for the role."
            f"2. Every point in \"Strengths\" and \"Areas of Concern\" must be a **direct JD vs candidate comparison**."
            f"   - If it's not in both, do not mention it."
            f"   - If requirement is missing in profile, flag under concerns."
            f"   - If requirement is fully met/exceeded, add to strengths."
            f"3. Maximum 3 strengths and 2 concerns (total 5 points)."
            f"4. Each statement must be 15–25 words, factual, and recruiter-ready."
            f"5. Treat missing info as missing — never assume."
            f"6. Apply Special Mentions only if explicitly visible:"
            f"   - Unemployed for 12+ months."
            f"   - Frequent job changes (<1 year)."
            f"   - Experience significantly above requirement (mark as strength)."
            f"7. Do not comment on communication skills or location unless explicitly stated in both JD and profile."
            f"8. Never use phrases like \"resume shows\" or \"appears to have.\" Always describe the candidate directly."
            f"9. there must be only 2 points in AreasOfConcern and 2-3 points in Strengths"
            f" - In entire feedback never talk about number of years experience. you can talk about domain experience if needed"
            f"10. Output must be valid JSON only — no text outside JSON"
            )
        completion_text_approval= gpt_models[0].invoke_model_with_backoff(prompt,Task= "Score feedback for 50 caped case ")
        print_completion_text(completion_text_approval)
        scoreDetails = completion_text_approval.get("feedback_Recruiter")
        scoreDetails = json.dumps(scoreDetails)
        scoreDetailsForApplicant = completion_text_approval.get("feedback_Candidate")
        scoreDetailsForApplicant = json.dumps(scoreDetailsForApplicant)

#############################################################################################################################################
    if not reject_on_ctc_or_exp and not department_mismatch:
        prompt = (
            f"Analyze the following job description and classify it as either 'Technical' or 'Non-Technical':\n"
            f"Job Description:\n"
            f"{job_desc}\n"
            f"Considerations for classification:\n"
            f"- Technical roles typically involve programming, engineering, data analysis, or IT skills\n"
            f"- Non-Technical roles typically focus on business, management, sales, or operations\n"
            f"- Respond with only one word: 'Technical' or 'Non-Technical'"
            )
            
        content = invoke_model_with_backoff_nova(prompt)
        print("new content from Nova",content)
        print_completion_text(content)
        completion_text = extract_text_from_nova(content)
        print_completion_text(completion_text)
        print("Checking the completion_text",completion_text)
        
        # Initialize the variable to store the Technical or Non Technical
        found_text = ""
        
        position = completion_text.find("Non-Technical")

        if position != -1:
            found_text = completion_text[position:position+len("Non-Technical")]
            print("The text '{}' is present.".format(found_text))
        else:
            print("The text 'Non-Technical' is not present.")
        
            # Initialize steps to avoid unassigned reference
        steps = []
        
        try:
            if found_text == "Non-Technical":
                print("I am in Non-Tech")
                # Determine the experience level of JD
                prompt = (
                            f"Human: Based on the following job description, please analyze the required years of experience:\n\n"
                            f"{job_desc}\n\n"
                            f"Human: Strictly determine the experience level using ONLY these criteria:\n"
                            f"- If years of experience is greater than 12: superior\n"
                            f"- If years of experience is between 5 and 12 (inclusive): senior\n"
                            f"- If years of experience is between 1 and 5 (exclusive): junior\n"
                            f"- If years of experience is less than 1: fresher\n\n"
                            f"Respond EXACTLY in this JSON format without any additional fields or explanations:\n"
                            f"{{\n"
                            f"  \"experience_level\": \"<determined_level>\",\n"
                            f"  \"criteria_matched\": \"<exact_matching_criteria_text>\"\n"
                            f"}}\n\n"
                            f"Do not include any other fields like 'reasoning' or additional commentary. Only provide the specified JSON output."
                        )

                content = invoke_model_with_backoff_nova(prompt)
                print("I am in Non-Tech",content )
                completion_text = extract_experience_level_nova(content)
                print_completion_text(completion_text)
                        
                if "superior" in completion_text:
                    print("Experience Level - Non-Tech superior")
                    steps = [
                                    ("Here is the most relevant sentence in the context: Evaluate the resume against the job description based on the following 4 parameters and their respective weighted scores:"
                                        "1. Experience (5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                        "2. Responsibilities (10 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                        "3. Achievements (5 points) - Look for exact keyword matches or direct mentions of achievements in the resume."
                                        "4. Core Skills/Core Competencies (10 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                        "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 30 (27), cap it at 27."
                                        "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                        "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                    ),
                                    ("Here is the most relevant sentence in the context: Mandatory Skills Evaluation Framework (Total: 40 Points)"
                                        "SECTION A: SKILL-BASED EVALUATION (24 points, 60% weight)"
                                            "List all mandatory technical/core skills from the job description."
                                            "Assign equal weight to each skill:"
                                            "- If there are n mandatory skills, each skill = 24/n points"
                                            "For each skill:"
                                            "- If the candidate has the skill → award full points for that skill."
                                            "If not → 0 points."
                                            "Section A Score = Sum of points for all matched skills."
                                            "Example:"
                                            "3 mandatory skills: Java, Spring Boot, DevOps"
                                            "Each skill = 8 points"
                                            "Candidate has Java & Spring Boot only"
                                            "Section A Score = 8 + 8 + 0 = 16 points"
                                        "SECTION B: NON-SKILL-BASED EVALUATION (16 points, 40% weight)"
                                            "List all non-skill mandatory requirements (education, company, location, etc.)."
                                            "If the candidate meets ALL non-skill requirements → 16 points."
                                            "If ANY non-skill requirement is missing → 0 points."
                                            "SCORING CALCULATION"
                                            "Final Score (rounded to nearest integer) = Section A Score + Section B Score"
                                            "Maximum: 40 points"
                                        "Provide results in JSON format: {\"score\": 0-40 (rounded to nearest integer), \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                    ),
                                    ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
                                        "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                        "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 10 points to the Matching Score."
                                        "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 10 points (9) to the Matching Score."
                                        "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 10 points (5) to the Matching Score."
                                        "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 10 points (7.5) to the Matching Score."
                                        "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 10 points (8) to the Matching Score."
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
                                    ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                        "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                        "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                        " 2: RESUME ANALYSIS"
                                        "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                        "RESUME KEYWORD WEIGHTING RULES:"
                                        "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                        "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                        "- If keyword appears in skills section or technical skills: Award 2 points"
                                        "- If keyword appears in education/certification section: Award 1 point"
                                        "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                        "- If keyword is not present: Award 0 points"
                                        "STEP 3: MATCHING AND SCORING"
                                        "For each of the 15 keywords:"
                                        "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                        "2. Calculate match score using this formula:"
                                        "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                        "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                        "   - If Resume Weight = 0: Award 0 points"
                                        "STEP 4: FINAL CALCULATION"
                                        "1. Sum up all 15 keyword match scores"
                                        "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                        "3. If this sum is 18 points or less, use the exact sum as the final score"
                                        "OUTPUT FORMAT:"
                                        "Present results in JSON format:"
                                        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                        "VALIDATION RULES:"
                                        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                        "- Do not make assumptions about implied skills or experience"
                                        "- Weight keywords based strictly on their placement and context within resume sections"
                                        "- If a keyword appears in multiple sections, use the highest applicable weight"
                                    )
                                ]
                elif "senior" in completion_text:
                    print("Experience Level - Non-Tech senior")
                    steps = [
                                    ("Here is the most relevant sentence in the context: Evaluate the resume against the job description based on the following 5 parameters and their respective weighted scores:"
                                                "1. Experience (5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                                "2. Responsibilities (10 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                                "3. Achievements (5 points) - Look for exact keyword matches or direct mentions of achievements in the resume."
                                                "4. Soft Skills (5 points) - Look for exact keyword matches or direct mentions of soft skills in the resume."
                                                "5. Core Skills/Core Competencies (5 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                                "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 30 (27), cap it at 27"
                                                "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                                "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
                                                "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                    ),
                                    ("Here is the most relevant sentence in the context: Mandatory Skills Evaluation Framework (Total: 40 Points)"
                                        "SECTION A: SKILL-BASED EVALUATION (24 points, 60% weight)"
                                            "List all mandatory technical/core skills from the job description."
                                            "Assign equal weight to each skill:"
                                            "- If there are n mandatory skills, each skill = 24/n points"
                                            "For each skill:"
                                            "- If the candidate has the skill → award full points for that skill."
                                            "If not → 0 points."
                                            "Section A Score = Sum of points for all matched skills."
                                            "Example:"
                                            "3 mandatory skills: Java, Spring Boot, DevOps"
                                            "Each skill = 8 points"
                                            "Candidate has Java & Spring Boot only"
                                            "Section A Score = 8 + 8 + 0 = 16 points"
                                        "SECTION B: NON-SKILL-BASED EVALUATION (16 points, 40% weight)"
                                            "List all non-skill mandatory requirements (education, company, location, etc.)."
                                            "If the candidate meets ALL non-skill requirements → 16 points."
                                            "If ANY non-skill requirement is missing → 0 points."
                                            "SCORING CALCULATION"
                                            "Final Score (rounded to nearest integer) = Section A Score + Section B Score"
                                            "Maximum: 40 points"
                                        "Provide results in JSON format: {\"score\": 0-40 (rounded to nearest integer), \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                    ),
                                    ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
                                                "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                                "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 10 points to the Matching Score."
                                                "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 10 points (9) to the Matching Score."
                                                "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 10 points (5) to the Matching Score."
                                                "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 10 points (7.5) to the Matching Score."
                                                "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 10 points (8) to the Matching Score."
                                                "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                                "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
                                    ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                        "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                        "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                        " 2: RESUME ANALYSIS"
                                        "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                        "RESUME KEYWORD WEIGHTING RULES:"
                                        "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                        "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                        "- If keyword appears in skills section or technical skills: Award 2 points"
                                        "- If keyword appears in education/certification section: Award 1 point"
                                        "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                        "- If keyword is not present: Award 0 points"
                                        "STEP 3: MATCHING AND SCORING"
                                        "For each of the 15 keywords:"
                                        "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                        "2. Calculate match score using this formula:"
                                        "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                        "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                        "   - If Resume Weight = 0: Award 0 points"
                                        "STEP 4: FINAL CALCULATION"
                                        "1. Sum up all 15 keyword match scores"
                                        "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                        "3. If this sum is 18 points or less, use the exact sum as the final score"
                                        "OUTPUT FORMAT:"
                                        "Present results in JSON format:"
                                        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                        "VALIDATION RULES:"
                                        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                        "- Do not make assumptions about implied skills or experience"
                                        "- Weight keywords based strictly on their placement and context within resume sections"
                                        "- If a keyword appears in multiple sections, use the highest applicable weight"
                                    )
                                ]
                                
                elif "junior" in completion_text:
                    print("Experience Level - Non-Tech junior")
                    steps = [
                                    ("Here is the most relevant sentence in the context: Evaluate the resume against the job description based on the following 5 parameters and their respective weighted scores:"
                                                "1. Experience (5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                                "2. Responsibilities (10 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                                "3. Achievements (5 points) - Look for exact keyword matches or direct mentions of achievements in the resume."
                                                "4. Soft Skills (5 points) - Look for exact keyword matches or direct mentions of soft skills in the resume."
                                                "5. Core Skills/Core Competencies (5 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                                "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 30 (27), cap it at 27"
                                                "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                                "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
                                                "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                    ),
                                    ("Here is the most relevant sentence in the context: Mandatory Skills Evaluation Framework (Total: 40 Points)"
                                        "SECTION A: SKILL-BASED EVALUATION (24 points, 60% weight)"
                                            "List all mandatory technical/core skills from the job description."
                                            "Assign equal weight to each skill:"
                                            "- If there are n mandatory skills, each skill = 24/n points"
                                            "For each skill:"
                                            "- If the candidate has the skill → award full points for that skill."
                                            "If not → 0 points."
                                            "Section A Score = Sum of points for all matched skills."
                                            "Example:"
                                            "3 mandatory skills: Java, Spring Boot, DevOps"
                                            "Each skill = 8 points"
                                            "Candidate has Java & Spring Boot only"
                                            "Section A Score = 8 + 8 + 0 = 16 points"
                                        "SECTION B: NON-SKILL-BASED EVALUATION (16 points, 40% weight)"
                                            "List all non-skill mandatory requirements (education, company, location, etc.)."
                                            "If the candidate meets ALL non-skill requirements → 16 points."
                                            "If ANY non-skill requirement is missing → 0 points."
                                            "SCORING CALCULATION"
                                            "Final Score (rounded to nearest integer) = Section A Score + Section B Score"
                                            "Maximum: 40 points"
                                        "Provide results in JSON format: {\"score\": 0-40 (rounded to nearest integer), \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                    ),
                                    ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
                                                "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                                "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 10 points to the Matching Score."
                                                "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 10 points (9) to the Matching Score."
                                                "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 10 points (5) to the Matching Score."
                                                "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 10 points (7.5) to the Matching Score."
                                                "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 10 points (8) to the Matching Score."
                                                "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                                "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
                                    ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                        "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                        "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                        " 2: RESUME ANALYSIS"
                                        "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                        "RESUME KEYWORD WEIGHTING RULES:"
                                        "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                        "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                        "- If keyword appears in skills section or technical skills: Award 2 points"
                                        "- If keyword appears in education/certification section: Award 1 point"
                                        "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                        "- If keyword is not present: Award 0 points"
                                        "STEP 3: MATCHING AND SCORING"
                                        "For each of the 15 keywords:"
                                        "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                        "2. Calculate match score using this formula:"
                                        "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                        "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                        "   - If Resume Weight = 0: Award 0 points"
                                        "STEP 4: FINAL CALCULATION"
                                        "1. Sum up all 15 keyword match scores"
                                        "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                        "3. If this sum is 18 points or less, use the exact sum as the final score"
                                        "OUTPUT FORMAT:"
                                        "Present results in JSON format:"
                                        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                        "VALIDATION RULES:"
                                        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                        "- Do not make assumptions about implied skills or experience"
                                        "- Weight keywords based strictly on their placement and context within resume sections"
                                        "- If a keyword appears in multiple sections, use the highest applicable weight"
                                    )
                                ]
                                
                elif "fresher" in completion_text:
                    print("Experience Level - Non-Tech fresher")
                    steps = [
                                    ("Here is the most relevant sentence in the context: Evaluate the resume against the job description based on the following 2 parameters and their respective weighted scores:"
                                                "1. Experience (10 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                                "2. Soft Skills (15 points) - Look for exact keyword matches or direct mentions of soft skills in the resume."
                                                "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 25 (22.5), cap it at 22.5."
                                                "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                                "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
                                                "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                    ),
                                    ("Here is the most relevant sentence in the context: Additionally, check for any specific relevant experience mentioned in the job description:"
                                                "If specific relevant Project/Internship/Experience/skills is mentioned as mandatory in the job description and it is not present in the resume, add 0% of 25 points to the Matching Score."
                                                "If specific relevant Project/Internship/Experience/skills is mentioned as mandatory in the job description and it is present in the resume, add 90% of 25 points (22.5) to the Matching Score."
                                                "If specific relevant Project/Internship/Experience/skills is mentioned as non-mandatory or preferred in the job description and it is present in the resume, add 90% of 25 points (22.5) to the Matching Score."
                                                "If specific relevant Project/Internship/Experience/skills is mentioned as non-mandatory or preferred in the job description and it is not present in the resume, add 60% of 25 points (15) to the Matching Score."
                                                "Before calculating the score, identify and list the most relevant sentences from the job description that specify the required or preferred experience, and the corresponding sentences from the resume that match or do not match these requirements."
                                                "Show the points given. Present it in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                                "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
                                    ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
                                                "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                                "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 30 points to the Matching Score."
                                                "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 30 points (27) to the Matching Score."
                                                "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 30 points (15) to the Matching Score."
                                                "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 30 points (22.5) to the Matching Score."
                                                "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 30 points (24) to the Matching Score."
                                                "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                                "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
                                    ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                        "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                        "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                        " 2: RESUME ANALYSIS"
                                        "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                        "RESUME KEYWORD WEIGHTING RULES:"
                                        "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                        "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                        "- If keyword appears in skills section or technical skills: Award 2 points"
                                        "- If keyword appears in education/certification section: Award 1 point"
                                        "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                        "- If keyword is not present: Award 0 points"
                                        "STEP 3: MATCHING AND SCORING"
                                        "For each of the 15 keywords:"
                                        "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                        "2. Calculate match score using this formula:"
                                        "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                        "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                        "   - If Resume Weight = 0: Award 0 points"
                                        "STEP 4: FINAL CALCULATION"
                                        "1. Sum up all 15 keyword match scores"
                                        "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                        "3. If this sum is 18 points or less, use the exact sum as the final score"
                                        "OUTPUT FORMAT:"
                                        "Present results in JSON format:"
                                        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                        "VALIDATION RULES:"
                                        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                        "- Do not make assumptions about implied skills or experience"
                                        "- Weight keywords based strictly on their placement and context within resume sections"
                                        "- If a keyword appears in multiple sections, use the highest applicable weight"
                                    )
                                ]
        
            else:
                # Determine the experience level of JD

                prompt = (
                            f"Human: Based on the following job description, please analyze the required years of experience:\n\n"
                            f"{job_desc}\n\n"
                            f"Human: Strictly determine the experience level using ONLY these criteria:\n"
                            f"- If years of experience is greater than 12: superior\n"
                            f"- If years of experience is between 5 and 12 (inclusive): senior\n"
                            f"- If years of experience is between 1 and 5 (exclusive): junior\n"
                            f"- If years of experience is less than 1: fresher\n\n"
                            f"Respond EXACTLY in this JSON format without any additional fields or explanations:\n"
                            f"{{\n"
                            f"  \"experience_level\": \"<determined_level>\",\n"
                            f"  \"criteria_matched\": \"<exact_matching_criteria_text>\"\n"
                            f"}}\n\n"
                            f"Do not include any other fields like 'reasoning' or additional commentary. Only provide the specified JSON output."
                        )

                content = invoke_model_with_backoff_nova(prompt)
                completion_text = extract_experience_level_nova(content)
                print_completion_text(completion_text)
                
                if "superior" in completion_text:
                    print("Experience Level - Tech superior")
                    steps = [
                                ("Here is the most relevant sentence in the context: Rate the resume against the job description based on the following 5 parameters:"
                                        "1. Technical Skills (weighted score: 10 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                        "2. Experience (weighted score: 5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                        "3. Education (weighted score: 5 points) - If no specific educational requirement is mentioned, award full points for a relevant degree, regardless of the institution."
                                        "4. Responsibilities (weighted score: 10 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                        "5. Achievements (weighted score: 5 points) - Look for exact keyword matches or direct mentions of achievements in the resume."
                                        "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 35 (31.5), cap it at 31.5"
                                        "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                        "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                    ),
                                    ("Here is the most relevant sentence in the context: Mandatory Skills Evaluation Framework (Total: 40 Points)"
                                        "SECTION A: SKILL-BASED EVALUATION (24 points, 60% weight)"
                                            "List all mandatory technical/core skills from the job description."
                                            "Assign equal weight to each skill:"
                                            "- If there are n mandatory skills, each skill = 24/n points"
                                            "For each skill:"
                                            "- If the candidate has the skill → award full points for that skill."
                                            "If not → 0 points."
                                            "Section A Score = Sum of points for all matched skills."
                                            "Example:"
                                            "3 mandatory skills: Java, Spring Boot, DevOps"
                                            "Each skill = 8 points"
                                            "Candidate has Java & Spring Boot only"
                                            "Section A Score = 8 + 8 + 0 = 16 points"
                                        "SECTION B: NON-SKILL-BASED EVALUATION (16 points, 40% weight)"
                                            "List all non-skill mandatory requirements (education, company, location, etc.)."
                                            "If the candidate meets ALL non-skill requirements → 16 points."
                                            "If ANY non-skill requirement is missing → 0 points."
                                            "SCORING CALCULATION"
                                            "Final Score (rounded to nearest integer) = Section A Score + Section B Score"
                                            "Maximum: 40 points"
                                        "Provide results in JSON format: {\"score\": 0-40 (rounded to nearest integer), \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                    ),
                                ("Here is the most relevant sentence in the context: Check if any specific educational requirement is asked for in the job description (e.g., specific certification, graduation from a Tier 1 institute, specific degree type, etc.)."
                                        "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                        "For the Education parameter (weighted score: 5 points):"
                                        "- If a specific educational requirement (like graduation from a Tier 1 institute) is mandatory in the job description:"
                                        "  - If the requirement is present in the resume, add 4.5 points (90% of 5 points) to the Matching Score."
                                        "  - If the requirement is not present in the resume, add 0 points to the Matching Score."
                                        "- If a specific educational requirement (like graduation from a Tier 1 institute) is preferred in the job description:"
                                        "  - If the requirement is present in the resume, add 4.5 points (90% of 5 points) to the Matching Score."
                                        "  - If the requirement is not present in the resume, add 2.5 points (50% of 5 points) to the Matching Score."
                                        "- If no specific educational requirement is mentioned in the job description:"
                                        "  - If the resume has a Tier 1 institute educational detail, add 4 points (80% of 5 points) to the Matching Score."
                                        "  - If the resume does not have a Tier 1 institute educational detail, add 3.75 points (75% of 5 points) to the Matching Score."
                                        "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                    ),
                                ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                        "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                        "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                        " 2: RESUME ANALYSIS"
                                        "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                        "RESUME KEYWORD WEIGHTING RULES:"
                                        "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                        "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                        "- If keyword appears in skills section or technical skills: Award 2 points"
                                        "- If keyword appears in education/certification section: Award 1 point"
                                        "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                        "- If keyword is not present: Award 0 points"
                                        "STEP 3: MATCHING AND SCORING"
                                        "For each of the 15 keywords:"
                                        "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                        "2. Calculate match score using this formula:"
                                        "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                        "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                        "   - If Resume Weight = 0: Award 0 points"
                                        "STEP 4: FINAL CALCULATION"
                                        "1. Sum up all 15 keyword match scores"
                                        "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                        "3. If this sum is 18 points or less, use the exact sum as the final score"
                                        "OUTPUT FORMAT:"
                                        "Present results in JSON format:"
                                        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                        "VALIDATION RULES:"
                                        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                        "- Do not make assumptions about implied skills or experience"
                                        "- Weight keywords based strictly on their placement and context within resume sections"
                                        "- If a keyword appears in multiple sections, use the highest applicable weight"
                                    )
                        ]
                        
                elif "senior" in completion_text:
                    print("Experience Level - Tech senior")
                    steps = [
                                ("Here is the most relevant sentence in the context: Rate the resume against the job description based on the following 5 parameters:"
                                        "1. Technical Skills (weighted score: 15 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                        "2. Experience (weighted score: 5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                        "3. Education (weighted score: 5 points) - If no specific educational requirement is mentioned, award full points for a relevant degree, regardless of the institution."
                                        "4. Responsibilities (weighted score: 5 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                        "5. Achievements (weighted score: 5 points) - Look for exact keyword matches or direct mentions of achievements in the resume."
                                        "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 35 (31.5), cap it at 31.5"
                                        "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                        "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                    ),
                                    ("Here is the most relevant sentence in the context: Mandatory Skills Evaluation Framework (Total: 40 Points)"
                                        "SECTION A: SKILL-BASED EVALUATION (24 points, 60% weight)"
                                            "List all mandatory technical/core skills from the job description."
                                            "Assign equal weight to each skill:"
                                            "- If there are n mandatory skills, each skill = 24/n points"
                                            "For each skill:"
                                            "- If the candidate has the skill → award full points for that skill."
                                            "If not → 0 points."
                                            "Section A Score = Sum of points for all matched skills."
                                            "Example:"
                                            "3 mandatory skills: Java, Spring Boot, DevOps"
                                            "Each skill = 8 points"
                                            "Candidate has Java & Spring Boot only"
                                            "Section A Score = 8 + 8 + 0 = 16 points"
                                        "SECTION B: NON-SKILL-BASED EVALUATION (16 points, 40% weight)"
                                            "List all non-skill mandatory requirements (education, company, location, industry, sector, etc.)."
                                            "If the candidate meets ALL non-skill requirements → 16 points."
                                            "If ANY non-skill requirement is missing → 0 points."
                                            "SCORING CALCULATION"
                                            "Final Score (rounded to nearest integer) = Section A Score + Section B Score"
                                            "Maximum: 40 points"
                                        "Provide results in JSON format: {\"score\": 0-40 (rounded to nearest integer), \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                    ),
                                ("Here is the most relevant sentence in the context: Check if any specific educational requirement is asked for in the job description (e.g., specific certification, graduation from a Tier 1 institute, specific degree type, etc.)."
                                        "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                        "For the Education parameter (weighted score: 5 points):"
                                        "- If a specific educational requirement (like graduation from a Tier 1 institute) is mandatory in the job description:"
                                        "  - If the requirement is present in the resume, add 4.5 points (90% of 5 points) to the Matching Score."
                                        "  - If the requirement is not present in the resume, add 0 points to the Matching Score."
                                        "- If a specific educational requirement (like graduation from a Tier 1 institute) is preferred in the job description:"
                                        "  - If the requirement is present in the resume, add 4.5 points (90% of 5 points) to the Matching Score."
                                        "  - If the requirement is not present in the resume, add 2.5 points (50% of 5 points) to the Matching Score."
                                        "- If no specific educational requirement is mentioned in the job description:"
                                        "  - If the resume has a Tier 1 institute educational detail, add 4 points (80% of 5 points) to the Matching Score."
                                        "  - If the resume does not have a Tier 1 institute educational detail, add 3.75 points (75% of 5 points) to the Matching Score."
                                        "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                    ),
                                ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                        "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                        "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                        " 2: RESUME ANALYSIS"
                                        "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                        "RESUME KEYWORD WEIGHTING RULES:"
                                        "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                        "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                        "- If keyword appears in skills section or technical skills: Award 2 points"
                                        "- If keyword appears in education/certification section: Award 1 point"
                                        "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                        "- If keyword is not present: Award 0 points"
                                        "STEP 3: MATCHING AND SCORING"
                                        "For each of the 15 keywords:"
                                        "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                        "2. Calculate match score using this formula:"
                                        "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                        "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                        "   - If Resume Weight = 0: Award 0 points"
                                        "STEP 4: FINAL CALCULATION"
                                        "1. Sum up all 15 keyword match scores"
                                        "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                        "3. If this sum is 18 points or less, use the exact sum as the final score"
                                        "OUTPUT FORMAT:"
                                        "Present results in JSON format:"
                                        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                        "VALIDATION RULES:"
                                        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                        "- Do not make assumptions about implied skills or experience"
                                        "- Weight keywords based strictly on their placement and context within resume sections"
                                        "- If a keyword appears in multiple sections, use the highest applicable weight"
                                    )
                            ]
                            
                elif "junior" in completion_text:
                    print("Experience Level - Tech junior")
                    steps = [
                                ("Here is the most relevant sentence in the context: Rate the resume against the job description based on the following 5 parameters:"
                                        "1. Technical Skills (weighted score: 5 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                        "2. Experience (weighted score: 10 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                        "3. Education (weighted score: 5 points) - If no specific educational requirement is mentioned, award full points for a relevant degree, regardless of the institution."
                                        "4. Responsibilities (weighted score: 5 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                        "5. Soft Skills (weighted score: 5 points) - Look for exact keyword matches or direct mentions of soft skills in the resume."
                                        "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 30 (27), cap it at 27"
                                        "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                        "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                    ),
                                ("Here is the most relevant sentence in the context: Mandatory Skills Evaluation Framework (Total: 40 Points)"
                                        "SECTION A: SKILL-BASED EVALUATION (24 points, 60% weight)"
                                            "List all mandatory technical/core skills from the job description."
                                            "Assign equal weight to each skill:"
                                            "- If there are n mandatory skills, each skill = 24/n points"
                                            "For each skill:"
                                            "- If the candidate has the skill → award full points for that skill."
                                            "If not → 0 points."
                                            "Section A Score = Sum of points for all matched skills."
                                            "Example:"
                                            "3 mandatory skills: Java, Spring Boot, DevOps"
                                            "Each skill = 8 points"
                                            "Candidate has Java & Spring Boot only"
                                            "Section A Score = 8 + 8 + 0 = 16 points"
                                        "SECTION B: NON-SKILL-BASED EVALUATION (16 points, 40% weight)"
                                            "List all non-skill mandatory requirements (education, company, location, etc.)."
                                            "If the candidate meets ALL non-skill requirements → 16 points."
                                            "If ANY non-skill requirement is missing → 0 points."
                                            "SCORING CALCULATION"
                                            "Final Score (rounded to nearest integer) = Section A Score + Section B Score"
                                            "Maximum: 40 points"
                                        "Provide results in JSON format: {\"score\": 0-40 (rounded to nearest integer), \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                    ),
                                ("Here is the most relevant sentence in the context: Check if any specific educational requirement is asked for in the job description (e.g., specific certification, graduation from a Tier 1 institute, specific degree type, etc.)."
                                        "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                        "For the Education parameter (weighted score: 10 points):"
                                        "- If a specific educational requirement (like graduation from a Tier 1 institute) is mandatory in the job description:"
                                        "  - If the requirement is present in the resume, add 9 points (90% of 10 points) to the Matching Score."
                                        "  - If the requirement is not present in the resume, add 0 points to the Matching Score."
                                        "- If a specific educational requirement (like graduation from a Tier 1 institute) is preferred in the job description:"
                                        "  - If the requirement is present in the resume, add 9 points (90% of 10 points) to the Matching Score."
                                        "  - If the requirement is not present in the resume, add 5 points (50% of 10 points) to the Matching Score."
                                        "- If no specific educational requirement is mentioned in the job description:"
                                        "  - If the resume has a Tier 1 institute educational detail, add 8 points (80% of 10 points) to the Matching Score."
                                        "  - If the resume does not have a Tier 1 institute educational detail, add 7.5 points (75% of 10 points) to the Matching Score."
                                        "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                    ),
                                ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                        "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                        "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                        " 2: RESUME ANALYSIS"
                                        "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                        "RESUME KEYWORD WEIGHTING RULES:"
                                        "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                        "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                        "- If keyword appears in skills section or technical skills: Award 2 points"
                                        "- If keyword appears in education/certification section: Award 1 point"
                                        "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                        "- If keyword is not present: Award 0 points"
                                        "STEP 3: MATCHING AND SCORING"
                                        "For each of the 15 keywords:"
                                        "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                        "2. Calculate match score using this formula:"
                                        "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                        "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                        "   - If Resume Weight = 0: Award 0 points"
                                        "STEP 4: FINAL CALCULATION"
                                        "1. Sum up all 15 keyword match scores"
                                        "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                        "3. If this sum is 18 points or less, use the exact sum as the final score"
                                        "OUTPUT FORMAT:"
                                        "Present results in JSON format:"
                                        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                        "VALIDATION RULES:"
                                        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                        "- Do not make assumptions about implied skills or experience"
                                        "- Weight keywords based strictly on their placement and context within resume sections"
                                        "- If a keyword appears in multiple sections, use the highest applicable weight"
                                    )
                            ]
                            
                elif "fresher" in completion_text:
                    print("Experience Level - Tech fresher")
                    steps = [
                                ("Here is the most relevant sentence in the context: Rate the resume against the job description based on the following 4 parameters:"
                                        "1. Technical Skills (weighted score: 15 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                                "a. Check if the job description mentions a specific requirement for relevant technical experience as mandatory."
                                                "  - If it is mandatory and the relevant technical experience is present in the resume, add 13.5 points (90% of 15 points) to the Matching Score."
                                                "  - If it is mandatory and the relevant technical experience is not present in the resume, add 0 points to the Matching Score."
                                                "b. If the job description mentions relevant technical experience as non-mandatory or preferred:"
                                                "  - If it is present in the resume, add 13.5 points (90% of 15 points) to the Matching Score."
                                                "  - If it is not present in the resume, add 9 points (60% of 15 points) to the Matching Score."
                                        "2. Experience (weighted score: 5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                        "3. Education (weighted score: 5 points) - If no specific educational requirement is mentioned, award full points for a relevant degree, regardless of the institution."
                                        "4. Soft Skills (weighted score: 5 points) - Look for exact keyword matches or direct mentions of soft skills in the resume."
                                        "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 30 (27), cap it at 27"
                                        "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                        "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                    ),
                                ("Here is the most relevant sentence in the context: Mandatory Skills Evaluation Framework (Total: 40 Points)"
                                        "SECTION A: SKILL-BASED EVALUATION (24 points, 60% weight)"
                                            "List all mandatory technical/core skills from the job description."
                                            "Assign equal weight to each skill:"
                                            "- If there are n mandatory skills, each skill = 24/n points"
                                            "For each skill:"
                                            "- If the candidate has the skill → award full points for that skill."
                                            "If not → 0 points."
                                            "Section A Score = Sum of points for all matched skills."
                                            "Example:"
                                            "3 mandatory skills: Java, Spring Boot, DevOps"
                                            "Each skill = 8 points"
                                            "Candidate has Java & Spring Boot only"
                                            "Section A Score = 8 + 8 + 0 = 16 points"
                                        "SECTION B: NON-SKILL-BASED EVALUATION (16 points, 40% weight)"
                                            "List all non-skill mandatory requirements (education, company, location, etc.)."
                                            "If the candidate meets ALL non-skill requirements → 16 points."
                                            "If ANY non-skill requirement is missing → 0 points."
                                            "SCORING CALCULATION"
                                            "Final Score (rounded to nearest integer) = Section A Score + Section B Score"
                                            "Maximum: 40 points"
                                        "Provide results in JSON format: {\"score\": 0-40 (rounded to nearest integer), \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                    ),
                                ("Here is the most relevant sentence in the context: Check if any specific educational requirement is asked for in the job description (e.g., specific certification, graduation from a Tier 1 institute, specific degree type, etc.)."
                                        "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                        "For the Education parameter (weighted score: 10 points):"
                                        "- If a specific educational requirement (like graduation from a Tier 1 institute) is mandatory in the job description:"
                                        "  - If the requirement is present in the resume, add 9 points (90% of 10 points) to the Matching Score."
                                        "  - If the requirement is not present in the resume, add 0 points to the Matching Score."
                                        "- If a specific educational requirement (like graduation from a Tier 1 institute) is preferred in the job description:"
                                        "  - If the requirement is present in the resume, add 9 points (90% of 10 points) to the Matching Score."
                                        "  - If the requirement is not present in the resume, add 5 points (50% of 10 points) to the Matching Score."
                                        "- If no specific educational requirement is mentioned in the job description:"
                                        "  - If the resume has a Tier 1 institute educational detail, add 8 points (80% of 10 points) to the Matching Score."
                                        "  - If the resume does not have a Tier 1 institute educational detail, add 7.5 points (75% of 10 points) to the Matching Score."
                                        "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                    ),
                                ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                        "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                        "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                        " 2: RESUME ANALYSIS"
                                        "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                        "RESUME KEYWORD WEIGHTING RULES:"
                                        "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                        "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                        "- If keyword appears in skills section or technical skills: Award 2 points"
                                        "- If keyword appears in education/certification section: Award 1 point"
                                        "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                        "- If keyword is not present: Award 0 points"
                                        "STEP 3: MATCHING AND SCORING"
                                        "For each of the 15 keywords:"
                                        "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                        "2. Calculate match score using this formula:"
                                        "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                        "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                        "   - If Resume Weight = 0: Award 0 points"
                                        "STEP 4: FINAL CALCULATION"
                                        "1. Sum up all 15 keyword match scores"
                                        "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                        "3. If this sum is 18 points or less, use the exact sum as the final score"
                                        "OUTPUT FORMAT:"
                                        "Present results in JSON format:"
                                        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                        "VALIDATION RULES:"
                                        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                        "- Do not make assumptions about implied skills or experience"
                                        "- Weight keywords based strictly on their placement and context within resume sections"
                                        "- If a keyword appears in multiple sections, use the highest applicable weight"
                                    )
                            ]
    
            for i, step in enumerate(steps):
                prompt = create_prompt(processed_text, job_desc, step)
                
                # Use different model invocation functions for each step
                if i == 0:
                    
                    #************************Start Old Models***********************************
                    # content = invoke_model_with_backoff_claude(prompt)
                    # final_completion_text = extract_text(content)
                    # print_completion_text(final_completion_text)
                    # temp_score = extract_score_from_response(final_completion_text)
                    # overall_Analysis = overall_Analysis + final_completion_text

                    # if temp_score is None:
                    #     temp_score = extract_score_from_response(final_completion_text)

                    # # Cap temp_score at 27 if it's greater than 27
                    # if temp_score is not None and temp_score > 27:
                    #     temp_score = 27
                    #************************End Old Models***********************************
                    
                    # Adding code for Open AI processing
                    content = gpt_models[0].invoke_model_with_backoff(prompt,Task= "step 1 for score calculations" ,want_json=False)
                    print("Open AI content",content)
                    overall_Analysis = overall_Analysis + content
                    temp_score = extract_score_from_OpenAI_response(content)
                    # temp_score = temp_score.get('score')

                    if temp_score is None:
                        temp_score = extract_score_from_OpenAI_response(content)

                    # Cap temp_score at 27 if it's greater than 27
                    if temp_score is not None and temp_score > 27:
                        temp_score = 27

                elif i == 1:
                    
                    #************************Start Old Models***********************************
                    # content = invoke_model_with_backoff_claude(prompt)
                    # final_completion_text = extract_text(content)
                    # print_completion_text(final_completion_text)
                    # temp_score = extract_score_from_response(final_completion_text)
                    # overall_Analysis = overall_Analysis + final_completion_text

                    # if temp_score is None:
                    #     temp_score = extract_score_from_response(final_completion_text)
                    
                    # # Cap temp_score at 36 if it's greater than 36
                    # if temp_score is not None and temp_score > 36:
                    #     temp_score = 36
                    #************************End Old Models***********************************
                    
                    # Adding code for Open AI processing
                    content = gpt_models[0].invoke_model_with_backoff(prompt,Task= "step 2 for score calculations", want_json=False)
                    print("Open AI content",content)
                    overall_Analysis = overall_Analysis + content
                    temp_score = extract_score_from_OpenAI_response(content)

                    if temp_score is None:
                        temp_score = extract_score_from_OpenAI_response(content)
                    
                    # Cap temp_score at 36 if it's greater than 36
                    if temp_score is not None and temp_score > 36:
                        temp_score = 36

                elif i == 2:
                    #************************Start Old Models***********************************
                    # print("Original Prompt",prompt)
                    # updated_prompt = f"Analyze this candidate. {college_status}\n {prompt}"
                    # print("Original Prompt",updated_prompt)
                    # content = invoke_model_with_backoff_deepseek(updated_prompt)
                    # print("content",content)
                    # temp_score = extract_score_from_json_deepseek(content)
                    # overall_Analysis = overall_Analysis + content

                    # if temp_score is None:
                    #     temp_score = extract_score_from_json_deepseek(content)
                    
                    # # Cap temp_score at 9 if it's greater than 9
                    # if temp_score is not None and temp_score > 9:
                    #     temp_score = 9
                    #************************End Old Models***********************************    
                    
                    # Adding code for Open AI processing
                    # print("Original Prompt",prompt)
                    # updated_prompt = f"Analyze this candidate. {college_status}\n {prompt}"
                    # print("Original Prompt",updated_prompt)
                    content = gpt_models[0].invoke_model_with_backoff(prompt,Task= "step 3 for score calculations", want_json=False)
                    print("Open AI content",content)
                    overall_Analysis = overall_Analysis + content
                    temp_score = extract_score_from_OpenAI_response(content)

                    if temp_score is None:
                        temp_score = extract_score_from_OpenAI_response(content)

                    # Cap temp_score at 9 if it's greater than 9
                    if temp_score is not None and temp_score > 9:
                        temp_score = 9

                elif i == 3:
                    
                    #************************Start Old Models***********************************
                    # content = invoke_model_with_backoff_mistral(prompt, model_id = "mistral.mistral-large-2402-v1:0")
                    # parsed_data = process_response(content)
                    # print_completion_text(content)
                    # temp_score = float(parsed_data.get('score', 0))
                    # overall_Analysis = overall_Analysis + content

                    # if temp_score is None:
                    #     temp_score = float(parsed_data.get('score', 0))

                    # # Cap temp_score at 18 if it's greater than 18
                    # if temp_score is not None and temp_score > 18:
                    #     temp_score = 18
                    #************************End Old Models***********************************

                    # Adding code for Open AI processing
                    content = gpt_models[0].invoke_model_with_backoff(prompt,Task= "step 4 for score calculations", want_json=False)
                    print("Open AI content",content)
                    overall_Analysis = overall_Analysis + content
                    temp_score = extract_score_from_OpenAI_response(content)

                    if temp_score is None:
                        temp_score = extract_score_from_OpenAI_response(content)
                    
                    # Cap temp_score at 18 if it's greater than 18
                    if temp_score is not None and temp_score > 18:
                        temp_score = 18
                else:
                    # Fallback to original function if there are more steps than defined functions
                    content = invoke_model_with_backoff_nova(prompt)

                # If temp_score is coming from the JSON as a list
                if isinstance(temp_score, list) and len(temp_score) > 0:
                    temp_score = temp_score[0]
                # If it's already been converted to a string representation of a list
                elif isinstance(temp_score, str) and temp_score.startswith('[') and temp_score.endswith(']'):
                    temp_score = temp_score.strip('[]')

                print("temp_score", temp_score)
                
                if temp_score is not None:
                    overall_matching_score = ensure_decimal(overall_matching_score)
                    temp_score = ensure_decimal(temp_score)
                    overall_matching_score = overall_matching_score + temp_score
                else:
                    print("No valid score found in this response")

                # print("overall_matching_score", overall_matching_score)
                # print("overall_Analysis:-", overall_Analysis)
            # overall_matching_score = 72
            # if "JOB" in job_ref_type:    # update score as soon as you get it (its changing in case of mandatory not met)
            #     update_ref_matching_score_in_dynamodb(jobs_table_name, partition_key_value, sort_key_prefix2, overall_matching_score)
            # else:
            #     update_ref_matching_score_in_dynamodb(table_name, partition_key_value, sort_key_prefix2, overall_matching_score)
            overall_matching_score = int(round(overall_matching_score))
            # print("overall_matching_score", overall_matching_score)
            # print("overall_Analysis:-", overall_Analysis)

            if "JOB" in job_ref_type and job_feedbacks:
                if Experience_mismatched:
                    if newThreshHoldF_for_exp.get("min",""):                  #substract 10 marks if exp does not machtes
                        if YOE_from_cv <= newThreshHoldF_for_exp["min"] and overall_matching_score>40:
                            
                            th = newThreshHoldF_for_exp["min"]
                            print(f"deducted 10 Marks becouse candidate is having less or eauqls {th} years of experience as per the previous feedbacks it should be greater then {YOE_from_cv} years. Initial Marks :- {overall_matching_score} updated marks :- {overall_matching_score-10}")
                            overall_matching_score -=10
                            
                            
                    if newThreshHoldF_for_exp.get("max",""):
                        if YOE_from_cv >= newThreshHoldF_for_exp["max"] and overall_matching_score >40:
                            th = newThreshHoldF_for_exp["max"]
                            print(f"deducted 10 Marks becouse candidate is having greater or eauqls {th} years of experience as per the previous feedbacks it should be less then {YOE_from_cv} years. Initial Marks :- {overall_matching_score} updated marks :- {overall_matching_score-10}")
                            overall_matching_score -=10
                            
                        
                # requirementsFormFeedback.append('Candidate must have chemical education background')       ## test
                if candidate_feedbacks:
                    prompt = (
                        f"You are a world-class HR Expert and Hiring Strategist with 40+ years of experience across technical and non-technical domains. and you are provided with all feedbak of a candidate\n\n"
                        f"Your job is to perform a *feedback-by-feedback audit* of a candidate’s and refram them as job requiremnets.\n\n"
                        f"example input : he don't know python , output : candidate must know python"
                        f"candidate_feedbacks : {candidate_feedbacks}"
                        f"### output formate must be a json as given below.\n"
                        f"  {{\n"
                        f'    "Requirements": ["Must have experience in SQL", "candidate msut know python language"]\n'
                        f"  }},\n"
                    )
                    candidate_feedbacks_requirements =  gpt_models[0].invoke_model_with_backoff(prompt,Task= "Ask ai, extract candidate feedback",want_json=False)
                    print("candidate_feedbacks_requirements : -",candidate_feedbacks_requirements)

                    prompt = (
                    f"You are a world-class HR Expert and Hiring Strategist with 40+ years of experience across technical and non-technical domains. and you are provided with all feedbak of a candidate\n\n"
                    f"your task is to Determine for each requirement whether it is asked in Job Description or not, if requirement is present in jd say yes otherwise say no. based **only** on explicit evidence from the Job Description text.\n\n"
                    f"### Job Description :\n{jdItem_extracted}\n\n"
                    f"### Requirements:\n{candidate_feedbacks_requirements}\n\n"
                    f"### Evaluation Rules:\n"
                    f"1. Always match requirement-by-requirement, not overall impression.\n"
                    f"2. Extract the exact matching sentence/phrase from resume text in 'partOfcandidateJobDescription'.\n"
                    f"   - If nothing matches, set 'partOfcandidateJobDescription': 'null'.\n"
                    f"3. Never include extra explanation or commentary outside JSON.\n"
                    f"4. The output must be strictly valid JSON — no markdown, no trailing commas, no commentary.\n\n"
                    f"5. Be verry concise if anything mentioned under should have, must have don't get confused if it is asked in jd the say yes with every requirements if not met exactly say MetOrNot == no and if asked in job description then say yes"
                    f"### Output Format (Strict JSON Array)\n"
                    f"Return an array where each element corresponds to one requirement from the job description:\n\n"
                    f"[\n"
                    f"  {{\n"
                    f'    "Requirements": "<exact requirement text>",\n'
                    f'    "MetOrNot": "yes" or "no",\n'
                    f'    "partOfcandidateJobDescription": "<exact JobDescription text that supports or contradicts the requirement>"\n'
                    f"  }},\n"
                    f"  ...\n"
                    f"]\n\n"
                    f"### Example Output:\n"
                    f"[\n"
                    f"  {{\n"
                    f'    "Requirements": "Must have experience in Python and SQL.",\n'
                    f'    "MetOrNot": "yes",\n'
                    f'    "partOfcandidateJobDescription": "good to have experience in python."\n'
                    f"  }},\n"
                    f"  {{\n"
                    f'    "Requirements": "Experience in sell side of catagory managemnt.",\n'
                    f'    "MetOrNot": "no",\n'
                    f'    "partOfcandidateJobDescription": "null"\n'
                    f"  }}\n"
                    f"]\n\n"
                    f"Now, analyze the Requirements **against each JobDescription one by one** and provide your final JSON response below — strictly following the above format."
                    )
                    candidate_feedbacks_requirements_MetOrNot =  gpt_models[0].invoke_model_with_backoff(prompt,Task= "Ask ai, extract candidate feedback")
                    print("candidate_feedbacks_requirements_MetOrNot :--",candidate_feedbacks_requirements_MetOrNot)
                    number_of_candidate_feedbacks_requirements_MetOrNot=False
                    try:
                        number_of_candidate_feedbacks_requirements_MetOrNot = len([i for i in candidate_feedbacks_requirements_MetOrNot if i["MetOrNot"].lower()=='yes'])
                        print(f'Requirements not met from candidate_feedback :--',number_of_candidate_feedbacks_requirements_MetOrNot)
                    except Exception as e:
                        number_of_candidate_feedbacks_requirements_MetOrNot=False
                        print("cheching requiremnet from feedback faild",e)

                    if number_of_candidate_feedbacks_requirements_MetOrNot:
                        
                        if 3>number_of_candidate_feedbacks_requirements_MetOrNot>0:
                            deduct_marks = number_of_candidate_feedbacks_requirements_MetOrNot*5
                            if overall_matching_score>70:
                                overall_matching_score -= deduct_marks
                                print(f'Diducting {deduct_marks} marks because {number_of_candidate_feedbacks_requirements_MetOrNot} requirements from  candidate feedback are not met ')

                        elif number_of_candidate_feedbacks_requirements_MetOrNot>=3:
                            
                            print(f'reducing score {overall_matching_score} to 60 becouse 3 or more the 3 requirements from candidate feedback are not met ')
                            overall_matching_score=55


                if requirementsFormFeedback:
                    prompt = (
                    f"You are a world-class HR Expert and Hiring Strategist with 40+ years of experience across technical and non-technical domains.\n\n"
                    f"Your job is to perform a *requirement-by-requirement audit* of a candidate’s resume against the job description requirements below.\n\n"
                    f"### Objective:\n"
                    f"Determine for each requirement in the Job Description whether the candidate meets it or not, based **only** on explicit evidence from the resume text.\n\n"
                    f"### Job Description Requirements:\n{requirementsFormFeedback}\n\n"
                    f"### Candidate’s Resume:\n{processed_text}\n\n"
                    f"### Evaluation Rules:\n"
                    f"1. Be objective, literal, and specific.\n"
                    f"   - Match only if the resume clearly shows proof (skills, Domain, experience, education, project, etc.).\n"
                    f"   - If the requirement is not found or only implied, classify it as 'no'.\n"
                    f"2. Do not assume or infer skills.\n"
                    f"   - Example: If JD asks for 'Power BI' and resume mentions 'Excel dashboards', mark it as 'no'.\n"
                    f"3. Always match requirement-by-requirement, not overall impression.\n"
                    f"4. Extract the exact matching sentence/phrase from resume text in 'partOfcandidateResume'.\n"
                    f"   - If nothing matches, set 'partOfcandidateResume': 'null'.\n"
                    f"5. Never include extra explanation or commentary outside JSON.\n"
                    f"6. The output must be strictly valid JSON — no markdown, no trailing commas, no commentary.\n\n"
                    f"7. Be verry specific with every requirements if not met exactly say MetOrNot == no"
                    f"### Output Format (Strict JSON Array)\n"
                    f"Return an array where each element corresponds to one requirement from the job description:\n\n"
                    f"[\n"
                    f"  {{\n"
                    f'    "Requirements": "<exact requirement text>",\n'
                    f'    "MetOrNot": "yes" or "no",\n'
                    f'    "partOfcandidateResume": "<exact resume text that supports or contradicts the requirement>"\n'
                    f"  }},\n"
                    f"  ...\n"
                    f"]\n\n"
                    f"### Example Output:\n"
                    f"[\n"
                    f"  {{\n"
                    f'    "Requirements": "Must have experience in Python and SQL.",\n'
                    f'    "MetOrNot": "yes",\n'
                    f'    "partOfcandidateResume": "Worked as a Data Analyst using Python and SQL for data automation projects."\n'
                    f"  }},\n"
                    f"  {{\n"
                    f'    "Requirements": "Experience in sell side of catagory managemnt.",\n'
                    f'    "MetOrNot": "no",\n'
                    f'    "partOfcandidateResume": "null"\n'
                    f"  }}\n"
                    f"]\n\n"
                    f"Now, analyze the candidate’s resume **against each job requirement one by one** and provide your final JSON response below — strictly following the above format."
                    )

                    feedbackMachingWithCandidate =  gpt_models[0].invoke_model_with_backoff(prompt,Task= "Ask ai, feedback matching or not")
                    print('feedbackMachingWithCandidate :- ' ,feedbackMachingWithCandidate)
                    number_of_requirements_not_met = False 
                    try:
                        number_of_requirements_not_met = len([i for i in feedbackMachingWithCandidate if i["MetOrNot"].lower()=='no'])
                        print(f'Requirements not met from feedback :--',number_of_requirements_not_met)
                    except Exception as e:
                        number_of_requirements_not_met=False
                        print("cheching requiremnet from feedback faild",e)
                    if number_of_requirements_not_met:
                        
                        if 3>number_of_requirements_not_met>0:
                            deduct_marks = number_of_requirements_not_met*5
                            if overall_matching_score>70:
                                overall_matching_score -= deduct_marks
                                print(f'Diducting {deduct_marks} marks because {number_of_requirements_not_met} requirements from feedback are not met ')

                        elif number_of_requirements_not_met>=3:
                            
                            print(f'reducing score {overall_matching_score} to 60 becouse 3 or more the 3 requirements from feedback are not met ')
                            overall_matching_score=55

            # overall_matching_score=50 #testing
            if 1 <= overall_matching_score < 70:
                prompt = (f"candidate profile : {processed_text}, job requirements : {jdItem_extracted}\n"
                    f"Analyze why this candidate scored low against job requirements highlight. Return response in exact JSON format:\n"
                    f"JSON must contain exactly two top-level keys: feedback_Recruiter and feedback_Candidate\n"
                    f"{{\n"
                    f"  \"feedback_Recruiter\": {{\n"
                    f"    \"RecruiterNote\": \"3–5 sentence recruiter-friendly summary of candidate fit, overall impression, and readiness for the role.\",\n"
                    f"    \"Strengths\": [\n"
                    f"      \"[name of candidate] Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                    f"      \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                    f"    ],\n"
                    f"    \"AreasOfConcern\": [\n"
                    f"      \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                    f"    ]\n"
                    f"  }},\n"
                    f"  \"feedback_Candidate\": {{\n"
                    f"    \"CandidateNote\": \"3–5 sentence candidate-friendly summary of fit, strengths, and shortfalls written in direct and clear language.\",\n"
                    f"    \"Strengths\": [\n"
                    f"      \"You bring X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                    f"      \"You demonstrate proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                    f"    ],\n"
                    f"    \"AreasOfConcern\": [\n"
                    f"      \"You lack explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                    f"    ]\n"
                    f"  }}\n"
                    f"}}\n"
                    f"Strict Rule 1 :\n"
                    f"1. RecruiterNote → Concise 3–5 line factual summary of candidate fit and readiness.\n"
                    f"2. Every point in Strengths and AreasOfConcern must be a direct Job Description vs Candidate comparison only.\n"
                    f"   - If requirement not present in JD or Candidate Profile → do not mention.\n"
                    f"   - If requirement in JD but missing in Candidate Profile → flag under AreasOfConcern.\n"
                    f"   - If requirement in JD and fully/over met → include under Strengths.\n"
                    f"3. Limit: max 3 strengths and 2 concerns (5 points total).\n"
                    f"4. Each point must be 15–25 words, sharp, factual, recruiter-ready.\n"
                    f"5. Treat missing info as missing — never assume.\n"
                    f"6. Apply Special Mentions only if explicitly visible in Candidate Profile:\n"
                    f"   - Unemployed 12+ months.\n"
                    f"   - Frequent job changes (<1 year).\n"
                    f"   - Experience significantly above requirement (mark as strength).\n"
                    f"Strict Rule 2 :\n"
                    f"In RecruiterNote → Never use speculative phrases like 'resume shows' or 'appears to have'. State facts directly.with calling candidate. [name of candidate] have 15+ experience in...\n"
                    f"Strict Rule 3 :\n"
                    f"In CandidateNote → Never use speculative phrases like 'your resume shows' or 'appears to have'. State facts directly with 'you...'\n"
                    f"Requirements:\n"
                    f"- Total 3 items focusing on critical gaps that caused rejection.\n"
                    f"- Each detail must be a direct 15–25 word statement starting with 'Candidate has no...' or 'Candidate lacks...'\n"
                    f"- Headings should be meaningful and aligned with the issue (e.g., 'Missing Required Certification', 'Insufficient Industry Experience').\n"
                    f"- Never start headings with 'Candidate has no...' — that's for the details.\n"
                    f"- Focus only on missing mandatory requirements from the JD.\n"
                    f"- Flag: Educational gaps, experience above requirement, missing technical skills, insufficient industry experience, absent certifications, lacking leadership/management, career inconsistencies.\n"
                    f"- Special Mentions: Extended unemployment 12+ months, frequent short tenure roles <1 year.\n"
                    f"- Location: Only mention if candidate explicitly states inability to work in required location.\n"
                    f"- Language: Only mention if candidate explicitly lacks required language skills.\n"
                    f"- Tone: Objective, professional, decision-focused.\n"
                    f"- There must be only 2 points in AreasOfConcern and 2-3 points in Strengths"
                    f" - In entire feedback never talk about number of years experience. you can talk about domain experience if needed"
                    f"- Omit detail field if heading itself is self-explanatory.\n"
                )



                        
    
                completion_text_rejection = gpt_models[0].invoke_model_with_backoff(prompt,Task= "Rejection for 1 <= overall_matching_score < 70:" )
                # content = invoke_model_with_backoff_OpenAI(prompt)
                # completion_text_rejection = clean_json_response(content)
                # try:
                #     completion_text_rejection = json.loads(completion_text_rejection)
                # except Exception as e:
                #     print("can't load this feed back json in 1-70 rejection")

                completion_text_rejection_for_candidate = completion_text_rejection.get("feedback_Candidate")
                completion_text_rejection= completion_text_rejection.get("feedback_Recruiter")
                

                completion_text_rejection = json.dumps(completion_text_rejection)        ### make it string again to store in db
                completion_text_rejection_for_candidate = json.dumps(completion_text_rejection_for_candidate)

                print_completion_text(f"rjection feedback for Recruiter {completion_text_rejection}")
                print_completion_text(f"rjection feedback for Candidate {completion_text_rejection_for_candidate}")
                rejection_feedback = completion_text_rejection
                rejectionFeedbackBySystemForApplicant = completion_text_rejection_for_candidate

                
                if overall_matching_score >= 40:
                    prompt = (f"You are an expert recruiter. Your only task is to compare the candidate profile against the job description."
                            f"Only use details explicitly stated in the provided text. Do not infer, assume, or invent information."
                            f"Input:"
                            f"- Candidate Profile: {processed_text}"
                            f"- Job Description: {job_desc}"
                            f"- Extra Analysis: {overall_Analysis}"
                            f"Output:"
                            f"Provide recruiter feedback in JSON format with three keys: \"RecruiterNote\", \"Strengths\", and \"Areas of Concern\"."
                            f"Format Example:"
                            f"{{\n"
                            f"  \"feedback_Recruiter\": {{\n"
                            f"    \"RecruiterNote\": \"3–5 sentence recruiter-friendly summary of candidate fit, overall impression, and readiness for the role.\",\n"
                            f"    \"Strengths\": [\n"
                            f"      \"[name of candidate] Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                            f"      \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                            f"    ],\n"
                            f"    \"AreasOfConcern\": [\n"
                            f"      \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                            f"    ]\n"
                            f"  }},\n"
                            f"  \"feedback_Candidate\": {{\n"
                            f"    \"CandidateNote\": \"3–5 sentence candidate-friendly summary of fit, strengths, and shortfalls written in direct and clear language.\",\n"
                            f"    \"Strengths\": [\n"
                            f"      \"You bring X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                            f"      \"You demonstrate proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                            f"    ],\n"
                            f"    \"AreasOfConcern\": [\n"
                            f"      \"You lack explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                            f"    ]\n"
                            f"  }}\n"
                            f"}}\n"
                            f"Strict Rules:"
                            f"1. **RecruiterNote** → A concise 2–3 line summary of candidate fit, overall impression, and readiness for the role."
                            f"2. Every point in \"Strengths\" and \"Areas of Concern\" must be a **direct JD vs candidate comparison**."
                            f"   - If it's not in both, do not mention it."
                            f"   - If requirement is missing in profile, flag under concerns."
                            f"   - If requirement is fully met/exceeded, add to strengths."
                            f"3. Maximum 3 strengths and 2 concerns (total 5 points)."
                            f"4. Each statement must be 15–25 words, factual, and recruiter-ready."
                            f"5. Treat missing info as missing — never assume."
                            f"6. Apply Special Mentions only if explicitly visible:"
                            f"   - Unemployed for 12+ months."
                            f"   - Frequent job changes (<1 year)."
                            f"   - Experience significantly above requirement (mark as strength)."
                            f"7. Do not comment on communication skills or location unless explicitly stated in both JD and profile."
                            f"8. Never use phrases like \"resume shows\" or \"appears to have.\" Always describe the candidate directly."
                            f"9. there must be only 2 points in AreasOfConcern and 2-3 points in Strengths"
                            f" - In entire feedback never talk about number of years experience. you can talk about domain experience if needed"
                            f"10. Output must be valid JSON only — no text outside JSON"
                            )
                    
                    # content = invoke_model_with_backoff_nova(prompt)
                    # completion_text_approval = extract_text_from_nova(content)
                    # print_completion_text(completion_text_approval)
                    # scoreDetails = completion_text_approval

                    completion_text_approval= gpt_models[0].invoke_model_with_backoff(prompt,Task= "Score feedback  for >40")
                    print_completion_text(completion_text_approval)
                    scoreDetails = completion_text_approval.get("feedback_Recruiter")
                    scoreDetailsForApplicant = completion_text_approval.get("feedback_Candidate")
                    # content = invoke_model_with_backoff_OpenAI(prompt)
                    # completion_text_approval = clean_json_response(content)
                    # try:
                    #     completion_text_approval = json.loads(completion_text_approval)
                    # except Exception as e:
                    #     print("can't load this feed back json in >40 scoreDetails")



                    scoreDetails = json.dumps(scoreDetails)        ### make it string again to store in db
                    scoreDetailsForApplicant = json.dumps(scoreDetailsForApplicant)        ### make it string again to store in db
                
                if overall_matching_score >= 40:
                    prompt = (f"{completion_text_approval}\n"
                            f"Based on the above content, write a one-line summary in 20-25 words that highlights ONLY the positive qualities and strengths that make this candidate suitable for the job.\n"
                            f"Focus exclusively on positive aspects - exclude any negative feedback or criticisms.")

                    # content = invoke_model_with_backoff_nova(prompt)
                    # emailFeedback = extract_text_from_nova(content)
                    emailFeedback = gpt_models[0].invoke_model_with_backoff(prompt,want_json=False)
                    print("feedback_for_email:-",emailFeedback)
            
            elif overall_matching_score >= 70:
                prompt = (f"You are an expert recruiter. Your only task is to compare the candidate profile against the job description."
                            f"Only use details explicitly stated in the provided text. Do not infer, assume, or invent information."
                            f"Input:"
                            f"- Candidate Profile: {processed_text}"
                            f"- Job Description: {job_desc}"
                            f"- Extra Analysis: {overall_Analysis}"
                            f"Output:"
                            f"Provide recruiter feedback in JSON format with two keys: feedback_Recruiter, feedback_Candidate"
                            f"Each feedback will have three keys: \"Note\", \"Strengths\", and \"Areas of Concern\"."
                            f"Format Example:"
                            f"{{\n"
                            f"  \"feedback_Recruiter\": {{\n"
                            f"    \"RecruiterNote\": \"3–5 sentence recruiter-friendly summary of candidate fit, overall impression, and readiness for the role.\",\n"
                            f"    \"Strengths\": [\n"
                            f"      \"[name of candidate] Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                            f"      \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                            f"    ],\n"
                            f"    \"AreasOfConcern\": [\n"
                            f"      \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                            f"    ]\n"
                            f"  }},\n"
                            f"  \"feedback_Candidate\": {{\n"
                            f"    \"CandidateNote\": \"3–5 sentence candidate-friendly summary of fit, strengths, and shortfalls written in direct and clear language.\",\n"
                            f"    \"Strengths\": [\n"
                            f"      \"You bring X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                            f"      \"You demonstrate proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                            f"    ],\n"
                            f"    \"AreasOfConcern\": [\n"
                            f"      \"You lack explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                            f"    ]\n"
                            f"  }}\n"
                            f"}}\n"
                            f"Strict Rules:"  
                            f"1. **RecruiterNote or CandidateNote ** → A concise 3–5 line summary of candidate fit, overall impression, and readiness for the role."  
                            f"2. Every point in \"Strengths\" and \"Areas of Concern\" must be a **direct Job Description vs Candidate comparison** only."  
                            f"   - If requirement is not present in Job Description or Candidate Profile, do not mention it."  
                            f"   - If requirement is in Job Description but missing in Candidate Profile, flag it under concerns."  
                            f"   - If requirement is in Job Description and fully/over met in Candidate Profile, add it under strengths."  
                            f"3. Limit to maximum **3 strengths** and **2 concerns** (total 5 points)."  
                            f"4. Each point must be **15–25 words**, sharp, factual, and recruiter-ready."  
                            f"5. Treat missing info as missing — never assume or generalize."  
                            f"6. Apply Special Mentions only if explicitly visible in Candidate Profile:"  
                            f"   - Unemployed for 12+ months."  
                            f"   - Frequent job changes (<1 year)."  
                            f"   - Experience significantly above requirement (mark as strength)." 
                            f"7.Use natural, direct language that sounds human-written, not AI-generated\n"
                            f"- Flag: Educational qualification gaps\n"
                            f"- Flag: Experience is higher than the required experience for the job\n"
                            f"- Flag: Critical technical skills missing\n"
                            f"- Flag: Industry experience insufficient\n"
                            f"- Flag: Required certifications absent\n"
                            f"- Flag: Leadership/management experience lacking when required\n"
                            f"- Flag: Career progression inconsistencies\n"
                            f"- SPECIAL MENTION: Extended unemployment periods (12+ months)\n"
                            f"- SPECIAL MENTION: Pattern of short tenure roles (<1 year)\n"
                            f"- LOCATION RULE: Only mention location concerns if candidate explicitly states inability to work from required location in resume. If location not mentioned, assume candidate is willing to work from any location.\n"
                            f"- LANGUAGE RULE: Only mention language deficiency if candidate explicitly lacks required languages in resume. If languages not mentioned, assume candidate has required language skills.\n"
                            f"- Tone should be objective, professional, and decision-focused for HR evaluation\n" 
                            
                            f"8. Focus only on **Job Description requirements matched with candidate evidence** — highlight why candidate deserves shortlist."  
                            f"9. Keep summary **crisp, keyword-heavy**, pulling exact terms from Job Description and Job Description."  
                            f"10. if you say skills matches tell which particular skill which is direct from Candidate Profile and Job Description, if you say experience matches then tell which particular experience matches."
                            f"11. Never say anything in a broad perspective just porvide all the exact reasons from Candidate Profile that why this is a ideal candidate."
                            f"12. Do not mention communication skills, cultural fit, or location unless explicitly present in both Job Description and Resume."  
                            f"13. -For RecruiterNote never use speculative phrases like 'resume shows' or 'appears to have' — state facts directly with calling candidate name."
                            f"    -For CandidateNote never use speculative phrases like 'your resume shows' or 'appears to have' — talk dierectly with candidate. state facts directly with calling candidate name."
                            f"15. **EXACT WORDING RULE**: Only use terminology explicitly stated in the resume/Job Description. Never generalize specific implementations into broader industry terms."
                            f"16. **NO DOMAIN INFERENCE**: Do not infer industry expertise from individual projects or features. State only the specific technologies/projects mentioned."
                            f"17. **FACT-CHECK REQUIREMENT**: Before including any point, verify the exact phrase exists in either the Job Description or Candidate Profile text."
                            f"18. there must be only 2 points in AreasOfConcern and 2-3 points in Strengths"
                            f" - In entire feedback never talk about number of years experience. you can talk about domain experience if needed"
                            f"19. **GRANULAR SPECIFICITY**: When mentioning experience, reference the exact role/company where it was gained, not as broad industry background."  
                            f"20. Output format must be **valid JSON only**, no text outside JSON."   
        
                        )
                
                # content = invoke_model_with_backoff_nova(prompt)
                # completion_text_approval = extract_text_from_nova(content)
                # print_completion_text(completion_text_approval)
                # scoreDetails = completion_text_approval

                completion_text_approval =gpt_models[0].invoke_model_with_backoff(prompt,Task= "Score feedback for >70")


                ###########################################
                print_completion_text(completion_text_approval)
                try:
                    # completion_text_approval = json.loads(completion_text_approval)
                    scoreDetails = completion_text_approval.get("feedback_Recruiter")
                    scoreDetailsForApplicant = completion_text_approval.get("feedback_Candidate")
                except Exception as e:
                    print("can't load scoreDetails and scoreDetailsForApplicant from json in >=70 scoreDetails")



                scoreDetails = json.dumps(scoreDetails)        ### make it string again to store in db
                scoreDetailsForApplicant = json.dumps(scoreDetailsForApplicant)        ### make it string again to store in db
                ###########################################


                # scoreDetails = completion_text_approval

                prompt = (f"{completion_text_approval}\n"
                        f"Based on the above content, write a one-line summary in 20-25 words that highlights ONLY the positive qualities and strengths that make this candidate suitable for the job.\n"
                        f"Focus exclusively on positive aspects - exclude any negative feedback or criticisms.do not give output like here is feeback or any thing like this just give feedback no system message")

                content = invoke_model_with_backoff_nova(prompt)
                emailFeedback = extract_text_from_nova(content)
                # emailFeedback= invoke_model_with_backoff_OpenAI(prompt,Task= "Cheching Mandatory Requirements",want_json=False) 
                
                print("feedback_for_email:-", emailFeedback)
                

                print("otherRequirements:-", otherRequirements)
                if otherRequirements:
                    # otherRequirements  = str(otherRequirements) + "candidate must have experience working in zomato"  #test

       
                    
                    prompt = (f"You are a precise resume analysis assistant. Your task is to determine if a candidate meets ALL mandatory requirements.\n\n"
                                f"**Resume Content:**\n"
                                f"{processed_text}\n\n"
                                f"**Mandatory Requirements:**\n"
                                f"{otherRequirements}\n\n"
                                f"**Critical Parsing Instructions:**\n"
                                f"You need to check Resume Content whether the Mandatory Requirements met by candidate or Not be verry strict and do not over evaluate candidate. say yes or Not"
                                f"all Mandatory Requirements should strictly match with Resume then only say No otherwise If any one Mandatory Requirement is not met say directly Yes"
                                f"1. FIRST, carefully parse the requirements text to identify individual requirements\n"
                                f"2. Look for conjunctions like 'and', semicolons, bullet points, or numbered lists that separate requirements\n"
                                f"3. Pay attention to negations like 'not necessary', 'not required' - these typically indicate something is NOT a requirement\n"
                                f"4. If a sentence contains multiple clauses, break them down logically\n"
                                f"5. Example: 'Must have X and Y is not necessary' = Two items: 'Must have X' (required) + 'Y is not necessary' (Y is NOT required)\n\n"
                                f" if Mandatory Requirements is NA or Null the it mean there is no Mandatory Requirements provided in job description in this case say No "
                                f"**Analysis Instructions:**\n"
                                f"1. For each identified requirement, look for clear, explicit evidence in the resume\n"
                                f"2. A requirement is 'met' only if there is direct evidence or reasonable inference from resume content\n"
                                f"3. For work authorization: Look for explicit statements, citizenship mentions, or work history patterns that indicate legal work status\n"
                                f"4. For location/relocation: Consider current location and any mobility statements\n"
                                f"5. For skills/experience: Look for direct mentions, project descriptions, or work history that demonstrates the skill\n"
                                f"6. If ANY mandatory requirement lacks sufficient evidence, flag as missing\n"
                                f"7. Be reasonably conservative but not overly strict - use professional judgment\n\n"
                                f"Example: Must have a tier 1 college degree Output --> Yes"
                                f"**Required JSON Response Format:**\n"
                                f"{{\n"
                                f'    "mandatory_skills_missing": "Yes" or "No",\n'
                                f'    "analysis": {{\n'
                                f'        "parsed_requirements": ["list each individual requirement you identified"],\n'
                                f'        "requirements_met": ["requirements with sufficient evidence"],\n'
                                f'        "requirements_missing": ["requirements lacking evidence"],\n'
                                f'        "evidence_summary": {{\n'
                                f'            "requirement_1": "evidence found or reason for missing",\n'
                                f'            "requirement_2": "evidence found or reason for missing"\n'
                                f"        }},\n"
                                f'        "confidence_level": "High" or "Medium" or "Low"\n'
                                f"    }}\n"
                                f"}}\n\n"
                                f"**Important Guidelines:**\n"
                                f"- Use professional judgment to parse complex requirement strings\n"
                                f"- Look for explicit evidence but allow reasonable inferences from work history\n"
                                f"- If requirements are unclear or contradictory, note this in your analysis\n"
                                f"- Respond with valid JSON only, no additional text")
                        
                    # content = invoke_model_with_backoff_nova(prompt)
                    # analysis_result = extract_text_from_nova(content)
                    
                    # content = invoke_model_with_backoff_claude(prompt)  #cloud
                    # analysis_result = extract_text(content)

                    analysis_result_json  = gpt_models[0].invoke_model_with_backoff(prompt,Task= "Cheching Mandatoey Requirements") 
                    # content = invoke_model_with_backoff_OpenAI(prompt)   #open ai
                    # analysis_result = clean_json_response(content)
                    print("analysis_result",analysis_result_json)
                    requirements_missing = analysis_result_json["analysis"]["requirements_missing"]
                    # analysis_result_json = json.loads(analysis_result)
                    mandatory_skills_missing = analysis_result_json.get('mandatory_skills_missing')
                    print("mandatory_skills_missing:-", mandatory_skills_missing)
                    
                    if mandatory_skills_missing == "Yes":
                        print(f"mandatory Requirements is missing so actual score was {overall_matching_score} now making it to 60")
                        overall_matching_score = 60

                        prompt = (
                            f"Analyze why this candidate scored low against job mandatory requirements. Return response in exact JSON format:\n"
                            f"JSON must contain exactly two top-level keys: feedback_Recruiter and feedback_Candidate\n"
                            f"{{\n"
                            f"  \"feedback_Recruiter\": {{\n"
                            f"    \"RecruiterNote\": \"3–5 sentence recruiter-friendly summary of candidate fit, overall impression, and readiness for the role.\",\n"
                            f"    \"Strengths\": [\n"
                            f"      \"[name of candidate] Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                            f"      \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                            f"    ],\n"
                            f"    \"AreasOfConcern\": [\n"
                            f"      \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                            f"    ]\n"
                            f"  }},\n"
                            f"  \"feedback_Candidate\": {{\n"
                            f"    \"CandidateNote\": \"3–5 sentence candidate-friendly summary of fit, strengths, and shortfalls written in direct and clear language.\",\n"
                            f"    \"Strengths\": [\n"
                            f"      \"You bring X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                            f"      \"You demonstrate proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                            f"    ],\n"
                            f"    \"AreasOfConcern\": [\n"
                            f"      \"You lack explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                            f"    ]\n"
                            f"  }}\n"
                            f"}}\n"
                            f"Strict Rule 1 :\n"
                            f"1. RecruiterNote → Concise 3–5 line factual summary of candidate fit and readiness.\n"
                            f"2. Every point in Strengths and AreasOfConcern must be a direct Job Description vs Candidate comparison only.\n"
                            f"   - If requirement not present in JD or Candidate Profile → do not mention.\n"
                            f"   - If requirement in JD but missing in Candidate Profile → flag under AreasOfConcern.\n"
                            f"   - If requirement in JD and fully/over met → include under Strengths.\n"
                            f"3. Limit: max 3 strengths and 2 concerns (5 points total).\n"
                            f"4. Each point must be 15–25 words, sharp, factual, recruiter-ready.\n"
                            f"5. Treat missing info as missing — never assume.\n"
                            f"6. Apply Special Mentions only if explicitly visible in Candidate Profile:\n"
                            f"   - Unemployed 12+ months.\n"
                            f"   - Frequent job changes (<1 year).\n"
                            f"   - Experience significantly above requirement (mark as strength).\n"
                            f"Strict Rule 2 :\n"
                            f"In RecruiterNote → Never use speculative phrases like 'resume shows' or 'appears to have'. State facts directly.with calling candidate. [name of candidate] have 15+ experience in...\n"
                            f"Strict Rule 3 :\n"
                            f"In CandidateNote → Never use speculative phrases like 'your resume shows' or 'appears to have'. State facts directly with 'you...'\n"
                            f"Requirements:\n"
                            f"- Each detail must be a direct 15–25 word statement starting with 'Candidate has no...' or 'Candidate lacks...'\n"
                            f"- Focus only on missing mandatory requirements from the JD.\n"
                            f"- Flag: Educational gaps, experience above requirement, missing technical skills, insufficient industry experience, absent certifications, lacking leadership/management, career inconsistencies.\n"
                            f"- Special Mentions: Extended unemployment 12+ months, frequent short tenure roles <1 year.\n"
                            f"- Location: Only mention if candidate explicitly states inability to work in required location.\n"
                            f"- Language: Only mention if candidate explicitly lacks required language skills.\n"
                            f"- Tone: Objective, professional, decision-focused.\n"
                            f"- There must be only 2 points in AreasOfConcern and 2-3 points in Strengths"
                            f" - In entire feedback never talk about number of years experience in AreasOfConcern. you can talk about domain experience if needed"
                            f"- Omit detail field if heading itself is self-explanatory.\n"
                            f"candidate profile : {processed_text}, job requirements : {jdItem_extracted}\n"
                            f"these are some of missing requirements in this candidate focus on these while generating feedback {requirements_missing}"
                            f"- **Last check** In entire feedback there must not be contracdiction if finds any correct it."
                        )

                        # prompt = (
                        #     f"**Resume Content:**{processed_text}"
                        #     f"**job Description:**{jdItem_extracted} \n"
                        #     f"**mandatory_skills: {mandatory_skills_missing} analys these structured ananlysis report and understand which requiremnts are met and which are not."
                        #     f"Analyze why this candidate scored low against job requirements in Mandatory Requirements. Return response in exact JSON format:\n"
                        #     f"Output:"
                        #     f"Provide recruiter feedback in JSON format with two keys: feedback_Recruiter, feedback_Candidate"
                        #     f"Each feedback will have three keys: \"Note\", \"Strengths\", and \"Areas of Concern\"."
                        #     f"Format Example:"
                        #     f"{{\n"
                        #     f"  \"feedback_Recruiter\": {{\n"
                        #     f"    \"RecruiterNote\": \"3–5 sentence recruiter-friendly summary of candidate fit, overall impression, and readiness for the role.\",\n"
                        #     f"    \"Strengths\": [\n"
                        #     f"      \"[name of candidate] Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                        #     f"      \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                        #     f"    ],\n"
                        #     f"    \"AreasOfConcern\": [\n"
                        #     f"      \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                        #     f"    ]\n"
                        #     f"  }},\n"
                        #     f"  \"feedback_Candidate\": {{\n"
                        #     f"    \"CandidateNote\": \"3–5 sentence candidate-friendly summary of fit, strengths, and shortfalls written in direct and clear language.\",\n"
                        #     f"    \"Strengths\": [\n"
                        #     f"      \"You bring X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                        #     f"      \"You demonstrate proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                        #     f"    ],\n"
                        #     f"    \"AreasOfConcern\": [\n"
                        #     f"      \"You lack explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                        #     f"    ]\n"
                        #     f"  }}\n"
                        #     f"}}\n"
                        #     f"Requirements:\n"
                        #     f"1. -For RecruiterNote never use speculative phrases like 'resume shows' or 'appears to have' — state facts directly with calling candidate name."
                        #     f"    -For CandidateNote never use speculative phrases like 'your resume shows' or 'appears to have' — talk dierectly with candidate. state facts directly with calling candidate name or saying you don't have..."
                        #     f"    -For CandidateNote evry missing  Mandatory Requirements must be included. and it should always start with you or name of the candidate."
                        #     f"    -For CandidateNote Never say candidate always talk directly to candidate. it must start with you or name of the candidate."
                        #     f"2. you are generating a rejection feedback so focuse more on what skills or Requirements candidate is not having and tell straightforward"
                        #     f"- Never talk about total years of experience in area of concern."
                        #     f"- Each Note detail should be one direct statement (15-25 words) starting with 'Candidate'\n"
                        #     f"- Note should be meaningful just dont put 'critical deficiency', it should match with the message\n"
                        #     f"- Heading should not start with 'name of candidate has no...' or 'name of candidate lacks...'never reference 'resume' or 'CV'\n"
                        #     f"- In detail, always write 'Candidate has no...' or 'Candidate lacks...' - never reference 'resume' or 'CV'\n"
                        #     f"- Focus on what the person doesn't have, not what their document doesn't show\n"
                        #     f"- Examples: 'Candidate has no digital marketing experience' or 'Candidate lacks required Python skills'\n"
                        #     f"- Highlight missing mandatory requirements that caused low score\n"
                        #     f"3. Use natural, direct language that sounds human-written, not AI-generated\n"
                        #     f"- Flag: Educational qualification gaps\n"
                        #     f"- Flag: Experience is higher than the required experience for the job\n"
                        #     f"- Flag: Critical technical skills missing\n"
                        #     f"- Flag: Industry experience insufficient\n"
                        #     f"- Flag: Required certifications absent\n"
                        #     f"- Flag: Leadership/management experience lacking when required\n"
                        #     f"- Flag: Career progression inconsistencies \n"
                        #     f"4. there must be only 2 points in AreasOfConcern and 2-3 points in Strengths"
                        #     f" - In entire feedback never talk about number of years experience. you can talk about domain experience if needed"
                        #     f"- SPECIAL MENTION: Extended unemployment periods (12+ months)\n"
                        #     f"- SPECIAL MENTION: Pattern of short tenure roles (<1 year)\n"
                        #     f"- LOCATION RULE: Only mention location concerns if candidate explicitly states inability to work from required location in resume. If location not mentioned, assume candidate is willing to work from any location.\n"
                        #     f"- LANGUAGE RULE: Only mention language deficiency if candidate explicitly lacks required languages in resume. If languages not mentioned, assume candidate has required language skills.\n"
                        #     f"- Tone should be objective, professional, and decision-focused for HR evaluation\n"
                        #     f"- Last check : GO through entre feedback once again and if RecruiterNote and Strengths if they are contradicting with each other then correct it by taking right statment from Resume and jd.\n"
                        #     f"5. Validate every line of feedback from Resume Content it should valid with respect to Resume Content"
                        #     )
                        
                        # content = invoke_model_with_backoff_nova(prompt)
                        # completion_text_rejection = extract_text_from_nova(content)
                        # print_completion_text(completion_text_rejection)
                        # rejection_feedback = completion_text_rejection
                        # print("******mandatory_skills_missing Issue******:", overall_matching_score)


                        completion_text_rejection =  gpt_models[0].invoke_model_with_backoff(prompt,Task= "Rejection when amndatory Not met")
                        # content = invoke_model_with_backoff_OpenAI(prompt)
                        # completion_text_rejection = clean_json_response(content)
                        # try:
                        #     completion_text_rejection = json.loads(completion_text_rejection)
                        # except Exception as e:
                        #     print("can't load this feed back json in 1-70 rejection")

                        completion_text_rejection_for_candidate = completion_text_rejection.get("feedback_Candidate")
                        completion_text_rejection= completion_text_rejection.get("feedback_Recruiter")
                        

                        completion_text_rejection = json.dumps(completion_text_rejection)        ### make it string again to store in db
                        completion_text_rejection_for_candidate = json.dumps(completion_text_rejection_for_candidate)  ### make it string again to store in db

                        print_completion_text(f"rejection feedback for Recruiter {completion_text_rejection}")
                        print_completion_text(f"rejection feedback for Candidate {completion_text_rejection_for_candidate}")
                        
                        rejection_feedback = completion_text_rejection
                        rejectionFeedbackBySystemForApplicant = completion_text_rejection_for_candidate

                        print_completion_text(f"Score feedback for Recruiter {scoreDetails}")
                        print_completion_text(f"Score feedback for Candidate {scoreDetailsForApplicant}")
    

            elif overall_matching_score == 0:
                rejection_feedback = "We encountered an error while processing. Please try again after some time"
            
            if overall_matching_score > 90:
                print("******Potential Issue******:", overall_matching_score)
                overall_matching_score = 90

            # update_sqs_queue(email, userId, referralId, job_ref_type) recently comented
            print("overall_matching_score", overall_matching_score)
        except Exception as e:
            print(f"An error occurred: {e}")
            if "JOB" in job_ref_type:
                update_cv_extract_in_dynamodb(jobs_table_name, partition_key_value, sort_key_prefix2, str(e) , 251, -1)
            else:
                update_cv_extract_in_dynamodb(table_name, partition_key_value, sort_key_prefix2, str(e) , 251, -1)

            # update_sqs_queue(email, userId, referralId, job_ref_type) recently comented
            return {"statusCode": 500, "body": {"error": str(e)}}
    elif reject_on_ctc_or_exp:
        overall_matching_score = 50
        

        if not name_of_the_candidate:              # if name of the candidate is not there just say 'you'
            name_of_the_candidate = 'your'
        reason  = get_reason_from_rejection_data(check_exp_data)
        rejectionFeedbackBySystemForApplicant = f"""Thank you for applying to {jobTitle}. After reviewing your profile, 
        we found a mismatch — your {reason} the requirement for this role. We encourage you to explore opportunities better 
        aligned with your background, 
        as we’d love to see you grow in the right role."""
        
        rejection_feedback = f"""{name_of_the_candidate} appled for {jobTitle} role. After reviewing his profile, we found a mismatch — his {reason} the requirement for this role."""
        rejection_feedback = json.dumps({"RecruiterNote":rejection_feedback})
    
    if "JOB" in job_ref_type:
        update_ref_response_in_dynamodb(jobs_table_name, partition_key_value, sort_key_prefix2, scoreDetails,scoreDetailsForApplicant, overall_matching_score, emailFeedback, rejection_feedback,rejectionFeedbackBySystemForApplicant,check_exp_data,reject_on_ctc_or_exp)
        
    else:
        update_ref_response_in_dynamodb(table_name, partition_key_value, sort_key_prefix2, scoreDetails,scoreDetailsForApplicant, overall_matching_score, emailFeedback, rejection_feedback,rejectionFeedbackBySystemForApplicant)
    
    update_sqs_queue(email, userId, referralId, job_ref_type)
    return {"statusCode": 200, "body": 
            {"Overall Matching Score": overall_matching_score}
        }


# if __name__ == "__main__":
    
    
    # event ={'USER_PK': 'USR#EML#ask.72544@gmail.com', 'USER_DETAIL_SK': 'ID#', 'MATCHING_ENTITY': 'JOB_APP', 'ENTITY_SK': 'JOB#APP#ID#01KJCSD7G4CGQNQYEGWFK3V9VK'}
    
    # form submit flow event
    
    # event ={'USER_PK': 'USR#EML#syadavendra@gmail.com', 'USER_DETAIL_SK': 'ID#', 'ENTITY_SK': 'JOB#APP#ID#01KJC783RRGAJ1EXXEV9KARE8X', 'MATCHING_ENTITY': 'SOURCE_TYPE_JOB_APP', 'candidateParsedCvId': '01KJC77XNPRW652J3GSYCDXREP', 'sourceTypeCvAwsS3Details': {'resourceType': 'CAND_SUBMIT_CV_JOB', 'bucketName': 'worko-app-dev', 'filePath': 'candidate-submit-cvs/companies/01K47MSBKS79ACY0BM6Z8VS3F5/jobs/01KHZVWRAG1H29PNBX6FQ4RYJW/cvs', 'fileName': '01KJC779BZ9D6J9YA75T30P7WD.pdf'}}
    
    #request from move to aplicant from my database
    # event = {'USER_PK': 'USR#EML#sahanasgp7@gmail.com', 'USER_DETAIL_SK': 'ID#', 'ENTITY_SK': 'JOB#APP#ID#01KJPQ9GK51XSH4JBDP6FKJRGB', 'MATCHING_ENTITY': 'SOURCE_TYPE_JOB_APP', 'candidateParsedCvId': '01KHXASXJ694280F3KY45AK6MR', 'sourceTypeCvAwsS3Details': {'resourceType': 'CORP_CAND_BULK_CV_UPLOAD', 'bucketName': 'worko-corporate-cand-profile-dev', 'filePath': 'companies/01K47MSBKS79ACY0BM6Z8VS3F5/bulk-cvs', 'fileName': '01KHXAS6YPNDWRDTJ1GVECX7G1.pdf'}}

    # lambda_handler(event, None)




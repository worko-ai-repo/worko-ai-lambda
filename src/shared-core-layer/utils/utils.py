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
from botocore.exceptions import ClientError


# Initialize Bedrock clients
sqs_region = 'ap-south-1'
region = 'us-east-1'
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client(service_name='bedrock', region_name = region)
bedrock_runtime = boto3.client(service_name='bedrock-runtime', region_name = region)
sqs = boto3.client('sqs')
s3_client = boto3.client('s3')

from pathlib import Path
import sys
if __name__ == "__main__":
    shared_layer_path = Path(__file__).parent.parent / "shared-core-layer"
    sys.path.insert(0, str(shared_layer_path))
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

def update_ref_response_in_dynamodb_for_bulk_process(table_name, partition_key, sort_key, cv_extract, cv_extracted_parsed, scoreDetails, matchingScore, rejection_feedback, emailFeedback, processing_status):
    
    try:
        print("saving data in dynamo")
        print(table_name, partition_key, sort_key, cv_extract, cv_extracted_parsed, scoreDetails, matchingScore, rejection_feedback, emailFeedback, processing_status)
        cv_extracted_parsed = convert_numbers_to_decimal(cv_extracted_parsed)
        table = dynamodb.Table(table_name)
        current_datetime = datetime.now().isoformat()
        jdMatchErrorCode = 200
        jdMatchErrorDesc = "Score is generated successfully"
        response = table.update_item(
            Key={
                'PK': partition_key,
                'SK': sort_key
            },
            UpdateExpression="SET jdMatchErrorDesc=:jdMatchErrorDesc, scoreDetails=:scoreDetails, matchingScore=:matchingScore, jdMatchErrorCode=:jdMatchErrorCode, scoreFetchedDate=:scoreFetchedDate, rejectionFeedbackBySystem=:rejectionFeedbackBySystem, cvExtract=:cvExtract, cvExtractedParsed=:cvExtractedParsed, emailFeedback=:emailFeedback, processingStatus=:processingStatus",
            ExpressionAttributeValues={
                ':jdMatchErrorDesc': jdMatchErrorDesc,
                ':scoreDetails': scoreDetails,
                ':matchingScore': matchingScore,
                ':jdMatchErrorCode': jdMatchErrorCode,
                ':scoreFetchedDate': current_datetime,
                ':rejectionFeedbackBySystem': rejection_feedback,
                ':cvExtract': cv_extract,
                ':cvExtractedParsed': cv_extracted_parsed,
                ':emailFeedback' : emailFeedback,
                ':processingStatus': processing_status
            },
            ReturnValues="UPDATED_NEW"
        )
        return response
    except Exception as e:
        print("failed saving data in dynamo becouse of ", e)

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

        # Define the SQS queue URLazure
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


def get_secret(secret_name):

    secrets_client = boto3.client('secretsmanager', region_name='ap-south-1')

    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret_value = response['SecretString']
        
        # Try to parse as JSON, fallback to string
        try:
            secret_data = json.loads(secret_value)
            gcp_credentials = secret_data
        except json.JSONDecodeError:
            secret_data = secret_value
        return secret_data
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"Secret '{secret_name}' not found")
            raise Exception(f"Secret '{secret_name}' not found")
        raise

def process_cv(processed_text: str,gpt_models) -> Tuple[str, Dict[str, str]]:
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

    cv_extract_template = {
    "Name": "",
    "Email": "",
    "Experience in years": "",
    "Achievements": "",
    "Technical skills": "",
    "Soft skills": "",
    "Core skills": "",
    "Education": "",
    "Industry experience": "",
    "Responsibilities": "",
    "Achievements against responsibility": "",
    "Certifications": "",
    "Strength": "",
    "Experience type (leadership, Mid management, Senior management, Team lead, Individual contributor)": "",
    "Team handling experience": "",
    "Industry type (B2B, D2C, C2C, B2C)": ""
    }

    cv_parsed_template = {
        "candidateName": "Parsing Failed",
        "candidateExperience": "",
        "candidateCurrentCompany": "",
        "candidateCurrentDesignation": "",
        "candidateEmail": "",
        "candidatePhoneNumber": "",
        "candidateLocation": ""
    }
     
    # cv_parsed_template ={
    # "candidateName": "Rohith Appala",
    # "candidateEmail": "rohithappala777@gmail.com",
    # "candidatePhoneNumber": "+919666308100",
    # "candidateNumber": 9666308100,
    # "candidatePhoneCountryCode": 91,
    # "candidateCurrentCompany": "Worko.ai-India",
    # "candidateCurrentDesignation": "NodeJs Backend Developer",
    # "candidateExperience": 3,
    # "candidateTotalYOE": 3,
    # "candidateRelevantYOE": 4,
    # "candidateCurrentCTC": 10,
    # "candidateExpectedCTC": 9,
    # "candidateNoticePeriod": 60,
    # "candidateLocation": "Hyderabad, Telangana",
    # "candidateReadyToRelocate": False,
    # "isNoticePeriodNegotiable": False
    # }

    if not processed_text:
        return "Unfortunately, we are not able to read your resume", cv_parsed_template

    try:
        # First extraction for CV details
        cv_prompt = (f"Extract professional CV/resume information from the following text. "
                    f"This is for legitimate recruitment purposes.\n\n"
                    f"CV TEXT: {processed_text}\n\n"
                    f"EXTRACTION TEMPLATE:\n{cv_extract_template}")
        cv_extract = gpt_models[0].invoke_model_with_backoff(cv_prompt,Task= "get cv_extract",want_json=False)
        
        # cv_extract = clean_text(cv_extract)
        print("cv_extract-------",cv_extract)
        
       
            # f"  \"candidateCurrentCTC\": 0,\n"
            # f"  \"candidateExpectedCTC\": 0,\n"
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
            f"1. candidatePhoneNumber: number with country code (string), 2. candidateNumber:  number only without country code (int), 3. candidatePhoneCountryCode (int), 4.candidateNoticePeriod int or Null"
            f"Rule to return null values:\n"
            f" if any str key is not given in in resume text just return Null for that partcular fild "
            f" example :candidateNoticePeriod,candidateLocation"
            f" candidateLocation must be only city name followed by state name examples. Mumbai, Maharahstra,  Bengaluru Karnataka"


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

            f"  \"candidateNoticePeriod\":  \"\",\n"
            f"  \"candidateLocation\": \"\",\n"
            f"  \"candidateReadyToRelocate\": false,\n"
            f"  \"isNoticePeriodNegotiable\": false\n"
            f"}}}}\n"
        )


        # cv_extracted_parsed = invoke_model_with_backoff_OpenAI(parsed_prompt,Task= "get cvExtractparsed" )
        cv_extracted_parsed = gpt_models[0].invoke_model_with_backoff(parsed_prompt,Task= "get cvExtractparsed " )
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

        # cv_extracted_parsed2 = invoke_model_with_backoff_OpenAI(prompt,Task = "Agency Resume parsing for skills and pref")
        cv_extracted_parsed2 = gpt_models[0].invoke_model_with_backoff(prompt,Task= "Resume parsing for skills and pref " )
        merged = {**cv_extracted_parsed, **cv_extracted_parsed2}
        merged = process_parsed_cv_json(merged)
        return cv_extract, merged
        
    except requests.exceptions.HTTPError as e:
        print(" Error occured : from open ai asuure.",e)
        return "Error processing CV", cv_parsed_template
    except Exception as e:
        print(f"Error processing CV: {str(e)}")
        return "Error processing CV", cv_parsed_template


def jd_resume_matching(table_name, partition_key_value, gcp_models, sort_key_prefix, job_desc, processed_text, cv_extract, cv_extracted_parsed,gpt_models,otherRequirements,jdItem_extracted):
    # Import here to avoid circular imports
    from scoring.get_scoring import get_score
    from feedback.feedback_generator import get_feedback_for_bulk_upload
    
    # Determine if job is non-technical
    print("*****************************Job Description******************************************")
    try:

        print(type(job_desc),type(processed_text), str(job_desc)[:100], str(processed_text)[:100])
        score_obj = get_score(processed_text, job_desc, gcp_models)
        overall_matching_score = score_obj["overall_matching_score"]

        print("overall_matching_score in lambda", overall_matching_score, type(overall_matching_score))
        # print("overall_Analysis:-", overall_Analysis)

        final_completion_text, rejection_feedback, emailFeedback = get_feedback_for_bulk_upload(overall_matching_score,processed_text,job_desc,gpt_models,otherRequirements)

        processing_status = "COMPLETED"
        update_ref_response_in_dynamodb_for_bulk_process(table_name, partition_key_value, sort_key_prefix,cv_extract, cv_extracted_parsed, final_completion_text, overall_matching_score, rejection_feedback, emailFeedback,processing_status)
        
    except Exception as e:
        print(f"An error occurred: {e}")
        # update_cv_extract_in_dynamodb(table_name, partition_key_value, sort_key_prefix, str(e) , 251, -1)
        return {"statusCode": 500, "body": {"error": str(e)}}
    
    return {"statusCode": 200, "body": 
        {"Overall Matching Score": overall_matching_score}
    }


#libraries for agency bulk lambda
def get_account_id():
    # Create STS client
    sts_client = boto3.client('sts')

    # Call get-caller-identity
    response = sts_client.get_caller_identity()

    # Extract account ID
    return response['Account']


def update_sqs_queue_agency(queue_url,agencyBulkJdResumeId):

    # Determine the event based on type
        

        event = "AGENCY_BULK_JD_RESUME_POST_MATCHING_SCORE"
        message_body ={
            "event": event,
            "agencyBulkJdResumeId": agencyBulkJdResumeId,
        }


        message_body_msg = json.dumps(message_body)
        
        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=message_body_msg
            )
        
        return {
            'statusCode': 200,
            'body': json.dumps('Message sent to SQS!')
        }


#################################  worko resume parsing lambda ########################################

# def update_sqs_queue_resume_parser(userId,ID):
#     event = "UPDATE_CV_CENTRAL_CAND_PROFILE"
#     email = userId.split("#")[-1]
#     queue_name = 'worko-app-event-queue'
#     # Determine the event based on type
#     # event = "REFERRAL_VALIDATE_MATCHING_SCORE"
#     message_body ={
#         "event": event,
#         "userEmail" : email,
#         "userId": ID}


#     print("event:-", event,"message_body",message_body)

#     # Define the SQS queue URL
#     account_id = get_account_id()
#     queue_url = f"https://sqs.ap-south-1.amazonaws.com/{account_id}/worko-app-event-queue"
#     # queue_url = f'https://sqs.{sqs_region}.amazonaws.com/{account_id}/{queue_name}'
    
#     message_body_msg = json.dumps(message_body)
    
#     response = sqs.send_message(
#         QueueUrl=queue_url,
#         MessageBody=message_body_msg
#         )
    
#     return {
#         'statusCode': 200,
#         'body': json.dumps('Message sent to SQS!')
#     }


# def process_parsed_cv_json_resume_parser(cv_obj):
#     try:
#         if not isinstance(cv_obj, dict):
#             return cv_obj
        
#         # Helper function to clean array items
#         def clean_array_items(arr):
#             if not isinstance(arr, list):
#                 return arr
#             return [
#                 {k: v for k, v in item.items() if v not in (None, "", [], {}, "null", "NULL")}
#                 for item in arr
#                 if isinstance(item, dict)
#             ]
        
#         # Process all arrays that contain objects
#         array_fields = ["education", "multipleCandidateExperience", "coreSkills", "technicalSkills", "softSkills"]
#         cleaned_arrays = {}
        
#         for field in array_fields:
#             if field in cv_obj:
#                 cleaned_array = clean_array_items(cv_obj[field])
#                 if cleaned_array:  # Only add back if not empty
#                     cleaned_arrays[field] = cleaned_array
        
#         # Remove null/empty values from top level
#         cv_obj = {k: v for k, v in cv_obj.items() if v not in (None, "", [], {}, "null", "NULL")}
        
#         # Add back all cleaned arrays
#         cv_obj.update(cleaned_arrays)
        
#         try:
#             cv_obj["name"] = cv_obj["name"].lower()
#             cv_obj["email"] = cv_obj["email"].lower()
#         except Exception as e:
#             print("Error in lowercasing name and email",e)

        
#         return cv_obj
#     except Exception as e:
#         print(f"Error processing parsed CV JSON: {e}")
#         return cv_obj
    

# def extract_text_from_pdf(pdf_data):
#     text = ""
#     pdf_document = fitz.open(stream=pdf_data, filetype="pdf")
#     for page in pdf_document:
#         text += page.get_text()

#     links = []
#     for page_num, page in enumerate(pdf_document, start=1):
#         for link in page.get_links():
#             if "uri" in link:
#                 links.append(link["uri"])
#     return text,links

# def extract_text_from_docx(docx_bytes):
#     text = ""
#     document = Document(BytesIO(docx_bytes))
#     for paragraph in document.paragraphs:
#         text += paragraph.text + "\n"
#     return text

# class DecimalEncoder(json.JSONEncoder):
#     def default(self, obj):
#         if isinstance(obj, Decimal):
#             if obj % 1 == 0:
#                 return int(obj)
#             else:
#                 return float(obj)
#         return super(DecimalEncoder, self).default(obj)


# def invoke_claude_with_image(base64_images):                
#     print('called invoke_claude_with_image')
#     messages = [
#         {
#             "role": "user",
#             "content": []
#         }
#     ]

#     # Add images
#     for image_str in base64_images:
#         messages[0]["content"].append({
#             "type": "image",
#             "source": {
#                 "type": "base64",
#                 "media_type": "image/png",
#                 "data": image_str
#             }
#         })
#     # Add resume parsing instructions
#     messages[0]["content"].append({
#         "type": "text",
#         "text": ('Carefully analyze the entire resume shown in the image. Extract all visible information and present it in plain text format, organized topic-wise never miss name, emaail and year of experience. as it wil always present in the data\n\n'
#             'Name:\nEmail:\nExperience in year:\nAchievements:\nTechnical skills:'
#             '\nSoft skills:\nCore skills:\nEducation:\nIndustry experience:\nResponsibilities:'
#             '\nAchievements against responsibility:\nCertifications:\nStrength:\n'
#             'Experience type (leadership, Mid management, Senior management, Team lead, Individual contributor):'
#             '\nTeam handling experience:\nIndustry type(B2B, D2C, C2C, B2C):\n\nAssistant:\" turn'



                
#         )
#     })



#     body = {
#         "messages": messages,
#         "anthropic_version": "bedrock-2023-05-31",
#         "max_tokens": 4096
#     }
#     print('model version from prompt body',body['anthropic_version'])
#     body = json.dumps(body)
    

#     # Send request to Bedrock (Claude)
#     response = bedrock_runtime.invoke_model(
#         body=body,
#         modelId="anthropic.claude-3-haiku-20240307-v1:0",
#         # modelId="anthropic.claude-3-sonnet-20240229-v1:0",
#         # modelId="anthropic.claude-sonnet-4-20250514-v1:0",
#         contentType="application/json",
#         accept="application/json"
#     )
#     print('Result:',response)
#     response_body = json.loads(response["body"].read())
    
#     return response_body.get("content", [{}])[0].get("text", "")



# def reset_skills_if_partition_exists(table_name, partition_key, sort_key):
#     table = dynamodb.Table(table_name)

#     try:
#         # First, check if the item exists
#         response = table.get_item(
#             Key={
#                 'PK': partition_key,
#                 'SK': sort_key
#             }
#         )

#         if 'Item' not in response:
#             # No item found for this partition
#             return {"message": "Item not found, nothing updated"}

#         # If item exists, reset all skills to empty arrays
#         update_expression = "SET coreSkills = :emptyList, technicalSkills = :emptyList, softSkills = :emptyList, updatedAt = :updatedAt"
        
#         expression_attribute_values = {
#             ":emptyList": [],
#             ":updatedAt": int(datetime.now().timestamp() * 1000)
#         }

#         update_response = table.update_item(
#             Key={
#                 'PK': partition_key,
#                 'SK': sort_key
#             },
#             UpdateExpression=update_expression,
#             ExpressionAttributeValues=expression_attribute_values,
#             ReturnValues="UPDATED_NEW"
#         )

#         return update_response

#     except Exception as e:
#         return {"error": str(e)}

# def reset_frontend_auto_populations_in_dynamodb(table_name, partition_key, sort_key):
#     # Force defaults
#     multipleCandidateExperience = []
#     about = ""
#     responsibilities = []

#     table = dynamodb.Table(table_name)

#     # Get current date and time
#     current_datetime = datetime.now().isoformat()

#     response = table.update_item(
#         Key={
#             'PK': partition_key,
#             'SK': sort_key
#         },
#         UpdateExpression="""
#             SET multipleCandidateExperience = :multipleCandidateExperience,
#                 multipleCandidateExperiencedDate = :multipleCandidateExperiencedDate,
#                 about = :about,
#                 responsibilities = :responsibilities
#         """,
#         ExpressionAttributeValues={
#             ':multipleCandidateExperience': multipleCandidateExperience,
#             ':multipleCandidateExperiencedDate': current_datetime,
#             ':about': about,
#             ':responsibilities': responsibilities
#         },
#         ReturnValues="UPDATED_NEW"
#     )

#     return response

# def correct_https_in_links(otherSocialPlatforms):
#     try:
#         for platform, links in otherSocialPlatforms.items():
#             # Normalize to list
#             if isinstance(links, str):
#                 links = [links]

#             corrected_links = []
#             for link in links:
#                 if not link:
#                     corrected_links.append("")
#                     continue

#                 link = link.strip()

#                 # Case 1: Already has https:// or http:// → keep as is
#                 if link.startswith("https://") or link.startswith("http://"):
#                     corrected_links.append(link)

#                 # Case 2: Starts with www. or subdomain (like in.linkedin.com)
#                 elif link.startswith("www.") or "." in link.split("/")[0]:
#                     corrected_links.append("https://" + link)

#                 # Case 3: Plain domain without www or protocol
#                 else:
#                     corrected_links.append("https://www." + link)

#             otherSocialPlatforms[platform] = corrected_links

#     except Exception as e:
#         print(f"Social links can't be formatted correctly: {e}")

#     return otherSocialPlatforms


# def reset_pref_section_in_dynamo(table_name, partition_key, sort_key):
#     table = dynamodb.Table(table_name)
#     email = partition_key.split('#')[2]
#     # Helper function to convert floats to Decimal
#     userPreferredRoles = []
#     userPreferredIndustries = []
    
#     try:
            
#         # First, check if the item exists
#         response = table.get_item(
#             Key={
#                 'PK': partition_key,
#                 'SK': sort_key
#             }
#         )

#         if 'Item' not in response:
#         # No item found for this partition
#             return {"message": "Item not found, nothing updated"}
#         else:
#             # Prepare update expression and attribute values
#             update_parts = []
#             expression_attribute_values = {}
            
#             # Always update Prefered_departments
#             update_parts.append("userPreferredRoles = :userPreferredRoles")
#             expression_attribute_values[':userPreferredRoles'] = userPreferredRoles

#             # Always update Prefered_departments
#             update_parts.append("userPreferredIndustries = :userPreferredIndustries")
#             expression_attribute_values[':userPreferredIndustries'] = userPreferredIndustries

            
#             # Combine all update parts into a single SET clause
#             update_expression = "SET " + ", ".join(update_parts)
            
#             # Perform the update
#             response = table.update_item(
#                 Key={
#                     'PK': partition_key,
#                     'SK': sort_key
#                 },
#                 UpdateExpression=update_expression,
#                 ExpressionAttributeValues=expression_attribute_values,
#                 ReturnValues="UPDATED_NEW"
#             )
            
#             return response
    
#     except Exception as e:
#         print(f"Error updating skills: {str(e)}")
#         return {"error": str(e)}

# def print_completion_text(completion_text):
#     print("***********************************************************************")
#     print(completion_text)
#     print("#######################################################################")

# def update_otherSocialPlatForms_in_dynamodb(table_name, partition_key, otherSocialPlatForms):
#     table = dynamodb.Table(table_name)
#     sort_key = "SOCIAL#"
#     current_timestamp = int(datetime.now().timestamp() * 1000)
#     social_fields = ["linkedin", "github", "twitter"]

#     update_expressions = []
#     expression_values = {}

#     # Always ensure linkedin, github, twitter exist at the top level
#     for field in social_fields:
#         value = otherSocialPlatForms.get(field, "")

#         # Normalize to list of strings
#         if isinstance(value, str):
#             value = [value] if value.strip() else [""]
#         elif isinstance(value, list):
#             # Clean list, default to [""] if empty
#             value = [str(v) for v in value if str(v).strip()] or [""]
#         else:
#             value = [str(value)]

#         update_expressions.append(f"{field} = :{field}")
#         expression_values[f":{field}"] = value

#     # Keep only extra fields in otherSocialPlatForms
#     extra_socials = {
#         k: v for k, v in otherSocialPlatForms.items() if k not in social_fields
#     }

#     # make createdAt only if new partiton is created otherwise do not update it
#     response1 = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(partition_key) 
#             & boto3.dynamodb.conditions.Key('SK').eq(sort_key))
#     skillS_Present_orNot = response1["Items"]==[]
#     if skillS_Present_orNot:
#         print("craeting createdAt in preff#" )
#         update_expressions.append("createdAt = :createdAt")
#         expression_values[':createdAt'] = current_timestamp

#     update_expressions.append("otherSocialPlatForms = :otherSocialPlatForms")
#     expression_values[":otherSocialPlatForms"] = extra_socials

#     update_expressions.append("updatedAt = :updatedAt")
#     expression_values[":updatedAt"] = current_timestamp
#     update_expression = "SET " + ", ".join(update_expressions)

#     response = table.update_item(
#         Key={
#             'PK': partition_key,
#             'SK': sort_key
#         },
#         UpdateExpression=update_expression,
#         ExpressionAttributeValues=expression_values,
#         ReturnValues="UPDATED_NEW"
#     )

#     return response
    
# def reset_otherSocialPlatForms_in_dynamodb(table_name, partition_key, sort_key="SOCIAL#"):
#     dynamodb = boto3.resource("dynamodb")
#     table = dynamodb.Table(table_name)

#     try:
#         # Check if the item exists
#         response = table.get_item(
#             Key={
#                 'PK': partition_key,
#                 'SK': sort_key
#             }
#         )

#         if 'Item' not in response:
#             # No item found for this partition
#             return {"message": "Item not found, nothing updated"}
#         else:
#             social_fields = ["linkedin", "github", "twitter", "otherSocialPlatForms"]

#             update_expressions = []
#             expression_values = {}

#             for field in social_fields:
#                 if field == "otherSocialPlatForms":
#                     update_expressions.append(f"{field} = :{field}")
#                     expression_values[f":{field}"] = []
#                 else:
#                     update_expressions.append(f"{field} = :{field}")
#                     expression_values[f":{field}"] = ""

#             update_expression = "SET " + ", ".join(update_expressions)

#             update_response = table.update_item(
#                 Key={
#                     'PK': partition_key,
#                     'SK': sort_key
#                 },
#                 UpdateExpression=update_expression,
#                 ExpressionAttributeValues=expression_values,
#                 ReturnValues="UPDATED_NEW"
#             )
#             return update_response
#     except Exception as e:
#         print("Error:", e)
#         return {"error": str(e)}


# def reset_partition(partition_key_value):
#     dynamodb = boto3.resource("dynamodb")
#     table_name = "worko"
#     table = dynamodb.Table(table_name)
#     sort_key_prefix = "EDU#ID#"
#     try:
#         response = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(partition_key_value) & boto3.dynamodb.conditions.Key('SK').begins_with(sort_key_prefix))
#         # Step 1: Query all items with the given partition key
#         # response = table.query(
#         #     KeyConditionExpression=boto3.dynamodb.conditions.Key("PK").eq(partition_key_value)
#         # )

#         items = response.get("Items", [])
#         # Delete all items
#         deleted_count = 0
#         with table.batch_writer() as batch:
#             for item in items:
#                 # Must provide both PK and SK for deletion
#                 batch.delete_item(
#                     Key={
#                         'PK': item['PK'],
#                         'SK': item['SK']
#                     }
#                 )
#                 deleted_count += 1
#                 print(f"Deleted item: PK={item['PK']}, SK={item['SK']}")
#             print(f"Total items deleted: {deleted_count}")
#             return deleted_count
#     except Exception as e:
#         print(e)

    




        
#         # if not items:
#         #     print(f"No items found for pk={partition_key_value}")
#         #     return

#         # # Step 2: Batch delete (max 25 items per batch)
#         # with table.batch_writer() as batch:
#         #     for item in items:
#         #         batch.delete_item(
#         #             Key={
#         #                 "pk": item["pk"],
#         #                 "sk": item["sk"]
#         #             }
#         #         )
#         #         print(f"Deleted item with SK: {item['sk']}")

#         # print(f"✅ Entire partition with pk={partition_key_value} deleted successfully.")
#         return items

#     except Exception as e:
#         print(f"Error deleting partition: {e}")

# def has_key_elements(resume_text, key_elements_dict, min_required_categories=2, min_total_elements=5):
    
#     # Initialize tracking
#     total_elements_found = 0
#     found_elements = {category: [] for category in key_elements_dict.keys()}
    
#     # Handle different input types
#     if isinstance(resume_text, dict):
#         resume_text_str = str(resume_text).lower()
#     elif isinstance(resume_text, str):
#         resume_text_str = resume_text.lower()
#     else:
#         resume_text_str = str(resume_text).lower()
    
#     # Preprocessing: Replace spaced out text like "C O N T A C T" with "CONTACT"
#     # Find patterns like "C O N T A C T" and convert to "CONTACT"
#     spaced_words = re.findall(r'\b([A-Z](\s+[A-Z])+)\b', resume_text)
#     for match in spaced_words:
#         original = match[0]
#         fixed = original.replace(" ", "")
#         resume_text_str = resume_text_str.replace(original.lower(), fixed.lower())
    
#     # Debug: Print the first 100 characters of the text
#     print(f"Text preview: {resume_text_str[:100]}...")
    
#     # Detect common personal info formats first
#     email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
#     phone_pattern = r'\b(?:\+\d{1,3}[-\s]?)?\d{3,}[-\s.]?\d{3,}[-\s.]?\d{3,4}\b'
    
#     # Check for email and phone directly - these are strong personal info indicators
#     email_match = re.search(email_pattern, resume_text_str)
#     phone_match = re.search(phone_pattern, resume_text_str)
    
#     if email_match:
#         found_elements["personal_info"].append("email")
#         total_elements_found += 1
#         print(f"Found element: email (category: personal_info) - {email_match.group()}")
    
#     if phone_match:
#         found_elements["personal_info"].append("phone")
#         total_elements_found += 1
#         print(f"Found element: phone (category: personal_info) - {phone_match.group()}")
    
#     # Check each category for keyword-based elements
#     for category, elements in key_elements_dict.items():
#         for element in elements:
#             # Skip email and phone for personal_info as we already handled them
#             if category == "personal_info" and element in ["email", "phone"]:
#                 continue
            
#             # Create patterns for accurate matching
#             element_escaped = re.escape(element.lower())
#             patterns = [
#                 f"\\b{element_escaped}\\b",                         # Word by itself
#                 f"\\b{element_escaped}:",                           # Word followed by colon
#                 f"\\b{element_escaped} :",                          # Word followed by space and colon
#                 f"\\b{element_escaped}\\s+section",                 # Word followed by "section"
#                 f"\\b{element_escaped}\\s*\\n",                     # Word at end of line
#                 f"^{element_escaped}\\s*$",                         # Word on its own line
#                 f"\\n{element_escaped}\\s*\\n",                     # Word between newlines
#             ]
            
#             # Add special patterns for specific phrases
#             if element.lower() == "contact me":
#                 patterns.extend([
#                     r"\bcontact me\b",
#                     r"\bcontact me at\b"
#                 ])
#             elif element.lower() == "personal details":
#                 patterns.append(r"\bpersonal details\b")
#             elif element.lower() == "personal profile":
#                 patterns.append(r"\bpersonal profile\b")
#             elif element.lower() == "professional experience":
#                 patterns.extend([
#                     r"\bprofessional experience\b",
#                     r"\bwork experience\b",
#                     r"\bemployment history\b"
#                 ])
#             elif element.lower() == "education":
#                 patterns.extend([
#                     r"\beducation\b",
#                     r"\bacademic background\b",
#                     r"\bacademic qualification\b"
#                 ])
            
#             # Check if any pattern matches
#             element_found = False
#             for pattern in patterns:
#                 if re.search(pattern, resume_text_str, re.MULTILINE | re.IGNORECASE):
#                     if element not in found_elements[category]:
#                         found_elements[category].append(element)
#                         total_elements_found += 1
#                         element_found = True
#                         print(f"Found element: {element} (category: {category})")
#                     break
            
#             if element_found:
#                 continue  # Move to next element
    
#     # Check if name is likely present (at the top, capitalized)
#     # Look for standalone capitalized words that might be names
#     potential_name_lines = re.findall(r'^([A-Z][a-z]+\s+[A-Z][a-z]+)', resume_text_str, re.MULTILINE)
#     if potential_name_lines:
#         if "name" not in found_elements["personal_info"]:
#             found_elements["personal_info"].append("name")
#             total_elements_found += 1
#             print(f"Found element: name (category: personal_info) - {potential_name_lines[0]}")
    
#     # Count categories that have any found elements
#     categories_with_matches = sum(1 for elements in found_elements.values() if len(elements) > 0)
    
#     print(f"Categories with matches: {categories_with_matches}/{len(key_elements_dict)}")
#     print(f"Total elements found: {total_elements_found}")
#     print(f"Found elements by category: {found_elements}")
    
#     # Check if we meet both category and total element thresholds
#     is_valid = (categories_with_matches >= min_required_categories and 
#                 total_elements_found >= min_total_elements)
    
#     return is_valid, found_elements, total_elements_found

# def check_if_resume(processed_text):

#     if not processed_text:
#         print("No text provided")
#         return {"statusCode": 404, "body": "No text provided"}
    
#     # Define categories with higher weights for critical resume sections
#     resume_elements = {
#         # Critical resume sections (highest weight)
#         "core_sections": [
#             'experience', 'work history', 'employment', 'professional experience',
#             'education', 'academic background', 'qualification', 'qualifications',
#             'work experience', 'career highlights'  # Added these common variants
#         ],
        
#         # Important but not critical sections
#         "additional_sections": [
#             'skills', 'technical skills', 'soft skills', 
#             'certifications', 'certificates', 'accreditations',
#             'projects', 'achievements', 'accomplishments',
#             'publications', 'research', 'patents', 
#             'core competencies', 'it skills'  # Added these common variants
#         ],
        
#         # Common resume sections
#         "standard_sections": [
#             'summary', 'profile', 'professional summary', 'career objective',
#             'objective', 'references', 'languages', 'volunteer', 'leadership',
#             'responsibilities', 'expertise', 'competencies',
#             'personal profile', 'career highlights'  # Added these common variants
#         ],
        
#         # Personal information (must have some contact info)
#         "personal_info": [
#             'name', 'email', 'phone', 'contact', 'address', 
#             'linkedin', 'github', 'portfolio', 'website',
#             'personal details', 'contact me'  # Added these common variants
#         ]
#     }
    
#     # Settings for validation
#     min_required_categories = 2  # Need matches from at least 2 categories
#     min_total_elements = 5       # Need at least 5 total elements across all categories
    
#     # At least one from personal_info + one from core_sections = strong resume indicator
#     is_valid, found_elements, total_found = has_key_elements(
#         processed_text, 
#         resume_elements,
#         min_required_categories,
#         min_total_elements
#     )
    
#     # Additional checks for higher confidence:
#     # 1. Must have at least one personal info element
#     # 2. Must have at least one core section
#     has_personal_info = len(found_elements["personal_info"]) > 0
#     has_core_section = len(found_elements["core_sections"]) > 0
    
#     # More detailed validation logic with better messaging
#     if is_valid:
#         if has_personal_info and has_core_section:
#             # High confidence - has both personal info and core sections
#             confidence = "high" if total_found >= 8 else "medium"
#             return {
#                 "statusCode": 200, 
#                 "body": "Valid resume found",
#                 "details": {
#                     "elements_found": found_elements,
#                     "confidence": confidence
#                 }
#             }
#         else:
#             # Moderate confidence - missing either personal info or core sections
#             missing_elements = []
#             if not has_personal_info:
#                 missing_elements.append("personal information (contact details, email, phone)")
#             if not has_core_section:
#                 missing_elements.append("core resume sections (experience, education)")
                
#             return {
#                 "statusCode": 200,  # Changed to 200 since it's still likely a resume
#                 "body": f"Partial resume detected - missing {', '.join(missing_elements)}",
#                 "details": {
#                     "elements_found": found_elements,
#                     "missing_critical": {
#                         "personal_info": not has_personal_info,
#                         "core_sections": not has_core_section
#                     },
#                     "confidence": "low"
#                 }
#             }
#     else:
#         # Not enough elements found to be considered a resume
#         return {"statusCode": 404, "body": "Not a valid resume"}

# def extract_skill_data_from_json(json_data):
#     """Extract skill data from GPT model JSON response.
    
#     Args:
#         json_data: Dictionary containing skill data from GPT model
        
#     Returns:
#         Tuple of (core_skills, technical_skills, soft_skills, preferred_departments, yoe)
#     """
#     try:
#         core_skills = json_data.get('coreSkills', [])
#         technical_skills = json_data.get('technicalSkills', [])
#         soft_skills = json_data.get('softSkills', [])
#         preferred_departments = json_data.get('Prefered_departments', [])
#         yoe = json_data.get('YOE', 0)
        
#         return core_skills, technical_skills, soft_skills, preferred_departments, yoe
        
#     except Exception as e:
#         print(f"Error extracting skills from JSON: {str(e)}")
#         return [], [], [], [], 0


# def update_core_skills_years(core_skills):
#     """Transform each skill's 'years' to a number."""
#     result = []
#     for skill in core_skills:
#         years_value = skill.get('years', 0)
#         # Handle if years is already an int/float
#         if isinstance(years_value, (int, float)):
#             skill['years'] = years_value
#         # Handle if years is a list
#         elif isinstance(years_value, list):
#             skill['years'] = years_value[0] if years_value else 0
#         else:
#             skill['years'] = 0
#         result.append(skill)
#     return result

# def clean_json_string(json_string):
#     # Remove ```json from the beginning if present
#     if json_string.startswith("```json"):
#         json_string = json_string[7:]
#     # Remove ``` from the beginning if present
#     elif json_string.startswith("```"):
#         json_string = json_string[3:]
    
#     # Remove ``` from the end if present
#     if json_string.endswith("```"):
#         json_string = json_string[:-3]
    
#     # Strip any extra whitespace
#     json_string = json_string.strip()
    
#     return json_string


# def update_technical_skills_years(technical_skills):
#     """Transform each skill's 'years' to a number."""
#     result = []
#     for skill in technical_skills:
#         years_value = skill.get('years', 0)
#         # Handle if years is already an int/float
#         if isinstance(years_value, (int, float)):
#             skill['years'] = years_value
#         # Handle if years is a list
#         elif isinstance(years_value, list):
#             skill['years'] = years_value[0] if years_value else 0
#         else:
#             skill['years'] = 0
#         result.append(skill)
#     return result

# def update_skills_in_dynamodb(table_name, partition_key, sort_key, core_skills, technical_skills, soft_skills):
#     table = dynamodb.Table(table_name)
    
#     # Helper function to convert floats to Decimal
#     def convert_floats_to_decimal(obj):
#         if isinstance(obj, list):
#             return [convert_floats_to_decimal(item) for item in obj]
#         elif isinstance(obj, dict):
#             return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
#         elif isinstance(obj, float):
#             return Decimal(str(obj))
#         else:
#             return obj
    
#     try:
#         # Convert float values to Decimal before using with DynamoDB
#         core_skills = convert_floats_to_decimal(core_skills)
#         technical_skills = convert_floats_to_decimal(technical_skills)
#         soft_skills = convert_floats_to_decimal(soft_skills)
        
#         # Prepare update expression and attribute values
#         update_parts = []
#         expression_attribute_values = {}
        
#         response1 = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(partition_key) & boto3.dynamodb.conditions.Key('SK').begins_with(sort_key))
#         skillS_Present_orNot = response1["Items"]==[]
#         if skillS_Present_orNot:
#             update_parts.append("createdAt = :createdAt")
#             expression_attribute_values[':createdAt'] = int(datetime.now().timestamp() * 1000)
        
#         # Always update coreSkills
#         update_parts.append("coreSkills = :coreSkills")
#         expression_attribute_values[':coreSkills'] = core_skills

#         # Always update technicalskills
#         update_parts.append("technicalSkills = :technicalSkills")
#         expression_attribute_values[':technicalSkills'] = technical_skills

#         # Always update softSkills
#         update_parts.append("softSkills = :softSkills")
#         expression_attribute_values[':softSkills'] = soft_skills
        
#         # Update the timestamp
#         update_parts.append("updatedAt = :updatedAt")
#         expression_attribute_values[':updatedAt'] = int(datetime.now().timestamp() * 1000)



    
#         # Combine all update parts into a single SET clause
#         update_expression = "SET " + ", ".join(update_parts)
        
#         # Perform the update
#         response = table.update_item(
#             Key={
#                 'PK': partition_key,
#                 'SK': sort_key
#             },
#             UpdateExpression=update_expression,
#             ExpressionAttributeValues=expression_attribute_values,
#             ReturnValues="UPDATED_NEW"
#         )
        
#         return response
    
#     except Exception as e:
#         print(f"Error updating skills: {str(e)}")
#         return {"error": str(e)}

# def update_yoe_in_dynamodb(table_name, partition_key, sort_key_prefix, yoe):
    
#     table = dynamodb.Table(table_name)
    
#     try:
#         # Query to find items that match the partition key and sort key prefix
#         response = table.query(
#             KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
#             ExpressionAttributeValues={
#                 ':pk': partition_key,
#                 ':sk_prefix': sort_key_prefix
#             }
#         )
        
#         # If no items found, return error
#         if 'Items' not in response or len(response['Items']) == 0:
#             return {
#                 "error": f"No records found with PK={partition_key} and SK beginning with {sort_key_prefix}. No update performed."
#             }
        
#         # Extract the first matching item's complete sort key
#         complete_sort_key = response['Items'][0]['SK']
        
#         # If yoe is a list with a single value, extract the value first
#         if isinstance(yoe, list) and len(yoe) == 1:
#             yoe = yoe[0]
        
#         # Convert YOE to Decimal if it's a float or int (after extracting from list)
#         if isinstance(yoe, (float, int)):
#             yoe = Decimal(str(yoe))
        
#         # Create update expression
#         update_expression = "SET YOE = :yoe, updatedAt = :updatedAt"
        
#         # Set the expression attribute values
#         expression_attribute_values = {
#             ':yoe': yoe,  # This will be a single value, not a list
#             ':updatedAt': int(datetime.now().timestamp() * 1000)
#         }
        
#         # Perform the update using the complete sort key
#         update_response = table.update_item(
#             Key={
#                 'PK': partition_key,
#                 'SK': complete_sort_key
#             },
#             UpdateExpression=update_expression,
#             ExpressionAttributeValues=expression_attribute_values,
#             ReturnValues="UPDATED_NEW"
#         )
        
#         return update_response
        
#     except Exception as e:
#         print(f"Error updating YOE: {str(e)}")
#         return {"error": str(e)}

# def update_pref_department_in_dynamo(table_name, partition_key, sort_key, userId,Prefered_departments):
#     table = dynamodb.Table(table_name)
#     email = partition_key.split('#')[2]
#     userId = userId.split('#')[-1]
#     # Helper function to convert floats to Decimal

    
#     try:
#         # Prepare update expression and attribute values
#         update_parts = []
#         expression_attribute_values = {}

#         # make createdAt only if new partiton is created otherwise do not update it
#         response1 = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(partition_key) 
#             & boto3.dynamodb.conditions.Key('SK').eq(sort_key))
#         skillS_Present_orNot = response1["Items"]==[]
#         if skillS_Present_orNot:
#             print("craeting createdAt in preff#" )
#             update_parts.append("createdAt = :createdAt")
#             expression_attribute_values[':createdAt'] = int(datetime.now().timestamp() * 1000)


#         # Always update Prefered_departments
#         update_parts.append("userPreferredDepartments = :userPreferredDepartments")
#         expression_attribute_values[':userPreferredDepartments'] = Prefered_departments

#         # Always update email
#         update_parts.append("email = :email")
#         expression_attribute_values[':email'] = email

        
#         # Always update userId
#         update_parts.append("createdByUserId = :createdByUserId")
#         expression_attribute_values[':createdByUserId'] = userId

#         # Update the timestamp
#         update_parts.append("updatedAt = :updatedAt")
#         expression_attribute_values[':updatedAt'] = int(datetime.now().timestamp() * 1000)

#         # Combine all update parts into a single SET clause
#         update_expression = "SET " + ", ".join(update_parts)
        
#         # Perform the update
#         response = table.update_item(
#             Key={
#                 'PK': partition_key,
#                 'SK': sort_key
#             },
#             UpdateExpression=update_expression,
#             ExpressionAttributeValues=expression_attribute_values,
#             ReturnValues="UPDATED_NEW"
#         )
#         return response
    
#     except Exception as e:
#         print(f"Error updating skills: {str(e)}")
#         return {"error": str(e)}


# def update_cv_extract_parsed_in_dynamodb(table_name, partition_key, sort_key, cv_extract_parsed):
#     for i in cv_extract_parsed['multipleCandidateExperience']:
#         i["YOE"]=Decimal(str(i["YOE"]))
#         if i["YOE"]<0.5:
#             i["YOE"]=0.5
        
#     cv_extract_parsed = convert_floats_to_decimals(cv_extract_parsed)
#     table = dynamodb.Table(table_name)

#     # Get current date and time
#     current_datetime = datetime.now().isoformat()

#     response = table.update_item(
#         Key={
#             'PK': partition_key,
#             'SK': sort_key
#         },
#         UpdateExpression="SET cvExtractParsed = :cvExtractParsed, cvExtractParsedDate = :cvExtractParsedDate",
        
#         ExpressionAttributeValues={
#             ':cvExtractParsed': cv_extract_parsed,
#             ':cvExtractParsedDate': current_datetime
#         },
#         ReturnValues="UPDATED_NEW"
#     )
#     return response

# def update_frontend_auto_populations_in_dynamodb(table_name, partition_key, sort_key, frontend_auto_populations):
#     multipleCandidateExperience = frontend_auto_populations.get("multipleCandidateExperience", None)
#     about = frontend_auto_populations.get("about", None)
#     responsibilities = frontend_auto_populations.get("responsibilities", [])

#     # Clean responsibilities endDate if "present"
#     for k in responsibilities:
#         if k.get("date", {}).get("endDate", "").lower() == "present":
#             k["date"]["endDate"] = ""
#     for k in multipleCandidateExperience:
#         if k.get("endDate", "").lower() == "present":
#             k["endDate"] = ""
    
#     for i in multipleCandidateExperience:
#         try:
#             i["YOE"] = float(i["YOE"])

#         except Exception as e:
#             i["YOE"]=1
#         if float(i["YOE"])<0.5:
#             i["YOE"]=0.5


    
#     # Convert floats to Decimal before sending to DynamoDB
#     multipleCandidateExperience = convert_floats_to_decimals(multipleCandidateExperience)

#     about = convert_floats_to_decimals(about)
#     responsibilities = convert_floats_to_decimals(responsibilities)

#     table = dynamodb.Table(table_name)

#     # Get current date and time
#     current_datetime = datetime.now().isoformat()


#     response = table.update_item(
#     Key={
#         'PK': partition_key,
#         'SK': sort_key
#     },
#     UpdateExpression="""
#         SET multipleCandidateExperience = :multipleCandidateExperience,
#             multipleCandidateExperiencedDate = :multipleCandidateExperiencedDate,
#             about = :about,
#             responsibilities = :responsibilities
#     """,
#     ExpressionAttributeValues={
#         ':multipleCandidateExperience': multipleCandidateExperience,
#         ':multipleCandidateExperiencedDate': current_datetime,
#         ':about': about,
#         ':responsibilities': responsibilities
#     },
#     ReturnValues="UPDATED_NEW"
#     )
#     return response


# def update_pref_section_in_dynamo(table_name, partition_key, sort_key, Prefered_section):
#     table = dynamodb.Table(table_name)
#     email = partition_key.split('#')[2]
#     # Helper function to convert floats to Decimal
    
#     userPreferredRoles = Prefered_section["userPreferredRoles"]
#     userPreferredIndustries = Prefered_section["userPreferredIndustries"]

#     # check is empty string is then make it a empty array
#     if userPreferredIndustries=="":
#         userPreferredIndustries=[]
#     if userPreferredRoles=="":
#         userPreferredRoles=[]
    
#     try:
#         # Prepare update expression and attribute values
#         update_parts = []
#         expression_attribute_values = {}
        
#         # Always update Prefered_departments
#         update_parts.append("userPreferredRoles = :userPreferredRoles")
#         expression_attribute_values[':userPreferredRoles'] = userPreferredRoles

#         # Always update Prefered_departments
#         update_parts.append("userPreferredIndustries = :userPreferredIndustries")
#         expression_attribute_values[':userPreferredIndustries'] = userPreferredIndustries

        
#         # Combine all update parts into a single SET clause
#         update_expression = "SET " + ", ".join(update_parts)
        
#         # Perform the update
#         response = table.update_item(
#             Key={
#                 'PK': partition_key,
#                 'SK': sort_key
#             },
#             UpdateExpression=update_expression,
#             ExpressionAttributeValues=expression_attribute_values,
#             ReturnValues="UPDATED_NEW"
#         )
        
#         return response
    
#     except Exception as e:
#         print(f"Error updating skills: {str(e)}")
#         return {"error": str(e)}

# def update_Education_in_dynamo(table_name, partition_key, education):
#     sort_key = str(uuid.uuid4())
#     sort_key = 'EDU#ID#'+ sort_key
#     print(f"sk:{sort_key} pk: {partition_key} update edu called")
#     table = dynamodb.Table(table_name)
#     collage = education["collage"]
#     degree = education["degree"]
#     try:
#         update_parts = []
#         expression_attribute_values = {}
#         passingYear = int(education.get("passingYear", 0))
#         # Always update passingYear if its given 
#         update_parts.append("passingYear = :passingYear")
#         expression_attribute_values[':passingYear'] = passingYear
#     except ValueError:
#         print(f"Invalid passingYear value: {education.get('passingYear')}")
#         passingYear = 2012
#     try:
#         # Prepare update expression and attribute values
#         # Always update collage
#         update_parts.append("collage = :collage")
#         expression_attribute_values[':collage'] = collage

#         # Always update degree
#         update_parts.append("degree = :degree")
#         expression_attribute_values[':degree'] = degree

#         # Always update createdAt
#         update_parts.append("createdAt = :createdAt")
#         expression_attribute_values[':createdAt'] = int(datetime.now().timestamp() * 1000)
#         # Always update updatedAt
#         update_parts.append("updatedAt = :updatedAt")
#         expression_attribute_values[':updatedAt'] =  int(datetime.now().timestamp() * 1000)

#         # Combine all update parts into a single SET clause
#         update_expression = "SET " + ", ".join(update_parts)
        
#         # Perform the update
#         response = table.update_item(
#             Key={
#                 'PK': partition_key,
#                 'SK': sort_key
#             },
#             UpdateExpression=update_expression,
#             ExpressionAttributeValues=expression_attribute_values,
#             ReturnValues="UPDATED_NEW"
#         )
#         return response
#     except Exception as e:
#         print(f"Error updating skills: {str(e)}")
#         return {"error": str(e)}


# def update_isCvExtracted_in_dynamodb(table_name, partition_key, sort_key, isCvExtracted):

#     table = dynamodb.Table(table_name)

#     # Get current date and time
#     current_datetime = datetime.now().isoformat()


#     response = table.update_item(
#     Key={
#         'PK': partition_key,
#         'SK': sort_key
#     },
#     UpdateExpression="""
#         SET isCvExtracted = :isCvExtracted
#     """,
#     ExpressionAttributeValues={
#         ':isCvExtracted': isCvExtracted
#     },
#     ReturnValues="UPDATED_NEW"
#     )
#     return response


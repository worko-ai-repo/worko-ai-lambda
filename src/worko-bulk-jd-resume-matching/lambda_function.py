import json
import boto3
import fitz
import os
import time
import re
import requests
from decimal import Decimal
from boto3.dynamodb.types import TypeDeserializer
from datetime import datetime
import botocore
from docx import Document
from io import BytesIO
import random
import string
from typing import Tuple, Dict, Any, Optional, Union
from utils import *
                   
import base64 

# Initialize the AWS service clients
region = 'us-east-1'
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')
bedrock_runtime = boto3.client('bedrock-runtime', region_name= region)
sqs = boto3.client('sqs')


  
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

def get_account_id():
    # Create STS client
    sts_client = boto3.client('sts')

    # Call get-caller-identity
    response = sts_client.get_caller_identity()

    # Extract account ID
    return response['Account']

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
    cv_extract_template = '''
    Name:
    Email:
    Experience in years:
    Achievements:
    Technical skills:
    Soft skills:
    Core skills:
    Education:
    Industry experience:
    Responsibilities:
    Achievements against responsibility:
    Certifications:
    Strength:
    Experience type (leadership, Mid management, Senior management, Team lead, Individual contributor):
    Team handling experience:
    Industry type (B2B, D2C, C2C, B2C):
    '''.strip()

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

        cv_content = invoke_model_with_backoff_nova_lite(cv_prompt)
        cv_extract = extract_text_from_nova(cv_content)
        
        cv_extract = clean_text(cv_extract)
        print("cv_extract-------",cv_extract)
        
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
        
        return cv_extract, merged
        
    except requests.exceptions.HTTPError as e:
        print(" Error occured : from open ai asuure.",e)
        return "Error processing CV", cv_parsed_template
    except Exception as e:
        print(f"Error processing CV: {str(e)}")
        return "Error processing CV", cv_parsed_template

def query_dynamodb_item_with_sk_prefix(table_name, partition_key_value, sort_key_prefix):
    table = dynamodb.Table(table_name)
    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(partition_key_value) &
                               boto3.dynamodb.conditions.Key('SK').eq(sort_key_prefix)
    )
    items = response.get('Items')
    if items:
        return items[0]
    return None

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

def update_ref_response_in_dynamodb(table_name, partition_key, sort_key, cv_extract, cv_extracted_parsed, scoreDetails, matchingScore, rejection_feedback, emailFeedback, processing_status):
    
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

def jd_resume_matching(table_name, partition_key_value, sort_key_prefix, job_desc, processed_text, cv_extract, cv_extracted_parsed,gpt_models):

    # Determine if job is non-technical
    print("*****************************Job Description******************************************")
    # print("jd:-", job_desc)
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
                                    "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                    "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                        "Final Score = Section A Score + Section B Score"
                                        "Maximum: 40 points"
                                    "Provide results in JSON format: {\"score\": [0-40], \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                ),
                                ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
                                    "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                    "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 10 points to the Matching Score."
                                    "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 10 points (9) to the Matching Score."
                                    "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 10 points (5) to the Matching Score."
                                    "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 10 points (7.5) to the Matching Score."
                                    "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 10 points (8) to the Matching Score."
                                    "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                    "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
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
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
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
                                             "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                             "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                        "Final Score = Section A Score + Section B Score"
                                        "Maximum: 40 points"
                                    "Provide results in JSON format: {\"score\": [0-40], \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                ),
                                ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
                                             "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 10 points to the Matching Score."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 10 points (9) to the Matching Score."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 10 points (5) to the Matching Score."
                                             "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 10 points (7.5) to the Matching Score."
                                             "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 10 points (8) to the Matching Score."
                                             "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                             "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
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
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
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
                                             "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                             "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                        "Final Score = Section A Score + Section B Score"
                                        "Maximum: 40 points"
                                    "Provide results in JSON format: {\"score\": [0-40], \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                ),
                                ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
                                             "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 10 points to the Matching Score."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 10 points (9) to the Matching Score."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 10 points (5) to the Matching Score."
                                             "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 10 points (7.5) to the Matching Score."
                                             "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 10 points (8) to the Matching Score."
                                             "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                             "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
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
                                    "stricly Present results in JSON format only:"
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
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
                                             "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                             "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                ),
                                ("Here is the most relevant sentence in the context: Additionally, check for any specific relevant experience mentioned in the job description:"
                                            "If specific relevant Project/Internship/Experience/skills is mentioned as mandatory in the job description and it is not present in the resume, add 0% of 25 points to the Matching Score."
                                            "If specific relevant Project/Internship/Experience/skills is mentioned as mandatory in the job description and it is present in the resume, add 90% of 25 points (22.5) to the Matching Score."
                                            "If specific relevant Project/Internship/Experience/skills is mentioned as non-mandatory or preferred in the job description and it is present in the resume, add 90% of 25 points (22.5) to the Matching Score."
                                            "If specific relevant Project/Internship/Experience/skills is mentioned as non-mandatory or preferred in the job description and it is not present in the resume, add 60% of 25 points (15) to the Matching Score."
                                            "Before calculating the score, identify and list the most relevant sentences from the job description that specify the required or preferred experience, and the corresponding sentences from the resume that match or do not match these requirements."
                                            "Show the points given. Present it in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                            "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
                                ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
                                             "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 30 points to the Matching Score."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 30 points (27) to the Matching Score."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 30 points (15) to the Matching Score."
                                             "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 30 points (22.5) to the Matching Score."
                                             "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 30 points (24) to the Matching Score."
                                             "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                             "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
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
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
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
                                    "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                    "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                        "Final Score = Section A Score + Section B Score"
                                        "Maximum: 40 points"
                                    "Provide results in JSON format: {\"score\": [0-40], \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
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
                                     "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
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
                                    "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                    "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                        "Final Score = Section A Score + Section B Score"
                                        "Maximum: 40 points"
                                    "Provide results in JSON format: {\"score\": [0-40], \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
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
                                     "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
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
                                    "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                    "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                        "Final Score = Section A Score + Section B Score"
                                        "Maximum: 40 points"
                                    "Provide results in JSON format: {\"score\": [0-40], \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
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
                                     "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
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
                                    "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                    "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                        "Final Score = Section A Score + Section B Score"
                                        "Maximum: 40 points"
                                    "Provide results in JSON format: {\"score\": [0-40], \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
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
                                     "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                    "striclty Present results in JSON format only:"
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                    "VALIDATION RULES:"
                                    "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                    "- Do not make assumptions about implied skills or experience"
                                    "- Weight keywords based strictly on their placement and context within resume sections"
                                    "- If a keyword appears in multiple sections, use the highest applicable weight"
                                )
                        ]
    
        final_completion_text = ""
        rejection_feedback = ""
        overall_matching_score = 0
        emailFeedback = ""
        overall_Analysis=""

        # for step in steps:
        #     prompt = create_prompt(cv_extract, job_desc, step)
        #     content = invoke_model_with_backoff(prompt)
        #     # content = invoke_model(prompt)
        #     final_completion_text = extract_text(content)
        #     print_completion_text(final_completion_text)

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
                # content = invoke_model_with_backoff_OpenAI(prompt,Task= "step 1 for score calculations" ,want_json=False)

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
                # content = invoke_model_with_backoff_OpenAI(prompt,Task= "step 2 for score calculations", want_json=False)
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
                # ccontent = invoke_model_with_backoff_OpenAI(prompt,Task= "step 3 for score calculations", want_json=False)
                
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
                # content = invoke_model_with_backoff_OpenAI(prompt,Task= "step 4 for score calculations", want_json=False)
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
        overall_matching_score = int(round(overall_matching_score))
        # print("overall_matching_score", overall_matching_score)
        # print("overall_Analysis:-", overall_Analysis)


        # overall_matching_score=50  #####################################  test with lower marks
        if 1 <= overall_matching_score < 70:
            prompt = (f"candidate profile : {processed_text}, job requirements : {job_desc}\n"
                f"Analyze why this candidate scored low against job requirements highlight. Return response in exact JSON format:\n"
                f"{{\n"
                f"  \"RecruiterNote\": \"2–3 sentences summarizing overall fit, written in clear recruiter-friendly language.\",\n"
                f"  \"Strengths\": [\n"
                f"    \"Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                f"    \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                f"  ],\n"
                f"  \"Areas of Concern\": [\n"
                f"    \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                f"  ]\n"
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
                f"- Omit detail field if heading itself is self-explanatory.\n"
                f"Strict Rule 3:\n"
                f" Never use speculative phrases like 'resume shows' or 'appears to have' — state facts directly with calling candidate name.\n"
            )

            
            # content = invoke_model_with_backoff_OpenAI(prompt,Task= "Rejection for 1 <= overall_matching_score < 70:" )
            content =  gpt_models[0].invoke_model_with_backoff(prompt,Task= "Rejection for 1 <= overall_matching_score < 70:"  )
            completion_text_rejection = json.dumps(content)

            # content = invoke_model_with_backoff_nova(prompt)
            # completion_text_rejection = extract_text_from_nova(content)
            print("***************************************  1 <70 *********************************************")
            print_completion_text(completion_text_rejection)
            rejection_feedback = completion_text_rejection

            if overall_matching_score > 40:
                prompt = (f"{final_completion_text}, {completion_text_rejection}\n"
                         f"Based on the above content, write a one-line summary in 20-25 words that highlights ONLY the positive qualities and strengths that make this candidate suitable for the job.\n"
                         f"Focus exclusively on positive aspects - exclude any negative feedback or criticisms.")

                content = invoke_model_with_backoff_nova(prompt)
                emailFeedback = extract_text_from_nova(content)
                print("feedback_for_email:-",emailFeedback)
            
        elif overall_matching_score >= 70:
            prompt = (f"You are an expert recruiter. Your only task is to compare the candidate profile against the job description."
                        f"Only use details explicitly stated in the provided text. Do not infer, assume, or invent information."
                        f"Input:"
                        f"- Candidate Profile: {processed_text}"
                        f"- Job Description: {job_desc}"
                        f"Output:"
                        f"Provide recruiter feedback in JSON format with three keys: \"RecruiterNote\", \"Strengths\", and \"Areas of Concern\"."
                        f"Format Example:"
                        f"{{\n"
                        f"  \"RecruiterNote\": \"2–3 sentences summarizing overall fit, written in clear recruiter-friendly language.\",\n"
                        f"  \"Strengths\": [\n"
                        f"    \"Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                        f"    \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                        f"  ],\n"
                        f"  \"Areas of Concern\": [\n"
                        f"    \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                        f"  ]\n"
                        f"}}\n"
                        f"Strict Rules:"  
                        f"1. **RecruiterNote** → A concise 3–5 line summary of candidate fit, overall impression, and readiness for the role."  
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
                        f"13. Never use speculative phrases like 'resume shows' or 'appears to have' — state facts directly with calling candidate name."
                        f"15. **EXACT WORDING RULE**: Only use terminology explicitly stated in the resume/Job Description. Never generalize specific implementations into broader industry terms."
                        f"16. **NO DOMAIN INFERENCE**: Do not infer industry expertise from individual projects or features. State only the specific technologies/projects mentioned."
                        f"17. **FACT-CHECK REQUIREMENT**: Before including any point, verify the exact phrase exists in either the Job Description or Candidate Profile text."
                        f"18. **GRANULAR SPECIFICITY**: When mentioning experience, reference the exact role/company where it was gained, not as broad industry background."  
                        f"19. Output format must be **valid JSON only**, no text outside JSON."   
	
                    )

            # content = invoke_model_with_backoff_OpenAI(prompt,Task= "Score feedback for >70")
            content =  gpt_models[0].invoke_model_with_backoff(prompt,Task= "Score feedback for >70")
            completion_text_approval = json.dumps(content)
            
            # content = invoke_model_with_backoff_nova(prompt)
            # completion_text_approval = extract_text_from_nova(content)
            print("***************************************   >70 *********************************************")
            print_completion_text(completion_text_approval)
            final_completion_text = completion_text_approval

            prompt = (f"{final_completion_text}\n"
                     f"Based on the above content, write a one-line summary in 20-25 words that highlights ONLY the positive qualities and strengths that make this candidate suitable for the job.\n"
                     f"Focus exclusively on positive aspects - exclude any negative feedback or criticisms.")

            content = invoke_model_with_backoff_nova(prompt)
            emailFeedback = extract_text_from_nova(content)
            print("feedback_for_email:-",emailFeedback)
            
        elif overall_matching_score == 0:
            rejection_feedback = "We encountered an error while processing. Please try again after some time"
        
        if overall_matching_score > 90:
            print("******Potential Issue******:", overall_matching_score)
            overall_matching_score = 90

        processing_status = "COMPLETED"
        update_ref_response_in_dynamodb(table_name, partition_key_value, sort_key_prefix, cv_extract, cv_extracted_parsed, final_completion_text, overall_matching_score, rejection_feedback, emailFeedback, processing_status)
        
    except Exception as e:
        print(f"An error occurred: {e}")
        # update_cv_extract_in_dynamodb(table_name, partition_key_value, sort_key_prefix, str(e) , 251, -1)
        return {"statusCode": 500, "body": {"error": str(e)}}
    
    return {"statusCode": 200, "body": 
        {"Overall Matching Score": overall_matching_score}
    }

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

def clean_json_response(response: str) -> str:
    return response.strip().removeprefix("```json").removesuffix("```").strip()

def lambda_handler(event, context):
    print("event-----", event)
    table_name = os.environ.get('table_name')

    env = os.environ.get("ENVIRONMENT","dev")
    GCP_secret_name = "GCP-firestore-secret-"+env
    print(GCP_secret_name)

    table_name = "worko"

    queue_name = os.environ.get('queue_name')
    GCP_credentials = get_secret(GCP_secret_name)
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
    # queue_name = 'worko-app-event-queue'
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

    azure_openai_secret_name = "AZURE-openai-secret-multimodel-"+env
    azure_openai_secret = get_secret(azure_openai_secret_name)
    gpt4 = AzureOpenAIClient(azure_openai_secret,model="gpt-4o")
    gpt_models = [gpt4]
    cv_extract, cv_extracted_parsed = process_cv(processed_text,gpt_models)
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

    update_ref_response_in_dynamodb(table_name, cv_partition_key_value, cv_sort_key_prefix_value, cv_extract, cv_extracted_parsed, scoreDetails, matchingScore, rejection_feedback, emailFeedback, processing_status)

    score = jd_resume_matching(table_name, cv_partition_key_value, cv_sort_key_prefix_value, job_desc, processed_text, cv_extract, cv_extracted_parsed,gpt_models)
            
    print("Score----",score)

    #Uncomment before deploying in production, uncommented for testing in dev
    update_sqs_queue(queue_url, "", "", cv_id, "BULK")
    
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


    lambda_handler(event, None)
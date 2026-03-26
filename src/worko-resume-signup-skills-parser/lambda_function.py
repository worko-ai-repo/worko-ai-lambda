import json
import boto3
import fitz
import os
import re
from decimal import Decimal
from boto3.dynamodb.types import TypeDeserializer
from datetime import datetime
import botocore
from docx import Document
from io import BytesIO
import time
import requests

import io                    
import base64                

# Initialize the AWS service clients
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')
# bedrock_runtime = boto3.client('bedrock-runtime', region_name='ap-south-1')
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')

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

def invoke_model_nova(prompt):
    body = json.dumps({
        "inferenceConfig": {
            "max_new_tokens": 4697, "temperature":0.1
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
    modelId= "amazon.nova-lite-v1:0"
    # modelId= "amazon.nova-micro-v1:0"
    # modelId= "amazon.nova-canvas-v1:0"

    print("Model used-", modelId)

    response = bedrock_runtime.invoke_model(
        body=body,
        modelId=modelId,
        contentType='application/json',
        accept='application/json'
    )
    
    response_body = json.loads(response['body'].read())
    
    return response_body

def convert_floats_to_decimals(obj):
    """ Recursively convert float, int, and numeric strings in dict/list to Decimal for DynamoDB """
    if isinstance(obj, list):
        return [convert_floats_to_decimals(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, (float, int)):
        return Decimal(str(obj))  # Safe conversion
    elif isinstance(obj, str):
        # Try converting numeric strings to Decimal
        try:
            return Decimal(obj)
        except:
            return obj
    else:
        return obj
def update_otherSocialPlatForms_in_dynamodb(table_name, partition_key, otherSocialPlatForms):
    table = dynamodb.Table(table_name)

    social_fields = ["linkedin", "github", "twitter"]

    update_expressions = []
    expression_values = {}

    # Always ensure linkedin, github, twitter exist at the top level
    for field in social_fields:
        value = otherSocialPlatForms.get(field, "")

        # Normalize to list of strings
        if isinstance(value, str):
            value = [value] if value.strip() else [""]
        elif isinstance(value, list):
            # Clean list, default to [""] if empty
            value = [str(v) for v in value if str(v).strip()] or [""]
        else:
            value = [str(value)]

        update_expressions.append(f"{field} = :{field}")
        expression_values[f":{field}"] = value

    # Keep only extra fields in otherSocialPlatForms
    extra_socials = {
        k: v for k, v in otherSocialPlatForms.items() if k not in social_fields
    }

    update_expressions.append("otherSocialPlatForms = :otherSocialPlatForms")
    expression_values[":otherSocialPlatForms"] = extra_socials

    update_expression = "SET " + ", ".join(update_expressions)

    response = table.update_item(
        Key={
            'PK': partition_key,
            'SK': "SOCIAL#"
        },
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_values,
        ReturnValues="UPDATED_NEW"
    )

    return response


def update_cv_extract_in_dynamodb(table_name, partition_key, sort_key, cv_extract):
    table = dynamodb.Table(table_name)

    # Get current date and time
    current_datetime = datetime.now().isoformat()

    response = table.update_item(
        Key={
            'PK': partition_key,
            'SK': sort_key
        },
        UpdateExpression="SET cvExtract = :cvExtract, cvExtractDate = :cvExtractDate",
        
        ExpressionAttributeValues={
            ':cvExtract': cv_extract,
            ':cvExtractDate': current_datetime
        },
        ReturnValues="UPDATED_NEW"
    )
    return response

dynamodb = boto3.resource('dynamodb')


def update_frontend_auto_populations_in_dynamodb(table_name, partition_key, sort_key, frontend_auto_populations):
    multipleCandidateExperience = frontend_auto_populations.get("multipleCandidateExperience", None)
    about = frontend_auto_populations.get("about", None)
    responsibilities = frontend_auto_populations.get("responsibilities", [])

    # Clean responsibilities endDate if "present"
    for k in responsibilities:
        if k.get("date", {}).get("endDate", "").lower() == "present":
            k["date"]["endDate"] = ""
    for k in multipleCandidateExperience:
        if k.get("endDate", "").lower() == "present":
            k["endDate"] = ""

    
    for i in multipleCandidateExperience:
        if float(i["YOE"])<0.5:
            i["YOE"]=0.5
    # Convert floats to Decimal before sending to DynamoDB
    multipleCandidateExperience = convert_floats_to_decimals(multipleCandidateExperience)

    about = convert_floats_to_decimals(about)
    responsibilities = convert_floats_to_decimals(responsibilities)

    table = dynamodb.Table(table_name)

    # Get current date and time
    current_datetime = datetime.now().isoformat()


    response = table.update_item(
    Key={
        'PK': partition_key,
        'SK': sort_key
    },
    UpdateExpression="""
        SET multipleCandidateExperience = :multipleCandidateExperience,
            multipleCandidateExperiencedDate = :multipleCandidateExperiencedDate,
            about = :about,
            responsibilities = :responsibilities
    """,
    ExpressionAttributeValues={
        ':multipleCandidateExperience': multipleCandidateExperience,
        ':multipleCandidateExperiencedDate': current_datetime,
        ':about': about,
        ':responsibilities': responsibilities
    },
    ReturnValues="UPDATED_NEW"
    )
    return response


def update_cv_extract_parsed_in_dynamodb(table_name, partition_key, sort_key, cv_extract_parsed):
    for i in cv_extract_parsed['multipleCandidateExperience']:
        i["YOE"]=Decimal(str(i["YOE"]))
        if i["YOE"]<0.5:
            i["YOE"]=0.5
        

    table = dynamodb.Table(table_name)

    # Get current date and time
    current_datetime = datetime.now().isoformat()

    response = table.update_item(
        Key={
            'PK': partition_key,
            'SK': sort_key
        },
        UpdateExpression="SET cvExtractParsed = :cvExtractParsed, cvExtractParsedDate = :cvExtractParsedDate",
        
        ExpressionAttributeValues={
            ':cvExtractParsed': cv_extract_parsed,
            ':cvExtractParsedDate': current_datetime
        },
        ReturnValues="UPDATED_NEW"
    )
    return response

def update_yoe_in_dynamodb(table_name, partition_key, sort_key_prefix, yoe):
    
    table = dynamodb.Table(table_name)
    
    try:
        # Query to find items that match the partition key and sort key prefix
        response = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ':pk': partition_key,
                ':sk_prefix': sort_key_prefix
            }
        )
        
        # If no items found, return error
        if 'Items' not in response or len(response['Items']) == 0:
            return {
                "error": f"No records found with PK={partition_key} and SK beginning with {sort_key_prefix}. No update performed."
            }
        
        # Extract the first matching item's complete sort key
        complete_sort_key = response['Items'][0]['SK']
        
        # If yoe is a list with a single value, extract the value first
        if isinstance(yoe, list) and len(yoe) == 1:
            yoe = yoe[0]
        
        # Convert YOE to Decimal if it's a float or int (after extracting from list)
        if isinstance(yoe, (float, int)):
            yoe = Decimal(str(yoe))
        
        # Create update expression
        update_expression = "SET YOE = :yoe, updatedAt = :updatedAt"
        
        # Set the expression attribute values
        expression_attribute_values = {
            ':yoe': yoe,  # This will be a single value, not a list
            ':updatedAt': int(datetime.now().timestamp() * 1000)
        }
        
        # Perform the update using the complete sort key
        update_response = table.update_item(
            Key={
                'PK': partition_key,
                'SK': complete_sort_key
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW"
        )
        
        return update_response
        
    except Exception as e:
        print(f"Error updating YOE: {str(e)}")
        return {"error": str(e)}

def update_skills_in_dynamodb(table_name, partition_key, sort_key, core_skills, technical_skills, soft_skills):
    table = dynamodb.Table(table_name)
    
    # Helper function to convert floats to Decimal
    def convert_floats_to_decimal(obj):
        if isinstance(obj, list):
            return [convert_floats_to_decimal(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, float):
            return Decimal(str(obj))
        else:
            return obj
    
    try:
        # Convert float values to Decimal before using with DynamoDB
        core_skills = convert_floats_to_decimal(core_skills)
        technical_skills = convert_floats_to_decimal(technical_skills)
        soft_skills = convert_floats_to_decimal(soft_skills)
        
        # Prepare update expression and attribute values
        update_parts = []
        expression_attribute_values = {}
        
        # Always update coreSkills
        update_parts.append("coreSkills = :coreSkills")
        expression_attribute_values[':coreSkills'] = core_skills

        # Always update technicalskills
        update_parts.append("technicalSkills = :technicalSkills")
        expression_attribute_values[':technicalSkills'] = technical_skills

        # Always update softSkills
        update_parts.append("softSkills = :softSkills")
        expression_attribute_values[':softSkills'] = soft_skills
        
        # Update the timestamp
        update_parts.append("updatedAt = :updatedAt")
        expression_attribute_values[':updatedAt'] = int(datetime.now().timestamp() * 1000)
        
        # Combine all update parts into a single SET clause
        update_expression = "SET " + ", ".join(update_parts)
        
        # Perform the update
        response = table.update_item(
            Key={
                'PK': partition_key,
                'SK': sort_key
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW"
        )
        
        return response
    
    except Exception as e:
        print(f"Error updating skills: {str(e)}")
        return {"error": str(e)}


def update_pref_department_in_dynamo(table_name, partition_key, sort_key, Prefered_departments):
    table = dynamodb.Table(table_name)
    email = partition_key.split('#')[2]
    # Helper function to convert floats to Decimal

    
    try:
        # Prepare update expression and attribute values
        update_parts = []
        expression_attribute_values = {}
        
        # Always update Prefered_departments
        update_parts.append("Prefered_departments = :Prefered_departments")
        expression_attribute_values[':Prefered_departments'] = Prefered_departments

        # Always update email
        update_parts.append("email = :email")
        expression_attribute_values[':email'] = email

        # Update the timestamp
        update_parts.append("updatedAt = :updatedAt")
        expression_attribute_values[':updatedAt'] = int(datetime.now().timestamp() * 1000)
        
        # Combine all update parts into a single SET clause
        update_expression = "SET " + ", ".join(update_parts)
        
        # Perform the update
        response = table.update_item(
            Key={
                'PK': partition_key,
                'SK': sort_key
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW"
        )
        
        return response
    
    except Exception as e:
        print(f"Error updating skills: {str(e)}")
        return {"error": str(e)}

def update_pref_section_in_dynamo(table_name, partition_key, sort_key, Prefered_section):
    table = dynamodb.Table(table_name)
    email = partition_key.split('#')[2]
    # Helper function to convert floats to Decimal

    
    try:
        # Prepare update expression and attribute values
        update_parts = []
        expression_attribute_values = {}
        
        # Always update Prefered_departments
        update_parts.append("Prefered_departments = :Prefered_departments")
        expression_attribute_values[':Prefered_departments'] = Prefered_departments

        # Always update email
        update_parts.append("email = :email")
        expression_attribute_values[':email'] = email

        # Update the timestamp
        update_parts.append("updatedAt = :updatedAt")
        expression_attribute_values[':updatedAt'] = int(datetime.now().timestamp() * 1000)
        
        # Combine all update parts into a single SET clause
        update_expression = "SET " + ", ".join(update_parts)
        
        # Perform the update
        response = table.update_item(
            Key={
                'PK': partition_key,
                'SK': sort_key
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW"
        )
        
        return response
    
    except Exception as e:
        print(f"Error updating skills: {str(e)}")
        return {"error": str(e)}

def print_completion_text(completion_text):
    print("***********************************************************************")
    print(completion_text)
    print("#######################################################################")

def invoke_model_with_backoff(prompt, max_retries=5, base_delay=1):
    for attempt in range(max_retries):
        try:
            # return invoke_model(prompt)
            return invoke_model_nova(prompt)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < max_retries - 1:
                delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                print(f"Throttling occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                raise
def invoke_model_with_backoff_sonnet(prompt, max_retries=5, base_delay=1):
    for attempt in range(max_retries):
        try:
            # return invoke_model(prompt)
            return invoke_model_soonet(prompt)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < max_retries - 1:
                delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                print(f"Throttling occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                raise

def extract_data_nova(input_data):

    try:
        # Step 1: Convert input to dictionary if it's a string
        if isinstance(input_data, str):
            try:
                # Try standard JSON parsing first
                data = json.loads(input_data)
            except json.JSONDecodeError:
                # If that fails, try handling Python-style dict strings with single quotes
                try:
                    data = ast.literal_eval(input_data)
                except (SyntaxError, ValueError):
                    # Last attempt: replace single quotes with double quotes and try again
                    input_data = input_data.replace("'", '"')
                    data = json.loads(input_data)
        else:
            # Input is already a dictionary
            data = input_data
            
        # Step 2: Extract the text content from the standardized dictionary structure
        text_content = data['output']['message']['content'][0]['text']
        
        # Step 3: Return the extracted text
        return text_content
        
    except Exception as e:
        return f"Error extracting text: {str(e)}"

def extract_skill_data_nova(input_data):
    import json
    import ast
    import re

    try:
        # Step 1: Convert input to dictionary if it's a string
        if isinstance(input_data, str):
            try:
                # Try standard JSON parsing first
                data = json.loads(input_data)
            except json.JSONDecodeError:
                # If that fails, try handling Python-style dict strings with single quotes
                try:
                    data = ast.literal_eval(input_data)
                except (SyntaxError, ValueError):
                    # Last attempt: replace single quotes with double quotes and try again
                    input_data = input_data.replace("'", '"')
                    data = json.loads(input_data)
        else:
            # Input is already a dictionary
            data = input_data
            
        # Step 2: Extract the text content from the standardized dictionary structure
        text_content = data['output']['message']['content'][0]['text']
        
        # Step 3: Clean the text content (remove markdown code blocks if present)
        json_text = re.sub(r'```json\s*|\s*```', '', text_content)
        
        # Step 4: Parse the JSON
        skills_data = json.loads(json_text)
        
        # Step 5: Extract coreSkills and softSkills
        core_skills = skills_data['coreSkills']
        technical_skills = skills_data['technicalSkills']
        soft_skills = skills_data['softSkills']
        Prefered_departments = skills_data['Prefered_departments']
        yoe = skills_data['YOE']
        
        # Return the extracted JSON structures
        return skills_data
        
    except Exception as e:
        return None, f"Error extracting skills: {str(e)}"

def update_technical_skills_years(technical_skills):
    # Transform each skill's 'years' from a list to a number
    return [
        {**skill, 'years': skill.get('years', [0])[0] if skill.get('years') else 0} 
        for skill in technical_skills
    ]

def update_core_skills_years(core_skills):
    # Transform each skill's 'years' from a list to a number
    return [
        {**skill, 'years': skill.get('years', [0])[0] if skill.get('years') else 0} 
        for skill in core_skills
    ]
def clean_json_response(response: str) -> str:
    return response.strip().removeprefix("```json").removesuffix("```").strip()
def clean_json_string(json_string):
    # Remove ```json from the beginning if present
    if json_string.startswith("```json"):
        json_string = json_string[7:]
    # Remove ``` from the beginning if present
    elif json_string.startswith("```"):
        json_string = json_string[3:]
    
    # Remove ``` from the end if present
    if json_string.endswith("```"):
        json_string = json_string[:-3]
    
    # Strip any extra whitespace
    json_string = json_string.strip()
    
    return json_string

def has_key_elements(resume_text, key_elements_dict, min_required_categories=2, min_total_elements=5):
    
    # Initialize tracking
    total_elements_found = 0
    found_elements = {category: [] for category in key_elements_dict.keys()}
    
    # Handle different input types
    if isinstance(resume_text, dict):
        resume_text_str = str(resume_text).lower()
    elif isinstance(resume_text, str):
        resume_text_str = resume_text.lower()
    else:
        resume_text_str = str(resume_text).lower()
    
    # Preprocessing: Replace spaced out text like "C O N T A C T" with "CONTACT"
    # Find patterns like "C O N T A C T" and convert to "CONTACT"
    spaced_words = re.findall(r'\b([A-Z](\s+[A-Z])+)\b', resume_text)
    for match in spaced_words:
        original = match[0]
        fixed = original.replace(" ", "")
        resume_text_str = resume_text_str.replace(original.lower(), fixed.lower())
    
    # Debug: Print the first 100 characters of the text
    print(f"Text preview: {resume_text_str[:100]}...")
    
    # Detect common personal info formats first
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    phone_pattern = r'\b(?:\+\d{1,3}[-\s]?)?\d{3,}[-\s.]?\d{3,}[-\s.]?\d{3,4}\b'
    
    # Check for email and phone directly - these are strong personal info indicators
    email_match = re.search(email_pattern, resume_text_str)
    phone_match = re.search(phone_pattern, resume_text_str)
    
    if email_match:
        found_elements["personal_info"].append("email")
        total_elements_found += 1
        print(f"Found element: email (category: personal_info) - {email_match.group()}")
    
    if phone_match:
        found_elements["personal_info"].append("phone")
        total_elements_found += 1
        print(f"Found element: phone (category: personal_info) - {phone_match.group()}")
    
    # Check each category for keyword-based elements
    for category, elements in key_elements_dict.items():
        for element in elements:
            # Skip email and phone for personal_info as we already handled them
            if category == "personal_info" and element in ["email", "phone"]:
                continue
            
            # Create patterns for accurate matching
            element_escaped = re.escape(element.lower())
            patterns = [
                f"\\b{element_escaped}\\b",                         # Word by itself
                f"\\b{element_escaped}:",                           # Word followed by colon
                f"\\b{element_escaped} :",                          # Word followed by space and colon
                f"\\b{element_escaped}\\s+section",                 # Word followed by "section"
                f"\\b{element_escaped}\\s*\\n",                     # Word at end of line
                f"^{element_escaped}\\s*$",                         # Word on its own line
                f"\\n{element_escaped}\\s*\\n",                     # Word between newlines
            ]
            
            # Add special patterns for specific phrases
            if element.lower() == "contact me":
                patterns.extend([
                    r"\bcontact me\b",
                    r"\bcontact me at\b"
                ])
            elif element.lower() == "personal details":
                patterns.append(r"\bpersonal details\b")
            elif element.lower() == "personal profile":
                patterns.append(r"\bpersonal profile\b")
            elif element.lower() == "professional experience":
                patterns.extend([
                    r"\bprofessional experience\b",
                    r"\bwork experience\b",
                    r"\bemployment history\b"
                ])
            elif element.lower() == "education":
                patterns.extend([
                    r"\beducation\b",
                    r"\bacademic background\b",
                    r"\bacademic qualification\b"
                ])
            
            # Check if any pattern matches
            element_found = False
            for pattern in patterns:
                if re.search(pattern, resume_text_str, re.MULTILINE | re.IGNORECASE):
                    if element not in found_elements[category]:
                        found_elements[category].append(element)
                        total_elements_found += 1
                        element_found = True
                        print(f"Found element: {element} (category: {category})")
                    break
            
            if element_found:
                continue  # Move to next element
    
    # Check if name is likely present (at the top, capitalized)
    # Look for standalone capitalized words that might be names
    potential_name_lines = re.findall(r'^([A-Z][a-z]+\s+[A-Z][a-z]+)', resume_text_str, re.MULTILINE)
    if potential_name_lines:
        if "name" not in found_elements["personal_info"]:
            found_elements["personal_info"].append("name")
            total_elements_found += 1
            print(f"Found element: name (category: personal_info) - {potential_name_lines[0]}")
    
    # Count categories that have any found elements
    categories_with_matches = sum(1 for elements in found_elements.values() if len(elements) > 0)
    
    print(f"Categories with matches: {categories_with_matches}/{len(key_elements_dict)}")
    print(f"Total elements found: {total_elements_found}")
    print(f"Found elements by category: {found_elements}")
    
    # Check if we meet both category and total element thresholds
    is_valid = (categories_with_matches >= min_required_categories and 
                total_elements_found >= min_total_elements)
    
    return is_valid, found_elements, total_elements_found

def check_if_resume(processed_text):

    if not processed_text:
        print("No text provided")
        return {"statusCode": 404, "body": "No text provided"}
    
    # Define categories with higher weights for critical resume sections
    resume_elements = {
        # Critical resume sections (highest weight)
        "core_sections": [
            'experience', 'work history', 'employment', 'professional experience',
            'education', 'academic background', 'qualification', 'qualifications',
            'work experience', 'career highlights'  # Added these common variants
        ],
        
        # Important but not critical sections
        "additional_sections": [
            'skills', 'technical skills', 'soft skills', 
            'certifications', 'certificates', 'accreditations',
            'projects', 'achievements', 'accomplishments',
            'publications', 'research', 'patents', 
            'core competencies', 'it skills'  # Added these common variants
        ],
        
        # Common resume sections
        "standard_sections": [
            'summary', 'profile', 'professional summary', 'career objective',
            'objective', 'references', 'languages', 'volunteer', 'leadership',
            'responsibilities', 'expertise', 'competencies',
            'personal profile', 'career highlights'  # Added these common variants
        ],
        
        # Personal information (must have some contact info)
        "personal_info": [
            'name', 'email', 'phone', 'contact', 'address', 
            'linkedin', 'github', 'portfolio', 'website',
            'personal details', 'contact me'  # Added these common variants
        ]
    }
    
    # Settings for validation
    min_required_categories = 2  # Need matches from at least 2 categories
    min_total_elements = 5       # Need at least 5 total elements across all categories
    
    # At least one from personal_info + one from core_sections = strong resume indicator
    is_valid, found_elements, total_found = has_key_elements(
        processed_text, 
        resume_elements,
        min_required_categories,
        min_total_elements
    )
    
    # Additional checks for higher confidence:
    # 1. Must have at least one personal info element
    # 2. Must have at least one core section
    has_personal_info = len(found_elements["personal_info"]) > 0
    has_core_section = len(found_elements["core_sections"]) > 0
    
    # More detailed validation logic with better messaging
    if is_valid:
        if has_personal_info and has_core_section:
            # High confidence - has both personal info and core sections
            confidence = "high" if total_found >= 8 else "medium"
            return {
                "statusCode": 200, 
                "body": "Valid resume found",
                "details": {
                    "elements_found": found_elements,
                    "confidence": confidence
                }
            }
        else:
            # Moderate confidence - missing either personal info or core sections
            missing_elements = []
            if not has_personal_info:
                missing_elements.append("personal information (contact details, email, phone)")
            if not has_core_section:
                missing_elements.append("core resume sections (experience, education)")
                
            return {
                "statusCode": 200,  # Changed to 200 since it's still likely a resume
                "body": f"Partial resume detected - missing {', '.join(missing_elements)}",
                "details": {
                    "elements_found": found_elements,
                    "missing_critical": {
                        "personal_info": not has_personal_info,
                        "core_sections": not has_core_section
                    },
                    "confidence": "low"
                }
            }
    else:
        # Not enough elements found to be considered a resume
        return {"statusCode": 404, "body": "Not a valid resume"}

def invoke_model_soonet(prompt):
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

from datetime import datetime
from decimal import Decimal
import boto3

dynamodb = boto3.resource('dynamodb')

from datetime import datetime
import boto3

dynamodb = boto3.resource('dynamodb')
def invoke_model_with_backoff_OpenAI(prompt, max_retries=10, base_delay=2):
    system_content = "You are a helpful assistant."
    
    for attempt in range(max_retries):
        try:
            return invoke_model_OpenAI(system_content, prompt)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < max_retries - 1:
                delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                print(f"Throttling occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                raise
def invoke_model_OpenAI(system_content, prompt):
    # Read sensitive config from environment variables
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
        ]
    }

    try:
        response = requests.post(url=url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]

    except requests.exceptions.HTTPError as err:
        print("HTTP Error:", err)
        print("Response Text:", response.text)
        raise

    except Exception as e:
        print("General Error:", e)
        raise



def reset_skills_if_partition_exists(table_name, partition_key, sort_key):
    table = dynamodb.Table(table_name)

    try:
        # First, check if the item exists
        response = table.get_item(
            Key={
                'PK': partition_key,
                'SK': sort_key
            }
        )

        if 'Item' not in response:
            # No item found for this partition
            return {"message": "Item not found, nothing updated"}

        # If item exists, reset all skills to empty arrays
        update_expression = "SET coreSkills = :emptyList, technicalSkills = :emptyList, softSkills = :emptyList, updatedAt = :updatedAt"
        
        expression_attribute_values = {
            ":emptyList": [],
            ":updatedAt": int(datetime.now().timestamp() * 1000)
        }

        update_response = table.update_item(
            Key={
                'PK': partition_key,
                'SK': sort_key
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW"
        )

        return update_response

    except Exception as e:
        return {"error": str(e)}
def invoke_model_with_backoff_OpenAI(prompt, max_retries=10, base_delay=2):
    system_content = "You are a helpful assistant."
    
    for attempt in range(max_retries):
        try:
            return invoke_model_OpenAI(system_content, prompt)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < max_retries - 1:
                delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                print(f"Throttling occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                raise
def invoke_model_OpenAI(system_content, prompt):
    # Read sensitive config from environment variables
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
        ]
    }

    try:
        response = requests.post(url=url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]

    except requests.exceptions.HTTPError as err:
        print("HTTP Error:", err)
        print("Response Text:", response.text)
        raise

    except Exception as e:
        print("General Error:", e)
        raise

def reset_frontend_auto_populations_in_dynamodb(table_name, partition_key, sort_key):
    # Force defaults
    multipleCandidateExperience = []
    about = ""
    responsibilities = []

    table = dynamodb.Table(table_name)

    # Get current date and time
    current_datetime = datetime.now().isoformat()

    response = table.update_item(
        Key={
            'PK': partition_key,
            'SK': sort_key
        },
        UpdateExpression="""
            SET multipleCandidateExperience = :multipleCandidateExperience,
                multipleCandidateExperiencedDate = :multipleCandidateExperiencedDate,
                about = :about,
                responsibilities = :responsibilities
        """,
        ExpressionAttributeValues={
            ':multipleCandidateExperience': multipleCandidateExperience,
            ':multipleCandidateExperiencedDate': current_datetime,
            ':about': about,
            ':responsibilities': responsibilities
        },
        ReturnValues="UPDATED_NEW"
    )

    return response


def clean_json_response(content):
    return content.strip().removeprefix("```json").removesuffix("```").strip()


def invoke_qwen3_32b(prompt: str,
                     stream: bool = False,
                     model_id: str = "qwen.qwen3-coder-480b-a35b-v1:0",
                     region: str = "ap-south-1") -> str or iter:
    """
    Invoke the Qwen3-32B dense model on Amazon Bedrock via boto3.

    Args:
        prompt (str): The user instruction or question.
        stream (bool): If True, stream the output as it arrives.
        model_id (str): Bedrock model ID for Qwen3-32B (dense).
        region (str): AWS region where model is available (default ap-south-1).

    Returns:
        str: Full generated content (if stream=False).
        iterator of str: Streaming text chunks (if stream=True).
    """
    try:
        client = boto3.client("bedrock-runtime", region_name=region)
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            "max_completion_tokens": 5000,
            "temperature": 0.1,
            "top_p": 0.1,
            "stream": stream
        }

        if stream:
            response = client.invoke_model_with_response_stream(
                modelId=model_id,
                contentType="application/json",
                body=json.dumps(payload),
                accept="application/json",
            )
            def generator():
                for event in response["body"]:
                    chunk = json.loads(event["chunk"]["bytes"])
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        if "content" in delta:
                            yield delta["content"]
            return generator()

        else:
            response = client.invoke_model(
                modelId=model_id,
                contentType="application/json",
                body=json.dumps(payload),
                accept="application/json",
            )
            resp_body = json.loads(response["body"].read().decode("utf-8"))
            texts = []
            for choice in resp_body.get("choices", []):
                msg = choice.get("message", {})
                if "content" in msg:
                    texts.append(msg["content"])
            return "\n".join(texts) or "(No output)"

    except (BotoCoreError, ClientError, json.JSONDecodeError) as e:
        if stream:
            return iter([f"[Error] {e}"])
        return f"[Error] {e}"

def get_json_from_qwen3(response):
    try:
        response = json.loads(response)
    except json.JSONDecodeError as e:
        print("qwen model colled seecond time for proper json format")
        prompt = f"make this broken json in a proper readable json  provide only json do not give anything else in output.  {response}"
        response = invoke_qwen3_32b(prompt)
        response = json.loads(response)

    except Exception as r:
        print(e)
    return response

def lambda_handler(event, context):
    start_time= time.time()
    print(event)
    resumeId = event.get('userId')
    cvId = event.get('s3ResumeId')
    key = "users/" + resumeId + "/resumes/" + cvId
    S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')
    end_time= time.time()
    # key="users/81d38daa-f061-7000-0f9e-64475bb44b9f/resumes/01K5ZV2E34TJ6F9DF8PWHK118Z.pdf"
    try:
        # Attempt to fetch the PDF file from S3
        response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=key)
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

    # Extract text from the PDF or DOCX file
    if ".pdf" in key:
        processed_text = extract_text_from_pdf(data)
        if not processed_text : 
            print('image Based cv processing..')                        ###
            base64_images = extract_images_from_pdf(data)
            processed_text = invoke_claude_with_image(base64_images)   
            print('image Based cv process completed')   

    print(f'Step 1 got cv from frontend  :- {end_time-start_time}')
    if processed_text:
    
        current_timestamp = datetime.now().isoformat()
        prompt = (
        f"**Extract the following details from the resume extract:**\n"
        f"- Core Skills (max 30 chars each)\n"
        f"- Soft Skills (max 30 chars each)\n"
        f"- userPreferredDepartments (for this field analyze entire resume and suggest some 0-5 departments based on experience and skills. example: data science, marketting)"
        f"- Years of Experience (YOE)\n"
        f"**Instructions**:\n"
        f"- Use ONLY information explicitly written in the resume. No assumptions.\n"
        f"- Extract ONLY the top 20 Core Skills and 20 Soft Skills.\n"
        f"- **Core Skills (TECH profiles): HIGH-LEVEL domains or expertise areas only (e.g., Software Development, Cloud Computing). DO NOT include tools, job responsibilities, or interpersonal abilities.**\n"
        f"Examples: System Architecture, Microservices Design.\n"
        f"- **Technical Skills: All specific tools, programming languages (Python, Java), frameworks (React, Django), cloud platforms (AWS, Azure), databases (MySQL), certifications.**\n"
        f"- **Core Skills (NON-TECH profiles): ONLY business or functional domains like Business Analysis, Marketing Strategy, Financial Planning. NEVER include leadership, management, team coordination, communication, mentoring, or action phrases.**\n"
        f"- **Technical Skills (NON-TECH): Tools (Salesforce, SAP), software (Excel, SQL), CRM, industry platforms, or certifications (PMP).**\n"
        f"- Soft Skills: ALL interpersonal or behavioral skills such as communication, teamwork, leadership, mentoring, negotiation, decision-making, adaptability, problem solving.\n"
        f"Examples: Communication, Teamwork, Leadership, Strategic Thinking.\n"
        f"- Add YOE for Core Skills if mentioned, else 0.\n"
        f"- Calculate total YOE from roles or experience dates; if missing, sum role durations.\n"
        f"**Mandatory moves**:\n"
        f"- The following are ALWAYS Soft Skills, NEVER Core Skills: 'Managing Escalations', 'Team Mentoring', 'Team Leadership', 'Strategic Planning', 'Stakeholder Management', 'Goal Setting', 'Problem Solving', 'Quick Learner', 'Leadership', 'Data-driven decision-making'.\n"
        f"- Core Skills MUST ONLY represent business or functional expertise or technical domains. DO NOT include:\n"
        f"  Job titles (e.g., Project Manager)\n"
        f" Action phrases (e.g., Managing escalations, Driving initiatives,Team mentoring)\n"
        f" Interpersonal traits (e.g., Leadership, Mentoring)\n"
        f" Technical tools or software (e.g., CRM systems, Excel, SAP, Salesforce)\n"
        f"- Use current timestamp for createdAt & updatedAt: {current_timestamp}\n"
        f"**STRICT Example**"
        f"coresklls : AWS or Cloud, Web App Design , Sales, Marketting"
        f"softSkills : Escalation handling, Strategy & Execution, Team mentoring, Presentation skills, Budget Management, Problem Solving, Quick Learner, Time management, Multi-tasking, Strategy & Execution"
        f"technicalSkills :CRM tools,"
        f"**STRICT RULES**:\n"
        f"- If more than 20 skills exist, pick the 20 most relevant.\n"
        f"- DO NOT guess, infer, or invent skills. Use ONLY resume text.\n"
        f"- A skill MUST appear in ONE category only. No duplicates across coreSkills, technicalSkills, softSkills.\n"
        f"- NEVER include full sentences, responsibilities, or job duties as skills.\n"
        f"- Skills MUST be concise names, NOT sentences.\n"
        f"- Never add Escalation handling, Team mentoring in Core skills these are soft skills"
        f"- For NON-TECH profiles: Core Skills = ONLY domain/business expertise. ALL leadership, mentoring, managing, stakeholder handling, escalation handling → Soft Skills.\n"
        f"- If a term includes verbs like 'Managing', 'Handling', 'Driving', 'Mentoring', classify it as Soft Skill.\n"
        f"- The following terms are ALWAYS Soft Skills: 'Problem Solving', 'Quick Learner', 'Team Mentoring', 'Leadership', 'Managing Escalations', 'Data-driven decision-making'.\n\n"
        f"Resume extract:\n\n{processed_text}\n\n"
        f"Return JSON only:\n"
        f"{{\n"
        f"  \"coreSkills\": [\n"
        f"    {{\"skillName\": \"[CORE_SKILL_NAME]\",\"years\":[YEARS_OF_EXPERIENCE]}}\n"
        f"  ],\n"
        f"  \"technicalSkills\": [\n"
        f"    {{\"skillName\": \"[TECHNICAL_SKILL_NAME]\",\"years\":[YEARS_OF_EXPERIENCE]}}\n"
        f"  ],\n"
        f"  \"softSkills\": [\n"
        f"    {{\"skillName\": \"[SOFT_SKILL_NAME]\"}}\n"
        f"  ],\n"
        f"  \"userPreferredDepartments\":[list the names of the departments that suits the cv ],\n"
        f"  \"YOE\": [TOTAL_YEARS_OF_EXPERIENCE]\n"
        f"}}"
    )



        #completion_text = invoke_qwen3_32b(prompt)
        #completion_text = get_json_from_qwen3(completion_text)

        content = invoke_model_with_backoff_OpenAI(prompt)
        completion_text = clean_json_response(content)
        print_completion_text(completion_text)
        try:
            completion_text = json.loads(completion_text)
        except Exception as e:
            print("can't load this as json")
        end_time = time.time()
        print(f'Step 2 Skils is fetched from cv time took :- {end_time-start_time}')
        print_completion_text(completion_text)
        # core_skills,technical_skills,soft_skills,Prefered_departments, yoe = extract_skill_data_nova(content)
        # content = extract_skill_data_nova(content)
        output = {"coreSkills":completion_text["coreSkills"],"userPreferredDepartments":completion_text["userPreferredDepartments"],"YOE":completion_text["YOE"]}

        
        return {
            'statusCode': 200,
            'body': json.dumps(output)
        }

    else:
        return {
            'statusCode': 404,
            'body': 'Item not found'
        }
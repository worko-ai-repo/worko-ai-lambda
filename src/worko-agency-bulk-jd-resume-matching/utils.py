
import boto3
from botocore.exceptions import ClientError
import json
import fitz
from typing import List, Tuple, Dict, Any, Optional, Union
from decimal import Decimal
import re


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
  
def extract_text_from_pdf(pdf_data):
    text = ""
    pdf_document = fitz.open(stream=pdf_data, filetype="pdf")
    for page in pdf_document:
        text += page.get_text()
    return text

def print_completion_text(content):
    print("*"*100, content,"*"*100)

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
    
    # Step 6: Rejoin lines and remove empty lines ")
    result = '\n'.join(line for line in cleaned_lines if line)
    
    return result

def create_prompt(cv_extract, job_desc, step ):
    return f'Human:\nResume:\n{cv_extract}\nJob Description:\n{job_desc}\n{step}'

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

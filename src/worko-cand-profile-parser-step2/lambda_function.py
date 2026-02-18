import json
import boto3
import os
import requests
import time
from datetime import datetime

sqs = boto3.client('sqs')

class AzureOpenAIClient:
    def __init__(self, azure_openai_secret, model="gpt-4o"):
        self.model = model
        self.endpoint = azure_openai_secret.get("AZURE_OPENAI_ENDPOINT", "")
        self.api_key = azure_openai_secret.get("AZURE_OPENAI_API_KEY", "")
        if model == "gpt-4o":
            self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT_gpt-4o", "")
            self.api_version = azure_openai_secret.get("AZURE_OPENAI_API_VERSION_gpt-4o", "2024-05-01-preview")
        elif model == "gpt-4.1-mini":
            self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT_gpt-4.1-mini", "")
            self.api_version = azure_openai_secret.get("AZURE_OPENAI_API_VERSION_gpt-4.1-mini", "2024-05-01-preview")
    
    def invoke_model_with_backoff(self, prompt, max_retries=10):
        for attempt in range(max_retries):
            try:
                return self.invoke_model(prompt)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code in [500, 502, 503, 504] and attempt < max_retries - 1:
                    delay = (2 ** attempt) * 2
                    time.sleep(delay)
                else:
                    raise
    
    def invoke_model(self, prompt):
        url = f"{self.endpoint}/openai/deployments/{self.deployment_name}/chat/completions?api-version={self.api_version}"
        headers = {"Content-Type": "application/json", "api-key": self.api_key}
        data = {"messages": [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": prompt}], "temperature": 0.3}
        response = requests.post(url=url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"].strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(content)

def get_secret(secret_name):
    secrets_client = boto3.client('secretsmanager', region_name='ap-south-1')
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

def get_queue_url(queue_name):
    response = sqs.get_queue_url(QueueName=queue_name)
    return response['QueueUrl']

def send_to_sqs(queue_name, body, delay_seconds=0):
    queue_url = get_queue_url(queue_name)
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(body), DelaySeconds=delay_seconds)

def process_cv(processed_text, gpt_models):
    current_timestamp = datetime.now().isoformat()
    parsed_prompt = f"Extract structured CV data from: {processed_text}. Return JSON with candidateName, candidateEmail, candidatePhoneNumber, candidateExperience, etc."
    cv_extracted_parsed = gpt_models[1].invoke_model_with_backoff(parsed_prompt)
    
    skills_prompt = f"Extract core skills, technical skills, soft skills from: {processed_text}. Return JSON."
    cv_extracted_parsed2 = gpt_models[0].invoke_model_with_backoff(skills_prompt)
    
    return {**cv_extracted_parsed, **cv_extracted_parsed2}

def lambda_handler(event, context):
    print(f"Step 2: Parse CV text")
    env = os.environ.get("ENVIRONMENT", "dev")
    retry_queue = f"state-machine-retry-{env}"
    step3_queue = f"worko-cand-profile-parser-step3-queue-{env}"
    
    try:
        body = json.loads(event['Records'][0]['body'])
        processed_text = body['processed_text']
        bucket_name = body['bucket_name']
        object_key = body['object_key']
        metadata = body.get('metadata', {})
        retry_counter = body.get('retry_counter', 0)
        
        if retry_counter >= 5:
            return {'statusCode': 200, 'body': 'Max retries'}
        
        azure_openai_secret = get_secret(f"AZURE-openai-secret-multimodel-{env}")
        gpt4 = AzureOpenAIClient(azure_openai_secret, model="gpt-4o")
        gpt4_1_mini = AzureOpenAIClient(azure_openai_secret, model="gpt-4.1-mini")
        gpt_models = [gpt4, gpt4_1_mini]
        
        cvExtractedParsed = process_cv(processed_text, gpt_models)
        
        if cvExtractedParsed:
            send_to_sqs(step3_queue, {'cvExtractedParsed': cvExtractedParsed, 'bucket_name': bucket_name, 'object_key': object_key, 'metadata': metadata, 'retry_counter': 0})
            return {'statusCode': 200, 'body': 'Step 2 completed'}
        else:
            raise Exception("Failed to parse CV")
            
    except Exception as e:
        error_message = str(e).lower()
        if any(term in error_message for term in ['throttling', 'rate limit', '429']):
            retry_counter += 1
            send_to_sqs(retry_queue, {'processed_text': processed_text, 'bucket_name': bucket_name, 'object_key': object_key, 'metadata': metadata, 'retry_counter': retry_counter, 'step': 2}, delay_seconds=90*retry_counter)
        print(f"Error in Step 2: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}

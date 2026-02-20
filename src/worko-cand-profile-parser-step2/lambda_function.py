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


def process_cv_step1(metadata,retry_queue_name, processed_text, gpt_models, bucket_name,object_key,retry_counter) -> Tuple[str, Dict[str, str]]:
    retry_counter +=1
    print("Processing cv for cvexractparesed with retry_counter:", retry_counter)
    try:
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

        if not processed_text:
            return "Unfortunately, we are not able to read your resume", processed_text

        

            
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
            f"1. candidatePhoneNumber: number with country code (string), 2. candidateNumber:  number only without country code (int), 3. candidatePhoneCountryCode (int),4.candidateNoticePeriod int or Null"
            f"Rule to return null values:\n"
            f" if any str key is not given in in resume text just return Null for that partcular fild "
            f" example :candidateNoticePeriod,candidateLocation"
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
        cv_extracted_parsed = gpt_models[1].invoke_model_with_backoff(parsed_prompt,Task= "get cvExtractparsed step1 ")
        # cv_extracted_parsed = OpenAIClient.invoke_model_with_backoff(parsed_prompt,Task= "get cvExtractparsed step1 " )
        return cv_extracted_parsed
        

    except Exception as execution_error:
        error_message = str(execution_error).lower()
        # error_traceback = traceback.format_exc()# Check if this is a throttling error
        if any(term in error_message for term in ['throttling', 'throttled', 'rate limit', 'too many requests', '429']):
            print("Errore of {execution_error} now sending sqs for startuing again in next 60 seconds")
            delay_seconds = 90*retry_counter
            body = {"bucket_name": bucket_name,"object_key": object_key,"from":"SQS throttling error","retry_counter":retry_counter ,"metadata":metadata}
            send_sqs_for_throttling_error(retry_queue_name,body,delay_seconds) #send sqs for throttled error
            return None 
        else:
            # For all other errors, just log and continue
            print(f"Error processing CV: {execution_error}")
            return None 

def lambda_handler(event, context):
    print(f"Step 2: Parse CV text")
    processed_text = event.get("processed_text")
    retry_queue_name = event.get("retry_queue_name")
    metadata = event.get("metadata")
    bucket_name =event.get("bucket_name")
    object_key = event.get("object_key")
    retry_counter = event.get("retry_counter")
    env = os.environ.get("ENVIRONMENT", "dev")
    retry_queue = f"state-machine-retry-{env}"
    
    azure_openai_secret_name = "AZURE-openai-secret-multimodel-"+env
    azure_openai_secret = get_secret(azure_openai_secret_name)
    gpt4 = AzureOpenAIClient(azure_openai_secret,model="gpt-4o")
    gpt4_1_mini = AzureOpenAIClient(azure_openai_secret,model="gpt-4.1-mini")
    gpt_models = [gpt4,gpt4_1_mini]
    process_cv_step1(metadata,retry_queue_name, processed_text, gpt_models, bucket_name,object_key,retry_counter) -> Tuple[str, Dict[str, str]]:
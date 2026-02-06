# gpt-4.1-mini confugrations
import requests
import json
from typing import Tuple, Dict, Any, Optional, Union
import boto3
import time
import json
from typing import Callable, Any



#     ############################################################################
# def get_queue_url(queue_name):
#     sqs = boto3.client('sqs')
#     response = sqs.get_queue_url(QueueName=queue_name)
#     return response['QueueUrl']

# def decimal_default(obj):
#     if isinstance(obj, Decimal):
#         return float(obj)
#     raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

# def send_sqs_for_throttling_error(retry_queue_name,message_body):
#     try:
#         retry_counter = message_body.get("retry_counter", "retry_counter not found")
#         from datetime import datetime, timedelta
#         queue_url = get_queue_url(retry_queue_name)
#         sqs = boto3.client('sqs')
        
#         # message_body = {"processed_text": processed_text,"object_key": object_key,"from":"throttling error"}
#         delay_seconds = 5
        
#         current_time = datetime.now()
#         visible_time = current_time + timedelta(seconds=delay_seconds)
        
#         print(f"Sending message to SQS with retry_counter: {retry_counter}")
#         print(f"[SQS SEND] Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
#         print(f"[SQS SEND] Message will be visible at: {visible_time.strftime('%Y-%m-%d %H:%M:%S')}")
#         print(f"[SQS SEND] DelaySeconds: {delay_seconds}")
#         print(f"SQS message body for throttled steps: {json.dumps(str(message_body)[:100])}")
        
#         response = sqs.send_message(
#             QueueUrl=queue_url,
#             MessageBody=json.dumps(message_body, default=decimal_default),
#             DelaySeconds=delay_seconds
#         )
        
#         print(f"[SQS SEND] MessageId: {response.get('MessageId', 'N/A')}")
        
        
#     except Exception as sqs_error:
#         print(f"Error sending send_sqs_for_throttling_error step to SQS: {sqs_error}")
#         print(f"Queue URL attempted: {queue_url}")
#         print(f"Message body: {message_body}")

# retry_queue_name = "worko-cand-profile-parser-retry-queue-dev"

# for i in range(10):
#     message_body = {f"testing_and_test{i}":"7757852171"}
#     # time.sleep(2)
#     send_sqs_for_throttling_error(retry_queue_name,message_body)

    ############################################################################
# def get_queue_url(queue_name):
#     sqs = boto3.client('sqs')
#     response = sqs.get_queue_url(QueueName=queue_name)
#     return response['QueueUrl']





# retry_queue_name = "worko-cand-profile-parser-retry-queue-dev"
# print(get_queue_url(retry_queue_name))
# azure_openai_secret = {"AZURE_OPENAI_API_KEY" :"REDACTED",
#                         "AZURE_OPENAI_API_VERSION" : "2024-12-01-preview",
#                         "AZURE_OPENAI_DEPLOYMENT" : "gpt-4.1-mini",
#                         "AZURE_OPENAI_ENDPOINT":"https://aif-wrk-dev-sin-01.openai.azure.com"}

# def get_secret(secret_name):
#     secrets_client = boto3.client('secretsmanager', region_name='ap-south-1')

#     try:
#         response = secrets_client.get_secret_value(SecretId=secret_name)
#         secret_value = response['SecretString']
        
#         # Try to parse as JSON, fallback to string
#         try:
#             secret_data = json.loads(secret_value)
#         except json.JSONDecodeError:
#             secret_data = secret_value
#         return secret_data
#     except ClientError as e:
#         if e.response['Error']['Code'] == 'ResourceNotFoundException':
#             return {
#                 "statusCode": 404,
#                 "body": json.dumps({"error": f"Secret '{secret_name}' not found"})
#             }

# secret_name = "AZURE-openai-secret-multimodel-dev"
# azure_openai_secret =get_secret(secret_name)
# print(azure_openai_secret)


# class AzureOpenAIClient:
#     """Client for Azure OpenAI API with retry logic."""
    
#     DEFAULT_TEMPERATURE = 0.3
#     DEFAULT_API_VERSION = "2024-05-01-preview"
#     REQUEST_TIMEOUT = 30  # seconds
    
#     def __init__(self, azure_openai_secret: Dict[str, str]):
#         """Initialize Azure OpenAI client.
        
#         Args:
#             azure_openai_secret: Dict containing:
#                 - AZURE_OPENAI_ENDPOINT
#                 - deployment_name
#                 - api_key
#                 - AZURE_OPENAI_API_VERSION (optional)
#         """
#         if not isinstance(azure_openai_secret, dict):
#             raise TypeError("azure_openai_secret must be a dictionary")
        
#         self.endpoint = azure_openai_secret.get("AZURE_OPENAI_ENDPOINT", "")
#         self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT", "")
#         self.api_version = azure_openai_secret.get(
#             "AZURE_OPENAI_API_VERSION", 
#             self.DEFAULT_API_VERSION
#         )
#         self.api_key = azure_openai_secret.get("AZURE_OPENAI_API_KEY", "")
        
#         # Validate required fields
#         if not all([self.endpoint, self.deployment_name, self.api_key]):
#             raise ValueError(
#                 "Missing required Azure OpenAI configuration: "
#                 "AZURE_OPENAI_ENDPOINT, deployment_name, and api_key are required"
#             )
    
#     def invoke_model_with_backoff(
#         self,
#         prompt: str,
#         Task="Not specified",
#         system_content: str = "You are a helpful assistant.",
#         max_retries: int = 10,
#         base_delay: int = 2,
#         want_json: bool = True
#     ) -> Union[str, Dict[Any, Any]]:
#         """Invoke model with exponential backoff for rate limiting.
        
#         Args:
#             prompt: User prompt
#             system_content: System message for the model
#             max_retries: Maximum number of retry attempts
#             base_delay: Base delay for exponential backoff
#             want_json: Whether to parse response as JSON
            
#         Returns:
#             Model response as string or parsed JSON dict
#         """
#         for attempt in range(max_retries):
#             print("Task to Ai is :- ",Task)
#             try:
#                 return self.invoke_model(system_content, prompt, want_json)
            
#             except requests.exceptions.HTTPError as e:
#                 # Check for rate limiting (429) or server errors (5xx)
#                 if e.response.status_code in [500, 502, 503, 504]:
#                     if attempt < max_retries - 1:
#                         delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
#                         print(
#                             f"Rate limit or server error (status {e.response.status_code}). "
#                             f"Retrying in {delay:.2f} seconds..."
#                         )
#                         time.sleep(delay)
#                     else:
#                         raise
#                 else:
#                     # Don't retry for other HTTP errors (auth, not found, etc.)
#                     raise
            
#             except requests.exceptions.RequestException as e:
#                 # Network errors - retry
#                 if attempt < max_retries - 1:
#                     delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
#                     print(f"Network error: {e}. Retrying in {delay:.2f} seconds...")
#                     time.sleep(delay)
#                 else:
#                     raise
    
#     def invoke_model(
#         self,
#         system_content: str,
#         prompt: str,
#         want_json: bool = True,
#         max_json_retries: int = 3,
#         temperature: float = DEFAULT_TEMPERATURE
#     ) -> Union[str, Dict[Any, Any]]:
#         """Invoke Azure OpenAI model.
        
#         Args:
#             system_content: System message
#             prompt: User prompt
#             want_json: Whether to parse response as JSON
#             max_json_retries: Max retries for JSON parsing
#             temperature: Model temperature
            
#         Returns:
#             Model response as string or parsed JSON dict
#         """
#         url = (
#             f"{self.endpoint}/openai/deployments/{self.deployment_name}/"
#             f"chat/completions?api-version={self.api_version}"
#         )
        
#         headers = {
#             "Content-Type": "application/json",
#             "api-key": self.api_key
#         }
        
#         data = {
#             "messages": [
#                 {"role": "system", "content": system_content},
#                 {"role": "user", "content": prompt}
#             ],
#             "temperature": temperature
#         }
        
#         if not want_json:
#             response = requests.post(
#                 url=url, 
#                 headers=headers, 
#                 json=data,
#                 timeout=self.REQUEST_TIMEOUT
#             )
#             response.raise_for_status()
#             result = response.json()
#             return result["choices"][0]["message"]["content"]
        
#         # JSON mode with retries
#         for attempt in range(max_json_retries):
#             try:
#                 response = requests.post(
#                     url=url, 
#                     headers=headers, 
#                     json=data,
#                     timeout=self.REQUEST_TIMEOUT
#                 )
#                 response.raise_for_status()
#                 result = response.json()
#                 try :
#                     tokens = result["usage"]
#                     output_tokens= tokens["completion_tokens"]
#                     input_tokens= tokens["prompt_tokens"]
#                     total = tokens["total_tokens"]
#                     print(" Token usage details input_tokens :-",input_tokens,"output_tokens",output_tokens,"total",total)

#                 except Exception as e :
#                     print("errore occured input output token not found :--",e)
                
#                 # Extract and clean content
#                 content = result["choices"][0]["message"]["content"]
#                 content = content.strip()
                
#                 # Remove markdown code blocks
#                 if content.startswith("```"):
#                     content = content.removeprefix("```json").removeprefix("```")
#                     content = content.removesuffix("```").strip()
                
#                 return json.loads(content)
            
#             except json.JSONDecodeError as e:
#                 remaining = max_json_retries - attempt - 1
#                 print(f"JSON parse failed. Retries left: {remaining}")
#                 print(f"Error: {e}")
                
#                 if remaining == 0:
#                     print(f"Raw content: {content}")
#                     raise ValueError(f"Failed to parse JSON after {max_json_retries} attempts") from e
                
#                 time.sleep(2)  # Brief delay before retry
            
#             except (KeyError, IndexError) as e:
#                 print(f"Unexpected response structure: {result}")
#                 raise ValueError("Invalid response format from Azure OpenAI") from e
       

# OpenAIClient = AzureOpenAIClient(azure_openai_secret)    
# prompt   = "tell me about taj mahal in json style"
# output = OpenAIClient.invoke_model_with_backoff(prompt,Task= "get cvExtractparsed step1 " )


# print(output)


import boto3
from datetime import datetime

def download_lambda_logs(function_name, output_file='lambda_logs.txt', max_events=200):
    """Download last N CloudWatch logs for a Lambda function."""
    logs_client = boto3.client('logs', region_name='ap-south-1')
    log_group_name = f'/aws/lambda/{function_name}'
    
    try:
        # Get log streams sorted by last event time
        streams_response = logs_client.describe_log_streams(
            logGroupName=log_group_name,
            orderBy='LastEventTime',
            descending=True,
            limit=5
        )
        
        all_events = []
        
        # Fetch events from recent streams
        for stream in streams_response['logStreams']:
            stream_name = stream['logStreamName']
            
            events_response = logs_client.get_log_events(
                logGroupName=log_group_name,
                logStreamName=stream_name,
                limit=max_events,
                startFromHead=False
            )
            
            all_events.extend(events_response['events'])
            
            if len(all_events) >= max_events:
                break
        
        # Sort by timestamp and take last N
        all_events.sort(key=lambda x: x['timestamp'])
        recent_events = all_events[-max_events:]
        
        # Write to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"Lambda Function: {function_name}\n")
            f.write(f"Log Group: {log_group_name}\n")
            f.write(f"Downloaded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Events: {len(recent_events)}\n")
            f.write("="*80 + "\n\n")
            
            for event in recent_events:
                timestamp = datetime.fromtimestamp(event['timestamp']/1000).strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"[{timestamp}] {event['message']}\n")
        
        print(f"Downloaded {len(recent_events)} log events to {output_file}")
        
    except Exception as e:
        print(f"Error downloading logs: {e}")

# Usage
download_lambda_logs('worko-bulk-jd-resume-matching-dev', 'lambda_logs.txt', 200)

import json
import boto3
import os
import base64
import fitz
from io import BytesIO
from urllib.parse import unquote_plus
from botocore.exceptions import ClientError

s3 = boto3.client('s3')
sqs = boto3.client('sqs')
bedrock_runtime = boto3.client('bedrock-runtime', region_name='ap-south-1')

def extract_text_from_pdf(pdf_data):
    text = ""
    pdf_document = fitz.open(stream=pdf_data, filetype="pdf")
    for page in pdf_document:
        text += page.get_text()
    return text

def extract_images_from_pdf(pdf_bytes):
    images_base64 = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        pix = page.get_pixmap(dpi=150)
        image_bytes = pix.tobytes("png")
        img_str = base64.b64encode(image_bytes).decode("utf-8")
        images_base64.append(img_str)
    return images_base64

def invoke_claude_with_image(base64_images):
    messages = [{"role": "user", "content": []}]
    for image_str in base64_images:
        messages[0]["content"].append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_str}})
    messages[0]["content"].append({"type": "text", "text": 'Extract all text from resume image'})
    body = json.dumps({"messages": messages, "anthropic_version": "bedrock-2023-05-31", "max_tokens": 4096})
    response = bedrock_runtime.invoke_model(body=body, modelId="anthropic.claude-3-haiku-20240307-v1:0", contentType="application/json", accept="application/json")
    response_body = json.loads(response["body"].read())
    return response_body.get("content", [{}])[0].get("text", "")

def get_text_from_cv(bucket_name, key):
    try:
        response = s3.get_object(Bucket=bucket_name, Key=key)
        data = response['Body'].read()
        processed_text = extract_text_from_pdf(data)
        if not processed_text:
            base64_images = extract_images_from_pdf(data)
            processed_text = invoke_claude_with_image(base64_images)
        return processed_text
    except ClientError as e:
        print(f"S3 Error: {e}")
        return None

def get_queue_url(queue_name):
    response = sqs.get_queue_url(QueueName=queue_name)
    return response['QueueUrl']

def send_to_sqs(queue_name, body, delay_seconds=0):
    queue_url = get_queue_url(queue_name)
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(body), DelaySeconds=delay_seconds)

def lambda_handler(event, context):
    print(f"Step 1: Extract text from CV")
    print(f"Event: {json.dumps(event)}")
    env = os.environ.get("ENVIRONMENT", "dev")
    retry_queue = f"state-machine-retry-{env}"
    step2_queue = f"worko-cand-profile-parser-step2-queue-{env}"
    
    try:
        if 'Records' in event and event['Records'][0].get('eventSource') == 'aws:sqs':
            body = json.loads(event['Records'][0]['body'])
            bucket_name = body['bucket_name']
            object_key = body['object_key']
            metadata = body.get('metadata', {})
            retry_counter = body.get('retry_counter', 0)
        else:
            s3_event = event['Records'][0]['s3']
            bucket_name = s3_event['bucket']['name']
            object_key = unquote_plus(s3_event['object']['key'])
            metadata = s3.head_object(Bucket=bucket_name, Key=object_key).get('Metadata', {})
            retry_counter = 0
        
        if retry_counter >= 5:
            print(f"Max retries reached, moving to DLQ")
            return {'statusCode': 200, 'body': 'Max retries'}
        
        processed_text = get_text_from_cv(bucket_name, object_key)
        
        if processed_text:
            send_to_sqs(step2_queue, {'processed_text': processed_text, 'bucket_name': bucket_name, 'object_key': object_key, 'metadata': metadata, 'retry_counter': 0})
            return {'statusCode': 200, 'body': 'Step 1 completed'}
        else:
            raise Exception("Failed to extract text")
            
    except Exception as e:
        print(f"Error in Step 1: {e}")
        retry_counter += 1
        send_to_sqs(retry_queue, {'bucket_name': bucket_name, 'object_key': object_key, 'metadata': metadata, 'retry_counter': retry_counter, 'step': 1}, delay_seconds=90*retry_counter)
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}

import boto3 
def get_queue_url(queue_name):
    sqs = boto3.client('sqs')
    response = sqs.get_queue_url(QueueName=queue_name)
    return response['QueueUrl']

retry_queue_name = "worko-cand-profile-parser-retry-queue-dev"
print(get_queue_url(retry_queue_name))
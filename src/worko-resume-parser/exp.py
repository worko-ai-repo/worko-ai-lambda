
import boto3
import json
import botocore

# Initialize the S3 client
s3_client = boto3.client('s3')

# S3 bucket name and key (file path)
s3_bucket_name = 'worko-admin-cand-profile-prod'
key = 'bulk-cvs/01KGME1WQTBHM5ZSXRA4GY2H9M.pdf'
# bulk-cvs/01KGME1WQTBHM5ZSXRA4GY2H9M
# s3://worko-admin-cand-profile-prod/bulk-cvs/01KGME1WQTBHM5ZSXRA4GY2H9M.pdf
def get_cv(s3_bucket_name,key):
    try:

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
get_cv(s3_bucket_name,key)
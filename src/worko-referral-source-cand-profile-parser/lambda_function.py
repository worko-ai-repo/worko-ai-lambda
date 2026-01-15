import boto3
from email import policy
from email.parser import BytesParser


def retrieve_email_from_s3(bucket_name: str, object_key: str):
    try:
        s3 = boto3.client("s3")

        # Get object from S3
        response = s3.get_object(
            Bucket=bucket_name,
            Key=object_key
        )

        # Read raw email bytes
        raw_email_bytes = response["Body"].read()
        if not raw_email_bytes:
            raise ValueError("No email content found")

        # Parse email (equivalent to simpleParser)
        parsed_email = BytesParser(policy=policy.default).parsebytes(raw_email_bytes)

        return parsed_email

    except Exception as e:
        print("Error retrieving email from S3", {
            "bucketName": bucket_name,
            "objectKey": object_key,
            "error": str(e)
        })
        raise
def get_attachments(email_obj):
    attachments = []

    for part in email_obj.walk():
        content_disposition = part.get_content_disposition()

        if content_disposition == "attachment":
            filename = part.get_filename()
            payload = part.get_payload(decode=True)

            attachments.append({
                "filename": filename,
                "content_type": part.get_content_type(),
                "size": len(payload) if payload else 0,
                "data": payload
            })

    return attachments


bucket_name = "worko-referral-email-dev"
object_key = "referral-sourcetype/0h47scor2sup779lmu5u6if6pkm8ncoio6808eg1"

email_obj = retrieve_email_from_s3(bucket_name, object_key)
attachments = get_attachments(email_obj)
print(attachments)
# print("Subject:", email_obj["subject"])
# print("From:", email_obj["from"])
# print("To:", email_obj["to"])
# print("Date:", email_obj["date"])

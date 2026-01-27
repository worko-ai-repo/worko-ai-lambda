










# from email import policy
# from email.parser import BytesParser
# import boto3

# def get_attachments(email_obj):
#     attachments = []
#     for part in email_obj.walk():
#         content_disposition = part.get_content_disposition()
#         if content_disposition == "attachment":
#             filename = part.get_filename()
#             payload = part.get_payload(decode=True)
#             attachments.append({
#                 "filename": filename,
#                 "content_type": part.get_content_type(),
#                 "data": payload,
#             })
#     return attachments

# msg_id = ""
# env = "dev"
# s3_client = boto3.client('s3')
# bucket_name = "worko-referral-email-"+env
# object_key=f"referral-sourcetype/{msg_id}"

# response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
# raw_email_bytes = response['Body'].read()

# email_obj = BytesParser(policy=policy.default).parsebytes(raw_email_bytes)
# attachments = get_attachments(email_obj)

# pdf_attachment = None
# for att in attachments:
#     filename = (att.get("filename") or "").lower()
#     if att.get("content_type") == "application/pdf" or filename.endswith(".pdf"):
#         pdf_attachment = att
#         break

# if not pdf_attachment:
#     pdf_attachment = attachments[0]

# pdf_bytes = pdf_attachment.get("data")
# company_id = ""
# file_id = ""
# s3_key = f"companies/{company_id}/referral-source-cvs/{file_id}.pdf"
# cv_bucket = "CV_UPLOAD_BUCKET"
# s3_client.put_object(Bucket=cv_bucket, Key=s3_key, Body=pdf_bytes)

















# # def get_email_id_from_subject(subject):
# #     email = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', subject)
# #     return email.group(0) if email else None

# # email_file_path = r"C:\Users\Administrator\Downloads\pv0a37qu6mif90h8s7c98ln5r4s9vhdm47848ug1"

# # with open(email_file_path, 'rb') as f:
# #     raw_email_bytes = f.read()

# # email_obj = BytesParser(policy=policy.default).parsebytes(raw_email_bytes)
# # subject = str(email_obj.get("subject"))

# # print("Subject:", subject)
# # email_id = get_email_id_from_subject(subject)
# # print("Extracted Email:", email_id)
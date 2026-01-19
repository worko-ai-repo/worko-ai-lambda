from email import policy
from email.parser import BytesParser
import re

def get_email_id_from_subject(subject):
    email = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', subject)
    return email.group(0) if email else None

email_file_path = r"C:\Users\Administrator\Downloads\pv0a37qu6mif90h8s7c98ln5r4s9vhdm47848ug1"

with open(email_file_path, 'rb') as f:
    raw_email_bytes = f.read()

email_obj = BytesParser(policy=policy.default).parsebytes(raw_email_bytes)
subject = str(email_obj.get("subject"))

print("Subject:", subject)
email_id = get_email_id_from_subject(subject)
print("Extracted Email:", email_id)
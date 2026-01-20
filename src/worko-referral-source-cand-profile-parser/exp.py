from email import policy
from email.parser import BytesParser
import re





event = {
  "Records": [
    {
      "eventSource": "aws:ses",
      "eventVersion": "1.0",
      "ses": {
        "mail": {
          "timestamp": "2026-01-19T12:43:07.914Z",
          "source": "forwarding-noreply@google.com",
          "messageId": "vb2gbk6kdmptv9m9n25g8u7df2cjspvb61vunl81",
          "destination": [
            "01JWAQF1G96E0SE9XHXSFGHNWW@referral.worko.work"
          ],
          "headersTruncated": False,
          "headers": [
            {
              "name": "Return-Path",
              "value": "<forwarding-noreply@google.com>"
            },
            {
              "name": "Received",
              "value": "from mail-yx1-f53.google.com (mail-yx1-f53.google.com [74.125.224.53]) by inbound-smtp.ap-south-1.amazonaws.com with SMTP id vb2gbk6kdmptv9m9n25g8u7df2cjspvb61vunl81 for 01JWAQF1G96E0SE9XHXSFGHNWW@referral.worko.work; Mon, 19 Jan 2026 12:43:07 +0000 (UTC)"
            },
            {
              "name": "X-SES-Spam-Verdict",
              "value": "PASS"
            },
            {
              "name": "X-SES-Virus-Verdict",
              "value": "PASS"
            },
            {
              "name": "Received-SPF",
              "value": "pass (spfCheck: domain of google.com designates 74.125.224.53 as permitted sender)"
            },
            {
              "name": "Authentication-Results",
              "value": "amazonses.com; spf=pass; dkim=pass; dmarc=pass"
            },
            {
              "name": "X-SES-RECEIPT",
              "value": "AEFBQUFBQUFBQUFGY05JR25DR1VDeDRrcS9iMlJRZUxtaHVUeHdlT2hITDcxUWhIMXVyYytBZnJ2V3gxSzNiaWxxUEdnWnV1eWtGM1NhV2NKRkpEWTM5SGRMc3hUNnJkWEtQR3V6WjFzdXVJS3VGeEtnNWhiWDNjem9QK3BpblR2UTBNUXd1RThTZk96QVIrYUY5ZkF4c1dnelZMclU1U3MwSkdnQ1Y0YjY0Q0M2Mk56cnd6VEhCdDdZMTZvWU5tMDNrVlo5cjNvMXAwS0ZORExvWTVyQkxUdTFCb3UrMDFkRmwvbndoaGZhNkhMTU1JT2xjWkR2MWREaER3dmNLcVc5RlBOOUJ3SFFwaVp4cUFkclVpNXRQTmVHOXBUQ2YrWUNXNEZpSlJPRTd6STFOVnVVOTdKWGc9PQ=="
            },
            {
              "name": "MIME-Version",
              "value": "1.0"
            },
            {
              "name": "Date",
              "value": "Mon, 19 Jan 2026 18:13:04 +0530"
            },
            {
              "name": "Message-ID",
              "value": "<CAA6HCTj1K1w5V+jJrPiUv8Do6CcztHZ5Hsdq5_kO7uYT0munqg@mail.gmail.com>"
            },
            {
              "name": "Subject",
              "value": "(Gmail Forwarding confirmation – Receive mail from shaukt1998@gmail.com"
            },
            {
              "name": "From",
              "value": "Gmail Team <forwarding-noreply@google.com>"
            },
            {
              "name": "To",
              "value": "01JWAQF1G96E0SE9XHXSFGHNWW@referral.worko.work"
            },
            {
              "name": "Content-Type",
              "value": "text/plain; charset=\"UTF-8\""
            }
          ],
          "commonHeaders": {
            "returnPath": "forwarding-noreply@google.com",
            "from": [
              "Gmail Team <forwarding-noreply@google.com>"
            ],
            "date": "Mon, 19 Jan 2026 18:13:04 +0530",
            "to": [
              "01JWAQF1G96E0SE9XHXSFGHNWW@referral.worko.work"
            ],
            "messageId": "<CAA6HCTj1K1w5V+jJrPiUv8Do6CcztHZ5Hsdq5_kO7uYT0munqg@mail.gmail.com>",
            "subject": "(Gmail Forwarding confirmation – Receive mail from shaukt1998@gmail.com"
          }
        },
        "receipt": {
          "timestamp": "2026-01-19T12:43:07.914Z",
          "processingTimeMillis": 960,
          "recipients": [
            "01JWAQF1G96E0SE9XHXSFGHNWW@referral.worko.work"
          ],
          "spamVerdict": {
            "status": "PASS"
          },
          "virusVerdict": {
            "status": "PASS"
          },
          "spfVerdict": {
            "status": "PASS"
          },
          "dkimVerdict": {
            "status": "PASS"
          },
          "dmarcVerdict": {
            "status": "PASS"
          },
          "action": {
            "type": "Lambda",
            "functionArn": "arn:aws:lambda:ap-south-1:211125353899:function:worko-referral-source-cand-profile-parser-dev",
            "invocationType": "Event"
          }
        }
      }
    }
  ]
}
msg_id = event.get("Records")[0].get("ses").get("mail").get("messageId")
print(msg_id)





















# def get_email_id_from_subject(subject):
#     email = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', subject)
#     return email.group(0) if email else None

# email_file_path = r"C:\Users\Administrator\Downloads\pv0a37qu6mif90h8s7c98ln5r4s9vhdm47848ug1"

# with open(email_file_path, 'rb') as f:
#     raw_email_bytes = f.read()

# email_obj = BytesParser(policy=policy.default).parsebytes(raw_email_bytes)
# subject = str(email_obj.get("subject"))

# print("Subject:", subject)
# email_id = get_email_id_from_subject(subject)
# print("Extracted Email:", email_id)
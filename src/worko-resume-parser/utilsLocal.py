
import json
import boto3
import fitz
import os
import re
from decimal import Decimal
from boto3.dynamodb.types import TypeDeserializer
from datetime import datetime
import botocore
from docx import Document
from io import BytesIO
import time
import requests
import io                    
import base64    
from typing import Tuple, Dict, Any, Optional, Union
from botocore.exceptions import ClientError
import uuid
import random
sqs = boto3.client('sqs')
# iac deploy 13


# Initialize the AWS service clients
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')


def process_parsed_cv_json_resume_parser(cv_obj):
    try:
        if not isinstance(cv_obj, dict):
            return cv_obj
        
        # Helper function to clean array items
        def clean_array_items(arr):
            if not isinstance(arr, list):
                return arr
            return [
                {k: v for k, v in item.items() if v not in (None, "", [], {}, "null", "NULL")}
                for item in arr
                if isinstance(item, dict)
            ]
        
        # Process all arrays that contain objects
        array_fields = ["education", "multipleCandidateExperience", "coreSkills", "technicalSkills", "softSkills"]
        cleaned_arrays = {}
        
        for field in array_fields:
            if field in cv_obj:
                cleaned_array = clean_array_items(cv_obj[field])
                if cleaned_array:  # Only add back if not empty
                    cleaned_arrays[field] = cleaned_array
        
        # Remove null/empty values from top level
        cv_obj = {k: v for k, v in cv_obj.items() if v not in (None, "", [], {}, "null", "NULL")}
        
        # Add back all cleaned arrays
        cv_obj.update(cleaned_arrays)
        
        try:
            cv_obj["name"] = cv_obj["name"].lower()
            cv_obj["email"] = cv_obj["email"].lower()
        except Exception as e:
            print("Error in lowercasing name and email",e)

        
        return cv_obj
    except Exception as e:
        print(f"Error processing parsed CV JSON: {e}")
        return cv_obj
    


# def process_parsed_cv_json(cv_obj):
#     try:
#         if not isinstance(cv_obj, dict):
#             return cv_obj
        
#         # Process education array separately
#         education = cv_obj.get("education", [])
#         if isinstance(education, list):
#             education = [
#                 {k: v for k, v in item.items() if v not in (None, "", [], {}, "null", "NULL")}
#                 for item in education
#                 if isinstance(item, dict)
#             ]
        
#         # Remove null/empty values from top level
#         cv_obj = {k: v for k, v in cv_obj.items() if v not in (None, "", [], {}, "null", "NULL")}
        
#         # Add back cleaned education if it has items
#         if education:
#             cv_obj["education"] = education
#         try:
#             cv_obj["name"] = cv_obj["name"].lower()
#             cv_obj["email"] = cv_obj["email"].lower()
#         except Exception as e:
#             print("Error in lowercasing name and email",e)

        
#         return cv_obj
#     except Exception as e:
#         print(f"Error processing parsed CV JSON: {e}")
#         return cv_obj
    

def reset_partition(partition_key_value):
    dynamodb = boto3.resource("dynamodb")
    table_name = "worko"
    table = dynamodb.Table(table_name)
    sort_key_prefix = "EDU#ID#"
    try:
        response = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(partition_key_value) & boto3.dynamodb.conditions.Key('SK').begins_with(sort_key_prefix))
        # Step 1: Query all items with the given partition key
        # response = table.query(
        #     KeyConditionExpression=boto3.dynamodb.conditions.Key("PK").eq(partition_key_value)
        # )

        items = response.get("Items", [])
        # Delete all items
        deleted_count = 0
        with table.batch_writer() as batch:
            for item in items:
                # Must provide both PK and SK for deletion
                batch.delete_item(
                    Key={
                        'PK': item['PK'],
                        'SK': item['SK']
                    }
                )
                deleted_count += 1
                print(f"Deleted item: PK={item['PK']}, SK={item['SK']}")
            print(f"Total items deleted: {deleted_count}")
            return deleted_count
    except Exception as e:
        print(e)

    




        
        # if not items:
        #     print(f"No items found for pk={partition_key_value}")
        #     return

        # # Step 2: Batch delete (max 25 items per batch)
        # with table.batch_writer() as batch:
        #     for item in items:
        #         batch.delete_item(
        #             Key={
        #                 "pk": item["pk"],
        #                 "sk": item["sk"]
        #             }
        #         )
        #         print(f"Deleted item with SK: {item['sk']}")

        # print(f"✅ Entire partition with pk={partition_key_value} deleted successfully.")
        return items

    except Exception as e:
        print(f"Error deleting partition: {e}")

def query_dynamodb_item_with_sk_prefix(table_name, partition_key_value, sort_key_prefix):
    table = dynamodb.Table(table_name)
    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(partition_key_value) &
                               boto3.dynamodb.conditions.Key('SK').begins_with(sort_key_prefix)
    )
    items = response.get('Items')
    if items:
        return items[0]
    return None

def extract_text_from_pdf(pdf_data):
    text = ""
    pdf_document = fitz.open(stream=pdf_data, filetype="pdf")
    for page in pdf_document:
        text += page.get_text()

    links = []
    for page_num, page in enumerate(pdf_document, start=1):
        for link in page.get_links():
            if "uri" in link:
                links.append(link["uri"])
    return text,links

def extract_text_from_docx(docx_bytes):
    text = ""
    document = Document(BytesIO(docx_bytes))
    for paragraph in document.paragraphs:
        text += paragraph.text + "\n"
    return text

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            else:
                return float(obj)
        return super(DecimalEncoder, self).default(obj)

def invoke_model_nova(prompt):
    body = json.dumps({
        "inferenceConfig": {
            "max_new_tokens": 4697, "temperature":0.1
        },
        "messages": [
            {
                "role": "user", 
                "content": [
                    {
                        "text": prompt  # Wrap the prompt in a text dictionary
                    }
                ]
            }
        ]
    })
    
    # modelId= "amazon.nova-pro-v1:0"
    modelId= "amazon.nova-lite-v1:0"
    # modelId= "amazon.nova-micro-v1:0"
    # modelId= "amazon.nova-canvas-v1:0"

    print("Model used-", modelId)

    response = bedrock_runtime.invoke_model(
        body=body,
        modelId=modelId,
        contentType='application/json',
        accept='application/json'
    )
    
    response_body = json.loads(response['body'].read())
    
    return response_body

def convert_floats_to_decimals(obj):
    """ Recursively convert float, int, and numeric strings in dict/list to Decimal for DynamoDB """
    if isinstance(obj, list):
        return [convert_floats_to_decimals(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, (float, int)):
        return Decimal(str(obj))  # Safe conversion
    elif isinstance(obj, str):
        # Try converting numeric strings to Decimal
        try:
            return Decimal(obj)
        except:
            return obj
    else:
        return obj

def update_otherSocialPlatForms_in_dynamodb(table_name, partition_key, otherSocialPlatForms):
    table = dynamodb.Table(table_name)
    sort_key = "SOCIAL#"
    current_timestamp = int(datetime.now().timestamp() * 1000)
    social_fields = ["linkedin", "github", "twitter"]

    update_expressions = []
    expression_values = {}

    # Always ensure linkedin, github, twitter exist at the top level
    for field in social_fields:
        value = otherSocialPlatForms.get(field, "")

        # Normalize to list of strings
        if isinstance(value, str):
            value = [value] if value.strip() else [""]
        elif isinstance(value, list):
            # Clean list, default to [""] if empty
            value = [str(v) for v in value if str(v).strip()] or [""]
        else:
            value = [str(value)]

        update_expressions.append(f"{field} = :{field}")
        expression_values[f":{field}"] = value

    # Keep only extra fields in otherSocialPlatForms
    extra_socials = {
        k: v for k, v in otherSocialPlatForms.items() if k not in social_fields
    }

    # make createdAt only if new partiton is created otherwise do not update it
    response1 = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(partition_key) 
            & boto3.dynamodb.conditions.Key('SK').eq(sort_key))
    skillS_Present_orNot = response1["Items"]==[]
    if skillS_Present_orNot:
        print("craeting createdAt in preff#" )
        update_expressions.append("createdAt = :createdAt")
        expression_values[':createdAt'] = current_timestamp

    update_expressions.append("otherSocialPlatForms = :otherSocialPlatForms")
    expression_values[":otherSocialPlatForms"] = extra_socials

    update_expressions.append("updatedAt = :updatedAt")
    expression_values[":updatedAt"] = current_timestamp
    update_expression = "SET " + ", ".join(update_expressions)

    response = table.update_item(
        Key={
            'PK': partition_key,
            'SK': sort_key
        },
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_values,
        ReturnValues="UPDATED_NEW"
    )

    return response
    
def reset_otherSocialPlatForms_in_dynamodb(table_name, partition_key, sort_key="SOCIAL#"):
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    try:
        # Check if the item exists
        response = table.get_item(
            Key={
                'PK': partition_key,
                'SK': sort_key
            }
        )

        if 'Item' not in response:
            # No item found for this partition
            return {"message": "Item not found, nothing updated"}
        else:
            social_fields = ["linkedin", "github", "twitter", "otherSocialPlatForms"]

            update_expressions = []
            expression_values = {}

            for field in social_fields:
                if field == "otherSocialPlatForms":
                    update_expressions.append(f"{field} = :{field}")
                    expression_values[f":{field}"] = []
                else:
                    update_expressions.append(f"{field} = :{field}")
                    expression_values[f":{field}"] = ""

            update_expression = "SET " + ", ".join(update_expressions)

            update_response = table.update_item(
                Key={
                    'PK': partition_key,
                    'SK': sort_key
                },
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
                ReturnValues="UPDATED_NEW"
            )
            return update_response
    except Exception as e:
        print("Error:", e)
        return {"error": str(e)}

def update_cv_extract_in_dynamodb(table_name, partition_key, sort_key, cv_extract):
    table = dynamodb.Table(table_name)

    # Get current date and time
    current_datetime = datetime.now().isoformat()

    response = table.update_item(
        Key={
            'PK': partition_key,
            'SK': sort_key
        },
        UpdateExpression="SET cvExtract = :cvExtract, cvExtractDate = :cvExtractDate",
        
        ExpressionAttributeValues={
            ':cvExtract': cv_extract,
            ':cvExtractDate': current_datetime
        },
        ReturnValues="UPDATED_NEW"
    )
    return response

def update_frontend_auto_populations_in_dynamodb(table_name, partition_key, sort_key, frontend_auto_populations):
    multipleCandidateExperience = frontend_auto_populations.get("multipleCandidateExperience", None)
    about = frontend_auto_populations.get("about", None)
    responsibilities = frontend_auto_populations.get("responsibilities", [])

    # Clean responsibilities endDate if "present"
    for k in responsibilities:
        if k.get("date", {}).get("endDate", "").lower() == "present":
            k["date"]["endDate"] = ""
    for k in multipleCandidateExperience:
        if k.get("endDate", "").lower() == "present":
            k["endDate"] = ""
    
    for i in multipleCandidateExperience:
        try:
            i["YOE"] = float(i["YOE"])

        except Exception as e:
            i["YOE"]=1
        if float(i["YOE"])<0.5:
            i["YOE"]=0.5


    
    # Convert floats to Decimal before sending to DynamoDB
    multipleCandidateExperience = convert_floats_to_decimals(multipleCandidateExperience)

    about = convert_floats_to_decimals(about)
    responsibilities = convert_floats_to_decimals(responsibilities)

    table = dynamodb.Table(table_name)

    # Get current date and time
    current_datetime = datetime.now().isoformat()


    response = table.update_item(
    Key={
        'PK': partition_key,
        'SK': sort_key
    },
    UpdateExpression="""
        SET multipleCandidateExperience = :multipleCandidateExperience,
            multipleCandidateExperiencedDate = :multipleCandidateExperiencedDate,
            about = :about,
            responsibilities = :responsibilities
    """,
    ExpressionAttributeValues={
        ':multipleCandidateExperience': multipleCandidateExperience,
        ':multipleCandidateExperiencedDate': current_datetime,
        ':about': about,
        ':responsibilities': responsibilities
    },
    ReturnValues="UPDATED_NEW"
    )
    return response

def update_isCvExtracted_in_dynamodb(table_name, partition_key, sort_key, isCvExtracted):

    table = dynamodb.Table(table_name)

    # Get current date and time
    current_datetime = datetime.now().isoformat()


    response = table.update_item(
    Key={
        'PK': partition_key,
        'SK': sort_key
    },
    UpdateExpression="""
        SET isCvExtracted = :isCvExtracted
    """,
    ExpressionAttributeValues={
        ':isCvExtracted': isCvExtracted
    },
    ReturnValues="UPDATED_NEW"
    )
    return response

def update_cv_extract_parsed_in_dynamodb(table_name, partition_key, sort_key, cv_extract_parsed):
    for i in cv_extract_parsed['multipleCandidateExperience']:
        i["YOE"]=Decimal(str(i["YOE"]))
        if i["YOE"]<0.5:
            i["YOE"]=0.5
        
    cv_extract_parsed = convert_floats_to_decimals(cv_extract_parsed)
    table = dynamodb.Table(table_name)

    # Get current date and time
    current_datetime = datetime.now().isoformat()

    response = table.update_item(
        Key={
            'PK': partition_key,
            'SK': sort_key
        },
        UpdateExpression="SET cvExtractParsed = :cvExtractParsed, cvExtractParsedDate = :cvExtractParsedDate",
        
        ExpressionAttributeValues={
            ':cvExtractParsed': cv_extract_parsed,
            ':cvExtractParsedDate': current_datetime
        },
        ReturnValues="UPDATED_NEW"
    )
    return response

def update_yoe_in_dynamodb(table_name, partition_key, sort_key_prefix, yoe):
    
    table = dynamodb.Table(table_name)
    
    try:
        # Query to find items that match the partition key and sort key prefix
        response = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ':pk': partition_key,
                ':sk_prefix': sort_key_prefix
            }
        )
        
        # If no items found, return error
        if 'Items' not in response or len(response['Items']) == 0:
            return {
                "error": f"No records found with PK={partition_key} and SK beginning with {sort_key_prefix}. No update performed."
            }
        
        # Extract the first matching item's complete sort key
        complete_sort_key = response['Items'][0]['SK']
        
        # If yoe is a list with a single value, extract the value first
        if isinstance(yoe, list) and len(yoe) == 1:
            yoe = yoe[0]
        
        # Convert YOE to Decimal if it's a float or int (after extracting from list)
        if isinstance(yoe, (float, int)):
            yoe = Decimal(str(yoe))
        
        # Create update expression
        update_expression = "SET YOE = :yoe, updatedAt = :updatedAt"
        
        # Set the expression attribute values
        expression_attribute_values = {
            ':yoe': yoe,  # This will be a single value, not a list
            ':updatedAt': int(datetime.now().timestamp() * 1000)
        }
        
        # Perform the update using the complete sort key
        update_response = table.update_item(
            Key={
                'PK': partition_key,
                'SK': complete_sort_key
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW"
        )
        
        return update_response
        
    except Exception as e:
        print(f"Error updating YOE: {str(e)}")
        return {"error": str(e)}

def update_skills_in_dynamodb(table_name, partition_key, sort_key, core_skills, technical_skills, soft_skills):
    table = dynamodb.Table(table_name)
    
    # Helper function to convert floats to Decimal
    def convert_floats_to_decimal(obj):
        if isinstance(obj, list):
            return [convert_floats_to_decimal(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, float):
            return Decimal(str(obj))
        else:
            return obj
    
    try:
        # Convert float values to Decimal before using with DynamoDB
        core_skills = convert_floats_to_decimal(core_skills)
        technical_skills = convert_floats_to_decimal(technical_skills)
        soft_skills = convert_floats_to_decimal(soft_skills)
        
        # Prepare update expression and attribute values
        update_parts = []
        expression_attribute_values = {}
        
        response1 = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(partition_key) & boto3.dynamodb.conditions.Key('SK').begins_with(sort_key))
        skillS_Present_orNot = response1["Items"]==[]
        if skillS_Present_orNot:
            update_parts.append("createdAt = :createdAt")
            expression_attribute_values[':createdAt'] = int(datetime.now().timestamp() * 1000)
        
        # Always update coreSkills
        update_parts.append("coreSkills = :coreSkills")
        expression_attribute_values[':coreSkills'] = core_skills

        # Always update technicalskills
        update_parts.append("technicalSkills = :technicalSkills")
        expression_attribute_values[':technicalSkills'] = technical_skills

        # Always update softSkills
        update_parts.append("softSkills = :softSkills")
        expression_attribute_values[':softSkills'] = soft_skills
        
        # Update the timestamp
        update_parts.append("updatedAt = :updatedAt")
        expression_attribute_values[':updatedAt'] = int(datetime.now().timestamp() * 1000)



    
        # Combine all update parts into a single SET clause
        update_expression = "SET " + ", ".join(update_parts)
        
        # Perform the update
        response = table.update_item(
            Key={
                'PK': partition_key,
                'SK': sort_key
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW"
        )
        
        return response
    
    except Exception as e:
        print(f"Error updating skills: {str(e)}")
        return {"error": str(e)}

def update_Education_in_dynamo(table_name, partition_key, education):
    sort_key = str(uuid.uuid4())
    sort_key = 'EDU#ID#'+ sort_key
    print(f"sk:{sort_key} pk: {partition_key} update edu called")
    table = dynamodb.Table(table_name)
    collage = education["collage"]
    degree = education["degree"]
    try:
        update_parts = []
        expression_attribute_values = {}
        passingYear = int(education.get("passingYear", 0))
        # Always update passingYear if its given 
        update_parts.append("passingYear = :passingYear")
        expression_attribute_values[':passingYear'] = passingYear
    except ValueError:
        print(f"Invalid passingYear value: {education.get('passingYear')}")
        passingYear = 2012
    try:
        # Prepare update expression and attribute values
        # Always update collage
        update_parts.append("collage = :collage")
        expression_attribute_values[':collage'] = collage

        # Always update degree
        update_parts.append("degree = :degree")
        expression_attribute_values[':degree'] = degree

        # Always update createdAt
        update_parts.append("createdAt = :createdAt")
        expression_attribute_values[':createdAt'] = int(datetime.now().timestamp() * 1000)
        # Always update updatedAt
        update_parts.append("updatedAt = :updatedAt")
        expression_attribute_values[':updatedAt'] =  int(datetime.now().timestamp() * 1000)

        # Combine all update parts into a single SET clause
        update_expression = "SET " + ", ".join(update_parts)
        
        # Perform the update
        response = table.update_item(
            Key={
                'PK': partition_key,
                'SK': sort_key
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW"
        )
        return response
    except Exception as e:
        print(f"Error updating skills: {str(e)}")
        return {"error": str(e)}

def update_pref_department_in_dynamo(table_name, partition_key, sort_key, userId,Prefered_departments):
    table = dynamodb.Table(table_name)
    email = partition_key.split('#')[2]
    userId = userId.split('#')[-1]
    # Helper function to convert floats to Decimal

    
    try:
        # Prepare update expression and attribute values
        update_parts = []
        expression_attribute_values = {}

        # make createdAt only if new partiton is created otherwise do not update it
        response1 = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(partition_key) 
            & boto3.dynamodb.conditions.Key('SK').eq(sort_key))
        skillS_Present_orNot = response1["Items"]==[]
        if skillS_Present_orNot:
            print("craeting createdAt in preff#" )
            update_parts.append("createdAt = :createdAt")
            expression_attribute_values[':createdAt'] = int(datetime.now().timestamp() * 1000)


        # Always update Prefered_departments
        update_parts.append("userPreferredDepartments = :userPreferredDepartments")
        expression_attribute_values[':userPreferredDepartments'] = Prefered_departments

        # Always update email
        update_parts.append("email = :email")
        expression_attribute_values[':email'] = email

        
        # Always update userId
        update_parts.append("createdByUserId = :createdByUserId")
        expression_attribute_values[':createdByUserId'] = userId

        # Update the timestamp
        update_parts.append("updatedAt = :updatedAt")
        expression_attribute_values[':updatedAt'] = int(datetime.now().timestamp() * 1000)

        # Combine all update parts into a single SET clause
        update_expression = "SET " + ", ".join(update_parts)
        
        # Perform the update
        response = table.update_item(
            Key={
                'PK': partition_key,
                'SK': sort_key
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW"
        )
        return response
    
    except Exception as e:
        print(f"Error updating skills: {str(e)}")
        return {"error": str(e)}

def update_pref_section_in_dynamo(table_name, partition_key, sort_key, Prefered_section):
    table = dynamodb.Table(table_name)
    email = partition_key.split('#')[2]
    # Helper function to convert floats to Decimal
    
    userPreferredRoles = Prefered_section["userPreferredRoles"]
    userPreferredIndustries = Prefered_section["userPreferredIndustries"]

    # check is empty string is then make it a empty array
    if userPreferredIndustries=="":
        userPreferredIndustries=[]
    if userPreferredRoles=="":
        userPreferredRoles=[]
    
    try:
        # Prepare update expression and attribute values
        update_parts = []
        expression_attribute_values = {}
        
        # Always update Prefered_departments
        update_parts.append("userPreferredRoles = :userPreferredRoles")
        expression_attribute_values[':userPreferredRoles'] = userPreferredRoles

        # Always update Prefered_departments
        update_parts.append("userPreferredIndustries = :userPreferredIndustries")
        expression_attribute_values[':userPreferredIndustries'] = userPreferredIndustries

        
        # Combine all update parts into a single SET clause
        update_expression = "SET " + ", ".join(update_parts)
        
        # Perform the update
        response = table.update_item(
            Key={
                'PK': partition_key,
                'SK': sort_key
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW"
        )
        
        return response
    
    except Exception as e:
        print(f"Error updating skills: {str(e)}")
        return {"error": str(e)}

def reset_pref_section_in_dynamo(table_name, partition_key, sort_key):
    table = dynamodb.Table(table_name)
    email = partition_key.split('#')[2]
    # Helper function to convert floats to Decimal
    userPreferredRoles = []
    userPreferredIndustries = []
    
    try:
            
        # First, check if the item exists
        response = table.get_item(
            Key={
                'PK': partition_key,
                'SK': sort_key
            }
        )

        if 'Item' not in response:
        # No item found for this partition
            return {"message": "Item not found, nothing updated"}
        else:
            # Prepare update expression and attribute values
            update_parts = []
            expression_attribute_values = {}
            
            # Always update Prefered_departments
            update_parts.append("userPreferredRoles = :userPreferredRoles")
            expression_attribute_values[':userPreferredRoles'] = userPreferredRoles

            # Always update Prefered_departments
            update_parts.append("userPreferredIndustries = :userPreferredIndustries")
            expression_attribute_values[':userPreferredIndustries'] = userPreferredIndustries

            
            # Combine all update parts into a single SET clause
            update_expression = "SET " + ", ".join(update_parts)
            
            # Perform the update
            response = table.update_item(
                Key={
                    'PK': partition_key,
                    'SK': sort_key
                },
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_attribute_values,
                ReturnValues="UPDATED_NEW"
            )
            
            return response
    
    except Exception as e:
        print(f"Error updating skills: {str(e)}")
        return {"error": str(e)}

def print_completion_text(completion_text):
    print("***********************************************************************")
    print(completion_text)
    print("#######################################################################")

def invoke_model_with_backoff(prompt, max_retries=5, base_delay=1):
    for attempt in range(max_retries):
        try:
            # return invoke_model(prompt)
            return invoke_model_nova(prompt)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < max_retries - 1:
                delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                print(f"Throttling occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                raise

def invoke_model_with_backoff_sonnet(prompt, max_retries=5, base_delay=1):
    for attempt in range(max_retries):
        try:
            # return invoke_model(prompt)
            return invoke_model_soonet(prompt)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < max_retries - 1:
                delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                print(f"Throttling occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                raise

def extract_data_nova(input_data):

    try:
        # Step 1: Convert input to dictionary if it's a string
        if isinstance(input_data, str):
            try:
                # Try standard JSON parsing first
                data = json.loads(input_data)
            except json.JSONDecodeError:
                # If that fails, try handling Python-style dict strings with single quotes
                try:
                    data = ast.literal_eval(input_data)
                except (SyntaxError, ValueError):
                    # Last attempt: replace single quotes with double quotes and try again
                    input_data = input_data.replace("'", '"')
                    data = json.loads(input_data)
        else:
            # Input is already a dictionary
            data = input_data
            
        # Step 2: Extract the text content from the standardized dictionary structure
        text_content = data['output']['message']['content'][0]['text']
        
        # Step 3: Return the extracted text
        return text_content
        
    except Exception as e:
        return f"Error extracting text: {str(e)}"

def extract_skill_data_nova(input_data):
    import json
    import ast
    import re

    try:
        # Step 1: Convert input to dictionary if it's a string
        if isinstance(input_data, str):
            try:
                # Try standard JSON parsing first
                data = json.loads(input_data)
            except json.JSONDecodeError:
                # If that fails, try handling Python-style dict strings with single quotes
                try:
                    data = ast.literal_eval(input_data)
                except (SyntaxError, ValueError):
                    # Last attempt: replace single quotes with double quotes and try again
                    input_data = input_data.replace("'", '"')
                    data = json.loads(input_data)
        else:
            # Input is already a dictionary
            data = input_data
            
        # Step 2: Extract the text content from the standardized dictionary structure
        text_content = data['output']['message']['content'][0]['text']
        
        # Step 3: Clean the text content (remove markdown code blocks if present)
        json_text = re.sub(r'```json\s*|\s*```', '', text_content)
        
        # Step 4: Parse the JSON
        skills_data = json.loads(json_text)
        
        # Step 5: Extract coreSkills and softSkills
        core_skills = skills_data['coreSkills']
        technical_skills = skills_data['technicalSkills']
        soft_skills = skills_data['softSkills']
        Prefered_departments = skills_data['Prefered_departments']
        yoe = skills_data['YOE']
        
        # Return the extracted JSON structures
        return core_skills, technical_skills,soft_skills,Prefered_departments, yoe
        
    except Exception as e:
        return None, f"Error extracting skills: {str(e)}"

def extract_skill_data_from_json(json_data):
    """Extract skill data from GPT model JSON response.
    
    Args:
        json_data: Dictionary containing skill data from GPT model
        
    Returns:
        Tuple of (core_skills, technical_skills, soft_skills, preferred_departments, yoe)
    """
    try:
        core_skills = json_data.get('coreSkills', [])
        technical_skills = json_data.get('technicalSkills', [])
        soft_skills = json_data.get('softSkills', [])
        preferred_departments = json_data.get('Prefered_departments', [])
        yoe = json_data.get('YOE', 0)
        
        return core_skills, technical_skills, soft_skills, preferred_departments, yoe
        
    except Exception as e:
        print(f"Error extracting skills from JSON: {str(e)}")
        return [], [], [], [], 0

def update_technical_skills_years(technical_skills):
    """Transform each skill's 'years' to a number."""
    result = []
    for skill in technical_skills:
        years_value = skill.get('years', 0)
        # Handle if years is already an int/float
        if isinstance(years_value, (int, float)):
            skill['years'] = years_value
        # Handle if years is a list
        elif isinstance(years_value, list):
            skill['years'] = years_value[0] if years_value else 0
        else:
            skill['years'] = 0
        result.append(skill)
    return result

def update_core_skills_years(core_skills):
    """Transform each skill's 'years' to a number."""
    result = []
    for skill in core_skills:
        years_value = skill.get('years', 0)
        # Handle if years is already an int/float
        if isinstance(years_value, (int, float)):
            skill['years'] = years_value
        # Handle if years is a list
        elif isinstance(years_value, list):
            skill['years'] = years_value[0] if years_value else 0
        else:
            skill['years'] = 0
        result.append(skill)
    return result

def clean_json_string(json_string):
    # Remove ```json from the beginning if present
    if json_string.startswith("```json"):
        json_string = json_string[7:]
    # Remove ``` from the beginning if present
    elif json_string.startswith("```"):
        json_string = json_string[3:]
    
    # Remove ``` from the end if present
    if json_string.endswith("```"):
        json_string = json_string[:-3]
    
    # Strip any extra whitespace
    json_string = json_string.strip()
    
    return json_string

def has_key_elements(resume_text, key_elements_dict, min_required_categories=2, min_total_elements=5):
    
    # Initialize tracking
    total_elements_found = 0
    found_elements = {category: [] for category in key_elements_dict.keys()}
    
    # Handle different input types
    if isinstance(resume_text, dict):
        resume_text_str = str(resume_text).lower()
    elif isinstance(resume_text, str):
        resume_text_str = resume_text.lower()
    else:
        resume_text_str = str(resume_text).lower()
    
    # Preprocessing: Replace spaced out text like "C O N T A C T" with "CONTACT"
    # Find patterns like "C O N T A C T" and convert to "CONTACT"
    spaced_words = re.findall(r'\b([A-Z](\s+[A-Z])+)\b', resume_text)
    for match in spaced_words:
        original = match[0]
        fixed = original.replace(" ", "")
        resume_text_str = resume_text_str.replace(original.lower(), fixed.lower())
    
    # Debug: Print the first 100 characters of the text
    print(f"Text preview: {resume_text_str[:100]}...")
    
    # Detect common personal info formats first
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    phone_pattern = r'\b(?:\+\d{1,3}[-\s]?)?\d{3,}[-\s.]?\d{3,}[-\s.]?\d{3,4}\b'
    
    # Check for email and phone directly - these are strong personal info indicators
    email_match = re.search(email_pattern, resume_text_str)
    phone_match = re.search(phone_pattern, resume_text_str)
    
    if email_match:
        found_elements["personal_info"].append("email")
        total_elements_found += 1
        print(f"Found element: email (category: personal_info) - {email_match.group()}")
    
    if phone_match:
        found_elements["personal_info"].append("phone")
        total_elements_found += 1
        print(f"Found element: phone (category: personal_info) - {phone_match.group()}")
    
    # Check each category for keyword-based elements
    for category, elements in key_elements_dict.items():
        for element in elements:
            # Skip email and phone for personal_info as we already handled them
            if category == "personal_info" and element in ["email", "phone"]:
                continue
            
            # Create patterns for accurate matching
            element_escaped = re.escape(element.lower())
            patterns = [
                f"\\b{element_escaped}\\b",                         # Word by itself
                f"\\b{element_escaped}:",                           # Word followed by colon
                f"\\b{element_escaped} :",                          # Word followed by space and colon
                f"\\b{element_escaped}\\s+section",                 # Word followed by "section"
                f"\\b{element_escaped}\\s*\\n",                     # Word at end of line
                f"^{element_escaped}\\s*$",                         # Word on its own line
                f"\\n{element_escaped}\\s*\\n",                     # Word between newlines
            ]
            
            # Add special patterns for specific phrases
            if element.lower() == "contact me":
                patterns.extend([
                    r"\bcontact me\b",
                    r"\bcontact me at\b"
                ])
            elif element.lower() == "personal details":
                patterns.append(r"\bpersonal details\b")
            elif element.lower() == "personal profile":
                patterns.append(r"\bpersonal profile\b")
            elif element.lower() == "professional experience":
                patterns.extend([
                    r"\bprofessional experience\b",
                    r"\bwork experience\b",
                    r"\bemployment history\b"
                ])
            elif element.lower() == "education":
                patterns.extend([
                    r"\beducation\b",
                    r"\bacademic background\b",
                    r"\bacademic qualification\b"
                ])
            
            # Check if any pattern matches
            element_found = False
            for pattern in patterns:
                if re.search(pattern, resume_text_str, re.MULTILINE | re.IGNORECASE):
                    if element not in found_elements[category]:
                        found_elements[category].append(element)
                        total_elements_found += 1
                        element_found = True
                        print(f"Found element: {element} (category: {category})")
                    break
            
            if element_found:
                continue  # Move to next element
    
    # Check if name is likely present (at the top, capitalized)
    # Look for standalone capitalized words that might be names
    potential_name_lines = re.findall(r'^([A-Z][a-z]+\s+[A-Z][a-z]+)', resume_text_str, re.MULTILINE)
    if potential_name_lines:
        if "name" not in found_elements["personal_info"]:
            found_elements["personal_info"].append("name")
            total_elements_found += 1
            print(f"Found element: name (category: personal_info) - {potential_name_lines[0]}")
    
    # Count categories that have any found elements
    categories_with_matches = sum(1 for elements in found_elements.values() if len(elements) > 0)
    
    print(f"Categories with matches: {categories_with_matches}/{len(key_elements_dict)}")
    print(f"Total elements found: {total_elements_found}")
    print(f"Found elements by category: {found_elements}")
    
    # Check if we meet both category and total element thresholds
    is_valid = (categories_with_matches >= min_required_categories and 
                total_elements_found >= min_total_elements)
    
    return is_valid, found_elements, total_elements_found

def check_if_resume(processed_text):

    if not processed_text:
        print("No text provided")
        return {"statusCode": 404, "body": "No text provided"}
    
    # Define categories with higher weights for critical resume sections
    resume_elements = {
        # Critical resume sections (highest weight)
        "core_sections": [
            'experience', 'work history', 'employment', 'professional experience',
            'education', 'academic background', 'qualification', 'qualifications',
            'work experience', 'career highlights'  # Added these common variants
        ],
        
        # Important but not critical sections
        "additional_sections": [
            'skills', 'technical skills', 'soft skills', 
            'certifications', 'certificates', 'accreditations',
            'projects', 'achievements', 'accomplishments',
            'publications', 'research', 'patents', 
            'core competencies', 'it skills'  # Added these common variants
        ],
        
        # Common resume sections
        "standard_sections": [
            'summary', 'profile', 'professional summary', 'career objective',
            'objective', 'references', 'languages', 'volunteer', 'leadership',
            'responsibilities', 'expertise', 'competencies',
            'personal profile', 'career highlights'  # Added these common variants
        ],
        
        # Personal information (must have some contact info)
        "personal_info": [
            'name', 'email', 'phone', 'contact', 'address', 
            'linkedin', 'github', 'portfolio', 'website',
            'personal details', 'contact me'  # Added these common variants
        ]
    }
    
    # Settings for validation
    min_required_categories = 2  # Need matches from at least 2 categories
    min_total_elements = 5       # Need at least 5 total elements across all categories
    
    # At least one from personal_info + one from core_sections = strong resume indicator
    is_valid, found_elements, total_found = has_key_elements(
        processed_text, 
        resume_elements,
        min_required_categories,
        min_total_elements
    )
    
    # Additional checks for higher confidence:
    # 1. Must have at least one personal info element
    # 2. Must have at least one core section
    has_personal_info = len(found_elements["personal_info"]) > 0
    has_core_section = len(found_elements["core_sections"]) > 0
    
    # More detailed validation logic with better messaging
    if is_valid:
        if has_personal_info and has_core_section:
            # High confidence - has both personal info and core sections
            confidence = "high" if total_found >= 8 else "medium"
            return {
                "statusCode": 200, 
                "body": "Valid resume found",
                "details": {
                    "elements_found": found_elements,
                    "confidence": confidence
                }
            }
        else:
            # Moderate confidence - missing either personal info or core sections
            missing_elements = []
            if not has_personal_info:
                missing_elements.append("personal information (contact details, email, phone)")
            if not has_core_section:
                missing_elements.append("core resume sections (experience, education)")
                
            return {
                "statusCode": 200,  # Changed to 200 since it's still likely a resume
                "body": f"Partial resume detected - missing {', '.join(missing_elements)}",
                "details": {
                    "elements_found": found_elements,
                    "missing_critical": {
                        "personal_info": not has_personal_info,
                        "core_sections": not has_core_section
                    },
                    "confidence": "low"
                }
            }
    else:
        # Not enough elements found to be considered a resume
        return {"statusCode": 404, "body": "Not a valid resume"}

def invoke_model_soonet(prompt):
    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 10000,
            "temperature": 0.3,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            ]
        })

        modelId = "arn:aws:bedrock:us-east-1:211125353899:inference-profile/us.anthropic.claude-sonnet-4-20250514-v1:0"

        response = bedrock_runtime.invoke_model(
            body=body,
            modelId=modelId,
            accept='*/*',
            contentType='application/json'
        )

        # Parse the Bedrock envelope
        model_output = json.loads(response['body'].read())
        llm_text = model_output.get("content", [{}])[0].get("text", "").strip()

        if not llm_text:
            raise ValueError("Model returned empty text.")

        # Extract JSON from code block if present
        json_match = re.search(r'```json\s*(.*?)\s*```', llm_text, re.DOTALL)
        json_str = json_match.group(1).strip() if json_match else llm_text.strip()

        if not json_str:
            raise ValueError("No JSON found in model output.")

        # Clean control chars
        json_str = re.sub(r'[\x00-\x1F\x7F]', '', json_str)

        return json.loads(json_str)

    except Exception as e:
        print("Unexpected error:", str(e))
        return {"error": f"Unexpected error: {str(e)}"}

def invoke_qwen3_32b(prompt: str,
                     stream: bool = False,
                    #  model_id: str = "qwen.qwen3-coder-480b-a35b-v1:0",
                     model_id: str = "qwen.qwen3-235b-a22b-2507-v1:0",

                     region: str = "ap-south-1") -> str or iter:
    """
    Invoke the Qwen3-32B dense model on Amazon Bedrock via boto3.

    Args:
        prompt (str): The user instruction or question.
        stream (bool): If True, stream the output as it arrives.
        model_id (str): Bedrock model ID for Qwen3-32B (dense).
        region (str): AWS region where model is available (default ap-south-1).

    Returns:
        str: Full generated content (if stream=False).
        iterator of str: Streaming text chunks (if stream=True).
    """
    try:
        client = boto3.client("bedrock-runtime", region_name=region)
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": "You are a expert Human Resource (HR) Manager."},
                {"role": "user", "content": prompt}
            ],
            "max_completion_tokens": 4000,
            "temperature": 0.1,
            "top_p": 0.1,
            "stream": stream
        }

        if stream:
            response = client.invoke_model_with_response_stream(
                modelId=model_id,
                contentType="application/json",
                body=json.dumps(payload),
                accept="application/json",
            )
            def generator():
                for event in response["body"]:
                    chunk = json.loads(event["chunk"]["bytes"])
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        if "content" in delta:
                            yield delta["content"]
            return generator()

        else:
            response = client.invoke_model(
                modelId=model_id,
                contentType="application/json",
                body=json.dumps(payload),
                accept="application/json",
            )
            resp_body = json.loads(response["body"].read().decode("utf-8"))
            texts = []
            for choice in resp_body.get("choices", []):
                msg = choice.get("message", {})
                if "content" in msg:
                    texts.append(msg["content"])
            return "\n".join(texts) or "(No output)"

    except (BotoCoreError, ClientError, json.JSONDecodeError) as e:
        if stream:
            return iter([f"[Error] {e}"])
        return f"[Error] {e}"

def get_json_from_qwen3(response):
    try:
        response = json.loads(response)
    except json.JSONDecodeError as e:
        print("qwen model colled seecond time for proper json format")
        # prompt = f"make this broken json in a proper readable json  provide only json do not give anything else in output.  {response}"
        # response = invoke_qwen3_32b(prompt)
        # response = json.loads(response)

    except Exception as r:
        print(e)
    return response
        
def extract_images_from_pdf(pdf_bytes):
    print('called extract_images_from_pdf')
   

    images_base64 = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    print('doc opened')

    for page in doc:
        print('started loop')
        pix = page.get_pixmap(dpi=150)
        image_bytes = pix.tobytes("png")
        img_str = base64.b64encode(image_bytes).decode("utf-8")
        images_base64.append(img_str)
    print('images_base64 len',len(images_base64))
    return images_base64

def invoke_claude_with_image(base64_images):                
    print('called invoke_claude_with_image')
    messages = [
        {
            "role": "user",
            "content": []
        }
    ]

    # Add images
    for image_str in base64_images:
        messages[0]["content"].append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": image_str
            }
        })
    # Add resume parsing instructions
    messages[0]["content"].append({
        "type": "text",
        "text": ('Carefully analyze the entire resume shown in the image. Extract all visible information and present it in plain text format, organized topic-wise never miss name, emaail and year of experience. as it wil always present in the data\n\n'
            'Name:\nEmail:\nExperience in year:\nAchievements:\nTechnical skills:'
            '\nSoft skills:\nCore skills:\nEducation:\nIndustry experience:\nResponsibilities:'
            '\nAchievements against responsibility:\nCertifications:\nStrength:\n'
            'Experience type (leadership, Mid management, Senior management, Team lead, Individual contributor):'
            '\nTeam handling experience:\nIndustry type(B2B, D2C, C2C, B2C):\n\nAssistant:\" turn'



                
        )
    })



    body = {
        "messages": messages,
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096
    }
    print('model version from prompt body',body['anthropic_version'])
    body = json.dumps(body)
    

    # Send request to Bedrock (Claude)
    response = bedrock_runtime.invoke_model(
        body=body,
        modelId="anthropic.claude-3-haiku-20240307-v1:0",
        # modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        # modelId="anthropic.claude-sonnet-4-20250514-v1:0",
        contentType="application/json",
        accept="application/json"
    )
    print('Result:',response)
    response_body = json.loads(response["body"].read())
    
    return response_body.get("content", [{}])[0].get("text", "")

def reset_skills_if_partition_exists(table_name, partition_key, sort_key):
    table = dynamodb.Table(table_name)

    try:
        # First, check if the item exists
        response = table.get_item(
            Key={
                'PK': partition_key,
                'SK': sort_key
            }
        )

        if 'Item' not in response:
            # No item found for this partition
            return {"message": "Item not found, nothing updated"}

        # If item exists, reset all skills to empty arrays
        update_expression = "SET coreSkills = :emptyList, technicalSkills = :emptyList, softSkills = :emptyList, updatedAt = :updatedAt"
        
        expression_attribute_values = {
            ":emptyList": [],
            ":updatedAt": int(datetime.now().timestamp() * 1000)
        }

        update_response = table.update_item(
            Key={
                'PK': partition_key,
                'SK': sort_key
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW"
        )

        return update_response

    except Exception as e:
        return {"error": str(e)}

def reset_frontend_auto_populations_in_dynamodb(table_name, partition_key, sort_key):
    # Force defaults
    multipleCandidateExperience = []
    about = ""
    responsibilities = []

    table = dynamodb.Table(table_name)

    # Get current date and time
    current_datetime = datetime.now().isoformat()

    response = table.update_item(
        Key={
            'PK': partition_key,
            'SK': sort_key
        },
        UpdateExpression="""
            SET multipleCandidateExperience = :multipleCandidateExperience,
                multipleCandidateExperiencedDate = :multipleCandidateExperiencedDate,
                about = :about,
                responsibilities = :responsibilities
        """,
        ExpressionAttributeValues={
            ':multipleCandidateExperience': multipleCandidateExperience,
            ':multipleCandidateExperiencedDate': current_datetime,
            ':about': about,
            ':responsibilities': responsibilities
        },
        ReturnValues="UPDATED_NEW"
    )

    return response

def correct_https_in_links(otherSocialPlatforms):
    try:
        for platform, links in otherSocialPlatforms.items():
            # Normalize to list
            if isinstance(links, str):
                links = [links]

            corrected_links = []
            for link in links:
                if not link:
                    corrected_links.append("")
                    continue

                link = link.strip()

                # Case 1: Already has https:// or http:// → keep as is
                if link.startswith("https://") or link.startswith("http://"):
                    corrected_links.append(link)

                # Case 2: Starts with www. or subdomain (like in.linkedin.com)
                elif link.startswith("www.") or "." in link.split("/")[0]:
                    corrected_links.append("https://" + link)

                # Case 3: Plain domain without www or protocol
                else:
                    corrected_links.append("https://www." + link)

            otherSocialPlatforms[platform] = corrected_links

    except Exception as e:
        print(f"Social links can't be formatted correctly: {e}")

    return otherSocialPlatforms

def invoke_model_with_backoff_OpenAI(prompt,Task="Not Specifield" ,max_retries=10, want_json=True, base_delay=2):
    print({"Task to ai":Task})
    system_content = "You are a helpful assistant."
    
    for attempt in range(max_retries):
        try:
            return invoke_model_OpenAI(system_content, prompt,want_json)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < max_retries - 1:
                delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                print(f"Throttling occurred. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                raise

def invoke_model_OpenAI(system_content, prompt, want_json=True, max_try_for_json=2):
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")     
    deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")

    if not all([endpoint, deployment_name, api_version, api_key]):
        raise ValueError("Missing Azure OpenAI configuration in environment variables")

    url = f"{endpoint}/openai/deployments/{deployment_name}/chat/completions?api-version={api_version}"

    headers = {
        "Content-Type": "application/json",
        "api-key": api_key
    }

    data = {
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        # "max_tokens": 10000,
    }

    if not want_json:
        response = requests.post(url=url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]

    else:
        for attempt in range(max_try_for_json):
            try:
                response = requests.post(url=url, headers=headers, json=data)
                response.raise_for_status()
                result = response.json()
                try :
                    tokens = result["usage"]
                    output_tokens= tokens["completion_tokens"]
                    input_tokens= tokens["prompt_tokens"]
                    total = tokens["total_tokens"]
                    print(" Token usage details input_tokens :-",input_tokens,"output_tokens",output_tokens,"total",total)

                except Exception as e :
                    print("errore occured input output token not found :--",e)
                print(result)
                content = result["choices"][0]["message"]["content"]
                content = content.strip().removeprefix("```json").removesuffix("```").strip()
                return json.loads(content)

            except Exception as e:
                remaining = max_try_for_json - attempt - 1
                
                print(f"JSON parse failed. Retries left: {remaining}")
                                # Safely show content ONLY if result exists
                try:
                    print(result["choices"][0]["message"]["content"])
                except:
                    print("No content received from API.")

                print("Error:", e)
                time.sleep(5)
                if remaining == 0:
                    raise

def clean_json_response(response: str) -> str:
    return response.strip().removeprefix("```json").removesuffix("```").strip()

def get_account_id():
    # Create STS client
    sts_client = boto3.client('sts')

    # Call get-caller-identity
    response = sts_client.get_caller_identity()

    # Extract account ID
    return response['Account']

def update_sqs_queue_resume_parser(userId,ID):
    event = "UPDATE_CV_CENTRAL_CAND_PROFILE"
    email = userId.split("#")[-1]
    queue_name = 'worko-app-event-queue'
    # Determine the event based on type
    # event = "REFERRAL_VALIDATE_MATCHING_SCORE"
    message_body ={
        "event": event,
        "userEmail" : email,
        "userId": ID}


    print("event:-", event,"message_body",message_body)

    # Define the SQS queue URL
    account_id = get_account_id()
    queue_url = f"https://sqs.ap-south-1.amazonaws.com/{account_id}/worko-app-event-queue"
    # queue_url = f'https://sqs.{sqs_region}.amazonaws.com/{account_id}/{queue_name}'
    
    message_body_msg = json.dumps(message_body)
    
    response = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=message_body_msg
        )
    
    return {
        'statusCode': 200,
        'body': json.dumps('Message sent to SQS!')
    }


def get_secret(secret_name):
    secrets_client = boto3.client('secretsmanager', region_name='ap-south-1')

    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret_value = response['SecretString']
        
        # Try to parse as JSON, fallback to string
        try:
            secret_data = json.loads(secret_value)
        except json.JSONDecodeError:
            secret_data = secret_value
        return secret_data
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return {
                "statusCode": 404,
                "body": json.dumps({"error": f"Secret '{secret_name}' not found"})
            }
class AzureOpenAIClient:
    """Client for Azure OpenAI API with retry logic."""
    
    DEFAULT_TEMPERATURE = 0.3
    DEFAULT_API_VERSION = "2024-05-01-preview"
    # REQUEST_TIMEOUT = 30  # seconds
    
    def __init__(self, azure_openai_secret: Dict[str, str],model="gpt-4o"):
        
        """Initialize Azure OpenAI client.
        
        Args:
            azure_openai_secret: Dict containing:
                - AZURE_OPENAI_ENDPOINT
                - deployment_name
                - api_key
                - AZURE_OPENAI_API_VERSION (optional)
        """
        self.model = model
        if not isinstance(azure_openai_secret, dict):
            raise TypeError("azure_openai_secret must be a dictionary")
        
        self.endpoint = azure_openai_secret.get("AZURE_OPENAI_ENDPOINT", "")
        self.api_key = azure_openai_secret.get("AZURE_OPENAI_API_KEY", "")
        if model=="gpt-4o":
            self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT_gpt-4o", "")
            self.api_version = azure_openai_secret.get(
                "AZURE_OPENAI_API_VERSION_gpt-4o", 
                self.DEFAULT_API_VERSION
            )
        elif model=="gpt-4.1-mini":
            self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT_gpt-4.1-mini", "")
            self.api_version = azure_openai_secret.get(
                "AZURE_OPENAI_API_VERSION_gpt-4.1-mini", 
                self.DEFAULT_API_VERSION
            )

        
        
        # Validate required fields
        if not all([self.endpoint, self.deployment_name, self.api_key]):
            raise ValueError(
                "Missing required Azure OpenAI configuration: "
                "AZURE_OPENAI_ENDPOINT, deployment_name, and api_key are required"
            )
    
    def invoke_model_with_backoff(
        self,
        prompt: str,
        Task="Not specified",
        system_content: str = "You are a helpful assistant.",
        max_retries: int = 10,
        base_delay: int = 2,
        want_json: bool = True
    ) -> Union[str, Dict[Any, Any]]:
        """Invoke model with exponential backoff for rate limiting.
        
        Args:
            prompt: User prompt
            system_content: System message for the model
            max_retries: Maximum number of retry attempts
            base_delay: Base delay for exponential backoff
            want_json: Whether to parse response as JSON
            
        Returns:
            Model response as string or parsed JSON dict
        """
        print("using model :-", self.model)
        for attempt in range(max_retries):
            print("Task to Ai is :- ",Task)
            try:
                return self.invoke_model(system_content, prompt, want_json)
            
            except requests.exceptions.HTTPError as e:
                # Check for rate limiting (429) or server errors (5xx)
                if e.response.status_code in [500, 502, 503, 504]:
                    if attempt < max_retries - 1:
                        delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                        print(
                            f"Rate limit or server error (status {e.response.status_code}). "
                            f"Retrying in {delay:.2f} seconds..."
                        )
                        time.sleep(delay)
                    else:
                        raise
                else:
                    # Don't retry for other HTTP errors (auth, not found, etc.)
                    raise
            
            except requests.exceptions.RequestException as e:
                # Network errors - retry
                if attempt < max_retries - 1:
                    delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                    print(f"Network error: {e}. Retrying in {delay:.2f} seconds...")
                    time.sleep(delay)
                else:
                    raise
    
    def invoke_model(
        self,
        system_content: str,
        prompt: str,
        want_json: bool = True,
        max_json_retries: int = 3,
        temperature: float = DEFAULT_TEMPERATURE
    ) -> Union[str, Dict[Any, Any]]:
        """Invoke Azure OpenAI model.
        
        Args:
            system_content: System message
            prompt: User prompt
            want_json: Whether to parse response as JSON
            max_json_retries: Max retries for JSON parsing
            temperature: Model temperature
            
        Returns:
            Model response as string or parsed JSON dict
        """
        url = (
            f"{self.endpoint}/openai/deployments/{self.deployment_name}/"
            f"chat/completions?api-version={self.api_version}"
        )
        
        headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key
        }
        
        data = {
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature
        }
        
        if not want_json:
            response = requests.post(
                url=url, 
                headers=headers, 
                json=data
            
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        
        # JSON mode with retries
        for attempt in range(max_json_retries):
            try:
                response = requests.post(
                    url=url, 
                    headers=headers, 
                    json=data
                )
                response.raise_for_status()
                result = response.json()
                try :
                    tokens = result["usage"]
                    output_tokens= tokens["completion_tokens"]
                    input_tokens= tokens["prompt_tokens"]
                    total = tokens["total_tokens"]
                    print(" Token usage details input_tokens :-",input_tokens,"output_tokens",output_tokens,"total",total)

                except Exception as e :
                    print("errore occured input output token not found :--",e)
                
                # Extract and clean content
                content = result["choices"][0]["message"]["content"]
                content = content.strip()
                
                # Remove markdown code blocks
                if content.startswith("```"):
                    content = content.removeprefix("```json").removeprefix("```")
                    content = content.removesuffix("```").strip()
                
                return json.loads(content)
            
            except json.JSONDecodeError as e:
                remaining = max_json_retries - attempt - 1
                print(f"JSON parse failed. Retries left: {remaining}")
                print(f"Error: {e}")
                
                if remaining == 0:
                    print(f"Raw content: {content}")
                    raise ValueError(f"Failed to parse JSON after {max_json_retries} attempts") from e
                
                time.sleep(2)  # Brief delay before retry
            
            except (KeyError, IndexError) as e:
                print(f"Unexpected response structure: {result}")
                raise ValueError("Invalid response format from Azure OpenAI") from e
         
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
from utils import *
# import ulid    
import uuid
sqs = boto3.client('sqs')
# iac deploy 13

def process_cv_for_agency(processed_text,model,current_timestamp):
    prompt = """you are a Expert in Extracting data from Resume. do detailed analysis of below given resume text and extract
    the data return null if data is str or 0 if its number when you don't any data in resume.
    strict instructions: 
    1) provide only below given json as output no other comments or explanations are allowd.
    2) if noticePeriod is not mentioned in resume text return null for noticePeriod.
    3) startedYear and passingYear must be number or null not str eg, 2014, 2020 or null if not mentioned in resume text.

    {{
        "name": "",
        "email": "",
        "about":"extract about me or summary or profile or objective from resume",
        "phoneNumberDetails": {{
            "number": 9666308100,
            "countryCode": 91
        }},
        "education":[
        {{
        "collage": "[INSTITUTION_NAME or COLLEGE_NAME]",
        "degree": "[DEGREE_NAME]",
        "startedYear": "[STARTED_YEAR]",
        "passingYear": "[GRADUATION_YEAR]",  
        }},   
        "multipleCandidateExperience": [
        {{
         "companyName: [COMPANY_NAME]
         "designation: [JOB_TITLE]
         "department: [DEPARTMENT]
         "YOE": 0,
         "startDate: [START_DATE]
          "endDate: [END_DATE or empty string if ongoing]
         }}   
            ],
        "currentCompany": "",
        "currentDesignation": "",
        "totalYOE": 0,
        "relevantYOE": 0,

        "noticePeriod": 0,
        "location": "",
        "readyToRelocate": false
        
    }}

    Resume Text : {}
    """.format(processed_text)

    # response = invoke_model_with_backoff_OpenAI(prompt,Task = "Agency Resume parsing")

    response = model[0].invoke_model_with_backoff(prompt,Task= "Agency Resume parsing " )
    
    response = process_parsed_cv_json(response)


    prompt = (
        f"**Extract the following details from the resume extract:**\n"
        f"- Core Skills (max 30 chars each)\n"
        f"- Soft Skills (max 30 chars each)\n"
        f"- Preferred departments (0–5, based on experience & skills)\n"
        f"- Years of Experience (YOE)\n\n"

        f"**Instructions**:\n"
        f"- Use ONLY information explicitly written in the resume.\n"
        f"- Extract ONLY the top 20 Core Skills and top 10 Soft Skills.\n"
        f"- **Core Skills (TECH)** = high-level domains only (System Architecture, Microservices Design).\n"
        f"- **Technical Skills** = tools, languages, frameworks, cloud, DBs, certifications.\n"
        f"- **Core Skills (NON-TECH)** = business/functional domains only.\n"
        f"- **Technical Skills (NON-TECH)** = tools/platforms (Excel, SQL, Salesforce, SAP).\n"
        f"- Soft Skills = interpersonal traits (Communication, Leadership, Problem Solving).\n"
        f"- Add YOE for Core Skills if mentioned, else 0.\n"
        f"- Calculate total YOE from roles or dates.\n\n"

        f"**Mandatory Rules**:\n"
        f"- ALWAYS Soft Skills (never Core): Managing Escalations, Team Mentoring, Leadership, Strategic Planning,\n"
        f"  Stakeholder Management, Goal Setting, Problem Solving, Quick Learner, Data-driven decision-making.\n"
        f"- Core Skills must NOT include:\n"
        f"  • Job titles (Project Manager)\n"
        f"  • Action phrases (Managing Escalations, Driving Initiatives)\n"
        f"  • Interpersonal traits (Leadership, Mentoring)\n"
        f"  • Tools/software (Excel, SAP, Salesforce)\n"
        f"- Use timestamp for createdAt & updatedAt: {current_timestamp}\n\n"

        f"**STRICT Example**:\n"
        f"coreSkills: AWS or Cloud, Web App Design, Sales, Marketing\n"
        f"softSkills: Escalation handling, Strategy & Execution, Team mentoring, Presentation skills,\n"
        f"            Budget Management, Problem Solving, Quick Learner, Time management\n"
        f"technicalSkills: CRM tools\n\n"

        f"**STRICT RULES**:\n"
        f"- If more than 20 skills exist, pick the 20 most relevant.\n"
        f"- Do NOT invent skills.\n"
        f"- A skill MUST appear only once across all categories.\n"
        f"- Never include responsibilities/duties as skills.\n"
        f"- Skills must be concise names.\n"
        f"- For NON-TECH profiles: Core = domain/business expertise only.\n"
        f"- Terms with verbs like Managing/Handling/Driving/Mentoring → Soft Skill.\n\n"

        f"Resume extract:\n\n{processed_text}\n\n"

        f"Return JSON only:\n"
        f"{{{{\n"
        f"  \"coreSkills\": [\n"
        f"    {{{{\"skillName\": \"[CORE_SKILL_NAME]\", \"years\": [YEARS_OF_EXPERIENCE]}}}}\n"
        f"  ],\n"
        f"  \"technicalSkills\": [\n"
        f"    {{{{\"skillName\": \"[TECHNICAL_SKILL_NAME]\", \"years\": [YEARS_OF_EXPERIENCE]}}}}\n"
        f"  ],\n"
        f"  \"softSkills\": [\n"
        f"    {{{{\"skillName\": \"[SOFT_SKILL_NAME]\"}}}}\n"
        f"  ],\n"
        f"  \"userPreferredDepartments\": [\n"
        f"    \"List the department names based on resume designations and core skills\"\n"
        f"  ],\n"
        f"  \"userPreferredIndustries\": [\n"
        f"    \"Extract up to 3 industries such as Information Technology, Banking, Healthcare\"\n"
        f"  ],\n"
        f"  \"userPreferredlocations\": [\n"
        f"    \"Extract if mentioned; else return empty list\"\n"
        f"  ],\n"
        f"  \"userPreferredRoles\": [\n"
        f"    \"Extract roles/designations from resume\"\n"
        f"  ]\n"
        f"}}}}\n"
    )

    # content2 = invoke_model_with_backoff_OpenAI(prompt,Task = "Agency Resume parsing for skills and pref")

    
    content2 = model[1].invoke_model_with_backoff(prompt,Task= "Agency Resume parsing for skills and pref" )
    # candidateParsedCvAwsS3File =candidateParsedCvAwsS3FileName.split(".")[-1]
    # addded_details = {
    #                 "jobId":jobId,
    #                 "agencyUserId":agencyUserId,
    #                 "candidateParsedCvAwsS3FileName":candidateParsedCvAwsS3File,
    #                 "agencyUserId":companyId}
    merged = {**response, **content2}  # , **addded_details}
    merged = process_parsed_cv_json(merged)
    return merged
# Initialize the AWS service clients
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')

def lambda_handler(event, context):
    print("Got a event" ,event)
    start_time = time.time()

    env = os.environ.get('ENV','dev')
    secret_name = "AZURE-openai-secret-multimodel-"+env
    azure_openai_secret =get_secret(secret_name)
    models_available = ["gpt-4o","gpt-4.1-mini"]
    current_timestamp = datetime.now().isoformat()

    gpt_4o_model = AzureOpenAIClient(azure_openai_secret,model="gpt-4o")
    gpt_4_1_mini_model = AzureOpenAIClient(azure_openai_secret,model="gpt-4.1-mini")
    gpt_models = [gpt_4o_model,gpt_4_1_mini_model]

    agencyUserId = event.get('agencyUserId',"")
    cvAwsS3ResourceType = event.get("cvAwsS3ResourceType","")
    if event.get("event") == "SOURCE_TYPE_REFRESH_CV":
        print("SOURCE_TYPE_REFRESH_CV event received.")
        cvAwsS3FilePath = event.get("cvAwsS3FilePath")
        cvAwsS3ResourceType = event.get("cvAwsS3ResourceType")
        s3_bucket_name = event.get("cvAwsS3BucketName")
        FileName = event.get("candidateParsedCvAwsS3FileName")
        key = f"{cvAwsS3FilePath}/{FileName}"
        print("key:",key,"s3_bucket_name",s3_bucket_name)
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
        
        if ".pdf" in key:
            processed_text,links_from_pdf = extract_text_from_pdf(data)
            if not processed_text : 
                print('image Based cv processing..')                        ###
                base64_images = extract_images_from_pdf(data)
                processed_text = invoke_claude_with_image(base64_images)   
                print('image Based cv process completed')   
        elif ".docx" in key:
            processed_text = extract_text_from_docx(data)
        else:
            print("The file format is not supported.")
            return {
                'statusCode': 400,
                'body': json.dumps({'message': 'Unsupported file format. Please upload a PDF or DOCX file.'})
            }

        print("processed_text", processed_text)

        merged = process_cv_for_agency(processed_text,gpt_models,current_timestamp)
            
            # "currentCTC": 0,
            # "expectedCTC": 0,

        print("final response for refresh cv", merged)
        return {
            'statusCode': 200,
            'body': json.dumps(merged)
        }

    elif agencyUserId or cvAwsS3ResourceType == "CAND_SUBMIT_CV_JOB":
        S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME',"worko-app-dev")
        s3_bucket_name = S3_BUCKET_NAME
        if cvAwsS3ResourceType == "CAND_SUBMIT_CV_JOB":
            companyId= event.get("companyId","")
            jobId = event.get("jobId","")
            candidateParsedCvAwsS3FileName = event.get("candidateParsedCvAwsS3FileName","")
            # example_path = "s3://worko-app-dev/candidate-submit-cvs/companies/01JWAQF1G96E0SE9XHXSFGHNWW/jobs/01K7Z7RM97J7V8E4059KQ1D2Z6/cvs/01KH1XG7Y8JJHZ65CAX8ZPERCQ.pdf"
            key = f"candidate-submit-cvs/companies/{companyId}/jobs/{jobId}/cvs/{candidateParsedCvAwsS3FileName}"
            print("key",key)
        
        else:
            companyId = event.get('companyId',"")
            jobId = event.get('jobId',"")
            candidateParsedCvAwsS3FileName = event.get("candidateParsedCvAwsS3FileName","")
            key = f"agencies/{agencyUserId}/companies/{companyId}/jobs/{jobId}/user-profiles/{candidateParsedCvAwsS3FileName}"
            print("key",key)

            # s3_path = "agencies/{agencyUserId}/companies/{companyId}/jobs/{jobId}/user-profiles/{candidateParsedCvAwsS3FileName}"

            
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

        if ".pdf" in key:
            processed_text,links_from_pdf = extract_text_from_pdf(data)
            if not processed_text : 
                print('image Based cv processing..')                        ###
                base64_images = extract_images_from_pdf(data)
                processed_text = invoke_claude_with_image(base64_images)   
                print('image Based cv process completed')   
        elif ".docx" in key:
            processed_text = extract_text_from_docx(data)
        else:
            print("The file format is not supported.")
            return {
                'statusCode': 400,
                'body': json.dumps({'message': 'Unsupported file format. Please upload a PDF or DOCX file.'})
            }

        print("processed_text", processed_text)
        merged = process_cv_for_agency(processed_text,gpt_models,current_timestamp)
            
            # "currentCTC": 0,
            # "expectedCTC": 0,

        print("final response for agency", merged)
        return {
            'statusCode': 200,
            'body': json.dumps(merged)
        }
    
    else:
        partition_key_value = event.get('USER_PK')
        sort_key_prefix = event.get('USER_DETAIL_SK')
        skill_sort_key = "SKILL#"
        yoe_sort_key = "ID#"
        sort_key_Preff = "PREF#"

        S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')
        table_name = os.environ.get('DYNAMO_TABLE_NAME')
        reset_skills_if_partition_exists(table_name, partition_key_value, skill_sort_key) #reset Skills to empty array
        

        # Query DynamoDB for items where SK begins with "ID#"
        item = query_dynamodb_item_with_sk_prefix(table_name, partition_key_value, sort_key_prefix)
        ID = item.get("id")
        if item:
            sort_key_value = item.get('SK')
            resumeId = item.get('SK').split('#')[-1]
            cvId = item.get('CV')
            print("cvId", cvId)

            # Prepare the response body
            body_content = json.dumps(item, cls=DecimalEncoder)

            # s3_bucket_name = os.environ['S3_BUCKET_NAME']
            s3_bucket_name = S3_BUCKET_NAME
            key = "users/" + resumeId + "/resumes/" + cvId
            print("key", key)
            
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
            reset_frontend_auto_populations_in_dynamodb(table_name, partition_key_value, sort_key_value)   # reset the feilds about,responsibilities,multipleCandidateExperience
            reset_pref_section_in_dynamo(table_name, partition_key_value, sort_key_Preff)      # reset the feilds pref role and industry.
            reset_otherSocialPlatForms_in_dynamodb(table_name, partition_key_value)
            reset_partition(partition_key_value)    #educaton
            # Extract text from the PDF or DOCX file
            if ".pdf" in key:
                processed_text,links_from_pdf = extract_text_from_pdf(data)
                if not processed_text : 
                    print('image Based cv processing..')                        ###
                    base64_images = extract_images_from_pdf(data)
                    processed_text = invoke_claude_with_image(base64_images)   
                    print('image Based cv process completed')   
            elif ".docx" in key:
                processed_text = extract_text_from_docx(data)
            else:
                print("The file format is not supported.")
                return {
                    'statusCode': 400,
                    'body': json.dumps({'message': 'Unsupported file format. Please upload a PDF or DOCX file.'})
                }

            print("processed_text", processed_text)
            
            # IMPORTANT: Check if the document is a valid resume before proceeding
            # This check should happen right after text extraction and before any processing
            result = check_if_resume(processed_text)
            
            if result["statusCode"] != 200:
                print("No valid resume data found or resume data is not readable")
                return {
                    'statusCode': 400,
                    'body': json.dumps({'message': 'The uploaded file does not appear to be a valid resume. Please upload a proper resume.'})
                }
            end_time = time.time()
            print(f'Step 1 feched cv and read as text time took :- {end_time-start_time}')
            # Continue with resume processing since we've confirmed it's a valid resume
            if processed_text != {"errorMsg": "Unfortunately, we are not able to read your resume"}:
            
                
                prompt = (
                f"**Extract the following details from the resume extract:**\n"
                f"- Core Skills (max 30 chars each)\n"
                f"- Soft Skills (max 30 chars each)\n"
                f"- Prefered departments (for this field analyze entire resume and suggest some 0-5 departments based on experience and skills. example: data science, marketting)"
                f"- Years of Experience (YOE)\n"
                f"**Instructions**:\n"
                f"- Use ONLY information explicitly written in the resume. No assumptions.\n"
                f"- Extract ONLY the top 20 Core Skills and 10 Soft Skills if more then 10 present take only top 10 most relavant.\n"
                f"- **Core Skills (TECH profiles): HIGH-LEVEL domains or expertise areas only (e.g., Software Development, Cloud Computing). DO NOT include tools, job responsibilities, or interpersonal abilities.**\n"
                f"Examples: System Architecture, Microservices Design.\n"
                f"- **Technical Skills: All specific tools, programming languages (Python, Java), frameworks (React, Django), cloud platforms (AWS, Azure), databases (MySQL), certifications.**\n"
                f"- **Core Skills (NON-TECH profiles): ONLY business or functional domains like Business Analysis, Marketing Strategy, Financial Planning. NEVER include leadership, management, team coordination, communication, mentoring, or action phrases.**\n"
                f"- **Technical Skills (NON-TECH): Tools (Salesforce, SAP), software (Excel, SQL), CRM, industry platforms, or certifications (PMP).**\n"
                f"- Soft Skills: ALL interpersonal or behavioral skills such as communication, teamwork, leadership, mentoring, negotiation, decision-making, adaptability, problem solving.\n"
                f"Examples: Communication, Teamwork, Leadership, Strategic Thinking.\n"
                f"- Add YOE for Core Skills if mentioned, else 0.\n"
                f"- Calculate total YOE from roles or experience dates; if missing, sum role durations.\n"
                f"**Mandatory moves**:\n"
                f"- The following are ALWAYS Soft Skills, NEVER Core Skills: 'Managing Escalations', 'Team Mentoring', 'Team Leadership', 'Strategic Planning', 'Stakeholder Management', 'Goal Setting', 'Problem Solving', 'Quick Learner', 'Leadership', 'Data-driven decision-making'.\n"
                f"- Core Skills MUST ONLY represent business or functional expertise or technical domains. DO NOT include:\n"
                f"  Job titles (e.g., Project Manager)\n"
                f" Action phrases (e.g., Managing escalations, Driving initiatives,Team mentoring)\n"
                f" Interpersonal traits (e.g., Leadership, Mentoring)\n"
                f" Technical tools or software (e.g., CRM systems, Excel, SAP, Salesforce)\n"
                f"- Use current timestamp for createdAt & updatedAt: {current_timestamp}\n"
                f"**STRICT Example**"
                f"coresklls : AWS or Cloud, Web App Design , Sales, Marketting"
                f"softSkills : Escalation handling, Strategy & Execution, Team mentoring, Presentation skills, Budget Management, Problem Solving, Quick Learner, Time management, Multi-tasking, Strategy & Execution"
                f"technicalSkills :CRM tools,"
                f"**STRICT RULES**:\n"
                f"- If more than 20 skills exist, pick the 20 most relevant.\n"
                f"- DO NOT guess, infer, or invent skills. Use ONLY resume text.\n"
                f"- A skill MUST appear in ONE category only. No duplicates across coreSkills, technicalSkills, softSkills.\n"
                f"- NEVER include full sentences, responsibilities, or job duties as skills.\n"
                f"- Skills MUST be concise names, NOT sentences.\n"
                f"- Never add Escalation handling, Team mentoring in Core skills these are soft skills"
                f"- For NON-TECH profiles: Core Skills = ONLY domain/business expertise. ALL leadership, mentoring, managing, stakeholder handling, escalation handling → Soft Skills.\n"
                f"- If a term includes verbs like 'Managing', 'Handling', 'Driving', 'Mentoring', classify it as Soft Skill.\n"
                f"- The following terms are ALWAYS Soft Skills: 'Problem Solving', 'Quick Learner', 'Team Mentoring', 'Leadership', 'Managing Escalations', 'Data-driven decision-making'.\n\n"
                f"Resume extract:\n\n{processed_text}\n\n"
                f"Return JSON only:\n"
                f"{{\n"
                f"  \"coreSkills\": [\n"
                f"    {{\"skillName\": \"[CORE_SKILL_NAME]\",\"years\":[YEARS_OF_EXPERIENCE]}}\n"
                f"  ],\n"
                f"  \"technicalSkills\": [\n"
                f"    {{\"skillName\": \"[TECHNICAL_SKILL_NAME]\",\"years\":[YEARS_OF_EXPERIENCE]}}\n"
                f"  ],\n"
                f"  \"softSkills\": [\n"
                f"    {{\"skillName\": \"[SOFT_SKILL_NAME]\"}}\n"
                f"  ],\n"
                f"  \"Prefered_departments\":[list the names of the departments that suits the cv focus on designations of candidate and core skills],\n"
                f"  \"YOE\": [TOTAL_YEARS_OF_EXPERIENCE]\n"
                f"}}"
            )





                content = invoke_model_with_backoff(prompt)
                print_completion_text(content)
                core_skills,technical_skills,soft_skills,Prefered_departments, yoe = extract_skill_data_nova(content)

                updated_core_skills = update_core_skills_years(core_skills)  ##
                print_completion_text(updated_core_skills)

                updated_technical_skills = update_technical_skills_years(technical_skills)
                print_completion_text(updated_technical_skills)
                
                print_completion_text(soft_skills)
                print_completion_text(yoe)

                update_skills_in_dynamodb(table_name, partition_key_value, skill_sort_key,updated_core_skills, updated_technical_skills,soft_skills)
                
                update_yoe_in_dynamodb(table_name, partition_key_value, yoe_sort_key, yoe)
                update_pref_department_in_dynamo(table_name, partition_key_value, sort_key_Preff, sort_key_value,Prefered_departments)

                end_time = time.time()
                print(f'Step 2 Skils is saved in dynamo time took :- {end_time-start_time}')
            
            if processed_text:
                prompt = (
                        f"Extract the following details from the resume:\n\n"
                        f"about:\n"
                        f"Personal Details:\n"
                        f"- Full name\n"
                        f"- Email address\n"
                        f"- Phone number\n\n"
                        f"Education and Certifications:\n"
                        f"- Educational qualifications with institution names and graduation years\n"
                        f"- Professional certifications with issuing organizations and dates\n\n"
                        f"Industry Experience:\n"
                        f"- Detailed industry knowledge and sector-specific expertise\n"
                        f"- Domain-specific skills and understanding\n"
                        f"- Industry-specific tools, methodologies, and practices used\n\n"
                        f"Professional Experience:\n"
                        f"- Key roles and positions held with companies\n"
                        f"- Time periods for each position\n"
                        f"- Detailed description of work performed, projects completed, and responsibilities handled\n"
                        f"- Technical skills applied in professional settings\n\n"
                        f"- Return every single experience never miss any single one\n\n"
                        f"- Return all the Professional Experience in the same sequence as of resume"
                        f"Role and Responsibilities:\n"
                        f"-for each experience metioned in resume extract these fields"
                        f"- startDate"
                        f"- endDate"
                        f"- Core job functions and responsibilities\n"
                        f"- Key accomplishments and achievements in each role\n"
                        f"- Quantifiable results and impacts\n"
                        f"- Team leadership and management experience\n\n"
                        f"- Return all the Role and Responsibilities in the same sequence as of resume"
                        f"- give all Responsibilities in 2-4 lines only"
                        f"preferredRoles\n" 
                        f"You are an expert career advisor and recruiter with 20+ years of experience across both technical and non-technical domains.\n"
                        f"I will provide you with a candidate’s CV or resume. Based on the CV, you must suggest 5 highly relevant job designations that align with the candidate’s profile.\n"
                        f"\n"
                        f"Follow these instructions:\n"
                        f"You must concider conadidates seniority level to give suggestions"
                        f"1. Analyze the CV to extract:\n"
                        f"   - Total experience, key skills/tools/domains, recent 2–7 roles & responsibilities.\n"
                        f"   - Career trajectory: IC, leadership, or entrepreneurial.\n"
                        f"   - Certifications, awards, or domain achievements.\n"
                        f"2. Generate realistic job designations aligned with skills and seniority across:\n"
                        f"   - Technical and non-technical roles, core and adjacent functions.\n"
                        f"- Do NOT output internal reasoning or chain-of-thought and any name of  company or location.\n"
                        f"\n"
                        f"preferedIndustriy\n"
                        f"-Extract the industry in which candidate is working and Reseme is showing relavance examples : Information Technology,Financial Services, Banking,Healthcare & Pharmaceuticals,Manufacturing. maximum should be 3 \n"
                        f"otherSocialPlatForms\n"
                        f"- Extract all the scocial links present in resume exacmples linkedin: https://www.linkedin.com/in/shaukatshaikh7/"
                        f"- If any other links then github, lnkedin, twiter are there then keep adding in similar fashion "
                        f"Important Instructions:\n"
                        f"- Extract ONLY information explicitly mentioned in the resume\n"
                        f"- Do not infer or fabricate any details not present in the text\n"
                        f"- Keep the information concise and relevant\n"
                        f"- For each section, extract up to 5 most relevant points\n"
                        f"- If information for any section is not available, return an empty array\n\n"
                        f"Here is the resume:\n\n"
                        f"{processed_text}\n\n"
                        f"if linkes are not correctly writen in Rsume text use these links {links_from_pdf}"
                        f"Return only the following JSON structure with extracted values. Do not provide any additional content, explanations, or details:\n\n"
                        f"{{\n"
                        f"  \"about\": \"[Extract the exact text from resume in Profile section remove any formatings oe headings and give in string format., this could be in heading of, summary, first heading, Profile]\",\n"
                        f"  \"personalDetails\": {{\n"
                        f"    \"name\": \"[FULL_NAME]\",\n"
                        f"    \"email\": \"[EMAIL_ADDRESS]\",\n"
                        f"    \"phone\": \"[PHONE_NUMBER]\"\n"
                        f"  }},\n"
                        f"  \"education\": [\n"
                        f"    {{\n"
                        f"      \"degree\": \"[DEGREE_NAME]\",\n"
                        f"      \"collage\": \"[INSTITUTION_NAME or COLLEGE_NAME]\",\n"
                        f"      \"passingYear\": \"[GRADUATION_YEAR]\",\n"
                        f"      \"createdAt\": \"[{current_timestamp}]\",\n"     
                        f"    }}\n"               
                        f"  ],\n"
                        f"  \"multipleCandidateExperience\": [\n"
                        f"    {{\n"
                        f"      \"companyName\": \"[COMPANY_NAME]\",\n"
                        f"      \"designation\": \"[JOB_TITLE]\",\n"
                        f"      \"department\":\"[Department of the works Experience]\",\n"
                        f"      \"YOE\":\"[Return the exact number of years candidate worked for this comapny in float (see start date and end date and substract to find out. , if the year is same the return in months example 0.5 for 6 months. if it comes less then 6 months return 0.5 only). an if enddate is present the use {current_timestamp} as present date to calculate YOE.]\",\n"
                        f"      \"startDate\": \"[Start of EMPLOYMENT in YYYY-MM-DD format example 2025-09-09]\",\n"
                        f"      \"endDate\": \"[End of EMPLOYMENT if present or candidate is still working in the company return present]\",\n"
                        f"      \"responsibilities\": [\n"
                        f"        \"[RESPONSIBILITY_1 (return only 2-3 lines of main responsibilities)]\",\n"
                        f"        \"[RESPONSIBILITY_2 (return only 2-3 lines of main responsibilities)]\"\n"
                        f"      ],\n"
                        f"    }}\n"
                        f"  ],\n"
                        f"  \"preferedRoles\":[]\n"
                        f"  \"preferedIndustry\":[]\n"
                        f"  \"otherSocialPlatForms\": {{\n"
                        f"    Example \"github\": \"[return the exact link text if provided in Resume else return empty string key should be in lower case]\",\n"
                        f"    Example \"linkedin\": \"[return the exact link text if provided in Resume else return empty string key should be in lower case]\",\n"
                        f"    Example \"twiter\": \"[return the exact link text if provided in Resume else return empty string key should be in lower case]\",\n"

                        f"  }},\n"
                        f"}}"
                    )
                completion_text = invoke_model_with_backoff_OpenAI(prompt,Task = "Generate cvExtractparsed")
                # completion_text=clean_json_response(completion_text)
                try:
                    completion_text = json.loads(completion_text)
                except Exception as e:
                    print(f"can't load json  {e}")
                # completion_text = invoke_qwen3_32b(prompt)
                # completion_text = get_json_from_qwen3(completion_text)

                # completion_text = extract_data_nova(content)# nova
                # print_completion_text(completion_text)#  nova
            else:
                completion_text = {"errorMsg": "Unfortunately, we are not able to read your resume"}

            # completion_text = clean_json_string(completion_text)  #  nova
            print("Processed completion_text: ", completion_text)

            # Update the DynamoDB item with the cvExytractparsed json
            update_response = update_cv_extract_parsed_in_dynamodb(table_name, partition_key_value, sort_key_value, completion_text)
            


            multipleCandidateExperience = completion_text['multipleCandidateExperience']
            about = completion_text['about']
            otherSocialPlatForms= completion_text['otherSocialPlatForms']
            preferedRoles= completion_text['preferedRoles']
            preferedIndustry= completion_text['preferedIndustry']


            responsibilities=[]
            for i in completion_text["multipleCandidateExperience"]:
                # print(i)
                item={}
                item["companyName"]=i["companyName"]
                item["date"]={"startDate" :i["startDate"],"endDate":i["endDate"]}
                multiline_string = "\n".join(i["responsibilities"])
                item["description"]=multiline_string
                responsibilities.append(item)

            Prefered_section = {"userPreferredIndustries":preferedIndustry,"userPreferredRoles":preferedRoles}
            for i in multipleCandidateExperience:
                del i["responsibilities"]
            frontend_auto_populations={"about":about,"responsibilities":responsibilities,"multipleCandidateExperience":multipleCandidateExperience}

            update_response_frontend_auto_populations = update_frontend_auto_populations_in_dynamodb(table_name, partition_key_value, sort_key_value,frontend_auto_populations)
            otherSocialPlatForms = correct_https_in_links(otherSocialPlatForms)
            update_otherSocialPlatForms_in_dynamodb(table_name, partition_key_value,otherSocialPlatForms)
            update_pref_section_in_dynamo(table_name, partition_key_value, sort_key_Preff, Prefered_section)       #####
            education = completion_text["education"]

            for i in education:
                update_Education_in_dynamo(table_name, partition_key_value,i)
                print('loop Started')
            print(multipleCandidateExperience)

            
            

            end_time = time.time()
            print(f'Step 3 cvExtractparsed saved in dynamo with time took  frontend_auto_populations and otherSocialPlatForms :- {end_time-start_time}')
            update_isCvExtracted_in_dynamodb(table_name, partition_key_value, sort_key_value,True)
            # prompt = (
            #     'Human:\n'
            #     f'Find below details from:\n\n{json.dumps(processed_text, indent=2)}\n\n'
            #     'Name:\nEmail:\nExperience in year:\nAchievements:\nTechnical skills:'
            #     '\nSoft skills:\nCore skills:\nEducation:\nIndustry experience:\nResponsibilities:'
            #     '\nAchievements against responsibility:\nCertifications:\nStrength:\n'
            #     'Experience type (leadership, Mid management, Senior management, Team lead, Individual contributor):'
            #     '\nTeam handling experience:\nIndustry type(B2B, D2C, C2C, B2C):\n\nAssistant:\" turn'
            # )

            # content = invoke_model_with_backoff(prompt)
            # print_completion_text(content)
                
            # completion_text = extract_data_nova(content)
            # print_completion_text(completion_text)
            # print("Processed completion_text: ", completion_text)
            # # Update the DynamoDB item with the processed text
            # update_response = update_cv_extract_in_dynamodb(table_name, partition_key_value, sort_key_value, completion_text)
            # end_time = time.time()
            # print(f'Step 4 CvExtract is saved in dynamo time took :- {end_time-start_time}')
            
            
            update_sqs_queue(partition_key_value,ID)
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'CV extract updated successfully','links_from_pdf':links_from_pdf})
                # 'body':json.dumps({"coreSkills":core_skills , "technicalSkills": technical_skills, 
                # "userPreferredDepartments": Prefered_departments,"userPreferredIndustries":preferedIndustry,
                # "userPreferredlocations":preferedIndustry,"userPreferredRoles" :preferedRoles})
            }


        else:
            return {
                'statusCode': 404,
                'body': 'Item not found'
            }


# if __name__ == "__main__":
    # event = {"companyId": "01JWAQF1G96E0SE9XHXSFGHNWW", 
    # "jobId": "01K636AKJRB7QZYB0KF9ASDY08", 
    # "agencyUserId": "71WFYNMG3HE02CK2EE0TAF04MX",
    # "candidateParsedCvAwsS3FileName": "01KCJVGXFCWHVZ1ZW3KKCSTR4H.pdf"}
    # event = {"event": "SOURCE_TYPE_REFRESH_CV", "candidateParsedCvAwsS3FileName": "01KH64VAN998DYYGPR9G6KQ3XW.pdf", "cvAwsS3FilePath": "companies/01JJVRPHNENTTFFF7M3N6HEQ38/bulk-cvs/01KH64V8YAF4R40RX96SKV02JE", "cvAwsS3ResourceType": "BULK_CVS", "cvAwsS3BucketName": "worko-corporate-dev"}

    # event = {
    # "companyId": "01JWAQF1G96E0SE9XHXSFGHNWW",
    # "jobId": "01K7Z7RM97J7V8E4059KQ1D2Z6",
    # "candidateParsedCvAwsS3FileName": "01KH1XG7Y8JJHZ65CAX8ZPERCQ.pdf",
    # "cvAwsS3ResourceType": "CAND_SUBMIT_CV_JOB"
    #     }
    # # example_path = "s3://worko-app-dev/candidate-submit-cvs/companies/01JWAQF1G96E0SE9XHXSFGHNWW/jobs/01K7Z7RM97J7V8E4059KQ1D2Z6/cvs/01KH1XG7Y8JJHZ65CAX8ZPERCQ.pdf"
    # lambda_handler(event, None)
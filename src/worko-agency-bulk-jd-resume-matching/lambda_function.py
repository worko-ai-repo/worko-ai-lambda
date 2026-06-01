import boto3
from google.cloud import firestore
from google.oauth2 import service_account
import requests
from datetime import datetime, timezone
import random
import time
import os
import json
from typing import List, Tuple, Dict, Any, Optional, Union
from botocore.exceptions import ClientError
from urllib.parse import unquote_plus
# iac deploy 11
dynamodb = boto3.resource('dynamodb')
import sys
from pathlib import Path

if __name__ == "__main__":
    shared_layer_path = Path(__file__).parent.parent / "shared-core-layer"
    sys.path.insert(0, str(shared_layer_path))
    
# from ai_clients import AzureOpenAIClient
from ai_clients.gcp_client import GeminiClient
from database_adapters import FirestoreManagerAgency
from utils import *
from scoring.get_scoring import get_score

def jd_resume_matching_agency(job_desc, processed_text, cv_extract, cv_extracted_parsed,gcp_models,update_doc_id,agencyBulkJdResumeId):
    region ="ap-south-1"
    account_id = get_account_id()
    queue_name = 'worko-corp-app-event-queue'
    queue_url = f"https://sqs.{region}.amazonaws.com/{account_id}/{queue_name}"
    # Determine if job is non-technical
    print("*****************************Job Description******************************************")
    # print("jd:-", job_desc)
    prompt = (
        f"Analyze the following job description and classify it as either 'Technical' or 'Non-Technical':\n"
        f"Job Description:\n"
        f"{job_desc}\n"
        f"Considerations for classification:\n"
        f"- Technical roles typically involve programming, engineering, data analysis, or IT skills\n"
        f"- Non-Technical roles typically focus on business, management, sales, or operations\n"
        f"- Respond with only one word: 'Technical' or 'Non-Technical'"
        )
          
    # content = OpenAIClient.invoke_model_with_backoff(prompt, Task= "Check Tech or Non-Tech JD", want_json=False)
    content = gcp_models[0].invoke_model_with_backoff(prompt,Task= "Check Tech or Non-Tech JD" ,want_json=False)
    print("Checking the Tech or non-tech jd",content)
    
    # Initialize the variable to store the Technical or Non Technical
    found_text = ""
    
    position = content.find("Non-Technical")

    if position != -1:
        found_text = content[position:position+len("Non-Technical")]
        print("The text '{}' is present.".format(found_text))
    else:
        print("The text 'Non-Technical' is not present.")
    
        # Initialize steps to avoid unassigned reference
    steps = []
    
    try:

        final_completion_text = ""
        rejection_feedback = ""
        # overall_matching_score = 0
        emailFeedback = ""
        overall_Analysis=""

        retry_on_scoring_fails = 3
        for _ in range(retry_on_scoring_fails):
            try:
                matching_score_obj = get_score(processed_text,job_desc,gcp_models)
                print("overall matching score ", matching_score_obj)
                overall_matching_score = matching_score_obj["overall_matching_score"]
                overall_matching_score = int(round(overall_matching_score))
                break
            except Exception as e:
                print(f"Error occurred while fetching scoring: {e}")
                time.sleep(2)  # Wait before retrying
        else:
            print("Failed to fetch scoring after multiple attempts.")


        
        

        # Generate feedback for rejection if score < 70
        if 1 <= overall_matching_score < 70:
            prompt = (f"candidate profile : {processed_text}, job requirements : {job_desc}\n"
                f"Analyze why this candidate scored low against job requirements highlight. Return response in exact JSON format:\n"
                f"{{\n"
                f"  \"RecruiterNote\": \"2–3 sentences summarizing overall fit, written in clear recruiter-friendly language.\",\n"
                f"  \"Strengths\": [\n"
                f"    \"Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                f"    \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                f"  ],\n"
                f"  \"Areas of Concern\": [\n"
                f"    \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                f"  ]\n"
                f"}}\n"
                f"Strict Rule 1 :\n"
                f"1. RecruiterNote → Concise 3–5 line factual summary of candidate fit and readiness.\n"
                f"2. Every point in Strengths and AreasOfConcern must be a direct Job Description vs Candidate comparison only.\n"
                f"   - If requirement not present in JD or Candidate Profile → do not mention.\n"
                f"   - If requirement in JD but missing in Candidate Profile → flag under AreasOfConcern.\n"
                f"   - If requirement in JD and fully/over met → include under Strengths.\n"
                f"3. Limit: max 3 strengths and 2 concerns (5 points total).\n"
                f"4. Each point must be 15–25 words, sharp, factual, recruiter-ready.\n"
                f"5. Treat missing info as missing — never assume.\n"
                f"6. Apply Special Mentions only if explicitly visible in Candidate Profile:\n"
                f"   - Unemployed 12+ months.\n"
                f"   - Frequent job changes (<1 year).\n"
                f"   - Experience significantly above requirement (mark as strength).\n"
                f"Strict Rule 2 :\n"
                f"In RecruiterNote → Never use speculative phrases like 'resume shows' or 'appears to have'. State facts directly.with calling candidate. [name of candidate] have 15+ experience in...\n"
                f"Strict Rule 3 :\n"
                f"Requirements:\n"
                f"- Total 3 items focusing on critical gaps that caused rejection.\n"
                f"- Each detail must be a direct 15–25 word statement starting with 'Candidate has no...' or 'Candidate lacks...'\n"
                f"- Headings should be meaningful and aligned with the issue (e.g., 'Missing Required Certification', 'Insufficient Industry Experience').\n"
                f"- Never start headings with 'Candidate has no...' — that's for the details.\n"
                f"- Focus only on missing mandatory requirements from the JD.\n"
                f"- Flag: Educational gaps, experience above requirement, missing technical skills, insufficient industry experience, absent certifications, lacking leadership/management, career inconsistencies.\n"
                f"- Special Mentions: Extended unemployment 12+ months, frequent short tenure roles <1 year.\n"
                f"- Location: Only mention if candidate explicitly states inability to work in required location.\n"
                f"- Language: Only mention if candidate explicitly lacks required language skills.\n"
                f"- Tone: Objective, professional, decision-focused.\n"
                f"- Omit detail field if heading itself is self-explanatory.\n"
                f"Strict Rule 4:\n"
                f" Never use speculative phrases like 'resume shows' or 'appears to have' — state facts directly with calling candidate name.\n"
            )

            content = gcp_models[0].invoke_model_with_backoff(prompt,Task= "Rejection for 1 <= overall_matching_score < 70:")
            # content = OpenAIClient.invoke_model_with_backoff(prompt,Task= "Rejection for 1 <= overall_matching_score < 70:" )
            completion_text_rejection = json.dumps(content)

            print("***************************************  1 <70 *********************************************")
            print_completion_text(completion_text_rejection)
            rejection_feedback = completion_text_rejection

            #generate email feedback focusing on positives
            if overall_matching_score > 40:
                prompt = (f"{final_completion_text}, {completion_text_rejection}\n"
                         f"Based on the above content, write a one-line summary in 20-25 words that highlights ONLY the positive qualities and strengths that make this candidate suitable for the job.\n"
                         f"Focus exclusively on positive aspects - exclude any negative feedback or criticisms.")
                content = gcp_models[0].invoke_model_with_backoff(prompt,Task= "Email feedback for 1 <= overall_matching_score < 70:",want_json=False)
                # emailFeedback = OpenAIClient.invoke_model_with_backoff(prompt,Task= "Email feedback for 1 <= overall_matching_score < 70:",want_json=False)
                print("feedback_for_email:-",emailFeedback)

        # Generate positive feedback for  if score >=70
        elif overall_matching_score >= 70:
            prompt = (f"You are an expert recruiter. Your only task is to compare the candidate profile against the job description."
                        f"Only use details explicitly stated in the provided text. Do not infer, assume, or invent information."
                        f"Input:"
                        f"- Candidate Profile: {processed_text}"
                        f"- Job Description: {job_desc}"
                        f"Output:"
                        f"Provide recruiter feedback in JSON format with three keys: \"RecruiterNote\", \"Strengths\", and \"Areas of Concern\"."
                        f"Format Example:"
                        f"{{\n"
                        f"  \"RecruiterNote\": \"2–3 sentences summarizing overall fit, written in clear recruiter-friendly language.\",\n"
                        f"  \"Strengths\": [\n"
                        f"    \"Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                        f"    \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                        f"  ],\n"
                        f"  \"Areas of Concern\": [\n"
                        f"    \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                        f"  ]\n"
                        f"}}\n"
                        f"Strict Rules:"  
                        f"1. **RecruiterNote** → A concise 3–5 line summary of candidate fit, overall impression, and readiness for the role."  
                        f"2. Every point in \"Strengths\" and \"Areas of Concern\" must be a **direct Job Description vs Candidate comparison** only."  
                        f"   - If requirement is not present in Job Description or Candidate Profile, do not mention it."  
                        f"   - If requirement is in Job Description but missing in Candidate Profile, flag it under concerns."  
                        f"   - If requirement is in Job Description and fully/over met in Candidate Profile, add it under strengths."  
                        f"3. Limit to maximum **3 strengths** and **2 concerns** (total 5 points)."  
                        f"4. Each point must be **15–25 words**, sharp, factual, and recruiter-ready."  
                        f"5. Treat missing info as missing — never assume or generalize."  
                        f"6. Apply Special Mentions only if explicitly visible in Candidate Profile:"  
                        f"   - Unemployed for 12+ months."  
                        f"   - Frequent job changes (<1 year)."  
                        f"   - Experience significantly above requirement (mark as strength)." 
                        f"7.Use natural, direct language that sounds human-written, not AI-generated\n"
                        f"- Flag: Educational qualification gaps\n"
                        f"- Flag: Experience is higher than the required experience for the job\n"
                        f"- Flag: Critical technical skills missing\n"
                        f"- Flag: Industry experience insufficient\n"
                        f"- Flag: Required certifications absent\n"
                        f"- Flag: Leadership/management experience lacking when required\n"
                        f"- Flag: Career progression inconsistencies\n"
                        f"- SPECIAL MENTION: Extended unemployment periods (12+ months)\n"
                        f"- SPECIAL MENTION: Pattern of short tenure roles (<1 year)\n"
                        f"- LOCATION RULE: Only mention location concerns if candidate explicitly states inability to work from required location in resume. If location not mentioned, assume candidate is willing to work from any location.\n"
                        f"- LANGUAGE RULE: Only mention language deficiency if candidate explicitly lacks required languages in resume. If languages not mentioned, assume candidate has required language skills.\n"
                        f"- Tone should be objective, professional, and decision-focused for HR evaluation\n" 
                        
                        f"8. Focus only on **Job Description requirements matched with candidate evidence** — highlight why candidate deserves shortlist."  
                        f"9. Keep summary **crisp, keyword-heavy**, pulling exact terms from Job Description and Job Description."  
                        f"10. if you say skills matches tell which particular skill which is direct from Candidate Profile and Job Description, if you say experience matches then tell which particular experience matches."
                        f"11. Never say anything in a broad perspective just porvide all the exact reasons from Candidate Profile that why this is a ideal candidate."
                        f"12. Do not mention communication skills, cultural fit, or location unless explicitly present in both Job Description and Resume."  
                        f"13. Never use speculative phrases like 'resume shows' or 'appears to have' — state facts directly with calling candidate name."
                        f"15. **EXACT WORDING RULE**: Only use terminology explicitly stated in the resume/Job Description. Never generalize specific implementations into broader industry terms."
                        f"16. **NO DOMAIN INFERENCE**: Do not infer industry expertise from individual projects or features. State only the specific technologies/projects mentioned."
                        f"17. **FACT-CHECK REQUIREMENT**: Before including any point, verify the exact phrase exists in either the Job Description or Candidate Profile text."
                        f"18. **GRANULAR SPECIFICITY**: When mentioning experience, reference the exact role/company where it was gained, not as broad industry background."  
                        f"19. Output format must be **valid JSON only**, no text outside JSON."   
	
                    )
            content = gcp_models[0].invoke_model_with_backoff(prompt,Task= "Score feedback for >70")
            # content = OpenAIClient.invoke_model_with_backoff(prompt,Task= "Score feedback for >70")
            completion_text_approval = json.dumps(content)

            print("***************************************   >70 *********************************************")
            print_completion_text(completion_text_approval)
            final_completion_text = completion_text_approval

            prompt = (f"{final_completion_text}\n"
                     f"Based on the above content, write a one-line summary in 20-25 words that highlights ONLY the positive qualities and strengths that make this candidate suitable for the job.\n"
                     f"Focus exclusively on positive aspects - exclude any negative feedback or criticisms.")

            emailFeedback = gcp_models[0].invoke_model_with_backoff(prompt, Task="Email Feedback",want_json=False)
            # emailFeedback = OpenAIClient.invoke_model_with_backoff(prompt, Task="Email Feedback",want_json=False)
            print("feedback_for_email:-",emailFeedback)
            
        elif overall_matching_score == 0:
            rejection_feedback = "We encountered an error while processing. Please try again after some time"
        
        if overall_matching_score > 90:
            print("******Potential Issue******:", overall_matching_score)
            overall_matching_score = 90

        update_data = {
            "updatedAt": datetime.now().isoformat(),
            "cvExtract": cv_extract,
            "matchingScore": overall_matching_score,
            "jdMatchErrorCode": 200,
            "jdMatchErrorDesc": "Score generated successfully",
            "scoreDetails": final_completion_text,
            "scoreFetchedDate": datetime.now().isoformat(),
            "rejectionFeedbackBySystem": rejection_feedback,
            "processingStatus": "COMPLETED"
        }   # ask need emai feedback or not
        processingStatus = "COMPLETED"
        update_collection_name = "agencyBulkJdResumes"
        print("updating firestore document after scoring with data :--",update_data)
        DBManager.update_firestore_document_with_scoring_data(update_collection_name, update_doc_id, update_data,processingStatus)
        # send sqs after score calculation
        update_sqs_queue_agency(queue_url,agencyBulkJdResumeId)
    except Exception as e:
        print(f"An error occurred: {e}")
        # update_cv_extract_in_dynamodb(table_name, partition_key_value, sort_key_prefix, str(e) , 251, -1)
        return {"statusCode": 500, "body": {"error": str(e)}}
    
    return {"statusCode": 200, "body": 
        {"Overall Matching Score": overall_matching_score}
    }
gcp_credentials = None
gcp_credentials_firstore = None
def lambda_handler(event, context):
    global gcp_credentials, gcp_credentials_firstore
    print(f"got a event : -  {event}") 
    global DBManager,update_doc_id
    # Get environment
    env=os.environ.get("ENVIRONMENT", "dev")
    # secret_name ="AZURE-openai-secret-" +env
    # AZURE_openai_secret = get_secret(secret_name) 

    #set variables for sqs
    region ="ap-south-1"
    account_id = get_account_id()
    queue_name = 'worko-corp-app-event-queue'
    queue_url = f"https://sqs.{region}.amazonaws.com/{account_id}/{queue_name}"

    try:
        # Parse S3 event
        s3_event = event['Records'][0]['s3']
        bucket_name = s3_event['bucket']['name']
        object_key = unquote_plus(s3_event['object']['key'])
        original_key = s3_event['object']['key']
        agencyBulkJdResumeId = original_key.split("/")[-1].split(".")[0]
        
        print(f"Processing S3 object: {bucket_name}/{object_key}")
        
        # Extract IDs from S3 path: agencies/{agencyUserId}/bulk-cvs/{agencyBulkJdId}/{filename}
        path_parts = object_key.split('/')
        if len(path_parts) < 5:
            raise ValueError(f"Invalid S3 path structure: {object_key}")
            
        agency_user_id = path_parts[1]
        agency_bulk_jd_id = path_parts[3]
        filename = path_parts[4]
  
        
        # Download PDF from S3
        s3_client = boto3.client('s3')
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
            pdf_data = response['Body'].read()
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                print(f"S3 object not found: {bucket_name}/{object_key}")
                # Try with original encoded key
                
                print(f"Trying original key: {bucket_name}/{original_key}")
                response = s3_client.get_object(Bucket=bucket_name, Key=original_key)
                pdf_data = response['Body'].read()
            else:
                raise
        
        # Extract text from PDF
        resume_text = extract_text_from_pdf(pdf_data)
        processed_text = clean_text(resume_text)
        # print(AZURE_openai_secret)
        # OpenAIClient = AzureOpenAIClient(AZURE_openai_secret)

        # azure_openai_secret_name = "AZURE-openai-secret-multimodel-"+env
        # azure_openai_secret = get_secret(azure_openai_secret_name)
        # gpt4 = AzureOpenAIClient(azure_openai_secret,model="gpt-4o")
        # gpt_models = [gpt4]

        if not gcp_credentials:
            GCP_secret_name ="GCP-aiplatform-secrect-"+env
            gcp_credentials = get_secret(GCP_secret_name)
        else:    
            print("Using cached GCP credentials")
        
        if not gcp_credentials_firstore:
            gcp_credentials_secrect_name= "GCP-firestore-secret-"+env
            gcp_credentials_firstore = get_secret(gcp_credentials_secrect_name)

        gcp = GeminiClient(gcp_credentials,env,model="gemini-3.5-flash")
        gcp_models = [gcp] 

        cv_extract, cv_extracted_parsed = process_cv(processed_text,gcp_models)
        print(f"Successfully processed resume: {processed_text[:200]}..")
        # GCP_secret_name = "GCP-firestore-secret-"+env
        GCP_DATABASE_NAME = "worko-corp-db-" +env 
        
        DBManager = FirestoreManagerAgency(gcp_credentials_firstore,GCP_DATABASE_NAME)

        update_data = {
            "updatedAt": datetime.now().isoformat(),
            "status" :"completed",
            "cvExtractedParsed": {
                "candidateName": "",
                "candidateEmail": "",
                "candidatePhoneNumber": "",
                "candidateNumber": 0,
                "candidatePhoneCountryCode": 0,
                "candidateCurrentCompany": "",
                "candidateCurrentDesignation": "",
                "candidateExperience": 0,
                "candidateTotalYOE": 0,
                "candidateRelevantYOE": 0,
                "candidateCurrentCTC": 0,
                "candidateExpectedCTC": 0,
                "candidateNoticePeriod": 0,
                "candidateLocation": "",
                "candidateReadyToRelocate": False,
                "isNoticePeriodNegotiable": False,
                "coreSkills": [],
                "technicalSkills": [],
                "userPreferredDepartments": [],
                "userPreferredIndustries": [],
                "userPreferredlocations": [],
                "userPreferredRoles": []
            },
            "cvExtract": resume_text,
            "matchingScore": 0,
            "jdMatchErrorCode": 200,
            "jdMatchErrorDesc": "",
            "scoreDetails": "",
            "scoreFetchedDate": datetime.now().isoformat(),
            "rejectionFeedbackBySystem": ""
        }
        # Get the Jobdescription from firstore
        
        get_collection_name ="agencyBulkJds"
        item = DBManager.get_document_firstore(get_collection_name, agency_bulk_jd_id)
        if item:

            #exclud agencyRegisteredEmail,companyId,id for cv-jd matching
            print(f"job description object fetched from firestore: {str(item)[:1000]}...")
            jobTitle = item.get("jobTitle","")
            experienceRange = item.get("experienceRange","")
            technicalSkills = item.get("technicalSkills","")
            jobLocation = item.get("jobLocation","")
            softSkills = item.get("softSkills","")
            coreSkills = item.get("coreSkills","")
            industryPreferences = item.get("industryPreferences","")
            jobDescription = item.get("jobDescription","")
            mustHaveSkills = item.get("mustHaveSkills","")
            goodToHaveSkills = item.get('goodToHaveSkills')
            mustNotHaveSkills = item.get("mustNotHaveSkills","")
            job_desc = f"{jobDescription}\nMust Have Skills: {mustHaveSkills}\nGood To Have Skills: {goodToHaveSkills}\nMust Not Have Skills: {mustNotHaveSkills}"
            job_desc = clean_text(job_desc)
            print("job_desc--------",job_desc)
        else:
            raise ValueError(f"Job description document not found for ID: {agency_bulk_jd_id}")
      
    
        # update data in firestore with empty values and status in progress
        update_doc_id = filename.replace('.pdf', '')  # review this line once doc is correct or not
        print("update_doc_id ::----",update_doc_id)
        # return update_doc_id
        update_collection_name = "agencyBulkJdResumes"
        processingStatus = "IN-PROGRESS"
        print("updating firestore document before scoring with IN-PROGRESS status and cv cv_extracted_parsed :--",cv_extracted_parsed)
        DBManager.update_firestore_document_with_scoring_data(update_collection_name, update_doc_id, cv_extracted_parsed,processingStatus)

        score = jd_resume_matching_agency(job_desc, processed_text, cv_extract, cv_extracted_parsed,gcp_models,update_doc_id,agencyBulkJdResumeId)
        return {
            "statusCode": 200,
            "body": json.dumps({
                # "message": score,
                "job_description": job_desc,
                "resume_text": resume_text
            })
        }
        
    except Exception as e:
        print(f"Error processing resume-jd-matching triggring failure sqs: {str(e)}")
        
        # # Define the SQS queue URL

        update_sqs_queue_agency(queue_url,agencyBulkJdResumeId)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e)
            })
        }
    
if __name__ == "__main__":
    event = {
        "Records": [
            {
            "eventVersion": "2.1",
            "eventSource": "aws:s3",
            "awsRegion": "ap-south-1",
            "eventTime": "2024-01-15T10:30:00.000Z",
            "eventName": "s3:ObjectCreated:Put",
            "s3": {
                "s3SchemaVersion": "1.0",
                "configurationId": "lambda-trigger",
                "bucket": {
                "name": "worko-app-dev",
                "arn": "arn:aws:s3:::worko-app-dev"
                },
                "object": {
                "key": "agencies/712EEWMW5HE3NE9K8DGRXXTR53/bulk-cvs/01KD2W640HJS9PZNJMHNH6YE6K/01KD2WDTS7RZKEJ6QFK87MDC0K.pdf",
                "size": 245760,
                "eTag": "d41d8cd98f00b204e9800998ecf8427e"
                }
            }
            }
        ]

    }
    lambda_handler(event,None)
    

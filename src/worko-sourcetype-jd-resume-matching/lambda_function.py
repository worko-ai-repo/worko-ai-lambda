import boto3
import fitz
from prompts import *
import requests
import random
import os
import time
import json
from decimal import Decimal
from typing import List, Tuple, Dict, Any, Optional, Union
from boto3.dynamodb.conditions import Key, Attr
import re
from botocore.exceptions import ClientError
from utils import get_secret, AzureOpenAIClient
dynamodb = boto3.resource('dynamodb')
from google.cloud import firestore
from google.oauth2 import service_account
from datetime import datetime, timezone

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

def query_dynamodb_item_with_index_sk_prefix(table_name, index_name, partition_key_value, sort_key_prefix):
    table = dynamodb.Table(table_name)
    response = table.query(
        IndexName=index_name,
        KeyConditionExpression=boto3.dynamodb.conditions.Key('GSI1PK').eq(partition_key_value) &
                               boto3.dynamodb.conditions.Key('GSI1SK').eq(sort_key_prefix)
    )
    items = response.get('Items')
    if items:
        return items[0]
    return None

def has_key_elements(text, key_elements, threshold):
    present_elements = sum(1 for element in key_elements if element.lower() in text.lower())
    return present_elements >= threshold



             
def get_scoring_prompts(department,experience):
    if department=="Non-Technical":
        if experience=="superior":
            prompt =Non_Technical_superior
        if experience=="senior":
            prompt =Non_Technical_senior
        if experience=="junior":
            prompt =Non_Technical_junior
        if experience=="fresher":
            prompt =Non_Technical_fresher   

    elif department=="Technical":
        if experience=="superior":
            prompt =Tech_superior
        if experience=="senior":
            prompt =Tech_senior
        if experience=="junior":
            prompt =Tech_junior
        if experience=="fresher":
            prompt =Tech_fresher
    else:
        prompt =" give an error in json format"
    return prompt 

def ensure_decimal(value: Union[float, int, str, Decimal, None]) -> Optional[Decimal]:

    """Convert numeric value to Decimal if it isn't already."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))

def create_prompt(cv_extract, job_desc, step ):
    return f'Human:\nResume:\n{cv_extract}\nJob Description:\n{job_desc}\n{step}'

def extract_score_from_OpenAI_response(response):
    """
    Extracts score from different response formats, including partial/incomplete JSON.
    Handles JSON objects, JSON strings, mixed text/JSON responses, and numeric values.
    
    Args:
        response (str, dict, int, or float): The response containing score information
        
    Returns:
        float or int: The extracted score value, or None if not found
    """
    temp_score = None
    
    try:
        # If response is already a numeric value (int or float), return it directly
        if isinstance(response, (int, float)):
            return response
        
        # If response is already a dictionary
        if isinstance(response, dict):
            temp_score = response.get('score')
            return temp_score if temp_score is not None else None
        
        # If response is a string, try different parsing approaches
        if isinstance(response, str):
            # Method 1: Simple regex pattern for "score": value (most reliable for partial JSON)
            score_pattern = r'"score":\s*([0-9]+\.?[0-9]*)'
            score_match = re.search(score_pattern, response)
            if score_match:
                temp_score = float(score_match.group(1))
                return temp_score
            
            # Method 2: Try to parse as direct JSON (only if it looks complete)
            try:
                # Only try JSON parsing if the string looks like complete JSON
                stripped = response.strip()
                if stripped.startswith('{') and stripped.endswith('}'):
                    data = json.loads(stripped)
                    # Handle case where parsed data is a number
                    if isinstance(data, (int, float)):
                        return data
                    # Handle case where parsed data is a dict
                    if isinstance(data, dict):
                        temp_score = data.get('score')
                        return temp_score if temp_score is not None else None
            except (json.JSONDecodeError, ValueError):
                pass
            
            # Method 3: Extract complete JSON blocks from mixed content
            # Look for complete JSON objects that contain "score"
            json_pattern = r'\{[^{}]*"score"[^{}]*\}'
            json_matches = re.findall(json_pattern, response, re.DOTALL)
            
            for match in json_matches:
                try:
                    data = json.loads(match)
                    if isinstance(data, dict) and 'score' in data:
                        temp_score = data['score']
                        if isinstance(temp_score, (int, float)):
                            return temp_score
                except (json.JSONDecodeError, ValueError):
                    continue
            
            # Method 4: Look for larger complete JSON blocks
            # Find JSON blocks that might contain score in nested structure
            large_json_pattern = r'\{(?:[^{}]|\{[^{}]*\})*\}'
            large_matches = re.findall(large_json_pattern, response, re.DOTALL)
            
            for match in large_matches:
                try:
                    # Only try parsing if it looks like complete JSON
                    if match.count('{') == match.count('}'):
                        data = json.loads(match)
                        if isinstance(data, dict):
                            temp_score = data.get('score')
                            if isinstance(temp_score, (int, float)):
                                return temp_score
                except (json.JSONDecodeError, ValueError):
                    continue
            
            # Method 5: Try to fix partial JSON by finding the score field specifically
            # Look for patterns like: "score": 15, even in incomplete JSON
            partial_score_pattern = r'"score":\s*([0-9]+\.?[0-9]*)[,\s}]?'
            partial_match = re.search(partial_score_pattern, response)
            if partial_match:
                try:
                    temp_score = float(partial_match.group(1))
                    return temp_score
                except ValueError:
                    pass
    
    except Exception as e:
        print(f"Error extracting score: {e}")
        print(f"Response type: {type(response)}")
        print(f"Response content: {str(response)[:200]}...")  # First 200 chars for debugging
        return None
    
    return temp_score

def query_dynamo_for_job_feedbacks(partition_key ,table_name='worko',sort_key_prefix='ID#'):

    partition_key = f'JOB#ID#{partition_key}'
    dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')
    table = dynamodb.Table('worko-job-app')
    index = 'GSI3'
    

    response = table.query(
        IndexName=index,
        KeyConditionExpression=Key('GSI3PK').eq(partition_key),
        FilterExpression=Attr('rejectedByUserId').exists() , # Sort descending # Specify which attributes to return
        ProjectionExpression='rejectedByUserId.reason,rejectedByUserId.userComment,PK,SK'
    )
    Salary_mismatched,Industry_mismatched,Educational_mismatched,Experience_mismatched,Other_mismatched=[],[],[],[],[]
    feedback = []
    if response["Items"]:
        for item in response["Items"]:
            item["rejectedByUserId"]["reason"]
            output ={}
            PK = item['PK']
            User_data = query_dynamodb_item_with_sk_prefix(table_name, PK, sort_key_prefix)
            ctc = User_data.get("CTC","")
            YOE = User_data.get("YOE","")

            output[f"YOE"] = YOE
            output[f"CTC"] = ctc
            output[f"PK"] = PK
            output[f"reason"] = item["rejectedByUserId"]["reason"]
            output[f"recruiterComment"] = item["rejectedByUserId"]["userComment"]
            if output[f"reason"]=="Salary Expectation Mismatch":
                Salary_mismatched.append(output)
            if output[f"reason"]=="Not From The Required Industry ":
                Industry_mismatched.append(output)
            if output[f"reason"]=="Educational Background Expectation Mismatch":
                Educational_mismatched.append(output)
            if output[f"reason"]=="Experience Expectation Mismatch":
                Experience_mismatched.append(output)
            if output[f"reason"]=="other":
                Other_mismatched.append(output)
            feedback.append({"reason":output[f"reason"],"recruiterComment" : output[f"recruiterComment"]})
          

        detailed_feedback = {"Salary_mismatched":Salary_mismatched,"Industry_mismatched":Industry_mismatched,
                "Educational_mismatched":Educational_mismatched,"Experience_mismatched":Experience_mismatched,
                "Other_mismatched":Other_mismatched}

        return feedback,detailed_feedback
    else:
        return False,False

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

def query_dynamo_for_candidate_feedbacks(partition_key='USR#EML#shaukt1998+34@gmail.com'):
    dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')
    table = dynamodb.Table('worko-job-app')
    

    response = table.query(
        KeyConditionExpression=Key('PK').eq(partition_key),
        FilterExpression=Attr('rejectedByUserId').exists() , # Sort descending # Specify which attributes to return
        ProjectionExpression='rejectedByUserId.reason,rejectedByUserId.userComment'
    )
    if response["Items"]:
        output = {}
        for i, item in enumerate(response["Items"], start=1):
            output[f"reason{i}"] = item["rejectedByUserId"]["reason"]
            output[f"recruiterComment{i}"] = item["rejectedByUserId"]["userComment"]
        return output
    else:
        return False

def check_exp_ctc(input_data):
    # Convert all numeric inputs to float safely
    cv_ctc = float(input_data["cv_ctc"])
    cv_exp = float(input_data["cv_exp"])

    jd_ctc = input_data["jd_ctc"]
    jd_exp = input_data["jd_exp"]

    jd_ctc_min = float(jd_ctc["min"])
    jd_ctc_max = float(jd_ctc["max"])
    jd_exp_min = float(jd_exp["min"])
    jd_exp_max = float(jd_exp["max"])
    ECTC = cv_ctc*1.25

    result = {"ctc": False, "experience": False, "Explanation": False}
    explanations = []  # collect multiple messages
    min_threshold_ctc = jd_ctc_min*0.7
    max_threshold_ctc = jd_ctc_max*0.6
    
    if jd_exp_max<=4:
        print(f'exp less than 4 jd exp {jd_exp_max} cv exp {cv_exp}')
        if cv_exp>(jd_exp_max*1.6): #(overqualified exp)
            print("statement 1")
            msg = (
                f"You are overqualified for this role in terms of experience. Your total experience is "
                f"{cv_exp} years but this role expected maximum {jd_exp_max} years of experience."
            )
            result["experience"] = "above"
            explanations.append(msg)
        

    
    elif jd_exp_min*0.3>=3:      # if  30% of minimum exp is greater than 3   (underqualified exp)
        print("Min exp 30% is Greater than 3")
        print("1")
        
        if jd_exp_min-cv_exp>3: # check if candidate exp is 3 years less than min_exp_jd
            print("statement 2")
            print(f"jd_mim {jd_exp_min} cv exp {cv_exp}")
            # print("under qualified rejected")
            msg = (
                f"You are underqualified in terms of experience. Your total experience is "
                f"{cv_exp} years but this role expected minimum of {jd_exp_min} years of experience."
            )
            result["experience"] = "below"  # True
            explanations.append(msg)
            
    elif cv_exp < (jd_exp_min * 0.7):
        print("statement 3")
        msg = (
            f"You are underqualified in terms of experience. Your total experience is "
            f"{cv_exp} years but this role expected minimum of {jd_exp_min} years of experience."
        )
        result["experience"] = "below" #True
        explanations.append(msg)

            
    if jd_exp_max*0.4>4:  # if  40% of maximum exp is greater than 4  (overqualified exp)
        print("max exp 40% is Greater than 4")
        
        
        if cv_exp - jd_exp_max>4: # check if candidate exp is 4 years greater than max_jd_exp
            print(f"jd_mx {jd_exp_max} cv exp {cv_exp}")
            print("statement 4")
            msg = (
                f"You are overqualified for this role in terms of experience. your total experience is "
                f"{cv_exp} years which exceeds job’s maximum required experience is {jd_exp_max} years."
            )
            result["experience"] = "above" #True
            explanations.append(msg)
    elif cv_exp > jd_exp_max * 1.4 and jd_exp_max>4 :
        print("statement 5")
        msg = (
            f"You are overqualified for this role in terms of experience. your total experience is "
            f"{cv_exp} years which exceeds job’s maximum required experience is {jd_exp_max} years."
        )
        result["experience"] = "above" #True
        explanations.append(msg)

        
    if ECTC > jd_ctc_max * 1.2 and (jd_ctc_max * 1.2)>10 :        # CTC logic
        print("statement 6")
        msg = (
            f"You are overqualified in terms of compensation, as your current CTC is "
            f"{cv_ctc} LPA and the maximum offered by this role is {jd_ctc_max} LPA."
        )
        result["ctc"] = "above" #True
        explanations.append(msg)
        
    if ECTC > jd_ctc_max * 1.3 and (jd_ctc_max * 1.2)<10:        # CTC logic
        print("statement 7")
        msg = (
            f"You are overqualified in terms of compensation, as your current CTC is "
            f"{cv_ctc} LPA and the maximum offered by this role is {jd_ctc_max} LPA."
        )
        result["ctc"] = "above" #True
        explanations.append(msg)

        # ---- Combine Explanations ----
    if explanations:
        if len(explanations) > 1:
            result["Explanation"] = ", ".join(explanations[:-1]) + " and " + explanations[-1]
        else:
            result['Explanation'] = explanations[0] 
            
    else:
        result["Explanation"] = False

    return result

def print_completion_text(completion_text):
    print("***********************************************************************")
    print(completion_text)
    print("#######################################################################")

def expRejectCheck(inps):
    new_check = {}
    for inp in inps:
        candidate_exp,job_min,job_max= inp["cv_exp"],inp["jd_exp"]["min"],inp["jd_exp"]["max"]
        if candidate_exp < job_min:
            new_check['min']=candidate_exp
            
            print('below')
        if candidate_exp > job_max:
            new_check['max']=candidate_exp
            print('above')
    return new_check

def Registered_user_analysis(jobs_id,jdItem,jdItem_extracted,partition_key_value,processed_text,gpt_models):
    print("found a registered user ... started analysis")
    print("partition_key_value...",partition_key_value)
    table_name="worko"
    sort_key_prefix1 = "ID#"
    Rejection_object = {}
    Rejection_object["candidateFeedbacksNotMet"]=False
    Rejection_object["jobFeedbackNotMet"]=False
    #get feedbacks
    otherRequirements = jdItem.get('otherRequirements')

    ############################################  Feedback  #########################################################################

    number_of_candidate_feedbacks_requirements_MetOrNot=False
    candidate_feedbacks = query_dynamo_for_candidate_feedbacks(partition_key_value)
    
    feedbacks,job_feedbacks = query_dynamo_for_job_feedbacks(jobs_id)
    if feedbacks:
        print(f"feedbacks received for the job {job_feedbacks}")
        # Experience_mismatched = False

        Salary_mismatched = job_feedbacks.get("Salary_mismatched","")
        Industry_mismatched = job_feedbacks.get("Industry_mismatched","")
        Educational_mismatched = job_feedbacks.get("Educational_mismatched","")
        Experience_mismatched = job_feedbacks.get("Experience_mismatched","")
        Other_mismatched = job_feedbacks.get("Other_mismatched","")
        #decide new thresh hold based on past rejection 

        if Experience_mismatched:   #get data if experince is rejected by numbers
            experienceFeedbackNumericData  = []
            for i in Experience_mismatched:
                data = {'cv_exp':i["YOE"],'jd_exp':experienceRange}
                experienceFeedbackNumericData.append(data)
            newThreshHoldF_for_exp = expRejectCheck(experienceFeedbackNumericData) 
        
        prompt = job_feedback_requirements_prompt.format(
        jdItem=jdItem,
        otherRequirements=otherRequirements,
        feedbacks=feedbacks
        )
        requirementsFormFeedback = gpt_models[0].invoke_model_with_backoff(prompt=prompt, Task="AI for feedback extraction")
        RequirementsFromFeedback = requirementsFormFeedback.get("requirements","")
        mandatoryRequirementsFromFeedback = requirementsFormFeedback.get("repeatedmandatoryRequirements","") + requirementsFormFeedback.get("feedbackmandatoryRequirements","")

        if RequirementsFromFeedback:
            prompt = (
            f"You are a world-class HR Expert and Hiring Strategist with 40+ years of experience across technical and non-technical domains.\n\n"
            f"Your job is to perform a *requirement-by-requirement audit* of a candidate’s resume against the job description requirements below.\n\n"
            f"### Objective:\n"
            f"Determine for each requirement in the Job Description whether the candidate meets it or not, based **only** on explicit evidence from the resume text.\n\n"
            f"### Job Description Requirements:\n{RequirementsFromFeedback}\n\n"
            f"### Candidate’s Resume:\n{processed_text}\n\n"
            f"### Evaluation Rules:\n"
            f"1. Be objective, literal, and specific.\n"
            f"   - Match only if the resume clearly shows proof (skills, Domain, experience, education, project, etc.).\n"
            f"   - If the requirement is not found or only implied, classify it as 'no'.\n"
            f"2. Do not assume or infer skills.\n"
            f"   - Example: If JD asks for 'Power BI' and resume mentions 'Excel dashboards', mark it as 'no'.\n"
            f"3. Always match requirement-by-requirement, not overall impression.\n"
            f"4. Extract the exact matching sentence/phrase from resume text in 'partOfcandidateResume'.\n"
            f"   - If nothing matches, set 'partOfcandidateResume': 'null'.\n"
            f"5. Never include extra explanation or commentary outside JSON.\n"
            f"6. The output must be strictly valid JSON — no markdown, no trailing commas, no commentary.\n\n"
            f"7. Be very specific with every requirement; if not met exactly say MetOrNot == no"
            f"### Output Format (Strict JSON Array)\n"
            f"Return an array where each element corresponds to one requirement from the job description:\n\n"
            f"[\n"
            f"  {{\n"
            f'    "Requirements": "<exact requirement text>",\n'
            f'    "MetOrNot": "yes" or "no",\n'
            f'    "partOfcandidateResume": "<exact resume text that supports or contradicts the requirement>"\n'
            f"  }},\n"
            f"  ...\n"
            f"]\n\n"
            f"### Example Output:\n"
            f"[\n"
            f"  {{\n"
            f'    "Requirements": "Must have experience in Python and SQL.",\n'
            f'    "MetOrNot": "yes",\n'
            f'    "partOfcandidateResume": "Worked as a Data Analyst using Python and SQL for data automation projects."\n'
            f"  }},\n"
            f"  {{\n"
            f'    "Requirements": "Experience in sell side of catagory managemnt.",\n'
            f'    "MetOrNot": "no",\n'
            f'    "partOfcandidateResume": "null"\n'
            f"  }}\n"
            f"]\n\n"
            f"Now, analyze the candidate’s resume **against each job requirement one by one** and provide your final JSON response below — strictly following the above format."
            )

            feedbackMatchingWithCandidate =  gpt_models[0].invoke_model_with_backoff(prompt, Task="Ask AI, feedback matching or not")
            not_met = [item for item in data if item.get("MetOrNot", "").lower() == "no"]
            print('feedbackMatchingWithCandidate :- ' ,feedbackMatchingWithCandidate)
            
            if len(not_met)!=0:
                Rejection_object["jobFeedbackNotMet"]=True
                Rejection_object["jobFeedbackNotMetObj"]=feedbackMatchingWithCandidate

    item = query_dynamodb_item_with_sk_prefix(table_name, partition_key_value, sort_key_prefix1)
    YOE_from_cv = item.get('YOE')
    CTC_from_cv = item.get('CTC')

    #do feedback analysis for candidate feedback
    if candidate_feedbacks:
        prompt = (
            f"You are a world-class HR Expert and Hiring Strategist with 40+ years of experience across technical and non-technical domains. and you are provided with all feedbak of a candidate\n\n"
            f"Your job is to perform a *feedback-by-feedback audit* of a candidate’s and refram them as job requiremnets.\n\n"
            f"example input : he don't know python , output : candidate must know python"
            f"candidate_feedbacks : {candidate_feedbacks}"
            f"### output formate must be a json as given below.\n"
            f"  {{\n"
            f'    "Requirements": ["Must have experience in SQL", "candidate msut know python language"]\n'
            f"  }},\n"
        )
        candidate_feedbacks_requirements =  gpt_models[0].invoke_model_with_backoff(prompt, Task="Ask ai, extract candidate feedback", want_json=False)
        print("candidate_feedbacks_requirements : -",candidate_feedbacks_requirements)

        prompt = (
        f"You are a world-class HR Expert and Hiring Strategist with 40+ years of experience across technical and non-technical domains. and you are provided with all feedbak of a candidate\n\n"
        f"your task is to Determine for each requirement whether it is asked in Job Description or not, if requirement is present in jd say yes otherwise say no. based **only** on explicit evidence from the Job Description text.\n\n"
        f"### Job Description :\n{jdItem_extracted}\n\n"
        f"### Requirements:\n{candidate_feedbacks_requirements}\n\n"
        f"### Evaluation Rules:\n"
        f"1. Always match requirement-by-requirement, not overall impression.\n"
        f"2. Extract the exact matching sentence/phrase from resume text in 'partOfcandidateJobDescription'.\n"
        f"   - If nothing matches, set 'partOfcandidateJobDescription': 'null'.\n"
        f"3. Never include extra explanation or commentary outside JSON.\n"
        f"4. The output must be strictly valid JSON — no markdown, no trailing commas, no commentary.\n\n"
        f"5. Be verry concise if anything mentioned under should have, must have don't get confused if it is asked in jd the say yes with every requirements if not met exactly say MetOrNot == no and if asked in job description then say yes"
        f"### Output Format (Strict JSON Array)\n"
        f"Return an array where each element corresponds to one requirement from the job description:\n\n"
        f"[\n"
        f"  {{\n"
        f'    "Requirements": "<exact requirement text>",\n'
        f'    "MetOrNot": "yes" or "no",\n'
        f'    "partOfcandidateJobDescription": "<exact JobDescription text that supports or contradicts the requirement>"\n'
        f"  }},\n"
        f"  ...\n"
        f"]\n\n"
        f"### Example Output:\n"
        f"[\n"
        f"  {{\n"
        f'    "Requirements": "Must have experience in Python and SQL.",\n'
        f'    "MetOrNot": "yes",\n'
        f'    "partOfcandidateJobDescription": "good to have experience in python."\n'
        f"  }},\n"
        f"  {{\n"
        f'    "Requirements": "Experience in sell side of catagory managemnt.",\n'
        f'    "MetOrNot": "no",\n'
        f'    "partOfcandidateJobDescription": "null"\n'
        f"  }}\n"
        f"]\n\n"
        f"Now, analyze the Requirements **against each JobDescription one by one** and provide your final JSON response below — strictly following the above format."
        )
        candidate_feedbacks_requirements_MetOrNot_response =  gpt_models[0].invoke_model_with_backoff(prompt, Task="Ask ai, extract candidate feedback")
        print("candidate_feedbacks_requirements_MetOrNot :--",candidate_feedbacks_requirements_MetOrNot_response)
        
        try:
            number_of_candidate_feedbacks_requirements_MetOrNot = len([i for i in candidate_feedbacks_requirements_MetOrNot_response if i["MetOrNot"].lower()=='yes'])
            if number_of_candidate_feedbacks_requirements_MetOrNot!=0:
                Rejection_object["candidateFeedbacksNotMet"]=True
                Rejection_object["candidateFeedbacksNotMetObj"]=candidate_feedbacks_requirements_MetOrNot_response


            print(f'Requirements not met from candidate_feedback :--',number_of_candidate_feedbacks_requirements_MetOrNot)
        except Exception as e:
            number_of_candidate_feedbacks_requirements_MetOrNot=False
            print("checking requirement from feedback failed",e)

        ##################################################### Salay and exp  ##########################################################
    salaryRange = jdItem.get('salaryRange')
    experienceRange = jdItem.get('experienceRange')
    
    data_to_check_ctc_and_exp = {"jd_ctc":salaryRange,"jd_exp":experienceRange,'cv_ctc':CTC_from_cv,'cv_exp':YOE_from_cv}
    check_exp_data = check_exp_ctc(data_to_check_ctc_and_exp)
    print(check_exp_data)
    reject_on_ctc_or_exp = bool([key for key, value in check_exp_data.items() if value is not False])

    if reject_on_ctc_or_exp:
        Rejection_object["rejectOnctcOrExp"]=True
        Rejection_object["rejectOnctcOrExpObj"]=check_exp_data
    else:
        Rejection_object["rejectOnctcOrExp"]=False
    print("registered user's rejectionObject",Rejection_object)
    return Rejection_object

class FirestoreManager:
    def __init__(self,GCP_secret_name,GCP_DATABASE_NAME):
        self.GCP_secret_name = GCP_secret_name
        self.GCP_DATABASE_NAME = GCP_DATABASE_NAME
        self.db = self._initialize_firestore()

    def get_secret(self,secret_name):
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



    def _initialize_firestore(self):
        creds_dict = self.get_secret(self.GCP_secret_name)
        FIRESTORE_PROJECT_ID =creds_dict.get("project_id")

        # GCP_DATABASE_NAME ="worko-corp-db-" +self.env 

        
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        db = firestore.Client(project=FIRESTORE_PROJECT_ID, credentials=credentials, database=self.GCP_DATABASE_NAME)
        print(f"Firestore initialized successfully for project: {FIRESTORE_PROJECT_ID}, database: {self.GCP_DATABASE_NAME}")
        return db

    def update_firestore_document_with_scoring_data(self,collection_name: str, doc_id: str,update_data,isFindMatchingScoreInProgress,jobMatched):
        current_datetime = datetime.now()
        # Convert it to an ISO 8601 formatted string
        iso_string = current_datetime.isoformat()


        try:
            if update_data :
                updatedByUserId = update_data.get("updatedByUserId","")
                updatedByCorporateUserId = update_data.get("updatedByCorporateUserId","")
                matchingScoreDetails = update_data.get("matchingScoreDetails","")

                if jobMatched:
                    doc_ref = self.db.collection(collection_name).document(doc_id)
                    doc_ref.update(update_data)
                    print(f"Updated Firestore document {doc_id} isFindMatchingScoreInProgress: False and update_data : {update_data}")
                    return True

                
                elif updatedByCorporateUserId: #if you receive actionByCorporateUserId in payload then  updatedByCorporateUserId 
                    doc_ref = self.db.collection(collection_name).document(doc_id)
                    doc_ref.update({
                        "matchingScoreDetails" : matchingScoreDetails,
                        "updatedAt": iso_string,
                        "updatedByCorporateUserId":updatedByCorporateUserId,
                        "isFindMatchingScoreInProgress":isFindMatchingScoreInProgress

                    })
                    print(f"Updated Firestore document {doc_id} isFindMatchingScoreInProgress: False and update_data : {matchingScoreDetails}")
                    return True

                elif updatedByUserId: #if you receive actionByUserId in payload then  updatedByUserId 
                    doc_ref = self.db.collection(collection_name).document(doc_id)
                    doc_ref.update({
                        # store as ISO string

                        "matchingScoreDetails" : matchingScoreDetails,
                        "updatedAt": iso_string,
                        "updatedByUserId":updatedByUserId,
                        "isFindMatchingScoreInProgress":isFindMatchingScoreInProgress

                    })
                    print(f"Updated Firestore document {doc_id} isFindMatchingScoreInProgress: False and update_data {matchingScoreDetails}")
                    return True

            else:
                doc_ref = self.db.collection(collection_name).document(doc_id)
                doc_ref.update({

                    "isFindMatchingScoreInProgress":True

                })
                print(f"Updated Firestore document {doc_id} with  isFindMatchingScoreInProgress :True ")
                return True

        except Exception as e:
            print(f"Error updating Firestore document {doc_id}: {e}")
            return False

    def get_document_firstore(self,collection_name,doc_id):
        doc_ref = self.db.collection(collection_name).document(doc_id)
        return doc_ref.get().to_dict()

def get_jd(jobs_id):
    # get the job description
    index_name = "GSI1"
    jobs_partition_key_value = "JOBS#"
    job_sort_key_prefix1 = "ID#" + jobs_id
    jobs_table_name = "worko-job-app"
    jdItem = query_dynamodb_item_with_index_sk_prefix(jobs_table_name, index_name, jobs_partition_key_value, job_sort_key_prefix1)
    print("jdItem:-",str(jdItem)[:100],"...")

    job_desc = jdItem.get('jobDescription')
    experienceRange = jdItem.get('experienceRange')
    softSkills = jdItem.get('softSkills')
    technicalSkills = jdItem.get('technicalSkills')
    coreSkills = jdItem.get('coreSkills')
    otherRequirements = jdItem.get('otherRequirements')
    salaryRange = jdItem.get('salaryRange') # Extract salaryRange, experienceRange, department for first check if these requirements are not met reject candidate directly.
    experienceRange = jdItem.get('experienceRange')
    department = jdItem.get('department')
    jobTitle = jdItem.get("jobTitle")

    jdItem_extracted = f"{job_desc}\nExperience Range: {experienceRange}\nSoft Skills: {softSkills}\nTechnical Skills: {technicalSkills}\nCore Skills: {coreSkills}\nMandatory Requirements: {otherRequirements}"
    # validate the job description
    key_jd_elements = ['experience', 'education', 'skills', 'primary responsibility', 'certifications', 'Preferred Skills', 'job description', 'responsibilities', 'role', 'Employment', 'Department', 'Posted', 'Company']
    
    if not jdItem or not has_key_elements(jdItem_extracted.lower(), key_jd_elements, 1):
        # update_cv_extract_in_dynamodb(table_name, partition_key_value, sort_key_prefix2, "No valid job description found or job description is not readable", 251, -1)
        print("No valid job description found or job description is not readable")
        # update_sqs_queue(email, userId, referralId, job_ref_type)
        return {"statusCode": 200, "body": "Overall matching score: 0"}
    else:
        return jdItem,jdItem_extracted,job_desc,experienceRange,softSkills,technicalSkills,coreSkills,otherRequirements,salaryRange,experienceRange,department,jobTitle 


def get_cv(s3_bucket_name,cvAwsS3FilePath,cvAwsS3FileName):
    key = cvAwsS3FilePath + '/' + cvAwsS3FileName
    s3_client = boto3.client('s3')
    print("s3_bucket_name",s3_bucket_name)
    print("key",key)
    response = s3_client.get_object(Bucket=s3_bucket_name, Key=key)
    processed_text,links_from_pdf = extract_text_from_pdf(response['Body'].read()) # add code for image based cv too
    print(str(processed_text)[:100],"...")
    key_resume_elements = ['experience', 'education', 'personalDetails','name', 'skills','email', 'certifications']
    #validate te resume
    if not processed_text or not has_key_elements(str(processed_text).lower(), key_resume_elements, 2):
        # update_cv_extract_in_dynamodb(table_name, partition_key_value, sort_key_prefix2, "No valid resume data found or resume data is not readable", 250, -1)
        print("No valid resume data found or resume data is not readable")
        return {"statusCode": 200, "body": "Overall matching score: 0"}

    return processed_text


def get_feedback(overall_matching_score,processed_text,jdItem_extracted,gpt_models,job_desc,overall_Analysis):
    rejection_feedback = ""
    rejectionFeedbackBySystemForApplicant = ""
    scoreDetails = ""
    scoreDetailsForApplicant = ""
    emailFeedback = ""
    otherRequirements = None
    
    if 1 <= overall_matching_score < 70:
        prompt = (f"candidate profile : {processed_text}, job requirements : {jdItem_extracted}\n"
            f"Analyze why this candidate scored low against job requirements highlight. Return response in exact JSON format:\n"
            f"JSON must contain exactly two top-level keys: feedback_Recruiter and feedback_Candidate\n"
            f"{{\n"
            f"  \"feedback_Recruiter\": {{\n"
            f"    \"RecruiterNote\": \"3–5 sentence recruiter-friendly summary of candidate fit, overall impression, and readiness for the role.\",\n"
            f"    \"Strengths\": [\n"
            f"      \"[name of candidate] Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
            f"      \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n"
            f"    ],\n"
            f"    \"AreasOfConcern\": [\n"
            f"      \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
            f"    ]\n"
            f"  }},\n"
            f"  \"feedback_Candidate\": {{\n"
            f"    \"CandidateNote\": \"3–5 sentence candidate-friendly summary of fit, strengths, and shortfalls written in direct and clear language.\",\n"
            f"    \"Strengths\": [\n"
            f"      \"You bring X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
            f"      \"You demonstrate proven skills in A and B, which match the mandatory requirement for this role.\"\n"
            f"    ],\n"
            f"    \"AreasOfConcern\": [\n"
            f"      \"You lack explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
            f"    ]\n"
            f"  }}\n"
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
            f"In CandidateNote → Never use speculative phrases like 'your resume shows' or 'appears to have'. State facts directly with 'you...'\n"
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
            f"- There must be only 2 points in AreasOfConcern and 2-3 points in Strengths"
            f" - In entire feedback never talk about number of years experience. you can talk about domain experience if needed"
            f"- Omit detail field if heading itself is self-explanatory.\n"
        )

        completion_text_rejection = gpt_models[0].invoke_model_with_backoff(prompt, Task="Rejection for 1 <= overall_matching_score < 70")

        completion_text_rejection_for_candidate = completion_text_rejection.get("feedback_Candidate")
        completion_text_rejection= completion_text_rejection.get("feedback_Recruiter")
        

        completion_text_rejection = json.dumps(completion_text_rejection)        ### make it string again to store in db
        completion_text_rejection_for_candidate = json.dumps(completion_text_rejection_for_candidate)

        print_completion_text(f"rejection feedback for Recruiter {completion_text_rejection}")
        print_completion_text(f"rejection feedback for Candidate {completion_text_rejection_for_candidate}")
        rejection_feedback = completion_text_rejection
        rejectionFeedbackBySystemForApplicant = completion_text_rejection_for_candidate


        if overall_matching_score >= 40:
            prompt = (f"You are an expert recruiter. Your only task is to compare the candidate profile against the job description."
                    f"Only use details explicitly stated in the provided text. Do not infer, assume, or invent information."
                    f"Input:"
                    f"- Candidate Profile: {processed_text}"
                    f"- Job Description: {job_desc}"
                    f"- Extra Analysis: {overall_Analysis}"
                    f"Output:"
                    f"Provide recruiter feedback in JSON format with three keys: \"RecruiterNote\", \"Strengths\", and \"Areas of Concern\"."
                    f"Format Example:"
                    f"{{\n"
                    f"  \"feedback_Recruiter\": {{\n"
                    f"    \"RecruiterNote\": \"3–5 sentence recruiter-friendly summary of candidate fit, overall impression, and readiness for the role.\",\n"
                    f"    \"Strengths\": [\n"
                    f"      \"[name of candidate] Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                    f"      \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                    f"    ],\n"
                    f"    \"AreasOfConcern\": [\n"
                    f"      \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                    f"    ]\n"
                    f"  }},\n"
                    f"  \"feedback_Candidate\": {{\n"
                    f"    \"CandidateNote\": \"3–5 sentence candidate-friendly summary of fit, strengths, and shortfalls written in direct and clear language.\",\n"
                    f"    \"Strengths\": [\n"
                    f"      \"You bring X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                    f"      \"You demonstrate proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                    f"    ],\n"
                    f"    \"AreasOfConcern\": [\n"
                    f"      \"You lack explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                    f"    ]\n"
                    f"  }}\n"
                    f"}}\n"
                    f"Strict Rules:"
                    f"1. **RecruiterNote** → A concise 2–3 line summary of candidate fit, overall impression, and readiness for the role."
                    f"2. Every point in \"Strengths\" and \"Areas of Concern\" must be a **direct JD vs candidate comparison**."
                    f"   - If it's not in both, do not mention it."
                    f"   - If requirement is missing in profile, flag under concerns."
                    f"   - If requirement is fully met/exceeded, add to strengths."
                    f"3. Maximum 3 strengths and 2 concerns (total 5 points)."
                    f"4. Each statement must be 15–25 words, factual, and recruiter-ready."
                    f"5. Treat missing info as missing — never assume."
                    f"6. Apply Special Mentions only if explicitly visible:"
                    f"   - Unemployed for 12+ months."
                    f"   - Frequent job changes (<1 year)."
                    f"   - Experience significantly above requirement (mark as strength)."
                    f"7. Do not comment on communication skills or location unless explicitly stated in both JD and profile."
                    f"8. Never use phrases like \"resume shows\" or \"appears to have.\" Always describe the candidate directly."
                    f"9. there must be only 2 points in AreasOfConcern and 2-3 points in Strengths"
                    f" - In entire feedback never talk about number of years experience. you can talk about domain experience if needed"
                    f"10. Output must be valid JSON only — no text outside JSON"
                    )
            
            completion_text_approval= gpt_models[0].invoke_model_with_backoff(prompt, Task="Score feedback for >40")

            print_completion_text(completion_text_approval)
            scoreDetails = completion_text_approval.get("feedback_Recruiter")
            scoreDetailsForApplicant = completion_text_approval.get("feedback_Candidate")

            scoreDetails = json.dumps(scoreDetails)        ### make it string again to store in db
            scoreDetailsForApplicant = json.dumps(scoreDetailsForApplicant)        ### make it string again to store in db
        

        
    elif overall_matching_score >= 70:
        prompt = (f"You are an expert recruiter. Your only task is to compare the candidate profile against the job description."
                    f"Only use details explicitly stated in the provided text. Do not infer, assume, or invent information."
                    f"Input:"
                    f"- Candidate Profile: {processed_text}"
                    f"- Job Description: {job_desc}"
                    f"- Extra Analysis: {overall_Analysis}"
                    f"Output:"
                    f"Provide recruiter feedback in JSON format with two keys: feedback_Recruiter, feedback_Candidate"
                    f"Each feedback will have three keys: \"Note\", \"Strengths\", and \"Areas of Concern\"."
                    f"Format Example:"
                    f"{{\n"
                    f"  \"feedback_Recruiter\": {{\n"
                    f"    \"RecruiterNote\": \"3–5 sentence recruiter-friendly summary of candidate fit, overall impression, and readiness for the role.\",\n"
                    f"    \"Strengths\": [\n"
                    f"      \"[name of candidate] Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                    f"      \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                    f"    ],\n"
                    f"    \"AreasOfConcern\": [\n"
                    f"      \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                    f"    ]\n"
                    f"  }},\n"
                    f"  \"feedback_Candidate\": {{\n"
                    f"    \"CandidateNote\": \"3–5 sentence candidate-friendly summary of fit, strengths, and shortfalls written in direct and clear language.\",\n"
                    f"    \"Strengths\": [\n"
                    f"      \"You bring X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                    f"      \"You demonstrate proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                    f"    ],\n"
                    f"    \"AreasOfConcern\": [\n"
                    f"      \"You lack explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                    f"    ]\n"
                    f"  }}\n"
                    f"}}\n"
                    f"Strict Rules:"  
                    f"1. **RecruiterNote or CandidateNote ** → A concise 3–5 line summary of candidate fit, overall impression, and readiness for the role."  
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
                    f"13. -For RecruiterNote never use speculative phrases like 'resume shows' or 'appears to have' — state facts directly with calling candidate name."
                    f"    -For CandidateNote never use speculative phrases like 'your resume shows' or 'appears to have' — talk dierectly with candidate. state facts directly with calling candidate name."
                    f"15. **EXACT WORDING RULE**: Only use terminology explicitly stated in the resume/Job Description. Never generalize specific implementations into broader industry terms."
                    f"16. **NO DOMAIN INFERENCE**: Do not infer industry expertise from individual projects or features. State only the specific technologies/projects mentioned."
                    f"17. **FACT-CHECK REQUIREMENT**: Before including any point, verify the exact phrase exists in either the Job Description or Candidate Profile text."
                    f"18. there must be only 2 points in AreasOfConcern and 2-3 points in Strengths"
                    f" - In entire feedback never talk about number of years experience. you can talk about domain experience if needed"
                    f"19. **GRANULAR SPECIFICITY**: When mentioning experience, reference the exact role/company where it was gained, not as broad industry background."  
                    f"20. Output format must be **valid JSON only**, no text outside JSON."   

                )


        completion_text_approval = gpt_models[0].invoke_model_with_backoff(prompt, Task="Score feedback for >=70")
        # content = invoke_model_with_backoff_OpenAI(prompt)
        # completion_text_approval = clean_json_response(content)

        ###########################################
        print_completion_text(completion_text_approval)
        # try:
        #     completion_text_approval = json.loads(completion_text_approval)
        # except Exception as e:
        #     print("can't load this feed back json in >=70 scoreDetails")

        print_completion_text(completion_text_approval)
        scoreDetails = completion_text_approval.get("feedback_Recruiter")
        scoreDetailsForApplicant = completion_text_approval.get("feedback_Candidate")

        scoreDetails = json.dumps(scoreDetails)        ### make it string again to store in db
        scoreDetailsForApplicant = json.dumps(scoreDetailsForApplicant)        ### make it string again to store in db
        ###########################################


        # scoreDetails = completion_text_approval

        prompt = (f"{completion_text_approval}\n"
                f"Based on the above content, write a one-line summary in 20-25 words that highlights ONLY the positive qualities and strengths that make this candidate suitable for the job.\n"
                f"Focus exclusively on positive aspects - exclude any negative feedback or criticisms.")

        emailFeedback  = gpt_models[0].invoke_model_with_backoff(prompt, Task="Get email feedback", want_json=False) 
        print("feedback_for_email:-", emailFeedback)
        

        print("otherRequirements:-", otherRequirements)
        if otherRequirements:
            # otherRequirements  = str(otherRequirements) + "candidate must have experience working in zomato"  #test


            
            prompt = (f"You are a precise resume analysis assistant. Your task is to determine if a candidate meets ALL mandatory requirements.\n\n"
                        f"**Resume Content:**\n"
                        f"{processed_text}\n\n"
                        f"**Mandatory Requirements:**\n"
                        f"{otherRequirements}\n\n"
                        f"**Critical Parsing Instructions:**\n"
                        f"You need to check Resume Content whether the Mandatory Requirements are met by candidate or not. Be very strict and do not over-evaluate candidate. Say yes or no."
                        f"All Mandatory Requirements should strictly match with Resume then only say No, otherwise if any one Mandatory Requirement is not met say directly Yes"
                        f"1. FIRST, carefully parse the requirements text to identify individual requirements\n"
                        f"2. Look for conjunctions like 'and', semicolons, bullet points, or numbered lists that separate requirements\n"
                        f"3. Pay attention to negations like 'not necessary', 'not required' - these typically indicate something is NOT a requirement\n"
                        f"4. If a sentence contains multiple clauses, break them down logically\n"
                        f"5. Example: 'Must have X and Y is not necessary' = Two items: 'Must have X' (required) + 'Y is not necessary' (Y is NOT required)\n\n"
                        f" If Mandatory Requirements is NA or Null then it means there are no Mandatory Requirements provided in job description. In this case say No "
                        f"**Analysis Instructions:**\n"
                        f"1. For each identified requirement, look for clear, explicit evidence in the resume\n"
                        f"2. A requirement is 'met' only if there is direct evidence or reasonable inference from resume content\n"
                        f"3. For work authorization: Look for explicit statements, citizenship mentions, or work history patterns that indicate legal work status\n"
                        f"4. For location/relocation: Consider current location and any mobility statements\n"
                        f"5. For skills/experience: Look for direct mentions, project descriptions, or work history that demonstrates the skill\n"
                        f"6. If ANY mandatory requirement lacks sufficient evidence, flag as missing\n"
                        f"7. Be reasonably conservative but not overly strict - use professional judgment\n\n"
                        f"Example: Must have a tier 1 college degree Output --> Yes"
                        f"**Required JSON Response Format:**\n"
                        f"{{\n"
                        f'    "mandatory_skills_missing": "Yes" or "No",\n'
                        f'    "analysis": {{\n'
                        f'        "parsed_requirements": ["list each individual requirement you identified"],\n'
                        f'        "requirements_met": ["requirements with sufficient evidence"],\n'
                        f'        "requirements_missing": ["requirements lacking evidence"],\n'
                        f'        "evidence_summary": {{\n'
                        f'            "requirement_1": "evidence found or reason for missing",\n'
                        f'            "requirement_2": "evidence found or reason for missing"\n'
                        f"        }},\n"
                        f'        "confidence_level": "High" or "Medium" or "Low"\n'
                        f"    }}\n"
                        f"}}\n\n"
                        f"**Important Guidelines:**\n"
                        f"- Use professional judgment to parse complex requirement strings\n"
                        f"- Look for explicit evidence but allow reasonable inferences from work history\n"
                        f"- If requirements are unclear or contradictory, note this in your analysis\n"
                        f"- Respond with valid JSON only, no additional text")
                

            analysis_result_json  = gpt_models[0].invoke_model_with_backoff(prompt, Task="Checking mandatory requirements") 
            print("analysis_result",analysis_result_json)
            requirements_missing = analysis_result_json["analysis"]["requirements_missing"]
            mandatory_skills_missing = analysis_result_json.get('mandatory_skills_missing')
            print("mandatory_skills_missing:-", mandatory_skills_missing)
            
            if mandatory_skills_missing == "Yes":
                print(f"mandatory Requirements is missing so actual score was {overall_matching_score} now making it to 60")
                overall_matching_score = 60

                prompt = (
                    f"Analyze why this candidate scored low against job mandatory requirements. Return response in exact JSON format:\n"
                    f"JSON must contain exactly two top-level keys: feedback_Recruiter and feedback_Candidate\n"
                    f"{{\n"
                    f"  \"feedback_Recruiter\": {{\n"
                    f"    \"RecruiterNote\": \"3–5 sentence recruiter-friendly summary of candidate fit, overall impression, and readiness for the role.\",\n"
                    f"    \"Strengths\": [\n"
                    f"      \"[name of candidate] Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                    f"      \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                    f"    ],\n"
                    f"    \"AreasOfConcern\": [\n"
                    f"      \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                    f"    ]\n"
                    f"  }},\n"
                    f"  \"feedback_Candidate\": {{\n"
                    f"    \"CandidateNote\": \"3–5 sentence candidate-friendly summary of fit, strengths, and shortfalls written in direct and clear language.\",\n"
                    f"    \"Strengths\": [\n"
                    f"      \"You bring X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                    f"      \"You demonstrate proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                    f"    ],\n"
                    f"    \"AreasOfConcern\": [\n"
                    f"      \"You lack explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                    f"    ]\n"
                    f"  }}\n"
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
                    f"In CandidateNote → Never use speculative phrases like 'your resume shows' or 'appears to have'. State facts directly with 'you...'\n"
                    f"Requirements:\n"
                    f"- Each detail must be a direct 15–25 word statement starting with 'Candidate has no...' or 'Candidate lacks...'\n"
                    f"- Focus only on missing mandatory requirements from the JD.\n"
                    f"- Flag: Educational gaps, experience above requirement, missing technical skills, insufficient industry experience, absent certifications, lacking leadership/management, career inconsistencies.\n"
                    f"- Special Mentions: Extended unemployment 12+ months, frequent short tenure roles <1 year.\n"
                    f"- Location: Only mention if candidate explicitly states inability to work in required location.\n"
                    f"- Language: Only mention if candidate explicitly lacks required language skills.\n"
                    f"- Tone: Objective, professional, decision-focused.\n"
                    f"- There must be only 2 points in AreasOfConcern and 2-3 points in Strengths"
                    f" - In entire feedback never talk about number of years experience in AreasOfConcern. you can talk about domain experience if needed"
                    f"- Omit detail field if heading itself is self-explanatory.\n"
                    f"candidate profile : {processed_text}, job requirements : {jdItem_extracted}\n"
                    f"these are some of missing requirements in this candidate focus on these while generating feedback {requirements_missing}"
                    f"- **Last check** In entire feedback there must not be contracdiction if finds any correct it."
                )



                completion_text_rejection =  gpt_models[0].invoke_model_with_backoff(prompt, Task="Rejection when mandatory not met")
                # content = invoke_model_with_backoff_OpenAI(prompt)
                # completion_text_rejection = clean_json_response(content)
                # try:
                #     completion_text_rejection = json.loads(completion_text_rejection)
                # except Exception as e:
                #     print("can't load this feed back json in 1-70 rejection")

                completion_text_rejection_for_candidate = completion_text_rejection.get("feedback_Candidate")
                completion_text_rejection= completion_text_rejection.get("feedback_Recruiter")
                

                completion_text_rejection = json.dumps(completion_text_rejection)        ### make it string again to store in db
                completion_text_rejection_for_candidate = json.dumps(completion_text_rejection_for_candidate)  ### make it string again to store in db

                print_completion_text(f"rejection feedback for Recruiter {completion_text_rejection}")
                print_completion_text(f"rejection feedback for Candidate {completion_text_rejection_for_candidate}")
                
                rejection_feedback = completion_text_rejection
                rejectionFeedbackBySystemForApplicant = completion_text_rejection_for_candidate

                print_completion_text(f"Score feedback for Recruiter {scoreDetails}")
                print_completion_text(f"Score feedback for Candidate {scoreDetailsForApplicant}")


    elif overall_matching_score == 0:
        rejection_feedback = "We encountered an error while processing. Please try again after some time"
    
    if overall_matching_score > 90:
        print("******Potential Issue******:", overall_matching_score)
        overall_matching_score = 90

        # update_sqs_queue(email, userId, referralId, job_ref_type)
        print("overall_matching_score", overall_matching_score)
    return int(overall_matching_score),rejection_feedback,rejectionFeedbackBySystemForApplicant,scoreDetailsForApplicant,scoreDetails,emailFeedback


def get_score_and_feedback(processed_text,jdItem_extracted,gpt_models,job_desc,jobs_id):
    final_completion_text = ""
    rejection_feedback = ""
    rejectionFeedbackBySystemForApplicant=""   #
    completion_text_approval= ""
    overall_matching_score = 0
    emailFeedback = ""
    overall_Analysis = ""
    scoreDetails = ""
    scoreDetailsForApplicant=""  #
    experienceRange = False
    job_feedbacks = False
    mandatoryRequirementsFromFeedback = False
    feedbackMachingWithCandidate = False

    # get the prompt for finding tech non-tech jd
  
    tech_non_tech_prompt = (
        "{\n"
        "  \"instruction\": \"Analyze the following job description and classify it as either 'Technical' or 'Non-Technical'.\",\n"
        f"  \"jobDescription\": \"{jdItem_extracted}\",\n"
        "  \"rules\": [\n"
        "    \"Technical roles involve programming, engineering, data analysis, cloud, software development, or IT skills.\",\n"
        "    \"Non-Technical roles involve business, HR, management, sales, operations, administration.\",\n"
        "    \"Respond ONLY with the final JSON output.\",\n"
        "    \"Each output value must be enclosed in double quotes.\"\n"
        "  ],\n"
        "  \"expectedOutputFormat\": {\n"
        "    \"department\": \"Technical or Non-Technical\"\n"
        "  }\n"
        "}"
    )


    # prompt = tech_non_tech_prompt.format(jdItem_extracted)

    content = gpt_models[0].invoke_model_with_backoff(tech_non_tech_prompt, Task="Step 1: Determine tech or non-tech JD", want_json=True)
    print("tech_non_tech_prompt response",content)
    tech_non_tech = content.get("department")
 


    # get the prompt for finding experience in jd
    prompt = experience_determine_prompt.format(jdItem_extracted)
    content = gpt_models[0].invoke_model_with_backoff(prompt, Task="Step 2: Determine experience level of JD", want_json=True)
    print("experience of jd",content)
    experience_level_jd = content.get("experience_level")   


    steps = get_scoring_prompts(tech_non_tech,experience_level_jd)
    print("prompts_for_scoring :-",steps[:10])
    
    try:
        for i, step in enumerate(steps):
            prompt = create_prompt(processed_text, job_desc, step)
            
            # Use different model invocation functions for each step
            if i == 0:
                
                # Adding code for OpenAI processing
                content = gpt_models[0].invoke_model_with_backoff(prompt, Task="Step 1 for score calculations", want_json=False)
                print("Open AI content",content)
                overall_Analysis = overall_Analysis + content
                temp_score = extract_score_from_OpenAI_response(content)
                # temp_score = temp_score.get('score')

                if temp_score is None:
                    temp_score = extract_score_from_OpenAI_response(content)

                # Cap temp_score at 27 if it's greater than 27
                if temp_score is not None and temp_score > 27:
                    temp_score = 27

            elif i == 1:

                # Adding code for OpenAI processing
                content = gpt_models[0].invoke_model_with_backoff(prompt, Task="Step 2 for score calculations", want_json=False)
                print("Open AI content",content)
                overall_Analysis = overall_Analysis + content
                temp_score = extract_score_from_OpenAI_response(content)

                if temp_score is None:
                    temp_score = extract_score_from_OpenAI_response(content)
                
                # Cap temp_score at 36 if it's greater than 36
                if temp_score is not None and temp_score > 36:
                    temp_score = 36

            elif i == 2:
                content = gpt_models[0].invoke_model_with_backoff(prompt, Task="Step 3 for score calculations", want_json=False)
                print("Open AI content",content)
                overall_Analysis = overall_Analysis + content
                temp_score = extract_score_from_OpenAI_response(content)

                if temp_score is None:
                    temp_score = extract_score_from_OpenAI_response(content)

                # Cap temp_score at 9 if it's greater than 9
                if temp_score is not None and temp_score > 9:
                    temp_score = 9

            elif i == 3:
                # Adding code for OpenAI processing
                content = gpt_models[0].invoke_model_with_backoff(prompt, Task="Step 4 for score calculations", want_json=False)
                print("Open AI content",content)
                overall_Analysis = overall_Analysis + content
                temp_score = extract_score_from_OpenAI_response(content)

                if temp_score is None:
                    temp_score = extract_score_from_OpenAI_response(content)
                
                # Cap temp_score at 18 if it's greater than 18
                if temp_score is not None and temp_score > 18:
                    temp_score = 18
            else:
                # Fallback to original function if there are more steps than defined functions
                content = gpt_models[0].invoke_model_with_backoff(prompt, Task="Step 2 for score calculations", want_json=False)

            # If temp_score is coming from the JSON as a list
            if isinstance(temp_score, list) and len(temp_score) > 0:
                temp_score = temp_score[0]
            # If it's already been converted to a string representation of a list
            elif isinstance(temp_score, str) and temp_score.startswith('[') and temp_score.endswith(']'):
                temp_score = temp_score.strip('[]')

            print("temp_score: ---", temp_score)
            
            if temp_score is not None:
                overall_matching_score = ensure_decimal(overall_matching_score)
                temp_score = ensure_decimal(temp_score)
                overall_matching_score = overall_matching_score + temp_score
            else:
                print("No valid score found in this response")
        print("final score: ---",overall_matching_score)
        overall_matching_score,rejection_feedback,rejectionFeedbackBySystemForApplicant,scoreDetailsForApplicant,scoreDetails,emailFeedback = get_feedback(overall_matching_score,processed_text,jdItem_extracted,gpt_models,job_desc,overall_Analysis)
        return overall_matching_score,rejection_feedback,rejectionFeedbackBySystemForApplicant,scoreDetailsForApplicant,scoreDetails,emailFeedback
        
    except Exception as e:
            print("final score: ---","Error occurred in scoring",e)


# def main(evant):
def lambda_handler(event, context):
    print("Got event:", event)
    env = os.environ.get("ENVIRONMENT","dev")
    GCP_secret_name = "GCP-firestore-secret-"+env
    GCP_DATABASE_NAME = "worko-corp-db-" +env
    current_datetime = datetime.now()
    iso_string = current_datetime.isoformat()

    azure_openai_secret_name = "AZURE-openai-secret-multimodel-"+env
    azure_openai_secret = get_secret(azure_openai_secret_name)
    gpt4 = AzureOpenAIClient(azure_openai_secret, model="gpt-4o")
    gpt_models = [gpt4] 
    
    USER_JOB_APPLICATION = event.get("sourceTypeMatchingScoreEntity","")
    if USER_JOB_APPLICATION=="USER_JOB_APPLICATION":
        print("new flow - USER_JOB_APPLICATION")
        applicantEmail = event.get("applicantEmail")
        userJobApplicationId = event.get("userJobApplicationId","")
        s3_bucket_name = event.get("cvAwsS3BucketName")
        cvAwsS3FilePath = event.get("cvAwsS3FilePath")
        cvAwsS3FileName = event.get("cvAwsS3FileName","")
        jobs_id = event.get("jobId")
        partition_key_value = event.get("USER_PK","")
        
        table_name = "worko-job-app"
        PK = f"USR#EML#{applicantEmail}"
        SK = f"JOB#APP#ID#{userJobApplicationId}"
        
        table = dynamodb.Table(table_name)
        table.update_item(
            Key={'PK': PK, 'SK': SK},
            UpdateExpression='SET isFindMatchingScoreInProgress = :val',
            ExpressionAttributeValues={':val': True}
        )
        
        processed_text = get_cv(s3_bucket_name,cvAwsS3FilePath,cvAwsS3FileName)
        jdItem,jdItem_extracted,job_desc,experienceRange,softSkills,technicalSkills,coreSkills,otherRequirements,salaryRange,experienceRange,department,jobTitle = get_jd(jobs_id)
        
        try:
            overall_matching_score,rejection_feedback,rejectionFeedbackBySystemForApplicant,scoreDetailsForApplicant,scoreDetails,emailFeedback = get_score_and_feedback(processed_text,jdItem_extracted,gpt_models,job_desc,jobs_id)
            
            Rejection_object = False
            if partition_key_value:
                Rejection_object = Registered_user_analysis(jobs_id,jdItem,jdItem_extracted,partition_key_value,processed_text,gpt_models)
            
            update_data = {
                'isFindMatchingScoreInProgress': False,
                'cvExtract': "",
                'jdMatchErrorCode': 200,
                'jdMatchErrorDesc': "",
                'matchingScore': int(overall_matching_score),
                'rejectionFeedbackBySystem': rejection_feedback,
                'rejectionFeedbackBySystemForApplicant': rejectionFeedbackBySystemForApplicant,
                'scoreDetailsForApplicant': scoreDetailsForApplicant,
                'scoreDetails': scoreDetails,
                'emailFeedback': emailFeedback,
                'scoreFetchedDate': iso_string
            }
            
            if Rejection_object:
                update_data['rejectionObject'] = Rejection_object
            
            update_expr = 'SET ' + ', '.join([f'{k} = :{k}' for k in update_data.keys()])
            expr_attr_values = {f':{k}': v for k, v in update_data.items()}
            
            table.update_item(
                Key={'PK': PK, 'SK': SK},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_attr_values
            )
            
            return {
                "statusCode": 200,
                "body": json.dumps({"score": float(overall_matching_score), "rejection_feedback": rejection_feedback, "scoreDetails": scoreDetails, "scoreDetailsForApplicant": scoreDetailsForApplicant, "rejectionFeedbackBySystemForApplicant": rejectionFeedbackBySystemForApplicant})
            }
        except Exception as e:
            print("Error in USER_JOB_APPLICATION flow:", e)
            table.update_item(
                Key={'PK': PK, 'SK': SK},
                UpdateExpression='SET isFindMatchingScoreInProgress = :prog, jdMatchErrorCode = :code, jdMatchErrorDesc = :desc, matchingScore = :score',
                ExpressionAttributeValues={':prog': False, ':code': 400, ':desc': str(e), ':score': -1}
            )
            return {
                "statusCode": 400,
                "body": json.dumps({"score": float(-1)})
            }
    else:
        Doc_ID = event.get("agencyUserSubmissionId","")
        s3_bucket_name = event.get("cvAwsS3BucketName")
        cvAwsS3FilePath = event.get("cvAwsS3FilePath")
        cvAwsS3FileName = event.get("cvAwsS3FileName")
        jobs_id = event.get("jobId")
        partition_key_value = event.get("USER_PK","")
        candidateJobMatchingId = event.get("candidateJobMatchingId","")

        actionByCorporateUserId = event.get("actionByCorporateUserId","")
        actionByUserId = event.get("actionByUserId")
        
        # Initialize Azure OpenAI Client

        if candidateJobMatchingId: #update flag in case of candidateJobMatchingId
            DBManager = FirestoreManager(GCP_secret_name,GCP_DATABASE_NAME)
            collection_name = "candidateJobMatchings" 
            DBManager.update_firestore_document_with_scoring_data(collection_name, candidateJobMatchingId,"","",False)

        else:
            DBManager = FirestoreManager(GCP_secret_name,GCP_DATABASE_NAME)
            collection_name = "agencyUserSubmissions" 
            DBManager.update_firestore_document_with_scoring_data(collection_name, Doc_ID,"","",False)

        # jdItem,jdItem_extracted,job_desc,experienceRange,softSkills,technicalSkills,coreSkills,otherRequirements,salaryRange,experienceRange,department,jobTitle  = get_jd(jobs_id)
        #get cv pdf from s3
        # if s3_bucket_name=="worko-app-dev":
        processed_text = get_cv(s3_bucket_name,cvAwsS3FilePath,cvAwsS3FileName)
        jdItem,jdItem_extracted,job_desc,experienceRange,softSkills,technicalSkills,coreSkills,otherRequirements,salaryRange,experienceRange,department,jobTitle =get_jd(jobs_id)

        try:   
            overall_matching_score,rejection_feedback,rejectionFeedbackBySystemForApplicant,scoreDetailsForApplicant,scoreDetails,emailFeedback = get_score_and_feedback(processed_text,jdItem_extracted,gpt_models,job_desc,jobs_id)

            Rejection_object=False
            
            if partition_key_value:
                Rejection_object  = Registered_user_analysis(jobs_id,jdItem,jdItem_extracted,partition_key_value,processed_text,gpt_models)

            if candidateJobMatchingId:
                DBManager = FirestoreManager(GCP_secret_name,GCP_DATABASE_NAME)
                collection_name = "candidateJobMatchings" 

                if actionByCorporateUserId:
                    if Rejection_object:
                        updated_data = { "isFindMatchingScoreInProgress":False,
                                        "updatedByCorporateUserId": actionByCorporateUserId,
                        "cvExtract":"",
                        "jdMatchErrorCode":200,
                        "jdMatchErrorDesc": "",
                        
                        "matchingScore": int(overall_matching_score),
                        "rejectionObject":Rejection_object,
                        "rejectionFeedbackBySystem":rejection_feedback,
                        "rejectionFeedbackBySystemForApplicant":rejectionFeedbackBySystemForApplicant,
                        "scoreDetailsForApplicant":scoreDetailsForApplicant,
                        "scoreDetails":scoreDetails,
                        "emailFeedback":emailFeedback,
                        
                        
                        }
                    else:
                        updated_data = { "isFindMatchingScoreInProgress":False,
                        "cvExtract":"",
                        "jdMatchErrorCode":200,
                        "jdMatchErrorDesc": "",
                        "matchingScore": int(overall_matching_score),
                        "rejectionFeedbackBySystem":rejection_feedback,
                        "rejectionFeedbackBySystemForApplicant":rejectionFeedbackBySystemForApplicant,
                        "scoreDetailsForApplicant":scoreDetailsForApplicant,
                        "scoreDetails":scoreDetails,
                        "emailFeedback":emailFeedback,
                        "updatedByCorporateUserId": actionByCorporateUserId,
                        }

                elif actionByUserId:
                    if Rejection_object:
                        updated_data = { "isFindMatchingScoreInProgress":False,
                        "cvExtract":"",
                        "jdMatchErrorCode":200,
                        "jdMatchErrorDesc": "",
                        "matchingScore": int(overall_matching_score),
                        "rejectionFeedbackBySystem":rejection_feedback,
                        "rejectionFeedbackBySystemForApplicant":rejectionFeedbackBySystemForApplicant,
                        "scoreDetailsForApplicant":scoreDetailsForApplicant,
                        "scoreDetails":scoreDetails,
                        "emailFeedback":emailFeedback,
                        "rejectionObject":Rejection_object,
                        "updatedByUserId": actionByUserId
                        
                        }
                    else:
                        updated_data = { "isFindMatchingScoreInProgress":False,
                        "cvExtract":"",
                        "jdMatchErrorCode":200,
                        "jdMatchErrorDesc": "",
                        "matchingScore": int(overall_matching_score),
                        "rejectionFeedbackBySystem":rejection_feedback,
                        "rejectionFeedbackBySystemForApplicant":rejectionFeedbackBySystemForApplicant,
                        "scoreDetailsForApplicant":scoreDetailsForApplicant,
                        "scoreDetails":scoreDetails,
                        "emailFeedback":emailFeedback,
                        "updatedByUserId": actionByUserId
                        }
                DBManager.update_firestore_document_with_scoring_data(collection_name, candidateJobMatchingId,updated_data,False,True)

            else:
                if actionByCorporateUserId:
                    if Rejection_object:
                        updated_data = { "matchingScoreDetails": { "cvExtract":"",
                        
                        "jdMatchErrorCode":200,
                        "jdMatchErrorDesc": "",
                        "matchingScore": int(overall_matching_score),
                        "rejectionFeedbackBySystem":rejection_feedback,
                        "rejectionFeedbackBySystemForApplicant":rejectionFeedbackBySystemForApplicant,
                        "scoreDetailsForApplicant":scoreDetailsForApplicant,
                        "scoreDetails":scoreDetails,
                        "emailFeedback":emailFeedback,
                        "rejectionObject":Rejection_object},
                        
                        "updatedByCorporateUserId": actionByCorporateUserId
                        }
                    else:
                        updated_data = { "matchingScoreDetails":{"cvExtract":"",
                        "jdMatchErrorCode":200,
                        "jdMatchErrorDesc": "",
                        "matchingScore": int(overall_matching_score),
                        "rejectionFeedbackBySystem":rejection_feedback,
                        "rejectionFeedbackBySystemForApplicant":rejectionFeedbackBySystemForApplicant,
                        "scoreDetailsForApplicant":scoreDetailsForApplicant,
                        "scoreDetails":scoreDetails,
                        "emailFeedback":emailFeedback},

                        "updatedByCorporateUserId": actionByCorporateUserId,
                        }

                elif actionByUserId:
                    if Rejection_object:
                        updated_data = { "matchingScoreDetails":{ "cvExtract":"",
                        "jdMatchErrorCode":200,
                        "jdMatchErrorDesc": "",
                        "matchingScore": int(overall_matching_score),
                        "rejectionFeedbackBySystem":rejection_feedback,
                        "rejectionFeedbackBySystemForApplicant":rejectionFeedbackBySystemForApplicant,
                        "scoreDetailsForApplicant":scoreDetailsForApplicant,
                        "scoreDetails":scoreDetails,
                        "emailFeedback":emailFeedback,
                        "rejectionObject":Rejection_object
                        },
                        
                        "updatedByUserId": actionByUserId
                        
                        }
                    else:
                        updated_data = { "matchingScoreDetails":{"cvExtract":"",
                        "jdMatchErrorCode":200,
                        "jdMatchErrorDesc": "",
                        "matchingScore": int(overall_matching_score),
                        "rejectionFeedbackBySystem":rejection_feedback,
                        "rejectionFeedbackBySystemForApplicant":rejectionFeedbackBySystemForApplicant,
                        "scoreDetailsForApplicant":scoreDetailsForApplicant,
                        "scoreDetails":scoreDetails,
                        "emailFeedback":emailFeedback
                        },
                        
                        "updatedByUserId": actionByUserId
                        }
                    # "updatedAt": iso_string,
                
                DBManager.update_firestore_document_with_scoring_data(collection_name, Doc_ID,updated_data,False,False)

            return {
                "statusCode": 200,
                # "body": json.dumps("Process completed successfully.")
                "body": json.dumps({"score": float(overall_matching_score), "rejection_feedback": rejection_feedback, "scoreDetails": scoreDetails, "scoreDetailsForApplicant": scoreDetailsForApplicant, "rejectionFeedbackBySystemForApplicant": rejectionFeedbackBySystemForApplicant})
            }
        except Exception as e:
            print("Error occurred: ",e )
            updated_data = { "cvExtract":"",
            "jdMatchErrorCode": 400,
            "jdMatchErrorDesc": e,
            "matchingScore": int(-1),
            "updatedAt": iso_string,
            "updatedByCorporateUserId": actionByCorporateUserId,
            "updatedByUserId": actionByUserId,
            }

            DBManager.update_firestore_document_with_scoring_data(collection_name, Doc_ID,updated_data,False,False)
            return {
                "statusCode": 400,
                # "body": json.dumps("Process completed successfully.")
                "body": json.dumps({"score": float(-1)})
            }



# if __name__ == "__main__":
    #admin
    # event = {"candidateJobMatchingId": "f7cba5dfe11b4a43fedd", "cvAwsS3ResourceType": "AGENCY_SUBMIT_USER_CV", "actionByUserId": "01b3adda-b0d1-7043-6a1e-6c833d4e8933", "jobId": "01K4MXX01Z4PP99PQTTF7DEBM9", "cvAwsS3BucketName": "worko-app-dev", "cvAwsS3FilePath": "agencies/71WFYNMG3HE02CK2EE0TAF04MX/companies/01JWAQF1G96E0SE9XHXSFGHNWW/jobs/01KD2Q23T7VMVHEEJZKT8TNTC5/user-profiles", "cvAwsS3FileName": "01KD8593V19MPKTYQF5QH18YCR.pdf"}



    # corp
    # event = {"candidateJobMatchingId": "e0752a3208b2b951614a", "cvAwsS3ResourceType": "CORP_CAND_BULK_CV_UPLOAD", "actionByCorporateUserId": "21PDYKMG11E1BK5V4762NN2KVQ", "jobId": "01K7Z7RM97J7V8E4059KQ1D2Z6", "cvAwsS3BucketName": "worko-corporate-cand-profile-dev", "cvAwsS3FilePath": "companies/01JWAQF1G96E0SE9XHXSFGHNWW/bulk-cvs", "cvAwsS3FileName": "01KF0H931TBG3S5SYH9WG5M9BM.pdf"}
    
    #new requirments event
    # event = {'sourceTypeMatchingScoreEntity': 'USER_JOB_APPLICATION', 'cvAwsS3ResourceType': 'CAND_SUBMIT_CV_JOB', 'applicantEmail': 'shaukatdatasciencerajraj@gmail.com', 'userJobApplicationId': '01KHECYMFQ34SN1RES9TVSRAF6', 'actionByCorporateUserId': '21PDYKMG11E1BK5V4762NN2KVQ', 'jobId': '01K9CAPP194FFNV6D876KVG01S', 'cvAwsS3BucketName': 'worko-app-dev', 'cvAwsS3FilePath': 'candidate-submit-cvs/companies/01JWAQF1G96E0SE9XHXSFGHNWW/jobs/01K9CAPP194FFNV6D876KVG01S/cvs', 'cvAwsS3FileName': '01KHECY94EEF53CBX479WJDWCS.pdf'}

  
    # lambda_handler(event,None)
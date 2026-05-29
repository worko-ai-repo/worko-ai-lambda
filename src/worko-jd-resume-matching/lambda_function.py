
import json
import boto3
import os
import sys
from decimal import Decimal
from pathlib import Path
sqs_region = 'ap-south-1'
region = 'us-east-1'
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client(service_name='bedrock', region_name = region)
bedrock_runtime = boto3.client(service_name='bedrock-runtime', region_name = region)
sqs = boto3.client('sqs')
s3_client = boto3.client('s3')
# Add shared-core-layer to path for local testing
if __name__ == "__main__":
    shared_layer_path = Path(__file__).parent.parent / "shared-core-layer"
    sys.path.insert(0, str(shared_layer_path))

# Import from shared-core-layer

from ai_clients import AzureOpenAIClient
from feedback.feedback_generator import get_reason_from_rejection_data
from parsers import extract_text_from_pdf, extract_text_from_docx
from utils import *
from prompt.prompts import *
from scoring.get_scoring import get_score

# Initialize clients
region = 'ap-south-1'

# bedrock_client = BedrockClient(region_name=region)


def has_key_elements(text, key_elements, threshold):
    """Check if text contains minimum required elements."""
    present_elements = sum(1 for element in key_elements if element.lower() in text.lower())
    return present_elements >= threshold


def determine_type(input_string):
    """Determine if input is JOB or REF type."""
    if "JOB#" in input_string:
        return "JOB"
    elif "REF#" in input_string:
        return "REF"
    else:
        return "UNKNOWN"


def lambda_handler(event, context):
    print("Got event:-", event)
    # Environment variables
    table_name = os.environ.get('DYNAMO_TABLE_NAME',"worko")
    jobs_table_name = os.environ.get('JOBS_DYNAMO_TABLE_NAME',"worko-job-app")
    s3_bucket_name = os.environ.get('S3_BUCKET_NAME',"worko-app-dev")
    print(f"DYNAMO_TABLE_NAME {table_name} JOBS_DYNAMO_TABLE_NAME {jobs_table_name} s3_bucket_name {s3_bucket_name}")
    env = os.environ.get("ENVIRONMENT", "dev")
    azure_openai_secret_name = "AZURE-openai-secret-multimodel-" + env
    azure_openai_secret = get_secret(azure_openai_secret_name)
    gpt4 = AzureOpenAIClient(azure_openai_secret, model="gpt-4o")
    gpt_models = [gpt4]
    otherRequirements=""

    partition_key_value = event.get('USER_PK')
    sort_key_prefix1 = event.get('USER_DETAIL_SK')
    sort_key_prefix2 = event.get('ENTITY_SK')
    MATCHING_ENTITY = event.get("MATCHING_ENTITY","") #"SOURCE_TYPE_JOB_APP"
    candidateParsedCvId = event.get("candidateParsedCvId","")
        
    item = query_dynamodb_item_with_sk_prefix(table_name, partition_key_value, sort_key_prefix1)
    print(f"cv item of the user {item}")
    # Fetch the jd attributes from the dynamo db
    jdItem = query_dynamodb_item_for_ref_with_sk_prefix(table_name, partition_key_value, sort_key_prefix2)
    print(f"jdItem:- table_name : {table_name},partition_key_value:{partition_key_value},sort_key_prefix2:{sort_key_prefix2}",jdItem)   
    email = partition_key_value.split('#')[2]
    userId = item.get('SK')
    userId = userId.split('#')[1]
    jdItem_extracted = jdItem.get('jdExtracted', '') if jdItem else ''

    referralId = sort_key_prefix2.split('#')[-1]
    print("job/ref Id:-", referralId)

    job_ref_type = determine_type(sort_key_prefix2)
    print("job_ref_type:-", job_ref_type)

    # Extracting the CV raw text
    resumeId = item.get('SK').split('#')[-1]
    cvId = item.get('CV')
    print(f"resumeId: {resumeId},cvId:{cvId}")

    if candidateParsedCvId:
        print("get firstore doc here")

        collection_name = "candidateParsedCvs"
        env = os.environ.get("ENVIRONMENT","dev")
        GCP_secret_name = "GCP-firestore-secret-"+env
        GCP_DATABASE_NAME = "worko-corp-db-"+env
        
        db = FirestoreManager(GCP_secret_name,GCP_DATABASE_NAME)
        item = db.get_document_firstore(collection_name,candidateParsedCvId)
        print(f"in case of candidate form submission cv item from firestore {str(item)[:100]}")
    try:
        if MATCHING_ENTITY =="SOURCE_TYPE_JOB_APP":
            sourceTypeCvAwsS3Details = event.get("sourceTypeCvAwsS3Details",{})
            filePath= sourceTypeCvAwsS3Details.get("filePath","")
            fileName= sourceTypeCvAwsS3Details.get("fileName","")
            key = filePath + "/" + fileName
            s3_bucket_name = sourceTypeCvAwsS3Details.get("bucketName")
        else:
            key = "users/" + resumeId + "/resumes/" + cvId
        print("key",key)


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
    try:
        if ".pdf" in key:
            processed_text = extract_text_from_pdf(data)
        if not processed_text : 
            print('image Based cv processing..')
            base64_images = extract_images_from_pdf(data)
            processed_text = invoke_claude_with_image(base64_images)   
            print('image Based cv process completed') 
        elif ".docx" in key:
            processed_text = extract_text_from_docx(data)
    except Exception as e :
        print("The file format is not supported.error ",e)
        return {
            'statusCode': 400,
            'body': json.dumps({'message': 'Unsupported file format. Please upload a PDF or DOCX file.'})
        }
    print("processed_text", str(processed_text)[:100])
    #   Validate the cv
    key_resume_elements = ['multipleCandidateExperience', 'education', 'personalDetails','name', 'email']
    key_jd_elements = ['experience', 'education', 'skills', 'primary responsibility', 'certifications', 'Preferred Skills', 'job description', 'responsibilities', 'role', 'Employment', 'Department', 'Posted', 'Company']
    
    cvExtractParsed = item.get('cvExtractParsed', '')
    CTC_from_cv = item.get('CTC')
    YOE_from_cv = item.get('YOE')
    cv_extract = item.get('cvExtractParsed')

    if candidateParsedCvId:#in case of firstore cv
        cvExtractParsed = item
        CTC_from_cv = cvExtractParsed.get('currentCTC')
        YOE_from_cv = cvExtractParsed.get('totalYOE')
        cv_extract = item
        # with open(r'src/worko-jd-resume-matching/firstore_cv_data.json', 'w') as json_file:
        #     json.dump(item, json_file, indent=4, cls=CustomEncoder)


    if not item or not has_key_elements(str(cvExtractParsed).lower(), key_resume_elements, 2):
        update_cv_extract_in_dynamodb(table_name, partition_key_value, sort_key_prefix2, "No valid resume data found or resume data is not readable", 250, -1)
        # update_sqs_queue(email, userId, referralId, job_ref_type) recently commented
        print("No valid resume data found or resume data is not readable")
        return {"statusCode": 200, "body": "Overall matching score: 0"}



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

    if "JOB" in job_ref_type:   #it will use to overwrite job_desc if it is from job application and not from reff
        Job_id_item = query_dynamodb_item_for_ref_with_sk_prefix(jobs_table_name, partition_key_value, sort_key_prefix2)
        
        jobs_id = Job_id_item.get('jobId')
        print("jobs_id:-", jobs_id)

        index_name = "GSI1"
        jobs_partition_key_value = "JOBS#"
        job_sort_key_prefix1 = "ID#" + jobs_id

        jdItem = query_dynamodb_item_with_index_sk_prefix(jobs_table_name, index_name, jobs_partition_key_value, job_sort_key_prefix1)
        print("jdItem:-",jdItem)
        
        if jdItem:
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
            print("jdItem_extracted:-",jdItem_extracted)
            
            #get the feedback for further analysis
            candidate_feedbacks = quiry_dynamo_for_candidate_feedbacks(partition_key_value)
            feedbacks ,job_feedbacks = quiry_dynamo_for_job_feedbacks(jobs_id) #(jobs_id)

            print(f"feedbacks got for the job {job_feedbacks}")
            # Experience_mismatched = False
            if job_feedbacks:
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
                
                collect_requiremet_from_feedback_prompt = f"""
                You are an **Expert HR Manager** with **40+ years of experience** in recruitment evaluation and job requirement analysis.

                You are given detailed **interviewer feedback** and a set of **mandatory requirements**.  
                Your job is to **analyze, extract, and structure** all job requirements derived from the feedback — without missing a single one.

                ##  PHASE 1 — Requirement Extraction
                ###  Objective
                Extract and summarize what the feedback **explicitly or implicitly** reveals about:
                - The **skills**, **experience**, or **attributes** the role requires.
                - What the **ideal candidate** should have or demonstrate.

                Every valid insight must be reframed into a clear, standardized **requirement statement**.

                ###  Instructions
                1. **Read every “reason” and “recruiterComment” carefully** — do not skip or omit any entry.
                2. **Derive requirements only from feedback content.**
                - The job description ({jdItem}) can be used **only for context clarification**.
                - Never add, infer, or invent new requirements beyond what feedback implies.
                3. **Reframe all valid insights** as **concise, single-line job requirements** starting with:
                - "Candidate must have..."
                - "Candidate should be skilled in..."
                - "Candidate must be able to..."
                4. **Include every unique feedback-derived requirement** in `"requirements"`.
                5. **Exclude**:
                - General praise (e.g., “Great attitude”).
                - Rejection reasons unrelated to job fit (e.g., “Not confident”).
                - Personal or behavioral opinions not tied to skill or experience.
                6. **Track repetition frequency**:
                - A requirement must appear under `"repeatedmandatoryRequirements"` **only if it occurs 3 or more times** (exactly or as a clear semantic equivalent).
                - If none meet this criterion, return `"repeatedmandatoryRequirements": []`.
                7. Avoid duplicates:
                - If two requirements are **more than 50% semantically similar**, keep only one.
                8. Do **not** include markdown, comments, or explanations.

                ---
                ##  PHASE 2 — Feedback-to-Requirement Matching

                ### Objective
                Identify which feedback statements **exactly or semantically match** the existing **Mandatory Requirements**.

                Only return the **original feedback lines** that clearly correspond to one or more mandatory requirements.

                ---

                ### Logic Rules
                1. Compare **each feedback line** against **all mandatory requirements** ({otherRequirements}).
                2. A feedback line is a **match** only if:
                - It expresses **the same meaning** as a mandatory requirement (≥80% semantic similarity).
                - It does **not** add, remove, or alter key information.
                3. If a feedback line is only partially similar or expands on the requirement — **exclude it**.
                4. Never paraphrase, summarize, or reword feedback.
                5. Include **only the exact original feedback sentences** inside `"feedbackmandatoryRequirements"`.
                6. If **no matches exist**, return `"feedbackmandatoryRequirements": []`.
                **last check**
                evrey feedback must be there in requirements skip only of you are adding it in repeatedmandatoryRequirements or feedbackmandatoryRequirements
                ---

                ## INPUT
                - **Mandatory Requirements:**  
                {otherRequirements}

                - **Feedback Entries (combined):**  
                {feedbacks}

                ---

                ## STRICT OUTPUT FORMAT (JSON ONLY)
                Return **only** a valid JSON object in the exact structure below — no additional text, markdown, or explanations:

                
                {{
                "requirements": [
                    "Candidate must have experience in data analysis.",
                    "Candidate should be skilled in Python and SQL."
                ],
                "repeatedmandatoryRequirements": [
                    "Candidate must have experience in data analysis."
                ],
                "feedbackmandatoryRequirements": [
                    "Candidate must have strong analytical skills."
                ]
                }}"""


                requirementsFormFeedback = gpt_models[0].invoke_model_with_backoff(prompt=collect_requiremet_from_feedback_prompt, Task="AI for feedback Extraction.")
                mandatoryRequirementsFromFeedback = requirementsFormFeedback.get("repeatedmandatoryRequirements","") + requirementsFormFeedback.get("feedbackmandatoryRequirements","")
                
                print(f'requirementsFormFeedback :-- {requirementsFormFeedback}')
                print("merged mandatoryRequirementsFromFeedback", mandatoryRequirementsFromFeedback)
                requirementsFormFeedback = requirementsFormFeedback.get("requirements","")

                make_feedback_summarised_reuirements_prompt = f"""
                You are an **Expert HR Manager** with over **40 years of experience** in recruitment evaluation and job analysis.

                Your task is to carefully review **recruiter feedback** and **mandatory requirements**, then **reframe and consolidate** them into a unified list of clear, concise **job requirements**.

                ### Objective
                Transform all recruiter feedback and mandatory requirements into **standardized job requirement statements** that begin with:
                - "Candidate must have..."
                - "Candidate must be..."

                These statements should capture only the **explicit or implicit requirements** derived from the provided inputs.


                ### Step-by-Step Instructions
                1. **Read every recruiter feedback entry carefully** — do not skip or ignore any.
                2. **Extract all implied or explicit job requirements** mentioned or hinted at.
                3. **Reframe** each requirement into a concise, single-line statement using a consistent format:
                -Example1: *"Candidate must have strong analytical skills."*
                -Example2: *"Candidate must be experienced in Python development."*
                4. **Combine** the results from both:
                - Recruiter Feedback  
                - Mandatory Requirements
                5. **Avoid repetition**:
                - If two statements are **more than 50% similar**, **keep only one**.
                - Retain both **only if** each adds **unique or explicit information**.
                6. **Do not add or infer** any new information not clearly supported by the inputs.
                7. Ensure that **every point from both sections** (feedback + mandatory requirements) is **represented** in the final output.

                ### Input Data
                **Recruiter Feedback:**  
                {mandatoryRequirementsFromFeedback}

                **Mandatory Requirements:**  
                {otherRequirements}

                ### Output Format (Strictly JSON)
                Return your final answer **only** in the following JSON structure (no text outside the JSON):

                
                {{
                "feedbackMandatoryRequirements": [
                    "Candidate must have knowledge of Python.",
                    "Candidate must be proficient in software development.",
                    "Candidate must have strong problem-solving skills."
                ]
                }}"""

                mandatoryRequirementsFromFeedback = gpt_models[0].invoke_model_with_backoff(prompt=make_feedback_summarised_reuirements_prompt, Task="AI for feedback summarization.")
                print("mandatoryRequirementsFromFeedback  :--",mandatoryRequirementsFromFeedback)

                mandatoryRequirementsFromFeedback = " ".join(mandatoryRequirementsFromFeedback.get("feedbackMandatoryRequirements",""))
                print("mandatoryRequirementsFromFeedback  :--",mandatoryRequirementsFromFeedback)

                if mandatoryRequirementsFromFeedback:
                    print("adding mandatoryRequirementsFromFeedback  :--",mandatoryRequirementsFromFeedback)
                    # otherRequirements = otherRequirements + mandatoryRequirementsFromFeedback
                    otherRequirements = mandatoryRequirementsFromFeedback

    # print("**********************************Resume*********************************************")
    print("Resume:-", str(cv_extract)[:100])
    # Validate the Job description
    if not jdItem or not has_key_elements(jdItem_extracted.lower(), key_jd_elements, 1):
        update_cv_extract_in_dynamodb(table_name, partition_key_value, sort_key_prefix2, "No valid job description found or job description is not readable", 251, -1)
        print("No valid job description found or job description is not readable")
        # update_sqs_queue(email, userId, referralId, job_ref_type) recently commented
        return {"statusCode": 200, "body": "Overall matching score: 0"}

    print("*****************************Job Description******************************************")
    job_desc = jdItem_extracted
    print("jd:-", job_desc)
#############################################Evaluate candidate based on ctc and exp#########################################################
    department_mismatch =False
    reject_on_ctc_or_exp=False
    if experienceRange:
        data_to_check_ctc_and_exp = {"jd_ctc":salaryRange,"jd_exp":experienceRange,'cv_ctc':CTC_from_cv,'cv_exp':YOE_from_cv}
        check_exp_data = check_exp_ctc(data_to_check_ctc_and_exp)
        reject_on_ctc_or_exp = bool([key for key, value in check_exp_data.items() if value is not False])      

        preff_sort_key = "PREF#"
        if candidateParsedCvId: #in case of firstore cv
            userPreferredDepartments = item.get("userPreferredDepartments","")
            department = jdItem.get("department")
            name_of_the_candidate= item.get("name","")

        else:
            preff_data = query_dynamodb_item_with_sk_prefix(table_name, partition_key_value, preff_sort_key)
            userPreferredDepartments = preff_data.get("userPreferredDepartments")
            department = jdItem.get("department")
            name_of_the_candidate = cvExtractParsed.get('personalDetails').get('name')

        check_department_alignment_prompt = (
        f"You are an expert HR Manager with 40+ years of experience in both technical and non-technical hiring.\n\n"
        f"Analyze the following job description and its department, then compare it with the candidate’s preferred departments and resume.\n\n"
        f"**Task:**\n"
        f"Your job is to check whether the candidate’s domain is aligned with the job description’s domain or not.\n\n"
        f"**Job Description:** {job_desc}\n"
        f"**Department of Job Description:** {department}\n\n"
        f"**Candidate’s Resume:** {processed_text}\n"
        f"**Candidate’s Preferred Departments:** {userPreferredDepartments}\n\n"
        f"**Considerations for classification:**\n"
        f"- Technical roles typically involve programming, engineering, data analysis, or IT skills.\n"
        f"- Non-technical roles typically focus on business, management, sales, or operations.\n\n"
        f"- **Strict Note** Never provide any extra explanantion apart feom below json"
        f"**Output Format:**\n"
        f"{{\n"
        f'  "AlignedOrNot": "yes" or "no",\n'
        f'  "feedbackforCandidate": "Thank you for applying to {jobTitle}. After reviewing your profile, we found that your department is not aligned with the requirement for this role. We encourage you to explore opportunities better aligned with your background, as we’d love to see you grow in the right role.",\n'
        f'  "feedbackforRecruiter": "{name_of_the_candidate}’s department is not aligned with the requirement for this role."\n'
        f"}}\n\n"
        f"**Example:**\n"
        f"{{\n"
        f'  "AlignedOrNot": "no",\n'
        f'  "feedbackforCandidate": "Thank you for applying to [Job Title]. After reviewing your profile, your department is not aligned with the requirement for this role. We encourage you to explore opportunities better aligned with your background, as we’d love to see you grow in the right role.",\n'
        f'  "feedbackforRecruiter": "[Candidate Name]’s department is not aligned with the requirement for this role."\n'
        f"}}"
        )

        completion_text_rejection =  gpt_models[0].invoke_model_with_backoff(check_department_alignment_prompt,Task= "check Department id Suitable or not from Ai",want_json=True)
        print(completion_text_rejection)

        if not reject_on_ctc_or_exp and completion_text_rejection['AlignedOrNot'].lower()=='no':
            statment = ' reject_on_ctc_or_exp is False and  is no'
            overall_matching_score = 50
            rejectionFeedbackBySystemForApplicant = completion_text_rejection["feedbackforCandidate"]
            rejection_feedback = completion_text_rejection["feedbackforRecruiter"]
            rejection_feedback = json.dumps({"RecruiterNote":rejection_feedback})
            department_mismatch = True

    if department_mismatch or reject_on_ctc_or_exp:
        feedback_for_department_or_ctc_mismatched_prompt = (
            f"You are an expert recruiter. Your only task is to compare the candidate profile against the job description."
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
        completion_text_approval= gpt_models[0].invoke_model_with_backoff(feedback_for_department_or_ctc_mismatched_prompt,Task= "Score feedback for 50 caped case ")
        print_completion_text(completion_text_approval)
        scoreDetails = completion_text_approval.get("feedback_Recruiter")
        scoreDetails = json.dumps(scoreDetails)
        scoreDetailsForApplicant = completion_text_approval.get("feedback_Candidate")
        scoreDetailsForApplicant = json.dumps(scoreDetailsForApplicant)

#############################################################################################################################################
    if not reject_on_ctc_or_exp and not department_mismatch:
        
        try:
            score_obj = get_score(processed_text, job_desc)
            overall_matching_score = score_obj["overall_matching_score"]

            print("overall_matching_score in lambda", overall_matching_score, type(overall_matching_score))
            # print("overall_Analysis:-", overall_Analysis)

            if "JOB" in job_ref_type and job_feedbacks:
                if Experience_mismatched:
                    if newThreshHoldF_for_exp.get("min",""):                  #substract 10 marks if exp does not machtes
                        if YOE_from_cv <= newThreshHoldF_for_exp["min"] and overall_matching_score>40:
                            
                            th = newThreshHoldF_for_exp["min"]
                            print(f"deducted 10 Marks becouse candidate is having less or eauqls {th} years of experience as per the previous feedbacks it should be greater then {YOE_from_cv} years. Initial Marks :- {overall_matching_score} updated marks :- {overall_matching_score-10}")
                            overall_matching_score -=10
                            
                            
                    if newThreshHoldF_for_exp.get("max",""):
                        
                        if YOE_from_cv >= newThreshHoldF_for_exp["max"] and overall_matching_score >40:
                            th = newThreshHoldF_for_exp["max"]
                            print(f"deducted 10 Marks becouse candidate is having greater or eauqls {th} years of experience as per the previous feedbacks it should be less then {YOE_from_cv} years. Initial Marks :- {overall_matching_score} updated marks :- {overall_matching_score-10}")
                            overall_matching_score -=10
                            
                        
                # requirementsFormFeedback.append('Candidate must have chemical education background')       ## test
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
                    candidate_feedbacks_requirements =  gpt_models[0].invoke_model_with_backoff(prompt,Task= "Ask ai, extract candidate feedback",want_json=False)
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
                    candidate_feedbacks_requirements_MetOrNot =  gpt_models[0].invoke_model_with_backoff(prompt,Task= "Ask ai, extract candidate feedback")
                    print("candidate_feedbacks_requirements_MetOrNot :--",candidate_feedbacks_requirements_MetOrNot)
                    number_of_candidate_feedbacks_requirements_MetOrNot=False
                    try:
                        number_of_candidate_feedbacks_requirements_MetOrNot = len([i for i in candidate_feedbacks_requirements_MetOrNot if i["MetOrNot"].lower()=='yes'])
                        print(f'Requirements not met from candidate_feedback :--',number_of_candidate_feedbacks_requirements_MetOrNot)
                    except Exception as e:
                        number_of_candidate_feedbacks_requirements_MetOrNot=False
                        print("cheching requiremnet from feedback faild",e)

                    if number_of_candidate_feedbacks_requirements_MetOrNot:
                        
                        if 3>number_of_candidate_feedbacks_requirements_MetOrNot>0:
                            deduct_marks = number_of_candidate_feedbacks_requirements_MetOrNot*5
                            if overall_matching_score>70:
                                overall_matching_score -= deduct_marks
                                print(f'Diducting {deduct_marks} marks because {number_of_candidate_feedbacks_requirements_MetOrNot} requirements from  candidate feedback are not met ')

                        elif number_of_candidate_feedbacks_requirements_MetOrNot>=3:
                            
                            print(f'reducing score {overall_matching_score} to 60 becouse 3 or more the 3 requirements from candidate feedback are not met ')
                            overall_matching_score=55


                if requirementsFormFeedback:
                    prompt = (
                    f"You are a world-class HR Expert and Hiring Strategist with 40+ years of experience across technical and non-technical domains.\n\n"
                    f"Your job is to perform a *requirement-by-requirement audit* of a candidate’s resume against the job description requirements below.\n\n"
                    f"### Objective:\n"
                    f"Determine for each requirement in the Job Description whether the candidate meets it or not, based **only** on explicit evidence from the resume text.\n\n"
                    f"### Job Description Requirements:\n{requirementsFormFeedback}\n\n"
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
                    f"7. Be verry specific with every requirements if not met exactly say MetOrNot == no"
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

                    feedbackMachingWithCandidate =  gpt_models[0].invoke_model_with_backoff(prompt,Task= "Ask ai, feedback matching or not")
                    print('feedbackMachingWithCandidate :- ' ,feedbackMachingWithCandidate)
                    number_of_requirements_not_met = False 
                    try:
                        number_of_requirements_not_met = len([i for i in feedbackMachingWithCandidate if i["MetOrNot"].lower()=='no'])
                        print(f'Requirements not met from feedback :--',number_of_requirements_not_met)
                    except Exception as e:
                        number_of_requirements_not_met=False
                        print("cheching requiremnet from feedback faild",e)
                    if number_of_requirements_not_met:
                        
                        if 3>number_of_requirements_not_met>0:
                            deduct_marks = number_of_requirements_not_met*5
                            if overall_matching_score>70:
                                overall_matching_score -= deduct_marks
                                print(f'Diducting {deduct_marks} marks because {number_of_requirements_not_met} requirements from feedback are not met ')

                        elif number_of_requirements_not_met>=3:
                            
                            print(f'reducing score {overall_matching_score} to 60 becouse 3 or more the 3 requirements from feedback are not met ')
                            overall_matching_score=55

            # overall_matching_score=50 #testing
            if 1 <= overall_matching_score < 70:

                prompt = feedback_0_70_prompt.format(processed_text=processed_text, 
                                                     jdItem_extracted=jdItem_extracted, 
                                                     overall_Analysis=overall_Analysis)
                
                completion_text_rejection = gpt_models[0].invoke_model_with_backoff(prompt,Task= "Rejection for 1 <= overall_matching_score < 70:" )
                completion_text_rejection_for_candidate = completion_text_rejection.get("feedback_Candidate")
                completion_text_rejection= completion_text_rejection.get("feedback_Recruiter")
                

                completion_text_rejection = json.dumps(completion_text_rejection)        ### make it string again to store in db
                completion_text_rejection_for_candidate = json.dumps(completion_text_rejection_for_candidate)

                print_completion_text(f"rjection feedback for Recruiter {completion_text_rejection}")
                print_completion_text(f"rjection feedback for Candidate {completion_text_rejection_for_candidate}")
                rejection_feedback = completion_text_rejection
                rejectionFeedbackBySystemForApplicant = completion_text_rejection_for_candidate

                
                if overall_matching_score >= 40:
                    prompt = feedback_greater_the_40.format(processed_text=processed_text, 
                                                           job_desc=jdItem_extracted, 
                                                           overall_Analysis=overall_Analysis)
    
                    completion_text_approval= gpt_models[0].invoke_model_with_backoff(prompt,Task= "Score feedback  for >40")
                    print_completion_text(completion_text_approval)
                    scoreDetails = completion_text_approval.get("feedback_Recruiter")
                    scoreDetailsForApplicant = completion_text_approval.get("feedback_Candidate")

                    scoreDetails = json.dumps(scoreDetails)        ### make it string again to store in db
                    scoreDetailsForApplicant = json.dumps(scoreDetailsForApplicant)        ### make it string again to store in db


                    prompt = feedback_email_greaterthen_40_prompt.format(completion_text_approval=completion_text_approval)
                    emailFeedback = gpt_models[0].invoke_model_with_backoff(prompt,want_json=False)
                    print("feedback_for_email:-",emailFeedback)
            
            elif overall_matching_score >= 70:

                
                prompt = feedback_greaterthen_70_prompt.format(
                    processed_text=processed_text,
                    job_desc=job_desc,
                    overall_Analysis=overall_Analysis
                )

                completion_text_approval =gpt_models[0].invoke_model_with_backoff(prompt,Task= "Score feedback for >70")


                ###########################################
                print_completion_text(completion_text_approval)
                try:
                    # completion_text_approval = json.loads(completion_text_approval)
                    scoreDetails = completion_text_approval.get("feedback_Recruiter")
                    scoreDetailsForApplicant = completion_text_approval.get("feedback_Candidate")
                except Exception as e:
                    print("can't load scoreDetails and scoreDetailsForApplicant from json in >=70 scoreDetails")



                scoreDetails = json.dumps(scoreDetails)        ### make it string again to store in db
                scoreDetailsForApplicant = json.dumps(scoreDetailsForApplicant)        ### make it string again to store in db
                ###########################################

                prompt = feedback_email_greaterthen_70_prompt.format(completion_text_approval=completion_text_approval)
                emailFeedback = gpt_models[0].invoke_model_with_backoff(prompt,Task= "Score feedback for >70",want_json=False)

                print("feedback_for_email:-", emailFeedback)
                

                print("otherRequirements:-", otherRequirements)
                if otherRequirements:
                    prompt = check_mandatory_requirement_prompt.format(processed_text=processed_text, otherRequirements=otherRequirements)
                    analysis_result_json  = gpt_models[0].invoke_model_with_backoff(prompt,Task= "Cheching Mandatoey Requirements") 

                    print("analysis_result",analysis_result_json)
                    requirements_missing = analysis_result_json["analysis"]["requirements_missing"]
                    mandatory_skills_missing = analysis_result_json.get('mandatory_skills_missing')
                    print("mandatory_skills_missing:-", mandatory_skills_missing)
                    
                    if mandatory_skills_missing == "Yes":
                        print(f"mandatory Requirements is missing so actual score was {overall_matching_score} now making it to 60")
                        overall_matching_score = 60

                        prompt = feedback_mandatory_requirement_missing_prompt.format(
                            processed_text=processed_text, 
                            jdItem_extracted=jdItem_extracted, 
                            requirements_missing=requirements_missing)

                        completion_text_rejection =  gpt_models[0].invoke_model_with_backoff(prompt,Task= "Rejection when amndatory Not met")


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

            # update_sqs_queue(email, userId, referralId, job_ref_type) recently comented
            print("overall_matching_score", overall_matching_score)
        except Exception as e:
            print(f"An error occurred: {e}")
            if "JOB" in job_ref_type:
                update_cv_extract_in_dynamodb(jobs_table_name, partition_key_value, sort_key_prefix2, str(e) , 251, -1)
            else:
                update_cv_extract_in_dynamodb(table_name, partition_key_value, sort_key_prefix2, str(e) , 251, -1)
        
            update_sqs_queue(email, userId, referralId, job_ref_type) #recently comented
            return {"statusCode": 500, "body": {"error": str(e)}}
        
    elif reject_on_ctc_or_exp:
        overall_matching_score = 50
        

        if not name_of_the_candidate:              # if name of the candidate is not there just say 'you'
            name_of_the_candidate = 'your'
        reason  = get_reason_from_rejection_data(check_exp_data)
        rejectionFeedbackBySystemForApplicant = f"""Thank you for applying to {jobTitle}. After reviewing your profile, 
        we found a mismatch — your {reason} the requirement for this role. We encourage you to explore opportunities better 
        aligned with your background, 
        as we’d love to see you grow in the right role."""
        
        rejection_feedback = f"""{name_of_the_candidate} appled for {jobTitle} role. After reviewing his profile, we found a mismatch — his {reason} the requirement for this role."""
        rejection_feedback = json.dumps({"RecruiterNote":rejection_feedback})
    
    if "JOB" in job_ref_type:
        update_ref_response_in_dynamodb(jobs_table_name, partition_key_value, sort_key_prefix2, scoreDetails,scoreDetailsForApplicant, overall_matching_score, emailFeedback, rejection_feedback,rejectionFeedbackBySystemForApplicant,check_exp_data,reject_on_ctc_or_exp)
        
    else:
        update_ref_response_in_dynamodb(table_name, partition_key_value, sort_key_prefix2, scoreDetails,scoreDetailsForApplicant, overall_matching_score, emailFeedback, rejection_feedback,rejectionFeedbackBySystemForApplicant)
    
    update_sqs_queue(email, userId, referralId, job_ref_type)
    return {"statusCode": 200, "body": 
            {"Overall Matching Score": overall_matching_score}
        }


if __name__ == "__main__":
    
    
    # event ={'USER_PK': 'USR#EML#ask.72544@gmail.com', 'USER_DETAIL_SK': 'ID#', 'MATCHING_ENTITY': 'JOB_APP', 'ENTITY_SK': 'JOB#APP#ID#01KJCSD7G4CGQNQYEGWFK3V9VK'}
    
    # form submit flow event
    
    # event ={'USER_PK': 'USR#EML#syadavendra@gmail.com', 'USER_DETAIL_SK': 'ID#', 'ENTITY_SK': 'JOB#APP#ID#01KJC783RRGAJ1EXXEV9KARE8X', 'MATCHING_ENTITY': 'SOURCE_TYPE_JOB_APP', 'candidateParsedCvId': '01KJC77XNPRW652J3GSYCDXREP', 'sourceTypeCvAwsS3Details': {'resourceType': 'CAND_SUBMIT_CV_JOB', 'bucketName': 'worko-app-dev', 'filePath': 'candidate-submit-cvs/companies/01K47MSBKS79ACY0BM6Z8VS3F5/jobs/01KHZVWRAG1H29PNBX6FQ4RYJW/cvs', 'fileName': '01KJC779BZ9D6J9YA75T30P7WD.pdf'}}
    
    #request from move to aplicant from my database
    event = {'USER_PK': 'USR#EML#sahanasgp7@gmail.com', 'USER_DETAIL_SK': 'ID#', 'ENTITY_SK': 'JOB#APP#ID#01KJPQ9GK51XSH4JBDP6FKJRGB', 'MATCHING_ENTITY': 'SOURCE_TYPE_JOB_APP', 'candidateParsedCvId': '01KHXASXJ694280F3KY45AK6MR', 'sourceTypeCvAwsS3Details': {'resourceType': 'CORP_CAND_BULK_CV_UPLOAD', 'bucketName': 'worko-corporate-cand-profile-dev', 'filePath': 'companies/01K47MSBKS79ACY0BM6Z8VS3F5/bulk-cvs', 'fileName': '01KHXAS6YPNDWRDTJ1GVECX7G1.pdf'}}

    lambda_handler(event, None)



    
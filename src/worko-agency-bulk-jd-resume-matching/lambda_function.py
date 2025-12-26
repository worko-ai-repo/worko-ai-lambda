import boto3
import requests
import random
import os
# from dotenv import load_dotenv
# load_dotenv()
import time
import json
from typing import List, Tuple, Dict, Any, Optional, Union
from botocore.exceptions import ClientError
from urllib.parse import unquote_plus
# iac deploy 11
dynamodb = boto3.resource('dynamodb')
from google.cloud import firestore
from google.oauth2 import service_account
from datetime import datetime, timezone

from utils import *

class AzureOpenAIClient:
    """Client for Azure OpenAI API with retry logic."""
    
    DEFAULT_TEMPERATURE = 0.3
    DEFAULT_API_VERSION = "2024-05-01-preview"
    REQUEST_TIMEOUT = 30  # seconds
    
    def __init__(self, azure_openai_secret: Dict[str, str]):
        """Initialize Azure OpenAI client.
        
        Args:
            azure_openai_secret: Dict containing:
                - AZURE_OPENAI_ENDPOINT
                - deployment_name
                - api_key
                - AZURE_OPENAI_API_VERSION (optional)
        """
        if not isinstance(azure_openai_secret, dict):
            raise TypeError("azure_openai_secret must be a dictionary")
        
        self.endpoint = azure_openai_secret.get("AZURE_OPENAI_ENDPOINT", "")
        self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT", "")
        self.api_version = azure_openai_secret.get(
            "AZURE_OPENAI_API_VERSION", 
            self.DEFAULT_API_VERSION
        )
        self.api_key = azure_openai_secret.get("AZURE_OPENAI_API_KEY", "")
        
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
        for attempt in range(max_retries):
            print("Task to Ai is :- ",Task)
            try:
                return self.invoke_model(system_content, prompt, want_json)
            
            except requests.exceptions.HTTPError as e:
                # Check for rate limiting (429) or server errors (5xx)
                if e.response.status_code in [429, 500, 502, 503, 504]:
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
                json=data,
                timeout=self.REQUEST_TIMEOUT
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
                    json=data,
                    timeout=self.REQUEST_TIMEOUT
                )
                response.raise_for_status()
                result = response.json()
                
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

    def update_firestore_document_with_scoring_data(self,collection_name: str, doc_id: str,update_data,status:str ):

        if update_data and status == "COMPLETED":
            try:
                doc_ref = self.db.collection(collection_name).document(doc_id)
                doc_ref.update(update_data)
                print(f"Updated Firestore document {doc_id} status : completed and update_data : {update_data}")
                return True
            except Exception as e:
                print("failed to updated 2ed step (score details) data in collection_name :-- ",collection_name,"doc_id :--",doc_id,"error is", e)
                return False


        else:
            try:
                doc_ref = self.db.collection(collection_name).document(doc_id)
                doc_ref.update({
                    "matchingScore" : 0,
                    "cvExtractedParsed":update_data,
                    "processingStatus":status

                })
                print(f"Updated Firestore document {doc_id} with  status :IN PROGRESS")
            except Exception as e:
                print("failed to updated 1st step (cvExtractparsed) data in collection_name :-- ",collection_name,"doc_id :--",doc_id,"error is", e)
                return False

    def get_document_firstore(self,collection_name,doc_id):
        doc_ref = self.db.collection(collection_name).document(doc_id)
        return doc_ref.get().to_dict()
    
def process_cv(processed_text: str,OpenAIClient) -> Tuple[str, Dict[str, str]]:
    print("Processing cv for cvexractparesed")

    processed_text = " ".join(processed_text.split())

    """
    Process CV text and extract structured information.
    
    Args:
        processed_text: Raw text from CV
        
    Returns:
        Tuple containing:
        - Extracted CV text in template format
        - Parsed CV information as structured JSON
    """
    cv_extract_template = '''
    Name:
    Email:
    Experience in years:
    Achievements:
    Technical skills:
    Soft skills:
    Core skills:
    Education:
    Industry experience:
    Responsibilities:
    Achievements against responsibility:
    Certifications:
    Strength:
    Experience type (leadership, Mid management, Senior management, Team lead, Individual contributor):
    Team handling experience:
    Industry type (B2B, D2C, C2C, B2C):
    '''.strip()

    cv_parsed_template = {
        "candidateName": "Parsing Failed",
        "candidateExperience": "",
        "candidateCurrentCompany": "",
        "candidateCurrentDesignation": "",
        "candidateEmail": "",
        "candidatePhoneNumber": "",
        "candidateLocation": ""
    }

    if not processed_text:
        return "Unfortunately, we are not able to read your resume", cv_parsed_template

    try:
        # First extraction for CV details
        cv_prompt = (f"Extract professional CV/resume information from the following text. "
                    f"This is for legitimate recruitment purposes.\n\n"
                    f"CV TEXT: {processed_text}\n\n"
                    f"EXTRACTION TEMPLATE:\n{cv_extract_template}")

        cv_extract = OpenAIClient.invoke_model_with_backoff(cv_prompt, Task= "get cvExtract in str",want_json=False)
        # cv_extract = extract_text_from_nova(cv_content)
        
        cv_extract = clean_text(cv_extract)
        print("cv_extract-------",cv_extract)
        
        # Second extraction for parsed details
        parsed_prompt = (
            f"You are an expert HR specialized in resume analysis and extracting structured data.\n\n"

            f"Resume text:\n{processed_text}\n\n"

            f"*** RULE: If you don't find any data in the resume ***\n"
            f"- If the value is a number → use 0\n"
            f"- If the value is a boolean → use false\n"
            f"- If the value is a string → use an empty string \"\"\n"
            f"- If the candidate is a fresher or not currently working → set candidateCurrentCompany = \"\"\n\n"

            f"*** Mandatory data to find in the resume ***\n"
            f"These fields MUST always be present in the output:\n"
            f"1. candidateName\n"
            f"2. candidateCurrentDesignation\n"
            f"3. candidateCurrentCompany\n"
            f"4. candidateTotalYOE\n"
            f"5. candidateLocation\n\n"

            f"*** Last Check ***\n"
            f"- All numbers must be integers.\n"
            f"- Ensure ALL mandatory fields are present.\n"
            f"- Output must be valid JSON only.\n"
            f"- candidateExperience must be a numeric value (int or decimal like 6, 6.5, 10.2).\n"
            f"- candidatePhoneNumber must be in format: +91XXXXXXXXXX (no spaces).\n\n"

            f"*** Output Format (JSON only) ***\n"
            f"{{{{\n"
            f"  \"candidateName\": \"\",\n"
            f"  \"candidateEmail\": \"\",\n"
            f"  \"candidatePhoneNumber\": \"\",\n"
            f"  \"candidateNumber\": 0,\n"
            f"  \"candidatePhoneCountryCode\": 0,\n"
            f"  \"candidateCurrentCompany\": \"\",\n"
            f"  \"candidateCurrentDesignation\": \"\",\n"
            f"  \"candidateExperience\": 0,\n"
            f"  \"candidateTotalYOE\": 0,\n"
            f"  \"candidateRelevantYOE\": 0,\n"
            f"  \"candidateCurrentCTC\": 0,\n"
            f"  \"candidateExpectedCTC\": 0,\n"
            f"  \"candidateNoticePeriod\": 0,\n"
            f"  \"candidateLocation\": \"\",\n"
            f"  \"candidateReadyToRelocate\": false,\n"
            f"  \"isNoticePeriodNegotiable\": false\n"
            f"}}}}\n"
        )

        cv_extracted_parsed = OpenAIClient.invoke_model_with_backoff(parsed_prompt,Task= "get cvExtractparsed" )
        current_timestamp = datetime.now().isoformat()
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

        cv_extracted_parsed2 = OpenAIClient.invoke_model_with_backoff(prompt,Task = "Agency Resume parsing for skills and pref")
        merged = {**cv_extracted_parsed, **cv_extracted_parsed2}
        
        return cv_extract, merged
        
    except requests.exceptions.HTTPError as e:
        print(" Error occured : from open ai asuure.",e)
        return "Error processing CV", cv_parsed_template
    except Exception as e:
        print(f"Error processing CV: {str(e)}")
        return "Error processing CV", cv_parsed_template


def jd_resume_matching(job_desc, processed_text, cv_extract, cv_extracted_parsed,OpenAIClient,update_doc_id):

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
          
    content = OpenAIClient.invoke_model_with_backoff(prompt, Task= "Check Tech or Non-Tech JD", want_json=False)

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
        if found_text == "Non-Technical":
            print("I am in Non-Tech")
            # Determine the experience level of JD
            prompt = (
                        f"Human: Based on the following job description, please analyze the required years of experience:\n\n"
                        f"{job_desc}\n\n"
                        f"Human: Strictly determine the experience level using ONLY these criteria:\n"
                        f"- If years of experience is greater than 12: superior\n"
                        f"- If years of experience is between 5 and 12 (inclusive): senior\n"
                        f"- If years of experience is between 1 and 5 (exclusive): junior\n"
                        f"- If years of experience is less than 1: fresher\n\n"
                        f"Respond EXACTLY in this JSON format without any additional fields or explanations:\n"
                        f"{{\n"
                        f"  \"experience_level\": \"<determined_level>\",\n"
                        f"  \"criteria_matched\": \"<exact_matching_criteria_text>\"\n"
                        f"}}\n\n"
                        f"Do not include any other fields like 'reasoning' or additional commentary. Only provide the specified JSON output."
                    )

            completion_text = OpenAIClient.invoke_model_with_backoff(prompt, Task= "Check JD experience level",want_json=False)
            print("I am in Non-Tech",content )
            print_completion_text(completion_text)
                      
            if "superior" in completion_text:
                print("Experience Level - Non-Tech superior")
                steps = [
                                ("Here is the most relevant sentence in the context: Evaluate the resume against the job description based on the following 4 parameters and their respective weighted scores:"
                                    "1. Experience (5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                    "2. Responsibilities (10 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                    "3. Achievements (5 points) - Look for exact keyword matches or direct mentions of achievements in the resume."
                                    "4. Core Skills/Core Competencies (10 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                    "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 30 (27), cap it at 27."
                                    "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                    "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                    "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                ),
                                ("Here is the most relevant sentence in the context: Mandatory Skills Evaluation Framework (Total: 40 Points)"
                                    "SECTION A: SKILL-BASED EVALUATION (24 points, 60% weight)"
                                        "List all mandatory technical/core skills from the job description."
                                        "Assign equal weight to each skill:"
                                        "- If there are n mandatory skills, each skill = 24/n points"
                                        "For each skill:"
                                        "- If the candidate has the skill → award full points for that skill."
                                        "If not → 0 points."
                                        "Section A Score = Sum of points for all matched skills."
                                        "Example:"
                                        "3 mandatory skills: Java, Spring Boot, DevOps"
                                        "Each skill = 8 points"
                                        "Candidate has Java & Spring Boot only"
                                        "Section A Score = 8 + 8 + 0 = 16 points"
                                    "SECTION B: NON-SKILL-BASED EVALUATION (16 points, 40% weight)"
                                        "List all non-skill mandatory requirements (education, company, location, etc.)."
                                        "If the candidate meets ALL non-skill requirements → 16 points."
                                        "If ANY non-skill requirement is missing → 0 points."
                                        "SCORING CALCULATION"
                                        "Final Score = Section A Score + Section B Score"
                                        "Maximum: 40 points"
                                    "Provide results in JSON format: {\"score\": [0-40], \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                ),
                                ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
                                    "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                    "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 10 points to the Matching Score."
                                    "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 10 points (9) to the Matching Score."
                                    "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 10 points (5) to the Matching Score."
                                    "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 10 points (7.5) to the Matching Score."
                                    "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 10 points (8) to the Matching Score."
                                    "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                    "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
                                ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                    "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                    "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                    " 2: RESUME ANALYSIS"
                                    "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                    "RESUME KEYWORD WEIGHTING RULES:"
                                    "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                    "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                    "- If keyword appears in skills section or technical skills: Award 2 points"
                                    "- If keyword appears in education/certification section: Award 1 point"
                                    "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                    "- If keyword is not present: Award 0 points"
                                    "STEP 3: MATCHING AND SCORING"
                                    "For each of the 15 keywords:"
                                    "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                    "2. Calculate match score using this formula:"
                                    "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                    "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                    "   - If Resume Weight = 0: Award 0 points"
                                    "STEP 4: FINAL CALCULATION"
                                    "1. Sum up all 15 keyword match scores"
                                    "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                    "3. If this sum is 18 points or less, use the exact sum as the final score"
                                    "OUTPUT FORMAT:"
                                    "Present results in JSON format:"
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                    "VALIDATION RULES:"
                                    "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                    "- Do not make assumptions about implied skills or experience"
                                    "- Weight keywords based strictly on their placement and context within resume sections"
                                    "- If a keyword appears in multiple sections, use the highest applicable weight"
                                )
                            ]
            elif "senior" in completion_text:
                print("Experience Level - Non-Tech senior")
                steps = [
                                ("Here is the most relevant sentence in the context: Evaluate the resume against the job description based on the following 5 parameters and their respective weighted scores:"
                                             "1. Experience (5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                             "2. Responsibilities (10 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                             "3. Achievements (5 points) - Look for exact keyword matches or direct mentions of achievements in the resume."
                                             "4. Soft Skills (5 points) - Look for exact keyword matches or direct mentions of soft skills in the resume."
                                             "5. Core Skills/Core Competencies (5 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                             "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 30 (27), cap it at 27"
                                             "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                             "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                             "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                ),
                                ("Here is the most relevant sentence in the context: Mandatory Skills Evaluation Framework (Total: 40 Points)"
                                    "SECTION A: SKILL-BASED EVALUATION (24 points, 60% weight)"
                                        "List all mandatory technical/core skills from the job description."
                                        "Assign equal weight to each skill:"
                                        "- If there are n mandatory skills, each skill = 24/n points"
                                        "For each skill:"
                                        "- If the candidate has the skill → award full points for that skill."
                                        "If not → 0 points."
                                        "Section A Score = Sum of points for all matched skills."
                                        "Example:"
                                        "3 mandatory skills: Java, Spring Boot, DevOps"
                                        "Each skill = 8 points"
                                        "Candidate has Java & Spring Boot only"
                                        "Section A Score = 8 + 8 + 0 = 16 points"
                                    "SECTION B: NON-SKILL-BASED EVALUATION (16 points, 40% weight)"
                                        "List all non-skill mandatory requirements (education, company, location, etc.)."
                                        "If the candidate meets ALL non-skill requirements → 16 points."
                                        "If ANY non-skill requirement is missing → 0 points."
                                        "SCORING CALCULATION"
                                        "Final Score = Section A Score + Section B Score"
                                        "Maximum: 40 points"
                                    "Provide results in JSON format: {\"score\": [0-40], \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                ),
                                ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
                                             "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 10 points to the Matching Score."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 10 points (9) to the Matching Score."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 10 points (5) to the Matching Score."
                                             "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 10 points (7.5) to the Matching Score."
                                             "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 10 points (8) to the Matching Score."
                                             "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                             "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
                                ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                    "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                    "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                    " 2: RESUME ANALYSIS"
                                    "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                    "RESUME KEYWORD WEIGHTING RULES:"
                                    "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                    "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                    "- If keyword appears in skills section or technical skills: Award 2 points"
                                    "- If keyword appears in education/certification section: Award 1 point"
                                    "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                    "- If keyword is not present: Award 0 points"
                                    "STEP 3: MATCHING AND SCORING"
                                    "For each of the 15 keywords:"
                                    "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                    "2. Calculate match score using this formula:"
                                    "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                    "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                    "   - If Resume Weight = 0: Award 0 points"
                                    "STEP 4: FINAL CALCULATION"
                                    "1. Sum up all 15 keyword match scores"
                                    "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                    "3. If this sum is 18 points or less, use the exact sum as the final score"
                                    "OUTPUT FORMAT:"
                                    "Present results in JSON format:"
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                    "VALIDATION RULES:"
                                    "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                    "- Do not make assumptions about implied skills or experience"
                                    "- Weight keywords based strictly on their placement and context within resume sections"
                                    "- If a keyword appears in multiple sections, use the highest applicable weight"
                                )
                            ]
                            
            elif "junior" in completion_text:
                print("Experience Level - Non-Tech junior")
                steps = [
                                ("Here is the most relevant sentence in the context: Evaluate the resume against the job description based on the following 5 parameters and their respective weighted scores:"
                                             "1. Experience (5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                             "2. Responsibilities (10 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                             "3. Achievements (5 points) - Look for exact keyword matches or direct mentions of achievements in the resume."
                                             "4. Soft Skills (5 points) - Look for exact keyword matches or direct mentions of soft skills in the resume."
                                             "5. Core Skills/Core Competencies (5 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                             "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 30 (27), cap it at 27"
                                             "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                             "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                             "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                ),
                                ("Here is the most relevant sentence in the context: Mandatory Skills Evaluation Framework (Total: 40 Points)"
                                    "SECTION A: SKILL-BASED EVALUATION (24 points, 60% weight)"
                                        "List all mandatory technical/core skills from the job description."
                                        "Assign equal weight to each skill:"
                                        "- If there are n mandatory skills, each skill = 24/n points"
                                        "For each skill:"
                                        "- If the candidate has the skill → award full points for that skill."
                                        "If not → 0 points."
                                        "Section A Score = Sum of points for all matched skills."
                                        "Example:"
                                        "3 mandatory skills: Java, Spring Boot, DevOps"
                                        "Each skill = 8 points"
                                        "Candidate has Java & Spring Boot only"
                                        "Section A Score = 8 + 8 + 0 = 16 points"
                                    "SECTION B: NON-SKILL-BASED EVALUATION (16 points, 40% weight)"
                                        "List all non-skill mandatory requirements (education, company, location, etc.)."
                                        "If the candidate meets ALL non-skill requirements → 16 points."
                                        "If ANY non-skill requirement is missing → 0 points."
                                        "SCORING CALCULATION"
                                        "Final Score = Section A Score + Section B Score"
                                        "Maximum: 40 points"
                                    "Provide results in JSON format: {\"score\": [0-40], \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                ),
                                ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
                                             "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 10 points to the Matching Score."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 10 points (9) to the Matching Score."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 10 points (5) to the Matching Score."
                                             "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 10 points (7.5) to the Matching Score."
                                             "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 10 points (8) to the Matching Score."
                                             "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                             "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
                                ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                    "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                    "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                    " 2: RESUME ANALYSIS"
                                    "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                    "RESUME KEYWORD WEIGHTING RULES:"
                                    "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                    "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                    "- If keyword appears in skills section or technical skills: Award 2 points"
                                    "- If keyword appears in education/certification section: Award 1 point"
                                    "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                    "- If keyword is not present: Award 0 points"
                                    "STEP 3: MATCHING AND SCORING"
                                    "For each of the 15 keywords:"
                                    "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                    "2. Calculate match score using this formula:"
                                    "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                    "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                    "   - If Resume Weight = 0: Award 0 points"
                                    "STEP 4: FINAL CALCULATION"
                                    "1. Sum up all 15 keyword match scores"
                                    "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                    "3. If this sum is 18 points or less, use the exact sum as the final score"
                                    "OUTPUT FORMAT:"
                                    "Present results in JSON format:"
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                    "VALIDATION RULES:"
                                    "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                    "- Do not make assumptions about implied skills or experience"
                                    "- Weight keywords based strictly on their placement and context within resume sections"
                                    "- If a keyword appears in multiple sections, use the highest applicable weight"
                                )
                            ]
                            
            elif "fresher" in completion_text:
                print("Experience Level - Non-Tech fresher")
                steps = [
                                ("Here is the most relevant sentence in the context: Evaluate the resume against the job description based on the following 2 parameters and their respective weighted scores:"
                                             "1. Experience (10 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                             "2. Soft Skills (15 points) - Look for exact keyword matches or direct mentions of soft skills in the resume."
                                             "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 25 (22.5), cap it at 22.5."
                                             "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                             "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                             "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                ),
                                ("Here is the most relevant sentence in the context: Additionally, check for any specific relevant experience mentioned in the job description:"
                                            "If specific relevant Project/Internship/Experience/skills is mentioned as mandatory in the job description and it is not present in the resume, add 0% of 25 points to the Matching Score."
                                            "If specific relevant Project/Internship/Experience/skills is mentioned as mandatory in the job description and it is present in the resume, add 90% of 25 points (22.5) to the Matching Score."
                                            "If specific relevant Project/Internship/Experience/skills is mentioned as non-mandatory or preferred in the job description and it is present in the resume, add 90% of 25 points (22.5) to the Matching Score."
                                            "If specific relevant Project/Internship/Experience/skills is mentioned as non-mandatory or preferred in the job description and it is not present in the resume, add 60% of 25 points (15) to the Matching Score."
                                            "Before calculating the score, identify and list the most relevant sentences from the job description that specify the required or preferred experience, and the corresponding sentences from the resume that match or do not match these requirements."
                                            "Show the points given. Present it in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                            "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
                                ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
                                             "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 30 points to the Matching Score."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 30 points (27) to the Matching Score."
                                             "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 30 points (15) to the Matching Score."
                                             "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 30 points (22.5) to the Matching Score."
                                             "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 30 points (24) to the Matching Score."
                                             "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                             "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
                                ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                    "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                    "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                    " 2: RESUME ANALYSIS"
                                    "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                    "RESUME KEYWORD WEIGHTING RULES:"
                                    "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                    "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                    "- If keyword appears in skills section or technical skills: Award 2 points"
                                    "- If keyword appears in education/certification section: Award 1 point"
                                    "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                    "- If keyword is not present: Award 0 points"
                                    "STEP 3: MATCHING AND SCORING"
                                    "For each of the 15 keywords:"
                                    "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                    "2. Calculate match score using this formula:"
                                    "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                    "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                    "   - If Resume Weight = 0: Award 0 points"
                                    "STEP 4: FINAL CALCULATION"
                                    "1. Sum up all 15 keyword match scores"
                                    "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                    "3. If this sum is 18 points or less, use the exact sum as the final score"
                                    "OUTPUT FORMAT:"
                                    "Present results in JSON format:"
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                    "VALIDATION RULES:"
                                    "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                    "- Do not make assumptions about implied skills or experience"
                                    "- Weight keywords based strictly on their placement and context within resume sections"
                                    "- If a keyword appears in multiple sections, use the highest applicable weight"
                                )
                            ]
    
        else:
            # Determine the experience level of JD

            prompt = (
                        f"Human: Based on the following job description, please analyze the required years of experience:\n\n"
                        f"{job_desc}\n\n"
                        f"Human: Strictly determine the experience level using ONLY these criteria:\n"
                        f"- If years of experience is greater than 12: superior\n"
                        f"- If years of experience is between 5 and 12 (inclusive): senior\n"
                        f"- If years of experience is between 1 and 5 (exclusive): junior\n"
                        f"- If years of experience is less than 1: fresher\n\n"
                        f"Respond EXACTLY in this JSON format without any additional fields or explanations:\n"
                        f"{{\n"
                        f"  \"experience_level\": \"<determined_level>\",\n"
                        f"  \"criteria_matched\": \"<exact_matching_criteria_text>\"\n"
                        f"}}\n\n"
                        f"Do not include any other fields like 'reasoning' or additional commentary. Only provide the specified JSON output."
                    )

            completion_text = OpenAIClient.invoke_model_with_backoff(prompt,Task="check exp level of tech guy",want_json=False)
            print_completion_text(completion_text)
            
            if "superior" in completion_text:
                print("Experience Level - Tech superior")
                steps = [
                            ("Here is the most relevant sentence in the context: Rate the resume against the job description based on the following 5 parameters:"
                                     "1. Technical Skills (weighted score: 10 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                     "2. Experience (weighted score: 5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                     "3. Education (weighted score: 5 points) - If no specific educational requirement is mentioned, award full points for a relevant degree, regardless of the institution."
                                     "4. Responsibilities (weighted score: 10 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                     "5. Achievements (weighted score: 5 points) - Look for exact keyword matches or direct mentions of achievements in the resume."
                                     "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 35 (31.5), cap it at 31.5"
                                    "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                    "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                    "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                ),
                                ("Here is the most relevant sentence in the context: Mandatory Skills Evaluation Framework (Total: 40 Points)"
                                    "SECTION A: SKILL-BASED EVALUATION (24 points, 60% weight)"
                                        "List all mandatory technical/core skills from the job description."
                                        "Assign equal weight to each skill:"
                                        "- If there are n mandatory skills, each skill = 24/n points"
                                        "For each skill:"
                                        "- If the candidate has the skill → award full points for that skill."
                                        "If not → 0 points."
                                        "Section A Score = Sum of points for all matched skills."
                                        "Example:"
                                        "3 mandatory skills: Java, Spring Boot, DevOps"
                                        "Each skill = 8 points"
                                        "Candidate has Java & Spring Boot only"
                                        "Section A Score = 8 + 8 + 0 = 16 points"
                                    "SECTION B: NON-SKILL-BASED EVALUATION (16 points, 40% weight)"
                                        "List all non-skill mandatory requirements (education, company, location, etc.)."
                                        "If the candidate meets ALL non-skill requirements → 16 points."
                                        "If ANY non-skill requirement is missing → 0 points."
                                        "SCORING CALCULATION"
                                        "Final Score = Section A Score + Section B Score"
                                        "Maximum: 40 points"
                                    "Provide results in JSON format: {\"score\": [0-40], \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                ),
                            ("Here is the most relevant sentence in the context: Check if any specific educational requirement is asked for in the job description (e.g., specific certification, graduation from a Tier 1 institute, specific degree type, etc.)."
                                     "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                     "For the Education parameter (weighted score: 5 points):"
                                     "- If a specific educational requirement (like graduation from a Tier 1 institute) is mandatory in the job description:"
                                     "  - If the requirement is present in the resume, add 4.5 points (90% of 5 points) to the Matching Score."
                                     "  - If the requirement is not present in the resume, add 0 points to the Matching Score."
                                     "- If a specific educational requirement (like graduation from a Tier 1 institute) is preferred in the job description:"
                                     "  - If the requirement is present in the resume, add 4.5 points (90% of 5 points) to the Matching Score."
                                     "  - If the requirement is not present in the resume, add 2.5 points (50% of 5 points) to the Matching Score."
                                     "- If no specific educational requirement is mentioned in the job description:"
                                     "  - If the resume has a Tier 1 institute educational detail, add 4 points (80% of 5 points) to the Matching Score."
                                     "  - If the resume does not have a Tier 1 institute educational detail, add 3.75 points (75% of 5 points) to the Matching Score."
                                     "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                     "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                ),
                            ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                    "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                    "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                    " 2: RESUME ANALYSIS"
                                    "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                    "RESUME KEYWORD WEIGHTING RULES:"
                                    "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                    "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                    "- If keyword appears in skills section or technical skills: Award 2 points"
                                    "- If keyword appears in education/certification section: Award 1 point"
                                    "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                    "- If keyword is not present: Award 0 points"
                                    "STEP 3: MATCHING AND SCORING"
                                    "For each of the 15 keywords:"
                                    "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                    "2. Calculate match score using this formula:"
                                    "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                    "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                    "   - If Resume Weight = 0: Award 0 points"
                                    "STEP 4: FINAL CALCULATION"
                                    "1. Sum up all 15 keyword match scores"
                                    "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                    "3. If this sum is 18 points or less, use the exact sum as the final score"
                                    "OUTPUT FORMAT:"
                                    "Present results in JSON format:"
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                    "VALIDATION RULES:"
                                    "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                    "- Do not make assumptions about implied skills or experience"
                                    "- Weight keywords based strictly on their placement and context within resume sections"
                                    "- If a keyword appears in multiple sections, use the highest applicable weight"
                                )
                    ]
                    
            elif "senior" in completion_text:
                print("Experience Level - Tech senior")
                steps = [
                            ("Here is the most relevant sentence in the context: Rate the resume against the job description based on the following 5 parameters:"
                                     "1. Technical Skills (weighted score: 15 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                     "2. Experience (weighted score: 5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                     "3. Education (weighted score: 5 points) - If no specific educational requirement is mentioned, award full points for a relevant degree, regardless of the institution."
                                     "4. Responsibilities (weighted score: 5 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                     "5. Achievements (weighted score: 5 points) - Look for exact keyword matches or direct mentions of achievements in the resume."
                                     "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 35 (31.5), cap it at 31.5"
                                    "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                    "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                    "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                ),
                                ("Here is the most relevant sentence in the context: Mandatory Skills Evaluation Framework (Total: 40 Points)"
                                    "SECTION A: SKILL-BASED EVALUATION (24 points, 60% weight)"
                                        "List all mandatory technical/core skills from the job description."
                                        "Assign equal weight to each skill:"
                                        "- If there are n mandatory skills, each skill = 24/n points"
                                        "For each skill:"
                                        "- If the candidate has the skill → award full points for that skill."
                                        "If not → 0 points."
                                        "Section A Score = Sum of points for all matched skills."
                                        "Example:"
                                        "3 mandatory skills: Java, Spring Boot, DevOps"
                                        "Each skill = 8 points"
                                        "Candidate has Java & Spring Boot only"
                                        "Section A Score = 8 + 8 + 0 = 16 points"
                                    "SECTION B: NON-SKILL-BASED EVALUATION (16 points, 40% weight)"
                                        "List all non-skill mandatory requirements (education, company, location, etc.)."
                                        "If the candidate meets ALL non-skill requirements → 16 points."
                                        "If ANY non-skill requirement is missing → 0 points."
                                        "SCORING CALCULATION"
                                        "Final Score = Section A Score + Section B Score"
                                        "Maximum: 40 points"
                                    "Provide results in JSON format: {\"score\": [0-40], \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                ),
                            ("Here is the most relevant sentence in the context: Check if any specific educational requirement is asked for in the job description (e.g., specific certification, graduation from a Tier 1 institute, specific degree type, etc.)."
                                     "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                     "For the Education parameter (weighted score: 5 points):"
                                     "- If a specific educational requirement (like graduation from a Tier 1 institute) is mandatory in the job description:"
                                     "  - If the requirement is present in the resume, add 4.5 points (90% of 5 points) to the Matching Score."
                                     "  - If the requirement is not present in the resume, add 0 points to the Matching Score."
                                     "- If a specific educational requirement (like graduation from a Tier 1 institute) is preferred in the job description:"
                                     "  - If the requirement is present in the resume, add 4.5 points (90% of 5 points) to the Matching Score."
                                     "  - If the requirement is not present in the resume, add 2.5 points (50% of 5 points) to the Matching Score."
                                     "- If no specific educational requirement is mentioned in the job description:"
                                     "  - If the resume has a Tier 1 institute educational detail, add 4 points (80% of 5 points) to the Matching Score."
                                     "  - If the resume does not have a Tier 1 institute educational detail, add 3.75 points (75% of 5 points) to the Matching Score."
                                     "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                     "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                ),
                            ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                    "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                    "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                    " 2: RESUME ANALYSIS"
                                    "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                    "RESUME KEYWORD WEIGHTING RULES:"
                                    "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                    "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                    "- If keyword appears in skills section or technical skills: Award 2 points"
                                    "- If keyword appears in education/certification section: Award 1 point"
                                    "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                    "- If keyword is not present: Award 0 points"
                                    "STEP 3: MATCHING AND SCORING"
                                    "For each of the 15 keywords:"
                                    "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                    "2. Calculate match score using this formula:"
                                    "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                    "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                    "   - If Resume Weight = 0: Award 0 points"
                                    "STEP 4: FINAL CALCULATION"
                                    "1. Sum up all 15 keyword match scores"
                                    "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                    "3. If this sum is 18 points or less, use the exact sum as the final score"
                                    "OUTPUT FORMAT:"
                                    "Present results in JSON format:"
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                    "VALIDATION RULES:"
                                    "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                    "- Do not make assumptions about implied skills or experience"
                                    "- Weight keywords based strictly on their placement and context within resume sections"
                                    "- If a keyword appears in multiple sections, use the highest applicable weight"
                                )
                        ]
                        
            elif "junior" in completion_text:
                print("Experience Level - Tech junior")
                steps = [
                            ("Here is the most relevant sentence in the context: Rate the resume against the job description based on the following 5 parameters:"
                                     "1. Technical Skills (weighted score: 5 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                     "2. Experience (weighted score: 10 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                     "3. Education (weighted score: 5 points) - If no specific educational requirement is mentioned, award full points for a relevant degree, regardless of the institution."
                                     "4. Responsibilities (weighted score: 5 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                     "5. Soft Skills (weighted score: 5 points) - Look for exact keyword matches or direct mentions of soft skills in the resume."
                                     "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 30 (27), cap it at 27"
                                    "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                    "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                    "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                ),
                            ("Here is the most relevant sentence in the context: Mandatory Skills Evaluation Framework (Total: 40 Points)"
                                    "SECTION A: SKILL-BASED EVALUATION (24 points, 60% weight)"
                                        "List all mandatory technical/core skills from the job description."
                                        "Assign equal weight to each skill:"
                                        "- If there are n mandatory skills, each skill = 24/n points"
                                        "For each skill:"
                                        "- If the candidate has the skill → award full points for that skill."
                                        "If not → 0 points."
                                        "Section A Score = Sum of points for all matched skills."
                                        "Example:"
                                        "3 mandatory skills: Java, Spring Boot, DevOps"
                                        "Each skill = 8 points"
                                        "Candidate has Java & Spring Boot only"
                                        "Section A Score = 8 + 8 + 0 = 16 points"
                                    "SECTION B: NON-SKILL-BASED EVALUATION (16 points, 40% weight)"
                                        "List all non-skill mandatory requirements (education, company, location, etc.)."
                                        "If the candidate meets ALL non-skill requirements → 16 points."
                                        "If ANY non-skill requirement is missing → 0 points."
                                        "SCORING CALCULATION"
                                        "Final Score = Section A Score + Section B Score"
                                        "Maximum: 40 points"
                                    "Provide results in JSON format: {\"score\": [0-40], \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                ),
                            ("Here is the most relevant sentence in the context: Check if any specific educational requirement is asked for in the job description (e.g., specific certification, graduation from a Tier 1 institute, specific degree type, etc.)."
                                     "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                     "For the Education parameter (weighted score: 10 points):"
                                     "- If a specific educational requirement (like graduation from a Tier 1 institute) is mandatory in the job description:"
                                     "  - If the requirement is present in the resume, add 9 points (90% of 10 points) to the Matching Score."
                                     "  - If the requirement is not present in the resume, add 0 points to the Matching Score."
                                     "- If a specific educational requirement (like graduation from a Tier 1 institute) is preferred in the job description:"
                                     "  - If the requirement is present in the resume, add 9 points (90% of 10 points) to the Matching Score."
                                     "  - If the requirement is not present in the resume, add 5 points (50% of 10 points) to the Matching Score."
                                     "- If no specific educational requirement is mentioned in the job description:"
                                     "  - If the resume has a Tier 1 institute educational detail, add 8 points (80% of 10 points) to the Matching Score."
                                     "  - If the resume does not have a Tier 1 institute educational detail, add 7.5 points (75% of 10 points) to the Matching Score."
                                     "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                     "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                ),
                            ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                    "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                    "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                    " 2: RESUME ANALYSIS"
                                    "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                    "RESUME KEYWORD WEIGHTING RULES:"
                                    "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                    "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                    "- If keyword appears in skills section or technical skills: Award 2 points"
                                    "- If keyword appears in education/certification section: Award 1 point"
                                    "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                    "- If keyword is not present: Award 0 points"
                                    "STEP 3: MATCHING AND SCORING"
                                    "For each of the 15 keywords:"
                                    "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                    "2. Calculate match score using this formula:"
                                    "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                    "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                    "   - If Resume Weight = 0: Award 0 points"
                                    "STEP 4: FINAL CALCULATION"
                                    "1. Sum up all 15 keyword match scores"
                                    "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                    "3. If this sum is 18 points or less, use the exact sum as the final score"
                                    "OUTPUT FORMAT:"
                                    "Present results in JSON format:"
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                    "VALIDATION RULES:"
                                    "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                    "- Do not make assumptions about implied skills or experience"
                                    "- Weight keywords based strictly on their placement and context within resume sections"
                                    "- If a keyword appears in multiple sections, use the highest applicable weight"
                                )
                        ]
                        
            elif "fresher" in completion_text:
                print("Experience Level - Tech fresher")
                steps = [
                            ("Here is the most relevant sentence in the context: Rate the resume against the job description based on the following 4 parameters:"
                                     "1. Technical Skills (weighted score: 15 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                            "a. Check if the job description mentions a specific requirement for relevant technical experience as mandatory."
                                            "  - If it is mandatory and the relevant technical experience is present in the resume, add 13.5 points (90% of 15 points) to the Matching Score."
                                            "  - If it is mandatory and the relevant technical experience is not present in the resume, add 0 points to the Matching Score."
                                            "b. If the job description mentions relevant technical experience as non-mandatory or preferred:"
                                            "  - If it is present in the resume, add 13.5 points (90% of 15 points) to the Matching Score."
                                            "  - If it is not present in the resume, add 9 points (60% of 15 points) to the Matching Score."
                                     "2. Experience (weighted score: 5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                     "3. Education (weighted score: 5 points) - If no specific educational requirement is mentioned, award full points for a relevant degree, regardless of the institution."
                                     "4. Soft Skills (weighted score: 5 points) - Look for exact keyword matches or direct mentions of soft skills in the resume."
                                     "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 30 (27), cap it at 27"
                                    "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                    "Present Matching Score in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                    "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                ),
                            ("Here is the most relevant sentence in the context: Mandatory Skills Evaluation Framework (Total: 40 Points)"
                                    "SECTION A: SKILL-BASED EVALUATION (24 points, 60% weight)"
                                        "List all mandatory technical/core skills from the job description."
                                        "Assign equal weight to each skill:"
                                        "- If there are n mandatory skills, each skill = 24/n points"
                                        "For each skill:"
                                        "- If the candidate has the skill → award full points for that skill."
                                        "If not → 0 points."
                                        "Section A Score = Sum of points for all matched skills."
                                        "Example:"
                                        "3 mandatory skills: Java, Spring Boot, DevOps"
                                        "Each skill = 8 points"
                                        "Candidate has Java & Spring Boot only"
                                        "Section A Score = 8 + 8 + 0 = 16 points"
                                    "SECTION B: NON-SKILL-BASED EVALUATION (16 points, 40% weight)"
                                        "List all non-skill mandatory requirements (education, company, location, etc.)."
                                        "If the candidate meets ALL non-skill requirements → 16 points."
                                        "If ANY non-skill requirement is missing → 0 points."
                                        "SCORING CALCULATION"
                                        "Final Score = Section A Score + Section B Score"
                                        "Maximum: 40 points"
                                    "Provide results in JSON format: {\"score\": [0-40], \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                ),
                            ("Here is the most relevant sentence in the context: Check if any specific educational requirement is asked for in the job description (e.g., specific certification, graduation from a Tier 1 institute, specific degree type, etc.)."
                                     "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                     "For the Education parameter (weighted score: 10 points):"
                                     "- If a specific educational requirement (like graduation from a Tier 1 institute) is mandatory in the job description:"
                                     "  - If the requirement is present in the resume, add 9 points (90% of 10 points) to the Matching Score."
                                     "  - If the requirement is not present in the resume, add 0 points to the Matching Score."
                                     "- If a specific educational requirement (like graduation from a Tier 1 institute) is preferred in the job description:"
                                     "  - If the requirement is present in the resume, add 9 points (90% of 10 points) to the Matching Score."
                                     "  - If the requirement is not present in the resume, add 5 points (50% of 10 points) to the Matching Score."
                                     "- If no specific educational requirement is mentioned in the job description:"
                                     "  - If the resume has a Tier 1 institute educational detail, add 8 points (80% of 10 points) to the Matching Score."
                                     "  - If the resume does not have a Tier 1 institute educational detail, add 7.5 points (75% of 10 points) to the Matching Score."
                                     "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                     "{\"score\": [final score],\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                ),
                            ("STEP 1: JOB DESCRIPTION ANALYSIS"
                                    "Find the top 15 keywords in the job description and give them weightage based on their repetition and mandatoriness/requirement. The combined weighted score of all 15 keywords should be 20."
                                    "Before proceeding, identify and list the most relevant sentences from the job description that contain these keywords, along with their frequency and context."
                                    " 2: RESUME ANALYSIS"
                                    "For the same 15 keywords identified from the job description, analyze their presence and importance in the resume using the following criteria:"
                                    "RESUME KEYWORD WEIGHTING RULES:"
                                    "- If keyword appears in professional experience section with action verbs (developed, managed, led, implemented): Award 4 points"
                                    "- If keyword appears in professional experience section without action verbs: Award 3 points"
                                    "- If keyword appears in skills section or technical skills: Award 2 points"
                                    "- If keyword appears in education/certification section: Award 1 point"
                                    "- If keyword appears only in summary/objective without experience backing: Award 0.5 points"
                                    "- If keyword is not present: Award 0 points"
                                    "STEP 3: MATCHING AND SCORING"
                                    "For each of the 15 keywords:"
                                    "1. Compare JD weightage (from Step 1) with Resume weightage (from Step 2)"
                                    "2. Calculate match score using this formula:"
                                    "   - If Resume Weight >= JD Weight: Award full JD weightage points"
                                    "   - If Resume Weight < JD Weight: Award (Resume Weight / JD Weight) * JD weightage points"
                                    "   - If Resume Weight = 0: Award 0 points"
                                    "STEP 4: FINAL CALCULATION"
                                    "1. Sum up all 15 keyword match scores"
                                    "2. If this sum exceeds 18 points (90% of 20), set the final score to 18"
                                    "3. If this sum is 18 points or less, use the exact sum as the final score"
                                    "OUTPUT FORMAT:"
                                    "Present results in JSON format:"
                                    "{\"score\": [final score], \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                    "VALIDATION RULES:"
                                    "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                    "- Do not make assumptions about implied skills or experience"
                                    "- Weight keywords based strictly on their placement and context within resume sections"
                                    "- If a keyword appears in multiple sections, use the highest applicable weight"
                                )
                        ]
    
        final_completion_text = ""
        rejection_feedback = ""
        overall_matching_score = 0
        emailFeedback = ""
        overall_Analysis=""
        print("About to start scoring loop...")
        if not steps:
            print("ERROR: No steps defined for this experience level!")
            return {"statusCode": 500, "body": {"error": "No scoring steps defined"}}

        for i, step in enumerate(steps):
            prompt = create_prompt(processed_text, job_desc, step)
            print(f"Processing Step in score calculation {i+1} with prompt: respective prompt")
            
            # Use different model invocation functions for each step
            if i == 0:
                # Adding code for Open AI processing
                content = OpenAIClient.invoke_model_with_backoff(prompt,Task= "step 1 for score calculations" ,want_json=False)

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
            
                # Adding code for Open AI processing
                content = OpenAIClient.invoke_model_with_backoff(prompt,Task= "step 2 for score calculations", want_json=False)
                print("Open AI content",content)
                overall_Analysis = overall_Analysis + content
                temp_score = extract_score_from_OpenAI_response(content)

                if temp_score is None:
                    temp_score = extract_score_from_OpenAI_response(content)
                
                # Cap temp_score at 36 if it's greater than 36
                if temp_score is not None and temp_score > 36:
                    temp_score = 36

            elif i == 2:
                content = OpenAIClient.invoke_model_with_backoff(prompt,Task= "step 3 for score calculations", want_json=False)
                
                print("Open AI content",content)
                overall_Analysis = overall_Analysis + content
                temp_score = extract_score_from_OpenAI_response(content)

                if temp_score is None:
                    temp_score = extract_score_from_OpenAI_response(content)

                # Cap temp_score at 9 if it's greater than 9
                if temp_score is not None and temp_score > 9:
                    temp_score = 9

            elif i == 3:
            
                # Adding code for Open AI processing
                content = OpenAIClient.invoke_model_with_backoff(prompt,Task= "step 4 for score calculations", want_json=False)
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
                content = OpenAIClient.invoke_model_with_backoff(prompt,want_json=False)
                print("Somthing went wrong)")
            print("temp_score", temp_score)
            # If temp_score is coming from the JSON as a list
            if isinstance(temp_score, list) and len(temp_score) > 0:
                temp_score = temp_score[0]
            # If it's already been converted to a string representation of a list
            elif isinstance(temp_score, str) and temp_score.startswith('[') and temp_score.endswith(']'):
                temp_score = temp_score.strip('[]')

            print("temp_score", temp_score)
            
            if temp_score is not None:
                overall_matching_score = ensure_decimal(overall_matching_score)
                temp_score = ensure_decimal(temp_score)
                overall_matching_score = overall_matching_score + temp_score
            else:
                print("No valid score found in this response")

        # overall_matching_score = 72
        overall_matching_score = int(round(overall_matching_score))
        print("overall_matching_score", overall_matching_score)

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


            content = OpenAIClient.invoke_model_with_backoff(prompt,Task= "Rejection for 1 <= overall_matching_score < 70:" )
            completion_text_rejection = json.dumps(content)

            print("***************************************  1 <70 *********************************************")
            print_completion_text(completion_text_rejection)
            rejection_feedback = completion_text_rejection

            #generate email feedback focusing on positives
            if overall_matching_score > 40:
                prompt = (f"{final_completion_text}, {completion_text_rejection}\n"
                         f"Based on the above content, write a one-line summary in 20-25 words that highlights ONLY the positive qualities and strengths that make this candidate suitable for the job.\n"
                         f"Focus exclusively on positive aspects - exclude any negative feedback or criticisms.")

                emailFeedback = OpenAIClient.invoke_model_with_backoff(prompt,Task= "Email feedback for 1 <= overall_matching_score < 70:",want_json=False)
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

            content = OpenAIClient.invoke_model_with_backoff(prompt,Task= "Score feedback for >70")
            completion_text_approval = json.dumps(content)

            print("***************************************   >70 *********************************************")
            print_completion_text(completion_text_approval)
            final_completion_text = completion_text_approval

            prompt = (f"{final_completion_text}\n"
                     f"Based on the above content, write a one-line summary in 20-25 words that highlights ONLY the positive qualities and strengths that make this candidate suitable for the job.\n"
                     f"Focus exclusively on positive aspects - exclude any negative feedback or criticisms.")

            emailFeedback = OpenAIClient.invoke_model_with_backoff(prompt, Task="Email Feedback",want_json=False)
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
        
    except Exception as e:
        print(f"An error occurred: {e}")
        # update_cv_extract_in_dynamodb(table_name, partition_key_value, sort_key_prefix, str(e) , 251, -1)
        return {"statusCode": 500, "body": {"error": str(e)}}
    
    return {"statusCode": 200, "body": 
        {"Overall Matching Score": overall_matching_score}
    }

def lambda_handler(event, context):
    print(f"got a event : -  {event}") 
    global DBManager,update_doc_id
    # env = "dev"   #change it make dynamically
    env=os.environ.get("ENVIRONMENT", "dev")
    secret_name ="AZURE-openai-secret-" +env
    AZURE_openai_secret = get_secret(secret_name) 
        
    try:
        # Parse S3 event
        s3_event = event['Records'][0]['s3']
        bucket_name = s3_event['bucket']['name']
        object_key = unquote_plus(s3_event['object']['key'])
        
        print(f"Processing S3 object: {bucket_name}/{object_key}")
        
        # Extract IDs from S3 path: agencies/{agencyUserId}/bulk-cvs/{agencyBulkJdId}/{filename}
        path_parts = object_key.split('/')
        if len(path_parts) < 5:
            raise ValueError(f"Invalid S3 path structure: {object_key}")
            
        agency_user_id = path_parts[1]
        agency_bulk_jd_id = path_parts[3]
        filename = path_parts[4]
        
        # Get environment
        env = os.environ.get("ENVIRONMENT", "dev")
        
        # Download PDF from S3
        s3_client = boto3.client('s3')
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
            pdf_data = response['Body'].read()
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                print(f"S3 object not found: {bucket_name}/{object_key}")
                # Try with original encoded key
                original_key = s3_event['object']['key']
                print(f"Trying original key: {bucket_name}/{original_key}")
                response = s3_client.get_object(Bucket=bucket_name, Key=original_key)
                pdf_data = response['Body'].read()
            else:
                raise
        
        # Extract text from PDF
        resume_text = extract_text_from_pdf(pdf_data)
        processed_text = clean_text(resume_text)
        print(AZURE_openai_secret)
        OpenAIClient = AzureOpenAIClient(AZURE_openai_secret)
        cv_extract, cv_extracted_parsed = process_cv(processed_text,OpenAIClient)
        print(f"Successfully processed resume: {processed_text[:200]}..")
        env = "dev"
        GCP_secret_name = "GCP-firestore-secret-"+env
        GCP_DATABASE_NAME = "worko-corp-db-" +env 
        
        DBManager = FirestoreManager(GCP_secret_name,GCP_DATABASE_NAME)



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

        score = jd_resume_matching(job_desc, processed_text, cv_extract, cv_extracted_parsed,OpenAIClient,update_doc_id)
        return {
            "statusCode": 200,
            "body": json.dumps({
                # "message": score,
                "job_description": job_desc,
                "resume_text": resume_text
            })
        }
        
    except Exception as e:
        print(f"Error processing resume: {str(e)}")
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
    

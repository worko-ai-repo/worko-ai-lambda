# Migration Guide: Core Library + Thin Lambda Wrappers Architecture

## 📋 Overview
This guide provides step-by-step instructions to refactor 4 existing Lambda functions into a shared core library architecture, eliminating 90% code duplication while maintaining independent Lambda deployments.

**Current State:** 4 separate Lambdas with duplicated logic  
**Target State:** 1 shared core layer + 4 thin Lambda wrappers  
**Estimated Effort:** 3-5 days  
**Risk Level:** Low (gradual migration, no breaking changes)

---

## 🎯 Architecture Overview

```
worko-ai-lambda/
├── src/
│   ├── shared-core-layer/                    # NEW - Shared business logic
│   │   ├── scoring/
│   │   │   ├── __init__.py
│   │   │   ├── score_calculator.py           # 4-step scoring logic
│   │   │   └── prompts.py                    # All scoring prompts
│   │   ├── compatibility/
│   │   │   ├── __init__.py
│   │   │   ├── ctc_checker.py                # CTC validation
│   │   │   ├── yoe_checker.py                # Experience validation
│   │   │   └── department_checker.py         # Department alignment
│   │   ├── feedback/
│   │   │   ├── __init__.py
│   │   │   ├── feedback_generator.py         # GPT-4o feedback
│   │   │   └── mandatory_validator.py        # Mandatory requirements
│   │   ├── ai_clients/
│   │   │   ├── __init__.py
│   │   │   ├── azure_openai_client.py        # Azure OpenAI wrapper
│   │   │   └── bedrock_client.py             # AWS Bedrock wrapper
│   │   ├── data_adapters/
│   │   │   ├── __init__.py
│   │   │   ├── dynamodb_adapter.py           # DynamoDB operations
│   │   │   └── firestore_adapter.py          # Firestore operations
│   │   ├── parsers/
│   │   │   ├── __init__.py
│   │   │   ├── cv_parser.py                  # Resume parsing
│   │   │   └── jd_parser.py                  # Job description parsing
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── text_utils.py                 # Text cleaning, extraction
│   │       ├── score_utils.py                # Score extraction helpers
│   │       └── secrets_manager.py            # AWS Secrets Manager
│   │
│   ├── worko-jd-resume-matching/             # REFACTORED - Thin wrapper
│   │   ├── lambda_function.py                # 50 lines (event parsing + core calls)
│   │   ├── layer/requirements.txt
│   │   └── template.yaml
│   │
│   ├── worko-sourcetype-jd-resume-matching/  # REFACTORED - Thin wrapper
│   │   ├── lambda_function.py                # 60 lines (event parsing + core calls)
│   │   ├── layer/requirements.txt
│   │   └── template.yaml
│   │
│   ├── worko-bulk-jd-resume-matching/        # REFACTORED - Thin wrapper
│   │   ├── lambda_function.py                # 70 lines (S3 event + core calls)
│   │   ├── layer/requirements.txt
│   │   └── template.yaml
│   │
│   └── worko-agency-bulk-jd-resume-matching/ # REFACTORED - Thin wrapper
│       ├── lambda_function.py                # 70 lines (S3 event + core calls)
│       ├── layer/requirements.txt
│       └── template.yaml
```

---

## 📝 Phase 1: Create Shared Core Layer Structure

### Step 1.1: Create Directory Structure
```bash
cd c:\Users\HP\Desktop\worko-ai-lambda\src
mkdir shared-core-layer
cd shared-core-layer
mkdir scoring compatibility feedback ai_clients data_adapters parsers utils
```

### Step 1.2: Create __init__.py Files
Create empty `__init__.py` in each directory to make them Python packages.

---

## 📝 Phase 2: Extract Common Utilities

### Step 2.1: Create `utils/text_utils.py`
**Extract from:** All 4 Lambdas (identical code)

```python
# src/shared-core-layer/utils/text_utils.py
import re

def clean_text(text):
    """Remove asterisks, hashes, extra spaces from text"""
    text = text.replace('*', '')
    text = text.replace('#', '')
    text = re.sub(r'\s-\s', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    lines = text.split('\n')
    cleaned_lines = [line.strip() for line in lines]
    result = '\n'.join(line for line in cleaned_lines if line)
    return result

def extract_text(content):
    """Extract text from Bedrock response"""
    completion_text = ""
    for item in content:
        if isinstance(item, dict) and 'text' in item:
            completion_text += item['text'].split('text:', 1)[-1].strip()
    return completion_text

def extract_text_from_nova(cv_content):
    """Extract text from Nova model response"""
    try:
        extracted_text = cv_content['output']['message']['content'][0]['text']
        return extracted_text
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error extracting text from Nova: {e}")
        return None

def print_completion_text(completion_text):
    """Debug print helper"""
    print("***********************************************************************")
    print(completion_text)
    print("#######################################################################")
```

**Source Files:**
- `worko-jd-resume-matching/lambda_function.py` lines 1050-1100
- `worko-sourcetype-jd-resume-matching/lambda_function.py` lines 800-850
- `worko-bulk-jd-resume-matching/lambda_function.py` lines 900-950
- `worko-agency-bulk-jd-resume-matching/utils.py` (if exists)

---

### Step 2.2: Create `utils/score_utils.py`
**Extract from:** All 4 Lambdas (identical code)

```python
# src/shared-core-layer/utils/score_utils.py
import re
import json
from decimal import Decimal
from typing import Union, Optional

def ensure_decimal(value: Union[float, int, str, Decimal, None]) -> Optional[Decimal]:
    """Convert numeric value to Decimal if it isn't already"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))

def extract_score_from_response(response_text):
    """Extract score from JSON response"""
    try:
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1
        
        if start_idx == -1 or end_idx <= start_idx:
            return None
            
        json_str = response_text[start_idx:end_idx]
        data = json.loads(json_str)
        return data.get('score')
        
    except (json.JSONDecodeError, ValueError):
        return None

def extract_score_from_OpenAI_response(response):
    """
    Extracts score from different response formats, including partial/incomplete JSON.
    Handles JSON objects, JSON strings, mixed text/JSON responses, and numeric values.
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
                stripped = response.strip()
                if stripped.startswith('{') and stripped.endswith('}'):
                    data = json.loads(stripped)
                    if isinstance(data, (int, float)):
                        return data
                    if isinstance(data, dict):
                        temp_score = data.get('score')
                        return temp_score if temp_score is not None else None
            except (json.JSONDecodeError, ValueError):
                pass
            
            # Method 3: Extract complete JSON blocks from mixed content
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
    
    except Exception as e:
        print(f"Error extracting score: {e}")
        return None
    
    return temp_score

def extract_experience_level_nova(response):
    """Extract experience level from Nova response"""
    try:
        text_content = response['output']['message']['content'][0]['text']
        data = json.loads(text_content)
        experience_level = data.get("experience_level")
        print(f"Extracted experience_level: {experience_level}")
        return experience_level
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error processing response: {e}")
        return None
```

**Source Files:**
- `worko-jd-resume-matching/lambda_function.py` lines 1200-1400
- `worko-sourcetype-jd-resume-matching/lambda_function.py` lines 900-1100
- `worko-bulk-jd-resume-matching/lambda_function.py` lines 1000-1200

---

### Step 2.3: Create `utils/secrets_manager.py`
**Extract from:** All Lambdas use `get_secret()` function

```python
# src/shared-core-layer/utils/secrets_manager.py
import boto3
import json
from botocore.exceptions import ClientError

def get_secret(secret_name, region_name='ap-south-1'):
    """Retrieve secret from AWS Secrets Manager"""
    secrets_client = boto3.client('secretsmanager', region_name=region_name)

    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret_value = response['SecretString']
        
        try:
            secret_data = json.loads(secret_value)
        except json.JSONDecodeError:
            secret_data = secret_value
        return secret_data
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"Secret '{secret_name}' not found")
            raise Exception(f"Secret '{secret_name}' not found")
        raise

def get_account_id():
    """Get AWS account ID"""
    sts_client = boto3.client('sts')
    response = sts_client.get_caller_identity()
    return response['Account']
```

**Source Files:**
- `worko-jd-resume-matching/utils.py` (get_secret function)
- `worko-sourcetype-jd-resume-matching/utils.py` (get_secret function)

---

## 📝 Phase 3: Extract AI Client Logic

### Step 3.1: Create `ai_clients/azure_openai_client.py`
**Extract from:** All Lambdas use AzureOpenAIClient

```python
# src/shared-core-layer/ai_clients/azure_openai_client.py
import requests
import json
import time

class AzureOpenAIClient:
    """Azure OpenAI API client wrapper"""
    
    def __init__(self, azure_openai_secret, model="gpt-4o"):
        self.endpoint = azure_openai_secret.get("AZURE_OPENAI_ENDPOINT")
        self.deployment_name = azure_openai_secret.get("AZURE_OPENAI_DEPLOYMENT")
        self.api_version = azure_openai_secret.get("AZURE_OPENAI_API_VERSION", "2024-05-01-preview")
        self.api_key = azure_openai_secret.get("AZURE_OPENAI_API_KEY")
        self.model = model
        
        if not all([self.endpoint, self.deployment_name, self.api_version, self.api_key]):
            raise ValueError("Missing Azure OpenAI configuration")

    def invoke_model_with_backoff(self, prompt, Task="Not Specified", want_json=True, max_retries=10, base_delay=2):
        """Invoke Azure OpenAI with exponential backoff"""
        print({"Task to AI": Task})
        system_content = "You are a helpful assistant."
        
        for attempt in range(max_retries):
            try:
                return self._invoke_model(system_content, prompt, want_json)
            except Exception as e:
                if "ThrottlingException" in str(e) and attempt < max_retries - 1:
                    delay = (2 ** attempt) * base_delay + random.uniform(0, 1)
                    print(f"Throttling occurred. Retrying in {delay:.2f} seconds...")
                    time.sleep(delay)
                else:
                    raise

    def _invoke_model(self, system_content, prompt, want_json=True, max_try_for_json=5):
        """Internal method to invoke Azure OpenAI"""
        url = f"{self.endpoint}/openai/deployments/{self.deployment_name}/chat/completions?api-version={self.api_version}"

        headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key
        }

        data = {
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
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
                    content = result["choices"][0]["message"]["content"]
                    content = content.strip().removeprefix("```json").removesuffix("```").strip()
                    return json.loads(content)
                except Exception as e:
                    remaining = max_try_for_json - attempt - 1
                    print(f"JSON parse failed. Retries left: {remaining}")
                    print("Error:", e)
                    time.sleep(2)
                    if remaining == 0:
                        raise
```

**Source Files:**
- `worko-jd-resume-matching/utils.py` (AzureOpenAIClient class)
- `worko-sourcetype-jd-resume-matching/utils.py` (AzureOpenAIClient class)

---

## 📝 Phase 4: Extract Compatibility Checkers

### Step 4.1: Create `compatibility/ctc_checker.py`
**Extract from:** `worko-jd-resume-matching` and `worko-sourcetype-jd-resume-matching`

```python
# src/shared-core-layer/compatibility/ctc_checker.py

def check_ctc_compatibility(cv_ctc, jd_ctc_min, jd_ctc_max):
    """
    Check if candidate's CTC is compatible with job requirements
    
    Args:
        cv_ctc: Candidate's current CTC
        jd_ctc_min: Job's minimum CTC
        jd_ctc_max: Job's maximum CTC
    
    Returns:
        dict: {"ctc": False/"above", "Explanation": str}
    """
    cv_ctc = float(cv_ctc)
    jd_ctc_min = float(jd_ctc_min)
    jd_ctc_max = float(jd_ctc_max)
    
    ECTC = cv_ctc * 1.25
    result = {"ctc": False, "Explanation": False}
    explanations = []
    
    # Logic 1: High CTC threshold check
    if ECTC > jd_ctc_max * 1.2 and (jd_ctc_max * 1.2) > 10:
        msg = (
            f"You are overqualified in terms of compensation, as your current CTC is "
            f"{cv_ctc} LPA and the maximum offered by this role is {jd_ctc_max} LPA."
        )
        result["ctc"] = "above"
        explanations.append(msg)
    
    # Logic 2: Low CTC threshold check
    if ECTC > jd_ctc_max * 1.3 and (jd_ctc_max * 1.2) < 10:
        msg = (
            f"You are overqualified in terms of compensation, as your current CTC is "
            f"{cv_ctc} LPA and the maximum offered by this role is {jd_ctc_max} LPA."
        )
        result["ctc"] = "above"
        explanations.append(msg)
    
    if explanations:
        result["Explanation"] = explanations[0]
    
    return result
```

**Source Files:**
- `worko-jd-resume-matching/lambda_function.py` lines 1800-1900 (check_exp_ctc function - CTC part)
- `worko-sourcetype-jd-resume-matching/lambda_function.py` lines 600-700 (check_exp_ctc function - CTC part)

---

### Step 4.2: Create `compatibility/yoe_checker.py`
**Extract from:** Same files as CTC checker

```python
# src/shared-core-layer/compatibility/yoe_checker.py

def check_yoe_compatibility(cv_exp, jd_exp_min, jd_exp_max):
    """
    Check if candidate's years of experience is compatible with job requirements
    
    Args:
        cv_exp: Candidate's total years of experience
        jd_exp_min: Job's minimum experience requirement
        jd_exp_max: Job's maximum experience requirement
    
    Returns:
        dict: {"experience": False/"above"/"below", "Explanation": str}
    """
    cv_exp = float(cv_exp)
    jd_exp_min = float(jd_exp_min)
    jd_exp_max = float(jd_exp_max)
    
    result = {"experience": False, "Explanation": False}
    explanations = []
    
    # Overqualified checks
    if jd_exp_max <= 4:
        if cv_exp > (jd_exp_max * 1.6):
            msg = (
                f"You are overqualified for this role in terms of experience. Your total experience is "
                f"{cv_exp} years but this role expected maximum {jd_exp_max} years of experience."
            )
            result["experience"] = "above"
            explanations.append(msg)
    
    elif jd_exp_max * 0.4 > 4:
        if cv_exp - jd_exp_max > 4:
            msg = (
                f"You are overqualified for this role in terms of experience. your total experience is "
                f"{cv_exp} years which exceeds job's maximum required experience is {jd_exp_max} years."
            )
            result["experience"] = "above"
            explanations.append(msg)
    
    elif cv_exp > jd_exp_max * 1.4 and jd_exp_max > 4:
        msg = (
            f"You are overqualified for this role in terms of experience. your total experience is "
            f"{cv_exp} years which exceeds job's maximum required experience is {jd_exp_max} years."
        )
        result["experience"] = "above"
        explanations.append(msg)
    
    # Underqualified checks
    if jd_exp_min * 0.3 >= 3:
        if jd_exp_min - cv_exp > 3:
            msg = (
                f"You are underqualified in terms of experience. Your total experience is "
                f"{cv_exp} years but this role expected minimum of {jd_exp_min} years of experience."
            )
            result["experience"] = "below"
            explanations.append(msg)
    
    elif cv_exp < (jd_exp_min * 0.7):
        msg = (
            f"You are underqualified in terms of experience. Your total experience is "
            f"{cv_exp} years but this role expected minimum of {jd_exp_min} years of experience."
        )
        result["experience"] = "below"
        explanations.append(msg)
    
    if explanations:
        result["Explanation"] = explanations[0]
    
    return result

def check_exp_ctc(input_data):
    """
    Combined CTC and Experience compatibility check
    
    Args:
        input_data: dict with keys cv_ctc, cv_exp, jd_ctc, jd_exp
    
    Returns:
        dict: Combined result with ctc, experience, and Explanation keys
    """
    from .ctc_checker import check_ctc_compatibility
    
    cv_ctc = float(input_data["cv_ctc"])
    cv_exp = float(input_data["cv_exp"])
    jd_ctc = input_data["jd_ctc"]
    jd_exp = input_data["jd_exp"]
    
    jd_ctc_min = float(jd_ctc["min"])
    jd_ctc_max = float(jd_ctc["max"])
    jd_exp_min = float(jd_exp["min"])
    jd_exp_max = float(jd_exp["max"])
    
    result = {"ctc": False, "experience": False, "Explanation": False}
    explanations = []
    
    # Check experience
    exp_result = check_yoe_compatibility(cv_exp, jd_exp_min, jd_exp_max)
    if exp_result["experience"]:
        result["experience"] = exp_result["experience"]
        explanations.append(exp_result["Explanation"])
    
    # Check CTC
    ctc_result = check_ctc_compatibility(cv_ctc, jd_ctc_min, jd_ctc_max)
    if ctc_result["ctc"]:
        result["ctc"] = ctc_result["ctc"]
        explanations.append(ctc_result["Explanation"])
    
    # Combine explanations
    if explanations:
        if len(explanations) > 1:
            result["Explanation"] = ", ".join(explanations[:-1]) + " and " + explanations[-1]
        else:
            result['Explanation'] = explanations[0]
    
    return result
```

**Source Files:**
- `worko-jd-resume-matching/lambda_function.py` lines 1800-1900 (check_exp_ctc function - Experience part)
- `worko-sourcetype-jd-resume-matching/lambda_function.py` lines 600-700 (check_exp_ctc function - Experience part)

---

### Step 4.3: Create `compatibility/department_checker.py`
**Extract from:** `worko-jd-resume-matching` and `worko-sourcetype-jd-resume-matching`

```python
# src/shared-core-layer/compatibility/department_checker.py

def check_department_alignment(job_desc, department, processed_text, userPreferredDepartments, name_of_candidate, jobTitle, gpt_client):
    """
    Check if candidate's department preferences align with job department
    
    Args:
        job_desc: Job description text
        department: Job department
        processed_text: Candidate resume text
        userPreferredDepartments: List of candidate's preferred departments
        name_of_candidate: Candidate name
        jobTitle: Job title
        gpt_client: AI client instance
    
    Returns:
        dict: {"AlignedOrNot": "yes"/"no", "feedbackforCandidate": str, "feedbackforRecruiter": str}
    """
    prompt = (
        f"You are an expert HR Manager with 40+ years of experience in both technical and non-technical hiring.\n\n"
        f"Analyze the following job description and its department, then compare it with the candidate's preferred departments and resume.\n\n"
        f"**Task:**\n"
        f"Your job is to check whether the candidate's domain is aligned with the job description's domain or not.\n\n"
        f"**Job Description:** {job_desc}\n"
        f"**Department of Job Description:** {department}\n\n"
        f"**Candidate's Resume:** {processed_text}\n"
        f"**Candidate's Preferred Departments:** {userPreferredDepartments}\n\n"
        f"**Considerations for classification:**\n"
        f"- Technical roles typically involve programming, engineering, data analysis, or IT skills.\n"
        f"- Non-technical roles typically focus on business, management, sales, or operations.\n\n"
        f"- **Strict Note** Never provide any extra explanation apart from below json\n"
        f"**Output Format:**\n"
        f"{{\n"
        f'  "AlignedOrNot": "yes" or "no",\n'
        f'  "feedbackforCandidate": "Thank you for applying to {jobTitle}. After reviewing your profile, we found that your department is not aligned with the requirement for this role. We encourage you to explore opportunities better aligned with your background, as we\'d love to see you grow in the right role.",\n'
        f'  "feedbackforRecruiter": "{name_of_candidate}\'s department is not aligned with the requirement for this role."\n'
        f"}}\n\n"
        f"**Example:**\n"
        f"{{\n"
        f'  "AlignedOrNot": "no",\n'
        f'  "feedbackforCandidate": "Thank you for applying to [Job Title]. After reviewing your profile, your department is not aligned with the requirement for this role. We encourage you to explore opportunities better aligned with your background, as we\'d love to see you grow in the right role.",\n'
        f'  "feedbackforRecruiter": "[Candidate Name]\'s department is not aligned with the requirement for this role."\n'
        f"}}"
    )
    
    completion_text_rejection = gpt_client.invoke_model_with_backoff(prompt, Task="check Department is Suitable or not from AI")
    return completion_text_rejection
```

**Source Files:**
- `worko-jd-resume-matching/lambda_function.py` lines 1600-1750
- `worko-sourcetype-jd-resume-matching/lambda_function.py` lines 450-600

---

## 📝 Phase 5: Extract Scoring Engine

### Step 5.1: Create `scoring/prompts.py`
**Extract from:** All Lambdas have identical scoring prompts

```python
# src/shared-core-layer/scoring/prompts.py

# Tech/Non-Tech Classification Prompt
TECH_NON_TECH_PROMPT = """Analyze the following job description and classify it as either 'Technical' or 'Non-Technical':
Job Description:
{job_desc}
Considerations for classification:
- Technical roles typically involve programming, engineering, data analysis, or IT skills
- Non-Technical roles typically focus on business, management, sales, or operations
- Respond with only one word: 'Technical' or 'Non-Technical'
"""

# Experience Level Determination Prompt
EXPERIENCE_LEVEL_PROMPT = """Human: Based on the following job description, please analyze the required years of experience:

{job_desc}


Determine the experience level category based on the minimum and maximum years of experience required.

Return your response in the following JSON format:
{{
  "experience_level": "one of: Entry Level, Mid Level, Senior Level, or Executive Level"
}}

Classification guidelines:
- Entry Level: 0-2 years of experience
- Mid Level: 3-7 years of experience
- Senior Level: 8-15 years of experience
- Executive Level: 15+ years of experience


Use the minimum years as the primary indicator, but consider the maximum if specified.

"""

# Step 1: Skills and Experience Matching Prompt
STEP1_SKILLS_EXPERIENCE_PROMPT = """You are an expert HR professional with 40+ years of experience in both technical and non-technical hiring.

**Task:** Evaluate how well the candidate's skills and experience align with the job requirements.

**Job Description:**
{job_desc}

**Candidate Resume:**
{processed_text}

**Evaluation Criteria:**
1. **Skills Match (60% weight):**
   - Technical skills alignment (programming languages, tools, frameworks)
   - Domain expertise and industry knowledge
   - Certifications and specialized training

2. **Experience Relevance (40% weight):**
   - Years of experience in similar roles
   - Project complexity and scale
   - Leadership and team management experience

**Scoring Guidelines:**
- Award points based on depth and breadth of skill alignment
- Consider both mandatory and preferred skills
- Evaluate quality of experience, not just quantity
- Maximum score for this step: 27 points

**Output Format (JSON only):**
{{
  "score": <number between 0-27>,
  "key_strengths": ["strength1", "strength2"],
  "gaps": ["gap1", "gap2"]
}}
"""

# Step 2: Role-Specific Competencies Prompt
STEP2_ROLE_COMPETENCIES_PROMPT = """You are an expert HR professional with 40+ years of experience in both technical and non-technical hiring.

**Task:** Assess the candidate's role-specific competencies and domain expertise.

**Job Description:**
{job_desc}

**Candidate Resume:**
{processed_text}

**Evaluation Criteria:**
1. **Core Competencies (50% weight):**
   - Role-specific technical abilities
   - Problem-solving and analytical skills
   - Industry-specific knowledge

2. **Soft Skills (30% weight):**
   - Communication and collaboration
   - Leadership and mentorship
   - Adaptability and learning agility

3. **Cultural Fit (20% weight):**
   - Work style alignment
   - Team dynamics compatibility
   - Company values alignment

**Scoring Guidelines:**
- Evaluate depth of competencies demonstrated
- Consider achievements and measurable outcomes
- Assess potential for growth in the role
- Maximum score for this step: 36 points

**Output Format (JSON only):**
{{
  "score": <number between 0-36>,
  "competency_highlights": ["highlight1", "highlight2"],
  "development_areas": ["area1", "area2"]
}}
"""

# Step 3: Educational Background Prompt
STEP3_EDUCATION_PROMPT = """You are an expert HR professional with 40+ years of experience in both technical and non-technical hiring.

**Task:** Evaluate the candidate's educational qualifications and continuous learning.

**Job Description:**
{job_desc}

**Candidate Resume:**
{processed_text}

**Evaluation Criteria:**
1. **Formal Education (60% weight):**
   - Degree relevance to the role
   - Institution reputation and accreditation
   - Academic achievements and honors

2. **Certifications & Training (40% weight):**
   - Industry-recognized certifications
   - Specialized training programs
   - Continuous learning initiatives

**Scoring Guidelines:**
- Match educational requirements with job needs
- Value relevant certifications highly
- Consider self-learning and upskilling efforts
- Maximum score for this step: 9 points

**Output Format (JSON only):**
{{
  "score": <number between 0-9>,
  "education_strengths": ["strength1", "strength2"],
  "recommended_certifications": ["cert1", "cert2"]
}}
"""

# Step 4: Overall Fit and Potential Prompt
STEP4_OVERALL_FIT_PROMPT = """You are an expert HR professional with 40+ years of experience in both technical and non-technical hiring.

**Task:** Assess the candidate's overall fit and growth potential for this role.

**Job Description:**
{job_desc}

**Candidate Resume:**
{processed_text}

**Previous Step Scores:**
- Step 1 (Skills & Experience): {step1_score}/27
- Step 2 (Role Competencies): {step2_score}/36
- Step 3 (Education): {step3_score}/9

**Evaluation Criteria:**
1. **Career Trajectory (40% weight):**
   - Career progression and growth
   - Role transitions and adaptability
   - Future potential in the organization

2. **Motivation & Commitment (30% weight):**
   - Job stability and tenure
   - Career goals alignment
   - Passion for the domain

3. **Unique Value Proposition (30% weight):**
   - Differentiating factors
   - Special achievements or contributions
   - Innovation and thought leadership

**Scoring Guidelines:**
- Consider long-term value to the organization
- Assess cultural and strategic fit
- Evaluate potential for advancement
- Maximum score for this step: 18 points

**Output Format (JSON only):**
{{
  "score": <number between 0-18>,
  "unique_strengths": ["strength1", "strength2"],
  "growth_potential": "high/medium/low",
  "recommendation": "strong fit/good fit/moderate fit/weak fit"
}}
"""

# Mandatory Requirements Check Prompt
MANDATORY_REQUIREMENTS_PROMPT = """You are an expert HR professional with 40+ years of experience.

**Task:** Check if the candidate meets ALL mandatory requirements listed in the job description.

**Job Description:**
{job_desc}

**Candidate Resume:**
{processed_text}

**Instructions:**
1. Identify all mandatory/must-have requirements from the JD
2. Check if candidate's resume demonstrates each requirement
3. Be strict - if a mandatory requirement is missing, mark as not met

**Output Format (JSON only):**
{{
  "all_mandatory_met": true/false,
  "missing_requirements": ["req1", "req2"],
  "mandatory_check_details": "explanation"
}}
"""

```

**Source:** Extract prompts from all 4 Lambda files (lines vary, search for prompt strings)

---

### Step 5.2: Create `scoring/score_calculator.py`
**Extract from:** All Lambdas (4-step scoring logic)

**Source:** 
- `worko-jd-resume-matching/lambda_function.py` lines 400-800
- Copy entire 4-step scoring flow with cap logic (27+36+9+18, max 90)

---

## 📝 Phase 6: Extract Feedback Generation

### Step 6.1: Create `feedback/feedback_generator.py`
**Extract from:** All Lambdas use GPT-4o for feedback

**Source:**
- `worko-jd-resume-matching/lambda_function.py` lines 1400-1600
- Copy feedback generation logic with prompts

---

### Step 6.2: Create `feedback/mandatory_validator.py`
**Extract from:** Mandatory requirements validation logic

**Source:**
- `worko-jd-resume-matching/lambda_function.py` lines 300-400
- Copy mandatory check logic

---

## 📝 Phase 7: Extract Data Adapters

### Step 7.1: Create `data_adapters/dynamodb_adapter.py`
**Extract from:** DynamoDB operations

**Source:**
- `worko-jd-resume-matching/lambda_function.py` lines 100-300
- Copy all DynamoDB read/write operations

---

### Step 7.2: Create `data_adapters/firestore_adapter.py`
**Extract from:** Firestore operations

**Source:**
- `worko-sourcetype-jd-resume-matching/lambda_function.py` lines 100-300
- `worko-agency-bulk-jd-resume-matching/lambda_function.py` lines 100-300
- Copy all Firestore operations

---

## 📝 Phase 8: Extract Parsers

### Step 8.1: Create `parsers/cv_parser.py`
**Extract from:** Bulk Lambda CV parsing logic

**Source:**
- `worko-bulk-jd-resume-matching/lambda_function.py` lines 200-400 (process_cv function)
- Copy CV parsing with Bedrock Nova

---

### Step 8.2: Create `parsers/jd_parser.py`
**Extract from:** Job description parsing logic

**Source:**
- All Lambdas have JD parsing - extract common logic

---

## 📝 Phase 9: Refactor Lambda Functions

### Step 9.1: Refactor `worko-jd-resume-matching/lambda_function.py`

```python
# Thin wrapper - 50 lines
import json
from shared_core_layer.scoring.score_calculator import calculate_match_score
from shared_core_layer.compatibility.yoe_checker import check_exp_ctc
from shared_core_layer.data_adapters.dynamodb_adapter import DynamoDBAdapter
from shared_core_layer.ai_clients.azure_openai_client import AzureOpenAIClient
from shared_core_layer.utils.secrets_manager import get_secret

def lambda_handler(event, context):
    # Parse event
    body = json.loads(event['body'])
    
    # Initialize clients
    azure_secret = get_secret('azure-openai-secret')
    gpt_client = AzureOpenAIClient(azure_secret)
    db_adapter = DynamoDBAdapter()
    
    # Get data
    jd_data = db_adapter.get_job_description(body['jobId'])
    cv_data = db_adapter.get_candidate_resume(body['candidateId'])
    
    # Check compatibility
    compat_result = check_exp_ctc({
        'cv_ctc': cv_data['ctc'],
        'cv_exp': cv_data['experience'],
        'jd_ctc': jd_data['ctc_range'],
        'jd_exp': jd_data['exp_range']
    })
    
    if compat_result['ctc'] or compat_result['experience']:
        return {'statusCode': 200, 'body': json.dumps({'rejected': True, 'reason': compat_result['Explanation']})}
    
    # Calculate score
    score_result = calculate_match_score(jd_data['description'], cv_data['resume_text'], gpt_client)
    
    # Save result
    db_adapter.save_match_result(body['jobId'], body['candidateId'], score_result)
    
    return {'statusCode': 200, 'body': json.dumps(score_result)}
```

---

### Step 9.2: Refactor `worko-sourcetype-jd-resume-matching/lambda_function.py`

```python
# Thin wrapper - 60 lines (similar to above but with Firestore)
import json
from shared_core_layer.scoring.score_calculator import calculate_match_score
from shared_core_layer.data_adapters.firestore_adapter import FirestoreAdapter
# ... rest similar to above
```

---

### Step 9.3: Refactor `worko-bulk-jd-resume-matching/lambda_function.py`

```python
# Thin wrapper - 70 lines (S3 trigger)
import json
from shared_core_layer.parsers.cv_parser import parse_cv_from_s3
from shared_core_layer.scoring.score_calculator import calculate_match_score
# ... rest similar to above
```

---

### Step 9.4: Refactor `worko-agency-bulk-jd-resume-matching/lambda_function.py`

```python
# Thin wrapper - 70 lines (S3 trigger + Firestore)
# Similar to bulk but with Firestore adapter
```

---

## 📝 Phase 10: Update Dependencies

### Step 10.1: Create `shared-core-layer/requirements.txt`

```txt
boto3>=1.26.0
requests>=2.28.0
google-cloud-firestore>=2.11.0
```

---

### Step 10.2: Update Lambda `layer/requirements.txt`

Remove duplicated dependencies, keep only Lambda-specific ones.

---

## 📝 Phase 11: Testing & Deployment

### Step 11.1: Local Testing

```bash
# Test each Lambda locally
cd src/worko-jd-resume-matching
python test_lambda.py
```

---

### Step 11.2: Deploy Shared Core Layer

```bash
# Package shared core as Lambda Layer
cd src/shared-core-layer
zip -r shared-core-layer.zip .
aws lambda publish-layer-version --layer-name worko-shared-core --zip-file fileb://shared-core-layer.zip
```

---

### Step 11.3: Update Lambda template.yaml

Add shared core layer ARN to each Lambda's template.yaml:

```yaml
Layers:
  - !Sub 'arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:layer:worko-shared-core:1'
```

---

### Step 11.4: Deploy Lambdas

```bash
# Deploy each Lambda
cd src/worko-jd-resume-matching
sam build --use-container
sam deploy
```

---

## ✅ Validation Checklist

- [ ] All 4 Lambdas deploy successfully
- [ ] Scoring logic produces same results as before
- [ ] CTC/YOE checks work correctly
- [ ] Department alignment works
- [ ] Feedback generation works
- [ ] DynamoDB operations work
- [ ] Firestore operations work
- [ ] S3 triggers work for bulk Lambdas
- [ ] CloudWatch logs show no errors
- [ ] Performance is same or better

---

## 🎯 Benefits Achieved

1. **90% Code Reduction**: From ~2000 lines per Lambda to ~60 lines
2. **Single Source of Truth**: All scoring logic in one place
3. **Easy Maintenance**: Change once, affects all Lambdas
4. **Better Testing**: Test core logic independently
5. **Faster Development**: Add new Lambdas quickly using core library

---

## 📞 Rollback Plan

If issues occur:
1. Keep old Lambda code in `backup/` folder
2. Revert to old code by redeploying from backup
3. No data loss - only code changes

---

**Migration Complete! 🚀**

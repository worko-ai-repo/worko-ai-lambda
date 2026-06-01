from utilsLocal import *
import os
from dataclasses import dataclass
import ast


@dataclass
class JDRequirements:
    """Data class to hold job description requirements"""
    exp_min: Optional[int] = None
    exp_max: Optional[int] = None
    ctc_min: Optional[int] = None
    ctc_max: Optional[int] = None
    
    def has_experience_requirement(self) -> bool:
        """Check if experience requirement exists"""
        return self.exp_min is not None
    
    def has_ctc_requirement(self) -> bool:
        """Check if CTC requirement exists"""
        return self.ctc_min is not None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for validation functions"""
        result = {}
        if self.has_experience_requirement():
            result["jd_exp"] = {"min": self.exp_min or 0, "max": self.exp_max or 999}
        if self.has_ctc_requirement():
            result["jd_ctc"] = {"min": self.ctc_min or 0, "max": self.ctc_max or 999}
        return result

class QueryParser:
    """Parses user query into structured JD requirements"""
    
    def __init__(self, gpt_client: AzureOpenAIClient):
        self.gpt_client = gpt_client
    
    def parse_query(self, query: str) -> Dict:
        """Parse natural language query into structured format"""
        prompt = f"""you will get a user quiry in str formate from user you need to covert it to a below json formate nver skip any skill or requirements from quiry and never fabricate from your side and skip the key which is not given in the quiry. and never give any explanation or summary just pure json 100% correct output
    if quiry say lpa or years then just give numbers in salary and experience range.
    important instructions.
    1) if quiry says experies or ctc in one number example 5+ years or must have 7 years then, make min max both as given one number. example {{"min":7,"max":7}}
    
    {{
    "jobTitle": "",
    "salaryRange": {{"min": "", "max": ""}},
    "experienceRange": {{"min": "", "max": ""}},
    "numberOfOpenings": "",
    "workMode": "",
    "location": "",
    "noticePeriod": "",
    "typeOfEmployment": "",
    "department": "",
    "coreSkills": [],
    "softSkills": [],
    "technicalSkills": [],
    "goodToHaveSkills": [],
    "mustHaveSkills": [],
    "mandatoryRequirements": [],
    "preferredRequirements": []
    }}
    quiry : {query}"""
        
        return self.gpt_client.invoke_model_with_backoff(
            prompt=prompt, 
            Task="AI prompt summarization."
        )
    
    def extract_jd_requirements(self, parsed_query: str) -> JDRequirements:
        """Extract JD requirements from parsed query"""
        parsed_dict = ast.literal_eval(parsed_query) if isinstance(parsed_query, str) else parsed_query
        
        exp_range = parsed_dict.get("experienceRange", {})
        sal_range = parsed_dict.get("salaryRange", {})
        
        return JDRequirements(
            exp_min=int(exp_range.get("min", 0) or 0) if exp_range.get("min") else None,
            exp_max=int(exp_range.get("max", 999) or 999) if exp_range.get("max") else None,
            ctc_min=int(sal_range.get("min", 0) or 0) if sal_range.get("min") else None,
            ctc_max=int(sal_range.get("max", 999) or 999) if sal_range.get("max") else None
        )

def apply_threshold_adjustments(parsed_query: Dict) -> Dict:
    """Apply CTC and experience threshold adjustments based on validation logic."""
    parsed_dict = ast.literal_eval(parsed_query) if isinstance(parsed_query, str) else parsed_query
    
    exp_range = parsed_dict.get("experienceRange", {})
    sal_range = parsed_dict.get("salaryRange", {})
    
    has_exp = exp_range.get("min") not in (None, "") or exp_range.get("max") not in (None, "")
    has_ctc = sal_range.get("min") not in (None, "") or sal_range.get("max") not in (None, "")
    
    print("\n=== THRESHOLD ADJUSTMENT ===")
    
    # ========== EXPERIENCE ADJUSTMENT ==========
    if has_exp:
        exp_min_val = exp_range.get("min")
        exp_max_val = exp_range.get("max")
        exp_min = float(exp_min_val) if exp_min_val not in (None, "") else None
        exp_max = float(exp_max_val) if exp_max_val not in (None, "") else None
        
        print(f"Experience: {exp_min if exp_min is not None else 'Not specified'}-{exp_max if exp_max is not None else 'Not specified'} years")
        
        # Adjust MIN only if provided
        if exp_min is not None:
            if exp_min <= 3:
                adjusted_min = max(0, exp_min - 1)
                print(f"  MIN: {exp_min} - 1 = {adjusted_min} (0-3y range)")
            elif exp_min <= 6:
                adjusted_min = max(0, exp_min - 1.5)
                print(f"  MIN: {exp_min} - 1.5 = {adjusted_min} (3-6y range)")
            elif exp_min <= 10:
                adjusted_min = max(0, exp_min - 2)
                print(f"  MIN: {exp_min} - 2 = {adjusted_min} (6-10y range)")
            else:
                if exp_min * 0.3 >= 3:
                    if exp_min <= 3:
                        max_gap = 1
                    elif exp_min <= 6:
                        max_gap = 1.5
                    elif exp_min <= 10:
                        max_gap = 2
                    else:
                        max_gap = 3
                    adjusted_min = max(0, exp_min - max_gap)
                    print(f"  MIN: {exp_min} - {max_gap} = {adjusted_min} (10+y gap logic)")
                else:
                    adjusted_min = exp_min * 0.7
                    print(f"  MIN: {exp_min} * 0.7 = {adjusted_min} (10+y percentage logic)")
            
            exp_range["min"] = adjusted_min
        else:
            exp_range.pop("min", None)
        
        # Adjust MAX only if provided
        if exp_max is not None:
            if exp_max <= 3:
                adjusted_max = exp_max + 1
                print(f"  MAX: {exp_max} + 1 = {adjusted_max} (0-3y range)")
            elif exp_max <= 6:
                adjusted_max = exp_max + 1.5
                print(f"  MAX: {exp_max} + 1.5 = {adjusted_max} (3-6y range)")
            elif exp_max <= 10:
                adjusted_max = exp_max + 2
                print(f"  MAX: {exp_max} + 2 = {adjusted_max} (6-10y range)")
            else:
                if exp_max <= 4:
                    adjusted_max = exp_max * 1.6
                    print(f"  MAX: {exp_max} * 1.6 = {adjusted_max} (10+y Statement 1)")
                elif exp_max * 0.4 > 4:
                    adjusted_max = exp_max + 4
                    print(f"  MAX: {exp_max} + 4 = {adjusted_max} (10+y Statement 4)")
                elif exp_max > 4:
                    adjusted_max = exp_max * 1.4
                    print(f"  MAX: {exp_max} * 1.4 = {adjusted_max} (10+y Statement 5)")
            
            exp_range["max"] = adjusted_max
        else:
            exp_range.pop("max", None)
        
        if exp_min is not None or exp_max is not None:
            print(f"  → Adjusted: {exp_range.get('min', 'Not specified')}-{exp_range.get('max', 'Not specified')} years")
    
    # ========== CTC ADJUSTMENT ==========
    if has_ctc:
        ctc_min_val = sal_range.get("min")
        ctc_max_val = sal_range.get("max")
        ctc_min = float(ctc_min_val) if ctc_min_val not in (None, "") else None
        ctc_max = float(ctc_max_val) if ctc_max_val not in (None, "") else None
        
        print(f"CTC: {ctc_min if ctc_min is not None else 'Not specified'}-{ctc_max if ctc_max is not None else 'Not specified'} LPA")
        
        # Remove min if empty
        if ctc_min is None:
            sal_range.pop("min", None)
        
        # Adjust MAX only if provided
        if ctc_max is not None:
            if ctc_max > 10:
                adjusted_max = ctc_max * 1.2
                print(f"  greater than 10 so +20% is acceptable MAX: ({ctc_max} * 1.2) = {adjusted_max}")
            else:
                adjusted_max = ctc_max * 1.3
                print(f"  less than 10 so +30% is acceptable MAX: ({ctc_max} * 1.3) = {adjusted_max}")
            
            sal_range["max"] = int(adjusted_max)
            print(f"  → Adjusted: {sal_range.get('min', 'Not specified')}-{sal_range['max']} LPA")
        else:
            sal_range.pop("max", None)
    
    # Clean up empty fields from entire parsed_dict
    def clean_empty_values(obj):
        if isinstance(obj, dict):
            return {k: clean_empty_values(v) for k, v in obj.items() if v not in (None, "", [], {})}
        elif isinstance(obj, list):
            return [clean_empty_values(item) for item in obj if item not in (None, "", [], {})]
        return obj
    
    parsed_dict = clean_empty_values(parsed_dict)
    
    print("=== ADJUSTMENT COMPLETE ===\n")
    
    return parsed_dict
    

import sys
from pathlib import Path

if __name__ == "__main__":
    shared_layer_path = Path(__file__).parent.parent / "shared-core-layer"
    sys.path.insert(0, str(shared_layer_path))
from ai_clients.gcp_client import GeminiClient
from utils import get_secret

gcp_credentials = None
def lambda_handler(event, context):
    global gcp_credentials
    print("Got a event :- ",event)

    searchByPrompt = event.get("searchByPrompt")
    env = os.environ.get("ENVIRONMENT", "dev")
    # GCP_secret_name = "AZURE-openai-secret-multimodel-"+env
    # azure_secret = get_secret(GCP_secret_name)
    # gptclient = AzureOpenAIClient(azure_secret, model="gpt-4o")
    if not gcp_credentials:
        GCP_secret_name ="GCP-aiplatform-secrect-"+env
        gcp_credentials = get_secret(GCP_secret_name)
    else:    
        print("Using cached GCP credentials")
    gcp = GeminiClient(gcp_credentials,env,model="gemini-3.5-flash")

    # query_parser = QueryParser(gptclient)
    query_parser = QueryParser(gcp)

    parsed_query = query_parser.parse_query(searchByPrompt)
    
    # Apply threshold adjustments based on check_ctc and check_experience logic
    adjusted_query = apply_threshold_adjustments(parsed_query)
    print(adjusted_query)
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(adjusted_query)  # Convert the dictionary to a JSON string
    }

if __name__ == "__main__":
    # Test the function with a sample event
    test_event = {
        "searchByPrompt": "need a software Engineer with 3+ years of experience in java and python with ctc 40"
    }
    result = lambda_handler(test_event, None)
    print(result)



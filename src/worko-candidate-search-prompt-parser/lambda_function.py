from utils import *
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
    if quiry say lpa or years then just give numbers in salary and experience range
    
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
    
    has_exp = exp_range.get("min") is not None or exp_range.get("max") is not None
    has_ctc = sal_range.get("min") is not None or sal_range.get("max") is not None
    
    print("\n=== THRESHOLD ADJUSTMENT ===")
    
    # ========== EXPERIENCE ADJUSTMENT ==========
    if has_exp:
        exp_min = float(exp_range.get("min", 0) or 0)
        exp_max = float(exp_range.get("max", 999) or 999)
        
        print(f"Experience: {exp_min}-{exp_max} years")
        
        # Adjust MIN
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
        
        # Adjust MAX
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
        print(f"  → Adjusted: {exp_range['min']}-{exp_range['max']} years")
    
    # ========== CTC ADJUSTMENT ==========
    if has_ctc:
        ctc_min = float(sal_range.get("min", 0) or 0)
        ctc_max = float(sal_range.get("max", 999) or 999)
        
        print(f"CTC: {ctc_min}-{ctc_max} LPA")
        
        if ctc_max > 10:
            adjusted_max = ctc_max * 1.2
            print(f" greater the 10 so +20% is acceptable MAX: ({ctc_max} * 1.2) ")
        else:
            adjusted_max = ctc_max * 1.3
            print(f" less the 10 so +30% is acceptable MAX: ({ctc_max} * 1.3) ")
        
        sal_range["max"] = int(adjusted_max)
        print(f"  → Adjusted: {sal_range['min']}-{sal_range['max']} LPA")
    
    print("=== ADJUSTMENT COMPLETE ===\n")
    
    return parsed_dict
    


def lambda_handler(event, context):
    print("Got a event :- ",event)

    searchByPrompt = event.get("searchByPrompt")
    env = os.environ.get("ENVIRONMENT", "dev")
    GCP_secret_name = "AZURE-openai-secret-multimodel-"+env
    azure_secret = get_secret(GCP_secret_name)
    gptclient = AzureOpenAIClient(azure_secret, model="gpt-4o")

    query_parser = QueryParser(gptclient)
    parsed_query = query_parser.parse_query(searchByPrompt)
    
    # Apply threshold adjustments based on check_ctc and check_experience logic
    adjusted_query = apply_threshold_adjustments(parsed_query)

    return adjusted_query

if __name__ == "__main__":
    # Test the function with a sample event
    test_event = {
        "searchByPrompt": "Senior Software Engineer must have node js and python sills with 5-12 years experience and CTC 15-20 LPA"
    }
    result = lambda_handler(test_event, None)
    print(result)



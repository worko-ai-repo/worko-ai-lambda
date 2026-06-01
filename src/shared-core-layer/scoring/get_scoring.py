"""Scoring prompts for 4-step JD-Resume matching evaluation."""
import sys
import os
from typing import List, Tuple
from pathlib import Path

if __name__ == "__main__":
    shared_layer_path = Path(__file__).parent.parent / "shared-core-layer"
    sys.path.insert(0, str(shared_layer_path))

# from ai_clients import AzureOpenAIClient
from ai_clients.gcp_client import GeminiClient
from prompt.prompts import *

# Import only specific functions to avoid circular imports
from utils.utils import (
    get_secret,
    create_prompt,
    extract_score_from_OpenAI_response,
    ensure_decimal
)

# Initialize AI client
# env = os.environ.get("ENVIRONMENT", "dev")
# azure_openai_secret_name = "AZURE-openai-secret-multimodel-" + env
# azure_openai_secret = get_secret(azure_openai_secret_name)
# gpt4 = AzureOpenAIClient(azure_openai_secret, model="gpt-4o")
# gpt_models = [gpt4]

# gcp_models =



def get_score(processed_text,job_desc,gcp_models):
    # return {"overall_matching_score": ensure_decimal(81)} #for debugging
    """Calculate matching score for job description and resume.
    
    Args:
        job_desc: Job description text
        
    Returns:
        dict: Scoring results
    """
    overall_Analysis = ""
    temp_score = 0
    overall_matching_score = 0
    try:
        exp_prompt = get_experience_level.format(job_desc=job_desc)

        # Get experience level
        content = gcp_models[0].invoke_model_with_backoff(
            exp_prompt, 
            Task="Extracting experience level for Non-Tech job",
            want_json=True
        )
        print("Experience level response:", content)
        
        # Check experience level in the response content, not completion_text
        experience_level = content.get("experience_level", "").lower()
        # Format the prompt with job description
        tech_prompt = get_tech_non_tech.format(job_desc=job_desc)
        
        # Get tech/non-tech classification
        completion_text = gcp_models[0].invoke_model_with_backoff(
            tech_prompt, 
            Task="checking for tech or non-tech job",
            want_json=False
        )

        found_text = ""
        position = completion_text.find("Non-Technical")

        if position != -1:
            found_text = completion_text[position:position+len("Non-Technical")]
            print("The text '{}' is present.".format(found_text))
        else:
            print("The text 'Non-Technical' is not present.")
        
        # Initialize steps to avoid unassigned reference
        steps = []
        
        if found_text == "Non-Technical":
            print("I am in Non-Tech")
            
            # Format experience level prompt

            
            if "superior" in experience_level:
                print("Superior level - work in progress")
                steps = non_tech_superior
            elif "senior" in experience_level:
                print("Senior level - work in progress")
                steps = non_tech_senior
            elif "junior" in experience_level:
                print("Junior level - work in progress")
                steps = non_tech_junior 
            elif "fresher" in experience_level:
                print("Fresher level - work in progress")
                steps = non_tech_fresher
        else:
            print("Technical role detected")
            if "superior" in experience_level:
                steps = tech_superior
            elif "senior" in experience_level:
                steps = tech_senior
            elif "junior" in experience_level:
                steps = tech_junior
            elif "fresher" in experience_level:
                steps = tech_fresher
        for i, step in enumerate(steps):

            prompt = create_prompt(processed_text, job_desc, step)
            
            # Use different model invocation functions for each step
            if i == 0:
                # Adding code for Open AI processing
                content = gcp_models[0].invoke_model_with_backoff(prompt,Task= "step 1 for score calculations" ,want_json=False)
                print("Open AI content",content)
                overall_Analysis = overall_Analysis + content
                temp_score = extract_score_from_OpenAI_response(content)

                if temp_score is None:
                    temp_score = extract_score_from_OpenAI_response(content)

                # Cap temp_score at 27 if it's greater than 27
                if temp_score is not None and temp_score > 27:
                    temp_score = 27

            elif i == 1:

                # Adding code for Open AI processing
                content = gcp_models[0].invoke_model_with_backoff(prompt,Task= "step 2 for score calculations", want_json=False)
                print("Open AI content",content)
                overall_Analysis = overall_Analysis + content
                temp_score = extract_score_from_OpenAI_response(content)

                if temp_score is None:
                    temp_score = extract_score_from_OpenAI_response(content)
                
                # Cap temp_score at 36 if it's greater than 36
                if temp_score is not None and temp_score > 36:
                    temp_score = 36

            elif i == 2:

                content = gcp_models[0].invoke_model_with_backoff(prompt,Task= "step 3 for score calculations", want_json=False)
                print("Open AI content",content)
                overall_Analysis = overall_Analysis + content
                temp_score = extract_score_from_OpenAI_response(content)

                if temp_score is None:
                    temp_score = extract_score_from_OpenAI_response(content)

                # Cap temp_score at 9 if it's greater than 9
                if temp_score is not None and temp_score > 9:
                    temp_score = 9

            elif i == 3:

                content = gcp_models[0].invoke_model_with_backoff(prompt,Task= "step 4 for score calculations", want_json=False)
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
                content = gcp_models[0].invoke_model_with_backoff(prompt,Task= "Fallback to original function if there are more steps than defined functions", want_json=False)

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
        overall_matching_score = ensure_decimal(overall_matching_score)
        return {
            "overall_Analysis": overall_Analysis,
            "overall_matching_score": overall_matching_score
        }
        
    except Exception as e:
        print(f"An error occurred, during score calculation: {e}")
        return {
            "status": "error",
            "error": str(e)
        }




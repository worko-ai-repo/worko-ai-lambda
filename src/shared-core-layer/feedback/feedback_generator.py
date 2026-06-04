"""Feedback generation for candidate and recruiter."""
import sys
from pathlib import Path
if __name__ == "__main__":
    shared_layer_path = Path(__file__).parent.parent / "shared-core-layer"
    sys.path.insert(0, str(shared_layer_path))
from typing import Dict, Any
from utils import *
from prompt.prompts import (
    feedback_0_70_prompt,
    feedback_greater_the_40,
    feedback_greaterthen_70_prompt,
    feedback_email_greaterthen_40_prompt,
    feedback_email_greaterthen_70_prompt,
    check_mandatory_requirement_prompt,
    feedback_mandatory_requirement_missing_prompt
)
import json
def get_feedback_for_bulk_upload(overall_matching_score,processed_text,job_desc,models,otherRequirements):
    final_completion_text = ""
    rejection_feedback = ""
    emailFeedback = ""
    for model in models:
        try:
        
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
                    f"Strict Rule 3:\n"
                    f" Never use speculative phrases like 'resume shows' or 'appears to have' — state facts directly with calling candidate name.\n"
                )

                
                # content = invoke_model_with_backoff_OpenAI(prompt,Task= "Rejection for 1 <= overall_matching_score < 70:" )
                content =  models[0].invoke_model_with_backoff(prompt,Task= "Rejection for 1 <= overall_matching_score < 70:"  )
                completion_text_rejection = json.dumps(content)

                print("***************************************  1 <70 *********************************************")
                print_completion_text(completion_text_rejection)
                rejection_feedback = completion_text_rejection

                if overall_matching_score > 40:
                    prompt = (f"{final_completion_text}, {completion_text_rejection}\n"
                                f"Based on the above content, write a one-line summary in 20-25 words that highlights ONLY the positive qualities and strengths that make this candidate suitable for the job.\n"
                                f"Focus exclusively on positive aspects - exclude any negative feedback or criticisms.")

                    emailFeedback =  models[0].invoke_model_with_backoff(prompt,Task= "get email feedback for 40-70" ,want_json=False )

                    print("feedback_for_email:-",emailFeedback)
                
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

                # content = invoke_model_with_backoff_OpenAI(prompt,Task= "Score feedback for >70")
                content =  models[0].invoke_model_with_backoff(prompt,Task= "Score feedback for >70")
                completion_text_approval = json.dumps(content)
                completion_text_approval
                
                print("***************************************   >70 *********************************************")
                print_completion_text(completion_text_approval)
                final_completion_text = completion_text_approval

                prompt = (f"{final_completion_text}\n"
                            f"Based on the above content, write a one-line summary in 20-25 words that highlights ONLY the positive qualities and strengths that make this candidate suitable for the job.\n"
                            f"Focus exclusively on positive aspects - exclude any negative feedback or criticisms.")

                emailFeedback =  models[0].invoke_model_with_backoff(prompt,Task= "get email feedback for scor > 70" ,want_json=False )

                
                print("feedback_for_email:-",emailFeedback)
                print("otherRequirements:-", otherRequirements)
                if otherRequirements:
                    prompt = check_mandatory_requirement_prompt.format(processed_text=processed_text, otherRequirements=otherRequirements)
                    analysis_result_json  = models[0].invoke_model_with_backoff(prompt,Task= "Cheching Mandatoey Requirements") 

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

                        completion_text_rejection =  models[0].invoke_model_with_backoff(prompt,Task= "Rejection when amndatory Not met")


                        completion_text_rejection_for_candidate = completion_text_rejection.get("feedback_Candidate")
                        completion_text_rejection= completion_text_rejection.get("feedback_Recruiter")
                        

                        completion_text_rejection = json.dumps(completion_text_rejection)        ### make it string again to store in db
                        completion_text_rejection_for_candidate = json.dumps(completion_text_rejection_for_candidate)  ### make it string again to store in db

                        print_completion_text(f"rejection feedback for Recruiter {completion_text_rejection}")
                        print_completion_text(f"rejection feedback for Candidate {completion_text_rejection_for_candidate}")
                
            elif overall_matching_score == 0:
                rejection_feedback = "We encountered an error while processing. Please try again after some time"
            
            if overall_matching_score > 90:
                print("******Potential Issue******:", overall_matching_score)
                overall_matching_score = 90
            
            return final_completion_text, rejection_feedback, emailFeedback
        except Exception as execution_error:
            if any(term in str(execution_error).lower() for term in ['throttling', 'throttled', 'rate limit', 'too many requests', '429', 'quota', 'resource exhausted']):
                print(f"Throttling error for {model.model}: {execution_error}, sending to retry queue")
                continue
            else:
                print(f"An error occurred: {execution_error}")
                # update_cv_extract_in_dynamodb(table_name, partition_key_value, sort_key_prefix, str(execution_error) , 251, -1)
                return {"statusCode": 500, "body": {"error": str(execution_error)}}


def get_detailed_feedback(processed_text: str, jdItem_extracted: str, overall_Analysis: Dict[str, Any], overall_matching_score: int, otherRequirements: Dict[str, Any], models: list):
    # this func will give positive and negative feedbacks for both recruiter and candidate based on the score and also give feedback for email to candidate.
    try :

        rejection_feedback = ""
        rejectionFeedbackBySystemForApplicant=""   #
        scoreDetails = ""
        scoreDetailsForApplicant=""  #
        completion_text_approval= ""
        emailFeedback = ""

        if 1 <= overall_matching_score < 70:

            prompt = feedback_0_70_prompt.format(processed_text=processed_text, 
                                                    jdItem_extracted=jdItem_extracted, 
                                                    overall_Analysis=overall_Analysis)
            
            try:
                completion_text_rejection = models[0].invoke_model_with_backoff(prompt,Task= "Rejection for 1 <= overall_matching_score < 70:" )
                completion_text_rejection_for_candidate = completion_text_rejection.get("feedback_Candidate")
                completion_text_rejection= completion_text_rejection.get("feedback_Recruiter")
            except Exception as e:
                print(f"[ERROR] Exception in <70 AI call: {e}")
                completion_text_rejection = {"RecruiterNote": "Error", "Strengths": [], "AreasOfConcern": []}
                completion_text_rejection_for_candidate = {"CandidateNote": "Error", "Strengths": [], "AreasOfConcern": []}
            

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

                completion_text_approval= models[0].invoke_model_with_backoff(prompt,Task= "Score feedback  for score >40")
                print_completion_text(completion_text_approval)
                scoreDetails = completion_text_approval.get("feedback_Recruiter")
                scoreDetailsForApplicant = completion_text_approval.get("feedback_Candidate")

                scoreDetails = json.dumps(scoreDetails)        ### make it string again to store in db
                scoreDetailsForApplicant = json.dumps(scoreDetailsForApplicant)        ### make it string again to store in db


                prompt = feedback_email_greaterthen_40_prompt.format(completion_text_approval=completion_text_approval)
                emailFeedback = models[0].invoke_model_with_backoff(prompt,want_json=False,Task= "email feedback  for score >40")
                print("feedback_for_email:-",emailFeedback)
        
        elif overall_matching_score >= 70:

            
            prompt = feedback_greaterthen_70_prompt.format(
                processed_text=processed_text,
                job_desc=jdItem_extracted,
                overall_Analysis=overall_Analysis
            )

            completion_text_approval =models[0].invoke_model_with_backoff(prompt,Task= "Score feedback for >70")


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
            emailFeedback = models[0].invoke_model_with_backoff(prompt,Task= "Score feedback for >70",want_json=False)

            print("feedback_for_email:-", emailFeedback)
            

            print("otherRequirements:-", otherRequirements)
            if otherRequirements:
                prompt = check_mandatory_requirement_prompt.format(processed_text=processed_text, otherRequirements=otherRequirements)
                analysis_result_json  = models[0].invoke_model_with_backoff(prompt,Task= "Cheching Mandatoey Requirements") 

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

                    completion_text_rejection =  models[0].invoke_model_with_backoff(prompt,Task= "Rejection when amndatory Not met")


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

        print("overall_matching_score", overall_matching_score)
        return {
            "rejection_feedback": rejection_feedback,
            "rejectionFeedbackBySystemForApplicant": rejectionFeedbackBySystemForApplicant,
            "scoreDetails": scoreDetails,
            "scoreDetailsForApplicant": scoreDetailsForApplicant,
            "emailFeedback": emailFeedback
            
        }
    except Exception as e:
        print(f"[ERROR] Exception in get_detailed_feedback: {e}")
        import traceback
        traceback.print_exc()
        return {
            "rejection_feedback": "We encountered an error while processing. Please try again after some time",
            "rejectionFeedbackBySystemForApplicant": "",
            "scoreDetails": "",
            "scoreDetailsForApplicant": "",
            "emailFeedback": "",
        }

def get_reason_from_rejection_data(response: Dict[str, Any]) -> str:
     
     data = {i: response[i] for i in response if response[i] != False and i != "Explanation"}
     reason = []
     for i in data:
         if len(data) == 1:
             reason.append(f'{i} is {data[i]}')
         else:
             reason.append(f'{i} is {data[i]}')  	
     reason = " and ".join(reason)
     if reason:
         return reason
     return ""
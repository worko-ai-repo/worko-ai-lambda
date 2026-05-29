
def create_prompt(cv_extract, job_desc, step ):
    return f'Human:\nResume:\n{cv_extract}\nJob Description:\n{job_desc}\n{step}'

# Template strings - use .format() to inject variables
get_tech_non_tech = """Analyze the following job description and classify it as either 'Technical' or 'Non-Technical':
Job Description:
{job_desc}
Considerations for classification:
- Technical roles typically involve programming, engineering, data analysis, or IT skills
- Non-Technical roles typically focus on business, management, sales, or operations
- Respond with only one word: 'Technical' or 'Non-Technical'"""


get_experience_level = """Human: Based on the following job description, please analyze the required years of experience:

{job_desc}

Human: Strictly determine the experience level using ONLY these criteria:
- If years of experience is greater than 12: superior
- If years of experience is between 5 and 12 (inclusive): senior
- If years of experience is between 1 and 5 (exclusive): junior
- If years of experience is less than 1: fresher

Respond EXACTLY in this JSON format without any additional fields or explanations:
{{
  "experience_level": "<determined_level>",
  "criteria_matched": "<exact_matching_criteria_text>"
}}

Do not include any other fields like 'reasoning' or additional commentary. Only provide the specified JSON output."""


# example use
# job_desc = "We are looking for a Senior Software Engineer with 8+ years of experience in backend development, proficient in Python and Java, and with a strong background in cloud technologies."

# tech_prompt = get_tech_non_tech.format(job_desc=job_desc)
# exp_prompt = get_experience_level.format(job_desc=job_desc)

# print(tech_prompt)


# Non-Technical Superior Level Prompts (4 steps)
non_tech_superior = [
    ("Here is the most relevant sentence in the context: Evaluate the resume against the job description based on the following 4 parameters and their respective weighted scores:"
        "1. Experience (5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
        "2. Responsibilities (10 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
        "3. Achievements (5 points) - Look for exact keyword matches or direct mentions of achievements in the resume."
        "4. Core Skills/Core Competencies (10 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
        "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 30 (27), cap it at 27."
        "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
        "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
            "Final Score (rounded to nearest integer) = Section A Score + Section B Score"
            "Maximum: 40 points"
        "Provide results in JSON format: {\"score\": 0-40 (rounded to nearest integer), \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
    ),
    ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
        "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
        "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 10 points to the Matching Score."
        "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 10 points (9) to the Matching Score."
        "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 10 points (5) to the Matching Score."
        "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 10 points (7.5) to the Matching Score."
        "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 10 points (8) to the Matching Score."
        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
        "VALIDATION RULES:"
        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
        "- Do not make assumptions about implied skills or experience"
        "- Weight keywords based strictly on their placement and context within resume sections"
        "- If a keyword appears in multiple sections, use the highest applicable weight"
    )
]

non_tech_senior = [
    ("Here is the most relevant sentence in the context: Evaluate the resume against the job description based on the following 5 parameters and their respective weighted scores:"
        "1. Experience (5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
        "2. Responsibilities (10 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
        "3. Achievements (5 points) - Look for exact keyword matches or direct mentions of achievements in the resume."
        "4. Soft Skills (5 points) - Look for exact keyword matches or direct mentions of soft skills in the resume."
        "5. Core Skills/Core Competencies (5 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
        "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 30 (27), cap it at 27"
        "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
        "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
            "Final Score (rounded to nearest integer) = Section A Score + Section B Score"
            "Maximum: 40 points"
        "Provide results in JSON format: {\"score\": 0-40 (rounded to nearest integer), \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
    ),
    ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
        "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
        "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 10 points to the Matching Score."
        "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 10 points (9) to the Matching Score."
        "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 10 points (5) to the Matching Score."
        "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 10 points (7.5) to the Matching Score."
        "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 10 points (8) to the Matching Score."
        "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
        "VALIDATION RULES:"
        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
        "- Do not make assumptions about implied skills or experience"
        "- Weight keywords based strictly on their placement and context within resume sections"
        "- If a keyword appears in multiple sections, use the highest applicable weight"
    )
]

non_tech_junior  =[
                                    ("Here is the most relevant sentence in the context: Evaluate the resume against the job description based on the following 5 parameters and their respective weighted scores:"
                                                "1. Experience (5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                                "2. Responsibilities (10 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                                "3. Achievements (5 points) - Look for exact keyword matches or direct mentions of achievements in the resume."
                                                "4. Soft Skills (5 points) - Look for exact keyword matches or direct mentions of soft skills in the resume."
                                                "5. Core Skills/Core Competencies (5 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                                "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 30 (27), cap it at 27"
                                                "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                                "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
                                                "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                            "Final Score (rounded to nearest integer) = Section A Score + Section B Score"
                                            "Maximum: 40 points"
                                        "Provide results in JSON format: {\"score\": 0-40 (rounded to nearest integer), \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
                                    ),
                                    ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
                                                "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                                "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 10 points to the Matching Score."
                                                "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 10 points (9) to the Matching Score."
                                                "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 10 points (5) to the Matching Score."
                                                "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 10 points (7.5) to the Matching Score."
                                                "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 10 points (8) to the Matching Score."
                                                "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                                "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
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
                                        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                        "VALIDATION RULES:"
                                        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                        "- Do not make assumptions about implied skills or experience"
                                        "- Weight keywords based strictly on their placement and context within resume sections"
                                        "- If a keyword appears in multiple sections, use the highest applicable weight"
                                    )
                                ]

non_tech_fresher = [
                                    ("Here is the most relevant sentence in the context: Evaluate the resume against the job description based on the following 2 parameters and their respective weighted scores:"
                                                "1. Experience (10 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                                "2. Soft Skills (15 points) - Look for exact keyword matches or direct mentions of soft skills in the resume."
                                                "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 25 (22.5), cap it at 22.5."
                                                "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                                "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
                                                "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
                                    ),
                                    ("Here is the most relevant sentence in the context: Additionally, check for any specific relevant experience mentioned in the job description:"
                                                "If specific relevant Project/Internship/Experience/skills is mentioned as mandatory in the job description and it is not present in the resume, add 0% of 25 points to the Matching Score."
                                                "If specific relevant Project/Internship/Experience/skills is mentioned as mandatory in the job description and it is present in the resume, add 90% of 25 points (22.5) to the Matching Score."
                                                "If specific relevant Project/Internship/Experience/skills is mentioned as non-mandatory or preferred in the job description and it is present in the resume, add 90% of 25 points (22.5) to the Matching Score."
                                                "If specific relevant Project/Internship/Experience/skills is mentioned as non-mandatory or preferred in the job description and it is not present in the resume, add 60% of 25 points (15) to the Matching Score."
                                                "Before calculating the score, identify and list the most relevant sentences from the job description that specify the required or preferred experience, and the corresponding sentences from the resume that match or do not match these requirements."
                                                "Show the points given. Present it in JSON format with score field and detailedAnalysis field without any additional calculations or explanations."
                                                "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
                                    ("Here is the most relevant sentence in the context: Check if any specific kind of educational requirement is asked in the job description (like specific certification, specific college or MBA/Executive MBA from a Tier 1 institute, specific degree type)"
                                                "Before evaluating, identify and list the most relevant sentences from the job description that specify educational requirements, and the corresponding sentences from the resume that match or do not match these requirements."
                                                "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is not present in the resume, then add 0% of 30 points to the Matching Score."
                                                "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as mandatory, and it is present in the resume, then add 90% of 30 points (27) to the Matching Score."
                                                "If a specific educational requirement (like graduation from a Tier 1 institute) is being asked in the job description as preferred, and it is not present in the resume, then add 50% of 30 points (15) to the Matching Score."
                                                "If any specific educational requirement is not being asked in the job description, and the resume also does not have Tier 1 institute educational details, then add 75% of 30 points (22.5) to the Matching Score."
                                                "If any specific educational requirement is not being asked in the job description, but the resume has Tier 1 institute educational details, then add 80% of 30 points (24) to the Matching Score."
                                                "Show the points given. Present it in JSON format with score field and detailedAnalysis field."
                                                "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"),
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
                                        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                        "VALIDATION RULES:"
                                        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                        "- Do not make assumptions about implied skills or experience"
                                        "- Weight keywords based strictly on their placement and context within resume sections"
                                        "- If a keyword appears in multiple sections, use the highest applicable weight"
                                    )
                                ]
        
tech_superior = [
                                ("Here is the most relevant sentence in the context: Rate the resume against the job description based on the following 5 parameters:"
                                        "1. Technical Skills (weighted score: 10 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                        "2. Experience (weighted score: 5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                        "3. Education (weighted score: 5 points) - If no specific educational requirement is mentioned, award full points for a relevant degree, regardless of the institution."
                                        "4. Responsibilities (weighted score: 10 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                        "5. Achievements (weighted score: 5 points) - Look for exact keyword matches or direct mentions of achievements in the resume."
                                        "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 35 (31.5), cap it at 31.5"
                                        "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                        "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                            "Final Score (rounded to nearest integer) = Section A Score + Section B Score"
                                            "Maximum: 40 points"
                                        "Provide results in JSON format: {\"score\": 0-40 (rounded to nearest integer), \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
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
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                        "VALIDATION RULES:"
                                        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                        "- Do not make assumptions about implied skills or experience"
                                        "- Weight keywords based strictly on their placement and context within resume sections"
                                        "- If a keyword appears in multiple sections, use the highest applicable weight"
                                    )
                        ] 

tech_senior =[
                                ("Here is the most relevant sentence in the context: Rate the resume against the job description based on the following 5 parameters:"
                                        "1. Technical Skills (weighted score: 15 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                        "2. Experience (weighted score: 5 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                        "3. Education (weighted score: 5 points) - If no specific educational requirement is mentioned, award full points for a relevant degree, regardless of the institution."
                                        "4. Responsibilities (weighted score: 5 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                        "5. Achievements (weighted score: 5 points) - Look for exact keyword matches or direct mentions of achievements in the resume."
                                        "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 35 (31.5), cap it at 31.5"
                                        "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                        "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                            "List all non-skill mandatory requirements (education, company, location, industry, sector, etc.)."
                                            "If the candidate meets ALL non-skill requirements → 16 points."
                                            "If ANY non-skill requirement is missing → 0 points."
                                            "SCORING CALCULATION"
                                            "Final Score (rounded to nearest integer) = Section A Score + Section B Score"
                                            "Maximum: 40 points"
                                        "Provide results in JSON format: {\"score\": 0-40 (rounded to nearest integer), \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
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
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                        "VALIDATION RULES:"
                                        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                        "- Do not make assumptions about implied skills or experience"
                                        "- Weight keywords based strictly on their placement and context within resume sections"
                                        "- If a keyword appears in multiple sections, use the highest applicable weight"
                                    )
                            ]
                            
tech_junior = [
                                ("Here is the most relevant sentence in the context: Rate the resume against the job description based on the following 5 parameters:"
                                        "1. Technical Skills (weighted score: 5 points) - Strictly look for exact keyword matches or direct mentions of the required skills in the resume. Do not give partial credit for related experience."
                                        "2. Experience (weighted score: 10 points) - Consider only the relevant experience directly aligning with the job description. Do not overinterpret broad experience."
                                        "3. Education (weighted score: 5 points) - If no specific educational requirement is mentioned, award full points for a relevant degree, regardless of the institution."
                                        "4. Responsibilities (weighted score: 5 points) - Look for exact keyword matches or direct mentions of responsibilities in the resume."
                                        "5. Soft Skills (weighted score: 5 points) - Look for exact keyword matches or direct mentions of soft skills in the resume."
                                        "Calculate the Matching Score by summing up the scores for each parameter. If the Matching Score is higher than 90% of 30 (27), cap it at 27"
                                        "Before responding, identify and list the most relevant sentences from the resume and job description that support your evaluation for each parameter."
                                        "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                            "Final Score (rounded to nearest integer) = Section A Score + Section B Score"
                                            "Maximum: 40 points"
                                        "Provide results in JSON format: {\"score\": 0-40 (rounded to nearest integer), \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
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
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                        "VALIDATION RULES:"
                                        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                        "- Do not make assumptions about implied skills or experience"
                                        "- Weight keywords based strictly on their placement and context within resume sections"
                                        "- If a keyword appears in multiple sections, use the highest applicable weight"
                                    )
                            ]
        
tech_fresher = [
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
                                        "Present Matching Score in JSON format with score field (rounded to nearest integer) and detailedAnalysis field without any additional calculations or explanations."
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                            "Final Score (rounded to nearest integer) = Section A Score + Section B Score"
                                            "Maximum: 40 points"
                                        "Provide results in JSON format: {\"score\": 0-40 (rounded to nearest integer), \"sectionA\": {\"skillsFound\": [], \"skillsMissing\": [], \"pointsPerSkill\": 0, \"totalSkills\": 0, \"score\": 0}, \"sectionB\":{\"requirementsMet\": [], \"requirementsMissing\": [], \"allRequirementsMet\": false, \"score\": 0}, \"recommendation\": \"\"}"
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
                                        "{\"score\": final score (rounded to nearest integer),\"detailedAnalysis\": [{\"keyword\": [keyword], \"weightage\": [assigned weight], \"found\": [true/false], \"points\": [points awarded], \"matchingText\": [matching sentence from resume]}]}"
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
                                        "{\"score\": final score (rounded to nearest integer), \"detailedAnalysis\": [{\"keyword\": \"[keyword]\", \"jdWeight\": \"[weight from job description]\", \"resumeWeight\": \"[weight from resume analysis]\", \"matchRatio\": \"[resume weight / jd weight]\", \"pointsAwarded\": \"[final points for this keyword]\", \"jdContext\": \"[sentence from JD containing keyword]\", \"resumeContext\": \"[sentence from resume containing keyword or 'Not Found']\", \"resumeSection\": \"[which section of resume: Experience/Skills/Education/Summary/NotFound]\"}], \"summary\": {\"totalPossiblePoints\": 20, \"totalEarnedPoints\": \"[sum before cap]\", \"finalScore\": \"[final score after 18-point cap]\", \"matchPercentage\": \"[final score / 20 * 100]%\"}}"
                                        "VALIDATION RULES:"
                                        "- Only consider exact keyword matches or very close variations (e.g., \"JavaScript\" and \"JS\")"
                                        "- Do not make assumptions about implied skills or experience"
                                        "- Weight keywords based strictly on their placement and context within resume sections"
                                        "- If a keyword appears in multiple sections, use the highest applicable weight"
                                    )
                            ]

feedback_greaterthen_70_prompt = """You are an expert recruiter. Your only task is to compare the candidate profile against the job description.
Only use details explicitly stated in the provided text. Do not infer, assume, or invent information.

Input:
- Candidate Profile: {processed_text}
- Job Description: {job_desc}
- Extra Analysis: {overall_Analysis}

Output:
Provide recruiter feedback in JSON format with two keys: feedback_Recruiter, feedback_Candidate.
Each feedback will have three keys: "Note", "Strengths", and "Areas of Concern".

Format Example:
{{
  "feedback_Recruiter": {{
    "RecruiterNote": "3-5 sentence recruiter-friendly summary of candidate fit, overall impression, and readiness for the role.",
    "Strengths": [
      "[name of candidate] has X years of Y experience in Z industry, directly meeting the required N years in the job description.",
      "Demonstrates proven skills in A and B, which match the mandatory requirement for this role."
    ],
    "AreasOfConcern": [
      "Lacks explicit experience in required skill/tool X, which is mandatory in the job description."
    ]
  }},
  "feedback_Candidate": {{
    "CandidateNote": "3-5 sentence candidate-friendly summary of fit, strengths, and shortfalls written in direct and clear language.",
    "Strengths": [
      "You bring X years of Y experience in Z industry, directly meeting the required N years in the job description.",
      "You demonstrate proven skills in A and B, which match the mandatory requirement for this role."
    ],
    "AreasOfConcern": [
      "You lack explicit experience in required skill/tool X, which is mandatory in the job description."
    ]
  }}
}}

Strict Rules:
1. RecruiterNote or CandidateNote: A concise 3-5 line summary of candidate fit, overall impression, and readiness for the role.
2. Every point in Strengths and Areas of Concern must be a direct Job Description vs Candidate comparison only.
   - If requirement is not present in Job Description or Candidate Profile, do not mention it.
   - If requirement is in Job Description but missing in Candidate Profile, flag it under concerns.
   - If requirement is in Job Description and fully/over met in Candidate Profile, add it under strengths.
3. Limit to maximum 3 strengths and 2 concerns (total 5 points).
4. Each point must be 15-25 words, sharp, factual, and recruiter-ready.
5. Treat missing info as missing - never assume or generalize.
6. Apply Special Mentions only if explicitly visible in Candidate Profile:
   - Unemployed for 12+ months.
   - Frequent job changes (<1 year).
   - Experience significantly above requirement (mark as strength).
7. Use natural, direct language that sounds human-written, not AI-generated.
- Flag: Educational qualification gaps
- Flag: Experience is higher than the required experience for the job
- Flag: Critical technical skills missing
- Flag: Industry experience insufficient
- Flag: Required certifications absent
- Flag: Leadership/management experience lacking when required
- Flag: Career progression inconsistencies
- SPECIAL MENTION: Extended unemployment periods (12+ months)
- SPECIAL MENTION: Pattern of short tenure roles (<1 year)
- LOCATION RULE: Only mention location concerns if candidate explicitly states inability to work from required location in resume.
- LANGUAGE RULE: Only mention language deficiency if candidate explicitly lacks required languages in resume.
- Tone should be objective, professional, and decision-focused for HR evaluation.
8. Focus only on Job Description requirements matched with candidate evidence - highlight why candidate deserves shortlist.
9. Keep summary crisp, keyword-heavy, pulling exact terms from Job Description and Candidate Profile.
10. If you say skills match, tell which particular skill from both Candidate Profile and Job Description. If experience matches, tell which particular experience matches.
11. Never say anything in a broad perspective, provide all the exact reasons from Candidate Profile.
12. Do not mention communication skills, cultural fit, or location unless explicitly present in both Job Description and Resume.
13. For RecruiterNote never use speculative phrases like 'resume shows' or 'appears to have' - state facts directly with calling candidate name.
    For CandidateNote never use speculative phrases like 'your resume shows' or 'appears to have' - talk directly with candidate.
15. EXACT WORDING RULE: Only use terminology explicitly stated in the resume/Job Description. Never generalize specific implementations into broader industry terms.
16. NO DOMAIN INFERENCE: Do not infer industry expertise from individual projects or features. State only the specific technologies/projects mentioned.
17. FACT-CHECK REQUIREMENT: Before including any point, verify the exact phrase exists in either the Job Description or Candidate Profile text.
18. There must be only 2 points in AreasOfConcern and 2-3 points in Strengths.
    In entire feedback never talk about number of years experience. You can talk about domain experience if needed.
19. GRANULAR SPECIFICITY: When mentioning experience, reference the exact role/company where it was gained, not as broad industry background.
20. Output format must be valid JSON only, no text outside JSON."""

feedback_email_greaterthen_70_prompt = """{completion_text_approval}\n"
                        Based on the above content, write a one-line summary in 20-25 words that highlights ONLY the positive qualities and strengths that make this candidate suitable for the job.\n"
                        Focus exclusively on positive aspects - exclude any negative feedback or criticisms.do not give output like here is feeback or any thing like this just give feedback no system message"""

check_mandatory_requirement_prompt = """You are a precise resume analysis assistant. Your task is to determine if a candidate meets ALL mandatory requirements.\n\n"
            **Resume Content:**\n
            {processed_text}\n\n
            **Mandatory Requirements:**\n
            {otherRequirements}\n\n
            **Critical Parsing Instructions:**\n
            You need to check Resume Content whether the Mandatory Requirements met by candidate or Not be verry strict and do not over evaluate candidate. say yes or Not
            all Mandatory Requirements should strictly match with Resume then only say No otherwise If any one Mandatory Requirement is not met say directly Yes
            1. FIRST, carefully parse the requirements text to identify individual requirements\n
            2. Look for conjunctions like 'and', semicolons, bullet points, or numbered lists that separate requirements\n
            3. Pay attention to negations like 'not necessary', 'not required' - these typically indicate something is NOT a requirement\n
            4. If a sentence contains multiple clauses, break them down logically\n
            5. Example: 'Must have X and Y is not necessary' = Two items: 'Must have X' (required) + 'Y is not necessary' (Y is NOT required)\n\n
            if Mandatory Requirements is NA or Null the it mean there is no Mandatory Requirements provided in job description in this case say No 
            **Analysis Instructions:**\n
            1. For each identified requirement, look for clear, explicit evidence in the resume\n
            2. A requirement is 'met' only if there is direct evidence or reasonable inference from resume content\n
            3. For work authorization: Look for explicit statements, citizenship mentions, or work history patterns that indicate legal work status\n
            4. For location/relocation: Consider current location and any mobility statements\n
            5. For skills/experience: Look for direct mentions, project descriptions, or work history that demonstrates the skill\n
            6. If ANY mandatory requirement lacks sufficient evidence, flag as missing\n
            7. Be reasonably conservative but not overly strict - use professional judgment\n\n
            Example: Must have a tier 1 college degree Output --> Yes
            **Required JSON Response Format:**\n
            {{\n"
                "mandatory_skills_missing": "Yes" or "No",\n
                "analysis": {{\n
                    "parsed_requirements": ["list each individual requirement you identified"],\n
                    "requirements_met": ["requirements with sufficient evidence"],\n
                    "requirements_missing": ["requirements lacking evidence"],\n
                    "evidence_summary": {{\n
                        "requirement_1": "evidence found or reason for missing",\n
                        "requirement_2": "evidence found or reason for missing"\n
                    }},\n
                    "confidence_level": "High" or "Medium" or "Low"\n
                }}\n
            }}\n\n
            **Important Guidelines:**\n"
            - Use professional judgment to parse complex requirement strings\n
            - Look for explicit evidence but allow reasonable inferences from work history\n
            - If requirements are unclear or contradictory, note this in your analysis\n
            - Respond with valid JSON only, no additional text"""



                # feedback_greaterthen_70_prompt = f"""You are an expert recruiter. Your only task is to compare the candidate profile against the job description."
                #             Only use details explicitly stated in the provided text. Do not infer, assume, or invent information."
                #             "Input:"
                #             Candidate Profile: {processed_text}"
                #             - Job Description: {job_desc}"
                #             - Extra Analysis: {overall_Analysis}"
                #             "Output:"
                #             "Provide recruiter feedback in JSON format with two keys: feedback_Recruiter, feedback_Candidate"
                #             "Each feedback will have three keys: \"Note\", \"Strengths\", and \"Areas of Concern\"."
                #             "Format Example:"
                #             "{{\n"
                #             "  \"feedback_Recruiter\": {{\n"
                #             "    \"RecruiterNote\": \"3–5 sentence recruiter-friendly summary of candidate fit, overall impression, and readiness for the role.\",\n"
                #             "    \"Strengths\": [\n"
                #             "      \"[name of candidate] Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                #             "      \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                #             "    ],\n"
                #             "    \"AreasOfConcern\": [\n"
                #             "      \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                #             "    ]\n"
                #             "  }},\n"
                #             "  \"feedback_Candidate\": {{\n"
                #             "    \"CandidateNote\": \"3–5 sentence candidate-friendly summary of fit, strengths, and shortfalls written in direct and clear language.\",\n"
                #             "    \"Strengths\": [\n"
                #             "      \"You bring X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n"
                #             "      \"You demonstrate proven skills in A and B, which match the mandatory requirement for this role.\"\n"
                #             "    ],\n"
                #             "    \"AreasOfConcern\": [\n"
                #             "      \"You lack explicit experience in required skill/tool X, which is mandatory in the job description.\"\n"
                #             "    ]\n"
                #             "  }}\n"
                #             "}}\n"
                #             "Strict Rules:"  
                #             "1. **RecruiterNote or CandidateNote ** → A concise 3–5 line summary of candidate fit, overall impression, and readiness for the role."  
                #             "2. Every point in \"Strengths\" and \"Areas of Concern\" must be a **direct Job Description vs Candidate comparison** only."  
                #             "   - If requirement is not present in Job Description or Candidate Profile, do not mention it."  
                #             "   - If requirement is in Job Description but missing in Candidate Profile, flag it under concerns."  
                #             "   - If requirement is in Job Description and fully/over met in Candidate Profile, add it under strengths."  
                #             "3. Limit to maximum **3 strengths** and **2 concerns** (total 5 points)."  
                #             "4. Each point must be **15–25 words**, sharp, factual, and recruiter-ready."  
                #             "5. Treat missing info as missing — never assume or generalize."  
                #             "6. Apply Special Mentions only if explicitly visible in Candidate Profile:"  
                #             "   - Unemployed for 12+ months."  
                #             "   - Frequent job changes (<1 year)."  
                #             "   - Experience significantly above requirement (mark as strength)." 
                #             "7.Use natural, direct language that sounds human-written, not AI-generated\n"
                #             "− Flag: Educational qualification gaps\n"
                #             " Flag: Experience is higher than the required experience for the job\n"
                #             "- Flag: Critical technical skills missing\n"
                #             "- Flag: Industry experience insufficient\n"
                #             "- Flag: Required certifications absent\n"
                #             "- Flag: Leadership/management experience lacking when required\n"
                #             "- Flag: Career progression inconsistencies\n"
                #             "- SPECIAL MENTION: Extended unemployment periods (12+ months)\n"
                #             "- SPECIAL MENTION: Pattern of short tenure roles (<1 year)\n"
                #             "- LOCATION RULE: Only mention location concerns if candidate explicitly states inability to work from required location in resume. If location not mentioned, assume candidate is willing to work from any location.\n"
                #             "- LANGUAGE RULE: Only mention language deficiency if candidate explicitly lacks required languages in resume. If languages not mentioned, assume candidate has required language skills.\n"
                #             "- Tone should be objective, professional, and decision-focused for HR evaluation\n" 
                        
                #             "8. Focus only on **Job Description requirements matched with candidate evidence** — highlight why candidate deserves shortlist."  
                #             "9. Keep summary **crisp, keyword-heavy**, pulling exact terms from Job Description and Job Description."  
                #             "10. if you say skills matches tell which particular skill which is direct from Candidate Profile and Job Description, if you say experience matches then tell which particular experience matches."
                #             "11. Never say anything in a broad perspective just porvide all the exact reasons from Candidate Profile that why this is a ideal candidate."
                #             "12. Do not mention communication skills, cultural fit, or location unless explicitly present in both Job Description and Resume."  
                #             "13. -For RecruiterNote never use speculative phrases like 'resume shows' or 'appears to have' — state facts directly with calling candidate name."
                #             "    -For CandidateNote never use speculative phrases like 'your resume shows' or 'appears to have' — talk dierectly with candidate. state facts directly with calling candidate name."
                #             "15. **EXACT WORDING RULE**: Only use terminology explicitly stated in the resume/Job Description. Never generalize specific implementations into broader industry terms."
                #             "16. **NO DOMAIN INFERENCE**: Do not infer industry expertise from individual projects or features. State only the specific technologies/projects mentioned."
                #             "17. **FACT-CHECK REQUIREMENT**: Before including any point, verify the exact phrase exists in either the Job Description or Candidate Profile text."
                #             "18. there must be only 2 points in AreasOfConcern and 2-3 points in Strengths"
                #             " - In entire feedback never talk about number of years experience. you can talk about domain experience if needed"
                #             "19. **GRANULAR SPECIFICITY**: When mentioning experience, reference the exact role/company where it was gained, not as broad industry background."  
                #             "20. Output format must be **valid JSON only**, no text outside JSON."""   
        
feedback_mandatory_requirement_missing_prompt = """Analyze why this candidate scored low against job mandatory requirements. Return response in exact JSON format:\n
    JSON must contain exactly two top-level keys: feedback_Recruiter and feedback_Candidate\n
    {{\n
        \"feedback_Recruiter\": {{\n
        \"RecruiterNote\": \"3–5 sentence recruiter-friendly summary of candidate fit, overall impression, and readiness for the role.\",\n
        \"Strengths\": [\n"
            \"[name of candidate] Has X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n
            \"Demonstrates proven skills in A and B, which match the mandatory requirement for this role.\"\n
        ],\n"
        \"AreasOfConcern\": [\n"
            \"Lacks explicit experience in required skill/tool X, which is mandatory in the job description.\"\n
        ]\n"
        }},\n"
        \"feedback_Candidate\": {{\n"
        \"CandidateNote\": \"3–5 sentence candidate-friendly summary of fit, strengths, and shortfalls written in direct and clear language.\",\n
        \"Strengths\": [\n"
            \"You bring X years of Y experience in Z industry, directly meeting the required N years in the job description.\",\n
            \"You demonstrate proven skills in A and B, which match the mandatory requirement for this role.\"\n
        ],\n"
        \"AreasOfConcern\": [\n"
            \"You lack explicit experience in required skill/tool X, which is mandatory in the job description.\"\n
        ]\n"
        }}\n"
    }}\n"
    Strict Rule 1 :\n
    1. RecruiterNote → Concise 3–5 line factual summary of candidate fit and readiness.\n
    2. Every point in Strengths and AreasOfConcern must be a direct Job Description vs Candidate comparison only.\n
        - If requirement not present in JD or Candidate Profile → do not mention.\n
        - If requirement in JD but missing in Candidate Profile → flag under AreasOfConcern.\n
        - If requirement in JD and fully/over met → include under Strengths.\n
    3. Limit: max 3 strengths and 2 concerns (5 points total).\n
    4. Each point must be 15–25 words, sharp, factual, recruiter-ready.\n
    5. Treat missing info as missing — never assume.\n
    6. Apply Special Mentions only if explicitly visible in Candidate Profile:\n
        - Unemployed 12+ months.\n
        - Frequent job changes (<1 year).\n
        - Experience significantly above requirement (mark as strength).\n
    Strict Rule 2 :\n
    In RecruiterNote → Never use speculative phrases like 'resume shows' or 'appears to have'. State facts directly.with calling candidate. [name of candidate] have 15+ experience in...\n
    Strict Rule 3 :\n
    In CandidateNote → Never use speculative phrases like 'your resume shows' or 'appears to have'. State facts directly with 'you...'\n
    Requirements:\n
    - Each detail must be a direct 15–25 word statement starting with 'Candidate has no...' or 'Candidate lacks...'\n
    - Focus only on missing mandatory requirements from the JD.\n"
    - Flag: Educational gaps, experience above requirement, missing technical skills, insufficient industry experience, absent certifications, lacking leadership/management, career inconsistencies.\n
    - Special Mentions: Extended unemployment 12+ months, frequent short tenure roles <1 year.\n
    - Location: Only mention if candidate explicitly states inability to work in required location.\n
    - Language: Only mention if candidate explicitly lacks required language skills.\n
    - Tone: Objective, professional, decision-focused.\n
    - There must be only 2 points in AreasOfConcern and 2-3 points in Strengths
        - In entire feedback never talk about number of years experience in AreasOfConcern. you can talk about domain experience if needed
    - Omit detail field if heading itself is self-explanatory.\n
    candidate profile : {processed_text}, job requirements : {jdItem_extracted}\n
    these are some of missing requirements in this candidate focus on these while generating feedback {requirements_missing}
    - **Last check** In entire feedback there must not be contracdiction if finds any correct it."""

feedback_0_70_prompt = """candidate profile : {processed_text}, job requirements : {jdItem_extracted}
Analyze why this candidate scored low against job requirements highlight. Return response in exact JSON format:
JSON must contain exactly two top-level keys: feedback_Recruiter and feedback_Candidate
{{
  "feedback_Recruiter": {{
    "RecruiterNote": "3–5 sentence recruiter-friendly summary of candidate fit, overall impression, and readiness for the role.",
    "Strengths": [
      "[name of candidate] Has X years of Y experience in Z industry, directly meeting the required N years in the job description.",
      "Demonstrates proven skills in A and B, which match the mandatory requirement for this role."
    ],
    "AreasOfConcern": [
      "Lacks explicit experience in required skill/tool X, which is mandatory in the job description."
    ]
  }},
  "feedback_Candidate": {{
    "CandidateNote": "3–5 sentence candidate-friendly summary of fit, strengths, and shortfalls written in direct and clear language.",
    "Strengths": [
      "You bring X years of Y experience in Z industry, directly meeting the required N years in the job description.",
      "You demonstrate proven skills in A and B, which match the mandatory requirement for this role."
    ],
    "AreasOfConcern": [
      "You lack explicit experience in required skill/tool X, which is mandatory in the job description."
    ]
  }}
}}
Strict Rule 1 :
1. RecruiterNote → Concise 3–5 line factual summary of candidate fit and readiness.
2. Every point in Strengths and AreasOfConcern must be a direct Job Description vs Candidate comparison only.
   - If requirement not present in JD or Candidate Profile → do not mention.
   - If requirement in JD but missing in Candidate Profile → flag under AreasOfConcern.
   - If requirement in JD and fully/over met → include under Strengths.
3. Limit: max 3 strengths and 2 concerns (5 points total).
4. Each point must be 15–25 words, sharp, factual, recruiter-ready.
5. Treat missing info as missing — never assume.
6. Apply Special Mentions only if explicitly visible in Candidate Profile:
   - Unemployed 12+ months.
   - Frequent job changes (<1 year).
   - Experience significantly above requirement (mark as strength).
Strict Rule 2 :
In RecruiterNote → Never use speculative phrases like 'resume shows' or 'appears to have'. State facts directly.with calling candidate. [name of candidate] have 15+ experience in...
Strict Rule 3 :
In CandidateNote → Never use speculative phrases like 'your resume shows' or 'appears to have'. State facts directly with 'you...'
Requirements:
- Total 3 items focusing on critical gaps that caused rejection.
- Each detail must be a direct 15–25 word statement starting with 'Candidate has no...' or 'Candidate lacks...'
- Headings should be meaningful and aligned with the issue (e.g., 'Missing Required Certification', 'Insufficient Industry Experience').
- Never start headings with 'Candidate has no...' — that's for the details.
- Focus only on missing mandatory requirements from the JD.
- Flag: Educational gaps, experience above requirement, missing technical skills, insufficient industry experience, absent certifications, lacking leadership/management, career inconsistencies.
- Special Mentions: Extended unemployment 12+ months, frequent short tenure roles <1 year.
- Location: Only mention if candidate explicitly states inability to work in required location.
- Language: Only mention if candidate explicitly lacks required language skills.
- Tone: Objective, professional, decision-focused.
- There must be only 2 points in AreasOfConcern and 2-3 points in Strengths - In entire feedback never talk about number of years experience. you can talk about domain experience if needed
- Omit detail field if heading itself is self-explanatory.
"""

feedback_greater_the_40 = """You are an expert recruiter. Your only task is to compare the candidate profile against the job description.
Only use details explicitly stated in the provided text. Do not infer, assume, or invent information.
Input:
- Candidate Profile: {processed_text}
- Job Description: {job_desc}
- Extra Analysis: {overall_Analysis}
Output:
Provide recruiter feedback in JSON format with three keys: "RecruiterNote", "Strengths", and "Areas of Concern".
Format Example:
{{
  "feedback_Recruiter": {{
    "RecruiterNote": "3–5 sentence recruiter-friendly summary of candidate fit, overall impression, and readiness for the role.",
    "Strengths": [
      "[name of candidate] Has X years of Y experience in Z industry, directly meeting the required N years in the job description.",
      "Demonstrates proven skills in A and B, which match the mandatory requirement for this role."
    ],
    "AreasOfConcern": [
      "Lacks explicit experience in required skill/tool X, which is mandatory in the job description."
    ]
  }},
  "feedback_Candidate": {{
    "CandidateNote": "3–5 sentence candidate-friendly summary of fit, strengths, and shortfalls written in direct and clear language.",
    "Strengths": [
      "You bring X years of Y experience in Z industry, directly meeting the required N years in the job description.",
      "You demonstrate proven skills in A and B, which match the mandatory requirement for this role."
    ],
    "AreasOfConcern": [
      "You lack explicit experience in required skill/tool X, which is mandatory in the job description."
    ]
  }}
}}
Strict Rules:
1. **RecruiterNote** → A concise 2–3 line summary of candidate fit, overall impression, and readiness for the role.
2. Every point in "Strengths" and "Areas of Concern" must be a **direct JD vs candidate comparison**.
   - If it's not in both, do not mention it.
   - If requirement is missing in profile, flag under concerns.
   - If requirement is fully met/exceeded, add to strengths.
3. Maximum 3 strengths and 2 concerns (total 5 points).
4. Each statement must be 15–25 words, factual, and recruiter-ready.
5. Treat missing info as missing — never assume.
6. Apply Special Mentions only if explicitly visible:
   - Unemployed for 12+ months.
   - Frequent job changes (<1 year).
   - Experience significantly above requirement (mark as strength).
7. Do not comment on communication skills or location unless explicitly stated in both JD and profile.
8. Never use phrases like "resume shows" or "appears to have." Always describe the candidate directly.
9. there must be only 2 points in AreasOfConcern and 2-3 points in Strengths
 - In entire feedback never talk about number of years experience. you can talk about domain experience if needed
10. Output must be valid JSON only — no text outside JSON
"""

feedback_email_greaterthen_40_prompt = """{completion_text_approval}\n"
        Based on the above content, write a one-line summary in 20-25 words that highlights ONLY the positive qualities and strengths that make this candidate suitable for the job.\n"
        Focus exclusively on positive aspects - exclude any negative feedback or criticisms."""





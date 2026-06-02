09/03/2026


added this lines in the prompt only code changes
candidateLocation must be only city name followed by state name examples. Mumbai, Maharahstra,  Bengaluru Karnataka"

worko-agency-bulk-jd-resume-matching
worko-bulk-jd-resume-matching
worko-cand-profile-parser
worko-referral-source-cand-profile-parser
worko-resume-parser
worko-cand-profil-parser

12/03/2026
added large files handling and sending summmary to recruoter in csv
worko-cand-profil-parser


17/03/2026

worko-jd-resume-matching

1) Candidate CV Submission via Form / 2) candidate asking for refferal

### 1. CTC (Compensation) Compatibility Check
### 2. Years of Experience (YOE) Compatibility Check
### 3. Department Alignment Check
## 4. 4 step score calculation
## 5. feedback based on score cap to 60 if mandatory req not met


3) Candidate Job Application
#when candidates applys a job, it will get backend and uptade results in dybamo db
### 1. feedback analysis
### 2. CTC (Compensation) Compatibility Check
### 3. Years of Experience (YOE) Compatibility Check
### 4. Department Alignment Check
## 5. 4 step score calculation
## 6. feedback based on score cap to 60 if mandatory req not met



worko-sourcetype-jd-resume-matching
#find matching score button in admin/ corporate

worko-bulk-jd-resume-matching
#bulk screening of candidate in admin/ corporate

worko-agency-bulk-jd-resume-jd-resume-matching
#bulk screening of candidate in Agency




### 1. CTC (Compensation) Compatibility Check

**Logic**: Evaluates if candidate's current CTC aligns with job's salary range

**Criteria**:
- **Expected CTC Calculation**: `ECTC = Current CTC × 1.25`
- **Rejection Thresholds**:
  - If `ECTC > JD_Max_CTC × 1.2` AND `JD_Max_CTC × 1.2 > 10 LPA` → **Overqualified**
  - If `ECTC > JD_Max_CTC × 1.3` AND `JD_Max_CTC × 1.2 < 10 LPA` → **Overqualified**

### 2. Years of Experience (YOE) Compatibility Check

**Logic**: Validates candidate experience against job requirements

**Criteria for Underqualified**:
- If `JD_Min_Exp × 0.3 ≥ 3 years` AND `JD_Min_Exp - CV_Exp > 3 years` → **Underqualified**
- If `CV_Exp < JD_Min_Exp × 0.7` → **Underqualified**

**Criteria for Overqualified**:
- If `JD_Max_Exp ≤ 4 years` AND `CV_Exp > JD_Max_Exp × 1.6` → **Overqualified**
- If `JD_Max_Exp × 0.4 > 4 years` AND `CV_Exp - JD_Max_Exp > 4 years` → **Overqualified**
- If `CV_Exp > JD_Max_Exp × 1.4` AND `JD_Max_Exp > 4 years` → **Overqualified**

### 3. Department Alignment Check

**Logic**: Ensures candidate's domain matches job department

**Process**:
1. Analyzes job description and department
2. Compares with candidate's preferred departments
3. Evaluates domain alignment (Technical vs Non-Technical)

## 4. Multi-Step Scoring Algorithm

### Experience Level Classification
Jobs are classified into experience levels:
- **Fresher**: < 1 year
- **Junior**: 1-5 years  
- **Senior**: 5-12 years
- **Superior**: > 12 years

## 5. 4 step score calculation
## 6. feedback based on score


############################     02-06-2026     ##################################
deployment for azure to gcp migration + secrect manager caching (only code changes + lambda template changes) no new lambda only added a new common layer for all (shared-core-layer)
check below things if needed after you deploy all lambdas.

***common changes for all.***

1) add SharedCoreLayer in template.yaml if its not there( need to add twice in (1) layer name, (2) layer details.)
2) every lambda should contain these two library in lambda_name/layer/rquirements.txt
google-auth==2.36.0
google-genai==1.0.0

***these are all lambdas which needs to be deployed with specific changes***

1) worko-job-description parser
2) worko-resume-parser
** remove these env variables from template.yaml
          AZURE_OPENAI_ENDPOINT,AZURE_OPENAI_DEPLOYMENT
          AZURE_OPENAI_API_KEY,AZURE_OPENAI_API_VERSION

3) worko-resume-sign-up-skills-parser
** add new env variable as ENVIRONMENT = "dev" (in template.yaml )

** remove these env variables from template.yaml
          AZURE_OPENAI_ENDPOINT,AZURE_OPENAI_DEPLOYMENT
          AZURE_OPENAI_API_KEY,AZURE_OPENAI_API_VERSION

4) worko-cand-profile-parser
5) worko-candidate-search-prompt-parser
6) worko-referrel-source-cand-profile-parser
7) worko-jd-resume-matching
** remove these env variables from template.yaml
          AZURE_OPENAI_ENDPOINT,AZURE_OPENAI_DEPLOYMENT
          AZURE_OPENAI_API_KEY,AZURE_OPENAI_API_VERSION

8) worko-bulk-jd-resume-matchig
9) worko-sourcetype-jd-resume-matching
** remove these env variables from template.yaml
          AZURE_OPENAI_ENDPOINT,AZURE_OPENAI_DEPLOYMENT
          AZURE_OPENAI_API_KEY,AZURE_OPENAI_API_VERSION

10) worko-agency-bulk-jd-resume-matching


***commands example*** 
(checkout  ,'codecatalyst/workflows/lambda_name' for exact commands)


## Lambda 2: worko-resume-parser-prod (EXISTING LAMBDA - REPLACEMENT)

### Navigate to Directory
```bash
cd src/worko-resume-parser
```

### Build
```bash
mac -->> sam build / windows -->> sam build --use-container 
```

### Deploy
```bash
sam deploy \
  --stack-name worko-resume-parser-dev-stack \ ##your lambda name with suffix stack
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=prod\ ## put prod here
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \  ## put one s3 bucket name
  --no-confirm-changeset
```




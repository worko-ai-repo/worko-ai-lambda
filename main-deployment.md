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




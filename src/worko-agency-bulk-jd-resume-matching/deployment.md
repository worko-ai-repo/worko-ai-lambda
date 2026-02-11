this is a new lambda function used for agency bulk cv matching with a job description.
will not replace any lambda, completely new flow.

there are 3 dependencies to make sure before and after deploying this lambda to make it run in prod

1) make sure "worko-agency-bulk-cvs-"+{env} s3 bucket is created

2) need to create a secret variable in secret manager whose name will be "AZURE-openai-secret-"+{env} and "GCP-firestore-secret-"+{env}, add them as key/value. its there in dev too you can copy from there also

AZURE-openai-secret-prod
{"AZURE_OPENAI_ENDPOINT":"https://aif-wrk-dev-sin-01.openai.azure.com","AZURE_OPENAI_DEPLOYMENT":"gpt-4o","AZURE_OPENAI_API_KEY":"REDACTED","AZURE_OPENAI_API_VERSION":"2025-01-01-preview"}


GCP-firestore-secret-prod
{
  "type": "service_account",
  "project_id": "worko-dev",
  "private_key_id": "REDACTED",
  "private_key": "REDACTED\n",
  "client_email": "worko-gcp-firestore@worko-dev.iam.gserviceaccount.com",
  "client_id": "REDACTED",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/worko-gcp-firestore%40worko-dev.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}



3) once lambda is deployed add the s3 triger manually in lambda function

#add trigger from s3
Source: S3
Bucket: "worko-agency-bulk-cvs-"+{env}
Request type: put
Prefix: agencies/
Suffix: .pdf
Events: All object create events


commands to run

## Quick Deploy
```bash
chmod +x deploy.sh
./deploy.sh dev   # for dev environment
./deploy.sh prod  # for prod environment
```

## Manual Deploy
```bash
# step 1: Set AWS Profile
export AWS_PROFILE=worko-d  # for dev
export AWS_PROFILE=worko-p  # for prod

# step 2: Build
sam build

# step 3: Deploy to prod
sam deploy \
  --stack-name worko-agency-bulk-jd-resume-matching-stack-prod \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=prod \
  --s3-bucket worko-aws-sam-cli-deployment-prod \
  --no-confirm-changeset

# step 3: Deploy to dev
sam deploy \
  --stack-name worko-agency-bulk-jd-resume-matching-stack-dev \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=dev \
  --s3-bucket worko-aws-sam-cli-deployment-dev \
  --no-confirm-changeset
```


































#################################### functionality it doing ##########################


1. Create lambda function for agency
   1. worko-agency-bulk-jd-resume-matching-dev
   2. worko-agency-bulk-jd-resume-matching-prod
2. S3 Trigger for `worko-agency-bulk-jd-resume-matching-dev` lambda
   ```sh
      `agencies/{agencyUserId}/bulk-cvs/{agencyBulkJdId}`
      # Example destination
      # s3://worko-app-dev/agencies/712EEWMW5HE3NE9K8DGRXXTR53/bulk-cvs/01KD2W640HJS9PZNJMHNH6YE6K/01KD2WDTS7RZKEJ6QFK87MDC0K.pdf
   ```
3. Update below things in `agencyBulkJdResumes` Firestore Collection: 
```ts
{
  updatedAt: string;
  cvExtractedParsed: {
    candidateName: string; //  "Rohith Appala";
    candidateEmail: string; // "rohithappala777@gmail.com";
    candidatePhoneNumber: string; // "+919666308100";
    candidateNumber: number; // 9666308100;
    candidatePhoneCountryCode: number; // 91;
    candidateCurrentCompany?: string; // "Worko.ai-India";
    candidateCurrentDesignation?: string; // "NodeJs Backend Developer";
    candidateExperience?: number; // 3;
    candidateTotalYOE?: number; // 3;
    candidateRelevantYOE?: number; // 4;
    candidateCurrentCTC?: number; // 10;
    candidateExpectedCTC?: number; // 9;
    candidateNoticePeriod?: number; // 60;
    candidateLocation?: string; // "Hyderabad, Telangana";
    candidateReadyToRelocate?: boolean; // false;
    isNoticePeriodNegotiable?: boolean; // false;

    coreSkills?: {
      skillName: string;
      years: number;
      timestamps?: {
        createdAt: string;
        updatedAt: string;
      };
    }[];
    technicalSkills?: {
      skillName: string;
      years: number;
      timestamps?: {
        createdAt: string;
        updatedAt: string;
      };
    }[];
    userPreferredDepartments?: string[];
    userPreferredIndustries?: string[];
    userPreferredlocations?: string[];
    userPreferredRoles?: string[];
	},
  processingStatus: "COMPLETED" | "FAILED" 
  cvExtract?: string;
  matchingScore?: number;
  jdMatchErrorCode?: number;
  jdMatchErrorDesc?: string;
  scoreDetails?: string;
  scoreFetchedDate?: string;
  rejectionFeedbackBySystem?: string;
}
```
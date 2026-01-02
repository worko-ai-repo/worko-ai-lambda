this is a new lambda function used for agency bulk cv matching with a job description.
will not replace any lambda, completely new flow.

there are 3 dependencies to make sure before and after deploying this lambda to make it run in prod

1) make sure "worko-agency-bulk-cvs-"+{env} s3 bucket is created

2) need to create a secret variable in secret manager whose name will be "AZURE-openai-secret-"+{env}

3) once lambda is deployed add the s3 triger manually in lambda function

#add trigger from s3
Source: S3
Bucket: "worko-agency-bulk-cvs-"+{env}
Request type: put
Prefix: agencies/
Suffix: .pdf
Events: All object create events


































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
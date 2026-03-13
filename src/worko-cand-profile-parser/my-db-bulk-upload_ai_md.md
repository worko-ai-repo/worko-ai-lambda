
1. Lambda name: `worko-cand-profile-parser-dev`
   1. S3 Triggers:
      1. `worko-corporate-cand-profile-dev`
         Full s3 path: `worko-corporate-cand-profile-dev/companies/{companyId}/bulk-cvs/01JJE6VEV1JRQ424RMJNXYVEN3.pdf`
      2. `worko-admin-cand-profile-dev`
         Full s3 path: `worko-admin-cand-profile-dev/bulk-cvs/01JJE6VEV1JRQ424RMJNXYVEN3.pdf`

2. Logic
   1. Parse the `cv`
   2. Duplicacy checks
      1. If `companyId` exists in `aws s3 trigger` details
         1. Check duplicacy in `corporateCandidateProfiles` collection in `worko-corp-db-dev` database, refer duplicacy logic:
            ```ts
            db.collection("corporateCandidateProfiles")
            .where("companyId", "==", companyId)
            .where(
               Filter.or(
                  Filter.where("candidateEmail", "==", "shaukat@gmail.com"),
                  Filter.and(
                     Filter.where(
                        "phoneNumberDetails.number",
                        "==",
                        9666308100
                     ),
                     Filter.where(
                        "phoneNumberDetails.countryCode",
                        "==",
                        91
                     )
                  )
               )
            )
            .get()
            ```
            1. If not duplicate:
               1. `worko-cand-profile-parser-dev` will trigger `sqs` event which is present in `worko-corp-app` repository by sending `parsing` response:
                  1. SQS Event name: `CORPORATE_CAND_PROFILE_BULK_UPLOAD`
                  2. body: 
                     ```json
					 {
                       "event": "CORPORATE_CAND_PROFILE_BULK_UPLOAD",
                        "candidateCvAwsS3FileName":"",
                        "companyId": "...",
                        "cvExtractedParsed": {
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
                        }
                     }
                     ```
            2. if duplicate then do not trigger `sqs`
      
      2. If no `companyId` present in `aws s3` trigger details
         1. Check duplicacy in `centralCandidateProfiles` collection in `worko-corp-db-dev` database, refer duplicacy logic:
            ```ts
            db.collection("centralCandidateProfiles")
            .where(
               Filter.or(
                  Filter.where("candidateEmail", "==", "shaukat@gmail.com"),
                  Filter.and(
                     Filter.where(
                        "phoneNumberDetails.number",
                        "==",
                        9666308100
                     ),
                     Filter.where(
                        "phoneNumberDetails.countryCode",
                        "==",
                        91
                     )
                  )
               )
            )
            .get()
            ```
            1. If not duplicate:
               1. `worko-cand-profile-parser-dev` will trigger `sqs` event which is present in `worko-corp-app` repository by sending `parsing` response:
                  1. SQS Event name: `ADMIN_CAND_PROFILE_BULK_UPLOAD`
                  2. body: 
                     ```json
                     {
                         "event":"ADMIN_CAND_PROFILE_BULK_UPLOAD",
                         "candidateCvAwsS3FileName":"",
                        // DO NOT SEND "companyId"
                        "cvExtractedParsed": {
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
                        }
                     }
                     ```
            2. if duplicate then do not trigger `sqs`
#########################   addded reuiremnets #####################
schema
parant                                        ---> bulkSourceTypeResumes--> wil be present need to quiry
bulkSourceTypeResumes-->DETXFCGVJHBNKXTFCGHBJN- child 
bulkSourceTypeParseResumes--> need update docs inside this which conatins values

1. s3 metadata:
   ```sh
   {
      "bulkSourceTypeResumeId": "DETXFCGVJHBNKXTFCGHBJN",
      "corporateUserEmail": "....", 
      "workoAdminUserEmail": "...."
   }
   ```
2. in first ai lambda `worko-cand-profile-parser-dev` 
   query document by "id" from `bulkSourceTypeResumes` collection
3. 
   <!-- 1. first check `totalResumesProcessed` undefined or `0` that means it first lambda
   2. parse cv and do existing stuff -->
   3. use `FieldValue.increment(1)` for incrementing `totalResumesProcessed`(always) in `bulkSourceTypeResumes` collection and create document in `bulkSourceTypeParseResumes` collection with appropriate status
   .
   .
   .
   4. for 1000th lambda check count of `totalResumesSucceeded + totalResumesFailed + totalResumesDuplicate` is `999` with `totalResumesUploaded-1` then
      process cv and do existing stuff
   5. update `processingStatus` as "COMPLETED" in  
      and after creating `bulkSourceTypeParseResumes` collection with appropriate status,
      in this `1000`th lambda retrieve info from `bulkSourceTypeParseResumes` collection with status `DUPLICATE` and keep in `.csv` and send email to `corporateUserEmail` or `workoAdminUserEmail`
      retrieve info from `bulkSourceTypeParseResumes` collection with status `FAILED` and keep in `.csv` and send email to `corporateUserEmail` or `workoAdminUserEmail`


```ts
// for increment
import { FieldValue } from "@google-cloud/firestore";
const totalResumesSucceeded = FieldValue.increment(1)
```



# Pending Implementations in Bulk cvs feature
1. how to send `counts` of `failed`, `success`, `duplicate` to `react ui` 


<!-- get dublicate logic -->



12/03/26
# For large file names
1. in `bulkSourceTypeResumes` gcp firestore collection `totalLargeResumesUploaded` will be stored if there are large files
2. in `bulkSourceTypeParseResumes` gcp firestore collection `userResumeFileName` will be stored when status is `LARGE_RESUME_FILE`

# For invalid file names
1. in `bulkSourceTypeResumes` gcp firestore collection `totalInvalidFileNamesUploaded` will be stored if there are invalid files
2. in `bulkSourceTypeParseResumes` gcp firestore collection `userResumeFileName` will be stored when status is `INVALID_FILE_NAME`

13/03/26
```sh
In `Metadata` you will recieve `skipParsing: "true"` or "false"
```

1. If cvAwsS3ResourceType="CORP_CAND_BULK_CV_UPLOAD" and "cvAwsS3FilePath": "companies/01JWAQF1G96E0SE9XHXSFGHNWW/bulk-cvs"
   1. `worko-corporate-cand-profile-dev` aws s3 bucket will trigger `worko-cand-profile-parser-dev` aws lambda
2. If cvAwsS3ResourceType="ADMIN_CAND_BULK_CV_UPLOAD" and "cvAwsS3FilePath": "bulk-cvs"
   1. `worko-admin-cand-profile-dev` aws s3 bucket will trigger `worko-cand-profile-parser-dev` aws lambda
3. If  If cvAwsS3ResourceType="BULK_CVS" and "cvAwsS3FilePath": "companies/01K47MSBKS79ACY0BM6Z8VS3F5/bulk-cvs/01KJW4QRC51YK2HRMPDSCPR353"
   1. `worko-corporate-dev` aws s3 bucket will trigger `worko-bulk-jd-resume-matching-dev` 






Date : 2024-06-19
create AZURE-openai-secret-multimodel-{env} in secrect varaibles which is given below and present in dev

{"AZURE_OPENAI_API_KEY":"REDACTED","AZURE_OPENAI_ENDPOINT":"https://aif-wrk-dev-sin-01.openai.azure.com","AZURE_OPENAI_DEPLOYMENT_gpt-4.1-mini":"gpt-4.1-mini","AZURE_OPENAI_API_VERSION_gpt-4.1-mini":"2024-12-01-preview","AZURE_OPENAI_DEPLOYMENT_gpt-4o":"gpt-4o","AZURE_OPENAI_API_VERSION_gpt-4o":"2025-01-01-preview"}

* deployment is of 5 lambda function with no dependancies only code and one secrect varable need to be deploy.
 * each folder of lambda contains a deploment.md file which have the SAM commands to deploy

1) worko-agency-bulk-jd-resume-matching
2) worko-bulk-jd-resume-matching
3) worko-cand-profile-parser
4) worko-referral-source-cand-profile-parser
5) worko-resume-parser


###########  deploment commands for this lambda (worko-resume-parser)  ###########

### Build
1) Navigate to lambda directory and build:
```bash
cd src/worko-resume-parser
sam build  # or sam build --use-container
```

2) Deploy using commands below:

### Deploy to Prod
```bash
sam deploy \
  --stack-name worko-resume-parser-prod-stack \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=prod \
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \
  --no-confirm-changeset
```

### Deploy to Dev
```bash
sam deploy \
  --stack-name worko-resume-parser-dev-stack \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=dev \
  --s3-bucket aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx \
  --no-confirm-changeset
```
09/03/2026
added this line in the prompt
 6) location must be only city name followed by state name examples. Mumbai, Maharahstra,  Bengaluru Karnataka"
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
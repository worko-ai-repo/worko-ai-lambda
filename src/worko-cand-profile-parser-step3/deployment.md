# Worko Candidate Profile Parser Step3 Deployment

## Function Details
- **Name**: worko-cand-profile-parser-step3-{env}
- **Runtime**: Python 3.11
- **Memory**: 512 MB
- **Timeout**: 300 seconds

## Deploy Commands

```bash
cd src/worko-cand-profile-parser-step3
sam build --use-container
sam deploy --stack-name worko-cand-profile-parser-step3-dev-stack --region ap-south-1 --capabilities CAPABILITY_IAM --parameter-overrides Environment=dev
```

## Test Invoke

```bash
aws lambda invoke \
  --function-name worko-cand-profile-parser-step3-dev \
  --region ap-south-1 \
  --payload file://test-event.json \
  response.json
```

## View Logs

```bash
aws logs tail /aws/lambda/worko-cand-profile-parser-step3-dev --follow --region ap-south-1
```

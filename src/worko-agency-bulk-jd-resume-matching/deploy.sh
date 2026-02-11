#!/bin/bash

ENV=$1

if [ -z "$ENV" ]; then
  echo "Usage: ./deploy.sh <env>"
  echo "Example: ./deploy.sh dev"
  exit 1
fi

if [ "$ENV" != "dev" ] && [ "$ENV" != "prod" ]; then
  echo "Error: Environment must be 'dev' or 'prod'"
  exit 1
fi

if [ "$ENV" == "dev" ]; then
  export AWS_PROFILE=worko-d
else
  export AWS_PROFILE=worko-p
fi

echo "Building SAM application..."
sam build

echo "Deploying to $ENV environment using profile $AWS_PROFILE..."
sam deploy \
  --stack-name worko-agency-bulk-jd-resume-matching-stack-${ENV} \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=${ENV} \
  --s3-bucket worko-aws-sam-cli-deployment-${ENV} \
  --no-confirm-changeset

echo "Deployment complete!"

#!/bin/bash

# Worko Candidate Search Prompt Parser - Deployment Script
# Usage: ./deploy.sh [dev|prod]

set -e

ENVIRONMENT=${1:-dev}
STACK_NAME="worko-candidate-search-prompt-parser-${ENVIRONMENT}-stack"
REGION="ap-south-1"
S3_BUCKET="aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx"

echo "=========================================="
echo "Deploying Candidate Search Prompt Parser"
echo "Environment: ${ENVIRONMENT}"
echo "Stack: ${STACK_NAME}"
echo "=========================================="

# Build
echo "Building SAM application..."
sam build --use-container

# Deploy
echo "Deploying to AWS..."
sam deploy \
  --stack-name ${STACK_NAME} \
  --region ${REGION} \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=${ENVIRONMENT} \
  --s3-bucket ${S3_BUCKET} \
  --no-confirm-changeset

echo "=========================================="
echo "Deployment completed successfully!"
echo "Function: worko-candidate-search-prompt-parser-${ENVIRONMENT}"
echo "=========================================="

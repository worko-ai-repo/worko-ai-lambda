#!/bin/bash

ENVIRONMENT="dev"
REGION="ap-south-1"
STACK_NAME="state-machine-retry-sqs-${ENVIRONMENT}"

echo "Deploying SQS Queue: state-machine-retry-${ENVIRONMENT}"

aws cloudformation deploy \
  --template-file sqs-queue.yaml \
  --stack-name $STACK_NAME \
  --parameter-overrides Environment=$ENVIRONMENT \
  --region $REGION \
  --capabilities CAPABILITY_IAM

echo "Getting Queue URL..."
QUEUE_URL=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`QueueUrl`].OutputValue' \
  --output text)

echo "Queue URL: $QUEUE_URL"

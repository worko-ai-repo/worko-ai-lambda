# Worko AI Lambda - Multi-Function Repository

## 📖 Overview

This repository contains multiple independent AWS Lambda functions that deploy selectively based on code changes. Each Lambda function has its own dependencies, permissions, and deployment configuration.

---

## 🎯 Repository Structure

```
worko-ai-lambda/
├── src/
│   └── worko-sourcetype-jd-resume-matching-dev/
│       ├── lambda_function.py
│       ├── requirements.txt
│       └── template.yaml
│
└── .codecatalyst/workflows/auto-deploy.yaml
```

---

## 🚀 How It Works

### Selective Deployment
- **Change Detection**: CodeCatalyst workflow detects which Lambda function was modified
- **Independent Build**: Only the changed Lambda function is built and deployed
- **Isolated Resources**: Each Lambda has its own IAM role, layer, and CloudFormation stack

### Lambda Functions

1. **worko-sourcetype-jd-resume-matching-dev**
   - Stack: `worko-sourcetype-jd-resume-matching-dev-stack`
   - Function: `worko-sourcetype-jd-resume-matching-dev`

2. **resume-parser**
   - Stack: `resume-parser-dev-stack`
   - Function: `resume-parser`
   - **Advanced Rollback**: Automatic backup and restore on deployment failure

*Additional Lambda functions can be added later with the same structure.*

---

## 🔧 Making Changes

### To modify a specific Lambda:

1. **Edit the Lambda code**
   ```bash
   # Example: Edit the sourcetype matching function
   code src/worko-sourcetype-jd-resume-matching-dev/lambda_function.py
   ```

2. **Update dependencies if needed**
   ```bash
   # Edit requirements.txt for that specific Lambda
   code src/worko-sourcetype-jd-resume-matching-dev/requirements.txt
   ```

3. **Commit and push**
   ```bash
   git add src/worko-sourcetype-jd-resume-matching-dev/
   git commit -m "Update sourcetype matching logic"
   git push origin main
   ```

4. **Automatic deployment**
   - Only the `worko-sourcetype-jd-resume-matching-dev` Lambda will be deployed
   - Other Lambda functions remain unchanged

---

## 📋 Quick Commands

### Test a specific Lambda locally
```bash
cd src/worko-sourcetype-jd-resume-matching-dev
sam build
sam local invoke LambdaFunction --event test-event.json
```

### Deploy a specific Lambda manually
```bash
cd src/worko-sourcetype-jd-resume-matching-dev
sam build
sam deploy --stack-name worko-sourcetype-jd-resume-matching-dev-stack --region ap-south-1 --capabilities CAPABILITY_IAM
```

### Invoke deployed Lambda
```bash
aws lambda invoke \
  --function-name worko-sourcetype-jd-resume-matching-dev \
  --region ap-south-1 \
  --payload '{"test":"data"}' \
  response.json
```

---

## 🔄 Advanced Deployment Features

### Resume Parser - Backup & Rollback System
The `resume-parser` Lambda includes advanced deployment safety:

1. **Pre-deployment Backup**
   - Downloads current function code and configuration
   - Stores backup locally during deployment

2. **Clean Deployment**
   - Deletes existing function to avoid conflicts
   - Deploys fresh version with new code

3. **Automatic Rollback**
   - If deployment fails, automatically restores previous version
   - Recreates Lambda with original code, configuration, and environment variables
   - Ensures zero-downtime recovery

### Rollback Process
```bash
# Automatic rollback includes:
- Function code restoration
- IAM role restoration  
- Runtime and handler restoration
- Memory and timeout restoration
- Environment variables restoration
```

---

## ✅ Benefits

- **Independent Deployments**: Change one Lambda without affecting others
- **Faster CI/CD**: Only modified functions are built and deployed
- **Isolated Resources**: Each Lambda has its own permissions and dependencies
- **Scalable Architecture**: Easy to add new Lambda functions
- **Cost Efficient**: No unnecessary deployments
- **Deployment Safety**: Automatic backup and rollback for critical functions

---

**Happy Coding! 🚀**
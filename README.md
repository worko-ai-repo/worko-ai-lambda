# Worko AI Lambda - Multi-Function Repository

## 📖 Overview



This repository contains multiple independent AWS Lambda functions that deploy selectively based on code changes. Each Lambda function has its own dependencies, permissions, and deployment configuration with automatic CI/CD via CodeCatalyst.

---

## 🎯 Repository Structure

```
worko-ai-lambda/
├── .codecatalyst/workflows/
│   ├── worko-sourcetype-jd-resume-matching.yaml
│   └── worko-resume-parser.yaml
├── src/
│   ├── worko-sourcetype-jd-resume-matching/
│   │   ├── layer/requirements.txt
│   │   ├── lambda_function.py
│   │   └── template.yaml
│   ├── worko-resume-parser/
│   │   ├── layer/requirements.txt
│   │   ├── lambda_function.py
│   │   └── template.yaml
│   ├── worko-job-description-parser/
│   └── worko-secret-manager/
├── env-config.json
├── ENVIRONMENT_SETUP.md
└── test_lambda.py
```

---

## 🚀 How It Works

### Environment-Based Deployment
- **Dynamic Environment**: Uses `env-config.json` to control deployment environment (dev/staging/prod)
- **Selective Deployment**: Only modified Lambda functions are built and deployed
- **Independent Resources**: Each Lambda has its own IAM role, layer, and CloudFormation stack

### Lambda Functions

1. **worko-sourcetype-jd-resume-matching** (NEW)
   - Stack: `worko-sourcetype-jd-resume-matching-{env}-stack`
   - Function: `worko-sourcetype-jd-resume-matching-{env}`
   - Purpose: AI-powered job description and resume matching

2. **worko-resume-parser** (REPLACEMENT)
   - Stack: `worko-resume-parser-{env}-stack`
   - Function: `worko-resume-parser-{env}`
   - Purpose: Resume parsing with advanced rollback system

---

## 🔧 Environment Configuration

### Quick Environment Switch
Edit **ONE FILE ONLY** to change environments:

```json
// env-config.json
{
  "ENVIRONMENT": "prod",  // Change this line
  "AWS_REGION": "ap-south-1",
  "S3_BUCKET_MANAGED": "your-sam-bucket"
}
```

### What Changes Automatically
- Lambda Functions: `worko-*-{ENV}`
- CloudFormation Stacks: `worko-*-{ENV}-stack`
- Lambda Layers: `worko-*-deps-{ENV}`
- S3 Buckets: `worko-app-{ENV}`

---

## 📚 Deployment Journey & Lessons Learned

### Key Problems Solved

1. **Lambda Function Name Conflicts**
   - **Issue**: Same function name across different stacks
   - **Solution**: Smart cleanup that finds owning stack and deletes properly

2. **Failed Stack Management**
   - **Issue**: Stacks in ROLLBACK_FAILED state
   - **Solution**: Auto-detection and cleanup of broken stacks

3. **Environment Variable Conflicts**
   - **Issue**: Reserved AWS environment variables
   - **Solution**: Dynamic parameter passing via `--parameter-overrides`

4. **Complex Dependencies**
   - **Issue**: C++ compilation requirements
   - **Solution**: `--use-container` flag for consistent builds

5. **Mixed Resource Management**
   - **Issue**: Manual vs CloudFormation-managed resources
   - **Solution**: Intelligent detection and appropriate cleanup

---

## 🔧 Making Changes

### To modify a specific Lambda:

1. **Edit the Lambda code**
   ```bash
   # Example: Edit the sourcetype matching function
   code src/worko-sourcetype-jd-resume-matching/lambda_function.py
   ```

2. **Update dependencies if needed**
   ```bash
   # Edit layer requirements
   code src/worko-sourcetype-jd-resume-matching/layer/requirements.txt
   ```

3. **Change environment (optional)**
   ```bash
   # Edit env-config.json to change deployment target
   code env-config.json
   ```

4. **Commit and push**
   ```bash
   git add .
   git commit -m "Update sourcetype matching logic"
   git push origin main
   ```

5. **Automatic deployment**
   - CodeCatalyst detects changes
   - Only modified Lambda is deployed
   - Other functions remain unchanged

---

## 📋 Quick Commands

### Test locally
```bash
python test_lambda.py
```

### Deploy manually (if needed)
```bash
cd src/worko-sourcetype-jd-resume-matching
sam build --use-container
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

### View logs
```bash
aws logs tail /aws/lambda/worko-sourcetype-jd-resume-matching-dev --follow --region ap-south-1
```

---

## 🔄 Advanced Deployment Features

### Smart Cleanup System
Both Lambda functions include intelligent cleanup:

1. **Resource Conflict Detection**
   - Checks for existing Lambda functions
   - Identifies owning CloudFormation stack
   - Handles manual vs stack-managed resources

2. **Broken Stack Recovery**
   - Detects ROLLBACK_FAILED states
   - Auto-deletes corrupted stacks
   - Ensures clean deployment environment

3. **Update vs Create Logic**
   - Determines if Lambda exists
   - Uses appropriate deployment strategy
   - Handles both scenarios gracefully

### Force Cleanup (Manual Override)
Commented cleanup sections available for:
- Corrupted CloudFormation stacks
- Manually deployed Lambda functions
- Complete clean slate deployments

---

## 🔧 Troubleshooting

### Deployment Fails
- Check CodeCatalyst workflow logs
- Verify env-config.json values
- Ensure S3 bucket exists and is accessible

### Lambda Doesn't Work
- Check CloudWatch Logs for runtime errors
- Verify environment variables in template.yaml
- Test locally with test_lambda.py

### Resource Conflicts
- Uncomment force cleanup section in workflow
- Manually delete conflicting resources
- Ensure proper IAM permissions

---

## ✅ Benefits

- **Environment Isolation**: Complete separation between dev/staging/prod
- **Independent Deployments**: Change one Lambda without affecting others
- **Intelligent Cleanup**: Automatic handling of resource conflicts
- **Scalable Architecture**: Easy to add new Lambda functions
- **Cost Efficient**: Only deploy what changed
- **Deployment Safety**: Automatic backup and rollback systems
- **Container Builds**: Consistent dependency compilation

---

## 📞 Support

For issues:
1. Check CodeCatalyst workflow logs
2. Review CloudWatch Logs for Lambda errors
3. Verify AWS credentials and permissions
4. Check ENVIRONMENT_SETUP.md for detailed configuration

---

**Happy Coding! 🚀**
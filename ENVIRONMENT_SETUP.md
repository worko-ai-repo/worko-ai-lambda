# Environment Configuration Guide

## 🎯 Quick Environment Switch

To change from **dev** to **prod** (or any environment), edit **ONE FILE ONLY**:

```bash
# Edit this file:
env-config.json
```

Change the `ENVIRONMENT` value:
```json
{
  "ENVIRONMENT": "prod",  // Change this line only
  "AWS_REGION": "ap-south-1",
  "S3_BUCKET_MANAGED": "aws-sam-cli-managed-default-samclisourcebucket-mpwvaft0yfqx"
}
```

## 📋 What Changes Automatically

When you change the environment in `env-config.json`, these resources will automatically use the new suffix:

### Lambda Functions
- `worko-sourcetype-jd-resume-matching-{ENV}`
- `worko-job-description-parser-{ENV}`
- `worko-resume-parser-{ENV}`
- `worko-secret-manager-{ENV}`

### CloudFormation Stacks
- `worko-sourcetype-jd-resume-matching-{ENV}-stack`
- `worko-job-description-parser-{ENV}-stack`
- `worko-resume-parser-{ENV}-stack`
- `worko-secret-manager-{ENV}-stack`

### Lambda Layers
- `worko-sourcetype-jd-resume-matching-deps-{ENV}`
- `worko-job-description-parser-deps-{ENV}`
- `worko-resume-parser-deps-{ENV}`
- `worko-secret-manager-deps-{ENV}`

### S3 Buckets
- `worko-app-{ENV}`

### GCP Project ID
- `worko-{ENV}`

## 🔧 Supported Environments

- `dev` - Development environment
- `staging` - Staging environment  
- `prod` - Production environment

## ⚠️ Important Notes

1. **Only edit `env-config.json`** - Do not modify individual workflow files
2. **Commit the change** - Make sure to commit `env-config.json` changes to trigger deployments
3. **Resource isolation** - Each environment creates completely separate AWS resources
4. **No conflicts** - Dev and prod resources cannot interfere with each other

## 🚀 Deployment Process

1. Edit `env-config.json`
2. Commit and push changes
3. CodeCatalyst workflows automatically detect the environment
4. Resources are created/updated with the correct environment suffix

**That's it! One file change deploys to any environment.**
# AWS Multi-Account Inventory Lambda

Docker-based Lambda function that fetches inventory from multiple AWS accounts, generates Excel reports, and stores them in S3.

## Architecture

```
SSM Parameter Store          Lambda (Container)                 S3 Bucket
┌─────────────────┐    ┌──────────────────────┐    ┌─────────────────────────┐
│ /fetch_inv/      │───>│                      │───>│ bucket/                 │
│   dev-access-key │    │  For each env:       │    │   2026/                 │
│   dev-secret-key │    │   1. Get creds (SSM) │    │     03/                 │
│   uat-access-key │    │   2. Fetch inventory │    │       AcctName_dev_...  │
│   uat-secret-key │    │   3. Generate Excel  │    │       AcctName_uat_...  │
│   prod-access-key│    │   4. Upload to S3    │    │       AcctName_prod_... │
│   prod-secret-key│    │                      │    │                         │
└─────────────────┘    └──────────────────────┘    └─────────────────────────┘
```

## Prerequisites (Create Manually)

1. **ECR Repository** — to store the Docker image
2. **Lambda Function** — container image type, with these settings:
   - Timeout: 900 seconds (15 min)
   - Memory: 512 MB+
   - Environment variables:

     | Variable     | Example             | Description                       |
     |--------------|---------------------|-----------------------------------|
     | S3_BUCKET    | my-inventory-bucket | S3 bucket for reports             |

3. **S3 Bucket** — for storing Excel reports
4. **SSM Parameters** (SecureString) — credentials for each target account:

   ```bash
   # Dev account
   aws ssm put-parameter --name "/fetch_inv/dev-access-key"  --value "AKIA..." --type SecureString
   aws ssm put-parameter --name "/fetch_inv/dev-secret-key"  --value "wJal..." --type SecureString

   # UAT account
   aws ssm put-parameter --name "/fetch_inv/uat-access-key"  --value "AKIA..." --type SecureString
   aws ssm put-parameter --name "/fetch_inv/uat-secret-key"  --value "wJal..." --type SecureString

   # Prod account
   aws ssm put-parameter --name "/fetch_inv/prod-access-key" --value "AKIA..." --type SecureString
   aws ssm put-parameter --name "/fetch_inv/prod-secret-key" --value "wJal..." --type SecureString
   ```

   The full SSM paths are defined in the `ACCOUNTS` dict at the top of `lambda_function.py`. To add a new account, just add a new entry there with its SSM paths:

   ```python
   ACCOUNTS = {
       'dev': {
           'access_key_ssm': '/fetch_inv/dev-access-key',
           'secret_key_ssm': '/fetch_inv/dev-secret-key',
       },
       'uat': {
           'access_key_ssm': '/fetch_inv/uat-access-key',
           'secret_key_ssm': '/fetch_inv/uat-secret-key',
       },
       'prod': {
           'access_key_ssm': '/fetch_inv/prod-access-key',
           'secret_key_ssm': '/fetch_inv/prod-secret-key',
       },
       # Add new accounts here
   }
   ```

5. **Lambda IAM Role** — Lambda will create a basic execution role by default (CloudWatch Logs). Add the following as an inline policy to that role for SSM and S3 access:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "SSMReadCredentials",
         "Effect": "Allow",
         "Action": [
           "ssm:GetParameter"
         ],
         "Resource": "arn:aws:ssm:*:*:parameter/fetch_inv/*"
       },
       {
         "Sid": "S3UploadReports",
         "Effect": "Allow",
         "Action": [
           "s3:PutObject"
         ],
         "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/*"
       }
     ]
   }
   ```

   Replace `YOUR_BUCKET_NAME` with your actual S3 bucket name.

   Target account IAM users (whose keys are stored in SSM) need **ReadOnlyAccess** policy attached.

## Deploy

On a Linux machine with Docker and AWS CLI:

```bash
git clone <repo-url>
cd <repo>
chmod +x deploy.sh
sh deploy.sh 1.0.0
```

The script will:
1. `git fetch --all` and checkout the given tag
2. Show git status and ask for confirmation
3. Login to ECR, build image, push to ECR
4. Update the Lambda function with the new image

ECR repo, Lambda function name, and region are hardcoded in `deploy.sh` — update them once to match your setup.

## Run

```bash
# Invoke with defaults (uses env vars on Lambda)
aws lambda invoke --function-name aws-inventory-collector output.json

# Invoke specific environments only
aws lambda invoke --function-name aws-inventory-collector \
  --payload '{"environments": ["dev"]}' output.json
```

## S3 Output

```
s3://bucket/
  2026/
    03/
      production_dev_20260327_060000.xlsx
      staging_uat_20260327_060000.xlsx
```

Each Excel file has 40+ sheets covering EC2, EBS, ECS, Lambda, S3, RDS, DynamoDB, VPC, IAM, and many more services.

## Optional: Schedule with EventBridge

Run monthly on the 1st at 6 AM UTC:

```bash
aws events put-rule --name monthly-inventory --schedule-expression "cron(0 6 1 * ? *)"
aws events put-targets --rule monthly-inventory \
  --targets "Id"="1","Arn"="arn:aws:lambda:REGION:ACCOUNT:function:aws-inventory-collector"
```

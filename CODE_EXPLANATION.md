# Code Explanation — lambda_function.py

This document explains how `lambda_function.py` works, block by block.

---

## 1. Imports and Configuration (Lines 1–65)

```python
import boto3
import pandas as pd
from datetime import datetime
import logging
import os
import io
```

- `boto3` — AWS SDK for Python, used to call all AWS service APIs
- `pandas` — Used to convert Python dicts into DataFrames and export to Excel
- `openpyxl` — Excel engine used by pandas (imported implicitly)
- `io.BytesIO` — Creates an in-memory file buffer so we can generate Excel without writing to disk (Lambda has limited `/tmp` space)

```python
S3_BUCKET = os.environ.get('S3_BUCKET', 'aws-inventory-collector')
```

The S3 bucket name is read from the Lambda environment variable. Defaults to `aws-inventory-collector` if not set.

```python
ACCOUNTS = {
    'dev': {
        'access_key_ssm': '/fetch_inv/dev-access-key',
        'secret_key_ssm': '/fetch_inv/dev-secret-key',
    },
    'uat': { ... },
    'prod': { ... },
    'oldprod': { ... },
    'network': { ... },
    'sharedservice': { ... },
}
```

Each entry maps an environment name (used in the Lambda payload) to the full SSM Parameter Store paths for that account's AWS access key and secret key. To add a new account, just add a new entry here and create the corresponding SSM parameters.

---

## 2. Helper Functions (Lines 67–120)

### `safe_dt(dt_value)`
Safely converts datetime objects to strings. Handles:
- `None` values → returns `'N/A'`
- Timezone-aware datetimes → strips timezone before formatting
- Already-string values → returns as-is

This prevents Excel serialization errors from timezone-aware datetime objects.

### `get_ssm_parameter(ssm_client, name)`
Reads a single parameter from AWS SSM Parameter Store with decryption enabled (`WithDecryption=True`). This is needed because the credentials are stored as `SecureString` type.

### `get_account_session(ssm_client, account_config)`
Creates a `boto3.Session` for a target AWS account:
1. Reads the access key from SSM using the path in `account_config['access_key_ssm']`
2. Reads the secret key from SSM using the path in `account_config['secret_key_ssm']`
3. Returns a new `boto3.Session` initialized with those credentials

This session is then used by all fetcher functions to make API calls to the target account.

### `get_account_info(session)`
Gets the AWS account ID (via `sts:GetCallerIdentity`) and account alias (via `iam:ListAccountAliases`). The account alias is used in the Excel filename. Falls back to account ID if no alias is set.

### `get_regions(session)`
Calls `ec2.describe_regions()` to get all enabled AWS regions for the account. All fetcher functions iterate over these regions to collect resources globally. Falls back to `['us-east-1']` on error.

---

## 3. Service Fetcher Functions (Lines 122–1050)

There are 40+ fetcher functions, all following the same pattern:

```python
def fetch_<service>(session, regions):
    items = []
    sn = 1                                    # Serial number counter
    for region in regions:                     # Iterate all AWS regions
        try:
            client = session.client('<service>', region_name=region)
            # Call the AWS API (with pagination if needed)
            for resource in api_response:
                items.append({
                    'Sr. No': sn,
                    'Field1': resource['Field1'],
                    ...
                    'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"<Service> error in {region}: {e}")
    return items
```

**Key points:**
- Each function creates a new boto3 client per region using the target account session
- Serial numbers (`sn`) provide row numbering in the Excel output
- Errors in one region don't stop collection in other regions
- Paginators are used for APIs that return paginated results (Lambda, DynamoDB, CloudWatch, etc.)

### Global services (no region loop)
Some services are global and don't iterate regions:
- `fetch_s3(session)` — S3 `list_buckets` returns all buckets globally
- `fetch_route53(session)` — Route53 is a global service
- `fetch_cloudfront(session)` — CloudFront is global
- `fetch_iam(session)` — IAM is global

### Multi-return fetchers
Some functions return multiple datasets:
- `fetch_ecs()` → returns `(clusters, services)` as two separate lists
- `fetch_glue()` → returns `(databases, jobs)`
- `fetch_cognito()` → returns `(user_pools, identity_pools)`
- `fetch_iam()` → returns `(users, roles, policies)`

### Complete list of fetchers

| Function | AWS Service | Regional/Global |
|----------|-------------|-----------------|
| `fetch_ec2` | EC2 Instances | Regional |
| `fetch_ebs` | EBS Volumes | Regional |
| `fetch_ecs` | ECS Clusters & Services | Regional |
| `fetch_ecr` | ECR Repositories | Regional |
| `fetch_lambda` | Lambda Functions | Regional |
| `fetch_s3` | S3 Buckets | Global |
| `fetch_rds` | RDS Instances | Regional |
| `fetch_dynamodb` | DynamoDB Tables | Regional |
| `fetch_elasticache` | ElastiCache Clusters | Regional |
| `fetch_opensearch` | OpenSearch Domains | Regional |
| `fetch_vpcs` | VPCs | Regional |
| `fetch_subnets` | Subnets | Regional |
| `fetch_security_groups` | Security Groups | Regional |
| `fetch_load_balancers` | ALB/NLB | Regional |
| `fetch_elastic_ips` | Elastic IPs | Regional |
| `fetch_nat_gateways` | NAT Gateways | Regional |
| `fetch_igws` | Internet Gateways | Regional |
| `fetch_tgws` | Transit Gateways | Regional |
| `fetch_route53` | Route53 Hosted Zones | Global |
| `fetch_cloudfront` | CloudFront Distributions | Global |
| `fetch_api_gateway` | API Gateway REST APIs | Regional |
| `fetch_cloudformation` | CloudFormation Stacks | Regional |
| `fetch_cloudtrail` | CloudTrail Trails | Regional |
| `fetch_cloudwatch_alarms` | CloudWatch Alarms | Regional |
| `fetch_cloudwatch_logs` | CloudWatch Log Groups | Regional |
| `fetch_eventbridge` | EventBridge Rules | Regional |
| `fetch_kms` | KMS Keys | Regional |
| `fetch_secrets` | Secrets Manager | Regional |
| `fetch_acm` | ACM Certificates | Regional |
| `fetch_waf` | WAF Web ACLs | Regional + Global |
| `fetch_sns` | SNS Topics | Regional |
| `fetch_sqs` | SQS Queues | Regional |
| `fetch_stepfunctions` | Step Functions | Regional |
| `fetch_glue` | Glue Databases & Jobs | Regional |
| `fetch_kinesis` | Kinesis Streams | Regional |
| `fetch_redshift` | Redshift Clusters | Regional |
| `fetch_sagemaker` | SageMaker Notebooks | Regional |
| `fetch_cognito` | Cognito User & Identity Pools | Regional |
| `fetch_config_rules` | AWS Config Rules | Regional |
| `fetch_ssm_params` | SSM Parameters | Regional |
| `fetch_backup` | Backup Plans | Regional |
| `fetch_efs` | EFS File Systems | Regional |
| `fetch_iam` | IAM Users, Roles, Policies | Global |

---

## 4. Inventory Collection Orchestrator (Lines 1052–1120)

### `collect_inventory(session)`

This function orchestrates all the fetcher functions for a single account:

```python
def collect_inventory(session):
    regions = get_regions(session)
    data = {}

    # Compute
    data['EC2_Instances'] = fetch_ec2(session, regions)
    data['EBS_Volumes'] = fetch_ebs(session, regions)
    ...

    # Multi-return fetchers are unpacked
    ecs_clusters, ecs_services = fetch_ecs(session, regions)
    data['ECS_Clusters'] = ecs_clusters
    data['ECS_Services'] = ecs_services
    ...

    return data
```

It returns a dictionary where:
- Keys = Excel sheet names (e.g., `'EC2_Instances'`, `'S3'`, `'IAM_Users'`)
- Values = lists of dicts (each dict is one row in the Excel sheet)

The fetchers are called in logical groups: Compute → Storage → Database → Networking → Management → Security → App Integration → Analytics → Governance → IAM.

---

## 5. Excel Export (Lines 1122–1145)

### `export_to_excel_buffer(data_dict)`

Generates an Excel file entirely in memory:

```python
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
    for sheet_name, data in data_dict.items():
        if data:  # Skip empty sheets
            df = pd.DataFrame(data)
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
buffer.seek(0)
return buffer
```

- Uses `io.BytesIO` instead of a file path — no disk I/O needed
- Sheet names are truncated to 31 characters (Excel limit)
- Empty datasets are skipped (no empty sheets in the output)
- Any remaining datetime objects are converted to strings via `safe_dt`

### `upload_to_s3(buffer, bucket, s3_key)`

Uploads the in-memory Excel buffer to S3:

```python
s3.put_object(Bucket=bucket, Key=s3_key, Body=buffer.getvalue(),
              ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
```

Sets the correct MIME type so the file is recognized as an Excel file when downloaded from S3.

---

## 6. Lambda Handler (Lines 1147–1220)

### `lambda_handler(event, context)`

This is the entry point that AWS Lambda invokes.

**Step 1 — Parse input:**
```python
envs = event.get('environments', list(ACCOUNTS.keys()))
bucket = event.get('bucket', S3_BUCKET)
```
- If `{"environments": ["dev"]}` is passed, only `dev` is processed
- If no payload, defaults to all accounts in `ACCOUNTS` dict
- Bucket can also be overridden via the event payload

**Step 2 — Create SSM client:**
```python
ssm_client = boto3.client('ssm')
```
This uses the Lambda function's own IAM role to read SSM parameters (in the same account where Lambda runs).

**Step 3 — Loop through environments:**
```python
for env in envs:
    # Validate env exists in ACCOUNTS
    if env not in ACCOUNTS:
        skip...

    # Create session for target account
    session = get_account_session(ssm_client, ACCOUNTS[env])

    # Get account info for filename
    account_id, account_name = get_account_info(session)

    # Collect all inventory
    data = collect_inventory(session)

    # Generate Excel in memory
    buffer = export_to_excel_buffer(data)

    # Build S3 path: inventory/YYYY/MM/AccountName_env_YYYYMMDD_HHMMSS.xlsx
    s3_key = f"inventory/{now.strftime('%Y')}/{now.strftime('%m')}/{account_name}_{env}_{timestamp}.xlsx"

    # Upload to S3
    upload_to_s3(buffer, bucket, s3_key)
```

**Step 4 — Return results:**
```python
return {
    'statusCode': 200,
    'body': {
        'dev': {'status': 'success', 'account_id': '...', 's3_path': '...', 'total_resources': 1234},
        ...
    }
}
```

Each environment's result includes status, account info, S3 path, and total resource count.

---

## 7. Execution Flow Summary

```
Lambda invoked with {"environments": ["dev"]}
  │
  ├─ Read SSM: /fetch_inv/dev-access-key
  ├─ Read SSM: /fetch_inv/dev-secret-key
  ├─ Create boto3 session with those credentials
  │
  ├─ Get account ID and alias
  ├─ Get all enabled regions (e.g., 20+ regions)
  │
  ├─ For each of 40+ services:
  │     For each region:
  │       Call AWS API → collect resources
  │
  ├─ Convert all collected data to Excel (in memory)
  ├─ Upload Excel to s3://aws-inventory-collector/inventory/2026/04/AcctName_dev_20260414_060000.xlsx
  │
  └─ Return summary with resource counts
```

---

## 8. deploy.sh Flow

```
sh deploy.sh 1.0.9
  │
  ├─ git fetch --all
  ├─ git checkout 1.0.9
  ├─ Show git status, ask for confirmation
  │
  ├─ Login to ECR (471112573018.dkr.ecr.ap-south-1.amazonaws.com)
  ├─ Docker build --no-cache --provenance=false
  │     FROM public.ecr.aws/lambda/python:3.11
  │     COPY requirements.txt → pip install
  │     COPY lambda_function.py
  │
  ├─ Tag and push image to ECR
  ├─ aws lambda update-function-code with new image URI
  └─ Show Lambda function state
```

The `--provenance=false` flag is critical — without it, Docker BuildKit creates a manifest list (OCI index) that Lambda doesn't support.

---

## 9. Dockerfile

```dockerfile
FROM public.ecr.aws/lambda/python:3.11       # AWS Lambda Python 3.11 base image
COPY requirements.txt ${LAMBDA_TASK_ROOT}/    # Copy deps list
RUN pip install -r ... --no-cache-dir         # Install pandas, numpy, openpyxl
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/  # Copy the function code
CMD ["lambda_function.lambda_handler"]        # Set the handler
```

- Uses the official AWS Lambda Python base image from public ECR
- `LAMBDA_TASK_ROOT` is `/var/task` — the standard Lambda function directory
- `boto3` is pre-installed in the base image, so only pandas/numpy/openpyxl are installed
- `--no-cache-dir` keeps the image size smaller

---

## 10. Dependencies (requirements.txt)

```
boto3>=1.26.0        # AWS SDK (already in base image, but listed for completeness)
pandas==2.2.3        # DataFrame + Excel export
numpy==1.26.4        # Required by pandas (pinned to avoid source compilation)
openpyxl>=3.0.0      # Excel engine used by pandas
```

`pandas` and `numpy` are pinned to specific versions because newer versions (pandas 3.x, numpy 2.x) require a C compiler to build from source, which isn't available in the Lambda base image.

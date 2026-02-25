# AWS Complete Inventory Script

Comprehensive Python script to collect AWS inventory across 50+ services and export to Excel.

## 🎯 How It Works: Two Scripts

### Script 1: `fetch_aws_services.py` (Service Discovery)
Discovers which AWS services you're actually using by querying Cost Explorer (last 90 days) and saves them to `aws_services.txt`.

### Script 2: `aws_inventory_dynamic.py` (Inventory Collection)
Reads `aws_services.txt` and collects detailed inventory for those services, plus core services (EC2, VPC, S3, IAM).

### Important: Script Relationship

The two scripts work together but have a limitation:

1. `fetch_aws_services.py` discovers services and saves to `aws_services.txt` with account info
2. `aws_inventory_dynamic.py` reads `aws_services.txt` and maps service names to fetch functions
3. **LIMITATION**: If a NEW service is added to your AWS account:
   - Step 1 will detect it and add to `aws_services.txt` ✓
   - Step 2 will try to map it using `SERVICE_NAME_MAPPING` dictionary
   - **BUT** if there's no fetch function for that service, it will be skipped ⚠
   - You'll need to add a new fetch function in `aws_inventory_dynamic.py` for that service

**Example**: If AWS launches a new service "AWS NewService" and you start using it:
- `fetch_aws_services.py` will list it in `aws_services.txt`
- `aws_inventory_dynamic.py` will show: `⚠ AWS NewService -> (not yet supported)`
- You'll need to add a `fetch_newservice()` function and update `SERVICE_NAME_MAPPING`

**Workaround**: The script always fetches core services (EC2, VPC, S3, IAM, etc.) even if not in the file, so you'll still get a comprehensive inventory of common services.

## Prerequisites

1. **Python 3.7+** installed
2. **AWS credentials** configured with **ReadOnlyAccess** or equivalent read permissions
3. **Required packages**:
   ```bash
   pip install -r requirements.txt
   ```

## AWS Permissions Required

Your AWS IAM user/role needs **ReadOnlyAccess** managed policy or equivalent read permissions for all services.

Minimum permissions:
- All `Describe*`, `List*`, `Get*` actions for services you want to inventory
- `ce:GetCostAndUsage` for service discovery (Step 1)
- `sts:GetCallerIdentity` for account info
- `iam:ListAccountAliases` for account name (optional)

## Quick Start

```bash
# 1. Install dependencies (first time only)
pip install -r requirements.txt

# 2. Discover services (creates aws_services.txt with account info)
python fetch_aws_services.py

# 3. Collect inventory (creates Excel file with account name)
python aws_inventory_dynamic.py

# Or use the batch/shell script to run both:
# Windows:
run.bat

# Linux/Mac:
chmod +x run.sh
./run.sh
```

### Output Files:
- `aws_services.txt` - List of services with account number and name
- `AWS_Inventory_<AccountName>_YYYYMMDD_HHMMSS.xlsx` - Excel file with inventory
  - Each AWS service in a separate sheet (50+ sheets)
  - Scans all AWS regions automatically
  - Takes 10-20 minutes depending on resources

## Services Collected (50+)

### Compute
- **EC2 Instances** - All instances with IPs, volumes, security groups
- **EBS Volumes** - All volumes with size, type, attachments
- **ECS Clusters** - Clusters with task counts
- **ECS Services** - Services with desired/running counts
- **ECR Repositories** - Container repositories
- **Lambda Functions** - Functions with runtime, VPC config
- **Elastic IPs** - All Elastic IPs
- **Key Pairs** - EC2 key pairs
- **ENI** - Elastic Network Interfaces

### Storage
- **S3 Buckets** - Buckets with region, access level
- **EFS** - File systems

### Database
- **RDS Instances** - Databases with engine, endpoint
- **DynamoDB Tables** - Tables with item counts
- **DAX Clusters** - DynamoDB Accelerator clusters
- **ElastiCache** - Redis/Memcached clusters
- **OpenSearch** - OpenSearch domains

### Networking
- **VPCs** - VPCs with CIDR blocks
- **Subnets** - Subnets with availability zones
- **Security Groups** - All security groups
- **Load Balancers** - ALB/NLB with DNS names
- **Route53** - Hosted zones
- **CloudFront** - Distributions
- **API Gateway** - REST APIs
- **VPC Endpoints** - VPC endpoints
- **Internet Gateways** - IGWs
- **NAT Gateways** - NAT gateways
- **Transit Gateways** - TGWs
- **Direct Connect** - Direct Connect connections

### Security & Identity
- **IAM Users** - All IAM users
- **IAM Roles** - All IAM roles
- **IAM Policies** - Customer managed policies
- **KMS Keys** - Encryption keys
- **Secrets Manager** - Secrets
- **ACM Certificates** - SSL/TLS certificates
- **WAF** - Web Application Firewall rules
- **Cognito User Pools** - User pools
- **Cognito Identity Pools** - Identity pools

### Management & Governance
- **CloudFormation** - Stacks with status
- **CloudTrail** - Trails
- **CloudWatch Alarms** - All alarms
- **CloudWatch Log Groups** - Log groups
- **EventBridge Rules** - Event rules
- **Config Rules** - Config rules
- **SSM Parameters** - Systems Manager parameters
- **AWS Backup** - Backup plans and vaults

### Application Integration
- **SNS Topics** - All topics
- **SQS Queues** - All queues
- **Step Functions** - State machines
- **MQ** - Message brokers
- **Kafka (MSK)** - Managed Kafka clusters
- **SES** - Email identities

### Analytics & ML
- **Glue Databases** - Glue databases
- **Glue Jobs** - ETL jobs
- **SageMaker** - Notebook instances
- **Kinesis** - Data streams
- **Redshift** - Data warehouse clusters

### Developer Tools
- **CodeBuild** - Build projects
- **CodePipeline** - CI/CD pipelines

### Monitoring
- **Grafana** - Managed Grafana workspaces
- **Prometheus** - Managed Prometheus workspaces
- **MWAA (Airflow)** - Managed Airflow environments

## Script Structure

The script is organized in 3 sections:

1. **Helper Functions** - Datetime conversion, file handling, account info
2. **Service Fetchers** - Individual fetch function for each AWS service (50+ functions)
3. **Main Execution** - Orchestrates collection and export

## Files

- `fetch_aws_services.py` - Service discovery script (Step 1)
- `aws_inventory_dynamic.py` - Main inventory collection script (Step 2)
- `aws_services.txt` - Generated list of services with account info
- `requirements.txt` - Python dependencies (boto3, pandas, openpyxl)
- `run.bat` - Quick run batch file
- `README.md` - This file

## Troubleshooting

### "NoCredentialsError"
- Run `aws configure` to set up credentials
- Or set environment variables (see above)

### "Access Denied"
- Ensure your IAM user has **ReadOnlyAccess** managed policy or equivalent read permissions
- For service discovery, you also need `ce:GetCostAndUsage` permission

### Missing Resources
- Check if resources exist in the regions being scanned
- Verify IAM permissions for that specific service
- Some services are region-specific (e.g., S3 is global, EC2 is regional)

### Script is Slow
- Normal behavior - scans all regions for all services
- Expected time: 10-20 minutes
- Faster on accounts with fewer resources

## Performance

- **Small account** (< 100 resources): 5-10 minutes
- **Medium account** (100-1000 resources): 10-15 minutes
- **Large account** (1000+ resources): 15-25 minutes

## Files

- `fetch_aws_services.py` - Service discovery script (Step 1)
- `aws_inventory_dynamic.py` - Main inventory collection script (Step 2)
- `aws_services.txt` - Generated list of services with account info (created by Step 1)
- `requirements.txt` - Python dependencies (boto3, pandas, openpyxl)
- `run.bat` - Quick run batch file for Windows
- `run.sh` - Quick run shell script for Linux/Mac
- `README.md` - This file

## Example Output

### aws_services.txt (after Step 1):
```
# AWS Account: 123456789012
# Account Name: production-account
# Generated: 2026-02-25 14:30:00
# Total Services: 35
#
# Services discovered from Cost Explorer (last 90 days):
#======================================================================

AWS Lambda
Amazon Elastic Compute Cloud - Compute
Amazon Simple Storage Service
Amazon Relational Database Service
...
```

### Excel File (after Step 2):
Filename: `AWS_Inventory_production-account_20260225_143000.xlsx`

```
Summary:
  EC2_Instances: 24 resources
  EBS_Volumes: 45 resources
  ECS_Clusters: 7 resources
  ECS_Services: 21 resources
  ECR_Repositories: 12 resources
  Lambda: 51 resources
  S3: 58 resources
  RDS: 3 resources
  DynamoDB: 15 resources
  ElastiCache: 2 resources
  OpenSearch: 1 resources
  VPC: 18 resources
  Subnets: 74 resources
  Security_Groups: 68 resources
  Load_Balancers: 16 resources
  Route53: 5 resources
  CloudFront: 3 resources
  API_Gateway: 8 resources
  CloudFormation: 100 resources
  CloudTrail: 2 resources
  CloudWatch_Alarms: 200 resources
  CloudWatch_Log_Groups: 150 resources
  EventBridge: 115 resources
  KMS_Keys: 25 resources
  Secrets_Manager: 18 resources
  ACM_Certificates: 12 resources
  SNS_Topics: 10 resources
  SQS_Queues: 8 resources
  SSM_Parameters: 1000 resources
  Config_Rules: 25 resources
  Glue_Jobs: 200 resources
  IAM_Users: 4 resources
  IAM_Roles: 909 resources
  IAM_Policies: 257 resources

Total: 3500+ resources
```

## Notes

- Script scans all enabled AWS regions by default
- Each service is exported to a separate Excel sheet
- Serial numbers (Sr. No.) are included for easy reference
- Errors in one service don't stop collection of other services
- All timestamps are converted to readable format (no timezone issues)
- Handles missing fields gracefully (shows 'N/A')

## Support

For issues or questions:
1. Check AWS credentials are configured correctly (`aws sts get-caller-identity`)
2. Verify IAM permissions - need **ReadOnlyAccess** or equivalent
3. For service discovery issues, ensure Cost Explorer is enabled and you have `ce:GetCostAndUsage` permission
4. Check the console output for specific error messages
5. Ensure Python 3.7+ and all dependencies are installed

## Adding New Services

If you need to add support for a new AWS service:

1. Add service name mapping in `SERVICE_NAME_MAPPING` dictionary
2. Create a new `fetch_<service>()` function following the existing pattern
3. Add the service to the main execution logic in `main()` function
4. Use paginators for API calls that return lists (see existing examples)
5. Always include error handling and logging

Example:
```python
def fetch_new_service(session, regions):
    """Fetch New Service resources"""
    logger.info("Fetching New Service...")
    all_resources = []
    serial_number = 1
    
    for region in regions:
        try:
            client = session.client('newservice', region_name=region)
            paginator = client.get_paginator('list_resources')
            
            for page in paginator.paginate():
                for resource in page['Resources']:
                    all_resources.append({
                        'Sr. No.': serial_number,
                        'Name': resource['Name'],
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching New Service in {region}: {e}")
    
    return all_resources
```

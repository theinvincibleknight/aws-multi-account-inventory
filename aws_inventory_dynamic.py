#!/usr/bin/env python3
"""
AWS Dynamic Inventory Script
Step 2: Reads services from aws_services.txt (created by fetch_aws_services.py)
        and fetches details for all of them
"""

import boto3
import pandas as pd
from datetime import datetime
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# SERVICE NAME MAPPING
# ============================================================================

# Map Cost Explorer service names to our fetch functions
SERVICE_NAME_MAPPING = {
    'Amazon Elastic Compute Cloud - Compute': 'ec2',
    'EC2 - Other': 'ebs',
    'Amazon Elastic Container Service': 'ecs',
    'Amazon EC2 Container Registry (ECR)': 'ecr',
    'AWS Lambda': 'lambda',
    'Amazon Simple Storage Service': 's3',
    'Amazon Relational Database Service': 'rds',
    'Amazon RDS Service': 'rds',
    'Amazon DynamoDB': 'dynamodb',
    'DynamoDB Accelerator (DAX)': 'dax',
    'Amazon ElastiCache': 'elasticache',
    'Amazon OpenSearch Service': 'opensearch',
    'Amazon Virtual Private Cloud': 'vpc',
    'Amazon VPC': 'vpc',
    'Amazon Elastic Load Balancing': 'load_balancers',
    'Amazon Route 53': 'route53',
    'Amazon CloudFront': 'cloudfront',
    'Amazon API Gateway': 'api_gateway',
    'AWS CloudFormation': 'cloudformation',
    'AWS CloudTrail': 'cloudtrail',
    'Amazon CloudWatch': 'cloudwatch',
    'AmazonCloudWatch': 'cloudwatch',
    'CloudWatch Events': 'eventbridge',
    'Amazon EventBridge': 'eventbridge',
    'AWS Key Management Service': 'kms',
    'AWS Secrets Manager': 'secrets',
    'AWS Certificate Manager': 'acm',
    'Amazon Simple Notification Service': 'sns',
    'Amazon Simple Queue Service': 'sqs',
    'AWS Step Functions': 'stepfunctions',
    'Amazon MQ': 'mq',
    'Amazon Managed Streaming for Apache Kafka': 'kafka',
    'AWS CodeBuild': 'codebuild',
    'CodeBuild': 'codebuild',
    'AWS CodePipeline': 'codepipeline',
    'AWS Glue': 'glue',
    'AWS Backup': 'backup',
    'AWS Amplify': 'amplify',
    'Amazon SageMaker': 'sagemaker',
    'Amazon Simple Email Service': 'ses',
    'AWS WAF': 'waf',
    'Amazon Cognito': 'cognito',
    'AWS Config': 'config',
    'AWS Systems Manager': 'ssm',
    'AWS Direct Connect': 'directconnect',
    'Amazon Kinesis': 'kinesis',
    'Amazon Redshift': 'redshift',
    'Amazon Elastic File System': 'efs',
    'Amazon EFS': 'efs',
    'Amazon Location Service': 'location',
    'Amazon Managed Grafana': 'grafana',
    'AWS Security Hub': 'securityhub',
    'AWS CloudShell': 'cloudshell',
    'Amazon Bedrock': 'bedrock',
    'AWS Cost Explorer': 'cost_explorer',
    'Amazon Managed Workflows for Apache Airflow': 'airflow',
    'Amazon Managed Service for Prometheus': 'prometheus',
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def safe_datetime_convert(dt_value):
    """Safely convert datetime to string, handling timezone-aware datetimes"""
    if dt_value is None or dt_value == 'N/A':
        return 'N/A'
    if hasattr(dt_value, 'strftime'):
        if hasattr(dt_value, 'tzinfo') and dt_value.tzinfo is not None:
            dt_value = dt_value.replace(tzinfo=None)
        return dt_value.strftime('%Y-%m-%d %H:%M:%S')
    return str(dt_value)


def get_account_info():
    """Get AWS account number and alias/name"""
    try:
        sts = boto3.client('sts')
        account_id = sts.get_caller_identity()['Account']
        
        # Try to get account alias
        try:
            iam = boto3.client('iam')
            aliases = iam.list_account_aliases()['AccountAliases']
            account_name = aliases[0] if aliases else account_id
        except:
            account_name = account_id
        
        return account_id, account_name
    except Exception as e:
        logger.error(f"Error getting account info: {e}")
        return 'Unknown', 'Unknown'


def load_services_from_file(filename='aws_services.txt'):
    """Load AWS services list from file"""
    if not os.path.exists(filename):
        logger.warning(f"{filename} not found.")
        logger.warning("Run 'python fetch_aws_services.py' first to discover services!")
        logger.info("Falling back to collecting all common services...")
        return None
    
    try:
        with open(filename, 'r') as f:
            services = [line.strip() for line in f if line.strip()]
        logger.info(f"Loaded {len(services)} services from {filename}")
        return services
    except Exception as e:
        logger.error(f"Error reading {filename}: {e}")
        return None


def map_service_to_fetcher(service_name):
    """Map Cost Explorer service name to our internal service name"""
    return SERVICE_NAME_MAPPING.get(service_name, None)


# ============================================================================
# DYNAMIC SERVICE FETCHERS
# ============================================================================

def fetch_ec2_instances(session, regions):
    """Fetch EC2 instances"""
    logger.info("Fetching EC2 instances...")
    all_instances = []
    serial_number = 1
    
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            response = ec2.describe_instances()
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    volume_ids = [bdm['Ebs']['VolumeId'] for bdm in instance.get('BlockDeviceMappings', []) if 'Ebs' in bdm]
                    tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                    
                    all_instances.append({
                        'Sr. No': serial_number,
                        'InstanceId': instance['InstanceId'],
                        'InstanceName': tags.get('Name', 'N/A'),
                        'InstanceState': instance['State']['Name'],
                        'InstanceType': instance['InstanceType'],
                        'AvailabilityZone': instance['Placement']['AvailabilityZone'],
                        'PublicIpAddress': instance.get('PublicIpAddress', 'N/A'),
                        'PrivateIpAddress': instance.get('PrivateIpAddress', 'N/A'),
                        'VpcId': instance.get('VpcId', 'N/A'),
                        'SubnetId': instance.get('SubnetId', 'N/A'),
                        'VolumeId': ','.join(volume_ids) if volume_ids else 'N/A',
                        'SecurityGroupName': ','.join([sg['GroupName'] for sg in instance.get('SecurityGroups', [])]),
                        'KeyName': instance.get('KeyName', 'N/A'),
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching EC2 in {region}: {e}")
    
    return all_instances


def fetch_ebs_volumes(session, regions):
    """Fetch EBS volumes"""
    logger.info("Fetching EBS volumes...")
    all_volumes = []
    serial_number = 1
    
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            volumes = ec2.describe_volumes()['Volumes']
            
            for volume in volumes:
                tags = {tag['Key']: tag['Value'] for tag in volume.get('Tags', [])}
                attachments = volume.get('Attachments', [])
                
                all_volumes.append({
                    'Sr. No.': serial_number,
                    'VolumeId': volume['VolumeId'],
                    'Name': tags.get('Name', 'N/A'),
                    'Size': volume['Size'],
                    'VolumeType': volume['VolumeType'],
                    'State': volume['State'],
                    'AvailabilityZone': volume['AvailabilityZone'],
                    'Encrypted': volume['Encrypted'],
                    'AttachedTo': attachments[0]['InstanceId'] if attachments else 'N/A',
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching EBS in {region}: {e}")
    
    return all_volumes


def fetch_ecs_clusters(session, regions):
    """Fetch ECS clusters"""
    logger.info("Fetching ECS clusters...")
    all_clusters = []
    serial_number = 1
    
    for region in regions:
        try:
            ecs = session.client('ecs', region_name=region)
            cluster_arns = ecs.list_clusters()['clusterArns']
            
            if cluster_arns:
                clusters = ecs.describe_clusters(clusters=cluster_arns)['clusters']
                for cluster in clusters:
                    all_clusters.append({
                        'Sr. No.': serial_number,
                        'Cluster Name': cluster['clusterName'],
                        'Status': cluster['status'],
                        'Running Tasks': cluster.get('runningTasksCount', 0),
                        'Pending Tasks': cluster.get('pendingTasksCount', 0),
                        'Active Services': cluster.get('activeServicesCount', 0),
                        'Registered Instances': cluster.get('registeredContainerInstancesCount', 0),
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching ECS in {region}: {e}")
    
    return all_clusters


def fetch_ecr_repositories(session, regions):
    """Fetch ECR repositories"""
    logger.info("Fetching ECR repositories...")
    all_repos = []
    serial_number = 1
    
    for region in regions:
        try:
            ecr = session.client('ecr', region_name=region)
            paginator = ecr.get_paginator('describe_repositories')
            
            for page in paginator.paginate():
                for repo in page['repositories']:
                    all_repos.append({
                        'Sr. No.': serial_number,
                        'Repository Name': repo['repositoryName'],
                        'Repository URI': repo['repositoryUri'],
                        'Created At': safe_datetime_convert(repo.get('createdAt')),
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching ECR in {region}: {e}")
    
    return all_repos


def fetch_lambda_functions(session, regions):
    """Fetch Lambda functions"""
    logger.info("Fetching Lambda functions...")
    all_functions = []
    serial_number = 1
    
    for region in regions:
        try:
            lambda_client = session.client('lambda', region_name=region)
            paginator = lambda_client.get_paginator('list_functions')
            
            for page in paginator.paginate():
                for func in page['Functions']:
                    vpc_config = func.get('VpcConfig', {})
                    all_functions.append({
                        'Sr. No': serial_number,
                        'Function Name': func['FunctionName'],
                        'Runtime': func.get('Runtime', 'N/A'),
                        'Handler': func.get('Handler', 'N/A'),
                        'MemorySize': func.get('MemorySize', 0),
                        'Timeout': func.get('Timeout', 0),
                        'Role': func['Role'],
                        'VpcId': vpc_config.get('VpcId', 'N/A'),
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Lambda in {region}: {e}")
    
    return all_functions


def fetch_s3_buckets(session):
    """Fetch S3 buckets"""
    logger.info("Fetching S3 buckets...")
    all_buckets = []
    serial_number = 1
    
    try:
        s3 = session.client('s3')
        # S3 list_buckets doesn't support pagination, but returns all buckets
        buckets = s3.list_buckets()['Buckets']
        
        for bucket in buckets:
            bucket_name = bucket['Name']
            
            try:
                location = s3.get_bucket_location(Bucket=bucket_name)
                region = location['LocationConstraint'] or 'us-east-1'
            except:
                region = 'N/A'
            
            try:
                acl = s3.get_bucket_acl(Bucket=bucket_name)
                is_public = any(
                    grant.get('Grantee', {}).get('URI') == 'http://acs.amazonaws.com/groups/global/AllUsers'
                    for grant in acl.get('Grants', [])
                )
                access = 'Public' if is_public else 'Private'
            except:
                access = 'N/A'
            
            all_buckets.append({
                'Sr. No.': serial_number,
                'Bucket Name': bucket_name,
                'Region': region,
                'Access': access,
                'Creation Date': safe_datetime_convert(bucket['CreationDate'])
            })
            serial_number += 1
    except Exception as e:
        logger.error(f"Error fetching S3 buckets: {e}")
    
    return all_buckets



def fetch_rds_instances(session, regions):
    """Fetch RDS instances"""
    logger.info("Fetching RDS instances...")
    all_rds = []
    serial_number = 1
    
    for region in regions:
        try:
            rds = session.client('rds', region_name=region)
            db_instances = rds.describe_db_instances()['DBInstances']
            
            for db in db_instances:
                all_rds.append({
                    'Sr. No.': serial_number,
                    'DB Identifier': db['DBInstanceIdentifier'],
                    'Endpoint': db.get('Endpoint', {}).get('Address', 'N/A'),
                    'Port': db.get('Endpoint', {}).get('Port', 'N/A'),
                    'Engine': db['Engine'],
                    'EngineVersion': db['EngineVersion'],
                    'DBInstanceClass': db['DBInstanceClass'],
                    'AllocatedStorage': db['AllocatedStorage'],
                    'MultiAZ': db['MultiAZ'],
                    'AvailabilityZone': db.get('AvailabilityZone', 'N/A'),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching RDS in {region}: {e}")
    
    return all_rds


def fetch_dynamodb_tables(session, regions):
    """Fetch DynamoDB tables"""
    logger.info("Fetching DynamoDB tables...")
    all_tables = []
    serial_number = 1
    
    for region in regions:
        try:
            dynamodb = session.client('dynamodb', region_name=region)
            paginator = dynamodb.get_paginator('list_tables')
            
            for page in paginator.paginate():
                for table_name in page['TableNames']:
                    try:
                        table = dynamodb.describe_table(TableName=table_name)['Table']
                        all_tables.append({
                            'Sr. No.': serial_number,
                            'TableName': table['TableName'],
                            'Status': table['TableStatus'],
                            'ItemCount': table.get('ItemCount', 0),
                            'TableSizeBytes': table.get('TableSizeBytes', 0),
                            'Region': region
                        })
                        serial_number += 1
                    except:
                        pass
        except Exception as e:
            logger.error(f"Error fetching DynamoDB in {region}: {e}")
    
    return all_tables


def fetch_elasticache_clusters(session, regions):
    """Fetch ElastiCache clusters"""
    logger.info("Fetching ElastiCache clusters...")
    all_clusters = []
    serial_number = 1
    
    for region in regions:
        try:
            elasticache = session.client('elasticache', region_name=region)
            clusters = elasticache.describe_cache_clusters()['CacheClusters']
            
            for cluster in clusters:
                all_clusters.append({
                    'Sr. No.': serial_number,
                    'CacheClusterId': cluster['CacheClusterId'],
                    'Engine': cluster.get('Engine', 'N/A'),
                    'EngineVersion': cluster.get('EngineVersion', 'N/A'),
                    'CacheNodeType': cluster.get('CacheNodeType', 'N/A'),
                    'Status': cluster.get('CacheClusterStatus', 'N/A'),
                    'NumCacheNodes': cluster.get('NumCacheNodes', 0),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching ElastiCache in {region}: {e}")
    
    return all_clusters


def fetch_opensearch_domains(session, regions):
    """Fetch OpenSearch domains"""
    logger.info("Fetching OpenSearch domains...")
    all_domains = []
    serial_number = 1
    
    for region in regions:
        try:
            opensearch = session.client('opensearch', region_name=region)
            domain_names = opensearch.list_domain_names()['DomainNames']
            
            for domain_info in domain_names:
                domain_name = domain_info['DomainName']
                try:
                    domain = opensearch.describe_domain(DomainName=domain_name)['DomainStatus']
                    all_domains.append({
                        'Sr. No.': serial_number,
                        'DomainName': domain['DomainName'],
                        'EngineVersion': domain.get('EngineVersion', 'N/A'),
                        'Endpoint': domain.get('Endpoint', 'N/A'),
                        'Created': domain.get('Created', False),
                        'Deleted': domain.get('Deleted', False),
                        'Region': region
                    })
                    serial_number += 1
                except:
                    pass
        except Exception as e:
            logger.error(f"Error fetching OpenSearch in {region}: {e}")
    
    return all_domains


def fetch_vpcs(session, regions):
    """Fetch VPCs"""
    logger.info("Fetching VPCs...")
    all_vpcs = []
    serial_number = 1
    
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            vpcs = ec2.describe_vpcs()['Vpcs']
            
            for vpc in vpcs:
                tags = {tag['Key']: tag['Value'] for tag in vpc.get('Tags', [])}
                all_vpcs.append({
                    'Sr. No.': serial_number,
                    'VpcId': vpc['VpcId'],
                    'Name': tags.get('Name', 'N/A'),
                    'CidrBlock': vpc['CidrBlock'],
                    'State': vpc['State'],
                    'IsDefault': vpc['IsDefault'],
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching VPCs in {region}: {e}")
    
    return all_vpcs


def fetch_subnets(session, regions):
    """Fetch Subnets"""
    logger.info("Fetching Subnets...")
    all_subnets = []
    serial_number = 1
    
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            subnets = ec2.describe_subnets()['Subnets']
            
            for subnet in subnets:
                tags = {tag['Key']: tag['Value'] for tag in subnet.get('Tags', [])}
                all_subnets.append({
                    'Sr. No.': serial_number,
                    'SubnetId': subnet['SubnetId'],
                    'Name': tags.get('Name', 'N/A'),
                    'VpcId': subnet['VpcId'],
                    'CidrBlock': subnet['CidrBlock'],
                    'AvailabilityZone': subnet['AvailabilityZone'],
                    'AvailableIpAddressCount': subnet['AvailableIpAddressCount'],
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Subnets in {region}: {e}")
    
    return all_subnets


def fetch_security_groups(session, regions):
    """Fetch Security Groups"""
    logger.info("Fetching Security Groups...")
    all_sgs = []
    serial_number = 1
    
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            sgs = ec2.describe_security_groups()['SecurityGroups']
            
            for sg in sgs:
                all_sgs.append({
                    'Sr. No.': serial_number,
                    'GroupId': sg['GroupId'],
                    'GroupName': sg['GroupName'],
                    'Description': sg['Description'],
                    'VpcId': sg.get('VpcId', 'N/A'),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Security Groups in {region}: {e}")
    
    return all_sgs


def fetch_load_balancers(session, regions):
    """Fetch Load Balancers"""
    logger.info("Fetching Load Balancers...")
    all_lbs = []
    serial_number = 1
    
    for region in regions:
        try:
            elbv2 = session.client('elbv2', region_name=region)
            lbs = elbv2.describe_load_balancers()['LoadBalancers']
            
            for lb in lbs:
                all_lbs.append({
                    'Sr. No.': serial_number,
                    'LoadBalancerName': lb['LoadBalancerName'],
                    'DNSName': lb['DNSName'],
                    'Type': lb['Type'],
                    'Scheme': lb['Scheme'],
                    'State': lb['State']['Code'],
                    'VpcId': lb['VpcId'],
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Load Balancers in {region}: {e}")
    
    return all_lbs


def fetch_route53_zones(session):
    """Fetch Route53 hosted zones"""
    logger.info("Fetching Route53 hosted zones...")
    all_zones = []
    serial_number = 1
    
    try:
        route53 = session.client('route53')
        zones = route53.list_hosted_zones()['HostedZones']
        
        for zone in zones:
            all_zones.append({
                'Sr. No.': serial_number,
                'Name': zone['Name'],
                'Id': zone['Id'],
                'ResourceRecordSetCount': zone.get('ResourceRecordSetCount', 0),
                'PrivateZone': zone.get('Config', {}).get('PrivateZone', False)
            })
            serial_number += 1
    except Exception as e:
        logger.error(f"Error fetching Route53 zones: {e}")
    
    return all_zones


def fetch_cloudfront_distributions(session):
    """Fetch CloudFront distributions"""
    logger.info("Fetching CloudFront distributions...")
    all_distributions = []
    serial_number = 1
    
    try:
        cloudfront = session.client('cloudfront')
        distributions = cloudfront.list_distributions().get('DistributionList', {}).get('Items', [])
        
        for dist in distributions:
            all_distributions.append({
                'Sr. No.': serial_number,
                'Id': dist['Id'],
                'DomainName': dist['DomainName'],
                'Status': dist['Status'],
                'Enabled': dist['Enabled'],
                'Comment': dist.get('Comment', 'N/A')
            })
            serial_number += 1
    except Exception as e:
        logger.error(f"Error fetching CloudFront distributions: {e}")
    
    return all_distributions


def fetch_api_gateways(session, regions):
    """Fetch API Gateways"""
    logger.info("Fetching API Gateways...")
    all_apis = []
    serial_number = 1
    
    for region in regions:
        try:
            apigw = session.client('apigateway', region_name=region)
            apis = apigw.get_rest_apis().get('items', [])
            
            for api in apis:
                all_apis.append({
                    'Sr. No.': serial_number,
                    'Name': api.get('name', 'N/A'),
                    'Id': api['id'],
                    'Description': api.get('description', 'N/A'),
                    'CreatedDate': safe_datetime_convert(api.get('createdDate')),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching API Gateway in {region}: {e}")
    
    return all_apis


def fetch_cloudformation_stacks(session, regions):
    """Fetch CloudFormation stacks"""
    logger.info("Fetching CloudFormation stacks...")
    all_stacks = []
    serial_number = 1
    
    for region in regions:
        try:
            cfn = session.client('cloudformation', region_name=region)
            stacks = cfn.describe_stacks()['Stacks']
            
            for stack in stacks:
                all_stacks.append({
                    'Sr. No.': serial_number,
                    'StackName': stack['StackName'],
                    'StackStatus': stack['StackStatus'],
                    'CreationTime': safe_datetime_convert(stack['CreationTime']),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching CloudFormation in {region}: {e}")
    
    return all_stacks


def fetch_cloudtrail_trails(session, regions):
    """Fetch CloudTrail trails"""
    logger.info("Fetching CloudTrail trails...")
    all_trails = []
    serial_number = 1
    
    for region in regions:
        try:
            cloudtrail = session.client('cloudtrail', region_name=region)
            trails = cloudtrail.describe_trails()['trailList']
            
            for trail in trails:
                all_trails.append({
                    'Sr. No.': serial_number,
                    'Name': trail['Name'],
                    'S3BucketName': trail.get('S3BucketName', 'N/A'),
                    'IsMultiRegionTrail': trail.get('IsMultiRegionTrail', False),
                    'HomeRegion': trail.get('HomeRegion', 'N/A'),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching CloudTrail in {region}: {e}")
    
    return all_trails


def fetch_cloudwatch_alarms(session, regions):
    """Fetch CloudWatch alarms"""
    logger.info("Fetching CloudWatch alarms...")
    all_alarms = []
    serial_number = 1
    
    for region in regions:
        try:
            cloudwatch = session.client('cloudwatch', region_name=region)
            paginator = cloudwatch.get_paginator('describe_alarms')
            
            for page in paginator.paginate():
                for alarm in page.get('MetricAlarms', []):
                    all_alarms.append({
                        'Sr. No.': serial_number,
                        'AlarmName': alarm['AlarmName'],
                        'StateValue': alarm.get('StateValue', 'N/A'),
                        'MetricName': alarm.get('MetricName', 'N/A'),
                        'Namespace': alarm.get('Namespace', 'N/A'),
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching CloudWatch alarms in {region}: {e}")
    
    return all_alarms


def fetch_eventbridge_rules(session, regions):
    """Fetch EventBridge rules"""
    logger.info("Fetching EventBridge rules...")
    all_rules = []
    serial_number = 1
    
    for region in regions:
        try:
            events = session.client('events', region_name=region)
            paginator = events.get_paginator('list_rules')
            
            for page in paginator.paginate():
                for rule in page['Rules']:
                    all_rules.append({
                        'Sr. No.': serial_number,
                        'Name': rule['Name'],
                        'State': rule.get('State', 'N/A'),
                        'Description': rule.get('Description', 'N/A'),
                        'EventBusName': rule.get('EventBusName', 'default'),
                        'ScheduleExpression': rule.get('ScheduleExpression', 'N/A'),
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching EventBridge in {region}: {e}")
    
    return all_rules


def fetch_kms_keys(session, regions):
    """Fetch KMS keys"""
    logger.info("Fetching KMS keys...")
    all_keys = []
    serial_number = 1
    
    for region in regions:
        try:
            kms = session.client('kms', region_name=region)
            paginator = kms.get_paginator('list_keys')
            
            for page in paginator.paginate():
                for key in page['Keys']:
                    try:
                        key_metadata = kms.describe_key(KeyId=key['KeyId'])['KeyMetadata']
                        all_keys.append({
                            'Sr. No.': serial_number,
                            'KeyId': key['KeyId'],
                            'Description': key_metadata.get('Description', 'N/A'),
                            'KeyState': key_metadata.get('KeyState', 'N/A'),
                            'Enabled': key_metadata.get('Enabled', False),
                            'Region': region
                        })
                        serial_number += 1
                    except:
                        pass
        except Exception as e:
            logger.error(f"Error fetching KMS in {region}: {e}")
    
    return all_keys


def fetch_secrets(session, regions):
    """Fetch Secrets Manager secrets"""
    logger.info("Fetching Secrets Manager secrets...")
    all_secrets = []
    serial_number = 1
    
    for region in regions:
        try:
            secrets = session.client('secretsmanager', region_name=region)
            paginator = secrets.get_paginator('list_secrets')
            
            for page in paginator.paginate():
                for secret in page['SecretList']:
                    all_secrets.append({
                        'Sr. No.': serial_number,
                        'Name': secret.get('Name', 'N/A'),
                        'Description': secret.get('Description', 'N/A'),
                        'LastChangedDate': safe_datetime_convert(secret.get('LastChangedDate')),
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Secrets Manager in {region}: {e}")
    
    return all_secrets


def fetch_sns_topics(session, regions):
    """Fetch SNS topics"""
    logger.info("Fetching SNS topics...")
    all_topics = []
    serial_number = 1
    
    for region in regions:
        try:
            sns = session.client('sns', region_name=region)
            paginator = sns.get_paginator('list_topics')
            
            for page in paginator.paginate():
                for topic in page['Topics']:
                    topic_arn = topic['TopicArn']
                    all_topics.append({
                        'Sr. No.': serial_number,
                        'TopicArn': topic_arn,
                        'TopicName': topic_arn.split(':')[-1],
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching SNS in {region}: {e}")
    
    return all_topics


def fetch_sqs_queues(session, regions):
    """Fetch SQS queues"""
    logger.info("Fetching SQS queues...")
    all_queues = []
    serial_number = 1
    
    for region in regions:
        try:
            sqs = session.client('sqs', region_name=region)
            paginator = sqs.get_paginator('list_queues')
            
            for page in paginator.paginate():
                for queue_url in page.get('QueueUrls', []):
                    all_queues.append({
                        'Sr. No.': serial_number,
                        'QueueName': queue_url.split('/')[-1],
                        'QueueUrl': queue_url,
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching SQS in {region}: {e}")
    
    return all_queues


def fetch_iam_resources(session):
    """Fetch IAM users, roles, and policies"""
    logger.info("Fetching IAM resources...")
    users = []
    roles = []
    policies = []
    
    try:
        iam = session.client('iam')
        
        # Users - with pagination
        serial_number = 1
        paginator = iam.get_paginator('list_users')
        for page in paginator.paginate():
            for user in page['Users']:
                users.append({
                    'Sr. No.': serial_number,
                    'UserName': user['UserName'],
                    'UserId': user['UserId'],
                    'CreateDate': safe_datetime_convert(user['CreateDate']),
                    'Path': user['Path']
                })
                serial_number += 1
        
        # Roles - with pagination
        serial_number = 1
        paginator = iam.get_paginator('list_roles')
        for page in paginator.paginate():
            for role in page['Roles']:
                roles.append({
                    'Sr. No.': serial_number,
                    'RoleName': role['RoleName'],
                    'RoleId': role['RoleId'],
                    'CreateDate': safe_datetime_convert(role['CreateDate']),
                    'Path': role['Path']
                })
                serial_number += 1
        
        # Policies - with pagination
        serial_number = 1
        paginator = iam.get_paginator('list_policies')
        for page in paginator.paginate(Scope='Local'):
            for policy in page['Policies']:
                policies.append({
                    'Sr. No.': serial_number,
                    'PolicyName': policy['PolicyName'],
                    'PolicyId': policy['PolicyId'],
                    'Arn': policy['Arn'],
                    'AttachmentCount': policy['AttachmentCount']
                })
                serial_number += 1
    except Exception as e:
        logger.error(f"Error fetching IAM resources: {e}")
    
    return users, roles, policies


def fetch_rds_instances(session, regions):
    """Fetch RDS instances"""
    logger.info("Fetching RDS instances...")
    all_rds = []
    serial_number = 1
    
    for region in regions:
        try:
            rds = session.client('rds', region_name=region)
            db_instances = rds.describe_db_instances()['DBInstances']
            
            for db in db_instances:
                all_rds.append({
                    'Sr. No.': serial_number,
                    'DB Identifier': db['DBInstanceIdentifier'],
                    'Endpoint': db.get('Endpoint', {}).get('Address', 'N/A'),
                    'Port': db.get('Endpoint', {}).get('Port', 'N/A'),
                    'Engine': db['Engine'],
                    'EngineVersion': db['EngineVersion'],
                    'DBInstanceClass': db['DBInstanceClass'],
                    'AllocatedStorage': db['AllocatedStorage'],
                    'MultiAZ': db['MultiAZ'],
                    'AvailabilityZone': db.get('AvailabilityZone', 'N/A'),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching RDS in {region}: {e}")
    
    return all_rds


def fetch_dax_clusters(session, regions):
    """Fetch DynamoDB Accelerator (DAX) clusters"""
    logger.info("Fetching DAX clusters...")
    all_clusters = []
    serial_number = 1
    
    for region in regions:
        try:
            dax = session.client('dax', region_name=region)
            clusters = dax.describe_clusters()['Clusters']
            
            for cluster in clusters:
                all_clusters.append({
                    'Sr. No.': serial_number,
                    'ClusterName': cluster['ClusterName'],
                    'Status': cluster.get('Status', 'N/A'),
                    'NodeType': cluster.get('NodeType', 'N/A'),
                    'TotalNodes': cluster.get('TotalNodes', 0),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching DAX in {region}: {e}")
    
    return all_clusters


def fetch_stepfunctions(session, regions):
    """Fetch Step Functions state machines"""
    logger.info("Fetching Step Functions...")
    all_state_machines = []
    serial_number = 1
    
    for region in regions:
        try:
            sfn = session.client('stepfunctions', region_name=region)
            state_machines = sfn.list_state_machines()['stateMachines']
            
            for sm in state_machines:
                all_state_machines.append({
                    'Sr. No.': serial_number,
                    'Name': sm['name'],
                    'StateMachineArn': sm['stateMachineArn'],
                    'Type': sm.get('type', 'N/A'),
                    'CreationDate': safe_datetime_convert(sm.get('creationDate')),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Step Functions in {region}: {e}")
    
    return all_state_machines


def fetch_mq_brokers(session, regions):
    """Fetch Amazon MQ brokers"""
    logger.info("Fetching MQ brokers...")
    all_brokers = []
    serial_number = 1
    
    for region in regions:
        try:
            mq = session.client('mq', region_name=region)
            brokers = mq.list_brokers()['BrokerSummaries']
            
            for broker in brokers:
                all_brokers.append({
                    'Sr. No.': serial_number,
                    'BrokerName': broker['BrokerName'],
                    'BrokerId': broker['BrokerId'],
                    'BrokerState': broker.get('BrokerState', 'N/A'),
                    'EngineType': broker.get('EngineType', 'N/A'),
                    'HostInstanceType': broker.get('HostInstanceType', 'N/A'),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching MQ in {region}: {e}")
    
    return all_brokers


def fetch_kafka_clusters(session, regions):
    """Fetch MSK (Kafka) clusters"""
    logger.info("Fetching MSK clusters...")
    all_clusters = []
    serial_number = 1
    
    for region in regions:
        try:
            kafka = session.client('kafka', region_name=region)
            clusters = kafka.list_clusters()['ClusterInfoList']
            
            for cluster in clusters:
                all_clusters.append({
                    'Sr. No.': serial_number,
                    'ClusterName': cluster['ClusterName'],
                    'ClusterArn': cluster['ClusterArn'],
                    'State': cluster.get('State', 'N/A'),
                    'KafkaVersion': cluster.get('CurrentBrokerSoftwareInfo', {}).get('KafkaVersion', 'N/A'),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching MSK in {region}: {e}")
    
    return all_clusters


def fetch_codebuild_projects(session, regions):
    """Fetch CodeBuild projects"""
    logger.info("Fetching CodeBuild projects...")
    all_projects = []
    serial_number = 1
    
    for region in regions:
        try:
            codebuild = session.client('codebuild', region_name=region)
            project_names = codebuild.list_projects()['projects']
            
            if project_names:
                projects = codebuild.batch_get_projects(names=project_names)['projects']
                for project in projects:
                    all_projects.append({
                        'Sr. No.': serial_number,
                        'Name': project['name'],
                        'Arn': project['arn'],
                        'Source': project.get('source', {}).get('type', 'N/A'),
                        'Created': safe_datetime_convert(project.get('created')),
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching CodeBuild in {region}: {e}")
    
    return all_projects


def fetch_codepipeline_pipelines(session, regions):
    """Fetch CodePipeline pipelines"""
    logger.info("Fetching CodePipeline pipelines...")
    all_pipelines = []
    serial_number = 1
    
    for region in regions:
        try:
            codepipeline = session.client('codepipeline', region_name=region)
            pipelines = codepipeline.list_pipelines()['pipelines']
            
            for pipeline in pipelines:
                all_pipelines.append({
                    'Sr. No.': serial_number,
                    'Name': pipeline['name'],
                    'Version': pipeline.get('version', 'N/A'),
                    'Created': safe_datetime_convert(pipeline.get('created')),
                    'Updated': safe_datetime_convert(pipeline.get('updated')),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching CodePipeline in {region}: {e}")
    
    return all_pipelines


def fetch_glue_databases(session, regions):
    """Fetch AWS Glue databases"""
    logger.info("Fetching Glue databases...")
    all_databases = []
    serial_number = 1
    
    for region in regions:
        try:
            glue = session.client('glue', region_name=region)
            databases = glue.get_databases()['DatabaseList']
            
            for db in databases:
                all_databases.append({
                    'Sr. No.': serial_number,
                    'Name': db['Name'],
                    'Description': db.get('Description', 'N/A'),
                    'CreateTime': safe_datetime_convert(db.get('CreateTime')),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Glue in {region}: {e}")
    
    return all_databases


def fetch_backup_plans(session, regions):
    """Fetch AWS Backup plans"""
    logger.info("Fetching Backup plans...")
    all_plans = []
    serial_number = 1
    
    for region in regions:
        try:
            backup = session.client('backup', region_name=region)
            plans = backup.list_backup_plans()['BackupPlansList']
            
            for plan in plans:
                all_plans.append({
                    'Sr. No.': serial_number,
                    'BackupPlanName': plan['BackupPlanName'],
                    'BackupPlanId': plan['BackupPlanId'],
                    'VersionId': plan.get('VersionId', 'N/A'),
                    'CreationDate': safe_datetime_convert(plan.get('CreationDate')),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Backup plans in {region}: {e}")
    
    return all_plans


def fetch_amplify_apps(session, regions):
    """Fetch AWS Amplify apps"""
    logger.info("Fetching Amplify apps...")
    all_apps = []
    serial_number = 1
    
    for region in regions:
        try:
            amplify = session.client('amplify', region_name=region)
            apps = amplify.list_apps()['apps']
            
            for app in apps:
                all_apps.append({
                    'Sr. No.': serial_number,
                    'Name': app['name'],
                    'AppId': app['appId'],
                    'AppArn': app['appArn'],
                    'Platform': app.get('platform', 'N/A'),
                    'CreateTime': safe_datetime_convert(app.get('createTime')),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Amplify in {region}: {e}")
    
    return all_apps


def fetch_waf_web_acls(session, regions):
    """Fetch WAF Web ACLs"""
    logger.info("Fetching WAF Web ACLs...")
    all_acls = []
    serial_number = 1
    
    for region in regions:
        try:
            wafv2 = session.client('wafv2', region_name=region)
            
            # Regional ACLs
            acls = wafv2.list_web_acls(Scope='REGIONAL')['WebACLs']
            for acl in acls:
                all_acls.append({
                    'Sr. No.': serial_number,
                    'Name': acl['Name'],
                    'Id': acl['Id'],
                    'ARN': acl['ARN'],
                    'Scope': 'REGIONAL',
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching WAF in {region}: {e}")
    
    # CloudFront (Global) ACLs
    try:
        wafv2_global = session.client('wafv2', region_name='us-east-1')
        acls = wafv2_global.list_web_acls(Scope='CLOUDFRONT')['WebACLs']
        for acl in acls:
            all_acls.append({
                'Sr. No.': serial_number,
                'Name': acl['Name'],
                'Id': acl['Id'],
                'ARN': acl['ARN'],
                'Scope': 'CLOUDFRONT',
                'Region': 'global'
            })
            serial_number += 1
    except Exception as e:
        logger.error(f"Error fetching WAF CloudFront ACLs: {e}")
    
    return all_acls


def fetch_cognito_user_pools(session, regions):
    """Fetch Cognito User Pools"""
    logger.info("Fetching Cognito User Pools...")
    all_pools = []
    serial_number = 1
    
    for region in regions:
        try:
            cognito = session.client('cognito-idp', region_name=region)
            pools = cognito.list_user_pools(MaxResults=60)['UserPools']
            
            for pool in pools:
                all_pools.append({
                    'Sr. No.': serial_number,
                    'Name': pool['Name'],
                    'Id': pool['Id'],
                    'CreationDate': safe_datetime_convert(pool.get('CreationDate')),
                    'LastModifiedDate': safe_datetime_convert(pool.get('LastModifiedDate')),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Cognito in {region}: {e}")
    
    return all_pools


def fetch_config_rules(session, regions):
    """Fetch AWS Config rules"""
    logger.info("Fetching Config rules...")
    all_rules = []
    serial_number = 1
    
    for region in regions:
        try:
            config = session.client('config', region_name=region)
            paginator = config.get_paginator('describe_config_rules')
            
            for page in paginator.paginate():
                for rule in page['ConfigRules']:
                    all_rules.append({
                        'Sr. No.': serial_number,
                        'ConfigRuleName': rule['ConfigRuleName'],
                        'ConfigRuleArn': rule.get('ConfigRuleArn', 'N/A'),
                        'ConfigRuleState': rule.get('ConfigRuleState', 'N/A'),
                        'Source': rule.get('Source', {}).get('Owner', 'N/A'),
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Config in {region}: {e}")
    
    return all_rules


def fetch_ssm_parameters(session, regions):
    """Fetch Systems Manager parameters"""
    logger.info("Fetching SSM parameters...")
    all_parameters = []
    serial_number = 1
    
    for region in regions:
        try:
            ssm = session.client('ssm', region_name=region)
            paginator = ssm.get_paginator('describe_parameters')
            
            # Use explicit pagination config to ensure all parameters are fetched
            page_iterator = paginator.paginate(
                PaginationConfig={
                    'MaxItems': None,  # No limit on total items
                    'PageSize': 50     # Fetch 50 parameters per page
                }
            )
            
            for page in page_iterator:
                for param in page['Parameters']:
                    all_parameters.append({
                        'Sr. No.': serial_number,
                        'Name': param['Name'],
                        'Type': param.get('Type', 'N/A'),
                        'LastModifiedDate': safe_datetime_convert(param.get('LastModifiedDate')),
                        'Version': param.get('Version', 'N/A'),
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching SSM in {region}: {e}")
    
    logger.info(f"Total SSM parameters fetched: {len(all_parameters)}")
    return all_parameters


def fetch_acm_certificates(session, regions):
    """Fetch ACM certificates"""
    logger.info("Fetching ACM certificates...")
    all_certs = []
    serial_number = 1
    
    for region in regions:
        try:
            acm = session.client('acm', region_name=region)
            paginator = acm.get_paginator('list_certificates')
            
            for page in paginator.paginate():
                for cert in page['CertificateSummaryList']:
                    all_certs.append({
                        'Sr. No.': serial_number,
                        'DomainName': cert['DomainName'],
                        'CertificateArn': cert['CertificateArn'],
                        'Status': cert.get('Status', 'N/A'),
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching ACM in {region}: {e}")
    
    return all_certs


def fetch_ecs_services(session, regions):
    """Fetch ECS Services"""
    logger.info("Fetching ECS Services...")
    all_services = []
    serial_number = 1
    
    for region in regions:
        try:
            ecs = session.client('ecs', region_name=region)
            
            # Get all clusters first
            cluster_paginator = ecs.get_paginator('list_clusters')
            for cluster_page in cluster_paginator.paginate():
                for cluster_arn in cluster_page['clusterArns']:
                    try:
                        # Get all services for this cluster with pagination
                        service_paginator = ecs.get_paginator('list_services')
                        for service_page in service_paginator.paginate(cluster=cluster_arn):
                            service_arns = service_page['serviceArns']
                            
                            if service_arns:
                                # Describe services in batches of 10 (AWS limit)
                                for i in range(0, len(service_arns), 10):
                                    batch = service_arns[i:i+10]
                                    services = ecs.describe_services(cluster=cluster_arn, services=batch)['services']
                                    
                                    for service in services:
                                        all_services.append({
                                            'Sr. No.': serial_number,
                                            'ServiceName': service['serviceName'],
                                            'ClusterArn': cluster_arn.split('/')[-1],
                                            'Status': service.get('status', 'N/A'),
                                            'DesiredCount': service.get('desiredCount', 0),
                                            'RunningCount': service.get('runningCount', 0),
                                            'LaunchType': service.get('launchType', 'N/A'),
                                            'Region': region
                                        })
                                        serial_number += 1
                    except Exception as e:
                        logger.debug(f"Error fetching services for cluster {cluster_arn}: {e}")
        except Exception as e:
            logger.error(f"Error fetching ECS Services in {region}: {e}")
    
    return all_services


def fetch_efs_file_systems(session, regions):
    """Fetch EFS file systems"""
    logger.info("Fetching EFS file systems...")
    all_fs = []
    serial_number = 1
    
    for region in regions:
        try:
            efs = session.client('efs', region_name=region)
            file_systems = efs.describe_file_systems()['FileSystems']
            
            for fs in file_systems:
                all_fs.append({
                    'Sr. No.': serial_number,
                    'FileSystemId': fs['FileSystemId'],
                    'Name': fs.get('Name', 'N/A'),
                    'LifeCycleState': fs.get('LifeCycleState', 'N/A'),
                    'SizeInBytes': fs.get('SizeInBytes', {}).get('Value', 0),
                    'NumberOfMountTargets': fs.get('NumberOfMountTargets', 0),
                    'CreationTime': safe_datetime_convert(fs.get('CreationTime')),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching EFS in {region}: {e}")
    
    return all_fs


def fetch_elastic_ips(session, regions):
    """Fetch Elastic IPs"""
    logger.info("Fetching Elastic IPs...")
    all_eips = []
    serial_number = 1
    
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            addresses = ec2.describe_addresses()['Addresses']
            
            for addr in addresses:
                all_eips.append({
                    'Sr. No.': serial_number,
                    'PublicIp': addr.get('PublicIp', 'N/A'),
                    'AllocationId': addr.get('AllocationId', 'N/A'),
                    'AssociationId': addr.get('AssociationId', 'N/A'),
                    'InstanceId': addr.get('InstanceId', 'N/A'),
                    'NetworkInterfaceId': addr.get('NetworkInterfaceId', 'N/A'),
                    'PrivateIpAddress': addr.get('PrivateIpAddress', 'N/A'),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching EIPs in {region}: {e}")
    
    return all_eips


def fetch_vpc_endpoints(session, regions):
    """Fetch VPC Endpoints"""
    logger.info("Fetching VPC Endpoints...")
    all_endpoints = []
    serial_number = 1
    
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            endpoints = ec2.describe_vpc_endpoints()['VpcEndpoints']
            
            for endpoint in endpoints:
                all_endpoints.append({
                    'Sr. No.': serial_number,
                    'VpcEndpointId': endpoint['VpcEndpointId'],
                    'VpcId': endpoint.get('VpcId', 'N/A'),
                    'ServiceName': endpoint.get('ServiceName', 'N/A'),
                    'State': endpoint.get('State', 'N/A'),
                    'VpcEndpointType': endpoint.get('VpcEndpointType', 'N/A'),
                    'CreationTimestamp': safe_datetime_convert(endpoint.get('CreationTimestamp')),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching VPC Endpoints in {region}: {e}")
    
    return all_endpoints


def fetch_internet_gateways(session, regions):
    """Fetch Internet Gateways"""
    logger.info("Fetching Internet Gateways...")
    all_igws = []
    serial_number = 1
    
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            igws = ec2.describe_internet_gateways()['InternetGateways']
            
            for igw in igws:
                tags = {tag['Key']: tag['Value'] for tag in igw.get('Tags', [])}
                attachments = igw.get('Attachments', [])
                
                all_igws.append({
                    'Sr. No.': serial_number,
                    'InternetGatewayId': igw['InternetGatewayId'],
                    'Name': tags.get('Name', 'N/A'),
                    'VpcId': attachments[0]['VpcId'] if attachments else 'N/A',
                    'State': attachments[0]['State'] if attachments else 'N/A',
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching IGWs in {region}: {e}")
    
    return all_igws


def fetch_nat_gateways(session, regions):
    """Fetch NAT Gateways"""
    logger.info("Fetching NAT Gateways...")
    all_natgws = []
    serial_number = 1
    
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            natgws = ec2.describe_nat_gateways()['NatGateways']
            
            for natgw in natgws:
                tags = {tag['Key']: tag['Value'] for tag in natgw.get('Tags', [])}
                
                all_natgws.append({
                    'Sr. No.': serial_number,
                    'NatGatewayId': natgw['NatGatewayId'],
                    'Name': tags.get('Name', 'N/A'),
                    'VpcId': natgw.get('VpcId', 'N/A'),
                    'SubnetId': natgw.get('SubnetId', 'N/A'),
                    'State': natgw.get('State', 'N/A'),
                    'CreatedTime': safe_datetime_convert(natgw.get('CreateTime')),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching NAT Gateways in {region}: {e}")
    
    return all_natgws


def fetch_network_interfaces(session, regions):
    """Fetch Network Interfaces (ENI)"""
    logger.info("Fetching Network Interfaces...")
    all_enis = []
    serial_number = 1
    
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            enis = ec2.describe_network_interfaces()['NetworkInterfaces']
            
            for eni in enis:
                tags = {tag['Key']: tag['Value'] for tag in eni.get('TagSet', [])}
                
                all_enis.append({
                    'Sr. No.': serial_number,
                    'NetworkInterfaceId': eni['NetworkInterfaceId'],
                    'Name': tags.get('Name', 'N/A'),
                    'Status': eni.get('Status', 'N/A'),
                    'VpcId': eni.get('VpcId', 'N/A'),
                    'SubnetId': eni.get('SubnetId', 'N/A'),
                    'PrivateIpAddress': eni.get('PrivateIpAddress', 'N/A'),
                    'InterfaceType': eni.get('InterfaceType', 'N/A'),
                    'Attachment': eni.get('Attachment', {}).get('InstanceId', 'N/A'),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching ENIs in {region}: {e}")
    
    return all_enis


def fetch_key_pairs(session, regions):
    """Fetch EC2 Key Pairs"""
    logger.info("Fetching Key Pairs...")
    all_keys = []
    serial_number = 1
    
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            keys = ec2.describe_key_pairs()['KeyPairs']
            
            for key in keys:
                all_keys.append({
                    'Sr. No.': serial_number,
                    'KeyName': key['KeyName'],
                    'KeyPairId': key.get('KeyPairId', 'N/A'),
                    'KeyFingerprint': key.get('KeyFingerprint', 'N/A'),
                    'KeyType': key.get('KeyType', 'N/A'),
                    'CreateTime': safe_datetime_convert(key.get('CreateTime')),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Key Pairs in {region}: {e}")
    
    return all_keys


def fetch_transit_gateways(session, regions):
    """Fetch Transit Gateways"""
    logger.info("Fetching Transit Gateways...")
    all_tgws = []
    serial_number = 1
    
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            tgws = ec2.describe_transit_gateways()['TransitGateways']
            
            for tgw in tgws:
                tags = {tag['Key']: tag['Value'] for tag in tgw.get('Tags', [])}
                
                all_tgws.append({
                    'Sr. No.': serial_number,
                    'TransitGatewayId': tgw['TransitGatewayId'],
                    'Name': tags.get('Name', 'N/A'),
                    'State': tgw.get('State', 'N/A'),
                    'OwnerId': tgw.get('OwnerId', 'N/A'),
                    'CreationTime': safe_datetime_convert(tgw.get('CreationTime')),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Transit Gateways in {region}: {e}")
    
    return all_tgws


def fetch_glue_jobs(session, regions):
    """Fetch AWS Glue Jobs"""
    logger.info("Fetching Glue Jobs...")
    all_jobs = []
    serial_number = 1
    
    for region in regions:
        try:
            glue = session.client('glue', region_name=region)
            paginator = glue.get_paginator('get_jobs')
            
            for page in paginator.paginate():
                for job in page['Jobs']:
                    all_jobs.append({
                        'Sr. No.': serial_number,
                        'Name': job['Name'],
                        'Role': job.get('Role', 'N/A'),
                        'CreatedOn': safe_datetime_convert(job.get('CreatedOn')),
                        'LastModifiedOn': safe_datetime_convert(job.get('LastModifiedOn')),
                        'MaxRetries': job.get('MaxRetries', 0),
                        'Timeout': job.get('Timeout', 0),
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Glue Jobs in {region}: {e}")
    
    return all_jobs


def fetch_opensearch_collections(session, regions):
    """Fetch OpenSearch Serverless Collections"""
    logger.info("Fetching OpenSearch Serverless Collections...")
    all_collections = []
    serial_number = 1
    
    for region in regions:
        try:
            aoss = session.client('opensearchserverless', region_name=region)
            collections = aoss.list_collections()['collectionSummaries']
            
            for collection in collections:
                all_collections.append({
                    'Sr. No.': serial_number,
                    'Name': collection.get('name', 'N/A'),
                    'Id': collection.get('id', 'N/A'),
                    'Status': collection.get('status', 'N/A'),
                    'Arn': collection.get('arn', 'N/A'),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching OpenSearch Collections in {region}: {e}")
    
    return all_collections


def fetch_ses_identities(session, regions):
    """Fetch SES Identities"""
    logger.info("Fetching SES Identities...")
    all_identities = []
    serial_number = 1
    
    for region in regions:
        try:
            ses = session.client('ses', region_name=region)
            identities = ses.list_identities()['Identities']
            
            for identity in identities:
                all_identities.append({
                    'Sr. No.': serial_number,
                    'Identity': identity,
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching SES in {region}: {e}")
    
    return all_identities


def fetch_cognito_identity_pools(session, regions):
    """Fetch Cognito Identity Pools"""
    logger.info("Fetching Cognito Identity Pools...")
    all_pools = []
    serial_number = 1
    
    for region in regions:
        try:
            cognito_identity = session.client('cognito-identity', region_name=region)
            pools = cognito_identity.list_identity_pools(MaxResults=60)['IdentityPools']
            
            for pool in pools:
                all_pools.append({
                    'Sr. No.': serial_number,
                    'IdentityPoolId': pool['IdentityPoolId'],
                    'IdentityPoolName': pool['IdentityPoolName'],
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Cognito Identity Pools in {region}: {e}")
    
    return all_pools


def fetch_direct_connect_connections(session, regions):
    """Fetch Direct Connect Connections"""
    logger.info("Fetching Direct Connect Connections...")
    all_connections = []
    serial_number = 1
    
    for region in regions:
        try:
            dx = session.client('directconnect', region_name=region)
            connections = dx.describe_connections()['connections']
            
            for conn in connections:
                all_connections.append({
                    'Sr. No.': serial_number,
                    'ConnectionId': conn['connectionId'],
                    'ConnectionName': conn.get('connectionName', 'N/A'),
                    'ConnectionState': conn.get('connectionState', 'N/A'),
                    'Location': conn.get('location', 'N/A'),
                    'Bandwidth': conn.get('bandwidth', 'N/A'),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Direct Connect in {region}: {e}")
    
    return all_connections


def fetch_cloudwatch_log_groups(session, regions):
    """Fetch CloudWatch Log Groups"""
    logger.info("Fetching CloudWatch Log Groups...")
    all_log_groups = []
    serial_number = 1
    
    for region in regions:
        try:
            logs = session.client('logs', region_name=region)
            paginator = logs.get_paginator('describe_log_groups')
            
            for page in paginator.paginate():
                for lg in page['logGroups']:
                    all_log_groups.append({
                        'Sr. No.': serial_number,
                        'LogGroupName': lg['logGroupName'],
                        'CreationTime': safe_datetime_convert(datetime.fromtimestamp(lg.get('creationTime', 0) / 1000)),
                        'StoredBytes': lg.get('storedBytes', 0),
                        'RetentionInDays': lg.get('retentionInDays', 'Never Expire'),
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching CloudWatch Log Groups in {region}: {e}")
    
    return all_log_groups


def fetch_grafana_workspaces(session, regions):
    """Fetch Managed Grafana Workspaces"""
    logger.info("Fetching Grafana Workspaces...")
    all_workspaces = []
    serial_number = 1
    
    for region in regions:
        try:
            grafana = session.client('grafana', region_name=region)
            workspaces = grafana.list_workspaces()['workspaces']
            
            for ws in workspaces:
                all_workspaces.append({
                    'Sr. No.': serial_number,
                    'Id': ws['id'],
                    'Name': ws.get('name', 'N/A'),
                    'Status': ws.get('status', 'N/A'),
                    'Endpoint': ws.get('endpoint', 'N/A'),
                    'GrafanaVersion': ws.get('grafanaVersion', 'N/A'),
                    'Created': safe_datetime_convert(ws.get('created')),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Grafana in {region}: {e}")
    
    return all_workspaces


def fetch_airflow_environments(session, regions):
    """Fetch MWAA (Airflow) Environments"""
    logger.info("Fetching MWAA Environments...")
    all_envs = []
    serial_number = 1
    
    for region in regions:
        try:
            mwaa = session.client('mwaa', region_name=region)
            envs = mwaa.list_environments()['Environments']
            
            for env_name in envs:
                try:
                    env = mwaa.get_environment(Name=env_name)['Environment']
                    all_envs.append({
                        'Sr. No.': serial_number,
                        'Name': env['Name'],
                        'Status': env.get('Status', 'N/A'),
                        'AirflowVersion': env.get('AirflowVersion', 'N/A'),
                        'WebserverUrl': env.get('WebserverUrl', 'N/A'),
                        'CreatedAt': safe_datetime_convert(env.get('CreatedAt')),
                        'Region': region
                    })
                    serial_number += 1
                except:
                    pass
        except Exception as e:
            logger.error(f"Error fetching MWAA in {region}: {e}")
    
    return all_envs


def fetch_prometheus_workspaces(session, regions):
    """Fetch Amazon Managed Prometheus Workspaces"""
    logger.info("Fetching Prometheus Workspaces...")
    all_workspaces = []
    serial_number = 1
    
    for region in regions:
        try:
            amp = session.client('amp', region_name=region)
            workspaces = amp.list_workspaces()['workspaces']
            
            for ws in workspaces:
                all_workspaces.append({
                    'Sr. No.': serial_number,
                    'WorkspaceId': ws['workspaceId'],
                    'Alias': ws.get('alias', 'N/A'),
                    'Status': ws.get('status', {}).get('statusCode', 'N/A'),
                    'PrometheusEndpoint': ws.get('prometheusEndpoint', 'N/A'),
                    'CreatedAt': safe_datetime_convert(ws.get('createdAt')),
                    'Region': region
                })
                serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching Prometheus in {region}: {e}")
    
    return all_workspaces


def fetch_sagemaker_notebooks(session, regions):
    """Fetch SageMaker Notebook Instances"""
    logger.info("Fetching SageMaker Notebooks...")
    all_notebooks = []
    serial_number = 1
    
    for region in regions:
        try:
            sagemaker = session.client('sagemaker', region_name=region)
            paginator = sagemaker.get_paginator('list_notebook_instances')
            
            for page in paginator.paginate():
                for nb in page['NotebookInstances']:
                    all_notebooks.append({
                        'Sr. No.': serial_number,
                        'NotebookInstanceName': nb['NotebookInstanceName'],
                        'NotebookInstanceArn': nb['NotebookInstanceArn'],
                        'InstanceType': nb.get('InstanceType', 'N/A'),
                        'NotebookInstanceStatus': nb.get('NotebookInstanceStatus', 'N/A'),
                        'CreationTime': safe_datetime_convert(nb.get('CreationTime')),
                        'LastModifiedTime': safe_datetime_convert(nb.get('LastModifiedTime')),
                        'Region': region
                    })
                    serial_number += 1
        except Exception as e:
            logger.error(f"Error fetching SageMaker in {region}: {e}")
    
    return all_notebooks


# Service dispatcher - maps service names to fetch functions
SERVICE_FETCHERS = {
    'ec2_instances': fetch_ec2_instances,
    'ebs_volumes': fetch_ebs_volumes,
    'ecs_clusters': fetch_ecs_clusters,
    'ecr_repositories': fetch_ecr_repositories,
    'lambda_functions': fetch_lambda_functions,
    's3_buckets': fetch_s3_buckets,
    'rds_instances': fetch_rds_instances,
    'dynamodb_tables': fetch_dynamodb_tables,
    'elasticache_clusters': fetch_elasticache_clusters,
    'opensearch_domains': fetch_opensearch_domains,
    'vpcs': fetch_vpcs,
    'subnets': fetch_subnets,
    'security_groups': fetch_security_groups,
    'load_balancers': fetch_load_balancers,
    'route53_zones': fetch_route53_zones,
    'cloudfront_distributions': fetch_cloudfront_distributions,
    'api_gateways': fetch_api_gateways,
    'cloudformation_stacks': fetch_cloudformation_stacks,
    'cloudtrail_trails': fetch_cloudtrail_trails,
    'cloudwatch_alarms': fetch_cloudwatch_alarms,
    'eventbridge_rules': fetch_eventbridge_rules,
    'kms_keys': fetch_kms_keys,
    'secrets': fetch_secrets,
    'sns_topics': fetch_sns_topics,
    'sqs_queues': fetch_sqs_queues,
}


# ============================================================================
# EXPORT TO EXCEL
# ============================================================================

def export_to_excel(data_dict, filename):
    """Export all data to Excel with each service in a different sheet"""
    logger.info(f"Exporting data to {filename}...")
    
    try:
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            for sheet_name, data in data_dict.items():
                if data:
                    df = pd.DataFrame(data)
                    
                    # Convert any remaining datetime columns
                    for col in df.columns:
                        if df[col].dtype == 'object':
                            sample = df[col].dropna().head(1)
                            if not sample.empty:
                                sample_val = sample.iloc[0]
                                if hasattr(sample_val, 'strftime'):
                                    df[col] = df[col].apply(safe_datetime_convert)
                    
                    df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
                    logger.info(f"  - {sheet_name}: {len(data)} records")
        
        logger.info(f"Successfully exported to {filename}")
        return True
    except Exception as e:
        logger.error(f"Error exporting to Excel: {e}")
        return False


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution function"""
    logger.info("="*60)
    logger.info("AWS Dynamic Inventory Collection")
    logger.info("="*60)
    
    # Load services from file
    services_from_file = load_services_from_file()
    
    if services_from_file:
        logger.info(f"\nServices to collect (from aws_services.txt):")
        for service in services_from_file:
            mapped = map_service_to_fetcher(service)
            if mapped:
                logger.info(f"  ✓ {service} -> {mapped}")
            else:
                logger.info(f"  ⚠ {service} -> (not yet supported)")
        print()
    
    # Initialize AWS session
    try:
        session = boto3.Session()
        logger.info("AWS session initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize AWS session: {e}")
        return 1
    
    # Get all regions
    try:
        ec2 = session.client('ec2', region_name='us-east-1')
        regions = [region['RegionName'] for region in ec2.describe_regions()['Regions']]
        logger.info(f"Scanning {len(regions)} regions")
    except Exception as e:
        logger.error(f"Failed to get regions: {e}")
        regions = ['us-east-1']
    
    # Collect all data
    data_to_export = {}
    
    # Determine which services to fetch
    services_to_fetch = set()
    
    if services_from_file:
        # Use services from file
        for service in services_from_file:
            mapped = map_service_to_fetcher(service)
            if mapped:
                services_to_fetch.add(mapped)
    
    # Always fetch these core services (even if not in file)
    core_services = {'ec2', 'vpc', 'subnets', 'security_groups', 's3', 'iam'}
    services_to_fetch.update(core_services)
    
    logger.info("\nFetching AWS resources...")
    logger.info("="*60)
    
    # Fetch based on discovered services
    if 'ec2' in services_to_fetch:
        data_to_export['EC2_Instances'] = fetch_ec2_instances(session, regions)
    
    if 'ebs' in services_to_fetch or 'ec2' in services_to_fetch:
        data_to_export['EBS_Volumes'] = fetch_ebs_volumes(session, regions)
    
    if 'ecs' in services_to_fetch:
        data_to_export['ECS_Clusters'] = fetch_ecs_clusters(session, regions)
        data_to_export['ECS_Services'] = fetch_ecs_services(session, regions)
    
    if 'ecr' in services_to_fetch:
        data_to_export['ECR_Repositories'] = fetch_ecr_repositories(session, regions)
    
    if 'lambda' in services_to_fetch:
        data_to_export['Lambda'] = fetch_lambda_functions(session, regions)
    
    if 's3' in services_to_fetch:
        data_to_export['S3'] = fetch_s3_buckets(session)
    
    if 'efs' in services_to_fetch:
        data_to_export['EFS'] = fetch_efs_file_systems(session, regions)
    
    if 'rds' in services_to_fetch:
        data_to_export['RDS'] = fetch_rds_instances(session, regions)
    
    if 'dynamodb' in services_to_fetch:
        data_to_export['DynamoDB'] = fetch_dynamodb_tables(session, regions)
    
    if 'dax' in services_to_fetch:
        data_to_export['DAX_Clusters'] = fetch_dax_clusters(session, regions)
    
    if 'elasticache' in services_to_fetch:
        data_to_export['ElastiCache'] = fetch_elasticache_clusters(session, regions)
    
    if 'opensearch' in services_to_fetch:
        data_to_export['OpenSearch'] = fetch_opensearch_domains(session, regions)
        data_to_export['OpenSearch_Collections'] = fetch_opensearch_collections(session, regions)
    
    # Network (always fetch core, conditionally fetch others)
    data_to_export['VPC'] = fetch_vpcs(session, regions)
    data_to_export['Subnets'] = fetch_subnets(session, regions)
    data_to_export['Security_Groups'] = fetch_security_groups(session, regions)
    data_to_export['Elastic_IPs'] = fetch_elastic_ips(session, regions)
    data_to_export['VPC_Endpoints'] = fetch_vpc_endpoints(session, regions)
    data_to_export['Internet_Gateways'] = fetch_internet_gateways(session, regions)
    data_to_export['NAT_Gateways'] = fetch_nat_gateways(session, regions)
    data_to_export['Network_Interfaces'] = fetch_network_interfaces(session, regions)
    data_to_export['Key_Pairs'] = fetch_key_pairs(session, regions)
    
    if 'directconnect' in services_to_fetch:
        data_to_export['Direct_Connect'] = fetch_direct_connect_connections(session, regions)
    
    # Transit Gateway
    data_to_export['Transit_Gateways'] = fetch_transit_gateways(session, regions)
    
    if 'load_balancers' in services_to_fetch:
        data_to_export['Load_Balancers'] = fetch_load_balancers(session, regions)
    
    if 'route53' in services_to_fetch:
        data_to_export['Route53'] = fetch_route53_zones(session)
    
    if 'cloudfront' in services_to_fetch:
        data_to_export['CloudFront'] = fetch_cloudfront_distributions(session)
    
    if 'api_gateway' in services_to_fetch:
        data_to_export['API_Gateway'] = fetch_api_gateways(session, regions)
    
    # Management
    if 'cloudformation' in services_to_fetch:
        data_to_export['CloudFormation'] = fetch_cloudformation_stacks(session, regions)
    
    if 'cloudtrail' in services_to_fetch:
        data_to_export['CloudTrail'] = fetch_cloudtrail_trails(session, regions)
    
    if 'cloudwatch' in services_to_fetch:
        data_to_export['CloudWatch_Alarms'] = fetch_cloudwatch_alarms(session, regions)
        data_to_export['CloudWatch_LogGroups'] = fetch_cloudwatch_log_groups(session, regions)
    
    if 'eventbridge' in services_to_fetch:
        data_to_export['EventBridge'] = fetch_eventbridge_rules(session, regions)
    
    # Security
    if 'kms' in services_to_fetch:
        data_to_export['KMS_Keys'] = fetch_kms_keys(session, regions)
    
    if 'secrets' in services_to_fetch:
        data_to_export['Secrets_Manager'] = fetch_secrets(session, regions)
    
    if 'acm' in services_to_fetch:
        data_to_export['ACM_Certificates'] = fetch_acm_certificates(session, regions)
    
    if 'waf' in services_to_fetch:
        data_to_export['WAF_WebACLs'] = fetch_waf_web_acls(session, regions)
    
    # Application Integration
    if 'sns' in services_to_fetch:
        data_to_export['SNS_Topics'] = fetch_sns_topics(session, regions)
    
    if 'sqs' in services_to_fetch:
        data_to_export['SQS_Queues'] = fetch_sqs_queues(session, regions)
    
    if 'stepfunctions' in services_to_fetch:
        data_to_export['Step_Functions'] = fetch_stepfunctions(session, regions)
    
    if 'mq' in services_to_fetch:
        data_to_export['MQ_Brokers'] = fetch_mq_brokers(session, regions)
    
    if 'kafka' in services_to_fetch:
        data_to_export['MSK_Clusters'] = fetch_kafka_clusters(session, regions)
    
    # Developer Tools
    if 'codebuild' in services_to_fetch:
        data_to_export['CodeBuild_Projects'] = fetch_codebuild_projects(session, regions)
    
    if 'codepipeline' in services_to_fetch:
        data_to_export['CodePipeline'] = fetch_codepipeline_pipelines(session, regions)
    
    # Analytics & Other
    if 'glue' in services_to_fetch:
        data_to_export['Glue_Databases'] = fetch_glue_databases(session, regions)
    
    if 'backup' in services_to_fetch:
        data_to_export['Backup_Plans'] = fetch_backup_plans(session, regions)
    
    if 'amplify' in services_to_fetch:
        data_to_export['Amplify_Apps'] = fetch_amplify_apps(session, regions)
    
    if 'cognito' in services_to_fetch:
        data_to_export['Cognito_UserPools'] = fetch_cognito_user_pools(session, regions)
        data_to_export['Cognito_IdentityPools'] = fetch_cognito_identity_pools(session, regions)
    
    if 'config' in services_to_fetch:
        data_to_export['Config_Rules'] = fetch_config_rules(session, regions)
    
    if 'ssm' in services_to_fetch:
        data_to_export['SSM_Parameters'] = fetch_ssm_parameters(session, regions)
    
    if 'ses' in services_to_fetch:
        data_to_export['SES_Identities'] = fetch_ses_identities(session, regions)
    
    if 'glue' in services_to_fetch:
        data_to_export['Glue_Databases'] = fetch_glue_databases(session, regions)
        data_to_export['Glue_Jobs'] = fetch_glue_jobs(session, regions)
    
    if 'sagemaker' in services_to_fetch:
        data_to_export['SageMaker_Notebooks'] = fetch_sagemaker_notebooks(session, regions)
    
    if 'grafana' in services_to_fetch:
        data_to_export['Grafana_Workspaces'] = fetch_grafana_workspaces(session, regions)
    
    if 'airflow' in services_to_fetch:
        data_to_export['MWAA_Environments'] = fetch_airflow_environments(session, regions)
    
    if 'prometheus' in services_to_fetch:
        data_to_export['Prometheus_Workspaces'] = fetch_prometheus_workspaces(session, regions)
    
    # IAM (always fetch)
    iam_users, iam_roles, iam_policies = fetch_iam_resources(session)
    data_to_export['IAM_Users'] = iam_users
    data_to_export['IAM_Roles'] = iam_roles
    data_to_export['IAM_Policies'] = iam_policies
    
    # Get account info for filename
    account_id, account_name = get_account_info()
    logger.info(f"AWS Account: {account_id} ({account_name})")
    
    # Export to Excel with account info in filename
    output_filename = f"AWS_Inventory_{account_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    success = export_to_excel(data_to_export, output_filename)
    
    if success:
        logger.info("="*60)
        logger.info(f"Inventory completed successfully!")
        logger.info(f"Output file: {output_filename}")
        logger.info("="*60)
        
        # Print summary
        print("\nSummary:")
        total_resources = 0
        for service, data in data_to_export.items():
            if data:
                count = len(data)
                total_resources += count
                print(f"  {service}: {count} resources")
        print(f"\nTotal: {total_resources} resources")
        
        return 0
    else:
        logger.error("Inventory collection failed")
        return 1


if __name__ == '__main__':
    exit(main())

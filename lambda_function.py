#!/usr/bin/env python3
"""
AWS Multi-Account Inventory Lambda Function

Fetches inventory from multiple AWS accounts using credentials stored in SSM Parameter Store,
generates Excel reports, and stores them in S3.

SSM Parameter Store structure (full paths defined in ACCOUNTS below):
  /fetch_inv/dev-access-key
  /fetch_inv/dev-secret-key
  /fetch_inv/uat-access-key
  /fetch_inv/uat-secret-key
  etc.

S3 output structure:
  s3://{bucket}/{year}/{month}/{AccountName}_{env}_YYYYMMDD_HHMMSS.xlsx
"""

import boto3
import pandas as pd
from datetime import datetime
import logging
import os
import io

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
S3_BUCKET = os.environ.get('S3_BUCKET', 'aws-inventory-reports')

# ============================================================================
# ACCOUNT DEFINITIONS
# Add/remove accounts here. Each entry maps an environment name to its
# full SSM parameter paths for access key and secret key.
# ============================================================================
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
    'oldprod': {
        'access_key_ssm': '/fetch_inv/oldprod-access-key',
        'secret_key_ssm': '/fetch_inv/oldprod-secret-key',
    },
    'network': {
        'access_key_ssm': '/fetch_inv/network-access-key',
        'secret_key_ssm': '/fetch_inv/network-secret-key',
    },
    'sharedservice': {
        'access_key_ssm': '/fetch_inv/sharedservice-access-key',
        'secret_key_ssm': '/fetch_inv/sharedservice-secret-key',
    },
}


# ============================================================================
# HELPERS
# ============================================================================

def safe_dt(dt_value):
    """Safely convert datetime to string"""
    if dt_value is None or dt_value == 'N/A':
        return 'N/A'
    if hasattr(dt_value, 'strftime'):
        if hasattr(dt_value, 'tzinfo') and dt_value.tzinfo is not None:
            dt_value = dt_value.replace(tzinfo=None)
        return dt_value.strftime('%Y-%m-%d %H:%M:%S')
    return str(dt_value)


def get_ssm_parameter(ssm_client, name):
    """Get a parameter from SSM Parameter Store"""
    try:
        resp = ssm_client.get_parameter(Name=name, WithDecryption=True)
        return resp['Parameter']['Value']
    except Exception as e:
        logger.error(f"Failed to get SSM parameter {name}: {e}")
        raise


def get_account_session(ssm_client, account_config):
    """Create a boto3 session for a target account using SSM-stored credentials"""
    access_key = get_ssm_parameter(ssm_client, account_config['access_key_ssm'])
    secret_key = get_ssm_parameter(ssm_client, account_config['secret_key_ssm'])
    return boto3.Session(aws_access_key_id=access_key, aws_secret_access_key=secret_key)


def get_account_info(session):
    """Get AWS account ID and alias"""
    try:
        sts = session.client('sts')
        account_id = sts.get_caller_identity()['Account']
        try:
            iam = session.client('iam')
            aliases = iam.list_account_aliases()['AccountAliases']
            account_name = aliases[0] if aliases else account_id
        except Exception:
            account_name = account_id
        return account_id, account_name
    except Exception as e:
        logger.error(f"Error getting account info: {e}")
        return 'Unknown', 'Unknown'


def get_regions(session):
    """Get all enabled AWS regions"""
    try:
        ec2 = session.client('ec2', region_name='us-east-1')
        return [r['RegionName'] for r in ec2.describe_regions()['Regions']]
    except Exception as e:
        logger.error(f"Failed to get regions: {e}")
        return ['us-east-1']


# ============================================================================
# SERVICE FETCHERS
# ============================================================================

def fetch_ec2(session, regions):
    logger.info("Fetching EC2 instances...")
    items = []
    sn = 1
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            for res in ec2.describe_instances()['Reservations']:
                for i in res['Instances']:
                    tags = {t['Key']: t['Value'] for t in i.get('Tags', [])}
                    vols = [b['Ebs']['VolumeId'] for b in i.get('BlockDeviceMappings', []) if 'Ebs' in b]
                    items.append({
                        'Sr. No': sn,
                        'InstanceId': i['InstanceId'],
                        'Name': tags.get('Name', 'N/A'),
                        'State': i['State']['Name'],
                        'Type': i['InstanceType'],
                        'AZ': i['Placement']['AvailabilityZone'],
                        'PublicIP': i.get('PublicIpAddress', 'N/A'),
                        'PrivateIP': i.get('PrivateIpAddress', 'N/A'),
                        'VpcId': i.get('VpcId', 'N/A'),
                        'SubnetId': i.get('SubnetId', 'N/A'),
                        'Volumes': ','.join(vols) or 'N/A',
                        'SecurityGroups': ','.join(sg['GroupName'] for sg in i.get('SecurityGroups', [])),
                        'KeyName': i.get('KeyName', 'N/A'),
                        'Region': region
                    })
                    sn += 1
        except Exception as e:
            logger.error(f"EC2 error in {region}: {e}")
    return items


def fetch_ebs(session, regions):
    logger.info("Fetching EBS volumes...")
    items = []
    sn = 1
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            for v in ec2.describe_volumes()['Volumes']:
                tags = {t['Key']: t['Value'] for t in v.get('Tags', [])}
                att = v.get('Attachments', [])
                items.append({
                    'Sr. No': sn, 'VolumeId': v['VolumeId'], 'Name': tags.get('Name', 'N/A'),
                    'Size(GB)': v['Size'], 'Type': v['VolumeType'], 'State': v['State'],
                    'AZ': v['AvailabilityZone'], 'Encrypted': v['Encrypted'],
                    'AttachedTo': att[0]['InstanceId'] if att else 'N/A', 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"EBS error in {region}: {e}")
    return items


def fetch_ecs(session, regions):
    logger.info("Fetching ECS clusters & services...")
    clusters_out, services_out = [], []
    csn, ssn = 1, 1
    for region in regions:
        try:
            ecs = session.client('ecs', region_name=region)
            cluster_arns = ecs.list_clusters()['clusterArns']
            if not cluster_arns:
                continue
            for c in ecs.describe_clusters(clusters=cluster_arns)['clusters']:
                clusters_out.append({
                    'Sr. No': csn, 'ClusterName': c['clusterName'], 'Status': c['status'],
                    'RunningTasks': c.get('runningTasksCount', 0),
                    'ActiveServices': c.get('activeServicesCount', 0), 'Region': region
                })
                csn += 1
            # Services
            for carn in cluster_arns:
                try:
                    svc_arns = ecs.list_services(cluster=carn)['serviceArns']
                    if svc_arns:
                        for i in range(0, len(svc_arns), 10):
                            for s in ecs.describe_services(cluster=carn, services=svc_arns[i:i+10])['services']:
                                services_out.append({
                                    'Sr. No': ssn, 'ServiceName': s['serviceName'],
                                    'Cluster': carn.split('/')[-1], 'Status': s.get('status', 'N/A'),
                                    'Desired': s.get('desiredCount', 0), 'Running': s.get('runningCount', 0),
                                    'LaunchType': s.get('launchType', 'N/A'), 'Region': region
                                })
                                ssn += 1
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"ECS error in {region}: {e}")
    return clusters_out, services_out


def fetch_ecr(session, regions):
    logger.info("Fetching ECR repositories...")
    items = []
    sn = 1
    for region in regions:
        try:
            ecr = session.client('ecr', region_name=region)
            for page in ecr.get_paginator('describe_repositories').paginate():
                for r in page['repositories']:
                    items.append({
                        'Sr. No': sn, 'Name': r['repositoryName'], 'URI': r['repositoryUri'],
                        'Created': safe_dt(r.get('createdAt')), 'Region': region
                    })
                    sn += 1
        except Exception as e:
            logger.error(f"ECR error in {region}: {e}")
    return items


def fetch_lambda(session, regions):
    logger.info("Fetching Lambda functions...")
    items = []
    sn = 1
    for region in regions:
        try:
            lam = session.client('lambda', region_name=region)
            for page in lam.get_paginator('list_functions').paginate():
                for f in page['Functions']:
                    items.append({
                        'Sr. No': sn, 'FunctionName': f['FunctionName'],
                        'Runtime': f.get('Runtime', 'N/A'), 'Memory': f.get('MemorySize', 0),
                        'Timeout': f.get('Timeout', 0), 'Region': region
                    })
                    sn += 1
        except Exception as e:
            logger.error(f"Lambda error in {region}: {e}")
    return items


def fetch_s3(session):
    logger.info("Fetching S3 buckets...")
    items = []
    sn = 1
    try:
        s3 = session.client('s3')
        for b in s3.list_buckets()['Buckets']:
            name = b['Name']
            try:
                loc = s3.get_bucket_location(Bucket=name)['LocationConstraint'] or 'us-east-1'
            except Exception:
                loc = 'N/A'
            items.append({
                'Sr. No': sn, 'BucketName': name, 'Region': loc,
                'Created': safe_dt(b['CreationDate'])
            })
            sn += 1
    except Exception as e:
        logger.error(f"S3 error: {e}")
    return items


def fetch_rds(session, regions):
    logger.info("Fetching RDS instances...")
    items = []
    sn = 1
    for region in regions:
        try:
            rds = session.client('rds', region_name=region)
            for db in rds.describe_db_instances()['DBInstances']:
                items.append({
                    'Sr. No': sn, 'DBIdentifier': db['DBInstanceIdentifier'],
                    'Endpoint': db.get('Endpoint', {}).get('Address', 'N/A'),
                    'Engine': db['Engine'], 'Version': db['EngineVersion'],
                    'Class': db['DBInstanceClass'], 'Storage(GB)': db['AllocatedStorage'],
                    'MultiAZ': db['MultiAZ'], 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"RDS error in {region}: {e}")
    return items


def fetch_dynamodb(session, regions):
    logger.info("Fetching DynamoDB tables...")
    items = []
    sn = 1
    for region in regions:
        try:
            ddb = session.client('dynamodb', region_name=region)
            for page in ddb.get_paginator('list_tables').paginate():
                for tname in page['TableNames']:
                    try:
                        t = ddb.describe_table(TableName=tname)['Table']
                        items.append({
                            'Sr. No': sn, 'TableName': t['TableName'], 'Status': t['TableStatus'],
                            'Items': t.get('ItemCount', 0), 'SizeBytes': t.get('TableSizeBytes', 0),
                            'Region': region
                        })
                        sn += 1
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"DynamoDB error in {region}: {e}")
    return items


def fetch_elasticache(session, regions):
    logger.info("Fetching ElastiCache clusters...")
    items = []
    sn = 1
    for region in regions:
        try:
            ec = session.client('elasticache', region_name=region)
            for c in ec.describe_cache_clusters()['CacheClusters']:
                items.append({
                    'Sr. No': sn, 'ClusterId': c['CacheClusterId'],
                    'Engine': c.get('Engine', 'N/A'), 'NodeType': c.get('CacheNodeType', 'N/A'),
                    'Status': c.get('CacheClusterStatus', 'N/A'),
                    'Nodes': c.get('NumCacheNodes', 0), 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"ElastiCache error in {region}: {e}")
    return items


def fetch_opensearch(session, regions):
    logger.info("Fetching OpenSearch domains...")
    items = []
    sn = 1
    for region in regions:
        try:
            os_client = session.client('opensearch', region_name=region)
            for d in os_client.list_domain_names()['DomainNames']:
                try:
                    dom = os_client.describe_domain(DomainName=d['DomainName'])['DomainStatus']
                    items.append({
                        'Sr. No': sn, 'DomainName': dom['DomainName'],
                        'EngineVersion': dom.get('EngineVersion', 'N/A'),
                        'Endpoint': dom.get('Endpoint', 'N/A'), 'Region': region
                    })
                    sn += 1
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"OpenSearch error in {region}: {e}")
    return items


def fetch_vpcs(session, regions):
    logger.info("Fetching VPCs...")
    items = []
    sn = 1
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            for v in ec2.describe_vpcs()['Vpcs']:
                tags = {t['Key']: t['Value'] for t in v.get('Tags', [])}
                items.append({
                    'Sr. No': sn, 'VpcId': v['VpcId'], 'Name': tags.get('Name', 'N/A'),
                    'CidrBlock': v['CidrBlock'], 'State': v['State'],
                    'IsDefault': v['IsDefault'], 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"VPC error in {region}: {e}")
    return items


def fetch_subnets(session, regions):
    logger.info("Fetching Subnets...")
    items = []
    sn = 1
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            for s in ec2.describe_subnets()['Subnets']:
                tags = {t['Key']: t['Value'] for t in s.get('Tags', [])}
                items.append({
                    'Sr. No': sn, 'SubnetId': s['SubnetId'], 'Name': tags.get('Name', 'N/A'),
                    'VpcId': s['VpcId'], 'CidrBlock': s['CidrBlock'],
                    'AZ': s['AvailabilityZone'], 'AvailableIPs': s['AvailableIpAddressCount'],
                    'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"Subnet error in {region}: {e}")
    return items


def fetch_security_groups(session, regions):
    logger.info("Fetching Security Groups...")
    items = []
    sn = 1
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            for sg in ec2.describe_security_groups()['SecurityGroups']:
                items.append({
                    'Sr. No': sn, 'GroupId': sg['GroupId'], 'GroupName': sg['GroupName'],
                    'Description': sg['Description'], 'VpcId': sg.get('VpcId', 'N/A'),
                    'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"SG error in {region}: {e}")
    return items


def fetch_load_balancers(session, regions):
    logger.info("Fetching Load Balancers...")
    items = []
    sn = 1
    for region in regions:
        try:
            elb = session.client('elbv2', region_name=region)
            for lb in elb.describe_load_balancers()['LoadBalancers']:
                items.append({
                    'Sr. No': sn, 'Name': lb['LoadBalancerName'], 'DNSName': lb['DNSName'],
                    'Type': lb['Type'], 'Scheme': lb['Scheme'],
                    'State': lb['State']['Code'], 'VpcId': lb['VpcId'], 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"ELB error in {region}: {e}")
    return items


def fetch_route53(session):
    logger.info("Fetching Route53 zones...")
    items = []
    sn = 1
    try:
        r53 = session.client('route53')
        for z in r53.list_hosted_zones()['HostedZones']:
            items.append({
                'Sr. No': sn, 'Name': z['Name'], 'Id': z['Id'],
                'RecordSets': z.get('ResourceRecordSetCount', 0),
                'Private': z.get('Config', {}).get('PrivateZone', False)
            })
            sn += 1
    except Exception as e:
        logger.error(f"Route53 error: {e}")
    return items


def fetch_cloudfront(session):
    logger.info("Fetching CloudFront distributions...")
    items = []
    sn = 1
    try:
        cf = session.client('cloudfront')
        dists = cf.list_distributions().get('DistributionList', {}).get('Items', [])
        for d in dists:
            items.append({
                'Sr. No': sn, 'Id': d['Id'], 'DomainName': d['DomainName'],
                'Status': d['Status'], 'Enabled': d['Enabled']
            })
            sn += 1
    except Exception as e:
        logger.error(f"CloudFront error: {e}")
    return items


def fetch_api_gateway(session, regions):
    logger.info("Fetching API Gateways...")
    items = []
    sn = 1
    for region in regions:
        try:
            apigw = session.client('apigateway', region_name=region)
            for api in apigw.get_rest_apis().get('items', []):
                items.append({
                    'Sr. No': sn, 'Name': api.get('name', 'N/A'), 'Id': api['id'],
                    'Created': safe_dt(api.get('createdDate')), 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"APIGW error in {region}: {e}")
    return items


def fetch_cloudformation(session, regions):
    logger.info("Fetching CloudFormation stacks...")
    items = []
    sn = 1
    for region in regions:
        try:
            cfn = session.client('cloudformation', region_name=region)
            for s in cfn.describe_stacks()['Stacks']:
                items.append({
                    'Sr. No': sn, 'StackName': s['StackName'], 'Status': s['StackStatus'],
                    'Created': safe_dt(s['CreationTime']), 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"CFN error in {region}: {e}")
    return items


def fetch_cloudtrail(session, regions):
    logger.info("Fetching CloudTrail trails...")
    items = []
    sn = 1
    for region in regions:
        try:
            ct = session.client('cloudtrail', region_name=region)
            for t in ct.describe_trails()['trailList']:
                items.append({
                    'Sr. No': sn, 'Name': t['Name'],
                    'S3Bucket': t.get('S3BucketName', 'N/A'),
                    'MultiRegion': t.get('IsMultiRegionTrail', False),
                    'HomeRegion': t.get('HomeRegion', 'N/A'), 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"CloudTrail error in {region}: {e}")
    return items


def fetch_cloudwatch_alarms(session, regions):
    logger.info("Fetching CloudWatch alarms...")
    items = []
    sn = 1
    for region in regions:
        try:
            cw = session.client('cloudwatch', region_name=region)
            for page in cw.get_paginator('describe_alarms').paginate():
                for a in page.get('MetricAlarms', []):
                    items.append({
                        'Sr. No': sn, 'AlarmName': a['AlarmName'],
                        'State': a.get('StateValue', 'N/A'),
                        'Metric': a.get('MetricName', 'N/A'),
                        'Namespace': a.get('Namespace', 'N/A'), 'Region': region
                    })
                    sn += 1
        except Exception as e:
            logger.error(f"CW Alarms error in {region}: {e}")
    return items


def fetch_cloudwatch_logs(session, regions):
    logger.info("Fetching CloudWatch Log Groups...")
    items = []
    sn = 1
    for region in regions:
        try:
            logs = session.client('logs', region_name=region)
            for page in logs.get_paginator('describe_log_groups').paginate():
                for lg in page['logGroups']:
                    items.append({
                        'Sr. No': sn, 'LogGroupName': lg['logGroupName'],
                        'StoredBytes': lg.get('storedBytes', 0),
                        'Retention': lg.get('retentionInDays', 'Never'),
                        'Region': region
                    })
                    sn += 1
        except Exception as e:
            logger.error(f"CW Logs error in {region}: {e}")
    return items


def fetch_eventbridge(session, regions):
    logger.info("Fetching EventBridge rules...")
    items = []
    sn = 1
    for region in regions:
        try:
            eb = session.client('events', region_name=region)
            for page in eb.get_paginator('list_rules').paginate():
                for r in page['Rules']:
                    items.append({
                        'Sr. No': sn, 'Name': r['Name'], 'State': r.get('State', 'N/A'),
                        'Schedule': r.get('ScheduleExpression', 'N/A'), 'Region': region
                    })
                    sn += 1
        except Exception as e:
            logger.error(f"EventBridge error in {region}: {e}")
    return items


def fetch_kms(session, regions):
    logger.info("Fetching KMS keys...")
    items = []
    sn = 1
    for region in regions:
        try:
            kms = session.client('kms', region_name=region)
            for page in kms.get_paginator('list_keys').paginate():
                for k in page['Keys']:
                    try:
                        meta = kms.describe_key(KeyId=k['KeyId'])['KeyMetadata']
                        items.append({
                            'Sr. No': sn, 'KeyId': k['KeyId'],
                            'Description': meta.get('Description', 'N/A'),
                            'State': meta.get('KeyState', 'N/A'),
                            'Enabled': meta.get('Enabled', False), 'Region': region
                        })
                        sn += 1
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"KMS error in {region}: {e}")
    return items


def fetch_secrets(session, regions):
    logger.info("Fetching Secrets Manager...")
    items = []
    sn = 1
    for region in regions:
        try:
            sm = session.client('secretsmanager', region_name=region)
            for page in sm.get_paginator('list_secrets').paginate():
                for s in page['SecretList']:
                    items.append({
                        'Sr. No': sn, 'Name': s.get('Name', 'N/A'),
                        'LastChanged': safe_dt(s.get('LastChangedDate')), 'Region': region
                    })
                    sn += 1
        except Exception as e:
            logger.error(f"Secrets error in {region}: {e}")
    return items


def fetch_acm(session, regions):
    logger.info("Fetching ACM certificates...")
    items = []
    sn = 1
    for region in regions:
        try:
            acm = session.client('acm', region_name=region)
            for page in acm.get_paginator('list_certificates').paginate():
                for c in page['CertificateSummaryList']:
                    items.append({
                        'Sr. No': sn, 'Domain': c['DomainName'],
                        'Arn': c['CertificateArn'], 'Status': c.get('Status', 'N/A'),
                        'Region': region
                    })
                    sn += 1
        except Exception as e:
            logger.error(f"ACM error in {region}: {e}")
    return items


def fetch_sns(session, regions):
    logger.info("Fetching SNS topics...")
    items = []
    sn = 1
    for region in regions:
        try:
            sns = session.client('sns', region_name=region)
            for page in sns.get_paginator('list_topics').paginate():
                for t in page['Topics']:
                    items.append({
                        'Sr. No': sn, 'TopicArn': t['TopicArn'],
                        'Name': t['TopicArn'].split(':')[-1], 'Region': region
                    })
                    sn += 1
        except Exception as e:
            logger.error(f"SNS error in {region}: {e}")
    return items


def fetch_sqs(session, regions):
    logger.info("Fetching SQS queues...")
    items = []
    sn = 1
    for region in regions:
        try:
            sqs = session.client('sqs', region_name=region)
            for page in sqs.get_paginator('list_queues').paginate():
                for url in page.get('QueueUrls', []):
                    items.append({
                        'Sr. No': sn, 'QueueName': url.split('/')[-1],
                        'QueueUrl': url, 'Region': region
                    })
                    sn += 1
        except Exception as e:
            logger.error(f"SQS error in {region}: {e}")
    return items


def fetch_stepfunctions(session, regions):
    logger.info("Fetching Step Functions...")
    items = []
    sn = 1
    for region in regions:
        try:
            sfn = session.client('stepfunctions', region_name=region)
            for sm in sfn.list_state_machines()['stateMachines']:
                items.append({
                    'Sr. No': sn, 'Name': sm['name'], 'Arn': sm['stateMachineArn'],
                    'Type': sm.get('type', 'N/A'),
                    'Created': safe_dt(sm.get('creationDate')), 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"StepFunctions error in {region}: {e}")
    return items


def fetch_glue(session, regions):
    logger.info("Fetching Glue databases & jobs...")
    dbs, jobs = [], []
    dsn, jsn = 1, 1
    for region in regions:
        try:
            glue = session.client('glue', region_name=region)
            for db in glue.get_databases()['DatabaseList']:
                dbs.append({
                    'Sr. No': dsn, 'Name': db['Name'],
                    'Created': safe_dt(db.get('CreateTime')), 'Region': region
                })
                dsn += 1
            for page in glue.get_paginator('get_jobs').paginate():
                for j in page['Jobs']:
                    jobs.append({
                        'Sr. No': jsn, 'Name': j['Name'],
                        'Created': safe_dt(j.get('CreatedOn')),
                        'Modified': safe_dt(j.get('LastModifiedOn')), 'Region': region
                    })
                    jsn += 1
        except Exception as e:
            logger.error(f"Glue error in {region}: {e}")
    return dbs, jobs


def fetch_iam(session):
    logger.info("Fetching IAM resources...")
    users, roles, policies = [], [], []
    try:
        iam = session.client('iam')
        sn = 1
        for page in iam.get_paginator('list_users').paginate():
            for u in page['Users']:
                users.append({
                    'Sr. No': sn, 'UserName': u['UserName'], 'UserId': u['UserId'],
                    'Created': safe_dt(u['CreateDate']), 'Path': u['Path']
                })
                sn += 1
        sn = 1
        for page in iam.get_paginator('list_roles').paginate():
            for r in page['Roles']:
                roles.append({
                    'Sr. No': sn, 'RoleName': r['RoleName'], 'RoleId': r['RoleId'],
                    'Created': safe_dt(r['CreateDate']), 'Path': r['Path']
                })
                sn += 1
        sn = 1
        for page in iam.get_paginator('list_policies').paginate(Scope='Local'):
            for p in page['Policies']:
                policies.append({
                    'Sr. No': sn, 'PolicyName': p['PolicyName'],
                    'Arn': p['Arn'], 'Attachments': p['AttachmentCount']
                })
                sn += 1
    except Exception as e:
        logger.error(f"IAM error: {e}")
    return users, roles, policies


def fetch_efs(session, regions):
    logger.info("Fetching EFS file systems...")
    items = []
    sn = 1
    for region in regions:
        try:
            efs = session.client('efs', region_name=region)
            for fs in efs.describe_file_systems()['FileSystems']:
                items.append({
                    'Sr. No': sn, 'FileSystemId': fs['FileSystemId'],
                    'Name': fs.get('Name', 'N/A'), 'State': fs.get('LifeCycleState', 'N/A'),
                    'SizeBytes': fs.get('SizeInBytes', {}).get('Value', 0),
                    'MountTargets': fs.get('NumberOfMountTargets', 0),
                    'Created': safe_dt(fs.get('CreationTime')), 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"EFS error in {region}: {e}")
    return items


def fetch_elastic_ips(session, regions):
    logger.info("Fetching Elastic IPs...")
    items = []
    sn = 1
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            for a in ec2.describe_addresses()['Addresses']:
                items.append({
                    'Sr. No': sn, 'PublicIP': a.get('PublicIp', 'N/A'),
                    'AllocationId': a.get('AllocationId', 'N/A'),
                    'InstanceId': a.get('InstanceId', 'N/A'),
                    'PrivateIP': a.get('PrivateIpAddress', 'N/A'), 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"EIP error in {region}: {e}")
    return items


def fetch_nat_gateways(session, regions):
    logger.info("Fetching NAT Gateways...")
    items = []
    sn = 1
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            for n in ec2.describe_nat_gateways()['NatGateways']:
                tags = {t['Key']: t['Value'] for t in n.get('Tags', [])}
                items.append({
                    'Sr. No': sn, 'NatGatewayId': n['NatGatewayId'],
                    'Name': tags.get('Name', 'N/A'), 'VpcId': n.get('VpcId', 'N/A'),
                    'State': n.get('State', 'N/A'), 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"NAT GW error in {region}: {e}")
    return items


def fetch_igws(session, regions):
    logger.info("Fetching Internet Gateways...")
    items = []
    sn = 1
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            for igw in ec2.describe_internet_gateways()['InternetGateways']:
                tags = {t['Key']: t['Value'] for t in igw.get('Tags', [])}
                att = igw.get('Attachments', [])
                items.append({
                    'Sr. No': sn, 'IGWId': igw['InternetGatewayId'],
                    'Name': tags.get('Name', 'N/A'),
                    'VpcId': att[0]['VpcId'] if att else 'N/A', 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"IGW error in {region}: {e}")
    return items


def fetch_tgws(session, regions):
    logger.info("Fetching Transit Gateways...")
    items = []
    sn = 1
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            for tgw in ec2.describe_transit_gateways()['TransitGateways']:
                tags = {t['Key']: t['Value'] for t in tgw.get('Tags', [])}
                items.append({
                    'Sr. No': sn, 'TGWId': tgw['TransitGatewayId'],
                    'Name': tags.get('Name', 'N/A'), 'State': tgw.get('State', 'N/A'),
                    'Owner': tgw.get('OwnerId', 'N/A'), 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"TGW error in {region}: {e}")
    return items


def fetch_waf(session, regions):
    logger.info("Fetching WAF Web ACLs...")
    items = []
    sn = 1
    for region in regions:
        try:
            waf = session.client('wafv2', region_name=region)
            for acl in waf.list_web_acls(Scope='REGIONAL')['WebACLs']:
                items.append({
                    'Sr. No': sn, 'Name': acl['Name'], 'Id': acl['Id'],
                    'Scope': 'REGIONAL', 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"WAF error in {region}: {e}")
    # Global (CloudFront) ACLs
    try:
        waf_g = session.client('wafv2', region_name='us-east-1')
        for acl in waf_g.list_web_acls(Scope='CLOUDFRONT')['WebACLs']:
            items.append({
                'Sr. No': sn, 'Name': acl['Name'], 'Id': acl['Id'],
                'Scope': 'CLOUDFRONT', 'Region': 'global'
            })
            sn += 1
    except Exception as e:
        logger.error(f"WAF CloudFront error: {e}")
    return items


def fetch_cognito(session, regions):
    logger.info("Fetching Cognito pools...")
    user_pools, identity_pools = [], []
    usn, isn = 1, 1
    for region in regions:
        try:
            cidp = session.client('cognito-idp', region_name=region)
            for p in cidp.list_user_pools(MaxResults=60)['UserPools']:
                user_pools.append({
                    'Sr. No': usn, 'Name': p['Name'], 'Id': p['Id'],
                    'Created': safe_dt(p.get('CreationDate')), 'Region': region
                })
                usn += 1
        except Exception as e:
            logger.error(f"Cognito UserPool error in {region}: {e}")
        try:
            ci = session.client('cognito-identity', region_name=region)
            for p in ci.list_identity_pools(MaxResults=60)['IdentityPools']:
                identity_pools.append({
                    'Sr. No': isn, 'Id': p['IdentityPoolId'],
                    'Name': p['IdentityPoolName'], 'Region': region
                })
                isn += 1
        except Exception as e:
            logger.error(f"Cognito IdentityPool error in {region}: {e}")
    return user_pools, identity_pools


def fetch_config_rules(session, regions):
    logger.info("Fetching Config rules...")
    items = []
    sn = 1
    for region in regions:
        try:
            cfg = session.client('config', region_name=region)
            for page in cfg.get_paginator('describe_config_rules').paginate():
                for r in page['ConfigRules']:
                    items.append({
                        'Sr. No': sn, 'RuleName': r['ConfigRuleName'],
                        'State': r.get('ConfigRuleState', 'N/A'),
                        'Source': r.get('Source', {}).get('Owner', 'N/A'), 'Region': region
                    })
                    sn += 1
        except Exception as e:
            logger.error(f"Config error in {region}: {e}")
    return items


def fetch_ssm_params(session, regions):
    logger.info("Fetching SSM parameters...")
    items = []
    sn = 1
    for region in regions:
        try:
            ssm = session.client('ssm', region_name=region)
            for page in ssm.get_paginator('describe_parameters').paginate():
                for p in page['Parameters']:
                    items.append({
                        'Sr. No': sn, 'Name': p['Name'], 'Type': p.get('Type', 'N/A'),
                        'LastModified': safe_dt(p.get('LastModifiedDate')),
                        'Version': p.get('Version', 'N/A'), 'Region': region
                    })
                    sn += 1
        except Exception as e:
            logger.error(f"SSM error in {region}: {e}")
    return items


def fetch_backup(session, regions):
    logger.info("Fetching Backup plans...")
    items = []
    sn = 1
    for region in regions:
        try:
            bk = session.client('backup', region_name=region)
            for p in bk.list_backup_plans()['BackupPlansList']:
                items.append({
                    'Sr. No': sn, 'PlanName': p['BackupPlanName'],
                    'PlanId': p['BackupPlanId'],
                    'Created': safe_dt(p.get('CreationDate')), 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"Backup error in {region}: {e}")
    return items


def fetch_sagemaker(session, regions):
    logger.info("Fetching SageMaker notebooks...")
    items = []
    sn = 1
    for region in regions:
        try:
            sm = session.client('sagemaker', region_name=region)
            for page in sm.get_paginator('list_notebook_instances').paginate():
                for nb in page['NotebookInstances']:
                    items.append({
                        'Sr. No': sn, 'Name': nb['NotebookInstanceName'],
                        'Type': nb.get('InstanceType', 'N/A'),
                        'Status': nb.get('NotebookInstanceStatus', 'N/A'),
                        'Created': safe_dt(nb.get('CreationTime')), 'Region': region
                    })
                    sn += 1
        except Exception as e:
            logger.error(f"SageMaker error in {region}: {e}")
    return items


def fetch_kinesis(session, regions):
    logger.info("Fetching Kinesis streams...")
    items = []
    sn = 1
    for region in regions:
        try:
            kin = session.client('kinesis', region_name=region)
            streams = kin.list_streams()['StreamNames']
            for name in streams:
                try:
                    desc = kin.describe_stream_summary(StreamName=name)['StreamDescriptionSummary']
                    items.append({
                        'Sr. No': sn, 'StreamName': name,
                        'Status': desc.get('StreamStatus', 'N/A'),
                        'Shards': desc.get('OpenShardCount', 0),
                        'Retention(hrs)': desc.get('RetentionPeriodHours', 0), 'Region': region
                    })
                    sn += 1
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Kinesis error in {region}: {e}")
    return items


def fetch_redshift(session, regions):
    logger.info("Fetching Redshift clusters...")
    items = []
    sn = 1
    for region in regions:
        try:
            rs = session.client('redshift', region_name=region)
            for c in rs.describe_clusters()['Clusters']:
                items.append({
                    'Sr. No': sn, 'ClusterId': c['ClusterIdentifier'],
                    'NodeType': c.get('NodeType', 'N/A'),
                    'Status': c.get('ClusterStatus', 'N/A'),
                    'Nodes': c.get('NumberOfNodes', 0),
                    'DBName': c.get('DBName', 'N/A'), 'Region': region
                })
                sn += 1
        except Exception as e:
            logger.error(f"Redshift error in {region}: {e}")
    return items


# ============================================================================
# COLLECT ALL INVENTORY FOR ONE ACCOUNT
# ============================================================================

def collect_inventory(session):
    """Collect all inventory for a single AWS account session"""
    regions = get_regions(session)
    logger.info(f"Scanning {len(regions)} regions")

    data = {}

    # Compute
    data['EC2_Instances'] = fetch_ec2(session, regions)
    data['EBS_Volumes'] = fetch_ebs(session, regions)
    ecs_clusters, ecs_services = fetch_ecs(session, regions)
    data['ECS_Clusters'] = ecs_clusters
    data['ECS_Services'] = ecs_services
    data['ECR_Repositories'] = fetch_ecr(session, regions)
    data['Lambda'] = fetch_lambda(session, regions)

    # Storage
    data['S3'] = fetch_s3(session)
    data['EFS'] = fetch_efs(session, regions)

    # Database
    data['RDS'] = fetch_rds(session, regions)
    data['DynamoDB'] = fetch_dynamodb(session, regions)
    data['ElastiCache'] = fetch_elasticache(session, regions)
    data['OpenSearch'] = fetch_opensearch(session, regions)

    # Networking
    data['VPC'] = fetch_vpcs(session, regions)
    data['Subnets'] = fetch_subnets(session, regions)
    data['Security_Groups'] = fetch_security_groups(session, regions)
    data['Load_Balancers'] = fetch_load_balancers(session, regions)
    data['Elastic_IPs'] = fetch_elastic_ips(session, regions)
    data['NAT_Gateways'] = fetch_nat_gateways(session, regions)
    data['Internet_Gateways'] = fetch_igws(session, regions)
    data['Transit_Gateways'] = fetch_tgws(session, regions)
    data['Route53'] = fetch_route53(session)
    data['CloudFront'] = fetch_cloudfront(session)
    data['API_Gateway'] = fetch_api_gateway(session, regions)

    # Management
    data['CloudFormation'] = fetch_cloudformation(session, regions)
    data['CloudTrail'] = fetch_cloudtrail(session, regions)
    data['CloudWatch_Alarms'] = fetch_cloudwatch_alarms(session, regions)
    data['CloudWatch_LogGroups'] = fetch_cloudwatch_logs(session, regions)
    data['EventBridge'] = fetch_eventbridge(session, regions)

    # Security
    data['KMS_Keys'] = fetch_kms(session, regions)
    data['Secrets_Manager'] = fetch_secrets(session, regions)
    data['ACM_Certificates'] = fetch_acm(session, regions)
    data['WAF_WebACLs'] = fetch_waf(session, regions)

    # App Integration
    data['SNS_Topics'] = fetch_sns(session, regions)
    data['SQS_Queues'] = fetch_sqs(session, regions)
    data['Step_Functions'] = fetch_stepfunctions(session, regions)

    # Analytics
    glue_dbs, glue_jobs = fetch_glue(session, regions)
    data['Glue_Databases'] = glue_dbs
    data['Glue_Jobs'] = glue_jobs
    data['Kinesis'] = fetch_kinesis(session, regions)
    data['Redshift'] = fetch_redshift(session, regions)
    data['SageMaker'] = fetch_sagemaker(session, regions)

    # Governance
    cognito_up, cognito_ip = fetch_cognito(session, regions)
    data['Cognito_UserPools'] = cognito_up
    data['Cognito_IdentityPools'] = cognito_ip
    data['Config_Rules'] = fetch_config_rules(session, regions)
    data['SSM_Parameters'] = fetch_ssm_params(session, regions)
    data['Backup_Plans'] = fetch_backup(session, regions)

    # IAM
    iam_users, iam_roles, iam_policies = fetch_iam(session)
    data['IAM_Users'] = iam_users
    data['IAM_Roles'] = iam_roles
    data['IAM_Policies'] = iam_policies

    return data


# ============================================================================
# EXCEL EXPORT & S3 UPLOAD
# ============================================================================

def export_to_excel_buffer(data_dict):
    """Export inventory data to an in-memory Excel file (BytesIO)"""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        for sheet_name, data in data_dict.items():
            if data:
                df = pd.DataFrame(data)
                for col in df.columns:
                    if df[col].dtype == 'object':
                        sample = df[col].dropna().head(1)
                        if not sample.empty and hasattr(sample.iloc[0], 'strftime'):
                            df[col] = df[col].apply(safe_dt)
                # Excel sheet names max 31 chars
                df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    buffer.seek(0)
    return buffer


def upload_to_s3(buffer, bucket, s3_key):
    """Upload a BytesIO buffer to S3"""
    s3 = boto3.client('s3')
    s3.put_object(Bucket=bucket, Key=s3_key, Body=buffer.getvalue(),
                  ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    logger.info(f"Uploaded to s3://{bucket}/{s3_key}")


# ============================================================================
# LAMBDA HANDLER
# ============================================================================

def lambda_handler(event, context):
    """
    Lambda entry point.

    Optional event overrides:
      - environments: list of env names to process, e.g. ["dev", "uat"]
                      (defaults to all accounts defined in ACCOUNTS)
      - bucket: S3 bucket name override
    """
    envs = event.get('environments', list(ACCOUNTS.keys()))
    bucket = event.get('bucket', S3_BUCKET)
    now = datetime.utcnow()
    results = {}

    # SSM client in the Lambda account to read credentials
    ssm_client = boto3.client('ssm')

    for env in envs:
        env = env.strip()
        if env not in ACCOUNTS:
            logger.error(f"✗ Environment '{env}' not defined in ACCOUNTS, skipping")
            results[env] = {'status': 'error', 'error': f"'{env}' not defined in ACCOUNTS"}
            continue

        logger.info(f"{'='*60}")
        logger.info(f"Processing environment: {env}")
        logger.info(f"{'='*60}")

        try:
            # Get target account session
            session = get_account_session(ssm_client, ACCOUNTS[env])
            account_id, account_name = get_account_info(session)
            logger.info(f"Account: {account_id} ({account_name})")

            # Collect inventory
            data = collect_inventory(session)

            # Generate Excel in memory
            buffer = export_to_excel_buffer(data)

            # S3 key: year/month/AccountName_env_YYYYMMDD_HHMMSS.xlsx
            s3_key = (
                f"{now.strftime('%Y')}/{now.strftime('%m')}/"
                f"{account_name}_{env}_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
            )

            upload_to_s3(buffer, bucket, s3_key)

            # Summary
            total = sum(len(v) for v in data.values() if v)
            results[env] = {
                'status': 'success',
                'account_id': account_id,
                'account_name': account_name,
                's3_path': f"s3://{bucket}/{s3_key}",
                'total_resources': total
            }
            logger.info(f"✓ {env}: {total} resources -> s3://{bucket}/{s3_key}")

        except Exception as e:
            logger.error(f"✗ Failed to process {env}: {e}")
            results[env] = {'status': 'error', 'error': str(e)}

    logger.info(f"{'='*60}")
    logger.info("All environments processed.")
    logger.info(f"{'='*60}")

    return {
        'statusCode': 200,
        'body': results
    }

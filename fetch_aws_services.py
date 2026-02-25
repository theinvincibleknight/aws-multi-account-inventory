#!/usr/bin/env python3
"""
Step 1: Fetch list of AWS services from Cost Explorer
This identifies which services are actually being used in your account
Saves the list to aws_services.txt
"""

import boto3
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def fetch_services_from_cost_explorer():
    """Fetch list of AWS services from Cost Explorer based on actual usage"""
    logger.info("Fetching AWS services from Cost Explorer...")
    
    try:
        ce = boto3.client('ce', region_name='us-east-1')
        
        # Get last 90 days of cost data to capture all services
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=90)
        
        logger.info(f"Analyzing costs from {start_date} to {end_date}")
        
        response = ce.get_cost_and_usage(
            TimePeriod={
                'Start': start_date.strftime('%Y-%m-%d'),
                'End': end_date.strftime('%Y-%m-%d')
            },
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            GroupBy=[
                {
                    'Type': 'DIMENSION',
                    'Key': 'SERVICE'
                }
            ]
        )
        
        # Extract unique services
        services = set()
        for result in response['ResultsByTime']:
            for group in result['Groups']:
                service_name = group['Keys'][0]
                if service_name and service_name not in ['NoService', 'Tax']:
                    services.add(service_name)
        
        # Sort services alphabetically
        services = sorted(services)
        
        logger.info(f"Found {len(services)} AWS services in use")
        return services
        
    except Exception as e:
        logger.error(f"Error fetching from Cost Explorer: {e}")
        logger.error("Make sure you have 'ce:GetCostAndUsage' permission")
        return []


def get_account_info():
    """Get AWS account number and alias/name"""
    try:
        sts = boto3.client('sts')
        account_id = sts.get_caller_identity()['Account']
        
        # Try to get account alias
        try:
            iam = boto3.client('iam')
            aliases = iam.list_account_aliases()['AccountAliases']
            account_name = aliases[0] if aliases else 'NoAlias'
        except:
            account_name = 'NoAlias'
        
        return account_id, account_name
    except Exception as e:
        logger.error(f"Error getting account info: {e}")
        return 'Unknown', 'Unknown'


def save_services_to_file(services, account_id, account_name, filename='aws_services.txt'):
    """Save services list to text file with account info"""
    logger.info(f"Saving services to {filename}...")
    
    try:
        with open(filename, 'w') as f:
            # Write account info as comments at the top
            f.write(f"# AWS Account: {account_id}\n")
            f.write(f"# Account Name: {account_name}\n")
            f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Total Services: {len(services)}\n")
            f.write("#\n")
            f.write("# Services discovered from Cost Explorer (last 90 days):\n")
            f.write("#" + "="*68 + "\n\n")
            
            for service in services:
                f.write(f"{service}\n")
        
        logger.info(f"Successfully saved {len(services)} services to {filename}")
        return True
    except Exception as e:
        logger.error(f"Error saving to file: {e}")
        return False


def main():
    """Main execution"""
    print("="*70)
    print("AWS Services Discovery from Cost Explorer")
    print("="*70)
    print()
    
    # Get account info
    account_id, account_name = get_account_info()
    logger.info(f"AWS Account: {account_id} ({account_name})")
    
    # Fetch services
    services = fetch_services_from_cost_explorer()
    
    if not services:
        logger.error("No services found or error occurred")
        logger.info("\nMake sure:")
        logger.info("  1. AWS credentials are configured")
        logger.info("  2. You have 'ce:GetCostAndUsage' permission")
        logger.info("  3. Cost Explorer is enabled in your account")
        return 1
    
    # Save to file
    if save_services_to_file(services, account_id, account_name):
        print("\n" + "="*70)
        print(f"✓ AWS Account: {account_id} ({account_name})")
        print(f"✓ Found {len(services)} AWS services in your account:")
        print("="*70)
        for i, service in enumerate(services, 1):
            print(f"  {i:2d}. {service}")
        print("="*70)
        print(f"\n✓ Services saved to: aws_services.txt")
        print("\nNext step:")
        print("  Run: python aws_inventory_dynamic.py")
        print("="*70)
        return 0
    else:
        logger.error("Failed to save services to file")
        return 1


if __name__ == '__main__':
    exit(main())

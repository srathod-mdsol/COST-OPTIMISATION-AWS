import argparse
import json
import csv
import re
import os
from datetime import datetime
from colorama import init, Fore, Style
from services.rds_manager import RDSManager
from services.ec2_manager import EC2Manager
from analysis.idle_analyzer import IdleAnalyzer
from analysis.cost_calculator import CostCalculator
from etl.data_provider import create_data_provider
from core.config import Config
from core.logger import setup_logger
from core.constants import HOURS_PER_MONTH

# Initialize colorama
init()

logger = setup_logger(__name__)


def parse_bool(value) -> bool:
    """Parse boolean value from various representations.
    
    Args:
        value: Value to parse (bool, str, or any)
        
    Returns:
        Boolean value
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', 'yes', '1', 'on')
    return bool(value)

class CLIInterface:
    """Command Line Interface for AWS Cost Optimizer"""
    
    def __init__(self):
        self.parser = self._setup_parser()
        self.etl_provider = create_data_provider()

    def _setup_parser(self):
        parser = argparse.ArgumentParser(description="AWS Idle Instance Monitor - CLI Mode")
        parser.add_argument('--service', choices=['rds', 'ec2'], required=False)
        parser.add_argument('--check-all', action='store_true')
        parser.add_argument('--instance-id', type=str)
        parser.add_argument('--region', type=str, default='us-east-1')
        parser.add_argument('--cloudwatch-hours', type=int, default=24)
        parser.add_argument('--activity-days', type=int, default=30)
        parser.add_argument('--idle-threshold', type=int, default=50)
        parser.add_argument('--output', type=str)
        parser.add_argument('--csv', type=str)
        parser.add_argument('--unlock', action='store_true', help='Forcefully release the ETL lock')
        return parser

    def run(self):
        args = self.parser.parse_args()
        
        if args.unlock:
            from etl.orchestrator import ETLOrchestrator
            orch = ETLOrchestrator()
            orch.force_unlock()
            print(f"{Fore.GREEN}ETL lock has been forcefully released.{Style.RESET_ALL}")
            return

        if not args.service:
            logger.error("--service is required unless using --unlock")
            return

        if not args.check_all and not args.instance_id:
            logger.error("Either --check-all or --instance-id must be specified")
            return

        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}AWS Idle Instance Monitor - {args.service.upper()} Service{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        
        if args.service == 'rds':
            manager = RDSManager(args.region, use_etl=False) # CLI mode uses direct API
            analyze_func = IdleAnalyzer.analyze_rds
        elif args.service == 'ec2':
            manager = EC2Manager(args.region, use_etl=False)
            analyze_func = IdleAnalyzer.analyze_ec2

        results = []
        instances = []
        
        if args.check_all:
            instances = manager.list_instances()
        else:
            # Handle single instance - S3 has been removed
            if args.service == 's3':
                print("S3 service has been removed from the application.")
                return
            instances = [{'instance_id': args.instance_id}]

        for idx, inst in enumerate(instances, 1):
            iid = inst.get('instance_id') or inst.get('bucket_name') or inst.get('name')
            print(f"[{idx}/{len(instances)}] Analyzing {Fore.YELLOW}{iid}{Style.RESET_ALL}...", end=' ', flush=True)
            
            try:
                metrics = manager.get_cloudwatch_metrics(iid, args.cloudwatch_hours)
                last_activity = manager.detect_last_activity(iid, args.activity_days)
                
                analysis = analyze_func(metrics, last_activity)
                
                status = 'IDLE' if analysis['idle_score'] >= args.idle_threshold else 'ACTIVE'
                color = Fore.RED if status == 'IDLE' else Fore.GREEN
                print(f"{color}{status}{Style.RESET_ALL} (Score: {analysis['idle_score']:.0f}%)")
                
                # Fetch pricing and calculate savings
                # For CLI mode, we still try to use the ETL provider for pricing if available
                savings = {'monthly': 0, 'annual': 0}
                iclass = inst.get('instance_class') or inst.get('instance_type')
                # Pass additional parameters for accurate pricing
                if args.service.upper() == 'RDS':
                        database_engine = inst.get('engine', '')
                        deployment_option = 'Multi-AZ' if parse_bool(inst.get('multi_az')) else 'Single-AZ'
                        multi_az = parse_bool(inst.get('multi_az'))
                        hourly = self.etl_provider.get_pricing(
                            iclass, args.region, args.service.upper(),
                            database_engine=database_engine,
                            deployment_option=deployment_option
                        ) or 0.0
                        
                        # Add RDS storage costs - use RDS-specific pricing (DIFFERENT from EBS!)
                        storage_type = inst.get('storage_type', 'gp2')
                        allocated_storage = inst.get('allocated_storage', 0)
                        iops = inst.get('iops', 0)
                        
                        if allocated_storage and allocated_storage > 0:
                            storage_cost = CostCalculator.calculate_rds_storage_cost(
                                int(allocated_storage), storage_type,
                                iops=int(iops) if iops else None,
                                multi_az=multi_az,
                                region=args.region
                            )
                            monthly_storage = storage_cost.get('monthly', 0)
                        else:
                            monthly_storage = 0
                        
                        monthly = (hourly * HOURS_PER_MONTH) + monthly_storage
                        savings = {'monthly': monthly, 'annual': monthly * 12}
                elif args.service.upper() == 'EC2':
                        operating_system = inst.get('platform', 'Linux/UNIX')
                        tenancy = inst.get('tenancy', 'shared')
                        hourly = self.etl_provider.get_pricing(
                            iclass, args.region, args.service.upper(),
                            operating_system=operating_system,
                            tenancy=tenancy
                        ) or 0.0
                        
                        # Add EC2 attached EBS volumes cost
                        monthly_ebs_cost = 0
                        attached_volumes = inst.get('attached_volumes', [])
                        for vol in attached_volumes:
                            vol_type = vol.get('volume_type', 'gp3')
                            vol_size = vol.get('size_gb', 0)
                            vol_iops = vol.get('iops', 0)
                            if vol_size > 0:
                                vol_cost = CostCalculator.calculate_ebs_cost(vol_size, vol_type, vol_iops, args.region)
                                monthly_ebs_cost += vol_cost.get('monthly', 0)
                        
                        monthly = (hourly * HOURS_PER_MONTH) + monthly_ebs_cost
                        savings = {'monthly': monthly, 'annual': monthly * 12}
                else:
                    price = self.etl_provider.get_pricing(iclass, args.region, args.service.upper())
                
                if args.service == 'rds':
                    savings = CostCalculator.calculate_rds_savings(price)
                else:
                    savings = CostCalculator.calculate_ec2_savings(price)
                
                results.append({
                    'id': iid,
                    'status': status,
                    'idle_score': analysis['idle_score'],
                    'recommendation': analysis['recommendation'],
                    'savings': savings
                })
                
            except Exception as e:
                print(f"{Fore.RED}FAILED: {e}{Style.RESET_ALL}")

        # Summary and exports
        self._display_summary(results)
        if args.output: self._export_json(results, args.output)
        if args.csv: self._export_csv(results, args.csv)

    def _display_summary(self, results):
        total_monthly = sum(r['savings'].get('monthly', 0) for r in results)
        idle_count = sum(1 for r in results if r['status'] == 'IDLE')
        
        print(f"\n{Fore.CYAN}{'-'*60}{Style.RESET_ALL}")
        print(f"Total Scanned: {len(results)}")
        print(f"Idle Flagged: {Fore.RED}{idle_count}{Style.RESET_ALL}")
        print(f"Potential Monthly Savings: {Fore.GREEN}${total_monthly:,.2f}{Style.RESET_ALL}")
        print(f"Potential Annual Savings: {Fore.GREEN}${total_monthly * 12:,.2f}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'-'*60}{Style.RESET_ALL}\n")

    def _export_json(self, results, path):
        # Security: Validate path
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(os.getcwd()):
            print(f"{Fore.RED}Error: Export path must be within the current directory.{Style.RESET_ALL}")
            return
            
        with open(abs_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Report exported to {abs_path}")

    def _export_csv(self, results, path):
        if not results: return
        
        # Security: Validate path
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(os.getcwd()):
            print(f"{Fore.RED}Error: Export path must be within the current directory.{Style.RESET_ALL}")
            return
            
        keys = results[0].keys()
        with open(abs_path, 'w', newline='') as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(results)
        print(f"Report exported to {path}")

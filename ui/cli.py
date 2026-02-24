import argparse
import json
import csv
import re
from datetime import datetime
from colorama import init, Fore, Style
from services.rds_manager import RDSManager
from services.ec2_manager import EC2Manager
from services.s3_manager import S3Manager
from analysis.idle_analyzer import IdleAnalyzer
from analysis.cost_calculator import CostCalculator
from etl.data_provider import create_data_provider
from core.config import Config
from core.logger import setup_logger

# Initialize colorama
init()

logger = setup_logger(__name__)

class CLIInterface:
    """Command Line Interface for AWS Cost Optimizer"""
    
    def __init__(self):
        self.parser = self._setup_parser()
        self.etl_provider = create_data_provider()

    def _setup_parser(self):
        parser = argparse.ArgumentParser(description="AWS Idle Instance Monitor - CLI Mode")
        parser.add_argument('--service', choices=['rds', 'ec2', 's3'], required=False)
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
        else:
            manager = S3Manager(args.region, use_etl=False)
            analyze_func = IdleAnalyzer.analyze_s3

        results = []
        instances = []
        
        if args.check_all:
            instances = manager.list_instances()
        else:
            # Handle single instance
            if args.service == 's3':
                instances = [{'name': args.instance_id, 'bucket_name': args.instance_id}]
            else:
                instances = [{'instance_id': args.instance_id}]

        for idx, inst in enumerate(instances, 1):
            iid = inst.get('instance_id') or inst.get('bucket_name') or inst.get('name')
            print(f"[{idx}/{len(instances)}] Analyzing {Fore.YELLOW}{iid}{Style.RESET_ALL}...", end=' ', flush=True)
            
            try:
                metrics = manager.get_cloudwatch_metrics(iid, args.cloudwatch_hours)
                last_activity = manager.detect_last_activity(iid, args.activity_days)
                
                if args.service == 's3':
                    analysis = analyze_func(metrics, last_activity, inst)
                else:
                    analysis = analyze_func(metrics, last_activity)
                
                status = 'IDLE' if analysis['idle_score'] >= args.idle_threshold else 'ACTIVE'
                color = Fore.RED if status == 'IDLE' else Fore.GREEN
                print(f"{color}{status}{Style.RESET_ALL} (Score: {analysis['idle_score']:.0f}%)")
                
                # Fetch pricing and calculate savings
                # For CLI mode, we still try to use the ETL provider for pricing if available
                savings = {'monthly': 0, 'annual': 0}
                if args.service == 's3':
                    savings = CostCalculator.calculate_s3_savings(inst.get('size_gb', 0))
                else:
                    iclass = inst.get('instance_class') or inst.get('instance_type')
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

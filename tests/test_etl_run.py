#!/usr/bin/env python3
"""
Quick test to verify ETL works

# TODO: [TESTING ISSUES]:
# 1. No cleanup of test data after run - leaves database in dirty state
# 2. No verification that data was actually loaded correctly
# 3. Should check for stuck locks before running test
# 4. Consider using a separate test database to avoid affecting production data
"""
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from etl.orchestrator import ETLOrchestrator

db_path = os.path.join(os.path.dirname(__file__), 'db', 'etl_database.db')

print("Testing ETL orchestrator...")
print(f"Database: {db_path}")

orchestrator = ETLOrchestrator(db_path)

print("\n🚀 Running ETL (this will call AWS APIs)...")
try:
    result = orchestrator.run_etl(
        run_type='manual',
        triggered_by='test_script',
        services=['RDS'],  # Start with just RDS
        regions=['us-east-1']
    )
    
    print(f"\n✅ ETL Result:")
    print(f"   Status: {result['status']}")
    print(f"   Duration: {result['duration']}s")
    print(f"   Records Extracted: {result['records_extracted']}")
    print(f"   Records Loaded: {result['records_loaded']}")
    
    if result['error_message']:
        print(f"   Error: {result['error_message']}")
    
except Exception as e:
    print(f"\n❌ ETL Failed: {e}")
    import traceback
    traceback.print_exc()

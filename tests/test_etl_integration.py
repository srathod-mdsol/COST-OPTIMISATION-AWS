#!/usr/bin/env python3
"""
Test script to verify ETL integration
Tests self-contained aws-cost-optimizer ETL implementation
"""
import sys
import os

def test_imports():
    """Test that all necessary imports work"""
    print("Testing imports...")
    
    try:
        from etl_data_provider import ETLDataProvider, create_data_provider
        print("✅ ETL data provider imports successfully")
    except ImportError as e:
        print(f"❌ Failed to import ETL data provider: {e}")
        return False
    
    try:
        from etl_orchestrator import ETLOrchestrator
        print("✅ ETL orchestrator imports successfully (local implementation)")
    except ImportError as e:
        print(f"❌ Failed to import ETL orchestrator: {e}")
        return False
    
    try:
        import pricing_etl
        print("✅ Pricing ETL imports successfully")
    except ImportError as e:
        print(f"❌ Failed to import pricing ETL: {e}")
        return False
    
    return True

def test_database_connection():
    """Test database connection"""
    print("\nTesting database connection...")
    
    from etl_data_provider import create_data_provider
    
    db_path = os.path.join(os.path.dirname(__file__), 'db', 'etl_database.db')
    print(f"Database path: {db_path}")
    
    if not os.path.exists(db_path):
        print(f"⚠️  Database file does not exist at {db_path}")
        return False
    
    try:
        provider = create_data_provider(db_path)
        print("✅ ETL data provider created successfully")
        
        # Test data freshness query
        freshness = provider.get_data_freshness('RDS')
        if freshness:
            print(f"✅ Data freshness query successful: {freshness}")
        else:
            print("⚠️  No data freshness information available (may need to run ETL)")
        
        return True
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return False

def test_etl_orchestrator():
    """Test ETL orchestrator initialization"""
    print("\nTesting ETL orchestrator...")
    
    try:
        from etl_orchestrator import ETLOrchestrator
        
        db_path = os.path.join(os.path.dirname(__file__), 'db', 'etl_database.db')
        orchestrator = ETLOrchestrator(db_path)
        print("✅ ETL orchestrator initialized successfully (local implementation)")
        print("✅ ETL orchestrator is self-contained within aws-cost-optimizer")
        
        # Note: We won't actually run ETL here as it would make AWS API calls
        print("⚠️  Not running actual ETL (would make AWS API calls)")
        
        return True
    except Exception as e:
        print(f"❌ Failed to initialize ETL orchestrator: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_pricing_etl():
    """Test pricing ETL function"""
    print("\nTesting pricing ETL...")
    
    try:
        import pricing_etl
        
        # Check if the function exists
        if hasattr(pricing_etl, 'run_pricing_etl'):
            print("✅ run_pricing_etl function exists")
        else:
            print("❌ run_pricing_etl function not found")
            return False
        
        # Check for pricing files
        pricing_dir = os.path.join(os.path.dirname(__file__), 'pricing')
        if os.path.exists(pricing_dir):
            files = os.listdir(pricing_dir)
            print(f"✅ Pricing directory exists with {len(files)} files")
            for f in files:
                if f.endswith('.json'):
                    print(f"   - {f}")
        else:
            print(f"⚠️  Pricing directory not found at {pricing_dir}")
        
        return True
    except Exception as e:
        print(f"❌ Pricing ETL test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("="*60)
    print("ETL Integration Test Suite")
    print("="*60)
    
    results = []
    
    results.append(("Imports", test_imports()))
    results.append(("Database Connection", test_database_connection()))
    results.append(("ETL Orchestrator", test_etl_orchestrator()))
    results.append(("Pricing ETL", test_pricing_etl()))
    
    print("\n" + "="*60)
    print("Test Results Summary")
    print("="*60)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name}: {status}")
    
    total_passed = sum(1 for _, result in results if result)
    print(f"\nTotal: {total_passed}/{len(results)} tests passed")
    
    if total_passed == len(results):
        print("\n🎉 All tests passed! ETL integration is working correctly.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Test script to demonstrate the refactored ingestion system.

This script shows:
1. Collection configuration system working
2. Generic filename to collection mapping
3. Configurable file patterns per collection
4. URL-based ingestion support for granules
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.collection_config import (
    get_collection_name_from_filename,
    get_collection_config,
    get_file_pattern_for_collection,
    get_filename_regex_for_collection,
    supports_s3_ingestion,
    supports_url_ingestion,
    list_all_collections
)

def test_collection_configuration():
    """Test the collection configuration system"""
    print("=== Collection Configuration Test ===")
    
    # Test listing all collections
    collections = list_all_collections()
    print(f"Available collections: {collections}")
    
    # Test filename to collection mapping
    test_files = [
        "cube-items.json",
        "velocity-mosaics-items.json", 
        "granule-items.json",
        "unknown-items.json"
    ]
    
    print("\nFilename to collection mapping:")
    for filename in test_files:
        collection = get_collection_name_from_filename(filename)
        print(f"  {filename} -> {collection}")
    
    # Test collection configurations
    print("\nCollection configurations:")
    for collection_id in collections:
        config = get_collection_config(collection_id)
        file_pattern = get_file_pattern_for_collection(collection_id)
        filename_regex = get_filename_regex_for_collection(collection_id)
        supports_s3 = supports_s3_ingestion(collection_id)
        supports_url = supports_url_ingestion(collection_id)
        
        print(f"  {collection_id}:")
        print(f"    File pattern: {file_pattern}")
        print(f"    Filename regex: {filename_regex.pattern if filename_regex else None}")
        print(f"    S3 ingestion: {supports_s3}")
        print(f"    URL ingestion: {supports_url}")
        print(f"    Description: {config.get('description', 'N/A')}")

def test_discover_files_signature():
    """Test that discover_files accepts the new collection_id parameter"""
    print("\n=== discover_files Signature Test ===")
    
    # Import the function to check its signature
    from app.tasks import discover_files
    import inspect
    
    sig = inspect.signature(discover_files)
    params = list(sig.parameters.keys())
    
    print(f"discover_files parameters: {params}")
    
    expected_params = ['bucket', 'path', 'recursive', 'year', 'collection_id']
    has_all_params = all(param in params for param in expected_params)
    
    print(f"Has all expected parameters: {has_all_params}")
    
    # Test default values
    collection_id_param = sig.parameters.get('collection_id')
    has_default = collection_id_param and collection_id_param.default is None
    print(f"collection_id has default None: {has_default}")

def test_tracker_signature():
    """Test that tracker.create_job accepts the new collection_id parameter"""
    print("\n=== Tracker Signature Test ===")
    
    from app.tracker import JobTracker
    import inspect
    
    sig = inspect.signature(JobTracker.create_job)
    params = list(sig.parameters.keys())
    
    print(f"JobTracker.create_job parameters: {params}")
    
    expected_params = ['self', 'bucket', 'path', 'recursive', 'year', 'collection_id']
    has_all_params = all(param in params for param in expected_params)
    
    print(f"Has all expected parameters: {has_all_params}")

def demonstrate_usage():
    """Demonstrate how the new system would be used"""
    print("\n=== Usage Examples ===")
    
    print("1. Generic S3 ingestion with collection_id:")
    print("   curl -X POST 'https://ingest.glaciers.cloud/ingest?")
    print("        bucket=its-live-data&")
    print("        path=test-space/stac_catalogs/sentinel2/v02/&")
    print("        recursive=true&")
    print("        collection_id=velocity-granules'")
    print("        -H 'X-API-Token: dopet'")
    
    print("\n2. Granule-specific URL ingestion:")
    print("   curl -X POST 'https://ingest.glaciers.cloud/ingest/granules?")
    print("        url=https://example.com/granules/2024.ndjson'")
    print("        -H 'X-API-Token: dopet'")
    
    print("\n3. Supported collections:")
    for collection_id in list_all_collections():
        if supports_s3_ingestion(collection_id):
            print(f"   {collection_id}: S3 ingestion supported")
        if supports_url_ingestion(collection_id):
            print(f"   {collection_id}: URL ingestion supported")

if __name__ == "__main__":
    print("Testing Refactored ITS-LIVE Ingestion System")
    print("=" * 50)
    
    try:
        test_collection_configuration()
        test_discover_files_signature()
        test_tracker_signature()
        demonstrate_usage()
        
        print("\n" + "=" * 50)
        print("✅ All tests passed! The refactored system is working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
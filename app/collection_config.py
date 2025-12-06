"""Collection configuration for generic ingestion system."""

from typing import Dict, Optional, List
import re

COLLECTION_CONFIGS = {
    "itslive-cubes": {
        "item_file_pattern": "cube-items.json",
        "s3_file_pattern": "*.ndjson",
        "filename_regex": r"^\d{4}$",  # 4-digit years
        "description": "Cloud optimized Zarr cubes with datacube extensions"
    },
    "velocity-mosaics": {
        "item_file_pattern": "velocity-mosaics-items.json", 
        "s3_file_pattern": "*.ndjson",
        "filename_regex": r"^\d{4}$",  # 4-digit years
        "description": "Regional glacier velocity mosaics (annual and static)"
    },
    "velocity-granules": {
        "item_file_pattern": "granule-items.json",
        "ingestion_type": "url_endpoint",
        "description": "Individual Landsat image-pair velocities"
    }
}

def get_collection_name_from_filename(filename: str) -> Optional[str]:
    """Get collection name from item filename using configuration."""
    for collection_id, config in COLLECTION_CONFIGS.items():
        if config.get("item_file_pattern") == filename:
            return collection_id
    return None

def get_collection_config(collection_id: str) -> Optional[Dict]:
    """Get configuration for a specific collection."""
    return COLLECTION_CONFIGS.get(collection_id)

def get_file_pattern_for_collection(collection_id: str) -> Optional[str]:
    """Get S3 file pattern for a collection."""
    config = get_collection_config(collection_id)
    return config.get("s3_file_pattern") if config else None

def get_filename_regex_for_collection(collection_id: str) -> Optional[re.Pattern]:
    """Get compiled filename regex for a collection."""
    config = get_collection_config(collection_id)
    regex_str = config.get("filename_regex")
    return re.compile(regex_str) if regex_str else None

def supports_s3_ingestion(collection_id: str) -> bool:
    """Check if collection supports S3-based ingestion."""
    config = get_collection_config(collection_id)
    return bool(config and config.get("s3_file_pattern"))

def supports_url_ingestion(collection_id: str) -> bool:
    """Check if collection supports URL-based ingestion."""
    config = get_collection_config(collection_id)
    return bool(config and config.get("ingestion_type") == "url_endpoint")

def list_all_collections() -> List[str]:
    """List all configured collection IDs."""
    return list(COLLECTION_CONFIGS.keys())
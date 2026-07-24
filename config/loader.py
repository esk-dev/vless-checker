"""Key loading utilities for VLESS gateway.

This module handles:
- Loading VLESS keys from JSON files
- Extracting best key based on latency
- Unified key extraction logic
"""
import json
import logging
import os
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


def load_key_pool(keys_path: str) -> List[str]:
    """Load all VLESS keys from JSON file.
    
    Recursively extracts keys from nested JSON structures with patterns:
    - `{"top10": [{"key": "vless://..."}]}`
    - `{"top5": [{"key": "vless://..."}]}`
    - Nested dictionaries and lists
    
    Args:
        keys_path: Path to the JSON file containing VLESS keys
        
    Returns:
        List of VLESS key strings (duplicates removed, order preserved)
    """
    try:
        if not os.path.exists(keys_path):
            logger.error(f"Keys file not found: {keys_path}")
            return []
        
        with open(keys_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        pool = []
        
        def extract_keys(obj):
            """Recursively extract keys from nested JSON structure."""
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ["top10", "top5"] and isinstance(v, list):
                        for entry in v:
                            if isinstance(entry, dict) and "key" in entry:
                                pool.append(entry["key"])
                    else:
                        extract_keys(v)
            elif isinstance(obj, list):
                for item in obj:
                    extract_keys(item)
        
        extract_keys(data)
        # Remove duplicates while preserving order
        return list(dict.fromkeys(pool))
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse keys JSON: {e}")
        return []
    except Exception as e:
        logger.error(f"Failed to load key pool: {e}")
        return []


def get_best_key(keys_path: str) -> Optional[str]:
    """Get best key from KEYS_JSON_PATH file based on lowest latency.
    
    Reads JSON file and extracts the best working key based on latency.
    The key with lowest latency_ms is selected as the best.
    If no latency info available, returns first key found.
    
    Args:
        keys_path: Path to keys.json file
        
    Returns:
        Best key string (lowest latency) or None if no keys found
    """
    try:
        if not os.path.exists(keys_path):
            logger.error(f"Keys file not found: {keys_path}")
            return None
        
        with open(keys_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        best_key = None
        best_latency = float('inf')
        
        def extract_key_with_latency(obj, path=""):
            """Recursively extract keys with their latency info."""
            nonlocal best_key, best_latency
            
            if isinstance(obj, dict):
                # Check for 'best' field directly
                if "best" in obj and isinstance(obj["best"], str):
                    key = obj["best"]
                    if key and best_key is None:
                        best_key = key
                    return
                
                # Check top10/top5 for keys with latency
                for top_key in ["top10", "top5"]:
                    if top_key in obj and isinstance(obj[top_key], list):
                        for entry in obj[top_key]:
                            if isinstance(entry, dict) and "key" in entry:
                                key = entry["key"]
                                latency = entry.get("latency_ms", float('inf'))
                                if isinstance(latency, (int, float)) and latency < best_latency:
                                    best_latency = latency
                                    best_key = key
                
                # Recursively check nested dicts
                for key_name, value in obj.items():
                    if key_name not in ["top10", "top5"]:
                        extract_key_with_latency(value, f"{path}.{key_name}" if path else key_name)
            
            elif isinstance(obj, list):
                for item in obj:
                    extract_key_with_latency(item, path)
        
        extract_key_with_latency(data)
        
        if best_key:
            if best_latency != float('inf'):
                logger.info(f"Best key from {keys_path}: {best_key[:50]}... (latency: {best_latency:.1f}ms)")
            else:
                logger.info(f"Best key from {keys_path}: {best_key[:50]}...")
        else:
            logger.info(f"No keys found in {keys_path}")
        
        return best_key
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse keys JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to get best key from keys JSON: {e}")
        return None


def load_keys_with_latency(keys_path: str) -> List[Dict[str, Any]]:
    """Load all keys with their latency information.
    
    Args:
        keys_path: Path to keys.json file
        
    Returns:
        List of dicts with 'key' and 'latency_ms' fields
    """
    try:
        if not os.path.exists(keys_path):
            logger.error(f"Keys file not found: {keys_path}")
            return []
        
        with open(keys_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        keys_with_latency = []
        
        def extract_keys_with_latency(obj, path=""):
            """Recursively extract keys with latency info."""
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ["top10", "top5"] and isinstance(v, list):
                        for entry in v:
                            if isinstance(entry, dict) and "key" in entry:
                                keys_with_latency.append({
                                    "key": entry["key"],
                                    "latency_ms": entry.get("latency_ms", float('inf'))
                                })
                    else:
                        extract_keys_with_latency(v)
            elif isinstance(obj, list):
                for item in obj:
                    extract_keys_with_latency(item)
        
        extract_keys_with_latency(data)
        return keys_with_latency
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse keys JSON: {e}")
        return []
    except Exception as e:
        logger.error(f"Failed to load keys with latency: {e}")
        return []

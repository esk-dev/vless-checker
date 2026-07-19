"""Gateway monitoring for VLESS key rotation.

This module handles:
- Loading VLESS keys from JSON files
- Checking connection health
- Main monitoring loop with automatic key rotation
"""
import json
import asyncio
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)


class GatewayMonitor:
    """Monitor gateway connectivity and handle key rotation.
    
    This class handles:
    - Loading keys from JSON files
    - Checking connection health to VLESS servers
    - Automatic key rotation when connections fail
    - Multi-client mode support
    
    Args:
        keys_path: Path to the JSON file containing VLESS keys
        xray_manager: XrayManager instance for config generation
    """
    
    def __init__(self, keys_path: str, xray_manager: 'XrayManager'):
        """Initialize the gateway monitor.
        
        Args:
            keys_path: Path to the JSON file containing VLESS keys
            xray_manager: XrayManager instance for config generation
        """
        self.keys_path = keys_path
        self.xray_manager = xray_manager
        self.key_pool: List[str] = []
        self.current_index = 0
    
    def load_key_pool(self) -> bool:
        """Load VLESS keys from JSON file.
        
        Returns:
            True if keys were loaded successfully
        """
        try:
            if not os.path.exists(self.keys_path):
                logger.error(f"Keys file not found: {self.keys_path}")
                return False
            
            with open(self.keys_path, "r", encoding="utf-8") as f:
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
            self.key_pool = list(dict.fromkeys(pool))
            
            logger.info(f"Loaded {len(self.key_pool)} keys from {self.keys_path}")
            return len(self.key_pool) > 0
        
        except Exception as e:
            logger.error(f"Failed to load key pool: {e}")
            return False
    
    async def check_connection(self, key: str) -> bool:
        """Check if a VLESS key is reachable.
        
        Args:
            key: VLESS key string to check
            
        Returns:
            True if connection is successful
        """
        vless_info = self.xray_manager.parse_vless_key(key)
        if not vless_info:
            return False
        
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(vless_info["address"], vless_info["port"]),
                timeout=5.0  # CHECK_TIMEOUT - should be imported from config
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception as e:
            logger.debug(f"Connection check failed for {vless_info['address']}: {e}")
            return False
    
    async def run(self):
        """Main monitoring loop.
        
        This method handles:
        - Loading client settings for multi-client mode
        - Starting single-key mode with key rotation
        - Running the monitoring loop indefinitely
        """
        logger.info("=== STEP 1: INITIALIZATION ===")
        
        # Load client settings for multi-client mode
        # This should be imported from config
        _load_client_settings()
        
        logger.info(f"Current GATEWAY_MODE: {GATEWAY_MODE}")
        
        if GATEWAY_MODE == "multi":
            logger.info("=== STEP 2: MULTI-CLIENT MODE ===")
            # Multi-client mode: no key rotation, all clients connected simultaneously
            logger.info("Starting in multi-client mode - all clients connected simultaneously")
            if not await self.xray_manager.apply_config():
                logger.error("Multi-client configuration failed.")
                return
            logger.info("Multi-client gateway started. All clients connected.")
            # Keep running without rotation
            while True:
                await asyncio.sleep(3600)  # Sleep without checks
        else:
            logger.info("=== STEP 2: SINGLE-KEY MODE ===")
            # Single-key mode: run with key rotation
            logger.info("Loading key pool from JSON file...")
            if not self.load_key_pool():
                logger.error("No keys available in pool. Exiting.")
                return
            
            logger.info(f"Key pool loaded successfully. Total keys: {len(self.key_pool)}")
            logger.info(f"Initializing with first key: {self.key_pool[self.current_index][:30]}...")
            logger.info("=== STEP 3: APPLY INITIAL CONFIG ===")
            if not await self.xray_manager.apply_config(self.key_pool[self.current_index]):
                logger.error("Initial configuration failed.")
                return

            logger.info("=== STEP 4: START GATEWAY MONITOR ===")
            logger.info("Gateway monitor started.")

            while True:
                if not self.key_pool:
                    logger.error("Key pool is empty. Exiting.")
                    return
                current_key = self.key_pool[self.current_index]
                is_alive = await self.check_connection(current_key)

                if not is_alive:
                    logger.warning(f"⚠️ Connection lost! Current key is dead: {current_key[:30]}...")
                    
                    self.current_index = (self.current_index + 1) % len(self.key_pool)
                    new_key = self.key_pool[self.current_index]
                    
                    logger.info(f"🔄 Rotating to next key: {new_key[:30]}...")
                    logger.info("=== STEP 5: APPLY NEW CONFIG ===")
                    success = await self.xray_manager.apply_config(new_key)
                    
                    if success:
                        logger.info("✅ Rotation successful.")
                    else:
                        logger.error("❌ Rotation failed! Retrying with backoff...")
                        await asyncio.sleep(1)  # Small delay before retrying
                        continue
                else:
                    logger.info(f"🟢 Connection healthy. Node: {self.xray_manager.parse_vless_key(current_key)['address']}")

                await asyncio.sleep(10.0)  # CHECK_INTERVAL - should be imported from config


# Import these from config for proper module separation
# GATEWAY_MODE and _load_client_settings should be defined in config module
GATEWAY_MODE = "single"  # Default, should be imported from config

def _load_client_settings():
    """Load client settings from environment variables.
    
    This should be moved to config module for proper separation.
    """
    pass  # Placeholder - implementation should be in config module

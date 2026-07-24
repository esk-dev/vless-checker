"""Gateway monitoring for VLESS key rotation.

This module handles:
- Loading VLESS keys from JSON files
- Checking connection health
- Main monitoring loop with automatic key rotation
"""
import asyncio
import logging
from typing import List, Optional

from config.loader import load_key_pool, get_best_key
from monitor.rotator import KeyRotator

logger = logging.getLogger(__name__)

# Import configuration values
try:
    from gateway_manager import CHECK_TIMEOUT, CHECK_INTERVAL, GATEWAY_MODE
except ImportError:
    # Fallback to defaults if gateway_manager is not available
    CHECK_TIMEOUT = 5.0
    CHECK_INTERVAL = 10.0
    GATEWAY_MODE = "single"


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
        self.rotator: Optional[KeyRotator] = None
        self._loaded = False
    
    def load_key_pool(self) -> bool:
        """Load VLESS keys from JSON file.
        
        Returns:
            True if keys were loaded successfully
        """
        try:
            self.key_pool = load_key_pool(self.keys_path)
            self.rotator = KeyRotator(self.key_pool)
            self._loaded = len(self.key_pool) > 0
            logger.info(f"Loaded {len(self.key_pool)} keys from {self.keys_path}")
            return self._loaded
        
        except Exception as e:
            logger.error(f"Failed to load key pool: {e}")
            self._loaded = False
            return False
    
    def get_best_key(self) -> Optional[str]:
        """Get best key from JSON file based on latency.
        
        Returns:
            Best VLESS key string or None if no keys found
        """
        return get_best_key(self.keys_path)
    
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
                timeout=CHECK_TIMEOUT
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
            if self.rotator:
                current_key = self.rotator.get_current_key()
                logger.info(f"Initializing with first key: {current_key[:30] if current_key else ''}...")
            
            logger.info("=== STEP 3: APPLY INITIAL CONFIG ===")
            if self.rotator:
                initial_key = self.rotator.get_current_key()
                if not initial_key:
                    logger.error("No initial key available.")
                    return
                if not await self.xray_manager.apply_config(initial_key):
                    logger.error("Initial configuration failed.")
                    return
            else:
                logger.error("Key rotator not initialized.")
                return

            logger.info("=== STEP 4: START GATEWAY MONITOR ===")
            logger.info("Gateway monitor started.")

            while True:
                if not self.rotator or not self.key_pool:
                    logger.error("Key pool is empty or rotator not initialized. Exiting.")
                    return
                current_key = self.rotator.get_current_key()
                if not current_key:
                    logger.error("No current key available.")
                    return
                is_alive = await self.check_connection(current_key)

                if not is_alive:
                    logger.warning(f"⚠️ Connection lost! Current key is dead: {current_key[:30]}...")
                    self.rotator.rotate()
                    new_key = self.rotator.get_current_key()
                    
                    logger.info(f"🔄 Rotating to next key: {new_key[:30] if new_key else ''}...")
                    logger.info("=== STEP 5: APPLY NEW CONFIG ===")
                    success = await self.xray_manager.apply_config(new_key) if new_key else False
                    
                    if success:
                        logger.info("✅ Rotation successful.")
                    else:
                        logger.error("❌ Rotation failed! Retrying with backoff...")
                        await asyncio.sleep(1)  # Small delay before retrying
                        continue
                else:
                    vless_info = self.xray_manager.parse_vless_key(current_key)
                    node = vless_info["address"] if vless_info else "unknown"
                    logger.info(f"🟢 Connection healthy. Node: {node}")

                await asyncio.sleep(CHECK_INTERVAL)

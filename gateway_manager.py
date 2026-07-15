import json
import os
import subprocess
import asyncio
import logging
import time
import re
from datetime import datetime
from urllib.parse import unquote

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("gateway_manager.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration (Ideally loaded from environment variables)
KEYS_JSON_PATH = os.getenv("KEYS_JSON_PATH", "docs/keys.json")
XRAY_CONFIG_PATH = os.getenv("XRAY_CONFIG_PATH", "xray_config.json")
CHECK_TIMEOUT = float(os.getenv("CHECK_TIMEOUT", 5.0))
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL", 10.0))

# Shadowsocks Settings for Inbound
SS_INBOUND_PORT = int(os.getenv("SS_INBOUND_PORT", 8388))
SS_PASSWORD = os.getenv("SS_PASSWORD", "secure_password_123")
SS_METHOD = os.getenv("SS_METHOD", "2022-blake3-aes-128-gcm")

class XrayManager:
    def __init__(self, config_path, xray_service_name="xray"):
        self.config_path = config_path
        self.xray_service_name = xray_service_name
        self.current_key = None

    def parse_vless_key(self, key):
        """Parses a VLESS key into a dictionary for Xray outbound configuration."""
        try:
            content = key[len("vless://"):]
            if "@" not in content:
                return None
            
            uuid, remainder = content.split("@", 1)
            parts = re.split(r'[?#]', remainder)
            host_port = parts[0]
            
            if ":" in host_port:
                host, port = host_port.rsplit(":", 1)
                port = int(port)
            else:
                host = host_port
                port = 443
            
            params = {}
            if len(parts) > 1:
                query_str = parts[1]
                for pair in query_str.split("&"):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        params[k] = v
            
            fragment = ""
            if len(parts) > 2:
                fragment = parts[2]

            return {
                "uuid": uuid,
                "address": host,
                "port": port,
                "encryption": params.get("encryption", "none"),
                "security": params.get("security", "tls"),
                "sni": params.get("sni") or fragment,
                "type": "vless"
            }
        except Exception as e:
            logger.error(f"Failed to parse VLESS key: {e}")
            return None

    def generate_config(self, vless_info):
        """Generates the full Xray JSON configuration including Shadowsocks Inbound."""
        config = {
            "log": {
                "loglevel": "warning"
            },
            "inbounds": [
                {
                    "port": 1080,
                    "protocol": "socks",
                    "settings": {
                        "auth": "noauth",
                        "udp": True
                    },
                    "sniffing": {
                        "enabled": True,
                        "destOverride": ["http", "tls"]
                    }
                },
                {
                    "port": SS_INBOUND_PORT,
                    "protocol": "shadowsocks",
                    "settings": {
                        "method": SS_METHOD,
                        "password": SS_PASSWORD
                    }
                }
            ],
            "outbounds": [
                {
                    "protocol": vless_info["type"],
                    "settings": {
                        "vless": {
                            "users": [
                                {
                                    "id": vless_info["uuid"],
                                    "encryption": vless_info["encryption"],
                                    "flow": "xtls-rprx-vision" if vless_info["security"] == "tls" else ""
                                }
                            ]
                        }
                    },
                    "streamSettings": {
                        "network": "tcp",
                        "security": vless_info["security"],
                        "tlsSettings": {
                            "serverName": vless_info["sni"]
                        } if vless_info["security"] == "tls" else None
                    },
                    "tag": "proxy"
                },
                {
                    "protocol": "freedom",
                    "settings": {},
                    "tag": "direct"
                },
                {
                    "protocol": "blackhole",
                    "settings": {},
                    "tag": "blocked"
                }
            ],
            "routing": {
                "domainStrategy": "IPIfNonMatch",
                "rules": [
                    {
                        "type": "field",
                        "domain": ["geosite:ru"],
                        "outboundTag": "direct"
                    },
                    {
                        "type": "field",
                        "ip": ["geoip:ru"],
                        "outboundTag": "direct"
                    },
                    {
                        "type": "field",
                        "network": "tcp,udp",
                        "outboundTag": "proxy"
                    }
                ]
            }
        }
        # Clean up None values in streamSettings
        if config["outbounds"][0]["streamSettings"]["tlsSettings"] is None:
            del config["outbounds"][0]["streamSettings"]["tlsSettings"]
            
        return config

    async def apply_config(self, key):
        vless_info = self.parse_vless_key(key)
        if not vless_info:
            logger.error("Could not parse key for configuration.")
            return False

        config = self.generate_config(vless_info)
        
        try:
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=2)
            
            logger.info(f"New config written to {self.config_path}")
            logger.info(f"Restarting Xray service: {self.xray_service_name}...")
            
            # In production, use:
            # await asyncio.create_subprocess_shell(f"sudo systemctl restart {self.xray_service_name}")
            await asyncio.sleep(1) 
            
            self.current_key = key
            return True
        except Exception as e:
            logger.error(f"Failed to apply Xray config: {e}")
            return False

class GatewayMonitor:
    def __init__(self, keys_path, xray_manager):
        self.keys_path = keys_path
        self.xray_manager = xray_manager
        self.key_pool = []
        self.current_index = 0

    def load_key_pool(self):
        try:
            if not os.path.exists(self.keys_path):
                logger.error(f"Keys file not found: {self.keys_path}")
                return False
            with open(self.keys_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            pool = []
            def extract_keys(obj):
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
            self.key_pool = list(dict.fromkeys(pool))
            logger.info(f"Loaded {len(self.key_pool)} keys from {self.keys_path}")
            return len(self.key_pool) > 0
        except Exception as e:
            logger.error(f"Failed to load key pool: {e}")
            return False

    async def check_connection(self, key):
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
        if not self.load_key_pool():
            logger.error("No keys available in pool. Exiting.")
            return

        logger.info(f"Initializing with first key: {self.key_pool[self.current_index][:30]}...")
        if not await self.xray_manager.apply_config(self.key_pool[self.current_index]):
            logger.error("Initial configuration failed.")
            return

        logger.info("Gateway monitor started.")

        while True:
            current_key = self.key_pool[self.current_index]
            is_alive = await self.check_connection(current_key)

            if not is_alive:
                logger.warning(f"⚠️ Connection lost! Current key is dead: {current_key[:30]}...")
                
                self.current_index = (self.current_index + 1) % len(self.key_pool)
                new_key = self.key_pool[self.current_index]
                
                logger.info(f"🔄 Rotating to next key: {new_key[:30]}...")
                success = await self.xray_manager.apply_config(new_key)
                
                if success:
                    logger.info("✅ Rotation successful.")
                else:
                    logger.error("❌ Rotation failed! Trying next key immediately...")
                    continue
            else:
                logger.info(f"🟢 Connection healthy. Node: {self.xray_manager.parse_vless_key(current_key)['address']}")

            await asyncio.sleep(CHECK_INTERVAL)

async def main():
    xray_manager = XrayManager(XRAY_CONFIG_PATH)
    monitor = GatewayMonitor(KEYS_JSON_PATH, xray_manager)
    await monitor.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Gateway monitor stopped by user.")
    except Exception as e:
        logger.critical(f"Gateway monitor crashed: {e}")

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
# We only use StreamHandler so that logs are captured by systemd journal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration (Ideally loaded from environment variables)
# We use absolute paths to avoid PermissionError when running as a service
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

KEYS_JSON_PATH = os.getenv("KEYS_JSON_PATH", os.path.join(BASE_DIR, "docs/keys.json"))
# Default path set to standard Xray system config location
XRAY_CONFIG_PATH = os.getenv("XRAY_CONFIG_PATH", "/usr/local/etc/xray/config.json")
CHECK_TIMEOUT = float(os.getenv("CHECK_TIMEOUT", 5.0))
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL", 10.0))

# Shadowsocks Settings for Inbound
SS_INBOUND_PORT = int(os.getenv("SS_INBOUND_PORT", 8388))
SS_PASSWORD = os.getenv("SS_PASSWORD", "secure_password_123")
SS_METHOD = os.getenv("SS_METHOD", "2022-blake3-aes-128-gcm")

# Multi-client Gateway Settings
GATEWAY_MODE = os.getenv("GATEWAY_MODE", "single")  # 'single' or 'multi'
XRAY_OUTBOUND_NETWORK = os.getenv("XRAY_OUTBOUND_NETWORK", "tcp")
XRAY_SECURITY = os.getenv("XRAY_SECURITY", "tls")
XRAY_INBOUND_SOCKS_PORT = int(os.getenv("XRAY_INBOUND_SOCKS_PORT", 1080))

# Client-specific settings (parsed from comma-separated values)
CLIENT_UUIDS = []
CLIENT_KEYS = []


def _parse_comma_separated_env(env_name, default=None):
    """Parse a comma-separated environment variable into a list."""
    value = os.getenv(env_name, "")
    if not value:
        return default if default else []
    return [item.strip() for item in value.split(",") if item.strip()]


def _load_client_settings():
    """Load client UUIDs and keys from environment variables."""
    global CLIENT_UUIDS, CLIENT_KEYS
    
    if GATEWAY_MODE == "multi":
        CLIENT_UUIDS = _parse_comma_separated_env("CLIENT_UUIDS")
        CLIENT_KEYS = _parse_comma_separated_env("CLIENT_KEYS")
        
        if len(CLIENT_UUIDS) != len(CLIENT_KEYS):
            logger.warning(f"UUID count ({len(CLIENT_UUIDS)}) != Key count ({len(CLIENT_KEYS)})")
        
        logger.info(f"Loaded {len(CLIENT_UUIDS)} client(s) for multi-client mode")
    else:
        logger.info("Running in single-key mode")


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

    def _build_vless_outbound(self, vless_info, tag, client_uuid=None):
        """Build a single VLESS outbound configuration."""
        outbound = {
            "protocol": vless_info["type"],
            "settings": {
                "vless": {
                    "users": [
                        {
                            "id": vless_info["uuid"] if client_uuid is None else client_uuid,
                            "encryption": vless_info["encryption"],
                            "flow": "xtls-rprx-vision" if vless_info["security"] == "tls" else ""
                        }
                    ]
                }
            },
            "streamSettings": {
                "network": XRAY_OUTBOUND_NETWORK,
                "security": vless_info["security"],
                "tlsSettings": {
                    "serverName": vless_info["sni"]
                } if vless_info["security"] == "tls" else None
            },
            "tag": tag
        }
        
        # Clean up None values in streamSettings
        if outbound["streamSettings"]["tlsSettings"] is None:
            del outbound["streamSettings"]["tlsSettings"]
            
        return outbound

    def generate_config(self, vless_info=None, client_vless_infos=None):
        """Generates the full Xray JSON configuration including Shadowsocks Inbound."""
        
        # Build inbounds
        inbounds = [
            {
                "port": XRAY_INBOUND_SOCKS_PORT,
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
        ]
        
        # Build outbounds
        outbounds = []
        routing_rules = []
        
        if GATEWAY_MODE == "multi" and client_vless_infos:
            # Multi-client mode: create multiple outbounds with routing rules
            for i, (tag, info) in enumerate(client_vless_infos.items()):
                outbound = self._build_vless_outbound(info, tag=f"proxy-{i}")
                outbounds.append(outbound)
                
                # Add routing rule to use this outbound for this client's UUID
                routing_rules.append({
                    "type": "field",
                    "user": [info["uuid"]],
                    "outboundTag": tag
                })
            
            # Default fallback rule
            routing_rules.append({
                "type": "field",
                "network": "tcp,udp",
                "outboundTag": "proxy-0"  # Default to first proxy
            })
            
        else:
            # Single-key mode
            outbound = self._build_vless_outbound(vless_info, "proxy")
            outbounds.append(outbound)
            
            # Single rule for all traffic
            routing_rules.append({
                "type": "field",
                "network": "tcp,udp",
                "outboundTag": "proxy"
            })
        
        # Add direct and blocked outbounds
        outbounds.extend([
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
        ])
        
        config = {
            "log": {
                "loglevel": "warning"
            },
            "inbounds": inbounds,
            "outbounds": outbounds,
            "routing": {
                "domainStrategy": "IPIfNonMatch",
                "rules": routing_rules + [
                    {
                        "type": "field",
                        "domain": ["geosite:ru"],
                        "outboundTag": "direct"
                    },
                    {
                        "type": "field",
                        "ip": ["geoip:ru"],
                        "outboundTag": "direct"
                    }
                ]
            }
        }
        
        return config

    async def apply_config(self, key=None):
        """Apply Xray configuration. For multi-client mode, key is ignored."""
        if GATEWAY_MODE == "multi":
            client_vless_infos = {}
            
            # Build vless info for each client
            for i, key_str in enumerate(CLIENT_KEYS):
                vless_info = self.parse_vless_key(key_str)
                if vless_info:
                    client_vless_infos[f"proxy-{i}"] = vless_info
                else:
                    logger.error(f"Failed to parse client key {i}: {key_str}")
                    continue
            
            if not client_vless_infos:
                logger.error("Could not parse any client keys for configuration.")
                return False
            
            config = self.generate_config(client_vless_infos=client_vless_infos)
            
        else:
            # Single-key mode
            if not key:
                logger.error("No key provided for single-key mode.")
                return False
            
            vless_info = self.parse_vless_key(key)
            if not vless_info:
                logger.error("Could not parse key for configuration.")
                return False
            
            config = self.generate_config(vless_info=vless_info)
        
        try:
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=2)
            
            logger.info(f"New config written to {self.config_path}")
            logger.info(f"Restarting Xray service: {self.xray_service_name}...")
            
            # In production, use:
            await asyncio.create_subprocess_shell(f"sudo systemctl restart {self.xray_service_name}")
            
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
        # Load client settings for multi-client mode
        _load_client_settings()
        
        if GATEWAY_MODE == "multi":
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
            # Single-key mode: run with key rotation
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

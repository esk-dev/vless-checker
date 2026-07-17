import json
import os
import subprocess
import asyncio
import logging
import time
import re
import sys
from datetime import datetime
from urllib.parse import unquote
import base64

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed, environment variables will be loaded from system
    pass

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


def generate_shadowsocks_key(ss_method: str = None, ss_password: str = None) -> str:
    """
    Generate a Shadowsocks shareable link for Outline clients.
    
    Format: ss://[BASE64(method:password)]@[IP]:PORT#TAG
    
    Args:
        ss_method: Encryption method (e.g., 'aes-256-gcm', '2022-blake3-aes-128-gcm')
        ss_password: Password for the Shadowsocks connection
        
    Returns:
        A shareable Shadowsocks URL for Outline clients
    """
    method = ss_method or SS_METHOD
    password = ss_password or SS_PASSWORD
    
    # Combine method and password with colon
    auth_string = f"{method}:{password}"
    
    # Encode to Base64
    encoded_auth = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
    
    # Get VPS IP from environment or use placeholder
    # In production, this would be the server's public IP
    vps_ip = os.getenv("VPS_IP", "YOUR_VPS_IP_ADDRESS")
    
    # Port for Shadowsocks (from environment or default)
    ss_port = int(os.getenv("SS_INBOUND_PORT", 8338))
    
    # Create the shareable link
    ss_link = f"ss://{encoded_auth}@{vps_ip}:{ss_port}#MyVLESSRotator"
    
    logger.info(f"Generated Shadowsocks key: {ss_link[:30]}...")
    
    return ss_link


def generate_shadowsocks_key_with_params(
    ss_method: str = None,
    ss_password: str = None,
    vps_ip: str = None,
    ss_port: int = None
) -> str:
    """
    Generate a Shadowsocks shareable link for Outline clients with custom parameters.
    
    Format: ss://[BASE64(method:password)]@[IP]:PORT#TAG
    
    Args:
        ss_method: Encryption method (e.g., 'aes-256-gcm', '2022-blake3-aes-128-gcm')
        ss_password: Password for the Shadowsocks connection
        vps_ip: IP address of your VPS/server
        ss_port: Port for the Shadowsocks service (default: 8338)
        
    Returns:
        A shareable Shadowsocks URL for Outline clients
    """
    method = ss_method or SS_METHOD
    password = ss_password or SS_PASSWORD
    ip = vps_ip or os.getenv("VPS_IP", "YOUR_VPS_IP_ADDRESS")
    port = ss_port or int(os.getenv("SS_INBOUND_PORT", 8388))
    
    # Combine method and password with colon
    auth_string = f"{method}:{password}"
    
    # Encode to Base64
    encoded_auth = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
    
    # Create the shareable link
    ss_link = f"ss://{encoded_auth}@{ip}:{port}#MyVLESSRotator"
    
    logger.info(f"Generated Shadowsocks key with params")
    
    return ss_link


def log_environment_variables():
    """Log all environment variables for debugging."""
    logger.info("=" * 60)
    logger.info("=== ENVIRONMENT VARIABLES DUMP START ===")
    logger.info("=" * 60)
    
    env_vars = [
        "KEYS_JSON_PATH",
        "XRAY_CONFIG_PATH",
        "CHECK_TIMEOUT",
        "CHECK_INTERVAL",
        "GATEWAY_MODE",
        "SS_INBOUND_PORT",
        "SS_PASSWORD",
        "SS_METHOD",
        "XRAY_OUTBOUND_NETWORK",
        "XRAY_SECURITY",
        "XRAY_INBOUND_SOCKS_PORT",
        "VPS_IP",
        "CLIENT_UUIDS",
        "CLIENT_KEYS"
    ]
    
    for var in env_vars:
        value = os.getenv(var, "NOT_SET")
        if "PASSWORD" in var or "KEY" in var:
            # Mask sensitive data
            if len(value) > 4:
                masked = value[:2] + "*" * (len(value) - 4) + value[-2:]
            else:
                masked = "***"
            logger.info(f"{var}={masked}")
        else:
            logger.info(f"{var}={value}")
    
    logger.info("=" * 60)
    logger.info("=== ENVIRONMENT VARIABLES DUMP END ===")
    logger.info("=" * 60)


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

# Validate SS_PASSWORD for 2022 methods
if SS_METHOD and "2022" in SS_METHOD.lower():
    if len(SS_PASSWORD.encode('utf-8')) != 16:
        logger.warning(f"SS_PASSWORD should be exactly 16 bytes for 2022 methods. Current length: {len(SS_PASSWORD.encode('utf-8'))} bytes")

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

            result = {
                "uuid": uuid,
                "address": host,
                "port": port,
                "encryption": params.get("encryption", "none"),
                "security": params.get("security", "tls"),
                "sni": params.get("sni") or fragment,
                "type": "vless"
            }
            
            # Add REALITY-specific parameters if available
            if params.get("security") == "reality":
                result["realitySettings"] = {
                    "publicKey": params.get("pbk", ""),
                    "shortId": params.get("sid", ""),
                    "serverName": params.get("sni") or fragment,
                    "spiderX": params.get("spiderX", "")
                }
            
            return result
        except Exception as e:
            logger.error(f"Failed to parse VLESS key: {e}")
            return None

    def _build_vless_outbound(self, vless_info, tag, client_uuid=None):
        """Build a single VLESS outbound configuration."""
        security = vless_info["security"]
        flow = vless_info.get("flow", "")
        
        outbound = {
            "protocol": vless_info["type"],
            "settings": {
                "vnext": [
                    {
                        "address": vless_info["address"],
                        "port": vless_info["port"],
                        "users": [
                            {
                                "id": vless_info["uuid"] if client_uuid is None else client_uuid,
                                "encryption": vless_info["encryption"],
                                "flow": flow
                            }
                        ]
                    }
                ]
            },
            "streamSettings": {
                "network": XRAY_OUTBOUND_NETWORK,
                "security": security
            } if security in ["tls", "reality"] else None,
            "tag": tag
        }
        
        # Add TLS settings if security is tls
        if security == "tls":
            outbound["streamSettings"]["tlsSettings"] = {
                "serverName": vless_info["sni"]
            }
        elif security == "reality":
            # Use REALITY settings from parsed VLESS key
            reality_settings = vless_info.get("realitySettings", {})
            outbound["streamSettings"]["realitySettings"] = {
                "serverName": reality_settings.get("serverName", vless_info["sni"]),
                "publicKey": reality_settings.get("publicKey", ""),
                "shortId": reality_settings.get("shortId", ""),
                "spiderX": reality_settings.get("spiderX", "")
            }
        
        # Clean up None values in streamSettings
        if outbound["streamSettings"] is None:
            del outbound["streamSettings"]
        elif "tlsSettings" in outbound["streamSettings"] and outbound["streamSettings"]["tlsSettings"] is None:
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
                logger.debug(f"Added routing rule for user {info['uuid']} -> {tag}")
            
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
        
        # Build routing rules - direct rules MUST come before proxy rules!
        direct_rules = [
            #ru-domains - direct
            {
                "type": "field",
                "domain": ["geosite:ru"],
                "outboundTag": "direct"
            },
            #ru-IPs - direct
            {
                "type": "field",
                "ip": ["geoip:ru"],
                "outboundTag": "direct"
            },
            #Blocked sites - direct (block or direct)
            {
                "type": "field",
                "domain": ["geosite:ru-blocked"],
                "outboundTag": "direct"
            }
        ]
        
        # Add blocked outbound for truly blocked sites if needed
        config = {
            "log": {
                "loglevel": "warning"
            },
            "inbounds": inbounds,
            "outbounds": outbounds,
            "routing": {
                "domainStrategy": "IPIfNonMatch",
                "implicitIPSetMatch": True,
                "rules": direct_rules + routing_rules
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
            # Log the full config for debugging
            logger.debug(f"Generated multi-client config: {json.dumps(config, indent=2)}")
            
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
        
        # Log the full config for debugging
        logger.info("=== XRAY CONFIGURATION DUMP START ===")
        logger.info(f"Config path: {self.config_path}")
        logger.info(f"Generated config JSON:\n{json.dumps(config, indent=2)}")
        logger.info("=== XRAY CONFIGURATION DUMP END ===")
        
        # Verify directory exists and is writable
        config_dir = os.path.dirname(self.config_path)
        logger.info(f"Checking config directory: {config_dir}")
        if os.path.exists(config_dir):
            logger.info(f"Config directory exists: {config_dir}")
        else:
            logger.warning(f"Config directory does not exist: {config_dir}")
        
        # Check if file exists before overwriting
        if os.path.exists(self.config_path):
            logger.info(f"Existing config file found at {self.config_path}")
            try:
                with open(self.config_path, "r") as f:
                    old_content = f.read()
                logger.info(f"Old config size: {len(old_content)} bytes")
            except Exception as e:
                logger.error(f"Could not read old config: {e}")
        
        # Step 1: Write config to file
        logger.info(f"STEP 1: Attempting to write config to {self.config_path}")
        try:
            logger.info(f"Opening file for writing: {self.config_path}")
            with open(self.config_path, "w") as f:
                logger.info(f"File opened successfully, writing JSON...")
                json.dump(config, f, indent=2)
                logger.info(f"JSON written successfully")
            
            logger.info(f"STEP 2: Verifying written config")
            logger.info(f"SUCCESS: New config written to {self.config_path}")
            
            # Verify the file was written correctly
            try:
                logger.info(f"Opening file for verification read: {self.config_path}")
                with open(self.config_path, "r") as f:
                    content = f.read()
                logger.info(f"VERIFICATION: Read back config file, size: {len(content)} bytes")
                logger.info(f"VERIFICATION: First 200 chars: {content[:200]}")
                logger.info(f"VERIFICATION: File path resolved to: {os.path.realpath(self.config_path)}")
            except Exception as e:
                logger.error(f"VERIFICATION FAILED: Could not read back file: {e}")
            
            logger.info(f"STEP 3: Restarting Xray service: {self.xray_service_name}...")
            
            # In production, use:
            logger.info(f"STEP 4: Executing systemctl restart xray...")
            await asyncio.create_subprocess_shell(f"sudo systemctl restart {self.xray_service_name}")
            logger.info(f"STEP 5: Xray restart command completed (async)")
            
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
        logger.info("=== STEP 1: INITIALIZATION ===")
        # Load client settings for multi-client mode
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
                        logger.error("❌ Rotation failed! Trying next key immediately...")
                        continue
                else:
                    logger.info(f"🟢 Connection healthy. Node: {self.xray_manager.parse_vless_key(current_key)['address']}")

                await asyncio.sleep(CHECK_INTERVAL)


async def main():
    logger.info("=" * 60)
    logger.info("=== GATEWAY MANAGER STARTING ===")
    logger.info("=" * 60)
    
    # Log all environment variables
    log_environment_variables()
    
    xray_manager = XrayManager(XRAY_CONFIG_PATH)
    monitor = GatewayMonitor(KEYS_JSON_PATH, xray_manager)
    await monitor.run()


def print_usage():
    """Print usage information for command-line options."""
    usage = """
Usage: python3 gateway_manager.py [OPTIONS]

Options:
  --gen-ss                Generate a Shadowsocks key for Outline (using .env settings)
  --gen-ss-full METHOD:PASS@IP:PORT
                          Generate a Shadowsocks key with full parameters
                          Format: METHOD:PASSWORD@IP:PORT
                          Example: aes-256-gcm:mypassword@192.168.1.100:443
  -h, --help              Show this help message

Examples:
  python3 gateway_manager.py --gen-ss
  python3 gateway_manager.py --gen-ss-full "aes-256-gcm:my_password@192.168.1.100:443"
"""
    print(usage)


def handle_cli_args():
    """Handle command-line arguments for key generation."""
    import sys
    
    if len(sys.argv) < 2:
        return None
    
    arg = sys.argv[1]
    
    if arg in ("-h", "--help"):
        print_usage()
        return "help"
    
    if arg == "--gen-ss":
        print("Generating Shadowsocks key from .env settings...")
        print(f"  Method: {SS_METHOD}")
        print(f"  Password: {SS_PASSWORD}")
        print(f"  VPS IP: {os.getenv('VPS_IP', 'YOUR_VPS_IP_ADDRESS')}")
        print(f"  Port: {os.getenv('SS_INBOUND_PORT', '443')}")
        print()
        ss_link = generate_shadowsocks_key()
        print(f"\n✅ Generated Shadowsocks link:\n{ss_link}")
        return "gen-ss"
    
    if arg == "--gen-ss-full":
        if len(sys.argv) < 3:
            print("❌ Error: --gen-ss-full requires a parameter in format METHOD:PASS@IP:PORT")
            print("Example: aes-256-gcm:my_password@192.168.1.100:443")
            return None
        param = sys.argv[2]
        try:
            # Parse format: METHOD:PASS@IP:PORT
            auth_part, host_part = param.split("@")
            method, password = auth_part.split(":", 1)
            ip, port = host_part.rsplit(":", 1)
            ss_link = generate_shadowsocks_key_with_params(
                ss_method=method,
                ss_password=password,
                vps_ip=ip,
                ss_port=int(port)
            )
            print(f"\n✅ Generated Shadowsocks link:\n{ss_link}")
            return "gen-ss-full"
        except ValueError as e:
            print(f"❌ Error parsing parameter: {e}")
            print("Format: METHOD:PASSWORD@IP:PORT")
            print("Example: aes-256-gcm:my_password@192.168.1.100:443")
            return None
    
    return None


if __name__ == "__main__":
    # Handle CLI arguments first
    cli_result = handle_cli_args()
    
    if cli_result in ("help", "gen-ss", "gen-ss-full"):
        # Key generation mode - exit after generating
        sys.exit(0)
    
    # Run normal gateway monitor
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Gateway monitor stopped by user.")
    except Exception as e:
        logger.critical(f"Gateway monitor crashed: {e}")

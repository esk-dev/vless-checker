#!/usr/bin/env python3
"""VLESS Self-Healing Gateway Manager - Main Entry Point.

This module provides:
- Main entry point for gateway monitoring
- CLI argument handling for key generation
- Environment variable loading
- Signal handling for graceful shutdown
"""
import asyncio
import sys
import signal
import os
import json
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Import new modular components
from config.vless import VLESSInfo, parse_vless_key, key_to_vless_string, get_current_xray_key
from config.builder import XrayConfigBuilder, OutboundConfig, StreamSettings
from config.warp import WarpConfig
from config.ipv6 import IPv6Config
from config.rules import RoutingRulesBuilder
from config.ss import generate_shadowsocks_key
from config.loader import load_key_pool, get_best_key
from monitor.gateway import GatewayMonitor


# Configuration loaded from environment
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_JSON_PATH = os.getenv("KEYS_JSON_PATH", os.path.join(BASE_DIR, "docs/keys.json"))
XRAY_CONFIG_PATH = os.getenv("XRAY_CONFIG_PATH", "/usr/local/etc/xray/config.json")
CHECK_TIMEOUT = float(os.getenv("CHECK_TIMEOUT", "5.0"))
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL", "10.0"))
SS_INBOUND_PORT = int(os.getenv("SS_INBOUND_PORT", "8388"))
SS_PASSWORD = os.getenv("SS_PASSWORD", "your_secure_password_here")
SS_METHOD = os.getenv("SS_METHOD", "2022-blake3-aes-128-gcm")
GATEWAY_MODE = os.getenv("GATEWAY_MODE", "single")

# Key source mode: 'keys_json' or 'direct_internet'
# - 'keys_json': Get best key from KEYS_JSON_PATH (docs/keys.json)
# - 'direct_internet': Use direct freedom outbound (no proxy, direct internet)
KEY_SOURCE_MODE = os.getenv("KEY_SOURCE_MODE", "keys_json")

# Multi-client settings
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
        "KEY_SOURCE_MODE",
        "SS_INBOUND_PORT",
        "SS_PASSWORD",
        "SS_METHOD",
        "XRAY_OUTBOUND_NETWORK",
        "XRAY_SECURITY",
        "XRAY_INBOUND_SOCKS_PORT",
        "VPS_IP",
        "CLIENT_UUIDS",
        "CLIENT_KEYS",
        "ENABLE_IPV6_BLOCK",
        "WARP_SOCKS_PORT",
        "WARP_DOMAINS",
        "CHAIN_OUTBOUND_TAG"
    ]
    
    for var in env_vars:
        value = os.getenv(var, "NOT_SET")
        if "PASSWORD" in var or "KEY" in var:
            # Mask sensitive data
            if len(value) > 4:
                masked = value[:2] + "*" * (len(value) - 4) + value[-2:]
            elif len(value) > 0:
                masked = "*" * len(value)
            else:
                masked = "***"
            logger.info(f"{var}={masked}")
        else:
            logger.info(f"{var}={value}")
    
    logger.info("=" * 60)
    logger.info("=== ENVIRONMENT VARIABLES DUMP END ===")
    logger.info("=" * 60)



async def get_active_vless_key() -> Optional[str]:
    """Get active VLESS key using unified logic.
    
    Logic priority:
    1. If KEY_SOURCE_MODE=direct_internet: return None (use freedom outbound)
    2. Try to get current key from Xray config
    3. If not found or invalid, get best key from KEYS_JSON_PATH
    4. If still not found, return None
    
    Returns:
        VLESS key string or None for direct internet mode or no keys available
    """
    logger.info(f"KEY_SOURCE_MODE: {KEY_SOURCE_MODE}")
    
    # Direct internet mode - no VLESS key needed
    if KEY_SOURCE_MODE == "direct_internet":
        logger.info("Using direct internet mode (no VLESS proxy)")
        return None
    
    # Keys JSON mode - try Xray config first, then fallback to KEYS_JSON_PATH
    if KEY_SOURCE_MODE == "keys_json":
        # Try to get current key from Xray config
        current_key = await get_current_xray_key(XRAY_CONFIG_PATH)
        if current_key:
            logger.info(f"Found current key from Xray config: {current_key[:50]}...")
            return current_key
        
        logger.info("No current key found in Xray config, fetching best from KEYS_JSON_PATH...")
        
        # Fall back to best key from KEYS_JSON_PATH
        best_key = get_best_key(KEYS_JSON_PATH)
        if best_key:
            logger.info(f"Using best key from KEYS_JSON_PATH: {best_key[:50]}...")
            return best_key
        
        logger.error("No keys available from KEYS_JSON_PATH")
        return None
    
    logger.error(f"Invalid KEY_SOURCE_MODE: {KEY_SOURCE_MODE}")
    return None


class XrayManager:
    """Manages Xray configuration generation and application."""
    
    def __init__(self, config_path, xray_service_name="xray"):
        self.config_path = config_path
        self.xray_service_name = xray_service_name
        self.current_key = None
    
    def parse_vless_key(self, key: str) -> Optional[VLESSInfo]:
        """Parse VLESS key using the modular config module.
        
        Args:
            key: VLESS key string
            
        Returns:
            VLESSInfo object or None if parsing fails
        """
        return VLESSInfo.from_key(key)
    
    def _build_stream_settings(self, vless_info: VLESSInfo) -> Optional[StreamSettings]:
        """Build StreamSettings object for VLESS outbound.
        
        Args:
            vless_info: VLESSInfo object with all parameters
            
        Returns:
            StreamSettings object or None if security is 'none'
        """
        if vless_info.security not in ["tls", "reality"]:
            return None
        
        return StreamSettings(
            network=vless_info.network,
            security=vless_info.security,
            sni=vless_info.sni,
            alpn=vless_info.alpn,
            fp=vless_info.fingerprint,
            pbk=vless_info.reality_public_key,
            sid=vless_info.reality_short_id,
            spiderx=vless_info.reality_spider_x,
            path=vless_info.path,
            headers=vless_info.headers,
            host=vless_info.host,
            mode=vless_info.mode,
            extra=vless_info.extra,
            allow_insecure=vless_info.allow_insecure,
            packet_encoding=vless_info.packet_encoding,
            header_type=vless_info.header_type,
        )
    
    def _build_vless_outbound_config(self, vless_info: VLESSInfo, tag: str, client_uuid: Optional[str] = None, is_chain: bool = False) -> OutboundConfig:
        """Build an OutboundConfig object for VLESS.
        
        Args:
            vless_info: VLESSInfo object with all parameters
            tag: Tag for the outbound
            client_uuid: Optional client UUID for multi-client mode
            is_chain: If True, mark this as a chain outbound
            
        Returns:
            OutboundConfig object
        """
        flow = vless_info.flow or ""
        uuid = vless_info.uuid if client_uuid is None else client_uuid
        
        settings = {
            "vnext": [{
                "address": vless_info.address,
                "port": vless_info.port,
                "users": [{
                    "id": uuid,
                    "encryption": vless_info.encryption,
                    "flow": flow
                }]
            }]
        }
        
        stream_settings = self._build_stream_settings(vless_info)
        
        return OutboundConfig(
            tag=tag,
            protocol="vless",
            settings=settings,
            stream_settings=stream_settings,
        )
    
    def _build_vless_outbound(self, vless_info: VLESSInfo, tag: str, client_uuid: Optional[str] = None, is_chain: bool = False) -> Dict[str, Any]:
        """Build a single VLESS outbound configuration.
        
        Args:
            vless_info: VLESSInfo object with all parameters
            tag: Tag for the outbound
            client_uuid: Optional client UUID for multi-client mode
            is_chain: If True, mark this as a chain outbound
            
        Returns:
            Outbound configuration dict
        """
        outbound_config = self._build_vless_outbound_config(vless_info, tag, client_uuid, is_chain)
        return self._outbound_config_to_dict(outbound_config)
    
    def _outbound_config_to_dict(self, outbound_config: OutboundConfig) -> Dict[str, Any]:
        """Convert OutboundConfig to dictionary.
        
        Args:
            outbound_config: OutboundConfig object
            
        Returns:
            Dictionary representation
        """
        config = {
            "protocol": outbound_config.protocol,
            "tag": outbound_config.tag,
            "settings": outbound_config.settings,
        }
        if outbound_config.stream_settings:
            stream = {
                "network": outbound_config.stream_settings.network,
                "security": outbound_config.stream_settings.security,
            }
            
            # Handle per-network settings
            network = outbound_config.stream_settings.network
            if network == "xhttp":
                xhttp_settings = {
                    "path": outbound_config.stream_settings.path or "/",
                    "mode": outbound_config.stream_settings.mode or "auto",
                }
                if outbound_config.stream_settings.host:
                    xhttp_settings["host"] = outbound_config.stream_settings.host
                if outbound_config.stream_settings.extra:
                    xhttp_settings["extra"] = outbound_config.stream_settings.extra
                stream["xhttpSettings"] = xhttp_settings
            elif network == "ws":
                ws_settings = {
                    "path": outbound_config.stream_settings.path or "/",
                }
                if outbound_config.stream_settings.headers:
                    ws_settings["headers"] = outbound_config.stream_settings.headers
                elif outbound_config.stream_settings.host:
                    ws_settings["headers"] = {"Host": outbound_config.stream_settings.host}
                stream["wsSettings"] = ws_settings
            elif network == "grpc":
                grpc_settings = {
                    "serviceName": outbound_config.stream_settings.path or "",
                }
                if outbound_config.stream_settings.mode == "multiMode" or outbound_config.stream_settings.mode == "gun":
                    grpc_settings["multiMode"] = True
                if outbound_config.stream_settings.host:
                    grpc_settings["authority"] = outbound_config.stream_settings.host
                stream["grpcSettings"] = grpc_settings
            elif network == "kcp":
                kcp_settings = {
                    "mtu": 1350,
                }
                if outbound_config.stream_settings.header_type:
                    kcp_settings["header"] = {"type": outbound_config.stream_settings.header_type}
                if outbound_config.stream_settings.path:
                    kcp_settings["seed"] = outbound_config.stream_settings.path
                stream["kcpSettings"] = kcp_settings
            
            # Handle TLS/REALITY settings
            if outbound_config.stream_settings.security == "tls":
                tls_settings = {
                    "serverName": outbound_config.stream_settings.sni
                }
                if outbound_config.stream_settings.fp:
                    tls_settings["fingerprint"] = outbound_config.stream_settings.fp
                if outbound_config.stream_settings.alpn:
                    tls_settings["alpn"] = outbound_config.stream_settings.alpn
                if outbound_config.stream_settings.allow_insecure:
                    tls_settings["allowInsecure"] = True
                stream["tlsSettings"] = tls_settings
            elif outbound_config.stream_settings.security == "reality":
                reality_settings = {
                    "serverName": outbound_config.stream_settings.sni,
                    "publicKey": outbound_config.stream_settings.pbk or "",
                    "shortId": outbound_config.stream_settings.sid or "",
                    "spiderX": outbound_config.stream_settings.spiderx or ""
                }
                if outbound_config.stream_settings.fp:
                    reality_settings["fingerprint"] = outbound_config.stream_settings.fp
                stream["realitySettings"] = reality_settings
            
            config["streamSettings"] = stream
            
            # Add packet encoding
            if outbound_config.stream_settings.packet_encoding:
                stream["packetEncoding"] = outbound_config.stream_settings.packet_encoding
        
        return config
    
    def _build_chain_vless_outbound(self, chain_key: str) -> Optional[Dict[str, Any]]:
        """Build a chain VLESS outbound configuration.
        
        Args:
            chain_key: VLESS key string for chain outbound
            
        Returns:
            Outbound configuration dict or None if parsing fails
        """
        vless_info = self.parse_vless_key(chain_key)
        if not vless_info:
            logger.error("Failed to parse chain VLESS key")
            return None
        
        return self._build_vless_outbound(vless_info, "chain-vless-out", is_chain=True)
    
    def generate_config(self, vless_info=None, client_vless_infos=None):
        """Generate Xray configuration."""
        from config.builder import XrayConfigBuilder
        from config.warp import WarpConfig
        from config.ipv6 import IPv6Config
        from config.rules import RoutingRulesBuilder
        # Parse environment variables
        XRAY_OUTBOUND_NETWORK = os.getenv("XRAY_OUTBOUND_NETWORK", "tcp")
        XRAY_SECURITY = os.getenv("XRAY_SECURITY", "tls")
        XRAY_INBOUND_SOCKS_PORT = int(os.getenv("XRAY_INBOUND_SOCKS_PORT", "1080"))
        ENABLE_IPV6_BLOCK = os.getenv("ENABLE_IPV6_BLOCK", "true").lower() == "true"
        WARP_SOCKS_PORT = int(os.getenv("WARP_SOCKS_PORT", "40000"))
        WARP_DOMAINS = _parse_comma_separated_env("WARP_DOMAINS", ["openai.com", "chatgpt.com", "ai.com"])
        CHAIN_OUTBOUND_TAG = os.getenv("CHAIN_OUTBOUND_TAG", "chain-vless-out")
        SS_INBOUND_PORT = int(os.getenv("SS_INBOUND_PORT", "8388"))
        
        # Get VPS IP
        vps_ip = os.getenv("VPS_IP", "YOUR_VPS_IP_ADDRESS")
        
        builder = XrayConfigBuilder()
        
        # Add inbound for Shadowsocks
        builder.add_inbound(
            port=SS_INBOUND_PORT,
            protocol="shadowsocks",
            listen="0.0.0.0",
            tag="shadowsocks-in",
            settings={
                "method": SS_METHOD,
                "password": SS_PASSWORD,
                "timeout": 300,
                "udp": True
            },
            sniffing={
                "enabled": True,
                "destOverride": ["http", "tls"]
            }
        )
        
        # Add inbound for SOCKS5
        builder.add_inbound(
            port=XRAY_INBOUND_SOCKS_PORT,
            protocol="socks",
            listen="0.0.0.0",
            tag="socks-in",
            settings={
                "auth": "noauth",
                "udp": True,
                "ip": "127.0.0.1"
            }
        )
        
        outbounds = [
            {"protocol": "freedom", "settings": {}, "tag": "direct"},
            {"protocol": "blackhole", "settings": {}, "tag": "blocked"}
        ]
        
        # Add WARP outbound if WARP domains are configured
        if WARP_DOMAINS and len(WARP_DOMAINS) > 0:
            outbounds.append({
                "protocol": "socks",
                "tag": "warp-proxy",
                "settings": {
                    "servers": [{
                        "address": "127.0.0.1",
                        "port": WARP_SOCKS_PORT
                    }]
                }
            })
            logger.info(f"Added WARP proxy outbound for domains: {WARP_DOMAINS}")
        
        # Chain outbound for explicit routing (if configured)
        if os.getenv("CHAIN_VLESS_KEY"):
            chain_outbound = self._build_chain_vless_outbound(os.getenv("CHAIN_VLESS_KEY"))
            if chain_outbound:
                outbounds.append(chain_outbound)
                logger.info(f"Added chain VLESS outbound: {CHAIN_OUTBOUND_TAG}")
        
        # Single-mode: Add VLESS outbound
        if vless_info:
            outbound = self._build_vless_outbound(vless_info, "proxy-out")
            outbounds.append(outbound)
        
        # Multi-mode: Add multiple VLESS outbounds
        if client_vless_infos:
            for tag, info in client_vless_infos.items():
                outbound = self._build_vless_outbound(info, tag)
                outbounds.append(outbound)
        
        # Build routing rules
        warp_config = WarpConfig(enabled=len(WARP_DOMAINS) > 0, domains=WARP_DOMAINS, port=WARP_SOCKS_PORT)
        ipv6_config = IPv6Config(enabled=ENABLE_IPV6_BLOCK)
        rules_builder = RoutingRulesBuilder(enable_ipv6_block=ipv6_config.enabled, warp_config=warp_config)
        
        direct_rules = rules_builder.build_all_rules()
        routing_rules = []
        
        # Chain routing rule (if chain is configured)
        if os.getenv("CHAIN_VLESS_KEY"):
            routing_rules.append({
                "type": "field",
                "outboundTag": CHAIN_OUTBOUND_TAG,
                "network": "tcp,udp"
            })
        
        # Proxy outbound rule (only when using VLESS)
        if vless_info or client_vless_infos:
            routing_rules.append({
                "type": "field",
                "network": "tcp,udp",
                "outboundTag": "proxy-out"
            })
        
        config = builder.build()
        config["inbounds"] = builder.inbounds
        config["outbounds"] = outbounds
        config["routing"]["rules"] = direct_rules + routing_rules
        
        return config
    
    def generate_direct_internet_config(self):
        """Generate Xray configuration for direct internet mode (no proxy).
        
        Returns:
            Xray configuration dict with freedom outbound
        """
        return self.generate_config()  # Call generate_config with no VLESS info
    
    async def apply_config(self, key=None):
        """Apply Xray configuration.
        
        Args:
            key: VLESS key string. If None and KEY_SOURCE_MODE=direct_internet,
                 uses freedom outbound (direct internet).
        """
        import json
        
        # Direct internet mode - no VLESS key needed
        if KEY_SOURCE_MODE == "direct_internet":
            logger.info("=== Direct Internet Mode ===")
            logger.info("Using freedom outbound (direct internet, no proxy)")
            config = self.generate_config()
            logger.debug(f"Generated direct internet config: {json.dumps(config, indent=2)}")
        elif GATEWAY_MODE == "multi":
            if not CLIENT_KEYS:
                logger.error("CLIENT_KEYS is empty for multi-client mode.")
                return False
            
            client_vless_infos = {}
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
            logger.debug(f"Generated multi-client config: {json.dumps(config, indent=2)}")
        else:
            # Single-key mode - requires key
            if not key:
                logger.error("No key provided for single-key mode.")
                return False
            
            vless_info = self.parse_vless_key(key)
            if not vless_info:
                logger.error("Could not parse key for configuration.")
                return False
            
            config = self.generate_config(vless_info=vless_info)
        
        logger.info("=== XRAY CONFIGURATION DUMP START ===")
        logger.info(f"Config path: {self.config_path}")
        logger.info(f"Generated config JSON:\n{json.dumps(config, indent=2)}")
        logger.info("=== XRAY CONFIGURATION DUMP END ===")
        
        config_dir = os.path.dirname(self.config_path)
        logger.info(f"Checking config directory: {config_dir}")
        
        if not os.path.exists(config_dir):
            try:
                os.makedirs(config_dir)
                logger.info(f"Created config directory: {config_dir}")
            except Exception as e:
                logger.error(f"Failed to create config directory: {e}")
                return False
        
        # Write config to file
        try:
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=2)
            logger.info(f"Config written to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to write config: {e}")
            return False
        
        # Restart Xray service
        try:
            await asyncio.create_subprocess_shell(f"sudo systemctl restart {self.xray_service_name}")
            logger.info(f"Restarted {self.xray_service_name} service")
        except Exception as e:
            logger.error(f"Failed to restart Xray: {e}")
            return False
        
        self.current_key = key
        return True




async def main(use_keys: bool = True):
    """Main entry point.
    
    Args:
        use_keys: If True, use keys from keys.json; otherwise use current Xray config
    """
    logger.info("=" * 60)
    logger.info("=== GATEWAY MANAGER STARTING ===")
    logger.info("=" * 60)
    
    # Log all environment variables
    log_environment_variables()
    
    # Load client settings for multi-client mode
    _load_client_settings()
    
    xray_manager = XrayManager(XRAY_CONFIG_PATH)
    
    # Use new unified key retrieval function
    active_key = await get_active_vless_key()
    
    if use_keys:
        monitor = GatewayMonitor(KEYS_JSON_PATH, xray_manager)
        
        # If no active key in keys_json mode, try to get best from KEYS_JSON_PATH
        if not active_key and KEY_SOURCE_MODE == "keys_json":
            logger.info("Fetching best key from KEYS_JSON_PATH for initial configuration...")
            best_key = get_best_key(KEYS_JSON_PATH)
            if best_key:
                active_key = best_key
        
        if active_key:
            logger.info(f"Initial key: {active_key[:50]}...")
            # Apply initial configuration with the active key
            if not await xray_manager.apply_config(active_key):
                logger.error("Failed to apply initial configuration.")
                return
        
        try:
            await monitor.run()
        except KeyboardInterrupt:
            logger.info("Gateway monitor stopped by user.")
    else:
        # Use currently active Xray configuration
        logger.info("=== Using currently active Xray configuration ===")
        
        if not active_key:
            logger.error("Could not determine active key. Exiting.")
            return
        
        logger.info(f"Active key detected: {active_key[:40]}...")
        
        # Apply current configuration
        if not await xray_manager.apply_config(active_key):
            logger.error("Failed to apply current configuration.")
            return
        
        logger.info("Current Xray configuration applied successfully.")
        logger.info("Gateway running in single-key mode with current config.")
        logger.info("Press Ctrl+C to stop.")
        
        # Keep running - use GatewayMonitor's check loop but with single key
        monitor = GatewayMonitor(KEYS_JSON_PATH, xray_manager)
        monitor.key_pool = [active_key]
        monitor.current_index = 0
        
        try:
            # Simple health check loop with current key
            while True:
                is_alive = await monitor.check_connection(active_key)
                if is_alive:
                    logger.info(f"🟢 Connection healthy to {active_key[:30]}...")
                else:
                    logger.warning(f"⚠️ Connection lost to {active_key[:30]}...")
                
                await asyncio.sleep(10.0)  # CHECK_INTERVAL
        except KeyboardInterrupt:
            logger.info("Gateway monitor stopped by user.")


def print_usage():
    """Print usage information."""
    print("""
Usage: python3 gateway_manager.py [OPTIONS]

Options:
  --gen-ss                Generate a Shadowsocks key for Outline
  --gen-ss-full METHOD:PASS@IP:PORT
                          Generate a Shadowsocks key with full parameters
  --use-keys              Use VLESS keys from keys.json file
  -h, --help              Show this help message

Examples:
  python3 gateway_manager.py --gen-ss
  python3 gateway_manager.py --gen-ss-full "aes-256-gcm:my_password@192.168.1.100:443"
  python3 gateway_manager.py --use-keys
""")


def handle_cli_args():
    """Handle command-line arguments."""
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
        print(f"\nGenerated Shadowsocks link:\n{ss_link}")
        return "gen-ss"
    
    if arg == "--gen-ss-full":
        if len(sys.argv) < 3:
            print("Error: --gen-ss-full requires a parameter in format METHOD:PASS@IP:PORT")
            print("Example: aes-256-gcm:my_password@192.168.1.100:443")
            return None
        param = sys.argv[2]
        try:
            auth_part, host_part = param.split("@")
            method, password = auth_part.split(":", 1)
            ip, port = host_part.rsplit(":", 1)
            ss_link = generate_shadowsocks_key(
                ss_method=method,
                ss_password=password,
                vps_ip=ip,
                ss_port=int(port)
            )
            print(f"\nGenerated Shadowsocks link:\n{ss_link}")
            return "gen-ss-full"
        except ValueError as e:
            print(f"Error parsing parameter: {e}")
            print("Format: METHOD:PASSWORD@IP:PORT")
            print("Example: aes-256-gcm:my_password@192.168.1.100:443")
            return None
    
    return None


if __name__ == "__main__":
    # Graceful shutdown handler
    shutdown_event = asyncio.Event()
    
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        shutdown_event.set()
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Handle CLI arguments first
    cli_result = handle_cli_args()
    
    if cli_result in ("help", "gen-ss", "gen-ss-full"):
        sys.exit(0)
    
    # Run normal gateway monitor
    use_keys = "--use-keys" in sys.argv
    
    if use_keys:
        logger.info("Using keys from keys.json file")
    else:
        logger.info("Using currently running Xray configuration as last key")
    
    try:
        asyncio.run(main(use_keys=use_keys))
    except KeyboardInterrupt:
        logger.info("Gateway monitor stopped by user.")
    except Exception as e:
        logger.critical(f"Gateway monitor crashed: {e}")
    finally:
        logger.info("Gateway monitor shutdown complete.")

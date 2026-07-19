"""VLESS key parsing and configuration building.

This module handles:
- Parsing VLESS key strings into structured data
- Converting VLESS info to Xray outbound configurations
- Handling TLS, REALITY, and other security types
"""
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class VLESSInfo:
    """Parsed VLESS key information.
    
    Args:
        uuid: UUID from the VLESS key
        address: Server address (hostname or IP)
        port: Server port
        encryption: Encryption method (default: "none")
        security: Security type (tls, reality, none - default: "tls")
        sni: Server Name Indication for TLS
        flow: Flow setting (e.g., "xtls-rprx-vision")
        reality_public_key: Public key for REALITY protocol
        reality_short_id: Short ID for REALITY protocol
        reality_spider_x: SpiderX for REALITY protocol
    """
    uuid: str
    address: str
    port: int
    encryption: str = "none"
    security: str = "tls"
    sni: Optional[str] = None
    flow: Optional[str] = None
    reality_public_key: Optional[str] = None
    reality_short_id: Optional[str] = None
    reality_spider_x: Optional[str] = None
    
    @classmethod
    def from_key(cls, key: str) -> Optional['VLESSInfo']:
        """Parse a VLESS key string into VLESSInfo.
        
        Args:
            key: VLESS key in format: vless://UUID@HOST:PORT?PARAMS#TAG
            
        Returns:
            VLESSInfo object or None if parsing fails
        """
        if not key or not key.startswith("vless://"):
            return None
        
        try:
            content = key[len("vless://"):]
            if "@" not in content:
                return None
            
            uuid, remainder = content.split("@", 1)
            parts = re.split(r'[?#]', remainder)
            host_port = parts[0]
            
            # Parse host and port
            address, port = cls._parse_host_port(host_port)
            if address is None or port is None:
                return None
            
            # Parse query parameters
            params = cls._parse_params(parts)
            
            # Parse fragment
            fragment = parts[2] if len(parts) > 2 else None
            
            # Build REALITY settings
            reality_settings = None
            if params.get("security") == "reality":
                reality_settings = {
                    "publicKey": params.get("pbk", ""),
                    "shortId": params.get("sid", ""),
                    "serverName": params.get("sni") or fragment,
                    "spiderX": params.get("spiderX", "")
                }
            
            return cls(
                uuid=uuid,
                address=address,
                port=port,
                encryption=params.get("encryption", "none"),
                security=params.get("security", "tls"),
                sni=params.get("sni") or fragment,
                flow=params.get("flow"),
                reality_public_key=reality_settings.get("publicKey") if reality_settings else None,
                reality_short_id=reality_settings.get("shortId") if reality_settings else None,
                reality_spider_x=reality_settings.get("spiderX") if reality_settings else None,
            )
        except (ValueError, AttributeError):
            return None
    
    @staticmethod
    def _parse_host_port(host_port: str) -> tuple:
        """Parse host:port string, handling IPv6 addresses.
        
        Args:
            host_port: Host and port string
            
        Returns:
            Tuple of (host, port) or (None, None) if parsing fails
        """
        # Handle IPv6 format: [2001:db8::1]:443
        if host_port.startswith("["):
            match = re.match(r'\[([^\]]+)\]:(\d+)$', host_port)
            if match:
                return match.group(1), int(match.group(2))
        
        # Handle IPv4 or hostname format: host:port
        if ":" in host_port:
            # Need to handle IPv6 without brackets (e.g., fe80::1:443)
            # This is a simplified check - real IPv6 addresses have :: or multiple colons
            parts = host_port.rsplit(":", 1)
            if len(parts) == 2:
                # Check if this is likely IPv6 (has multiple colons or ::)
                if parts[0].count(":") >= 1:
                    # Could be IPv6 - try to parse as bracketed format
                    return None, None
                host, port_str = parts
                try:
                    return host, int(port_str)
                except ValueError:
                    return None, None
        
        # Plain host or IPv4 without port
        return host_port, 443
    
    @staticmethod
    def _parse_params(parts: list) -> Dict[str, str]:
        """Parse query parameters from parts list.
        
        Args:
            parts: Split parts from the VLESS key
            
        Returns:
            Dictionary of parameters
        """
        params = {}
        if len(parts) > 1:
            query_str = parts[1]
            for pair in query_str.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    params[k] = v
        return params
    
    def to_outbound_config(
        self, 
        tag: str, 
        client_uuid: Optional[str] = None, 
        is_chain: bool = False,
        network: str = "tcp"
    ) -> Dict[str, Any]:
        """Convert VLESSInfo to Xray outbound configuration.
        
        Args:
            tag: Tag for the outbound
            client_uuid: Optional client UUID for multi-client mode
            is_chain: If True, mark this as a chain outbound
            network: Network type (tcp, xhttp, ws, grpc)
            
        Returns:
            Outbound configuration dict
        """
        outbound = {
            "protocol": "vless",
            "tag": tag,
            "settings": {
                "vnext": [{
                    "address": self.address,
                    "port": self.port,
                    "users": [{
                        "id": self.uuid if client_uuid is None else client_uuid,
                        "encryption": self.encryption,
                        "flow": self.flow or ""
                    }]
                }]
            }
        }
        
        # Add stream settings
        if self.security in ["tls", "reality"]:
            stream_settings = {
                "network": network,
                "security": self.security
            }
            
            if self.security == "tls":
                stream_settings["tlsSettings"] = {
                    "serverName": self.sni
                }
            elif self.security == "reality":
                stream_settings["realitySettings"] = {
                    "serverName": self.sni,
                    "publicKey": self.reality_public_key or "",
                    "shortId": self.reality_short_id or "",
                    "spiderX": self.reality_spider_x or ""
                }
            
            outbound["streamSettings"] = stream_settings
        
        return outbound


def parse_vless_key(key: str) -> Optional[Dict[str, Any]]:
    """Parse a VLESS key string and return Xray-compatible config.
    
    This is the legacy function that returns a dictionary (like the original).
    
    Args:
        key: VLESS key string
        
    Returns:
        Dictionary with parsed VLESS info or None if parsing fails
    """
    info = VLESSInfo.from_key(key)
    if info is None:
        return None
    
    result = {
        "uuid": info.uuid,
        "address": info.address,
        "port": info.port,
        "encryption": info.encryption,
        "security": info.security,
        "sni": info.sni,
        "flow": info.flow,
        "type": "vless"
    }
    
    if info.security == "reality":
        result["realitySettings"] = {
            "publicKey": info.reality_public_key or "",
            "shortId": info.reality_short_id or "",
            "serverName": info.sni,
            "spiderX": info.reality_spider_x or ""
        }
    
    return result

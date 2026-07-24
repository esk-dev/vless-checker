"""VLESS key parsing and configuration building.

This module handles:
- Parsing VLESS key strings into structured data
- Converting VLESS info to Xray outbound configurations
- Handling TLS, REALITY, and other security types
"""
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from urllib.parse import unquote_plus


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
        network: Network type (tcp, xhttp, ws, grpc, kcp)
        host: Host header for WebSocket or xhttp
        path: Path for WebSocket or xhttp
        headers: Custom headers as dict
        alpn: Application-Layer Protocol Negotiation list
        fingerprint: Fingerprint for TLS
        allow_insecure: Allow insecure TLS connections
        mode: Mode for xhttp or grpc
        extra: Extra settings as JSON dict
        packet_encoding: Packet encoding for xudp
        header_type: Header type for TCP
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
    network: str = "tcp"
    host: Optional[str] = None
    path: Optional[str] = None
    headers: Optional[Dict[str, List[str]]] = None
    alpn: Optional[List[str]] = None
    fingerprint: Optional[str] = None
    allow_insecure: bool = False
    mode: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None
    packet_encoding: Optional[str] = None
    header_type: Optional[str] = None
    
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
                network=params.get("type", "tcp"),
                host=params.get("host"),
                path=params.get("path"),
                alpn=params.get("alpn"),
                fingerprint=params.get("fingerprint"),
                allow_insecure=params.get("allow_insecure", False),
                mode=params.get("mode"),
                extra=params.get("extra"),
                packet_encoding=params.get("packet_encoding"),
                header_type=params.get("header_type"),
                reality_public_key=params.get("reality_public_key"),
                reality_short_id=params.get("reality_short_id"),
                reality_spider_x=params.get("reality_spider_x"),
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
    def _parse_params(parts: list) -> Dict[str, Any]:
        """Parse query parameters from parts list.
        
        Args:
            parts: Split parts from the VLESS key
            
        Returns:
            Dictionary of parameters with type conversions
        """
        params = {}
        if len(parts) > 1:
            query_str = parts[1]
            for pair in query_str.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    # URL decode the value
                    v = unquote_plus(v)
                    
                    # Parse special parameter types
                    if k == "allowinsecure" or k == "insecure":
                        params["allow_insecure"] = v.lower() in ("1", "true", "yes", "on")
                    elif k == "alpn":
                        # Split comma-separated ALPN list
                        params["alpn"] = [algo.strip() for algo in v.split(",")]
                    elif k == "extra":
                        # Parse JSON extra object
                        try:
                            params["extra"] = json.loads(v)
                        except json.JSONDecodeError:
                            params["extra"] = None
                    elif k == "packetEncoding":
                        params["packet_encoding"] = v
                    elif k == "headerType":
                        params["header_type"] = v
                    elif k == "fp":
                        params["fingerprint"] = v
                    elif k == "pbk":
                        params["reality_public_key"] = v
                    elif k == "sid":
                        params["reality_short_id"] = v
                    elif k == "spiderX":
                        params["reality_spider_x"] = v
                    else:
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
            network: Network type (tcp, xhttp, ws, grpc, kcp)
            
        Returns:
            Outbound configuration dict with complete stream settings
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
        
        # Determine network type - use self.network first, then fallback
        effective_network = self.network if self.network != "tcp" else network
        
        # Add stream settings for non-none security
        if self.security in ["tls", "reality"]:
            stream_settings = {
                "network": effective_network,
                "security": self.security
            }
            
            # Handle per-network settings
            if effective_network == "xhttp":
                xhttp_settings = {
                    "path": self.path or "/",
                    "mode": self.mode or "auto",
                }
                if self.host:
                    xhttp_settings["host"] = self.host
                if self.extra:
                    xhttp_settings["extra"] = self.extra
                stream_settings["xhttpSettings"] = xhttp_settings
            elif effective_network == "ws":
                ws_settings = {
                    "path": self.path or "/",
                }
                if self.headers:
                    ws_settings["headers"] = self.headers
                elif self.host:
                    ws_settings["headers"] = {"Host": self.host}
                stream_settings["wsSettings"] = ws_settings
            elif effective_network == "grpc":
                grpc_settings = {
                    "serviceName": self.path or "",
                }
                if self.mode == "multiMode" or self.mode == "gun":
                    grpc_settings["multiMode"] = True
                if self.host:
                    grpc_settings["authority"] = self.host
                stream_settings["grpcSettings"] = grpc_settings
            elif effective_network == "kcp":
                kcp_settings = {
                    "mtu": 1350,
                }
                if self.header_type:
                    kcp_settings["header"] = {"type": self.header_type}
                if self.path:
                    kcp_settings["seed"] = self.path
                stream_settings["kcpSettings"] = kcp_settings
            
            # Handle TLS/REALITY settings
            if self.security == "tls":
                tls_settings = {
                    "serverName": self.sni
                }
                if self.fingerprint:
                    tls_settings["fingerprint"] = self.fingerprint
                if self.alpn:
                    tls_settings["alpn"] = self.alpn
                if self.allow_insecure:
                    tls_settings["allowInsecure"] = True
                stream_settings["tlsSettings"] = tls_settings
            elif self.security == "reality":
                reality_settings = {
                    "serverName": self.sni,
                    "publicKey": self.reality_public_key or "",
                    "shortId": self.reality_short_id or "",
                    "spiderX": self.reality_spider_x or ""
                }
                if self.fingerprint:
                    reality_settings["fingerprint"] = self.fingerprint
                stream_settings["realitySettings"] = reality_settings
            
            outbound["streamSettings"] = stream_settings
            
            # Add packet encoding for xudp
            if self.packet_encoding:
                stream_settings["packetEncoding"] = self.packet_encoding
        
        return outbound


def parse_vless_key(key: str) -> Optional[Dict[str, Any]]:
    """Parse a VLESS key string and return Xray-compatible config.
    
    This is the legacy function that returns a dictionary (like the original).
    For new code, use VLESSInfo.from_key() directly.
    
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
        "type": "vless",
        "network": info.network,
        "host": info.host,
        "path": info.path,
        "alpn": info.alpn,
        "fingerprint": info.fingerprint,
        "allow_insecure": info.allow_insecure,
        "mode": info.mode,
        "extra": info.extra,
        "packet_encoding": info.packet_encoding,
        "header_type": info.header_type,
        "reality_public_key": info.reality_public_key,
        "reality_short_id": info.reality_short_id,
        "reality_spider_x": info.reality_spider_x,
    }
    
    if info.security == "reality":
        result["realitySettings"] = {
            "publicKey": info.reality_public_key or "",
            "shortId": info.reality_short_id or "",
            "serverName": info.sni,
            "spiderX": info.reality_spider_x or ""
        }
    
    return result

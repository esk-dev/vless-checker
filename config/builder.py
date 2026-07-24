"""Xray configuration builder with fluent interface.

This module provides:
- XrayConfigBuilder class for declarative config building
- OutboundConfig dataclass for outbound definitions
- StreamSettings dataclass for stream configuration
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from urllib.parse import unquote_plus


@dataclass
class StreamSettings:
    """Stream settings for outbound connections.
    
    Args:
        network: Network type (tcp, xhttp, ws, grpc)
        security: Security type (tls, reality, none)
        sni: Server Name Indication for TLS
        alpn: Application-Layer Protocol Negotiation
        fp: Fingerprint for TLS
        pbk: Public key for REALITY
        sid: Short ID for REALITY
        spiderx: SpiderX for REALITY
        path: Path for WebSocket or xhttp
        headers: Custom headers for WebSocket or xhttp
        allow_insecure: Allow insecure TLS connections
        host: Host header for WebSocket or xhttp
        mode: Mode for xhttp or grpc
        extra: Extra settings as JSON dict
        packet_encoding: Packet encoding for xudp
        header_type: Header type for TCP
    """
    network: str = "tcp"
    security: str = "tls"
    sni: Optional[str] = None
    alpn: Optional[List[str]] = None
    fp: Optional[str] = None
    pbk: Optional[str] = None
    sid: Optional[str] = None
    spiderx: Optional[str] = None
    path: Optional[str] = None
    headers: Optional[Dict[str, List[str]]] = None
    allow_insecure: bool = False
    host: Optional[str] = None
    mode: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None
    packet_encoding: Optional[str] = None
    header_type: Optional[str] = None


@dataclass
class OutboundConfig:
    """Represents an outbound configuration.
    
    Args:
        tag: Tag for the outbound
        protocol: Protocol type (vless, shadowsocks, etc.)
        settings: Protocol-specific settings
        stream_settings: Optional stream settings
        proxy_settings: Optional proxy settings
    """
    tag: str
    protocol: str
    settings: Dict[str, Any]
    stream_settings: Optional[StreamSettings] = None
    proxy_settings: Optional[Dict[str, Any]] = None


class XrayConfigBuilder:
    """Builds Xray configuration in a readable, step-by-step way.
    
    Example usage:
        builder = XrayConfigBuilder()
        builder.add_inbound(port=8388, protocol="shadowsocks", settings={...})
        builder.add_outbound(vless_outbound)
        builder.add_routing_rule(rule)
        config = builder.build()
    """
    
    def __init__(self):
        """Initialize the config builder."""
        self.inbounds: List[Dict] = []
        self.outbounds: List[Dict] = []
        self.routing_rules: List[Dict] = []
        self.log_level = "warning"
    
    def set_log_level(self, level: str) -> 'XrayConfigBuilder':
        """Set the log level for Xray.
        
        Args:
            level: Log level (debug, info, warning, error, none)
            
        Returns:
            Self for method chaining
        """
        self.log_level = level
        return self
    
    def add_inbound(
        self,
        port: int,
        protocol: str,
        settings: Dict,
        listen: str = "127.0.0.1",
        tag: Optional[str] = None,
       sniffing: Optional[Dict] = None
    ) -> 'XrayConfigBuilder':
        """Add an inbound configuration.
        
        Args:
            port: Inbound port
            protocol: Protocol type (shadowsocks, socks, etc.)
            settings: Protocol-specific settings
            listen: Listen address (default: 127.0.0.1)
            tag: Optional tag for the inbound
            sniffing: Optional sniffing settings
            
        Returns:
            Self for method chaining
        """
        inbound = {
            "port": port,
            "protocol": protocol,
            "settings": settings,
            "listen": listen,
        }
        if tag:
            inbound["tag"] = tag
        if sniffing:
            inbound["sniffing"] = sniffing
        self.inbounds.append(inbound)
        return self
    
    def add_vless_outbound(
        self,
        tag: str,
        address: str,
        port: int,
        uuid: str,
        encryption: str = "none",
        flow: str = "",
        network: str = "tcp",
        security: str = "tls",
        sni: Optional[str] = None,
        client_uuid: Optional[str] = None,
    ) -> 'XrayConfigBuilder':
        """Add a VLESS outbound configuration.
        
        Args:
            tag: Tag for the outbound
            address: Server address
            port: Server port
            uuid: UUID for the VLESS connection
            encryption: Encryption method (default: "none")
            flow: Flow setting (default: "")
            network: Network type (default: "tcp")
            security: Security type (default: "tls")
            sni: Server Name Indication for TLS
            client_uuid: Optional client UUID for multi-client mode
            
        Returns:
            Self for method chaining
        """
        outbound = {
            "protocol": "vless",
            "tag": tag,
            "settings": {
                "vnext": [{
                    "address": address,
                    "port": port,
                    "users": [{
                        "id": uuid if client_uuid is None else client_uuid,
                        "encryption": encryption,
                        "flow": flow
                    }]
                }]
            }
        }
        
        # Add stream settings if needed
        if security in ["tls", "reality"]:
            stream_settings = {
                "network": network,
                "security": security
            }
            
            if security == "tls":
                stream_settings["tlsSettings"] = {
                    "serverName": sni
                }
            elif security == "reality":
                stream_settings["realitySettings"] = {
                    "serverName": sni,
                    "publicKey": "",
                    "shortId": "",
                    "spiderX": ""
                }
            
            outbound["streamSettings"] = stream_settings
        
        self.outbounds.append(outbound)
        return self
    
    def add_outbound(self, outbound: OutboundConfig) -> 'XrayConfigBuilder':
        """Add an outbound configuration.
        
        Args:
            outbound: OutboundConfig object
            
        Returns:
            Self for method chaining
        """
        config = {
            "protocol": outbound.protocol,
            "tag": outbound.tag,
            "settings": outbound.settings,
        }
        if outbound.stream_settings:
            stream = {
                "network": outbound.stream_settings.network,
                "security": outbound.stream_settings.security,
            }
            if outbound.stream_settings.network == "xhttp":
                xhttp_settings = {
                    "path": outbound.stream_settings.path or "/",
                    "mode": outbound.stream_settings.mode or "auto",
                }
                if outbound.stream_settings.host:
                    xhttp_settings["host"] = outbound.stream_settings.host
                if outbound.stream_settings.extra:
                    xhttp_settings["extra"] = outbound.stream_settings.extra
                stream["xhttpSettings"] = xhttp_settings
            elif outbound.stream_settings.network == "ws":
                ws_settings = {
                    "path": outbound.stream_settings.path or "/",
                }
                if outbound.stream_settings.headers:
                    ws_settings["headers"] = outbound.stream_settings.headers
                if outbound.stream_settings.host:
                    ws_settings["headers"] = {"Host": outbound.stream_settings.host}
                stream["wsSettings"] = ws_settings
            elif outbound.stream_settings.network == "grpc":
                grpc_settings = {
                    "serviceName": outbound.stream_settings.path or "",
                }
                if outbound.stream_settings.mode == "multiMode" or outbound.stream_settings.mode == "gun":
                    grpc_settings["multiMode"] = True
                if outbound.stream_settings.host:
                    grpc_settings["authority"] = outbound.stream_settings.host
                stream["grpcSettings"] = grpc_settings
            elif outbound.stream_settings.network == "kcp":
                kcp_settings = {
                    "mtu": 1350,
                }
                if outbound.stream_settings.header_type:
                    kcp_settings["header"] = {"type": outbound.stream_settings.header_type}
                if outbound.stream_settings.path:
                    kcp_settings["seed"] = outbound.stream_settings.path
                stream["kcpSettings"] = kcp_settings
            if outbound.stream_settings.security == "tls":
                tls_settings = {
                    "serverName": outbound.stream_settings.sni
                }
                if outbound.stream_settings.fp:
                    tls_settings["fingerprint"] = outbound.stream_settings.fp
                if outbound.stream_settings.alpn:
                    tls_settings["alpn"] = outbound.stream_settings.alpn
                if outbound.stream_settings.allow_insecure:
                    tls_settings["allowInsecure"] = True
                stream["tlsSettings"] = tls_settings
            elif outbound.stream_settings.security == "reality":
                reality_settings = {
                    "serverName": outbound.stream_settings.sni,
                    "publicKey": outbound.stream_settings.pbk or "",
                    "shortId": outbound.stream_settings.sid or "",
                    "spiderX": outbound.stream_settings.spiderx or ""
                }
                if outbound.stream_settings.fp:
                    reality_settings["fingerprint"] = outbound.stream_settings.fp
                stream["realitySettings"] = reality_settings
            config["streamSettings"] = stream
            if outbound.stream_settings.packet_encoding:
                stream["packetEncoding"] = outbound.stream_settings.packet_encoding
        if outbound.proxy_settings:
            config["proxySettings"] = outbound.proxy_settings
        self.outbounds.append(config)
        return self
    
    def add_shadowsocks_outbound(
        self,
        tag: str,
        address: str,
        port: int,
        method: str,
        password: str,
        udp: bool = True
    ) -> 'XrayConfigBuilder':
        """Add a Shadowsocks outbound configuration.
        
        Args:
            tag: Tag for the outbound
            address: Server address
            port: Server port
            method: Encryption method
            password: Password for the connection
            udp: Enable UDP relay (default: True)
            
        Returns:
            Self for method chaining
        """
        self.outbounds.append({
            "protocol": "shadowsocks",
            "tag": tag,
            "settings": {
                "servers": [{
                    "address": address,
                    "port": port,
                    "method": method,
                    "password": password,
                    "udp": udp
                }]
            }
        })
        return self
    
    def add_direct_outbound(self, tag: str = "direct") -> 'XrayConfigBuilder':
        """Add a direct (freedom) outbound configuration.
        
        Args:
            tag: Tag for the outbound (default: "direct")
            
        Returns:
            Self for method chaining
        """
        self.outbounds.append({
            "protocol": "freedom",
            "tag": tag,
            "settings": {}
        })
        return self
    
    def add_blocked_outbound(self, tag: str = "blocked") -> 'XrayConfigBuilder':
        """Add a blocked (blackhole) outbound configuration.
        
        Args:
            tag: Tag for the outbound (default: "blocked")
            
        Returns:
            Self for method chaining
        """
        self.outbounds.append({
            "protocol": "blackhole",
            "tag": tag,
            "settings": {}
        })
        return self
    
    def add_socks_outbound(
        self,
        tag: str,
        address: str,
        port: int
    ) -> 'XrayConfigBuilder':
        """Add a Socks outbound configuration.
        
        Args:
            tag: Tag for the outbound
            address: Socks server address
            port: Socks server port
            
        Returns:
            Self for method chaining
        """
        self.outbounds.append({
            "protocol": "socks",
            "tag": tag,
            "settings": {
                "servers": [{
                    "address": address,
                    "port": port
                }]
            }
        })
        return self
    
    def add_routing_rule(self, rule: Dict) -> 'XrayConfigBuilder':
        """Add a routing rule.
        
        Args:
            rule: Routing rule dictionary
            
        Returns:
            Self for method chaining
        """
        self.routing_rules.append(rule)
        return self
    
    def add_routing_rule_field(
        self,
        field_type: str = "field",
        domain: Optional[List[str]] = None,
        ip: Optional[List[str]] = None,
        outbound_tag: str = "direct"
    ) -> 'XrayConfigBuilder':
        """Add a routing rule using field matcher.
        
        Args:
            field_type: Rule type (default: "field")
            domain: Domain list for matching
            ip: IP list for matching
            outbound_tag: Target outbound tag
            
        Returns:
            Self for method chaining
        """
        rule = {
            "type": field_type,
            "outboundTag": outbound_tag
        }
        if domain:
            rule["domain"] = domain
        if ip:
            rule["ip"] = ip
        self.routing_rules.append(rule)
        return self
    
    def build(self) -> Dict[str, Any]:
        """Build and return the final Xray configuration.
        
        Returns:
            Complete Xray configuration dictionary
        """
        return {
            "log": {"loglevel": self.log_level},
            "inbounds": self.inbounds,
            "outbounds": self.outbounds,
            "routing": {
                "domainStrategy": "IPIfNonMatch",
                "implicitIPSetMatch": True,
                "rules": self.routing_rules,
            }
        }

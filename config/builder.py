"""Xray configuration builder with fluent interface.

This module provides:
- XrayConfigBuilder class for declarative config building
- OutboundConfig dataclass for outbound definitions
- StreamSettings dataclass for stream configuration
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


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
            if outbound.stream_settings.security == "tls":
                stream["tlsSettings"] = {
                    "serverName": outbound.stream_settings.sni
                }
            elif outbound.stream_settings.security == "reality":
                stream["realitySettings"] = {
                    "serverName": outbound.stream_settings.sni,
                    "publicKey": outbound.stream_settings.pbk or "",
                    "shortId": outbound.stream_settings.sid or "",
                    "spiderX": outbound.stream_settings.spiderx or ""
                }
            config["streamSettings"] = stream
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

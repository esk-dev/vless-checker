"""Cloudflare WARP proxy configuration for Xray.

This module handles:
- Building WARP SOCKS5 outbound configuration
- Creating WARP routing rules for specific domains
- Enabling/disabling WARP with simple configuration
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class WarpConfig:
    """WARP proxy configuration.
    
    Args:
        enabled: Enable WARP proxy (default: False)
        port: WARP SOCKS5 port (default: 40000)
        domains: List of domains to route through WARP
    """
    enabled: bool = False
    port: int = 40000
    domains: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize default domains if not provided."""
        if not self.domains:
            self.domains = []
    
    def is_enabled(self) -> bool:
        """Check if WARP is enabled and has domains configured.
        
        Returns:
            True if WARP is enabled and domains are configured
        """
        return self.enabled and len(self.domains) > 0
    
    def add_domain(self, domain: str) -> 'WarpConfig':
        """Add a domain to WARP routing.
        
        Args:
            domain: Domain to add
            
        Returns:
            Self for method chaining
        """
        if domain not in self.domains:
            self.domains.append(domain)
        return self
    
    def set_domains(self, domains: List[str]) -> 'WarpConfig':
        """Set the list of domains for WARP routing.
        
        Args:
            domains: List of domains to route through WARP
            
        Returns:
            Self for method chaining
        """
        self.domains = domains
        return self
    
    def build_outbound(self) -> Optional[Dict[str, Any]]:
        """Build WARP outbound configuration.
        
        Returns:
            WARP outbound config dict or None if WARP not enabled
        """
        if not self.is_enabled():
            return None
        
        return {
            "protocol": "socks",
            "tag": "warp-proxy",
            "settings": {
                "servers": [{
                    "address": "127.0.0.1",
                    "port": self.port
                }]
            }
        }
    
    def build_routing_rules(self) -> List[Dict[str, Any]]:
        """Build WARP routing rules.
        
        Returns:
            List of WARP routing rules, or empty list if WARP not enabled
        """
        if not self.is_enabled():
            return []
        
        return [
            {
                "type": "field",
                "domain": [f"full:{domain}"],
                "outboundTag": "warp-proxy"
            }
            for domain in self.domains
        ]
    
    @classmethod
    def from_env(cls, enabled: bool = True) -> 'WarpConfig':
        """Create WarpConfig from environment variables.
        
        Args:
            enabled: Enable WARP by default
            
        Returns:
            WarpConfig with environment-based settings
        """
        import os
        
        # Get WARP port from environment or use default
        port = int(os.getenv("WARP_SOCKS_PORT", "40000"))
        
        # Get WARP domains from environment
        domains_str = os.getenv("WARP_DOMAINS", "")
        if domains_str:
            domains = [d.strip() for d in domains_str.split(",") if d.strip()]
        else:
            domains = []
        
        return cls(
            enabled=enabled,
            port=port,
            domains=domains
        )

"""IPv6 blocking configuration for Xray.

This module handles:
- Building IPv6 blocking rules
- Allowing Russian IPv6 traffic to go direct
- Enabling/disabling IPv6 blocking
"""
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class IPv6Config:
    """IPv6 blocking configuration.
    
    Args:
        enabled: Enable IPv6 blocking (default: True)
    """
    enabled: bool = True
    
    def is_enabled(self) -> bool:
        """Check if IPv6 blocking is enabled.
        
        Returns:
            True if IPv6 blocking is enabled
        """
        return self.enabled
    
    def enable(self) -> 'IPv6Config':
        """Enable IPv6 blocking.
        
        Returns:
            Self for method chaining
        """
        self.enabled = True
        return self
    
    def disable(self) -> 'IPv6Config':
        """Disable IPv6 blocking.
        
        Returns:
            Self for method chaining
        """
        self.enabled = False
        return self
    
    def build_rules(self) -> List[Dict[str, Any]]:
        """Build IPv6 blocking rules.
        
        Returns:
            List of IPv6 routing rules, or empty list if disabled
        """
        if not self.enabled:
            return []
        
        return [
            # Block IPv6 traffic via proxy - route to blocked
            {
                "type": "field",
                "ip": ["geoip6:all"],
                "outboundTag": "blocked"
            },
            # Allow Russian IPv6 traffic to go direct
            {
                "type": "field",
                "ip": ["geoip6:ru"],
                "outboundTag": "direct"
            }
        ]
    
    @classmethod
    def from_env(cls, enabled: bool = True) -> 'IPv6Config':
        """Create IPv6Config from environment variable.
        
        Args:
            enabled: Default enabled state
            
        Returns:
            IPv6Config with environment-based settings
        """
        import os
        
        enabled_str = os.getenv("ENABLE_IPV6_BLOCK", "true").lower()
        if enabled_str in ("true", "1", "yes"):
            return cls(enabled=True)
        return cls(enabled=False)

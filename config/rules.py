# rules.py
"""Routing rules builder for Xray configuration.

This module handles:
- Building base routing rules (RU domains, blocked sites)
- IPv6 blocking rules
- WARP routing rules
- Composing all rules together
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class RoutingRulesBuilder:
    """Build routing rules for Xray configuration.
    
    Args:
        enable_ipv6_block: Enable IPv6 blocking (default: True)
        warp_config: Optional WarpConfig for WARP routing
    """
    enable_ipv6_block: bool = True
    warp_config: Optional['WarpConfig'] = None
    
    def build_base_rules(self) -> List[Dict[str, Any]]:
        """Build base routing rules.
        
        Returns:
            List of base routing rules
        """
        return [
            # ru-IPs - direct
            {
                "type": "field",
                "ip": ["geoip:ru-blocked"],
                "outboundTag": "direct"
            },
            # Blocked sites - direct (block or direct)
            {
                "type": "field",
                "domain": ["geosite:ru-blocked"],
                "outboundTag": "direct"
            }
        ]
    
    def build_ipv6_rules(self) -> List[Dict[str, Any]]:
        """Build IPv6 blocking rules.
        
        Returns:
            List of IPv6 routing rules
        """
        # Note: geoip6:all and geoip6:ru are not available in geoip.dat
        # The runetfreedom geoip.dat only contains IPv4 ranges
        # If IPv6 blocking is needed, use outbound tag "blocked" with domain rules
        return []
    
    def build_warp_rules(self) -> List[Dict[str, Any]]:
        """Build WARP routing rules.
        
        Returns:
            List of WARP routing rules, or empty list if WARP not enabled
        """
        if not self.warp_config or not self.warp_config.is_enabled():
            return []
        
        return [
            {
                "type": "field",
                "domain": [f"full:{domain}"],
                "outboundTag": "warp-proxy"
            }
            for domain in self.warp_config.domains
        ]
    
    def build_all_rules(self) -> List[Dict[str, Any]]:
        """Build all routing rules including IPv6 and WARP.
        
        Returns:
            Complete list of routing rules
        """
        rules = self.build_base_rules()
        
        if self.enable_ipv6_block:
            rules.extend(self.build_ipv6_rules())
        
        if self.warp_config and self.warp_config.is_enabled():
            rules.extend(self.build_warp_rules())
        
        return rules


# For type hints in other modules, this import is needed
# WarpConfig must be defined before or imported after this module
# The circular import will be resolved in the main config/__init__.py

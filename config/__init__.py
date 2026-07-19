# Config module for VLESS Gateway Manager
"""Configuration building and management for Xray."""
from .builder import XrayConfigBuilder, OutboundConfig, StreamSettings
from .vless import VLESSInfo, parse_vless_key
from .warp import WarpConfig
from .ipv6 import IPv6Config
from .rules import RoutingRulesBuilder
from .ss import generate_shadowsocks_key, generate_shadowsocks_key_with_params

__all__ = [
    'XrayConfigBuilder',
    'OutboundConfig',
    'StreamSettings',
    'VLESSInfo',
    'parse_vless_key',
    'WarpConfig',
    'IPv6Config',
    'RoutingRulesBuilder',
    'generate_shadowsocks_key',
    'generate_shadowsocks_key_with_params',
]

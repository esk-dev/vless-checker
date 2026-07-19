"""Shadowsocks key generation utilities.

This module handles:
- Generating Shadowsocks shareable links for Outline clients
- Base64 encoding for authentication strings
"""
import base64
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def generate_shadowsocks_key(
    ss_method: Optional[str] = None,
    ss_password: Optional[str] = None,
    vps_ip: Optional[str] = None,
    ss_port: Optional[int] = None
) -> str:
    """Generate a Shadowsocks shareable link for Outline clients.
    
    Format: ss://[BASE64(method:password)]@[IP]:PORT#TAG
    
    Args:
        ss_method: Encryption method (e.g., 'aes-256-gcm', '2022-blake3-aes-128-gcm')
        ss_password: Password for the Shadowsocks connection
        vps_ip: IP address of your VPS/server
        ss_port: Port for the Shadowsocks service
        
    Returns:
        A shareable Shadowsocks URL for Outline clients
    """
    method = ss_method or os.getenv("SS_METHOD", "2022-blake3-aes-128-gcm")
    password = ss_password or os.getenv("SS_PASSWORD", "your_secure_password_here")
    
    # Get VPS IP from environment or use placeholder
    vps = vps_ip or os.getenv("VPS_IP", "YOUR_VPS_IP_ADDRESS")
    
    # Port for Shadowsocks (from environment or default)
    port = ss_port or int(os.getenv("SS_INBOUND_PORT", 8388))
    
    # Combine method and password with colon
    auth_string = f"{method}:{password}"
    
    # Encode to Base64
    encoded_auth = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
    
    # Create the shareable link
    ss_link = f"ss://{encoded_auth}@{vps}:{port}#MyVLESSRotator"
    
    logger.info(f"Generated Shadowsocks key: {ss_link[:30]}...")
    
    return ss_link


def generate_shadowsocks_key_with_params(
    ss_method: Optional[str] = None,
    ss_password: Optional[str] = None,
    vps_ip: Optional[str] = None,
    ss_port: Optional[int] = None
) -> str:
    """Generate a Shadowsocks shareable link with custom parameters.
    
    Args:
        ss_method: Encryption method (e.g., 'aes-256-gcm', '2022-blake3-aes-128-gcm')
        ss_password: Password for the Shadowsocks connection
        vps_ip: IP address of your VPS/server
        ss_port: Port for the Shadowsocks service
        
    Returns:
        A shareable Shadowsocks URL for Outline clients
    """
    return generate_shadowsocks_key(ss_method, ss_password, vps_ip, ss_port)

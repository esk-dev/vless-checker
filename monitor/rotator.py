"""Key rotation logic for VLESS gateway.

This module handles:
- Rotating between VLESS keys
- Managing key pool state
- Getting current and next keys
"""
from typing import List, Optional


class KeyRotator:
    """Handles key rotation logic independently.
    
    This class provides clean key rotation functionality:
    - Get current key
    - Rotate to next key
    - Get next key without rotating
    
    Args:
        key_pool: List of VLESS keys to rotate through
    """
    
    def __init__(self, key_pool: List[str]):
        """Initialize the key rotator.
        
        Args:
            key_pool: List of VLESS keys to rotate through
        """
        self.key_pool = key_pool
        self.current_index = 0
        self.pool_size = len(key_pool)
    
    def get_current_key(self) -> Optional[str]:
        """Get current key without rotation.
        
        Returns:
            Current VLESS key or None if pool is empty
        """
        if not self.key_pool:
            return None
        return self.key_pool[self.current_index]
    
    def rotate(self) -> Optional[str]:
        """Rotate to next key and return it.
        
        Returns:
            New current VLESS key or None if pool is empty
        """
        if not self.key_pool:
            return None
        
        self.current_index = (self.current_index + 1) % self.pool_size
        return self.get_current_key()
    
    def get_next_key(self) -> Optional[str]:
        """Get next key without rotating.
        
        Returns:
            Next VLESS key or None if pool is empty
        """
        if not self.key_pool:
            return None
        
        next_index = (self.current_index + 1) % self.pool_size
        return self.key_pool[next_index]
    
    def get_index(self) -> int:
        """Get current key index.
        
        Returns:
            Current key index
        """
        return self.current_index
    
    def set_index(self, index: int) -> 'KeyRotator':
        """Set current key index.
        
        Args:
            index: Key index to set
            
        Returns:
            Self for method chaining
        """
        if self.key_pool and 0 <= index < self.pool_size:
            self.current_index = index
        return self
    
    def is_key_alive(self, key: str) -> bool:
        """Check if a key is the current key.
        
        Args:
            key: VLESS key to check
            
        Returns:
            True if the key matches current key
        """
        return self.get_current_key() == key
    
    def reset(self) -> 'KeyRotator':
        """Reset to first key.
        
        Returns:
            Self for method chaining
        """
        self.current_index = 0
        return self

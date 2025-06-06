"""
Simple in-memory cache for JSON configuration files.
Thread-safe caching with automatic file modification detection.

This cache improves performance by keeping frequently accessed JSON files
(squadrons, aircraft, bases, etc.) in memory instead of reading from disk
on every request.
"""
import json
import os
import threading
import time
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class JSONFileCache:
    """
    Thread-safe cache for JSON files with automatic reload on file changes.
    
    Features:
    - In-memory storage of parsed JSON data
    - Automatic detection of file modifications
    - Thread-safe access using locks
    - Configurable TTL (time-to-live) for cache entries
    """
    
    def __init__(self, default_ttl: int = 300):
        """
        Initialize the cache.
        
        Args:
            default_ttl: Default time-to-live for cache entries in seconds (5 minutes)
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._default_ttl = default_ttl
        logger.info(f"[CACHE] JSONFileCache initialized with TTL={default_ttl}s")
    
    def get(self, file_path: str, ttl: Optional[int] = None) -> Dict[str, Any]:
        """
        Get JSON data from cache or load from file.
        
        Args:
            file_path: Absolute path to the JSON file
            ttl: Time-to-live override for this specific file
            
        Returns:
            Parsed JSON data as dictionary
            
        Raises:
            FileNotFoundError: If the JSON file doesn't exist
            json.JSONDecodeError: If the file contains invalid JSON
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"JSON file not found: {file_path}")
        
        file_path = os.path.abspath(file_path)
        ttl = ttl or self._default_ttl
        
        with self._lock:
            # Check if we have cached data
            if file_path in self._cache:
                cache_entry = self._cache[file_path]
                current_time = time.time()
                file_mtime = os.path.getmtime(file_path)
                
                # Check if cache is still valid (not expired and file not modified)
                if (current_time - cache_entry['cached_at'] < ttl and 
                    cache_entry['file_mtime'] >= file_mtime):
                    # Reduced logging - only log cache hits in debug mode
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"[CACHE] Cache HIT for {os.path.basename(file_path)}")
                    return cache_entry['data']
                else:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"[CACHE] Cache EXPIRED for {os.path.basename(file_path)}")
            
            # Cache miss or expired - load from file
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"[CACHE] Loading from disk: {os.path.basename(file_path)}")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Store in cache
                self._cache[file_path] = {
                    'data': data,
                    'cached_at': time.time(),
                    'file_mtime': os.path.getmtime(file_path)
                }
                
                # Reduced logging for cache operations
                if logger.isEnabledFor(logging.INFO):
                    logger.info(f"[CACHE] Cached {os.path.basename(file_path)} ({len(str(data))} chars)")
                return data
                
            except json.JSONDecodeError as e:
                logger.error(f"[CACHE] Invalid JSON in {file_path}: {e}")
                raise
            except Exception as e:
                logger.error(f"[CACHE] Error loading {file_path}: {e}")
                raise
    
    def invalidate(self, file_path: str = None):
        """
        Invalidate cache entries.
        
        Args:
            file_path: Specific file to invalidate, or None to clear all cache
        """
        with self._lock:
            if file_path:
                file_path = os.path.abspath(file_path)
                if file_path in self._cache:
                    del self._cache[file_path]
                    logger.info(f"[CACHE] Invalidated cache for {os.path.basename(file_path)}")
            else:
                self._cache.clear()
                logger.info("[CACHE] All cache entries cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        with self._lock:
            stats = {
                'total_entries': len(self._cache),
                'files_cached': [os.path.basename(path) for path in self._cache.keys()],
                'cache_size_bytes': sum(len(str(entry['data'])) for entry in self._cache.values())
            }
            return stats


# Global cache instance
_json_cache = JSONFileCache()

def get_cached_json(file_path: str, ttl: Optional[int] = None) -> Dict[str, Any]:
    """
    Convenience function to get cached JSON data.
    
    Args:
        file_path: Path to JSON file
        ttl: Optional TTL override
        
    Returns:
        Parsed JSON data
    """
    return _json_cache.get(file_path, ttl)

def invalidate_cache(file_path: str = None):
    """
    Convenience function to invalidate cache.
    
    Args:
        file_path: Specific file to invalidate, or None for all
    """
    _json_cache.invalidate(file_path)

def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics.
    
    Returns:
        Cache statistics dictionary
    """
    return _json_cache.get_stats()

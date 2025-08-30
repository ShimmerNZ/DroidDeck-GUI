"""
WALL-E Control System - Configuration Management (Updated)
"""

import json
import os
from functools import lru_cache
from typing import Dict, Any, Optional

from .logger import get_logger


class ConfigManager:
    """Singleton configuration manager with caching and file monitoring"""
    _instance = None
    _configs: Dict[str, Dict] = {}
    _last_modified: Dict[str, float] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.logger = get_logger("config")
        return cls._instance
    
    @lru_cache(maxsize=32)
    def get_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration with file modification time checking"""
        try:
            if not os.path.exists(config_path):
                self.logger.warning(f"Config file not found: {config_path}")
                return {}
                
            current_mtime = os.path.getmtime(config_path)
            if (config_path not in self._last_modified or 
                self._last_modified[config_path] < current_mtime):
                
                with open(config_path, "r") as f:
                    self._configs[config_path] = json.load(f)
                self._last_modified[config_path] = current_mtime
                self.logger.debug(f"Loaded config: {config_path}")
                
            return self._configs[config_path]
        except Exception as e:
            self.logger.error(f"Failed to load config {config_path}: {e}")
            return {}
    
    def save_config(self, config_path: str, config_data: Dict[str, Any]) -> bool:
        """Save configuration to file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)
            
            # Update cache
            self._configs[config_path] = config_data
            self._last_modified[config_path] = os.path.getmtime(config_path)
            self.clear_cache()
            
            self.logger.info(f"Saved config: {config_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save config {config_path}: {e}")
            return False
    
    def get_wave_config(self) -> Dict[str, Any]:
        """Get wave detection configuration with defaults"""
        config = self.get_config("resources/configs/steamdeck_config.json")
        wave_config = config.get("current", {})
        wave_settings = wave_config.get("wave_detection", {})
        
        return {
            "esp32_cam_url": wave_config.get("esp32_cam_url", ""),
            "camera_proxy_url": wave_config.get("camera_proxy_url", ""),
            "sample_duration": wave_settings.get("sample_duration", 3),
            "sample_rate": wave_settings.get("sample_rate", 5),
            "confidence_threshold": wave_settings.get("confidence_threshold", 0.7),
            "stand_down_time": wave_settings.get("stand_down_time", 30)
        }
    
    def get_network_config(self) -> Dict[str, Any]:
        """Get network monitoring configuration with defaults"""
        config = self.get_config("resources/configs/steamdeck_config.json")
        current = config.get("current", {})
        network_settings = current.get("network_monitoring", {})
        
        return {
            "update_interval": network_settings.get("update_interval", 5.0),
            "ping_samples": network_settings.get("ping_samples", 3),
            "pi_ip": self.extract_pi_ip_from_config(current)
        }
    
    def extract_pi_ip_from_config(self, config: Dict[str, Any]) -> str:
        """Extract Pi IP from camera proxy URL"""
        proxy_url = config.get("camera_proxy_url", "http://10.1.1.230:8081")
        try:
            import re
            ip_match = re.search(r'http://([^:]+)', proxy_url)
            return ip_match.group(1) if ip_match else "10.1.1.230"
        except:
            return "10.1.1.230"
    
    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration with defaults"""
        config = self.get_config("resources/configs/steamdeck_config.json")
        current = config.get("current", {})
        
        return {
            "debug_level": current.get("debug_level", "INFO"),
            "module_debug": current.get("module_debug", {
                "camera": "INFO",
                "servo": "INFO",
                "network": "INFO",
                "websocket": "WARNING", 
                "telemetry": "INFO",
                "ui": "INFO",
                "config": "WARNING",
                "main": "INFO",
                "controller": "INFO",
                "error": "ERROR"
            })
        }
    
    def get_websocket_url(self) -> str:
        """Get WebSocket URL with default"""
        config = self.get_config("resources/configs/steamdeck_config.json")
        return config.get("current", {}).get("control_websocket_url", "localhost:8766")
    
    def clear_cache(self):
        """Clear configuration cache"""
        self.get_config.cache_clear()
        self._configs.clear()
        self._last_modified.clear()
        self.logger.debug("Configuration cache cleared")
    
    def load_servo_names(self) -> list:
        """Load servo friendly names from configuration"""
        try:
            config = self.get_config("resources/configs/servo_config.json")
            return [v["name"] for v in config.values() if "name" in v and v["name"]]
        except Exception as e:
            self.logger.error(f"Failed to load servo names: {e}")
            return []
    
    def load_movement_controls(self) -> tuple:
        """Load movement controls from configuration"""
        try:
            config = self.get_config("resources/configs/movement_controls.json")
            return (
                config.get("steam_controls", []),
                config.get("nema_movements", [])
            )
        except Exception as e:
            self.logger.error(f"Failed to load movement controls: {e}")
            return [], []


# Global config manager instance
config_manager = ConfigManager()
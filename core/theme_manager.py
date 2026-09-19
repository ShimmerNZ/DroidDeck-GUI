# core/theme_manager.py

import os
import json
from pathlib import Path
from typing import Callable, Dict, Any, List
from .logger import get_logger


class ThemeManager:
    """Manages application themes with dynamic switching capability"""
    
    # Define available themes and their properties
    THEMES: Dict[str, Dict[str, Any]] = {
        "Wall-e": {
            "name": "Wall-e",
            "display_name": "WALL-E",
            "primary_color": "#e1a014",
            "primary_light": "#f4c430",
            "primary_gradient": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e1a014, stop:1 #FFD700)",
            "panel_bg": "#181818",
            "panel_dark": "#1e1e1e",
            "card_bg": "#252525",
            "grey": "#888",
            "grey_light": "#aaa",
            "green": "#44bb44",
            "green_gradient": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #44bb44, stop:1 #228822)",
            "red": "#cc4444",
            "dark_bg": "#1a1a1a",
            "expanded_bg": "#2a2a2a",
            "image_main": "resources/theme/Wall-e/walle.png",
            "background": "resources/theme/Wall-e/background.png",
            "icons": {
                "home": "resources/theme/Wall-e/icons/Home.png",
                "home_pressed": "resources/theme/Wall-e/icons/Home_pressed.png",
                "camera": "resources/theme/Wall-e/icons/Camera.png",
                "camera_pressed": "resources/theme/Wall-e/icons/Camera_pressed.png",
                "health": "resources/theme/Wall-e/icons/Health.png",
                "health_pressed": "resources/theme/Wall-e/icons/Health_pressed.png",
                "servo": "resources/theme/Wall-e/icons/ServoConfig.png",
                "servo_pressed": "resources/theme/Wall-e/icons/ServoConfig_pressed.png",
                "controller": "resources/theme/Wall-e/icons/Controller.png",
                "controller_pressed": "resources/theme/Wall-e/icons/Controller_pressed.png",
                "settings": "resources/theme/Wall-e/icons/Settings.png",
                "settings_pressed": "resources/theme/Wall-e/icons/Settings_pressed.png",
                "scene": "resources/theme/Wall-e/icons/Scene.png",
                "scene_pressed": "resources/theme/Wall-e/icons/Scene_pressed.png",
                "failsafe": "resources/theme/Wall-e/icons/failsafe.png",
                "failsafe_pressed": "resources/theme/Wall-e/icons/failsafe_pressed.png"
            }
        },
        "Star Wars": {
            "name": "Star Wars",
            "display_name": "Star Wars",
            "primary_color": "#1976d2",
            "primary_light": "#63a4ff",
            "primary_gradient": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1976d2, stop:1 #63a4ff)",
            "panel_bg": "#0a1929",
            "panel_dark": "#1e2328",
            "card_bg": "#1a2332",
            "grey": "#888",
            "grey_light": "#aaa",
            "green": "#2e7d32",
            "green_gradient": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4caf50, stop:1 #2e7d32)",
            "red": "#d32f2f",
            "dark_bg": "#0d1421",
            "expanded_bg": "#1a2332",
            "image_main": "resources/theme/Star Wars/r2d2.png",
            "background": "resources/theme/Star Wars/background.png",
            "icons": {
                "home": "resources/theme/Star Wars/icons/Home.png",
                "home_pressed": "resources/theme/Star Wars/icons/Home_pressed.png",
                "camera": "resources/theme/Star Wars/icons/Camera.png",
                "camera_pressed": "resources/theme/Star Wars/icons/Camera_pressed.png",
                "health": "resources/theme/Star Wars/icons/Health.png",
                "health_pressed": "resources/theme/Star Wars/icons/Health_pressed.png",
                "servo": "resources/theme/Star Wars/icons/ServoConfig.png",
                "servo_pressed": "resources/theme/Star Wars/icons/ServoConfig_pressed.png",
                "controller": "resources/theme/Star Wars/icons/Controller.png",
                "controller_pressed": "resources/theme/Star Wars/icons/Controller_pressed.png",
                "settings": "resources/theme/Star Wars/icons/Settings.png",
                "settings_pressed": "resources/theme/Star Wars/icons/Settings_pressed.png",
                "scene": "resources/theme/Star Wars/icons/Scene.png",
                "scene_pressed": "resources/theme/Star Wars/icons/Scene_pressed.png",
                "failsafe": "resources/theme/Star Wars/icons/failsafe.png",
                "failsafe_pressed": "resources/theme/Star Wars/icons/failsafe_pressed.png"
            }
        }
    }

    _current_theme: Dict[str, Any] = THEMES["Wall-e"]
    _callbacks: List[Callable[[], None]] = []
    _logger = None
    _config_path = "resources/configs/theme_config.json"

    @classmethod
    def _get_logger(cls):
        if cls._logger is None:
            cls._logger = get_logger("theme")
        return cls._logger

    @classmethod
    def initialize(cls):
        """Initialize theme manager and load saved theme"""
        cls._load_saved_theme()

    @classmethod
    def available_themes(cls) -> List[str]:
        """Get list of available theme names"""
        return list(cls.THEMES.keys())

    @classmethod
    def get_theme_name(cls) -> str:
        """Get current theme name"""
        return cls._current_theme["name"]

    @classmethod
    def get_display_name(cls) -> str:
        """Get current theme display name"""
        return cls._current_theme.get("display_name", cls._current_theme["name"])

    @classmethod
    def set_theme(cls, theme_name: str) -> bool:
        """Set active theme and save to config"""
        if theme_name not in cls.THEMES:
            cls._get_logger().error(f"Theme '{theme_name}' not found. Available: {list(cls.THEMES.keys())}")
            return False
        
        if cls._current_theme["name"] == theme_name:
            return True  # Already active
        
        cls._current_theme = cls.THEMES[theme_name]
        cls._save_theme_config()
        cls._notify_theme_changed()
        cls._get_logger().info(f"Theme changed to: {theme_name}")
        return True

    @classmethod
    def get(cls, key: str, default=None):
        """Get theme property value"""
        return cls._current_theme.get(key, default)

    @classmethod
    def get_icon_path(cls, icon_name: str, pressed: bool = False) -> str:
        """Get path to themed icon"""
        icons = cls._current_theme.get("icons", {})
        if pressed:
            icon_key = f"{icon_name}_pressed"
            if icon_key in icons:
                return icons[icon_key]
        
        # Fallback to normal icon
        return icons.get(icon_name, f"resources/icons/{icon_name}.png")

    @classmethod
    def get_image_path(cls, image_key: str) -> str:
        """Get path to themed image"""
        if image_key == "main":
            return cls._current_theme.get("image_main", "resources/images/walle.png")
        elif image_key == "background":
            return cls._current_theme.get("background", "resources/images/background.png")
        else:
            return cls._current_theme.get(image_key, f"resources/images/{image_key}.png")

    @classmethod
    def get_button_style(cls, style_type: str = "default", checked: bool = False) -> str:
        """Get themed button stylesheet"""
        primary = cls.get("primary_color")
        primary_light = cls.get("primary_light")
        primary_gradient = cls.get("primary_gradient")
        grey = cls.get("grey")
        
        if style_type == "primary":
            if checked:
                return f"""
                QPushButton {{
                    background: {primary_gradient};
                    border: 2px solid {primary};
                    border-radius: 8px;
                    color: black;
                    font-weight: bold;
                    padding: 8px 16px;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {primary_light}, stop:1 {primary});
                }}
                """
            else:
                return f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #4a4a4a, stop:1 #2a2a2a);
                    border: 2px solid #666;
                    border-radius: 8px;
                    color: #ccc;
                    font-weight: bold;
                    padding: 8px 16px;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #5a5a5a, stop:1 #3a3a3a);
                    border: 2px solid {primary};
                    color: {primary};
                }}
                """
        
        # Default style
        return f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #4a4a4a, stop:1 #2a2a2a);
            color: white;
            border: 1px solid #666;
            border-radius: 6px;
            padding: 6px;
            text-align: center;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #5a5a5a, stop:1 #3a3a3a);
            border-color: #888;
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #3a3a3a, stop:1 #1a1a1a);
            border-color: {primary};
        }}
        """

    @classmethod
    def get_panel_style(cls, style_type: str = "main") -> str:
        """Get themed panel stylesheet"""
        primary = cls.get("primary_color")
        panel_bg = cls.get("panel_bg")
        panel_dark = cls.get("panel_dark")
        
        if style_type == "main":
            return f"""
            QWidget {{
                background-color: {panel_dark};
                border: 2px solid {primary};
                border-radius: 12px;
                color: white;
            }}
            """
        elif style_type == "section":
            return f"""
            QWidget {{
                border: 1px solid #555;
                border-radius: 8px;
                background-color: rgba(0, 0, 0, 0.3);
            }}
            """
        
        return f"""
        QWidget {{
            background-color: {panel_bg};
            color: white;
        }}
        """

    @classmethod
    def register_callback(cls, callback: Callable[[], None]):
        """Register a callback to be called when the theme changes"""
        if callback not in cls._callbacks:
            cls._callbacks.append(callback)

    @classmethod
    def unregister_callback(cls, callback: Callable[[], None]):
        """Unregister a theme change callback"""
        if callback in cls._callbacks:
            cls._callbacks.remove(callback)

    @classmethod
    def _notify_theme_changed(cls):
        """Notify all registered callbacks of theme change"""
        cls._get_logger().debug(f"Notifying {len(cls._callbacks)} theme change callbacks")
        for callback in cls._callbacks:
            try:
                callback()
            except Exception as e:
                cls._get_logger().error(f"Theme callback error: {e}")

    @classmethod
    def _load_saved_theme(cls):
        """Load saved theme from config file"""
        try:
            if os.path.exists(cls._config_path):
                with open(cls._config_path, 'r') as f:
                    config = json.load(f)
                    saved_theme = config.get("current_theme", "Wall-e")
                    if saved_theme in cls.THEMES:
                        cls._current_theme = cls.THEMES[saved_theme]
                        cls._get_logger().info(f"Loaded saved theme: {saved_theme}")
                    else:
                        cls._get_logger().warning(f"Invalid saved theme: {saved_theme}, using default")
        except Exception as e:
            cls._get_logger().error(f"Failed to load saved theme: {e}")

    @classmethod
    def _save_theme_config(cls):
        """Save current theme to config file"""
        try:
            os.makedirs(os.path.dirname(cls._config_path), exist_ok=True)
            config = {"current_theme": cls._current_theme["name"]}
            with open(cls._config_path, 'w') as f:
                json.dump(config, f, indent=2)
            cls._get_logger().debug(f"Theme config saved: {cls._current_theme['name']}")
        except Exception as e:
            cls._get_logger().error(f"Failed to save theme config: {e}")


# Global theme manager instance (initialize on import)
theme_manager = ThemeManager()
theme_manager.initialize()
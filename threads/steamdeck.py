#!/usr/bin/env python3
"""
SteamDeck Controller Thread - PyQt6 Gamepad Input Handler
Handles SteamDeck gamepad input with safety monitoring and WebSocket communication
"""

import pygame
import time
import json
from typing import Dict, Any, Optional
from PyQt6.QtCore import QThread, pyqtSignal

from core.logger import get_logger
from core.config_manager import config_manager
from core.utils import error_boundary


class ControllerInputData:
    """Container for controller input data"""
    def __init__(self, axes: Dict[str, float], buttons: Dict[str, bool], 
                 timestamp: float, sequence: int):
        self.axes = axes
        self.buttons = buttons  
        self.timestamp = timestamp
        self.sequence = sequence
        self.source = "steamdeck"


class SteamDeckControllerThread(QThread):
    """Thread for handling SteamDeck gamepad input with safety monitoring"""
    
    # Qt signals for thread-safe communication
    controller_input = pyqtSignal(ControllerInputData)
    controller_connected = pyqtSignal(str, str)  # controller_name, controller_id
    controller_disconnected = pyqtSignal(str)     # reason
    heartbeat_signal = pyqtSignal(float)          # timestamp
    stats_updated = pyqtSignal(dict)              # statistics
    
    def __init__(self, websocket_manager=None):
        super().__init__()
        self.logger = get_logger("controller")
        self.websocket_manager = websocket_manager
        
        # Thread control
        self.running = False
        self.controller_active = False
        
        # Controller state
        self.joystick = None
        self.controller_name = ""
        self.controller_id = ""
        self.last_controller_state = None
        self.sequence_number = 0
        
        # Timing control
        self.poll_rate_hz = 60  # 60Hz for responsive control
        self.poll_interval = 1.0 / self.poll_rate_hz
        self.heartbeat_interval = 0.5  # 500ms heartbeat
        self.last_heartbeat = 0
        
        # Safety monitoring
        self.safety_enabled = True
        self.max_missed_heartbeats = 3  # Stop after 1.5 seconds
        self.last_input_sent = 0
        
        # Statistics
        self.stats = {
            "inputs_processed": 0,
            "inputs_sent": 0,
            "connection_attempts": 0,
            "disconnections": 0,
            "start_time": 0,
            "last_input_time": 0
        }
        
        # Load controller mappings from config
        self.button_mappings = {}
        self.axis_mappings = {}
        self._load_controller_mappings()
        
        self.logger.info("SteamDeck controller thread initialized")
        
    def _load_controller_mappings(self):
        """Load controller button/axis mappings from configuration"""
        try:
            # Use existing get_config method instead of non-existent get_controller_mappings
            mappings_config = config_manager.get_config("resources/configs/controller_mappings.json")
            
            if not mappings_config:
                self.logger.warning("No controller mappings file found, using defaults")
                self._set_default_mappings()
                return
                
            steam_deck_config = mappings_config.get("steam_deck", {})
            if not steam_deck_config:
                self.logger.warning("No Steam Deck config found in mappings, using defaults")
                self._set_default_mappings()
                return
                
            self.button_mappings = steam_deck_config.get("button_map", {})
            self.axis_mappings = steam_deck_config.get("axis_map", {})
            
            self.logger.info(f"Loaded SteamDeck mappings: {len(self.button_mappings)} buttons, {len(self.axis_mappings)} axes")
            
            # Fallback to defaults if mappings are empty
            if not self.button_mappings and not self.axis_mappings:
                self.logger.warning("Empty controller mappings loaded, using defaults")
                self._set_default_mappings()
            
        except Exception as e:
            self.logger.error(f"Failed to load controller mappings: {e}")
            self._set_default_mappings()
    
    def _set_default_mappings(self):
        """Set default SteamDeck controller mappings"""
        self.button_mappings = {
            "0": "button_b",
            "1": "button_a", 
            "2": "button_x",
            "3": "button_y",
            "4": "button_start",
            "5": "shoulder_left",
            "6": "shoulder_right",
            "9": "button_back",
            "11": "button_guide"
        }
        
        self.axis_mappings = {
            "0": "left_stick_x",
            "1": "left_stick_y",
            "2": "right_stick_x", 
            "3": "right_stick_y",
            "7": "left_trigger",
            "8": "right_trigger"
        }
        
        self.logger.info("Using default SteamDeck controller mappings")
    
    def start_monitoring(self):
        """Start the controller monitoring thread"""
        if not self.running:
            self.running = True
            self.stats["start_time"] = time.time()
            self.start()
            self.logger.info("SteamDeck controller monitoring started")
    
    def stop_monitoring(self):
        """Stop the controller monitoring thread"""
        self.running = False
        if self.isRunning():
            self.quit()
            self.wait(5000)  # Wait up to 5 seconds
        
        self._cleanup_pygame()
        self.logger.info("SteamDeck controller monitoring stopped")
    
    def run(self):
        """Main controller monitoring loop"""
        self._init_pygame()
        
        while self.running:
            try:
                current_time = time.time()
                
                # Handle pygame events (required for joystick updates)
                pygame.event.pump()
                
                # Check for controller connection/disconnection
                self._check_controller_connection()
                
                # Process controller input if connected
                if self.controller_active and self.joystick:
                    self._process_controller_input(current_time)
                
                # Send heartbeat if needed
                if current_time - self.last_heartbeat >= self.heartbeat_interval:
                    self._send_heartbeat(current_time)
                    self.last_heartbeat = current_time
                
                # Update statistics periodically
                if int(current_time) % 5 == 0:  # Every 5 seconds
                    self._update_stats()
                
                # Sleep to maintain desired poll rate
                time.sleep(self.poll_interval)
                
            except Exception as e:
                self.logger.error(f"Controller thread error: {e}")
                time.sleep(1.0)  # Prevent rapid error loops
            
    def _init_pygame(self):
        """Initialize pygame for joystick input"""
        try:
            pygame.init()
            pygame.joystick.init()
            
            joystick_count = pygame.joystick.get_count()
            self.logger.info(f"Pygame initialized - {joystick_count} joysticks detected")
            
            # DEBUG: List all detected joysticks
            for i in range(joystick_count):
                joystick = pygame.joystick.Joystick(i)
                joystick.init()
                self.logger.info(f"Joystick {i}: {joystick.get_name()}")
                joystick.quit()
                
        except Exception as e:
            self.logger.error(f"Failed to initialize pygame: {e}")
            self.running = False
    
    def _cleanup_pygame(self):
        """Clean up pygame resources"""
        try:
            if self.joystick:
                self.joystick.quit()
                self.joystick = None
            
            pygame.joystick.quit()
            pygame.quit()
            self.logger.info("Pygame cleaned up")
            
        except Exception as e:
            self.logger.error(f"Error cleaning up pygame: {e}")
    

    def _check_controller_connection(self):
        """Check for controller connection/disconnection events with safety checks"""
        try:
            # Ensure joystick subsystem is still initialized
            if not pygame.joystick.get_init():
                self.logger.warning("Joystick subsystem not initialized, reinitializing...")
                pygame.joystick.init()
                return
            
            joystick_count = pygame.joystick.get_count()
            
            # Controller connected
            if not self.controller_active and joystick_count > 0:
                try:
                    # Create joystick instance with safety checks
                    self.joystick = pygame.joystick.Joystick(0)  # Use first controller
                    self.joystick.init()
                    
                    # Verify joystick is properly initialized before accessing properties
                    if self.joystick.get_init():
                        self.controller_name = self.joystick.get_name()
                        self.controller_id = f"joy_{self.joystick.get_instance_id()}"
                        self.controller_active = True
                        self.stats["connection_attempts"] += 1
                        
                        self.logger.info(f"Controller connected: {self.controller_name}")
                        self.controller_connected.emit(self.controller_name, self.controller_id)
                    else:
                        self.logger.error("Failed to initialize joystick instance")
                        if self.joystick:
                            try:
                                self.joystick.quit()
                            except:
                                pass
                            self.joystick = None
                            
                except Exception as init_error:
                    self.logger.error(f"Controller initialization error: {init_error}")
                    if hasattr(self, 'joystick') and self.joystick:
                        try:
                            self.joystick.quit()
                        except:
                            pass
                        self.joystick = None
            
            # Controller disconnected  
            elif self.controller_active and joystick_count == 0:
                self._handle_controller_disconnect("Controller physically disconnected")
                
        except Exception as e:
            self.logger.error(f"Controller connection check failed: {e}")
            if self.controller_active:
                self._handle_controller_disconnect(f"Connection error: {e}")


    def _handle_controller_disconnect(self, reason: str):
        """Handle controller disconnection"""
        self.controller_active = False
        self.stats["disconnections"] += 1
        
        if self.joystick:
            try:
                self.joystick.quit()
            except:
                pass
            self.joystick = None
        
        self.logger.warning(f"Controller disconnected: {reason}")
        self.controller_disconnected.emit(reason)
        
        # Send emergency stop via WebSocket
        self._send_emergency_stop(reason)
        
    def _process_controller_input(self, current_time: float):
        """Process current controller input and send via WebSocket with safety checks"""
        try:
            if not self.joystick or not self.joystick.get_init():
                return
                
            # Verify joystick is still valid before accessing
            try:
                # Test if joystick is still accessible
                self.joystick.get_numaxes()
            except pygame.error:
                self.logger.warning("Joystick became invalid, reconnecting...")
                self._handle_controller_disconnect("Joystick became invalid")
                return
                
            # Read analog axes with bounds checking
            axes = {}
            num_axes = self.joystick.get_numaxes()
            for axis_id, axis_name in self.axis_mappings.items():
                axis_index = int(axis_id)
                if axis_index < num_axes:
                    try:
                        raw_value = self.joystick.get_axis(axis_index)
                        # Apply deadzone
                        if abs(raw_value) < 0.05:
                            raw_value = 0.0
                        axes[axis_name] = raw_value
                    except pygame.error as axis_error:
                        self.logger.debug(f"Error reading axis {axis_index}: {axis_error}")
            
            # Read buttons with bounds checking
            buttons = {}
            num_buttons = self.joystick.get_numbuttons()
            for button_id, button_name in self.button_mappings.items():
                button_index = int(button_id)
                if button_index < num_buttons:
                    try:
                        buttons[button_name] = bool(self.joystick.get_button(button_index))
                    except pygame.error as button_error:
                        self.logger.debug(f"Error reading button {button_index}: {button_error}")
            
            # Read D-pad (hat) with bounds checking
            if self.joystick.get_numhats() > 0:
                try:
                    hat_x, hat_y = self.joystick.get_hat(0)
                    buttons.update({
                        "dpad_up": hat_y > 0,
                        "dpad_down": hat_y < 0,
                        "dpad_left": hat_x < 0,
                        "dpad_right": hat_x > 0
                    })
                except pygame.error as hat_error:
                    self.logger.debug(f"Error reading hat: {hat_error}")
            
            # Only create input data if we have some input
            if axes or buttons:
                input_data = ControllerInputData(
                    axes=axes,
                    buttons=buttons,
                    timestamp=current_time,
                    sequence=self.sequence_number
                )
                self.sequence_number += 1
                
                # Send via Qt signal (thread-safe)
                self.controller_input.emit(input_data)
                
                # Send via WebSocket if available
                self._send_controller_websocket(input_data)
                
                # Update statistics
                self.stats["inputs_processed"] += 1
                self.stats["last_input_time"] = current_time
                self.last_input_sent = current_time
                
        except Exception as e:
            self.logger.error(f"Controller input processing error: {e}")
            # Don't crash the thread on input errors
            
    def _send_controller_websocket(self, input_data: ControllerInputData):
        """Send controller data via WebSocket"""
        # FIX 1: Check for correct method name 'send_safe' not 'send_message'
        if not self.websocket_manager or not hasattr(self.websocket_manager, 'send_safe'):
            self.logger.warning("WebSocket manager not available or missing send_safe method")
            return
            
        try:
            message = {
                "type": "steamdeck_controller",
                "axes": input_data.axes,
                "buttons": input_data.buttons,
                "timestamp": input_data.timestamp,
                "sequence": input_data.sequence,
                "source": "steamdeck"
            }
            
            # FIX 2: Don't double-encode JSON - send_safe handles dict conversion
            success = self.websocket_manager.send_safe(message)
            if success:
                self.stats["inputs_sent"] += 1
            else:
                self.logger.debug("Failed to send controller data - WebSocket not connected")
            
        except Exception as e:
            self.logger.error(f"Failed to send controller data via WebSocket: {e}")

    def _send_heartbeat(self, timestamp: float):
        """Send heartbeat signal"""
        self.heartbeat_signal.emit(timestamp)
        
        # Also send via WebSocket
        if self.websocket_manager and hasattr(self.websocket_manager, 'send_safe'):
            try:
                heartbeat_msg = {
                    "type": "controller_heartbeat", 
                    "timestamp": timestamp,
                    "alive": True,
                    "source": "steamdeck"
                }
                success = self.websocket_manager.send_safe(heartbeat_msg)
                if not success:
                    self.logger.debug("Failed to send heartbeat - WebSocket not connected")
            except Exception as e:
                self.logger.error(f"Failed to send heartbeat: {e}")

    def _send_emergency_stop(self, reason: str):
        """Send emergency stop command"""
        if self.websocket_manager and hasattr(self.websocket_manager, 'send_safe'):
            try:
                stop_msg = {
                    "type": "emergency_stop",
                    "reason": f"controller_disconnect: {reason}",
                    "timestamp": time.time(),
                    "source": "steamdeck_controller"
                }
                success = self.websocket_manager.send_safe(stop_msg)
                if success:
                    self.logger.critical(f"🚨 Emergency stop sent: {reason}")
                else:
                    self.logger.error(f"Failed to send emergency stop - WebSocket not connected: {reason}")
            except Exception as e:
                self.logger.error(f"Failed to send emergency stop: {e}")

    def _update_stats(self):
        """Update and emit statistics"""
        current_time = time.time()
        uptime = current_time - self.stats["start_time"] if self.stats["start_time"] > 0 else 0
        
        stats_update = {
            **self.stats,
            "uptime": uptime,
            "controller_active": self.controller_active,
            "controller_name": self.controller_name,
            "input_rate": self.stats["inputs_processed"] / uptime if uptime > 0 else 0,
            "last_input_age": current_time - self.stats["last_input_time"] if self.stats["last_input_time"] > 0 else 0
        }
        
        self.stats_updated.emit(stats_update)
    
    @error_boundary
    def get_controller_info(self) -> Dict[str, Any]:
        """Get current controller information"""
        return {
            "connected": self.controller_active,
            "controller_name": self.controller_name,
            "controller_id": self.controller_id,
            "axes_count": self.joystick.get_numaxes() if self.joystick else 0,
            "button_count": self.joystick.get_numbuttons() if self.joystick else 0,
            "hat_count": self.joystick.get_numhats() if self.joystick else 0,
            "sequence_number": self.sequence_number,
            "poll_rate": self.poll_rate_hz
        }
    
    def set_poll_rate(self, hz: int):
        """Set controller polling rate"""
        if 10 <= hz <= 120:  # Reasonable bounds
            self.poll_rate_hz = hz
            self.poll_interval = 1.0 / hz
            self.logger.info(f"Controller poll rate set to {hz}Hz")
    
    def enable_safety_monitoring(self, enabled: bool):
        """Enable/disable safety monitoring"""
        self.safety_enabled = enabled
        self.logger.info(f"Controller safety monitoring {'enabled' if enabled else 'disabled'}")
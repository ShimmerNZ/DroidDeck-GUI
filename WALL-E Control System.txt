# WALL-E Control System Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Installation & Setup](#installation--setup)
4. [Configuration](#configuration)
5. [Core Components](#core-components)
6. [UI Components](#ui-components)
7. [Background Processing](#background-processing)
8. [API Reference](#api-reference)
9. [Development Guide](#development-guide)
10. [Troubleshooting](#troubleshooting)
11. [To-Do List](#to-do-list)

## Overview

The WALL-E Control System is a comprehensive PyQt6 application for controlling robotic systems through multiple interfaces including live camera feeds, advanced servo control, health monitoring, gesture recognition, and Steam Deck controller mapping. The system uses WebSocket-based communication with automatic reconnection and sophisticated error handling.

### Key Features

- **Live Camera Feed**: MJPEG stream processing with MediaPipe pose detection and wave detection
- **Advanced Servo Control**: Real-time dual-Maestro support with home position indicators, sweep testing, and live position feedback
- **Health Monitoring**: System telemetry with pyqtgraph-based battery/current monitoring and network quality assessment
- **Gesture Recognition**: Configurable wave detection with confidence thresholds and stand-down periods
- **Controller Integration**: Steam Deck control mapping with calibration, differential steering, and advanced input processing
- **Network Monitoring**: WiFi signal strength monitoring with visual indicators and bandwidth testing
- **Scene Management**: Emotion-based scene triggering with audio integration
- **Modular Architecture**: Clean separation with dependency injection and thread-safe communication

### System Requirements

- Python 3.8+
- PyQt6
- pyqtgraph (for health monitoring graphs)
- OpenCV 4.0+ (optional, for camera features)
- MediaPipe (optional, for pose detection)
- Network connectivity to robot backend

## Architecture

The system follows a modular architecture with clear separation between infrastructure, UI, and processing components.

### High-Level Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   UI Widgets    │◄──►│  Core Services   │◄──►│ Background      │
│                 │    │                  │    │ Processing      │
│ - Home Screen   │    │ - Config Manager │    │                 │
│ - Camera Screen │    │ - Logger         │    │ - Image Proc    │
│ - Health Screen │    │ - WebSocket Mgr  │    │ - Network Mon   │
│ - Servo Screen  │    │ - Utils          │    │ - Controller    │
│ - Controller    │    │                  │    │                 │
│ - Settings      │    │                  │    │                 │
│ - Scene Editor  │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
        │                        │                        │
        └────────────────────────┼────────────────────────┘
                                 │
                    ┌──────────────────┐
                    │   Robot Backend  │
                    │   (WebSocket)    │
                    └──────────────────┘
```

### Design Principles

1. **Single Responsibility**: Each module has one clear purpose
2. **Dependency Injection**: Services are passed to components that need them
3. **Error Isolation**: Failures in one component don't cascade
4. **Thread Safety**: Background processing isolated from UI with Qt signals
5. **Configuration Driven**: Behavior controlled through JSON config files
6. **Testability**: Components can be mocked and tested independently

## Installation & Setup

### Prerequisites

```bash
# Install Python dependencies
pip install PyQt6 numpy requests pyqtgraph

# Optional: For camera functionality
pip install opencv-python mediapipe

# Optional: For advanced plotting
pip install matplotlib seaborn
```

### Directory Structure

```
wall-e-frontend/
├── main.py
├── core/
│   ├── __init__.py
│   ├── application.py
│   ├── config_manager.py
│   ├── logger.py
│   ├── websocket_manager.py
│   └── utils.py
├── widgets/
│   ├── __init__.py
│   ├── base_screen.py
│   ├── home_screen.py
│   ├── camera_screen.py
│   ├── health_screen.py
│   ├── servo_screen.py
│   ├── controller_screen.py
│   ├── settings_screen.py
│   └── scene_screen.py
├── threads/
│   ├── __init__.py
│   ├── image_processor.py
│   └── network_monitor.py
├── resources/
│   ├── icons/
│   ├── images/
│   └── configs/
│       ├── steamdeck_config.json
│       ├── servo_config.json
│       ├── motion_config.json
│       ├── controller_config.json
│       ├── emotion_buttons.json
│       └── movement_controls.json
└── tests/
    └── __init__.py
```

### Quick Start

1. Copy all source files to appropriate directories
2. Create configuration files in `resources/configs/`
3. Add icons and images to `resources/` subdirectories
4. Run: `python main.py`

## Configuration

The system uses JSON configuration files managed centrally through the `ConfigManager` class with LRU caching and file modification monitoring.

### Main Configuration File

`resources/configs/steamdeck_config.json`:

```json
{
  "current": {
    "esp32_cam_url": "http://10.1.1.203:81/stream",
    "camera_proxy_url": "http://10.1.1.230:8081/stream",
    "control_websocket_url": "ws://10.1.1.230:8766",
    "debug_level": "ERROR",
    "module_debug": {
      "camera": "ERROR",
      "servo": "ERROR",
      "network": "INFO",
      "websocket": "WARNING",
      "telemetry": "INFO",
      "ui": "INFO",
      "config": "WARNING",
      "main": "INFO",
      "controller": "INFO",
      "error": "ERROR"
    },
    "wave_detection": {
      "sample_duration": 3,
      "sample_rate": 5,
      "confidence_threshold": 0.7,
      "stand_down_time": 30
    }
  },
  "defaults": {
    // Same structure with default values
  }
}
```

### Servo Configuration

`resources/configs/servo_config.json`:

```json
{
  "m1_ch0": {
    "name": "Head Pan",
    "min": 993,
    "max": 2000,
    "speed": 0,
    "accel": 0,
    "home": 993
  },
  "m1_ch1": {
    "name": "Head Tilt",
    "min": 1000,
    "max": 1900,
    "speed": 20,
    "accel": 10,
    "home": 1302
  }
}
```

### Controller Configuration

`resources/configs/controller_config.json`:

```json
{
  "left_stick_x": {
    "type": "track_control",
    "group": "Drive System",
    "tracks": {
      "left": {"maestro": "Maestro 2 / Ch 0", "invert": false},
      "right": {"maestro": "Maestro 2 / Ch 1", "invert": true}
    }
  },
  "button_a": {
    "type": "scene",
    "emotion": "Happy"
  }
}
```

## Core Components

### Logger (`core/logger.py`)

Centralized logging system with per-module configuration and runtime reconfiguration.

#### Key Features
- Module-specific log levels
- Configurable output formatting
- Runtime level adjustment
- Thread-safe operation

#### Usage Example
```python
from core.logger import get_logger

logger = get_logger("my_module")
logger.info("Operation completed successfully")
logger.debug("Detailed debugging information")
logger.error("An error occurred", exc_info=True)
```

### Configuration Manager (`core/config_manager.py`)

Singleton configuration manager with file monitoring, LRU caching, and validation.

#### Key Features
- Automatic file change detection with mtime checking
- LRU caching for performance
- Type-safe configuration access
- Centralized configuration logic with defaults

#### Usage Example
```python
from core.config_manager import config_manager

# Get specific configurations
wave_config = config_manager.get_wave_config()
network_config = config_manager.get_network_config()
servo_names = config_manager.load_servo_names()

# Save configuration with validation
success = config_manager.save_config("path/to/file.json", data)
```

### WebSocket Manager (`core/websocket_manager.py`)

Handles WebSocket connections with automatic reconnection, exponential backoff, and structured command interface.

#### Key Features
- Automatic reconnection with configurable retry limits
- Connection state management
- Safe message sending with validation
- Structured command interface

#### Usage Example
```python
from core.websocket_manager import WebSocketManager

# Create connection
ws = WebSocketManager("ws://localhost:8766")

# Send structured command
success = ws.send_command("servo", channel="m1_ch0", pos=1500)

# Check connection status
if ws.is_connected():
    print("Connected to backend")
```

### Utilities (`core/utils.py`)

Common utilities including error handling, memory management, and MediaPipe integration.

#### Error Boundary Decorator
```python
@error_boundary
def risky_function():
    # Function that might throw exceptions
    pass
```

#### MediaPipe Manager
```python
from core.utils import mediapipe_manager

if mediapipe_manager.initialize():
    # Use MediaPipe functionality
    results = mediapipe_manager.pose.process(frame)
```

## UI Components

### Base Screen (`widgets/base_screen.py`)

Abstract base class providing common functionality, WebSocket communication helpers, and dynamic header with network monitoring.

#### DynamicHeader Features
- Battery voltage display with color coding
- WiFi signal strength with visual bars and ping-based coloring
- Current screen name display
- Network monitoring integration

#### WiFiSignalWidget
Custom widget displaying signal bars with:
- 5-bar signal strength indicator
- Ping-based color coding (green/yellow/orange/red)
- Timeout flash animation
- Real-time percentage display

### Home Screen (`widgets/home_screen.py`)

Main dashboard with emotion controls, mode selection, and WALL-E imagery.

#### Features
- Scrollable emotion button grid from configuration
- Mode controls (Idle/Demo modes) with toggle states
- Configurable emoji-based scene triggers
- Real-time scene command transmission

### Camera Screen (`widgets/camera_screen.py`)

Live camera feed with pose tracking, camera controls, and unified control panel.

#### Components
- **Live Video Display**: MJPEG stream rendering with error handling
- **Camera Controls**: ESP32 settings (resolution, quality, brightness, contrast, saturation, mirroring)
- **Stream Control**: Start/stop streaming with visual state indicators
- **Wave Detection**: Configurable gesture recognition with confidence thresholds

#### Wave Detection Features
- Sample collection over configurable time windows
- Confidence threshold filtering with buffer analysis
- Stand-down period between detections
- Visual feedback and status updates

### Health Screen (`widgets/health_screen.py`)

System monitoring with telemetry graphs, network testing, and component status.

#### Features
- **Battery Monitoring**: Real-time voltage graphing with alarm thresholds
- **Current Monitoring**: Dual current sensor displays with separate Y-axis
- **Network Quality**: WiFi monitoring and bandwidth testing
- **System Stats**: CPU, memory, temperature monitoring
- **Component Status**: Maestro, audio system connection status

#### Graph Configuration
- Battery voltage range: 0-20V optimized for 4S LiPo
- Current range: 0-70A for motor controllers
- Time-based X-axis with configurable windowing
- Color-coded status displays with threshold warnings

### Servo Screen (`widgets/servo_screen.py`)

Advanced servo control interface with dual-Maestro support and real-time position feedback.

#### Features
- **Dual-Maestro Support**: Switch between Maestro 1 and 2 with independent configurations
- **Real-time Control**: Live position sliders with conditional updates
- **Home Positions**: Diamond indicators on sliders showing home positions
- **Sweep Testing**: Automated min/max position sweeps with speed control
- **Live Updates**: Toggle-able real-time position feedback
- **Configuration Management**: Per-channel settings (min/max/speed/acceleration)

#### Advanced Features
- Custom `HomePositionSlider` with diamond position indicators
- `MinMaxSweep` class for automated testing with position validation
- Thread-safe position updates via Qt signals
- Automatic servo configuration loading and validation

### Controller Screen (`widgets/controller_screen.py`)

Advanced Steam Deck controller configuration with calibration and differential steering.

#### Features
- **Controller Calibration**: Real-time input sampling with min/max/center detection
- **Mapping Configuration**: Visual mapping of controls to servos/tracks/scenes
- **Differential Steering**: Tank-style track control with configurable parameters
- **Live Position Display**: Real-time controller input visualization
- **Advanced Mapping Types**: Servo control, scene triggers, track control, joystick axes

#### Calibration Process
- 100ms backend polling during calibration
- Min/max/center value capture with validation
- Visual progress indication and data validation
- Automatic calibration file generation and backend synchronization

### Settings Screen (`widgets/settings_screen.py`)

Configuration interface with scrollable layout and grouped settings sections.

#### Sections
- **Network Configuration**: Camera URLs, WebSocket endpoints
- **Logging Configuration**: Global and per-module debug levels
- **Wave Detection**: Sample duration, confidence thresholds, stand-down periods

#### Features
- Compact scrollable layout with grouped sections
- Real-time configuration validation
- WebSocket connection testing
- Reset to defaults functionality with confirmation dialogs

### Scene Screen (`widgets/scene_screen.py`)

Scene management interface for emotion configuration and audio mapping.

#### Features
- Import scenes from backend with WebSocket communication
- Category assignment for scene organization
- Scene testing with real-time playback
- Configuration export to emotion buttons
- Integration with home screen emotion grid

## Background Processing

### Image Processing Thread (`threads/image_processor.py`)

Handles camera stream processing and pose detection in dedicated thread.

#### Features
- **MJPEG Stream Processing**: Frame parsing with reconnection logic
- **Pose Detection**: MediaPipe integration for gesture recognition
- **Performance Optimization**: Frame rate limiting and memory management
- **Error Recovery**: Automatic stream reconnection with exponential backoff

#### Thread Communication
- Qt signals for thread-safe UI updates
- Frame processing results with pose data
- Statistics and status information
- Proper thread lifecycle management

### Network Monitor Thread (`threads/network_monitor.py`)

Background WiFi signal monitoring and network quality assessment.

#### Features
- **WiFi Signal Detection**: Multiple detection methods (iwconfig, nmcli, /proc/net/wireless)
- **Ping Quality Assessment**: Connection quality based on ping latency
- **Bandwidth Testing**: Download speed testing with configurable file sizes
- **Thread-safe Updates**: Qt signals for UI synchronization

## API Reference

### WebSocket Message Protocol

#### Outgoing Messages
```python
# Servo control
{"type": "servo", "channel": "m1_ch0", "pos": 1500}
{"type": "servo_speed", "channel": "m1_ch0", "speed": 50}

# Scene triggers
{"type": "scene", "emotion": "happy"}

# Controller calibration
{"type": "start_controller_calibration"}
{"type": "controller_calibration_update", "calibration": {...}}

# Status requests
{"type": "get_maestro_info", "maestro": 1}
{"type": "get_all_servo_positions", "maestro": 1}
```

#### Incoming Messages
```python
# Telemetry data
{
  "type": "telemetry",
  "battery_voltage": 14.2,
  "current": 5.3,
  "cpu": 45,
  "memory": 67,
  "maestro1": {"connected": true, "channels": 12},
  "maestro2": {"connected": false}
}

# Servo positions
{"type": "servo_position", "channel": "m1_ch0", "position": 1500}
{"type": "all_servo_positions", "maestro": 1, "positions": {...}}

# Controller input
{"type": "controller_input", "control": "left_stick_x", "value": 0.75}
```

## Development Guide

### Adding New Screens

1. Create new file in `widgets/` directory inheriting from `BaseScreen`
2. Implement `_setup_screen()` method
3. Add to `widgets/__init__.py` exports
4. Register in `core/application.py`

Example:
```python
from widgets.base_screen import BaseScreen

class NewScreen(BaseScreen):
    def _setup_screen(self):
        # Setup UI components
        layout = QVBoxLayout()
        self.setLayout(layout)
    
    def cleanup(self):
        # Cleanup resources
        pass
```

### Configuration Management

When adding new configuration options:

1. Update appropriate JSON configuration file
2. Add getter method to `ConfigManager` if needed
3. Update settings screen UI
4. Provide sensible defaults
5. Add validation logic

### Error Handling Best Practices

1. Use `@error_boundary` decorator for UI methods
2. Log errors with full context using module-specific loggers
3. Provide user-friendly error messages
4. Implement graceful degradation
5. Test error conditions thoroughly

## Troubleshooting

### Common Issues

#### Camera Not Working
- **Symptoms**: Black screen, "OpenCV not available" message
- **Solutions**: 
  - Install OpenCV: `pip install opencv-python`
  - Check camera URLs in settings
  - Verify network connectivity to camera proxy
  - Check ESP32 camera power and WiFi connection

#### WebSocket Connection Failed
- **Symptoms**: "WebSocket not connected" messages, no backend communication
- **Solutions**:
  - Verify backend is running on specified port
  - Check WebSocket URL format (ws:// prefix)
  - Examine firewall/network configuration
  - Review WebSocket manager logs for detailed errors

#### Servo Control Not Responding
- **Symptoms**: Position sliders don't move servos, timeout errors
- **Solutions**:
  - Check Maestro USB connections and power
  - Verify servo power supply voltage
  - Test with Pololu Maestro Control Center
  - Check servo configuration limits and channel assignments

#### Network Monitoring Issues
- **Symptoms**: WiFi shows "No signal" or constant timeouts
- **Solutions**:
  - Verify Pi IP address in configuration
  - Check network connectivity to Raspberry Pi
  - Test ping manually to verify network path
  - Review network interface configuration

### Debug Logging

Enable detailed logging for troubleshooting:

```json
{
  "debug_level": "DEBUG",
  "module_debug": {
    "camera": "DEBUG",
    "servo": "DEBUG", 
    "websocket": "DEBUG",
    "network": "DEBUG"
  }
}
```

### Performance Monitoring

Monitor these metrics for performance issues:

- Memory usage growth over time
- CPU usage during camera processing
- WebSocket message queuing and latency
- Configuration file access patterns
- Thread communication overhead

## To-Do List

### High Priority

- [ ] **Battery Management System Integration**
  - Add low voltage cutoff automation with graceful shutdown
  - Create battery health tracking and capacity estimation

- [ ] **Audio System Integration**
  - Add audio synchronization with emotion scenes
  - Create audio feedback for system status and alerts

### Medium Priority

- [ ] **Enhanced Camera System**
  - Implement object tracking beyond person detection


- [ ] **Advanced Controller Features**
  - Add support for additional controller types (Xbox, PlayStation)
  - Implement haptic feedback integration
  - Create custom control schemes for different operational modes
  - Add controller battery monitoring and low battery alerts

- [ ] **Telemetry and Monitoring**
  - Create alerting system for critical thresholds

### Low Priority

- [ ] **User Experience Improvements**
  - Add theme support with light/dark mode switching
  - Implement user profiles with different configurations
  - Create guided setup wizard for initial configuration
  - Add keyboard shortcuts for common operations

- [ ] **Documentation and Testing**
  - Add integration tests for WebSocket communication
  - Create user manual with detailed operation procedures
  - Add performance benchmarking and optimization guides

### Future Considerations

- [ ] **AI and Machine Learning**
  - Add gesture recognition beyond simple wave detection
  - Implement voice recognition and natural language processing
  - Create behavioral learning and adaptation systems


### Technical Debt and Refactoring

- [ ] **Code Quality Improvements**
  - Refactor large methods into smaller, focused functions
  - Implement comprehensive type hinting throughout codebase
  - Add dataclass usage for configuration structures
  - Create abstract interfaces for better testability

- [ ] **Performance Optimizations**
  - Optimize memory usage in long-running threads
  - Implement connection pooling for HTTP requests
  - Add caching layers for frequently accessed data
  - Optimize Qt signal/slot connections for better performance

- [ ] **Architecture Enhancements**
  - Implement proper dependency injection container
  - Add event bus for decoupled component communication
  - Create state machine for system operational modes
  - Add configuration validation with schema definitions

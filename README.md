# Droid Deck

A comprehensive PyQt6-based robot control interface designed for droid robots, featuring real-time telemetry, servo control, camera feeds, gesture recognition, and Steam Deck controller integration.

## 🚀 Features

### Core Functionality
- **Live Camera Feed**: MJPEG stream processing with MediaPipe pose detection and gesture recognition
- **Advanced Servo Control**: Dual-Maestro servo controller support with real-time position feedback
- **Health Monitoring**: System telemetry with battery voltage, current monitoring, and performance graphs
- **Controller Integration**: Steam Deck gamepad mapping with calibration and differential steering
- **Scene Management**: Emotion-based scene triggering with audio playback integration
- **Network Monitoring**: WiFi signal strength visualization and connection quality assessment

### User Interface
- **Modular Screen Architecture**: Clean separation between different control interfaces
- **Theme System**: Customizable theming with icon and background support
- **Dynamic Header**: Real-time status display with network quality and battery indicators
- **Responsive Design**: Optimized for various screen sizes and orientations

### Technical Highlights
- **WebSocket Communication**: Real-time bidirectional communication with automatic reconnection
- **Thread-Safe Processing**: Background image processing and network monitoring
- **Configuration Management**: JSON-based configuration with hot-reloading and validation
- **Error Handling**: Comprehensive error boundaries and graceful degradation
- **Memory Management**: Periodic cleanup and resource optimization

## 📋 Requirements

### Python Dependencies
```
Python 3.9+
PyQt6
pyqtgraph (for health monitoring graphs)
pygame (for audio playback)
requests (for network testing)
websockets (for WebSocket communication)
```

### Optional Dependencies
```
opencv-python (for camera processing)
mediapipe (for pose detection and gesture recognition)
```

### Hardware Requirements
- Network connectivity to robot backend
- Optional: USB gamepad/Steam Deck for controller input
- Optional: Camera for live feed processing

## 🛠️ Installation

### 1. Clone or Download
```bash
git clone <repository-url>
cd droid-deck
```

### 2. Install Dependencies
```bash
pip install PyQt6 pyqtgraph pygame requests websockets
```

### 3. Optional Dependencies
```bash
# For camera features
pip install opencv-python mediapipe

# For additional features
pip install numpy
```

### 4. Directory Structure Setup
```
droid-deck/
├── main.py
├── core/
│   ├── __init__.py
│   ├── application.py
│   ├── config_manager.py
│   ├── logger.py
│   ├── websocket_manager.py
│   ├── theme_manager.py
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
│   ├── scene_screen.py
│   └── splash_screen.py
├── threads/
│   ├── __init__.py
│   ├── image_processor.py
│   └── network_monitor.py
└── resources/
    ├── configs/
    ├── icons/
    ├── images/
    └── themes/
```

## ⚙️ Configuration

### Main Configuration File
Create `resources/configs/steamdeck_config.json`:

```json
{
  "current": {
    "esp32_cam_url": "http://10.1.1.203:81/stream",
    "camera_proxy_url": "http://10.1.1.230:8081/stream",
    "control_websocket_url": "ws://10.1.1.230:8766",
    "debug_level": "INFO",
    "module_debug": {
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
    },
    "wave_detection": {
      "sample_duration": 3,
      "sample_rate": 5,
      "confidence_threshold": 0.7,
      "stand_down_time": 30
    },
    "network_monitoring": {
      "update_interval": 5.0,
      "ping_samples": 3
    }
  },
  "defaults": {
    // Copy of current section for reset functionality
  }
}
```

### Servo Configuration
Create `resources/configs/servo_config.json`:

```json
{
  "m1_ch0": {
    "name": "Head Pan",
    "min": 993,
    "max": 2000,
    "speed": 20,
    "accel": 10,
    "home": 1500
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
Create `resources/configs/controller_config.json`:

```json
{
  "left_stick_x": {
    "type": "track_control",
    "group": "Drive System",
    "tracks": {
      "left": {"maestro": "Maestro 2 / Ch 0", "invert": false},
      "right": {"maestro": "Maestro 2 / Ch 1", "invert": true}
    },
    "calibration": {
      "min": -32768,
      "max": 32767,
      "center": 0,
      "deadzone": 0.1
    }
  },
  "button_a": {
    "type": "scene",
    "emotion": "Happy"
  }
}
```

## 🚀 Quick Start

1. **Configure Network Settings**
   - Update IP addresses in `steamdeck_config.json`
   - Ensure robot backend is running and accessible

2. **Launch Application**
   ```bash
   python main.py
   ```

3. **Initial Setup**
   - Navigate to Settings screen to verify connectivity
   - Test WebSocket connection to robot backend
   - Configure camera URLs if using video feed
   - Calibrate controller if using gamepad input

## 📱 User Interface Guide

### Home Screen
- **Scene Selection**: Grid of emotion-based scene buttons
- **Audio Feedback**: Sound effects for button interactions
- **Controller Navigation**: Navigate scenes using gamepad D-pad

### Camera Screen
- **Live Video Feed**: MJPEG stream from robot camera
- **Pose Detection**: Real-time human pose tracking with MediaPipe
- **Wave Detection**: Configurable gesture recognition for robot interaction
- **Performance Statistics**: Frame rate and processing metrics

### Health Screen
- **System Telemetry**: Real-time monitoring of robot systems
- **Battery Monitoring**: Voltage tracking with visual alerts
- **Current Draw**: Power consumption monitoring
- **Network Quality**: Connection status and ping latency
- **Performance Graphs**: Historical data visualization with pyqtgraph

### Servo Screen
- **Dual-Maestro Support**: Switch between multiple servo controllers
- **Real-time Control**: Interactive sliders with live position feedback
- **Home Position Indicators**: Visual markers showing servo home positions
- **Sweep Testing**: Automated min/max position testing
- **Speed & Acceleration**: Per-servo configuration controls

### Controller Screen
- **Live Input Display**: Real-time gamepad input visualization
- **Calibration Wizard**: Step-by-step controller calibration process
- **Mapping Configuration**: Assign controls to servos, tracks, or scenes
- **Differential Steering**: Tank-style drive control configuration
- **System Controls**: Emergency shutdown and restart commands

### Settings Screen
- **Network Configuration**: Camera URLs and WebSocket endpoints
- **Logging Configuration**: Global and per-module debug levels
- **Wave Detection**: Gesture recognition sensitivity and timing
- **Connectivity Testing**: Built-in network diagnostics

### Scene Screen
- **Scene Management**: Import and organize scenes from robot backend
- **Category Assignment**: Group scenes by emotion or type
- **Audio Integration**: Scene playback with sound effect synchronization
- **Testing Interface**: Preview scenes before deployment

## 🔧 Development Guide

### Architecture Overview

The application follows a modular architecture with clear separation of concerns:

- **Core Services**: Configuration, logging, WebSocket communication, utilities
- **UI Widgets**: Screen-specific interfaces inheriting from BaseScreen
- **Background Processing**: Threaded image processing and network monitoring
- **Theme System**: Centralized styling and resource management

### Adding New Screens

1. Create new screen class inheriting from `BaseScreen`:
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

2. Register screen in `core/application.py`:
```python
from widgets.new_screen import NewScreen

# In DroidDeckApplication.__init__
self.new_screen = NewScreen(websocket=self.websocket)
self.stack.addWidget(self.new_screen)
```

3. Add navigation button in `_setup_navigation()` method

### WebSocket Message Protocol

#### Outgoing Messages
```python
# Servo control
{"type": "servo", "channel": "m1_ch0", "pos": 1500}

# Scene triggers
{"type": "scene", "emotion": "happy"}

# System commands
{"type": "pi_control", "action": "restart"}
```

#### Incoming Messages
```python
# Telemetry data
{
  "type": "telemetry",
  "battery_voltage": 14.2,
  "current": 5.3,
  "cpu_usage": 45,
  "memory_usage": 67
}

# Servo position feedback
{"type": "servo_position", "channel": "m1_ch0", "position": 1500}
```

### Error Handling

Use the error boundary decorator for robust error handling:
```python
from core.utils import error_boundary

@error_boundary
def risky_function():
    # Function that might throw exceptions
    pass
```

### Logging

Use module-specific loggers for debugging:
```python
from core.logger import get_logger

logger = get_logger("module_name")
logger.info("Operation completed")
logger.debug("Detailed debug info")
logger.error("Error occurred", exc_info=True)
```

## 🐛 Troubleshooting

### Common Issues

**WebSocket Connection Failed**
- Verify robot backend is running
- Check IP address and port in configuration
- Ensure network connectivity between devices

**Camera Feed Not Loading**
- Verify camera URLs are accessible
- Check if ESP32/camera is powered and connected
- Test URLs in web browser first

**Controller Not Responding**
- Ensure controller is paired and connected
- Run controller calibration wizard
- Check USB/Bluetooth connection status

**Audio Not Playing**
- Verify pygame is installed
- Check audio file paths in scene configuration
- Ensure system audio is enabled

### Debug Mode

Enable detailed logging by updating `steamdeck_config.json`:
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

### Performance Optimization

- **Memory Usage**: Monitor memory consumption in Health screen
- **Frame Rate**: Adjust camera processing rate if needed
- **Network**: Use local proxy for camera streams to reduce bandwidth
- **Threading**: Ensure background threads are properly cleaned up

## 🔒 Safety Features

- **Emergency Stop**: Keyboard shortcut (Ctrl+Q) for immediate shutdown
- **Failsafe Mode**: Visual indicator and system protection
- **Connection Monitoring**: Automatic reconnection with exponential backoff
- **Error Isolation**: Component failures don't cascade to entire system
- **Battery Protection**: Low voltage alerts and monitoring

## 📄 License

This project is provided as-is for educational and hobbyist purposes. Please ensure compliance with any applicable hardware and software licenses when using with specific robot platforms.

## 🤖 About Droid Deck

This control system was designed to provide a comprehensive, user-friendly interface for controlling droid-style robots. The modular architecture ensures extensibility for future enhancements while maintaining reliability and performance for real-time robot control applications.

For additional support or contributions, please refer to the project documentation or contact the development team.
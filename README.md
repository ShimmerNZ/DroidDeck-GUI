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
- **Responsive Design**: Optimized for Steam Deck and various screen sizes

### Technical Highlights
- **WebSocket Communication**: Real-time bidirectional communication with automatic reconnection
- **Thread-Safe Processing**: Background image processing and network monitoring
- **Configuration Management**: JSON-based configuration with hot-reloading and validation
- **Error Handling**: Comprehensive error boundaries and graceful degradation
- **Memory Management**: Periodic cleanup and resource optimization

## 📋 Requirements

### Steam Deck (Recommended)
- SteamOS 3.0+
- Desktop Mode access
- Network connectivity to robot backend

### Alternative Linux Systems
- Python 3.10+
- X11 display server
- Network connectivity to robot backend

### Hardware Requirements
- Network connectivity to robot backend
- Optional: USB gamepad/Steam Deck for controller input
- Optional: Camera for live feed processing

## 🛠️ Installation

### Steam Deck Installation (Automated)

The easiest way to install Droid Deck on Steam Deck is using the automated installer:

#### Step 1: Switch to Desktop Mode

1. **Press the Steam Button** (bottom left of screen)
2. **Select "Power"** from the menu
3. **Choose "Switch to Desktop"**
4. **Wait for restart** (takes 30-60 seconds)

#### Step 2: Download the Repository

```bash
# Clone the repository
cd ~
git clone https://github.com/ShimmerNZ/DroidDeck-GUI.git
cd DroidDeck-GUI
```

#### Step 3: Run the Installer

```bash
# Make the installer executable
chmod +x DD_install.sh

# Run the automated installer (takes 10-15 minutes)
./DD_install.sh
```

The installer will:
- ✅ Install Distrobox (containerization system)
- ✅ Create an Ubuntu 22.04 container
- ✅ Install Python 3.10 and all dependencies
- ✅ Set up PyQt6 with full XCB/X11 support
- ✅ Configure audio libraries for Steam Deck
- ✅ Create project directory structure at `~/DroidDeck/`
- ✅ Generate launch scripts
- ✅ Create Steam integration helpers

#### Step 4: Copy Application Files

After installation, copy the application files to the DroidDeck directory:

```bash
# From the cloned repository
cp -r main.py widgets core threads resources ~/DroidDeck/
```

Or clone directly into the DroidDeck directory:

```bash
cd ~/DroidDeck
git clone https://github.com/ShimmerNZ/DroidDeck-GUI.git .
```

#### Step 5: Test the Installation

```bash
# Launch Droid Deck in Desktop Mode
~/DroidDeck/launch.sh
```

#### Step 6: Add to Steam (Gaming Mode)

For Gaming Mode access, run the helper script:

```bash
~/DroidDeck/complete_steam_setup.sh
```

Then manually add to Steam:
1. Open Steam in Desktop Mode
2. Click **Games** → **Add a Non-Steam Game to My Library**
3. Click **Browse** and navigate to: `~/DroidDeck/launch.sh`
4. Select **launch.sh** and click **Add Selected Programs**
5. Rename to "Droid Deck" in Steam library

### Manual Installation (Other Linux Systems)

For non-Steam Deck Linux systems:

#### 1. Install System Dependencies

```bash
# Debian/Ubuntu
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3-pip \
    libxcb1 libxcb-cursor0 libxcb-xfixes0 libxcb-shape0 \
    libxcb-randr0 libxcb-render0 libxcb-xinerama0 \
    libgl1-mesa-glx libglib2.0-0 libfontconfig1 \
    libxkbcommon-x11-0 libasound2 libpulse0
```

#### 2. Create Virtual Environment

```bash
# Clone repository
git clone https://github.com/ShimmerNZ/DroidDeck-GUI.git
cd DroidDeck-GUI

# Create virtual environment
python3.10 -m venv venv
source venv/bin/activate
```

#### 3. Install Python Dependencies

```bash
# Core dependencies
pip install --upgrade pip setuptools wheel
pip install PyQt6==6.7.1 PyQt6-Qt6==6.7.3
pip install pyqtgraph==0.13.7
pip install websockets==12.0
pip install requests==2.32.3
pip install numpy==1.24.4
pip install Pillow==10.4.0
pip install psutil==6.0.0
pip install watchdog==4.0.1
pip install jsonschema==4.19.2
pip install python-dateutil==2.8.2
pip install pygame==2.6.0

# Optional dependencies
pip install opencv-python==4.10.0.84
pip install mediapipe==0.10.14
```

#### 4. Run the Application

```bash
# From project directory with venv activated
python main.py
```

## 📁 Directory Structure

After installation, your directory structure will be:

```
~/DroidDeck/  (or your project directory)
├── main.py                    # Application entry point
├── core/                      # Core application services
│   ├── __init__.py
│   ├── application.py
│   ├── config_manager.py
│   ├── logger.py
│   ├── websocket_manager.py
│   ├── theme_manager.py
│   └── utils.py
├── widgets/                   # UI screen components
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
├── threads/                   # Background processing
│   ├── __init__.py
│   ├── image_processor.py
│   └── network_monitor.py
├── resources/                 # Configuration and assets
│   ├── configs/
│   │   ├── steamdeck_config.json
│   │   ├── servo_config.json
│   │   ├── controller_config.json
│   │   └── scenes_config.json
│   ├── icons/
│   ├── images/
│   └── themes/
├── launch.sh                  # Desktop launcher (Steam Deck)
└── complete_steam_setup.sh    # Steam integration helper
```

## ⚙️ Configuration

### Main Configuration File

Edit `resources/configs/steamdeck_config.json`:

```json
{
  "current": {
    "esp32_cam_url": "http://YOUR_ROBOT_IP:81/stream",
    "camera_proxy_url": "http://YOUR_ROBOT_IP:8081/stream",
    "control_websocket_url": "ws://YOUR_ROBOT_IP:8766",
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
  }
}
```

### Servo Configuration

Edit `resources/configs/servo_config.json`:

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

Edit `resources/configs/controller_config.json`:

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
   - Update IP addresses in `resources/configs/steamdeck_config.json`
   - Replace `YOUR_ROBOT_IP` with your robot's actual IP address
   - Ensure robot backend is running and accessible

2. **Launch Application**
   
   **Steam Deck (Desktop Mode):**
   ```bash
   ~/DroidDeck/launch.sh
   ```
   
   **Steam Deck (Gaming Mode):**
   - Launch "Droid Deck" from Steam library
   
   **Other Linux Systems:**
   ```bash
   source venv/bin/activate
   python main.py
   ```

3. **Initial Setup**
   - Navigate to Settings screen to verify connectivity
   - Test WebSocket connection to robot backend
   - Configure camera URLs if using video feed
   - Calibrate controller if using gamepad input

## 🎮 Steam Deck Controller Mapping

**Recommended Layout:**
- **Left Stick**: Robot movement (differential drive)
- **Right Stick**: Camera pan/tilt
- **A Button**: Happy emotion scene
- **B Button**: Sad emotion scene
- **X Button**: Curious emotion scene
- **Y Button**: Surprise emotion scene
- **D-Pad**: Navigate scene categories
- **Triggers**: Additional servo control

## 📱 User Interface Guide

### Home Screen
- Grid of emotion-based scene buttons
- Audio feedback for button interactions
- Controller navigation with gamepad D-pad

### Camera Screen
- Live MJPEG video stream from robot
- Real-time pose detection with MediaPipe
- Wave detection for gesture-based interaction
- Performance statistics and FPS monitoring

### Health Screen
- Real-time system telemetry monitoring
- Battery voltage tracking with alerts
- Current draw and power consumption
- Network quality and ping latency
- Historical data visualization

### Servo Screen
- Dual-Maestro controller support
- Interactive sliders with live feedback
- Home position indicators
- Automated sweep testing
- Per-servo speed and acceleration control

### Controller Screen
- Live gamepad input visualization
- Calibration wizard for controllers
- Mapping configuration interface
- Differential steering setup
- Emergency shutdown controls

### Settings Screen
- Network configuration management
- Logging level configuration
- Wave detection sensitivity
- Connectivity testing tools
- Theme selection

### Scene Screen
- Scene management and organization
- Category assignment system
- Audio file integration
- Scene testing interface
- Batch scene import from backend

## 🛠️ Troubleshooting

### Steam Deck Issues

**Installation Failed:**
```bash
# Check Distrobox installation
distrobox list

# Reinstall if needed
curl -s https://raw.githubusercontent.com/89luca89/distrobox/main/install | sh -s -- --prefix ~/.local
```

**Container Issues:**
```bash
# Check container status
distrobox enter droiddeckapp -- echo "Container OK"

# Rebuild container if needed
distrobox stop droiddeckapp
distrobox rm droiddeckapp -f
./DD_install.sh
```

**Audio Not Working:**
- Check Steam Deck audio output settings
- Verify PulseAudio is running: `pactl info`
- Test audio in Desktop Mode first

### General Issues

**WebSocket Connection Failed:**
- Verify robot backend is running
- Check IP address in `steamdeck_config.json`
- Test connectivity: `ping YOUR_ROBOT_IP`
- Ensure port 8766 is not blocked

**Camera Feed Not Loading:**
- Verify camera URLs in configuration
- Test URLs in web browser first
- Check ESP32/camera power and connection
- Try toggling camera start/stop in Settings

**Controller Not Responding:**
- Ensure controller is paired and connected
- Run controller calibration wizard
- Check USB/Bluetooth connection
- Test controller in Steam's controller configuration

**PyQt6 Import Errors:**
- Ensure X11 is available (Steam Deck Desktop Mode)
- Check environment variables:
  ```bash
  echo $DISPLAY  # Should show :0 or similar
  echo $QT_QPA_PLATFORM  # Should show xcb
  ```

### Performance Issues

**Low Frame Rate:**
- Reduce camera resolution in Settings
- Disable MediaPipe processing if not needed
- Lower network monitoring update interval

**High Memory Usage:**
- Monitor in Health screen
- Check for memory leaks in logs
- Restart application periodically

### Debug Mode

Enable detailed logging:

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

View logs:
```bash
# Steam Deck
tail -f ~/DroidDeck/logs/droid_deck.log

# Other systems
tail -f logs/droid_deck.log
```

## 🔒 Safety Features

- **Emergency Stop**: Keyboard shortcut (Ctrl+Q) for immediate shutdown
- **Failsafe Mode**: Visual indicator and system protection
- **Connection Monitoring**: Automatic reconnection with exponential backoff
- **Error Isolation**: Component failures don't cascade
- **Battery Protection**: Low voltage alerts and monitoring

## 📖 Documentation

For more detailed information:
- See `Droid Deck - Quick Install Guide.txt` for installation details
- Check configuration files in `resources/configs/` for examples
- Review logs in `~/DroidDeck/logs/` for troubleshooting

## 🤝 Contributing

This is a personal project for controlling droid-style robots. Feel free to fork and adapt for your own robots!

## 📄 License

This project is provided as-is for educational and hobbyist purposes.

## 🤖 About

Droid Deck is a comprehensive control system designed to provide a user-friendly, Steam Deck-optimized interface for controlling droid-style robots. The modular architecture ensures extensibility for future enhancements while maintaining reliability and performance for real-time robot control applications.

**Repository**: https://github.com/ShimmerNZ/DroidDeck-GUI

---

**Total Setup Time**: ~30 minutes  
**Difficulty**: ⭐⭐☆☆☆ (Easy-Medium)
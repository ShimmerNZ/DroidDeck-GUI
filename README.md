# Droid Deck

A PyQt6 control interface for droid animatronics, built to run full screen on a Steam Deck. It talks to the DroidDeck backend on the robot's Raspberry Pi ([Wall-e-Backend](https://github.com/ShimmerNZ/Wall-e-Backend)) and covers scene playback, servo and stepper setup, controller mapping, live camera with person tracking, health telemetry and over-the-air updates.

## 🚀 Features

### Core Functionality
- **Scene Playback**: Scene list grouped by category with audio and animation, sequential/random advance and an idle mode
- **Live Camera Feed**: MJPEG stream via the Pi's camera proxy, MediaPipe wave/gesture detection and multi-person tracking
- **Servo Control**: Dual Maestro (48 channels) with live sliders, D-pad nudge, home positions, sweep testing and NEMA23 stepper settings
- **Controller Mapping**: Steam Deck inputs mapped to servos, tracks, stepper, scenes, system actions and IMU tilt, with conflict checking
- **Health Monitoring**: Pack voltage and current, Pi temperature/memory/throttling, motion stats, Wi-Fi signal and ping, bandwidth test
- **Battery Alerts**: Low and critical pack voltage alerts with themed audio
- **Updates**: Install GUI and backend updates from GitHub straight from the Settings screen

### User Interface
- **Card-style screens** at the Deck's native 1280×800
- **Themes**: Wall-e and Star Wars, each with its own droid image, icons, background and sounds
- **Top bar**: Robot and Steam Deck battery, track and electronics current, active alerts and the Wi-Fi link (network name and ping) on every screen
- **Startup and shutdown screens** showing progress, GUI version and installed commit

### Technical Highlights
- **WebSocket link** to the backend on port 8766 with automatic reconnection
- **Background threads** for camera processing, controller input and network monitoring
- **JSON configuration** under `resources/configs/`, kept safe during updates
- **Steam Deck HID reader** (`core/deck.py`) for gyro/accelerometer access in Gaming Mode

## 📋 Requirements

### Steam Deck (Recommended)
- SteamOS 3.0+
- Desktop Mode access (for installation)
- Network connection to the robot's Raspberry Pi running the DroidDeck backend

### Other Linux Systems
- Python 3.10
- X11 display (the app runs as a fixed 1280×800 window)
- Network connection to the robot backend

## 🛠️ Installation

### Steam Deck Installation (Automated)

#### Step 1: Switch to Desktop Mode

1. **Press the Steam Button**
2. **Select "Power"**
3. **Choose "Switch to Desktop"**

#### Step 2: Download the Repository

```bash
cd ~
git clone https://github.com/ShimmerNZ/DroidDeck-GUI.git
cd DroidDeck-GUI
```

#### Step 3: Run the Installer

A sudo password must be set on the Deck (`passwd` in Konsole) before running the installer.

```bash
chmod +x DD_Install.sh
./DD_Install.sh
```

The installer will:
- ✅ Install a udev rule giving DroidDeck access to the Deck's built-in controller (IMU tilt)
- ✅ Install Distrobox and create an Ubuntu 22.04 container named `droiddeckapp`
- ✅ Create a Python 3.10 environment at `/home/deck/droiddeck_env` and install all dependencies
- ✅ Install the Qt/XCB and audio libraries PyQt6 and pygame need
- ✅ Create the project directory at `~/DroidDeck/`
- ✅ Generate `~/DroidDeck/launch.sh` and a desktop menu entry

#### Step 4: Copy Application Files

The installer creates the folders but does not copy the app. From the cloned repository:

```bash
cp -r main.py core widgets threads resources configs ~/DroidDeck/
```

#### Step 5: Set the Robot's Address

Edit `~/DroidDeck/resources/configs/steamdeck_config.json` and set the Pi's IP address (see Configuration below).

#### Step 6: Test the Installation

```bash
~/DroidDeck/launch.sh
```

#### Step 7: Add to Steam (Gaming Mode)

1. Open Steam in Desktop Mode
2. Click **Games** → **Add a Non-Steam Game to My Library**
3. Click **Browse** and select `~/DroidDeck/launch.sh`
4. Click **Add Selected Programs** and rename it to "DroidDeck"
5. Optional: set the artwork using the images in `Steam Icons/`

After this first install, updates are done from the Settings screen (see Updating below).

### Manual Installation (Other Linux Systems)

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
git clone https://github.com/ShimmerNZ/DroidDeck-GUI.git
cd DroidDeck-GUI
python3.10 -m venv venv
source venv/bin/activate
```

#### 3. Install Python Dependencies

```bash
pip install --upgrade pip setuptools wheel

# Required
pip install PyQt6==6.7.1 PyQt6-Qt6==6.7.3
pip install pyqtgraph==0.13.7       # Health screen graphs
pip install requests==2.32.3        # Updates, camera and bandwidth tests
pip install numpy==1.24.4
pip install pygame==2.6.0           # Sound effects and splash music

# Camera, gesture detection and person tracking
pip install opencv-python==4.10.0.84
pip install mediapipe==0.10.14

# Steam Deck IMU tilt control
pip install hid==1.0.6
pip install scipy
```

#### 4. Run the Application

```bash
python main.py
```

## 📁 Directory Structure

```
~/DroidDeck/
├── main.py                        # Application entry point
├── core/
│   ├── application.py             # Main window, startup/shutdown sequence, navigation
│   ├── battery.py                 # Robot battery thresholds from the backend
│   ├── config_manager.py          # JSON config loading and saving
│   ├── deck.py                    # Steam Deck HID reader with IMU support
│   ├── http_client.py             # Non-blocking HTTP requests
│   ├── logger.py                  # Logging setup and per-module levels
│   ├── theme_manager.py           # Wall-e / Star Wars themes
│   ├── utils.py                   # Shared helpers and battery thresholds
│   ├── version.py                 # GUI version and installed commit
│   └── websocket_manager.py       # Backend WebSocket link
├── widgets/
│   ├── base_screen.py             # Shared screen base
│   ├── home_screen.py
│   ├── camera_screen.py
│   ├── health_screen.py
│   ├── servo_screen.py
│   ├── controller_screen.py
│   ├── controller_calibration_screen.py
│   ├── controller_status_splash.py
│   ├── scene_screen.py
│   ├── settings_screen.py
│   ├── flow_dialog.py             # Themed dialogs: updates, network test, exit/restart
│   ├── bandwidth_test_splash.py
│   ├── voltage_alert_splash.py
│   ├── splash_screen.py           # Startup and shutdown screens
│   └── top_bar.py                 # Status bar across the top of every screen
├── threads/
│   ├── image_processor.py         # Camera stream, gestures and person detection
│   ├── person_tracker.py          # Stable IDs for tracked people
│   ├── network_monitor.py         # Wi-Fi signal and ping
│   └── steamdeck.py               # Controller input and mapping behaviours
├── resources/
│   ├── configs/                   # App configuration (kept during updates)
│   ├── icons/
│   ├── images/
│   ├── models/pose_landmarker_lite.task   # MediaPipe person detection model
│   └── theme/                     # Wall-e and Star Wars images, icons and audio
├── configs/
├── logs/                          # Created by launch.sh
├── version_info.json              # Written by the GUI updater
└── launch.sh                      # Created by the installer
```

## ⚙️ Configuration

All app settings live in `resources/configs/`. Most can be changed from the GUI, so editing the files by hand is only needed for first setup.

| File | Purpose | Edited from |
|---|---|---|
| `steamdeck_config.json` | Backend and camera URLs, logging levels, wave detection, volume | Settings screen |
| `servo_config.json` | Servo names, limits, home positions, NEMA stepper settings | Servo screen |
| `controller_config.json` | Controller input mappings | Controller screen |
| `controller_mappings.json` | Controller button/axis definitions | — |
| `scenes_config.json` | Scene list, categories and timing | Scene screen |
| `theme_config.json` | Current theme | Settings screen |
| `motion_config.json`, `movement_controls.json` | Motion groups and movement controls | — |

### Network Settings

`resources/configs/steamdeck_config.json`:

```json
{
  "current": {
    "esp32_cam_url": "http://ESP32_CAM_IP:81/stream",
    "camera_proxy_url": "http://YOUR_PI_IP:8081/stream",
    "control_websocket_url": "ws://YOUR_PI_IP:8766",
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
    "volume": 70
  },
  "defaults": { }
}
```

`defaults` holds the values used by **Reset to Defaults** in Settings.

### Servo Configuration

`resources/configs/servo_config.json` uses `m1_chN` / `m2_chN` keys for Maestro 1 and 2 (channels 0–23 each), plus a `nema` block for the stepper:

```json
{
  "nema": {
    "lead_screw_pitch": 8.0,
    "lead_screw_length": 20.0,
    "homing_speed": 800,
    "normal_speed": 4800,
    "acceleration": 5163,
    "min_position": 0.0,
    "max_position": 13.0
  },
  "m2_ch0": {
    "name": "L Arm Raise",
    "min": 800,
    "max": 2000,
    "home": 1400,
    "accel": 0
  }
}
```

### Controller Configuration

`resources/configs/controller_config.json` maps each input to a list of behaviours:

```json
{
  "left_stick_x": [
    { "behavior": "differential_tracks", "left_servo": "m2_ch12", "right_servo": "m2_ch13" }
  ],
  "left_trigger": [
    { "behavior": "multi_servo",
      "servos": [ { "channel": "m2_ch6", "invert": true },
                  { "channel": "m2_ch7", "invert": false } ] }
  ],
  "button_menu": [
    { "behavior": "system_control", "system_action": "exit_app" }
  ]
}
```

Available behaviours: `direct_servo`, `multi_servo`, `toggle_servo`, `joystick_pair`, `differential_tracks`, `scene_trigger`, `toggle_scenes`, `nema_stepper`, `system_control`, `imu_tilt`, `imu_toggle`.

## 🚀 Quick Start

1. **Start the robot** and make sure the backend service is running on the Pi
2. **Launch DroidDeck**
   - Gaming Mode: launch "DroidDeck" from the Steam library
   - Desktop Mode: `~/DroidDeck/launch.sh`
3. **Check the link**: the top bar shows the Wi-Fi network, ping and backend connection; Settings → **NETWORK TEST** checks the WebSocket, camera proxy and ESP32 camera
4. **Set up the robot**: configure channels on the Servo screen, mappings on the Controller screen and scenes on the Scene screen

## 🎮 Steam Deck Controls

Inputs are fully configurable on the Controller screen. Each mapping picks an input (sticks, triggers, face buttons, D-pad, back grips, trackpad clicks) and a behaviour:

| Behaviour | Use |
|---|---|
| Servo (direct) / Multi servo | Drive one or more servos from an axis or trigger, with optional invert |
| Toggle servo | Flip a servo between two positions with a button |
| Joystick pair | Drive two servos from one stick (e.g. head pan/tilt) |
| Tracks (differential) | Tank-style drive from one stick |
| Scene trigger / Toggle scenes | Play a scene, or toggle scene playback |
| NEMA stepper | Toggle positions, sweep or direct control of the stepper |
| System control | Navigate menus, exit or restart the app, restart or shut down the Pi |
| IMU tilt / IMU on/off | Drive servos by tilting the Deck |

The editor flags inputs already used by another mapping. **CALIBRATE** runs the controller calibration wizard and **STATUS** shows live input.

### IMU Tilt Control

DroidDeck can use the Steam Deck's built-in accelerometer to drive head servos: tilt the Deck to move the robot's head. It uses absolute gravity-relative tilt (not gyro rate integration), so the servo holds position when the Deck is held still.

**How it works:** A custom HID reader (`core/deck.py`) opens the Steam Deck controller directly and sends a firmware command that keeps raw accelerometer and gyroscope data in the HID report. This command is re-sent every 800ms to counter Steam periodically disabling it, so IMU tilt works in both Desktop Mode and Gaming Mode with the gyro layout setting left at None.

**Setup:**
1. Map an `imu_toggle` input and an `imu_tilt` behaviour on the Controller screen
2. Press the toggle input to enable IMU tilt
3. The current Deck angle is captured as the neutral position when enabled
4. Tilt the Deck to drive the mapped servos

**Dependencies:** `hid==1.0.6` and `scipy` (installed by the installer), plus the udev rule the installer adds.

**Note:** `hid==1.0.6` specifically is required. The `hidapi` package uses a different API (`hid.device` lowercase) and will not work.

## 📱 User Interface Guide

### Home Screen
- Droid stage with the theme's droid image
- Scene list by category: D-pad left/right changes category, up/down selects, select plays
- **NOW PLAYING** card with progress
- Sequential / Random advance and an **Idle** toggle

### Camera Screen
- Live view from the camera proxy with **Start Stream** / **Stop Stream**
- **Track Person**: MediaPipe multi-person detection with a focus box on the tracked person
- Wave and hands-up gesture detection
- ESP32 camera settings (resolution, quality, brightness, contrast, saturation, mirror/flip, clock) with reset to defaults

### Health Screen
- **Power**: Pack voltage, total and tracks current, electronics
- **Raspberry Pi**: Temperature, memory, under-voltage and throttling
- **Motion**: Maestro and Sabertooth status, active channels, commands per second, scene blend
- **Link**: Deck Wi-Fi signal, Pi ping, what each side sees, and a bandwidth test

### Servo Screen
- Channel list for both Maestros with editor for name, limits and home
- Position slider with **Live** mode, D-pad nudge, **SET FROM SLIDER**, **GO HOME** and **SWEEP TEST**
- **READ POSITIONS** from the Maestros
- NEMA23 stepper settings (lead screw, speeds, acceleration, travel limits) and test sweep

### Controller Screen
- Mapping list with friendly input and behaviour names
- Mapping editor with live conflict check
- **CALIBRATE** wizard and live **STATUS** view
- **SAVE ALL** sends mappings to the backend

### Scene Screen
- Scene list and editor: name, category, audio, animation and audio delay
- **TEST** plays the selected scene so the audio delay can be tuned against the animation
- **REFRESH** reloads scenes from the backend

### Settings Screen
- **Network**: Backend and camera URLs, network test
- **Wave detection**: Sample duration, rate, confidence and stand-down time
- **Logging**: Global and per-module log levels
- **Appearance**: Theme and system volume
- **UPDATE GUI** / **UPDATE SERVER** (see below)

## 🔄 Updating

From the Settings screen:

- **UPDATE GUI**: Choose a branch (default `main`); DroidDeck downloads it from GitHub, installs it on the Deck and offers to restart. Everything under `resources/configs/` is kept. The installed branch and commit are saved to `version_info.json` and shown on the startup screen.
- **UPDATE SERVER**: Downloads the latest [Wall-e-Backend](https://github.com/ShimmerNZ/Wall-e-Backend), backs up and installs it on the Pi, then restarts the backend service.

Because updates pull straight from GitHub, anything pushed to `main` reaches the robot the next time it updates. Test changes on another branch first.

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
./DD_Install.sh
```

**"Transport endpoint is not connected" when entering the container** (usually after the app was force-closed):
```bash
podman stop droiddeckapp
pkill fuse-overlayfs
```
If that doesn't clear it, reboot the Deck.

**`No module named pygame` (or PyQt6)**: The app was started outside the container. Use `launch.sh`, which runs it inside `droiddeckapp` with the right environment.

**Audio Not Working:**
- Check Steam Deck audio output settings
- Verify PulseAudio is running: `pactl info`
- Test audio in Desktop Mode first

### General Issues

**WebSocket Connection Failed:**
- Verify the backend service is running on the Pi
- Check `control_websocket_url` in `steamdeck_config.json`
- Run the network test in Settings
- Ensure port 8766 is not blocked

**Camera Feed Not Loading:**
- Verify camera URLs in Settings
- Run the network test (checks the camera proxy and ESP32 directly)
- Check ESP32 camera power and Wi-Fi

**Person Tracking Unavailable:**
- Check `resources/models/pose_landmarker_lite.task` is present
- Check the log for `MediaPipe not available` (mediapipe not installed)

**Controller Not Responding:**
- Check the mapping on the Controller screen and use **STATUS** to see live input
- Run the **CALIBRATE** wizard

**IMU Tilt Not Working:**
- Verify `hid==1.0.6` is installed (not `hidapi`): `pip show hid`
- Verify `scipy` is installed: `pip show scipy`
- Check the log after toggling IMU: `accel zero: x=0 y=0` means the firmware enable packet failed
- Ensure `core/deck.py` is present and the installer's udev rule exists (`/etc/udev/rules.d/99-steamdeck-hid.rules`)
- The gyro layout setting in Steam can be left at None

**PyQt6 Display Errors:**
- `launch.sh` sets `QT_QPA_PLATFORM=xcb` and `DISPLAY=:0`; check these if launching another way

### Debug Logging

Set log levels in Settings → **Logging**, or in `steamdeck_config.json`:

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
# Steam Deck (current and previous session)
tail -f ~/DroidDeck/logs/droiddeck.log
less ~/DroidDeck/logs/droiddeck.prev.log
```

On other systems, logs are printed to the terminal.

## 🔒 Safety Features

- **Failsafe button** on every screen: stops all motion on the robot; state is kept in sync with the backend
- **Failsafe release is never queued**: if the link is down, releasing failsafe is dropped rather than sent later
- **Connection monitoring**: Automatic reconnection with backoff
- **Battery alerts**: Low (below 14.0 V) and critical (below 13.2 V) pack voltage alerts, averaged over 10 seconds so track current sag doesn't trigger false alarms
- **Confirmed exit/restart**: Exit and restart from the controller ask for confirmation
- **Clean shutdown**: Configs saved and connections closed before exit
- **Ctrl+Q** quits the app (keyboard)

## 🤝 Contributing

This is a personal project for controlling droid-style animatronics. Feel free to fork and adapt it for your own robots!

## 📄 License

MIT License. See `LICENSE`.

## 🤖 About

DroidDeck gives a Steam Deck-optimised, convention-ready interface for controlling a droid animatronic, with the robot-side logic in [Wall-e-Backend](https://github.com/ShimmerNZ/Wall-e-Backend).

**Repository**: https://github.com/ShimmerNZ/DroidDeck-GUI
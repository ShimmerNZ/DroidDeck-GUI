# DroidDeck

A PyQt6-based robot control interface for droid robots, featuring real-time telemetry, servo control, camera feeds, gesture recognition, and Steam Deck controller integration.

## Features

- **Live Camera Feed** — MJPEG stream with MediaPipe pose detection and wave gesture recognition
- **Servo Control** — Dual Maestro controller support with real-time position feedback
- **Health Monitoring** — Battery voltage, current draw, and performance graphs
- **Controller Integration** — Steam Deck HID input with IMU tilt, differential steering, and fully configurable button mapping
- **Scene Management** — Emotion-based scene triggering with audio playback
- **Network Monitoring** — WiFi signal strength and connection quality

---

## Requirements

- Steam Deck running SteamOS 3.0+ in Desktop Mode
- Network connection to the robot backend (Raspberry Pi)
- Robot backend running at a known IP address

---

## Installation

### Step 1 — Set your sudo password

After a factory reset the `deck` user has no password. Open **Konsole** and run:

```bash
passwd
```

Set any password. You only need to do this once.

### Step 2 — Switch to Desktop Mode

Steam button → Power → Switch to Desktop

### Step 3 — Clone the repository

```bash
git clone https://github.com/ShimmerNZ/DroidDeck-GUI.git ~/DroidDeck
cd ~/DroidDeck
```

### Step 4 — Run the installer

```bash
chmod +x DD_Install.sh
./DD_Install.sh
```

The installer handles everything automatically (~10 minutes):

- Installs Distrobox and creates an Ubuntu 22.04 container
- Installs Python 3.10, PyQt6, and all dependencies
- Installs `iw` for WiFi signal monitoring
- Installs `bitsteam` for Steam Deck IMU/gyroscope support
- Installs the HID udev rule for direct controller access
- Creates the launch script with session logging
- Sets up the SMB file share for easy file transfer
- Creates a desktop entry for the application menu

### Step 5 — Configure your robot IP

Edit `~/DroidDeck/resources/configs/steamdeck_config.json` and set your Pi's IP address:

```json
{
  "current": {
    "esp32_cam_url": "http://10.1.1.x:81/stream",
    "camera_proxy_url": "http://10.1.1.x:8081/stream",
    "control_websocket_url": "ws://10.1.1.x:8766"
  }
}
```

### Step 6 — Test in Desktop Mode

```bash
~/DroidDeck/launch.sh
```

### Step 7 — Add to Steam for Gaming Mode

The installer cannot write Steam's binary shortcuts file automatically. Do this manually:

1. Open **Steam** in Desktop Mode
2. Click **Games → Add a Non-Steam Game to My Library**
3. Click **Browse** and navigate to `~/DroidDeck/launch.sh`
4. Select it, click **Add Selected Programs**
5. Rename the entry to **DroidDeck** in your library
6. Optionally set the icon to `~/DroidDeck/resources/droiddeck.png`

DroidDeck will now appear in Gaming Mode.

---

## SMB File Share

The installer sets up a Samba share so you can transfer files to and from the Steam Deck without SSH or a USB cable. The share runs automatically in the background.

**Connect (no password required):**

| Platform | Address |
|----------|---------|
| Mac | Finder → Go → Connect to Server → `smb://steamdeck/DroidDeck` |
| Windows | Explorer → `\\steamdeck\DroidDeck` |

If the hostname doesn't resolve, use the Steam Deck's IP address directly (`smb://10.1.1.x/DroidDeck`).

**Useful commands:**

```bash
# Check share status
systemctl --user status droiddeck-smb.service

# Restart if needed
systemctl --user restart droiddeck-smb.service
```

---

## Updating DroidDeck

### GUI (Steam Deck frontend)

Use the **Update** button in the Settings screen to pull the latest version from GitHub. Config files in `resources/configs/` are never overwritten by updates.

Alternatively, copy files directly via the SMB share.

### Backend (Raspberry Pi)

Use the **Update Server** button in the Settings screen. The backend service restarts automatically.

---

## Logs

Session logs are written to `~/DroidDeck/logs/droiddeck.log`. The previous session is kept as `droiddeck.prev.log`. Access them via the SMB share or:

```bash
tail -f ~/DroidDeck/logs/droiddeck.log
```

---

## Directory Structure

```
~/DroidDeck/
├── main.py
├── launch.sh
├── DD_Install.sh
├── core/
├── widgets/
├── threads/
├── resources/
│   └── configs/
│       ├── steamdeck_config.json
│       ├── servo_config.json
│       ├── controller_config.json
│       └── scenes_config.json
└── logs/
    ├── droiddeck.log
    └── droiddeck.prev.log
```

---

## Troubleshooting

**App won't start**
Check the log: `cat ~/DroidDeck/logs/droiddeck.log`

**WebSocket connection failed**
- Verify the backend is running on the Pi
- Check the IP in `steamdeck_config.json`
- Test: `ping 10.1.1.x`

**Camera feed not loading**
- Verify camera URLs in config
- Test the URL in a browser first

**Controller not responding**
- Ensure the HID udev rule was installed (the installer does this automatically)
- Check: `ls /etc/udev/rules.d/99-steamdeck-hid.rules`

**SMB share not connecting**
```bash
systemctl --user status droiddeck-smb.service
systemctl --user restart droiddeck-smb.service
```

**Container issues**
```bash
distrobox enter droiddeckapp -- echo "OK"

# Rebuild if needed (re-run installer)
distrobox stop droiddeckapp
distrobox rm droiddeckapp -f
./DD_Install.sh
```

---

## Repository

- GUI: https://github.com/ShimmerNZ/DroidDeck-GUI
- Backend: https://github.com/ShimmerNZ/Wall-e-Backend

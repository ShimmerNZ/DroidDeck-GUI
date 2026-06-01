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

- Steam Deck running SteamOS 3.0+
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
- Sets up SMB file share with guest read/write access
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

The installer sets up a Samba share so you can transfer files to and from the Steam Deck without SSH or a USB cable. The share starts automatically on boot with guest read/write access — no password required.

**Connect:**

| Platform | Address |
|----------|---------|
| Mac | Finder → `Cmd+K` → `smb://10.1.1.x/DroidDeck` |
| Windows | Explorer → `\\10.1.1.x\DroidDeck` |

The installer opens port 445 in firewalld automatically. If you reinstall SteamOS you will need to re-run the installer to restore this.

**Useful commands:**
```bash
# Check status
sudo systemctl status droiddeck-smb.service

# Restart if needed
sudo systemctl restart droiddeck-smb.service

# View SMB log
cat ~/.config/droiddeck-smb/smbd.log

# Manually re-open port 445 if needed
sudo firewall-cmd --permanent --add-port=445/tcp
sudo firewall-cmd --reload
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

Session logs are written to `~/DroidDeck/logs/droiddeck.log`. The previous session is kept as `droiddeck.prev.log`. Pull them off via the SMB share or:

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
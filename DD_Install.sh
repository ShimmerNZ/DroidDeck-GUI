#!/bin/bash
# DroidDeck Installer for Steam Deck
# Sets up the Ubuntu Distrobox container, Python environment,
# launch script with logging, and Steam integration.

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
print_step()    { echo -e "\n${GREEN}==>${NC} $1"; }

CONTAINER_NAME="droiddeckapp"
PROJECT_DIR="$HOME/DroidDeck"
DISTROBOX_IMAGE="ubuntu:22.04"

cleanup_on_failure() {
    print_warning "Cleaning up after installation failure..."
    distrobox stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
    distrobox rm "$CONTAINER_NAME" -f >/dev/null 2>&1 || true
    print_info "Cleanup complete"
}
trap cleanup_on_failure ERR

# ─────────────────────────────────────────────
check_sudo() {
    print_step "Checking sudo access..."
    if ! sudo -n true 2>/dev/null && ! sudo -v 2>/dev/null; then
        print_error "sudo is not available."
        print_info "Set a password first: passwd"
        exit 1
    fi
    # Extend sudo credential lifetime to cover the full install (~15 min)
    sudo sh -c 'echo "Defaults timestamp_timeout=60" > /etc/sudoers.d/droiddeck-install'
    print_success "sudo access confirmed"
}

# ─────────────────────────────────────────────
check_steam_deck() {
    print_step "Checking environment..."
    if [[ -f "/etc/os-release" ]] && grep -q "steam" /etc/os-release; then
        print_success "Steam Deck detected"
    else
        print_warning "Not running on Steam Deck - proceeding anyway"
    fi
    if [[ "$XDG_CURRENT_DESKTOP" == "KDE" ]]; then
        print_info "Desktop mode detected"
    else
        print_warning "Gaming mode detected - installer should be run in Desktop Mode"
    fi
}

# ─────────────────────────────────────────────
setup_distrobox() {
    print_step "Setting up Distrobox..."
    if command -v distrobox >/dev/null 2>&1; then
        print_success "Distrobox already installed ($(distrobox --version))"
        return 0
    fi
    print_info "Distrobox not found, installing via curl..."
    if curl -s https://raw.githubusercontent.com/89luca89/distrobox/main/install | sh -s -- --prefix ~/.local; then
        export PATH="$HOME/.local/bin:$PATH"
        print_success "Distrobox installed"
        return 0
    fi
    print_error "Failed to install Distrobox"
    print_info "Install manually: https://distrobox.privatedns.org/"
    exit 1
}

# ─────────────────────────────────────────────
create_container() {
    print_step "Creating Ubuntu 22.04 container '$CONTAINER_NAME'..."
    cd "$HOME"
    if distrobox list 2>/dev/null | grep -q "$CONTAINER_NAME"; then
        print_warning "Container already exists — removing..."
        timeout 30 distrobox stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
        timeout 30 distrobox rm "$CONTAINER_NAME" -f >/dev/null 2>&1 || {
            timeout 15 podman stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
            timeout 15 podman rm "$CONTAINER_NAME" -f >/dev/null 2>&1 || true
        }
        if distrobox list 2>/dev/null | grep -q "$CONTAINER_NAME"; then
            print_error "Could not remove existing container"
            print_info "Run: podman stop $CONTAINER_NAME && podman rm $CONTAINER_NAME -f"
            exit 1
        fi
        print_success "Existing container removed"
    fi
    if ! distrobox create --name "$CONTAINER_NAME" --image "$DISTROBOX_IMAGE" --yes; then
        print_error "Failed to create container"
        exit 1
    fi
    print_success "Container '$CONTAINER_NAME' created"
}

# ─────────────────────────────────────────────
setup_python_environment() {
    print_step "Setting up Python environment in container..."

    cat > /tmp/droiddecksetup.sh << 'EOF'
#!/bin/bash
set -e
echo "=== DroidDeck Container Setup ==="
cd /home/deck || cd ~

export DEBIAN_FRONTEND=noninteractive
sudo apt update

echo "Installing Python and build tools..."
sudo apt install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-dev \
    build-essential pkg-config curl wget git iw

echo "Installing audio libraries..."
sudo apt install -y --no-install-recommends \
    libpulse0 libpulse-dev pulseaudio-utils \
    libasound2 libasound2-dev libasound2-plugins

echo "Installing HID libraries..."
sudo apt install -y --no-install-recommends \
    libhidapi-hidraw0 libhidapi-libusb0 libhidapi-dev

echo "Installing X11 libraries..."
sudo apt install -y --no-install-recommends \
    xorg-dev \
    libx11-dev libx11-6 libxext-dev libxext6 \
    libxrender-dev libxrender1 libxrandr-dev libxrandr2 \
    libxinerama-dev libxinerama1 libxcursor-dev libxcursor1 \
    libxcomposite-dev libxcomposite1 libxdamage-dev libxdamage1 \
    libxfixes-dev libxfixes3 libxi-dev libxi6 \
    libxtst-dev libxtst6 libxss-dev libxss1

echo "Installing XCB libraries..."
sudo apt install -y --no-install-recommends \
    libxcb1-dev libxcb1 \
    libxcb-cursor0 libxcb-cursor-dev \
    libxcb-xfixes0 libxcb-xfixes0-dev \
    libxcb-shape0 libxcb-shape0-dev \
    libxcb-randr0 libxcb-randr0-dev \
    libxcb-glx0 libxcb-glx0-dev \
    libxcb-render0 libxcb-render0-dev \
    libxcb-render-util0 libxcb-render-util0-dev \
    libxcb-xinerama0 libxcb-xinerama0-dev \
    libxcb-xinput0 libxcb-xinput-dev \
    libxcb-xkb1 libxcb-xkb-dev \
    libxcb-icccm4 libxcb-icccm4-dev \
    libxcb-image0 libxcb-image0-dev \
    libxcb-keysyms1 libxcb-keysyms1-dev \
    libxcb-util1 libxcb-util0-dev

echo "Installing Qt6 libraries..."
sudo apt install -y --no-install-recommends \
    qt6-base-dev qt6-base-dev-tools \
    libqt6core6 libqt6gui6 libqt6widgets6 \
    libqt6opengl6 libqt6printsupport6

echo "Installing graphics libraries..."
sudo apt install -y --no-install-recommends \
    libgl1-mesa-dev libgl1-mesa-glx \
    libglu1-mesa-dev libegl1-mesa-dev \
    libgles2-mesa-dev libdrm2 libdrm-dev

echo "Installing GUI support libraries..."
sudo apt install -y --no-install-recommends \
    libglib2.0-0 libglib2.0-dev \
    libfontconfig1 libfontconfig1-dev \
    libfreetype6 libfreetype6-dev \
    libxkbcommon0 libxkbcommon-dev \
    libxkbcommon-x11-0 libxkbcommon-x11-dev

echo "Creating Python virtual environment..."
cd /home/deck
python3 -m venv droiddeck_env
source droiddeck_env/bin/activate

pip install --upgrade pip setuptools wheel

echo "Installing Python dependencies..."
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

echo "Installing optional packages..."
pip install pygame==2.6.0     || echo "pygame install failed (optional)"
pip install hid==1.0.6            || echo "hid install failed (optional)"
pip install scipy              || echo "scipy install failed (optional)"
pip install opencv-python==4.10.0.84 || echo "OpenCV install failed (optional)"
pip install mediapipe==0.10.14       || echo "MediaPipe install failed (optional)"

echo "Testing PyQt6..."
export DISPLAY=:0
export QT_QPA_PLATFORM=xcb
python -c "
import PyQt6.QtCore
print(f'PyQt6 {PyQt6.QtCore.qVersion()} OK')
import pyqtgraph, websockets, requests, numpy, psutil
print('Core dependencies OK')
try:
    import hid; hid.Device  # verify hid 1.0.6 API
    import scipy               # verify scipy for IMU quaternion maths
    print('hid 1.0.6 + scipy OK')
except Exception as e:
    print(f'hid not available: {e} (optional)')
try:
    import cv2; print(f'OpenCV {cv2.__version__} OK')
except ImportError:
    print('OpenCV not available (optional)')
try:
    import mediapipe; print(f'MediaPipe {mediapipe.__version__} OK')
except ImportError:
    print('MediaPipe not available (optional)')
"

echo "Container setup complete"
EOF

    chmod +x /tmp/droiddecksetup.sh
    print_info "Running setup in container (this takes ~10 minutes)..."
    distrobox enter "$CONTAINER_NAME" -- bash /tmp/droiddecksetup.sh
    rm /tmp/droiddecksetup.sh
    print_success "Python environment ready"
}

# ─────────────────────────────────────────────
install_hid_udev_rule() {
    print_step "Installing HID udev rule for Steam Deck controller access..."

    RULES_FILE="/etc/udev/rules.d/99-steamdeck-hid.rules"
    if [[ -f "$RULES_FILE" ]]; then
        print_info "udev rule already installed"
        return 0
    fi
    sudo tee "$RULES_FILE" > /dev/null << 'EOF'
# Steam Deck built-in controller HID access for DroidDeck
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="28de", ATTRS{idProduct}=="1205", MODE="0666"
EOF
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    print_success "HID udev rule installed"
}

# ─────────────────────────────────────────────
setup_project_structure() {
    print_step "Creating project directory structure..."
    # mkdir -p is safe on existing dirs — will not overwrite any files
    mkdir -p "$PROJECT_DIR"/{widgets,resources/configs,core,threads,logs}
    print_success "Directory structure ready at $PROJECT_DIR"
}

# ─────────────────────────────────────────────
create_launcher() {
    print_step "Creating launch script..."

    cat > "$PROJECT_DIR/launch.sh" << 'EOF'
#!/bin/bash
# DroidDeck Launcher for Steam Deck

# Redirect all output to log — rotate previous session
mkdir -p "$HOME/DroidDeck/logs"
[ -f "$HOME/DroidDeck/logs/droiddeck.log" ] && mv "$HOME/DroidDeck/logs/droiddeck.log" "$HOME/DroidDeck/logs/droiddeck.prev.log"
exec > "$HOME/DroidDeck/logs/droiddeck.log" 2>&1

if [[ ! -f "$HOME/DroidDeck/main.py" ]]; then
    echo "main.py not found in $HOME/DroidDeck/"
    exit 1
fi

export QT_QPA_PLATFORM=xcb
export QT_SCALE_FACTOR=1.0
export QT_AUTO_SCREEN_SCALE_FACTOR=0
export QT_ENABLE_HIGHDPI_SCALING=0
export QT_SCREEN_SCALE_FACTORS=1
export QT_FONT_DPI=64
export QT_SCALE_FACTOR_ROUNDING_POLICY=RoundPreferFloor
export QT_USE_PHYSICAL_DPI=0
export QT_DEVICE_PIXEL_RATIO=1
export DISPLAY=:0

echo "DroidDeck starting..."

distrobox enter droiddeckapp -- bash -c '
    cd /home/deck/DroidDeck
    source /home/deck/droiddeck_env/bin/activate

    export SDL_AUDIODRIVER=pulseaudio
    export PULSE_RUNTIME_PATH=/run/user/1000/pulse
    export PULSE_SERVER=unix:/run/user/1000/pulse/native

    cat > ~/.asoundrc << "ALSA_EOF"
defaults.pcm.card 1
defaults.pcm.device 1
defaults.ctl.card 1

pcm.!default {
    type pulse
    fallback "steamdeck"
}

ctl.!default {
    type pulse
    fallback "steamdeck"
}

pcm.steamdeck {
    type hw
    card 1
    device 1
}

ctl.steamdeck {
    type hw
    card 1
}
ALSA_EOF

    export QT_QPA_PLATFORM=xcb
    export QT_SCALE_FACTOR=1.0
    export QT_AUTO_SCREEN_SCALE_FACTOR=0
    export QT_ENABLE_HIGHDPI_SCALING=0
    export QT_SCREEN_SCALE_FACTORS=1
    export QT_FONT_DPI=64
    export QT_SCALE_FACTOR_ROUNDING_POLICY=RoundPreferFloor
    export QT_USE_PHYSICAL_DPI=0
    export QT_DEVICE_PIXEL_RATIO=1
    export DISPLAY=:0

    python -u main.py
'
EOF

    chmod +x "$PROJECT_DIR/launch.sh"
    print_success "launch.sh created"
}

# ─────────────────────────────────────────────
setup_steam_integration() {
    print_step "Setting up Steam integration..."

    # Desktop entry for application menu
    mkdir -p "$HOME/.local/share/applications"
    cat > "$HOME/.local/share/applications/droiddeckapp.desktop" << EOF
[Desktop Entry]
Name=DroidDeck
Comment=WALL-E Control System
Exec=$PROJECT_DIR/launch.sh
Icon=$PROJECT_DIR/resources/droiddeck.png
Terminal=false
Type=Application
Categories=Game;
StartupNotify=true
EOF
    print_success "Desktop entry created"

    # Attempt to write Steam shortcut directly
    STEAM_USERDATA="$HOME/.local/share/Steam/userdata"
    STEAM_USER_ID=$(find "$STEAM_USERDATA" -maxdepth 1 -type d -name "[0-9]*" 2>/dev/null | head -1 | xargs basename 2>/dev/null)

    if [[ -z "$STEAM_USER_ID" ]]; then
        print_warning "Steam user data not found — add DroidDeck to Steam manually (see README.md)"
        return 0
    fi

    SHORTCUTS_VDF="$STEAM_USERDATA/$STEAM_USER_ID/config/shortcuts.vdf"
    if [[ -f "$SHORTCUTS_VDF" ]]; then
        cp "$SHORTCUTS_VDF" "$SHORTCUTS_VDF.backup.$(date +%s)"
        print_info "Backed up existing shortcuts.vdf"
    fi

    # shortcuts.vdf is a binary format — we can't safely write it automatically.
    # Print clear manual instructions instead.
    print_info "Steam shortcut requires manual addition (binary VDF format):"
    print_info "  1. Open Steam in Desktop Mode"
    print_info "  2. Games > Add a Non-Steam Game to My Library"
    print_info "  3. Browse to: $PROJECT_DIR/launch.sh"
    print_info "  4. Name it 'DroidDeck' and click Add"
    print_success "Steam integration setup complete"
}

# ─────────────────────────────────────────────
test_installation() {
    print_step "Testing installation..."

    if ! distrobox enter "$CONTAINER_NAME" -- echo "Container OK" >/dev/null 2>&1; then
        print_error "Cannot access container"
        return 1
    fi
    print_success "Container accessible"

    if distrobox enter "$CONTAINER_NAME" -- bash -c "
        source /home/deck/droiddeck_env/bin/activate 2>/dev/null &&
        python -c 'import PyQt6, websockets, requests, numpy; print(\"Core dependencies OK\")'
    " 2>/dev/null; then
        print_success "Python dependencies OK"
    else
        print_warning "Dependency check failed — may still work at runtime"
    fi

    if distrobox enter "$CONTAINER_NAME" -- bash -c "
        source /home/deck/droiddeck_env/bin/activate 2>/dev/null &&
        python -c 'import hid; hid.Device; import scipy; print(\"IMU dependencies OK\")'
    " 2>/dev/null; then
        print_success "IMU dependencies OK (hid==1.0.6, scipy)"
    else
        print_warning "IMU dependencies check failed — IMU tilt control will not work"
    fi

    if [[ -f "$PROJECT_DIR/core/deck.py" ]]; then
        print_success "deck.py present in core/"
    else
        print_warning "core/deck.py not found — IMU tilt control will not work until added"
    fi

    if [[ -x "$PROJECT_DIR/launch.sh" ]]; then
        print_success "launch.sh present and executable"
    else
        print_error "launch.sh missing or not executable"
        return 1
    fi

    print_success "Installation tests passed"
}

# ─────────────────────────────────────────────
main() {
    echo ""
    print_step "DroidDeck Installer for Steam Deck"
    echo ""

    check_sudo
    check_steam_deck
    install_hid_udev_rule
    setup_distrobox
    create_container
    setup_python_environment
    setup_project_structure
    create_launcher
    setup_steam_integration
    test_installation

    trap - ERR

    # Remove the temporary sudo timeout extension
    sudo rm -f /etc/sudoers.d/droiddeck-install

    echo ""
    print_success "DroidDeck installation complete!"
    echo ""
    print_info "Project directory:  $PROJECT_DIR"
    print_info "Container:          $CONTAINER_NAME"
    print_info "Python environment: /home/deck/droiddeck_env (in container)"
    print_info "Logs:               $PROJECT_DIR/logs/droiddeck.log"
    echo ""
    print_info "Next steps:"
    print_info "  1. Configure your robot IP in resources/configs/steamdeck_config.json"
    print_info "  2. Ensure core/deck.py is present (required for IMU tilt control)"
    print_info "  3. Test: $PROJECT_DIR/launch.sh"
    print_info "  4. Add to Steam Gaming Mode (see README.md)"
    echo ""
}

main "$@"
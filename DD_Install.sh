#!/bin/bash
# Steam Deck DroidDeck Installer using Distrobox
# Designed for Steam Deck with persistent Ubuntu container

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_step() { echo -e "\n${GREEN}==>${NC} $1"; }

# Configuration
CONTAINER_NAME="droiddeckapp"
PROJECT_DIR="$HOME/DroidDeck"
DISTROBOX_IMAGE="ubuntu:22.04"

# Cleanup function for failed installs
cleanup_on_failure() {
    print_warning "Cleaning up after installation failure..."
    distrobox stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
    distrobox rm "$CONTAINER_NAME" -f >/dev/null 2>&1 || true
    rm -rf "$PROJECT_DIR" >/dev/null 2>&1 || true
    print_info "Cleanup completed"
}

# Set trap for cleanup
trap cleanup_on_failure ERR

print_step "🎮 Steam Deck DroidDeck Installer"
print_info "Creating persistent Ubuntu environment for DroidDeck"

# Check if we're on Steam Deck
check_steam_deck() {
    print_step "Checking Steam Deck environment..."
    
    if [[ -f "/etc/os-release" ]] && grep -q "steam" /etc/os-release; then
        print_success "Steam Deck detected"
    else
        print_warning "Not running on Steam Deck - proceeding anyway"
    fi
    
    # Check if we're in desktop mode
    if [[ "$XDG_CURRENT_DESKTOP" == "KDE" ]]; then
        print_info "Desktop mode detected"
    else
        print_info "Gaming mode detected"
    fi
}

# Install or check Distrobox
setup_distrobox() {
    print_step "Setting up Distrobox..."
    
    if command -v distrobox >/dev/null 2>&1; then
        print_success "Distrobox already installed"
        distrobox --version
        return 0
    fi
    
    print_info "Distrobox not found, attempting automatic installation..."
    
    # Try to install Distrobox
    if command -v flatpak >/dev/null 2>&1; then
        print_info "Installing Distrobox via Flatpak..."
        if flatpak install --user -y flathub io.github.89luca89.distrobox; then
            print_success "Distrobox installed via Flatpak"
            # Add flatpak distrobox to PATH for this session
            export PATH="$HOME/.local/share/flatpak/exports/bin:$PATH"
            alias distrobox='flatpak run io.github.89luca89.distrobox'
            return 0
        fi
    fi
    
    # Try curl installation
    print_info "Installing Distrobox via curl..."
    if curl -s https://raw.githubusercontent.com/89luca89/distrobox/main/install | sh -s -- --prefix ~/.local; then
        export PATH="$HOME/.local/bin:$PATH"
        print_success "Distrobox installed via curl"
        return 0
    fi
    
    print_error "Failed to install Distrobox automatically"
    print_info "Please install Distrobox manually:"
    print_info "  Flatpak: flatpak install --user flathub io.github.89luca89.distrobox"
    print_info "  Or visit: https://distrobox.privatedns.org/"
    exit 1
}

# Create and setup Ubuntu container
create_container() {
    print_step "Creating Ubuntu container '$CONTAINER_NAME'..."
    
    # Ensure we're in a stable directory to avoid getcwd errors
    cd "$HOME"
    
    # Check if container already exists
    if distrobox list 2>/dev/null | grep -q "$CONTAINER_NAME"; then
        print_warning "Container '$CONTAINER_NAME' already exists"
        print_info "Attempting to remove existing container..."
        
        # Try graceful removal with timeout
        timeout 30 distrobox stop "$CONTAINER_NAME" >/dev/null 2>&1 || {
            print_warning "Graceful stop timed out, force stopping..."
        }
        
        # Force removal with timeout
        timeout 30 distrobox rm "$CONTAINER_NAME" -f >/dev/null 2>&1 || {
            print_warning "Distrobox removal failed, trying podman directly..."
            
            # Try podman directly as fallback
            timeout 15 podman stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
            timeout 15 podman rm "$CONTAINER_NAME" -f >/dev/null 2>&1 || true
        }
        
        # Verify removal
        if distrobox list 2>/dev/null | grep -q "$CONTAINER_NAME"; then
            print_error "Failed to remove existing container"
            print_info "Manual cleanup required:"
            print_info "  1. Run: killall distrobox"
            print_info "  2. Run: podman stop $CONTAINER_NAME && podman rm $CONTAINER_NAME -f"
            print_info "  3. Re-run this installer"
            exit 1
        else
            print_success "Existing container removed"
        fi
    fi
    
    print_info "Creating new Ubuntu 22.04 container from stable directory..."
    if ! distrobox create --name "$CONTAINER_NAME" --image "$DISTROBOX_IMAGE" --yes; then
        print_error "Failed to create container"
        exit 1
    fi
    
    print_success "Container '$CONTAINER_NAME' created"
}

# Install Python and dependencies in container
setup_python_environment() {
    print_step "Setting up Python 3.10 environment in container..."
    
    print_info "Entering container and installing dependencies..."
    
    # Create comprehensive setup script
    cat > /tmp/droiddecksetup.sh << 'EOF'
#!/bin/bash
set -e

echo "=== DroidDeck Container Setup (Fresh Install) ==="

# Ensure we're in a stable directory
cd /home/deck || cd ~

# Check if we have sudo access
if ! sudo -n true 2>/dev/null; then
    echo "Setting up sudo access..."
fi

# Update system with proper permissions
echo "Updating package lists..."
export DEBIAN_FRONTEND=noninteractive
sudo apt update

# Install Python 3.10 and development tools
echo "Installing Python 3.10 and build tools..."
sudo apt install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-dev \
    build-essential pkg-config curl wget git

# Install audio libraries for Steam Deck
echo "Installing PulseAudio and ALSA libraries..."
sudo apt install -y --no-install-recommends \
    libpulse0 \
    libpulse-dev \
    pulseaudio-utils \
    libasound2 \
    libasound2-dev \
    libasound2-plugins

# Install comprehensive X11 and XCB libraries for PyQt6
echo "Installing comprehensive X11 and XCB libraries..."
sudo apt install -y --no-install-recommends \
    xorg-dev \
    libx11-dev libx11-6 \
    libxext-dev libxext6 \
    libxrender-dev libxrender1 \
    libxrandr-dev libxrandr2 \
    libxinerama-dev libxinerama1 \
    libxcursor-dev libxcursor1 \
    libxcomposite-dev libxcomposite1 \
    libxdamage-dev libxdamage1 \
    libxfixes-dev libxfixes3 \
    libxi-dev libxi6 \
    libxtst-dev libxtst6 \
    libxss-dev libxss1

# Install comprehensive XCB libraries
echo "Installing comprehensive XCB libraries..."
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

# Install Qt6 platform libraries
echo "Installing Qt6 platform libraries..."
sudo apt install -y --no-install-recommends \
    qt6-base-dev \
    qt6-base-dev-tools \
    libqt6core6 \
    libqt6gui6 \
    libqt6widgets6 \
    libqt6opengl6 \
    libqt6printsupport6

# Install OpenGL and graphics libraries
echo "Installing graphics libraries..."
sudo apt install -y --no-install-recommends \
    libgl1-mesa-dev libgl1-mesa-glx \
    libglu1-mesa-dev \
    libegl1-mesa-dev \
    libgles2-mesa-dev \
    libdrm2 libdrm-dev

# Install essential GUI support libraries
echo "Installing essential GUI libraries..."
sudo apt install -y --no-install-recommends \
    libglib2.0-0 libglib2.0-dev \
    libfontconfig1 libfontconfig1-dev \
    libfreetype6 libfreetype6-dev \
    libxkbcommon0 libxkbcommon-dev \
    libxkbcommon-x11-0 libxkbcommon-x11-dev

# Create Python virtual environment
echo "Creating Python virtual environment..."
cd /home/deck
python3 -m venv droiddeck_env
source droiddeck_env/bin/activate

# Upgrade pip
echo "Upgrading pip..."
python -m pip install --upgrade pip setuptools wheel

# Install DroidDeck dependencies
echo "Installing PyQt6..."
pip install PyQt6==6.7.1 PyQt6-Qt6==6.7.3

echo "Installing core application dependencies..."
pip install pyqtgraph==0.13.7
pip install websockets==12.0
pip install requests==2.32.3
pip install numpy==1.24.4
pip install Pillow==10.4.0
pip install psutil==6.0.0
pip install watchdog==4.0.1
pip install jsonschema==4.19.2
pip install python-dateutil==2.8.2

# Install optional packages
echo "Installing optional packages..."
pip install pygame==2.6.0 || echo "pygame install failed (optional)"
pip install opencv-python==4.10.0.84 || echo "OpenCV install failed (optional)"
pip install mediapipe==0.10.14 || echo "MediaPipe install failed (optional)"

# Comprehensive PyQt6 testing with XCB
echo "Testing PyQt6 installation with comprehensive XCB support..."
export DISPLAY=:0
export QT_QPA_PLATFORM=xcb
export QT_DEBUG_PLUGINS=0

python -c "
import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QLibraryInfo
import PyQt6.QtCore

print(f'✅ PyQt6 {PyQt6.QtCore.qVersion()} installed')

# Test QLibraryInfo path safely
try:
    plugins_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)
    print(f'✅ Qt Library Path: {plugins_path}')
    
    # List available Qt platform plugins
    if os.path.exists(plugins_path):
        platforms_path = os.path.join(plugins_path, 'platforms')
        if os.path.exists(platforms_path):
            available_plugins = os.listdir(platforms_path)
            print(f'✅ Available platform plugins: {available_plugins}')
            if 'libqxcb.so' in available_plugins:
                print('✅ XCB platform plugin found')
            else:
                print('⚠️  XCB platform plugin missing')
        else:
            print('⚠️  Platforms directory not found')
    else:
        print('⚠️  Plugins path not found')
except AttributeError as e:
    print(f'⚠️  Could not get Qt library path: {e}')
except Exception as e:
    print(f'⚠️  Plugin detection failed: {e}')

# Test QApplication creation
try:
    print('Testing QApplication creation...')
    app = QApplication(['test'])
    print(f'✅ QApplication created successfully')
    print(f'✅ Active platform: {app.platformName()}')
    app.quit()
    print('✅ XCB platform working correctly')
except Exception as e:
    print(f'❌ QApplication test failed: {e}')
    # Try to provide helpful debugging info
    print('Debug info:')
    print(f'  DISPLAY: {os.environ.get(\"DISPLAY\", \"not set\")}')
    print(f'  QT_QPA_PLATFORM: {os.environ.get(\"QT_QPA_PLATFORM\", \"not set\")}')
    # Don't raise here, continue with other tests

print('Testing other dependencies...')
try:
    import pyqtgraph, websockets, requests, numpy, psutil
    print('✅ All core dependencies working')
except ImportError as e:
    print(f'❌ Core dependency missing: {e}')

try:
    import cv2
    print(f'✅ OpenCV {cv2.__version__} available')
except ImportError:
    print('⚠️  OpenCV not available (optional)')

try:
    import mediapipe
    print(f'✅ MediaPipe {mediapipe.__version__} available')
except ImportError:
    print('⚠️  MediaPipe not available (optional)')

print('✅ Testing complete')
"

echo "🎉 Container setup complete!"
echo "Python environment: /home/deck/droiddeck_env"
echo "All GUI and audio libraries installed for Steam Deck compatibility"
EOF

    chmod +x /tmp/droiddecksetup.sh
    
    # Run setup in container
    print_info "Running setup script in container (this may take 5-10 minutes)..."
    distrobox enter "$CONTAINER_NAME" -- bash /tmp/droiddecksetup.sh
    
    # Cleanup temp script
    rm /tmp/droiddecksetup.sh
    
    print_success "Python 3.10 environment setup complete"
}

# Create project directory structure
setup_project_structure() {
    print_step "Creating project directory structure..."
    
    # Remove existing directory
    rm -rf "$PROJECT_DIR" >/dev/null 2>&1 || true
    
    # Create directory structure
    mkdir -p "$PROJECT_DIR"/{widgets,resources,core,threads}
    
    print_info "Created directories:"
    print_info "  📁 $PROJECT_DIR/widgets/"
    print_info "  📁 $PROJECT_DIR/resources/"
    print_info "  📁 $PROJECT_DIR/core/"
    print_info "  📁 $PROJECT_DIR/threads/"
    
    print_success "Project structure created"
}

# Create launch script
create_launcher() {
    print_step "Creating launch script..."
    
    cat > "$PROJECT_DIR/launch.sh" << 'EOF'
#!/bin/bash
# DroidDeck Launcher for Steam Deck - Fixed Audio

if [[ ! -f "$HOME/DroidDeck/main.py" ]]; then
    echo "❌ main.py not found in $HOME/DroidDeck/"
    exit 1
fi

# Steam Deck optimized display settings
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

echo "🤖 DroidDeck Launcher (Steam Deck Optimized)"
echo "📁 Project: $HOME/DroidDeck"

distrobox enter droiddeckapp -- bash -c '
    cd /home/deck/DroidDeck
    source /home/deck/droiddeck_env/bin/activate
    
    # Use PipeWire via PulseAudio compatibility
    export SDL_AUDIODRIVER=pulseaudio
    export PULSE_RUNTIME_PATH=/run/user/1000/pulse
    export PULSE_SERVER=unix:/run/user/1000/pulse/native
    
    # Set default ALSA device to Steam Deck speakers (card 1, device 1)
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
    
    echo "🔊 Audio configured for Steam Deck speakers (card 1, device 1)"
    
    # Set optimized display environment variables in container
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
    
    echo "🎮 Starting DroidDeck with SteamDeck audio configuration..."
    python main.py
'
EOF
    
    chmod +x "$PROJECT_DIR/launch.sh"
    
    print_success "Launch script created: $PROJECT_DIR/launch.sh"
}

# Create Steam shortcut automatically
create_steam_shortcut() {
    print_step "Adding DroidDeck to Steam..."
    
    # Create desktop file first
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
    
    print_success "Desktop file created"
    
    # Auto-add to Steam if possible
    STEAM_USERDATA="$HOME/.local/share/Steam/userdata"
    
    if [[ -d "$STEAM_USERDATA" ]]; then
        print_info "Steam installation detected, attempting to add DroidDeck..."
        
        # Find Steam user ID
        STEAM_USER_ID=$(find "$STEAM_USERDATA" -maxdepth 1 -type d -name "[0-9]*" | head -1 | xargs basename 2>/dev/null)
        
        if [[ -n "$STEAM_USER_ID" ]]; then
            print_info "Found Steam User ID: $STEAM_USER_ID"
            
            # Create Steam shortcut helper script for manual steps
            cat > "$PROJECT_DIR/complete_steam_setup.sh" << 'STEAM_EOF'
#!/bin/bash
# Complete Steam integration for DroidDeck

echo "🎮 Completing Steam Integration for DroidDeck"
echo ""
echo "DroidDeck has been added to your applications menu, but to use it in Gaming Mode:"
echo ""
echo "📋 Steps to complete Steam integration:"
echo "1. Open Steam in Desktop Mode"
echo "2. Click 'Games' → 'Add a Non-Steam Game to My Library'"
echo "3. Click 'Browse' and navigate to:"
echo "   $HOME/DroidDeck/launch.sh"
echo "4. Select launch.sh and click 'Open'"
echo "5. Change the name to 'DroidDeck' and click 'Add Selected Programs'"
echo "6. Right-click DroidDeck in your Steam library → 'Properties'"
echo "7. Optional: Set icon to: $HOME/DroidDeck/resources/droiddeck.png"
echo ""
echo "✅ After these steps, DroidDeck will be available in Gaming Mode!"
echo ""
echo "🎯 Quick test: Run this in Desktop Mode first:"
echo "   $HOME/DroidDeck/launch.sh"
STEAM_EOF
            
            chmod +x "$PROJECT_DIR/complete_steam_setup.sh"
            
            # Try to detect if Steam is running
            if pgrep -f "steam" >/dev/null; then
                print_warning "Steam is currently running"
                print_info "For best results, close Steam and run: $PROJECT_DIR/complete_steam_setup.sh"
            else
                print_info "Steam is not running - perfect for adding shortcuts"
                
                # Try automatic Steam integration using steamtinkerlaunch or similar tools
                SHORTCUTS_VDF="$STEAM_USERDATA/$STEAM_USER_ID/config/shortcuts.vdf"
                
                if [[ -f "$SHORTCUTS_VDF" ]]; then
                    print_info "Found Steam shortcuts file, creating backup..."
                    cp "$SHORTCUTS_VDF" "$SHORTCUTS_VDF.backup.$(date +%s)"
                    
                    # Note: We can't easily modify the binary VDF file automatically
                    # So we'll just provide the helper script
                    print_warning "Steam shortcuts require manual addition"
                fi
            fi
            
            print_success "Steam integration helper created: $PROJECT_DIR/complete_steam_setup.sh"
            
        else
            print_warning "Could not find Steam user ID"
            print_info "Steam integration will need to be done manually"
        fi
        
    else
        print_warning "Steam not found at $STEAM_USERDATA"
        print_info "Install Steam to enable Gaming Mode integration"
    fi
    
    print_success "Steam integration setup complete"
}

# Test installation comprehensively
test_installation() {
    print_step "Testing installation comprehensively..."
    
    # Test container access
    if ! distrobox enter "$CONTAINER_NAME" -- echo "Container accessible" >/dev/null 2>&1; then
        print_error "Cannot access container"
        return 1
    fi
    
    # Test Python environment
    print_info "Testing Python environment..."
    if distrobox enter "$CONTAINER_NAME" -- bash -c "
        cd /home/deck 2>/dev/null || cd ~
        if [[ -f droiddeck_env/bin/activate ]]; then
            source droiddeck_env/bin/activate && 
            python -c 'import PyQt6; print(\"PyQt6 OK\")' &&
            python -c 'import pyqtgraph; print(\"pyqtgraph OK\")' &&
            python -c 'import websockets, requests, numpy; print(\"Core libs OK\")'
        else
            echo 'Python environment not found'
            exit 1
        fi
    "; then
        print_success "Python environment test passed"
    else
        print_error "Python environment test failed"
        return 1
    fi
    
    # Test GUI capability with better error handling
    print_info "Testing GUI libraries and XCB platform..."
    GUI_TEST_RESULT=$(distrobox enter "$CONTAINER_NAME" -- bash -c "
        cd /home/deck 2>/dev/null || cd ~
        export DISPLAY=:0
        export QT_QPA_PLATFORM=xcb
        if [[ -f droiddeck_env/bin/activate ]]; then
            source droiddeck_env/bin/activate
            python -c '
import sys
try:
    from PyQt6.QtWidgets import QApplication
    print(\"Testing GUI setup...\")
    app = QApplication([\"test\"])
    print(\"✅ QApplication created successfully\")
    print(f\"✅ Platform: {app.platformName()}\")
    app.quit()
    print(\"✅ XCB platform working correctly\")
    sys.exit(0)
except Exception as e:
    print(f\"GUI test failed: {e}\")
    sys.exit(1)
'
        else
            echo 'Python environment not found'
            exit 1
        fi
    " 2>&1)
    
    if [[ $? -eq 0 ]]; then
        print_success "GUI libraries test passed"
    else
        print_warning "GUI libraries test failed - may work when X11 is available"
        print_info "GUI test output: $GUI_TEST_RESULT"
        print_info "This can be normal if running without active display"
    fi
    
    # Test project directory structure
    print_info "Testing project directory structure..."
    if [[ -d "$PROJECT_DIR/widgets" ]] && [[ -d "$PROJECT_DIR/core" ]] && [[ -d "$PROJECT_DIR/threads" ]] && [[ -d "$PROJECT_DIR/resources" ]]; then
        print_success "Project directory structure test passed"
    else
        print_error "Project directory structure test failed"
        return 1
    fi
    
    # Test launch script
    print_info "Testing launch script..."
    if [[ -x "$PROJECT_DIR/launch.sh" ]]; then
        print_success "Launch script test passed"
    else
        print_error "Launch script test failed"
        return 1
    fi
    
    print_success "Installation tests completed successfully"
}

# Main installation function
main() {
    print_info "Steam Deck DroidDeck Installer"
    print_info "Using Distrobox for persistent Ubuntu environment"
    echo ""
    
    check_steam_deck
    setup_distrobox
    create_container
    setup_python_environment
    setup_project_structure
    create_launcher
    create_steam_shortcut
    test_installation
    
    # Clear trap since we succeeded
    trap - ERR
    
    echo ""
    print_success "🎉 DroidDeck Installation Complete!"
    echo ""
    print_info "📁 Project Directory: $PROJECT_DIR"
    print_info "🧊 Container Name: $CONTAINER_NAME"
    print_info "🐍 Python Environment: /home/deck/droiddeck_env (in container)"
    echo ""
    print_warning "📋 Next Steps:"
    print_info "1. Copy your DroidDeck Python files to:"
    print_info "   • $PROJECT_DIR/main.py (entry point)"
    print_info "   • $PROJECT_DIR/widgets/ (UI components)"
    print_info "   • $PROJECT_DIR/core/ (application core)"
    print_info "   • $PROJECT_DIR/threads/ (background processing)"
    print_info "   • $PROJECT_DIR/resources/ (configs, images, icons)"
    echo ""
    print_info "2. Test the installation:"
    print_info "   $PROJECT_DIR/launch.sh"
    echo ""
    print_info "3. Complete Steam integration:"
    print_info "   $PROJECT_DIR/complete_steam_setup.sh"
    echo ""
    print_info "🎮 Container: distrobox enter $CONTAINER_NAME"
    print_info "🛠️  Debug: distrobox enter $CONTAINER_NAME -- bash"
    echo ""
    print_success "🤖 Ready for DroidDeck!"
}

# Run main installation
main "$@"
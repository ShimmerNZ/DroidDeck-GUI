#!/usr/bin/env python3
"""
Droid Deck - Main Entry Point
Enhanced with SteamDeck audio support
"""

import sys
import os
import pygame
from PyQt6.QtWidgets import QApplication

from core.application import DroidDeckApplication


def setup_steamdeck_audio():
    """Initialize audio with SteamDeck-specific settings"""
    if sys.platform == 'darwin':
        print("macOS detected - skipping pygame audio")
        return True

    try:
        # Set SteamDeck-specific environment variables
        os.environ['SDL_AUDIODRIVER'] = 'pulse'
        user_id = os.getuid()
        os.environ['PULSE_SERVER'] = f'unix:/run/user/{user_id}/pulse/native'
        
        print("Setting up SteamDeck audio...")
        
        # Try PulseAudio/PipeWire first (preferred for SteamDeck)
        try:
            pygame.mixer.pre_init(
                frequency=44100,    # High quality audio
                size=-16,           # 16-bit signed
                channels=2,         # Stereo
                buffer=1024         # Optimized buffer for SteamDeck
            )
            pygame.mixer.init()
            print("Audio initialized successfully with PulseAudio/PipeWire")
            return True
            
        except pygame.error as pulse_error:
            print(f"PulseAudio failed: {pulse_error}")
            print("Trying ALSA direct...")
            
            # Fallback to ALSA direct (SteamDeck hardware)
            os.environ['SDL_AUDIODRIVER'] = 'alsa'
            os.environ['ALSA_CARD'] = 'acp5x'  # SteamDeck audio card
            
            pygame.mixer.quit()  # Clean up previous attempt
            pygame.mixer.pre_init(
                frequency=44100,
                size=-16,
                channels=2,
                buffer=2048     # Larger buffer for ALSA
            )
            pygame.mixer.init()
            print("Audio initialized successfully with ALSA direct")
            return True
            
    except Exception as e:
        print(f"Audio initialization failed completely: {e}")
        print("Application will run without audio")
        return False

def main():
    """Main entry point for Droid Deck"""
    print("Starting DroidDeck application...")
    
    # Initialize audio first
    audio_available = setup_steamdeck_audio()
    if audio_available:
        print("Audio system ready")
    else:
        print("Running in silent mode")
    
    # Create Qt Application
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    
    # Create Droid Deck application
    try:
        droid_deck_app = DroidDeckApplication()
        droid_deck_app.show()
        
        print("DroidDeck application started successfully")
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"Failed to start DroidDeck application: {e}")
        sys.exit(1)
    finally:
        # Clean up audio on exit
        try:
            pygame.mixer.quit()
        except:
            pass

if __name__ == "__main__":
    main()
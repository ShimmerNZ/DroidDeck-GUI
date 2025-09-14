#!/usr/bin/env python3
"""
Droid Deck - Main Entry Point
"""

import sys
from PyQt6.QtWidgets import QApplication

from core.application import DroidDeckApplication

def main():
    """Main entry point for Droid Deck"""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    
    # Create Droid Deck application
    droid_deck_app = DroidDeckApplication()
    droid_deck_app.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
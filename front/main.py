#!/usr/bin/env python3
"""
WALL-E Control System - Main Entry Point
"""

import sys
from PyQt6.QtWidgets import QApplication

from core.application import WalleApplication


def main():
    """Main entry point for WALL-E Control System"""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    
    # Create WALL-E application
    walle_app = WalleApplication()
    walle_app.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
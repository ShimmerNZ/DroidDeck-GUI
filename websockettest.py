#!/usr/bin/env python3
"""
Simple WebSocket Client for Testing WALL-E Telemetry
This script connects to the WALL-E backend and prints telemetry data
"""

import asyncio
import websockets
import json
import time

async def telemetry_client():
    """Connect to WALL-E backend and display telemetry"""
    uri = "ws://10.1.1.230:8766"
    
    try:
        print(f"Connecting to {uri}...")
        
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to WALL-E backend")
            
            # Send heartbeat to keep connection alive
            heartbeat_task = asyncio.create_task(send_heartbeat(websocket))
            
            # Listen for messages
            async for message in websocket:
                try:
                    data = json.loads(message)
                    
                    if data.get("type") == "telemetry":
                        print("\n" + "="*60)
                        print(f"TELEMETRY UPDATE - {time.strftime('%H:%M:%S')}")
                        print("="*60)
                        
                        # System stats
                        print(f"CPU: {data.get('cpu', 'N/A')}%")
                        print(f"Memory: {data.get('memory', 'N/A')}%")
                        print(f"Temperature: {data.get('temperature', 'N/A')}°C")
                        
                        # Battery and current
                        battery_voltage = data.get('battery_voltage', 0)
                        current = data.get('current', 0)
                        current_a1 = data.get('current_a1', 0)
                        
                        print(f"Battery Voltage: {battery_voltage:.2f}V")
                        print(f"Current A0: {current:.2f}A")
                        print(f"Current A1: {current_a1:.2f}A")
                        
                        # Hardware status
                        maestro1 = data.get('maestro1', {})
                        maestro2 = data.get('maestro2', {})
                        
                        print(f"Maestro 1: {'Connected' if maestro1.get('connected') else 'Disconnected'}")
                        if maestro1.get('connected'):
                            print(f"  - Channels: {maestro1.get('channel_count', 'Unknown')}")
                            print(f"  - Firmware: {maestro1.get('firmware_version', 'Unknown')}")
                            print(f"  - Errors: {maestro1.get('error_flags', {}).get('has_errors', False)}")
                        
                        print(f"Maestro 2: {'Connected' if maestro2.get('connected') else 'Disconnected'}")
                        if maestro2.get('connected'):
                            print(f"  - Channels: {maestro2.get('channel_count', 'Unknown')}")
                            print(f"  - Firmware: {maestro2.get('firmware_version', 'Unknown')}")
                            print(f"  - Errors: {maestro2.get('error_flags', {}).get('has_errors', False)}")
                        
                        # Audio system
                        audio = data.get('audio_system', {})
                        print(f"Audio: {'Connected' if audio.get('connected') else 'Disconnected'}")
                        print(f"Audio Files: {audio.get('file_count', 0)}")
                        
                    elif data.get("type") == "heartbeat_response":
                        print("💓 Heartbeat response received")
                        
                    else:
                        print(f"📨 Message type: {data.get('type', 'unknown')}")
                        
                except json.JSONDecodeError as e:
                    print(f"❌ JSON decode error: {e}")
                    
    except websockets.exceptions.ConnectionRefused:
        print("❌ Connection refused - is the WALL-E backend running?")
        print("   Start it with: python main.py")
    except Exception as e:
        print(f"❌ Connection error: {e}")

async def send_heartbeat(websocket):
    """Send periodic heartbeat to keep connection alive"""
    while True:
        try:
            await websocket.send(json.dumps({
                "type": "heartbeat",
                "timestamp": time.time()
            }))
            await asyncio.sleep(30)  # Send heartbeat every 30 seconds
        except Exception as e:
            print(f"💔 Heartbeat failed: {e}")
            break

def main():
    """Main function"""
    print("🤖 WALL-E Telemetry Test Client")
    print("This will connect to the backend and display telemetry data")
    print("Press Ctrl+C to exit")
    
    try:
        asyncio.run(telemetry_client())
    except KeyboardInterrupt:
        print("\n👋 Disconnected")

if __name__ == "__main__":
    main()
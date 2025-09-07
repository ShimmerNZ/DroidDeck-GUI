#!/usr/bin/env python3
import asyncio
import websockets
import json

async def test_stepper():
    uri = "ws://10.1.1.230:8766"  # Your WebSocket URL
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to WALL-E backend")
            
            # Test forward
            await websocket.send(json.dumps({
                "type": "stepper",
                "command": "move_relative", 
                "steps": 100,
                "direction": "forward"
            }))
            
            await asyncio.sleep(2)
            
            # Test backward
            await websocket.send(json.dumps({
                "type": "stepper",
                "command": "move_relative",
                "steps": 100, 
                "direction": "backward"
            }))
            
            print("Stepper test commands sent")
            
    except Exception as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_stepper())
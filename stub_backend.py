import asyncio
import websockets
import json
import random
import psutil

# Generate fake telemetry data
def generate_telemetry():
    return {
        "battery_voltage": round(random.uniform(6.0, 16.0), 2),
        "current_draw": round(random.uniform(0.0, 120.0), 2),
        "cpu_usage": psutil.cpu_percent(),
        "memory_usage": psutil.virtual_memory().percent,
        "pi_temperature": round(random.uniform(40.0, 70.0), 1),
        "mjpeg_stream": {
            "fps": random.randint(15, 30),
            "resolution": "640x480",
            "latency_ms": random.randint(50, 150)
        },
        "dfplayer": {
            "connected": True,
            "file_count": random.randint(50, 200)
        },
        "maestro_1": {
            "connected": True,
            "channel_count": 18
        },
        "maestro_2": {
            "connected": True,
            "channel_count": 18
        }
    }

# Predefined list of 20 emotions with emojis
PREDEFINED_SCENES = [
    {"label": "Happy", "emoji": "😊"},
    {"label": "Sad", "emoji": "😢"},
    {"label": "Excited", "emoji": "🤩"},
    {"label": "Angry", "emoji": "😠"},
    {"label": "Surprised", "emoji": "😲"},
    {"label": "Sleepy", "emoji": "😴"},
    {"label": "Curious", "emoji": "🤔"},
    {"label": "Scared", "emoji": "😱"},
    {"label": "Confused", "emoji": "😕"},
    {"label": "Proud", "emoji": "😌"},
    {"label": "Shy", "emoji": "☺️"},
    {"label": "Bored", "emoji": "🥱"},
    {"label": "Love", "emoji": "😍"},
    {"label": "Laughing", "emoji": "😂"},
    {"label": "Crying", "emoji": "😭"},
    {"label": "Winking", "emoji": "😉"},
    {"label": "Thinking", "emoji": "🧠"},
    {"label": "Cool", "emoji": "😎"},
    {"label": "Annoyed", "emoji": "😒"},
    {"label": "Neutral", "emoji": "😐"}
]

# Send telemetry every 5 seconds
async def send_telemetry(websocket):
    while True:
        telemetry = generate_telemetry()
        await websocket.send(json.dumps({"type": "telemetry", "data": telemetry}))
        await asyncio.sleep(5)

# Handle incoming messages
async def handle_client(websocket):
    print("Client connected")
    telemetry_task = asyncio.create_task(send_telemetry(websocket))

    try:
        async for message in websocket:
            print("Received:", message)
            try:
                msg = json.loads(message)
                if msg.get("type") == "play_scene":
                    scene_name = msg.get("scene", "unknown")
                    print(f"Simulating scene: {scene_name}")
                    await asyncio.sleep(1)
                    await websocket.send(json.dumps({"type": "scene_done", "scene": scene_name}))
                elif msg.get("type") == "failsafe":
                    print("Failsafe triggered")
                    await websocket.send(json.dumps({"type": "failsafe_ack"}))
                elif msg.get("type") == "get_scenes":
                    await websocket.send(json.dumps({"type": "scene_list", "scenes": PREDEFINED_SCENES}))
            except json.JSONDecodeError:
                print("Invalid JSON received")
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    finally:
        telemetry_task.cancel()

# Start the WebSocket server
async def start_server():
    print("Stub backend running on ws://0.0.0.0:8765")
    async with websockets.serve(handle_client, "0.0.0.0", 8765):
        await asyncio.Future()  # Run forever

# Entry point
if __name__ == "__main__":
    try:
        import sys
        if sys.version_info >= (3, 7):
            asyncio.run(start_server())
        else:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(start_server())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(start_server())

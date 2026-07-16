import asyncio
import websockets
import json

async def main():
    uri = "ws://localhost:7842/ws/4caf7a56"
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected! Listening for events...")
            # Receive 5 events
            for i in range(15):
                msg = await websocket.recv()
                event = json.loads(msg)
                print(f"Event {i+1}: {event}")
    except Exception as e:
        print(f"WebSocket error: {e}")

asyncio.run(main())

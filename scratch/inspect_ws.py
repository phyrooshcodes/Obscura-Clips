import asyncio
import websockets
import json

async def main():
    uri = "ws://localhost:7842/ws/job_4caf7a56"
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected! Listening for events...")
            while True:
                try:
                    msg = await websocket.recv()
                    event = json.loads(msg)
                    print(f"Event: {event}")
                except websockets.exceptions.ConnectionClosed as e:
                    print(f"Connection closed: {e}")
                    break
    except Exception as e:
        print(f"WebSocket error: {e}")

asyncio.run(main())

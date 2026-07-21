import asyncio
import json
import math
import time
import websockets

async def stream_tracking_data(websocket):
    print("Frontend client connected.")
    angle = 0.0
    
    try:
        while True:
            # Simulate a circular cursor movement path
            angle += 0.05
            cx = 0.5 + 0.2 * math.cos(angle)
            cy = 0.5 + 0.2 * math.sin(angle)
            
            # Simulate changing states based on rotation
            is_dragging = (math.sin(angle) > 0.7)
            action = "drag_move" if is_dragging else "cursor_move"
            gesture = "PINCH" if is_dragging else "POINT"
            
            # Pack data identically to your system requirements
            payload = {
                "cursor": [cx, cy],
                "gesture": gesture,
                "action": action,
                "is_dragging": is_dragging
            }
            
            await websocket.send(json.dumps(payload))
            await asyncio.sleep(1 / 60)  # Lock execution to 60 FPS
            
    except websockets.exceptions.ConnectionClosedOK:
        print("Frontend client disconnected.")

async def main():
    async with websockets.serve(stream_tracking_data, "localhost", 8765):
        print("Aether core WebSocket server running on ws://localhost:8765")
        await asyncio.Event().wait()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
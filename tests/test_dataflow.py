"""Quick integration test for one-way data flow architecture."""

from aether.core.event_bus_v2 import EventBus
from aether.vision import PerceptionResult, DetectedObject, DetectedHand
from aether.vision.event_adapter import VisionEventAdapter
from aether.vision.state_builder import VisionStateBuilder
from aether.vision.vision_state import VisionState, TrackedObject

bus = EventBus(queued=True)
perception = PerceptionResult()
adapter = VisionEventAdapter(bus)
builder = VisionStateBuilder()

received = []
def on_event(e):
    received.append(e.type.value if hasattr(e.type, "value") else str(e.type))

for t in ["vision.object.detected", "vision.object.tracked", "vision.object.lost",
          "vision.hand.detected", "vision.hand.updated", "vision.hand.lost",
          "vision.gesture.started", "vision.gesture.holding", "vision.gesture.ended"]:
    bus.subscribe(t, lambda e: on_event(e))

# Helper: build VisionState from PerceptionResult and run adapter
def tick(frame_id=1):
    import time
    now = time.time()
    builder.begin_frame(frame_id, now)
    raw_objects = perception.get_objects()
    # Simulate tracker: give each object a stable ID
    tracked = []
    for i, obj in enumerate(raw_objects):
        tracked.append(TrackedObject(
            id=i + 1, label=obj.name, confidence=obj.confidence,
            box=obj.box, position=[0, 0, obj.distance_z],
            age=1, last_seen=now
        ))
    builder.update_objects(tracked)
    hands = perception.get_hands()
    builder.update_hands(hands)
    if hands and hands[0].landmarks:
        wrist = hands[0].landmarks[0]
        builder.update_cursor(wrist.get("x", 0), wrist.get("y", 0))
    else:
        builder.update_cursor(0, 0)
    state = builder.build()
    adapter.update(state)
    bus.flush()

# Frame 1: Object appears
received.clear()
perception.update_objects([DetectedObject(name="laptop", confidence=0.9, box=[0,0,100,100], distance_z=0.5)])
tick(1)
print(f"Frame 1 (new): {received}")

# Frame 2: Same object tracked
received.clear()
perception.update_objects([DetectedObject(name="laptop", confidence=0.91, box=[0,0,100,100], distance_z=0.49)])
tick(2)
print(f"Frame 2 (tracked): {received}")

# Frame 3: Object lost
received.clear()
perception.update_objects([])
tick(3)
print(f"Frame 3 (lost): {received}")

# Frame 4: Hand with gesture
received.clear()
perception.update_hands([DetectedHand(label="Right", landmarks=[{"x":0.5,"y":0.5,"z":0}]*21, gesture="Open_Palm", gesture_score=0.95)])
tick(4)
print(f"Frame 4 (gesture start): {received}")

# Frame 5: Gesture held
received.clear()
tick(5)
print(f"Frame 5 (holding): {received}")

# Frame 6: Gesture ended
received.clear()
perception.update_hands([])
tick(6)
print(f"Frame 6 (ended): {received}")

print()
print("Lifecycle events verified!")

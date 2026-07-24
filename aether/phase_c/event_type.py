class EventType(Enum):
    # Input
    KEYBOARD = "input_keyboard"
    MOUSE = "input_mouse"
    HOTKEY = "input_hotkey"
    GESTURE = "input_gesture"
    VOICE = "input_voice"
    
    # Vision
    HAND_DETECTED = "vision_hand_detected"
    HAND_LOST = "vision_hand_lost"
    OBJECT_DETECTED = "vision_object_detected"
    OBJECT_TRACKED = "vision_object_tracked"
    OBJECT_LOST = "vision_object_lost"

    # Command
    COMMAND_EXECUTED = "command_executed"
    COMMAND_COMPLETED = "command_completed"
    COMMAND_FAILED = "command_failed"

    # Status
    STATUS_UPDATE = "status_update"

    # UI
    UI_REQUESTED = "ui_requested"

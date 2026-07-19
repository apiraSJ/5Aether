import threading


class FrameBroker:
    """Thread-safe reference storage for raw incoming camera matrices.

    Producers call update_frame(); consumer threads wait on new_frame_event
    and then call get_frame() to grab the latest snapshot.
    """

    def __init__(self):
        self._current_frame = None
        self._lock = threading.Lock()
        self.new_frame_event = threading.Event()

    def update_frame(self, frame):
        with self._lock:
            self._current_frame = frame.copy()
        self.new_frame_event.set()

    def get_frame(self):
        with self._lock:
            return self._current_frame.copy() if self._current_frame is not None else None

    def clear_event(self):
        self.new_frame_event.clear()

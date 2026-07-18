class Tracker:
    """A placeholder tracker that currently passes detections through with dummy track IDs."""
    def __init__(self):
        pass

    def update(self, detections):
        """Annotates detections with tracking IDs."""
        tracked = []
        for i, det in enumerate(detections):
            tracked_det = det.copy()
            tracked_det["track_id"] = i  # simple baseline track ID
            tracked.append(tracked_det)
        return tracked

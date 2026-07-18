import time

class PerformanceTimer:
    """A context manager to measure execution time of a code block."""
    def __init__(self, name="Operation"):
        self.name = name
        self.start_time = None
        self.elapsed = 0.0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = time.perf_counter() - self.start_time

class PerformanceTracker:
    """Tracks running averages of various operations' durations."""
    def __init__(self):
        self.records = {}

    def update(self, name, duration):
        if name not in self.records:
            self.records[name] = []
        self.records[name].append(duration)
        # Keep only the last 100 entries for rolling average
        if len(self.records[name]) > 100:
            self.records[name].pop(0)

    def get_average(self, name):
        if name not in self.records or not self.records[name]:
            return 0.0
        return sum(self.records[name]) / len(self.records[name])

    def get_all_averages(self):
        return {name: self.get_average(name) for name in self.records}

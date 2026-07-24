class Event:
    """Event container for PluginBase interoperability with legacy event system."""
    
    def __init__(self, type, data=None, source=""):
        self.type = type
        self.data = data or {}
        self.source = source
        self.timestamp = time.time()
    
    def to_dict(self):
        return {
            "type": self.type,
            "data": self.data,
            "source": self.source,
            "timestamp": self.timestamp
        }

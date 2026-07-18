import logging
from ultralytics import YOLO

class Detector:
    """Wraps YOLOv8 model loading and inference."""
    def __init__(self, config: dict):
        self.logger = logging.getLogger("Aether.Detector")
        self.weights_path = config.get("weights", "yolov8n.pt")
        self.confidence_threshold = config.get("confidence", 0.25)
        
        self.logger.info(f"Initializing YOLO detector with weights: {self.weights_path}")
        try:
            self.model = YOLO(self.weights_path)
        except Exception as e:
            self.logger.error(f"Failed to load YOLO model: {e}")
            raise

    def detect(self, frame):
        """Runs object detection on the frame and returns filtered detections."""
        results = self.model(frame, verbose=False)[0]
        detections = []
        
        for box in results.boxes:
            conf = float(box.conf[0])
            if conf < self.confidence_threshold:
                continue
                
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            class_id = int(box.cls[0])
            label = results.names[class_id]
            
            detections.append({
                "box": (x1, y1, x2, y2),
                "confidence": conf,
                "class_id": class_id,
                "label": label
            })
            
        return detections

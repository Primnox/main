# backend/spatial_engine.py
import cv2
import numpy as np
from PIL import Image
from ultralytics import YOLO
try:
    import easyocr
    HAS_EASYOCR = True
except ImportError:
    HAS_EASYOCR = False
from logger import get_logger

log = get_logger("spatial")

class SpatialEngine:
    def __init__(self, model_path="yolov8n.pt"):
        log.info(f"Initializing SpatialEngine with {model_path}...")
        try:
            self.model = YOLO(model_path)
            if HAS_EASYOCR:
                self.reader = easyocr.Reader(['en'])
            else:
                self.reader = None
                log.warning("EasyOCR not found. Text mapping disabled.")
        except Exception as e:
            log.error(f"Failed to initialize SpatialEngine: {e}")
            self.model = None
            self.reader = None

    def generate_map(self, pil_img):
        """
        Runs YOLO detection and then OCR inside detected boxes.
        Returns a 'Spatial Map' string.
        """
        if not self.model:
            return "Spatial Engine Offline"

        log.debug("Generating spatial map...")
        # Convert PIL to OpenCV
        open_cv_image = np.array(pil_img)
        # Convert RGB to BGR
        open_cv_image = open_cv_image[:, :, ::-1].copy()

        results = self.model(open_cv_image, verbose=False)
        spatial_data = []

        for result in results:
            boxes = result.boxes
            for box in boxes:
                coords = box.xyxy[0].tolist() # x1, y1, x2, y2
                cls = int(box.cls[0])
                label = result.names[cls]
                conf = float(box.conf[0])

                item = {
                    "label": label,
                    "coords": [int(c) for c in coords],
                    "confidence": conf,
                    "text": ""
                }

                # Try OCR inside the box if it's a 'window', 'button', etc.
                if self.reader and conf > 0.5:
                    x1, y1, x2, y2 = item["coords"]
                    # Crop the region
                    crop = open_cv_image[y1:y2, x1:x2]
                    if crop.size > 0:
                        ocr_res = self.reader.readtext(crop)
                        if ocr_res:
                            item["text"] = " ".join([r[1] for r in ocr_res])

                spatial_data.append(item)

        # Format into a textual map
        map_lines = []
        for d in spatial_data:
            text_info = f" | Text: '{d['text']}'" if d['text'] else ""
            map_lines.append(f"- {d['label']} at {d['coords']}{text_info}")

        log.info(f"Spatial map generated with {len(spatial_data)} items.")
        return "\n".join(map_lines) if map_lines else "No major UI elements detected via YOLO."

if __name__ == "__main__":
    # Mock test
    engine = SpatialEngine()
    dummy_img = Image.new('RGB', (1280, 720), color=(73, 109, 137))
    print(engine.generate_map(dummy_img))

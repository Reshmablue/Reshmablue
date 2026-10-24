import time
import threading
import cv2
import numpy as np

# Silence noisy OpenCV internal C++ warnings from stderr
if hasattr(cv2, "utils") and hasattr(cv2.utils, "logging"):
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
    except Exception:
        pass

# Optional high-performance barcode decoding engine (ZXing-C++)
try:
    import zxingcpp
    HAS_ZXING = True
except ImportError:
    zxingcpp = None
    HAS_ZXING = False


class WebcamScanner:
    """
    Threaded webcam barcode and QR scanner.
    
    Features:
    - High-accuracy retail 1D (EAN-13, UPC, Code 128) and 2D (QR) decoding via zxing-cpp.
    - Fallback to OpenCV cv2.barcode.BarcodeDetector and cv2.QRCodeDetector.
    - Background camera acquisition for smooth 60fps GUI responsiveness.
    - Automatic bounding box drawing on detected barcodes.
    - Debounce / cooldown logic to prevent duplicate scans while an item stays in view.
    - Automatic reset once the item is removed from view.
    - Multi-backend camera initialization (CAP_ANY, CAP_DSHOW, CAP_MSMF).
    - Zero disk writes (never saves frames to disk).
    """

    def __init__(self, on_frame=None, on_barcode_scanned=None, on_status=None, cooldown_seconds=2.5):
        self.on_frame = on_frame
        self.on_barcode_scanned = on_barcode_scanned
        self.on_status = on_status
        self.cooldown_seconds = cooldown_seconds

        self.running = False
        self.thread = None
        self.cap = None

        # Cooldown and state tracking
        self.last_barcode = None
        self.last_scan_time = 0.0
        self.last_seen_time = 0.0

        # Initialize OpenCV fallback detectors
        self.barcode_detector = None
        self.qr_detector = None
        self._init_detectors()

    def _init_detectors(self):
        """Initialize OpenCV barcode and QR code detectors as fallback."""
        try:
            if hasattr(cv2, "barcode") and hasattr(cv2.barcode, "BarcodeDetector"):
                self.barcode_detector = cv2.barcode.BarcodeDetector()
        except Exception:
            self.barcode_detector = None

        try:
            if hasattr(cv2, "QRCodeDetector"):
                self.qr_detector = cv2.QRCodeDetector()
        except Exception:
            self.qr_detector = None

    def _notify_status(self, message, is_error=False):
        if self.on_status:
            try:
                self.on_status(message, is_error)
            except Exception:
                pass

    def start(self, camera_index=0):
        """Start webcam capture and barcode scanning in a background thread."""
        if self.running:
            return True

        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, args=(camera_index,), daemon=True)
        self.thread.start()
        return True

    def stop(self):
        """Stop webcam capture and release all camera resources."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.5)
        self.thread = None
        self._release_camera()
        self._notify_status("Webcam stopped.")

    def is_running(self):
        """Return True if the camera scanning thread is active."""
        return self.running and self.cap is not None and self.cap.isOpened()

    def _release_camera(self):
        """Safely release the OpenCV VideoCapture object."""
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def _decode_frame(self, frame):
        """
        Attempt to detect and decode barcode or QR code in the frame.
        Returns (barcode_text, points_polygon) or (None, None).
        """
        # 1. Primary: Use zxing-cpp if available (handles all retail EAN-13, UPC, Code 128, QR)
        if HAS_ZXING and zxingcpp is not None:
            try:
                # Try direct frame
                result = zxingcpp.read_barcode(frame)
                if not result:
                    # Try center crop with slight contrast boost for webcam clarity
                    h, w = frame.shape[:2]
                    cx, cy = w // 2, h // 2
                    rw, rh = int(w * 0.7), int(h * 0.7)
                    x1, y1 = max(0, cx - rw // 2), max(0, cy - rh // 2)
                    x2, y2 = min(w, cx + rw // 2), min(h, cy + rh // 2)
                    crop = frame[y1:y2, x1:x2]
                    crop_result = zxingcpp.read_barcode(crop)
                    if crop_result:
                        text = str(crop_result.text).strip()
                        if text:
                            # Offset points back to original frame
                            pos = crop_result.position
                            pts = np.array([
                                [pos.top_left.x + x1, pos.top_left.y + y1],
                                [pos.top_right.x + x1, pos.top_right.y + y1],
                                [pos.bottom_right.x + x1, pos.bottom_right.y + y1],
                                [pos.bottom_left.x + x1, pos.bottom_left.y + y1]
                            ], dtype=np.int32)
                            return text, pts

                if result:
                    text = str(result.text).strip()
                    if text:
                        pos = result.position
                        pts = np.array([
                            [pos.top_left.x, pos.top_left.y],
                            [pos.top_right.x, pos.top_right.y],
                            [pos.bottom_right.x, pos.bottom_right.y],
                            [pos.bottom_left.x, pos.bottom_left.y]
                        ], dtype=np.int32)
                        return text, pts
            except Exception:
                pass

        # 2. Secondary: OpenCV 1D Barcode detector fallback
        if self.barcode_detector is not None:
            try:
                ret, decoded_info, decoded_types, points = self.barcode_detector.detectAndDecodeWithType(frame)
                if ret and decoded_info:
                    for text in decoded_info:
                        clean_text = str(text).strip()
                        if clean_text:
                            pts = points[0] if (points is not None and len(points) > 0) else None
                            return clean_text, pts
            except Exception:
                pass

        # 3. Tertiary: OpenCV QR Code detector fallback
        if self.qr_detector is not None:
            try:
                text, points, _ = self.qr_detector.detectAndDecode(frame)
                clean_text = str(text).strip() if text else ""
                if clean_text:
                    pts = points[0] if (points is not None and len(points) > 0) else points
                    return clean_text, pts
            except Exception:
                pass

        return None, None

    def _capture_loop(self, camera_index):
        """Main camera acquisition and barcode processing loop running in background."""
        self._notify_status("Connecting to webcam...")

        try:
            self.cap = None
            # Try available backends cleanly
            for backend in (cv2.CAP_ANY, cv2.CAP_DSHOW, cv2.CAP_MSMF):
                try:
                    test_cap = cv2.VideoCapture(camera_index, backend)
                    if test_cap.isOpened():
                        self.cap = test_cap
                        break
                    else:
                        test_cap.release()
                except Exception:
                    pass

            if self.cap is None or not self.cap.isOpened():
                self.running = False
                self._notify_status(
                    "Webcam unavailable. Check camera privacy permissions or ensure another app is not using it.",
                    is_error=True
                )
                return

            # Set reasonable resolution for responsiveness
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

            self._notify_status("Webcam active. Hold barcode inside the target box.")

            consecutive_read_failures = 0

            while self.running:
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    consecutive_read_failures += 1
                    if consecutive_read_failures > 30:
                        self._notify_status("Lost connection to webcam.", is_error=True)
                        break
                    time.sleep(0.03)
                    continue

                consecutive_read_failures = 0
                now = time.time()

                # Mirror frame horizontally for natural user interaction
                frame = cv2.flip(frame, 1)

                # Decode barcodes from frame
                barcode, points = self._decode_frame(frame)

                if barcode:
                    self.last_seen_time = now

                    # Draw green bounding box around detected barcode
                    if points is not None:
                        try:
                            pts = np.int32(points).reshape((-1, 1, 2))
                            cv2.polylines(frame, [pts], isClosed=True, color=(0, 255, 0), thickness=3)
                        except Exception:
                            pass

                    # Check debounce / cooldown
                    is_same_barcode = (barcode == self.last_barcode)
                    cooldown_expired = (now - self.last_scan_time) >= self.cooldown_seconds

                    if not is_same_barcode or cooldown_expired:
                        # New valid scan
                        self.last_barcode = barcode
                        self.last_scan_time = now

                        # Visual feedback banner on frame
                        cv2.putText(
                            frame, f"SCANNED: {barcode}", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA
                        )

                        if self.on_barcode_scanned:
                            try:
                                self.on_barcode_scanned(barcode)
                            except Exception as err:
                                self._notify_status(f"Error handling scanned barcode: {err}", is_error=True)
                    else:
                        # Barcode is still in view during cooldown
                        cv2.putText(
                            frame, f"IN VIEW: {barcode}", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 215, 255), 2, cv2.LINE_AA
                        )
                else:
                    # No barcode detected in current frame
                    # If barcode has disappeared for > 1.0 second, reset state so it can be re-scanned immediately
                    if (now - self.last_seen_time) > 1.0:
                        self.last_barcode = None

                    # Visual scan guide overlay (reticle in center)
                    h, w = frame.shape[:2]
                    cx, cy = w // 2, h // 2
                    rw, rh = 320, 180
                    x1, y1 = cx - rw // 2, cy - rh // 2
                    x2, y2 = cx + rw // 2, cy + rh // 2
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 255), 2)
                    cv2.putText(
                        frame, "Center Barcode Here", (x1 + 10, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2, cv2.LINE_AA
                    )

                # Send frame to GUI callback
                if self.on_frame:
                    try:
                        self.on_frame(frame)
                    except Exception:
                        pass

                # Cap capture rate (~30 FPS)
                time.sleep(0.02)

        except Exception as error:
            self._notify_status(f"Webcam error: {error}", is_error=True)

        finally:
            self._release_camera()
            self.running = False

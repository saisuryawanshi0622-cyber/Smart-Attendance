import cv2
import os
import numpy as np
import mediapipe as mp

class FaceEngine:
    def __init__(self, known_faces_dir='known_faces'):
        self.known_faces_dir = known_faces_dir
        
        # Mediapipe for fast face detection
        self.mp_face_detection = mp.solutions.face_detection
        self.face_detection = self.mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5)
        
        # OpenCV Face Recognizer (Lightweight, Mac-friendly)
        try:
            self.recognizer = cv2.face.LBPHFaceRecognizer_create()
            self.is_trained = False
        except AttributeError:
            print("WARNING: opencv-contrib-python is required for LBPHFaceRecognizer.")
            self.recognizer = None
            self.is_trained = False
            
        self.name_dict = {} # Map integer ID to Name
        self.load_known_faces()
        
    def load_known_faces(self):
        """Trains LBPH face recognizer from the known_faces directory."""
        if not self.recognizer: return
        
        if not os.path.exists(self.known_faces_dir):
            os.makedirs(self.known_faces_dir)
            
        faces = []
        ids = []
        current_id = 0
        
        for filename in os.listdir(self.known_faces_dir):
            if filename.endswith(('.jpg', '.jpeg', '.png')):
                filepath = os.path.join(self.known_faces_dir, filename)
                name = os.path.splitext(filename)[0].replace('_', ' ')
                
                # Load image and convert to grayscale
                img = cv2.imread(filepath)
                if img is None: continue
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                
                # We need to crop to face to train LBPH properly
                results = self.face_detection.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
                if results.detections:
                    detection = results.detections[0]
                    bboxC = detection.location_data.relative_bounding_box
                    h, w, _ = img.shape
                    x, y, fw, fh = int(bboxC.xmin * w), int(bboxC.ymin * h), int(bboxC.width * w), int(bboxC.height * h)
                    
                    # Ensure within bounds
                    x, y = max(0, x), max(0, y)
                    face_roi = gray[y:y+fh, x:x+fw]
                    if face_roi.size > 0:
                        faces.append(cv2.resize(face_roi, (200, 200)))
                        ids.append(current_id)
                        self.name_dict[current_id] = name
                        current_id += 1
                        print(f"Trained face for: {name}")

        if faces:
            self.recognizer.train(faces, np.array(ids))
            self.is_trained = True

    def detect_faces(self, rgb_frame):
        """
        Takes an RGB frame and returns locations and names of detected faces.
        Returns: [(top, right, bottom, left), name]
        """
        results = self.face_detection.process(rgb_frame)
        
        detected_list = []
        if results.detections:
            h, w, _ = rgb_frame.shape
            gray = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2GRAY)
            
            for detection in results.detections:
                bboxC = detection.location_data.relative_bounding_box
                x, y, fw, fh = int(bboxC.xmin * w), int(bboxC.ymin * h), int(bboxC.width * w), int(bboxC.height * h)
                
                x, y = max(0, x), max(0, y)
                fw = min(fw, w - x)
                fh = min(fh, h - y)
                
                if fw == 0 or fh == 0: continue
                
                top, right, bottom, left = y, x+fw, y+fh, x
                name = "Unknown"
                
                if self.is_trained and self.recognizer:
                    face_roi = gray[y:y+fh, x:x+fw]
                    if face_roi.size > 0:
                        face_roi = cv2.resize(face_roi, (200, 200))
                        id_, conf = self.recognizer.predict(face_roi)
                        # Lower conf is better in LBPH. Usually < 70 is very reliable.
                        if conf < 70:
                            name = self.name_dict.get(id_, "Unknown")
                            
                detected_list.append(((top, right, bottom, left), name))
                
        return detected_list

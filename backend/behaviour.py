import cv2
import numpy as np
import time
import mediapipe as mp

class BehaviourEngine:
    def __init__(self):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=10, 
            refine_landmarks=True, 
            min_detection_confidence=0.5, 
            min_tracking_confidence=0.5
        )
        
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            max_num_hands=10,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
            
        self.student_states = {}
        # Format: {name: {'ear_start': None, 'mar_start': None, 'orig_pos': None, 'phone_start': None, 'score': 10, 'last_seen': time.time()}}
        
    def _eye_aspect_ratio(self, eye_pts, landmarks, w, h):
        # Mediapipe gives normalized coordinates
        p1 = np.array([landmarks[eye_pts[0]].x * w, landmarks[eye_pts[0]].y * h]) # Left
        p2 = np.array([landmarks[eye_pts[1]].x * w, landmarks[eye_pts[1]].y * h]) # Right
        p3 = np.array([landmarks[eye_pts[2]].x * w, landmarks[eye_pts[2]].y * h]) # Top
        p4 = np.array([landmarks[eye_pts[3]].x * w, landmarks[eye_pts[3]].y * h]) # Bottom
        
        vert = np.linalg.norm(p3 - p4)
        horz = np.linalg.norm(p1 - p2)
        if horz == 0: return 1.0
        return vert / horz

    def _mouth_aspect_ratio(self, landmarks, w, h):
        # 13 top lip, 14 bottom lip, 78 left corner, 308 right corner
        top = np.array([landmarks[13].x * w, landmarks[13].y * h])
        bottom = np.array([landmarks[14].x * w, landmarks[14].y * h])
        left = np.array([landmarks[78].x * w, landmarks[78].y * h])
        right = np.array([landmarks[308].x * w, landmarks[308].y * h])
        
        vert = np.linalg.norm(top - bottom)
        horz = np.linalg.norm(left - right)
        if horz == 0: return 0.0
        return vert / horz
        
    def init_student(self, name, position):
        if name not in self.student_states:
            self.student_states[name] = {
                'ear_start': None,
                'mar_start': None,
                'hiding_mouth_start': None,
                'orig_pos': position, # (x,y)
                'phone_start': None,
                'score': 10,
                'last_seat_alert': 0,
                'last_seen': time.time()
            }
        else:
            self.student_states[name]['last_seen'] = time.time()

    def process_frame(self, frame, rgb_frame, detected_faces):
        """
        detected_faces: list of ((top, right, bottom, left), name)
        Returns alerts list.
        """
        alerts = []
        current_time = time.time()
        h, w, _ = frame.shape
        
        # We run Face Mesh and Hand Tracking over the entire frame
        results = self.face_mesh.process(rgb_frame)
        hand_results = self.hands.process(rgb_frame)
        
        # Mediapipe points don't naturally link to face locations directly by name,
        # so we will use the bounding box logic.
        
        for (top, right, bottom, left), name in detected_faces:
            if name == "Unknown": continue
            
            center_x = (left + right) // 2
            center_y = (top + bottom) // 2
            
            self.init_student(name, (center_x, center_y))
            state = self.student_states[name]
            
            # 1. Seat Change Detection
            if state['orig_pos'] is not None:
                orig_x, orig_y = state['orig_pos']
                move_dist = np.linalg.norm(np.array([center_x, center_y]) - np.array([orig_x, orig_y]))
                
                # Check if it's been at least 10 seconds since the last seat change alert
                if move_dist > 150:
                    last_alert_time = state.get('last_seat_alert', 0)
                    if current_time - last_alert_time > 10.0:
                        alerts.append({'name': name, 'type': 'seat_change', 'msg': f'{name} changed seat'})
                        state['score'] -= 1
                        state['orig_pos'] = (center_x, center_y) # reset
                        state['last_seat_alert'] = current_time
                        
            # Hand over mouth detection (Hiding Mouth)
            is_hiding_mouth = False
            if hand_results.multi_hand_landmarks:
                for hand_landmarks in hand_results.multi_hand_landmarks:
                    for lm in hand_landmarks.landmark:
                        hx, hy = int(lm.x * w), int(lm.y * h)
                        # Check if hand landmark is within the lower half of the face box
                        if left <= hx <= right and (top + bottom)//2 <= hy <= bottom:
                            is_hiding_mouth = True
                            break
                    if is_hiding_mouth:
                        break
                        
            if is_hiding_mouth:
                if state['hiding_mouth_start'] is None:
                    state['hiding_mouth_start'] = current_time
                elif current_time - state['hiding_mouth_start'] > 2.0:
                    alerts.append({'name': name, 'type': 'hiding_mouth', 'msg': f'{name} is hiding mouth'})
                    state['score'] -= 1
                    state['hiding_mouth_start'] = None
            else:
                state['hiding_mouth_start'] = None
                    
            # 2 & 3. Sleep & Talk Detection via Face Mesh
            # Match mesh to this face box by checking center
            matched_mesh = None
            if results.multi_face_landmarks:
                for face_landmarks in results.multi_face_landmarks:
                    # Nose tip is index 1
                    nose_x = face_landmarks.landmark[1].x * w
                    nose_y = face_landmarks.landmark[1].y * h
                    if left <= nose_x <= right and top <= nose_y <= bottom:
                        matched_mesh = face_landmarks.landmark
                        break
                        
            if matched_mesh:
                # Left eye: 33 (L), 133 (R), 159 (T), 145 (B)
                left_ear = self._eye_aspect_ratio([33, 133, 159, 145], matched_mesh, w, h)
                # Right eye: 362 (L), 263 (R), 386 (T), 374 (B)
                right_ear = self._eye_aspect_ratio([362, 263, 386, 374], matched_mesh, w, h)
                ear = (left_ear + right_ear) / 2.0
                
                # Sleep threshold - increase to 0.18 for better sensitivity
                if ear < 0.18:
                    if state['ear_start'] is None:
                        state['ear_start'] = current_time
                    elif current_time - state['ear_start'] > 2.0: # Reduced from 3s to 2s
                        alerts.append({'name': name, 'type': 'sleeping', 'msg': f'{name} is sleeping'})
                        state['score'] -= 2
                        state['ear_start'] = None
                else:
                    state['ear_start'] = None
                    
                mar = self._mouth_aspect_ratio(matched_mesh, w, h)
                
                # Talk threshold - adjust to 0.12 and remove ear check dependency
                if mar > 0.12: 
                    if state['mar_start'] is None:
                        state['mar_start'] = current_time
                    elif current_time - state['mar_start'] > 3.0: # Reduced from 4s to 3s
                        alerts.append({'name': name, 'type': 'talking', 'msg': f'{name} is talking'})
                        state['score'] -= 1
                        state['mar_start'] = None
                else:
                    state['mar_start'] = None
                    
            # 4. Phone Detection
            roi_top = max(0, bottom)
            roi_bottom = min(frame.shape[0], bottom + (bottom - top))
            roi_left = max(0, left - 50)
            roi_right = min(frame.shape[1], right + 50)
            
            if roi_bottom > roi_top and roi_right > roi_left:
                roi = frame[roi_top:roi_bottom, roi_left:roi_right]
                hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                lower_skin = np.array([0, 20, 70], dtype=np.uint8)
                upper_skin = np.array([20, 255, 255], dtype=np.uint8)
                mask = cv2.inRange(hsv_roi, lower_skin, upper_skin)
                skin_ratio = cv2.countNonZero(mask) / (mask.shape[0] * mask.shape[1] + 1)
                
                if skin_ratio > 0.3: 
                    if state['phone_start'] is None:
                        state['phone_start'] = current_time
                    elif current_time - state['phone_start'] > 5.0:
                        alerts.append({'name': name, 'type': 'phone', 'msg': f'{name} is using phone'})
                        state['score'] -= 1.5
                        state['phone_start'] = None
                else:
                    state['phone_start'] = None
                    
        # Check for left class
        for name, state in list(self.student_states.items()):
            if current_time - state['last_seen'] > 30:
                alerts.append({'name': name, 'type': 'left_class', 'msg': f'{name} left the classroom'})
                del self.student_states[name]
                
        return alerts

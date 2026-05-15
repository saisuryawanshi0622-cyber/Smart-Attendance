import time
import csv
import os
from datetime import datetime
import database

class AttendanceEngine:
    def __init__(self):
        self.class_active = False
        self.start_time = None
        self.duration_minutes = 0
        self.subject = "General"
        self.user_id = None
        self.presence_tracking = {} 
        self.marked_students = set()
        self.face_buffer = {} 
        self.frames_to_confirm = 3
        self._timer = None
        
    def start_class(self, duration_minutes, subject, user_id):
        self.class_active = True
        self.start_time = time.time()
        self.duration_minutes = duration_minutes
        self.subject = subject
        self.user_id = user_id
        self.presence_tracking = {}
        self.marked_students = set()
        
        # Start a background timer to ensure class ends exactly when time is up
        import threading
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(duration_minutes * 60, self.end_class)
        self._timer.daemon = True
        self._timer.start()
        
    def end_class(self):
        if not self.class_active:
            return
        self.class_active = False
        if self._timer:
            self._timer.cancel()
        self._process_attendance()
        
    def get_time_remaining(self):
        if not self.class_active:
            return 0
        elapsed = time.time() - self.start_time
        remaining = (self.duration_minutes * 60) - elapsed
        if remaining <= 0:
            self.end_class()
            return 0
        return remaining
        
    def update_presence(self, name):
        if not self.class_active: return False, False
        if name == "Unknown": return False, False
        
        # Buffer the name to ensure it's not a flickering misidentification
        self.face_buffer[name] = self.face_buffer.get(name, 0) + 1
        
        # Only process if we've seen this name enough times
        if self.face_buffer[name] < self.frames_to_confirm:
            return False, False
            
        # Reset buffer for this name once confirmed
        self.face_buffer[name] = 0
        
        # Initialize if new
        if name not in self.presence_tracking:
            self.presence_tracking[name] = {
                'seconds': 0, 
                'last_seen': time.time(),
                'arrival': datetime.now().strftime('%H:%M'),
                'score': 10, # Start with perfect behaviour
                'checked_in': False,
                'checked_out': False
            }
            
        # Update presence time
        current_time = time.time()
        elapsed = current_time - self.presence_tracking[name]['last_seen']
        
        # Only add if seen recently (e.g. within last 10 seconds)
        if elapsed < 10:
            self.presence_tracking[name]['seconds'] += int(elapsed)
            
        self.presence_tracking[name]['last_seen'] = current_time
        
        # Check-in/Check-out logic
        checkin_window = 1 if self.duration_minutes == 3 else 10
        checkout_window = 1 if self.duration_minutes == 3 else 10
        
        elapsed_seconds_total = current_time - self.start_time
        elapsed_minutes_total = elapsed_seconds_total / 60
        remaining_minutes = self.duration_minutes - elapsed_minutes_total
        
        just_checked_in = False
        just_checked_out = False
        
        if elapsed_minutes_total <= checkin_window:
            if not self.presence_tracking[name]['checked_in']:
                self.presence_tracking[name]['checked_in'] = True
                just_checked_in = True
            
        if remaining_minutes <= checkout_window:
            if not self.presence_tracking[name]['checked_out']:
                self.presence_tracking[name]['checked_out'] = True
                just_checked_out = True
                
        return just_checked_in, just_checked_out
                
    def deduct_score(self, name, points):
        if name in self.presence_tracking:
            self.presence_tracking[name]['score'] -= points
                
    def _process_attendance(self):
        total_seconds = self.duration_minutes * 60
        date_today = datetime.now().strftime("%Y-%m-%d")
        
        # Load settings
        settings = database.get_settings()
        threshold_present = float(settings.get('attendance_threshold', 75))
        
        all_students = database.get_all_students()
        
        for student in all_students:
            student_name = student['name']
            student_roll = student['roll_number']
            student_id = student['id']
            
            # The face_engine produces names in the format "Name RollNumber" based on the filename
            tracking_key = f"{student_name} {student_roll}"
            
            if tracking_key in self.presence_tracking:
                data = self.presence_tracking[tracking_key]
                presence_percentage = (data['seconds'] / total_seconds) * 100
                presence_percentage = min(presence_percentage, 100) # Cap at 100
                
                # Mark present ONLY if both checked in and checked out
                checked_in = data.get('checked_in', False)
                checked_out = data.get('checked_out', False)
                
                print(f"[DEBUG] Student {tracking_key}: Checked IN = {checked_in}, Checked OUT = {checked_out}")
                
                if checked_in and checked_out:
                    status = "Present"
                else:
                    status = "Absent"
                    
                arrival = data['arrival']
                presence_sec = data['seconds']
                score = data['score']
            else:
                print(f"[DEBUG] Student {tracking_key}: Never seen during class.")
                presence_percentage = 0.0
                status = "Absent"
                arrival = "-"
                presence_sec = 0
                score = 10.0
                
            database.save_attendance_record(
                student_id=student_id,
                user_id=self.user_id,
                date=date_today,
                subject=self.subject,
                status=status,
                arrival_time=arrival,
                presence_seconds=presence_sec,
                presence_percentage=presence_percentage,
                behaviour_score=score
            )
            
        self.export_csv()
            
    def export_csv(self):
        records = database.get_today_attendance()
        if not records: return
        
        os.makedirs('attendance', exist_ok=True)
        date_today = datetime.now().strftime("%Y-%m-%d")
        filepath = f"attendance/Attendance_{date_today}.csv"
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', 'Name', 'Roll Number', 'Subject', 'Status', 'Arrival Time', 'Presence %', 'Behaviour Score'])
            for r in records:
                writer.writerow([r['student_id'], r['name'], r['roll_number'], r['subject'], r['status'], r['arrival_time'], f"{r['presence_percentage']:.1f}%", r['behaviour_score']])

import os
import threading
import time
import queue

class VoiceAlertSystem:
    def __init__(self):
        self.alert_queue = queue.Queue()
        self.cooldowns = {} # {(name, type): last_alert_time}
        self.cooldown_period = 10 # 10 seconds instead of 3 minutes so it repeats
        self.is_active = True
        
        # Start background thread for alerts
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        
    def _worker(self):
        while True:
            if not self.is_active:
                time.sleep(1)
                continue
                
            try:
                alert = self.alert_queue.get(timeout=1)
                # Use native Mac 'say' command which is extremely reliable
                os.system(f'say "{alert}" &')
                self.alert_queue.task_done()
            except queue.Empty:
                pass
            except Exception as e:
                print(f"Voice Alert Error: {e}")

    def add_alert(self, name, alert_type, custom_msg=None):
        if not self.is_active:
            return
            
        current_time = time.time()
        key = (name, alert_type)
        
        if key in self.cooldowns:
            if current_time - self.cooldowns[key] < self.cooldown_period:
                return # Cooldown active
                
        self.cooldowns[key] = current_time
        
        if custom_msg:
            msg = custom_msg
        elif alert_type == 'sleeping':
            msg = f"{name} is sleeping. Wake up immediately."
        elif alert_type == 'talking':
            msg = f"{name} is talking. Please stop talking."
        elif alert_type == 'hiding_mouth':
            msg = f"{name} is covering their mouth. Do not hide your mouth."
        elif alert_type == 'seat_change':
            msg = f"{name} changed seats. Please go back to your original seat."
        elif alert_type == 'left_class':
            msg = f"{name} has left the classroom."
        else:
            msg = f"{name}, please pay attention."
                
        self.alert_queue.put(msg)
        
    def set_active(self, active):
        self.is_active = active
        
    def announce_class_end(self):
        if self.is_active:
            self.alert_queue.put("The lecture is now over. Attendance is being marked for all students.")

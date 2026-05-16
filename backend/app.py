import os
import cv2
import numpy as np
import threading
import json
import time
from flask import Flask, render_template, Response, request, jsonify, redirect, url_for, send_file, session, flash
from werkzeug.utils import secure_filename
from datetime import datetime
from functools import wraps

import database
from face_engine import FaceEngine
from behaviour import BehaviourEngine
from voice_alert import VoiceAlertSystem
from attendance_engine import AttendanceEngine
import report_generator
import notifications

import csv
import openpyxl
import fitz

app = Flask(__name__, template_folder='../frontend/templates', static_folder='../frontend/static')
app.config['UPLOAD_FOLDER'] = 'known_faces'
app.secret_key = 'smart-classroom-secret-key-123'

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Initialize engines
print("Initializing Engines...")
database.init_db()
face_engine = None
try:
    face_engine = FaceEngine()
    print("Face Engine Loaded")
except Exception as e:
    print(f"Face Engine Error: {e}")
behaviour_engine = BehaviourEngine()
voice_system = None
try:
    voice_system = VoiceAlertSystem()
    print("Voice System Loaded")
except Exception as e:
    print(f"Voice System Error: {e}")
attendance_engine = AttendanceEngine()

# Global state for streaming
output_frame = None
lock = threading.Lock()
latest_alerts = []
camera_requested = False
cap = None
current_class_settings = {}

def process_camera():
    global output_frame, latest_alerts, cap, camera_requested
    frame_count = 0
    
    while True:
        # Physical Camera Management (exclusively in this thread to prevent Mac crashes)
        if camera_requested and (cap is None or not cap.isOpened()):
            os.environ["OPENCV_AVFOUNDATION_SKIP_AUTH"] = "1"
            print("Turning ON physical camera...")
            try:
                cap = cv2.VideoCapture(0)
            except Exception as e:
                print(f"Camera Error: {e}")
                cap = None
            if cap is None or not cap.isOpened():
                print("Failed to open physical camera (cloud environment).")
                cap = None
            
        if not camera_requested and cap is not None:
            print("Turning OFF physical camera...")
            cap.release()
            cap = None
            with lock:
                output_frame = None
                
        if cap is None or not cap.isOpened():
            # Generate placeholder while camera is off
            placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(placeholder, "CAMERA OFFLINE", (170, 240), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(placeholder, "Click 'Start Class' to begin", (150, 280), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (150, 150, 150), 1)
            with lock:
                output_frame = placeholder
            time.sleep(1)
            continue
            
        ret, frame = cap.read()
        if not ret: continue
        
        frame_count += 1
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Run face recognition every 3rd frame
        if frame_count % 3 == 0:
            detected_faces = list(face_engine.detect_faces(rgb_frame))
            
            if attendance_engine.class_active:
                for box, name in detected_faces:
                    just_checked_in, just_checked_out = attendance_engine.update_presence(name)
                    
                    if just_checked_in:
                        students = database.get_all_students()
                        roll = ""
                        for s in students:
                            if s['name'] == name:
                                roll = s['roll_number']
                                break
                        voice_system.add_alert(name, 'custom', f"{name} {roll}")
                        
                    if just_checked_out:
                        voice_system.add_alert(name, 'custom', f"Attendance is marked for {name}")
                
                # Run behaviour detection
                alerts = behaviour_engine.process_frame(frame, rgb_frame, detected_faces)
                for alert in alerts:
                    # Filter alerts based on settings
                    if alert['type'] == 'sleeping' and current_class_settings.get('detect_sleep', '1') == '0': continue
                    if alert['type'] == 'talking' and current_class_settings.get('detect_talk', '1') == '0': continue
                    if alert['type'] == 'seat_change' and current_class_settings.get('detect_seat', '1') == '0': continue
                    if alert['type'] == 'phone' and current_class_settings.get('detect_phone', '1') == '0': continue

                    latest_alerts.append({**alert, 'time': datetime.now().strftime("%H:%M:%S")})
                    if len(latest_alerts) > 50: latest_alerts.pop(0) # keep recent 50
                    
                    # Voice Alert for behaviour disabled as requested
                    # voice_system.add_alert(alert['name'], alert['type'], alert.get('msg'))
                    
                    # Deduct score & log
                    attendance_engine.deduct_score(alert['name'], 1)
                    student = database.get_student_by_roll(alert['name']) # name used here assuming mapped correctly or we log name directly
                    if student:
                        database.log_behaviour(student['id'], datetime.now().strftime("%Y-%m-%d"), attendance_engine.subject, alert['type'], datetime.now().strftime("%H:%M:%S"))

            # Draw boxes
            for (top, right, bottom, left), name in detected_faces:
                color = (0, 0, 255) if name == "Unknown" else (0, 255, 0)
                cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                cv2.putText(frame, name, (left, bottom + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        with lock:
            output_frame = frame.copy()

# Start camera thread
t = threading.Thread(target=process_camera, daemon=True)
t.start()

def generate():
    global output_frame, lock
    while True:
        with lock:
            if output_frame is None:
                # Create a black placeholder frame with "Camera Offline" text
                placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(placeholder, "CAMERA OFFLINE", (170, 240), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                cv2.putText(placeholder, "Click 'Start Class' to begin", (150, 280), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (150, 150, 150), 1)
                (flag, encodedImage) = cv2.imencode(".jpg", placeholder)
            else:
                (flag, encodedImage) = cv2.imencode(".jpg", output_frame)
                if not flag:
                    encodedImage = None
                    
        if encodedImage is None:
            time.sleep(0.05)
            continue
            
        yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encodedImage) + b'\r\n')
        time.sleep(0.05) # ~20 FPS for stability

from flask import send_from_directory

@app.route('/known_faces/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            return render_template('signup.html', error="Passwords do not match")
            
        if database.get_user(username):
            return render_template('signup.html', error="Username already exists")
            
        if database.add_user(username, password):
            return render_template('signup.html', success="Account created! You can now login.")
        else:
            return render_template('signup.html', error="Registration failed")
            
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = database.get_user(username)
        
        if user and user['password'] == password:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Invalid username or password")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    records = database.get_today_attendance(session['user_id'])
    subjects = sorted(list(set(r['subject'] for r in records if r['subject'])))
    return render_template('dashboard.html', records=records, subjects=subjects)

@app.route('/delete_record/<int:id>', methods=['POST'])
@login_required
def delete_record(id):
    database.delete_attendance_record(id)
    return redirect(url_for('dashboard'))

@app.route('/delete_selected', methods=['POST'])
@login_required
def delete_selected():
    record_ids = request.form.getlist('record_ids')
    if record_ids:
        # Convert to integers
        record_ids = [int(id) for id in record_ids if id.isdigit()]
        database.delete_multiple_attendance_records(record_ids)
    return redirect(url_for('dashboard'))

@app.route('/clear_today_attendance', methods=['POST'])
@login_required
def clear_today_attendance():
    database.clear_today_attendance(session['user_id'])
    return redirect(url_for('dashboard'))

@app.route('/students')
@login_required
def students():
    student_list = database.get_all_students()
    return render_template('students.html', students=student_list)

@app.route('/student/<int:id>')
@login_required
def student_profile(id):
    student = database.get_student_by_id(id)
    return render_template('student_profile.html', student=student)

@app.route('/clear_students', methods=['POST'])
@login_required
def clear_students():
    database.clear_all_students()
    
    # Also delete all images from the known_faces folder so the AI stops recognizing them
    upload_folder = app.config['UPLOAD_FOLDER']
    if os.path.exists(upload_folder):
        for filename in os.listdir(upload_folder):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                file_path = os.path.join(upload_folder, filename)
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Error deleting file {file_path}: {e}")
                    
    # Also delete all daily attendance CSV files
    if os.path.exists('attendance'):
        for filename in os.listdir('attendance'):
            if filename.endswith('.csv'):
                try:
                    os.remove(os.path.join('attendance', filename))
                except Exception as e:
                    print(f"Error deleting attendance CSV {filename}: {e}")
                    
    # Also delete any generated reports
    if os.path.exists('reports'):
        for filename in os.listdir('reports'):
            if filename.endswith('.csv'):
                try:
                    os.remove(os.path.join('reports', filename))
                except Exception as e:
                    print(f"Error deleting report CSV {filename}: {e}")

    face_engine.load_known_faces()
    flash("All student records, photos, and historical attendance data have been successfully cleared.", "success")
    return redirect(url_for('students'))

@app.route('/bulk_import', methods=['POST'])
@login_required
def bulk_import():
    csv_file = request.files.get('csv_file')
    pdf_file = request.files.get('pdf_file')

    if not csv_file:
        return redirect(url_for('students'))

    # Process CSV/Excel to get student details
    students_data = []
    filename = secure_filename(csv_file.filename)
    
    try:
        if filename.endswith('.csv'):
            stream = csv_file.stream.read().decode('utf-8-sig').splitlines()
            if not stream:
                flash("Error: The uploaded file is empty.", "danger")
                return redirect(url_for('students'))
            try:
                dialect = csv.Sniffer().sniff(stream[0])
                reader = csv.reader(stream, dialect=dialect)
            except csv.Error:
                reader = csv.reader(stream)
            
            rows = list(reader)
            if not rows:
                flash("Error: The uploaded file has no data.", "danger")
                return redirect(url_for('students'))
                
            headers = [str(h).lower().strip() for h in rows[0]]
            has_headers = any('name' in h or 'roll' in h for h in headers)
            start_idx = 1 if has_headers else 0
            
            for row in rows[start_idx:]:
                if len(row) >= 2:
                    name, roll = str(row[0]).strip(), str(row[1]).strip()
                    if name and roll:
                        students_data.append({'name': name, 'roll': roll, 'phone': '', 'email': ''})
                        
        elif filename.endswith('.xlsx'):
            wb = openpyxl.load_workbook(csv_file)
            sheet = wb.active
            
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                flash("Error: The Excel file is empty.", "danger")
                return redirect(url_for('students'))
                
            # Scan first 5 rows to find a possible header row
            start_idx = 0
            for i, row in enumerate(rows[:5]):
                headers = [str(cell).lower().strip() if cell else '' for cell in row]
                if any('name' in h or 'roll' in h for h in headers):
                    start_idx = i + 1
                    break
                    
            for row in rows[start_idx:]:
                if len(row) >= 2:
                    name, roll = str(row[0] or '').strip(), str(row[1] or '').strip()
                    if name and name != 'None' and roll and roll != 'None':
                        students_data.append({'name': name, 'roll': roll, 'phone': '', 'email': ''})
                        
    except Exception as e:
        flash(f"Error parsing file: {str(e)}", 'danger')
        return redirect(url_for('students'))

    extracted_images = []
    if pdf_file and pdf_file.filename.endswith('.pdf'):
        try:
            pdf_bytes = pdf_file.read()
            doc = fitz.open("pdf", pdf_bytes)
            for page_num in range(len(doc)):
                page = doc[page_num]
                for img_index, img in enumerate(page.get_images(full=True)):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    extracted_images.append((base_image["image"], base_image["ext"]))
        except Exception as e:
            flash(f"Warning: Could not extract photos from PDF: {str(e)}", 'warning')

    added_names = []
    duplicate_count = 0
    
    # Pre-fetch existing roll numbers to avoid saving photos for duplicates
    existing_students = database.get_all_students()
    existing_rolls = {s['roll_number'] for s in existing_students}
    
    for idx, s in enumerate(students_data):
        if s['roll'] in existing_rolls:
            duplicate_count += 1
            continue
            
        filepath = ""
        if idx < len(extracted_images):
            image_bytes, image_ext = extracted_images[idx]
            p_filename = f"{s['name'].replace(' ', '_')}_{s['roll']}.{image_ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], p_filename)
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            
        success = database.add_student(s['name'], s['roll'], filepath, s['phone'], s['email'])
        if success:
            added_names.append(s['name'])
            
    face_engine.load_known_faces()
    
    if added_names:
        names_str = ", ".join(added_names)
        msg = f'Successfully added {len(added_names)} new student(s): {names_str}.'
        if duplicate_count > 0:
            msg += f' (Skipped {duplicate_count} duplicate records)'
        flash(msg, 'success')
    elif duplicate_count > 0:
        flash(f'Skipped {duplicate_count} duplicate student(s). All students in the file were already registered!', 'warning')
    else:
        flash('No valid students found to import.', 'danger')
        
    return redirect(url_for('students'))

@app.route('/analytics')
@login_required
def analytics():
    return render_template('analytics.html')

@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if request.method == 'POST':
        name = request.form['name']
        roll = request.form['roll']
        p_phone = request.form.get('p_phone', '')
        p_email = request.form.get('p_email', '')
        
        photo = request.files['photo']
        if photo:
            filename = f"{name.replace(' ', '_')}.jpg"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            photo.save(filepath)
            
            database.add_student(name, roll, filepath, p_phone, p_email)
            face_engine.load_known_faces() # Reload encodings
            return redirect(url_for('students'))
            
    return render_template('register.html')

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        for key, val in request.form.items():
            database.save_setting(key, val)
        return redirect(url_for('settings'))
    
    current_settings = database.get_settings()
    return render_template('settings.html', settings=current_settings)


# API Endpoints
@app.route('/api/live_feed')
def live_feed():
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route('/api/start_class', methods=['POST'])
@login_required
def start_class():
    global camera_requested, current_class_settings
    data = request.json
    
    current_class_settings = database.get_settings()
    duration = int(current_class_settings.get('lecture_duration', 60))
    subject = data.get('subject', 'General')
    
    voice_system.set_active(current_class_settings.get('voice_alerts', '1') == '1')
    
    camera_requested = True
    attendance_engine.start_class(duration, subject, session['user_id'])
    return jsonify({"status": "started", "duration": duration, "subject": subject})

@app.route('/api/end_class', methods=['POST'])
@login_required
def end_class():
    global camera_requested
    attendance_engine.end_class()
    voice_system.announce_class_end()
    camera_requested = False
    return jsonify({"status": "ended"})

@app.route('/api/alerts')
def get_alerts():
    current_time = time.time()
    present_students = []
    checked_in_students = []
    checked_out_students = []
    if attendance_engine.class_active:
        for name, data in attendance_engine.presence_tracking.items():
            if current_time - data['last_seen'] < 15:
                present_students.append(name)
            if data.get('checked_in'):
                checked_in_students.append(name)
            if data.get('checked_out'):
                checked_out_students.append(name)
                
    return jsonify({
        "alerts": latest_alerts[::-1][:10], # Last 10 alerts
        "present_students": present_students,
        "checked_in": checked_in_students,
        "checked_out": checked_out_students,
        "timer": attendance_engine.get_time_remaining(),
        "is_active": attendance_engine.class_active
    })

@app.route('/api/export_pdf', methods=['POST'])
def export_pdf():
    records = database.get_today_attendance()
    date_str = datetime.now().strftime("%Y-%m-%d")
    filepath = report_generator.generate_pdf_report(records, attendance_engine.subject or 'All', date_str)
    return send_file(filepath, as_attachment=True)

@app.route('/api/export_excel', methods=['POST'])
def export_excel():
    date_today = datetime.now().strftime("%Y-%m-%d")
    filepath = f"attendance/Attendance_{date_today}.csv"
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({"error": "No data today"}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

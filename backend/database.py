import sqlite3
import os
from datetime import datetime

DB_PATH = 'database/attendance.db'

def get_db_connection():
    os.makedirs('database', exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database structure."""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Students table
    c.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll_number TEXT UNIQUE NOT NULL,
            photo_path TEXT,
            parent_phone TEXT,
            parent_email TEXT,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Attendance table
    c.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            user_id INTEGER,
            date TEXT,
            subject TEXT,
            status TEXT,
            arrival_time TEXT,
            presence_seconds INTEGER,
            presence_percentage REAL,
            behaviour_score REAL,
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    # Behaviour logs table
    c.execute('''
        CREATE TABLE IF NOT EXISTS behaviour_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            date TEXT,
            subject TEXT,
            behaviour_type TEXT,
            timestamp TEXT,
            alert_given INTEGER,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    ''')

    # Settings table
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            value TEXT
        )
    ''')
    
    # Insert default settings if not exists
    default_settings = {
        'lecture_duration': '60',
        'attendance_threshold': '75',
        'voice_alerts': '1',
        'alert_sensitivity': 'Medium',
        'detect_sleep': '1',
        'detect_talk': '1',
        'detect_seat': '1',
        'detect_phone': '1',
        'parent_notifications': '0',
        'twilio_sid': '',
        'twilio_token': '',
        'twilio_from': '',
        'smtp_email': '',
        'smtp_password': ''
    }
    for k, v in default_settings.items():
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (k, v))

    # Subjects table
    c.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_name TEXT UNIQUE NOT NULL,
            teacher_name TEXT,
            schedule TEXT
        )
    ''')
    
    # Users table for login
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'teacher'
        )
    ''')
    
    # Insert a default admin user if not exists (username: admin, password: admin)
    c.execute('INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)', ('admin', 'admin', 'admin'))

    conn.commit()
    conn.close()

def get_all_students():
    conn = get_db_connection()
    students = conn.execute('SELECT * FROM students').fetchall()
    conn.close()
    return [dict(s) for s in students]

def get_student_by_roll(roll):
    conn = get_db_connection()
    student = conn.execute('SELECT * FROM students WHERE roll_number = ?', (roll,)).fetchone()
    conn.close()
    return dict(student) if student else None

def get_student_by_id(id):
    conn = get_db_connection()
    student = conn.execute('SELECT * FROM students WHERE id = ?', (id,)).fetchone()
    conn.close()
    return dict(student) if student else None

def add_student(name, roll_number, photo_path, parent_phone, parent_email):
    try:
        conn = get_db_connection()
        conn.execute('INSERT INTO students (name, roll_number, photo_path, parent_phone, parent_email) VALUES (?, ?, ?, ?, ?)',
                     (name, roll_number, photo_path, parent_phone, parent_email))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def clear_all_students():
    conn = get_db_connection()
    conn.execute('DELETE FROM behaviour_logs')
    conn.execute('DELETE FROM attendance')
    conn.execute('DELETE FROM students')
    conn.commit()
    conn.close()

def get_settings():
    conn = get_db_connection()
    settings_rows = conn.execute('SELECT key, value FROM settings').fetchall()
    conn.close()
    return {row['key']: row['value'] for row in settings_rows}

def save_setting(key, value):
    conn = get_db_connection()
    conn.execute('UPDATE settings SET value = ? WHERE key = ?', (str(value), key))
    conn.commit()
    conn.close()

def save_attendance_record(student_id, user_id, date, subject, status, arrival_time, presence_seconds, presence_percentage, behaviour_score):
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO attendance (student_id, user_id, date, subject, status, arrival_time, presence_seconds, presence_percentage, behaviour_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (student_id, user_id, date, subject, status, arrival_time, presence_seconds, presence_percentage, behaviour_score))
    conn.commit()
    conn.close()

def log_behaviour(student_id, date, subject, behaviour_type, timestamp, alert_given=1):
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO behaviour_logs (student_id, date, subject, behaviour_type, timestamp, alert_given)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (student_id, date, subject, behaviour_type, timestamp, alert_given))
    conn.commit()
    conn.close()
    
def get_today_attendance(user_id=None):
    date_today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db_connection()
    # Use subquery to get only the LATEST record for each student per subject today
    query = '''
        SELECT a.*, s.name, s.roll_number, s.photo_path 
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE a.id IN (
            SELECT MAX(id) 
            FROM attendance 
            WHERE date = ?
            GROUP BY student_id, subject
        )
    '''
    params = [date_today]
    if user_id:
        query += ' AND a.user_id = ?'
        params.append(user_id)
        
    records = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in records]

def get_user(username):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return dict(user) if user else None

def add_user(username, password, role='teacher'):
    try:
        conn = get_db_connection()
        conn.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', (username, password, role))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False

def delete_attendance_record(record_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM attendance WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()

def delete_multiple_attendance_records(record_ids):
    if not record_ids:
        return
    conn = get_db_connection()
    placeholders = ','.join(['?'] * len(record_ids))
    conn.execute(f'DELETE FROM attendance WHERE id IN ({placeholders})', tuple(record_ids))
    conn.commit()
    conn.close()

def clear_today_attendance(user_id=None):
    date_today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db_connection()
    if user_id:
        conn.execute('DELETE FROM attendance WHERE date = ? AND user_id = ?', (date_today, user_id))
    else:
        conn.execute('DELETE FROM attendance WHERE date = ?', (date_today,))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized.")

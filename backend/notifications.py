import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from twilio.rest import Client
import database

def send_whatsapp_alert(to_number, message_body):
    settings = database.get_settings()
    sid = settings.get('twilio_sid')
    token = settings.get('twilio_token')
    from_number = settings.get('twilio_from') # e.g. whatsapp:+14155238886
    
    if not sid or not token or not from_number:
        print("Twilio settings missing. Cannot send WhatsApp.")
        return
        
    try:
        client = Client(sid, token)
        message = client.messages.create(
            from_=from_number,
            body=message_body,
            to=f"whatsapp:{to_number}"
        )
        print(f"WhatsApp sent: {message.sid}")
    except Exception as e:
        print(f"Twilio Error: {e}")

def send_email_alert(to_email, subject, html_content):
    settings = database.get_settings()
    sender_email = settings.get('smtp_email')
    password = settings.get('smtp_password')
    
    if not sender_email or not password:
        print("SMTP settings missing. Cannot send email.")
        return
        
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(html_content, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, password)
        server.send_message(msg)
        server.quit()
        print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"SMTP Error: {e}")

def notify_absence(student_name, parent_phone, parent_email, subject, date):
    msg = f"Dear Parent, your child {student_name} was absent in {subject} class on {date}."
    if parent_phone:
        send_whatsapp_alert(parent_phone, msg)
    if parent_email:
        html = f"<h3>Attendance Alert</h3><p>Dear Parent,</p><p>Your child <b>{student_name}</b> was marked <b>ABSENT</b> in <b>{subject}</b> class on {date}.</p>"
        send_email_alert(parent_email, f"Absence Alert: {student_name}", html)

def notify_low_attendance(student_name, parent_phone, parent_email, subject, percentage):
    msg = f"Warning: {student_name}'s attendance in {subject} has fallen to {percentage}%. Minimum required is 75%."
    if parent_phone:
        send_whatsapp_alert(parent_phone, msg)
    if parent_email:
        html = f"<h3>Attendance Warning</h3><p>Dear Parent,</p><p>Warning: <b>{student_name}</b>'s attendance in {subject} has fallen to <b>{percentage}%</b>. Minimum required is 75%.</p>"
        send_email_alert(parent_email, f"Low Attendance Warning: {student_name}", html)

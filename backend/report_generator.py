import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from datetime import datetime

def generate_pdf_report(records, subject, date_str):
    os.makedirs('reports', exist_ok=True)
    filepath = f"reports/Attendance_Report_{subject}_{date_str}.pdf"
    
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    # Title
    title = Paragraph(f"Attendance Report &mdash; {subject} &mdash; {date_str}", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))
    
    # Summary
    total = len(records)
    present = sum(1 for r in records if r['status'] == 'Present')
    absent = sum(1 for r in records if r['status'] == 'Absent')
    late = sum(1 for r in records if r['status'] == 'Late')
    
    summary_text = f"Total Students: {total} | Present: {present} | Absent: {absent} | Late: {late}"
    elements.append(Paragraph(summary_text, styles['Normal']))
    elements.append(Spacer(1, 12))
    
    # Table Data
    data = [['Roll No', 'Name', 'Status', 'Arrival Time', 'Presence %', 'Score']]
    for r in records:
        data.append([
            r['roll_number'],
            r['name'],
            r['status'],
            r['arrival_time'],
            f"{r['presence_percentage']:.1f}%",
            str(r['behaviour_score'])
        ])
        
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 24))
    
    # Risk Section
    elements.append(Paragraph("Students at Risk (Attendance < 75%)", styles['Heading2']))
    risk_data = [['Roll No', 'Name', 'Presence %']]
    for r in records:
        if r['presence_percentage'] < 75.0:
            risk_data.append([r['roll_number'], r['name'], f"{r['presence_percentage']:.1f}%"])
            
    if len(risk_data) > 1:
        risk_table = Table(risk_data)
        risk_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkred),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(risk_table)
    else:
        elements.append(Paragraph("None", styles['Normal']))
        
    doc.build(elements)
    return filepath

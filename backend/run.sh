#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Please wait for installation to finish."
    exit 1
fi
source venv/bin/activate
echo "Starting Smart Classroom Face Recognition System..."
python app.py

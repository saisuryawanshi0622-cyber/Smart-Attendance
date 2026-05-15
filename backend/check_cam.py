import cv2
cap = cv2.VideoCapture(0)
if cap.isOpened():
    print("SUCCESS: Camera opened")
    cap.release()
else:
    print("FAILED: Camera not found or busy")

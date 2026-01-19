import cv2
import face_recognition
import mysql.connector
from datetime import datetime
import os
import pickle
import winsound
import time
import numpy as np
import math
from PIL import Image
import ctypes

# ---------------- CONFIG ----------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
KNOWN_FACES_DIR = os.path.join(BASE_DIR, "../known_faces")
ENCODINGS_FILE = os.path.join(KNOWN_FACES_DIR, "face_encodings.pkl")

# PNG you uploaded
ICON_PNG = os.path.join(BASE_DIR, "../static/images/e819011f-8056-4dd1-a237-8388cf21d68a.png")
# Converted ICO path
ICON_ICO = os.path.join(BASE_DIR, "../static/images/camera_icon.ico")

# Convert PNG to ICO if not exists
if not os.path.exists(ICON_ICO) and os.path.exists(ICON_PNG):
    img = Image.open(ICON_PNG)
    img.save(ICON_ICO, format='ICO', sizes=[(32,32)])

MODE = "IN"

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "face_att"
}

# ---------------- TIME RULES ----------------
MORNING_START = 8
MORNING_END = 12
AFTERNOON_START = 13
AFTERNOON_END = 17

# ---------------- UI CONFIG ----------------
LOG_PANEL_WIDTH = 360
MAX_LOGS = 12
FRAME_WIDTH = 800
FRAME_HEIGHT = 600
FONT = cv2.FONT_HERSHEY_SIMPLEX

# ---------------- BEEP ----------------
def beep_in(): winsound.Beep(1200, 180)
def beep_out(): winsound.Beep(900, 180)
def beep_error(): winsound.Beep(400, 350)

# ---------------- SCAN COOLDOWN ----------------
SCAN_COOLDOWN = 5
last_scan_time = {}

# ---------------- LOG STORAGE ----------------
logs = []

def add_log(message, color):
    timestamp = datetime.now().strftime("%H:%M:%S")
    logs.append((f"[{timestamp}] {message}", color))
    if len(logs) > MAX_LOGS:
        logs.pop(0)

# ---------------- DATABASE ----------------
def get_user_info(name):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT users.id, sections.name
        FROM users
        LEFT JOIN sections ON users.section_id = sections.id
        WHERE users.name = %s
    """, (name,))
    row = cursor.fetchone()
    conn.close()
    return row if row else (None, None)

def mark_attendance(name):
    now_ts = time.time()
    if name in last_scan_time and now_ts - last_scan_time[name] < SCAN_COOLDOWN:
        return None, False

    user_id, section = get_user_info(name)
    if not user_id:
        beep_error()
        add_log(f"{name} not registered", (0, 0, 255))
        return None, False

    now = datetime.now()
    today = now.date()
    current_time = now.strftime("%H:%M:%S")
    hour = now.hour

    if MORNING_START <= hour < MORNING_END:
        in_col, out_col = "morning_in", "morning_out"
    elif AFTERNOON_START <= hour < AFTERNOON_END:
        in_col, out_col = "afternoon_in", "afternoon_out"
    else:
        beep_error()
        add_log(f"{name} outside allowed hours", (0, 0, 255))
        return section, False

    target_col = in_col if MODE == "IN" else out_col

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT id, {target_col} FROM attendance WHERE user_id=%s AND date=%s",
        (user_id, today)
    )
    row = cursor.fetchone()

    success = False
    if not row:
        cursor.execute(
            f"INSERT INTO attendance (user_id, date, {target_col}) VALUES (%s,%s,%s)",
            (user_id, today, current_time)
        )
        success = True
    else:
        if row[1] is None:
            cursor.execute(
                f"UPDATE attendance SET {target_col}=%s WHERE id=%s",
                (current_time, row[0])
            )
            success = True
        else:
            beep_error()
            add_log(f"{name} already {MODE}", (0, 0, 255))

    conn.commit()
    conn.close()

    if success:
        last_scan_time[name] = now_ts
        beep_in() if MODE == "IN" else beep_out()
        add_log(f"{name} {MODE} | {section}", (0, 255, 0))
        return section, True

    return section, False

# ---------------- LOAD ENCODINGS ----------------
def load_encodings():
    if not os.path.exists(ENCODINGS_FILE):
        return {"encodings": [], "names": []}
    with open(ENCODINGS_FILE, "rb") as f:
        return pickle.load(f)

data = load_encodings()
known_files = set(os.listdir(KNOWN_FACES_DIR))

# ---------------- CAMERA ----------------
video = cv2.VideoCapture(0)
video.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
video.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

# ---------------- WINDOW ----------------
WINDOW_NAME = "Face Attendance - Modern Kiosk"
cv2.namedWindow(WINDOW_NAME)

# Set Windows icon
if os.path.exists(ICON_ICO):
    hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_NAME)
    if hwnd:
        ctypes.windll.user32.SendMessageW(hwnd, 0x80, 0, ICON_ICO)  # WM_SETICON

# ---------------- HELPER FUNCTIONS ----------------
def draw_pulsing_box(img, pt1, pt2, color, pulse_phase, thickness=3):
    x1, y1 = pt1
    x2, y2 = pt2
    pulse = int(2 + 2 * math.sin(pulse_phase))
    c = tuple(min(255, max(0, int(c + 50 * math.sin(pulse_phase)))) for c in color)
    cv2.rectangle(img, (x1, y1), (x2, y2), c, thickness + pulse)

# ---------------- MAIN LOOP ----------------
pulse_phase = 0
while True:
    ret, frame = video.read()
    if not ret:
        break

    frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
    h, w, _ = frame.shape

    # ---------------- LOG PANEL ----------------
    log_panel = np.zeros((h, LOG_PANEL_WIDTH, 3), dtype=np.uint8)
    for i in range(h):
        color = (30, 30 + i//20, 60 + i//10)
        log_panel[i, :] = color

    # Reload encodings if needed
    current_files = set(os.listdir(KNOWN_FACES_DIR))
    if current_files != known_files:
        data = load_encodings()
        known_files = current_files
        add_log("Encodings reloaded", (255, 255, 0))

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(rgb)
    encodings = face_recognition.face_encodings(rgb, locations)

    for (top, right, bottom, left), face_encoding in zip(locations, encodings):
        name = "Unknown"
        section = ""
        color = (0, 0, 255)

        if data["encodings"]:
            distances = face_recognition.face_distance(data["encodings"], face_encoding)
            best = distances.argmin()
            if distances[best] < 0.5:
                name = data["names"][best]
                section, success = mark_attendance(name)
                if success:
                    color = (0, 255, 0)

        label = f"{name} | {section}" if section else name
        draw_pulsing_box(frame, (left, top), (right, bottom), color, pulse_phase)
        cv2.putText(frame, label, (left, top - 10), FONT, 0.8, color, 2, cv2.LINE_AA)

    # ---------------- FACE GUIDE CIRCLE ----------------
    pulse_radius = 80 + int(10 * math.sin(pulse_phase))
    overlay = frame.copy()
    center = (FRAME_WIDTH // 2, FRAME_HEIGHT // 2)
    cv2.circle(overlay, center, pulse_radius, (100, 150, 255), 3)
    alpha = 0.25
    frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)

    # ---------------- DRAW LOGS (STATIC) ----------------
    cv2.putText(log_panel, "SCAN LOGS", (10, 30), FONT, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    y = 65
    for msg, color in logs[::-1]:
        cv2.putText(log_panel, msg, (10, y), FONT, 0.45, color, 1, cv2.LINE_AA)
        y += 28

    # ---------------- COMBINE FRAME + LOG PANEL ----------------
    combined = np.hstack((frame, log_panel))

    # ---------------- STATUS BAR ----------------
    now_time = datetime.now().strftime("%I:%M:%S %p")
    cv2.putText(combined, "(I=IN, O=OUT, Q=QUIT)", (10, 35), FONT, 0.7, (0, 255, 255), 2, cv2.LINE_AA)
    mode_text = f"{MODE} | {now_time}"
    (text_width, _), _ = cv2.getTextSize(mode_text, FONT, 0.9, 2)
    center_x = FRAME_WIDTH // 2 - text_width // 2
    cv2.putText(combined, mode_text, (center_x, 35), FONT, 0.9, (0, 255, 0), 2, cv2.LINE_AA)
    faces_text = f"Faces: {len(locations)}"
    (text_width_faces, _), _ = cv2.getTextSize(faces_text, FONT, 0.8, 2)
    cv2.putText(combined, faces_text, (FRAME_WIDTH - text_width_faces - 10, 35), FONT, 0.8, (255, 255, 0), 2, cv2.LINE_AA)

    pulse_phase += 0.1
    cv2.imshow(WINDOW_NAME, combined)

    key = cv2.waitKey(1) & 0xFF
    if key == ord("i"):
        MODE = "IN"
        add_log("Mode switched to IN", (0, 255, 255))
    elif key == ord("o"):
        MODE = "OUT"
        add_log("Mode switched to OUT", (0, 255, 255))
    elif key == ord("q"):
        break

video.release()
cv2.destroyAllWindows()

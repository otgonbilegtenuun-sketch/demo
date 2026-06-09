"""
Test scenario: record a short webcam clip of yourself, configure a seat map,
upload in batch mode, and verify attendance was marked.

Usage:
    python apps/edge-agent/test_scenario.py

Prerequisites:
    - Server running on http://localhost:8080  (python run.py)
    - At least one student enrolled via /enroll
    - A webcam connected

Steps this script performs:
    1. Records 20 seconds of webcam video → test_clip.mp4
    2. Logs in as admin
    3. Lists enrolled students
    4. Configures a seat map covering the full frame, assigned to the first student
    5. Uploads the video in batch mode
    6. Polls until processing completes
    7. Checks /api/attendance/today and /api/seats/occupancy
"""

import cv2
import json
import os
import sys
import time
import requests

BASE = "http://localhost:8080"
CLIP_PATH = os.path.join(os.path.dirname(__file__), "test_clip.mp4")
RECORD_SECONDS = 120  # 2 minutes — seat attendance needs 90s of occupancy


def record_webcam(path: str, seconds: int):
    print(f"\n[1/7] Recording {seconds}s webcam video...")
    print("      Sit in front of your camera like a student at a desk.\n")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Cannot open webcam. Plug one in and retry.")
        sys.exit(1)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(path, fourcc, fps, (w, h))
    start = time.time()
    frames = 0
    while time.time() - start < seconds:
        ret, frame = cap.read()
        if not ret:
            break
        out.write(frame)
        frames += 1
        remaining = seconds - int(time.time() - start)
        cv2.putText(frame, f"Recording... {remaining}s left",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        cv2.imshow("Test Recording (press Q to stop early)", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cap.release()
    out.release()
    cv2.destroyAllWindows()
    print(f"      Saved {frames} frames ({w}x{h}) to {path}\n")
    return w, h


def login():
    print("[2/7] Logging in as admin...")
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"username": "admin", "password": "admin123"})
    r.raise_for_status()
    token = r.json()["token"]
    print(f"      Got token: {token[:20]}...\n")
    return {"Authorization": f"Bearer {token}"}


def list_students(headers):
    print("[3/7] Checking enrolled students...")
    r = requests.get(f"{BASE}/api/students", headers=headers)
    r.raise_for_status()
    students = r.json()
    if not students:
        print("      ERROR: No students enrolled!")
        print("      Go to http://localhost:8080/enroll and add at least one student first.")
        sys.exit(1)
    for s in students:
        print(f"      id={s['id']}  name={s['name']}")
    print()
    return students


def setup_seat_map(headers, student, frame_w, frame_h):
    print(f"[4/7] Setting up seat map: full frame → {student['name']}...")
    margin = 50
    seat = {
        "student_id": student["id"],
        "x1": margin, "y1": margin,
        "x2": frame_w - margin, "y2": frame_h - margin,
    }
    body = {"class_name": "Class A", "seats": [seat]}
    r = requests.post(f"{BASE}/api/seats", headers=headers, json=body)
    r.raise_for_status()
    result = r.json()
    print(f"      Saved {result['saved']} seat(s)\n")
    return result


def upload_batch(headers, path):
    print("[5/7] Uploading video in batch mode...")
    with open(path, "rb") as f:
        r = requests.post(
            f"{BASE}/api/video/upload?batch=true",
            headers=headers,
            files={"file": ("test_clip.mp4", f, "video/mp4")},
        )
    r.raise_for_status()
    result = r.json()
    print(f"      Status: {result['status']}, batch={result['batch']}\n")
    return result


def wait_for_completion(headers, timeout=120):
    print("[6/7] Waiting for batch processing to finish...")
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(f"{BASE}/api/camera/status", headers=headers)
        r.raise_for_status()
        status = r.json()
        bp = status.get("batch", {})
        if not status.get("running", False):
            print(f"      Done! Processed {bp.get('current_frame', '?')} frames "
                  f"in {bp.get('elapsed_s', '?')}s\n")
            return True
        pct = bp.get("percent", 0)
        fps = bp.get("fps_actual", 0)
        print(f"      {pct:.1f}% — {bp.get('current_frame',0)}/{bp.get('total_frames',0)} "
              f"frames @ {fps:.1f} fps", end="\r")
        time.sleep(2)
    print("\n      TIMEOUT waiting for batch to finish")
    return False


def check_results(headers, student):
    print("[7/7] Checking results...\n")

    # Attendance
    r = requests.get(f"{BASE}/api/attendance/today", headers=headers)
    r.raise_for_status()
    attendance = r.json()
    print("  ATTENDANCE TODAY:")
    if not attendance:
        print("    (none)")
    for a in attendance:
        present = "PRESENT" if a.get("total_frames", 0) > 0 else "absent"
        print(f"    {a.get('student_name', a.get('student_id'))}  "
              f"— {present}  "
              f"(frames: {a.get('total_frames', 0)}, "
              f"attention: {a.get('attention_frames', 0)})")

    found = any(
        a.get("student_id") == student["id"] and a.get("total_frames", 0) > 0
        for a in attendance
    )

    # Seat occupancy
    r2 = requests.get(f"{BASE}/api/seats/occupancy", headers=headers)
    r2.raise_for_status()
    occupancy = r2.json()
    print("\n  SEAT OCCUPANCY:")
    if not occupancy:
        print("    (no active occupancy — normal after batch completes)")
    for o in occupancy:
        print(f"    seat #{o['seat_id']}: {o['occupied_for_s']}s "
              f"present={o['considered_present']} "
              f"attendance_marked={o.get('attendance_marked', '?')}")

    print("\n" + "=" * 50)
    if found:
        print(f"  SUCCESS: {student['name']} was marked present!")
    else:
        print(f"  NOTE: {student['name']} not in attendance yet.")
        print("  This can happen if:")
        print("    - The video was too short (need 90s of seat occupancy)")
        print("    - YOLO didn't detect a person (try a longer/clearer video)")
        print("    - Face recognition matched instead (check attendance list)")
    print("=" * 50)


def main():
    print("=" * 50)
    print("  MERGEN AI — Test Scenario")
    print("  Seat-Based Attendance from Webcam")
    print("=" * 50)

    # Step 1: Record
    frame_w, frame_h = record_webcam(CLIP_PATH, RECORD_SECONDS)

    # Step 2: Login
    headers = login()

    # Step 3: List students
    students = list_students(headers)
    student = students[0]
    print(f"  Using student: {student['name']} (id={student['id']})\n")

    # Step 4: Seat map
    setup_seat_map(headers, student, frame_w, frame_h)

    # Step 5: Upload
    upload_batch(headers, CLIP_PATH)

    # Step 6: Wait
    wait_for_completion(headers)

    # Step 7: Results
    check_results(headers, student)

    # Cleanup
    try:
        os.remove(CLIP_PATH)
    except OSError:
        pass


if __name__ == "__main__":
    main()

# AttendAI – Face Recognition Attendance System

This is the redesigned version of the uploaded Flask project. The existing SQLite database and face-recognition workflow are retained. The `.venv` folder is intentionally not included; virtual environments should be recreated on the computer where the project will run.

## What's included

- New responsive navy / blue / cyan interface
- Separate Student, Lecturer and Admin login portals
- Student dashboard with attendance history
- Lecturer dashboard with live face scanner, attendance date filter and CSV export
- Admin dashboard with system overview, student directory and lecturer account management
- Existing SQLite student and attendance data retained in `data/attendance.db`
- Admin account table is created automatically without deleting existing tables or records

## Requirements

Use **Python 3.11 (64-bit)** on Windows. The uploaded project includes a dlib wheel built for CPython 3.11. Python 3.14 is not compatible with that wheel.

## Setup on Windows

1. Extract this ZIP file.
2. Open the extracted `ai_attendance_professional` folder in VS Code.
3. Open Terminal → New Terminal.
4. Create a virtual environment:

   ```powershell
   py -3.11 -m venv .venv
   ```

5. Activate it:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

6. Install the included dlib wheel:

   ```powershell
   pip install .\dlib-19.24.1-cp311-cp311-win_amd64.whl
   ```

7. Install the remaining packages:

   ```powershell
   pip install -r requirements.txt
   ```

8. Start the application:

   ```powershell
   python app.py
   ```

9. Open `http://127.0.0.1:5000` in your browser. Allow camera access when asked.

## Initial demo accounts

- Admin: `admin` / `admin123`
- Lecturer: `lecturer` / `lecturer123`

Change both default passwords after first sign-in. The Admin dashboard has an account settings panel. The Lecturer dashboard also has account settings.

## Important notes

- The application uses SQLite, not browser Local Storage.
- The database file is `data/attendance.db`. Keep a backup before making changes.
- Camera access works on `localhost` or an HTTPS website.
- Attendance is limited to one record per student per date, matching the original database rule.
- The displayed attendance percentage is today's present students divided by registered students. There is no timetable / class-session table in the current database, so it is not a full semester attendance percentage.
- Before public deployment, set a strong `SECRET_KEY` environment variable and add CSRF protection, stronger password rules, and appropriate privacy/consent controls for face data.

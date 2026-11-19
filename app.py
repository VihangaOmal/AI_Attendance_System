
import os
import csv
import base64
import json
import sqlite3
from io import StringIO
from datetime import datetime
from functools import wraps

import cv2
import face_recognition
import numpy as np

from flask import (
    Flask, Response, render_template, request, redirect,
    url_for, session, jsonify, flash
)

from werkzeug.security import generate_password_hash, check_password_hash


# ---------------------------------
# APPLICATION CONFIGURATION
# ---------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "data", "attendance.db")

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-before-deployment"
)

os.makedirs(os.path.dirname(DB), exist_ok=True)


# ---------------------------------
# DATABASE CONNECTION
# ---------------------------------

def db():
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    return connection


# ---------------------------------
# DATABASE INITIALIZATION
# ---------------------------------

def init_db():

    connection = db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS students(
            id INTEGER PRIMARY KEY,
            student_id TEXT UNIQUE,
            name TEXT NOT NULL,
            email TEXT,
            password_hash TEXT,
            face_encoding TEXT,
            created_at TEXT
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS lecturers(
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password_hash TEXT
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS admins(
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password_hash TEXT
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS attendance(
            id INTEGER PRIMARY KEY,
            student_id TEXT,
            name TEXT,
            date TEXT,
            time TEXT,
            status TEXT,
            UNIQUE(student_id, date)
        )
    """)

    # Default lecturer account
    if not connection.execute(
        "SELECT 1 FROM lecturers WHERE username=?",
        ("lecturer",)
    ).fetchone():

        connection.execute(
            """
            INSERT INTO lecturers(username, password_hash)
            VALUES(?, ?)
            """,
            (
                "lecturer",
                generate_password_hash("lecturer123")
            )
        )

    # Default admin account
    if not connection.execute(
        "SELECT 1 FROM admins WHERE username=?",
        ("admin",)
    ).fetchone():

        connection.execute(
            """
            INSERT INTO admins(username, password_hash)
            VALUES(?, ?)
            """,
            (
                "admin",
                generate_password_hash("admin123")
            )
        )

    connection.commit()
    connection.close()


# ---------------------------------
# ROLE AUTHENTICATION
# ---------------------------------

def role_required(role):

    def decorator(function):

        @wraps(function)
        def wrapper(*args, **kwargs):

            if session.get("role") != role:

                flash(
                    "Please sign in to access that page.",
                    "error"
                )

                return redirect(url_for("home"))

            return function(*args, **kwargs)

        return wrapper

    return decorator


# ---------------------------------
# IMAGE PROCESSING
# ---------------------------------

def img(data):

    try:

        if not data:
            return None

        if "," in data:
            data = data.split(",", 1)[1]

        raw = base64.b64decode(data)

        array = np.frombuffer(raw, dtype=np.uint8)

        frame = cv2.imdecode(
            array,
            cv2.IMREAD_COLOR
        )

        if frame is None:
            return None

        return np.ascontiguousarray(
            frame,
            dtype=np.uint8
        )

    except Exception as error:

        print("Image decoding error:", error)

        return None


# ---------------------------------
# FACE ENCODING
# ---------------------------------

def encoding(frame):

    if frame is None:
        return None, 0

    try:

        frame = np.asarray(frame)

        if frame.dtype != np.uint8:

            frame = np.clip(
                frame,
                0,
                255
            ).astype(np.uint8)

        if len(frame.shape) == 2:

            frame = cv2.cvtColor(
                frame,
                cv2.COLOR_GRAY2BGR
            )

        elif len(frame.shape) == 3 and frame.shape[2] == 4:

            frame = cv2.cvtColor(
                frame,
                cv2.COLOR_BGRA2BGR
            )

        if len(frame.shape) != 3 or frame.shape[2] != 3:
            return None, 0

        frame = np.ascontiguousarray(
            frame,
            dtype=np.uint8
        )

        rgb = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )

        rgb = np.ascontiguousarray(
            rgb,
            dtype=np.uint8
        )

        locations = face_recognition.face_locations(
            rgb,
            model="hog"
        )

        if len(locations) != 1:
            return None, len(locations)

        encodings = face_recognition.face_encodings(
            rgb,
            known_face_locations=locations
        )

        return (encodings[0], 1) if encodings else (None, 0)

    except Exception as error:

        print("Face encoding error:", error)

        return None, 0


# ---------------------------------
# HOME PAGE
# ---------------------------------

@app.route("/")
def home():

    return render_template("index.html")


# ---------------------------------
# ABOUT PAGE
# ---------------------------------

@app.route("/about")
def about():

    return render_template("about.html")


# ---------------------------------
# SERVICES PAGE
# ---------------------------------

@app.route("/services")
def services():

    return render_template("services.html")


# ---------------------------------
# STUDENT REGISTRATION
# ---------------------------------

@app.route("/student/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        student_id = request.form.get(
            "student_id", ""
        ).strip()

        name = request.form.get(
            "name", ""
        ).strip()

        email = request.form.get(
            "email", ""
        ).strip()

        password = request.form.get(
            "password", ""
        )

        image_data = request.form.get(
            "image", ""
        )

        if (
            not student_id
            or not name
            or len(password) < 6
            or not image_data
        ):

            return jsonify(
                ok=False,
                message=(
                    "Complete all required fields and capture your face. "
                    "Password must be at least 6 characters."
                )
            )

        connection = db()

        existing = connection.execute(
            """
            SELECT 1 FROM students
            WHERE student_id=?
            """,
            (student_id,)
        ).fetchone()

        if existing:

            connection.close()

            return jsonify(
                ok=False,
                message=(
                    "Student ID already registered. "
                    "Please use Student Login."
                )
            )

        frame = img(image_data)

        if frame is None:

            connection.close()

            return jsonify(
                ok=False,
                message=(
                    "Invalid image. Please capture your face again."
                )
            )

        enc, count = encoding(frame)

        if enc is None:

            connection.close()

            return jsonify(
                ok=False,
                message=f"Exactly one face is required. Detected {count}."
            )

        students = connection.execute(
            """
            SELECT student_id, name, face_encoding
            FROM students
            """
        ).fetchall()

        for student in students:

            try:

                old_encoding = np.asarray(
                    json.loads(student["face_encoding"]),
                    dtype=np.float64
                )

                if face_recognition.compare_faces(
                    [old_encoding],
                    enc,
                    tolerance=0.45
                )[0]:

                    connection.close()

                    return jsonify(
                        ok=False,
                        message=(
                            f"This face is already registered as "
                            f"{student['student_id']}. Use Student Login."
                        )
                    )

            except Exception as error:

                print(
                    "Existing face check error:",
                    error
                )

        connection.execute(
            """
            INSERT INTO students(
                student_id,
                name,
                email,
                password_hash,
                face_encoding,
                created_at
            )
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                student_id,
                name,
                email,
                generate_password_hash(password),
                json.dumps(enc.tolist()),
                datetime.now().isoformat(timespec="seconds")
            )
        )

        connection.commit()
        connection.close()

        return jsonify(
            ok=True,
            message=(
                "Registration successful. "
                "You can now sign in."
            )
        )

    return render_template("register.html")


# ---------------------------------
# STUDENT LOGIN
# ---------------------------------

@app.route("/student/login", methods=["GET", "POST"])
def slogin():

    if request.method == "POST":

        student_id = request.form.get(
            "student_id", ""
        ).strip()

        password = request.form.get(
            "password", ""
        )

        connection = db()

        student = connection.execute(
            """
            SELECT * FROM students
            WHERE student_id=?
            """,
            (student_id,)
        ).fetchone()

        connection.close()

        if student and check_password_hash(
            student["password_hash"],
            password
        ):

            session.clear()

            session.update(
                role="student",
                student_id=student_id,
                name=student["name"]
            )

            return redirect(
                url_for("sdash")
            )

        flash(
            "Invalid Student ID or password.",
            "error"
        )

    return render_template(
        "login.html",
        kind="Student"
    )


# ---------------------------------
# STUDENT DASHBOARD
# ---------------------------------

@app.route("/student/dashboard")
@role_required("student")
def sdash():

    connection = db()

    rows = connection.execute(
        """
        SELECT date, time, status
        FROM attendance
        WHERE student_id=?
        ORDER BY date DESC, time DESC
        """,
        (session["student_id"],)
    ).fetchall()

    student = connection.execute(
        """
        SELECT email, created_at
        FROM students
        WHERE student_id=?
        """,
        (session["student_id"],)
    ).fetchone()

    connection.close()

    return render_template(
        "student.html",
        rows=rows,
        student=student
    )


# ---------------------------------
# LECTURER LOGIN
# ---------------------------------

@app.route("/lecturer/login", methods=["GET", "POST"])
def llogin():

    if request.method == "POST":

        username = request.form.get(
            "username", ""
        ).strip()

        password = request.form.get(
            "password", ""
        )

        connection = db()

        lecturer = connection.execute(
            """
            SELECT * FROM lecturers
            WHERE username=?
            """,
            (username,)
        ).fetchone()

        connection.close()

        if lecturer and check_password_hash(
            lecturer["password_hash"],
            password
        ):

            session.clear()

            session.update(
                role="lecturer",
                username=username
            )

            return redirect(
                url_for("ldash")
            )

        flash(
            "Invalid lecturer username or password.",
            "error"
        )

    return render_template(
        "login.html",
        kind="Lecturer"
    )


# ---------------------------------
# LECTURER DASHBOARD
# ---------------------------------

@app.route("/lecturer/dashboard")
@role_required("lecturer")
def ldash():

    selected_date = request.args.get(
        "date", ""
    ).strip()

    connection = db()

    students = connection.execute(
        """
        SELECT student_id, name
        FROM students
        ORDER BY name
        """
    ).fetchall()

    if selected_date:

        attendance = connection.execute(
            """
            SELECT * FROM attendance
            WHERE date=?
            ORDER BY date DESC, time DESC
            """,
            (selected_date,)
        ).fetchall()

    else:

        attendance = connection.execute(
            """
            SELECT * FROM attendance
            ORDER BY date DESC, time DESC
            """
        ).fetchall()

    total_students = connection.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    today = datetime.now().strftime("%Y-%m-%d")

    present_today = connection.execute(
        """
        SELECT COUNT(*) FROM attendance
        WHERE date=?
        """,
        (today,)
    ).fetchone()[0]

    connection.close()

    rate = round(
        (present_today / total_students) * 100
    ) if total_students else 0

    return render_template(
        "lecturer.html",
        students=students,
        att=attendance,
        total_students=total_students,
        present_today=present_today,
        attendance_rate=rate,
        selected_date=selected_date
    )


# ---------------------------------
# ADMIN LOGIN
# ---------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form.get(
            "username", ""
        ).strip()

        password = request.form.get(
            "password", ""
        )

        connection = db()

        admin = connection.execute(
            """
            SELECT * FROM admins
            WHERE username=?
            """,
            (username,)
        ).fetchone()

        connection.close()

        if admin and check_password_hash(
            admin["password_hash"],
            password
        ):

            session.clear()

            session.update(
                role="admin",
                username=username
            )

            return redirect(
                url_for("admin_dashboard")
            )

        flash(
            "Invalid administrator username or password.",
            "error"
        )

    return render_template(
        "login.html",
        kind="Admin"
    )


# ---------------------------------
# ADMIN DASHBOARD
# ---------------------------------

@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():

    today = datetime.now().strftime("%Y-%m-%d")

    connection = db()

    total_students = connection.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    total_lecturers = connection.execute(
        "SELECT COUNT(*) FROM lecturers"
    ).fetchone()[0]

    total_records = connection.execute(
        "SELECT COUNT(*) FROM attendance"
    ).fetchone()[0]

    present_today = connection.execute(
        """
        SELECT COUNT(*) FROM attendance
        WHERE date=?
        """,
        (today,)
    ).fetchone()[0]

    recent = connection.execute(
        """
        SELECT student_id, name, date, time, status
        FROM attendance
        ORDER BY date DESC, time DESC
        LIMIT 8
        """
    ).fetchall()

    students = connection.execute(
        """
        SELECT student_id, name, email, created_at
        FROM students
        ORDER BY name
        """
    ).fetchall()

    lecturers = connection.execute(
        """
        SELECT id, username
        FROM lecturers
        ORDER BY username
        """
    ).fetchall()

    connection.close()

    rate = round(
        (present_today / total_students) * 100
    ) if total_students else 0

    return render_template(
        "admin.html",
        total_students=total_students,
        total_lecturers=total_lecturers,
        total_records=total_records,
        present_today=present_today,
        attendance_rate=rate,
        recent=recent,
        students=students,
        lecturers=lecturers
    )


# ---------------------------------
# ADD LECTURER
# ---------------------------------

@app.route("/admin/lecturer/add", methods=["POST"])
@role_required("admin")
def add_lecturer():

    username = request.form.get(
        "username", ""
    ).strip()

    password = request.form.get(
        "password", ""
    )

    if len(username) < 3 or len(password) < 6:

        flash(
            "Username must be at least 3 characters "
            "and password at least 6 characters.",
            "error"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    connection = db()

    try:

        connection.execute(
            """
            INSERT INTO lecturers(username, password_hash)
            VALUES(?, ?)
            """,
            (
                username,
                generate_password_hash(password)
            )
        )

        connection.commit()

        flash(
            "Lecturer account created successfully.",
            "success"
        )

    except sqlite3.IntegrityError:

        flash(
            "That lecturer username already exists.",
            "error"
        )

    finally:

        connection.close()

    return redirect(
        url_for("admin_dashboard")
    )


# ---------------------------------
# DELETE LECTURER
# ---------------------------------

@app.route(
    "/admin/lecturer/delete/<int:lecturer_id>",
    methods=["POST"]
)
@role_required("admin")
def delete_lecturer(lecturer_id):

    connection = db()

    connection.execute(
        "DELETE FROM lecturers WHERE id=?",
        (lecturer_id,)
    )

    connection.commit()
    connection.close()

    flash(
        "Lecturer account deleted.",
        "success"
    )

    return redirect(
        url_for("admin_dashboard")
    )


# ---------------------------------
# ADMIN DELETE STUDENT
# ---------------------------------

@app.route(
    "/admin/student/delete/<path:student_id>",
    methods=["POST"]
)
@role_required("admin")
def admin_delete_student(student_id):

    connection = db()

    connection.execute(
        "DELETE FROM attendance WHERE student_id=?",
        (student_id,)
    )

    connection.execute(
        "DELETE FROM students WHERE student_id=?",
        (student_id,)
    )

    connection.commit()
    connection.close()

    flash(
        "Student and their attendance records deleted.",
        "success"
    )

    return redirect(
        url_for("admin_dashboard")
    )


# ---------------------------------
# ADMIN SETTINGS
# ---------------------------------

@app.route("/admin/settings", methods=["POST"])
@role_required("admin")
def admin_settings():

    username = request.form.get(
        "username", ""
    ).strip()

    password = request.form.get(
        "password", ""
    )

    if len(username) < 3 or len(password) < 6:

        flash(
            "Enter a username (3+ characters) "
            "and password (6+ characters).",
            "error"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    connection = db()

    try:

        connection.execute(
            """
            UPDATE admins
            SET username=?, password_hash=?
            WHERE username=?
            """,
            (
                username,
                generate_password_hash(password),
                session["username"]
            )
        )

        connection.commit()

        session["username"] = username

        flash(
            "Administrator credentials updated.",
            "success"
        )

    except sqlite3.IntegrityError:

        flash(
            "That administrator username is already in use.",
            "error"
        )

    finally:

        connection.close()

    return redirect(
        url_for("admin_dashboard")
    )


# ---------------------------------
# LECTURER DELETE STUDENT
# ---------------------------------

@app.route(
    "/lecturer/delete_student/<path:student_id>",
    methods=["POST"]
)
@role_required("lecturer")
def delete_student(student_id):

    connection = db()

    connection.execute(
        "DELETE FROM attendance WHERE student_id=?",
        (student_id,)
    )

    connection.execute(
        "DELETE FROM students WHERE student_id=?",
        (student_id,)
    )

    connection.commit()
    connection.close()

    flash(
        f"Student {student_id} and related attendance records removed.",
        "success"
    )

    return redirect(
        url_for("ldash")
    )


# ---------------------------------
# DOWNLOAD ATTENDANCE REPORT
# ---------------------------------

@app.route("/lecturer/download")
@role_required("lecturer")
def download_attendance():

    connection = db()

    records = connection.execute(
        """
        SELECT student_id, name, date, time, status
        FROM attendance
        ORDER BY date DESC, time DESC
        """
    ).fetchall()

    connection.close()

    stream = StringIO()

    writer = csv.writer(stream)

    writer.writerow([
        "Student ID",
        "Name",
        "Date",
        "Time",
        "Status"
    ])

    for row in records:

        writer.writerow([
            row["student_id"],
            row["name"],
            row["date"],
            row["time"],
            row["status"]
        ])

    response = Response(
        stream.getvalue(),
        mimetype="text/csv"
    )

    response.headers["Content-Disposition"] = (
        "attachment; filename=Attendance_Report.csv"
    )

    return response


# ---------------------------------
# CLEAR ATTENDANCE
# ---------------------------------

@app.route("/lecturer/clear", methods=["POST"])
@role_required("lecturer")
def clear_attendance():

    connection = db()

    connection.execute(
        "DELETE FROM attendance"
    )

    connection.commit()
    connection.close()

    flash(
        "Attendance history cleared.",
        "success"
    )

    return redirect(
        url_for("ldash")
    )


# ---------------------------------
# UPDATE LECTURER DETAILS
# ---------------------------------

@app.route("/lecturer/settings", methods=["POST"])
@role_required("lecturer")
def update_lecturer():

    username = request.form.get(
        "username", ""
    ).strip()

    password = request.form.get(
        "password", ""
    )

    if len(username) < 3 or len(password) < 6:

        flash(
            "Username must be at least 3 characters "
            "and password at least 6 characters.",
            "error"
        )

        return redirect(
            url_for("ldash")
        )

    connection = db()

    try:

        connection.execute(
            """
            UPDATE lecturers
            SET username=?, password_hash=?
            WHERE username=?
            """,
            (
                username,
                generate_password_hash(password),
                session["username"]
            )
        )

        connection.commit()

        session["username"] = username

        flash(
            "Lecturer credentials updated.",
            "success"
        )

    except sqlite3.IntegrityError:

        flash(
            "That username is already in use.",
            "error"
        )

    finally:

        connection.close()

    return redirect(
        url_for("ldash")
    )


# ---------------------------------
# UPDATE STUDENT PASSWORD
# ---------------------------------

@app.route("/student/settings", methods=["POST"])
@role_required("student")
def update_student():

    password = request.form.get(
        "password", ""
    )

    if len(password) < 6:

        flash(
            "Password must be at least 6 characters.",
            "error"
        )

        return redirect(
            url_for("sdash")
        )

    connection = db()

    connection.execute(
        """
        UPDATE students
        SET password_hash=?
        WHERE student_id=?
        """,
        (
            generate_password_hash(password),
            session["student_id"]
        )
    )

    connection.commit()
    connection.close()

    flash(
        "Password updated successfully.",
        "success"
    )

    return redirect(
        url_for("sdash")
    )


# ---------------------------------
# FACE RECOGNITION ATTENDANCE
# ---------------------------------

@app.route(
    "/lecturer/recognize",
    methods=["POST"]
)
@role_required("lecturer")
def recognize():

    data = request.get_json(silent=True) or {}

    image_data = data.get(
        "image", ""
    )

    if not image_data:

        return jsonify(
            ok=False,
            message="No camera image received."
        )

    frame = img(image_data)

    if frame is None:

        return jsonify(
            ok=False,
            message="Invalid camera image."
        )

    enc, count = encoding(frame)

    if enc is None:

        return jsonify(
            ok=False,
            message=(
                f"Show exactly one face to the camera. "
                f"Detected {count}."
            )
        )

    connection = db()

    students = connection.execute(
        """
        SELECT student_id, name, face_encoding
        FROM students
        """
    ).fetchall()

    best_student = None
    best_distance = 999.0

    for student in students:

        try:

            stored = np.asarray(
                json.loads(student["face_encoding"]),
                dtype=np.float64
            )

            distance = float(
                face_recognition.face_distance(
                    [stored],
                    enc
                )[0]
            )

            if distance < best_distance:

                best_distance = distance
                best_student = student

        except Exception as error:

            print(
                "Face comparison error:",
                error
            )

    if best_student is None or best_distance > 0.45:

        connection.close()

        return jsonify(
            ok=False,
            message=(
                "Unknown face. "
                "This person is not registered."
            )
        )

    now = datetime.now()

    date = now.strftime("%Y-%m-%d")
    time = now.strftime("%H:%M:%S")

    try:

        connection.execute(
            """
            INSERT INTO attendance(
                student_id,
                name,
                date,
                time,
                status
            )
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                best_student["student_id"],
                best_student["name"],
                date,
                time,
                "Present"
            )
        )

        connection.commit()

        message = (
            f"{best_student['name']} marked present at {time}."
        )

    except sqlite3.IntegrityError:

        message = (
            f"{best_student['name']} is already marked present today."
        )

    connection.close()

    return jsonify(
        ok=True,
        message=message
    )


# ---------------------------------
# LOGOUT
# ---------------------------------

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been signed out.",
        "success"
    )

    return redirect(
        url_for("home")
    )


# ---------------------------------
# RUN APPLICATION
# ---------------------------------

if __name__ == "__main__":

    init_db()

    app.run(debug=True)

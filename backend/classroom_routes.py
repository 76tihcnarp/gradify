import base64
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import time
from typing import Optional

import mysql.connector
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from backend.db import get_db_connection


router = APIRouter(tags=["classrooms and authentication"])

# Set GRADIFY_TOKEN_SECRET to a long random value in .env before deployment.
TOKEN_SECRET = os.getenv(
    "GRADIFY_TOKEN_SECRET",
    "gradify-local-development-secret-change-this",
).encode("utf-8")
TOKEN_LIFETIME_SECONDS = 12 * 60 * 60
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 260_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = stored_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_token(payload: dict) -> str:
    token_data = dict(payload)
    token_data["exp"] = int(time.time()) + TOKEN_LIFETIME_SECONDS
    encoded_payload = base64.urlsafe_b64encode(
        json.dumps(token_data, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(TOKEN_SECRET, encoded_payload.encode("ascii"), hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{encoded_payload}.{encoded_signature}"


def read_token(token: str) -> dict:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(
            TOKEN_SECRET, encoded_payload.encode("ascii"), hashlib.sha256
        ).digest()
        supplied_signature = base64.urlsafe_b64decode(
            encoded_signature + "=" * (-len(encoded_signature) % 4)
        )
        if not hmac.compare_digest(expected_signature, supplied_signature):
            raise ValueError("Invalid signature")
        payload_bytes = base64.urlsafe_b64decode(
            encoded_payload + "=" * (-len(encoded_payload) % 4)
        )
        payload = json.loads(payload_bytes.decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("Expired token")
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired login token.")


def get_current_identity(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Please log in first.")
    return read_token(credentials.credentials)


def get_current_teacher(identity: dict = Depends(get_current_identity)) -> dict:
    if identity.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Teacher access required.")
    return identity


def get_current_student(identity: dict = Depends(get_current_identity)) -> dict:
    if identity.get("role") != "student":
        raise HTTPException(status_code=403, detail="Student access required.")
    return identity


class TeacherRegister(BaseModel):
    teacher_id: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    email: Optional[str] = Field(default=None, max_length=255)


class TeacherLogin(BaseModel):
    teacher_id: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class ClassroomCreate(BaseModel):
    class_name: str = Field(min_length=1, max_length=100)


class StudentLogin(BaseModel):
    student_id: int = Field(gt=0)
    class_pin: str = Field(min_length=1, max_length=20)


@router.post("/auth/teacher/register", status_code=201)
def register_teacher(data: TeacherRegister):
    teacher_id = data.teacher_id.strip()
    email = data.email.strip() if data.email else None
    if not teacher_id:
        raise HTTPException(status_code=422, detail="Teacher ID cannot be blank.")

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, role, is_active)
            VALUES (%s, %s, %s, 'teacher', TRUE)
            """,
            (teacher_id, email or None, hash_password(data.password)),
        )
        connection.commit()
        return {
            "message": "Teacher account created successfully.",
            "teacher_id": teacher_id,
            "user_id": cursor.lastrowid,
        }
    except mysql.connector.IntegrityError:
        connection.rollback()
        raise HTTPException(status_code=409, detail="That Teacher ID or email is already registered.")
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


@router.post("/auth/teacher/login")
def login_teacher(data: TeacherLogin):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT user_id, username, password_hash, role, is_active
            FROM users
            WHERE username = %s AND role = 'teacher'
            LIMIT 1
            """,
            (data.teacher_id.strip(),),
        )
        teacher = cursor.fetchone()
        if (
            not teacher
            or not teacher["is_active"]
            or not verify_password(data.password, teacher["password_hash"])
        ):
            raise HTTPException(status_code=401, detail="Incorrect Teacher ID or password.")

        token = create_token({
            "sub": int(teacher["user_id"]),
            "role": "teacher",
            "teacher_id": teacher["username"],
        })
        return {
            "message": "Teacher login successful.",
            "access_token": token,
            "token_type": "bearer",
            "teacher_id": teacher["username"],
        }
    finally:
        cursor.close()
        connection.close()


def generate_class_pin(cursor) -> str:
    for _ in range(20):
        pin = f"{secrets.randbelow(1_000_000):06d}"
        cursor.execute("SELECT class_id FROM classes WHERE class_pin = %s LIMIT 1", (pin,))
        if cursor.fetchone() is None:
            return pin
    raise HTTPException(status_code=500, detail="Could not generate a classroom PIN. Try again.")


def ensure_teacher_owns_class(cursor, class_id: int, teacher_user_id: int):
    cursor.execute(
        "SELECT class_id FROM classes WHERE class_id = %s AND teacher_id = %s",
        (class_id, teacher_user_id),
    )
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Classroom not found.")


@router.post("/classrooms", status_code=201)
def create_classroom(data: ClassroomCreate, teacher: dict = Depends(get_current_teacher)):
    class_name = data.class_name.strip()
    if not class_name:
        raise HTTPException(status_code=422, detail="Classroom name cannot be blank.")

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        pin = generate_class_pin(cursor)
        cursor.execute(
            "INSERT INTO classes (teacher_id, class_name, class_pin) VALUES (%s, %s, %s)",
            (int(teacher["sub"]), class_name, pin),
        )
        connection.commit()
        return {
            "message": "Classroom created successfully.",
            "class_id": cursor.lastrowid,
            "class_name": class_name,
            "class_pin": pin,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


@router.get("/classrooms")
def get_teacher_classrooms(teacher: dict = Depends(get_current_teacher)):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT c.class_id, c.class_name, c.class_pin, c.created_at,
                   COUNT(s.student_id) AS student_count
            FROM classes c
            LEFT JOIN students s ON s.class_id = c.class_id
            WHERE c.teacher_id = %s
            GROUP BY c.class_id, c.class_name, c.class_pin, c.created_at
            ORDER BY c.created_at DESC
            """,
            (int(teacher["sub"]),),
        )
        return {"classrooms": cursor.fetchall()}
    finally:
        cursor.close()
        connection.close()


@router.get("/classrooms/{class_id}/students")
def get_class_students(class_id: int, teacher: dict = Depends(get_current_teacher)):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        cursor.execute(
            """
            SELECT student_id, student_name, roll_number, created_at
            FROM students
            WHERE class_id = %s
            ORDER BY roll_number, student_id
            """,
            (class_id,),
        )
        students = cursor.fetchall()
        cursor.execute("SELECT class_name, class_pin FROM classes WHERE class_id = %s", (class_id,))
        classroom = cursor.fetchone()
        return {
            "class_id": class_id,
            "class_name": classroom["class_name"],
            "class_pin": classroom["class_pin"],
            "total_students": len(students),
            "students": students,
        }
    finally:
        cursor.close()
        connection.close()


def normalize_header(value: str) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())


@router.post("/classrooms/{class_id}/students/upload", status_code=201)
async def upload_class_roster(
    class_id: int,
    file: UploadFile = File(...),
    teacher: dict = Depends(get_current_teacher),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="CSV file must be 5 MB or smaller.")

    try:
        decoded = contents.decode("utf-8-sig")
        try:
            dialect = csv.Sniffer().sniff(decoded[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(decoded), dialect=dialect)
        if not reader.fieldnames:
            raise ValueError("CSV header row is missing.")

        normalized_headers = {
            normalize_header(header): header for header in reader.fieldnames if header
        }
        name_header = next(
            (normalized_headers[key] for key in ("student name", "name", "student")
             if key in normalized_headers),
            None,
        )
        roll_header = next(
            (normalized_headers[key] for key in ("roll number", "roll no", "rollno", "roll")
             if key in normalized_headers),
            None,
        )
        if not name_header or not roll_header:
            raise HTTPException(
                status_code=422,
                detail="CSV must contain student_name/name and roll_number/roll_no columns.",
            )

        roster = []
        seen_rolls = set()
        for row_number, row in enumerate(reader, start=2):
            name = (row.get(name_header) or "").strip()
            roll = (row.get(roll_header) or "").strip()
            if not name and not roll:
                continue
            if not name or not roll:
                raise HTTPException(
                    status_code=422,
                    detail=f"Row {row_number} must contain both student name and roll number.",
                )
            if roll in seen_rolls:
                raise HTTPException(status_code=409, detail=f"Duplicate roll number '{roll}' in the uploaded CSV.")
            seen_rolls.add(roll)
            roster.append((name, roll))
        if not roster:
            raise HTTPException(status_code=400, detail="The CSV contains no student records.")
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Could not read CSV: {error}")

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        cursor.execute("SELECT roll_number FROM students WHERE class_id = %s", (class_id,))
        existing_rolls = {row[0] for row in cursor.fetchall()}
        conflicts = sorted(existing_rolls.intersection(seen_rolls))
        if conflicts:
            raise HTTPException(
                status_code=409,
                detail=f"These roll numbers already exist in this classroom: {', '.join(conflicts[:10])}",
            )

        created_students = []
        for student_name, roll_number in roster:
            cursor.execute(
                "INSERT INTO students (student_name, roll_number, class_id) VALUES (%s, %s, %s)",
                (student_name, roll_number, class_id),
            )
            created_students.append({
                "student_id": cursor.lastrowid,
                "student_name": student_name,
                "roll_number": roll_number,
            })
        connection.commit()
        return {
            "message": "Student roster uploaded successfully.",
            "class_id": class_id,
            "total_created": len(created_students),
            "students": created_students,
        }
    except HTTPException:
        connection.rollback()
        raise
    except mysql.connector.IntegrityError:
        connection.rollback()
        raise HTTPException(status_code=409, detail="A roll number already exists in this classroom.")
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


@router.post("/auth/student/login")
def login_student(data: StudentLogin):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT s.student_id, s.student_name, s.roll_number, s.class_id,
                   c.class_name
            FROM students s
            INNER JOIN classes c ON c.class_id = s.class_id
            WHERE s.student_id = %s AND c.class_pin = %s
            LIMIT 1
            """,
            (data.student_id, data.class_pin.strip()),
        )
        student = cursor.fetchone()
        if not student:
            raise HTTPException(status_code=401, detail="Student ID or class PIN is incorrect.")

        token = create_token({
            "sub": int(student["student_id"]),
            "role": "student",
            "class_id": int(student["class_id"]),
        })
        return {
            "message": "Student login successful.",
            "access_token": token,
            "token_type": "bearer",
            "student": student,
        }
    finally:
        cursor.close()
        connection.close()

from datetime import date
from pathlib import Path
from typing import List, Literal, Optional
import secrets

import mysql.connector
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.db import get_db_connection
from backend.classroom_routes import (
    ensure_teacher_owns_class,
    get_current_identity,
    get_current_student,
    get_current_teacher,
)

router = APIRouter(tags=["Attendance, Class Materials and Syllabus Progress"])

BACKEND_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = BACKEND_DIR / "uploads"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class AttendanceItem(BaseModel):
    student_id: int = Field(gt=0)
    status: Literal["present", "absent", "late"]


class AttendanceSubmission(BaseModel):
    attendance_date: date
    records: List[AttendanceItem] = Field(min_length=1)


class TopicCreate(BaseModel):
    topic_name: str = Field(min_length=1, max_length=150)
    sort_order: int = Field(default=0, ge=0)


class TopicUpdate(BaseModel):
    topic_name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    sort_order: Optional[int] = Field(default=None, ge=0)


class ProgressUpdate(BaseModel):
    topic_id: int = Field(gt=0)
    is_completed: bool


def _student_class_id(student: dict) -> int:
    try:
        return int(student["class_id"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Student session is missing classroom information. Please log in again.")


def _ensure_student_in_class(cursor, student_id: int, class_id: int):
    cursor.execute(
        "SELECT student_id FROM students WHERE student_id = %s AND class_id = %s",
        (student_id, class_id),
    )
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Student not found in this classroom.")


@router.post("/classrooms/{class_id}/attendance")
def mark_class_attendance(
    class_id: int,
    data: AttendanceSubmission,
    teacher: dict = Depends(get_current_teacher),
):
    student_ids = [item.student_id for item in data.records]
    if len(student_ids) != len(set(student_ids)):
        raise HTTPException(status_code=422, detail="A student can appear only once in an attendance upload.")

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        placeholders = ",".join(["%s"] * len(student_ids))
        cursor.execute(
            f"SELECT student_id FROM students WHERE class_id = %s AND student_id IN ({placeholders})",
            (class_id, *student_ids),
        )
        valid_ids = {int(row[0]) for row in cursor.fetchall()}
        invalid_ids = sorted(set(student_ids) - valid_ids)
        if invalid_ids:
            raise HTTPException(status_code=422, detail={"message": "Some students do not belong to this classroom.", "student_ids": invalid_ids})

        for item in data.records:
            cursor.execute(
                """
                INSERT INTO attendance (student_id, class_id, attendance_date, status, marked_by)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE status = VALUES(status), marked_by = VALUES(marked_by)
                """,
                (item.student_id, class_id, data.attendance_date, item.status, int(teacher["sub"])),
            )
        connection.commit()
        return {
            "message": "Attendance saved successfully.",
            "class_id": class_id,
            "attendance_date": data.attendance_date.isoformat(),
            "records_saved": len(data.records),
            "counts": {
                status: sum(1 for item in data.records if item.status == status)
                for status in ("present", "absent", "late")
            },
        }
    except HTTPException:
        connection.rollback()
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


@router.get("/classrooms/{class_id}/attendance")
def get_class_attendance(
    class_id: int,
    attendance_date: Optional[date] = Query(default=None),
    teacher: dict = Depends(get_current_teacher),
):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        if attendance_date:
            cursor.execute(
                """
                SELECT a.attendance_id, a.student_id, s.student_name, s.roll_number,
                       a.attendance_date, a.status, a.marked_by, a.created_at
                FROM attendance a JOIN students s ON s.student_id = a.student_id
                WHERE a.class_id = %s AND a.attendance_date = %s
                ORDER BY s.roll_number, s.student_id
                """,
                (class_id, attendance_date),
            )
        else:
            cursor.execute(
                """
                SELECT a.attendance_id, a.student_id, s.student_name, s.roll_number,
                       a.attendance_date, a.status, a.marked_by, a.created_at
                FROM attendance a JOIN students s ON s.student_id = a.student_id
                WHERE a.class_id = %s
                ORDER BY a.attendance_date DESC, s.roll_number, s.student_id
                """,
                (class_id,),
            )
        rows = cursor.fetchall()
        return {"class_id": class_id, "total_records": len(rows), "attendance": rows}
    finally:
        cursor.close()
        connection.close()


@router.get("/students/me/attendance")
def get_my_attendance(student: dict = Depends(get_current_student)):
    student_id = int(student["sub"])
    class_id = _student_class_id(student)
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT attendance_id, attendance_date, status, created_at
            FROM attendance
            WHERE student_id = %s AND class_id = %s
            ORDER BY attendance_date DESC
            """,
            (student_id, class_id),
        )
        rows = cursor.fetchall()
        total = len(rows)
        counts = {status: sum(1 for row in rows if row["status"] == status) for status in ("present", "absent", "late")}
        marked_days = counts["present"] + counts["absent"] + counts["late"]
        percentage = round((counts["present"] + counts["late"]) / marked_days * 100, 2) if marked_days else None
        return {"student_id": student_id, "class_id": class_id, "total_records": total, "counts": counts, "attendance_percentage": percentage, "attendance": rows}
    finally:
        cursor.close()
        connection.close()


@router.post("/classrooms/{class_id}/materials", status_code=201)
async def upload_class_material(
    class_id: int,
    material_type: Literal["timetable_photo", "syllabus"],
    file: UploadFile = File(...),
    teacher: dict = Depends(get_current_teacher),
):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_IMAGES:
        raise HTTPException(status_code=415, detail="Upload a JPG, JPEG, PNG or WEBP image.")
    if file.content_type and file.content_type not in set(ALLOWED_IMAGES.values()):
        raise HTTPException(status_code=415, detail="The uploaded file must be an image.")
    contents = await file.read(MAX_IMAGE_BYTES + 1)
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded image is empty.")
    if len(contents) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image size must not exceed 5 MB.")
    valid_signature = (
        (extension in {".jpg", ".jpeg"} and contents.startswith(b"\xff\xd8\xff"))
        or (extension == ".png" and contents.startswith(b"\x89PNG\r\n\x1a\n"))
        or (extension == ".webp" and len(contents) >= 12 and contents[:4] == b"RIFF" and contents[8:12] == b"WEBP")
    )
    if not valid_signature:
        raise HTTPException(status_code=415, detail="The file contents do not match the image extension.")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    saved_path = None
    old_paths = []
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        class_dir = UPLOAD_ROOT / f"class_{class_id}"
        class_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{material_type}_{secrets.token_hex(12)}{extension}"
        saved_path = class_dir / filename
        saved_path.write_bytes(contents)
        relative_path = str(saved_path.relative_to(BACKEND_DIR))

        cursor.execute(
            "SELECT file_path FROM study_materials WHERE class_id = %s AND material_type = %s",
            (class_id, material_type),
        )
        old_paths = [row["file_path"] for row in cursor.fetchall() if row.get("file_path")]
        cursor.execute(
            """
            INSERT INTO study_materials
                (owner_user_id, student_id, class_id, material_type, original_filename,
                 file_path, mime_type, file_size_bytes)
            VALUES (%s, NULL, %s, %s, %s, %s, %s, %s)
            """,
            (int(teacher["sub"]), class_id, material_type, Path(file.filename or filename).name,
             relative_path, ALLOWED_IMAGES[extension], len(contents)),
        )
        new_id = cursor.lastrowid
        cursor.execute(
            "DELETE FROM study_materials WHERE class_id = %s AND material_type = %s AND material_id <> %s",
            (class_id, material_type, new_id),
        )
        connection.commit()
        for old_path in old_paths:
            old_file = (BACKEND_DIR / old_path).resolve()
            if UPLOAD_ROOT.resolve() in old_file.parents and old_file != saved_path.resolve():
                try:
                    old_file.unlink(missing_ok=True)
                except OSError:
                    pass
        return {
            "message": "Class material uploaded successfully.",
            "material_id": new_id,
            "class_id": class_id,
            "material_type": material_type,
            "original_filename": Path(file.filename or filename).name,
            "file_size_bytes": len(contents),
            "file_url": f"/classrooms/{class_id}/materials/{new_id}/file",
        }
    except HTTPException:
        connection.rollback()
        if saved_path:
            saved_path.unlink(missing_ok=True)
        raise
    except Exception:
        connection.rollback()
        if saved_path:
            saved_path.unlink(missing_ok=True)
        raise
    finally:
        cursor.close()
        connection.close()


def _ensure_class_access(cursor, class_id: int, identity: dict):
    role = identity.get("role")
    if role == "teacher":
        ensure_teacher_owns_class(cursor, class_id, int(identity["sub"]))
    elif role == "student":
        if int(identity.get("class_id", -1)) != class_id:
            raise HTTPException(status_code=403, detail="You do not have access to this classroom.")
        _ensure_student_in_class(cursor, int(identity["sub"]), class_id)
    else:
        raise HTTPException(status_code=403, detail="Classroom access required.")


@router.get("/classrooms/{class_id}/materials")
def get_class_materials(class_id: int, identity: dict = Depends(get_current_identity)):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        _ensure_class_access(cursor, class_id, identity)
        cursor.execute(
            """
            SELECT material_id, material_type, original_filename, mime_type,
                   file_size_bytes, uploaded_at
            FROM study_materials
            WHERE class_id = %s AND material_type IN ('timetable_photo', 'syllabus')
            ORDER BY uploaded_at DESC
            """,
            (class_id,),
        )
        rows = cursor.fetchall()
        for row in rows:
            row["file_url"] = f"/classrooms/{class_id}/materials/{row['material_id']}/file"
        return {"class_id": class_id, "total_materials": len(rows), "materials": rows}
    finally:
        cursor.close()
        connection.close()


@router.get("/classrooms/{class_id}/materials/{material_id}/file")
def get_class_material_file(
    class_id: int,
    material_id: int,
    identity: dict = Depends(get_current_identity),
):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        _ensure_class_access(cursor, class_id, identity)
        cursor.execute(
            """
            SELECT file_path, original_filename, mime_type
            FROM study_materials
            WHERE material_id = %s AND class_id = %s
            LIMIT 1
            """,
            (material_id, class_id),
        )
        material = cursor.fetchone()
        if not material:
            raise HTTPException(status_code=404, detail="Class material not found.")
        file_path = (BACKEND_DIR / material["file_path"]).resolve()
        if UPLOAD_ROOT.resolve() not in file_path.parents or not file_path.is_file():
            raise HTTPException(status_code=404, detail="The material file is unavailable.")
        return FileResponse(
            path=file_path,
            media_type=material["mime_type"],
            filename=material["original_filename"],
            headers={"Content-Disposition": "inline"},
        )
    finally:
        cursor.close()
        connection.close()


@router.post("/classrooms/{class_id}/topics", status_code=201)
def create_class_topic(
    class_id: int,
    data: TopicCreate,
    teacher: dict = Depends(get_current_teacher),
):
    topic_name = data.topic_name.strip()
    if not topic_name:
        raise HTTPException(status_code=422, detail="Topic name cannot be blank.")
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        cursor.execute(
            "INSERT INTO topics (class_id, topic_name, sort_order) VALUES (%s, %s, %s)",
            (class_id, topic_name, data.sort_order),
        )
        connection.commit()
        return {"message": "Topic created successfully.", "topic_id": cursor.lastrowid, "class_id": class_id, "topic_name": topic_name, "sort_order": data.sort_order}
    except mysql.connector.IntegrityError:
        connection.rollback()
        raise HTTPException(status_code=409, detail="This topic already exists in the classroom.")
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


@router.get("/classrooms/{class_id}/topics")
def get_class_topics(class_id: int, identity: dict = Depends(get_current_identity)):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        _ensure_class_access(cursor, class_id, identity)
        cursor.execute(
            """
            SELECT t.topic_id, t.topic_name, t.sort_order,
                   COUNT(sp.student_id) AS completion_records,
                   SUM(CASE WHEN sp.is_completed = TRUE THEN 1 ELSE 0 END) AS completed_records
            FROM topics t
            LEFT JOIN student_progress sp ON sp.topic_id = t.topic_id
            WHERE t.class_id = %s
            GROUP BY t.topic_id, t.topic_name, t.sort_order
            ORDER BY t.sort_order, t.topic_id
            """,
            (class_id,),
        )
        topics = cursor.fetchall()
        return {"class_id": class_id, "total_topics": len(topics), "topics": topics}
    finally:
        cursor.close()
        connection.close()


@router.put("/classrooms/{class_id}/topics/{topic_id}")
def update_class_topic(
    class_id: int,
    topic_id: int,
    data: TopicUpdate,
    teacher: dict = Depends(get_current_teacher),
):
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide topic_name or sort_order to update.")
    if "topic_name" in changes:
        changes["topic_name"] = changes["topic_name"].strip()
        if not changes["topic_name"]:
            raise HTTPException(status_code=422, detail="Topic name cannot be blank.")
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        cursor.execute("SELECT topic_id FROM topics WHERE topic_id = %s AND class_id = %s", (topic_id, class_id))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Topic not found in this classroom.")
        assignments = ", ".join(f"{column} = %s" for column in changes)
        cursor.execute(
            f"UPDATE topics SET {assignments} WHERE topic_id = %s AND class_id = %s",
            (*changes.values(), topic_id, class_id),
        )
        connection.commit()
        return {"message": "Topic updated successfully.", "topic_id": topic_id, **changes}
    except mysql.connector.IntegrityError:
        connection.rollback()
        raise HTTPException(status_code=409, detail="A topic with that name already exists in this classroom.")
    except HTTPException:
        connection.rollback()
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


@router.delete("/classrooms/{class_id}/topics/{topic_id}")
def delete_class_topic(
    class_id: int,
    topic_id: int,
    teacher: dict = Depends(get_current_teacher),
):
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        cursor.execute("DELETE FROM topics WHERE topic_id = %s AND class_id = %s", (topic_id, class_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Topic not found in this classroom.")
        connection.commit()
        return {"message": "Topic deleted successfully.", "topic_id": topic_id}
    except HTTPException:
        connection.rollback()
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


@router.get("/classrooms/{class_id}/progress")
def get_class_progress_overview(
    class_id: int,
    teacher: dict = Depends(get_current_teacher),
):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        cursor.execute(
            """
            SELECT s.student_id, s.student_name, s.roll_number,
                   t.topic_id, t.topic_name, t.sort_order,
                   COALESCE(sp.is_completed, FALSE) AS is_completed,
                   sp.completed_at
            FROM students s
            CROSS JOIN topics t
            LEFT JOIN student_progress sp
                ON sp.student_id = s.student_id AND sp.topic_id = t.topic_id
            WHERE s.class_id = %s AND t.class_id = %s
            ORDER BY s.roll_number, s.student_id, t.sort_order, t.topic_id
            """,
            (class_id, class_id),
        )
        rows = cursor.fetchall()
        return {"class_id": class_id, "total_student_topic_records": len(rows), "progress": rows}
    finally:
        cursor.close()
        connection.close()


@router.get("/students/me/progress")
def get_my_topic_progress(student: dict = Depends(get_current_student)):
    student_id = int(student["sub"])
    class_id = _student_class_id(student)
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT t.topic_id, t.topic_name, t.sort_order,
                   COALESCE(sp.is_completed, FALSE) AS is_completed,
                   sp.completed_at, sp.updated_at
            FROM topics t
            LEFT JOIN student_progress sp
                ON sp.topic_id = t.topic_id AND sp.student_id = %s
            WHERE t.class_id = %s
            ORDER BY t.sort_order, t.topic_id
            """,
            (student_id, class_id),
        )
        topics = cursor.fetchall()
        completed = sum(1 for topic in topics if topic["is_completed"])
        return {"student_id": student_id, "class_id": class_id, "total_topics": len(topics), "completed_topics": completed, "pending_topics": len(topics) - completed, "progress_percentage": round(completed / len(topics) * 100, 2) if topics else 0, "topics": topics}
    finally:
        cursor.close()
        connection.close()


@router.post("/students/me/progress")
def update_my_topic_progress(
    data: ProgressUpdate,
    student: dict = Depends(get_current_student),
):
    student_id = int(student["sub"])
    class_id = _student_class_id(student)
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT topic_id FROM topics WHERE topic_id = %s AND class_id = %s", (data.topic_id, class_id))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Topic not found in your classroom.")
        cursor.execute(
            """
            INSERT INTO student_progress (student_id, topic_id, is_completed, completed_at)
            VALUES (%s, %s, %s, CASE WHEN %s = TRUE THEN CURRENT_TIMESTAMP ELSE NULL END)
            ON DUPLICATE KEY UPDATE
                is_completed = VALUES(is_completed),
                completed_at = CASE WHEN VALUES(is_completed) = TRUE THEN CURRENT_TIMESTAMP ELSE NULL END,
                updated_at = CURRENT_TIMESTAMP
            """,
            (student_id, data.topic_id, data.is_completed, data.is_completed),
        )
        connection.commit()
        return {"message": "Topic progress updated successfully.", "student_id": student_id, "topic_id": data.topic_id, "is_completed": data.is_completed}
    except HTTPException:
        connection.rollback()
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


@router.get("/classrooms/{class_id}/students/{student_id}/progress")
def get_student_progress_for_teacher(
    class_id: int,
    student_id: int,
    teacher: dict = Depends(get_current_teacher),
):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        _ensure_student_in_class(cursor, student_id, class_id)
        cursor.execute(
            """
            SELECT t.topic_id, t.topic_name, t.sort_order,
                   COALESCE(sp.is_completed, FALSE) AS is_completed,
                   sp.completed_at, sp.updated_at
            FROM topics t
            LEFT JOIN student_progress sp
                ON sp.topic_id = t.topic_id AND sp.student_id = %s
            WHERE t.class_id = %s
            ORDER BY t.sort_order, t.topic_id
            """,
            (student_id, class_id),
        )
        topics = cursor.fetchall()
        completed = sum(1 for topic in topics if topic["is_completed"])
        return {"student_id": student_id, "class_id": class_id, "total_topics": len(topics), "completed_topics": completed, "pending_topics": len(topics) - completed, "progress_percentage": round(completed / len(topics) * 100, 2) if topics else 0, "topics": topics}
    finally:
        cursor.close()
        connection.close()

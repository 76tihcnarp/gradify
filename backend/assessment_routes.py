import csv
import io
import json
from datetime import date
from pathlib import Path
from typing import Optional

import joblib
import mysql.connector
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.db import get_db_connection
from backend.classroom_routes import (
    ensure_teacher_owns_class,
    get_current_student,
    get_current_teacher,
)

router = APIRouter(tags=["Class Assessments and Predictions"])

BASE_DIR = Path(__file__).resolve().parent.parent
try:
    QUICK_REGRESSION = joblib.load(BASE_DIR / "ml" / "gradify_quick_regression.pkl")
    DETAILED_REGRESSION = joblib.load(BASE_DIR / "ml" / "gradify_detailed_regression.pkl")
except Exception as exc:
    print(f"WARNING: Assessment prediction models could not be loaded: {exc}")
    QUICK_REGRESSION = None
    DETAILED_REGRESSION = None

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _header(value: str) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())


def _number(value, field_name: str, row_number: int, minimum: float = 0.0) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail=f"Row {row_number}: '{field_name}' must be a number, got '{value}'.",
        )
    if number < minimum:
        raise HTTPException(
            status_code=422,
            detail=f"Row {row_number}: '{field_name}' cannot be less than {minimum}.",
        )
    return number


def _parse_assessment_value(value, maximum: float, field_name: str, row_number: int):
    raw = "" if value is None else str(value).strip()
    if raw == "":
        return None, "missing"
    if raw.upper() == "A":
        return None, "absent"
    marks = _number(raw, field_name, row_number)
    if marks > maximum:
        raise HTTPException(
            status_code=422,
            detail=f"Row {row_number}: {field_name} mark {marks} exceeds maximum {maximum}.",
        )
    return marks, "present"


def _read_assessment_csv(contents: bytes):
    try:
        decoded = contents.decode("utf-8-sig")
        try:
            dialect = csv.Sniffer().sniff(decoded[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(decoded), dialect=dialect)
        if not reader.fieldnames:
            raise ValueError("CSV header row is missing.")
        header_map = {_header(name): name for name in reader.fieldnames if name}
        aliases = {
            "roll number": ("roll number", "roll no", "rollno", "roll"),
            "g1": ("g1", "st1", "term1", "assessment1"),
            "g2": ("g2", "st2", "term2", "assessment2"),
            "failures": ("failures", "past failures"),
            "absences": ("absences", "absence count"),
            "studytime": ("studytime", "study time", "weekly studytime"),
        }
        resolved = {}
        for canonical, names in aliases.items():
            found = next((header_map[name] for name in names if name in header_map), None)
            if found:
                resolved[canonical] = found
        missing = [key for key in ("roll number", "g1", "g2") if key not in resolved]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"CSV is missing required columns: {missing}. Required: roll_number, G1, G2.",
            )

        parsed = []
        seen_rolls = set()
        for row_number, row in enumerate(reader, start=2):
            if not any(str(value or "").strip() for value in row.values()):
                continue
            roll = str(row.get(resolved["roll number"]) or "").strip()
            if not roll:
                raise HTTPException(status_code=422, detail=f"Row {row_number}: roll number is blank.")
            if roll in seen_rolls:
                raise HTTPException(status_code=409, detail=f"Duplicate roll number '{roll}' in CSV.")
            seen_rolls.add(roll)
            parsed.append({"row_number": row_number, "roll_number": roll, "raw": row, "headers": resolved})
        if not parsed:
            raise HTTPException(status_code=400, detail="CSV contains no student rows.")
        return parsed, resolved
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read CSV: {exc}")


def _parse_detailed_features(row, headers, row_number):
    required = ("failures", "absences", "studytime")
    missing_columns = [key for key in required if key not in headers]
    if missing_columns:
        raise HTTPException(
            status_code=422,
            detail=f"Detailed mode requires CSV columns: {missing_columns}.",
        )

    values = {}
    for key in required:
        raw = row.get(headers[key])
        if raw is None or str(raw).strip() == "":
            raise HTTPException(status_code=422, detail=f"Row {row_number}: '{key}' is required for detailed mode.")
        number = _number(raw, key, row_number)
        if not number.is_integer():
            raise HTTPException(status_code=422, detail=f"Row {row_number}: '{key}' must be a whole number.")
        values[key] = int(number)
    if values["studytime"] not in (1, 2, 3, 4):
        raise HTTPException(status_code=422, detail=f"Row {row_number}: studytime must be between 1 and 4.")
    return values


def _predict(mode: str, normalized_g1: float, normalized_g2: float, detailed_features: Optional[dict]):
    if mode == "quick":
        if QUICK_REGRESSION is None:
            raise HTTPException(status_code=500, detail="Quick regression model is not loaded.")
        features = {"G1": normalized_g1, "G2": normalized_g2}
        expected = list(getattr(QUICK_REGRESSION, "feature_names_in_", ["G1", "G2"]))
        frame = pd.DataFrame([[features[name] for name in expected]], columns=expected)
        score = float(QUICK_REGRESSION.predict(frame)[0])
        return score, features

    if mode == "detailed":
        if DETAILED_REGRESSION is None:
            raise HTTPException(status_code=500, detail="Detailed regression model is not loaded.")
        features = {"G1": normalized_g1, "G2": normalized_g2, **(detailed_features or {})}
        expected = list(getattr(DETAILED_REGRESSION, "feature_names_in_", ["G1", "G2", "failures", "absences", "studytime"]))
        frame = pd.DataFrame([[features[name] for name in expected]], columns=expected)
        score = float(DETAILED_REGRESSION.predict(frame)[0])
        return score, features

    raise HTTPException(status_code=422, detail="mode must be 'quick' or 'detailed'.")


@router.post("/classrooms/{class_id}/assessments/upload", status_code=201)
async def upload_class_assessment(
    class_id: int,
    file: UploadFile = File(...),
    g1_assessment_name: str = Form("G1"),
    g1_maximum_marks: float = Form(..., gt=0),
    g2_assessment_name: str = Form("G2"),
    g2_maximum_marks: float = Form(..., gt=0),
    target_assessment: str = Form(..., min_length=1, max_length=100),
    target_maximum_marks: float = Form(..., gt=0),
    mode: str = Form("quick"),
    assessment_date: Optional[date] = Form(None),
    teacher: dict = Depends(get_current_teacher),
):
    if mode not in ("quick", "detailed"):
        raise HTTPException(status_code=422, detail="mode must be 'quick' or 'detailed'.")
    if mode == "quick" and QUICK_REGRESSION is None:
        raise HTTPException(status_code=500, detail="Quick regression model is not loaded.")
    if mode == "detailed" and DETAILED_REGRESSION is None:
        raise HTTPException(status_code=500, detail="Detailed regression model is not loaded.")
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")
    if not g1_assessment_name.strip() or not g2_assessment_name.strip() or not target_assessment.strip():
        raise HTTPException(status_code=422, detail="Assessment names cannot be blank.")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV file must be 5 MB or smaller.")
    rows, headers = _read_assessment_csv(contents)

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        cursor.execute(
            "SELECT student_id, roll_number FROM students WHERE class_id = %s",
            (class_id,),
        )
        roster = {str(item["roll_number"]).strip(): int(item["student_id"]) for item in cursor.fetchall()}
        if not roster:
            raise HTTPException(status_code=404, detail="This classroom has no students yet.")

        unknown_rolls = [item["roll_number"] for item in rows if item["roll_number"] not in roster]
        if unknown_rolls:
            raise HTTPException(status_code=422, detail=f"These roll numbers are not in this classroom: {unknown_rolls}")

        prepared = []
        for item in rows:
            row_number = item["row_number"]
            raw = item["raw"]
            g1, g1_status = _parse_assessment_value(raw.get(headers["g1"]), g1_maximum_marks, "G1", row_number)
            g2, g2_status = _parse_assessment_value(raw.get(headers["g2"]), g2_maximum_marks, "G2", row_number)
            detailed_features = None
            detailed_error = None
            if mode == "detailed" and g1_status == "present" and g2_status == "present":
                detailed_features = _parse_detailed_features(raw, headers, row_number)
            can_predict = g1_status == "present" and g2_status == "present"
            if mode == "detailed" and can_predict:
                can_predict = detailed_features is not None
            predicted_score = None
            predicted_marks = None
            risk_status = None
            model_features = None
            if can_predict:
                normalized_g1 = (g1 / g1_maximum_marks) * 20
                normalized_g2 = (g2 / g2_maximum_marks) * 20
                raw_score, model_features = _predict(mode, normalized_g1, normalized_g2, detailed_features)
                normalized_score = max(0.0, min(20.0, raw_score))
                predicted_score = round(normalized_score, 2)
                predicted_marks = round((normalized_score / 20.0) * target_maximum_marks, 2)
                risk_status = "At Risk" if normalized_score <= 10 else "Not At Risk"
            prepared.append({
                "student_id": roster[item["roll_number"]],
                "roll_number": item["roll_number"],
                "g1": g1,
                "g1_status": g1_status,
                "g2": g2,
                "g2_status": g2_status,
                "predicted_score": predicted_score,
                "predicted_marks": predicted_marks,
                "risk_status": risk_status,
                "model_features": model_features,
                "detailed_features": detailed_features,
            })

        assessment_day = assessment_date or date.today()
        cursor.execute(
            """INSERT INTO assessment_batches
               (class_id, teacher_id, g1_assessment_name, g1_maximum_marks,
                g2_assessment_name, g2_maximum_marks, target_assessment,
                target_maximum_marks, mode, assessment_date, original_filename, students_in_file)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                class_id, int(teacher["sub"]), g1_assessment_name.strip(), g1_maximum_marks,
                g2_assessment_name.strip(), g2_maximum_marks, target_assessment.strip(),
                target_maximum_marks, mode, assessment_day, file.filename, len(prepared),
            ),
        )
        batch_id = int(cursor.lastrowid)

        records_created = 0
        predictions_created = 0
        skipped_predictions = []
        absent_g1 = absent_g2 = missing_g1 = missing_g2 = 0

        for item in prepared:
            for assessment_name, maximum, marks, status in (
                (g1_assessment_name.strip(), g1_maximum_marks, item["g1"], item["g1_status"]),
                (g2_assessment_name.strip(), g2_maximum_marks, item["g2"], item["g2_status"]),
            ):
                cursor.execute(
                    """INSERT INTO assessment_records
                       (student_id, assessment_name, obtained_marks, maximum_marks, assessment_date, record_status, batch_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (item["student_id"], assessment_name, marks, maximum, assessment_day, status, batch_id),
                )
                records_created += 1
            absent_g1 += item["g1_status"] == "absent"
            absent_g2 += item["g2_status"] == "absent"
            missing_g1 += item["g1_status"] == "missing"
            missing_g2 += item["g2_status"] == "missing"

            if item["predicted_score"] is None:
                reasons = []
                if item["g1_status"] != "present":
                    reasons.append(f"{g1_assessment_name}: {item['g1_status']}")
                if item["g2_status"] != "present":
                    reasons.append(f"{g2_assessment_name}: {item['g2_status']}")
                skipped_predictions.append({
                    "student_id": item["student_id"],
                    "roll_number": item["roll_number"],
                    "reason": "; ".join(reasons) or "Required detailed features unavailable",
                })
                continue

            input_payload = {
                "source": "class_assessment_upload",
                "roll_number": item["roll_number"],
                "g1_actual": item["g1"],
                "g1_maximum_marks": g1_maximum_marks,
                "g2_actual": item["g2"],
                "g2_maximum_marks": g2_maximum_marks,
                "normalized_model_inputs": item["model_features"],
            }
            cursor.execute(
                """INSERT INTO predictions
                   (student_id, class_id, mode, regression_score, classification_label,
                    risk_status, input_data, model_version, target_assessment,
                    target_maximum_marks, predicted_marks, batch_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    item["student_id"], class_id, mode, item["predicted_score"], None,
                    item["risk_status"], json.dumps(input_payload), "gradify-v1",
                    target_assessment.strip(), target_maximum_marks, item["predicted_marks"], batch_id,
                ),
            )
            predictions_created += 1

        cursor.execute(
            """UPDATE assessment_batches
               SET assessment_records_created = %s, predictions_created = %s, predictions_skipped = %s
               WHERE batch_id = %s""",
            (records_created, predictions_created, len(skipped_predictions), batch_id),
        )
        connection.commit()
        rows_not_uploaded = sorted(set(roster) - {item["roll_number"] for item in rows})
        return {
            "message": "Assessment upload processed successfully.",
            "batch_id": batch_id,
            "class_id": class_id,
            "mode": mode,
            "target_assessment": target_assessment.strip(),
            "target_maximum_marks": target_maximum_marks,
            "students_in_file": len(prepared),
            "assessment_records_created": records_created,
            "predictions_created": predictions_created,
            "predictions_skipped": skipped_predictions,
            "absence_counts": {"G1": absent_g1, "G2": absent_g2},
            "missing_counts": {"G1": missing_g1, "G2": missing_g2},
            "students_not_in_file": rows_not_uploaded,
        }
    except HTTPException:
        connection.rollback()
        raise
    except mysql.connector.Error as exc:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while saving assessment: {exc}")
    except Exception as exc:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"Assessment upload failed: {exc}")
    finally:
        cursor.close()
        connection.close()


@router.get("/classrooms/{class_id}/assessments")
def get_class_assessments(class_id: int, teacher: dict = Depends(get_current_teacher)):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        cursor.execute(
            """SELECT ar.record_id, ar.batch_id, ar.student_id, s.student_name, s.roll_number,
                      ar.assessment_name, ar.obtained_marks, ar.maximum_marks,
                      ar.record_status, ar.assessment_date, ar.created_at
               FROM assessment_records ar
               JOIN students s ON s.student_id = ar.student_id
               WHERE s.class_id = %s
               ORDER BY ar.created_at DESC, s.roll_number, ar.assessment_name""",
            (class_id,),
        )
        records = cursor.fetchall()
        return {"class_id": class_id, "total_records": len(records), "assessments": records}
    finally:
        cursor.close()
        connection.close()


@router.get("/classrooms/{class_id}/predictions")
def get_class_predictions(class_id: int, teacher: dict = Depends(get_current_teacher)):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        cursor.execute(
            """SELECT p.prediction_id, p.batch_id, p.student_id, s.student_name, s.roll_number,
                      p.mode, p.regression_score, p.risk_status, p.target_assessment,
                      p.target_maximum_marks, p.predicted_marks, p.created_at
               FROM predictions p
               JOIN students s ON s.student_id = p.student_id
               WHERE p.class_id = %s
               ORDER BY p.created_at DESC, s.roll_number""",
            (class_id,),
        )
        predictions = cursor.fetchall()
        return {"class_id": class_id, "total_predictions": len(predictions), "predictions": predictions}
    finally:
        cursor.close()
        connection.close()


@router.get("/students/me/assessments")
def get_my_assessments(student: dict = Depends(get_current_student)):
    student_id = int(student["sub"])
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT record_id, batch_id, assessment_name, obtained_marks, maximum_marks,
                      record_status, assessment_date, created_at
               FROM assessment_records WHERE student_id = %s
               ORDER BY created_at DESC""",
            (student_id,),
        )
        records = cursor.fetchall()
        return {"student_id": student_id, "total_records": len(records), "assessments": records}
    finally:
        cursor.close()
        connection.close()


@router.get("/students/me/predictions")
def get_my_predictions(student: dict = Depends(get_current_student)):
    student_id = int(student["sub"])
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT prediction_id, batch_id, mode, regression_score, risk_status,
                      target_assessment, target_maximum_marks, predicted_marks, created_at
               FROM predictions WHERE student_id = %s
               ORDER BY created_at DESC""",
            (student_id,),
        )
        records = cursor.fetchall()
        return {"student_id": student_id, "total_predictions": len(records), "predictions": records}
    finally:
        cursor.close()
        connection.close()


@router.get("/classrooms/{class_id}/assessment-batches")
def get_assessment_batches(class_id: int, teacher: dict = Depends(get_current_teacher)):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        cursor.execute(
            """SELECT batch_id, g1_assessment_name, g1_maximum_marks,
                      g2_assessment_name, g2_maximum_marks, target_assessment,
                      target_maximum_marks, mode, assessment_date, original_filename,
                      students_in_file, assessment_records_created, predictions_created,
                      predictions_skipped, created_at
               FROM assessment_batches WHERE class_id = %s
               ORDER BY created_at DESC, batch_id DESC""",
            (class_id,),
        )
        batches = cursor.fetchall()
        return {"class_id": class_id, "total_batches": len(batches), "batches": batches}
    finally:
        cursor.close()
        connection.close()


@router.get("/classrooms/{class_id}/assessment-batches/{batch_id}")
def get_assessment_batch_details(
    class_id: int, batch_id: int, teacher: dict = Depends(get_current_teacher)
):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        cursor.execute(
            "SELECT * FROM assessment_batches WHERE batch_id = %s AND class_id = %s",
            (batch_id, class_id),
        )
        batch = cursor.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Assessment batch not found.")
        cursor.execute(
            """SELECT ar.record_id, ar.student_id, s.student_name, s.roll_number,
                      ar.assessment_name, ar.obtained_marks, ar.maximum_marks,
                      ar.record_status, ar.assessment_date
               FROM assessment_records ar JOIN students s ON s.student_id = ar.student_id
               WHERE ar.batch_id = %s AND s.class_id = %s
               ORDER BY s.roll_number, ar.assessment_name""",
            (batch_id, class_id),
        )
        assessments = cursor.fetchall()
        cursor.execute(
            """SELECT p.prediction_id, p.student_id, s.student_name, s.roll_number,
                      p.mode, p.regression_score, p.risk_status, p.target_assessment,
                      p.target_maximum_marks, p.predicted_marks, p.created_at
               FROM predictions p JOIN students s ON s.student_id = p.student_id
               WHERE p.batch_id = %s AND p.class_id = %s
               ORDER BY s.roll_number""",
            (batch_id, class_id),
        )
        predictions = cursor.fetchall()
        return {"batch": batch, "assessments": assessments, "predictions": predictions}
    finally:
        cursor.close()
        connection.close()


@router.get("/classrooms/{class_id}/analytics")
def get_classroom_analytics(class_id: int, teacher: dict = Depends(get_current_teacher)):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        cursor.execute("SELECT COUNT(*) AS total_students FROM students WHERE class_id = %s", (class_id,))
        total_students = int(cursor.fetchone()["total_students"])
        cursor.execute(
            """SELECT p.student_id, p.regression_score, p.risk_status
               FROM predictions p
               JOIN (SELECT student_id, MAX(prediction_id) AS latest_id
                     FROM predictions WHERE class_id = %s GROUP BY student_id) latest
                 ON latest.latest_id = p.prediction_id
               WHERE p.class_id = %s""",
            (class_id, class_id),
        )
        latest = cursor.fetchall()
        predicted_count = len(latest)
        at_risk = sum(1 for row in latest if row["risk_status"] == "At Risk")
        not_at_risk = sum(1 for row in latest if row["risk_status"] == "Not At Risk")
        scores = [float(row["regression_score"]) for row in latest if row["regression_score"] is not None]
        return {
            "class_id": class_id,
            "total_students": total_students,
            "students_with_predictions": predicted_count,
            "students_without_predictions": max(0, total_students - predicted_count),
            "at_risk_count": at_risk,
            "not_at_risk_count": not_at_risk,
            "average_predicted_score": round(sum(scores) / len(scores), 2) if scores else None,
            "latest_predictions_only": True,
        }
    finally:
        cursor.close()
        connection.close()


@router.get("/classrooms/{class_id}/students/at-risk")
def get_classroom_at_risk_students(class_id: int, teacher: dict = Depends(get_current_teacher)):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        cursor.execute(
            """SELECT p.prediction_id, p.student_id, s.student_name, s.roll_number,
                      p.regression_score, p.target_assessment, p.target_maximum_marks,
                      p.predicted_marks, p.mode, p.created_at
               FROM predictions p
               JOIN students s ON s.student_id = p.student_id
               JOIN (SELECT student_id, MAX(prediction_id) AS latest_id
                     FROM predictions WHERE class_id = %s GROUP BY student_id) latest
                 ON latest.latest_id = p.prediction_id
               WHERE p.class_id = %s AND p.risk_status = 'At Risk'
               ORDER BY p.regression_score ASC""",
            (class_id, class_id),
        )
        students = cursor.fetchall()
        return {"class_id": class_id, "total_at_risk": len(students), "students": students}
    finally:
        cursor.close()
        connection.close()


@router.get("/classrooms/{class_id}/analytics/score-count")
def get_classroom_score_count(
    class_id: int, score: float, teacher: dict = Depends(get_current_teacher)
):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        cursor.execute(
            """SELECT COUNT(*) AS student_count
               FROM predictions p
               JOIN (SELECT student_id, MAX(prediction_id) AS latest_id
                     FROM predictions WHERE class_id = %s GROUP BY student_id) latest
                 ON latest.latest_id = p.prediction_id
               WHERE p.class_id = %s AND ROUND(p.regression_score) = ROUND(%s)""",
            (class_id, class_id, score),
        )
        count = int(cursor.fetchone()["student_count"])
        return {
            "class_id": class_id,
            "requested_score": score,
            "matching_students": count,
            "basis": "latest prediction per student; regression_score rounded to nearest whole mark out of 20",
        }
    finally:
        cursor.close()
        connection.close()

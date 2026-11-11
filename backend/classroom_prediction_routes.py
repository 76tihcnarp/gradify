import json
from pathlib import Path
from typing import Optional

import joblib
import mysql.connector
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.db import get_db_connection
from backend.classroom_routes import ensure_teacher_owns_class, get_current_teacher

router = APIRouter(tags=["Manual Classroom Predictions and Student Profiles"])

BASE_DIR = Path(__file__).resolve().parent.parent
try:
    QUICK_REGRESSION = joblib.load(BASE_DIR / "ml" / "gradify_quick_regression.pkl")
    DETAILED_REGRESSION = joblib.load(BASE_DIR / "ml" / "gradify_detailed_regression.pkl")
except Exception as exc:
    print(f"WARNING: Manual prediction models could not be loaded: {exc}")
    QUICK_REGRESSION = None
    DETAILED_REGRESSION = None


class ManualQuickPrediction(BaseModel):
    student_id: int = Field(gt=0)
    g1_marks: float = Field(ge=0)
    g1_maximum_marks: float = Field(gt=0)
    g2_marks: float = Field(ge=0)
    g2_maximum_marks: float = Field(gt=0)
    target_assessment: str = Field(min_length=1, max_length=100)
    target_maximum_marks: float = Field(gt=0)


class ManualDetailedPrediction(ManualQuickPrediction):
    failures: int = Field(ge=0)
    absences: int = Field(ge=0)
    studytime: int = Field(ge=1, le=4)


def _validate_marks(data: ManualQuickPrediction):
    if data.g1_marks > data.g1_maximum_marks:
        raise HTTPException(status_code=422, detail="G1 marks cannot exceed G1 maximum marks.")
    if data.g2_marks > data.g2_maximum_marks:
        raise HTTPException(status_code=422, detail="G2 marks cannot exceed G2 maximum marks.")
    if not data.target_assessment.strip():
        raise HTTPException(status_code=422, detail="Target assessment name cannot be blank.")


def _run_prediction(mode: str, data):
    model = QUICK_REGRESSION if mode == "quick" else DETAILED_REGRESSION
    if model is None:
        raise HTTPException(status_code=500, detail=f"{mode.title()} regression model is not loaded.")

    normalized = {
        "G1": data.g1_marks / data.g1_maximum_marks * 20,
        "G2": data.g2_marks / data.g2_maximum_marks * 20,
    }
    if mode == "detailed":
        normalized.update({
            "failures": data.failures,
            "absences": data.absences,
            "studytime": data.studytime,
        })

    expected = list(getattr(model, "feature_names_in_", normalized.keys()))
    missing = [feature for feature in expected if feature not in normalized]
    if missing:
        raise HTTPException(status_code=500, detail=f"Model feature configuration mismatch: {missing}")
    frame = pd.DataFrame([[normalized[name] for name in expected]], columns=expected)
    score = float(model.predict(frame)[0])
    return score, normalized


def _save_manual_prediction(class_id: int, teacher_id: int, mode: str, data, score: float, normalized: dict):
    risk_status = "At Risk" if score <= 10 else "Not At Risk"
    predicted_marks = score / 20 * data.target_maximum_marks
    input_data = {
        "student_id": data.student_id,
        "raw_g1_marks": data.g1_marks,
        "g1_maximum_marks": data.g1_maximum_marks,
        "raw_g2_marks": data.g2_marks,
        "g2_maximum_marks": data.g2_maximum_marks,
        **normalized,
    }

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        ensure_teacher_owns_class(cursor, class_id, teacher_id)
        cursor.execute(
            "SELECT student_id FROM students WHERE student_id = %s AND class_id = %s",
            (data.student_id, class_id),
        )
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Student not found in this classroom.")

        cursor.execute(
            """INSERT INTO predictions
               (student_id, class_id, mode, regression_score, classification_label,
                risk_status, input_data, model_version, target_assessment,
                target_maximum_marks, predicted_marks)
               VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, %s)""",
            (
                data.student_id,
                class_id,
                mode,
                round(score, 2),
                risk_status,
                json.dumps(input_data),
                "gradify-v1",
                data.target_assessment.strip(),
                data.target_maximum_marks,
                round(predicted_marks, 2),
            ),
        )
        prediction_id = cursor.lastrowid
        connection.commit()
        return {
            "message": "Manual prediction saved successfully.",
            "prediction_id": prediction_id,
            "student_id": data.student_id,
            "class_id": class_id,
            "mode": mode,
            "regression_score": round(score, 2),
            "risk_status": risk_status,
            "target_assessment": data.target_assessment.strip(),
            "target_maximum_marks": data.target_maximum_marks,
            "predicted_marks": round(predicted_marks, 2),
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


@router.post("/classrooms/{class_id}/predict/quick")
def manual_quick_prediction(
    class_id: int,
    data: ManualQuickPrediction,
    teacher: dict = Depends(get_current_teacher),
):
    _validate_marks(data)
    score, normalized = _run_prediction("quick", data)
    return _save_manual_prediction(class_id, int(teacher["sub"]), "quick", data, score, normalized)


@router.post("/classrooms/{class_id}/predict/detailed")
def manual_detailed_prediction(
    class_id: int,
    data: ManualDetailedPrediction,
    teacher: dict = Depends(get_current_teacher),
):
    _validate_marks(data)
    score, normalized = _run_prediction("detailed", data)
    return _save_manual_prediction(class_id, int(teacher["sub"]), "detailed", data, score, normalized)


@router.get("/classrooms/{class_id}/students/{student_id}")
def get_classroom_student_profile(
    class_id: int,
    student_id: int,
    teacher: dict = Depends(get_current_teacher),
):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        ensure_teacher_owns_class(cursor, class_id, int(teacher["sub"]))
        cursor.execute(
            """SELECT student_id, student_name, roll_number, created_at
               FROM students WHERE student_id = %s AND class_id = %s""",
            (student_id, class_id),
        )
        student = cursor.fetchone()
        if student is None:
            raise HTTPException(status_code=404, detail="Student not found in this classroom.")

        cursor.execute(
            """SELECT record_id, batch_id, assessment_name, obtained_marks,
                      maximum_marks, record_status, assessment_date, created_at
               FROM assessment_records WHERE student_id = %s
               ORDER BY COALESCE(assessment_date, DATE(created_at)) DESC, record_id DESC""",
            (student_id,),
        )
        assessments = cursor.fetchall()

        cursor.execute(
            """SELECT prediction_id, batch_id, mode, regression_score, risk_status,
                      target_assessment, target_maximum_marks, predicted_marks, created_at
               FROM predictions WHERE student_id = %s AND class_id = %s
               ORDER BY prediction_id DESC LIMIT 10""",
            (student_id, class_id),
        )
        predictions = cursor.fetchall()
        return {
            "class_id": class_id,
            "student": student,
            "total_assessments": len(assessments),
            "assessments": assessments,
            "recent_predictions": predictions,
        }
    finally:
        cursor.close()
        connection.close()

import json
from backend.db import get_db_connection

import io
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import joblib
import pandas as pd
from pydantic import BaseModel
from backend.classroom_routes import router as classroom_router

# ------------------------------------------------------------------
# 1. INITIALIZATION & APP SETUP
# ------------------------------------------------------------------
app = FastAPI(
    title="GRADIFY API",
    description="Student Performance Prediction and Classroom Monitoring System",
    version="1.0.0",
)
app.include_router(classroom_router)

# Enable CORS for React Frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------
# 2. LOAD ML MODELS & DATASET
# ------------------------------------------------------------------
try:
    quick_regression = joblib.load(
        BASE_DIR / "ml" / "gradify_quick_regression.pkl"
    )
    quick_classification = joblib.load(
        BASE_DIR / "ml" / "gradify_quick_classification.pkl"
    )
    detailed_regression = joblib.load(
        BASE_DIR / "ml" / "gradify_detailed_regression.pkl"
    )
    detailed_classification = joblib.load(
        BASE_DIR / "ml" / "gradify_detailed_classification.pkl"
    )
    print("✅ All ML models loaded successfully.")
except Exception as e:
    print(f"⚠️ Warning: Could not load ML models: {e}")
    quick_regression = None
    quick_classification = None
    detailed_regression = None
    detailed_classification = None

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "ml" / "student-math.csv"
try:
    students_df = pd.read_csv(DATA_PATH, sep=";")
    print(
        f"✅ Loaded {len(students_df)} student records from {DATA_PATH}."
    )
except Exception as e:
    students_df = None
    print(f"⚠️ Warning: Could not load dataset at {DATA_PATH}. Error: {e}")

# In-memory progress database (maps student_id -> progress record)
DEFAULT_CURRICULUM = [
    "Algebra & Functions",
    "Trigonometry",
    "Calculus Fundamentals",
    "Probability & Statistics",
    "Geometry & Vectors",
]

progress_db: Dict[int, dict] = {}
def save_prediction(student_data: dict, mode: str, predicted_score: float, risk_status: str):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        student_id = student_data.get("student_id")

        if student_id is not None:
            student_id = int(student_id)

        cursor.execute(
            """
            INSERT INTO predictions
            (student_id, mode, regression_score, classification_label,
             risk_status, input_data, model_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                student_id,
                mode,
                predicted_score,
                None,
                risk_status,
                json.dumps(student_data),
                "gradify-v1",
            ),
        )

        connection.commit()

    except Exception as e:
        if connection:
            connection.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Could not save prediction to database: {str(e)}",
        )

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

# 4. API ENDPOINTS
# ------------------------------------------------------------------


@app.get("/")
def home():
    return {"message": "Gradify API is running!", "status": "active"}


# --- PREDICTION ENDPOINTS ---


@app.post("/predict/quick")
def quick_predict(student_data: dict):
    if quick_regression is None:
        raise HTTPException(
            status_code=500,
            detail="Quick regression model is not loaded."
        )

    model_data = {
        key: value
        for key, value in student_data.items()
        if key != "student_id"
    }

    input_data = pd.DataFrame([model_data])
    predicted_score = float(quick_regression.predict(input_data)[0])
    risk_status = "At Risk" if predicted_score <= 10 else "Not At Risk"

    return {
        "mode": "quick",
        "predicted_score": round(predicted_score, 2),
        "risk_status": risk_status,
    }


# ------------------------------------------------------------------
# 3. Predict detailed
# ------------------------------------------------------------------

def run_detailed_prediction(student_data: dict) -> dict:
    """Predict a student's final score without substituting the actual grade."""
    if detailed_regression is None:
        raise HTTPException(
            status_code=500,
            detail="Detailed regression model is not loaded.",
        )

    input_df = prepare_detailed_input(student_data)
    predicted_score = float(detailed_regression.predict(input_df)[0])

    return {
        "predicted_score": round(predicted_score, 2),
        "risk_status": (
            "At Risk" if predicted_score <= 10 else "Not At Risk"
        ),
    }


    # Fallback to G3 if model inference fails
    g3 = float(student_data.get("G3", 10))
    return {
        "predicted_score": g3,
        "risk_status": "At Risk" if g3 < 10 else "Not At Risk",
    }

def prepare_detailed_input(student_data: dict) -> pd.DataFrame:
    """Arrange input features in the exact order expected by the trained model."""
    expected_features = list(detailed_regression.feature_names_in_)

    missing_features = [
        feature for feature in expected_features
        if feature not in student_data
    ]

    if missing_features:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required features: {missing_features}"
        )

    return pd.DataFrame(
        [[student_data[feature] for feature in expected_features]],
        columns=expected_features
    )


@app.post("/predict/detailed")
def detailed_predict(student_data: dict):
    if detailed_regression is None:
        raise HTTPException(
            status_code=500,
            detail="Detailed regression model is not loaded."
        )

    input_data = prepare_detailed_input(student_data)
    predicted_score = float(detailed_regression.predict(input_data)[0])
    risk_status = "At Risk" if predicted_score <= 10 else "Not At Risk"

    return {
        "mode": "detailed",
        "predicted_score": round(predicted_score, 2),
        "risk_status": risk_status,
    }

# ------------------------------------------------------------------


# --- STUDENT MANAGEMENT ENDPOINTS ---

def pick_model(columns):
    """Detailed if all its columns exist, else quick."""
    cols = set(columns)
    for mode, model in (("detailed", detailed_regression), ("quick", quick_regression)):
        if model is not None and set(model.feature_names_in_) <= cols:
            return mode, model
    return None, None


@app.post("/students/upload")
async def upload_students_csv(file: UploadFile = File(...), save: bool = False):
    global students_df

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    contents = await file.read()
    try:
        text = contents.decode("utf-8-sig")
        sep = ";" if ";" in text.splitlines()[0] else ","
        df = pd.read_csv(io.StringIO(text), sep=sep)
        ALIASES = {
         "g1": "G1", "grade1": "G1", "term1": "G1", "mark1": "G1","st1":"G1","ST1":"G1",
         "g2": "G2", "grade2": "G2", "term2": "G2", "mark2": "G2","st2":"G1","ST2":"G1",
         "studentid": "student_id", "roll no": "student_id", "rollno": "student_id",
             }
        df.columns = [ALIASES.get(str(c).strip().lower(), str(c).strip()) for c in df.columns]

        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read CSV: {e}")

    if df.empty:
        raise HTTPException(status_code=400, detail="The CSV has no records.")

    mode, model = pick_model(df.columns)
    if model is None:
        raise HTTPException(status_code=422, detail="CSV is missing columns needed by the models.")

    scores = model.predict(df[list(model.feature_names_in_)])
    ids = df["student_id"].astype(int).tolist() if "student_id" in df.columns \
        else list(range(1, len(df) + 1))

    results = []
    for i, score in enumerate(scores):
        score = float(score)
        results.append({
            "student_id": ids[i],
            "predicted_score": round(score, 2),
            "risk_status": "At Risk" if score <= 10 else "Not At Risk",
        })

    saved = 0
    if save:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT student_id FROM students")
            valid = {r[0] for r in cur.fetchall()}
            for i, r in enumerate(results):
                if r["student_id"] not in valid:
                    continue
                cur.execute("DELETE FROM predictions WHERE student_id = %s", (r["student_id"],))
                cur.execute(
                    """INSERT INTO predictions
                       (student_id, mode, regression_score, risk_status, input_data, model_version)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (r["student_id"], mode, r["predicted_score"], r["risk_status"],
                     json.dumps(df.iloc[i].to_dict(), default=str), "gradify-v1"),
                )
                saved += 1
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Could not save: {e}")
        finally:
            cur.close()
            conn.close()

    students_df = df.reset_index(drop=True)
    return {"mode": mode, "total": len(results), "saved": saved, "results": results}


# --- ANALYTICS & AT-RISK ENDPOINTS ---


@app.get("/students/at-risk")
def get_at_risk_students():
    global students_df

    if students_df is None or students_df.empty:
        try:
            students_df = pd.read_csv(DATA_PATH, sep=";")
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Could not load dataset: {str(e)}"
            )

    at_risk_list = []

    for idx, row in students_df.iterrows():
        student_id = int(idx + 1)
        g3 = float(row.get("G3", 0))
        g2 = float(row.get("G2", 0))
        failures = int(row.get("failures", 0))
        absences = int(row.get("absences", 0))
        studytime = int(row.get("studytime", 0))

        is_at_risk = (g3 < 10) if "G3" in row else (g2 < 10 or failures > 0)

        if is_at_risk:
            risk_factors = []
            if failures > 0:
                risk_factors.append(f"Past failures: {failures}")
            if absences > 8:
                risk_factors.append(f"High absences: {absences} days")
            if studytime < 2:
                risk_factors.append("Low weekly study time: < 2 hrs")
            if g2 < 10:
                risk_factors.append(f"Low G2 score: {g2}/20")

            at_risk_list.append(
                {
                    "student_id": student_id,
                    "school": str(row.get("school", "N/A")),
                    "age": int(row.get("age", 0)),
                    "g2_score": g2,
                    "g3_score": g3,
                    "failures": failures,
                    "absences": absences,
                    "risk_factors": risk_factors,
                }
            )

    return {
        "total_students": len(students_df),
        "at_risk_count": len(at_risk_list),
        "at_risk_percentage": round(
            (len(at_risk_list) / len(students_df)) * 100, 2
        ),
        "at_risk_students": at_risk_list,
    }


@app.get("/students/{student_id}")
def get_student_by_id(student_id: int):
    global students_df

    if students_df is None or students_df.empty:
        try:
            students_df = pd.read_csv(DATA_PATH, sep=";")
        except Exception:
            raise HTTPException(
                status_code=500, detail="Student dataset not loaded on server."
            )

    row_idx = student_id - 1

    if row_idx < 0 or row_idx >= len(students_df):
        raise HTTPException(
            status_code=404, detail=f"Student with ID {student_id} not found."
        )

    student_data = students_df.iloc[row_idx].to_dict()
  
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
    "SELECT regression_score, risk_status FROM predictions "
    "WHERE student_id = %s ORDER BY prediction_id DESC LIMIT 1",
    (student_id,),
    )
    saved = cur.fetchone()
    cur.close()
    conn.close()
    prediction_result = {
    "predicted_score": float(saved["regression_score"]) if saved else None,
    "risk_status": saved["risk_status"] if saved else "Not published yet",
    }

    return {
        "student_id": student_id,
        "profile": {
            "age": student_data.get("age"),
            "sex": student_data.get("sex"),
            "school": student_data.get("school"),
            "guardian": student_data.get("guardian"),
        },
        "academic_history": {
            "G1": student_data.get("G1"),
            "G2": student_data.get("G2"),
            "studytime": student_data.get("studytime"),
            "failures": student_data.get("failures"),
            "absences": student_data.get("absences"),
        },
        "ml_insights": {
            "predicted_final_score": prediction_result.get("predicted_score"),
            "risk_status": prediction_result.get("risk_status"),
        },
        "raw_details": student_data,
    }


@app.get("/analytics")
def get_class_analytics():
    global students_df

    if students_df is None or students_df.empty:
        try:
            students_df = pd.read_csv(DATA_PATH, sep=";")
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Could not load dataset: {str(e)}"
            )

    total_students = len(students_df)
    g3_scores = (
        students_df["G3"] if "G3" in students_df else students_df["G2"]
    )
    passed_students = int((g3_scores >= 10).sum())
    failed_students = int((g3_scores < 10).sum())

    study_impact = {}
    if "studytime" in students_df and "G3" in students_df:
        grouped = (
            students_df.groupby("studytime")["G3"].mean().round(2).to_dict()
        )
        study_impact = {
            f"studytime_level_{k}": v for k, v in grouped.items()
        }

    return {
        "summary": {
            "total_students": total_students,
            "pass_count": passed_students,
            "fail_count": failed_students,
            "pass_rate_percentage": round(
                (passed_students / total_students) * 100, 2
            ),
        },
        "grade_averages": {
            "G1_avg": round(float(students_df["G1"].mean()), 2)
            if "G1" in students_df
            else None,
            "G2_avg": round(float(students_df["G2"].mean()), 2)
            if "G2" in students_df
            else None,
            "G3_avg": round(float(students_df["G3"].mean()), 2)
            if "G3" in students_df
            else None,
            "max_score": float(g3_scores.max()),
            "min_score": float(g3_scores.min()),
        },
        "study_time_vs_avg_score": study_impact,
        "class_attendance": {
            "avg_absences": round(float(students_df["absences"].mean()), 2)
            if "absences" in students_df
            else 0,
            "max_absences": int(students_df["absences"].max())
            if "absences" in students_df
            else 0,
        },
    }


@app.get("/analytics/score-count")
def get_score_count(score: Optional[int] = None):
    """Counts SAVED predicted scores. Add ?score=13 to get the count for one mark."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT ROUND(regression_score), COUNT(*) FROM predictions "
            "GROUP BY ROUND(regression_score) ORDER BY 1"
        )
        distribution = [
            {"score": int(s), "student_count": int(c)} for s, c in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()

    result = {
        "total_students": sum(d["student_count"] for d in distribution),
        "distribution": distribution,
    }
    if score is not None:
        result["score"] = score
        result["student_count"] = next(
            (d["student_count"] for d in distribution if d["score"] == score), 0
        )
    return result

# --- PROGRESS TRACKING ENDPOINTS ---


class ProgressUpdate(BaseModel):
    student_id: int
    completed_topic: str


@app.get("/progress/{student_id}")
def get_student_progress(student_id: int):
    global progress_db

    if student_id not in progress_db:
        progress_db[student_id] = {
            "student_id": student_id,
            "total_topics": len(DEFAULT_CURRICULUM),
            "completed_topics": [],
            "remaining_topics": list(DEFAULT_CURRICULUM),
        }

    record = progress_db[student_id]
    completed_count = len(record["completed_topics"])
    total_count = record["total_topics"]
    completion_percentage = (
        round((completed_count / total_count) * 100, 2)
        if total_count > 0
        else 0.0
    )

    return {
        "student_id": student_id,
        "completion_percentage": completion_percentage,
        "completed_count": completed_count,
        "total_topics": total_count,
        "completed_topics": record["completed_topics"],
        "remaining_topics": record["remaining_topics"],
    }


@app.post("/progress")
def update_student_progress(data: ProgressUpdate):
    global progress_db
    student_id = data.student_id
    topic = data.completed_topic.strip()

    if student_id < 1 or (
        students_df is not None and student_id > len(students_df)
    ):
        raise HTTPException(
            status_code=404,
            detail=f"Student with ID {student_id} not found.",
        )

    if topic not in DEFAULT_CURRICULUM:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid topic. Choose one of: {DEFAULT_CURRICULUM}"
            ),
        )

    if student_id not in progress_db:
        progress_db[student_id] = {
            "student_id": student_id,
            "total_topics": len(DEFAULT_CURRICULUM),
            "completed_topics": [],
            "remaining_topics": list(DEFAULT_CURRICULUM),
        }

    record = progress_db[student_id]

    if topic in record["completed_topics"]:
        return {
            "message": f"Topic '{topic}' is already marked as completed.",
            "student_id": student_id,
        }

    record["completed_topics"].append(topic)
    if topic in record["remaining_topics"]:
        record["remaining_topics"].remove(topic)

    completed_count = len(record["completed_topics"])
    total_count = record["total_topics"]
    completion_percentage = round((completed_count / total_count) * 100, 2)

    return {
        "message": f"Progress updated successfully for student {student_id}!",
        "student_id": student_id,
        "just_completed": topic,
        "completion_percentage": completion_percentage,
        "completed_topics": record["completed_topics"],
        "remaining_topics": record["remaining_topics"],
    }
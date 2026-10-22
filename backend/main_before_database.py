import io
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import joblib
import pandas as pd
from pydantic import BaseModel

# ------------------------------------------------------------------
# 1. INITIALIZATION & APP SETUP
# ------------------------------------------------------------------
app = FastAPI(
    title="GRADIFY API",
    description="Intelligent Student Performance Prediction and Academic Progress Tracking System",
    version="1.0.0",
)

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
            status_code=500, detail="Quick regression model is not loaded."
        )

    input_data = pd.DataFrame([student_data])
    predicted_score = quick_regression.predict(input_data)[0]
    risk_status = "At Risk" if predicted_score <= 10 else "Not At Risk"

    return {
        "mode": "quick",
        "predicted_score": round(float(predicted_score), 2),
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
    predicted_score = detailed_regression.predict(input_data)[0]
    risk_status = "At Risk" if predicted_score <= 10 else "Not At Risk"

    return {
        "mode": "detailed",
        "predicted_score": round(float(predicted_score), 2),
        "risk_status": risk_status,
    }

# ------------------------------------------------------------------


# --- STUDENT MANAGEMENT ENDPOINTS ---

@app.post("/students/upload")
async def upload_students_csv(file: UploadFile = File(...)):
    global students_df

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Please upload a CSV file.",
        )

    try:
        contents = await file.read()

        if not contents:
            raise HTTPException(
                status_code=400,
                detail="The uploaded CSV file is empty.",
            )

        csv_string = contents.decode("utf-8-sig")
        first_line = csv_string.splitlines()[0]
        delimiter = ";" if ";" in first_line else ","

        new_df = pd.read_csv(
            io.StringIO(csv_string),
            sep=delimiter,
        )

        if new_df.empty:
            raise HTTPException(
                status_code=400,
                detail="The uploaded CSV file contains no student records.",
            )

        if new_df.columns.duplicated().any():
            raise HTTPException(
                status_code=400,
                detail="The CSV contains duplicate column names.",
            )

        # Replace existing in-memory student data instead of appending.
        students_df = new_df.reset_index(drop=True)

        return {
            "status": "success",
            "filename": file.filename,
            "records_loaded": len(students_df),
            "total_students_in_system": len(students_df),
            "detected_delimiter": delimiter,
        }

    except HTTPException:
        raise

    except (UnicodeDecodeError, pd.errors.ParserError, ValueError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to process CSV file: {str(e)}",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process CSV file: {str(e)}",
        )


# --- ANALYTICS & AT-RISK ENDPOINTS ---


@app.get("/students/at-risk")
def get_at_risk_students():
    global students_df

    if students_df is None or students_df.empty:
        try:
            students_df = pd.read_csv("student-math.csv", sep=";")
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
    prediction_result = run_detailed_prediction(student_data)

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
            students_df = pd.read_csv("student-math.csv", sep=";")
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
    if "studytime" in students_df:
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
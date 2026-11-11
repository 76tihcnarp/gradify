from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.classroom_routes import router as classroom_router
from backend.assessment_routes import router as assessment_router
from backend.classroom_features_routes import router as classroom_features_router
from backend.classroom_prediction_routes import router as classroom_prediction_router

app = FastAPI(
    title="GRADIFY API",
    description="Intelligent Student Performance Prediction and Academic Progress Tracking System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(classroom_router)
app.include_router(assessment_router)
app.include_router(classroom_features_router)
app.include_router(classroom_prediction_router)


@app.get("/")
def home():
    return {"message": "Gradify API is running!", "status": "active"}

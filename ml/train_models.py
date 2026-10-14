# %%
import pandas as pd
import joblib

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.metrics import mean_absolute_error, r2_score, accuracy_score, f1_score


# Load dataset
df = pd.read_csv("student-math.csv", sep=";")


# =====================================================
# QUICK MODE
# G1 + G2
# =====================================================

quick_features = ["G1", "G2"]

X = df[quick_features]
y_reg = df["G3"]

# At-risk: G3 <= 10
y_class = (df["G3"] <= 10).astype(int)

X_train, X_test, y_train, y_test = train_test_split(
    X, y_reg, test_size=0.2, random_state=42
)

quick_regression = RandomForestRegressor(
    n_estimators=100,
    random_state=42
)

quick_regression.fit(X_train, y_train)

pred = quick_regression.predict(X_test)

print("QUICK REGRESSION")
print("MAE:", round(mean_absolute_error(y_test, pred), 2))
print("R2:", round(r2_score(y_test, pred), 3))


X_train, X_test, y_train, y_test = train_test_split(
    X, y_class, test_size=0.2, random_state=42
)

quick_classification = RandomForestClassifier(
    n_estimators=100,
    random_state=42
)

quick_classification.fit(X_train, y_train)

pred = quick_classification.predict(X_test)

print("QUICK CLASSIFICATION")
print("Accuracy:", round(accuracy_score(y_test, pred), 3))
print("F1:", round(f1_score(y_test, pred), 3))


# =====================================================
# DETAILED MODE
# G1 + G2 + failures + absences + studytime
# =====================================================

detailed_features = [
    "G1",
    "G2",
    "failures",
    "absences",
    "studytime"
]

X = df[detailed_features]


X_train, X_test, y_train, y_test = train_test_split(
    X, y_reg, test_size=0.2, random_state=42
)

detailed_regression = RandomForestRegressor(
    n_estimators=100,
    random_state=42
)

detailed_regression.fit(X_train, y_train)

pred = detailed_regression.predict(X_test)

print("\nDETAILED REGRESSION")
print("MAE:", round(mean_absolute_error(y_test, pred), 2))
print("R2:", round(r2_score(y_test, pred), 3))


X_train, X_test, y_train, y_test = train_test_split(
    X, y_class, test_size=0.2, random_state=42
)

detailed_classification = RandomForestClassifier(
    n_estimators=100,
    random_state=42
)

detailed_classification.fit(X_train, y_train)

pred = detailed_classification.predict(X_test)

print("DETAILED CLASSIFICATION")
print("Accuracy:", round(accuracy_score(y_test, pred), 3))
print("F1:", round(f1_score(y_test, pred), 3))


# =====================================================
# SAVE MODELS
# =====================================================

joblib.dump(
    quick_regression,
    "gradify_quick_regression.pkl"
)

joblib.dump(
    quick_classification,
    "gradify_quick_classification.pkl"
)

joblib.dump(
    detailed_regression,
    "gradify_detailed_regression.pkl"
)

joblib.dump(
    detailed_classification,
    "gradify_detailed_classification.pkl"
)

print("\nALL 4 MODELS SAVED SUCCESSFULLY!")
# %%

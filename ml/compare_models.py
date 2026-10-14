# %%
import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score


# Load dataset
df = pd.read_csv("student-math.csv", sep=";")


# -------------------------
# Model A: G1 + G2
# -------------------------

X = df[["G1", "G2"]]
y = df["G3"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

model_a = RandomForestRegressor(
    n_estimators=100,
    random_state=42
)

model_a.fit(X_train, y_train)

pred_a = model_a.predict(X_test)

print("MODEL A: G1 + G2")
print("MAE:", round(mean_absolute_error(y_test, pred_a), 2))
print("R2:", round(r2_score(y_test, pred_a), 3))


# -------------------------
# Model B: G1 + G2 + extras
# -------------------------

features = [
    "G1",
    "G2",
    "failures",
    "absences",
    "studytime"
]

X = df[features]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

model_b = RandomForestRegressor(
    n_estimators=100,
    random_state=42
)

model_b.fit(X_train, y_train)

pred_b = model_b.predict(X_test)

print("\nMODEL B: G1 + G2 + failures + absences + studytime")
print("MAE:", round(mean_absolute_error(y_test, pred_b), 2))
print("R2:", round(r2_score(y_test, pred_b), 3))
# %%

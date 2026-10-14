# %%
import pandas as pd

df = pd.read_csv("student-math.csv" ,sep=";")

print(df.head())
print(df.shape)
print(df.columns)

# %%
X = df.drop("G3", axis=1)
y = df["G3"]

print("Features:", X.shape)
print("Target:", y.shape)

# %%
print(df.info())
print(df.isnull().sum())
print(df.describe())

# %%
categorical_columns = X.select_dtypes(include="object").columns

print(categorical_columns)
print("Number of categorical columns:", len(categorical_columns))


# %%
numerical_columns = X.select_dtypes(include="number").columns

print(numerical_columns)
print("Number of numerical columns:", len(numerical_columns))

# %%
from sklearn.model_selection import train_test_split

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)

print("Training data:", X_train.shape)
print("Testing data:", X_test.shape)
# %%
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LinearRegression

preprocessor = ColumnTransformer(
    transformers=[
        ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical_columns)
    ],
    remainder="passthrough"
)

model = Pipeline([
    ("preprocessing", preprocessor),
    ("regression", LinearRegression())
])

# %%
X_train_processed = preprocessor.fit_transform(X_train)
X_test_processed = preprocessor.transform(X_test)

print(X_train_processed.shape)
print(X_test_processed.shape)
# %%
from sklearn.linear_model import LinearRegression

regression_model = LinearRegression()

regression_model.fit(X_train_processed, y_train)
# %%
predictions = regression_model.predict(X_test_processed)

print(predictions[:10])
# %%
comparison = pd.DataFrame({
    "Actual G3": y_test.values,
    "Predicted G3": predictions
})

print(comparison.head(10))
# %%
from sklearn.metrics import mean_absolute_error

mae = mean_absolute_error(y_test, predictions)

print("Mean Absolute Error:", mae)
# %%
from sklearn.metrics import r2_score

r2 = r2_score(y_test, predictions)

print("R² Score:", r2)
# %%
from sklearn.ensemble import RandomForestRegressor

rf_model = RandomForestRegressor(
    n_estimators=100,
    random_state=42
)

rf_model.fit(X_train_processed, y_train)

rf_predictions = rf_model.predict(X_test_processed)
# %%
rf_mae = mean_absolute_error(y_test, rf_predictions)
rf_r2 = r2_score(y_test, rf_predictions)

print("MAE:", rf_mae)
print("R²:", rf_r2)

# %%
df["At_Risk"] = (df["G3"] <= 10).astype(int)

print(df["At_Risk"].value_counts())

# %%
X_class = df.drop(columns=["G3", "At_Risk"])
y_class = df["At_Risk"]

categorical_class = X_class.select_dtypes(include="str").columns

print("Features:", X_class.shape)
print("Categorical:", len(categorical_class))

# %%
X_train_class, X_test_class, y_train_class, y_test_class = train_test_split(
    X_class,
    y_class,
    test_size=0.2,
    random_state=42,
    stratify=y_class
)

print("Training:", X_train_class.shape)
print("Testing:", X_test_class.shape)

# %%
class_preprocessor = ColumnTransformer(
    transformers=[
        ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical_class)
    ],
    remainder="passthrough"
)

X_train_class_processed = class_preprocessor.fit_transform(X_train_class)
X_test_class_processed = class_preprocessor.transform(X_test_class)

print(X_train_class_processed.shape)
print(X_test_class_processed.shape)

# %%
from sklearn.linear_model import LogisticRegression

logistic_model = LogisticRegression(max_iter=1000)

logistic_model.fit(X_train_class_processed, y_train_class)

# %%
class_predictions = logistic_model.predict(X_test_class_processed)

print(class_predictions[:10])

# %%
from sklearn.metrics import accuracy_score

accuracy = accuracy_score(y_test_class, class_predictions)

print("Accuracy:", accuracy)

# %%
from sklearn.metrics import classification_report

print(classification_report(
    y_test_class,
    class_predictions,
    target_names=["Not At Risk", "At Risk"]
))

# %%
from sklearn.ensemble import RandomForestClassifier

rf_classifier = RandomForestClassifier(
    n_estimators=100,
    random_state=42
)

rf_classifier.fit(X_train_class_processed, y_train_class)

# %%
rf_class_predictions = rf_classifier.predict(X_test_class_processed)

print(rf_class_predictions[:10])

# %%
from sklearn.metrics import classification_report

print(classification_report(
    y_test_class,
    rf_class_predictions,
    target_names=["Not At Risk", "At Risk"]
))

# %%
regression_pipeline = Pipeline([
    ("preprocessing", preprocessor),
    ("regression", RandomForestRegressor(
        n_estimators=100,
        random_state=42
    ))
])

regression_pipeline.fit(X_train, y_train)

# %%
classification_pipeline = Pipeline([
    ("preprocessing", class_preprocessor),
    ("classification", RandomForestClassifier(
        n_estimators=100,
        random_state=42
    ))
])

classification_pipeline.fit(X_train_class, y_train_class)

# %%
import joblib

joblib.dump(regression_pipeline, "gradify_regression.pkl")
joblib.dump(classification_pipeline, "gradify_classification.pkl")

print("Models saved successfully!")
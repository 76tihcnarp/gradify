
from pathlib import Path

import pandas as pd
import mysql.connector

from db import get_db_connection


BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "ml" / "student-math.csv"

# Preserve the original CSV column names and order.
ACADEMIC_COLUMNS = [
    "school", "sex", "age", "address", "famsize", "Pstatus",
    "Medu", "Fedu", "Mjob", "Fjob", "reason", "guardian",
    "traveltime", "studytime", "failures", "schoolsup",
    "famsup", "paid", "activities", "nursery", "higher",
    "internet", "romantic", "famrel", "freetime", "goout",
    "Dalc", "Walc", "health", "absences", "G1", "G2", "G3"
]


def python_value(value):
    """Convert pandas/numpy values into MySQL-compatible values."""
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH, sep=";")

    if list(df.columns) != ACADEMIC_COLUMNS:
        raise ValueError(
            "CSV columns differ from the expected original dataset.\n"
            f"Found: {list(df.columns)}"
        )

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # All database changes succeed together or are rolled back.
        connection.start_transaction()

        insert_student_sql = """
            INSERT INTO students (source_key)
            VALUES (%s)
            ON DUPLICATE KEY UPDATE
                student_id = LAST_INSERT_ID(student_id)
        """

        insert_record_sql = f"""
            INSERT INTO academic_records (
                student_id, {", ".join(f"`{c}`" for c in ACADEMIC_COLUMNS)}
            )
            VALUES ({", ".join(["%s"] * (len(ACADEMIC_COLUMNS) + 1))})
        """

        for row_number, (_, row) in enumerate(df.iterrows(), start=1):
            # Stable identifier tied to this row in this dataset.
            source_key = f"student-math-{row_number:03d}"

            cursor.execute(insert_student_sql, (source_key,))
            student_id = cursor.lastrowid

            # Make reruns replace this dataset row's academic record
            # instead of adding a duplicate.
            cursor.execute(
                "DELETE FROM academic_records WHERE student_id = %s",
                (student_id,)
            )

            values = [python_value(row[column]) for column in ACADEMIC_COLUMNS]

            cursor.execute(
                insert_record_sql,
                [student_id, *values]
            )

        connection.commit()

        cursor.execute("SELECT COUNT(*) FROM students")
        student_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM academic_records")
        record_count = cursor.fetchone()[0]

        print("Dataset import successful!")
        print("CSV rows:", len(df))
        print("Students in database:", student_count)
        print("Academic records in database:", record_count)
        print("Original columns per academic record:", len(ACADEMIC_COLUMNS))

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()


import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

# Locate the .env file in the GRADIFY project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.getenv("DB_NAME", "gradify_db"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


if __name__ == "__main__":
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES")

        print("MySQL connection successful!")
        print("Tables in gradify_db:")
        for (table_name,) in cursor.fetchall():
            print("-", table_name)

        cursor.close()
        connection.close()

    except mysql.connector.Error as error:
        print("MySQL connection failed.")
        print("Error:", error)

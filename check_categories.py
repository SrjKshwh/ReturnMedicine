import sqlite3
import os

def check_categories():
    # Check both database locations
    db_files = ['returns_mvp.db', 'instance/returns_mvp.db']

    for db_file in db_files:
        if os.path.exists(db_file):
            print(f"\nChecking {db_file}:")
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM return_categories")
            categories = cursor.fetchall()

            print("Current categories in database:")
            for cat in categories:
                print(f"  ID: {cat[0]}, Name: {cat[1]}")

            conn.close()
        else:
            print(f"Database file {db_file} not found")

if __name__ == "__main__":
    check_categories()
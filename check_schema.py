import sqlite3
import os

def check_schema():
    # Check the instance database
    db_path = 'instance/returns_mvp.db'

    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=== ReturnItem Table Schema ===")
    cursor.execute("PRAGMA table_info(return_items)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"  {col[1]} ({col[2]})")

    print("\n=== ReturnCategory Table Schema ===")
    cursor.execute("PRAGMA table_info(return_categories)")
    categories = cursor.fetchall()
    for cat in categories:
        print(f"  {cat[1]} ({cat[2]})")

    print("\n=== Foreign Keys ===")
    cursor.execute("PRAGMA foreign_key_list(return_items)")
    fks = cursor.fetchall()
    for fk in fks:
        print(f"  Column: {fk[3]}, References: {fk[2]}.{fk[4]}")

    conn.close()

if __name__ == "__main__":
    check_schema()
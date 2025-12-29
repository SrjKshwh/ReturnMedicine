import sqlite3
import os
from models import db, ReturnItem, Reason, ReturnCategory
from flask import Flask

def migrate_database():
    # Create app context
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/returns_mvp.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        # Check if migration is needed
        conn = sqlite3.connect('instance/returns_mvp.db')
        cursor = conn.cursor()

        # Check current schema
        cursor.execute("PRAGMA table_info(return_items)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]

        if 'reason' in column_names and 'reason_id' not in column_names:
            print("Migration needed: reason column exists but reason_id is missing")

            # Step 1: Add reason_id column
            cursor.execute("ALTER TABLE return_items ADD COLUMN reason_id INTEGER")

            # Step 2: Create temporary mapping of reason names to reason IDs
            reason_mapping = {}
            cursor.execute("SELECT id, name FROM reasons")
            reasons = cursor.fetchall()
            for reason_id, reason_name in reasons:
                reason_mapping[reason_name] = reason_id

            # Step 3: Update reason_id based on reason column
            cursor.execute("SELECT id, reason FROM return_items WHERE reason IS NOT NULL")
            items = cursor.fetchall()

            for item_id, reason_name in items:
                if reason_name in reason_mapping:
                    cursor.execute(
                        "UPDATE return_items SET reason_id = ? WHERE id = ?",
                        (reason_mapping[reason_name], item_id)
                    )

            # Step 4: Drop the old reason column
            # First, create a new table without the reason column
            cursor.execute("""
                CREATE TABLE return_items_new (
                    id INTEGER PRIMARY KEY,
                    return_report_id INTEGER NOT NULL,
                    ndc VARCHAR(11) NOT NULL,
                    description VARCHAR(255) NOT NULL,
                    lot_no VARCHAR(50) NOT NULL,
                    exp_date DATE NOT NULL,
                    pkg_size INTEGER NOT NULL,
                    full_qty INTEGER NOT NULL,
                    partial_qty INTEGER NOT NULL,
                    unit_price FLOAT NOT NULL,
                    extended_price FLOAT NOT NULL,
                    category_id INTEGER NOT NULL,
                    reason_id INTEGER NOT NULL,
                    manufacturer VARCHAR(120) NOT NULL,
                    FOREIGN KEY (return_report_id) REFERENCES return_reports(id),
                    FOREIGN KEY (category_id) REFERENCES return_categories(id),
                    FOREIGN KEY (reason_id) REFERENCES reasons(id)
                )
            """)

            # Copy data from old table to new table
            cursor.execute("""
                INSERT INTO return_items_new
                SELECT id, return_report_id, ndc, description, lot_no, exp_date,
                       pkg_size, full_qty, partial_qty, unit_price, extended_price,
                       category_id, reason_id, manufacturer
                FROM return_items
            """)

            # Drop old table and rename new table
            cursor.execute("DROP TABLE return_items")
            cursor.execute("ALTER TABLE return_items_new RENAME TO return_items")

            conn.commit()
            print("Migration completed successfully")

        else:
            print("No migration needed - schema is already correct")

        conn.close()

if __name__ == "__main__":
    migrate_database()
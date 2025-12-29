import sqlite3
import os

def test_database_schema():
    """Test that all required tables and columns exist"""
    # Check both possible database locations
    db_paths = ['instance/returns_mvp.db', 'returns_mvp.db']
    db_path = None

    for path in db_paths:
        if os.path.exists(path):
            db_path = path
            break

    if not db_path:
        print("[-] No database file found")
        return False

    if not os.path.exists(db_path):
        print("[-] Database file not found")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Test 1: Check ReturnItem table exists with all required columns
        cursor.execute("PRAGMA table_info(return_items)")
        columns = cursor.fetchall()
        required_columns = [
            'ndc', 'description', 'lot_no', 'exp_date', 'pkg_size',
            'full_qty', 'partial_qty', 'unit_price', 'extended_price',
            'category_id', 'reason_id', 'manufacturer', 'return_report_id'
        ]

        column_names = [col[1] for col in columns]
        missing_columns = [col for col in required_columns if col not in column_names]

        if missing_columns:
            print(f"[-] Missing columns in ReturnItem table: {missing_columns}")
            return False
        else:
            print("[+] ReturnItem table has all required columns")

        # Test 2: Check ReturnCategory table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='return_categories'")
        if cursor.fetchone():
            print("[+] ReturnCategory table exists")

            # Check if it has the required categories
            cursor.execute("SELECT COUNT(*) FROM return_categories WHERE name IN ('Short Dated', 'Outdated', 'Future Dated', 'Non-Returnable')")
            count = cursor.fetchone()[0]
            if count >= 4:
                print("[+] ReturnCategory table has required rule definitions")
            else:
                print(f"[-] ReturnCategory table missing some rule definitions (found {count})")
        else:
            print("[-] ReturnCategory table not found")
            return False

        # Test 3: Check foreign key relationships
        cursor.execute("PRAGMA foreign_key_list(return_items)")
        fk_info = cursor.fetchall()

        # Should have foreign keys to return_reports, return_categories, and reasons
        fk_tables = [fk[2] for fk in fk_info]  # table column
        required_fk_tables = ['return_reports', 'return_categories', 'reasons']

        missing_fks = [table for table in required_fk_tables if table not in fk_tables]
        if missing_fks:
            print(f"[-] Missing foreign key relationships: {missing_fks}")
        else:
            print("[+] All required foreign key relationships exist")

        # Test 4: Check if there are any return items in the database
        cursor.execute("SELECT COUNT(*) FROM return_items")
        item_count = cursor.fetchone()[0]
        print(f"[+] Found {item_count} return items in database")

        # Test 5: Check if there are return reports with items
        cursor.execute("SELECT COUNT(*) FROM return_reports WHERE id IN (SELECT DISTINCT return_report_id FROM return_items)")
        reports_with_items = cursor.fetchone()[0]
        print(f"[+] Found {reports_with_items} return reports with items")

        conn.close()
        return True

    except Exception as e:
        print(f"[-] Error testing database: {e}")
        return False

def test_forms_and_validation():
    """Test that forms and validation logic exist"""
    try:
        # Check if forms.py has ReturnItemForm
        with open('forms.py', 'r') as f:
            content = f.read()

        if 'class ReturnItemForm' in content:
            print("[+] ReturnItemForm exists in forms.py")

            # Check for required fields
            required_fields = ['manufacturer', 'ndc', 'exp_date', 'category']
            for field in required_fields:
                if field in content:
                    print(f"[+] {field} field found in ReturnItemForm")
                else:
                    print(f"[-] {field} field missing from ReturnItemForm")
        else:
            print("[-] ReturnItemForm not found in forms.py")
            return False

        # Check for expiration validation logic
        if 'validate_exp_date' in content and 'timedelta' in content:
            print("[+] Expiration validation logic found")
        else:
            print("[-] Expiration validation logic missing")

        return True

    except Exception as e:
        print(f"[-] Error testing forms: {e}")
        return False

def test_routes():
    """Test that required routes exist"""
    try:
        with open('app.py', 'r') as f:
            content = f.read()

        # Check for the new route
        if '/add_item/<int:return_id>' in content:
            print("[+] /add_item/<return_id> route found")
        else:
            print("[-] /add_item/<return_id> route not found")
            return False

        # Check for the existing route
        if '/add_item/<return_no>' in content:
            print("[+] /add_item/<return_no> route found")
        else:
            print("[-] /add_item/<return_no> route not found")
            return False

        return True

    except Exception as e:
        print(f"[-] Error testing routes: {e}")
        return False

def main():
    print("=== Day 15 & 16 Implementation Test ===\n")

    print("1. Testing Database Schema:")
    db_ok = test_database_schema()

    print("\n2. Testing Forms and Validation:")
    forms_ok = test_forms_and_validation()

    print("\n3. Testing Routes:")
    routes_ok = test_routes()

    print("\n=== Summary ===")
    if db_ok and forms_ok and routes_ok:
        print("[+] All Day 15 & 16 requirements are implemented!")
        return True
    else:
        print("[-] Some requirements are missing or incomplete")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
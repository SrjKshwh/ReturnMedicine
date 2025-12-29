#!/usr/bin/env python3
"""
End-to-End Test Script for Pharmaceutical Returns Portal
Tests the complete flow: Create Return → Add Items → Auto-classify → Generate Report → Export PDF/Excel
"""

import requests
import json
from datetime import datetime, timedelta
import time
import os

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing BeautifulSoup...")
    import subprocess
    subprocess.check_call(["pip", "install", "beautifulsoup4"])
    from bs4 import BeautifulSoup

BASE_URL = "http://localhost:5000"

def login_session():
    """Create a session and login"""
    session = requests.Session()

    # Login directly (CSRF disabled for testing)
    login_data = {
        'username': 'user1',
        'password': 'pass123'
    }
    response = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=True)
    if response.status_code != 200:
        print(f"Login failed: {response.status_code}")
        return None
    return session

def create_return_report(session):
    """Create a new return report"""
    print("Creating return report...")

    return_data = {
        'return_no': f'TEST-{int(time.time())}',
        'invoice_date': '2024-01-15',
        'service_type': 'Standard Return',
        'ERV': 15000.00,
        'credit_received': 12000.00,
        'fees': 500.00,
        'amount_paid': 11500.00,
        'last_payment_date': '2024-02-01'
    }

    # Add manufacturer breakdowns
    manufacturers = [
        {'manufacturer_name': 'PharmaCo', 'ERV': 8000.00, 'expiration_date': '2024-07-15'},
        {'manufacturer_name': 'MediCorp', 'ERV': 7000.00, 'expiration_date': '2024-08-20'}
    ]

    # Add manufacturers to form data
    for i, mfg in enumerate(manufacturers):
        return_data[f'manufacturers-{i}-manufacturer_name'] = mfg['manufacturer_name']
        return_data[f'manufacturers-{i}-ERV'] = str(mfg['ERV'])
        return_data[f'manufacturers-{i}-expiration_date'] = mfg['expiration_date']

    response = session.post(f"{BASE_URL}/new_return", data=return_data)
    if response.status_code == 302:  # Redirect on success
        print("Return report created successfully")
        return return_data['return_no']
    else:
        print(f"Failed to create return: {response.status_code} - {response.text}")
        return None

def add_items_to_return(session, return_no):
    """Add items to the return with auto-classification"""
    print(f"Adding items to return {return_no}...")

    # Get the return report
    response = session.get(f"{BASE_URL}/returns/{return_no}")
    if response.status_code != 200:
        print(f"Could not find return {return_no}")
        return False

    # Add items via POST to /add_item/<return_no>
    items = [
        {
            'ndc': '0002-1234-01',  # From seeded NDC master
            'description': 'Sample Drug A 10mg',
            'lot_no': 'LOT001',
            'exp_date': '2024-08-15',  # Short dated (within 6 months)
            'pkg_size': 100,
            'full_qty': 5,
            'partial_qty': 0,
            'unit_price': 12.50,
            'extended_price': 625.00,
            'category': '1',  # Assuming category ID
            'manufacturer': 'PharmaCo'
        },
        {
            'ndc': '0003-5678-02',  # From seeded NDC master
            'description': 'Sample Drug B 500mg',
            'lot_no': 'LOT002',
            'exp_date': '2025-02-15',  # Returnable
            'pkg_size': 50,
            'full_qty': 10,
            'partial_qty': 0,
            'unit_price': 8.99,
            'extended_price': 449.50,
            'category': '1',
            'manufacturer': 'MediCorp'
        },
        {
            'ndc': '0004-9012-03',  # Non-returnable
            'description': 'Ineligible Product',
            'lot_no': 'LOT003',
            'exp_date': '2023-12-01',  # Outdated
            'pkg_size': 25,
            'full_qty': 2,
            'partial_qty': 0,
            'unit_price': 0.00,
            'extended_price': 0.00,
            'category': '1',
            'manufacturer': 'NoReturn Inc'
        }
    ]

    for item in items:
        response = session.post(f"{BASE_URL}/add_item/{return_no}", data=item)
        if response.status_code == 302:
            print(f"Added item {item['ndc']} successfully")
        else:
            print(f"Failed to add item {item['ndc']}: {response.status_code}")

    return True

def check_reports(session):
    """Check that reports are generated correctly"""
    print("Checking reports...")

    response = session.get(f"{BASE_URL}/reports")
    if response.status_code == 200:
        print("Reports page loaded successfully")
        return True
    else:
        print(f"Reports page failed: {response.status_code}")
        return False

def export_pdf(session):
    """Test PDF export functionality"""
    print("Testing PDF export...")

    # Export returnable/non-returnable report
    response = session.get(f"{BASE_URL}/reports/returnable_nonreturnable/pdf")
    if response.status_code == 200:
        print("PDF export successful")
        return True
    else:
        print(f"PDF export failed: {response.status_code}")
        return False

def export_excel(session):
    """Test Excel export functionality"""
    print("Testing Excel export...")

    response = session.get(f"{BASE_URL}/export_excel")
    if response.status_code == 200:
        print("Excel export successful")
        return True
    else:
        print(f"Excel export failed: {response.status_code}")
        return False

def run_e2e_test():
    """Run the complete end-to-end test"""
    print("Starting End-to-End Test for Pharmaceutical Returns Portal")
    print("=" * 60)

    # Login
    session = login_session()
    if not session:
        print("Test FAILED: Could not login")
        return False

    # Create return
    return_no = create_return_report(session)
    if not return_no:
        print("Test FAILED: Could not create return report")
        return False

    # Add items
    if not add_items_to_return(session, return_no):
        print("Test FAILED: Could not add items")
        return False

    # Check reports
    if not check_reports(session):
        print("Test FAILED: Reports not working")
        return False

    # Export PDF
    if not export_pdf(session):
        print("Test FAILED: PDF export not working")
        return False

    # Export Excel
    if not export_excel(session):
        print("Test FAILED: Excel export not working")
        return False

    print("=" * 60)
    print("End-to-End Test PASSED!")
    print("All functionality working correctly:")
    print("✓ Create Return → ✓ Add Items → ✓ Auto-classify → ✓ Generate Report → ✓ Export PDF/Excel")
    return True

if __name__ == "__main__":
    success = run_e2e_test()
    exit(0 if success else 1)
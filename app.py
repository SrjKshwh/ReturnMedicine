import os
from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_wtf import FlaskForm
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import uuid # For generating Submission IDs
from functools import wraps
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from io import BytesIO
from models import db, User
from forms import RegistrationForm, LoginForm, ReturnForm, CheckForm, ReturnItemForm, BulkUploadForm, PDFUploadForm
from models import ReturnReport, CheckStatement, CheckDetail, ManufacturerBreakdown, ReturnCategory, ReturnItem, Reason
import os
from werkzeug.utils import secure_filename
import csv
import io
import pdfplumber
import pandas as pd
# from weasyprint import HTML, CSS
# from weasyprint.text.fonts import FontConfiguration

# --- CONFIGURATION ---
class Config:
    # Use a basic SQLite database for this MVP development phase
    # Replace this with a PostgreSQL connection string for production deployment (e.g., on Render)
    basedir = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
                              'sqlite:///' + os.path.join(basedir, 'returns_mvp.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a_very_secret_key_for_flask_session'
    WTF_CSRF_ENABLED = False  # Disable CSRF for testing
    
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login' # Define the view function for logging in
    login_manager.login_message_category = 'warning'

    return app

# Initialize Extensions (outside create_app for global use)
login_manager = LoginManager()

# --- DATABASE MODELS (Day 2) ---
# Models are now imported from models.py

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class Submission(db.Model):
    __tablename__ = 'submissions'
    id = db.Column(db.Integer, primary_key=True)
    # Submission ID used by the user (UUID for better uniqueness)
    submission_uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # Relationship to User (submitter)
    submitter = db.relationship('User', backref='submissions')
    submission_date = db.Column(db.Date, nullable=False, default=date.today)
    # Status: Draft, Submitted, Received, Credited
    status = db.Column(db.String(20), nullable=False, default='Draft')
    tracking_number = db.Column(db.String(100)) # Placeholder for tracking
    status_updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to Items
    items = db.relationship('SubmissionItem', backref='submission', lazy=True, cascade="all, delete-orphan")
    # Relationship to Status History
    status_history = db.relationship('StatusUpdate', backref='submission', lazy=True, cascade="all, delete-orphan")
    
class SubmissionItem(db.Model):
    __tablename__ = 'submission_items'
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id'), nullable=False)
    ndc = db.Column(db.String(11), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    expiration_date = db.Column(db.Date, nullable=False)
    estimated_credit = db.Column(db.Float, default=0.0)
    # returnable_status: Eligible, Ineligible (based on NDC lookup/expiration rules)
    returnable_status = db.Column(db.String(20), default='Unchecked')
    reason_id = db.Column(db.Integer, db.ForeignKey('reasons.id'))

    # Relationship to Reason
    reason = db.relationship('Reason', backref='submission_items')

class NDC_Master(db.Model):
    __tablename__ = 'ndc_master'
    ndc = db.Column(db.String(11), primary_key=True)
    drug_name = db.Column(db.String(255), nullable=False)
    manufacturer = db.Column(db.String(120), nullable=False)
    policy_code = db.Column(db.String(10))
    base_credit_value = db.Column(db.Float, default=1.00) # Base value per unit for calculation

class StatusUpdate(db.Model):
    __tablename__ = 'status_updates'
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id'), nullable=False)
    old_status = db.Column(db.String(20))
    new_status = db.Column(db.String(20), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_by = db.Column(db.String(100)) # Could be 'system' or admin username
    notes = db.Column(db.Text)

# --- DECORATORS ---

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Access denied. Admin only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def reviewer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['admin', 'reviewer']:
            flash('Access denied. Reviewer or Admin only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- UTILITIES ---

def classify_item(exp_date, ndc_record=None):
    """Classify an item based on expiration date and NDC rules."""
    today = date.today()

    # Calculate months until expiration
    months_until_expiry = (exp_date - today).days / 30

    if exp_date < today:
        return "Outdated"
    elif months_until_expiry <= 6:
        return "Short Dated"
    elif months_until_expiry > 12:
        return "Future Dated"
    else:
        # Check NDC policy if available
        if ndc_record and ndc_record.policy_code == 'X':
            return "Non-Returnable"
        return "Returnable"

def seed_ndc_master(app):
    """Seeds the NDC Master table with sample data."""
    with app.app_context():
        if NDC_Master.query.count() == 0:
            sample_ndcs = [
                {'ndc': '0002-1234-01', 'drug_name': 'Sample Drug A 10mg', 'manufacturer': 'PharmaCo', 'base_credit_value': 12.50},
                {'ndc': '0003-5678-02', 'drug_name': 'Sample Drug B 500mg', 'manufacturer': 'MediCorp', 'base_credit_value': 8.99},
                {'ndc': '0004-9012-03', 'drug_name': 'Ineligible Product', 'manufacturer': 'NoReturn Inc', 'policy_code': 'X', 'base_credit_value': 0.00},
            ]
            for data in sample_ndcs:
                ndc_record = NDC_Master(**data)
                db.session.add(ndc_record)
            db.session.commit()
            print("NDC Master seeded with sample data.")

def seed_sample_users(app):
    """Seeds sample users with different roles for testing."""
    with app.app_context():
        if User.query.count() == 0:
            sample_users = [
                {'username': 'user1', 'email': 'user1@example.com', 'company_name': 'MediPharm Pharmacy', 'role': 'user'},
                {'username': 'user2', 'email': 'user2@example.com', 'company_name': 'HealthCare Solutions', 'role': 'user'},
                {'username': 'reviewer1', 'email': 'reviewer1@example.com', 'company_name': 'PharmaReturns Processing', 'role': 'reviewer'},
                {'username': 'admin', 'email': 'admin@example.com', 'company_name': 'Admin', 'role': 'admin'},
            ]
            passwords = ['pass123', 'pass123', 'review123', 'admin123']
            for data, password in zip(sample_users, passwords):
                user = User(**data)
                user.set_password(password)
                db.session.add(user)
            db.session.commit()
            print("Sample users seeded with different roles.")

def seed_reasons():
    """Seeds default reasons for classification."""
    with app.app_context():
        if Reason.query.count() == 0:
            reasons = [
                {"name": "Short Dated", "description": "Expires within 6 months"},
                {"name": "Outdated", "description": "Expired before today"},
                {"name": "Future Dated", "description": "Expires > 12 months"},
                {"name": "Returnable", "description": "Eligible for return"},
                {"name": "Non-Returnable", "description": "Vendor policy or label issue"}
            ]
            for reason_data in reasons:
                reason = Reason(**reason_data)
                db.session.add(reason)
            db.session.commit()
            print("Default reasons seeded.")

def seed_return_reports():
    """Seeds sample return reports with manufacturer breakdowns."""
    with app.app_context():
        if ReturnReport.query.count() == 0:
            from datetime import datetime, date
            sample_reports = [
                {
                    'return_no': 'RTN-241231-1200',
                    'invoice_date': date(2024, 12, 15),
                    'service_type': 'Standard Return',
                    'ERV': 25000.00,
                    'credit_received': 22500.00,
                    'fees': 2500.00,
                    'amount_paid': 20000.00,
                    'last_payment_date': date(2024, 12, 20),
                    'manufacturers': [
                        {'manufacturer_name': 'Pfizer Inc.', 'ERV': 12000.00, 'expiration_date': date(2026, 6, 15)},
                        {'manufacturer_name': 'Johnson & Johnson', 'ERV': 8000.00, 'expiration_date': date(2026, 8, 20)},
                        {'manufacturer_name': 'Merck & Co.', 'ERV': 5000.00, 'expiration_date': date(2026, 4, 10)}
                    ]
                },
                {
                    'return_no': 'RTN-241231-1300',
                    'invoice_date': date(2024, 12, 16),
                    'service_type': 'Express Return',
                    'ERV': 18500.00,
                    'credit_received': 17000.00,
                    'fees': 1500.00,
                    'amount_paid': 15500.00,
                    'last_payment_date': date(2024, 12, 22),
                    'manufacturers': [
                        {'manufacturer_name': 'AstraZeneca', 'ERV': 9500.00, 'expiration_date': date(2026, 9, 5)},
                        {'manufacturer_name': 'Novartis AG', 'ERV': 6000.00, 'expiration_date': date(2026, 7, 18)},
                        {'manufacturer_name': 'GlaxoSmithKline', 'ERV': 3000.00, 'expiration_date': date(2026, 5, 12)}
                    ]
                },
                {
                    'return_no': 'RTN-241231-1400',
                    'invoice_date': date(2024, 12, 17),
                    'service_type': 'Standard Return',
                    'ERV': 32000.00,
                    'credit_received': 29000.00,
                    'fees': 3000.00,
                    'amount_paid': 26000.00,
                    'last_payment_date': date(2024, 12, 25),
                    'manufacturers': [
                        {'manufacturer_name': 'Bristol Myers Squibb', 'ERV': 15000.00, 'expiration_date': date(2026, 10, 8)},
                        {'manufacturer_name': 'Eli Lilly and Company', 'ERV': 12000.00, 'expiration_date': date(2026, 11, 14)},
                        {'manufacturer_name': 'AbbVie Inc.', 'ERV': 5000.00, 'expiration_date': date(2026, 3, 22)}
                    ]
                },
                {
                    'return_no': 'RTN-241231-1500',
                    'invoice_date': date(2024, 12, 18),
                    'service_type': 'Priority Return',
                    'ERV': 27500.00,
                    'credit_received': 25000.00,
                    'fees': 2500.00,
                    'amount_paid': 22500.00,
                    'last_payment_date': date(2024, 12, 28),
                    'manufacturers': [
                        {'manufacturer_name': 'Sanofi S.A.', 'ERV': 14000.00, 'expiration_date': date(2026, 12, 1)},
                        {'manufacturer_name': 'Roche Holding AG', 'ERV': 9500.00, 'expiration_date': date(2026, 8, 30)},
                        {'manufacturer_name': 'Bayer AG', 'ERV': 4000.00, 'expiration_date': date(2026, 6, 25)}
                    ]
                },
                {
                    'return_no': 'RTN-241231-1600',
                    'invoice_date': date(2024, 12, 19),
                    'service_type': 'Standard Return',
                    'ERV': 21000.00,
                    'credit_received': 19500.00,
                    'fees': 1500.00,
                    'amount_paid': 18000.00,
                    'last_payment_date': date(2024, 12, 30),
                    'manufacturers': [
                        {'manufacturer_name': 'Amgen Inc.', 'ERV': 11000.00, 'expiration_date': date(2026, 7, 7)},
                        {'manufacturer_name': 'Gilead Sciences', 'ERV': 7000.00, 'expiration_date': date(2026, 9, 15)},
                        {'manufacturer_name': 'Regeneron Pharmaceuticals', 'ERV': 3000.00, 'expiration_date': date(2026, 4, 28)}
                    ]
                }
            ]

            for report_data in sample_reports:
                manufacturers = report_data.pop('manufacturers')
                return_report = ReturnReport(**report_data)
                db.session.add(return_report)
                db.session.flush()  # Get the ID

                for manufacturer_data in manufacturers:
                    breakdown = ManufacturerBreakdown(
                        return_report_id=return_report.id,
                        **manufacturer_data
                    )
                    db.session.add(breakdown)

            db.session.commit()
            print("Sample return reports with manufacturer breakdowns seeded.")

# --- APPLICATION FACTORY SETUP ---
app = create_app()

with app.app_context():
    db.create_all() # Create tables if they don't exist (Day 2)
    seed_ndc_master(app) # Seed sample data
    seed_reasons() # Seed default reasons
    seed_return_reports() # Seed sample return reports
    seed_sample_users(app) # Seed sample users
    print("Seeding users...")

# --- ROUTES (Day 3, 5, 8, 11) ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html', title='Welcome')

# --- AUTH ROUTES (Day 3) ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html', title='Login', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = RegistrationForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('register'))

        new_user = User(username=form.username.data, email=form.email.data)
        new_user.set_password(form.password.data)

        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', title='Register', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# --- DASHBOARD & SUBMISSION ROUTES (Day 5, 7, 8, 11) ---

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'reviewer':
        # Reviewers see all submissions
        submissions = Submission.query.order_by(Submission.submission_date.desc()).all()
        return render_template('dashboard.html', title='Reviewer Dashboard', submissions=submissions, is_reviewer=True)
    else:
        # Regular users see only their own submissions
        submissions = Submission.query.filter_by(user_id=current_user.id).order_by(Submission.submission_date.desc()).all()

        # Calculate dashboard metrics
        total_erv = db.session.query(db.func.sum(ReturnReport.ERV)).scalar() or 0
        total_short_dated = db.session.query(db.func.sum(ReturnItem.extended_price)).join(Reason).filter(Reason.name == 'Short Dated').scalar() or 0

        # Top 5 manufacturers by ERV
        top_manufacturers = db.session.query(
            ManufacturerBreakdown.manufacturer_name,
            db.func.sum(ManufacturerBreakdown.ERV).label('total_erv')
        ).group_by(ManufacturerBreakdown.manufacturer_name).order_by(db.desc('total_erv')).limit(5).all()

        # ERV trend data (by month)
        erv_trend_raw = db.session.query(
            db.func.strftime('%Y-%m', ReturnReport.invoice_date).label('month'),
            db.func.sum(ReturnReport.ERV).label('total_erv')
        ).filter(ReturnReport.invoice_date.isnot(None)).group_by('month').order_by('month').all()

        # Convert Row objects to dictionaries for JSON serialization
        erv_trend = [{'month': row.month, 'total_erv': float(row.total_erv) if row.total_erv else 0} for row in erv_trend_raw]

        return render_template('dashboard.html',
                             title='Dashboard',
                             submissions=submissions,
                             is_reviewer=False,
                             total_erv=total_erv,
                             total_short_dated=total_short_dated,
                             top_manufacturers=top_manufacturers,
                             erv_trend=erv_trend)

@app.route('/new_return', methods=['GET', 'POST'])
@login_required
def new_return():
    form = ReturnForm()
    if request.method == 'POST':
        # Handle dynamic manufacturer data from JavaScript
        manufacturer_names = request.form.getlist('manufacturers-*-manufacturer_name')
        manufacturer_ervs = request.form.getlist('manufacturers-*-ERV')
        manufacturer_exps = request.form.getlist('manufacturers-*-expiration_date')

        # Validate basic form data
        if not form.invoice_date.data:
            flash('Please fill in all required fields.', 'danger')
            return render_template('new_return.html', title='New Return', form=form)

        # Auto-generate return_no in format RTN-yymmdd-hhmm
        from datetime import datetime
        now = datetime.now()
        yy = now.strftime('%y')
        mm = now.strftime('%m')
        dd = now.strftime('%d')
        hh = now.strftime('%H')
        mi = now.strftime('%M')
        return_no = f"RTN-{yy}{mm}{dd}-{hh}{mi}"

        new_return_report = ReturnReport(
            return_no=return_no,
            invoice_date=form.invoice_date.data,
            service_type=form.service_type.data,
            ERV=form.ERV.data,
            credit_received=form.credit_received.data,
            fees=form.fees.data,
            amount_paid=form.amount_paid.data,
            last_payment_date=form.last_payment_date.data
        )
        db.session.add(new_return_report)
        db.session.flush()  # Get the ID without committing

        # Process manufacturer breakdowns
        for name, erv, exp in zip(manufacturer_names, manufacturer_ervs, manufacturer_exps):
            if name.strip() and erv and exp:  # Only add if all fields are filled
                try:
                    from datetime import datetime
                    exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
                    breakdown = ManufacturerBreakdown(
                        return_report_id=new_return_report.id,
                        manufacturer_name=name,
                        ERV=float(erv),
                        expiration_date=exp_date
                    )
                    db.session.add(breakdown)
                except ValueError:
                    flash(f'Invalid data for manufacturer {name}', 'warning')
                    continue

        db.session.commit()
        flash('Return report with manufacturer breakdown submitted successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('new_return.html', title='New Return', form=form)

@app.route('/new_check', methods=['GET', 'POST'])
@login_required
def new_check():
    form = CheckForm()
    if request.method == 'POST':
        # Handle dynamic check detail data from JavaScript
        return_nos = request.form.getlist('details-*-return_no')
        amounts = request.form.getlist('details-*-amount')
        pdf_files = request.files.getlist('details-*-pdf_file')

        # Validate basic form data
        if not form.statement_no.data or not form.payment_date.data:
            flash('Please fill in all required fields.', 'danger')
            return render_template('new_check.html', title='New Check', form=form)

        new_check_statement = CheckStatement(
            statement_no=form.statement_no.data,
            payment_date=form.payment_date.data,
            check_amount=form.amount.data,
            check_no=form.check_no.data,
            status=form.status.data or 'Pending'
        )
        db.session.add(new_check_statement)
        db.session.flush()  # Get the ID without committing

        # Ensure uploads directory exists
        uploads_dir = os.path.join(app.root_path, 'static', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)

        # Process check details
        for i, (return_no, amount) in enumerate(zip(return_nos, amounts)):
            if return_no.strip() and amount:
                pdf_path = None
                # Handle PDF upload for this detail
                pdf_key = f'details-{i}-pdf_file'
                if pdf_key in request.files:
                    pdf_file = request.files[pdf_key]
                    if pdf_file and pdf_file.filename:
                        filename = secure_filename(pdf_file.filename)
                        pdf_path = os.path.join('uploads', filename)
                        pdf_file.save(os.path.join(uploads_dir, filename))

                try:
                    detail = CheckDetail(
                        check_statement_id=new_check_statement.id,
                        return_no=return_no,
                        amount=float(amount),
                        pdf_file=pdf_path
                    )
                    db.session.add(detail)
                except ValueError:
                    flash(f'Invalid data for return {return_no}', 'warning')
                    continue

        db.session.commit()
        flash('Check statement with details submitted successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('new_check.html', title='New Check', form=form)

@app.route('/submission/new', methods=['GET', 'POST'])
@login_required
def new_submission():
    if request.method == 'POST':
        # --- Day 7: Handle Item Persistence ---

        ndc_list = request.form.getlist('ndc[]')
        qty_list = request.form.getlist('qty[]')
        exp_list = request.form.getlist('exp[]')

        if not ndc_list or not any(ndc.strip() for ndc in ndc_list):
            flash('Please add at least one item to the submission.', 'danger')
            return redirect(url_for('new_submission'))

        # Validate that all lists have the same length
        if not (len(ndc_list) == len(qty_list) == len(exp_list)):
            flash('Form data is incomplete. Please try again.', 'danger')
            return redirect(url_for('new_submission'))
        
        new_submission_obj = Submission(user_id=current_user.id, status='Draft')
        db.session.add(new_submission_obj)
        db.session.flush() # Flushes the new object to get its ID without committing

        # Process Items (Day 7/9 Logic)
        for ndc, qty_str, exp_str in zip(ndc_list, qty_list, exp_list):
            try:
                # Data cleaning and type conversion
                qty = int(qty_str)
                exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()

                # Basic validation
                if qty <= 0:
                    flash(f'Quantity must be positive for NDC {ndc}', 'warning')
                    continue
                
                # Day 9: NDC Validation and Credit Logic with enhanced business rules
                ndc_record = NDC_Master.query.get(ndc)

                credit = 0.0
                status = 'Ineligible'

                # Auto-classify the item using the classification logic
                classification = classify_item(exp_date, ndc_record)
                reason = Reason.query.filter_by(name=classification).first()
                if not reason:
                    flash(f'Classification reason not found for {classification}. Please contact admin.', 'danger')
                    continue

                if ndc_record:
                    # Check expiration date - must be at least 6 months from now to be returnable
                    today = date.today()
                    min_return_date = today + timedelta(days=180)  # 6 months

                    if exp_date <= min_return_date:
                        status = 'Ineligible (Expiration Too Soon)'
                    elif exp_date > today + timedelta(days=365*3):  # More than 3 years from now
                        status = 'Ineligible (Expiration Too Far)'
                    else:
                        # Check policy code
                        if ndc_record.policy_code == 'X':
                            status = 'Ineligible (Policy Restricted)'
                        else:
                            # Calculate credit with enhanced logic
                            base_credit = ndc_record.base_credit_value
                            if base_credit > 0:
                                # Apply quantity discount for bulk returns
                                if qty >= 100:
                                    discount_factor = 0.95  # 5% discount
                                elif qty >= 50:
                                    discount_factor = 0.97  # 3% discount
                                else:
                                    discount_factor = 1.0

                                # Apply expiration-based adjustment
                                months_until_expiry = (exp_date - today).days / 30
                                if months_until_expiry > 24:  # More than 2 years
                                    expiry_factor = 0.9  # 10% reduction for long expiry
                                elif months_until_expiry < 12:  # Less than 1 year
                                    expiry_factor = 0.95  # 5% reduction for short expiry
                                else:
                                    expiry_factor = 1.0

                                credit = round(base_credit * qty * discount_factor * expiry_factor, 2)
                                status = 'Eligible'
                            else:
                                status = 'Ineligible (No Credit Value)'
                else:
                    status = 'NDC Not Found'

                item = SubmissionItem(
                    submission_id=new_submission_obj.id,
                    ndc=ndc,
                    quantity=qty,
                    expiration_date=exp_date,
                    estimated_credit=credit,
                    returnable_status=status,
                    reason_id=reason.id
                )
                db.session.add(item)
            except ValueError:
                # Handle corrupted data row
                flash(f'Skipped invalid item row: NDC {ndc}', 'warning')
                continue

        db.session.commit()

        # Create initial status update record
        update_submission_status(new_submission_obj, 'Draft', 'user', 'Submission created')

        flash(f'New submission {new_submission_obj.submission_uuid} created successfully! Please review the manifest.', 'success')
        return redirect(url_for('view_submission', submission_uuid=new_submission_obj.submission_uuid))

    # --- Day 5: GET Request ---
    return render_template('new_submission.html', title='New Return Submission')

@app.route('/submission/<submission_uuid>')
@login_required
def view_submission(submission_uuid):
    # Ensure the user owns the submission (security check)
    submission = Submission.query.filter_by(submission_uuid=submission_uuid, user_id=current_user.id).first_or_404()
    
    total_credit = sum(item.estimated_credit for item in submission.items)
    
    return render_template('view_submission.html', 
                           title=f'Submission {submission_uuid}', 
                           submission=submission,
                           total_credit=total_credit)

def update_submission_status(submission, new_status, updated_by='system', notes=None):
    """Update submission status and create history record."""
    old_status = submission.status
    submission.status = new_status
    submission.status_updated_at = datetime.utcnow()

    # Create status update record
    status_update = StatusUpdate(
        submission_id=submission.id,
        old_status=old_status,
        new_status=new_status,
        updated_by=updated_by,
        notes=notes
    )
    db.session.add(status_update)
    db.session.commit()

@app.route('/submission/<submission_uuid>/finalize', methods=['POST'])
@login_required
def finalize_submission(submission_uuid):
    # Day 11: Finalize submission
    submission = Submission.query.filter_by(submission_uuid=submission_uuid, user_id=current_user.id).first_or_404()

    if submission.status == 'Draft':
        update_submission_status(submission, 'Submitted', 'user', 'User finalized submission for shipment')
        # In a real app, this would trigger an external tracking number request
        submission.tracking_number = f"TRACK-{submission_uuid[:8].upper()}"
        db.session.commit()
        flash(f'Submission {submission_uuid} is finalized and ready for shipment. Tracking: {submission.tracking_number}', 'success')
    else:
        flash(f'Submission {submission_uuid} is already {submission.status}.', 'info')

    return redirect(url_for('view_submission', submission_uuid=submission_uuid))

@app.route('/submission/<submission_uuid>/review', methods=['GET', 'POST'])
@login_required
@reviewer_required
def review_submission(submission_uuid):

    submission = Submission.query.filter_by(submission_uuid=submission_uuid).first_or_404()
    total_credit = sum(item.estimated_credit for item in submission.items)

    if request.method == 'POST':
        new_status = request.form.get('status')
        notes = request.form.get('notes', '')

        valid_statuses = ['Received', 'Credited']
        if new_status not in valid_statuses:
            flash('Invalid status.', 'danger')
            return redirect(url_for('review_submission', submission_uuid=submission_uuid))

        update_submission_status(submission, new_status, f'reviewer:{current_user.username}', notes)
        flash(f'Submission {submission_uuid} status updated to {new_status}.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('review_submission.html',
                          title=f'Review Submission {submission_uuid}',
                          submission=submission,
                          total_credit=total_credit)


def generate_manifest_pdf(submission):
    """Generate a PDF manifest for the submission."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
    )
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=20,
    )

    story = []

    # Title
    story.append(Paragraph("Pharmaceutical Return Manifest", title_style))
    story.append(Spacer(1, 12))

    # Submission details
    story.append(Paragraph(f"Submission ID: {submission.submission_uuid}", styles['Normal']))
    story.append(Paragraph(f"Date: {submission.submission_date.strftime('%Y-%m-%d')}", styles['Normal']))
    story.append(Paragraph(f"Company: {submission.submitter.company_name}", styles['Normal']))
    story.append(Paragraph(f"Status: {submission.status}", styles['Normal']))
    if submission.tracking_number:
        story.append(Paragraph(f"Tracking Number: {submission.tracking_number}", styles['Normal']))
    story.append(Spacer(1, 20))

    # Items table
    story.append(Paragraph("Return Items:", subtitle_style))

    data = [['NDC', 'Quantity', 'Expiration Date', 'Status', 'Estimated Credit']]
    total_credit = 0
    for item in submission.items:
        data.append([
            item.ndc,
            str(item.quantity),
            item.expiration_date.strftime('%Y-%m-%d'),
            item.returnable_status,
            f"${item.estimated_credit:.2f}"
        ])
        total_credit += item.estimated_credit

    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    story.append(table)
    story.append(Spacer(1, 20))
    story.append(Paragraph(f"Total Estimated Credit: ${total_credit:.2f}", styles['Normal']))

    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_shipping_label_pdf(submission):
    """Generate a PDF shipping label for the submission."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    story = []

    # Shipping label content
    story.append(Paragraph("PHARMACEUTICAL RETURNS - PREPAID SHIPPING LABEL", styles['Heading1']))
    story.append(Spacer(1, 20))

    story.append(Paragraph("FROM:", styles['Heading2']))
    story.append(Paragraph(f"{submission.submitter.company_name}", styles['Normal']))
    story.append(Paragraph(f"User: {submission.submitter.username}", styles['Normal']))
    story.append(Spacer(1, 20))

    story.append(Paragraph("TO:", styles['Heading2']))
    story.append(Paragraph("PharmaReturns Processing Center", styles['Normal']))
    story.append(Paragraph("123 Return Lane", styles['Normal']))
    story.append(Paragraph("Processing City, PC 12345", styles['Normal']))
    story.append(Spacer(1, 20))

    story.append(Paragraph("SUBMISSION DETAILS:", styles['Heading2']))
    story.append(Paragraph(f"Submission ID: {submission.submission_uuid}", styles['Normal']))
    if submission.tracking_number:
        story.append(Paragraph(f"Tracking Number: {submission.tracking_number}", styles['Normal']))
    story.append(Paragraph(f"Items: {len(submission.items)}", styles['Normal']))
    story.append(Spacer(1, 20))

    story.append(Paragraph("IMPORTANT: This shipment contains pharmaceutical products. Handle with care.", styles['Normal']))

    doc.build(story)
    buffer.seek(0)
    return buffer

@app.route('/submission/<submission_uuid>/manifest/pdf')
@login_required
def download_manifest(submission_uuid):
    submission = Submission.query.filter_by(submission_uuid=submission_uuid, user_id=current_user.id).first_or_404()
    pdf_buffer = generate_manifest_pdf(submission)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f'manifest_{submission_uuid}.pdf',
        mimetype='application/pdf'
    )

@app.route('/submission/<submission_uuid>/label/pdf')
@login_required
def download_label(submission_uuid):
    submission = Submission.query.filter_by(submission_uuid=submission_uuid, user_id=current_user.id).first_or_404()
    pdf_buffer = generate_shipping_label_pdf(submission)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f'shipping_label_{submission_uuid}.pdf',
        mimetype='application/pdf'
    )

# --- Day 8: View Returns ---

@app.route('/returns')
@login_required
def returns():
    # Get filters from request args
    return_no = request.args.get('return_no', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    service_type = request.args.get('service_type', '')

    query = ReturnReport.query

    if return_no:
        query = query.filter(ReturnReport.return_no.ilike(f'%{return_no}%'))
    if start_date:
        query = query.filter(ReturnReport.invoice_date >= start_date)
    if end_date:
        query = query.filter(ReturnReport.invoice_date <= end_date)
    if service_type:
        query = query.filter(ReturnReport.service_type.ilike(f'%{service_type}%'))

    returns_list = query.all()

    return render_template('returns.html', returns=returns_list, return_no=return_no, start_date=start_date, end_date=end_date, service_type=service_type)

@app.route('/returns/<return_no>')
@login_required
def return_details(return_no):
    return_report = ReturnReport.query.filter_by(return_no=return_no).first_or_404()
    manufacturers = return_report.breakdowns
    items = return_report.items  # Assuming items relationship is added
    return render_template('return_details.html', return_report=return_report, manufacturers=manufacturers, items=items)

@app.route('/add_item/<return_no>', methods=['GET', 'POST'])
@login_required
def add_item(return_no):
    return_report = ReturnReport.query.filter_by(return_no=return_no).first_or_404()

    form = ReturnItemForm()
    bulk_form = BulkUploadForm()
    pdf_form = PDFUploadForm()

    # Populate manufacturer choices from NDC_Master
    manufacturers = db.session.query(NDC_Master.manufacturer).distinct().all()
    form.manufacturer.choices = [(m.manufacturer, m.manufacturer) for m in manufacturers]

    # Populate category choices
    categories = ReturnCategory.query.all()
    form.category.choices = [(str(c.id), c.name) for c in categories]

    if form.validate_on_submit():
        # Auto-classify the item
        ndc_record = NDC_Master.query.get(form.ndc.data)
        classification = classify_item(form.exp_date.data, ndc_record)

        # Get the reason object
        reason = Reason.query.filter_by(name=classification).first()
        if not reason:
            flash('Classification reason not found. Please contact admin.', 'danger')
            return redirect(url_for('add_item', return_no=return_no))

        # Create new ReturnItem
        new_item = ReturnItem(
            return_report_id=return_report.id,
            ndc=form.ndc.data,
            description=form.description.data,
            lot_no=form.lot_no.data,
            exp_date=form.exp_date.data,
            pkg_size=form.pkg_size.data,
            full_qty=form.full_qty.data,
            partial_qty=form.partial_qty.data,
            unit_price=form.unit_price.data,
            extended_price=form.extended_price.data,
            category_id=int(form.category.data),
            reason_id=reason.id,
            manufacturer=form.manufacturer.data
        )
        db.session.add(new_item)
        db.session.commit()
        flash(f'Item added successfully! Classified as: {classification}', 'success')
        return redirect(url_for('return_details', return_no=return_no))

    return render_template('add_item.html', form=form, bulk_form=bulk_form, pdf_form=pdf_form, return_report=return_report)

@app.route('/add_item/<int:return_id>', methods=['GET', 'POST'])
@login_required
def add_item_by_id(return_id):
    return_report = ReturnReport.query.get_or_404(return_id)
    return redirect(url_for('add_item', return_no=return_report.return_no))

@app.route('/bulk_upload/<return_no>', methods=['POST'])
@login_required
def bulk_upload(return_no):
    return_report = ReturnReport.query.filter_by(return_no=return_no).first_or_404()
    form = BulkUploadForm()

    if form.validate_on_submit():
        csv_file = form.csv_file.data
        if csv_file and csv_file.filename.endswith('.csv'):
            # Read CSV content
            stream = io.StringIO(csv_file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.DictReader(stream)

            # Expected columns: ndc, description, lot_no, exp_date, pkg_size, full_qty, partial_qty, unit_price, extended_price, category, reason, manufacturer
            required_fields = ['ndc', 'description', 'lot_no', 'exp_date', 'pkg_size', 'full_qty', 'partial_qty', 'unit_price', 'extended_price', 'category', 'reason', 'manufacturer']

            items_added = 0
            errors = []
            ndc_seen = set()

            for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 because row 1 is header
                # Check for empty fields
                empty_fields = [field for field in required_fields if not row.get(field, '').strip()]
                if empty_fields:
                    errors.append(f"Row {row_num}: Empty fields: {', '.join(empty_fields)}")
                    continue

                ndc = row['ndc'].strip()
                # Check for duplicate NDCs in the file
                if ndc in ndc_seen:
                    errors.append(f"Row {row_num}: Duplicate NDC in file: {ndc}")
                    continue
                ndc_seen.add(ndc)

                # Check for duplicate NDCs in database for this return
                existing_item = ReturnItem.query.filter_by(return_report_id=return_report.id, ndc=ndc).first()
                if existing_item:
                    errors.append(f"Row {row_num}: NDC already exists in this return: {ndc}")
                    continue

                try:
                    # Validate and convert data
                    exp_date = datetime.strptime(row['exp_date'].strip(), '%Y-%m-%d').date()
                    pkg_size = int(row['pkg_size'].strip())
                    full_qty = int(row['full_qty'].strip())
                    partial_qty = int(row['partial_qty'].strip())
                    unit_price = float(row['unit_price'].strip())
                    extended_price = float(row['extended_price'].strip())

                    # Get category ID by name
                    category = ReturnCategory.query.filter_by(name=row['category'].strip()).first()
                    if not category:
                        errors.append(f"Row {row_num}: Invalid category: {row['category']}")
                        continue

                    # Auto-classify the item
                    ndc_record = NDC_Master.query.get(ndc)
                    classification = classify_item(exp_date, ndc_record)
                    reason = Reason.query.filter_by(name=classification).first()
                    if not reason:
                        errors.append(f"Row {row_num}: Classification reason not found for {classification}")
                        continue

                    # Create ReturnItem
                    new_item = ReturnItem(
                        return_report_id=return_report.id,
                        ndc=ndc,
                        description=row['description'].strip(),
                        lot_no=row['lot_no'].strip(),
                        exp_date=exp_date,
                        pkg_size=pkg_size,
                        full_qty=full_qty,
                        partial_qty=partial_qty,
                        unit_price=unit_price,
                        extended_price=extended_price,
                        category_id=category.id,
                        reason_id=reason.id,
                        manufacturer=row['manufacturer'].strip()
                    )
                    db.session.add(new_item)
                    items_added += 1

                except ValueError as e:
                    errors.append(f"Row {row_num}: Invalid data format - {str(e)}")
                except Exception as e:
                    errors.append(f"Row {row_num}: Error processing row - {str(e)}")

            db.session.commit()

            if items_added > 0:
                flash(f'Successfully added {items_added} items from CSV!', 'success')
            if errors:
                flash(f'Errors encountered: {"; ".join(errors)}', 'warning')

            return redirect(url_for('return_details', return_no=return_no))
        else:
            flash('Please upload a valid CSV file.', 'danger')

    return redirect(url_for('add_item', return_no=return_no))

# --- Day 9: View Checks ---

@app.route('/checks')
@login_required
def checks():
    # Get filters from request args
    statement_no = request.args.get('statement_no', '')
    check_no = request.args.get('check_no', '')

    query = CheckStatement.query

    if statement_no:
        query = query.filter(CheckStatement.statement_no.ilike(f'%{statement_no}%'))
    if check_no:
        query = query.filter(CheckStatement.check_no.ilike(f'%{check_no}%'))

    checks_list = query.all()

    return render_template('checks.html', checks=checks_list, statement_no=statement_no, check_no=check_no)

@app.route('/checks/<int:id>')
@login_required
def check_details(id):
    check_statement = CheckStatement.query.get_or_404(id)
    details = check_statement.details
    return render_template('check_details.html', check_statement=check_statement, details=details)

# --- Day 11: Reports Route ---

@app.route('/reports')
@login_required
def reports():
    # Aggregate totals
    total_erv = db.session.query(db.func.sum(ReturnReport.ERV)).scalar() or 0
    total_credits = db.session.query(db.func.sum(ReturnReport.credit_received)).scalar() or 0
    total_fees = db.session.query(db.func.sum(ReturnReport.fees)).scalar() or 0

    # Compute classification-based values
    short_dated_value = db.session.query(db.func.sum(ReturnItem.extended_price)).join(Reason).filter(Reason.name == 'Short Dated').scalar() or 0
    outdated_value = db.session.query(db.func.sum(ReturnItem.extended_price)).join(Reason).filter(Reason.name == 'Outdated').scalar() or 0
    non_returnable_value = db.session.query(db.func.sum(ReturnItem.extended_price)).join(Reason).filter(Reason.name == 'Non-Returnable').scalar() or 0

    # Aggregated manufacturer data
    manufacturer_data = db.session.query(
        ManufacturerBreakdown.manufacturer_name,
        db.func.sum(ManufacturerBreakdown.ERV).label('total_erv'),
        db.func.count(ManufacturerBreakdown.id).label('return_count')
    ).group_by(ManufacturerBreakdown.manufacturer_name).all()

    # Add percentages to manufacturer data
    for m in manufacturer_data:
        m.percentage = (m.total_erv / total_erv * 100) if total_erv > 0 else 0

    # Aggregated category data
    category_data = db.session.query(
        ReturnCategory.name,
        db.func.sum(ReturnItem.extended_price).label('total_value'),
        db.func.count(ReturnItem.id).label('item_count')
    ).join(ReturnItem).group_by(ReturnCategory.name).all()

    # Data for charts
    manufacturer_labels = [m.manufacturer_name for m in manufacturer_data]
    manufacturer_percentages = [m.percentage for m in manufacturer_data]
    manufacturer_colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', '#FF6384', '#C9CBCF']

    # Returnable vs Non-Returnable counts
    returnable_count = db.session.query(db.func.count(ReturnItem.id)).join(Reason).filter(Reason.name == 'Returnable').scalar() or 0
    non_returnable_count = db.session.query(db.func.count(ReturnItem.id)).join(Reason).filter(Reason.name.in_(['Non-Returnable', 'Outdated', 'Short Dated'])).scalar() or 0

    return render_template('reports.html',
                          total_erv=total_erv,
                          total_credits=total_credits,
                          total_fees=total_fees,
                          short_dated_value=short_dated_value,
                          outdated_value=outdated_value,
                          non_returnable_value=non_returnable_value,
                          manufacturer_data=manufacturer_data,
                          category_data=category_data,
                          manufacturer_labels=manufacturer_labels,
                          manufacturer_percentages=manufacturer_percentages,
                          manufacturer_colors=manufacturer_colors[:len(manufacturer_labels)],
                          returnable_count=returnable_count,
                          non_returnable_count=non_returnable_count)

def parse_pdf_to_csv(pdf_file):
    """Parse PDF file and extract tabular data to CSV format."""
    csv_data = []

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            # Extract tables from the page
            tables = page.extract_tables()

            for table in tables:
                # Skip empty tables
                if not table or len(table) < 2:
                    continue

                # Assume first row is headers
                headers = [str(cell).strip() if cell else '' for cell in table[0]]

                # Process data rows
                for row in table[1:]:
                    row_data = {}
                    for i, cell in enumerate(row):
                        if i < len(headers):
                            row_data[headers[i]] = str(cell).strip() if cell else ''

                    # Only add rows that have some data
                    if any(row_data.values()):
                        csv_data.append(row_data)

    return csv_data

@app.route('/pdf_upload/<return_no>', methods=['POST'])
@login_required
def pdf_upload(return_no):
    return_report = ReturnReport.query.filter_by(return_no=return_no).first_or_404()
    form = PDFUploadForm()

    if form.validate_on_submit():
        pdf_file = form.pdf_file.data
        if pdf_file and pdf_file.filename.endswith('.pdf'):
            try:
                # Parse PDF to extract tabular data
                csv_data = parse_pdf_to_csv(pdf_file)

                if not csv_data:
                    flash('No tabular data found in the PDF file.', 'warning')
                    return redirect(url_for('add_item', return_no=return_no))

                # Create CSV content for download/review
                output = io.StringIO()
                if csv_data:
                    fieldnames = csv_data[0].keys()
                    writer = csv.DictWriter(output, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(csv_data)

                # Store the parsed CSV data in session or temporary file for review
                # For now, we'll create a downloadable CSV file
                csv_content = output.getvalue()

                # Create a response with the CSV file
                response = send_file(
                    io.BytesIO(csv_content.encode('utf-8')),
                    as_attachment=True,
                    download_name=f'parsed_data_{return_no}.csv',
                    mimetype='text/csv'
                )

                flash('PDF parsed successfully! Download the CSV file to review the extracted data before uploading.', 'success')
                return response

            except Exception as e:
                flash(f'Error parsing PDF: {str(e)}', 'danger')
        else:
            flash('Please upload a valid PDF file.', 'danger')

    return redirect(url_for('add_item', return_no=return_no))

def generate_return_letter_pdf(return_report):
    """Generate a PDF return letter for a specific return report."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=1,  # Center
    )
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=20,
    )
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=12,
    )

    story = []

    # Header with logo placeholder (since we don't have actual logos)
    story.append(Paragraph("PHARMARETURNS PROCESSING CENTER", title_style))
    story.append(Spacer(1, 20))

    # Letter details
    story.append(Paragraph("Return Acknowledgment Letter", subtitle_style))
    story.append(Spacer(1, 12))

    story.append(Paragraph(f"Return Number: {return_report.return_no}", normal_style))
    story.append(Paragraph(f"Invoice Date: {return_report.invoice_date.strftime('%B %d, %Y')}", normal_style))
    story.append(Paragraph(f"Service Type: {return_report.service_type}", normal_style))
    story.append(Spacer(1, 20))

    # Summary table
    story.append(Paragraph("Return Summary:", subtitle_style))

    summary_data = [
        ['ERV', 'Credit Received', 'Fees', 'Amount Paid', 'Last Payment Date'],
        [
            f"${return_report.ERV:.2f}",
            f"${return_report.credit_received:.2f}",
            f"${return_report.fees:.2f}",
            f"${return_report.amount_paid:.2f}",
            return_report.last_payment_date.strftime('%Y-%m-%d')
        ]
    ]

    summary_table = Table(summary_data)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    story.append(summary_table)
    story.append(Spacer(1, 20))

    # Manufacturer breakdown
    if return_report.breakdowns:
        story.append(Paragraph("Manufacturer Breakdown:", subtitle_style))

        breakdown_data = [['Manufacturer', 'ERV', 'Expiration Date']]
        for breakdown in return_report.breakdowns:
            breakdown_data.append([
                breakdown.manufacturer_name,
                f"${breakdown.ERV:.2f}",
                breakdown.expiration_date.strftime('%Y-%m-%d')
            ])

        breakdown_table = Table(breakdown_data)
        breakdown_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))

        story.append(breakdown_table)
        story.append(Spacer(1, 20))

    # Closing
    story.append(Paragraph("Thank you for your return submission. This letter serves as acknowledgment of receipt.", normal_style))
    story.append(Spacer(1, 20))
    story.append(Paragraph("Sincerely,", normal_style))
    story.append(Spacer(1, 30))
    story.append(Paragraph("PharmaReturns Processing Team", normal_style))
    story.append(Paragraph("_______________________________", normal_style))
    story.append(Paragraph("Signature", normal_style))

    doc.build(story)
    buffer.seek(0)
    return buffer

@app.route('/reports/<return_no>/pdf')
@login_required
def download_return_letter(return_no):
    return_report = ReturnReport.query.filter_by(return_no=return_no).first_or_404()
    pdf_buffer = generate_return_letter_pdf(return_report)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f'return_letter_{return_no}.pdf',
        mimetype='application/pdf'
    )

@app.route('/reports/summary')
@login_required
def reports_summary():
    # Aggregate totals
    total_erv = db.session.query(db.func.sum(ReturnReport.ERV)).scalar() or 0
    total_credits = db.session.query(db.func.sum(ReturnReport.credit_received)).scalar() or 0
    total_fees = db.session.query(db.func.sum(ReturnReport.fees)).scalar() or 0

    # Compute classification-based values
    short_dated_value = db.session.query(db.func.sum(ReturnItem.extended_price)).join(Reason).filter(Reason.name == 'Short Dated').scalar() or 0
    outdated_value = db.session.query(db.func.sum(ReturnItem.extended_price)).join(Reason).filter(Reason.name == 'Outdated').scalar() or 0
    non_returnable_value = db.session.query(db.func.sum(ReturnItem.extended_price)).join(Reason).filter(Reason.name == 'Non-Returnable').scalar() or 0

    # Aggregated manufacturer data
    manufacturer_data = db.session.query(
        ManufacturerBreakdown.manufacturer_name,
        db.func.sum(ManufacturerBreakdown.ERV).label('total_erv'),
        db.func.count(ManufacturerBreakdown.id).label('return_count')
    ).group_by(ManufacturerBreakdown.manufacturer_name).all()

    # Add percentages to manufacturer data
    for m in manufacturer_data:
        m.percentage = (m.total_erv / total_erv * 100) if total_erv > 0 else 0

    # Aggregated category data
    category_data = db.session.query(
        ReturnCategory.name,
        db.func.sum(ReturnItem.extended_price).label('total_value'),
        db.func.count(ReturnItem.id).label('item_count')
    ).join(ReturnItem).group_by(ReturnCategory.name).all()

    # Data for charts
    manufacturer_labels = [m.manufacturer_name for m in manufacturer_data]
    manufacturer_percentages = [m.percentage for m in manufacturer_data]
    manufacturer_colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', '#FF6384', '#C9CBCF']

    # Returnable vs Non-Returnable counts
    returnable_count = db.session.query(db.func.count(ReturnItem.id)).join(Reason).filter(Reason.name == 'Returnable').scalar() or 0
    non_returnable_count = db.session.query(db.func.count(ReturnItem.id)).join(Reason).filter(Reason.name.in_(['Non-Returnable', 'Outdated', 'Short Dated'])).scalar() or 0

    return render_template('reports.html',
                          total_erv=total_erv,
                          total_credits=total_credits,
                          total_fees=total_fees,
                          short_dated_value=short_dated_value,
                          outdated_value=outdated_value,
                          non_returnable_value=non_returnable_value,
                          manufacturer_data=manufacturer_data,
                          category_data=category_data,
                          manufacturer_labels=manufacturer_labels,
                          manufacturer_percentages=manufacturer_percentages,
                          manufacturer_colors=manufacturer_colors[:len(manufacturer_labels)],
                          returnable_count=returnable_count,
                          non_returnable_count=non_returnable_count)

@app.route('/reports/returnable_nonreturnable')
@login_required
def reports_returnable_nonreturnable():
    # Get returnable items from ManufacturerBreakdown (data from /new_return)
    returnable_items = ManufacturerBreakdown.query.all()

    # Get non-returnable items
    non_returnable_items = db.session.query(ReturnItem).join(Reason).filter(Reason.name.in_(['Non-Returnable', 'Outdated', 'Short Dated'])).all()

    # Calculate totals
    returnable_total = sum(item.ERV for item in returnable_items)
    non_returnable_total = sum(item.extended_price for item in non_returnable_items)
    grand_total = returnable_total + non_returnable_total

    return render_template('reports_returnable_nonreturnable.html',
                          returnable_items=returnable_items,
                          non_returnable_items=non_returnable_items,
                          returnable_total=returnable_total,
                          non_returnable_total=non_returnable_total,
                          grand_total=grand_total)

@app.route('/reports/returnable_nonreturnable/pdf')
@login_required
def reports_returnable_nonreturnable_pdf():
    # For now, use ReportLab to generate PDF since WeasyPrint has installation issues on Windows
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from io import BytesIO

    # Get returnable items from ManufacturerBreakdown (data from /new_return)
    returnable_items = ManufacturerBreakdown.query.all()

    # Get non-returnable items
    non_returnable_items = db.session.query(ReturnItem).join(Reason).filter(Reason.name.in_(['Non-Returnable', 'Outdated', 'Short Dated'])).all()

    # Calculate totals
    returnable_total = sum(item.ERV for item in returnable_items)
    non_returnable_total = sum(item.extended_price for item in non_returnable_items)
    grand_total = returnable_total + non_returnable_total

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=1,  # Center
    )
    section_style = ParagraphStyle(
        'SectionStyle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=20,
    )

    story = []

    # Title
    story.append(Paragraph("Returnable / Non-Returnable Report", title_style))
    story.append(Spacer(1, 20))

    # Returnable Items Section
    story.append(Paragraph("Returnable Items", section_style))

    if returnable_items:
        data = [['Return No', 'Manufacturer', 'ERV', 'Expiration Date']]
        for item in returnable_items:
            data.append([
                item.return_report.return_no,
                item.manufacturer_name,
                f"${item.ERV:.2f}",
                item.expiration_date.strftime('%Y-%m-%d')
            ])

        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.green),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(table)
        story.append(Spacer(1, 20))

    # Non-Returnable Items Section
    story.append(Paragraph("Non-Returnable Items", section_style))

    if non_returnable_items:
        data = [['Return No', 'NDC', 'Description', 'Lot No', 'Exp Date', 'Manufacturer', 'Reason', 'Extended Price']]
        for item in non_returnable_items:
            data.append([
                item.return_report.return_no,
                item.ndc,
                item.description,
                item.lot_no,
                item.exp_date.strftime('%Y-%m-%d'),
                item.manufacturer,
                item.reason.name,
                f"${item.extended_price:.2f}"
            ])

        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.red),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(table)
        story.append(Spacer(1, 20))

    # Totals
    story.append(Paragraph("Totals", section_style))
    story.append(Paragraph(f"Returnable Total: ${returnable_total:.2f}", styles['Normal']))
    story.append(Paragraph(f"Non-Returnable Total: ${non_returnable_total:.2f}", styles['Normal']))
    story.append(Paragraph(f"Grand Total: ${grand_total:.2f}", styles['Normal']))

    doc.build(story)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name='returnable_nonreturnable_report.pdf',
        mimetype='application/pdf'
    )

@app.route('/export_excel')
@login_required
def export_excel():
    # Get filters from request args
    manufacturer = request.args.get('manufacturer', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    category = request.args.get('category', '')

    # Query return items with joins
    query = db.session.query(ReturnItem).join(ReturnReport).join(Reason).join(ReturnCategory)

    if manufacturer:
        query = query.filter(ReturnItem.manufacturer.ilike(f'%{manufacturer}%'))
    if start_date:
        query = query.filter(ReturnReport.invoice_date >= start_date)
    if end_date:
        query = query.filter(ReturnReport.invoice_date <= end_date)
    if category:
        query = query.filter(ReturnCategory.name.ilike(f'%{category}%'))

    items = query.all()

    # Create DataFrame
    data = []
    for item in items:
        data.append({
            'Return No': item.return_report.return_no,
            'Invoice Date': item.return_report.invoice_date.strftime('%Y-%m-%d') if item.return_report.invoice_date else '',
            'NDC': item.ndc,
            'Description': item.description,
            'Lot No': item.lot_no,
            'Exp Date': item.exp_date.strftime('%Y-%m-%d'),
            'Pkg Size': item.pkg_size,
            'Full Qty': item.full_qty,
            'Partial Qty': item.partial_qty,
            'Unit Price': item.unit_price,
            'Extended Price': item.extended_price,
            'Category': item.category.name if item.category else '',
            'Reason': item.reason.name,
            'Manufacturer': item.manufacturer
        })

    df = pd.DataFrame(data)

    # Create Excel file in memory
    from io import BytesIO
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Returns_Report', index=False)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name='Returns_Report.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/manufacturer/<name>')
@login_required
def manufacturer_details(name):
    # Get all return reports for this manufacturer
    manufacturer_breakdowns = ManufacturerBreakdown.query.filter_by(manufacturer_name=name).all()

    # Get all items for this manufacturer
    items = ReturnItem.query.filter_by(manufacturer=name).all()

    # Calculate subtotals
    total_erv = sum(bd.ERV for bd in manufacturer_breakdowns)
    total_extended_price = sum(item.extended_price for item in items)

    # Group items by return report
    returns_data = {}
    for item in items:
        return_no = item.return_report.return_no
        if return_no not in returns_data:
            returns_data[return_no] = {
                'return_report': item.return_report,
                'items': [],
                'subtotal': 0
            }
        returns_data[return_no]['items'].append(item)
        returns_data[return_no]['subtotal'] += item.extended_price

    return render_template('manufacturer.html',
                         manufacturer_name=name,
                         total_erv=total_erv,
                         total_extended_price=total_extended_price,
                         returns_data=returns_data)

# --- ADMIN ROUTES ---

@app.route('/admin/reasons')
@login_required
@admin_required
def admin_reasons():
    reasons = Reason.query.all()
    return render_template('admin_reasons.html', reasons=reasons)

@app.route('/admin/reasons/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_reason():

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')

        if not name or not description:
            flash('Please fill in all fields.', 'danger')
            return redirect(url_for('add_reason'))

        if Reason.query.filter_by(name=name).first():
            flash('Reason name already exists.', 'danger')
            return redirect(url_for('add_reason'))

        new_reason = Reason(name=name, description=description)
        db.session.add(new_reason)
        db.session.commit()
        flash('Reason added successfully!', 'success')
        return redirect(url_for('admin_reasons'))

    return render_template('add_reason.html')

@app.route('/admin/reasons/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_reason(id):

    reason = Reason.query.get_or_404(id)

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')

        if not name or not description:
            flash('Please fill in all fields.', 'danger')
            return redirect(url_for('edit_reason', id=id))

        existing_reason = Reason.query.filter_by(name=name).first()
        if existing_reason and existing_reason.id != id:
            flash('Reason name already exists.', 'danger')
            return redirect(url_for('edit_reason', id=id))

        reason.name = name
        reason.description = description
        db.session.commit()
        flash('Reason updated successfully!', 'success')
        return redirect(url_for('admin_reasons'))

    return render_template('edit_reason.html', reason=reason)

@app.route('/admin/reasons/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_reason(id):

    reason = Reason.query.get_or_404(id)

    # Check if reason is being used
    if reason.items:
        flash('Cannot delete reason that is being used by items.', 'danger')
        return redirect(url_for('admin_reasons'))

    db.session.delete(reason)
    db.session.commit()
    flash('Reason deleted successfully!', 'success')
    return redirect(url_for('admin_reasons'))

# --- ADMIN USER MANAGEMENT ROUTES ---

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        company_name = request.form.get('company_name')
        role = request.form.get('role')

        # Validate inputs
        if not username or not email or not role:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('edit_user', id=id))

        # Check for duplicate username/email
        existing_user = User.query.filter(
            ((User.username == username) | (User.email == email)) & (User.id != id)
        ).first()
        if existing_user:
            flash('Username or email already exists.', 'danger')
            return redirect(url_for('edit_user', id=id))

        user.username = username
        user.email = email
        user.company_name = company_name
        user.role = role
        db.session.commit()
        flash('User updated successfully!', 'success')
        return redirect(url_for('admin_users'))

    return render_template('edit_user.html', user=user)

@app.route('/admin/users/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(id):
    user = User.query.get_or_404(id)

    # Prevent deleting self
    if user.id == current_user.id:
        flash('Cannot delete your own account.', 'danger')
        return redirect(url_for('admin_users'))

    # Check if user has submissions
    if user.submissions:
        flash('Cannot delete user that has submissions.', 'danger')
        return redirect(url_for('admin_users'))

    db.session.delete(user)
    db.session.commit()
    flash('User deleted successfully!', 'success')
    return redirect(url_for('admin_users'))

# --- ADMIN RETURN MANAGEMENT ROUTES ---

@app.route('/admin/returns')
@login_required
@admin_required
def admin_returns():
    returns = ReturnReport.query.all()
    return render_template('admin_returns.html', returns=returns)

@app.route('/admin/returns/<return_no>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_return(return_no):
    return_report = ReturnReport.query.filter_by(return_no=return_no).first_or_404()

    if request.method == 'POST':
        return_report.invoice_date = datetime.strptime(request.form.get('invoice_date'), '%Y-%m-%d').date()
        return_report.service_type = request.form.get('service_type')
        return_report.ERV = float(request.form.get('ERV'))
        return_report.credit_received = float(request.form.get('credit_received'))
        return_report.fees = float(request.form.get('fees'))
        return_report.amount_paid = float(request.form.get('amount_paid'))
        return_report.last_payment_date = datetime.strptime(request.form.get('last_payment_date'), '%Y-%m-%d').date()

        db.session.commit()
        flash('Return report updated successfully!', 'success')
        return redirect(url_for('admin_returns'))

    return render_template('edit_return.html', return_report=return_report)

@app.route('/admin/returns/<return_no>/delete', methods=['POST'])
@login_required
@admin_required
def delete_return(return_no):
    return_report = ReturnReport.query.filter_by(return_no=return_no).first_or_404()

    # Delete associated items and breakdowns
    for item in return_report.items:
        db.session.delete(item)
    for breakdown in return_report.breakdowns:
        db.session.delete(breakdown)

    db.session.delete(return_report)
    db.session.commit()
    flash('Return report and associated data deleted successfully!', 'success')
    return redirect(url_for('admin_returns'))

if __name__ == '__main__':
    # Use Gunicorn or similar for production; Flask's development server for testing
    app.run(debug=True)

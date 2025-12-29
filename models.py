from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    company_name = db.Column(db.String(120))
    role = db.Column(db.String(20), nullable=False, default='user')

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

class ReturnReport(db.Model):
    __tablename__ = 'return_reports'
    id = db.Column(db.Integer, primary_key=True)
    return_no = db.Column(db.String(50), unique=True, nullable=False)
    invoice_date = db.Column(db.Date, nullable=False)
    service_type = db.Column(db.String(100), nullable=False)
    ERV = db.Column(db.Float, nullable=False)
    credit_received = db.Column(db.Float, nullable=False)
    fees = db.Column(db.Float, nullable=False)
    amount_paid = db.Column(db.Float, nullable=False)
    last_payment_date = db.Column(db.Date, nullable=False)

    # Optional relationship to ManufacturerBreakdown
    breakdowns = db.relationship('ManufacturerBreakdown', backref='return_report', lazy=True)
    # Relationship to ReturnItem
    items = db.relationship('ReturnItem', backref='return_report', lazy=True)

class CheckStatement(db.Model):
    __tablename__ = 'check_statements'
    id = db.Column(db.Integer, primary_key=True)
    statement_no = db.Column(db.String(50), unique=True, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    check_amount = db.Column(db.Float, nullable=False)
    check_no = db.Column(db.String(50), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Pending')

    # Relationship to CheckDetail
    details = db.relationship('CheckDetail', backref='check_statement', lazy=True)

class CheckDetail(db.Model):
    __tablename__ = 'check_details'
    id = db.Column(db.Integer, primary_key=True)
    check_statement_id = db.Column(db.Integer, db.ForeignKey('check_statements.id'), nullable=False)
    return_no = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    pdf_file = db.Column(db.String(255))  # Path to PDF file

class ManufacturerBreakdown(db.Model):
    __tablename__ = 'manufacturer_breakdowns'
    id = db.Column(db.Integer, primary_key=True)
    return_report_id = db.Column(db.Integer, db.ForeignKey('return_reports.id'), nullable=False)
    manufacturer_name = db.Column(db.String(120), nullable=False)
    ERV = db.Column(db.Float, nullable=False)
    expiration_date = db.Column(db.Date, nullable=False)

class ReturnCategory(db.Model):
    __tablename__ = 'return_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class Reason(db.Model):
    __tablename__ = 'reasons'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=False)

class ReturnItem(db.Model):
    __tablename__ = 'return_items'
    id = db.Column(db.Integer, primary_key=True)
    return_report_id = db.Column(db.Integer, db.ForeignKey('return_reports.id'), nullable=False)
    ndc = db.Column(db.String(11), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    lot_no = db.Column(db.String(50), nullable=False)
    exp_date = db.Column(db.Date, nullable=False)
    pkg_size = db.Column(db.Integer, nullable=False)
    full_qty = db.Column(db.Integer, nullable=False)
    partial_qty = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    extended_price = db.Column(db.Float, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('return_categories.id'), nullable=False)
    reason_id = db.Column(db.Integer, db.ForeignKey('reasons.id'), nullable=False)
    manufacturer = db.Column(db.String(120), nullable=False)

    # Relationships
    category = db.relationship('ReturnCategory', backref='items')
    reason = db.relationship('Reason', backref='items')
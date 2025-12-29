from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, EmailField, DateField, FloatField, FieldList, FormField, FileField, SelectField, IntegerField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError
from datetime import date, timedelta
from models import ReturnCategory
import csv
import io

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=80)])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class ManufacturerBreakdownForm(FlaskForm):
    manufacturer_name = StringField('Manufacturer Name', validators=[DataRequired()])
    ERV = FloatField('ERV', validators=[DataRequired()])
    expiration_date = DateField('Expiration Date', validators=[DataRequired()])

    def validate_expiration_date(self, field):
        if field.data <= date.today():
            raise ValidationError('Expiration date must be in the future.')

class CheckDetailForm(FlaskForm):
    return_no = StringField('Return #', validators=[DataRequired()])
    amount = FloatField('Amount', validators=[DataRequired()])
    pdf_file = FileField('PDF Upload')

    def validate_amount(self, field):
        if field.data <= 0:
            raise ValidationError('Amount must be a positive number.')

class CheckForm(FlaskForm):
    statement_no = StringField('Statement No', validators=[DataRequired()])
    payment_date = DateField('Payment Date', validators=[DataRequired()])
    check_no = StringField('Check No', validators=[DataRequired()])
    amount = FloatField('Amount', validators=[DataRequired()])
    status = StringField('Status', default='Pending')
    details = FieldList(FormField(CheckDetailForm), min_entries=0)
    submit = SubmitField('Submit Check')

    def validate_amount(self, field):
        if field.data <= 0:
            raise ValidationError('Amount must be a positive number.')

class ReturnForm(FlaskForm):
    invoice_date = DateField('Invoice Date', validators=[DataRequired()])
    service_type = StringField('Service Type', validators=[DataRequired()])
    ERV = FloatField('ERV', validators=[DataRequired()])
    credit_received = FloatField('Credit Received', validators=[DataRequired()])
    fees = FloatField('Fees', validators=[DataRequired()])
    amount_paid = FloatField('Amount Paid', validators=[DataRequired()])
    last_payment_date = DateField('Last Payment Date', validators=[DataRequired()])
    manufacturers = FieldList(FormField(ManufacturerBreakdownForm), min_entries=0)
    submit = SubmitField('Submit Return')

    def validate_ERV(self, field):
        if field.data < 0:
            raise ValidationError('ERV must be a non-negative number.')

    def validate_credit_received(self, field):
        if field.data < 0:
            raise ValidationError('Credit received must be a non-negative number.')

    def validate_fees(self, field):
        if field.data < 0:
            raise ValidationError('Fees must be a non-negative number.')

    def validate_amount_paid(self, field):
        if field.data < 0:
            raise ValidationError('Amount paid must be a non-negative number.')

class ReturnItemForm(FlaskForm):
    manufacturer = SelectField('Manufacturer', validators=[DataRequired()], choices=[])
    ndc = StringField('NDC', validators=[DataRequired(), Length(min=11, max=11)])
    description = StringField('Description', validators=[DataRequired()])
    lot_no = StringField('Lot Number', validators=[DataRequired()])
    exp_date = DateField('Expiration Date', validators=[DataRequired()])
    pkg_size = IntegerField('Package Size', validators=[DataRequired()])
    full_qty = IntegerField('Full Quantity', validators=[DataRequired()])
    partial_qty = IntegerField('Partial Quantity', validators=[DataRequired()])
    unit_price = FloatField('Unit Price', validators=[DataRequired()])
    extended_price = FloatField('Extended Price', validators=[DataRequired()])
    category = SelectField('Category', validators=[DataRequired()], choices=[])
    submit = SubmitField('Add Item')

    def validate_ndc(self, field):
        if not field.data.isdigit() or len(field.data) != 11:
            raise ValidationError('NDC must be exactly 11 digits.')

    def validate_exp_date(self, field):
        today = date.today()
        future_6_months = today + timedelta(days=180)
        if field.data <= future_6_months:
            raise ValidationError('Expiration date must be more than 6 months in the future.')

    def validate_full_qty(self, field):
        if field.data < 0:
            raise ValidationError('Full quantity must be non-negative.')

    def validate_partial_qty(self, field):
        if field.data < 0:
            raise ValidationError('Partial quantity must be non-negative.')

    def validate_unit_price(self, field):
        if field.data < 0:
            raise ValidationError('Unit price must be non-negative.')

    def validate_extended_price(self, field):
        if field.data < 0:
            raise ValidationError('Extended price must be non-negative.')

class BulkUploadForm(FlaskForm):
    csv_file = FileField('CSV File', validators=[DataRequired()])
    submit = SubmitField('Upload CSV')

class PDFUploadForm(FlaskForm):
    pdf_file = FileField('PDF File', validators=[DataRequired()])
    submit = SubmitField('Upload and Parse PDF')
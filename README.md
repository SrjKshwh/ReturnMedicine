# Pharmaceutical Returns Portal MVP

A Flask-based web application for managing pharmaceutical returns, including return reports, check statements, manufacturer breakdowns, and PDF generation.

## Features

- **User Authentication**: Secure login and registration system
- **Return Management**: Create and track return reports with manufacturer breakdowns
- **Check Processing**: Manage check statements and payment details
- **PDF Generation**: Generate manifests, shipping labels, and return letters
- **Reporting**: View aggregated reports and manufacturer breakdowns
- **File Uploads**: Support for PDF attachments to check details
- **Responsive Design**: Mobile-friendly interface using Bootstrap 5

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd returnMedicne
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up the database:
```bash
python create_tables.py
```

4. Run the application:
```bash
python app.py
```

The application will be available at `http://localhost:5000`

## Usage

### User Flow
1. **Register/Login**: Create an account or log in with existing credentials
2. **Create Return**: Submit a new return report with manufacturer breakdown
3. **Create Check**: Add check statements with payment details
4. **View Reports**: Access aggregated reports and manufacturer data

### Default Users
- Username: `user1`, Password: `pass123` (Regular User)
- Username: `reviewer1`, Password: `review123` (Reviewer)

## Project Structure

```
returnMedicne/
├── app.py                 # Main Flask application
├── models.py             # Database models
├── forms.py              # WTForms definitions
├── create_tables.py      # Database initialization
├── requirements.txt      # Python dependencies
├── templates/            # Jinja2 templates
│   ├── base.html
│   ├── dashboard.html
│   ├── login.html
│   ├── register.html
│   ├── new_return.html
│   ├── new_check.html
│   ├── returns.html
│   ├── checks.html
│   ├── reports.html
│   └── ...
├── static/               # Static files (CSS, JS, uploads)
│   └── uploads/
└── instance/             # Database files
    └── returns_mvp.db
```

## Technologies Used

- **Backend**: Flask, SQLAlchemy, Flask-Login
- **Frontend**: Bootstrap 5, Jinja2 templates
- **Database**: SQLite (development), PostgreSQL (production)
- **PDF Generation**: ReportLab
- **Forms**: WTForms

## API Endpoints

- `/` - Home page
- `/login` - User login
- `/register` - User registration
- `/dashboard` - User dashboard
- `/new_return` - Create new return report
- `/new_check` - Create new check statement
- `/returns` - View all returns
- `/checks` - View all checks
- `/reports` - View reports

## Development

This is an MVP (Minimum Viable Product) built over 14 days as part of a development challenge. The application includes:

- Complete CRUD operations for returns and checks
- Form validation and error handling
- Flash messages for user feedback
- Responsive design for mobile devices
- PDF generation for documents
- File upload functionality

## Testing

The application includes an end-to-end test script to verify the complete workflow:

```bash
python test_e2e.py
```

This test performs:
- User authentication
- Return report creation with manufacturer breakdowns
- Item addition with auto-classification
- Report generation
- PDF and Excel export functionality

## Deployment

For production deployment:

1. Set environment variables:
    - `SECRET_KEY`: A secure random key
    - `DATABASE_URL`: PostgreSQL connection string

2. Use a WSGI server like Gunicorn:
```bash
gunicorn app:create_app() -w 4 -b 0.0.0.0:8000
```

3. Consider using services like Render, Heroku, or AWS for hosting

## Database Setup

To initialize the database with sample data:

```bash
python create_tables.py
python seed_categories.py
python seed_reasons.py
python seed_users.py
```

## How to Use the returnMedicine App

### User Guide

The returnMedicine app streamlines the pharmaceutical returns process with automated classification and comprehensive reporting. Below is a step-by-step guide for different user roles.

#### For Regular Users

1. **Registration/Login**
   - Visit the app at `http://localhost:5000`
   - Click "Register" to create a new account with your company details
   - Or login with existing credentials (default: user1/pass123)

2. **Dashboard Overview**
   - View your recent submissions and their statuses
   - See key metrics like total ERV and short-dated value
   - Access top manufacturers by ERV

3. **Creating a Return Submission**
   - Click "New Submission" from the dashboard
   - Add items by entering:
     - NDC (National Drug Code)
     - Quantity
     - Expiration Date
   - Items are automatically classified as:
     - **Returnable**: Eligible for credit (6+ months to expiry, within policy)
     - **Short Dated**: Expires within 6 months
     - **Outdated**: Already expired
     - **Non-Returnable**: Policy restricted or other issues
   - Review estimated credits for each item
   - Finalize submission to send for review

4. **Viewing Submissions**
   - Access your submissions from the dashboard
   - Download PDF manifests and shipping labels
   - Track submission status (Draft → Submitted → Received → Credited)

#### For Reviewers

1. **Review Submissions**
   - Login with reviewer credentials (default: reviewer1/review123)
   - View all pending submissions from users
   - Update submission status (Received, Credited)
   - Add notes during review process

#### For Administrators

1. **User Management**
   - Access admin panel at `/admin/users`
   - Add, edit, or delete user accounts
   - Manage user roles (user, reviewer, admin)

2. **Reason Management**
   - Manage classification reasons at `/admin/reasons`
   - Add custom reasons for item classification

3. **Return Management**
   - View and edit all return reports
   - Manage manufacturer breakdowns and ERV data

#### Reports and Analytics

1. **Access Reports**
   - Navigate to "Reports" section
   - View aggregated data by manufacturer, category, and classification
   - See returnable vs non-returnable breakdowns

2. **Export Data**
   - Download Excel reports with filters
   - Generate PDF reports for returnable/non-returnable items

### Flow Diagram

```
┌─────────────────┐
│   User Login    │
│   / Register    │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│   Dashboard     │
│ • View Metrics  │
│ • Recent Subs   │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐     ┌─────────────────┐
│ Create Submission│────▶│  Auto-Classify │
│ • Add NDC        │     │  Items         │
│ • Quantity       │     │ • Returnable   │
│ • Exp Date       │     │ • Short Dated  │
└─────────────────┘     │ • Outdated     │
          │             │ • Non-Returnable│
          ▼             └─────────────────┘
┌─────────────────┐             │
│ Review & Finalize│             │
│ • Check Credits  │             │
│ • Download PDFs  │             │
└─────────┬───────┘             │
          │                     │
          ▼                     ▼
┌─────────────────┐     ┌─────────────────┐
│   Submit for    │     │   Reviewer      │
│   Processing    │────▶│   Review        │
└─────────────────┘     │ • Update Status │
          │             │ • Add Notes     │
          ▼             └─────────────────┘
┌─────────────────┐             │
│   Processing    │             │
│ • Received      │             │
│ • Credited      │             │
└─────────┬───────┘             │
          │                     │
          ▼                     ▼
┌─────────────────┐     ┌─────────────────┐
│   Reports &     │     │   Admin Panel   │
│   Analytics     │     │ • User Mgmt     │
│ • Manufacturer  │     │ • Reason Mgmt   │
│ • Category      │     │ • Return Mgmt   │
│ • Export Data   │     └─────────────────┘
└─────────────────┘
```

## Sample Data for Testing

Use the following sample data to test all implementations of the returnMedicine app:

### Default Test Users
- **Regular User**: username: `user1`, password: `pass123`
- **Reviewer**: username: `reviewer1`, password: `review123`

### Sample NDCs for Testing
| NDC | Drug Name | Manufacturer | Policy | Base Credit |
|-----|-----------|--------------|--------|-------------|
| 0002-1234-01 | Sample Drug A 10mg | PharmaCo | - | $12.50 |
| 0003-5678-02 | Sample Drug B 500mg | MediCorp | - | $8.99 |
| 0004-9012-03 | Ineligible Product | NoReturn Inc | X | $0.00 |

### Test Scenarios

#### 1. Returnable Item Submission
- NDC: 0002-1234-01
- Quantity: 100
- Expiration Date: 2026-12-31 (future date >6 months)
- Expected: Classified as "Returnable", credit calculated

#### 2. Short Dated Item
- NDC: 0002-1234-01
- Quantity: 50
- Expiration Date: 2025-03-01 (within 6 months)
- Expected: Classified as "Short Dated"

#### 3. Outdated Item
- NDC: 0002-1234-01
- Quantity: 25
- Expiration Date: 2024-01-01 (past date)
- Expected: Classified as "Outdated"

#### 4. Non-Returnable Item (Policy Restricted)
- NDC: 0004-9012-03
- Quantity: 10
- Expiration Date: 2026-06-15
- Expected: Classified as "Non-Returnable (Policy Restricted)"

#### 5. Bulk Return Discount
- NDC: 0002-1234-01
- Quantity: 150 (≥100 for 5% discount)
- Expiration Date: 2027-01-15
- Expected: Credit with bulk discount applied

#### 6. Long Expiry Adjustment
- NDC: 0002-1234-01
- Quantity: 75
- Expiration Date: 2028-12-31 (>2 years)
- Expected: 10% credit reduction for long expiry

### Sample Return Report Data
The app includes pre-seeded return reports with manufacturer breakdowns:

- RTN-241231-1200: Pfizer, J&J, Merck returns
- RTN-241231-1300: AstraZeneca, Novartis, GSK returns
- RTN-241231-1400: BMS, Lilly, AbbVie returns
- RTN-241231-1500: Sanofi, Roche, Bayer returns
- RTN-241231-1600: Amgen, Gilead, Regeneron returns

### Testing Checklist
- [ ] User registration and login
- [ ] Create submission with multiple items
- [ ] Auto-classification of items
- [ ] Credit calculation with discounts
- [ ] PDF manifest and label generation
- [ ] Submission status updates
- [ ] Reviewer approval workflow
- [ ] Admin user/reason management
- [ ] Reports and Excel export
- [ ] Manufacturer breakdown views

## License

This project is for educational purposes as part of a development challenge.
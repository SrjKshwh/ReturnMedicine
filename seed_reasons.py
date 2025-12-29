from flask import Flask
from models import db, Reason

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///returns_mvp.db'
db.init_app(app)

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
    else:
        print("Reasons already exist.")
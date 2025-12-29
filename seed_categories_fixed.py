from models import db, ReturnCategory
from flask import Flask
import os

# Create app context
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///returns_mvp.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

def seed_categories():
    with app.app_context():
        # Clear existing categories first
        ReturnCategory.query.delete()

        # Add the required rule definitions
        categories = [
            'Short Dated',
            'Outdated',
            'Future Dated',
            'Non-Returnable',
            'Returnable'  # Also add this as it's used in the system
        ]

        for category_name in categories:
            category = ReturnCategory(name=category_name)
            db.session.add(category)

        db.session.commit()
        print(f"Seeded {len(categories)} categories successfully")

if __name__ == "__main__":
    seed_categories()
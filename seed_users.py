from flask import Flask
from models import db, User

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///returns_mvp.db'
db.init_app(app)

with app.app_context():
    if User.query.count() == 0:
        sample_users = [
            {'username': 'user1', 'email': 'user1@example.com', 'password': 'pass123', 'company_name': 'MediPharm Pharmacy', 'role': 'user'},
            {'username': 'user2', 'email': 'user2@example.com', 'password': 'pass123', 'company_name': 'HealthCare Solutions', 'role': 'user'},
            {'username': 'reviewer1', 'email': 'reviewer1@example.com', 'password': 'review123', 'company_name': 'PharmaReturns Processing', 'role': 'reviewer'},
            {'username': 'admin', 'email': 'admin@example.com', 'password': 'admin123', 'company_name': 'Admin', 'role': 'admin'},
        ]
        for data in sample_users:
            user = User(**data)
            user.set_password(data['password'])
            db.session.add(user)
        db.session.commit()
        print("Sample users seeded with different roles.")
    else:
        print("Users already exist.")
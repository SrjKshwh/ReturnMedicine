from models import db
from flask import Flask
from models import ReturnCategory

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///returns_mvp.db'
db.init_app(app)

with app.app_context():
    if ReturnCategory.query.count() == 0:
        categories = ['Short Dated', 'Outdated', 'Future Dated', 'Non-Returnable']
        for c in categories:
            cat = ReturnCategory(name=c)
            db.session.add(cat)
        db.session.commit()
        print('Categories seeded')
    else:
        print('Categories already exist')
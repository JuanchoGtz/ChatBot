from main import User, SessionLocal

db = SessionLocal()
admin = User(username="juan", password="1234", role="admin")
db.add(admin)
db.commit()
db.close()

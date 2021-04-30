from flask.cli import FlaskGroup
from race import app, db, User
cli = FlaskGroup(app)

FLAG = open('flag.txt', 'r').read()

@cli.command("create_db")
def create_db():
    db.drop_all()
    db.create_all()
    db.session.add(User(email="webpentest@gmail.com", flag=FLAG)) # <- attack this user
    db.session.commit()

if __name__ == "__main__":
    cli()

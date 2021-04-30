import string
import random
import datetime
import uuid
import sqlalchemy
import logging
import logging.handlers
import json
import time
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

from flask import Flask, session, redirect, request
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# don't wanna deal with all those races...
app.config.from_object('race.config.Config')

app.logger.addHandler(logging.handlers.SysLogHandler(address=('poc.fun', 514))) # log to remote syslog

db = SQLAlchemy(app, engine_options={'isolation_level':'REPEATABLE READ'})

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    flag = db.Column(db.String(100), nullable=False)


class EmailValidation(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    email = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(5), nullable=False)
    expiry_date = db.Column(db.DateTime)
    available_attempts = db.Column(db.Integer)

def send_code(email, code):
    #TODO: really send a code...
    pass

@app.route('/email-code/send/', methods=['POST'])
def send_email_code():
    email = request.form['email']
    verification_code = '%05d' % random.randint(0,99999)
    validation = EmailValidation(
        id=str(uuid.uuid4()),
        email=email,
        code=verification_code,
        expiry_date=datetime.datetime.now() + datetime.timedelta(hours=6),
        available_attempts = 5
    )
    send_code(email, verification_code)
    db.session.add(validation)
    db.session.commit()
    return validation.id

@app.route('/email-code/validate/', methods=['POST'])
def validate_email_code():
    validation_code = request.json['validation_code']
    validation_id = request.json['uuid']
    db.session.begin()
    validation = db.session.query(EmailValidation).filter(EmailValidation.id==validation_id).first()
    if not validation:
        return "Wrong UUID"
    if validation.expiry_date < datetime.datetime.now():
        return "Expired: %s < %s" % (validation.expiry_date, datetime.datetime.now())
    if validation.code != validation_code:
        invalidate = False
        # Yay, using atomic decrements via DB, no writes will be lost
        validation.available_attempts = EmailValidation.available_attempts - 1 
        try:
            db.session.commit() # select and update in the same transation
        except sqlalchemy.exc.SQLAlchemyError:
            # some shenanigans! We're under attack, invalidate code immediately
            db.session.rollback() # rollback old txn to be able to proceed
            invalidate = True
        app.logger.warn("Verification attempt for validation_id %s failed! Request: %s" % (validation_id, json.dumps(request.json)))
        attempts = validation.available_attempts
        if invalidate or validation.available_attempts == 0:
            deleted = False
            #make sure that we delete even if we need to retry transaction multiple times
            while not deleted:
                try:
                    db.session.begin()
                    EmailValidation.query.filter_by(id=validation_id).delete()
                    db.session.commit()
                    deleted = True
                except sqlalchemy.exc.SQLAlchemyError:
                    db.session.rollback() # Rollback for retry
            if invalidate:
                return "Wrong code, shenanigans detected, no more attempts"
            else:
                return "Wrong code, no more attempts"
        else:
            return "Wrong code, %d attempts remain" % attempts
    else:
        user = db.session.query(User).filter(User.email==validation.email).first()
        if user:
            return user.flag
        else:
            return "Sorry, but the admin is in another castle"

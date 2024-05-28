import sqlite3
import os
from flask import g
from config import Config

DATABASE = Config.DATABASE

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

def init_db(app):
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                date TEXT,
                time TEXT,
                event TEXT,
                country TEXT,
                currency TEXT,
                previous REAL,
                estimate REAL,
                actual REAL,
                change REAL,
                impact TEXT,
                changePercentage REAL,
                unit TEXT
            )
        ''')
        db.commit()

def get_events():
    db = get_db()
    cur = db.execute('SELECT date, time, event, country, currency, previous, estimate, actual, change, impact, changePercentage, unit FROM events')
    events = cur.fetchall()
    return [
        {
            'date': row[0],
            'time': row[1],
            'event': row[2],
            'country': row[3],
            'currency': row[4],
            'previous': row[5],
            'estimate': row[6],
            'actual': row[7],
            'change': row[8],
            'impact': row[9],
            'changePercentage': row[10],
            'unit': row[11]
        } for row in events
    ]

import os, secrets

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_urlsafe(16)
    DATABASE = os.environ.get('DATABASE') or 'data/economic_events.db'
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DATABASE = os.path.join(BASE_DIR, 'data', 'economic_events.db')

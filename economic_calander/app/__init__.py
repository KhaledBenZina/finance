from flask import Flask
from app.routes import main
from app.database import init_db

def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')
    
    init_db(app)
    
    app.register_blueprint(main)
    
    return app

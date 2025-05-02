import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'mysql+pymysql://root:Pass%40123@localhost/semantic_grader'

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload size
    
    # Create upload directories if they don't exist
    @staticmethod
    def init_app(app):
        os.makedirs(os.path.join(Config.UPLOAD_FOLDER, 'question_papers'), exist_ok=True)
        os.makedirs(os.path.join(Config.UPLOAD_FOLDER, 'model_answers'), exist_ok=True)
        os.makedirs(os.path.join(Config.UPLOAD_FOLDER, 'student_answers'), exist_ok=True)

# This script adds the profile_photo column to the User table
# Save this in a file like 'add_profile_photo.py' and run it once to update your database

from app import app, db
from flask_migrate import Migrate

migrate = Migrate(app, db)

# Inside your app context, run:
with app.app_context():
    # Create a migration to add the profile_photo column
    # First, make sure your updated User model is imported
    
    # Option 1: If you're using Flask-Migrate, you can run:
    # $ flask db migrate -m "Add profile_photo to User model"
    # $ flask db upgrade
    
    # Option 2: For a quick direct update without migration versioning:
    try:
        # Check if column exists first
        db.engine.execute("SELECT profile_photo FROM user LIMIT 1")
        print("Column profile_photo already exists")
    except Exception:
        # Add the column if it doesn't exist
        db.engine.execute("ALTER TABLE user ADD COLUMN profile_photo VARCHAR(255)")
        print("Added profile_photo column to the user table")
        db.session.commit()

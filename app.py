from flask import Flask, render_template, redirect, url_for, request, flash, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import pandas as pd
from datetime import datetime

from config import Config
from semantic_grader.grader import SemanticGrader

app = Flask(__name__)
app.config.from_object(Config)
Config.init_app(app)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Initialize the grader
grader = SemanticGrader()

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True)
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    roll_number = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120))
    batch = db.Column(db.String(50))
    evaluations = db.relationship('Evaluation', backref='student', lazy='dynamic')

class QuestionPaper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    description = db.Column(db.Text)
    question_file_path = db.Column(db.String(255))
    model_answer_path = db.Column(db.String(255))
    total_marks = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    evaluations = db.relationship('Evaluation', backref='question_paper', lazy='dynamic')

class Evaluation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    question_paper_id = db.Column(db.Integer, db.ForeignKey('question_paper.id'))
    answer_file_path = db.Column(db.String(255))
    marks_obtained = db.Column(db.Float)
    percentage = db.Column(db.Float)
    feedback = db.Column(db.Text)
    evaluated_at = db.Column(db.DateTime, default=datetime.utcnow)
    evaluated_by = db.Column(db.Integer, db.ForeignKey('user.id'))

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

# Helper functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        
        login_user(user)
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('dashboard')
        return redirect(next_page)
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    question_papers = QuestionPaper.query.filter_by(user_id=current_user.id).all()
    recent_evaluations = Evaluation.query.join(QuestionPaper).filter(
        QuestionPaper.user_id == current_user.id
    ).order_by(Evaluation.evaluated_at.desc()).limit(5).all()
    
    student_count = Student.query.count()
    evaluation_count = Evaluation.query.join(QuestionPaper).filter(
        QuestionPaper.user_id == current_user.id
    ).count()
    
    return render_template('dashboard.html', 
                           question_papers=question_papers, 
                           recent_evaluations=recent_evaluations,
                           student_count=student_count,
                           evaluation_count=evaluation_count)

@app.route('/upload_questions', methods=['GET', 'POST'])
@login_required
def upload_questions():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        
        # Check if the post request has the file parts
        if 'question_file' not in request.files or 'model_answer_file' not in request.files:
            flash('Both files are required')
            return redirect(request.url)
        
        question_file = request.files['question_file']
        model_answer_file = request.files['model_answer_file']
        
        # If user does not select files, browser submits empty files
        if question_file.filename == '' or model_answer_file.filename == '':
            flash('Both files are required')
            return redirect(request.url)
        
        if not (allowed_file(question_file.filename) and allowed_file(model_answer_file.filename)):
            flash('Only PDF files are allowed')
            return redirect(request.url)
        
        # Save the files
        question_filename = secure_filename(question_file.filename)
        model_answer_filename = secure_filename(model_answer_file.filename)
        
        question_path = os.path.join(app.config['UPLOAD_FOLDER'], 'question_papers', question_filename)
        model_answer_path = os.path.join(app.config['UPLOAD_FOLDER'], 'model_answers', model_answer_filename)
        
        question_file.save(question_path)
        model_answer_file.save(model_answer_path)
        
        # Load questions from the PDF
        try:
            grader.parse_questions_from_pdf(model_answer_path)
            total_marks = sum(grader.max_marks)
            
            new_paper = QuestionPaper(
                title=title,
                description=description,
                question_file_path=question_path,
                model_answer_path=model_answer_path,
                total_marks=total_marks,
                user_id=current_user.id
            )
            
            db.session.add(new_paper)
            db.session.commit()
            
            flash('Question paper uploaded successfully')
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            flash(f'Error processing the PDF: {str(e)}')
            return redirect(request.url)
    
    return render_template('upload_questions.html')

@app.route('/students', methods=['GET', 'POST'])
@login_required
def students():
    if request.method == 'POST':
        roll_number = request.form.get('roll_number')
        name = request.form.get('name')
        email = request.form.get('email')
        batch = request.form.get('batch')
        
        # Check if student already exists
        existing_student = Student.query.filter_by(roll_number=roll_number).first()
        if existing_student:
            flash('Student with this roll number already exists')
            return redirect(url_for('students'))
        
        new_student = Student(roll_number=roll_number, name=name, email=email, batch=batch)
        db.session.add(new_student)
        db.session.commit()
        
        flash('Student added successfully')
        return redirect(url_for('students'))
    
    students_list = Student.query.all()
    return render_template('students.html', students=students_list)

@app.route('/students/import', methods=['POST'])
@login_required
def import_students():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'})
    
    if not file.filename.endswith(('.csv', '.xlsx')):
        return jsonify({'success': False, 'message': 'Only CSV and Excel files are allowed'})
    
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # Check for required columns
        required_columns = ['roll_number', 'name', 'email', 'batch']
        if not all(col in df.columns for col in required_columns):
            return jsonify({
                'success': False, 
                'message': f'File must contain columns: {", ".join(required_columns)}'
            })
        
        # Add students
        count = 0
        for _, row in df.iterrows():
            existing_student = Student.query.filter_by(roll_number=row['roll_number']).first()
            if not existing_student:
                new_student = Student(
                    roll_number=row['roll_number'],
                    name=row['name'],
                    email=row['email'],
                    batch=row['batch']
                )
                db.session.add(new_student)
                count += 1
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'{count} students imported successfully'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/evaluation', methods=['GET', 'POST'])
@login_required
def evaluation():
    question_papers = QuestionPaper.query.filter_by(user_id=current_user.id).all()
    students_list = Student.query.all()
    
    if request.method == 'POST':
        question_paper_id = request.form.get('question_paper_id')
        student_id = request.form.get('student_id')
        
        # Check if the post request has the file part
        if 'answer_file' not in request.files:
            flash('Answer file is required')
            return redirect(request.url)
        
        answer_file = request.files['answer_file']
        
        # If user does not select file, browser submits empty file
        if answer_file.filename == '':
            flash('Answer file is required')
            return redirect(request.url)
        
        if not allowed_file(answer_file.filename):
            flash('Only PDF files are allowed')
            return redirect(request.url)
        
        # Save the file
        answer_filename = secure_filename(answer_file.filename)
        answer_path = os.path.join(app.config['UPLOAD_FOLDER'], 'student_answers', answer_filename)
        answer_file.save(answer_path)
        
        # Evaluate the answer
        try:
            # Get the model answer for the question paper
            question_paper = QuestionPaper.query.get(question_paper_id)
            if not question_paper:
                flash('Question paper not found')
                return redirect(request.url)
            
            # Load questions from the model answer
            grader.parse_questions_from_pdf(question_paper.model_answer_path)
            
            # Grade the student's answer
            results = grader.grade_student_paper(answer_path)
            
            if not results:
                flash('Error evaluating the answer')
                return redirect(request.url)
            
            # Create an evaluation record
            new_evaluation = Evaluation(
                student_id=student_id,
                question_paper_id=question_paper_id,
                answer_file_path=answer_path,
                marks_obtained=results['total_score'],
                percentage=(results['total_score'] / results['max_possible']) * 100,
                feedback=', '.join(results['feedback']),
                evaluated_by=current_user.id
            )
            
            db.session.add(new_evaluation)
            db.session.commit()
            
            flash('Answer evaluated successfully')
            return redirect(url_for('results'))
            
        except Exception as e:
            flash(f'Error evaluating the answer: {str(e)}')
            return redirect(request.url)
    
    return render_template('evaluation.html', question_papers=question_papers, students=students_list)

@app.route('/results')
@login_required
def results():
    evaluations = Evaluation.query.join(QuestionPaper).filter(
        QuestionPaper.user_id == current_user.id
    ).order_by(Evaluation.evaluated_at.desc()).all()
    
    return render_template('results.html', evaluations=evaluations)

@app.route('/batch_evaluation', methods=['GET', 'POST'])
@login_required
def batch_evaluation():
    question_papers = QuestionPaper.query.filter_by(user_id=current_user.id).all()
    
    if request.method == 'POST':
        question_paper_id = request.form.get('question_paper_id')
        
        # Check if the post request has files
        if 'answer_files' not in request.files:
            flash('Answer files are required')
            return redirect(request.url)
        
        files = request.files.getlist('answer_files')
        
        if not files:
            flash('At least one answer file is required')
            return redirect(request.url)
        
        # Get the model answer for the question paper
        question_paper = QuestionPaper.query.get(question_paper_id)
        if not question_paper:
            flash('Question paper not found')
            return redirect(request.url)
        
        # Load questions from the model answer
        grader.parse_questions_from_pdf(question_paper.model_answer_path)
        
        # Create a temporary directory for batch processing
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save all files to temporary directory
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(temp_dir, filename)
                    file.save(file_path)
            
            # Batch grade
            try:
                output_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'results')
                os.makedirs(output_folder, exist_ok=True)
                
                grader.batch_grade_student_papers(temp_dir, output_folder)
                
                # TODO: Match filenames with students and save evaluations
                # This would require a naming convention for files or a mapping
                
                flash('Batch evaluation completed. Check results for details.')
                return redirect(url_for('results'))
                
            except Exception as e:
                flash(f'Error in batch evaluation: {str(e)}')
                return redirect(request.url)
    
    return render_template('batch_evaluation.html', question_papers=question_papers)

@app.route('/download/<file_type>/<int:id>')
@login_required
def download_file(file_type, id):
    if file_type == 'question':
        question_paper = QuestionPaper.query.get_or_404(id)
        return send_file(question_paper.question_file_path, as_attachment=True)
    elif file_type == 'model_answer':
        question_paper = QuestionPaper.query.get_or_404(id)
        return send_file(question_paper.model_answer_path, as_attachment=True)
    elif file_type == 'student_answer':
        evaluation = Evaluation.query.get_or_404(id)
        return send_file(evaluation.answer_file_path, as_attachment=True)
    else:
        flash('Invalid file type')
        return redirect(url_for('dashboard'))

# Create an admin user if none exists
# @app.before_first_request
# def create_admin():
#     if User.query.filter_by(username='admin').first() is None:
#         admin = User(username='admin', email='admin@example.com', is_admin=True)
#         admin.set_password('admin')
#         db.session.add(admin)
#         db.session.commit()

@app.route('/admin/manage', methods=['GET'])
@login_required
def admin_manage():
    # Check if the current user is an admin
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('dashboard'))
    
    # Get all admin users
    admins = User.query.filter_by(is_admin=True).all()
    
    return render_template('admin_manage.html', admins=admins)

@app.route('/admin/add', methods=['POST'])
@login_required
def admin_add():
    # Check if the current user is an admin
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('dashboard'))
    
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    
    # Basic validation
    if not username or not email or not password:
        flash('All fields are required')
        return redirect(url_for('admin_manage'))
    
    # Check if username or email already exists
    if User.query.filter_by(username=username).first():
        flash('Username already exists')
        return redirect(url_for('admin_manage'))
    
    if User.query.filter_by(email=email).first():
        flash('Email already exists')
        return redirect(url_for('admin_manage'))
    
    # Create new admin user
    new_admin = User(username=username, email=email, is_admin=True)
    new_admin.set_password(password)
    
    db.session.add(new_admin)
    db.session.commit()
    
    flash(f'Admin user {username} added successfully')
    return redirect(url_for('admin_manage'))

@app.route('/admin/edit/<int:id>', methods=['POST'])
@login_required
def admin_edit(id):
    # Check if the current user is an admin
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('dashboard'))
    
    admin = User.query.get_or_404(id)
    
    # Don't allow editing the last admin
    if admin.id == current_user.id and User.query.filter_by(is_admin=True).count() == 1:
        flash('Cannot modify the last admin account')
        return redirect(url_for('admin_manage'))
    
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    
    # Basic validation
    if not username or not email:
        flash('Username and email are required')
        return redirect(url_for('admin_manage'))
    
    # Check if username already exists for other users
    existing_user = User.query.filter_by(username=username).first()
    if existing_user and existing_user.id != id:
        flash('Username already exists')
        return redirect(url_for('admin_manage'))
    
    # Check if email already exists for other users
    existing_email = User.query.filter_by(email=email).first()
    if existing_email and existing_email.id != id:
        flash('Email already exists')
        return redirect(url_for('admin_manage'))
    
    # Update user
    admin.username = username
    admin.email = email
    if password:
        admin.set_password(password)
    
    db.session.commit()
    
    flash(f'Admin user {username} updated successfully')
    return redirect(url_for('admin_manage'))

@app.route('/admin/delete/<int:id>', methods=['POST'])
@login_required
def admin_delete(id):
    # Check if the current user is an admin
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('dashboard'))
    
    admin = User.query.get_or_404(id)
    
    # Don't allow deleting the current user
    if admin.id == current_user.id:
        flash('Cannot delete your own account')
        return redirect(url_for('admin_manage'))
    
    db.session.delete(admin)
    db.session.commit()
    
    flash(f'Admin user {admin.username} deleted successfully')
    return redirect(url_for('admin_manage'))

@app.route('/admin/toggle/<int:id>', methods=['POST'])
@login_required
def admin_toggle(id):
    # Check if the current user is an admin
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(id)
    
    # Don't allow removing admin privileges from the last admin
    if user.is_admin and user.id == current_user.id and User.query.filter_by(is_admin=True).count() == 1:
        flash('Cannot remove admin privileges from the last admin')
        return redirect(url_for('admin_manage'))
    
    # Toggle admin status
    user.is_admin = not user.is_admin
    db.session.commit()
    
    status = "granted" if user.is_admin else "removed"
    flash(f'Admin privileges {status} for user {user.username}')
    return redirect(url_for('admin_manage'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Create admin user if it doesn't exist
        if User.query.filter_by(username='admin').first() is None:
            admin = User(username='admin', email='admin@example.com', is_admin=True)
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()

    app.run(debug=True)

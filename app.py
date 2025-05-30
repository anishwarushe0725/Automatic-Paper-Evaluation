from flask import Flask, render_template, redirect, url_for, request, flash, send_file, jsonify,send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import pandas as pd
from datetime import datetime
from config import Config
from semantic_grader.grader import SemanticGrader
import uuid
from flask_migrate import Migrate
from PIL import Image

app = Flask(__name__)
app.config.from_object(Config)
Config.init_app(app)

db = SQLAlchemy(app)
migrate = Migrate(app, db)
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
    profile_photo = db.Column(db.String(255), nullable=True)  # Path to profile photo
    is_student = db.Column(db.Boolean, default=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=True)
    
    # Change this relationship to avoid the conflict
    student = db.relationship('Student', backref='user_account', lazy=True, uselist=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
        
    def get_profile_photo_url(self):
        if self.profile_photo:
            return url_for('uploaded_file', filename=self.profile_photo)
        return url_for('static', filename='img/default-profile.png')

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    roll_number = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120))
    batch = db.Column(db.String(50))
    aadhar_id = db.Column(db.String(12), nullable=True)
    evaluations = db.relationship('Evaluation', backref='student', lazy='dynamic')
    _has_account = None  # Add this field to cache the account status
    
    @property
    def has_account(self):
        if self._has_account is None:
            from flask_sqlalchemy import SQLAlchemy
            from sqlalchemy.orm import Query
            # Check if this student has a user account
            if isinstance(self.user_account, Query):
                self._has_account = self.user_account.first() is not None
            else:
                self._has_account = self.user_account is not None
        return self._has_account
        
    @has_account.setter
    def has_account(self, value):
        self._has_account = value

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

class QuestionResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey('evaluation.id'))
    question_text = db.Column(db.Text)
    student_answer = db.Column(db.Text)
    model_answer = db.Column(db.Text)
    max_marks = db.Column(db.Float)
    marks_obtained = db.Column(db.Float)
    feedback = db.Column(db.Text)
    
    # Relationship with parent evaluation
    evaluation = db.relationship('Evaluation', backref='question_results')
    

def create_student_user(student, password):
    """Create a user account for a student"""
    # Check if student already has a user account
    if User.query.filter_by(student_id=student.id).first():
        return False, "Student already has a user account"
    
    # Create username from roll number
    username = f"student_{student.roll_number}"
    
    # Check if username exists
    if User.query.filter_by(username=username).first():
        return False, "Username already exists"
    
    # Create user
    user = User(
        username=username,
        email=student.email,
        is_student=True,
        student_id=student.id
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    return True, "Student user account created successfully"

# Configure upload folder for profile photos
PROFILE_PHOTOS_FOLDER = os.path.join(app.config['UPLOAD_FOLDER'], 'profile_photos')
os.makedirs(PROFILE_PHOTOS_FOLDER, exist_ok=True)

# Add this to your allowed_file function or create a new one
def allowed_image_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

@app.route('/search')
@login_required
def search():
    query = request.args.get('q', '')
    if not query:
        flash('Please enter a search term')
        return redirect(url_for('dashboard'))
        
    # Define search results
    results = {
        'students': [],
        'pages': []
    }
    
    # Search for students
    if not current_user.is_student:  # Only teachers/admins can search students
        students = Student.query.filter(
            db.or_(
                Student.name.ilike(f'%{query}%'),
                Student.roll_number.ilike(f'%{query}%'),
                Student.email.ilike(f'%{query}%'),
                Student.batch.ilike(f'%{query}%')
            )
        ).all()
        results['students'] = students
    
    # Search for pages (if the search query matches specific pages)
    pages = []
    
    # Check if search query matches page names
    if 'dashboard' in query.lower():
        pages.append({'name': 'Dashboard', 'url': url_for('dashboard')})
    if 'evaluation' in query.lower():
        pages.append({'name': 'Evaluation', 'url': url_for('evaluation')})
    if 'question' in query.lower() or 'paper' in query.lower():
        pages.append({'name': 'Upload Question Paper', 'url': url_for('upload_questions')})
        pages.append({'name': 'Create Question Paper', 'url': url_for('create_question_paper')})
    if 'student' in query.lower():
        pages.append({'name': 'Students', 'url': url_for('students')})
    if 'result' in query.lower():
        pages.append({'name': 'Results', 'url': url_for('results')})
    if 'admin' in query.lower() and current_user.is_admin:
        pages.append({'name': 'Admin Management', 'url': url_for('admin_manage')})
    
    results['pages'] = pages
    
    # If we have exactly one page result and no student results, redirect directly
    if len(results['pages']) == 1 and len(results['students']) == 0:
        return redirect(results['pages'][0]['url'])
    
    # If we have exactly one student result and no page results, redirect to student details
    if len(results['students']) == 1 and len(results['pages']) == 0 and not current_user.is_student:
        # Redirect to student details
        return redirect(url_for('student_details', student_id=results['students'][0].id))
        
    # Otherwise, show all results
    return render_template('search_results.html', query=query, results=results)

@app.route('/student_details/<int:student_id>')
@login_required
def student_details(student_id):
    # Only teachers/admins can view student details
    if current_user.is_student:
        flash('Access denied. Teacher/Admin privileges required.')
        return redirect(url_for('student_dashboard'))
    
    student = Student.query.get_or_404(student_id)
    
    # Get all evaluations for this student
    evaluations = Evaluation.query.filter_by(student_id=student_id).order_by(Evaluation.evaluated_at.desc()).all()
    
    # Calculate performance metrics
    total_evaluations = len(evaluations)
    avg_score = 0
    if total_evaluations > 0:
        avg_score = sum(eval.percentage for eval in evaluations) / total_evaluations
    
    return render_template(
        'student_details.html',
        student=student,
        evaluations=evaluations,
        total_evaluations=total_evaluations,
        avg_score=avg_score
    )

# Route to serve uploaded files
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Add this function to resize and save profile photos
def save_profile_photo(file):
    # Generate a unique filename to avoid overwrites
    filename = str(uuid.uuid4()) + '.' + file.filename.rsplit('.', 1)[1].lower()
    filepath = os.path.join(PROFILE_PHOTOS_FOLDER, filename)
    
    # Resize image to a standard size
    image = Image.open(file)
    image = image.resize((200, 200))
    image.save(filepath)
    
    # Return relative path from UPLOAD_FOLDER
    return os.path.join('profile_photos', filename)


@app.route('/create_question_paper', methods=['GET', 'POST'])
@login_required
def create_question_paper():
    if request.method == 'POST':
        college_name = request.form.get('college_name')
        exam_type = request.form.get('exam_type')
        course_code = request.form.get('course_code')
        course_name = request.form.get('course_name')
        exam_date = request.form.get('exam_date')
        exam_time = request.form.get('exam_time')
        maximum_marks = request.form.get('maximum_marks')
        instructions = request.form.get('instructions')
        
        # Get questions, marks, and correct answers
        questions = request.form.getlist('choice_question[]')
        marks = request.form.getlist('marks[]')
        correct_answers = request.form.getlist('correct_answer[]')
        
        # Validate data
        if not all([college_name, exam_type, course_code, course_name, exam_date, 
                   exam_time, maximum_marks, instructions]) or not questions:
            flash('All fields are required and at least one question must be added')
            return redirect(url_for('create_question_paper'))
        
        # Generate PDF for the question paper
        from pdf_generator import generate_question_paper_pdf
        
        try:
            # Create a title for the question paper
            title = f"{course_code} - {exam_type}"
            description = f"Question paper for {course_name}, {exam_date}"
            
            # Generate the PDF
            pdf_filename = f"question_paper_{course_code}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], 'question_papers', pdf_filename)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
            
            # Create question data structure
            question_data = []
            for i in range(len(questions)):
                question_data.append({
                    'question_text': questions[i],
                    'marks': float(marks[i]) if marks[i] else 0,
                    'correct_answer': correct_answers[i]
                })
            
            # Generate PDF with the question data
            generate_question_paper_pdf(
                pdf_path,
                college_name=college_name,
                exam_type=exam_type,
                course_code=course_code,
                course_name=course_name,
                exam_date=exam_date,
                exam_time=exam_time,
                maximum_marks=maximum_marks,
                instructions=instructions,
                questions=question_data
            )
            
            # Generate model answer PDF
            model_answer_filename = f"model_answer_{course_code}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
            model_answer_path = os.path.join(app.config['UPLOAD_FOLDER'], 'model_answers', model_answer_filename)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(model_answer_path), exist_ok=True)
            
            # Generate model answer PDF with the question data and answers
            generate_model_answer_pdf(
                model_answer_path,
                college_name=college_name,
                exam_type=exam_type,
                course_code=course_code,
                course_name=course_name,
                questions=question_data
            )
            
            # Create the question paper record in the database
            total_marks = sum(float(mark) for mark in marks if mark)
            
            new_paper = QuestionPaper(
                title=title,
                description=description,
                question_file_path=pdf_path,
                model_answer_path=model_answer_path,
                total_marks=total_marks,
                user_id=current_user.id
            )
            
            db.session.add(new_paper)
            db.session.commit()
            
            flash('Question paper created successfully')
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            flash(f'Error creating the question paper: {str(e)}')
            return redirect(url_for('create_question_paper'))
    
    # GET request - render the template
    return render_template('create_question_paper.html')

# Helper function to generate model answer PDF
def generate_model_answer_pdf(output_path, **kwargs):
    from pdf_generator import generate_model_answer_pdf as gen_pdf
    gen_pdf(output_path, **kwargs)

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

# Helper functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_student:
            return redirect(url_for('student_dashboard'))
        else:
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
            next_page = url_for('dashboard') if not user.is_student else url_for('student_dashboard')
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
        aadhar_id = request.form.get('aadhar_id')
        batch = request.form.get('batch')
        
        # Check if student already exists
        existing_student = Student.query.filter_by(roll_number=roll_number).first()
        if existing_student:
            flash('Student with this roll number already exists')
            return redirect(url_for('students'))
        
        new_student = Student(roll_number=roll_number, name=name, email=email, aadhar_id=aadhar_id, batch=batch)
        db.session.add(new_student)
        db.session.commit()
        
        flash('Student added successfully')
        return redirect(url_for('students'))
    
    students_list = Student.query.limit(12).all()

    return render_template('students.html', students=students_list)


@app.route('/import_students', methods=['POST'])
@login_required
def import_students():
    if 'file' not in request.files:
        return jsonify({
            'success': False,
            'message': 'No file uploaded'
        })
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({
            'success': False,
            'message': 'No file selected'
        })
    
    # Check file extension
    allowed_extensions = {'csv', 'xlsx', 'xls'}
    file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    
    if file_ext not in allowed_extensions:
        return jsonify({
            'success': False,
            'message': f'Invalid file format. Allowed formats: {", ".join(allowed_extensions)}'
        })
    
    try:
        # Process CSV file
        if file_ext == 'csv':
            df = pd.read_csv(file)
        # Process Excel files
        else:
            df = pd.read_excel(file, engine='openpyxl')
        
        # Convert all column names to lowercase and trim whitespace
        df.columns = [col.strip().lower() for col in df.columns]
        
        # Check for required columns
        required_columns = ['roll_number', 'name', 'email', 'batch']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return jsonify({
                'success': False,
                'message': 'File is missing required columns',
                'missing_columns': missing_columns,
                'found_columns': list(df.columns)
            })
        
        # Extract the required data
        students_data = df[required_columns].copy()
        
        # Add aadhar_id column if it exists
        if 'aadhar_id' in df.columns:
            students_data['aadhar_id'] = df['aadhar_id']
        else:
            # Add empty aadhar_id column if not present in file
            students_data['aadhar_id'] = None
        
        # Convert to records
        students_records = students_data.to_dict(orient='records')
        
        # Validate data
        if not students_records:
            return jsonify({
                'success': False,
                'message': 'File contains no valid student records'
            })
        
        # Add students to database
        success_count = 0
        error_count = 0
        
        for student in students_records:
            try:
                # Check if student already exists
                existing_student = Student.query.filter_by(roll_number=student['roll_number']).first()
                
                if existing_student:
                    # Update existing student
                    existing_student.name = student['name']
                    existing_student.email = student['email']
                    existing_student.batch = student['batch']
                    # Only update aadhar_id if provided
                    if 'aadhar_id' in student and student['aadhar_id']:
                        existing_student.aadhar_id = student['aadhar_id']
                else:
                    # Create new student
                    new_student = Student(
                        roll_number=student['roll_number'],
                        name=student['name'],
                        email=student['email'],
                        batch=student['batch'],
                        aadhar_id=student.get('aadhar_id')
                    )
                    db.session.add(new_student)
                
                success_count += 1
            except Exception as e:
                error_count += 1
                print(f"Error adding student {student.get('roll_number')}: {str(e)}")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Successfully imported {success_count} students. {error_count} errors.'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Import error: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error processing file: {str(e)}'
        })

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
            
            # Add individual question results
            for i in range(len(results['questions'])):
                question_result = QuestionResult(
                    evaluation_id=new_evaluation.id,
                    question_text=results['questions'][i],
                    student_answer=results['student_answers'][i] if i < len(results['student_answers']) else '',
                    model_answer=results['model_answers'][i],
                    max_marks=results['max_marks'][i],
                    marks_obtained=results['scores'][i],
                    feedback=results['feedback'][i]
                )
                db.session.add(question_result)
            
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
                
                all_results = grader.batch_grade_student_papers(temp_dir, output_folder)
                
                # Process each result
                for result in all_results:
                    # Try to match filename with student
                    student_name = os.path.splitext(result['student_file'])[0]
                    student = Student.query.filter(Student.name.ilike(f'%{student_name}%')).first()
                    
                    if student:
                        # Create evaluation record
                        new_evaluation = Evaluation(
                            student_id=student.id,
                            question_paper_id=question_paper_id,
                            answer_file_path=os.path.join(temp_dir, result['student_file']),
                            marks_obtained=result['total_score'],
                            percentage=(result['total_score'] / result['max_possible']) * 100,
                            feedback=', '.join(result['feedback']),
                            evaluated_by=current_user.id
                        )
                        
                        db.session.add(new_evaluation)
                        db.session.commit()
                        
                        # Add individual question results
                        for i in range(len(result['questions'])):
                            question_result = QuestionResult(
                                evaluation_id=new_evaluation.id,
                                question_text=result['questions'][i],
                                student_answer=result['student_answers'][i] if i < len(result['student_answers']) else '',
                                model_answer=result['model_answers'][i],
                                max_marks=result['max_marks'][i],
                                marks_obtained=result['scores'][i],
                                feedback=result['feedback'][i]
                            )
                            db.session.add(question_result)
                        
                        db.session.commit()
                
                flash('Batch evaluation completed. Check results for details.')
                return redirect(url_for('results'))
                
            except Exception as e:
                flash(f'Error in batch evaluation: {str(e)}')
                return redirect(request.url)
    
    return render_template('batch_evaluation.html', question_papers=question_papers)


@app.route('/evaluation_details/<int:evaluation_id>')
@login_required
def evaluation_details(evaluation_id):
    evaluation = Evaluation.query.get_or_404(evaluation_id)
    
    # Check if this evaluation belongs to a question paper created by the current user
    question_paper = QuestionPaper.query.get(evaluation.question_paper_id)
    if question_paper.user_id != current_user.id:
        flash('Access denied. You can only view your own evaluations.')
        return redirect(url_for('results'))
    
    # Get the student information
    student = Student.query.get(evaluation.student_id)
    
    return render_template(
        'evaluation_details.html',
        evaluation=evaluation,
        question_paper=question_paper,
        student=student
    )

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


@app.route('/admin/manage', methods=['GET'])
@login_required
def admin_manage():
    # Check if the current user is an admin
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('dashboard'))
    
    # Get all admin users
    admins = User.query.filter_by(is_admin=True).all()

    for admin in admins:
        print(f"Admin {admin.username} photo path: {admin.profile_photo}")
    
    return render_template('admin_manage.html', admins=admins,current_user=current_user)

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
    
    # Handle profile photo upload if provided
    if 'profile_photo' in request.files and request.files['profile_photo'].filename:
        photo_file = request.files['profile_photo']
        if allowed_image_file(photo_file.filename):
            photo_path = save_profile_photo(photo_file)
            new_admin.profile_photo = photo_path
        else:
            flash('Invalid image file format. Allowed formats: png, jpg, jpeg, gif')
    
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
    
    # Handle profile photo upload if provided
    if 'profile_photo' in request.files and request.files['profile_photo'].filename:
        photo_file = request.files['profile_photo']
        if allowed_image_file(photo_file.filename):
            # Remove old photo if exists
            if admin.profile_photo:
                old_photo_path = os.path.join(app.config['UPLOAD_FOLDER'], admin.profile_photo)
                if os.path.exists(old_photo_path):
                    try:
                        os.remove(old_photo_path)
                    except Exception as e:
                        print(f"Error removing old profile photo: {str(e)}")
            
            # Save new photo
            photo_path = save_profile_photo(photo_file)
            admin.profile_photo = photo_path
        else:
            flash('Invalid image file format. Allowed formats: png, jpg, jpeg, gif')
    
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
@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if current_user.is_authenticated:
        if current_user.is_student:
            return redirect(url_for('student_dashboard'))
        else:
            return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password) or not user.is_student:
            flash('Invalid username or password')
            return redirect(url_for('student_login'))
        
        login_user(user)
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('student_dashboard')
        return redirect(next_page)
    
    return render_template('student_login.html')

# Student dashboard
@app.route('/student/dashboard')
@login_required
def student_dashboard():
    if not current_user.is_student:
        flash('Access denied. Student privileges required.')
        return redirect(url_for('dashboard'))
    
    # Get the student associated with the current user
    student = Student.query.get(current_user.student_id)
    if not student:
        flash('Student record not found')
        return redirect(url_for('logout'))
    
    # Get evaluations for this student
    evaluations = Evaluation.query.filter_by(student_id=student.id).order_by(Evaluation.evaluated_at.desc()).all()
    
    return render_template('student_dashboard.html', 
                          student=student, 
                          evaluations=evaluations)

# Student view results
@app.route('/student/results')
@login_required
def student_results():
    if not current_user.is_student:
        flash('Access denied. Student privileges required.')
        return redirect(url_for('dashboard'))
    
    # Get the student associated with the current user
    student = Student.query.get(current_user.student_id)
    if not student:
        flash('Student record not found')
        return redirect(url_for('logout'))
    
    # Get evaluations for this student
    evaluations = Evaluation.query.filter_by(student_id=student.id).order_by(Evaluation.evaluated_at.desc()).all()
    
    return render_template('student_results.html', evaluations=evaluations)

# Student view specific evaluation details
@app.route('/student/evaluation_details/<int:evaluation_id>')
@login_required
def student_evaluation_details(evaluation_id):
    if not current_user.is_student:
        flash('Access denied. Student privileges required.')
        return redirect(url_for('dashboard'))
    
    # Get evaluation
    evaluation = Evaluation.query.get_or_404(evaluation_id)
    
    # Security check - make sure this evaluation belongs to the current student
    if evaluation.student_id != current_user.student_id:
        flash('Access denied. You can only view your own evaluations.')
        return redirect(url_for('student_results'))
    
    # Get the student information
    student = Student.query.get(evaluation.student_id)
    
    # Get question paper
    question_paper = QuestionPaper.query.get(evaluation.question_paper_id)
    
    return render_template(
        'student_evaluation_details.html',
        evaluation=evaluation,
        question_paper=question_paper,
        student=student
    )

# Admin route to manage student accounts
@app.route('/admin/manage_student_accounts', methods=['GET'])
@login_required
def manage_student_accounts():
    # Check if the current user is an admin
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('dashboard'))
    
    # Get all students
    students = Student.query.all()
    
    # For each student, check if they have a user account
    for student in students:
        student.has_account = User.query.filter_by(student_id=student.id).first() is not None
    
    return render_template('manage_student_accounts.html', students=students)

# Admin route to create student account
@app.route('/admin/create_student_account/<int:student_id>', methods=['POST'])
@login_required
def create_student_account(student_id):
    # Check if the current user is an admin
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('dashboard'))
    
    # Special case for student_id=0: create accounts for all students without one
    if student_id == 0:
        # Get all students without accounts
        students_without_accounts = []
        students = Student.query.all()
        for student in students:
            if not User.query.filter_by(student_id=student.id).first():
                students_without_accounts.append(student)
        
        if not students_without_accounts:
            flash('All students already have accounts')
            return redirect(url_for('manage_student_accounts'))
        
        # Create accounts for all students without one
        success_count = 0
        error_count = 0
        
        for student in students_without_accounts:
            # Generate default password
            default_password = f"student_{student.roll_number}"
            
            # Create user account
            success, _ = create_student_user(student, default_password)
            
            if success:
                success_count += 1
            else:
                error_count += 1
        
        if success_count > 0:
            flash(f'Created {success_count} student accounts successfully. Default password format: student_ROLLNUMBER')
        if error_count > 0:
            flash(f'Failed to create {error_count} student accounts.')
        
        return redirect(url_for('manage_student_accounts'))
    
    # Handle creating a single student account
    student = Student.query.get_or_404(student_id)
    
    # Generate default password (can be changed by student later)
    default_password = f"student_{student.roll_number}"
    
    # Create user account
    success, message = create_student_user(student, default_password)
    
    if success:
        flash(f'Student account created for {student.name}. Default password: {default_password}')
    else:
        flash(f'Error creating student account: {message}')
    
    return redirect(url_for('manage_student_accounts'))

# Admin route to delete student account
@app.route('/admin/delete_student_account/<int:student_id>', methods=['POST'])
@login_required
def delete_student_account(student_id):
    # Check if the current user is an admin
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('dashboard'))
    
    # Get student
    student = Student.query.get_or_404(student_id)
    
    # Get user
    user = User.query.filter_by(student_id=student.id).first()
    
    if user:
        db.session.delete(user)
        db.session.commit()
        flash(f'Student account deleted for {student.name}')
    else:
        flash(f'No account found for student {student.name}')
    
    return redirect(url_for('manage_student_accounts'))

# Add this to your routes to check user type
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_student:
            return redirect(url_for('student_dashboard'))
        else:
            return redirect(url_for('dashboard'))
    return redirect(url_for('login'))




if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Create admin user if it doesn't exist
        if User.query.filter_by(username='admin').first() is None:
            admin = User(username='admin', email='admin@example.com', is_admin=True)
            admin.set_password('admin')
            admin.profile_photo = 'static\img\default-profile.png'
            db.session.add(admin)
            db.session.commit()
        print("Database tables updated. If you need to add columns to existing tables, use Flask-Migrate instead.")

    app.run(debug=True)





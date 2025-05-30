from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER

def generate_question_paper_pdf(output_path, **kwargs):
    """
    Generate a PDF question paper
    
    Parameters:
    - output_path: path where the PDF will be saved
    - kwargs: dictionary containing all question paper details
        - college_name: name of the college
        - exam_type: type of exam (mid-term, final, etc.)
        - course_code: course code
        - course_name: course name
        - exam_date: date of exam
        - exam_time: time allocated for exam
        - maximum_marks: maximum marks for the exam
        - instructions: exam instructions
        - questions: list of dictionaries containing question details
            - question_text: text of the question
            - marks: marks for the question
    """
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    story = []
    
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Center', alignment=TA_CENTER))
    
    # Header
    story.append(Paragraph(kwargs.get('college_name', ''), styles['Center']))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(f"{kwargs.get('exam_type', '')} Examination", styles['Center']))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(f"{kwargs.get('course_code', '')} - {kwargs.get('course_name', '')}", styles['Center']))
    story.append(Spacer(1, 0.2 * inch))
    
    # Exam details
    data = [
        ['Date:', kwargs.get('exam_date', '')],
        ['Time:', kwargs.get('exam_time', '')],
        ['Maximum Marks:', kwargs.get('maximum_marks', '')]
    ]
    
    t = Table(data, colWidths=[2*inch, 4*inch])
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.2 * inch))
    
    # Instructions
    story.append(Paragraph('Instructions:', styles['Heading2']))
    story.append(Paragraph(kwargs.get('instructions', ''), styles['Normal']))
    story.append(Spacer(1, 0.2 * inch))
    
    # Questions
    questions = kwargs.get('questions', [])
    for i, q in enumerate(questions):
        story.append(Paragraph(f"Question {i+1} ({q.get('marks', 0)} marks)", styles['Heading3']))
        story.append(Paragraph(q.get('question_text', ''), styles['Normal']))
        story.append(Spacer(1, 0.2 * inch))
    
    doc.build(story)
    return output_path

def generate_model_answer_pdf(output_path, **kwargs):
    """
    Generate a PDF with model answers
    
    Parameters:
    - output_path: path where the PDF will be saved
    - kwargs: dictionary containing all question paper details
        - college_name: name of the college
        - exam_type: type of exam (mid-term, final, etc.)
        - course_code: course code
        - course_name: course name
        - questions: list of dictionaries containing question details
            - question_text: text of the question
            - marks: marks for the question
            - correct_answer: correct answer for the question
    """
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    story = []
    
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Center', alignment=TA_CENTER))
    
    # Header
    story.append(Paragraph(kwargs.get('college_name', ''), styles['Center']))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(f"{kwargs.get('exam_type', '')} - MODEL ANSWERS", styles['Center']))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(f"{kwargs.get('course_code', '')} - {kwargs.get('course_name', '')}", styles['Center']))
    story.append(Spacer(1, 0.2 * inch))
    
    # Questions and Answers
    questions = kwargs.get('questions', [])
    for i, q in enumerate(questions):
        story.append(Paragraph(f"Question {i+1} ({q.get('marks', 0)} marks)", styles['Heading3']))
        story.append(Paragraph(q.get('question_text', ''), styles['Normal']))
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(f"Answer: {q.get('correct_answer', '')}", styles['Normal']))
        story.append(Spacer(1, 0.2 * inch))
    
    doc.build(story)
    return output_path

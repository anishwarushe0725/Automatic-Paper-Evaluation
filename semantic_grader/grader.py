import os
import re
import PyPDF2
import nltk
import numpy as np
import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModel
from nltk.tokenize import sent_tokenize
from nltk.corpus import stopwords
from sklearn.metrics.pairwise import cosine_similarity

# Download necessary NLTK resources
nltk.download('punkt', quiet=True)
nltk.download('stopwords', quiet=True)

class SemanticGrader:
    def __init__(self, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        """Initialize the grader with a language model for semantic understanding."""
        self.questions = []
        self.model_answers = []
        self.max_marks = []
        self.stop_words = set(stopwords.words('english'))
        
        # Load model and tokenizer
        print("Loading language model for semantic understanding...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        print("Model loaded successfully!")
        
    def add_question(self, question, model_answer, max_marks):
        """Add a question with its model answer and maximum marks."""
        self.questions.append(question)
        self.model_answers.append(model_answer)
        self.max_marks.append(max_marks)
    
    def load_questions_from_array(self, questions_array):
        """Load questions, model answers, and max marks from an array."""
        # Clear existing questions
        self.questions = []
        self.model_answers = []
        self.max_marks = []
        
        # Add each question from the array
        for i, question_data in enumerate(questions_array):
            question_text = question_data.get("question", "")
            model_answer = question_data.get("model_answer", "")
            max_marks = question_data.get("max_marks", 0)
            
            self.add_question(question_text, model_answer, float(max_marks))
            print(f"Loaded Question {i+1}: {question_text[:50]}...")
        
        print(f"Successfully loaded {len(self.questions)} questions from array")
        return True
    
    def format_and_load_questions_from_flask(self, data):
        """Convert data from Flask form to the format expected by load_questions_from_array."""
        questions_array = []
        
        for question_item in data["questions"]:
            formatted_question = {
                "question": question_item["question"],
                "model_answer": question_item["correct_answer"],
                "max_marks": float(question_item["marks"])
            }
            questions_array.append(formatted_question)
        
        # Now load the questions using the existing method
        return self.load_questions_from_array(questions_array)
    
    def extract_text_from_pdf(self, pdf_path):
        """Extract text from a PDF file."""
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text
    
    def parse_questions_from_pdf(self, pdf_path):
        """Parse questions, model answers, and max marks from a PDF file."""
        text = self.extract_text_from_pdf(pdf_path)
        
        # Pattern to match question blocks
        pattern = r"(?:Question|Q)\s*(\d+):?\s*(.*?)(?:Model Answer|Model|Answer):?\s*(.*?)(?:Max(?:imum)?\s*Marks|Max|Marks):?\s*(\d+(?:\.\d+)?)"
        
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        
        if not matches:
            print("Warning: Could not find any questions in the specified format.")
            return False
        
        # Clear existing questions
        self.questions = []
        self.model_answers = []
        self.max_marks = []
        
        # Add each found question
        for match in matches:
            question_num, question_text, model_answer, max_marks = match
            self.add_question(question_text.strip(), model_answer.strip(), float(max_marks))
            print(f"Loaded Question {question_num}: {question_text.strip()[:50]}...")
        
        print(f"Successfully loaded {len(self.questions)} questions from {pdf_path}")
        return True
    
    def parse_student_answers(self, pdf_path):
        """Parse student answers from a PDF file."""
        text = self.extract_text_from_pdf(pdf_path)
        
        # Enhanced parsing logic with better handling of different question formats
        student_answers = []
        for i in range(len(self.questions)):
            # Try multiple pattern variants
            patterns = [
                rf"(?:Question|Q)\s*{i+1}:?\s*(.*?)(?:(?:Question|Q)\s*{i+2}|$)",
                rf"{i+1}\.\s*(.*?)(?:{i+2}\.\s*|$)",
                rf"(?:Answer|A)\s*{i+1}:?\s*(.*?)(?:(?:Answer|A)\s*{i+2}|$)"
            ]
            
            answer_found = False
            for pattern in patterns:
                match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
                if match:
                    student_answers.append(match.group(1).strip())
                    answer_found = True
                    break
            
            if not answer_found:
                student_answers.append("")
                print(f"Warning: Could not find answer for Question {i+1}")
        
        return student_answers
    
    def get_embedding(self, text):
        """Generate sentence embeddings using the transformer model."""
        # Clean and preprocess text
        text = text.replace('\n', ' ').strip()
        if not text:
            return np.zeros(384)  # Return zero vector for empty text
            
        # Tokenize and get model output
        inputs = self.tokenizer(text, padding=True, truncation=True, return_tensors="pt", max_length=512)
        with torch.no_grad():
            outputs = self.model(**inputs)
        
        # Use mean pooling to get sentence embedding
        attention_mask = inputs['attention_mask']
        token_embeddings = outputs.last_hidden_state
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
        sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
        embedding = (sum_embeddings / sum_mask).squeeze().numpy()
        
        return embedding
    
    def split_into_concepts(self, text):
        """Split an answer into individual concepts/statements."""
        # Split into sentences
        sentences = sent_tokenize(text)
        
        # Clean sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return sentences
        
    def semantic_similarity(self, text1, text2):
        """Calculate semantic similarity between two texts using embeddings."""
        embedding1 = self.get_embedding(text1)
        embedding2 = self.get_embedding(text2)
        
        # Compute cosine similarity between the embeddings
        similarity = cosine_similarity([embedding1], [embedding2])[0][0]
        return similarity
    
    def concept_matching(self, model_answer, student_answer):
        """Break down answers into concepts and check how many concepts match."""
        # Split answers into concepts (sentences)
        model_concepts = self.split_into_concepts(model_answer)
        student_concepts = self.split_into_concepts(student_answer)
        
        if not model_concepts or not student_concepts:
            return 0.0
        
        # Matrix to store similarity between each concept pair
        similarity_matrix = np.zeros((len(model_concepts), len(student_concepts)))
        
        # Compute similarity for each pair of concepts
        for i, model_concept in enumerate(model_concepts):
            for j, student_concept in enumerate(student_concepts):
                similarity_matrix[i, j] = self.semantic_similarity(model_concept, student_concept)
        
        # For each model concept, find the best matching student concept
        best_matches = np.max(similarity_matrix, axis=1)
        
        # Average of best matches gives us concept coverage
        concept_coverage = np.mean(best_matches)
        
        return concept_coverage
    
    def factual_accuracy(self, model_answer, student_answer):
        """Evaluate factual accuracy by checking for contradictions."""
        # This is a simplified approach - a more advanced system would use
        # natural language inference models to detect contradictions
        
        # Get overall semantic similarity
        similarity = self.semantic_similarity(model_answer, student_answer)
        
        # Lower similarity might indicate factual errors
        accuracy = similarity
        
        return accuracy
    
    def grade_answer(self, model_answer, student_answer, max_marks):
        """Grade a student answer based on semantic understanding of the content."""
        if not student_answer.strip():
            return 0.0
            
        # Compute overall semantic similarity
        overall_similarity = self.semantic_similarity(model_answer, student_answer)
        
        # Compute concept coverage
        concept_match = self.concept_matching(model_answer, student_answer)
        
        # Compute factual accuracy
        accuracy = self.factual_accuracy(model_answer, student_answer)
        
        # Calculate final score based on multiple metrics
        # You can adjust these weights based on importance
        score = (
            overall_similarity * 0.4 +  # Overall semantic similarity
            concept_match * 0.4 +       # Concept coverage
            accuracy * 0.2              # Factual accuracy
        ) * max_marks
        
        # Round to nearest 0.5
        score = round(score * 2) / 2
        
        # Ensure score is within bounds
        score = max(0, min(score, max_marks))
        
        print(f"Grading metrics - Similarity: {overall_similarity:.2f}, Concept Match: {concept_match:.2f}, Accuracy: {accuracy:.2f}")
        print(f"Final score: {score}/{max_marks}")
        
        return score
    
    def grade_student_paper(self, pdf_path):
        """Grade a student's entire paper."""
        print(f"Grading paper: {pdf_path}")
        
        if not self.questions:
            print("Error: No questions loaded. Please load questions first.")
            return None
        
        # Parse student answers from PDF
        student_answers = self.parse_student_answers(pdf_path)
        
        # Grade each answer
        scores = []
        detailed_feedback = []
        
        for i in range(len(self.questions)):
            print(f"\nEvaluating Question {i+1}:")
            print(f"Model answer: {self.model_answers[i]}")
            print(f"Student answer: {student_answers[i] if i < len(student_answers) else 'No answer found'}")
            
            if i < len(student_answers):
                score = self.grade_answer(self.model_answers[i], student_answers[i], self.max_marks[i])
                
                # Generate feedback
                if score >= self.max_marks[i] * 0.8:
                    feedback = "Excellent answer with comprehensive understanding."
                elif score >= self.max_marks[i] * 0.6:
                    feedback = "Good answer with most key concepts covered."
                elif score >= self.max_marks[i] * 0.4:
                    feedback = "Satisfactory answer but missing some important concepts."
                elif score >= self.max_marks[i] * 0.2:
                    feedback = "Below average answer with significant gaps in understanding."
                else:
                    feedback = "Poor answer showing minimal understanding of the topic."
                
                scores.append(score)
                detailed_feedback.append(feedback)
            else:
                scores.append(0)
                detailed_feedback.append("No answer provided")
        
        # Calculate total score
        total_score = sum(scores)
        max_possible = sum(self.max_marks)
        
        # Create a detailed report
        results = {
            'questions': self.questions,
            'model_answers': self.model_answers,
            'student_answers': student_answers,
            'max_marks': self.max_marks,
            'scores': scores,
            'feedback': detailed_feedback,
            'total_score': total_score,
            'max_possible': max_possible
        }
        
        return results
    
    def print_report(self, results):
        """Print a detailed grading report."""
        print("\n===== Grading Report =====")
        for i in range(len(results['questions'])):
            print(f"\nQuestion {i+1}: {results['questions'][i]}")
            print(f"Model Answer: {results['model_answers'][i]}")
            print(f"Student Answer: {results['student_answers'][i] if i < len(results['student_answers']) else 'No answer found'}")
            print(f"Score: {results['scores'][i]}/{results['max_marks'][i]}")
            print(f"Feedback: {results['feedback'][i]}")
        
        print(f"\nTotal Score: {results['total_score']}/{results['max_possible']}")
        print(f"Percentage: {(results['total_score']/results['max_possible']*100):.2f}%")
    
    def save_report(self, results, output_path="grading_results.csv"):
        """Save the grading results to a CSV file."""
        df = pd.DataFrame({
            'Question': results['questions'],
            'Model Answer': results['model_answers'],
            'Student Answer': results['student_answers'],
            'Maximum Marks': results['max_marks'],
            'Score': results['scores'],
            'Feedback': results['feedback']
        })
        
        df.to_csv(output_path, index=False)
        print(f"Results saved to {output_path}")
        
        # Also save a summary
        summary_df = pd.DataFrame({
            'Total Score': [results['total_score']],
            'Maximum Possible': [results['max_possible']],
            'Percentage': [(results['total_score']/results['max_possible']*100)]
        })
        
        summary_path = output_path.replace('.csv', '_summary.csv')
        summary_df.to_csv(summary_path, index=False)
        print(f"Summary saved to {summary_path}")

    def batch_grade_student_papers(self, folder_path, output_folder="grading_results"):
        """Grade multiple student papers from a folder."""
        if not os.path.exists(folder_path):
            print(f"Error: Folder '{folder_path}' not found.")
            return
            
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            print(f"Created output folder: {output_folder}")
            
        # Get all PDF files in the folder
        pdf_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.pdf')]
        
        if not pdf_files:
            print(f"No PDF files found in {folder_path}")
            return
            
        print(f"Found {len(pdf_files)} PDF files to grade.")
        
        # Grade each file
        all_results = []
        for pdf_file in pdf_files:
            print(f"\n\nProcessing {pdf_file}...")
            pdf_path = os.path.join(folder_path, pdf_file)
            
            # Grade the paper
            results = self.grade_student_paper(pdf_path)
            if results:
                results['student_file'] = pdf_file
                all_results.append(results)
                # Save individual report
                student_name = os.path.splitext(pdf_file)[0]
                output_path = os.path.join(output_folder, f"{student_name}_results.csv")
                self.save_report(results, output_path)
                
        # Create a summary report of all students
        if all_results:
            summary_data = {
                'Student': [],
                'Total Score': [],
                'Maximum Possible': [],
                'Percentage': []
            }
            
            for result in all_results:
                summary_data['Student'].append(os.path.splitext(result['student_file'])[0])
                summary_data['Total Score'].append(result['total_score'])
                summary_data['Maximum Possible'].append(result['max_possible'])
                summary_data['Percentage'].append((result['total_score']/result['max_possible']*100))
                
            # Create a summary dataframe for all students
            summary_df = pd.DataFrame(summary_data)
            
            # Sort by percentage in descending order
            summary_df = summary_df.sort_values('Percentage', ascending=False)
            
            # Save the summary
            summary_path = os.path.join(output_folder, "all_students_summary.csv")
            summary_df.to_csv(summary_path, index=False)
            print(f"\nSummary of all students saved to {summary_path}")
            
        return all_results
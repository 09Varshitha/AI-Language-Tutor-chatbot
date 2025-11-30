from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv
import json
import requests

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Gemini API Configuration
GEMINI_API_KEY = 'AIzaSyBmvGxeFJ629IpRdDwBmRiPNt6YqL1vCbg'
GEMINI_API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent'

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# Available languages dictionary
LANGUAGES = {
    'Indian Languages': [
        'Hindi', 'Tamil', 'Telugu', 'Bengali', 'Marathi', 
        'Gujarati', 'Kannada', 'Malayalam', 'Punjabi', 'Urdu'
    ],
    'International Languages': [
        'English', 'Spanish', 'French', 'German', 'Chinese', 
        'Japanese', 'Korean', 'Arabic', 'Russian', 'Portuguese'
    ]
}

# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    current_language = db.Column(db.String(50), nullable=True)
    skill_level = db.Column(db.String(20), nullable=True)

# Create all database tables
with app.app_context():
    db.drop_all()  # Drop all existing tables
    db.create_all()  # Create new tables with updated schema

# Routes
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        user = User.query.get(session['user_id'])
        if user is None:
            # If user not found, clear session and redirect to login
            session.clear()
            return redirect(url_for('login'))
            
        return render_template('chat.html', 
                             languages=LANGUAGES,
                             current_language=user.current_language if user else None,
                             current_level=user.skill_level if user else 'beginner')
    except Exception as e:
        print(f"Error in index route: {str(e)}")
        session.clear()
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            return redirect(url_for('index'))
        
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('register'))
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/set_language', methods=['POST'])
def set_language():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        language = request.form.get('language')
        level = request.form.get('level', 'beginner')
        
        if not language:
            return jsonify({'error': 'Language is required'}), 400
            
        if level not in ['beginner', 'intermediate', 'advanced']:
            level = 'beginner'
        
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        user.current_language = language
        user.skill_level = level
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Language set to {language} ({level})',
            'language': language,
            'level': level
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error in set_language: {str(e)}")
        return jsonify({'error': 'Failed to update language settings'}), 500

@app.route('/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404

        user_message = request.form.get('message', '').strip()
        if not user_message:
            return jsonify({'error': 'Message cannot be empty'}), 400

        # Create system prompt
        system_prompt = f"""You are a helpful and encouraging language tutor teaching {user.current_language or 'multiple languages'}. 
        Current skill level: {user.skill_level or 'beginner'}.
        
        Guidelines:
        1. If teaching a specific language:
           - Provide basic phrases and their pronunciation
           - Explain grammar concepts simply
           - Include cultural context
           - Use both English and the target language
        2. Keep responses clear and engaging
        3. Provide examples from daily life
        4. Encourage practice through conversation
        5. If the user hasn't selected a language, help them choose one
        """

        # Prepare the request for Gemini API
        headers = {
            'Content-Type': 'application/json',
            'x-goog-api-key': GEMINI_API_KEY
        }
        
        data = {
            "contents": [
                {
                    "parts": [
                        {"text": system_prompt},
                        {"text": user_message}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 500
            }
        }

        # Make API call to Gemini
        try:
            response = requests.post(
                GEMINI_API_URL,
                headers=headers,
                json=data
            )
            
            response.raise_for_status()  # Raise an exception for bad status codes
            
            response_data = response.json()
            
            # Extract the response text from Gemini's response
            if (response_data.get('candidates') and 
                response_data['candidates'][0].get('content') and 
                response_data['candidates'][0]['content'].get('parts')):
                bot_response = response_data['candidates'][0]['content']['parts'][0]['text'].strip()
            else:
                raise ValueError("Invalid response format from Gemini API")
                
            if not bot_response:
                raise ValueError("Empty response from Gemini API")
                
            return jsonify({'response': bot_response})
            
        except requests.exceptions.RequestException as e:
            print(f"Gemini API Request Error: {str(e)}")
            return jsonify({
                'error': 'Unable to connect to the language service. Please try again in a few moments.'
            }), 500
            
        except ValueError as e:
            print(f"Gemini API Response Error: {str(e)}")
            return jsonify({
                'error': 'Received an invalid response from the language service. Please try again.'
            }), 500
            
        except Exception as e:
            print(f"Unexpected error in Gemini API call: {str(e)}")
            return jsonify({
                'error': 'An unexpected error occurred. Please try again or contact support if the problem persists.'
            }), 500
            
    except Exception as e:
        print(f"Error in chat route: {str(e)}")
        return jsonify({
            'error': 'An error occurred while processing your request. Please try again.'
        }), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True) 
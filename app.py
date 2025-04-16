from flask import Flask, render_template, request, redirect, url_for, session, flash
import psycopg2  # Import psycopg2 for PostgreSQL connection
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or 'your_secret_key_here'

# PostgreSQL connection
def get_db_connection():
    conn = psycopg2.connect(
        dbname=os.environ.get("DB_NAME", "dbms_project"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "Aneesh@2005"),
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432")
    )
    return conn

def update_overall_score(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get the latest score for each topic for the user
    cursor.execute("""
        SELECT MAX(us.attempted_on) AS latest_attempt, us.topic_id
        FROM user_scores us
        WHERE us.user_id = %s
        GROUP BY us.topic_id
    """, (user_id,))
    latest_attempts = cursor.fetchall()

    total_score = 0

    # For each topic, get the latest score
    for row in latest_attempts:
        cursor.execute("""
            SELECT score FROM user_scores 
            WHERE user_id = %s AND topic_id = %s AND attempted_on = %s
        """, (user_id, row['topic_id'], row['latest_attempt']))
        latest_score = cursor.fetchone()
        if latest_score:
            total_score += latest_score[0]

    # Insert or update the overall_scores table
    cursor.execute("SELECT * FROM overall_scores WHERE user_id = %s", (user_id,))
    if cursor.fetchone():
        cursor.execute("""
            UPDATE overall_scores SET total_score = %s WHERE user_id = %s
        """, (total_score, user_id))
    else:
        cursor.execute("""
            INSERT INTO overall_scores (user_id, total_score) VALUES (%s, %s)
        """, (user_id, total_score))
    conn.commit()
    cursor.close()
    conn.close()

@app.route('/')
def default():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("INSERT INTO user_details (user_name, email_id, password) VALUES (%s, %s, %s)",
                           (username, email, password))
            conn.commit()
            flash('Registration successful. Please login.', 'success')
            return redirect(url_for('login'))
        except psycopg2.Error as err:
            flash(f"Error: {err}", 'danger')
            conn.rollback()
            return redirect(url_for('register'))
        finally:
            cursor.close()
            conn.close()

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password_input = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM user_details WHERE email_id = %s", (email,))
        user = cursor.fetchone()

        if not user:
            flash('User does not exist. Please register first.', 'warning')
            return redirect(url_for('register'))

        db_password = user[3]  # 'password' is the 4th column in user_details

        if db_password and check_password_hash(db_password, password_input):
            session['user_id'] = user[0]  # 'user_id' is the 1st column in user_details
            session['user_name'] = user[1]  # 'user_name' is the 2nd column in user_details
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Incorrect password. Try again.', 'danger')

        cursor.close()
        conn.close()

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch total score from overall_scores
    cursor.execute("""
        SELECT total_score FROM overall_scores WHERE user_id = %s
    """, (session['user_id'],))
    overall = cursor.fetchone()
    overall_score = overall[0] if overall else 0

    cursor.execute("SELECT * FROM topic")
    topics = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("dashboard.html",
                           username=session['user_name'],
                           overall_score=overall_score,
                           topics=topics
)

@app.route('/quiz/<int:topic_id>', methods=['GET', 'POST'])
def quiz(topic_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch topic name
    cursor.execute('SELECT topic_name FROM topic WHERE topic_id = %s', (topic_id,))
    topic = cursor.fetchone()
    if not topic:
        flash("Invalid topic selected.", "danger")
        return redirect(url_for('dashboard'))

    topic_name = topic[0]

    # Fetch questions
    cursor.execute('SELECT * FROM quiz_questions WHERE topic_id = %s', (topic_id,))
    questions = cursor.fetchall()
    if not questions:
        flash("No questions found for this topic.", "warning")
        return redirect(url_for('dashboard'))

    score = 0
    selected_answers = {}
    submitted = False
    explanations = {}

    if request.method == 'POST':
        submitted = True
        for q in questions:
            qid = str(q[0])  # 'qn_id' is the 1st column in quiz_questions
            correct_answer = q[4].split('_')[1]  # extracts '3' from 'option_3'

            selected = request.form.get(qid)
            selected_answers[int(qid)] = selected

            if selected == correct_answer:
                score += 1
            else:
                explanations[int(qid)] = q[5]  # explanation is in the 6th column

        # Store score in DB
        cursor.execute('''
            INSERT INTO user_scores (user_id, topic_id, score, attempted_on)
            VALUES (%s, %s, %s, NOW())
        ''', (session['user_id'], topic_id, score))
        conn.commit()

        # 🔥 Update overall score
        update_overall_score(session['user_id'])

    cursor.close()
    conn.close()

    return render_template('quiz.html',
        questions=questions,
        topic_name=topic_name,
        submitted=submitted,
        selected_answers=selected_answers,
        explanations=explanations,
        score=score
    )

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

if __name__ == '_main_':
    app.run(debug=True)
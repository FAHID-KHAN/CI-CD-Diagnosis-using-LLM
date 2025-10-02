# human_study.py - User study interface and evaluation tools

from flask import Flask, render_template_string, request, jsonify, session
import json
import sqlite3
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import secrets
import time
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats

@dataclass
class StudyTask:
    """Represents a single evaluation task"""
    task_id: str
    log_content: str
    log_id: str
    error_type: str
    with_assistance: bool
    actual_fix: Optional[str] = None

@dataclass
class TaskResponse:
    """Participant's response to a task"""
    participant_id: str
    task_id: str
    start_time: float
    end_time: float
    time_taken_seconds: float
    identified_error_type: str
    identified_root_cause: str
    suggested_fix: str
    confidence_rating: int  # 1-5
    difficulty_rating: int  # 1-5
    with_assistance: bool
    tool_helpfulness_rating: Optional[int] = None  # 1-5, only if with_assistance

@dataclass
class ParticipantProfile:
    """Participant demographic and experience data"""
    participant_id: str
    years_experience: int
    ci_cd_experience: str  # 'none', 'beginner', 'intermediate', 'expert'
    primary_languages: List[str]
    primary_tools: List[str]
    consent_given: bool
    timestamp: str

class StudyDatabase:
    """Manage study data storage"""
    
    def __init__(self, db_path: str = "human_study.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Participants table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                participant_id TEXT PRIMARY KEY,
                years_experience INTEGER,
                ci_cd_experience TEXT,
                primary_languages TEXT,
                primary_tools TEXT,
                consent_given BOOLEAN,
                timestamp TEXT
            )
        """)
        
        # Tasks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                log_id TEXT,
                log_content TEXT,
                error_type TEXT,
                actual_fix TEXT
            )
        """)
        
        # Responses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                response_id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_id TEXT,
                task_id TEXT,
                start_time REAL,
                end_time REAL,
                time_taken_seconds REAL,
                identified_error_type TEXT,
                identified_root_cause TEXT,
                suggested_fix TEXT,
                confidence_rating INTEGER,
                difficulty_rating INTEGER,
                with_assistance BOOLEAN,
                tool_helpfulness_rating INTEGER,
                FOREIGN KEY (participant_id) REFERENCES participants(participant_id),
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def add_participant(self, profile: ParticipantProfile):
        """Add participant profile"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO participants VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            profile.participant_id,
            profile.years_experience,
            profile.ci_cd_experience,
            json.dumps(profile.primary_languages),
            json.dumps(profile.primary_tools),
            profile.consent_given,
            profile.timestamp
        ))
        
        conn.commit()
        conn.close()
    
    def add_task(self, task: StudyTask):
        """Add study task"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR IGNORE INTO tasks VALUES (?, ?, ?, ?, ?)
        """, (
            task.task_id,
            task.log_id,
            task.log_content,
            task.error_type,
            task.actual_fix
        ))
        
        conn.commit()
        conn.close()
    
    def save_response(self, response: TaskResponse):
        """Save task response"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO responses (participant_id, task_id, start_time, end_time, 
                                 time_taken_seconds, identified_error_type, 
                                 identified_root_cause, suggested_fix, 
                                 confidence_rating, difficulty_rating, 
                                 with_assistance, tool_helpfulness_rating)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            response.participant_id,
            response.task_id,
            response.start_time,
            response.end_time,
            response.time_taken_seconds,
            response.identified_error_type,
            response.identified_root_cause,
            response.suggested_fix,
            response.confidence_rating,
            response.difficulty_rating,
            response.with_assistance,
            response.tool_helpfulness_rating
        ))
        
        conn.commit()
        conn.close()
    
    def get_all_responses(self) -> List[Dict]:
        """Get all responses for analysis"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT r.*, p.years_experience, p.ci_cd_experience, t.error_type as actual_error_type
            FROM responses r
            JOIN participants p ON r.participant_id = p.participant_id
            JOIN tasks t ON r.task_id = t.task_id
        """)
        
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(zip(columns, row)) for row in rows]

class StudyTaskGenerator:
    """Generate balanced study tasks"""
    
    @staticmethod
    def create_task_sequence(test_logs: List[Dict], 
                           num_tasks_per_participant: int = 8) -> List[StudyTask]:
        """Create balanced task sequence with/without assistance"""
        tasks = []
        
        # Select diverse logs
        selected_logs = test_logs[:num_tasks_per_participant]
        
        for i, log in enumerate(selected_logs):
            # Alternate with/without assistance
            with_assistance = (i % 2 == 0)
            
            task = StudyTask(
                task_id=f"task_{log['log_id']}_{i}",
                log_content=log['log_content'],
                log_id=log['log_id'],
                error_type=log['error_type'],
                with_assistance=with_assistance,
                actual_fix=log.get('fix_description')
            )
            tasks.append(task)
        
        return tasks

class StudyAnalyzer:
    """Analyze human study results"""
    
    def __init__(self, db: StudyDatabase):
        self.db = db
    
    def analyze_time_to_insight(self) -> Dict:
        """Analyze time taken with/without assistance"""
        responses = self.db.get_all_responses()
        df = pd.DataFrame(responses)
        
        # Split by assistance
        with_assist = df[df['with_assistance'] == 1]['time_taken_seconds']
        without_assist = df[df['with_assistance'] == 0]['time_taken_seconds']
        
        # Statistical test
        t_stat, p_value = stats.ttest_ind(without_assist, with_assist)
        
        return {
            'mean_time_without_assist': float(without_assist.mean()),
            'mean_time_with_assist': float(with_assist.mean()),
            'median_time_without_assist': float(without_assist.median()),
            'median_time_with_assist': float(with_assist.median()),
            'time_reduction_percentage': float((1 - with_assist.mean() / without_assist.mean()) * 100),
            't_statistic': float(t_stat),
            'p_value': float(p_value),
            'significant': p_value < 0.05
        }
    
    def analyze_accuracy(self) -> Dict:
        """Analyze diagnostic accuracy"""
        responses = self.db.get_all_responses()
        df = pd.DataFrame(responses)
        
        # Calculate accuracy
        df['correct'] = df['identified_error_type'] == df['actual_error_type']
        
        with_assist_acc = df[df['with_assistance'] == 1]['correct'].mean()
        without_assist_acc = df[df['with_assistance'] == 0]['correct'].mean()
        
        return {
            'accuracy_without_assist': float(without_assist_acc),
            'accuracy_with_assist': float(with_assist_acc),
            'accuracy_improvement': float((with_assist_acc - without_assist_acc) * 100)
        }
    
    def analyze_confidence(self) -> Dict:
        """Analyze participant confidence"""
        responses = self.db.get_all_responses()
        df = pd.DataFrame(responses)
        
        with_assist = df[df['with_assistance'] == 1]['confidence_rating']
        without_assist = df[df['with_assistance'] == 0]['confidence_rating']
        
        return {
            'mean_confidence_without_assist': float(without_assist.mean()),
            'mean_confidence_with_assist': float(with_assist.mean()),
            'confidence_improvement': float(with_assist.mean() - without_assist.mean())
        }
    
    def analyze_by_experience(self) -> Dict:
        """Analyze results by experience level"""
        responses = self.db.get_all_responses()
        df = pd.DataFrame(responses)
        
        experience_levels = df['ci_cd_experience'].unique()
        results = {}
        
        for level in experience_levels:
            level_df = df[df['ci_cd_experience'] == level]
            
            with_assist = level_df[level_df['with_assistance'] == 1]
            without_assist = level_df[level_df['with_assistance'] == 0]
            
            results[level] = {
                'count': len(level_df),
                'time_reduction': float((1 - with_assist['time_taken_seconds'].mean() / 
                                       without_assist['time_taken_seconds'].mean()) * 100) if len(without_assist) > 0 else 0,
                'accuracy_with_assist': float((with_assist['identified_error_type'] == 
                                             with_assist['actual_error_type']).mean()) if len(with_assist) > 0 else 0
            }
        
        return results
    
    def generate_report(self, output_path: str):
        """Generate comprehensive study report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'time_analysis': self.analyze_time_to_insight(),
            'accuracy_analysis': self.analyze_accuracy(),
            'confidence_analysis': self.analyze_confidence(),
            'experience_analysis': self.analyze_by_experience()
        }
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"Report saved to {output_path}")
        return report
    
    def plot_results(self, output_dir: str):
        """Generate visualization plots"""
        responses = self.db.get_all_responses()
        df = pd.DataFrame(responses)
        
        # Time comparison plot
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # 1. Time taken comparison
        ax1 = axes[0, 0]
        df.boxplot(column='time_taken_seconds', by='with_assistance', ax=ax1)
        ax1.set_title('Time Taken: With vs Without Assistance')
        ax1.set_xlabel('With Assistance')
        ax1.set_ylabel('Time (seconds)')
        
        # 2. Confidence ratings
        ax2 = axes[0, 1]
        df.groupby('with_assistance')['confidence_rating'].mean().plot(kind='bar', ax=ax2)
        ax2.set_title('Average Confidence Rating')
        ax2.set_xlabel('With Assistance')
        ax2.set_ylabel('Confidence (1-5)')
        ax2.set_xticklabels(['Without', 'With'], rotation=0)
        
        # 3. Difficulty ratings
        ax3 = axes[1, 0]
        df.groupby('with_assistance')['difficulty_rating'].mean().plot(kind='bar', ax=ax3)
        ax3.set_title('Average Difficulty Rating')
        ax3.set_xlabel('With Assistance')
        ax3.set_ylabel('Difficulty (1-5)')
        ax3.set_xticklabels(['Without', 'With'], rotation=0)
        
        # 4. Tool helpfulness
        ax4 = axes[1, 1]
        tool_help = df[df['with_assistance'] == 1]['tool_helpfulness_rating'].dropna()
        ax4.hist(tool_help, bins=5, range=(0.5, 5.5), alpha=0.7, edgecolor='black')
        ax4.set_title('Tool Helpfulness Rating Distribution')
        ax4.set_xlabel('Rating (1-5)')
        ax4.set_ylabel('Frequency')
        ax4.set_xticks([1, 2, 3, 4, 5])
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/study_results.png", dpi=300, bbox_inches='tight')
        print(f"Plot saved to {output_dir}/study_results.png")

# Flask web interface for conducting the study
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# HTML templates
CONSENT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>CI/CD Diagnostic Study - Consent Form</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
        .consent-box { background: #f5f5f5; padding: 20px; border-radius: 5px; margin: 20px 0; }
        button { background: #4CAF50; color: white; padding: 15px 32px; font-size: 16px; border: none; cursor: pointer; }
        button:hover { background: #45a049; }
        input[type="number"], select { padding: 10px; margin: 5px 0; width: 100%; }
        label { font-weight: bold; display: block; margin-top: 15px; }
    </style>
</head>
<body>
    <h1>CI/CD Failure Diagnosis Study</h1>
    <h2>Informed Consent</h2>
    
    <div class="consent-box">
        <h3>Study Purpose</h3>
        <p>This study evaluates the effectiveness of an AI-powered tool for diagnosing CI/CD pipeline failures.</p>
        
        <h3>Procedure</h3>
        <p>You will:</p>
        <ul>
            <li>Complete 8 diagnostic tasks (approximately 30-45 minutes)</li>
            <li>Diagnose CI/CD failures with and without tool assistance</li>
            <li>Rate your confidence and the difficulty of each task</li>
        </ul>
        
        <h3>Confidentiality</h3>
        <p>All data will be anonymized. Your responses will only be used for research purposes.</p>
        
        <h3>Voluntary Participation</h3>
        <p>You may withdraw at any time without penalty.</p>
    </div>
    
    <form method="POST" action="/consent">
        <h2>Participant Information</h2>
        
        <label>Years of Programming Experience:</label>
        <input type="number" name="years_experience" min="0" max="50" required>
        
        <label>CI/CD Experience Level:</label>
        <select name="ci_cd_experience" required>
            <option value="">Select...</option>
            <option value="none">None</option>
            <option value="beginner">Beginner (< 1 year)</option>
            <option value="intermediate">Intermediate (1-3 years)</option>
            <option value="expert">Expert (3+ years)</option>
        </select>
        
        <label>Primary Programming Languages (comma-separated):</label>
        <input type="text" name="primary_languages" placeholder="e.g., Python, JavaScript, Java" required>
        
        <label>CI/CD Tools You Use (comma-separated):</label>
        <input type="text" name="primary_tools" placeholder="e.g., GitHub Actions, Jenkins, GitLab CI" required>
        
        <br><br>
        <label>
            <input type="checkbox" name="consent" required>
            I have read and understood the study information and consent to participate
        </label>
        
        <br><br>
        <button type="submit">Begin Study</button>
    </form>
</body>
</html>
"""

TASK_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Task {{ task_num }} of {{ total_tasks }}</title>
    <style>
        body { font-family: monospace; max-width: 1200px; margin: 20px auto; padding: 20px; }
        .header { background: #333; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
        .log-container { background: #f5f5f5; padding: 20px; border: 1px solid #ddd; 
                         max-height: 400px; overflow-y: scroll; margin: 20px 0; }
        .tool-output { background: #e8f5e9; padding: 15px; border-left: 4px solid #4CAF50; margin: 20px 0; }
        textarea { width: 100%; min-height: 100px; font-family: monospace; }
        select, input[type="range"] { width: 100%; padding: 8px; margin: 5px 0; }
        button { background: #4CAF50; color: white; padding: 15px 32px; font-size: 16px; 
                border: none; cursor: pointer; margin-top: 20px; }
        label { font-weight: bold; display: block; margin-top: 15px; }
        .timer { font-size: 24px; color: #4CAF50; float: right; }
    </style>
    <script>
        var startTime = Date.now();
        function updateTimer() {
            var elapsed = Math.floor((Date.now() - startTime) / 1000);
            var minutes = Math.floor(elapsed / 60);
            var seconds = elapsed % 60;
            document.getElementById('timer').textContent = 
                String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');
        }
        setInterval(updateTimer, 1000);
        
        function submitTask() {
            document.getElementById('start_time').value = startTime;
            document.getElementById('end_time').value = Date.now();
            return true;
        }
    </script>
</head>
<body>
    <div class="header">
        <h1>Task {{ task_num }} of {{ total_tasks }}</h1>
        <div class="timer" id="timer">00:00</div>
    </div>
    
    <h2>CI/CD Build Log</h2>
    <div class="log-container">
        <pre>{{ log_content }}</pre>
    </div>
    
    {% if with_assistance %}
    <h2>Diagnostic Tool Output</h2>
    <div class="tool-output">
        <h3>Error Type: {{ tool_output.error_type }}</h3>
        <p><strong>Root Cause:</strong> {{ tool_output.root_cause }}</p>
        <p><strong>Suggested Fix:</strong> {{ tool_output.suggested_fix }}</p>
        <p><strong>Failure Lines:</strong> {{ tool_output.failure_lines }}</p>
        <p><strong>Confidence:</strong> {{ tool_output.confidence_score }}</p>
    </div>
    {% endif %}
    
    <form method="POST" action="/submit_task" onsubmit="return submitTask()">
        <input type="hidden" name="task_id" value="{{ task_id }}">
        <input type="hidden" name="with_assistance" value="{{ with_assistance }}">
        <input type="hidden" id="start_time" name="start_time">
        <input type="hidden" id="end_time" name="end_time">
        
        <h2>Your Diagnosis</h2>
        
        <label>What type of error is this?</label>
        <select name="error_type" required>
            <option value="">Select error type...</option>
            <option value="dependency_error">Dependency Error</option>
            <option value="test_failure">Test Failure</option>
            <option value="build_configuration">Build Configuration</option>
            <option value="timeout">Timeout</option>
            <option value="permission_denied">Permission Denied</option>
            <option value="syntax_error">Syntax Error</option>
            <option value="network_error">Network Error</option>
            <option value="unknown">Unknown</option>
        </select>
        
        <label>Describe the root cause:</label>
        <textarea name="root_cause" required placeholder="Explain what caused this failure..."></textarea>
        
        <label>Suggested fix:</label>
        <textarea name="suggested_fix" required placeholder="What steps would you take to fix this?"></textarea>
        
        <label>How confident are you in your diagnosis? (1 = Not confident, 5 = Very confident)</label>
        <input type="range" name="confidence" min="1" max="5" value="3" 
               oninput="this.nextElementSibling.textContent = this.value">
        <span>3</span>
        
        <label>How difficult was this task? (1 = Very easy, 5 = Very difficult)</label>
        <input type="range" name="difficulty" min="1" max="5" value="3"
               oninput="this.nextElementSibling.textContent = this.value">
        <span>3</span>
        
        {% if with_assistance %}
        <label>How helpful was the diagnostic tool? (1 = Not helpful, 5 = Very helpful)</label>
        <input type="range" name="tool_helpfulness" min="1" max="5" value="3"
               oninput="this.nextElementSibling.textContent = this.value">
        <span>3</span>
        {% endif %}
        
        <br>
        <button type="submit">Submit and Continue</button>
    </form>
</body>
</html>
"""

COMPLETION_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Study Complete</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; text-align: center; }
        .success { background: #4CAF50; color: white; padding: 30px; border-radius: 10px; }
        h1 { margin: 0; }
    </style>
</head>
<body>
    <div class="success">
        <h1>Thank You!</h1>
        <p>You have completed the study.</p>
        <p>Your participation ID: <strong>{{ participant_id }}</strong></p>
    </div>
    
    <h2>Summary</h2>
    <p>Total time: {{ total_time }} minutes</p>
    <p>Tasks completed: {{ tasks_completed }}</p>
    
    <p>Your responses will contribute to improving CI/CD diagnostic tools.</p>
</body>
</html>
"""

# Global state
db = StudyDatabase()
diagnostic_api = None  # Should be initialized with actual API

@app.route('/')
def index():
    return render_template_string(CONSENT_TEMPLATE)

@app.route('/consent', methods=['POST'])
def consent():
    # Generate participant ID
    participant_id = f"P{secrets.token_hex(4)}"
    
    # Save participant profile
    profile = ParticipantProfile(
        participant_id=participant_id,
        years_experience=int(request.form['years_experience']),
        ci_cd_experience=request.form['ci_cd_experience'],
        primary_languages=request.form['primary_languages'].split(','),
        primary_tools=request.form['primary_tools'].split(','),
        consent_given=True,
        timestamp=datetime.now().isoformat()
    )
    
    db.add_participant(profile)
    
    # Initialize session
    session['participant_id'] = participant_id
    session['current_task'] = 0
    session['start_time'] = time.time()
    
    return redirect('/task')

@app.route('/task')
def task():
    if 'participant_id' not in session:
        return redirect('/')
    
    task_num = session.get('current_task', 0)
    tasks = session.get('tasks', [])
    
    if task_num >= len(tasks):
        # Generate tasks on first access
        # In production, load actual test logs
        tasks = StudyTaskGenerator.create_task_sequence(
            test_logs=[],  # Load from database
            num_tasks_per_participant=8
        )
        session['tasks'] = [asdict(t) for t in tasks]
        task_num = 0
    
    if task_num >= len(tasks):
        return redirect('/complete')
    
    current_task = tasks[task_num]
    
    # Get tool output if with_assistance
    tool_output = None
    if current_task['with_assistance'] and diagnostic_api:
        tool_output = diagnostic_api.diagnose(current_task['log_content'])
    
    return render_template_string(
        TASK_TEMPLATE,
        task_num=task_num + 1,
        total_tasks=len(tasks),
        task_id=current_task['task_id'],
        log_content=current_task['log_content'],
        with_assistance=current_task['with_assistance'],
        tool_output=tool_output
    )

@app.route('/submit_task', methods=['POST'])
def submit_task():
    if 'participant_id' not in session:
        return redirect('/')
    
    # Save response
    response = TaskResponse(
        participant_id=session['participant_id'],
        task_id=request.form['task_id'],
        start_time=float(request.form['start_time']),
        end_time=float(request.form['end_time']),
        time_taken_seconds=(float(request.form['end_time']) - float(request.form['start_time'])) / 1000,
        identified_error_type=request.form['error_type'],
        identified_root_cause=request.form['root_cause'],
        suggested_fix=request.form['suggested_fix'],
        confidence_rating=int(request.form['confidence']),
        difficulty_rating=int(request.form['difficulty']),
        with_assistance=request.form.get('with_assistance') == 'True',
        tool_helpfulness_rating=int(request.form.get('tool_helpfulness', 0)) if request.form.get('tool_helpfulness') else None
    )
    
    db.save_response(response)
    
    # Move to next task
    session['current_task'] = session.get('current_task', 0) + 1
    
    return redirect('/task')

@app.route('/complete')
def complete():
    if 'participant_id' not in session:
        return redirect('/')
    
    total_time = (time.time() - session['start_time']) / 60  # minutes
    tasks_completed = session.get('current_task', 0)
    
    return render_template_string(
        COMPLETION_TEMPLATE,
        participant_id=session['participant_id'],
        total_time=round(total_time, 1),
        tasks_completed=tasks_completed
    )

# Command-line interface for study management
class StudyCLI:
    """Command-line interface for study management"""
    
    def __init__(self):
        self.db = StudyDatabase()
        self.analyzer = StudyAnalyzer(self.db)
    
    def start_web_server(self, port: int = 5000):
        """Start the web-based study interface"""
        print(f"Starting study web server on port {port}...")
        print(f"Participants can access the study at: http://localhost:{port}")
        app.run(host='0.0.0.0', port=port, debug=False)
    
    def show_statistics(self):
        """Show current study statistics"""
        responses = self.db.get_all_responses()
        
        print("\n=== Study Statistics ===")
        print(f"Total responses: {len(responses)}")
        
        if responses:
            df = pd.DataFrame(responses)
            print(f"Unique participants: {df['participant_id'].nunique()}")
            print(f"Average time per task: {df['time_taken_seconds'].mean():.1f} seconds")
            print(f"Responses with assistance: {df['with_assistance'].sum()}")
            print(f"Responses without assistance: {(~df['with_assistance'].astype(bool)).sum()}")
    
    def generate_report(self, output_dir: str = "./study_results"):
        """Generate analysis report and visualizations"""
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        print("Generating study report...")
        
        # Generate JSON report
        report = self.analyzer.generate_report(f"{output_dir}/report.json")
        
        # Generate visualizations
        self.analyzer.plot_results(output_dir)
        
        # Print summary
        print("\n=== Study Results Summary ===")
        print(f"\nTime Analysis:")
        print(f"  Mean time without assist: {report['time_analysis']['mean_time_without_assist']:.1f}s")
        print(f"  Mean time with assist: {report['time_analysis']['mean_time_with_assist']:.1f}s")
        print(f"  Time reduction: {report['time_analysis']['time_reduction_percentage']:.1f}%")
        print(f"  Statistically significant: {report['time_analysis']['significant']}")
        
        print(f"\nAccuracy Analysis:")
        print(f"  Accuracy without assist: {report['accuracy_analysis']['accuracy_without_assist']:.1%}")
        print(f"  Accuracy with assist: {report['accuracy_analysis']['accuracy_with_assist']:.1%}")
        print(f"  Improvement: {report['accuracy_analysis']['accuracy_improvement']:.1f}%")
        
        print(f"\nConfidence Analysis:")
        print(f"  Mean confidence without assist: {report['confidence_analysis']['mean_confidence_without_assist']:.2f}")
        print(f"  Mean confidence with assist: {report['confidence_analysis']['mean_confidence_with_assist']:.2f}")
        
        print(f"\nFull report saved to: {output_dir}/report.json")
        print(f"Visualizations saved to: {output_dir}/study_results.png")
    
    def export_data(self, output_file: str = "study_data.csv"):
        """Export all study data to CSV"""
        responses = self.db.get_all_responses()
        df = pd.DataFrame(responses)
        df.to_csv(output_file, index=False)
        print(f"Data exported to {output_file}")

# Example usage
if __name__ == "__main__":
    import sys
    
    cli = StudyCLI()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python human_study.py start [port]   - Start web server")
        print("  python human_study.py stats           - Show statistics")
        print("  python human_study.py report [dir]    - Generate report")
        print("  python human_study.py export [file]   - Export data")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "start":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
        cli.start_web_server(port)
    
    elif command == "stats":
        cli.show_statistics()
    
    elif command == "report":
        output_dir = sys.argv[2] if len(sys.argv) > 2 else "./study_results"
        cli.generate_report(output_dir)
    
    elif command == "export":
        output_file = sys.argv[2] if len(sys.argv) > 2 else "study_data.csv"
        cli.export_data(output_file)
    
    else:
        print(f"Unknown command: {command}")
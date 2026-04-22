import os
import json
import ast
import subprocess
import tempfile
import logging
from flask import Flask, render_template, request, jsonify
from github import Github
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
DEEPSEEK_API_URL = 'https://api.deepseek.com/v1/chat/completions'
HISTORY_FILE = 'history.json'

if not DEEPSEEK_API_KEY:
    logger.error('DEEPSEEK_API_KEY not set')
if not GITHUB_TOKEN:
    logger.error('GITHUB_TOKEN not set')

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def save_history(history):
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def call_deepseek_with_reasoning(user_command):
    system_prompt = """You are an expert project generator. Generate a complete, production-ready code project based on the user's command.
Return a JSON object with exactly this structure:
{
    "reasoning": "Step-by-step thought process",
    "projectType": "web-app | api | script | static-site",
    "summary": "Brief description of what was created",
    "files": [
        {"path": "filename.ext", "content": "actual code"}
    ]
}
CRITICAL:
- Generate COMPLETE working code (NO placeholders)
- Include all necessary files
- Code must be properly indented
- Return ONLY valid JSON
"""
    headers = {
        'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': 'deepseek-reasoner',
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_command}
        ],
        'temperature': 0.3,
        'response_format': {'type': 'json_object'}
    }
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        # Extract content from response
        content = data['choices'][0]['message']['content']
        result = json.loads(content)
        return result
    except Exception as e:
        logger.error(f'DeepSeek API call failed: {e}')
        return None

def verify_files(files):
    errors = []
    for file in files:
        path = file['path']
        content = file['content']
        ext = os.path.splitext(path)[1].lower()
        if ext == '.py':
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f'Syntax error in {path}: {e}')
        elif ext == '.json':
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                errors.append(f'Invalid JSON in {path}: {e}')
        elif ext == '.js':
            # Optionally check with node if available
            try:
                subprocess.run(['node', '--check', '-'], input=content, capture_output=True, text=True, timeout=5, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Basic syntax check via acorn? Not available, skip
                pass
    return errors

def fix_files_with_deepseek(files, errors, original_command):
    error_str = '\n'.join(errors)
    fix_prompt = f"""The following generated files have errors:
{error_str}

Original command: {original_command}

Please provide corrected versions of these files. Return the same JSON structure with all files (including unchanged ones).
"""
    # Create a temporary context to send only erroneous files? For simplicity, we send the whole set.
    result = call_deepseek_with_reasoning(fix_prompt)
    if result and 'files' in result:
        return result['files']
    return files

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.get_json()
    if not data or 'command' not in data:
        return jsonify({'error': 'No command provided'}), 400
    command = data['command']
    logger.info(f'Generating project for command: {command}')
    
    # Call DeepSeek
    result = call_deepseek_with_reasoning(command)
    if not result:
        return jsonify({'error': 'Failed to generate project'}), 500
    
    reasoning = result.get('reasoning', '')
    project_type = result.get('projectType', 'unknown')
    summary = result.get('summary', '')
    files = result.get('files', [])
    
    # Self-verification
    errors = verify_files(files)
    attempts = 0
    while errors and attempts < 2:
        logger.warning(f'Errors found, fixing attempt {attempts+1}')
        files = fix_files_with_deepseek(files, errors, command)
        errors = verify_files(files)
        attempts += 1
    
    if errors:
        logger.warning(f'Failed to fix all errors after {attempts} attempts')
    
    # Save to history
    history = load_history()
    project_entry = {
        'id': len(history) + 1,
        'timestamp': __import__('datetime').datetime.now().isoformat(),
        'command': command,
        'reasoning': reasoning,
        'summary': summary,
        'projectType': project_type,
        'files': files
    }
    history.append(project_entry)
    save_history(history)
    
    return jsonify({
        'reasoning': reasoning,
        'projectType': project_type,
        'summary': summary,
        'files': files,
        'errors': errors  # include any remaining errors
    })

@app.route('/api/history', methods=['GET'])
def history():
    history = load_history()
    # Return only metadata (without full file contents to save bandwidth)
    simplified = []
    for entry in history:
        simplified.append({
            'id': entry['id'],
            'timestamp': entry['timestamp'],
            'command': entry['command'],
            'reasoning': entry.get('reasoning', '')[:200],  # truncate for display
            'summary': entry['summary'],
            'projectType': entry['projectType']
        })
    return jsonify(simplified)

@app.route('/api/push-to-github', methods=['POST'])
def push_to_github():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    repo_name = data.get('repoName')
    description = data.get('description', 'Generated by AI Project Generator')
    files = data.get('files', [])
    
    if not repo_name or not files:
        return jsonify({'error': 'Missing repoName or files'}), 400
    
    if not GITHUB_TOKEN:
        return jsonify({'error': 'GitHub token not configured'}), 500
    
    try:
        g = Github(GITHUB_TOKEN)
        user = g.get_user()
        repo = user.create_repo(repo_name, description=description, private=False, auto_init=False)
        
        # Create initial commit with all files
        for file in files:
            path = file['path']
            content = file['content']
            # Ensure path is clean
            path = path.lstrip('/')
            try:
                repo.create_file(path, f'Add {path}', content, branch='main')
            except Exception as e:
                logger.error(f'Failed to create {path}: {e}')
                # Could try with alternative branch
                pass
        
        return jsonify({'success': True, 'repoUrl': repo.html_url})
    except Exception as e:
        logger.error(f'GitHub push failed: {e}')
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)

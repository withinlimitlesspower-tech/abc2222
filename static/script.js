// State
let currentFiles = [];
let currentReasoning = '';
let currentProjectType = '';
let currentSummary = '';

const historyList = document.getElementById('historyList');
const commandInput = document.getElementById('commandInput');
const generateBtn = document.getElementById('generateBtn');
const pushBtn = document.getElementById('pushBtn');
const loading = document.getElementById('loading');
const output = document.getElementById('output');
const reasoningSection = document.getElementById('reasoningSection');
const reasoningContent = document.getElementById('reasoningContent');
const toggleReasoning = document.getElementById('toggleReasoning');

// Load history on page load
loadHistory();

// Event Listeners
generateBtn.addEventListener('click', generateProject);
pushBtn.addEventListener('click', pushToGitHub);
toggleReasoning.addEventListener('click', () => {
    const hidden = reasoningContent.classList.toggle('hidden');
    toggleReasoning.textContent = hidden ? 'Show Reasoning' : 'Hide Reasoning';
});
document.getElementById('newProjectBtn').addEventListener('click', () => {
    commandInput.value = '';
    output.innerHTML = '<p class="text-gray-400">Generated project will appear here.</p>';
    reasoningSection.classList.add('hidden');
    pushBtn.disabled = true;
    currentFiles = [];
});

async function generateProject() {
    const command = commandInput.value.trim();
    if (!command) {
        alert('Please enter a command.');
        return;
    }

    // UI: show loading, disable button
    loading.classList.remove('hidden');
    generateBtn.disabled = true;
    output.innerHTML = '';
    reasoningSection.classList.add('hidden');

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command })
        });
        const data = await response.json();
        
        if (data.error) {
            output.innerHTML = `<p class="text-red-500">Error: ${data.error}</p>`;
            return;
        }

        currentFiles = data.files;
        currentReasoning = data.reasoning || '';
        currentProjectType = data.projectType;
        currentSummary = data.summary;

        // Display reasoning
        if (currentReasoning) {
            reasoningSection.classList.remove('hidden');
            reasoningContent.textContent = currentReasoning;
            toggleReasoning.textContent = 'Show Reasoning';
            reasoningContent.classList.add('hidden');
        }

        // Display files
        renderFiles(currentFiles);
        
        // Enable push button
        pushBtn.disabled = false;

        // Reload history
        loadHistory();

        // Show errors if any
        if (data.errors && data.errors.length > 0) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'mt-4 p-3 bg-red-800 rounded';
            errorDiv.innerHTML = `<p class="font-bold">Syntax Errors (some may remain):</p><ul class="list-disc pl-5">${data.errors.map(e => `<li>${e}</li>`).join('')}</ul>`;
            output.appendChild(errorDiv);
        }
    } catch (err) {
        output.innerHTML = `<p class="text-red-500">Request failed: ${err.message}</p>`;
    } finally {
        loading.classList.add('hidden');
        generateBtn.disabled = false;
    }
}

function renderFiles(files) {
    output.innerHTML = '';
    if (!files || files.length === 0) {
        output.innerHTML = '<p class="text-gray-400">No files generated.</p>';
        return;
    }

    files.forEach(file => {
        const fileDiv = document.createElement('div');
        fileDiv.className = 'mb-4 p-3 bg-gray-700 rounded';
        
        const header = document.createElement('div');
        header.className = 'flex justify-between items-center mb-2';
        const pathSpan = document.createElement('span');
        pathSpan.className = 'font-mono text-sm text-green-400';
        pathSpan.textContent = file.path;
        header.appendChild(pathSpan);
        
        const copyBtn = document.createElement('button');
        copyBtn.className = 'bg-blue-500 hover:bg-blue-600 text-white px-2 py-1 rounded text-xs';
        copyBtn.textContent = 'Copy';
        copyBtn.addEventListener('click', () => {
            navigator.clipboard.writeText(file.content).then(() => {
                copyBtn.textContent = 'Copied!';
                setTimeout(() => { copyBtn.textContent = 'Copy'; }, 2000);
            });
        });
        header.appendChild(copyBtn);
        
        fileDiv.appendChild(header);
        
        const pre = document.createElement('pre');
        pre.className = 'bg-gray-900 p-2 rounded text-xs overflow-x-auto';
        pre.textContent = file.content;
        fileDiv.appendChild(pre);
        
        output.appendChild(fileDiv);
    });
}

async function pushToGitHub() {
    if (!currentFiles.length) {
        alert('No files to push. Generate a project first.');
        return;
    }

    const repoName = prompt('Enter repository name:');
    if (!repoName) return;
    const description = prompt('Enter description (optional):', 'Generated by AI Project Generator');
    if (description === null) return;

    pushBtn.disabled = true;
    pushBtn.textContent = 'Pushing...';

    try {
        const response = await fetch('/api/push-to-github', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ repoName, description: description || '', files: currentFiles })
        });
        const data = await response.json();
        
        if (data.error) {
            alert(`Push failed: ${data.error}`);
        } else {
            alert(`Repository created: ${data.repoUrl}`);
            // Optionally open in new tab
            window.open(data.repoUrl, '_blank');
        }
    } catch (err) {
        alert(`Push request failed: ${err.message}`);
    } finally {
        pushBtn.disabled = false;
        pushBtn.textContent = 'Push to GitHub';
    }
}

async function loadHistory() {
    try {
        const response = await fetch('/api/history');
        const history = await response.json();
        
        historyList.innerHTML = '';
        if (history.length === 0) {
            historyList.innerHTML = '<p class="text-gray-500 text-sm">No history yet.</p>';
            return;
        }

        // Show latest first
        history.reverse();
        history.forEach(entry => {
            const div = document.createElement('div');
            div.className = 'p-2 bg-gray-700 rounded cursor-pointer hover:bg-gray-600';
            div.innerHTML = `
                <p class="font-bold text-sm">${escapeHtml(entry.command.substring(0, 30))}${entry.command.length > 30 ? '...' : ''}</p>
                <p class="text-xs text-gray-400">${entry.projectType} - ${new Date(entry.timestamp).toLocaleString()}</p>
            `;
            div.addEventListener('click', () => {
                // Load this project into main view? For simplicity, we just show alert with summary.
                alert(`Summary: ${entry.summary}\n\nReasoning: ${entry.reasoning}`);
            });
            historyList.appendChild(div);
        });
    } catch (err) {
        console.error('Failed to load history:', err);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

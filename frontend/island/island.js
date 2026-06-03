const ipcRenderer = window.electron.ipcRenderer;
const clipboard = window.electron.clipboard;

const island = document.getElementById('island');
const msgEl = document.getElementById('msg');
const chipsEl = document.getElementById('chips');
const copyBtn = document.getElementById('copy-btn');
const clearBtn = document.getElementById('clear-btn');
const activeMicBtn = document.getElementById('active-mic-btn');
const statusDot = document.getElementById('status-dot');

let dismissTimeout = null;

function setState(active) {
    if (active) {
        island.classList.add('active');
        ipcRenderer.send('island:set-ignore-mouse', false);
    } else {
        island.classList.remove('active');
        ipcRenderer.send('island:set-ignore-mouse', true);
    }
}

function showProactive(payload) {
    const { message, suggestions } = payload;
    
    // Clear previous
    msgEl.innerText = message;
    chipsEl.innerHTML = '';
    
    // Add chips
    if (suggestions && suggestions.length > 0) {
        suggestions.forEach(text => {
            const chip = document.createElement('div');
            chip.className = 'chip';
            chip.innerText = text;
            chip.onclick = () => {
                ipcRenderer.send('friday:reply', text);
                retract();
            };
            chipsEl.appendChild(chip);
        });
    }

    setState(true);

    // Auto-dismiss after 8 seconds of no interaction if it was a proactive trigger
    resetTimeout(8000);
}

function retract() {
    setState(false);
    if (dismissTimeout) clearTimeout(dismissTimeout);
}

function resetTimeout(ms) {
    if (dismissTimeout) clearTimeout(dismissTimeout);
    dismissTimeout = setTimeout(() => {
        retract();
    }, ms);
}

copyBtn.onclick = () => {
    clipboard.writeText(msgEl.innerText);
    copyBtn.innerText = 'copied!';
    copyBtn.classList.add('success');
    
    setTimeout(() => {
        copyBtn.innerText = 'copy';
        copyBtn.classList.remove('success');
        retract();
    }, 1200);
};

if (clearBtn) {
    clearBtn.onclick = () => {
        ipcRenderer.send('friday:clear-clipboard');
        clearBtn.innerText = 'cleared!';
        setTimeout(() => {
            clearBtn.innerText = 'clear';
            retract();
        }, 1200);
    };
}

// Listen for PRIMNOX's proactive alerts
ipcRenderer.on('friday:proactive', (payload) => {
    showProactive(payload);
});

// Allow manual expansion for testing
island.onclick = (e) => {
    if (!island.classList.contains('active')) {
        // Only expand on click if we want to show history or status
        // For now, let's keep it proactive-only per requirements
    }
};

let micMuted = false;

function updateMicUI(muted) {
    micMuted = muted;
    const micIconEl = document.getElementById('idle-mic-icon');
    
    const micSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#00f0ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-mic"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>`;
    const micOffSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#ff003c" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-mic-off"><line x1="2" x2="22" y1="2" y2="22"/><path d="M18.89 13.23A7.12 7.12 0 0 0 19 12v-2"/><path d="M5 10v2a7 7 0 0 0 12 5.79"/><path d="M15 9.34V5a3 3 0 0 0-5.68-1.33"/><path d="M9 9v3a3 3 0 0 0 5.12 2.12"/><line x1="12" x2="12" y1="19" y2="22"/></svg>`;
    
    if (micIconEl) {
        micIconEl.innerHTML = muted ? micOffSvg : micSvg;
    }
    
    if (activeMicBtn) {
        activeMicBtn.innerText = muted ? 'unmute mic' : 'mute mic';
        if (muted) {
            activeMicBtn.style.color = '#ff003c';
            activeMicBtn.style.borderColor = 'rgba(255, 0, 60, 0.4)';
        } else {
            activeMicBtn.style.color = '#00f0ff';
            activeMicBtn.style.borderColor = 'rgba(0, 240, 255, 0.3)';
        }
    }
}

const notesBtn = document.getElementById('notes-btn');
if (notesBtn) {
    notesBtn.onclick = () => {
        ipcRenderer.send('friday:open-notes');
    };
}

if (activeMicBtn) {
    activeMicBtn.onclick = () => {
        ipcRenderer.send('friday:mic-toggle');
    };
}

ipcRenderer.on('friday:mic-state', (payload) => {
    updateMicUI(payload.muted);
});

ipcRenderer.on('friday:state', (payload) => {
    const val = payload.value;
    if (statusDot) {
        statusDot.style.animation = 'none';
        if (val === 'listening') {
            statusDot.style.background = '#ff003c';
            statusDot.style.boxShadow = '0 0 10px #ff003c';
            statusDot.style.animation = 'pulse 1s infinite alternate';
        } else if (val === 'thinking') {
            statusDot.style.background = '#00f0ff';
            statusDot.style.boxShadow = '0 0 10px #00f0ff';
            statusDot.style.animation = 'pulse 1s infinite alternate';
        } else {
            statusDot.style.background = '#00ff88';
            statusDot.style.boxShadow = '0 0 10px #00ff88';
        }
    }
});

// Add keyframe animation for status dot pulsing dynamically if not present
if (!document.getElementById('pulse-style')) {
    const style = document.createElement('style');
    style.id = 'pulse-style';
    style.innerHTML = `
        @keyframes pulse {
            0% { transform: scale(1); opacity: 0.6; }
            100% { transform: scale(1.3); opacity: 1; }
        }
    `;
    document.head.appendChild(style);
}

// Initial state: ignore mouse events
ipcRenderer.send('island:set-ignore-mouse', true);

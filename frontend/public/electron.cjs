const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, screen, globalShortcut, clipboard } = require('electron');
const path = require('path');
const { spawn, execSync } = require('child_process');
const { autoUpdater } = require('electron-updater');
const fs = require('fs');
const http = require('http');


// ── Load .env (GH_TOKEN for private-release auto-updater) ────────────────────
try {
  const envPath = app.isPackaged
    ? path.join(process.resourcesPath, '.env')
    : path.join(app.getAppPath(), '.env');
  require('dotenv').config({ path: envPath });
} catch (_) {}

// ── Single instance lock ──────────────────────────────────────────────────────
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
  process.exit(0);
}

// ── Updater logging ───────────────────────────────────────────────────────────
const logFilePath = path.join(app.getPath('userData'), 'updater.log');
function logUpdater(message) {
  const ts = new Date().toISOString();
  const line = `[${ts}] ${message}\n`;
  try { fs.appendFileSync(logFilePath, line, 'utf8'); } catch (_) {}
  console.log(line.trim());
}
autoUpdater.logger = {
  info:  (m) => logUpdater(`INFO: ${m}`),
  warn:  (m) => logUpdater(`WARN: ${m}`),
  error: (m) => logUpdater(`ERROR: ${m}`)
};
if (process.env.GH_TOKEN) {
  autoUpdater.requestHeaders = { Authorization: 'Bearer ' + process.env.GH_TOKEN };
}
app.commandLine.appendSwitch('disable-http-cache');

// ── State ─────────────────────────────────────────────────────────────────────
let mainWindow   = null;
let islandWindow = null;   // small always-on-top overlay
let tray         = null;
let pythonProcess = null;
let forceQuit     = false; // true only when quitting via tray menu
let isIslandMode  = false;
let islandEnabled = true;   // #13 Dynamic-Island toggle; renderer pushes the real value from settings

// ── Smart Paste (global shortcut helper) ─────────────────────────────────────

function fetchSmartPaste(content) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ content });
    const req = http.request(
      {
        hostname: '127.0.0.1',
        port: 8000,
        path: '/api/smart_paste',
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(body),
        },
      },
      (res) => {
        let raw = '';
        res.on('data', (chunk) => { raw += chunk; });
        res.on('end', () => {
          try { resolve(JSON.parse(raw)); }
          catch { resolve({ transformed: content }); }
        });
      }
    );
    req.setTimeout(10000, () => { req.destroy(); reject(new Error('timeout')); });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

let pasteInFlight = false;  // prevent concurrent requests racing on the clipboard

function runSmartPaste() {
  if (pasteInFlight) return;
  const content = clipboard.readText();
  if (!content.trim()) return;

  pasteInFlight = true;

  const notify = (payload) => {
    const target = (isIslandMode && islandWindow && !islandWindow.isDestroyed())
      ? islandWindow : (mainWindow && !mainWindow.isDestroyed() ? mainWindow : null);
    if (target) target.webContents.send('smart-paste-result', payload);
  };

  fetchSmartPaste(content)
    .then(({ transformed }) => {
      const result = transformed && transformed.trim() ? transformed : null;
      if (result && result !== content) {
        clipboard.writeText(result);
        notify({ ok: true, changed: true });
      } else {
        // Content already optimal — not a failure, just nothing to transform
        notify({ ok: true, changed: false });
      }
    })
    .catch(() => notify({ ok: false }))
    .finally(() => { pasteInFlight = false; });
}

// ── Island overlay window ─────────────────────────────────────────────────────
// This is a SEPARATE 900×220 window that loads the same React app with
// ?primnox_island=1 — the React app detects that param and renders ONLY the
// DynamicIsland pill. Body background is overridden to transparent before
// React even mounts, so no black box.

function getBaseUrl() {
  if (!app.isPackaged) {
    return process.env.ELECTRON_START_URL || 'http://localhost:5173';
  }
  return null; // prod: use loadFile
}

let islandReady = false; // true once the island window's React app has fully loaded

function createIslandWindow() {
  if (islandWindow && !islandWindow.isDestroyed()) return;
  islandReady = false;

  const { width } = screen.getPrimaryDisplay().workAreaSize;

  islandWindow = new BrowserWindow({
    width: 900,
    height: 220,
    x: Math.floor(width / 2 - 450),
    y: 0,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    movable: false,
    focusable: false,  // never steal focus from the user's active app
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  // Transparent areas of the island window must not swallow clicks.
  // Default: pass all mouse events through. The renderer sends
  // 'island:set-ignore-mouse' false/true when the pill is hovered/left.
  islandWindow.setIgnoreMouseEvents(true, { forward: true });

  // Never destroy — just hide
  islandWindow.on('close', (e) => {
    if (!forceQuit) {
      e.preventDefault();
      islandWindow.hide();
    }
  });

  islandWindow.webContents.once('did-finish-load', () => { islandReady = true; });

  islandWindow.webContents.on('console-message', (_ev, _lvl, msg, line, src) => {
    console.log(`[Island] ${msg} (${src}:${line})`);
  });

  const baseUrl = getBaseUrl();
  if (baseUrl) {
    // Dev: append query param
    islandWindow.loadURL(baseUrl + '?primnox_island=1');
  } else {
    // Prod: loadFile supports a query object
    islandWindow.loadFile(path.join(__dirname, '../dist/index.html'), {
      query: { primnox_island: '1' }
    });
  }

  islandWindow.hide(); // starts hidden; shown when enterIslandMode() fires
}

// ── Main window ───────────────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: false,
    show: false,
    skipTaskbar: false,  // shows in taskbar while the full window is open
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  // Native close (Alt+F4, taskbar right-click → Close)
  mainWindow.on('close', (e) => {
    if (!forceQuit) {
      e.preventDefault();
      if (islandEnabled) {
        enterIslandMode();           // fold to island pill
      } else {
        mainWindow.setSkipTaskbar(true);
        mainWindow.hide();           // hide to tray, off taskbar
      }
    }
  });

  // Native minimize (taskbar click, Win+Down, Alt+Space → Minimize).
  // 'minimize' fires after the OS has already minimized; calling enterIslandMode
  // immediately removes it from the taskbar and shows the island pill instead.
  mainWindow.on('minimize', () => {
    if (islandEnabled) {
      enterIslandMode();
    }
    // Island OFF: standard minimize — window stays in taskbar, no action needed.
  });

  mainWindow.webContents.on('console-message', (_ev, _lvl, msg, line, src) => {
    console.log(`[Browser] ${msg} (${src}:${line})`);
  });

  const revealWindow = () => {
    if (mainWindow && !mainWindow.isDestroyed() && !mainWindow.isVisible()) {
      mainWindow.show();
      mainWindow.focus();
    }
  };

  mainWindow.once('ready-to-show', revealWindow);

  // Safety net: if 'ready-to-show' never fires (e.g. the page failed to load),
  // reveal the window anyway so the app is never left permanently invisible.
  const revealFallback = setTimeout(revealWindow, 10000);
  mainWindow.once('ready-to-show', () => clearTimeout(revealFallback));

  mainWindow.webContents.on('did-fail-load', (_ev, code, desc, url, isMainFrame) => {
    console.error(`Main window failed to load: ${code} ${desc} ${url || ''}`);
    if (code === -3) return;        // ERR_ABORTED — normal during redirects/reloads
    if (isMainFrame === false) return; // only act on the top-level frame
    // Make sure the user sees something actionable instead of a blank/hidden window.
    revealWindow();
    mainWindow.webContents.loadURL(
      'data:text/html,' + encodeURIComponent(
        '<body style="background:#000;color:#aaa;font-family:monospace;display:flex;'
        + 'align-items:center;justify-content:center;height:100vh;margin:0;text-align:center">'
        + '<div><h2 style="color:#fff">Primnox failed to load</h2>'
        + '<p>' + desc + ' (' + code + ')</p>'
        + '<p style="color:#666">The backend or dev server may still be starting — '
        + 'close and reopen the app.</p></div></body>'
      )
    );
  });

  const baseUrl = getBaseUrl();
  if (baseUrl) {
    mainWindow.loadURL(baseUrl);
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  // Ctrl+= / Ctrl+- zoom
  mainWindow.webContents.on('before-input-event', (_ev, input) => {
    if (input.control && input.type === 'keyDown') {
      const zl = mainWindow.webContents.getZoomLevel();
      if (input.key === '=' || input.key === '+') { mainWindow.webContents.setZoomLevel(zl + 0.5); _ev.preventDefault(); }
      else if (input.key === '-') { mainWindow.webContents.setZoomLevel(zl - 0.5); _ev.preventDefault(); }
      else if (input.key === '0') { mainWindow.webContents.setZoomLevel(0); _ev.preventDefault(); }
    }
  });
}

// ── Mode helpers ──────────────────────────────────────────────────────────────

function enterIslandMode() {
  if (!mainWindow) return;
  // Dynamic Island disabled in settings → behave like a normal minimize instead.
  if (!islandEnabled) { mainWindow.minimize(); return; }
  isIslandMode = true;

  // Remove from taskbar before hiding — island pill is the UI, not a taskbar entry
  mainWindow.setSkipTaskbar(true);

  // Ensure island window exists and is in the right position
  createIslandWindow();
  const { width } = screen.getPrimaryDisplay().workAreaSize;
  if (islandWindow && !islandWindow.isDestroyed()) {
    islandWindow.setPosition(Math.floor(width / 2 - 450), 0);
    if (islandReady) {
      islandWindow.showInactive();
    } else {
      // React hasn't finished loading yet — show once it's ready
      islandWindow.webContents.once('did-finish-load', () => {
        if (isIslandMode && islandWindow && !islandWindow.isDestroyed()) {
          islandWindow.setPosition(Math.floor(width / 2 - 450), 0);
          islandWindow.showInactive();
        }
      });
    }
  }

  mainWindow.hide();
}

function exitIslandMode() {
  if (!mainWindow) return;
  isIslandMode = false;

  if (islandWindow && !islandWindow.isDestroyed()) {
    // Reset click-through state before hiding so the next show starts clean
    islandWindow.setIgnoreMouseEvents(true, { forward: true });
    islandWindow.hide();
  }

  // Re-add to taskbar now that the full window is visible
  mainWindow.setSkipTaskbar(false);
  mainWindow.show();
  mainWindow.focus();
}

// ── System tray ───────────────────────────────────────────────────────────────

async function createTray() {
  let icon;
  try {
    icon = await app.getFileIcon(app.getPath('exe'), { size: 'small' });
  } catch (_) {
    icon = nativeImage.createEmpty();
  }

  tray = new Tray(icon);
  tray.setToolTip('Primnox — running in background');

  function buildMenu() {
    return Menu.buildFromTemplate([
      { label: 'Open Primnox',                       click: () => exitIslandMode() },
      { label: isIslandMode ? 'Exit Island Mode' : 'Island Mode',
        click: () => isIslandMode ? exitIslandMode() : enterIslandMode() },
      { type: 'separator' },
      { label: 'Quit Primnox',
        click: () => { forceQuit = true; app.quit(); } }
    ]);
  }

  // Left-click: show full window
  tray.on('click', () => {
    if (!mainWindow) return;
    if (!mainWindow.isVisible() || isIslandMode) exitIslandMode();
    else mainWindow.focus();
  });

  // Right-click: fresh menu so label reflects state
  tray.on('right-click', () => {
    tray.setContextMenu(buildMenu());
    tray.popUpContextMenu();
  });

  tray.setContextMenu(buildMenu());
}

// ── IPC handlers ──────────────────────────────────────────────────────────────

ipcMain.on('minimize-app', () => {
  if (!isIslandMode) enterIslandMode();
});

ipcMain.on('maximize-app', () => {
  if (!mainWindow) return;
  if (isIslandMode) { exitIslandMode(); return; }
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  else mainWindow.maximize();
});

// Custom close button in the React UI
ipcMain.on('close-app', () => {
  if (islandEnabled) {
    // Island ON: fold to island pill — same as minimize
    enterIslandMode();
  } else {
    // Island OFF: hide everything to tray, remove from taskbar
    if (mainWindow) {
      mainWindow.setSkipTaskbar(true);
      mainWindow.hide();
    }
    if (islandWindow && !islandWindow.isDestroyed()) {
      islandWindow.setIgnoreMouseEvents(true, { forward: true });
      islandWindow.hide();
    }
    isIslandMode = false;
  }
});

// Island pill logo / expand button → restore full window
ipcMain.on('show-full-window', () => exitIslandMode());

// Run Smart Paste from the renderer (Dynamic Island) via the NATIVE clipboard.
// navigator.clipboard.readText() rejects in the focusable:false island window,
// so the in-app path must delegate to the same handler the global shortcut uses.
ipcMain.on('run-smart-paste', () => runSmartPaste());

// Dynamic Island on/off — the renderer pushes the setting value (#13).
ipcMain.on('island:set-enabled', (_ev, enabled) => { islandEnabled = !!enabled; });

// Forward proactive alerts from main window to the island overlay
ipcMain.on('friday:proactive', (_ev, data) => {
  if (islandWindow && !islandWindow.isDestroyed() && isIslandMode) {
    islandWindow.webContents.send('friday:proactive', data);
  }
});

// Toggle click-through on the island overlay window.
// Renderer sends false (capture) when cursor enters the pill,
// true (pass-through) when it leaves.
ipcMain.on('island:set-ignore-mouse', (_ev, ignore) => {
  if (islandWindow && !islandWindow.isDestroyed()) {
    if (ignore) {
      islandWindow.setIgnoreMouseEvents(true, { forward: true });
    } else {
      islandWindow.setIgnoreMouseEvents(false);
    }
  }
});

// Legacy compat
ipcMain.on('set-window-mode', (_ev, mode) => {
  if (mode === 'island') enterIslandMode(); else exitIslandMode();
});

ipcMain.on('restart-app', () => autoUpdater.quitAndInstall());

// ── App lifecycle ─────────────────────────────────────────────────────────────

app.on('second-instance', () => {
  if (mainWindow) {
    if (!mainWindow.isVisible() || isIslandMode) exitIslandMode();
    else mainWindow.focus();
  }
});

app.whenReady().then(async () => {
  startBackend();
  createWindow();
  // Pre-create the island window so it's fully loaded by the time the user
  // clicks minimize. Without this, the first minimize would show a blank window
  // for ~500ms while the React app loads.
  createIslandWindow();
  await createTray();

  // ── Global keyboard shortcut: Smart Paste ────────────────────────────────
  // Works even when Primnox is in island mode (focusable:false) or the user
  // is in a different app entirely — global shortcuts fire regardless of focus.
  globalShortcut.register('CommandOrControl+Shift+P', runSmartPaste);

  autoUpdater.on('checking-for-update',  ()    => logUpdater('Checking for update...'));
  autoUpdater.on('update-not-available', ()    => logUpdater('No update.'));
  autoUpdater.on('error',               (err)  => logUpdater(`Updater error: ${err.stack || err}`));
  autoUpdater.on('download-progress',   (p)    => logUpdater(`Download: ${Math.round(p.percent)}%`));
  autoUpdater.on('update-available', (info) => {
    logUpdater(`Update available: ${JSON.stringify(info)}`);
    if (mainWindow) mainWindow.webContents.send('update-available');
  });
  autoUpdater.on('update-downloaded', (info) => {
    logUpdater(`Update downloaded: ${JSON.stringify(info)}`);
    if (mainWindow) mainWindow.webContents.send('update-downloaded');
  });

  logUpdater('Calling checkForUpdatesAndNotify()...');
  autoUpdater.checkForUpdatesAndNotify();

  app.on('activate', () => {
    if (!mainWindow || !mainWindow.isVisible()) exitIslandMode();
    else mainWindow.focus();
  });
});

// Don't quit when all windows close — lives in the tray
app.on('window-all-closed', () => { /* intentional no-op */ });

app.on('quit', () => {
  globalShortcut.unregisterAll();
  // On Windows, pythonProcess.kill() only signals the direct child; the
  // PyInstaller backend can leave grandchildren behind. taskkill /T kills the
  // whole tree so nothing is left squatting on port 8000 for the next launch.
  if (pythonProcess && pythonProcess.pid) {
    try {
      if (process.platform === 'win32') {
        execSync(`taskkill /PID ${pythonProcess.pid} /T /F`, { stdio: 'ignore' });
      } else {
        pythonProcess.kill();
      }
    } catch (_) { try { pythonProcess.kill(); } catch (_) {} }
  }
  if (tray) tray.destroy();
  if (islandWindow && !islandWindow.isDestroyed()) islandWindow.destroy();
});

// ── Backend ────────────────────────────────────────────────────────────────────

// Kill any orphaned backend still holding port 8000 from a previous run.
// The single-instance lock guards the Electron process, but if the app was
// force-killed (Task Manager, crash, OS shutdown), its backend child survives,
// keeps port 8000 + the logfile, and the next launch's backend can't bind —
// which looks to the user like "Primnox won't connect to the backend".
function freeBackendPort(port = 8000) {
  try {
    if (process.platform === 'win32') {
      const out = execSync('netstat -ano -p tcp', { encoding: 'utf8' });
      const pids = new Set();
      for (const line of out.split(/\r?\n/)) {
        if (line.includes(`:${port}`) && line.includes('LISTENING')) {
          const pid = line.trim().split(/\s+/).pop();
          if (/^\d+$/.test(pid) && pid !== '0') pids.add(pid);
        }
      }
      for (const pid of pids) {
        try { execSync(`taskkill /PID ${pid} /T /F`, { stdio: 'ignore' }); } catch (_) {}
      }
      if (pids.size) console.log(`Freed port ${port} (killed orphan backend PID ${[...pids].join(', ')})`);
    } else {
      execSync(`lsof -ti tcp:${port} | xargs -r kill -9`, { stdio: 'ignore', shell: '/bin/sh' });
    }
  } catch (_) { /* nothing listening — fine */ }
}

function startBackend() {
  freeBackendPort(8000);
  const isDev = !app.isPackaged;
  if (isDev) {
    const backendPath = path.join(__dirname, '../../backend/server.py');
    pythonProcess = spawn('python', [backendPath], {
      cwd: path.join(__dirname, '../../backend')
    });
  } else {
    const exeName = process.platform === 'win32' ? 'primnox_backend.exe' : 'primnox_backend';
    const backendPath = path.join(process.resourcesPath, 'primnox_backend', exeName);
    pythonProcess = spawn(backendPath, [], {
      cwd: path.join(process.resourcesPath, 'primnox_backend'),
      windowsHide: process.platform === 'win32'
    });
  }
  pythonProcess.stdout.on('data', (d) => console.log(`Backend: ${d}`));
  pythonProcess.stderr.on('data', (d) => console.error(`Backend err: ${d}`));
  pythonProcess.on('error', (err) => console.error('Backend spawn error:', err));
  pythonProcess.on('exit', (code) => { if (code) console.error('Backend exited with code:', code); });
}

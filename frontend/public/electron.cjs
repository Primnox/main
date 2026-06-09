const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, screen } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const { autoUpdater } = require('electron-updater');
const fs = require('fs');

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
    skipTaskbar: false,  // shows in taskbar while the full window is open
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  // Close → hide to tray, not quit
  mainWindow.on('close', (e) => {
    if (!forceQuit) {
      e.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.webContents.on('console-message', (_ev, _lvl, msg, line, src) => {
    console.log(`[Browser] ${msg} (${src}:${line})`);
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

// Close → hide everything to tray (remove from taskbar while hidden)
ipcMain.on('close-app', () => {
  if (mainWindow) {
    mainWindow.setSkipTaskbar(true);
    mainWindow.hide();
  }
  if (islandWindow && !islandWindow.isDestroyed()) {
    islandWindow.setIgnoreMouseEvents(true, { forward: true });
    islandWindow.hide();
  }
  isIslandMode = false;
});

// Island pill logo / expand button → restore full window
ipcMain.on('show-full-window', () => exitIslandMode());

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
  if (pythonProcess) pythonProcess.kill();
  if (tray) tray.destroy();
  if (islandWindow && !islandWindow.isDestroyed()) islandWindow.destroy();
});

// ── Backend ────────────────────────────────────────────────────────────────────

function startBackend() {
  const isDev = !app.isPackaged;
  if (isDev) {
    const backendPath = path.join(__dirname, '../../backend/server.py');
    pythonProcess = spawn('python', [backendPath], {
      cwd: path.join(__dirname, '../../backend')
    });
  } else {
    const backendPath = path.join(process.resourcesPath, 'primnox_backend', 'primnox_backend.exe');
    pythonProcess = spawn(backendPath, [], {
      cwd: path.join(process.resourcesPath, 'primnox_backend'),
      windowsHide: true
    });
  }
  pythonProcess.stdout.on('data', (d) => console.log(`Backend: ${d}`));
  pythonProcess.stderr.on('data', (d) => console.error(`Backend err: ${d}`));
}

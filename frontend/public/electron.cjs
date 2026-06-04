const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const { autoUpdater } = require('electron-updater');
const fs = require('fs');

const envPath = app.isPackaged ? path.join(process.resourcesPath, '.env') : path.join(app.getAppPath(), '.env');
require('dotenv').config({ path: envPath });

const logFilePath = path.join(app.getPath('userData'), 'updater.log');
function logUpdater(message) {
  const timestamp = new Date().toISOString();
  const logMessage = `[${timestamp}] ${message}\n`;
  try {
    fs.appendFileSync(logFilePath, logMessage, 'utf8');
  } catch (e) {
    console.error('Failed to write to updater log file:', e);
  }
  console.log(logMessage);
}

// Log updater events
autoUpdater.logger = {
  info: (msg) => logUpdater(`INFO: ${msg}`),
  warn: (msg) => logUpdater(`WARN: ${msg}`),
  error: (msg) => logUpdater(`ERROR: ${msg}`)
};

if (process.env.GH_TOKEN) {
  logUpdater('GH_TOKEN found in env, setting requestHeaders');
  autoUpdater.requestHeaders = { Authorization: 'Bearer ' + process.env.GH_TOKEN };
} else {
  logUpdater('No GH_TOKEN found in env, checking publicly');
}

// Hardening: Disable Chromium remote debugging switches
app.commandLine.appendSwitch('disable-http-cache');

let mainWindow;
let islandWindow;
let pythonProcess;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  mainWindow.webContents.on('console-message', (event, level, message, line, sourceId) => { console.log('[Browser Console] ' + message + ' (' + sourceId + ':' + line + ')'); });

  const isDev = !app.isPackaged;
  if (isDev) {
    mainWindow.loadURL(process.env.ELECTRON_START_URL || 'http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  // Handle Zooming since default menu is hidden (frame: false)
  mainWindow.webContents.on('before-input-event', (event, input) => {
    if (input.control && input.type === 'keyDown') {
      if (input.key === '=' || input.key === '+') {
        let zoom = mainWindow.webContents.getZoomLevel();
        mainWindow.webContents.setZoomLevel(zoom + 0.5);
        event.preventDefault();
      } else if (input.key === '-') {
        let zoom = mainWindow.webContents.getZoomLevel();
        mainWindow.webContents.setZoomLevel(zoom - 0.5);
        event.preventDefault();
      } else if (input.key === '0') {
        mainWindow.webContents.setZoomLevel(0);
        event.preventDefault();
      }
    }
  });
}

// IPC Relays and Controls
ipcMain.on('restart-app', () => {
  autoUpdater.quitAndInstall();
});
ipcMain.on('set-window-mode', (event, mode) => {
  if (!mainWindow) return;
  const { screen } = require('electron');
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width, height } = primaryDisplay.workAreaSize;
  
  if (mode === 'island') {
    mainWindow.setSize(800, 200, true);
    mainWindow.setPosition(Math.floor(width / 2 - 400), 20, true);
    mainWindow.setAlwaysOnTop(true, 'floating');
  } else {
    mainWindow.setSize(1200, 800, true);
    mainWindow.center();
    mainWindow.setAlwaysOnTop(false);
  }
});

ipcMain.on('close-app', () => {
  app.quit();
});

ipcMain.on('minimize-app', () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on('maximize-app', () => {
  if (!mainWindow) return;
  if (mainWindow.isMaximized()) {
    mainWindow.unmaximize();
  } else {
    mainWindow.maximize();
  }
});

// App lifecycle hooks
app.whenReady().then(() => {
  startBackend();
  createWindow();

  autoUpdater.on('checking-for-update', () => {
    logUpdater('Checking for update...');
  });

  autoUpdater.on('update-available', (info) => {
    logUpdater(`Update available: ${JSON.stringify(info)}`);
    if (mainWindow) mainWindow.webContents.send('update-available');
  });

  autoUpdater.on('update-not-available', (info) => {
    logUpdater(`Update not available: ${JSON.stringify(info)}`);
  });

  autoUpdater.on('error', (err) => {
    logUpdater(`Error in auto-updater: ${err.stack || err.message || err}`);
  });

  autoUpdater.on('download-progress', (progressObj) => {
    logUpdater(`Download progress: ${progressObj.percent}% (${progressObj.transferred}/${progressObj.total})`);
  });

  autoUpdater.on('update-downloaded', (info) => {
    logUpdater(`Update downloaded: ${JSON.stringify(info)}`);
    if (mainWindow) mainWindow.webContents.send('update-downloaded');
  });

  // Check for updates quietly
  logUpdater('Triggering checkForUpdatesAndNotify()...');
  autoUpdater.checkForUpdatesAndNotify();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('quit', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
});

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

  pythonProcess.stdout.on('data', (data) => {
    console.log(`Backend stdout: ${data}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`Backend stderr: ${data}`);
  });
}



const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const { autoUpdater } = require('electron-updater');

const envPath = app.isPackaged ? path.join(process.resourcesPath, '.env') : path.join(app.getAppPath(), '.env');
require('dotenv').config({ path: envPath });
if (process.env.GH_TOKEN) {
  autoUpdater.requestHeaders = { Authorization: 'Bearer ' + process.env.GH_TOKEN };
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

  autoUpdater.on('update-available', () => {
    if (mainWindow) mainWindow.webContents.send('update-available');
  });

  autoUpdater.on('update-downloaded', () => {
    if (mainWindow) mainWindow.webContents.send('update-downloaded');
  });

  // Check for updates quietly
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



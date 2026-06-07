const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electron', {
  ipcRenderer: {
    send: (channel, data) => {
      const validChannels = [
        // Window controls
        'minimize-app', 'maximize-app', 'close-app', 'restart-app',
        // Island / tray
        'show-full-window',
        // Legacy
        'set-window-mode',
        // App IPC
        'friday:proactive', 'friday:reply', 'friday:clear-clipboard',
        'friday:mic-state', 'friday:state',
        'island:set-ignore-mouse',
        'window-minimize', 'window-maximize', 'window-close',
      ];
      if (validChannels.includes(channel)) {
        ipcRenderer.send(channel, data);
      }
    },
    on: (channel, func) => {
      const validChannels = [
        // Island mode toggle sent from main process
        'primnox:island-mode',
        // Existing channels
        'friday:proactive', 'friday:open-notes',
        'friday:mic-state', 'friday:state',
        'morph-island', 'render-token-binary',
        'update-available', 'update-downloaded',
      ];
      if (validChannels.includes(channel)) {
        const subscription = (_event, ...args) => func(...args);
        ipcRenderer.on(channel, subscription);
        return () => ipcRenderer.removeListener(channel, subscription);
      }
      return () => {}; // no-op cleanup for unrecognised channels
    }
  }
});

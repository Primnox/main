const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electron', {
  ipcRenderer: {
    send: (channel, data) => {
      // Whitelist channels to prevent arbitrary IPC sending
      const validChannels = ['set-window-mode', 'friday:proactive', 'friday:reply', 'friday:clear-clipboard', 'island:set-ignore-mouse', 'friday:mic-state', 'friday:state', 'window-minimize', 'window-maximize', 'window-close', 'minimize-app', 'maximize-app', 'close-app', 'restart-app'];
      if (validChannels.includes(channel)) {
        ipcRenderer.send(channel, data);
      }
    },
    on: (channel, func) => {
      const validChannels = ['friday:proactive', 'morph-island', 'render-token-binary', 'friday:open-notes', 'update-available', 'update-downloaded'];
      if (validChannels.includes(channel)) {
        // Strip event object to prevent exposing full event structure
        const subscription = (event, ...args) => func(...args);
        ipcRenderer.on(channel, subscription);
        return () => ipcRenderer.removeListener(channel, subscription);
      }
    }
  }
});

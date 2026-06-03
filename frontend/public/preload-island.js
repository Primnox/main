const { contextBridge, ipcRenderer, clipboard } = require('electron');

contextBridge.exposeInMainWorld('electron', {
  ipcRenderer: {
    send: (channel, data) => {
      const validChannels = ['island:set-ignore-mouse', 'friday:reply', 'friday:clear-clipboard', 'friday:mic-toggle', 'friday:open-notes'];
      if (validChannels.includes(channel)) {
        ipcRenderer.send(channel, data);
      }
    },
    on: (channel, func) => {
      const validChannels = ['friday:proactive', 'morph-island', 'friday:mic-state', 'friday:state'];
      if (validChannels.includes(channel)) {
        const subscription = (event, ...args) => func(...args);
        ipcRenderer.on(channel, subscription);
        return () => ipcRenderer.removeListener(channel, subscription);
      }
    }
  },
  clipboard: {
    writeText: (text) => clipboard.writeText(text)
  }
});

const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('clipperx',{desktop:true,apiBase:'http://127.0.0.1:8787',minimize:()=>ipcRenderer.send('window:minimize'),maximize:()=>ipcRenderer.send('window:maximize'),close:()=>ipcRenderer.send('window:close')});

import { contextBridge, ipcRenderer } from 'electron'

const desktop = {
  getSettings: () => ipcRenderer.invoke('settings:get'),
  setEndpoint: (url: string) => ipcRenderer.invoke('settings:setEndpoint', url),
  setToken: (token: string) => ipcRenderer.invoke('settings:setToken', token),
  request: (request: { method?: string; path: string; body?: unknown }) =>
    ipcRenderer.invoke('api:request', request),
  chooseImage: () => ipcRenderer.invoke('files:chooseImage'),
  uploadReference: (assetId: string, role: string, filePath: string) =>
    ipcRenderer.invoke('files:uploadReference', assetId, role, filePath),
  saveResult: (path: string, filename: string) =>
    ipcRenderer.invoke('files:saveResult', path, filename),
}

contextBridge.exposeInMainWorld('directorDesktop', desktop)

import { app, BrowserWindow, dialog, ipcMain } from 'electron'
import { join } from 'node:path'
import { writeFile } from 'node:fs/promises'
import { apiRequest, downloadBinary, uploadReference, type ApiRequest } from './api-proxy'
import { currentToken, hasToken, saveEndpoint, saveToken, settings } from './config'

let window: BrowserWindow | null = null
const authorizedImages = new Set<string>()

function createWindow(): void {
  window = new BrowserWindow({
    title: 'AI Director Studio', width: 1440, height: 920, minWidth: 1040, minHeight: 640,
    show: false, backgroundColor: '#101826',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true, sandbox: true, nodeIntegration: false,
      webSecurity: true,
    },
  })
  window.once('ready-to-show', () => window?.show())
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  window.webContents.on('will-navigate', (event) => event.preventDefault())
  if (process.env.ELECTRON_RENDERER_URL) {
    void window.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    void window.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

function registerIpc(): void {
  ipcMain.handle('settings:get', () => ({ ...settings(), tokenConfigured: hasToken() }))
  ipcMain.handle('settings:setEndpoint', (_event, url: string) => saveEndpoint(url))
  ipcMain.handle('settings:setToken', (_event, token: string) => { saveToken(token); return { configured: !!currentToken() } })
  ipcMain.handle('api:request', (_event, request: ApiRequest) => apiRequest(request))
  ipcMain.handle('files:chooseImage', async () => {
    const selected = await dialog.showOpenDialog({
      properties: ['openFile'], filters: [{ name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'webp'] }],
    })
    if (selected.canceled || !selected.filePaths[0]) return null
    const path = selected.filePaths[0]
    authorizedImages.add(path)
    return path
  })
  ipcMain.handle('files:uploadReference', (_event, assetId: string, role: string, filePath: string) => {
    if (!authorizedImages.has(filePath)) throw new Error('请选择需要上传的本地图片')
    return uploadReference(assetId, role, filePath)
  })
  ipcMain.handle('files:saveResult', async (_event, path: string, filename: string) => {
    if (!/^\/api\/v1\/generation-jobs\/[0-9a-f-]{36}\/files\/\d+$/.test(path)) {
      throw new Error('非法结果路径')
    }
    const selection = await dialog.showSaveDialog({ defaultPath: filename })
    if (selection.canceled || !selection.filePath) return false
    await writeFile(selection.filePath, await downloadBinary(path))
    return true
  })
}

app.whenReady().then(() => { registerIpc(); createWindow() })
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
app.on('activate', () => { if (!BrowserWindow.getAllWindows().length) createWindow() })

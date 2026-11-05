import { app, safeStorage } from 'electron'
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'
import desktopDefaults from './defaults.json'

export interface DesktopSettings {
  apiBaseUrl: string
  timeoutMs: number
}

const defaults: DesktopSettings = desktopDefaults
let volatileToken = ''

function configFile(name: string): string {
  return join(app.getPath('userData'), name)
}

export function settings(): DesktopSettings {
  try {
    const stored = JSON.parse(readFileSync(configFile('settings.json'), 'utf8')) as Partial<DesktopSettings>
    const apiBaseUrl = stored.apiBaseUrl ? validateEndpoint(stored.apiBaseUrl) : defaults.apiBaseUrl
    const timeoutMs = typeof stored.timeoutMs === 'number' &&
      stored.timeoutMs >= 1000 && stored.timeoutMs <= 600000
      ? stored.timeoutMs : defaults.timeoutMs
    return { apiBaseUrl, timeoutMs }
  } catch {
    return { ...defaults }
  }
}

function validateEndpoint(endpoint: string): string {
  const url = new URL(endpoint)
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('API 地址只能填写协议、主机和端口，不包含路径或账户')
  }
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
  if (url.protocol !== 'https:' && !(local && url.protocol === 'http:')) {
    throw new Error('非本机 API 必须通过 HTTPS 连接')
  }
  return url.origin
}

export function saveEndpoint(apiBaseUrl: string): DesktopSettings {
  const value = { ...settings(), apiBaseUrl: validateEndpoint(apiBaseUrl) }
  mkdirSync(app.getPath('userData'), { recursive: true })
  writeFileSync(configFile('settings.json'), JSON.stringify(value, null, 2), { mode: 0o600 })
  return value
}

export function saveToken(token: string): void {
  volatileToken = token
  if (safeStorage.isEncryptionAvailable()) {
    writeFileSync(configFile('token.bin'), safeStorage.encryptString(token), { mode: 0o600 })
  }
}

export function currentToken(): string {
  if (volatileToken) return volatileToken
  const path = configFile('token.bin')
  if (!safeStorage.isEncryptionAvailable() || !existsSync(path)) return ''
  try {
    return safeStorage.decryptString(readFileSync(path))
  } catch {
    return ''
  }
}

export function hasToken(): boolean {
  return currentToken().length > 0
}

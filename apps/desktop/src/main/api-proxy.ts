import { readFile } from 'node:fs/promises'
import { extname, basename } from 'node:path'
import { settings, currentToken } from './config'

export type ApiMethod = 'GET' | 'POST' | 'PATCH' | 'DELETE'

export interface ApiRequest {
  method?: ApiMethod
  path: string
  body?: unknown
}

function apiUrl(path: string): string {
  if (!path.startsWith('/api/v1/') || path.includes('..') || path.includes('\\') || path.includes('://')) {
    throw new Error('只允许访问版本化的 FastAPI 业务接口')
  }
  const base = settings().apiBaseUrl
  if (!base) throw new Error('请先在设置中配置真实 FastAPI 地址')
  return `${base}${path}`
}

function apiHeaders(): Headers {
  const headers = new Headers()
  if (currentToken()) headers.set('X-API-Token', currentToken())
  return headers
}

async function execute(url: string, init: RequestInit = {}): Promise<Response> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), settings().timeoutMs)
  try {
    const response = await fetch(url, { ...init, signal: controller.signal })
    if (!response.ok) {
      const message = await response.text()
      let detail = message
      try {
        const parsed = JSON.parse(message) as { detail?: unknown }
        detail = typeof parsed.detail === 'string' ? parsed.detail : JSON.stringify(parsed.detail ?? parsed)
      } catch { /* keep original response */ }
      throw new Error(`HTTP ${response.status}: ${detail.slice(0, 1200)}`)
    }
    return response
  } finally {
    clearTimeout(timeout)
  }
}

export async function apiRequest(request: ApiRequest): Promise<unknown> {
  const headers = apiHeaders()
  const method = request.method ?? 'GET'
  if (!['GET', 'POST', 'PATCH', 'DELETE'].includes(method)) throw new Error('非法请求方法')
  const body = request.body === undefined ? undefined : JSON.stringify(request.body)
  if (body !== undefined) headers.set('Content-Type', 'application/json')
  const response = await execute(apiUrl(request.path), { method, headers, body })
  return response.json()
}

export async function uploadReference(
  assetId: string, role: string, filePath: string
): Promise<unknown> {
  if (!/^[a-z0-9-]{36}$/i.test(assetId)) throw new Error('非法资产 ID')
  if (!['identity', 'pose', 'costume', 'composition', 'environment', 'prop', 'first_frame'].includes(role)) {
    throw new Error('非法参考图用途')
  }
  const ext = extname(filePath).toLowerCase()
  if (!['.png', '.jpg', '.jpeg', '.webp'].includes(ext)) throw new Error('仅支持常见图片格式')
  const bytes = await readFile(filePath)
  if (bytes.length > 12 * 1024 * 1024) throw new Error('图片大小超过 12MB')
  const contentType = ext === '.png' ? 'image/png' : ext === '.webp' ? 'image/webp' : 'image/jpeg'
  const form = new FormData()
  form.append('file', new Blob([new Uint8Array(bytes)], { type: contentType }), basename(filePath))
  const response = await execute(
    apiUrl(`/api/v1/assets/${assetId}/references?role=${role}`),
    { method: 'POST', headers: apiHeaders(), body: form },
  )
  return response.json()
}

export async function downloadBinary(path: string): Promise<Buffer> {
  const response = await execute(apiUrl(path), { headers: apiHeaders() })
  return Buffer.from(await response.arrayBuffer())
}

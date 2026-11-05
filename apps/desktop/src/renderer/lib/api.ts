export interface DesktopSettings {
  apiBaseUrl: string
  timeoutMs: number
  tokenConfigured: boolean
}

export interface DesktopBridge {
  getSettings(): Promise<DesktopSettings>
  setEndpoint(url: string): Promise<DesktopSettings>
  setToken(token: string): Promise<{ configured: boolean }>
  request(request: { method?: string; path: string; body?: unknown }): Promise<unknown>
  chooseImage(): Promise<string | null>
  uploadReference(assetId: string, role: string, filePath: string): Promise<unknown>
  saveResult(path: string, filename: string): Promise<boolean>
}

declare global {
  interface Window { directorDesktop: DesktopBridge }
}

export const client = {
  get<T>(path: string): Promise<T> {
    return window.directorDesktop.request({ path }) as Promise<T>
  },
  post<T>(path: string, body: unknown = {}): Promise<T> {
    return window.directorDesktop.request({ path, method: 'POST', body }) as Promise<T>
  },
  patch<T>(path: string, body: unknown): Promise<T> {
    return window.directorDesktop.request({ path, method: 'PATCH', body }) as Promise<T>
  },
}

export const api = (path: string) => `/api/v1${path}`

export type Project = { id: string; title: string; style_guide: string }
export type Script = { id: string; project_id: string; version: number; text: string }
export type Candidate = {
  id: string; run_id: string; kind: string; name: string; description: string;
  status: string; quote: string; facts: string[]
}
export type Asset = {
  id: string; name: string; kind: string; description: string; locked_fields: Record<string, string>;
  facts: string[]; revision: number; status: string
}
export type Reference = { id: string; role: string; approved: boolean; original_filename: string }
export type Shot = {
  id: string; ordinal: number; script_id: string; narrative: string; duration_seconds: number;
  camera: Record<string, string>; constraints: unknown[]; asset_ids: string[];
  reference_ids: string[]; revision: number; transition: string
}
export type Prompt = {
  id: string; purpose: string; raw_prompt: string; compiled_prompt: string;
  version: number; approved: boolean; manifest: Array<{slot: number; asset_name: string; role: string}>
}
export type Job = {
  id: string; shot_id: string; workflow_id: string; node_id: string; status: string;
  error: string; result_files: Array<{index: number; filename: string}>
}

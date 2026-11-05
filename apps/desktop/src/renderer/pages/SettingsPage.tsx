import { useEffect, useState } from 'react'
import { Cloud, KeyRound, ShieldCheck } from 'lucide-react'
import { api, client } from '../lib/api'

type Props = { report: (error: unknown) => void; onConnected: () => Promise<void> }

export default function SettingsPage({ report, onConnected }: Props) {
  const [url, setUrl] = useState('')
  const [token, setToken] = useState('')
  const [saved, setSaved] = useState(false)
  const [status, setStatus] = useState('未测试')
  const [configured, setConfigured] = useState(false)

  useEffect(() => {
    window.directorDesktop.getSettings().then(settings => {
      setUrl(settings.apiBaseUrl); setConfigured(settings.tokenConfigured)
    }).catch(report)
  }, [])

  async function save() {
    try {
      await window.directorDesktop.setEndpoint(url)
      if (token) {
        await window.directorDesktop.setToken(token)
        setConfigured(true)
        setToken('')
      }
      setSaved(true)
      await onConnected()
    } catch (error) { report(error) }
  }

  async function test() {
    try {
      const data = await client.get<{status: string}>(api('/health'))
      setStatus(data.status === 'ok' ? '连接成功' : '服务未就绪')
    } catch (error) { report(error); setStatus('连接失败') }
  }

  return <div className="page narrow">
    <div className="page-title"><div><span className="eyebrow">05 / CONNECTION SETTINGS</span>
      <h1>连接设置</h1><p>桌面端只需要配置 FastAPI 地址；Qwen 密钥与 GPU 节点均由云端服务配置。</p></div></div>
    <section className="panel">
      <h2><Cloud size={18}/>FastAPI 云端服务</h2>
      <label>服务器地址（HTTPS）<input value={url} onChange={e => { setUrl(e.target.value); setSaved(false) }}
        placeholder="https://api.example.com"/></label>
      <p className="muted">只填写服务根地址；桌面端自动使用 /api/v1/ 接口。仅 localhost 允许使用 HTTP。</p>
      <label><KeyRound size={14}/>访问令牌<input type="password" value={token} placeholder={configured ? '已配置；留空保持不变' : '填写服务器 APP_API_TOKEN'}
        onChange={e => setToken(e.target.value)} autoComplete="off"/></label>
      <p className="muted">令牌由 Electron 主进程保管；系统加密功能可用时保存为加密文件，不暴露给 React。</p>
      <div className="row-actions"><button className="primary" onClick={save}>保存连接配置</button>
        <button onClick={test}>测试连接</button></div>
      <div className="info-line"><strong>连接测试</strong><span>{status}</span></div>
      {saved && <p className="success-text">设置已保存。新请求将连接新的云端服务。</p>}
    </section>
    <section className="panel subtle">
      <h2><ShieldCheck size={18}/>三端部署原则</h2>
      <div className="info-line"><strong>Electron</strong><span>用户电脑，负责界面和本地文件交互</span></div>
      <div className="info-line"><strong>FastAPI</strong><span>云端，负责业务、权限、Qwen 和任务管理</span></div>
      <div className="info-line"><strong>ComfyUI</strong><span>独立 GPU 服务器，由 FastAPI 后端访问</span></div>
    </section>
  </div>
}

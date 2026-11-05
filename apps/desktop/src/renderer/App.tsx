import { useCallback, useEffect, useState } from 'react'
import { Clapperboard, FolderOpen, Images, Layers3, Server, WandSparkles, RefreshCw } from 'lucide-react'
import { api, client, type Project, type Script } from './lib/api'
import ProjectsPage from './pages/ProjectsPage'
import AssetsPage from './pages/AssetsPage'
import StoryboardsPage from './pages/StoryboardsPage'
import JobsPage from './pages/JobsPage'
import SettingsPage from './pages/SettingsPage'

type Tab = 'scripts' | 'assets' | 'shots' | 'jobs' | 'settings'

const navigation = [
  { id: 'scripts', label: '剧本与项目', icon: FolderOpen },
  { id: 'assets', label: '人物 · 场景 · 道具', icon: Images },
  { id: 'shots', label: '智能分镜', icon: Layers3 },
  { id: 'jobs', label: '视频生成', icon: Clapperboard },
  { id: 'settings', label: '连接设置', icon: Server },
] as const

export default function App() {
  const [tab, setTab] = useState<Tab>('scripts')
  const [projects, setProjects] = useState<Project[]>([])
  const [scripts, setScripts] = useState<Script[]>([])
  const [projectId, setProjectId] = useState('')
  const [scriptId, setScriptId] = useState('')
  const [message, setMessage] = useState('')
  const [online, setOnline] = useState(false)
  const [busy, setBusy] = useState(false)

  const report = useCallback((error: unknown) => {
    setMessage(error instanceof Error ? error.message : String(error))
  }, [])

  const refreshProjects = useCallback(async () => {
    try {
      const found = await client.get<Project[]>(api('/projects'))
      setProjects(found)
      setProjectId(current => found.some(p => p.id === current) ? current : (found[0]?.id ?? ''))
      setOnline(true)
    } catch (error) {
      setOnline(false)
      report(error)
    }
  }, [report])

  const refreshScripts = useCallback(async () => {
    if (!projectId) {
      setScripts([])
      setScriptId('')
      return
    }
    try {
      const rows = await client.get<Script[]>(api(`/projects/${projectId}/scripts`))
      setScripts(rows)
      setScriptId(current => rows.some(s => s.id === current) ? current : (rows[0]?.id ?? ''))
    } catch (error) { report(error) }
  }, [projectId, report])

  useEffect(() => { void refreshProjects() }, [refreshProjects])
  useEffect(() => { void refreshScripts() }, [refreshScripts])

  async function execute<T>(action: () => Promise<T>): Promise<T | undefined> {
    setMessage('')
    setBusy(true)
    try { return await action() }
    catch (error) { report(error); return undefined }
    finally { setBusy(false) }
  }

  const project = projects.find(p => p.id === projectId)
  const script = scripts.find(s => s.id === scriptId)
  const shared = { projectId, scriptId, execute, report, busy }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-icon"><WandSparkles size={23} /></div>
          <div><strong>AI Director</strong><small>STORY STUDIO / V1.1</small></div>
        </div>
        <div className="nav-caption">创作工作台</div>
        <nav>
          {navigation.map(item => <button key={item.id}
            className={`nav-button ${tab === item.id ? 'active' : ''}`}
            onClick={() => setTab(item.id as Tab)}>
            <item.icon size={18} /><span>{item.label}</span>
          </button>)}
        </nav>
        <div className="sidebar-foot">
          <div className={`indicator ${online ? 'online' : ''}`} />
          <div><strong>{online ? 'FastAPI 已连接' : '服务未连接'}</strong>
            <small>{online ? '业务处理运行在云端' : '请配置 API 地址与令牌'}</small></div>
        </div>
      </aside>
      <main className="content">
        <header className="topbar">
          <div className="header-left">
            <span className="eyebrow">PROJECT WORKSPACE</span>
            <div className="toolbar-row">
              <select value={projectId} onChange={e => setProjectId(e.target.value)} aria-label="选择项目">
                <option value="">选择剧本项目</option>
                {projects.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
              </select>
              <select value={scriptId} onChange={e => setScriptId(e.target.value)} aria-label="选择剧本版本" disabled={!projectId}>
                <option value="">选择剧本</option>
                {scripts.map(item => <option key={item.id} value={item.id}>剧本 V{item.version}</option>)}
              </select>
            </div>
          </div>
          <button className="icon-button" title="刷新云端项目" onClick={() => { void refreshProjects(); void refreshScripts() }}>
            <RefreshCw size={17}/>
          </button>
        </header>
        {message && <div className="notice" role="alert"><span>{message}</span><button onClick={() => setMessage('')}>关闭</button></div>}
        <section className="workspace">
          {tab === 'scripts' && <ProjectsPage {...shared} project={project} script={script}
            onProjectsChange={refreshProjects} onScriptsChange={refreshScripts} onScriptCreated={setScriptId} />}
          {tab === 'assets' && <AssetsPage {...shared} />}
          {tab === 'shots' && <StoryboardsPage {...shared} />}
          {tab === 'jobs' && <JobsPage {...shared} />}
          {tab === 'settings' && <SettingsPage report={report} onConnected={refreshProjects} />}
        </section>
      </main>
    </div>
  )
}

export type SharedProps = {
  projectId: string
  scriptId: string
  execute: <T>(action: () => Promise<T>) => Promise<T | undefined>
  report: (error: unknown) => void
  busy: boolean
}

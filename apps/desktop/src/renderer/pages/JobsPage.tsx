import { useEffect, useState } from 'react'
import { Download, Play, RefreshCw } from 'lucide-react'
import { api, client, type Job, type Prompt, type Shot } from '../lib/api'
import type { SharedProps } from '../App'

type Workflow = { id: string; name: string; ready: boolean; max_images: number }
type Node = { id: string; name: string; enabled: boolean; models: string[] }

export default function JobsPage({ projectId, execute, report, busy }: SharedProps) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [shots, setShots] = useState<Shot[]>([])
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [nodes, setNodes] = useState<Node[]>([])
  const [shotId, setShotId] = useState('')
  const [promptId, setPromptId] = useState('')
  const [workflowId, setWorkflowId] = useState('minimax_h3')
  const [nodeId, setNodeId] = useState('')
  const [seed, setSeed] = useState('')

  async function refreshJobs() {
    if (!projectId) return
    try { setJobs(await client.get(api(`/projects/${projectId}/generation-jobs`))) }
    catch (error) { report(error) }
  }

  useEffect(() => {
    if (!projectId) { setJobs([]); setShots([]); return }
    Promise.all([
      client.get<Shot[]>(api(`/projects/${projectId}/shots`)),
      client.get<Workflow[]>(api('/workflows')),
      client.get<Node[]>(api('/gpu-nodes')),
    ]).then(([s, w, n]) => {
      setShots(s); setWorkflows(w); setNodes(n)
      setShotId(old => s.some(x => x.id === old) ? old : (s[0]?.id ?? ''))
    }).catch(report)
    void refreshJobs()
    const timer = setInterval(() => { void refreshJobs() }, 5000)
    return () => clearInterval(timer)
  }, [projectId])

  useEffect(() => {
    if (!shotId) { setPrompts([]); setPromptId(''); return }
    client.get<Prompt[]>(api(`/prompts?owner_kind=shot&owner_id=${shotId}`))
      .then(all => {
        const approved = all.filter(p => p.purpose === 'shot_video' && p.approved)
        setPrompts(approved); setPromptId(approved[0]?.id ?? '')
      }).catch(report)
  }, [shotId])

  async function submit() {
    await execute(async () => {
      await client.post(api('/generation-jobs'), {
        shot_id: shotId, prompt_version_id: promptId, workflow_id: workflowId,
        node_id: nodeId || null, seed: seed === '' ? null : Number(seed),
      })
      await refreshJobs()
    })
  }

  async function retry(id: string) {
    await execute(async () => {
      await client.post(api(`/generation-jobs/${id}/retry`))
      await refreshJobs()
    })
  }

  return <div className="page">
    <div className="page-title"><div><span className="eyebrow">04 / GPU GENERATION</span>
      <h1>视频生成与任务追踪</h1><p>FastAPI 统一提交 ComfyUI 工作流；关掉 Electron 后，云端 Worker 仍可处理任务。</p></div></div>
    {!projectId ? <div className="empty">请选择项目。</div> : <>
      <section className="panel">
        <h2><Play size={18}/>创建视频任务</h2>
        <div className="form-grid">
          <label>选择分镜<select value={shotId} onChange={e => setShotId(e.target.value)}>
            {shots.map(x => <option key={x.id} value={x.id}>{x.ordinal}. {x.narrative}</option>)}
          </select></label>
          <label>已审核视频提示词<select value={promptId} onChange={e => setPromptId(e.target.value)}>
            <option value="">请选择审核通过的提示词</option>
            {prompts.map(p => <option key={p.id} value={p.id}>版本 {p.version}</option>)}
          </select></label>
          <label>工作流<select value={workflowId} onChange={e => setWorkflowId(e.target.value)}>
            {workflows.map(w => <option key={w.id} value={w.id}>{w.name} {w.ready ? '' : '（未导入API JSON）'}</option>)}
          </select></label>
          <label>GPU 节点<select value={nodeId} onChange={e => setNodeId(e.target.value)}>
            <option value="">按配置选用首个可用节点</option>
            {nodes.filter(n => n.enabled).map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
          </select></label>
          <label>随机种子<input value={seed} onChange={e => setSeed(e.target.value)} placeholder="可选，留空由模型决定" type="number" min={0}/></label>
        </div>
        <button className="primary" disabled={busy || !shotId || !promptId || !workflows.find(w => w.id === workflowId)?.ready}
          onClick={submit}>提交 GPU 生成任务</button>
        {!workflows.some(w => w.ready) && <p className="muted">尚未导入可执行 API 工作流。请将 ComfyUI 的 API 格式 JSON 放入服务器 workflows 目录并核对映射。</p>}
      </section>
      <section className="panel">
        <div className="panel-top"><h2>生成任务</h2><button onClick={refreshJobs}><RefreshCw size={15}/>刷新</button></div>
        {jobs.map(job => <div className="job-row" key={job.id}>
          <div><strong>{job.workflow_id}</strong> <span className={`status ${job.status}`}>{job.status}</span>
            <small>任务 {job.id.slice(0, 8)} · GPU {job.node_id}</small>
            {job.error && <p className="error-text">{job.error}</p>}</div>
          <div className="row-actions">
            {job.status === 'failed' && <button onClick={() => retry(job.id)}>重试</button>}
            {job.result_files.map(file => <button key={file.index} onClick={() =>
              window.directorDesktop.saveResult(api(`/generation-jobs/${job.id}/files/${file.index}`), file.filename).catch(report)
            }><Download size={15}/>下载 {file.filename}</button>)}
          </div>
        </div>)}
        {!jobs.length && <p className="muted">暂无生成任务。</p>}
      </section>
    </>}
  </div>
}

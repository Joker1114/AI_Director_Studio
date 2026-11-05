import { useEffect, useState } from 'react'
import { Plus, Sparkles, FileText } from 'lucide-react'
import { api, client, type Project, type Script } from '../lib/api'
import type { SharedProps } from '../App'

type Props = SharedProps & {
  project?: Project; script?: Script
  onProjectsChange(): Promise<void>
  onScriptsChange(): Promise<void>
  onScriptCreated(id: string): void
}

export default function ProjectsPage(props: Props) {
  const [title, setTitle] = useState('')
  const [style, setStyle] = useState('写实电影风格，真实布光，空间布局一致')
  const [text, setText] = useState('')
  const [extraction, setExtraction] = useState<{candidates: unknown[]; beats: unknown[]} | null>(null)
  const { projectId, scriptId, project, script, execute, busy } = props
  useEffect(() => { setText(script?.text ?? ''); setExtraction(null) }, [scriptId, script?.text])

  async function createProject() {
    if (!title.trim()) return
    await execute(async () => {
      await client.post(api('/projects'), { title: title.trim(), style_guide: style })
      await props.onProjectsChange()
      setTitle('')
    })
  }

  async function saveScript() {
    if (!projectId || text.trim().length < 10) return
    await execute(async () => {
      const created = await client.post<Script>(api(`/projects/${projectId}/scripts`), { text })
      await props.onScriptsChange()
      props.onScriptCreated(created.id)
    })
  }

  async function extract() {
    if (!scriptId) return
    const data = await execute(() => client.post<{candidates: unknown[]; beats: unknown[]}>(
      api(`/scripts/${scriptId}/extract`), { force: false },
    ))
    if (data) setExtraction(data)
  }

  return <div className="page">
    <div className="page-title"><div><span className="eyebrow">01 / SCREENPLAY</span>
      <h1>剧本与项目</h1><p>建立项目、保存剧本版本，并使用 Qwen3.8 解析剧情要素。</p></div></div>
    <div className="grid-two">
      <section className="panel">
        <h2><Plus size={18}/>创建项目</h2>
        <label>项目名称<input value={title} onChange={e => setTitle(e.target.value)} placeholder="例如：雨夜来客" /></label>
        <label>全剧统一画风<textarea rows={3} value={style} onChange={e => setStyle(e.target.value)}/></label>
        <button disabled={busy || !title.trim()} className="primary" onClick={createProject}>创建项目</button>
      </section>
      <section className="panel subtle">
        <h2><FileText size={18}/>当前项目信息</h2>
        {project ? <><div className="info-line"><strong>项目</strong><span>{project.title}</span></div>
          <div className="info-line"><strong>画风</strong><span>{project.style_guide}</span></div>
          <div className="info-line"><strong>剧本版本</strong><span>{script ? `V${script.version}` : '暂无'}</span></div></> :
          <p className="muted">请选择或创建项目，再开始制作短剧。</p>}
      </section>
    </div>
    <section className="panel">
      <div className="panel-top"><h2>剧本文本</h2><span className="muted">每次保存会创建新版本，不覆盖原始内容</span></div>
      <textarea className="script-input" value={text} onChange={e => setText(e.target.value)}
        placeholder="请在此输入小说章节、短剧剧本或场次描述..."/>
      <div className="row-actions">
        <button className="primary" disabled={!projectId || text.trim().length < 10 || busy} onClick={saveScript}>保存为新版本</button>
        <button disabled={!scriptId || busy} onClick={extract}><Sparkles size={16}/>Qwen3.8 提取人景物</button>
      </div>
      {extraction && <p className="success-text">本次提取获得 {extraction.candidates.length} 个资产候选、{extraction.beats.length} 个剧情事件，请进入「人物 · 场景 · 道具」审核。</p>}
    </section>
  </div>
}

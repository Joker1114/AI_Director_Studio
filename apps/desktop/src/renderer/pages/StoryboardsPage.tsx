import { useEffect, useState } from 'react'
import { Camera, Play, ShieldCheck, WandSparkles } from 'lucide-react'
import { api, client, type Asset, type Prompt, type Reference, type Shot } from '../lib/api'
import type { SharedProps } from '../App'

export default function StoryboardsPage({ projectId, scriptId, execute, report, busy }: SharedProps) {
  const [shots, setShots] = useState<Shot[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [selected, setSelected] = useState('')
  const [constraints, setConstraints] = useState('[]')
  const [narrative, setNarrative] = useState('')
  const [duration, setDuration] = useState(5)
  const [referenceIds, setReferenceIds] = useState<string[]>([])
  const [references, setReferences] = useState<Array<Reference & {assetName: string}>>([])
  const [validation, setValidation] = useState<{findings: Array<{level: string; message: string}>; has_errors: boolean} | null>(null)
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [guidance, setGuidance] = useState('保持场景左右结构、人物站位、正确持物动作与前后镜头连贯')
  const [purpose, setPurpose] = useState('shot_video')
  const [count, setCount] = useState(12)
  const shot = shots.find(x => x.id === selected)

  async function refresh() {
    if (!projectId) { setShots([]); setSelected(''); return }
    try {
      const data = await Promise.all([
        client.get<Shot[]>(api(`/projects/${projectId}/shots`)),
        client.get<Asset[]>(api(`/projects/${projectId}/assets`)),
      ])
      setShots(data[0]); setAssets(data[1]);
      setSelected(old => data[0].some(s => s.id === old) ? old : (data[0][0]?.id ?? ''))
    } catch (error) { report(error) }
  }

  useEffect(() => { void refresh() }, [projectId, scriptId])
  useEffect(() => {
    setConstraints(JSON.stringify(shot?.constraints ?? [], null, 2))
    setNarrative(shot?.narrative ?? '')
    setDuration(shot?.duration_seconds ?? 5)
    setReferenceIds(shot?.reference_ids ?? [])
    setValidation(null)
    if (!shot) { setPrompts([]); setReferences([]); return }
    client.get<Prompt[]>(api(`/prompts?owner_kind=shot&owner_id=${shot.id}`))
      .then(setPrompts).catch(report)
    Promise.all(assets.filter(a => shot.asset_ids.includes(a.id)).map(async asset => {
      const images = await client.get<Reference[]>(api(`/assets/${asset.id}/references`))
      return images.filter(x => x.approved).map(image => ({ ...image, assetName: asset.name }))
    })).then(data => setReferences(data.flat())).catch(report)
  }, [selected, shot?.revision, assets])

  async function plan() {
    if (!scriptId) return
    await execute(async () => {
      await client.post(api(`/scripts/${scriptId}/storyboard`), { count_limit: count, force: false })
      await refresh()
    })
  }

  async function save() {
    if (!shot) return
    let rules: unknown[]
    try {
      rules = JSON.parse(constraints)
      if (!Array.isArray(rules)) throw new Error('空间约束必须是 JSON 数组')
    } catch { report(new Error('空间约束 JSON 格式不正确')); return }
    await execute(async () => {
      await client.patch(api(`/shots/${shot.id}`), {
        revision: shot.revision, narrative, duration_seconds: duration,
        constraints: rules, reference_ids: referenceIds,
      })
      await refresh()
    })
  }

  async function validate() {
    if (!shot) return
    const result = await execute(() => client.get<typeof validation>(api(`/shots/${shot.id}/validate`)))
    if (result) setValidation(result)
  }

  async function polish() {
    if (!shot) return
    await execute(async () => {
      await client.post(api(`/shots/${shot.id}/prompts`), { purpose, user_guidance: guidance })
      setPrompts(await client.get(api(`/prompts?owner_kind=shot&owner_id=${shot.id}`)))
    })
  }

  async function review(prompt: Prompt) {
    await execute(async () => {
      await client.post(api(`/prompts/${prompt.id}/review`), { approved: !prompt.approved })
      setPrompts(await client.get(api(`/prompts?owner_kind=shot&owner_id=${shot?.id}`)))
    })
  }

  function toggleReference(id: string) {
    setReferenceIds(old => old.includes(id) ? old.filter(x => x !== id) : [...old, id])
  }

  return <div className="page">
    <div className="page-title"><div><span className="eyebrow">03 / STORYBOARD DIRECTOR</span>
      <h1>智能分镜与空间关系</h1><p>生成、编辑和审核镜头；参考图与空间事实对每个分镜独立绑定。</p></div></div>
    {!projectId ? <div className="empty">请先选择项目。</div> : <>
      <section className="panel panel-top">
        <div><h2><Camera size={18}/>Qwen 智能拆镜</h2><p className="muted">从当前剧本创建分镜；已有分镜不会被覆盖。</p></div>
        <div className="row-actions"><label className="inline-field">镜头上限<input type="number" min={1} max={30} value={count}
          onChange={e => setCount(Number(e.target.value))}/></label>
          <button className="primary" disabled={!scriptId || busy} onClick={plan}><Play size={15}/>生成分镜</button></div>
      </section>
      <div className="grid-two large-left">
        <section className="panel">
          <h2>镜头列表 <span className="muted">{shots.length} 镜</span></h2>
          <div className="shot-list">
            {shots.map(s => <button key={s.id} className={`shot-item ${selected === s.id ? 'selected' : ''}`}
              onClick={() => setSelected(s.id)}><span className="shot-number">{String(s.ordinal).padStart(2, '0')}</span>
              <span><strong>{s.narrative}</strong><small>{s.duration_seconds}s · {s.camera.shot_size ?? 'wide'} · {s.transition}</small></span></button>)}
          </div>
          {!shots.length && <p className="muted">暂无分镜，请在审核资产后执行智能拆镜。</p>}
        </section>
        <section className="panel">
          <h2><ShieldCheck size={18}/>分镜详情</h2>
          {shot ? <>
            <label>剧情与调度<textarea rows={3} value={narrative} onChange={e => setNarrative(e.target.value)}/></label>
            <label>镜头时长（秒）<input type="number" min={1} max={30} value={duration} onChange={e => setDuration(Number(e.target.value))}/></label>
            <label>空间与接触约束（JSON）<textarea className="mono" rows={9} value={constraints}
              onChange={e => setConstraints(e.target.value)}/></label>
            <h3>镜头参考图（最多9张，顺序代表 Picture 编号）</h3>
            <div className="checkbox-list">
              {references.map(r => <label key={r.id} className="checkbox-row">
                <input type="checkbox" checked={referenceIds.includes(r.id)} onChange={() => toggleReference(r.id)}/>
                <span>{r.assetName} · {r.role} · {r.original_filename}</span></label>)}
              {!references.length && <p className="muted">暂无已审核的资产参考图。</p>}
            </div>
            <div className="row-actions"><button className="primary" disabled={busy || referenceIds.length > 9} onClick={save}>保存镜头</button>
              <button disabled={busy} onClick={validate}>校验空间关系</button></div>
            {validation && <div className="validation">
              <strong>{validation.has_errors ? '存在空间冲突' : '元数据校验通过（不代表视觉质量已验收）'}</strong>
              {validation.findings.map((item, index) => <p key={index}>{item.level}: {item.message}</p>)}
            </div>}
            <hr/>
            <h3><WandSparkles size={16}/>分镜提示词</h3>
            <label>输出类型<select value={purpose} onChange={e => setPurpose(e.target.value)}>
              <option value="shot_still">首帧生图提示词</option><option value="shot_video">MiniMax H3 视频提示词</option>
            </select></label>
            <label>润色要求<textarea rows={2} value={guidance} onChange={e => setGuidance(e.target.value)}/></label>
            <button className="primary" disabled={busy} onClick={polish}>生成并润色提示词</button>
            {prompts.map(p => <div key={p.id} className="prompt-card">
              <div className="panel-top"><strong>{p.purpose} · V{p.version}</strong>
                <button onClick={() => review(p)}>{p.approved ? '已审核 · 撤销' : '审核通过'}</button></div>
              <pre>{p.compiled_prompt}</pre></div>)}
          </> : <p className="muted">点击左侧镜头查看详细信息。</p>}
        </section>
      </div>
    </>}
  </div>
}

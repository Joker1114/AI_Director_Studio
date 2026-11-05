import { useEffect, useState } from 'react'
import { BadgeCheck, ImagePlus, WandSparkles } from 'lucide-react'
import { api, client, type Asset, type Candidate, type Prompt, type Reference } from '../lib/api'
import type { SharedProps } from '../App'

const roleOptions = ['identity', 'pose', 'costume', 'composition', 'environment', 'prop', 'first_frame']

export default function AssetsPage({ projectId, scriptId, execute, busy, report }: SharedProps) {
  const [assets, setAssets] = useState<Asset[]>([])
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [selected, setSelected] = useState('')
  const [references, setReferences] = useState<Reference[]>([])
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [assetName, setAssetName] = useState('')
  const [assetKind, setAssetKind] = useState('character')
  const [assetDescription, setAssetDescription] = useState('')
  const [guidance, setGuidance] = useState('电影级写实、稳定身份、符合资产锁定事实')
  const [role, setRole] = useState('identity')
  const [imagePath, setImagePath] = useState('')
  const [lockedText, setLockedText] = useState('{}')
  const selectedAsset = assets.find(a => a.id === selected)

  async function refresh() {
    if (!projectId) { setAssets([]); setSelected(''); return }
    try {
      const data = await client.get<Asset[]>(api(`/projects/${projectId}/assets`))
      setAssets(data)
      setSelected(old => data.find(a => a.id === old)?.id ?? data[0]?.id ?? '')
    } catch (error) { report(error) }
  }

  async function refreshCandidates() {
    if (!scriptId) { setCandidates([]); return }
    try {
      const result = await client.get<{candidates: Candidate[]}>(api(`/scripts/${scriptId}/extraction`))
      setCandidates(result.candidates)
    } catch (error) { report(error) }
  }

  useEffect(() => { void refresh() }, [projectId])
  useEffect(() => { void refreshCandidates() }, [scriptId])
  useEffect(() => {
    setLockedText(JSON.stringify(selectedAsset?.locked_fields ?? {}, null, 2))
    if (!selected) { setReferences([]); setPrompts([]); return }
    Promise.all([
      client.get<Reference[]>(api(`/assets/${selected}/references`)),
      client.get<Prompt[]>(api(`/prompts?owner_kind=asset&owner_id=${selected}`)),
    ]).then(([r, p]) => { setReferences(r); setPrompts(p) }).catch(report)
  }, [selected, selectedAsset?.revision])

  async function approve(candidate: Candidate) {
    await execute(async () => {
      await client.post(api(`/candidates/${candidate.id}/approve`), {})
      await Promise.all([refresh(), refreshCandidates()])
    })
  }

  async function createAsset() {
    await execute(async () => {
      await client.post(api(`/projects/${projectId}/assets`), {
        kind: assetKind, name: assetName, description: assetDescription,
        facts: [], aliases: [], locked_fields: {},
      })
      setAssetName(''); setAssetDescription('')
      await refresh()
    })
  }

  async function updateLocks() {
    if (!selectedAsset) return
    let locks: Record<string, string>
    try {
      locks = JSON.parse(lockedText)
      if (typeof locks !== 'object' || !locks || Array.isArray(locks) ||
        Object.values(locks).some(value => typeof value !== 'string')) throw new Error('必须是字符串字典')
    } catch { report(new Error('锁定事实必须是 JSON 字符串键值对象')); return }
    await execute(async () => {
      await client.patch(api(`/assets/${selected}`), {
        revision: selectedAsset.revision, locked_fields: locks,
      })
      await refresh()
    })
  }

  async function polish() {
    await execute(async () => {
      await client.post(api(`/assets/${selected}/image-prompts`), {
        target_image_model: 'generic', request: guidance,
      })
      setPrompts(await client.get(api(`/prompts?owner_kind=asset&owner_id=${selected}`)))
    })
  }

  async function upload() {
    if (!selected || !imagePath) return
    await execute(async () => {
      await window.directorDesktop.uploadReference(selected, role, imagePath)
      setImagePath('')
      setReferences(await client.get(api(`/assets/${selected}/references`)))
    })
  }

  async function review(ref: Reference) {
    await execute(async () => {
      await client.post(api(`/references/${ref.id}/review`), { approved: !ref.approved })
      setReferences(await client.get(api(`/assets/${selected}/references`)))
    })
  }

  async function reviewPrompt(prompt: Prompt) {
    await execute(async () => {
      await client.post(api(`/prompts/${prompt.id}/review`), { approved: !prompt.approved })
      setPrompts(await client.get(api(`/prompts?owner_kind=asset&owner_id=${selected}`)))
    })
  }

  return <div className="page">
    <div className="page-title"><div><span className="eyebrow">02 / ASSET REGISTRY</span>
      <h1>人物 · 场景 · 道具</h1><p>每个资产独立维护身份、提示词、参考图及不可更改的事实。</p></div></div>
    {!projectId ? <div className="empty">请先选择项目。</div> : <>
      <section className="panel">
        <div className="panel-top"><h2>剧本提取候选</h2><button onClick={() => void refreshCandidates()}>刷新候选</button></div>
        <div className="asset-list">
          {candidates.filter(c => c.status === 'pending').map(c =>
            <div className="asset-item" key={c.id}><div><strong>{c.name}</strong><small>{c.kind} · {c.quote}</small></div>
              <button disabled={busy} onClick={() => approve(c)}><BadgeCheck size={15}/>批准入库</button></div>)}
          {!candidates.some(c => c.status === 'pending') && <p className="muted">暂无待审核候选。请先在剧本页面执行提取。</p>}
        </div>
      </section>
      <div className="grid-two large-left">
        <section className="panel">
          <h2>资产库 <span className="muted">{assets.length} 项</span></h2>
          <div className="asset-list tall">
            {assets.map(item => <button key={item.id}
              className={`asset-item selectable ${selected === item.id ? 'selected' : ''}`}
              onClick={() => setSelected(item.id)}>
              <span><strong>{item.name}</strong><small>{item.kind} · {item.description || '暂无描述'}</small></span></button>)}
          </div>
          <div className="form-grid">
            <label>名称<input value={assetName} onChange={e => setAssetName(e.target.value)}/></label>
            <label>类别<select value={assetKind} onChange={e => setAssetKind(e.target.value)}>
              <option value="character">角色</option><option value="scene">场景</option><option value="prop">道具</option>
            </select></label>
          </div>
          <label>描述<textarea rows={2} value={assetDescription} onChange={e => setAssetDescription(e.target.value)}/></label>
          <button disabled={!assetName.trim() || busy} onClick={createAsset}>手动新增资产</button>
        </section>
        <section className="panel">
          <h2>资产详情与提示词</h2>
          {selectedAsset ? <>
            <div className="info-line"><strong>名称</strong><span>{selectedAsset.name}</span></div>
            <label>锁定事实（JSON）<textarea rows={4} className="mono" value={lockedText} onChange={e => setLockedText(e.target.value)}/></label>
            <button disabled={busy} onClick={updateLocks}>保存锁定事实</button>
            <hr/>
            <label>生图提示词要求<textarea rows={3} value={guidance} onChange={e => setGuidance(e.target.value)}/></label>
            <button className="primary" disabled={busy} onClick={polish}><WandSparkles size={15}/>Qwen 润色生图提示词</button>
            {prompts.slice(0, 3).map(p => <div key={p.id} className="prompt-card">
              <div className="panel-top"><strong>生图提示词 V{p.version}</strong><button onClick={() => reviewPrompt(p)}>{p.approved ? '撤销审核' : '审核通过'}</button></div>
              <pre>{p.compiled_prompt}</pre></div>)}
            <hr/>
            <h3><ImagePlus size={16}/>参考图</h3>
            <label>图片用途<select value={role} onChange={e => setRole(e.target.value)}>{roleOptions.map(x => <option key={x}>{x}</option>)}</select></label>
            <div className="row-actions"><button onClick={async () => setImagePath(await window.directorDesktop.chooseImage() ?? '')}>选择图片</button>
              <button disabled={!imagePath || busy} onClick={upload}>上传至云端</button></div>
            {imagePath && <p className="muted cut">{imagePath}</p>}
            {references.map(ref => <div className="asset-item" key={ref.id}><span><strong>{ref.original_filename}</strong><small>{ref.role} · {ref.approved ? '已审核' : '待审核'}</small></span>
              <button onClick={() => review(ref)}>{ref.approved ? '撤销' : '审核'}</button></div>)}
          </> : <p className="muted">请选中左侧资产。</p>}
        </section>
      </div>
    </>}
  </div>
}

const state = {
  token: sessionStorage.getItem('director_token') || '',
  tab: 'script', projects: [], projectId: '', scripts: [], scriptId: '',
  assets: [], shots: [], extraction: { run: null, candidates: [], beats: [] },
  selectedAssetId: '', selectedShotId: '', prompts: [], refs: [], audit: [],
};
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pretty = obj => JSON.stringify(obj, null, 2);
const badge = (s) => `<span class="badge ${s === 'approved' || s === 'success' ? 'good' : s === 'pending' ? 'warn' : s === 'invalid_evidence' ? 'bad' : ''}">${esc(s)}</span>`;
const kindLabel = kind => ({ character: '角色', scene: '场景', prop: '道具' })[kind] || kind;
function alertMessage(message, isError = false) {
  const box = $('#alert'); box.textContent = String(message); box.className = `visible ${isError ? 'error' : ''}`;
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function load(text) { $('#loading-msg').textContent = text; $('#overlay').classList.remove('hidden'); }
function unload() { $('#overlay').classList.add('hidden'); }
async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers['X-API-Token'] = state.token;
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const result = await fetch(`/api${path}`, { ...options, headers });
  if (!result.ok) {
    const body = await result.json().catch(() => ({ detail: result.statusText }));
    throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail));
  }
  if (options.blob) return result.blob();
  return result.json();
}
async function action(fn, message = '正在请求 Qwen3.8 云端 API，耗时与剧本长度有关…') {
  load(message);
  try { await fn(); }
  catch (error) { console.error(error); alertMessage(error.message || '操作失败', true); }
  finally { unload(); }
}
async function refreshAll() {
  state.projects = await api('/projects');
  if (state.projectId && !state.projects.some(p => p.id === state.projectId)) state.projectId = '';
  if (!state.projectId && state.projects.length) state.projectId = state.projects[0].id;
  if (state.projectId) await refreshProject();
  render();
}
async function refreshProject() {
  const id = state.projectId;
  [state.scripts, state.assets, state.shots, state.audit] = await Promise.all([
    api(`/projects/${id}/scripts`), api(`/projects/${id}/assets`),
    api(`/projects/${id}/shots`), api(`/projects/${id}/llm-calls`)
  ]);
  if (!state.scripts.some(s => s.id === state.scriptId)) state.scriptId = state.scripts[0]?.id || '';
  state.extraction = state.scriptId ? await api(`/scripts/${state.scriptId}/extraction`) : { run: null, candidates: [], beats: [] };
  if (!state.assets.some(a => a.id === state.selectedAssetId)) state.selectedAssetId = state.assets[0]?.id || '';
  if (!state.shots.some(s => s.id === state.selectedShotId)) state.selectedShotId = state.shots[0]?.id || '';
  if (state.tab === 'assets' && state.selectedAssetId) await refreshAssetDetails();
  if (state.tab === 'shots' && state.selectedShotId) await refreshShotDetails();
}
async function refreshAssetDetails() {
  const id = state.selectedAssetId;
  state.prompts = await api(`/prompts?owner_kind=asset&owner_id=${id}`);
  state.refs = await api(`/assets/${id}/references`);
}
async function refreshShotDetails() {
  state.prompts = await api(`/prompts?owner_kind=shot&owner_id=${state.selectedShotId}`);
}
function render() {
  $('#project-picker').innerHTML = '<option value="">新建或选择项目</option>' + state.projects.map(p => `<option value="${p.id}" ${p.id === state.projectId ? 'selected' : ''}>${esc(p.title)}</option>`).join('');
  document.querySelectorAll('#navigation button').forEach(b => b.classList.toggle('active', b.dataset.tab === state.tab));
  if (!state.projectId) { $('#content').innerHTML = projectLanding(); return; }
  $('#content').innerHTML = ({ script: renderScript, assets: renderAssets, shots: renderShots, audit: renderAudit })[state.tab]();
}
function projectLanding() { return `<div class="page-header"><div><h1>开始创作</h1><p>创建一个项目，然后导入剧本，生成全剧统一资产。</p></div></div><section class="card" style="max-width:600px"><h2>新建短剧项目</h2><div class="field"><label>项目名称</label><input id="new-project-title" placeholder="例如：雨夜公交站 · 第1集" /></div><div class="field"><label>画面风格</label><input id="new-project-style" value="写实电影风格，人物身份与空间连续性优先" /></div><button data-action="create-project">创建项目</button></section>`; }
function renderScript() {
  const script = state.scripts.find(s => s.id === state.scriptId);
  const e = state.extraction;
  return `<div class="page-header"><div><h1>剧本解析</h1><p>保存剧本版本 → Qwen提取候选 → 核对原文证据 → 审核进入资产库。</p></div><button class="secondary" data-action="create-project-dialog">＋ 新建项目</button></div>
  <div class="grid"><section class="card"><div class="panel-header"><h2>剧本内容</h2><select id="script-select" style="width:160px">${state.scripts.map(s => `<option value="${s.id}" ${s.id === state.scriptId ? 'selected' : ''}>版本 ${s.version}</option>`).join('')}</select></div><textarea id="script-text" rows="15" placeholder="粘贴剧本原文；保存时会建立新的版本，不覆盖历史。">${esc(script?.text || '')}</textarea><div class="row right" style="margin-top:14px"><button class="secondary" data-action="save-script">保存新版本</button><button data-action="extract" ${script ? '' : 'disabled'}>✦ Qwen 提取人/景/物</button></div><p class="hint">每个候选都会记录原文引用跨度，无对应原文依据的结果不可审核通过。</p></section>
  <section class="card"><div class="panel-header"><h2>抽取结果</h2>${e.run ? badge(e.run.status) : ''}</div>${!e.run ? '<div class="empty">尚未抽取。请保存并解析剧本。</div>' : `<p class="hint">共识别 ${e.candidates.length} 个候选、${e.beats.length} 个情节事件。候选需人工确认。</p><div style="max-height:490px;overflow:auto">${e.candidates.map(c => `<div class="item"><div class="item-head">${badge(c.status)}<strong>${esc(c.name)}</strong><span class="textmuted">${kindLabel(c.kind)}</span></div><p>${esc(c.description)}</p><p class="hint">原文证据：「${esc(c.quote)}」</p>${c.status === 'pending' ? `<div class="row"><button data-action="approve-candidate" data-id="${c.id}">审核通过</button><button data-action="reject-candidate" data-id="${c.id}" class="secondary">拒绝</button></div>` : ''}</div>`).join('')}</div>`}</section></div>
  ${e.beats.length ? `<section class="card"><h2>已识别的剧情事件</h2>${e.beats.map((b, i) => `<div class="item"><strong>${i + 1}. ${esc(b.text)}</strong><p class="hint">${esc(b.scene_name)} · 「${esc(b.quote)}」</p></div>`).join('')}</section>` : ''}`;
}
function renderAssets() {
  const asset = state.assets.find(a => a.id === state.selectedAssetId);
  const refs = state.refs;
  return `<div class="page-header"><div><h1>统一资产中心</h1><p>所有角色、场景和道具拥有独立ID、锁定事实、提示词版本与参考图审核状态。</p></div><button class="secondary" data-action="create-asset">＋ 手工建立资产</button></div>
  <div class="asset-grid"><section class="card"><div class="panel-header"><h2>资产列表</h2><span class="badge">${state.assets.length}项</span></div><div class="asset-list">${state.assets.map(a => `<button data-action="select-asset" data-id="${a.id}" class="${a.id === state.selectedAssetId ? 'selected' : ''}">${esc(a.name)}<small>${kindLabel(a.kind)} · ${esc(a.status)} · r${a.revision}</small></button>`).join('') || '<div class="empty">尚无资产，请先解析剧本。</div>'}</div></section>
  ${asset ? `<section class="card"><div class="panel-header"><h2>${esc(asset.name)} ${badge(asset.status)}</h2><button class="secondary" data-action="save-asset">保存修改</button></div>
   <div class="field"><label>名称</label><input id="asset-name" value="${esc(asset.name)}" /></div><div class="field"><label>详细描述</label><textarea id="asset-description" rows="3">${esc(asset.description)}</textarea></div>
   <div class="two-col"><div class="field"><label>事实（JSON字符串数组）</label><textarea id="asset-facts" rows="5">${esc(pretty(asset.facts))}</textarea></div><div class="field"><label>锁定事实（JSON对象）</label><textarea id="asset-locked" rows="5">${esc(pretty(asset.locked_fields))}</textarea></div></div>
   <hr><div class="panel-header"><h2>资产生图提示词</h2><button data-action="polish-asset">✦ Qwen润色</button></div><div class="field"><label>润色要求</label><input id="asset-guidance" value="真实电影质感、清晰明确的对象外观、参考资产母版，保留锁定事实" /></div>
   ${state.prompts.map(p => promptCard(p)).join('') || '<p class="hint">暂无提示词版本。</p>'}
   <hr><div class="panel-header"><h2>参考图片</h2><span class="hint">审核后才会用于镜头的 &lt;Picture N&gt; 映射</span></div><div class="row"><input id="ref-upload" type="file" accept="image/png,image/jpeg,image/webp" style="max-width:290px"/><select id="ref-role" style="width:140px"><option value="identity">身份</option><option value="pose">动作姿态</option><option value="environment">环境布局</option><option value="composition">构图</option><option value="prop">道具</option><option value="first_frame">首帧</option></select><button data-action="upload-reference">上传参考图</button></div><div style="margin-top:15px">${refs.map(r => `<div class="ref-card"><div class="thumb-placeholder" id="thumb-${r.id}">参考图</div><div style="flex:1"><strong>${esc(r.original_filename)}</strong><p class="hint">${esc(r.role)} · ${r.approved ? '已审核' : '未审核'}</p><button data-action="review-reference" data-id="${r.id}" data-approved="${!r.approved}" class="secondary">${r.approved ? '取消审核' : '审核通过'}</button><button data-action="preview-reference" data-id="${r.id}" class="ghost">预览</button></div></div>`).join('') || '<p class="hint">暂无图片，请上传PNG/JPG/WEBP。</p>'}</div>
   </section>`: '<section class="card"><div class="empty">选择左侧资产进行编辑。</div></section>'}</div>`;
}
function promptCard(p) { return `<div class="item"><div class="item-head"><strong>${esc(p.purpose)} · V${p.version}</strong>${badge(p.approved ? 'approved' : 'pending')}<span class="hint">${esc(p.model)}</span></div><div class="prompt-view">${esc(p.compiled_prompt)}</div><div class="row right" style="margin-top:10px"><button class="secondary" data-action="copy-prompt" data-id="${p.id}">复制</button>${!p.approved ? `<button data-action="review-prompt" data-id="${p.id}">审核提示词</button>` : ''}</div></div>`; }
function renderShots() {
  const shot = state.shots.find(s => s.id === state.selectedShotId);
  return `<div class="page-header"><div><h1>智能分镜导演台</h1><p>镜头结构、人物朝向、画面左右位置和接触关系分开存储，润色不能修改锁定约束。</p></div><div class="row"><button class="secondary" data-action="new-shot">＋ 手工分镜</button><button data-action="plan-shots" ${state.scriptId ? '' : 'disabled'}>✦ Qwen自动分镜</button></div></div>
  <div class="asset-grid"><section class="card"><h2>镜头时间线</h2><div class="asset-list">${state.shots.map(s => `<button data-action="select-shot" data-id="${s.id}" class="${s.id === state.selectedShotId ? 'selected' : ''}">镜头 ${s.ordinal} · ${esc(s.narrative.slice(0, 36))}<small>${s.duration_seconds}秒 · ${esc(s.camera?.shot_size)} · ${esc(s.camera?.movement)}</small></button>`).join('') || '<div class="empty">暂无分镜。先审核资产，再选择自动分镜。</div>'}</div></section>
  ${shot ? `<section class="card"><div class="panel-header"><h2>分镜 ${shot.ordinal} · 编辑与校验</h2><button data-action="save-shot" class="secondary">保存镜头</button></div><div class="field"><label>剧情与动作</label><textarea id="shot-narrative" rows="4">${esc(shot.narrative)}</textarea></div><div class="two-col"><div class="field"><label>景别/镜头运动（JSON）</label><textarea id="shot-camera" rows="5">${esc(pretty(shot.camera))}</textarea></div><div class="field"><label>空间与接触约束（JSON数组）</label><textarea id="shot-constraints" rows="9">${esc(pretty(shot.constraints))}</textarea></div></div>
  <div class="two-col"><div class="field"><label>开始状态（JSON数组）</label><textarea id="shot-start" rows="5">${esc(pretty(shot.start_state))}</textarea></div><div class="field"><label>结束状态（JSON数组）</label><textarea id="shot-end" rows="5">${esc(pretty(shot.end_state))}</textarea></div></div>
  <div class="two-col"><div class="field"><label>转场方式</label><select id="shot-transition">${['cut', 'eyeline_match', 'action_match', 'time_jump', 'scene_change'].map(x => `<option ${shot.transition === x ? 'selected' : ''}>${x}</option>`).join('')}</select></div><div class="field"><label>分镜时长（秒）</label><input id="shot-duration" type="number" min="1" max="30" value="${shot.duration_seconds}" /></div></div>
  <div class="field"><label>关联资产</label><div class="row">${state.assets.map(a => `<label style="font-size:12px"><input class="asset-link" type="checkbox" value="${a.id}" ${shot.asset_ids.includes(a.id) ? 'checked' : ''}>${esc(a.name)}</label>`).join('')}</div></div>
  <div class="row"><button data-action="validate-shot" class="secondary">检查空间连续性</button><button data-action="polish-shot-still">✦ 首帧生图提示词</button><button data-action="polish-shot-video">✦ 视频提示词</button></div>
  <div class="field"><label>生成提示词额外要求</label><input id="shot-guidance" placeholder="如：保持右侧公交站，男人仅占画面10%，右手握住伞柄" /></div>
  <div class="item"><h3>提示词版本</h3>${state.prompts.map(p => promptCard(p)).join('') || '<p class="hint">尚未生成提示词。</p>'}</div></section>` : '<section class="card"><div class="empty">选择镜头进行编辑。</div></section>'}</div>`;
}
function renderAudit() { return `<div class="page-header"><div><h1>大模型调用记录</h1><p>记录模型、任务、延迟、Token统计和失败类型；不在日志中保存完整敏感剧本。</p></div></div><section class="card table-wrap"><table><thead><tr><th>时间</th><th>任务</th><th>模型</th><th>状态</th><th>耗时</th><th>Token 入/出</th></tr></thead><tbody>${state.audit.map(a => `<tr><td>${esc(a.created_at?.slice(0, 19))}</td><td>${esc(a.task)}</td><td>${esc(a.model)}</td><td>${badge(a.status)}</td><td>${a.elapsed_ms} ms</td><td>${a.input_tokens ?? '-'} / ${a.output_tokens ?? '-'}</td></tr>`).join('') || '<tr><td colspan="6">暂无云端调用记录</td></tr>'}</tbody></table></section>`; }
async function showModal(content) { $('#modal-content').innerHTML = content; $('#modal').showModal(); }
async function promptForToken() { await showModal(`<h2>设置访问令牌</h2><p class="hint">请输入服务器 .env 中配置的 APP_API_TOKEN。只暂存于当前浏览器标签会话，不会发送给 Qwen。</p><input id="token-value" type="password" placeholder="服务端APP_API_TOKEN" value="${esc(state.token)}" /><div class="row right" style="margin-top:15px"><button data-action="save-token">保存并连接</button></div>`); }
async function handle(actionName, el) {
  const id = el.dataset.id;
  switch (actionName) {
    case 'create-project': {
      const title = ($('#new-project-title')?.value || '').trim(); if (!title) throw new Error('请填写项目名称');
      const project = await api('/projects', { method: 'POST', body: JSON.stringify({ title, style_guide: $('#new-project-style')?.value || '写实电影风格' }) });
      state.projectId = project.id; if ($('#modal').open) $('#modal').close(); await refreshAll(); break;
    }
    case 'create-project-dialog': await showModal(`<h2>新建项目</h2><div class="field"><label>名称</label><input id="new-project-title" /></div><div class="field"><label>画面风格</label><input id="new-project-style" value="写实电影风格" /></div><button data-action="create-project">创建</button>`); break;
    case 'save-script': {
      const text = $('#script-text').value.trim(); if (text.length < 10) throw new Error('剧本至少10个字符');
      const s = await api(`/projects/${state.projectId}/scripts`, { method: 'POST', body: JSON.stringify({ text }) });
      state.scriptId = s.id; state.extraction = { run: null, candidates: [], beats: [] }; await refreshProject(); render(); alertMessage('新剧本版本已保存。'); break;
    }
    case 'extract': await action(async () => { state.extraction = await api(`/scripts/${state.scriptId}/extract`, { method: 'POST', body: JSON.stringify({ force: false }) }); await refreshProject(); render(); alertMessage('提取完成，请逐个审核候选资产。'); }); break;
    case 'approve-candidate': {
      await api(`/candidates/${id}/approve`, { method: 'POST', body: JSON.stringify({}) }); await refreshProject(); render(); alertMessage('资产已审核入库。'); break;
    }
    case 'reject-candidate': await api(`/candidates/${id}/reject`, { method: 'POST' }); await refreshProject(); render(); break;
    case 'create-asset': {
      const name = prompt('资产名称'); if (!name) return; const kind = prompt('输入资产类型：character / scene / prop', 'character') || 'character';
      await api(`/projects/${state.projectId}/assets`, { method: 'POST', body: JSON.stringify({ name, kind }) }); await refreshProject(); render(); break;
    }
    case 'select-asset': state.selectedAssetId = id; await refreshAssetDetails(); render(); break;
    case 'save-asset': {
      const a = state.assets.find(x => x.id === state.selectedAssetId);
      await api(`/assets/${a.id}`, { method: 'PATCH', body: JSON.stringify({ revision: a.revision, name: $('#asset-name').value, description: $('#asset-description').value, facts: JSON.parse($('#asset-facts').value), locked_fields: JSON.parse($('#asset-locked').value) }) });
      await refreshProject(); render(); alertMessage('资产已保存，并更新修订号。'); break;
    }
    case 'polish-asset': await action(async () => {
      await api(`/assets/${state.selectedAssetId}/image-prompts`, { method: 'POST', body: JSON.stringify({ request: $('#asset-guidance').value, target_image_model: 'generic' }) });
      await refreshAssetDetails(); render(); alertMessage('生图提示词已生成，等待审核。');    
}); break;
    case 'upload-reference': {
      const file = $('#ref-upload').files?.[0]; if (!file) throw new Error('请先选取参考图片');
      const form = new FormData(); form.append('file', file); form.append('role', $('#ref-role').value);
      await api(`/assets/${state.selectedAssetId}/references?role=${encodeURIComponent($('#ref-role').value)}`, { method: 'POST', body: form });
      await refreshAssetDetails(); render(); alertMessage('参考图已上传，审核后可用于分镜。'); break;
    }
    case 'review-reference': await api(`/references/${id}/review`, { method: 'POST', body: JSON.stringify({ approved: el.dataset.approved === 'true' }) }); await refreshAssetDetails(); render(); break;
    case 'preview-reference': {
      const blob = await api(`/references/${id}/file`, { blob: true }); const url = URL.createObjectURL(blob);
      await showModal(`<h2>参考图预览</h2><img src="${url}" alt="参考图" style="width:100%;max-height:68vh;object-fit:contain"/>`);
      $('#modal').addEventListener('close', () => URL.revokeObjectURL(url), { once: true }); break;
    }
    case 'plan-shots': await action(async () => {
      if (state.shots.length && !confirm('当前项目已有分镜。对当前剧本重复规划会沿用已有镜头。继续吗？')) return;
      await api(`/scripts/${state.scriptId}/storyboard`, { method: 'POST', body: JSON.stringify({ count_limit: 12, force: false }) });
      await refreshProject(); await refreshShotDetails(); render(); alertMessage('分镜已生成；可编辑空间约束后再润色。');
    }, 'Qwen3.8 正在根据剧本及已审核资产设计分镜…'); break;
    case 'new-shot': {
      if (!state.scriptId) throw new Error('请先保存剧本');
      const narrative = prompt('请输入分镜剧情'); if (!narrative) return;
      await api(`/projects/${state.projectId}/shots`, { method: 'POST', body: JSON.stringify({ script_id: state.scriptId, ordinal: 1 + Math.max(0, ...state.shots.filter(s => s.script_id === state.scriptId).map(s => s.ordinal)), narrative }) });
      await refreshProject(); render(); break;
    }
    case 'select-shot': state.selectedShotId = id; await refreshShotDetails(); render(); break;
    case 'save-shot': {
      const s = state.shots.find(x => x.id === state.selectedShotId);
      await api(`/shots/${s.id}`, { method: 'PATCH', body: JSON.stringify({ revision: s.revision, narrative: $('#shot-narrative').value, duration_seconds: Number($('#shot-duration').value), camera: JSON.parse($('#shot-camera').value), constraints: JSON.parse($('#shot-constraints').value), start_state: JSON.parse($('#shot-start').value), end_state: JSON.parse($('#shot-end').value), transition: $('#shot-transition').value, asset_ids: [...document.querySelectorAll('.asset-link:checked')].map(x => x.value) }) });
      await refreshProject(); await refreshShotDetails(); render(); alertMessage('分镜已保存。'); break;
    }
    case 'validate-shot': {
      const result = await api(`/shots/${state.selectedShotId}/validate`);
      await showModal(`<h2>分镜连续性检查</h2>${result.findings.length ? result.findings.map(f => `<div class="item">${badge(f.level)} <strong>${esc(f.code)}</strong> ${esc(f.message)}</div>`).join('') : '<p>✓ 当前结构化分镜未检出规则冲突。<br><small>注意：不代表最终画面像素必然符合约束。</small></p>'}`); break;
    }
    case 'polish-shot-still': case 'polish-shot-video': await action(async () => {
      const purpose = actionName === 'polish-shot-still' ? 'shot_still' : 'shot_video';
      await api(`/shots/${state.selectedShotId}/prompts`, { method: 'POST', body: JSON.stringify({ purpose, user_guidance: $('#shot-guidance').value }) });
      await refreshShotDetails(); render(); alertMessage('分镜提示词已生成并保留新版本。');
    }); break;
    case 'copy-prompt': {
      const p = state.prompts.find(x => x.id === id); await navigator.clipboard.writeText(p.compiled_prompt); alertMessage('提示词已复制。'); break;
    }
    case 'review-prompt': await api(`/prompts/${id}/review`, { method: 'POST', body: JSON.stringify({ approved: true }) });
      if (state.tab === 'shots') await refreshShotDetails(); else await refreshAssetDetails(); render(); break;
    case 'save-token': state.token = $('#token-value').value; sessionStorage.setItem('director_token', state.token); $('#modal').close(); await refreshAll(); break;
    default: throw new Error('未知操作：' + actionName);
  }
}
document.addEventListener('click', event => {
  const button = event.target.closest('[data-action]'); if (!button) return;
  action(() => handle(button.dataset.action, button), '操作执行中…');
});
$('#project-picker').addEventListener('change', event => action(async () => { state.projectId = event.target.value; state.scriptId = ''; state.selectedAssetId = ''; state.selectedShotId = ''; if (state.projectId) await refreshProject(); render(); }));
$('#navigation').addEventListener('click', event => {
  const tab = event.target.closest('[data-tab]')?.dataset.tab; if (!tab) return;
  action(async () => { state.tab = tab; if (tab === 'assets' && state.selectedAssetId) await refreshAssetDetails(); if (tab === 'shots' && state.selectedShotId) await refreshShotDetails(); render(); }, '加载工作台…');
});
$('#content').addEventListener('change', event => {
  if (event.target.id === 'script-select') action(async () => { state.scriptId = event.target.value; state.extraction = await api(`/scripts/${state.scriptId}/extraction`); render(); });
});
$('#refresh').addEventListener('click', () => action(refreshAll, '正在刷新…'));
$('#setup-token').addEventListener('click', promptForToken);
$('#close-dialog').addEventListener('click', () => $('#modal').close());
(async () => {
  try {
    const health = await api('/health');
    $('#cloud-status').textContent = health.qwen_configured ? 'Qwen已配置' : '未配置Qwen密钥';
    await refreshAll();
  } catch (error) { await promptForToken(); }
})();

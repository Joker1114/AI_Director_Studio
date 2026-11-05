<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Camera, Play, ShieldCheck, WandSparkles } from 'lucide-vue-next'
import { api, client, type Asset, type Prompt, type Reference, type Shot } from '../lib/api'
import type { SharedProps } from '../lib/shared'

type Validation = { findings: Array<{ level: string; message: string }>; has_errors: boolean }
type NamedReference = Reference & { assetName: string }

const props = defineProps<SharedProps>()
const shots = ref<Shot[]>([])
const assets = ref<Asset[]>([])
const selected = ref('')
const constraints = ref('[]')
const narrative = ref('')
const duration = ref(5)
const referenceIds = ref<string[]>([])
const references = ref<NamedReference[]>([])
const validation = ref<Validation | null>(null)
const prompts = ref<Prompt[]>([])
const guidance = ref('保持场景左右结构、人物站位、正确持物动作与前后镜头连贯')
const purpose = ref('shot_video')
const count = ref(12)
const shot = computed(() => shots.value.find(item => item.id === selected.value))

async function refresh(): Promise<void> {
  if (!props.projectId) {
    shots.value = []
    selected.value = ''
    return
  }
  try {
    const [loadedShots, loadedAssets] = await Promise.all([
      client.get<Shot[]>(api(`/projects/${props.projectId}/shots`)),
      client.get<Asset[]>(api(`/projects/${props.projectId}/assets`)),
    ])
    shots.value = loadedShots
    assets.value = loadedAssets
    selected.value = loadedShots.some(item => item.id === selected.value)
      ? selected.value : (loadedShots[0]?.id ?? '')
  } catch (error) {
    props.report(error)
  }
}

watch([() => props.projectId, () => props.scriptId], () => { void refresh() }, { immediate: true })
watch([selected, () => shot.value?.revision, assets], () => {
  constraints.value = JSON.stringify(shot.value?.constraints ?? [], null, 2)
  narrative.value = shot.value?.narrative ?? ''
  duration.value = shot.value?.duration_seconds ?? 5
  referenceIds.value = shot.value?.reference_ids ?? []
  validation.value = null
  if (!shot.value) {
    prompts.value = []
    references.value = []
    return
  }
  const currentShot = shot.value
  client.get<Prompt[]>(api(`/prompts?owner_kind=shot&owner_id=${currentShot.id}`))
    .then(data => { prompts.value = data }).catch(props.report)
  Promise.all(assets.value.filter(asset => currentShot.asset_ids.includes(asset.id)).map(async asset => {
    const images = await client.get<Reference[]>(api(`/assets/${asset.id}/references`))
    return images.filter(image => image.approved).map(image => ({ ...image, assetName: asset.name }))
  })).then(data => { references.value = data.flat() }).catch(props.report)
}, { immediate: true })

async function plan(): Promise<void> {
  if (!props.scriptId) return
  await props.execute(async () => {
    await client.post(api(`/scripts/${props.scriptId}/storyboard`), { count_limit: count.value, force: false })
    await refresh()
  })
}

async function save(): Promise<void> {
  if (!shot.value) return
  let rules: unknown[]
  try {
    rules = JSON.parse(constraints.value)
    if (!Array.isArray(rules)) throw new Error('空间约束必须是 JSON 数组')
  } catch {
    props.report(new Error('空间约束 JSON 格式不正确'))
    return
  }
  await props.execute(async () => {
    await client.patch(api(`/shots/${shot.value?.id}`), {
      revision: shot.value?.revision, narrative: narrative.value, duration_seconds: duration.value,
      constraints: rules, reference_ids: referenceIds.value,
    })
    await refresh()
  })
}

async function validate(): Promise<void> {
  if (!shot.value) return
  const result = await props.execute(() => client.get<Validation>(api(`/shots/${shot.value?.id}/validate`)))
  if (result) validation.value = result
}

async function polish(): Promise<void> {
  if (!shot.value) return
  await props.execute(async () => {
    await client.post(api(`/shots/${shot.value?.id}/prompts`), {
      purpose: purpose.value, user_guidance: guidance.value,
    })
    prompts.value = await client.get<Prompt[]>(api(`/prompts?owner_kind=shot&owner_id=${shot.value?.id}`))
  })
}

async function review(prompt: Prompt): Promise<void> {
  await props.execute(async () => {
    await client.post(api(`/prompts/${prompt.id}/review`), { approved: !prompt.approved })
    prompts.value = await client.get<Prompt[]>(api(`/prompts?owner_kind=shot&owner_id=${shot.value?.id}`))
  })
}

function toggleReference(id: string): void {
  referenceIds.value = referenceIds.value.includes(id)
    ? referenceIds.value.filter(item => item !== id)
    : [...referenceIds.value, id]
}
</script>

<template>
  <div class="page">
    <div class="page-title"><div><span class="eyebrow">03 / STORYBOARD DIRECTOR</span>
      <h1>智能分镜与空间关系</h1><p>生成、编辑和审核镜头；参考图与空间事实对每个分镜独立绑定。</p></div></div>
    <div v-if="!projectId" class="empty">请先选择项目。</div>
    <template v-else>
      <section class="panel panel-top">
        <div><h2><Camera :size="18" />Qwen 智能拆镜</h2><p class="muted">从当前剧本创建分镜；已有分镜不会被覆盖。</p></div>
        <div class="row-actions"><label class="inline-field">镜头上限<input v-model.number="count" type="number" min="1" max="30" /></label>
          <button class="primary" :disabled="!scriptId || busy" @click="plan"><Play :size="15" />生成分镜</button></div>
      </section>
      <div class="grid-two large-left">
        <section class="panel">
          <h2>镜头列表 <span class="muted">{{ shots.length }} 镜</span></h2>
          <div class="shot-list">
            <button v-for="item in shots" :key="item.id" :class="['shot-item', { selected: selected === item.id }]"
              @click="selected = item.id">
              <span class="shot-number">{{ String(item.ordinal).padStart(2, '0') }}</span>
              <span><strong>{{ item.narrative }}</strong><small>{{ item.duration_seconds }}s · {{ item.camera.shot_size ?? 'wide' }} · {{ item.transition }}</small></span>
            </button>
          </div>
          <p v-if="!shots.length" class="muted">暂无分镜，请在审核资产后执行智能拆镜。</p>
        </section>
        <section class="panel">
          <h2><ShieldCheck :size="18" />分镜详情</h2>
          <template v-if="shot">
            <label>剧情与调度<textarea v-model="narrative" rows="3" /></label>
            <label>镜头时长（秒）<input v-model.number="duration" type="number" min="1" max="30" /></label>
            <label>空间与接触约束（JSON）<textarea v-model="constraints" class="mono" rows="9" /></label>
            <h3>镜头参考图（最多9张，顺序代表 Picture 编号）</h3>
            <div class="checkbox-list">
              <label v-for="reference in references" :key="reference.id" class="checkbox-row">
                <input type="checkbox" :checked="referenceIds.includes(reference.id)" @change="toggleReference(reference.id)" />
                <span>{{ reference.assetName }} · {{ reference.role }} · {{ reference.original_filename }}</span>
              </label>
              <p v-if="!references.length" class="muted">暂无已审核的资产参考图。</p>
            </div>
            <div class="row-actions"><button class="primary" :disabled="busy || referenceIds.length > 9" @click="save">保存镜头</button>
              <button :disabled="busy" @click="validate">校验空间关系</button></div>
            <div v-if="validation" class="validation">
              <strong>{{ validation.has_errors ? '存在空间冲突' : '元数据校验通过（不代表视觉质量已验收）' }}</strong>
              <p v-for="(item, index) in validation.findings" :key="index">{{ item.level }}: {{ item.message }}</p>
            </div>
            <hr />
            <h3><WandSparkles :size="16" />分镜提示词</h3>
            <label>输出类型<select v-model="purpose">
              <option value="shot_still">首帧生图提示词</option><option value="shot_video">MiniMax H3 视频提示词</option>
            </select></label>
            <label>润色要求<textarea v-model="guidance" rows="2" /></label>
            <button class="primary" :disabled="busy" @click="polish">生成并润色提示词</button>
            <div v-for="prompt in prompts" :key="prompt.id" class="prompt-card">
              <div class="panel-top"><strong>{{ prompt.purpose }} · V{{ prompt.version }}</strong>
                <button @click="review(prompt)">{{ prompt.approved ? '已审核 · 撤销' : '审核通过' }}</button></div>
              <pre>{{ prompt.compiled_prompt }}</pre>
            </div>
          </template>
          <p v-else class="muted">点击左侧镜头查看详细信息。</p>
        </section>
      </div>
    </template>
  </div>
</template>

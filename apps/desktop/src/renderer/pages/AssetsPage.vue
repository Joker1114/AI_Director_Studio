<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { BadgeCheck, ImagePlus, WandSparkles } from 'lucide-vue-next'
import { api, client, type Asset, type Candidate, type Prompt, type Reference } from '../lib/api'
import type { SharedProps } from '../lib/shared'

const roleOptions = ['identity', 'pose', 'costume', 'composition', 'environment', 'prop', 'first_frame']
const props = defineProps<SharedProps>()
const assets = ref<Asset[]>([])
const candidates = ref<Candidate[]>([])
const selected = ref('')
const references = ref<Reference[]>([])
const prompts = ref<Prompt[]>([])
const assetName = ref('')
const assetKind = ref('character')
const assetDescription = ref('')
const guidance = ref('电影级写实、稳定身份、符合资产锁定事实')
const role = ref('identity')
const imagePath = ref('')
const lockedText = ref('{}')
const selectedAsset = computed(() => assets.value.find(asset => asset.id === selected.value))

async function refresh(): Promise<void> {
  if (!props.projectId) {
    assets.value = []
    selected.value = ''
    return
  }
  try {
    const data = await client.get<Asset[]>(api(`/projects/${props.projectId}/assets`))
    assets.value = data
    selected.value = data.find(asset => asset.id === selected.value)?.id ?? data[0]?.id ?? ''
  } catch (error) {
    props.report(error)
  }
}

async function refreshCandidates(): Promise<void> {
  if (!props.scriptId) {
    candidates.value = []
    return
  }
  try {
    const result = await client.get<{ candidates: Candidate[] }>(api(`/scripts/${props.scriptId}/extraction`))
    candidates.value = result.candidates
  } catch (error) {
    props.report(error)
  }
}

watch(() => props.projectId, () => { void refresh() }, { immediate: true })
watch(() => props.scriptId, () => { void refreshCandidates() }, { immediate: true })
watch([selected, () => selectedAsset.value?.revision], () => {
  lockedText.value = JSON.stringify(selectedAsset.value?.locked_fields ?? {}, null, 2)
  if (!selected.value) {
    references.value = []
    prompts.value = []
    return
  }
  Promise.all([
    client.get<Reference[]>(api(`/assets/${selected.value}/references`)),
    client.get<Prompt[]>(api(`/prompts?owner_kind=asset&owner_id=${selected.value}`)),
  ]).then(([loadedReferences, loadedPrompts]) => {
    references.value = loadedReferences
    prompts.value = loadedPrompts
  }).catch(props.report)
}, { immediate: true })

async function approve(candidate: Candidate): Promise<void> {
  await props.execute(async () => {
    await client.post(api(`/candidates/${candidate.id}/approve`), {})
    await Promise.all([refresh(), refreshCandidates()])
  })
}

async function createAsset(): Promise<void> {
  await props.execute(async () => {
    await client.post(api(`/projects/${props.projectId}/assets`), {
      kind: assetKind.value, name: assetName.value, description: assetDescription.value,
      facts: [], aliases: [], locked_fields: {},
    })
    assetName.value = ''
    assetDescription.value = ''
    await refresh()
  })
}

async function updateLocks(): Promise<void> {
  if (!selectedAsset.value) return
  let locks: Record<string, string>
  try {
    locks = JSON.parse(lockedText.value)
    if (typeof locks !== 'object' || !locks || Array.isArray(locks) ||
      Object.values(locks).some(value => typeof value !== 'string')) throw new Error('必须是字符串字典')
  } catch {
    props.report(new Error('锁定事实必须是 JSON 字符串键值对象'))
    return
  }
  await props.execute(async () => {
    await client.patch(api(`/assets/${selected.value}`), {
      revision: selectedAsset.value?.revision, locked_fields: locks,
    })
    await refresh()
  })
}

async function polish(): Promise<void> {
  await props.execute(async () => {
    await client.post(api(`/assets/${selected.value}/image-prompts`), {
      target_image_model: 'generic', request: guidance.value,
    })
    prompts.value = await client.get<Prompt[]>(api(`/prompts?owner_kind=asset&owner_id=${selected.value}`))
  })
}

async function chooseImage(): Promise<void> {
  try {
    imagePath.value = await window.directorDesktop.chooseImage() ?? ''
  } catch (error) {
    props.report(error)
  }
}

async function upload(): Promise<void> {
  if (!selected.value || !imagePath.value) return
  await props.execute(async () => {
    await window.directorDesktop.uploadReference(selected.value, role.value, imagePath.value)
    imagePath.value = ''
    references.value = await client.get<Reference[]>(api(`/assets/${selected.value}/references`))
  })
}

async function review(reference: Reference): Promise<void> {
  await props.execute(async () => {
    await client.post(api(`/references/${reference.id}/review`), { approved: !reference.approved })
    references.value = await client.get<Reference[]>(api(`/assets/${selected.value}/references`))
  })
}

async function reviewPrompt(prompt: Prompt): Promise<void> {
  await props.execute(async () => {
    await client.post(api(`/prompts/${prompt.id}/review`), { approved: !prompt.approved })
    prompts.value = await client.get<Prompt[]>(api(`/prompts?owner_kind=asset&owner_id=${selected.value}`))
  })
}
</script>

<template>
  <div class="page">
    <div class="page-title"><div><span class="eyebrow">02 / ASSET REGISTRY</span>
      <h1>人物 · 场景 · 道具</h1><p>每个资产独立维护身份、提示词、参考图及不可更改的事实。</p></div></div>
    <div v-if="!projectId" class="empty">请先选择项目。</div>
    <template v-else>
      <section class="panel">
        <div class="panel-top"><h2>剧本提取候选</h2><button @click="refreshCandidates">刷新候选</button></div>
        <div class="asset-list">
          <div v-for="candidate in candidates.filter(item => item.status === 'pending')" :key="candidate.id" class="asset-item">
            <div><strong>{{ candidate.name }}</strong><small>{{ candidate.kind }} · {{ candidate.quote }}</small></div>
            <button :disabled="busy" @click="approve(candidate)"><BadgeCheck :size="15" />批准入库</button>
          </div>
          <p v-if="!candidates.some(item => item.status === 'pending')" class="muted">暂无待审核候选。请先在剧本页面执行提取。</p>
        </div>
      </section>
      <div class="grid-two large-left">
        <section class="panel">
          <h2>资产库 <span class="muted">{{ assets.length }} 项</span></h2>
          <div class="asset-list tall">
            <button v-for="item in assets" :key="item.id"
              :class="['asset-item', 'selectable', { selected: selected === item.id }]"
              @click="selected = item.id">
              <span><strong>{{ item.name }}</strong><small>{{ item.kind }} · {{ item.description || '暂无描述' }}</small></span>
            </button>
          </div>
          <div class="form-grid">
            <label>名称<input v-model="assetName" /></label>
            <label>类别<select v-model="assetKind">
              <option value="character">角色</option><option value="scene">场景</option><option value="prop">道具</option>
            </select></label>
          </div>
          <label>描述<textarea v-model="assetDescription" rows="2" /></label>
          <button :disabled="!assetName.trim() || busy" @click="createAsset">手动新增资产</button>
        </section>
        <section class="panel">
          <h2>资产详情与提示词</h2>
          <template v-if="selectedAsset">
            <div class="info-line"><strong>名称</strong><span>{{ selectedAsset.name }}</span></div>
            <label>锁定事实（JSON）<textarea v-model="lockedText" rows="4" class="mono" /></label>
            <button :disabled="busy" @click="updateLocks">保存锁定事实</button>
            <hr />
            <label>生图提示词要求<textarea v-model="guidance" rows="3" /></label>
            <button class="primary" :disabled="busy" @click="polish"><WandSparkles :size="15" />Qwen 润色生图提示词</button>
            <div v-for="prompt in prompts.slice(0, 3)" :key="prompt.id" class="prompt-card">
              <div class="panel-top"><strong>生图提示词 V{{ prompt.version }}</strong>
                <button @click="reviewPrompt(prompt)">{{ prompt.approved ? '撤销审核' : '审核通过' }}</button></div>
              <pre>{{ prompt.compiled_prompt }}</pre>
            </div>
            <hr />
            <h3><ImagePlus :size="16" />参考图</h3>
            <label>图片用途<select v-model="role"><option v-for="option in roleOptions" :key="option">{{ option }}</option></select></label>
            <div class="row-actions"><button @click="chooseImage">选择图片</button>
              <button :disabled="!imagePath || busy" @click="upload">上传至云端</button></div>
            <p v-if="imagePath" class="muted cut">{{ imagePath }}</p>
            <div v-for="reference in references" :key="reference.id" class="asset-item">
              <span><strong>{{ reference.original_filename }}</strong><small>{{ reference.role }} · {{ reference.approved ? '已审核' : '待审核' }}</small></span>
              <button @click="review(reference)">{{ reference.approved ? '撤销' : '审核' }}</button>
            </div>
          </template>
          <p v-else class="muted">请选中左侧资产。</p>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Plus, Sparkles, FileText } from 'lucide-vue-next'
import { api, client, type Project, type Script } from '../lib/api'
import type { SharedProps } from '../lib/shared'

interface Props extends SharedProps {
  project?: Project
  script?: Script
  onProjectsChange(): Promise<void>
  onScriptsChange(): Promise<void>
  onScriptCreated(id: string): void
}

const props = defineProps<Props>()
const title = ref('')
const style = ref('写实电影风格，真实布光，空间布局一致')
const text = ref('')
const extraction = ref<{ candidates: unknown[]; beats: unknown[] } | null>(null)

watch([() => props.scriptId, () => props.script?.text], () => {
  text.value = props.script?.text ?? ''
  extraction.value = null
}, { immediate: true })

async function createProject(): Promise<void> {
  if (!title.value.trim()) return
  await props.execute(async () => {
    await client.post(api('/projects'), { title: title.value.trim(), style_guide: style.value })
    await props.onProjectsChange()
    title.value = ''
  })
}

async function saveScript(): Promise<void> {
  if (!props.projectId || text.value.trim().length < 10) return
  await props.execute(async () => {
    const created = await client.post<Script>(api(`/projects/${props.projectId}/scripts`), { text: text.value })
    await props.onScriptsChange()
    props.onScriptCreated(created.id)
  })
}

async function extract(): Promise<void> {
  if (!props.scriptId) return
  const data = await props.execute(() => client.post<{ candidates: unknown[]; beats: unknown[] }>(
    api(`/scripts/${props.scriptId}/extract`), { force: false },
  ))
  if (data) extraction.value = data
}
</script>

<template>
  <div class="page">
    <div class="page-title"><div><span class="eyebrow">01 / SCREENPLAY</span>
      <h1>剧本与项目</h1><p>建立项目、保存剧本版本，并使用 Qwen3.8 解析剧情要素。</p></div></div>
    <div class="grid-two">
      <section class="panel">
        <h2><Plus :size="18" />创建项目</h2>
        <label>项目名称<input v-model="title" placeholder="例如：雨夜来客" /></label>
        <label>全剧统一画风<textarea v-model="style" rows="3" /></label>
        <button :disabled="busy || !title.trim()" class="primary" @click="createProject">创建项目</button>
      </section>
      <section class="panel subtle">
        <h2><FileText :size="18" />当前项目信息</h2>
        <template v-if="project">
          <div class="info-line"><strong>项目</strong><span>{{ project.title }}</span></div>
          <div class="info-line"><strong>画风</strong><span>{{ project.style_guide }}</span></div>
          <div class="info-line"><strong>剧本版本</strong><span>{{ script ? `V${script.version}` : '暂无' }}</span></div>
        </template>
        <p v-else class="muted">请选择或创建项目，再开始制作短剧。</p>
      </section>
    </div>
    <section class="panel">
      <div class="panel-top"><h2>剧本文本</h2><span class="muted">每次保存会创建新版本，不覆盖原始内容</span></div>
      <textarea v-model="text" class="script-input"
        placeholder="请在此输入小说章节、短剧剧本或场次描述..." />
      <div class="row-actions">
        <button class="primary" :disabled="!projectId || text.trim().length < 10 || busy" @click="saveScript">保存为新版本</button>
        <button :disabled="!scriptId || busy" @click="extract"><Sparkles :size="16" />Qwen3.8 提取人景物</button>
      </div>
      <p v-if="extraction" class="success-text">本次提取获得 {{ extraction.candidates.length }} 个资产候选、{{ extraction.beats.length }} 个剧情事件，请进入「人物 · 场景 · 道具」审核。</p>
    </section>
  </div>
</template>

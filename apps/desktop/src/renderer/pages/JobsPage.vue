<script setup lang="ts">
import { ref, watch } from 'vue'
import { Download, Play, RefreshCw } from 'lucide-vue-next'
import { api, client, type Job, type Prompt, type Shot } from '../lib/api'
import type { SharedProps } from '../lib/shared'

type Workflow = { id: string; name: string; ready: boolean; max_images: number }
type Node = { id: string; name: string; enabled: boolean; models: string[] }

const props = defineProps<SharedProps>()
const jobs = ref<Job[]>([])
const shots = ref<Shot[]>([])
const prompts = ref<Prompt[]>([])
const workflows = ref<Workflow[]>([])
const nodes = ref<Node[]>([])
const shotId = ref('')
const promptId = ref('')
const workflowId = ref('minimax_h3')
const nodeId = ref('')
const seed = ref('')

async function refreshJobs(): Promise<void> {
  if (!props.projectId) return
  try {
    jobs.value = await client.get<Job[]>(api(`/projects/${props.projectId}/generation-jobs`))
  } catch (error) {
    props.report(error)
  }
}

watch(() => props.projectId, (currentProjectId, _previous, onCleanup) => {
  if (!currentProjectId) {
    jobs.value = []
    shots.value = []
    return
  }
  Promise.all([
    client.get<Shot[]>(api(`/projects/${currentProjectId}/shots`)),
    client.get<Workflow[]>(api('/workflows')),
    client.get<Node[]>(api('/gpu-nodes')),
  ]).then(([loadedShots, loadedWorkflows, loadedNodes]) => {
    shots.value = loadedShots
    workflows.value = loadedWorkflows
    nodes.value = loadedNodes
    shotId.value = loadedShots.some(item => item.id === shotId.value)
      ? shotId.value : (loadedShots[0]?.id ?? '')
  }).catch(props.report)
  void refreshJobs()
  const timer = setInterval(() => { void refreshJobs() }, 5000)
  onCleanup(() => clearInterval(timer))
}, { immediate: true })

watch(shotId, currentShotId => {
  if (!currentShotId) {
    prompts.value = []
    promptId.value = ''
    return
  }
  client.get<Prompt[]>(api(`/prompts?owner_kind=shot&owner_id=${currentShotId}`))
    .then(all => {
      const approved = all.filter(prompt => prompt.purpose === 'shot_video' && prompt.approved)
      prompts.value = approved
      promptId.value = approved[0]?.id ?? ''
    }).catch(props.report)
}, { immediate: true })

async function submit(): Promise<void> {
  await props.execute(async () => {
    await client.post(api('/generation-jobs'), {
      shot_id: shotId.value, prompt_version_id: promptId.value, workflow_id: workflowId.value,
      node_id: nodeId.value || null, seed: seed.value === '' ? null : Number(seed.value),
    })
    await refreshJobs()
  })
}

async function retry(id: string): Promise<void> {
  await props.execute(async () => {
    await client.post(api(`/generation-jobs/${id}/retry`))
    await refreshJobs()
  })
}

async function download(job: Job, file: Job['result_files'][number]): Promise<void> {
  try {
    await window.directorDesktop.saveResult(api(`/generation-jobs/${job.id}/files/${file.index}`), file.filename)
  } catch (error) {
    props.report(error)
  }
}
</script>

<template>
  <div class="page">
    <div class="page-title"><div><span class="eyebrow">04 / GPU GENERATION</span>
      <h1>视频生成与任务追踪</h1><p>FastAPI 统一提交 ComfyUI 工作流；关掉 Electron 后，云端 Worker 仍可处理任务。</p></div></div>
    <div v-if="!projectId" class="empty">请选择项目。</div>
    <template v-else>
      <section class="panel">
        <h2><Play :size="18" />创建视频任务</h2>
        <div class="form-grid">
          <label>选择分镜<select v-model="shotId">
            <option v-for="item in shots" :key="item.id" :value="item.id">{{ item.ordinal }}. {{ item.narrative }}</option>
          </select></label>
          <label>已审核视频提示词<select v-model="promptId">
            <option value="">请选择审核通过的提示词</option>
            <option v-for="prompt in prompts" :key="prompt.id" :value="prompt.id">版本 {{ prompt.version }}</option>
          </select></label>
          <label>工作流<select v-model="workflowId">
            <option v-for="workflow in workflows" :key="workflow.id" :value="workflow.id">
              {{ workflow.name }} {{ workflow.ready ? '' : '（未导入API JSON）' }}
            </option>
          </select></label>
          <label>GPU 节点<select v-model="nodeId">
            <option value="">按配置选用首个可用节点</option>
            <option v-for="node in nodes.filter(item => item.enabled)" :key="node.id" :value="node.id">{{ node.name }}</option>
          </select></label>
          <label>随机种子<input v-model="seed" placeholder="可选，留空由模型决定" type="number" min="0" /></label>
        </div>
        <button class="primary" :disabled="busy || !shotId || !promptId || !workflows.find(item => item.id === workflowId)?.ready"
          @click="submit">提交 GPU 生成任务</button>
        <p v-if="!workflows.some(item => item.ready)" class="muted">尚未导入可执行 API 工作流。请将 ComfyUI 的 API 格式 JSON 放入服务器 workflows 目录并核对映射。</p>
      </section>
      <section class="panel">
        <div class="panel-top"><h2>生成任务</h2><button @click="refreshJobs"><RefreshCw :size="15" />刷新</button></div>
        <div v-for="job in jobs" :key="job.id" class="job-row">
          <div><strong>{{ job.workflow_id }}</strong> <span :class="['status', job.status]">{{ job.status }}</span>
            <small>任务 {{ job.id.slice(0, 8) }} · GPU {{ job.node_id }}</small>
            <p v-if="job.error" class="error-text">{{ job.error }}</p></div>
          <div class="row-actions">
            <button v-if="job.status === 'failed'" @click="retry(job.id)">重试</button>
            <button v-for="file in job.result_files" :key="file.index" @click="download(job, file)">
              <Download :size="15" />下载 {{ file.filename }}
            </button>
          </div>
        </div>
        <p v-if="!jobs.length" class="muted">暂无生成任务。</p>
      </section>
    </template>
  </div>
</template>

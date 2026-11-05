<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Clapperboard, FolderOpen, Images, Layers3, Server, WandSparkles, RefreshCw } from 'lucide-vue-next'
import { api, client, type Project, type Script } from './lib/api'
import type { SharedProps } from './lib/shared'
import ProjectsPage from './pages/ProjectsPage.vue'
import AssetsPage from './pages/AssetsPage.vue'
import StoryboardsPage from './pages/StoryboardsPage.vue'
import JobsPage from './pages/JobsPage.vue'
import SettingsPage from './pages/SettingsPage.vue'

type Tab = 'scripts' | 'assets' | 'shots' | 'jobs' | 'settings'

const navigation = [
  { id: 'scripts', label: '剧本与项目', icon: FolderOpen },
  { id: 'assets', label: '人物 · 场景 · 道具', icon: Images },
  { id: 'shots', label: '智能分镜', icon: Layers3 },
  { id: 'jobs', label: '视频生成', icon: Clapperboard },
  { id: 'settings', label: '连接设置', icon: Server },
] as const

const tab = ref<Tab>('scripts')
const projects = ref<Project[]>([])
const scripts = ref<Script[]>([])
const projectId = ref('')
const scriptId = ref('')
const message = ref('')
const online = ref(false)
const busy = ref(false)

function report(error: unknown): void {
  message.value = error instanceof Error ? error.message : String(error)
}

async function refreshProjects(): Promise<void> {
  try {
    const found = await client.get<Project[]>(api('/projects'))
    projects.value = found
    projectId.value = found.some(project => project.id === projectId.value)
      ? projectId.value : (found[0]?.id ?? '')
    online.value = true
  } catch (error) {
    online.value = false
    report(error)
  }
}

async function refreshScripts(): Promise<void> {
  if (!projectId.value) {
    scripts.value = []
    scriptId.value = ''
    return
  }
  try {
    const rows = await client.get<Script[]>(api(`/projects/${projectId.value}/scripts`))
    scripts.value = rows
    scriptId.value = rows.some(script => script.id === scriptId.value)
      ? scriptId.value : (rows[0]?.id ?? '')
  } catch (error) {
    report(error)
  }
}

async function execute<T>(action: () => Promise<T>): Promise<T | undefined> {
  message.value = ''
  busy.value = true
  try {
    return await action()
  } catch (error) {
    report(error)
    return undefined
  } finally {
    busy.value = false
  }
}

const project = computed(() => projects.value.find(item => item.id === projectId.value))
const script = computed(() => scripts.value.find(item => item.id === scriptId.value))
const shared = computed<SharedProps>(() => ({
  projectId: projectId.value, scriptId: scriptId.value, execute, report, busy: busy.value,
}))

watch(projectId, () => { void refreshScripts() })
onMounted(() => { void refreshProjects() })
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-icon"><WandSparkles :size="23" /></div>
        <div><strong>AI Director</strong><small>STORY STUDIO / V1.1</small></div>
      </div>
      <div class="nav-caption">创作工作台</div>
      <nav>
        <button v-for="item in navigation" :key="item.id"
          :class="['nav-button', { active: tab === item.id }]"
          @click="tab = item.id">
          <component :is="item.icon" :size="18" /><span>{{ item.label }}</span>
        </button>
      </nav>
      <div class="sidebar-foot">
        <div :class="['indicator', { online }]" />
        <div><strong>{{ online ? 'FastAPI 已连接' : '服务未连接' }}</strong>
          <small>{{ online ? '业务处理运行在云端' : '请配置 API 地址与令牌' }}</small></div>
      </div>
    </aside>
    <main class="content">
      <header class="topbar">
        <div class="header-left">
          <span class="eyebrow">PROJECT WORKSPACE</span>
          <div class="toolbar-row">
            <select v-model="projectId" aria-label="选择项目">
              <option value="">选择剧本项目</option>
              <option v-for="item in projects" :key="item.id" :value="item.id">{{ item.title }}</option>
            </select>
            <select v-model="scriptId" aria-label="选择剧本版本" :disabled="!projectId">
              <option value="">选择剧本</option>
              <option v-for="item in scripts" :key="item.id" :value="item.id">剧本 V{{ item.version }}</option>
            </select>
          </div>
        </div>
        <button class="icon-button" title="刷新云端项目" @click="refreshProjects(); refreshScripts()">
          <RefreshCw :size="17" />
        </button>
      </header>
      <div v-if="message" class="notice" role="alert">
        <span>{{ message }}</span><button @click="message = ''">关闭</button>
      </div>
      <section class="workspace">
        <ProjectsPage v-if="tab === 'scripts'" v-bind="shared" :project="project" :script="script"
          :on-projects-change="refreshProjects" :on-scripts-change="refreshScripts"
          :on-script-created="id => scriptId = id" />
        <AssetsPage v-else-if="tab === 'assets'" v-bind="shared" />
        <StoryboardsPage v-else-if="tab === 'shots'" v-bind="shared" />
        <JobsPage v-else-if="tab === 'jobs'" v-bind="shared" />
        <SettingsPage v-else :report="report" :on-connected="refreshProjects" />
      </section>
    </main>
  </div>
</template>

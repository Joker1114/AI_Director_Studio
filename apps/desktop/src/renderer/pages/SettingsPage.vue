<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Cloud, KeyRound, ShieldCheck } from 'lucide-vue-next'
import { api, client } from '../lib/api'

const props = defineProps<{
  report: (error: unknown) => void
  onConnected: () => Promise<void>
}>()

const url = ref('')
const token = ref('')
const saved = ref(false)
const status = ref('未测试')
const configured = ref(false)

onMounted(() => {
  window.directorDesktop.getSettings().then(settings => {
    url.value = settings.apiBaseUrl
    configured.value = settings.tokenConfigured
  }).catch(props.report)
})

async function save(): Promise<void> {
  try {
    await window.directorDesktop.setEndpoint(url.value)
    if (token.value) {
      await window.directorDesktop.setToken(token.value)
      configured.value = true
      token.value = ''
    }
    saved.value = true
    await props.onConnected()
  } catch (error) {
    props.report(error)
  }
}

async function test(): Promise<void> {
  try {
    const data = await client.get<{ status: string }>(api('/health'))
    status.value = data.status === 'ok' ? '连接成功' : '服务未就绪'
  } catch (error) {
    props.report(error)
    status.value = '连接失败'
  }
}
</script>

<template>
  <div class="page narrow">
    <div class="page-title"><div><span class="eyebrow">05 / CONNECTION SETTINGS</span>
      <h1>连接设置</h1><p>桌面端只需要配置 FastAPI 地址；Qwen 密钥与 GPU 节点均由云端服务配置。</p></div></div>
    <section class="panel">
      <h2><Cloud :size="18" />FastAPI 云端服务</h2>
      <label>服务器地址（HTTPS）<input v-model="url" placeholder="https://api.example.com" @input="saved = false" /></label>
      <p class="muted">只填写服务根地址；桌面端自动使用 /api/v1/ 接口。仅 localhost 允许使用 HTTP。</p>
      <label><KeyRound :size="14" />访问令牌<input v-model="token" type="password"
        :placeholder="configured ? '已配置；留空保持不变' : '填写服务器 APP_API_TOKEN'" autocomplete="off" /></label>
      <p class="muted">令牌由 Electron 主进程保管；系统加密功能可用时保存为加密文件，不暴露给渲染页面。</p>
      <div class="row-actions"><button class="primary" @click="save">保存连接配置</button>
        <button @click="test">测试连接</button></div>
      <div class="info-line"><strong>连接测试</strong><span>{{ status }}</span></div>
      <p v-if="saved" class="success-text">设置已保存。新请求将连接新的云端服务。</p>
    </section>
    <section class="panel subtle">
      <h2><ShieldCheck :size="18" />三端部署原则</h2>
      <div class="info-line"><strong>Electron</strong><span>用户电脑，负责界面和本地文件交互</span></div>
      <div class="info-line"><strong>FastAPI</strong><span>云端，负责业务、权限、Qwen 和任务管理</span></div>
      <div class="info-line"><strong>ComfyUI</strong><span>独立 GPU 服务器，由 FastAPI 后端访问</span></div>
    </section>
  </div>
</template>

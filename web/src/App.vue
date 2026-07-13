<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { FolderOpened as Archive, Box, Check, Collection, DataAnalysis, Document, Files, Fold, Grid, Lock, Menu as MenuIcon, Operation, Refresh, Search, Setting, Timer, UploadFilled, User } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, clearToken, savedToken, saveToken } from './api'
import { SAMPLE_FEISHU, SAMPLE_TEXT } from './sample'
import type { Asset, AuditEvent, DocumentSummary, ImportForm, Job, Overview } from './types'

type Page = 'dashboard' | 'import' | 'documents' | 'jobs' | 'assets' | 'schema' | 'audit' | 'settings'
const page = ref<Page>((location.hash.slice(1) as Page) || 'dashboard')
const authenticated = ref(false), loginToken = ref(savedToken()), loginBusy = ref(false), loading = ref(false), collapsed = ref(false)
const overview = ref<Overview | null>(null), documents = ref<DocumentSummary[]>([]), documentsTotal = ref(0)
const jobs = ref<Job[]>([]), assets = ref<Asset[]>([]), audit = ref<AuditEvent[]>([])
const schema = ref<Record<string, unknown> | null>(null), runtime = ref<Record<string, unknown> | null>(null)
const query = ref(''), statusFilter = ref(''), selectedDocument = ref<Record<string, any> | null>(null), drawerOpen = ref(false)
const rawPayload = ref(SAMPLE_TEXT), preview = ref<Record<string, unknown> | null>(null), importBusy = ref(false)
const feishuConfig = ref<Record<string, any> | null>(null), feishuSpaces = ref<Record<string, any>[]>([]), feishuNodes = ref<Record<string, any>[]>([])
const selectedSpace = ref(''), botBusy = ref(false), showDebugImport = ref(false)
const parentNodeToken = ref(''), folderTrail = ref<Array<{ token: string; title: string }>>([])
const botConfig = reactive({ app_id: '', app_secret: '', brand: 'feishu', base_url: '' })
const exclusions = ref<Record<string, any> | null>(null), exclusionPatterns = ref(''), exclusionBusy = ref(false)
const form = reactive<ImportForm>({ document_id: 'doc-demo-001', revision: '1', title: 'Search reliability proposal', space_id: 'engineering', path: ['Engineering', 'Search'], source_url: '', permissions: { visibility: 'organization' }, payload: SAMPLE_FEISHU })

const navigation = [
  { id: 'dashboard', label: '总览', icon: DataAnalysis }, { id: 'import', label: '飞书导入', icon: UploadFilled },
  { id: 'documents', label: '文档库', icon: Collection }, { id: 'jobs', label: '同步任务', icon: Timer },
  { id: 'assets', label: '资源文件', icon: Files }, { id: 'schema', label: '文档模型', icon: Operation },
  { id: 'audit', label: '审计日志', icon: Document }, { id: 'settings', label: '系统设置', icon: Setting },
] as const
const pageTitle = computed(() => navigation.find(item => item.id === page.value)?.label || '总览')
const pageCaption = computed(() => ({ dashboard: '知识同步系统的运行态势', import: '从已配置的飞书机器人导入知识', documents: '统一管理开放文档模型', jobs: '追踪每一次同步与失败原因', assets: '图片和附件的下载队列', schema: '查看当前 OKD JSON Schema', audit: '关键管理操作的不可变记录', settings: '飞书机器人、运行环境与访问控制' }[page.value]))
const fmt = (value?: string) => value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(value)) : '—'
const exclusionHint = (row: Record<string, any>) => row.exclusion ? `命中 ${row.exclusion.pattern}（${row.exclusion.field}）` : ''
function navigate(next: Page) { page.value = next; location.hash = next }

async function login() {
  loginBusy.value = true; saveToken(loginToken.value.trim())
  try { await api('/api/admin/session'); authenticated.value = true; await loadPage() }
  catch (error) { clearToken(); authenticated.value = false; ElMessage.error((error as Error).message) }
  finally { loginBusy.value = false }
}
function logout() { clearToken(); authenticated.value = false; loginToken.value = '' }
async function loadPage() {
  if (!authenticated.value) return; loading.value = true
  try {
    if (page.value === 'dashboard') overview.value = await api('/api/admin/overview')
    if (page.value === 'import' || page.value === 'settings') {
      const config = await api<Record<string, any>>('/api/admin/feishu/config')
      feishuConfig.value = config; botConfig.app_id = config.app_id || ''; botConfig.brand = config.brand || 'feishu'; botConfig.base_url = config.base_url || ''
    }
    if (page.value === 'documents') { const params = new URLSearchParams({ query: query.value, status: statusFilter.value }); const result = await api<{ items: DocumentSummary[]; total: number }>(`/api/admin/documents?${params}`); documents.value = result.items; documentsTotal.value = result.total }
    if (page.value === 'jobs') jobs.value = await api('/api/admin/jobs')
    if (page.value === 'assets') assets.value = await api('/api/admin/assets')
    if (page.value === 'schema') schema.value = await api('/api/admin/schema')
    if (page.value === 'audit') audit.value = await api('/api/admin/audit')
    if (page.value === 'settings') { runtime.value = await api('/api/admin/runtime'); exclusions.value = await api('/api/admin/exclusions'); exclusionPatterns.value = (exclusions.value?.patterns || []).join('\n') }
  } catch (error) { ElMessage.error((error as Error).message) } finally { loading.value = false }
}
async function saveBotConfig() {
  botBusy.value = true
  try { feishuConfig.value = await api('/api/admin/feishu/config', { method: 'POST', body: JSON.stringify(botConfig) }); botConfig.app_secret = ''; ElMessage.success('飞书机器人配置已保存') }
  catch (error) { ElMessage.error((error as Error).message) } finally { botBusy.value = false }
}
async function connectBot() {
  botBusy.value = true
  try { const result = await api<Record<string, any>>('/api/admin/feishu/check', { method: 'POST' }); ElMessage.success(result.message); await loadSpaces() }
  catch (error) { ElMessage.error((error as Error).message) } finally { botBusy.value = false }
}
async function loadSpaces() {
  feishuSpaces.value = await api('/api/admin/feishu/spaces')
  if (!selectedSpace.value && feishuSpaces.value.length) selectedSpace.value = String(feishuSpaces.value[0].space_id || feishuSpaces.value[0].id || '')
}
async function selectSpace() { parentNodeToken.value = ''; folderTrail.value = []; await loadNodes() }
async function loadNodes() {
  if (!selectedSpace.value) return
  botBusy.value = true
  try {
    const params = new URLSearchParams({ parent_node_token: parentNodeToken.value, recursive: 'false', limit: '200' })
    const nodes = await api<Record<string, any>[]>(`/api/admin/feishu/spaces/${encodeURIComponent(selectedSpace.value)}/nodes?${params}`)
    const prefix = folderTrail.value.map(item => item.title)
    feishuNodes.value = nodes.map(node => ({ ...node, path: [...prefix, node.title || '未命名节点'] }))
  }
  catch (error) { ElMessage.error((error as Error).message) } finally { botBusy.value = false }
}
async function openNode(node: Record<string, any>) {
  if (node.syncable) return importNode(node)
  if (node.has_child && node.node_token) { parentNodeToken.value = String(node.node_token); folderTrail.value.push({ token: parentNodeToken.value, title: String(node.title || '未命名目录') }); await loadNodes() }
}
async function returnToRoot() { parentNodeToken.value = ''; folderTrail.value = []; await loadNodes() }
async function importNode(node: Record<string, any>) {
  botBusy.value = true
  try {
    const result = await api<Record<string, any>>('/api/admin/feishu/import', { method: 'POST', body: JSON.stringify({ document_id: node.obj_token, node_token: node.node_token, title: node.title, space_id: node.space_id || selectedSpace.value, revision: node.obj_edit_time || 'latest', path: node.path || [node.title], permissions: { visibility: 'organization' } }) })
    ElMessage.success(`已导入「${node.title}」`); preview.value = await api(`/api/admin/documents/${encodeURIComponent(result.document.id)}`)
  } catch (error) { ElMessage.error((error as Error).message) } finally { botBusy.value = false }
}
async function syncSpace() {
  if (!selectedSpace.value) return
  await ElMessageBox.confirm('将通过飞书机器人递归拉取并导入当前知识空间中的 Docx 文档，继续吗？', '同步知识空间', { type: 'warning' })
  botBusy.value = true
  try { const result = await api<Record<string, any>>('/api/admin/feishu/sync', { method: 'POST', body: JSON.stringify({ space_id: selectedSpace.value, recursive: true, limit: 500 }) }); ElMessage.success(`同步完成：${result.imported} 篇导入，${result.excluded || 0} 篇被黑名单排除，${result.failed.length} 篇失败`) }
  catch (error) { ElMessage.error((error as Error).message) } finally { botBusy.value = false }
}
async function saveExclusions() {
  exclusionBusy.value = true
  try {
    const patterns = exclusionPatterns.value.split(/\r?\n/).map(item => item.trim()).filter(Boolean)
    exclusions.value = await api('/api/admin/exclusions', { method: 'PUT', body: JSON.stringify({ enabled: exclusions.value?.enabled ?? true, patterns }) })
    exclusionPatterns.value = (exclusions.value?.patterns || []).join('\n'); ElMessage.success('同步黑名单已保存')
  } catch (error) { ElMessage.error((error as Error).message) } finally { exclusionBusy.value = false }
}
async function runConversion(persist: boolean) {
  importBusy.value = true
  try {
    form.payload = JSON.parse(rawPayload.value)
    const result = await api<Record<string, any>>(persist ? '/api/admin/import/feishu' : '/api/convert/feishu', { method: 'POST', body: JSON.stringify(form) })
    preview.value = persist ? await api(`/api/admin/documents/${encodeURIComponent(result.document.id)}`) : result
    ElMessage.success(persist ? '文档已校验并写入文档库' : '转换预览已生成，尚未入库')
  } catch (error) { ElMessage.error((error as Error).message) } finally { importBusy.value = false }
}
async function inspectDocument(row: DocumentSummary) { selectedDocument.value = await api(`/api/admin/documents/${encodeURIComponent(row.id)}`); drawerOpen.value = true }
async function archiveDocument(row: DocumentSummary) { await ElMessageBox.confirm(`归档「${row.title || row.id}」？原始快照仍会保留。`, '确认归档', { type: 'warning' }); await api(`/api/admin/documents/${encodeURIComponent(row.id)}/archive`, { method: 'POST' }); ElMessage.success('文档已归档'); await loadPage() }
function downloadJson() { if (!selectedDocument.value) return; const blob = new Blob([JSON.stringify(selectedDocument.value, null, 2)], { type: 'application/json' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'okd-document.json'; link.click(); URL.revokeObjectURL(link.href) }
watch(page, loadPage); watch([query, statusFilter], () => { if (page.value === 'documents') loadPage() })
window.addEventListener('hashchange', () => { page.value = (location.hash.slice(1) as Page) || 'dashboard' })
onMounted(async () => { if (savedToken()) await login() })
</script>

<template>
  <div v-if="!authenticated" class="login-shell">
    <section class="login-story"><div class="brand-mark"><Box :size="28" /><span>OKD</span></div><div><p class="eyebrow">OPEN KNOWLEDGE DOCUMENT</p><h1>让知识从飞书流动，<br>而不被飞书锁住。</h1><p>统一文档模型、增量同步、资源归档和审计追踪，全部运行在你自己的基础设施中。</p></div><div class="login-status"><span class="pulse"></span> 本地优先 · 开放模型 · 可审计</div></section>
    <section class="login-panel"><div class="login-card"><div class="login-icon"><Lock /></div><h2>管理员登录</h2><p>输入容器环境变量 OKD_ADMIN_TOKEN 配置的访问令牌。</p><el-input v-model="loginToken" size="large" type="password" show-password placeholder="Administrator token" @keyup.enter="login" /><el-button type="primary" size="large" :loading="loginBusy" @click="login">进入控制台</el-button><small>本地 Docker 默认令牌：change-me-local</small></div></section>
  </div>

  <el-container v-else class="admin-shell">
    <el-aside :width="collapsed ? '72px' : '248px'" class="sidebar"><div class="sidebar-brand"><div class="brand-cube"><Box /></div><div v-show="!collapsed"><strong>OKD Admin</strong><span>OPEN DOCUMENT LAYER</span></div></div><el-menu :default-active="page" :collapse="collapsed" @select="navigate($event as Page)"><el-menu-item v-for="item in navigation" :key="item.id" :index="item.id"><el-icon><component :is="item.icon" /></el-icon><template #title>{{ item.label }}</template></el-menu-item></el-menu><div class="sidebar-foot"><span class="status-dot"></span><div v-show="!collapsed"><strong>服务正常</strong><small>Schema v0.1.0</small></div></div></el-aside>
    <el-container><el-header class="topbar"><el-button text circle @click="collapsed = !collapsed"><el-icon><Fold v-if="!collapsed" /><MenuIcon v-else /></el-icon></el-button><div class="breadcrumbs">Open Knowledge Document <b>/</b> {{ pageTitle }}</div><div class="top-actions"><el-button text circle :loading="loading" @click="loadPage"><el-icon><Refresh /></el-icon></el-button><div class="user-chip"><el-icon><User /></el-icon><span>Administrator</span></div></div></el-header>
      <el-main v-loading="loading" class="main-content"><header class="page-header"><div><p class="eyebrow">CONTROL CENTER</p><h1>{{ pageTitle }}</h1><p>{{ pageCaption }}</p></div><el-button v-if="page === 'dashboard' || page === 'documents'" type="primary" :icon="UploadFilled" @click="navigate('import')">导入飞书文档</el-button></header>

        <template v-if="page === 'dashboard'"><div class="metric-grid"><article class="metric-card"><span>文档总数</span><strong>{{ overview?.documents ?? 0 }}</strong><small>{{ overview?.active_documents ?? 0 }} 篇处于活跃状态</small></article><article class="metric-card"><span>资源文件</span><strong>{{ overview?.assets ?? 0 }}</strong><small>{{ overview?.pending_assets ?? 0 }} 个等待下载</small></article><article class="metric-card"><span>转换警告</span><strong>{{ overview?.warnings ?? 0 }}</strong><small>未知块会保留源数据</small></article><article class="metric-card danger"><span>失败任务</span><strong>{{ overview?.failed_jobs ?? 0 }}</strong><small>需要人工检查</small></article></div>
          <div class="dashboard-grid"><section class="panel"><div class="panel-head"><div><h3>最近文档</h3><p>最后写入开放文档层的内容</p></div><el-button link @click="navigate('documents')">查看全部</el-button></div><el-table :data="overview?.recent_documents || []"><el-table-column prop="title" label="标题" min-width="220"><template #default="scope"><div class="title-cell"><el-icon><Document /></el-icon><div><strong>{{ scope.row.title || '未命名文档' }}</strong><small>{{ scope.row.space_id || '未分配空间' }}</small></div></div></template></el-table-column><el-table-column prop="revision" label="版本" width="90"/><el-table-column label="更新时间" width="170"><template #default="scope">{{ fmt(scope.row.updated_at) }}</template></el-table-column></el-table></section>
            <section class="panel"><div class="panel-head"><div><h3>同步任务</h3><p>最近的转换执行记录</p></div><el-button link @click="navigate('jobs')">任务中心</el-button></div><div class="job-feed"><div v-for="job in overview?.recent_jobs" :key="job.id" class="job-row"><span :class="['job-indicator', job.status]"></span><div><strong>{{ job.source_document_id }}</strong><small>{{ fmt(job.started_at) }}</small></div><el-tag :type="job.status === 'failed' ? 'danger' : job.status === 'running' ? 'warning' : 'success'" effect="plain">{{ job.status }}</el-tag></div><el-empty v-if="!overview?.recent_jobs.length" description="还没有同步任务" :image-size="64" /></div></section></div></template>

        <template v-if="page === 'import'">
          <section v-if="!feishuConfig?.configured" class="panel bot-setup">
            <div><p class="eyebrow">BOT REQUIRED</p><h3>尚未配置飞书机器人</h3><p>请先在系统设置中填写 App ID 与 App Secret，配置完成后再回来选择知识空间。</p></div>
            <el-button type="primary" :icon="Setting" @click="navigate('settings')">前往系统设置</el-button>
          </section>
          <template v-else>
            <section class="panel source-browser">
              <div class="panel-head"><div><p class="eyebrow">BOT SOURCE</p><h3>从飞书知识库导入</h3><p>{{ feishuConfig.app_id }} · tenant_access_token · {{ feishuConfig.base_url }}</p></div><div><el-button :loading="botBusy" @click="connectBot">检测连接</el-button><el-button type="primary" :loading="botBusy" @click="syncSpace">同步当前空间</el-button></div></div>
              <div class="source-toolbar"><el-select v-model="selectedSpace" filterable placeholder="先检测连接并选择知识空间" @change="selectSpace"><el-option v-for="space in feishuSpaces" :key="space.space_id || space.id" :label="space.name || space.title || space.space_id" :value="space.space_id || space.id"/></el-select><el-button v-if="parentNodeToken" @click="returnToRoot">返回根目录</el-button><el-button :disabled="!selectedSpace" :loading="botBusy" @click="loadNodes">刷新当前目录</el-button><span>{{ folderTrail.map(item => item.title).join(' / ') || '根目录' }} · {{ feishuNodes.length }} 个节点</span></div>
              <el-table :data="feishuNodes" stripe max-height="460"><el-table-column label="知识库路径" min-width="300"><template #default="scope"><div class="title-cell"><el-icon><Document /></el-icon><div><strong>{{ scope.row.title || '未命名节点' }}</strong><small>{{ (scope.row.path || []).join(' / ') }}</small></div></div></template></el-table-column><el-table-column prop="obj_type" label="类型" width="100"/><el-table-column prop="obj_edit_time" label="飞书版本" width="140"/><el-table-column label="状态" width="110"><template #default="scope"><el-tag :type="scope.row.excluded ? 'danger' : scope.row.syncable ? 'success' : 'info'" effect="plain">{{ scope.row.excluded ? '黑名单' : scope.row.syncable ? '可同步' : '跳过' }}</el-tag></template></el-table-column><el-table-column label="操作" width="110"><template #default="scope"><el-tooltip :content="exclusionHint(scope.row)" :disabled="!scope.row.excluded"><el-button link type="primary" :disabled="!scope.row.syncable && !scope.row.has_child" :loading="botBusy" @click="openNode(scope.row)">{{ scope.row.syncable ? '导入' : scope.row.has_child ? '打开' : '不可用' }}</el-button></el-tooltip></template></el-table-column></el-table>
              <el-empty v-if="!feishuNodes.length" description="检测机器人连接，然后选择一个知识空间" :image-size="70" />
            </section>
          </template>
          <section class="panel debug-toggle"><div><strong>高级调试：手工 Block JSON</strong><p>仅用于转换器开发和问题复现，不是正式导入入口。</p></div><el-switch v-model="showDebugImport" /></section>
          <div v-if="showDebugImport" class="import-grid"><section class="panel form-panel"><div class="panel-head"><div><h3>调试来源信息</h3><p>直接提交飞书 Block API JSON</p></div><el-tag effect="plain">DEBUG</el-tag></div><el-form label-position="top"><div class="form-two"><el-form-item label="文档 ID"><el-input v-model="form.document_id" /></el-form-item><el-form-item label="版本号"><el-input v-model="form.revision" /></el-form-item></div><el-form-item label="标题"><el-input v-model="form.title" /></el-form-item><el-form-item label="知识空间"><el-input v-model="form.space_id" /></el-form-item><el-form-item label="飞书 Block API JSON"><el-input v-model="rawPayload" type="textarea" :rows="13" spellcheck="false" class="code-input" /></el-form-item><div class="form-actions"><el-button :loading="importBusy" @click="runConversion(false)">仅转换预览</el-button><el-button type="primary" :loading="importBusy" :icon="Check" @click="runConversion(true)">校验并写入文档库</el-button></div></el-form></section><section class="panel preview-panel"><div class="panel-head"><div><h3>OKD 输出</h3><p>规范化 JSON</p></div><el-tag :type="preview ? 'success' : 'info'" effect="plain">{{ preview ? 'VALID' : 'WAITING' }}</el-tag></div><pre v-if="preview">{{ JSON.stringify(preview, null, 2) }}</pre><el-empty v-else description="运行转换后在这里检查结果" /></section></div>
        </template>

        <section v-if="page === 'documents'" class="panel"><div class="toolbar"><el-input v-model="query" :prefix-icon="Search" clearable placeholder="搜索标题、文档 ID"/><el-select v-model="statusFilter" clearable placeholder="全部状态"><el-option label="活跃" value="active"/><el-option label="已归档" value="archived"/></el-select><span class="record-count">{{ documentsTotal }} 条记录</span></div><el-table :data="documents" stripe><el-table-column label="文档" min-width="280"><template #default="scope"><div class="title-cell"><div class="file-glyph">OKD</div><div><strong>{{ scope.row.title || '未命名文档' }}</strong><small>{{ scope.row.id }}</small></div></div></template></el-table-column><el-table-column prop="space_id" label="空间" width="140"/><el-table-column prop="revision" label="版本" width="80"/><el-table-column label="资源 / 警告" width="130"><template #default="scope">{{ scope.row.asset_count }} / <span :class="{ warn: scope.row.warning_count }">{{ scope.row.warning_count }}</span></template></el-table-column><el-table-column label="状态" width="100"><template #default="scope"><el-tag :type="scope.row.status === 'active' ? 'success' : 'info'" effect="plain">{{ scope.row.status }}</el-tag></template></el-table-column><el-table-column label="更新时间" width="170"><template #default="scope">{{ fmt(scope.row.updated_at) }}</template></el-table-column><el-table-column label="操作" width="150" fixed="right"><template #default="scope"><el-button link type="primary" @click="inspectDocument(scope.row)">查看</el-button><el-button v-if="scope.row.status !== 'archived'" link type="danger" @click="archiveDocument(scope.row)">归档</el-button></template></el-table-column></el-table></section>
        <section v-if="page === 'jobs'" class="panel"><el-table :data="jobs" stripe><el-table-column label="状态" width="110"><template #default="scope"><el-tag :type="scope.row.status === 'failed' ? 'danger' : scope.row.status === 'running' ? 'warning' : 'success'">{{ scope.row.status }}</el-tag></template></el-table-column><el-table-column prop="source_document_id" label="飞书文档" min-width="180"/><el-table-column prop="kind" label="任务类型" width="150"/><el-table-column prop="document_id" label="OKD 文档" min-width="220"/><el-table-column prop="warning_count" label="警告" width="80"/><el-table-column label="开始时间" width="180"><template #default="scope">{{ fmt(scope.row.started_at) }}</template></el-table-column><el-table-column prop="error" label="失败原因" min-width="220" show-overflow-tooltip/></el-table></section>
        <section v-if="page === 'assets'" class="panel"><div class="notice"><el-icon><Archive /></el-icon><div><strong>资源下载采用独立状态机</strong><p>转换时先登记 token；下载器接入飞书授权后再写入对象存储和 SHA-256。</p></div></div><el-table :data="assets" stripe><el-table-column prop="filename" label="文件名" min-width="180"><template #default="scope">{{ scope.row.filename || scope.row.source_asset_id }}</template></el-table-column><el-table-column prop="media_type" label="媒体类型" width="180"/><el-table-column prop="document_id" label="所属文档" min-width="220"/><el-table-column label="下载状态" width="120"><template #default="scope"><el-tag :type="scope.row.download_status === 'downloaded' ? 'success' : 'warning'" effect="plain">{{ scope.row.download_status }}</el-tag></template></el-table-column><el-table-column prop="storage_ref" label="存储位置" min-width="220"/></el-table></section>
        <section v-if="page === 'schema'" class="schema-grid"><div class="panel schema-summary"><h3>Open Knowledge Document</h3><p>当前后台在每次正式导入前，使用 Draft 2020-12 对转换结果做完整校验。</p><dl><div><dt>Schema ID</dt><dd>{{ schema?.$id }}</dd></div><div><dt>版本</dt><dd>0.1.0</dd></div><div><dt>格式</dt><dd>JSON Schema 2020-12</dd></div><div><dt>核心对象</dt><dd>source · metadata · document · assets</dd></div></dl></div><div class="panel schema-code"><pre>{{ JSON.stringify(schema, null, 2) }}</pre></div></section>
        <section v-if="page === 'audit'" class="panel"><el-table :data="audit" stripe><el-table-column prop="id" label="#" width="70"/><el-table-column prop="event_type" label="事件" width="190"/><el-table-column prop="actor" label="操作者" width="120"/><el-table-column prop="target_id" label="对象" min-width="240"/><el-table-column label="详情" min-width="260"><template #default="scope"><code>{{ JSON.stringify(scope.row.detail) }}</code></template></el-table-column><el-table-column label="时间" width="180"><template #default="scope">{{ fmt(scope.row.created_at) }}</template></el-table-column></el-table></section>
        <template v-if="page === 'settings'">
          <section class="panel bot-settings"><div class="panel-head"><div><p class="eyebrow">FEISHU CONNECTOR</p><h3>飞书机器人</h3><p>凭证仅保存在服务端 /data/feishu-config.json，浏览器不会读取已保存的 App Secret。</p></div><el-tag :type="feishuConfig?.configured ? 'success' : 'warning'" effect="plain">{{ feishuConfig?.configured ? 'CONFIGURED' : 'NOT CONNECTED' }}</el-tag></div><el-form label-position="top"><div class="form-two"><el-form-item label="App ID"><el-input v-model="botConfig.app_id" placeholder="cli_xxxxxxxxxx" /></el-form-item><el-form-item :label="feishuConfig?.app_secret_configured ? 'App Secret（留空则保持原值）' : 'App Secret'"><el-input v-model="botConfig.app_secret" type="password" show-password /></el-form-item></div><div class="form-two"><el-form-item label="平台"><el-select v-model="botConfig.brand"><el-option label="飞书（中国）" value="feishu"/><el-option label="Lark（国际）" value="lark"/></el-select></el-form-item><el-form-item label="OpenAPI Base URL（可选）"><el-input v-model="botConfig.base_url" /></el-form-item></div><div class="form-actions"><el-button :disabled="!feishuConfig?.configured" :loading="botBusy" @click="connectBot">检测连接</el-button><el-button type="primary" :loading="botBusy" @click="saveBotConfig">保存机器人配置</el-button></div></el-form></section>
          <section class="panel exclusion-settings"><div class="panel-head"><div><p class="eyebrow">IMPORT POLICY</p><h3>同步黑名单</h3><p>匹配的 Wiki 节点会在预览中标红，并在单篇导入与整空间同步时跳过。</p></div><el-switch v-if="exclusions" v-model="exclusions.enabled" active-text="已启用" /></div><el-form label-position="top"><el-form-item label="排除规则（每行一条）"><el-input v-model="exclusionPatterns" type="textarea" :rows="7" class="code-input light" placeholder="Archive&#10;*/草稿/*&#10;re:^内部-" /></el-form-item><div class="exclusion-help"><span>支持普通包含、* / ? 通配符、re: 正则</span><div><code v-for="field in exclusions?.fields || []" :key="field">{{ field }}</code></div></div><div class="form-actions"><el-button type="primary" :loading="exclusionBusy" @click="saveExclusions">保存黑名单</el-button></div></el-form></section>
          <div class="settings-grid"><section class="panel"><div class="panel-head"><div><h3>运行环境</h3><p>当前服务的持久化与版本信息</p></div><el-icon class="big-icon"><Grid /></el-icon></div><dl class="settings-list"><div v-for="(value, key) in runtime" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></div></dl></section><section class="panel danger-zone"><h3>管理员会话</h3><p>令牌只存放在当前浏览器标签页的 sessionStorage 中，关闭标签页后自动清除。</p><el-button type="danger" plain @click="logout">退出并清除令牌</el-button></section></div>
        </template>
      </el-main>
    </el-container>
  </el-container>
  <el-drawer v-model="drawerOpen" size="55%" title="文档详情"><template #header><div class="drawer-title"><div><strong>{{ selectedDocument?.metadata?.title || selectedDocument?.id }}</strong><small>规范化 OKD JSON</small></div><el-button type="primary" plain @click="downloadJson">下载 JSON</el-button></div></template><pre class="drawer-json">{{ JSON.stringify(selectedDocument, null, 2) }}</pre></el-drawer>
</template>

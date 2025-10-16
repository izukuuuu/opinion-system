<template>
  <div class="space-y-8">
    <section class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.4em] text-slate-400">系统设置</p>
        <h2 class="text-2xl font-semibold text-slate-900">集中管理核心配置</h2>
        <p class="text-sm text-slate-500">维护数据库连接与模型参数，保持环境配置一致。</p>
      </header>
      <div class="grid gap-6 lg:grid-cols-2">
        <article class="card-surface space-y-6 p-6">
          <header class="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h3 class="text-lg font-semibold text-slate-900">数据库连接</h3>
              <p class="text-sm text-slate-500">维护项目可用的数据库连接，并指定默认连接。</p>
            </div>
            <button
              type="button"
              class="inline-flex items-center gap-2 rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600"
              @click="openCreateDatabaseModal"
            >
              新增连接
            </button>
          </header>

          <p v-if="databaseState.error" class="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-600">{{ databaseState.error }}</p>
          <p v-if="databaseState.message" class="rounded-2xl bg-emerald-100 px-4 py-3 text-sm text-emerald-600">{{ databaseState.message }}</p>

          <ul v-if="databaseState.connections.length" class="space-y-4">
            <li
              v-for="connection in databaseState.connections"
              :key="connection.id"
              class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div class="flex flex-col gap-2">
                <div class="flex flex-wrap items-center gap-2">
                  <h4 class="text-base font-semibold text-slate-900">{{ connection.name }}</h4>
                  <span v-if="databaseState.active === connection.id" class="badge-soft bg-indigo-100 text-indigo-600">默认</span>
                </div>
                <p class="text-sm text-slate-500">{{ connection.engine }} · {{ connection.url }}</p>
                <p class="text-sm text-slate-500">{{ connection.description || '暂无描述' }}</p>
              </div>
              <div class="mt-4 flex flex-wrap gap-2">
                <button
                  v-if="databaseState.active !== connection.id"
                  type="button"
                  class="rounded-full border border-slate-200 px-4 py-1.5 text-sm font-medium text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600"
                  @click="activateConnection(connection.id)"
                >
                  设为默认
                </button>
                <button
                  type="button"
                  class="rounded-full border border-slate-200 px-4 py-1.5 text-sm font-medium text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600"
                  @click="editDatabaseConnection(connection)"
                >
                  编辑
                </button>
                <button
                  type="button"
                  class="rounded-full border border-rose-200 px-4 py-1.5 text-sm font-medium text-rose-600 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60"
                  :disabled="databaseState.active === connection.id"
                  @click="deleteDatabaseConnection(connection.id)"
                >
                  删除
                </button>
              </div>
            </li>
          </ul>
          <p v-else-if="!databaseState.loading" class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">尚未添加数据库连接。</p>
          <p v-if="databaseState.loading" class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">加载中…</p>

          <AppModal
            v-model="databaseModalVisible"
            eyebrow="数据库管理"
            :title="databaseModalMode === 'create' ? '新增数据库连接' : '编辑数据库连接'"
            :description="databaseModalMode === 'create' ? '为项目添加新的数据库连接，并可选择设为默认。' : '更新数据库连接信息，保存后即时生效。'"
            cancel-text="取消"
            :confirm-text="databaseModalMode === 'create' ? '新增连接' : '保存修改'"
            confirm-loading-text="保存中…"
            :confirm-loading="databaseFormState.saving"
            :confirm-disabled="databaseModalConfirmDisabled"
            :close-on-backdrop="!databaseFormState.saving"
            :show-close="!databaseFormState.saving"
            width="max-w-2xl"
            @cancel="handleDatabaseModalCancel"
            @confirm="handleDatabaseModalConfirm"
          >
            <p v-if="databaseFormState.error" class="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-600">
              {{ databaseFormState.error }}
            </p>
            <form class="space-y-4" @submit.prevent="handleDatabaseModalConfirm">
              <div class="grid gap-4 md:grid-cols-2">
                <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
                  <span>标识</span>
                  <input
                    v-model.trim="databaseForm.id"
                    type="text"
                    :disabled="databaseModalMode === 'edit'"
                    required
                    placeholder="如：remote-mysql"
                    class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-100"
                  />
                </label>
                <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
                  <span>名称</span>
                  <input
                    v-model.trim="databaseForm.name"
                    type="text"
                    required
                    placeholder="展示用名称"
                    class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                  />
                </label>
                <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
                  <span>数据库类型</span>
                  <input
                    v-model.trim="databaseForm.engine"
                    type="text"
                    required
                    placeholder="mysql / postgres / sqlite"
                    class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                  />
                </label>
                <label class="flex flex-col gap-2 text-sm font-medium text-slate-600 md:col-span-2">
                  <span>连接 URL</span>
                  <input
                    v-model.trim="databaseForm.url"
                    type="text"
                    required
                    placeholder="示例：mysql+pymysql://user:pass@host:3306/db"
                    class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                  />
                </label>
                <label class="flex flex-col gap-2 text-sm font-medium text-slate-600 md:col-span-2">
                  <span>描述</span>
                  <textarea
                    v-model.trim="databaseForm.description"
                    rows="3"
                    placeholder="用途说明（可选）"
                    class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                  ></textarea>
                </label>
                <label class="flex items-center gap-2 text-sm font-medium text-slate-600 md:col-span-2">
                  <input v-model="databaseForm.set_active" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
                  <span>保存后设为默认连接</span>
                </label>
              </div>
              <button type="submit" class="hidden" aria-hidden="true">保存</button>
            </form>
          </AppModal>
        </article>

        <article class="card-surface space-y-6 p-6">
          <header>
            <h3 class="text-lg font-semibold text-slate-900">筛选模型配置</h3>
            <p class="text-sm text-slate-500">配置用于舆情筛选的 LLM 服务和参数。</p>
          </header>

          <p v-if="llmState.error" class="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-600">{{ llmState.error }}</p>
          <p v-if="llmState.message" class="rounded-2xl bg-emerald-100 px-4 py-3 text-sm text-emerald-600">{{ llmState.message }}</p>

          <form class="space-y-4" @submit.prevent="submitLlmFilter">
            <div class="grid gap-4 md:grid-cols-2">
              <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
                <span>服务提供方</span>
                <select
                  v-model="llmState.filter.provider"
                  class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                >
                  <option
                    v-for="option in providerOptions"
                    :key="`filter-${option.value}`"
                    :value="option.value"
                  >
                    {{ option.label }}
                  </option>
                </select>
              </label>
              <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
                <span>模型名称</span>
                <input
                  v-model.trim="llmState.filter.model"
                  type="text"
                  :placeholder="filterModelPlaceholder"
                  class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                />
              </label>
              <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
                <span>QPS</span>
                <input
                  v-model.number="llmState.filter.qps"
                  type="number"
                  min="0"
                  class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                />
              </label>
              <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
                <span>批处理大小</span>
                <input
                  v-model.number="llmState.filter.batch_size"
                  type="number"
                  min="1"
                  class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                />
              </label>
              <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
                <span>截断长度</span>
                <input
                  v-model.number="llmState.filter.truncation"
                  type="number"
                  min="0"
                  class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                />
              </label>
            </div>
            <div class="flex flex-wrap gap-3">
              <button type="submit" class="rounded-full bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow hover:bg-indigo-500">
                保存筛选配置
              </button>
            </div>
          </form>

          <header>
            <h3 class="text-lg font-semibold text-slate-900">对话模型配置</h3>
            <p class="text-sm text-slate-500">用于项目汇报与交互问答的模型参数。</p>
          </header>

          <p v-if="llmState.error" class="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-600">{{ llmState.error }}</p>

          <form class="space-y-4" @submit.prevent="submitLlmAssistant">
            <div class="grid gap-4 md:grid-cols-2">
              <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
                <span>服务提供方</span>
                <select
                  v-model="llmState.assistant.provider"
                  class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                >
                  <option
                    v-for="option in providerOptions"
                    :key="`assistant-${option.value}`"
                    :value="option.value"
                  >
                    {{ option.label }}
                  </option>
                </select>
              </label>
              <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
                <span>模型名称</span>
                <input
                  v-model.trim="llmState.assistant.model"
                  type="text"
                  :placeholder="assistantModelPlaceholder"
                  class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                />
              </label>
              <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
                <span>最大 Tokens</span>
                <input
                  v-model.number="llmState.assistant.max_tokens"
                  type="number"
                  min="0"
                  class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                />
              </label>
              <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
                <span>温度</span>
                <input
                  v-model.number="llmState.assistant.temperature"
                  type="number"
                  min="0"
                  step="0.1"
                  class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                />
              </label>
            </div>
            <div class="flex flex-wrap gap-3">
              <button type="submit" class="rounded-full bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow hover:bg-indigo-500">
                保存对话配置
              </button>
            </div>
          </form>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import AppModal from '../components/AppModal.vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
const providerOptions = [
  { label: '阿里通义千问（DashScope）', value: 'qwen' },
  { label: 'OpenAI / 兼容 API', value: 'openai' }
]

const databaseState = reactive({
  connections: [],
  loading: false,
  error: '',
  message: '',
  active: ''
})

const llmState = reactive({
  filter: {
    provider: 'qwen',
    model: '',
    qps: 0,
    batch_size: 1,
    truncation: 0
  },
  assistant: {
    provider: 'qwen',
    model: '',
    max_tokens: 0,
    temperature: 0
  },
  loading: false,
  error: '',
  message: ''
})

const filterModelPlaceholder = computed(() =>
  llmState.filter.provider === 'openai' ? '如：gpt-3.5-turbo' : '如：qwen-plus'
)
const assistantModelPlaceholder = computed(() =>
  llmState.assistant.provider === 'openai' ? '如：gpt-4o-mini' : '如：qwen-turbo'
)

const databaseModalVisible = ref(false)
const databaseModalMode = ref('create')
const databaseFormState = reactive({
  saving: false,
  error: ''
})
const databaseForm = reactive({
  id: '',
  name: '',
  engine: '',
  url: '',
  description: '',
  set_active: false
})

const resetDatabaseForm = () => {
  databaseForm.id = ''
  databaseForm.name = ''
  databaseForm.engine = ''
  databaseForm.url = ''
  databaseForm.description = ''
  databaseForm.set_active = false
}

const databaseModalConfirmDisabled = computed(() => {
  return (
    databaseFormState.saving ||
    !databaseForm.id ||
    !databaseForm.name ||
    !databaseForm.engine ||
    !databaseForm.url
  )
})

const fetchDatabaseConnections = async () => {
  databaseState.loading = true
  databaseState.error = ''
  try {
    const response = await fetch(`${API_BASE_URL}/settings/databases`)
    if (!response.ok) {
      throw new Error('获取数据库连接失败')
    }
    const payload = await response.json()
    const result = payload && typeof payload === 'object' ? payload.data ?? {} : {}
    const connections = Array.isArray(result.connections) ? result.connections : []
    databaseState.connections = connections
    databaseState.active = typeof result.active === 'string' ? result.active : ''
  } catch (err) {
    databaseState.error = err instanceof Error ? err.message : '获取数据库连接失败'
  } finally {
    databaseState.loading = false
  }
}

const openCreateDatabaseModal = () => {
  resetDatabaseForm()
  databaseModalMode.value = 'create'
  databaseFormState.error = ''
  databaseModalVisible.value = true
}

const editDatabaseConnection = (connection) => {
  if (!connection) return
  databaseModalMode.value = 'edit'
  databaseFormState.error = ''
  databaseForm.id = connection.id || ''
  databaseForm.name = connection.name || ''
  databaseForm.engine = connection.engine || ''
  databaseForm.url = connection.url || ''
  databaseForm.description = connection.description || ''
  databaseForm.set_active = databaseState.active === connection.id
  databaseModalVisible.value = true
}

const closeDatabaseModal = () => {
  databaseModalVisible.value = false
  databaseModalMode.value = 'create'
  databaseFormState.error = ''
  resetDatabaseForm()
}

const handleDatabaseModalCancel = () => {
  if (databaseFormState.saving) return
  closeDatabaseModal()
}

const handleDatabaseModalConfirm = async () => {
  if (databaseFormState.saving) return
  databaseFormState.error = ''

  const trimmed = {
    id: (databaseForm.id || '').trim(),
    name: (databaseForm.name || '').trim(),
    engine: (databaseForm.engine || '').trim(),
    url: (databaseForm.url || '').trim(),
    description: (databaseForm.description || '').trim(),
    set_active: databaseForm.set_active
  }

  if (!trimmed.id) {
    databaseFormState.error = '标识不能为空'
    return
  }
  if (!trimmed.name) {
    databaseFormState.error = '名称不能为空'
    return
  }
  if (!trimmed.engine) {
    databaseFormState.error = '数据库类型不能为空'
    return
  }
  if (!trimmed.url) {
    databaseFormState.error = '连接 URL 不能为空'
    return
  }

  databaseFormState.saving = true
  databaseState.message = ''

  try {
    const endpoint =
      databaseModalMode.value === 'create'
        ? `${API_BASE_URL}/settings/databases`
        : `${API_BASE_URL}/settings/databases/${encodeURIComponent(trimmed.id)}`
    const method = databaseModalMode.value === 'create' ? 'POST' : 'PUT'
    const response = await fetch(endpoint, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(trimmed)
    })
    const result = await response.json().catch(() => ({}))
    if (!response.ok || result.status === 'error') {
      const message = result && typeof result === 'object' ? result.message : ''
      throw new Error(message || '保存数据库连接失败')
    }
    databaseState.message = databaseModalMode.value === 'create' ? '新增连接成功' : '连接信息已更新'
    await fetchDatabaseConnections()
    closeDatabaseModal()
  } catch (err) {
    databaseFormState.error = err instanceof Error ? err.message : '保存数据库连接失败'
  }
  databaseFormState.saving = false
}

const activateConnection = async (connectionId) => {
  databaseState.error = ''
  try {
    const response = await fetch(`${API_BASE_URL}/settings/databases/${encodeURIComponent(connectionId)}/activate`, {
      method: 'POST'
    })
    if (!response.ok) {
      throw new Error('设置默认连接失败')
    }
    databaseState.message = '已设为默认连接'
    databaseState.active = connectionId
  } catch (err) {
    databaseState.error = err instanceof Error ? err.message : '设置默认连接失败'
  }
}

const deleteDatabaseConnection = async (connectionId) => {
  if (!window.confirm('确定要删除该连接吗？')) return
  databaseState.error = ''
  try {
    const response = await fetch(`${API_BASE_URL}/settings/databases/${encodeURIComponent(connectionId)}`, {
      method: 'DELETE'
    })
    if (!response.ok) {
      throw new Error('删除数据库连接失败')
    }
    databaseState.message = '删除成功'
    await fetchDatabaseConnections()
  } catch (err) {
    databaseState.error = err instanceof Error ? err.message : '删除数据库连接失败'
  }
}

const submitLlmFilter = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const response = await fetch(`${API_BASE_URL}/settings/llm/filter`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(llmState.filter)
    })
    if (!response.ok) {
      throw new Error('保存筛选配置失败')
    }
    llmState.message = '筛选配置已保存'
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '保存筛选配置失败'
  }
}

const submitLlmAssistant = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const response = await fetch(`${API_BASE_URL}/settings/llm/assistant`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(llmState.assistant)
    })
    if (!response.ok) {
      throw new Error('保存对话配置失败')
    }
    llmState.message = '对话配置已保存'
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '保存对话配置失败'
  }
}

const fetchLlmSettings = async () => {
  llmState.loading = true
  llmState.error = ''
  try {
    const response = await fetch(`${API_BASE_URL}/settings/llm`)
    if (!response.ok) {
      throw new Error('读取模型配置失败')
    }
    const payload = await response.json()
    const result = payload && typeof payload === 'object' ? payload.data ?? {} : {}
    if (result.filter && typeof result.filter === 'object') {
      Object.assign(llmState.filter, result.filter)
    }
    if (!llmState.filter.provider) {
      llmState.filter.provider = 'qwen'
    }
    if (result.assistant && typeof result.assistant === 'object') {
      Object.assign(llmState.assistant, result.assistant)
    }
    if (!llmState.assistant.provider) {
      llmState.assistant.provider = 'qwen'
    }
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '读取模型配置失败'
  } finally {
    llmState.loading = false
  }
}

onMounted(() => {
  fetchDatabaseConnections()
  fetchLlmSettings()
})
</script>

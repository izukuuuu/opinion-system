<template>
  <div class="settings">
    <section class="settings__section">
      <header class="settings__intro">
        <p class="settings__eyebrow">系统设置</p>
        <h2>集中管理核心配置</h2>
        <p>维护数据库连接与模型参数，保持环境配置一致。</p>
      </header>

      <div class="settings__grid">
        <article class="settings-card">
          <header class="settings-card__header">
            <div>
              <h3>数据库连接</h3>
              <p>维护项目可用的数据库连接，并指定默认连接。</p>
            </div>
            <button type="button" class="settings-card__action" @click="toggleDatabaseForm">
              {{ databaseFormVisible ? '关闭表单' : '新增连接' }}
            </button>
          </header>

          <p v-if="databaseState.error" class="settings-card__error">{{ databaseState.error }}</p>
          <p v-if="databaseState.message" class="settings-card__message">{{ databaseState.message }}</p>

          <ul v-if="databaseState.connections.length" class="connection-list">
            <li
              v-for="connection in databaseState.connections"
              :key="connection.id"
              class="connection-list__item"
            >
              <div class="connection-list__meta">
                <h4>
                  {{ connection.name }}
                  <span v-if="databaseState.active === connection.id" class="connection-list__badge">默认</span>
                </h4>
                <p class="connection-list__engine">{{ connection.engine }} · {{ connection.url }}</p>
                <p class="connection-list__description">
                  {{ connection.description || '暂无描述' }}
                </p>
              </div>
              <div class="connection-list__actions">
                <button
                  v-if="databaseState.active !== connection.id"
                  type="button"
                  class="settings-button settings-button--ghost"
                  @click="activateConnection(connection.id)"
                >
                  设为默认
                </button>
                <button
                  type="button"
                  class="settings-button settings-button--ghost"
                  @click="editDatabaseConnection(connection)"
                >
                  编辑
                </button>
                <button
                  type="button"
                  class="settings-button settings-button--danger"
                  :disabled="databaseState.active === connection.id"
                  @click="deleteDatabaseConnection(connection.id)"
                >
                  删除
                </button>
              </div>
            </li>
          </ul>
          <p v-else-if="!databaseState.loading" class="settings-card__empty">尚未添加数据库连接。</p>
          <p v-if="databaseState.loading" class="settings-card__loading">加载中…</p>

          <form v-if="databaseFormVisible" class="settings-form" @submit.prevent="submitDatabaseForm">
            <div class="settings-form__grid">
              <label class="settings-field">
                <span>标识</span>
                <input
                  v-model.trim="databaseForm.id"
                  type="text"
                  :disabled="databaseFormMode === 'edit'"
                  required
                  placeholder="如：remote-mysql"
                />
              </label>
              <label class="settings-field">
                <span>名称</span>
                <input v-model.trim="databaseForm.name" type="text" required placeholder="展示用名称" />
              </label>
              <label class="settings-field">
                <span>数据库类型</span>
                <input v-model.trim="databaseForm.engine" type="text" required placeholder="mysql / postgres / sqlite" />
              </label>
              <label class="settings-field settings-field--wide">
                <span>连接 URL</span>
                <input
                  v-model.trim="databaseForm.url"
                  type="text"
                  required
                  placeholder="示例：mysql+pymysql://user:pass@host:3306/db"
                />
              </label>
              <label class="settings-field settings-field--wide">
                <span>描述</span>
                <textarea
                  v-model.trim="databaseForm.description"
                  rows="3"
                  placeholder="用途说明（可选）"
                ></textarea>
              </label>
              <label class="settings-checkbox">
                <input v-model="databaseForm.set_active" type="checkbox" />
                <span>保存后设为默认连接</span>
              </label>
            </div>
            <div class="settings-form__actions">
              <button type="submit" class="settings-button">
                {{ databaseFormMode === 'create' ? '新增连接' : '保存修改' }}
              </button>
              <button type="button" class="settings-button settings-button--ghost" @click="closeDatabaseForm">
                取消
              </button>
            </div>
          </form>
        </article>

        <article class="settings-card">
          <header class="settings-card__header">
            <div>
              <h3>筛选模型配置</h3>
              <p>配置用于舆情筛选的 LLM 服务和参数。</p>
            </div>
          </header>

          <p v-if="llmState.error" class="settings-card__error">{{ llmState.error }}</p>
          <p v-if="llmState.message" class="settings-card__message">{{ llmState.message }}</p>

          <form class="settings-form" @submit.prevent="submitLlmFilter">
            <div class="settings-form__grid">
              <label class="settings-field">
                <span>服务提供方</span>
                <input v-model.trim="llmState.filter.provider" type="text" placeholder="如：qwen" />
              </label>
              <label class="settings-field">
                <span>模型名称</span>
                <input v-model.trim="llmState.filter.model" type="text" placeholder="如：qwen-plus" />
              </label>
              <label class="settings-field">
                <span>QPS</span>
                <input v-model.number="llmState.filter.qps" type="number" min="0" />
              </label>
              <label class="settings-field">
                <span>批处理大小</span>
                <input v-model.number="llmState.filter.batch_size" type="number" min="1" />
              </label>
              <label class="settings-field">
                <span>截断长度</span>
                <input v-model.number="llmState.filter.truncation" type="number" min="0" />
              </label>
            </div>
            <div class="settings-form__actions">
              <button type="submit" class="settings-button">保存筛选配置</button>
            </div>
          </form>

          <section class="preset">
            <header class="preset__header">
              <div>
                <h4>模型预设</h4>
                <p>维护常用的模型参数组合，方便快速切换。</p>
              </div>
              <button type="button" class="settings-card__action" @click="togglePresetForm">
                {{ llmPresetFormVisible ? '关闭表单' : '新增预设' }}
              </button>
            </header>

            <ul v-if="llmState.presets.length" class="preset-list">
              <li v-for="preset in llmState.presets" :key="preset.id" class="preset-list__item">
                <div class="preset-list__meta">
                  <h5>{{ preset.name }}</h5>
                  <p class="preset-list__engine">{{ preset.provider }} · {{ preset.model }}</p>
                  <p class="preset-list__description">{{ preset.description || '暂无描述' }}</p>
                </div>
                <div class="preset-list__actions">
                  <button type="button" class="settings-button settings-button--ghost" @click="editPreset(preset)">
                    编辑
                  </button>
                  <button
                    type="button"
                    class="settings-button settings-button--danger"
                    @click="deletePreset(preset.id)"
                  >
                    删除
                  </button>
                </div>
              </li>
            </ul>
            <p v-else-if="!llmState.loading" class="settings-card__empty">尚未添加模型预设。</p>
            <p v-if="llmState.loading" class="settings-card__loading">加载中…</p>

            <form v-if="llmPresetFormVisible" class="settings-form" @submit.prevent="submitPresetForm">
              <div class="settings-form__grid">
                <label class="settings-field">
                  <span>标识</span>
                  <input
                    v-model.trim="llmPresetForm.id"
                    type="text"
                    :disabled="llmPresetFormMode === 'edit'"
                    required
                    placeholder="如：default"
                  />
                </label>
                <label class="settings-field">
                  <span>名称</span>
                  <input v-model.trim="llmPresetForm.name" type="text" required placeholder="展示用名称" />
                </label>
                <label class="settings-field">
                  <span>服务提供方</span>
                  <input v-model.trim="llmPresetForm.provider" type="text" required />
                </label>
                <label class="settings-field">
                  <span>模型名称</span>
                  <input v-model.trim="llmPresetForm.model" type="text" required />
                </label>
                <label class="settings-field settings-field--wide">
                  <span>描述</span>
                  <textarea v-model.trim="llmPresetForm.description" rows="3" placeholder="用途说明（可选）"></textarea>
                </label>
              </div>
              <div class="settings-form__actions">
                <button type="submit" class="settings-button">
                  {{ llmPresetFormMode === 'create' ? '新增预设' : '保存修改' }}
                </button>
                <button type="button" class="settings-button settings-button--ghost" @click="closePresetForm">
                  取消
                </button>
              </div>
            </form>
          </section>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

const resolveApiUrl = (path) => {
  if (!path) return API_BASE_URL || ''
  if (/^https?:\/\//i.test(path)) {
    return path
  }

  const normalizedPath = path.startsWith('/') ? path : `/${path}`

  if (!API_BASE_URL) {
    return normalizedPath
  }

  if (API_BASE_URL.endsWith('/api') && normalizedPath.startsWith('/api')) {
    const trimmed = normalizedPath.replace(/^\/api/, '') || ''
    return `${API_BASE_URL}${trimmed}`
  }

  return `${API_BASE_URL}${normalizedPath}`
}

const parseResponseData = (response) => {
  if (!response || typeof response !== 'object') {
    return {}
  }
  const payload = response.data
  if (!payload || typeof payload !== 'object') {
    return {}
  }
  return payload
}

const toNormalizedInteger = (value, fallback, minimum) => {
  if (value === null || value === undefined || value === '') {
    return fallback
  }

  const numeric = Number(value)
  if (!Number.isFinite(numeric)) {
    return fallback
  }

  const rounded = Math.round(numeric)
  return rounded < minimum ? minimum : rounded
}

const databaseState = reactive({
  connections: [],
  active: '',
  loading: false,
  error: '',
  message: ''
})

const databaseFormVisible = ref(false)
const databaseFormMode = ref('create')
const databaseForm = reactive({
  id: '',
  name: '',
  engine: 'mysql',
  url: '',
  description: '',
  set_active: true
})

const llmState = reactive({
  filter: {
    provider: '',
    model: '',
    qps: 0,
    batch_size: 1,
    truncation: 0
  },
  presets: [],
  loading: false,
  error: '',
  message: ''
})

const llmPresetFormVisible = ref(false)
const llmPresetFormMode = ref('create')
const llmPresetForm = reactive({
  id: '',
  name: '',
  provider: '',
  model: '',
  description: ''
})

const apiRequest = async (url, options = {}) => {
  const init = {
    headers: {
      'Content-Type': 'application/json'
    },
    ...options
  }

  if (init.body && typeof init.body !== 'string') {
    init.body = JSON.stringify(init.body)
  }

  const response = await fetch(resolveApiUrl(url), init)
  const data = await response.json().catch(() => {
    throw new Error('无法解析服务器返回的数据')
  })

  if (!response.ok || data.status === 'error') {
    const message = data.message || `请求失败（${response.status}）`
    throw new Error(message)
  }

  return data
}

const loadDatabaseConnections = async () => {
  databaseState.loading = true
  databaseState.error = ''
  try {
    const payload = parseResponseData(await apiRequest('/api/settings/databases'))
    databaseState.connections = Array.isArray(payload.connections) ? payload.connections : []
    databaseState.active = typeof payload.active === 'string' ? payload.active : payload.active || ''
  } catch (error) {
    databaseState.error = error.message
  } finally {
    databaseState.loading = false
  }
}

const resetDatabaseForm = () => {
  databaseForm.id = ''
  databaseForm.name = ''
  databaseForm.engine = 'mysql'
  databaseForm.url = ''
  databaseForm.description = ''
  databaseForm.set_active = !databaseState.connections.length
}

const toggleDatabaseForm = () => {
  if (databaseFormVisible.value) {
    closeDatabaseForm()
    return
  }

  databaseFormMode.value = 'create'
  resetDatabaseForm()
  databaseFormVisible.value = true
}

const editDatabaseConnection = (connection) => {
  databaseFormMode.value = 'edit'
  databaseFormVisible.value = true
  databaseForm.id = connection.id
  databaseForm.name = connection.name
  databaseForm.engine = connection.engine
  databaseForm.url = connection.url
  databaseForm.description = connection.description || ''
  databaseForm.set_active = databaseState.active === connection.id
}

const closeDatabaseForm = () => {
  databaseFormVisible.value = false
}

const submitDatabaseForm = async () => {
  databaseState.error = ''
  databaseState.message = ''

  const payload = {
    name: databaseForm.name,
    engine: databaseForm.engine,
    url: databaseForm.url,
    description: databaseForm.description,
    set_active: databaseForm.set_active
  }

  const isCreate = databaseFormMode.value === 'create'
  let endpoint = '/api/settings/databases'
  let method = 'POST'

  if (isCreate) {
    payload.id = databaseForm.id
  } else {
    endpoint = `/api/settings/databases/${databaseForm.id}`
    method = 'PUT'
  }

  try {
    await apiRequest(endpoint, { method, body: payload })
    databaseState.message = isCreate ? '新增数据库连接成功' : '数据库连接已更新'
    databaseFormVisible.value = false
    await loadDatabaseConnections()
  } catch (error) {
    databaseState.error = error.message
  }
}

const deleteDatabaseConnection = async (connectionId) => {
  if (!window.confirm('确定要删除该连接吗？')) {
    return
  }

  databaseState.error = ''
  databaseState.message = ''

  try {
    await apiRequest(`/api/settings/databases/${connectionId}`, { method: 'DELETE' })
    databaseState.message = '数据库连接已删除'
    await loadDatabaseConnections()
  } catch (error) {
    databaseState.error = error.message
  }
}

const activateConnection = async (connectionId) => {
  databaseState.error = ''
  databaseState.message = ''

  try {
    await apiRequest(`/api/settings/databases/${connectionId}/activate`, { method: 'POST' })
    databaseState.message = '默认数据库已更新'
    await loadDatabaseConnections()
  } catch (error) {
    databaseState.error = error.message
  }
}

const loadLlmConfig = async () => {
  llmState.loading = true
  llmState.error = ''
  try {
    const payload = parseResponseData(await apiRequest('/api/settings/llm'))
    llmState.filter = {
      provider: payload.filter_llm?.provider || '',
      model: payload.filter_llm?.model || '',
      qps: payload.filter_llm?.qps ?? 0,
      batch_size: payload.filter_llm?.batch_size ?? 1,
      truncation: payload.filter_llm?.truncation ?? 0
    }
    llmState.presets = Array.isArray(payload.presets) ? payload.presets : []
  } catch (error) {
    llmState.error = error.message
  } finally {
    llmState.loading = false
  }
}

const submitLlmFilter = async () => {
  llmState.error = ''
  llmState.message = ''

  try {
    const payload = {
      provider: (llmState.filter.provider || '').trim(),
      model: (llmState.filter.model || '').trim(),
      qps: toNormalizedInteger(llmState.filter.qps, 0, 0),
      batch_size: toNormalizedInteger(llmState.filter.batch_size, 1, 1),
      truncation: toNormalizedInteger(llmState.filter.truncation, 0, 0)
    }

    llmState.filter.provider = payload.provider
    llmState.filter.model = payload.model
    llmState.filter.qps = payload.qps
    llmState.filter.batch_size = payload.batch_size
    llmState.filter.truncation = payload.truncation

    await apiRequest('/api/settings/llm/filter', {
      method: 'PUT',
      body: payload
    })
    llmState.message = '筛选模型配置已保存'
    await loadLlmConfig()
  } catch (error) {
    llmState.error = error.message
  }
}

const resetPresetForm = () => {
  llmPresetForm.id = ''
  llmPresetForm.name = ''
  llmPresetForm.provider = ''
  llmPresetForm.model = ''
  llmPresetForm.description = ''
}

const togglePresetForm = () => {
  if (llmPresetFormVisible.value) {
    closePresetForm()
    return
  }

  llmPresetFormMode.value = 'create'
  resetPresetForm()
  llmPresetFormVisible.value = true
}

const editPreset = (preset) => {
  llmPresetFormMode.value = 'edit'
  llmPresetFormVisible.value = true
  llmPresetForm.id = preset.id
  llmPresetForm.name = preset.name
  llmPresetForm.provider = preset.provider
  llmPresetForm.model = preset.model
  llmPresetForm.description = preset.description || ''
}

const closePresetForm = () => {
  llmPresetFormVisible.value = false
}

const submitPresetForm = async () => {
  llmState.error = ''
  llmState.message = ''

  const payload = {
    name: llmPresetForm.name,
    provider: llmPresetForm.provider,
    model: llmPresetForm.model,
    description: llmPresetForm.description
  }

  const isCreate = llmPresetFormMode.value === 'create'
  let endpoint = '/api/settings/llm/presets'
  let method = 'POST'

  if (isCreate) {
    payload.id = llmPresetForm.id
  } else {
    endpoint = `/api/settings/llm/presets/${llmPresetForm.id}`
    method = 'PUT'
  }

  try {
    await apiRequest(endpoint, { method, body: payload })
    llmState.message = isCreate ? '模型预设已新增' : '模型预设已更新'
    llmPresetFormVisible.value = false
    await loadLlmConfig()
  } catch (error) {
    llmState.error = error.message
  }
}

const deletePreset = async (presetId) => {
  if (!window.confirm('确定要删除该预设吗？')) {
    return
  }

  llmState.error = ''
  llmState.message = ''

  try {
    await apiRequest(`/api/settings/llm/presets/${presetId}`, { method: 'DELETE' })
    llmState.message = '模型预设已删除'
    await loadLlmConfig()
  } catch (error) {
    llmState.error = error.message
  }
}

onMounted(() => {
  loadDatabaseConnections()
  loadLlmConfig()
})
</script>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  gap: 2.5rem;
}

.settings__section {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.settings__intro {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.settings__eyebrow {
  font-size: 0.85rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #6366f1;
  font-weight: 600;
}

.settings__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1.75rem;
}

.settings-card {
  background: rgba(255, 255, 255, 0.85);
  border-radius: 20px;
  padding: 1.75rem;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.12);
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  backdrop-filter: blur(8px);
}

.settings-card__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.settings-card__header h3 {
  font-size: 1.2rem;
  margin: 0;
  font-weight: 700;
}

.settings-card__header p {
  margin: 0.35rem 0 0;
  color: #64748b;
}

.settings-card__action {
  border: none;
  background: #4338ca;
  color: #f8fafc;
  padding: 0.55rem 1.1rem;
  border-radius: 999px;
  font-size: 0.9rem;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  box-shadow: 0 14px 30px rgba(67, 56, 202, 0.25);
}

.settings-card__action:hover {
  transform: translateY(-1px);
  box-shadow: 0 18px 36px rgba(67, 56, 202, 0.28);
}

.settings-card__error {
  background: rgba(248, 113, 113, 0.12);
  color: #b91c1c;
  padding: 0.75rem 1rem;
  border-radius: 12px;
  font-size: 0.9rem;
}

.settings-card__message {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
  padding: 0.75rem 1rem;
  border-radius: 12px;
  font-size: 0.9rem;
}

.settings-card__empty,
.settings-card__loading {
  color: #64748b;
  font-size: 0.95rem;
}

.connection-list,
.preset-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.connection-list__item,
.preset-list__item {
  background: rgba(248, 250, 252, 0.9);
  border-radius: 16px;
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.connection-list__meta h4,
.preset-list__meta h5 {
  margin: 0;
  font-size: 1.05rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.connection-list__engine,
.preset-list__engine {
  font-size: 0.9rem;
  color: #475569;
  margin: 0;
}

.connection-list__description,
.preset-list__description {
  font-size: 0.85rem;
  margin: 0;
  color: #64748b;
}

.connection-list__badge {
  background: rgba(16, 185, 129, 0.16);
  color: #047857;
  border-radius: 999px;
  padding: 0.2rem 0.65rem;
  font-size: 0.7rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.connection-list__actions,
.preset-list__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.settings-button {
  border: none;
  background: #2563eb;
  color: #f8fafc;
  padding: 0.5rem 1.1rem;
  border-radius: 12px;
  font-size: 0.9rem;
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease;
}

.settings-button:hover {
  background: #1d4ed8;
  transform: translateY(-1px);
}

.settings-button--ghost {
  background: rgba(148, 163, 184, 0.14);
  color: #0f172a;
}

.settings-button--ghost:hover {
  background: rgba(148, 163, 184, 0.22);
}

.settings-button--danger {
  background: rgba(248, 113, 113, 0.85);
}

.settings-button--danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.settings-form {
  border-top: 1px dashed rgba(148, 163, 184, 0.28);
  padding-top: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.settings-form__grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.settings-field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  font-size: 0.9rem;
}

.settings-field span {
  color: #334155;
  font-weight: 600;
}

.settings-field input,
.settings-field textarea {
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.4);
  padding: 0.55rem 0.75rem;
  font-size: 0.95rem;
  background: rgba(255, 255, 255, 0.9);
  color: #0f172a;
  transition: border 0.2s ease, box-shadow 0.2s ease;
}

.settings-field input:focus,
.settings-field textarea:focus {
  outline: none;
  border-color: rgba(59, 130, 246, 0.65);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
}

.settings-field--wide {
  grid-column: 1 / -1;
}

.settings-checkbox {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
  color: #475569;
}

.settings-form__actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.preset {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.preset__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.preset__header h4 {
  margin: 0;
  font-size: 1rem;
}

.preset__header p {
  margin: 0.35rem 0 0;
  color: #64748b;
  font-size: 0.9rem;
}

@media (max-width: 768px) {
  .settings-card {
    padding: 1.25rem;
  }

  .settings-form__grid {
    grid-template-columns: 1fr;
  }
}
</style>

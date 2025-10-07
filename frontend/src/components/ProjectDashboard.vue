<template>
  <div class="dashboard">
    <section class="card">
      <header class="card__header">
        <div>
          <h2>{{ formTitle }}</h2>
          <p>{{ formSubtitle }}</p>
        </div>
        <p v-if="isReadOnly" class="card__hint">当前为查看模式，点击左侧“编辑项目”按钮即可修改信息。</p>
      </header>
      <form class="form" :class="{ 'form--readonly': isReadOnly }" @submit.prevent="submit">
        <div class="form__row">
          <label for="name">项目名称</label>
          <input
            id="name"
            v-model="form.name"
            type="text"
            placeholder="例如：专题_2024"
            :readonly="isReadOnly"
            required
          />
        </div>
        <div class="form__row">
          <label for="description">项目描述</label>
          <textarea
            id="description"
            v-model="form.description"
            rows="2"
            placeholder="用于说明项目背景或目的"
            :readonly="isReadOnly"
          ></textarea>
        </div>
        <div class="form__row">
          <label for="metadata">附加信息 (JSON 可选)</label>
          <textarea
            id="metadata"
            v-model="form.metadata"
            rows="3"
            placeholder='{"owner": "张三", "priority": "高"}'
            :readonly="isReadOnly"
          ></textarea>
        </div>
        <div class="form__actions">
          <button v-if="!isReadOnly" type="button" class="form__secondary" @click="cancelEdit">
            取消
          </button>
          <button type="submit" :disabled="submitting || isReadOnly">
            {{ submitLabel }}
          </button>
        </div>
        <p v-if="formError" class="form__message form__message--error">{{ formError }}</p>
        <p v-if="formSuccess" class="form__message form__message--success">{{ formSuccess }}</p>
      </form>
    </section>

    <section class="card card--project" v-if="project">
      <header class="card__header card__header--project">
        <div>
          <h2>{{ project.name }}</h2>
          <p>最近更新：{{ formatTimestamp(project.updated_at) }}</p>
        </div>
      </header>
      <section class="project-card__summary" aria-label="项目摘要">
        <div class="summary-grid">
          <div class="summary-item">
            <span class="summary-item__label">状态</span>
            <span class="summary-item__value" :data-status="project.status">
              {{ statusLabel(project.status) }}
            </span>
          </div>
          <div class="summary-item">
            <span class="summary-item__label">创建时间</span>
            <span class="summary-item__value">{{ formatTimestamp(project.created_at) }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-item__label">执行记录</span>
            <span class="summary-item__value">
              {{ timeline.length ? `${timeline.length} 条` : '暂无' }}
            </span>
          </div>
          <div class="summary-item">
            <span class="summary-item__label">包含日期</span>
            <span class="summary-item__value">{{ formattedDates }}</span>
          </div>
        </div>
      </section>
      <nav class="project-card__tabs" role="tablist" aria-label="项目信息分类">
        <button
          v-for="tab in detailTabs"
          :key="tab.key"
          class="project-card__tab"
          :class="{ 'project-card__tab--active': activeDetailTab === tab.key }"
          type="button"
          role="tab"
          :id="`project-tab-${tab.key}`"
          :aria-selected="activeDetailTab === tab.key"
          :aria-controls="`project-panel-${tab.key}`"
          @click="setActiveTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </nav>
      <div class="project-card__body">
        <section
          v-if="activeDetailTab === 'overview'"
          class="project-card__panel"
          role="tabpanel"
          id="project-panel-overview"
          aria-labelledby="project-tab-overview"
        >
          <p v-if="project.description" class="details__description">{{ project.description }}</p>
          <p v-else class="details__placeholder">暂无项目描述，可在编辑模式下补充背景信息。</p>
          <div v-if="hasDates" class="details__dates">
            <h3>包含日期</h3>
            <ul>
              <li v-for="date in project.dates" :key="date">{{ date }}</li>
            </ul>
          </div>
          <div class="details__metadata" v-if="hasMetadata">
            <h3>附加信息</h3>
            <ul>
              <li v-for="(value, key) in project.metadata" :key="key">
                <strong>{{ key }}：</strong>{{ formatValue(value) }}
              </li>
            </ul>
          </div>
        </section>
        <section
          v-else
          class="project-card__panel project-card__panel--timeline"
          role="tabpanel"
          id="project-panel-activity"
          aria-labelledby="project-tab-activity"
        >
          <h3>执行记录</h3>
          <ul v-if="timeline.length">
            <li v-for="item in timeline" :key="item.timestamp + item.operation" :data-success="item.success">
              <div class="timeline__header">
                <span class="timeline__operation">{{ item.operation }}</span>
                <span class="timeline__timestamp">{{ formatTimestamp(item.timestamp) }}</span>
              </div>
              <p class="timeline__status">{{ item.success ? '成功' : '失败' }}</p>
              <pre class="timeline__params" v-if="Object.keys(item.params).length">{{ prettyParams(item.params) }}</pre>
            </li>
          </ul>
          <p v-else class="timeline__empty">暂未记录任何执行步骤。</p>
        </section>
      </div>
    </section>
    <section class="placeholder" v-else-if="!loading && !isCreateMode">
      <p>从左侧列表选择一个项目即可浏览详情，或使用上方按钮快速创建。</p>
      <p v-if="props.error" class="placeholder__error">{{ props.error }}</p>
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'

const props = defineProps({
  project: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  },
  error: {
    type: String,
    default: ''
  },
  mode: {
    type: String,
    default: 'view'
  }
})

const emit = defineEmits(['project-created', 'cancel'])

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const form = reactive({
  name: '',
  description: '',
  metadata: ''
})

const submitting = ref(false)
const formError = ref('')
const formSuccess = ref('')

const formMode = computed(() => props.mode || 'view')
const isCreateMode = computed(() => formMode.value === 'create')
const isEditMode = computed(() => formMode.value === 'edit')
const isReadOnly = computed(() => formMode.value === 'view' && !!props.project)

const formTitle = computed(() => {
  if (isCreateMode.value) return '新建项目'
  if (isEditMode.value) return '编辑项目'
  if (props.project) return '查看项目信息'
  return '创建或更新项目'
})

const formSubtitle = computed(() => {
  if (isCreateMode.value) return '填写基础信息后保存，即可开始跟踪专题。'
  if (isEditMode.value) return '更新项目信息并保存，系统会同步记录最新描述与附加信息。'
  return '可先行创建专题，后续后端流程执行时会自动追加执行记录。'
})

const submitLabel = computed(() => {
  if (submitting.value) return '保存中…'
  if (isCreateMode.value) return '创建项目'
  if (isEditMode.value) return '保存修改'
  return '保存项目'
})

const hasMetadata = computed(
  () => props.project && props.project.metadata && Object.keys(props.project.metadata).length > 0
)

const detailTabs = [
  { key: 'overview', label: '项目概览' },
  { key: 'activity', label: '执行记录' }
]

const activeDetailTab = ref('overview')

const hasDates = computed(() => {
  const dates = props.project?.dates
  return Array.isArray(dates) && dates.length > 0
})

const formattedDates = computed(() => {
  if (!hasDates.value) return '暂无'
  return (props.project?.dates ?? []).join('、')
})

const resetForm = () => {
  form.name = ''
  form.description = ''
  form.metadata = ''
}

watch(
  [() => props.project, () => props.mode],
  ([project, mode]) => {
    if (mode === 'create') {
      resetForm()
    } else if (project) {
      form.name = project.name
      form.description = project.description || ''
      form.metadata = project.metadata ? JSON.stringify(project.metadata, null, 2) : ''
    } else {
      resetForm()
    }
    formSuccess.value = ''
    formError.value = ''
    activeDetailTab.value = 'overview'
  },
  { immediate: true }
)

const setActiveTab = (key) => {
  if (detailTabs.some((tab) => tab.key === key)) {
    activeDetailTab.value = key
  }
}

const timeline = computed(() => {
  if (!props.project?.operations) return []
  return [...props.project.operations].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
})

const parseMetadata = () => {
  if (!form.metadata.trim()) return undefined
  try {
    const metadata = JSON.parse(form.metadata)
    if (metadata && typeof metadata === 'object') {
      return metadata
    }
    throw new Error('metadata 需要是对象')
  } catch (err) {
    throw new Error('附加信息需为合法的 JSON 格式')
  }
}

const submit = async () => {
  if (isReadOnly.value) {
    formError.value = '当前为查看模式，请先点击左侧的“编辑项目”按钮'
    return
  }

  if (!form.name.trim()) {
    formError.value = '请输入项目名称'
    return
  }

  submitting.value = true
  formError.value = ''
  formSuccess.value = ''

  try {
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || undefined,
      metadata: parseMetadata()
    }

    const response = await fetch(`${API_BASE_URL}/projects`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })

    if (!response.ok) {
      throw new Error('项目保存失败')
    }

    const data = await response.json()
    if (data?.project) {
      emit('project-created', data.project)
      formSuccess.value = isCreateMode.value ? '新项目已创建' : '项目信息已更新'
    } else {
      formSuccess.value = '操作完成，但未返回项目信息'
    }
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '项目保存失败'
  } finally {
    submitting.value = false
  }
}

const cancelEdit = () => {
  emit('cancel')
}

const formatTimestamp = (timestamp) => {
  if (!timestamp) return '未知'
  try {
    const date = new Date(timestamp)
    return date.toLocaleString()
  } catch (err) {
    return timestamp
  }
}

const statusLabel = (status) => {
  if (status === 'success') return '成功'
  if (status === 'error') return '失败'
  return '进行中'
}

const formatValue = (value) => {
  if (typeof value === 'object' && value !== null) {
    return JSON.stringify(value)
  }
  return String(value)
}

const prettyParams = (params) => JSON.stringify(params, null, 2)
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.card {
  background: #ffffff;
  border-radius: 20px;
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
  padding: 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.card__header h2 {
  margin: 0;
  font-size: 1.5rem;
}

.card__header p {
  margin: 0.35rem 0 0;
  color: #64748b;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form--readonly {
  opacity: 0.85;
}

.form__row {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form__row input,
.form__row textarea {
  padding: 0.75rem 1rem;
  border-radius: 12px;
  border: 1px solid rgba(15, 23, 42, 0.1);
  background: #f8fafc;
  font-family: inherit;
  font-size: 0.95rem;
  resize: vertical;
}

.form__row input:focus,
.form__row textarea:focus {
  outline: none;
  border-color: rgba(59, 130, 246, 0.6);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
}

.form__actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.form__actions button {
  border: none;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: #fff;
  padding: 0.6rem 1.4rem;
  border-radius: 999px;
  cursor: pointer;
  font-weight: 600;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.form__actions button.form__secondary {
  background: rgba(99, 102, 241, 0.1);
  color: #4c1d95;
}

.form__actions button.form__secondary:hover {
  box-shadow: none;
  transform: none;
  background: rgba(99, 102, 241, 0.18);
}

.form__actions button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.form__actions button:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 25px rgba(99, 102, 241, 0.25);
}

.form__message {
  margin: 0;
  font-size: 0.9rem;
}

.form__message--error {
  color: #dc2626;
}

.form__message--success {
  color: #059669;
}

.card__hint {
  margin: 0.5rem 0 0;
  font-size: 0.85rem;
  color: #6366f1;
}

.form__row input[readonly],
.form__row textarea[readonly] {
  background: #f1f5f9;
  color: #64748b;
  cursor: not-allowed;
}

.card--project {
  gap: 1.75rem;
}

.card__header--project {
  align-items: flex-start;
}

.project-card__summary {
  background: #f8fafc;
  border-radius: 16px;
  padding: 1.25rem 1.5rem;
  border: 1px solid #e2e8f0;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.summary-item__label {
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #94a3b8;
}

.summary-item__value {
  font-size: 1.05rem;
  font-weight: 600;
  color: #1f2937;
  word-break: break-word;
}

.summary-item__value[data-status='success'] {
  color: #047857;
}

.summary-item__value[data-status='error'] {
  color: #b91c1c;
}

.project-card__tabs {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem;
  border-radius: 999px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  align-self: flex-start;
}

.project-card__tab {
  border: none;
  background: transparent;
  padding: 0.45rem 1.1rem;
  border-radius: 999px;
  font-weight: 600;
  color: #475569;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
}

.project-card__tab:hover,
.project-card__tab:focus-visible {
  outline: none;
  background: rgba(99, 102, 241, 0.12);
  color: #4338ca;
}

.project-card__tab--active {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #ffffff;
  box-shadow: 0 10px 24px rgba(99, 102, 241, 0.25);
}

.project-card__body {
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
}

.project-card__panel {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.project-card__panel--timeline h3 {
  margin: 0;
}

.details__description {
  margin: 0;
  font-size: 1rem;
  line-height: 1.5;
}

.details__placeholder {
  margin: 0;
  color: #64748b;
  background: rgba(248, 250, 252, 0.8);
  padding: 0.75rem 1rem;
  border-radius: 12px;
}

.details__placeholder--muted {
  background: transparent;
  padding: 0;
  color: #94a3b8;
}

.details__dates {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.details__dates h3 {
  margin: 0;
  font-size: 1rem;
  color: #1f2937;
}

.details__dates ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.details__dates li {
  padding: 0.4rem 0.75rem;
  border-radius: 999px;
  background: rgba(99, 102, 241, 0.12);
  color: #4338ca;
  font-weight: 600;
  font-size: 0.85rem;
}

.details__metadata {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  background: rgba(248, 250, 252, 0.85);
  border-radius: 16px;
  padding: 1rem 1.25rem;
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.details__metadata h3 {
  margin: 0 0 0.5rem;
}

.details__metadata ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  color: #475569;
}

.details__metadata li strong {
  color: #1f2937;
}

.project-card__panel--timeline {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.project-card__panel--timeline ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.project-card__panel--timeline li {
  padding: 1rem;
  border-radius: 16px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(248, 250, 252, 0.8);
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.project-card__panel--timeline li[data-success='false'] {
  border-color: rgba(220, 38, 38, 0.35);
}

.timeline__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}

.timeline__operation {
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.timeline__timestamp {
  color: #64748b;
  font-size: 0.85rem;
}

.timeline__status {
  margin: 0;
  font-weight: 600;
  color: #059669;
}

.project-card__panel--timeline li[data-success='false'] .timeline__status {
  color: #dc2626;
}

.timeline__params {
  margin: 0;
  background: #0f172a;
  color: #e0e7ff;
  padding: 0.75rem;
  border-radius: 12px;
  font-size: 0.85rem;
  overflow-x: auto;
}

.timeline__empty {
  margin: 0;
  color: #64748b;
}

@media (min-width: 1280px) {
  .summary-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

.placeholder {
  padding: 2rem;
  border-radius: 16px;
  background: rgba(248, 250, 252, 0.8);
  color: #475569;
}

.placeholder__error {
  margin-top: 1rem;
  color: #dc2626;
}

@media (max-width: 960px) {
  .project-card__tabs {
    width: 100%;
    justify-content: space-between;
  }
}
</style>

<template>
  <div class="dashboard">
    <section class="card">
      <header class="card__header">
        <h2>创建或更新项目</h2>
        <p>可先行创建专题，后续后端流程执行时会自动追加执行记录。</p>
      </header>
      <form class="form" @submit.prevent="submit">
        <div class="form__row">
          <label for="name">项目名称</label>
          <input id="name" v-model="form.name" type="text" placeholder="例如：专题_2024" required />
        </div>
        <div class="form__row">
          <label for="description">项目描述</label>
          <textarea
            id="description"
            v-model="form.description"
            rows="2"
            placeholder="用于说明项目背景或目的"
          ></textarea>
        </div>
        <div class="form__row">
          <label for="metadata">附加信息 (JSON 可选)</label>
          <textarea
            id="metadata"
            v-model="form.metadata"
            rows="3"
            placeholder='{"owner": "张三", "priority": "高"}'
          ></textarea>
        </div>
        <div class="form__actions">
          <button type="submit" :disabled="submitting">
            {{ submitting ? '保存中…' : '保存项目' }}
          </button>
        </div>
        <p v-if="formError" class="form__message form__message--error">{{ formError }}</p>
        <p v-if="formSuccess" class="form__message form__message--success">{{ formSuccess }}</p>
      </form>
    </section>

    <section class="card" v-if="project">
      <header class="card__header">
        <h2>{{ project.name }}</h2>
        <p>最近更新：{{ formatTimestamp(project.updated_at) }}</p>
      </header>
      <div class="card__body">
        <article class="details">
          <p v-if="project.description" class="details__description">{{ project.description }}</p>
          <ul class="details__list">
            <li><strong>状态：</strong>{{ statusLabel(project.status) }}</li>
            <li><strong>创建时间：</strong>{{ formatTimestamp(project.created_at) }}</li>
            <li>
              <strong>包含日期：</strong>
              <span v-if="project.dates?.length">{{ project.dates.join(', ') }}</span>
              <span v-else>暂无</span>
            </li>
          </ul>
          <div class="details__metadata" v-if="hasMetadata">
            <h3>附加信息</h3>
            <ul>
              <li v-for="(value, key) in project.metadata" :key="key">
                <strong>{{ key }}：</strong>{{ formatValue(value) }}
              </li>
            </ul>
          </div>
        </article>
        <section class="timeline">
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
    <section class="placeholder" v-else-if="!loading">
      <p>选择左侧的项目以查看详情，或创建一个新项目。</p>
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
  }
})

const emit = defineEmits(['project-created'])

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const form = reactive({
  name: '',
  description: '',
  metadata: ''
})

const submitting = ref(false)
const formError = ref('')
const formSuccess = ref('')

const hasMetadata = computed(
  () => props.project && props.project.metadata && Object.keys(props.project.metadata).length > 0
)

watch(
  () => props.project,
  (project) => {
    if (project) {
      form.name = project.name
      form.description = project.description || ''
      form.metadata = project.metadata ? JSON.stringify(project.metadata, null, 2) : ''
    } else {
      form.name = ''
      form.description = ''
      form.metadata = ''
    }
    formSuccess.value = ''
    formError.value = ''
  },
  { immediate: true }
)

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
      formSuccess.value = '项目信息已保存'
    } else {
      formSuccess.value = '操作完成，但未返回项目信息'
    }
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '项目保存失败'
  } finally {
    submitting.value = false
  }
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

.card__body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2rem;
}

.details {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.details__description {
  margin: 0;
  font-size: 1rem;
  line-height: 1.5;
}

.details__list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
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
}

.timeline {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.timeline ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.timeline li {
  padding: 1rem;
  border-radius: 16px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(248, 250, 252, 0.8);
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.timeline li[data-success='false'] {
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

.timeline li[data-success='false'] .timeline__status {
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
  .card__body {
    grid-template-columns: 1fr;
  }
}
</style>

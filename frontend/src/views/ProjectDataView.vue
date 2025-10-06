<template>
  <div class="data-manager">
    <aside class="data-manager__projects">
      <div class="data-manager__projects-header">
        <h2>项目列表</h2>
        <button type="button" @click="fetchProjects" :disabled="projectLoading">
          {{ projectLoading ? '加载中…' : '刷新' }}
        </button>
      </div>
      <ul class="data-manager__project-list">
        <li
          v-for="project in projects"
          :key="project.name"
          :class="['data-manager__project-item', { 'data-manager__project-item--active': project.name === selectedProject }]"
        >
          <button type="button" @click="selectProject(project.name)">
            <span class="project-name">{{ project.name }}</span>
            <span class="project-updated">{{ formatTimestamp(project.updated_at) }}</span>
          </button>
        </li>
      </ul>
      <p v-if="!projects.length && !projectLoading" class="data-manager__empty">暂无项目，请先在项目面板中创建。</p>
    </aside>

    <section class="data-manager__content">
      <header class="data-manager__header">
        <h1>项目数据归档</h1>
        <p>导入 Excel/CSV 文件并自动生成 PKL 与 JSON 存档，全部保存在 backend/data 与 backend/store 中。</p>
      </header>

      <div class="data-manager__card">
        <div class="data-manager__card-header">
          <h2>上传表格</h2>
          <span v-if="selectedProject" class="badge">当前项目：{{ selectedProject }}</span>
        </div>
        <p class="data-manager__card-description">
          支持 .xlsx、.xls、.csv 文件，系统会为每份表格生成同名的 PKL 和 JSON 文件，方便在后续流程中直接读取。
        </p>
        <form class="upload-form" @submit.prevent="uploadDataset">
          <label class="upload-form__input" :class="{ 'upload-form__input--active': uploadFile }">
            <input ref="fileInput" type="file" accept=".xlsx,.xls,.csv" @change="handleFileChange" />
            <span v-if="uploadFile">{{ uploadFile.name }}</span>
            <span v-else>点击或拖拽文件到此处</span>
          </label>
          <div class="upload-form__actions">
            <button type="submit" :disabled="!canUpload">
              {{ uploading ? '上传中…' : '上传并归档' }}
            </button>
            <p v-if="uploadError" class="upload-form__message upload-form__message--error">{{ uploadError }}</p>
            <p v-if="uploadSuccess" class="upload-form__message upload-form__message--success">{{ uploadSuccess }}</p>
          </div>
        </form>
      </div>

      <div class="data-manager__card">
        <div class="data-manager__card-header">
          <h2>数据集清单</h2>
          <span v-if="datasets.length" class="badge badge--muted">共 {{ datasets.length }} 个</span>
        </div>
        <p v-if="!selectedProject" class="data-manager__placeholder">请选择左侧项目以查看归档记录。</p>
        <p v-else-if="datasetLoading" class="data-manager__placeholder">数据加载中…</p>
        <p v-else-if="datasetError" class="data-manager__placeholder data-manager__placeholder--error">{{ datasetError }}</p>
        <p v-else-if="!datasets.length" class="data-manager__placeholder">尚未上传任何数据集。</p>
        <ul v-else class="dataset-list">
          <li v-for="dataset in datasets" :key="dataset.id" class="dataset-list__item">
            <header class="dataset-list__header">
              <h3>{{ dataset.display_name }}</h3>
              <span>{{ formatTimestamp(dataset.stored_at) }}</span>
            </header>
            <dl class="dataset-list__meta">
              <div>
                <dt>数据行列</dt>
                <dd>{{ dataset.rows }} 行 · {{ dataset.column_count }} 列</dd>
              </div>
              <div>
                <dt>源文件</dt>
                <dd>{{ dataset.source_file }}</dd>
              </div>
              <div>
                <dt>PKL</dt>
                <dd>{{ dataset.pkl_file }}</dd>
              </div>
              <div>
                <dt>JSON</dt>
                <dd>{{ dataset.json_file }}</dd>
              </div>
            </dl>
            <details class="dataset-list__columns">
              <summary>字段预览</summary>
              <p>{{ dataset.columns.join(', ') }}</p>
            </details>
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const projects = ref([])
const projectLoading = ref(false)
const selectedProject = ref('')

const datasets = ref([])
const datasetLoading = ref(false)
const datasetError = ref('')

const fileInput = ref(null)
const uploadFile = ref(null)
const uploading = ref(false)
const uploadError = ref('')
const uploadSuccess = ref('')

const canUpload = computed(
  () => Boolean(selectedProject.value && uploadFile.value && !uploading.value)
)

const fetchProjects = async () => {
  projectLoading.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/projects`)
    if (!response.ok) {
      throw new Error('项目列表获取失败')
    }
    const data = await response.json()
    projects.value = Array.isArray(data.projects) ? data.projects : []
    if (!selectedProject.value && projects.value.length) {
      selectedProject.value = projects.value[0].name
      await fetchDatasets(selectedProject.value)
    }
  } catch (err) {
    console.error(err)
    projects.value = []
  } finally {
    projectLoading.value = false
  }
}

const fetchDatasets = async (projectName) => {
  if (!projectName) return
  datasetLoading.value = true
  datasetError.value = ''
  try {
    const response = await fetch(`${API_BASE_URL}/projects/${encodeURIComponent(projectName)}/datasets`)
    if (!response.ok) {
      throw new Error('读取数据集失败')
    }
    const data = await response.json()
    datasets.value = Array.isArray(data.datasets) ? data.datasets : []
  } catch (err) {
    datasetError.value = err instanceof Error ? err.message : '读取数据集失败'
    datasets.value = []
  } finally {
    datasetLoading.value = false
  }
}

const selectProject = async (projectName) => {
  if (selectedProject.value === projectName) return
  selectedProject.value = projectName
  await fetchDatasets(projectName)
}

const handleFileChange = (event) => {
  uploadSuccess.value = ''
  uploadError.value = ''
  const [file] = event.target.files || []
  uploadFile.value = file || null
}

const uploadDataset = async () => {
  if (!canUpload.value) {
    uploadError.value = '请选择项目和文件'
    return
  }

  uploading.value = true
  uploadError.value = ''
  uploadSuccess.value = ''

  try {
    const formData = new FormData()
    formData.append('file', uploadFile.value)

    const response = await fetch(
      `${API_BASE_URL}/projects/${encodeURIComponent(selectedProject.value)}/datasets`,
      {
        method: 'POST',
        body: formData
      }
    )

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(payload.message || '上传失败')
    }

    await response.json()
    uploadSuccess.value = '上传成功，已生成对应的 PKL 与 JSON 文件。'
    uploadFile.value = null
    if (fileInput.value) {
      fileInput.value.value = ''
    }
    await fetchDatasets(selectedProject.value)
  } catch (err) {
    uploadError.value = err instanceof Error ? err.message : '上传失败'
  } finally {
    uploading.value = false
  }
}

const formatTimestamp = (timestamp) => {
  if (!timestamp) return '未知时间'
  try {
    return new Date(timestamp).toLocaleString()
  } catch (err) {
    return timestamp
  }
}

onMounted(fetchProjects)
</script>

<style scoped>
.data-manager {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 2.5rem;
}

.data-manager__projects {
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(12px);
  border-radius: 24px;
  padding: 2rem 1.75rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.data-manager__projects-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.data-manager__projects-header h2 {
  margin: 0;
  font-size: 1.2rem;
}

.data-manager__projects-header button {
  border: none;
  background: rgba(59, 130, 246, 0.1);
  color: #2563eb;
  padding: 0.4rem 0.8rem;
  border-radius: 12px;
  font-weight: 600;
  cursor: pointer;
}

.data-manager__project-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.data-manager__project-item button {
  width: 100%;
  border: none;
  border-radius: 16px;
  padding: 0.85rem 1rem;
  background: rgba(248, 250, 252, 0.9);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.35rem;
  text-align: left;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.data-manager__project-item button:hover {
  transform: translateX(3px);
  box-shadow: 0 14px 35px rgba(15, 23, 42, 0.12);
}

.data-manager__project-item--active button {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.25), rgba(14, 116, 144, 0.25));
  color: #0f172a;
  box-shadow: 0 20px 45px rgba(59, 130, 246, 0.25);
}

.project-name {
  font-weight: 600;
}

.project-updated {
  font-size: 0.75rem;
  color: #64748b;
}

.data-manager__empty {
  margin: 0;
  font-size: 0.9rem;
  color: #64748b;
}

.data-manager__content {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.data-manager__header h1 {
  margin: 0;
  font-size: 1.75rem;
}

.data-manager__header p {
  margin: 0.4rem 0 0;
  color: #475569;
  max-width: 640px;
}

.data-manager__card {
  background: rgba(255, 255, 255, 0.92);
  border-radius: 24px;
  padding: 2rem;
  border: 1px solid rgba(148, 163, 184, 0.16);
  box-shadow: 0 25px 50px -20px rgba(15, 23, 42, 0.2);
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.data-manager__card-header {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.data-manager__card-header h2 {
  margin: 0;
}

.data-manager__card-description {
  margin: 0;
  color: #475569;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.2rem 0.7rem;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
  font-size: 0.75rem;
  font-weight: 600;
}

.badge--muted {
  background: rgba(15, 23, 42, 0.06);
  color: #0f172a;
}

.upload-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.upload-form__input {
  border: 1px dashed rgba(99, 102, 241, 0.4);
  border-radius: 18px;
  padding: 1.5rem;
  display: flex;
  justify-content: center;
  align-items: center;
  background: rgba(239, 246, 255, 0.65);
  cursor: pointer;
  transition: border 0.2s ease, background 0.2s ease;
  color: #475569;
  font-weight: 500;
  text-align: center;
}

.upload-form__input--active {
  border-color: rgba(22, 101, 216, 0.7);
  background: rgba(219, 234, 254, 0.85);
}

.upload-form__input input {
  display: none;
}

.upload-form__actions {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.75rem;
}

.upload-form__actions button {
  border: none;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: #fff;
  padding: 0.65rem 1.5rem;
  border-radius: 16px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 18px 40px rgba(79, 70, 229, 0.25);
}

.upload-form__actions button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  box-shadow: none;
}

.upload-form__message {
  margin: 0;
  font-size: 0.9rem;
}

.upload-form__message--error {
  color: #dc2626;
}

.upload-form__message--success {
  color: #059669;
}

.data-manager__placeholder {
  margin: 0;
  color: #64748b;
}

.data-manager__placeholder--error {
  color: #dc2626;
}

.dataset-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.dataset-list__item {
  padding: 1.5rem;
  border-radius: 20px;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.16);
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.dataset-list__header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  font-weight: 600;
}

.dataset-list__header h3 {
  margin: 0;
}

.dataset-list__header span {
  color: #64748b;
  font-weight: 500;
}

.dataset-list__meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.75rem;
  margin: 0;
}

.dataset-list__meta div {
  background: rgba(255, 255, 255, 0.65);
  border-radius: 14px;
  padding: 0.75rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.dataset-list__meta dt {
  font-size: 0.75rem;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.dataset-list__meta dd {
  margin: 0;
  word-break: break-all;
}

.dataset-list__columns {
  cursor: pointer;
}

.dataset-list__columns summary {
  font-weight: 600;
  color: #2563eb;
}

.dataset-list__columns p {
  margin: 0.5rem 0 0;
  color: #475569;
  word-break: break-word;
}

@media (max-width: 960px) {
  .data-manager {
    grid-template-columns: 1fr;
  }

  .data-manager__projects {
    flex-direction: row;
    flex-wrap: wrap;
    align-items: flex-start;
  }

  .data-manager__project-list {
    flex: 1;
    max-height: 220px;
    overflow-y: auto;
  }
}

@media (max-width: 640px) {
  .data-manager {
    gap: 1.5rem;
  }

  .data-manager__projects {
    padding: 1.5rem 1.25rem;
  }

  .data-manager__card {
    padding: 1.5rem;
    border-radius: 20px;
  }
}
</style>

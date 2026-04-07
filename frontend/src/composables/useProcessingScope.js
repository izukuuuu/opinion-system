import { computed, ref, watch } from 'vue'
import { useApiBase } from './useApiBase'
import { useTopicCreationProject } from './useTopicCreationProject'

export function useProcessingScope() {
  const { callApi } = useApiBase()
  const {
    projectOptions,
    projectsLoading,
    projectsError,
    selectedProjectName,
    loadProjects,
    refreshProjects
  } = useTopicCreationProject()

  const datasets = ref([])
  const datasetsLoading = ref(false)
  const datasetsError = ref('')
  const selectedDatasetId = ref('')
  const lastFetchedProjectName = ref('')

  const databases = ref([])
  const databasesLoading = ref(false)
  const databasesError = ref('')
  const selectedDatabase = ref('')

  const currentProjectName = computed(() => String(selectedProjectName.value || '').trim())

  const datasetOptions = computed(() =>
    datasets.value.map((item) => {
      const name = item.display_name || item.id
      const parts = [name]
      if (item.topic_label) parts.push(`专题：${item.topic_label}`)
      if (item.stored_at) parts.push(`更新于 ${formatTimestamp(item.stored_at)}`)
      return {
        id: item.id,
        label: parts.join(' · '),
        raw: item
      }
    })
  )

  const databaseOptions = computed(() =>
    databases.value.map((item) => ({
      name: String(item?.name || '').trim(),
      tableCount: Number(item?.table_count || item?.tables?.length || 0),
      totalRows: Number(item?.total_rows || 0),
      tables: Array.isArray(item?.tables) ? item.tables : [],
      raw: item
    })).filter((item) => item.name)
  )

  const activeDatabase = computed(() =>
    databaseOptions.value.find((item) => item.name === selectedDatabase.value) || null
  )

  const tableOptions = computed(() =>
    (activeDatabase.value?.tables || []).map((table) => ({
      name: String(table?.name || '').trim(),
      rowCount: Number(table?.record_count ?? table?.row_count ?? 0),
      raw: table
    })).filter((item) => item.name)
  )

  async function loadDatasets(projectName = currentProjectName.value, { force = false } = {}) {
    const trimmed = String(projectName || '').trim()
    if (!trimmed) {
      datasets.value = []
      selectedDatasetId.value = ''
      lastFetchedProjectName.value = ''
      return
    }
    if (!force && lastFetchedProjectName.value === trimmed && datasets.value.length) {
      return
    }
    datasetsLoading.value = true
    datasetsError.value = ''
    try {
      const response = await callApi(`/api/projects/${encodeURIComponent(trimmed)}/datasets`)
      if (response?.status !== 'ok') {
        throw new Error(response?.message || '读取数据集失败')
      }
      const items = Array.isArray(response.datasets) ? response.datasets : []
      datasets.value = items
      lastFetchedProjectName.value = trimmed
      if (selectedDatasetId.value && items.some((item) => item.id === selectedDatasetId.value)) {
        return
      }
      selectedDatasetId.value = items[0]?.id || ''
    } catch (error) {
      datasets.value = []
      selectedDatasetId.value = ''
      lastFetchedProjectName.value = ''
      datasetsError.value = error instanceof Error ? error.message : '读取数据集失败'
    } finally {
      datasetsLoading.value = false
    }
  }

  async function refreshDatasets() {
    await loadDatasets(currentProjectName.value, { force: true })
  }

  async function loadDatabases() {
    if (databasesLoading.value) return
    databasesLoading.value = true
    databasesError.value = ''
    try {
      const response = await callApi('/api/query', {
        method: 'POST',
        body: JSON.stringify({ include_counts: true })
      })
      if (response?.status !== 'ok') {
        throw new Error(response?.message || '读取数据库列表失败')
      }
      const items = Array.isArray(response?.data?.databases) ? response.data.databases : []
      databases.value = items
      if (selectedDatabase.value && items.some((item) => item?.name === selectedDatabase.value)) {
        return
      }
      selectedDatabase.value = items[0]?.name || ''
    } catch (error) {
      databases.value = []
      selectedDatabase.value = ''
      databasesError.value = error instanceof Error ? error.message : '读取数据库列表失败'
    } finally {
      databasesLoading.value = false
    }
  }

  watch(currentProjectName, (value) => {
    if (!value) {
      datasets.value = []
      selectedDatasetId.value = ''
      lastFetchedProjectName.value = ''
      return
    }
    loadDatasets(value)
  }, { immediate: true })

  return {
    callApi,
    currentProjectName,
    projectOptions,
    projectsLoading,
    projectsError,
    selectedProjectName,
    loadProjects,
    refreshProjects,
    datasets,
    datasetOptions,
    datasetsLoading,
    datasetsError,
    selectedDatasetId,
    loadDatasets,
    refreshDatasets,
    databases,
    databaseOptions,
    databasesLoading,
    databasesError,
    selectedDatabase,
    activeDatabase,
    tableOptions,
    loadDatabases
  }
}

function formatTimestamp(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', { hour12: false })
}

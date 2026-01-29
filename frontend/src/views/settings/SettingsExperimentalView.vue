<template>
  <div class="space-y-8">
    <header class="space-y-2">
      <div class="flex items-center gap-2">
        <h1 class="text-2xl font-semibold text-primary">实验性功能</h1>
        <span class="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">Beta</span>
      </div>
      <p class="text-sm text-secondary">
        这些功能正在开发中，可能不稳定。用于准备 PostgreSQL 迁移和统一项目管理。
      </p>
    </header>

    <!-- 远程专题快照 -->
    <section class="card-surface space-y-4 p-6">
      <header class="flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold text-primary">远程专题快照</h2>
          <p class="text-sm text-secondary">从远程数据库获取专题列表并保存到本地</p>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full bg-brand px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="snapshotLoading"
          @click="fetchRemoteTopics"
        >
          <ArrowPathIcon v-if="snapshotLoading" class="h-4 w-4 animate-spin" />
          <CloudArrowDownIcon v-else class="h-4 w-4" />
          {{ snapshotLoading ? '获取中...' : '获取远程专题' }}
        </button>
      </header>

      <div v-if="snapshotError" class="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-600">
        {{ snapshotError }}
      </div>

      <div v-if="remoteTopics.length" class="space-y-3">
        <div class="flex items-center justify-between text-sm text-secondary">
          <span>共 {{ remoteTopics.length }} 个远程专题</span>
          <span v-if="snapshotTime">快照时间：{{ snapshotTime }}</span>
        </div>
        <div class="max-h-64 overflow-y-auto rounded-2xl border border-soft">
          <table class="min-w-full divide-y divide-soft text-sm">
            <thead class="bg-surface-muted">
              <tr>
                <th class="px-4 py-2 text-left font-medium text-secondary">专题名称</th>
                <th class="px-4 py-2 text-left font-medium text-secondary">数据量</th>
                <th class="px-4 py-2 text-left font-medium text-secondary">映射状态</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-soft bg-white">
              <tr v-for="topic in remoteTopics" :key="topic.name" class="hover:bg-surface-muted/50">
                <td class="px-4 py-2 font-medium text-primary">{{ topic.name }}</td>
                <td class="px-4 py-2 text-secondary">{{ topic.count ?? '—' }}</td>
                <td class="px-4 py-2">
                  <span
                    :class="[
                      'inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
                      getMappingForTopic(topic.name) ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
                    ]"
                  >
                    {{ getMappingForTopic(topic.name) ? '已映射' : '未映射' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="flex gap-2">
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-sm font-medium text-secondary transition hover:border-brand-soft hover:text-brand-600"
            @click="saveSnapshotToLocal"
          >
            <ArrowDownTrayIcon class="h-4 w-4" />
            保存到本地
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-sm font-medium text-secondary transition hover:border-brand-soft hover:text-brand-600"
            @click="exportSnapshotAsJson"
          >
            <DocumentArrowDownIcon class="h-4 w-4" />
            导出 JSON
          </button>
        </div>
      </div>

      <div v-else-if="!snapshotLoading" class="rounded-2xl bg-surface-muted px-4 py-6 text-center text-sm text-secondary">
        点击上方按钮获取远程专题列表
      </div>
    </section>

    <!-- 继续下一部分 -->

    <!-- 本地项目列表 -->
    <section class="card-surface space-y-4 p-6">
      <header class="flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold text-primary">本地项目列表</h2>
          <p class="text-sm text-secondary">当前系统中的本地项目</p>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full border border-soft px-4 py-2 text-sm font-medium text-secondary transition hover:border-brand-soft hover:text-brand-600 disabled:opacity-50"
          :disabled="projectsLoading"
          @click="fetchLocalProjects"
        >
          <ArrowPathIcon v-if="projectsLoading" class="h-4 w-4 animate-spin" />
          {{ projectsLoading ? '加载中...' : '刷新列表' }}
        </button>
      </header>

      <div v-if="projectsError" class="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-600">
        {{ projectsError }}
      </div>

      <div v-if="localProjects.length" class="max-h-48 overflow-y-auto rounded-2xl border border-soft">
        <table class="min-w-full divide-y divide-soft text-sm">
          <thead class="bg-surface-muted">
            <tr>
              <th class="px-4 py-2 text-left font-medium text-secondary">项目名称</th>
              <th class="px-4 py-2 text-left font-medium text-secondary">标识</th>
              <th class="px-4 py-2 text-left font-medium text-secondary">已映射专题</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-soft bg-white">
            <tr v-for="project in localProjects" :key="project.name" class="hover:bg-surface-muted/50">
              <td class="px-4 py-2 font-medium text-primary">{{ project.display_name || project.name }}</td>
              <td class="px-4 py-2 text-secondary">{{ project.slug || project.name }}</td>
              <td class="px-4 py-2 text-secondary">{{ getMappingsForProject(project.name).length || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else-if="!projectsLoading" class="rounded-2xl bg-surface-muted px-4 py-6 text-center text-sm text-secondary">
        暂无本地项目，请先在项目管理中创建
      </div>
    </section>

    <!-- 映射管理 -->
    <section class="card-surface space-y-4 p-6">
      <header>
        <h2 class="text-lg font-semibold text-primary">专题映射管理</h2>
        <p class="text-sm text-secondary">建立本地项目与远程专题的对应关系</p>
      </header>

      <!-- 添加映射表单 -->
      <div class="rounded-2xl border border-soft bg-surface-muted/50 p-4">
        <h3 class="mb-3 text-sm font-medium text-primary">添加新映射</h3>
        <div class="grid gap-3 sm:grid-cols-3">
          <label class="space-y-1">
            <span class="text-xs text-secondary">本地项目</span>
            <select
              v-model="newMapping.localProject"
              class="w-full rounded-xl border border-soft bg-white px-3 py-2 text-sm"
            >
              <option value="">选择项目...</option>
              <option v-for="p in localProjects" :key="p.name" :value="p.name">
                {{ p.display_name || p.name }}
              </option>
            </select>
          </label>
          <label class="space-y-1">
            <span class="text-xs text-secondary">远程专题</span>
            <select
              v-model="newMapping.remoteTopic"
              class="w-full rounded-xl border border-soft bg-white px-3 py-2 text-sm"
            >
              <option value="">选择专题...</option>
              <option v-for="t in remoteTopics" :key="t.name" :value="t.name">
                {{ t.name }}
              </option>
            </select>
          </label>
          <div class="flex items-end">
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-full bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-600 disabled:opacity-50"
              :disabled="!newMapping.localProject || !newMapping.remoteTopic"
              @click="addMapping"
            >
              <PlusIcon class="h-4 w-4" />
              添加映射
            </button>
          </div>
        </div>
      </div>

      <!-- 映射列表 -->
      <div v-if="topicMappings.length" class="space-y-2">
        <div class="flex items-center justify-between text-sm text-secondary">
          <span>已建立 {{ topicMappings.length }} 个映射</span>
        </div>
        <div class="rounded-2xl border border-soft">
          <table class="min-w-full divide-y divide-soft text-sm">
            <thead class="bg-surface-muted">
              <tr>
                <th class="px-4 py-2 text-left font-medium text-secondary">本地项目</th>
                <th class="px-4 py-2 text-left font-medium text-secondary">远程专题</th>
                <th class="px-4 py-2 text-left font-medium text-secondary">创建时间</th>
                <th class="px-4 py-2 text-right font-medium text-secondary">操作</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-soft bg-white">
              <tr v-for="(mapping, idx) in topicMappings" :key="idx" class="hover:bg-surface-muted/50">
                <td class="px-4 py-2 font-medium text-primary">{{ mapping.localProject }}</td>
                <td class="px-4 py-2 text-secondary">{{ mapping.remoteTopic }}</td>
                <td class="px-4 py-2 text-xs text-muted">{{ mapping.createdAt || '—' }}</td>
                <td class="px-4 py-2 text-right">
                  <button
                    type="button"
                    class="text-rose-500 hover:text-rose-600"
                    @click="removeMapping(idx)"
                  >
                    <TrashIcon class="h-4 w-4" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else class="rounded-2xl bg-surface-muted px-4 py-6 text-center text-sm text-secondary">
        暂无映射关系，请在上方添加
      </div>

      <!-- 导出操作 -->
      <div class="flex flex-wrap gap-2 border-t border-soft pt-4">
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-sm font-medium text-secondary transition hover:border-brand-soft hover:text-brand-600"
          @click="saveMappingsToLocal"
        >
          <ArrowDownTrayIcon class="h-4 w-4" />
          保存映射到本地
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-sm font-medium text-secondary transition hover:border-brand-soft hover:text-brand-600"
          @click="exportMappingsAsJson"
        >
          <DocumentArrowDownIcon class="h-4 w-4" />
          导出映射 JSON
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-sm font-medium text-secondary transition hover:border-brand-soft hover:text-brand-600"
          @click="exportAsSql"
        >
          <CodeBracketIcon class="h-4 w-4" />
          导出 SQL
        </button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import {
  ArrowPathIcon,
  CloudArrowDownIcon,
  ArrowDownTrayIcon,
  DocumentArrowDownIcon,
  PlusIcon,
  TrashIcon,
  CodeBracketIcon
} from '@heroicons/vue/24/outline'
import { useApiBase } from '../../composables/useApiBase'

const { callApi } = useApiBase()

// 远程专题快照状态
const remoteTopics = ref([])
const snapshotLoading = ref(false)
const snapshotError = ref('')
const snapshotTime = ref('')

// 本地项目列表
const localProjects = ref([])
const projectsLoading = ref(false)
const projectsError = ref('')

// 映射关系
const topicMappings = ref([])

// 新映射表单
const newMapping = reactive({
  localProject: '',
  remoteTopic: ''
})

// 从 localStorage 加载已保存的数据
const STORAGE_KEY_TOPICS = 'opinion-system-remote-topics-snapshot'
const STORAGE_KEY_MAPPINGS = 'opinion-system-topic-mappings'

const loadFromStorage = () => {
  try {
    const savedTopics = localStorage.getItem(STORAGE_KEY_TOPICS)
    if (savedTopics) {
      const parsed = JSON.parse(savedTopics)
      remoteTopics.value = parsed.topics || []
      snapshotTime.value = parsed.timestamp || ''
    }
    const savedMappings = localStorage.getItem(STORAGE_KEY_MAPPINGS)
    if (savedMappings) {
      topicMappings.value = JSON.parse(savedMappings) || []
    }
  } catch (e) {
    console.error('Failed to load from storage:', e)
  }
}

const getMappingForTopic = (topicName) => {
  return topicMappings.value.find(m => m.remoteTopic === topicName)
}

const getMappingsForProject = (projectName) => {
  return topicMappings.value.filter(m => m.localProject === projectName)
}

const fetchLocalProjects = async () => {
  projectsLoading.value = true
  projectsError.value = ''
  try {
    const response = await callApi('/api/projects', { method: 'GET' })
    const list = response?.projects ?? []
    localProjects.value = list.map(p => ({
      name: p.name || '',
      slug: p.slug || p.name || '',
      display_name: p.display_name || p.metadata?.display_name || p.name || ''
    })).filter(p => p.name)
  } catch (error) {
    projectsError.value = error instanceof Error ? error.message : '获取本地项目失败'
  } finally {
    projectsLoading.value = false
  }
}

const fetchRemoteTopics = async () => {
  snapshotLoading.value = true
  snapshotError.value = ''
  try {
    const response = await callApi('/api/query', {
      method: 'POST',
      body: JSON.stringify({ include_counts: true })
    })
    const databases = response?.data?.databases ?? []
    remoteTopics.value = databases.map(db => ({
      name: String(db?.name || '').trim(),
      count: db?.count ?? null
    })).filter(t => t.name)
    snapshotTime.value = new Date().toLocaleString()
  } catch (error) {
    snapshotError.value = error instanceof Error ? error.message : '获取远程专题失败'
  } finally {
    snapshotLoading.value = false
  }
}

const saveSnapshotToLocal = () => {
  try {
    localStorage.setItem(STORAGE_KEY_TOPICS, JSON.stringify({
      topics: remoteTopics.value,
      timestamp: snapshotTime.value
    }))
    alert('快照已保存到本地存储')
  } catch (e) {
    alert('保存失败: ' + e.message)
  }
}

const exportSnapshotAsJson = () => {
  const data = {
    topics: remoteTopics.value,
    timestamp: snapshotTime.value,
    exportedAt: new Date().toISOString()
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `remote-topics-snapshot-${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

const addMapping = () => {
  if (!newMapping.localProject || !newMapping.remoteTopic) return
  const exists = topicMappings.value.some(
    m => m.localProject === newMapping.localProject && m.remoteTopic === newMapping.remoteTopic
  )
  if (exists) {
    alert('该映射已存在')
    return
  }
  topicMappings.value.push({
    localProject: newMapping.localProject,
    remoteTopic: newMapping.remoteTopic,
    createdAt: new Date().toLocaleString()
  })
  newMapping.localProject = ''
  newMapping.remoteTopic = ''
}

const removeMapping = (index) => {
  topicMappings.value.splice(index, 1)
}

const saveMappingsToLocal = () => {
  try {
    localStorage.setItem(STORAGE_KEY_MAPPINGS, JSON.stringify(topicMappings.value))
    alert('映射已保存到本地存储')
  } catch (e) {
    alert('保存失败: ' + e.message)
  }
}

const exportMappingsAsJson = () => {
  const data = {
    mappings: topicMappings.value,
    exportedAt: new Date().toISOString()
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `topic-mappings-${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

const exportAsSql = () => {
  const lines = [
    '-- Topic Mappings Export',
    `-- Generated at: ${new Date().toISOString()}`,
    '',
    '-- Insert into topic_mappings table',
  ]
  topicMappings.value.forEach(m => {
    const sql = `INSERT INTO topic_mappings (local_project, remote_topic, mapping_type, created_at) VALUES ('${m.localProject}', '${m.remoteTopic}', 'manual', NOW());`
    lines.push(sql)
  })
  const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `topic-mappings-${new Date().toISOString().slice(0, 10)}.sql`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(() => {
  loadFromStorage()
  fetchLocalProjects()
})
</script>

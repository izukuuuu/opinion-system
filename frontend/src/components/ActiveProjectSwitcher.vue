<template>
  <div ref="dropdownRef" class="relative inline-flex text-sm">
    <button
      type="button"
      class="inline-flex items-center gap-2 rounded-md border border-soft bg-surface-muted px-3 py-1.5 text-secondary shadow-sm transition hover:border-brand-soft hover:text-primary focus-ring-accent"
      :aria-expanded="isOpen"
      aria-haspopup="listbox"
      @click.stop="toggleDropdown"
    >
      <BriefcaseIcon class="h-4 w-4 text-muted" />
      <span class="font-medium text-muted">当前项目：</span>
      <span class="font-semibold text-primary">
        {{ displayName }}
      </span>
      <ChevronDownIcon
        class="h-4 w-4 text-muted transition"
        :class="isOpen ? 'rotate-180' : ''"
      />
    </button>

    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 -translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 -translate-y-1"
    >
      <div
        v-if="isOpen"
        class="absolute right-0 top-full z-50 mt-3 w-64 overflow-hidden rounded-md border border-soft bg-surface text-sm shadow-lg"
        role="listbox"
      >
        <div class="flex items-center justify-between border-b border-soft px-3 py-2 text-xs text-muted">
          <span>项目列表</span>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-full border border-soft px-2 py-0.5 text-xs transition hover:border-brand-soft hover:text-brand-600 focus-ring-accent"
            :disabled="loading"
            @click.stop="refreshProjects"
          >
            <ArrowPathIcon
              class="h-3.5 w-3.5"
              :class="loading ? 'animate-spin text-brand-600' : 'text-muted'"
            />
            <span>{{ loading ? '刷新中…' : '刷新' }}</span>
          </button>
        </div>

        <div v-if="error" class="px-3 py-3 text-xs text-rose-600">
          {{ error }}
        </div>

        <div v-else-if="!projects.length && !loading" class="px-3 py-3 text-xs text-muted">
          暂无项目，请前往项目管理创建。
        </div>

        <ul v-else class="max-h-60 overflow-y-auto py-1">
          <li
            v-for="project in projects"
            :key="project.name"
            class="flex cursor-pointer items-center justify-between px-3 py-2 text-sm transition hover:bg-brand-soft/80"
            :class="project.name === selectedName ? 'bg-brand-soft/60 text-brand-600' : 'text-secondary'"
            role="option"
            :aria-selected="project.name === selectedName"
            @click.stop="selectProject(project)"
          >
            <span class="truncate">{{ project.name }}</span>
            <span v-if="project.status" class="ml-2 shrink-0 rounded-full bg-surface-muted px-2 py-0.5 text-xs text-muted">
              {{ statusLabel(project.status) }}
            </span>
          </li>
        </ul>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ArrowPathIcon,
  BriefcaseIcon,
  ChevronDownIcon
} from '@heroicons/vue/24/outline'
import { useActiveProject } from '../composables/useActiveProject'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const { activeProjectName, setActiveProject, clearActiveProject } = useActiveProject()

const projects = ref([])
const loading = ref(false)
const error = ref('')
const isOpen = ref(false)
const selectedName = ref(activeProjectName.value || '')
const dropdownRef = ref(null)

const displayName = computed(() => selectedName.value || '未选择项目')

const statusMap = {
  success: '成功',
  error: '失败'
}

const statusLabel = (status) => statusMap[status] || '进行中'

const updateSelectionFromProjects = () => {
  if (!projects.value.length) {
    selectedName.value = ''
    clearActiveProject()
    return
  }

  const currentName = activeProjectName.value || selectedName.value
  const matched = currentName
    ? projects.value.find((project) => project.name === currentName)
    : null
  const target = matched || projects.value[0]
  selectedName.value = target.name
  setActiveProject(target)
}

const fetchProjects = async () => {
  loading.value = true
  error.value = ''
  try {
    const response = await fetch(`${API_BASE_URL}/projects`)
    if (!response.ok) {
      throw new Error('获取项目列表失败')
    }
    const data = await response.json()
    projects.value = Array.isArray(data.projects) ? data.projects : []
    updateSelectionFromProjects()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '请求项目列表时出现问题'
  } finally {
    loading.value = false
  }
}

const refreshProjects = async () => {
  if (loading.value) return
  await fetchProjects()
}

const selectProject = (project) => {
  if (!project) return
  if (typeof project === 'string') {
    const matched = projects.value.find((item) => item.name === project)
    if (!matched) {
      selectedName.value = project
      isOpen.value = false
      return
    }
    project = matched
  }
  selectedName.value = project.name
  setActiveProject(project)
  isOpen.value = false
}

const toggleDropdown = () => {
  isOpen.value = !isOpen.value
}

const handleClickOutside = (event) => {
  if (!dropdownRef.value) return
  if (dropdownRef.value.contains(event.target)) return
  isOpen.value = false
}

watch(activeProjectName, (name) => {
  if (!name) {
    selectedName.value = ''
    return
  }
  if (selectedName.value !== name) {
    selectProject(name)
  }
})

onMounted(() => {
  fetchProjects()
  document.addEventListener('click', handleClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

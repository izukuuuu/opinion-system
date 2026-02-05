<template>
  <div class="mx-auto max-w-5xl pt-0 pb-12 space-y-6">
    <form class="space-y-6" @submit.prevent="runSelectedFunctions">
      <!-- Configuration Panel -->
      <section class="card-surface space-y-4 p-6">
        <div class="mb-5 flex items-center justify-between">
          <h2 class="text-lg font-semibold text-primary">基础配置</h2>
          <button type="button"
            class="flex items-center gap-1 text-xs text-brand-600 transition-colors hover:text-brand-700 disabled:opacity-50"
            :disabled="topicsState.loading" @click="loadTopics">
            <ArrowPathIcon class="h-3 w-3" :class="{ 'animate-spin': topicsState.loading }" />
            {{ topicsState.loading ? '正在同步专题...' : '刷新同步' }}
          </button>
        </div>

        <div class="grid gap-6 md:grid-cols-3">
          <!-- Topic Selection -->
          <div class="space-y-2">
            <label class="text-sm font-medium text-secondary">分析专题 (Topic)</label>
            <div class="relative">
              <select v-model="analyzeForm.topic" class="input w-full appearance-none pr-8"
                :disabled="topicsState.loading || !topicOptions.length" required
                @change="changeTopic($event.target.value)">
                <option value="" disabled>请选择远程专题数据源</option>
                <option v-for="option in topicOptions" :key="`analyze-${option}`" :value="option">
                  {{ option }}
                </option>
              </select>
              <div class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted">
                <ChevronUpDownIcon class="h-4 w-4" />
              </div>
            </div>
            <p v-if="topicsState.error" class="text-xs text-danger">{{ topicsState.error }}</p>
          </div>

          <!-- Date Range Selection -->
          <div class="col-span-2 space-y-2">
            <span class="text-sm font-medium text-secondary">分析时间范围 (Date Range)</span>
            <div class="flex items-center gap-4">
              <div class="relative flex-1">
                <input v-model="analyzeForm.start" type="date" class="input w-full" required />
                <span class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted">开始</span>
              </div>
              <span class="text-muted">→</span>
              <div class="relative flex-1">
                <input v-model="analyzeForm.end" type="date" class="input w-full" required />
                <span class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted">结束</span>
              </div>
            </div>
            <div class="flex justify-between text-xs text-muted">
              <span>建议范围：{{ availableRange.start || '...' }} ~ {{ availableRange.end || '...' }}</span>
              <span v-if="availableRange.loading" class="animate-pulse">正在检查数据可用性...</span>
            </div>
          </div>
        </div>
      </section>

      <!-- Analysis Functions Selection - Wrapped in a shadow card -->
      <section class="card-surface space-y-4 p-6">
        <div class="mb-6 flex items-center justify-between">
          <h2 class="text-lg font-semibold text-primary">
            选择分析维度
            <span class="ml-2 text-sm font-normal text-muted">
              已选 {{ selectedFunctions.length }} 项
            </span>
          </h2>
          <div class="flex gap-2">
            <button type="button" class="btn-ghost text-xs" @click="selectAll">全选</button>
            <span class="text-soft">|</span>
            <button type="button" class="btn-ghost text-xs" @click="clearSelection">清空</button>
          </div>
        </div>

        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div v-for="func in analysisFunctions" :key="func.id"
            class="group relative flex cursor-pointer flex-col justify-between rounded-xl border border-soft bg-surface-muted/30 p-4 transition-all"
            :class="{ 'ring-2 ring-brand-500 border-transparent bg-surface': selectedFunctions.includes(func.id) }"
            @click="toggleSelection(func.id)">
            <!-- Checkbox at Top Right -->
            <div class="absolute right-3 top-3 h-5 w-5">
              <input type="checkbox" :value="func.id" v-model="selectedFunctions"
                class="peer h-5 w-5 appearance-none rounded-full border border-soft transition-colors checked:border-transparent checked:bg-brand-500" />
              <CheckIcon class="pointer-events-none absolute inset-0 hidden h-5 w-5 text-white peer-checked:block" />
            </div>

            <div class="mb-3 flex items-start">
              <div class="flex h-10 w-10 items-center justify-center rounded-lg"
                :class="selectedFunctions.includes(func.id) ? 'bg-brand-50 text-brand-600' : 'bg-surface text-secondary group-hover:bg-brand-soft/10'">
                <component :is="getIcon(func.id)" class="h-6 w-6" />
              </div>
            </div>

            <div class="space-y-1">
              <h3 class="font-semibold text-primary group-hover:text-brand-700">{{ func.label }}</h3>
              <p class="text-xs leading-relaxed text-muted line-clamp-2">{{ func.description }}</p>
            </div>

            <!-- Hover Action -->
            <div
              class="mt-4 pt-3 border-t border-dashed border-soft opacity-0 transition-opacity group-hover:opacity-100 flex justify-end">
              <button type="button" class="text-[10px] font-medium text-brand-600 hover:text-brand-800 hover:underline"
                @click.stop="runSingleFunction(func.id)" :disabled="analyzeState.running">
                仅运行此项 &rarr;
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- Logs & Actions - Style Refinement -->
      <section class="card-surface space-y-4 p-6">
        <AnalysisLogList :logs="combinedLogs" class="mb-4 max-h-40 overflow-y-auto"
          empty-label="准备就绪。配置完成后点击下方按钮开始分析任务。" />

        <div class="flex items-center justify-end gap-4 border-t border-soft/50 pt-4">
          <span v-if="analyzeState.running" class="text-sm text-brand-600 animate-pulse font-medium">
            系统任务处理中，请稍候...
          </span>
          <button type="submit" class="btn-primary min-w-[150px] shadow-lg shadow-brand-500/20 py-3 text-base"
            :disabled="analyzeState.running || !selectedFunctions.length">
            <span v-if="analyzeState.running" class="flex items-center gap-2">
              <ArrowPathIcon class="h-5 w-5 animate-spin" />
              正在执行
            </span>
            <span v-else>立即开始分析 ({{ selectedFunctions.length }})</span>
          </button>
        </div>
      </section>
    </form>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import {
  ArrowPathIcon,
  CheckIcon,
  ChevronUpDownIcon
} from '@heroicons/vue/24/solid'
import {
  FaceSmileIcon,
  TagIcon,
  MapIcon,
  KeyIcon,
  UserGroupIcon,
  PresentationChartLineIcon,
  ChartBarIcon
} from '@heroicons/vue/24/outline'

import { useBasicAnalysis } from '../../../composables/useBasicAnalysis'
import AnalysisLogList from '../../../components/analysis/AnalysisLogList.vue'

const {
  topicsState,
  topicOptions,
  fetchLogs,
  loadTopics,
  analyzeForm,
  analyzeState,
  analyzeLogs,
  analysisFunctions,
  selectedFunctions,
  selectAll,
  clearSelection,
  runSelectedFunctions,
  runSingleFunction,
  changeTopic,
  availableRange
} = useBasicAnalysis()

const combinedLogs = computed(() => [...(fetchLogs?.value || []), ...(analyzeLogs?.value || [])])

// Mapping icons to analysis function IDs
const iconMap = {
  attitude: FaceSmileIcon,
  classification: TagIcon,
  geography: MapIcon,
  keywords: KeyIcon,
  publishers: UserGroupIcon,
  trends: PresentationChartLineIcon,
  volume: ChartBarIcon
}

const getIcon = (id) => iconMap[id] || ChartBarIcon

const toggleSelection = (id) => {
  if (analyzeState.running) return
  const idx = selectedFunctions.value.indexOf(id)
  if (idx > -1) {
    selectedFunctions.value.splice(idx, 1)
  } else {
    selectedFunctions.value.push(id)
  }
}

onMounted(() => {
  if (!topicsState.options?.length) {
    loadTopics()
  }
})
</script>

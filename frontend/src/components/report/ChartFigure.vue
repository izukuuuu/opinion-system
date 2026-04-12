<template>
  <AnalysisChartPanel
    :title="title"
    :description="description"
    :option="option"
    :has-data="hasData"
    :empty-message="emptyMessage"
    :is-keywords="isKeywords"
    :all-rows="allRows"
  >
    <template #default>
      <div v-if="showTable" class="overflow-hidden rounded-2xl border border-soft">
        <table class="min-w-full text-sm">
          <thead class="bg-surface-muted text-xs uppercase tracking-wide text-muted">
            <tr>
              <th class="px-3 py-2 text-left">名称</th>
              <th class="px-3 py-2 text-left">数值</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, index) in previewRows"
              :key="`${figureId}-${index}`"
              class="border-t border-soft text-secondary"
            >
              <td class="px-3 py-2">{{ row.displayName ?? row.name ?? row.label ?? row.key ?? row.source ?? '未命名' }}</td>
              <td class="px-3 py-2">{{ row.displayValue ?? row.value ?? row.count ?? row.total ?? row.target ?? '--' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </AnalysisChartPanel>
</template>

<script setup>
import { computed } from 'vue'
import AnalysisChartPanel from '../AnalysisChartPanel.vue'

const props = defineProps({
  contract: {
    type: Object,
    default: () => ({})
  }
})

const figureId = computed(() => String(props.contract?.figure_id || '').trim())
const title = computed(() => String(props.contract?.caption || props.contract?.title || '图表').trim() || '图表')
const description = computed(() => String(props.contract?.description || props.contract?.subtitle || '').trim())
const option = computed(() => (props.contract?.option && typeof props.contract.option === 'object' ? props.contract.option : {}))
const hasData = computed(() => Boolean(props.contract?.hasData))
const emptyMessage = computed(() => String(props.contract?.emptyMessage || '暂无可视化数据').trim() || '暂无可视化数据')
const allRows = computed(() => (Array.isArray(props.contract?.allRows) ? props.contract.allRows : []))
const previewRows = computed(() => (Array.isArray(props.contract?.previewRows) ? props.contract.previewRows : []))
const isKeywords = computed(() => String(props.contract?.functionName || '').trim() === 'keywords')
const showTable = computed(() => {
  if (!hasData.value || !previewRows.value.length) return false
  if (String(props.contract?.intent || '').trim() === 'network') return false
  return true
})
</script>

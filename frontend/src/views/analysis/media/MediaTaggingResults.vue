<template>
  <div class="space-y-6 pb-12">
    <AnalysisPageHeader
      eyebrow="媒体识别与打标"
      title="查看结果"
      description="从历史记录里加载媒体候选列表，完成专题打标并维护共享媒体字典。"
      :meta-items="metaItems"
      :actions="headerActions"
    />

    <AnalysisSectionCard
      title="选择识别记录"
      description="先选择专题和历史记录，也可以直接输入时间范围重新读取。"
    >
      <div class="space-y-4">
        <div class="grid gap-4 lg:grid-cols-[minmax(220px,0.85fr)_minmax(260px,1fr)_minmax(0,1.1fr)]">
          <label class="space-y-2 text-secondary">
            <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">专题</span>
            <AppSelect
              :options="topicSelectOptions"
              :value="viewSelection.topic"
              :disabled="topicsState.loading || !topicOptions.length"
              @change="handleTopicChange"
            />
          </label>

          <label class="space-y-2 text-secondary">
            <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">历史记录</span>
            <AppSelect
              :options="historySelectOptions"
              :value="selectedHistoryId"
              :disabled="historyState.loading || !historySelectOptions.length"
              @change="selectedHistoryId = $event"
            />
          </label>

          <div class="rounded-[1.4rem] border border-dashed border-soft bg-surface-muted px-4 py-4">
            <div class="space-y-1">
              <h3 class="text-sm font-semibold text-primary">手动读取区间</h3>
              <p class="text-sm text-secondary">当你想对照特定区间时，可以直接输入起止日期重新加载。</p>
            </div>
            <div class="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
              <input v-model="viewManualForm.start" type="date" class="input h-11 rounded-2xl" />
              <input v-model="viewManualForm.end" type="date" class="input h-11 rounded-2xl" />
              <button
                type="button"
                class="btn-secondary h-11 rounded-full px-4"
                :disabled="resultsState.loading || !viewManualForm.topic"
                @click="loadResultsFromManual"
              >
                {{ resultsState.loading ? '读取中…' : '读取结果' }}
              </button>
            </div>
          </div>
        </div>

        <div v-if="historyState.error" class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">
          {{ historyState.error }}
        </div>
        <div v-if="resultsState.error" class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">
          {{ resultsState.error }}
        </div>
      </div>
    </AnalysisSectionCard>

    <AnalysisSectionCard
      title="候选媒体维护台"
      description="先筛选和确认候选媒体标签，再把变更批量写回本次专题结果。"
    >
      <div class="space-y-5">
        <div class="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
          <div class="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
            <label class="space-y-2 text-secondary">
              <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">搜索</span>
              <input
                v-model="filters.search"
                type="text"
                class="input h-11 rounded-2xl"
                placeholder="搜索媒体名、命中字典或平台"
              />
            </label>
            <div class="space-y-2">
              <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">标签筛选</span>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="option in labelOptions"
                  :key="option.value"
                  type="button"
                  class="rounded-full border px-4 py-2 text-sm font-medium transition"
                  :class="filters.label === option.value
                    ? 'border-brand-soft bg-brand-soft-muted text-brand-700'
                    : 'border-soft bg-surface text-secondary hover:border-brand-soft hover:bg-surface-muted'"
                  @click="filters.label = option.value"
                >
                  {{ option.label }}
                </button>
              </div>
            </div>
          </div>

          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="analysis-toolbar__action analysis-toolbar__action--ghost"
              :disabled="!filteredCandidates.length"
              @click="applyLabelToFilteredCandidates('official_media')"
            >
              <span>当前筛选标为官方媒体</span>
            </button>
            <button
              type="button"
              class="analysis-toolbar__action analysis-toolbar__action--ghost"
              :disabled="!filteredCandidates.length"
              @click="applyLabelToFilteredCandidates('local_media')"
            >
              <span>当前筛选标为地方媒体</span>
            </button>
            <button
              type="button"
              class="analysis-toolbar__action analysis-toolbar__action--secondary"
              :disabled="!hasPendingChanges"
              @click="clearAllCandidateChanges"
            >
              <span>清空暂存</span>
            </button>
          </div>
        </div>

        <div class="grid gap-4 md:grid-cols-4">
          <article
            v-for="item in summaryCards"
            :key="item.label"
            class="card-surface px-4 py-4"
          >
            <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">{{ item.label }}</p>
            <p class="mt-2 text-2xl font-semibold text-primary">{{ item.value }}</p>
            <p class="mt-1 text-sm text-secondary">{{ item.description }}</p>
          </article>
        </div>

        <div v-if="resultsState.saveNotice" class="rounded-2xl border border-brand-soft bg-brand-soft-muted px-4 py-3 text-sm text-secondary">
          {{ resultsState.saveNotice }}
        </div>
        <div v-if="resultsState.saveError" class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">
          {{ resultsState.saveError }}
        </div>

        <div class="overflow-hidden rounded-[1.6rem] border border-soft">
          <div class="overflow-x-auto">
            <table class="min-w-[1240px] text-sm">
              <thead class="bg-surface-muted text-xs uppercase tracking-[0.18em] text-muted">
                <tr>
                  <th class="px-4 py-3 text-left">publisher_name</th>
                  <th class="px-4 py-3 text-left">publish_count</th>
                  <th class="px-4 py-3 text-left">matched_registry_name</th>
                  <th class="px-4 py-3 text-left">current_label</th>
                  <th class="px-4 py-3 text-left">sample_count</th>
                  <th class="px-4 py-3 text-left">latest_published_at</th>
                  <th class="px-4 py-3 text-left">platforms</th>
                  <th class="px-4 py-3 text-left">samples</th>
                  <th class="px-4 py-3 text-left">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="candidate in filteredCandidates"
                  :key="candidate.publisher_name"
                  class="border-t border-soft align-top"
                >
                  <td class="px-4 py-4">
                    <div class="space-y-1">
                      <p class="font-semibold text-primary">{{ candidate.publisher_name }}</p>
                      <p v-if="candidate._dirty" class="text-xs text-brand-700">有未保存改动</p>
                    </div>
                  </td>
                  <td class="px-4 py-4 text-secondary">{{ candidate.publish_count }}</td>
                  <td class="px-4 py-4">
                    <span class="text-secondary">{{ candidate.matched_registry_name || '未命中共享字典' }}</span>
                  </td>
                  <td class="px-4 py-4">
                    <span class="inline-flex rounded-full border px-3 py-1 text-xs font-semibold" :class="labelTone(candidate.current_label)">
                      {{ labelText(candidate.current_label) }}
                    </span>
                  </td>
                  <td class="px-4 py-4 text-secondary">{{ candidate.sample_count }}</td>
                  <td class="px-4 py-4 text-secondary">{{ candidate.latest_published_at || '--' }}</td>
                  <td class="px-4 py-4">
                    <div class="flex flex-wrap gap-2">
                      <span
                        v-for="platform in candidate.platforms"
                        :key="platform"
                        class="inline-flex rounded-full border border-soft bg-surface px-2.5 py-1 text-xs text-secondary"
                      >
                        {{ platform }}
                      </span>
                      <span v-if="!candidate.platforms?.length" class="text-secondary">--</span>
                    </div>
                  </td>
                  <td class="px-4 py-4">
                    <div class="space-y-2">
                      <div
                        v-for="(sample, index) in candidate.samples?.slice(0, 2) || []"
                        :key="`${candidate.publisher_name}-${index}`"
                        class="rounded-2xl border border-soft bg-surface px-3 py-2"
                      >
                        <a
                          v-if="sample.url"
                          :href="sample.url"
                          target="_blank"
                          rel="noreferrer"
                          class="line-clamp-2 text-primary underline-offset-2 hover:underline"
                        >
                          {{ sample.title || sample.url }}
                        </a>
                        <p v-else class="line-clamp-2 text-primary">{{ sample.title || '未提供标题' }}</p>
                        <p class="mt-1 text-xs text-muted">{{ sample.platform || '--' }} · {{ sample.published_at || '--' }}</p>
                      </div>
                      <p v-if="!candidate.samples?.length" class="text-secondary">暂无样本</p>
                    </div>
                  </td>
                  <td class="px-4 py-4">
                    <div class="flex flex-col gap-2">
                      <button
                        type="button"
                        class="rounded-full border px-3 py-1.5 text-xs font-semibold transition"
                        :class="candidate.current_label === 'official_media'
                          ? 'border-brand-soft bg-brand-soft-muted text-brand-700'
                          : 'border-soft bg-surface text-secondary hover:border-brand-soft hover:bg-surface-muted'"
                        @click="stageCandidateLabel(candidate.publisher_name, 'official_media')"
                      >
                        官方媒体
                      </button>
                      <button
                        type="button"
                        class="rounded-full border px-3 py-1.5 text-xs font-semibold transition"
                        :class="candidate.current_label === 'local_media'
                          ? 'border-brand-soft bg-brand-soft-muted text-brand-700'
                          : 'border-soft bg-surface text-secondary hover:border-brand-soft hover:bg-surface-muted'"
                        @click="stageCandidateLabel(candidate.publisher_name, 'local_media')"
                      >
                        地方媒体
                      </button>
                      <button
                        type="button"
                        class="rounded-full border px-3 py-1.5 text-xs font-semibold transition"
                        :class="!candidate.current_label
                          ? 'border-brand-soft bg-brand-soft-muted text-brand-700'
                          : 'border-soft bg-surface text-secondary hover:border-brand-soft hover:bg-surface-muted'"
                        @click="stageCandidateLabel(candidate.publisher_name, '')"
                      >
                        设为未标记
                      </button>
                      <button
                        v-if="candidate._dirty"
                        type="button"
                        class="btn-primary rounded-full px-3 py-1.5 text-xs"
                        :disabled="resultsState.saving"
                        @click="saveCandidateUpdates([candidate.publisher_name])"
                      >
                        保存此条
                      </button>
                      <button
                        v-else
                        type="button"
                        class="analysis-toolbar__action analysis-toolbar__action--ghost text-xs"
                        @click="openRegistryModalForCandidate(candidate)"
                      >
                        编辑字典
                      </button>
                    </div>
                  </td>
                </tr>
                <tr v-if="!filteredCandidates.length">
                  <td colspan="9" class="px-4 py-10 text-center text-sm text-muted">
                    当前条件下还没有可展示的候选媒体。
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="flex flex-col gap-3 rounded-[1.5rem] border border-soft bg-surface-muted px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div class="space-y-1">
            <p class="text-sm font-medium text-primary">
              {{ hasPendingChanges ? `待保存 ${pendingUpdates.length} 条标签变更。` : '当前没有未保存的标签变更。' }}
            </p>
            <p class="text-sm text-secondary">保存后，专题结果和共享字典会一起更新。</p>
          </div>
          <button
            type="button"
            class="btn-primary inline-flex min-w-[170px] items-center justify-center gap-2 rounded-full px-5 py-3"
            :disabled="!hasPendingChanges || resultsState.saving"
            @click="saveCandidateUpdates()"
          >
            <ArrowPathIcon v-if="resultsState.saving" class="h-5 w-5 animate-spin" />
            <span>{{ resultsState.saving ? '保存中…' : `批量保存 (${pendingUpdates.length})` }}</span>
          </button>
        </div>
      </div>
    </AnalysisSectionCard>

    <AnalysisSectionCard
      title="共享媒体字典"
      description="这里维护传统媒体名称、别名和正式标签，方便后续专题直接复用。"
      :actions="registryActions"
      tone="soft"
    >
      <div class="space-y-4">
        <div v-if="resultsState.registryNotice" class="rounded-2xl border border-brand-soft bg-brand-soft-muted px-4 py-3 text-sm text-secondary">
          {{ resultsState.registryNotice }}
        </div>
        <div v-if="resultsState.registryError" class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">
          {{ resultsState.registryError }}
        </div>

        <div class="overflow-hidden rounded-[1.6rem] border border-soft">
          <div class="overflow-x-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-surface-muted text-xs uppercase tracking-[0.18em] text-muted">
                <tr>
                  <th class="px-4 py-3 text-left">名称</th>
                  <th class="px-4 py-3 text-left">别名</th>
                  <th class="px-4 py-3 text-left">标签</th>
                  <th class="px-4 py-3 text-left">状态</th>
                  <th class="px-4 py-3 text-left">备注</th>
                  <th class="px-4 py-3 text-left">最近更新</th>
                  <th class="px-4 py-3 text-left">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in filteredRegistryItems"
                  :key="item.id"
                  class="border-t border-soft"
                >
                  <td class="px-4 py-4 font-semibold text-primary">{{ item.name }}</td>
                  <td class="px-4 py-4 text-secondary">{{ item.aliases?.join('、') || '--' }}</td>
                  <td class="px-4 py-4">
                    <span class="inline-flex rounded-full border px-3 py-1 text-xs font-semibold" :class="labelTone(item.media_level)">
                      {{ labelText(item.media_level) }}
                    </span>
                  </td>
                  <td class="px-4 py-4 text-secondary">{{ item.status || '--' }}</td>
                  <td class="px-4 py-4 text-secondary">{{ item.notes || '--' }}</td>
                  <td class="px-4 py-4 text-secondary">{{ formatTimestamp(item.updated_at) }}</td>
                  <td class="px-4 py-4">
                    <button
                      type="button"
                      class="analysis-toolbar__action analysis-toolbar__action--ghost"
                      @click="openRegistryModal(item)"
                    >
                      <span>编辑</span>
                    </button>
                  </td>
                </tr>
                <tr v-if="!filteredRegistryItems.length">
                  <td colspan="7" class="px-4 py-8 text-center text-sm text-muted">
                    当前筛选条件下没有共享字典条目。
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </AnalysisSectionCard>

    <AppModal
      v-model="registryModalOpen"
      eyebrow="共享媒体字典"
      :title="registryModalTitle"
      description="维护正式名称、别名和标签后，后续专题识别会优先沿用这里的口径。"
      confirm-text="保存字典条目"
      confirm-loading-text="保存中…"
      width="max-w-2xl"
      scrollable
      :confirm-disabled="!registryForm.name.trim()"
      :confirm-loading="resultsState.registrySaving"
      @confirm="submitRegistryModal"
      @cancel="resetRegistryModal"
    >
      <div class="grid gap-4 md:grid-cols-2">
        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">媒体名称</span>
          <input v-model="registryForm.name" type="text" class="input h-11 rounded-2xl" placeholder="例如：人民日报" />
        </label>

        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">正式标签</span>
          <AppSelect
            :options="registryLabelSelectOptions"
            :value="registryForm.media_level"
            @change="registryForm.media_level = $event"
          />
        </label>

        <label class="space-y-2 text-secondary md:col-span-2">
          <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">别名</span>
          <textarea
            v-model="registryForm.aliases"
            class="input min-h-[120px] rounded-2xl py-3"
            placeholder="多个别名可用逗号、分号或换行分隔"
          />
        </label>

        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">状态</span>
          <AppSelect
            :options="registryStatusOptions"
            :value="registryForm.status"
            @change="registryForm.status = $event"
          />
        </label>

        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">备注</span>
          <input v-model="registryForm.notes" type="text" class="input h-11 rounded-2xl" placeholder="可记录识别口径或说明" />
        </label>
      </div>
    </AppModal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import {
  ArrowPathIcon,
  BookOpenIcon,
  PencilSquareIcon,
  SwatchIcon,
  TableCellsIcon
} from '@heroicons/vue/24/outline'
import AppModal from '../../../components/AppModal.vue'
import AppSelect from '../../../components/AppSelect.vue'
import AnalysisPageHeader from '../../../components/analysis/AnalysisPageHeader.vue'
import AnalysisSectionCard from '../../../components/analysis/AnalysisSectionCard.vue'
import { useMediaTagging } from '../../../composables/useMediaTagging'

const {
  topicsState,
  topicOptions,
  historyState,
  historyRecords,
  selectedHistoryId,
  viewSelection,
  viewManualForm,
  resultsState,
  filters,
  resultSummary,
  currentRange,
  filteredCandidates,
  filteredRegistryItems,
  candidateStats,
  hasPendingChanges,
  pendingUpdates,
  registryItems,
  loadResultsFromManual,
  loadRegistry,
  loadResults,
  stageCandidateLabel,
  applyLabelToFilteredCandidates,
  clearAllCandidateChanges,
  saveCandidateUpdates,
  saveRegistryItem,
  changeTopic
} = useMediaTagging()

const registryModalOpen = ref(false)
const registryForm = reactive({
  id: '',
  name: '',
  aliases: '',
  media_level: '',
  status: 'draft',
  notes: ''
})

const labelOptions = [
  { value: 'all', label: '全部' },
  { value: 'official_media', label: '官方媒体' },
  { value: 'local_media', label: '地方媒体' },
  { value: 'unlabeled', label: '未标记' }
]

const topicSelectOptions = computed(() =>
  topicOptions.value.map((item) => ({ value: item, label: item }))
)

const historySelectOptions = computed(() =>
  historyRecords.value.map((item) => ({
    value: item.id,
    label: `${item.start} → ${item.end}`
  }))
)

const selectedRecord = computed(() =>
  historyRecords.value.find((item) => item.id === selectedHistoryId.value) || null
)

const metaItems = computed(() => {
  const items = []
  if (viewSelection.topic) {
    items.push({ label: '当前专题', value: viewSelection.topic, icon: BookOpenIcon })
  }
  if (currentRange.value?.start) {
    items.push({
      label: '结果区间',
      value: `${currentRange.value.start} 至 ${currentRange.value.end || currentRange.value.start}`,
      icon: TableCellsIcon
    })
  }
  if (resultSummary.value) {
    items.push({
      label: '候选媒体',
      value: `${resultSummary.value.total_candidates || 0} 条`,
      icon: SwatchIcon
    })
  }
  return items
})

const summaryCards = computed(() => [
  {
    label: '候选总数',
    value: candidateStats.value.total,
    description: '当前结果里共识别出的媒体候选'
  },
  {
    label: '官方媒体',
    value: candidateStats.value.official,
    description: '已确认进入正式集合的官方媒体'
  },
  {
    label: '地方媒体',
    value: candidateStats.value.local,
    description: '已确认进入正式集合的地方媒体'
  },
  {
    label: '待确认',
    value: candidateStats.value.unlabeled,
    description: '还没有打正式标签的候选媒体'
  }
])

const headerActions = computed(() => [
  {
    label: '刷新结果',
    variant: 'ghost',
    icon: ArrowPathIcon,
    onClick: () => loadResults()
  }
])

const registryActions = computed(() => [
  {
    label: resultsState.registryLoading ? '同步中…' : '刷新字典',
    variant: 'ghost',
    icon: ArrowPathIcon,
    onClick: () => loadRegistry()
  },
  {
    label: '新增条目',
    variant: 'secondary',
    icon: PencilSquareIcon,
    onClick: () => openRegistryModal()
  }
])

const registryModalTitle = computed(() =>
  registryForm.id ? '编辑共享媒体条目' : '新增共享媒体条目'
)

const registryLabelSelectOptions = [
  { value: '', label: '未标记' },
  { value: 'official_media', label: '官方媒体' },
  { value: 'local_media', label: '地方媒体' }
]

const registryStatusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'active', label: '启用' }
]

const handleTopicChange = (value) => {
  changeTopic(value)
  filters.search = ''
  filters.label = 'all'
}

const labelText = (value) => {
  if (value === 'official_media') return '官方媒体'
  if (value === 'local_media') return '地方媒体'
  return '未标记'
}

const labelTone = (value) => {
  if (value === 'official_media') return 'border-brand-soft bg-brand-soft-muted text-brand-700'
  if (value === 'local_media') return 'border-soft bg-surface-muted text-secondary'
  return 'border-soft bg-surface text-muted'
}

const formatTimestamp = (value) => {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function resetRegistryModal() {
  registryForm.id = ''
  registryForm.name = ''
  registryForm.aliases = ''
  registryForm.media_level = ''
  registryForm.status = 'draft'
  registryForm.notes = ''
}

function openRegistryModal(item = null) {
  resetRegistryModal()
  if (item) {
    registryForm.id = String(item.id || '').trim()
    registryForm.name = String(item.name || '').trim()
    registryForm.aliases = Array.isArray(item.aliases) ? item.aliases.join('，') : ''
    registryForm.media_level = String(item.media_level || '').trim()
    registryForm.status = String(item.status || '').trim() || (registryForm.media_level ? 'active' : 'draft')
    registryForm.notes = String(item.notes || '').trim()
  }
  registryModalOpen.value = true
}

function openRegistryModalForCandidate(candidate) {
  const matched = registryItems.value.find((item) => item.name === candidate.matched_registry_name)
  if (matched) {
    openRegistryModal(matched)
    return
  }
  openRegistryModal({
    name: candidate.matched_registry_name || candidate.publisher_name,
    aliases: candidate.publisher_name && candidate.publisher_name !== candidate.matched_registry_name
      ? [candidate.publisher_name]
      : [],
    media_level: candidate.current_label || '',
    status: candidate.current_label ? 'active' : 'draft',
    notes: ''
  })
}

async function submitRegistryModal() {
  const saved = await saveRegistryItem({
    id: registryForm.id,
    name: registryForm.name,
    aliases: registryForm.aliases,
    media_level: registryForm.media_level,
    status: registryForm.status,
    notes: registryForm.notes
  })
  if (saved) {
    registryModalOpen.value = false
    resetRegistryModal()
  }
}

onMounted(async () => {
  await loadRegistry()
  if (selectedRecord.value) {
    await loadResults(selectedRecord.value)
  }
})
</script>

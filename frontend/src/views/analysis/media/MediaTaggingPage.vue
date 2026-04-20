<template>
  <div class="space-y-6 pb-12">
    <!-- ── 顶部：页头 + 配置/状态 ───────────────────────────────────── -->
    <section class="card-surface space-y-5 p-6">
      <!-- 页头 -->
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">媒体打标</p>
          <h2 class="mt-2 text-xl font-semibold text-primary">发布者识别与媒体标注</h2>
          <p class="mt-2 text-sm text-secondary">
            从原始语料识别媒体候选，按发布量排序，打上官方媒体或地方媒体标签后写入共享字典。
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <span v-if="candidateStats.total" class="rounded-full border border-soft bg-surface px-3 py-1.5 text-xs font-semibold text-secondary">
            候选 {{ candidateStats.total }}
          </span>
          <span v-if="candidateStats.hasSuggest" class="rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs font-semibold text-sky-700">
            有建议 {{ candidateStats.hasSuggest }}
          </span>
          <button
            v-if="candidateStats.hasSuggest"
            type="button"
            class="inline-flex items-center gap-1.5 rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs font-semibold text-sky-700 transition hover:bg-sky-100"
            @click="acceptAllSuggestions"
          >
            <CheckIcon class="h-3.5 w-3.5" />
            一键采纳全部
          </button>
          <span v-if="candidateStats.official" class="rounded-full border border-brand-soft bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-700">
            官方 {{ candidateStats.official }}
          </span>
          <span v-if="candidateStats.local" class="rounded-full border border-soft bg-surface-muted px-3 py-1.5 text-xs font-semibold text-secondary">
            地方 {{ candidateStats.local }}
          </span>
          <span v-if="candidateStats.network" class="rounded-full border border-amber-soft bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-700">
            网络 {{ candidateStats.network }}
          </span>
          <span v-if="candidateStats.comprehensive" class="rounded-full border border-emerald-soft bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700">
            综合 {{ candidateStats.comprehensive }}
          </span>
          <span v-if="candidateStats.unlabeled" class="rounded-full border border-dashed border-soft px-3 py-1.5 text-xs font-semibold text-muted">
            未标 {{ candidateStats.unlabeled }}
          </span>
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600"
            @click="loadResults"
          >
            <ArrowPathIcon class="h-4 w-4" />
            刷新结果
          </button>
        </div>
      </div>

      <!-- 配置与状态：两列 -->
      <div class="grid gap-5 xl:grid-cols-[1.1fr,1fr]">
        <!-- 左：识别配置 -->
        <div class="space-y-4 rounded-3xl border border-soft bg-surface-muted/60 p-5">
          <div>
            <h3 class="text-base font-semibold text-primary">识别配置</h3>
            <p class="mt-1 text-sm text-secondary">选择专题和时间范围，再选已有历史或直接运行一次新识别。</p>
          </div>

          <form class="space-y-4" @submit.prevent="handleRun">
            <div class="grid gap-4 sm:grid-cols-2">
              <label class="space-y-2">
                <div class="flex items-center justify-between gap-2">
                  <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">专题</span>
                  <button
                    type="button"
                    class="inline-flex items-center gap-1 rounded-full border border-soft px-2 py-0.5 text-xs text-secondary transition hover:border-brand-soft hover:text-brand-600"
                    :disabled="topicsState.loading"
                    @click="loadTopics"
                  >
                    <ArrowPathIcon class="h-3 w-3" :class="{ 'animate-spin': topicsState.loading }" />
                    {{ topicsState.loading ? '…' : '刷新' }}
                  </button>
                </div>
                <AppSelect
                  :options="topicSelectOptions"
                  :value="runForm.topic"
                  :disabled="topicsState.loading || !topicOptions.length"
                  @change="handleTopicChange"
                />
                <p v-if="topicsState.error" class="text-xs text-danger">{{ topicsState.error }}</p>
              </label>

              <label class="space-y-2">
                <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">历史记录</span>
                <AppSelect
                  :options="historySelectOptions"
                  :value="selectedHistoryId"
                  :disabled="historyState.loading || !historySelectOptions.length"
                  placeholder="-- 选择已有结果 --"
                  @change="selectedHistoryId = $event"
                />
                <p v-if="historyState.error" class="text-xs text-danger">{{ historyState.error }}</p>
              </label>
            </div>

            <div class="grid gap-3 sm:grid-cols-[1fr,auto,1fr] sm:items-end">
              <label class="space-y-2">
                <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">开始日期</span>
                <input v-model="runForm.start" type="date" class="input h-10 w-full" />
              </label>
              <span class="hidden pb-2 text-muted sm:inline">→</span>
              <label class="space-y-2">
                <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">结束日期</span>
                <input v-model="runForm.end" type="date" class="input h-10 w-full" />
              </label>
            </div>

            <div class="rounded-2xl border border-soft bg-white px-4 py-3 text-sm text-secondary">
              <p v-if="availableRange.loading" class="animate-pulse text-xs">正在同步可用范围…</p>
              <p v-else-if="availableRange.error" class="text-xs text-danger">{{ availableRange.error }}</p>
              <p v-else class="text-xs">本地可用：{{ availableRange.start || '--' }} 至 {{ availableRange.end || '--' }}</p>
            </div>

            <button
              type="submit"
              class="btn-primary inline-flex w-full items-center justify-center gap-2"
              :disabled="runState.running || !runForm.topic || !runForm.start"
            >
              <ArrowPathIcon v-if="runState.running" class="h-4 w-4 animate-spin" />
              <MegaphoneIcon v-else class="h-4 w-4" />
              {{ runState.running ? '识别中…' : '运行识别' }}
            </button>
          </form>
        </div>

        <!-- 右：任务状态 -->
        <div class="space-y-4 rounded-3xl border border-soft bg-surface-muted/60 p-5">
          <div>
            <h3 class="text-base font-semibold text-primary">任务状态</h3>
            <p class="mt-1 text-sm text-secondary">当前运行进度与 worker 状态。</p>
          </div>

          <div v-if="taskState.error" class="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
            {{ taskState.error }}
          </div>
          <div v-if="taskState.notice" class="rounded-2xl border border-soft bg-white px-4 py-3 text-sm text-secondary">
            {{ taskState.notice }}
          </div>

          <template v-if="tasks && tasks.length">
            <div
              v-for="task in tasks.slice(0, 3)"
              :key="task.id || task.task_id"
              class="rounded-2xl border border-soft bg-white px-4 py-3"
            >
              <div class="flex items-center justify-between gap-3">
                <p class="text-xs text-muted">{{ task.topic || task.identifier || '媒体识别' }}</p>
                <span
                  class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                  :class="task.status === 'completed' ? 'bg-emerald-50 text-emerald-700'
                    : task.status === 'running' ? 'bg-brand-50 text-brand-700'
                    : task.status === 'failed' || task.status === 'error' ? 'bg-rose-50 text-rose-700'
                    : 'bg-surface-muted text-muted'"
                >
                  {{ task.status === 'completed' ? '已完成'
                    : task.status === 'running' ? '运行中'
                    : task.status === 'queued' ? '排队中'
                    : task.status === 'failed' || task.status === 'error' ? '失败'
                    : task.status || '待开始' }}
                </span>
              </div>
              <p v-if="task.message" class="mt-1 text-xs text-secondary">{{ task.message }}</p>
              <div v-if="task.percentage != null" class="mt-3">
                <div class="flex items-center justify-between gap-2 text-xs text-secondary">
                  <span>进度</span>
                  <span>{{ task.percentage }}%</span>
                </div>
                <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100">
                  <div
                    class="h-full rounded-full bg-brand-600 transition-all duration-500"
                    :style="{ width: `${task.percentage}%` }"
                  />
                </div>
              </div>
              <p v-if="task.candidate_count != null" class="mt-2 text-xs text-secondary">
                候选媒体 {{ task.candidate_count }} 家
              </p>
            </div>
          </template>
          <div v-else class="rounded-2xl border border-dashed border-soft bg-white px-4 py-6 text-sm text-secondary">
            还没有运行记录，点击「运行识别」启动一次媒体候选整理。
          </div>

          <div v-if="workerState && (workerState.running || workerState.status)" class="rounded-2xl border border-soft bg-white px-4 py-3">
            <div class="flex items-center gap-2">
              <span class="h-2 w-2 rounded-full" :class="workerState.running ? 'bg-emerald-500 animate-pulse' : 'bg-slate-300'" />
              <p class="text-xs font-semibold text-primary">Worker</p>
            </div>
            <p class="mt-1 text-xs text-secondary">{{ workerState.status || (workerState.running ? '运行中' : '待机') }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ── 候选媒体列表 ──────────────────────────────────────────────── -->
    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 class="text-base font-semibold text-primary">候选媒体列表</h3>
          <p class="mt-1 text-sm text-secondary">按发布量降序排列，命中内建词典的候选会显示建议标签。点击标签按钮自动保存。</p>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600"
            @click="loadResults"
          >
            <ArrowPathIcon class="h-4 w-4" />
            刷新结果
          </button>
        </div>
      </div>

      <!-- 统计卡片 -->
      <div class="grid gap-3 sm:grid-cols-4 lg:grid-cols-7">
        <div
          v-for="card in summaryCards"
          :key="card.label"
          class="rounded-2xl border border-soft bg-surface-muted/60 px-4 py-4"
          :class="{ 'opacity-50': !card.value }"
        >
          <p class="text-xs text-muted">{{ card.label }}</p>
          <p class="mt-1 text-2xl font-semibold text-primary">{{ card.value }}</p>
        </div>
      </div>

      <!-- 筛选栏 -->
      <div class="flex flex-wrap items-center gap-4">
        <!-- 左侧：多选操作（仅当有选中时显示） -->
        <div v-if="selectedCount > 0" class="flex items-center gap-2 rounded-lg border border-brand-soft bg-brand-50 px-3 py-2">
          <span class="text-xs font-semibold text-brand-700">已选 {{ selectedCount }} 条</span>
          <button
            type="button"
            class="rounded-full border border-soft bg-white px-2 py-1 text-xs text-secondary transition hover:border-brand-soft hover:text-brand-600"
            :disabled="resultsState.saving"
            @click="handleBatchLabel('official_media')"
          >→官方</button>
          <button
            type="button"
            class="rounded-full border border-soft bg-white px-2 py-1 text-xs text-secondary transition hover:border-brand-soft hover:text-brand-600"
            :disabled="resultsState.saving"
            @click="handleBatchLabel('local_media')"
          >→地方</button>
          <button
            type="button"
            class="rounded-full border border-soft bg-white px-2 py-1 text-xs text-secondary transition hover:border-amber-soft hover:text-amber-600"
            :disabled="resultsState.saving"
            @click="handleBatchLabel('network_media')"
          >→网络</button>
          <button
            type="button"
            class="rounded-full border border-soft bg-white px-2 py-1 text-xs text-secondary transition hover:border-emerald-soft hover:text-emerald-600"
            :disabled="resultsState.saving"
            @click="handleBatchLabel('comprehensive_media')"
          >→综合</button>
          <button
            type="button"
            class="rounded-full border border-soft bg-white px-2 py-1 text-xs text-muted transition hover:bg-surface-muted"
            :disabled="resultsState.saving"
            @click="handleBatchLabel('')"
          >清除标签</button>
          <button
            type="button"
            class="rounded-full border border-danger-soft bg-white px-2 py-1 text-xs text-danger transition hover:bg-danger-50"
            :disabled="resultsState.saving"
            @click="handleDeleteSelected"
          >
            <TrashIcon class="h-3 w-3" />
            删除
          </button>
          <button
            type="button"
            class="rounded-full border border-soft bg-white px-2 py-1 text-xs text-muted transition hover:bg-surface-muted"
            @click="clearSelection()"
          >取消选择</button>
        </div>

        <!-- 中间：筛选条件 -->
        <div class="flex items-center gap-3 shrink-0">
          <!-- 标签筛选 -->
          <div class="flex gap-2 shrink-0">
            <button
              v-for="opt in labelOptions"
              :key="opt.value"
              type="button"
              class="rounded-full border px-3 py-1.5 text-xs font-medium transition shrink-0"
              :class="filters.label === opt.value
                ? 'border-brand-soft bg-brand-50 text-brand-700'
                : 'border-soft bg-surface text-secondary hover:border-brand-soft'"
              @click="filters.label = opt.value"
            >
              {{ opt.label }}
            </button>
          </div>

          <!-- 平台筛选 -->
          <div class="flex items-center gap-2 shrink-0 whitespace-nowrap">
            <span class="text-xs text-muted">平台</span>
            <AppSelect
              :options="platformSelectOptions"
              :value="filters.platform"
              size="sm"
              @change="filters.platform = $event"
            />
          </div>

          <!-- 排序模式 -->
          <div class="flex items-center gap-2 shrink-0 whitespace-nowrap">
            <span class="text-xs text-muted">排序</span>
            <AppSelect
              :options="sortModeOptions"
              :value="filters.sortMode"
              size="sm"
              @change="filters.sortMode = $event"
            />
          </div>
        </div>

        <!-- 右侧：搜索框 -->
        <div class="ml-auto flex items-center gap-2 shrink-0">
          <input
            v-model="filters.search"
            type="text"
            class="input h-9 w-[200px] text-sm"
            placeholder="搜索名称、别名…"
          />
        </div>
      </div>

      <div v-if="resultsState.error" class="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
        {{ resultsState.error }}
      </div>

      <!-- 候选表格 -->
      <div class="overflow-hidden rounded-3xl border border-soft">
        <!-- 分页控制栏 -->
        <div class="flex items-center justify-between gap-3 border-b border-soft bg-surface-muted/40 px-4 py-2">
          <p class="text-xs text-secondary">
            显示 {{ pageInfo.start }}–{{ pageInfo.end }} / {{ pageInfo.total }} 条
          </p>
          <div class="flex items-center gap-2">
            <span class="text-xs text-muted">每页</span>
            <TabSwitch
              :tabs="pageSizeTabs"
              :active="String(pageSize)"
              size="sm"
              @change="handlePageSizeChange"
            />
          </div>
        </div>

        <div v-if="resultsState.loading" class="px-4 py-10 text-center text-sm text-muted">
          正在加载媒体候选列表…
        </div>
        <div v-else class="overflow-x-auto">
          <table class="min-w-[900px] text-sm">
            <thead class="bg-surface-muted text-xs uppercase tracking-[0.18em] text-muted">
              <tr>
                <th class="w-12 px-2 py-3 text-center">
                  <label class="inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      :checked="isAllSelected"
                      :indeterminate.prop="selectedCount > 0 && !isAllSelected"
                      class="rounded border-soft"
                      @change="toggleSelectAll($event.target.checked)"
                    />
                  </label>
                </th>
                <th class="px-4 py-3 text-left">发布者</th>
                <th class="px-4 py-3 text-right">发布量</th>
                <th class="px-4 py-3 text-left">平台</th>
                <th class="px-4 py-3 text-left">建议</th>
                <th class="px-4 py-3 text-left">当前标签</th>
                <th class="px-4 py-3 text-left">快速打标</th>
                <th class="px-4 py-3 text-left">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="candidate in paginatedCandidates"
                :key="candidate.publisher_name"
                class="border-t border-soft align-middle transition hover:bg-surface-muted/40"
                :class="{ 'bg-brand-50/30': selectedItems.has(candidate.publisher_name.toLowerCase().trim()) }"
              >
                <td class="w-12 px-2 py-3 text-center">
                  <label class="inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      :checked="selectedItems.has(candidate.publisher_name.toLowerCase().trim())"
                      class="rounded border-soft"
                      @change="toggleSelectItem(candidate.publisher_name, $event.target.checked)"
                    />
                  </label>
                </td>
                <td class="px-4 py-3">
                  <p class="font-semibold text-primary">{{ candidate.publisher_name }}</p>
                  <p v-if="candidate.matched_registry_name" class="mt-0.5 text-xs text-secondary">
                    → {{ candidate.matched_registry_name }}
                  </p>
                </td>
                <td class="px-4 py-3 text-right font-mono text-secondary">{{ candidate.publish_count }}</td>
                <td class="px-4 py-3">
                  <div class="flex flex-wrap gap-1.5">
                    <span
                      v-for="platform in candidate.platforms"
                      :key="platform"
                      class="inline-flex rounded-full border border-soft bg-surface px-2 py-0.5 text-xs text-secondary"
                    >{{ platform }}</span>
                    <span v-if="!candidate.platforms?.length" class="text-muted">—</span>
                  </div>
                </td>
                <td class="px-4 py-3">
                  <!-- 建议标签：有建议时显示，未打标时可点击采纳 -->
                  <span
                    v-if="candidate.suggested_label"
                    class="inline-flex rounded-full border px-2.5 py-1 text-xs"
                    :class="[
                      candidate.current_label ? 'border-soft bg-surface-muted text-muted' : 'cursor-pointer border-dashed transition',
                      !candidate.current_label && candidate.suggested_label === 'official_media' ? 'border-brand-soft/60 text-brand-600 hover:bg-brand-50' : '',
                      !candidate.current_label && candidate.suggested_label === 'local_media' ? 'border-soft text-secondary hover:bg-surface-muted' : '',
                      !candidate.current_label && candidate.suggested_label === 'network_media' ? 'border-amber-soft/60 text-amber-600 hover:bg-amber-50' : '',
                      !candidate.current_label && candidate.suggested_label === 'comprehensive_media' ? 'border-emerald-soft/60 text-emerald-600 hover:bg-emerald-50' : ''
                    ]"
                    :title="candidate.current_label ? '已打标' : `系统建议：${labelText(candidate.suggested_label)}，点击采纳`"
                    @click="!candidate.current_label && handleLabelClick(candidate.publisher_name, candidate.suggested_label)"
                  >
                    {{ labelText(candidate.suggested_label) }}
                    <span v-if="!candidate.current_label" class="ml-1 text-muted">?</span>
                  </span>
                  <span v-else class="text-muted">—</span>
                </td>
                <td class="px-4 py-3">
                  <span
                    class="inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold"
                    :class="labelTone(candidate.current_label)"
                  >{{ labelText(candidate.current_label) }}</span>
                </td>
                <td class="px-4 py-3">
                  <div class="flex flex-wrap gap-1.5">
                    <button
                      type="button"
                      class="rounded-full border px-2.5 py-1 text-xs font-medium transition"
                      :class="candidate.current_label === 'official_media'
                        ? 'border-brand-soft bg-brand-50 text-brand-700'
                        : 'border-soft text-secondary hover:border-brand-soft hover:bg-surface-muted'"
                      @click="handleLabelClick(candidate.publisher_name, 'official_media')"
                    >官方</button>
                    <button
                      type="button"
                      class="rounded-full border px-2.5 py-1 text-xs font-medium transition"
                      :class="candidate.current_label === 'local_media'
                        ? 'border-brand-soft bg-brand-50 text-brand-700'
                        : 'border-soft text-secondary hover:border-brand-soft hover:bg-surface-muted'"
                      @click="handleLabelClick(candidate.publisher_name, 'local_media')"
                    >地方</button>
                    <button
                      type="button"
                      class="rounded-full border px-2.5 py-1 text-xs font-medium transition"
                      :class="candidate.current_label === 'network_media'
                        ? 'border-amber-soft bg-amber-50 text-amber-700'
                        : 'border-soft text-secondary hover:border-amber-soft hover:bg-amber-50'"
                      @click="handleLabelClick(candidate.publisher_name, 'network_media')"
                    >网络</button>
                    <button
                      type="button"
                      class="rounded-full border px-2.5 py-1 text-xs font-medium transition"
                      :class="candidate.current_label === 'comprehensive_media'
                        ? 'border-emerald-soft bg-emerald-50 text-emerald-700'
                        : 'border-soft text-secondary hover:border-emerald-soft hover:bg-emerald-50'"
                      @click="handleLabelClick(candidate.publisher_name, 'comprehensive_media')"
                    >综合</button>
                    <button
                      v-if="candidate.current_label"
                      type="button"
                      class="rounded-full border border-soft px-2.5 py-1 text-xs text-muted transition hover:bg-surface-muted"
                      @click="handleLabelClick(candidate.publisher_name, '')"
                    >清除</button>
                  </div>
                </td>
                <td class="px-4 py-3">
                  <div class="flex gap-1.5">
                    <button
                      type="button"
                      class="rounded-full border border-soft px-3 py-1.5 text-xs text-secondary transition hover:border-brand-soft hover:text-brand-600"
                      @click="openDetailModal(candidate)"
                    >详情</button>
                    <button
                      type="button"
                      class="rounded-full border border-danger-soft px-3 py-1.5 text-xs text-danger transition hover:bg-danger-50"
                      @click="handleDeleteCandidate(candidate)"
                    >
                      <TrashIcon class="h-3 w-3" />
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="!paginatedCandidates.length && !resultsState.loading">
                <td colspan="8" class="px-4 py-12 text-center text-sm text-muted">
                  <span v-if="!mediaResult">请先选择历史记录或运行一次识别，再查看媒体候选。</span>
                  <span v-else>当前筛选条件下没有符合条件的候选媒体。</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 分页导航 -->
        <div v-if="filteredCandidates.length > pageSize" class="flex items-center justify-center gap-2 border-t border-soft bg-surface-muted/40 px-4 py-3">
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-lg border border-soft px-3 py-1.5 text-xs text-secondary transition hover:border-brand-soft hover:text-brand-600"
            :disabled="currentPage === 1"
            @click="currentPage = 1"
          >
            首页
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-lg border border-soft px-3 py-1.5 text-xs text-secondary transition hover:border-brand-soft hover:text-brand-600 disabled:opacity-50"
            :disabled="currentPage === 1"
            @click="currentPage = Math.max(1, currentPage - 1)"
          >
            ‹ 上一页
          </button>

          <div class="flex items-center gap-1">
            <template v-for="p in visiblePageNumbers" :key="p">
              <button
                v-if="p === '...'"
                type="button"
                class="px-2 py-1 text-xs text-muted"
              >...</button>
              <button
                v-else
                type="button"
                class="rounded-lg px-3 py-1.5 text-xs font-medium transition"
                :class="currentPage === p
                  ? 'bg-brand-100 text-brand-700'
                  : 'text-secondary hover:bg-surface-muted'"
                @click="currentPage = p"
              >{{ p }}</button>
            </template>
          </div>

          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-lg border border-soft px-3 py-1.5 text-xs text-secondary transition hover:border-brand-soft hover:text-brand-600 disabled:opacity-50"
            :disabled="currentPage === totalPages"
            @click="currentPage = Math.min(totalPages, currentPage + 1)"
          >
            下一页 ›
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-lg border border-soft px-3 py-1.5 text-xs text-secondary transition hover:border-brand-soft hover:text-brand-600"
            :disabled="currentPage === totalPages"
            @click="currentPage = totalPages"
          >
            末页
          </button>
        </div>
      </div>
    </section>

    <!-- ── 共享媒体字典 ────────────────────────────────────────────── -->
    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 class="text-base font-semibold text-primary">共享媒体字典</h3>
          <p class="mt-1 text-sm text-secondary">跨专题复用的媒体名称与正式标签，识别时会自动对齐。支持多选合并。</p>
        </div>
        <div class="flex items-center gap-2">
          <!-- 多选操作栏 -->
          <div v-if="selectedRegistryCount > 0" class="flex items-center gap-2 rounded-lg border border-brand-soft bg-brand-50 px-3 py-2">
            <span class="text-xs font-semibold text-brand-700">已选 {{ selectedRegistryCount }} 条</span>
            <button
              type="button"
              class="rounded-full border border-soft bg-white px-2 py-1 text-xs text-secondary transition hover:border-brand-soft hover:text-brand-600"
              @click="openMergeRegistryModal"
            >
              <svg class="h-3 w-3 inline mr-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h7" /></svg>
              合并
            </button>
            <button
              type="button"
              class="rounded-full border border-soft bg-white px-2 py-1 text-xs text-muted transition hover:bg-surface-muted"
              @click="clearRegistrySelection()"
            >取消</button>
          </div>
          <!-- 常规按钮 -->
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600"
            :disabled="resultsState.registryLoading"
            @click="loadRegistry"
          >
            <ArrowPathIcon class="h-4 w-4" :class="{ 'animate-spin': resultsState.registryLoading }" />
            {{ resultsState.registryLoading ? '同步中…' : '刷新字典' }}
          </button>
          <button
            type="button"
            class="btn-secondary inline-flex items-center gap-2"
            @click="openRegistryModal()"
          >
            <PencilSquareIcon class="h-4 w-4" />
            新增条目
          </button>
        </div>
      </div>

      <div v-if="resultsState.registryNotice" class="rounded-2xl border border-brand-soft bg-brand-50 px-4 py-3 text-sm text-brand-700">
        {{ resultsState.registryNotice }}
      </div>
      <div v-if="resultsState.registryError" class="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
        {{ resultsState.registryError }}
      </div>

      <div class="overflow-hidden rounded-3xl border border-soft">
        <div class="overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead class="bg-surface-muted text-xs uppercase tracking-[0.18em] text-muted">
              <tr>
                <th class="w-12 px-2 py-3 text-center">
                  <label class="inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      :checked="isAllRegistrySelected"
                      :indeterminate.prop="selectedRegistryCount > 0 && !isAllRegistrySelected"
                      class="rounded border-soft"
                      @change="toggleSelectAllRegistry($event.target.checked)"
                    />
                  </label>
                </th>
                <th class="px-4 py-3 text-left">名称</th>
                <th class="px-4 py-3 text-left">别名</th>
                <th class="px-4 py-3 text-left">标签</th>
                <th class="px-4 py-3 text-left">备注</th>
                <th class="px-4 py-3 text-left">最近更新</th>
                <th class="px-4 py-3 text-left">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in filteredRegistryItems"
                :key="item.id"
                class="border-t border-soft align-middle transition hover:bg-surface-muted/40"
                :class="{ 'bg-brand-50/30': selectedRegistryItems.has(item.id) }"
              >
                <td class="w-12 px-2 py-3 text-center">
                  <label class="inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      :checked="selectedRegistryItems.has(item.id)"
                      class="rounded border-soft"
                      @change="toggleSelectRegistryItem(item.id, $event.target.checked)"
                    />
                  </label>
                </td>
                <td class="px-4 py-3 font-semibold text-primary">{{ item.name }}</td>
                <td class="px-4 py-3 text-secondary">{{ item.aliases?.join('、') || '—' }}</td>
                <td class="px-4 py-3">
                  <span class="inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold" :class="labelTone(item.media_level)">
                    {{ labelText(item.media_level) }}
                  </span>
                </td>
                <td class="px-4 py-3 text-secondary">{{ item.notes || '—' }}</td>
                <td class="px-4 py-3 text-secondary">{{ formatTimestamp(item.updated_at) }}</td>
                <td class="px-4 py-3">
                  <div class="flex gap-1.5">
                    <button
                      type="button"
                      class="rounded-full border border-soft px-3 py-1.5 text-xs text-secondary transition hover:border-brand-soft hover:text-brand-600"
                      @click="openRegistryModal(item)"
                    >编辑</button>
                    <button
                      type="button"
                      class="rounded-full border border-danger-soft px-3 py-1.5 text-xs text-danger transition hover:bg-danger-50"
                      @click="handleDeleteRegistryItem(item)"
                    >
                      <TrashIcon class="h-3 w-3" />
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="!filteredRegistryItems.length">
                <td colspan="7" class="px-4 py-8 text-center text-sm text-muted">
                  字典为空，请先运行识别并打标，或手动新增。
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- ── 详情 / 字典编辑 Modal ──────────────────────────────────── -->
    <AppModal
      v-model="detailModalOpen"
      eyebrow="媒体候选"
      :title="detailCandidate?.publisher_name || '候选详情'"
      description="查看样本文章，并为这家媒体维护字典条目。"
      confirm-text="保存字典"
      confirm-loading-text="保存中…"
      width="max-w-3xl"
      scrollable
      :confirm-disabled="!registryForm.name.trim()"
      :confirm-loading="resultsState.registrySaving"
      @confirm="submitDetailModal"
      @cancel="closeDetailModal"
    >
      <div v-if="detailCandidate" class="space-y-6">
        <!-- 样本 -->
        <div>
          <p class="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-muted">样本文章</p>
          <div class="space-y-2">
            <div
              v-for="(sample, index) in detailCandidate.samples || []"
              :key="index"
              class="rounded-2xl border border-soft bg-surface-muted/50 px-4 py-3"
            >
              <a
                v-if="sample.url"
                :href="sample.url"
                target="_blank"
                rel="noreferrer"
                class="line-clamp-2 text-sm font-medium text-primary underline-offset-2 hover:underline"
              >{{ sample.title || sample.url }}</a>
              <p v-else class="line-clamp-2 text-sm font-medium text-primary">{{ sample.title || '未提供标题' }}</p>
              <p class="mt-1 text-xs text-muted">{{ sample.platform || '—' }} · {{ sample.published_at || '—' }}</p>
            </div>
            <p v-if="!detailCandidate.samples?.length" class="text-sm text-muted">暂无样本</p>
          </div>
        </div>

        <!-- 字典表单 -->
        <div>
          <p class="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-muted">字典条目</p>
          <div class="grid gap-4 md:grid-cols-2">
            <label class="space-y-2">
              <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">媒体名称</span>
              <input v-model="registryForm.name" type="text" class="input h-10" placeholder="例如：人民日报" />
            </label>

            <label class="space-y-2">
              <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">正式标签</span>
              <AppSelect
                :options="registryLabelOptions"
                :value="registryForm.media_level"
                @change="registryForm.media_level = $event"
              />
            </label>

            <label class="space-y-2 md:col-span-2">
              <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">别名（逗号/换行分隔）</span>
              <textarea
                v-model="registryForm.aliases"
                class="input min-h-[80px] py-3"
                placeholder="多个别名可用逗号、分号或换行分隔"
              />
            </label>

            <label class="space-y-2">
              <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">状态</span>
              <AppSelect
                :options="registryStatusOptions"
                :value="registryForm.status"
                @change="registryForm.status = $event"
              />
            </label>

            <label class="space-y-2">
              <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">备注</span>
              <input v-model="registryForm.notes" type="text" class="input h-10" placeholder="可记录识别口径" />
            </label>
          </div>
        </div>
      </div>
    </AppModal>

    <!-- ── 新增 / 编辑字典条目 Modal ──────────────────────────────── -->
    <AppModal
      v-model="registryModalOpen"
      eyebrow="共享媒体字典"
      :title="registryForm.id ? '编辑媒体条目' : '新增媒体条目'"
      description="维护正式名称、别名和标签，后续识别会优先沿用。"
      confirm-text="保存"
      confirm-loading-text="保存中…"
      width="max-w-2xl"
      scrollable
      :confirm-disabled="!registryForm.name.trim()"
      :confirm-loading="resultsState.registrySaving"
      @confirm="submitRegistryModal"
      @cancel="resetRegistryModal"
    >
      <div class="grid gap-4 md:grid-cols-2">
        <label class="space-y-2">
          <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">媒体名称</span>
          <input v-model="registryForm.name" type="text" class="input h-10" placeholder="例如：人民日报" />
        </label>

        <label class="space-y-2">
          <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">正式标签</span>
          <AppSelect
            :options="registryLabelOptions"
            :value="registryForm.media_level"
            @change="registryForm.media_level = $event"
          />
        </label>

        <label class="space-y-2 md:col-span-2">
          <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">别名</span>
          <textarea
            v-model="registryForm.aliases"
            class="input min-h-[100px] py-3"
            placeholder="多个别名可用逗号、分号或换行分隔"
          />
        </label>

        <label class="space-y-2">
          <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">状态</span>
          <AppSelect
            :options="registryStatusOptions"
            :value="registryForm.status"
            @change="registryForm.status = $event"
          />
        </label>

        <label class="space-y-2">
          <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">备注</span>
          <input v-model="registryForm.notes" type="text" class="input h-10" placeholder="可记录识别口径或说明" />
        </label>
      </div>
    </AppModal>

    <!-- ── 合并字典条目 Modal ─────────────────────────────────────────── -->
    <AppModal
      v-model="mergeRegistryModalOpen"
      eyebrow="合并字典条目"
      title="合并选中条目"
      description="选择主条目，其他条目的名称和别名将合并为该条目的别名。"
      confirm-text="确认合并"
      confirm-loading-text="合并中…"
      width="max-w-xl"
      :confirm-disabled="!mergeForm.canonicalName.trim()"
      :confirm-loading="resultsState.registrySaving"
      @confirm="submitMergeRegistryModal"
      @cancel="closeMergeRegistryModal"
    >
      <div class="space-y-4">
        <p class="text-sm text-secondary">已选择 {{ selectedRegistryCount }} 条条目：</p>
        <div class="rounded-xl border border-soft bg-surface-muted/50 px-4 py-3">
          <ul class="space-y-1 text-sm">
            <li v-for="item in selectedRegistryItemsList" :key="item.id" class="flex items-center gap-2">
              <input
                type="radio"
                :value="item.id"
                :checked="mergeForm.canonicalId === item.id"
                class="rounded border-soft"
                @change="selectMergeCanonical(item)"
              />
              <span class="font-semibold text-primary">{{ item.name }}</span>
              <span class="text-xs text-muted">( {{ labelText(item.media_level) }} )</span>
              <span v-if="item.aliases?.length" class="text-xs text-secondary">别名: {{ item.aliases.join('、') }}</span>
            </li>
          </ul>
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <label class="space-y-2">
            <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">主条目名称</span>
            <input v-model="mergeForm.canonicalName" type="text" class="input h-10" placeholder="选择或输入主名称" />
          </label>

          <label class="space-y-2">
            <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">合并后标签</span>
            <AppSelect
              :options="registryLabelOptions"
              :value="mergeForm.mediaLevel"
              @change="mergeForm.mediaLevel = $event"
            />
          </label>
        </div>

        <p class="text-xs text-muted">合并后，其他条目将被删除，其名称和别名将汇总到主条目的别名列表中。</p>
      </div>
    </AppModal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  ArrowPathIcon,
  MegaphoneIcon,
  PencilSquareIcon,
  CheckIcon,
  TrashIcon,
} from '@heroicons/vue/24/outline'
import AppModal from '../../../components/AppModal.vue'
import AppSelect from '../../../components/AppSelect.vue'
import TabSwitch from '../../../components/TabSwitch.vue'
import { useMediaTagging } from '../../../composables/useMediaTagging'

const {
  topicsState,
  topicOptions,
  runForm,
  availableRange,
  runState,
  taskState,
  workerState,
  tasks,
  historyState,
  historyRecords,
  selectedHistoryId,
  viewSelection,
  resultsState,
  mediaResult,
  registryItems,
  filters,
  resultSummary,
  currentRange,
  filteredCandidates,
  filteredRegistryItems,
  candidateStats,
  allPlatforms,
  selectedItems,
  isAllSelected,
  selectedCount,
  loadTopics,
  changeTopic,
  runMediaTagging,
  loadResults,
  loadResultsFromManual,
  loadRegistry,
  stageCandidateLabel,
  applyLabelToFilteredCandidates,
  toggleSelectAll,
  toggleSelectItem,
  applyLabelToSelected,
  clearSelection,
  saveCandidateUpdates,
  saveRegistryItem,
  deleteCandidates,
  deleteSelectedCandidates,
  deleteRegistryItem,
  acceptAllSuggestions,
  selectedRegistryItems,
  isAllRegistrySelected,
  selectedRegistryCount,
  toggleSelectAllRegistry,
  toggleSelectRegistryItem,
  clearRegistrySelection,
  mergeRegistryItems
} = useMediaTagging()

// ── Modals ──────────────────────────────────────────────────────────────
const detailModalOpen = ref(false)
const detailCandidate = ref(null)
const registryModalOpen = ref(false)
const mergeRegistryModalOpen = ref(false)

// ── Pagination ───────────────────────────────────────────────────────────
const pageSize = ref(30)
const currentPage = ref(1)
const pageSizeOptions = [10, 30, 50, 100]
const pageSizeTabs = pageSizeOptions.map((size) => ({ value: String(size), label: String(size) }))

function handlePageSizeChange(value) {
  pageSize.value = Number(value)
  currentPage.value = 1
}

const totalPages = computed(() =>
  Math.max(1, Math.ceil(filteredCandidates.value.length / pageSize.value))
)

const paginatedCandidates = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredCandidates.value.slice(start, end)
})

const pageInfo = computed(() => ({
  start: (currentPage.value - 1) * pageSize.value + 1,
  end: Math.min(currentPage.value * pageSize.value, filteredCandidates.value.length),
  total: filteredCandidates.value.length
}))

// 可见页码数字（带省略号）
const visiblePageNumbers = computed(() => {
  const total = totalPages.value
  const current = currentPage.value
  const pages = []

  if (total <= 7) {
    for (let i = 1; i <= total; i++) pages.push(i)
  } else {
    pages.push(1)
    if (current > 3) pages.push('...')
    for (let i = Math.max(2, current - 1); i <= Math.min(total - 1, current + 1); i++) {
      pages.push(i)
    }
    if (current < total - 2) pages.push('...')
    pages.push(total)
  }
  return pages
})

// 筛选条件变化时重置页码
watch([() => filters.search, () => filters.label, () => filters.platform], () => {
  currentPage.value = 1
  clearSelection()
})

const registryForm = reactive({
  id: '',
  name: '',
  aliases: '',
  media_level: '',
  status: 'draft',
  notes: ''
})

const mergeForm = reactive({
  canonicalId: '',
  canonicalName: '',
  mediaLevel: ''
})

// ── Computed ─────────────────────────────────────────────────────────────
const topicSelectOptions = computed(() =>
  topicOptions.value.map((item) => ({ value: item, label: item }))
)

const historySelectOptions = computed(() =>
  historyRecords.value.map((item) => ({
    value: item.id,
    label: `${item.start} → ${item.end}`
  }))
)

const platformSelectOptions = computed(() => [
  { value: '', label: '全部' },
  ...allPlatforms.value.map((platform) => ({ value: platform, label: platform }))
])

const sortModeOptions = [
  { value: 'suggest_first', label: '建议优先' },
  { value: 'publish_count', label: '发布量优先' }
]

const summaryCards = computed(() => [
  { label: '候选总数', value: candidateStats.value.total },
  { label: '有建议', value: candidateStats.value.hasSuggest },
  { label: '官方媒体', value: candidateStats.value.official },
  { label: '地方媒体', value: candidateStats.value.local },
  { label: '网络媒体', value: candidateStats.value.network },
  { label: '综合媒体', value: candidateStats.value.comprehensive },
  { label: '待确认', value: candidateStats.value.unlabeled }
])

// ── Constants ─────────────────────────────────────────────────────────────
const labelOptions = [
  { value: 'all', label: '全部' },
  { value: 'has_suggest', label: '有建议' },
  { value: 'official_media', label: '官方媒体' },
  { value: 'local_media', label: '地方媒体' },
  { value: 'network_media', label: '网络媒体' },
  { value: 'comprehensive_media', label: '综合媒体' },
  { value: 'unlabeled', label: '未标记' }
]

const registryLabelOptions = [
  { value: '', label: '未标记' },
  { value: 'official_media', label: '官方媒体' },
  { value: 'local_media', label: '地方媒体' },
  { value: 'network_media', label: '网络媒体' },
  { value: 'comprehensive_media', label: '综合媒体' }
]

const registryStatusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'active', label: '启用' }
]

// ── Helpers ───────────────────────────────────────────────────────────────
function labelText(value) {
  if (value === 'official_media') return '官方媒体'
  if (value === 'local_media') return '地方媒体'
  if (value === 'network_media') return '网络媒体'
  if (value === 'comprehensive_media') return '综合媒体'
  return '未标记'
}

function labelTone(value) {
  if (value === 'official_media') return 'border-brand-soft bg-brand-50 text-brand-700'
  if (value === 'local_media') return 'border-soft bg-surface-muted text-secondary'
  if (value === 'network_media') return 'border-amber-soft bg-amber-50 text-amber-700'
  if (value === 'comprehensive_media') return 'border-emerald-soft bg-emerald-50 text-emerald-700'
  return 'border-soft bg-surface text-muted'
}

function formatTimestamp(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', { hour12: false, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

// ── Handlers ─────────────────────────────────────────────────────────────
function handleTopicChange(value) {
  changeTopic(value)
  filters.search = ''
  filters.label = 'all'
}

async function handleRun() {
  await runMediaTagging()
}

async function handleDeleteCandidate(candidate) {
  if (!candidate?.publisher_name) return
  if (!confirm(`确定删除候选媒体「${candidate.publisher_name}」吗？此操作不可恢复。`)) return
  await deleteCandidates([candidate.publisher_name])
}

async function handleDeleteSelected() {
  if (!selectedCount.value) return
  if (!confirm(`确定删除已选的 ${selectedCount.value} 条候选媒体吗？此操作不可恢复。`)) return
  await deleteSelectedCandidates()
}

async function handleDeleteRegistryItem(item) {
  if (!item?.id) return
  if (!confirm(`确定删除字典条目「${item.name}」吗？此操作不可恢复。`)) return
  await deleteRegistryItem(item.id)
}

// 打标点击处理：包装异步调用，确保错误被正确显示
// 打标点击处理：乐观更新，不等待API
function handleLabelClick(publisherName, label) {
  stageCandidateLabel(publisherName, label)
}

// 批量打标处理
function handleBatchLabel(label) {
  applyLabelToSelected(label)
}

// ── Detail Modal ─────────────────────────────────────────────────────────
function openDetailModal(candidate) {
  detailCandidate.value = candidate
  populateRegistryFormFromCandidate(candidate)
  detailModalOpen.value = true
}

function closeDetailModal() {
  detailModalOpen.value = false
  detailCandidate.value = null
  resetRegistryForm()
}

function populateRegistryFormFromCandidate(candidate) {
  const matched = registryItems.value.find((item) => item.name === candidate.matched_registry_name)
  if (matched) {
    registryForm.id = String(matched.id || '')
    registryForm.name = String(matched.name || '')
    registryForm.aliases = Array.isArray(matched.aliases) ? matched.aliases.join('，') : ''
    registryForm.media_level = String(matched.media_level || '')
    registryForm.status = String(matched.status || 'draft')
    registryForm.notes = String(matched.notes || '')
  } else {
    registryForm.id = String(candidate.matched_registry_id || '')
    registryForm.name = String(candidate.matched_registry_name || candidate.publisher_name || '')
    registryForm.aliases = (candidate.publisher_name && candidate.publisher_name !== candidate.matched_registry_name)
      ? candidate.publisher_name
      : ''
    registryForm.media_level = String(candidate.current_label || candidate.suggested_label || '')
    registryForm.status = registryForm.media_level ? 'active' : 'draft'
    registryForm.notes = ''
  }
}

async function submitDetailModal() {
  const saved = await saveRegistryItem({
    id: registryForm.id,
    name: registryForm.name,
    aliases: registryForm.aliases,
    media_level: registryForm.media_level,
    status: registryForm.status,
    notes: registryForm.notes
  })
  if (saved) {
    detailModalOpen.value = false
    detailCandidate.value = null
    resetRegistryForm()
  }
}

// ── Registry Modal ────────────────────────────────────────────────────────
function openRegistryModal(item = null) {
  resetRegistryForm()
  if (item) {
    registryForm.id = String(item.id || '')
    registryForm.name = String(item.name || '')
    registryForm.aliases = Array.isArray(item.aliases) ? item.aliases.join('，') : ''
    registryForm.media_level = String(item.media_level || '')
    registryForm.status = String(item.status || 'draft')
    registryForm.notes = String(item.notes || '')
  }
  registryModalOpen.value = true
}

function resetRegistryForm() {
  registryForm.id = ''
  registryForm.name = ''
  registryForm.aliases = ''
  registryForm.media_level = ''
  registryForm.status = 'draft'
  registryForm.notes = ''
}

function resetRegistryModal() {
  registryModalOpen.value = false
  resetRegistryForm()
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
    resetRegistryForm()
  }
}

// ── Merge Registry Modal ────────────────────────────────────────────────────
const selectedRegistryItemsList = computed(() =>
  registryItems.value.filter((item) => selectedRegistryItems.value.has(item.id))
)

function openMergeRegistryModal() {
  if (selectedRegistryCount.value < 2) {
    resultsState.registryError = '请至少选择 2 条条目进行合并。'
    return
  }
  // 默认选择第一个作为 canonical
  const first = selectedRegistryItemsList.value[0]
  if (first) {
    mergeForm.canonicalId = first.id
    mergeForm.canonicalName = first.name
    mergeForm.mediaLevel = first.media_level || ''
  } else {
    mergeForm.canonicalId = ''
    mergeForm.canonicalName = ''
    mergeForm.mediaLevel = ''
  }
  resultsState.registryError = ''
  mergeRegistryModalOpen.value = true
}

function selectMergeCanonical(item) {
  mergeForm.canonicalId = item.id
  mergeForm.canonicalName = item.name
  mergeForm.mediaLevel = item.media_level || ''
}

function closeMergeRegistryModal() {
  mergeRegistryModalOpen.value = false
  mergeForm.canonicalId = ''
  mergeForm.canonicalName = ''
  mergeForm.mediaLevel = ''
}

async function submitMergeRegistryModal() {
  const result = await mergeRegistryItems({
    canonicalId: mergeForm.canonicalId,
    canonicalName: mergeForm.canonicalName,
    mediaLevel: mergeForm.mediaLevel,
    notes: ''
  })
  if (result) {
    closeMergeRegistryModal()
  }
}

// ── Lifecycle ─────────────────────────────────────────────────────────────
onMounted(async () => {
  await loadRegistry()
})
</script>

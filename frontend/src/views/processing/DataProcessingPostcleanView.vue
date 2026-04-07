<template>
  <div class="space-y-6 pb-12">
    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">Post Clean</p>
          <h2 class="mt-2 text-xl font-semibold text-primary">数据库后清洗</h2>
          <p class="mt-2 text-sm text-secondary">
            统一管理项目排除词与发布者黑名单。执行后清洗时，命中排除词或命中黑名单的发布者都会被删除；若有删除，会自动同步本地缓存。
          </p>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600"
          :disabled="projectsLoading || databasesLoading"
          @click="refreshAll"
        >
          <ArrowPathIcon class="h-4 w-4" :class="projectsLoading || databasesLoading ? 'animate-spin' : ''" />
          刷新上下文
        </button>
      </div>

      <div class="grid gap-5 xl:grid-cols-[1.1fr,1fr]">
        <div class="space-y-4 rounded-3xl border border-soft bg-surface-muted/60 p-5">
          <div class="grid gap-4 md:grid-cols-2">
            <label class="space-y-2">
              <span class="text-xs font-semibold text-muted">项目</span>
              <select v-model="selectedProjectName" class="input" :disabled="projectsLoading || !projectOptions.length">
                <option value="" disabled>请选择项目</option>
                <option v-for="option in projectOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
              <p v-if="projectsError" class="text-xs text-danger">{{ projectsError }}</p>
            </label>

            <label class="space-y-2">
              <span class="text-xs font-semibold text-muted">数据集</span>
              <select v-model="selectedDatasetId" class="input" :disabled="datasetsLoading || !datasetOptions.length">
                <option value="">项目级默认上下文</option>
                <option v-for="option in datasetOptions" :key="option.id" :value="option.id">{{ option.label }}</option>
              </select>
              <p v-if="datasetsError" class="text-xs text-danger">{{ datasetsError }}</p>
            </label>

            <label class="space-y-2 md:col-span-2">
              <span class="text-xs font-semibold text-muted">数据库</span>
              <select v-model="selectedDatabase" class="input" :disabled="databasesLoading || !databaseOptions.length">
                <option value="" disabled>{{ databaseOptions.length ? '请选择数据库' : '暂无数据库' }}</option>
                <option v-for="option in databaseOptions" :key="option.name" :value="option.name">
                  {{ option.name }} · {{ option.tableCount }} 张表
                </option>
              </select>
              <p v-if="databasesError" class="text-xs text-danger">{{ databasesError }}</p>
            </label>
          </div>

          <div class="rounded-2xl border border-soft bg-white p-4">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p class="text-sm font-semibold text-primary">表范围</p>
                <p class="mt-1 text-xs text-secondary">默认全选。Top50 发布者分析和执行后清洗都会使用这里的范围。</p>
              </div>
              <div class="flex items-center gap-2 text-xs">
                <button type="button" class="text-brand-600 transition hover:text-brand-700" @click="selectAllTables">全选</button>
                <button type="button" class="text-secondary transition hover:text-primary" @click="clearSelectedTables">清空</button>
              </div>
            </div>
            <div v-if="tableOptions.length" class="mt-4 grid gap-2 md:grid-cols-2">
              <label
                v-for="table in tableOptions"
                :key="table.name"
                class="flex items-center justify-between gap-3 rounded-2xl border border-soft px-3 py-2 text-sm text-secondary"
              >
                <span class="flex items-center gap-2">
                  <input v-model="selectedTables" type="checkbox" :value="table.name" class="h-4 w-4 rounded border-soft text-brand-600 focus:ring-brand-400" />
                  <span class="font-medium text-primary">{{ table.name }}</span>
                </span>
                <span class="text-xs text-muted">{{ formatInteger(table.rowCount) }} 行</span>
              </label>
            </div>
            <p v-else class="mt-4 text-sm text-secondary">当前数据库暂无可选数据表。</p>
          </div>
        </div>

        <div class="space-y-4 rounded-3xl border border-rose-200 bg-rose-50/50 p-5">
          <div class="rounded-2xl border border-soft bg-white px-4 py-3">
            <p class="text-xs text-muted">当前范围</p>
            <p class="mt-1 text-sm font-semibold text-primary">{{ currentProjectName || '未选择项目' }}</p>
            <p class="mt-1 text-xs text-secondary">
              数据库 {{ selectedDatabase || '—' }} · 表 {{ selectedTables.length || tableOptions.length ? selectedTables.length : 0 }} / {{ tableOptions.length }}
            </p>
          </div>

          <div class="rounded-2xl border border-rose-200 bg-white px-4 py-3 text-sm text-rose-700">
            <p class="font-semibold">危险操作</p>
            <p class="mt-1 text-xs leading-relaxed">执行后会直接删除数据库记录，不进入回收站；只有命中记录时才会继续触发本地缓存刷新。</p>
          </div>

          <div class="rounded-2xl border border-soft bg-white px-4 py-3">
            <p class="text-xs text-muted">任务状态</p>
            <p class="mt-1 text-sm font-semibold text-primary">{{ statusLabel }}</p>
            <p class="mt-1 text-xs text-secondary">{{ postcleanState.message || '等待执行。' }}</p>
          </div>

          <button
            type="button"
            class="btn-primary inline-flex w-full items-center justify-center gap-2"
            :disabled="!canRun || postcleanState.running || sharedPromptState.saving"
            @click="runPostclean"
          >
            <SparklesIcon class="h-4 w-4" />
            {{ postcleanState.running ? '后清洗执行中…' : '执行数据库后清洗' }}
          </button>

          <div class="rounded-2xl border border-soft bg-white px-4 py-4">
            <div class="flex items-center justify-between gap-3 text-xs text-secondary">
              <span>整体进度</span>
              <span>{{ postcleanState.progress.percentage }}%</span>
            </div>
            <div class="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
              <div class="h-full rounded-full bg-rose-500 transition-all duration-500" :style="{ width: `${postcleanState.progress.percentage}%` }" />
            </div>
            <p class="mt-3 text-xs text-secondary">
              {{ postcleanState.progress.completed_tables }} / {{ postcleanState.progress.total_tables }} 张表
              <span v-if="postcleanState.progress.deleted_rows"> · 已删除 {{ formatInteger(postcleanState.progress.deleted_rows) }} 条</span>
            </p>
          </div>
        </div>
      </div>
    </section>

    <section class="card-surface space-y-5 p-6">
      <div class="grid gap-5 xl:grid-cols-2">
        <div class="space-y-3 rounded-3xl border border-soft bg-surface-muted/60 p-5">
          <div class="flex items-center justify-between gap-3">
            <div>
              <h3 class="text-base font-semibold text-primary">排除词后清洗</h3>
              <p class="mt-1 text-sm text-secondary">每行一个词；命中标题、正文或命中词字段时会被删除。</p>
            </div>
            <span class="rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">{{ stopwordList.length }} 项</span>
          </div>
          <div class="flex flex-wrap items-center justify-end gap-3 rounded-2xl border border-soft bg-white px-4 py-4">
            <button
              type="button"
              class="btn-primary inline-flex items-center gap-2"
              :disabled="!currentProjectName"
              @click="openStopwordModal"
            >
              打开排除词弹窗
            </button>
          </div>
          <textarea
            v-model="sharedPromptState.projectStopwordsText"
            rows="12"
            class="input min-h-[16rem] resize-y"
            placeholder="每行一个排除词"
          />
          <div class="flex justify-end pt-1">
            <button
              type="button"
              class="btn-primary inline-flex items-center gap-2"
              :disabled="!currentProjectName"
              @click="openStopwordModal"
            >
              打开排除词弹窗
            </button>
          </div>
        </div>

        <div class="space-y-3 rounded-3xl border border-soft bg-surface-muted/60 p-5">
          <div class="flex items-center justify-between gap-3">
            <div>
              <h3 class="text-base font-semibold text-primary">发布者黑名单</h3>
              <p class="mt-1 text-sm text-secondary">每行一个发布者；保存后不会立即删库，只有执行后清洗时才会生效。</p>
            </div>
            <span class="rounded-full bg-rose-50 px-3 py-1 text-xs font-semibold text-rose-700">{{ blacklistList.length }} 项</span>
          </div>
          <div class="flex flex-wrap items-center justify-end gap-3 rounded-2xl border border-soft bg-white px-4 py-4">
            <button
              type="button"
              class="btn-primary inline-flex items-center gap-2"
              :disabled="!canInspectPublishers"
              @click="openPublisherModal"
            >
              <ArrowPathIcon class="h-4 w-4" :class="publisherDetectionState.loading ? 'animate-spin' : ''" />
              打开异常发布者识别弹窗
            </button>
          </div>
          <textarea
            v-model="sharedPromptState.publisherBlacklistText"
            rows="12"
            class="input min-h-[16rem] resize-y"
            placeholder="每行一个发布者"
          />
          <div class="flex justify-end pt-1">
            <button
              type="button"
              class="btn-primary inline-flex items-center gap-2"
              :disabled="!canInspectPublishers"
              @click="openPublisherModal"
            >
              <ArrowPathIcon class="h-4 w-4" :class="publisherDetectionState.loading ? 'animate-spin' : ''" />
              打开异常发布者识别弹窗
            </button>
          </div>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-3">
        <button
          type="button"
          class="btn-primary inline-flex items-center gap-2"
          :disabled="!currentProjectName || sharedPromptState.loading || sharedPromptState.saving"
          @click="saveSharedPromptConfig"
        >
          <CheckIcon class="h-4 w-4" />
          {{ sharedPromptState.saving ? '保存中…' : '保存共享配置' }}
        </button>
        <p v-if="sharedPromptState.error" class="text-xs text-danger">{{ sharedPromptState.error }}</p>
        <p v-else-if="sharedPromptState.success" class="text-xs text-emerald-600">{{ sharedPromptState.success }}</p>
      </div>
    </section>

    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 class="text-base font-semibold text-primary">异常发布者识别</h3>
          <p class="mt-1 text-sm text-secondary">打开弹窗后再查看范围、状态和样本，不在页面正文重复展示。</p>
        </div>
        <button
          type="button"
          class="btn-primary inline-flex items-center gap-2"
          :disabled="!canInspectPublishers"
          @click="openPublisherModal"
        >
          <ArrowPathIcon class="h-4 w-4" :class="publisherDetectionState.loading ? 'animate-spin' : ''" />
          打开识别弹窗
        </button>
      </div>
    </section>

    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 class="text-base font-semibold text-primary">结果与审计</h3>
          <p class="mt-1 text-sm text-secondary">完成后可查看总删除数、原因拆分、每表结果以及缓存刷新后续动作。</p>
        </div>
      </div>

      <div v-if="postcleanResult" class="grid gap-4 xl:grid-cols-[0.9fr,1.1fr]">
        <div class="grid gap-3 sm:grid-cols-2">
          <div class="rounded-2xl border border-soft bg-surface-muted/60 px-4 py-4">
            <p class="text-xs text-muted">删除记录</p>
            <p class="mt-1 text-2xl font-semibold text-primary">{{ formatInteger(postcleanResult.deleted_rows || 0) }}</p>
          </div>
          <div class="rounded-2xl border border-soft bg-surface-muted/60 px-4 py-4">
            <p class="text-xs text-muted">缺失表</p>
            <p class="mt-1 text-2xl font-semibold text-primary">{{ (postcleanResult.missing_tables || []).length }}</p>
          </div>
          <div class="rounded-2xl border border-soft bg-surface-muted/60 px-4 py-4">
            <p class="text-xs text-muted">仅排除词</p>
            <p class="mt-1 text-2xl font-semibold text-primary">{{ formatInteger(postcleanResult.reason_breakdown?.keyword_only || 0) }}</p>
          </div>
          <div class="rounded-2xl border border-soft bg-surface-muted/60 px-4 py-4">
            <p class="text-xs text-muted">仅黑名单</p>
            <p class="mt-1 text-2xl font-semibold text-primary">{{ formatInteger(postcleanResult.reason_breakdown?.author_only || 0) }}</p>
          </div>
          <div class="rounded-2xl border border-soft bg-surface-muted/60 px-4 py-4 sm:col-span-2">
            <p class="text-xs text-muted">双重命中 / 缓存刷新</p>
            <p class="mt-1 text-sm font-semibold text-primary">
              双重命中 {{ formatInteger(postcleanResult.reason_breakdown?.both || 0) }} 条
            </p>
            <p class="mt-1 text-xs text-secondary">{{ postcleanResult.follow_up?.message || '未返回后续动作。' }}</p>
          </div>
        </div>

        <div class="rounded-2xl border border-soft bg-white p-4">
          <div class="flex items-center justify-between gap-3">
            <p class="text-sm font-semibold text-primary">按表结果</p>
            <span class="text-xs text-secondary">{{ (postcleanResult.tables || []).length }} 项</span>
          </div>
          <div v-if="(postcleanResult.tables || []).length" class="mt-4 space-y-2">
            <div
              v-for="table in postcleanResult.tables"
              :key="table.table"
              class="rounded-2xl border border-soft px-4 py-3"
            >
              <div class="flex flex-wrap items-center justify-between gap-2">
                <p class="text-sm font-semibold text-primary">{{ table.table }}</p>
                <span class="text-xs text-secondary">{{ table.status === 'skipped' ? '已跳过' : '已完成' }}</span>
              </div>
              <p class="mt-2 text-xs text-secondary">
                <span v-if="table.reason">{{ table.reason }}</span>
                <span v-else>
                  命中 {{ formatInteger(table.matched_rows || 0) }} 条，删除 {{ formatInteger(table.deleted_rows || 0) }} 条。
                  仅排除词 {{ formatInteger(table.reason_breakdown?.keyword_only || 0) }}，
                  仅黑名单 {{ formatInteger(table.reason_breakdown?.author_only || 0) }}，
                  双重命中 {{ formatInteger(table.reason_breakdown?.both || 0) }}。
                </span>
              </p>
            </div>
          </div>
          <p v-else class="mt-4 text-sm text-secondary">还没有可展示的审计结果。</p>
        </div>
      </div>
      <p v-else class="text-sm text-secondary">尚未执行数据库后清洗。</p>

      <div class="rounded-2xl border border-soft bg-slate-950 px-4 py-4">
        <p class="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Task Log</p>
        <div v-if="postcleanState.logs.length" class="mt-3 max-h-64 space-y-2 overflow-y-auto">
          <div v-for="item in postcleanState.logs" :key="`${item.ts}-${item.message}`" class="rounded-xl bg-slate-900/80 px-3 py-2 text-xs text-slate-200">
            <p class="font-medium text-slate-100">{{ item.message }}</p>
            <p class="mt-1 text-[11px] text-slate-400">{{ formatTimestamp(item.ts) }}</p>
          </div>
        </div>
        <p v-else class="mt-3 text-sm text-slate-300">等待任务日志。</p>
      </div>
    </section>

    <AppModal
      v-model="publisherModalOpen"
      title="异常发布者识别"
      description="展示当前范围内 Top50 发布者，每个发布者附带 3 条样本。黑名单保存后不会立即删库，只有执行数据库后清洗时才会真正删除。"
      width="max-w-6xl"
      :show-footer="false"
      scrollable
    >
      <div class="space-y-4">
        <div class="rounded-3xl border border-soft bg-surface-muted/35 p-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="space-y-1">
              <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">当前范围</p>
              <p class="text-sm font-semibold text-primary">{{ currentProjectName || '未选择项目' }}</p>
              <p class="text-xs text-secondary">数据库 {{ selectedDatabase || '—' }} · 表 {{ selectedTables.length || tableOptions.length ? selectedTables.length : 0 }} / {{ tableOptions.length }}</p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <button
                type="button"
                class="btn-secondary inline-flex items-center gap-2 whitespace-nowrap"
                :disabled="!canInspectPublishers || publisherDetectionState.loading"
                @click="loadPublisherDetectionStatus()"
              >
                <ArrowPathIcon class="h-4 w-4" :class="publisherDetectionState.loading ? 'animate-spin' : ''" />
                刷新状态
              </button>
              <button
                type="button"
                class="btn-primary whitespace-nowrap"
                :disabled="!canInspectPublishers || publisherDetectionState.starting"
                @click="startPublisherDetectionTask(true)"
              >
                {{ publisherDetectionState.starting ? '启动中…' : publisherDetectionResult ? '重新统计' : '开始统计' }}
              </button>
            </div>
          </div>
        </div>

        <div class="grid gap-4 xl:grid-cols-[0.95fr,1.05fr]">
          <div class="rounded-3xl border border-soft bg-surface-muted/60 p-5">
            <div class="flex items-start justify-between gap-4">
              <div>
                <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">任务状态</p>
                <h3 class="mt-2 text-base font-semibold text-primary">{{ publisherDetectionModalTitle }}</h3>
                <p class="mt-2 text-sm text-secondary">{{ publisherDetectionTask?.message || '打开弹窗后不会自动统计，点击“开始统计”即可进入后台执行。' }}</p>
              </div>
              <div class="relative flex h-20 w-20 items-center justify-center">
                <svg class="absolute inset-0 h-full w-full -rotate-90" viewBox="0 0 80 80" aria-hidden="true">
                  <circle
                    cx="40"
                    cy="40"
                    :r="publisherDetectionRingRadius"
                    fill="none"
                    stroke="var(--color-surface-muted)"
                    :stroke-width="publisherDetectionRingStroke"
                  />
                  <circle
                    v-if="publisherDetectionShowProgress"
                    cx="40"
                    cy="40"
                    :r="publisherDetectionRingRadius"
                    fill="none"
                    stroke="rgb(var(--color-brand-600) / 1)"
                    :stroke-width="publisherDetectionRingStroke"
                    stroke-linecap="round"
                    :stroke-dasharray="publisherDetectionRingDasharray"
                  />
                </svg>
                <div class="relative z-10 flex h-12 w-12 items-center justify-center rounded-full bg-surface text-sm font-semibold text-primary">
                  {{ Math.round(publisherDetectionPercentage) }}%
                </div>
              </div>
            </div>

            <div class="mt-4 grid gap-3 sm:grid-cols-3">
              <div class="rounded-2xl border border-soft bg-white px-4 py-3">
                <p class="text-xs text-muted">状态</p>
                <p class="mt-1 text-sm font-semibold text-primary">{{ publisherDetectionStatusLabel }}</p>
              </div>
              <div class="rounded-2xl border border-soft bg-white px-4 py-3">
                <p class="text-xs text-muted">扫描进度</p>
                <p class="mt-1 text-sm font-semibold text-primary">{{ publisherDetectionProgress.completed_tables }} / {{ publisherDetectionProgress.total_tables }}</p>
              </div>
              <div class="rounded-2xl border border-soft bg-white px-4 py-3">
                <p class="text-xs text-muted">候选发布者</p>
                <p class="mt-1 text-sm font-semibold text-primary">{{ formatInteger(publisherDetectionPublishers.length) }}</p>
              </div>
            </div>

            <div class="mt-4 rounded-2xl border border-soft bg-white px-4 py-4 text-sm text-secondary">
              <p>当前表：{{ publisherDetectionProgress.current_table || '—' }}</p>
              <p class="mt-2">已扫描 {{ publisherDetectionScannedTables.length }} 张表，跳过 {{ publisherDetectionSkippedTables.length }} 张，缺失 {{ publisherDetectionMissingTables.length }} 张。</p>
            </div>

            <p v-if="publisherDetectionState.error" class="mt-3 text-xs text-danger">{{ publisherDetectionState.error }}</p>
          </div>

          <div class="rounded-3xl border border-soft bg-surface-muted/60 p-5">
            <div class="flex items-center justify-between gap-3">
              <div>
                <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">Top50 发布者</p>
                <p class="mt-2 text-sm text-secondary">固定返回 50 个发布者，每个发布者附 3 条样本。</p>
              </div>
              <span v-if="publisherDetectionResultGeneratedAt" class="text-xs text-secondary">结果时间 {{ formatTimestamp(publisherDetectionResultGeneratedAt) }}</span>
            </div>

            <div v-if="publisherDetectionPublishers.length" class="mt-4 max-h-[32rem] space-y-3 overflow-y-auto pr-1">
              <article
                v-for="publisher in publisherDetectionPublishers"
                :key="publisher.author"
                class="rounded-3xl border border-soft bg-white p-4"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <div class="flex flex-wrap items-center gap-2">
                      <p class="text-base font-semibold text-primary">{{ publisher.author }}</p>
                      <span class="rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="publisher.blacklisted ? 'bg-rose-100 text-rose-700' : 'bg-slate-100 text-slate-700'">
                        {{ publisher.blacklisted ? '黑名单中' : '未拉黑' }}
                      </span>
                    </div>
                    <p class="mt-1 text-xs text-secondary">命中 {{ formatInteger(publisher.count) }} 条</p>
                  </div>
                  <button
                    type="button"
                    class="rounded-full border px-3 py-1 text-xs font-semibold transition"
                    :class="publisher.blacklisted ? 'border-soft text-secondary hover:text-primary' : 'border-rose-200 text-rose-600 hover:border-rose-300 hover:text-rose-700'"
                    :disabled="sharedPromptState.saving"
                    @click="toggleBlacklist(publisher)"
                  >
                    {{ publisher.blacklisted ? '移出黑名单' : '加入黑名单' }}
                  </button>
                </div>

                <div v-if="publisher.samples?.length" class="mt-4 space-y-2">
                  <div
                    v-for="sample in publisher.samples"
                    :key="`${publisher.author}-${sample.table}-${sample.url}-${sample.published_at}`"
                    class="rounded-2xl border border-soft bg-surface-muted/50 px-3 py-3"
                  >
                    <div class="flex flex-wrap items-center justify-between gap-2">
                      <span class="text-xs font-semibold text-primary">{{ sample.table }}</span>
                      <span class="text-[11px] text-muted">{{ formatTimestamp(sample.published_at) || '时间未知' }}</span>
                    </div>
                    <p v-if="sample.title" class="mt-2 text-sm font-medium text-primary">{{ sample.title }}</p>
                    <p class="mt-2 text-xs leading-5 text-secondary">{{ sample.preview || '暂无样本摘要。' }}</p>
                    <a
                      v-if="sample.url"
                      :href="sample.url"
                      target="_blank"
                      rel="noreferrer"
                      class="mt-2 inline-flex text-xs font-semibold text-brand-600 transition hover:text-brand-700"
                    >
                      打开原文
                    </a>
                  </div>
                </div>
              </article>
            </div>
            <div v-else class="mt-4 rounded-2xl border border-dashed border-soft bg-white px-4 py-6 text-sm text-secondary">
              {{ publisherDetectionRunning ? '异常发布者识别执行中，结果会自动刷新。' : '当前还没有识别结果，点击“开始统计”即可生成。' }}
            </div>
          </div>
        </div>
      </div>
    </AppModal>

    <AppModal
      v-model="stopwordModalOpen"
      title="项目排除词设置"
      description="左侧查看系统整理的高频词建议，右侧维护项目排除词。修改后会同步到当前页面，保存共享配置后正式生效。"
      width="max-w-6xl"
      :show-footer="false"
      scrollable
    >
      <div class="space-y-4">
        <div class="rounded-3xl border border-soft bg-surface-muted/35 p-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="inline-flex rounded-2xl border border-soft bg-white p-1 gap-0.5">
              <button
                v-for="option in stopwordStageOptions"
                :key="option.value"
                type="button"
                class="rounded-xl px-4 py-2 text-xs font-semibold transition-all duration-150"
                :class="stopwordSuggestionStage === option.value ? 'bg-brand-50 text-brand-700 ring-1 ring-brand-100' : 'text-secondary hover:text-primary hover:bg-surface-muted/70'"
                @click="stopwordSuggestionStage = option.value; seedStopwordSuggestionDate(); loadStopwordSuggestionStatus({ syncTopK: true })"
              >
                {{ option.label }}
              </button>
            </div>

            <div class="flex flex-wrap items-center gap-2">
              <span class="text-xs font-medium text-secondary">获取数量</span>
              <div class="inline-flex rounded-2xl border border-soft bg-white p-1 gap-0.5">
                <button
                  v-for="option in stopwordSuggestionTopKOptions"
                  :key="option.value"
                  type="button"
                  class="rounded-xl px-3 py-2 text-xs font-semibold transition-all duration-150"
                  :class="stopwordSuggestionTopKMode === option.value ? 'bg-brand-50 text-brand-700 ring-1 ring-brand-100' : 'text-secondary hover:text-primary hover:bg-surface-muted/70'"
                  @click="stopwordSuggestionTopKMode = option.value"
                >
                  {{ option.label }}
                </button>
              </div>
              <input
                v-if="stopwordSuggestionUsesCustomTopK"
                v-model.trim="stopwordSuggestionCustomTopK"
                type="number"
                min="20"
                step="1"
                class="input w-28"
                placeholder="自定义"
              />
            </div>
          </div>

          <div class="mt-3 grid gap-2 lg:grid-cols-[minmax(0,1fr),auto,auto] lg:items-center">
            <select
              v-model="currentStopwordSuggestionDate"
              class="input w-full min-w-0"
              :disabled="stopwordSuggestionArchivesState.loading || !stopwordSuggestionArchiveOptions.length"
              @change="loadStopwordSuggestionStatus({ syncTopK: true })"
            >
              <option value="" disabled>{{ stopwordSuggestionArchiveOptions.length ? '选择存档范围' : '暂无可用存档' }}</option>
              <option v-for="option in stopwordSuggestionArchiveOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
            <button type="button" class="btn-secondary inline-flex items-center justify-center gap-2 whitespace-nowrap" :disabled="stopwordSuggestionArchivesState.loading" @click="loadStopwordSuggestionArchives">
              <ArrowPathIcon class="h-4 w-4" :class="stopwordSuggestionArchivesState.loading ? 'animate-spin' : ''" />
              刷新存档
            </button>
            <button type="button" class="btn-primary whitespace-nowrap" :disabled="stopwordSuggestionState.starting || !stopwordSuggestionCanRun" @click="startStopwordSuggestionTask(true)">
              {{ stopwordSuggestionState.starting ? '启动中…' : '开始统计词频' }}
            </button>
          </div>
        </div>

        <p v-if="stopwordSuggestionTopKError" class="text-xs text-danger">{{ stopwordSuggestionTopKError }}</p>

        <div class="grid gap-4 xl:grid-cols-[1.02fr,1.18fr]">
          <div class="rounded-3xl border border-soft bg-surface-muted/60 p-5">
            <div class="flex items-start justify-between gap-4">
              <div>
                <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">文档高频词</p>
                <h3 class="mt-2 text-base font-semibold text-primary">{{ stopwordSuggestionTitle }}</h3>
                <p class="mt-2 text-sm text-secondary">{{ stopwordSuggestionTask?.message || '选择一个存档后启动统计。' }}</p>
              </div>
              <div class="relative flex h-20 w-20 items-center justify-center">
                <svg class="absolute inset-0 h-full w-full -rotate-90" viewBox="0 0 80 80" aria-hidden="true">
                  <circle
                    cx="40"
                    cy="40"
                    :r="stopwordSuggestionRingRadius"
                    fill="none"
                    stroke="var(--color-surface-muted)"
                    :stroke-width="stopwordSuggestionRingStroke"
                  />
                  <circle
                    v-if="stopwordSuggestionShowProgress"
                    cx="40"
                    cy="40"
                    :r="stopwordSuggestionRingRadius"
                    fill="none"
                    stroke="rgb(var(--color-brand-600) / 1)"
                    :stroke-width="stopwordSuggestionRingStroke"
                    stroke-linecap="round"
                    :stroke-dasharray="stopwordSuggestionRingDasharray"
                  />
                </svg>
                <div class="relative z-10 flex h-12 w-12 items-center justify-center rounded-full bg-surface text-sm font-semibold text-primary">
                  {{ Math.round(stopwordSuggestionPercentage) }}%
                </div>
              </div>
            </div>

            <div class="mt-4 grid gap-3 sm:grid-cols-3">
              <div class="rounded-2xl border border-soft bg-white px-4 py-3">
                <p class="text-xs text-muted">统计范围</p>
                <p class="mt-1 text-sm font-semibold text-primary">{{ stopwordSuggestionSourceLabel }}</p>
              </div>
              <div class="rounded-2xl border border-soft bg-white px-4 py-3">
                <p class="text-xs text-muted">文档进度</p>
                <p class="mt-1 text-sm font-semibold text-primary">{{ stopwordSuggestionSummary.processed_docs || 0 }} / {{ stopwordSuggestionSummary.total_docs || 0 }}</p>
              </div>
              <div class="rounded-2xl border border-soft bg-white px-4 py-3">
                <p class="text-xs text-muted">词频数量</p>
                <p class="mt-1 text-sm font-semibold text-primary">{{ stopwordSuggestionTaskTopK }}</p>
              </div>
            </div>

            <p v-if="stopwordSuggestionArchivesState.error" class="mt-3 text-xs text-danger">{{ stopwordSuggestionArchivesState.error }}</p>
            <p v-if="stopwordSuggestionState.error" class="mt-2 text-xs text-danger">{{ stopwordSuggestionState.error }}</p>

            <div class="mt-4 space-y-2">
              <div v-if="stopwordSuggestionTerms.length" class="max-h-[28rem] space-y-2 overflow-y-auto pr-1">
                <button
                  v-for="item in stopwordSuggestionTerms"
                  :key="`suggestion-${item.term}`"
                  type="button"
                  class="flex w-full items-center justify-between rounded-2xl border px-4 py-3 text-left transition disabled:cursor-default"
                  :class="isNoiseTermSelected(item.term)
                    ? 'border-rose-200 bg-rose-50/70'
                    : 'border-soft bg-white hover:border-brand-soft hover:bg-brand-50/60'"
                  :disabled="isNoiseTermSelected(item.term)"
                  @click="appendNoiseTerm(item.term)"
                >
                  <div>
                    <p class="text-sm font-semibold" :class="isNoiseTermSelected(item.term) ? 'text-rose-700' : 'text-primary'">{{ item.term }}</p>
                    <p class="mt-1 text-xs" :class="isNoiseTermSelected(item.term) ? 'text-rose-500' : 'text-secondary'">文档频次 {{ item.doc_count }} · 总词频 {{ item.total_count }}</p>
                  </div>
                  <span
                    class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold"
                    :class="isNoiseTermSelected(item.term) ? 'bg-rose-100 text-rose-600' : 'bg-brand-50 text-brand-600'"
                  >
                    {{ isNoiseTermSelected(item.term) ? '已排除' : '追加' }}
                  </span>
                </button>
              </div>
              <div v-else class="rounded-2xl border border-dashed border-soft bg-white px-4 py-6 text-sm text-secondary">
                {{ stopwordSuggestionRunning ? '词频统计执行中，结果会自动刷新。' : '还没有词频建议，点击“开始统计词频”即可生成。' }}
              </div>
            </div>
          </div>

          <div class="rounded-3xl border border-soft bg-surface-muted/60 p-5">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">项目排除词</p>
                <p class="mt-2 text-sm text-secondary">支持换行、空格、逗号（，）或分号（；）分隔。</p>
              </div>
            </div>

            <div class="mt-4 flex gap-2">
              <input v-model.trim="manualNoiseTerm" type="text" class="input flex-1" placeholder="输入一个词后回车或点击追加" @keydown.enter.prevent="appendManualNoiseTerm" />
              <button type="button" class="btn-secondary" @click="appendManualNoiseTerm">追加</button>
            </div>

            <textarea
              v-model="sharedPromptState.projectStopwordsText"
              rows="12"
              class="input mt-4 min-h-[14rem] resize-y"
              placeholder="例如：油烟机 抽油烟机 厨电 方太 老板电器 ..."
            />

            <div class="mt-4 rounded-2xl border border-soft bg-white p-4">
              <div class="flex items-center justify-between gap-3">
                <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">已解析词条</p>
                <span class="text-xs text-secondary">{{ stopwordList.length }} 个</span>
              </div>
              <div v-if="stopwordList.length" class="mt-3 flex max-h-52 flex-wrap gap-2 overflow-y-auto">
                <div
                  v-for="term in stopwordList"
                  :key="`modal-noise-term-${term}`"
                  class="inline-flex items-center gap-1 rounded-full bg-brand-50 py-1 pl-3 pr-1 text-xs font-medium text-brand-700"
                >
                  <span>{{ term }}</span>
                  <button
                    type="button"
                    class="inline-flex h-5 w-5 items-center justify-center rounded-full text-brand-600 transition hover:bg-brand-100 hover:text-brand-700"
                    :aria-label="`移除 ${term}`"
                    @click="removeNoiseTerm(term)"
                  >
                    <XMarkIcon class="h-3 w-3" />
                  </button>
                </div>
              </div>
              <p v-else class="mt-3 text-sm text-secondary">当前还没有排除词，可以手动输入，也可以从左侧建议里点选追加。</p>
            </div>
            <p v-if="sharedPromptState.error" class="mt-3 text-xs text-danger">{{ sharedPromptState.error }}</p>
            <p v-else-if="sharedPromptState.success" class="mt-3 text-xs text-emerald-600">{{ sharedPromptState.success }}</p>
          </div>
        </div>
      </div>
    </AppModal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ArrowPathIcon, CheckIcon, SparklesIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import AppModal from '../../components/AppModal.vue'
import { useProcessingScope } from '../../composables/useProcessingScope'

const POLL_INTERVAL = 3000
const STOPWORD_SPLIT_PATTERN = /[\s,，;；]+/
const BLACKLIST_SPLIT_PATTERN = /[\n,，;；、]+/
const STOPWORD_SUGGESTION_DEFAULT_TOP_K = 100
const STOPWORD_SUGGESTION_TOP_K_OPTIONS = [
  { value: '100', label: '100' },
  { value: '300', label: '300' },
  { value: '500', label: '500' },
  { value: 'custom', label: '自定义' }
]

const {
  callApi,
  currentProjectName,
  projectOptions,
  projectsLoading,
  projectsError,
  selectedProjectName,
  loadProjects,
  refreshProjects,
  datasetOptions,
  datasetsLoading,
  datasetsError,
  selectedDatasetId,
  refreshDatasets,
  databaseOptions,
  databasesLoading,
  databasesError,
  selectedDatabase,
  tableOptions,
  loadDatabases
} = useProcessingScope()

const selectedTables = ref([])
const pollTimer = ref(null)
const stopwordSuggestionTimer = ref(null)
const publisherDetectionTimer = ref(null)
const stopwordModalOpen = ref(false)
const publisherModalOpen = ref(false)
const manualNoiseTerm = ref('')
const stopwordSuggestionStage = ref('post')
const stopwordSuggestionTopKMode = ref(String(STOPWORD_SUGGESTION_DEFAULT_TOP_K))
const stopwordSuggestionCustomTopK = ref('')
const stopwordSuggestionDateByStage = reactive({
  pre: '',
  post: ''
})

const sharedPromptState = reactive({
  loading: false,
  saving: false,
  error: '',
  success: '',
  projectStopwordsText: '',
  publisherBlacklistText: ''
})

const stopwordSuggestionArchivesState = reactive({
  loading: false,
  error: '',
  archives: {
    fetch: [],
    clean: [],
    filter: []
  }
})

const stopwordSuggestionState = reactive({
  loading: false,
  starting: false,
  error: '',
  task: null,
  worker: {}
})

const publisherDetectionState = reactive({
  loading: false,
  starting: false,
  error: '',
  task: null,
  worker: {},
  latestResult: null
})

const postcleanState = reactive({
  running: false,
  success: null,
  message: '',
  logs: [],
  progress: {
    total_tables: 0,
    completed_tables: 0,
    deleted_rows: 0,
    current_table: '',
    percentage: 0
  },
  result: null
})

const stopwordList = computed(() => splitStopwordText(sharedPromptState.projectStopwordsText))
const stopwordSet = computed(() => new Set(stopwordList.value))
const blacklistList = computed(() => splitBlacklistText(sharedPromptState.publisherBlacklistText))
const canRun = computed(() => Boolean(currentProjectName.value && selectedDatabase.value))
const canInspectPublishers = computed(() => Boolean(currentProjectName.value && selectedDatabase.value))
const postcleanResult = computed(() => postcleanState.result && typeof postcleanState.result === 'object' ? postcleanState.result : null)
const statusLabel = computed(() => {
  if (postcleanState.running) return '正在执行'
  if (postcleanState.success === true) {
    const deletedRows = Number(postcleanResult.value?.deleted_rows || postcleanState.progress.deleted_rows || 0)
    return deletedRows > 0 ? '已完成' : '已完成，未命中可删除记录'
  }
  if (postcleanState.success === false) return '执行失败'
  return '待执行'
})
const publisherDetectionTask = computed(() => (
  publisherDetectionState.task && typeof publisherDetectionState.task === 'object'
    ? publisherDetectionState.task
    : null
))
const publisherDetectionStatus = computed(() => String(publisherDetectionTask.value?.status || 'idle'))
const publisherDetectionRunning = computed(() => ['queued', 'running'].includes(publisherDetectionStatus.value))
const publisherDetectionProgress = computed(() => {
  const progress = publisherDetectionTask.value?.progress
  return progress && typeof progress === 'object'
    ? {
        total_tables: Number(progress.total_tables || 0),
        completed_tables: Number(progress.completed_tables || 0),
        percentage: Number(progress.percentage || publisherDetectionTask.value?.percentage || 0),
        current_table: String(progress.current_table || '')
      }
    : {
        total_tables: 0,
        completed_tables: 0,
        percentage: Number(publisherDetectionTask.value?.percentage || 0),
        current_table: ''
      }
})
const publisherDetectionResult = computed(() => {
  const taskResult = publisherDetectionTask.value?.result
  if (taskResult && typeof taskResult === 'object') return taskResult
  return publisherDetectionState.latestResult && typeof publisherDetectionState.latestResult === 'object'
    ? publisherDetectionState.latestResult
    : null
})
const publisherDetectionPublishers = computed(() => {
  const publishers = publisherDetectionResult.value?.publishers
  return Array.isArray(publishers) ? publishers : []
})
const publisherDetectionScannedTables = computed(() => {
  const progressTables = publisherDetectionTask.value?.progress?.scanned_tables
  if (Array.isArray(progressTables) && progressTables.length) return progressTables
  const resultTables = publisherDetectionResult.value?.scanned_tables
  return Array.isArray(resultTables) ? resultTables : []
})
const publisherDetectionSkippedTables = computed(() => {
  const progressTables = publisherDetectionTask.value?.progress?.skipped_tables
  if (Array.isArray(progressTables) && progressTables.length) return progressTables
  const resultTables = publisherDetectionResult.value?.skipped_tables
  return Array.isArray(resultTables) ? resultTables : []
})
const publisherDetectionMissingTables = computed(() => {
  const progressTables = publisherDetectionTask.value?.progress?.missing_tables
  if (Array.isArray(progressTables) && progressTables.length) return progressTables
  const resultTables = publisherDetectionResult.value?.missing_tables
  return Array.isArray(resultTables) ? resultTables : []
})
const publisherDetectionPercentage = computed(() => Number(publisherDetectionProgress.value.percentage || 0))
const publisherDetectionStatusLabel = computed(() => {
  if (publisherDetectionStatus.value === 'running') return '后台执行中'
  if (publisherDetectionStatus.value === 'queued') return '排队中'
  if (publisherDetectionStatus.value === 'completed') return '已完成'
  if (publisherDetectionStatus.value === 'failed') return '执行失败'
  return '待开始'
})
const publisherDetectionModalTitle = computed(() => (
  publisherDetectionRunning.value
    ? '后台统计中'
    : publisherDetectionPublishers.value.length
      ? '识别结果'
      : '等待开始'
))
const publisherDetectionResultGeneratedAt = computed(() => String(publisherDetectionResult.value?.generated_at || ''))
const stopwordStageOptions = [
  { value: 'pre', label: '预处理词频' },
  { value: 'post', label: '后处理词频' }
]
const stopwordSuggestionTopKOptions = STOPWORD_SUGGESTION_TOP_K_OPTIONS
const currentStopwordSuggestionDate = computed({
  get: () => stopwordSuggestionDateByStage[stopwordSuggestionStage.value] || '',
  set: (value) => {
    stopwordSuggestionDateByStage[stopwordSuggestionStage.value] = String(value || '')
  }
})
const stopwordSuggestionUsesCustomTopK = computed(() => stopwordSuggestionTopKMode.value === 'custom')
const stopwordSuggestionTopKError = computed(() => {
  if (!stopwordSuggestionUsesCustomTopK.value) return ''
  const rawValue = String(stopwordSuggestionCustomTopK.value || '').trim()
  if (!rawValue) return '请输入自定义获取数量。'
  const parsed = Number.parseInt(rawValue, 10)
  if (!Number.isInteger(parsed) || parsed < 20) {
    return '自定义获取数量需为不小于 20 的整数。'
  }
  return ''
})
const stopwordSuggestionTopK = computed(() => {
  if (!stopwordSuggestionUsesCustomTopK.value) {
    return Number.parseInt(stopwordSuggestionTopKMode.value, 10) || STOPWORD_SUGGESTION_DEFAULT_TOP_K
  }
  const parsed = Number.parseInt(String(stopwordSuggestionCustomTopK.value || '').trim(), 10)
  return Number.isInteger(parsed) && parsed >= 20 ? parsed : STOPWORD_SUGGESTION_DEFAULT_TOP_K
})
const stopwordSuggestionArchiveOptions = computed(() => {
  const priorities = stopwordSuggestionStage.value === 'pre'
    ? ['clean', 'fetch']
    : ['filter', 'clean', 'fetch']
  const merged = new Map()
  priorities.forEach((layer) => {
    const items = Array.isArray(stopwordSuggestionArchivesState.archives[layer])
      ? stopwordSuggestionArchivesState.archives[layer]
      : []
    items.forEach((item) => {
      const date = String(item?.date || '').trim()
      if (!date) return
      const existing = merged.get(date) || { value: date, labels: [], rank: priorities.indexOf(layer) }
      existing.labels.push(layer.toUpperCase())
      existing.rank = Math.min(existing.rank, priorities.indexOf(layer))
      merged.set(date, existing)
    })
  })
  return Array.from(merged.values())
    .sort((a, b) => a.rank - b.rank || String(b.value).localeCompare(String(a.value)))
    .map((item) => ({
      value: item.value,
      label: `${item.value} · ${Array.from(new Set(item.labels)).join(' / ')}`
    }))
})
const stopwordSuggestionTask = computed(() => (
  stopwordSuggestionState.task && typeof stopwordSuggestionState.task === 'object'
    ? stopwordSuggestionState.task
    : null
))
const stopwordSuggestionTerms = computed(() => {
  const terms = stopwordSuggestionTask.value?.result?.terms
  return Array.isArray(terms) ? terms : []
})
const stopwordSuggestionSummary = computed(() => {
  const summary = stopwordSuggestionTask.value?.summary
  return summary && typeof summary === 'object' ? summary : {}
})
const stopwordSuggestionStatus = computed(() => String(stopwordSuggestionTask.value?.status || 'idle'))
const stopwordSuggestionTaskTopK = computed(() => Number(stopwordSuggestionTask.value?.top_k || stopwordSuggestionTopK.value || STOPWORD_SUGGESTION_DEFAULT_TOP_K))
const stopwordSuggestionPercentage = computed(() => Number(stopwordSuggestionTask.value?.percentage || 0))
const stopwordSuggestionSourceLabel = computed(() => {
  const source = String(stopwordSuggestionSummary.value?.source_layer || stopwordSuggestionTask.value?.source_layer || '').toLowerCase()
  if (source === 'filter') return '当前筛选结果'
  if (source === 'clean') return '预处理结果'
  if (source === 'fetch') return '原始抓取结果'
  return '待生成'
})
const stopwordSuggestionCanRun = computed(() => Boolean(
  currentProjectName.value &&
  currentStopwordSuggestionDate.value &&
  !stopwordSuggestionTopKError.value
))
const stopwordSuggestionRunning = computed(() => ['queued', 'running'].includes(stopwordSuggestionStatus.value))
const stopwordSuggestionTitle = computed(() => (
  stopwordSuggestionRunning.value ? '后台统计中' : '词频建议'
))
const stopwordSuggestionRingRadius = 30
const stopwordSuggestionRingStroke = 8
const stopwordSuggestionRingCircumference = 2 * Math.PI * stopwordSuggestionRingRadius
const stopwordSuggestionShowProgress = computed(() => stopwordSuggestionPercentage.value > 0)
const stopwordSuggestionRingDasharray = computed(() => {
  const percentage = Math.max(0, Math.min(100, stopwordSuggestionPercentage.value))
  const filled = stopwordSuggestionRingCircumference * (percentage / 100)
  return `${filled} ${stopwordSuggestionRingCircumference}`
})
const publisherDetectionRingRadius = 30
const publisherDetectionRingStroke = 8
const publisherDetectionRingCircumference = 2 * Math.PI * publisherDetectionRingRadius
const publisherDetectionShowProgress = computed(() => publisherDetectionPercentage.value > 0)
const publisherDetectionRingDasharray = computed(() => {
  const percentage = Math.max(0, Math.min(100, publisherDetectionPercentage.value))
  const filled = publisherDetectionRingCircumference * (percentage / 100)
  return `${filled} ${publisherDetectionRingCircumference}`
})

watch(tableOptions, (items) => {
  const names = items.map((item) => item.name)
  if (!names.length) {
    selectedTables.value = []
    return
  }
  const preserved = selectedTables.value.filter((item) => names.includes(item))
  selectedTables.value = preserved.length ? preserved : [...names]
}, { immediate: true })

watch([currentProjectName, selectedDatasetId], async ([projectName]) => {
  if (!projectName) {
    resetSharedPromptState()
    resetPublisherDetectionState()
    publisherModalOpen.value = false
    stopwordModalOpen.value = false
    stopPublisherDetectionPolling()
    stopStopwordSuggestionPolling()
    return
  }
  await loadSharedPromptConfig()
}, { immediate: true })

watch([currentProjectName, selectedDatasetId, selectedDatabase], async ([projectName, datasetId, database]) => {
  if (!projectName || !database) {
    stopPolling()
    stopPublisherDetectionPolling()
    resetPostcleanState()
    resetPublisherDetectionState()
    return
  }
  await loadPostcleanStatus({
    project: projectName,
    datasetId,
    database,
    silent: true
  })
  if (publisherModalOpen.value) {
    await loadPublisherDetectionStatus({ silent: true })
  }
})

watch(
  () => selectedTables.value.join('|'),
  async () => {
    if (!currentProjectName.value || !selectedDatabase.value) return
    await loadPostcleanStatus({
      project: currentProjectName.value,
      datasetId: selectedDatasetId.value,
      database: selectedDatabase.value,
      silent: true
    })
    if (publisherModalOpen.value) {
      await loadPublisherDetectionStatus({ silent: true })
    } else {
      resetPublisherDetectionState()
    }
  }
)

onMounted(async () => {
  await loadProjects()
  await loadDatabases()
})

onBeforeUnmount(() => {
  stopPolling()
  stopPublisherDetectionPolling()
  stopStopwordSuggestionPolling()
})

watch(publisherModalOpen, async (open) => {
  if (!open) {
    stopPublisherDetectionPolling()
    return
  }
  await loadPublisherDetectionStatus()
  if (publisherDetectionRunning.value) {
    startPublisherDetectionPolling()
  }
})

watch(stopwordModalOpen, async (open) => {
  if (!open) {
    stopStopwordSuggestionPolling()
    manualNoiseTerm.value = ''
    return
  }
  await loadStopwordSuggestionArchives()
  seedStopwordSuggestionDate()
  await loadStopwordSuggestionStatus({ syncTopK: true })
  if (stopwordSuggestionRunning.value) {
    startStopwordSuggestionPolling()
  }
})

async function refreshAll() {
  await Promise.all([refreshProjects(), refreshDatasets(), loadDatabases()])
  await loadSharedPromptConfig()
  if (currentProjectName.value && selectedDatabase.value) {
    await loadPostcleanStatus({
      project: currentProjectName.value,
      datasetId: selectedDatasetId.value,
      database: selectedDatabase.value,
      silent: true
    })
  }
  if (publisherModalOpen.value) {
    await loadPublisherDetectionStatus({ silent: true })
  }
  if (stopwordModalOpen.value) {
    await loadStopwordSuggestionArchives()
    await loadStopwordSuggestionStatus({ syncTopK: true })
  }
}

function resetSharedPromptState() {
  sharedPromptState.error = ''
  sharedPromptState.success = ''
  sharedPromptState.projectStopwordsText = ''
  sharedPromptState.publisherBlacklistText = ''
}

function resetPublisherDetectionState() {
  publisherDetectionState.loading = false
  publisherDetectionState.starting = false
  publisherDetectionState.error = ''
  publisherDetectionState.task = null
  publisherDetectionState.worker = {}
  publisherDetectionState.latestResult = null
}

function openPublisherModal() {
  if (!canInspectPublishers.value) return
  publisherModalOpen.value = true
}

function openStopwordModal() {
  stopwordSuggestionStage.value = 'post'
  stopwordModalOpen.value = true
}

function selectAllTables() {
  selectedTables.value = tableOptions.value.map((item) => item.name)
}

function clearSelectedTables() {
  selectedTables.value = []
}

function splitStopwordText(value) {
  const parts = String(value || '')
    .split(STOPWORD_SPLIT_PATTERN)
    .map((item) => item.trim())
    .filter(Boolean)
  return Array.from(new Set(parts))
}

function splitBlacklistText(value) {
  const parts = String(value || '')
    .split(BLACKLIST_SPLIT_PATTERN)
    .map((item) => item.trim())
    .filter(Boolean)
  return Array.from(new Set(parts))
}

function buildTableQueryParams(params, tables) {
  tables.forEach((table) => params.append('tables', table))
}

async function loadSharedPromptConfig() {
  if (!currentProjectName.value) return
  sharedPromptState.loading = true
  sharedPromptState.error = ''
  sharedPromptState.success = ''
  try {
    const params = new URLSearchParams()
    params.set('project', currentProjectName.value)
    if (selectedDatasetId.value) params.set('dataset_id', selectedDatasetId.value)
    const response = await callApi(`/api/topic/bertopic/prompt?${params.toString()}`)
    const payload = response?.data || {}
    sharedPromptState.projectStopwordsText = splitStopwordText(payload.project_stopwords_text || payload.project_stopwords || '').join('\n')
    sharedPromptState.publisherBlacklistText = splitBlacklistText(payload.publisher_blacklist_text || payload.publisher_blacklist || '').join('\n')
  } catch (error) {
    sharedPromptState.error = error instanceof Error ? error.message : '读取共享配置失败'
  } finally {
    sharedPromptState.loading = false
  }
}

async function saveSharedPromptConfig({ silent = false } = {}) {
  if (!currentProjectName.value) return false
  sharedPromptState.saving = true
  if (!silent) {
    sharedPromptState.error = ''
    sharedPromptState.success = ''
  }
  try {
    const response = await callApi('/api/topic/bertopic/prompt', {
      method: 'POST',
      body: JSON.stringify({
        project: currentProjectName.value,
        dataset_id: selectedDatasetId.value || undefined,
        project_stopwords: sharedPromptState.projectStopwordsText,
        publisher_blacklist: sharedPromptState.publisherBlacklistText
      })
    })
    const payload = response?.data || {}
    sharedPromptState.projectStopwordsText = splitStopwordText(payload.project_stopwords_text || sharedPromptState.projectStopwordsText).join('\n')
    sharedPromptState.publisherBlacklistText = splitBlacklistText(payload.publisher_blacklist_text || sharedPromptState.publisherBlacklistText).join('\n')
    if (!silent) {
      sharedPromptState.success = '共享配置已保存。'
    }
    return true
  } catch (error) {
    sharedPromptState.error = error instanceof Error ? error.message : '保存共享配置失败'
    return false
  } finally {
    sharedPromptState.saving = false
  }
}

async function toggleBlacklist(publisher) {
  const name = String(publisher?.author || '').trim()
  if (!name) return
  const items = new Set(blacklistList.value)
  if (items.has(name)) {
    items.delete(name)
  } else {
    items.add(name)
  }
  sharedPromptState.publisherBlacklistText = Array.from(items).sort((a, b) => a.localeCompare(b, 'zh-CN')).join('\n')
  const saved = await saveSharedPromptConfig({ silent: false })
  if (saved) {
    await loadPublisherDetectionStatus({ silent: true })
  }
}

function isNoiseTermSelected(term) {
  return stopwordSet.value.has(String(term || '').trim())
}

function appendNoiseTerm(term) {
  const nextTerms = splitStopwordText(`${sharedPromptState.projectStopwordsText}\n${term}`)
  sharedPromptState.projectStopwordsText = nextTerms.join('\n')
}

function removeNoiseTerm(term) {
  sharedPromptState.projectStopwordsText = stopwordList.value.filter((item) => item !== term).join('\n')
}

function appendManualNoiseTerm() {
  const value = String(manualNoiseTerm.value || '').trim()
  if (!value) return
  appendNoiseTerm(value)
  manualNoiseTerm.value = ''
}

function syncStopwordSuggestionTopK(value) {
  const parsed = Number.parseInt(String(value || '').trim(), 10)
  if (!Number.isInteger(parsed) || parsed < 20) {
    stopwordSuggestionTopKMode.value = String(STOPWORD_SUGGESTION_DEFAULT_TOP_K)
    stopwordSuggestionCustomTopK.value = ''
    return
  }
  if ([100, 300, 500].includes(parsed)) {
    stopwordSuggestionTopKMode.value = String(parsed)
    stopwordSuggestionCustomTopK.value = ''
    return
  }
  stopwordSuggestionTopKMode.value = 'custom'
  stopwordSuggestionCustomTopK.value = String(parsed)
}

function seedStopwordSuggestionDate() {
  if (!stopwordSuggestionDateByStage.pre) {
    stopwordSuggestionDateByStage.pre = stopwordSuggestionArchiveOptions.value[0]?.value || ''
  }
  if (!stopwordSuggestionDateByStage.post) {
    stopwordSuggestionDateByStage.post = stopwordSuggestionArchiveOptions.value[0]?.value || ''
  }
}

async function loadStopwordSuggestionArchives() {
  if (!currentProjectName.value) return
  stopwordSuggestionArchivesState.loading = true
  stopwordSuggestionArchivesState.error = ''
  try {
    const params = new URLSearchParams()
    params.set('layers', 'fetch,clean,filter')
    if (selectedDatasetId.value) {
      params.set('dataset_id', selectedDatasetId.value)
    }
    const response = await callApi(`/api/projects/${encodeURIComponent(currentProjectName.value)}/archives?${params.toString()}`)
    const archives = response.archives || {}
    stopwordSuggestionArchivesState.archives = {
      fetch: Array.isArray(archives.fetch) ? archives.fetch : [],
      clean: Array.isArray(archives.clean) ? archives.clean : [],
      filter: Array.isArray(archives.filter) ? archives.filter : []
    }
  } catch (error) {
    stopwordSuggestionArchivesState.archives = { fetch: [], clean: [], filter: [] }
    stopwordSuggestionArchivesState.error = error instanceof Error ? error.message : '读取词频存档失败'
  } finally {
    stopwordSuggestionArchivesState.loading = false
  }
}

async function loadStopwordSuggestionStatus({ syncTopK = false } = {}) {
  if (!currentProjectName.value) return
  stopwordSuggestionState.loading = true
  stopwordSuggestionState.error = ''
  try {
    const params = new URLSearchParams()
    params.set('project', currentProjectName.value)
    params.set('stage', stopwordSuggestionStage.value)
    if (selectedDatasetId.value) {
      params.set('dataset_id', selectedDatasetId.value)
    }
    if (currentStopwordSuggestionDate.value) {
      params.set('date', currentStopwordSuggestionDate.value)
    }
    const response = await callApi(`/api/filter/stopwords/suggestions?${params.toString()}`)
    const payload = response.data || {}
    stopwordSuggestionState.task = payload.task || null
    stopwordSuggestionState.worker = payload.worker || {}
    if (syncTopK && payload.task?.top_k) {
      syncStopwordSuggestionTopK(payload.task.top_k)
    }
    if (payload.date && !currentStopwordSuggestionDate.value) {
      currentStopwordSuggestionDate.value = String(payload.date)
    }
    if (stopwordSuggestionRunning.value) {
      startStopwordSuggestionPolling()
    } else {
      stopStopwordSuggestionPolling()
    }
  } catch (error) {
    stopwordSuggestionState.task = null
    stopwordSuggestionState.worker = {}
    stopwordSuggestionState.error = error instanceof Error ? error.message : '读取词频任务状态失败'
    stopStopwordSuggestionPolling()
  } finally {
    stopwordSuggestionState.loading = false
  }
}

async function startStopwordSuggestionTask(force = true) {
  if (!stopwordSuggestionCanRun.value) return
  stopwordSuggestionState.starting = true
  stopwordSuggestionState.error = ''
  try {
    await callApi('/api/filter/stopwords/suggestions', {
      method: 'POST',
      body: JSON.stringify({
        project: currentProjectName.value,
        dataset_id: selectedDatasetId.value || undefined,
        date: currentStopwordSuggestionDate.value || undefined,
        stage: stopwordSuggestionStage.value,
        top_k: stopwordSuggestionTopK.value,
        force
      })
    })
    await loadStopwordSuggestionStatus({ syncTopK: true })
    startStopwordSuggestionPolling()
  } catch (error) {
    stopwordSuggestionState.error = error instanceof Error ? error.message : '启动词频统计失败'
  } finally {
    stopwordSuggestionState.starting = false
  }
}

async function loadPublisherDetectionStatus({ silent = false } = {}) {
  if (!canInspectPublishers.value) return null
  publisherDetectionState.loading = true
  if (!silent) publisherDetectionState.error = ''
  try {
    const params = new URLSearchParams()
    params.set('project', currentProjectName.value)
    if (selectedDatasetId.value) params.set('dataset_id', selectedDatasetId.value)
    params.set('database', selectedDatabase.value)
    buildTableQueryParams(params, selectedTables.value)
    const response = await callApi(`/api/database/postclean/publishers/status?${params.toString()}`)
    const payload = response?.data || {}
    publisherDetectionState.error = ''
    publisherDetectionState.task = payload.task || null
    publisherDetectionState.worker = payload.worker || {}
    publisherDetectionState.latestResult = payload.latest_result || null
    if (publisherDetectionRunning.value) {
      startPublisherDetectionPolling()
    } else {
      stopPublisherDetectionPolling()
    }
    return payload
  } catch (error) {
    if (!silent) {
      publisherDetectionState.error = error instanceof Error ? error.message : '读取异常发布者任务状态失败'
    }
    stopPublisherDetectionPolling()
    return null
  } finally {
    publisherDetectionState.loading = false
  }
}

async function startPublisherDetectionTask(force = true) {
  if (!canInspectPublishers.value) return
  publisherDetectionState.starting = true
  publisherDetectionState.error = ''
  try {
    await callApi('/api/database/postclean/publishers/task', {
      method: 'POST',
      body: JSON.stringify({
        project: currentProjectName.value,
        dataset_id: selectedDatasetId.value || undefined,
        database: selectedDatabase.value,
        tables: selectedTables.value.length ? selectedTables.value : undefined,
        limit: 50,
        sample_limit: 3,
        force
      })
    })
    await loadPublisherDetectionStatus({ silent: true })
    startPublisherDetectionPolling()
  } catch (error) {
    publisherDetectionState.error = error instanceof Error ? error.message : '启动异常发布者识别失败'
  } finally {
    publisherDetectionState.starting = false
  }
}

function applyPostcleanPayload(payload) {
  if (!payload || typeof payload !== 'object') return
  postcleanState.running = payload.status === 'running'
  postcleanState.success = payload.status === 'completed' ? true : payload.status === 'error' ? false : postcleanState.success
  postcleanState.message = String(payload.message || postcleanState.message || '')
  postcleanState.logs = Array.isArray(payload.logs) ? payload.logs : []
  postcleanState.progress = {
    total_tables: Number(payload.progress?.total_tables || 0),
    completed_tables: Number(payload.progress?.completed_tables || 0),
    deleted_rows: Number(payload.progress?.deleted_rows || 0),
    current_table: String(payload.progress?.current_table || ''),
    percentage: Number(payload.progress?.percentage || 0)
  }
  if (payload.result && typeof payload.result === 'object') {
    postcleanState.result = payload.result
  }
}

function resetPostcleanState() {
  postcleanState.running = false
  postcleanState.success = null
  postcleanState.message = ''
  postcleanState.logs = []
  postcleanState.result = null
  postcleanState.progress = {
    total_tables: 0,
    completed_tables: 0,
    deleted_rows: 0,
    current_table: '',
    percentage: 0
  }
}

async function runPostclean() {
  if (!canRun.value) return
  const confirmed = window.confirm(`将对数据库 ${selectedDatabase.value} 执行后清洗硬删除，是否继续？`)
  if (!confirmed) return
  const saved = await saveSharedPromptConfig({ silent: true })
  if (!saved) return
  postcleanState.success = null
  postcleanState.message = ''
  try {
    const response = await callApi('/api/database/postclean', {
      method: 'POST',
      body: JSON.stringify({
        project: currentProjectName.value,
        dataset_id: selectedDatasetId.value || undefined,
        database: selectedDatabase.value,
        tables: selectedTables.value.length ? selectedTables.value : undefined
      })
    })
    applyPostcleanPayload(response?.data || {})
    postcleanState.running = true
    postcleanState.message = response?.data?.message || '数据库后清洗任务已提交。'
    startPolling()
  } catch (error) {
    postcleanState.success = false
    postcleanState.message = error instanceof Error ? error.message : '启动数据库后清洗失败'
  }
}

async function loadPostcleanStatus({ project, datasetId, database, silent = false }) {
  try {
    const params = new URLSearchParams()
    params.set('project', project)
    if (datasetId) params.set('dataset_id', datasetId)
    params.set('database', database)
    buildTableQueryParams(params, selectedTables.value)
    const response = await callApi(`/api/database/postclean/status?${params.toString()}`)
    applyPostcleanPayload(response?.data || {})
    if (postcleanState.running) {
      startPolling()
    } else {
      stopPolling()
    }
    return response?.data || null
  } catch (error) {
    if (!silent) {
      postcleanState.success = false
      postcleanState.message = error instanceof Error ? error.message : '读取后清洗状态失败'
    }
    return null
  }
}

function startPolling() {
  if (typeof window === 'undefined' || pollTimer.value) return
  pollTimer.value = window.setInterval(() => {
    if (!currentProjectName.value || !selectedDatabase.value) return
    loadPostcleanStatus({
      project: currentProjectName.value,
      datasetId: selectedDatasetId.value,
      database: selectedDatabase.value,
      silent: true
    })
  }, POLL_INTERVAL)
}

function stopPolling() {
  if (typeof window === 'undefined' || !pollTimer.value) return
  window.clearInterval(pollTimer.value)
  pollTimer.value = null
}

function startPublisherDetectionPolling() {
  if (typeof window === 'undefined' || publisherDetectionTimer.value) return
  publisherDetectionTimer.value = window.setInterval(() => {
    if (!currentProjectName.value || !selectedDatabase.value || !publisherModalOpen.value) return
    loadPublisherDetectionStatus({ silent: true })
  }, POLL_INTERVAL)
}

function stopPublisherDetectionPolling() {
  if (typeof window === 'undefined' || !publisherDetectionTimer.value) return
  window.clearInterval(publisherDetectionTimer.value)
  publisherDetectionTimer.value = null
}

function startStopwordSuggestionPolling() {
  if (typeof window === 'undefined' || stopwordSuggestionTimer.value) return
  stopwordSuggestionTimer.value = window.setInterval(() => {
    loadStopwordSuggestionStatus()
  }, POLL_INTERVAL)
}

function stopStopwordSuggestionPolling() {
  if (typeof window === 'undefined' || !stopwordSuggestionTimer.value) return
  window.clearInterval(stopwordSuggestionTimer.value)
  stopwordSuggestionTimer.value = null
}

function formatInteger(value) {
  const num = Number(value || 0)
  if (!Number.isFinite(num)) return '0'
  return new Intl.NumberFormat('zh-CN').format(num)
}

function formatTimestamp(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', { hour12: false })
}
</script>

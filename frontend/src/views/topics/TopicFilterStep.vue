<template>
  <div class="space-y-6 pb-12">
    <header class="flex flex-wrap items-center justify-between gap-4">
      <div class="space-y-1.5">
        <div class="flex items-center gap-3">
          <h1 class="text-xl font-bold tracking-tight text-primary">筛选数据</h1>
          <div class="inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-brand-500 to-brand-600 px-3 py-1 text-[11px] font-semibold text-white">
            <AdjustmentsHorizontalIcon class="h-3.5 w-3.5" />
            <span>Filter</span>
          </div>
        </div>
        <p class="text-sm text-secondary">选定范围后，依次执行预清洗或 AI 筛选；后清洗单独在第三个标签页进行。</p>
      </div>
    </header>

    <section class="sticky top-[4.25rem] z-10 overflow-hidden rounded-3xl border border-brand-100/80 bg-white/95 backdrop-blur-md lg:top-[3.25rem]">
      <div class="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-brand-400 via-brand-500 to-indigo-400" />
      <div class="px-4 py-3 lg:px-5 lg:py-4">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div class="space-y-2">
            <div class="flex flex-wrap items-center gap-2">
              <span class="rounded-full bg-brand-50 px-2.5 py-1 text-[11px] font-semibold text-brand-700">当前任务</span>
              <span class="rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="filterSourceTone">{{ filterSourceLabel }}</span>
              <span class="text-xs text-secondary">优先动作：<span class="font-medium text-secondary">{{ recommendedActionLabel }}</span></span>
            </div>
            <p class="text-sm text-primary">
              项目 <span class="font-semibold">{{ projectSummaryLabel }}</span>
              <span class="text-secondary"> · 数据集 {{ datasetSummaryLabel }} · 处理范围 {{ cleanArchiveSummaryLabel }}</span>
            </p>
          </div>
          <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div class="rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-2">
              <p class="text-[10px] font-medium uppercase tracking-wide text-muted">总条数</p>
              <p class="mt-0.5 text-sm font-bold text-primary">{{ statusState.summary.total_rows || 0 }}</p>
            </div>
            <div class="rounded-xl border border-emerald-100 bg-emerald-50/60 px-3 py-2">
              <p class="text-[10px] font-medium uppercase tracking-wide text-emerald-600/70">保留</p>
              <p class="mt-0.5 text-sm font-bold text-emerald-700">{{ statusState.summary.kept_rows || 0 }}</p>
            </div>
            <div class="rounded-xl border border-indigo-100 bg-indigo-50/60 px-3 py-2">
              <p class="text-[10px] font-medium uppercase tracking-wide text-indigo-500/70">Token</p>
              <p class="mt-0.5 text-sm font-bold text-indigo-700">{{ formatInteger(statusState.summary.token_usage || 0) }}</p>
            </div>
            <div class="rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-2">
              <p class="text-[10px] font-medium uppercase tracking-wide text-muted">更新时间</p>
              <p class="mt-0.5 text-sm font-bold text-primary">{{ formatTimestamp(statusState.summary.updated_at) || '—' }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-0.5">
          <div class="flex items-center gap-2">
            <span class="h-4 w-1 rounded-full bg-brand-500" />
            <h2 class="text-base font-bold text-primary">筛选范围与排除词设置</h2>
          </div>
          <p class="pl-3 text-sm text-secondary">选择项目与处理范围后，就可以统一维护排除词；保存后，预清洗和后清洗都会使用。</p>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600"
          :disabled="projectsLoading"
          @click="refreshProjects"
        >
          <ArrowPathIcon class="h-4 w-4" :class="projectsLoading ? 'animate-spin' : ''" />
          刷新项目
        </button>
      </div>

      <div class="grid gap-5 xl:grid-cols-[1.05fr,1.3fr]">
        <div class="space-y-4 rounded-3xl border border-soft bg-surface-muted/60 p-5">
          <div>
            <h3 class="text-base font-semibold text-primary">筛选范围</h3>
            <p class="mt-1 text-sm text-secondary">指定项目、数据集和当前处理范围。</p>
          </div>

          <label class="space-y-2">
            <span class="text-xs font-semibold text-muted">项目</span>
            <select v-model="selectedProjectName" class="input" :disabled="projectsLoading || !projectOptions.length">
              <option value="" disabled>请选择项目</option>
              <option v-for="option in projectOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
            <p v-if="projectsError" class="text-xs text-danger">{{ projectsError }}</p>
          </label>

          <label class="space-y-2">
            <span class="text-xs font-semibold text-muted">数据集</span>
            <select v-model="selectedDatasetId" class="input" :disabled="datasetsLoading || !datasetOptions.length">
              <option value="">项目级默认上下文</option>
              <option v-for="option in datasetOptions" :key="option.id" :value="option.id">
                {{ option.label }}
              </option>
            </select>
            <p v-if="datasetsError" class="text-xs text-danger">{{ datasetsError }}</p>
          </label>

          <label class="space-y-2">
            <span class="flex items-center justify-between gap-3">
              <span class="text-xs font-semibold text-muted">处理范围</span>
              <button
                type="button"
                class="text-xs font-semibold text-brand-600 transition hover:text-brand-700"
                :disabled="cleanArchivesState.loading || !currentProjectName"
                @click="loadCleanArchives({ force: true })"
              >
                {{ cleanArchivesState.loading ? '加载中…' : '刷新' }}
              </button>
            </span>
            <div v-if="cleanArchivesState.loading" class="rounded-2xl border border-soft bg-white px-4 py-3 text-sm text-secondary">
              正在同步可用范围…
            </div>
            <select v-else v-model="selectedCleanDate" class="input" :disabled="!cleanArchiveOptions.length">
              <option value="" disabled>{{ cleanArchiveOptions.length ? '请选择处理范围' : '暂无可用范围' }}</option>
              <option v-for="option in cleanArchiveOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
            <p v-if="cleanArchivesState.error" class="text-xs text-danger">{{ cleanArchivesState.error }}</p>
            <div v-else class="space-y-2">
              <p class="text-xs text-secondary">{{ scopeHelperText }}</p>
              <button
                v-if="showPreprocessCta"
                type="button"
                class="inline-flex items-center gap-2 text-xs font-semibold text-brand-600 transition hover:text-brand-700"
                @click="goToPreprocess"
              >
                <ArrowUpRightIcon class="h-3.5 w-3.5" />
                前往数据预处理
              </button>
            </div>
          </label>
        </div>

        <div class="space-y-3">
          <div class="rounded-3xl border border-soft bg-surface-muted/60 p-5">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 class="text-base font-semibold text-primary">排除词设置</h3>
                <p class="mt-1 text-sm text-secondary">项目级共享词表。你可以在弹窗里查看高频词建议，并维护需要排除的词。</p>
              </div>
            </div>

            <div class="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-soft bg-white px-4 py-4">
              <div class="space-y-1">
                <p class="text-xs text-muted">当前词条</p>
                <p class="text-2xl font-semibold text-primary">{{ parsedNoiseTerms.length }}</p>
                <p class="text-xs text-secondary">可在弹窗内手动维护，也可以直接加入建议词。</p>
              </div>
              <button
                type="button"
                class="btn-primary inline-flex items-center gap-2"
                :disabled="!currentProjectName"
                @click="openStopwordModal('pre')"
              >
                打开排除词弹窗
              </button>
            </div>
            <p v-if="sharedPromptState.error" class="mt-3 text-xs text-danger">{{ sharedPromptState.error }}</p>
            <p v-else-if="sharedPromptState.success" class="mt-3 text-xs text-emerald-600">{{ sharedPromptState.success }}</p>

            <div class="mt-4 rounded-2xl border border-soft bg-white p-4">
              <div class="flex items-center justify-between gap-3">
                <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">词条预览</p>
                <span class="text-xs text-secondary">{{ parsedNoiseTerms.length ? '命中即丢弃' : '打开弹窗开始维护' }}</span>
              </div>
              <div v-if="previewNoiseTerms.length" class="mt-3 flex max-h-52 flex-wrap gap-2 overflow-y-auto">
                <span
                  v-for="term in previewNoiseTerms"
                  :key="`noise-term-${term}`"
                  class="rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700"
                >
                  {{ term }}
                </span>
              </div>
              <p v-else class="mt-3 text-sm text-secondary">当前还没有排除词。建议先补充后再执行预清洗。</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-0.5">
          <div class="flex items-center gap-2">
            <span class="h-4 w-1 rounded-full bg-brand-500" />
            <h2 class="text-base font-bold text-primary">执行筛选</h2>
          </div>
          <p class="pl-3 text-sm text-secondary">在此执行筛选操作，结果详情请在下方"结果与记录"中查看。</p>
        </div>
        <div class="inline-flex rounded-2xl border border-soft bg-surface-muted/70 p-1 gap-0.5">
          <button
            v-for="tab in tabOptions"
            :key="tab.value"
            type="button"
            class="rounded-xl px-4 py-2 text-xs font-semibold transition-all duration-150"
            :class="activeTab === tab.value ? 'bg-white text-brand-700 ring-1 ring-brand-100' : 'text-secondary hover:text-primary hover:bg-white/50'"
            @click="activeTab = tab.value"
          >
            {{ tab.label }}
          </button>
        </div>
      </div>

      <div v-if="activeTab === 'preclean'" class="grid gap-5 xl:grid-cols-3">
        <div class="space-y-4 rounded-3xl border border-brand-200 bg-brand-50/50 p-5 xl:col-span-2">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">预清洗</p>
            <h3 class="mt-2 text-base font-semibold text-primary">先做预清洗</h3>
            <p class="mt-2 text-sm text-secondary">适合先快速剔除明显噪声，不消耗 token。完成后会生成当前筛选结果。</p>
          </div>
          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <div class="rounded-2xl border border-soft bg-white px-4 py-3"><p class="text-xs text-muted">适用场景</p><p class="mt-1 text-sm font-semibold text-primary">先排明显噪声</p></div>
            <div class="rounded-2xl border border-soft bg-white px-4 py-3"><p class="text-xs text-muted">执行前提</p><p class="mt-1 text-sm font-semibold text-primary">{{ canRunPreclean ? '已可执行' : '需先选好处理范围' }}</p></div>
            <div class="rounded-2xl border border-soft bg-white px-4 py-3"><p class="text-xs text-muted">排除词</p><p class="mt-1 text-sm font-semibold text-primary">{{ parsedNoiseTerms.length }} 个</p></div>
          </div>
          <div class="flex min-h-[3rem] flex-wrap items-center gap-3">
            <button type="button" class="btn-primary inline-flex items-center gap-2" :disabled="!canRunPreclean || precleanState.running" @click="runPreclean">
              <SparklesIcon class="h-4 w-4" />
              {{ precleanState.running ? '预清洗执行中…' : '先做预清洗' }}
            </button>
            <button
              v-if="showPreprocessCta && !canRunPreclean"
              type="button"
              class="btn-secondary inline-flex items-center gap-2"
              @click="goToPreprocess"
            >
              <ArrowUpRightIcon class="h-4 w-4" />
              去做数据预处理
            </button>
            <p v-if="precleanState.message" class="text-xs" :class="precleanState.success === false ? 'text-danger' : 'text-secondary'">
              {{ precleanState.message }}
            </p>
          </div>
        </div>

        <div class="rounded-3xl border border-soft bg-surface-muted/60 p-5">
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">执行提示</p>
          <p class="mt-3 text-sm text-secondary">预清洗会按照当前排除词，直接过滤明显噪声内容。完成后可在下方“结果与记录”查看输出。</p>
          <button
            v-if="showPreprocessCta && !canRunPreclean"
            type="button"
            class="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-brand-600 transition hover:text-brand-700"
            @click="goToPreprocess"
          >
            <ArrowUpRightIcon class="h-3.5 w-3.5" />
            当前还没有可用范围，前往数据预处理
          </button>
        </div>
      </div>

      <div v-else-if="activeTab === 'ai'" class="grid gap-5 xl:grid-cols-[1.25fr,1fr]">
        <div class="space-y-4 rounded-3xl border border-soft bg-surface-muted/60 p-5">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">AI 筛选</p>
            <h3 class="mt-2 text-base font-semibold text-primary">运行 AI 筛选</h3>
            <p class="mt-2 text-sm text-secondary">适合在预清洗之后继续细筛。会调用模型并消耗 token。</p>
          </div>

          <label class="space-y-2">
            <span class="text-xs font-semibold text-muted">筛选主题</span>
            <input v-model.trim="aiTemplateState.theme" type="text" class="input" placeholder="例如：控烟政策、校园安全" />
          </label>

          <label class="space-y-2">
            <span class="text-xs font-semibold text-muted">分类选项</span>
            <textarea
              v-model="aiTemplateState.categoriesText"
              rows="5"
              class="input min-h-[9rem] resize-y"
              placeholder="支持换行、空格、逗号、中文逗号、分号。"
            />
          </label>

          <div class="grid gap-3 sm:grid-cols-2">
            <button type="button" class="btn-secondary" :disabled="aiTemplateState.loading || !currentProjectName" @click="loadAiTemplateConfig">
              {{ aiTemplateState.loading ? '读取中…' : '读取现有模板' }}
            </button>
            <button type="button" class="btn-primary" :disabled="aiTemplateState.saving || !canSaveAiTemplate" @click="saveAiTemplateConfig">
              {{ aiTemplateState.saving ? '保存中…' : '保存模板' }}
            </button>
          </div>

          <p v-if="aiTemplateState.error" class="text-xs text-danger">{{ aiTemplateState.error }}</p>
          <p v-else-if="aiTemplateState.success" class="text-xs text-emerald-600">{{ aiTemplateState.success }}</p>

          <div class="rounded-3xl border border-soft bg-slate-950 px-4 py-4">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Template Preview</p>
            <pre class="mt-3 max-h-72 overflow-y-auto whitespace-pre-wrap break-words text-xs leading-6 text-slate-200">{{ aiTemplatePreview }}</pre>
          </div>
        </div>

        <div class="space-y-4 rounded-3xl border border-soft bg-surface-muted/60 p-5">
          <div class="rounded-2xl border border-soft bg-white px-4 py-3">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">模型配置</p>
            <p class="mt-2 text-sm font-semibold text-primary">{{ aiConfigLabel }}</p>
          </div>

          <div class="rounded-2xl border border-soft bg-white px-4 py-3">
            <p class="text-xs text-muted">执行前提</p>
            <p class="mt-1 text-sm font-semibold text-primary">{{ canRunAiFilter ? '已可执行' : '需先选好处理范围' }}</p>
            <p class="mt-1 text-xs text-secondary">目标日期 {{ selectedCleanDate || cleanArchivesState.latest || '—' }}</p>
          </div>

          <div class="rounded-2xl border border-soft bg-white px-4 py-3">
            <p class="text-xs text-muted">执行提示</p>
            <p class="mt-1 text-sm font-semibold text-primary">{{ statusState.running ? '任务运行中' : '空闲' }}</p>
            <p class="mt-1 text-xs text-secondary">会直接更新当前筛选结果。</p>
          </div>

          <button type="button" class="btn-primary inline-flex w-full items-center justify-center gap-2" :disabled="!canRunAiFilter || aiRunState.running" @click="runAiFilter">
            <SparklesIcon class="h-4 w-4" />
            {{ aiRunState.running ? 'AI 筛选运行中…' : '运行 AI 筛选' }}
          </button>
          <p v-if="aiRunState.message" class="text-xs" :class="aiRunState.success === false ? 'text-danger' : 'text-secondary'">
            {{ aiRunState.message }}
          </p>
        </div>
      </div>

      <div v-else class="grid gap-5 xl:grid-cols-[1.1fr,1fr]">
        <div class="space-y-4 rounded-3xl border border-rose-200 bg-rose-50/50 p-5">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-rose-500">后清洗</p>
            <h3 class="mt-2 text-base font-semibold text-primary">清理数据库噪声</h3>
            <p class="mt-2 text-sm text-secondary">只在你确认当前筛选结果之后再做。将直接删除数据库记录，无法撤销。</p>
          </div>

          <div class="rounded-3xl border border-rose-200 bg-white px-4 py-3 text-sm text-rose-700">
            <p class="font-semibold">危险操作</p>
            <p class="mt-1 text-xs leading-relaxed">建议先确认数据库名，再核对是否需要限制表名。执行后不会进入回收站。</p>
            <p class="mt-1 text-xs leading-relaxed">若本次确实删除了记录，系统会自动提交当前项目已有本地缓存的同步任务，进度可在后台任务中查看。</p>
          </div>

          <label class="space-y-2">
            <span class="flex items-center justify-between gap-3">
              <span class="text-xs font-semibold text-muted">目标数据库</span>
              <button
                type="button"
                class="text-xs font-semibold text-brand-600 transition hover:text-brand-700"
                :disabled="postcleanState.loadingDatabases"
                @click="loadDatabaseOptions"
              >
                {{ postcleanState.loadingDatabases ? '刷新中…' : '刷新数据库' }}
              </button>
            </span>
            <select v-model="postcleanState.database" class="input" :disabled="postcleanState.loadingDatabases || !databaseOptions.length">
              <option value="" disabled>{{ databaseOptions.length ? '请选择数据库' : '暂无数据库' }}</option>
              <option v-for="option in databaseOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>

          <label class="space-y-2">
            <span class="text-xs font-semibold text-muted">限制表名（可选）</span>
            <textarea
              v-model="postcleanState.tablesText"
              rows="4"
              class="input min-h-[7rem] resize-y"
              placeholder="留空表示扫描全部业务表；支持换行、逗号、分号。"
            />
          </label>

          <button type="button" class="inline-flex w-full items-center justify-center gap-2 rounded-full bg-rose-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60" :disabled="!canRunPostclean || postcleanState.running" @click="runPostclean">
            <TrashIcon class="h-4 w-4" />
            {{ postcleanState.running ? '后清洗执行中…' : '清理数据库噪声' }}
          </button>
          <div v-if="postcleanState.running" class="rounded-2xl border border-soft bg-white px-4 py-3 text-xs text-secondary">
            <p class="font-semibold text-primary">正在处理</p>
            <p class="mt-1">当前表：{{ postcleanState.progress.current_table || '准备中' }}</p>
            <p class="mt-1">进度：{{ postcleanState.progress.completed_tables || 0 }} / {{ postcleanState.progress.total_tables || 0 }} · {{ postcleanState.progress.percentage || 0 }}%</p>
            <p class="mt-1">最近更新：{{ formatTimestamp(postcleanState.lastHeartbeat) || '—' }}</p>
          </div>
          <p v-if="postcleanState.message" class="text-xs" :class="postcleanState.success === false ? 'text-danger' : 'text-secondary'">
            {{ postcleanState.message }}
          </p>
        </div>

        <div class="rounded-3xl border border-soft bg-surface-muted/60 p-5">
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">处理结果</p>
          <div v-if="postcleanState.logs.length" class="mt-4 rounded-2xl border border-soft bg-slate-950 px-4 py-4">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">处理记录</p>
            <div class="mt-3 max-h-56 space-y-2 overflow-y-auto">
              <article
                v-for="(log, index) in postcleanState.logs"
                :key="`postclean-log-${index}`"
                class="rounded-xl bg-slate-900/80 px-3 py-2"
              >
                <p class="text-[11px] text-slate-400">{{ formatTimestamp(log.ts) || '—' }} · {{ log.event || 'progress' }}</p>
                <p class="mt-1 text-xs leading-5" :class="log.level === 'error' ? 'text-rose-300' : 'text-slate-200'">{{ log.message || '—' }}</p>
              </article>
            </div>
          </div>
          <div v-if="postcleanState.lastResult" class="mt-4 space-y-3">
            <div class="rounded-2xl border border-soft bg-white px-4 py-3">
              <p class="text-xs text-muted">审计报告</p>
              <p class="mt-1 text-sm font-semibold text-primary break-all">{{ postcleanState.lastResult.report_path || '—' }}</p>
            </div>
            <div class="rounded-2xl border border-soft bg-white px-4 py-3">
              <p class="text-xs text-muted">总删除数</p>
              <p class="mt-1 text-lg font-semibold text-rose-700">{{ postcleanState.lastResult.deleted_rows || 0 }}</p>
            </div>
            <div v-if="postcleanState.lastResult.follow_up" class="rounded-2xl border border-soft bg-white px-4 py-3">
              <p class="text-xs text-muted">本地缓存同步</p>
              <p class="mt-1 text-sm font-semibold text-primary">
                {{ postcleanState.lastResult.follow_up.message || '—' }}
              </p>
              <p
                v-if="Array.isArray(postcleanState.lastResult.follow_up.ranges) && postcleanState.lastResult.follow_up.ranges.length"
                class="mt-1 text-xs text-secondary"
              >
                共 {{ postcleanState.lastResult.follow_up.ranges.length }} 个缓存批次。
              </p>
            </div>
            <div class="space-y-2">
              <article
                v-for="table in postcleanState.lastResult.tables || []"
                :key="`postclean-table-${table.table}`"
                class="rounded-2xl border border-soft bg-white px-4 py-3"
              >
                <div class="flex items-center justify-between gap-3">
                  <div>
                    <p class="text-sm font-semibold text-primary">{{ table.table }}</p>
                    <p class="text-xs text-secondary">{{ (table.matched_columns || []).join(' / ') || table.reason || '—' }}</p>
                  </div>
                  <span class="text-sm font-semibold text-rose-700">{{ table.deleted_rows || 0 }}</span>
                </div>
              </article>
            </div>
          </div>
          <p v-else-if="postcleanState.running" class="mt-4 text-sm text-secondary">后清洗任务正在运行，审计结果会在完成后自动展示。</p>
          <p v-else class="mt-4 text-sm text-secondary">尚未执行后清洗。</p>
        </div>
      </div>
    </section>

    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-0.5">
          <div class="flex items-center gap-2">
            <span class="h-4 w-1 rounded-full bg-brand-500" />
            <h2 class="text-base font-bold text-primary">结果与记录</h2>
          </div>
          <p class="pl-3 text-sm text-secondary">查看本次筛选的摘要统计、最近处理记录及保留 / 丢弃样本。</p>
        </div>
        <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="statusLoading || !currentProjectName || !selectedCleanDate" @click="loadStatus">
          <ArrowPathIcon class="h-4 w-4" :class="statusLoading ? 'animate-spin' : ''" />
          刷新状态
        </button>
      </div>

      <div class="grid gap-3 md:grid-cols-4">
        <div class="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
          <p class="text-[10px] font-medium uppercase tracking-wide text-muted">结果来源</p>
          <p class="mt-1.5 text-base font-bold text-primary">{{ filterSourceLabel }}</p>
        </div>
        <div class="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
          <p class="text-[10px] font-medium uppercase tracking-wide text-muted">总条数</p>
          <p class="mt-1.5 text-base font-bold text-primary">{{ statusState.summary.total_rows || 0 }}</p>
        </div>
        <div class="rounded-2xl border border-emerald-100 bg-emerald-50/70 px-4 py-4">
          <p class="text-[10px] font-medium uppercase tracking-wide text-emerald-600/70">保留</p>
          <p class="mt-1.5 text-base font-bold text-emerald-700">{{ statusState.summary.kept_rows || 0 }}</p>
        </div>
        <div class="rounded-2xl border border-indigo-100 bg-indigo-50/70 px-4 py-4">
          <p class="text-[10px] font-medium uppercase tracking-wide text-indigo-500/70">Token</p>
          <p class="mt-1.5 text-base font-bold text-indigo-700">{{ formatInteger(statusState.summary.token_usage || 0) }}</p>
        </div>
      </div>

      <div v-if="showResultEmptyState" class="rounded-3xl border border-dashed border-soft px-5 py-8 text-center">
        <p class="text-base font-semibold text-primary">{{ resultEmptyTitle }}</p>
        <p class="mt-2 text-sm text-secondary">{{ resultEmptyDescription }}</p>
        <button
          v-if="showPreprocessCta"
          type="button"
          class="btn-secondary mt-4 inline-flex items-center gap-2"
          @click="goToPreprocess"
        >
          <ArrowUpRightIcon class="h-4 w-4" />
          去做数据预处理
        </button>
      </div>

      <p v-else-if="statusState.message" class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
        {{ statusState.message }}
      </p>

      <div v-if="!showResultEmptyState" class="grid gap-5 xl:grid-cols-[1.25fr,1fr]">
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-bold text-primary">最近处理记录</h3>
            <span class="rounded-full bg-surface-muted px-2.5 py-1 text-[11px] font-semibold text-muted">{{ statusState.recentRecords.length }} 条</span>
          </div>
          <div v-if="statusState.recentRecords.length" class="space-y-2.5">
            <article
              v-for="(record, index) in statusState.recentRecords"
              :key="`filter-recent-${record.channel}-${record.index}-${index}`"
              class="rounded-2xl border bg-white px-4 py-4"
              :class="record.status === 'discarded' ? 'border-rose-100' : 'border-emerald-100'"
            >
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div class="flex items-center gap-2">
                  <span class="rounded-full bg-brand-50 px-2.5 py-1 text-[11px] font-semibold text-brand-700">{{ record.channel || 'unknown' }}</span>
                  <span class="text-[11px] text-muted">{{ formatTimestamp(record.updated_at) || '—' }}</span>
                </div>
                <span class="rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="record.status === 'discarded' ? 'bg-rose-50 text-rose-700' : 'bg-emerald-50 text-emerald-700'">
                  {{ record.status === 'discarded' ? '已丢弃' : '已保留' }}
                </span>
              </div>
              <p class="mt-2.5 text-sm font-semibold text-primary">{{ record.title || '无标题记录' }}</p>
              <p class="mt-1 text-sm text-secondary">{{ record.preview || '—' }}</p>
              <p v-if="record.matched_terms?.length" class="mt-2 text-xs text-rose-600">
                命中词：{{ record.matched_terms.join('、') }}
              </p>
            </article>
          </div>
          <div v-else class="rounded-2xl border border-dashed border-soft px-4 py-8 text-center text-sm text-secondary">
            当前还没有筛选记录。
          </div>
        </div>

        <div class="space-y-3">
          <div class="rounded-3xl border border-emerald-100 bg-emerald-50/40 p-4">
            <p class="text-xs font-bold text-emerald-700">保留样本</p>
            <div v-if="statusState.relevantSamples.length" class="mt-3 space-y-2">
              <article v-for="(item, index) in statusState.relevantSamples" :key="`relevant-${item.channel}-${index}`" class="rounded-2xl border border-emerald-100/70 bg-white px-4 py-3">
                <p class="text-sm font-semibold text-primary">{{ item.title || '无标题记录' }}</p>
                <p class="mt-1 text-xs text-secondary">{{ item.preview || '—' }}</p>
              </article>
            </div>
            <p v-else class="mt-3 text-sm text-secondary">暂无保留样本。</p>
          </div>

          <div class="rounded-3xl border border-rose-100 bg-rose-50/40 p-4">
            <p class="text-xs font-bold text-rose-600">丢弃样本</p>
            <div v-if="statusState.irrelevantSamples.length" class="mt-3 space-y-2">
              <article v-for="(item, index) in statusState.irrelevantSamples" :key="`irrelevant-${item.channel}-${index}`" class="rounded-2xl border border-rose-100/70 bg-white px-4 py-3">
                <p class="text-sm font-semibold text-primary">{{ item.title || '无标题记录' }}</p>
                <p class="mt-1 text-xs text-secondary">{{ item.preview || '—' }}</p>
              </article>
            </div>
            <p v-else class="mt-3 text-sm text-secondary">暂无丢弃样本。</p>
          </div>
        </div>
      </div>
    </section>

    <AppModal
      v-model="stopwordModalOpen"
      title="项目排除词设置"
      description="左侧查看系统整理的高频词建议，右侧维护项目排除词。保存后，预清洗和后清洗都会使用。"
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
                <p class="mt-2 text-sm text-secondary">支持换行、空格、逗号（，）或分号（；）分隔，修改后会自动保存。</p>
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
                <span class="text-xs text-secondary">{{ parsedNoiseTerms.length }} 个</span>
              </div>
              <div v-if="parsedNoiseTerms.length" class="mt-3 flex max-h-52 flex-wrap gap-2 overflow-y-auto">
                <div
                  v-for="term in parsedNoiseTerms"
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
            <p v-else-if="sharedPromptState.saving" class="mt-3 text-xs text-secondary">正在自动保存…</p>
            <p v-else-if="sharedPromptState.success" class="mt-3 text-xs text-emerald-600">{{ sharedPromptState.success }}</p>
          </div>
        </div>
      </div>
    </AppModal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  AdjustmentsHorizontalIcon,
  ArrowPathIcon,
  ArrowUpRightIcon,
  SparklesIcon,
  TrashIcon,
  XMarkIcon
} from '@heroicons/vue/24/outline'
import AppModal from '../../components/AppModal.vue'
import { useApiBase } from '../../composables/useApiBase'
import { useTopicCreationProject } from '../../composables/useTopicCreationProject'

const { callApi } = useApiBase()
const router = useRouter()
const {
  projectOptions,
  projectsLoading,
  projectsError,
  selectedProjectName,
  loadProjects,
  refreshProjects
} = useTopicCreationProject()

const SPLIT_PATTERN = /[\s,，;；]+/
const POLL_INTERVAL = 2000
const SHARED_PROMPT_AUTOSAVE_DELAY = 800
const STOPWORD_SUGGESTION_DEFAULT_TOP_K = 100
const STOPWORD_SUGGESTION_TOP_K_OPTIONS = [
  { value: '100', label: '100' },
  { value: '300', label: '300' },
  { value: '500', label: '500' },
  { value: 'custom', label: '自定义' }
]

const datasets = ref([])
const datasetsLoading = ref(false)
const datasetsError = ref('')
const selectedDatasetId = ref('')

const cleanArchivesState = reactive({
  loading: false,
  error: '',
  items: [],
  latest: ''
})
const selectedCleanDate = ref('')
const stopwordModalOpen = ref(false)
const manualNoiseTerm = ref('')
const stopwordSuggestionStage = ref('pre')
const stopwordSuggestionTopKMode = ref(String(STOPWORD_SUGGESTION_DEFAULT_TOP_K))
const stopwordSuggestionCustomTopK = ref('')
const stopwordSuggestionDateByStage = reactive({
  pre: '',
  post: ''
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

const sharedPromptState = reactive({
  loading: false,
  saving: false,
  error: '',
  success: '',
  path: '',
  rawPayload: null,
  projectStopwordsText: ''
})
let sharedPromptAutosaveTimer = null
let sharedPromptAutosaveSuspend = false
let sharedPromptLastSavedText = ''

const aiTemplateState = reactive({
  loading: false,
  saving: false,
  error: '',
  success: '',
  exists: false,
  path: '',
  theme: '',
  categoriesText: '',
  template: ''
})

const postcleanState = reactive({
  loadingDatabases: false,
  databases: [],
  database: '',
  tablesText: '',
  activeTables: [],
  running: false,
  success: null,
  message: '',
  lastResult: null,
  lastHeartbeat: '',
  logs: [],
  progress: {
    total_tables: 0,
    completed_tables: 0,
    deleted_rows: 0,
    current_table: '',
    percentage: 0
  }
})

const precleanState = reactive({
  running: false,
  success: null,
  message: '',
  lastResult: null
})

const aiRunState = reactive({
  running: false,
  success: null,
  message: ''
})

const statusState = reactive({
  running: false,
  message: '',
  source: '',
  aiConfig: {},
  progress: {
    total: 0,
    completed: 0,
    failed: 0,
    kept: 0,
    percentage: 0,
    token_usage: 0
  },
  summary: {
    total_rows: 0,
    kept_rows: 0,
    discarded_rows: 0,
    token_usage: 0,
    updated_at: '',
    source: ''
  },
  recentRecords: [],
  relevantSamples: [],
  irrelevantSamples: []
})

const statusLoading = ref(false)
const activeTab = ref('preclean')
const statusTimer = ref(null)
const postcleanTimer = ref(null)
const stopwordSuggestionTimer = ref(null)

const currentProjectName = computed(() => String(selectedProjectName.value || '').trim())
const datasetOptions = computed(() =>
  datasets.value.map((item) => ({ id: item.id, label: item.display_name || item.id, raw: item }))
)
const cleanArchiveOptions = computed(() =>
  (cleanArchivesState.items || []).map((item) => ({
    value: item.date,
    label: item.matches_dataset ? `${item.date} · 匹配当前数据集` : item.date
  }))
)
const databaseOptions = computed(() =>
  (postcleanState.databases || []).map((item) => ({ value: item.name, label: item.name }))
)
const parsedNoiseTerms = computed(() => splitDelimitedText(sharedPromptState.projectStopwordsText))
const parsedNoiseTermSet = computed(() => new Set(parsedNoiseTerms.value))
const parsedCategories = computed(() => splitDelimitedText(aiTemplateState.categoriesText))
const selectedTables = computed(() => splitDelimitedText(postcleanState.tablesText))
const canSaveAiTemplate = computed(() => Boolean(currentProjectName.value && aiTemplateState.theme.trim() && parsedCategories.value.length))
const canRunPreclean = computed(() => Boolean(currentProjectName.value && (selectedCleanDate.value || cleanArchivesState.latest)))
const canRunAiFilter = computed(() => Boolean(currentProjectName.value && (selectedCleanDate.value || cleanArchivesState.latest)))
const canRunPostclean = computed(() => Boolean(currentProjectName.value && postcleanState.database))
const filterSourceLabel = computed(() => {
  const source = statusState.source || statusState.summary.source || ''
  if (source === 'keyword-preclean') return '预清洗结果'
  if (source === 'ai-filter') return 'AI 筛选结果'
  return '尚未生成筛选结果'
})
const filterSourceTone = computed(() => {
  const source = statusState.source || statusState.summary.source || ''
  if (source === 'keyword-preclean') return 'bg-emerald-50 text-emerald-700'
  if (source === 'ai-filter') return 'bg-brand-50 text-brand-700'
  return 'bg-slate-100 text-slate-600'
})
const statusDateLabel = computed(() => selectedCleanDate.value || cleanArchivesState.latest || '—')
const projectSummaryLabel = computed(() => currentProjectName.value || '未选择')
const datasetSummaryLabel = computed(() => {
  if (!selectedDatasetId.value) return '项目默认上下文'
  return datasetOptions.value.find((item) => item.id === selectedDatasetId.value)?.label || selectedDatasetId.value
})
const cleanArchiveSummaryLabel = computed(() => statusDateLabel.value)
const showPreprocessCta = computed(() => Boolean(currentProjectName.value && !cleanArchivesState.loading && !cleanArchiveOptions.value.length))
const recommendedActionLabel = computed(() => {
  if (!currentProjectName.value) return '先选择项目'
  if (!selectedCleanDate.value && !cleanArchivesState.latest) return '先完成预处理并生成可用范围'
  if (!parsedNoiseTerms.value.length) return '建议先保存排除词，再做预清洗'
  if (!statusState.summary.total_rows) return '先做预清洗'
  if ((statusState.source || statusState.summary.source || '') === 'keyword-preclean') return '如需进一步细筛，可运行 AI 筛选'
  if ((statusState.source || statusState.summary.source || '') === 'ai-filter') return '结果已生成，可查看记录或执行后清洗'
  return '先做预清洗'
})
const scopeHelperText = computed(() => {
  if (!currentProjectName.value) return '先选择项目，再读取对应的处理范围。'
  if (cleanArchivesState.error) return cleanArchivesState.error
  if (!cleanArchiveOptions.value.length) return '当前还没有可用的处理范围，请先完成预处理。'
  return `当前默认使用 ${statusDateLabel.value} 作为筛选输入。`
})
const showResultEmptyState = computed(() => {
  if (!currentProjectName.value) return true
  if (!selectedCleanDate.value && !cleanArchivesState.latest) return true
  if (!statusState.summary.total_rows && !statusState.recentRecords.length && !statusState.message) return true
  return false
})
const resultEmptyTitle = computed(() => {
  if (!currentProjectName.value) return '先选择项目'
  if (!selectedCleanDate.value && !cleanArchivesState.latest) return '先生成可用范围'
  if (!parsedNoiseTerms.value.length) return '还没有可用的筛选结果'
  return '当前还没有筛选结果'
})
const resultEmptyDescription = computed(() => {
  if (!currentProjectName.value) return '选定项目后，页面会自动读取数据集、排除词和可用的处理范围。'
  if (!selectedCleanDate.value && !cleanArchivesState.latest) return '先完成预处理，准备好可用范围后，再回来执行预清洗或 AI 筛选。'
  if (!parsedNoiseTerms.value.length) return '建议先保存排除词，再执行预清洗。完成后，这里会汇总结果来源、记录和样本。'
  return '建议先做预清洗；如果需要更细的判断，再运行 AI 筛选。'
})
const aiConfigLabel = computed(() => {
  const provider = String(statusState.aiConfig.provider || 'qwen').toUpperCase()
  const model = String(statusState.aiConfig.model || '默认模型')
  const qps = statusState.aiConfig.qps ?? '—'
  const batch = statusState.aiConfig.batch_size ?? '—'
  return `${provider} · ${model} · QPS ${qps} · Batch ${batch}`
})
const aiTemplatePreview = computed(() => buildFilterTemplatePreview(aiTemplateState.theme, parsedCategories.value))
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
const previewNoiseTerms = computed(() => parsedNoiseTerms.value.slice(0, 12))
const tabOptions = [
  { value: 'preclean', label: '预清洗' },
  { value: 'ai', label: 'AI 筛选' },
  { value: 'postclean', label: '后清洗' }
]

onMounted(async () => {
  await loadProjects()
  await loadDatabaseOptions()
  if (currentProjectName.value) {
    await refreshProjectContext()
  }
})

onBeforeUnmount(() => {
  stopStatusPolling()
  stopPostcleanPolling()
  stopStopwordSuggestionPolling()
  clearSharedPromptAutosave()
})

watch(
  () => currentProjectName.value,
  async (value, previous) => {
    if (value === previous) return
    stopStatusPolling()
    clearSharedPromptAutosave()
    sharedPromptLastSavedText = ''
    sharedPromptAutosaveSuspend = false
    clearLocalMessages()
    datasets.value = []
    selectedDatasetId.value = ''
    cleanArchivesState.items = []
    cleanArchivesState.latest = ''
    selectedCleanDate.value = ''
    stopwordSuggestionDateByStage.pre = ''
    stopwordSuggestionDateByStage.post = ''
    stopwordSuggestionState.task = null
    stopwordSuggestionState.worker = {}
    stopwordSuggestionArchivesState.archives = { fetch: [], clean: [], filter: [] }
    stopwordSuggestionArchivesState.error = ''
    stopwordModalOpen.value = false
    stopStopwordSuggestionPolling()
    resetStatusState()
    resetPostcleanState()
    if (!value) return
    await refreshProjectContext()
  }
)

watch(
  () => selectedDatasetId.value,
  async (value, previous) => {
    if (value === previous) return
    clearSharedPromptAutosave()
    clearLocalMessages()
    cleanArchivesState.items = []
    cleanArchivesState.latest = ''
    selectedCleanDate.value = ''
    stopwordSuggestionDateByStage.pre = ''
    stopwordSuggestionDateByStage.post = ''
    stopwordSuggestionState.task = null
    stopwordSuggestionState.worker = {}
    stopwordSuggestionArchivesState.archives = { fetch: [], clean: [], filter: [] }
    stopwordSuggestionArchivesState.error = ''
    stopStopwordSuggestionPolling()
    resetStatusState()
    if (!currentProjectName.value) return
    await Promise.all([loadSharedPromptConfig(), loadCleanArchives(), loadStatus()])
  }
)

watch(
  () => selectedCleanDate.value,
  async (value, previous) => {
    if (value === previous) return
    if (!currentProjectName.value || !value) return
    await loadStatus()
  }
)

watch(
  () => sharedPromptState.projectStopwordsText,
  (value, previous) => {
    if (value === previous) return
    sharedPromptState.error = ''
    sharedPromptState.success = ''
    scheduleSharedPromptAutosave()
  }
)

watch(
  () => postcleanState.database,
  async (value, previous) => {
    if (value === previous) return
    resetPostcleanState()
    if (!currentProjectName.value || !value) return
    await loadPostcleanStatus({ silent: true })
  }
)

watch(stopwordModalOpen, async (open) => {
  if (!open) {
    stopStopwordSuggestionPolling()
    manualNoiseTerm.value = ''
    return
  }
  await Promise.all([loadSharedPromptConfig(), loadStopwordSuggestionArchives()])
  seedStopwordSuggestionDate()
  await loadStopwordSuggestionStatus({ syncTopK: true })
  if (stopwordSuggestionRunning.value) {
    startStopwordSuggestionPolling()
  }
})

async function refreshProjectContext() {
  await Promise.all([loadDatasets(), loadAiTemplateConfig(), loadSharedPromptConfig(), loadCleanArchives()])
  await loadStatus()
}

function goToPreprocess() {
  router.push({ name: 'topic-create-preprocess' })
}

function openStopwordModal(stage = 'pre') {
  stopwordSuggestionStage.value = stage === 'post' ? 'post' : 'pre'
  stopwordModalOpen.value = true
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
    stopwordSuggestionDateByStage.pre = selectedCleanDate.value || cleanArchivesState.latest || stopwordSuggestionArchiveOptions.value[0]?.value || ''
  }
  if (!stopwordSuggestionDateByStage.post) {
    stopwordSuggestionDateByStage.post = stopwordSuggestionArchiveOptions.value[0]?.value || selectedCleanDate.value || cleanArchivesState.latest || ''
  }
}

async function loadDatasets() {
  if (!currentProjectName.value) return
  datasetsLoading.value = true
  datasetsError.value = ''
  try {
    const response = await callApi(`/api/projects/${encodeURIComponent(currentProjectName.value)}/datasets`)
    const items = Array.isArray(response.datasets) ? response.datasets : []
    datasets.value = items
    const currentIds = new Set(items.map((item) => item.id))
    if (selectedDatasetId.value && !currentIds.has(selectedDatasetId.value)) {
      selectedDatasetId.value = ''
    }
  } catch (error) {
    datasets.value = []
    datasetsError.value = error instanceof Error ? error.message : '加载数据集失败'
  } finally {
    datasetsLoading.value = false
  }
}

async function loadCleanArchives({ force = false } = {}) {
  if (!currentProjectName.value) return
  if (cleanArchivesState.loading && !force) return
  cleanArchivesState.loading = true
  cleanArchivesState.error = ''
  try {
    const params = new URLSearchParams()
    params.set('layers', 'clean')
    if (selectedDatasetId.value) {
      params.set('dataset_id', selectedDatasetId.value)
    }
    const response = await callApi(`/api/projects/${encodeURIComponent(currentProjectName.value)}/archives?${params.toString()}`)
    const archives = response.archives || {}
    const items = Array.isArray(archives.clean) ? archives.clean : []
    cleanArchivesState.items = items
    cleanArchivesState.latest = response.latest?.clean || items[0]?.date || ''
    if (selectedCleanDate.value) {
      const exists = items.some((item) => item.date === selectedCleanDate.value)
      if (!exists) {
        selectedCleanDate.value = cleanArchivesState.latest || ''
      }
    } else {
      selectedCleanDate.value = cleanArchivesState.latest || ''
    }
  } catch (error) {
    cleanArchivesState.items = []
    cleanArchivesState.latest = ''
    cleanArchivesState.error = error instanceof Error ? error.message : '读取 Clean 存档失败'
  } finally {
    cleanArchivesState.loading = false
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

async function loadSharedPromptConfig() {
  if (!currentProjectName.value) return
  sharedPromptState.loading = true
  sharedPromptState.error = ''
  sharedPromptState.success = ''
  try {
    const params = new URLSearchParams()
    params.set('project', currentProjectName.value)
    if (selectedDatasetId.value) {
      params.set('dataset_id', selectedDatasetId.value)
    }
    const response = await callApi(`/api/topic/bertopic/prompt?${params.toString()}`)
    const payload = response.data || {}
    const nextText = normaliseTextBlock(
      payload.project_stopwords ?? payload.projectStopwords ?? payload.project_stopwords_text ?? ''
    )
    sharedPromptAutosaveSuspend = true
    sharedPromptState.rawPayload = payload
    sharedPromptState.path = payload.path || ''
    sharedPromptState.projectStopwordsText = nextText
    sharedPromptLastSavedText = nextText
  } catch (error) {
    sharedPromptState.rawPayload = null
    sharedPromptState.path = ''
    sharedPromptState.error = error instanceof Error ? error.message : '读取共享词表失败'
  } finally {
    sharedPromptState.loading = false
    sharedPromptAutosaveSuspend = false
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

function appendNoiseTerm(term) {
  const nextTerms = splitDelimitedText(`${sharedPromptState.projectStopwordsText}\n${term}`)
  sharedPromptState.projectStopwordsText = nextTerms.join('\n')
}

function isNoiseTermSelected(term) {
  return parsedNoiseTermSet.value.has(String(term || '').trim())
}

function removeNoiseTerm(term) {
  sharedPromptState.projectStopwordsText = parsedNoiseTerms.value.filter((item) => item !== term).join('\n')
}

function appendManualNoiseTerm() {
  const value = String(manualNoiseTerm.value || '').trim()
  if (!value) return
  appendNoiseTerm(value)
  manualNoiseTerm.value = ''
}

async function saveSharedPromptConfig() {
  if (!currentProjectName.value) return
  clearSharedPromptAutosave()
  sharedPromptState.saving = true
  sharedPromptState.error = ''
  sharedPromptState.success = ''
  try {
    const baseline = sharedPromptState.rawPayload && typeof sharedPromptState.rawPayload === 'object'
      ? sharedPromptState.rawPayload
      : {}
    const payload = {
      topic: baseline.topic_identifier || currentProjectName.value,
      project: currentProjectName.value,
      dataset_id: selectedDatasetId.value || undefined,
      target_topics: baseline.target_topics ?? baseline.max_topics ?? baseline.maxTopics ?? 8,
      drop_rule_prompt: baseline.drop_rule_prompt ?? '',
      recluster_system_prompt: baseline.recluster_system_prompt ?? '',
      recluster_user_prompt: baseline.recluster_user_prompt ?? '',
      keyword_system_prompt: baseline.keyword_system_prompt ?? '',
      keyword_user_prompt: baseline.keyword_user_prompt ?? '',
      global_filters: baseline.global_filters ?? baseline.globalFilters ?? [],
      project_filters: baseline.project_filters ?? baseline.projectFilters ?? [],
      recluster_dimension: baseline.recluster_dimension ?? '',
      must_separate_rules: baseline.must_separate_rules ?? baseline.mustSeparateRules ?? [],
      custom_topic_seed_rules: baseline.custom_topic_seed_rules ?? baseline.customTopicSeedRules ?? [],
      must_merge_rules: baseline.must_merge_rules ?? baseline.mustMergeRules ?? [],
      core_drop_rules: baseline.core_drop_rules ?? baseline.coreDropRules ?? [],
      pre_filter_enabled: baseline.pre_filter_enabled ?? baseline.preFilterEnabled ?? true,
      pre_filter_similarity_floor: baseline.pre_filter_similarity_floor ?? baseline.preFilterSimilarityFloor ?? 0.24,
      pre_filter_max_drop_ratio: baseline.pre_filter_max_drop_ratio ?? baseline.preFilterMaxDropRatio ?? 0.35,
      pre_filter_query_hint: baseline.pre_filter_query_hint ?? '',
      pre_filter_negative_hint: baseline.pre_filter_negative_hint ?? '',
      recluster_topic_limit: baseline.recluster_topic_limit ?? baseline.reclusterTopicLimit ?? 140,
      recluster_target_coverage_ratio:
        baseline.recluster_target_coverage_ratio ?? baseline.reclusterTargetCoverageRatio ?? 0.55,
      project_stopwords: sharedPromptState.projectStopwordsText
    }
    const response = await callApi('/api/topic/bertopic/prompt', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
    const refreshed = response.data || {}
    sharedPromptState.rawPayload = refreshed
    sharedPromptState.path = refreshed.path || sharedPromptState.path
    sharedPromptState.projectStopwordsText = normaliseTextBlock(
      refreshed.project_stopwords ?? payload.project_stopwords
    )
    sharedPromptLastSavedText = sharedPromptState.projectStopwordsText
    sharedPromptState.success = '已自动保存。'
  } catch (error) {
    sharedPromptState.error = error instanceof Error ? error.message : '保存共享词表失败'
  } finally {
    sharedPromptState.saving = false
  }
}

function clearSharedPromptAutosave() {
  if (sharedPromptAutosaveTimer) {
    clearTimeout(sharedPromptAutosaveTimer)
    sharedPromptAutosaveTimer = null
  }
}

function scheduleSharedPromptAutosave() {
  if (!currentProjectName.value || sharedPromptAutosaveSuspend) return
  if (sharedPromptState.projectStopwordsText === sharedPromptLastSavedText) return
  clearSharedPromptAutosave()
  sharedPromptAutosaveTimer = setTimeout(() => {
    sharedPromptAutosaveTimer = null
    if (!currentProjectName.value || sharedPromptState.loading || sharedPromptState.saving) return
    if (sharedPromptState.projectStopwordsText === sharedPromptLastSavedText) return
    saveSharedPromptConfig()
  }, SHARED_PROMPT_AUTOSAVE_DELAY)
}

async function loadAiTemplateConfig() {
  if (!currentProjectName.value) return
  aiTemplateState.loading = true
  aiTemplateState.error = ''
  aiTemplateState.success = ''
  try {
    const params = new URLSearchParams()
    params.set('project', currentProjectName.value)
    const response = await callApi(`/api/filter/template?${params.toString()}`)
    const payload = response.data || {}
    aiTemplateState.exists = Boolean(payload.exists)
    aiTemplateState.path = payload.path || ''
    aiTemplateState.theme = payload.topic_theme || ''
    aiTemplateState.categoriesText = normaliseTextBlock((payload.categories || []).join('\n'))
    aiTemplateState.template = payload.template || ''
  } catch (error) {
    aiTemplateState.error = error instanceof Error ? error.message : '读取 AI 模板失败'
  } finally {
    aiTemplateState.loading = false
  }
}

async function saveAiTemplateConfig() {
  if (!currentProjectName.value) return
  aiTemplateState.saving = true
  aiTemplateState.error = ''
  aiTemplateState.success = ''
  try {
    const response = await callApi('/api/filter/template', {
      method: 'POST',
      body: JSON.stringify({
        project: currentProjectName.value,
        topic_theme: aiTemplateState.theme.trim(),
        categories: parsedCategories.value
      })
    })
    const payload = response.data || {}
    aiTemplateState.exists = Boolean(payload.exists)
    aiTemplateState.path = payload.path || ''
    aiTemplateState.theme = payload.topic_theme || aiTemplateState.theme.trim()
    aiTemplateState.categoriesText = normaliseTextBlock((payload.categories || parsedCategories.value).join('\n'))
    aiTemplateState.template = payload.template || ''
    aiTemplateState.success = 'AI 筛选模板已保存。'
  } catch (error) {
    aiTemplateState.error = error instanceof Error ? error.message : '保存 AI 模板失败'
  } finally {
    aiTemplateState.saving = false
  }
}

async function loadDatabaseOptions() {
  if (postcleanState.loadingDatabases) return
  postcleanState.loadingDatabases = true
  try {
    const response = await callApi('/api/query', {
      method: 'POST',
      body: JSON.stringify({ include_counts: false })
    })
    const payload = response.data || {}
    postcleanState.databases = Array.isArray(payload.databases) ? payload.databases : []
    if (!postcleanState.database && postcleanState.databases.length) {
      postcleanState.database = postcleanState.databases[0].name || ''
    }
    if (currentProjectName.value && postcleanState.database) {
      await loadPostcleanStatus({ silent: true })
    }
  } catch (error) {
    postcleanState.message = error instanceof Error ? error.message : '读取数据库列表失败'
    postcleanState.success = false
  } finally {
    postcleanState.loadingDatabases = false
  }
}

async function loadStatus() {
  if (!currentProjectName.value || !selectedCleanDate.value) return
  statusLoading.value = true
  try {
    const params = new URLSearchParams()
    params.set('project', currentProjectName.value)
    params.set('date', selectedCleanDate.value)
    if (selectedDatasetId.value) {
      params.set('dataset_id', selectedDatasetId.value)
    }
    const response = await callApi(`/api/filter/status?${params.toString()}`)
    const payload = response.data || {}
    statusState.running = Boolean(payload.running)
    statusState.message = payload.message || ''
    statusState.source = payload.source || payload.summary?.source || ''
    statusState.aiConfig = payload.ai_config || {}
    statusState.progress = {
      total: payload.progress?.total || 0,
      completed: payload.progress?.completed || 0,
      failed: payload.progress?.failed || 0,
      kept: payload.progress?.kept || 0,
      percentage: payload.progress?.percentage || 0,
      token_usage: payload.progress?.token_usage || 0
    }
    statusState.summary = {
      total_rows: payload.summary?.total_rows || 0,
      kept_rows: payload.summary?.kept_rows || 0,
      discarded_rows: payload.summary?.discarded_rows || 0,
      token_usage: payload.summary?.token_usage || 0,
      updated_at: payload.summary?.updated_at || '',
      source: payload.summary?.source || ''
    }
    statusState.recentRecords = Array.isArray(payload.recent_records) ? payload.recent_records : []
    statusState.relevantSamples = Array.isArray(payload.relevant_samples) ? payload.relevant_samples : []
    statusState.irrelevantSamples = Array.isArray(payload.irrelevant_samples) ? payload.irrelevant_samples : []
    if (statusState.running) {
      startStatusPolling()
    } else {
      stopStatusPolling()
      aiRunState.running = false
    }
  } catch (error) {
    statusState.message = error instanceof Error ? error.message : '读取筛选状态失败'
    stopStatusPolling()
  } finally {
    statusLoading.value = false
  }
}

async function runPreclean() {
  if (!canRunPreclean.value) return
  precleanState.running = true
  precleanState.success = null
  precleanState.message = ''
  try {
    const response = await callApi('/api/filter/preclean', {
      method: 'POST',
      body: JSON.stringify({
        project: currentProjectName.value,
        dataset_id: selectedDatasetId.value || undefined,
        date: selectedCleanDate.value || undefined
      })
    })
    const payload = response.data || {}
    precleanState.lastResult = payload
    precleanState.success = true
    precleanState.message = `预清洗完成，保留 ${payload.kept_rows || 0} / ${payload.total_rows || 0} 条。`
    if (payload.date) {
      selectedCleanDate.value = payload.date
    }
    await loadStatus()
  } catch (error) {
    precleanState.success = false
    precleanState.message = error instanceof Error ? error.message : '执行预清洗失败'
  } finally {
    precleanState.running = false
  }
}

async function runAiFilter() {
  if (!canRunAiFilter.value) return
  aiRunState.running = true
  aiRunState.success = null
  aiRunState.message = ''
  try {
    const response = await callApi('/api/filter', {
      method: 'POST',
      body: JSON.stringify({
        project: currentProjectName.value,
        dataset_id: selectedDatasetId.value || undefined,
        date: selectedCleanDate.value || undefined
      })
    })
    const payload = response.data || {}
    if (payload.date) {
      selectedCleanDate.value = payload.date
    }
    aiRunState.success = true
    aiRunState.message = response.message || 'AI 筛选已开始，结果会自动刷新。'
    await loadStatus()
    startStatusPolling()
  } catch (error) {
    aiRunState.running = false
    aiRunState.success = false
    aiRunState.message = error instanceof Error ? error.message : '启动 AI 筛选失败'
  }
}

async function runPostclean() {
  if (!canRunPostclean.value) return
  const confirmed = window.confirm(
    `将对数据库 ${postcleanState.database} 执行硬删除，且不可撤销。是否继续？`
  )
  if (!confirmed) return

  postcleanState.running = true
  postcleanState.success = null
  postcleanState.message = ''
  postcleanState.activeTables = [...selectedTables.value]
  try {
    const response = await callApi('/api/database/postclean', {
      method: 'POST',
      body: JSON.stringify({
        project: currentProjectName.value,
        dataset_id: selectedDatasetId.value || undefined,
        database: postcleanState.database,
        tables: postcleanState.activeTables.length ? postcleanState.activeTables : undefined
      })
    })
    const payload = response.data || {}
    applyPostcleanPayload(payload)
    postcleanState.success = null
    postcleanState.message = response.status === 'accepted'
      ? (payload.message || '后清洗已开始，处理进度会自动刷新；若删除了记录，系统会自动同步当前项目已有的本地缓存。')
      : (payload.message || '后清洗已开始。')
    startPostcleanPolling()
  } catch (error) {
    postcleanState.success = false
    postcleanState.message = error instanceof Error ? error.message : '执行后清洗失败'
  } finally {
    if (!postcleanState.running) {
      stopPostcleanPolling()
    }
  }
}

async function loadPostcleanStatus({ silent = false } = {}) {
  if (!currentProjectName.value || !postcleanState.database) return null
  const params = new URLSearchParams()
  params.set('project', currentProjectName.value)
  if (selectedDatasetId.value) {
    params.set('dataset_id', selectedDatasetId.value)
  }
  params.set('database', postcleanState.database)
  const queryTables = postcleanState.activeTables.length ? postcleanState.activeTables : selectedTables.value
  queryTables.forEach((table) => params.append('tables', table))
  try {
    const response = await callApi(`/api/database/postclean/status?${params.toString()}`)
    const payload = response.data || {}
    applyPostcleanPayload(payload)
    if (payload.status === 'running') {
      startPostcleanPolling()
    }
    if (payload.status === 'completed' || payload.status === 'error' || payload.status === 'idle') {
      stopPostcleanPolling()
    }
    if (!silent && payload.status === 'error' && payload.message) {
      postcleanState.message = payload.message
      postcleanState.success = false
    }
    return payload
  } catch (error) {
    if (!silent) {
      postcleanState.message = error instanceof Error ? error.message : '读取后清洗状态失败'
      postcleanState.success = false
    }
    return null
  }
}

function applyPostcleanPayload(payload) {
  if (!payload || typeof payload !== 'object') return
  postcleanState.activeTables = Array.isArray(payload.tables)
    ? payload.tables.map((item) => String(item || '').trim()).filter(Boolean)
    : []
  postcleanState.running = payload.status === 'running'
  if (payload.status === 'completed') {
    postcleanState.success = true
  } else if (payload.status === 'error') {
    postcleanState.success = false
  }
  postcleanState.lastHeartbeat = String(payload.last_heartbeat || '')
  postcleanState.logs = Array.isArray(payload.logs) ? payload.logs : []
  postcleanState.progress = {
    total_tables: payload.progress?.total_tables || 0,
    completed_tables: payload.progress?.completed_tables || 0,
    deleted_rows: payload.progress?.deleted_rows || 0,
    current_table: payload.progress?.current_table || '',
    percentage: payload.progress?.percentage || 0
  }
  if (payload.message) {
    postcleanState.message = String(payload.message)
  }
  if (payload.result && typeof payload.result === 'object') {
    postcleanState.lastResult = payload.result
  }
}

function startPostcleanPolling() {
  if (typeof window === 'undefined' || postcleanTimer.value) return
  postcleanTimer.value = window.setInterval(() => {
    loadPostcleanStatus({ silent: true })
  }, POLL_INTERVAL)
}

function stopPostcleanPolling() {
  if (typeof window === 'undefined' || !postcleanTimer.value) return
  window.clearInterval(postcleanTimer.value)
  postcleanTimer.value = null
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

function startStatusPolling() {
  if (typeof window === 'undefined' || statusTimer.value) return
  statusTimer.value = window.setInterval(() => {
    loadStatus()
  }, POLL_INTERVAL)
}

function stopStatusPolling() {
  if (typeof window === 'undefined' || !statusTimer.value) return
  window.clearInterval(statusTimer.value)
  statusTimer.value = null
}

function resetStatusState() {
  statusState.running = false
  statusState.message = ''
  statusState.source = ''
  statusState.aiConfig = {}
  statusState.progress = {
    total: 0,
    completed: 0,
    failed: 0,
    kept: 0,
    percentage: 0,
    token_usage: 0
  }
  statusState.summary = {
    total_rows: 0,
    kept_rows: 0,
    discarded_rows: 0,
    token_usage: 0,
    updated_at: '',
    source: ''
  }
  statusState.recentRecords = []
  statusState.relevantSamples = []
  statusState.irrelevantSamples = []
}

function resetPostcleanState() {
  stopPostcleanPolling()
  postcleanState.activeTables = []
  postcleanState.running = false
  postcleanState.success = null
  postcleanState.message = ''
  postcleanState.lastResult = null
  postcleanState.lastHeartbeat = ''
  postcleanState.logs = []
  postcleanState.progress = {
    total_tables: 0,
    completed_tables: 0,
    deleted_rows: 0,
    current_table: '',
    percentage: 0
  }
}

function clearLocalMessages() {
  sharedPromptState.error = ''
  sharedPromptState.success = ''
  aiTemplateState.error = ''
  aiTemplateState.success = ''
  precleanState.message = ''
  aiRunState.message = ''
}

function splitDelimitedText(value) {
  const parts = String(value || '')
    .split(SPLIT_PATTERN)
    .map((item) => item.trim())
    .filter(Boolean)
  return Array.from(new Set(parts))
}

function normaliseTextBlock(value) {
  return splitDelimitedText(value).join('\n')
}

function buildFilterTemplatePreview(theme, categories) {
  const subject = String(theme || '').trim() || '该专题'
  const cleanedCategories = Array.isArray(categories) ? categories.filter(Boolean) : []
  const lines = [
    `你是一名舆情筛选助手，请判断以下文本是否与“${subject}”专题相关，并输出 JSON 结果：`,
    '规则：',
    `1. 判断文本是否与${subject}相关，相关返回true，否则返回false；`
  ]
  if (cleanedCategories.length) {
    lines.push(`2. 如果文本相关，请从以下分类中选择最贴切的一项：${cleanedCategories.join('、')}。`)
    lines.push('返回格式: {"相关": true或false, "分类": "<分类名称，必须来自上述列表>"}')
  } else {
    lines.push('2. 如果文本相关，请给出合适的分类描述。')
    lines.push('返回格式: {"相关": true或false, "分类": "分类名称"}')
  }
  lines.push('文本：{text}')
  return lines.join('\n')
}

function formatTimestamp(value) {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return String(value)
  return parsed.toLocaleString('zh-CN', { hour12: false })
}

function formatInteger(value) {
  const num = Number(value || 0)
  if (!Number.isFinite(num)) return '0'
  return new Intl.NumberFormat('zh-CN').format(num)
}
</script>

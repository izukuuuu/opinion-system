<template>
  <div class="space-y-6 pb-12">
    <header class="flex flex-wrap items-center justify-between gap-4">
      <div class="space-y-1">
        <h1 class="text-xl font-bold tracking-tight text-primary">筛选数据</h1>
        <p class="text-sm text-secondary">先确认筛选范围，再执行预清洗或 AI 筛选；数据库后清洗放在最后单独处理。</p>
      </div>
      <div class="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">
        <AdjustmentsHorizontalIcon class="h-4 w-4" />
        <span>Filter</span>
      </div>
    </header>

    <section class="sticky top-3 z-10 rounded-3xl border border-brand-100 bg-white/90 px-5 py-4 backdrop-blur">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div class="space-y-2">
          <div class="flex flex-wrap items-center gap-2">
            <span class="rounded-full bg-brand-50 px-2.5 py-1 text-[11px] font-semibold text-brand-700">当前任务</span>
            <span class="rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="filterSourceTone">{{ filterSourceLabel }}</span>
            <span class="text-xs text-secondary">优先动作：{{ recommendedActionLabel }}</span>
          </div>
          <p class="text-sm text-primary">
            项目 <span class="font-semibold">{{ projectSummaryLabel }}</span>
            <span class="text-secondary"> · 数据集 {{ datasetSummaryLabel }} · Clean 存档 {{ cleanArchiveSummaryLabel }}</span>
          </p>
        </div>
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div class="rounded-2xl bg-surface-muted/60 px-3 py-2">
            <p class="text-[11px] text-muted">总条数</p>
            <p class="mt-1 text-sm font-semibold text-primary">{{ statusState.summary.total_rows || 0 }}</p>
          </div>
          <div class="rounded-2xl bg-surface-muted/60 px-3 py-2">
            <p class="text-[11px] text-muted">保留</p>
            <p class="mt-1 text-sm font-semibold text-emerald-700">{{ statusState.summary.kept_rows || 0 }}</p>
          </div>
          <div class="rounded-2xl bg-surface-muted/60 px-3 py-2">
            <p class="text-[11px] text-muted">Token</p>
            <p class="mt-1 text-sm font-semibold text-primary">{{ formatInteger(statusState.summary.token_usage || 0) }}</p>
          </div>
          <div class="rounded-2xl bg-surface-muted/60 px-3 py-2">
            <p class="text-[11px] text-muted">更新时间</p>
            <p class="mt-1 text-sm font-semibold text-primary">{{ formatTimestamp(statusState.summary.updated_at) || '—' }}</p>
          </div>
        </div>
      </div>
    </section>

    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold text-primary">筛选范围与排除词设置</h2>
          <p class="text-sm text-secondary">先确认本次筛选范围，再维护排除词。排除词保存后，可直接用于预清洗和后清洗。</p>
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
            <p class="mt-1 text-sm text-secondary">这里决定本次筛选作用在哪个项目、哪个数据集、哪个 Clean 存档。</p>
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
              <span class="text-xs font-semibold text-muted">Clean 存档</span>
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
              正在同步可用的 Clean 存档…
            </div>
            <select v-else v-model="selectedCleanDate" class="input" :disabled="!cleanArchiveOptions.length">
              <option value="" disabled>{{ cleanArchiveOptions.length ? '请选择 Clean 存档' : '暂无 Clean 存档' }}</option>
              <option v-for="option in cleanArchiveOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
            <p v-if="cleanArchivesState.error" class="text-xs text-danger">{{ cleanArchivesState.error }}</p>
            <p v-else class="text-xs text-secondary">{{ scopeHelperText }}</p>
          </label>
        </div>

        <div class="space-y-3">
          <div class="rounded-3xl border border-soft bg-surface-muted/60 p-5">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 class="text-base font-semibold text-primary">排除词设置</h3>
                <p class="mt-1 text-sm text-secondary">命中即丢弃，可随时保存。高级来源关系保留在次级说明里。</p>
              </div>
              <div class="flex flex-wrap items-center gap-2 text-xs text-muted">
                <button
                  type="button"
                  class="btn-secondary inline-flex items-center gap-2"
                  :disabled="sharedPromptState.loading || !currentProjectName"
                  @click="loadSharedPromptConfig"
                >
                  <ArrowPathIcon class="h-4 w-4" :class="sharedPromptState.loading ? 'animate-spin' : ''" />
                  重新读取
                </button>
              </div>
            </div>

            <label class="mt-4 block space-y-2">
              <span class="text-xs font-semibold text-muted">排除词</span>
              <p class="text-xs text-secondary">支持换行、空格、逗号、中文逗号、分号。</p>
            </label>
            <textarea
              v-model="sharedPromptState.projectStopwordsText"
              rows="10"
              class="input mt-2 min-h-[16rem] resize-y"
              placeholder="例如：油烟机 抽油烟机 厨电 方太 老板电器 ..."
            />

              <div class="mt-4 flex flex-wrap items-center justify-between gap-3">
              <div class="space-y-1">
                <p class="text-xs text-secondary">已解析 {{ parsedNoiseTerms.length }} 个词条。</p>
                <p class="text-xs text-secondary">这里维护的是当前专题共享使用的排除词设置。</p>
              </div>
              <button
                type="button"
                class="btn-primary"
                :disabled="sharedPromptState.saving || !canSaveSharedPrompt"
                @click="saveSharedPromptConfig"
              >
                {{ sharedPromptState.saving ? '保存中…' : '保存排除词' }}
              </button>
            </div>
            <p v-if="sharedPromptState.error" class="mt-3 text-xs text-danger">{{ sharedPromptState.error }}</p>
            <p v-else-if="sharedPromptState.success" class="mt-3 text-xs text-emerald-600">{{ sharedPromptState.success }}</p>

            <div class="mt-4 rounded-2xl border border-soft bg-white p-4">
              <div class="flex items-center justify-between gap-3">
                <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">词条预览</p>
                <span class="text-xs text-secondary">命中即丢弃</span>
              </div>
              <div v-if="parsedNoiseTerms.length" class="mt-3 flex max-h-52 flex-wrap gap-2 overflow-y-auto">
                <span
                  v-for="term in parsedNoiseTerms"
                  :key="`noise-term-${term}`"
                  class="rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700"
                >
                  {{ term }}
                </span>
              </div>
              <p v-else class="mt-3 text-sm text-secondary">当前还没有排除词。建议先保存排除词，再执行预清洗。</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold text-primary">执行筛选</h2>
          <p class="text-sm text-secondary">操作区只负责执行动作，不承载结果详情。结果统一在下方查看。</p>
        </div>
        <div class="inline-flex rounded-full border border-soft bg-surface-muted/70 p-1">
          <button
            v-for="tab in tabOptions"
            :key="tab.value"
            type="button"
            class="rounded-full px-4 py-2 text-xs font-semibold transition"
            :class="activeTab === tab.value ? 'bg-white text-brand-700 shadow-sm' : 'text-secondary hover:text-primary'"
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
            <p class="mt-2 text-sm text-secondary">适合先快速剔除明显噪声，不消耗 token。会直接生成当前 Filter 结果。</p>
          </div>
          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <div class="rounded-2xl border border-soft bg-white px-4 py-3"><p class="text-xs text-muted">适用场景</p><p class="mt-1 text-sm font-semibold text-primary">先排明显噪声</p></div>
            <div class="rounded-2xl border border-soft bg-white px-4 py-3"><p class="text-xs text-muted">执行前提</p><p class="mt-1 text-sm font-semibold text-primary">{{ canRunPreclean ? '已可执行' : '需先选好 Clean 存档' }}</p></div>
            <div class="rounded-2xl border border-soft bg-white px-4 py-3"><p class="text-xs text-muted">排除词</p><p class="mt-1 text-sm font-semibold text-primary">{{ parsedNoiseTerms.length }} 个</p></div>
          </div>
          <div class="flex min-h-[3rem] flex-wrap items-center gap-3">
            <button type="button" class="btn-primary inline-flex items-center gap-2" :disabled="!canRunPreclean || precleanState.running" @click="runPreclean">
              <SparklesIcon class="h-4 w-4" />
              {{ precleanState.running ? '预清洗执行中…' : '先做预清洗' }}
            </button>
            <p v-if="precleanState.message" class="text-xs" :class="precleanState.success === false ? 'text-danger' : 'text-secondary'">
              {{ precleanState.message }}
            </p>
          </div>
        </div>

        <div class="rounded-3xl border border-soft bg-surface-muted/60 p-5">
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">执行提示</p>
          <p class="mt-3 text-sm text-secondary">预清洗会按照当前排除词，直接过滤 `title + contents + hit_words`。完成后去下方“结果与记录”查看输出。</p>
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
            <p class="mt-1 text-sm font-semibold text-primary">{{ canRunAiFilter ? '已可执行' : '需先选好 Clean 存档' }}</p>
            <p class="mt-1 text-xs text-secondary">目标日期 {{ selectedCleanDate || cleanArchivesState.latest || '—' }}</p>
          </div>

          <div class="rounded-2xl border border-soft bg-white px-4 py-3">
            <p class="text-xs text-muted">执行提示</p>
            <p class="mt-1 text-sm font-semibold text-primary">{{ statusState.running ? '任务运行中' : '空闲' }}</p>
            <p class="mt-1 text-xs text-secondary">会直接覆盖当前 Filter 结果来源。</p>
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
            <p class="mt-2 text-sm text-secondary">只在你确认 Filter 结果之后再做。将直接删除数据库记录，无法撤销。</p>
          </div>

          <div class="rounded-3xl border border-rose-200 bg-white px-4 py-3 text-sm text-rose-700">
            <p class="font-semibold">危险操作</p>
            <p class="mt-1 text-xs leading-relaxed">建议先确认数据库名，再核对是否需要限制表名。执行后不会进入回收站。</p>
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
          <p v-if="postcleanState.message" class="text-xs" :class="postcleanState.success === false ? 'text-danger' : 'text-secondary'">
            {{ postcleanState.message }}
          </p>
        </div>

        <div class="rounded-3xl border border-soft bg-surface-muted/60 p-5">
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">审计结果</p>
          <div v-if="postcleanState.lastResult" class="mt-4 space-y-3">
            <div class="rounded-2xl border border-soft bg-white px-4 py-3">
              <p class="text-xs text-muted">审计报告</p>
              <p class="mt-1 text-sm font-semibold text-primary break-all">{{ postcleanState.lastResult.report_path || '—' }}</p>
            </div>
            <div class="rounded-2xl border border-soft bg-white px-4 py-3">
              <p class="text-xs text-muted">总删除数</p>
              <p class="mt-1 text-lg font-semibold text-rose-700">{{ postcleanState.lastResult.deleted_rows || 0 }}</p>
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
          <p v-else class="mt-4 text-sm text-secondary">尚未执行后清洗。</p>
        </div>
      </div>
    </section>

    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold text-primary">结果与记录</h2>
          <p class="text-sm text-secondary">先看结果摘要，再看最近处理记录和样本。执行区不会重复展示这些结果。</p>
        </div>
        <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="statusLoading || !currentProjectName || !selectedCleanDate" @click="loadStatus">
          <ArrowPathIcon class="h-4 w-4" :class="statusLoading ? 'animate-spin' : ''" />
          刷新状态
        </button>
      </div>

      <div class="grid gap-4 md:grid-cols-4">
        <div class="rounded-2xl border border-soft bg-surface-muted/50 px-4 py-4">
          <p class="text-xs text-muted">结果来源</p>
          <p class="mt-1 text-lg font-semibold text-primary">{{ filterSourceLabel }}</p>
        </div>
        <div class="rounded-2xl border border-soft bg-surface-muted/50 px-4 py-4">
          <p class="text-xs text-muted">总条数</p>
          <p class="mt-1 text-lg font-semibold text-primary">{{ statusState.summary.total_rows || 0 }}</p>
        </div>
        <div class="rounded-2xl border border-soft bg-surface-muted/50 px-4 py-4">
          <p class="text-xs text-muted">保留</p>
          <p class="mt-1 text-lg font-semibold text-emerald-700">{{ statusState.summary.kept_rows || 0 }}</p>
        </div>
        <div class="rounded-2xl border border-soft bg-surface-muted/50 px-4 py-4">
          <p class="text-xs text-muted">Token</p>
          <p class="mt-1 text-lg font-semibold text-primary">{{ formatInteger(statusState.summary.token_usage || 0) }}</p>
        </div>
      </div>

      <div v-if="showResultEmptyState" class="rounded-3xl border border-dashed border-soft px-5 py-8 text-center">
        <p class="text-base font-semibold text-primary">{{ resultEmptyTitle }}</p>
        <p class="mt-2 text-sm text-secondary">{{ resultEmptyDescription }}</p>
      </div>

      <p v-else-if="statusState.message" class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
        {{ statusState.message }}
      </p>

      <div v-if="!showResultEmptyState" class="grid gap-5 xl:grid-cols-[1.25fr,1fr]">
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold text-primary">最近处理记录</h3>
            <span class="text-xs text-muted">{{ statusState.recentRecords.length }} 条</span>
          </div>
          <div v-if="statusState.recentRecords.length" class="space-y-3">
            <article
              v-for="(record, index) in statusState.recentRecords"
              :key="`filter-recent-${record.channel}-${record.index}-${index}`"
              class="rounded-2xl border border-soft bg-surface-muted/50 px-4 py-4"
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
              <p class="mt-3 text-sm font-semibold text-primary">{{ record.title || '无标题记录' }}</p>
              <p class="mt-1 text-sm text-secondary">{{ record.preview || '—' }}</p>
              <p v-if="record.matched_terms?.length" class="mt-2 text-xs text-rose-700">
                命中词: {{ record.matched_terms.join('、') }}
              </p>
            </article>
          </div>
          <div v-else class="rounded-2xl border border-dashed border-soft px-4 py-8 text-sm text-secondary">
            当前还没有筛选记录。
          </div>
        </div>

        <div class="space-y-4">
          <div class="rounded-3xl border border-soft bg-surface-muted/50 p-4">
            <p class="text-sm font-semibold text-primary">保留样本</p>
            <div v-if="statusState.relevantSamples.length" class="mt-3 space-y-2">
              <article v-for="(item, index) in statusState.relevantSamples" :key="`relevant-${item.channel}-${index}`" class="rounded-2xl border border-soft bg-white px-4 py-3">
                <p class="text-sm font-semibold text-primary">{{ item.title || '无标题记录' }}</p>
                <p class="mt-1 text-xs text-secondary">{{ item.preview || '—' }}</p>
              </article>
            </div>
            <p v-else class="mt-3 text-sm text-secondary">暂无保留样本。</p>
          </div>

          <div class="rounded-3xl border border-soft bg-surface-muted/50 p-4">
            <p class="text-sm font-semibold text-primary">丢弃样本</p>
            <div v-if="statusState.irrelevantSamples.length" class="mt-3 space-y-2">
              <article v-for="(item, index) in statusState.irrelevantSamples" :key="`irrelevant-${item.channel}-${index}`" class="rounded-2xl border border-soft bg-white px-4 py-3">
                <p class="text-sm font-semibold text-primary">{{ item.title || '无标题记录' }}</p>
                <p class="mt-1 text-xs text-secondary">{{ item.preview || '—' }}</p>
              </article>
            </div>
            <p v-else class="mt-3 text-sm text-secondary">暂无丢弃样本。</p>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  AdjustmentsHorizontalIcon,
  ArrowPathIcon,
  SparklesIcon,
  TrashIcon
} from '@heroicons/vue/24/outline'
import { useApiBase } from '../../composables/useApiBase'
import { useTopicCreationProject } from '../../composables/useTopicCreationProject'

const { callApi } = useApiBase()
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

const sharedPromptState = reactive({
  loading: false,
  saving: false,
  error: '',
  success: '',
  path: '',
  rawPayload: null,
  projectStopwordsText: ''
})

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
  running: false,
  success: null,
  message: '',
  lastResult: null
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
const parsedCategories = computed(() => splitDelimitedText(aiTemplateState.categoriesText))
const selectedTables = computed(() => splitDelimitedText(postcleanState.tablesText))
const canSaveSharedPrompt = computed(() => Boolean(currentProjectName.value))
const canSaveAiTemplate = computed(() => Boolean(currentProjectName.value && aiTemplateState.theme.trim() && parsedCategories.value.length))
const canRunPreclean = computed(() => Boolean(currentProjectName.value && (selectedCleanDate.value || cleanArchivesState.latest)))
const canRunAiFilter = computed(() => Boolean(currentProjectName.value && (selectedCleanDate.value || cleanArchivesState.latest)))
const canRunPostclean = computed(() => Boolean(currentProjectName.value && postcleanState.database))
const filterSourceLabel = computed(() => {
  const source = statusState.source || statusState.summary.source || ''
  if (source === 'keyword-preclean') return '预清洗结果'
  if (source === 'ai-filter') return 'AI 筛选结果'
  return '尚未生成 Filter 结果'
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
const recommendedActionLabel = computed(() => {
  if (!currentProjectName.value) return '先选择项目'
  if (!selectedCleanDate.value && !cleanArchivesState.latest) return '先完成预处理并生成 Clean 存档'
  if (!parsedNoiseTerms.value.length) return '建议先保存排除词，再做预清洗'
  if (!statusState.summary.total_rows) return '先做预清洗'
  if ((statusState.source || statusState.summary.source || '') === 'keyword-preclean') return '如需进一步细筛，可运行 AI 筛选'
  if ((statusState.source || statusState.summary.source || '') === 'ai-filter') return '结果已生成，可查看记录或执行后清洗'
  return '先做预清洗'
})
const scopeHelperText = computed(() => {
  if (!currentProjectName.value) return '先选择项目，再读取对应的 Clean 存档。'
  if (cleanArchivesState.error) return cleanArchivesState.error
  if (!cleanArchiveOptions.value.length) return '当前还没有可用的 Clean 存档，请先完成预处理。'
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
  if (!selectedCleanDate.value && !cleanArchivesState.latest) return '先生成 Clean 存档'
  if (!parsedNoiseTerms.value.length) return '还没有可用的筛选结果'
  return '当前还没有 Filter 结果'
})
const resultEmptyDescription = computed(() => {
  if (!currentProjectName.value) return '选定项目后，页面会自动读取数据集、排除词和可用的 Clean 存档。'
  if (!selectedCleanDate.value && !cleanArchivesState.latest) return '先完成预处理，生成 Clean 存档后，再回来执行预清洗或 AI 筛选。'
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
})

watch(
  () => currentProjectName.value,
  async (value, previous) => {
    if (value === previous) return
    stopStatusPolling()
    clearLocalMessages()
    datasets.value = []
    selectedDatasetId.value = ''
    cleanArchivesState.items = []
    cleanArchivesState.latest = ''
    selectedCleanDate.value = ''
    resetStatusState()
    if (!value) return
    await refreshProjectContext()
  }
)

watch(
  () => selectedDatasetId.value,
  async (value, previous) => {
    if (value === previous) return
    clearLocalMessages()
    cleanArchivesState.items = []
    cleanArchivesState.latest = ''
    selectedCleanDate.value = ''
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

async function refreshProjectContext() {
  await Promise.all([loadDatasets(), loadAiTemplateConfig(), loadSharedPromptConfig(), loadCleanArchives()])
  await loadStatus()
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
    sharedPromptState.rawPayload = payload
    sharedPromptState.path = payload.path || ''
    sharedPromptState.projectStopwordsText = normaliseTextBlock(
      payload.project_stopwords ?? payload.projectStopwords ?? payload.project_stopwords_text ?? ''
    )
  } catch (error) {
    sharedPromptState.rawPayload = null
    sharedPromptState.path = ''
    sharedPromptState.error = error instanceof Error ? error.message : '读取共享词表失败'
  } finally {
    sharedPromptState.loading = false
  }
}

async function saveSharedPromptConfig() {
  if (!currentProjectName.value) return
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
    sharedPromptState.success = '共享黑名单词表已保存。'
  } catch (error) {
    sharedPromptState.error = error instanceof Error ? error.message : '保存共享词表失败'
  } finally {
    sharedPromptState.saving = false
  }
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
    aiRunState.message = response.message || 'AI 筛选任务已提交。'
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
  try {
    const response = await callApi('/api/database/postclean', {
      method: 'POST',
      body: JSON.stringify({
        project: currentProjectName.value,
        dataset_id: selectedDatasetId.value || undefined,
        database: postcleanState.database,
        tables: selectedTables.value.length ? selectedTables.value : undefined
      })
    })
    const payload = response.data || {}
    postcleanState.lastResult = payload
    postcleanState.success = true
    postcleanState.message = `后清洗完成，共删除 ${payload.deleted_rows || 0} 条记录。`
  } catch (error) {
    postcleanState.success = false
    postcleanState.message = error instanceof Error ? error.message : '执行后清洗失败'
  } finally {
    postcleanState.running = false
  }
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

<template>
  <div class="space-y-6">
    <section class="overflow-hidden rounded-[2rem] border border-slate-300 bg-white shadow-[0_24px_80px_-36px_rgba(15,23,42,0.45)]">
      <div class="border-b border-slate-800 bg-[linear-gradient(135deg,#0f172a_0%,#172554_45%,#0f766e_100%)] px-6 py-6 text-white">
        <div class="flex flex-col gap-6 2xl:flex-row 2xl:items-start 2xl:justify-between">
          <div class="space-y-4">
            <div class="inline-flex items-center gap-3 rounded-full border border-white/15 bg-white/10 px-4 py-2">
              <QueueListIcon class="h-4 w-4 text-sky-300" />
              <span class="font-mono text-[11px] uppercase tracking-[0.35em] text-sky-100">NetInsight Queue</span>
            </div>
            <div>
              <h2 class="text-3xl font-semibold tracking-tight text-white">平台数据获取</h2>
              <p class="mt-2 max-w-3xl text-sm leading-6 text-slate-200/90">
                按 aria2 式队列盯住采集任务。新建、排队、执行、失败、重试和下载都在一个面板里完成，
                刷新页面后进度也会继续保留。
              </p>
            </div>
            <div class="flex flex-wrap gap-2 font-mono text-[12px] text-slate-200/85">
              <span class="rounded-full border border-white/10 bg-white/10 px-3 py-1.5">
                PROJECT {{ activeProjectName || 'UNBOUND' }}
              </span>
              <span class="rounded-full border border-white/10 bg-white/10 px-3 py-1.5">
                DAEMON {{ workerStatusLabel }}
              </span>
              <span class="rounded-full border border-white/10 bg-white/10 px-3 py-1.5">
                AUTO {{ autoRefresh ? 'ON' : 'OFF' }}
              </span>
            </div>
          </div>

          <div class="grid gap-3 sm:grid-cols-2 xl:min-w-[420px]">
            <button
              type="button"
              class="inline-flex items-center justify-center gap-2 rounded-2xl border border-sky-300/30 bg-sky-400/20 px-4 py-3 text-sm font-semibold text-white transition hover:bg-sky-400/30"
              @click="openCreateModal"
            >
              <PlusIcon class="h-4 w-4" />
              <span>新建任务</span>
            </button>
            <button
              type="button"
              class="inline-flex items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm font-medium text-slate-100 transition hover:bg-white/15"
              :disabled="loading"
              @click="fetchTasks"
            >
              <ArrowPathIcon class="h-4 w-4" :class="loading ? 'animate-spin' : ''" />
              <span>{{ loading ? '刷新中…' : '刷新队列' }}</span>
            </button>
            <button
              type="button"
              class="inline-flex items-center justify-center gap-2 rounded-2xl border px-4 py-3 text-sm font-medium transition"
              :class="autoRefresh ? 'border-emerald-300/30 bg-emerald-400/20 text-emerald-50 hover:bg-emerald-400/30' : 'border-white/10 bg-white/10 text-slate-100 hover:bg-white/15'"
              @click="autoRefresh = !autoRefresh"
            >
              <PauseCircleIcon v-if="autoRefresh" class="h-4 w-4" />
              <PlayCircleIcon v-else class="h-4 w-4" />
              <span>{{ autoRefresh ? '关闭自动刷新' : '开启自动刷新' }}</span>
            </button>
            <button
              type="button"
              class="inline-flex items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm font-medium text-slate-100 transition hover:bg-white/15"
              @click="goSettings"
            >
              <Cog6ToothIcon class="h-4 w-4" />
              <span>NetInsight 设置</span>
            </button>
          </div>
        </div>

        <div class="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <article class="rounded-3xl border border-white/10 bg-white/10 px-4 py-4 backdrop-blur">
            <p class="font-mono text-[11px] uppercase tracking-[0.32em] text-slate-300">ALL TASKS</p>
            <p class="mt-3 text-3xl font-semibold text-white">{{ taskSummary.total ?? 0 }}</p>
            <p class="mt-2 text-xs text-slate-300">所有本地持久化队列任务</p>
          </article>
          <article class="rounded-3xl border border-white/10 bg-white/10 px-4 py-4 backdrop-blur">
            <p class="font-mono text-[11px] uppercase tracking-[0.32em] text-slate-300">WAITING</p>
            <p class="mt-3 text-3xl font-semibold text-white">{{ taskSummary.queued ?? 0 }}</p>
            <p class="mt-2 text-xs text-slate-300">等待后台开始处理</p>
          </article>
          <article class="rounded-3xl border border-white/10 bg-white/10 px-4 py-4 backdrop-blur">
            <p class="font-mono text-[11px] uppercase tracking-[0.32em] text-slate-300">ACTIVE</p>
            <p class="mt-3 text-3xl font-semibold text-white">{{ taskSummary.running ?? 0 }}</p>
            <p class="mt-2 text-xs text-slate-300">正在登录、计数或抓取</p>
          </article>
          <article class="rounded-3xl border border-white/10 bg-white/10 px-4 py-4 backdrop-blur">
            <p class="font-mono text-[11px] uppercase tracking-[0.32em] text-slate-300">READY</p>
            <p class="mt-3 text-3xl font-semibold text-white">{{ taskSummary.completed ?? 0 }}</p>
            <p class="mt-2 text-xs text-slate-300">已可直接下载结果文件</p>
          </article>
        </div>
      </div>

      <div
        v-if="!settingsState.credentials.configured"
        class="border-t border-amber-200 bg-amber-50 px-6 py-4 text-sm text-amber-900"
      >
        还没有配置 NetInsight 账号密码。请先在“系统设置 → NetInsight 配置”中保存账号信息，否则任务无法开始。
      </div>
      <div
        v-else-if="feedback.message"
        class="border-t px-6 py-4 text-sm"
        :class="feedback.type === 'error' ? 'border-rose-200 bg-rose-50 text-rose-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'"
      >
        {{ feedback.message }}
      </div>
    </section>

    <section class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
      <section class="overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-[0_18px_60px_-36px_rgba(15,23,42,0.28)]">
        <div class="flex flex-col gap-4 border-b border-slate-200 bg-slate-50/80 px-6 py-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p class="font-mono text-[11px] uppercase tracking-[0.32em] text-slate-400">Transfer List</p>
            <h3 class="mt-2 text-xl font-semibold text-slate-900">任务队列</h3>
            <p class="mt-1 text-sm text-slate-500">按创建时间倒序展示，运行中的任务会自动刷新。</p>
          </div>
          <label class="inline-flex items-center gap-3 rounded-full border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-600 shadow-sm">
            <input v-model="onlyCurrentProject" type="checkbox" class="rounded border-slate-300 text-sky-600 focus:ring-sky-500" />
            仅看当前项目
          </label>
        </div>

        <div v-if="loading && !tasks.length" class="px-6 py-16 text-center text-sm text-slate-500">
          正在加载队列状态…
        </div>
        <div v-else-if="error" class="px-6 py-8 text-sm text-rose-700">
          {{ error }}
        </div>
        <div v-else-if="!filteredTasks.length" class="px-6 py-16 text-center text-sm text-slate-500">
          还没有可展示的 NetInsight 任务，先新建一个试试。
        </div>

        <div v-else class="divide-y divide-slate-200">
          <article
            v-for="task in filteredTasks"
            :key="task.id"
            class="px-6 py-5 transition hover:bg-slate-50/80"
          >
            <div class="flex flex-col gap-5 xl:grid xl:grid-cols-[minmax(0,1.45fr)_minmax(280px,0.95fr)_auto] xl:items-start">
              <div class="min-w-0 space-y-4">
                <div class="flex flex-wrap items-center gap-3">
                  <span class="h-2.5 w-2.5 rounded-full" :class="statusDotClass(task.status)" />
                  <h4 class="truncate text-lg font-semibold text-slate-900">{{ task.title || task.id }}</h4>
                  <span class="rounded-full px-3 py-1 text-xs font-semibold" :class="statusClass(task.status)">
                    {{ statusLabel(task.status) }}
                  </span>
                  <span v-if="task.project" class="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                    {{ task.project }}
                  </span>
                </div>

                <p class="text-sm leading-6 text-slate-500">{{ task.summary || task.query || '未填写任务说明' }}</p>

                <div class="flex flex-wrap gap-2">
                  <span
                    v-for="keyword in task.keywords || []"
                    :key="`${task.id}-kw-${keyword}`"
                    class="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700"
                  >
                    {{ keyword }}
                  </span>
                </div>

                <div class="flex flex-wrap gap-2">
                  <span
                    v-for="platform in task.platforms || []"
                    :key="`${task.id}-pf-${platform}`"
                    class="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700"
                  >
                    {{ platform }}
                  </span>
                </div>

                <div class="rounded-3xl border border-slate-200 bg-slate-50/70 px-4 py-4">
                  <div class="flex items-center justify-between gap-4 text-[12px] font-medium text-slate-500">
                    <span class="truncate">{{ task.progress?.message || '等待状态更新' }}</span>
                    <span class="font-mono text-slate-700">{{ Number(task.progress?.percentage || 0).toFixed(0) }}%</span>
                  </div>
                  <div class="mt-3 h-2 overflow-hidden rounded-full bg-slate-200">
                    <div
                      class="h-full rounded-full transition-all duration-300"
                      :class="progressFillClass(task.status)"
                      :style="{ width: `${Math.max(0, Math.min(100, Number(task.progress?.percentage || 0)))}%` }"
                    />
                  </div>
                </div>
              </div>

              <div class="space-y-4">
                <dl class="grid gap-3 rounded-3xl border border-slate-200 bg-white p-4 text-sm text-slate-600 sm:grid-cols-2">
                  <div>
                    <dt class="font-mono text-[11px] uppercase tracking-[0.24em] text-slate-400">Task ID</dt>
                    <dd class="mt-1 break-all font-medium text-slate-900">{{ task.id }}</dd>
                  </div>
                  <div>
                    <dt class="font-mono text-[11px] uppercase tracking-[0.24em] text-slate-400">Updated</dt>
                    <dd class="mt-1 font-medium text-slate-900">{{ formatTimestamp(task.updated_at) }}</dd>
                  </div>
                  <div>
                    <dt class="font-mono text-[11px] uppercase tracking-[0.24em] text-slate-400">Range</dt>
                    <dd class="mt-1 font-medium text-slate-900">{{ task.config?.start_date || '--' }} → {{ task.config?.end_date || '--' }}</dd>
                  </div>
                  <div>
                    <dt class="font-mono text-[11px] uppercase tracking-[0.24em] text-slate-400">Plan</dt>
                    <dd class="mt-1 font-medium text-slate-900">{{ task.progress?.planned_total ?? 0 }}</dd>
                  </div>
                  <div>
                    <dt class="font-mono text-[11px] uppercase tracking-[0.24em] text-slate-400">Fetched</dt>
                    <dd class="mt-1 font-medium text-slate-900">{{ task.progress?.fetched_total ?? 0 }}</dd>
                  </div>
                  <div>
                    <dt class="font-mono text-[11px] uppercase tracking-[0.24em] text-slate-400">Deduped</dt>
                    <dd class="mt-1 font-medium text-slate-900">{{ task.output?.deduplicated_count ?? task.progress?.deduped_total ?? 0 }}</dd>
                  </div>
                </dl>
              </div>

              <div class="flex flex-wrap gap-2 xl:max-w-[180px] xl:justify-end">
                <button
                  v-if="task.status === 'queued' || task.status === 'running'"
                  type="button"
                  class="rounded-full border border-rose-200 px-4 py-2 text-xs font-semibold text-rose-700 transition hover:bg-rose-50"
                  @click="cancelTask(task)"
                >
                  取消
                </button>
                <button
                  v-if="task.status === 'failed' || task.status === 'cancelled' || task.status === 'completed'"
                  type="button"
                  class="rounded-full border border-sky-200 px-4 py-2 text-xs font-semibold text-sky-700 transition hover:bg-sky-50"
                  @click="retryTask(task)"
                >
                  重试
                </button>
                <button
                  v-if="task.status !== 'running'"
                  type="button"
                  class="rounded-full border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-600 transition hover:bg-slate-100"
                  @click="deleteTask(task)"
                >
                  删除
                </button>
              </div>
            </div>

            <div class="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(280px,0.8fr)]">
              <div class="rounded-3xl border border-slate-200 bg-white px-4 py-4">
                <div class="flex items-start justify-between gap-4">
                  <div>
                    <p class="font-mono text-[11px] uppercase tracking-[0.24em] text-slate-400">Output</p>
                    <p class="mt-2 break-all text-sm font-medium text-slate-700">{{ task.output?.dir || '尚未生成' }}</p>
                  </div>
                  <ArrowDownTrayIcon class="mt-0.5 h-5 w-5 flex-none text-slate-300" />
                </div>
                <div v-if="task.status === 'completed'" class="mt-4 flex flex-wrap gap-2">
                  <button
                    v-if="taskHasFile(task, 'records.csv')"
                    type="button"
                    class="rounded-full border border-slate-200 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                    :disabled="downloadingTaskId === task.id"
                    @click="downloadTaskFile(task, 'csv')"
                  >
                    下载 CSV
                  </button>
                  <button
                    v-if="taskHasFile(task, 'records.jsonl')"
                    type="button"
                    class="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                    :disabled="downloadingTaskId === task.id"
                    @click="downloadTaskFile(task, 'jsonl')"
                  >
                    下载 JSONL
                  </button>
                  <button
                    v-if="taskHasFile(task, 'meta.json')"
                    type="button"
                    class="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                    :disabled="downloadingTaskId === task.id"
                    @click="downloadTaskFile(task, 'meta')"
                  >
                    下载 Meta
                  </button>
                </div>
              </div>

              <div class="rounded-3xl border border-slate-800 bg-slate-950 px-4 py-4 text-slate-200">
                <p class="font-mono text-[11px] uppercase tracking-[0.24em] text-slate-500">Recent Log</p>
                <ul v-if="task.events?.length" class="mt-3 space-y-2 font-mono text-[12px] leading-5 text-slate-300">
                  <li v-for="event in task.events.slice(-3).reverse()" :key="`${task.id}-${event.timestamp}-${event.message}`">
                    <span class="text-slate-500">{{ formatTimestamp(event.timestamp) }}</span>
                    <span class="mx-2 text-slate-600">|</span>
                    <span>{{ event.message }}</span>
                  </li>
                </ul>
                <p v-else class="mt-3 text-sm text-slate-500">暂无事件记录。</p>
              </div>
            </div>

            <div v-if="task.error" class="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {{ task.error }}
            </div>
          </article>
        </div>
      </section>

      <aside class="space-y-4">
        <section class="rounded-[1.75rem] border border-slate-200 bg-white px-5 py-5 shadow-sm">
          <p class="font-mono text-[11px] uppercase tracking-[0.3em] text-slate-400">Queue Overview</p>
          <div class="mt-4 space-y-3">
            <article
              v-for="card in summaryCards"
              :key="card.key"
              class="rounded-2xl border border-slate-200 bg-slate-50/70 px-4 py-3"
            >
              <div class="flex items-center justify-between gap-3">
                <p class="text-sm font-semibold text-slate-700">{{ card.label }}</p>
                <p class="font-mono text-lg font-semibold text-slate-900">{{ card.value }}</p>
              </div>
              <p class="mt-1 text-xs leading-5 text-slate-500">{{ card.description }}</p>
            </article>
          </div>
        </section>

        <section class="rounded-[1.75rem] border border-slate-800 bg-slate-950 px-5 py-5 text-slate-200 shadow-sm">
          <p class="font-mono text-[11px] uppercase tracking-[0.3em] text-slate-500">Queue Guide</p>
          <div class="mt-4 space-y-3 text-sm leading-6 text-slate-300">
            <p>1. 先在设置里保存账号，再新建任务。</p>
            <p>2. 任务会先解析说明，再进入排队和执行。</p>
            <p>3. 完成后可直接下载 CSV、JSONL 和 Meta。</p>
          </div>
        </section>
      </aside>
    </section>

    <AppModal
      v-model="createModalOpen"
      title="新建 NetInsight 采集任务"
      eyebrow="Task Builder"
      width="max-w-5xl"
      confirm-text="提交到队列"
      confirm-loading-text="提交中…"
      :confirm-loading="submitting"
      :confirm-disabled="submitting || !canSubmit"
      @confirm="submitTask"
    >
      <template #description>
        <p class="text-sm text-slate-500">
          先写任务说明并解析，再按需修正关键词、平台和时间范围。提交后任务会进入后台队列执行。
        </p>
      </template>

      <div class="space-y-6">
        <div class="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
          <label class="space-y-2 text-sm">
            <span class="font-medium text-slate-700">任务标题</span>
            <input
              v-model.trim="taskForm.title"
              type="text"
              placeholder="例如：小米 SU7 舆情追踪"
              class="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            />
          </label>
          <label class="space-y-2 text-sm">
            <span class="font-medium text-slate-700">关联项目</span>
            <select
              v-model="taskForm.project"
              class="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            >
              <option value="">不关联项目</option>
              <option v-for="project in projects" :key="project.name" :value="project.name">
                {{ project.name }}
              </option>
            </select>
          </label>
        </div>

        <div class="space-y-3">
          <div class="flex items-center justify-between gap-3">
            <label class="text-sm font-medium text-slate-700">任务说明</label>
            <button
              type="button"
              class="rounded-full border border-indigo-200 px-4 py-2 text-xs font-semibold text-indigo-700 transition hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="planning || !taskForm.brief.trim()"
              @click="planTask"
            >
              {{ planning ? '解析中…' : '解析关键词与配置' }}
            </button>
          </div>
          <textarea
            v-model.trim="taskForm.brief"
            rows="4"
            placeholder="例如：监测最近一个月小米 SU7 在微博和新闻网站的舆情，重点关注刹车、事故、交付、退订。"
            class="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
          />
          <p class="text-xs text-slate-500">
            可直接描述关注对象、时间范围、平台与重点词。解析结果只是建议，你可以继续手动修改。
          </p>
        </div>

        <div class="grid gap-4 lg:grid-cols-2">
          <label class="space-y-2 text-sm">
            <span class="font-medium text-slate-700">关键词</span>
            <textarea
              v-model.trim="taskForm.keywordsText"
              rows="5"
              placeholder="每行一个，或用逗号分隔"
              class="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            />
          </label>
          <div class="space-y-4 rounded-3xl border border-slate-200 bg-slate-50/80 p-4">
            <div>
              <p class="text-sm font-medium text-slate-700">平台</p>
              <div class="mt-3 grid gap-2 sm:grid-cols-2">
                <label
                  v-for="option in platformOptions"
                  :key="option"
                  class="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600"
                >
                  <input v-model="taskForm.platforms" type="checkbox" :value="option" class="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
                  <span>{{ option }}</span>
                </label>
              </div>
            </div>
            <div class="grid gap-4 sm:grid-cols-2">
              <label class="space-y-2 text-sm">
                <span class="font-medium text-slate-700">开始日期</span>
                <input
                  v-model="taskForm.startDate"
                  type="date"
                  class="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                />
              </label>
              <label class="space-y-2 text-sm">
                <span class="font-medium text-slate-700">结束日期</span>
                <input
                  v-model="taskForm.endDate"
                  type="date"
                  class="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                />
              </label>
            </div>
          </div>
        </div>

        <div class="grid gap-4 lg:grid-cols-4">
          <label class="space-y-2 text-sm">
            <span class="font-medium text-slate-700">总抓取上限</span>
            <input
              v-model.number="taskForm.totalLimit"
              type="number"
              min="1"
              class="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            />
          </label>
          <label class="space-y-2 text-sm">
            <span class="font-medium text-slate-700">分页大小</span>
            <input
              v-model.number="taskForm.pageSize"
              type="number"
              min="10"
              class="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            />
          </label>
          <label class="space-y-2 text-sm">
            <span class="font-medium text-slate-700">排序</span>
            <select
              v-model="taskForm.sort"
              class="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            >
              <option value="comments_desc">按评论热度</option>
              <option value="relevance">按相关度</option>
              <option value="hot">按热度</option>
            </select>
          </label>
          <label class="space-y-2 text-sm">
            <span class="font-medium text-slate-700">内容类型</span>
            <select
              v-model="taskForm.infoType"
              class="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            >
              <option value="2">内容</option>
              <option value="1">全部</option>
              <option value="3">评论</option>
            </select>
          </label>
        </div>

        <label class="inline-flex items-center gap-2 text-sm text-slate-600">
          <input v-model="taskForm.dedupeByContent" type="checkbox" class="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
          导出前按“内容”字段去重
        </label>
      </div>
    </AppModal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  Cog6ToothIcon,
  PauseCircleIcon,
  PlayCircleIcon,
  PlusIcon,
  QueueListIcon,
} from '@heroicons/vue/24/outline'

import AppModal from '../../components/AppModal.vue'
import { useActiveProject } from '../../composables/useActiveProject'
import { useApiBase } from '../../composables/useApiBase'

const platformOptions = ['微博', '微信', '新闻网站', '新闻APP', '论坛', '视频', '自媒体号', '全部']

const router = useRouter()
const { backendBase, callApi } = useApiBase()
const { activeProjectName } = useActiveProject()

const loading = ref(false)
const error = ref('')
const tasks = ref([])
const projects = ref([])
const autoRefresh = ref(true)
const onlyCurrentProject = ref(false)
const createModalOpen = ref(false)
const planning = ref(false)
const submitting = ref(false)
const refreshTimer = ref(null)
const downloadingTaskId = ref('')

const worker = ref({})
const settingsState = reactive({
  credentials: {
    configured: false,
    user: '',
    masked_user: '',
    password_configured: false,
  },
  runtime: {},
  planner: {},
})

const feedback = reactive({
  type: '',
  message: '',
})

const taskForm = reactive({
  title: '',
  project: '',
  brief: '',
  keywordsText: '',
  platforms: [],
  startDate: '',
  endDate: '',
  totalLimit: 500,
  pageSize: 50,
  sort: 'comments_desc',
  infoType: '2',
  dedupeByContent: true,
})

const canSubmit = computed(() => {
  if (!taskForm.title.trim()) return false
  if (!taskForm.startDate || !taskForm.endDate) return false
  if (!parseKeywords(taskForm.keywordsText).length) return false
  if (!taskForm.platforms.length) return false
  return true
})

const filteredTasks = computed(() => {
  if (!onlyCurrentProject.value || !activeProjectName.value) return tasks.value
  return tasks.value.filter((task) => task.project === activeProjectName.value)
})

const workerStatusLabel = computed(() => {
  if (!worker.value?.running) return '离线'
  if (worker.value?.status === 'running') return `运行中${worker.value?.current_task_id ? ` · ${worker.value.current_task_id}` : ''}`
  return '待命'
})

const summaryCards = computed(() => {
  const summary = taskSummary.value
  return [
    {
      key: 'total',
      label: '总任务数',
      value: summary.total ?? 0,
      description: '本地持久化的 NetInsight 队列任务总量',
    },
    {
      key: 'queued',
      label: '排队中',
      value: summary.queued ?? 0,
      description: '等待后台开始处理',
    },
    {
      key: 'running',
      label: '执行中',
      value: summary.running ?? 0,
      description: '正在登录、计数、抓取或导出',
    },
    {
      key: 'completed',
      label: '已完成',
      value: summary.completed ?? 0,
      description: '成功导出 CSV / JSONL / meta 文件',
    },
    {
      key: 'failed',
      label: '失败/取消',
      value: (summary.failed ?? 0) + (summary.cancelled ?? 0),
      description: '可直接在列表中重试或删除',
    },
  ]
})

const taskSummary = computed(() => {
  if (!tasks.value.length) {
    return { total: 0, queued: 0, running: 0, completed: 0, failed: 0, cancelled: 0 }
  }
  return tasks.value.reduce(
    (summary, task) => {
      const status = task.status
      summary.total += 1
      if (status in summary) summary[status] += 1
      return summary
    },
    { total: 0, queued: 0, running: 0, completed: 0, failed: 0, cancelled: 0 }
  )
})

function openCreateModal() {
  resetTaskForm()
  createModalOpen.value = true
}

function resetTaskForm() {
  const today = new Date()
  const start = new Date(today)
  start.setDate(today.getDate() - Number(settingsState.planner.default_days || 30) + 1)
  taskForm.title = ''
  taskForm.project = activeProjectName.value || ''
  taskForm.brief = ''
  taskForm.keywordsText = ''
  taskForm.platforms = normalizePlatformsForSubmit(settingsState.planner.default_platforms || ['微博'])
  taskForm.startDate = formatDateInput(start)
  taskForm.endDate = formatDateInput(today)
  taskForm.totalLimit = Number(settingsState.planner.default_total_limit || 500)
  taskForm.pageSize = Number(settingsState.runtime.page_size || 50)
  taskForm.sort = String(settingsState.runtime.sort || 'comments_desc')
  taskForm.infoType = String(settingsState.runtime.info_type || '2')
  taskForm.dedupeByContent = true
}

async function fetchProjects() {
  try {
    const response = await callApi('/api/projects', { method: 'GET' })
    projects.value = Array.isArray(response.projects) ? response.projects : []
  } catch (err) {
    console.warn(err)
  }
}

async function fetchSettings() {
  try {
    const response = await callApi('/api/settings/netinsight', { method: 'GET' })
    const payload = response?.data || {}
    Object.assign(settingsState.credentials, payload.credentials || {})
    settingsState.runtime = payload.runtime || {}
    settingsState.planner = payload.planner || {}
  } catch (err) {
    console.warn(err)
  }
}

async function fetchTasks() {
  loading.value = true
  error.value = ''
  try {
    const response = await callApi('/api/netinsight/tasks', { method: 'GET' })
    const payload = response?.data || {}
    tasks.value = Array.isArray(payload.tasks) ? payload.tasks : []
    worker.value = payload.worker || {}
  } catch (err) {
    error.value = err instanceof Error ? err.message : '读取任务列表失败'
  } finally {
    loading.value = false
  }
}

async function planTask() {
  if (!taskForm.brief.trim()) return
  planning.value = true
  feedback.type = ''
  feedback.message = ''
  try {
    const response = await callApi('/api/netinsight/tasks/plan', {
      method: 'POST',
      body: JSON.stringify({ brief: taskForm.brief }),
    })
    const plan = response?.data || {}
    taskForm.title = String(plan.title || taskForm.title || '').trim()
    taskForm.keywordsText = Array.isArray(plan.keywords) ? plan.keywords.join('\n') : taskForm.keywordsText
    taskForm.platforms = Array.isArray(plan.platforms) && plan.platforms.length
      ? normalizePlatformsForSubmit(plan.platforms)
      : taskForm.platforms
    taskForm.startDate = String(plan.start_date || taskForm.startDate || '')
    taskForm.endDate = String(plan.end_date || taskForm.endDate || '')
    taskForm.totalLimit = Number(plan.total_limit || taskForm.totalLimit || 500)
    taskForm.pageSize = Number(plan.page_size || taskForm.pageSize || 50)
    taskForm.sort = String(plan.sort || taskForm.sort || 'comments_desc')
    taskForm.infoType = String(plan.info_type || taskForm.infoType || '2')
    taskForm.dedupeByContent = Boolean(plan.dedupe_by_content ?? taskForm.dedupeByContent)
    feedback.type = 'success'
    feedback.message = `已根据任务说明生成建议配置（来源：${plan.planner_source || 'heuristic'}）`
  } catch (err) {
    feedback.type = 'error'
    feedback.message = err instanceof Error ? err.message : '解析任务说明失败'
  } finally {
    planning.value = false
  }
}

async function submitTask() {
  if (!canSubmit.value) return
  submitting.value = true
  feedback.type = ''
  feedback.message = ''
  try {
    const response = await callApi('/api/netinsight/tasks', {
      method: 'POST',
      body: JSON.stringify({
        title: taskForm.title,
        project: taskForm.project,
        query: taskForm.brief,
        summary: taskForm.brief,
        keywords: parseKeywords(taskForm.keywordsText),
        platforms: normalizePlatformsForSubmit(taskForm.platforms),
        start_date: taskForm.startDate,
        end_date: taskForm.endDate,
        total_limit: Number(taskForm.totalLimit || 500),
        page_size: Number(taskForm.pageSize || 50),
        sort: taskForm.sort,
        info_type: taskForm.infoType,
        dedupe_by_content: taskForm.dedupeByContent,
      }),
    })
    createModalOpen.value = false
    feedback.type = 'success'
    feedback.message = `任务 ${response?.data?.task?.id || ''} 已提交到队列`
    await fetchTasks()
  } catch (err) {
    feedback.type = 'error'
    feedback.message = err instanceof Error ? err.message : '创建任务失败'
  } finally {
    submitting.value = false
  }
}

async function cancelTask(task) {
  try {
    await callApi(`/api/netinsight/tasks/${encodeURIComponent(task.id)}/cancel`, {
      method: 'POST',
    })
    feedback.type = 'success'
    feedback.message = `已发送取消请求：${task.title || task.id}`
    await fetchTasks()
  } catch (err) {
    feedback.type = 'error'
    feedback.message = err instanceof Error ? err.message : '取消任务失败'
  }
}

async function retryTask(task) {
  try {
    const response = await callApi(`/api/netinsight/tasks/${encodeURIComponent(task.id)}/retry`, {
      method: 'POST',
    })
    feedback.type = 'success'
    feedback.message = `已创建重试任务：${response?.data?.task?.id || ''}`
    await fetchTasks()
  } catch (err) {
    feedback.type = 'error'
    feedback.message = err instanceof Error ? err.message : '重试任务失败'
  }
}

async function deleteTask(task) {
  try {
    await callApi(`/api/netinsight/tasks/${encodeURIComponent(task.id)}`, {
      method: 'DELETE',
    })
    feedback.type = 'success'
    feedback.message = `已删除任务：${task.title || task.id}`
    await fetchTasks()
  } catch (err) {
    feedback.type = 'error'
    feedback.message = err instanceof Error ? err.message : '删除任务失败'
  }
}

async function downloadTaskFile(task, kind) {
  downloadingTaskId.value = task.id
  feedback.type = ''
  feedback.message = ''
  try {
    const response = await fetch(buildTaskFileUrl(task.id, kind))
    if (!response.ok) {
      const text = await response.text()
      throw new Error(text || '下载任务文件失败')
    }
    const blob = await response.blob()
    const downloadUrl = window.URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = downloadUrl
    anchor.download = parseDownloadFilename(response.headers.get('Content-Disposition')) || `${task.id}.${kind}`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    window.URL.revokeObjectURL(downloadUrl)
    feedback.type = 'success'
    feedback.message = `已开始下载 ${task.title || task.id} 的 ${kind.toUpperCase()} 文件`
  } catch (err) {
    feedback.type = 'error'
    feedback.message = err instanceof Error ? err.message : '下载任务文件失败'
  } finally {
    downloadingTaskId.value = ''
  }
}

function goSettings() {
  router.push({ name: 'settings-netinsight' })
}

function statusLabel(status) {
  return {
    queued: '排队中',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }[status] || status || '未知'
}

function statusClass(status) {
  return {
    queued: 'border border-slate-200 bg-slate-100 text-slate-700',
    running: 'border border-sky-200 bg-sky-50 text-sky-700',
    completed: 'border border-emerald-200 bg-emerald-50 text-emerald-700',
    failed: 'border border-rose-200 bg-rose-50 text-rose-700',
    cancelled: 'border border-amber-200 bg-amber-50 text-amber-700',
  }[status] || 'bg-slate-100 text-slate-700'
}

function statusDotClass(status) {
  return {
    queued: 'bg-slate-400',
    running: 'bg-sky-500',
    completed: 'bg-emerald-500',
    failed: 'bg-rose-500',
    cancelled: 'bg-amber-500',
  }[status] || 'bg-slate-400'
}

function progressFillClass(status) {
  return {
    queued: 'bg-slate-500',
    running: 'bg-gradient-to-r from-sky-500 to-cyan-400',
    completed: 'bg-gradient-to-r from-emerald-500 to-teal-400',
    failed: 'bg-gradient-to-r from-rose-500 to-orange-400',
    cancelled: 'bg-gradient-to-r from-amber-400 to-yellow-300',
  }[status] || 'bg-slate-500'
}

function parseKeywords(text) {
  return String(text || '')
    .split(/[\n,，;；、]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function normalizePlatformsForSubmit(values) {
  const list = Array.isArray(values) ? values.map((item) => String(item).trim()).filter(Boolean) : []
  if (list.includes('全部')) return ['全部']
  return list
}

function taskHasFile(task, filename) {
  const files = Array.isArray(task?.output?.files) ? task.output.files : []
  if (!files.length) return Boolean(task?.output?.dir && task?.status === 'completed')
  return files.some((item) => String(item || '').endsWith(`/${filename}`) || String(item || '').endsWith(`\\${filename}`))
}

function buildTaskFileUrl(taskId, kind) {
  const base = String(backendBase.value || '').replace(/\/+$/, '')
  return `${base}/api/netinsight/tasks/${encodeURIComponent(taskId)}/files/${encodeURIComponent(kind)}`
}

function formatDateInput(value) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatTimestamp(value) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

function parseDownloadFilename(contentDisposition) {
  const match = String(contentDisposition || '').match(/filename\*?=(?:UTF-8''|")?([^\";]+)/i)
  if (!match?.[1]) return ''
  const raw = match[1].replace(/"/g, '').trim()
  try {
    return decodeURIComponent(raw)
  } catch {
    return raw
  }
}

function startRefreshLoop() {
  stopRefreshLoop()
  refreshTimer.value = window.setInterval(() => {
    if (!autoRefresh.value) return
    const hasActive = tasks.value.some((task) => ['queued', 'running'].includes(task.status))
    if (hasActive || !tasks.value.length) {
      fetchTasks()
    }
  }, 5000)
}

function stopRefreshLoop() {
  if (refreshTimer.value) {
    window.clearInterval(refreshTimer.value)
    refreshTimer.value = null
  }
}

watch(activeProjectName, (value) => {
  if (!taskForm.project) {
    taskForm.project = value || ''
  }
})

onMounted(async () => {
  await Promise.all([fetchSettings(), fetchProjects(), fetchTasks()])
  resetTaskForm()
  startRefreshLoop()
})

onBeforeUnmount(() => {
  stopRefreshLoop()
})
</script>

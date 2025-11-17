<template>
  <div class="space-y-8">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="space-y-1">
        <p class="text-xs font-semibold uppercase tracking-[0.4em] text-muted">Content Analysis</p>
        <h1 class="text-2xl font-semibold text-primary">内容分析 · Prompt 工作台</h1>
        <p class="text-sm text-secondary">按专题从零搭建一级/二级编码，生成 LLM 可读的 Prompt 并保存。</p>
      </div>
      <div class="inline-flex items-center gap-2 rounded-full bg-brand-soft px-4 py-1.5 text-xs font-semibold text-brand-700">
        <AdjustmentsHorizontalIcon class="h-4 w-4" />
        <span>编码工作台</span>
      </div>
    </header>

    <section class="card-surface space-y-6 p-6">
      <header class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-1">
          <h2 class="text-xl font-semibold text-primary">提示词工作台</h2>
          <p class="text-sm text-secondary">选择专题 → 搭建一级/二级编码 → 生成/微调 Prompt → 保存。</p>
        </div>
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <label class="flex items-center gap-2">
            <span class="text-xs font-semibold text-muted">专题</span>
            <select
              v-model="selectedTopic"
              class="rounded-2xl border border-soft px-3 py-2 text-sm focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
              :disabled="topicsState.loading || !topicOptions.length"
            >
              <option value="" disabled>请选择专题</option>
              <option v-for="option in topicOptions" :key="option" :value="option">{{ option }}</option>
            </select>
          </label>
          <button type="button" class="btn-ghost px-3 py-1" :disabled="topicsState.loading" @click="loadTopics">
            <ArrowPathIcon class="h-4 w-4" :class="topicsState.loading ? 'animate-spin' : ''" />
            刷新专题
          </button>
          <button type="button" class="btn-ghost px-3 py-1" @click="resetBuilderToBlank">清空方案</button>
          <button type="button" class="btn-ghost px-3 py-1" @click="loadPresetExample" :disabled="promptState.loading">载入示例</button>
          <span v-if="promptState.path" class="text-[11px] text-muted">存储路径：{{ promptState.path }}</span>
        </div>
      </header>

      <div class="grid gap-6">
        <div class="rounded-3xl border border-soft bg-surface p-4 shadow-sm space-y-4">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="space-y-1">
              <h3 class="text-sm font-semibold text-primary">编码方案工作台</h3>
              <p class="text-xs text-muted">建组（一级/二级+单/多选）→ 添加编码 → 生成 Prompt。</p>
            </div>
            <div class="flex flex-wrap gap-2 text-[11px] text-muted">
              <button type="button" class="btn-secondary px-3 py-1" @click="addBlock({ level: 'level1', selection: 'single' })">新增一级组</button>
              <button type="button" class="btn-secondary px-3 py-1" @click="addBlock({ level: 'level2', selection: 'multi' })">新增二级组</button>
            </div>
          </div>

          <div class="grid gap-4 md:grid-cols-4">
            <div class="rounded-2xl border border-dashed border-soft bg-white p-3 text-xs text-secondary md:col-span-1">
              <div class="mb-2 text-sm font-semibold text-primary">设计提示</div>
              <ul class="list-disc space-y-1 pl-4">
                <li>一级/二级可混用但务必命名清晰。</li>
                <li>单选字段写明“只能选一项”。</li>
                <li>多选字段给出主次/排序的判断逻辑。</li>
                <li>强制规则写在 Edge cases，优先级高的放前。</li>
              </ul>
            </div>
            <div class="md:col-span-3 space-y-4">
              <div
                v-for="(block, blockIndex) in builder.blocks"
                :key="block.id"
                class="rounded-3xl border border-dashed border-soft bg-white p-4 shadow-sm"
              >
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div class="flex flex-wrap items-center gap-2 text-sm">
                    <input
                      v-model="block.title"
                      type="text"
                      class="w-56 rounded-2xl border border-soft px-3 py-2 text-sm focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                      placeholder="组名，如 信息类别 / 议题编码"
                    />
                    <select
                      v-model="block.level"
                      class="rounded-2xl border border-soft px-3 py-2 text-sm focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                    >
                      <option value="level1">一级编码</option>
                      <option value="level2">二级编码</option>
                    </select>
                    <select
                      v-model="block.selection"
                      class="rounded-2xl border border-soft px-3 py-2 text-sm focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                    >
                      <option value="single">单选</option>
                      <option value="multi">多选</option>
                    </select>
                    <span class="text-[11px] text-muted">层级+选型要写清楚，LLM 才能遵守</span>
                  </div>
                  <div class="flex flex-wrap gap-2 text-xs">
                    <button type="button" class="btn-ghost px-3 py-1" @click="openModal(block)">新增编码</button>
                    <button type="button" class="btn-ghost px-3 py-1 text-rose-600 hover:text-rose-700" @click="removeBlock(blockIndex)">
                      删除组
                    </button>
                  </div>
                </div>

                <div class="mt-3 rounded-2xl border border-soft bg-surface-muted/60 p-3">
                  <div class="mb-2 flex items-center justify-between text-xs text-muted">
                    <span>编码项（逐条添加，可混排）</span>
                    <span>共 {{ block.codes.length }} 项</span>
                  </div>
                  <div class="grid gap-2 md:grid-cols-2">
                    <div
                      v-for="(code, codeIndex) in block.codes"
                      :key="code.id"
                      class="flex items-center gap-2 rounded-2xl border border-soft bg-white px-3 py-2"
                    >
                      <span class="rounded-full bg-surface-muted px-2 py-1 text-[11px] font-semibold text-muted">{{ block.level === 'level1' ? 'L1' : 'L2' }}</span>
                      <input
                        v-model="code.code"
                        type="text"
                        class="w-24 rounded-xl border border-soft px-2 py-1 text-sm focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                        placeholder="编码"
                      />
                      <input
                        v-model="code.label"
                        type="text"
                        class="flex-1 rounded-xl border border-soft px-2 py-1 text-sm focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                        placeholder="描述，如 青少年 / 观点性报道"
                      />
                      <button
                        type="button"
                        class="text-xs text-muted hover:text-rose-500"
                        @click="removeCode(block, codeIndex)"
                      >
                        删除
                      </button>
                    </div>
                    <p v-if="!block.codes.length" class="text-xs text-muted md:col-span-2">请为该组添加编码项。</p>
                  </div>
                </div>
              </div>
              <p v-if="!builder.blocks.length" class="text-xs text-muted">当前为空白方案，请先新增一级组/二级组。</p>
            </div>
          </div>

          <div class="grid gap-4 rounded-3xl border border-soft bg-white p-4 text-sm text-secondary">
            <label class="space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-xs font-semibold text-muted">Edge Cases / 强制规则</span>
                <button type="button" class="btn-ghost px-2 py-1 text-[11px]" @click="applyEdgeCases">插入常见规则</button>
              </div>
              <textarea
                v-model="builder.edgeCases"
                rows="5"
                class="w-full rounded-2xl border border-dashed border-soft bg-surface px-3 py-2 text-sm leading-relaxed text-primary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                placeholder="写下强制规则与边界处理，比如：出现电子烟 → 必须含 1-14。"
              />
            </label>
            <div class="flex flex-wrap items-center gap-2 text-xs text-muted">
              <button type="button" class="btn-primary" @click="buildPrompts" :disabled="promptState.saving || !currentTopic">生成 Prompt</button>
              <button type="button" class="btn-ghost" @click="saveDraft">保存草稿</button>
              <span>生成后可下方微调文本再保存到后端。</span>
            </div>
          </div>
        </div>

        <div class="grid gap-6 lg:grid-cols-2">
          <label class="space-y-2 text-sm text-secondary">
            <div class="flex items-center justify-between">
              <span class="text-xs font-semibold text-muted">System Prompt *</span>
              <span class="text-[11px] text-muted">负责角色 / 输出边界</span>
            </div>
            <textarea
              v-model="promptState.system_prompt"
              rows="10"
              class="w-full rounded-3xl border border-soft bg-surface px-4 py-3 text-sm leading-relaxed text-primary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
              placeholder="You are a strict content-coding engine. Your only job is to return a JSON..."
            />
          </label>
          <label class="space-y-2 text-sm text-secondary">
            <div class="flex items-center justify-between">
              <span class="text-xs font-semibold text-muted">Analysis Prompt *</span>
              <span class="text-[11px] text-muted">编码规则 / 字段定义</span>
            </div>
            <textarea
              v-model="promptState.analysis_prompt"
              rows="14"
              class="w-full rounded-3xl border border-soft bg-surface px-4 py-3 text-sm leading-relaxed text-primary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
              placeholder="Coding rules with 信息类别 / 议题编码 / 信源编码 / 报道体裁 / 诉求方式..."
            />
          </label>
        </div>

        <div class="flex flex-wrap items-center gap-3 text-sm">
          <button
            type="button"
            class="btn-primary"
            :disabled="promptState.saving || !currentTopic"
            @click="savePrompt"
          >
            {{ promptState.saving ? '保存中…' : '保存提示词' }}
          </button>
          <button
            type="button"
            class="btn-secondary"
            :disabled="promptState.loading"
            @click="loadPrompt"
          >
            重新加载
          </button>
          <span v-if="!currentTopic" class="text-xs text-danger">请先选择专题</span>
          <span v-else-if="promptState.error" class="text-xs text-danger">{{ promptState.error }}</span>
          <span v-else-if="promptState.message" class="text-xs text-emerald-600">{{ promptState.message }}</span>
          <span v-else class="text-xs text-muted">
            保存后即可在后端以 ContentAnalyze 运行；未填写时会保留已有配置。
          </span>
        </div>

        <div class="rounded-3xl border border-dashed border-soft bg-surface-muted p-4 text-xs text-secondary">
          <div class="mb-2 flex items-center justify-between">
            <span class="font-semibold text-primary">实时提示词预览</span>
            <span v-if="promptState.path" class="text-[11px] text-muted">保存位置：{{ promptState.path }}</span>
          </div>
          <div class="grid gap-4 md:grid-cols-2">
            <div class="rounded-2xl border border-soft bg-white p-3">
              <div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">System Prompt</div>
              <pre class="max-h-52 overflow-y-auto whitespace-pre-wrap break-words text-[12px] leading-relaxed text-primary">{{ promptState.system_prompt || '（未填写）' }}</pre>
            </div>
            <div class="rounded-2xl border border-soft bg-white p-3">
              <div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">Analysis Prompt</div>
              <pre class="max-h-52 overflow-y-auto whitespace-pre-wrap break-words text-[12px] leading-relaxed text-primary">{{ promptState.analysis_prompt || '（未填写）' }}</pre>
            </div>
          </div>
        </div>
      </div>
    </section>

    <div v-if="modalState.visible" class="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <div class="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl">
        <h3 class="text-lg font-semibold text-primary">新增编码</h3>
        <p class="mt-1 text-xs text-muted">填写编码值与描述，支持一级/二级组混用。</p>
        <div class="mt-4 space-y-3 text-sm">
          <label class="space-y-1">
            <span class="text-xs font-semibold text-muted">编码值</span>
            <input
              v-model="modalState.form.code"
              type="text"
              class="w-full rounded-2xl border border-soft px-3 py-2 text-sm focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
              placeholder="如 1-12 / 3"
            />
          </label>
          <label class="space-y-1">
            <span class="text-xs font-semibold text-muted">描述</span>
            <input
              v-model="modalState.form.label"
              type="text"
              class="w-full rounded-2xl border border-soft px-3 py-2 text-sm focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
              placeholder="如 青少年 / 观点性报道"
            />
          </label>
        </div>
        <div class="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
          <span>将保存到：{{ modalState.targetBlock?.title || '未命名组' }}（{{ modalState.targetBlock?.level === 'level1' ? '一级' : '二级' }}）</span>
          <div class="flex gap-2 text-sm">
            <button class="btn-ghost" type="button" @click="modalState.visible = false">取消</button>
            <button class="btn-primary" type="button" :disabled="!modalState.form.code || !modalState.form.label" @click="addCodeFromModal">
              确认添加
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { AdjustmentsHorizontalIcon, ArrowPathIcon } from '@heroicons/vue/24/outline'
import { useApiBase } from '../../../composables/useApiBase'

const { callApi } = useApiBase()

const topicsState = reactive({
  loading: false,
  error: '',
  options: []
})

const topicOptions = computed(() => topicsState.options)
const selectedTopic = ref('')

const promptState = reactive({
  loading: false,
  saving: false,
  error: '',
  message: '',
  exists: false,
  system_prompt: '',
  analysis_prompt: '',
  path: ''
})

const currentTopic = computed(() => (selectedTopic.value || '').trim())

const builder = reactive({
  blocks: [],
  edgeCases: ''
})

const modalState = reactive({
  visible: false,
  targetBlock: null,
  form: {
    code: '',
    label: ''
  }
})

const presetBlocks = [
  {
    title: '信息类别（单选）',
    selection: 'single',
    level: 'level1',
    codes: [
      { code: '1', label: '控烟立场（支持控烟）' },
      { code: '2', label: '烟草立场（支持产业/反控烟）' },
      { code: '3', label: '其他或无关' }
    ]
  },
  {
    title: '议题编码（多选）',
    selection: 'multi',
    level: 'level2',
    codes: [
      { code: '1-1', label: '烟草与健康' },
      { code: '1-2', label: '无烟立法' },
      { code: '1-3', label: '控烟公约' },
      { code: '1-12', label: '青少年' },
      { code: '1-14', label: '电子烟' },
      { code: '2-1', label: '社会公益' }
    ]
  },
  {
    title: '信源编码（多选）',
    selection: 'multi',
    level: 'level2',
    codes: [
      { code: '2', label: '卫生部门' },
      { code: '10', label: '意见领袖' },
      { code: '11', label: '媒体自采' },
      { code: '8', label: '烟草行业' }
    ]
  },
  {
    title: '报道体裁（单选）',
    selection: 'single',
    level: 'level1',
    codes: [
      { code: '1', label: '事实性报道' },
      { code: '2', label: '观点性报道' },
      { code: '3', label: '深度综合' },
      { code: '4', label: '科普/研究' },
      { code: '5', label: '其他' }
    ]
  },
  {
    title: '诉求方式（多选）',
    selection: 'multi',
    level: 'level2',
    codes: [
      { code: '1', label: '恐怖诉求' },
      { code: '2', label: '人性诉求' },
      { code: '3', label: '代言人/证言' },
      { code: '4', label: '行动呼吁' },
      { code: '5', label: '修辞格' },
      { code: '6', label: '无明显诉求' }
    ]
  }
]

const draftKeyForTopic = (topic) => `content-prompt-draft:${topic}`

const uuid = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `id-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

const resetPromptState = () => {
  promptState.system_prompt = ''
  promptState.analysis_prompt = ''
  promptState.exists = false
  promptState.path = ''
  promptState.error = ''
  promptState.message = ''
}

const extractRemoteTopics = (payload) => {
  const databases = payload?.data?.databases || payload?.databases || []
  if (!Array.isArray(databases)) return []
  const unique = new Set()
  databases.forEach((entry) => {
    if (!entry) return
    if (typeof entry === 'string') {
      const trimmed = entry.trim()
      if (trimmed) unique.add(trimmed)
      return
    }
    if (typeof entry === 'object') {
      const name = String(entry.name || entry.topic || entry.display_name || entry.project || '').trim()
      if (name) {
        unique.add(name)
        return
      }
      const label = String(entry.metadata?.topic_label || '').trim()
      if (label) unique.add(label)
    }
  })
  return Array.from(unique)
}

const loadTopics = async () => {
  topicsState.loading = true
  topicsState.error = ''
  try {
    const response = await callApi('/api/query', { method: 'POST', body: JSON.stringify({}) })
    const options = extractRemoteTopics(response)
    topicsState.options = options
    if (!options.length) {
      selectedTopic.value = ''
      return
    }
    if (!options.includes(currentTopic.value)) {
      selectedTopic.value = options[0]
    }
  } catch (err) {
    topicsState.error = err instanceof Error ? err.message : '无法加载专题列表'
    topicsState.options = []
    selectedTopic.value = ''
  } finally {
    topicsState.loading = false
  }
}

const addBlock = (preset) => {
  const codes = (preset?.codes || []).map((item) => ({
    id: uuid(),
    code: item.code || '',
    label: item.label || ''
  }))
  builder.blocks.push({
    id: uuid(),
    title: preset?.title || '',
    selection: preset?.selection || 'single',
    level: preset?.level || 'level1',
    codes
  })
}

const removeBlock = (index) => {
  builder.blocks.splice(index, 1)
}

const addCode = (block) => {
  block.codes.push({ id: uuid(), code: '', label: '' })
}

const removeCode = (block, index) => {
  block.codes.splice(index, 1)
}

const openModal = (block) => {
  modalState.visible = true
  modalState.targetBlock = block
  modalState.form.code = ''
  modalState.form.label = ''
}

const addCodeFromModal = () => {
  if (!modalState.targetBlock) return
  modalState.targetBlock.codes.push({
    id: uuid(),
    code: modalState.form.code.trim(),
    label: modalState.form.label.trim()
  })
  modalState.visible = false
}

const applyEdgeCases = () => {
  builder.edgeCases =
    builder.edgeCases ||
    [
      '出现青少年 → 必须含 "1-12"',
      '出现电子烟 → 必须含 "1-14"',
      '港澳台/国外经验 → 必须含 "1-13"',
      '1200 字以上解释原因/影响 → 体裁 3',
      '社论/评论员文章 → 体裁 2',
      '纯发报告数据 → 体裁 4',
      '简讯/会议通稿 → 体裁 1'
    ].join('\n')
}

const buildPrompts = () => {
  if (!builder.blocks.length) {
    promptState.error = '请至少创建一组编码'
    return
  }

  const systemBase =
    'You are a strict content-coding engine. Your only job is to return a valid JSON with five fields: ' +
    '{"信息类别": "1|2|3","议题编码": ["...", "..."],"信源编码": ["...", "..."],"报道体裁": "1|2|3|4|5","诉求方式": ["...", "..."]}'

  const parts = ['Coding rules (must be followed exactly, no new codes allowed)', '']
  builder.blocks.forEach((block, idx) => {
    const heading = `${idx + 1}. ${block.title || '未命名组'}（${block.level === 'level1' ? '一级' : '二级'}，${block.selection === 'single' ? '单选' : '多选'}）`
    parts.push(heading)
    const cleaned = block.codes
      .filter((c) => c.code || c.label)
      .map((c) => `${c.code || ''} ${c.label || ''}`.trim())
    parts.push(cleaned.length ? cleaned.join('； ') : '请补充编码')
    parts.push('')
  })
  parts.push('Hard-case hints（当你犹豫时按下列示例执行）')
  parts.push(builder.edgeCases || '无')

  promptState.system_prompt = systemBase
  promptState.analysis_prompt = parts.join('\n')
  promptState.message = '已根据方案生成草稿，可下方微调后保存。'
  saveDraft()
}

const loadPresetExample = () => {
  builder.blocks = []
  presetBlocks.forEach((p) => addBlock(p))
  builder.edgeCases =
    '出现青少年 → 必须含 "1-12"\n' +
    '出现电子烟 → 必须含 "1-14"\n' +
    '港澳台/国外经验 → 必须含 "1-13"\n' +
    '1200 字以上解释原因/影响 → 体裁 3\n' +
    '社论/评论员文章 → 体裁 2\n' +
    '纯发报告数据 → 体裁 4\n' +
    '简讯/会议通稿 → 体裁 1'
  buildPrompts()
  promptState.message = '已载入示例，可直接保存或继续调整。'
}

const resetBuilderToBlank = () => {
  builder.blocks = []
  builder.edgeCases = ''
  promptState.system_prompt = ''
  promptState.analysis_prompt = ''
  promptState.message = '已清空方案，请从新增组开始。'
  saveDraft()
}

const saveDraft = () => {
  const topic = currentTopic.value
  if (!topic) return
  const payload = {
    blocks: builder.blocks.map((b) => ({
      title: b.title,
      selection: b.selection,
      level: b.level,
      codes: b.codes.map((c) => ({ code: c.code, label: c.label }))
    })),
    edgeCases: builder.edgeCases,
    system_prompt: promptState.system_prompt,
    analysis_prompt: promptState.analysis_prompt
  }
  try {
    window.localStorage.setItem(draftKeyForTopic(topic), JSON.stringify(payload))
  } catch {
    /* ignore storage errors */
  }
}

const loadDraft = () => {
  const topic = currentTopic.value
  if (!topic) return false
  try {
    const raw = window.localStorage.getItem(draftKeyForTopic(topic))
    if (!raw) return false
    const payload = JSON.parse(raw)
    builder.blocks = []
    ;(payload.blocks || []).forEach((b) =>
      addBlock({
        title: b.title,
        selection: b.selection,
        level: b.level,
        codes: b.codes || []
      })
    )
    builder.edgeCases = payload.edgeCases || ''
    promptState.system_prompt = payload.system_prompt || ''
    promptState.analysis_prompt = payload.analysis_prompt || ''
    return true
  } catch {
    return false
  }
}

const loadPrompt = async () => {
  const topic = currentTopic.value
  if (!topic) {
    promptState.error = '请先选择专题'
    resetPromptState()
    return
  }

  promptState.loading = true
  promptState.error = ''
  promptState.message = ''
  try {
    const params = new URLSearchParams({ topic }).toString()
    const result = await callApi(`/api/content/prompt?${params}`)
    const data = result?.data ?? {}
    promptState.exists = Boolean(data.exists)
    promptState.system_prompt = data.system_prompt || ''
    promptState.analysis_prompt = data.analysis_prompt || ''
    promptState.path = data.path || ''
    if (!loadDraft()) {
      saveDraft()
    }
  } catch (err) {
    promptState.error = err instanceof Error ? err.message : '加载提示词失败'
    resetPromptState()
  } finally {
    promptState.loading = false
  }
}

const savePrompt = async () => {
  const topic = currentTopic.value
  if (!topic) {
    promptState.error = '请先选择专题'
    return
  }
  if (!promptState.system_prompt && !promptState.analysis_prompt) {
    promptState.error = 'system_prompt 与 analysis_prompt 不能同时为空'
    return
  }

  promptState.saving = true
  promptState.error = ''
  promptState.message = ''
  try {
    const result = await callApi('/api/content/prompt', {
      method: 'POST',
      body: JSON.stringify({
        topic,
        system_prompt: promptState.system_prompt,
        analysis_prompt: promptState.analysis_prompt
      })
    })
    const data = result?.data ?? {}
    promptState.exists = Boolean(data.exists)
    promptState.path = data.path || ''
    promptState.message = '提示词已保存'
    saveDraft()
  } catch (err) {
    promptState.error = err instanceof Error ? err.message : '保存失败'
  } finally {
    promptState.saving = false
  }
}

onMounted(() => {
  loadTopics()
})

watch(
  () => topicOptions.value.slice(),
  (list) => {
    if (!currentTopic.value && list.length) {
      selectedTopic.value = list[0]
    }
  },
  { immediate: true }
)

watch(
  () => currentTopic.value,
  (value) => {
    if (value) {
      if (!loadDraft()) {
        loadPrompt()
      }
    } else {
      resetPromptState()
      builder.blocks = []
      builder.edgeCases = ''
    }
  },
  { immediate: true }
)

watch(
  () => [builder.blocks, builder.edgeCases, promptState.system_prompt, promptState.analysis_prompt],
  () => saveDraft(),
  { deep: true }
)
</script>

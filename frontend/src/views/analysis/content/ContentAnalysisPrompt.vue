<template>
  <div class="space-y-8">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="space-y-1">
        <p class="text-xs font-semibold uppercase tracking-[0.4em] text-muted">Content Analysis</p>
        <h1 class="text-2xl font-semibold text-primary">内容分析 · 提示词工作台</h1>
        <p class="text-sm text-secondary">按专题搭建一级/二级编码，生成可直接使用的提示词并保存。</p>
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
          <p class="text-sm text-secondary">选择专题 → 搭建一级/二级编码 → 生成并微调提示词后保存。</p>
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
              <p class="text-xs text-muted">通过设置编码组（一级/二级，单选/多选）并添加对应编码项，完善提示词配置。</p>
            </div>
            <div class="flex flex-wrap gap-2 text-[11px] text-muted">
              <button type="button" class="btn-secondary px-3 py-1" @click="addBlock({ level: 'level1', selection: 'single' })">新增一级组</button>
              <button type="button" class="btn-secondary px-3 py-1" @click="addBlock({ level: 'level2', selection: 'multi' })">新增二级组</button>
            </div>
          </div>

          <div class="grid gap-4 md:grid-cols-4">
            <div class="rounded-2xl border border-dashed border-soft bg-white p-3 text-xs text-secondary md:col-span-1">
              <div class="mb-2 text-sm font-semibold text-primary">怎么搭建编码方案？</div>
              <ul class="list-disc space-y-1 pl-4">
                <li>每个组对应一个要分析的字段，如“信息类别”或“议题编码”。建议把组名写清楚，方便后续统计。</li>
                <li>“一级”字段适合简单分类，若要细分建议设为“二级编码”。可同时添加多个一级和二级组。</li>
                <li>单选字段场景如“信息类别”、“报道体裁”，请选择“单选（唯一）”；类似“议题”需多选的请选择“多选（可多项）”。</li>
                <li>如果某些情况必须选，或者有需要特殊处理的例外，可以写到“边界情况”里，让AI优先遵循。</li>
              </ul>
            </div>
            <div class="md:col-span-3 space-y-4">
              <div
                v-for="(block, blockIndex) in builder.blocks"
                :key="block.id"
                class="rounded-3xl border border-soft bg-white p-5"
              >
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div class="flex items-center gap-2 text-sm font-semibold text-primary">
                        <Squares2X2Icon class="h-4 w-4 text-brand-600" />
                    <span>字段 {{ blockIndex + 1 }}</span>
                    <span class="text-xs font-normal text-secondary">&middot; {{ block.title || '未命名组' }}</span>
                  </div>
                  <button
                    type="button"
                    class="inline-flex items-center gap-1 text-xs font-semibold text-muted hover:text-danger"
                    @click="removeBlock(blockIndex)"
                  >
                    <TrashIcon class="h-3 w-3" />
                    删除组
                  </button>
                </div>
                <div class="mt-4 grid gap-3 md:grid-cols-[minmax(220px,1.5fr)_repeat(2,minmax(160px,1fr))_minmax(160px,0.9fr)]">
                  <label class="flex flex-col gap-1 text-xs text-muted">
                    <span>组名</span>
                    <input
                      v-model="block.title"
                      type="text"
                      class="h-10 rounded-2xl border border-soft bg-surface px-3 text-sm font-medium text-primary focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                      placeholder="如 信息类别 / 议题编码"
                    />
                  </label>
                  <label class="flex flex-col gap-1 text-xs text-muted">
                    <span>编码层级</span>
                    <select
                      v-model="block.level"
                      class="h-10 rounded-2xl border border-soft bg-surface px-3 text-sm font-medium focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                    >
                      <option value="level1">一级编码</option>
                      <option value="level2">二级编码</option>
                    </select>
                  </label>
                  <label class="flex flex-col gap-1 text-xs text-muted">
                    <span>选项类型</span>
                    <select
                      v-model="block.selection"
                      class="h-10 rounded-2xl border border-soft bg-surface px-3 text-sm font-medium focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                    >
                      <option value="single">单选（唯一）</option>
                      <option value="multi">多选（可多项）</option>
                    </select>
                  </label>
                  <div class="flex flex-col justify-end gap-2">
                    <button type="button" class="btn-ghost h-10 px-3 text-sm font-medium" @click="addCode(block)">
                      <PlusSmallIcon class="mr-1 h-4 w-4" />
                      快速添加
                    </button>
                  </div>
                </div>

                <div class="mt-4 rounded-2xl border border-soft bg-surface-muted/60 p-4">
                  <div class="mb-3 flex flex-wrap items-center justify-between gap-3 text-xs text-muted">
                    <div class="flex items-center gap-2 text-sm text-primary">
                      <span>编码项（逐条添加，可混排）</span>
                      <span class="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-secondary">共 {{ block.codes.length }} 项</span>
                    </div>
                    <div class="flex flex-wrap items-center gap-2 text-sm">
                      <button v-if="block.level === 'level2'" type="button" class="btn-ghost h-9 px-3 text-sm" @click="addGroup(block)">
                        <PlusSmallIcon class="mr-1 h-4 w-4" />
                        新增大类
                      </button>
                      <button v-if="block.level !== 'level2'" type="button" class="btn-ghost h-9 px-3 text-sm" @click="addCode(block)">
                        <PlusSmallIcon class="mr-1 h-4 w-4" />
                        新增编码
                      </button>
                    </div>
                  </div>
                  <p v-if="!block.codes.length" class="text-xs text-muted">请为该组添加编码项。</p>
                  <div v-else>
                    <div v-if="shouldGroupBlock(block)" class="space-y-3">
                      <div
                        v-for="group in getGroupedCodes(block)"
                        :key="group.key"
                        class="rounded-2xl border border-soft bg-white p-3"
                      >
                        <div class="mb-2 flex flex-wrap items-center justify-between gap-3 text-xs font-semibold text-muted">
                          <div class="flex flex-wrap items-center gap-2">
                            <span v-if="group.prefix" class="text-[10px] text-secondary">L{{ group.prefix }}</span>
                            <input
                              :value="group.rawTitle"
                              class="h-9 w-40 rounded-2xl border border-soft bg-surface px-3 text-sm font-semibold text-primary focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                              placeholder="填写大类名称"
                              @input="updateGroupTitle(block, group, $event.target.value)"
                            />
                          </div>
                          <div class="flex flex-wrap items-center gap-2 font-semibold text-muted">
                            <span>{{ group.codes.length }} 项</span>
                            <button
                              type="button"
                              class="btn-ghost h-9 px-3 text-sm"
                              @click="addCode(block, { group: group.rawTitle || group.title || '' })"
                            >
                              <PlusSmallIcon class="mr-1 h-4 w-4" />
                              新增子项
                            </button>
                            <button
                              type="button"
                              class="btn-ghost h-9 px-3 text-sm text-danger"
                              @click="toggleGroupDelete(block, group)"
                            >
                              删除大类
                            </button>
                          </div>
                        </div>
                        <div
                          v-if="block.pendingGroupDelete === group.key"
                          class="mb-3 rounded-xl border border-soft bg-surface px-3 py-2 text-xs text-danger"
                        >
                          <p>确认删除「{{ group.rawTitle || group.title }}」及其 {{ group.codes.length }} 个子项？</p>
                          <div class="mt-2 flex flex-wrap gap-2">
                            <button
                              type="button"
                              class="btn-primary px-3 py-1 text-xs"
                              @click="confirmGroupDelete(block, group)"
                            >
                              确认删除
                            </button>
                            <button type="button" class="btn-ghost px-3 py-1 text-xs" @click="cancelGroupDelete(block)">取消</button>
                          </div>
                        </div>
                        <div class="grid gap-3 md:grid-cols-2">
                          <div
                            v-for="code in group.codes"
                            :key="code.id"
                            class="rounded-2xl border border-soft bg-white px-3 py-2"
                          >
                            <div class="flex flex-wrap items-center gap-2 text-sm">
                              <span class="rounded-full bg-surface-muted px-2 py-1 text-[11px] font-semibold text-muted">{{ block.level === 'level1' ? 'L1' : 'L2' }}</span>
                              <input
                                v-model="code.code"
                                type="text"
                                class="h-9 w-24 rounded-xl border border-soft px-2 text-sm focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                                placeholder="编码"
                              />
                              <input
                                v-model="code.label"
                                type="text"
                                class="h-9 flex-1 rounded-xl border border-soft px-3 text-sm focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                                placeholder="描述，如 青少年 / 观点性报道"
                              />
                              <button
                                type="button"
                                class="text-xs text-muted hover:text-rose-500"
                                @click="removeCode(block, block.codes.indexOf(code))"
                              >
                                删除
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div v-else class="grid gap-3 md:grid-cols-2">
                      <div
                        v-for="(code, codeIndex) in block.codes"
                        :key="code.id"
                        class="flex flex-wrap items-center gap-2 rounded-2xl border border-soft bg-white px-3 py-2 text-sm"
                      >
                        <span class="rounded-full bg-surface-muted px-2 py-1 text-[11px] font-semibold text-muted">{{ block.level === 'level1' ? 'L1' : 'L2' }}</span>
                        <input
                          v-model="code.code"
                          type="text"
                          class="h-9 w-24 rounded-xl border border-soft px-2 text-sm focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                          placeholder="编码"
                        />
                        <input
                          v-model="code.label"
                          type="text"
                          class="h-9 flex-1 rounded-xl border border-soft px-3 text-sm focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                          placeholder="描述，如 青少年 / 观点性报道"
                        />
                        <input
                          v-if="block.level === 'level2'"
                          v-model="code.group"
                          type="text"
                          class="h-9 w-40 rounded-xl border border-soft px-3 text-sm focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                          placeholder="所属大类"
                        />
                        <button
                          type="button"
                          class="text-xs text-muted hover:text-rose-500"
                          @click="removeCode(block, codeIndex)"
                        >
                          删除
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <p v-if="!builder.blocks.length" class="text-xs text-muted">当前为空白方案，请先新增一级组/二级组。</p>
            </div>
          </div>

          <div class="grid gap-4 rounded-3xl border border-soft bg-white p-4 text-sm text-secondary">
            <label class="space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-xs font-semibold text-muted">特定情况提示</span>
                <button type="button" class="btn-ghost px-2 py-1 text-[11px]" @click="applyEdgeCases">填入常用规则</button>
              </div>
              <textarea
                v-model="builder.edgeCases"
                rows="5"
                class="w-full rounded-2xl border border-dashed border-soft bg-surface px-3 py-2 text-sm leading-relaxed text-primary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                placeholder="请输入强制规则与特定情况处理，这将更好地指导AI进行编码。"
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
              <span class="text-[11px] text-muted">指导提示词</span>
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
              <span class="text-[11px] text-muted">编码提示词</span>
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
            保存后可用于内容分析；未填写时会保留已有配置。
          </span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { AdjustmentsHorizontalIcon, ArrowPathIcon, Squares2X2Icon, TrashIcon, PlusSmallIcon } from '@heroicons/vue/24/outline'
import { useApiBase } from '../../../composables/useApiBase'
import { contentAnalysisPreset } from '../../../data/contentAnalysisPreset'

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

const extractGroupFromLabel = (label = '') => {
  if (!label) return ''
  const separators = ['·', '：', ':']
  for (const separator of separators) {
    if (label.includes(separator)) {
      return label.split(separator)[0].trim()
    }
  }
  return ''
}

const getGroupTitleFromCode = (code = {}) => (code.group || '').trim() || extractGroupFromLabel(code.label || '')

const getCodePrefix = (code = {}) => {
  const value = String(code.code || '').trim()
  if (!value) return ''
  if (value.includes('-')) return value.split('-')[0].trim()
  const numeric = value.match(/^\d+/)
  return numeric ? numeric[0] : ''
}

const buildGroupMeta = (block, code) => {
  const rawTitle = getGroupTitleFromCode(code)
  const prefix = getCodePrefix(code)
  const key = rawTitle || prefix || '未分组'
  const displayTitle =
    rawTitle && prefix ? `${prefix}. ${rawTitle}` : rawTitle || (prefix ? `${prefix}` : '未分组')
  return {
    key: `${block.id}-${key}`,
    title: displayTitle,
    prefix,
    rawTitle,
    codes: []
  }
}

const getGroupedCodes = (block) => {
  if (!block?.codes?.length) return []
  const order = []
  const map = new Map()
  block.codes.forEach((code) => {
    const rawTitle = getGroupTitleFromCode(code)
    const prefix = getCodePrefix(code)
    const key = rawTitle || prefix || '未分组'
    if (!map.has(key)) {
      map.set(key, buildGroupMeta(block, code))
      order.push(map.get(key))
    }
    map.get(key).codes.push(code)
  })
  return order
}

const shouldGroupBlock = (block) => block.level === 'level2' && getGroupedCodes(block).length > 0

const getGroupNameOptions = (block) => {
  if (!block?.codes?.length) return []
  const names = []
  getGroupedCodes(block).forEach((group) => {
    const candidate = group.rawTitle || group.title
    if (candidate && !names.includes(candidate)) {
      names.push(candidate)
    }
  })
  return names
}

const updateGroupTitle = (block, group, nextTitle) => {
  const value = nextTitle.trim()
  group.codes.forEach((code) => {
    code.group = value
  })
}

const nextGroupName = (block) => {
  const existing = getGroupNameOptions(block)
  const base = '新大类'
  if (!existing.includes(base)) return base
  let idx = existing.length + 1
  let candidate = `${base}${idx}`
  while (existing.includes(candidate)) {
    idx += 1
    candidate = `${base}${idx}`
  }
  return candidate
}

const addGroup = (block) => {
  const title = nextGroupName(block)
  block.codes.push(createCode({ group: title }))
}

const toggleGroupDelete = (block, group) => {
  const target = ensureBlockMeta(block)
  target.pendingGroupDelete = target.pendingGroupDelete === group.key ? '' : group.key
}

const cancelGroupDelete = (block) => {
  ensureBlockMeta(block).pendingGroupDelete = ''
}

const codeMatchesGroup = (code, group) => {
  const rawTitle = (group.rawTitle || '').trim()
  if (rawTitle) {
    return (code.group || '').trim() === rawTitle
  }
  if (group.prefix) {
    return getCodePrefix(code) === group.prefix
  }
  return false
}

const confirmGroupDelete = (block, group) => {
  for (let i = block.codes.length - 1; i >= 0; i -= 1) {
    if (codeMatchesGroup(block.codes[i], group)) {
      block.codes.splice(i, 1)
    }
  }
  cancelGroupDelete(block)
}

const draftKeyForTopic = (topic) => `content-prompt-draft:${topic}`

const uuid = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `id-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

const createCode = (item = {}) => ({
  id: uuid(),
  code: item.code || '',
  label: item.label || '',
  group: item.group || item.category || ''
})

const ensureBlockMeta = (block) => {
  if (!Object.prototype.hasOwnProperty.call(block, 'pendingGroupDelete')) {
    block.pendingGroupDelete = ''
  }
  return block
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
  const presetCodes = Array.isArray(preset?.codes)
    ? preset.codes
    : Array.isArray(preset?.groups)
      ? preset.groups.flatMap((group) =>
          (group.codes || []).map((code) => ({
            ...code,
            group: code.group || group.title || group.name || ''
          }))
        )
      : []
  const codes = presetCodes.map((item) => createCode(item))
  builder.blocks.push({
    id: uuid(),
    title: preset?.title || '',
    selection: preset?.selection || 'single',
    level: preset?.level || 'level1',
    codes
  })
  ensureBlockMeta(builder.blocks[builder.blocks.length - 1])
}

const removeBlock = (index) => {
  builder.blocks.splice(index, 1)
}

const addCode = (block, defaults = {}) => {
  block.codes.push(createCode(defaults))
}

const removeCode = (block, index) => {
  block.codes.splice(index, 1)
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

const escapeJsonString = (input) => String(input ?? '').replace(/"/g, "'")

const formatSchemaSample = () => {
  if (!builder.blocks.length) {
    return '{"字段1": "编码值"}'
  }
  const entries = builder.blocks.map((block, idx) => {
    const title = escapeJsonString((block.title || '').trim() || `字段${idx + 1}`)
    const codes = block.codes
      .map((c) => escapeJsonString((c.code || c.label || '').trim()))
      .filter(Boolean)
    if (block.selection === 'single') {
      const sample = codes[0] || '编码值'
      return `"${title}": "${sample}"`
    }
    const samples = codes.slice(0, 2)
    while (samples.length < 2) {
      samples.push(`编码值${samples.length + 1}`)
    }
    return `"${title}": [${samples.map((s) => `"${s}"`).join(', ')}]`
  })
  return `{ ${entries.join(', ')} }`
}

const summarizeFieldSettings = () => {
  if (!builder.blocks.length) return ''
  return builder.blocks
    .map((block, idx) => {
      const title = (block.title || '').trim() || `字段${idx + 1}`
      const levelText = block.level === 'level1' ? '一级' : '二级'
      const selectionText = block.selection === 'single' ? '单选' : '多选'
      return `${title}（${levelText}·${selectionText}）`
    })
    .join('； ')
}

const formatBlockCodesForPrompt = (block) => {
  const entries = block.codes.filter((c) => c.code || c.label)
  if (!entries.length) return '请补充编码'
  if (block.level !== 'level2') {
    return entries.map((c) => `${c.code || ''} ${c.label || ''}`.trim()).join('； ')
  }
  const grouped = getGroupedCodes(block)
  if (!grouped.length) {
    return entries.map((c) => `${c.code || ''} ${c.label || ''}`.trim()).join('； ')
  }
  return grouped
    .map((group) => {
      const list = group.codes
        .filter((c) => c.code || c.label)
        .map((c) => `${c.code || ''} ${c.label || ''}`.trim())
        .join('； ')
      return `${group.title}：${list || '请补充编码'}`
    })
    .join('\n')
}

const buildPrompts = () => {
  if (!builder.blocks.length) {
    promptState.error = '请至少创建一组编码'
    return
  }

  const schemaSample = formatSchemaSample()
  const fieldNotes = summarizeFieldSettings()
  const systemBase =
    'You are a structured content-coding assistant. Always return a valid JSON that follows: ' +
    `${schemaSample}` +
    (fieldNotes ? `。字段设置：${fieldNotes}` : '')

  const parts = ['Coding rules（请严格按要求执行，勿新增编码）', '']
  builder.blocks.forEach((block, idx) => {
    const heading = `${idx + 1}. ${block.title || '未命名组'}（${block.level === 'level1' ? '一级' : '二级'}，${block.selection === 'single' ? '单选' : '多选'}）`
    parts.push(heading)
    parts.push(formatBlockCodesForPrompt(block))
    parts.push('')
  })
  parts.push('特定情况提示（拿不准时参照下列示例）')
  parts.push(builder.edgeCases || '无')

  promptState.system_prompt = systemBase
  promptState.analysis_prompt = parts.join('\n')
  promptState.message = '已根据方案生成草稿，可下方微调后保存。'
  saveDraft()
}

const loadPresetExample = () => {
  builder.blocks = []
  ;(contentAnalysisPreset.blocks || []).forEach((p) => addBlock(p))
  builder.edgeCases = contentAnalysisPreset.edgeCases || ''
  buildPrompts()
  promptState.message = contentAnalysisPreset.description || '已载入示例，可直接保存或继续调整。'
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
      codes: b.codes.map((c) => ({ code: c.code, label: c.label, group: c.group }))
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

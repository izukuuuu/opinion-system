<template>
  <section class="card-surface space-y-6 p-6">
    <header class="settings-page-header">
      <p class="settings-page-eyebrow">数据导入</p>
      <h2 class="settings-page-title">列名映射</h2>
      <p class="settings-page-desc">
        维护统一别名字典。把同一个字段可能出现的列名加进来，后端会按这份映射继续识别。
      </p>
    </header>

    <div v-if="feedback.error" class="settings-message-error">
      {{ feedback.error }}
    </div>
    <div v-if="feedback.success" class="settings-message-success">
      {{ feedback.success }}
    </div>

    <section class="settings-section settings-section-split space-y-5">
      <header class="settings-toolbar">
        <div class="settings-section-header">
          <h3 class="settings-section-title">标准字段与别名</h3>
          <p class="settings-section-desc">只维护统一别名，不区分数据源。</p>
        </div>
      </header>

      <div class="rounded-2xl border border-soft bg-surface-muted/50 px-4 py-3 text-sm text-secondary">
        每张小卡代表一个系统字段。卡片里的标签是当前已识别的别名，下面输入框用于继续补充。
      </div>

      <div v-if="state.loading && !rows.length" class="settings-empty-state py-10">
        正在加载列名映射...
      </div>

      <div v-else class="grid gap-4 lg:grid-cols-2">
        <article
          v-for="(row, index) in rows"
          :key="row.key"
          class="rounded-3xl border border-soft bg-surface-muted/50 p-4"
        >
          <div class="space-y-3">
            <div class="space-y-1.5">
              <div class="flex flex-wrap items-center gap-2">
                <h3 class="text-sm font-semibold text-primary">{{ row.label }}</h3>
                <code class="rounded-full bg-white px-2.5 py-0.5 text-[11px] text-secondary ring-1 ring-black/5">
                  {{ row.name }}
                </code>
              </div>
              <p class="text-xs leading-5 text-secondary">{{ row.description }}</p>
            </div>

            <div class="space-y-2.5">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <span class="text-xs font-semibold text-secondary">已收录别名</span>
                <span class="text-[11px] text-muted">例如：{{ exampleText(row.name) }}</span>
              </div>

              <div v-if="row.aliases.length" class="flex flex-wrap gap-2">
                <span
                  v-for="alias in row.aliases"
                  :key="`${row.key}-${alias}`"
                  class="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1 text-[11px] font-medium text-brand-700"
                >
                  {{ alias }}
                  <button
                    type="button"
                    class="text-brand-500 transition hover:text-brand-700"
                    @click="removeAlias(index, alias)"
                  >
                    ×
                  </button>
                </span>
              </div>
              <p v-else class="text-[11px] text-muted">当前还没有设置别名。</p>

              <div class="flex flex-wrap gap-2">
                <input
                  v-model.trim="row.draftAlias"
                  type="text"
                  class="input h-11 flex-1 min-w-[180px]"
                  placeholder="输入列名后回车"
                  @keyup.enter="addAlias(index)"
                />
                <button
                  type="button"
                  class="btn-secondary px-4 py-2 text-sm"
                  @click="addAlias(index)"
                >
                  添加
                </button>
              </div>
            </div>
          </div>
        </article>
      </div>
    </section>

    <div class="settings-action-row">
      <p class="text-xs text-muted">
        保存后，新导入文件会直接使用这份统一别名字典。
      </p>
      <div class="flex flex-wrap gap-3">
        <button
          type="button"
          class="btn-secondary px-4 py-2 text-sm"
          :disabled="state.loading || state.saving"
          @click="loadSettings"
        >
          重新加载
        </button>
        <button
          type="button"
          class="btn-primary px-6 py-2.5 text-sm"
          :disabled="state.loading || state.saving"
          @click="saveSettings"
        >
          {{ state.saving ? '保存中...' : '保存列名映射' }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useApiBase } from '../../composables/useApiBase'

const { callApi } = useApiBase()

const DEFAULT_STANDARD_FIELDS = [
  { key: 'title', label: '标题', description: '文章或帖文标题' },
  { key: 'summary', label: '摘要', description: '摘要、导语、简述' },
  { key: 'ocr', label: '图片文字', description: 'OCR 或图片提取文字' },
  { key: 'content', label: '正文', description: '正文、内容主体' },
  { key: 'platform', label: '平台', description: '发布平台、站点或 App 名称' },
  { key: 'author', label: '作者', description: '作者、账号、博主、公众号' },
  { key: 'published_at', label: '发布时间', description: '发布时间或原始时间字段' },
  { key: 'url', label: '链接', description: '原文链接、URL' },
  { key: 'region', label: '地域', description: '属地、发文 IP、命中地域' },
  { key: 'hit_words', label: '命中词', description: '关键词、命中词' },
  { key: 'polarity', label: '情感倾向', description: '倾向性、情感' },
  { key: 'like_count', label: '点赞数', description: '点赞、点赞量' },
  { key: 'comment_count', label: '评论数', description: '评论、评论量' },
  { key: 'favorite_count', label: '收藏数', description: '收藏、收藏量' },
  { key: 'share_count', label: '转发数', description: '转发、分享、转发量' },
]

const EXAMPLE_MAP = {
  title: '标题、文章标题、帖文标题',
  summary: '摘要、导语、简介',
  ocr: 'OCR、图片文字',
  content: '正文、内容、文本',
  platform: '平台、发布平台、app名称',
  author: '作者、账号、博主',
  published_at: '发布时间、时间、publish_time',
  url: '链接、URL、原文链接',
  region: '发文IP属地、属地、地域',
  hit_words: '命中词、关键词',
  polarity: '倾向性、情感',
  like_count: '点赞数、点赞量、likes',
  comment_count: '评论数、评论量、comments',
  favorite_count: '收藏数、收藏量、favorites',
  share_count: '转发数、转发量、shares',
}

const state = reactive({
  loading: false,
  saving: false,
})

const feedback = reactive({
  success: '',
  error: '',
})

const rows = ref([])

const createRow = (definition, aliases = []) => ({
  key: `${definition.key}-${Math.random().toString(36).slice(2, 8)}`,
  name: definition.key,
  label: definition.label,
  description: definition.description,
  aliases: Array.isArray(aliases) ? aliases.map((item) => String(item || '').trim()).filter(Boolean) : [],
  draftAlias: '',
})

const clearFeedback = () => {
  feedback.success = ''
  feedback.error = ''
}

const normalizeAliasList = (aliases) => {
  const seen = new Set()
  return aliases
    .map((item) => String(item || '').trim())
    .filter((item) => {
      if (!item) return false
      const key = item.toLocaleLowerCase()
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
}

const buildRows = (fieldAlias, standardFields) => {
  const definitions = Array.isArray(standardFields) && standardFields.length ? standardFields : DEFAULT_STANDARD_FIELDS
  const aliasMap = fieldAlias && typeof fieldAlias === 'object' ? fieldAlias : {}
  const baseRows = definitions.map((definition) => createRow(definition, aliasMap[definition.key] || []))

  const knownKeys = new Set(definitions.map((item) => item.key))
  const extraRows = Object.entries(aliasMap)
    .filter(([key]) => !knownKeys.has(key))
    .map(([key, aliases]) =>
      createRow(
        {
          key,
          label: key,
          description: '后端已存在的扩展字段',
        },
        aliases
      )
    )

  return [...baseRows, ...extraRows]
}

const loadSettings = async () => {
  state.loading = true
  clearFeedback()
  try {
    const response = await callApi('/api/settings/channels/aliases', { method: 'GET' })
    const payload = response?.data || {}
    rows.value = buildRows(payload.field_alias, payload.standard_fields)
  } catch (error) {
    feedback.error = error instanceof Error ? error.message : '读取列名映射失败'
  } finally {
    state.loading = false
  }
}

const addAlias = (index) => {
  const row = rows.value[index]
  if (!row) return
  const nextAlias = String(row.draftAlias || '').trim()
  if (!nextAlias) return
  row.aliases = normalizeAliasList([...row.aliases, nextAlias])
  row.draftAlias = ''
}

const removeAlias = (index, alias) => {
  const row = rows.value[index]
  if (!row) return
  row.aliases = row.aliases.filter((item) => item !== alias)
}

const saveSettings = async () => {
  state.saving = true
  clearFeedback()
  try {
    const fieldAlias = {}
    rows.value.forEach((row) => {
      fieldAlias[row.name] = normalizeAliasList(row.aliases)
    })
    await callApi('/api/settings/channels/aliases', {
      method: 'PUT',
      body: JSON.stringify({ field_alias: fieldAlias }),
    })
    feedback.success = '列名映射已保存'
    await loadSettings()
  } catch (error) {
    feedback.error = error instanceof Error ? error.message : '保存列名映射失败'
  } finally {
    state.saving = false
  }
}

const exampleText = (fieldKey) => EXAMPLE_MAP[fieldKey] || '输入你文件里实际出现过的列名'

onMounted(() => {
  loadSettings()
})
</script>

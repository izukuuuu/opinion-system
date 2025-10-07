<template>
  <section class="database-view">
    <header class="database-view__header">
      <CircleStackIcon class="database-view__icon" />
      <div class="database-view__title-group">
        <h1>数据库概览</h1>
        <p>实时查看后端数据库的连接信息、库表结构与数据量，快速验证配置是否正确。</p>
      </div>
      <button type="button" class="database-view__refresh" @click="refresh" :disabled="loading">
        <ArrowPathIcon class="database-view__refresh-icon" :class="{ 'is-spinning': loading }" />
        {{ loading ? '刷新中…' : '刷新数据' }}
      </button>
    </header>

    <section v-if="error" class="database-view__alert" role="alert">
      <p>{{ error }}</p>
      <p class="database-view__alert-hint">请检查后端服务与数据库配置，稍后再试。</p>
    </section>

    <section v-if="hasData" class="database-view__overview">
      <article class="card">
        <header>
          <h2>连接信息</h2>
          <p>从配置文件推断出的数据库连接要素。</p>
        </header>
        <dl class="database-view__details">
          <div v-for="detail in connectionDetails" :key="detail.label">
            <dt>{{ detail.label }}</dt>
            <dd>{{ detail.value }}</dd>
          </div>
        </dl>
      </article>

      <article class="card">
        <header>
          <h2>数据量统计</h2>
          <p>帮助快速了解业务数据规模。</p>
        </header>
        <ul class="database-view__stats">
          <li>
            <span class="database-view__stats-label">业务数据库</span>
            <strong>{{ summaryStats.databaseCount }}</strong>
          </li>
          <li>
            <span class="database-view__stats-label">总表数</span>
            <strong>{{ summaryStats.tableCount }}</strong>
          </li>
          <li>
            <span class="database-view__stats-label">已统计行数</span>
            <strong>{{ summaryStats.rowCount }}</strong>
          </li>
        </ul>
        <footer class="database-view__footer" v-if="queriedAt">
          <ServerStackIcon class="database-view__footer-icon" />
          <span>最近一次查询：{{ queriedAt }}</span>
        </footer>
      </article>
    </section>

    <section v-if="loading" class="database-view__skeleton">
      <div class="database-view__skeleton-card" v-for="index in 2" :key="index"></div>
    </section>

    <section v-if="hasData" class="database-view__databases">
      <article v-for="database in databases" :key="database.name" class="database-card">
        <header class="database-card__header">
          <h3>{{ database.name }}</h3>
          <p>{{ database.table_count }} 张表 · {{ formatNumber(database.total_rows) }} 行</p>
        </header>
        <ul class="database-card__tables">
          <li
            v-for="table in database.tables"
            :key="table.name"
            :class="['database-card__table', { 'database-card__table--error': table.error }]"
          >
            <span class="database-card__table-name">{{ table.name }}</span>
            <span v-if="table.error" class="database-card__table-error">{{ table.error }}</span>
            <span v-else class="database-card__table-count">{{ formatNumber(table.record_count) }} 行</span>
          </li>
        </ul>
        <p v-if="!database.tables.length" class="database-card__empty">该库暂无业务表。</p>
      </article>
    </section>

    <p v-if="!loading && !hasData && !error" class="database-view__empty">
      未检索到业务数据库，请确认配置是否正确。
    </p>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ArrowPathIcon, CircleStackIcon, ServerStackIcon } from '@heroicons/vue/24/outline'

import { useBackendClient } from '../composables/useBackendClient'

const { callApi } = useBackendClient()

const loading = ref(false)
const error = ref('')
const payload = ref(null)

const numberFormatter = new Intl.NumberFormat('zh-CN')
const formatNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return numberFormatter.format(Number(value))
}

const queriedAt = computed(() => {
  if (!payload.value?.queried_at) return ''
  try {
    return new Date(payload.value.queried_at).toLocaleString()
  } catch (err) {
    return payload.value.queried_at
  }
})

const connectionDetails = computed(() => {
  const connection = payload.value?.connection ?? {}
  const items = [
    { label: '驱动', value: connection.driver || '未知' },
    { label: '主机', value: connection.host || '未配置' },
    { label: '端口', value: connection.port || '未配置' },
    { label: '默认数据库', value: connection.database || '未配置' },
    { label: '用户名', value: connection.username || '未配置' },
    {
      label: '密码配置',
      value: connection.has_password ? '已配置' : '未配置'
    }
  ]
  return items.filter((item) => item.value !== undefined && item.value !== null)
})

const summaryStats = computed(() => {
  const summary = payload.value?.summary ?? {}
  return {
    databaseCount: summary.database_count ? formatNumber(summary.database_count) : '0',
    tableCount: summary.table_count ? formatNumber(summary.table_count) : '0',
    rowCount: summary.row_count ? formatNumber(summary.row_count) : '0'
  }
})

const databases = computed(() => payload.value?.databases ?? [])
const hasData = computed(() => (databases.value?.length ?? 0) > 0)

const refresh = async () => {
  loading.value = true
  error.value = ''
  try {
    const response = await callApi('/api/query', { method: 'POST', body: JSON.stringify({}) })
    payload.value = response.data ?? null
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    payload.value = null
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<style scoped>
.database-view {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  padding: 2.5rem;
  background: rgba(255, 255, 255, 0.92);
  border-radius: 28px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  box-shadow: 0 25px 60px -30px rgba(15, 23, 42, 0.35);
}

.database-view__header {
  display: flex;
  align-items: center;
  gap: 1.75rem;
}

.database-view__icon {
  width: 3rem;
  height: 3rem;
  color: #0f172a;
}

.database-view__title-group h1 {
  margin: 0;
  font-size: 2rem;
  font-weight: 700;
}

.database-view__title-group p {
  margin: 0.35rem 0 0;
  color: #475569;
  max-width: 640px;
}

.database-view__refresh {
  margin-left: auto;
  border: none;
  background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
  color: #fff;
  padding: 0.65rem 1.3rem;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-weight: 600;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.database-view__refresh:disabled {
  opacity: 0.7;
  cursor: not-allowed;
  box-shadow: none;
}

.database-view__refresh:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: 0 15px 30px rgba(37, 99, 235, 0.28);
}

.database-view__refresh-icon {
  width: 1.25rem;
  height: 1.25rem;
}

.database-view__refresh-icon.is-spinning {
  animation: spin 1s linear infinite;
}

.database-view__alert {
  background: rgba(220, 38, 38, 0.08);
  border: 1px solid rgba(220, 38, 38, 0.18);
  border-radius: 18px;
  padding: 1.25rem 1.5rem;
  color: #b91c1c;
}

.database-view__alert p {
  margin: 0.25rem 0;
}

.database-view__alert-hint {
  color: rgba(185, 28, 28, 0.8);
}

.database-view__overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1.75rem;
}

.database-view__details {
  margin: 0;
  display: grid;
  gap: 1rem;
}

.database-view__details div {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  padding-bottom: 0.6rem;
}

.database-view__details dt {
  margin: 0;
  font-weight: 600;
  color: #1f2937;
}

.database-view__details dd {
  margin: 0;
  color: #475569;
}

.database-view__stats {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.database-view__stats-label {
  color: #475569;
  font-size: 0.9rem;
}

.database-view__stats strong {
  display: block;
  font-size: 1.5rem;
  font-weight: 700;
  color: #111827;
}

.database-view__footer {
  margin-top: 1.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #475569;
}

.database-view__footer-icon {
  width: 1.25rem;
  height: 1.25rem;
}

.database-view__skeleton {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1.5rem;
}

.database-view__skeleton-card {
  height: 140px;
  border-radius: 22px;
  background: linear-gradient(90deg, rgba(226, 232, 240, 0.6), rgba(241, 245, 249, 0.9), rgba(226, 232, 240, 0.6));
  background-size: 200% 100%;
  animation: shimmer 1.4s ease-in-out infinite;
}

.database-view__databases {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1.75rem;
}

.database-card {
  background: rgba(255, 255, 255, 0.92);
  border-radius: 24px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  padding: 1.5rem 1.75rem;
  box-shadow: 0 22px 48px -28px rgba(15, 23, 42, 0.32);
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
}

.database-card__header h3 {
  margin: 0;
  font-size: 1.3rem;
  font-weight: 700;
}

.database-card__header p {
  margin: 0.35rem 0 0;
  color: #475569;
}

.database-card__tables {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.database-card__table {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.6rem 0.75rem;
  background: rgba(15, 23, 42, 0.03);
  border-radius: 14px;
  align-items: baseline;
}

.database-card__table-name {
  font-weight: 600;
  color: #1f2937;
}

.database-card__table-count {
  color: #2563eb;
  font-weight: 600;
}

.database-card__table--error {
  border: 1px solid rgba(220, 38, 38, 0.25);
  background: rgba(220, 38, 38, 0.05);
}

.database-card__table-error {
  color: #b91c1c;
  font-weight: 600;
  text-align: right;
}

.database-card__empty {
  margin: 0;
  color: #64748b;
  font-style: italic;
}

.database-view__empty {
  margin: 0;
  text-align: center;
  color: #64748b;
}

@keyframes shimmer {
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 640px) {
  .database-view {
    padding: 1.75rem;
    border-radius: 22px;
  }

  .database-view__header {
    flex-direction: column;
    align-items: flex-start;
  }

  .database-view__refresh {
    margin-left: 0;
  }
}
</style>

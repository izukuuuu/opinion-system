<template>
    <div class="space-y-4">
        <section class="card-surface space-y-6 p-6">
            <header class="flex flex-col gap-2">
                <h2 class="text-2xl font-semibold text-primary">运行流体力学分析</h2>
                <p class="text-sm text-secondary">选择专题和时间范围，启动后端流体力学模型计算。</p>
            </header>

            <form class="space-y-5 text-sm" @submit.prevent="runAnalysis">
                <div class="grid gap-4 md:grid-cols-3">
                    <label class="space-y-2 text-secondary">
                        <div class="flex items-center justify-between gap-2">
                            <span class="text-xs font-semibold text-muted">专题 Topic *</span>
                            <button type="button"
                                class="inline-flex items-center gap-1 text-[11px] font-medium text-brand-600 hover:text-brand-700 disabled:cursor-default disabled:opacity-60"
                                :disabled="topicsState.loading" @click="loadTopics">
                                <ArrowPathIcon class="h-3 w-3"
                                    :class="topicsState.loading ? 'animate-spin text-brand-600' : 'text-brand-600'" />
                                <span>{{ topicsState.loading ? '刷新中…' : '刷新专题' }}</span>
                            </button>
                        </div>
                        <select v-model="form.topic" class="input"
                            :disabled="topicsState.loading || !topicOptions.length" required>
                            <option value="" disabled>请选择远程专题</option>
                            <option v-for="option in topicOptions" :key="`fluid-${option}`" :value="option">
                                {{ option }}
                            </option>
                        </select>
                        <p v-if="topicsState.error" class="text-xs text-danger">{{ topicsState.error }}</p>
                    </label>
                    <label class="space-y-2 text-secondary">
                        <span class="text-xs font-semibold text-muted">开始日期 Start *</span>
                        <input v-model="form.start_date" type="date" class="input" required />
                    </label>
                    <label class="space-y-2 text-secondary">
                        <span class="text-xs font-semibold text-muted">结束日期 End *</span>
                        <input v-model="form.end_date" type="date" class="input" required />
                    </label>
                </div>

                <div class="flex flex-wrap gap-3 text-sm">
                    <button type="submit" class="btn-primary" :disabled="loading">
                        <span v-if="loading" class="mr-2 animate-spin">
                            <ArrowPathIcon class="h-4 w-4" />
                        </span>
                        {{ loading ? '计算中...' : '开始计算' }}
                    </button>
                </div>
            </form>

            <div v-if="message"
                :class="['rounded-xl p-4 text-sm', success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700']">
                {{ message }}
                <div v-if="success" class="mt-2">
                    <button class="font-semibold underline"
                        @click="$router.push({ name: 'deep-analysis-fluid-dynamics-view', query: { topic: form.topic, start: form.start_date, end: form.end_date } })">
                        前往查看结果 &rarr;
                    </button>
                </div>
            </div>
        </section>
    </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ArrowPathIcon } from '@heroicons/vue/24/outline'

// Reuse topic loading logic from existing composables or implement simple fetch
const topicsState = reactive({
    loading: false,
    error: null
})
const topicOptions = ref([])
const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'

const loadTopics = async () => {
    topicsState.loading = true
    topicsState.error = null
    try {
        const res = await fetch(`${backendUrl}/api/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ include_counts: false })
        })
        if (!res.ok) throw new Error('Failed to fetch topics')
        const data = await res.json()
        if (data.status === 'ok') {
            // Extract database names
            topicOptions.value = (data.data?.databases || [])
                .map(db => db.name)
                .filter(name => name) // filter empty
        }
    } catch (e) {
        topicsState.error = e.message
    } finally {
        topicsState.loading = false
    }
}

const form = reactive({
    topic: '',
    start_date: '',
    end_date: ''
})

const loading = ref(false)
const message = ref('')
const success = ref(false)

const runAnalysis = async () => {
    loading.value = true
    message.value = ''
    success.value = false

    try {
        const res = await fetch(`${backendUrl}/api/fluid/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(form)
        })
        const data = await res.json()

        if (res.ok && data.status === 'ok') {
            success.value = true
            message.value = '分析计算完成！'
        } else {
            throw new Error(data.message || 'Unknown error')
        }
    } catch (e) {
        message.value = `执行失败: ${e.message}`
    } finally {
        loading.value = false
    }
}

onMounted(() => {
    loadTopics()
})
</script>

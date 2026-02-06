<template>
    <div class="mx-auto max-w-5xl pt-0 pb-12 space-y-6">
        <!-- Configuration Panel -->
        <section class="card-surface space-y-4 p-6">
            <div class="mb-5 flex items-center justify-between">
                <h2 class="text-lg font-semibold text-primary">流体力学配置</h2>
                <button type="button"
                    class="flex items-center gap-1 text-xs text-brand-600 transition-colors hover:text-brand-700 disabled:opacity-50"
                    :disabled="topicsState.loading" @click="loadTopics">
                    <ArrowPathIcon class="h-3 w-3" :class="{ 'animate-spin': topicsState.loading }" />
                    {{ topicsState.loading ? '正在同步专题...' : '刷新同步' }}
                </button>
            </div>

            <form class="space-y-6" @submit.prevent="runAnalysis">
                <div class="grid gap-6 md:grid-cols-3">
                    <!-- Topic Selection -->
                    <div class="space-y-2">
                        <label class="text-xs font-semibold text-muted tracking-wide uppercase">专题 Topic *</label>
                        <div class="relative">
                            <select v-model="form.topic" class="input w-full appearance-none pr-8"
                                :disabled="topicsState.loading || !topicOptions.length" required>
                                <option value="" disabled>请选择远程专题</option>
                                <option v-for="option in topicOptions" :key="`fluid-${option}`" :value="option">
                                    {{ option }}
                                </option>
                            </select>
                            <div class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted">
                                <ChevronUpDownIcon class="h-4 w-4" />
                            </div>
                        </div>
                        <p v-if="topicsState.error" class="text-xs text-danger">{{ topicsState.error }}</p>
                    </div>

                    <!-- Date Range -->
                    <div class="col-span-2 space-y-2">
                        <span class="text-xs font-semibold text-muted tracking-wide uppercase">分析时间范围 Date Range
                            *</span>
                        <div class="flex items-center gap-4">
                            <div class="relative flex-1">
                                <input v-model="form.start_date" type="date" class="input w-full" required />
                                <span
                                    class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-bold text-muted uppercase">Start</span>
                            </div>
                            <span class="text-muted">→</span>
                            <div class="relative flex-1">
                                <input v-model="form.end_date" type="date" class="input w-full" required />
                                <span
                                    class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-bold text-muted uppercase">End</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="flex items-center justify-end gap-4 border-t border-soft/50 pt-6">
                    <span v-if="loading" class="text-sm text-brand-600 animate-pulse font-medium">
                        流体模型计算中，请稍候...
                    </span>
                    <button type="submit" class="btn-primary min-w-[150px] py-3 text-base"
                        :disabled="loading || !form.topic">
                        <span v-if="loading" class="flex items-center gap-2">
                            <ArrowPathIcon class="h-5 w-5 animate-spin" />
                            正在计算
                        </span>
                        <span v-else>启动流体力学分析</span>
                    </button>
                </div>
            </form>
        </section>

        <!-- Status Message -->
        <section v-if="message" class="rounded-2xl border p-5"
            :class="success ? 'border-green-200 bg-green-50 text-green-700' : 'border-danger/20 bg-danger/5 text-danger'">
            <div class="flex items-start gap-3">
                <component :is="success ? CheckBadgeIcon : ExclamationCircleIcon" class="h-6 w-6 shrink-0" />
                <div class="space-y-3">
                    <div>
                        <p class="font-bold">{{ success ? '任务执行成功' : '任务运行中止' }}</p>
                        <p class="text-sm mt-0.5">{{ message }}</p>
                    </div>
                    <div v-if="success">
                        <button
                            class="inline-flex items-center gap-2 rounded-full bg-green-600 px-4 py-2 text-sm font-bold text-white transition hover:bg-green-700 active:scale-95"
                            @click="$router.push({ name: 'deep-analysis-fluid-dynamics-view', query: { topic: form.topic, start: form.start_date, end: form.end_date } })">
                            前往仪表盘查看可视化 &rarr;
                        </button>
                    </div>
                </div>
            </div>
        </section>
    </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import {
    ArrowPathIcon,
    ChevronUpDownIcon,
    CheckBadgeIcon,
    ExclamationCircleIcon
} from '@heroicons/vue/24/solid'

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
            topicOptions.value = (data.data?.databases || [])
                .map(db => db.name)
                .filter(name => name)
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
            message.value = '流体动力学模型计算已完成，物理特征指标已成功提取。'
        } else {
            throw new Error(data.message || 'Unknown error occurred during fluid calculation')
        }
    } catch (e) {
        message.value = `计算任务失败: ${e.message}`
    } finally {
        loading.value = false
    }
}

onMounted(() => {
    loadTopics()
})
</script>

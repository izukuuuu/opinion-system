<template>
    <div class="space-y-10">
        <section
            class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-500 to-purple-700 px-6 py-10 text-white sm:px-10">
            <div class="absolute inset-0 opacity-40">
                <div class="absolute -top-28 left-1/3 h-72 w-72 -translate-x-1/2 rounded-full bg-white/25 blur-3xl">
                </div>
                <div class="absolute bottom-0 right-10 h-56 w-56 rounded-full bg-indigo-200/80 blur-3xl"></div>
            </div>
            <div class="relative space-y-6">
                <div class="space-y-4">
                    <p class="text-sm font-semibold uppercase tracking-[0.4em] text-white/70">深度分析</p>
                    <h1 class="text-3xl font-semibold sm:text-4xl">舆论流体力学分析</h1>
                </div>

                <div class="space-y-4">
                    <p class="text-sm text-white/90">
                        基于物理学流体动力学模型，将舆论场视为流体系统，分析其流速、粘度、压力等物理属性，从而揭示舆论传播的深层机制与演化趋势。
                    </p>

                    <div>
                        <p class="mb-2 text-sm font-semibold text-white">核心指标</p>
                        <div class="flex flex-wrap gap-2">
                            <span
                                class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">流速
                                (Information Velocity)</span>
                            <span
                                class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">粘度
                                (Platform Viscosity)</span>
                            <span
                                class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">雷诺数
                                (Reynolds Number)</span>
                            <span
                                class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">涡度
                                (Vorticity)</span>
                            <span
                                class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">压强梯度
                                (Pressure Gradient)</span>
                        </div>
                    </div>
                </div>

                <div class="flex justify-end">
                    <button type="button"
                        class="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-indigo-700 transition hover:bg-gray-50 focus-ring-accent"
                        @click="goToRun">
                        <span
                            class="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-50 text-indigo-700">
                            <PlayCircleIcon class="h-4 w-4" />
                        </span>
                        <span class="text-sm font-semibold">开始分析</span>
                    </button>
                </div>
            </div>
        </section>

        <section class="space-y-6">
            <header class="space-y-2">
                <h2 class="text-2xl font-semibold text-primary">分析流程</h2>
            </header>

            <div class="grid gap-6 md:grid-cols-2">
                <article v-for="step in steps" :key="step.title" class="card-surface flex flex-col gap-4 p-6">
                    <div class="flex items-center gap-3">
                        <span
                            class="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-lg font-semibold text-indigo-600">
                            {{ step.index }}
                        </span>
                        <div>
                            <h3 class="text-lg font-semibold text-primary">{{ step.title }}</h3>
                            <p class="text-sm text-secondary">{{ step.subtitle }}</p>
                        </div>
                    </div>
                    <p class="flex-1 text-sm leading-relaxed text-secondary">
                        {{ step.description }}
                    </p>
                    <button type="button"
                        class="inline-flex items-center gap-2 self-start rounded-full border border-indigo-100 px-4 py-1.5 text-sm font-semibold text-indigo-600 transition hover:bg-indigo-50 focus-ring-accent"
                        @click="router.push(step.route)">
                        <ArrowRightIcon class="h-4 w-4" />
                        前往
                    </button>
                </article>
            </div>
        </section>
    </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import {
    ArrowRightIcon,
    PlayCircleIcon
} from '@heroicons/vue/24/outline'

const router = useRouter()

const goToRun = () => {
    router.push({ name: 'deep-analysis-fluid-dynamics-run' })
}

const steps = [
    {
        index: 1,
        title: '运行分析',
        subtitle: '计算流体力学指标',
        description: '选择专题和时间范围，系统将从后端计算流速、粘度、雷诺数等关键物理指标，并生成分析报告。',
        route: { name: 'deep-analysis-fluid-dynamics-run' }
    },
    {
        index: 2,
        title: '查看结果',
        subtitle: '可视化仪表盘',
        description: '通过五维雷达图、热度曲线、仪表盘等可视化组件，直观展示舆论场的物理状态与演化趋势。',
        route: { name: 'deep-analysis-fluid-dynamics-view' }
    }
]
</script>

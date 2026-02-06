<template>
    <div class="space-y-12 pb-12">
        <!-- Hero Section -->
        <section class="relative overflow-hidden rounded-3xl bg-surface border border-soft p-1">
            <div
                class="relative overflow-hidden rounded-[22px] bg-gradient-to-br from-brand-600 via-brand-700 to-indigo-900 px-6 py-10 text-white sm:px-10 sm:py-12">
                <!-- Abstract background elements -->
                <div class="absolute inset-0 overflow-hidden opacity-20 pointer-events-none">
                    <div class="absolute -top-1/4 -left-1/4 h-[400px] w-[400px] rounded-full bg-white/30 blur-[100px]">
                    </div>
                    <div
                        class="absolute -bottom-1/4 -right-1/4 h-[300px] w-[300px] rounded-full bg-brand-400 blur-[80px]">
                    </div>
                </div>

                <div class="relative z-10 grid gap-8 lg:grid-cols-2 lg:items-center">
                    <div class="space-y-6">
                        <div class="space-y-2">
                            <div
                                class="inline-flex items-center rounded-full bg-white/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-widest text-brand-100 backdrop-blur-md border border-white/10">
                                Computational Linguistics
                            </div>
                            <h1 class="text-3xl font-extrabold tracking-tight sm:text-4xl lg:text-5xl">
                                舆论流体力学分析
                            </h1>
                            <p class="max-w-xl text-base text-brand-50/80 leading-relaxed font-medium">
                                基于物理学流体动力学模型，分析舆论的传播流速、粘度与压力梯度。量化揭示信息的传播动力与演化路径。
                            </p>
                        </div>

                        <div class="flex flex-wrap gap-2 text-[10px]">
                            <span v-for="tag in activeDimensions" :key="tag"
                                class="rounded-full bg-white/10 px-3 py-1 font-semibold text-white backdrop-blur-sm border border-white/5">
                                {{ tag }}
                            </span>
                        </div>

                        <div class="flex flex-wrap items-center gap-3 pt-2">
                            <button type="button"
                                class="inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-brand-800 transition-all active:scale-95 group"
                                @click="goToRun">
                                <PlayIcon class="h-4 w-4 fill-current" />
                                <span class="text-sm font-bold">启动流体动力计算</span>
                            </button>

                            <button type="button"
                                class="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/5 px-5 py-2.5 text-white text-sm transition-all"
                                @click="scrollToProcess">
                                <InformationCircleIcon class="h-4 w-4" />
                                <span>了解流体模型</span>
                            </button>
                        </div>
                    </div>

                    <!-- Feature highlight -->
                    <div class="hidden lg:block">
                        <div class="relative rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-md">
                            <h3 class="mb-3 text-xs font-bold text-brand-200">物理特性指标 (Physical Metrics)</h3>
                            <ul class="space-y-2.5 text-[13px] text-white/70">
                                <li class="flex items-start gap-3">
                                    <div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400"></div>
                                    <span>信息流速 (Velocity)：单位时间内信息穿透的主体密度</span>
                                </li>
                                <li class="flex items-start gap-3">
                                    <div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400"></div>
                                    <span>介质粘度 (Viscosity)：平台环境对传播阻尼的影响系数</span>
                                </li>
                                <li class="flex items-start gap-3">
                                    <div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400"></div>
                                    <span>雷诺数 (Reynolds Num)：判断传播状态属于层流或湍流</span>
                                </li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Workflow Section -->
        <section id="workflow-section" class="space-y-6 scroll-mt-6">
            <div class="text-center space-y-1">
                <h2 class="text-2xl font-bold text-primary tracking-tight">分析流程</h2>
                <p class="mx-auto max-w-xl text-secondary text-sm">
                    将语义数据映射至物理矢量空间，实现舆情演化的动力学建模。
                </p>
            </div>

            <div class="grid gap-5 md:grid-cols-2">
                <article v-for="step in steps" :key="step.title" class="card-surface p-6 transition-all">
                    <div class="flex items-start gap-4">
                        <div
                            class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-soft/50 text-lg font-black text-brand-600 border border-brand-soft">
                            {{ step.index }}
                        </div>
                        <div class="space-y-3">
                            <div class="space-y-0.5">
                                <h3 class="text-lg font-bold text-primary">{{ step.title }}</h3>
                                <p class="text-[11px] font-medium text-brand-600/70">{{ step.subtitle }}</p>
                            </div>
                            <p class="text-sm leading-relaxed text-secondary/80">
                                {{ step.description }}
                            </p>
                            <button type="button"
                                class="inline-flex items-center gap-1 text-sm font-bold text-brand-600 transition hover:underline group"
                                @click="router.push(step.route)">
                                前往执行分析
                                <ArrowSmallRightIcon class="h-4 w-4" />
                            </button>
                        </div>
                    </div>
                </article>
            </div>
        </section>

        <!-- Example Section -->
        <section class="space-y-6">
            <div class="flex items-center justify-between">
                <h2 class="text-xl font-bold text-primary tracking-tight">物理场解读示例</h2>
                <div class="h-px flex-1 bg-soft mx-4 hidden sm:block"></div>
                <span class="text-[10px] font-bold text-muted uppercase tracking-widest">Dynamics & Statics</span>
            </div>

            <div class="card-surface p-6 space-y-8">
                <!-- Mockup: Gauge Results -->
                <div class="rounded-xl border border-soft bg-surface-muted/20 p-5 overflow-hidden relative">
                    <div class="flex items-center gap-3 mb-4">
                        <div class="h-7 w-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white">
                            <BoltIcon class="h-4 w-4" />
                        </div>
                        <h3 class="text-base font-bold text-primary tracking-tight">传播稳定性监测 (Flux Stability)</h3>
                    </div>

                    <div class="grid gap-4 sm:grid-cols-3">
                        <div v-for="stat in [{ l: '雷诺数', v: '1,240' }, { l: '传播压强', v: '0.82 Gpa' }, { l: '演化熵值', v: '4.12' }]"
                            :key="stat.l" class="p-3 bg-white rounded-xl border border-soft">
                            <p class="text-[10px] font-bold text-muted uppercase tracking-wider mb-1">{{ stat.l }}</p>
                            <p class="text-lg font-black text-primary">{{ stat.v }}</p>
                        </div>
                    </div>

                    <div class="mt-6 p-4 rounded-xl bg-white border border-soft">
                        <div class="flex items-center gap-2 mb-2">
                            <div class="h-2 w-2 rounded-full bg-blue-500"></div>
                            <span class="text-[10px] font-bold text-muted uppercase tracking-wider">Physics
                                Interpretation</span>
                        </div>
                        <p class="text-sm text-secondary leading-relaxed">
                            当前雷诺数处于临界区间，暗示传播流态正由均匀层流转向剧烈湍流。粘度系数较低说明平台管控阻力较小，需关注次生舆情爆发点。
                        </p>
                    </div>
                </div>

                <!-- Capability Grid -->
                <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <div v-for="example in examples" :key="example.title"
                        class="flex flex-col rounded-xl border border-soft bg-surface-muted/30 p-4 transition-all">
                        <div class="mb-3 flex items-center justify-between">
                            <div class="flex h-9 w-9 items-center justify-center rounded-lg"
                                :class="example.colorClass">
                                <component :is="example.icon" class="h-4 w-4" />
                            </div>
                            <span class="text-[9px] font-black text-muted opacity-30 uppercase">{{ example.id }}</span>
                        </div>
                        <h4 class="mb-1 text-sm font-bold text-primary">{{ example.title }}</h4>
                        <p class="text-xs leading-relaxed text-secondary/80">
                            {{ example.description }}
                        </p>
                    </div>
                </div>
            </div>
        </section>
    </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import {
    ArrowSmallRightIcon,
    PlayIcon,
    InformationCircleIcon,
    BoltIcon,
    ChartBarIcon,
    GlobeAltIcon,
    BeakerIcon,
    SignalIcon,
    AdjustmentsHorizontalIcon,
    VariableIcon
} from '@heroicons/vue/24/solid'

const router = useRouter()

const goToRun = () => {
    router.push({ name: 'deep-analysis-fluid-dynamics-run' })
}

const scrollToProcess = () => {
    const el = document.getElementById('workflow-section')
    if (el) el.scrollIntoView({ behavior: 'smooth' })
}

const activeDimensions = ['流速分析', '粘度评估', '雷诺数判定', '涡度追踪', '多层网络流', '压力梯度']

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

const examples = [
    {
        id: 'IV',
        title: '信息流速',
        icon: BoltIcon,
        colorClass: 'bg-amber-50 text-amber-600',
        description: '监测信息在全网节点间的扩散加速度，识别异常爆发事件。'
    },
    {
        id: 'PV',
        title: '介质粘度',
        icon: BeakerIcon,
        colorClass: 'bg-indigo-50 text-indigo-600',
        description: '评估平台审查、用户交互门槛对传播流动的抑制作用。'
    },
    {
        id: 'RN',
        title: '雷诺数判定',
        icon: AdjustmentsHorizontalIcon,
        colorClass: 'bg-purple-50 text-purple-600',
        description: '通过动力量化指标区分受控规律传播与无序自发蔓延。'
    },
    {
        id: 'PG',
        title: '压强梯度',
        icon: GlobeAltIcon,
        colorClass: 'bg-emerald-50 text-emerald-600',
        description: '识别不同利益群体或地域间的信息势能差与流动牵引力。'
    }
]
</script>

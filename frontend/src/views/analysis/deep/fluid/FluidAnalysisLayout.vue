<template>
    <div class="space-y-6">
        <header class="flex flex-wrap items-center justify-between gap-3 text-sm text-secondary">
            <nav class="flex items-center gap-2">
                <RouterLink :to="{ name: 'deep-analysis-fluid-dynamics' }"
                    class="inline-flex items-center gap-1 rounded-full px-3 py-1 transition focus-ring-accent"
                    :class="isOverview ? 'bg-brand-soft text-brand-600' : 'text-secondary hover:bg-brand-soft/60'">
                    <Squares2X2Icon class="h-4 w-4" />
                    <span>流程概览</span>
                </RouterLink>
                <template v-if="!isOverview">
                    <ChevronRightIcon class="h-4 w-4 text-muted" />
                    <span class="text-secondary">{{ currentBreadcrumb }}</span>
                </template>
            </nav>
            <RouterLink v-if="!isOverview" :to="{ name: 'deep-analysis-fluid-dynamics' }"
                class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-ring-accent">
                <ChevronLeftIcon class="h-4 w-4" />
                返回开始页
            </RouterLink>
        </header>

        <div class="flex flex-col gap-6 pb-20 lg:flex-row lg:items-start lg:pb-0">
            <CollapsibleSidebar :items="steps" :is-active-fn="isActive" />
            <div class="flex-1 min-w-0">
                <RouterView />
            </div>
        </div>
    </div>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
    Squares2X2Icon,
    PlayCircleIcon,
    ChartBarSquareIcon,
    ChevronRightIcon,
    ChevronLeftIcon
} from '@heroicons/vue/24/outline'
import CollapsibleSidebar from '../../../../components/navigation/CollapsibleSidebar.vue'

const steps = [
    {
        key: 'overview',
        label: '流程概览',
        to: { name: 'deep-analysis-fluid-dynamics' },
        icon: Squares2X2Icon,
        description: '了解流体力学分析'
    },
    {
        key: 'run',
        label: '运行分析',
        to: { name: 'deep-analysis-fluid-dynamics-run' },
        icon: PlayCircleIcon,
        description: '执行流体力学计算'
    },
    {
        key: 'view',
        label: '查看结果',
        to: { name: 'deep-analysis-fluid-dynamics-view' },
        icon: ChartBarSquareIcon,
        description: '查看可视化仪表盘'
    }
]

const route = useRoute()

const isActive = (itemOrTarget) => {
    const target = itemOrTarget?.to ?? itemOrTarget
    if (!target?.name) return false
    if (route.name === target.name) return true
    if (Array.isArray(route.matched)) {
        return route.matched.some((record) => record.name === target.name)
    }
    return false
}

const isOverview = computed(() => route.name === 'deep-analysis-fluid-dynamics')
const currentBreadcrumb = computed(() => route.meta?.breadcrumb || route.meta?.title || '')
</script>

<template>
  <div class="space-y-8">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="space-y-1">
        <h1 class="text-2xl font-semibold text-primary">专题基础分析</h1>
        <p class="text-sm text-secondary">
          围绕已归档的数据集规划基础指标，后续将在此展示可视化分析面板。
        </p>
      </div>
      <div class="flex items-center gap-2 rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">
        <BeakerIcon class="h-4 w-4" />
        <span>基础分析模块</span>
      </div>
    </header>

    <section class="card-surface space-y-6 p-6 text-sm text-secondary">
      <header class="space-y-2">
        <h2 class="text-xl font-semibold text-primary">分析面板建设中</h2>
        <p>
          计划提供词云、情感倾向、热度趋势等基础指标，帮助团队快速理解专题表现并指导后续研判。
        </p>
      </header>
      <div class="rounded-3xl border border-dashed border-brand-soft bg-brand-soft-muted p-5 text-sm text-brand-600">
        当前可通过命令行或 Notebook 运行
        <code class="rounded bg-brand-soft px-1 py-0.5 text-xs text-brand-600">analyze</code>
        模块获取统计结果。界面版分析将在后续迭代中上线。
      </div>
      <p>
        具体请移步测试页面。
      </p>
    </section>
  </div>
</template>

<script setup>
import { BeakerIcon } from '@heroicons/vue/24/outline'
</script>

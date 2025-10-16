<template>
  <div class="space-y-8">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="space-y-1">
        <h1 class="text-2xl font-semibold text-primary">基本分析</h1>
        <p class="text-sm text-secondary">即将上线的可视化指标，为专题研判提供快捷参考。</p>
      </div>
      <div class="flex items-center gap-2 rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">
        <BeakerIcon class="h-4 w-4" />
        <span>步骤 4 · 基本分析</span>
      </div>
    </header>

    <section class="card-surface space-y-6 p-6 text-sm text-secondary">
      <header class="space-y-2">
        <h2 class="text-xl font-semibold text-primary">基础分析模块筹备中</h2>
        <p class="text-sm text-secondary">计划在此提供词云、情感倾向以及热度趋势等基础指标，帮助快速理解专题表现。</p>
      </header>
      <div class="rounded-3xl border border-dashed border-brand-soft bg-brand-soft-muted p-5 text-sm text-brand-600">
        当前可通过命令行或 Notebook 运行 <code class="rounded bg-brand-soft px-1 py-0.5 text-xs text-brand-600">Analyze</code> 模块获取统计结果。界面版分析将在后续迭代中上线。
      </div>
      <p class="text-sm text-secondary">
        如有优先需求，可在 TODO 清单中补充具体指标，我们将优先排期实现。
      </p>
    </section>
  </div>
</template>

<script setup>
import { BeakerIcon } from '@heroicons/vue/24/outline'
</script>

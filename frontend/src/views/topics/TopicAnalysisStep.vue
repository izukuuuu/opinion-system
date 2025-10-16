<template>
  <div class="space-y-8">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="space-y-1">
        <h1 class="text-2xl font-semibold text-slate-900">基本分析</h1>
        <p class="text-sm text-slate-500">即将上线的可视化指标，为专题研判提供快捷参考。</p>
      </div>
      <div class="flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-600">
        <BeakerIcon class="h-4 w-4" />
        <span>步骤 4 · 基本分析</span>
      </div>
    </header>

    <section class="card-surface space-y-6 rounded-3xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm">
      <header class="space-y-2">
        <h2 class="text-xl font-semibold text-slate-900">基础分析模块筹备中</h2>
        <p class="text-sm text-slate-500">计划在此提供词云、情感倾向以及热度趋势等基础指标，帮助快速理解专题表现。</p>
      </header>
      <div class="rounded-3xl border border-dashed border-indigo-200 bg-indigo-50/60 p-5 text-sm text-indigo-700">
        当前可通过命令行或 Notebook 运行 <code class="rounded bg-indigo-100 px-1 py-0.5 text-xs text-indigo-700">Analyze</code> 模块获取统计结果。界面版分析将在后续迭代中上线。
      </div>
      <p class="text-sm text-slate-500">
        如有优先需求，可在 TODO 清单中补充具体指标，我们将优先排期实现。
      </p>
    </section>
  </div>
</template>

<script setup>
import { BeakerIcon } from '@heroicons/vue/24/outline'
</script>

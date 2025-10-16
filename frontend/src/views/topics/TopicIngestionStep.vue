<template>
  <div class="space-y-8">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="space-y-1">
        <h1 class="text-2xl font-semibold text-slate-900">数据入库</h1>
        <p class="text-sm text-slate-500">了解当前入库实现状态，按提示手动完成写入流程。</p>
      </div>
      <div class="flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-600">
        <ArrowTrendingUpIcon class="h-4 w-4" />
        <span>步骤 3 · 入库</span>
      </div>
    </header>

    <section class="card-surface space-y-6 rounded-3xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm">
      <header class="space-y-2">
        <h2 class="text-xl font-semibold text-slate-900">入库功能建设中</h2>
        <p class="text-sm text-slate-500">
          数据库访问模块尚在调整中，暂不提供自动化入库能力。可以使用下方建议步骤手动完成。
        </p>
      </header>
      <ol class="list-decimal space-y-2 pl-6">
        <li>在服务器上确认数据库连接配置，确保目标库表可写入。</li>
        <li>使用上一阶段产出的筛选结果，通过命令行 <code class="rounded bg-slate-100 px-1 py-0.5 text-xs">python backend/main.py Upload --topic &lt;name&gt; --date &lt;YYYY-MM-DD&gt;</code> 执行入库。</li>
        <li>如需验证结果，可在数据库页面或命令行执行查询以确认数据写入。</li>
      </ol>
      <div class="rounded-3xl border border-dashed border-indigo-200 bg-indigo-50/60 p-5 text-sm text-indigo-700">
        入库 API 调试完成后，可在此页面直接填写专题名称与日期，并调用 <code class="rounded bg-indigo-100 px-1 py-0.5 text-xs text-indigo-700">/api/upload</code> 接口完成操作。
      </div>
    </section>
  </div>
</template>

<script setup>
import { ArrowTrendingUpIcon } from '@heroicons/vue/24/outline'
</script>

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
        <h2 class="text-xl font-semibold text-primary">分析模块规划中</h2>
        <p>以下功能正在搭建中，敬请期待。</p>
      </header>
      <div class="rounded-3xl border border-dashed border-brand-soft bg-brand-soft-muted p-5 font-mono text-sm text-brand-600">
        <pre class="whitespace-pre text-brand-700" v-text="placeholderTree"></pre>
      </div>
    </section>
  </div>
</template>

<script setup>
import { BeakerIcon } from '@heroicons/vue/24/outline'

const placeholderTree = `专题基础分析
├── 情感分析
│   ├── 话题分类
│   ├── 地域分析
│   ├── 关键词提取
│   ├── 趋势分析
│   └── 内容编码分析`
</script>

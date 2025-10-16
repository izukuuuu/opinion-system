<template>
  <div class="space-y-10">
    <section class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-500 via-sky-500 to-sky-400 px-6 py-10 text-white shadow-2xl sm:px-10">
      <div class="absolute inset-0 opacity-40">
        <div class="absolute -top-24 left-1/2 h-72 w-72 -translate-x-1/2 rounded-full bg-white/20 blur-3xl"></div>
        <div class="absolute bottom-0 right-10 h-56 w-56 rounded-full bg-sky-200/40 blur-3xl"></div>
      </div>
      <div class="relative flex flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
        <div class="space-y-4">
          <p class="text-sm font-semibold uppercase tracking-[0.4em] text-white/60">新建专题</p>
          <h1 class="text-3xl font-semibold sm:text-4xl">启动新的舆情专题</h1>
          <p class="text-lg text-indigo-100/90">
            通过上传数据、执行预处理、入库以及分析，快速完成专题初始化。
          </p>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full bg-white/90 px-6 py-3 text-indigo-600 shadow-lg transition hover:-translate-y-0.5 hover:bg-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          @click="goToUpload"
        >
          <span class="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-100 text-indigo-600">
            <CloudArrowUpIcon class="h-5 w-5" />
          </span>
          <span class="text-base font-semibold">立即上传数据</span>
        </button>
      </div>
    </section>

    <section class="space-y-6">
      <header class="space-y-2">
        <h2 class="text-2xl font-semibold text-slate-900">专题筹备流程</h2>
        <p class="text-sm text-slate-500">
          按照步骤完成数据导入和准备工作，也可以直接跳转到需要的步骤。
        </p>
      </header>
      <div class="grid gap-6 md:grid-cols-2">
        <article
          v-for="stage in stages"
          :key="stage.title"
          class="card-surface flex flex-col gap-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-lg"
        >
          <div class="flex items-center gap-3">
            <span
              class="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-500/10 text-lg font-semibold text-indigo-600"
            >
              {{ stage.index }}
            </span>
            <div>
              <h3 class="text-lg font-semibold text-slate-900">{{ stage.title }}</h3>
              <p class="text-sm text-slate-500">{{ stage.subtitle }}</p>
            </div>
          </div>
          <p class="flex-1 text-sm leading-relaxed text-slate-600">
            {{ stage.description }}
          </p>
          <button
            type="button"
            class="inline-flex items-center gap-2 self-start rounded-full border border-indigo-200 px-4 py-1.5 text-sm font-semibold text-indigo-600 transition hover:bg-indigo-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
            @click="router.push(stage.route)"
          >
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
import { ArrowRightIcon, CloudArrowUpIcon } from '@heroicons/vue/24/outline'

const router = useRouter()

const goToUpload = () => {
  router.push({ name: 'topic-create-upload' })
}

const stages = [
  {
    index: 1,
    title: '上传原始数据',
    subtitle: '导入 Excel/CSV 数据文件',
    description:
      '将获取到的专题素材上传至系统，自动生成 JSONL 与 PKL 存档，为后续处理做好准备。',
    route: { name: 'topic-create-upload' }
  },
  {
    index: 2,
    title: '数据预处理',
    subtitle: '执行合并、清洗与筛选',
    description:
      '根据专题日期执行 Merge、Clean、Filter 三个步骤，生成符合分析标准的结构化数据。',
    route: { name: 'topic-create-preprocess' }
  },
  {
    index: 3,
    title: '入库',
    subtitle: '上传至数据库',
    description:
      '将筛选后的数据写入数据库，后续可用于深度分析与可视化展示。当前阶段暂留空，可提前规划。',
    route: { name: 'topic-create-ingest' }
  },
  {
    index: 4,
    title: '基本分析',
    subtitle: '快速查看数据指标',
    description:
      '执行基础数据统计与概览，为舆情研判提供初步依据。功能即将开放，敬请期待。',
    route: { name: 'topic-create-analysis' }
  }
]
</script>

<template>
  <div class="space-y-10">
    <section class="relative overflow-hidden rounded-3xl bg-gradient-brand px-6 py-10 text-white sm:px-10">
      <div class="absolute inset-0 opacity-40">
        <div class="absolute -top-24 left-1/2 h-72 w-72 -translate-x-1/2 rounded-full bg-white/25 blur-3xl"></div>
        <div class="absolute bottom-0 right-10 h-56 w-56 rounded-full bg-accent-soft opacity-60 blur-3xl"></div>
      </div>
      <div class="relative flex flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
        <div class="space-y-4">
          <p class="text-sm font-semibold uppercase tracking-[0.4em] text-white/70">新建专题</p>
          <h1 class="text-3xl font-semibold sm:text-4xl">启动新的舆情专题</h1>
          <p class="text-lg text-white/80">
            通过上传数据、执行预处理与入库，快速完成专题初始化；分析结果可在项目数据模块中查看。
          </p>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 border border-brand-100 transition hover:bg-gray-50 focus-ring-accent"
          @click="goToUpload"
        >
          <span class="flex h-9 w-9 items-center justify-center rounded-full bg-brand-50"
                style="color: rgb(var(--color-brand-800));">
            <CloudArrowUpIcon class="h-5 w-5" />
          </span>
          <span class="text-base font-semibold" style="color: rgb(var(--color-brand-800));">立即上传数据</span>
        </button>
      </div>
    </section>

    <section class="space-y-6">
      <header class="space-y-2">
        <h2 class="text-2xl font-semibold text-primary">专题筹备流程</h2>
        <p class="text-sm text-secondary">
          按照步骤完成数据导入和准备工作，也可以直接跳转到需要的步骤。
        </p>
      </header>
      <div class="grid gap-6 md:grid-cols-2">
        <article
          v-for="stage in stages"
          :key="stage.title"
          class="card-surface flex flex-col gap-4 p-6"
        >
          <div class="flex items-center gap-3">
            <span
              class="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-soft text-lg font-semibold text-brand-600"
            >
              {{ stage.index }}
            </span>
            <div>
              <h3 class="text-lg font-semibold text-primary">{{ stage.title }}</h3>
              <p class="text-sm text-secondary">{{ stage.subtitle }}</p>
            </div>
          </div>
          <p class="flex-1 text-sm leading-relaxed text-secondary">
            {{ stage.description }}
          </p>
          <button
            type="button"
            class="inline-flex items-center gap-2 self-start rounded-full border border-brand-soft px-4 py-1.5 text-sm font-semibold text-brand-600 transition hover:bg-brand-soft focus-ring-accent"
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
    subtitle: '执行 Merge 与 Clean',
    description:
      '根据当前处理日期执行 Merge、Clean 两个步骤，生成符合分析标准的结构化数据。',
    route: { name: 'topic-create-preprocess' }
  },
  {
    index: 3,
    title: '筛选数据',
    subtitle: '配置提示词并执行筛选',
    description:
      '管理 AI 提示词模板，独立运行 Filter 流程，获取与专题高度相关的内容。',
    route: { name: 'topic-create-filter' }
  },
  {
    index: 4,
    title: '入库',
    subtitle: '上传至数据库',
    description:
      '将筛选后的数据写入数据库，后续可用于深度分析与可视化展示。当前阶段暂留空，可提前规划。',
    route: { name: 'topic-create-ingest' }
  },
]
</script>

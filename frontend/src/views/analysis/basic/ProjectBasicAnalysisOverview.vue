<template>
  <div class="space-y-10">
    <section class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-500 to-brand-700 px-6 py-10 text-white sm:px-10">
      <div class="absolute inset-0 opacity-40">
        <div class="absolute -top-28 left-1/3 h-72 w-72 -translate-x-1/2 rounded-full bg-white/25 blur-3xl"></div>
        <div class="absolute bottom-0 right-10 h-56 w-56 rounded-full bg-brand-200/80 blur-3xl"></div>
      </div>
      <div class="relative space-y-6">
        <div class="space-y-4">
          <p class="text-sm font-semibold uppercase tracking-[0.4em] text-white/70">基础分析</p>
          <h1 class="text-3xl font-semibold sm:text-4xl">专题基础分析</h1>
        </div>
        
        <div class="space-y-4">
          <p class="text-sm text-white/90">
            专题基础分析对指定时间范围内的数据进行统计和分类，帮助了解专题的传播情况、内容特征和用户反馈。
          </p>
          
          <div>
            <p class="mb-2 text-sm font-semibold text-white">主要输出</p>
            <p class="text-sm leading-relaxed text-white/80">
              系统会统计舆情声量变化趋势、各平台分布情况、内容类型占比、高频关键词、发布者信息、情感倾向分布等数据，并以图表形式展示分析结果。
            </p>
          </div>
          
          <div>
            <p class="mb-2 text-sm font-semibold text-white">分析维度</p>
            <div class="flex flex-wrap gap-2">
              <span class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">地域分析</span>
              <span class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">关键词分析</span>
              <span class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">趋势洞察</span>
              <span class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">发布者分析</span>
              <span class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">情感分析</span>
              <span class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">声量概览</span>
              <span class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">话题分类</span>
            </div>
          </div>
        </div>
        
        <div class="flex justify-end">
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-brand-700 transition hover:bg-gray-50 focus-ring-accent"
            @click="goToRun"
          >
            <span class="flex h-7 w-7 items-center justify-center rounded-full bg-brand-50 text-brand-700">
              <PlayCircleIcon class="h-4 w-4" />
            </span>
            <span class="text-sm font-semibold">立即运行分析</span>
          </button>
        </div>
      </div>
    </section>

    <section class="space-y-6">
      <header class="space-y-2">
        <h2 class="text-2xl font-semibold text-primary">基础分析流程</h2>
        <p class="text-sm text-secondary">请先针对各个专题运行各项基础分析功能之后，在查看分析界面查看基础统计</p>
      </header>

      <div class="grid gap-6 md:grid-cols-2">
        <article
          v-for="step in steps"
          :key="step.title"
          class="card-surface flex flex-col gap-4 p-6"
        >
          <div class="flex items-center gap-3">
            <span class="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-soft text-lg font-semibold text-brand-600">
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
          <button
            type="button"
            class="inline-flex items-center gap-2 self-start rounded-full border border-brand-soft px-4 py-1.5 text-sm font-semibold text-brand-600 transition hover:bg-brand-soft focus-ring-accent"
            @click="router.push(step.route)"
          >
            <ArrowRightIcon class="h-4 w-4" />
            前往
          </button>
        </article>
      </div>
    </section>

    <section class="space-y-6">
      <header class="space-y-2">
        <h2 class="text-2xl font-semibold text-primary">分析解读示例</h2>
      </header>

      <div class="card-surface space-y-6 p-5 sm:p-6">
        <section class="space-y-4">
        <h3 class="text-lg font-semibold text-primary">AI 摘要解读</h3>
        
        <div>
          <p class="mb-2 text-sm font-semibold text-primary">主要发现</p>
          <p class="text-sm leading-relaxed text-secondary">
            2025年9月23日舆情声量达峰值369，社交平台与自媒体主导传播，信息传递类内容占主流。舆论聚焦戒烟与健康关联，nicotine、肺癌等关键词反映公众对吸烟风险的科学关切，情绪总体平稳但负面略显突出。
          </p>
        </div>
        
        <div>
          <p class="mb-2 text-sm text-secondary">依据：</p>
          <div class="flex flex-wrap gap-2">
            <span class="inline-flex items-center rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">情感分析</span>
            <span class="inline-flex items-center rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">话题分类</span>
            <span class="inline-flex items-center rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">地域分析</span>
            <span class="inline-flex items-center rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">关键词分析</span>
            <span class="inline-flex items-center rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">发布者分析</span>
            <span class="inline-flex items-center rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">趋势洞察</span>
            <span class="inline-flex items-center rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">声量概览</span>
          </div>
        </div>
      </section>

      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <article class="flex h-full flex-col rounded-2xl border border-soft bg-base-soft p-4">
          <div class="mb-3 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-50 text-purple-600">
              <HeartIcon class="h-4 w-4" />
            </div>
            <h4 class="text-sm font-semibold text-primary">情感分析</h4>
          </div>
          <p class="flex-1 text-sm leading-relaxed text-secondary">
            舆情整体以中性为主，负面略高于正面，情绪倾向总体平稳。
          </p>
        </article>

        <article class="flex h-full flex-col rounded-2xl border border-soft bg-base-soft p-4">
          <div class="mb-3 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
              <TagIcon class="h-4 w-4" />
            </div>
            <h4 class="text-sm font-semibold text-primary">话题分类</h4>
          </div>
          <p class="flex-1 text-sm leading-relaxed text-secondary">
            报道事实类内容显著多于评论观点类，舆论场以信息传递为主导。
          </p>
        </article>

        <article class="flex h-full flex-col rounded-2xl border border-soft bg-base-soft p-4">
          <div class="mb-3 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-green-50 text-green-600">
              <MapPinIcon class="h-4 w-4" />
            </div>
            <h4 class="text-sm font-semibold text-primary">地域分析</h4>
          </div>
          <p class="flex-1 text-sm leading-relaxed text-secondary">
            地域分布显示舆情主要集中在广东、河北、浙江等地，华北与东南沿海省份占比较高，另有118条来源未知，需进一步核查数据准确性。
          </p>
        </article>

        <article class="flex h-full flex-col rounded-2xl border border-soft bg-base-soft p-4">
          <div class="mb-3 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-50 text-orange-600">
              <MagnifyingGlassIcon class="h-4 w-4" />
            </div>
            <h4 class="text-sm font-semibold text-primary">关键词分析</h4>
          </div>
          <p class="flex-1 text-sm leading-relaxed text-secondary">
            戒烟与健康关联最密切，控烟、烟草危害及吸烟风险成舆论焦点，nicotine、肺癌等关键词凸显公众对吸烟健康后果的科学关注。
          </p>
        </article>

        <article class="flex h-full flex-col rounded-2xl border border-soft bg-base-soft p-4">
          <div class="mb-3 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
              <UserGroupIcon class="h-4 w-4" />
            </div>
            <h4 class="text-sm font-semibold text-primary">发布者分析</h4>
          </div>
          <p class="flex-1 text-sm leading-relaxed text-secondary">
            青少年控烟与健康、梦中情郎各发布5次居首，悦子鸭鸭、仁心药士等各3次紧随，头部发布者集中度较高。
          </p>
        </article>

        <article class="flex h-full flex-col rounded-2xl border border-soft bg-base-soft p-4">
          <div class="mb-3 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-pink-50 text-pink-600">
              <ChartBarIcon class="h-4 w-4" />
            </div>
            <h4 class="text-sm font-semibold text-primary">趋势洞察</h4>
          </div>
          <p class="flex-1 text-sm leading-relaxed text-secondary">
            2025年9月23日舆情总量达369，为当前周期内峰值，显示该日事件引发显著舆论关注。
          </p>
        </article>

        <article class="flex h-full flex-col rounded-2xl border border-soft bg-base-soft p-4">
          <div class="mb-3 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-50 text-cyan-600">
              <SpeakerWaveIcon class="h-4 w-4" />
            </div>
            <h4 class="text-sm font-semibold text-primary">声量概览</h4>
          </div>
          <p class="flex-1 text-sm leading-relaxed text-secondary">
            自媒体号和微信平台声量领先，微博与视频次之，论坛关注度最低，整体传播以社交和自媒体渠道为主导。
          </p>
        </article>
      </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import {
  ArrowRightIcon,
  PlayCircleIcon,
  HeartIcon,
  TagIcon,
  MapPinIcon,
  MagnifyingGlassIcon,
  UserGroupIcon,
  ChartBarIcon,
  SpeakerWaveIcon
} from '@heroicons/vue/24/outline'

const router = useRouter()

const goToRun = () => {
  router.push({ name: 'project-data-analysis-run' })
}

const steps = [
  {
    index: 1,
    title: '运行分析',
    subtitle: '拉取数据并执行',
    description: '选择远程数据库的专题并指定时间区间，运行基础分析，结果将保存到后台以供查看。',
    route: { name: 'project-data-analysis-run' }
  },
  {
    index: 2,
    title: '查看分析',
    subtitle: '刷新与浏览结果',
    description: '从历史记录中选择分析任务，查看可视化面板，并快速定位到具体模块。',
    route: { name: 'project-data-analysis-view' }
  }
]
</script>

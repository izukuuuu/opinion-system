<template>
  <div class="space-y-10">
    <!-- Hero Section -->
    <section
      class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-600 via-brand-500 to-accent-500 px-8 py-16 text-white sm:px-12 lg:px-16 space-shadow-none">
      <div class="absolute inset-0 opacity-30 mix-blend-overlay">
        <div class="absolute -top-32 -left-32 h-96 w-96 rounded-full bg-white/20 blur-[100px]"></div>
        <div
          class="absolute bottom-0 right-0 h-[30rem] w-[30rem] translate-x-1/3 translate-y-1/3 rounded-full bg-accent-300/30 blur-[120px]">
        </div>
      </div>
      <div class="relative flex flex-col gap-10 lg:flex-row lg:items-center lg:justify-between">
        <div class="space-y-6 max-w-2xl">
          <div
            class="inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-1.5 text-sm font-medium text-white/90 backdrop-blur-md border border-white/10">
            <span class="flex h-2 w-2 rounded-full bg-accent-300"></span>
            舆情分析工作台
          </div>
          <h1 class="text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl text-white">
            启动新的<br />舆情专题
          </h1>
          <p class="text-lg text-white/80 leading-relaxed max-w-xl">
            通过简单的四步流程，快速完成数据上传、清洗、筛选与入库。系统将自动构建分析所需的结构化存档。
          </p>
        </div>
        <button type="button"
          class="group relative inline-flex items-center gap-3 overflow-hidden rounded-full bg-white px-8 py-4 text-brand-900 transition-all hover:bg-gray-50 active:scale-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          @click="goToUpload">
          <div
            class="flex h-10 w-10 items-center justify-center rounded-full bg-brand-100 group-hover:bg-brand-200 transition-colors">
            <CloudArrowUpIcon class="h-6 w-6 text-brand-700" />
          </div>
          <span class="text-lg font-bold tracking-tight">立即上传数据</span>
        </button>
      </div>
    </section>

    <TopicPreparationWorkflow />
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import {
  CloudArrowUpIcon
} from '@heroicons/vue/24/outline'
import TopicPreparationWorkflow from '../../components/topics/TopicPreparationWorkflow.vue'

const router = useRouter()

const goToUpload = () => {
  router.push({ name: 'topic-create-upload' })
}
</script>

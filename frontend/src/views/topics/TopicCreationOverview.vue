<template>
  <div class="space-y-6 pb-12">
    <section class="relative overflow-hidden rounded-3xl border border-soft bg-surface p-1">
      <div
        class="relative isolate overflow-hidden rounded-[22px] bg-gradient-to-br from-brand-600 via-brand-500 to-accent-500 px-6 py-10 text-white sm:px-10 sm:py-12">
        <div class="absolute inset-0 opacity-30 mix-blend-overlay">
          <div class="absolute -top-32 -left-32 h-96 w-96 rounded-full bg-white/20 blur-[100px]"></div>
          <div
            class="absolute bottom-0 right-0 h-[30rem] w-[30rem] translate-x-1/3 translate-y-1/3 rounded-full bg-accent-300/30 blur-[120px]">
          </div>
        </div>

        <div class="relative z-10 grid gap-8 lg:grid-cols-2 lg:items-center">
          <div class="space-y-6">
            <div class="space-y-2">
              <div
                class="inline-flex items-center rounded-full border border-white/10 bg-white/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-widest text-brand-100 backdrop-blur-md">
                Topic Creation Workflow
              </div>
              <h1 class="text-3xl font-extrabold tracking-tight sm:text-4xl lg:text-5xl">
                启动新的专题
              </h1>
              <p class="max-w-xl text-base font-medium leading-relaxed text-brand-50/80">
                通过上传、清洗、筛选和入库四个环节，把原始舆情数据整理成后续分析可直接使用的专题存档。
              </p>
            </div>

            <div class="flex flex-wrap gap-2 text-[10px]">
              <span v-for="tag in workflowTags" :key="tag"
                class="rounded-full border border-white/5 bg-white/10 px-3 py-1 font-semibold text-white backdrop-blur-sm">
                {{ tag }}
              </span>
            </div>

            <div class="flex flex-wrap items-center gap-3 pt-2">
              <button type="button"
                class="group inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-brand-800 transition-all active:scale-95"
                @click="goToUpload">
                <CloudArrowUpIcon class="h-4 w-4" />
                <span class="text-sm font-bold">立即上传数据</span>
              </button>

              <button type="button"
                class="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/5 px-5 py-2.5 text-sm text-white transition-all"
                @click="scrollToWorkflow">
                <InformationCircleIcon class="h-4 w-4" />
                <span>查看流程说明</span>
              </button>
            </div>
          </div>

          <div class="hidden lg:block">
            <div class="glass-inner-glow-card rounded-2xl p-5">
              <div class="relative z-10">
                <h3 class="mb-3 text-xs font-bold text-brand-200">需要完成的步骤 (Workflow Snapshot)</h3>
                <ul class="space-y-2.5 text-[13px] text-white/70">
                  <li class="flex items-start gap-3">
                    <div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400"></div>
                    <span>上传原始数据文件，建立专题的初始数据池</span>
                  </li>
                  <li class="flex items-start gap-3">
                    <div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400"></div>
                    <span>执行清洗与筛选，排除噪音内容并保留有效样本</span>
                  </li>
                  <li class="flex items-start gap-3">
                    <div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400"></div>
                    <span>完成入库归档，为后续基础分析和主题聚类准备标准输入</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section id="workflow-section">
      <TopicPreparationWorkflow />
    </section>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import {
  CloudArrowUpIcon,
  InformationCircleIcon
} from '@heroicons/vue/24/outline'
import TopicPreparationWorkflow from '../../components/topics/TopicPreparationWorkflow.vue'

const router = useRouter()
const workflowTags = ['数据上传', '数据清洗', '条件筛选', '专题入库']

const goToUpload = () => {
  router.push({ name: 'topic-create-upload' })
}

const scrollToWorkflow = () => {
  const el = document.getElementById('workflow-section')
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<template>
  <section class="topic-prep-workflow">
    <header class="topic-prep-workflow__header">
      <h2 class="topic-prep-workflow__title">{{ title }}</h2>
      <p class="topic-prep-workflow__description">
        {{ description }}
      </p>
    </header>

    <div class="topic-prep-workflow__grid">
      <article
        v-for="stage in stages"
        :key="stage.title"
        class="topic-prep-workflow__card"
        @click="router.push(stage.route)"
      >
        <div class="topic-prep-workflow__index">{{ stage.index }}</div>

        <div class="topic-prep-workflow__body">
          <div class="topic-prep-workflow__icon">
            <component :is="stage.icon" class="topic-prep-workflow__icon-svg" />
          </div>

          <div class="topic-prep-workflow__meta">
            <h3 class="topic-prep-workflow__step-title">{{ stage.title }}</h3>
            <p class="topic-prep-workflow__step-subtitle">{{ stage.subtitle }}</p>
          </div>

          <p class="topic-prep-workflow__step-description">
            {{ stage.description }}
          </p>
        </div>

        <div class="topic-prep-workflow__action">
          <span>{{ actionLabel }}</span>
          <ArrowRightIcon class="topic-prep-workflow__action-icon" />
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import '../../assets/topic-preparation-workflow.css'

import { useRouter } from 'vue-router'
import {
  ArrowRightIcon,
  CloudArrowUpIcon,
  FunnelIcon,
  AdjustmentsHorizontalIcon,
  ArrowTrendingUpIcon
} from '@heroicons/vue/24/outline'

const props = defineProps({
  title: {
    type: String,
    default: '专题筹备流程'
  },
  description: {
    type: String,
    default: '按照顺序完成数据准备，每一步都会生成独立的存档，方便随时回溯与调整。'
  },
  actionLabel: {
    type: String,
    default: '前往配置'
  }
})

const router = useRouter()

const stages = [
  {
    index: 1,
    title: '上传原始数据',
    subtitle: 'Upload',
    description: '将本地 Excel/CSV 原始数据导入系统，生成当前项目的标准化存档。',
    route: { name: 'topic-create-upload' },
    icon: CloudArrowUpIcon
  },
  {
    index: 2,
    title: '数据预处理',
    subtitle: 'Preprocess',
    description: '基于本地项目数据执行 Merge 与 Clean，完成合并、清洗和字段补齐。',
    route: { name: 'topic-create-preprocess' },
    icon: FunnelIcon
  },
  {
    index: 3,
    title: '筛选数据',
    subtitle: 'Filter',
    description: '围绕本地处理结果先做预清洗，再按需启用 AI 筛选，并继续后续清洗流程。',
    route: { name: 'topic-create-filter' },
    icon: AdjustmentsHorizontalIcon
  },
  {
    index: 4,
    title: '入库',
    subtitle: 'Ingest',
    description: '将本地清洗筛选后的最终结果写入目标数据库，供后续分析使用。',
    route: { name: 'topic-create-ingest' },
    icon: ArrowTrendingUpIcon
  }
]
</script>

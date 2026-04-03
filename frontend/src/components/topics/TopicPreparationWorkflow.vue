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
    description: '将获取到的 Excel/CSV 专题素材上传至系统，自动生成标准化存档。',
    route: { name: 'topic-create-upload' },
    icon: CloudArrowUpIcon
  },
  {
    index: 2,
    title: '数据预处理',
    subtitle: 'Preprocess',
    description: '执行 Merge 与 Clean，清洗数据并补齐字段，为分析做好准备。',
    route: { name: 'topic-create-preprocess' },
    icon: FunnelIcon
  },
  {
    index: 3,
    title: '筛选数据',
    subtitle: 'Filter',
    description: '先做零 token 预清洗，再按需启用 AI 筛选，最后可对数据库执行后清洗。',
    route: { name: 'topic-create-filter' },
    icon: AdjustmentsHorizontalIcon
  },
  {
    index: 4,
    title: '入库',
    subtitle: 'Ingest',
    description: '将清洗筛选后的最终数据写入数据库，供后续深度分析使用。',
    route: { name: 'topic-create-ingest' },
    icon: ArrowTrendingUpIcon
  }
]
</script>

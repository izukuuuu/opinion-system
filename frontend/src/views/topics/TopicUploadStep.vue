<template>
  <div class="space-y-10">
    <header class="flex flex-wrap items-center justify-between gap-4">
      <div class="space-y-1">
        <h1 class="text-xl font-bold tracking-tight text-primary">上传原始数据</h1>
        <p class="text-sm text-secondary">创建专题并上传 Excel/CSV 文件，系统将自动生成标准化存档。</p>
      </div>
      <div
        class="inline-flex items-center gap-2 rounded-full bg-brand-50 px-4 py-1.5 text-sm font-semibold text-brand-700 ring-1 ring-brand-200/50">
        <CloudArrowUpIcon class="h-5 w-5" />
        <span>Step 1 · Upload</span>
      </div>
    </header>

    <div class="grid gap-8 xl:grid-cols-[1fr,minmax(320px,1fr)]">
      <!-- Left Column: Create Topic Form -->
      <section class="card-surface p-8 flex flex-col gap-6">
        <header class="space-y-2">
          <h2 class="text-lg font-bold text-primary">创建专题</h2>
          <p class="text-xs text-secondary">
            填写专题信息以建立档案，后续数据将自动归档至此专题下。
          </p>
        </header>

        <form @submit.prevent="createTopic" class="flex flex-col gap-6 flex-1">
          <div class="space-y-5">
            <div class="space-y-2">
              <label class="text-sm font-bold text-primary ml-1">专题名称</label>
              <input v-model.trim="topicName" type="text" required class="input" placeholder="例如：2024-两会舆情专项" />
            </div>

            <div class="space-y-2">
              <label class="text-sm font-bold text-primary ml-1">专题说明</label>
              <textarea v-model.trim="topicDescription" rows="4" class="form-textarea resize-none"
                :placeholder="selectedTags.length ? '补充更多背景信息...' : '简要描述专题背景、抓取渠道等信息...'"></textarea>
            </div>

            <div class="space-y-3 rounded-3xl bg-surface-variant/50 p-5">
              <div class="flex items-center gap-2 text-sm font-bold text-primary">
                <TagIcon class="h-4 w-4 text-brand-500" />
                <span>快速标签</span>
              </div>
              <div class="flex flex-wrap gap-2">
                <button v-for="tag in suggestedTags" :key="tag" type="button"
                  class="inline-flex items-center rounded-full px-4 py-1.5 text-xs font-medium transition-all active:scale-95"
                  :class="selectedTags.includes(tag)
                    ? 'bg-brand-600 text-white'
                    : 'bg-white text-secondary ring-1 ring-black/5 hover:bg-gray-50'" @click="toggleTag(tag)">
                  {{ tag }}
                </button>
              </div>
              <div v-if="selectedTags.length" class="pt-2 text-xs text-secondary pl-1">
                已选：<span class="font-medium text-primary">{{ selectedTags.join(' · ') }}</span>
              </div>
            </div>
          </div>

          <div class="mt-auto flex items-center justify-end pt-4">
            <div class="mr-auto text-xs text-rose-500 font-medium" v-if="createError">{{ createError }}</div>
            <div class="mr-auto text-xs text-emerald-600 font-medium" v-if="createSuccess">{{ createSuccess }}</div>
            <button type="submit"
              class="inline-flex items-center gap-2 rounded-full bg-brand-600 px-8 py-3 text-sm font-bold text-white transition-all hover:bg-brand-700 disabled:opacity-60 disabled:cursor-not-allowed"
              :disabled="creating || !topicName">
              <span v-if="creating"
                class="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"></span>
              <span v-else>创建专题</span>
            </button>
          </div>
        </form>
      </section>

      <!-- Right Column: Upload Area -->
      <section class="card-surface p-8 flex flex-col gap-6">
        <header class="flex items-center justify-between">
          <div class="space-y-1">
            <h2 class="text-lg font-bold text-primary">上传文件</h2>
            <p class="text-xs text-secondary">
              支持 .xlsx, .xls, .csv
            </p>
          </div>
          <div v-if="topicName"
            class="hidden sm:inline-flex items-center rounded-full bg-base-soft px-3 py-1 text-xs font-medium text-secondary">
            当前：{{ topicName }}
          </div>
        </header>

        <template v-if="canUpload">
          <form class="flex flex-col gap-6" @submit.prevent="uploadDataset">
            <!-- Drop Zone -->
            <div
              class="relative flex min-h-[240px] cursor-pointer flex-col items-center justify-center gap-4 rounded-3xl border-2 border-dashed transition-all duration-300"
              :class="[
                uploadFiles.length || dragActive
                  ? 'border-brand-400 bg-brand-50/50'
                  : 'border-gray-200 bg-base-soft/50 hover:border-brand-300 hover:bg-base-soft'
              ]" @dragenter.prevent="handleDragEnter" @dragover.prevent="handleDragOver"
              @dragleave.prevent="handleDragLeave" @drop.prevent="handleDrop" @click="fileInput?.click()">
              <input ref="fileInput" type="file" class="hidden" accept=".xlsx,.xls,.csv,.jsonl" multiple
                @change="handleFileChange" />

              <div class="rounded-full bg-white p-4 ring-1 ring-black/5 transition-transform duration-300"
                :class="{ 'scale-110': dragActive }">
                <DocumentArrowUpIcon class="h-8 w-8 text-brand-500" />
              </div>

              <div class="text-center space-y-1">
                <p class="text-sm font-semibold text-primary">
                  {{ uploadFiles.length ? `已选择 ${uploadFiles.length} 个文件` : '点击选择或拖拽上传' }}
                </p>
                <p class="text-[11px] text-muted">
                  {{ uploadFiles.length ? '再次点击可继续添加' : '单文件最大 50MB · 支持批量上传' }}
                </p>
              </div>
            </div>

            <!-- File List Pills -->
            <div v-if="uploadFiles.length" class="flex flex-wrap gap-2">
              <div v-for="(file, index) in uploadFiles" :key="`${file.name}-${index}`"
                class="inline-flex items-center gap-2 rounded-full border border-gray-100 bg-white pl-4 pr-2 py-1.5 text-sm transition hover:scale-105">
                <span class="max-w-[150px] truncate text-secondary font-medium">{{ file.name }}</span>
                <button type="button"
                  class="rounded-full p-1 text-muted hover:bg-rose-50 hover:text-rose-600 transition-colors"
                  @click.stop="removeSelectedFile(index)">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
                    <path
                      d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                  </svg>
                </button>
              </div>
              <button v-if="uploadFiles.length > 0" type="button"
                class="inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs text-rose-600 hover:bg-rose-50 transition-colors"
                @click.stop="clearSelectedFiles">
                清空全部
              </button>
            </div>

            <div v-if="uploadFiles.length || uploading || uploadError || uploadSuccess || uploadStatuses.length"
              class="space-y-4 rounded-3xl border border-brand-100 bg-brand-50/50 p-4">
              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0 space-y-1">
                  <p class="text-sm font-bold text-primary">上传操作</p>
                  <p class="text-xs text-secondary">
                    {{ uploadFiles.length ? `当前待上传：${selectedFileSummary}` : '选择文件后即可开始上传并生成存档。' }}
                  </p>
                </div>
                <button type="submit"
                  class="inline-flex shrink-0 items-center justify-center rounded-full bg-brand-600 px-5 py-3 text-sm font-bold text-white shadow-sm transition-all hover:bg-brand-700 active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-brand-300"
                  :disabled="uploading || !uploadFiles.length">
                  {{ uploading ? '正在上传...' : '上传并生成存档' }}
                </button>
              </div>

              <div v-if="uploading || uploadError || uploadSuccess || uploadHelper" class="rounded-2xl border px-4 py-3"
                :class="uploadError
                  ? 'border-rose-200 bg-rose-50/90'
                  : uploadSuccess
                    ? 'border-emerald-200 bg-emerald-50/90'
                    : uploading
                      ? 'border-brand-200 bg-brand-50/80'
                      : 'border-gray-200 bg-white/80'">
                <div v-if="uploading" class="flex items-start gap-3 text-sm text-brand-800">
                  <span
                    class="mt-0.5 h-4 w-4 animate-spin rounded-full border-2 border-brand-200 border-t-brand-600"></span>
                  <div class="space-y-1">
                    <p class="font-semibold">{{ uploadActiveMessage }}</p>
                    <p class="text-xs text-brand-700/80">{{ uploadProgressMessage }}</p>
                  </div>
                </div>
                <div v-else-if="uploadError" class="space-y-1 text-sm text-rose-700">
                  <p class="font-semibold">上传未全部完成</p>
                  <p>{{ uploadError }}</p>
                </div>
                <div v-else-if="uploadSuccess" class="space-y-1 text-sm text-emerald-700">
                  <p class="font-semibold">上传结果已生成</p>
                  <p>{{ uploadSuccess }}</p>
                </div>
                <p v-else class="text-sm text-secondary">{{ uploadHelper }}</p>
              </div>

              <!-- Upload Progress -->
              <div v-if="uploadStatuses.length" class="space-y-3 rounded-2xl bg-surface-variant/30 p-4">
                <div
                  class="flex justify-between items-center text-xs font-bold text-secondary uppercase tracking-wider">
                  <span>Batch Progress</span>
                  <span>{{ uploadProgress.percent }}%</span>
                </div>
                <div class="h-3 w-full overflow-hidden rounded-full bg-base-soft">
                  <div class="h-full rounded-full bg-brand-500 transition-all duration-500 ease-out"
                    :style="{ width: `${uploadProgress.percent}%` }"></div>
                </div>
                <div class="space-y-1 max-h-32 overflow-y-auto pr-2 sidebar-scroll">
                  <div v-for="status in uploadStatuses" :key="status.key"
                    class="flex items-center justify-between text-xs py-1">
                    <span class="truncate text-secondary max-w-[70%]">{{ status.name }}</span>
                    <span class="px-2 py-0.5 rounded-full font-medium"
                      :class="status.status === 'success' ? 'bg-emerald-100 text-emerald-700' : status.status === 'error' ? 'bg-rose-100 text-rose-700' : 'text-muted'">
                      {{ status.message }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </form>

        </template>

        <div v-else
          class="flex-1 flex flex-col items-center justify-center rounded-[2rem] border-2 border-dashed border-gray-200 bg-base-soft/30 p-8 text-center">
          <div class="rounded-full bg-gray-50 p-4 mb-4">
            <CloudArrowUpIcon class="h-8 w-8 text-gray-300" />
          </div>
          <p class="text-secondary font-medium">等待创建专题</p>
          <p class="text-xs text-muted mt-1">请先在左侧完成专题信息填写</p>
        </div>
      </section>
    </div>

    <section class="card-surface p-8">
      <div class="grid gap-8 xl:grid-cols-[minmax(260px,360px),1fr] xl:items-start">
        <aside class="space-y-3">
          <p class="text-xs font-bold uppercase tracking-wider text-secondary">Online Acquisition</p>
          <h2 class="text-xl font-bold text-primary">在线采集</h2>
          <p class="text-sm leading-6 text-secondary">
            创建采集任务后，完成的数据会自动传输到当前专题。
          </p>
          <div v-if="canUpload" class="rounded-3xl border border-brand-100 bg-brand-50/50 p-4 text-xs text-secondary">
            当前专题：<span class="font-bold text-primary">{{ topicName }}</span>
          </div>
          <button
            v-if="canUpload && !settingsState.credentials.configured"
            type="button"
            class="rounded-full border border-amber-200 px-4 py-2 text-xs font-bold text-amber-700 transition hover:bg-amber-50"
            @click="goNetInsightSettings"
          >
            前往采集设置
          </button>
        </aside>

        <div v-if="canUpload" class="space-y-6">
          <div
            v-if="acquisitionFeedback.message || !settingsState.credentials.configured"
            class="rounded-2xl border px-4 py-3 text-sm"
            :class="acquisitionFeedback.type === 'error' || !settingsState.credentials.configured
              ? 'border-rose-200 bg-rose-50 text-rose-700'
              : 'border-emerald-200 bg-emerald-50 text-emerald-700'"
          >
            {{ !settingsState.credentials.configured ? '还没有完成采集账号设置，任务暂时无法运行。' : acquisitionFeedback.message }}
          </div>

          <form class="space-y-5" @submit.prevent="submitAcquisitionTask">
            <div class="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
              <label class="space-y-2">
                <span class="block text-sm font-bold text-primary">任务说明</span>
                <textarea
                  v-model.trim="acquisitionForm.brief"
                  rows="5"
                  class="form-textarea resize-none"
                  placeholder="描述采集对象、范围和重点议题"
                  @input="acquisitionBriefTouched = true"
                ></textarea>
              </label>
              <div class="space-y-4 rounded-3xl border border-gray-200 bg-base-soft/50 p-4">
                <div class="flex items-center justify-between gap-3">
                  <span class="text-sm font-bold text-primary">推荐配置</span>
                  <button
                    type="button"
                    class="rounded-full border border-brand-200 px-4 py-2 text-xs font-bold text-brand-700 transition hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-60"
                    :disabled="acquisitionPlanning || !acquisitionForm.brief.trim()"
                    @click="planAcquisitionTask(true)"
                  >
                    {{ acquisitionPlanning ? '生成中...' : '智能推荐' }}
                  </button>
                </div>
                <div class="grid gap-2 sm:grid-cols-3">
                  <button
                    v-for="scope in scopeOptions"
                    :key="scope.value"
                    type="button"
                    class="rounded-full border px-3 py-2 text-xs font-bold transition"
                    :class="acquisitionForm.scope === scope.value
                      ? 'border-brand-500 bg-brand-600 text-white'
                      : 'border-gray-200 bg-white text-secondary hover:bg-base-soft'"
                    @click="setAcquisitionScope(scope.value)"
                  >
                    {{ scope.label }}
                  </button>
                </div>
                <div class="grid gap-3 sm:grid-cols-2">
                  <label class="space-y-2">
                    <span class="block text-xs font-semibold text-primary/80">开始日期</span>
                    <input v-model="acquisitionForm.startDate" type="date" class="input" />
                  </label>
                  <label class="space-y-2">
                    <span class="block text-xs font-semibold text-primary/80">结束日期</span>
                    <input v-model="acquisitionForm.endDate" type="date" class="input" />
                  </label>
                </div>
              </div>
            </div>

            <div class="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
              <label class="space-y-2">
                <span class="block text-sm font-bold text-primary">关键词</span>
                <textarea
                  v-model.trim="acquisitionForm.keywordsText"
                  rows="6"
                  class="form-textarea resize-none"
                  placeholder="可按行输入，也可用逗号分隔"
                ></textarea>
              </label>
              <div class="space-y-3">
                <p class="text-sm font-bold text-primary">采集平台</p>
                <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  <AppCheckbox
                    v-for="option in acquisitionPlatformOptions"
                    :key="option"
                    v-model="acquisitionForm.platforms"
                    :value="option"
                    class="rounded-2xl border border-gray-200 bg-white px-3 py-2"
                    label-class="gap-2 text-sm text-secondary"
                    input-class="shadow-none"
                  >
                    {{ option }}
                  </AppCheckbox>
                </div>
              </div>
            </div>

            <div class="grid gap-4 md:grid-cols-4">
              <label class="space-y-2">
                <span class="block text-xs font-semibold text-primary/80">最多采集条数</span>
                <input v-model.number="acquisitionForm.totalLimit" type="number" min="1" class="input" />
              </label>
              <label class="space-y-2">
                <span class="block text-xs font-semibold text-primary/80">每批请求数</span>
                <input v-model.number="acquisitionForm.pageSize" type="number" min="10" class="input" />
              </label>
              <label class="flex items-end">
                <AppCheckbox
                  v-model="acquisitionForm.dedupeByContent"
                  label-class="gap-2 text-sm text-secondary"
                  input-class="shadow-none"
                >
                  自动过滤重复内容
                </AppCheckbox>
              </label>
              <div class="flex items-end justify-end">
                <button
                  type="submit"
                  class="rounded-full bg-brand-600 px-6 py-3 text-sm font-bold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-brand-300"
                  :disabled="acquisitionSubmitting || !canSubmitAcquisition || !settingsState.credentials.configured"
                >
                  {{ acquisitionSubmitting ? '提交中...' : '开始采集并传输' }}
                </button>
              </div>
            </div>
          </form>

          <div v-if="acquisitionTasks.length" class="space-y-3 rounded-3xl border border-gray-200 bg-white p-4">
            <div class="flex items-center justify-between gap-3">
              <p class="text-sm font-bold text-primary">当前专题采集任务</p>
              <button
                type="button"
                class="rounded-full px-3 py-1.5 text-xs font-bold text-brand-700 hover:bg-brand-50"
                :disabled="acquisitionLoading"
                @click="fetchAcquisitionTasks"
              >
                {{ acquisitionLoading ? '刷新中...' : '刷新' }}
              </button>
            </div>
            <div class="space-y-2">
              <div
                v-for="task in acquisitionTasks.slice(0, 5)"
                :key="task.id"
                class="rounded-2xl border border-gray-100 bg-base-soft/40 p-3"
              >
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div class="min-w-0">
                    <p class="truncate text-sm font-bold text-primary">{{ task.title || task.id }}</p>
                    <p class="mt-1 text-xs text-secondary">{{ acquisitionTaskSummary(task) }}</p>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="rounded-full px-3 py-1 text-xs font-bold" :class="acquisitionTaskStatusClass(task.status)">
                      {{ acquisitionTaskStatusLabel(task.status) }}
                    </span>
                    <button
                      v-if="canImportAcquisitionTask(task)"
                      type="button"
                      class="rounded-full border border-brand-200 px-3 py-1.5 text-xs font-bold text-brand-700 hover:bg-brand-50"
                      :disabled="acquisitionImportingTaskId === task.id"
                      @click="importAcquisitionTask(task)"
                    >
                      {{ acquisitionImportingTaskId === task.id ? '传输中...' : '传输到专题' }}
                    </button>
                  </div>
                </div>
                <div class="mt-3 h-2 overflow-hidden rounded-full bg-gray-100">
                  <div
                    class="h-full rounded-full bg-brand-500 transition-all duration-500"
                    :style="{ width: `${Math.max(0, Math.min(100, Number(task.progress?.percentage || 0)))}%` }"
                  ></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="flex min-h-[220px] flex-col items-center justify-center rounded-[2rem] border-2 border-dashed border-gray-200 bg-base-soft/30 p-8 text-center">
          <div class="mb-4 rounded-full bg-gray-50 p-4">
            <CloudArrowUpIcon class="h-8 w-8 text-gray-300" />
          </div>
          <p class="font-medium text-secondary">等待创建专题</p>
          <p class="mt-1 text-xs text-muted">专题创建后即可配置在线采集任务</p>
        </div>
      </div>
    </section>

    <transition name="fade" mode="out-in">
      <section v-if="latestDataset" key="dataset-column-setup" class="card-surface p-8">
        <div class="grid gap-8 xl:grid-cols-[minmax(260px,360px),1fr] xl:items-start">
          <aside class="space-y-3">
            <p class="text-xs font-bold uppercase tracking-wider text-secondary">Column Setup</p>
            <h2 class="text-xl font-bold text-primary">字段映射设置</h2>
            <p class="text-sm leading-6 text-secondary">
              请从刚上传的表格里选出发布时间、标题、正文和作者所在的列。
            </p>
            <div class="flex flex-wrap gap-2 text-xs">
              <span class="rounded-full bg-white px-3 py-1 text-secondary ring-1 ring-black/5">{{
                latestDataset.display_name
              }}</span>
              <span class="rounded-full bg-white px-3 py-1 text-secondary ring-1 ring-black/5">{{
                formatFileSize(latestDataset.file_size) }}</span>
              <span class="rounded-full bg-white px-3 py-1 text-secondary ring-1 ring-black/5">{{ latestDataset.rows }}
                行</span>
            </div>
          </aside>

          <div class="rounded-3xl border border-gray-200 bg-white p-6">
            <div class="grid gap-4 md:grid-cols-2">
              <label class="space-y-2">
                <span class="block text-xs font-semibold text-primary/80">哪一列是发布时间</span>
                <AppSelect :options="columnSelectOptions" :value="columnMappingForm.date" placeholder="选择表里的时间列"
                  @change="columnMappingForm.date = $event" />
              </label>
              <label class="space-y-2">
                <span class="block text-xs font-semibold text-primary/80">哪一列是标题</span>
                <AppSelect :options="columnSelectOptions" :value="columnMappingForm.title" placeholder="选择表里的标题列"
                  @change="columnMappingForm.title = $event" />
              </label>
              <label class="space-y-2">
                <span class="block text-xs font-semibold text-primary/80">哪一列是正文</span>
                <AppSelect :options="columnSelectOptions" :value="columnMappingForm.content" placeholder="选择表里的正文列"
                  @change="columnMappingForm.content = $event" />
              </label>
              <label class="space-y-2">
                <span class="block text-xs font-semibold text-primary/80">哪一列是作者</span>
                <AppSelect :options="columnSelectOptions" :value="columnMappingForm.author" placeholder="没有作者列可以先不选"
                  @change="columnMappingForm.author = $event" />
              </label>
            </div>

            <div v-if="mappingError || mappingSuccess" class="mt-4 rounded-2xl border px-4 py-3 text-sm" :class="mappingError
              ? 'border-rose-200 bg-rose-50 text-rose-700'
              : 'border-emerald-200 bg-emerald-50 text-emerald-700'">
              {{ mappingError || mappingSuccess }}
            </div>

            <div class="mt-5 flex flex-wrap items-center justify-between gap-3">
              <p class="text-xs text-secondary">
                保存后，后续清洗和入库会按你这里选的列来识别内容。
              </p>
              <button type="button"
                class="rounded-full bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-700 disabled:opacity-50"
                @click="saveColumnMapping" :disabled="mappingSaving">
                {{ mappingSaving ? '正在保存...' : '保存字段映射' }}
              </button>
            </div>
          </div>
        </div>
      </section>
    </transition>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { CloudArrowUpIcon, DocumentArrowUpIcon, TagIcon } from '@heroicons/vue/24/outline'
import AppCheckbox from '../../components/AppCheckbox.vue'
import AppSelect from '../../components/AppSelect.vue'
import { useApiBase } from '../../composables/useApiBase'
import {
  PLATFORM_OPTIONS,
  SCOPE_OPTIONS,
  useNetInsightTaskForm,
} from '../../composables/useNetInsightTaskForm'
import { useTopicCreationProject } from '../../composables/useTopicCreationProject'

const router = useRouter()
const { ensureApiBase, callApi } = useApiBase()
const { setSelectedProjectName, refreshProjects } = useTopicCreationProject()

const topicName = ref('')
const topicDescription = ref('')
const selectedTags = ref([])

const creating = ref(false)
const createError = ref('')
const createSuccess = ref('')

const fileInput = ref(null)
const uploadFiles = ref([])
const dragActive = ref(false)
const dragCounter = ref(0)
const uploading = ref(false)
const uploadError = ref('')
const uploadSuccess = ref('')
const uploadStatuses = ref([])
const uploadedDatasets = ref([])
const latestDataset = computed(() => {
  const list = uploadedDatasets.value
  return list.length ? list[list.length - 1] : null
})
const columnMappingForm = reactive({
  topic: '',
  date: '',
  title: '',
  content: '',
  author: ''
})
const mappingSaving = ref(false)
const mappingError = ref('')
const mappingSuccess = ref('')
const acquisition = useNetInsightTaskForm()
const acquisitionForm = acquisition.form
const acquisitionPlatformOptions = PLATFORM_OPTIONS.filter((item) => item !== '全部')
const scopeOptions = SCOPE_OPTIONS
const acquisitionPlanning = ref(false)
const acquisitionSubmitting = ref(false)
const acquisitionLoading = ref(false)
const acquisitionTasks = ref([])
const acquisitionImportingTaskId = ref('')
const acquisitionBriefTouched = ref(false)
const acquisitionFeedback = reactive({
  type: '',
  message: ''
})
const settingsState = reactive({
  credentials: {
    configured: false
  },
  runtime: {},
  planner: {}
})
const loginState = ref({ status: 'idle' })
const acquisitionRefreshTimer = ref(null)

const suggestedTags = Object.freeze([
  '舆情监测',
  '新闻采集',
  '社交媒体',
  '自动化报告',
  '关键事件',
  '专家研判'
])

const buildApiUrl = async (path) => {
  const baseUrl = await ensureApiBase()
  return `${baseUrl}${path}`
}

const canUpload = computed(() => Boolean(createSuccess.value))
const canSubmitAcquisition = computed(() => canUpload.value && acquisition.canSubmit.value)

const uploadHelper = computed(() => {
  if (uploading.value) return ''
  if (!canUpload.value) return '请先创建专题后再操作'
  if (!topicName.value) return '请先填写专题名称'
  if (!uploadFiles.value.length) return '请选择需要上传的文件'
  return ''
})

const uploadProgress = computed(() => {
  const total = uploadStatuses.value.length
  if (!total) {
    return { total: 0, completed: 0, percent: 0, running: false }
  }
  const completed = uploadStatuses.value.filter((item) => ['success', 'error'].includes(item.status)).length
  const running = uploadStatuses.value.some((item) => item.status === 'uploading')
  const percent = Math.round((completed / total) * 100)
  return { total, completed, percent, running }
})

const uploadActiveMessage = computed(() => {
  const total = uploadProgress.value.total
  if (!total) return '正在准备上传文件'
  return total === 1
    ? `正在上传 1 个文件，请稍候`
    : `正在上传 ${total} 个文件，请稍候`
})

const uploadProgressMessage = computed(() => {
  const { completed, total } = uploadProgress.value
  if (!total) return '上传开始后，这里会持续显示处理结果。'
  if (completed >= total) return '文件已传输完成，正在整理结果。'
  const remaining = Math.max(total - completed, 0)
  return `已完成 ${completed} / ${total}，剩余 ${remaining} 个文件。每个文件的结果会显示在上方进度列表中。`
})

const hasMultipleDatasets = computed(() => uploadedDatasets.value.length > 1)

const datasetColumns = computed(() => {
  const batches = uploadedDatasets.value
  if (!batches.length) {
    return []
  }
  const columnSets = batches.map((dataset) => {
    if (!dataset || !Array.isArray(dataset.columns)) return []
    return dataset.columns.map((column) => column.toString())
  })
  if (!columnSets.length) return []
  return columnSets.reduce((acc, columns) => {
    if (!acc.length) return columns
    return acc.filter((column) => columns.includes(column))
  }, columnSets[0])
})

const columnSelectOptions = computed(() =>
  datasetColumns.value.map(col => ({ value: col, label: col }))
)

const mappingTargets = computed(() => uploadedDatasets.value)

const tagPrefix = computed(() => {
  if (!selectedTags.value.length) return ''
  return selectedTags.value.map((item) => `#${item}`).join(' · ')
})

const descriptionPayload = computed(() => {
  const prefix = tagPrefix.value
  const body = topicDescription.value.trim()
  if (prefix && body) {
    return `${prefix}\n\n${body}`
  }
  return prefix || body
})

const acquisitionBriefDefault = computed(() => {
  const parts = []
  if (topicName.value.trim()) {
    parts.push(`专题：${topicName.value.trim()}`)
  }
  if (descriptionPayload.value.trim()) {
    parts.push(descriptionPayload.value.trim())
  }
  return parts.join('\n\n')
})

const toggleTag = (tag) => {
  if (selectedTags.value.includes(tag)) {
    selectedTags.value = selectedTags.value.filter((item) => item !== tag)
  } else {
    selectedTags.value = [...selectedTags.value, tag]
  }
}

const formatFileSize = (value) => {
  const bytes = Number(value)
  if (!Number.isFinite(bytes) || bytes <= 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const size = bytes / Math.pow(1024, exponent)
  return `${size.toFixed(size >= 100 || exponent === 0 ? 0 : 1)} ${units[exponent]}`
}

const datetimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit'
})

const formatTimestamp = (value) => {
  if (!value) return '—'
  try {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return value
    return datetimeFormatter.format(date)
  } catch (error) {
    return value
  }
}

const applyDatasetMapping = (dataset) => {
  if (!dataset || typeof dataset !== 'object') {
    columnMappingForm.date = ''
    columnMappingForm.title = ''
    columnMappingForm.content = ''
    columnMappingForm.author = ''
    columnMappingForm.topic = ''
    mappingError.value = ''
    mappingSuccess.value = ''
    return
  }
  const mapping = typeof dataset.column_mapping === 'object' && dataset.column_mapping !== null
    ? dataset.column_mapping
    : {}
  columnMappingForm.topic = typeof dataset.topic_label === 'string' ? dataset.topic_label.trim() : ''
  columnMappingForm.date = mapping.date || ''
  columnMappingForm.title = mapping.title || ''
  columnMappingForm.content = mapping.content || ''
  columnMappingForm.author = mapping.author || ''
  mappingError.value = ''
}

const updateUploadedDataset = (datasetId, updates) => {
  uploadedDatasets.value = uploadedDatasets.value.map((dataset) => {
    if (dataset.id !== datasetId) return dataset
    return {
      ...dataset,
      ...updates
    }
  })
}

const saveColumnMapping = async () => {
  const targets = mappingTargets.value
  if (!targets.length || !topicName.value) return
  mappingSaving.value = true
  mappingError.value = ''
  mappingSuccess.value = ''

  const payload = {
    column_mapping: {
      date: columnMappingForm.date || '',
      title: columnMappingForm.title || '',
      content: columnMappingForm.content || '',
      author: columnMappingForm.author || ''
    },
    topic_label: columnMappingForm.topic || ''
  }

  const failures = []
  let successCount = 0

  for (const dataset of targets) {
    try {
      const endpoint = await buildApiUrl(
        `/projects/${encodeURIComponent(dataset.project)}/datasets/${encodeURIComponent(dataset.id)}/mapping`
      )
      const response = await fetch(endpoint, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })
      const result = await response.json()
      if (!response.ok || result.status !== 'ok') {
        throw new Error(result.message || '字段映射保存失败')
      }
      successCount += 1
      const nextTopicLabel = typeof result.topic_label === 'string' ? result.topic_label : payload.topic_label
      updateUploadedDataset(dataset.id, {
        column_mapping: result.column_mapping,
        topic_label: typeof nextTopicLabel === 'string' ? nextTopicLabel.trim() : ''
      })
    } catch (err) {
      failures.push({
        dataset,
        message: err instanceof Error ? err.message : '字段映射保存失败'
      })
    }
  }

  if (failures.length) {
    const failedNames = failures.map((failure) => failure.dataset.display_name || failure.dataset.id).join('、')
    mappingError.value =
      failures.length === targets.length
        ? `所有数据集字段映射保存失败：${failures[0].message}`
        : `部分数据集字段映射保存失败（${failedNames}），请检查后重试。`
  } else if (successCount) {
    mappingSuccess.value =
      successCount === 1 ? '字段映射已保存' : `字段映射已同步至 ${successCount} 个数据集`
    const firstTopic = uploadedDatasets.value[uploadedDatasets.value.length - 1]?.topic_label
    columnMappingForm.topic = typeof firstTopic === 'string' ? firstTopic.trim() : columnMappingForm.topic
  }

  mappingSaving.value = false
}

watch(
  latestDataset,
  (dataset, previous) => {
    const previousId = previous && typeof previous === 'object' ? previous.id : ''
    applyDatasetMapping(dataset)
    if (!dataset || dataset.id !== previousId) {
      mappingSuccess.value = ''
    }
  },
  { immediate: true }
)

watch(topicName, (current, previous) => {
  if (current !== previous && createSuccess.value) {
    createSuccess.value = ''
  }
  if (current !== previous) {
    acquisitionTasks.value = []
    uploadedDatasets.value = []
    acquisitionFeedback.message = ''
  }
})

onMounted(async () => {
  await Promise.all([fetchNetInsightSettings(), fetchNetInsightLoginState()])
  acquisition.resetForm(settingsState)
})

onBeforeUnmount(() => {
  stopAcquisitionRefreshLoop()
})

const createTopic = async () => {
  if (!topicName.value) return
  creating.value = true
  createError.value = ''
  createSuccess.value = ''

  try {
    const endpoint = await buildApiUrl('/projects')
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        name: topicName.value,
        description: descriptionPayload.value || undefined,
        metadata: selectedTags.value.length ? { tags: selectedTags.value } : undefined
      })
    })

    const result = await response.json()
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '专题创建失败')
    }
    const createdProjectName =
      typeof result.project?.name === 'string' && result.project.name.trim()
        ? result.project.name.trim()
        : topicName.value.trim()
    setSelectedProjectName(createdProjectName)
    await refreshProjects()
    createSuccess.value = '专题创建成功，可以继续上传数据。'
    prepareAcquisitionDefaults()
    await planAcquisitionTask(false)
    await fetchAcquisitionTasks()
  } catch (err) {
    createError.value = err instanceof Error ? err.message : '专题创建失败'
  } finally {
    creating.value = false
  }
}

const prepareAcquisitionDefaults = () => {
  if (!topicName.value.trim()) return
  acquisition.resetForm(settingsState, {
    title: `${topicName.value.trim()} 数据采集`,
    project: topicName.value.trim(),
    brief: acquisitionBriefTouched.value && acquisitionForm.brief.trim()
      ? acquisitionForm.brief
      : acquisitionBriefDefault.value,
  })
}

const fetchNetInsightSettings = async () => {
  try {
    const response = await callApi('/api/settings/netinsight', { method: 'GET' })
    const payload = response?.data || {}
    Object.assign(settingsState.credentials, payload.credentials || {})
    settingsState.runtime = payload.runtime || {}
    settingsState.planner = payload.planner || {}
  } catch {
    settingsState.credentials.configured = false
  }
}

const fetchNetInsightLoginState = async () => {
  try {
    const response = await callApi('/api/netinsight/login', { method: 'GET' })
    loginState.value = response?.data || { status: 'idle' }
  } catch {
    loginState.value = { status: 'idle' }
  }
}

const planAcquisitionTask = async (forceApply = true) => {
  if (!canUpload.value || acquisitionPlanning.value) return
  if (!acquisitionForm.brief.trim()) {
    acquisitionForm.brief = acquisitionBriefDefault.value
  }
  if (!acquisitionForm.brief.trim()) return

  acquisitionPlanning.value = true
  acquisitionFeedback.type = ''
  acquisitionFeedback.message = ''
  try {
    const response = await callApi('/api/netinsight/tasks/plan', {
      method: 'POST',
      body: JSON.stringify({ brief: acquisitionForm.brief })
    })
    const plan = response?.data || {}
    if (forceApply || !acquisitionForm.keywordsText.trim()) {
      acquisition.applyPlan(plan)
      acquisitionForm.project = topicName.value.trim()
    }
    acquisitionFeedback.type = 'success'
    acquisitionFeedback.message = '已生成推荐配置，可继续手动调整。'
  } catch (err) {
    acquisitionFeedback.type = 'error'
    acquisitionFeedback.message = err instanceof Error ? err.message : '智能推荐失败'
  } finally {
    acquisitionPlanning.value = false
  }
}

const setAcquisitionScope = (scope) => {
  acquisition.setScope(scope)
}

const submitAcquisitionTask = async () => {
  if (!canSubmitAcquisition.value || acquisitionSubmitting.value) return
  acquisitionSubmitting.value = true
  acquisitionFeedback.type = ''
  acquisitionFeedback.message = ''
  try {
    const payload = acquisition.buildPayload({
      title: acquisitionForm.title || `${topicName.value.trim()} 数据采集`,
      project: topicName.value.trim(),
      auto_import_project: true,
    })
    const response = await callApi('/api/netinsight/tasks', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
    const task = response?.data?.task
    if (task?.id) {
      acquisitionTasks.value = [task, ...acquisitionTasks.value.filter((item) => item.id !== task.id)]
    }
    acquisitionFeedback.type = 'success'
    acquisitionFeedback.message = '采集任务已提交，完成后会自动传输到当前专题。'
    startAcquisitionRefreshLoop()
    await fetchAcquisitionTasks()
  } catch (err) {
    acquisitionFeedback.type = 'error'
    acquisitionFeedback.message = err instanceof Error ? err.message : '采集任务提交失败'
  } finally {
    acquisitionSubmitting.value = false
  }
}

const fetchAcquisitionTasks = async () => {
  if (!topicName.value.trim()) return
  acquisitionLoading.value = true
  try {
    const response = await callApi(
      `/api/netinsight/tasks?project=${encodeURIComponent(topicName.value.trim())}&limit=20`,
      { method: 'GET' }
    )
    const payload = response?.data || {}
    acquisitionTasks.value = Array.isArray(payload.tasks) ? payload.tasks : []
    syncImportedDatasetsFromTasks()
  } catch (err) {
    acquisitionFeedback.type = 'error'
    acquisitionFeedback.message = err instanceof Error ? err.message : '读取采集任务失败'
  } finally {
    acquisitionLoading.value = false
  }
}

const importAcquisitionTask = async (task) => {
  if (!task?.id || acquisitionImportingTaskId.value) return
  acquisitionImportingTaskId.value = task.id
  acquisitionFeedback.type = ''
  acquisitionFeedback.message = ''
  try {
    const response = await callApi(`/api/netinsight/tasks/${encodeURIComponent(task.id)}/import-to-project`, {
      method: 'POST',
      body: JSON.stringify({ project: topicName.value.trim(), force: true })
    })
    const updatedTask = response?.data?.task
    if (updatedTask?.id) {
      acquisitionTasks.value = acquisitionTasks.value.map((item) => item.id === updatedTask.id ? updatedTask : item)
    }
    syncImportedDatasetsFromTasks()
    acquisitionFeedback.type = 'success'
    acquisitionFeedback.message = '采集结果已传输到当前专题。'
  } catch (err) {
    acquisitionFeedback.type = 'error'
    acquisitionFeedback.message = err instanceof Error ? err.message : '采集结果传输失败'
  } finally {
    acquisitionImportingTaskId.value = ''
  }
}

const syncImportedDatasetsFromTasks = () => {
  const existingIds = new Set(uploadedDatasets.value.map((dataset) => dataset?.id).filter(Boolean))
  const imported = []
  acquisitionTasks.value.forEach((task) => {
    const projectImport = task?.output?.project_import
    const dataset = projectImport?.status === 'completed' ? normaliseDatasetPayload(projectImport.dataset) : null
    if (dataset?.id && !existingIds.has(dataset.id)) {
      existingIds.add(dataset.id)
      imported.push(dataset)
    }
  })
  if (imported.length) {
    uploadedDatasets.value = [...uploadedDatasets.value, ...imported]
    const latestProjectName = imported[imported.length - 1]?.project || topicName.value.trim()
    if (latestProjectName) {
      setSelectedProjectName(latestProjectName)
      void refreshProjects()
    }
  }
}

const acquisitionTaskStatusLabel = (status) => ({
  queued: '排队中',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消'
}[status] || '未知')

const acquisitionTaskStatusClass = (status) => ({
  queued: 'bg-gray-100 text-secondary',
  running: 'bg-brand-50 text-brand-700',
  completed: 'bg-emerald-50 text-emerald-700',
  failed: 'bg-rose-50 text-rose-700',
  cancelled: 'bg-amber-50 text-amber-700'
}[status] || 'bg-gray-100 text-secondary')

const acquisitionTaskSummary = (task) => {
  const count = Number(task?.output?.project_import?.dataset?.rows || task?.output?.deduplicated_count || task?.progress?.deduped_total || 0)
  const importStatus = task?.output?.project_import?.status
  if (importStatus === 'completed') return `已传输 ${count} 条数据，可继续设置字段映射。`
  if (importStatus === 'failed') return task?.output?.project_import?.message || '采集完成，传输失败，可手动重试。'
  return task?.progress?.message || '等待任务进度更新。'
}

const canImportAcquisitionTask = (task) => {
  if (task?.status !== 'completed') return false
  const importStatus = task?.output?.project_import?.status
  return importStatus !== 'completed'
}

const startAcquisitionRefreshLoop = () => {
  stopAcquisitionRefreshLoop()
  acquisitionRefreshTimer.value = window.setInterval(() => {
    const hasActive = acquisitionTasks.value.some((task) => ['queued', 'running'].includes(task.status))
    if (hasActive) {
      void fetchAcquisitionTasks()
    }
  }, 5000)
}

const stopAcquisitionRefreshLoop = () => {
  if (acquisitionRefreshTimer.value) {
    window.clearInterval(acquisitionRefreshTimer.value)
    acquisitionRefreshTimer.value = null
  }
}

const goNetInsightSettings = () => {
  router.push({ name: 'settings-netinsight' })
}

const selectedFileSummary = computed(() => {
  if (!uploadFiles.value.length) return ''
  if (uploadFiles.value.length === 1) return uploadFiles.value[0].name
  if (uploadFiles.value.length === 2) return `${uploadFiles.value[0].name}、${uploadFiles.value[1].name}`
  return `${uploadFiles.value[0].name} 等 ${uploadFiles.value.length} 个文件`
})

const resetFileInput = () => {
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

const addSelectedFiles = (files) => {
  if (!files.length) return false
  const existingKeys = new Set(
    uploadFiles.value.map((file) => `${file.name}-${file.size}-${file.lastModified}`)
  )
  const next = uploadFiles.value.slice()
  files.forEach((file) => {
    const key = `${file.name}-${file.size}-${file.lastModified}`
    if (!existingKeys.has(key)) {
      existingKeys.add(key)
      next.push(file)
    }
  })
  if (next.length === uploadFiles.value.length) {
    return false
  }
  uploadFiles.value = next
  uploadError.value = ''
  uploadSuccess.value = ''
  uploadedDatasets.value = []
  uploadStatuses.value = []
  return true
}

const handleFileChange = (event) => {
  const files = Array.from(event?.target?.files || [])
  addSelectedFiles(files)
  resetFileInput()
}

const clearSelectedFiles = ({ resetStatuses = true } = {}) => {
  uploadFiles.value = []
  resetFileInput()
  if (resetStatuses) {
    uploadStatuses.value = []
  }
}

const removeSelectedFile = (index) => {
  if (index < 0 || index >= uploadFiles.value.length) return
  const next = uploadFiles.value.slice()
  next.splice(index, 1)
  uploadFiles.value = next
  if (!next.length) {
    resetFileInput()
  }
}

const handleDragEnter = (event) => {
  event?.preventDefault?.()
  dragCounter.value += 1
  dragActive.value = true
}

const handleDragOver = (event) => {
  event?.preventDefault?.()
  if (!dragActive.value) {
    dragActive.value = true
  }
}

const handleDragLeave = (event) => {
  event?.preventDefault?.()
  dragCounter.value = Math.max(dragCounter.value - 1, 0)
  if (dragCounter.value === 0) {
    dragActive.value = false
  }
}

const handleDrop = (event) => {
  event?.preventDefault?.()
  const files = Array.from(event?.dataTransfer?.files || [])
  dragCounter.value = 0
  dragActive.value = false
  if (addSelectedFiles(files)) {
    resetFileInput()
  }
}

const normaliseDatasetPayload = (dataset) => {
  if (!dataset || typeof dataset !== 'object') return null
  return {
    ...dataset,
    topic_label: typeof dataset.topic_label === 'string' ? dataset.topic_label.trim() : ''
  }
}

const uploadDataset = async () => {
  if (!topicName.value) {
    uploadError.value = '请填写专题名称后再上传'
    return
  }
  if (!uploadFiles.value.length) {
    uploadError.value = '请选择需要上传的文件'
    return
  }

  uploading.value = true
  uploadError.value = ''
  uploadSuccess.value = ''

  uploadStatuses.value = uploadFiles.value.map((file, index) => ({
    key: `${file.name}-${file.size}-${file.lastModified}-${index}`,
    name: file.name,
    status: 'pending',
    message: '排队中'
  }))

  const endpoint = await buildApiUrl(`/projects/${encodeURIComponent(topicName.value)}/datasets`)
  const successes = []
  const failures = []

  for (const [index, file] of uploadFiles.value.entries()) {
    const formData = new FormData()
    formData.append('file', file)
    try {
      if (uploadStatuses.value[index]) {
        uploadStatuses.value[index].status = 'uploading'
        uploadStatuses.value[index].message = '上传中…'
      }
      const response = await fetch(endpoint, {
        method: 'POST',
        body: formData
      })
      const result = await response.json()
      if (!response.ok || result.status !== 'ok') {
        throw new Error(result.message || '上传失败')
      }
      const uploadedDatasetsRaw = Array.isArray(result.datasets)
        ? result.datasets
        : result.dataset
          ? [result.dataset]
          : []
      const datasetEntries = uploadedDatasetsRaw
        .map(normaliseDatasetPayload)
        .filter((dataset) => Boolean(dataset))
      const dataset = datasetEntries.length ? datasetEntries[datasetEntries.length - 1] : null
      successes.push({ file, dataset })
      if (uploadStatuses.value[index]) {
        uploadStatuses.value[index].status = 'success'
        uploadStatuses.value[index].message = '上传完成'
      }
    } catch (err) {
      failures.push({ file, message: err instanceof Error ? err.message : '上传失败' })
      if (uploadStatuses.value[index]) {
        uploadStatuses.value[index].status = 'error'
        uploadStatuses.value[index].message = err instanceof Error ? err.message : '上传失败'
      }
    }
  }

  const succeededDatasets = successes
    .map((entry) => entry.dataset)
    .filter((dataset) => dataset && typeof dataset === 'object')

  uploadedDatasets.value = succeededDatasets

  if (successes.length) {
    const latestProjectName =
      typeof succeededDatasets[succeededDatasets.length - 1]?.project === 'string' &&
      succeededDatasets[succeededDatasets.length - 1].project.trim()
        ? succeededDatasets[succeededDatasets.length - 1].project.trim()
        : topicName.value.trim()
    if (latestProjectName) {
      setSelectedProjectName(latestProjectName)
      await refreshProjects()
    }
    const successMessage =
      successes.length === 1
        ? `已成功上传 ${successes[0].file.name}`
        : `已成功上传 ${successes.length} 个文件`
    uploadSuccess.value = failures.length
      ? `${successMessage}，${failures.length} 个文件需要重试。`
      : `${successMessage}，已生成 JSONL 与 PKL 存档。`
  } else {
    uploadSuccess.value = ''
  }

  if (failures.length) {
    const failedNames = failures.map((entry) => entry.file?.name || '未知文件').join('、')
    const lastError = failures[failures.length - 1]?.message || '上传失败'
    uploadError.value =
      failures.length === uploadFiles.value.length
        ? `全部上传失败：${lastError}（${failedNames}）`
        : `部分文件上传失败：${lastError}（${failedNames}）`

    uploadFiles.value = failures.map((entry) => entry.file).filter((file) => Boolean(file))
    resetFileInput()
  } else {
    uploadError.value = ''
    clearSelectedFiles({ resetStatuses: false })
  }

  uploading.value = false
}
</script>

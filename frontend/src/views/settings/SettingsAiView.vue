<template>
  <section class="card-surface space-y-6 p-6">
      <header class="settings-page-header">
        <p class="settings-page-eyebrow">AI 服务</p>
        <h2 class="settings-page-title">AI 服务配置</h2>
        <p class="settings-page-desc">管理模型接入、对话模型和报告设置。</p>
      </header>

      <p v-if="llmState.error || credentialState.error" class="settings-message-error">
        {{ llmState.error || credentialState.error }}
      </p>
      <p
        v-if="llmState.message || credentialState.message"
        class="settings-message-success"
      >
        {{ llmState.message || credentialState.message }}
      </p>

      <section class="settings-section">
        <div class="flex items-center gap-3">
          <div class="flex h-8 w-8 items-center justify-center rounded-xl bg-brand-soft">
            <KeyIcon class="h-4 w-4 text-brand" />
          </div>
          <div>
            <h3 class="text-sm font-semibold text-primary">凭证</h3>
            <p class="text-xs text-muted">保存通义千问和 OpenAI 兼容接口的访问凭证与默认地址。</p>
          </div>
        </div>
        <div class="space-y-8">
          <div class="grid gap-8 md:grid-cols-2">
            <div class="space-y-3">
              <label class="block text-sm font-medium text-secondary ml-1">DashScope API Key（通义千问）</label>
              <div class="relative">
                <input
                  v-model.trim="credentialState.form.qwen_api_key"
                  type="password"
                  autocomplete="new-password"
                  placeholder="sk-..."
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
                <div class="absolute inset-y-0 right-3 flex items-center">
                  <span
                    v-if="credentialState.summary.qwen.configured"
                    class="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-2.5 py-1 text-xs font-medium text-success ring-1 ring-success-500/10"
                  >
                    <CheckIcon class="w-3.5 h-3.5" />
                    已配置
                  </span>
                  <span
                    v-else
                    class="inline-flex items-center gap-1 rounded-full bg-surface-muted px-2.5 py-1 text-xs font-medium text-muted"
                  >
                    未配置
                  </span>
                </div>
              </div>
              <div v-if="credentialState.summary.qwen.configured" class="flex justify-end pr-1">
                <button
                  type="button"
                  class="text-xs font-medium text-muted transition-colors hover:text-danger"
                  @click="clearCredential('qwen')"
                >
                  清除密钥
                </button>
              </div>
            </div>

            <div class="space-y-3">
              <label class="block text-sm font-medium text-secondary ml-1">OpenAI API Key（兼容接口）</label>
              <div class="relative">
                <input
                  v-model.trim="credentialState.form.openai_api_key"
                  type="password"
                  autocomplete="new-password"
                  placeholder="sk-..."
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
                <div class="absolute inset-y-0 right-3 flex items-center">
                  <span
                    v-if="credentialState.summary.openai.configured"
                    class="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-2.5 py-1 text-xs font-medium text-success ring-1 ring-success-500/10"
                  >
                    <CheckIcon class="w-3.5 h-3.5" />
                    已配置
                  </span>
                  <span
                    v-else
                    class="inline-flex items-center gap-1 rounded-full bg-surface-muted px-2.5 py-1 text-xs font-medium text-muted"
                  >
                    未配置
                  </span>
                </div>
              </div>
              <div v-if="credentialState.summary.openai.configured" class="flex justify-end pr-1">
                <button
                  type="button"
                  class="text-xs font-medium text-muted transition-colors hover:text-danger"
                  @click="clearCredential('openai')"
                >
                  清除密钥
                </button>
              </div>
            </div>
          </div>

          <div class="border-t border-soft/60 pt-6 space-y-4">
            <div class="space-y-2">
              <label class="block text-sm font-medium text-secondary ml-1">OpenAI 兼容接口地址</label>
              <input
                v-model.trim="credentialState.form.openai_base_url"
                type="text"
                placeholder="https://api.openai.com/v1"
                class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
              />
              <p class="text-xs text-muted ml-1">只在使用第三方代理或自建兼容服务时需要修改，留空会使用默认地址。</p>
            </div>
            <div class="flex justify-end">
              <button
                type="button"
                class="btn-primary rounded-full px-6 py-3"
                :disabled="credentialState.loading"
                @click="submitCredentials"
              >
                <span v-if="credentialState.loading">保存中...</span>
                <span v-else>保存凭证</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      <section class="settings-section border-t border-soft/60 pt-6">
        <div class="flex items-center gap-3">
          <div class="flex h-8 w-8 items-center justify-center rounded-xl bg-brand-soft">
            <CpuChipIcon class="h-4 w-4 text-brand" />
          </div>
          <div>
            <h3 class="text-sm font-semibold text-primary">调用模型</h3>
            <p class="text-xs text-muted">配置对话、筛选和向量模型，也可以查看知识库参考说明。</p>
          </div>
        </div>
        <div class="grid gap-6 xl:grid-cols-12">
          <form
            @submit.prevent="submitLlmAssistant"
            class="space-y-5 rounded-3xl border border-soft/70 bg-surface-muted/35 p-5 xl:col-span-7"
          >
            <div class="space-y-1">
              <h3 class="text-base font-semibold text-primary">对话模型</h3>
              <p class="text-sm text-muted">用于 AI 助手问答和知识库对话。</p>
            </div>
            <div class="grid gap-5 md:grid-cols-2">
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">服务提供方</label>
                <select
                  v-model="llmState.assistant.provider"
                  class="form-select w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 cursor-pointer"
                >
                  <option v-for="opt in providerOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
              </div>

              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">模型名称</label>
                <input
                  v-model.trim="llmState.assistant.model"
                  type="text"
                  :placeholder="assistantModelPlaceholder"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>

              <div v-if="llmState.assistant.provider === 'openai'" class="md:col-span-2">
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">请求地址</label>
                <input
                  v-model.trim="llmState.assistant.base_url"
                  type="text"
                  placeholder="继承全局设置"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>

              <div class="md:col-span-2">
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">系统提示词</label>
                <textarea
                  v-model.trim="llmState.assistant.system_prompt"
                  rows="3"
                  placeholder="如：你是一个专业的舆情分析助手，请结合提供的知识库内容回答问题。"
                  class="form-textarea w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50 resize-none"
                ></textarea>
                <p class="mt-2 text-xs text-muted ml-1">用来定义助手的角色、语气和回答边界。</p>
              </div>

              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">最大输出</label>
                <input
                  v-model.number="llmState.assistant.max_tokens"
                  type="number"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">Temperature</label>
                <input
                  v-model.number="llmState.assistant.temperature"
                  type="number"
                  step="0.1"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
            </div>
            <div class="flex justify-end">
              <button type="submit" class="btn-primary rounded-full px-5 py-2.5">保存对话配置</button>
            </div>
          </form>

          <div class="space-y-4 rounded-3xl border border-soft/70 bg-surface-muted/35 p-5 xl:col-span-5">
            <div class="space-y-1">
              <h3 class="text-base font-semibold text-primary">知识库参考</h3>
              <p class="text-sm text-muted">对话时会参考你整理好的共享资料。</p>
            </div>
            <div class="rounded-2xl bg-base-soft p-4 space-y-3 text-sm text-secondary">
              <p>把研究文档、业务说明或标准材料整理成共享资料后，新的提问会自动参考最新内容。</p>
              <p>资料较多时，优先保留最常用、最权威的版本，引用会更稳定。</p>
              <p>配合系统提示词一起使用，回答会更贴近你的业务口径。</p>
            </div>
          </div>

          <form
            @submit.prevent="submitLlmFilter"
            class="space-y-5 rounded-3xl border border-soft/70 bg-surface-muted/35 p-5 xl:col-span-6"
          >
            <div class="space-y-1">
              <h3 class="text-base font-semibold text-primary">筛选模型</h3>
              <p class="text-sm text-muted">用于数据清洗、相关性判断和批量筛选。</p>
            </div>
            <div class="grid gap-5 md:grid-cols-2">
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">服务提供方</label>
                <select
                  v-model="llmState.filter.provider"
                  class="form-select w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 cursor-pointer"
                >
                  <option v-for="opt in providerOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
              </div>
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">模型名称</label>
                <input
                  v-model.trim="llmState.filter.model"
                  type="text"
                  :placeholder="filterModelPlaceholder"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
              <div v-if="llmState.filter.provider === 'openai'" class="md:col-span-2">
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">请求地址</label>
                <input
                  v-model.trim="llmState.filter.base_url"
                  type="text"
                  placeholder="继承全局设置"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">QPS 限制</label>
                <input
                  v-model.number="llmState.filter.qps"
                  type="number"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">批处理数量</label>
                <input
                  v-model.number="llmState.filter.batch_size"
                  type="number"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
            </div>
            <div class="flex justify-end">
              <button type="submit" class="btn-primary rounded-full px-5 py-2.5">保存筛选配置</button>
            </div>
          </form>

          <form
            @submit.prevent="submitLlmEmbedding"
            class="space-y-5 rounded-3xl border border-soft/70 bg-surface-muted/35 p-5 xl:col-span-6"
          >
            <div class="space-y-1">
              <h3 class="text-base font-semibold text-primary">向量模型</h3>
              <p class="text-sm text-muted">用于检索增强生成和向量化分析。</p>
            </div>
            <div class="grid gap-5 md:grid-cols-2">
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">服务提供方</label>
                <select
                  v-model="llmState.embedding.provider"
                  class="form-select w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 cursor-pointer"
                >
                  <option v-for="opt in providerOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
              </div>
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">模型名称</label>
                <input
                  v-model.trim="llmState.embedding.model"
                  type="text"
                  :placeholder="embeddingModelPlaceholder"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
              <div v-if="llmState.embedding.provider === 'openai'" class="md:col-span-2">
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">请求地址</label>
                <input
                  v-model.trim="llmState.embedding.base_url"
                  type="text"
                  placeholder="继承全局设置"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">向量维度</label>
                <input
                  v-model.number="llmState.embedding.dimension"
                  type="number"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
            </div>
            <div class="flex justify-end">
              <button type="submit" class="btn-primary rounded-full px-5 py-2.5">保存向量配置</button>
            </div>
          </form>
        </div>
      </section>

      <section class="settings-section border-t border-soft/60 pt-6">
        <div class="flex items-center gap-3">
          <div class="flex h-8 w-8 items-center justify-center rounded-xl bg-brand-soft">
            <AdjustmentsHorizontalIcon class="h-4 w-4 text-brand" />
          </div>
          <div>
            <h3 class="text-sm font-semibold text-primary">功能模型</h3>
            <p class="text-xs text-muted">这些设置会影响报告生成、摘要整理等默认功能链路。</p>
          </div>
        </div>
        <form @submit.prevent="submitLlmLangchain" class="space-y-6">
          <div class="space-y-1">
            <h3 class="text-lg font-semibold text-primary">通用功能模型</h3>
            <p class="text-sm text-muted">设置报告和摘要默认使用的模型与请求入口。</p>
          </div>

          <div class="space-y-5">
            <div>
              <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">调用入口</label>
              <select
                v-model="langchainBaseUrlMode"
                class="form-select w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 cursor-pointer"
              >
                <option value="dashscope">阿里云 DashScope</option>
                <option value="openai">OpenAI 官方</option>
                <option value="custom">自定义兼容接口</option>
              </select>
            </div>

            <div>
              <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">默认模型</label>
              <input
                v-model.trim="llmState.langchain.model"
                type="text"
                :placeholder="featureModelPlaceholder"
                class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
              />
            </div>

            <div class="grid gap-6 md:grid-cols-2">
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">报告生成模型</label>
                <input
                  v-model.trim="llmState.langchain.report_model"
                  type="text"
                  placeholder="留空时跟随默认模型"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">摘要整理模型</label>
                <input
                  v-model.trim="llmState.langchain.analyze_summary_model"
                  type="text"
                  placeholder="留空时跟随默认模型"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
            </div>

            <div>
              <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">
                {{ langchainBaseUrlMode === 'custom' ? '自定义请求地址' : '当前请求地址' }}
              </label>
              <input
                v-if="langchainBaseUrlMode === 'custom'"
                v-model.trim="llmState.langchain.base_url"
                type="text"
                placeholder="请输入 OpenAI 兼容接口地址"
                class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
              />
              <input
                v-else
                :value="effectiveLangchainBaseUrl"
                type="text"
                disabled
                class="form-input w-full rounded-2xl border-0 bg-base-soft/70 px-4 py-3 text-sm text-muted cursor-not-allowed"
              />
            </div>

            <div v-if="langchainBaseUrlMode === 'custom'" class="rounded-2xl bg-base-soft px-4 py-3 text-xs text-muted">
              请输入可直接调用的 OpenAI 兼容地址。
            </div>

            <div class="grid gap-6 md:grid-cols-2">
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">Temperature</label>
                <input
                  v-model.number="llmState.langchain.temperature"
                  type="number"
                  step="0.1"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">最大输出</label>
                <input
                  v-model.number="llmState.langchain.max_tokens"
                  type="number"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">超时（秒）</label>
                <input
                  v-model.number="llmState.langchain.timeout"
                  type="number"
                  step="1"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">重试次数</label>
                <input
                  v-model.number="llmState.langchain.max_retries"
                  type="number"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
            </div>
          </div>

          <div class="flex justify-end">
            <button type="submit" class="btn-primary rounded-full px-6 py-3">保存功能模型</button>
          </div>
        </form>
      </section>

      <section class="settings-section border-t border-soft/60 pt-6">
        <div class="flex items-center gap-3">
          <div class="flex h-8 w-8 items-center justify-center rounded-xl bg-brand-soft">
            <DocumentTextIcon class="h-4 w-4 text-brand" />
          </div>
          <div>
            <h3 class="text-sm font-semibold text-primary">报告专用接入</h3>
            <p class="text-xs text-muted">为报告单独设置模型、请求地址和专用密钥。</p>
          </div>
        </div>
        <form @submit.prevent="submitReportRuntime" class="space-y-6">
          <div class="space-y-1">
            <h3 class="text-lg font-semibold text-primary">独立模型与密钥</h3>
            <p class="text-sm text-muted">需要单独维护报告链路时，在这里覆盖设置即可。</p>
          </div>

          <div class="space-y-5">
            <div class="grid gap-6 md:grid-cols-2">
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">服务提供方</label>
                <select
                  v-model="reportRuntime.provider"
                  class="form-select w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 cursor-pointer"
                >
                  <option v-for="opt in providerOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
              </div>

              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">模型名称</label>
                <input
                  v-model.trim="reportRuntime.model"
                  type="text"
                  :placeholder="reportRuntimeModelPlaceholder"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
            </div>

            <div>
              <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">请求地址</label>
              <input
                v-model.trim="reportRuntime.base_url"
                type="text"
                placeholder="如：https://dashscope.aliyuncs.com/compatible-mode/v1"
                class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
              />
              <p class="mt-2 text-xs text-muted ml-1">如果报告要走单独入口，在这里填写地址。</p>
            </div>

            <div class="space-y-3">
              <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">报告专用 API Key</label>
              <div class="relative">
                <input
                  v-model.trim="reportRuntime.api_key"
                  type="password"
                  autocomplete="new-password"
                  placeholder="留空表示保留当前已保存的密钥"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 pr-28 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
                <div class="absolute inset-y-0 right-3 flex items-center">
                  <span
                    v-if="reportRuntime.api_key_summary.configured"
                    class="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-2.5 py-1 text-xs font-medium text-success ring-1 ring-success-500/10"
                  >
                    <CheckIcon class="w-3.5 h-3.5" />
                    已配置
                  </span>
                  <span
                    v-else
                    class="inline-flex items-center gap-1 rounded-full bg-surface-muted px-2.5 py-1 text-xs font-medium text-muted"
                  >
                    未配置
                  </span>
                </div>
              </div>
              <div class="flex items-center justify-between gap-3">
                <p class="text-xs text-muted ml-1">如果你要切换到新的报告账号，直接在这里覆盖保存即可。</p>
                <button
                  v-if="reportRuntime.api_key_summary.configured"
                  type="button"
                  class="text-xs font-medium text-muted transition-colors hover:text-danger"
                  @click="clearReportRuntimeApiKey"
                >
                  清除专用密钥
                </button>
              </div>
            </div>

            <div class="grid gap-6 md:grid-cols-2">
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">Temperature</label>
                <input
                  v-model.number="reportRuntime.temperature"
                  type="number"
                  step="0.1"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">最大输出</label>
                <input
                  v-model.number="reportRuntime.max_tokens"
                  type="number"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">超时（秒）</label>
                <input
                  v-model.number="reportRuntime.timeout"
                  type="number"
                  step="1"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
              <div>
                <label class="block text-xs font-bold uppercase tracking-wider text-muted mb-2 ml-1">重试次数</label>
                <input
                  v-model.number="reportRuntime.max_retries"
                  type="number"
                  class="form-input w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm transition-all focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted/50"
                />
              </div>
            </div>
          </div>

          <div class="flex justify-end">
            <button type="submit" class="btn-primary rounded-full px-6 py-3">保存报告接入</button>
          </div>
        </form>
      </section>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  AdjustmentsHorizontalIcon,
  CheckBadgeIcon as CheckIcon,
  CpuChipIcon,
  DocumentTextIcon,
  KeyIcon,
} from '@heroicons/vue/24/outline'
import { useApiBase } from '../../composables/useApiBase'

const { ensureApiBase } = useApiBase()
const buildApiUrl = async (path) => {
  const baseUrl = await ensureApiBase()
  return `${baseUrl}${path}`
}

const providerOptions = [
  { label: '阿里通义千问（DashScope）', value: 'qwen' },
  { label: 'OpenAI / 兼容 API', value: 'openai' }
]

const LANGCHAIN_DASHSCOPE_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
const LANGCHAIN_OPENAI_BASE_URL = 'https://api.openai.com/v1'
const langchainBaseUrlMode = ref('dashscope')

const llmState = reactive({
  filter: {
    provider: 'qwen',
    model: '',
    qps: 0,
    batch_size: 1,
    truncation: 0,
    base_url: ''
  },
  assistant: {
    provider: 'qwen',
    model: '',
    max_tokens: 0,
    temperature: 0,
    base_url: '',
    system_prompt: ''
  },
  embedding: {
    provider: 'qwen',
    model: '',
    dimension: 0,
    base_url: ''
  },
  langchain: {
    provider: 'qwen',
    model: '',
    report_model: '',
    analyze_summary_model: '',
    base_url: '',
    temperature: 0.3,
    max_tokens: 3000,
    timeout: 120,
    max_retries: 2
  },
  loading: false,
  error: '',
  message: ''
})

const reportRuntime = reactive({
  provider: 'qwen',
  model: '',
  base_url: '',
  api_key: '',
  api_key_summary: {
    configured: false,
    last_four: ''
  },
  temperature: 0.2,
  max_tokens: 12000,
  timeout: 300,
  max_retries: 2
})

const credentialState = reactive({
  summary: {
    qwen: { configured: false, last_four: '' },
    openai: { configured: false, last_four: '' },
    openai_base_url: ''
  },
  form: {
    qwen_api_key: '',
    openai_api_key: '',
    openai_base_url: ''
  },
  loading: false,
  error: '',
  message: ''
})

const asNumber = (value, fallback) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

const filterModelPlaceholder = computed(() =>
  llmState.filter.provider === 'openai' ? '如：gpt-3.5-turbo' : '如：qwen-plus'
)
const assistantModelPlaceholder = computed(() =>
  llmState.assistant.provider === 'openai' ? '如：gpt-4o-mini' : '如：qwen-turbo'
)
const embeddingModelPlaceholder = computed(() =>
  llmState.embedding.provider === 'openai' ? '如：text-embedding-3-small' : '如：text-embedding-v4'
)
const featureModelPlaceholder = computed(() =>
  llmState.langchain.provider === 'openai' ? '如：gpt-4o-mini' : '如：qwen-plus'
)
const reportRuntimeModelPlaceholder = computed(() =>
  reportRuntime.provider === 'openai' ? '如：gpt-4.1 或 gpt-4o-mini' : '如：qwen3.5-plus'
)
const effectiveLangchainBaseUrl = computed(() => {
  const raw = (llmState.langchain.base_url || '').trim()
  if (langchainBaseUrlMode.value === 'dashscope') {
    return raw || LANGCHAIN_DASHSCOPE_BASE_URL
  }
  if (langchainBaseUrlMode.value === 'openai') {
    return raw || LANGCHAIN_OPENAI_BASE_URL
  }
  return raw
})

const syncLangchainBaseUrlModeFromState = () => {
  const provider = String(llmState.langchain.provider || '').toLowerCase()
  const baseUrl = String(llmState.langchain.base_url || '').trim()

  if (!baseUrl) {
    langchainBaseUrlMode.value = provider === 'openai' ? 'openai' : 'dashscope'
    llmState.langchain.provider = langchainBaseUrlMode.value === 'openai' ? 'openai' : 'qwen'
    return
  }

  if (baseUrl === LANGCHAIN_DASHSCOPE_BASE_URL) {
    langchainBaseUrlMode.value = 'dashscope'
    llmState.langchain.provider = 'qwen'
    return
  }

  if (baseUrl === LANGCHAIN_OPENAI_BASE_URL) {
    langchainBaseUrlMode.value = 'openai'
    llmState.langchain.provider = 'openai'
    return
  }

  langchainBaseUrlMode.value = 'custom'
  llmState.langchain.provider = 'openai'
}

watch(
  () => llmState.filter.provider,
  (provider) => {
    if (provider !== 'openai') {
      llmState.filter.base_url = ''
    }
  }
)

watch(
  () => llmState.assistant.provider,
  (provider) => {
    if (provider !== 'openai') {
      llmState.assistant.base_url = ''
    }
  }
)

watch(
  () => llmState.embedding.provider,
  (provider) => {
    if (provider !== 'openai') {
      llmState.embedding.base_url = ''
    }
  }
)

watch(
  () => langchainBaseUrlMode.value,
  (mode) => {
    if (mode === 'dashscope') {
      llmState.langchain.provider = 'qwen'
      llmState.langchain.base_url = LANGCHAIN_DASHSCOPE_BASE_URL
      return
    }
    if (mode === 'openai') {
      llmState.langchain.provider = 'openai'
      llmState.langchain.base_url = LANGCHAIN_OPENAI_BASE_URL
      return
    }
    llmState.langchain.provider = 'openai'
  }
)

const applyCredentialResult = (result) => {
  const qwenSummary = result && typeof result === 'object' && typeof result.qwen === 'object' ? result.qwen : {}
  const openaiSummary = result && typeof result === 'object' && typeof result.openai === 'object' ? result.openai : {}
  credentialState.summary.qwen.configured = Boolean(qwenSummary.configured)
  credentialState.summary.qwen.last_four = qwenSummary.last_four || ''
  credentialState.summary.openai.configured = Boolean(openaiSummary.configured)
  credentialState.summary.openai.last_four = openaiSummary.last_four || ''
  credentialState.summary.openai_base_url = typeof result.openai_base_url === 'string' ? result.openai_base_url : ''
  credentialState.form.openai_base_url = credentialState.summary.openai_base_url
  credentialState.form.qwen_api_key = ''
  credentialState.form.openai_api_key = ''
}

const fetchLlmCredentials = async () => {
  credentialState.loading = true
  credentialState.error = ''
  credentialState.message = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/credentials')
    const response = await fetch(endpoint)
    if (!response.ok) {
      throw new Error('读取 API 凭证失败')
    }
    const payload = await response.json()
    const result = payload && typeof payload === 'object' ? payload.data ?? {} : {}
    applyCredentialResult(result)
  } catch (err) {
    credentialState.error = err instanceof Error ? err.message : '读取 API 凭证失败'
  } finally {
    credentialState.loading = false
  }
}

const updateCredentials = async (payload, successMessage = 'API 凭证已更新') => {
  if (!payload || Object.keys(payload).length === 0) {
    return
  }
  credentialState.loading = true
  credentialState.error = ''
  credentialState.message = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/credentials')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!response.ok) {
      throw new Error('保存 API 凭证失败')
    }
    const payloadResult = await response.json()
    const result = payloadResult && typeof payloadResult === 'object' ? payloadResult.data ?? {} : {}
    applyCredentialResult(result)
    credentialState.message = successMessage
  } catch (err) {
    credentialState.error = err instanceof Error ? err.message : '保存 API 凭证失败'
  } finally {
    credentialState.loading = false
  }
}

const submitCredentials = async () => {
  credentialState.message = ''
  credentialState.error = ''
  const payload = {}
  const qwenInput = (credentialState.form.qwen_api_key || '').trim()
  const openaiInput = (credentialState.form.openai_api_key || '').trim()
  const baseUrlInput = (credentialState.form.openai_base_url || '').trim()
  const currentBaseUrl = credentialState.summary.openai_base_url || ''

  if (qwenInput) {
    payload.qwen_api_key = qwenInput
  }
  if (openaiInput) {
    payload.openai_api_key = openaiInput
  }
  if (baseUrlInput !== currentBaseUrl) {
    payload.openai_base_url = baseUrlInput
  }

  if (Object.keys(payload).length === 0) {
    credentialState.error = '请填写需要更新的字段'
    return
  }

  await updateCredentials(payload)
}

const clearCredential = async (provider) => {
  credentialState.error = ''
  credentialState.message = ''
  if (provider === 'qwen') {
    await updateCredentials({ qwen_api_key: '' }, '千问 API Key 已清空')
  } else if (provider === 'openai') {
    await updateCredentials({ openai_api_key: '' }, 'OpenAI API Key 已清空')
  }
}

const submitLlmFilter = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/filter')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(llmState.filter)
    })
    if (!response.ok) {
      throw new Error('保存筛选配置失败')
    }
    llmState.message = '筛选配置已保存'
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '保存筛选配置失败'
  }
}

const submitLlmAssistant = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/assistant')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(llmState.assistant)
    })
    if (!response.ok) {
      throw new Error('保存对话配置失败')
    }
    llmState.message = '对话配置已保存'
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '保存对话配置失败'
  }
}

const submitLlmEmbedding = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/embedding')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(llmState.embedding)
    })
    if (!response.ok) {
      throw new Error('保存向量化配置失败')
    }
    llmState.message = '向量配置已保存'
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '保存向量化配置失败'
  }
}

const submitLlmLangchain = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const payload = {
      provider: llmState.langchain.provider,
      model: llmState.langchain.model,
      report_model: llmState.langchain.report_model,
      analyze_summary_model: llmState.langchain.analyze_summary_model,
      base_url: llmState.langchain.base_url,
      temperature: llmState.langchain.temperature,
      max_tokens: llmState.langchain.max_tokens,
      timeout: llmState.langchain.timeout,
      max_retries: llmState.langchain.max_retries
    }
    const endpoint = await buildApiUrl('/settings/llm/langchain')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!response.ok) {
      throw new Error('保存功能模型失败')
    }
    llmState.message = '功能模型已保存'
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '保存功能模型失败'
  }
}

const applyReportRuntimeResult = (result) => {
  if (!result || typeof result !== 'object') {
    return
  }
  reportRuntime.provider = String(result.provider || 'qwen').trim() || 'qwen'
  reportRuntime.model = String(result.model || '').trim()
  reportRuntime.base_url = String(result.base_url || '').trim()
  reportRuntime.temperature = asNumber(result.temperature, 0.2)
  reportRuntime.max_tokens = asNumber(result.max_tokens, 12000)
  reportRuntime.timeout = asNumber(result.timeout, 300)
  reportRuntime.max_retries = asNumber(result.max_retries, 2)
  const apiKeySummary = result.api_key && typeof result.api_key === 'object' ? result.api_key : {}
  reportRuntime.api_key_summary.configured = Boolean(apiKeySummary.configured)
  reportRuntime.api_key_summary.last_four = String(apiKeySummary.last_four || '')
  reportRuntime.api_key = ''
}

const fetchReportRuntimeSettings = async () => {
  try {
    const endpoint = await buildApiUrl('/settings/llm/report-runtime')
    const response = await fetch(endpoint)
    if (!response.ok) {
      throw new Error('读取报告接入配置失败')
    }
    const payload = await response.json()
    const result = payload && typeof payload === 'object' ? payload.data ?? {} : {}
    applyReportRuntimeResult(result)
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '读取报告接入配置失败'
  }
}

const submitReportRuntime = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const payload = {
      provider: reportRuntime.provider,
      model: reportRuntime.model,
      base_url: reportRuntime.base_url,
      temperature: reportRuntime.temperature,
      max_tokens: reportRuntime.max_tokens,
      timeout: reportRuntime.timeout,
      max_retries: reportRuntime.max_retries
    }
    if ((reportRuntime.api_key || '').trim()) {
      payload.api_key = reportRuntime.api_key.trim()
    }
    const endpoint = await buildApiUrl('/settings/llm/report-runtime')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!response.ok) {
      throw new Error('保存报告接入失败')
    }
    const resultPayload = await response.json()
    const result = resultPayload && typeof resultPayload === 'object' ? resultPayload.data ?? {} : {}
    applyReportRuntimeResult(result)
    llmState.message = '报告专用接入已保存'
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '保存报告接入失败'
  }
}

const clearReportRuntimeApiKey = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/report-runtime')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clear_api_key: true })
    })
    if (!response.ok) {
      throw new Error('清除报告专用密钥失败')
    }
    const resultPayload = await response.json()
    const result = resultPayload && typeof resultPayload === 'object' ? resultPayload.data ?? {} : {}
    applyReportRuntimeResult(result)
    llmState.message = '报告专用密钥已清除'
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '清除报告专用密钥失败'
  }
}

const fetchLlmSettings = async () => {
  llmState.loading = true
  llmState.error = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm')
    const response = await fetch(endpoint)
    if (!response.ok) {
      throw new Error('读取模型配置失败')
    }
    const payload = await response.json()
    const result = payload && typeof payload === 'object' ? payload.data ?? {} : {}
    const filterConfig =
      result && typeof result === 'object'
        ? (result.filter_llm && typeof result.filter_llm === 'object'
          ? result.filter_llm
          : result.filter && typeof result.filter === 'object'
            ? result.filter
            : {})
        : {}

    if (filterConfig && typeof filterConfig === 'object') {
      Object.assign(llmState.filter, filterConfig)
    }
    if (!llmState.filter.provider) {
      llmState.filter.provider = 'qwen'
    }

    if (result.assistant && typeof result.assistant === 'object') {
      Object.assign(llmState.assistant, result.assistant)
    }
    if (!llmState.assistant.provider) {
      llmState.assistant.provider = 'qwen'
    }

    if (result.embedding_llm && typeof result.embedding_llm === 'object') {
      Object.assign(llmState.embedding, result.embedding_llm)
    } else if (result.embedding && typeof result.embedding === 'object') {
      Object.assign(llmState.embedding, result.embedding)
    }
    if (!llmState.embedding.provider) {
      llmState.embedding.provider = 'qwen'
    }

    const langchainConfig = result.langchain && typeof result.langchain === 'object' ? result.langchain : {}
    llmState.langchain.provider = String(langchainConfig.provider || 'qwen').trim() || 'qwen'
    llmState.langchain.model = String(langchainConfig.model || '').trim()
    llmState.langchain.report_model = String(langchainConfig.report_model || '').trim()
    llmState.langchain.analyze_summary_model = String(langchainConfig.analyze_summary_model || '').trim()
    llmState.langchain.base_url = String(langchainConfig.base_url || '').trim()
    llmState.langchain.temperature = asNumber(langchainConfig.temperature, 0.3)
    llmState.langchain.max_tokens = asNumber(langchainConfig.max_tokens, 3000)
    llmState.langchain.timeout = asNumber(langchainConfig.timeout, 120)
    llmState.langchain.max_retries = asNumber(langchainConfig.max_retries, 2)
    syncLangchainBaseUrlModeFromState()
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '读取模型配置失败'
  } finally {
    llmState.loading = false
  }
}

onMounted(() => {
  fetchLlmSettings()
  fetchLlmCredentials()
  fetchReportRuntimeSettings()
})
</script>

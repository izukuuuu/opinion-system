<template>
    <div class="space-y-6">
        <!-- Header / Controls -->
        <header class="card-surface p-4 flex flex-wrap items-center justify-between gap-4">
            <div class="flex flex-wrap gap-4">
                <label class="flex flex-col text-xs font-semibold text-secondary">
                    <span>专题 Topic</span>
                    <select v-model="currentTopic" class="input mt-1 min-w-[150px]" @change="refreshData">
                        <option v-for="t in topicOptions" :key="t" :value="t">{{ t }}</option>
                    </select>
                </label>
                <label class="flex flex-col text-xs font-semibold text-secondary">
                    <span>开始日期 Start</span>
                    <input v-model="startDate" type="date" class="input mt-1" @change="refreshData" />
                </label>
                <label class="flex flex-col text-xs font-semibold text-secondary">
                    <span>结束日期 End</span>
                    <input v-model="endDate" type="date" class="input mt-1" @change="refreshData" />
                </label>
            </div>
            <button class="btn-primary flex items-center gap-2" @click="refreshData" :disabled="loading">
                <ArrowPathIcon class="h-4 w-4" :class="{ 'animate-spin': loading }" />
                {{ loading ? '加载中...' : '刷新数据' }}
            </button>
        </header>

        <div v-if="error" class="bg-red-50 text-red-700 p-4 rounded-xl text-sm">
            {{ error }}
        </div>

        <div v-if="hasData" class="grid grid-cols-1 lg:grid-cols-2 gap-6">

            <!-- Heat Comparison Chart -->
            <section class="card-surface p-6 col-span-1 lg:col-span-2">
                <h3 class="text-lg font-semibold text-primary mb-4">舆论热度变化曲线对比</h3>
                <div ref="heatChartRef" class="w-full h-[400px]"></div>
            </section>

            <!-- Radar Chart & Stats -->
            <section class="card-surface p-6 col-span-1 lg:col-span-2">
                <div class="flex flex-wrap items-center justify-between mb-4">
                    <h3 class="text-lg font-semibold text-primary">舆论场五维状态面板</h3>
                    <div class="flex items-center gap-2 text-sm text-secondary">
                        <span>选择时间窗口: </span>
                        <select v-model="selectedWindowIndex" class="input py-1 px-2">
                            <option v-for="(item, index) in calculationResults" :key="index" :value="index">
                                {{ item['日期'] || `窗口 ${index + 1}` }}
                            </option>
                        </select>
                    </div>
                </div>

                <div class="grid grid-cols-2 md:grid-cols-5 gap-2 mb-6 bg-base-soft p-4 rounded-xl">
                    <div class="text-center">
                        <div class="text-xs text-secondary mb-1">信息扩散速度(I)</div>
                        <div class="text-lg font-bold text-indigo-700">{{ currentFiveDim.diffusionSpeed.toFixed(2) }}
                        </div>
                    </div>
                    <div class="text-center">
                        <div class="text-xs text-secondary mb-1">平台集中度(C)</div>
                        <div class="text-lg font-bold text-indigo-700">{{
                            currentFiveDim.platformConcentration.toFixed(2) }}</div>
                    </div>
                    <div class="text-center">
                        <div class="text-xs text-secondary mb-1">参与密度(D)</div>
                        <div class="text-lg font-bold text-indigo-700">{{ currentFiveDim.participationDensity.toFixed(2)
                        }}</div>
                    </div>
                    <div class="text-center">
                        <div class="text-xs text-secondary mb-1">舆情温度(T)</div>
                        <div class="text-lg font-bold text-indigo-700">{{ currentFiveDim.sentimentTemperature.toFixed(2)
                        }}</div>
                    </div>
                    <div class="text-center">
                        <div class="text-xs text-secondary mb-1">外部压力(S)</div>
                        <div class="text-lg font-bold text-indigo-700">{{ currentFiveDim.externalPressure.toFixed(2) }}
                        </div>
                    </div>
                </div>

                <div ref="radarChartRef" class="w-full h-[400px]"></div>
            </section>

            <!-- Indicators -->
            <section class="card-surface p-6">
                <h3 class="text-lg font-semibold text-primary mb-2">观点极化程度 (涡度)</h3>
                <p class="text-xs text-secondary mb-4">衡量舆论场中观点对立和极化的程度，超过 {{ thresholds.vortex }} 表示高风险</p>
                <div ref="vortexChartRef" class="w-full h-[300px]"></div>
            </section>

            <section class="card-surface p-6">
                <h3 class="text-lg font-semibold text-primary mb-2">影响力驱动 (压强梯度)</h3>
                <p class="text-xs text-secondary mb-4">反映意见领袖与普通用户之间的影响力差异，超过 {{ thresholds.pressure }} 表示高风险</p>
                <div ref="pressureChartRef" class="w-full h-[300px]"></div>
            </section>

            <section class="card-surface p-6">
                <h3 class="text-lg font-semibold text-primary mb-2">
                    舆论场稳定度 (雷诺数)
                    <span v-if="currentFlowState" class="ml-2 px-2 py-0.5 rounded text-xs text-white bg-blue-500">流态: {{
                        currentFlowState }}</span>
                </h3>
                <p class="text-xs text-secondary mb-4">评估舆论场的稳定状态，超过 {{ thresholds.reynolds }} 表示高风险</p>
                <div ref="reynoldsChartRef" class="w-full h-[300px]"></div>
            </section>

            <!-- Policy Recommendations -->
            <section class="card-surface p-6">
                <h3 class="text-lg font-semibold text-primary mb-4">
                    AI 舆情控制政策建议
                    <span class="text-xs font-normal text-secondary ml-2">(基于千问大模型分析)</span>
                </h3>
                <div class="grid md:grid-cols-2 gap-4">
                    <div v-if="aiAnalysis" class="space-y-4">
                        <div v-if="aiAnalysis['态势判断']" class="bg-indigo-50 p-4 rounded-xl border-l-4 border-indigo-600">
                            <div class="font-bold text-indigo-800 text-sm mb-1">📊 态势判断</div>
                            <div class="text-sm text-indigo-900 leading-relaxed">{{ aiAnalysis['态势判断'] }}</div>
                        </div>
                        <div v-if="aiAnalysis['风险等级']" class="bg-indigo-50 p-4 rounded-xl border-l-4 border-indigo-600">
                            <div class="font-bold text-indigo-800 text-sm mb-1">⚠️ 风险等级</div>
                            <div class="text-sm font-bold" :class="{
                                'text-green-600': aiAnalysis['风险等级'] === '低',
                                'text-orange-500': aiAnalysis['风险等级'] === '中',
                                'text-red-500': aiAnalysis['风险等级'] === '高'
                            }">{{ aiAnalysis['风险等级'] }}</div>
                        </div>
                        <div v-if="aiAnalysis['建议措施'] && aiAnalysis['建议措施'].length"
                            class="bg-indigo-50 p-4 rounded-xl border-l-4 border-indigo-600">
                            <div class="font-bold text-indigo-800 text-sm mb-1">💡 建议措施</div>
                            <ul class="list-decimal list-inside text-sm text-indigo-900 space-y-1">
                                <li v-for="(measure, idx) in aiAnalysis['建议措施']" :key="idx">{{ measure }}</li>
                            </ul>
                        </div>
                    </div>
                    <div v-else-if="recommendations.length">
                        <div v-for="(rec, idx) in recommendations" :key="idx"
                            class="bg-indigo-50 p-4 rounded-xl border-l-4 border-indigo-600 mb-2 last:mb-0">
                            <div class="text-sm text-indigo-900 leading-relaxed">{{ rec }}</div>
                        </div>
                    </div>
                    <div v-else class="text-sm text-secondary italic">暂无政策建议</div>
                </div>
            </section>

        </div>

        <div v-else-if="!loading && !error" class="text-center py-20 text-muted">
            请选择专题并点击刷新以获取数据
        </div>
    </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch, computed, nextTick } from 'vue'
import { ArrowPathIcon } from '@heroicons/vue/24/outline'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'

const route = useRoute()
const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'

// State
const loading = ref(false)
const error = ref(null)
const hasData = ref(false)
const topicOptions = ref([])
const currentTopic = ref('')
const startDate = ref('')
const endDate = ref('')

const calculationResults = ref([])
const selectedWindowIndex = ref(0)
const thresholds = reactive({ vortex: 0.75, pressure: 0.7, reynolds: 2000 })
const recommendations = ref([])
const aiAnalysis = ref(null)

// Chart Refs
const heatChartRef = ref(null)
const radarChartRef = ref(null)
const vortexChartRef = ref(null)
const pressureChartRef = ref(null)
const reynoldsChartRef = ref(null)

let heatChart = null
let radarChart = null
let vortexChart = null
let pressureChart = null
let reynoldsChart = null

// Computed for current window data
const currentFiveDim = computed(() => {
    const res = calculationResults.value[selectedWindowIndex.value] || {}
    // Need to extract raw values or normalized values depending on display needs.
    // Assuming calculationResults structure matches backend output
    return {
        diffusionSpeed: res['流速(I)'] || 0,
        platformConcentration: res['粘度(C)'] || 0,
        participationDensity: res['密度(D)'] || 0,
        sentimentTemperature: res['温度(T)'] || 0,
        externalPressure: res['压力(S)'] || 0
    }
})

const currentFlowState = computed(() => {
    const res = calculationResults.value[selectedWindowIndex.value] || {}
    return res['流态'] || ''
})

const currentDateRec = computed(() => {
    return calculationResults.value[selectedWindowIndex.value] || {}
})

watch(selectedWindowIndex, () => {
    updateRadarChart()
    updateIndicators()
    updateAiAnalysis()
})

const loadTopics = async () => {
    try {
        const res = await fetch(`${backendUrl}/api/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ include_counts: false })
        })
        const data = await res.json()
        if (data.status === 'ok') {
            topicOptions.value = (data.data?.databases || [])
                .map(db => db.name)
                .filter(name => name)
        }
    } catch (e) { console.error(e) }
}

const refreshData = async () => {
    if (!currentTopic.value || !startDate.value) return
    loading.value = true
    error.value = null
    hasData.value = false

    try {
        const url = new URL(`${backendUrl}/api/fluid/result`)
        url.searchParams.append('topic', currentTopic.value)
        url.searchParams.append('start_date', startDate.value)
        if (endDate.value) url.searchParams.append('end_date', endDate.value)

        const res = await fetch(url)
        const json = await res.json()

        if (json.status === 'ok' && json.data) {
            processData(json.data)
            hasData.value = true
        } else {
            error.value = json.message || '并未找到相关数据'
        }
    } catch (e) {
        error.value = e.message
    } finally {
        loading.value = false
        await nextTick()
        if (hasData.value) {
            initCharts()
        }
    }
}

const processData = (data) => {
    // 1. Calculation Results (Time Windows)
    calculationResults.value = data['计算结果'] || []
    if (calculationResults.value.length > 0) {
        selectedWindowIndex.value = calculationResults.value.length - 1
    }

    // 2. Thresholds
    // Extract or use defaults
    // In backend fluid_analysis.py, these might not be explicitly passed unless in metrics
    // We stick to defaults if not found

    // 3. Analysis
    const analysis = data.analysis || {}
    recommendations.value = analysis.recommendations || []

    updateAiAnalysis()
}

const updateAiAnalysis = () => {
    const current = calculationResults.value[selectedWindowIndex.value] || {}
    aiAnalysis.value = current['AI分析建议'] || null
}

// --- Charts Logic ---

const initCharts = () => {
    if (heatChart) heatChart.dispose()
    if (radarChart) radarChart.dispose()
    if (vortexChart) vortexChart.dispose()
    if (pressureChart) pressureChart.dispose()
    if (reynoldsChart) reynoldsChart.dispose()

    heatChart = echarts.init(heatChartRef.value)
    radarChart = echarts.init(radarChartRef.value)
    vortexChart = echarts.init(vortexChartRef.value)
    pressureChart = echarts.init(pressureChartRef.value)
    reynoldsChart = echarts.init(reynoldsChartRef.value)

    renderHeatChart()
    updateRadarChart()
    updateIndicators()
}

const renderHeatChart = () => {
    const dates = calculationResults.value.map(item => {
        // Format date nicely if possible
        const d = item['日期'] || ''
        return d.split(' ')[1] || d // Extract time part if format is "YYYY-MM-DD HH:MM:SS"
    })

    // H_Predict and H_Real
    // Note: Backend might not return prediction if not requested, but fluid_analysis.py returns '窗口热度'(Display) and 'H'(Theoretical)
    // Adjust key names based on fluid_analysis.py output
    const heatValues = calculationResults.value.map(item => item['窗口热度'] || 0)

    const option = {
        title: { text: '' },
        tooltip: { trigger: 'axis' },
        legend: { data: ['热度'] },
        xAxis: { type: 'category', data: dates },
        yAxis: { type: 'value' },
        series: [
            {
                name: '热度',
                type: 'line',
                data: heatValues,
                color: '#ff7043',
                lineStyle: { width: 3 },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(255, 112, 67, 0.5)' },
                        { offset: 1, color: 'rgba(255, 112, 67, 0.0)' }
                    ])
                },
                smooth: true
            }
        ]
    }
    heatChart.setOption(option)
}

const updateRadarChart = () => {
    const data = currentFiveDim.value
    const option = {
        radar: {
            indicator: [
                { name: '信息扩散速度\n(I)', max: 1 },
                { name: '平台集中度\n(C)', max: 1 },
                { name: '参与密度\n(D)', max: 1 },
                { name: '舆情温度\n(T)', max: 1 },
                { name: '外部压力\n(S)', max: 1 }
            ],
            center: ['50%', '50%'],
            radius: '65%'
        },
        series: [{
            type: 'radar',
            data: [{
                value: [
                    data.diffusionSpeed,
                    data.platformConcentration,
                    data.participationDensity,
                    data.sentimentTemperature,
                    data.externalPressure
                ],
                name: '舆论场状态'
            }],
            areaStyle: {
                color: 'rgba(79, 70, 229, 0.2)'
            },
            lineStyle: {
                color: '#4f46e5',
                width: 2
            },
            itemStyle: {
                color: '#4f46e5'
            }
        }]
    }
    radarChart.setOption(option)
}

const updateIndicators = () => {
    const res = currentDateRec.value

    // Vortex
    const vortexVal = res['涡度(Ω)'] || 0
    renderGauge(vortexChart, '涡度', vortexVal, thresholds.vortex, 1.5)

    // Pressure
    const pressVal = res['压强梯度(G)'] || 0
    renderGauge(pressureChart, '压强梯度', pressVal, thresholds.pressure, 1.5)

    // Reynolds
    const reVal = res['雷诺数(Re)'] || 0
    renderGauge(reynoldsChart, '雷诺数', reVal, thresholds.reynolds, 4000)
}

const renderGauge = (chartInstance, name, value, threshold, maxVal) => {
    const option = {
        series: [{
            type: 'gauge',
            min: 0,
            max: maxVal,
            splitNumber: 5,
            axisLine: {
                lineStyle: {
                    width: 10,
                    color: [
                        [threshold / maxVal, '#10b981'],
                        [1, '#ef4444']
                    ]
                }
            },
            pointer: {
                itemStyle: { color: 'auto' }
            },
            axisTick: { distance: -10, length: 8, lineStyle: { color: '#fff', width: 2 } },
            splitLine: { distance: -10, length: 15, lineStyle: { color: '#fff', width: 3 } },
            axisLabel: { color: 'auto', distance: 20, fontSize: 10 },
            detail: { valueAnimation: true, formatter: '{value}', color: 'auto', fontSize: 20 },
            data: [{ value: parseFloat(value.toFixed(2)), name: name }],
            title: { offsetCenter: [0, '80%'], fontSize: 14, color: '#333' }
        }]
    }
    chartInstance.setOption(option)
}

onMounted(() => {
    loadTopics()
    // Populate form from query if exists
    if (route.query.topic) currentTopic.value = route.query.topic
    if (route.query.start) startDate.value = route.query.start
    if (route.query.end) endDate.value = route.query.end

    if (currentTopic.value && startDate.value) {
        refreshData()
    }

    window.addEventListener('resize', resizeCharts)
})

const resizeCharts = () => {
    if (heatChart) heatChart.resize()
    if (radarChart) radarChart.resize()
    if (vortexChart) vortexChart.resize()
    if (pressureChart) pressureChart.resize()
    if (reynoldsChart) reynoldsChart.resize()
}

</script>

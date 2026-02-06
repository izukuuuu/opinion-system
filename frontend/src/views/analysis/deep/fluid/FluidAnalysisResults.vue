<template>
    <div class="space-y-6">
        <!-- Header / Controls -->
        <header class="card-surface p-4 flex flex-wrap items-center justify-between gap-4">
            <div class="flex flex-wrap gap-4">
                <label class="flex flex-col text-xs font-semibold text-secondary">
                    <span>专题 Topic</span>
                    <select v-model="currentTopic" class="input mt-1 min-w-[150px]" @change="loadArchives">
                        <option v-for="t in topicOptions" :key="t" :value="t">{{ t }}</option>
                    </select>
                </label>
                <label class="flex flex-col text-xs font-semibold text-secondary">
                    <span>分析存档 Archive</span>
                    <select v-model="selectedArchive" class="input mt-1 min-w-[200px]" @change="onArchiveChange">
                        <option value="" disabled>请选择分析存档</option>
                        <option v-for="arc in archiveOptions" :key="arc" :value="arc">{{ arc }}</option>
                    </select>
                </label>
                <!-- Hidden inputs for compatibility or display if needed, but not user editable -->
                <div v-if="startDate && endDate" class="flex flex-col text-xs text-secondary mt-1">
                    <span>时间范围: {{ startDate }} ~ {{ endDate }}</span>
                </div>
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
                <h3 class="text-lg font-semibold text-primary mb-2 flex items-center gap-2">
                    观点极化程度 (涡度)
                    <span v-if="currentVortex > thresholds.vortex"
                        class="px-2 py-0.5 bg-red-500 text-white text-[10px] rounded uppercase font-bold">高风险</span>
                </h3>
                <p class="text-xs text-secondary mb-4">衡量舆论场中观点对立和极化的程度，超过 {{ thresholds.vortex }} 表示高风险</p>
                <div ref="vortexChartRef" class="w-full h-[300px]"></div>
            </section>

            <section class="card-surface p-6">
                <h3 class="text-lg font-semibold text-primary mb-2 flex items-center gap-2">
                    影响力驱动 (压强梯度)
                    <span v-if="currentPressure > thresholds.pressure"
                        class="px-2 py-0.5 bg-red-500 text-white text-[10px] rounded uppercase font-bold">高风险</span>
                </h3>
                <p class="text-xs text-secondary mb-4">反映意见领袖与普通用户之间的影响力差异，超过 {{ thresholds.pressure }} 表示高风险</p>
                <div ref="pressureChartRef" class="w-full h-[300px]"></div>
            </section>

            <section class="card-surface p-6">
                <h3 class="text-lg font-semibold text-primary mb-2 flex flex-wrap items-center gap-2">
                    舆论场稳定度 (雷诺数)
                    <span v-if="currentReynolds > thresholds.reynolds"
                        class="px-2 py-0.5 bg-red-500 text-white text-[10px] rounded uppercase font-bold">高风险</span>
                    <span v-if="currentFlowState"
                        class="px-2 py-0.5 rounded text-[10px] text-white bg-blue-600 font-bold uppercase tracking-wider">流态:
                        {{
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
                        <div v-if="aiAnalysis['关键指标'] && aiAnalysis['关键指标'].length"
                            class="bg-indigo-50 p-4 rounded-xl border-l-4 border-indigo-600">
                            <div class="font-bold text-indigo-800 text-sm mb-1">🎯 关键指标</div>
                            <div class="text-sm text-indigo-900">{{ aiAnalysis['关键指标'].join('、') }}</div>
                        </div>
                        <div v-if="aiAnalysis['风险点'] && aiAnalysis['风险点'].length"
                            class="bg-indigo-50 p-4 rounded-xl border-l-4 border-indigo-600">
                            <div class="font-bold text-indigo-800 text-sm mb-1">⚡ 风险点</div>
                            <ul class="list-disc list-inside text-sm text-indigo-900 space-y-1">
                                <li v-for="(risk, idx) in aiAnalysis['风险点']" :key="idx">{{ risk }}</li>
                            </ul>
                        </div>
                        <div v-if="aiAnalysis['建议措施'] && aiAnalysis['建议措施'].length"
                            class="bg-indigo-50 p-4 rounded-xl border-l-4 border-indigo-600">
                            <div class="font-bold text-indigo-800 text-sm mb-1">💡 建议措施</div>
                            <ul class="list-decimal list-inside text-sm text-indigo-900 space-y-1">
                                <li v-for="(measure, idx) in aiAnalysis['建议措施']" :key="idx">{{ measure }}</li>
                            </ul>
                        </div>
                        <div v-if="aiAnalysis['预警提示']" class="bg-indigo-50 p-4 rounded-xl border-l-4 border-indigo-600">
                            <div class="font-bold text-indigo-800 text-sm mb-1">🔔 预警提示</div>
                            <div class="text-sm text-indigo-900 italic font-medium">{{ aiAnalysis['预警提示'] }}</div>
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
const archiveOptions = ref([])
const selectedArchive = ref('')
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
    const getVal = (v) => (v && typeof v === 'object') ? (v.值 || 0) : (v || 0)

    return {
        diffusionSpeed: getVal(res['流速(I)']),
        platformConcentration: getVal(res['粘度(C)']),
        participationDensity: getVal(res['密度(D)']),
        sentimentTemperature: getVal(res['温度(T)']),
        externalPressure: getVal(res['压力(S)'])
    }
})

const currentFlowState = computed(() => {
    const res = calculationResults.value[selectedWindowIndex.value] || {}
    return res['流态'] || (res['雷诺数(Re)'] && res['雷诺数(Re)'].流态) || '未知'
})

const currentDateRec = computed(() => {
    return calculationResults.value[selectedWindowIndex.value] || {}
})

const getNumericVal = (v) => (v && typeof v === 'object') ? (v.值 || 0) : (v || 0)

const currentVortex = computed(() => getNumericVal(currentDateRec.value['涡度(Ω)'] || currentDateRec.value['涡度']))
const currentPressure = computed(() => getNumericVal(currentDateRec.value['压强梯度(G)'] || currentDateRec.value['压强梯度']))
const currentReynolds = computed(() => getNumericVal(currentDateRec.value['雷诺数(Re)'] || currentDateRec.value['雷诺数']))

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

const loadArchives = async () => {
    archiveOptions.value = []
    selectedArchive.value = ''
    if (!currentTopic.value) return

    try {
        const url = new URL(`${backendUrl}/api/fluid/archives`)
        url.searchParams.append('topic', currentTopic.value)
        const res = await fetch(url)
        const json = await res.json()
        if (json.status === 'ok') {
            archiveOptions.value = json.data || []
            // Auto select latest if available
            if (archiveOptions.value.length > 0) {
                selectedArchive.value = archiveOptions.value[0]
                onArchiveChange()
            }
        }
    } catch (e) {
        console.error("Failed to load archives", e)
    }
}

const onArchiveChange = () => {
    if (!selectedArchive.value) return

    // Parse start/end from archive name (e.g. "20230101_20230131" or "20230101")
    const parts = selectedArchive.value.split('_')
    if (parts.length === 2) {
        // Simple heuristic: assume format YYYYMMDD
        // Convert to YYYY-MM-DD for API/display consistency if needed or keep raw
        // The API likely expects the exact strings passed during creation or generic strings
        // But for "start_date" param in get_result, we might need to be careful.
        // Actually api.py get_result reconstructs `date_range = f"{start_date}_{end_date}"`

        // Let's assume the archive name IS the date_range identifier.
        // We need to reverse engineer start_date and end_date to pass to /result API
        // which reconstructs it. 
        // /result?topic=T&start_date=20230101&end_date=20230131 => date_range="20230101_20230131"
        startDate.value = parts[0]
        endDate.value = parts[1]
    } else {
        startDate.value = selectedArchive.value
        endDate.value = ''
    }
    refreshData()
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
    if (!heatChart) return
    const dates = calculationResults.value.map(item => {
        const d = item['日期'] || ''
        return d.split(' ')[1] || d
    })

    const getVal = (v) => (v && typeof v === 'object') ? (v.值 || 0) : (v || 0)

    // Support H_预测 or H_真实
    const realValues = calculationResults.value.map(item => getVal(item['H_真实'] || item['窗口热度']))
    const predValues = calculationResults.value.map(item => getVal(item['H_预测'] || item['热度(H)']))

    const option = {
        title: { text: '' },
        tooltip: { trigger: 'axis' },
        legend: { data: ['实际热度', '预测模型'] },
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        xAxis: { type: 'category', data: dates, boundaryGap: false },
        yAxis: { type: 'value' },
        series: [
            {
                name: '实际热度',
                type: 'line',
                data: realValues,
                color: '#ff7043',
                lineStyle: { width: 3 },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(255, 112, 67, 0.5)' },
                        { offset: 1, color: 'rgba(255, 112, 67, 0.0)' }
                    ])
                },
                smooth: true,
                symbol: 'none'
            },
            {
                name: '预测模型',
                type: 'line',
                data: predValues,
                color: '#3b82f6',
                lineStyle: { width: 2, type: 'dashed' },
                smooth: true,
                symbol: 'none'
            }
        ]
    }
    heatChart.setOption(option)
}

const updateRadarChart = () => {
    if (!radarChart) return
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
    if (!vortexChart || !pressureChart || !reynoldsChart) return
    const res = currentDateRec.value
    const getVal = (v) => (v && typeof v === 'object') ? (v.值 || 0) : (v || 0)

    // Vortex
    const vortexVal = getVal(res['涡度(Ω)'] || res['涡度'])
    renderGauge(vortexChart, '涡度', vortexVal, thresholds.vortex, 1.5)

    // Pressure
    const pressVal = getVal(res['压强梯度(G)'] || res['压强梯度'])
    renderGauge(pressureChart, '压强梯度', pressVal, thresholds.pressure, 1.5)

    // Reynolds
    const reVal = getVal(res['雷诺数(Re)'] || res['雷诺数'])
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

    if (currentTopic.value) {
        loadArchives()
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

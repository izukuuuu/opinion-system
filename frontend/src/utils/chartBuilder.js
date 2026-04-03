const HORIZONTAL_BAR_FUNCTIONS = ['geography', 'publishers', 'keywords', 'classification']

const STACKED_SERIES_COLORS = [
  '#4f46e5',
  '#0f766e',
  '#d97706',
  '#dc2626',
  '#2563eb',
  '#7c3aed',
  '#0891b2',
  '#65a30d',
  '#ea580c',
  '#db2777'
]

const LABEL_TRANSLATIONS = Object.freeze({
  overall: '总体',
  total: '总体',
  summary: '总体',
  positive: '正面',
  negative: '负面',
  neutral: '中性',
  unknown: '未知',
  unknownplatform: '未知平台',
  unknownauthor: '未知发布者',
  unknownregion: '未知地区',
  newsapp: '新闻APP',
  newsapplication: '新闻APP',
  newsclient: '新闻APP',
  newswebsite: '新闻网站',
  newssite: '新闻网站',
  forum: '论坛',
  video: '视频',
  selfmedia: '自媒体号',
  selfmediaaccount: '自媒体号',
  selfmediaaccounts: '自媒体号',
  officialmedia: '官方媒体',
  wechat: '微信',
  weixin: '微信',
  weibo: '微博',
  telegram: 'Telegram',
  twitter: '推特',
  facebook: '脸书',
  youtube: '油管',
  instagram: '照片墙',
  tiktok: 'TikTok',
  douyin: '抖音',
  kuaishou: '快手',
  xiaohongshu: '小红书',
  rednote: '小红书',
  bilibili: 'B站',
  zhihu: '知乎',
  news: '新闻',
  comment: '评论',
  comments: '评论',
  discussion: '讨论',
  discussions: '讨论',
  policy: '政策',
  health: '健康',
  science: '科普',
  economy: '经济',
  society: '社会',
  rumor: '谣言',
  other: '其他'
})

export const isHorizontalBarFunction = (funcName) => HORIZONTAL_BAR_FUNCTIONS.includes(funcName)

export const extractRows = (payload) => {
  if (!payload) return []
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload.data)) return payload.data
  return []
}

const ensureNumber = (value) => {
  const num = Number(value)
  return Number.isFinite(num) ? num : 0
}

const normalizeLabelKey = (value) =>
  String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[._/-]+/g, ' ')
    .replace(/\s+/g, ' ')

const compactLabelKey = (value) => normalizeLabelKey(value).replace(/\s+/g, '')

export const translateAnalysisLabel = (value) => {
  const text = String(value ?? '').trim()
  if (!text) return '未命名'
  if (/[\u4e00-\u9fa5]/.test(text)) return text
  const compactKey = compactLabelKey(text)
  if (LABEL_TRANSLATIONS[compactKey]) {
    return LABEL_TRANSLATIONS[compactKey]
  }
  if (/^unknown/i.test(text)) {
    return '未知'
  }
  return text
}

const rowName = (row) => {
  if (!row) return '-'
  return row.name ?? row.label ?? row.key ?? '未命名'
}

const rowValue = (row) => {
  if (!row) return 0
  return row.value ?? row.count ?? row.total ?? 0
}

export const translateRows = (rows) =>
  (Array.isArray(rows) ? rows : []).map((row) => {
    const translatedName = translateAnalysisLabel(rowName(row))
    return {
      ...row,
      name: translatedName,
      label: translatedName,
      rawName: rowName(row)
    }
  })

export const sortRowsDescending = (rows) =>
  [...rows].sort((a, b) => ensureNumber(rowValue(b)) - ensureNumber(rowValue(a)))

const buildBarOption = (title, rows, orientation = 'vertical', categoryLabel = '类别', valueLabel = '数量') => {
  const orderedRows = sortRowsDescending(rows)
  const displayRows = orderedRows
  const categories = displayRows.map((row) => rowName(row))
  const values = displayRows.map((row) => ensureNumber(rowValue(row)))
  const isVertical = orientation !== 'horizontal'
  const defaultVisibleCount = 20
  const shouldEnableVerticalZoom = !isVertical && categories.length > defaultVisibleCount
  const grid = isVertical
    ? { left: 30, right: 20, top: 20, bottom: 30, containLabel: true }
    : {
        left: 120,
        right: shouldEnableVerticalZoom ? 80 : 28,
        top: 20,
        bottom: 20,
        containLabel: true
      }
  const catAxis = {
    type: 'category',
    data: categories,
    axisLabel: { interval: 0, color: '#303d47', margin: 10 },
    axisLine: { lineStyle: { color: '#d0d5d9' } }
  }
  const valAxis = {
    type: 'value',
    axisLabel: { color: '#303d47' },
    splitLine: { lineStyle: { color: '#e2e9f1' } }
  }
  return {
    color: ['#9ab2cb'],
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid,
    xAxis: isVertical ? catAxis : valAxis,
    yAxis: isVertical
      ? valAxis
      : {
          ...catAxis,
          inverse: true,
          axisLabel: {
            ...catAxis.axisLabel,
            width: 96,
            overflow: 'truncate'
          }
        },
    dataset: {
      dimensions: [categoryLabel, valueLabel],
      source: displayRows.map((row) => ({ name: rowName(row), value: ensureNumber(rowValue(row)) }))
    },
    dataZoom: shouldEnableVerticalZoom
      ? [
          {
            type: 'inside',
            yAxisIndex: 0,
            zoomLock: true,
            startValue: 0,
            endValue: defaultVisibleCount - 1,
            moveOnMouseMove: true,
            moveOnMouseWheel: true,
            preventDefaultMouseMove: true
          },
          {
            type: 'slider',
            yAxisIndex: 0,
            right: 18,
            top: 20,
            bottom: 20,
            width: 14,
            startValue: 0,
            endValue: defaultVisibleCount - 1,
            zoomLock: true,
            brushSelect: false,
            fillerColor: 'rgba(154, 178, 203, 0.22)',
            borderColor: '#d0d5d9',
            backgroundColor: '#eef2f6',
            dataBackground: {
              lineStyle: { color: '#d0d5d9' },
              areaStyle: { color: 'rgba(154, 178, 203, 0.16)' }
            },
            handleStyle: {
              color: '#9ab2cb',
              borderColor: '#879db3'
            },
            moveHandleStyle: {
              color: '#879db3'
            },
            textStyle: {
              color: '#445562'
            }
          }
        ]
      : undefined,
    series: [
      {
        type: 'bar',
        data: values,
        barMaxWidth: isVertical ? 28 : 18,
        label: {
          show: true,
          color: '#303d47',
          position: isVertical ? 'top' : 'right'
        }
      }
    ]
  }
}

const buildLineOption = (title, rows, categoryLabel = '日期', valueLabel = '数量') => {
  const categories = rows.map((row) => rowName(row))
  const values = rows.map((row) => ensureNumber(rowValue(row)))
  return {
    color: ['#7babce'],
    tooltip: { trigger: 'axis' },
    grid: { left: 30, right: 15, top: 20, bottom: 30, containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: categories, axisLabel: { color: '#303d47' } },
    yAxis: { type: 'value', axisLabel: { color: '#303d47' }, splitLine: { lineStyle: { color: '#e2e9f1' } } },
    dataset: {
      dimensions: [categoryLabel, valueLabel],
      source: rows.map((row) => ({ name: rowName(row), value: ensureNumber(rowValue(row)) }))
    },
    series: [
      {
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.1 },
        data: values
      }
    ]
  }
}

const buildPieOption = (title, rows) => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0, type: 'scroll', textStyle: { color: '#303d47' } },
  series: [
    {
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '45%'],
      data: rows.map((row) => ({ name: rowName(row), value: ensureNumber(rowValue(row)) })),
      label: { formatter: '{b}: {d}%' }
    }
  ]
})

const compareCategoryValues = (left, right) => {
  const leftTime = Date.parse(String(left))
  const rightTime = Date.parse(String(right))
  const leftValid = Number.isFinite(leftTime)
  const rightValid = Number.isFinite(rightTime)
  if (leftValid && rightValid) {
    return leftTime - rightTime
  }
  return String(left).localeCompare(String(right))
}

export const buildTrendFlowDataset = (targets) => {
  const comparableTargets = Array.isArray(targets)
    ? targets.filter((target) => {
        const targetName = String(target?.target || '').trim()
        return targetName && targetName !== '总体'
      })
    : []

  const targetSeriesMaps = new Map()
  const dateKeys = new Set()

  comparableTargets.forEach((target) => {
    const targetName = translateAnalysisLabel(target.target)
    const rows = extractRows(target.data)
    if (!rows.length) return
    if (!targetSeriesMaps.has(targetName)) {
      targetSeriesMaps.set(targetName, new Map())
    }
    const targetMap = targetSeriesMaps.get(targetName)
    rows.forEach((row) => {
      const category = String(rowName(row)).trim()
      if (!category) return
      const value = ensureNumber(rowValue(row))
      dateKeys.add(category)
      targetMap.set(category, (targetMap.get(category) || 0) + value)
    })
  })

  const dates = [...dateKeys].sort(compareCategoryValues)
  if (!dates.length) return null

  const seriesEntries = [...targetSeriesMaps.entries()]
    .map(([name, valueMap]) => {
      const values = dates.map((date) => ensureNumber(valueMap.get(date)))
      const total = values.reduce((sum, value) => sum + value, 0)
      return { name, values, total }
    })
    .filter((entry) => entry.total > 0)
    .sort((a, b) => b.total - a.total)

  if (seriesEntries.length < 2) return null

  const totalsByDate = dates.map((_, index) =>
    seriesEntries.reduce((sum, entry) => sum + ensureNumber(entry.values[index]), 0)
  )
  const totalVolume = seriesEntries.reduce((sum, entry) => sum + entry.total, 0)

  const series = seriesEntries.map((entry) => ({
    ...entry,
    shares: entry.values.map((value, index) => {
      const totalAtDate = totalsByDate[index]
      if (!totalAtDate) return 0
      return Number(((value / totalAtDate) * 100).toFixed(2))
    })
  }))

  const summaryRows = series.map((entry) => ({
    name: entry.name,
    value: entry.total,
    displayValue: `${entry.total.toLocaleString()} (${totalVolume ? ((entry.total / totalVolume) * 100).toFixed(1) : '0.0'}%)`
  }))

  return {
    dates,
    series,
    summaryRows,
    raw: {
      dates,
      totalsByDate,
      totalVolume,
      series: series.map((entry) => ({
        name: entry.name,
        total: entry.total,
        values: entry.values,
        shares: entry.shares
      }))
    }
  }
}

export const buildTrendStackedAreaOption = (title, dataset) => {
  if (!dataset?.dates?.length || !dataset?.series?.length) return null
  return {
    color: STACKED_SERIES_COLORS,
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value) => `${Math.round(ensureNumber(value)).toLocaleString()}`
    },
    legend: {
      top: 0,
      left: 0,
      right: 0,
      type: 'scroll',
      textStyle: { color: '#303d47' }
    },
    grid: { left: 36, right: 18, top: 58, bottom: 30, containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: dataset.dates,
      axisLabel: { color: '#303d47' },
      axisLine: { lineStyle: { color: '#d0d5d9' } }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#303d47' },
      splitLine: { lineStyle: { color: '#e2e9f1' } }
    },
    series: dataset.series.map((entry) => ({
      name: entry.name,
      type: 'line',
      stack: 'total',
      smooth: true,
      showSymbol: false,
      areaStyle: { opacity: 0.18 },
      emphasis: { focus: 'series' },
      data: entry.values
    }))
  }
}

export const buildTrendStackedShareOption = (title, dataset) => {
  if (!dataset?.dates?.length || !dataset?.series?.length) return null
  return {
    color: STACKED_SERIES_COLORS,
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value) => `${ensureNumber(value).toFixed(1)}%`
    },
    legend: {
      top: 0,
      left: 0,
      right: 0,
      type: 'scroll',
      textStyle: { color: '#303d47' }
    },
    grid: { left: 36, right: 18, top: 58, bottom: 30, containLabel: true },
    xAxis: {
      type: 'category',
      data: dataset.dates,
      axisLabel: { color: '#303d47' },
      axisLine: { lineStyle: { color: '#d0d5d9' } }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: {
        color: '#303d47',
        formatter: '{value}%'
      },
      splitLine: { lineStyle: { color: '#e2e9f1' } }
    },
    series: dataset.series.map((entry) => ({
      name: entry.name,
      type: 'bar',
      stack: 'share',
      emphasis: { focus: 'series' },
      data: entry.shares
    }))
  }
}

export const buildChartOption = (funcName, rows, title) => {
  if (!rows?.length) return null
  if (funcName === 'trends') return buildLineOption(title, rows)
  if (funcName === 'attitude') return buildPieOption(title, rows)
  const orientation = isHorizontalBarFunction(funcName) ? 'horizontal' : 'vertical'
  return buildBarOption(title, rows, orientation)
}

export const buildRawText = (payload) => JSON.stringify(payload ?? {}, null, 2)

export { HORIZONTAL_BAR_FUNCTIONS }

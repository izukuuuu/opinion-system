const HORIZONTAL_BAR_FUNCTIONS = ['geography', 'publishers', 'keywords', 'classification']

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

const rowName = (row) => {
  if (!row) return '-'
  return row.name ?? row.label ?? row.key ?? '未命名'
}

const rowValue = (row) => {
  if (!row) return 0
  return row.value ?? row.count ?? row.total ?? 0
}

export const sortRowsDescending = (rows) =>
  [...rows].sort((a, b) => ensureNumber(rowValue(b)) - ensureNumber(rowValue(a)))

const buildBarOption = (title, rows, orientation = 'vertical', categoryLabel = '类别', valueLabel = '数量') => {
  const orderedRows = orientation === 'horizontal' ? sortRowsDescending(rows) : rows
  const categories = orderedRows.map((row) => rowName(row))
  const values = orderedRows.map((row) => ensureNumber(rowValue(row)))
  const isVertical = orientation !== 'horizontal'
  const catAxis = {
    type: 'category',
    data: categories,
    axisLabel: { interval: 0, color: '#303d47' },
    axisLine: { lineStyle: { color: '#d0d5d9' } }
  }
  const valAxis = {
    type: 'value',
    axisLabel: { color: '#303d47' },
    splitLine: { lineStyle: { color: '#e2e9f1' } }
  }
  return {
    color: ['#9ab2cb'],
    title: { text: title, left: 'center', textStyle: { color: '#1c252c' } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 60, right: 30, top: 60, bottom: 60, containLabel: true },
    xAxis: isVertical ? catAxis : valAxis,
    yAxis: isVertical ? valAxis : catAxis,
    dataset: {
      dimensions: [categoryLabel, valueLabel],
      source: orderedRows.map((row) => ({ name: rowName(row), value: ensureNumber(rowValue(row)) }))
    },
    series: [
      {
        type: 'bar',
        data: values,
        label: { show: true, color: '#303d47' }
      }
    ]
  }
}

const buildLineOption = (title, rows, categoryLabel = '日期', valueLabel = '数量') => {
  const categories = rows.map((row) => rowName(row))
  const values = rows.map((row) => ensureNumber(rowValue(row)))
  return {
    color: ['#7babce'],
    title: { text: title, left: 'center', textStyle: { color: '#1c252c' } },
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 30, top: 60, bottom: 60, containLabel: true },
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
  title: { text: title, left: 'center', textStyle: { color: '#1c252c' } },
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

export const buildChartOption = (funcName, rows, title) => {
  if (!rows?.length) return null
  if (funcName === 'trends') return buildLineOption(title, rows)
  if (funcName === 'attitude') return buildPieOption(title, rows)
  const orientation = isHorizontalBarFunction(funcName) ? 'horizontal' : 'vertical'
  return buildBarOption(title, rows, orientation)
}

export const buildRawText = (payload) => JSON.stringify(payload ?? {}, null, 2)

export { HORIZONTAL_BAR_FUNCTIONS }

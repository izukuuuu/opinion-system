import {
  buildChartOption,
  buildTrendFlowDataset,
  buildTrendStackedAreaOption,
  buildTrendStackedShareOption,
  buildRawText,
  extractRows,
  isHorizontalBarFunction,
  sortRowsDescending,
  translateAnalysisLabel,
  translateRows
} from './chartBuilder'

export const analysisFunctions = [
  {
    id: 'attitude',
    label: '情感分析',
    description: '分析内容的情感倾向分布，识别正面、负面和中性情绪。'
  },
  {
    id: 'classification',
    label: '话题分类',
    description: '对内容进行分类统计，了解不同话题的分布情况。'
  },
  {
    id: 'geography',
    label: '地域分析',
    description: '分析内容的地域分布特征，识别主要传播区域。'
  },
  {
    id: 'keywords',
    label: '关键词分析',
    description: '提取并统计高频关键词，了解核心关注点。'
  },
  {
    id: 'publishers',
    label: '发布者分析',
    description: '分析主要发布者分布，识别活跃的媒体和账号。'
  },
  {
    id: 'trends',
    label: '趋势洞察',
    description: '分析时间维度的声量变化，识别传播趋势和峰值。'
  },
  {
    id: 'volume',
    label: '声量概览',
    description: '统计各渠道的声量分布，评估传播渠道的影响力。'
  }
]

const analysisFunctionOrder = new Map(
  analysisFunctions.map((item, index) => [item.id, index])
)

const sanitizeLabel = (label) => {
  if (!label) return ''
  const match = String(label).match(/^[\u4e00-\u9fa5·\s]+/)
  if (match) {
    const value = match[0].trim()
    if (value) return value
  }
  return String(label).trim()
}

export const getAnalysisFunctionMeta = (functionId) =>
  analysisFunctions.find((item) => item.id === functionId) || {
    id: functionId,
    label: functionId,
    description: ''
  }

export const buildAnalysisSections = (functionsPayload) => {
  if (!Array.isArray(functionsPayload)) return []

  const sections = functionsPayload.map((func) => {
    const meta = getAnalysisFunctionMeta(func?.name)
    const displayLabel = sanitizeLabel(meta.label) || meta.label || func?.name || ''
    const baseTargets = Array.isArray(func?.targets) ? func.targets : []
    const targets = baseTargets.map((target) => {
      const rows = translateRows(extractRows(target?.data))
      const shouldSortDescending = isHorizontalBarFunction(func?.name)
      const displayRows = shouldSortDescending ? sortRowsDescending(rows) : rows
      const translatedTargetLabel = translateAnalysisLabel(target?.target)
      const targetTitle = `${displayLabel} · ${translatedTargetLabel}`
      return {
        target: target?.target,
        title: targetTitle,
        subtitle: '',
        option: buildChartOption(func?.name, displayRows, targetTitle),
        hasData: rows.length > 0,
        rows: displayRows.slice(0, 12),
        rawText: buildRawText(target?.data),
        order: translatedTargetLabel === '总体' ? 10 : 20
      }
    })

    if (func?.name === 'trends') {
      const flowDataset = buildTrendFlowDataset(baseTargets)
      if (flowDataset) {
        targets.unshift(
          {
            target: '__trend_share__',
            title: `${displayLabel} · 渠道占比堆叠`,
            subtitle: '100% 堆叠占比图，查看各渠道在不同日期的相对份额变化。',
            option: buildTrendStackedShareOption(`${displayLabel} · 渠道占比堆叠`, flowDataset),
            hasData: true,
            rows: flowDataset.summaryRows,
            rawText: buildRawText(flowDataset.raw),
            order: 1
          },
          {
            target: '__trend_flow__',
            title: `${displayLabel} · 渠道声量堆叠`,
            subtitle: '按日期对齐各渠道趋势，查看声量在时间轴上的流动与累积变化。',
            option: buildTrendStackedAreaOption(`${displayLabel} · 渠道声量堆叠`, flowDataset),
            hasData: true,
            rows: flowDataset.summaryRows,
            rawText: buildRawText(flowDataset.raw),
            order: 0
          }
        )
      }
    }

    targets.sort((left, right) => {
      const orderDiff = (left?.order ?? 50) - (right?.order ?? 50)
      if (orderDiff !== 0) return orderDiff
      return String(left?.title || '').localeCompare(String(right?.title || ''))
    })

    return {
      name: func?.name,
      label: meta.label,
      description: meta.description,
      targets
    }
  })

  sections.sort((left, right) => {
    const leftOrder = analysisFunctionOrder.get(left?.name) ?? 999
    const rightOrder = analysisFunctionOrder.get(right?.name) ?? 999
    if (leftOrder !== rightOrder) return leftOrder - rightOrder
    return String(left?.name || '').localeCompare(String(right?.name || ''))
  })

  return sections
}

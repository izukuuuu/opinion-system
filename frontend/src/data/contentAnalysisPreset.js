export const contentAnalysisPreset = {
  title: '默认控烟示例方案',
  description: '用于内容分析提示词工作台的示例编码方案，可直接在此文件修改。',
  edgeCases: [
    '出现青少年 → 必须含 "1-12"',
    '出现电子烟 → 必须含 "1-14"',
    '港澳台/国外经验 → 必须含 "1-13"，并补具体议题',
    '青少年 + 电子烟 同时出现 → 议题必须含 "1-12" 与 "1-14"',
    '1200 字以上且解释原因/影响 → 报道体裁 3',
    '社论/评论员文章 → 报道体裁 2',
    '纯发报告数据 → 报道体裁 4',
    '简讯/会议通稿 → 报道体裁 1',
    '恐怖诉求仅限“肺部烂掉/死亡倒计时”等强烈恐惧场景 → 否则默认为 6',
    '突出权威/专家代言（如钟南山发声） → 诉求方式 3；仅引用数据不算 3',
    '出现“立即拨打/马上戒烟/扫码举报”等动作指令 → 诉求方式 4；泛化“应加强监管”→ 6',
    '报道强调烟草捐资助学且无批判 → 信息类别 2 + 议题 2-1',
    '烟草捐资助学被质疑洗白 → 信息类别 1 + 议题 1-11',
    '“国家卫健委专家接受本报记者采访” → 信源编码 [2,10]（卫生部门主，意见领袖辅）'
  ].join('\n'),
  blocks: [
    {
      title: '信息类别（单选）',
      selection: 'single',
      level: 'level1',
      codes: [
        { code: '1', label: '控烟立场（支持控烟）' },
        { code: '2', label: '烟草立场（支持产业/反控烟）' },
        { code: '3', label: '其他或无关' }
      ]
    },
    {
      title: '议题编码（多选）',
      selection: 'multi',
      level: 'level2',
      codes: [
        { code: '1-1', label: '烟草与健康', group: '控烟立场' },
        { code: '1-2', label: '无烟立法', group: '控烟立场' },
        { code: '1-3', label: '控烟公约', group: '控烟立场' },
        { code: '1-4', label: '无烟场所', group: '控烟立场' },
        { code: '1-5', label: '监管处罚', group: '控烟立场' },
        { code: '1-6', label: '包装警示', group: '控烟立场' },
        { code: '1-7', label: '税收价格', group: '控烟立场' },
        { code: '1-8', label: '影视广告', group: '控烟立场' },
        { code: '1-9', label: '公共事件', group: '控烟立场' },
        { code: '1-10', label: '公共卫生', group: '控烟立场' },
        { code: '1-11', label: '文化价值', group: '控烟立场' },
        { code: '1-12', label: '青少年', group: '控烟立场' },
        { code: '1-13', label: '国际经验', group: '控烟立场' },
        { code: '1-14', label: '电子烟', group: '控烟立场' },
        { code: '1-15', label: '其他', group: '控烟立场' },
        { code: '2-1', label: '社会公益', group: '烟草立场' },
        { code: '2-2', label: '打假走私', group: '烟草立场' },
        { code: '2-3', label: '政策扶持', group: '烟草立场' },
        { code: '2-4', label: '产业与产品', group: '烟草立场' },
        { code: '2-5', label: '烟草腐败', group: '烟草立场' },
        { code: '2-6', label: '其他', group: '烟草立场' }
      ]
    },
    {
      title: '信源编码（多选）',
      selection: 'multi',
      level: 'level1',
      codes: [
        { code: '1', label: '中央非卫生' },
        { code: '2', label: '卫生部门' },
        { code: '3', label: '地方非卫生' },
        { code: '4', label: '官方控烟' },
        { code: '5', label: '民间控烟' },
        { code: '6', label: '国际控烟' },
        { code: '7', label: '港澳台/国外控烟' },
        { code: '8', label: '烟草行业' },
        { code: '9', label: '普通公众' },
        { code: '10', label: '意见领袖' },
        { code: '11', label: '媒体自采' },
        { code: '12', label: '医疗机构' },
        { code: '13', label: '公共组织' },
        { code: '14', label: '其他' }
      ]
    },
    {
      title: '报道体裁（单选）',
      selection: 'single',
      level: 'level1',
      codes: [
        { code: '1', label: '事实性报道' },
        { code: '2', label: '观点性报道' },
        { code: '3', label: '深度综合' },
        { code: '4', label: '科普/研究' },
        { code: '5', label: '其他' }
      ]
    },
    {
      title: '诉求方式（多选）',
      selection: 'multi',
      level: 'level1',
      codes: [
        { code: '1', label: '恐怖诉求' },
        { code: '2', label: '人性诉求' },
        { code: '3', label: '代言人/证言' },
        { code: '4', label: '行动呼吁' },
        { code: '5', label: '修辞格' },
        { code: '6', label: '无明显诉求' }
      ]
    }
  ]
}

export default contentAnalysisPreset


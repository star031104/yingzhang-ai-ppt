import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { slideHtml } from '../src/author.mjs'
import { candidateVariants } from '../src/cli.mjs'
import { deterministicScore } from '../src/score.mjs'
import { exportPptx, nativeTableDataset } from '../src/pptx.mjs'

test('author escapes source content', () => assert.match(
  slideHtml({ id: '1', role: 'data', position: 1, message: 'x', content: { title: '<unsafe>', bullets: [] } }),
  /&lt;unsafe&gt;/,
))

test('renderer never creates placeholder metrics or business copy', () => {
  const html = slideHtml({
    id: '2', role: 'data', position: 2, message: '只呈现资料原文',
    content: { title: '结果', bullets: ['尚未提供量化结果'] },
  })
  assert.doesNotMatch(html, /8\.6|(?:^|\D)0%|传统制作|显著下降/)
})

test('renderer does not promote model names, table numbers, or bare digits into hero metrics', () => {
  const html = slideHtml({
    id: 'metric-guard', role: 'data', position: 14, message: '实验采用多维评价指标',
    content: { title: '实验设置与评价指标', bullets: ['F1-score用于评价分类效果', 'Hit@1衡量检索命中', '36'] },
    visualIntent: { primaryVisual: 'chart', archetypeCandidates: ['metric-wall'] },
  }, 'metric-wall')
  assert.doesNotMatch(html, /class="metric-card/)
  assert.doesNotMatch(html, /<strong[^>]*>1<\/strong>/)
  assert.doesNotMatch(html, /<strong[^>]*>36<\/strong>/)
})

test('renderer keeps a real percentage while ignoring the one in Hit at one', () => {
  const html = slideHtml({
    id: 'real-metric', role: 'data', position: 16, message: '检索性能得到提升',
    content: { title: '检索结果', bullets: ['Hit@1提升1.5%'] },
  }, 'metric-wall')
  assert.match(html, />1\.5%<\/strong>/)
  assert.doesNotMatch(html, />1<\/strong>/)
})

test('candidate layouts follow the semantic role and available evidence', () => {
  const method = candidateVariants({ role: 'method', content: { bullets: ['第一步', '第二步'] } })
  const dataWithoutNumbers = candidateVariants({ role: 'data', content: { bullets: ['暂无量化结果'] } })
  assert.ok(method.includes('workflow'))
  assert.ok(!dataWithoutNumbers.includes('metric-wall'))
  assert.deepEqual(candidateVariants({
    role: 'insight', content: { bullets: ['洞察'] },
    assetBindings: [{ type: 'generated-image', path: 'visual.png' }],
  }), ['image-story'])
})

test('unitless academic metrics still unlock data-native candidates', () => {
  const variants = candidateVariants({
    role: 'data',
    content: { bullets: [
      '关键词规则：Accuracy 0.8120，F1 0.8043',
      '证据契约方法：Accuracy 0.8981，F1 0.9333',
    ] },
    visualIntent: { archetypeCandidates: ['chart-focus', 'metric-wall', 'table-highlight'] },
  })
  assert.ok(variants.includes('chart-focus'))
  assert.ok(variants.includes('metric-wall'))
  assert.ok(variants.includes('table-highlight'))
})

test('source reference markers never masquerade as chart data', () => {
  const variants = candidateVariants({
    role: 'comparison',
    content: { bullets: ['端到端模型存在事实幻觉（S003）', '检索增强生成缺乏显式约束（S003）'] },
    visualIntent: { archetypeCandidates: ['comparison-bars', 'two-column', 'scorecard'] },
  })
  assert.deepEqual(variants, ['two-column'])
})

test('a persisted candidate selection remains part of the render candidate set', () => {
  const variants = candidateVariants({
    role: 'method', content: { bullets: ['方法约束输出'] },
    visualIntent: { archetypeCandidates: ['workflow', 'process'], selectedVariant: 'three-stage' },
  })
  assert.equal(variants[0], 'three-stage')
  assert.ok(variants.includes('workflow'))
})

test('metric bullets can become an editable native table dataset', () => {
  const dataset = nativeTableDataset({content:{bullets:[
    '关键词规则：Accuracy 0.8120，F1 0.8043',
    '证据契约方法：Accuracy 0.8981，F1 0.9333',
  ]}})
  assert.deepEqual(dataset.headers, ['方法 / 对象','Accuracy','F1'])
  assert.deepEqual(dataset.rows[1], ['证据契约方法',0.8981,0.9333])
})

test('generated visual is embedded as a meaningful image layout', () => {
  const html = slideHtml({
    id: 'visual', role: 'insight', position: 3, message: '视觉必须服务结论',
    content: { title: '证据决定配图，而不是装饰决定内容', bullets: ['先确定论点', '再选择视觉'] },
    assetBindings: [{
      type: 'generated-image', dataUri: 'data:image/png;base64,AAAA',
      alt: '概念主视觉', provenance: 'AI 生成概念图，不作为事实证据',
    }],
  })
  assert.match(html, /class="image-story"/)
  assert.match(html, /AI 生成概念图，不作为事实证据/)
})

test('media assets use a dedicated narrative composition', () => {
  const spec = {
    id: 'media', role: 'insight', position: 4, message: '演示片段证明真实使用路径',
    content: { title: '产品演示', bullets: ['先观察操作路径', '再解释关键决策'] },
    assetBindings: [{ type: 'licensed-video', path: 'demo.mp4', mediaUri: 'file:///demo.mp4', alt: '产品演示视频', license: 'owned' }],
    visualIntent: { primaryVisual: 'media' },
    layoutPlan: { focalPoint: 'left', candidateOrder: ['media-focus', 'split'] },
  }
  assert.deepEqual(candidateVariants(spec), ['media-focus'])
  const html = slideHtml(spec, 'media-focus')
  assert.match(html, /class="media-story"/)
  assert.match(html, /data-scene-type="video"/)
  assert.match(html, /focal-left/)
})

test('layout contract participates in deterministic candidate scoring', () => {
  const result = deterministicScore({ nodes: [
    { type: 'text', bbox: { x: 60, y: 40, width: 900, height: 100 }, style: { fontSize: 38 } },
    { type: 'chart', bbox: { x: 70, y: 190, width: 1080, height: 390 }, style: {} },
  ] }, {
    role: 'data', content: { bullets: ['准确率达到 92%'] },
    visualIntent: { archetypeCandidates: ['chart-focus'] },
    layoutPlan: { recommendedVariant: 'chart-focus', constraints: { minOccupiedRatio: .2, maxOccupiedRatio: .8 } },
  }, 'chart-focus')
  assert.ok(result.planningFit >= 90)
  const alternative = deterministicScore({ nodes: [
    { type: 'text', bbox: { x: 60, y: 40, width: 900, height: 100 }, style: { fontSize: 38 } },
    { type: 'chart', bbox: { x: 70, y: 190, width: 1080, height: 390 }, style: {} },
  ] }, {
    role: 'data', content: { bullets: ['准确率达到 92%'] },
    visualIntent: { archetypeCandidates: ['chart-focus', 'split'] },
    layoutPlan: { recommendedVariant: 'chart-focus', constraints: { minOccupiedRatio: .2, maxOccupiedRatio: .8 } },
  }, 'split')
  assert.ok(result.planningFit > alternative.planningFit)
  const html = slideHtml({
    id: 'manual-layout', role: 'content', position: 3, message: '手工布局与导出共享同一契约',
    content: { title: '布局画布', bullets: ['主要内容'] },
    layoutPlan: { manualOverride: true, focalPoint: 'left', regions: [
      { id: 'primary', x: 0, y: 2, w: 5, h: 8 },
      { id: 'support', x: 5.5, y: 2, w: 6.5, h: 8 },
    ] },
  }, 'split')
  assert.match(html, /data-manual-layout="true"/)
  assert.match(html, /--planned-primary:5fr/)
})

test('visual intent overrides a generic role layout', () => {
  const chart = slideHtml({
    id: 'chart', role: 'evidence', position: 4, message: '准确率和覆盖率同时提升',
    content: { title: '实验数据与效果验证', bullets: ['事实准确率从81.4%提升至98.7%', '内容覆盖率从76.2%提升至92.5%'] },
    visualIntent: { primaryVisual: 'chart', archetypeCandidates: ['evidence-chain'] },
  })
  const closing = slideHtml({
    id: 'close', role: 'conclusion', position: 6, message: '证据图谱驱动的方法具有显著优势',
    content: { title: '结论与应用价值', bullets: ['提升效率与信息完整性', '支持可编辑交付'] },
    visualIntent: { primaryVisual: 'typography', archetypeCandidates: ['takeaways'] },
  })
  assert.match(chart, /class="dataset-chart"/)
  assert.match(chart, /准确率和覆盖率同时提升/)
  assert.match(closing, /class="typography-story"/)
  assert.match(closing, /证据图谱驱动的方法具有显著优势/)
})

test('renderers hide internal source markers from audience copy and deduplicate footers', () => {
  const html = slideHtml({
    id: 'legacy-sources', role: 'questions', position: 8,
    message: '未来完善跨版本检测 (S008)',
    content: { title: '边界与未来', bullets: ['补充运行时证据（S008）', '回顾当前边界 (S)'] },
    sourceRefs: [
      { document: 'report.md', section: 'S007' },
      { document: 'report.md', section: 'S008' },
    ],
  })
  assert.doesNotMatch(html, /S008|\(S\)/)
  assert.equal((html.match(/report\.md/g) ?? []).length, 1)
})

test('composite comparisons retain all values and qualifying observations', () => {
  const html = slideHtml({
    id: 'rag-comparison', role: 'comparison', position: 17, message: 'RAG机制提升头部排序质量',
    content: { title: 'RAG检索性能提升对比', bullets: [
      '意图约束使 MRR 0.8812→0.8945，Hit@1 0.8150→0.8300',
      'nDCG@5 0.9042→0.9173，Hit@8 与 Recall@8 均达到 1.0000',
      'Hit@1 提升约 1.5%，Hit@3 提升约 1.0%，收益集中在头部排序',
    ] },
    visualIntent: { primaryVisual: 'chart', archetypeCandidates: ['comparison-bars'] },
  })
  for(const value of ['MRR','0.8812','0.8945','Hit@1','0.815','0.8300','收益集中在头部排序','Recall@8'])assert.ok(html.includes(value))
  assert.doesNotMatch(html, /\+-0\.5|1\.5%<\/b>|1\.0%<\/b>/)
})

test('distinct metric gain percentages are not fabricated into a baseline comparison', () => {
  const html = slideHtml({
    id: 'gain-only', role: 'comparison', position: 2, message: '收益集中在头部排序',
    content: { title: '增益摘要', bullets: ['Hit@1 提升约 1.5%，Hit@3 提升约 1.0%'] },
    visualIntent: { primaryVisual: 'chart', archetypeCandidates: ['comparison-bars'] },
  })
  assert.doesNotMatch(html, /class="bars"/)
  assert.doesNotMatch(html, /基线/)
})

test('missing generated image falls back to an intentional typography composition', () => {
  const html = slideHtml({
    id: 'no-image', role: 'conclusion', position: 7, message: '把行动沉淀为组织能力',
    content: { title: '形成决策闭环', bullets: ['明确责任', '持续复盘'] },
    visualIntent: { primaryVisual: 'generated-image', archetypeCandidates: ['takeaways'] },
  })
  assert.match(html, /class="typography-story"/)
})

test('semantic problem composition is preserved when the model asks for a diagram', () => {
  const html = slideHtml({
    id: 'problem', role: 'problem', position: 2, message: '当前流程缺少证据约束',
    content: { title: '三类问题削弱答辩可信度', bullets: ['事实没有来源', '叙事缺少重点', '页面难以修改'] },
    visualIntent: { primaryVisual: 'diagram', archetypeCandidates: ['problem-cards'] },
  })
  assert.match(html, /class="problem-grid"/)
  assert.doesNotMatch(html, /class="flow"/)
})

test('candidate names correspond to genuinely different compositions', () => {
  const spec = {
    id: 'problem-variants', role: 'problem', position: 2, message: '流程必须建立证据约束',
    content: { title: '问题结构', bullets: ['事实没有来源', '叙事缺少重点', '页面难以修改'] },
    visualIntent: { primaryVisual: 'diagram', archetypeCandidates: ['contrast', 'before-after', 'problem-cards'] },
  }
  const contrast = slideHtml(spec, 'contrast')
  const sequence = slideHtml(spec, 'before-after')
  const cards = slideHtml(spec, 'problem-cards')
  assert.match(contrast, /class="problem-contrast"/)
  assert.match(sequence, /class="problem-sequence"/)
  assert.match(cards, /class="problem-grid"/)
  assert.notEqual(contrast, sequence)
  assert.notEqual(sequence, cards)
})

test('cover copy exposes the presentation objective, not renderer process slogans', () => {
  const html = slideHtml({
    id: 'cover-copy', role: 'cover', position: 1, message: '帮助管理层完成方案决策',
    content: { title: '年度增长方案', bullets: [] },
    designSystem: { communication: { objective: '帮助管理层完成方案决策' } },
  }, 'editorial-cover')
  assert.match(html, /帮助管理层完成方案决策/)
  assert.doesNotMatch(html, /从证据提取、叙事规划到可编辑交付|证据可追溯 · 叙事可验证 · 页面可编辑/)
})

test('score penalizes overflow and overlap', () => {
  const result = deterministicScore({ nodes: [
    { type: 'text', bbox: { x: -1, y: 0, width: 10, height: 10 }, style: { fontSize: '12px' } },
    { type: 'text', bbox: { x: 2, y: 2, width: 10, height: 10 }, style: { fontSize: '12px' } },
  ] }, { content: { bullets: [] }, visualIntent: { archetypeCandidates: ['hero'] } })
  assert.ok(result.overall < 100)
  assert.ok(result.geometry < 100)
})

test('pptx export supports native multi-series charts and source notes', async t => {
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-pptx-'))
  t.after(()=>fs.rm(root,{recursive:true,force:true}))
  const output=path.join(root,'chart.pptx')
  await exportPptx([{
    id:'native-chart',position:1,role:'data',message:'证据契约方法在两项指标上领先',
    content:{title:'两项指标共同验证方法优势',bullets:[
      '关键词规则：Accuracy 0.8120，F1 0.8043',
      '自由生成小模型：Accuracy 0.8610，F1 0.8577',
      '证据契约方法：Accuracy 0.8981，F1 0.9333',
    ]},
    sourceRefs:[{document:'实验结果.csv',section:'S001',page:1}],
    evidenceBindings:['F001'],visualIntent:{primaryVisual:'chart'},
    designSystem:{palette:{},typography:{fontFamily:'Microsoft YaHei'},brand:{name:'示例实验室'}},
  },{
    id:'native-table',position:2,role:'data',message:'表格保留完整数据结构',
    content:{title:'可编辑指标表',bullets:[
      '关键词规则：Accuracy 0.8120，F1 0.8043',
      '证据契约方法：Accuracy 0.8981，F1 0.9333',
    ]},
    sourceRefs:[{document:'实验结果.csv',section:'S001',page:1}],
    visualIntent:{primaryVisual:'chart',selectedVariant:'table-highlight'},
    designSystem:{palette:{},typography:{fontFamily:'Microsoft YaHei'}},
  }],output)
  assert.ok((await fs.stat(output)).size>10000)
})

test('pptx export embeds a licensed media asset without flattening the page', async t => {
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-media-'))
  t.after(()=>fs.rm(root,{recursive:true,force:true}))
  const media=path.join(root,'demo.mp4'),output=path.join(root,'media.pptx')
  await fs.writeFile(media,Buffer.from('000000186674797069736F6D0000020069736F6D6D703431','hex'))
  await exportPptx([{
    id:'media-slide',position:1,role:'insight',message:'演示片段证明真实使用路径',
    content:{title:'产品演示',bullets:['观察操作路径','解释关键决策']},
    assetBindings:[{type:'licensed-video',path:media,alt:'产品演示',license:'owned',provenance:'项目团队'}],
    visualIntent:{primaryVisual:'media',selectedVariant:'media-focus'},
    layoutPlan:{focalPoint:'right'},designSystem:{palette:{},typography:{fontFamily:'Microsoft YaHei'}},
  }],output)
  assert.ok((await fs.stat(output)).size>10000)
})

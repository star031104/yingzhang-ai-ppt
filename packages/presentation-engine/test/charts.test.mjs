import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import JSZip from 'jszip'
import {chartModel,chartSvg,selectChartType,normalizeChartType,waterfallSteps} from '../src/charts.mjs'
import {labelsAreOrdered,orderedLabelKey,numericTableDataset} from '../src/data.mjs'
import {slideHtml} from '../src/author.mjs'
import {exportPptx} from '../src/pptx.mjs'
import {closeSceneBrowser} from '../src/scene.mjs'

const gallery=JSON.parse(await fs.readFile(new URL('./fixtures/chart-gallery.json',import.meta.url),'utf8'))
const numbersIn=items=>new Set([...items.join(' ').matchAll(/-?\d+(?:\.\d+)?/g)].map(match=>Number(match[0])))

test('chart type follows the data shape deterministically',()=>{
 assert.deepEqual(gallery.map(spec=>chartModel(spec)?.type),['column','bar','line','area','doughnut','scatter','combo','waterfall','column'])
 assert.equal(chartModel(gallery[8]).reason,'before-after')
 assert.equal(chartModel(gallery[2]).reason,'ordered-labels')
 assert.equal(chartModel(gallery[4]).reason,'shares-sum-100')
 assert.equal(chartModel(gallery[7]).reason,'increments')
 for(const spec of gallery)assert.equal(JSON.stringify(chartModel(spec)),JSON.stringify(chartModel(structuredClone(spec))))
})

test('chart models only contain values stated in the evidence',()=>{
 for(const spec of gallery){
  const model=chartModel(spec),stated=numbersIn(spec.content.bullets)
  for(const series of model.series)for(const value of series.values)assert.ok(stated.has(value),`${spec.id}: ${value}`)
 }
 // Shares that do not sum to 100% are not drawn as a doughnut.
 assert.notEqual(chartModel({content:{bullets:['移动端：访问占比：68%','桌面端：访问占比：20%']}})?.type,'doughnut')
 // Inconsistent increments are not presented as a waterfall bridge.
 assert.notEqual(chartModel({content:{bullets:['期初余额：金额：100万元','新增签约：金额：35万元','期末余额：金额：150万元']}})?.type,'waterfall')
 // Mixed units without an ordered axis stay in a table.
 assert.equal(chartModel({content:{bullets:['方案甲：准确率89%，耗时20秒','方案乙：准确率93%，耗时12秒']}}),null)
 const steps=waterfallSteps(chartModel(gallery[7]))
 assert.deepEqual(steps.map(step=>[step.kind,step.start,step.end]),[['total',0,100],['increase',100,135],['decrease',135,123],['increase',123,131],['total',0,131]])
})

test('explicit chart types are honoured only when the data supports them',()=>{
 assert.equal(normalizeChartType('donut'),'doughnut')
 assert.equal(normalizeChartType('horizontal-bar'),'bar')
 assert.equal(normalizeChartType('radar'),null)
 const explicit={...gallery[0],chartType:'bar'}
 assert.equal(chartModel(explicit).type,'bar')
 assert.equal(chartModel(explicit).reason,'explicit')
 const impossible={...gallery[0],visualIntent:{...gallery[0].visualIntent,chartType:'doughnut'}}
 assert.equal(chartModel(impossible).type,'column')
 assert.match(chartModel(impossible).reason,/^explicit-doughnut-incompatible/)
 assert.equal(selectChartType({labels:['A','B'],series:[{name:'x',values:[1,2],unit:''}]},{explicit:'line'}).type,'line')
})

test('ordered labels cover years, quarters, months and Chinese ordinals',()=>{
 assert.ok(labelsAreOrdered(['2022年','2023年','2024年']))
 assert.ok(labelsAreOrdered(['Q1','Q2','Q3','Q4']))
 assert.ok(labelsAreOrdered(['1月','2月','3月']))
 assert.ok(labelsAreOrdered(['第一阶段','第二阶段','第三阶段']))
 assert.ok(labelsAreOrdered(['Jan','Feb','Mar']))
 assert.ok(!labelsAreOrdered(['2024年','2022年','2023年']))
 assert.ok(!labelsAreOrdered(['华东','华南','华北']))
 assert.equal(orderedLabelKey('Day-30'),30)
 assert.equal(numericTableDataset(['收入：120万元']),null)
})

test('SVG preview and native PPTX use the same chart family and data',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-charts-'))
 t.after(async()=>{await closeSceneBrowser();await fs.rm(root,{recursive:true,force:true})})
 for(const spec of gallery){
  const html=slideHtml(spec,'chart-focus')
  const model=chartModel(spec)
  assert.ok(html.includes(`data-chart-type="${model.type}"`),spec.id)
  assert.ok(html.includes('<svg class="evidence-chart"'),spec.id)
  const svg=chartSvg(structuredClone(model))
  assert.ok(/<(rect|path|circle)/.test(svg))
 }
 const output=path.join(root,'gallery.pptx')
 const report=await exportPptx(gallery,output,{mode:'scene'})
 assert.ok(report.slides.every(slide=>slide.renderer==='scene'&&slide.objects.chart===1),JSON.stringify(report.slides))
 const zip=await JSZip.loadAsync(await fs.readFile(output))
 const xml=await Promise.all(gallery.map((_,index)=>zip.file(`ppt/charts/chart${index+1}.xml`).async('string')))
 assert.match(xml[0],/<c:barChart>[\s\S]*<c:barDir val="col"\/>/)
 assert.match(xml[1],/<c:barDir val="bar"\/>/)
 assert.match(xml[2],/<c:lineChart>/)
 assert.match(xml[3],/<c:areaChart>/)
 assert.match(xml[4],/<c:doughnutChart>/)
 assert.match(xml[5],/<c:scatterChart>/)
 assert.match(xml[6],/<c:barChart>[\s\S]*<c:lineChart>/)
 assert.match(xml[7],/<c:grouping val="stacked"\/>/)
 // The waterfall base series is invisible and unlabeled.
 const base=xml[7].match(/<c:ser>(?:(?!<\/c:ser>).)*辅助基线(?:(?!<\/c:ser>).)*<\/c:ser>/s)[0]
 assert.match(base,/<c:spPr><a:noFill\/><a:ln><a:noFill\/><\/a:ln><\/c:spPr>/)
 assert.match(base,/<c:dLbls><c:delete val="1"\/><\/c:dLbls>/)
 // Manual plot layout aligns PowerPoint's plot area with the SVG preview.
 assert.match(xml[0],/<c:manualLayout>/)
 for(const value of ['92','64'])assert.ok(xml[1].includes(`<c:v>${value}</c:v>`))
})

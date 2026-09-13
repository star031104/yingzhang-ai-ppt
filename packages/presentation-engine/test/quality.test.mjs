import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import JSZip from 'jszip'
import {slideHtml} from '../src/author.mjs'
import {metricDataset,namedMetricTable} from '../src/data.mjs'
import {exportPptx} from '../src/pptx.mjs'
import {captureScene,closeSceneBrowser} from '../src/scene.mjs'
import {deterministicScore,safeCandidate} from '../src/score.mjs'

const spec=bullets=>({id:'quality',position:1,role:'data',message:'比较结果以实验记录为准',
 content:{title:'方案表现对照',bullets},visualIntent:{selectedVariant:'chart-focus'}})

test('both formats retain every named series and percentage unit',async t=>{
 const bullets=['方案甲：准确率89%，召回率82%','方案乙：准确率93%，召回率87%']
 const dataset=metricDataset(bullets)
 assert.deepEqual(dataset.series.map(item=>item.values),[[89,93],[82,87]])
 assert.deepEqual(namedMetricTable(bullets).headers,['方法 / 对象','准确率 (%)','召回率 (%)'])
 const html=slideHtml(spec(bullets),'chart-focus')
 assert.ok(['89%','93%','82%','87%'].every(value=>html.includes(value)))
 assert.ok(html.includes('dataset-chart'))
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-data-'))
 t.after(()=>fs.rm(root,{recursive:true,force:true}))
 const output=path.join(root,'chart.pptx')
 await exportPptx([spec(bullets)],output)
 const zip=await JSZip.loadAsync(await fs.readFile(output))
 const charts=Object.keys(zip.files).filter(name=>/^ppt\/charts\/chart\d+\.xml$/.test(name))
 assert.equal(charts.length,1)
 const xml=await zip.file(charts[0]).async('string')
 for(const value of ['89','93','82','87'])assert.ok(xml.includes(`<c:v>${value}</c:v>`))
 assert.ok(xml.includes('%'))
 assert.ok(xml.includes('<c:barDir val="bar"/>'))
 assert.ok(xml.includes('<c:gapWidth val="48"/>'))
 assert.match(xml,/<c:valAx>[\s\S]*?<c:numFmt formatCode="0\.##&quot;%&quot;"/)
 assert.equal((xml.match(/<c:ser>/g)??[]).length,2)
 assert.ok(Object.keys(zip.files).some(name=>name.startsWith('ppt/embeddings/')&&name.endsWith('.xlsx')))
})

test('incompatible units and missing values stay visible in tables',()=>{
 const mixed=['方案甲：准确率89%，耗时20秒','方案乙：准确率93%，耗时12秒']
 assert.equal(metricDataset(mixed),null)
 const table=namedMetricTable(mixed)
 assert.deepEqual(table.headers,['方法 / 对象','准确率 (%)','耗时 (秒)'])
 assert.deepEqual(table.rows[0],['方案甲',89,20])
 assert.ok(slideHtml(spec(mixed),'chart-focus').includes('<th>耗时 (秒)</th>'))
 const partial=['方案甲：Accuracy 0.8，F1 0.7','方案乙：Accuracy 0.9','方案丙：Accuracy 0.95，F1 0.91']
 assert.equal(metricDataset(partial),null)
 assert.equal(namedMetricTable(partial).rows.length,3)
 assert.deepEqual(namedMetricTable(partial).rows[1],['方案乙',0.9,'—'])
})

test('signed measurements use a shared zero baseline without clamping over 100 percent',()=>{
 const bullets=['业务甲：增长率-12%','业务乙：增长率125%']
 const dataset=metricDataset(bullets)
 assert.equal(dataset.axisMin,-12)
 assert.equal(dataset.axisMax,125)
 assert.deepEqual(dataset.series[0].values,[-12,125])
 const html=slideHtml(spec(bullets),'chart-focus')
 assert.ok(html.includes('-12%'))
 assert.ok(html.includes('125%'))
 assert.ok(html.includes('dataset-zero'))
})

test('fully overlapping sibling text is a collision but parent containers are not',()=>{
 const box={x:100,y:100,width:300,height:40},style={fontSize:24}
 const scene={nodes:[{id:'one',type:'text',bbox:box,style},{id:'two',type:'text',bbox:box,style}]}
 assert.equal(deterministicScore(scene,spec([])).overlaps,1)
 scene.nodes[1].ancestorIds=['one']
 assert.equal(deterministicScore(scene,spec([])).overlaps,0)
})

test('real browser catches nested text clipping and broken images inside valid boxes',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-render-'))
 t.after(async()=>{await closeSceneBrowser();await fs.rm(root,{recursive:true,force:true})})
 const html=path.join(root,'中文 # 裁切.html'),png=path.join(root,'preview.png')
 await fs.writeFile(html,'<!doctype html><style>body{margin:0}.slide{width:1280px;height:720px;overflow:hidden}.clip{position:absolute;left:100px;top:100px;width:180px;height:30px;overflow:hidden}p{font:24px/32px Arial;margin:0}</style><section class="slide"><div class="clip"><p>First visible line<br>Second hidden line</p></div><img src="missing.png" style="position:absolute;left:400px;top:100px;width:60px;height:60px"></section>')
 const scene=await captureScene(html,png)
 const score=deterministicScore(scene,spec([]))
 assert.equal(score.textOverflow,1)
 assert.equal(score.missingAssets,1)
 assert.equal(safeCandidate({...score,geometry:100,readability:100,contentFit:100}),false)
 assert.ok(score.issues.some(issue=>issue.code==='text-clipped'))
 // Repair the actual HTML and recapture it, exercising the fix-and-verify loop.
 await fs.writeFile(html,'<!doctype html><style>body{margin:0}p{position:absolute;left:100px;top:100px;width:300px;font:24px/32px Arial;margin:0}</style><p>First visible line<br>Second visible line</p>')
 const repaired=deterministicScore(await captureScene(html,png),spec([]))
 assert.equal(repaired.textOverflow,0)
 assert.equal(repaired.missingAssets,0)
})

test('exporting another brand does not leak its colors or font into default slides',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-brand-'))
 t.after(()=>fs.rm(root,{recursive:true,force:true}))
 const branded={...spec(['说明']),role:'cover',designSystem:{palette:{deep:'#AB1234'},typography:{fontFamily:'Courier New'}}}
 const output=path.join(root,'brand.pptx')
 await exportPptx([branded],output)
 await exportPptx([{...spec([]),role:'cover'}],output)
 const zip=await JSZip.loadAsync(await fs.readFile(output))
 const xml=await zip.file('ppt/slides/slide1.xml').async('string')
 assert.ok(!xml.includes('AB1234'))
 assert.ok(!xml.includes('Courier New'))
 assert.ok(xml.includes('20284D'))
})

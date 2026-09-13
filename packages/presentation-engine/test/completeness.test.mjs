import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import JSZip from 'jszip'
import {slideHtml} from '../src/author.mjs'
import {exportPptx} from '../src/pptx.mjs'
import {captureScene,closeSceneBrowser} from '../src/scene.mjs'
import {deterministicScore} from '../src/score.mjs'
import {metricDataset,namedMetrics,namedMetricTable,transitionDataset} from '../src/data.mjs'
import {renderStamp,matchesRenderStamp} from '../src/render-input.mjs'
import {candidateVariants,main} from '../src/cli.mjs'
import {textContrast} from '../src/contrast.mjs'

test('structured source rows retain arbitrary headers, original units and unknown values',()=>{
 const items=['方案甲：平均耗时：32秒；复核覆盖率：70%','方案乙：平均耗时：18秒；复核覆盖率：未提供']
 assert.equal(metricDataset(items),null)
 assert.deepEqual(namedMetricTable(items),{headers:['方法 / 对象','平均耗时','复核覆盖率'],rows:[['方案甲','32秒','70%'],['方案乙','18秒','未提供']]})
 const chart=metricDataset(['方案甲：复核覆盖率：70%；证据覆盖率：68%','方案乙：复核覆盖率：96%；证据覆盖率：94%'])
 assert.deepEqual(chart.series.map(series=>series.name),['复核覆盖率','证据覆盖率'])
 assert.deepEqual(chart.series[0].labels,['方案甲','方案乙'])
})

test('candidate planning recognizes structured table numbers without explicit units',()=>{
 const spec={role:'data',content:{bullets:[
  '公益采购：第一年：5.0；第二年：8.0；第三年：10.0',
  '总收入：第一年：8.0；第二年：15.0；第三年：25.0',
 ]},visualIntent:{archetypeCandidates:['chart-focus','table-highlight']},layoutPlan:{candidateOrder:['chart-focus','table-highlight']}}
 assert.ok(candidateVariants(spec).includes('chart-focus'))
 const scene={measurementVersion:2,nodes:[],visibleText:spec.content.bullets.join(''),structuredContent:[0,1]}
 assert.equal(deterministicScore(scene,spec,'chart-focus').contentFit,100)
})

test('qualitative comparison cards render without requiring chart data',()=>{
 const spec={role:'comparison',message:'差异来自服务闭环',content:{title:'竞品差异',bullets:['现有平台缺少系统科普','服务场景彼此割裂','项目覆盖多角色协作']},visualIntent:{primaryVisual:'cards'}}
 const html=slideHtml(spec,'cards')
 assert.ok(html.includes('summary-grid'))
 assert.ok(html.includes('现有平台缺少系统科普'))
})

test('editorial evidence layout is readable and preserves qualifications in both formats',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-editorial-'))
 t.after(async()=>{await closeSceneBrowser();await fs.rm(root,{recursive:true,force:true})})
 const spec={id:'editorial',position:1,role:'method',message:'每个回答都应回到原始证据',
  content:{title:'检索与复核形成可追溯的回答',bullets:['每个回答都应回到原始证据','索引保留文件版本、章节与页码','资料未提供的信息保持未知，不自行补充','当前结果仅限内部样本，不能推断外部效果']},
  visualIntent:{selectedVariant:'evidence-brief',contentRelation:'explanation'},speakerIntent:{sourceBoundaries:['外部效果尚未验证']}}
 const file=path.join(root,'slide.html');await fs.writeFile(file,slideHtml(spec,'evidence-brief'))
 const scene=await captureScene(file,path.join(root,'slide.png')),score=deterministicScore(scene,spec,'evidence-brief')
 for(const field of ['overflow','textOverflow','missingContent','lowContrast'])assert.equal(score[field],0,field)
 assert.ok(!scene.visibleText.includes('→'))
 await exportPptx([spec],path.join(root,'slide.pptx'))
 const zip=await JSZip.loadAsync(await fs.readFile(path.join(root,'slide.pptx')))
 const xml=await zip.file('ppt/slides/slide1.xml').async('string')
 for(const bullet of spec.content.bullets)assert.ok(xml.includes(bullet),bullet)
 assert.ok((await zip.file('ppt/notesSlides/notesSlide1.xml').async('string')).includes('外部效果尚未验证'))
})

test('dark covers, section dividers and closing pages keep readable titles',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-contrast-'))
 t.after(async()=>{await closeSceneBrowser();await fs.rm(root,{recursive:true,force:true})})
 for(const role of ['cover','section','questions']){
  const spec={id:role,role,position:1,message:'让读者清楚理解本次讨论',content:{title:'清晰的演示标题',bullets:[]}}
  const file=path.join(root,`${role}.html`);await fs.writeFile(file,slideHtml(spec))
  const scene=await captureScene(file,path.join(root,`${role}.png`)),title=scene.nodes.find(node=>node.tag==='h1')
  assert.ok(textContrast(title)>=3,role)
  const damaged=structuredClone(scene)
  damaged.nodes.find(node=>node.tag==='h1').style.color='rgb(24, 32, 51)'
  assert.ok(deterministicScore(damaged,spec).issues.some(issue=>issue.code==='low-text-contrast'),role)
 }
})

test('crowded role layouts keep every point in real previews and editable PPTX',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-complete-'))
 t.after(async()=>{await closeSceneBrowser();await fs.rm(root,{recursive:true,force:true})})
 const bullets=['明确受众和本次汇报目标','保留原始材料的关键证据','按同一口径比较实验结果','说明适用条件及已知限制','指定行动负责人和时间安排','持续跟踪实施后的实际反馈']
 const roles=['cover','agenda','method','architecture','problem','insight','conclusion','questions']
 const slides=roles.map((role,i)=>({id:`role-${role}`,position:i+1,role,message:'完整内容帮助读者理解判断与行动',content:{title:'从材料梳理到行动安排',bullets},visualIntent:{selectedVariant:role==='method'?'workflow':'cards'}}))
 for(const slide of slides){
  const html=path.join(root,`${slide.position}.html`)
  await fs.writeFile(html,slideHtml(slide,slide.visualIntent.selectedVariant))
  const scene=await captureScene(html,path.join(root,`${slide.position}.png`)),score=deterministicScore(scene,slide,slide.visualIntent.selectedVariant)
  assert.equal(score.missingContent,0,slide.role)
  assert.equal(score.textOverflow,0,slide.role)
  assert.equal(score.overflow,0,slide.role)
  const damaged={...scene,visibleText:scene.visibleText.replace(bullets[5],''),structuredContent:[]}
  assert.equal(deterministicScore(damaged,slide).missingContent,1,'Omitted point must fail coverage independently of geometry')
 }
 const output=path.join(root,'complete.pptx')
 await exportPptx(slides,output)
 const zip=await JSZip.loadAsync(await fs.readFile(output))
 const contentTypes=await zip.file('[Content_Types].xml').async('string')
 assert.ok(contentTypes.includes('/ppt/slideMasters/slideMaster1.xml'))
 assert.equal(contentTypes.includes('/ppt/slideMasters/slideMaster2.xml'),false)
 for(const slide of slides){
  const xml=await zip.file(`ppt/slides/slide${slide.position}.xml`).async('string')
  for(const bullet of bullets)assert.ok(xml.includes(bullet),`${slide.role}: ${bullet}`)
 }
})

test('rank indices and qualifications cannot become fabricated measurements',()=>{
 assert.deepEqual(namedMetrics('Hit@8 与 Recall@8 均达到 1.0000'),[])
 const items=['方案甲：准确率约89%，仅限中文问答','方案乙：准确率93%，样本仍需扩大','人工复核尚未完成']
 assert.equal(metricDataset(items),null)
 const table=namedMetricTable(items)
 assert.equal(table.rows.length,3)
 assert.ok(table.headers.includes('说明'))
 assert.ok(table.rows[0].at(-1).includes('近似值'))
 assert.ok(table.rows[1].at(-1).includes('样本仍需扩大'))
 assert.equal(table.rows[2][0],'人工复核尚未完成')
})

test('before and after charts use signed values, shared units and no invented baseline',()=>{
 const dataset=transitionDataset(['增长率从-12%提升至125%','增长率从0%提升至25%'])
 assert.deepEqual(dataset.series.map(series=>series.values),[[-12,0],[125,25]])
 assert.equal(dataset.axisMin,-12);assert.equal(dataset.axisMax,125)
 assert.equal(transitionDataset(['准确率从80%提升至90%','耗时从20秒下降至12秒']),null)
 assert.equal(transitionDataset(['准确率提升约10%']),null)
})

test('render stamp follows content and asset bytes while candidate selection stays reusable',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-stamp-'))
 t.after(()=>fs.rm(root,{recursive:true,force:true}))
 const asset=path.join(root,'asset.txt');await fs.writeFile(asset,'first')
 const slide={id:'a',position:1,content:{title:'标题',bullets:['原内容']},assetBindings:[{path:asset}],visualIntent:{primaryVisual:'cards'}}
 const stamp=await renderStamp(slide)
 assert.equal(await matchesRenderStamp(stamp,{...slide,visualIntent:{...slide.visualIntent,selectedVariant:'split',variantSelectionSource:'user'}}),true)
 assert.equal(await matchesRenderStamp(stamp,{...slide,content:{...slide.content,bullets:['新内容']}}),false)
 await fs.writeFile(asset,'other')
 assert.equal(await matchesRenderStamp(stamp,slide),false)
})

test('assembly rejects stale candidates after an edit',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-assemble-'))
 t.after(()=>fs.rm(root,{recursive:true,force:true}))
 const slide={id:'a',position:1,role:'content',message:'结论',content:{title:'标题',bullets:['原内容']},visualIntent:{selectedVariant:'split'}}
 const folder=path.join(root,'slides','1');await fs.mkdir(folder,{recursive:true})
 await fs.writeFile(path.join(folder,'split.html'),'<html>original</html>')
 await fs.writeFile(path.join(folder,'split.scene.json'),'{}')
 await fs.writeFile(path.join(folder,'split.score.json'),JSON.stringify({overall:90,renderStamp:await renderStamp(slide)}))
 const input=path.join(root,'input.json');await fs.writeFile(input,JSON.stringify([slide]))
 await main(['assemble',input,root])
 slide.content.bullets=['修改后内容'];await fs.writeFile(input,JSON.stringify([slide]))
 await assert.rejects(main(['assemble',input,root]),/重新生成/)
})

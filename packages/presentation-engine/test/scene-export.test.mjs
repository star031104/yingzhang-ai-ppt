import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import JSZip from 'jszip'
import {slideHtml} from '../src/author.mjs'
import {exportPptx} from '../src/pptx.mjs'
import {captureScene,closeSceneBrowser} from '../src/scene.mjs'
import {pptxMode,sceneExportIssues,planSceneSlide,textFrame,officeFont,patchSlideXml} from '../src/pptx-scene.mjs'
import {parsePath} from '../src/svg-path.mjs'
import {normalizedText} from '../src/content.mjs'
import {validateScene} from '../../scene-schema/src/index.js'

const EMU=914400
const slides=[
 {id:'metrics',position:1,role:'data',message:'三项指标说明转化与留存表现',content:{title:'核心经营指标',bullets:['转化率达到12%','七日留存率为82%','满意度达到91%']},visualIntent:{selectedVariant:'metric-wall'}},
 {id:'problems',position:2,role:'problem',message:'流程必须建立证据约束',content:{title:'三类问题削弱答辩可信度',bullets:['事实没有来源','叙事缺少重点','页面难以修改']},visualIntent:{selectedVariant:'problem-cards'}},
 {id:'cover',position:3,role:'cover',message:'帮助管理层完成方案决策',content:{title:'年度增长方案',bullets:[]},visualIntent:{selectedVariant:'hero'}},
 {id:'table',position:4,role:'data',message:'表格保留完整数据结构',content:{title:'可编辑指标表',bullets:['关键词规则：Accuracy 0.8120，F1 0.8043','证据契约方法：Accuracy 0.8981，F1 0.9333']},visualIntent:{selectedVariant:'table-highlight'}},
]

async function render(root,spec){
 const file=path.join(root,`${spec.id}.html`)
 await fs.writeFile(file,slideHtml(spec,spec.visualIntent.selectedVariant))
 return captureScene(file,path.join(root,`${spec.id}.png`))
}

function shapes(xml){
 return [...xml.matchAll(/<p:(sp|pic|graphicFrame)>([\s\S]*?)<\/p:\1>/g)].map(([,kind,body])=>{
  const off=body.match(/<a:off x="(-?\d+)" y="(-?\d+)"\/>/),ext=body.match(/<a:ext cx="(\d+)" cy="(\d+)"\/>/)
  return {kind,body,x:off?Number(off[1])/EMU:null,y:off?Number(off[2])/EMU:null,w:ext?Number(ext[1])/EMU:null,h:ext?Number(ext[2])/EMU:null,
   text:[...body.matchAll(/<a:t>([^<]*)<\/a:t>/g)].map(match=>match[1]).join('')}
 })
}

test('scene export places native shapes at the measured HTML geometry without losing or duplicating text',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-scene-'))
 t.after(async()=>{await closeSceneBrowser();await fs.rm(root,{recursive:true,force:true})})
 const scenes={}
 for(const spec of slides)scenes[spec.position]=validateScene(await render(root,spec))
 const output=path.join(root,'scene.pptx')
 const report=await exportPptx(slides,output,{mode:'scene',scenes,keepBrowser:true})
 assert.deepEqual(report.slides.map(slide=>slide.renderer),['scene','scene','scene','scene'])
 const zip=await JSZip.loadAsync(await fs.readFile(output))
 for(const spec of slides){
  const scene=scenes[spec.position],xml=await zip.file(`ppt/slides/slide${spec.position}.xml`).async('string'),placed=shapes(xml)
  const texts=scene.exportLayer.items.filter(item=>item.kind==='text')
  for(const item of texts){
   const content=item.runs.map(run=>run.text).join('')
   const match=placed.filter(shape=>normalizedText(shape.text)===normalizedText(content))
   assert.ok(match.length>=1,`${spec.id}: ${content} is exported`)
   const frame=textFrame(item)
   assert.ok(match.some(shape=>Math.abs(shape.x-frame.x/96)<.02&&Math.abs(shape.y-frame.y/96)<.02),`${spec.id}: ${content} position`)
   // The frame starts on the measured glyph box (minus leading) and covers its width.
   assert.ok(match.some(shape=>shape.x<=item.x/96+.02&&shape.x+shape.w>=(item.x+item.w)/96-.02),`${spec.id}: ${content} width`)
  }
  for(const box of scene.exportLayer.items.filter(item=>item.kind==='box'&&!item.root&&item.fill&&!(item.borders??[]).length&&item.radius.every(r=>r===0))){
   assert.ok(placed.some(shape=>shape.kind==='sp'&&Math.abs(shape.x-box.x/96)<.02&&Math.abs(shape.y-box.y/96)<.02&&Math.abs(shape.w-box.w/96)<.02&&Math.abs(shape.h-box.h/96)<.02),`${spec.id}: box at ${box.x},${box.y}`)
  }
  const all=normalizedText(placed.map(shape=>shape.text).join('\n'))
  for(const bullet of spec.content.bullets){
   const expected=normalizedText(bullet)
   const visible=normalizedText(scene.visibleText).split(expected).length-1
   const exported=all.split(expected).length-1
   if(spec.id==='table'){assert.ok(placed.some(shape=>shape.kind==='graphicFrame'&&/<a:tbl>/.test(shape.body)),'native table');continue}
   assert.equal(exported,visible,`${spec.id}: ${bullet} appears exactly as often as in HTML`)
  }
  assert.ok((await zip.file(`ppt/notesSlides/notesSlide${spec.position}.xml`).async('string')).includes(spec.message))
 }
 const table=shapes(await zip.file('ppt/slides/slide4.xml').async('string')).find(shape=>/<a:tbl>/.test(shape.body))
 const tableItem=scenes[4].exportLayer.items.find(item=>item.kind==='table')
 assert.ok(Math.abs(table.x-tableItem.x/96)<.02&&Math.abs(table.y-tableItem.y/96)<.02)
 for(const value of ['0.8981','0.9333','关键词规则'])assert.ok(table.body.includes(value))
})

test('scenes that cannot prove coverage fall back to the legacy compiler per slide',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-fallback-'))
 t.after(async()=>{await closeSceneBrowser();await fs.rm(root,{recursive:true,force:true})})
 const scene=await render(root,slides[0])
 const broken={...scene,exportLayer:{...scene.exportLayer,items:scene.exportLayer.items.filter(item=>!(item.kind==='text'&&item.runs.some(run=>run.text.includes('七日留存率'))))}}
 assert.ok(sceneExportIssues(broken,slides[0]).some(issue=>issue.startsWith('text-lost')))
 const doubled={...scene,exportLayer:{...scene.exportLayer,items:[...scene.exportLayer.items,...scene.exportLayer.items.filter(item=>item.kind==='text')]}}
 assert.ok(sceneExportIssues(doubled,slides[0]).some(issue=>issue.startsWith('text-duplicated')))
 assert.deepEqual(sceneExportIssues({nodes:[]},slides[0]),['scene-export-missing'])
 const malformed={...scene,exportLayer:{...scene.exportLayer,items:[...scene.exportLayer.items,{kind:'hologram',x:0,y:0,w:1,h:1,order:1,z:0}]}}
 assert.ok(sceneExportIssues(malformed,slides[0]).some(issue=>issue.startsWith('scene-export-invalid')))
 assert.throws(()=>validateScene(malformed),/Invalid export item kind/)
 const output=path.join(root,'mixed.pptx')
 const report=await exportPptx([slides[0],slides[1]],output,{mode:'scene',scenes:{1:broken},capture:false,keepBrowser:true})
 assert.equal(report.slides[0].renderer,'legacy')
 assert.match(report.slides[0].fallbackReason,/text-lost/)
 assert.equal(report.slides[1].renderer,'legacy')
 assert.equal(report.slides[1].fallbackReason,'scene-unavailable')
 const xml=await (await JSZip.loadAsync(await fs.readFile(output))).file('ppt/slides/slide1.xml').async('string')
 for(const bullet of slides[0].content.bullets)assert.ok(xml.includes(bullet))
})

test('PPTX mode switch honours both environment names and defaults to scene',()=>{
 assert.equal(pptxMode({}),'scene')
 assert.equal(pptxMode({YINGZHANG_PPTX_MODE:'legacy'}),'legacy')
 assert.equal(pptxMode({SLIDEFORGE_PPTX_MODE:'LEGACY'}),'legacy')
 assert.equal(pptxMode({YINGZHANG_PPTX_MODE:'scene',SLIDEFORGE_PPTX_MODE:'legacy'}),'scene')
 assert.equal(pptxMode({YINGZHANG_PPTX_MODE:'unknown'}),'scene')
})

test('stored candidate scenes are reused only while their render stamp matches',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-stored-'))
 t.after(async()=>{await closeSceneBrowser();await fs.rm(root,{recursive:true,force:true})})
 const {main}=await import('../src/cli.mjs')
 const input=path.join(root,'slides.json'),rendered=path.join(root,'rendered')
 await fs.writeFile(input,JSON.stringify([slides[1]]))
 await main(['build',input,rendered])
 const current=JSON.parse(await fs.readFile(path.join(rendered,'slides','2','current.json'),'utf8'))
 const chosen={...slides[1],visualIntent:{selectedVariant:current.variant}}
 await fs.writeFile(input,JSON.stringify([chosen]))
 await main(['pptx',input,path.join(root,'deck.pptx'),rendered])
 const report=JSON.parse(await fs.readFile(path.join(root,'deck.export.json'),'utf8'))
 assert.equal(report.slides[0].renderer,'scene')
 assert.equal(report.slides[0].sceneSource,'stored')
 const edited={...chosen,content:{...chosen.content,bullets:['事实没有来源','叙事缺少重点','页面需要重新编辑']}}
 await fs.writeFile(input,JSON.stringify([edited]))
 await main(['pptx',input,path.join(root,'edited.pptx'),rendered])
 const second=JSON.parse(await fs.readFile(path.join(root,'edited.export.json'),'utf8'))
 assert.equal(second.slides[0].sceneSource,'captured')
 const xml=await (await JSZip.loadAsync(await fs.readFile(path.join(root,'edited.pptx')))).file('ppt/slides/slide1.xml').async('string')
 assert.ok(xml.includes('页面需要重新编辑'))
})

test('gradients, pseudo elements and mixed corner radii become native drawing objects',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-paint-'))
 t.after(async()=>{await closeSceneBrowser();await fs.rm(root,{recursive:true,force:true})})
 const spec={id:'statement',position:1,role:'insight',message:'把行动沉淀为组织能力',content:{title:'形成决策闭环',bullets:['明确责任','持续复盘']},visualIntent:{selectedVariant:'big-statement'}}
 const scene=await render(root,spec)
 const plan=planSceneSlide(scene,spec)
 assert.ok(plan.ops.some(op=>op.gradient?.type==='linear'))
 assert.ok(plan.ops.some(op=>op.shape==='round2SameRect'&&op.rotate===90))
 const output=path.join(root,'paint.pptx')
 await exportPptx([spec],output,{mode:'scene',scenes:{1:scene},keepBrowser:true})
 const xml=await (await JSZip.loadAsync(await fs.readFile(output))).file('ppt/slides/slide1.xml').async('string')
 assert.match(xml,/<a:gradFill rotWithShape="1"><a:gsLst>/)
 assert.match(xml,/prst="round2SameRect"><a:avLst><a:gd name="adj1"/)
 assert.ok(!/name="yzgrad-\d+"[\s\S]*?<a:solidFill>[\s\S]*?<\/p:spPr>/.test(xml.match(/<p:sp>(?:(?!<\/p:sp>).)*yzgrad(?:(?!<\/p:sp>).)*<\/p:sp>/s)?.[0]??''))
 const agenda={id:'agenda',position:2,role:'agenda',message:'按三个问题推进',content:{title:'汇报路线',bullets:['问题与目标','方案与证据','结论与行动']},visualIntent:{selectedVariant:'section-map'}}
 const map=await render(root,agenda)
 assert.ok(map.exportLayer.pseudoMaterialized>=3,'agenda dots are pseudo elements')
 assert.ok(planSceneSlide(map,agenda).ops.some(op=>op.shape==='ellipse'&&op.line))
})

test('font mapping keeps Office-safe faces and svg paths parse arcs into curves',()=>{
 assert.equal(officeFont('"Microsoft YaHei", "PingFang SC", Arial, sans-serif'),'Microsoft YaHei')
 assert.equal(officeFont('"Noto Serif SC", "Songti SC", serif'),'SimSun')
 assert.equal(officeFont('serif'),'SimSun')
 assert.equal(officeFont('sans-serif'),'Microsoft YaHei')
 const [path]=parsePath('M0 0 L10 0 A5 5 0 0 1 10 10 Z')
 assert.equal(path.closed,true)
 assert.ok(path.segments.some(segment=>segment.type==='C'))
 const end=path.segments.at(-1).points
 assert.ok(Math.abs(end.at(-2)-10)<1e-6&&Math.abs(end.at(-1)-10)<1e-6)
 assert.equal(patchSlideXml('<a:prstGeom prst="round2SameRect"><a:avLst><a:gd name="adj" fmla="val 1"/>',{gradients:[]}),'<a:prstGeom prst="round2SameRect"><a:avLst><a:gd name="adj1" fmla="val 1"/>')
})

test('bound images keep their original files, object-fit crop and alt text in scene mode',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-images-'))
 t.after(async()=>{await closeSceneBrowser();await fs.rm(root,{recursive:true,force:true})})
 // A real 1280×720 PNG produced by the renderer serves as the bound asset.
 await render(root,slides[1])
 const picture=path.join(root,'problems.png')
 const art={type:'generated-image',path:picture,alt:'概念主视觉',provenance:'AI 生成概念图，不作为事实证据'}
 const cover={id:'art-cover',position:1,role:'cover',message:'帮助管理层完成方案决策',content:{title:'年度增长方案',bullets:[]},assetBindings:[art],visualIntent:{selectedVariant:'hero'},designSystem:{brand:{name:'示例品牌',logoPath:picture}}}
 const output=path.join(root,'images.pptx')
 const report=await exportPptx([cover],output,{mode:'scene',keepBrowser:true})
 assert.equal(report.slides[0].renderer,'scene',report.slides[0].fallbackReason)
 assert.equal(report.slides[0].objects.image,2,'cover art and brand logo')
 const zip=await JSZip.loadAsync(await fs.readFile(output))
 const xml=await zip.file('ppt/slides/slide1.xml').async('string')
 assert.match(xml,/descr="概念主视觉"/)
 assert.match(xml,/<a:srcRect l="\d+" r="\d+" t="\d+" b="\d+"\/>/,'object-fit cover becomes a crop')
 assert.ok(Object.keys(zip.files).some(name=>/^ppt\/media\/image-.*\.png$/.test(name)))
 // An image the compiler cannot map back to a file makes the slide fall back instead of dropping evidence.
 const file=path.join(root,'cover.html');await fs.writeFile(file,slideHtml({...cover,assetBindings:[{...art,dataUri:`data:image/png;base64,${(await fs.readFile(picture)).toString('base64')}`}]},'hero').replace(/ data-asset-index="0"/g,''))
 const orphan=await captureScene(file,null)
 const fallback=await exportPptx([cover],path.join(root,'orphan.pptx'),{mode:'scene',scenes:{1:orphan},keepBrowser:true})
 assert.equal(fallback.slides[0].renderer,'legacy')
 assert.match(fallback.slides[0].fallbackReason,/image-without-path/)
})

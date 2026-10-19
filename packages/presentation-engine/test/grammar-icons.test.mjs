import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import JSZip from 'jszip'
import {ICONS,ICON_NAMES,iconFor,iconsForItems,iconSvg} from '../src/icons.mjs'
import {grammarFor,grammarClasses,decorations} from '../src/grammar.mjs'
import {validateVisualTokens,GRAMMAR_FIELDS} from '../../skill-schema/src/index.js'
import {slideHtml} from '../src/author.mjs'
import {exportPptx} from '../src/pptx.mjs'
import {captureScene,closeSceneBrowser} from '../src/scene.mjs'
import {deterministicScore,safeCandidate} from '../src/score.mjs'
import {parsePath} from '../src/svg-path.mjs'

const skillsRoot=new URL('../../../skills/visual/',import.meta.url)

test('built-in icon set has 40+ editable stroke icons with bilingual keywords',()=>{
 assert.ok(ICON_NAMES.length>=40)
 for(const [name,icon] of Object.entries(ICONS)){
  assert.ok(icon.keywords.some(keyword=>/[一-鿿]/.test(keyword)),`${name} has Chinese keywords`)
  assert.ok(icon.keywords.some(keyword=>/^[a-z]+$/.test(keyword)),`${name} has English keywords`)
  assert.doesNotMatch(icon.body,/<(?!\/?(?:path|line|circle|ellipse|rect|polyline|polygon)\b)/,`${name} uses only vector primitives`)
  for(const [,d] of icon.body.matchAll(/ d="([^"]+)"/g))assert.ok(parsePath(d).length,`${name} path parses`)
 }
 assert.equal(iconFor('第一阶段：构建完整证据链'),'link')
 assert.equal(iconFor('检索证据并建立关联'),'search','ties resolve by catalogue order')
 assert.equal(iconFor('Strong growth in Q3'),'trend-up')
 assert.equal(iconFor('Revenue growth accelerated'),'coin','the longest keyword wins')
 assert.equal(iconFor('成本与收入'),'coin')
 assert.equal(iconFor('没有可匹配的词语'),null)
 assert.deepEqual(iconsForItems(['收入增长','利润增长']),['trend-up','coin'])
 assert.match(iconSvg('target'),/stroke="currentColor"/)
 assert.match(iconSvg('target'),/data-scene-type="group"/)
})

test('icons appear in cards, flows and agenda and export as native freeform shapes',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-icons-'))
 t.after(async()=>{await closeSceneBrowser();await fs.rm(root,{recursive:true,force:true})})
 const spec={id:'flow',position:1,role:'method',message:'每一步都可追溯',content:{title:'证据驱动的生成流程',bullets:['收集原始材料与数据','检索证据并建立关联','生成页面并完成验证','发布汇报并持续复盘']},visualIntent:{selectedVariant:'workflow'}}
 const html=slideHtml(spec,'workflow')
 assert.equal((html.match(/class="yz-icon"/g)??[]).length,4)
 assert.match(slideHtml({...spec,role:'agenda'},'agenda-cards'),/agenda-card"><b>01<i class="yz-icon-wrap">/)
 const forbidden=slideHtml({...spec,designSystem:{grammar:{forbidden:['icons']}}},'workflow')
 assert.doesNotMatch(forbidden,/class="yz-icon"/)
 const file=path.join(root,'flow.html');await fs.writeFile(file,html)
 const scene=await captureScene(file,path.join(root,'flow.png'))
 const score=deterministicScore(scene,spec,'workflow')
 assert.ok(safeCandidate(score),JSON.stringify(score.issues))
 assert.ok(!scene.nodes.some(node=>node.tag==='svg'&&node.type==='svg'),'icons do not inflate visual evidence scores')
 assert.equal(scene.exportLayer.items.filter(item=>item.kind==='vector').length,4)
 const output=path.join(root,'flow.pptx')
 const report=await exportPptx([spec],output,{mode:'scene',scenes:{1:scene},keepBrowser:true})
 assert.equal(report.slides[0].renderer,'scene')
 const xml=await (await JSZip.loadAsync(await fs.readFile(output))).file('ppt/slides/slide1.xml').async('string')
 assert.ok((xml.match(/<a:custGeom>/g)??[]).length>=8)
 assert.match(xml,/<a:cubicBezTo>/)
})

test('visual token schema accepts legacy tokens and rejects unsafe grammar',()=>{
 assert.deepEqual(validateVisualTokens({palette:{primary:'#112233'},fontFamily:'Microsoft YaHei'}),{grammar:null,errors:[]})
 const {grammar,errors}=validateVisualTokens({grid:{columns:12,margin:{x:72,top:56,bottom:44},gutter:24},
  typeScale:{display:72,title:50,subtitle:22,body:20,caption:11},density:'airy',decoration:{motifs:['orb','rule'],intensity:'subtle'},
  titleStyle:{align:'center',weight:700,tracking:-0.02,font:'serif',accent:'bar'},chartStyle:{palette:['primary','#FF8800'],gridlines:'none'},forbidden:['orb']})
 assert.deepEqual(errors,[])
 assert.deepEqual(grammar.decoration.motifs,['rule'],'forbidden motifs are removed')
 assert.equal(grammar.chartStyle.dataLabels,true)
 const bad=validateVisualTokens({grid:{columns:30,margin:8,gutter:2},typeScale:{display:20,title:40,subtitle:22,body:20,caption:11},density:'dense',forbidden:['comic-sans']})
 assert.equal(bad.grammar,null)
 assert.equal(bad.errors.length,4)
 assert.throws(()=>validateVisualTokens({density:'dense'},{strict:true}),/density/)
})

test('every built-in visual skill ships a distinct, valid layout grammar',async()=>{
 const names=(await fs.readdir(skillsRoot,{withFileTypes:true})).filter(entry=>entry.isDirectory()).map(entry=>entry.name)
 assert.ok(names.length>=9)
 for(const required of ['academic-defense','finance-research','gov-briefing'])assert.ok(names.includes(required))
 const fingerprints=new Set()
 for(const name of names){
  const tokens=JSON.parse(await fs.readFile(new URL(`${name}/tokens.json`,skillsRoot),'utf8'))
  const manifest=JSON.parse(await fs.readFile(new URL(`${name}/skill.json`,skillsRoot),'utf8'))
  assert.equal(manifest.kind,'visual');assert.equal(manifest.id,name)
  const {grammar,errors}=validateVisualTokens(tokens)
  assert.deepEqual(errors,[],name)
  for(const field of GRAMMAR_FIELDS)assert.ok(grammar[field]!==undefined,`${name}.${field}`)
  fingerprints.add(JSON.stringify([grammar.typeScale.title,grammar.titleStyle,grammar.decoration.motifs,grammar.density,grammar.grid.margin.x]))
 }
 assert.equal(fingerprints.size,names.length,'grammars are distinct')
})

test('grammar drives the HTML candidate: grid, type scale, title style, decorations and forbidden patterns',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-grammar-'))
 t.after(async()=>{await closeSceneBrowser();await fs.rm(root,{recursive:true,force:true})})
 const tokens=JSON.parse(await fs.readFile(new URL('gov-briefing/tokens.json',skillsRoot),'utf8'))
 const {grammar}=validateVisualTokens(tokens)
 const spec={id:'g',position:2,role:'problem',message:'流程必须建立证据约束',content:{title:'三类问题削弱可信度',bullets:['事实缺少来源','叙事缺少重点','页面难以修改']},
  designSystem:{palette:tokens.palette,typography:{fontFamily:'Microsoft YaHei'},grammar},visualIntent:{selectedVariant:'problem-cards'}}
 assert.equal(grammarFor(spec).titleStyle.align,'center')
 assert.match(grammarClasses(grammar),/has-grammar/)
 assert.match(decorations(grammar),/deco-band/)
 const html=slideHtml(spec,'problem-cards')
 assert.match(html,/class="slide [^"]*has-grammar[^"]*title-center[^"]*no-gradient/)
 const file=path.join(root,'g.html');await fs.writeFile(file,html)
 const scene=await captureScene(file,path.join(root,'g.png'))
 const title=scene.nodes.find(node=>node.tag==='h1')
 assert.equal(title.style.fontSize,grammar.typeScale.title)
 assert.equal(title.style.textAlign,'center')
 const footer=scene.nodes.find(node=>node.tag==='footer')
 assert.equal(Math.round(footer.bbox.x),grammar.grid.margin.x)
 assert.ok(scene.exportLayer.items.some(item=>item.kind==='box'&&item.z<0),'decorations sit behind content')
 assert.ok(safeCandidate(deterministicScore(scene,spec,'problem-cards')))
 // Legacy decks without grammar keep their established markup.
 const plain=slideHtml({...spec,designSystem:{}},'problem-cards')
 assert.doesNotMatch(plain,/class="slide [^"]*has-grammar/)
 assert.doesNotMatch(plain,/class="deco /)
})

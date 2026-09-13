import {referenceRegions} from './reference-layout.mjs'
import {sourceLabel} from './source-label.mjs'
import pptxgen from 'pptxgenjs'
import JSZip from 'jszip'
import fs from 'node:fs/promises'
import {metricDataset,namedMetricTable,transitionDataset,metricTokens as numbers} from './data.mjs'
import {resolveComposition,contentLayout,editorialContent,sameStatement,tableFits} from './content.mjs'

const C={bg:'F6F7FB',ink:'182033',muted:'667085',line:'E3E7F0',deep:'20284D',deep2:'313A6B',primary:'625BF6',mint:'78E3C5',mintSoft:'E6FAF4',lavender:'ECEAFF',white:'FFFFFF'}
const defaultColors=Object.freeze({...C})
const roleLabels={cover:'封面',agenda:'目录',section:'章节',background:'研究背景',problem:'研究问题',method:'方法论',architecture:'系统架构',evidence:'证据链路',data:'数据结果',comparison:'性能对比',insight:'关键洞察',conclusion:'结论',questions:'问答'}
let font='Microsoft YaHei'
let cardRadius=.12
const ShapeType=new pptxgen().ShapeType
const ChartType=new pptxgen().ChartType

function applyDesignSystem(spec){
 Object.assign(C,defaultColors);font='Microsoft YaHei'
 const palette=spec?.designSystem?.palette??{},map={bg:'bg',ink:'ink',line:'line',deep:'deep',primary:'primary',accent:'mint'}
 for(const [source,target] of Object.entries(map)){
  const value=String(palette[source]??'').replace(/^#/,'')
  if(/^[0-9A-F]{6}$/i.test(value))C[target]=value.toUpperCase()
 }
 const suppliedFont=String(spec?.designSystem?.typography?.fontFamily??'').split(',')[0].replace(/["']/g,'').trim()
 if(suppliedFont)font=suppliedFont
 const radius=Number(spec?.designSystem?.radius?.card)
 cardRadius=Number.isFinite(radius)?Math.max(.02,Math.min(.2,radius/120)):.12
 C.deep2=C.deep;C.lavender=C.bg;C.mintSoft=C.bg
}

function text(slide,value,options={}){slide.addText(String(value??''),{fontFace:font,margin:0,fit:'shrink',...options})}
function card(slide,x,y,w,h,fill=C.white,line=C.line,radius=cardRadius){slide.addShape(ShapeType.roundRect,{x,y,w,h,rectRadius:radius,fill:{color:fill},line:{color:line,width:1}})}
const sourceText=sourceLabel
function cleanAudienceText(value){return String(value??'').replace(/\s*[（(]\s*(?:S|SRC)\s*\d*\s*[）)]/gi,'').replace(/\s*\[\s*(?:S|SRC)\s*\d+\s*\]/gi,'').replace(/\s{2,}/g,' ').trim()}
function cleanAudienceSpec(spec){return {...spec,message:cleanAudienceText(spec.message),content:{...(spec.content??{}),title:cleanAudienceText(spec.content?.title),bullets:(spec.content?.bullets??[]).map(cleanAudienceText)}}}
function selectedVariantVisual(spec){
 const variant=spec.visualIntent?.selectedVariant
 if(variant==='media-focus')return 'media'
 if(variant==='split')return 'split'
 if(variant==='cards')return 'cards'
 if(['big-statement','statement','closing-statement','minimal-qa'].includes(variant))return 'typography'
 if(['chart-focus','metric-wall','table-highlight','comparison-bars','scorecard','ablation'].includes(variant))return 'chart'
 if(['workflow','three-stage','process','timeline','layered-architecture','pipeline','hub-spoke','evidence-chain','source-map','claim-map'].includes(variant))return 'diagram'
 return null
}
function brandLabel(spec){return String(spec?.designSystem?.brand?.name??'').trim()}
function coverSubtitle(spec){
 const communication=spec?.designSystem?.communication??{},title=String(spec.content?.title??'').trim()
 return String(communication.coverStrapline||(String(spec.message??'').trim()===title?'':spec.message??'')).trim()
}
function addBrandLogo(slide,spec){
 const logo=String(spec?.designSystem?.brand?.logoPath??'')
 if(logo)try{slide.addImage({path:logo,x:11.15,y:.46,w:1.15,h:.42,altText:brandLabel(spec)||'品牌标识'})}catch{}
}
function base(slide,spec,dark=false){
 slide.background={color:dark?C.deep:C.bg}
 addBrandLogo(slide,spec)
 const source=sourceText(spec)
 if(source)text(slide,`来源：${source}`,{x:.72,y:7.01,w:10.8,h:.2,fontSize:9,color:dark?'AEB7D4':C.muted})
 text(slide,String(spec.position).padStart(2,'0'),{x:12.05,y:7.0,w:.52,h:.2,fontSize:9,color:dark?'AEB7D4':C.muted,align:'right'})
 if(typeof slide.addNotes==='function'){
  const intent=spec.speakerIntent??{},refs=sourceText(spec,true)
  const assetSources=(spec.assetBindings??[]).filter(item=>item.provenance).map(item=>`- 视觉素材：${item.provenance}${item.license?' · 许可 '+item.license:''}${item.sourceUrl?' · '+item.sourceUrl:''}`)
  const notes=[
   `本页结论：${spec.message??''}`,
   intent.narration?`旁白：${intent.narration}`:'',
   ...(intent.talkingPoints??[]).map(point=>`要点：${point}`),
   ...(intent.sourceBoundaries??[]).map(point=>`适用边界：${point}`),
   intent.transition?`过渡：${intent.transition}`:'',
   '[Sources]',
   refs?`- 内容来源：${refs}`:'- 内容来源：用户创作简报',
   ...assetSources,
   '[/Sources]',
  ].filter(Boolean)
  slide.addNotes(notes.join('\n'))
 }
}
function heading(slide,spec,{dark=false,title=displayTitle(spec),y=.48}={}){
 text(slide,roleLabels[spec.role]??spec.role??'正文',{x:.72,y,w:2.2,h:.24,fontSize:11,bold:true,color:dark?C.mint:C.primary,charSpacing:1.4})
 text(slide,title,{x:.72,y:y+.46,w:11.65,h:.82,fontSize:35,bold:true,color:dark?C.white:C.ink,breakLine:true})
}
function numberedItems(slide,items,x,y,w,{dark=false,size=16,gap=.62}={}){
 items.forEach((item,index)=>{
  card(slide,x,y+index*gap,.34,.34,dark?C.deep2:C.lavender,dark?C.deep2:C.lavender,.08)
  text(slide,String(index+1).padStart(2,'0'),{x:x+.04,y:y+index*gap+.085,w:.26,h:.12,fontSize:7,bold:true,color:dark?C.mint:C.primary,align:'center'})
  text(slide,item,{x:x+.5,y:y+index*gap-.01,w:w-.5,h:.42,fontSize:size,color:dark?C.white:C.ink,breakLine:true})
 })
}
function firstNumber(value,fallback='—'){return numbers(value)[0]??fallback}
function metricValue(value){const found=numbers(value);return /分.*秒/.test(String(value))?found.join(''):found[0]??'—'}
export function nativeTableDataset(spec){
 const items=spec.content?.bullets??[],table=namedMetricTable(items)
 if(table)return table
 const transition=transitionDataset(items)
 if(transition)return {headers:['指标',`原值 (${transition.unit||'数值'})`,`现值 (${transition.unit||'数值'})`],
  rows:transition.series[0].labels.map((label,index)=>[label,transition.series[0].values[index],transition.series[1].values[index]])}
 const pipeRows=items.map(item=>String(item).split(/\s*\|\s*/).filter(Boolean)).filter(row=>row.length>=2)
 if(pipeRows.length===items.length&&pipeRows.length>=2&&new Set(pipeRows.map(row=>row.length)).size===1)return {
  headers:pipeRows[0].map((_,index)=>`列 ${index+1}`),rows:pipeRows,
 }
 return null
}
function chartOptions(dataset){
 const format=dataset.isRatio?'0.0000':`0.##${dataset.unit?`"${dataset.unit}"`:dataset.isPercent?'"%"':''}`
 return {
  x:.86,y:1.9,w:11.55,h:3.92,
  barDir:'bar',barGrouping:'clustered',catAxisOrientation:'maxMin',catAxisLabelPos:'low',
  catAxisLabelFontFace:font,catAxisLabelFontSize:12,
  valAxisLabelFontFace:font,valAxisLabelFontSize:10,
  valGridLine:{color:C.line,width:1},showCatName:false,showTitle:false,
  showLegend:dataset.series.length>1,legendPos:'b',legendFontFace:font,legendFontSize:11,
  showValue:true,dataLabelPosition:'outEnd',dataLabelColor:C.ink,dataLabelFormatCode:format,
  valAxisLabelFormatCode:format,valAxisMinVal:dataset.axisMin??0,
  ...(dataset.axisMax!==undefined?{valAxisMaxVal:dataset.axisMax}:{}),
  chartColors:[C.primary,C.mint,C.deep,'A0A7B8'],showBorder:false,
  barGapWidthPct:48,barOverlapPct:0,
 }
}
function nativeMetricChart(slide,spec,items){
 const dataset=transitionDataset(items)||metricDataset(items)
 if(!dataset)return false
 slide.addChart(ChartType.bar,dataset.series,chartOptions(dataset))
 card(slide,2.05,5.92,9.25,.62,C.deep,C.deep,.1)
 text(slide,spec.message,{x:2.36,y:6.08,w:8.62,h:.28,fontSize:15,bold:true,color:C.mint,align:'center',breakLine:true})
 return true
}
function nativeTable(slide,spec){
 const dataset=nativeTableDataset(spec)
 if(!dataset||!tableFits(dataset))return false
 const header=dataset.headers.map(value=>({text:String(value),options:{bold:true,color:C.white,fill:C.deep,align:'center'}}))
 const rows=dataset.rows.map((row,rowIndex)=>row.map(value=>({
  text:String(value),options:{fill:rowIndex%2?C.white:C.lavender,color:C.ink,align:typeof value==='number'?'right':'left'},
 })))
 slide.addTable([header,...rows],{
  x:.84,y:1.92,w:11.65,h:Math.min(3.9,.56*(rows.length+1)),
  border:{type:'solid',color:C.line,width:1},fontFace:font,fontSize:13,
  margin:.1,breakLine:false,autoFit:false,
 })
 card(slide,2.05,5.92,9.25,.62,C.deep,C.deep,.1)
 text(slide,spec.message,{x:2.36,y:6.08,w:8.62,h:.28,fontSize:15,bold:true,color:C.mint,align:'center',breakLine:true})
 return true
}
function metricWall(slide,spec){
 const items=(spec.content?.bullets??[]).filter(item=>numbers(item).length).slice(0,3)
 if(!items.length)return false
 base(slide,spec);heading(slide,spec)
 const width=items.length===1?7.2:items.length===2?5.55:3.66,start=items.length===1?3.05:.76,gap=items.length===3?.42:.5
 items.forEach((item,index)=>{
  const x=start+index*(width+gap),dark=index===Math.min(1,items.length-1)
  card(slide,x,2.02,width,3.55,dark?C.deep:C.white,dark?C.deep:C.line,.18)
  text(slide,metricValue(item),{x:x+.24,y:2.68,w:width-.48,h:.82,fontSize:items.length===1?48:38,bold:true,color:dark?C.mint:C.primary,align:'center'})
  text(slide,item,{x:x+.34,y:3.88,w:width-.68,h:.92,fontSize:16,bold:true,color:dark?C.white:C.ink,align:'center',breakLine:true})
 })
 text(slide,spec.message,{x:1.1,y:5.92,w:11.1,h:.38,fontSize:15,bold:true,color:C.primary,align:'center',breakLine:true})
 return true
}
function comparisonColumnsPptx(slide,spec){
 base(slide,spec);heading(slide,spec)
  const items=(spec.content?.bullets??[]),mid=Math.ceil(items.length/2)
  card(slide,.78,2.05,5.68,3.65,C.white,C.line,.08);card(slide,6.82,2.05,5.68,3.65,C.deep,C.deep,.08)
  text(slide,'关键观察',{x:1.1,y:2.42,w:4.95,h:.32,fontSize:18,bold:true,color:C.primary})
  text(slide,'决策含义',{x:7.14,y:2.42,w:4.95,h:.32,fontSize:18,bold:true,color:C.mint})
  numberedItems(slide,items.slice(0,mid),1.1,3.1,4.95,{size:16,gap:.82})
  numberedItems(slide,items.slice(mid),7.14,3.1,4.95,{dark:true,size:16,gap:.82})
 return true
}
function problemContrastPptx(slide,spec){
 base(slide,spec);heading(slide,spec)
 const items=(spec.content?.bullets??[]).slice(0,3)
 slide.addShape(ShapeType.rect,{x:.76,y:2.02,w:4.55,h:3.78,fill:{color:C.deep},line:{color:C.deep}})
 slide.addShape(ShapeType.rect,{x:.76,y:2.02,w:.1,h:3.78,fill:{color:C.mint},line:{color:C.mint}})
 text(slide,'核心矛盾',{x:1.12,y:2.48,w:1.5,h:.28,fontSize:11,bold:true,color:C.mint,charSpacing:1.4})
 text(slide,spec.message,{x:1.12,y:3.12,w:3.75,h:1.65,fontSize:24,bold:true,color:C.white,breakLine:true,valign:'mid'})
 numberedItems(slide,items,5.8,2.24,6.25,{size:17,gap:1.08})
 return true
}
function summaryGridPptx(slide,spec){
 base(slide,spec);heading(slide,spec)
 const items=(spec.content?.bullets??[]).slice(0,4)
 if(items[0]){
  card(slide,.76,2.02,6.0,3.74,C.deep,C.deep,.08)
  text(slide,'01',{x:1.08,y:2.42,w:.5,h:.24,fontSize:10,bold:true,color:C.mint})
  text(slide,items[0],{x:1.08,y:3.12,w:5.36,h:1.55,fontSize:23,bold:true,color:C.white,breakLine:true,valign:'mid'})
 }
 items.slice(1,4).forEach((item,index)=>{
  const y=2.02+index*1.23
  slide.addShape(ShapeType.rect,{x:7.12,y,w:5.42,h:1.05,fill:{color:C.white},line:{color:C.line,width:1}})
  slide.addShape(ShapeType.rect,{x:7.12,y,w:.07,h:1.05,fill:{color:C.primary},line:{color:C.primary}})
  text(slide,`0${index+2}`,{x:7.42,y:y+.34,w:.46,h:.22,fontSize:9,bold:true,color:C.primary})
  text(slide,item,{x:8.02,y:y+.22,w:4.15,h:.54,fontSize:16,bold:true,color:C.ink,breakLine:true})
 })
 return true
}
function boundImage(spec){return (spec.assetBindings??[]).find(item=>item.path&&['generated-image','source-image','licensed-image'].includes(item.type))}
function boundMedia(spec){return (spec.assetBindings??[]).find(item=>item.path&&['licensed-video','licensed-audio'].includes(item.type))}
function addBoundImage(slide,asset,x,y,w,h){
 const iw=Number(asset.width),ih=Number(asset.height)
 if(['source-image','licensed-image'].includes(asset.type)&&iw>0&&ih>0){
  const scale=Math.min(w/iw,h/ih),width=iw*scale,height=ih*scale
  slide.addImage({path:asset.path,x:x+(w-width)/2,y:y+(h-height)/2,w:width,h:height,altText:asset.alt??'来源视觉'})
 }else slide.addImage({path:asset.path,x,y,w,h,altText:asset.alt??'主题配图'})
}
const genericTitle=/^(?:研究|项目|系统|方案)?(?:背景|问题|方法|方法论|流程|架构|数据|结果|实验|验证|分析|洞察|结论|总结|价值|优势|方向|应用)(?:与|及|和|、|的|研究|分析|验证|结果|价值|方向|应用|总结|介绍|概述|模块)*$/
function displayTitle(spec){const title=String(spec.content?.title??'').trim(),message=String(spec.message??'').trim();return message&&message.length<=24&&genericTitle.test(title)?message:title||message||'未命名页面'}

function imageStory(slide,spec){
 base(slide,spec);heading(slide,spec)
 const asset=boundImage(spec),items=(spec.content?.bullets??[]).slice(0,4)
 if(['source-image','licensed-image'].includes(asset.type)){
  const kind=asset.kind??spec.visualIntent?.figureKind??'figure',wide=kind==='chart'||Number(asset.width)>Number(asset.height)*1.2
  const figureWidth=wide?7.45:5.55,notesX=wide?8.55:6.72,notesWidth=wide?3.75:5.72
  card(slide,.76,1.92,figureWidth,4.28,C.white,C.line,.16)
  addBoundImage(slide,asset,.9,2.06,figureWidth-.28,4.0)
  numberedItems(slide,items,notesX,2.02,notesWidth,{size:wide?12:14,gap:.72})
  card(slide,notesX,5.04,notesWidth,.78,C.deep,C.deep,.12)
  text(slide,spec.message,{x:notesX+.22,y:5.25,w:notesWidth-.44,h:.32,fontSize:wide?11:13,bold:true,color:C.mint,align:'center',breakLine:true})
  text(slide,asset.provenance??asset.caption??'原文图表',{x:.9,y:6.34,w:figureWidth-.28,h:.18,fontSize:7,color:C.muted,align:'right'})
  return
 }
 const imageLeft=spec.layoutPlan?.focalPoint==='left',pointsX=imageLeft?6.66:.78,imageX=imageLeft ? .78 : 6.92
 numberedItems(slide,items,pointsX,2.0,5.9,{size:14,gap:.72})
 card(slide,pointsX,4.78,5.75,.9,C.deep,C.deep,.14)
 text(slide,spec.message,{x:pointsX+.3,y:5.06,w:5.16,h:.36,fontSize:14,bold:true,color:C.mint,align:'center',breakLine:true})
 card(slide,imageX,2.0,5.62,3.72,C.white,C.line,.18)
 addBoundImage(slide,asset,imageX+.13,2.13,5.36,3.46)
 text(slide,asset.provenance??'主题配图',{x:imageX+1.63,y:5.82,w:3.85,h:.18,fontSize:7,color:C.muted,align:'right'})
}

function mediaStory(slide,spec){
 base(slide,spec);heading(slide,spec)
 const asset=boundMedia(spec),items=(spec.content?.bullets??[]).slice(0,4)
 const mediaLeft=spec.layoutPlan?.focalPoint==='left',pointsX=mediaLeft?7.28:.78,mediaX=mediaLeft ? .78 : 6.28
 numberedItems(slide,items,pointsX,2.0,5.25,{size:13,gap:.7})
 card(slide,pointsX,5.02,5.15,.75,C.deep,C.deep,.12)
 text(slide,spec.message,{x:pointsX+.24,y:5.22,w:4.68,h:.32,fontSize:12,bold:true,color:C.mint,align:'center',breakLine:true})
 card(slide,mediaX,1.94,6.24,3.86,'11172C','11172C',.18)
 try{
  if(typeof slide.addMedia==='function')slide.addMedia({type:asset.type==='licensed-video'?'video':'audio',path:asset.path,x:mediaX+.14,y:2.08,w:5.96,h:3.58})
  else text(slide,asset.type==='licensed-video'?'视频素材将在演示软件中播放':'音频素材将在演示软件中播放',{x:mediaX+.5,y:3.42,w:5.18,h:.54,fontSize:18,bold:true,color:C.white,align:'center'})
 }catch{
  text(slide,asset.type==='licensed-video'?'视频素材（请在演示软件中播放）':'音频素材（请在演示软件中播放）',{x:mediaX+.5,y:3.42,w:5.18,h:.54,fontSize:18,bold:true,color:C.white,align:'center'})
 }
 text(slide,asset.provenance??asset.caption??'已绑定媒体素材',{x:mediaX+1,y:5.96,w:5.02,h:.18,fontSize:7,color:C.muted,align:'right'})
}

function cover(slide,spec){
 base(slide,spec,true)
 const variant=spec.visualIntent?.selectedVariant??'hero',minimal=variant==='minimal-cover',editorial=variant==='editorial-cover'
 if(!minimal){
  slide.addShape(ShapeType.ellipse,{x:10.0,y:.08,w:3.15,h:3.15,fill:{color:C.primary,transparency:35},line:{color:C.primary,transparency:100}})
  slide.addShape(ShapeType.ellipse,{x:10.75,y:.32,w:2.0,h:2.0,fill:{color:C.mint,transparency:80},line:{color:C.mint,transparency:100}})
 }
 const brand=brandLabel(spec)
 if(brand)text(slide,brand,{x:minimal?4.55:.82,y:.62,w:minimal?4.2:4.2,h:.28,fontSize:12,bold:true,color:C.mint,charSpacing:1.2,align:minimal?'center':'left'})
 if(editorial)slide.addShape(ShapeType.rect,{x:.82,y:1.25,w:.9,h:.08,fill:{color:C.mint},line:{color:C.mint}})
 text(slide,spec.content?.title??spec.message,{x:minimal?1.35:.82,y:minimal?2.0:1.58,w:minimal?10.65:editorial?8.4:9.5,h:1.75,fontSize:minimal?48:50,bold:true,color:C.white,breakLine:true,align:minimal?'center':'left'})
 const subtitle=coverSubtitle(spec)
 if(subtitle)text(slide,subtitle,{x:minimal?2.1:.84,y:minimal?4.02:3.58,w:minimal?9.15:7.9,h:.7,fontSize:17,color:'DCE1F2',breakLine:true,align:minimal?'center':'left'})
 const items=(spec.content?.bullets??[]).slice(0,3)
 items.forEach((item,index)=>{
  card(slide,.82+index*3.75,5.3,3.35,.72,C.deep2,C.deep2,.12)
  text(slide,item,{x:1.02+index*3.75,y:5.52,w:2.95,h:.3,fontSize:11,color:C.white,align:'center'})
 })
 const communication=spec.designSystem?.communication??{},meta=[communication.audience,communication.durationMinutes?`${communication.durationMinutes} 分钟`:null].filter(Boolean).join('  ·  ')
 if(meta)text(slide,meta,{x:.84,y:6.44,w:6.6,h:.3,fontSize:11,color:'DCE1F2'})
}
function coverWithImage(slide,spec){
 base(slide,spec,true)
 const asset=boundImage(spec)
 slide.addImage({path:asset.path,x:8.15,y:0,w:5.18,h:7.5})
 slide.addShape(ShapeType.rect,{x:7.2,y:0,w:2.3,h:7.5,fill:{color:C.deep,transparency:18},line:{color:C.deep,transparency:100}})
 const brand=brandLabel(spec)
 if(brand)text(slide,brand,{x:.82,y:.62,w:4.2,h:.28,fontSize:12,bold:true,color:C.mint,charSpacing:1.2})
 text(slide,spec.content?.title??spec.message,{x:.82,y:1.5,w:7.0,h:1.78,fontSize:46,bold:true,color:C.white,breakLine:true})
 const subtitle=coverSubtitle(spec)
 if(subtitle)text(slide,subtitle,{x:.84,y:3.52,w:6.65,h:.72,fontSize:16,color:'DCE1F2',breakLine:true})
 const items=(spec.content?.bullets??[]).slice(0,2)
 items.forEach((item,index)=>{card(slide,.82+index*3.25,5.18,2.95,.72,C.deep2,C.deep2,.12);text(slide,item,{x:1.02+index*3.25,y:5.4,w:2.55,h:.3,fontSize:10,color:C.white,align:'center'})})
 const communication=spec.designSystem?.communication??{},meta=[communication.audience,communication.durationMinutes?`${communication.durationMinutes} 分钟`:null].filter(Boolean).join('  ·  ')
 if(meta)text(slide,meta,{x:.84,y:6.44,w:6.6,h:.3,fontSize:11,color:'DCE1F2'})
 text(slide,asset.provenance??'AI 生成概念图',{x:9.15,y:6.92,w:3.0,h:.18,fontSize:7,color:'DCE1F2',align:'right'})
}
function agenda(slide,spec){
 base(slide,spec);heading(slide,spec)
 const items=(spec.content?.bullets??[]).slice(0,4),variant=spec.visualIntent?.selectedVariant
 if(variant==='section-map'){
  slide.addShape(ShapeType.line,{x:1.35,y:3.05,w:10.45,h:0,line:{color:C.primary,width:2.5}})
  items.forEach((item,index)=>{
   const x=1.15+index*3.02
   slide.addShape(ShapeType.ellipse,{x:x+.6,y:2.83,w:.44,h:.44,fill:{color:index%2?C.mint:C.primary},line:{color:C.bg,width:2}})
   text(slide,String(index+1).padStart(2,'0'),{x:x+.48,y:3.55,w:.68,h:.22,fontSize:10,bold:true,color:C.primary,align:'center'})
   text(slide,item,{x,y:3.92,w:1.65,h:1.0,fontSize:16,bold:true,color:C.ink,align:'center',breakLine:true})
  })
  return
 }
 if(variant==='agenda-cards'){
  items.forEach((item,index)=>{
   const col=index%2,row=Math.floor(index/2),x=.82+col*6.02,y=2.02+row*1.72,dark=index===0
   card(slide,x,y,5.48,1.4,dark?C.deep:C.white,dark?C.deep:C.line,.16)
   text(slide,String(index+1).padStart(2,'0'),{x:x+.28,y:y+.28,w:.58,h:.24,fontSize:10,bold:true,color:dark?C.mint:C.primary})
   text(slide,item,{x:x+1.0,y:y+.28,w:4.05,h:.72,fontSize:18,bold:true,color:dark?C.white:C.ink,breakLine:true})
  })
  return
 }
 items.forEach((item,index)=>{
  const col=index%2,row=Math.floor(index/2),x=.82+col*6.02,y=2.04+row*1.57
  slide.addShape(ShapeType.line,{x,y,w:5.48,h:0,line:{color:index<2?C.primary:C.line,width:index<2?2:1}})
  text(slide,String(index+1).padStart(2,'0'),{x,y:y+.3,w:.58,h:.26,fontSize:11,bold:true,color:C.primary})
  text(slide,item,{x:x+.82,y:y+.18,w:4.54,h:.78,fontSize:18,bold:true,color:C.ink,breakLine:true})
 })
 slide.addShape(ShapeType.line,{x:.82,y:5.42,w:11.66,h:0,line:{color:C.line,width:1}})
 text(slide,spec.message,{x:.82,y:5.72,w:11.66,h:.38,fontSize:13,color:C.muted,align:'center'})
}
function section(slide,spec){
 base(slide,spec,true)
 slide.addShape(ShapeType.ellipse,{x:10.08,y:.06,w:3.05,h:3.05,fill:{color:C.primary,transparency:42},line:{color:C.primary,transparency:100}})
 text(slide,`${String(spec.position).padStart(2,'0')} · 章节导航`,{x:.82,y:.72,w:2.8,h:.28,fontSize:10,bold:true,color:C.mint,charSpacing:1.8})
 text(slide,spec.content?.title??spec.message,{x:.82,y:2.22,w:9.6,h:1.55,fontSize:39,bold:true,color:C.white,breakLine:true})
 text(slide,spec.message,{x:.84,y:4.08,w:7.6,h:.55,fontSize:18,color:C.mint,breakLine:true})
 slide.addShape(ShapeType.roundRect,{x:.84,y:5.15,w:2.3,h:.08,rectRadius:.04,fill:{color:C.mint},line:{color:C.mint}})
 const brand=brandLabel(spec)
 if(brand)text(slide,brand,{x:.84,y:6.44,w:4.0,h:.24,fontSize:10,color:'AEB7D4'})
}
function background(slide,spec){
 const variant=spec.visualIntent?.selectedVariant
 if(variant==='big-statement')return typographyStory(slide,spec)
 if(variant==='timeline')return timeline(slide,spec)
 base(slide,spec);heading(slide,spec)
 const items=spec.content?.bullets??[],metricItem=items.find(item=>numbers(item).length)
 if(metricItem){
  card(slide,.76,2.0,4.15,3.95,C.deep,C.deep,.18)
  text(slide,metricValue(metricItem),{x:1.04,y:2.55,w:3.56,h:1.05,fontSize:48,bold:true,color:C.mint,align:'center'})
  text(slide,metricItem,{x:1.18,y:3.7,w:3.28,h:1.0,fontSize:15,bold:true,color:C.white,align:'center',breakLine:true})
  numberedItems(slide,items.filter(item=>item!==metricItem).slice(0,3),5.55,2.24,6.6,{size:17,gap:1.02})
 }else{
  numberedItems(slide,items.slice(0,4),.9,2.1,6.1,{size:16,gap:.82})
  card(slide,7.45,2.08,5.0,3.55,C.deep,C.deep,.18)
  text(slide,spec.message,{x:7.88,y:2.72,w:4.14,h:2.15,fontSize:21,bold:true,color:C.mint,align:'center',valign:'mid',breakLine:true})
 }
}
function problem(slide,spec){
 if(spec.visualIntent?.selectedVariant==='contrast')return problemContrastPptx(slide,spec)
 if(spec.visualIntent?.selectedVariant==='before-after')return flow(slide,spec,false)
 base(slide,spec);heading(slide,spec)
 const items=(spec.content?.bullets??[]).slice(0,3),metric=items.find(item=>numbers(item).length)
 if(!metric){
  items.forEach((item,index)=>{
   const x=.76+index*4.08,dark=index===1
   card(slide,x,2.05,3.66,3.55,dark?C.deep:C.white,dark?C.deep:C.line,.18)
   text(slide,String(index+1).padStart(2,'0'),{x:x+.32,y:2.45,w:.52,h:.28,fontSize:11,bold:true,color:dark?C.mint:C.primary})
   text(slide,item,{x:x+.38,y:3.18,w:2.9,h:1.35,fontSize:18,bold:true,color:dark?C.white:C.ink,align:'center',valign:'mid',breakLine:true})
  })
  return
 }
 const rest=items.filter(item=>item!==metric).slice(0,2)
 card(slide,.76,2.05,4.18,3.72,C.deep,C.deep,.18)
 text(slide,'核心代价',{x:1.06,y:2.42,w:1.4,h:.22,fontSize:9,bold:true,color:C.mint,charSpacing:1.4})
 text(slide,metricValue(metric),{x:1.04,y:3.05,w:3.62,h:.92,fontSize:48,bold:true,color:C.mint,align:'center'})
 text(slide,metric,{x:1.12,y:4.28,w:3.48,h:.62,fontSize:14,color:C.white,align:'center',breakLine:true})
 rest.forEach((item,index)=>{
  const x=5.35+index*3.56
  card(slide,x,2.05,3.18,2.52,C.white,C.line,.14)
  slide.addShape(ShapeType.rect,{x,y:2.05,w:3.18,h:.05,fill:{color:C.primary},line:{color:C.primary}})
  text(slide,`0${index+2}`,{x:x+.26,y:2.38,w:.48,h:.22,fontSize:9,bold:true,color:C.primary})
  text(slide,item,{x:x+.28,y:3.08,w:2.62,h:.84,fontSize:16,bold:true,color:C.ink,align:'center',valign:'mid',breakLine:true})
 })
 card(slide,5.35,4.87,6.74,.72,C.lavender,C.lavender,.12)
 text(slide,spec.message,{x:5.68,y:5.11,w:6.08,h:.24,fontSize:13,bold:true,color:C.primary,align:'center'})
}
function flow(slide,spec,vertical=false){
 base(slide,spec);heading(slide,spec)
 const items=(spec.content?.bullets??[]).slice(0,4)
 if(vertical){
  items.forEach((item,index)=>{
   const y=1.88+index*1.04
   card(slide,1.05,y,11.15,.78,index%2?C.white:C.lavender,index%2?C.line:C.lavender,.12)
   text(slide,`层级 ${index+1}`,{x:1.38,y:y+.24,w:1.1,h:.2,fontSize:9,bold:true,color:C.primary})
   text(slide,item,{x:2.7,y:y+.17,w:8.9,h:.36,fontSize:16,bold:true,color:C.ink,breakLine:true})
  })
 }else{
  items.forEach((item,index)=>{
   const x=.72+index*3.12
   card(slide,x,2.25,2.62,2.62,index===2?C.deep:C.white,index===2?C.deep:C.line,.16)
   text(slide,String(index+1).padStart(2,'0'),{x:x+.25,y:2.52,w:.55,h:.28,fontSize:11,bold:true,color:index===2?C.mint:C.primary})
   text(slide,item,{x:x+.25,y:3.12,w:2.12,h:.92,fontSize:15,bold:true,color:index===2?C.white:C.ink,breakLine:true,valign:'mid'})
   if(index<items.length-1)text(slide,'→',{x:x+2.7,y:3.16,w:.36,h:.4,fontSize:19,bold:true,color:C.primary,align:'center'})
  })
 }
 text(slide,spec.message,{x:1.1,y:5.75,w:11.1,h:.38,fontSize:14,color:C.muted,align:'center'})
}
function timeline(slide,spec){
 base(slide,spec);heading(slide,spec)
 const items=(spec.content?.bullets??[]).slice(0,5),startX=1.05,endX=12.15,y=3.38
 slide.addShape(ShapeType.line,{x:startX,y,w:endX-startX,h:0,line:{color:C.primary,width:3,beginArrowType:'none',endArrowType:'triangle'}})
 items.forEach((item,index)=>{
  const x=startX+(endX-startX-.45)*(items.length===1?0:index/(items.length-1))
  slide.addShape(ShapeType.ellipse,{x:x-.12,y:y-.12,w:.3,h:.3,fill:{color:index===items.length-1?C.mint:C.primary},line:{color:C.white,width:2}})
  const above=index%2===0
  text(slide,String(index+1).padStart(2,'0'),{x:x-.18,y:above?2.25:3.82,w:.48,h:.2,fontSize:9,bold:true,color:C.primary,align:'center'})
  text(slide,item,{x:x-1.05,y:above?2.5:4.08,w:2.2,h:.76,fontSize:14,bold:true,color:C.ink,align:'center',valign:above?'bottom':'top',breakLine:true})
 })
 text(slide,spec.message,{x:1.1,y:5.78,w:11.1,h:.36,fontSize:14,color:C.muted,align:'center'})
}
function hubSpoke(slide,spec){
 base(slide,spec);heading(slide,spec)
 const items=(spec.content?.bullets??[]).slice(0,4),center={x:5.15,y:2.55,w:3.0,h:1.35}
 const nodes=[{x:.88,y:2.05},{x:9.82,y:2.05},{x:1.7,y:4.52},{x:9.0,y:4.52}].slice(0,items.length)
 nodes.forEach(node=>slide.addShape(ShapeType.line,{x:center.x+center.w/2,y:center.y+center.h/2,w:node.x+1.22-(center.x+center.w/2),h:node.y+.58-(center.y+center.h/2),line:{color:C.primary,width:1.5,endArrowType:'triangle'}}))
 card(slide,center.x,center.y,center.w,center.h,C.deep,C.deep,.18)
 text(slide,spec.message,{x:center.x+.25,y:center.y+.28,w:center.w-.5,h:.76,fontSize:17,bold:true,color:C.mint,align:'center',valign:'mid',breakLine:true})
 nodes.forEach((node,index)=>{
  card(slide,node.x,node.y,2.45,1.16,C.white,C.line,.14)
  text(slide,`0${index+1}`,{x:node.x+.18,y:node.y+.18,w:.38,h:.2,fontSize:8,bold:true,color:C.primary})
  text(slide,items[index],{x:node.x+.48,y:node.y+.22,w:1.78,h:.62,fontSize:13,bold:true,color:C.ink,align:'center',valign:'mid',breakLine:true})
 })
}
function structuredDiagram(slide,spec){
 const variant=spec.visualIntent?.selectedVariant
 if(variant==='timeline')return timeline(slide,spec)
 if(['hub-spoke','source-map'].includes(variant))return hubSpoke(slide,spec)
 if(['layered-architecture','claim-map'].includes(variant))return flow(slide,spec,true)
 return flow(slide,spec,false)
}
function evidence(slide,spec){
 base(slide,spec);heading(slide,spec)
 const labels=['原始章节','数字事实','页面结论'],items=(spec.content?.bullets??[]).slice(0,3)
 labels.forEach((label,index)=>{
  const x=.92+index*4.12
  card(slide,x,2.2,3.46,2.12,index===1?C.deep:C.white,index===1?C.deep:C.line,.17)
  text(slide,label,{x:x+.28,y:2.48,w:2.9,h:.3,fontSize:11,bold:true,color:index===1?C.mint:C.primary,align:'center'})
  text(slide,items[index]??label,{x:x+.3,y:3.08,w:2.86,h:.72,fontSize:15,bold:true,color:index===1?C.white:C.ink,align:'center',valign:'mid',breakLine:true})
  if(index<2)text(slide,'→',{x:x+3.58,y:2.97,w:.4,h:.42,fontSize:21,bold:true,color:C.primary,align:'center'})
 })
 card(slide,2.3,5.1,8.75,.75,C.mintSoft,C.mintSoft,.14)
 text(slide,spec.message,{x:2.62,y:5.34,w:8.1,h:.27,fontSize:14,bold:true,color:'126F5D',align:'center'})
}
function data(slide,spec){
 if(['metric-wall','scorecard'].includes(spec.visualIntent?.selectedVariant)&&metricWall(slide,spec))return
 const items=spec.content?.bullets??[]
 if(!transitionDataset(items)&&!metricDataset(items)&&!nativeTableDataset(spec)){completeContent(slide,spec);return}
 base(slide,spec);heading(slide,spec)
 if(spec.visualIntent?.selectedVariant==='table-highlight'&&nativeTable(slide,spec))return
 if(nativeMetricChart(slide,spec,items))return
 if(!nativeTable(slide,spec))completeContent(slide,spec)
}
function comparison(slide,spec){
 if(spec.visualIntent?.selectedVariant==='two-column')return comparisonColumnsPptx(slide,spec)
 return data(slide,spec)
}
function insight(slide,spec){
 if(spec.visualIntent?.selectedVariant==='big-statement')return typographyStory(slide,spec)
 if(spec.visualIntent?.selectedVariant==='ablation')return data(slide,spec)
 base(slide,spec);heading(slide,spec)
 const items=(spec.content?.bullets??[]).slice(0,2)
 items.forEach((item,index)=>{
  const x=.76+index*6.08,vals=numbers(item).slice(0,2)
  card(slide,x,2.1,5.62,3.28,index===0?C.deep:C.white,index===0?C.deep:C.line,.18)
  const label=vals.length?(String(item).split(/[：:。；;]/)[0].slice(0,24)||`发现 ${index+1}`):`洞察 0${index+1}`
  text(slide,label,{x:x+.36,y:2.48,w:4.9,h:.35,fontSize:16,bold:true,color:index===0?C.mint:C.primary})
  if(vals.length){
   text(slide,vals.join(' → '),{x:x+.36,y:3.18,w:4.9,h:.7,fontSize:32,bold:true,color:index===0?C.white:C.ink,align:'center'})
   text(slide,item,{x:x+.42,y:4.36,w:4.78,h:.54,fontSize:11,color:index===0?'DCE1F2':C.muted,align:'center',breakLine:true})
  }else text(slide,item,{x:x+.44,y:3.15,w:4.7,h:1.35,fontSize:20,bold:true,color:index===0?C.white:C.ink,align:'left',valign:'mid',breakLine:true})
 })
 text(slide,(spec.content?.bullets??[])[2]??spec.message,{x:1.2,y:5.88,w:10.95,h:.35,fontSize:16,bold:true,color:C.primary,align:'center'})
}
function conclusion(slide,spec){
 if(spec.visualIntent?.selectedVariant==='summary-grid')return summaryGridPptx(slide,spec)
 if(spec.visualIntent?.selectedVariant==='next-steps')return timeline(slide,spec)
 base(slide,spec);heading(slide,spec)
 const items=spec.content?.bullets??[]
 items.slice(0,3).forEach((item,index)=>{
  const x=.82+index*3.88
  if(index>0)slide.addShape(ShapeType.line,{x:x-.24,y:2.12,w:0,h:2.72,line:{color:C.line,width:1}})
  text(slide,String(index+1).padStart(2,'0'),{x,y:2.22,w:.52,h:.24,fontSize:10,bold:true,color:C.primary})
  text(slide,item,{x,y:3.08,w:3.28,h:1.08,fontSize:17,bold:true,color:C.ink,align:'left',valign:'mid',breakLine:true})
 })
 slide.addShape(ShapeType.line,{x:.82,y:5.02,w:11.66,h:0,line:{color:C.primary,width:2}})
 const closing=items[3]??(items.some(item=>sameStatement(item,spec.message))?'':spec.message)
 if(closing)text(slide,closing,{x:.98,y:5.35,w:11.34,h:.42,fontSize:14,bold:true,color:C.primary,align:'center'})
}
function typographyStory(slide,spec){
 base(slide,spec);heading(slide,spec)
 const items=(spec.content?.bullets??[]).slice(0,3)
 card(slide,.76,2.05,11.82,3.68,C.deep,C.deep,.08)
 slide.addShape(ShapeType.rect,{x:.76,y:2.05,w:.08,h:3.68,fill:{color:C.mint},line:{color:C.mint}})
 text(slide,'“',{x:1.08,y:2.18,w:.7,h:.7,fontFace:'Georgia',fontSize:54,bold:true,color:C.mint})
 text(slide,items[0]??spec.message,{x:1.86,y:2.55,w:9.8,h:1.02,fontSize:25,bold:true,color:C.white,breakLine:true})
 items.slice(1).forEach((item,index)=>{
  const x=1.86+index*4.92
  slide.addShape(ShapeType.line,{x,y:4.1,w:4.35,h:0,line:{color:'697197',width:1}})
  text(slide,`0${index+1}`,{x,y:4.32,w:.48,h:.2,fontSize:8,bold:true,color:C.mint})
  text(slide,item,{x:x+.5,y:4.24,w:3.8,h:.52,fontSize:12,color:'E5E8F2',breakLine:true})
 })
 if(!sameStatement(items[0],spec.message))text(slide,spec.message,{x:7.2,y:5.26,w:4.7,h:.2,fontSize:9,bold:true,color:C.mint,align:'right'})
}
function questions(slide,spec){
 base(slide,spec,true)
 slide.addShape(ShapeType.ellipse,{x:10.0,y:.08,w:3.15,h:3.15,fill:{color:C.primary,transparency:28},line:{color:C.primary,transparency:100}})
 text(slide,'Q & A',{x:.82,y:.68,w:2.4,h:.35,fontSize:12,bold:true,color:C.mint,charSpacing:3})
 text(slide,spec.content?.title??'问答环节',{x:.82,y:1.66,w:8.4,h:1.05,fontSize:44,bold:true,color:C.white})
 text(slide,spec.message,{x:.84,y:3.02,w:8.3,h:.6,fontSize:20,color:C.mint,breakLine:true})
 numberedItems(slide,(spec.content?.bullets??[]).slice(0,3),.86,4.25,7.5,{dark:true,size:13,gap:.64})
 text(slide,'感谢聆听',{x:10.28,y:5.72,w:1.75,h:.4,fontSize:14,bold:true,color:C.white,align:'center'})
}

function splitStory(slide,spec){
 base(slide,spec);heading(slide,spec)
 const regions=spec.layoutPlan?.regions??[],primary=regions.find(item=>item.id==='primary'),support=regions.find(item=>item.id==='support'),manual=spec.layoutPlan?.manualOverride&&primary&&support
 const mapX=value=>.78+Number(value)*.98,mapW=value=>Math.max(1.5,Number(value)*.98)
 const primaryX=manual?mapX(primary.x):.92,primaryW=manual?mapW(primary.w):6.1,supportX=manual?mapX(support.x):7.42,supportW=manual?mapW(support.w):5.02
 numberedItems(slide,(spec.content?.bullets??[]).slice(0,4),primaryX,2.05,primaryW,{size:16,gap:.78})
 card(slide,supportX,2.05,supportW,3.65,C.deep,C.deep,.18)
 text(slide,spec.message,{x:supportX+.34,y:2.68,w:Math.max(1,supportW-.68),h:2.3,fontSize:22,bold:true,color:C.mint,align:'center',valign:'mid',breakLine:true})
}

function completeContent(slide,spec){
 base(slide,spec);heading(slide,spec)
 const asset=boundImage(spec),media=boundMedia(spec),layout=contentLayout(spec,{hasAsset:Boolean(asset||media)})
 const contentWidth=asset||media?6.25:11.88,gap=.46,width=(contentWidth-gap*(layout.columns-1))/layout.columns
 let index=0
 layout.groups.forEach((group,column)=>{
  const weights=layout.weights[column],total=weights.reduce((sum,value)=>sum+value,0)||1
  const available=3.7-.12*Math.max(0,group.length-1)
  let y=2.02
  group.forEach((item,row)=>{
   const x=.72+column*(width+gap),height=available*weights[row]/total
   slide.addShape(ShapeType.line,{x,y,w:width,h:0,line:{color:C.line,width:.8}})
   text(slide,String(++index).padStart(2,'0'),{x,y:y+.17,w:.3,h:.18,fontSize:9,color:C.primary,bold:true})
   text(slide,item,{x:x+.45,y:y+.13,w:width-.45,h:Math.max(.3,height-.18),fontSize:layout.fontSize*.75,color:C.ink,bold:true,valign:'mid',breakLine:true})
   y+=height+.12
  })
 })
 if(asset)addBoundImage(slide,asset,7.3,2.02,5.25,3.38)
 if(media)slide.addMedia({type:media.type==='licensed-video'?'video':'audio',path:media.path,x:7.3,y:2.02,w:5.25,h:3.38})
 if(asset||media)text(slide,(asset||media).provenance??(asset||media).caption??'',{x:7.3,y:5.46,w:5.25,h:.3,fontSize:9,color:C.muted})
 slide.addShape(ShapeType.rect,{x:.72,y:5.98,w:11.88,h:.59,fill:{color:C.line},line:{color:C.line}})
 text(slide,spec.message,{x:.95,y:6.1,w:11.4,h:.35,fontSize:15,bold:true,color:C.ink,breakLine:true})
}

function evidenceBrief(slide,spec){
 base(slide,spec);heading(slide,spec)
 const {lead,points}=editorialContent(spec)
 slide.addShape(ShapeType.line,{x:.72,y:2.04,w:4.66,h:0,line:{color:C.primary,width:3.75}})
 text(slide,'核心判断',{x:.72,y:2.4,w:4.25,h:.22,fontSize:11,bold:true,color:C.primary})
 text(slide,lead,{x:.72,y:2.95,w:4.25,h:2.5,fontSize:24,bold:true,color:C.ink,breakLine:true,valign:'mid'})
 const height=Math.min(1.28,3.8/Math.max(1,points.length)),start=2.04+(3.8-height*points.length)/2
 points.forEach((point,index)=>{
  const y=start+index*height
  slide.addShape(ShapeType.line,{x:6.05,y,w:6.55,h:0,line:{color:C.line,width:.75}})
  text(slide,String(index+1).padStart(2,'0'),{x:6.05,y:y+.22,w:.33,h:.18,fontSize:9,bold:true,color:C.primary})
  text(slide,point,{x:6.58,y:y+.14,w:6.02,h:height-.22,fontSize:16.5,bold:true,color:C.ink,breakLine:true,valign:'mid'})
 })
}

async function removeDanglingPackageDeclarations(output){
 const buffer=await fs.readFile(output),zip=await JSZip.loadAsync(buffer)
 const typesFile=zip.file('[Content_Types].xml')
 if(!typesFile)return
 const declared=await typesFile.async('string')
 const normalized=declared.replace(
  /<Override PartName="\/ppt\/slideMasters\/slideMaster(\d+)\.xml" ContentType="application\/vnd\.openxmlformats-officedocument\.presentationml\.slideMaster\+xml"\/>/g,
  (entry,index)=>zip.file(`ppt/slideMasters/slideMaster${index}.xml`)?entry:'',
 )
 if(normalized===declared)return
 zip.file('[Content_Types].xml',normalized)
 await fs.writeFile(output,await zip.generateAsync({type:'nodebuffer',compression:'DEFLATE'}))
}

export async function exportPptx(slides,output){
 applyDesignSystem(slides[0])
 const pptx=new pptxgen();pptx.layout='LAYOUT_WIDE';pptx.author='映章';pptx.subject='映章智能演示';pptx.company='映章';pptx.lang='zh-CN';pptx.theme={headFontFace:font,bodyFontFace:font,lang:'zh-CN'}
 for(const rawSpec of slides){
  const spec=cleanAudienceSpec(rawSpec)
  applyDesignSystem(spec)
  const slide=pptx.addSlide()
  if(spec.visualIntent?.selectedVariant==='personal-reference'){
   const regions=referenceRegions(spec)
   if(regions){
    slide.background={color:C.bg}
    for(const region of regions)text(slide,region.text,{x:region.x*13.333333,y:region.y*7.5,w:region.w*13.333333,h:region.h*7.5,fontSize:region.fontSize*.75,fontFace:region.fontFamily??font,bold:region.title,color:C.ink,margin:0,breakLine:false,valign:'top'})
    slide.addNotes((spec.sourceRefs??[]).map(ref=>`${ref.document??''} ${ref.section??''}`).join(' / '))
    continue
   }
  }
  if(resolveComposition(spec,spec.visualIntent?.selectedVariant)==='content-list'){completeContent(slide,spec);continue}
  if(resolveComposition(spec,spec.visualIntent?.selectedVariant)==='evidence-brief'){evidenceBrief(slide,spec);continue}
 const handler={cover,agenda,section,background,problem,method:(s,v)=>flow(s,v,false),architecture:(s,v)=>flow(s,v,true),evidence,data,comparison,insight,conclusion,questions}[spec.role]
  const asset=boundImage(spec),media=boundMedia(spec)
  const selectedVisual=selectedVariantVisual(spec),visual=selectedVisual??spec.visualIntent?.primaryVisual
  if(media&&spec.role!=='cover'&&spec.role!=='questions')mediaStory(slide,spec)
  else if(asset&&spec.role==='cover')coverWithImage(slide,spec)
  else if(asset&&spec.role!=='questions')imageStory(slide,spec)
  else if(spec.role==='cover')cover(slide,spec)
  else if(selectedVisual==='typography')typographyStory(slide,spec)
  else if(selectedVisual==='split')splitStory(slide,spec)
  else if(selectedVisual==='cards')summaryGridPptx(slide,spec)
  else if(selectedVisual==='chart')data(slide,spec)
  else if(selectedVisual==='diagram')structuredDiagram(slide,spec)
  else if(['agenda','section','background','problem','insight','conclusion','questions'].includes(spec.role)&&handler)handler(slide,spec)
  else if(visual==='chart')data(slide,spec)
  else if(visual==='typography')typographyStory(slide,spec)
  else if(visual==='generated-image'&&spec.role!=='cover')typographyStory(slide,spec)
  else if(handler)handler(slide,spec)
  else if(visual==='diagram')flow(slide,spec,false)
  else splitStory(slide,spec)
 }
 await pptx.writeFile({fileName:output})
 await removeDanglingPackageDeclarations(output)
}

import {missingContent,resolveComposition} from './content.mjs'
import {textContrast} from './contrast.mjs'
import {metricDataset,namedMetricTable} from './data.mjs'
const PAGE_AREA=1280*720
const clamp=value=>Math.max(0,Math.min(100,Math.round(value)))
const area=box=>Math.max(0,box.width)*Math.max(0,box.height)
const fontSize=node=>Number.parseFloat(node.style?.fontSize??0)||0

const VARIANT_FAMILIES={
 'evidence-brief':'typography',
 hero:'cover','editorial-cover':'cover-editorial','minimal-cover':'typography',
 'numbered-list':'list','section-map':'map','agenda-cards':'cards',
 'chapter-divider':'section','section-statement':'typography','minimal-section':'minimal',
 'big-statement':'typography','context-cards':'cards',timeline:'timeline',
 'problem-cards':'cards',contrast:'comparison','before-after':'comparison',
 workflow:'flow','three-stage':'stages',process:'flow','layered-architecture':'layers',pipeline:'flow','hub-spoke':'map',
 'evidence-chain':'flow','source-map':'map','claim-map':'layers',
 'chart-focus':'chart','metric-wall':'metrics','table-highlight':'table',
 'comparison-bars':'chart','two-column':'comparison',scorecard:'metrics',
 'finding-cards':'cards',ablation:'chart',takeaways:'list','summary-grid':'cards','next-steps':'timeline',
 'minimal-qa':'minimal','closing-statement':'typography',contact:'contact',split:'split',statement:'typography',cards:'cards',
 'figure-wide':'image-wide','figure-analysis':'image-analysis','figure-focus':'image-focus','image-story':'image-split','media-focus':'media',
}

export const variantFamily=variant=>VARIANT_FAMILIES[variant]??variant??'unspecified'

function intersection(a,b){const width=Math.max(0,Math.min(a.x+a.width,b.x+b.width)-Math.max(a.x,b.x)),height=Math.max(0,Math.min(a.y+a.height,b.y+b.height)-Math.max(a.y,b.y));return width*height}
function overlapPairs(nodes){
 const candidates=nodes.filter(node=>node.type!=='group'&&node.region!=='footer')
 let count=0
 for(let i=0;i<candidates.length;i++)for(let j=i+1;j<candidates.length;j++){
  const a=candidates[i],b=candidates[j],overlap=intersection(a.bbox,b.bbox),small=Math.min(area(a.bbox),area(b.bbox))
  if((a.ancestorIds??[]).includes(b.id)||(b.ancestorIds??[]).includes(a.id))continue
  if(!overlap||!small||(overlap/small>=.80&&(a.type!=='text'||b.type!=='text')))continue
  if(a.type==='text'&&b.type==='text'&&overlap/small<.08)continue
  if(overlap>180)count++
 }
 return count
}

function coverageRatio(nodes){
 const columns=40,rows=23,cells=new Set()
 for(const node of nodes){
  if(node.region==='footer'||node.region==='header'||node.type==='group')continue
  const box=node.bbox??{},boxArea=area(box)
  if(boxArea<80||boxArea>PAGE_AREA*.82)continue
  const x0=Math.max(0,Math.floor(box.x/1280*columns)),x1=Math.min(columns-1,Math.floor((box.x+box.width)/1280*columns))
  const y0=Math.max(0,Math.floor(box.y/720*rows)),y1=Math.min(rows-1,Math.floor((box.y+box.height)/720*rows))
  for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++)cells.add(`${x}:${y}`)
 }
 return cells.size/(columns*rows)
}

const audienceMetricText=item=>String(item).replace(/[（(]\s*(?:S|SRC)\s*\d*\s*[）)]/gi,'').replace(/\[\s*(?:S|SRC)\s*\d+\s*\]/gi,'')
const metricCount=items=>{
 const structured=metricDataset(items)||namedMetricTable(items)
 if(structured)return items.length
 return items.filter(rawItem=>{
 const item=audienceMetricText(rawItem)
 return /\d[\d,]*(?:\.\d+)?\s*(?:%|个百分点|倍|万|亿|ms|毫秒|秒|分|分钟|小时|MB|GB|TB)/i.test(item)
  || /(?:Accuracy|Precision|Recall|F1|MRR|nDCG|Hit@?\d*|准确率|召回率|精确率|完整率|支撑率|通过率)\D{0,10}\d/i.test(item)
  || /\b0\.\d{2,}\b/.test(item)
 }).length
}
const pairCount=items=>items.filter(item=>/(?:从|由)\s*\d+(?:\.\d+)?%?.{0,10}(?:至|到|为)\s*\d+(?:\.\d+)?%?|\d+(?:\.\d+)?%?\s*(?:→|->|➡)\s*\d+(?:\.\d+)?%?/.test(String(item))).length
function contentFitScore(spec,variant){
 if(resolveComposition(spec,variant)==='content-list')return 90
 if(resolveComposition(spec,variant)==='evidence-brief')return 95
 const items=spec.content?.bullets??[],metrics=metricCount(items),pairs=pairCount(items),count=items.length
 const hasAsset=(spec.assetBindings??[]).some(item=>item.path||item.dataUri)
 if(variant.startsWith('figure-')||variant==='image-story')return hasAsset?100:20
 if(variant==='media-focus')return (spec.assetBindings??[]).some(item=>['licensed-video','licensed-audio'].includes(item.type))?100:20
 if(variant==='metric-wall'||variant==='scorecard')return metrics>=3?100:metrics===2?84:metrics===1?62:24
 if(variant==='chart-focus')return metrics>=2?100:metrics===1?68:28
 if(variant==='table-highlight')return metrics>=2?96:metrics===1?55:22
 if(variant==='comparison-bars')return pairs>=2?100:pairs===1?82:metrics>=2?64:28
 if(variant==='two-column')return pairs>=1?96:count>=2?82:48
 if(variant==='ablation')return metrics>=2?96:count>=2?70:44
 if(['timeline','next-steps'].includes(variant))return count>=3&&count<=5?94:count===2?76:58
 if(['hub-spoke','source-map'].includes(variant))return count>=3&&count<=5?96:count===2?72:52
 if(['layered-architecture','claim-map'].includes(variant))return count>=3&&count<=5?96:count===2?78:55
 if(['workflow','three-stage','process','pipeline','evidence-chain'].includes(variant))return count>=3&&count<=4?96:count===2?82:60
 if(['big-statement','statement','section-statement','closing-statement'].includes(variant))return count<=3?94:66
 if(['context-cards','problem-cards','agenda-cards','finding-cards','summary-grid','cards'].includes(variant))return count>=3&&count<=4?91:count===2?78:62
 if(['minimal-cover','minimal-section','minimal-qa'].includes(variant))return count<=1?96:72
 const planned=spec.layoutPlan?.candidateOrder??[]
 return planned.includes(variant)?Math.max(84,96-planned.indexOf(variant)*4):84
}

function visualEvidenceScore(nodes,variant){
 const meaningful=nodes.filter(node=>['chart','diagram','table','image','svg','video'].includes(node.type)).length
 if(meaningful)return clamp(82+Math.min(18,meaningful*6))
 const family=variantFamily(variant)
 if(family==='typography')return 88
 if(['split','comparison','timeline','layers','map','flow','stages'].includes(family))return 82
 if(['cards','list','metrics'].includes(family))return 70
 return 62
}

export function recomputeOverall(score){
 return clamp(
  score.geometry*.16+score.readability*.14+score.hierarchy*.12+score.whitespace*.09+
  score.alignment*.08+score.semanticFit*.12+score.contentFit*.11+score.visualEvidence*.07+
  (score.planningFit??90)*.06+
  score.styleConsistency*.03+score.deckRhythm*.02
 )
}

export function safeCandidate(score){
 return score.geometry>=80&&score.readability>=78&&(score.contentFit??score.semanticFit??0)>=62
  &&!['overflow','clipping','textOverflow','missingAssets','missingContent'].some(key=>score[key]>0)
  &&!(score.issues??[]).some(issue=>issue.severity==='error')
}

export function deterministicScore(scene,spec,variant='split'){
 const nodes=scene.nodes??[],text=nodes.filter(node=>scene.measurementVersion>=2?node.isTextLeaf:node.type==='text'||node.text)
 const overflow=nodes.filter(node=>node.bbox.x<0||node.bbox.y<0||node.bbox.x+node.bbox.width>1280||node.bbox.y+node.bbox.height>720).length
 const overlaps=overlapPairs(nodes)
 const clipping=text.filter(node=>fontSize(node)>0&&node.bbox.height<(fontSize(node)*.72)).length
 const textOverflow=text.filter(node=>node.measurement?.textClipped).length
 const missingAssets=nodes.filter(node=>node.measurement?.assetMissing).length+(spec.assetLoadErrors??[]).length
 const omitted=missingContent(scene,spec)
 const lowContrast=text.filter(node=>node.text&& !['footer','header'].includes(node.region)&&fontSize(node)>=18&&(textContrast(node)??21)<3)
 const issues=[
  ...(spec.assetLoadErrors??[]),
  ...omitted.map(item=>({code:'missing-content',severity:'error',bulletIndex:item.index,message:'页面未展示该条内容，请调整版式',text:item.text})),
  ...lowContrast.map(node=>({code:'low-text-contrast',severity:'error',nodeId:node.id,message:'文字与所在背景对比度不足',ratio:Math.round(textContrast(node)*100)/100,text:node.text.slice(0,100)})),
  ...text.filter(node=>node.measurement?.textClipped).map(node=>({code:'text-clipped',severity:'error',nodeId:node.id,message:'文字被容器或画布裁切',text:node.text.slice(0,100)})),
  ...nodes.filter(node=>node.measurement?.assetMissing).map(node=>({code:'missing-asset',severity:'error',nodeId:node.id,message:'图片未成功加载'})),
 ]
 const contentText=text.filter(node=>!['footer','header','title'].includes(node.region))
 const tooSmall=contentText.filter(node=>fontSize(node)>0&&fontSize(node)<11).length
 const bodyLegibility=contentText.filter(node=>fontSize(node)>0&&fontSize(node)<15.5).length
 const density=(spec.content?.bullets??[]).join('').length
 const bulletCount=(spec.content?.bullets??[]).length
 const title=String(spec.content?.title??'')
 const genericTitle=/^(?:背景|背景介绍|核心内容|方法概述|项目介绍|研究内容|主要内容|总结|结论)$/.test(title.trim())
 const occupied=coverageRatio(nodes)
 const geometry=clamp(100-overflow*35-overlaps*10-clipping*18-textOverflow*25-missingAssets*35)
 const complete=resolveComposition(spec,variant)==='content-list'
 const readability=clamp(100-tooSmall*12-bodyLegibility*3-Math.max(0,density-(complete?520:340))/3-Math.max(0,bulletCount-(complete?8:4))*12)
 const titleNode=text.find(node=>node.region==='title')
 const hierarchy=clamp((text.some(node=>node.text===spec.content?.title)?100:62)-(genericTitle?24:0)-Math.max(0,35-(titleNode?fontSize(titleNode):35))*2)
 const whitespace=clamp(100-Math.abs(.43-occupied)*125-Math.max(0,density-300)/8)
 const aligned=nodes.filter(node=>Math.min(Math.abs(node.bbox.x%4),Math.abs(4-node.bbox.x%4))<1.25).length
 const alignment=clamp(nodes.length?62+(aligned/nodes.length)*38:70)
 const candidates=spec.visualIntent?.archetypeCandidates??[]
 const contentFit=contentFitScore(spec,variant)
 const semantic=clamp((candidates.includes(variant)?92:70)*.55+contentFit*.45)
 const fontFamilies=new Set(text.map(node=>node.style?.fontFamily).filter(Boolean))
 const styleConsistency=clamp(100-Math.max(0,fontFamilies.size-2)*12)
 const visualEvidence=visualEvidenceScore(nodes,variant)
 const plannedConstraints=spec.layoutPlan?.constraints??{}
 const minOccupied=Number(plannedConstraints.minOccupiedRatio??.18),maxOccupied=Number(plannedConstraints.maxOccupiedRatio??.78)
 const planningPenalty=occupied<minOccupied?(minOccupied-occupied)*90:occupied>maxOccupied?(occupied-maxOccupied)*90:0
 const plannedVariant=spec.layoutPlan?.recommendedVariant
 const planningFit=clamp(100-planningPenalty-(plannedVariant&&plannedVariant!==variant?18:0))
 const score={geometry,readability,hierarchy,whitespace,alignment,semantic,semanticFit:semantic,contentFit,visualEvidence,planningFit,styleConsistency,deckRhythm:90,overflow,overlaps,clipping,tooSmall,bodyLegibility,density,bulletCount,genericTitle,occupied:Math.round(occupied*1000)/1000,variantFamily:variantFamily(variant)}
 score.overall=recomputeOverall(score)
 Object.assign(score,{textOverflow,missingAssets,missingContent:omitted.length,lowContrast:lowContrast.length,issues,effectiveVariant:resolveComposition(spec,variant)})
 score.needsReview=!safeCandidate(score)
 return score
}

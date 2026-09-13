import {referenceRegions} from './reference-layout.mjs'
import fs from 'node:fs/promises'
import path from 'node:path'
import {slideHtml,deckHtml} from './author.mjs'
import {captureScene,closeSceneBrowser,exportPdf} from './scene.mjs'
import {deterministicScore,recomputeOverall,variantFamily,safeCandidate} from './score.mjs'
import {exportPptx} from './pptx.mjs'
import {fileURLToPath,pathToFileURL} from 'node:url'
import {renderStamp,matchesRenderStamp} from './render-input.mjs'
import {metricDataset,namedMetricTable} from './data.mjs'

const defaults={
 cover:['hero','editorial-cover','minimal-cover'],agenda:['numbered-list','section-map','agenda-cards'],section:['chapter-divider','section-statement','minimal-section'],
 background:['big-statement','context-cards','timeline'],problem:['problem-cards','contrast','before-after'],
 method:['workflow','three-stage','process'],architecture:['layered-architecture','pipeline','hub-spoke'],
 evidence:['evidence-chain','source-map','claim-map'],data:['chart-focus','metric-wall','table-highlight'],
 comparison:['comparison-bars','two-column','scorecard'],insight:['finding-cards','ablation','big-statement'],
 conclusion:['takeaways','summary-grid','next-steps'],questions:['minimal-qa','closing-statement','contact'],
 content:['split','statement','cards'],
}
async function hydrateAssets(spec){
 const clone=structuredClone(spec),assets=clone.assetBindings??[]
 clone.assetLoadErrors=[]
 for(const asset of assets){
  if(!asset.path||asset.dataUri)continue
  if(['licensed-video','licensed-audio'].includes(asset.type)){asset.mediaUri=pathToFileURL(asset.path).href;continue}
  try{
   const data=await fs.readFile(asset.path),ext=path.extname(asset.path).toLowerCase()
   const mime=ext==='.svg'?'image/svg+xml':ext==='.jpg'||ext==='.jpeg'?'image/jpeg':ext==='.webp'?'image/webp':'image/png'
   asset.dataUri=`data:${mime};base64,${data.toString('base64')}`
  }catch{clone.assetLoadErrors.push({code:'missing-asset',severity:'error',message:'绑定的图片文件无法读取',assetId:asset.id??null})}
 }
 const logoPath=clone.designSystem?.brand?.logoPath
 if(logoPath){
  try{
   const data=await fs.readFile(logoPath),ext=path.extname(logoPath).toLowerCase()
   const mime=ext==='.svg'?'image/svg+xml':ext==='.jpg'||ext==='.jpeg'?'image/jpeg':'image/png'
   clone.designSystem.brand.logoDataUri=`data:${mime};base64,${data.toString('base64')}`
  }catch{clone.assetLoadErrors.push({code:'missing-asset',severity:'error',message:'品牌标识文件无法读取'})}
 }
 return clone
}
export function candidateVariants(spec){
 const personalLayout=referenceRegions(spec)?['personal-reference']:[]
 const preferred=spec.visualIntent?.selectedVariant
 const learned=spec.designSystem?.referenceGrammar?.variantByRole?.[spec.role]??[]
 const asset=(spec.assetBindings??[]).find(item=>item.path&&['generated-image','source-image','licensed-image'].includes(item.type))
 const media=(spec.assetBindings??[]).find(item=>item.path&&['licensed-video','licensed-audio'].includes(item.type))
 if(media)return [...new Set([preferred,'media-focus'].filter(Boolean))]
 if(asset){
  if(asset.type==='generated-image')return [...new Set([preferred,'image-story'].filter(Boolean))]
  const requested=spec.visualIntent?.archetypeCandidates
  const variants=Array.isArray(requested)&&requested.length?requested:['figure-wide','figure-analysis','image-story']
  return [...new Set([preferred,...learned,...variants].filter(Boolean))].slice(0,5)
 }
 const planned=spec.layoutPlan?.candidateOrder
 const requested=Array.isArray(planned)&&planned.length?planned:spec.visualIntent?.archetypeCandidates
 const variants=Array.isArray(requested)&&requested.length?requested:(defaults[spec.role]??defaults.content)
 const items=spec.content?.bullets??[]
 const hasMetric=Boolean(metricDataset(items)||namedMetricTable(items))||items.some(rawItem=>{
  const item=String(rawItem).replace(/[（(]\s*(?:S|SRC)\s*\d*\s*[）)]/gi,'').replace(/\[\s*(?:S|SRC)\s*\d+\s*\]/gi,'')
  return /\d[\d,]*(?:\.\d+)?\s*(?:%|倍|万|亿|ms|秒|分|分钟|小时|MB|GB)/i.test(item)
   || /(?:Accuracy|Precision|Recall|F1|MRR|nDCG|Hit@?\d*|准确率|召回率|精确率|完整率|支撑率|通过率)\D{0,10}\d/i.test(item)
   || /\b0\.\d{2,}\b/.test(item)
 })
 const explanatory=spec.visualIntent?.contentRelation==='explanation'&&!['cover','agenda','section','questions'].includes(spec.role)
 const structural=['workflow','process','pipeline','three-stage','evidence-chain','timeline','next-steps','layered-architecture','claim-map','source-map','hub-spoke','before-after']
 return [...new Set([preferred,...learned,...variants,...(explanatory?['evidence-brief']:[])].filter(Boolean))]
  .filter(variant=>!explanatory||!structural.includes(variant))
  .filter(variant=>hasMetric||!['metric','metric-wall','chart-focus','comparison-bars','scorecard'].includes(variant)||variant===preferred).slice(0,5).concat(personalLayout)
}

export async function main([command,input,output]=process.argv.slice(2)){
 const parsed=command==='pdf'?[]:JSON.parse(await fs.readFile(input,'utf8'))
 const slides=Array.isArray(parsed)?parsed:parsed?.slides
 if(command!=='pdf'&&!Array.isArray(slides))throw new Error('Input must be a slide array or a deck spec with a slides array')
 try{if(command==='build'){
 await fs.mkdir(path.join(output,'slides'),{recursive:true})
 const selected=[],finalScenes=[],usedVariants=new Map(),usedFamilies=new Map()
 let previousFamily=null
 for(const spec of slides){
 const root=path.join(output,'slides',String(spec.position))
 // A regenerated page can have a different candidate set. Remove old scores so
 // the visual critic can never select a stale variant from an earlier outline.
 await fs.rm(root,{recursive:true,force:true});await fs.mkdir(root,{recursive:true})
  const stamp=await renderStamp(spec),hydrated=await hydrateAssets(spec)
  let best=null,bestSafe=null,fallbackSafe=null,preferred=null,planned=null
  const renderedCandidates=[]
  for(const variant of [...new Set([...candidateVariants(spec),'content-list'])]){
   const safe=variant.replace(/[^a-z0-9_-]/gi,'-'),html=path.join(root,`${safe}.html`),png=path.join(root,`${safe}.png`)
   await fs.writeFile(html,slideHtml(hydrated,variant))
   const scene=await captureScene(html,png),score=deterministicScore(scene,hydrated,variant)
   score.renderStamp=stamp
   const family=variantFamily(score.effectiveVariant??variant),repeats=usedVariants.get(variant)??0,familyRepeats=usedFamilies.get(family)??0
   score.variantFamily=family
   score.deckRhythm=Math.max(48,100-repeats*16-familyRepeats*7-(previousFamily===family?18:0))
   score.overall=recomputeOverall(score)
   await fs.writeFile(path.join(root,`${safe}.scene.json`),JSON.stringify(scene,null,2))
   await fs.writeFile(path.join(root,`${safe}.score.json`),JSON.stringify(score,null,2))
   const result={variant,safe,score:score.overall,scoreDetail:score,scene}
   renderedCandidates.push(result)
   if(variant===spec.visualIntent?.selectedVariant)preferred=result
   if(variant===spec.layoutPlan?.recommendedVariant)planned=result
   if(!best||score.overall>best.score)best=result
   if(safeCandidate(score)){
    if(variant==='content-list')fallbackSafe=result
    else if(!bestSafe||score.overall>bestSafe.score)bestSafe=result
   }
  }
  const protectedSelection=['user','critic'].includes(spec.visualIntent?.variantSelectionSource)
  // Automatic selections belong to the previous render. When the planner has
  // produced a new recommendation, let that recommendation win on regeneration.
  if(!protectedSelection&&preferred&&spec.layoutPlan?.recommendedVariant&&preferred.variant!==spec.layoutPlan.recommendedVariant)preferred=null
  if(preferred&&!protectedSelection&&!safeCandidate(preferred.scoreDetail))preferred=null
  best=preferred??(planned&&safeCandidate(planned.scoreDetail)?planned:null)??bestSafe??fallbackSafe??best
  const personalVariant=spec.designSystem?.personalization?.preferredVariant??spec.designSystem?.personalization?.preferredByRole?.[spec.role]
  const personal=renderedCandidates.find(candidate=>candidate.variant===personalVariant)
  if(!protectedSelection&&personal&&best&&safeCandidate(personal.scoreDetail)&&['overall','geometry','readability','contentFit','semanticFit','hierarchy','visualEvidence'].every(key=>(personal.scoreDetail[key]??0)>=(best.scoreDetail[key]??0)))best=personal
  if(!protectedSelection&&best&&spec.designSystem?.personalization?.density==='airy'){
   const spacious=renderedCandidates.filter(candidate=>safeCandidate(candidate.scoreDetail)&&['overall','geometry','readability','contentFit','semanticFit','hierarchy','visualEvidence'].every(key=>(candidate.scoreDetail[key]??0)>=(best.scoreDetail[key]??0)))
   best=[best,...spacious].sort((a,b)=>(b.scoreDetail.whitespace??0)-(a.scoreDetail.whitespace??0))[0]
  }
  if(!best)throw new Error(`No evidence-safe candidate for slide ${spec.position}`)
  const chosen=await fs.readFile(path.join(root,`${best.safe}.html`),'utf8')
  selected.push(chosen);finalScenes.push({...best.scene,slideId:spec.id,position:spec.position,variant:best.variant})
  usedVariants.set(best.variant,(usedVariants.get(best.variant)??0)+1)
  const chosenFamily=best.scoreDetail.variantFamily
  usedFamilies.set(chosenFamily,(usedFamilies.get(chosenFamily)??0)+1)
  previousFamily=chosenFamily
  await fs.writeFile(path.join(output,'slides',`${spec.position}.html`),chosen)
  await fs.writeFile(path.join(root,'current.json'),JSON.stringify({variant:best.variant,score:best.score,scoreDetail:best.scoreDetail},null,2))
 }
 await fs.writeFile(path.join(output,'index.html'),deckHtml(selected))
 await fs.writeFile(path.join(output,'scene-ir.json'),JSON.stringify({version:'scene-ir-v1',slides:finalScenes},null,2))
 }else if(command==='assemble'){
  const selected=[],finalScenes=[]
  for(const spec of slides){
   const root=path.join(output,'slides',String(spec.position))
   let prior={};try{prior=JSON.parse(await fs.readFile(path.join(root,'current.json'),'utf8'))}catch{}
   const variant=spec.visualIntent?.selectedVariant||prior.variant
   if(!variant)throw new Error(`Slide ${spec.position} has no selected variant`)
   const safe=variant.replace(/[^a-z0-9_-]/gi,'-')
   const chosen=await fs.readFile(path.join(root,`${safe}.html`),'utf8')
   const scene=JSON.parse(await fs.readFile(path.join(root,`${safe}.scene.json`),'utf8'))
   const scoreDetail=JSON.parse(await fs.readFile(path.join(root,`${safe}.score.json`),'utf8'))
   if(!await matchesRenderStamp(scoreDetail.renderStamp,spec))throw new Error(`第 ${spec.position} 页内容或素材已修改，请重新生成该页后再合并`)
   selected.push(chosen);finalScenes.push({...scene,slideId:spec.id,position:spec.position,variant})
   await fs.writeFile(path.join(output,'slides',`${spec.position}.html`),chosen)
   await fs.writeFile(path.join(root,'current.json'),JSON.stringify({...prior,variant,score:scoreDetail.overall,scoreDetail},null,2))
  }
  await fs.writeFile(path.join(output,'index.html'),deckHtml(selected))
  await fs.writeFile(path.join(output,'scene-ir.json'),JSON.stringify({version:'scene-ir-v1',slides:finalScenes},null,2))
 }else if(command==='pptx')await exportPptx(slides,output)
 else if(command==='pdf')await exportPdf(input,output)
 else throw new Error(`Unknown command ${command}`)
 }finally{await closeSceneBrowser()}
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))await main()

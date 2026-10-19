import fs from 'node:fs/promises'
import path from 'node:path'
import {slideHtml,deckHtml} from './author.mjs'
import {captureScene,closeSceneBrowser,exportPdf} from './scene.mjs'
import {deterministicScore,recomputeOverall,variantFamily,safeCandidate} from './score.mjs'
import {exportPptx} from './pptx.mjs'
import {fileURLToPath,pathToFileURL} from 'node:url'
import {renderStamp,matchesRenderStamp} from './render-input.mjs'
import {candidateVariants} from './candidates.mjs'
import {hydrateAssets} from './assets.mjs'
export {candidateVariants}

const MAX_PORTABLE_MEDIA_BYTES=50*1024*1024
const mediaMimeByExtension={'.mp4':'video/mp4','.webm':'video/webm','.mov':'video/quicktime','.mp3':'audio/mpeg','.wav':'audio/wav','.m4a':'audio/mp4'}
async function portableDeckMedia(slides,selected,{strict=true}={}){
 let totalBytes=0
 const output=[...selected]
 const media=[]
 for(let index=0;index<slides.length;index++){
  for(const asset of slides[index].assetBindings??[]){
   if(!asset.path||!['licensed-video','licensed-audio'].includes(asset.type))continue
   const extension=path.extname(asset.path).toLowerCase(),mime=mediaMimeByExtension[extension]
   if(!mime){if(strict)throw new Error(`无法打包媒体格式 ${extension||'(无扩展名)'}`);return selected}
   const stat=await fs.stat(asset.path)
   totalBytes+=stat.size
   if(totalBytes>MAX_PORTABLE_MEDIA_BYTES){
    if(strict)throw new Error('演示中的音视频素材总量超过 50 MB，无法生成独立 HTML；请压缩或减少素材后重试')
    return selected
   }
   media.push({index,path:asset.path,mime,uri:pathToFileURL(asset.path).href})
  }
 }
 for(const asset of media){
  const data=await fs.readFile(asset.path)
  const dataUri=`data:${asset.mime};base64,${data.toString('base64')}`
  output[asset.index]=output[asset.index].split(asset.uri).join(dataUri)
 }
 return output
}

async function assembleDeck(slides,output,{portable=true,strict=true}={}){
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
 const htmlSlides=portable?await portableDeckMedia(slides,selected,{strict}):selected
 await fs.writeFile(path.join(output,'index.html'),deckHtml(htmlSlides))
 await fs.writeFile(path.join(output,'scene-ir.json'),JSON.stringify({version:'scene-ir-v1',slides:finalScenes},null,2))
}

export async function main([command,input,output,sceneRoot]=process.argv.slice(2)){
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
 await fs.writeFile(path.join(output,'index.html'),deckHtml(await portableDeckMedia(slides,selected,{strict:false})))
 await fs.writeFile(path.join(output,'scene-ir.json'),JSON.stringify({version:'scene-ir-v1',slides:finalScenes},null,2))
  }else if(command==='assemble')await assembleDeck(slides,output)
  else if(command==='assemble-local')await assembleDeck(slides,output,{strict:false})
  else if(command==='assemble-bundle')await assembleDeck(slides,output,{portable:false})
  else if(command==='pptx')await exportPptx(slides,output,{sceneRoot:sceneRoot||process.env.YINGZHANG_SCENE_ROOT||null,reportPath:`${output.replace(/\.pptx$/i,'')}.export.json`,keepBrowser:true})
 else if(command==='pdf')await exportPdf(input,output)
 else throw new Error(`Unknown command ${command}`)
 }finally{await closeSceneBrowser()}
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))await main()

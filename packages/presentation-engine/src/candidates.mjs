import {referenceRegions} from './reference-layout.mjs'
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


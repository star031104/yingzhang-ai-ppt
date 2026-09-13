import {metricDataset,namedMetricTable,metricTokens,transitionDataset} from './data.mjs'

// Shared by HTML and native PowerPoint. Capacity is a content contract, not a slice.
const capacity={cover:3,section:0,questions:3,agenda:4,background:4,problem:3,
 method:4,architecture:4,evidence:3,data:4,comparison:3,insight:2,conclusion:4,content:4}
const variantCapacity={'big-statement':3,statement:3,'closing-statement':3,'section-statement':0,
 'metric-wall':3,scorecard:3,timeline:5,'next-steps':5,'finding-cards':2,
 'hub-spoke':4,'source-map':4,'layered-architecture':4,'claim-map':4,
 workflow:4,process:4,pipeline:4,'three-stage':4,'evidence-chain':4,split:4,cards:4}

export const cleanText=value=>String(value??'').replace(/\s*[（(]\s*(?:S|SRC)\s*\d*\s*[）)]/gi,'').replace(/\s*\[\s*(?:S|SRC)\s*\d+\s*\]/gi,'').replace(/\s{2,}/g,' ').trim()
export const normalizedText=value=>cleanText(value).replace(/\s+/g,'').replace(/−/g,'-')
export const sameStatement=(left,right)=>normalizedText(left).replace(/[。.!！?？]+$/,'')===normalizedText(right).replace(/[。.!！?？]+$/,'')

export function editorialContent(spec){
 const lead=cleanText(spec.message||spec.content?.bullets?.[0]||spec.content?.title)
 return {lead,points:(spec.content?.bullets??[]).map(cleanText).filter(item=>!sameStatement(item,lead))}
}

export function resolveComposition(spec,variant){
 if(variant==='content-list')return variant
 if(spec.visualIntent?.contentRelation==='explanation'&&!['cover','agenda','section','questions'].includes(spec.role)&&['workflow','process','pipeline','three-stage','evidence-chain','timeline','next-steps','layered-architecture','claim-map','source-map','hub-spoke','before-after'].includes(variant))return resolveComposition(spec,'evidence-brief')
 const items=spec.content?.bullets??[],hasAsset=(spec.assetBindings??[]).some(asset=>asset.path||asset.dataUri)
 if(variant==='evidence-brief')return hasAsset||items.length>4||items.some(item=>cleanText(item).length>110)||editorialContent(spec).lead.length>70?'content-list':variant
 const chart=!['cover','section','questions'].includes(spec.role)&&(['chart-focus','comparison-bars','table-highlight','ablation'].includes(variant)||spec.visualIntent?.primaryVisual==='chart'||(['data','comparison'].includes(spec.role)&&!['split','cards','two-column','metric-wall','scorecard'].includes(variant)))
 const data=chart&&(transitionDataset(items)||metricDataset(items)||namedMetricTable(items))
 const table=variant==='table-highlight'&&namedMetricTable(items)
 if(table&&!tableFits(table))return 'content-list'
 if(chart&&!data&&!hasAsset&&!['metric-wall','scorecard'].includes(variant))return 'content-list'
 const limit=hasAsset?(spec.role==='cover'?2:4):['cover','section','questions'].includes(spec.role)?capacity[spec.role]:data?5:variantCapacity[variant]??capacity[spec.role]??4
 if(items.length>limit||items.some(item=>cleanText(item).length>110))return 'content-list'
 if(['metric-wall','scorecard'].includes(variant)&&items.some(item=>!metricTokens(item).length))return 'content-list'
 return variant
}

export function tableFits(dataset){
 if(!dataset?.headers?.length||!dataset?.rows?.length)return false
 const colWidth=11.65/dataset.headers.length-.2
 const weight=value=>[...String(value)].reduce((n,c)=>n+(/[\u4e00-\u9fff]/.test(c)?1:.55),0)
 const rows=[dataset.headers,...dataset.rows]
 const height=rows.reduce((n,row)=>n+Math.max(1,...row.map(cell=>Math.ceil(weight(cell)*13/72/colWidth)))*13*1.3/72+.2,0)
 return height<=3.7
}

// Balanced columns preserve reading order and keep the longest column within budget.
export function contentLayout(spec,{hasAsset=false}={}){
 const items=(spec.content?.bullets??[]).map(cleanText),weight=item=>Math.max(1,Math.ceil(item.length/(hasAsset?30:34)))
 let split=items.length,columns=1
 if(!hasAsset&&items.length>3){
  columns=2
  let best=Infinity
  for(let i=1;i<items.length;i++){
   const size=Math.max(items.slice(0,i).reduce((sum,item)=>sum+weight(item),0),items.slice(i).reduce((sum,item)=>sum+weight(item),0))
   if(size<best){best=size;split=i}
  }
 }
 const groups=columns===1?[items]:[items.slice(0,split),items.slice(split)]
 const units=Math.max(1,...groups.map(group=>group.reduce((sum,item)=>sum+weight(item),0)))
 const fontSize=units<=7?24:units<=10?22:20
 return {groups,columns,fontSize,weights:groups.map(group=>group.map(weight))}
}

export function missingContent(scene,spec){
 if(typeof scene.visibleText!=='string')return [] // Legacy scenes cannot prove coverage.
 const visible=normalizedText(scene.visibleText)
 const structured=new Set(scene.structuredContent??[])
 return (spec.content?.bullets??[]).flatMap((item,index)=>{
  const expected=normalizedText(item)
  return !expected||visible.includes(expected)||structured.has(index)?[]:[{index,text:cleanText(item)}]
 })
}

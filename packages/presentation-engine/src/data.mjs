// Both renderers consume this evidence table. Never manufacture missing measurements.
export function metricTokens(value){
 const text=String(value??'').trim()
 if(!text||/^[-+−]?\d+(?:\.\d+)?$/.test(text))return []
 return [...text.matchAll(/[-+−]?\d[\d,]*(?:\.\d+)?\s*(?:%|个百分点|倍|万|亿|小时|分钟|毫秒|秒|分|条|项|个|份|人|页|KB|MB|GB|TB|ms)?/gi)].filter(match=>{
  const token=match[0].trim(),before=text.slice(Math.max(0,(match.index??0)-6),match.index??0)
  if(/(?:F|Hit@|Top-?|表|图|第|\[|（|\()\s*$/i.test(before)&&!/[.%]/.test(token))return false
  if(/[.%]/.test(token)||/(?:个百分点|倍|万|亿|小时|分钟|毫秒|秒|分|条|项|个|份|人|页|KB|MB|GB|TB|ms)$/i.test(token))return true
  return Math.abs(Number(token.replaceAll(',','').replace('−','-')))>=10&&/[\u4e00-\u9fffA-Za-z]{2}/.test(text)
 }).map(match=>match[0].replace(/\s/g,'').replace('−','-'))
}

const metricNamePattern=/((?:Weighted\s*F1|Macro\s*(?:Precision|Recall|F1)|Accuracy|Precision|Recall@?\d*|F1(?:-score)?|MRR|nDCG@?\d*|Hit@?\d+)(?![A-Za-z0-9@_-])|准确率|召回率|精确率|完整率|支撑率|通过率|增长率|成本|耗时|时长|数量|得分|评分)\s*(?:达到|提升至|增至|下降至|降至|为|约为|约|:|：)?\s*([-+−]?\d[\d,]*(?:\.\d+)?)\s*(%|个百分点|倍|万元|亿元|万|亿|毫秒|分钟|小时|秒|元\/应用|元|ms)?/gi

export function namedMetrics(value){
 return [...String(value??'').matchAll(metricNamePattern)].map(match=>({
  name:match[1].replace(/-score/i,'').replace(/\s+/g,' '),
  value:Number(match[2].replaceAll(',','').replace('−','-')),
  unit:match[3]??'',index:match.index??0,end:(match.index??0)+match[0].length,raw:match[0],
 })).filter(pair=>Number.isFinite(pair.value))
}

function structuredRow(value){
 // Parser-produced rows have explicit subject + column + value delimiters.
 const match=String(value).match(/^([^：:；;]+)[：:]([^；;]+[：:].*)(?:[。.]?)$/)
 if(!match)return null
 const fields=match[2].split(/[；;]/).map(part=>{
  const field=part.trim().match(/^([^：:]{1,60})[：:]\s*(.+?)\s*$/)
  return field?{name:field[1].trim(),value:field[2].trim()}:null
 })
 if(fields.some(field=>!field)||new Set(fields.map(field=>field.name)).size!==fields.length)return null
 return {label:match[1].trim(),fields}
}

function metricRows(items){
 return (items??[]).map((item,index)=>{
  const structured=structuredRow(item)
  if(structured){
   const pairs=[],notes=[]
   for(const field of structured.fields){
    const measured=field.value.match(/^([-+−]?\d[\d,]*(?:\.\d+)?)\s*(%|个百分点|倍|万元|亿元|毫秒|分钟|小时|秒|元|ms|人|个|条)?$/)
    if(measured)pairs.push({name:field.name,value:Number(measured[1].replaceAll(',','').replace('−','-')),unit:measured[2]??''})
    else notes.push(`${field.name}：${field.value}`)
   }
   return {label:structured.label,pairs,detail:notes.join('；')}
  }
  const pairs=namedMetrics(item)
  const label=pairs.length?String(item).slice(0,pairs[0].index).replace(/^(?:其中|同时|此外)\s*/,'').replace(/[：:，,、\s]+$/g,'').trim():''
  let detail=pairs.length?String(item).slice(pairs[0].index):''
  for(const pair of pairs)detail=detail.replace(pair.raw,'')
  detail=detail.replace(/[，,；;。\s]+/g,' ').trim()
  // Approximation belongs to the evidence, even when the parser understood the value.
  if(pairs.some(pair=>/约/.test(pair.raw)))detail=[detail,'数值为近似值'].filter(Boolean).join('；')
  return {label:label||(!pairs.length?String(item):`对象 ${index+1}`),pairs,detail}
 })
}

export function metricDataset(items){
 const rows=metricRows(items)
 if(rows.length<2||rows.some(row=>!row.pairs.length||row.detail))return null
 const names=[...new Set(rows.flatMap(row=>row.pairs.map(pair=>pair.name)))]
 // Partial rows stay in a table. Filtering them out would silently change the evidence.
 if(rows.some(row=>names.some(name=>row.pairs.filter(pair=>pair.name===name).length!==1)))return null
 const units=new Set(rows.flatMap(row=>row.pairs.map(pair=>pair.unit)))
 if(units.size!==1)return null
 const unit=[...units][0]
 const series=names.map(name=>({name,labels:rows.map(row=>row.label),values:rows.map(row=>row.pairs.find(pair=>pair.name===name).value)}))
 const values=series.flatMap(item=>item.values),min=Math.min(0,...values),max=Math.max(0,...values)
 return {series,unit,isPercent:unit==='%',isRatio:!unit&&values.every(value=>value>=0&&value<=1),
  axisMin:min,axisMax:unit==='%'&&max<=100?100:max||1}
}

export function namedMetricTable(items){
 // Multi-clause transitions need their full sentence to retain the relationships.
 if((items??[]).some(item=>/→|->|➡|(?:从|由)\s*[-+−]?\d/.test(String(item))))return null
 const structured=(items??[]).map(structuredRow)
 if(structured.length>=2&&structured.every(Boolean)){
  const names=[...new Set(structured.flatMap(row=>row.fields.map(field=>field.name)))]
  return {headers:['方法 / 对象',...names],rows:structured.map(row=>[row.label,...names.map(name=>row.fields.find(field=>field.name===name)?.value??'未提供')])}
 }
 const rows=metricRows(items)
 if(rows.length<2||!rows.some(row=>row.pairs.length))return null
 const columns=[]
 for(const row of rows)for(const pair of row.pairs){
  if(!columns.some(col=>col.name===pair.name&&col.unit===pair.unit))columns.push({name:pair.name,unit:pair.unit})
 }
 const hasDetail=rows.some(row=>row.detail)
 return {
  headers:['方法 / 对象',...columns.map(col=>`${col.name}${col.unit?` (${col.unit})`:''}`),...(hasDetail?['说明']:[])],
  rows:rows.map(row=>[row.label,...columns.map(col=>{
   const matches=row.pairs.filter(pair=>pair.name===col.name&&pair.unit===col.unit)
   return matches.length===1?matches[0].value:matches.length===0?'—':matches.map(pair=>pair.value).join(' / ')
  }),...(hasDetail?[row.detail||'—']:[])]),
 }
}

export function transitionDataset(items){
 const rows=(items??[]).map(item=>{
  const match=String(item).trim().match(/^(.+?)\s*(?:从|由|\s)\s*([-+−]?\d+(?:\.\d+)?)\s*(%|秒|分钟|ms|万元|元)?\s*(?:(?:提升|提高|增长|下降|变化)?(?:至|到|为)|→|->|➡)\s*([-+−]?\d+(?:\.\d+)?)\s*(%|秒|分钟|ms|万元|元)?[。.]?$/)
  if(!match||match[3]!==match[5])return null
  return {label:match[1].trim(),before:Number(match[2].replace('−','-')),after:Number(match[4].replace('−','-')),unit:match[3]??''}
 })
 if(!rows.length||rows.some(row=>!row)||new Set(rows.map(row=>row.unit)).size!==1)return null
 const unit=rows[0].unit,values=rows.flatMap(row=>[row.before,row.after]),max=Math.max(0,...values)
 return {series:[{name:'原值',labels:rows.map(row=>row.label),values:rows.map(row=>row.before)},
  {name:'现值',labels:rows.map(row=>row.label),values:rows.map(row=>row.after)}],unit,isPercent:unit==='%',
  isRatio:!unit&&values.every(value=>value>=0&&value<=1),axisMin:Math.min(0,...values),axisMax:unit==='%'&&max<=100?100:max||1}
}

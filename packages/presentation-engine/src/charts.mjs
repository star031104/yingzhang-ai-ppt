// Evidence charts shared by the HTML preview (inline SVG) and native PPTX.
// The model only contains values parsed from the slide evidence; derived
// geometry such as waterfall bases is computed, never invented.
import {transitionDataset,numericTableDataset,labelsAreOrdered,sourceDecimals} from './data.mjs'
import {escapeHtml} from './utils.mjs'

export const CHART_TYPES=['column','bar','line','area','doughnut','pie','scatter','combo','waterfall']
const ALIASES={groupedbar:'column','grouped-bar':'column',clustered:'column',vbar:'column',vertical:'column',
 horizontalbar:'bar','horizontal-bar':'bar',hbar:'bar',barh:'bar',donut:'doughnut',ring:'doughnut',
 'bar-line':'combo',barline:'combo',mixed:'combo',bubble:'scatter'}
const START=/期初|起始|起点|基数|基线|上年|去年|年初|上期|opening|start|baseline|begin/i
const END=/期末|合计|总计|本年|今年|年末|本期|closing|ending|end|total/i
export const DECREASE_COLOR='#C8553D'

export function normalizeChartType(value){
 const key=String(value??'').trim().toLowerCase().replace(/\s+/g,'')
 if(!key)return null
 const type=ALIASES[key]??key
 return CHART_TYPES.includes(type)?type:null
}

export function explicitChartType(spec){
 return normalizeChartType(spec?.chartType??spec?.visualIntent?.chartType??spec?.content?.chartType??spec?.layoutPlan?.chartType)
}

const weight=text=>[...String(text)].reduce((sum,char)=>sum+(/[⺀-￿]/.test(char)?1:.55),0)

function chartData(items){
 const transition=transitionDataset(items)
 if(transition)return {kind:'transition',labels:transition.series[0].labels,
  series:transition.series.map(series=>({name:series.name,values:series.values,unit:transition.unit}))}
 // A single structured row is a series only when its columns are time-ordered.
 const single=(items??[]).length===1?numericTableDataset(items,{minRows:1}):null
 const table=numericTableDataset(items)??(single&&single.columns.length>=3&&labelsAreOrdered(single.columns.map(column=>column.name))?single:null)
 if(!table)return null
 const units=new Set(table.columns.map(column=>column.unit))
 // Time-like column headers (第一年/2023年/Q1) describe the x axis: one series per row.
 if(units.size===1&&labelsAreOrdered(table.columns.map(column=>column.name)))return {kind:'rows-as-series',
  labels:table.columns.map(column=>column.name),unit:[...units][0],
  series:table.labels.map((label,row)=>({name:label,values:table.columns.map(column=>column.values[row]),unit:[...units][0]}))}
 return {kind:'table',labels:table.labels,series:table.columns.map(column=>({name:column.name,values:column.values,unit:column.unit}))}
}

function isWaterfall(labels,values,decimals){
 if(labels.length<3||!START.test(labels[0])||!END.test(labels.at(-1)))return false
 if(labels.slice(1,-1).some(label=>START.test(label)||END.test(label)))return false
 const expected=values.slice(0,-1).reduce((sum,value)=>sum+value,0),actual=values.at(-1)
 return Math.abs(expected-actual)<=Math.max(Math.abs(actual)*.005,10**-decimals/2+1e-9)
}

function isShare(series,labels){
 if(series.length!==1||series[0].unit!=='%'||labels.length<2||labels.length>8)return false
 const values=series[0].values,sum=values.reduce((total,value)=>total+value,0)
 return values.every(value=>value>=0)&&Math.abs(sum-100)<=1.5
}

const longLabels=(labels,series)=>labels.length>6||Math.max(...labels.map(weight))>9||labels.length*series.length>14

function compatible(type,data){
 const {labels,series}=data,units=new Set(series.map(item=>item.unit))
 if(['line','area'].includes(type))return labels.length>=2&&units.size===1
 if(['doughnut','pie'].includes(type))return series.length===1&&labels.length>=2&&series[0].values.every(value=>value>=0)
 if(type==='scatter')return series.length===2&&labels.length>=3
 if(type==='combo')return series.length===2&&labels.length>=2
 if(type==='waterfall')return series.length===1&&labels.length>=3
 return units.size===1
}

export function selectChartType(data,{explicit=null,decimals=0}={}){
 if(explicit){
  if(compatible(explicit,data))return {type:explicit,reason:'explicit'}
 }
 const {labels,series,kind}=data,units=new Set(series.map(item=>item.unit)),ordered=labelsAreOrdered(labels)
 const categorical=()=>longLabels(labels,series)?'bar':'column'
 const fallback=explicit?`explicit-${explicit}-incompatible;`:''
 if(kind==='transition')return {type:categorical(),reason:`${fallback}before-after`}
 if(series.length===1){
  if(isWaterfall(labels,series[0].values,decimals))return {type:'waterfall',reason:`${fallback}increments`}
  if(isShare(series,labels))return {type:'doughnut',reason:`${fallback}shares-sum-100`}
  if(ordered)return {type:'line',reason:`${fallback}ordered-labels`}
  return {type:categorical(),reason:`${fallback}categories`}
 }
 if(units.size===1)return ordered?{type:'line',reason:`${fallback}ordered-labels`}:{type:categorical(),reason:`${fallback}categories`}
 if(series.length===2&&units.size===2){
  if(ordered)return {type:'combo',reason:`${fallback}ordered-mixed-units`}
  if(labels.length>=5)return {type:'scatter',reason:`${fallback}two-numeric-dimensions`}
 }
 return null
}

export function resolvePalette(designSystem={}){
 const palette=designSystem.palette??{},hex=value=>/^#[0-9a-f]{6}$/i.test(String(value??''))?String(value).toUpperCase():null
 const named={primary:hex(palette.primary)??'#625BF6',accent:hex(palette.accent)??'#78E3C5',deep:hex(palette.deep)??'#20284D',
  ink:hex(palette.ink)??'#182033',line:hex(palette.line)??'#E3E7F0',bg:hex(palette.bg)??'#F6F7FB',muted:'#68758B'}
 const style=designSystem.grammar?.chartStyle??designSystem.chartStyle??{}
 const order=Array.isArray(style.palette)&&style.palette.length?style.palette:['primary','accent','deep','muted']
 const series=order.map(key=>named[key]??hex(key)).filter(Boolean)
 return {...named,series:series.length?series:[named.primary,named.accent,named.deep,named.muted],
  gridlines:['none','horizontal','both'].includes(style.gridlines)?style.gridlines:'horizontal',
  dataLabels:style.dataLabels!==false,barRadius:Number.isFinite(Number(style.barRadius))?Number(style.barRadius):2,
  decrease:hex(style.decrease)??DECREASE_COLOR}
}

export function chartModel(spec,items=spec?.content?.bullets??[]){
 const data=chartData(items)
 if(!data)return null
 const decimals=sourceDecimals(items),explicit=explicitChartType(spec)
 const selected=selectChartType(data,{explicit,decimals})
 if(!selected)return null
 const palette=resolvePalette(spec?.designSystem)
 const units=[...new Set(data.series.map(item=>item.unit))]
 const model={version:'chart-v1',type:selected.type,reason:selected.reason,requested:explicit,labels:data.labels,
  series:data.series.map((series,index)=>({...series,axis:selected.type==='combo'&&index===1?'secondary':'primary'})),
  unit:units.length===1?units[0]:null,decimals,colors:palette.series,decrease:palette.decrease,deep:palette.deep,
  ink:palette.ink,muted:'#667085',line:palette.line,gridlines:palette.gridlines,dataLabels:palette.dataLabels,barRadius:palette.barRadius,
  font:String(spec?.designSystem?.typography?.fontFamily??'Microsoft YaHei')}
 if(model.type==='waterfall')model.steps=waterfallSteps(model)
 return model
}

export function waterfallSteps(model){
 const values=model.series[0].values,steps=[]
 let running=0
 values.forEach((value,index)=>{
  const total=index===0||index===values.length-1
  if(total){steps.push({label:model.labels[index],kind:'total',start:0,end:value,value});running=value;return}
  steps.push({label:model.labels[index],kind:value>=0?'increase':'decrease',start:running,end:running+value,value})
  running+=value
 })
 return steps
}

export function formatValue(value,model,unit=model.unit??''){
 const fixed=Number(value).toFixed(model.decimals)
 return `${fixed}${unit??''}`
}

export function niceScale(minValue,maxValue,count=5){
 let min=Math.min(0,minValue),max=Math.max(0,maxValue)
 if(min===max)max=min+1
 const raw=(max-min)/count,power=10**Math.floor(Math.log10(raw)),fraction=raw/power
 const step=(fraction<=1?1:fraction<=2?2:fraction<=2.5?2.5:fraction<=5?5:10)*power
 min=Math.floor(min/step+1e-9)*step;max=Math.ceil(max/step-1e-9)*step
 const ticks=[];for(let value=min;value<=max+step/2;value+=step)ticks.push(Math.round(value/step)*step)
 return {min,max,step,ticks}
}

// ---------------------------------------------------------------- SVG preview
// Every renderer records its plot rectangle (model.plot, fractions of the SVG)
// so the native chart can use the same manual plot layout in PowerPoint.
const fontStack=font=>`${/[\s,]/.test(font)&&!/["']/.test(font)?`'${font}'`:font}, 'PingFang SC', Arial, sans-serif`
const text=(x,y,value,{size=15,anchor='middle',fill='#182033',weight=500,font,transform=''}={})=>
 `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="${anchor}" font-size="${size}" font-weight="${weight}" fill="${fill}" font-family="${escapeHtml(fontStack(font))}"${transform?` transform="${transform}"`:''}>${escapeHtml(value)}</text>`
function wrap(label,width,size){
 const words=/[⺀-￿]/.test(label)?[...String(label)]:String(label).split(/(\s+)/)
 const lines=[''],limit=width/size
 for(const word of words){
  const next=lines.at(-1)+word
  if(weight(next)>limit&&lines.at(-1).trim())lines.push(word.trimStart())
  else lines[lines.length-1]=next
 }
 return lines.map(line=>line.trim()).filter(Boolean)
}
const multiline=(x,y,label,width,options)=>wrap(label,width,options.size).map((line,index)=>text(x,y+index*(options.size*1.25),line,options)).join('')
const tickLabel=(value,scale,model,unit)=>formatValue(value,{decimals:Number.isInteger(scale.step)?0:Math.max(model.decimals,1)},unit??'')
const SIZES={category:15,value:14,tick:12,legend:14}

function legend(model,W,entries,font){
 const widths=entries.map(([name])=>18+weight(name)*SIZES.legend),total=widths.reduce((sum,value)=>sum+value,0)+(entries.length-1)*24
 let cursor=(W-total)/2
 return entries.map(([name,color],index)=>{
  const item=`<rect x="${cursor.toFixed(1)}" y="7" width="12" height="12" rx="2" fill="${color}"/>${text(cursor+18,18,name,{size:SIZES.legend,anchor:'start',fill:model.ink,font})}`
  cursor+=widths[index]+24
  return item
 }).join('')
}
const seriesLegend=(model,W)=>model.series.length>1?legend(model,W,model.series.map((item,index)=>[item.name,model.colors[index%model.colors.length]]),model.font):''
const setPlot=(model,W,H,left,top,right,bottom,extra={})=>{model.plot={x:left/W,y:top/H,w:(right-left)/W,h:(bottom-top)/H,...extra};model.viewBox={w:W,h:H}}
const gridY=(model,scale,yOf,left,right,unit,anchorLeft=true)=>model.gridlines==='none'?'':scale.ticks.map(tick=>
 `<line x1="${left}" x2="${right}" y1="${yOf(tick).toFixed(1)}" y2="${yOf(tick).toFixed(1)}" stroke="${model.line}" stroke-width="1"/>`+
 (anchorLeft?text(left-10,yOf(tick)+4,tickLabel(tick,scale,model,unit),{size:SIZES.tick,anchor:'end',fill:model.muted,font:model.font}):'')).join('')
const values=model=>model.series.flatMap(item=>item.values)

function columnSvg(model,W,H){
 const {series,labels,font}=model,scale=niceScale(Math.min(...values(model)),Math.max(...values(model)))
 const top=(series.length>1?34:0)+24,left=model.gridlines!=='none'?62:14,right=W-14
 const groupW=(right-left)/labels.length,lines=Math.max(...labels.map(label=>wrap(label,groupW-12,SIZES.category).length))
 const bottom=H-12-lines*SIZES.category*1.25
 const yOf=value=>bottom-(value-scale.min)/(scale.max-scale.min)*(bottom-top)
 const barW=Math.min(72,groupW*.68/series.length)
 setPlot(model,W,H,left,top,right,bottom,{gap:Math.round(Math.max(0,Math.min(500,(groupW-barW*series.length)/barW*100))),scale})
 const parts=[seriesLegend(model,W),gridY(model,scale,yOf,left,right,model.unit)]
 labels.forEach((label,column)=>{
  const center=left+groupW*column+groupW/2
  series.forEach((item,index)=>{
   const value=item.values[column],x=center-barW*series.length/2+index*barW,y0=yOf(Math.max(0,value)),y1=yOf(Math.min(0,value))
   parts.push(`<rect x="${x.toFixed(1)}" y="${y0.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(1,y1-y0).toFixed(1)}" rx="${model.barRadius}" fill="${model.colors[index%model.colors.length]}"/>`)
   if(model.dataLabels)parts.push(text(x+barW/2,value>=0?y0-7:y1+17,formatValue(value,model,item.unit),{size:SIZES.value,fill:model.ink,weight:700,font}))
  })
  parts.push(multiline(center,bottom+SIZES.category+6,label,groupW-12,{size:SIZES.category,fill:model.ink,weight:600,font}))
 })
 parts.push(`<line class="dataset-zero" x1="${left}" x2="${right}" y1="${yOf(0).toFixed(1)}" y2="${yOf(0).toFixed(1)}" stroke="${model.ink}" stroke-width="1"/>`)
 return parts.join('')
}

function barSvg(model,W,H){
 const {series,labels,font}=model,scale=niceScale(Math.min(...values(model)),Math.max(...values(model)))
 const labelWidth=Math.min(300,Math.max(...labels.map(label=>weight(label)*SIZES.category))+8)
 const top=(series.length>1?34:0)+4,left=labelWidth+20,right=W-96,bottom=H-(model.gridlines!=='none'?26:4)
 const rowH=(bottom-top)/labels.length,barH=Math.min(30,rowH*.7/series.length)
 const xOf=value=>left+(value-scale.min)/(scale.max-scale.min)*(right-left)
 setPlot(model,W,H,left,top,right,bottom,{gap:Math.round(Math.max(0,Math.min(500,(rowH-barH*series.length)/barH*100))),scale})
 const parts=[seriesLegend(model,W)]
 if(model.gridlines!=='none')scale.ticks.forEach(tick=>parts.push(`<line x1="${xOf(tick).toFixed(1)}" x2="${xOf(tick).toFixed(1)}" y1="${top}" y2="${bottom}" stroke="${model.line}" stroke-width="1"/>`,text(xOf(tick),bottom+18,tickLabel(tick,scale,model,model.unit),{size:SIZES.tick,fill:model.muted,font})))
 labels.forEach((label,row)=>{
  const center=top+rowH*row+rowH/2,wrapped=wrap(label,labelWidth,SIZES.category)
  parts.push(multiline(left-12,center+5-(wrapped.length-1)*SIZES.category*.62,label,labelWidth,{size:SIZES.category,anchor:'end',fill:model.ink,weight:600,font}))
  series.forEach((item,index)=>{
   const value=item.values[row],y=center-barH*series.length/2+index*barH,x0=xOf(Math.min(0,value)),x1=xOf(Math.max(0,value))
   parts.push(`<rect x="${x0.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(1,x1-x0).toFixed(1)}" height="${barH.toFixed(1)}" rx="${model.barRadius}" fill="${model.colors[index%model.colors.length]}"/>`)
   if(model.dataLabels)parts.push(text(value>=0?x1+8:x0-8,y+barH/2+5,formatValue(value,model,item.unit),{size:SIZES.value,anchor:value>=0?'start':'end',fill:model.ink,weight:700,font}))
  })
 })
 parts.push(`<line class="dataset-zero" x1="${xOf(0).toFixed(1)}" x2="${xOf(0).toFixed(1)}" y1="${top}" y2="${bottom}" stroke="${model.ink}" stroke-width="1"/>`)
 return parts.join('')
}

function trendSvg(model,W,H){
 const font=model.font,combo=model.type==='combo',area=model.type==='area'
 const primary=combo?[model.series[0]]:model.series,secondary=combo?model.series[1]:null
 const scaleA=niceScale(Math.min(...primary.flatMap(item=>item.values)),Math.max(...primary.flatMap(item=>item.values)))
 const scaleB=secondary?niceScale(Math.min(...secondary.values),Math.max(...secondary.values)):null
 const top=(model.series.length>1?34:0)+24,left=model.gridlines!=='none'?62:14,right=W-(scaleB?62:14)
 const step=(right-left)/model.labels.length,lines=Math.max(...model.labels.map(label=>wrap(label,step-8,SIZES.category).length))
 const bottom=H-12-lines*SIZES.category*1.25
 const yA=value=>bottom-(value-scaleA.min)/(scaleA.max-scaleA.min)*(bottom-top)
 const yB=value=>bottom-(value-scaleB.min)/(scaleB.max-scaleB.min)*(bottom-top)
 const xOf=index=>left+step*index+step/2,barW=Math.min(64,step*.56)
 setPlot(model,W,H,left,top,right,bottom,{gap:Math.round(Math.max(0,Math.min(500,(step-barW)/barW*100))),scale:scaleA,secondaryScale:scaleB})
 const parts=[seriesLegend(model,W),gridY(model,scaleA,yA,left,right,primary[0].unit)]
 if(scaleB)scaleB.ticks.forEach(tick=>parts.push(text(right+10,yB(tick)+4,tickLabel(tick,scaleB,model,secondary.unit),{size:SIZES.tick,anchor:'start',fill:model.muted,font})))
 if(combo)model.series[0].values.forEach((value,index)=>{
  const y0=yA(Math.max(0,value)),y1=yA(Math.min(0,value))
  parts.push(`<rect x="${(xOf(index)-barW/2).toFixed(1)}" y="${y0.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(1,y1-y0).toFixed(1)}" rx="${model.barRadius}" fill="${model.colors[0]}"/>`)
  if(model.dataLabels)parts.push(text(xOf(index),y0-7,formatValue(value,model,model.series[0].unit),{size:SIZES.value-1,fill:model.ink,weight:700,font}))
 })
 parts.push(`<line class="dataset-zero" x1="${left}" x2="${right}" y1="${yA(Math.max(scaleA.min,0)).toFixed(1)}" y2="${yA(Math.max(scaleA.min,0)).toFixed(1)}" stroke="${model.ink}" stroke-width="1"/>`)
 const drawn=combo?[[secondary,yB,1]]:model.series.map((item,index)=>[item,yA,index])
 for(const [item,yOf,index] of drawn){
  const color=model.colors[index%model.colors.length],points=item.values.map((value,i)=>[xOf(i),yOf(value)])
  const path=points.map(point=>point.map(n=>n.toFixed(1)).join(' ')).join('L')
  if(area)parts.push(`<path d="M${path}L${points.at(-1)[0].toFixed(1)} ${yOf(Math.max(0,scaleA.min)).toFixed(1)}L${points[0][0].toFixed(1)} ${yOf(Math.max(0,scaleA.min)).toFixed(1)}Z" fill="${color}" fill-opacity="0.35" stroke="none"/>`)
  parts.push(`<path d="M${path}" fill="none" stroke="${color}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>`)
  points.forEach(([x,y],i)=>{
   if(!area)parts.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="${color}"/>`)
   if(model.dataLabels&&model.labels.length<=12)parts.push(text(x,y-11,formatValue(item.values[i],model,item.unit),{size:SIZES.value-1,fill:model.ink,weight:700,font}))
  })
 }
 model.labels.forEach((label,index)=>parts.push(multiline(xOf(index),bottom+SIZES.category+6,label,step-8,{size:SIZES.category,fill:model.ink,weight:600,font})))
 return parts.join('')
}

function shareSvg(model,W,H){
 const font=model.font,data=model.series[0].values,total=data.reduce((sum,value)=>sum+value,0)||1
 const radius=Math.min(H/2-8,W*.18),cx=radius+40,cy=H/2,inner=model.type==='doughnut'?radius*.5:0,parts=[]
 setPlot(model,W,H,cx-radius,cy-radius,cx+radius,cy+radius)
 let angle=-Math.PI/2
 const point=(r,a)=>`${(cx+r*Math.cos(a)).toFixed(2)} ${(cy+r*Math.sin(a)).toFixed(2)}`
 data.forEach((value,index)=>{
  const sweep=value/total*Math.PI*2,end=angle+sweep,large=sweep>Math.PI?1:0,color=model.colors[index%model.colors.length]
  const d=data.length===1?`M${point(radius,angle)}A${radius} ${radius} 0 1 1 ${point(radius,angle+Math.PI*1.999)}Z`
   :inner?`M${point(radius,angle)}A${radius} ${radius} 0 ${large} 1 ${point(radius,end)}L${point(inner,end)}A${inner} ${inner} 0 ${large} 0 ${point(inner,angle)}Z`
   :`M${cx} ${cy}L${point(radius,angle)}A${radius} ${radius} 0 ${large} 1 ${point(radius,end)}Z`
  parts.push(`<path d="${d}" fill="${color}" stroke="#FFFFFF" stroke-width="2"/>`)
  if(value/total>=.06){
   const mid=angle+sweep/2,r=inner?(radius+inner)/2:radius*.62
   parts.push(text(cx+r*Math.cos(mid),cy+r*Math.sin(mid)+5,formatValue(value,model,model.series[0].unit),{size:SIZES.value,fill:'#FFFFFF',weight:700,font}))
  }
  angle=end
 })
 const listX=cx+radius+72,rowH=Math.min(54,(H-20)/data.length),startY=cy-rowH*data.length/2+rowH/2
 data.forEach((value,index)=>{
  const y=startY+index*rowH,color=model.colors[index%model.colors.length]
  parts.push(`<rect x="${listX}" y="${(y-8).toFixed(1)}" width="14" height="14" rx="3" fill="${color}"/>`,
   text(listX+26,y+5,model.labels[index],{size:16,anchor:'start',fill:model.ink,weight:600,font}),
   text(W-12,y+5,formatValue(value,model,model.series[0].unit),{size:18,anchor:'end',fill:model.ink,weight:800,font}))
 })
 return parts.join('')
}

function scatterSvg(model,W,H){
 const font=model.font,[xs,ys]=model.series,parts=[]
 const sx=niceScale(Math.min(...xs.values),Math.max(...xs.values)),sy=niceScale(Math.min(...ys.values),Math.max(...ys.values))
 const left=86,right=W-24,top=14,bottom=H-56
 const xOf=value=>left+(value-sx.min)/(sx.max-sx.min)*(right-left),yOf=value=>bottom-(value-sy.min)/(sy.max-sy.min)*(bottom-top)
 setPlot(model,W,H,left,top,right,bottom,{scale:sy,xScale:sx})
 sy.ticks.forEach(tick=>parts.push(`<line x1="${left}" x2="${right}" y1="${yOf(tick).toFixed(1)}" y2="${yOf(tick).toFixed(1)}" stroke="${model.line}" stroke-width="1"/>`,text(left-10,yOf(tick)+4,tickLabel(tick,sy,model,ys.unit),{size:SIZES.tick,anchor:'end',fill:model.muted,font})))
 sx.ticks.forEach(tick=>parts.push(text(xOf(tick),bottom+19,tickLabel(tick,sx,model,xs.unit),{size:SIZES.tick,fill:model.muted,font})))
 parts.push(`<line class="dataset-zero" x1="${left}" x2="${right}" y1="${bottom}" y2="${bottom}" stroke="${model.ink}" stroke-width="1"/>`)
 parts.push(text((left+right)/2,H-8,`${xs.name}${xs.unit?`（${xs.unit}）`:''}`,{size:13,fill:model.ink,weight:600,font}),
  text(22,(top+bottom)/2,`${ys.name}${ys.unit?`（${ys.unit}）`:''}`,{size:13,fill:model.ink,weight:600,font,transform:`rotate(-90 22 ${((top+bottom)/2).toFixed(1)})`}))
 model.labels.forEach((label,index)=>{
  const x=xOf(xs.values[index]),y=yOf(ys.values[index])
  parts.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="6" fill="${model.colors[0]}"/>`,text(x+11,y+5,label,{size:13,anchor:'start',fill:model.ink,weight:600,font}))
 })
 return parts.join('')
}

function waterfallSvg(model,W,H){
 const font=model.font,steps=model.steps,parts=[]
 const scale=niceScale(Math.min(...steps.flatMap(step=>[step.start,step.end])),Math.max(...steps.flatMap(step=>[step.start,step.end])))
 const top=20,left=model.gridlines!=='none'?62:14,right=W-14,groupW=(right-left)/steps.length
 const lines=Math.max(...steps.map(step=>wrap(step.label,groupW-12,SIZES.category).length)),bottom=H-12-lines*SIZES.category*1.25
 const yOf=value=>bottom-(value-scale.min)/(scale.max-scale.min)*(bottom-top)
 const barW=Math.min(76,groupW*.62)
 setPlot(model,W,H,left,top,right,bottom,{gap:Math.round(Math.max(0,Math.min(500,(groupW-barW)/barW*100))),scale})
 parts.push(gridY(model,scale,yOf,left,right,model.unit))
 steps.forEach((step,index)=>{
  const center=left+groupW*index+groupW/2,y0=yOf(Math.max(step.start,step.end)),y1=yOf(Math.min(step.start,step.end))
  const color=step.kind==='total'?model.deep:step.kind==='increase'?model.colors[0]:model.decrease
  parts.push(`<rect x="${(center-barW/2).toFixed(1)}" y="${y0.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(1,y1-y0).toFixed(1)}" rx="${model.barRadius}" fill="${color}"/>`)
  if(index<steps.length-1)parts.push(`<line x1="${(center+barW/2).toFixed(1)}" x2="${(center+groupW-barW/2).toFixed(1)}" y1="${yOf(step.end).toFixed(1)}" y2="${yOf(step.end).toFixed(1)}" stroke="${model.muted}" stroke-width="1" stroke-dasharray="4 3"/>`)
  const label=step.kind==='total'?formatValue(step.value,model):`${step.value>=0?'+':''}${formatValue(step.value,model)}`
  // Labels sit inside tall bars and above short ones, as PowerPoint centres them.
  const inside=y1-y0>=SIZES.value+8
  parts.push(text(center,inside?(y0+y1)/2+5:y0-7,label,{size:SIZES.value,fill:inside?'#FFFFFF':model.ink,weight:700,font}))
  parts.push(multiline(center,bottom+SIZES.category+6,step.label,groupW-12,{size:SIZES.category,fill:model.ink,weight:600,font}))
 })
 parts.push(`<line class="dataset-zero" x1="${left}" x2="${right}" y1="${yOf(0).toFixed(1)}" y2="${yOf(0).toFixed(1)}" stroke="${model.ink}" stroke-width="1"/>`)
 return parts.join('')
}

export function chartSvg(model,{width=1144,height=330}={}){
 const renderer={column:columnSvg,bar:barSvg,line:trendSvg,area:trendSvg,combo:trendSvg,doughnut:shareSvg,pie:shareSvg,scatter:scatterSvg,waterfall:waterfallSvg}[model.type]??columnSvg
 const body=renderer(model,width,height)
 const label=`${model.series.map(item=>item.name).join('、')}：${model.labels.join('、')}`
 return `<svg class="evidence-chart" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="${escapeHtml(label)}" xmlns="http://www.w3.org/2000/svg">${body}</svg>`
}

// ----------------------------------------------------------------- native PPTX
const hex=value=>String(value??'').replace(/^#/,'').toUpperCase()
export const WATERFALL_BASE='辅助基线'

function formatCode(model,unit=model.unit??''){
 const number=model.decimals?`0.${'0'.repeat(model.decimals)}`:'0'
 const suffix=unit?`"${unit.replace(/"/g,'')}"`:''
 return `${number}${suffix}`
}
const axisCode=(scale,model,unit)=>formatCode({decimals:scale&&!Number.isInteger(scale.step)?Math.max(1,model.decimals):0},unit)

// box: inches on the slide; scale: rendered SVG px per SVG unit (text sizing).
export function nativeChartSpec(model,box,ChartType){
 const font=model.font,colors=model.colors.map(hex),labels=model.labels
 const k=(box.w*96)/(model.viewBox?.w??1144),pt=px=>Math.round(px*k*.75*10)/10
 const plot=model.plot,layout=plot?{x:plot.x,y:plot.y,w:plot.w,h:plot.h}:undefined
 const range=scale=>scale?{valAxisMinVal:scale.min,valAxisMaxVal:scale.max,valAxisMajorUnit:scale.step}:{}
 const common={x:box.x,y:box.y,w:box.w,h:box.h,showTitle:false,showBorder:false,layout,
  catAxisLabelFontFace:font,catAxisLabelFontSize:pt(SIZES.category),catAxisLabelColor:hex(model.ink),catAxisLabelFontBold:true,
  valAxisLabelFontFace:font,valAxisLabelFontSize:pt(SIZES.tick),valAxisLabelColor:hex(model.muted),
  valGridLine:model.gridlines==='none'?{style:'none'}:{color:hex(model.line),size:.75},catGridLine:{style:'none'},
  valAxisHidden:model.gridlines==='none',valAxisLineShow:false,catAxisLineShow:true,catAxisLineColor:hex(model.ink),
  legendFontFace:font,legendFontSize:pt(SIZES.legend),legendColor:hex(model.ink),
  dataLabelFontFace:font,dataLabelFontSize:pt(SIZES.value),dataLabelColor:hex(model.ink),dataLabelFontBold:true,
  showValue:model.dataLabels,dataLabelFormatCode:formatCode(model),valAxisLabelFormatCode:axisCode(plot?.scale,model,model.unit)}
 const series=model.series.map(item=>({name:item.name,labels,values:item.values}))
 if(model.type==='column'||model.type==='bar'){
  return {type:ChartType.bar,data:series,options:{...common,barDir:model.type==='bar'?'bar':'col',barGrouping:'clustered',
   ...(model.type==='bar'?{catAxisOrientation:'maxMin',valAxisLabelPos:'high'}:{}),chartColors:series.length===1?[colors[0]]:colors,
   showLegend:series.length>1,legendPos:'t',dataLabelPosition:'outEnd',barGapWidthPct:plot?.gap??80,...range(plot?.scale)}}
 }
 if(model.type==='line'||model.type==='area'){
  return {type:model.type==='area'?ChartType.area:ChartType.line,data:series,options:{...common,chartColors:series.length===1?[colors[0]]:colors,
   lineSize:2.25,lineDataSymbol:model.type==='area'?'none':'circle',lineDataSymbolSize:7,showLegend:series.length>1,legendPos:'t',
   dataLabelPosition:model.type==='area'?undefined:'t',...(model.type==='area'?{chartColorsOpacity:35}:{}),...range(plot?.scale)}}
 }
 if(model.type==='doughnut'||model.type==='pie'){
  return {type:model.type==='pie'?ChartType.pie:ChartType.doughnut,data:series,options:{...common,chartColors:colors,
   holeSize:50,showLegend:true,legendPos:'r',legendFontSize:pt(16),dataLabelColor:'FFFFFF',showPercent:false,showValue:true,
   firstSliceAng:0}}
 }
 if(model.type==='scatter'){
  const [xs,ys]=model.series
  return {type:ChartType.scatter,data:[{name:xs.name,values:xs.values},{name:ys.name,values:ys.values,labels}],options:{...common,
   chartColors:[colors[0]],lineSize:0,lineDataSymbol:'circle',lineDataSymbolSize:9,showLegend:false,
   showValue:false,showLabel:true,dataLabelFormatScatter:'custom',dataLabelPosition:'r',dataLabelFontBold:true,dataLabelFontSize:pt(13),
   showValAxisTitle:true,valAxisTitle:`${ys.name}${ys.unit?`（${ys.unit}）`:''}`,valAxisTitleFontSize:pt(13),valAxisTitleColor:hex(model.ink),
   showCatAxisTitle:true,catAxisTitle:`${xs.name}${xs.unit?`（${xs.unit}）`:''}`,catAxisTitleFontSize:pt(13),catAxisTitleColor:hex(model.ink),
   valAxisLabelFormatCode:axisCode(plot?.scale,model,ys.unit),valGridLine:{color:hex(model.line),size:.75},valAxisHidden:false,...range(plot?.scale),
   catAxisLabelFontBold:false,catAxisLabelFontSize:pt(SIZES.tick),catAxisLabelColor:hex(model.muted)},
   axisPatches:{b:{formatCode:axisCode(plot?.xScale,model,xs.unit),scale:plot?.xScale,bold:false}}}
 }
 if(model.type==='combo'){
  const [bars,line]=model.series
  return {type:'combo',data:[
   {type:ChartType.bar,data:[{name:bars.name,labels,values:bars.values}],options:{barDir:'col',chartColors:[colors[0]],barGapWidthPct:plot?.gap??90,
    showValue:model.dataLabels,dataLabelPosition:'outEnd',dataLabelFormatCode:formatCode(model,bars.unit)}},
   {type:ChartType.line,data:[{name:line.name,labels,values:line.values}],options:{chartColors:[colors[1]],lineSize:2.25,lineDataSymbol:'circle',lineDataSymbolSize:7,
    secondaryValAxis:true,secondaryCatAxis:true,showValue:model.dataLabels,dataLabelPosition:'t',dataLabelFormatCode:formatCode(model,line.unit)}},
  ],options:{...common,showLegend:true,legendPos:'t',
   valAxes:[{showValAxisTitle:false,valAxisLabelFormatCode:axisCode(plot?.scale,model,bars.unit),valGridLine:common.valGridLine,...range(plot?.scale)},
    {showValAxisTitle:false,valAxisLabelFormatCode:axisCode(plot?.secondaryScale,model,line.unit),valGridLine:{style:'none'},...range(plot?.secondaryScale)}],
   catAxes:[{catAxisTitle:''},{catAxisHidden:true}]}}
 }
 // Waterfall: stacked columns with an invisible base series. The base values
 // are running totals derived from the evidence values, never new facts.
 const steps=model.steps??waterfallSteps(model)
 const base=steps.map(step=>step.kind==='total'?0:Math.min(step.start,step.end))
 const pick=kind=>steps.map(step=>step.kind===kind?(kind==='total'?step.value:Math.abs(step.value)):0)
 const code=formatCode(model)
 return {type:ChartType.bar,data:[{name:WATERFALL_BASE,labels,values:base},{name:'总量',labels,values:pick('total')},
  {name:'增加',labels,values:pick('increase')},{name:'减少',labels,values:pick('decrease')}],
  options:{...common,barDir:'col',barGrouping:'stacked',chartColors:['FFFFFF',hex(model.deep),colors[0],hex(model.decrease)],
   showLegend:false,barGapWidthPct:plot?.gap??60,barOverlapPct:100,dataLabelPosition:'ctr',dataLabelColor:'FFFFFF',
   dataLabelFormatCode:`${code};-${code};;`,...range(plot?.scale)},
  seriesPatches:{[WATERFALL_BASE]:{noFill:true,hideLabels:true},'增加':{formatCode:`+${code};-${code};;`},'减少':{formatCode:`-${code};-${code};;`}}}
}

export function addNativeChart(slide,model,box,ChartType){
 const spec=nativeChartSpec(model,box,ChartType)
 const options=Object.fromEntries(Object.entries(spec.options).filter(([,value])=>value!==undefined))
 if(spec.type==='combo')slide.addChart(spec.data,options)
 else slide.addChart(spec.type,spec.data,options)
 return spec.seriesPatches||spec.axisPatches?{series:spec.seriesPatches??{},axes:spec.axisPatches??{}}:null
}

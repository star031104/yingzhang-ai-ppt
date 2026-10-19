// Scene-driven PPTX compiler.
//
// The HTML candidate is measured in Chromium (scene-export.mjs). This module
// turns that measured export layer into native PowerPoint objects with the same
// geometry: 1280 CSS px = 13.333 in, so 1 px = 1/96 in and 1 px font = 0.75 pt.
// Planning is pure (testable); applying the plan touches PptxGenJS only.
import {normalizedText,cleanText} from './content.mjs'
import {parsePath,transformSubpaths,pathBounds} from './svg-path.mjs'
import {addNativeChart} from './charts.mjs'
import {validateExportLayer} from '../../scene-schema/src/index.js'

export const SCENE_EXPORT_VERSION='scene-export-v1'
const IN=1/96,PT=.75
const r3=value=>Math.round(value*1000)/1000
const inch=value=>r3(value*IN)

const hex=color=>[color.r,color.g,color.b].map(value=>Math.max(0,Math.min(255,Math.round(value))).toString(16).padStart(2,'0')).join('').toUpperCase()
const transparency=(color,opacity=1)=>Math.max(0,Math.min(100,Math.round((1-(color?.a??1)*opacity)*100)))

const GENERIC=new Set(['serif','sans-serif','monospace','system-ui','cursive','fantasy','ui-sans-serif','ui-serif','-apple-system'])
// Office-safe faces. Web-only CJK families map to fonts installed with Office.
const FONT_MAP={'noto serif sc':'SimSun','noto serif cjk sc':'SimSun','songti sc':'SimSun','stsong':'SimSun','source han serif sc':'SimSun',
 'pingfang sc':'Microsoft YaHei','noto sans sc':'Microsoft YaHei','noto sans cjk sc':'Microsoft YaHei','source han sans sc':'Microsoft YaHei','hiragino sans gb':'Microsoft YaHei'}
export function officeFont(family,fallback='Microsoft YaHei'){
 const names=String(family??'').split(',').map(name=>name.trim().replace(/^["']|["']$/g,'')).filter(Boolean)
 const first=names.find(name=>!GENERIC.has(name.toLowerCase()))
 if(!first)return names.some(name=>name.toLowerCase()==='serif')?'SimSun':fallback
 return FONT_MAP[first.toLowerCase()]??first
}

export function pptxMode(env=process.env){
 const value=String(env.YINGZHANG_PPTX_MODE??env.SLIDEFORGE_PPTX_MODE??'scene').trim().toLowerCase()
 return value==='legacy'?'legacy':'scene'
}

// ------------------------------------------------------------- sanity check
const textOf=item=>item.kind==='text'?item.runs.map(run=>run.text).join('')
 :item.kind==='table'?item.rows.flatMap(row=>row.cells.map(cell=>cell.text)).join('')
 :item.kind==='chart'?[...(item.labels??[]),...(item.model?.labels??[])].join(''):''

export function sceneExportText(scene){
 return (scene?.exportLayer?.items??[]).map(textOf).join('\n')
}

// Returns the reasons a scene cannot drive the PPTX (empty array = usable).
export function sceneExportIssues(scene,spec){
 const layer=scene?.exportLayer,issues=[]
 if(!layer||layer.version!==SCENE_EXPORT_VERSION)return ['scene-export-missing']
 if(layer.error)return [`scene-export-error:${layer.error}`]
 if(!Array.isArray(layer.items)||!layer.items.length)return ['scene-export-empty']
 if(Math.abs((layer.canvas?.width??1280)-1280)>1||Math.abs((layer.canvas?.height??720)-720)>1)issues.push('scene-canvas-size')
 try{validateExportLayer(layer)}catch(error){issues.push(`scene-export-invalid:${error.message}`)}
 if(!layer.items.some(item=>item.kind==='text'))issues.push('scene-without-text')
 const exported=normalizedText(sceneExportText(scene))
 const visible=normalizedText(scene.visibleText??'')
 const structured=new Set(scene.structuredContent??[])
 const hasStructured=layer.items.some(item=>['chart','table'].includes(item.kind))
 const bullets=(spec?.content?.bullets??[]).map(cleanText)
 bullets.forEach((bullet,index)=>{
  const expected=normalizedText(bullet)
  if(!expected||!visible.includes(expected))return
  if(structured.has(index)&&hasStructured)return
  if(!exported.includes(expected))issues.push(`text-lost:${index}`)
 })
 // A text leaf is exported once: compare occurrence counts with the HTML.
 const count=(haystack,needle)=>needle?haystack.split(needle).length-1:0
 bullets.forEach((bullet,index)=>{
  const expected=normalizedText(bullet)
  if(expected.length>=6&&count(exported,expected)>Math.max(1,count(visible,expected)))issues.push(`text-duplicated:${index}`)
 })
 return issues
}

// ------------------------------------------------------------------ planning
function shapeKind(item){
 const [tl,tr,br,bl]=item.radius??[0,0,0,0],min=Math.min(item.w,item.h)
 const rounded=[tl,tr,br,bl].filter(value=>value>.5)
 if(rounded.length===4&&rounded.every(value=>value>=min/2-.6))return Math.abs(item.w-item.h)<1.5?{shape:'ellipse'}:{shape:'roundRect',radius:min/2}
 if(rounded.length>=3)return {shape:'roundRect',radius:Math.min(min/2,rounded.reduce((sum,value)=>sum+value,0)/rounded.length)}
 if(rounded.length===2){
  const pairs=[[tl,tr,0],[tr,br,90],[br,bl,180],[bl,tl,270]]
  const pair=pairs.find(([a,b])=>a>.5&&b>.5)
  if(pair)return {shape:'round2SameRect',radius:Math.min(min/2,(pair[0]+pair[1])/2),rotate:pair[2]}
 }
 return {shape:'rect'}
}

function gradientInfo(layer,item,opacity=1){
 const stops=layer.stops.filter(stop=>stop.color).map(stop=>({...stop,color:{...stop.color,a:stop.color.a*opacity}}))
 if(stops.length<2)return null
 const span=layer.type==='linear'?(()=>{
  const angle=((layer.angle%360)+360)%360*Math.PI/180
  return Math.abs(item.w*Math.sin(angle))+Math.abs(item.h*Math.cos(angle))
 })():Math.max(item.w,item.h)
 const positioned=stops.map((stop,index)=>({color:stop.color,pos:stop.position?(stop.position.unit==='%'?stop.position.value/100:stop.position.value/Math.max(1,span)):null,index}))
 positioned.forEach((stop,index)=>{if(stop.pos===null)stop.pos=index===0?0:index===positioned.length-1?1:null})
 for(let i=0;i<positioned.length;i++){
  if(positioned[i].pos!==null)continue
  let j=i;while(positioned[j].pos===null)j++
  const start=positioned[i-1].pos,end=positioned[j].pos
  for(let k=i;k<j;k++)positioned[k].pos=start+(end-start)*(k-i+1)/(j-i+1)
 }
 const clamped=positioned.map(stop=>({...stop,pos:Math.max(0,Math.min(1,stop.pos))}))
 const visible=clamped.filter(stop=>stop.color.a>.02)
 if(!visible.length)return null
 // Solid fallback: alpha-weighted average, used if gradient XML is unavailable.
 const totalAlpha=clamped.reduce((sum,stop)=>sum+stop.color.a,0)/clamped.length
 const average=['r','g','b'].reduce((acc,key)=>({...acc,[key]:visible.reduce((sum,stop)=>sum+stop.color[key]*stop.color.a,0)/visible.reduce((sum,stop)=>sum+stop.color.a,0)}),{})
 const ooxmlAngle=layer.type==='linear'?((layer.angle-90)%360+360)%360:0
 let focus=null
 const at=String(layer.shape??'').match(/at\s+(-?[\d.]+)%\s+(-?[\d.]+)%/)
 if(layer.type==='radial')focus=at?{x:Number(at[1])/100,y:Number(at[2])/100}:{x:.5,y:.5}
 return {type:layer.type==='radial'?'radial':'linear',angle:ooxmlAngle,focus,stops:clamped.map(stop=>({pos:stop.pos,color:hex(stop.color),alpha:stop.color.a})),
  fallback:{color:hex(average),transparency:Math.round((1-totalAlpha)*100)}}
}

function shadowOption(shadow,opacity){
 if(!shadow?.color||shadow.color.a*opacity<.02)return null
 const distance=Math.hypot(shadow.x,shadow.y)
 return {type:'outer',blur:r3(shadow.blur*PT),offset:r3(distance*PT),angle:Math.round((Math.atan2(shadow.y,shadow.x)*180/Math.PI+360)%360),
  color:hex(shadow.color),opacity:Math.round(shadow.color.a*opacity*100)/100}
}

function boxPlan(item,ops,context){
 const opacity=item.opacity??1
 if(item.root){
  if(item.fill)context.background={color:hex(item.fill)}
  for(const layer of [...(item.gradients??[])].reverse()){
   const gradient=gradientInfo(layer,item)
   if(gradient)ops.push({type:'shape',shape:'rect',x:0,y:0,w:inch(item.w),h:inch(item.h),fill:gradient.fallback,gradient,line:null,source:item})
  }
  return
 }
 const geometry=shapeKind(item)
 const borders=item.borders??[]
 const uniform=borders.length===4&&borders.every(side=>side.width===borders[0].width&&hex(side.color)===hex(borders[0].color)&&side.color.a===borders[0].color.a&&side.style===borders[0].style)
 const stroke=uniform?borders[0]:null
 const inset=stroke?stroke.width/2:0
 const frame={x:item.x+inset,y:item.y+inset,w:Math.max(.5,item.w-2*inset),h:Math.max(.5,item.h-2*inset)}
 const line=stroke?{color:hex(stroke.color),transparency:transparency(stroke.color,opacity),width:r3(stroke.width*PT),
  dashType:stroke.style==='dashed'?'dash':stroke.style==='dotted'?'sysDot':'solid'}:null
 const place=(target,extra={})=>{
  const out={type:'shape',shape:geometry.shape,x:inch(target.x),y:inch(target.y),w:inch(target.w),h:inch(target.h),...extra,source:item}
  if(geometry.radius)out.rectRadius=inch(Math.max(0,geometry.radius-inset))
  if(geometry.rotate){
   out.rotate=geometry.rotate
   if(geometry.rotate%180){
    const cx=target.x+target.w/2,cy=target.y+target.h/2
    Object.assign(out,{x:inch(cx-target.h/2),y:inch(cy-target.w/2),w:inch(target.h),h:inch(target.w)})
   }
  }
  return out
 }
 const shadow=shadowOption(item.shadow,opacity)
 if(item.fill||line||shadow){
  ops.push(place(frame,{fill:item.fill?{color:hex(item.fill),transparency:transparency(item.fill,opacity)}:null,line,shadow}))
 }
 for(const layer of [...(item.gradients??[])].reverse()){
  const gradient=gradientInfo(layer,item,opacity)
  // Gradients rotate with the shape; counter-rotate shapes that were turned
  // to place their rounded corners on the correct side.
  if(gradient&&geometry.rotate&&gradient.type==='linear')gradient.angle=((gradient.angle-geometry.rotate)%360+360)%360
  if(gradient)ops.push(place(frame,{fill:gradient.fallback,gradient,line:null}))
 }
 if(!uniform)for(const side of borders){
  const w=side.width,box=side.side==='top'?{x:item.x,y:item.y,w:item.w,h:w}:side.side==='bottom'?{x:item.x,y:item.y+item.h-w,w:item.w,h:w}
   :side.side==='left'?{x:item.x,y:item.y,w,h:item.h}:{x:item.x+item.w-w,y:item.y,w,h:item.h}
  ops.push({type:'shape',shape:'rect',x:inch(box.x),y:inch(box.y),w:inch(box.w),h:inch(box.h),
   fill:{color:hex(side.color),transparency:transparency(side.color,opacity)},line:null,source:item,border:side.side})
 }
}

// Text frames follow CSS line boxes. Chromium centres the glyph content area
// in each line box (half-leading above and below), while Office applies exact
// line spacing above the glyphs. The frame therefore starts one full leading
// above the measured glyph top, which lands every baseline where CSS put it.
export function textFrame(item){
 const lines=Math.max(1,item.lines||1)
 const lineHeight=item.lineHeight&&item.lineHeight>0?item.lineHeight:null
 const contentHeight=lineHeight&&lines>1?Math.max(item.fontSize,item.h-(lines-1)*lineHeight):item.h
 const L=lineHeight??contentHeight
 const top=item.y-(L-contentHeight)
 const container=item.container??{x:item.x,y:item.y,w:item.w,h:item.h}
 const slack=Math.max(2,item.fontSize*.12)
 let x,w
 if(item.align==='center'){
  const center=lines>1?container.x+container.w/2:item.x+item.w/2
  w=Math.max(container.w,item.w)+slack*2;x=center-w/2
 }else if(item.align==='right'){
  const right=Math.max(item.x+item.w,lines>1?container.x+container.w:item.x+item.w)
  w=Math.max(item.w,lines>1?container.w:item.w)+slack;x=right-w
 }else{
  x=item.x
  const right=lines>1?Math.max(container.x+container.w,item.x+item.w):Math.max(item.x+item.w,Math.min(container.x+container.w,item.x+item.w+Math.max(slack*4,item.w*.15)))
  w=right-x+slack
 }
 // A single line in a tight container must not re-wrap when Office metrics differ.
 const tight=lines===1&&container.x+container.w-(item.x+item.w)<item.fontSize*1.5&&item.align!=='center'
 return {x,y:top,w,h:L*lines,lineHeight:L,wrap:!tight}
}

function runOptions(run,item,context){
 const color=run.color??{r:0,g:0,b:0,a:1}
 const options={fontSize:Math.max(1,r3(run.fontSize*PT)),bold:run.fontWeight>=600,italic:Boolean(run.italic),
  color:hex(color),fontFace:officeFont(run.fontFamily,context.font)}
 const alpha=transparency(color,item.opacity??1)
 if(alpha)options.transparency=alpha
 if(Math.abs(run.letterSpacing??0)>.05)options.charSpacing=r3(run.letterSpacing*PT)
 if(run.underline)options.underline={style:'sng'}
 return options
}

function textPlan(item,ops,context){
 const runs=[]
 for(const run of item.runs){
  if(run.lineBreak){if(runs.length)runs.at(-1).options.breakLine=true;continue}
  if(!run.text)continue
  runs.push({text:run.text,options:runOptions(run,item,context)})
 }
 if(!runs.length)return
 const frame=textFrame(item)
 ops.push({type:'text',runs,x:inch(frame.x),y:inch(frame.y),w:inch(frame.w),h:inch(Math.max(frame.h,item.fontSize)),
  align:['center','right','justify'].includes(item.align)?(item.align==='justify'?'left':item.align):'left',
  lineSpacing:r3(frame.lineHeight*PT),wrap:frame.wrap,source:item,
  text:runs.map(run=>run.text).join('')})
}

function imageRect(item){
 const box={x:item.x,y:item.y,w:item.w,h:item.h},nw=item.naturalWidth,nh=item.naturalHeight
 let display=box
 if(nw>0&&nh>0&&['contain','cover','scale-down','none'].includes(item.fit)){
  const scale=item.fit==='cover'?Math.max(box.w/nw,box.h/nh):item.fit==='none'?1:Math.min(box.w/nw,box.h/nh,item.fit==='scale-down'?1:Infinity)
  const w=nw*scale,h=nh*scale
  display={x:box.x+(box.w-w)/2,y:box.y+(box.h-h)/2,w,h}
 }
 let visible={...display}
 for(const limit of [item.fit==='cover'||item.fit==='none'?box:null,item.clip].filter(Boolean)){
  const x=Math.max(visible.x,limit.x),y=Math.max(visible.y,limit.y)
  visible={x,y,w:Math.max(0,Math.min(visible.x+visible.w,limit.x+limit.w)-x),h:Math.max(0,Math.min(visible.y+visible.h,limit.y+limit.h)-y)}
 }
 return {display,visible}
}

function assetPath(item,spec){
 if(item.asset==='brand-logo')return spec?.designSystem?.brand?.logoPath??null
 if(Number.isInteger(item.assetIndex))return spec?.assetBindings?.[item.assetIndex]?.path??null
 if(item.src?.startsWith('file://'))return decodeURIComponent(new URL(item.src).pathname)
 return null
}

function imagePlan(item,ops,context,spec){
 const path=assetPath(item,spec)
 if(!path){context.issues.push('image-without-path');return}
 const {display,visible}=imageRect(item)
 if(visible.w<1||visible.h<1)return
 const cropped=Math.abs(visible.w-display.w)>.5||Math.abs(visible.h-display.h)>.5
 const op={type:'image',path,x:inch(visible.x),y:inch(visible.y),w:inch(visible.w),h:inch(visible.h),altText:item.alt||'',source:item}
 if(cropped){
  Object.assign(op,{w:inch(display.w),h:inch(display.h),sizing:{type:'crop',x:inch(visible.x-display.x),y:inch(visible.y-display.y),w:inch(visible.w),h:inch(visible.h)}})
 }
 if((item.opacity??1)<.99)op.transparency=Math.round((1-item.opacity)*100)
 ops.push(op)
}

function vectorPlan(item,ops,context){
 for(const shape of item.shapes){
  let subpaths
  try{subpaths=transformSubpaths(parsePath(shape.d),shape.matrix)}catch{context.issues.push('vector-path-invalid');continue}
  const bounds=pathBounds(subpaths)
  if(!bounds)continue
  const width=Math.max(bounds.w,.5),height=Math.max(bounds.h,.5)
  const points=[]
  for(const path of subpaths){
   path.segments.forEach(segment=>{
    const rel=segment.points.map((value,index)=>inch(index%2?value-bounds.y:value-bounds.x))
    if(segment.type==='M')points.push({x:rel[0],y:rel[1],moveTo:true})
    else if(segment.type==='L')points.push({x:rel[0],y:rel[1]})
    else points.push({x:rel[4],y:rel[5],curve:{type:'cubic',x1:rel[0],y1:rel[1],x2:rel[2],y2:rel[3]}})
   })
   if(path.closed)points.push({close:true})
  }
  const opacity=item.opacity??1
  ops.push({type:'shape',shape:'custGeom',x:inch(bounds.x),y:inch(bounds.y),w:inch(width),h:inch(height),points,
   fill:shape.fill?{color:hex(shape.fill),transparency:transparency(shape.fill,opacity)}:null,
   line:shape.stroke?{color:hex(shape.stroke),transparency:transparency(shape.stroke,opacity),width:Math.max(.25,r3(shape.strokeWidth*PT)),
    cap:shape.linecap,dashType:shape.dash?'dash':'solid'}:null,source:item,vector:true})
 }
}

function tablePlan(item,ops,context){
 const rows=item.rows.filter(row=>row.cells.length)
 if(!rows.length)return
 const first=rows.find(row=>row.cells.every(cell=>(cell.colSpan??1)===1))??rows[0]
 const colW=first.cells.map(cell=>inch(cell.w))
 const border=side=>side&&side.width>0&&side.color&&!['none','hidden'].includes(side.style)?{type:'solid',pt:r3(side.width*PT),color:hex(side.color)}:{type:'none'}
 const data=rows.map(row=>row.cells.map(cell=>({text:cell.text,options:{
  fill:cell.fill?{color:hex(cell.fill),transparency:transparency(cell.fill)}:undefined,color:cell.color?hex(cell.color):undefined,
  fontSize:r3(cell.fontSize*PT),bold:cell.fontWeight>=600,fontFace:officeFont(cell.fontFamily,context.font),
  align:['center','right'].includes(cell.align)?cell.align:'left',valign:cell.valign==='top'?'top':cell.valign==='bottom'?'bottom':'middle',
  margin:cell.padding.map(value=>inch(value)),border:cell.borders.map(border),colspan:cell.colSpan>1?cell.colSpan:undefined,
 }})))
 ops.push({type:'table',rows:data,x:inch(item.x),y:inch(item.y),w:inch(item.w),colW,rowH:rows.map(row=>inch(row.h)),source:item})
}

export function planSceneSlide(scene,spec,{font='Microsoft YaHei'}={}){
 const context={background:null,issues:[],font}
 const ops=[]
 for(const item of scene.exportLayer.items){
  if(item.kind==='box')boxPlan(item,ops,context)
  else if(item.kind==='text')textPlan(item,ops,context)
  else if(item.kind==='image')imagePlan(item,ops,context,spec)
  else if(item.kind==='vector')vectorPlan(item,ops,context)
  else if(item.kind==='svg')ops.push({type:'image',data:`data:image/svg+xml;base64,${Buffer.from(item.markup,'utf8').toString('base64')}`,x:inch(item.x),y:inch(item.y),w:inch(item.w),h:inch(item.h),altText:item.label||'矢量图形',source:item})
  else if(item.kind==='table')tablePlan(item,ops,context)
  else if(item.kind==='chart')ops.push({type:'chart',model:item.model,x:inch(item.x),y:inch(item.y),w:inch(item.w),h:inch(item.h),source:item})
  else if(item.kind==='media'){
   const path=Number.isInteger(item.assetIndex)?spec?.assetBindings?.[item.assetIndex]?.path:null
   ops.push({type:'media',mediaType:item.mediaType==='audio'?'audio':'video',path,x:inch(item.x),y:inch(item.y),w:inch(item.w),h:inch(item.h),label:item.label,source:item})
  }
 }
 const stats={}
 for(const op of ops)stats[op.type]=(stats[op.type]??0)+1
 return {background:context.background,ops,stats,issues:context.issues}
}

// ------------------------------------------------------------------ applying
export function applyScenePlan(slide,plan,{ShapeType,ChartType,font,registry}){
 if(plan.background)slide.background=plan.background
 for(const op of plan.ops){
  if(op.type==='shape'){
   const options={x:op.x,y:op.y,w:op.w,h:op.h}
   options.fill=op.fill?{color:op.fill.color,transparency:op.fill.transparency||0}:{type:'none'}
   options.line=op.line?{color:op.line.color,width:op.line.width,transparency:op.line.transparency||0,dashType:op.line.dashType}:{type:'none'}
   if(op.rectRadius)options.rectRadius=op.rectRadius
   if(op.rotate)options.rotate=op.rotate
   if(op.shadow)options.shadow=op.shadow
   if(op.points)options.points=op.points
   if(op.gradient){options.objectName=`yzgrad-${registry.gradients.length}`;registry.gradients.push(op.gradient)}
   else if(op.line?.cap==='round'){options.objectName=`yzcap-${registry.capped++}`}
   slide.addShape(op.shape==='custGeom'?ShapeType.custGeom:ShapeType[op.shape]??op.shape,options)
  }else if(op.type==='text'){
   slide.addText(op.runs,{x:op.x,y:op.y,w:op.w,h:op.h,margin:0,valign:'top',align:op.align,fit:'none',wrap:op.wrap!==false,
    lineSpacing:op.lineSpacing,paraSpaceBefore:0,paraSpaceAfter:0,fontFace:font,isTextBox:true})
  }else if(op.type==='image'){
   const options={x:op.x,y:op.y,w:op.w,h:op.h,altText:op.altText}
   if(op.path)options.path=op.path;else options.data=op.data
   if(op.sizing)options.sizing=op.sizing
   if(op.transparency)options.transparency=op.transparency
   slide.addImage(options)
  }else if(op.type==='table'){
   slide.addTable(op.rows,{x:op.x,y:op.y,w:op.w,colW:op.colW,rowH:op.rowH,autoPage:false,fontFace:font})
  }else if(op.type==='chart'){
   const patches=addNativeChart(slide,op.model,{x:op.x,y:op.y,w:op.w,h:op.h},ChartType)
   // Chart parts are numbered in creation order across the whole deck.
   if(patches)registry.chartPatches[registry.chartCount]=patches
  }else if(op.type==='media'){
   let placed=false
   if(op.path&&typeof slide.addMedia==='function'){
    try{slide.addMedia({type:op.mediaType,path:op.path,x:op.x,y:op.y,w:op.w,h:op.h});placed=true}catch{}
   }
   if(!placed){
    slide.addShape(ShapeType.rect,{x:op.x,y:op.y,w:op.w,h:op.h,fill:{color:'11172C'},line:{type:'none'}})
    slide.addText(op.mediaType==='video'?'视频素材（请在演示软件中播放）':'音频素材（请在演示软件中播放）',{x:op.x,y:op.y+op.h/2-.25,w:op.w,h:.5,align:'center',fontFace:font,fontSize:16,bold:true,color:'FFFFFF',margin:0})
   }
  }
 }
}

// ------------------------------------------------------- package post-process
const alphaXml=alpha=>alpha<.999?`<a:alpha val="${Math.round(alpha*100000)}"/>`:''
export function gradientXml(gradient){
 const stops=gradient.stops.map(stop=>`<a:gs pos="${Math.round(stop.pos*100000)}"><a:srgbClr val="${stop.color}">${alphaXml(stop.alpha)}</a:srgbClr></a:gs>`).join('')
 const shade=gradient.type==='radial'
  ?`<a:path path="circle"><a:fillToRect l="${Math.round(gradient.focus.x*100000)}" t="${Math.round(gradient.focus.y*100000)}" r="${Math.round((1-gradient.focus.x)*100000)}" b="${Math.round((1-gradient.focus.y)*100000)}"/></a:path>`
  :`<a:lin ang="${Math.round(gradient.angle*60000)}" scaled="0"/>`
 return `<a:gradFill rotWithShape="1"><a:gsLst>${stops}</a:gsLst>${shade}</a:gradFill>`
}

export function patchSlideXml(xml,registry){
 let output=xml.replace(/<p:sp>((?:(?!<\/p:sp>).)*?name="yzgrad-(\d+)"(?:(?!<\/p:sp>).)*?)<\/p:sp>/gs,(match,body,index)=>{
  const gradient=registry.gradients[Number(index)]
  if(!gradient)return match
  return `<p:sp>${body.replace(/<a:solidFill>(?:(?!<\/a:solidFill>).)*<\/a:solidFill>/s,gradientXml(gradient))}</p:sp>`
 })
 output=output.replace(/<p:sp>((?:(?!<\/p:sp>).)*?name="yzcap-\d+"(?:(?!<\/p:sp>).)*?)<\/p:sp>/gs,(match,body)=>`<p:sp>${body.replace(/<a:ln w="(\d+)">/,'<a:ln w="$1" cap="rnd">').replace(/<a:prstDash val="solid"\/>/,'<a:prstDash val="solid"/><a:round/>')}</p:sp>`)
 // PptxGenJS writes "adj" for every preset; round2SameRect reads adj1.
 output=output.replace(/(<a:prstGeom prst="round2SameRect"><a:avLst>)<a:gd name="adj"/g,'$1<a:gd name="adj1"')
 return output
}

export function patchChartXml(xml,{series={},axes={}}={}){
 let output=xml.replace(/<c:ser>(?:(?!<\/c:ser>).)*<\/c:ser>/gs,block=>{
  const name=block.match(/<c:tx>.*?<c:v>(.*?)<\/c:v>/s)?.[1]
  const patch=series[name]
  if(!patch)return block
  let result=block
  if(patch.noFill)result=result.replace(/<c:spPr>(?:(?!<\/c:spPr>).)*<\/c:spPr>/s,'<c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr>')
  if(patch.hideLabels)result=result.replace(/<c:dLbls>(?:(?!<\/c:dLbls>).)*<\/c:dLbls>/s,'<c:dLbls><c:delete val="1"/></c:dLbls>')
  if(patch.formatCode)result=result.replace(/(<c:dLbls>(?:(?!<\/c:dLbls>).)*?)<c:numFmt formatCode="[^"]*"/s,`$1<c:numFmt formatCode="${patch.formatCode.replace(/"/g,'&quot;')}"`)
  return result
 })
 output=output.replace(/<c:(valAx|catAx)>(?:(?!<\/c:\1>).)*<\/c:\1>/gs,block=>{
  const position=block.match(/<c:axPos val="(\w)"\/>/)?.[1]
  const patch=axes[position]
  if(!patch)return block
  let result=block
  if(patch.formatCode)result=result.replace(/<c:numFmt formatCode="[^"]*"/,`<c:numFmt formatCode="${patch.formatCode.replace(/"/g,'&quot;')}"`)
  if(patch.scale)result=result.replace(/<c:scaling>(?:(?!<\/c:scaling>).)*<\/c:scaling>/s,`<c:scaling><c:orientation val="minMax"/><c:max val="${patch.scale.max}"/><c:min val="${patch.scale.min}"/></c:scaling>`)
  if(patch.scale){
   result=result.replace(/<c:majorUnit val="[^"]*"\/>/,'')
   const unit=`<c:majorUnit val="${patch.scale.step}"/>`
   result=/<c:crossBetween[^>]*\/>/.test(result)?result.replace(/(<c:crossBetween[^>]*\/>)/,`$1${unit}`)
    :/<c:crosses(?:At)? [^>]*\/>/.test(result)?result.replace(/(<c:crosses(?:At)? [^>]*\/>)/,`$1${unit}`):result.replace(/<\/c:valAx>$/,`${unit}</c:valAx>`)
  }
  if(patch.bold===false)result=result.replace(/(<c:txPr>(?:(?!<\/c:txPr>).)*?<a:defRPr[^>]*?) b="1"/s,'$1 b="0"')
  return result
 })
 return output
}

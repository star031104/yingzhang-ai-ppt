// Browser-side collector for the export layer of the Scene IR.
//
// `collectExportLayer` runs inside Chromium (page.evaluate) after the candidate
// screenshot was taken. It records every painted primitive of the slide in CSS
// pixels: boxes (background, border, radius, shadow, gradients), text blocks
// with styled runs, images, tables, charts, vectors and media. The PPTX scene
// compiler turns this list into native PowerPoint objects, so the exported deck
// follows the geometry of the exact HTML candidate that was scored and selected.
//
// The function must stay self-contained: Playwright serialises its source.
export function collectExportLayer(){
 const slide=document.querySelector('section.slide')||document.body
 const origin=slide.getBoundingClientRect()
 const round=value=>Math.round(value*100)/100
 const box=rect=>({x:round(rect.left-origin.left),y:round(rect.top-origin.top),w:round(rect.width),h:round(rect.height)})
 const px=value=>Number.parseFloat(value)||0
 const color=value=>{
  const match=String(value??'').match(/rgba?\(([^)]+)\)/)
  if(!match)return null
  const parts=match[1].split(/[\s,/]+/).filter(Boolean).map(Number)
  if(parts.length<3||parts.slice(0,3).some(part=>!Number.isFinite(part)))return null
  const alpha=Number.isFinite(parts[3])?parts[3]:1
  return alpha>0.003?{r:Math.round(parts[0]),g:Math.round(parts[1]),b:Math.round(parts[2]),a:round(alpha)}:null
 }

 // 1. Pseudo elements carry decorative bars, dots and overlays. Materialise them
 //    as real elements so their boxes can be measured; revert if layout moves.
 const all=()=>[slide,...slide.querySelectorAll('*')]
 const snapshot=()=>all().map(el=>{const r=el.getBoundingClientRect();return `${r.left},${r.top},${r.width},${r.height}`})
 const before=snapshot(),created=[]
 for(const el of all()){
  if(['IMG','VIDEO','AUDIO','svg','SVG','TABLE','INPUT','BR'].includes(el.tagName)||el.closest('svg'))continue
  for(const which of ['before','after']){
   const ps=getComputedStyle(el,`::${which}`),content=ps.content
   if(!content||content==='none'||content==='normal'||ps.display==='none')continue
   const node=document.createElement('yz-pseudo')
   for(let i=0;i<ps.length;i++){const prop=ps[i];if(prop!=='content')node.style.setProperty(prop,ps.getPropertyValue(prop))}
   const literal=content.match(/^"((?:[^"\\]|\\.)*)"$/)
   node.textContent=literal?literal[1].replace(/\\(.)/g,'$1'):''
   if(which==='before')el.insertBefore(node,el.firstChild);else el.appendChild(node)
   el.setAttribute(`data-yz-pseudo-${which}`,'1')
   created.push({el,node,which})
  }
 }
 let pseudoMaterialized=0
 if(created.length){
  const guard=document.createElement('style')
  guard.textContent='[data-yz-pseudo-before]::before{content:none!important}[data-yz-pseudo-after]::after{content:none!important}'
  document.head.appendChild(guard)
  // New nodes shift the element list; compare the original elements only.
  const originals=new Set(created.map(item=>item.node))
  const after=all().filter(el=>!originals.has(el)&&!el.closest('yz-pseudo')).map(el=>{const r=el.getBoundingClientRect();return `${r.left},${r.top},${r.width},${r.height}`})
  const moved=after.length!==before.length||after.some((value,index)=>{
   const a=value.split(',').map(Number),b=before[index].split(',').map(Number)
   return a.some((n,i)=>Math.abs(n-b[i])>0.6)
  })
  if(moved){
   for(const item of created){item.node.remove();item.el.removeAttribute(`data-yz-pseudo-${item.which}`)}
   guard.remove()
  }else pseudoMaterialized=created.length
 }

 // 2. Paint-order helpers (approximation of CSS stacking for slide layouts).
 const stackCache=new Map(),opacityCache=new Map(),clipCache=new Map()
 const stackInfo=el=>{
  if(stackCache.has(el))return stackCache.get(el)
  let z=0,layer=0
  for(let node=el;node&&node!==slide;node=node.parentElement){
   const cs=getComputedStyle(node)
   if(cs.position!=='static'){layer=1;if(cs.zIndex!=='auto'){z=Number.parseInt(cs.zIndex,10)||0;break}}
  }
  const value={z,layer};stackCache.set(el,value);return value
 }
 const opacityOf=el=>{
  if(!el||el===document.documentElement)return 1
  if(opacityCache.has(el))return opacityCache.get(el)
  const value=Number(getComputedStyle(el).opacity)*opacityOf(el.parentElement)
  opacityCache.set(el,value);return value
 }
 const clipOf=el=>{
  if(!el||el===document.documentElement)return null
  if(clipCache.has(el))return clipCache.get(el)
  let clip=clipOf(el.parentElement)
  const cs=getComputedStyle(el)
  if(el!==slide&&(cs.overflowX!=='visible'||cs.overflowY!=='visible')){
   const r=el.getBoundingClientRect(),own=box(r)
   own.x+=px(cs.borderLeftWidth);own.y+=px(cs.borderTopWidth)
   own.w-=px(cs.borderLeftWidth)+px(cs.borderRightWidth);own.h-=px(cs.borderTopWidth)+px(cs.borderBottomWidth)
   own.radius=px(cs.borderTopLeftRadius)
   if(clip){
    const x=Math.max(clip.x,own.x),y=Math.max(clip.y,own.y)
    clip={x,y,w:Math.max(0,Math.min(clip.x+clip.w,own.x+own.w)-x),h:Math.max(0,Math.min(clip.y+clip.h,own.y+own.h)-y),radius:own.radius}
   }else clip=own
  }
  clipCache.set(el,clip);return clip
 }

 const radiusOf=(cs,w,h)=>['TopLeft','TopRight','BottomRight','BottomLeft'].map(corner=>{
  const raw=cs[`border${corner}Radius`]
  const first=String(raw).split(' ')[0]
  return first.endsWith('%')?Math.min(w,h)*px(first)/100:px(first)
 })
 const gradients=value=>{
  if(!value||value==='none'||!/gradient\(/.test(value))return []
  const layers=[];let depth=0,start=0
  for(let i=0;i<value.length;i++){
   if(value[i]==='(')depth++
   else if(value[i]===')')depth--
   else if(value[i]===','&&depth===0){layers.push(value.slice(start,i).trim());start=i+1}
  }
  layers.push(value.slice(start).trim())
  return layers.filter(layer=>/gradient\(/.test(layer)).map(layer=>{
   const type=layer.startsWith('radial')?'radial':layer.startsWith('linear')?'linear':'other'
   const inner=layer.slice(layer.indexOf('(')+1,layer.lastIndexOf(')'))
   const parts=[];let d=0,s=0
   for(let i=0;i<inner.length;i++){
    if(inner[i]==='(')d++;else if(inner[i]===')')d--;else if(inner[i]===','&&d===0){parts.push(inner.slice(s,i).trim());s=i+1}
   }
   parts.push(inner.slice(s).trim())
   let angle=180,shape=null
   if(parts.length&&!/rgba?\(/.test(parts[0])){
    const head=parts.shift()
    const deg=head.match(/(-?[\d.]+)deg/)
    if(deg)angle=Number(deg[1])
    else if(/to /.test(head))angle={'to top':0,'to right':90,'to bottom':180,'to left':270,'to top right':45,'to right top':45,'to bottom right':135,'to right bottom':135,'to bottom left':225,'to left bottom':225,'to top left':315,'to left top':315}[head.trim()]??180
    shape=head
   }
   const stops=parts.map(part=>{
    const c=part.match(/rgba?\([^)]+\)/)
    const rest=c?part.replace(c[0],'').trim():part
    const position=rest.match(/(-?[\d.]+)(%|px)/)
    const raw=c?c[0]:'rgba(0,0,0,0)'
    const parsed=String(raw).match(/rgba?\(([^)]+)\)/)?.[1].split(/[\s,/]+/).filter(Boolean).map(Number)??[0,0,0,0]
    return {color:{r:parsed[0],g:parsed[1],b:parsed[2],a:Number.isFinite(parsed[3])?parsed[3]:1},position:position?{value:Number(position[1]),unit:position[2]}:null}
   })
   return {type,angle,shape,stops}
  })
 }
 const shadowOf=value=>{
  if(!value||value==='none'||/inset/.test(value))return null
  const c=value.match(/rgba?\([^)]+\)/)
  const numbers=value.replace(c?.[0]??'','').trim().split(/\s+/).map(px)
  const parsed=color(c?.[0])
  if(!parsed)return null
  return {color:parsed,x:numbers[0]??0,y:numbers[1]??0,blur:numbers[2]??0,spread:numbers[3]??0}
 }

 const items=[]
 let order=0
 const base=(el,extra=0)=>{
  const {z,layer}=stackInfo(el)
  return {order:order+extra,z,layer,opacity:round(opacityOf(el)),clip:clipOf(el.parentElement)}
 }
 const nodeId=el=>el.getAttribute('data-node-id')??null

 // 3. Text runs belonging to a block container (inline descendants only).
 const isInline=el=>['inline','contents'].includes(getComputedStyle(el).display)
 const textRuns=block=>{
  const runs=[],rects=[]
  const visitInline=(parent)=>{
   for(const child of parent.childNodes){
    if(child.nodeType===Node.TEXT_NODE){
     const raw=child.data
     if(!raw.trim()&&!/\S/.test(raw))
      {if(runs.length&&!runs.at(-1).lineBreak&&raw.length&&!/\s$/.test(runs.at(-1).text))runs.push({...runs.at(-1),text:' ',space:true});continue}
     const cs=getComputedStyle(child.parentElement)
     const pre=/pre/.test(cs.whiteSpace)
     let text=pre?raw:raw.replace(/\s+/g,' ')
     if(cs.textTransform==='uppercase')text=text.toUpperCase()
     else if(cs.textTransform==='lowercase')text=text.toLowerCase()
     const range=document.createRange();range.selectNodeContents(child)
     const clientRects=[...range.getClientRects()].filter(r=>r.width>0&&r.height>0)
     if(!clientRects.length)continue
     rects.push(...clientRects)
     const fill=color(cs.color)
     runs.push({text,fontSize:px(cs.fontSize),fontWeight:Number(cs.fontWeight)||400,italic:cs.fontStyle==='italic',
      color:fill,fontFamily:cs.fontFamily,letterSpacing:cs.letterSpacing==='normal'?0:px(cs.letterSpacing),
      underline:/underline/.test(cs.textDecorationLine),pre})
    }else if(child.nodeType===Node.ELEMENT_NODE){
     if(child.tagName==='BR'){runs.push({text:'',lineBreak:true});continue}
     if(child.tagName==='YZ-PSEUDO'&&!isInline(child))continue
     const cs=getComputedStyle(child)
     if(cs.display==='none'||cs.visibility==='hidden')continue
     if(isInline(child)&&!['IMG','SVG','svg','VIDEO','AUDIO'].includes(child.tagName))visitInline(child)
    }
   }
  }
  visitInline(block)
  while(runs.length&&(runs[0].space||runs[0].lineBreak))runs.shift()
  while(runs.length&&(runs.at(-1).space||runs.at(-1).lineBreak))runs.pop()
  if(runs.length&&!runs[0].pre)runs[0].text=runs[0].text.replace(/^\s+/,'')
  if(runs.length&&!runs.at(-1).pre)runs.at(-1).text=runs.at(-1).text.replace(/\s+$/,'')
  return {runs:runs.filter(run=>run.lineBreak||run.text.length),rects}
 }
 const lineCount=rects=>{
  const tops=[]
  for(const rect of [...rects].sort((a,b)=>a.top-b.top)){
   if(!tops.some(top=>Math.abs(top-rect.top)<Math.max(4,rect.height*.45)))tops.push(rect.top)
  }
  return tops.length
 }

 const svgShapes=svg=>{
  const shapes=[],supported=new Set(['g','path','line','rect','circle','ellipse','polyline','polygon','title','desc'])
  for(const el of svg.querySelectorAll('*')){
   const tag=el.tagName.toLowerCase()
   if(!supported.has(tag))return null
   if(['g','title','desc'].includes(tag))continue
   const cs=getComputedStyle(el)
   if(cs.display==='none'||cs.visibility==='hidden')continue
   if(/url\(/.test(cs.fill)||/url\(/.test(cs.stroke)||cs.filter!=='none'||cs.mask!=='none')return null
   const m=el.getScreenCTM()
   if(!m)return null
   const num=name=>Number(el.getAttribute(name))||0
   let d=''
   if(tag==='path')d=el.getAttribute('d')??''
   else if(tag==='line')d=`M${num('x1')} ${num('y1')}L${num('x2')} ${num('y2')}`
   else if(tag==='rect'){const x=num('x'),y=num('y'),w=num('width'),h=num('height'),r=Math.min(num('rx')||num('ry'),w/2,h/2);d=r?`M${x+r} ${y}H${x+w-r}A${r} ${r} 0 0 1 ${x+w} ${y+r}V${y+h-r}A${r} ${r} 0 0 1 ${x+w-r} ${y+h}H${x+r}A${r} ${r} 0 0 1 ${x} ${y+h-r}V${y+r}A${r} ${r} 0 0 1 ${x+r} ${y}Z`:`M${x} ${y}H${x+w}V${y+h}H${x}Z`}
   else if(tag==='circle'||tag==='ellipse'){const cx=num('cx'),cy=num('cy'),rx=tag==='circle'?num('r'):num('rx'),ry=tag==='circle'?num('r'):num('ry');d=`M${cx-rx} ${cy}A${rx} ${ry} 0 1 0 ${cx+rx} ${cy}A${rx} ${ry} 0 1 0 ${cx-rx} ${cy}Z`}
   else{const points=(el.getAttribute('points')??'').trim().split(/[\s,]+/).map(Number);for(let i=0;i+1<points.length;i+=2)d+=`${i?'L':'M'}${points[i]} ${points[i+1]}`;if(tag==='polygon')d+='Z'}
   if(!d.trim())continue
   const fill=cs.fill==='none'?null:color(cs.fill),stroke=cs.stroke==='none'?null:color(cs.stroke)
   if(fill)fill.a=round(fill.a*Number(cs.fillOpacity??1))
   if(stroke)stroke.a=round(stroke.a*Number(cs.strokeOpacity??1))
   if(!fill&&!stroke)continue
   shapes.push({d,matrix:[m.a,m.b,m.c,m.d,m.e-origin.left,m.f-origin.top].map(round),fill,stroke,
    strokeWidth:round(px(cs.strokeWidth)*Math.sqrt(Math.abs(m.a*m.d-m.b*m.c))),linecap:cs.strokeLinecap,linejoin:cs.strokeLinejoin,
    dash:cs.strokeDasharray!=='none'})
  }
  return shapes
 }
 const serializeSvg=svg=>{
  const clone=svg.cloneNode(true),source=[svg,...svg.querySelectorAll('*')],target=[clone,...clone.querySelectorAll('*')]
  source.forEach((el,index)=>{
   const cs=getComputedStyle(el)
   for(const prop of ['fill','stroke','stroke-width','stroke-linecap','stroke-linejoin','opacity','font-size','font-family','font-weight'])target[index].setAttribute(prop,cs.getPropertyValue(prop))
  })
  const r=svg.getBoundingClientRect()
  clone.setAttribute('xmlns','http://www.w3.org/2000/svg')
  clone.setAttribute('width',String(r.width));clone.setAttribute('height',String(r.height))
  return new XMLSerializer().serializeToString(clone)
 }

 const visit=el=>{
  const cs=getComputedStyle(el)
  if(cs.display==='none'||opacityOf(el)<0.01)return
  const rect=el.getBoundingClientRect(),geometry=box(rect),tag=el.tagName.toLowerCase()
  const hidden=cs.visibility==='hidden'
  if(!hidden&&rect.width>0&&rect.height>0&&!['video','audio','svg','table'].includes(tag)){
   const fill=color(cs.backgroundColor),layers=gradients(cs.backgroundImage)
   const sides=['Top','Right','Bottom','Left'].map(side=>({side:side.toLowerCase(),width:px(cs[`border${side}Width`]),
    style:cs[`border${side}Style`],color:color(cs[`border${side}Color`])})).filter(side=>side.width>0&&side.color&&!['none','hidden'].includes(side.style))
   const shadow=shadowOf(cs.boxShadow)
   if(fill||layers.length||sides.length||shadow){
    items.push({kind:'box',...base(el),...geometry,fill,gradients:layers,borders:sides,radius:radiusOf(cs,rect.width,rect.height).map(round),
     shadow,root:el===slide,nodeId:nodeId(el),tag})
   }
  }
  if(tag==='img'){
   // Object-fit applies to the content box; padding shows the element background.
   const inset={l:px(cs.borderLeftWidth)+px(cs.paddingLeft),t:px(cs.borderTopWidth)+px(cs.paddingTop),r:px(cs.borderRightWidth)+px(cs.paddingRight),b:px(cs.borderBottomWidth)+px(cs.paddingBottom)}
   const content={x:round(geometry.x+inset.l),y:round(geometry.y+inset.t),w:round(geometry.w-inset.l-inset.r),h:round(geometry.h-inset.t-inset.b)}
   if(!hidden)items.push({kind:'image',...base(el,.5),...content,fit:cs.objectFit,naturalWidth:el.naturalWidth,naturalHeight:el.naturalHeight,
    radius:radiusOf(cs,rect.width,rect.height).map(round),alt:el.getAttribute('alt')??'',assetIndex:el.hasAttribute('data-asset-index')?Number(el.getAttribute('data-asset-index')):null,
    asset:el.getAttribute('data-asset')??null,src:/^data:/.test(el.currentSrc||el.src)?null:(el.currentSrc||el.src)})
   order++;return
  }
  if(tag==='video'||tag==='audio'){
   if(!hidden)items.push({kind:'media',...base(el),...geometry,mediaType:tag,assetIndex:el.hasAttribute('data-asset-index')?Number(el.getAttribute('data-asset-index')):null,label:el.getAttribute('aria-label')??''})
   order++;return
  }
  if(el.hasAttribute('data-chart')){
   let model=null
   try{model=JSON.parse(el.getAttribute('data-chart'))}catch{}
   const svg=el.querySelector('svg'),target=svg?box(svg.getBoundingClientRect()):geometry
   if(model&&!hidden)items.push({kind:'chart',...base(el,.5),...target,model,
    labels:[...el.querySelectorAll('text')].map(node=>node.textContent.trim()).filter(Boolean),nodeId:nodeId(el)})
   order++;return
  }
  if(tag==='svg'){
   if(!hidden&&rect.width>0&&rect.height>0){
    const shapes=svgShapes(el)
    items.push(shapes?{kind:'vector',...base(el),...geometry,shapes,label:el.getAttribute('aria-label')??''}
     :{kind:'svg',...base(el),...geometry,markup:serializeSvg(el),label:el.getAttribute('aria-label')??''})
   }
   order++;return
  }
  if(tag==='table'){
   if(!hidden){
    const rows=[...el.rows].map(row=>{
     const r=row.getBoundingClientRect()
     return {h:round(r.height),cells:[...row.cells].map(cell=>{
      const c=getComputedStyle(cell),cr=cell.getBoundingClientRect()
      const rowFill=color(getComputedStyle(row).backgroundColor)
      return {text:cell.innerText.trim(),w:round(cr.width),colSpan:cell.colSpan,fill:color(c.backgroundColor)??rowFill,color:color(c.color),
       fontSize:px(c.fontSize),fontWeight:Number(c.fontWeight)||400,fontFamily:c.fontFamily,align:c.textAlign,valign:c.verticalAlign,
       padding:[px(c.paddingTop),px(c.paddingRight),px(c.paddingBottom),px(c.paddingLeft)],
       borders:['Top','Right','Bottom','Left'].map(side=>({width:px(c[`border${side}Width`]),color:color(c[`border${side}Color`]),style:c[`border${side}Style`]}))}
     })}
    })
    items.push({kind:'table',...base(el,.5),...geometry,rows,nodeId:nodeId(el)})
   }
   order++;return
  }
  const own=order++
  if(!isInline(el)&&!hidden){
   const {runs,rects}=textRuns(el)
   if(runs.some(run=>run.text&&run.text.trim())){
    const left=Math.min(...rects.map(r=>r.left)),top=Math.min(...rects.map(r=>r.top))
    const right=Math.max(...rects.map(r=>r.right)),bottom=Math.max(...rects.map(r=>r.bottom))
    const content={x:rect.left+px(cs.borderLeftWidth)+px(cs.paddingLeft),y:rect.top+px(cs.borderTopWidth)+px(cs.paddingTop)}
    content.w=rect.width-px(cs.borderLeftWidth)-px(cs.borderRightWidth)-px(cs.paddingLeft)-px(cs.paddingRight)
    content.h=rect.height-px(cs.borderTopWidth)-px(cs.borderBottomWidth)-px(cs.paddingTop)-px(cs.paddingBottom)
    const lineHeight=cs.lineHeight==='normal'?null:px(cs.lineHeight)
    const {z,layer}=stackInfo(el)
    items.push({kind:'text',order:own+.5,z,layer,opacity:round(opacityOf(el)),clip:clipOf(el),
     x:round(left-origin.left),y:round(top-origin.top),w:round(right-left),h:round(bottom-top),
     container:{x:round(content.x-origin.left),y:round(content.y-origin.top),w:round(content.w),h:round(content.h)},
     align:cs.textAlign==='start'?(cs.direction==='rtl'?'right':'left'):cs.textAlign==='end'?'right':cs.textAlign,
     fontSize:px(cs.fontSize),lineHeight,lines:lineCount(rects),whiteSpace:cs.whiteSpace,runs,nodeId:nodeId(el),tag,
     region:el.closest('footer')?'footer':el.closest('header')?'header':tag==='h1'?'title':'content'})
   }
  }
  for(const child of el.children)visit(child)
 }
 visit(slide)
 return {version:'scene-export-v1',canvas:{width:Math.round(origin.width),height:Math.round(origin.height)},pseudoMaterialized,
  items:items.sort((a,b)=>a.z-b.z||a.layer-b.layer||a.order-b.order)}
}

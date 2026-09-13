import {chromium} from 'playwright'
import {pathToFileURL} from 'node:url'

let sharedBrowser=null
let launchingBrowser=null
async function browserInstance(){
 if(!sharedBrowser){
  launchingBrowser??=chromium.launch({headless:true})
  try{sharedBrowser=await launchingBrowser}finally{launchingBrowser=null}
 }
 return sharedBrowser
}

async function settlePage(page){
 await page.evaluate(async()=>{
  await document.fonts.ready
  await Promise.all([...document.images].map(img=>img.decode().catch(()=>{})))
 })
}
export async function closeSceneBrowser(){
 if(sharedBrowser){await sharedBrowser.close().catch(()=>{});sharedBrowser=null}
}

export async function captureScene(htmlPath,pngPath){
 for(let attempt=0;attempt<2;attempt++){
  let context
  try{
  const browser=await browserInstance()
  context=await browser.newContext({viewport:{width:1280,height:720}})
  const page=await context.newPage()
  await page.goto(pathToFileURL(htmlPath).href)
  await settlePage(page)
  await page.screenshot({path:pngPath,animations:'disabled',timeout:30000})
  return await page.evaluate(()=>{
   const selector='[data-scene-type],h1,h2,h3,p,li,span,strong,b,figcaption,td,th,.flow-node,.agenda-card,.problem-card,.note-card,.insight-card,.conclusion-card,.split-grid aside,footer,img,svg,table,video,audio'
   const elements=[...document.querySelectorAll(selector)].filter(el=>{
    const r=el.getBoundingClientRect(),style=getComputedStyle(el)
    return r.width>0&&r.height>0&&style.visibility!=='hidden'&&style.display!=='none'
   })
   const ids=new Map(elements.map((el,index)=>[el,el.getAttribute('data-node-id')??`node-${index+1}`]))
   const textTags=new Set(['H1','H2','H3','P','LI','SPAN','STRONG','B','FIGCAPTION','TD','TH','FOOTER'])
   const structuredContent=[...document.querySelectorAll('[data-content-indices]')].flatMap(el=>el.getAttribute('data-content-indices').split(',').filter(Boolean).map(Number))
   return {version:'scene-ir-v1',measurementVersion:2,width:1280,height:720,visibleText:document.body.innerText,structuredContent,nodes:elements.map(el=>{
    const r=el.getBoundingClientRect(),style=getComputedStyle(el),declared=el.getAttribute('data-scene-type')
    const type=declared||(el.tagName==='IMG'?'image':el.tagName==='SVG'?'svg':el.tagName==='TABLE'?'table':el.tagName==='VIDEO'||el.tagName==='AUDIO'?'video':textTags.has(el.tagName)?'text':'shape')
    const region=el.closest('footer')?'footer':el.closest('header')?'header':el.tagName==='H1'?'title':el.closest('main')?'content':'canvas'
    const ancestorIds=[],clipBoxes=[],backgroundStack=[]
    for(let parent=el;parent;parent=parent.parentElement){
     if(parent!==el&&ids.has(parent))ancestorIds.push(ids.get(parent))
     const css=getComputedStyle(parent),box=parent.getBoundingClientRect()
     const gradient=css.backgroundImage.match(/rgba?\([^)]+\)/g)?.find(value=>!/^rgba\(.*,[\s]*0\)$/.test(value))
     backgroundStack.push(css.backgroundColor==='rgba(0, 0, 0, 0)'&&gradient?gradient:css.backgroundColor)
     if(['hidden','clip','scroll','auto'].includes(css.overflowX)||['hidden','clip','scroll','auto'].includes(css.overflowY))clipBoxes.push({box,x:css.overflowX!=='visible',y:css.overflowY!=='visible'})
    }
    const isTextLeaf=type==='text'&&!el.querySelector('h1,h2,h3,p,li,span,strong,b,figcaption')
    let textClipped=false
    if(isTextLeaf&&el.textContent.trim()){
     const range=document.createRange();range.selectNodeContents(el)
     textClipped=[...range.getClientRects()].some(rect=>clipBoxes.some(({box,x,y})=>
      (x&&(rect.left<box.left-2||rect.right>box.right+2))||(y&&(rect.top<box.top-2||rect.bottom>box.bottom+2))))
    }
    return {id:ids.get(el),type,tag:el.tagName.toLowerCase(),classes:[...el.classList],region,ancestorIds,isTextLeaf,text:(el.textContent??'').trim(),bbox:{x:r.x,y:r.y,width:r.width,height:r.height},measurement:{textClipped,scrollWidth:el.scrollWidth,scrollHeight:el.scrollHeight,clientWidth:el.clientWidth,clientHeight:el.clientHeight,assetMissing:el.tagName==='IMG'&&(!el.complete||el.naturalWidth===0)},style:{fontFamily:style.fontFamily,fontSize:parseFloat(style.fontSize)||0,fontWeight:style.fontWeight,color:style.color,backgroundColor:style.backgroundColor,backgroundStack,lineHeight:style.lineHeight,textAlign:style.textAlign,borderRadius:style.borderRadius},preferredExport:['text','shape','chart','diagram','table','video'].includes(type)?'native':type==='svg'?'svg':'raster',fallback:type==='text'||type==='shape'?['svg','raster']:['raster']}
   })}
  })
  }catch(error){
   if(attempt===1)throw error
   await closeSceneBrowser()
  }finally{await context?.close().catch(()=>{})}
 }
}

export async function exportPdf(htmlPath,pdfPath){
 const browser=await chromium.launch({headless:true})
 try{const page=await browser.newPage();await page.goto(pathToFileURL(htmlPath).href);await settlePage(page);await page.pdf({path:pdfPath,width:'13.333in',height:'7.5in',printBackground:true,margin:{top:'0',right:'0',bottom:'0',left:'0'}})}finally{await browser.close()}
}

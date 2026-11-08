// Reference exporter for the cross-format fidelity benchmark.
//
// Exports the *same* selected HTML candidates with dom-to-pptx (MIT, an
// independent DOM → editable PPTX converter) so the scene compiler can be compared
// against a third-party implementation of the same idea on identical input.
// dom-to-pptx is not a runtime dependency: install it on demand, e.g.
//   PUPPETEER_SKIP_DOWNLOAD=1 npm install --prefix runtime/tools/dom-to-pptx dom-to-pptx@2.1.2
//
// usage: node dom-to-pptx-reference.mjs <slides.json> <rendered-root> <out.pptx> <dom-to-pptx.bundle.js>
import fs from 'node:fs/promises'
import path from 'node:path'
import {pathToFileURL} from 'node:url'
import {chromium} from 'playwright'

const [slidesPath,renderedRoot,outPath,bundlePath]=process.argv.slice(2)
if(!bundlePath)throw new Error('usage: dom-to-pptx-reference.mjs <slides.json> <rendered-root> <out.pptx> <bundle.js>')
const parsed=JSON.parse(await fs.readFile(slidesPath,'utf8'))
const slides=(Array.isArray(parsed)?parsed:parsed.slides).slice().sort((a,b)=>a.position-b.position)
const browser=await chromium.launch({headless:true})
try{
 const context=await browser.newContext({viewport:{width:1280,height:720}})
 const page=await context.newPage()
 // Start from the first page (it carries the shared stylesheet), then append the
 // other selected pages' slide sections into the same document.
 await page.goto(pathToFileURL(path.join(renderedRoot,'slides',`${slides[0].position}.html`)).href)
 for(const slide of slides.slice(1)){
  const html=await fs.readFile(path.join(renderedRoot,'slides',`${slide.position}.html`),'utf8')
  await page.evaluate(markup=>{
   const doc=new DOMParser().parseFromString(markup,'text/html')
   const section=doc.querySelector('section.slide')
   if(section)document.body.appendChild(document.importNode(section,true))
  },html)
 }
 await page.addStyleTag({content:'html,body{overflow:visible!important;height:auto!important;transform:none!important}.slide{flex:none}'})
 await page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(img=>img.decode().catch(()=>{})))})
 await page.addScriptTag({path:bundlePath})
 const base64=await page.evaluate(async()=>{
  const blob=await window.domToPptx.exportToPptx(Array.from(document.querySelectorAll('section.slide')),{skipDownload:true,autoEmbedFonts:false,svgAsVector:true,width:13.333,height:7.5})
  const bytes=new Uint8Array(await blob.arrayBuffer())
  let binary='';for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x8000))
  return btoa(binary)
 })
 await fs.writeFile(outPath,Buffer.from(base64,'base64'))
 console.log(JSON.stringify({slides:slides.length,bytes:Buffer.byteLength(base64,'base64')}))
}finally{await browser.close()}

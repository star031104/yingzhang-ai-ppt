import fs from 'node:fs/promises'
import path from 'node:path'
import assert from 'node:assert/strict'
import JSZip from 'jszip'
import {main} from '../packages/presentation-engine/src/cli.mjs'
import {exportPptx} from '../packages/presentation-engine/src/pptx.mjs'

const root=path.resolve(process.argv[3]??'test-results/professional-quality')
await fs.mkdir(root,{recursive:true})
const fixture=JSON.parse(await fs.readFile(process.argv[2]??'benchmarks/render-quality/fixture.json','utf8'))
const tokens=JSON.parse(await fs.readFile('skills/visual/data-consulting/tokens.json','utf8'))
const slides=fixture.slides.map(slide=>({...slide,
 sourceRefs:[{document:'合成回归样例，非真实业务数据',section:'fixture'}],
 designSystem:{palette:tokens.palette,layoutProfile:tokens.layoutProfile,typography:{fontFamily:tokens.fontFamily}},
}))
const input=path.join(root,'slides.json')
await fs.writeFile(input,JSON.stringify(slides,null,2))
await main(['build',input,root])
const results=[]
for(const slide of slides){
 const selected=JSON.parse(await fs.readFile(path.join(root,'slides',String(slide.position),'current.json'),'utf8'))
 for(const field of ['overflow','textOverflow','missingAssets','missingContent','lowContrast'])assert.equal(selected.scoreDetail[field]??0,0,`Slide ${slide.position}: ${field}`)
 slide.visualIntent={...slide.visualIntent,selectedVariant:selected.variant}
 results.push({position:slide.position,variant:selected.variant,score:selected.score,
  geometry:selected.scoreDetail.geometry,textOverflow:selected.scoreDetail.textOverflow,
  image:path.join(root,'slides',String(slide.position),`${selected.variant}.png`)})
}
await fs.writeFile(input,JSON.stringify(slides,null,2))
await main(['assemble',input,root])
await exportPptx(slides,path.join(root,'样例.pptx'))
const zip=await JSZip.loadAsync(await fs.readFile(path.join(root,'样例.pptx')))
const slideParts=Object.keys(zip.files).filter(name=>/^ppt\/slides\/slide\d+\.xml$/.test(name))
assert.equal(slideParts.length,slides.length,'Export must preserve the requested slide count')
let tables=0
for(const name of slideParts){
 const xml=await zip.file(name).async('string')
 tables+=(xml.match(/<a:tbl>/g)??[]).length
}
const charts=Object.keys(zip.files).filter(name=>/^ppt\/charts\/chart\d+\.xml$/.test(name)).length
assert.equal(charts,fixture.expectedCharts??2);assert.equal(tables,fixture.expectedTables??2)
const report={fixture:fixture.description,slides:results,nativeCharts:charts,nativeTables:tables,
 verification:'Chromium screenshots and PPTX package data. Desktop PowerPoint/WPS rendering is not covered.'}
await fs.writeFile(path.join(root,'verification.json'),JSON.stringify(report,null,2))
console.log(JSON.stringify(report,null,2))

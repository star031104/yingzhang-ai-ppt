import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import JSZip from 'jszip'
import { referenceRegions } from '../src/reference-layout.mjs'
import { slideHtml } from '../src/author.mjs'
import { candidateVariants } from '../src/cli.mjs'
import { exportPptx } from '../src/pptx.mjs'

const spec = {
 id:'reference',position:1,role:'content',message:'Complete evidence',
 content:{title:'Reference layout',bullets:Array.from({length:8},(_,i)=>`Required point ${i}`)},
 designSystem:{typography:{fontFamily:'Arial'},referenceLayouts:{content:[
  {x:.05,y:.04,w:.9,h:.15,fontSize:36},
  {x:.05,y:.22,w:.43,h:.65,fontSize:20},
  {x:.52,y:.22,w:.43,h:.65,fontSize:20}
 ]}}, visualIntent:{selectedVariant:'personal-reference'}
}
test('reference layout preserves all evidence in HTML and editable PPTX', async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'yingzhang-reference-'))
 t.after(()=>fs.rm(root,{recursive:true,force:true}))
 assert.ok(candidateVariants(spec).includes('personal-reference'))
 const html=slideHtml(spec,'personal-reference')
 assert.match(html,/variant-personal-reference/)
 const output=path.join(root,'reference.pptx')
 await exportPptx([spec],output)
 const archive=await JSZip.loadAsync(await fs.readFile(output))
 const xml=await archive.file('ppt/slides/slide1.xml').async('string')
 for(const text of [spec.content.title,spec.message,...spec.content.bullets]){
  assert.ok(html.includes(text),`HTML missing ${text}`)
  assert.ok(xml.includes(text),`PPTX missing ${text}`)
 }
 assert.match(xml,/Arial/)
 assert.ok((xml.match(/<p:sp>/g)??[]).length>=3)
})
test('reference layout cannot displace data layouts or accept off-canvas regions',()=>{
 assert.equal(referenceRegions({...spec,role:'data'}),null)
 const malformed=structuredClone(spec);malformed.designSystem.referenceLayouts.content[0].x=2
 assert.equal(referenceRegions(malformed),null)
})

import test from 'node:test'
import assert from 'node:assert/strict'
import {sourceLabel} from '../src/source-label.mjs'
test('audience citations group pages while notes retain every section',()=>{
 const spec={sourceRefs:[1,2,3,5,5].map((page,i)=>({document:'论文.pdf',page,section:`S${i}`}))}
 assert.equal(sourceLabel(spec),'论文.pdf · 第1–3、5页')
 assert.match(sourceLabel(spec,true),/S4/)
 assert.equal(sourceLabel({sourceRefs:[]}), '')
})

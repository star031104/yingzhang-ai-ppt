import test from 'node:test'
import assert from 'node:assert/strict'
import {resolveComposition,tableFits} from '../src/content.mjs'
test('dense lead cannot enter the oversized editorial heading layout',()=>{
 const spec={role:'method',message:'论文摘要中的长句。'.repeat(12),content:{bullets:['方法说明','实验结果']},visualIntent:{contentRelation:'explanation'}}
 assert.equal(resolveComposition(spec,'evidence-brief'),'content-list')
 assert.equal(resolveComposition(spec,'workflow'),'content-list')
})
test('native table capacity accounts for wrapped cell text before PowerPoint expands rows',()=>{
 assert.equal(tableFits({headers:['任务','Accuracy'],rows:[['A',.89],['B',.85]]}),true)
 assert.equal(tableFits({headers:['任务','Accuracy','Precision','Recall','说明'],rows:Array.from({length:4},()=>['长任务说明'.repeat(12),.89,.9,.8,'解释'.repeat(30)])}),false)
})

export function referenceRegions(spec){
 const layouts=spec.designSystem?.referenceLayouts??{}
 const boxes=layouts[spec.role]??(!['cover','data','comparison','method','architecture','evidence'].includes(spec.role)?layouts.content:null)
 if(!Array.isArray(boxes)||boxes.length<2||boxes.length>8)return null
 if(boxes.some(box=>!['x','y','w','h','fontSize'].every(key=>Number.isFinite(box[key]))||box.x<0||box.y<0||box.w<=0||box.h<=0||box.x+box.w>1.001||box.y+box.h>1.001))return null
 const points=[...(spec.content?.bullets??[])]
 if(spec.message&&!points.includes(spec.message)&&spec.message!==spec.content?.title)points.unshift(spec.message)
 const regions=boxes.map((box,index)=>({...box,text:index===0?String(spec.content?.title??''):[],title:index===0}))
 points.forEach((point,index)=>regions[1+index%(regions.length-1)].text.push(String(point)))
 return regions.map(region=>({...region,text:Array.isArray(region.text)?region.text.join('\n\n'):region.text}))
}

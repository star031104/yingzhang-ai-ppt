// Compact audience citations; detailed references remain intact in speaker notes.
export function sourceLabel(spec,detailed=false){
 const refs=spec.sourceRefs??[]
 if(detailed)return [...new Map(refs.map(r=>[`${r.document}|${r.section??''}|${r.page??''}`,`${r.document}${r.section?' · '+r.section:''}${r.page?' · 第'+r.page+'页':''}`])).values()].join(' ｜ ')
 const groups=new Map()
 for(const ref of refs){
  if(!groups.has(ref.document))groups.set(ref.document,new Set())
  if(ref.page)groups.get(ref.document).add(Number(ref.page))
 }
 return [...groups].map(([name,values])=>{
  const pages=[...values].sort((a,b)=>a-b),ranges=[]
  for(let i=0;i<pages.length;i++){
   const start=pages[i];let end=start
   while(i+1<pages.length&&pages[i+1]===end+1)end=pages[++i]
   ranges.push(start===end?`${start}`:`${start}–${end}`)
  }
  return `${name}${ranges.length?' · 第'+ranges.join('、')+'页':''}`
 }).join(' ｜ ')
}

function rgba(value){
 const match=String(value??'').match(/^rgba?\(([^)]+)\)$/)
 if(!match)return null
 const parts=match[1].split(/[,\s/]+/).map(Number)
 return parts.length>=3&&parts.every(Number.isFinite)?[...parts.slice(0,3),parts[3]??1]:null
}
const blend=(front,back)=>front.slice(0,3).map((value,i)=>value*front[3]+back[i]*(1-front[3]))
const luminance=color=>color.map(value=>{const c=value/255;return c<=.04045?c/12.92:((c+.055)/1.055)**2.4}).reduce((sum,value,i)=>sum+value*[.2126,.7152,.0722][i],0)

// Solid-color estimate. Raster images and gradients still require visual review.
export function textContrast(node){
 const foreground=rgba(node.style?.color),stack=node.style?.backgroundStack
 if(!foreground||!Array.isArray(stack))return null
 let background=[255,255,255]
 for(const value of [...stack].reverse()){
  const color=rgba(value)
  if(color)background=blend(color,background)
 }
 const fg=luminance(blend(foreground,background)),bg=luminance(background)
 return (Math.max(fg,bg)+.05)/(Math.min(fg,bg)+.05)
}

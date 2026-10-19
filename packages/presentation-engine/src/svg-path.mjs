// Minimal SVG path parser that converts every command to absolute moveTo,
// lineTo and cubic Bézier segments. Arcs are approximated with cubic curves,
// so icons and diagram strokes can become editable PowerPoint freeforms.

const ARG_COUNTS={M:2,L:2,H:1,V:1,C:6,S:4,Q:4,T:2,A:7,Z:0}

function tokenize(d){
 const tokens=[],pattern=/([MLHVCSQTAZmlhvcsqtaz])|(-?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)/g
 let match
 while((match=pattern.exec(String(d??'')))){tokens.push(match[1]??Number(match[2]))}
 return tokens
}

function arcToCubic(x1,y1,rx,ry,angle,largeArc,sweep,x2,y2){
 if(!rx||!ry)return [[x1,y1,x2,y2,x2,y2]]
 const phi=angle*Math.PI/180,cos=Math.cos(phi),sin=Math.sin(phi)
 const dx=(x1-x2)/2,dy=(y1-y2)/2
 const x1p=cos*dx+sin*dy,y1p=-sin*dx+cos*dy
 rx=Math.abs(rx);ry=Math.abs(ry)
 const lambda=x1p*x1p/(rx*rx)+y1p*y1p/(ry*ry)
 if(lambda>1){rx*=Math.sqrt(lambda);ry*=Math.sqrt(lambda)}
 const sign=largeArc===sweep?-1:1
 const numerator=rx*rx*ry*ry-rx*rx*y1p*y1p-ry*ry*x1p*x1p
 const coef=sign*Math.sqrt(Math.max(0,numerator/(rx*rx*y1p*y1p+ry*ry*x1p*x1p)))
 const cxp=coef*rx*y1p/ry,cyp=-coef*ry*x1p/rx
 const cx=cos*cxp-sin*cyp+(x1+x2)/2,cy=sin*cxp+cos*cyp+(y1+y2)/2
 const vectorAngle=(ux,uy,vx,vy)=>{
  const dot=ux*vx+uy*vy,len=Math.hypot(ux,uy)*Math.hypot(vx,vy)
  const value=Math.acos(Math.max(-1,Math.min(1,dot/len)))
  return (ux*vy-uy*vx<0?-1:1)*value
 }
 let theta=vectorAngle(1,0,(x1p-cxp)/rx,(y1p-cyp)/ry)
 let delta=vectorAngle((x1p-cxp)/rx,(y1p-cyp)/ry,(-x1p-cxp)/rx,(-y1p-cyp)/ry)
 if(!sweep&&delta>0)delta-=2*Math.PI
 if(sweep&&delta<0)delta+=2*Math.PI
 const segments=Math.max(1,Math.ceil(Math.abs(delta)/(Math.PI/2))),step=delta/segments
 const curves=[]
 for(let i=0;i<segments;i++){
  const a1=theta+i*step,a2=a1+step,k=4/3*Math.tan(step/4)
  const p=(a)=>[Math.cos(a),Math.sin(a)]
  const [c1,s1]=p(a1),[c2,s2]=p(a2)
  const points=[[c1-k*s1,s1+k*c1],[c2+k*s2,s2-k*c2],[c2,s2]].map(([ux,uy])=>{
   const x=ux*rx,y=uy*ry
   return [cos*x-sin*y+cx,sin*x+cos*y+cy]
  })
  curves.push(points.flat())
 }
 return curves
}

// Returns subpaths: [{closed, segments:[{type:'M'|'L'|'C', points:[x,y,...]}]}]
export function parsePath(d){
 const tokens=tokenize(d),subpaths=[]
 let i=0,command=null,x=0,y=0,startX=0,startY=0,lastControl=null,lastQuad=null,current=null
 const begin=(px,py)=>{current={closed:false,segments:[{type:'M',points:[px,py]}]};subpaths.push(current)}
 while(i<tokens.length){
  if(typeof tokens[i]==='string'){command=tokens[i++]}
  else if(!command)throw new Error('SVG path must start with a command')
  const upper=command.toUpperCase(),relative=command!==upper,count=ARG_COUNTS[upper]
  if(count===undefined)throw new Error(`Unsupported SVG path command ${command}`)
  if(upper==='Z'){
   if(current){current.closed=true}
   x=startX;y=startY;lastControl=lastQuad=null
   command=null
   continue
  }
  const args=tokens.slice(i,i+count)
  if(args.length<count||args.some(value=>typeof value!=='number'))throw new Error('Malformed SVG path')
  i+=count
  const ox=relative?x:0,oy=relative?y:0
  if(upper==='M'){
   x=args[0]+ox;y=args[1]+oy;startX=x;startY=y;begin(x,y);lastControl=lastQuad=null
   command=relative?'l':'L';continue
  }
  if(!current)begin(x,y)
  if(upper==='L'||upper==='H'||upper==='V'){
   if(upper==='L'){x=args[0]+ox;y=args[1]+oy}
   else if(upper==='H')x=args[0]+(relative?x:0)
   else y=args[0]+(relative?y:0)
   current.segments.push({type:'L',points:[x,y]});lastControl=lastQuad=null;continue
  }
  if(upper==='C'||upper==='S'){
   let c1x,c1y,c2x,c2y,ex,ey
   if(upper==='C'){[c1x,c1y,c2x,c2y,ex,ey]=[args[0]+ox,args[1]+oy,args[2]+ox,args[3]+oy,args[4]+ox,args[5]+oy]}
   else{
    c1x=lastControl?2*x-lastControl[0]:x;c1y=lastControl?2*y-lastControl[1]:y
    ;[c2x,c2y,ex,ey]=[args[0]+ox,args[1]+oy,args[2]+ox,args[3]+oy]
   }
   current.segments.push({type:'C',points:[c1x,c1y,c2x,c2y,ex,ey]})
   lastControl=[c2x,c2y];lastQuad=null;x=ex;y=ey;continue
  }
  if(upper==='Q'||upper==='T'){
   let qx,qy,ex,ey
   if(upper==='Q'){[qx,qy,ex,ey]=[args[0]+ox,args[1]+oy,args[2]+ox,args[3]+oy]}
   else{qx=lastQuad?2*x-lastQuad[0]:x;qy=lastQuad?2*y-lastQuad[1]:y;[ex,ey]=[args[0]+ox,args[1]+oy]}
   current.segments.push({type:'C',points:[x+2/3*(qx-x),y+2/3*(qy-y),ex+2/3*(qx-ex),ey+2/3*(qy-ey),ex,ey]})
   lastQuad=[qx,qy];lastControl=null;x=ex;y=ey;continue
  }
  if(upper==='A'){
   const ex=args[5]+ox,ey=args[6]+oy
   for(const curve of arcToCubic(x,y,args[0],args[1],args[2],args[3]?1:0,args[4]?1:0,ex,ey))current.segments.push({type:'C',points:curve})
   x=ex;y=ey;lastControl=lastQuad=null
  }
 }
 return subpaths
}

export function transformSubpaths(subpaths,[a,b,c,d,e,f]){
 return subpaths.map(path=>({closed:path.closed,segments:path.segments.map(segment=>{
  const points=[]
  for(let i=0;i<segment.points.length;i+=2){
   const px=segment.points[i],py=segment.points[i+1]
   points.push(a*px+c*py+e,b*px+d*py+f)
  }
  return {type:segment.type,points}
 })}))
}

export function pathBounds(subpaths){
 let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity
 for(const path of subpaths)for(const segment of path.segments)for(let i=0;i<segment.points.length;i+=2){
  minX=Math.min(minX,segment.points[i]);maxX=Math.max(maxX,segment.points[i])
  minY=Math.min(minY,segment.points[i+1]);maxY=Math.max(maxY,segment.points[i+1])
 }
 return Number.isFinite(minX)?{x:minX,y:minY,w:maxX-minX,h:maxY-minY}:null
}

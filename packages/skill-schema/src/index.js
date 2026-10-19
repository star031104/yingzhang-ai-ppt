export function validateSkillManifest(value){for(const field of ['id','version','kind'])if(!value?.[field])throw new Error(`Missing ${field}`);if(value.permissions?.executeScripts!==true&&value.scripts?.length)throw new Error('Scripts require executeScripts permission');return value}

// Visual grammar carried by a visual skill's tokens.json. Every field is
// optional: tokens written before the grammar existed stay valid and simply
// produce no grammar. Keep in sync with apps/api/app/presentation_intelligence/visual_grammar.py.
export const GRAMMAR_FIELDS=['grid','typeScale','density','decoration','titleStyle','chartStyle','iconStyle','forbidden']
export const DENSITIES=['compact','balanced','airy']
export const MOTIFS=['orb','glow','rule','corner','grid-lines','quote-mark','seal','band','dots','frame']
export const TITLE_ACCENTS=['none','bar','underline','kicker','numeral']
export const FORBIDDEN_PATTERNS=['gradient','shadow','orb','rounded-card','dark-card','icons','centered-body','all-caps','serif-title','glow','decorative-quote']
export const PALETTE_KEYS=['primary','accent','deep','ink','line','bg','muted']
const TYPE_RANGES={display:[36,104],title:[26,68],subtitle:[15,36],body:[14,28],caption:[9,16]}

const isObject=value=>value&&typeof value==='object'&&!Array.isArray(value)
const inRange=(value,[min,max])=>Number.isFinite(value)&&value>=min&&value<=max

export function validateVisualTokens(tokens,{strict=false}={}){
 const errors=[],grammar={}
 const fail=message=>errors.push(message)
 if(!isObject(tokens)){if(strict)throw new Error('tokens.json must be an object');return {grammar:null,errors:['tokens.json must be an object']}}
 if(tokens.grid!==undefined){
  const grid=tokens.grid,margin=isObject(grid?.margin)?grid.margin:{x:grid?.margin,top:grid?.margin,bottom:grid?.margin}
  const value={columns:Number(grid?.columns),margin:{x:Number(margin.x),top:Number(margin.top??margin.x),bottom:Number(margin.bottom??margin.x)},gutter:Number(grid?.gutter)}
  if(!Number.isInteger(value.columns)||!inRange(value.columns,[4,16]))fail('grid.columns must be an integer between 4 and 16')
  else if(!inRange(value.margin.x,[32,140])||!inRange(value.margin.top,[24,120])||!inRange(value.margin.bottom,[24,100]))fail('grid.margin is outside the safe slide area')
  else if(!inRange(value.gutter,[8,64]))fail('grid.gutter must be between 8 and 64 px')
  else grammar.grid=value
 }
 if(tokens.typeScale!==undefined){
  const scale=tokens.typeScale,value={}
  for(const [key,range] of Object.entries(TYPE_RANGES)){
   const size=Number(scale?.[key])
   if(!inRange(size,range))fail(`typeScale.${key} must be between ${range[0]} and ${range[1]} px`)
   else value[key]=size
  }
  const order=['display','title','subtitle','body','caption']
  if(Object.keys(value).length===5&&order.some((key,index)=>index&&value[key]>value[order[index-1]]))fail('typeScale must descend from display to caption')
  else if(Object.keys(value).length===5)grammar.typeScale=value
 }
 if(tokens.density!==undefined){if(DENSITIES.includes(tokens.density))grammar.density=tokens.density;else fail(`density must be one of ${DENSITIES.join(', ')}`)}
 if(tokens.decoration!==undefined){
  const motifs=tokens.decoration?.motifs??[],intensity=tokens.decoration?.intensity??'subtle'
  if(!Array.isArray(motifs)||motifs.some(motif=>!MOTIFS.includes(motif)))fail(`decoration.motifs must use ${MOTIFS.join(', ')}`)
  else if(!['none','subtle','bold'].includes(intensity))fail('decoration.intensity must be none, subtle or bold')
  else grammar.decoration={motifs:[...new Set(motifs)],intensity}
 }
 if(tokens.titleStyle!==undefined){
  const style=tokens.titleStyle??{},value={align:style.align??'left',weight:Number(style.weight??800),tracking:Number(style.tracking??-0.03),
   case:style.case??'none',font:style.font??'sans',accent:style.accent??'none'}
  if(!['left','center'].includes(value.align))fail('titleStyle.align must be left or center')
  else if(!inRange(value.weight,[300,900]))fail('titleStyle.weight must be between 300 and 900')
  else if(!inRange(value.tracking,[-0.08,0.2]))fail('titleStyle.tracking must be between -0.08 and 0.2 em')
  else if(!['none','upper'].includes(value.case))fail('titleStyle.case must be none or upper')
  else if(!['sans','serif'].includes(value.font))fail('titleStyle.font must be sans or serif')
  else if(!TITLE_ACCENTS.includes(value.accent))fail(`titleStyle.accent must be one of ${TITLE_ACCENTS.join(', ')}`)
  else grammar.titleStyle=value
 }
 if(tokens.chartStyle!==undefined){
  const style=tokens.chartStyle??{},palette=style.palette??['primary','accent','deep','muted']
  const value={palette,gridlines:style.gridlines??'horizontal',dataLabels:style.dataLabels!==false,barRadius:Number(style.barRadius??2)}
  if(!Array.isArray(palette)||palette.length<2||palette.length>8||palette.some(item=>!PALETTE_KEYS.includes(item)&&!/^#[0-9a-f]{6}$/i.test(String(item))))fail('chartStyle.palette must list 2-8 palette keys or #RRGGBB colours')
  else if(!['none','horizontal','both'].includes(value.gridlines))fail('chartStyle.gridlines must be none, horizontal or both')
  else if(!inRange(value.barRadius,[0,12]))fail('chartStyle.barRadius must be between 0 and 12')
  else grammar.chartStyle=value
 }
 if(tokens.iconStyle!==undefined){
  const style=tokens.iconStyle??{},value={use:style.use!==false,stroke:Number(style.stroke??1.75),container:style.container??'none'}
  if(!inRange(value.stroke,[1,2.5]))fail('iconStyle.stroke must be between 1 and 2.5')
  else if(!['none','circle','square'].includes(value.container))fail('iconStyle.container must be none, circle or square')
  else grammar.iconStyle=value
 }
 if(tokens.forbidden!==undefined){
  if(!Array.isArray(tokens.forbidden)||tokens.forbidden.some(item=>!FORBIDDEN_PATTERNS.includes(item)))fail(`forbidden must list ${FORBIDDEN_PATTERNS.join(', ')}`)
  else grammar.forbidden=[...new Set(tokens.forbidden)]
 }
 if(grammar.decoration&&grammar.forbidden)grammar.decoration.motifs=grammar.decoration.motifs.filter(motif=>!grammar.forbidden.includes(motif))
 if(strict&&errors.length)throw new Error(errors.join('; '))
 return {grammar:Object.keys(grammar).length?{version:'visual-grammar-v1',...grammar}:null,errors}
}

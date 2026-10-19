// Applies a visual skill's layout grammar to the HTML candidate. Every rule is
// scoped to `.has-grammar` (and finer flags), so decks without a grammar keep
// their established rendering. The PPTX scene compiler measures the result, so
// PowerPoint inherits the same grid, type scale and decoration choices.
import {validateVisualTokens} from '../../skill-schema/src/index.js'

const DENSITY_MAIN={compact:30,balanced:42,airy:54}
const DENSITY_GAP={compact:.8,balanced:1,airy:1.25}

export function grammarFor(spec){
 const raw=spec?.designSystem?.grammar
 if(!raw||typeof raw!=='object')return null
 return validateVisualTokens(raw).grammar
}

export const forbids=(grammar,pattern)=>Boolean(grammar?.forbidden?.includes(pattern))
export const hasMotif=(grammar,motif)=>Boolean(grammar?.decoration?.motifs?.includes(motif))&&grammar.decoration.intensity!=='none'
export const iconsAllowed=grammar=>!forbids(grammar,'icons')&&grammar?.iconStyle?.use!==false

export function grammarVars(grammar){
 if(!grammar)return ''
 const vars=[]
 const grid=grammar.grid,scale=grammar.typeScale,title=grammar.titleStyle
 if(grid)vars.push(`--g-x:${grid.margin.x}px`,`--g-top:${grid.margin.top}px`,`--g-bottom:${grid.margin.bottom}px`,`--gutter:${grid.gutter}px`)
 const density=grammar.density??'balanced'
 vars.push(`--g-main:${DENSITY_MAIN[density]}px`,`--g-gap-scale:${DENSITY_GAP[density]}`)
 if(scale)vars.push(`--fs-display:${scale.display}px`,`--fs-title:${scale.title}px`,`--fs-subtitle:${scale.subtitle}px`,`--fs-body:${scale.body}px`,`--fs-caption:${scale.caption}px`,`--title-ratio:${Math.round(scale.title/52*1000)/1000}`)
 if(title)vars.push(`--title-weight:${title.weight}`,`--title-tracking:${title.tracking}em`)
 return vars.join(';')
}

export function grammarClasses(grammar){
 if(!grammar)return ''
 const classes=['has-grammar',`density-${grammar.density??'balanced'}`]
 if(grammar.grid)classes.push('has-grid')
 if(grammar.typeScale)classes.push('has-type-scale')
 if(grammar.titleStyle){
  classes.push('has-title-style',`title-${grammar.titleStyle.align}`,`title-accent-${grammar.titleStyle.accent}`,`title-font-${grammar.titleStyle.font}`)
  if(grammar.titleStyle.case==='upper')classes.push('title-upper')
 }
 for(const motif of grammar.decoration?.motifs??[])if(hasMotif(grammar,motif))classes.push(`motif-${motif}`)
 if(grammar.decoration?.intensity)classes.push(`motifs-${grammar.decoration.intensity}`)
 for(const pattern of grammar.forbidden??[])classes.push(`no-${pattern}`)
 if(grammar.iconStyle?.container&&grammar.iconStyle.container!=='none')classes.push(`icon-${grammar.iconStyle.container}`)
 return classes.join(' ')
}

// Decorative layers are real, absolutely positioned elements behind content,
// so they are measured and exported as editable shapes.
export function decorations(grammar,{dark=false}={}){
 if(!grammar)return ''
 const layers=[]
 const columns=grammar.grid?.columns??12
 if(hasMotif(grammar,'grid-lines'))layers.push(`<div class="deco deco-grid" aria-hidden="true">${Array.from({length:columns-1},(_,index)=>`<i style="left:${((index+1)/columns*100).toFixed(3)}%"></i>`).join('')}</div>`)
 if(hasMotif(grammar,'band'))layers.push('<div class="deco deco-band" aria-hidden="true"></div>')
 if(hasMotif(grammar,'frame'))layers.push('<div class="deco deco-frame" aria-hidden="true"></div>')
 if(hasMotif(grammar,'corner'))layers.push('<div class="deco deco-corner tr" aria-hidden="true"></div><div class="deco deco-corner bl" aria-hidden="true"></div>')
 if(hasMotif(grammar,'seal'))layers.push('<div class="deco deco-seal" aria-hidden="true"><i></i></div>')
 if(hasMotif(grammar,'dots'))layers.push(`<div class="deco deco-dots" aria-hidden="true">${Array.from({length:15},()=>'<i></i>').join('')}</div>`)
 if(hasMotif(grammar,'glow')&&!forbids(grammar,'gradient'))layers.push(`<div class="deco deco-glow${dark?' on-dark':''}" aria-hidden="true"></div>`)
 return layers.join('')
}

const DARK=':is(.agenda-card:first-child,.problem-card:nth-child(2),.flow-node:nth-of-type(3),.metric-card.focus,.insight-card.dark,.conclusion-card:nth-child(2),.summary-grid article.lead,.split-grid aside,.comparison-columns.narrative article.active,.problem-thesis,.problem-metric,.hero-metric,.image-points>strong,.media-points>strong,.source-analysis-notes>strong,.source-focus aside,.hub-map>strong,.problem-sequence article:nth-of-type(3),.stage-flow .flow-node:nth-of-type(3),.chart-message,.typography-story)'

export const grammarStyles=`
.slide.has-grammar{z-index:0}
.slide.has-grammar.has-grid{padding:var(--g-top) var(--g-x) var(--g-bottom)}
.slide.has-grammar.has-grid footer{left:var(--g-x);right:var(--g-x)}
.slide.has-grammar:not(.cover):not(.section-divider) main{margin-top:var(--g-main)}
.slide.has-grammar.has-grid main :is(.problem-grid,.metric-grid,.insight-grid,.agenda-grid,.summary-grid,.comparison-columns,.conclusion-grid,.background-grid,.split-grid,.image-story,.media-story,.evidence-brief,.problem-contrast,.problem-focus,.complete-columns){column-gap:calc(var(--gutter) * var(--g-gap-scale))}
.slide.has-grammar.has-grid main .flow{gap:calc(var(--gutter) * var(--g-gap-scale))}
.slide.has-grammar.has-type-scale>h1{font-size:var(--fs-title)}
.slide.has-grammar.has-type-scale.variant-evidence-brief>h1{font-size:calc(44px * var(--title-ratio))}
.slide.has-grammar.has-type-scale.variant-content-list>h1{font-size:calc(42px * var(--title-ratio))}
.slide.has-grammar.has-type-scale.cover>h1,.slide.has-grammar.has-type-scale.section-divider>h1{font-size:var(--fs-display)}
.slide.has-grammar.has-type-scale.questions>h1{font-size:calc(var(--fs-display) * 1.2)}
.slide.has-grammar.has-type-scale.cover .lead,.slide.has-grammar.has-type-scale.section-divider>p{font-size:var(--fs-subtitle)}
.slide.has-grammar.has-type-scale :is(.split-grid li,.brief-points p,.agenda-list p){font-size:var(--fs-body)}
.slide.has-grammar.has-type-scale footer{font-size:var(--fs-caption)}
.slide.has-grammar.has-type-scale header span{font-size:calc(var(--fs-caption) + 3px)}
.slide.has-grammar.has-title-style>h1{font-weight:var(--title-weight);letter-spacing:var(--title-tracking);position:relative}
.slide.has-grammar.title-center:not(.cover):not(.section-divider):not(.questions)>h1{text-align:center;margin-left:auto;margin-right:auto}
.slide.has-grammar.title-font-serif>h1{font-family:"Noto Serif SC","Songti SC",serif}
.slide.has-grammar.title-upper>h1{text-transform:uppercase}
.slide.has-grammar.title-accent-bar:not(.cover):not(.section-divider)>h1:before{content:"";position:absolute;left:0;top:-16px;width:44px;height:5px;background:var(--primary)}
.slide.has-grammar.title-accent-bar.title-center:not(.cover):not(.section-divider)>h1:before{left:calc(50% - 22px)}
.slide.has-grammar.title-accent-underline:not(.cover):not(.section-divider)>h1:after{content:"";position:absolute;left:0;bottom:-14px;width:72px;height:3px;background:var(--accent)}
.slide.has-grammar.title-accent-underline.title-center:not(.cover):not(.section-divider)>h1:after{left:calc(50% - 36px)}
.slide.has-grammar.title-accent-kicker header span{border-left:4px solid var(--accent);padding-left:10px}
.slide.has-grammar.title-accent-numeral:not(.cover):not(.section-divider) header>i{position:absolute;right:var(--g-x,68px);top:calc(var(--g-top,52px) - 14px);font-size:34px;font-weight:800;color:var(--line);letter-spacing:-.02em}
.slide.has-grammar.motif-rule:not(.cover):not(.section-divider):not(.title-accent-underline)>h1:after{content:"";position:absolute;left:0;bottom:-12px;width:56px;height:3px;background:var(--accent)}
.slide.has-grammar:not(.motif-orb) :is(.orb,.section-orb){display:none}
.slide.has-grammar:not(.motif-quote-mark) .quote-mark{display:none}
.slide.has-grammar:not(.motif-grid-lines).profile-data-consulting{background-image:none}
.slide.has-grammar.profile-nebula-tech:not(.cover):after{display:none}
.deco{position:absolute;pointer-events:none;z-index:-1}
.deco-grid{left:var(--g-x,68px);right:var(--g-x,68px);top:0;bottom:0}
.deco-grid i{position:absolute;top:0;bottom:0;width:1px;background:var(--line);opacity:.55}
.deco-band{left:0;top:0;bottom:0;width:10px;background:var(--primary)}
.deco-frame{inset:20px;border:1px solid var(--line)}
.deco-corner{width:44px;height:44px;border-color:var(--primary);border-style:solid;border-width:0}
.deco-corner.tr{right:26px;top:24px;border-top-width:3px;border-right-width:3px}
.deco-corner.bl{left:26px;bottom:24px;border-bottom-width:3px;border-left-width:3px}
.deco-seal{right:22px;bottom:18px;width:38px;height:38px;border:2.5px solid var(--primary);border-radius:5px;opacity:.85}
.deco-seal i{position:absolute;inset:6px;border:1.5px solid var(--primary);border-radius:2px}
.deco-dots{right:116px;top:18px;width:96px;display:grid;grid-template-columns:repeat(5,1fr);row-gap:12px;opacity:.55}
.deco-dots i{width:5px;height:5px;border-radius:50%;background:var(--primary)}
.deco-glow{right:-160px;top:-200px;width:560px;height:560px;border-radius:50%;background:radial-gradient(circle,var(--primary),rgba(255,255,255,0) 70%);opacity:.18}
.deco-glow.on-dark{opacity:.45}
.motifs-subtle .deco-grid i{opacity:.4}
.slide.has-grammar.no-gradient,.slide.has-grammar.no-gradient *{background-image:none!important}
.slide.has-grammar.no-gradient .typography-story{background-color:var(--deep)}
.slide.has-grammar.no-gradient .agenda-track{background-color:var(--primary)}
.slide.has-grammar.no-gradient .single-metric-row>div i{background-color:var(--primary)}
.slide.has-grammar.no-shadow *{box-shadow:none!important}
.slide.has-grammar.no-orb :is(.orb,.section-orb){display:none}
.slide.has-grammar.no-rounded-card main :is(article,aside,figure,.flow-node,.future,.chart-message,.data-table-wrap,.typography-story,.problem-thesis,.hub-map>strong,.brief-lead,.complete-takeaway){border-radius:0!important}
.slide.has-grammar.no-dark-card main ${DARK}{background:#fff!important;color:var(--ink)!important;border:1px solid var(--line)!important}
.slide.has-grammar.no-dark-card main ${DARK} :is(b,small,span,strong,p,h3){color:var(--ink)!important}
.slide.has-grammar.no-dark-card main ${DARK} :is(b,small){color:var(--primary)!important}
.slide.has-grammar.no-dark-card main .chart-message{color:var(--primary)!important}
.slide.has-grammar.no-centered-body main :is(p,strong,h3,span){text-align:left!important}
.slide.has-grammar.no-all-caps *{text-transform:none!important}
.slide.has-grammar.no-serif-title h1{font-family:var(--font-family),"Microsoft YaHei",sans-serif!important}
.slide.has-grammar.no-decorative-quote .quote-mark{display:none}
.yz-icon-wrap{display:inline-flex;align-items:center;justify-content:center;color:var(--primary);line-height:0;font-style:normal}
.yz-icon-wrap svg{display:block}
.flow-node,.problem-card,.summary-grid article,.note-card{position:relative}
.flow-node>.yz-icon-wrap,.problem-card>.yz-icon-wrap,.summary-grid article>.yz-icon-wrap{position:absolute;right:22px;top:22px}
.note-card>.yz-icon-wrap{position:absolute;right:18px;top:50%;margin-top:-13px}
.note-card:has(>.yz-icon-wrap){padding-right:56px}
.flow-node:nth-of-type(3)>.yz-icon-wrap,.problem-card:nth-child(2)>.yz-icon-wrap,.summary-grid article.lead>.yz-icon-wrap,.agenda-card:first-child .yz-icon-wrap{color:var(--accent)}
.agenda-card>b,.agenda-list article>b{display:flex;flex-direction:column;gap:8px;align-items:flex-start}
.slide.icon-circle .yz-icon-wrap,.slide.icon-square .yz-icon-wrap{padding:7px;border:1.5px solid currentColor}
.slide.icon-circle .yz-icon-wrap{border-radius:50%}
.slide.icon-square .yz-icon-wrap{border-radius:6px}
.slide.has-grammar.no-dark-card .yz-icon-wrap{color:var(--primary)!important}
`

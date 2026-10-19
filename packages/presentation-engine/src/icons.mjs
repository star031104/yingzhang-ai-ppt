// 映章 built-in icon set: original 24×24 stroke icons drawn for this project
// (no third-party artwork). Every icon uses only line, circle, rect, polyline
// and path primitives so the PPTX compiler can rebuild it as editable shapes.
import {escapeHtml} from './utils.mjs'

const I=(keywords,body)=>({keywords,body})
export const ICONS={
 target:I(['目标','靶心','聚焦','定位','goal','target','objective','aim','focus'],'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>'),
 'bar-chart':I(['数据','指标','统计','图表','结果','data','metric','chart','statistics','kpi'],'<path d="M4 20h16"/><rect x="5.5" y="11" width="3" height="6" rx=".5"/><rect x="10.5" y="7" width="3" height="10" rx=".5"/><rect x="15.5" y="4" width="3" height="13" rx=".5"/>'),
 'trend-up':I(['增长','提升','上升','提高','增加','growth','increase','rise','improve','up'],'<polyline points="3 17 9 11 13 15 21 7"/><polyline points="15 7 21 7 21 13"/>'),
 'trend-down':I(['下降','降低','减少','缩短','节省','decline','decrease','reduce','drop','down'],'<polyline points="3 7 9 13 13 9 21 17"/><polyline points="15 17 21 17 21 11"/>'),
 search:I(['检索','搜索','查找','调研','发现','search','find','query','research','discover'],'<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L20.5 20.5"/>'),
 document:I(['文档','报告','材料','论文','文件','来源','document','report','file','paper','source'],'<path d="M6 3h8l4 4v14H6z"/><polyline points="14 3 14 7 18 7"/><path d="M9 12h6M9 16h6"/>'),
 database:I(['数据库','存储','知识库','数据集','database','storage','dataset','repository'],'<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6"/><path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>'),
 layers:I(['架构','分层','层级','体系','平台','architecture','layer','stack','framework','system'],'<polygon points="12 3 21 8 12 13 3 8"/><polyline points="3 12.5 12 17.5 21 12.5"/><polyline points="3 17 12 22 21 17"/>'),
 workflow:I(['流程','步骤','路径','管线','过程','process','workflow','pipeline','step','path'],'<rect x="3" y="4" width="6" height="6" rx="1.5"/><rect x="15" y="14" width="6" height="6" rx="1.5"/><path d="M9 7h4a2 2 0 0 1 2 2v5"/><polyline points="13 12 15 14 17 12"/>'),
 users:I(['用户','团队','客户','人员','受众','成员','users','team','people','customer','audience'],'<circle cx="9" cy="8" r="3.5"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><circle cx="17" cy="9" r="2.5"/><path d="M16 14.2c2.9.4 5 2.7 5 5.8"/>'),
 user:I(['个人','负责人','专家','person','owner','expert','individual'],'<circle cx="12" cy="8" r="4"/><path d="M4.5 21c0-4.1 3.4-7.5 7.5-7.5s7.5 3.4 7.5 7.5"/>'),
 shield:I(['安全','合规','保障','防护','可信','security','compliance','protect','trust','safe'],'<path d="M12 3l7.5 3v5.5c0 4.6-3.2 8.2-7.5 9.5-4.3-1.3-7.5-4.9-7.5-9.5V6z"/><polyline points="8.5 12 11 14.5 15.5 9.5"/>'),
 check:I(['完成','验证','通过','结论','达成','确认','done','verified','pass','complete','confirm'],'<circle cx="12" cy="12" r="9"/><polyline points="7.5 12.5 10.5 15.5 16.5 9"/>'),
 alert:I(['问题','风险','警告','挑战','痛点','缺陷','issue','risk','warning','problem','challenge','pain'],'<path d="M12 3.5L21.5 20h-19z"/><path d="M12 10v4.5"/><circle cx="12" cy="17.3" r=".6"/>'),
 lightbulb:I(['洞察','创新','想法','启示','发现','insight','idea','innovation','inspiration'],'<path d="M9 18h6M10 21h4"/><path d="M8.5 14.5A6 6 0 1 1 15.5 14.5c-.9.8-1.5 1.8-1.5 3h-4c0-1.2-.6-2.2-1.5-3z"/>'),
 sliders:I(['方法','机制','设置','配置','引擎','method','mechanism','settings','configure','engine'],'<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>'),
 clock:I(['时间','效率','耗时','时长','速度','实时','time','efficiency','duration','speed','realtime'],'<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15.5 14"/>'),
 calendar:I(['计划','日程','安排','排期','时间线','季度','plan','schedule','timeline','calendar','quarter'],'<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/><path d="M8 14h3"/>'),
 coin:I(['成本','收入','预算','资金','利润','价格','费用','cost','revenue','budget','profit','price','finance'],'<circle cx="12" cy="12" r="9"/><path d="M15 8.5h-4.2a2 2 0 0 0 0 4h2.4a2 2 0 0 1 0 4H9"/><path d="M12 6.5v2M12 16.5v2"/>'),
 cart:I(['销售','购买','订单','电商','零售','sales','purchase','order','commerce','retail'],'<path d="M3 4h2.5l2.2 10.5h10.3L20 7.5H6.4"/><circle cx="9.5" cy="19" r="1.5"/><circle cx="16.5" cy="19" r="1.5"/>'),
 globe:I(['全球','市场','国际','海外','开放','global','market','international','world'],'<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.5 2.5 3.8 5.5 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.5-3.8-9S9.5 5.5 12 3z"/>'),
 link:I(['关联','连接','证据链','引用','绑定','link','connect','relation','reference','bind'],'<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>'),
 book:I(['学习','教育','研究','课程','知识','教学','learning','education','study','course','knowledge'],'<path d="M4 5.5C6.5 4 9.5 4 12 6c2.5-2 5.5-2 8-.5V19c-2.5-1.5-5.5-1.5-8 .5-2.5-2-5.5-2-8-.5z"/><path d="M12 6v13.5"/>'),
 academic:I(['学术','答辩','论文','毕业','学位','科研','academic','thesis','defense','degree','scholar'],'<polygon points="12 4 22 9 12 14 2 9"/><path d="M6 11v4.5c1.7 1.6 3.7 2.5 6 2.5s4.3-.9 6-2.5V11"/><path d="M22 9v5"/>'),
 message:I(['沟通','反馈','交流','对话','咨询','communication','feedback','chat','dialogue','consult'],'<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9.5h8M8 12.5h5"/>'),
 lock:I(['隐私','权限','保密','加密','privacy','permission','confidential','encrypt'],'<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/><path d="M12 14.5v2.5"/>'),
 rocket:I(['发布','启动','上线','加速','突破','launch','start','release','accelerate'],'<path d="M12 3c3.5 2 5.5 5.5 5.5 9.5L15 16H9l-2.5-3.5C6.5 8.5 8.5 5 12 3z"/><circle cx="12" cy="9.5" r="1.8"/><path d="M9 16l-2.5 4M15 16l2.5 4M12 16v4.5"/>'),
 flag:I(['里程碑','阶段','节点','旗帜','milestone','phase','checkpoint'],'<path d="M5 21V4"/><path d="M5 4.5h11l-2 3.5 2 3.5H5"/>'),
 puzzle:I(['整合','方案','解决','模块','组件','集成','integration','solution','module','component'],'<path d="M4 8.5h4.2a2.6 2.6 0 0 1 5.2 0H17.5v4a2.6 2.6 0 0 1 0 5.2V21H4z"/>'),
 compass:I(['战略','方向','导航','愿景','strategy','direction','navigation','vision'],'<circle cx="12" cy="12" r="9"/><polygon points="15.5 8.5 13.5 13.5 8.5 15.5 10.5 10.5"/>'),
 scale:I(['对比','平衡','权衡','公平','比较','comparison','balance','tradeoff','fair','compare'],'<path d="M12 4v16M7 20h10M5 7h14"/><path d="M5 7l-2.5 6h5z"/><path d="M19 7l-2.5 6h5z"/>'),
 chip:I(['技术','模型','算法','智能','人工智能','计算','technology','model','algorithm','ai','compute'],'<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5"/><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3"/>'),
 cloud:I(['云端','云平台','平台','服务','部署','在线','cloud','platform','service','deploy','online'],'<path d="M7 18.5a4.5 4.5 0 0 1-.6-9A5.5 5.5 0 0 1 17 8.6 4 4 0 0 1 17.5 18.5z"/>'),
 building:I(['机构','企业','政府','部门','单位','组织','organization','company','government','department','agency'],'<path d="M4 21V5l8-2v18M12 8h8v13"/><path d="M3 21h18M7.5 8h1.5M7.5 12h1.5M7.5 16h1.5M15.5 12h1.5M15.5 16h1.5"/>'),
 partnership:I(['合作','伙伴','协同','签约','共建','partner','cooperation','collaborate','alliance','deal'],'<circle cx="9" cy="12" r="5.5"/><circle cx="15" cy="12" r="5.5"/>'),
 'map-pin':I(['地区','区域','位置','地点','门店','region','location','place','site','store'],'<path d="M12 21s6.5-5.5 6.5-11a6.5 6.5 0 0 0-13 0C5.5 15.5 12 21 12 21z"/><circle cx="12" cy="10" r="2.3"/>'),
 star:I(['亮点','优势','品质','核心','卓越','highlight','advantage','quality','core','excellence'],'<polygon points="12 3.5 14.6 9 20.5 9.6 16 13.6 17.3 19.5 12 16.5 6.7 19.5 8 13.6 3.5 9.6 9.4 9"/>'),
 refresh:I(['迭代','循环','复盘','优化','更新','改进','iteration','cycle','review','optimize','update'],'<path d="M20 12a8 8 0 0 1-14.3 4.9"/><path d="M4 12a8 8 0 0 1 14.3-4.9"/><polyline points="18.5 3 18.5 7.2 14.3 7.2"/><polyline points="5.5 21 5.5 16.8 9.7 16.8"/>'),
 eye:I(['观察','可视','监测','透明','洞见','observe','visibility','monitor','transparent','view'],'<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>'),
 code:I(['开发','代码','工程','程序','接口','development','code','engineering','software','api'],'<polyline points="8 7 3 12 8 17"/><polyline points="16 7 21 12 16 17"/><path d="M13.5 4.5l-3 15"/>'),
 leaf:I(['可持续','绿色','环境','环保','生态','sustainability','green','environment','esg','ecology'],'<path d="M5 19C5 10 10 5 20 4c0 9.5-5 15-12.5 15H5z"/><path d="M5 19l8-8"/>'),
 heart:I(['健康','关怀','公益','医疗','民生','health','care','charity','medical','wellbeing'],'<path d="M12 20s-8-4.8-8-10.5A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 8 2.5C20 15.2 12 20 12 20z"/>'),
 'pie-chart':I(['占比','份额','构成','比例','分布','share','composition','proportion','distribution','ratio'],'<path d="M12 3a9 9 0 1 0 9 9h-9z"/><path d="M15 3.5a9 9 0 0 1 5.5 5.5H15z"/>'),
 presentation:I(['汇报','演示','展示','简报','演讲','presentation','briefing','demo','pitch','talk'],'<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M12 16v3.5M8 21l4-1.5 4 1.5"/><polyline points="7 12 10 9 12.5 11 17 7"/>'),
}

export const ICON_NAMES=Object.keys(ICONS)

const normalize=value=>String(value??'').toLowerCase()

// Deterministic keyword match: longest keyword wins; ties resolve by icon order.
export function iconFor(text,{exclude=[]}={}){
 const haystack=normalize(text)
 let best=null
 for(const [name,icon] of Object.entries(ICONS)){
  if(exclude.includes(name))continue
  for(const keyword of icon.keywords){
   const key=normalize(keyword)
   const hit=/^[a-z]+$/.test(key)?new RegExp(`\\b${key}\\b`).test(haystack):haystack.includes(key)
   if(hit&&(!best||key.length>best.length))best={name,length:key.length}
  }
 }
 return best?.name??null
}

// One distinct icon per item; items without a confident match get none.
export function iconsForItems(items){
 const used=[]
 return items.map(item=>{
  const name=iconFor(item,{exclude:used})
  if(name)used.push(name)
  return name
 })
}

export function iconSvg(name,{size=24,stroke=1.75,label=''}={}){
 const icon=ICONS[name]
 if(!icon)return ''
 return `<svg class="yz-icon" data-icon="${name}" data-scene-type="group" viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="${stroke}" stroke-linecap="round" stroke-linejoin="round"${label?` role="img" aria-label="${escapeHtml(label)}"`:' aria-hidden="true"'}>${icon.body}</svg>`
}

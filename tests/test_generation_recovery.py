import json
import httpx
import pytest
from app.providers.openai_compatible import OpenAICompatibleClient,ProviderError
from test_image_provider import mock_transport

async def test_timed_out_task_resumes_without_another_submission(monkeypatch,tmp_path):
 calls=[]; ready=False
 def handle(request):
  calls.append(request.method)
  if request.method=='POST':return httpx.Response(200,json={'task_id':'durable'})
  if request.url.path.endswith('/tasks/durable'):
   return httpx.Response(200,json={'task_status':'SUCCEED','output_images':['https://images.example.com/a.png']} if ready else {'task_status':'RUNNING'})
  return httpx.Response(200,content=b'image')
 mock_transport(monkeypatch,handle)
 client=OpenAICompatibleClient('https://api-inference.modelscope.cn/v1','secret',{},10)
 path=tmp_path/'task.json'
 with pytest.raises(ProviderError,match='0.05'):
  await client.image_generation('Qwen/Qwen-Image','example',task_state_path=path,wait_seconds=.05)
 assert json.loads(path.read_text())['task_id']=='durable'
 ready=True
 assert await client.image_generation('Qwen/Qwen-Image','example',task_state_path=path,wait_seconds=1)==b'image'
 assert calls.count('POST')==1


def test_appendix_continuations_cannot_become_conclusions():
 from app.presentation_intelligence.planner import _section_records
 source={'name':'paper.pdf','sections':[
  {'id':'S1','title':'6.1 研究总结','text':'本文通过多源信息建模实现了研究目标。'},
  {'id':'S2','title':'参考文献','text':'参考资料'},
  {'id':'S3','title':'语鲸订阅工具','text':'总结隐私政策 https://example.com/privacy'},
 ]}
 assert [r['section']['id'] for r in _section_records([source])]==['S1']


def test_flattened_table_does_not_replace_readable_prose():
 from app.intelligence.content_selection import select_key_points
 source={'title':'控制点分析','text':'控制点来源风险值'*70+'。\n逐项判断控制点，并提供规范依据。\n但静态信息不能代表运行时行为。'}
 points=select_key_points(source)
 assert all(len(p)<=240 for p in points)
 assert '但静态信息不能代表运行时行为。' in points
 assert len(source['text'])>500


def test_short_named_metric_is_not_model_debris():
 from app.api.workflow_routes import clean_audience_bullet
 assert clean_audience_bullet('MRR：0.8812 → 0.8945')=='MRR：0.8812 → 0.8945'
 assert clean_audience_bullet('Hit@1：0.8150 → 0.8300')=='Hit@1：0.8150 → 0.8300'
 assert clean_audience_bullet('0.8812')==''


def test_figure_binding_preserves_all_fact_references(tmp_path):
 from app.presentation_intelligence.assets import bind_source_figures, _figure_score
 image=tmp_path/'figure.png';image.write_bytes(b'fixture')
 refs=[{'document':'paper','section':f'S{i}','page':i} for i in range(1,9)]
 slide={'role':'method','purpose':'处理流程','content':{'title':'处理流程'},'sourceRefs':refs.copy(),'visualIntent':{}}
 figure={'path':str(image),'document':'paper','section':'S1','page':1,'caption':'处理流程','kind':'diagram'}
 assert bind_source_figures({'slides':[slide]},[{'name':'paper','figures':[figure],'sections':[]}])==1
 assert all(ref in slide['sourceRefs'] for ref in refs)
 assert _figure_score(slide,{**figure,'page':50,'section':'S50'})<0


def test_pending_image_test_returns_accepted_not_failure(client,monkeypatch):
 from app.db.session import SessionLocal
 from app.db.models import Provider,ModelConfig
 from app.providers.openai_compatible import ImageGenerationPending
 with SessionLocal() as db:
  provider=Provider(name='fixture',base_url='https://api.example.com/v1',extra_headers={});db.add(provider);db.flush()
  model=ModelConfig(provider_id=provider.id,model_id='custom-image',capabilities=['image_generation']);db.add(model);db.commit();model_id=model.id
 async def pending(*args,**kwargs):
  assert kwargs['task_state_path'].name==f'{model_id}.task.json'
  raise ImageGenerationPending('仍在生成，请继续查询')
 monkeypatch.setattr(OpenAICompatibleClient,'image_generation',pending)
 response=client.post(f'/api/v1/models/{model_id}/test-image')
 assert response.status_code==202
 assert response.json()['status']=='pending'


def test_semantic_audit_does_not_require_bibliography_urls():
 from app.validation.quality import semantic_completeness
 sections=[{'id':'S1','title':'研究方法','text':'使用多源语义信息进行约束推理，提升分析结果的可解释性。','semanticRole':'method'},
 {'id':'S2','title':'参考文献','text':'参考资料'*20,'semanticRole':'method'},
 {'id':'S3','title':'网页链接','text':'附录中的隐私政策网址'*20,'semanticRole':'method'}]
 assert semantic_completeness([],[{'name':'paper','sections':sections}])['requiredSections']==1


def test_source_warning_group_preserves_pages():
 from types import SimpleNamespace
 from app.documents.review import source_reading_view
 row=SimpleNamespace(id='x',name='source',sha256='hash',model={'readingWarnings':[{'code':'table-text-only','page':page,'message':'table unavailable'} for page in [17,28,29]]})
 warnings=source_reading_view(row)['readingWarnings']
 assert len(warnings)==1 and warnings[0]['pages']==[17,28,29] and warnings[0]['count']==3


async def test_optional_image_failure_does_not_block_page(client,monkeypatch):
 from test_personalization import make_profile,plan
 from app.db.session import SessionLocal
 from app.db.models import Provider,ModelConfig,RoleAssignment,Project,SlideSpecRecord
 from app.api.workflow_routes import ensure_generated_images
 from app.slides import load_slides
 profile=make_profile(client);project,_=plan(client,profile)
 with SessionLocal() as db:
  p=Provider(name='synthetic',base_url='https://api.example.com/v1',extra_headers={});db.add(p);db.flush()
  m=ModelConfig(provider_id=p.id,model_id='custom-image',capabilities=['image_generation']);db.add(m);db.flush()
  db.add(RoleAssignment(role='image_generation',model_config_id=m.id));db.commit()
  async def fail(*args,**kwargs):raise ProviderError('still pending')
  monkeypatch.setattr(OpenAICompatibleClient,'image_generation',fail)
  slides=load_slides(project['id'],db)
  assert await ensure_generated_images(db.get(Project,project['id']),slides,db)==0
  assert slides[0]['imageGeneration']['status']=='deferred'
  assert db.get(SlideSpecRecord,slides[0]['id']).spec['imageGeneration']['message']=='still pending'

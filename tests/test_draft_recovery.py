import json
import httpx
import pymupdf
from app.intelligence.content_selection import source_sentences
from app.documents.parser import _aligned_metric_tables
from app.providers.openai_compatible import OpenAICompatibleClient
from test_image_provider import mock_transport


def test_abstract_copy_excludes_cover_metadata():
    source={'text':'论文标题\n信息科学学院 网络安全专业 张同学 指导老师：李老师\n摘 要：本研究构建多源合规分析框架。\n但静态信息不能证明运行行为。'}
    points=source_sentences(source)
    assert points[0]=='本研究构建多源合规分析框架。'
    assert not any('学院' in text or '老师' in text for text in points)
    assert '但静态信息不能证明运行行为。' in points


def test_borderless_metric_rows_preserve_headers_and_values():
    doc=pymupdf.open();page=doc.new_page()
    for y,row in [(100,['Metric','Before','After']),(125,['MRR','0.8812','0.8945']),(150,['Hit1','0.8150','0.8300'])]:
        for x,text in zip([80,210,340],row):page.insert_text((x,y),text)
    found=_aligned_metric_tables(page,[{'bbox':[80,60,400,75]}])
    assert len(found)==1
    assert found[0].extract()==[['Metric','Before','After'],['MRR','0.8812','0.8945'],['Hit1','0.8150','0.8300']]
    doc.close()


async def test_reasoning_only_truncation_retries_once_for_complete_json(monkeypatch):
    calls=[]
    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls)==1:return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'','reasoning_content':'private reasoning'}}]})
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"title":"完整标题"}'}}]})
    mock_transport(monkeypatch,handler)
    client=OpenAICompatibleClient('https://api-inference.modelscope.cn/v1','fixture',{},1)
    assert json.loads(await client.chat_completion('ZhipuAI/GLM-5.2',[],json_mode=True,max_tokens=100))['title']=='完整标题'
    assert len(calls)==2 and calls[1]['chat_template_kwargs']['enable_thinking'] is False
    assert calls[1]['max_tokens']==4096


def test_missing_office_registration_is_unavailable(monkeypatch,tmp_path):
    from app.personalization import office
    if office.os.name!='nt':return
    source=tmp_path/'example.pptx';source.write_bytes(b'fixture')
    monkeypatch.setattr(office,'registered_office',lambda _:False)
    result=office.render_office(source,tmp_path/'render','wps')
    assert result['status']=='unavailable' and '自动化接口' in result['message']


async def test_null_choices_are_retried_without_crashing(monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'choices':None} if len(calls)==1 else {'choices':[{'finish_reason':'stop','message':{'content':'{"slides":[]}'}}]})
    mock_transport(monkeypatch,handler)
    client=OpenAICompatibleClient('https://example.com/v1','fixture',{},1)
    assert json.loads(await client.chat_completion('fixture',[],json_mode=True))=={'slides':[]}
    assert len(calls)==2


def test_ambiguous_metric_row_does_not_become_partial_table():
    doc=pymupdf.open();page=doc.new_page()
    for y,row in [(100,['Metric','Before','After']),(125,['MRR','0.8812','0.8945']),(150,['Hit1','0.8150','0.8300']),(175,['Hit3','missing','0.96'])]:
        for x,text in zip([80,210,340],row):page.insert_text((x,y),text)
    assert not _aligned_metric_tables(page,[{'bbox':[80,60,400,75]}])
    doc.close()


def test_page_prefix_stays_with_previous_section_and_decimal_is_not_heading():
    from app.documents.parser import _pdf_page_sections
    doc=pymupdf.open();page=doc.new_page()
    for y,text in [(70,'Previous task result Accuracy 0.7146.'),(100,'0.5037 and 0.5128 are macro scores'),(160,'5.4.2 Next task'),(190,'Next task Accuracy 0.8896.')]:
        page.insert_text((70,y),text)
    sections=_pdf_page_sections(page,41,1,previous_heading='5.4.1 Previous task')
    assert len(sections)==2
    assert sections[0]['title']=='5.4.1 Previous task'
    assert '0.7146' in sections[0]['text'] and '0.8896' not in sections[0]['text']
    assert sections[1]['title']=='5.4.2 Next task'
    assert '0.8896' in sections[1]['text'] and '0.7146' not in sections[1]['text']
    doc.close()


def test_continuation_pages_share_one_topic_without_losing_references():
    from app.presentation_intelligence.planner import _section_records
    from app.validation.quality import semantic_completeness
    source={'name':'paper','sections':[
        {'id':'S1','title':'3.1 研究方法','page':1,'text':'检索模型使用外部知识限制推理范围。','semanticRole':'method'},
        {'id':'S2','title':'3.1 研究方法','page':2,'text':'检索模型输出同时包含来源记录和校验结果。','semanticRole':'method'},
        {'id':'S3','title':'5.1 核心结果','page':3,'text':'核心任务准确率达到0.8981，召回率达到0.9277。','semanticRole':'data'}]}
    records=_section_records([source])
    assert len(records)==2 and len(records[0]['refSections'])==2
    assert '来源记录' in records[0]['section']['text']
    assert '来源记录' not in source['sections'][0]['text']
    report=semantic_completeness([], [source])
    assert report['requiredSections']==2 and report['overall']==0


def test_long_report_summary_requires_real_chapter_copy_and_task_metrics():
    from app.validation.quality import summary_evidence_coverage
    sections=[];slides=[]
    for chapter,claim in [(1,'研究问题涉及应用隐私声明与权限行为的不一致。'),(2,'研究方法通过检索外部知识对推理过程施加约束。'),(3,'实验结果反映不同应用任务具有不同的准确率表现。')]:
        for n in range(10):
            sections.append({'id':f'S{chapter}-{n}','title':f'{chapter}.{n+1} 章节内容','text':claim})
        slides.append({'role':'content','content':{'title':'研究说明','bullets':[claim]},'sourceRefs':[{'document':'paper','section':f'S{chapter}-0'}]})
    source={'name':'paper','sections':sections,'tables':[{'section':'S3-0','caption':'任务性能','rows':[['Metric','Value'],['Accuracy','0.89']]}]}
    report=summary_evidence_coverage(slides,[source])
    assert not report['passed'] and not report['missingChapters'] and len(report['missingResultTables'])==1
    slides[2]['content']['bullets'].append('Accuracy：0.89')
    assert summary_evidence_coverage(slides,[source])['passed']
    slides[1]['content']['bullets']=['谢谢大家。']
    assert not summary_evidence_coverage(slides,[source])['passed']


def test_result_repair_adds_sibling_metric_and_its_exact_source():
    from app.presentation_intelligence.result_coverage import complete_primary_results
    source={'name':'paper','sections':[{'id':'A','title':'5.4.1 Task A'},{'id':'B','title':'5.4.2 Task B'}],
            'tables':[{'section':'B','page':42,'caption':'表5-6 Task B','rows':[['Metric','Value'],['Accuracy','0.8896']]}]}
    slide={'role':'data','content':{'title':'Task A','bullets':['Original detail']},'sourceRefs':[{'document':'paper','section':'A','page':41}]}
    plan={'slides':[slide]}
    assert complete_primary_results(plan,[source])==1
    assert 'Task B：Accuracy 0.8896' in slide['content']['bullets']
    assert {'document':'paper','section':'B','page':42} in slide['sourceRefs']
    assert 'Original detail' in slide['speakerIntent']['talkingPoints']
    assert complete_primary_results(plan,[source])==0


def test_editorial_review_instruction_never_becomes_slide_copy():
    from app.api.workflow_routes import clean_audience_bullet
    assert clean_audience_bullet('统一标题风格为实验任务描述，将具体结论保留在 message 中，避免标题过长')==''
    assert clean_audience_bullet('检索增强生成通过外部知识约束推理')=='检索增强生成通过外部知识约束推理'


def test_url_table_cells_and_dangling_list_introductions_are_not_copy():
    points=source_sentences({'text':'本文使用四份国家标准作为规范来源，包括\n360 浏览器 https://example.com/privacy/long-path/index.html'})
    assert points==['本文使用四份国家标准作为规范来源']

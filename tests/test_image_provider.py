import base64
import json
import httpx
import pytest
from app.providers.openai_compatible import OpenAICompatibleClient, ProviderError
from app.providers.image_models import image_candidates


def mock_transport(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr('app.providers.openai_compatible.httpx.AsyncClient', lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr('app.providers.openai_compatible.assert_public_image_url', lambda _: None)


def test_image_candidates_exclude_chat_vision_embedding_and_edit():
    ids = ['deepseek-ai/DeepSeek-V4-Pro','Qwen/Qwen3-VL-8B-Instruct','Qwen/Qwen3-Embedding-4B','Qwen/Qwen-Image-Edit','MusePublic/Qwen-Image-Edit','Shanghai_AI_Laboratory/Intern-S2-Preview','Qwen/Qwen-Image','Tongyi-MAI/Z-Image-Turbo']
    assert image_candidates([{'id': name} for name in ids]) == ids[-2:]
    assert image_candidates([{'id':'custom-image-endpoint','capabilities':['image_generation']}]) == ['custom-image-endpoint']


async def test_modelscope_async_submission_poll_and_download(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == 'POST':
            assert request.headers['X-ModelScope-Async-Mode'] == 'true'
            assert json.loads(request.content)['size'] == '1664x928'
            return httpx.Response(200,json={'task_id':'example'})
        if request.url.path.endswith('/tasks/example'):
            assert request.headers['X-ModelScope-Task-Type'] == 'image_generation'
            return httpx.Response(200,json={'task_status':'SUCCEED','output_images':['https://images.example.com/result.png']})
        assert 'authorization' not in request.headers
        return httpx.Response(200,content=b'image bytes')
    mock_transport(monkeypatch,handler)
    client=OpenAICompatibleClient('https://api-inference.modelscope.cn/v1','secret',{},15)
    assert await client.image_generation('Qwen/Qwen-Image','example','1664x928') == b'image bytes'
    assert len(calls)==3


async def test_async_failure_is_readable(monkeypatch):
    def handler(request):
        return httpx.Response(200,json={'task_id':'x'} if request.method=='POST' else {'task_status':'FAILED','message':'quota exhausted'})
    mock_transport(monkeypatch,handler)
    with pytest.raises(ProviderError,match='quota exhausted'):
        await OpenAICompatibleClient('https://api-inference.modelscope.cn/v1','secret',{},15).image_generation('Qwen/Qwen-Image','example')


async def test_upstream_error_preserves_reason_and_redacts_secret(monkeypatch):
    mock_transport(monkeypatch, lambda request:httpx.Response(400,json={'errors':{'message':'model unavailable for secret-token-123'}}))
    with pytest.raises(ProviderError) as error:
        await OpenAICompatibleClient('https://api.example.com/v1','secret-token-123',{},15).image_generation('custom-image','example')
    assert 'model unavailable' in str(error.value) and 'HTTP 400' in str(error.value)
    assert 'secret-token-123' not in str(error.value)


async def test_sync_image_provider_remains_supported(monkeypatch):
    def handler(request):
        assert 'X-ModelScope-Async-Mode' not in request.headers
        assert json.loads(request.content)['image_size']=='1664x928'
        return httpx.Response(200,json={'data':[{'b64_json':base64.b64encode(b'sync image').decode()}]})
    mock_transport(monkeypatch,handler)
    assert await OpenAICompatibleClient('https://api.siliconflow.cn/v1','secret',{},15).image_generation('Qwen/Qwen-Image','example','1664x928')==b'sync image'


async def test_edit_model_rejected_before_request(monkeypatch):
    def handler(request):raise AssertionError('must not spend a request on incompatible model')
    mock_transport(monkeypatch,handler)
    with pytest.raises(ProviderError,match='原图'):
        await OpenAICompatibleClient('https://api.example.com/v1','secret',{},15).image_generation('Qwen/Qwen-Image-Edit','example')


def test_registering_text_model_as_image_is_rejected(client):
    provider=client.post('/api/v1/providers',json={'name':'test','base_url':'https://api.example.com/v1'}).json()
    response=client.post(f"/api/v1/providers/{provider['id']}/models",json={'model_id':'Shanghai_AI_Laboratory/Intern-S2-Preview','capabilities':['image_generation']})
    assert response.status_code==422

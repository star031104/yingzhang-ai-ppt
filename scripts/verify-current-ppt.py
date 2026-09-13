import argparse,asyncio,json,time
from pathlib import Path
import httpx
from app.config import settings
parser=argparse.ArgumentParser(description='Run sample, full rendering and PPTX export on an explicitly selected existing project.')
parser.add_argument('project_id')
parser.add_argument('--output-dir',default='output/ppt-e2e')
parser.add_argument('--require-quality-pass',action='store_true',help='Fail when content or rendering quality is not ready for formal delivery')
args=parser.parse_args()
PID=args.project_id
async def main():
 async with httpx.AsyncClient(base_url='http://127.0.0.1:8000/api/v1',timeout=240,trust_env=False) as c:
  r=await c.get('/auth/session');r.raise_for_status()
  if not r.json().get('authenticated'):
   if not settings.public_admin_password:raise RuntimeError('Server requires authentication; use the local launcher for account-free verification.')
   r=await c.post('/auth/login',json={'name':'验收助手','password':settings.public_admin_password});r.raise_for_status()
  base=f'/projects/{PID}'
  async def post(path):
   r=await c.post(path);r.raise_for_status();return r.json()
  async def job(kind):
   j=await post(base+'/jobs/'+kind);print('START',kind,j['id'],flush=True)
   previous='';deadline=time.monotonic()+1200
   while time.monotonic()<deadline:
    r=await c.get('/jobs/'+j['id']);r.raise_for_status();j=r.json()
    label=j.get('checkpoint',{}).get('label','')
    if label!=previous:print(kind,j['status'],label,flush=True);previous=label
    if j['status'] in ['completed','failed','cancelled']:
     if j['status']!='completed':raise RuntimeError(str(j.get('error')))
     return j
    await asyncio.sleep(3)
   raise RuntimeError('Job did not finish in 20 minutes')
  await post(base+'/gates/outline/approve')
  await job('sample')
  await post(base+'/gates/sample/approve')
  result=await job('generate')
  root=Path(args.output_dir);root.mkdir(parents=True,exist_ok=True)
  (root/'job.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
  r=await c.get(base+'/export/pptx?stage=draft');r.raise_for_status();(root/'thesis-defense.pptx').write_bytes(r.content)
  print('EXPORTED PPTX',len(r.content),flush=True)
  r=await c.post(base+'/validate');print('QUALITY',r.status_code,r.text[:3500],flush=True)
  (root/'quality.json').write_text(r.text,encoding='utf-8')
  r.raise_for_status()
  quality=r.json()
  print('RENDER CHECK:',quality.get('visualQA',{}).get('blocking'),'blocking pages; QUALITY PASS:',quality.get('passed'),flush=True)
  if quality.get('visualQA',{}).get('blocking') or not quality.get('visualQA',{}).get('complete'):
   raise RuntimeError('Rendering acceptance failed')
  if args.require_quality_pass and not quality.get('passed'):
   raise RuntimeError('Content quality needs review; see quality.json')
asyncio.run(main())

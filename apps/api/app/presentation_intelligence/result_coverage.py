"""Keep headline task results visible when a model omits a sibling subsection."""
import re


def complete_primary_results(plan, sources):
    repaired = 0
    for source in sources:
        sections = {s['id']: s for s in source.get('sections', [])}
        for table in source.get('tables', []):
            rows = table.get('rows', [])
            if len(rows) < 2 or len(rows[0]) != 2:
                continue
            row = next((r for r in rows[1:] if len(r) == 2 and str(r[0]).lower() == 'accuracy'
                        and re.fullmatch(r'0(?:\.\d+)?|1(?:\.0+)?', str(r[1]).strip())), None)
            section = sections.get(table.get('section'), {})
            match = re.match(r'^(\d+\.\d+)\.\d+\s', section.get('title', ''))
            if not row or not match:
                continue
            family = match.group(1)
            candidates = []
            for slide in plan.get('slides', []):
                if slide.get('role') not in {'data', 'comparison', 'insight'}:
                    continue
                refs = [r for r in slide.get('sourceRefs', []) if r.get('document') == source['name']]
                exact = any(r.get('section') == table.get('section') for r in refs)
                related = any(re.match(r'^' + re.escape(family) + r'(?:\.\d+)*\s', sections.get(r.get('section'), {}).get('title', '')) for r in refs)
                if related:
                    candidates.append((int(exact), slide))
            if not candidates:
                continue
            slide = max(candidates, key=lambda x: x[0])[1]
            text = ' '.join([slide.get('message', ''), *slide.get('content', {}).get('bullets', [])])
            if str(row[1]) in text and any(r.get('section') == table.get('section') and r.get('document') == source['name'] for r in slide.get('sourceRefs', [])):
                continue
            caption = re.sub(r'^表\s*\d+(?:[-－.]\d+)*\s*', '', table.get('caption', section.get('title', '')))
            point = f'{caption}：Accuracy {row[1]}'
            bullets = list(slide['content'].get('bullets', []))
            notes = slide.setdefault('speakerIntent', {})
            notes['talkingPoints'] = list(dict.fromkeys([*notes.get('talkingPoints', []), *bullets]))
            # Preserve prior detail in notes, reserving visible space for results.
            metrics = [b for b in bullets if re.search(r'Accuracy\s*[:：]?\s*0\.\d+', b, re.I)]
            others = [b for b in bullets if b not in metrics]
            slide['content']['bullets'] = [*metrics, point, *others][:5]
            ref = table.get('sourceRef') or {'document':source['name'], 'section':table['section'], 'page':table.get('page')}
            if ref not in slide['sourceRefs']:
                slide['sourceRefs'].append(ref)
            if not max(candidates, key=lambda x:x[0])[0] or len(metrics) >= 1:
                parent = next((s.get('title', '') for s in sections.values() if re.match(r'^'+re.escape(family)+r'\s', s.get('title',''))), '')
                slide['content']['title'] = parent if parent and len(parent) <= 44 else '各任务主要指标对比'
                slide['message'] = '各项任务按原文的准确率口径进行对比'
            repaired += 1
    return repaired

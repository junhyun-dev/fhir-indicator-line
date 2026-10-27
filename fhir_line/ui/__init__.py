"""D1-D7 / ADR0010: static local pages. Embedded payload has already passed the allowlist."""
from pathlib import Path
import json,html

TITLES={'S01':'지표 현황','S02':'대상 환자 조회','S03':'환자 상세','S04':'데이터 품질 검사','S05':'오류내역'}

def write_site(folder,payload,public,guard):
    here=Path(__file__).parent
    for name in ('report.css','report.js'):
        with guard(folder/name).open('x') as f:f.write((here/name).read_text())
    encoded=json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    with guard(folder/'data.json').open('x') as f:f.write(encoded+'\n')
    screens=['S01','S04','S05'] if public else list(TITLES)
    menu=''.join(f'<a href="{s}.html">{html.escape(TITLES[s])}</a>' for s in screens)
    for screen in screens:
        body=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{TITLES[screen]} · 임상 지표</title><link rel="stylesheet" href="report.css"></head><body data-screen="{screen}"><header><div><b>임상 지표 대시보드</b><small>OMOP CDM · 학습용 v1</small></div><nav>{menu}</nav><span>로컬 조회 · 합성 / 공개 비식별 자료</span></header><div class="crumb">혈압 조절률 / {TITLES[screen]}</div><main><h1>{TITLES[screen]}</h1><div id="app"></div></main><footer>병원 안 환자 번호는 이 실행에서만 사용해요. 의료 판단이나 공식 CMS 적합성 검증이 아니에요.</footer><script id="payload" type="application/json">{encoded}</script><script src="report.js"></script></body></html>'''
        with guard(folder/(screen+'.html')).open('x') as f:f.write(body)

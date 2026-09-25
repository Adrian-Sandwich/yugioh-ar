"""Build a standalone comparison gallery and machine-readable summary."""
import html,json,statistics
from pathlib import Path
OUT=Path(__file__).resolve().parent
variants=['original','clahe','docshrnet','mimo-shdocs']
samples=json.loads((OUT/'samples.json').read_text(encoding='utf-8'))['samples']
reports={v:json.loads((OUT/'outputs'/v/'evaluation.json').read_text(encoding='utf-8')) for v in variants}
summary={}
for name,data in reports.items():
    table=[r for r in data['rows'] if r['sample'].startswith('table-')]
    assert len(table)==7 and len(data['rows'])==len(samples),'Incomplete evaluation'
    timing=OUT/'outputs'/name/'run.json'
    latencies=[r['ms'] for r in json.loads(timing.read_text())['rows'] if r['sample'].startswith('table-')] if timing.exists() else []
    summary[name]={'table_top1_correct':sum(r['top1_correct'] for r in table),
                   'table_accepted_correct':sum(r['accepted_correct'] for r in table),
                   'table_false_accepts':sum(r['false_accept'] for r in table),
                   'table_ocr_matches':sum(r['ocr_matches_expected'] for r in table),
                   'close_ocr_matches':data['rows'][-1]['ocr_matches_expected'],
                   'restore_median_ms':statistics.median(latencies) if latencies else None}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
parts=['''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prueba de reflejos — siete cartas</title><style>body{background:#10141d;color:#ecf1f9;font:16px system-ui;margin:24px auto;max-width:1400px;padding:0 20px}a{color:#8de5ca}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #425169;text-align:left}img{max-width:100%;height:230px;object-fit:contain}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.sample{background:#192335;padding:14px;border-radius:10px}small{display:block;color:#bed0df}h2{margin-top:40px}@media(max-width:700px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}</style>
<h1>Reflejos: comparación sobre una captura real</h1><p>Siete instancias de la misma escena y una foto cercana de control. Prueba exploratoria, sin imagen limpia pareada. Las puntuaciones son similitudes del piloto, no probabilidades.</p>
<p>Las siete cartas: Ojos Anómalos (dos copias), Utopía, Dragón Negro, Mago Oscuro, Juicio Solemne y Dragón Blanco. La primera opción correcta no equivale a una identificación aceptada.</p>
<table><tr><th>Variante</th><th>Primera opción correcta</th><th>Aceptadas correctas</th><th>Falsas aceptaciones</th><th>Seriales en mesa</th><th>Serial cercano</th><th>Restauración mediana</th></tr>''']
for v,s in summary.items():
    ms=f'{s["restore_median_ms"]/1000:.2f} s/carta' if s['restore_median_ms'] is not None else '—'
    parts.append(f'<tr><td>{v}</td><td>{s["table_top1_correct"]}/7</td><td>{s["table_accepted_correct"]}/7</td><td>{s["table_false_accepts"]}</td><td>{s["table_ocr_matches"]}/7</td><td>{"Sí" if s["close_ocr_matches"] else "No"}</td><td>{ms}</td></tr>')
parts.append('</table><p>Los tiempos de restauración son CPU, dos hilos, con otros servicios activos; excluyen captura y reconocimiento. No representan un límite de rendimiento del modelo.</p>')
for sample in samples:
    parts.append(f'<h2>{html.escape(sample["sample"])} · {html.escape(sample.get("expected_name","Dragón Blanco cercano"))}</h2><div class="grid">')
    for v in variants:
        r=next(r for r in reports[v]['rows'] if r['sample']==sample['sample'])
        path=f'outputs/{v}/{sample["sample"]}.png';code=r['ocr_best']['passcode'] if r['ocr_best'] else 'Sin lectura'
        parts.append(f'<article class="sample"><h3>{v}</h3><a href="{path}"><img src="{path}" alt="{v}: {sample["sample"]}"></a><p>{html.escape(r["predicted"])}</p><small>{"Aceptada" if r["accepted"] else "Rechazada"} · similitud {r["score"]:.3f} · margen {r["margin"]:.3f}</small><small>OCR: {html.escape(code)}</small></article>')
    parts.append('</div>')
parts.append('<p>Modelos externos evaluados sin entrenar ni modificar pesos. Los originales y cada salida están disponibles haciendo clic en la imagen.</p></html>')
(OUT/'comparison.html').write_text('\n'.join(parts),encoding='utf-8')
print(json.dumps(summary,indent=2))

import json, datetime
from google.cloud import firestore
db = firestore.Client(project='fiscocontmais')
desde = (datetime.date.today() - datetime.timedelta(days=12)).strftime('%Y%m%d')
print('== agenda_sefin desde', desde)
for d in db.collection('agenda_sefin').stream():
    if d.id[:8] < desde: continue
    x = d.to_dict()
    print(d.id, '|', x.get('status'), '| tent', x.get('tentativas'), '|', x.get('maquina'), '|', x.get('em', '')[:19], '->', (x.get('fimEm') or '')[:19],
          '| F', json.dumps(x.get('fisconforme'), ensure_ascii=False), '| D', json.dumps(x.get('dare'), ensure_ascii=False), '| P', json.dumps(x.get('pagos'), ensure_ascii=False))
def meta(col, doc, campos):
    x = (db.collection(col).document(doc).get().to_dict() or {})
    print(col + '/' + doc, {k: x.get(k) for k in campos})
meta('fisconforme', '_meta', ['ultimaLeitura', 'por', 'auto', 'novas'])
meta('dare', '_meta_2026', ['ultimaLeitura', 'por', 'auto', 'novos', 'empresas', 'falhas'])
meta('dare', '_pg_202611', ['ultimaLeitura', 'por', 'auto', 'duracaoSeg'])
meta('dare', '_pg_202610', ['ultimaLeitura', 'por', 'auto', 'duracaoSeg'])

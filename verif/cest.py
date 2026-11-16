import re, json, urllib.request
B = 'http://www.sped.fazenda.gov.br/spedtabelas/WsConsulta/WsConsulta.asmx'
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=120).read()
x = get(B + '/consultarVersoesTabelasExternas?codigoSistema=SpedFiscal').decode('utf-8', 'replace')
open('verif/versoes.xml', 'w').write(x)
print('RESULTADO versoes', len(x))
# acha a tabela de CEST
blocos = re.findall(r'<tabela>(.*?)</tabela>', x, re.S | re.I) or re.findall(r'<Tabela[^>]*>(.*?)</Tabela>', x, re.S)
achou = [b for b in blocos if 'CEST' in b.upper() or 'ESPECIFICADOR' in b.upper()]
print('RESULTADO tabelas', len(blocos), 'cest', len(achou))
for b in achou[:3]:
    print('RESULTADO', re.sub(r'\s+', ' ', b)[:600])
ids = re.findall(r'<id>(\d+)</id>', ' '.join(achou)) or re.findall(r'(\d+)', ' '.join(achou))[:1]
out = {}
for i in ids[:2]:
    try:
        t = get(B + f'/baixarVersaoTabelaExterna?idPacote={i}').decode('latin1')
        open(f'verif/cest_{i}.txt', 'w', encoding='utf-8').write(t)
        codes = sorted(set(re.findall(r'(?<!\d)(\d{7})(?!\d)', t)))
        out[i] = codes
        print('RESULTADO baixou', i, len(t), len(codes), t[:300].replace('\n', ' | '))
    except Exception as e:
        print('RESULTADO falhou', i, e)
json.dump(out, open('verif/cest_oficial.json', 'w'), indent=0)

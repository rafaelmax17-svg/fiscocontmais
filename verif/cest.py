import re, json, html, urllib.request
B = 'http://www.sped.fazenda.gov.br/spedtabelas/WsConsulta/WsConsulta.asmx'
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=120).read()
x = html.unescape(get(B + '/consultarVersoesTabelasExternas?codigoSistema=SpedFiscal').decode('utf-8', 'replace'))
tabs = re.findall(r'<tabela\b[^>]*>', x)
cest = [t for t in tabs if 'COD_CEST' in t]
print('RESULTADO', len(tabs), 'tabelas;', len(cest), 'de CEST')
for t in cest:
    print('RESULTADO', t[:400])
out = {}
for t in cest[-2:]:
    m = re.search(r'\bid="(\d+)"', t)
    if not m:
        continue
    i = m.group(1)
    for u in ('http://www.sped.fazenda.gov.br/spedtabelas/wsconsulta/obterTabela.ashx?idPacote=' + i, B + '/baixarVersaoTabelaExterna?idPacote=' + i):
        try:
            raw = get(u)
            t2 = raw.decode('latin1')
            codes = sorted(set(re.findall(r'(?<!\d)(\d{7})(?!\d)', t2)))
            out[i] = {'url': u, 'cab': t2[:400], 'codes': codes}
            print('RESULTADO baixou', i, len(raw), len(codes), '1708704' in codes, '1700301' in codes, '0302500' in codes, t2[:200].replace('\n', ' | '))
            break
        except Exception as e:
            print('RESULTADO falhou', u, e)
json.dump(out, open('verif/cest_oficial.json', 'w'), indent=0)

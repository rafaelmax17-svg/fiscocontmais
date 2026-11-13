# -*- coding: utf-8 -*-
"""NCM × XML das entradas (Corretor do SPED Fiscal · Análise Inteligente).

O C170 não tem NCM: o NCM do item é o do cadastro do produto, registro 0200, campo 08 (COD_NCM) — Guia Prático da
EFD ICMS/IPI. A etapa liga cada item de ENTRADA do C170 ao item da NF-e do fornecedor (pela chave do C100 e pelo número
do item com valor compatível, o mesmo casamento das demais etapas — icms_xml._casar) e compara o NCM do 0200 do produto
com o NCM que o fornecedor informou no XML (det/prod/NCM).

Decisão, por produto (COD_ITEM):
  • todas as notas trazem o mesmo NCM e ele é diferente do 0200 → troca o COD_NCM pelo do XML;
  • 0200 sem NCM (ou com NCM inválido: não tem 8 dígitos / 00000000) → preenche com o do XML;
  • fornecedores usam NCMs diferentes → fica o NCM da maioria das notas; se o do 0200 já é o da maioria (ou empata
    com ela), fica como está e o motivo aparece na tela.
NCM do XML vazio, inválido ou 00000000 não conta. Notas canceladas/denegadas/inutilizadas ficam de fora.
Proteções (ficam como estão, com o motivo na tela):
  • o item ligado na NF-e é OUTRO produto: nenhuma palavra em comum entre a descrição do 0200 e a do XML (xProd) —
    ex.: "INSUMOS HORTIFRUT CHUCHU" ligado ao item "REPOLHO ROXO"; essa nota não vota no NCM do produto;
  • o NCM do XML é de OUTRO CAPÍTULO (2 primeiros dígitos) e só uma nota traz: erro do fornecedor é mais provável
    (ex.: "MEIO DA ASA DE FRANGO" com NCM 0406.90.90, de queijo) — com 2 ou mais notas iguais, troca;
  • código genérico: o mesmo código recebe mais de 3 NCMs diferentes nas notas (ex.: "MATERIAIS ELETRICA") — é um
    código usado para vários produtos, e nenhum NCM sozinho é o dele.
Efeito na ST de RO: compara st_entrada_ro.produto_st com o NCM antigo e o novo (a etapa roda ANTES da ICMS-ST na
entrada, que então usa o NCM corrigido).
O 0200 vale para o arquivo inteiro (entradas, saídas e inventário H010): o cadastro do sistema da empresa também precisa
ser ajustado, senão o NCM antigo volta no próximo SPED. Gera arquivo NOVO; o original nunca é alterado.
"""
import re
from collections import Counter, defaultdict

import difal_ro as dr
import icms_xml as ix

CANC = {'02', '03', '04', '05'}


def _so(s):
    return re.sub(r'\D', '', s or '')


def _valido(n):
    return len(n) == 8 and n != '00000000'


def fmt(n):
    n = _so(n)
    return f'{n[:4]}.{n[4:6]}.{n[6:]}' if len(n) == 8 else (n or '')


def _efeito_st(de, para, cest):
    try:
        import st_entrada_ro as se
        a, _ = se.produto_st(de, cest) if de else (None, '')
        b, _ = se.produto_st(para, cest)
    except Exception:
        return '', ''
    if b and not a:
        return 'entra', f"passa a ser da ST de RO (Anexo VI, Tabela {b['tab']})"
    if a and not b:
        return 'sai', f"deixa de ser da ST de RO (era da Tabela {a['tab']})"
    if a and b and a['tab'] != b['tab']:
        return 'muda', f"continua na ST, mas muda da Tabela {a['tab']} para a {b['tab']}"
    if a and b:
        return 'igual', f"não muda a ST (Tabela {b['tab']})"
    return '', ''


_VAZIAS = {'INSUMO', 'INSUMOS', 'CONSUMO', 'FUNC', 'LIMPEZA', 'UTENSILIOS', 'ULTENSILIOS', 'EPI', 'DOCE', 'DOCES', 'COM', 'SEM', 'PARA',
           'UND', 'UNID', 'LATA', 'PET', 'PCT', 'TIPO', 'HORTIFRUT', 'TEMPEROS', 'CONSTRUCAO', 'MATERIAIS', 'MATERIAL', 'DIVERSOS', 'PRODUTO',
           'PRODUTOS', 'REVENDA', 'USO', 'KIT', 'CAIXA', 'PACOTE', 'FARDO', 'UNIDADE', 'DAS', 'DOS', 'NAS', 'NOS'}


def _palavras(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().upper()
    return {w for w in re.split(r'[^A-Z0-9]+', s) if len(w) >= 3 and w not in _VAZIAS and not re.fullmatch(r'\d+[A-Z]{0,3}', w)}


def _mesmo_produto(descr_sped, descr_xml):
    a, b = _palavras(descr_sped), _palavras(descr_xml)
    if not a or not b:
        return True                                  # sem descrição útil: não dá para dizer que é outro produto
    for x in a:
        for y in b:
            if x == y or x.startswith(y) or y.startswith(x) or (min(len(x), len(y)) >= 4 and x[:4] == y[:4]):
                return True
    return False


def _estrutura(linhas):
    _, part, _, docs, _, _ = dr._estrutura(linhas)
    p200 = {}
    for i, l in enumerate(linhas):
        if l.startswith('|0200|'):
            c = l.split('|')
            if len(c) > 8:
                p200[c[2]] = {'i': i, 'descr': c[3], 'ncm': c[8], 'cest': c[13] if len(c) > 13 else ''}
    return part, docs, p200


def analisar_texto(texto, xmls=None):
    xmls = xmls or {}
    linhas, _, _ = dr.dividir(texto)
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), None)
    if fim is not None:
        linhas = linhas[:fim + 1]
    part, docs, p200 = _estrutura(linhas)
    por_cod, outros = defaultdict(list), defaultdict(list)
    conferidos, sem_xml, ncm_xml_vazio = 0, 0, 0
    for d in docs:
        if d['oper'] != '0' or d['sit'] in CANC or not d['c170']:
            continue
        x = xmls.get(_so(d['chave'])) if d['chave'] else None
        if not x or not x.get('itens'):
            sem_xml += 1
            continue
        par = ix._casar(d, x)[0]
        forn = (part.get(d['part']) or {}).get('nome', d['part'])
        for c in d['c170']:
            it = par.get(c['i'])
            if it is None:
                continue
            n = _so(it.get('ncm'))
            if not _valido(n):
                ncm_xml_vazio += 1
                continue
            conferidos += 1
            prod = p200.get(c['item']) or {}
            sped = _so(prod.get('ncm'))
            if n != sped and not _mesmo_produto(prod.get('descr') or c['descr'], it.get('xprod')):
                outros[c['item']].append({'num': d['num'], 'serie': d['serie'], 'forn': forn, 'data': d['dt'], 'ncm': fmt(n), 'valor': round(c['vl'], 2),
                                          'xprod': it.get('xprod') or '', 'diverge': True})
                continue
            por_cod[c['item']].append({'doc': d['i'], 'num': d['num'], 'serie': d['serie'], 'forn': forn, 'data': d['dt'],
                                       'ncm': n, 'valor': round(c['vl'], 2), 'cest': it.get('cest') or '', 'descr_xml': it.get('xprod') or ''})
    itens, fica = [], []
    for cod, occ in por_cod.items():
        prod = p200.get(cod)
        if not prod:
            continue
        sped = _so(prod['ncm'])
        notas = {}                                   # NCM por nota (a nota conta uma vez para cada NCM)
        for o in occ:
            notas.setdefault((o['doc'], o['ncm']), o)
        cont = Counter(n for (_, n) in notas)
        if set(cont) == {sped}:
            continue                                 # tudo confere
        if len(cont) > 3:                            # código genérico: vários produtos no mesmo código
            fica.append({'id': cod, 'cod': cod, 'descr': prod['descr'], 'ncm_sped': fmt(sped) if sped else '', 'ncm_xml': '', 'itens': len(occ),
                         'notas': len({o['doc'] for o in occ}), 'valor': round(sum(o['valor'] for o in occ), 2), 'conflito': True,
                         'ncms_xml': {fmt(n): q for n, q in cont.most_common()}, 'tipo': 'generico',
                         'nfs': [{'num': o['num'], 'serie': o['serie'], 'forn': o['forn'], 'data': o['data'], 'ncm': fmt(o['ncm']), 'valor': o['valor'],
                                  'diverge': o['ncm'] != sped} for o in notas.values()],
                         'motivo': f"código usado para vários produtos: as notas trazem {len(cont)} NCMs diferentes; nenhum NCM sozinho é o deste código"})
            continue
        topo = max(cont.values())
        lideres = [n for n, q in cont.items() if q == topo]
        if len(lideres) > 1:                         # empate: o que tem mais itens; depois, o da nota mais recente
            def _peso(n):
                ds = [o for o in occ if o['ncm'] == n]
                ult = max((o['data'][4:8] + o['data'][2:4] + o['data'][:2]) for o in ds)
                return (len(ds), ult)
            lideres.sort(key=_peso, reverse=True)
        para = lideres[0]
        nfs = sorted(({'num': o['num'], 'serie': o['serie'], 'forn': o['forn'], 'data': o['data'], 'ncm': fmt(o['ncm']), 'valor': o['valor'],
                       'diverge': o['ncm'] != para} for o in notas.values()), key=lambda z: (z['data'][4:8] + z['data'][2:4] + z['data'][:2], z['num']))
        base = {'id': cod, 'cod': cod, 'descr': prod['descr'], 'ncm_sped': fmt(sped) if sped else '', 'itens': len(occ), 'notas': len({o['doc'] for o in occ}),
                'valor': round(sum(o['valor'] for o in occ), 2), 'nfs': nfs,
                'conflito': len(cont) > 1, 'ncms_xml': {fmt(n): q for n, q in cont.most_common()}}
        if _valido(sped) and sped in cont and cont[sped] >= topo:
            fica.append({**base, 'ncm_xml': fmt(sped), 'tipo': 'maioria',
                         'motivo': f"os fornecedores usam NCMs diferentes ({', '.join(f'{fmt(n)} em {q} nota(s)' for n, q in cont.most_common())}); "
                                   f"o NCM do SPED já é o da maioria das notas"})
            continue
        if _valido(sped) and para[:2] != sped[:2] and cont[para] < 2:
            fica.append({**base, 'ncm_xml': fmt(para), 'tipo': 'capitulo',
                         'motivo': f"o NCM do XML ({fmt(para)}) é de outro capítulo da tabela (capítulo {para[:2]}; o do SPED é o {sped[:2]}) e só uma nota "
                                   f"traz esse NCM: o mais provável é erro do fornecedor, o NCM do SPED fica"})
            continue
        cest = prod['cest'] or next((o['cest'] for o in occ if o['ncm'] == para and o['cest']), '')
        ef, ef_txt = _efeito_st(sped if _valido(sped) else '', para, cest)
        if not _valido(sped):
            regra, mot = 'preenche', ('o produto está sem NCM no SPED' if not sped else f'o NCM do SPED ({sped}) é inválido') + ': entra o NCM do XML'
        elif len(cont) == 1:
            regra, mot = 'troca', f"{'todas as notas trazem' if base['notas'] > 1 else 'a nota traz'} o NCM {fmt(para)}"
        else:
            regra, mot = 'maioria', (f"os fornecedores usam NCMs diferentes ({', '.join(f'{fmt(n)} em {q} nota(s)' for n, q in cont.most_common())}): "
                                     f"fica o da maioria das notas")
        itens.append({**base, 'ncm_xml': fmt(para), 'regra': regra, 'motivo': mot, 'efeito': ef, 'efeito_txt': ef_txt})
    ja = {f['cod'] for f in fica} | {i['cod'] for i in itens}
    for cod, oc in outros.items():                   # notas em que o item ligado é outro produto (não votaram)
        if cod in ja:
            continue
        prod = p200.get(cod) or {}
        x = oc[0]
        fica.append({'id': cod, 'cod': cod, 'descr': prod.get('descr') or cod, 'ncm_sped': fmt(prod.get('ncm')), 'ncm_xml': '', 'itens': len(oc),
                     'notas': len({(o['num'], o['serie'], o['forn']) for o in oc}), 'valor': round(sum(o['valor'] for o in oc), 2), 'conflito': False,
                     'ncms_xml': dict(Counter(o['ncm'] for o in oc)), 'tipo': 'outro', 'nfs': oc,
                     'motivo': f"na NF {x['num']} ({x['forn']}) o item ligado é \"{x['xprod']}\", NCM {x['ncm']}: parece outro produto"
                               + (f" (e mais {len(oc) - 1} item(ns))" if len(oc) > 1 else '') + "; o NCM do SPED fica. Confira o código usado no lançamento"})
    itens.sort(key=lambda z: (z['efeito'] not in ('entra', 'sai', 'muda'), z['descr']))
    fica.sort(key=lambda z: z['descr'])
    return {'itens': itens, 'fica': fica,
            'resumo': {'produtos': len(itens), 'troca': sum(1 for i in itens if i['regra'] == 'troca'),
                       'preenche': sum(1 for i in itens if i['regra'] == 'preenche'), 'maioria': sum(1 for i in itens if i['regra'] == 'maioria'),
                       'muda_st': sum(1 for i in itens if i['efeito'] in ('entra', 'sai', 'muda')),
                       'fica': len(fica), 'generico': sum(1 for f in fica if f.get('tipo') == 'generico'),
                       'outro': sum(1 for f in fica if f.get('tipo') == 'outro'), 'capitulo': sum(1 for f in fica if f.get('tipo') == 'capitulo'), 'conferidos': conferidos, 'sem_xml': sem_xml, 'ncm_xml_vazio': ncm_xml_vazio}}


def aplicar_texto(texto, cods, xmls=None):
    """cods: COD_ITEM escolhidos → troca o campo 08 (COD_NCM) do 0200 pelo NCM do XML. -> (texto_novo, resumo)."""
    a = analisar_texto(texto, xmls)
    novo = {i['cod']: _so(i['ncm_xml']) for i in a['itens'] if i['cod'] in set(cods)}
    linhas, quebra, final_vazio = dr.dividir(texto)
    feitos = []
    for k, l in enumerate(linhas):
        if not l.startswith('|0200|'):
            continue
        c = l.split('|')
        if len(c) > 8 and c[2] in novo and _so(c[8]) != novo[c[2]]:
            feitos.append({'cod': c[2], 'de': c[8], 'para': novo[c[2]]})
            c[8] = novo[c[2]]
            linhas[k] = '|'.join(c)
    return quebra.join(linhas) + (quebra if final_vazio else ''), {'produtos': len(feitos), 'feitos': feitos}


if __name__ == '__main__':
    import sys
    import json
    from xml_entradas import ler_xmls
    import fiscal_core as fc
    t, _ = fc._ler_sped(sys.argv[1])
    xs = ler_xmls([sys.argv[2]])[0] if len(sys.argv) > 2 else {}
    print(json.dumps(analisar_texto(t, xs)['resumo'], ensure_ascii=False, indent=1))

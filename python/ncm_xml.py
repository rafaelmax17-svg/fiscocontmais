# -*- coding: utf-8 -*-
"""NCM × XML das entradas (Corretor do SPED Fiscal · Análise Inteligente).

O C170 não tem NCM: o NCM do item é o do cadastro do produto, registro 0200, campo 08 (COD_NCM) — Guia Prático da
EFD ICMS/IPI. A etapa liga cada item de ENTRADA do C170 ao item da NF-e do fornecedor (pela chave do C100 e pelo número
do item com valor compatível, o mesmo casamento das demais etapas — icms_xml._casar) e compara o NCM do 0200 do produto
com o NCM que o fornecedor informou no XML (det/prod/NCM).

Regra única: NCM do SPED diferente do NCM do XML → o produto aparece com a opção de alterar para o NCM do XML.
Quem decide é o usuário (marca ou desmarca). Se as notas do mesmo produto trazem NCMs diferentes, ele escolhe qual
(vem selecionado o que aparece em mais notas). NCM do XML vazio, inválido ou 00000000 não conta; notas canceladas,
denegadas e inutilizadas ficam de fora.
A linha mostra, só como informação, a descrição do produto no XML e se o NCM novo muda a ST de RO (a etapa roda
ANTES da ICMS-ST na entrada, que então usa o NCM escolhido).
O 0200 vale para o arquivo inteiro (entradas, saídas e inventário H010). Gera arquivo NOVO; o original nunca é alterado.
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


def _ord_data(d):
    return (d or '')[4:8] + (d or '')[2:4] + (d or '')[:2]


def efeito_st(de, para, cest):
    """Texto curto: o NCM novo muda a ST de RO? (só informação)."""
    try:
        import st_entrada_ro as se
        a = se.produto_st(de, cest)[0] if _valido(_so(de)) else None
        b = se.produto_st(para, cest)[0]
    except Exception:
        return ''
    if b and not a:
        return f"com o NCM do XML passa a ser da ST de RO (Anexo VI, Tabela {b['tab']})"
    if a and not b:
        return f"com o NCM do XML deixa de ser da ST de RO (era da Tabela {a['tab']})"
    if a and b and a['tab'] != b['tab']:
        return f"com o NCM do XML muda da Tabela {a['tab']} para a {b['tab']} da ST de RO"
    return ''


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
    por_cod = defaultdict(list)
    conferidos, sem_xml = 0, 0
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
                continue
            conferidos += 1
            por_cod[c['item']].append({'doc': d['i'], 'num': d['num'], 'serie': d['serie'], 'forn': forn, 'data': d['dt'], 'ncm': n,
                                       'valor': round(c['vl'], 2), 'cest': it.get('cest') or '', 'xprod': it.get('xprod') or ''})
    itens = []
    for cod, occ in por_cod.items():
        prod = p200.get(cod)
        if not prod:
            continue
        sped = _so(prod['ncm'])
        dif = [o for o in occ if o['ncm'] != sped]
        if not dif:
            continue                                         # SPED igual ao XML em todas as notas
        cont = Counter()
        for doc, n in {(o['doc'], o['ncm']) for o in dif}:   # cada nota conta uma vez para cada NCM
            cont[n] += 1
        ult = {n: max(_ord_data(o['data']) for o in dif if o['ncm'] == n) for n in cont}
        opcoes = sorted(sorted(cont), key=lambda n: (cont[n], ult[n]), reverse=True)   # mais notas; empate: a mais recente; depois pelo NCM
        para = opcoes[0]
        ex = next(o for o in sorted(dif, key=lambda o: _ord_data(o['data']), reverse=True) if o['ncm'] == para)
        cest = prod['cest'] or ex['cest']
        nfs = sorted(({'num': o['num'], 'serie': o['serie'], 'forn': o['forn'], 'data': o['data'], 'ncm': fmt(o['ncm']), 'valor': o['valor'],
                       'xprod': o['xprod'], 'diverge': o['ncm'] != sped} for o in occ), key=lambda z: (_ord_data(z['data']), z['num']))
        iguais = len({o['doc'] for o in occ if o['ncm'] == sped})
        itens.append({'id': cod, 'cod': cod, 'descr': prod['descr'], 'ncm_sped': fmt(sped) if sped else '', 'ncm_xml': fmt(para),
                      'opcoes': [{'v': n, 'rot': f"{fmt(n)} · {cont[n]} nota(s)"} for n in opcoes],
                      'xprod': ex['xprod'], 'nota_ex': f"NF {ex['num']} · {ex['forn']}", 'itens': len(dif), 'notas': len({o['doc'] for o in dif}),
                      'notas_iguais': iguais, 'valor': round(sum(o['valor'] for o in dif), 2), 'nfs': nfs,
                      'st': {n: efeito_st(sped, n, cest) for n in opcoes}})
    itens.sort(key=lambda z: z['descr'])
    return {'itens': itens, 'resumo': {'produtos': len(itens), 'conferidos': conferidos, 'sem_xml': sem_xml,
                                       'sem_ncm': sum(1 for i in itens if not _valido(_so(i['ncm_sped'])))}}


def aplicar_texto(texto, cods, xmls=None):
    """cods: lista de COD_ITEM (vai o NCM sugerido) ou dict {COD_ITEM: NCM escolhido}. Troca o campo 08 do 0200.
    -> (texto_novo, resumo)."""
    if isinstance(cods, dict):
        novo = {k: _so(v) for k, v in cods.items() if _valido(_so(v))}
    else:
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

# -*- coding: utf-8 -*-
"""Corretor do SPED Fiscal — VL_ABAT_NT dos itens (C170 campo 38) × total da nota (C100 campo 15).

Advertência do PVA: "O somatório do campo 38 VL_ABAT_NT dos registros C170 está diferente do valor informado no campo 15
do registro C100". O campo 15 do C100 é o abatimento não tributado e não comercial da nota (nas entradas da ZFM/ALC, o
desconto do ICMS dado pelo fornecedor); o campo 38 do C170 é o mesmo valor, item a item.

Preenche o campo 38 de cada item:
  • com o XML: o vICMSDeson do próprio item (quando a soma dos itens bate com o C100);
  • sem XML (ou soma diferente): rateio do C100 pelo valor do item (C170 campo 07), sobra de centavos no maior item.
O C100 não muda (fidelidade ao documento). Gera arquivo NOVO; o original nunca é alterado.
"""
import re

import difal_ro as dr
import desconto_xml as dx

CANC = {'02', '03', '04', '05'}


def _ch(s):
    return re.sub(r'\D', '', s or '')


def _notas(linhas):
    """[{i, chave, num, abat, itens:[{i, num, vl_item, abat}]}] — só C100 modelo 55 com C170 no leiaute com o campo 38."""
    out, cur = [], None
    for i, l in enumerate(linhas):
        if l.startswith('|C100|'):
            c = l.split('|')
            cur = None
            if len(c) > 15 and c[5] == '55' and c[6] not in CANC:
                cur = {'i': i, 'chave': _ch(c[9]), 'num': c[8], 'part': c[4], 'oper': c[2], 'abat': dr._n(c[15]), 'itens': []}
                out.append(cur)
        elif l.startswith('|C170|') and cur is not None:
            c = l.split('|')
            if len(c) < 40:                  # leiaute antigo, sem o campo 38
                cur['sem_campo'] = True
                continue
            cur['itens'].append({'i': i, 'num': c[2], 'vl_item': dr._n(c[7]), 'abat': dr._n(c[38])})
        elif l[:6] in ('|C990|', '|D001|'):
            cur = None
    return [n for n in out if n['itens'] and not n.get('sem_campo')]


def _rateio(total, itens):
    base = sum(max(it['vl_item'], 0) for it in itens)
    if base <= 0:
        return None
    vals = [round(total * max(it['vl_item'], 0) / base, 2) for it in itens]
    sobra = round(total - sum(vals), 2)
    if sobra:
        k = max(range(len(itens)), key=lambda j: itens[j]['vl_item'])
        vals[k] = round(vals[k] + sobra, 2)
    return vals


def analisar_texto(texto, xmls=None):
    xmls = xmls or {}
    linhas, _, _ = dr.dividir(texto)
    docs = []
    for n in _notas(linhas):
        soma = round(sum(it['abat'] for it in n['itens']), 2)
        if n['abat'] <= 0 or abs(soma - n['abat']) < 0.005:
            continue
        novos, fonte = None, 'rateio pelo valor do item'
        x = xmls.get(n['chave'])
        if x and x.get('itens') and 'erro' not in x:
            par = dx._casar([{'i': it['i'], 'num': it['num'], 'vl_item': it['vl_item']} for it in n['itens']], x['itens'])
            if len(par) == len(n['itens']):
                v = [round(par[it['i']].get('vdeson') or 0, 2) for it in n['itens']]
                if abs(sum(v) - n['abat']) <= 0.02:
                    sobra = round(n['abat'] - sum(v), 2)
                    if sobra:
                        k = max(range(len(v)), key=lambda j: v[j])
                        v[k] = round(v[k] + sobra, 2)
                    novos, fonte = v, 'desconto do ICMS de cada item no XML'
        if novos is None:
            novos = _rateio(n['abat'], n['itens'])
        if novos is None:
            continue
        docs.append({'id': n['i'], 'sel': n['chave'] or f"{n['num']}|{n['part']}", 'num': n['num'], 'part': n['part'],
                     'abat': n['abat'], 'soma': soma, 'itens': len(n['itens']), 'fonte': fonte,
                     'novos': [(it['i'], v) for it, v in zip(n['itens'], novos)]})
    return {'docs': docs, 'resumo': {'notas': len(docs), 'com_xml': sum(1 for d in docs if d['fonte'].startswith('desconto'))}}


def aplicar_texto(texto, xmls, ids=None):
    linhas, quebra, final_vazio = dr.dividir(texto)
    an = analisar_texto(texto, xmls)
    quer = set(ids) if ids is not None else None
    feitas = 0
    for d in an['docs']:
        if quer is not None and d['id'] not in quer:
            continue
        for i, v in d['novos']:
            c = linhas[i].split('|')
            c[38] = dr._f(v)
            linhas[i] = '|'.join(c)
        feitas += 1
    novo = dr.monta_arquivo(linhas, set(), {}, [], [], [], quebra, final_vazio)
    return novo, {'notas': feitas}

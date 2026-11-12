# -*- coding: utf-8 -*-
"""Produto de uso e consumo lançado como revenda / industrialização → CFOP de uso e consumo (Corretor do SPED Fiscal).

Como reconhece: o produto do item (0200 DESCR_ITEM ou o DESCR_COMPL do C170) diz "USO E CONSUMO" — é o produto genérico
que o escritório cadastra no Domínio (ex.: "PROD USO E CONSUMO") para material de uso e consumo. Mesmo assim ele chega no
SPED com CFOP de compra para revenda (x.102, x.403) ou para industrialização (x.101, x.401), por causa do acumulador da
nota (6001 COMPRA PARA REVENDA, 6002 COMPRA P/ PROD. ESTABELECIMENTO).

Para qual CFOP vai (Tabela de CFOP — Convênio s/nº de 1970, Anexo, redação do Ajuste SINIEF 07/2001):
  • compra com ICMS por substituição tributária — CFOP de origem x.401 / x.403, ou CST do ICMS terminado em 10, 30, 60
    ou 70 → 1.407 / 2.407 "Compra de mercadoria para uso ou consumo cuja mercadoria está sujeita ao regime de ST";
  • demais compras → 1.556 / 2.556 / 3.556 "Compra de material para uso ou consumo";
  • transferência (x.151, x.152, x.408, x.409) → 1.557 / 2.557 "Transferência de material para uso ou consumo".
O 1º dígito continua o mesmo (1 dentro do estado, 2 outro estado, 3 exterior; 3.407 não existe → 3.556).
Devolução, retorno, remessa e outras entradas (x.2xx, x.9xx…) não mudam.

Onde muda: C170 (CFOP do item) e C190 (resumo da nota, dividido quando só parte do grupo muda — mesma rotina do
combustível). Nada muda em valor de imposto nem no E110: crédito de ICMS em uso e consumo e o DIFAL de 2.556/2.407 são
conferidos depois, na etapa "Uso e consumo · DIFAL e crédito" (LC 87/1996, art. 33, I: uso e consumo só dá crédito a
partir de 2033). Gera arquivo NOVO; o original nunca é alterado.
"""
import re

import combustivel_cfop as cc

_COMPRA = {'101', '102', '111', '113', '116', '117', '118', '120', '121', '122', '401', '403'}
_TRANSF = {'151', '152', '408', '409'}
_DESC = re.compile(r'\bUSO\s*(E|/|&|\+)?\s*CONSUMO\b')
CANC = cc.CANC


def eh_uso_consumo(descr):
    return bool(_DESC.search(cc._norm(descr)))


def origem(cf):
    return len(cf or '') == 4 and cf[:1] in '123' and (cf[1:] in _COMPRA or cf[1:] in _TRANSF)


def novo_cfop(cf, cst):
    d, r = cf[:1], cf[1:]
    if r in _TRANSF:
        return d + '557'
    st = r in ('401', '403') or (cst or '')[-2:] in ('10', '30', '60', '70')
    return d + ('407' if st and d in '12' else '556')


def analisar_texto(texto, xmls=None):
    linhas = texto.splitlines()
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), None)
    if fim is not None:
        linhas = linhas[:fim + 1]
    p200, p150, docs = cc._estrutura(linhas)
    itens, notas = [], set()
    for k, d in enumerate(docs):
        c = d['c']
        if len(c) < 12 or c[2] != '0' or c[6] in CANC:
            continue
        for i, x in d['c170']:
            if len(x) < 15:
                continue
            cf = x[11]
            if not origem(cf):
                continue
            descr = p200.get(x[3], ('', ''))[0]
            compl = x[4] if len(x) > 4 else ''
            if not (eh_uso_consumo(descr) or eh_uso_consumo(compl)):
                continue
            para = novo_cfop(cf, x[10])
            itens.append({'doc': k, 'num': c[8], 'serie': c[7], 'forn': p150.get(c[4], c[4]), 'data': cc._data(c[10]), 'chave': d['chave'],
                          'id': f'{k}:{x[2]}', 'item': x[2], 'cod': x[3], 'descr': descr or compl, 'cfop_de': cf, 'cfop_para': para,
                          'cst': x[10], 'valor': round(cc._f(x[7]) - cc._f(x[8]), 2), 'icms': round(cc._f(x[15]), 2), 'cod_nat': x[12] if len(x) > 12 else '',
                          'motivo': ('transferência' if cf[1:] in _TRANSF else ('compra com ST' if para[1:] == '407' else 'compra'))})
            notas.add(k)
    return {'itens': itens, 'pendencias': [],
            'resumo': {'itens': len(itens), 'notas': len(notas), 'valor': round(sum(i['valor'] for i in itens), 2),
                       'com_icms': sum(1 for i in itens if i['icms'] > 0.004)}}


def aplicar_texto(texto, ids, xmls=None):
    """ids: lista de 'doc:NUM_ITEM'. -> (texto_novo, resumo)."""
    return cc.troca_cfop(texto, ids, xmls, analisar_texto, origem, novo_cfop, '', 'uso e consumo')


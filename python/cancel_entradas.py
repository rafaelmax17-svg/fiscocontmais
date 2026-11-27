# -*- coding: utf-8 -*-
"""Notas fiscais (NF-e/NFC-e) e CT-e de ENTRADA canceladas na SEFAZ e escrituradas no SPED Fiscal como regulares.

A situação de cada chave vem da consulta na SEFAZ autorizadora (nfe_chave.situacao: NfeConsultaProtocolo /
CTeConsultaProtocolo), guardada num arquivo de situações {chave: {situacao, cstat, motivo, quando, ...}}.

Correção:
  • documento de terceiros (IND_EMIT = 1) cancelado/denegado: sai do arquivo (C100/D100 e todos os registros filhos).
    Documento cancelado não tem validade jurídica e não dá direito a crédito (LC 87/1996, art. 23: o crédito depende
    de documento idôneo); o Guia Prático da EFD só prevê COD_SIT 02/04 para documento de emissão própria.
  • documento de emissão própria (IND_EMIT = 0, ex.: nota de entrada emitida pela empresa) cancelado/denegado: fica só
    com REG, IND_OPER, IND_EMIT, COD_MOD, COD_SIT (02 cancelado · 04 denegado), SER, (SUB), NUM_DOC e a chave,
    sem os registros filhos (Guia Prático, C100/D100, exceção 1).
  • o crédito que saiu ajusta a apuração: E110 campo 06 (ICMS dos C190/D190), 07 e 03 (ajustes C197/D197 dos
    documentos retirados); campos 11/13/14 e a obrigação 000 do E116 recalculados (difal_ro.aplica_apuracao).
"""
import json
import os
from decimal import Decimal

import difal_ro as dr

MOD_ENT = {'C100': ('55', '65'), 'D100': ('57', '67')}
SIT_REGULAR = ('00', '01', '06', '07', '08')


def _num(s):
    try:
        return float(str(s or '0').replace('.', '').replace(',', '.')) if ',' in str(s or '') else float(s or 0)
    except ValueError:
        return 0.0


def _fm(v):
    return f'{v:,.2f}'.replace(',', '§').replace('.', ',').replace('§', '.')


def ler_situacoes(caminho):
    if not caminho or not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, encoding='utf-8') as fh:
            d = json.load(fh)
        return d.get('itens', d) if isinstance(d, dict) else {}
    except Exception:
        return {}


def _docs(linhas):
    """Documentos de entrada (C100 NF-e/NFC-e e D100 CT-e) com o intervalo de linhas dos registros filhos."""
    out, cur = [], None

    def fecha():
        if cur:
            out.append(cur)
    for i, l in enumerate(linhas):
        reg = l[1:5] if l.startswith('|') else ''
        if reg in ('C100', 'D100'):
            fecha()
            cur = {'i': i, 'fim': i, 'reg': reg, 'f': l.split('|')}
            continue
        if cur:
            pfx = cur['reg'][:2]
            if reg.startswith(pfx) and reg > cur['reg'] and reg[:2] == pfx and int(reg[1:4]) < 200 and reg != cur['reg']:
                cur['fim'] = i
                continue
            fecha()
            cur = None
    fecha()
    res = []
    for d in out:
        f = d['f']
        if len(f) < 12 or f[2] != '0':
            continue
        mod, sit = f[5], f[6]
        if mod not in MOD_ENT[d['reg']]:
            continue
        ch = (f[9] if d['reg'] == 'C100' else f[10]).strip()
        if len(ch) != 44 or not ch.isdigit():
            continue
        cred = c197c = c197d = 0.0
        for j in range(d['i'] + 1, d['fim'] + 1):
            g = linhas[j].split('|')
            r = g[1] if len(g) > 1 else ''
            if r in ('C190', 'D190') and len(g) > 7 and g[3][:1] in '123':
                cred += _num(g[7])
            elif r in ('C197', 'D197') and len(g) > 7:
                cod = g[2].strip()
                if len(cod) >= 4 and cod[3] in '0345678':
                    if cod[2] in '345':
                        c197d += _num(g[7])
                    elif cod[2] in '012':
                        c197c += _num(g[7])
        res.append({'i': d['i'], 'fim': d['fim'], 'reg': d['reg'], 'ind_emit': f[3], 'mod': mod, 'sit': sit,
                    'ser': f[7], 'num': f[9] if d['reg'] == 'D100' else f[8], 'chave': ch,
                    'part': f[4], 'dt': (f[11] if d['reg'] == 'D100' else f[10]),
                    'valor': _num(f[15] if d['reg'] == 'D100' else f[12]), 'cred': round(cred, 2),
                    'c197c': round(c197c, 2), 'c197d': round(c197d, 2)})
    return res


def chaves_entrada(texto):
    linhas, _, _ = dr.dividir(texto)
    return [d['chave'] for d in _docs(linhas) if d['sit'] in SIT_REGULAR]


def analisar_texto(texto, situ):
    linhas, _, _ = dr.dividir(texto)
    nomes = {}
    for l in linhas:
        if l.startswith('|0150|'):
            f = l.split('|')
            nomes[f[2]] = f[3]
    docs = [d for d in _docs(linhas) if d['sit'] in SIT_REGULAR]
    itens, sem, conferidas = [], 0, 0
    for d in docs:
        s = situ.get(d['chave']) or {}
        st = s.get('situacao')
        if not st or st == 'erro':
            sem += 1
            continue
        conferidas += 1
        if st in ('cancelada', 'denegada'):
            itens.append({**d, 'id': d['chave'], 'situacao': st, 'motivo': s.get('motivo', ''), 'quando': s.get('quando', ''),
                          'fornecedor': nomes.get(d['part'], d['part']), 'tipo': 'CT-e' if d['reg'] == 'D100' else ('NFC-e' if d['mod'] == '65' else 'NF-e')})
    return {'itens': itens, 'total': len(docs), 'conferidas': conferidas, 'sem_consulta': sem,
            'nao_encontradas': sum(1 for d in docs if (situ.get(d['chave']) or {}).get('situacao') == 'nao_encontrada')}


def aplicar_texto(texto, situ, ids, e116=None):
    linhas, quebra, final_vazio = dr.dividir(texto)
    an = analisar_texto(texto, situ)
    alvo = [d for d in an['itens'] if d['id'] in set(ids)]
    res = {'notas': 0, 'retiradas': 0, 'proprias': 0, 'credito': 0.0, 'avisos': [], 'e116': '', 'e110_antes': None, 'e110_depois': None}
    if not alvo:
        return texto, res
    remover = set()
    d06 = d07 = d03 = Decimal('0')
    for d in alvo:
        for j in range(d['i'] + 1, d['fim'] + 1):
            remover.add(j)
        if d['ind_emit'] == '1':
            remover.add(d['i'])
            res['retiradas'] += 1
        else:
            f = linhas[d['i']].split('|')
            novo = [''] * len(f)
            sit = '04' if d['situacao'] == 'denegada' else '02'
            if d['reg'] == 'C100':
                keep = {1: f[1], 2: f[2], 3: f[3], 5: f[5], 6: sit, 7: f[7], 8: f[8], 9: f[9]}
            else:
                keep = {1: f[1], 2: f[2], 3: f[3], 5: f[5], 6: sit, 7: f[7], 8: f[8], 9: f[9], 10: f[10]}
            for k, v in keep.items():
                novo[k] = v
            linhas[d['i']] = '|'.join(novo)
            res['proprias'] += 1
        d06 -= Decimal(str(d['cred']))
        d07 -= Decimal(str(d['c197c']))
        d03 -= Decimal(str(d['c197d']))
        res['notas'] += 1
        res['credito'] += d['cred'] + d['c197c']
    deltas = {k: float(v) for k, v in ((6, d06), (7, d07), (3, d03)) if abs(v) >= Decimal('0.005')}
    e110, cab = None, {}
    for i, l in enumerate(linhas):
        if l.startswith('|0000|'):
            cab['dt_ini'] = l.split('|')[4]
        elif l.startswith('|E110|') and i not in remover:
            e110 = {'i': i}
    novas_e116, erro = dr.aplica_apuracao(linhas, e110, deltas, {'e116': e116 or {}}, cab, remover, res)
    if erro:
        res['erro'] = erro
        return texto, res
    res['credito'] = round(res['credito'], 2)
    return dr.monta_arquivo(linhas, remover, {}, [], [], novas_e116, quebra, final_vazio), res

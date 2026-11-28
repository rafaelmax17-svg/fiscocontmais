# -*- coding: utf-8 -*-
"""DARE × ajustes de crédito da apuração (E111) — Rondônia.

Os créditos de ICMS recolhido por DARE (ex.: RO020003, ICMS antecipado) trazem o número do lançamento do DARE na
descrição do E111 (ou no E112, NUM_DA). Com os DAREs PAGOS lidos pelo módulo de DARE (Conta Corrente do Portal do
Contribuinte da SEFIN-RO), a conferência mostra:
  • ok: DARE pago com o mesmo valor do ajuste;
  • diferente: DARE pago com valor diferente do ajuste → o ajuste passa ao valor pago (principal, sem multa/juros);
  • não pago: o número do ajuste não aparece entre os DAREs pagos lidos (informativo: pode ter sido pago fora do
    período consultado);
  • sem crédito: DARE de ICMS antecipado pago, com referência no mês da apuração, que nenhum ajuste cita. Fica para a
    equipe decidir (desmarcado): só dá crédito o antecipado sem encerramento de tributação.
"""
import json
import os
import re
from decimal import Decimal

import difal_ro as dr


def _n(s):
    try:
        return float(str(s or '0').replace('.', '').replace(',', '.')) if ',' in str(s or '') else float(s or 0)
    except ValueError:
        return 0.0


def _fm(v):
    return f'{v:,.2f}'.replace(',', '§').replace('.', ',').replace('§', '.')


def _so(s):
    return re.sub(r'\D', '', str(s or '')).lstrip('0')


def ler_pagos(caminho):
    if not caminho or not os.path.exists(caminho):
        return None
    try:
        with open(caminho, encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return None


def _ajustes(linhas):
    out, cur = [], None
    for i, l in enumerate(linhas):
        if l.startswith('|E111|'):
            f = l.split('|')
            cur = {'i': i, 'cod': f[2].strip(), 'desc': f[3].strip(), 'valor': _n(f[4]), 'refs': set(re.findall(r'\d{12,16}', f[3]))}
            out.append(cur)
        elif l.startswith('|E112|') and cur:
            nd = re.sub(r'\D', '', l.split('|')[2])
            if len(nd) >= 10:
                cur['refs'].add(nd)
        elif not l.startswith('|E113|'):
            cur = None
    return out


def analisar_texto(texto, dados):
    linhas, _, _ = dr.dividir(texto)
    mes = ''
    for l in linhas:
        if l.startswith('|0000|'):
            d = l.split('|')[4]
            mes = f'{d[2:4]}/{d[4:8]}'
            break
    pagos = (dados or {}).get('pagos') or []
    por_nr = {}
    for p in pagos:
        por_nr.setdefault(_so(p.get('nr')), []).append(p)
    itens, citados = [], set()
    for a in _ajustes(linhas):
        if a['cod'][3:4] not in ('2', '3') or not a['refs']:
            continue
        ps = [p for r in a['refs'] for p in por_nr.get(_so(r), [])]
        citados.update(_so(r) for r in a['refs'])
        curtos = sorted(r for r in a['refs'] if not any(o != r and r.startswith(o) for o in a['refs']))   # E112 pode repetir com sufixo
        nrs = ', '.join(curtos)
        if not ps:
            itens.append({'id': f"aj|{a['cod']}|{nrs}", 'tipo': 'nao_pago', 'cod': a['cod'], 'nrs': nrs, 'ajuste': a['valor'], 'pago': 0.0, 'i': a['i'], 'desc': a['desc']})
            continue
        principal = round(sum(_n(p.get('valorN', p.get('valor'))) for p in ps), 2)
        tipo = 'ok' if abs(principal - a['valor']) <= 0.05 else 'diferente'
        itens.append({'id': f"aj|{a['cod']}|{nrs}", 'tipo': tipo, 'cod': a['cod'], 'nrs': nrs, 'ajuste': a['valor'], 'pago': principal,
                      'pagoEm': ', '.join(sorted({str(p.get('pagoEm', '')) for p in ps})), 'i': a['i'], 'desc': a['desc']})
    for p in pagos:
        if _so(p.get('nr')) in citados:
            continue
        if not re.search(r'antecip', str(p.get('rec', '')), re.I) or (mes and mes not in str(p.get('ref', ''))):
            continue
        itens.append({'id': f"novo|{_so(p.get('nr'))}|{p.get('parc', '')}", 'tipo': 'sem_credito', 'cod': 'RO020003', 'nrs': str(p.get('nr')),
                      'ajuste': 0.0, 'pago': _n(p.get('valorN', p.get('valor'))), 'pagoEm': p.get('pagoEm', ''), 'rec': p.get('rec', ''), 'ref': p.get('ref', '')})
    return {'itens': itens, 'mes': mes, 'tem_pagos': bool(pagos), 'meses': (dados or {}).get('meses') or []}


def aplicar_texto(texto, dados, ids, e116=None):
    linhas, quebra, final_vazio = dr.dividir(texto)
    an = analisar_texto(texto, dados)
    ids = set(ids)
    res = {'acertados': 0, 'incluidos': 0, 'credito': 0.0, 'avisos': [], 'e116': ''}
    d08 = d09 = Decimal('0')
    novas = []
    for x in an['itens']:
        if x['id'] not in ids:
            continue
        if x['tipo'] == 'diferente':
            f = linhas[x['i']].split('|')
            dv = Decimal(str(x['pago'])) - Decimal(str(x['ajuste']))
            f[4] = f'{x["pago"]:.2f}'.replace('.', ',')
            linhas[x['i']] = '|'.join(f)
            if x['cod'][3] == '2':
                d08 += dv
            else:
                d09 += dv
            res['acertados'] += 1
            res['credito'] += float(dv)
        elif x['tipo'] == 'sem_credito' and x['pago'] > 0:
            valor = f"{x['pago']:.2f}".replace('.', ',')
            novas.append(f"|E111|RO020003|DARE ICMS Antecipado n. {x['nrs']}|{valor}|")
            d08 += Decimal(str(x['pago']))
            res['incluidos'] += 1
            res['credito'] += x['pago']
    deltas = {k: float(v) for k, v in ((8, d08), (9, d09)) if abs(v) >= Decimal('0.005')}
    if not deltas and not novas:
        return texto, res
    e110, cab = None, {}
    for i, l in enumerate(linhas):
        if l.startswith('|0000|'):
            cab['dt_ini'] = l.split('|')[4]
        elif l.startswith('|E110|'):
            e110 = {'i': i}
    novas_e116, erro = dr.aplica_apuracao(linhas, e110, deltas, {'e116': e116 or {}}, cab, set(), res)
    if erro:
        res['erro'] = erro
        return texto, res
    res['credito'] = round(res['credito'], 2)
    return dr.monta_arquivo(linhas, set(), {}, [], novas, novas_e116, quebra, final_vazio), res


def etapa(texto, dados):
    a = analisar_texto(texto, dados)
    if dados is None:
        return {'key': 'dareaj', 'titulo': 'DARE × ajustes de crédito', 'desc': 'os DAREs pagos desta empresa não foram lidos (módulo de DARE)',
                'qtd': 'não conferido', 'valor': '', 'badge': 'consultar os pagos', 'tipo': 'sem_xml', 'grupos': []}
    if not a['itens']:
        return {'key': 'dareaj', 'titulo': 'DARE × ajustes de crédito',
                'desc': 'nenhum ajuste de crédito com número de DARE' if a['tem_pagos'] or not a['meses'] else 'nenhum DARE pago lido para esta empresa nos meses da apuração',
                'qtd': 'nada encontrado', 'valor': '', 'badge': 'sem correção', 'tipo': 'zero', 'grupos': []}
    rot = {'ok': 'OK', 'diferente': 'DIFERENTE', 'nao_pago': 'NÃO ACHADO NOS PAGOS'}
    l1, l2 = [], []
    for x in a['itens']:
        if x['tipo'] == 'sem_credito':
            l2.append({'sel': x['id'], 'nota': f"DARE {x['nrs']}", 'valor': x['pago'], 'marcado': False,
                       'det': f"{x['rec'][:50]} · ref. {x['ref']} · pago em {x['pagoEm']} · lança E111 RO020003 com o número do DARE"
                              ' (confirme que é antecipado SEM encerramento de tributação)', 'busca': x['nrs']})
            continue
        det = f"{rot[x['tipo']]} · DARE {x['nrs']}"
        if x['tipo'] == 'ok':
            det += f" · pago em {x['pagoEm']} · R$ {_fm(x['pago'])} = ajuste"
        elif x['tipo'] == 'diferente':
            det += f" · pago R$ {_fm(x['pago'])} × ajuste R$ {_fm(x['ajuste'])} → ajuste passa a R$ {_fm(x['pago'])}"
        else:
            det += ' · não está entre os DAREs pagos lidos (pode ter sido pago fora dos meses consultados)'
        l1.append({'sel': x['id'], 'nota': x['cod'], 'valor': x['ajuste'], 'marcado': x['tipo'] == 'diferente',
                   'bloqueado': x['tipo'] != 'diferente', 'det': det, 'busca': x['nrs']})
    grupos = []
    if l1:
        grupos.append({'id': 'dareaj', 'titulo': 'Ajustes de crédito com número de DARE', 'sugestao': 'acertar o valor pelo DARE pago', 'linhas': l1})
    if l2:
        grupos.append({'id': 'dareajn', 'titulo': 'DARE de antecipado pago e sem ajuste no SPED (crédito que pode estar faltando)',
                       'sugestao': 'lançar o crédito', 'linhas': l2})
    dif = sum(x['pago'] - x['ajuste'] for x in a['itens'] if x['tipo'] == 'diferente')
    novo = sum(x['pago'] for x in a['itens'] if x['tipo'] == 'sem_credito')
    meses = ', '.join(f"{m[4:]}/{m[:4]}" for m in a['meses'])
    return {'key': 'dareaj', 'titulo': 'DARE × ajustes de crédito',
            'desc': f"Ajustes com número de DARE conferidos com os DAREs pagos lidos no Portal do Contribuinte ({meses})." if meses else
                    'Ajustes com número de DARE conferidos com os DAREs pagos lidos no Portal do Contribuinte.',
            'qtd': f"{len(l1)} ajuste(s) · {len(l2)} DARE(s) sem crédito",
            'valor': (f"{'+' if dif + novo >= 0 else '−'} R$ {_fm(abs(dif + novo))} possível" if (dif or novo) else ''),
            'badge': 'decidir' if (l2 or any(not l.get('bloqueado') for l in l1)) else 'verificar', 'tipo': 'decidir', 'grupos': grupos}

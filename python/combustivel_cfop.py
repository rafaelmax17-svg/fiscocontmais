# -*- coding: utf-8 -*-
"""Combustível e lubrificante lançados como uso e consumo — CFOP x.556 / x.407 → x.653 (Corretor do SPED, só Admin).

Por que: o CFOP 1.556/2.556 (material de uso ou consumo) e o 1.407/2.407 (uso e consumo com ST) são genéricos. Para
combustível e lubrificante comprados por consumidor ou usuário final existe o código próprio do grupo 1.650/2.650:
  1.653 / 2.653 / 3.653 — "Compra de combustível ou lubrificante por consumidor ou usuário final"
(Tabela de CFOP — Convênio s/nº de 1970, Anexo, na redação do Ajuste SINIEF 07/2001). O 1º dígito continua o mesmo:
1 (dentro do estado), 2 (outro estado), 3 (exterior).

Como reconhece o produto (sem palpite pela descrição quando há NCM):
  • combustível: NCM 2710.12 (gasolinas), 2710.19.2 (querosene/diesel), 2710.20 (diesel com biodiesel), 2711 (GLP/GNV),
    3826.00 (biodiesel) e 2207 (etanol) quando a descrição diz ETANOL, ÁLCOOL COMBUSTÍVEL ou HIDRATADO/ANIDRO;
  • lubrificante: NCM 2710.19.3 (óleos lubrificantes), 2710.19.9 (outros óleos/graxas) e 3403 (preparações lubrificantes);
  • sem NCM: só pela descrição (GASOLINA, DIESEL, ETANOL, GNV, GLP, ÓLEO LUBRIFICANTE, GRAXA).
  Filtro de combustível (NCM 8421), ARLA 32 (3102) e aditivos (3811) NÃO entram: não são combustível nem lubrificante.

Onde muda: C170 (CFOP do item) e C190 (o resumo da nota). Se só parte dos itens de um C190 muda, o C190 é dividido:
BC, ICMS, ST e IPI vêm dos próprios C170; valor da operação e redução de base em proporção ao valor dos itens.
Nota sem C170: usa os itens do XML anexado — se todos forem combustível/lubrificante, troca o CFOP do C190 inteiro.
Nada muda em valor de imposto nem no E110. Gera arquivo NOVO; o original nunca é alterado.
"""
import json
import os
import re
from collections import defaultdict

import difal_ro as dr

CFOP_ORIGEM = ('556', '407')
CANC = {'02', '03', '04', '05'}
_DESC_COMB = re.compile(r'\b(GASOLINA|DIESEL|S-?10\b|S-?500\b|ETANOL|GNV|GLP|QUEROSENE|BIODIESEL|ALCOOL\s+(COMB|HIDRAT|ANIDRO))')
_DESC_LUB = re.compile(r'\b(OLEO\s+(LUB|MOTOR|HIDRAUL|DE\s+MOTOR|TRANSMISS|CAMBIO)|LUBRIFICANTE|GRAXA|FLUIDO\s+DE\s+FREIO)')
_DESC_NAO = re.compile(r'\b(FILTRO|ARLA|ADITIVO|BOMBA|BICO|MANGUEIRA|TAMPA|GALAO|VASILHAME|EMBALAGEM)\b')


def _norm(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'\s+', ' ', s).strip()


def classifica(ncm, descr):
    """-> (tipo 'combustivel'|'lubrificante'|None, motivo)."""
    n = re.sub(r'\D', '', ncm or '')
    d = _norm(descr)
    if len(n) >= 4:
        if n.startswith(('271012', '2710192', '271020', '2711', '382600')):
            return 'combustivel', f'NCM {n}: combustível'
        if n.startswith('2207') and re.search(r'ETANOL|ALCOOL\s+(COMB|HIDRAT|ANIDRO)|HIDRATADO|ANIDRO', d):
            return 'combustivel', f'NCM {n} + descrição de etanol combustível'
        if n.startswith(('2710193', '2710199', '3403')):
            return 'lubrificante', f'NCM {n}: óleo lubrificante / graxa'
        return None, ''
    if _DESC_NAO.search(d):
        return None, ''
    if _DESC_COMB.search(d):
        return 'combustivel', 'sem NCM: descrição de combustível'
    if _DESC_LUB.search(d):
        return 'lubrificante', 'sem NCM: descrição de lubrificante'
    return None, ''


def _f(v):
    try:
        return float(str(v or '0').replace(',', '.'))
    except ValueError:
        return 0.0


def _s(v):
    return f'{v:.2f}'.replace('.', ',')


def _aliq(v):
    return round(_f(v), 2)


def _data(d):
    return f'{d[:2]}/{d[2:4]}/{d[4:8]}' if len(d or '') == 8 else (d or '')


def _estrutura(linhas):
    p200, p150, docs, cur = {}, {}, [], None
    for i, l in enumerate(linhas):
        c = l.split('|')
        if len(c) < 3:
            continue
        r = c[1]
        if r == '0200' and len(c) > 8:
            p200[c[2]] = (c[3], c[8])
        elif r == '0150' and len(c) > 3:
            p150[c[2]] = c[3]
        elif r == 'C100':
            cur = {'i': i, 'c': c, 'c170': [], 'c190': [], 'c191': set(), 'c197': [], 'chave': c[9] if len(c) > 9 else ''}
            docs.append(cur)
        elif cur is not None and r == 'C170':
            cur['c170'].append((i, c))
        elif cur is not None and r == 'C190':
            cur['c190'].append((i, c))
        elif cur is not None and r == 'C191':
            if cur['c190']:
                cur['c191'].add(cur['c190'][-1][0])
        elif cur is not None and r == 'C197':
            cur['c197'].append(c)
        elif cur is not None and not (r.startswith('C1') and r != 'C100'):
            cur = None                                  # C300, C400, D…, E…: acabou a nota
    return p200, p150, docs


def _novo_cfop(cf):
    return cf[:1] + '653'


def analisar_texto(texto, xmls=None):
    xmls = xmls or {}
    linhas = texto.splitlines()
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), None)
    if fim is not None:
        linhas = linhas[:fim + 1]
    p200, p150, docs = _estrutura(linhas)
    itens, pend, notas_ok = [], [], set()
    for k, d in enumerate(docs):
        c = d['c']
        if len(c) < 12 or c[2] != '0' or c[6] in CANC:
            continue
        nota = {'doc': k, 'num': c[8], 'serie': c[7], 'forn': p150.get(c[4], c[4]), 'data': _data(c[10]), 'chave': d['chave']}
        tem_difal = any(len(x) > 2 and x[2] == 'RO40000002' for x in d['c197'])
        if d['c170']:
            for i, x in d['c170']:
                cf = x[11] if len(x) > 11 else ''
                if cf[1:] not in CFOP_ORIGEM:
                    continue
                descr, ncm = p200.get(x[3], (x[4] if len(x) > 4 else '', ''))
                tipo, mot = classifica(ncm, descr or (x[4] if len(x) > 4 else ''))
                if not tipo:
                    continue
                itens.append({**nota, 'id': f'{k}:{x[2]}', 'item': x[2], 'cod': x[3], 'descr': descr or x[4], 'ncm': ncm,
                              'cfop_de': cf, 'cfop_para': _novo_cfop(cf), 'cst': x[10], 'valor': round(_f(x[7]) - _f(x[8]), 2),
                              'tipo': tipo, 'motivo': mot, 'origem': 'C170', 'tem_difal': tem_difal})
                notas_ok.add(k)
            continue
        alvo = [c190 for _, c190 in d['c190'] if len(c190) > 3 and c190[3][1:] in CFOP_ORIGEM]
        if not alvo:
            continue
        x = xmls.get(re.sub(r'\D', '', d['chave'] or ''))
        if not x or not x.get('itens'):
            continue
        cls = [(it, *classifica(it.get('ncm'), it.get('xprod'))) for it in x['itens']]
        comb = [t for t in cls if t[1]]
        if not comb:
            continue
        if len(comb) < len(cls) or len(alvo) < len(d['c190']):
            pend.append({**nota, 'motivo': f'{len(comb)} de {len(cls)} item(ns) da nota são combustível/lubrificante e a nota não tem C170: '
                                             'sem os itens no SPED não dá para separar o C190. Lance os C170 ou corrija no sistema de origem.'})
            continue
        for it, tipo, mot in comb:
            itens.append({**nota, 'id': f'{k}:*', 'item': it.get('n', ''), 'cod': it.get('cprod', ''), 'descr': it.get('xprod', ''),
                          'ncm': it.get('ncm', ''), 'cfop_de': alvo[0][3], 'cfop_para': _novo_cfop(alvo[0][3]), 'cst': alvo[0][2],
                          'valor': round(it.get('valor_oper') or 0, 2), 'tipo': tipo, 'motivo': mot + ' (pelo XML; nota sem C170)',
                          'origem': 'XML', 'tem_difal': tem_difal})
        notas_ok.add(k)
    return {'itens': itens, 'pendencias': pend,
            'resumo': {'itens': len(itens), 'notas': len(notas_ok), 'valor': round(sum(i['valor'] for i in itens), 2),
                       'combustivel': sum(1 for i in itens if i['tipo'] == 'combustivel'),
                       'lubrificante': sum(1 for i in itens if i['tipo'] == 'lubrificante'),
                       'com_difal': len({i['doc'] for i in itens if i['tem_difal']}), 'pendencias': len(pend)}}


def aplicar_texto(texto, ids, xmls=None):
    """ids: lista de 'doc:NUM_ITEM' (C170) ou 'doc:*' (nota sem C170, pelo XML). -> (texto_novo, resumo)."""
    import fiscal_core as fc
    linhas, quebra, final_vazio = dr.dividir(texto)
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), None)
    assinado = fim is not None and fim < len(linhas) - 1
    if assinado:
        linhas = linhas[:fim + 1]
        final_vazio = True
    an = analisar_texto(quebra.join(linhas) + quebra, xmls)
    validos = {i['id'] for i in an['itens']}
    ids = [x for x in ids if x in validos]
    _, _, docs = _estrutura(linhas)
    por_doc = defaultdict(set)
    for x in ids:
        k, item = x.split(':', 1)
        por_doc[int(k)].add(item)
    res = {'itens': 0, 'notas': 0, 'c190_divididos': 0, 'avisos': []}
    trocas, inserir, apagar = {}, {}, set()           # índice → nova linha · índice → linhas novas depois dele · índices a apagar
    for k, sel in por_doc.items():
        d = docs[k]
        if '*' in sel:                                  # nota sem C170: o C190 inteiro vai para x.653
            for i, c in d['c190']:
                if len(c) > 3 and c[3][1:] in CFOP_ORIGEM:
                    n = c[:]; n[3] = _novo_cfop(c[3]); trocas[i] = '|'.join(n)
            res['notas'] += 1
            res['itens'] += sum(1 for x in an['itens'] if x['doc'] == k)
            continue
        # C170: grupos do C190 (CST, CFOP, alíquota) — o que muda e o total de cada grupo
        grupos = defaultdict(lambda: {'tot': 0.0, 'mov': 0.0, 'bc': 0.0, 'icms': 0.0, 'bcst': 0.0, 'st': 0.0, 'ipi': 0.0, 'n_tot': 0, 'n_mov': 0})
        for i, c in d['c170']:
            if len(c) < 15:
                continue
            g = grupos[(c[10], c[11], _aliq(c[14]))]
            v = _f(c[7]) - _f(c[8])
            g['tot'] += v; g['n_tot'] += 1
            if c[2] in sel and c[11][1:] in CFOP_ORIGEM:
                g['mov'] += v; g['n_mov'] += 1
                g['bc'] += _f(c[13]); g['icms'] += _f(c[15])
                g['bcst'] += _f(c[16]) if len(c) > 16 else 0; g['st'] += _f(c[18]) if len(c) > 18 else 0
                g['ipi'] += _f(c[24]) if len(c) > 24 else 0
        # C190 com C191 (FCP) só muda se o grupo inteiro mudar (dividir o C191 não é seguro)
        bloqueados = set()
        for i, c in d['c190']:
            key = (c[2], c[3], _aliq(c[4]))
            g = grupos.get(key)
            if g and g['n_mov'] and g['n_mov'] < g['n_tot'] and i in d['c191']:
                bloqueados.add(key)
                res['avisos'].append(f'NF {d["c"][8]}: o resumo CST {c[2]}/CFOP {c[3]} tem C191 (FCP) e só parte dos itens é combustível; '
                                     'esses itens ficaram como estavam.')
        mudou = False
        for i, c in d['c170']:
            if len(c) > 11 and c[2] in sel and c[11][1:] in CFOP_ORIGEM and (c[10], c[11], _aliq(c[14])) not in bloqueados:
                n = c[:]; n[11] = _novo_cfop(c[11]); trocas[i] = '|'.join(n)
                res['itens'] += 1; mudou = True
        existentes = {(c[2], c[3], _aliq(c[4])): (i, c) for i, c in d['c190']}
        for i, c in d['c190']:
            key = (c[2], c[3], _aliq(c[4]))
            g = grupos.get(key)
            if not g or not g['n_mov'] or key in bloqueados:
                continue
            novo_cf = _novo_cfop(c[3])
            destino = existentes.get((c[2], novo_cf, key[2]))
            if g['n_mov'] == g['n_tot'] and not destino:
                n = c[:]; n[3] = novo_cf; trocas[i] = '|'.join(n)
                continue
            # parte que muda (ou o grupo inteiro, quando já existe um C190 x.653 igual para somar)
            inteiro = g['n_mov'] == g['n_tot']
            prop = 1.0 if inteiro else (g['mov'] / g['tot'] if g['tot'] else 0.0)
            vals = [_f(x) for x in c[5:12]]           # VL_OPR, VL_BC, VL_ICMS, VL_BC_ST, VL_ICMS_ST, VL_RED_BC, VL_IPI
            parte = vals[:] if inteiro else [round(vals[0] * prop, 2), round(g['bc'], 2), round(g['icms'], 2), round(g['bcst'], 2),
                                               round(g['st'], 2), round(vals[5] * prop, 2), round(g['ipi'], 2)]
            if destino:
                di, dc = destino
                base = trocas.get(di, '|'.join(dc)).split('|')
                for j in range(7):
                    base[5 + j] = _s(_f(base[5 + j]) + parte[j])
                trocas[di] = '|'.join(base)
            else:
                n = c[:]; n[3] = novo_cf
                for j in range(7):
                    n[5 + j] = _s(parte[j])
                inserir.setdefault(i, []).append('|'.join(n))
            if inteiro:
                apagar.add(i)
            else:
                resto = c[:]
                for j in range(7):
                    resto[5 + j] = _s(vals[j] - parte[j])
                trocas[i] = '|'.join(resto)
                res['c190_divididos'] += 1
        if mudou:
            res['notas'] += 1
    novo = []
    for i, l in enumerate(linhas):
        if i in apagar:
            novo.extend(inserir.get(i, []))
            continue
        novo.append(trocas.get(i, l))
        novo.extend(inserir.get(i, []))
    linhas = novo
    if res['itens']:
        linhas = fc._recalcula_fechamentos_bloco(linhas)
        linhas = fc._recalcula_bloco9_global(linhas)
    if any(i['tem_difal'] for i in an['itens'] if i['id'] in set(ids)):
        res['avisos'].append('Há nota com DIFAL de uso e consumo lançado (C197 RO40000002). Combustível e lubrificante não são '
                             'uso e consumo: confira esse DIFAL em "Uso e consumo · DIFAL e crédito".')
    if assinado:
        res['avisos'].append('O arquivo estava assinado no PVA: a assinatura foi retirada (ela deixa de valer com a alteração). Valide e assine de novo no PVA.')
    depois = analisar_texto(quebra.join(linhas) + quebra, xmls)
    res['restantes'] = depois['resumo']['itens']
    return quebra.join(linhas) + (quebra if final_vazio else ''), res


def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    sped, js = opt('--sped'), opt('--json')
    if not sped or not js:
        print('uso: combustivel-cfop --sped ARQ.txt [--xmls PASTA|ZIP] --json saida.json [--aplicar ids.json --saida novo.txt]')
        return 1
    try:
        xmls = {}
        if opt('--xmls'):
            from xml_entradas import ler_xmls
            xmls, _, _ = ler_xmls([p for p in opt('--xmls').split(os.pathsep) if p])
        texto, enc = dr._ler(sped)
        if opt('--aplicar'):
            with open(opt('--aplicar'), encoding='utf-8') as fh:
                ids = json.load(fh)
            novo, res = aplicar_texto(texto, ids, xmls)
            tmp = opt('--saida') + '.parcial'
            with open(tmp, 'w', encoding=enc, newline='') as fh:
                fh.write(novo)
            os.replace(tmp, opt('--saida'))
        else:
            res = analisar_texto(texto, xmls)
    except Exception as e:  # pragma: no cover
        res = {'erro': f'Falha ao processar: {e}'}
    tmp = js + '.parcial'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False)
    os.replace(tmp, js)
    return 0

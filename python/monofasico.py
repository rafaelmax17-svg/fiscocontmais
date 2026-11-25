# -*- coding: utf-8 -*-
"""
Correção do PIS/COFINS monofásico na EFD-Contribuições (Admin) — botão "⚡ Corrigir monofásico".

Pedido do Rafael (15/10/2026). O Radar de Oportunidades já ACHA o monofásico pago a mais nos meses
passados; aqui o mesmo diagnóstico vira CORREÇÃO do arquivo do mês, antes de transmitir:

  * itens de VENDA (revenda) com NCM de incidência monofásica e CST 01 passam para CST 04
    (operação tributável monofásica — revenda a alíquota zero), com base, alíquota e valor zerados;
    registros: C170 (NF-e por item), C181/C185 (NF-e consolidada, NCM no C180) e C175 de NFC-e
    com CFOP de combustível (o C175 não traz NCM; o CFOP de combustível já identifica o produto);
  * C100: VL_PIS/VL_COFINS da nota reduzidos no mesmo valor;
  * apuração: M210/M610 (receita, base e contribuição), M200/M600 recalculados, M205/M605 (DARF);
  * receita a alíquota zero informada no M400/M410 e M800/M810 com a natureza da Tabela 4.3.10
    (001 combustíveis, 002 fármacos e perfumaria, 003 veículos/autopeças/pneus);
  * contadores refeitos. O arquivo original nunca é alterado.

Fica de FORA (não é seguro decidir sozinho): CST 02 (alíquota diferenciada = indústria/importador),
CFOP de produção própria, bebidas frias (regra por embalagem/ex-tarifário), NFC-e sem CFOP de
combustível (o C175 não tem NCM) e regime não cumulativo quando os créditos descontados passariam
da contribuição (mexe no saldo de créditos — ajuste manual).

Base legal: Lei 9.718/1998, arts. 4º e 5º (combustíveis/álcool); Lei 10.147/2000, arts. 1º e 2º
(farmacêuticos/perfumaria); Lei 10.485/2002 (pneus/autopeças); Tabela 4.3.10 da EFD-Contribuições.
"""
import json
import os
import re
import sys
from collections import defaultdict

import efd_corretor as ec
from oportunidades import REGRAS_MONOFASICO, CFOP_COMBUSTIVEL, _regra_ncm

# natureza da receita (Tabela 4.3.10) por grupo — revenda a alíquota zero
NAT_REC = {
    'Produtos farmacêuticos': '002',
    'Perfumaria, toucador e higiene pessoal': '002',
    'Pneumáticos (pneus novos e câmaras de ar)': '003',
    'Combustíveis (diesel, GLP, gasolina)': '001',
    'Álcool para fins carburantes': '001',
}
NAT_DESC = {'001': 'Revenda de combustíveis – alíquota zero', '002': 'Revenda de fármacos e perfumarias – alíquota zero',
            '003': 'Revenda de veículos, máquinas e autopeças – alíquota zero'}
GRUPO_COMB = REGRAS_MONOFASICO[3]['grupo']
# CFOP de produção própria / industrialização: quem fabrica não tem alíquota zero na revenda
_CFOP_PRODUCAO = {'101', '103', '105', '109', '111', '113', '116', '118', '122', '124', '125', '401', '402', '651', '652', '653', '654'}
_ZERO, _ZERO_ALIQ = '0,00', '0,0000'


def _regime(aliq_pis):
    """0,65% -> cumulativo (COD_CONT 51); 1,65% -> não cumulativo (01). Outra alíquota: não mexe."""
    a = round(aliq_pis, 2)
    if a == 0.65:
        return 'cum'
    if a == 1.65:
        return 'nc'
    return None


def _ler_arquivo(caminho):
    with open(caminho, 'r', encoding='latin-1', newline='') as fh:
        return fh.read()


def _diagnostico(L):
    """Percorre o arquivo e devolve as alterações candidatas (sem aplicar)."""
    ncm_item, desc_item = {}, {}
    for l in L:
        if ec._reg(l) == '0200':
            p = ec._partes(l['txt'])
            if len(p) > 7:
                ncm_item[p[1]] = re.sub(r'\D', '', p[7])
                desc_item[p[1]] = p[2]
    cands = []            # cada um: dict(i, reg, i100, grupo, regime, receita, base_p, v_p, base_c, v_c, ...)
    fora = []             # monofásico, mas fora da correção automática (motivo)
    kpi = {'itens_venda': 0, 'itens_mono': 0, 'corretos': 0}
    i100, oper, sit, mod, nota = None, '', '', '', ''
    c180 = None
    pend181 = {}          # C181 aguardando o C185 do mesmo C180
    for i, l in enumerate(L):
        r = ec._reg(l)
        if r == 'C100':
            p = ec._partes(l['txt'])
            i100, oper, sit, mod, nota = i, p[1], p[5], p[4], p[7]
            continue
        if r == 'C180':
            p = ec._partes(l['txt'])
            c180 = {'cod': p[4] if len(p) > 4 else '', 'ncm': re.sub(r'\D', '', p[5] if len(p) > 5 else '') or ncm_item.get(p[4] if len(p) > 4 else '', ''),
                    'ini': p[2] if len(p) > 2 else '', 'fim': p[3] if len(p) > 3 else ''}
            continue
        if r == 'C170' and oper == '1' and sit not in ('02', '03', '04', '05'):
            p = ec._partes(l['txt'])
            if len(p) < 36 or not p[10] or p[10][0] not in '567':
                continue
            kpi['itens_venda'] += 1
            reg = _regra_ncm(ncm_item.get(p[2], ''))
            if not reg:
                continue
            kpi['itens_mono'] += 1
            cst, v_p, v_c = p[24], ec._num(p[29]), ec._num(p[35])
            if cst not in ('01', '02') or (v_p <= 0 and v_c <= 0):
                kpi['corretos'] += 1
                continue
            base = {'i': i, 'reg': 'C170', 'i100': i100, 'grupo': reg['grupo'], 'produto': desc_item.get(p[2], p[2])[:60],
                    'ncm': ncm_item.get(p[2], ''), 'nota': nota, 'cfop': p[10], 'cst': cst,
                    'receita': round(ec._num(p[6]) - ec._num(p[7]), 2), 'base_p': ec._num(p[25]), 'v_p': v_p,
                    'base_c': ec._num(p[31]), 'v_c': v_c, 'aliq_p': ec._num(p[26]), 'cod_cta': p[36] if len(p) > 36 else ''}
            motivo = _motivo_fora(reg, cst, p[10], ec._num(p[26]))
            (fora if motivo else cands).append({**base, 'motivo': motivo} if motivo else base)
            continue
        if r in ('C181', 'C185') and c180:
            p = ec._partes(l['txt'])
            if len(p) < 10 or not p[2] or p[2][0] not in '567':
                continue
            reg = _regra_ncm(c180['ncm'])
            if r == 'C181':
                kpi['itens_venda'] += 1
            if not reg:
                continue
            cst, v = p[1], ec._num(p[9])
            if r == 'C181':
                kpi['itens_mono'] += 1
            if cst not in ('01', '02') or v <= 0:
                if r == 'C181':
                    kpi['corretos'] += 1
                continue
            item = {'i': i, 'reg': r, 'i100': None, 'grupo': reg['grupo'], 'produto': desc_item.get(c180['cod'], c180['cod'])[:60],
                    'ncm': c180['ncm'], 'nota': 'consolidado (C180)', 'cfop': p[2], 'cst': cst,
                    'receita': round(ec._num(p[3]) - ec._num(p[4]), 2) if r == 'C181' else 0.0,
                    'base_p': ec._num(p[5]) if r == 'C181' else 0.0, 'v_p': v if r == 'C181' else 0.0,
                    'base_c': ec._num(p[5]) if r == 'C185' else 0.0, 'v_c': v if r == 'C185' else 0.0,
                    'aliq_p': ec._num(p[6]) if r == 'C181' else 0.0, 'cod_cta': p[10] if len(p) > 10 else ''}
            if r == 'C181':
                pend181[(c180['cod'], p[2])] = item
            else:
                par = pend181.get((c180['cod'], p[2]))
                item['aliq_p'] = par['aliq_p'] if par else 0.0
            motivo = _motivo_fora(reg, cst, p[2], item['aliq_p'] if r == 'C181' else (pend181.get((c180['cod'], p[2])) or {}).get('aliq_p', 0.0))
            (fora if motivo else cands).append({**item, 'motivo': motivo} if motivo else item)
            continue
        if r == 'C175' and oper == '1' and sit not in ('02', '03', '04', '05'):
            p = ec._partes(l['txt'])
            if len(p) < 16 or not p[1] or p[1][0] not in '567':
                continue
            kpi['itens_venda'] += 1
            if p[1][1:] not in CFOP_COMBUSTIVEL:
                continue
            kpi['itens_mono'] += 1
            cst, v_p, v_c = p[4], ec._num(p[9]), ec._num(p[15])
            if cst not in ('01', '02') or (v_p <= 0 and v_c <= 0):
                kpi['corretos'] += 1
                continue
            item = {'i': i, 'reg': 'C175', 'i100': i100, 'grupo': GRUPO_COMB, 'produto': f'NFC-e · CFOP {p[1]}', 'ncm': '(CFOP de combustível)',
                    'nota': nota, 'cfop': p[1], 'cst': cst, 'receita': round(ec._num(p[2]) - ec._num(p[3]), 2),
                    'base_p': ec._num(p[5]), 'v_p': v_p, 'base_c': ec._num(p[11]), 'v_c': v_c, 'aliq_p': ec._num(p[6]),
                    'cod_cta': p[16] if len(p) > 16 else ''}
            # 2.4.48: o C175 não traz o produto, e o CFOP 5656/5667 serve tanto para combustível quanto para
            # lubrificante — que é tributado. Sem o XML da NFC-e não dá para saber: nunca corrige sozinho.
            motivo = _motivo_fora(REGRAS_MONOFASICO[3], cst, p[1], ec._num(p[6])) or (
                f'NFC-e consolidada (C175) não traz o produto: o CFOP {p[1]} vale para combustível e também para lubrificante, '
                'que é tributado. Confira no XML da NFC-e se é combustível antes de trocar o CST.')
            fora.append({**item, 'motivo': motivo})
    return cands, fora, kpi


def _motivo_fora(reg, cst, cfop, aliq_p):
    if reg['grupo'] not in NAT_REC:
        return 'Bebidas frias: regra por embalagem e ex-tarifário — conferir e corrigir manualmente.'
    if cst == '02':
        return 'CST 02 (alíquota diferenciada) indica venda de indústria ou importador — não é revenda a alíquota zero.'
    if cfop[1:] in _CFOP_PRODUCAO:
        return f'CFOP {cfop} é de produção própria — quem fabrica não tem alíquota zero.'
    if aliq_p and _regime(aliq_p) is None:
        return f'Alíquota de PIS {ec._fmt(aliq_p, 2)}% não é a básica (0,65% ou 1,65%) — conferir manualmente.'
    return None


def _apuracao(L):
    out = {}
    for trib, r200 in (('PIS', 'M200'), ('COFINS', 'M600')):
        m = next((ec._partes(l['txt']) for l in L if ec._reg(l) == r200), None)
        if m:
            out[trib] = {'nc_rec': ec._num(m[7]), 'cum_rec': ec._num(m[11]), 'total': ec._num(m[12]),
                         'cred_desc': ec._num(m[2]) + ec._num(m[3]), 'nc_per': ec._num(m[1])}
    return out


def analisar_texto(texto):
    L, _eol, _t = ec._ler(texto)
    cab = {}
    for l in L:
        if ec._reg(l) == '0000':
            p = ec._partes(l['txt'])
            cab = {'ini': p[5] if len(p) > 5 else '', 'fim': p[6] if len(p) > 6 else '', 'nome': p[7] if len(p) > 7 else '', 'cnpj': p[8] if len(p) > 8 else ''}
            break
    cands, fora, kpi = _diagnostico(L)
    grupos = defaultdict(lambda: {'itens': 0, 'receita': 0.0, 'pis': 0.0, 'cofins': 0.0, 'exemplos': [], 'regimes': set()})
    for c in cands:
        g = grupos[c['grupo']]
        g['itens'] += 1 if c['reg'] != 'C185' else 0
        g['receita'] += c['receita']
        g['pis'] += c['v_p']
        g['cofins'] += c['v_c']
        rg = _regime(c['aliq_p'])
        if rg:
            g['regimes'].add(rg)
        if len(g['exemplos']) < 8 and c['reg'] != 'C185':
            g['exemplos'].append({k: c[k] for k in ('nota', 'produto', 'ncm', 'cfop', 'cst', 'receita')} | {'valor': round(c['v_p'] + c['v_c'], 2), 'reg': c['reg']})
    # simulação com tudo marcado: apuração depois e o que não pôde ser aplicado
    sim = aplicar_texto(texto, list(grupos.keys()), simular=True) if grupos else None
    lista = [{'grupo': k, 'nat_rec': NAT_REC.get(k, ''), 'nat_desc': NAT_DESC.get(NAT_REC.get(k, ''), ''),
              'lei': next((r['lei'] for r in REGRAS_MONOFASICO if r['grupo'] == k), ''),
              'itens': v['itens'], 'receita': round(v['receita'], 2), 'pis': round(v['pis'], 2), 'cofins': round(v['cofins'], 2),
              'regimes': sorted(v['regimes']), 'exemplos': v['exemplos']} for k, v in grupos.items()]
    lista.sort(key=lambda g: -(g['pis'] + g['cofins']))
    fora_res = defaultdict(lambda: {'itens': 0, 'valor': 0.0})
    for f in fora:
        fr = fora_res[(f['grupo'], f['motivo'])]
        fr['itens'] += 1 if f['reg'] != 'C185' else 0
        fr['valor'] += f['v_p'] + f['v_c']
    return {
        'empresa': cab, 'kpi': {**kpi, 'indevidos': sum(g['itens'] for g in lista),
                                'pis': round(sum(g['pis'] for g in lista), 2), 'cofins': round(sum(g['cofins'] for g in lista), 2)},
        'grupos': lista,
        'fora': [{'grupo': g, 'motivo': m, 'itens': v['itens'], 'valor': round(v['valor'], 2)} for (g, m), v in fora_res.items()],
        'apuracao_antes': _apuracao(L),
        'apuracao_depois': sim['apuracao_depois'] if sim else _apuracao(L),
        'pendencias': sim['pendencias'] if sim else [],
        'so_documento': sim['so_documento'] if sim else [],
    }


def aplicar_texto(texto, grupos_sel, simular=False):
    """Aplica a correção só nos grupos escolhidos. Devolve dict com texto novo, resumo e pendências."""
    L, eol, termina = ec._ler(texto)
    cands, _fora, _k = _diagnostico(L)
    cands = [c for c in cands if c['grupo'] in set(grupos_sel)]
    pend = []
    # 1) agrupa o efeito por regime (cum/nc) e tributo, para conferir a apuração antes de mexer
    efeito = {'cum': defaultdict(float), 'nc': defaultdict(float)}
    for c in cands:
        rg = _regime(c['aliq_p'])
        c['regime'] = rg
        if not rg:
            continue
        e = efeito[rg]
        e['rec_' + c['grupo']] += c['receita']
        e['receita'] += c['receita']
        e['base_p'] += c['base_p']
        e['v_p'] += c['v_p']
        e['base_c'] += c['base_c']
        e['v_c'] += c['v_c']
    ap = _apuracao(L)
    ap_antes = ap
    bloqueia = set()
    # não cumulativo: se os créditos descontados passariam da contribuição nova, a sobra de crédito volta para o saldo
    # (M100/M500, M200/M600 e 1100/1500) — 2.4.48. Só bloqueia se o arquivo não tiver de onde tirar (inconsistente).
    for trib, k in (('PIS', 'v_p'), ('COFINS', 'v_c')):
        a = ap.get(trib)
        if a and efeito['nc'][k]:
            sobra = a['cred_desc'] - (a['nc_per'] - efeito['nc'][k])
            if sobra > 0.005 and sobra > a['cred_desc'] + 0.005:
                bloqueia.add('nc')
    # M210/M610 de destino precisam existir. Se a contribuição desses itens nem está no M210/M610 (a apuração do arquivo
    # não foi montada a partir dos documentos), corrige só os documentos e o M400/M410: tirar do M210 reduziria o
    # tributo de outros itens ou o acréscimo da redução linear (M220/M620 código 11) — 2.4.48
    sem_base = set()
    falta_base = {}
    for rg, cods in (('cum', ec._CUMULATIVOS), ('nc', ec._NAO_CUMULATIVOS)):
        if not efeito[rg]['receita'] and not efeito[rg]['v_p']:
            continue
        for r210, kv in (('M210', 'v_p'), ('M610', 'v_c')):
            alvos = [i for i, l in enumerate(L) if ec._reg(l) == r210 and ec._partes(l['txt'])[1] in cods[:1] and len(ec._partes(l['txt'])) >= 16]
            if len(alvos) != 1:
                bloqueia.add(rg)
            elif efeito[rg][kv] > ec._num(ec._partes(L[alvos[0]]['txt'])[10]) + 0.01:
                sem_base.add(rg)
                falta_base[(rg, r210)] = (efeito[rg][kv], ec._num(ec._partes(L[alvos[0]]['txt'])[10]))
    for rg in bloqueia:
        n = sum(1 for c in cands if c['regime'] == rg and c['reg'] != 'C185')
        if n:
            pend.append({'titulo': f'{n} item(ns) do regime {"não cumulativo" if rg == "nc" else "cumulativo"} não foram corrigidos',
                         'detalhe': ('Os créditos descontados no M200/M600 não fecham com o M100/M500 e o 1100/1500 do arquivo — confira a apuração no PVA antes.'
                                     if rg == 'nc' else 'Não achei um único M210/M610 (COD_CONT 51, leiaute com 16 campos) para receber a redução.')})
    sem_base -= bloqueia
    for rg in sorted(sem_base):
        vp, ap210 = falta_base.get((rg, 'M210'), falta_base.get((rg, 'M610'), (0, 0)))
        pend.append({'tipo': 'info', 'titulo': 'Corrigido nos documentos — o valor a recolher não muda',
                     'detalhe': f'Os itens tinham PIS de R$ {ec._fmt(vp)} nos documentos, mas o M210 do arquivo só apura R$ {ec._fmt(ap210)} de contribuição '
                                '(o resto do M200 é o acréscimo da redução linear, M220 código 11). Ou seja, esse PIS/COFINS não estava sendo cobrado na apuração. '
                                'O arquivo novo corrige o CST 01 → 04 nos documentos e leva a receita para o M400/M410 (alíquota zero); '
                                'o M210/M610 e o M220/M620 ficam como estão. Vale conferir no Domínio por que a apuração não bate com os documentos.'})
    cands = [c for c in cands if c['regime'] and c['regime'] not in bloqueia]
    acoes = []
    # 2) itens
    red100 = defaultdict(lambda: [0.0, 0.0])
    for c in cands:
        p = ec._partes(L[c['i']]['txt'])
        antes = L[c['i']]['txt']
        if c['reg'] == 'C170':
            p[24] = '04'; p[25] = _ZERO; p[26] = _ZERO_ALIQ; p[27] = ''; p[28] = ''; p[29] = _ZERO
            p[30] = '04'; p[31] = _ZERO; p[32] = _ZERO_ALIQ; p[33] = ''; p[34] = ''; p[35] = _ZERO
        elif c['reg'] in ('C181', 'C185'):
            p[1] = '04'; p[5] = _ZERO; p[6] = _ZERO_ALIQ; p[7] = ''; p[8] = ''; p[9] = _ZERO
        elif c['reg'] == 'C175':
            p[4] = '04'; p[5] = _ZERO; p[6] = _ZERO_ALIQ; p[7] = ''; p[8] = ''; p[9] = _ZERO
            p[10] = '04'; p[11] = _ZERO; p[12] = _ZERO_ALIQ; p[13] = ''; p[14] = ''; p[15] = _ZERO
        L[c['i']]['txt'] = ec._monta(p)
        if c['i100'] is not None:
            red100[c['i100']][0] += c['v_p']
            red100[c['i100']][1] += c['v_c']
        acoes.append({'registro': c['reg'], 'linha': L[c['i']]['n'], 'antes': antes, 'depois': L[c['i']]['txt'], 'grupo': c['grupo']})
    for i, (vp, vc) in red100.items():
        p = ec._partes(L[i]['txt'])
        if len(p) > 26:
            p[25] = ec._fmt(max(0.0, ec._num(p[25]) - vp))
            p[26] = ec._fmt(max(0.0, ec._num(p[26]) - vc))
            L[i]['txt'] = ec._monta(p)
    # 3) apuração: M210/M610
    tot = {'cum': defaultdict(float), 'nc': defaultdict(float)}
    for c in cands:
        t = tot[c['regime']]
        for k in ('receita', 'base_p', 'v_p', 'base_c', 'v_c'):
            t[k] += c[k]
        t['nat_' + NAT_REC[c['grupo']]] += c['receita']
        if c['cod_cta'] and not t.get('cta'):
            t['cta'] = c['cod_cta']
    for rg, cods in (('cum', ec._CUMULATIVOS), ('nc', ec._NAO_CUMULATIVOS)):
        t = tot[rg]
        if rg in sem_base or (not t['receita'] and not t['v_p'] and not t['v_c']):
            continue
        for r210, kb, kv in (('M210', 'base_p', 'v_p'), ('M610', 'base_c', 'v_c')):
            i = next(i for i, l in enumerate(L) if ec._reg(l) == r210 and ec._partes(l['txt'])[1] == cods[0])
            p = ec._partes(L[i]['txt'])
            p[2] = ec._fmt(max(0.0, ec._num(p[2]) - t['receita']))
            p[3] = ec._fmt(max(0.0, ec._num(p[3]) - t[kb]))
            p[6] = ec._fmt(max(0.0, ec._num(p[6]) - t[kb]))
            p[10] = ec._fmt(max(0.0, ec._num(p[10]) - t[kv]))
            p[15] = ec._fmt(max(0.0, ec._num(p[15]) - t[kv]))
            L[i]['txt'] = ec._monta(p)
    ctx = {}
    credito_saldo = {}
    for trib in ('PIS', 'COFINS'):
        credito_saldo[trib] = _devolve_credito(L, trib, acoes)
        ec._recalc_m200(L, trib, ctx, 'Recalculado depois da correção do monofásico.')
    # 4) M205/M605 (valor do DARF por campo) acompanham o M200/M600
    for trib, r200, r205 in (('PIS', 'M200', 'M205'), ('COFINS', 'M600', 'M605')):
        m = next((ec._partes(l['txt']) for l in L if ec._reg(l) == r200), None)
        if not m:
            continue
        for campo, pos in (('08', 7), ('12', 11)):
            novo = round(ec._num(m[pos]), 2)
            idxs = [i for i, l in enumerate(L) if ec._reg(l) == r205 and ec._partes(l['txt'])[1] == campo]
            atual = round(sum(ec._num(ec._partes(L[i]['txt'])[3]) for i in idxs), 2)
            dif = round(atual - novo, 2)
            for i in sorted(idxs, key=lambda i: -ec._num(ec._partes(L[i]['txt'])[3])):
                if dif <= 0.004:
                    break
                p = ec._partes(L[i]['txt'])
                v = ec._num(p[3])
                tira = min(v, dif)
                p[3] = ec._fmt(v - tira)
                dif = round(dif - tira, 2)
                L[i]['txt'] = ec._monta(p)
            for i in sorted(idxs, reverse=True):         # DARF zerado não fica no arquivo
                if ec._num(ec._partes(L[i]['txt'])[3]) <= 0.004:
                    L.pop(i)
    # 5) M400/M410 e M800/M810: receita a alíquota zero (CST 04) por natureza
    nat_tot = defaultdict(float)
    cta = ''
    for rg in ('cum', 'nc'):
        for k, v in tot[rg].items():
            if k.startswith('nat_'):
                nat_tot[k[4:]] += v
        cta = cta or tot[rg].get('cta', '')
    if nat_tot:
        for r400, r410, limite in (('M400', 'M410', 400), ('M800', 'M810', 800)):
            _soma_m400(L, r400, r410, limite, nat_tot, cta)
    L = ec._recontar(L, [])
    novo_texto = ec._escrever(L, eol, termina)
    res = {
        'itens_corrigidos': sum(1 for c in cands if c['reg'] != 'C185'),
        'pis': round(sum(c['v_p'] for c in cands), 2), 'cofins': round(sum(c['v_c'] for c in cands), 2),
        'receita': round(sum(c['receita'] for c in cands), 2),
        'apuracao_depois': _apuracao(L), 'pendencias': pend, 'acoes': acoes[:300],
        'credito_saldo': {k: round(v, 2) for k, v in credito_saldo.items()},
        'so_documento': sorted(sem_base),
    }
    dep = res['apuracao_depois']
    res['economia'] = {t: round(max(0.0, (ap_antes.get(t) or {}).get('total', 0) - (dep.get(t) or {}).get('total', 0)), 2) for t in ('PIS', 'COFINS')}
    if not simular:
        res['texto'] = novo_texto
    return res


def _periodo(L):
    p = next((ec._partes(l['txt']) for l in L if ec._reg(l) == '0000'), None)
    return p[6][2:8] if p and len(p) > 6 and len(p[6]) == 8 else ''      # DT_INI ddmmaaaa → mmaaaa


def _devolve_credito(L, trib, acoes):
    """Regime não cumulativo: depois de reduzir a contribuição (M210/M610), os créditos descontados no M200/M600 não podem
    passar da contribuição nova. A sobra deixa de ser descontada e volta para o saldo a utilizar em períodos futuros:
      * M100/M500 (créditos do mês): VL_CRED_DESC menos, SLD_CRED mais, IND_DESC_CRED = 1 (parcial);
      * M200/M600: VL_TOT_CRED_DESC (e, se faltar, VL_TOT_CRED_DESC_ANT) menos — o M200 é recalculado em seguida;
      * 1100/1500 (controle de créditos): VL_CRED_DESC_EFD menos e SLD_CRED_FIM mais, no período e código do crédito;
        sem linha do período, ela é criada.
    Devolve o valor que voltou para o saldo."""
    r100, r200, r210, r1100, ant1100 = (('M100', 'M200', 'M210', '1100', '1001') if trib == 'PIS' else ('M500', 'M600', 'M610', '1500', '1001'))
    i200 = next((i for i, l in enumerate(L) if ec._reg(l) == r200), None)
    if i200 is None:
        return 0.0
    p200 = ec._partes(L[i200]['txt'])
    nc_novo = sum(ec._num(ec._partes(l['txt'])[15]) for l in L if ec._reg(l) == r210 and ec._partes(l['txt'])[1] in ec._NAO_CUMULATIVOS)
    desc, ant = ec._num(p200[2]), ec._num(p200[3])
    sobra = round(desc + ant - nc_novo, 2)
    if sobra <= 0.004:
        return 0.0
    per = _periodo(L)
    tira_mes = min(sobra, desc)
    resto = round(sobra - tira_mes, 2)
    # 1) créditos do mês (M100/M500), do último para o primeiro
    falta = tira_mes
    for i in sorted((i for i, l in enumerate(L) if ec._reg(l) == r100), reverse=True):
        if falta <= 0.004:
            break
        p = ec._partes(L[i]['txt'])
        if len(p) < 15:
            continue
        usado = ec._num(p[13])
        x = round(min(usado, falta), 2)
        if x <= 0:
            continue
        antes = L[i]['txt']
        p[13] = ec._fmt(usado - x)
        p[14] = ec._fmt(ec._num(p[14]) + x)
        p[12] = '1'
        L[i]['txt'] = ec._monta(p)
        acoes.append({'registro': r100, 'linha': L[i]['n'], 'antes': antes, 'depois': L[i]['txt'], 'grupo': 'crédito volta ao saldo'})
        _ajusta_1100(L, r1100, ant1100, per, p[1], x, p, acoes)
        falta = round(falta - x, 2)
    tirado_mes = round(tira_mes - falta, 2)
    # 2) se ainda sobrar, créditos de meses anteriores usados neste mês (1100/1500 de outros períodos), do mais novo
    tirado_ant = 0.0
    if resto > 0.004:
        outras = [i for i, l in enumerate(L) if ec._reg(l) == r1100 and ec._partes(l['txt'])[1] != per and ec._num(ec._partes(l['txt'])[12]) > 0]
        outras.sort(key=lambda i: (ec._partes(L[i]['txt'])[1][2:], ec._partes(L[i]['txt'])[1][:2]), reverse=True)
        for i in outras:
            if resto <= 0.004:
                break
            p = ec._partes(L[i]['txt'])
            x = round(min(ec._num(p[12]), resto), 2)
            antes = L[i]['txt']
            p[12] = ec._fmt(ec._num(p[12]) - x)
            p[17] = ec._fmt(ec._num(p[17]) + x)
            L[i]['txt'] = ec._monta(p)
            acoes.append({'registro': r1100, 'linha': L[i]['n'], 'antes': antes, 'depois': L[i]['txt'], 'grupo': 'crédito volta ao saldo'})
            resto = round(resto - x, 2)
            tirado_ant = round(tirado_ant + x, 2)
    p200[2] = ec._fmt(desc - tirado_mes)
    p200[3] = ec._fmt(ant - tirado_ant)
    L[i200]['txt'] = ec._monta(p200)
    return round(tirado_mes + tirado_ant, 2)


def _ajusta_1100(L, r1100, ant1100, per, cod, x, p100, acoes):
    """1100/1500 do crédito do mês (PER_APU_CRED = período do arquivo, ORIG_CRED 01, mesmo COD_CRED)."""
    alvo = next((i for i, l in enumerate(L) if ec._reg(l) == r1100 and ec._partes(l['txt'])[1] == per
                 and ec._partes(l['txt'])[4] == cod and ec._partes(l['txt'])[2] in ('01', '1')), None)
    if alvo is not None:
        p = ec._partes(L[alvo]['txt'])
        antes = L[alvo]['txt']
        p[12] = ec._fmt(max(0.0, ec._num(p[12]) - x))
        p[17] = ec._fmt(ec._num(p[17]) + x)
        L[alvo]['txt'] = ec._monta(p)
        acoes.append({'registro': r1100, 'linha': L[alvo]['n'], 'antes': antes, 'depois': L[alvo]['txt'], 'grupo': 'crédito volta ao saldo'})
        return
    disp = ec._num(p100[11])
    desc_novo = ec._num(p100[13])
    novo = [r1100, per, '01', '', cod, ec._fmt(disp), ec._fmt(0), ec._fmt(disp), ec._fmt(0), ec._fmt(0), ec._fmt(0), ec._fmt(disp),
            ec._fmt(desc_novo), ec._fmt(0), ec._fmt(0), ec._fmt(0), ec._fmt(0), ec._fmt(disp - desc_novo)]
    # posição: depois do último 1100/1500 ou, sem nenhum, antes do primeiro registro do bloco 1 com código maior
    ult = [i for i, l in enumerate(L) if ec._reg(l) == r1100]
    if ult:
        pos = ult[-1] + 1
    else:
        pos = next((i for i, l in enumerate(L) if ec._reg(l).startswith('1') and ec._reg(l)[1:].isdigit() and int(ec._reg(l)) > int(r1100)), None)
        if pos is None:
            pos = next((i for i, l in enumerate(L) if ec._reg(l) == '1990'), len(L))
    L.insert(pos, {'n': None, 'txt': ec._monta(novo), 'novo': True})
    i1001 = next((i for i, l in enumerate(L) if ec._reg(l) == '1001'), None)       # bloco 1 passa a ter dados
    if i1001 is not None and ec._partes(L[i1001]['txt'])[1] != '0':
        L[i1001]['txt'] = ec._monta(['1001', '0'])
    acoes.append({'registro': r1100, 'linha': None, 'antes': '(não existia)', 'depois': ec._monta(novo), 'grupo': 'crédito volta ao saldo'})


def _soma_m400(L, r400, r410, limite, nat_tot, cta):
    total = round(sum(nat_tot.values()), 2)
    i400 = next((i for i, l in enumerate(L) if ec._reg(l) == r400 and ec._partes(l['txt'])[1] == '04'), None)
    if i400 is None:
        # entra antes do primeiro registro do bloco M com número >= limite (ex.: M500/M600/... para o M400)
        pos = next((i for i, l in enumerate(L) if ec._reg(l)[0] == 'M' and ec._reg(l)[1:].isdigit()
                    and int(ec._reg(l)[1:]) >= limite and ec._reg(l) not in (r400, r410)), None)
        if pos is None:
            return
        L.insert(pos, {'n': None, 'txt': ec._monta([r400, '04', ec._fmt(total), cta, '']), 'novo': True})
        i400 = pos
    else:
        p = ec._partes(L[i400]['txt'])
        p[2] = ec._fmt(ec._num(p[2]) + total)
        L[i400]['txt'] = ec._monta(p)
    # filhos M410/M810 logo abaixo do M400/M800 de CST 04
    j = i400 + 1
    filhos = {}
    while j < len(L) and ec._reg(L[j]) == r410:
        filhos[ec._partes(L[j]['txt'])[1]] = j
        j += 1
    for nat, v in sorted(nat_tot.items()):
        if nat in filhos:
            p = ec._partes(L[filhos[nat]]['txt'])
            p[2] = ec._fmt(ec._num(p[2]) + v)
            L[filhos[nat]]['txt'] = ec._monta(p)
        else:
            L.insert(j, {'n': None, 'txt': ec._monta([r410, nat, ec._fmt(v), cta, '']), 'novo': True})
            j += 1


# ------------------------------------------------------------------ CLI
def main_cli(argv):
    """monofasico.py analisar EFD.txt --json saida.json
       monofasico.py aplicar EFD.txt --grupos '["...", ...]' --saida NOVO.txt --json resumo.json"""
    if len(argv) < 3:
        print(main_cli.__doc__)
        return 1
    modo, arq = argv[1], argv[2]
    args = argv[3:]

    def opt(n, d=None):
        return args[args.index(n) + 1] if n in args and args.index(n) + 1 < len(args) else d
    try:
        texto = _ler_arquivo(arq)
        if modo == 'analisar':
            res = analisar_texto(texto)
        else:
            grupos = json.loads(opt('--grupos', '[]'))
            res = aplicar_texto(texto, grupos)
            with open(opt('--saida', 'efd_monofasico.txt'), 'w', encoding='latin-1', newline='') as fh:
                fh.write(res.pop('texto'))
    except Exception as e:
        res = {'erro': f'Não consegui analisar esse arquivo: {e}'}
    saida = json.dumps(res, ensure_ascii=False, default=list)
    if opt('--json'):
        with open(opt('--json'), 'w', encoding='utf-8') as fh:
            fh.write(saida)
    print(saida[:2000])
    return 0 if 'erro' not in res else 1


if __name__ == '__main__':
    sys.exit(main_cli(sys.argv))

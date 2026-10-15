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
            motivo = _motivo_fora(REGRAS_MONOFASICO[3], cst, p[1], ec._num(p[6]))
            (fora if motivo else cands).append({**item, 'motivo': motivo} if motivo else item)
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
    bloqueia = set()
    # não cumulativo: se os créditos descontados passariam da contribuição, não aplica (mexe no saldo de créditos)
    for trib, k in (('PIS', 'v_p'), ('COFINS', 'v_c')):
        a = ap.get(trib)
        if a and efeito['nc'][k] and a['cred_desc'] > a['nc_per'] - efeito['nc'][k] + 0.005:
            bloqueia.add('nc')
    # M210/M610 de destino precisam existir
    for rg, cods in (('cum', ec._CUMULATIVOS), ('nc', ec._NAO_CUMULATIVOS)):
        if not efeito[rg]['receita'] and not efeito[rg]['v_p']:
            continue
        for r210 in ('M210', 'M610'):
            alvos = [i for i, l in enumerate(L) if ec._reg(l) == r210 and ec._partes(l['txt'])[1] in cods[:1] and len(ec._partes(l['txt'])) >= 16]
            if len(alvos) != 1:
                bloqueia.add(rg)
    for rg in bloqueia:
        n = sum(1 for c in cands if c['regime'] == rg and c['reg'] != 'C185')
        if n:
            pend.append({'titulo': f'{n} item(ns) do regime {"não cumulativo" if rg == "nc" else "cumulativo"} não foram corrigidos',
                         'detalhe': ('Os créditos descontados no M200/M600 passariam da contribuição do mês — a correção mexe no saldo de créditos e precisa ser feita manualmente.'
                                     if rg == 'nc' else 'Não achei um único M210/M610 (COD_CONT 51, leiaute com 16 campos) para receber a redução.')})
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
        if not t['receita'] and not t['v_p'] and not t['v_c']:
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
    for trib in ('PIS', 'COFINS'):
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
    }
    if not simular:
        res['texto'] = novo_texto
    return res


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

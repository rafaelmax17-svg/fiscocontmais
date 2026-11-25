# -*- coding: utf-8 -*-
"""
Alíquota do regime e apuração a partir dos documentos (2.4.56) — corretor da EFD-Contribuições.

1) Alíquota do CST 01 × regime da empresa (0110): o PVA exige a alíquota básica do regime em toda operação com CST 01
   — cumulativo (Lucro Presumido) 0,65% / 3%; não cumulativo (Lucro Real) 1,65% / 7,6% (Lei 9.718/1998, art. 8º;
   Lei 10.637/2002, art. 2º; Lei 10.833/2003, art. 2º). Quando o Domínio grava 1,65/7,6 numa empresa do cumulativo
   (ou o contrário), o PIS/COFINS do documento fica errado e o M210/M610 não bate. Aqui a alíquota volta para a do
   regime e o valor é recalculado (base × alíquota) no item e no total do C100.
   Só para 0110 = 1 ou 2 (um regime só); empresa com os dois regimes (0110 = 3) fica como pendência.

2) Apuração pelos documentos: o M210/M610 (receita bruta, base e contribuição do CST 01) e o M400/M800 (receita
   com CST 04, 06, 07, 08 e 09) precisam fechar com a soma dos documentos — são as regras do PVA "Deverá existir um
   registro M210/M610 para cada código de contribuição e alíquota" e "A soma de VL_TOT_REC dos registros M400/M800
   deve ser igual à soma de VL_ITEM…". O M210/M610 que falta é criado; o que não fecha é refeito (os ajustes
   M220/M620 e o diferimento ficam como estão); a diferença do M400/M800 vai para a natureza de maior valor do M410/M810.
   Depois, M200/M600 e M205/M605.
"""
from collections import defaultdict

import efd_corretor as ec

BASICA = {'cum': (0.65, 3.00), 'nc': (1.65, 7.60)}
COD_CONT = {'cum': '51', 'nc': '01'}
_SEM_INCID = ('04', '06', '07', '08', '09')


def _regime(L):
    p = next((ec._partes(l['txt']) for l in L if ec._reg(l) == '0110'), None)
    return {'1': 'nc', '2': 'cum'}.get(p[1] if p else '', '')


# posição dos campos por registro: (VL_ITEM, VL_DESC, CST_PIS, BC_PIS, ALIQ_PIS, VL_PIS, CST_COF, BC_COF, ALIQ_COF, VL_COF)
_POS = {
    'C170': (6, 7, 24, 25, 26, 29, 30, 31, 32, 35),
    'C175': (2, 3, 4, 5, 6, 9, 10, 11, 12, 15),
    'A170': (4, 5, 8, 9, 10, 11, 12, 13, 14, 15),
    'F100': (5, None, 6, 7, 8, 9, 10, 11, 12, 13),
}
# C181 (PIS) e C185 (COFINS): CST, CFOP, VL_ITEM, VL_DESC, BC, ALIQ, QUANT, ALIQ_QUANT, VALOR
_POS_C18 = (1, 3, 4, 5, 6, 9)


def _docs(L):
    """Percorre os itens dos documentos: (i, reg, tributo, cst, vl_item, desc, base, aliq, valor, pos_aliq, pos_valor, pai_c100)"""
    pai = None
    for i, l in enumerate(L):
        r = ec._reg(l)
        if r in ('C100', 'A100'):
            pai = i
        elif r in ('C010', 'A010', 'F010', 'D010', 'C180', 'C190', 'C380', 'C400', 'C490', 'C500', 'C600', 'D100', 'D200', 'D500', 'D600'):
            pai = None
        if r in _POS:
            p = ec._partes(l['txt'])
            pos = _POS[r]
            if len(p) <= max(x for x in pos if x is not None):
                continue
            vi = ec._num(p[pos[0]])
            de = ec._num(p[pos[1]]) if pos[1] is not None else 0.0
            yield (i, r, 'PIS', p[pos[2]], vi, de, ec._num(p[pos[3]]), ec._num(p[pos[4]]), ec._num(p[pos[5]]), pos[4], pos[5], pos[3], pai if r in ('C170', 'C175', 'A170') else None)
            yield (i, r, 'COFINS', p[pos[6]], vi, de, ec._num(p[pos[7]]), ec._num(p[pos[8]]), ec._num(p[pos[9]]), pos[8], pos[9], pos[7], pai if r in ('C170', 'C175', 'A170') else None)
        elif r in ('C181', 'C185'):
            p = ec._partes(l['txt'])
            if len(p) <= 9:
                continue
            trib = 'PIS' if r == 'C181' else 'COFINS'
            c, it, de, bc, al, vl = _POS_C18
            yield (i, r, trib, p[c], ec._num(p[it]), ec._num(p[de]), ec._num(p[bc]), ec._num(p[al]), ec._num(p[vl]), al, vl, bc, None)


# ------------------------------------------------------------------ 1) alíquota do regime
def det_aliq_regime(L):
    reg = _regime(L)
    if not reg:
        return []
    ap, ac = BASICA[reg]
    out = {}
    for (i, r, trib, cst, vi, de, bc, al, vl, pa, pv, pb, pai) in _docs(L):
        if cst != '01':
            continue
        alvo = ap if trib == 'PIS' else ac
        if abs(al - alvo) > 0.00005 or abs(vl - round(bc * alvo / 100, 2)) > 0.011:
            out.setdefault(i, {'i': i, 'n': L[i]['n'], 'reg': r})
    return list(out.values())


def fix_aliq_regime(L, acoes, pend, ctx):
    reg = _regime(L)
    if not reg:
        if any(cst == '01' for (_, _, _, cst, *_r) in _docs(L)) and next((1 for l in L if ec._reg(l) == '0110'), None):
            p = next(ec._partes(l['txt']) for l in L if ec._reg(l) == '0110')
            if p[1] == '3':
                pend.append({'cat': 'aliq_regime', 'linha': None, 'titulo': 'Empresa nos dois regimes (0110 = 3)',
                             'detalhe': 'Com regime cumulativo e não cumulativo ao mesmo tempo, a alíquota do CST 01 depende da receita. Confira as alíquotas no PVA.'})
        return L
    ap, ac = BASICA[reg]
    muda = defaultdict(list)                     # i -> [(pos_aliq, pos_valor, pos_base, alvo)]
    for (i, r, trib, cst, vi, de, bc, al, vl, pa, pv, pb, pai) in _docs(L):
        if cst != '01':
            continue
        alvo = ap if trib == 'PIS' else ac
        if abs(al - alvo) > 0.00005 or abs(vl - round(bc * alvo / 100, 2)) > 0.011:
            muda[i].append((pa, pv, pb, alvo, pai))
    pais = set()
    for i, lst in muda.items():
        p = ec._partes(L[i]['txt'])
        antes = L[i]['txt']
        for pa, pv, pb, alvo, pai in lst:
            p[pa] = ec._fmt(alvo, 4)
            p[pv] = ec._fmt(round(ec._num(p[pb]) * alvo / 100, 2))
            if pai is not None:
                pais.add(pai)
        L[i]['txt'] = ec._monta(p)
        acoes.append({'cat': 'aliq_regime', 'tipo': 'alterado', 'linha': L[i]['n'], 'registro': ec._reg(L[i]), 'antes': antes, 'depois': L[i]['txt'],
                      'motivo': f"CST 01 com alíquota fora do regime {'cumulativo' if reg == 'cum' else 'não cumulativo'}: "
                                f"PIS {ec._fmt(ap, 2)}% e COFINS {ec._fmt(ac, 2)}%, valor recalculado (base × alíquota)."})
    # total do C100/A100 = soma dos itens (o CST 05/75 — ST — não entra no total do documento)
    for pai in sorted(pais):
        r = ec._reg(L[pai])
        j, sp, sc = pai + 1, 0.0, 0.0
        filho = 'C170' if r == 'C100' else 'A170'
        while j < len(L) and ec._reg(L[j]) not in (r, 'C990', 'A990') and ec._reg(L[j])[:1] == r[:1] and not ec._reg(L[j]).endswith('010'):
            if ec._reg(L[j]) in (filho, 'C175'):
                q = ec._partes(L[j]['txt'])
                pos = _POS[ec._reg(L[j])]
                if q[pos[2]] not in ('05', '75'):
                    sp += ec._num(q[pos[5]])
                if q[pos[6]] not in ('05', '75'):
                    sc += ec._num(q[pos[9]])
            j += 1
        p = ec._partes(L[pai]['txt'])
        ip, ic = (25, 26) if r == 'C100' else (15, 17)
        if len(p) <= ic:
            continue
        if abs(ec._num(p[ip]) - sp) > 0.005 or abs(ec._num(p[ic]) - sc) > 0.005:
            antes = L[pai]['txt']
            p[ip], p[ic] = ec._fmt(round(sp, 2)), ec._fmt(round(sc, 2))
            L[pai]['txt'] = ec._monta(p)
            acoes.append({'cat': 'aliq_regime', 'tipo': 'alterado', 'linha': L[pai]['n'], 'registro': r, 'antes': antes, 'depois': L[pai]['txt'],
                          'motivo': 'Total de PIS/COFINS do documento refeito pela soma dos itens corrigidos.'})
    return L


# ------------------------------------------------------------------ 2) apuração pelos documentos
def _somas(L):
    reg = _regime(L)
    s01 = {'PIS': defaultdict(float), 'COFINS': defaultdict(float)}         # (aliq) -> rec, bc
    rec = {'PIS': defaultdict(float), 'COFINS': defaultdict(float)}         # cst -> receita
    for (i, r, trib, cst, vi, de, bc, al, vl, *_x) in _docs(L):
        if cst == '01':
            k = round(al, 4)
            s01[trib][('rec', k)] += vi
            s01[trib][('bc', k)] += bc
        elif cst in _SEM_INCID:
            rec[trib][cst] += vi
    return reg, s01, rec


def det_apuracao(L):
    reg, s01, rec = _somas(L)
    out = []
    if reg:
        cod = COD_CONT[reg]
        for trib, r210 in (('PIS', 'M210'), ('COFINS', 'M610')):
            for (tipo, al), v in s01[trib].items():
                if tipo != 'bc':
                    continue
                m = [ec._partes(l['txt']) for l in L if ec._reg(l) == r210 and ec._partes(l['txt'])[1] == cod and abs(ec._num(ec._partes(l['txt'])[7]) - al) < 0.00005]
                if not m or abs(sum(ec._num(x[3]) for x in m) - v) > 0.05:
                    out.append({'reg': r210, 'aliq': al, 'docs': round(v, 2), 'arq': round(sum(ec._num(x[3]) for x in m), 2) if m else None})
    for trib, r400 in (('PIS', 'M400'), ('COFINS', 'M800')):
        arq = defaultdict(float)
        for l in L:
            if ec._reg(l) == r400:
                p = ec._partes(l['txt'])
                arq[p[1]] += ec._num(p[2])
        for cst in sorted(set(arq) | set(rec[trib])):
            if cst in _SEM_INCID and abs(arq.get(cst, 0) - rec[trib].get(cst, 0)) > 0.05:
                out.append({'reg': r400, 'cst': cst, 'docs': round(rec[trib].get(cst, 0), 2), 'arq': round(arq.get(cst, 0), 2)})
    return out


def fix_apuracao(L, acoes, pend, ctx):
    falhas = det_apuracao(L)
    if not falhas:
        return L
    reg, s01, rec = _somas(L)
    mexeu = False
    if reg:
        cod = COD_CONT[reg]
        for trib, r200, r205, r210 in (('PIS', 'M200', 'M205', 'M210'), ('COFINS', 'M600', 'M605', 'M610')):
            for al in sorted({k[1] for k in s01[trib] if k[0] == 'bc'}):
                if not any(f['reg'] == r210 and f.get('aliq') == al for f in falhas):
                    continue
                rb, bc = round(s01[trib][('rec', al)], 2), round(s01[trib][('bc', al)], 2)
                if abs(al - BASICA[reg][0 if trib == 'PIS' else 1]) > 0.00005:
                    pend.append({'cat': 'apuracao', 'linha': None, 'titulo': f'{r210}: CST 01 com alíquota {ec._fmt(al, 4)}%',
                                 'detalhe': 'A alíquota não é a básica do regime da empresa: o M210/M610 dela não foi montado. Confira o 0110 e as alíquotas dos documentos.'})
                    continue
                idx = [i for i, l in enumerate(L) if ec._reg(l) == r210 and ec._partes(l['txt'])[1] == cod and abs(ec._num(ec._partes(l['txt'])[7]) - al) < 0.00005]
                if idx:
                    i = idx[0]
                    p = ec._partes(L[i]['txt'])
                    antes = L[i]['txt']
                    bc_aj = bc + ec._num(p[4]) - ec._num(p[5])
                    apur = round(bc_aj * al / 100, 2)
                    p[2], p[3], p[6], p[10] = ec._fmt(rb), ec._fmt(bc), ec._fmt(bc_aj), ec._fmt(apur)
                    p[15] = ec._fmt(apur + ec._num(p[11]) - ec._num(p[12]) - ec._num(p[13]) + ec._num(p[14]))
                    L[i]['txt'] = ec._monta(p)
                    acoes.append({'cat': 'apuracao', 'tipo': 'alterado', 'linha': L[i]['n'], 'registro': r210, 'antes': antes, 'depois': L[i]['txt'],
                                  'motivo': f'Receita e base do CST 01 refeitas pela soma dos documentos: receita R$ {ec._brl(rb)}, base R$ {ec._brl(bc)}, contribuição R$ {ec._brl(apur)} (ajustes M220/M620 mantidos).'})
                else:
                    apur = round(bc * al / 100, 2)
                    i200 = next((i for i, l in enumerate(L) if ec._reg(l) == r200), None)
                    if i200 is None:
                        pend.append({'cat': 'apuracao', 'linha': None, 'titulo': f'{r200} não existe', 'detalhe': 'Gere a apuração no PVA.'})
                        continue
                    pos = i200 + 1
                    while pos < len(L) and (ec._reg(L[pos]) in (r205, r210) or (ec._reg(L[pos])[:2] == r210[:2] and ec._reg(L[pos])[2:] in ('11', '15', '20', '25', '30'))):
                        pos += 1
                    novo = ec._monta([r210, cod, ec._fmt(rb), ec._fmt(bc), '0,00', '0,00', ec._fmt(bc), ec._fmt(al, 4), '', '', ec._fmt(apur),
                                      '0,00', '0,00', '0,00', '0,00', ec._fmt(apur)])
                    L.insert(pos, {'n': L[i200]['n'], 'txt': novo, 'novo': True})
                    acoes.append({'cat': 'apuracao', 'tipo': 'incluido', 'linha': L[i200]['n'], 'registro': r210, 'antes': '', 'depois': novo,
                                  'motivo': f'Não havia {r210} para o CST 01 ({"cumulativo" if reg == "cum" else "não cumulativo"}, alíquota {ec._fmt(al, 2)}%): '
                                            f'receita R$ {ec._brl(rb)}, base R$ {ec._brl(bc)}, contribuição R$ {ec._brl(apur)}.'})
                mexeu = True
    for trib, r400, r410 in (('PIS', 'M400', 'M410'), ('COFINS', 'M800', 'M810')):
        for f in [x for x in falhas if x['reg'] == r400]:
            cst, dif = f['cst'], round(f['docs'] - f['arq'], 2)
            idx = [i for i, l in enumerate(L) if ec._reg(l) == r400 and ec._partes(l['txt'])[1] == cst]
            if not idx:
                pend.append({'cat': 'apuracao', 'linha': None, 'titulo': f'{r400} com CST {cst} não existe',
                             'detalhe': f'Os documentos têm R$ {ec._brl(f["docs"])} de receita com CST {cst}, sem natureza no {r400}/{r410}. Informe a natureza no PVA.'})
                continue
            # natureza de maior valor entre todos os M400 deste CST
            melhor = None
            for i400 in idx:
                j = i400 + 1
                while j < len(L) and ec._reg(L[j]) == r410:
                    v = ec._num(ec._partes(L[j]['txt'])[2])
                    if melhor is None or v > melhor[2]:
                        melhor = (i400, j, v)
                    j += 1
            if melhor is None or melhor[2] + dif < -0.005:
                pend.append({'cat': 'apuracao', 'linha': L[idx[0]]['n'], 'titulo': f'{r400} CST {cst}: diferença de R$ {ec._brl(dif)}',
                             'detalhe': 'Não há natureza com valor suficiente para absorver a diferença. Confira a receita por natureza no PVA.'})
                continue
            i400, j410, _v = melhor
            for k, campo in ((i400, 2), (j410, 2)):
                p = ec._partes(L[k]['txt'])
                antes = L[k]['txt']
                p[campo] = ec._fmt(ec._num(p[campo]) + dif)
                L[k]['txt'] = ec._monta(p)
                acoes.append({'cat': 'apuracao', 'tipo': 'alterado', 'linha': L[k]['n'], 'registro': ec._reg(L[k]), 'antes': antes, 'depois': L[k]['txt'],
                              'motivo': f'Receita com CST {cst} igualada à soma dos documentos (R$ {ec._brl(f["docs"])}): '
                                        f'{"+" if dif > 0 else "−"} R$ {ec._brl(abs(dif))} na natureza de maior valor ({ec._partes(L[j410]["txt"])[1]}).'})
            mexeu = True
    if mexeu:
        for trib in ('PIS', 'COFINS'):
            ec._recalc_m200(L, trib, ctx, 'Recalculado a partir do M210/M610 refeito pelos documentos.')
        import efd_itens_xml
        efd_itens_xml._acerta_m205(L, reg or 'cum')
    # redução linear (LC 224/2025) — só aponta: a receita com CST 06 não tem acréscimo no M220/M620
    p0 = ec._partes(L[0]['txt']) if L and ec._reg(L[0]) == '0000' else []
    comp = (p0[5][4:] + p0[5][2:4]) if len(p0) > 5 else ''
    if comp >= '202604' and rec['PIS'].get('06', 0) > 0 and not any(ec._reg(l) == 'M220' and ec._partes(l['txt'])[3] == '11' for l in L):
        a = {'cum': (0.065, 0.300), 'nc': (0.165, 0.760)}.get(reg or 'cum')
        pend.append({'cat': 'apuracao', 'linha': None, 'titulo': 'Redução linear da LC 224/2025 não informada',
                     'detalhe': f'Há R$ {ec._brl(rec["PIS"]["06"])} de receita com CST 06 (alíquota zero) e nenhum ajuste M220/M620 código 11. '
                                f'Se toda essa receita entrar na redução linear, seriam cerca de PIS R$ {ec._brl(rec["PIS"]["06"] * a[0] / 100)} e '
                                f'COFINS R$ {ec._brl(rec["COFINS"].get("06", 0) * a[1] / 100)} a mais (base sem o ICMS, por documento, nos M225/M625). Confira no Domínio.'})
    return L


# ------------------------------------------------------------------ 3) conferência do CST das NF-e pelo NCM (só aponta)
def resumo_cst_ncm(L):
    """Itens de saída das NF-e (C170) agrupados por NCM e CST, com o que o NCM indica.
    Aponta: CST 01 com NCM monofásico (deveria ser 04) e combustível (NCM do art. 4º da Lei 9.718) fora do CST 04/06."""
    from oportunidades import _regra_ncm
    prod, est, oper = {}, '', ''
    for l in L:
        r = ec._reg(l)
        if r == '0140':
            est = ec._partes(l['txt'])[3]
        elif r == '0200':
            p = ec._partes(l['txt'])
            prod[(est, p[1])] = (p[7] if len(p) > 7 else '', p[2])
        elif r in ('C010', 'A010', 'D010', 'F010'):
            est = ec._partes(l['txt'])[1]
    grupos = {}
    for l in L:
        r = ec._reg(l)
        if r in ('C010', 'A010', 'D010', 'F010'):
            est = ec._partes(l['txt'])[1]
        elif r == 'C100':
            oper = ec._partes(l['txt'])[1]
        elif r == 'C170' and oper == '1':
            p = ec._partes(l['txt'])
            if len(p) < 31:
                continue
            ncm, desc = prod.get((est, p[2]), ('', ''))
            k = (ncm, p[24])
            g = grupos.setdefault(k, {'ncm': ncm, 'cst': p[24], 'produto': desc or p[3], 'itens': 0, 'valor': 0.0, 'linhas': [], 'nomes': set()})
            g['nomes'].add(desc or p[3])
            g['itens'] += 1
            g['valor'] += ec._num(p[6])
            if len(g['linhas']) < 5:
                g['linhas'].append(l['n'])
    out = []
    for g in grupos.values():
        reg = _regra_ncm(g['ncm']) if g['ncm'] else None
        alerta = ''
        if g['cst'] == '01' and reg and reg.get('confianca') in ('Alta', 'Média'):
            alerta = f"NCM do monofásico ({reg['grupo']}) com CST 01 — na revenda o certo é CST 04 ({reg['lei']})"
        elif reg and reg['grupo'].startswith('Combustíveis') and g['cst'] not in ('04', '06', '49', '99'):
            alerta = f"Combustível com CST {g['cst']} — revenda de combustível é CST 04"
        g['indica'] = f"{reg['grupo']} (CST 04)" if reg else ''
        g['alerta'] = alerta
        g['valor'] = round(g['valor'], 2)
        nomes = sorted(g.pop('nomes'))
        g['produto'] = nomes[0] + (f' e mais {len(nomes) - 1}' if len(nomes) > 1 else '')
        out.append(g)
    out.sort(key=lambda g: (not g['alerta'], g['cst'], -g['valor']))
    return out

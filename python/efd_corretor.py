# -*- coding: utf-8 -*-
"""
Corretor de EFD-Contribuições (admin) — corrige os erros de validação do PVA que são
mecânicos e registra CADA ação (antes → depois), separada por tipo de erro.

Conferido contra dois arquivos reais (C. C. de Aguiar / Lucro Presumido — 56 erros; Cacoal
/ Lucro Real — 204 erros), 02/10/2026. Princípios:
 - só corrige o que é determinístico; nunca inventa dado (ex.: CPF);
 - o que depende de decisão (natureza da receita fora da tabela) vira PENDÊNCIA;
 - todo registro incluído pelo sistema é descrito como tal no próprio arquivo e no relatório;
 - o PVA continua sendo o juiz final: revalide o arquivo corrigido.
"""
import html as _html
import re
from collections import Counter, defaultdict

try:
    from efd_tabelas_natureza_dados import TABELAS as _TABELAS_NATUREZA
except Exception:
    _TABELAS_NATUREZA = {}
_CST_PARA_TABELA = {'02': '4.3.10', '04': '4.3.10', '05': '4.3.12', '06': '4.3.13', '07': '4.3.14', '08': '4.3.15', '09': '4.3.16'}

# mesmos mapas do corretor do SPED Fiscal (fiscal_core.py), para tratar COD_NAT igual nos dois
_MAPA_COD_NAT_ACUMULADOR = {'1102': '6000', '2102': '6000', '1403': '6001', '2403': '6001', '1101': '6002', '2101': '6002'}
_MAPA_COD_NAT_POR_CFOP = {'1102': '100', '2102': '100', '1403': '103', '2403': '103', '1556': '7005', '2556': '7005',
                          '1407': '7005', '2407': '7005', '1653': '121', '2653': '121'}
_COD_NAT_NOVOS = {'7005': 'MATERIAL DE USO E CONSUMO'}
_CUMULATIVOS, _NAO_CUMULATIVOS = ('51', '52', '53', '54'), ('01', '02', '03', '04', '31', '32')

TITULOS = {
    'cpf': ('CPF inválido (registro 0150)', '#8b5cf6'),
    'c100': ('Total do C100 menor que a soma dos itens (PIS/COFINS)', '#0ea5e9'),
    'c175dup': ('C175 duplicado dentro da mesma NFC-e', '#e8632b'),
    'mdup': ('Apuração duplicada (M210/M610)', '#d4711a'),
    'msoma': ('M205/M605 diferente do M200/M600', '#0f6e56'),
    'natureza': ('Natureza da operação sem cadastro no 0400 (COD_NAT)', '#1f2a5a'),
    'm105': ('Base do crédito por natureza (M105/M505)', '#14b8a6'),
    'm410': ('Natureza da receita fora da tabela (M410/M810)', '#e23d4c'),
    'contadores': ('Contadores do arquivo (9900, x990, 9999)', '#6b7392'),
}


# ------------------------------------------------------------------ utilidades
def _num(s):
    s = (s or '').strip()
    if not s:
        return 0.0
    try:
        return float(s.replace('.', '').replace(',', '.'))
    except ValueError:
        return 0.0


def _fmt(v, casas=2):
    v = round(v + 0.0, casas)
    return f'{v:.{casas}f}'.replace('.', ',')


def _brl(v):
    return f'{(v or 0):,.2f}'.replace(',', '§').replace('.', ',').replace('§', '.')


def _esc(s):
    return _html.escape('' if s is None else str(s))


def _partes(txt):
    return txt[1:-1].split('|')


def _monta(partes):
    return '|' + '|'.join(partes) + '|'


def _reg(l):
    return l['txt'][1:5]


def _ler(texto):
    eol = '\r\n' if '\r\n' in texto else '\n'
    linhas = texto.split(eol)
    termina = bool(linhas) and linhas[-1] == ''
    if termina:
        linhas.pop()
    return [{'n': i + 1, 'txt': t, 'novo': False} for i, t in enumerate(linhas)], eol, termina


def _escrever(L, eol, termina):
    return eol.join(l['txt'] for l in L) + (eol if termina else '')


def _cpf_valido(c):
    c = re.sub(r'\D', '', c or '')
    if len(c) != 11 or len(set(c)) == 1:
        return False
    for n in (9, 10):
        s = sum(int(c[i]) * (n + 1 - i) for i in range(n))
        if (s * 10) % 11 % 10 != int(c[n]):
            return False
    return True


def _ultimo_dia(L):
    p = _partes(L[0]['txt']) if L and _reg(L[0]) == '0000' else []
    return p[6] if len(p) > 6 else ''


# ------------------------------------------------------------------ detectores (antes e depois usam os mesmos)
def det_cpf(L):
    out = []
    for i, l in enumerate(L):
        if _reg(l) != '0150':
            continue
        p = _partes(l['txt'])
        cpf = p[5].strip() if len(p) > 5 else ''
        if cpf and not _cpf_valido(cpf):
            cod = p[1]
            usos = [x['n'] for x in L if _reg(x) != '0150' and f'|{cod}|' in x['txt']]
            out.append({'i': i, 'cod': cod, 'nome': p[2], 'cpf': cpf, 'usos': usos})
    return out


def det_c100(L):
    out, estado = [], {'cur': None, 'acc': None}

    def fecha():
        cur, acc = estado['cur'], estado['acc']
        if cur is None:
            return
        p = _partes(L[cur]['txt'])
        for campo, pos, chave in (('VL_PIS', 25, 'pis'), ('VL_COFINS', 26, 'cof')):
            atual = _num(p[pos]) if len(p) > pos else 0.0
            if atual + 0.005 < acc[chave]:
                out.append({'i': cur, 'campo': campo, 'pos': pos, 'atual': atual, 'esperado': round(acc[chave], 2), 'num': p[7], 'chv': p[8]})
    for i, l in enumerate(L):
        r = _reg(l)
        if r == 'C100':
            fecha()
            estado['cur'], estado['acc'] = i, {'pis': 0.0, 'cof': 0.0}
        elif r == 'C170' and estado['cur'] is not None:
            p = _partes(l['txt'])
            if len(p) > 35:
                if p[24] not in ('05', '75'):
                    estado['acc']['pis'] += _num(p[29])
                if p[30] not in ('05', '75'):
                    estado['acc']['cof'] += _num(p[35])
        elif not r.startswith('C') and estado['cur'] is not None:
            fecha()
            estado['cur'] = None
    fecha()
    return out


def _chave_c175(p):
    # chave do PVA: CFOP, CST_PIS, ALIQ_PIS, CST_COFINS, ALIQ_COFINS, ALIQ_PIS_QUANT, ALIQ_COFINS_QUANT, COD_CTA
    return (p[1], p[4], _num(p[6]), p[10], _num(p[12]), _num(p[8]), _num(p[14]), p[16])


def det_c175dup(L):
    grupos, cur, vistos = [], None, {}

    def fecha():
        for idxs in vistos.values():
            if len(idxs) > 1:
                grupos.append({'c100': cur, 'idxs': idxs})
    for i, l in enumerate(L):
        r = _reg(l)
        if r == 'C100':
            fecha()
            cur = i
            vistos.clear()
        elif r == 'C175' and cur is not None:
            p = _partes(l['txt'])
            if len(p) > 16:
                vistos.setdefault(_chave_c175(p), []).append(i)
    fecha()
    return grupos


def _m2xx_grupos(L, reg):
    g = defaultdict(list)
    for i, l in enumerate(L):
        if _reg(l) == reg:
            p = _partes(l['txt'])
            g[(p[1], _num(p[7]), _num(p[9]))].append(i)
    return [{'reg': reg, 'chave': k, 'idxs': v} for k, v in g.items() if len(v) > 1]


def det_mdup(L):
    return _m2xx_grupos(L, 'M210') + _m2xx_grupos(L, 'M610')


def _somas_m205(L, reg205):
    s = defaultdict(float)
    for l in L:
        if _reg(l) == reg205:
            p = _partes(l['txt'])
            s[p[1]] += _num(p[3])
    return s


def det_msoma(L):
    out = []
    for trib, r200, r205 in (('PIS', 'M200', 'M205'), ('COFINS', 'M600', 'M605')):
        m = next((i for i, l in enumerate(L) if _reg(l) == r200), None)
        if m is None:
            continue
        p = _partes(L[m]['txt'])
        somas = _somas_m205(L, r205)
        for campo, pos in (('08', 7), ('12', 11)):
            ref = _num(p[pos])
            if abs(somas.get(campo, 0.0) - ref) > 0.005 and (campo in somas or ref):
                out.append({'trib': trib, 'r200': r200, 'r205': r205, 'campo': campo, 'm200': ref, 'm205': somas.get(campo, 0.0), 'i200': m})
    return out


def _cods_0400(L):
    return {_partes(l['txt'])[1] for l in L if _reg(l) == '0400'}


def det_natureza(L):
    cods = _cods_0400(L)
    return [{'i': i, 'cod': _partes(l['txt'])[11], 'cfop': _partes(l['txt'])[10], 'item': _partes(l['txt'])[2], 'descr': _partes(l['txt'])[3]}
            for i, l in enumerate(L)
            if _reg(l) == 'C170' and len(_partes(l['txt'])) > 35 and _partes(l['txt'])[11] and _partes(l['txt'])[11] not in cods]


def _onde_existe(cod):
    return [f"{t} (CST {'/'.join(v['csts'])})" for t, v in _TABELAS_NATUREZA.items() if cod in v['itens']]


def det_m410(L):
    out, cst = [], ''
    for i, l in enumerate(L):
        r = _reg(l)
        if r in ('M400', 'M800'):
            cst = _partes(l['txt'])[1]
        elif r in ('M410', 'M810'):
            p = _partes(l['txt'])
            tab = _CST_PARA_TABELA.get(cst.zfill(2))
            if tab and tab in _TABELAS_NATUREZA and p[1] not in _TABELAS_NATUREZA[tab]['itens']:
                out.append({'i': i, 'reg': r, 'cst': cst, 'nat': p[1], 'valor': _num(p[2]), 'tabela': tab, 'existe_em': _onde_existe(p[1])})
    return out


def _esperados_contadores(L):
    corpo = [l for l in L if not _reg(l).startswith('9')]
    cont = Counter(_reg(l) for l in corpo)
    por_bloco = Counter(_reg(l)[0] for l in corpo)
    return cont, por_bloco


def det_contadores(L):
    cont, por_bloco = _esperados_contadores(L)
    out = []
    for l in L:
        r = _reg(l)
        p = _partes(l['txt'])
        if r.endswith('990') and not r.startswith('9') and len(p) > 1 and int(_num(p[1])) != por_bloco.get(r[0], 0):
            out.append({'reg': r, 'antes': int(_num(p[1])), 'depois': por_bloco.get(r[0], 0)})
        elif r == '9900' and len(p) > 2 and p[1] in cont and int(_num(p[2])) != cont[p[1]]:
            out.append({'reg': '9900 ' + p[1], 'antes': int(_num(p[2])), 'depois': cont[p[1]]})
    return out


def det_atencao_aliquota(L):
    """Linhas C175 (CST 01) com PIS/COFINS lançado diferente de base × alíquota declarada — sinal de tributação
    calculada por outra alíquota (ex.: 1,65%/7,6% em empresa com 0,65%/3%). Só informa, não altera."""
    out, cur, oper = [], None, None
    for i, l in enumerate(L):
        r = _reg(l)
        if r == 'C100':
            cur, oper = i, _partes(l['txt'])[1]
        elif r == 'C175' and oper == '1':
            p = _partes(l['txt'])
            if len(p) > 16 and p[4] == '01':
                bc, aq, pis, bcc, aqc, cof = _num(p[5]), _num(p[6]), _num(p[9]), _num(p[11]), _num(p[12]), _num(p[15])
                esp_p, esp_c = round(bc * aq / 100, 2), round(bcc * aqc / 100, 2)
                if abs(pis - esp_p) > 0.011 or abs(cof - esp_c) > 0.011:
                    out.append({'n': l['n'], 'bc': bc, 'aq': aq, 'pis': pis, 'esp_p': esp_p, 'aqc': aqc, 'cof': cof, 'esp_c': esp_c})
    return out


# ------------------------------------------------------------------ correções
def _fix_cpf(L, acoes, pend, ctx):
    remover = set()
    for f in det_cpf(L):
        if f['usos']:
            por_reg = Counter(_reg(next(x for x in L if x['n'] == n)) for n in f['usos'])
            uso = ', '.join(f'{q} × {r}' for r, q in por_reg.most_common())
            pend.append({'cat': 'cpf', 'linha': L[f['i']]['n'], 'titulo': f"CPF inválido ({f['cpf']}) no participante {f['cod']} — {f['nome']}",
                         'detalhe': f"O participante é usado em {len(f['usos'])} registro(s) ({uso}; ex.: linhas {', '.join(map(str, f['usos'][:5]))}), por isso não pode ser removido. "
                                    f"O sistema não inventa CPF: informe o CPF correto no cadastro do cliente (Domínio) e gere o SPED de novo.",
                         'usos': len(f['usos'])})
            continue
        remover.add(f['i'])
        acoes.append({'cat': 'cpf', 'tipo': 'removido', 'linha': L[f['i']]['n'], 'registro': '0150', 'antes': L[f['i']]['txt'], 'depois': '(registro removido)',
                      'motivo': f"CPF {f['cpf']} é inválido e o participante {f['cod']} não é usado em nenhum documento.", 'cod': f['cod'], 'nome': f['nome'], 'cpf': f['cpf']})
    return [l for i, l in enumerate(L) if i not in remover]


def _fix_c100(L, acoes, pend, ctx):
    for f in det_c100(L):
        l = L[f['i']]
        p = _partes(l['txt'])
        antes = l['txt']
        p[f['pos']] = _fmt(f['esperado'])
        l['txt'] = _monta(p)
        acoes.append({'cat': 'c100', 'tipo': 'alterado', 'linha': l['n'], 'registro': 'C100', 'antes': antes, 'depois': l['txt'],
                      'motivo': f"{f['campo']} do C100 estava menor que a soma dos itens (CST ≠ 05/75): passou de {_brl(f['atual'])} para {_brl(f['esperado'])}.",
                      'num': f['num'], 'chv': f['chv'], 'campo': f['campo'], 'v_antes': f['atual'], 'v_depois': f['esperado']})
    return L


def _fix_c175dup(L, acoes, pend, ctx):
    remover = set()
    for g in det_c175dup(L):
        idxs = g['idxs']
        ps = [_partes(L[i]['txt']) for i in idxs]
        base = list(ps[0])
        soma = lambda k: sum(_num(p[k]) for p in ps)
        for k in (2, 3, 5, 9, 11, 15):                      # VL_OPR, VL_DESC, BC PIS, VL_PIS, BC COFINS, VL_COFINS
            base[k] = _fmt(soma(k))
        for k in (7, 13):                                   # quantidades (só se informadas)
            if any(p[k].strip() for p in ps):
                base[k] = _fmt(soma(k), 3)
        antes = [L[i]['txt'] for i in idxs]
        novo = _monta(base)
        L[idxs[0]]['txt'] = novo
        remover.update(idxs[1:])
        c100 = _partes(L[g['c100']]['txt'])
        acoes.append({'cat': 'c175dup', 'tipo': 'agrupado', 'linha': [L[i]['n'] for i in idxs], 'registro': 'C175', 'antes': antes, 'depois': novo,
                      'motivo': f"{len(idxs)} linhas C175 com a mesma chave (CFOP {ps[0][1]}, CST {ps[0][4]}, alíquotas {ps[0][6]}/{ps[0][12]}) viraram uma, somando os valores.",
                      'doc': c100[7], 'c100_linha': L[g['c100']]['n'], 'cfop': ps[0][1], 'cst': ps[0][4],
                      'op': [_num(p[2]) for p in ps], 'pis': [_num(p[9]) for p in ps], 'cof': [_num(p[15]) for p in ps],
                      'op_dep': _num(base[2]), 'pis_dep': _num(base[9]), 'cof_dep': _num(base[15])})
    return [l for i, l in enumerate(L) if i not in remover]


# (removido: não usado)


def _ajustes_do_grupo(L, ultimo_idx, r220):
    r225 = 'M225' if r220 == 'M220' else 'M625'
    ac = rd = 0.0
    j = ultimo_idx + 1
    while j < len(L) and _reg(L[j]) in (r220, r225):
        if _reg(L[j]) == r220:
            p = _partes(L[j]['txt'])
            if p[1] == '1':
                ac += _num(p[2])
            else:
                rd += _num(p[2])
        j += 1
    return round(ac, 2), round(rd, 2)


def _fix_mdup(L, acoes, pend, ctx):
    remover = set()
    for g in det_mdup(L):
        reg, idxs = g['reg'], g['idxs']
        r220 = 'M220' if reg == 'M210' else 'M620'
        ps = [_partes(L[i]['txt']) for i in idxs]
        mesma_base = all(p[2:8] == ps[0][2:8] and p[10] == ps[0][10] for p in ps)
        ac, rd = _ajustes_do_grupo(L, idxs[-1], r220)
        corretas = [k for k, p in enumerate(ps) if abs(_num(p[11]) - ac) < 0.005 and abs(_num(p[12]) - rd) < 0.005]
        if not mesma_base or len(corretas) != 1:
            pend.append({'cat': 'mdup', 'qtd': len(idxs), 'linha': L[idxs[0]]['n'], 'titulo': f'{reg} duplicado (COD_CONT {g["chave"][0]})',
                         'detalhe': 'As linhas não são iguais na base ou nenhuma bate com os ajustes lançados: revisão manual.'})
            continue
        manter = corretas[0]
        for k, i in enumerate(idxs):
            if k != manter:
                remover.add(i)
                acoes.append({'cat': 'mdup', 'tipo': 'removido', 'linha': L[i]['n'], 'registro': reg, 'antes': L[i]['txt'], 'depois': '(registro removido)',
                              'motivo': f"Duplicado do {reg} da linha {L[idxs[manter]]['n']}: mesma base, mas sem os ajustes ({r220}: acréscimos {_brl(ac)} / reduções {_brl(rd)}) que estão na linha mantida.",
                              'mantida': L[idxs[manter]]['n'], 'v_per_removida': _num(ps[k][15]), 'v_per_mantida': _num(ps[manter][15]), 'cod': g['chave'][0]})
    ctx['mdup_removidos'] = len(remover)
    return [l for i, l in enumerate(L) if i not in remover]


def _recalc_m200(L, trib, ctx, motivo):
    r200, r210 = ('M200', 'M210') if trib == 'PIS' else ('M600', 'M610')
    m = next((i for i, l in enumerate(L) if _reg(l) == r200), None)
    if m is None:
        return
    p = _partes(L[m]['txt'])
    linhas210 = [_partes(l['txt']) for l in L if _reg(l) == r210]
    nc_l = [x for x in linhas210 if x[1] in _NAO_CUMULATIVOS]
    cum_l = [x for x in linhas210 if x[1] in _CUMULATIVOS]
    novo = list(p)
    if nc_l:                                  # só recalcula a parte que tem apuração (M210/M610) correspondente
        novo[1] = _fmt(sum(_num(x[15]) for x in nc_l))
        novo[4] = _fmt(_num(novo[1]) - _num(novo[2]) - _num(novo[3]))
        novo[7] = _fmt(_num(novo[4]) - _num(novo[5]) - _num(novo[6]))
    if cum_l:
        novo[8] = _fmt(sum(_num(x[15]) for x in cum_l))
        novo[11] = _fmt(_num(novo[8]) - _num(novo[9]) - _num(novo[10]))
    novo[12] = _fmt(_num(novo[7]) + _num(novo[11]))
    if [_num(x) for x in novo[1:]] == [_num(x) for x in p[1:]]:
        return
    antes = L[m]['txt']
    L[m]['txt'] = _monta(novo)
    nomes = ['', 'VL_TOT_CONT_NC_PER', 'VL_TOT_CRED_DESC', 'VL_TOT_CRED_DESC_ANT', 'VL_TOT_CONT_NC_DEV', 'VL_RET_NC', 'VL_OUT_DED_NC', 'VL_CONT_NC_REC',
             'VL_TOT_CONT_CUM_PER', 'VL_RET_CUM', 'VL_OUT_DED_CUM', 'VL_CONT_CUM_REC', 'VL_TOT_CONT_REC']
    campos = [{'campo': nomes[k], 'antes': _num(p[k]), 'depois': _num(novo[k])} for k in range(1, 13) if _num(p[k]) != _num(novo[k])]
    ctx.setdefault('recalc', []).append({'trib': trib, 'registro': r200, 'linha': L[m]['n'], 'campos': campos, 'antes': antes, 'depois': L[m]['txt'], 'motivo': motivo})


def _fix_msoma(L, acoes, pend, ctx):
    if ctx.get('mdup_removidos'):
        for trib in ('PIS', 'COFINS'):
            _recalc_m200(L, trib, ctx, 'Recalculado a partir do M210/M610 depois de remover a apuração duplicada.')
    for trib, campo in [(f['trib'], f['campo']) for f in det_msoma(L)]:
        f = next((x for x in det_msoma(L) if x['trib'] == trib and x['campo'] == campo), None)
        if f is None:
            continue
        r210, r220 = ('M210', 'M220') if trib == 'PIS' else ('M610', 'M620')
        codigos = _CUMULATIVOS if campo == '12' else _NAO_CUMULATIVOS
        alvos = [i for i, l in enumerate(L) if _reg(l) == r210 and _partes(l['txt'])[1] in codigos]
        if len(alvos) != 1:
            pend.append({'cat': 'msoma', 'linha': L[f['i200']]['n'], 'titulo': f"{f['r205']} ({trib}) difere de {f['r200']}",
                         'detalhe': f"{f['r205']} soma {_brl(f['m205'])} e {f['r200']} traz {_brl(f['m200'])}, mas não há um único {r210} para receber o ajuste automático."})
            continue
        i = alvos[0]
        dif = round(f['m205'] - f['m200'], 2)
        ind = '1' if dif > 0 else '0'
        valor = abs(dif)
        p = _partes(L[i]['txt'])
        antes_m = L[i]['txt']
        if ind == '1':
            p[11] = _fmt(_num(p[11]) + valor)
        else:
            p[12] = _fmt(_num(p[12]) + valor)
        p[15] = _fmt(_num(p[15]) + dif)
        L[i]['txt'] = _monta(p)
        fim_dt = _ultimo_dia(L)
        descr = (f"Ajuste incluido pelo FiscoCont+ ({ctx['hoje']}): diferenca entre o {f['r205']} ({_brl(f['m205'])}) e a apuracao do {r210} ({_brl(f['m200'])})")
        novo_rec = _monta([r220, ind, _fmt(valor), '06', '', descr, fim_dt])
        j = i + 1
        while j < len(L) and _reg(L[j]) in (r220, 'M225' if r220 == 'M220' else 'M625', 'M211', 'M230'):
            j += 1
        L.insert(j, {'n': None, 'txt': novo_rec, 'novo': True})
        ctx['ajustes'].append({'tributo': trib, 'registro': r220, 'ind': ind, 'valor': valor, 'cod': '06', 'descr': descr, 'dt': fim_dt, 'texto': novo_rec,
                               'pai': r210, 'pai_linha': L[i]['n'], 'campo': f"VL_CONT_{'CUM' if campo == '12' else 'NC'}_REC",
                               'm200': f['m200'], 'm205': f['m205'], 'pai_antes': antes_m, 'pai_depois': L[i]['txt']})
        acoes.append({'cat': 'msoma', 'tipo': 'incluido', 'linha': None, 'registro': r220, 'antes': '(não existia)', 'depois': novo_rec,
                      'motivo': f"{f['r205']} ({trib}) soma {_brl(f['m205'])} e a apuração do {r210} dava {_brl(f['m200'])}: incluído ajuste de {'acréscimo' if ind == '1' else 'redução'} de {_brl(valor)} (código 06) no {r220}.",
                      'trib': trib, 'm200': f['m200'], 'm205': f['m205'], 'valor': valor, 'ind': ind})
        acoes.append({'cat': 'msoma', 'tipo': 'alterado', 'linha': L[i]['n'], 'registro': r210, 'antes': antes_m, 'depois': L[i]['txt'],
                      'motivo': f"{r210}: ajuste de {'acréscimo' if ind == '1' else 'redução'} e contribuição do período atualizados com o ajuste incluído.", 'trib': trib})
    for trib in ('PIS', 'COFINS'):
        _recalc_m200(L, trib, ctx, 'Recalculado a partir do M210/M610 depois do ajuste incluído.' if ctx['ajustes'] else 'Recalculado a partir do M210/M610.')
    return L


def _aprender_cfop(L):
    c = defaultdict(Counter)
    cods = _cods_0400(L)
    for l in L:
        if _reg(l) == 'C170':
            p = _partes(l['txt'])
            if len(p) > 35 and p[11] in cods:
                c[p[10]][p[11]] += 1
    return c


def _resolve_cod_nat(cfop, aprendido, cods):
    def topo(cf):
        cnt = aprendido.get(cf)
        if cnt:
            cod, q = cnt.most_common(1)[0]
            if q / sum(cnt.values()) >= 0.9:
                return cod, q
        return None, 0
    cod, q = topo(cfop)
    if cod:
        return cod, f'aprendido neste arquivo: itens com CFOP {cfop} já usam {cod}', False
    irmao = {'1': '2', '2': '1', '5': '6', '6': '5'}.get(cfop[:1])
    if irmao:
        cod, q = topo(irmao + cfop[1:])
        if cod:
            return cod, f'CFOP irmão {irmao + cfop[1:]} já usa {cod} neste arquivo', False
    cod = _MAPA_COD_NAT_ACUMULADOR.get(cfop)
    if cod and cod in cods:
        return cod, f'mapa de acumuladores do SPED Fiscal (CFOP {cfop} → {cod}, já cadastrado no 0400)', False
    cod = _MAPA_COD_NAT_POR_CFOP.get(cfop)
    if cod and (cod in cods or cod in _COD_NAT_NOVOS):
        return cod, f'mapa padrão do SPED Fiscal (CFOP {cfop} → {cod})', cod not in cods
    return None, '', False


def _fix_natureza(L, acoes, pend, ctx):
    achados = det_natureza(L)
    if not achados:
        return L
    cods = _cods_0400(L)
    aprendido = _aprender_cfop(L)
    novos_0400 = {}
    por_cfop = defaultdict(list)
    for f in achados:
        por_cfop[f['cfop']].append(f)
    for cfop, lista in por_cfop.items():
        cod, regra, criar = _resolve_cod_nat(cfop, aprendido, cods)
        if not cod:
            pend.append({'cat': 'natureza', 'qtd': len(lista), 'linha': L[lista[0]['i']]['n'], 'titulo': f'{len(lista)} item(ns) com CFOP {cfop} e natureza {lista[0]["cod"]} sem cadastro no 0400',
                         'detalhe': 'Não achei um acumulador para esse CFOP neste arquivo nem nos mapas do SPED Fiscal. Cadastre no 0400 ou informe a natureza.'})
            continue
        if criar:
            novos_0400[cod] = _COD_NAT_NOVOS[cod]
        for f in lista:
            l = L[f['i']]
            p = _partes(l['txt'])
            antes = l['txt']
            p[11] = cod
            l['txt'] = _monta(p)
            acoes.append({'cat': 'natureza', 'tipo': 'alterado', 'linha': l['n'], 'registro': 'C170', 'antes': antes, 'depois': l['txt'],
                          'motivo': f"COD_NAT {f['cod']} não existe no 0400 → {cod} ({regra}).", 'item': f['item'], 'descr': f['descr'], 'cfop': cfop,
                          'cod_antes': f['cod'], 'cod_depois': cod, 'regra': regra})
    if novos_0400:
        ult = max(i for i, l in enumerate(L) if _reg(l) == '0400')
        for k, (cod, nome) in enumerate(sorted(novos_0400.items())):
            rec = _monta(['0400', cod, nome])
            L.insert(ult + 1 + k, {'n': None, 'txt': rec, 'novo': True})
            acoes.append({'cat': 'natureza', 'tipo': 'incluido', 'linha': None, 'registro': '0400', 'antes': '(não existia)', 'depois': rec,
                          'motivo': f'Natureza {cod} ({nome}) cadastrada no 0400, igual ao corretor do SPED Fiscal.', 'cod_novo': cod})
    return L


def _fix_m105(L, acoes, pend, ctx):
    for e in ctx.get('pva', {}).get('m105', []):
        r105 = 'M105' if e['tributo'] == 'PIS' else 'M505'
        alvo = next((i for i, l in enumerate(L) if _reg(l) == r105 and _partes(l['txt'])[1] == e['nat'] and _partes(l['txt'])[2] == e['cst']), None)
        if alvo is None:
            continue
        p = _partes(L[alvo]['txt'])
        atual = _num(p[3])
        item = {'cat': 'm105', 'registro': r105, 'nat': e['nat'], 'cst': e['cst'], 'esperado': e['esperado'], 'no_arquivo': atual, 'conteudo_pva': e['conteudo'], 'linha': L[alvo]['n']}
        if abs(atual - e['esperado']) < 0.005:
            item.update({'tipo': 'ja_correto', 'antes': L[alvo]['txt'], 'depois': L[alvo]['txt'],
                         'motivo': f"O arquivo já traz o valor esperado pelo PVA ({_brl(e['esperado'])}); o relatório foi gerado de uma versão anterior (tinha {_brl(e['conteudo'])})."})
        else:
            antes = L[alvo]['txt']
            cum = _num(p[4])
            p[3], p[5], p[6] = _fmt(e['esperado']), _fmt(e['esperado'] - cum), _fmt(e['esperado'] - cum)
            L[alvo]['txt'] = _monta(p)
            item.update({'tipo': 'alterado', 'antes': antes, 'depois': L[alvo]['txt'],
                         'motivo': f"Base do crédito da natureza {e['nat']}/CST {e['cst']} ajustada de {_brl(atual)} para {_brl(e['esperado'])} (valor esperado pelo PVA)."})
        acoes.append(item)
    return L


def _fix_m410(L, acoes, pend, ctx):
    for f in det_m410(L):
        onde = '; '.join(f['existe_em']) or 'nenhuma das tabelas carregadas'
        pend.append({'cat': 'm410', 'linha': L[f['i']]['n'], 'titulo': f"{f['reg']}: natureza {f['nat']} sob CST {f['cst']} (R$ {_brl(f['valor'])})",
                     'detalhe': f"O código {f['nat']} não existe na tabela {f['tabela']} (CST {f['cst']}). Ele existe em: {onde}. Decisão sua: ou o CST da receita está errado (a receita iria para o CST da tabela correta) "
                                f"ou a natureza está errada. O sistema não muda classificação tributária sozinho.",
                     'reg': f['reg'], 'cst': f['cst'], 'nat': f['nat'], 'valor': f['valor'], 'existe_em': f['existe_em']})
    return L


def _recontar(L, acoes):
    cont, por_bloco = _esperados_contadores(L)
    antigos = {}
    for l in L:
        r = _reg(l)
        p = _partes(l['txt'])
        if r == '9900' and len(p) > 2:
            antigos['9900 ' + p[1]] = int(_num(p[2]))
        elif r.endswith('990') and len(p) > 1:
            antigos[r] = int(_num(p[1]))
        elif r == '9999':
            antigos[r] = int(_num(p[1]))
    ordem = [p[1] for l in L if _reg(l) == '9900' for p in [_partes(l['txt'])] if len(p) > 2]
    corpo = [l for l in L if not _reg(l).startswith('9')]
    vistos = list(dict.fromkeys(_reg(l) for l in corpo))
    regs = [r for r in ordem if r in vistos and r not in ('9001', '9900', '9990', '9999')] + [r for r in vistos if r not in ordem]
    regs += ['9001', '9900', '9990', '9999']
    n9900 = len(regs)
    bloco9 = [{'n': None, 'txt': '|9001|0|', 'novo': False}]
    qtd = dict(cont)
    qtd.update({'9001': 1, '9900': n9900, '9990': 1, '9999': 1})
    for r in regs:
        bloco9.append({'n': None, 'txt': _monta(['9900', r, str(qtd[r])]), 'novo': False})
    bloco9.append({'n': None, 'txt': _monta(['9990', str(n9900 + 3)]), 'novo': False})
    for l in corpo:
        r = _reg(l)
        if r.endswith('990'):
            l['txt'] = _monta([r, str(por_bloco.get(r[0], 0))])
    total = len(corpo) + len(bloco9) + 1
    bloco9.append({'n': None, 'txt': _monta(['9999', str(total)]), 'novo': False})
    novos = {'9900 ' + r: qtd[r] for r in regs}
    novos.update({r: por_bloco.get(r[0], 0) for r in {_reg(l) for l in corpo if _reg(l).endswith('990')}})
    novos.update({'9990': n9900 + 3, '9999': total})
    mudou = []
    for k, v in novos.items():
        a = antigos.get(k)
        if (a is not None and a != v) or (a is None and k.startswith('9900 ')):
            mudou.append({'reg': k, 'antes': a, 'depois': v})
    for m in mudou:
        acoes.append({'cat': 'contadores', 'tipo': 'alterado', 'linha': None, 'registro': m['reg'], 'antes': m['antes'], 'depois': m['depois'],
                      'motivo': 'Contador recalculado depois das correções.'})
    return corpo + bloco9


# ------------------------------------------------------------------ PVA (PDF de erros)
def ler_erros_pva(caminho):
    import pdfplumber
    with pdfplumber.open(caminho) as pdf:
        texto = '\n'.join((p.extract_text() or '') for p in pdf.pages)
    m = re.search(r'Total de Erros\s+(\d+)', texto)
    if not m:
        raise ValueError('não parece ser o relatório "Pendências de Validação" do PVA')
    total = int(m.group(1))
    cnpj = re.search(r'CNPJ:\s*([\d./-]+)', texto)
    i = texto.find('Total de Erros')
    j = texto.find('\nERROS', i)
    resumo = texto[i:j if j > 0 else i + 3000]
    cats = [('CPF inválido', 'cpf'), ('maior ou igual à soma', 'c100'), ('Duplicidade de ocorrência', 'dup'), ('somatório dos registros M205', 'msoma'),
            ('Código da natureza inválido', 'natureza'), ('somatório dos valores das bases', 'm105'), ('Natureza da Receita inválida', 'm410')]
    por_cat = {}
    for linha in resumo.split('\n'):
        q = re.search(r'(\d+)\s*$', linha)
        for chave, cat in cats:
            if chave in linha and q:
                por_cat[cat] = int(q.group(1))
    m105 = []
    for mm in re.finditer(r'(\d{3,8})\s+VL_BC_[A-Z_]+\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})\s+M([15])05\s+\|M[15]05\|(\d{2})\|(\d{2})\|', texto):
        m105.append({'linha': int(mm.group(1)), 'tributo': 'PIS' if mm.group(4) == '1' else 'COFINS', 'esperado': _num(mm.group(2)),
                     'conteudo': _num(mm.group(3)), 'nat': mm.group(5), 'cst': mm.group(6)})
    return {'total': total, 'por_cat': por_cat, 'm105': m105, 'cnpj': re.sub(r'\D', '', cnpj.group(1)) if cnpj else ''}


# ------------------------------------------------------------------ orquestração
def corrigir_efd(texto, pva=None, nome_arquivo='sped.txt', hoje=''):
    L, eol, termina = _ler(texto)
    ctx = {'pva': pva or {}, 'hoje': hoje or '', 'ajustes': [], 'mapa_n': {}}
    p0 = _partes(L[0]['txt']) if L and _reg(L[0]) == '0000' else []
    empresa = {'nome': p0[7] if len(p0) > 7 else '', 'cnpj': p0[8] if len(p0) > 8 else '', 'ini': p0[5] if len(p0) > 5 else '', 'fim': p0[6] if len(p0) > 6 else ''}
    avisos = []
    if pva and pva.get('cnpj') and empresa['cnpj'] and pva['cnpj'] != empresa['cnpj']:
        avisos.append(f"O relatório do PVA é do CNPJ {pva['cnpj']}, mas o SPED é do CNPJ {empresa['cnpj']}.")
    antes = {
        'cpf': det_cpf(L), 'c100': det_c100(L), 'c175dup': det_c175dup(L), 'mdup': det_mdup(L), 'msoma': det_msoma(L),
        'natureza': det_natureza(L), 'm410': det_m410(L), 'contadores': det_contadores(L),
    }
    atencao = det_atencao_aliquota(L)
    n_antes = len(L)
    acoes, pend = [], []
    for fix in (_fix_cpf, _fix_c100, _fix_c175dup, _fix_mdup, _fix_msoma, _fix_natureza, _fix_m105, _fix_m410):
        L = fix(L, acoes, pend, ctx)
    L = _recontar(L, acoes)
    depois = {'cpf': det_cpf(L), 'c100': det_c100(L), 'c175dup': det_c175dup(L), 'mdup': det_mdup(L), 'msoma': det_msoma(L),
              'natureza': det_natureza(L), 'm410': det_m410(L), 'contadores': det_contadores(L)}
    pva_cat = (pva or {}).get('por_cat', {})
    dup_total = pva_cat.get('dup')
    cats = []
    for cid in ('cpf', 'c100', 'c175dup', 'mdup', 'msoma', 'natureza', 'm105', 'm410', 'contadores'):
        titulo, cor = TITULOS[cid]
        a_cat = [a for a in acoes if a['cat'] == cid]
        pendentes = sum(x.get('qtd', 1) for x in pend if x['cat'] == cid)
        if cid == 'm105':
            achados = len(ctx['pva'].get('m105', []))
            corrigidos = len([a for a in a_cat if a['tipo'] in ('alterado', 'ja_correto')])
        elif cid == 'c175dup':
            achados = sum(len(g['idxs']) for g in antes['c175dup'])
            corrigidos = sum(len(a['linha']) for a in a_cat)
        elif cid == 'mdup':
            achados = sum(len(g['idxs']) for g in antes['mdup'])
            corrigidos = achados - pendentes
        elif cid == 'msoma':
            achados = len(antes['msoma'])
            corrigidos = len([a for a in a_cat if a['tipo'] == 'incluido'])
        elif cid == 'natureza':
            achados = len(antes['natureza'])
            corrigidos = len([a for a in a_cat if a['tipo'] == 'alterado'])
        elif cid == 'contadores':
            achados, corrigidos = 0, len(a_cat)
        elif cid == 'm410':
            achados, corrigidos = len(antes['m410']), 0
        else:
            achados, corrigidos = len(antes[cid]), len(a_cat)
        if not achados and not a_cat and not pendentes:
            continue
        cats.append({'id': cid, 'titulo': titulo, 'cor': cor, 'achados': achados, 'corrigidos': corrigidos, 'pendentes': pendentes,
                     'acoes': a_cat, 'consequencia': cid == 'contadores'})
    verif = [
        ('CPF inválido em participante sem uso', len(antes['cpf']), len([f for f in depois['cpf'] if not f['usos']])),
        ('Total do C100 menor que a soma dos itens', len(antes['c100']), len(depois['c100'])),
        ('C175 duplicado na mesma NFC-e (grupos)', len(antes['c175dup']), len(depois['c175dup'])),
        ('M210/M610 duplicado (grupos)', len(antes['mdup']), len(depois['mdup'])),
        ('M205/M605 diferente do M200/M600', len(antes['msoma']), len(depois['msoma'])),
        ('COD_NAT sem cadastro no 0400', len(antes['natureza']), len(depois['natureza'])),
        ('Natureza da receita fora da tabela (pendência)', len(antes['m410']), len(depois['m410'])),
        ('Contadores (9900/x990/9999) divergentes', len(antes['contadores']), len(depois['contadores'])),
    ]
    resumo = {
        'empresa': empresa, 'arquivo': nome_arquivo, 'hoje': hoje, 'linhas_antes': n_antes, 'linhas_depois': len(L),
        'categorias': cats, 'ajustes': ctx['ajustes'], 'pendencias': pend, 'recalc': ctx.get('recalc', []), 'atencao': atencao,
        'verificacao': verif, 'avisos': avisos, 'pva': {'total': (pva or {}).get('total'), 'por_cat': pva_cat} if pva else None,
        'removidas': sum(1 for a in acoes if a['tipo'] in ('removido',)) + sum(len(a['linha']) - 1 for a in acoes if a['tipo'] == 'agrupado'),
        'alteradas': sum(1 for a in acoes if a['tipo'] == 'alterado' and a['cat'] != 'contadores'),
        'incluidas': sum(1 for a in acoes if a['tipo'] == 'incluido'),
    }
    return _escrever(L, eol, termina), resumo


# ------------------------------------------------------------------ relatório (HTML com dashboards animados, por tipo de erro)
_CSS_CORR = """
.aviso2{background:linear-gradient(90deg,#fdf1dc,#fff8ea);border:1px solid #efc98f;border-radius:12px;padding:11px 14px;font-size:12px;color:#633806;line-height:1.55;margin:10px 20px}
.cab-cat{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:0 0 10px}
.cab-cat .tit{font-size:15px;font-weight:700;color:var(--ink)}
.pil{display:inline-block;border-radius:999px;padding:3px 12px;font-size:11.5px;font-weight:700;box-shadow:0 3px 8px rgba(31,42,90,.12)}
.pil.ach{background:#eef0f6;color:#232a3d}.pil.cor{background:#e1f5ee;color:#085041}.pil.pen{background:#faeeda;color:#854f0b}
.txt{font-size:12.5px;line-height:1.6;color:var(--ink);margin:6px 0}
.txt b.rot{color:var(--navy)}
.reg{font-family:Consolas,'Courier New',monospace;font-size:11px;background:#f6f8fd;border:1px solid #e3e8f4;border-radius:8px;padding:6px 9px;margin:4px 0;word-break:break-all;white-space:pre-wrap}
.reg.novo{background:#e8f8f1;border-color:#a8dcc8}
.reg.velho{background:#fdf0f0;border-color:#f0c4c4;text-decoration:line-through;text-decoration-color:rgba(180,35,24,.45)}
.destaque-aj{border:2px solid #0f6e56;background:linear-gradient(180deg,#f2fbf7,#fff)}
.kv{display:grid;grid-template-columns:200px 1fr;gap:6px 14px;font-size:12.5px;margin:10px 0}
.kv span:nth-child(odd){color:var(--ink2)}
.sel{display:inline-block;background:#0f6e56;color:#fff;border-radius:6px;padding:2px 9px;font-size:11px;font-weight:700;margin-left:8px}
.bar-grp{display:flex;flex-direction:column;align-items:center;min-width:92px}
.bar-par{display:flex;align-items:flex-end;gap:6px;height:210px}
.b2{width:34px;border-radius:7px 7px 3px 3px;height:0;transition:height 1.1s cubic-bezier(.2,.8,.2,1)}
.rot-bar{font-size:10.5px;color:var(--ink2);margin-top:6px;text-align:center;max-width:96px}
.val-bar{font-size:11px;font-weight:800;margin-bottom:4px}
.ok{color:#0f6e56;font-weight:700}.bad{color:#b42318;font-weight:700}
"""

_JS_CORR = """
(function(){
  var D=__DADOS__, CX=110, CY=110, R=92, tot=0, i;
  for(i=0;i<D.length;i++) tot+=D[i].a;
  function pt(d){var a=(d-90)*Math.PI/180;return [CX+R*Math.cos(a), CY+R*Math.sin(a)];}
  var svg=document.getElementById('corrSlices'), ang=0, html='';
  for(i=0;i<D.length;i++){
    var fr=D[i].a/tot, a1=ang+fr*360;
    if(D.length===1){ html+='<circle cx="'+CX+'" cy="'+CY+'" r="'+R+'" fill="'+D[i].c+'" stroke="#fff" stroke-width="2.5"/>'; }
    else {
      var p0=pt(ang), p1=pt(a1), g=(a1-ang)>180?1:0;
      html+='<path d="M'+CX+' '+CY+' L'+p0[0].toFixed(2)+' '+p0[1].toFixed(2)+' A'+R+' '+R+' 0 '+g+' 1 '+p1[0].toFixed(2)+' '+p1[1].toFixed(2)+' Z" fill="'+D[i].c+'" stroke="#fff" stroke-width="2.5" stroke-linejoin="round"/>';
    }
    ang=a1;
  }
  svg.innerHTML=html;
  requestAnimationFrame(function(){ setTimeout(function(){
    document.getElementById('corrPizza').style.transform='rotate(360deg)';
    var bs=document.querySelectorAll('.b2'); for(var k=0;k<bs.length;k++) bs[k].style.height=bs[k].dataset.alvo+'px';
  },150); });
  var cs=document.querySelectorAll('.cnt');
  Array.prototype.forEach.call(cs,function(el,idx){
    var alvo=parseInt(el.dataset.alvo,10), ini=null;
    function passo(ts){ if(!ini) ini=ts; var p=Math.min(1,(ts-ini)/1000), f=1-Math.pow(1-p,3); el.textContent=Math.round(alvo*f).toLocaleString('pt-BR'); if(p<1) requestAnimationFrame(passo); }
    setTimeout(function(){ requestAnimationFrame(passo); }, 120*idx);
  });
})();
"""

_EXPLICA = {
    'cpf': ('O PVA rejeita CPF com dígitos verificadores inválidos (ex.: 88888888888, usado como "genérico").',
            'Se o participante não fosse usado em nenhum documento, o registro 0150 seria removido. Quando é usado, o sistema NÃO inventa CPF: deixa como pendência.'),
    'c100': ('No C100, o VL_PIS e o VL_COFINS não podem ser menores que a soma dos itens (C170) com CST diferente de 05 e 75.',
             'O total do C100 foi acertado para a soma dos itens.'),
    'c175dup': ('Dentro de uma mesma nota, o C175 não pode ter duas linhas com a mesma chave (CFOP, CST, alíquotas e conta). O PVA aponta as duas linhas de cada par.',
                'As linhas repetidas viraram uma só, somando valor da operação, desconto, bases, PIS e COFINS. Os totais do documento não mudam.'),
    'mdup': ('O M210 (PIS) e o M610 (COFINS) só podem ter uma linha por tipo de contribuição e alíquota. A apuração foi lançada duas vezes: uma sem ajustes e outra já com os ajustes das devoluções (M220/M620), o que dobrava o M200/M600.',
             'Ficou a linha cujos ajustes batem com os M220/M620 lançados; a repetida foi removida e o M200/M600 recalculado.'),
    'msoma': ('A soma do M205/M605 (valor por código de DARF) precisa ser igual ao campo 08 ou 12 do M200/M600.',
              'Depois de remover a apuração duplicada e recalcular, o M205/M605 continuou diferente. Conforme a orientação, o sistema INCLUIU um ajuste no M220/M620 com o valor da diferença, mantendo o M205/M605 como estava.'),
    'natureza': ('Todo COD_NAT usado no C170 precisa estar cadastrado no registro 0400. O Domínio deixou COD_NAT = 0 em itens de compra.',
                 'O sistema trocou o 0 pelo acumulador do mesmo CFOP (aprendido neste arquivo; se não houver, o mapa do SPED Fiscal) e cadastrou no 0400 o que faltava.'),
    'm105': ('A base do crédito por natureza (M105/M505) precisa fechar com a soma dos documentos por natureza e CST.',
             'Os valores esperados vêm do próprio relatório do PVA. Se o arquivo já traz o valor esperado, nada é alterado.'),
    'm410': ('A natureza da receita (M410/M810) precisa existir na tabela oficial do CST do M400/M800.',
             'O sistema não altera classificação tributária sozinho: fica como pendência, com a indicação de onde o código existe.'),
    'contadores': ('Depois das correções o número de linhas muda, então os contadores do arquivo ficam errados.',
                   'Os contadores 9900, x990 e 9999 foram refeitos. Não é um erro do PVA: é consequência das correções.'),
}
_CURTO = {'cpf': 'CPF', 'c100': 'C100', 'c175dup': 'C175 duplic.', 'mdup': 'M210/M610', 'msoma': 'M205/M605', 'natureza': 'Natureza 0400', 'm105': 'M105/M505', 'm410': 'M410/M810'}


def _mix(hexc, alvo, f):
    h = hexc.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return '#%02x%02x%02x' % (int(r + (alvo[0] - r) * f), int(g + (alvo[1] - g) * f), int(b + (alvo[2] - b) * f))


def _grad_barra(cor):
    esc, claro = _mix(cor, (0, 0, 0), .35), _mix(cor, (255, 255, 255), .35)
    return f'linear-gradient(90deg,{esc} 0%,{cor} 28%,{claro} 46%,{cor} 70%,{esc} 100%)'


def _dt(s):
    return f'{s[:2]}/{s[2:4]}/{s[4:]}' if re.fullmatch(r'\d{8}', s or '') else (s or '')


def _reg_html(txt, classe=''):
    return f'<div class="reg {classe}">{_esc(txt)}</div>'


def _tab_cat(c, res):
    from efd_contribuicoes import _linhas_tabela
    a = c['acoes']
    cid = c['id']
    if cid == 'cpf':
        p = [x for x in res['pendencias'] if x['cat'] == 'cpf']
        return _linhas_tabela(['Linha', 'Situação', 'Detalhe'], [[str(x['linha']), '<span class="st dif">Pendente</span>', _esc(x['titulo'] + ' — ' + x['detalhe'])] for x in p] +
                              [[str(x['linha']), '<span class="st ok">Removido</span>', _esc(f"0150 {x['cod']} ({x['nome']}) — {x['motivo']}")] for x in a], ['l', 'c', 'l'])
    if cid == 'c100':
        return _linhas_tabela(['Linha', 'Nota nº', 'Chave (final)', 'Campo', 'Antes', 'Depois'],
                              [[str(x['linha']), _esc(x['num']), '…' + _esc(x['chv'][-8:]), x['campo'], _brl(x['v_antes']), f'<b>{_brl(x["v_depois"])}</b>'] for x in a], ['l', 'l', 'l', 'l', 'r', 'r'])
    if cid == 'c175dup':
        def soma(v):
            return ' + '.join(_brl(i) for i in v) + ' = <b>' + _brl(sum(v)) + '</b>'
        return _linhas_tabela(['Nota (linha do C100)', 'CFOP', 'CST', 'Linhas C175 unidas', 'Valor da operação', 'PIS', 'COFINS'],
                              [[f'…{_esc(x["doc"][-8:])} (linha {x["c100_linha"]})', _esc(x['cfop']), _esc(x['cst']), ' + '.join(str(n) for n in x['linha']),
                                soma(x['op']), soma(x['pis']), soma(x['cof'])] for x in a], ['l', 'l', 'l', 'l', 'r', 'r', 'r'])
    if cid == 'mdup':
        t1 = _linhas_tabela(['Registro', 'COD_CONT', 'Linha removida', 'Linha mantida', 'Contribuição do período (removida → mantida)', 'Motivo'],
                            [[x['registro'], _esc(x['cod']), str(x['linha']), str(x['mantida']), f'{_brl(x["v_per_removida"])} → <b>{_brl(x["v_per_mantida"])}</b>', _esc(x['motivo'])] for x in a],
                            ['l', 'l', 'l', 'l', 'r', 'l'])
        cadeia = defaultdict(list)
        for r in res['recalc']:
            cadeia[r['registro']].append(r)
        linhas = []
        for reg, lst in cadeia.items():
            for r in lst:
                for f in r['campos']:
                    linhas.append([f'{reg} (linha {r["linha"]})', f['campo'], _brl(f['antes']), f'<b>{_brl(f["depois"])}</b>', _esc(r['motivo'])])
        t2 = _linhas_tabela(['Registro', 'Campo recalculado', 'Antes', 'Depois', 'Etapa'], linhas, ['l', 'l', 'r', 'r', 'l'])
        return t1 + '<div style="height:12px"></div><h3 style="margin-top:6px">M200/M600 recalculados (todas as etapas)</h3>' + t2
    if cid == 'msoma':
        inc = [x for x in a if x['tipo'] == 'incluido']
        return _linhas_tabela(['Tributo', 'M205/M605 (DARF)', 'Apuração do M210/M610 (recalculada)', 'Diferença', 'Ajuste incluído', 'Registro criado'],
                              [[x['trib'], _brl(x['m205']), _brl(x['m200']), _brl(x['m205'] - x['m200']),
                                f'{"Acréscimo" if x["ind"] == "1" else "Redução"} de <b>{_brl(x["valor"])}</b> (código 06)', f'<span class="sel">NOVO</span> {x["registro"]}'] for x in inc],
                              ['l', 'r', 'r', 'r', 'l', 'l'])
    if cid == 'natureza':
        grupos = Counter((x['cfop'], x['cod_antes'], x['cod_depois'], x['regra']) for x in a if x['tipo'] == 'alterado')
        t1 = _linhas_tabela(['CFOP', 'Itens', 'COD_NAT antes', 'COD_NAT depois', 'Regra usada'],
                            [[_esc(k[0]), str(q), _esc(k[1]), f'<b>{_esc(k[2])}</b>', _esc(k[3])] for k, q in sorted(grupos.items(), key=lambda z: -z[1])], ['l', 'r', 'l', 'l', 'l'])
        inc = [x for x in a if x['tipo'] == 'incluido']
        t_inc = ''
        if inc:
            t_inc = '<h3 style="margin-top:14px">Registros incluídos no 0400</h3>' + ''.join(_reg_html(x['depois'], 'novo') + f'<div class="txt">{_esc(x["motivo"])}</div>' for x in inc)
        t2 = _linhas_tabela(['Linha', 'Item', 'Descrição', 'CFOP', 'Antes', 'Depois'],
                            [[str(x['linha']), _esc(x['item']), _esc(x['descr'][:42]), _esc(x['cfop']), _esc(x['cod_antes']), f'<b>{_esc(x["cod_depois"])}</b>'] for x in a if x['tipo'] == 'alterado'],
                            ['l', 'l', 'l', 'l', 'l', 'l'])
        return t1 + t_inc + '<h3 style="margin-top:14px">Todos os itens alterados</h3>' + t2
    if cid == 'm105':
        rot = {'alterado': '<span class="st dif">Ajustado</span>', 'ja_correto': '<span class="st ok">Já correto no arquivo</span>'}
        return _linhas_tabela(['Registro', 'Natureza / CST', 'Esperado pelo PVA', 'Constava no relatório do PVA', 'No arquivo enviado', 'Situação'],
                              [[x['registro'], f'{x["nat"]} / {x["cst"]}', _brl(x['esperado']), _brl(x['conteudo_pva']), _brl(x['no_arquivo']), rot[x['tipo']]] for x in a],
                              ['l', 'l', 'r', 'r', 'r', 'c'])
    if cid == 'm410':
        p = [x for x in res['pendencias'] if x['cat'] == 'm410']
        return _linhas_tabela(['Registro', 'Linha', 'CST', 'Natureza', 'Valor', 'Onde o código existe', 'Orientação'],
                              [[x['reg'], str(x['linha']), _esc(x['cst']), _esc(x['nat']), _brl(x['valor']), _esc('; '.join(x['existe_em']) or '—'), _esc(x['detalhe'])] for x in p],
                              ['l', 'l', 'l', 'l', 'r', 'l', 'l'])
    if cid == 'contadores':
        return _linhas_tabela(['Contador', 'Antes', 'Depois'], [[_esc(x['registro']), '—' if x['antes'] is None else str(x['antes']), f'<b>{x["depois"]}</b>'] for x in a], ['l', 'r', 'r'])
    return ''


def gerar_relatorio_correcao_html(res):
    from efd_contribuicoes import _CSS, _linhas_tabela
    e = res['empresa']
    cats = res['categorias']
    erro_cats = [c for c in cats if not c['consequencia']]
    ach = sum(c['achados'] for c in erro_cats)
    cor = sum(c['corrigidos'] for c in erro_cats)
    pen = sum(c['pendentes'] for c in erro_cats)
    graf = [c for c in erro_cats if c['achados'] > 0]
    dados = [{'n': _CURTO.get(c['id'], c['titulo']), 'c': c['cor'], 'a': c['achados'], 'k': c['corrigidos']} for c in graf]
    js = _JS_CORR.replace('__DADOS__', repr(dados).replace("'", '"').replace('True', 'true').replace('False', 'false'))
    cab = (f'<div class="hdr"><b>FiscoCont+ · Correção da EFD-Contribuições</b><div>{_esc(e["nome"])} · CNPJ {_esc(e["cnpj"])} · Competência {_dt(e["ini"])} a {_dt(e["fim"])}'
           f' · arquivo {_esc(res["arquivo"])} · corrigido em {_esc(res["hoje"])}</div></div>')
    kpis = (f'<div class="kpis">'
            f'<div class="kpi"><b class="cnt" data-alvo="{ach}">0</b><span>Erros encontrados{" (PVA: " + str(res["pva"]["total"]) + ")" if res.get("pva") and res["pva"].get("total") else ""}</span></div>'
            f'<div class="kpi verde"><b class="cnt" data-alvo="{cor}" style="color:#0f6e56">0</b><span>Corrigidos pelo sistema</span></div>'
            f'<div class="kpi laranja"><b class="cnt" data-alvo="{pen}" style="color:#e8632b">0</b><span>Pendências (decisão sua)</span></div>'
            f'<div class="kpi destaque"><b class="cnt" data-alvo="{res["incluidas"]}">0</b><span>Registros incluídos no arquivo</span></div></div>')
    leg = ''.join(f'<div><i style="background:linear-gradient(135deg,{_mix(c["cor"], (255, 255, 255), .3)},{c["cor"]});box-shadow:0 2px 4px rgba(31,42,90,.3)"></i>{_esc(_CURTO.get(c["id"], c["titulo"]))}'
                  f'<br><b>{c["achados"]}</b> <span style="color:var(--ink2);font-size:11px">({round(100 * c["achados"] / ach) if ach else 0}%)</span></div>' for c in graf)
    pizza = (f'<div class="card chart"><h3>Erros por tipo</h3><div style="display:flex;align-items:center;justify-content:center;gap:20px 30px;flex-wrap:wrap;padding:6px 0 4px">'
             f'<div class="pizza-wrap"><svg id="corrPizza" width="220" height="220" viewBox="0 0 220 220" style="display:block;transition:transform 1.1s cubic-bezier(.2,.8,.2,1);transform-origin:110px 110px">'
             f'<defs><radialGradient id="corrGl" cx="34%" cy="24%" r="58%"><stop offset="0" stop-color="#fff" stop-opacity=".38"/><stop offset="100%" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>'
             f'<g id="corrSlices"></g><circle cx="110" cy="110" r="92" fill="url(#corrGl)" style="pointer-events:none"/></svg></div>'
             f'<div class="leg" style="min-width:210px;gap:9px">{leg}</div></div></div>')
    mx = max([c['achados'] for c in graf] + [1])
    cols = ''
    for c in graf:
        ha, hk = max(6, round(190 * c['achados'] / mx)), (max(6, round(190 * c['corrigidos'] / mx)) if c['corrigidos'] else 0)
        cols += (f'<div class="bar-grp"><div class="bar-par"><div style="display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%"><span class="val-bar" style="color:{c["cor"]}">{c["achados"]}</span>'
                 f'<div class="b2" data-alvo="{ha}" style="background:{_grad_barra(c["cor"])};box-shadow:0 10px 16px {c["cor"]}55,inset 0 3px 0 rgba(255,255,255,.3)"></div></div>'
                 f'<div style="display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%"><span class="val-bar" style="color:#0f6e56">{c["corrigidos"]}</span>'
                 f'<div class="b2" data-alvo="{hk}" style="background:{_grad_barra("#0f9d6e")};box-shadow:0 10px 16px #0f9d6e55,inset 0 3px 0 rgba(255,255,255,.3)"></div></div></div>'
                 f'<div class="rot-bar">{_esc(_CURTO.get(c["id"], c["titulo"]))}</div></div>')
    colunas = (f'<div class="card chart"><h3>Encontrados × corrigidos, por tipo <small>(cor do tipo = encontrados · verde = corrigidos)</small></h3>'
               f'<div style="overflow-x:auto"><div style="display:flex;align-items:flex-end;gap:18px;padding-top:6px;margin:0 auto;width:max-content">{cols}</div></div></div>')
    avisos = ''.join(f'<div class="aviso">{_esc(a)}</div>' for a in res['avisos'])
    resumo_arq = _linhas_tabela(['Linhas antes', 'Linhas depois', 'Linhas removidas', 'Linhas alteradas', 'Registros incluídos'],
                                [[str(res['linhas_antes']), str(res['linhas_depois']), str(res['removidas']), str(res['alteradas']), str(res['incluidas'])]], ['r', 'r', 'r', 'r', 'r'])
    # ajustes incluídos (destaque: o usuário pediu que seja informado)
    aj = ''
    for x in res['ajustes']:
        aj += (f'<div class="card destaque-aj"><h3>Ajuste incluído no {x["registro"]} ({x["tributo"]}) — <span class="sel">INCLUÍDO PELO SISTEMA</span></h3>'
               f'<div class="txt">O {"M205" if x["tributo"] == "PIS" else "M605"} (DARF) soma <b>R$ {_brl(x["m205"])}</b> e a apuração do {x["pai"]} resultava em <b>R$ {_brl(x["m200"])}</b>. '
               f'Foi incluído um ajuste de {"acréscimo" if x["ind"] == "1" else "redução"} de <b>R$ {_brl(x["valor"])}</b>, e o {x["pai"]} e o {"M200" if x["tributo"] == "PIS" else "M600"} foram atualizados para fechar com o DARF.</div>'
               f'<div class="kv"><span>Registro</span><span><b>{x["registro"]}</b> (filho do {x["pai"]} da linha {x["pai_linha"]})</span>'
               f'<span>Tipo de ajuste</span><span>{x["ind"]} — {"Ajuste de acréscimo" if x["ind"] == "1" else "Ajuste de redução"}</span>'
               f'<span>Valor do ajuste</span><span>R$ {_brl(x["valor"])}</span><span>Código do ajuste</span><span>06 — Estorno</span>'
               f'<span>Descrição</span><span>{_esc(x["descr"])}</span><span>Data de referência</span><span>{_esc(x["dt"][:2] + "/" + x["dt"][2:4] + "/" + x["dt"][4:])}</span></div>'
               f'<div class="txt"><b class="rot">Linha incluída no arquivo:</b></div>{_reg_html(x["texto"], "novo")}'
               f'<div class="txt"><b class="rot">{x["pai"]} depois do ajuste (antes → depois):</b></div>{_reg_html(x["pai_antes"], "velho")}{_reg_html(x["pai_depois"], "novo")}'
               f'<div class="txt" style="color:var(--ink2);font-size:11.5px">Usei o {x["registro"]} (ajuste da contribuição apurada) e não o M110, porque o M110 é ajuste de crédito e só existe como filho do M100; '
               f'esta empresa não tem M100, e um ajuste de crédito não altera o campo {"12" if x["campo"].endswith("CUM_REC") else "08"} do {"M200" if x["tributo"] == "PIS" else "M600"}.</div></div>')
    # seções por tipo de erro
    secoes = ''
    for c in cats:
        o_que, fez = _EXPLICA[c['id']]
        pils = (f'<span class="pil ach">{c["achados"]} encontrado(s)</span>' if not c['consequencia'] else '') + \
               f'<span class="pil cor">{c["corrigidos"]} {"alteração(ões)" if c["consequencia"] else "corrigido(s)"}</span>' + \
               (f'<span class="pil pen">{c["pendentes"]} pendente(s)</span>' if c['pendentes'] else '')
        secoes += (f'<h2 class="secao"><span class="dot" style="background:{c["cor"]}"></span>{_esc(c["titulo"])}</h2>'
                   f'<div class="card" style="border-top:4px solid {c["cor"]}"><div class="cab-cat">{pils}</div>'
                   f'<div class="txt"><b class="rot">O que era:</b> {_esc(o_que)}</div><div class="txt"><b class="rot">O que o sistema fez:</b> {_esc(fez)}</div>'
                   f'<div style="height:8px"></div>{_tab_cat(c, res)}</div>')
    pend_html = ''
    if res['pendencias']:
        pend_html = ('<h2 class="secao"><span class="dot" style="background:#e8632b"></span>Pendências — precisam da sua decisão</h2><div class="card" style="border-top:4px solid #e8632b">' +
                     ''.join(f'<div class="nota"><b>{_esc(x["titulo"])}</b> (linha {x["linha"]})<br>{_esc(x["detalhe"])}</div>' for x in res['pendencias']) + '</div>')
    aten = ''
    if res['atencao']:
        at = res['atencao']
        exc_p, exc_c = sum(x['pis'] - x['esp_p'] for x in at), sum(x['cof'] - x['esp_c'] for x in at)
        aten = ('<h2 class="secao"><span class="dot" style="background:#f5a524"></span>Sinal de atenção (não alterado)</h2><div class="card" style="border-top:4px solid #f5a524">'
                f'<div class="txt"><b>{len(at)} linha(s) de NFC-e (C175, CST 01)</b> têm PIS ou COFINS lançado diferente de base × alíquota declarada. '
                f'Diferença somada: PIS <b>R$ {_brl(exc_p)}</b> · COFINS <b>R$ {_brl(exc_c)}</b>. Em alguns casos o valor lançado corresponde às alíquotas do regime não cumulativo (1,65% / 7,6%) '
                f'com a alíquota informada do regime cumulativo (0,65% / 3%). O sistema não mexe nisso: pode ser cadastro de produto no Domínio com a tributação errada, e a decisão é sua.</div>' +
                _linhas_tabela(['Linha', 'Base', 'Alíq. PIS', 'PIS lançado', 'PIS por base × alíq.', 'Alíq. COFINS', 'COFINS lançada', 'COFINS por base × alíq.'],
                               [[str(x['n']), _brl(x['bc']), _brl(x['aq']) + '%', _brl(x['pis']), _brl(x['esp_p']), _brl(x['aqc']) + '%', _brl(x['cof']), _brl(x['esp_c'])] for x in at[:25]],
                               ['l', 'r', 'r', 'r', 'r', 'r', 'r', 'r']) +
                (f'<div class="txt" style="color:var(--ink2)">Mostrando as 25 primeiras de {len(at)}.</div>' if len(at) > 25 else '') + '</div>')
    verif = _linhas_tabela(['Regra do PVA verificada no arquivo corrigido', 'Antes', 'Depois', 'Resultado'],
                           [[_esc(v[0]), str(v[1]), str(v[2]), '<span class="ok">✓ ok</span>' if v[2] == 0 else '<span class="bad">pendente</span>'] for v in res['verificacao']], ['l', 'r', 'r', 'c'])
    prox = ('<div class="card"><h3>Próximos passos</h3><div class="txt">1) Importe o arquivo corrigido no PVA e valide de novo — o PVA é quem dá a palavra final. '
            '2) Resolva as pendências acima. 3) Se o PVA apontar algo novo, envie o novo relatório de erros para o sistema conferir.</div></div>')
    corpo = (cab + kpis + f'<div class="grid2"{" style=\"grid-template-columns:1fr\"" if len(graf) > 4 else ""}>{pizza}{colunas}</div>' + avisos +
             f'<div class="card"><h3>Resumo do arquivo</h3>{resumo_arq}</div>' + aj + secoes + pend_html + aten +
             f'<h2 class="secao"><span class="dot" style="background:#0f6e56"></span>Verificação depois da correção</h2><div class="card">{verif}</div>' + prox)
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Correção EFD-Contribuições · {_esc(e["nome"])}</title>'
            f'<style>{_CSS}{_CSS_CORR}</style></head><body>{corpo}<script>{js}</script></body></html>')


def resumo_leve(res):
    return {'empresa': res['empresa'], 'arquivo': res['arquivo'], 'linhas_antes': res['linhas_antes'], 'linhas_depois': res['linhas_depois'],
            'removidas': res['removidas'], 'alteradas': res['alteradas'], 'incluidas': res['incluidas'],
            'categorias': [{'id': c['id'], 'titulo': c['titulo'], 'achados': c['achados'], 'corrigidos': c['corrigidos'], 'pendentes': c['pendentes']} for c in res['categorias']],
            'ajustes': [{'tributo': a['tributo'], 'registro': a['registro'], 'valor': a['valor'], 'ind': a['ind']} for a in res['ajustes']],
            'pendencias': len(res['pendencias']), 'avisos': res['avisos']}


def corrigir_arquivo(sped_path, pva_path=None, saida_path=None, html_path=None, json_path=None):
    import datetime
    import json
    import os
    with open(sped_path, 'r', encoding='latin-1', newline='') as fh:
        texto = fh.read()
    pva, aviso_pva = None, None
    if pva_path:
        try:
            pva = ler_erros_pva(pva_path)
        except Exception as ex:
            aviso_pva = f'Não consegui ler o relatório do PVA ({ex}); a correção seguiu só com o SPED.'
    novo, res = corrigir_efd(texto, pva, os.path.basename(sped_path), datetime.date.today().strftime('%d/%m/%Y'))
    if aviso_pva:
        res['avisos'].append(aviso_pva)
    if saida_path:
        with open(saida_path, 'w', encoding='latin-1', newline='') as fh:
            fh.write(novo)
    if html_path:
        with open(html_path, 'w', encoding='utf-8') as fh:
            fh.write(gerar_relatorio_correcao_html(res))
    if json_path:
        with open(json_path, 'w', encoding='utf-8') as fh:
            json.dump(resumo_leve(res), fh, ensure_ascii=False)
    return novo, res

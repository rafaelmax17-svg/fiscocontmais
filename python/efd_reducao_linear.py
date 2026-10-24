# -*- coding: utf-8 -*-
"""
Conferência da redução linear de benefícios de PIS/COFINS (LC 224/2025) na EFD-Contribuições.
Conferência INTERNA do escritório: entra no painel de conferência, nunca no relatório do cliente.

Como a redução é escriturada (Nota Técnica EFD-Contribuições nº 12/2026):
  • a receita com alíquota zero (CST 06) continua com CST 06 nos documentos;
  • o acréscimo de 10% do benefício vai no M220 (PIS) e M620 (COFINS), código de ajuste 11, IND_AJ = 1,
    detalhado por documento no M225/M625 (chave de acesso, base, alíquota, data e conta contábil);
  • alíquotas do ajuste = 10% das alíquotas básicas: não cumulativo PIS 0,165% e COFINS 0,76%;
    cumulativo PIS 0,065% e COFINS 0,30%;
  • vale para PIS/COFINS a partir de 01/04/2026; o monofásico (CST 04) não entra.
"""
import re
from collections import defaultdict

INICIO = '2026-04'
ALIQ = {'nc': (0.165, 0.76), 'cum': (0.065, 0.30)}


def _n(s):
    s = (s or '').strip()
    if not s:
        return 0.0
    try:
        return float(s.replace('.', '').replace(',', '.')) if ',' in s else float(s)
    except ValueError:
        return 0.0


def _brl(v):
    return f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _esc(s):
    return str(s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _pct(v):
    return f'{v:.3f}'.rstrip('0').rstrip('.').replace('.', ',') + '%'


def _comp(dt):          # 'DDMMAAAA' -> 'AAAA-MM'
    return f'{dt[4:8]}-{dt[2:4]}' if re.fullmatch(r'\d{8}', dt or '') else ''


def conferir(caminho):
    with open(caminho, 'r', encoding='latin-1', newline='') as fh:
        linhas = fh.read().splitlines()
    cab = {}
    regime = ''
    contas = {}
    docs = {}                 # chave -> {num, mod, data, valor, desc, icms, c110}
    atual = None
    m400_06 = m400_04 = 0.0
    aj = {'PIS': [], 'COFINS': []}
    det = {'PIS': [], 'COFINS': []}
    for ln in linhas:
        c = ln.split('|')
        if len(c) < 3:
            continue
        r = c[1]
        if r == '0000':
            cab = {'nome': c[8] if len(c) > 8 else '', 'cnpj': c[9] if len(c) > 9 else '', 'ini': c[6], 'fim': c[7]}
        elif r == '0110':
            regime = c[2]
        elif r == '0500' and len(c) > 7:
            contas[c[6].strip()] = {'nome': c[7].strip(), 'analitica': c[4].strip().upper() == 'A'}
        elif r == 'C100':
            atual = None
            if c[2] == '1' and len(c) > 9 and c[9].strip():
                atual = docs.setdefault(c[9].strip(), {'num': c[8], 'mod': c[5], 'data': c[11] or c[10], 'valor': 0.0,
                                                       'desc': 0.0, 'icms': 0.0, 'c110': False, 'tem06': False})
        elif r == 'C110' and atual is not None:
            if re.search(r'224\s*/\s*2025', ln):
                atual['c110'] = True
        elif r == 'C170' and atual is not None and len(c) > 31:
            if c[25] == '06' or c[31] == '06':
                atual['tem06'] = True
                atual['valor'] += _n(c[7]) - _n(c[8])
                atual['desc'] += _n(c[8])
                atual['icms'] += _n(c[15])
        elif r == 'C175' and atual is not None and len(c) > 11:
            if c[5] == '06' or c[11] == '06':
                atual['tem06'] = True
                atual['valor'] += _n(c[3]) - _n(c[4])
                atual['desc'] += _n(c[4])
        elif r[0] != 'C':
            atual = None
            if r == 'M400':
                if c[2] == '06':
                    m400_06 += _n(c[3])
                elif c[2] == '04':
                    m400_04 += _n(c[3])
            elif r in ('M220', 'M620'):
                aj['PIS' if r == 'M220' else 'COFINS'].append({'ind': c[2], 'valor': _n(c[3]), 'cod': c[4], 'descr': c[6] if len(c) > 6 else ''})
            elif r in ('M225', 'M625'):
                trib = 'PIS' if r == 'M225' else 'COFINS'
                if aj[trib] and aj[trib][-1]['cod'] == '11':
                    det[trib].append({'valor': _n(c[2]), 'cst': c[3], 'base': _n(c[4]), 'aliq': _n(c[5]), 'data': c[6],
                                      'desc': c[7] if len(c) > 7 else '', 'cta': (c[8] if len(c) > 8 else '').strip()})
    comp = _comp(cab.get('ini', ''))
    res = {'empresa': cab, 'competencia': comp, 'aplica': bool(comp) and comp >= INICIO, 'conferencias': [], 'docs': [],
           'regime': regime, 'm400_06': round(m400_06, 2), 'm400_04': round(m400_04, 2)}
    if not res['aplica']:
        return res
    docs06 = {k: d for k, d in docs.items() if d['tem06']}
    aj11 = {t: [a for a in aj[t] if a['cod'] == '11'] for t in aj}
    if regime == '2':
        esperadas = {'PIS': {ALIQ['cum'][0]}, 'COFINS': {ALIQ['cum'][1]}}
        rot_reg = 'Cumulativo (Lucro Presumido)'
    elif regime == '3':
        esperadas = {'PIS': {ALIQ['nc'][0], ALIQ['cum'][0]}, 'COFINS': {ALIQ['nc'][1], ALIQ['cum'][1]}}
        rot_reg = 'Não cumulativo e cumulativo'
    else:
        esperadas = {'PIS': {ALIQ['nc'][0]}, 'COFINS': {ALIQ['nc'][1]}}
        rot_reg = 'Não cumulativo (Lucro Real)'
    C = res['conferencias']

    def add(st, titulo, detalhe):
        C.append({'st': st, 'titulo': titulo, 'detalhe': detalhe})

    receita06 = round(sum(d['valor'] for d in docs06.values()), 2)
    if not docs06 and not m400_06 and not aj11['PIS'] and not aj11['COFINS']:
        add('info', 'Sem receita com alíquota zero (CST 06)', 'Não há o que ajustar pela redução linear neste período.')
        return res
    add('ok', 'Período alcançado', f'Competência {comp[5:]}/{comp[:4]}: a redução vale para PIS/COFINS desde 01/04/2026 (LC 224/2025).')
    # ajuste no lugar certo
    for t, reg in (('PIS', 'M220'), ('COFINS', 'M620')):
        if not aj11[t]:
            add('erro', f'Ajuste {reg} código 11 ({t})', f'Há receita com CST 06, mas nenhum {reg} com código 11 (acréscimo da LC 224/2025).')
        elif any(a['ind'] != '1' for a in aj11[t]):
            add('erro', f'Ajuste {reg} código 11 ({t})', 'O ajuste da redução linear é acréscimo: IND_AJ deve ser 1.')
    if aj11['PIS'] and aj11['COFINS'] and all(a['ind'] == '1' for a in aj11['PIS'] + aj11['COFINS']):
        add('ok', 'Ajuste no lugar certo', 'M220 e M620 com código 11, como acréscimo (IND_AJ 1).')
    # alíquotas
    al_err = {t: sorted({d['aliq'] for d in det[t] if round(d['aliq'], 3) not in {round(x, 3) for x in esperadas[t]}}) for t in det}
    if any(al_err.values()):
        add('erro', 'Alíquota do ajuste', ' · '.join(f'{t}: informado {", ".join(_pct(a) for a in v)}' for t, v in al_err.items() if v)
            + f' — o esperado é 10% da alíquota básica ({rot_reg}).')
    elif det['PIS'] or det['COFINS']:
        e = ', '.join(_pct(x) for x in sorted(esperadas['PIS'])) + ' (PIS) e ' + ', '.join(_pct(x) for x in sorted(esperadas['COFINS'])) + ' (COFINS)'
        add('ok', 'Regime e alíquotas', f'{rot_reg} · {e} = 10% das alíquotas básicas.')
    # CST nos detalhamentos
    cst_fora = sorted({d['cst'] for t in det for d in det[t] if d['cst'] != '06'})
    if cst_fora:
        add('erro', 'CST no detalhamento', f'M225/M625 com CST {", ".join(cst_fora)}: a redução linear se aplica à alíquota zero (CST 06); o monofásico (CST 04) não entra.')
    # cada documento detalhado
    por_ch = {t: defaultdict(list) for t in det}
    for t in det:
        for d in det[t]:
            ch = re.findall(r'\d{44}', d['desc'])
            por_ch[t][ch[0] if ch else ''].append(d)
    faltam = [k for k in docs06 if not por_ch['PIS'].get(k) or not por_ch['COFINS'].get(k)]
    if docs06:
        if faltam:
            add('erro', 'Notas com CST 06 sem detalhamento', f'{len(faltam)} de {len(docs06)} notas sem M225/M625 com a chave de acesso.')
        else:
            add('ok', 'Toda nota com CST 06 detalhada', f'{len(docs06)} de {len(docs06)} documentos com M225 e M625 (chave de acesso).')
    sobra = [k for k in por_ch['PIS'] if k and k not in docs06]
    if sobra:
        add('dif', 'Detalhamento de nota sem CST 06', f'{len(sobra)} M225 apontam para notas que não têm item com CST 06 no arquivo.')
    # base e valor por documento
    base_ok = base_div = val_div = val_cent = 0
    notas_cent = []
    regra = defaultdict(int)
    for k, d in sorted(docs06.items(), key=lambda x: (x[1]['data'][4:] + x[1]['data'][2:4] + x[1]['data'][:2], x[1]['num'])):
        lp, lc = por_ch['PIS'].get(k, []), por_ch['COFINS'].get(k, [])
        bp = round(sum(x['base'] for x in lp), 2)
        vp = round(sum(x['valor'] for x in lp), 2)
        vc = round(sum(x['valor'] for x in lc), 2)
        cand = {'valor − ICMS': round(d['valor'] - d['icms'], 2), 'valor da operação': round(d['valor'], 2)}
        r_ok = next((nm for nm, v in cand.items() if abs(v - bp) <= 0.02), '')
        if lp:
            if r_ok:
                base_ok += 1; regra[r_ok] += 1
            else:
                base_div += 1
        exp_p = round(sum(round(x['base'] * x['aliq'] / 100, 2) for x in lp), 2)
        exp_c = round(sum(round(x['base'] * x['aliq'] / 100, 2) for x in lc), 2)
        dmax = max(abs(exp_p - vp), abs(exp_c - vc))
        if lp and dmax > 0.011:
            val_div += 1
        elif lp and dmax > 0.004:
            val_cent += 1; notas_cent.append(d['num'])
        st = 'falta' if not lp or not lc else ('ok' if r_ok and dmax <= 0.004 else 'dif')
        res['docs'].append({'num': d['num'], 'mod': d['mod'], 'data': d['data'], 'valor': round(d['valor'], 2), 'icms': round(d['icms'], 2),
                            'base': bp, 'pis': vp, 'cofins': vc, 'st': st, 'regra': r_ok, 'c110': d['c110']})
    if base_ok and not base_div:
        add('ok', 'Base de cada nota', ' · '.join(f'{nm} em {q} de {base_ok}' for nm, q in regra.items()) + ' notas.')
    elif base_div:
        add('dif', 'Base de cada nota', f'{base_div} nota(s) com base no M225 diferente do valor da operação (com ou sem o ICMS).')
    # totais do ajuste
    for t, reg in (('PIS', 'M220'), ('COFINS', 'M620')):
        tot_det = round(sum(x['valor'] for x in det[t]), 2)
        tot_aj = round(sum(a['valor'] for a in aj11[t]), 2)
        if aj11[t] and abs(tot_det - tot_aj) > 0.01:
            add('erro', f'{reg} × detalhamento ({t})', f'{reg} código 11 = R$ {_brl(tot_aj)}, mas a soma do detalhamento é R$ {_brl(tot_det)}.')
    vp = round(sum(a['valor'] for a in aj11['PIS']), 2)
    vc = round(sum(a['valor'] for a in aj11['COFINS']), 2)
    bp = round(sum(x['base'] for x in det['PIS']), 2)
    if val_div:
        add('erro', 'Valor do ajuste', f'{val_div} nota(s) com valor do M225/M625 diferente de base × alíquota.')
    elif val_cent:
        add('dif', 'Valor do ajuste', f'PIS R$ {_brl(vp)} · COFINS R$ {_brl(vc)} · {val_cent} nota(s) com 1 centavo de diferença em base × alíquota (nº {", ".join(notas_cent[:5])}).')
    elif aj11['PIS'] or aj11['COFINS']:
        ep = round(sum(x['base'] * x['aliq'] / 100 for x in det['PIS']), 2)
        ec = round(sum(x['base'] * x['aliq'] / 100 for x in det['COFINS']), 2)
        add('ok', 'Valor do ajuste', f'PIS R$ {_brl(vp)} · COFINS R$ {_brl(vc)}' + (f' (sobre o total daria R$ {_brl(ep)} e R$ {_brl(ec)}: diferença de arredondamento por nota).' if abs(ep - vp) > 0.004 or abs(ec - vc) > 0.004 else '.'))
    # conta contábil
    todos = det['PIS'] + det['COFINS']
    sem = [x for x in todos if not x['cta']]
    fora = [x for x in todos if x['cta'] and not contas.get(x['cta'], {}).get('analitica')]
    if sem or fora:
        add('erro', 'Conta contábil no M225/M625', (f'{len(sem)} sem conta' if sem else '') + (' · ' if sem and fora else '')
            + (f'{len(fora)} com conta que não é analítica no 0500' if fora else '') + ' — o PVA não valida; a Correção da EFD-Contribuições preenche a conta.')
    elif todos:
        ctas = sorted({x['cta'] for x in todos})
        add('ok', 'Conta contábil no M225/M625', ', '.join(f'{k} – {contas[k]["nome"]}' for k in ctas) + f' em {len(todos)} de {len(todos)}.')
    if m400_04:
        add('info', 'Monofásico fora da redução', f'CST 04 (R$ {_brl(m400_04)}) sem ajuste, como deve ser.')
    # M400 × documentos
    desc = round(sum(d['desc'] for d in docs06.values()), 2)
    if m400_06 and abs(m400_06 - receita06) > 0.01:
        expl = ' = descontos dos itens' if abs(m400_06 - receita06 - desc) <= 0.02 else ''
        add('dif', 'Receita CST 06 × documentos', f'M400: R$ {_brl(m400_06)} · documentos: R$ {_brl(receita06)} · diferença R$ {_brl(m400_06 - receita06)}{expl}.')
    # C110 (informação complementar na nota)
    if docs06:
        com = sum(1 for d in docs06.values() if d['c110'])
        if com < len(docs06):
            add('dif', 'Informação na nota (C110)', f'{len(docs06) - com} de {len(docs06)} notas sem C110 citando a LC 224/2025 — a NT 12/2026 orienta replicar no C110 o texto do infAdFisco.')
        else:
            add('ok', 'Informação na nota (C110)', 'Todas as notas com CST 06 citam a LC 224/2025 no C110.')
    add('info', 'Exceções da lei', 'Exceções previstas na LC 224/2025 (ex.: cesta básica, Zona Franca, Simples Nacional) não são conferidas automaticamente: confira se alguma receita CST 06 está nelas.')
    res.update({'receita06_docs': receita06, 'base': bp, 'pis': vp, 'cofins': vc, 'n_docs': len(docs06), 'regime_rot': rot_reg})
    return res


_ST = {'ok': ('ok', '✓ correto'), 'erro': ('err', 'erro'), 'dif': ('dif', 'atenção'), 'info': ('so', 'informativo')}


def html_reducao(res):
    if not res.get('aplica'):
        return ''
    from efd_contribuicoes import _linhas_tabela
    C = res['conferencias']
    n_ok = sum(1 for x in C if x['st'] == 'ok')
    n_err = sum(1 for x in C if x['st'] == 'erro')
    n_dif = sum(1 for x in C if x['st'] == 'dif')
    css = ('<style>.st.err{background:#fdecec;color:#a32020}.rl-aviso{background:#fdf1dc;border:1px solid #efc98f;border-radius:12px;'
           'padding:10px 14px;font-size:12px;color:#633806;margin:10px 20px}</style>')
    linhas = [[f'<span class="st {_ST[x["st"]][0]}">{_ST[x["st"]][1]}</span>', f'<b>{_esc(x["titulo"])}</b>', _esc(x['detalhe'])] for x in C]
    t1 = _linhas_tabela(['Situação', 'Conferência', 'Detalhe'], linhas, ['c', 'l', 'l'])
    if len(C) == 1 and C[0]['st'] == 'info':
        return css + f'<div class="card"><h3>Redução linear de benefícios · LC 224/2025 <span style="font-size:11px;color:#854f0b">(conferência interna)</span></h3>{t1}</div>'
    mod = {'55': 'NF-e', '65': 'NFC-e'}
    dd = lambda d: f'{d[:2]}/{d[2:4]}' if len(d) == 8 else d
    stm = {'ok': '<span class="st ok">✓</span>', 'dif': '<span class="st dif">diverge</span>', 'falta': '<span class="st err">sem M225/M625</span>'}
    t2 = _linhas_tabela(['Documento', 'Data', 'Valor CST 06', 'ICMS', 'Base (M225)', 'PIS', 'COFINS', 'Situação'],
                        [[f'{mod.get(d["mod"], d["mod"])} {_esc(d["num"])}', dd(d['data']), _brl(d['valor']), _brl(d['icms']), f'<b>{_brl(d["base"])}</b>',
                          _brl(d['pis']), _brl(d['cofins']), stm[d['st']]] for d in res['docs']],
                        ['l', 'l', 'r', 'r', 'r', 'r', 'r', 'c'])
    kp = (f'<div class="kpis"><div class="kpi"><b>R$ {_brl(res.get("m400_06") or res.get("receita06_docs", 0))}</b><span>Receita com CST 06 (alíquota zero)</span></div>'
          f'<div class="kpi"><b>R$ {_brl(res.get("base", 0))}</b><span>Base do ajuste (M225/M625) · {res.get("n_docs", 0)} notas</span></div>'
          f'<div class="kpi laranja"><b style="color:#e8632b">R$ {_brl(res.get("pis", 0) + res.get("cofins", 0))}</b><span>Ajuste PIS + COFINS (código 11)</span></div>'
          f'<div class="kpi {"verde" if not n_err else "laranja"}"><b style="color:{"#0f6e56" if not n_err else "#a32020"}">{n_ok} corretas</b>'
          f'<span>{n_dif} atenção · {n_err} erro(s)</span></div></div>')
    return (css + '<div class="rl-aviso">🔒 <b>Conferência interna — redução linear (LC 224/2025).</b> Esta parte não vai para o relatório do cliente.</div>'
            + kp + f'<div class="card"><h3>Redução linear de benefícios · conferências</h3>{t1}'
            '<div style="font-size:11px;color:var(--ink2);margin-top:8px">Base legal: LC 224/2025 · Nota Técnica EFD-Contribuições nº 12/2026 · IN RFB nº 2.305/2025, art. 7º.</div></div>'
            + f'<div class="card"><h3>Redução linear · nota a nota ({res.get("n_docs", 0)} documentos com CST 06)</h3>{t2}</div>')

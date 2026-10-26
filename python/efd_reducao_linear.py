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

from efd_lc224_excecoes import classifica_ncm, ZFM_ALC

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
    prod = {}                 # COD_ITEM -> {descr, ncm}
    part = {}                 # COD_PART -> {nome, mun}
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
        elif r == '0200' and len(c) > 8:
            prod[c[2]] = {'descr': c[3], 'ncm': c[8]}
        elif r == '0150' and len(c) > 8:
            part[c[2]] = {'nome': c[3], 'mun': c[8].strip()}
        elif r == '0500' and len(c) > 7:
            contas[c[6].strip()] = {'nome': c[7].strip(), 'analitica': c[4].strip().upper() == 'A'}
        elif r == 'C100':
            atual = None
            if c[2] == '1' and len(c) > 9 and c[9].strip():
                atual = docs.setdefault(c[9].strip(), {'num': c[8], 'mod': c[5], 'data': c[11] or c[10], 'valor': 0.0,
                                                       'desc': 0.0, 'icms': 0.0, 'c110': False, 'tem06': False,
                                                       'part': c[4], 'itens': []})
        elif r == 'C110' and atual is not None:
            if re.search(r'224\s*/\s*2025', ln):
                atual['c110'] = True
        elif r == 'C170' and atual is not None and len(c) > 31:
            if c[25] == '06' or c[31] == '06':
                atual['tem06'] = True
                atual['valor'] += _n(c[7]) - _n(c[8])
                atual['desc'] += _n(c[8])
                atual['icms'] += _n(c[15])
                atual['itens'].append({'cod': c[3], 'valor': _n(c[7]) - _n(c[8]), 'icms': _n(c[15])})
        elif r == 'C175' and atual is not None and len(c) > 11:
            if c[5] == '06' or c[11] == '06':
                atual['tem06'] = True
                atual['valor'] += _n(c[3]) - _n(c[4])
                atual['desc'] += _n(c[4])
                atual['itens'].append({'cod': '', 'valor': _n(c[3]) - _n(c[4]), 'icms': 0.0, 'consolidado': True})
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
    # quais itens com alíquota zero entram de fato na redução (exceções do art. 4º, § 8º, da LC 224/2025)
    produtos = {}
    for d in docs06.values():
        mun = part.get(d['part'], {}).get('mun', '')
        zfm = ZFM_ALC.get(mun)
        d['v_in'] = d['i_in'] = d['v_fora'] = d['v_conf'] = 0.0
        for it in d['itens']:
            if it.get('consolidado'):
                st, mot = 'entra', ''
                chave_p = '(NFC-e consolidada · C175)'
                info = {'descr': 'Vendas de NFC-e consolidadas no C175 (sem o produto no arquivo)', 'ncm': ''}
            else:
                info = prod.get(it['cod'], {'descr': it['cod'], 'ncm': ''})
                st, mot = classifica_ncm(info['ncm'])
                chave_p = it['cod']
            if zfm and st != 'fora':
                st, mot = 'fora', f'venda para {zfm} — benefício da ZFM/ALC (art. 4º, § 8º, II)'
            p = produtos.setdefault((chave_p, st, mot), {'cod': chave_p, 'descr': info['descr'], 'ncm': info['ncm'], 'st': st,
                                                          'motivo': mot, 'valor': 0.0, 'notas': set(), 'consolidado': bool(it.get('consolidado'))})
            p['valor'] += it['valor']; p['notas'].add(d['num'])
            if st == 'fora':
                d['v_fora'] += it['valor']
            else:
                d['v_in'] += it['valor']; d['i_in'] += it['icms']
                if st == 'confirmar':
                    d['v_conf'] += it['valor']
    res['produtos'] = sorted(({**p, 'valor': round(p['valor'], 2), 'notas': len(p['notas'])} for p in produtos.values()),
                             key=lambda x: ({'fora': 0, 'confirmar': 1, 'entra': 2}[x['st']], -x['valor']))
    res['v_entra'] = round(sum(d['v_in'] - d['v_conf'] for d in docs06.values()), 2)
    res['v_fora'] = round(sum(d['v_fora'] for d in docs06.values()), 2)
    res['v_conf'] = round(sum(d['v_conf'] for d in docs06.values()), 2)
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
    so_fora = {k for k, d in docs06.items() if d['v_in'] <= 0.004}          # nota só com produtos fora da redução
    devem = {k for k in docs06 if k not in so_fora}
    faltam = [k for k in devem if not por_ch['PIS'].get(k) or not por_ch['COFINS'].get(k)]
    indevidas = [k for k in so_fora if por_ch['PIS'].get(k) or por_ch['COFINS'].get(k)]
    if devem:
        if faltam:
            add('erro', 'Notas que entram na redução sem detalhamento', f'{len(faltam)} de {len(devem)} notas com produto alcançado pela redução sem M225/M625.')
        else:
            add('ok', 'Toda nota alcançada está detalhada', f'{len(devem)} de {len(devem)} documentos com M225 e M625 (chave de acesso).')
    if indevidas:
        add('erro', 'Ajuste em nota que não entra na redução', f'{len(indevidas)} nota(s) com M225/M625, mas todos os produtos estão nas exceções da lei (art. 4º, § 8º).')
    sobra = [k for k in por_ch['PIS'] if k and k not in docs06]
    if sobra:
        add('dif', 'Detalhamento de nota sem CST 06', f'{len(sobra)} M225 apontam para notas que não têm item com CST 06 no arquivo.')
    # base e valor por documento (só os produtos que entram na redução)
    base_ok = base_div = base_com_fora = val_div = val_cent = 0
    notas_cent = []
    regra = defaultdict(int)
    for k, d in sorted(docs06.items(), key=lambda x: (x[1]['data'][4:] + x[1]['data'][2:4] + x[1]['data'][:2], x[1]['num'])):
        lp, lc = por_ch['PIS'].get(k, []), por_ch['COFINS'].get(k, [])
        bp = round(sum(x['base'] for x in lp), 2)
        vp = round(sum(x['valor'] for x in lp), 2)
        vc = round(sum(x['valor'] for x in lc), 2)
        cand = {'valor − ICMS': round(d['v_in'] - d['i_in'], 2), 'valor da operação': round(d['v_in'], 2)}
        r_ok = next((nm for nm, v in cand.items() if abs(v - bp) <= 0.02), '')
        com_fora = bool(d['v_fora'] > 0.004 and lp and not r_ok and
                        any(abs(v - bp) <= 0.02 for v in (round(d['valor'] - d['icms'], 2), round(d['valor'], 2))))
        if lp and k in devem:
            if r_ok:
                base_ok += 1; regra[r_ok] += 1
            elif com_fora:
                base_com_fora += 1
            else:
                base_div += 1
        exp_p = round(sum(round(x['base'] * x['aliq'] / 100, 2) for x in lp), 2)
        exp_c = round(sum(round(x['base'] * x['aliq'] / 100, 2) for x in lc), 2)
        dmax = max(abs(exp_p - vp), abs(exp_c - vc))
        if lp and dmax > 0.011:
            val_div += 1
        elif lp and dmax > 0.004:
            val_cent += 1; notas_cent.append(d['num'])
        if k in so_fora:
            st = 'indevido' if lp or lc else 'fora'
        elif not lp or not lc:
            st = 'falta'
        elif com_fora:
            st = 'com_fora'
        else:
            st = 'ok' if r_ok and dmax <= 0.004 else 'dif'
        res['docs'].append({'num': d['num'], 'mod': d['mod'], 'data': d['data'], 'valor': round(d['valor'], 2), 'icms': round(d['icms'], 2),
                            'v_fora': round(d['v_fora'], 2), 'base': bp, 'pis': vp, 'cofins': vc, 'st': st, 'regra': r_ok, 'c110': d['c110']})
    if base_com_fora:
        add('erro', 'Produto fora da redução incluído na base', f'{base_com_fora} nota(s) com a base do M225 somando também produtos que estão nas exceções da lei.')
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
    n_in = sum(1 for p in res['produtos'] if p['st'] == 'entra')
    n_fora = sum(1 for p in res['produtos'] if p['st'] == 'fora')
    n_conf = sum(1 for p in res['produtos'] if p['st'] == 'confirmar')
    add('ok' if not n_conf else 'dif', 'Produtos que entram na redução',
        f'{n_in} produto(s) entram (R$ {_brl(res["v_entra"])}) · {n_fora} fora pelas exceções da lei (R$ {_brl(res["v_fora"])})'
        + (f' · {n_conf} para confirmar (R$ {_brl(res["v_conf"])})' if n_conf else '')
        + '. Exceções conferidas pelo NCM e pelo destino: Cesta Básica Nacional (LC 214/2025, Anexo I), hortícolas, frutas e ovos (Anexo XV) e vendas para ZFM/ALC.')
    # base e ajuste que deveriam existir, só com os produtos que entram (regra da base usada no próprio arquivo)
    usa_icms = regra.get('valor − ICMS', 0) >= regra.get('valor da operação', 0)
    base_esp = round(sum((d['v_in'] - (d['i_in'] if usa_icms else 0)) for d in docs06.values()), 2)
    if (det['PIS'] or base_esp) and abs(base_esp - bp) > 0.05:
        r_pis = min(esperadas['PIS']); r_cof = min(esperadas['COFINS'])
        add('erro', 'Base total do ajuste', f'Pelos produtos que entram na redução, a base seria R$ {_brl(base_esp)}'
            f' ({"valor − ICMS" if usa_icms else "valor da operação"}) e o ajuste PIS R$ {_brl(base_esp * r_pis / 100)} · COFINS R$ {_brl(base_esp * r_cof / 100)};'
            f' no arquivo a base é R$ {_brl(bp)} (PIS R$ {_brl(vp)} · COFINS R$ {_brl(vc)}).'
            + (' Os produtos "para confirmar" foram mantidos dentro.' if res['v_conf'] else ''))
    res['base_esperada'] = base_esp
    # apuração da redução linear pelo próprio sistema (independe do que foi declarado no arquivo)
    if not (det['PIS'] or det['COFINS']):
        usa_icms = True        # sem ajuste no arquivo: base sem o ICMS destacado, como na base do PIS/COFINS (Tema 69 do STF)
    r_pis = min(esperadas['PIS']) if regime != '2' else ALIQ['cum'][0]
    r_cof = min(esperadas['COFINS']) if regime != '2' else ALIQ['cum'][1]
    if regime not in ('2', '3'):
        r_pis, r_cof = ALIQ['nc']
    ap_base = ap_pis = ap_cof = 0.0
    for d in docs06.values():
        b = round(d['v_in'] - (d['i_in'] if usa_icms else 0), 2)
        if b <= 0:
            continue
        ap_base += b
        ap_pis += round(b * r_pis / 100 + 1e-9, 2)
        ap_cof += round(b * r_cof / 100 + 1e-9, 2)
    res['apuracao'] = {'base': round(ap_base, 2), 'pis': round(ap_pis, 2), 'cofins': round(ap_cof, 2), 'r_pis': r_pis, 'r_cof': r_cof,
                       'usa_icms': usa_icms, 'decl_base': bp, 'decl_pis': vp, 'decl_cofins': vc,
                       'regime3': regime == '3', 'v_conf': res['v_conf']}
    if any(p['consolidado'] for p in res['produtos']):
        add('info', 'NFC-e consolidada (C175)', 'O C175 não traz o produto: essas vendas foram consideradas dentro da redução. Se alguma for de produto da cesta básica ou hortifruti, ela sai do ajuste.')
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
           'padding:10px 14px;font-size:12px;color:#633806;margin:10px 20px}'
           '.rl-det summary{cursor:pointer;font-weight:700;font-size:14px;color:#1f2a5a;list-style:none;display:flex;align-items:center;gap:8px}'
           '.rl-det summary::before{content:"▸";transition:transform .2s;display:inline-block}.rl-det[open] summary::before{transform:rotate(90deg)}'
           '.rl-det summary span{font-weight:400;color:var(--ink2);font-size:12.5px}.rl-det[open] summary{margin-bottom:10px}</style>')
    linhas = [[f'<span class="st {_ST[x["st"]][0]}">{_ST[x["st"]][1]}</span>', f'<b>{_esc(x["titulo"])}</b>', _esc(x['detalhe'])] for x in C]
    t1 = _linhas_tabela(['Situação', 'Conferência', 'Detalhe'], linhas, ['c', 'l', 'l'])
    if len(C) == 1 and C[0]['st'] == 'info':
        return css + f'<div class="card"><h3>Redução linear de benefícios · LC 224/2025 <span style="font-size:11px;color:#854f0b">(conferência interna)</span></h3>{t1}</div>'
    mod = {'55': 'NF-e', '65': 'NFC-e'}
    dd = lambda d: f'{d[:2]}/{d[2:4]}' if len(d) == 8 else d
    stm = {'ok': '<span class="st ok">✓</span>', 'dif': '<span class="st dif">diverge</span>', 'falta': '<span class="st err">sem M225/M625</span>',
           'fora': '<span class="st so">fora da redução</span>', 'indevido': '<span class="st err">ajuste indevido</span>',
           'com_fora': '<span class="st err">base com produto fora</span>'}
    stp = {'entra': '<span class="st ok">entra</span>', 'fora': '<span class="st so">fora</span>', 'confirmar': '<span class="st dif">confirmar</span>'}
    tp = _linhas_tabela(['Produto', 'NCM', 'Descrição', 'Notas', 'Valor', 'Redução', 'Motivo'],
                        [[_esc(p['cod']), _esc(p['ncm']), _esc(p['descr'][:80]), str(p['notas']), _brl(p['valor']), stp[p['st']], _esc(p['motivo']) or '—']
                         for p in res.get('produtos', [])], ['l', 'l', 'l', 'r', 'r', 'c', 'l'])
    t2 = _linhas_tabela(['Documento', 'Data', 'Valor CST 06', 'Fora da redução', 'ICMS', 'Base (M225)', 'PIS', 'COFINS', 'Situação'],
                        [[f'{mod.get(d["mod"], d["mod"])} {_esc(d["num"])}', dd(d['data']), _brl(d['valor']), _brl(d.get('v_fora', 0)), _brl(d['icms']), f'<b>{_brl(d["base"])}</b>',
                          _brl(d['pis']), _brl(d['cofins']), stm[d['st']]] for d in res['docs']],
                        ['l', 'l', 'r', 'r', 'r', 'r', 'r', 'r', 'c'])
    a = res.get('apuracao') or {}
    def lin(rot, ap, de):
        dif = round(ap - de, 2)
        cor = '#0f6e56' if abs(dif) < 0.05 else '#a32020'
        return [rot, f'<b>R$ {_brl(ap)}</b>', f'R$ {_brl(de)}', f'<b style="color:{cor}">{"✓" if abs(dif) < 0.05 else ("+" if dif > 0 else "−") + " R$ " + _brl(abs(dif))}</b>']
    t_ap = _linhas_tabela(['', 'Apurado pelo sistema', 'Declarado no arquivo (M220/M620)', 'Diferença'], [
        lin(f'Base (produtos que entram · {"valor − ICMS" if a.get("usa_icms") else "valor da operação"})', a.get('base', 0), a.get('decl_base', 0)),
        lin(f'PIS ({_pct(a.get("r_pis", 0))})', a.get('pis', 0), a.get('decl_pis', 0)),
        lin(f'COFINS ({_pct(a.get("r_cof", 0))})', a.get('cofins', 0), a.get('decl_cofins', 0)),
        lin('<b>Total a acrescentar</b>', a.get('pis', 0) + a.get('cofins', 0), a.get('decl_pis', 0) + a.get('decl_cofins', 0)),
    ], ['l', 'r', 'r', 'r'], [None, None, None, 'tot']) if a else ''
    nota_ap = ('Calculado nota a nota, só com os produtos que entram na redução (exceções da LC 224/2025 fora), com arredondamento por nota como no M225/M625.'
               + (' Os produtos "para confirmar" estão dentro.' if a.get('v_conf') else '')
               + (' Empresa com os dois regimes: usado o não cumulativo.' if a.get('regime3') else ''))
    card_ap = (f'<div class="card"><h3>Apuração da redução linear pelo sistema</h3>{t_ap}'
               f'<div style="font-size:11px;color:var(--ink2);margin-top:8px">{nota_ap}</div></div>') if a else ''
    n_prob = sum(1 for d in res['docs'] if d['st'] not in ('ok', 'fora'))
    kp = (f'<div class="kpis"><div class="kpi"><b>R$ {_brl(res.get("m400_06") or res.get("receita06_docs", 0))}</b><span>Receita com CST 06 (alíquota zero)</span></div>'
          f'<div class="kpi"><b>R$ {_brl(res.get("base", 0))}</b><span>Base do ajuste (M225/M625) · {res.get("n_docs", 0)} notas</span></div>'
          f'<div class="kpi laranja"><b style="color:#e8632b">R$ {_brl(a.get("pis", 0) + a.get("cofins", 0))}</b><span>Apurado pelo sistema (PIS + COFINS)</span></div>'
          f'<div class="kpi {"verde" if not n_err else "laranja"}"><b style="color:{"#0f6e56" if not n_err else "#a32020"}">{n_ok} corretas</b>'
          f'<span>{n_dif} atenção · {n_err} erro(s)</span></div></div>')
    return (css + '<div class="rl-aviso">🔒 <b>Conferência interna — redução linear (LC 224/2025).</b> Esta parte não vai para o relatório do cliente.</div>'
            + kp + card_ap + f'<div class="card"><h3>Redução linear de benefícios · conferências</h3>{t1}'
            '<div style="font-size:11px;color:var(--ink2);margin-top:8px">Base legal: LC 224/2025 · Nota Técnica EFD-Contribuições nº 12/2026 · IN RFB nº 2.305/2025, art. 7º.</div></div>'
            + f'<div class="card"><h3>Redução linear · produtos com alíquota zero (CST 06)</h3>'
            f'<div style="font-size:12px;color:var(--ink2);margin:-4px 0 8px">Entram na redução: R$ {_brl(res.get("v_entra", 0))} · fora pelas exceções: R$ {_brl(res.get("v_fora", 0))}'
            + (f' · para confirmar: R$ {_brl(res.get("v_conf", 0))}' if res.get('v_conf') else '') + f'</div>{tp}</div>'
            + f'<div class="card"><details class="rl-det"><summary>Detalhar documentos <span>({res.get("n_docs", 0)} notas com CST 06'
            + (f' · {n_prob} com divergência' if n_prob else '') + f')</span></summary>{t2}</details></div>')


def resumo_alerta(res):
    """Resumo para o alerta da tela ao importar o arquivo: 'falta' (sem ajuste), 'menor', 'maior', 'ok' ou None."""
    if not res.get('aplica') or not res.get('apuracao'):
        return None
    a = res['apuracao']
    ap = round(a['pis'] + a['cofins'], 2)
    de = round(a['decl_pis'] + a['decl_cofins'], 2)
    if ap <= 0.05 and de <= 0.05:
        return None
    if de <= 0.004 and ap > 0.05:
        st = 'falta'
    elif ap - de > 0.05:
        st = 'menor'
    elif de - ap > 0.05:
        st = 'maior'
    else:
        st = 'ok'
    docs_in = sum(1 for d in res.get('docs', []) if d.get('st') not in ('fora',))
    return {'status': st, 'competencia': res.get('competencia', ''), 'empresa': (res.get('empresa') or {}).get('nome', ''),
            'regime': res.get('regime_rot', ''), 'receita': round(res.get('v_entra', 0) + res.get('v_conf', 0), 2),
            'notas': docs_in, 'produtos': sum(1 for p in res.get('produtos', []) if p['st'] != 'fora'),
            'r_pis': a['r_pis'], 'r_cof': a['r_cof'], 'ap_pis': a['pis'], 'ap_cofins': a['cofins'], 'ap_total': ap,
            'de_pis': a['decl_pis'], 'de_cofins': a['decl_cofins'], 'de_total': de, 'diferenca': round(ap - de, 2)}

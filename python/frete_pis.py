# -*- coding: utf-8 -*-
"""Crédito de PIS/COFINS sobre frete FOB (Admin · teste).

Frete pago pela própria empresa na compra (CT-e em que o tomador do serviço é a empresa) × itens das NF-e
transportadas. O frete da compra integra o custo de aquisição e só gera crédito na medida dos bens que dão crédito:
compra para revenda de produto monofásico e de produto com alíquota zero não gera crédito (Lei 10.833/2003, art. 3º,
I, "b", e §2º, II; Lei 10.637/2002, art. 3º, I, "b", e §2º, II). Por isso o frete de cada CT-e é rateado pelo valor
dos itens tributados das notas que ele transportou.

Classificação de cada item pelo CST de PIS informado pelo fornecedor:
  01 → tributado · 02, 03, 04 → monofásico · 05 → substituição tributária · 06, 07, 08 → alíquota zero / isento /
  sem incidência · 09, 49, 99 e demais → "Verificar". Fornecedor do Simples Nacional (CRT 1/4) → tributado.
Item com NCM da lista de monofásicos (Tabela 4.3.10, oportunidades.py) e CST 01 → "Verificar" (o CST e o NCM não
batem; quem decide é o contador). Itens "Verificar" ficam fora da base e aparecem como crédito adicional possível.

Nada nos arquivos é alterado. O cálculo é para conferência.
"""
import os
import re
import json
from collections import defaultdict, Counter

import xml_entradas as xe

ALIQ_PIS, ALIQ_COFINS = 1.65, 7.6
CST_CAT = {'01': 'tributado', '02': 'monofasico', '03': 'monofasico', '04': 'monofasico', '05': 'st',
           '06': 'zero', '07': 'zero', '08': 'zero'}
CAT_NOME = {'tributado': 'Tributado', 'monofasico': 'Monofásico', 'st': 'Substituição tributária',
            'zero': 'Alíquota zero / isento', 'verificar': 'Verificar'}


def _fx(s):
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def _br(d):
    return f'{d[8:10]}/{d[5:7]}/{d[:4]}' if d and len(d) >= 10 and d[4] == '-' else d


def _brl(v):
    return f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _ler_nfe(texto):
    m = re.search(r'<infNFe[^>]*Id="NFe(\d{44})"', texto)
    if not m:
        return None
    try:
        raiz = xe._limpa(texto)
    except Exception:
        return None
    inf = raiz if raiz.tag == 'infNFe' else raiz.find('.//infNFe')
    if inf is None:
        return None
    t = xe._t
    emit, ide = inf.find('emit'), inf.find('ide')
    itens = []
    for det in inf.findall('det'):
        prod, imp = det.find('prod'), det.find('imposto')
        if prod is None:
            continue
        pis = imp.find('PIS') if imp is not None else None
        g = list(pis)[0] if pis is not None and len(list(pis)) else None
        itens.append({'n': det.get('nItem'), 'cod': t(prod, 'cProd'), 'desc': t(prod, 'xProd'), 'ncm': t(prod, 'NCM'),
                      'cfop': t(prod, 'CFOP'), 'cst': t(g, 'CST'),
                      'valor': round(_fx(t(prod, 'vProd')) - _fx(t(prod, 'vDesc')), 2)})
    return {'chave': m.group(1), 'num': t(ide, 'nNF'), 'data': (t(ide, 'dhEmi') or t(ide, 'dEmi'))[:10],
            'emit': t(emit, 'CNPJ') or t(emit, 'CPF'), 'emit_nome': t(emit, 'xNome'), 'crt': t(emit, 'CRT'),
            'dest': t(inf.find('dest'), 'CNPJ'), 'itens': itens}


def _ler_cte(texto):
    c = xe.ler_cte(texto)
    if not c:
        return None
    c['num'] = (re.search(r'<nCT>(\d+)</nCT>', texto) or [None, ''])[1]
    c['data'] = ((re.search(r'<dhEmi>([^<]+)</dhEmi>', texto) or [None, ''])[1])[:10]
    return c


def ler_arquivos(caminhos):
    from fiscal_core import coletar_xmls, _read_text
    ctes, nfes, erros, cancel = {}, {}, 0, set()
    for p in coletar_xmls(caminhos):
        try:
            tx = _read_text(p)
        except Exception:
            erros += 1
            continue
        if '<infCte' in tx:
            c = _ler_cte(tx)
            if c:
                ctes[c['chave']] = c
        elif '<infNFe' in tx:
            n = _ler_nfe(tx)
            if n:
                nfes[n['chave']] = n
        elif '<tpEvento>110111</tpEvento>' in tx:
            m = re.search(r'<ch(?:NFe|CTe)>(\d{44})</ch(?:NFe|CTe)>', tx)
            if m:
                cancel.add(m.group(1))
    return ctes, nfes, cancel, erros


def ler_efd(caminho):
    """EFD-Contribuições: créditos já tomados sobre CT-e (D100 + D101/D105) e CNPJ do estabelecimento."""
    import difal_ro as dr
    texto, _ = dr._ler(caminho)
    cnpj, nome, ini, fim = '', '', '', ''
    por_cte = defaultdict(lambda: {'pis': 0.0, 'cofins': 0.0})
    atual = None
    for l in texto.replace('\r\n', '\n').split('\n'):
        c = l.split('|')
        if len(c) < 3:
            continue
        r = c[1]
        if r == '0000' and len(c) > 9:
            ini, fim, nome, cnpj = c[6], c[7], c[8], c[9]
        elif r == 'D100' and len(c) > 10:
            atual = c[10] if c[2] == '0' else None
        elif r == 'D101' and atual and len(c) > 8:
            por_cte[atual]['pis'] += _fx(c[8].replace(',', '.'))
        elif r == 'D105' and atual and len(c) > 8:
            por_cte[atual]['cofins'] += _fx(c[8].replace(',', '.'))
        elif r == '9999':
            break
    return {'cnpj': cnpj, 'nome': nome, 'ini': ini, 'fim': fim, 'por_cte': dict(por_cte)}


def classificar(item, nfe, regra_ncm):
    simples = nfe['crt'] in ('1', '4')
    mono_ncm = regra_ncm(item['ncm']) is not None
    if simples:
        if mono_ncm:
            return 'monofasico', 'Fornecedor do Simples; NCM da lista de monofásicos (Tabela 4.3.10)'
        return 'tributado', 'Fornecedor do Simples Nacional: a compra gera crédito'
    cat = CST_CAT.get(item['cst'])
    if cat == 'tributado' and mono_ncm:
        return 'verificar', f'CST {item["cst"]} (tributado) com NCM da lista de monofásicos: confira o produto'
    if cat:
        return cat, f'CST de PIS {item["cst"]} informado pelo fornecedor'
    return 'verificar', f'CST de PIS {item["cst"] or "(vazio)"}: depende da operação; confira'


def analisar(caminhos, efd='', cnpj='', excluir_icms=True):
    from oportunidades import _regra_ncm
    ctes, nfes, cancel, erros = ler_arquivos(caminhos)
    ef = ler_efd(efd) if efd else None
    cnpj = re.sub(r'\D', '', cnpj or (ef or {}).get('cnpj', ''))
    if not cnpj:
        cont = Counter(c['toma_cnpj'] for c in ctes.values() if c.get('toma_cnpj'))
        cnpj = cont.most_common(1)[0][0] if cont else ''
    raiz = cnpj[:8]
    linhas, pend, cif = [], [], []
    tot = defaultdict(float)
    cats_tot = defaultdict(float)
    for c in sorted(ctes.values(), key=lambda x: (x['data'], x['num'])):
        if c['chave'] in cancel:
            pend.append({'sit': 'Informativo', 'texto': f'CT-e {c["num"]} cancelado (evento no lote): fora do cálculo'})
            continue
        if not raiz or (c.get('toma_cnpj') or '')[:8] != raiz:
            cif.append({'num': c['num'], 'data': c['data'], 'transp': c['emit_nome'], 'toma': c.get('toma_cnpj', ''),
                        'valor': c['vtprest']})
            continue
        base_frete = round(c['vtprest'] - (c['vicms'] if excluir_icms else 0), 2)
        notas, faltam = [], []
        soma = defaultdict(float)
        for ch in c['nfes']:
            n = nfes.get(ch)
            if not n:
                faltam.append(ch)
                continue
            sn = defaultdict(float)
            its = []
            for it in n['itens']:
                cat, motivo = classificar(it, n, _regra_ncm)
                sn[cat] += it['valor']
                its.append({**it, 'cat': cat, 'motivo': motivo})
            for k, v in sn.items():
                soma[k] += v
            total_n = sum(sn.values())
            notas.append({'chave': ch, 'num': n['num'], 'data': n['data'], 'emit_nome': n['emit_nome'], 'total': round(total_n, 2),
                          'cats': {k: round(v, 2) for k, v in sn.items()}, 'itens': its})
        total = sum(soma.values())
        l = {'chave': c['chave'], 'num': c['num'], 'data': c['data'], 'transp': c['emit_nome'], 'transp_cnpj': c['emit_cnpj'],
             'vtprest': c['vtprest'], 'vicms': c['vicms'], 'base_frete': base_frete, 'qtd_nfes': len(c['nfes']),
             'notas': notas, 'faltam': faltam, 'cats': {k: round(v, 2) for k, v in soma.items()}}
        if not c['nfes']:
            l.update(sit='Verificar', base=0.0, pis=0.0, cofins=0.0, adicional=0.0,
                     motivo='O CT-e não informa as NF-e transportadas')
            pend.append({'sit': 'Verificar', 'texto': f'CT-e {c["num"]}: não informa as NF-e transportadas, sem como ratear'})
        elif faltam:
            l.update(sit='Verificar', base=0.0, pis=0.0, cofins=0.0, adicional=0.0,
                     motivo=f'Falta o XML de {len(faltam)} NF-e transportada(s)')
            pend.append({'sit': 'Verificar', 'texto': f'CT-e {c["num"]}: falta o XML de {len(faltam)} NF-e ({", ".join(faltam[:3])}'
                                                      f'{"…" if len(faltam) > 3 else ""}) — o rateio fica pendente até a nota ser anexada'})
        elif total <= 0:
            l.update(sit='Verificar', base=0.0, pis=0.0, cofins=0.0, adicional=0.0, motivo='Notas sem valor de itens')
        else:
            prop = soma['tributado'] / total
            prop_v = soma['verificar'] / total
            base = round(base_frete * prop, 2)
            adic = round(base_frete * prop_v, 2)
            l.update(prop=round(prop * 100, 2), base=base, pis=round(base * ALIQ_PIS / 100, 2),
                     cofins=round(base * ALIQ_COFINS / 100, 2), adicional=adic,
                     sit='Calculado' if base > 0 else 'Sem crédito',
                     motivo=(f'{prop * 100:.1f}% das notas é tributado'.replace('.', ',')
                             + (f' · {prop_v * 100:.1f}% para verificar'.replace('.', ',') if prop_v else '')))
            if prop_v:
                pend.append({'sit': 'Verificar', 'texto': f'CT-e {c["num"]}: itens para verificar (CST × NCM ou CST que depende da '
                                                          f'operação) — R$ {_brl(adic)} de frete fora da base até a confirmação'})
            for k, v in soma.items():
                cats_tot[k] += v
        if ef:
            ja = ef['por_cte'].get(c['chave'], {'pis': 0.0, 'cofins': 0.0})
            l['efd_pis'], l['efd_cofins'] = round(ja['pis'], 2), round(ja['cofins'], 2)
            tot['efd'] += ja['pis'] + ja['cofins']
        tot['frete'] += c['vtprest']
        tot['base_frete'] += base_frete
        tot['base'] += l['base']
        tot['pis'] += l['pis']
        tot['cofins'] += l['cofins']
        tot['adicional'] += l['adicional']
        linhas.append(l)
    r2 = lambda v: round(v, 2)
    res = {
        'cnpj': cnpj, 'empresa': (ef or {}).get('nome', ''), 'excluir_icms': excluir_icms,
        'periodo_efd': f"{(ef or {}).get('ini', '')} a {(ef or {}).get('fim', '')}" if ef else '',
        'qtd': {'ctes': len(ctes), 'nfes': len(nfes), 'fob': len(linhas), 'cif': len(cif), 'erros': erros},
        'totais': {k: r2(v) for k, v in tot.items()},
        'cats': {k: r2(v) for k, v in cats_tot.items()},
        'adicional_credito': r2(tot['adicional'] * (ALIQ_PIS + ALIQ_COFINS) / 100),
        'linhas': linhas, 'pendencias': pend, 'cif': cif, 'tem_efd': bool(ef),
    }
    res['totais']['credito'] = r2(tot['pis'] + tot['cofins'])
    if ef:
        res['totais']['diferenca'] = r2(tot['pis'] + tot['cofins'] - tot['efd'])
    return res


# ------------------------------------------------------------------------------------------------ Excel
def gerar_xlsx(res, destino):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    navy, cab = PatternFill('solid', fgColor='1E3A8A'), PatternFill('solid', fgColor='334155')
    din = '#,##0.00'

    def faixa(ws, titulo, sub, ncol):
        for r in (1, 2):
            for c in range(1, max(ncol, 8) + 1):
                ws.cell(r, c).fill = navy
        ws.cell(1, 1, titulo).font = Font(bold=True, size=13, color='FFFFFF')
        ws.cell(2, 1, sub).font = Font(size=9.5, color='C7D2FE')
        ws.row_dimensions[1].height = 28
        ws.sheet_view.showGridLines = False

    def tabela(ws, h, cabs, linhas, larg, moeda=()):
        for j, t in enumerate(cabs, 1):
            x = ws.cell(h, j, t)
            x.font, x.fill, x.alignment = Font(bold=True, color='FFFFFF'), cab, Alignment(wrap_text=True, vertical='center')
        for i, l in enumerate(linhas, h + 1):
            for j, v in enumerate(l, 1):
                x = ws.cell(i, j, v)
                x.border = Border(bottom=Side(style='thin', color='E2E8F0'))
                if j - 1 in moeda:
                    x.number_format = din
        for j, w in enumerate(larg, 1):
            ws.column_dimensions[get_column_letter(j)].width = w
        ws.freeze_panes = ws.cell(h + 1, 1)
        if linhas:
            ws.auto_filter.ref = f'A{h}:{get_column_letter(len(cabs))}{h + len(linhas)}'

    t = res['totais']
    sub = (f"CNPJ {res['cnpj']} · PIS {_brl(ALIQ_PIS)}% e COFINS {_brl(ALIQ_COFINS)}% · "
           f"ICMS do CT-e {'excluído' if res['excluir_icms'] else 'mantido'} na base · cálculo para conferência")
    ws = wb.active
    ws.title = 'Resumo'
    faixa(ws, 'CRÉDITO DE PIS/COFINS SOBRE FRETE FOB', sub, 6)
    lin = [('CT-e FOB (tomador = empresa)', res['qtd']['fob']), ('CT-e CIF / de outro tomador (fora)', res['qtd']['cif']),
           ('Frete total dos CT-e FOB', t.get('frete', 0)), ('Base do frete (após ICMS, se excluído)', t.get('base_frete', 0)),
           ('Frete dos itens tributados (base do crédito)', t.get('base', 0)), ('Crédito de PIS', t.get('pis', 0)),
           ('Crédito de COFINS', t.get('cofins', 0)), ('Crédito total', t.get('credito', 0)),
           ('Crédito adicional possível (itens para verificar)', res['adicional_credito'])]
    if res['tem_efd']:
        lin += [('Já tomado na EFD-Contribuições (D101/D105)', t.get('efd', 0)), ('Diferença', t.get('diferenca', 0))]
    for i, (rot, v) in enumerate(lin, 4):
        ws.cell(i, 1, rot).font = Font(bold='Crédito' in rot or 'Diferença' in rot)
        x = ws.cell(i, 2, v)
        if isinstance(v, float):
            x.number_format = din
    ws.column_dimensions['A'].width = 52
    ws.column_dimensions['B'].width = 18
    ws.cell(len(lin) + 5, 1, 'Base legal: Lei 10.833/2003, art. 3º, I, "b", e §2º, II; Lei 10.637/2002, art. 3º, I, "b", e §2º, II. '
                             'O frete da compra acompanha o crédito dos bens transportados; rateio pelo valor dos itens tributados.'
                             ).font = Font(italic=True, size=9, color='64748B')
    w = wb.create_sheet('Por CT-e')
    faixa(w, 'POR CT-E', sub, 14)
    tabela(w, 3, ['CT-e', 'Data', 'Transportadora', 'NF-e', 'Frete', 'ICMS CT-e', 'Base do frete', '% tributado', 'Base do crédito',
                  'PIS', 'COFINS', 'Frete p/ verificar'] + (['PIS na EFD', 'COFINS na EFD'] if res['tem_efd'] else []) + ['Situação', 'Chave'],
           [[l['num'], _br(l['data']), l['transp'], l['qtd_nfes'], l['vtprest'], l['vicms'], l['base_frete'], l.get('prop', 0) / 100,
             l['base'], l['pis'], l['cofins'], l['adicional']] + ([l.get('efd_pis', 0), l.get('efd_cofins', 0)] if res['tem_efd'] else [])
            + [l['sit'] + (' · ' + l['motivo'] if l.get('motivo') else ''), l['chave']] for l in res['linhas']],
           [10, 11, 34, 6, 13, 12, 13, 10, 14, 11, 11, 13] + ([12, 12] if res['tem_efd'] else []) + [44, 47],
           (4, 5, 6, 8, 9, 10, 11) + ((12, 13) if res['tem_efd'] else ()))
    for r in range(4, len(res['linhas']) + 4):
        w.cell(r, 8).number_format = '0.0%'
    w = wb.create_sheet('Itens das NF-e')
    faixa(w, 'ITENS DAS NF-E TRANSPORTADAS', sub, 11)
    rows = []
    for l in res['linhas']:
        for n in l['notas']:
            for it in n['itens']:
                rows.append([l['num'], n['num'], n['emit_nome'], it['cod'], it['desc'], it['ncm'], it['cfop'], it['cst'],
                             it['valor'], CAT_NOME[it['cat']], it['motivo']])
    tabela(w, 3, ['CT-e', 'NF-e', 'Fornecedor', 'Código', 'Produto', 'NCM', 'CFOP', 'CST PIS', 'Valor do item', 'Classificação', 'Motivo'],
           rows, [10, 10, 32, 12, 40, 11, 7, 8, 13, 22, 60], (8,))
    w = wb.create_sheet('Pendências')
    faixa(w, 'PENDÊNCIAS', sub, 3)
    tabela(w, 3, ['Situação', 'O que foi encontrado'], [[p['sit'], p['texto']] for p in res['pendencias']], [14, 120])
    if res['cif']:
        w = wb.create_sheet('CT-e fora (CIF)')
        faixa(w, 'CT-E COM OUTRO TOMADOR (CIF) — FORA DO CÁLCULO', sub, 5)
        tabela(w, 3, ['CT-e', 'Data', 'Transportadora', 'Tomador', 'Valor'],
               [[c['num'], _br(c['data']), c['transp'], c['toma'], c['valor']] for c in res['cif']], [10, 11, 36, 18, 13], (4,))
    tmp = destino + '.parcial'
    wb.save(tmp)
    os.replace(tmp, destino)


# ------------------------------------------------------------------------------------------------ HTML
def gerar_html(res):
    js = json.dumps(res, ensure_ascii=False).replace('</', '<\\/')
    return HTML.replace('/*DADOS*/', js)


HTML = r'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Crédito PIS/COFINS sobre frete FOB</title><style>
*{box-sizing:border-box}body{margin:0;font-family:"Segoe UI",Arial,sans-serif;background:#f1f4f9;color:#0f172a}
.hd{background:#1e3a8a;color:#fff;padding:20px 28px;display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap}
.hd h1{margin:0;font-size:21px}.hd .s{font-size:12.5px;color:#c7d2fe;margin-top:4px}
.adm{font-size:10px;font-weight:800;letter-spacing:1px;background:#7c3aed;padding:3px 8px;border-radius:5px;margin-left:8px;vertical-align:middle}
.w{padding:18px 28px;max-width:1500px;margin:0 auto}
.k{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.c{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:13px 14px;border-top:3px solid var(--c);animation:sobe .5s both}
.c small{font-size:10.5px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.5px}.c b{display:block;font-size:20px;margin-top:5px}.c span{font-size:11px;color:#64748b}
@keyframes sobe{from{opacity:0;transform:translateY(10px)}}
h3{font-size:13px;color:#1e3a8a;margin:22px 0 8px;letter-spacing:.5px;text-transform:uppercase}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e2e8f0;font-size:12.5px}
th{background:#334155;color:#fff;text-align:left;padding:9px 10px;font-size:11px;position:sticky;top:0}td{padding:8px 10px;border-top:1px solid #eef2f7;vertical-align:middle}
td.n,th.n{text-align:right;white-space:nowrap}tr.cte{cursor:pointer}tr.cte:hover td{background:#f8fafc}
tr.sub td{background:#f8fafc;font-size:12px;color:#334155}tr.sub2 td{background:#fcfdff;font-size:11.5px;color:#475569}
.pb{display:flex;height:10px;border-radius:5px;overflow:hidden;width:150px;background:#e2e8f0}.pb i{display:block;height:100%}
.tg{font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:20px;white-space:nowrap}
.t-Calculado,.t-Sem{background:#dcfce7;color:#15803d}.t-Verificar{background:#fef3c7;color:#b45309}.t-Informativo{background:#e0e7ff;color:#4338ca}
.lg{display:flex;gap:14px;font-size:11.5px;color:#475569;margin:6px 0;flex-wrap:wrap}.lg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
.lei{background:#eef2ff;border-left:4px solid #1e3a8a;border-radius:8px;padding:10px 14px;font-size:12px;color:#334155;margin-top:16px;line-height:1.55}
input.q{border:1px solid #cbd5e1;border-radius:10px;padding:8px 12px;font-size:13px;min-width:320px;margin-bottom:8px}
.sm{font-size:11px;color:#64748b}
</style></head><body>
<div class="hd"><div><h1>Crédito de PIS/COFINS sobre frete FOB <span class="adm">ADMIN · TESTE</span></h1><div class="s">CT-e de frete na compra × itens das NF-e transportadas · rateio pelo valor dos itens tributados</div></div><div class="s" id="cab"></div></div>
<div class="w"><div class="k" id="kpis"></div>
<h3>Por CT-e (clique para ver as notas e o rateio)</h3>
<div class="lg"><span><i style="background:#0ea472"></i>tributado</span><span><i style="background:#f59e0b"></i>monofásico</span><span><i style="background:#ef4444"></i>substituição tributária</span><span><i style="background:#94a3b8"></i>alíquota zero / isento</span><span><i style="background:#a78bfa"></i>verificar</span></div>
<input class="q" id="q" placeholder="Pesquisar CT-e, NF-e, transportadora ou fornecedor">
<table><thead><tr><th>CT-e</th><th>Data</th><th>Transportadora</th><th>NF-e</th><th>Composição das notas</th><th class="n">Frete</th><th class="n">Base do crédito</th><th class="n">PIS + COFINS</th><th>Situação</th></tr></thead><tbody id="tb"></tbody></table>
<h3>Pendências</h3><div id="pend"></div>
<div id="cifbox"></div>
<div class="lei"><b>Critério:</b> o frete pago na compra (FOB) integra o custo de aquisição e gera crédito na mesma medida dos bens transportados. A compra para revenda de produto monofásico e de produto com alíquota zero não gera crédito (Lei 10.833/2003, art. 3º, I, "b", e §2º, II; Lei 10.637/2002, art. 3º, I, "b", e §2º, II), então o frete de cada CT-e é rateado pelo valor dos itens tributados das notas transportadas. Itens "verificar" (CST × NCM de monofásico, ou CST que depende da operação) ficam fora da base até a confirmação. Só se aplica ao regime não cumulativo. <b>O cálculo é para conferência; quem decide é o contador.</b></div></div>
<script>
const D=/*DADOS*/;const $=s=>document.querySelector(s);
const m=v=>(v||0).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});
const e=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const br=d=>d&&d.length>=10?d.slice(8,10)+'/'+d.slice(5,7)+'/'+d.slice(0,4):(d||'');
const COR={tributado:'#0ea472',monofasico:'#f59e0b',st:'#ef4444',zero:'#94a3b8',verificar:'#a78bfa'};
const NOME={tributado:'Tributado',monofasico:'Monofásico',st:'Subst. tributária',zero:'Alíquota zero / isento',verificar:'Verificar'};
const T=D.totais;
$('#cab').innerHTML=`${D.empresa?e(D.empresa)+' · ':''}CNPJ ${e(D.cnpj)}<br>${D.qtd.fob} CT-e FOB · ${D.qtd.nfes} NF-e lidas · ICMS do CT-e ${D.excluir_icms?'excluído':'mantido'} na base`;
const kp=[['CT-e FOB analisados',D.qtd.fob,'tomador = empresa','#1e3a8a',1],['Frete total',T.frete,'valor da prestação','#0891b2'],
 ['Frete dos itens tributados',T.base,(T.base_frete?((T.base/T.base_frete*100).toFixed(1).replace('.',',')+'% pelo rateio'):''),'#0ea472'],
 ['Crédito PIS 1,65%',T.pis,'sobre a base rateada','#7c3aed'],['Crédito COFINS 7,6%',T.cofins,'sobre a base rateada','#7c3aed'],
 ['Crédito adicional possível',D.adicional_credito,'se os itens "verificar" forem confirmados','#a78bfa']];
if(D.tem_efd)kp.push(['Já tomado na EFD',T.efd,'diferença: R$ '+m(T.diferenca),'#ea580c']);
$('#kpis').innerHTML=kp.map(([t,v,s,c,i],k)=>`<div class="c" style="--c:${c};animation-delay:${k*.06}s"><small>${t}</small><b>${i?v:'R$ '+m(v)}</b><span>${e(s)}</span></div>`).join('');
const barra=cats=>{const t=Object.values(cats).reduce((a,b)=>a+b,0)||1;return `<div class="pb">${Object.entries(cats).map(([k,v])=>`<i style="width:${v/t*100}%;background:${COR[k]}" title="${NOME[k]}: R$ ${m(v)}"></i>`).join('')}</div>`};
const abertos=new Set();
function desenha(){const q=($('#q').value||'').toLowerCase();let h='';
 D.linhas.forEach((l,i)=>{const txt=(l.num+' '+l.transp+' '+l.notas.map(n=>n.num+' '+n.emit_nome).join(' ')).toLowerCase();if(q&&!txt.includes(q))return;
  h+=`<tr class="cte" data-i="${i}"><td><b>${e(l.num)}</b></td><td>${br(l.data)}</td><td>${e(l.transp)}</td><td>${l.qtd_nfes} nota(s)</td><td>${barra(l.cats)}</td><td class="n">${m(l.vtprest)}</td><td class="n">${l.sit==='Verificar'&&!l.base?'—':m(l.base)}</td><td class="n">${l.sit==='Verificar'&&!l.base?'—':m(l.pis+l.cofins)}</td><td><span class="tg t-${l.sit.split(' ')[0]}">${e(l.sit)}</span><div class="sm">${e(l.motivo||'')}</div></td></tr>`;
  if(abertos.has(i)){
   h+=`<tr class="sub"><td></td><td colspan="8">Frete R$ ${m(l.vtprest)}${l.vicms?` · ICMS do CT-e R$ ${m(l.vicms)} ${D.excluir_icms?'(excluído)':'(mantido)'}`:''} · base do frete R$ ${m(l.base_frete)}${l.efd_pis!==undefined?` · na EFD: PIS R$ ${m(l.efd_pis)} / COFINS R$ ${m(l.efd_cofins)}`:''}</td></tr>`;
   l.notas.forEach(n=>{const trib=n.cats.tributado||0;
    h+=`<tr class="sub"><td></td><td colspan="3">↳ NF-e ${e(n.num)} · ${e(n.emit_nome)} · ${br(n.data)}</td><td>${barra(n.cats)}</td><td class="n" colspan="2">tributado R$ ${m(trib)} de R$ ${m(n.total)}</td><td class="n" colspan="2">${n.total?(trib/n.total*100).toFixed(1).replace('.',','):0}% tributado</td></tr>`;
    n.itens.forEach(it=>{h+=`<tr class="sub2"><td></td><td></td><td colspan="2">${e(it.desc)} <span class="sm">· NCM ${e(it.ncm)} · CST ${e(it.cst)}</span></td><td><span style="color:${COR[it.cat]};font-weight:700">${NOME[it.cat]}</span></td><td class="n">${m(it.valor)}</td><td colspan="3" class="sm">${e(it.motivo)}</td></tr>`});});
   l.faltam.forEach(ch=>{h+=`<tr class="sub"><td></td><td colspan="8" style="color:#b45309">↳ NF-e sem XML no lote: ${e(ch)}</td></tr>`});}
 });$('#tb').innerHTML=h||'<tr><td colspan="9" class="sm">Nenhum CT-e com essa pesquisa.</td></tr>';
 document.querySelectorAll('tr.cte').forEach(r=>r.onclick=()=>{const i=+r.dataset.i;abertos.has(i)?abertos.delete(i):abertos.add(i);desenha();});}
$('#q').oninput=desenha;desenha();
$('#pend').innerHTML=D.pendencias.length?`<table><tr><th>Situação</th><th>O que foi encontrado</th></tr>${D.pendencias.map(p=>`<tr><td><span class="tg t-${p.sit}">${p.sit}</span></td><td>${e(p.texto)}</td></tr>`).join('')}</table>`:'<div class="sm">Nenhuma pendência.</div>';
if(D.cif.length)$('#cifbox').innerHTML=`<h3>CT-e com outro tomador (CIF) — fora do cálculo</h3><table><tr><th>CT-e</th><th>Data</th><th>Transportadora</th><th>Tomador</th><th class="n">Valor</th></tr>${D.cif.map(c=>`<tr><td>${e(c.num)}</td><td>${br(c.data)}</td><td>${e(c.transp)}</td><td>${e(c.toma)}</td><td class="n">${m(c.valor)}</td></tr>`).join('')}</table>`;
</script></body></html>'''


def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None

    def lista(n):
        if n not in argv:
            return []
        out = []
        for a in argv[argv.index(n) + 1:]:
            if a.startswith('--'):
                break
            out.append(a)
        return out
    xmls, js = lista('--xmls'), opt('--json')
    if not xmls or not js:
        print('uso: frete-pis --xmls a.zip [b.zip ...] --json saida.json [--efd efd.txt] [--cnpj N] [--manter-icms] '
              '[--html saida.html] [--xlsx saida.xlsx]')
        return 1
    try:
        res = analisar(xmls, efd=opt('--efd') or '', cnpj=opt('--cnpj') or '', excluir_icms='--manter-icms' not in argv)
        if not res['qtd']['ctes']:
            res = {'erro': 'Nenhum CT-e foi encontrado nos arquivos selecionados.'}
        elif not res['qtd']['fob']:
            res = {'erro': 'Nenhum CT-e tem a empresa como tomadora do serviço (frete FOB). Confira o CNPJ ou os arquivos.'}
        else:
            if opt('--html'):
                tmp = opt('--html') + '.parcial'
                with open(tmp, 'w', encoding='utf-8') as fh:
                    fh.write(gerar_html(res))
                os.replace(tmp, opt('--html'))
            if opt('--xlsx'):
                gerar_xlsx(res, opt('--xlsx'))
            res = {k: v for k, v in res.items() if k not in ('linhas',)}
    except Exception as e:  # pragma: no cover
        import traceback
        traceback.print_exc()
        res = {'erro': f'Falha ao processar: {e}'}
    tmp = js + '.parcial'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False)
    os.replace(tmp, js)
    return 0

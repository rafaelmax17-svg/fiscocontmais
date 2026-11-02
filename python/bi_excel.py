# -*- coding: utf-8 -*-
"""BI da Empresa (Admin) — Excel com o resumo de todas as análises registradas de UMA empresa.

Entrada: lista de registros do bi-historico.json (um por competência + módulo). Abas:
  Painel   — faixa de título, competência numa lista suspensa e cartões que recalculam por fórmula (SOMASES na aba Dados);
  Evolução — tabela mês a mês com gráfico nativo do Excel (barras de entradas + linha de pontos em aberto);
  Mapa     — módulo × mês com a quantidade de pontos em aberto, colorida;
  Pontos   — onde estão os pontos em aberto (módulo, tema, competência);
  uma aba por módulo e a aba Dados (formato tabela, pronta para filtro e tabela dinâmica).
Só lê os resumos; nenhum arquivo do cliente é usado.
"""
import os
import json
from collections import defaultdict

MOD_NOME = {'analise': 'Análise Tributária', 'apuracao': 'Apuração IBS/CBS', 'frete': 'Frete FOB',
            'deson': 'ICMS Desonerado', 'nfse': 'NFS-e'}
IND_NOME = {'entradas': 'Entradas analisadas', 'icms_cred': 'ICMS creditado', 'icms_st': 'ICMS-ST', 'notas': 'Notas de entrada',
            'produtos': 'Produtos', 'ibscbs_debito': 'IBS+CBS débitos', 'ibscbs_credito': 'IBS+CBS créditos',
            'ibscbs_saldo': 'IBS+CBS saldo', 'frete_credito': 'Crédito PIS/COFINS frete', 'frete_total': 'Frete FOB total',
            'frete_adicional': 'Crédito frete a confirmar', 'deson_total': 'ICMS desonerado', 'deson_notas': 'Notas com desoneração',
            'nfse_retido': 'NFS-e retido', 'nfse_com_ret': 'NFS-e com retenção', 'nfse_notas': 'NFS-e no período',
            'nfse_prestado': 'Serviços prestados', 'nfse_tomado': 'Serviços tomados', 'pontos': 'Pontos em aberto'}
CARDS = [('entradas', 'Entradas', '1E3A8A'), ('icms_cred', 'ICMS creditado', '0EA472'), ('ibscbs_saldo', 'IBS+CBS saldo', 'E2552D'),
         ('frete_credito', 'Créd. frete FOB', '7C3AED'), ('pontos', 'Pontos em aberto', 'F59E0B'), ('nfse_retido', 'NFS-e retido', '0891B2')]


def _mes(c):
    return f'{c[5:7]}/{c[:4]}' if len(c) == 7 else c


def gerar(regs, destino):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.chart import BarChart, LineChart, Reference
    regs = sorted(regs, key=lambda r: (r['comp'], r['modulo']))
    empresa = next((r['empresa'] for r in reversed(regs) if r.get('empresa')), '')
    cnpj = regs[-1]['cnpj']
    comps = sorted({r['comp'] for r in regs})
    navy, cab, papel = PatternFill('solid', fgColor='1E3A8A'), PatternFill('solid', fgColor='334155'), PatternFill('solid', fgColor='F1F4F9')
    din = '#,##0.00'
    wb = Workbook()

    def faixa(ws, titulo, sub, ncol):
        for r in (1, 2):
            for c in range(1, ncol + 1):
                ws.cell(r, c).fill = navy
        ws.cell(1, 1, titulo).font = Font(bold=True, size=15, color='FFFFFF')
        ws.cell(2, 1, sub).font = Font(size=10, color='C7D2FE')
        ws.row_dimensions[1].height = 30
        ws.sheet_view.showGridLines = False

    def tabela(ws, h, cabs, linhas, larg, moeda=()):
        for j, t in enumerate(cabs, 1):
            x = ws.cell(h, j, t)
            x.font, x.fill, x.alignment = Font(bold=True, color='FFFFFF'), cab, Alignment(vertical='center', wrap_text=True)
        for i, l in enumerate(linhas, h + 1):
            for j, v in enumerate(l, 1):
                x = ws.cell(i, j, v)
                x.border = Border(bottom=Side(style='thin', color='E2E8F0'))
                if (i - h) % 2 == 0:
                    x.fill = PatternFill('solid', fgColor='F8FAFC')
                if j - 1 in moeda:
                    x.number_format = din
        for j, w in enumerate(larg, 1):
            ws.column_dimensions[get_column_letter(j)].width = w
        ws.freeze_panes = ws.cell(h + 1, 1)
        if linhas:
            ws.auto_filter.ref = f'A{h}:{get_column_letter(len(cabs))}{h + len(linhas)}'

    # ---- Dados (formato longo)
    dados = []
    for r in regs:
        for k, v in (r.get('kpis') or {}).items():
            dados.append([r['comp'], MOD_NOME.get(r['modulo'], r['modulo']), k, IND_NOME.get(k, k), float(v or 0)])
        p = r.get('pontos') or {}
        dados.append([r['comp'], MOD_NOME.get(r['modulo'], r['modulo']), 'pontos', IND_NOME['pontos'],
                      float((p.get('divergente') or 0) + (p.get('verificar') or 0))])
    sub = f'CNPJ {cnpj} · competências {_mes(comps[0])} a {_mes(comps[-1])} · resumo das análises feitas no FiscoCont+'

    ws = wb.active
    ws.title = 'Painel'
    for r in range(1, 40):
        for c in range(1, 15):
            ws.cell(r, c).fill = papel
    faixa(ws, f'BI da Empresa · {empresa}', sub, 14)
    ws.sheet_view.showGridLines = False
    for c in range(1, 15):
        ws.column_dimensions[get_column_letter(c)].width = 14
    ws['B4'] = 'Competência:'
    ws['B4'].font = Font(bold=True, color='1E3A8A')
    ws['C4'] = comps[-1]
    ws['C4'].font = Font(bold=True, size=12)
    ws['C4'].fill = PatternFill('solid', fgColor='FFFFFF')
    ws['C4'].border = Border(*(Side(style='thin', color='1E3A8A'),) * 4)
    ws['E4'] = 'Comparar com:'
    ws['E4'].font = Font(bold=True, color='1E3A8A')
    ws['F4'] = comps[-2] if len(comps) > 1 else comps[-1]
    ws['F4'].font = Font(bold=True, size=12)
    ws['F4'].fill = PatternFill('solid', fgColor='FFFFFF')
    ws['F4'].border = Border(*(Side(style='thin', color='1E3A8A'),) * 4)
    ws['H4'] = 'Troque a competência nas listas: os cartões recalculam sozinhos.'
    ws['H4'].font = Font(italic=True, size=9, color='64748B')
    # lista das competências para a validação
    ws_l = wb.create_sheet('Listas')
    for i, c in enumerate(comps, 1):
        ws_l.cell(i, 1, c)
    ws_l.sheet_state = 'hidden'
    dv = DataValidation(type='list', formula1=f'=Listas!$A$1:$A${len(comps)}', allow_blank=False)
    ws.add_data_validation(dv)
    dv.add('C4')
    dv.add('F4')
    n_d = len(dados) + 3
    for k, (ind, rot, cor) in enumerate(CARDS):
        col = 2 + k * 2
        L = get_column_letter(col)
        for rr in (6, 7, 8):
            for cc in (col, col + 1):
                ws.cell(rr, cc).fill = PatternFill('solid', fgColor='FFFFFF')
            ws.cell(6, col).border = Border(top=Side(style='thick', color=cor))
            ws.cell(6, col + 1).border = Border(top=Side(style='thick', color=cor))
        ws.cell(6, col, rot.upper()).font = Font(bold=True, size=8.5, color='64748B')
        f_atual = f'SUMIFS(Dados!$E$4:$E${n_d},Dados!$A$4:$A${n_d},$C$4,Dados!$C$4:$C${n_d},"{ind}")'
        f_comp = f'SUMIFS(Dados!$E$4:$E${n_d},Dados!$A$4:$A${n_d},$F$4,Dados!$C$4:$C${n_d},"{ind}")'
        ws.merge_cells(start_row=7, start_column=col, end_row=7, end_column=col + 1)
        c = ws.cell(7, col, f'={f_atual}')
        c.font = Font(bold=True, size=15, color=cor)
        c.number_format = '#,##0' if ind == 'pontos' else din
        c.alignment = Alignment(horizontal='left')
        ws.merge_cells(start_row=8, start_column=col, end_row=8, end_column=col + 1)
        v = ws.cell(8, col, f'=IF({f_comp}=0,"",TEXT(({f_atual}-{f_comp})/ABS({f_comp}),"+0,0%;-0,0%")&" vs. "&$F$4)')
        v.font = Font(size=9, color='64748B')
        ws.row_dimensions[7].height = 26
    # mapa resumido no painel: pontos por módulo na competência escolhida
    ws['B10'] = 'Pontos em aberto por módulo (competência escolhida)'
    ws['B10'].font = Font(bold=True, color='1E3A8A')
    for i, (m, nome) in enumerate(MOD_NOME.items()):
        ws.cell(11 + i, 2, nome)
        c = ws.cell(11 + i, 5, f'=SUMIFS(Dados!$E$4:$E${n_d},Dados!$A$4:$A${n_d},$C$4,Dados!$B$4:$B${n_d},"{nome}",Dados!$C$4:$C${n_d},"pontos")')
        c.number_format = '#,##0'
        for cc in range(2, 6):
            ws.cell(11 + i, cc).fill = PatternFill('solid', fgColor='FFFFFF')
            ws.cell(11 + i, cc).border = Border(bottom=Side(style='thin', color='E2E8F0'))
    from openpyxl.formatting.rule import DataBarRule
    ws.conditional_formatting.add(f'E11:E{10 + len(MOD_NOME)}', DataBarRule(start_type='num', start_value=0, end_type='max', color='F59E0B'))

    # ---- Evolução
    w = wb.create_sheet('Evolução', 1)
    faixa(w, 'EVOLUÇÃO MENSAL', sub, 8)
    agg = defaultdict(lambda: defaultdict(float))
    for c, _m, ind, _n, v in dados:
        agg[c][ind] += v
    cols = ['entradas', 'icms_cred', 'ibscbs_saldo', 'frete_credito', 'nfse_retido', 'pontos']
    tabela(w, 3, ['Competência'] + [IND_NOME[c] for c in cols], [[_mes(c)] + [agg[c].get(k, 0.0) for k in cols] for c in comps],
           [13, 18, 16, 15, 18, 14, 15], (1, 2, 3, 4, 5))
    if len(comps) >= 1:
        ch = BarChart()
        ch.title = 'Entradas × pontos em aberto'
        ch.y_axis.title = 'Entradas (R$)'
        ch.add_data(Reference(w, min_col=2, min_row=3, max_row=3 + len(comps)), titles_from_data=True)
        ch.set_categories(Reference(w, min_col=1, min_row=4, max_row=3 + len(comps)))
        ln = LineChart()
        ln.add_data(Reference(w, min_col=7, min_row=3, max_row=3 + len(comps)), titles_from_data=True)
        ln.y_axis.axId = 200
        ln.y_axis.title = 'Pontos em aberto'
        ln.y_axis.crosses = 'max'
        ch += ln
        ch.height, ch.width = 9, 22
        w.add_chart(ch, f'A{6 + len(comps)}')

    # ---- Mapa módulo × mês
    w = wb.create_sheet('Mapa', 2)
    faixa(w, 'SITUAÇÃO POR MÓDULO · MÊS A MÊS', sub + ' · número = pontos em aberto', 2 + len(comps))
    por = {(r['modulo'], r['comp']): (r.get('pontos') or {}) for r in regs}
    linhas = []
    for m, nome in MOD_NOME.items():
        l = [nome]
        for c in comps:
            p = por.get((m, c))
            l.append('—' if p is None else int((p.get('divergente') or 0) + (p.get('verificar') or 0)))
        linhas.append(l)
    tabela(w, 3, ['Módulo'] + [_mes(c) for c in comps], linhas, [22] + [10] * len(comps))
    for i, (m, _n) in enumerate(MOD_NOME.items(), 4):
        for j, c in enumerate(comps, 2):
            p = por.get((m, c))
            x = w.cell(i, j)
            x.alignment = Alignment(horizontal='center')
            if p is None:
                x.fill, x.font = PatternFill('solid', fgColor='E2E8F0'), Font(color='94A3B8')
            else:
                div, tot = p.get('divergente') or 0, (p.get('divergente') or 0) + (p.get('verificar') or 0)
                cor = 'DC2626' if div >= 20 else ('F59E0B' if tot else '16A34A')
                x.fill, x.font = PatternFill('solid', fgColor=cor), Font(bold=True, color='FFFFFF')

    # ---- Pontos (temas)
    w = wb.create_sheet('Pontos', 3)
    faixa(w, 'ONDE ESTÃO OS PONTOS EM ABERTO', sub, 5)
    tl = [[_mes(r['comp']), MOD_NOME.get(r['modulo'], r['modulo']), t.get('tema', ''), int(t.get('itens') or 0), int(t.get('div') or 0)]
          for r in regs for t in (r.get('temas') or [])]
    tl.sort(key=lambda x: (x[0], -x[3]), reverse=True)
    tabela(w, 3, ['Competência', 'Módulo', 'Tema', 'Itens', 'Divergentes'], tl, [13, 22, 60, 10, 12])

    # ---- uma aba por módulo
    for m, nome in MOD_NOME.items():
        rm = [r for r in regs if r['modulo'] == m]
        if not rm:
            continue
        inds = sorted({k for r in rm for k in (r.get('kpis') or {})})
        w = wb.create_sheet(nome.replace('/', '-')[:31])
        faixa(w, nome.upper(), sub, 3 + len(inds))
        tabela(w, 3, ['Competência'] + [IND_NOME.get(k, k) for k in inds] + ['Divergentes', 'Para verificar', 'Analisado em'],
               [[_mes(r['comp'])] + [float((r.get('kpis') or {}).get(k, 0)) for k in inds]
                + [int((r.get('pontos') or {}).get('divergente') or 0), int((r.get('pontos') or {}).get('verificar') or 0),
                   (r.get('quando') or '')[:16].replace('T', ' ')] for r in rm],
               [13] + [17] * len(inds) + [12, 14, 17], tuple(range(1, 1 + len(inds))))

    # ---- Dados
    w = wb.create_sheet('Dados')
    faixa(w, 'DADOS (formato tabela · use filtros e tabela dinâmica)', sub, 5)
    tabela(w, 3, ['Competência', 'Módulo', 'Indicador (código)', 'Indicador', 'Valor'], dados, [13, 22, 18, 30, 16], (4,))
    wb.move_sheet('Listas', offset=len(wb.sheetnames))
    tmp = destino + '.parcial'
    wb.save(tmp)
    os.replace(tmp, destino)
    return {'ok': True, 'competencias': len(comps), 'registros': len(regs)}


def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    ent, sai, js = opt('--entrada'), opt('--saida'), opt('--json')
    try:
        with open(ent, encoding='utf-8') as fh:
            regs = json.load(fh)
        res = gerar(regs, sai) if regs else {'erro': 'Nenhuma análise registrada.'}
    except Exception as e:  # pragma: no cover
        import traceback
        traceback.print_exc()
        res = {'erro': f'Falha ao gerar o BI: {e}'}
    if js:
        with open(js + '.parcial', 'w', encoding='utf-8') as fh:
            json.dump(res, fh, ensure_ascii=False)
        os.replace(js + '.parcial', js)
    return 0

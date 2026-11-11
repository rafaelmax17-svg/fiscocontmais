# -*- coding: utf-8 -*-
"""Adaptação de planilhas (só Admin) · Auditoria de itens (NF · COD_ITEM · DESCRICAO · NCM · CST · CFOP · LEGENDA · CONDICIONAL).

Gera um NOVO Excel no "Modelo B" aprovado: uma aba "Auditoria" de cima para baixo, com os problemas primeiro, cada
grupo com uma frase explicando, e os itens corretos/entradas recolhidos no fim; e a aba "Base original" com os dados
do arquivo do jeito que vieram. O arquivo original nunca é alterado.

Regra da situação (só para SAÍDAS, CFOP 5/6/7; entradas ficam como informativo, porque o CST é do fornecedor):
  • CST de substituição tributária = terminados em 10, 30, 60, 61 e 70.
  • LEGENDA "S.T"       + CST que não é de ST            → Tributou produto que já tem ICMS-ST
  • LEGENDA "Tributado" + CST de ST                       → Saiu como ST, mas o produto é tributado
  • LEGENDA "Isento"    + CST diferente de 40/41          → CST não combina com produto isento
  • Com texto em CONDICIONAL                              → Depende da finalidade (a regra é mostrada)
  • O resto                                               → Correto
"""
import json
import os
import re
from collections import Counter
from datetime import datetime

CST_ST = ('10', '30', '60', '61', '70')
CST_ISENTO = ('40', '41')
CAMPOS = {'NF': 'nf', 'COD_ITEM': 'cod', 'DESCRICAO': 'desc', 'NCM': 'ncm', 'CST': 'cst', 'CFOP': 'cfop',
          'LEGENDA': 'leg', 'CONDICIONAL': 'cond'}
OBRIGATORIOS = ('nf', 'desc', 'cst', 'cfop', 'leg')
MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

# ordem dos grupos na aba Auditoria · (título, cor do grupo, explicação, o que fazer, recolhido?)
GRUPOS = [
    ('st_indevido', '✖ Saiu como Substituição Tributária, mas o produto é tributado', 'B91C1C',
     'Risco: ICMS sem destaque na venda. É o que a SEFIN aponta na malha “Falta de destaque de ICMS · itens que saíram do ST”.',
     'Produto tributado: a venda deve destacar o ICMS (CST 00, ou 20 se houver redução de base). Corrigir o cadastro do produto no sistema do cliente.', False),
    ('trib_indevido', '✖ Tributou um produto que já tem ICMS-ST', 'C2410C',
     'O ICMS já foi pago antes, por substituição tributária: destacar de novo na venda é pagar duas vezes.',
     'Produto com ICMS-ST: vender com CST 60 (ou 61 nos combustíveis), sem destaque de ICMS. Corrigir o cadastro do produto.', False),
    ('isento_div', '✖ CST não combina com produto isento', 'A16207',
     'A legenda diz que o produto é isento, mas o CST usado é de produto tributado ou com ST.',
     'Produto isento: vender com CST 40 (ou 41, se não tributado). Corrigir o cadastro do produto.', False),
    ('condicional', '◆ Depende da finalidade da venda', '4338CA',
     'O produto tem regra especial: o CST usado está certo só se a venda for para a finalidade descrita na regra.',
     '', False),
    ('ok', '✔ Corretos', '15803D', 'O CST usado combina com o tratamento do produto. Nada a fazer.', '', True),
    ('entrada', 'Entradas (informativo)', '64748B',
     'Notas de entrada (CFOP 1, 2 ou 3): o CST é o informado pelo fornecedor, só para consulta.', '', True),
    ('sem_legenda', 'Sem legenda', '64748B', 'O item veio sem tratamento definido na planilha original.', '', True),
]
ROTULO = {'st_indevido': '✖ Saiu como ST · é tributado', 'trib_indevido': '✖ Tributou produto com ST', 'isento_div': '✖ CST errado p/ isento',
          'condicional': '◆ Depende da finalidade', 'ok': '✔ Correto', 'entrada': 'Entrada', 'sem_legenda': 'Sem legenda'}
COR_ROT = {'st_indevido': ('FEE2E2', '991B1B'), 'trib_indevido': ('FFEDD5', '9A3412'), 'isento_div': ('FEF3C7', '92400E'),
           'condicional': ('E0E7FF', '3730A3'), 'ok': ('DCFCE7', '166534'), 'entrada': ('F1F5F9', '475569'), 'sem_legenda': ('F1F5F9', '475569')}


def _txt(v):
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _n(x):
    return f'{x:,}'.replace(',', '.')


def _acentos(s):
    """Os textos da regra vêm sem cedilha (ex.: "PEcAS", "REDUcAO"): só para a leitura na aba Auditoria."""
    s = re.sub(r'(?<=[A-ZÁÉÍÓÚÃÕÂÊÔ])c(?=[AÃOÕEÕ])', 'Ç', s)
    return s.replace('ÇAO', 'ÇÃO').replace('ÇOES', 'ÇÕES')


def ler(caminho):
    import openpyxl
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    for ws in wb.worksheets:
        linhas = ws.iter_rows(values_only=True)
        cab, mapa, pulo = None, None, 0
        for i, r in enumerate(linhas):
            nomes = [_txt(x).upper() for x in (r or ())]
            m = {CAMPOS[n]: j for j, n in enumerate(nomes) if n in CAMPOS}
            if all(k in m for k in OBRIGATORIOS):
                cab, mapa, pulo = nomes, m, i
                break
            if i >= 15:
                break
        if not mapa:
            continue
        itens = []
        for r in ws.iter_rows(min_row=pulo + 2, values_only=True):
            if not r or all(x is None or _txt(x) == '' for x in r):
                continue
            it = {k: _txt(r[j]) if j < len(r) else '' for k, j in mapa.items()}
            for k in CAMPOS.values():
                it.setdefault(k, '')
            itens.append(it)
        wb.close()
        return {'aba': ws.title, 'itens': itens}
    wb.close()
    raise ValueError('Formato não reconhecido: a planilha precisa das colunas NF, DESCRICAO, CST, CFOP e LEGENDA '
                     '(e, se houver, COD_ITEM, NCM e CONDICIONAL).')


def situacao(it):
    cfop = re.sub(r'\D', '', it['cfop'])
    if cfop[:1] in ('1', '2', '3'):
        return 'entrada'
    if it['cond']:
        return 'condicional'
    leg = it['leg'].upper().replace(' ', '')
    if not leg:
        return 'sem_legenda'
    fim = re.sub(r'\D', '', it['cst'])[-2:]
    st = fim in CST_ST
    if leg in ('S.T', 'ST', 'S.T.') and not st:
        return 'trib_indevido'
    if leg.startswith('TRIBUT') and st:
        return 'st_indevido'
    if leg.startswith('ISENT') and fim not in CST_ISENTO:
        return 'isento_div'
    return 'ok'


def titulo_padrao(nome_arquivo):
    base = os.path.splitext(os.path.basename(nome_arquivo))[0]
    base = re.sub(r'^\d{8,}_', '', base)                       # prefixo numérico de anexo
    per = ''
    m = re.search(r'(\d{2})(\d{4})$', base)
    if m and 1 <= int(m.group(1)) <= 12:
        per = f'{MESES[int(m.group(1)) - 1]}/{m.group(2)}'
        base = base[:m.start()]
    nome = re.sub(r'^(AUDIT|AUDITORIA)[_\s-]*', '', base, flags=re.I).replace('_', ' ').strip(' -')
    return ' · '.join(x for x in ('Auditoria de itens', nome, per) if x)


def analisar(caminho):
    d = ler(caminho)
    c = Counter(situacao(i) for i in d['itens'])
    return {'aba': d['aba'], 'itens': len(d['itens']), 'notas': len({i['nf'] for i in d['itens']}),
            'contagem': dict(c), 'titulo': titulo_padrao(caminho)}


def gerar(caminho, saida, titulo=''):
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.properties import Outline

    d = ler(caminho)
    itens = d['itens']
    for it in itens:
        it['sit'] = situacao(it)
    cont = Counter(it['sit'] for it in itens)
    titulo = titulo or titulo_padrao(caminho)
    n_notas = len({i['nf'] for i in itens})

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Auditoria'
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.outlinePr = Outline(summaryBelow=False)
    larg = [11, 12, 46, 11, 8, 10, 16, 27, 70]
    for i, w in enumerate(larg, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    NC = len(larg)
    F = lambda c: PatternFill('solid', start_color=c, end_color=c)
    fino = Side(style='thin', color='E5E7EB')
    borda = Border(bottom=fino)
    quebra = Alignment(wrap_text=True, vertical='top')
    meio = Alignment(vertical='center')

    def faixa(lin, texto, cor_fundo, cor_txt='FFFFFF', tam=11, neg=True, alt=None):
        ws.merge_cells(start_row=lin, start_column=1, end_row=lin, end_column=NC)
        cel = ws.cell(lin, 1, texto)
        cel.font = Font(bold=neg, color=cor_txt, size=tam)
        cel.alignment = Alignment(vertical='center', wrap_text=True, indent=1)
        for col in range(1, NC + 1):
            ws.cell(lin, col).fill = F(cor_fundo)
        if alt:
            ws.row_dimensions[lin].height = alt

    # ---- cabeçalho
    faixa(1, titulo, '14532D', tam=16, alt=30)
    faixa(2, f'Confere se o CST usado em cada item combina com o tratamento do produto (Tributado, Substituição Tributária ou Isento) · '
             f'{_n(len(itens))} itens em {_n(n_notas)} notas · gerado pelo FiscoCont+ em {datetime.now():%d/%m/%Y}',
          '166534', tam=10, neg=False, alt=20)

    # ---- resumo (com atalho para cada grupo)
    lin = 4
    ws.cell(lin, 1, 'Resumo').font = Font(bold=True, size=13, color='14532D')
    lin += 1
    for col in range(1, NC + 1):
        ws.cell(lin, col).fill = F('14532D')
    for col, t in ((1, 'Situação'), (4, 'O que significa'), (NC, 'Itens')):
        c = ws.cell(lin, col, t)
        c.font = Font(bold=True, color='FFFFFF')
    ws.merge_cells(start_row=lin, start_column=1, end_row=lin, end_column=3)
    ws.merge_cells(start_row=lin, start_column=4, end_row=lin, end_column=NC - 1)
    lin_resumo = lin + 1
    presentes = [g for g in GRUPOS if cont.get(g[0])]
    lin = lin_resumo + len(presentes) + 2
    pos = {}
    lin_ini_grupos = lin
    # posição de cada grupo (calculada antes para os atalhos)
    p = lin_ini_grupos
    for g in presentes:
        pos[g[0]] = p
        p += 3 + cont[g[0]] + 1                                  # título + explicação + cabeçalho + itens + linha em branco
    for k, g in enumerate(presentes):
        r = lin_resumo + k
        a = ws.cell(r, 1, g[1])
        a.hyperlink = f"#'Auditoria'!A{pos[g[0]]}"
        a.font = Font(bold=True, color='FFFFFF', underline='single'); a.alignment = Alignment(vertical='center', indent=1)
        for col in (1, 2, 3):
            ws.cell(r, col).fill = F(g[2])
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        b = ws.cell(r, 4, g[3]); b.alignment = Alignment(wrap_text=True, vertical='center'); b.font = Font(size=10, color='374151')
        ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=NC - 1)
        n = ws.cell(r, NC, cont[g[0]]); n.font = Font(bold=True, size=12); n.number_format = '#,##0'; n.alignment = Alignment(horizontal='left', vertical='center')
        ws.row_dimensions[r].height = 30
        for col in range(1, NC + 1):
            ws.cell(r, col).border = borda
    ws.cell(lin_resumo + len(presentes), 1, 'Clique na situação para ir direto ao grupo. Os grupos “Corretos” e “Entradas” vêm recolhidos: use o botão + à esquerda para abrir.').font = Font(italic=True, size=9, color='6B7280')

    # ---- grupos
    CAB = ['Nota', 'Código', 'Produto', 'NCM', 'CFOP', 'CST usado', 'Tratamento', 'Situação', 'O que fazer']
    lin = lin_ini_grupos
    for g in presentes:
        chave, tit, cor, expl, fazer, recolhido = g
        sel = sorted((i for i in itens if i['sit'] == chave), key=lambda i: (i['desc'], i['nf']))
        faixa(lin, f'{tit}   ·   {_n(len(sel))} {"item" if len(sel) == 1 else "itens"}', cor, tam=12, alt=24)
        ini = lin + 1
        faixa(lin + 1, expl, 'FFFBEB', cor_txt='713F12', tam=10, neg=False, alt=30)
        for col, t in enumerate(CAB, 1):
            c = ws.cell(lin + 2, col, t)
            c.font = Font(bold=True, color='FFFFFF'); c.fill = F('14532D'); c.alignment = meio
        fundo_rot, cor_rot = COR_ROT[chave]
        r = lin + 3
        for it in sel:
            fz = fazer or (('Regra: ' + _acentos(it['cond'])) if chave == 'condicional' else '')
            vals = [it['nf'], it['cod'] if it['cod'] != it['desc'] else '', it['desc'], it['ncm'], it['cfop'], it['cst'], it['leg'], ROTULO[chave], fz]
            for col, v in enumerate(vals, 1):
                c = ws.cell(r, col, v)
                c.border = borda
                if col == 9:
                    c.alignment = quebra; c.font = Font(size=9, color='4B5563')
                elif col == 8:
                    c.fill = F(fundo_rot); c.font = Font(bold=True, size=9, color=cor_rot); c.alignment = meio
                elif col == 6:
                    c.font = Font(bold=True)
            r += 1
        fim = r - 1
        if recolhido:
            for x in range(ini, fim + 1):
                ws.row_dimensions[x].outlineLevel = 1
                ws.row_dimensions[x].hidden = True
        else:
            for x in range(ini, fim + 1):
                ws.row_dimensions[x].outlineLevel = 1
        lin = fim + 2

    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True

    # ---- base original (dados como vieram)
    ob = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    for k, wo in enumerate(ob.worksheets):
        nome = 'Base original' if len(ob.worksheets) == 1 else f'Base · {wo.title}'[:31]
        wd = wb.create_sheet(nome)
        for row in wo.iter_rows(values_only=True):
            wd.append(list(row))
        if wd.max_row >= 1:
            for c in wd[1]:
                c.font = Font(bold=True, color='FFFFFF'); c.fill = F('14532D')
            wd.freeze_panes = 'A2'
            wd.auto_filter.ref = wd.dimensions
            for i in range(1, wd.max_column + 1):
                wd.column_dimensions[get_column_letter(i)].width = 14
            if wd.max_column >= 3:
                wd.column_dimensions['C'].width = 48
            if wd.max_column >= 8:
                wd.column_dimensions['H'].width = 60
    ob.close()

    tmp = saida + '.parcial.xlsx'
    wb.save(tmp)
    os.replace(tmp, saida)
    return {'saida': saida, 'itens': len(itens), 'notas': n_notas, 'contagem': dict(cont), 'titulo': titulo}


def saida_livre(original):
    base, _ = os.path.splitext(original)
    p = f'{base} - Profissional.xlsx'
    n = 2
    while os.path.exists(p):
        p = f'{base} - Profissional ({n}).xlsx'
        n += 1
    return p


if __name__ == '__main__':
    import sys
    print(json.dumps(gerar(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ''), ensure_ascii=False))

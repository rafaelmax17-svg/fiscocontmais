# -*- coding: utf-8 -*-
"""Adaptação de planilhas (só Admin) · Auditoria de itens (NF · COD_ITEM · DESCRICAO · NCM · CST · CFOP · LEGENDA · CONDICIONAL).

Gera um NOVO Excel no "Modelo 4" aprovado: a mesma planilha (mesmas colunas, mesma ordem, dados iguais) com título,
resumo, cabeçalho fixo com filtro, linhas zebradas, a tributação em etiqueta colorida e a coluna "Conferência" no fim
(✔ OK · ✖ CST divergente, com a linha em vermelho claro · ◆ Ver condição · Entrada). O original nunca é alterado.

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


CONF = {'ok': ('✔ OK', '15803D'), 'st_indevido': ('✖ CST divergente', 'B91C1C'), 'trib_indevido': ('✖ CST divergente', 'B91C1C'),
        'isento_div': ('✖ CST divergente', 'B91C1C'), 'condicional': ('◆ Ver condição', '4338CA'), 'entrada': ('Entrada', '64748B'),
        'sem_legenda': ('Sem legenda', '64748B')}
NOTA_DIV = {
    'st_indevido': 'Produto TRIBUTADO saiu com CST de substituição tributária: a venda deveria destacar o ICMS (CST 00, ou 20 com redução de base). Corrigir o cadastro do produto.',
    'trib_indevido': 'Produto com ICMS-ST saiu TRIBUTADO: o ICMS já foi pago antes; vender com CST 60 (61 nos combustíveis), sem destaque. Corrigir o cadastro do produto.',
    'isento_div': 'Produto ISENTO saiu com CST de produto tributado ou com ST: vender com CST 40 (ou 41). Corrigir o cadastro do produto.',
}
PILL = {'S.T': ('DBEAFE', '1E40AF'), 'TRIBUTADO': ('FFEDD5', '9A3412'), 'ISENTO': ('DCFCE7', '166534')}


def gerar(caminho, saida, titulo=''):
    """Modelo 4 (aprovado): a MESMA planilha (mesmas colunas, mesma ordem dos itens, dados iguais) com acabamento
    profissional + coluna "Conferência" no fim, que aponta o CST divergente (linha em vermelho claro)."""
    import openpyxl
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    d = ler(caminho)
    itens = d['itens']
    for it in itens:
        it['sit'] = situacao(it)
    cont = Counter(it['sit'] for it in itens)
    leg = Counter(it['leg'].upper().replace(' ', '') for it in itens)
    titulo = titulo or titulo_padrao(caminho)
    n_notas = len({i['nf'] for i in itens})
    n_cond = sum(1 for i in itens if i['cond'])
    n_div = cont['st_indevido'] + cont['trib_indevido'] + cont['isento_div']

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Relatório'
    ws.sheet_view.showGridLines = False
    CAB = ['Nota fiscal', 'Código do item', 'Descrição', 'NCM', 'CST', 'CFOP', 'Tributação', 'Condição especial', 'Conferência']
    larg = [13, 22, 50, 12, 7, 8, 13, 70, 19]
    NC = len(CAB)
    for k, w in enumerate(larg, 1):
        ws.column_dimensions[get_column_letter(k)].width = w
    F = lambda c: PatternFill('solid', start_color=c, end_color=c)
    linha = Border(bottom=Side(style='thin', color='E2E8F0'), right=Side(style='thin', color='EEF2F6'))
    meio = Alignment(vertical='center')

    # 1 · título
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=NC)
    c = ws.cell(1, 1, titulo)
    c.font = Font(bold=True, size=16, color='FFFFFF'); c.alignment = Alignment(vertical='center', indent=1)
    for k in range(1, NC + 1):
        ws.cell(1, k).fill = F('0F172A')
    ws.row_dimensions[1].height = 32
    # 2 · resumo
    resumo = (f'Resumo: {_n(len(itens))} itens · {_n(n_notas)} notas   |   S.T {_n(leg["S.T"] + leg["ST"])}  ·  '
              f'Tributado {_n(leg["TRIBUTADO"])}  ·  Isento {_n(leg["ISENTO"])}  ·  Com condição especial {_n(n_cond)}   |   '
              f'{_n(n_div)} {"item" if n_div == 1 else "itens"} com CST divergente   ·   gerado pelo FiscoCont+ em {datetime.now():%d/%m/%Y}')
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=NC)
    c = ws.cell(2, 1, resumo)
    c.font = Font(size=10.5, color='B91C1C' if n_div else '0F172A', bold=bool(n_div)); c.alignment = Alignment(vertical='center', indent=1)
    for k in range(1, NC + 1):
        ws.cell(2, k).fill = F('F1F5F9')
    ws.row_dimensions[2].height = 22
    # 3 · cabeçalho
    for k, t in enumerate(CAB, 1):
        c = ws.cell(3, k, t)
        c.font = Font(bold=True, color='FFFFFF'); c.fill = F('1E293B'); c.alignment = meio
    ws.row_dimensions[3].height = 22

    zebra, div = F('F8FAFC'), F('FEF2F2')
    pills = {k: (F(b), Font(bold=True, color=f, size=10)) for k, (b, f) in PILL.items()}
    f_cst, f_cond = Font(bold=True), Font(color='6B7280', size=10)
    r = 4
    for n, it in enumerate(itens):
        sit = it['sit']
        fundo = div if sit in NOTA_DIV else (zebra if n % 2 else None)
        vals = [it['nf'], it['cod'], it['desc'], it['ncm'], it['cst'], it['cfop'], it['leg'], it['cond']]
        for k, v in enumerate(vals, 1):
            c = ws.cell(r, k, v)
            c.border = linha
            if fundo:
                c.fill = fundo
        ws.cell(r, 5).font = f_cst
        ws.cell(r, 8).font = f_cond
        lg = it['leg'].upper().replace(' ', '')
        p = pills['S.T'] if lg in ('S.T', 'ST', 'S.T.') else pills['TRIBUTADO'] if lg.startswith('TRIBUT') else pills['ISENTO'] if lg.startswith('ISENT') else None
        if p:
            ws.cell(r, 7).fill, ws.cell(r, 7).font = p
            ws.cell(r, 7).alignment = Alignment(horizontal='center')
        t, cor = CONF[sit]
        c = ws.cell(r, 9, t)
        c.font = Font(bold=sit != 'entrada', color=cor); c.border = linha
        if fundo:
            c.fill = fundo
        if sit in NOTA_DIV:
            c.comment = Comment(NOTA_DIV[sit], 'FiscoCont+', width=320, height=110)
        elif sit == 'condicional':
            c.comment = Comment('O CST está certo só se a venda for para a finalidade da regra da coluna “Condição especial”.', 'FiscoCont+', width=300, height=80)
        r += 1
    ultima = r - 1

    ws.freeze_panes = 'A4'
    ws.auto_filter.ref = f'A3:{get_column_letter(NC)}{max(ultima, 3)}'
    ws.print_title_rows = '3:3'
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddFooter.center.text = 'Página &P de &N'

    tmp = saida + '.parcial.xlsx'
    wb.save(tmp)
    os.replace(tmp, saida)
    return {'saida': saida, 'itens': len(itens), 'notas': n_notas, 'contagem': dict(cont), 'titulo': titulo, 'divergentes': n_div}


SUFIXO = ' - OK'
_RE_GERADO = re.compile(r' - (OK|Profissional)( \(\d+\))?$', re.I)


def ja_gerada(caminho):
    """Planilha que o próprio módulo gerou (não entra de novo num lote)."""
    return bool(_RE_GERADO.search(os.path.splitext(os.path.basename(caminho))[0]))


def saida_livre(original):
    base, _ = os.path.splitext(original)
    p = f'{base}{SUFIXO}.xlsx'
    n = 2
    while os.path.exists(p):
        p = f'{base}{SUFIXO} ({n}).xlsx'
        n += 1
    return p


def analisar_lote(arquivos):
    out = []
    for a in arquivos:
        item = {'arquivo': a, 'nome': os.path.basename(a)}
        try:
            r = analisar(a)
            c = r['contagem']
            item.update(r, divergentes=c.get('st_indevido', 0) + c.get('trib_indevido', 0) + c.get('isento_div', 0))
        except Exception as e:
            item['erro'] = str(e)
        out.append(item)
    return out


def gerar_lote(entradas, progresso=None):
    out = []
    for i, ent in enumerate(entradas, 1):
        a = ent.get('arquivo', '')
        item = {'arquivo': a, 'nome': os.path.basename(a)}
        try:
            item.update(gerar(a, saida_livre(a), ent.get('titulo', '')))
        except Exception as e:
            item['erro'] = str(e)
        out.append(item)
        if progresso:
            try:
                with open(progresso, 'w', encoding='utf-8') as fh:
                    json.dump({'feitas': i, 'total': len(entradas), 'atual': os.path.basename(a)}, fh)
            except OSError:
                pass
    return out


if __name__ == '__main__':
    import sys
    print(json.dumps(gerar(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ''), ensure_ascii=False))

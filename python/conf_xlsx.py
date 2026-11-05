"""Conferência NF-e × SPED (entradas) em Excel, para enviar ao cliente: aba "Faltantes no SPED" (modelo da equipe:
Situação · Data · NF-e · Fornecedor · Chave de acesso · Valor XML) e aba "Divergência de valor" (Valor XML × Valor SPED).

CLI: python fiscal_core.py conf-xlsx --entrada conferencia.json --saida arquivo.xlsx --json resultado.json
"""
import json
import sys

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font as _Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

NAVY, AMARELO, OURO, LARANJA, CINZA, LINHA, ZEBRA, TINTA = '1F2A5A', 'FFE7A3', 'E0B84C', 'C2410C', '5A6785', 'E5E9F1', 'F7F8FC', '243056'
MOEDA = '"R$" #,##0.00;[Red]-"R$" #,##0.00'
MOEDA_TOTAL = '"R$" #,##0.00;-"R$" #,##0.00'
COR_SIT = {'Faltante': 'E23D4C', 'Divergente': 'D4711A'}
_fino = Side(style='thin', color=LINHA)


def Font(**k):
    k.setdefault('name', 'Calibri')
    return _Font(**k)


def _cnpj(c):
    c = ''.join(ch for ch in str(c or '') if ch.isdigit())
    return f'{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}' if len(c) == 14 else c


def _ordem_data(d):
    d = str(d or '')
    return (d[6:10] + d[3:5] + d[0:2]) if len(d) == 10 else d


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return str(v or '')


def _cabecalho(ws, emp, titulo, sub, ncol):
    ws.sheet_view.showGridLines = False
    ult = get_column_letter(ncol)
    ws.merge_cells(f'A1:{ult}1')
    c = ws['A1']
    c.value = titulo
    c.font = Font(bold=True, size=15, color='FFFFFF')
    c.fill = PatternFill('solid', fgColor=NAVY)
    c.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 34
    ws.merge_cells(f'A2:{ult}2')
    c = ws['A2']
    partes = [f"CONTRIBUINTE: {emp.get('empresa', '')}"]
    if emp.get('cnpj'):
        partes.append(f"CNPJ: {_cnpj(emp.get('cnpj'))}")
    if emp.get('periodo') and emp.get('periodo').strip() != 'a':
        partes.append(f"PERÍODO: {emp.get('periodo')}")
    c.value = '     ·     '.join(partes)
    c.font = Font(bold=True, size=10.5, color=NAVY)
    c.fill = PatternFill('solid', fgColor='EEF1F7')
    c.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[2].height = 22
    ws.merge_cells(f'A3:{ult}3')
    c = ws['A3']
    c.value = sub
    c.font = Font(italic=True, size=9.5, color=CINZA)
    c.alignment = Alignment(horizontal='center')


def _tabela(ws, cab, larguras, linhas, moeda, totais, linha0=5):
    centro = {'DATA', 'NF-e'}
    for i, (h, w) in enumerate(zip(cab, larguras), 1):
        c = ws.cell(linha0, i, h)
        c.font = Font(bold=True, size=11, color=LARANJA)
        c.fill = PatternFill('solid', fgColor=AMARELO)
        c.border = Border(bottom=Side(style='medium', color=OURO))
        c.alignment = Alignment(vertical='center', horizontal='center' if h in centro else ('right' if i in moeda else 'left'))
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[linha0].height = 24
    r = linha0
    for ln in linhas:
        r += 1
        for i, v in enumerate(ln, 1):
            c = ws.cell(r, i, v)
            c.font = Font(size=10.5, color=TINTA)
            c.border = Border(bottom=_fino)
            c.alignment = Alignment(vertical='center')
            h = cab[i - 1]
            if i in moeda:
                c.number_format = MOEDA
                c.alignment = Alignment(horizontal='right', vertical='center')
            elif h.startswith('CHAVE'):
                c.number_format = '@'                       # 44 dígitos como texto: o Excel não corta nem vira notação científica
                c.font = Font(name='Consolas', size=9.5, color=CINZA)
            elif h in centro:
                c.alignment = Alignment(horizontal='center', vertical='center')
        sit = ws.cell(r, 1)
        sit.font = Font(bold=True, size=10.5, color=COR_SIT.get(sit.value, TINTA))
        ws.row_dimensions[r].height = 19
    ult = get_column_letter(len(cab))
    if r > linha0:
        ws.conditional_formatting.add(f'A{linha0 + 1}:{ult}{r}', FormulaRule(formula=['MOD(ROW(),2)=0'], fill=PatternFill('solid', fgColor=ZEBRA, bgColor=ZEBRA)))
        ws.auto_filter.ref = f'A{linha0}:{ult}{r}'
    else:
        r += 1
        ws.merge_cells(f'A{r}:{ult}{r}')
        c = ws.cell(r, 1, 'Nenhuma nota nesta situação no período.')
        c.font = Font(italic=True, size=10.5, color='0EA472')
        c.alignment = Alignment(horizontal='center')
    r += 1
    c = ws.cell(r, 1, f'TOTAL · {len(linhas)} nota(s)')
    c.font = Font(bold=True, color='FFFFFF')
    for i in range(1, len(cab) + 1):
        ws.cell(r, i).fill = PatternFill('solid', fgColor=NAVY)
    for col in totais:
        L = get_column_letter(col)
        c = ws.cell(r, col, f'=SUM({L}{linha0 + 1}:{L}{r - 1})' if linhas else 0)
        c.number_format = MOEDA_TOTAL
        c.font = Font(bold=True, color='FFFFFF')
        c.alignment = Alignment(horizontal='right')
    ws.row_dimensions[r].height = 22
    ws.freeze_panes = f'A{linha0 + 1}'
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins = PageMargins(left=.4, right=.4, top=.5, bottom=.5)
    ws.print_title_rows = f'{linha0}:{linha0}'
    ws.oddFooter.center.text = 'Liddera | Inteligência em Negócios · página &P de &N'


def gerar(cf, destino):
    emp = cf.get('empresa') or {}
    wb = Workbook()
    ws = wb.active
    ws.title = 'Faltantes no SPED'
    _cabecalho(ws, emp, 'COMPARATIVO SPED FISCAL VS. XML · NOTAS DE ENTRADA FALTANTES',
               'XMLs de entrada que não foram encontrados no SPED Fiscal do período', 6)
    fal = sorted(cf.get('faltantes') or [], key=lambda x: (_ordem_data(x.get('data')), str(_int(x.get('nnf'))).zfill(12)))
    _tabela(ws, ['SITUAÇÃO', 'DATA', 'NF-e', 'FORNECEDOR', 'CHAVE DE ACESSO (44 DÍGITOS)', 'VALOR XML'], [13, 12, 11, 58, 50, 16],
            [['Faltante', x.get('data', ''), _int(x.get('nnf')), x.get('fornecedor', ''), x.get('chave', ''), round(float(x.get('vnf') or 0), 2)] for x in fal],
            moeda={6}, totais=[6])
    ws = wb.create_sheet('Divergência de valor')
    _cabecalho(ws, emp, 'COMPARATIVO SPED FISCAL VS. XML · DIVERGÊNCIA DE VALOR',
               'Notas encontradas no SPED Fiscal com valor diferente do XML', 8)
    dv = sorted(cf.get('divergencias') or [], key=lambda x: (_ordem_data(x.get('data')), str(_int(x.get('nnf'))).zfill(12)))
    _tabela(ws, ['SITUAÇÃO', 'DATA', 'NF-e', 'FORNECEDOR', 'CHAVE DE ACESSO (44 DÍGITOS)', 'VALOR XML', 'VALOR SPED', 'DIFERENÇA'],
            [13, 12, 11, 50, 50, 15, 15, 15],
            [['Divergente', x.get('data', ''), _int(x.get('nnf')), x.get('fornecedor', ''), x.get('chave', ''),
              round(float(x.get('vnf') or 0), 2), round(float(x.get('vl_sped') or 0), 2),
              round(float(x.get('vnf') or 0) - float(x.get('vl_sped') or 0), 2)] for x in dv],
            moeda={6, 7, 8}, totais=[6, 7, 8])
    wb.active = 0
    wb.save(destino)
    return {'ok': True, 'faltantes': len(fal), 'divergencias': len(dv), 'arquivo': destino}


def main_cli(argv):
    def opt(n, d=None):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else d
    try:
        cf = json.load(open(opt('--entrada'), encoding='utf-8'))
        res = gerar(cf, opt('--saida'))
    except Exception as e:      # noqa: BLE001 — o erro vai para a tela em texto simples
        res = {'erro': f'Não consegui gerar o Excel: {e}'}
    if opt('--json'):
        with open(opt('--json'), 'w', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False)
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main_cli(sys.argv[1:]))

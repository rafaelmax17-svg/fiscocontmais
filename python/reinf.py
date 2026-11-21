"""Conferência da EFD-Reinf (2.4.6) — leitura dos XMLs baixados do eCAC e a lista em Excel.

Eventos lidos (leiaute 2.01.x, sem depender do namespace):
  • R-4010 (pagamento a pessoa física), R-4020 (pagamento a pessoa jurídica): beneficiário, natureza do rendimento, data do
    fato gerador, valor bruto e as retenções (IR, CSLL, Cofins, PIS/Pasep e a retenção agregada).
  • R-2010 (serviços tomados com cessão de mão de obra): prestador, valor bruto e a retenção do INSS.
  • Totalizadores (R-9005, R-9015, R-9001, R-9011): recibo, data de processamento e os valores por código de receita.

Modos (python fiscal_core.py ...):
  reinf-xml   --xml <arquivo> [--xml ...] --json <saida>       lê os XMLs e devolve uma lista de eventos
  reinf-lista --entrada <json> --xlsx <saida>                  lista de todas as empresas (retenção separada) em Excel
"""
import json
import re
import sys

TAGS_RET = {
    'irrf': ('vlrIR',), 'csll': ('vlrCSLL',), 'cofins': ('vlrCofins', 'vlrCOFINS'), 'pis': ('vlrPP', 'vlrPIS'),
    'agreg': ('vlrAgreg',),
}


def _num(v):
    s = str(v or '').strip()
    if not s:
        return 0.0
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0


def _sem_ns(xml):
    xml = re.sub(r'<\?xml[^>]*\?>', '', xml)
    xml = re.sub(r'<(/?)[\w.-]+:', r'<\1', xml)
    return re.sub(r'\sxmlns(:\w+)?="[^"]*"', '', xml)


def _txt(xml, tag):
    m = re.search(rf'<{tag}\b[^>]*>([^<]*)</{tag}>', xml)
    return m.group(1).strip() if m else ''


def _todos(xml, tag):
    return [m.group(1).strip() for m in re.finditer(rf'<{tag}\b[^>]*>([^<]*)</{tag}>', xml)]


def _blocos(xml, tag):
    return [m.group(0) for m in re.finditer(rf'<{tag}\b[^>]*>.*?</{tag}>', xml, re.S)]


def _soma(xml, tags):
    return round(sum(_num(v) for t in tags for v in _todos(xml, t)), 2)


def ler_evento(xml):
    """Um XML do eCAC → dict com o evento (ou None se não reconhecer)."""
    x = _sem_ns(xml)
    ind = _txt(x, 'indRetif')
    base = {'tipo': 'Retificador' if ind == '2' else 'Original', 'id': (re.search(r'\b[iI]d="([^"]+)"', x) or [None, ''])[1],
            'perApur': _txt(x, 'perApur'), 'reciboOrig': _txt(x, 'nrRecibo')}
    if re.search(r'<evtRetPJ\b', x) or re.search(r'<evtRetPF\b', x):
        pj = bool(re.search(r'<evtRetPJ\b', x))
        benef = _txt(x, 'cnpjBenef') or _txt(x, 'cpfBenef') or _txt(x, 'nmBenef')
        pgs = []
        for nat in _blocos(x, 'idePgto'):
            nr = _txt(nat, 'natRend')
            for p in _blocos(nat, 'infoPgto'):
                r = {k: _soma(p, t) for k, t in TAGS_RET.items()}
                bruto = _soma(p, ('vlrBruto', 'vlrRendBruto'))
                pgs.append({'natRend': nr, 'dtFG': _txt(p, 'dtFG'), 'bruto': bruto, **r})
        tot = {k: round(sum(p[k] for p in pgs), 2) for k in [*TAGS_RET, 'bruto']}
        return {**base, 'evento': 'R-4020' if pj else 'R-4010', 'benef': benef, 'pagamentos': pgs,
                'natRend': sorted({p['natRend'] for p in pgs if p['natRend']}), **tot, 'inss': 0.0}
    if re.search(r'<evtServTom\b', x):
        prest = []
        for b in _blocos(x, 'idePrestServ'):
            prest.append({'cnpj': _txt(b, 'cnpjPrestador'), 'bruto': _num(_txt(b, 'vlrTotalBruto')),
                          'inss': _num(_txt(b, 'vlrTotalRetPrinc')) + _num(_txt(b, 'vlrTotalRetAdic'))})
        return {**base, 'evento': 'R-2010', 'benef': ', '.join(p['cnpj'] for p in prest if p['cnpj']), 'prestadores': prest,
                'bruto': round(sum(p['bruto'] for p in prest), 2), 'inss': round(sum(p['inss'] for p in prest), 2),
                **{k: 0.0 for k in TAGS_RET}, 'natRend': []}
    if re.search(r'<(evtRet|evtTotal|evtTotalContrib|evtRetCons|evtFech)\w*\b', x) or _blocos(x, 'totApurMen') or _blocos(x, 'RTom'):
        cods = []
        for b in re.findall(r'<(totApur\w+)\b[^>]*>(.*?)</\1>', x, re.S):
            cod = _txt(b[1], 'CRMen') or _txt(b[1], 'CRQui') or _txt(b[1], 'CRDec') or _txt(b[1], 'CRSem') or _txt(b[1], 'CRDia') or \
                (re.search(r'<CR\w*>(\d{6})</CR\w*>', b[1]) or [None, ''])[1]
            vals = {t: _num(v) for t, v in re.findall(r'<(vlrCR\w+)>([^<]*)</vlrCR\w+>', b[1])}
            calc = next((v for t, v in vals.items() if t.endswith('Calc') and 'Susp' not in t), None)
            inf = next((v for t, v in vals.items() if t.endswith('Inf') and 'Susp' not in t), None)
            cods.append({'natRend': _txt(b[1], 'natRend'), 'cod': cod, 'valor': round(calc if calc is not None else (inf or 0), 2),
                         'suspenso': round(sum(v for t, v in vals.items() if 'Susp' in t), 2)})
        # R-9001/R-9011 (série R-2000): totais por código de receita das contribuições previdenciárias
        for b in _blocos(x, 'RTom') + _blocos(x, 'infoTotalContrib'):
            for cr in re.findall(r'<(?:infoCRTom|RCPRB|RRecRepAD|RComl|RAquis)\b[^>]*>(.*?)</(?:infoCRTom|RCPRB|RRecRepAD|RComl|RAquis)>', b, re.S):
                cod = _txt(cr, 'CRTom') or _txt(cr, 'CRCPRB') or _txt(cr, 'CRRecRepAD') or _txt(cr, 'CRComl') or _txt(cr, 'CRAquis')
                v = _num(_txt(cr, 'vlrCRTom') or _txt(cr, 'vlrCRCPRB') or _txt(cr, 'vlrCRRecRepAD') or _txt(cr, 'vlrCRComl') or _txt(cr, 'vlrCRAquis'))
                if cod:
                    cods.append({'natRend': '', 'cod': cod, 'valor': round(v, 2), 'suspenso': 0.0})
        return {**base, 'evento': 'totalizador', 'recibo': _txt(x, 'nrRecArqBase') or _txt(x, 'nrRecibo') or _txt(x, 'nrProtEntr'),
                'dhProcess': _txt(x, 'dhProcess') or _txt(x, 'dhRecepcao'), 'codigos': cods}
    return None


# códigos de receita da série R-4000: CSRF (CSLL, PIS, Cofins ou agregada); os demais são de IRRF
def imposto_do_codigo(cod, serie='4000'):
    c = re.sub(r'\D', '', str(cod or ''))[:4]
    if serie == '2000':
        return 'inss'
    return {'6228': 'csll', '5987': 'csll', '6230': 'pis', '5979': 'pis', '6243': 'cofins', '5960': 'cofins', '5952': 'agreg'}.get(c, 'irrf')


def lista_xlsx(dados, saida):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = 'EFD-Reinf'
    comp = dados.get('comp', '')
    ws['A1'] = f"EFD-Reinf · retenções por empresa · competência {comp[5:7]}/{comp[:4]}" if comp else 'EFD-Reinf · retenções por empresa'
    ws['A1'].font = Font(bold=True, size=14, color='1E2A78')
    ws['A2'] = dados.get('sub', '')
    ws['A2'].font = Font(color='64748B', size=10)
    cab = ['Empresa', 'CNPJ', 'IRRF', 'CSLL', 'Cofins', 'PIS/Pasep', 'Agregada (CSRF)', 'INSS (R-2010)', 'Funrural (R-2055)', 'Total', 'Eventos',
           'Situação', 'Recibo de envio', 'Enviado em']
    ws.append([])
    ws.append(cab)
    fino = Side(style='thin', color='E2E8F0')
    for i, _ in enumerate(cab, 1):
        c = ws.cell(row=4, column=i)
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor='1E2A78')
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ks = ['irrf', 'csll', 'cofins', 'pis', 'agreg', 'inss', 'funrural']
    tot = {k: 0.0 for k in ks}
    for e in dados.get('empresas', []):
        t = e.get('totais') or {}
        linha = [e.get('nome', ''), e.get('cnpjFmt', e.get('cnpj', ''))] + [round(t.get(k, 0) or 0, 2) for k in ks] + \
            [round(sum(t.get(k, 0) or 0 for k in ks), 2), e.get('nEventos', 0), e.get('situacao', ''), e.get('recibo', ''), e.get('enviado', '')]
        ws.append(linha)
        for k in ks:
            tot[k] += t.get(k, 0) or 0
    ws.append(['Total', ''] + [round(tot[k], 2) for k in ks] + [round(sum(tot.values()), 2), '', '', '', ''])
    ult = ws.max_row
    for r in range(5, ult + 1):
        for cidx in range(1, len(cab) + 1):
            c = ws.cell(row=r, column=cidx)
            c.border = Border(bottom=fino)
            if 3 <= cidx <= 10:
                c.number_format = '#,##0.00'
        if r == ult:
            for cidx in range(1, len(cab) + 1):
                ws.cell(row=r, column=cidx).font = Font(bold=True)
                ws.cell(row=r, column=cidx).fill = PatternFill('solid', fgColor='F1F5F9')
    larg = [44, 20, 13, 12, 12, 12, 15, 14, 15, 14, 9, 24, 34, 17]
    for i, w in enumerate(larg, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'C5'
    # eventos (uma linha por evento, com o recibo)
    ev = wb.create_sheet('Eventos')
    ce = ['Empresa', 'CNPJ', 'Evento', 'Beneficiário / prestador', 'Natureza', 'Valor bruto', 'IRRF', 'CSLL', 'Cofins', 'PIS/Pasep',
          'Agregada', 'INSS', 'Tipo', 'Recibo', 'Recepção']
    ev.append(ce)
    for i, _ in enumerate(ce, 1):
        c = ev.cell(row=1, column=i)
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor='1E2A78')
    for e in dados.get('empresas', []):
        for x in e.get('eventos', []):
            ev.append([e.get('nome', ''), e.get('cnpjFmt', ''), x.get('evento', ''), x.get('benef', ''), ', '.join(x.get('natRend') or []),
                       x.get('bruto', 0), x.get('irrf', 0), x.get('csll', 0), x.get('cofins', 0), x.get('pis', 0), x.get('agreg', 0),
                       x.get('inss', 0), x.get('tipo', ''), x.get('recibo', ''), x.get('recepcao', '')])
    for r in range(2, ev.max_row + 1):
        for cidx in range(6, 13):
            ev.cell(row=r, column=cidx).number_format = '#,##0.00'
    for i, w in enumerate([40, 20, 9, 26, 14, 14, 12, 11, 11, 11, 11, 11, 12, 34, 17], 1):
        ev.column_dimensions[get_column_letter(i)].width = w
    ev.freeze_panes = 'A2'
    wb.save(saida)
    return {'ok': True, 'arquivo': saida}


def main_cli(argv):
    def opt(n, d=None):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else d
    saida = opt('--json')
    try:
        modo = argv[0] if argv else ''
        if modo == 'xml':
            arqs = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == '--xml']
            out = []
            for a in arqs:
                try:
                    with open(a, encoding='utf-8', errors='replace') as fh:
                        out.append({'arquivo': a, **(ler_evento(fh.read()) or {'evento': ''})})
                except OSError as e:
                    out.append({'arquivo': a, 'erro': str(e)})
            r = {'ok': True, 'eventos': out}
        elif modo == 'lista':
            with open(opt('--entrada'), encoding='utf-8') as fh:
                dados = json.load(fh)
            r = lista_xlsx(dados, opt('--xlsx'))
        else:
            r = {'erro': 'modo desconhecido'}
    except Exception as e:  # noqa: BLE001
        r = {'erro': f'{type(e).__name__}: {e}'}
    if saida:
        with open(saida, 'w', encoding='utf-8') as fh:
            json.dump(r, fh, ensure_ascii=False)
    else:
        print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main_cli(sys.argv[1:]))

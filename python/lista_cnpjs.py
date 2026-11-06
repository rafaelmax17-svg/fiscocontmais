"""Lê uma lista de empresas com CNPJ (relatório "Cadastro de Empresas" do Domínio em PDF, ou planilha / CSV / TXT)
para o Fechamento do Simples preencher o CNPJ das empresas já cadastradas.

Saída: {'ok': True, 'empresas': [{'codigo', 'nome', 'cnpj'}], 'ignoradas': n}  — só CNPJ (CPF e CAEPF ficam de fora).
CLI: python fiscal_core.py lista-cnpjs --entrada arquivo --json resultado.json
"""
import csv
import json
import os
import re
import sys

RE_DOMINIO = re.compile(r'Empresa:\s*(\d+)\s*-\s*(.+?)\s+(CNPJ|CPF|CAEPF|CEI):\s*([\d./-]+)')
RE_CNPJ = re.compile(r'(?<!\d)(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?!\d)')


def _so_dig(s):
    return re.sub(r'\D', '', str(s or ''))


def _cnpj_valido(c):
    if len(c) != 14 or len(set(c)) == 1:
        return False
    def dv(base, pesos):
        s = sum(int(a) * b for a, b in zip(base, pesos)) % 11
        return '0' if s < 2 else str(11 - s)
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = dv(c[:12], p1)
    d2 = dv(c[:12] + d1, [6] + p1)
    return c[12:] == d1 + d2


def _de_texto(linhas):
    out, ign = [], 0
    for ln in linhas:
        m = RE_DOMINIO.search(ln)
        if m:
            if m.group(3) != 'CNPJ':
                ign += 1
                continue
            c = _so_dig(m.group(4))
            if _cnpj_valido(c):
                out.append({'codigo': m.group(1), 'nome': m.group(2).strip(), 'cnpj': c})
            continue
    return out, ign


def _de_linhas_soltas(linhas):
    """Planilha / CSV / TXT: em cada linha, um CNPJ e o maior texto como razão social."""
    out = []
    for cols in linhas:
        cols = [str(x or '').strip() for x in cols]
        cnpj = next((_so_dig(m.group(1)) for x in cols for m in [RE_CNPJ.search(x)] if m), '')
        if not _cnpj_valido(cnpj):
            continue
        textos = [x for x in cols if re.search(r'[A-Za-zÀ-ú]{3}', x) and not RE_CNPJ.search(x)]
        if textos:
            out.append({'codigo': '', 'nome': max(textos, key=len), 'cnpj': cnpj})
    return out


def ler(caminho):
    ext = os.path.splitext(caminho)[1].lower()
    if ext == '.pdf':
        import pdfplumber
        linhas = []
        with pdfplumber.open(caminho) as pdf:
            for pg in pdf.pages:
                linhas += (pg.extract_text(layout=True) or '').splitlines()
        emp, ign = _de_texto(linhas)
        if not emp:
            emp = _de_linhas_soltas([[x] for x in linhas])
    elif ext in ('.xlsx', '.xlsm'):
        from openpyxl import load_workbook
        wb = load_workbook(caminho, read_only=True, data_only=True)
        rows = [list(r) for ws in wb.worksheets for r in ws.iter_rows(values_only=True)]
        emp, ign = _de_linhas_soltas(rows), 0
    else:
        bruto = open(caminho, 'rb').read()
        try:
            txt = bruto.decode('utf-8')
        except UnicodeDecodeError:
            txt = bruto.decode('latin-1')
        emp, ign = _de_texto(txt.splitlines())
        if not emp:
            sep = ';' if txt.count(';') > txt.count(',') else ','
            emp = _de_linhas_soltas(list(csv.reader(txt.splitlines(), delimiter=sep)))
    vistos, unicas = set(), []
    for e in emp:
        if e['cnpj'] not in vistos:
            vistos.add(e['cnpj'])
            unicas.append(e)
    return {'ok': True, 'empresas': unicas, 'ignoradas': ign}


def main_cli(argv):
    def opt(n, d=None):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else d
    try:
        res = ler(opt('--entrada'))
        if not res['empresas']:
            res = {'ok': False, 'erro': 'Não encontrei nenhum CNPJ com razão social nesse arquivo.'}
    except Exception as e:      # noqa: BLE001
        res = {'ok': False, 'erro': f'Não consegui ler o arquivo: {e}'}
    with open(opt('--json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False)
    return 0 if res.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main_cli(sys.argv[1:]))

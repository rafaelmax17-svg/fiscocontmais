# -*- coding: utf-8 -*-
"""Consulta de NCM (menu Fiscal, toda a equipe): descrição oficial, PIS/COFINS e IBS/CBS.

Fontes:
  • Descrição: tabela NCM do Classif (Portal Único Siscomex), arquivo JSON público baixado pelo sistema
    (https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json?perfil=PUBLICO).
  • PIS/COFINS: tabelas oficiais da EFD-Contribuições (efd_tabelas_natureza_dados): 4.3.10 (monofásico / bebidas frias),
    4.3.12 (substituição tributária, CST 05), 4.3.13 (alíquota zero, CST 06), 4.3.14 (isenção, CST 07),
    4.3.15 (sem incidência, CST 08), 4.3.16 (suspensão, CST 09) — só itens vigentes na data da consulta.
    Sem enquadramento: tributação básica (CST 01) — cumulativo 0,65% / 3% (Lei 9.718/1998) ou não cumulativo
    1,65% / 7,6% (Leis 10.637/2002 e 10.833/2003).
  • IBS/CBS: reduções da LC 214/2025 por NCM (beneficios_rtc) e alíquotas de teste de 2026 (CBS 0,9% e IBS 0,1%).
  • A partir de 01/01/2027 o PIS e a COFINS deixam de existir e passa a valer a CBS (LC 214/2025); de 24/12/2026 em
    diante a consulta já avisa.
"""
import json
import re
import unicodedata
from datetime import date

import beneficios_rtc as brt
import efd_tabelas_natureza_dados as tn

FIM_PIS = date(2027, 1, 1)
AVISO_DESDE = date(2026, 12, 24)          # 8 dias antes

CST_TAB = {'4.3.10': '02 (fabricante/importador) · 04 (revenda)', '4.3.12': '05', '4.3.13': '06', '4.3.14': '07',
           '4.3.15': '08', '4.3.16': '09'}
ROT_TAB = {'4.3.10': 'Incidência monofásica', '4.3.12': 'Substituição tributária', '4.3.13': 'Alíquota zero',
           '4.3.14': 'Isenção', '4.3.15': 'Sem incidência', '4.3.16': 'Suspensão'}
NAT_REVENDA = {'1': '001 (combustíveis)', '2': '002 (fármacos e perfumaria)', '3': '003 (veículos, máquinas e autopeças)', '4': '004 (bebidas frias)'}

RX_COD = re.compile(r'(?<![\d.])(\d{2}\.\d{2}(?:\.\d{1,2}){0,2}|\d{4}(?:\.\d{1,2}){1,2}|\d{8})(?![\d])')
RX_FAIXA = re.compile(r'(\d{2}\.\d{2})\s+a\s+(\d{2}\.\d{2})')
RX_CAP = re.compile(r'Cap[ií]tulos?\s+(\d{1,2}(?:\s*(?:,|e|a)\s*\d{1,2})*)', re.I)


def _so(s):
    return re.sub(r'\D', '', str(s or ''))


def _sem_acento(s):
    return ''.join(c for c in unicodedata.normalize('NFD', str(s or '')) if unicodedata.category(c) != 'Mn').upper()


def fmt_ncm(n):
    n = _so(n)
    if len(n) == 8:
        return f'{n[:4]}.{n[4:6]}.{n[6:]}'
    if len(n) == 6:
        return f'{n[:4]}.{n[4:]}'
    if len(n) == 4:
        return f'{n[:2]}.{n[2:]}'
    return n


def _dt(s, fim=False):
    s = (s or '').strip()
    m = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', s)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.match(r'^(\d{2})/(\d{4})$', s)
    if m:
        a, mm = int(m.group(2)), int(m.group(1))
        import calendar
        return date(a, mm, calendar.monthrange(a, mm)[1] if fim else 1)
    return None


# ------------------------------------------------------------------ PIS/COFINS: regras das tabelas oficiais
def _regras_item(it):
    """[(prefixo, exceto:set, condicao)] a partir dos códigos citados no item da tabela."""
    n, d = it.get('n') or '', it.get('d') or ''
    regras = []
    # a descrição só vale quando é o próprio produto ("Sabões de toucador classificados no código ..."); quando fala de
    # venda, receita, serviço ou programa, os códigos citados são contexto e não o enquadramento do NCM
    d_ok = not re.match(r'\s*(venda|vendas|receita|receitas|valores|opera[cç]|importa[cç]|presta[cç]|servi[cç]|programa|patvd|aquisi[cç]|bens|mercadorias)', d, re.I)
    for texto, de_desc in ((n, False), (d if d_ok else '', True)):
        if not texto:
            continue
        excl = set()
        for m in re.finditer(r'exceto([^);]*)', texto, re.I):
            excl.update(_so(c) for c in RX_COD.findall(m.group(1)))
        for m in RX_FAIXA.finditer(texto):
            a, b = int(_so(m.group(1))), int(_so(m.group(2)))
            if a < b and b - a < 50:
                regras += [(str(x).zfill(4), excl, '') for x in range(a, b + 1)]
        if not de_desc:
            for m in RX_CAP.finditer(texto):
                for c in re.findall(r'\d{1,2}', m.group(1)):
                    regras.append((c.zfill(2), excl, ''))
        for m in RX_COD.finditer(texto):
            c = _so(m.group(1))
            if c in excl:
                continue
            cauda = texto[m.end():m.end() + 10]
            ex = re.match(r'\s*Ex\.?\s*(\d+)', cauda, re.I)
            regras.append((c, excl, f'só o Ex {ex.group(1)} da TIPI' if ex else ''))
        if regras and not de_desc:
            break                                  # o campo de NCM manda; a descrição só entra quando ele está vazio
    return regras


# Na Tabela 4.3.10 o mesmo código aparece em várias linhas, uma por período de alíquota; o arquivo gerado guardou o fim
# do primeiro período. Fármacos e perfumaria (Lei 10.147/2000) e veículos, autopeças e pneus (Lei 10.485/2002) seguem
# monofásicos até a extinção do PIS e da COFINS: esses códigos não "vencem" pela data da linha.
_SEM_FIM = {('4.3.10', c) for c in ('201', '202', '301', '302', '303', '304')}


def _vigente(it, hoje, chave=None):
    i, t = _dt(it.get('i')), (None if chave in _SEM_FIM else _dt(it.get('t'), fim=True))
    return (i is None or i <= hoje) and (t is None or t >= hoje)


def pis_cofins(ncm, hoje):
    n = _so(ncm)
    achados = []
    for tab, v in tn.TABELAS.items():
        for cod, it in v['itens'].items():
            if not _vigente(it, hoje, (tab, cod)):
                continue
            melhor = None
            for pre, excl, cond in _regras_item(it):
                if pre and n.startswith(pre) and not any(n.startswith(x) for x in excl if x):
                    if melhor is None or len(pre) > len(melhor[0]):
                        melhor = (pre, cond)
            if melhor:
                achados.append({'tabela': tab, 'codigo': cod, 'regime': ROT_TAB[tab], 'cst': CST_TAB[tab], 'descricao': it['d'],
                                'ncm_tabela': it.get('n') or '', 'desde': it.get('i') or '', 'ate': it.get('t') or '',
                                'condicao': melhor[1] + ('; ' if melhor[1] else '') + ('depende do destino/condição do item' if tab == '4.3.16' else ''),
                                'natureza_revenda': NAT_REVENDA.get(cod[:1]) if tab == '4.3.10' else ''})
    # monofásico da Lei 10.147/2000 (fármacos e perfumaria) e da Lei 10.485/2002 (pneus): as mesmas regras do detector de
    # monofásico do sistema (oportunidades.REGRAS_MONOFASICO), que seguem a Tabela 4.3.10
    try:
        from oportunidades import _regra_ncm
        r = _regra_ncm(n)
    except Exception:
        r = None
    if r and r['confianca'] != 'Baixa' and not any(a['tabela'] == '4.3.10' for a in achados):
        cod = r['tabela'].split('/')[0]
        achados.append({'tabela': '4.3.10', 'codigo': r['tabela'], 'regime': ROT_TAB['4.3.10'], 'cst': CST_TAB['4.3.10'],
                        'descricao': f"{r['grupo']} — {r['lei']}", 'ncm_tabela': r['obs'], 'desde': '', 'ate': '',
                        'condicao': '', 'natureza_revenda': NAT_REVENDA.get(cod[:1], '')})
    achados.sort(key=lambda a: ('4.3.10', '4.3.12', '4.3.13', '4.3.14', '4.3.15', '4.3.16').index(a['tabela']))
    out = {'achados': achados, 'basica': not achados,
           'aviso_sem_ncm': (not achados and n[:2].isdigit() and 1 <= int(n[:2]) <= 24)}
    return out


# ------------------------------------------------------------------ IBS/CBS
def ibs_cbs(ncm, hoje, desc=''):
    b = brt.classifica(ncm, desc)
    red = float(b['red']) if b else 0.0
    out = {'reducao': red, 'cst': '200' if b else '000', 'cclasstrib': b['cclass'] if b else '000001',
           'enquadramento': b['nome'] if b else 'Tributação integral (sem redução pelo NCM)',
           'lei': b['lei'] if b else 'LC 214/2025 (regra geral)', 'condicao': (b or {}).get('cond') or '', 'certo': (b or {}).get('certo', True)}
    if hoje.year == 2026:
        f = (100 - red) / 100
        out['ano_teste'] = {'cbs': round(0.9 * f, 4), 'ibs': round(0.1 * f, 4)}
    try:
        import apuracao_rtc as ar
        out['art57'] = bool(ar.art57(_so(ncm)))
    except Exception:
        out['art57'] = False
    return out


# ------------------------------------------------------------------ tabela NCM (Siscomex)
def _ler_tabela(caminho):
    if not caminho:
        return {}
    try:
        with open(caminho, encoding='utf-8') as fh:
            d = json.load(fh)
    except Exception:
        try:
            with open(caminho, encoding='latin-1') as fh:
                d = json.load(fh)
        except Exception:
            return {}
    lista = None
    if isinstance(d, list):
        lista = d
    elif isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, list) and 'nomenclatura' in k.lower():
                lista = v
                break
        if lista is None:
            lista = next((v for v in d.values() if isinstance(v, list)), [])
    tab = {}
    for x in lista or []:
        if not isinstance(x, dict):
            continue
        cod = next((x[k] for k in x if k.lower() == 'codigo'), '')
        desc = next((x[k] for k in x if k.lower() == 'descricao'), '')
        c = _so(cod)
        if c:
            tab[c] = re.sub(r'<[^>]+>', '', str(desc)).strip()
    return tab


def _limpa(desc):
    return re.sub(r'^[\s\-–—]+', '', desc or '').strip()


def hierarquia(n, tab):
    out = []
    for tam, rot in ((2, 'Capítulo'), (4, 'Posição'), (5, 'Subposição'), (6, 'Subposição'), (7, 'Item'), (8, 'Subitem')):
        c = n[:tam]
        if len(n) >= tam and c in tab:
            if out and out[-1]['codigo'] == fmt_ncm(c):
                continue
            out.append({'nivel': rot, 'codigo': fmt_ncm(c) if tam != 2 else c, 'descricao': _limpa(tab[c])})
    return out


def consultar(ncm, hoje=None, tabela=None):
    hoje = hoje or date.today()
    n = _so(ncm)
    tab = _ler_tabela(tabela)
    res = {'ncm': fmt_ncm(n), 'valido': len(n) == 8, 'hoje': hoje.isoformat(), 'tabela': bool(tab)}
    if len(n) != 8:
        res['erro'] = 'O NCM tem 8 dígitos (ex.: 4818.10.00).'
        return res
    if tab:
        res['existe'] = n in tab
        res['descricao'] = _limpa(tab.get(n, ''))
        res['hierarquia'] = hierarquia(n, tab)
    res['ibs_cbs'] = ibs_cbs(n, hoje, res.get('descricao', ''))
    if hoje >= FIM_PIS:
        res['pis_cofins'] = {'extinto': True}
        res['aviso'] = {'tipo': 'vigente', 'texto': 'Desde 01/01/2027 o PIS e a COFINS não existem mais: vale a CBS (LC 214/2025).'}
    else:
        res['pis_cofins'] = pis_cofins(n, hoje)
        if hoje >= AVISO_DESDE:
            dias = (FIM_PIS - hoje).days
            res['aviso'] = {'tipo': 'contagem', 'dias': dias,
                            'texto': f'Falta{"m" if dias > 1 else ""} {dias} dia{"s" if dias > 1 else ""}: em 01/01/2027 o PIS e a COFINS deixam de existir e passa a valer a CBS (LC 214/2025).'}
    return res


def buscar(texto, tabela, limite=40):
    tab = _ler_tabela(tabela)
    q = _sem_acento(texto).split()
    if not q or not tab:
        return {'itens': [], 'tabela': bool(tab)}
    itens = []
    pref = _so(texto) if re.fullmatch(r'[\d.\s-]+', texto or '') else ''
    for c, d in tab.items():
        if len(c) != 8:
            continue
        if pref:
            if c.startswith(pref):
                itens.append({'ncm': fmt_ncm(c), 'descricao': _limpa(d)})
            continue
        alvo = _sem_acento(d)
        if all(p in alvo for p in q):
            itens.append({'ncm': fmt_ncm(c), 'descricao': _limpa(d)})
    itens.sort(key=(lambda x: x['ncm']) if pref else (lambda x: (len(x['descricao']), x['ncm'])))
    return {'itens': itens[:limite], 'total': len(itens), 'tabela': True}

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
    Itens da Tabela 4.3.13 que descrevem o produto sem citar o NCM (leite, queijos, adubos, sementes, livros...): códigos da
    NCM pelo texto da Lei 10.925/2004 e da Lei 10.865/2004 (_PRODUTO_LEI) — o sistema decide, sem mandar conferir tabela.
  • IBS/CBS e Imposto Seletivo: banco oficial da Calculadora de Tributos da RFB (rtc_calc_dados, gerado por
    tools/gerar_rtc_calc.py): NCM aplicáveis a cada cClassTrib, exceções, item do anexo da LC 214/2025, percentual de
    redução e alíquotas de referência do ano.
  • A partir de 01/01/2027 o PIS e a COFINS deixam de existir e passa a valer a CBS (LC 214/2025); de 24/12/2026 em
    diante a consulta já avisa.
"""
import json
import re
import unicodedata
from datetime import date

import efd_tabelas_natureza_dados as tn
import rtc_calc_dados as R

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
        excl, excl_ex = set(), {}
        for m in re.finditer(r'exceto([^);]*)', texto, re.I):
            cods = [_so(c) for c in RX_COD.findall(m.group(1))]
            if re.search(r'\bEx\b', m.group(1), re.I):       # "exceto os Ex 01 e Ex 02 do código 2201.10.00": só os Ex saem
                for c in cods:
                    excl_ex[c] = 'exceto com EX TIPI ' + ' ou '.join(re.findall(r'Ex\.?\s*(\d+)', m.group(1), re.I)) + ' (campo EXTIPI da NF-e)'
            else:
                excl.update(cods)
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
            ex = re.match(r'\s*(Ex\.?\s*\d+(?:\s*(?:,|e)\s*Ex\.?\s*\d+)*)', texto[m.end():m.end() + 40], re.I)
            if ex:
                nums = re.findall(r'\d+', ex.group(1))
                cond = f"somente com EX TIPI {' ou '.join(nums)} (campo EXTIPI da NF-e)"
            regras.append((c, excl, cond if ex else ''))
            for xc, xt in excl_ex.items():
                if xc.startswith(c) and xc != c:
                    regras.append((xc, excl, xt))          # o código do Ex é mais específico e vence no NCM dele
        if regras and not de_desc:
            break                                  # o campo de NCM manda; a descrição só entra quando ele está vazio
    return regras


# Na Tabela 4.3.10 o mesmo código aparece em várias linhas, uma por período de alíquota; o arquivo gerado guardou o fim
# do primeiro período. Fármacos e perfumaria (Lei 10.147/2000) e veículos, autopeças e pneus (Lei 10.485/2002) seguem
# monofásicos até a extinção do PIS e da COFINS: esses códigos não "vencem" pela data da linha.
# O mesmo vale para as bebidas frias (Lei 13.097/2015, arts. 14 a 36), cujas linhas mudaram de alíquota até 2017.
_SEM_FIM = {('4.3.10', c) for c in ('201', '202', '301', '302', '303', '304')} | {('4.3.10', str(c)) for c in range(411, 435)}


def _vigente(it, hoje, chave=None):
    i, t = _dt(it.get('i')), (None if chave in _SEM_FIM else _dt(it.get('t'), fim=True))
    return (i is None or i <= hoje) and (t is None or t >= hoje)


# Itens da Tabela 4.3.13 que descrevem o produto sem citar o NCM: códigos pelo texto da lei. Condição vazia = o próprio
# NCM já é o produto da lei; com condição = o NCM abrange outros produtos e a alíquota zero vale só para o descrito.
_SEMEADURA = None


def _semeadura():
    global _SEMEADURA
    if _SEMEADURA is None:
        d = R.ncm_descricoes()
        _SEMEADURA = sorted({c for c, t in d.items() if len(c) >= 6 and re.search(r'semeadura|batata-semente', t, re.I)})
    return _SEMEADURA


_COND_CORRETIVO = 'somente quando vendido como corretivo de solo'
_PRODUTO_LEI = {
    ('4.3.13', '101'): lambda: [('31', '')],                                                # Lei 10.925/2004, art. 1º, I
    ('4.3.13', '103'): lambda: [(c, '') for c in _semeadura()] +                            # art. 1º, III
                               [('0602', 'somente mudas destinadas ao plantio (Lei 10.711/2003)')],
    ('4.3.13', '104'): lambda: [('2518', _COND_CORRETIVO), ('252010', _COND_CORRETIVO), ('25210000', _COND_CORRETIVO)],  # art. 1º, II
    ('4.3.13', '110'): lambda: [(c, '') for c in ('04011010', '04011090', '04012010', '04012090', '04014010', '04015010',  # art. 1º, XI
                                                  '04021010', '04021090', '04022110', '04022120', '04022910', '04022920',
                                                  '04032000', '04039000', '19011010', '19011090')] +
                               [('22029900', 'somente bebidas lácteas'), ('19019090', 'somente compostos lácteos')],
    ('4.3.13', '111'): lambda: [('04061010', ''),                                           # art. 1º, XII
                                ('0406', 'somente queijos minas, prato, coalho, ricota, requeijão, provolone, parmesão e fresco não maturado')],
    ('4.3.13', '112'): lambda: [('04041000', 'somente soro de leite fluido para industrializar produtos de consumo humano')],  # art. 1º, XIII
    ('4.3.13', '120'): lambda: [('0406', 'somente queijo do reino')],                       # art. 1º, XII
    ('4.3.13', '903'): lambda: [('4901', ''), ('49030000', '')],                            # Lei 10.865/2004, art. 28, VI
    ('4.3.13', '304'): lambda: [(c, 'somente almofadas antiescaras') for c in ('39', '40', '63', '94')],  # Lei 10.865/2004, art. 28
}

RX_COND = re.compile(r'\b(quando\b|destinad[oa]s?\b|auferida\s+pel|efetuada\s+por|vendas?\s+(?:a|para|por)\b)', re.I)


def _condicao_texto(d):
    """Item da tabela que só vale numa situação ("quando destinado...", "auferida pela varejista..."): a regra escrita."""
    m = RX_COND.search(d or '')
    if not m:
        return ''
    t = re.split(r'[;:]|(?<!art)(?<!\bn)(?<!nº)(?<!\bo)\.\s', d[m.start():])[0].strip().rstrip('.,')
    t = re.sub(r',\s*assim considerad.*$', '', t)
    if len(t) > 170:
        t = t[:170].rsplit(' ', 1)[0] + '…'
    if not re.match(r'quando\b', t, re.I) and not re.match(r'vendas?\b', t, re.I):
        t = 'quando ' + t
    return 'somente ' + t[0].lower() + t[1:]


ORDEM_TAB = ('4.3.10', '4.3.12', '4.3.13', '4.3.14', '4.3.15', '4.3.16')


def pis_cofins(ncm, hoje):
    n = _so(ncm)
    achados = []
    for tab, v in tn.TABELAS.items():
        for cod, it in v['itens'].items():
            if not _vigente(it, hoje, (tab, cod)):
                continue
            regras = _regras_item(it)
            if (tab, cod) in _PRODUTO_LEI:
                regras = [(pre, set(), cond) for pre, cond in _PRODUTO_LEI[(tab, cod)]()]
            melhor = None
            for pre, excl, cond in regras:
                if pre and n.startswith(pre) and not any(n.startswith(x) for x in excl if x):
                    if melhor is None or len(pre) > len(melhor[0]):
                        melhor = (pre, cond)
            if melhor:
                cond = '; '.join(x for x in (melhor[1], _condicao_texto(it['d'])) if x)
                if tab == '4.3.16' and not cond:
                    cond = 'somente na operação descrita'
                achados.append({'tabela': tab, 'codigo': cod, 'regime': ROT_TAB[tab], 'cst': CST_TAB[tab], 'descricao': it['d'],
                                'ncm_tabela': it.get('n') or '', 'desde': it.get('i') or '', 'ate': it.get('t') or '',
                                'condicao': cond, 'natureza_revenda': NAT_REVENDA.get(cod[:1]) if tab == '4.3.10' and cod[:1] != '4' else ''})
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
    bf = [a for a in achados if a['tabela'] == '4.3.10' and a['codigo'][:1] == '4' and a['codigo'].isdigit()]
    if bf:                                   # bebidas frias: as linhas 411 a 434 são as alíquotas do fabricante/importador
        cods = sorted(a['codigo'] for a in bf)
        achados = [a for a in achados if a not in bf]
        exs = [re.search(r'(somente|exceto) com EX TIPI[^;]*', a['condicao']) for a in bf]
        cond_bf = exs[0].group(0) if all(exs) and len({x.group(0) for x in exs}) == 1 else ''
        achados.append({'tabela': '4.3.10', 'codigo': cods[0] if len(cods) == 1 else f'{cods[0]} a {cods[-1]}',
                        'regime': 'Tributação concentrada', 'cst': '02 (fabricante/importador)',
                        'descricao': 'Bebidas frias — PIS e COFINS concentrados no fabricante e no importador (Lei 13.097/2015, '
                                     'arts. 14 a 36); a alíquota do fabricante muda com a embalagem, o comprador e o volume de produção.',
                        'ncm_tabela': bf[0]['ncm_tabela'], 'desde': bf[0]['desde'], 'ate': '', 'condicao': cond_bf, 'natureza_revenda': ''})
    achados.sort(key=lambda a: (bool(a['condicao']), ORDEM_TAB.index(a['tabela'])))
    gerais = [a for a in achados if not a['condicao']]
    return {'achados': gerais, 'situacoes': [a for a in achados if a['condicao']], 'basica': not gerais}


# ------------------------------------------------------------------ IBS/CBS
ROMANOS = {str(i): r for i, r in enumerate(('', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII', 'XIII',
                                              'XIV', 'XV'))}
# cClassTrib oficiais de bens que o banco da calculadora não liga a NCM: o produto descrito decide (LC 214/2025)
_EXTRA_NCM = (('3003', '200032', ''),                 # medicamento (posições 30.03 e 30.04): redução de 60%, LC 214, art. 133
              ('3004', '200032', ''),
              ('3003', '200009', 'princípio ativo no Anexo XIV da LC 214/2025'),
              ('3004', '200009', 'princípio ativo no Anexo XIV da LC 214/2025'),
              ('3002', '200053', 'somente soros e vacinas registrados na Anvisa'),
              ('96190000', '200013', 'somente absorventes, tampões e coletores menstruais (fraldas não)'))
_CL_POR_CD = {}
for _id, _c in R.CLASSES.items():
    if _c['tributo'] == 'IBSCBS':
        _CL_POR_CD.setdefault(_c['cd'], _id)


def _vig(ini, fim, d):
    s = d.isoformat()
    return (not ini or ini <= s) and (not fim or fim >= s)


def _reducao(cl, d):
    out = {}
    for t, lst in cl['red'].items():
        for v, i, f in lst:
            if _vig(i, f, d):
                out[t] = v
    return out


def _aliq_ref(d):
    return {t: v for t, v, i, f in R.ALIQ_REF if _vig(i, f, d)}


def _enq(cid, cl, hoje, anexo=None, condicao=''):
    red = _reducao(cl, hoje)
    num, item, txt = anexo or ('', '', '')
    desc = cl['desc']
    publico = bool(re.search(r'administra[cç][aã]o p[uú]blica|imunes', desc, re.I))
    return {'cclasstrib': cl['cd'], 'cst': cl['cst'], 'cst_desc': cl['cst_desc'], 'descricao': desc,
            'anexo': num or ROMANOS.get(cl['anexo'] or '', ''), 'item': item, 'texto_item': txt,
            'red_cbs': red.get('cbs', 0.0), 'red_ibs': red.get('ibsuf', 0.0),
            'publico': publico, 'diferimento': cl['cst'] == '515', 'condicao': condicao}


def imposto_seletivo(n):
    """Imposto Seletivo (a partir de 2027) pelo banco da calculadora: produto listado nas classificações do IS."""
    if any(n.startswith(x) for x in R.IS_EXCECAO):
        return None
    if n in R.IS_PRODUTO:
        return {'desde': R.IS_PRODUTO[n][0] or '2027-01-01'}
    for (i, pre, cid, ax, ini, fim) in R.APLIC:
        cl = R.CLASSES.get(cid)
        if cl and cl['tributo'] == 'IS' and cl['cd'] in ('000001', '000010') and n.startswith(pre):
            return {'desde': ini or cl['ini'] or '2027-01-01'}
    return None


def ibs_cbs(ncm, hoje, desc=''):
    n = _so(ncm)
    lst, vistos = [], set()
    for (i, pre, cid, ax, ini, fim) in R.APLIC:
        if not n.startswith(pre) or not _vig(ini, fim, hoje):
            continue
        cl = R.CLASSES.get(cid)
        if not cl or cl['tributo'] != 'IBSCBS' or not _vig(cl['ini'], cl['fim'], hoje):
            continue
        if any(n.startswith(x) and _vig(a, b, hoje) for x, a, b in R.EXCECOES.get(i, [])):
            continue
        k = (cl['cd'], ax)
        if k in vistos:
            continue
        vistos.add(k)
        lst.append(_enq(cid, cl, hoje, R.ANEXOS.get(ax)))
    for pre, cd, cond in _EXTRA_NCM:
        cid = _CL_POR_CD.get(cd)
        if n.startswith(pre) and cid and (cd, None) not in vistos and _vig(R.CLASSES[cid]['ini'], R.CLASSES[cid]['fim'], hoje):
            vistos.add((cd, None))
            x = _enq(cid, R.CLASSES[cid], hoje, condicao=cond)
            x['prio'] = not cond
            lst.append(x)
    gerais = [x for x in lst if not x['publico'] and not x['diferimento'] and not x['condicao']]
    gerais.sort(key=lambda x: (-x['red_cbs'], not x.get('prio')))
    principal = gerais[0] if gerais else None
    outros = [x for x in lst if x is not principal]
    outros.sort(key=lambda x: (x['publico'], x['diferimento'], -x['red_cbs']))
    red = principal['red_cbs'] if principal else 0.0
    out = {'reducao': red, 'principal': principal, 'outros': outros,
           'cst': principal['cst'] if principal else '000', 'cclasstrib': principal['cclasstrib'] if principal else '000001',
           'base': {'versao': R.VERSAO, 'data': R.VERSAO_DATA}}
    ref = _aliq_ref(hoje)
    if ref:
        f = (100 - red) / 100
        out['aliquotas'] = {'ano': hoje.year, 'cbs': round(ref.get('cbs', 0) * f, 4),
                            'ibs': round((ref.get('ibsuf', 0) + ref.get('ibsmun', 0)) * f, 4),
                            'ref_cbs': ref.get('cbs', 0), 'ref_ibs': ref.get('ibsuf', 0) + ref.get('ibsmun', 0)}
    if any(x['cclasstrib'] == '200009' for x in lst):
        out['anexo_xiv'] = sorted((t for (a, it, t) in R.ANEXOS.values() if a == 'XIV'))
    out['seletivo'] = imposto_seletivo(n)
    try:
        import apuracao_rtc as ar
        out['art57'] = ar.art57(n) or ''
    except Exception:
        out['art57'] = ''
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


def _tabela(caminho):
    """Tabela NCM do Siscomex (baixada pelo sistema); sem ela, a tabela NCM do banco oficial da calculadora da RFB."""
    tab = _ler_tabela(caminho)
    if tab:
        return tab, 'siscomex'
    try:
        return R.ncm_descricoes(), 'rfb'
    except Exception:
        return {}, ''


def _limpa(desc):
    return re.sub(r'<[^>]+>', '', re.sub(r'^[\s\-–—]+', '', desc or '')).strip()


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
    tab, fonte = _tabela(tabela)
    res = {'ncm': fmt_ncm(n), 'valido': len(n) == 8, 'hoje': hoje.isoformat(), 'tabela': bool(tab), 'fonte': fonte}
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
    tab, _ = _tabela(tabela)
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

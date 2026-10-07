# -*- coding: utf-8 -*-
"""Evolução Tributária e de Faturamento — módulo restrito ao Admin.

Lê vários SPED Fiscais (EFD ICMS/IPI) da MESMA empresa, um por competência, e monta a série mensal de:
  • faturamento (saídas por CFOP, menos devoluções de venda) e entradas;
  • apuração do ICMS próprio (E110), ST (E200/E210), DIFAL/FCP (E300/E310) e IPI (E520);
  • ajustes da apuração (E111, E220, E311) — com descrição oficial da Tabela 5.1.1 da UF e destaque
    para o ICMS ANTECIPADO e para os benefícios fiscais;
  • obrigações a recolher (E116 / E250) com código da Tabela 5.4, vencimento e código de receita.

Layouts conferidos no Guia Prático da EFD ICMS/IPI v3.2.4 (Ato COTEPE/ICMS 44/2018). Nada aqui é estimado:
todo número vem de um campo declarado no SPED, e a origem de cada um está na tela ("de onde vem cada número").
"""
import os
import re
import sys
import json
from collections import defaultdict, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tabela_ajustes_dados import TABELA_5_4, TABELA_5_1_1, VERSOES, carregar_tabela_externa  # noqa: E402

# Registros analíticos com o layout REG|CST|CFOP|ALIQ|VL_OPR|VL_BC|VL_ICMS|… (Guia Prático, Bloco C e D)
ANALITICOS = {'C190', 'C320', 'C390', 'C490', 'C590', 'C690', 'C790', 'C850', 'C890', 'D190', 'D590', 'D690', 'D696'}
# documentos cujos analíticos não contam quando cancelados/denegados/inutilizados (COD_SIT 02 a 05)
CABECALHOS = {'C100': 6, 'C500': 6, 'D100': 6, 'C800': 3}   # registro -> índice do COD_SIT (quando houver)
CANC = {'02', '03', '04', '05'}
# outros registros-pai de analíticos: ao encontrá-los, a situação do C100/C500/D100 anterior deixa de valer
PAIS_SEM_SIT = {'C300', 'C350', 'C400', 'C405', 'C600', 'C700', 'C860', 'D300', 'D400', 'D500', 'D600', 'D695', 'D700', 'D750'}

NATUREZA = {'0': 'Outros débitos', '1': 'Estorno de créditos', '2': 'Outros créditos',
            '3': 'Estorno de débitos', '4': 'Deduções do imposto apurado', '5': 'Débitos especiais'}
SINAL = {'0': 1, '1': 1, '2': -1, '3': -1, '4': -1, '5': 1}          # efeito no imposto a pagar
APURACAO = {'0': 'ICMS próprio', '1': 'ICMS-ST', '2': 'DIFAL', '3': 'FCP'}
MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']


def _n(s):
    s = (s or '').strip()
    if not s:
        return 0.0
    try:
        return float(s.replace('.', '').replace(',', '.')) if ',' in s else float(s)
    except ValueError:
        return 0.0


def _linhas(path):
    for enc in ('utf-8', 'latin-1'):
        try:
            with open(path, 'r', encoding=enc) as fh:
                return fh.read().splitlines()
        except UnicodeDecodeError:
            continue
    return []


def _r(v):
    return round(v + 0.0, 2)


# ------------------------------------------------------------------ CFOP (Ajuste SINIEF 07/01)
def classifica_cfop(cfop):
    """Devolve (sentido, grupo). Grupos de saída: venda, transferencia, devol_compra, remessa, outras.
    Grupos de entrada: compra, uso_ativo, devol_venda, transferencia, outras."""
    c = re.sub(r'\D', '', cfop or '')
    if len(c) != 4:
        return ('?', 'outras')
    d, r = c[0], int(c[1:])
    if d in '567':
        if 101 <= r <= 127 or 251 <= r <= 258 or 301 <= r <= 307 or 351 <= r <= 360 or r in (401, 402, 403, 405) \
                or 651 <= r <= 656 or r == 667 or (d == '7' and r == 501):
            return ('saida', 'venda')
        if 151 <= r <= 159 or r in (408, 409) or r in (658, 659) or r == 552 or r == 557:
            return ('saida', 'transferencia')
        if 201 <= r <= 213 or 410 <= r <= 413 or 660 <= r <= 662 or r in (553, 556):
            return ('saida', 'devol_compra')
        return ('saida', 'outras')
    if d in '123':
        if 201 <= r <= 209 or r in (410, 411) or 660 <= r <= 662 or (d == '3' and r in (201, 202, 211)):
            return ('entrada', 'devol_venda')
        if 101 <= r <= 128 or r in (401, 403, 408) or 651 <= r <= 652 or 251 <= r <= 257 or 301 <= r <= 307 or 351 <= r <= 360:
            return ('entrada', 'compra')
        if 551 <= r <= 557 or r in (406, 407, 653):
            return ('entrada', 'uso_ativo')
        if 151 <= r <= 159 or r in (409,) or r in (658, 659):
            return ('entrada', 'transferencia')
        return ('entrada', 'outras')
    return ('?', 'outras')


def _mes_rotulo(comp):
    a, m = comp.split('-')
    return f'{MESES[int(m) - 1]}/{a[2:]}'


def _cnpj_fmt(c):
    c = re.sub(r'\D', '', c or '')
    return f'{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}' if len(c) == 14 else c


# ------------------------------------------------------------------ leitura de um SPED
def ler_sped(path):
    L = _linhas(path)
    m = {'arquivo': os.path.basename(path), 'cab': {}, 'fat': defaultdict(float), 'ent': defaultdict(float),
         'icms_saidas': 0.0, 'icms_entradas': 0.0, 'icms_st_saidas': 0.0, 'ipi_saidas': 0.0,
         'cfop_saida': defaultdict(float), 'cfop_entrada': defaultdict(float),
         'e110': None, 'ajustes': [], 'obrig': [], 'st': {}, 'difal': {}, 'e520': None, 'qtd': defaultdict(int)}
    sit = ''
    uf_e200 = uf_e300 = ''
    for ln in L:
        c = ln.split('|')
        if len(c) < 3:
            continue
        r = c[1]
        if r == '0000' and len(c) > 9:
            m['cab'] = {'dt_ini': c[4], 'dt_fin': c[5], 'nome': c[6].strip(), 'cnpj': c[7], 'uf': c[9], 'ie': c[10] if len(c) > 10 else ''}
            continue
        if r in CABECALHOS:
            i = CABECALHOS[r]
            sit = c[i] if r != 'C800' and len(c) > i else (c[3] if len(c) > 3 else '')
            m['qtd'][r] += 1
            continue
        if r in PAIS_SEM_SIT:
            sit = ''
            continue
        if r in ANALITICOS and len(c) > 7:
            if sit in CANC:
                continue
            cfop = c[3].strip()
            vl_opr, vl_icms = _n(c[5]), _n(c[7])
            sentido, grupo = classifica_cfop(cfop)
            if sentido == 'saida':
                m['fat'][grupo] += vl_opr
                m['cfop_saida'][cfop] += vl_opr
                if grupo == 'venda':
                    m['fat']['venda_' + {'5': 'interna', '6': 'interestadual', '7': 'exterior'}[cfop[0]]] += vl_opr
                    if cfop[1:] in ('401', '402', '403', '405'):
                        m['fat']['venda_st'] += vl_opr
                m['icms_saidas'] += vl_icms
                if r == 'C190' and len(c) > 11:
                    m['icms_st_saidas'] += _n(c[9])
                    m['ipi_saidas'] += _n(c[11])
            elif sentido == 'entrada':
                m['ent'][grupo] += vl_opr
                m['cfop_entrada'][cfop] += vl_opr
                m['icms_entradas'] += vl_icms
            continue
        if r == 'E110' and len(c) > 15:
            m['e110'] = {k: _n(c[i]) for i, k in enumerate(
                ['deb', 'aj_deb_doc', 'outros_deb', 'estornos_cred', 'cred', 'aj_cred_doc', 'outros_cred', 'estornos_deb',
                 'sld_ant', 'sld_apurado', 'deducoes', 'recolher', 'sld_transp', 'deb_esp'], start=2)}
        elif r in ('E111', 'E220', 'E311') and len(c) > 4:
            m['ajustes'].append({'reg': r, 'cod': c[2].strip(), 'compl': c[3].strip(), 'valor': _n(c[4]),
                                 'ind_benef': c[5].strip() if len(c) > 5 and r != 'E311' else '',
                                 'uf': uf_e200 if r == 'E220' else (uf_e300 if r == 'E311' else '')})
        elif r in ('E116', 'E250') and len(c) > 5:
            m['obrig'].append({'reg': r, 'cod': c[2].strip(), 'valor': _n(c[3]), 'venc': c[4].strip(), 'cod_rec': c[5].strip(),
                               'compl': c[9].strip() if len(c) > 9 else '', 'mes_ref': c[10].strip() if len(c) > 10 else '',
                               'uf': uf_e200 if r == 'E250' else ''})
        elif r == 'E200' and len(c) > 2:
            uf_e200 = c[2].strip()
        elif r == 'E210' and len(c) > 15:
            st = m['st'].setdefault(uf_e200, {'retencao': 0.0, 'recolher': 0.0, 'deb_esp': 0.0, 'sld_transp': 0.0})
            st['retencao'] += _n(c[8]); st['recolher'] += _n(c[13]); st['sld_transp'] += _n(c[14]); st['deb_esp'] += _n(c[15])
        elif r == 'E300' and len(c) > 2:
            uf_e300 = c[2].strip()
        elif r == 'E310' and len(c) > 22:
            d = m['difal'].setdefault(uf_e300, {'difal': 0.0, 'fcp': 0.0, 'deb_esp_difal': 0.0, 'deb_esp_fcp': 0.0})
            d['difal'] += _n(c[10]); d['deb_esp_difal'] += _n(c[12]); d['fcp'] += _n(c[20]); d['deb_esp_fcp'] += _n(c[22])
        elif r == 'E520' and len(c) > 8:
            m['e520'] = {'deb': _n(c[3]), 'cred': _n(c[4]), 'recolher': _n(c[8]), 'sld_transp': _n(c[7])}
    return m


# ------------------------------------------------------------------ tabela de ajustes
def _descricoes(uf, tabela_externa=None):
    tab = {}
    fonte = ''
    if tabela_externa and os.path.exists(tabela_externa):
        tab = carregar_tabela_externa(tabela_externa)
        if tab:
            fonte = f'Tabela 5.1.1 oficial de {uf} (Sped, baixada pelo sistema)'
    if not tab and uf in TABELA_5_1_1:
        tab = TABELA_5_1_1[uf]
        fonte = f'Tabela 5.1.1 oficial de {uf} ({VERSOES.get(uf, "")}), embutida no sistema'
    return tab, fonte


def _classifica_ajuste(a, tab):
    cod = a['cod']
    tipo = cod[2:3] if len(cod) >= 4 else ''
    nat = cod[3:4] if len(cod) >= 4 else ''
    desc_of = tab.get(cod, '')
    texto = (desc_of + ' ' + a['compl']).upper()
    antecip = 'ANTECIP' in texto
    benef = (any(k in texto for k in ('PRESUMID', 'ESTÍMULO', 'ESTIMULO', 'INCENTIV', 'PIT -', 'PIT –'))
             or a.get('ind_benef', '') in ('1', '2', '3', '9'))
    return {**a, 'tipo': tipo, 'apuracao': APURACAO.get(tipo, 'Outros'), 'natureza': nat, 'nat_rotulo': NATUREZA.get(nat, 'Natureza ' + (nat or '?')),
            'sinal': SINAL.get(nat, 1), 'desc_oficial': desc_of, 'antecipado': antecip, 'beneficio': benef,
            'titulo': desc_of or a['compl'] or ('Ajuste ' + cod)}


# ------------------------------------------------------------------ análise do período
def analisar(caminhos, tabela_externa=None):
    lidos = []
    avisos = []
    for p in caminhos:
        try:
            m = ler_sped(p)
        except Exception as e:  # pragma: no cover
            avisos.append(f'Não foi possível ler {os.path.basename(p)}: {e}')
            continue
        cab = m['cab']
        if not cab.get('dt_ini') or len(cab['dt_ini']) != 8:
            avisos.append(f'{m["arquivo"]}: não parece um SPED Fiscal (registro 0000 ausente). Ignorado.')
            continue
        m['comp'] = f'{cab["dt_ini"][4:]}-{cab["dt_ini"][2:4]}'
        lidos.append(m)
    if not lidos:
        return {'erro': 'Nenhum SPED Fiscal válido entre os arquivos selecionados.'}

    cnpjs = OrderedDict()
    for m in lidos:
        cnpjs.setdefault(re.sub(r'\D', '', m['cab']['cnpj']), []).append(m)
    if len(cnpjs) > 1:
        partes = '; '.join(f'{_cnpj_fmt(k)} ({v[0]["cab"]["nome"]}, {len(v)} arquivo(s))' for k, v in cnpjs.items())
        return {'erro': 'Os arquivos são de empresas diferentes: ' + partes + '. Selecione os SPEDs de uma empresa só.'}

    por_comp = OrderedDict()
    for m in sorted(lidos, key=lambda x: x['comp']):
        if m['comp'] in por_comp:
            avisos.append(f'Há mais de um SPED de {_mes_rotulo(m["comp"])}: usado {m["arquivo"]} (o último selecionado); '
                          f'{por_comp[m["comp"]]["arquivo"]} foi descartado.')
        por_comp[m['comp']] = m
    comps = list(por_comp)
    # meses faltando no intervalo
    a0, m0 = map(int, comps[0].split('-'))
    a1, m1 = map(int, comps[-1].split('-'))
    faltam = []
    a, mm = a0, m0
    while (a, mm) <= (a1, m1):
        k = f'{a:04d}-{mm:02d}'
        if k not in por_comp:
            faltam.append(k)
        mm += 1
        if mm > 12:
            a, mm = a + 1, 1
    if faltam:
        avisos.append('Meses sem SPED no intervalo (os gráficos pulam esses meses): ' + ', '.join(_mes_rotulo(k) for k in faltam) + '.')

    cab = por_comp[comps[-1]]['cab']
    uf = cab.get('uf', '')
    tab, fonte_tab = _descricoes(uf, tabela_externa)
    if not tab:
        avisos.append(f'Sem a Tabela 5.1.1 de {uf or "?"} no momento: os ajustes aparecem pela descrição complementar do E111 '
                      'e pela natureza do código (4º caractere).')

    meses = []
    aj_res = OrderedDict()
    cfop_s = defaultdict(float)
    cfop_e = defaultdict(float)
    for comp in comps:
        m = por_comp[comp]
        f = m['fat']
        vendas = f['venda']
        devol = m['ent']['devol_venda']
        e110 = m['e110'] or {k: 0.0 for k in ('deb', 'aj_deb_doc', 'outros_deb', 'estornos_cred', 'cred', 'aj_cred_doc', 'outros_cred',
                                               'estornos_deb', 'sld_ant', 'sld_apurado', 'deducoes', 'recolher', 'sld_transp', 'deb_esp')}
        if not m['e110']:
            avisos.append(f'{_mes_rotulo(comp)}: SPED sem registro E110 (apuração do ICMS).')
        st_rec = sum(v['recolher'] + v['deb_esp'] for v in m['st'].values())
        st_proprio = sum(v['recolher'] + v['deb_esp'] for k, v in m['st'].items() if k == uf)
        difal = sum(v['difal'] + v['deb_esp_difal'] for v in m['difal'].values())
        fcp = sum(v['fcp'] + v['deb_esp_fcp'] for v in m['difal'].values())
        ipi = (m['e520'] or {}).get('recolher', 0.0)
        ajustes = [_classifica_ajuste(a, tab) for a in m['ajustes'] if a['valor']]
        ant_deb_esp = sum(a['valor'] for a in ajustes if a['antecipado'] and a['natureza'] == '5')
        ant_cred = sum(a['valor'] for a in ajustes if a['antecipado'] and a['natureza'] in ('2', '4'))
        ant_outros = sum(a['valor'] for a in ajustes if a['antecipado'] and a['natureza'] not in ('2', '4', '5'))
        benef = sum(a['valor'] for a in ajustes if a['beneficio'] and a['natureza'] in ('2', '3', '4'))
        obrig = []
        for o in m['obrig']:
            obrig.append({**o, 'desc': TABELA_5_4.get(o['cod'], 'Código ' + o['cod']),
                          'venc_fmt': f'{o["venc"][:2]}/{o["venc"][2:4]}/{o["venc"][4:]}' if len(o['venc']) == 8 else o['venc']})
        e116 = sum(o['valor'] for o in m['obrig'] if o['reg'] == 'E116')
        icms_prop = e110['recolher'] + e110['deb_esp']
        total_icms = icms_prop + st_rec + difal + fcp
        liquido = vendas - devol
        mes = {
            'comp': comp, 'rotulo': _mes_rotulo(comp), 'arquivo': m['arquivo'],
            'fat': {'vendas': _r(vendas), 'devolucoes': _r(devol), 'liquido': _r(liquido),
                    'interna': _r(f['venda_interna']), 'interestadual': _r(f['venda_interestadual']), 'exterior': _r(f['venda_exterior']),
                    'com_st': _r(f['venda_st']), 'transferencias': _r(f['transferencia']), 'devol_compra': _r(f['devol_compra']),
                    'outras_saidas': _r(f['outras']), 'total_saidas': _r(sum(v for k, v in f.items() if not k.startswith('venda_')))},
            'ent': {'compras': _r(m['ent']['compra']), 'uso_ativo': _r(m['ent']['uso_ativo']), 'devol_venda': _r(devol),
                    'transferencias': _r(m['ent']['transferencia']), 'outras': _r(m['ent']['outras']),
                    'total': _r(sum(m['ent'].values()))},
            'apur': {k: _r(v) for k, v in e110.items()},
            'icms_proprio': _r(e110['recolher']), 'deb_esp': _r(e110['deb_esp']),
            'st': _r(st_rec), 'st_proprio': _r(st_proprio), 'st_por_uf': {k: _r(v['recolher'] + v['deb_esp']) for k, v in m['st'].items()},
            'st_retido': _r(sum(v['retencao'] for v in m['st'].values())),
            'difal': _r(difal), 'fcp': _r(fcp), 'difal_por_uf': {k: _r(v['difal'] + v['deb_esp_difal']) for k, v in m['difal'].items()},
            'ipi': _r(ipi), 'total_icms': _r(total_icms), 'total_recolher': _r(total_icms + ipi),
            'carga': round(total_icms / liquido * 100, 2) if liquido > 0 else None,
            'antecipado': {'deb_esp': _r(ant_deb_esp), 'creditos': _r(ant_cred), 'outros': _r(ant_outros)},
            'beneficios': _r(benef),
            'ajustes': ajustes, 'obrigacoes': obrig,
            'e116_soma': _r(e116), 'e116_confere': (not m['obrig']) or abs(e116 - icms_prop) < 0.05,
            'sld_credor': _r(e110['sld_transp']),
        }
        if m['obrig'] and not mes['e116_confere']:
            avisos.append(f'{mes["rotulo"]}: a soma das obrigações do E116 ({e116:,.2f}) não fecha com ICMS a recolher + débitos especiais '
                          f'do E110 ({icms_prop:,.2f}).'.replace(',', 'X').replace('.', ',').replace('X', '.'))
        meses.append(mes)
        for a in ajustes:
            k = (a['reg'], a['cod'], a['compl'] if not a['desc_oficial'] else '')
            r = aj_res.setdefault(k, {'reg': a['reg'], 'cod': a['cod'], 'titulo': a['titulo'], 'desc_oficial': a['desc_oficial'],
                                      'compl': a['compl'], 'apuracao': a['apuracao'], 'natureza': a['natureza'], 'nat_rotulo': a['nat_rotulo'],
                                      'antecipado': a['antecipado'], 'beneficio': a['beneficio'], 'total': 0.0, 'por_mes': {}})
            r['total'] += a['valor']
            r['por_mes'][comp] = _r(r['por_mes'].get(comp, 0.0) + a['valor'])
        for k, v in m['cfop_saida'].items():
            cfop_s[k] += v
        for k, v in m['cfop_entrada'].items():
            cfop_e[k] += v

    def soma(campo, sub=None):
        return _r(sum((x[campo][sub] if sub else x[campo]) or 0.0 for x in meses))

    tot = {
        'vendas': soma('fat', 'vendas'), 'devolucoes': soma('fat', 'devolucoes'), 'liquido': soma('fat', 'liquido'),
        'interna': soma('fat', 'interna'), 'interestadual': soma('fat', 'interestadual'), 'exterior': soma('fat', 'exterior'),
        'com_st': soma('fat', 'com_st'), 'compras': soma('ent', 'compras'), 'entradas': soma('ent', 'total'),
        'icms_proprio': soma('icms_proprio'), 'deb_esp': soma('deb_esp'), 'st': soma('st'), 'difal': soma('difal'), 'fcp': soma('fcp'),
        'ipi': soma('ipi'), 'total_icms': soma('total_icms'), 'total_recolher': soma('total_recolher'),
        'debitos': _r(sum(x['apur']['deb'] + x['apur']['aj_deb_doc'] + x['apur']['outros_deb'] + x['apur']['estornos_cred'] for x in meses)),
        'creditos': _r(sum(x['apur']['cred'] + x['apur']['aj_cred_doc'] + x['apur']['outros_cred'] + x['apur']['estornos_deb'] for x in meses)),
        'deducoes': _r(sum(x['apur']['deducoes'] for x in meses)),
        'antecipado_deb_esp': _r(sum(x['antecipado']['deb_esp'] for x in meses)),
        'antecipado_creditos': _r(sum(x['antecipado']['creditos'] for x in meses)),
        'beneficios': soma('beneficios'),
        'sld_credor_inicial': meses[0]['apur']['sld_ant'], 'sld_credor_final': meses[-1]['sld_credor'],
    }
    tot['carga'] = round(tot['total_icms'] / tot['liquido'] * 100, 2) if tot['liquido'] > 0 else None
    tot['media_fat'] = _r(tot['liquido'] / len(meses))
    tot['media_recolher'] = _r(tot['total_recolher'] / len(meses))
    # variação: média do último terço vs. primeiro terço (quando há pelo menos 2 meses)
    n = len(meses)
    var = None
    if n >= 2:
        k = max(1, n // 3)
        ini = sum(x['fat']['liquido'] for x in meses[:k]) / k
        fim = sum(x['fat']['liquido'] for x in meses[-k:]) / k
        var = {'meses_base': k, 'inicio': _r(ini), 'fim': _r(fim), 'pct': round((fim - ini) / ini * 100, 1) if ini > 0 else None}
        ini_t = sum(x['total_recolher'] for x in meses[:k]) / k
        fim_t = sum(x['total_recolher'] for x in meses[-k:]) / k
        var['trib_inicio'], var['trib_fim'] = _r(ini_t), _r(fim_t)
        var['trib_pct'] = round((fim_t - ini_t) / ini_t * 100, 1) if ini_t > 0 else None
    melhor = max(meses, key=lambda x: x['fat']['liquido'])
    maior_trib = max(meses, key=lambda x: x['total_recolher'])

    ajustes = sorted(aj_res.values(), key=lambda a: -a['total'])
    for a in ajustes:
        a['total'] = _r(a['total'])

    return {
        'empresa': {'nome': cab.get('nome', ''), 'cnpj': _cnpj_fmt(cab.get('cnpj', '')), 'uf': uf, 'ie': cab.get('ie', '')},
        'periodo': {'ini': comps[0], 'fim': comps[-1], 'ini_rot': _mes_rotulo(comps[0]), 'fim_rot': _mes_rotulo(comps[-1]),
                    'meses': n, 'faltando': [_mes_rotulo(k) for k in faltam]},
        'meses': meses, 'totais': tot, 'variacao': var,
        'destaques': {'melhor_mes': melhor['rotulo'], 'melhor_valor': melhor['fat']['liquido'],
                      'maior_trib_mes': maior_trib['rotulo'], 'maior_trib_valor': maior_trib['total_recolher']},
        'ajustes': ajustes,
        'cfop_saida': [{'cfop': k, 'valor': _r(v), 'grupo': classifica_cfop(k)[1]} for k, v in sorted(cfop_s.items(), key=lambda x: -x[1])[:12]],
        'cfop_entrada': [{'cfop': k, 'valor': _r(v), 'grupo': classifica_cfop(k)[1]} for k, v in sorted(cfop_e.items(), key=lambda x: -x[1])[:12]],
        'fonte_tabela': fonte_tab or 'Sem tabela 5.1.1 da UF',
        'avisos': avisos,
        'arquivos': [por_comp[k]['arquivo'] for k in comps],
    }


def main_cli(argv):
    jo = argv[argv.index('--json') + 1] if '--json' in argv else None
    tab = argv[argv.index('--tabela') + 1] if '--tabela' in argv else None
    arqs = []
    i = 0
    while i < len(argv):
        if argv[i] == '--sped':
            i += 1
            while i < len(argv) and not argv[i].startswith('--'):
                arqs.append(argv[i]); i += 1
        else:
            i += 2 if argv[i] in ('--json', '--tabela') else 1
    if not arqs:
        print('uso: evolucao-tributaria --sped A.txt [B.txt ...] [--tabela tabela_5_1_1.txt] --json saida.json'); return 1
    try:
        res = analisar(arqs, tab)
    except Exception as e:  # pragma: no cover
        res = {'erro': f'Falha ao ler os SPEDs: {e}'}
    if jo:
        with open(jo, 'w', encoding='utf-8') as fh:
            json.dump(res, fh, ensure_ascii=False)
    else:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


def uf_do_sped(path):
    """Lê só a 1ª linha (0000) para descobrir a UF — usado pelo Electron para baixar a tabela certa."""
    for ln in _linhas(path)[:3]:
        c = ln.split('|')
        if len(c) > 9 and c[1] == '0000':
            return c[9]
    return ''


if __name__ == '__main__':
    sys.exit(main_cli(sys.argv[1:]))

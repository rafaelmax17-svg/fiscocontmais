# -*- coding: utf-8 -*-
"""Uso e consumo / ativo vindos de outro estado — CFOP e DIFAL de Rondônia no SPED Fiscal (EFD ICMS/IPI).
Módulo do Corretor do SPED, restrito ao Admin. Gera arquivo NOVO; o original nunca é alterado.

O que faz
  1) Acha entradas de uso e consumo (x.556, x.407) e de ativo (x.551, x.406) e confere o 1º dígito do CFOP com a UF
     do emitente (chave de acesso; sem chave, município do 0150): de outro estado deve ser 2.xxx; do próprio estado, 1.xxx.
  2) Calcula o DIFAL devido a RO e confere se já está lançado na nota (C197). Mostra: lançado e confere, lançado com
     valor diferente, pago fora da apuração (informativo) ou faltando.
  3) Aplica só o que for confirmado na tela: troca o CFOP (C170 e C190), inclui C195 + C197 por nota (0460 se faltar),
     soma o DIFAL no campo 03 do E110, recalcula o E110, ajusta/cria o E116 e reconta os blocos.
  4) Crédito de ICMS tomado em uso e consumo / ativo (LC 87/96, art. 33, I — só a partir de 01/01/2033; ativo pelo CIAP,
     art. 20, § 5º): zera base, alíquota e ICMS no C170/C190/C100 (campo 06 do E110 diminui) ou mantém a nota e lança
     estorno de crédito no E111 (campo 05 do E110), com o código da tabela 5.1.1 da UF que o usuário confirmar.

Fontes oficiais (lidas em 09/10/2026)
  • Lei 688/96 (RO), art. 17, XIII; art. 18, IX "a" e "b", § 1º e § 7º (redação da Lei 5.369/2022, efeitos a partir de
    01/04/2022): base dupla — base de destino com o imposto por dentro, alíquota interna para a base de destino.
  • RICMS/RO (Decreto 22.721/2018), art. 15, § 2º e art. 16, § 2º (Decreto 27.901/2023).
  • Lei 688/96, art. 27, I, "c" (Lei 5.634/2023): alíquota interna geral de 19,5% a partir de 12/01/2024.
  • Manual de Orientações da EFD de RO (anexo da IN 033/2018/GAB/CRE), itens 3, 4 e 12: C195 + C197 RO40000001
    (ativo) / RO40000002 (uso e consumo) por documento e por combinação de alíquotas, VL_BC_ICMS = base do DIFAL,
    ALIQ_ICMS = interestadual, VL_ICMS = DIFAL, VL_OUTROS = alíquota interna; soma no campo 03 (VL_AJ_DEBITOS) do E110;
    RO90000002 = DIFAL recolhido fora da conta gráfica (só informativo).
  • Guia Prático da EFD ICMS/IPI v3.2.4: E110 campos 03, 11, 13, 14; C195; C197; 0460; E116.
"""
import os
import re
import sys
import json
from decimal import Decimal, ROUND_HALF_UP

UF_IBGE = {'11': 'RO', '12': 'AC', '13': 'AM', '14': 'RR', '15': 'PA', '16': 'AP', '17': 'TO', '21': 'MA', '22': 'PI', '23': 'CE',
           '24': 'RN', '25': 'PB', '26': 'PE', '27': 'AL', '28': 'SE', '29': 'BA', '31': 'MG', '32': 'ES', '33': 'RJ', '35': 'SP',
           '41': 'PR', '42': 'SC', '43': 'RS', '50': 'MS', '51': 'MT', '52': 'GO', '53': 'DF'}
SUL_SUDESTE_SEM_ES = {'SP', 'RJ', 'MG', 'PR', 'SC', 'RS'}       # Res. Senado 22/89: 7% para N/NE/CO/ES
ORIGEM_IMPORTADA = {'1', '2', '3', '8'}                          # Res. Senado 13/12: 4%
CANC = {'02', '03', '04', '05'}
EXTEMP = {'01', '07', '10'}                                       # fora do campo 03 do E110 (Guia Prático)

TIPOS = {  # final do CFOP -> (tipo, código de ajuste RO, descrição oficial do manual, tem ST?)
    '556': ('uso', 'RO40000002', 'DÉBITO DE DIFERENCIAL DE MATERIAL DE USO E CONSUMO', False),
    '407': ('uso', 'RO40000002', 'DÉBITO DE DIFERENCIAL DE MATERIAL DE USO E CONSUMO', True),
    '551': ('ativo', 'RO40000001', 'DÉBITO DE DIFERENCIAL DE ALÍQUOTA DE ATIVO PERMANENTE', False),
    '406': ('ativo', 'RO40000001', 'DÉBITO DE DIFERENCIAL DE ALÍQUOTA DE ATIVO PERMANENTE', True),
}
OBS = {'uso': ('DIFUC', 'DIFERENCIAL DE ALIQUOTA - MATERIAL DE USO E CONSUMO'),
       'ativo': ('DIFAP', 'DIFERENCIAL DE ALIQUOTA - ATIVO PERMANENTE')}
COD_DIFAL_APUR = {'RO40000001', 'RO40000002'}
COD_DIFAL_FORA = {'RO90000002'}
FILHOS_C100 = {'C101', 'C105', 'C110', 'C111', 'C112', 'C113', 'C114', 'C115', 'C116', 'C120', 'C130', 'C140', 'C141',
               'C160', 'C165', 'C170', 'C171', 'C172', 'C173', 'C174', 'C175', 'C176', 'C177', 'C178', 'C179', 'C180',
               'C181', 'C185', 'C186', 'C190', 'C191', 'C195', 'C197'}


# ------------------------------------------------------------------ utilidades
def _d(v):
    return Decimal(str(v)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _n(s):
    s = (s or '').strip()
    if not s:
        return 0.0
    try:
        return float(s.replace('.', '').replace(',', '.')) if ',' in s else float(s)
    except ValueError:
        return 0.0


def _f(v):
    return f'{_d(v):.2f}'.replace('.', ',')


def _ler(path):
    raw = open(path, 'rb').read()
    try:
        return raw.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError:
        return raw.decode('latin-1'), 'latin-1'


def aliq_interna_padrao(dt_ini):
    """dt_ini ddmmaaaa -> alíquota interna geral de RO no período (Lei 688/96, art. 27, I, 'c')."""
    if len(dt_ini or '') == 8 and dt_ini[4:] + dt_ini[2:4] + dt_ini[:2] >= '20240112':
        return 19.5
    return 17.5


def base_dupla(dt_ini):
    return len(dt_ini or '') != 8 or dt_ini[4:] + dt_ini[2:4] >= '202204'


def calcular_difal(valor, aliq_inter, aliq_interna, dupla=True):
    """Devolve (base, difal). Base dupla (Lei 688/96, art. 18, IX, §§ 1º e 7º):
    ICMS origem = V × inter; base destino = (V − ICMS origem) ÷ (1 − interna); DIFAL = base × interna − ICMS origem.
    Base única (antes de 04/2022): base = V; DIFAL = V × (interna − inter)."""
    v, ai, an = Decimal(str(valor)), Decimal(str(aliq_inter)) / 100, Decimal(str(aliq_interna)) / 100
    if an <= ai or v <= 0:
        return (_d(v), _d(0))
    if dupla:
        icms_orig = v * ai
        base = (v - icms_orig) / (1 - an)
        return (_d(base), _d(base * an - icms_orig))
    return (_d(v), _d(v * (an - ai)))


def _aliq_inter(c190_aliq, cst, uf_orig):
    if c190_aliq in (4.0, 7.0, 12.0):
        return c190_aliq, 'alíquota da nota'
    orig = cst[:1] if len(cst) == 3 else ''
    if orig in ORIGEM_IMPORTADA:
        return 4.0, 'produto importado (origem ' + orig + ')'
    if uf_orig in SUL_SUDESTE_SEM_ES:
        return 7.0, 'remetente do Sul/Sudeste'
    return 12.0, 'regra geral interestadual'


# ------------------------------------------------------------------ leitura
def _estrutura(linhas):
    cab, part, obs460 = {}, {}, {}
    docs = []
    e110 = None
    e111_difal = []
    cur = None
    for i, ln in enumerate(linhas):
        c = ln.split('|')
        if len(c) < 3:
            continue
        r = c[1]
        if r == '0000':
            cab = {'cod_ver': c[2], 'dt_ini': c[4], 'dt_fin': c[5], 'nome': c[6], 'cnpj': c[7], 'uf': c[9] if len(c) > 9 else ''}
        elif r == '0150' and len(c) > 8:
            part[c[2]] = {'nome': c[3], 'pais': c[4], 'cnpj': c[5] or c[6], 'mun': c[8]}
        elif r == '0460' and len(c) > 3:
            obs460[c[2]] = c[3]
        elif r == 'C100':
            cur = {'i': i, 'fim': i, 'oper': c[2], 'emit': c[3], 'part': c[4], 'mod': c[5], 'sit': c[6], 'serie': c[7],
                   'num': c[8], 'chave': c[9] if len(c) > 9 else '', 'dt': (c[11] if len(c) > 11 and c[11] else (c[10] if len(c) > 10 else '')),
                   'c170': [], 'c190': [], 'c197': [], 'c195': []}
            docs.append(cur)
        elif cur is not None and r in FILHOS_C100:
            cur['fim'] = i
            if r == 'C170' and len(c) > 11:
                cur['c170'].append({'i': i, 'cst': c[10], 'cfop': c[11], 'vl': _n(c[7]) - _n(c[8]), 'item': c[3], 'descr': c[4],
                                    'bc': _n(c[13]) if len(c) > 15 else 0.0, 'aliq': _n(c[14]) if len(c) > 15 else 0.0,
                                    'icms': _n(c[15]) if len(c) > 15 else 0.0})
            elif r == 'C190' and len(c) > 7:
                cur['c190'].append({'i': i, 'cst': c[2], 'cfop': c[3], 'aliq': _n(c[4]), 'vl_opr': _n(c[5]), 'vl_bc': _n(c[6]), 'vl_icms': _n(c[7])})
            elif r == 'C195':
                cur['c195'].append({'i': i, 'cod_obs': c[2] if len(c) > 2 else ''})
            elif r == 'C197' and len(c) > 7:
                cur['c197'].append({'i': i, 'cod': c[2], 'bc': _n(c[5]), 'aliq': _n(c[6]), 'icms': _n(c[7]), 'outros': _n(c[8]) if len(c) > 8 else 0.0})
        else:
            cur = None          # qualquer registro que não é filho do C100 encerra o documento atual
            if r == 'E110' and len(c) > 15:
                e110 = {'i': i, 'c': c}
            elif r == 'E111' and len(c) > 4 and re.search(r'DIF(ERENCIAL|AL)', (c[3] or '').upper()):
                e111_difal.append({'cod': c[2], 'descr': c[3], 'valor': _n(c[4])})
    return cab, part, obs460, docs, e110, e111_difal


def _e111_estornos(linhas):
    """E111 de estorno de crédito (ICMS próprio: 3º caractere 0, 4º caractere 1)."""
    out = []
    for ln in linhas:
        c = ln.split('|')
        if len(c) > 4 and c[1] == 'E111' and len(c[2]) == 8 and c[2][2:4] == '01':
            out.append({'cod': c[2], 'descr': c[3], 'valor': _n(c[4]), 'uso': bool(re.search(r'USO|CONSUMO', (c[3] or '').upper()))})
    return out


def codigos_estorno(uf):
    """Códigos de estorno de crédito (ICMS próprio) da tabela 5.1.1 da UF."""
    try:
        from tabela_ajustes_dados import TABELA_5_1_1
    except Exception:
        return []
    tab = TABELA_5_1_1.get(uf or '', {})
    return [{'cod': k, 'descr': v} for k, v in sorted(tab.items()) if k[2:4] == '01']


def _uf_emitente(doc, part):
    ch = re.sub(r'\D', '', doc['chave'] or '')
    if len(ch) == 44 and ch[:2] in UF_IBGE:
        return UF_IBGE[ch[:2]], 'chave de acesso'
    p = part.get(doc['part'], {})
    if p.get('pais') and p['pais'] not in ('1058', '01058'):
        return 'EX', 'participante do exterior'
    mun = re.sub(r'\D', '', p.get('mun', ''))
    if len(mun) == 7 and mun[:2] in UF_IBGE:
        return UF_IBGE[mun[:2]], 'município do participante'
    return '', ''


# ------------------------------------------------------------------ análise
def analisar_texto(texto):
    linhas = texto.splitlines()
    cab, part, obs460, docs, e110, e111_difal = _estrutura(linhas)
    uf_emp = (cab.get('uf') or '').strip()
    dupla = base_dupla(cab.get('dt_ini'))
    interna = aliq_interna_padrao(cab.get('dt_ini'))
    avisos = []
    if uf_emp != 'RO':
        avisos.append(f'Este SPED é de {uf_emp or "UF não informada"}: o cálculo e os códigos de lançamento são os de Rondônia. '
                      'Para outra UF a correção do CFOP vale, mas o DIFAL não deve ser incluído por aqui.')
    if e111_difal:
        tot = sum(x['valor'] for x in e111_difal)
        avisos.append(f'Já existe DIFAL lançado direto no E111 ({len(e111_difal)} ajuste(s), R$ {_f(tot)}). Confira se ele já cobre as notas '
                      'abaixo antes de incluir pelo C197, para não cobrar duas vezes. Pelo manual da SEFIN/RO o lançamento correto é no C197.')
    saida = []
    for d in docs:
        if d['oper'] != '0':
            continue
        alvo = [x for x in d['c190'] if x['cfop'][1:] in TIPOS and x['cfop'][:1] in '12']
        if not alvo:
            continue
        uf_or, fonte_uf = _uf_emitente(d, part)
        p = part.get(d['part'], {})
        interestadual = bool(uf_or) and uf_or not in (uf_emp, 'EX')
        if not interestadual and uf_or and all(x['cfop'][:1] == '1' for x in alvo):
            continue        # compra interna já com CFOP 1.xxx: nada a conferir
        correcoes = []
        for cf in sorted({x['cfop'] for x in alvo}):
            novo = ('2' if interestadual else '1') + cf[1:] if uf_or and uf_or != 'EX' else cf
            if novo != cf:
                correcoes.append({'de': cf, 'para': novo})
        # grupos por (tipo, alíquota interestadual)
        grupos = {}
        tem_st = False
        cst_sem_trib = False
        for x in alvo:
            tipo, cod_aj, descr, st = TIPOS[x['cfop'][1:]]
            tem_st = tem_st or st or x['cst'][-2:] in ('10', '30', '60', '70')
            cst_sem_trib = cst_sem_trib or x['cst'][-2:] in ('40', '41', '50')
            ai, fonte_ai = _aliq_inter(x['aliq'], x['cst'], uf_or)
            g = grupos.setdefault((tipo, ai), {'tipo': tipo, 'cod_aj': cod_aj, 'descr': descr, 'aliq_inter': ai, 'fonte_aliq': fonte_ai,
                                               'aliq_interna': interna, 'valor': 0.0, 'cfops': set()})
            g['valor'] += x['vl_opr']
            g['cfops'].add(x['cfop'])
        lista_g = []
        for g in grupos.values():
            base, dif = calcular_difal(g['valor'], g['aliq_inter'], g['aliq_interna'], dupla)
            lista_g.append({**g, 'cfops': sorted(g['cfops']), 'valor': float(_d(g['valor'])), 'base': float(base), 'difal': float(dif)})
        calc = float(_d(sum(g['difal'] for g in lista_g))) if interestadual else 0.0
        existente = float(_d(sum(x['icms'] for x in d['c197'] if x['cod'] in COD_DIFAL_APUR)))
        fora = float(_d(sum(x['icms'] for x in d['c197'] if x['cod'] in COD_DIFAL_FORA)))
        obs_doc = []
        if d['sit'] in CANC:
            status = 'cancelada'
        elif not interestadual:
            status = 'interna' if uf_or else 'sem_uf'
        elif existente > 0:
            status = 'ok' if abs(existente - calc) <= 0.05 else 'divergente'
        elif fora > 0:
            status = 'pago_fora'
        else:
            status = 'faltando'
        if d['sit'] in EXTEMP:
            obs_doc.append('Documento extemporâneo: o DIFAL vai no débito especial, não no campo 03 do E110. Não incluir por aqui.')
        if tem_st and interestadual:
            obs_doc.append('Há item com substituição tributária: se o ICMS-ST para RO foi retido na nota, o diferencial normalmente já está nele. Confira antes de incluir.')
        if cst_sem_trib and interestadual:
            obs_doc.append('Há item isento/não tributado na origem: confira se há benefício que afaste ou reduza o DIFAL.')
        if any(x['vl_icms'] > 0 for x in alvo):
            obs_doc.append('A nota tem crédito de ICMS tomado: veja o quadro "Crédito de ICMS em uso e consumo".')
        if not uf_or:
            obs_doc.append('Não foi possível identificar a UF do emitente (sem chave de acesso e sem município no cadastro do participante).')
        sugerido_cfop = bool(correcoes) and d['sit'] not in CANC
        sugerido_difal = status in ('faltando', 'divergente') and d['sit'] not in CANC and d['sit'] not in EXTEMP and not tem_st and not cst_sem_trib and uf_emp == 'RO'
        saida.append({
            'id': d['i'], 'num': d['num'], 'serie': d['serie'], 'chave': d['chave'], 'data': d['dt'], 'sit': d['sit'],
            'fornecedor': p.get('nome', d['part']), 'cnpj': p.get('cnpj', ''), 'uf_origem': uf_or, 'fonte_uf': fonte_uf,
            'interestadual': interestadual, 'correcoes_cfop': correcoes, 'grupos': lista_g,
            'difal_calculado': calc, 'difal_lancado': existente, 'difal_pago_fora': fora, 'status': status,
            'obs': obs_doc, 'sugerido_cfop': sugerido_cfop, 'sugerido_difal': sugerido_difal,
        })
    prod = {c[2]: c[3] for c in (ln.split('|') for ln in linhas if ln.startswith('|0200|')) if len(c) > 3}
    creditos = _analisar_creditos(docs, part, uf_emp, prod)
    est_ex = _e111_estornos(linhas)
    if creditos['docs'] and any(x['uso'] for x in est_ex):
        tot = sum(x['valor'] for x in est_ex if x['uso'])
        avisos.append(f'Já existe estorno de crédito de uso e consumo no E111 (R$ {_f(tot)}). Confira se ele já cobre as notas do quadro de '
                      'crédito, para não estornar duas vezes.')
    # Guia Prático, E110 campo 03: soma do VL_ICMS dos C197/C597/C857/C897/D197/D737 com 3º caractere 3, 4 ou 5 e
    # 4º caractere 0, 3, 4, 5, 6, 7 ou 8 (sem documentos extemporâneos). Confere se o arquivo original já fechava.
    soma03, sit_doc = Decimal('0'), ''
    for ln in linhas:
        c = ln.split('|')
        if len(c) < 3:
            continue
        if c[1] in ('C100', 'C500', 'C800', 'D100', 'D700'):
            sit_doc = c[6] if c[1] in ('C100', 'D100') and len(c) > 6 else (c[5] if len(c) > 5 else '')
        elif c[1] in ('C197', 'C597', 'C857', 'C897', 'D197', 'D737') and len(c) > 7:
            cod = c[2]
            if len(cod) >= 4 and cod[2] in '345' and cod[3] in '0345678' and sit_doc not in EXTEMP and sit_doc not in CANC:
                soma03 += Decimal(str(_n(c[7])))
    apur = None
    if e110:
        c = e110['c']
        apur = {k: _n(c[i]) for i, k in enumerate(['deb', 'aj_deb', 'tot_aj_deb', 'est_cred', 'cred', 'aj_cred', 'tot_aj_cred', 'est_deb',
                                                    'sld_ant', 'sld_apurado', 'ded', 'recolher', 'sld_transp', 'deb_esp'], start=2)}
        apur['aj_deb_esperado'] = float(_d(soma03))
        if abs(apur['aj_deb'] - float(soma03)) > 0.05:
            avisos.append(f'No arquivo original, o campo 03 do E110 (R$ {_f(apur["aj_deb"])}) já não fecha com a soma dos ajustes das notas '
                          f'(C197 e similares: R$ {_f(soma03)}). O sistema soma só o DIFAL incluído agora; essa diferença antiga continua e '
                          'deve ser revista antes de transmitir.')
    e116 = []
    for ln in linhas:
        c = ln.split('|')
        if len(c) > 5 and c[1] == 'E116':
            e116.append({'cod': c[2], 'valor': _n(c[3]), 'venc': c[4], 'cod_rec': c[5]})
    return {
        'empresa': {'nome': cab.get('nome', ''), 'cnpj': cab.get('cnpj', ''), 'uf': uf_emp, 'dt_ini': cab.get('dt_ini', ''), 'dt_fin': cab.get('dt_fin', ''),
                    'cod_ver': cab.get('cod_ver', '')},
        'base_dupla': dupla, 'aliq_interna_padrao': interna, 'docs': saida, 'avisos': avisos, 'e110': apur, 'e116': e116,
        'e111_difal': e111_difal, 'creditos': creditos,
        'resumo': {
            'notas': len(saida),
            'cfop_errado': sum(1 for x in saida if x['correcoes_cfop']),
            'faltando': sum(1 for x in saida if x['status'] == 'faltando'),
            'divergente': sum(1 for x in saida if x['status'] == 'divergente'),
            'ok': sum(1 for x in saida if x['status'] == 'ok'),
            'pago_fora': sum(1 for x in saida if x['status'] == 'pago_fora'),
            'difal_faltando': float(_d(sum(x['difal_calculado'] for x in saida if x['status'] == 'faltando'))),
        },
    }


def _analisar_creditos(docs, part, uf_emp, prod=None):
    """Entradas de uso e consumo (x.556/x.407) e ativo (x.551/x.406) com ICMS creditado no C190.
    LC 87/96, art. 33, I (redação da LC 171/2019): crédito de uso e consumo só a partir de 01/01/2033.
    LC 87/96, art. 20, § 5º: o crédito do ativo é apropriado em 48 parcelas (CIAP, Bloco G), não na nota."""
    out = []
    for d in docs:
        if d['oper'] != '0' or d['sit'] in CANC:
            continue
        alvo = [x for x in d['c190'] if x['cfop'][1:] in TIPOS and x['cfop'][:1] in '123' and x['vl_icms'] > 0.004]
        if not alvo:
            continue
        cfops = {x['cfop'] for x in alvo}
        uf_or, _ = _uf_emitente(d, part)
        p = part.get(d['part'], {})
        tipos = {TIPOS[x['cfop'][1:]][0] for x in alvo}
        tipo = 'ativo' if tipos == {'ativo'} else ('misto' if len(tipos) > 1 else 'uso')
        itens = [{'item': x['item'], 'descr': x['descr'] or (prod or {}).get(x['item'], ''), 'cfop': x['cfop'], 'cst': x['cst'], 'valor': float(_d(x['vl'])),
                  'bc': x['bc'], 'aliq': x['aliq'], 'icms': x['icms']}
                 for x in d['c170'] if x['cfop'] in cfops and x['icms'] > 0.004]
        obs = []
        if 'ativo' in tipos:
            obs.append('Ativo imobilizado: o crédito vem pelo CIAP em 48 parcelas (Bloco G), não direto na nota. Se a empresa controla o CIAP, '
                       'retire o crédito da nota e confira o G125.')
        if not d['c170']:
            obs.append('Nota sem itens (C170): a correção é feita no resumo da nota (C190).')
        if d['sit'] in EXTEMP:
            obs.append('Documento extemporâneo.')
        out.append({
            'id': d['i'], 'num': d['num'], 'serie': d['serie'], 'data': d['dt'], 'sit': d['sit'],
            'fornecedor': p.get('nome', d['part']), 'cnpj': p.get('cnpj', ''), 'uf_origem': uf_or, 'tipo': tipo,
            'c190': [{'cst': x['cst'], 'cfop': x['cfop'], 'aliq': x['aliq'], 'vl_opr': x['vl_opr'], 'bc': x['vl_bc'], 'icms': x['vl_icms']} for x in alvo],
            'itens': itens,
            'valor': float(_d(sum(x['vl_opr'] for x in alvo))),
            'credito': float(_d(sum(x['vl_icms'] for x in alvo))),
            'difal_lancado': float(_d(sum(x['icms'] for x in d['c197'] if x['cod'] in COD_DIFAL_APUR))),
            'sugerido': tipo == 'uso',
            'obs': obs,
        })
    cods = codigos_estorno(uf_emp)
    padrao = next((c['cod'] for c in cods if c['cod'] == f'{uf_emp}010011'), None) or \
        next((c['cod'] for c in cods if c['cod'].endswith('9999')), None) or (cods[0]['cod'] if cods else '')
    return {'docs': out, 'codigos_estorno': cods, 'cod_estorno_padrao': padrao,
            'total': float(_d(sum(x['credito'] for x in out))),
            'total_uso': float(_d(sum(x['credito'] for x in out if x['sugerido'])))}


# ------------------------------------------------------------------ aplicação
CAMPOS_E110 = (('aj_deb', 3), ('est_cred', 5), ('cred', 6), ('sld_apurado', 11), ('recolher', 13), ('sld_transp', 14))


def _novo_e110(c, deltas):
    """deltas = {campo: valor} somado aos campos 03 (ajustes a débito), 05 (estornos de crédito) ou 06 (créditos)."""
    v = [Decimal('0')] * 16
    for i in range(2, 16):
        v[i] = Decimal(str(_n(c[i])))
    for i, dv in deltas.items():
        v[i] += Decimal(str(dv))
    expr = (v[2] + v[3] + v[4] + v[5]) - (v[6] + v[7] + v[8] + v[9] + v[10])     # Guia Prático, E110 campos 11 e 14
    v[11] = expr if expr >= 0 else Decimal('0')
    v[13] = max(Decimal('0'), v[11] - v[12])                                         # campo 13
    resto = expr - v[12]
    v[14] = -resto if resto < 0 else Decimal('0')                                    # campo 14
    novo = list(c)
    for i in set(deltas) | {11, 13, 14}:
        novo[i] = _f(v[i])
    return novo, {k: float(_d(v[i])) for k, i in CAMPOS_E110}


def _junta_c190(linhas, d, remover):
    """C190 não pode repetir a combinação CST + CFOP + alíquota: junta as linhas repetidas da nota."""
    vistos = {}
    for x in d['c190']:
        if x['i'] in remover:
            continue
        c = linhas[x['i']].split('|')
        k = (c[2], c[3], _f(_n(c[4])))
        if k in vistos:
            alvo = linhas[vistos[k]].split('|')
            for j in range(5, min(len(c), len(alvo))):
                if j in (5, 6, 7, 8, 9, 10, 11):
                    alvo[j] = _f(_n(alvo[j]) + _n(c[j]))
            linhas[vistos[k]] = '|'.join(alvo)
            remover.add(x['i'])
        else:
            vistos[k] = x['i']


def aplicar_texto(texto, selecao):
    """selecao = {'docs': [{'id', 'corrigir_cfop', 'incluir_difal', 'grupos': [{'tipo','aliq_inter','aliq_interna'}]}],
                  'creditos': {'modo': 'zerar' | 'estorno', 'cod_aj': 'RO010011', 'docs': [id, ...]},
                  'e116': {'cod_rec': '', 'venc': 'ddmmaaaa'}}  ->  (texto_novo, resumo)"""
    from fiscal_core import _recalcula_bloco9_global, _recalcula_fechamentos_bloco
    quebra = '\r\n' if '\r\n' in texto else '\n'
    final_vazio = texto.endswith(quebra)
    linhas = texto.split(quebra)
    if final_vazio:
        linhas = linhas[:-1]
    an = analisar_texto(texto)
    por_id = {d['id']: d for d in an['docs']}
    cab, part, obs460, docs, e110, _ = _estrutura(linhas)
    docs_por_i = {d['i']: d for d in docs}
    v020 = (cab.get('cod_ver') or '0') >= '020'
    dupla = an['base_dupla']
    resumo = {'cfop_corrigidos': 0, 'notas_cfop': 0, 'difal_incluidos': 0, 'difal_total': 0.0, 'difal_removido': 0.0,
              'c197_inseridos': 0, 'c195_inseridos': 0, 'obs_0460_criados': [], 'e110_antes': None, 'e110_depois': None,
              'e116': '', 'detalhe': [], 'avisos': [],
              'cred_modo': '', 'cred_notas': 0, 'cred_c170': 0, 'cred_c190': 0, 'cred_total': 0.0, 'cred_e111': ''}
    insercoes = {}      # índice da última linha do documento -> linhas a inserir depois dela
    remover = set()
    usados_obs = set()

    for sel in selecao.get('docs', []):
        a = por_id.get(sel.get('id'))
        d = docs_por_i.get(sel.get('id'))
        if not a or not d:
            continue
        mapa = {x['de']: x['para'] for x in a['correcoes_cfop']} if sel.get('corrigir_cfop') else {}
        if mapa:
            resumo['notas_cfop'] += 1
            for reg, campo in (('c170', 11), ('c190', 3)):
                for x in d[reg]:
                    if x['cfop'] in mapa:
                        c = linhas[x['i']].split('|')
                        c[campo] = mapa[x['cfop']]
                        linhas[x['i']] = '|'.join(c)
                        resumo['cfop_corrigidos'] += 1
            _junta_c190(linhas, d, remover)
        if sel.get('incluir_difal') and a['interestadual'] and an['empresa']['uf'] == 'RO':
            ed = {(g.get('tipo'), float(g.get('aliq_inter'))): g for g in sel.get('grupos', [])}
            novos = []
            for g in a['grupos']:
                e = ed.get((g['tipo'], float(g['aliq_inter'])), {})
                ai = float(e.get('aliq_inter_nova', g['aliq_inter']))
                an_ = float(e.get('aliq_interna', g['aliq_interna']))
                base, dif = calcular_difal(g['valor'], ai, an_, dupla)
                if dif <= 0:
                    continue
                novos.append((g, base, dif, ai, an_))
            if not novos:
                continue
            # substitui lançamento anterior de DIFAL na apuração (se houver) pelo recalculado
            for x in d['c197']:
                if x['cod'] in COD_DIFAL_APUR:
                    remover.add(x['i'])
                    resumo['difal_removido'] += x['icms']
            # C195 que ficou sem nenhum C197 depois da remoção (era só do DIFAL antigo) também sai
            for k, c195 in enumerate(d['c195']):
                prox = d['c195'][k + 1]['i'] if k + 1 < len(d['c195']) else d['fim'] + 1
                filhos = [x for x in d['c197'] if c195['i'] < x['i'] < prox]
                if filhos and all(x['i'] in remover for x in filhos):
                    remover.add(c195['i'])
            bloco = []
            for tipo in ('uso', 'ativo'):
                gs = [n for n in novos if n[0]['tipo'] == tipo]
                if not gs:
                    continue
                cod_obs = next((k for k, t in obs460.items() if 'DIFERENCIAL' in t.upper() and (('USO' in t.upper()) if tipo == 'uso' else ('ATIVO' in t.upper()))), None)
                if not cod_obs:
                    cod_obs = OBS[tipo][0]
                    if cod_obs not in obs460:
                        obs460[cod_obs] = OBS[tipo][1]
                        resumo['obs_0460_criados'].append(cod_obs)
                usados_obs.add(cod_obs)
                bloco.append(f'|C195|{cod_obs}||')
                resumo['c195_inseridos'] += 1
                for g, base, dif, ai, an_ in gs:
                    campos = ['', 'C197', g['cod_aj'], g['descr'], '', _f(base), _f(ai), _f(dif), _f(an_)]
                    if v020:
                        campos.append('0')
                    bloco.append('|'.join(campos) + '|')
                    resumo['c197_inseridos'] += 1
                    resumo['difal_total'] += float(dif)
            insercoes.setdefault(d['fim'], []).extend(bloco)
            resumo['difal_incluidos'] += 1
            resumo['detalhe'].append({'num': a['num'], 'fornecedor': a['fornecedor'], 'uf': a['uf_origem'],
                                      'difal': float(_d(sum(n[2] for n in novos)))})

    # crédito de ICMS em uso e consumo / ativo (LC 87/96, art. 33, I; art. 20, § 5º)
    cred = selecao.get('creditos') or {}
    cred_por_id = {x['id']: x for x in an['creditos']['docs']}
    modo = cred.get('modo') or 'zerar'
    d05 = d06 = Decimal('0')
    nums = []
    for cid in cred.get('docs', []):
        a, d = cred_por_id.get(cid), docs_por_i.get(cid)
        if not a or not d:
            continue
        resumo['cred_notas'] += 1
        nums.append(a['num'])
        if modo == 'estorno':
            d05 += Decimal(str(a['credito']))
            continue
        for x in d['c170']:
            c = linhas[x['i']].split('|')
            if len(c) > 15 and c[11][1:] in TIPOS and c[11][:1] in '123' and _n(c[15]) > 0.004:
                c[13] = c[14] = c[15] = '0,00'
                linhas[x['i']] = '|'.join(c)
                resumo['cred_c170'] += 1
        bc_tot = icms_tot = Decimal('0')
        for x in d['c190']:
            if x['i'] in remover:
                continue
            c = linhas[x['i']].split('|')
            if len(c) > 7 and c[3][1:] in TIPOS and c[3][:1] in '123' and _n(c[7]) > 0.004:
                bc_tot += Decimal(str(_n(c[6])))
                icms_tot += Decimal(str(_n(c[7])))
                c[4], c[6], c[7] = '0,00', '0,00', '0,00'
                linhas[x['i']] = '|'.join(c)
                resumo['cred_c190'] += 1
        _junta_c190(linhas, d, remover)
        c = linhas[d['i']].split('|')
        if len(c) > 22:
            c[21] = _f(max(Decimal('0'), Decimal(str(_n(c[21]))) - bc_tot))
            c[22] = _f(max(Decimal('0'), Decimal(str(_n(c[22]))) - icms_tot))
            linhas[d['i']] = '|'.join(c)
        d06 -= icms_tot
    novas_e111 = []
    if resumo['cred_notas']:
        resumo['cred_modo'] = modo
        if modo == 'estorno' and d05 > 0:
            cod = (cred.get('cod_aj') or an['creditos']['cod_estorno_padrao'] or '').strip().upper()
            if len(cod) != 8 or cod[2:4] != '01':
                return texto, {'erro': 'Escolha um código de ajuste de estorno de crédito válido (E111, 3º e 4º caracteres "01").'}
            lista = ', '.join(nums[:12]) + (f' E MAIS {len(nums) - 12}' if len(nums) > 12 else '')
            descr = f'ESTORNO DE CREDITO DE ICMS DE MATERIAL DE USO E CONSUMO/ATIVO (LC 87/96, ART. 33, I E ART. 20, PAR. 5) - NF {lista}'
            novas_e111.append(f'|E111|{cod}|{descr}|{_f(d05)}|')
            resumo['cred_e111'] = f'E111 {cod} de R$ {_f(d05)} incluído (estorno de crédito, campo 05 do E110).'
        resumo['cred_total'] = float(_d(d05 if modo == 'estorno' else -d06))

    delta = float(_d(resumo['difal_total'] - resumo['difal_removido']))
    deltas = {k: float(v) for k, v in ((3, Decimal(str(delta))), (5, d05), (6, d06)) if abs(v) >= Decimal('0.005')}
    # E110 / E116
    novas_e116 = []
    if e110 and deltas:
        c = linhas[e110['i']].split('|')
        antes = {k: _n(c[i]) for k, i in CAMPOS_E110}
        novo, depois = _novo_e110(c, deltas)
        linhas[e110['i']] = '|'.join(novo)
        resumo['e110_antes'], resumo['e110_depois'] = antes, depois
        d13 = Decimal(str(depois['recolher'])) - Decimal(str(antes['recolher']))
        if d13 != 0:
            idx_000 = [i for i, l in enumerate(linhas) if l.startswith('|E116|000|') and i not in remover]
            if idx_000:
                c = linhas[idx_000[0]].split('|')
                nv = Decimal(str(_n(c[3]))) + d13
                c[3] = _f(nv)
                linhas[idx_000[0]] = '|'.join(c)
                resumo['e116'] = f'Obrigação 000 (ICMS a recolher) ajustada para R$ {_f(nv)}.'
            elif depois['recolher'] > 0:
                e = selecao.get('e116') or {}
                venc = re.sub(r'\D', '', e.get('venc', ''))
                cod_rec = (e.get('cod_rec') or '').strip()
                if len(venc) != 8 or not cod_rec:
                    return texto, {'erro': 'Com a correção a empresa passa a ter ICMS a recolher e o SPED não tem guia (E116) de ICMS normal. '
                                           'Informe o vencimento e o código de receita da guia para continuar.'}
                mes_ref = (cab.get('dt_ini') or '')[2:]
                novas_e116.append(f'|E116|000|{_f(depois["recolher"])}|{venc}|{cod_rec}||||ICMS A RECOLHER|{mes_ref}|')
                resumo['e116'] = f'Guia (E116) de ICMS a recolher criada: R$ {_f(depois["recolher"])}, vencimento {venc[:2]}/{venc[2:4]}/{venc[4:]}.'
        if depois['sld_transp'] != antes['sld_transp']:
            resumo['avisos'].append(f'O saldo credor a transportar mudou de R$ {_f(antes["sld_transp"])} para R$ {_f(depois["sld_transp"])}: '
                                    'o SPED do mês seguinte precisa receber esse novo saldo credor anterior.')
    elif deltas:
        return texto, {'erro': 'O SPED não tem o registro E110 (apuração do ICMS); não dá para lançar a correção.'}

    # monta o arquivo novo
    saida = []
    obs_novos = [f'|0460|{k}|{obs460[k]}|' for k in resumo['obs_0460_criados']]
    pos_0460 = None
    ultimo_bloco0 = None
    for i, l in enumerate(linhas):
        r = l.split('|')[1] if l.count('|') >= 2 else ''
        if r in ('0400', '0450', '0460'):
            pos_0460 = i
        if r.startswith('0') and r not in ('0990',):
            ultimo_bloco0 = i if r in ('0000', '0001', '0002', '0005', '0015', '0100', '0150', '0175', '0190', '0200', '0205', '0206', '0210',
                                          '0220', '0221', '0300', '0305', '0400', '0450', '0460') else ultimo_bloco0
    if obs_novos and pos_0460 is None:
        pos_0460 = ultimo_bloco0
    pos_e116 = pos_e111 = None
    for i, l in enumerate(linhas):
        if l[:6] in ('|E110|', '|E111|', '|E112|', '|E113|', '|E115|', '|E116|'):
            pos_e116 = i
        if l[:6] in ('|E110|', '|E111|', '|E112|', '|E113|'):
            pos_e111 = i
    for i, l in enumerate(linhas):
        if i not in remover:
            saida.append(l)
        if i == pos_0460 and obs_novos:
            saida.extend(obs_novos)
        if i in insercoes:
            saida.extend(insercoes[i])
        if i == pos_e111 and novas_e111:
            saida.extend(novas_e111)
        if i == pos_e116 and novas_e116:
            saida.extend(novas_e116)
    saida = _recalcula_bloco9_global(saida)
    saida = _recalcula_fechamentos_bloco(saida)
    resumo['difal_total'] = float(_d(resumo['difal_total']))
    resumo['difal_removido'] = float(_d(resumo['difal_removido']))
    resumo['delta_e110'] = delta
    return quebra.join(saida) + (quebra if final_vazio else ''), resumo


# ------------------------------------------------------------------ CLI
def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    sped, js = opt('--sped'), opt('--json')
    if not sped or not js:
        print('uso: difal-ro --sped ARQ.txt --json saida.json [--aplicar selecao.json --saida novo.txt]'); return 1
    texto, enc = _ler(sped)
    try:
        if opt('--aplicar'):
            with open(opt('--aplicar'), 'r', encoding='utf-8') as fh:
                sel = json.load(fh)
            novo, res = aplicar_texto(texto, sel)
            if not res.get('erro'):
                tmp = opt('--saida') + '.parcial'
                with open(tmp, 'w', encoding=enc, newline='') as fh:
                    fh.write(novo)
                os.replace(tmp, opt('--saida'))
        else:
            res = analisar_texto(texto)
    except Exception as e:  # pragma: no cover
        res = {'erro': f'Falha ao processar o SPED: {e}'}
    tmp = js + '.parcial'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False)
    os.replace(tmp, js)
    return 0


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main_cli(sys.argv[1:]))

# -*- coding: utf-8 -*-
"""DIFAL do Acre — uso e consumo e ativo imobilizado vindos de outro estado (empresa do AC, UF do registro 0000).
Etapa do Corretor do SPED Fiscal (EM TESTE, só Admin). Gera arquivo NOVO; o original nunca é alterado.

Cálculo (base dupla, com o imposto por dentro)
  • LC 55/1997 (AC), art. 6º, XI e §§ 7º e 8º, e art. 8º (redação da LC 417/2022, DOE 19/12/2022);
  • RICMS-AC (Decreto 8/1998), art. 5º, IX-A e §§ 8º e 9º, e art. 7º (Decreto 11.206/2023, DOE 24/03/2023):
      ICMS origem = V × interestadual; base de destino = (V − ICMS origem) ÷ (1 − interna); DIFAL = base × interna − ICMS origem.
    Antes de 24/03/2023: base única (art. 5º, IX, "c"): DIFAL = V × (interna − interestadual).
  • Alíquota interna 19% desde 01/04/2023 (LC 55/1997, art. 18, I, redação da LC 422/2022); antes, 17%.
  • RICMS-AC, art. 97: § 3º o frete entra na base (incisos I e II); § 5º fornecedor do Simples: abate a alíquota interestadual
    cheia; § 7º-B (Decreto 11.852/2026) sem DIFAL na transferência entre estabelecimentos da mesma empresa.
    Os §§ 2º e 6º (base de origem) valem só para os incisos III a V (cesta básica, insumo), não para uso/consumo e ativo.
  • V = valor do item − desconto + frete + seguro + outras despesas + IPI (XML, quando anexado; sem XML, rateio do C100).

Escrituração (Manual da EFD do AC — IN DIAT 2/2018, itens 8 e 9; Tabela 5.3) — "estabelecimento detentor de regime especial":
  nota sem crédito com CST 90; 0460 + C195; um C197 por item: AC70000001 (ativo) / AC70000002 (uso e consumo), COD_ITEM,
  VL_BC_ICMS = base do DIFAL, ALIQ_ICMS = interestadual, VL_ICMS = DIFAL, DESCR_COMPL_AJ e VL_OUTROS em branco;
  soma no campo 15 (DEB_ESP) do E110; E116 com COD_REC 1642 (ativo) / 1641 (uso e consumo), MES_REF mmaaaa.
  Vencimento: dia 20 do mês seguinte (RICMS-AC, art. 93, IV, "f", c/c art. 97-B, II, "b").
  Sem regime especial o DIFAL é notificado na entrada (art. 93, VI) e o manual não prevê lançamento: a etapa só confere.
"""
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP

import difal_ro as dr

TIPOS = {'556': 'uso', '407': 'uso', '551': 'ativo', '406': 'ativo'}
COD = {'uso': 'AC70000002', 'ativo': 'AC70000001'}
COD_REC = {'uso': '1641', 'ativo': '1642'}
TXT_OBS = {'uso': 'Diferencial de Alíquotas Uso e Consumo', 'ativo': 'Diferencial de Alíquotas Ativo Imobilizado'}
OBS_PADRAO = {'uso': 'DIFUC', 'ativo': 'DIFAI'}
INICIO_BASE_DUPLA = '20230324'          # Decreto 11.206/2023 (DOE 24/03/2023)
INICIO_19 = '20230401'                  # LC 422/2022
CANC = {'02', '03', '04', '05'}
EXTEMP = {'01', '07', '10'}


def _d(v):
    return Decimal(str(v)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _n(s):
    return dr._n(s)


def _f(v):
    return dr._f(v)


def _aaaammdd(dt):
    dt = re.sub(r'\D', '', dt or '')
    return dt[4:] + dt[2:4] + dt[:2] if len(dt) == 8 else ''


def _norm(s):
    return ''.join(ch for ch in unicodedata.normalize('NFD', (s or '').upper()) if unicodedata.category(ch) != 'Mn')


def aliq_interna(data):
    d = _aaaammdd(data)
    return 19.0 if not d or d >= INICIO_19 else 17.0


def base_dupla(data):
    d = _aaaammdd(data)
    return not d or d >= INICIO_BASE_DUPLA


def calcular(valor, ai, interna, dupla):
    """(base, difal)."""
    return dr.calcular_difal(valor, ai, interna, dupla)


def vencimento(dt_ini):
    """Dia 20 do mês seguinte ao período (ddmmaaaa)."""
    d = re.sub(r'\D', '', dt_ini or '')
    if len(d) != 8:
        return ''
    m, a = int(d[2:4]) + 1, int(d[4:])
    if m == 13:
        m, a = 1, a + 1
    return f'20{m:02d}{a:04d}'


def id_doc(d):
    ch = re.sub(r'\D', '', d.get('chave') or '')
    return ch if len(ch) == 44 else f"{(d.get('num') or '').lstrip('0')}|{d.get('serie', '')}|{d.get('part', '')}|{d.get('dt', '')}"


# ------------------------------------------------------------------ leitura
def _estrutura(linhas):
    """0000, 0150, 0200, 0460, C100 (com C170/C190/C195/C197), E110 e E116."""
    cab, part, prod, obs460 = {}, {}, {}, {}
    docs, e116 = [], []
    e110 = None
    cur = None
    for i, ln in enumerate(linhas):
        c = ln.split('|')
        if len(c) < 3:
            continue
        r = c[1]
        if r == '0000':
            cab = {'dt_ini': c[4], 'dt_fin': c[5], 'nome': c[6], 'cnpj': c[7], 'uf': c[9] if len(c) > 9 else ''}
        elif r == '0150' and len(c) > 8:
            part[c[2]] = {'nome': c[3], 'pais': c[4], 'cnpj': c[5] or c[6], 'mun': c[8]}
        elif r == '0200' and len(c) > 3:
            prod[c[2]] = c[3]
        elif r == '0460' and len(c) > 3:
            obs460[c[2]] = {'i': i, 'txt': c[3]}
        elif r == 'C100':
            cur = {'i': i, 'fim': i, 'oper': c[2], 'emit': c[3], 'part': c[4], 'mod': c[5], 'sit': c[6], 'serie': c[7],
                   'num': c[8], 'chave': c[9] if len(c) > 9 else '', 'dt': (c[11] if len(c) > 11 and c[11] else (c[10] if len(c) > 10 else '')),
                   'vl_merc': _n(c[16]) if len(c) > 16 else 0.0, 'vl_frt': _n(c[18]) if len(c) > 18 else 0.0,
                   'vl_seg': _n(c[19]) if len(c) > 19 else 0.0, 'vl_out': _n(c[20]) if len(c) > 20 else 0.0,
                   'c170': [], 'c190': [], 'c195': [], 'c197': []}
            docs.append(cur)
        elif cur is not None and r in dr.FILHOS_C100:
            cur['fim'] = i
            if r == 'C170' and len(c) > 15:
                cur['c170'].append({'i': i, 'num': c[2].lstrip('0') or c[2], 'item': c[3], 'descr': c[4], 'vl': _n(c[7]), 'desc': _n(c[8]),
                                    'cst': c[10], 'cfop': c[11], 'bc': _n(c[13]), 'aliq': _n(c[14]), 'icms': _n(c[15]),
                                    'icms_st': _n(c[18]) if len(c) > 18 else 0.0, 'ipi': _n(c[24]) if len(c) > 24 else 0.0})
            elif r == 'C190' and len(c) > 7:
                cur['c190'].append({'i': i, 'cst': c[2], 'cfop': c[3], 'aliq': _n(c[4]), 'vl_opr': _n(c[5]), 'vl_bc': _n(c[6]), 'vl_icms': _n(c[7])})
            elif r == 'C195':
                cur['c195'].append({'i': i, 'cod_obs': c[2] if len(c) > 2 else ''})
            elif r == 'C197' and len(c) > 7:
                cur['c197'].append({'i': i, 'cod': c[2], 'item': c[4], 'bc': _n(c[5]), 'aliq': _n(c[6]), 'icms': _n(c[7])})
        else:
            cur = None
            if r == 'E110' and len(c) > 15:
                e110 = {'i': i, 'c': c}
            elif r == 'E116' and len(c) > 5:
                e116.append({'i': i, 'cod_or': c[2], 'valor': _n(c[3]), 'venc': c[4], 'cod_rec': c[5]})
    return cab, part, prod, obs460, docs, e110, e116


def _aliq_inter(it170, xi, uf_or):
    """Alíquota interestadual do item: a da nota (4/7/12), senão a do XML, senão a regra (origem importada 4%, Sul/Sudeste 7%)."""
    if it170 and it170['aliq'] in (4.0, 7.0, 12.0):
        return it170['aliq'], 'alíquota da nota'
    if xi and xi.get('picms') in (4.0, 7.0, 12.0):
        return xi['picms'], 'alíquota do XML'
    orig = (xi or {}).get('orig') or ((it170 or {}).get('cst') or '')[:1]
    ai, fonte = dr._aliq_inter(0.0, (orig or '0') + '00', uf_or)
    return ai, fonte


# ------------------------------------------------------------------ análise
def analisar_texto(texto, xmls=None, regime_especial=None):
    xmls = xmls or {}
    linhas = texto.splitlines()
    cab, part, prod, obs460, docs, e110, e116 = _estrutura(linhas)
    uf_emp = (cab.get('uf') or '').strip().upper()
    res = {'empresa': {'nome': cab.get('nome', ''), 'cnpj': cab.get('cnpj', ''), 'uf': uf_emp, 'dt_ini': cab.get('dt_ini', '')},
           'aplica': uf_emp == 'AC', 'docs': [], 'cst': [], 'avisos': [], 'resumo': {}}
    if uf_emp != 'AC':
        return res
    raiz = re.sub(r'\D', '', cab.get('cnpj') or '')[:8]
    tem_codigos = any(x['cod'] in COD.values() for d in docs for x in d['c197']) or any(e['cod_rec'] in COD_REC.values() for e in e116)
    reg_esp = tem_codigos if regime_especial is None else bool(regime_especial)
    res['regime_especial'] = {'detectado': tem_codigos, 'usado': reg_esp}
    for d in docs:
        if d['oper'] != '0' or d['sit'] in CANC:
            continue
        alvo = [x for x in d['c170'] if x['cfop'][1:] in TIPOS and x['cfop'][:1] in '12']
        if not alvo:
            continue
        uf_or, fonte_uf = dr._uf_emitente(d, part)
        if not uf_or or uf_or in ('AC', 'EX'):
            continue
        p = part.get(d['part'], {})
        x = xmls.get(re.sub(r'\D', '', d['chave'] or ''))
        if x and x.get('tipo') != 'nfe':
            x = None
        if raiz and re.sub(r'\D', '', p.get('cnpj') or '')[:8] == raiz:
            res['docs'].append({'id': id_doc(d), 'num': d['num'], 'serie': d['serie'], 'data': d['dt'], 'fornecedor': p.get('nome', d['part']),
                                'uf_origem': uf_or, 'status': 'transferencia', 'itens': [], 'difal_calculado': 0.0, 'difal_lancado': 0.0,
                                'obs': ['Transferência entre estabelecimentos da mesma empresa: sem DIFAL (RICMS-AC, art. 97, § 7º-B).'], 'sugerido': False})
            continue
        xi_por_n = {(i.get('n') or '').lstrip('0'): i for i in (x or {}).get('itens') or []}
        tot_vl = sum(max(0.0, c['vl'] - c['desc']) for c in d['c170']) or 1.0
        rateio = d['vl_frt'] + d['vl_seg'] + d['vl_out']
        dt_doc = d['dt'] or cab.get('dt_ini')
        interna, dupla = aliq_interna(dt_doc), base_dupla(dt_doc)
        itens, obs = [], []
        for c in alvo:
            tipo = TIPOS[c['cfop'][1:]]
            xi = xi_por_n.get(c['num'])
            st = (xi or {}).get('vicmsst', 0.0) > 0.004 or c['icms_st'] > 0.004
            if xi:
                valor, fonte_v = xi['valor_oper'], 'XML'
            else:
                valor = c['vl'] - c['desc'] + c['ipi'] + (rateio * max(0.0, c['vl'] - c['desc']) / tot_vl if rateio else 0.0)
                fonte_v = 'SPED'
            ai, fonte_ai = _aliq_inter(c, xi, uf_or)
            if st:
                base, dif = Decimal('0'), Decimal('0')
            else:
                base, dif = calcular(valor, ai, interna, dupla)
            lanc = [y for y in d['c197'] if y['cod'] in COD.values() and y['item'] == c['item']]
            itens.append({'num': c['num'], 'cod': c['item'], 'descr': prod.get(c['item']) or c['descr'] or (xi or {}).get('xprod', ''),
                          'cfop': c['cfop'], 'cst': c['cst'], 'tipo': tipo, 'valor': float(_d(valor)), 'fonte_valor': fonte_v,
                          'aliq_inter': ai, 'fonte_aliq': fonte_ai, 'aliq_interna': interna, 'base': float(base), 'difal': float(dif),
                          'st': st, 'lancado': float(_d(sum(y['icms'] for y in lanc))), 'credito': c['icms'], 'i170': c['i']})
        if any(i['st'] for i in itens):
            obs.append('Item com ICMS-ST retido na nota: o diferencial já foi cobrado pelo fornecedor e o item fica fora do DIFAL.')
        if x and x.get('simples'):
            obs.append('Fornecedor do Simples Nacional: abate-se a alíquota interestadual cheia, mesmo sem ICMS destacado (RICMS-AC, art. 97, § 5º).')
        if not dupla:
            obs.append('Entrada anterior a 24/03/2023: base única (RICMS-AC, art. 5º, IX, "c", antes do Decreto 11.206/2023).')
        if not x and rateio:
            obs.append(f'Sem o XML: frete, seguro e outras despesas da nota (R$ {_f(rateio)}) foram rateados pelos itens (art. 97, § 3º).')
        lanc_doc = [y for y in d['c197'] if y['cod'] in COD.values()]
        calc = float(_d(sum(i['difal'] for i in itens)))
        lancado = float(_d(sum(y['icms'] for y in lanc_doc)))
        sem_item = any(not y['item'] for y in lanc_doc)
        if calc <= 0 and not lanc_doc:
            status = 'st_nota' if itens and all(i['st'] for i in itens) else 'zero'
        elif not lanc_doc:
            status = 'faltando'
        elif abs(lancado - calc) <= 0.05:
            status = 'ok'
        else:
            status = 'divergente'
            if abs(lancado - sum(float(_d(Decimal(str(i['valor'])) * Decimal(str(i['aliq_interna'] - i['aliq_inter'])) / 100))
                                 for i in itens if not i['st'])) <= 0.05:
                obs.append('O valor lançado é o da base única, valor × (19% − interestadual): desde 24/03/2023 a base é dupla.')
        if status in ('ok', 'divergente') and sem_item:
            obs.append('O C197 lançado está sem o código do item: o manual do AC pede um C197 por item.')
        if d['sit'] in EXTEMP:
            obs.append('Documento extemporâneo: confira o período do lançamento antes de incluir.')
        res['docs'].append({'id': id_doc(d), 'num': d['num'], 'serie': d['serie'], 'data': d['dt'], 'fornecedor': p.get('nome', d['part']),
                            'uf_origem': uf_or, 'fonte_uf': fonte_uf, 'tem_xml': bool(x), 'status': status, 'itens': itens,
                            'difal_calculado': calc, 'difal_lancado': lancado, 'base_dupla': dupla, 'aliq_interna': interna,
                            'obs': obs, 'sugerido': status in ('faltando', 'divergente') and reg_esp and d['sit'] not in EXTEMP})
        # CST 90 sem crédito (manual do AC, itens 8 e 9): só os itens sem crédito (o crédito sai na etapa "Uso e consumo")
        if reg_esp:
            for it in itens:
                if it['st'] or it['cst'][-2:] == '90':
                    continue
                res['cst'].append({'id': f"{id_doc(d)}#{it['num']}", 'num': d['num'], 'fornecedor': p.get('nome', d['part']),
                                   'item': it['cod'], 'descr': it['descr'], 'cst': it['cst'], 'para': (it['cst'][:1] or '0') + '90',
                                   'bloqueado': it['credito'] > 0.004,
                                   'motivo': ('item com crédito de ICMS: retire o crédito na etapa "Uso e consumo · DIFAL e crédito" e analise de novo'
                                              if it['credito'] > 0.004 else 'nota de entrada com DIFAL: CST 90, sem crédito')})
    ds = res['docs']
    res['resumo'] = {
        'notas': len(ds), 'faltando': sum(1 for x in ds if x['status'] == 'faltando'), 'divergente': sum(1 for x in ds if x['status'] == 'divergente'),
        'ok': sum(1 for x in ds if x['status'] == 'ok'),
        'calculado': float(_d(sum(x['difal_calculado'] for x in ds))), 'lancado': float(_d(sum(x['difal_lancado'] for x in ds))),
        'a_lancar': float(_d(sum(x['difal_calculado'] - x['difal_lancado'] for x in ds if x['status'] in ('faltando', 'divergente')))),
        'base_unica': float(_d(sum(Decimal(str(i['valor'])) * Decimal(str(i['aliq_interna'] - i['aliq_inter'])) / 100
                                   for x in ds for i in x['itens'] if not i['st']))),
        'cst': sum(1 for c in res['cst'] if not c['bloqueado']),
    }
    if not reg_esp and any(x['status'] in ('faltando', 'divergente') for x in ds):
        res['avisos'].append('Sem regime especial o DIFAL é notificado pela SEFAZ-AC na entrada (RICMS-AC, art. 93, VI) e o manual da EFD do AC '
                             'não prevê lançamento: compare o valor calculado com a notificação paga. Se a empresa tiver regime especial, '
                             'marque a opção e o sistema lança C197, campo 15 do E110 e E116.')
    return res


# ------------------------------------------------------------------ aplicação
def _cod_obs(obs460, tipo, usados):
    alvo = _norm(TXT_OBS[tipo])
    for k, v in obs460.items():
        if _norm(v['txt']).strip() == alvo:
            return k, None
    cod = OBS_PADRAO[tipo]
    n = 1
    while cod in obs460 or cod in usados:
        n += 1
        cod = f'{OBS_PADRAO[tipo][:4]}{n}'
    return cod, f'|0460|{cod}|{TXT_OBS[tipo]}|'


def aplicar_texto(texto, ids_docs, ids_cst=None, regime_especial=None, xmls=None):
    """ids_docs: notas (id estável) cujo DIFAL será lançado/corrigido; ids_cst: itens 'doc#n' que passam a CST 90."""
    an = analisar_texto(texto, xmls, regime_especial)
    res = {'notas': 0, 'difal': 0.0, 'cst': 0, 'avisos': []}
    if not an['aplica']:
        return texto, res
    linhas, quebra, final_vazio = dr.dividir(texto)
    cab, part, prod, obs460, docs, e110, e116 = _estrutura(linhas)
    por_id = {id_doc(d): d for d in docs}
    ids_docs, ids_cst = set(ids_docs or []), set(ids_cst or [])
    remover, insercoes, novos_0460, usados = set(), {}, [], {}
    delta = {'uso': Decimal('0'), 'ativo': Decimal('0')}
    for a in an['docs']:
        if a['id'] not in ids_docs or a['status'] not in ('faltando', 'divergente'):
            continue
        d = por_id.get(a['id'])
        if not d:
            continue
        antigos = [y for y in d['c197'] if y['cod'] in COD.values()]
        for y in antigos:
            remover.add(y['i'])
            delta['ativo' if y['cod'] == COD['ativo'] else 'uso'] -= Decimal(str(y['icms']))
        # C195 dos lançamentos antigos: reaproveitado quando só tem DIFAL embaixo (um C195 sem filhos não faz sentido)
        pai = None
        if antigos:
            c195s = [z for z in d['c195'] if z['i'] < antigos[0]['i']]
            if c195s:
                z = c195s[-1]
                prox = min([w['i'] for w in d['c195'] if w['i'] > z['i']] + [d['fim'] + 1])
                filhos = [y for y in d['c197'] if z['i'] < y['i'] < prox]
                if filhos and all(y['cod'] in COD.values() for y in filhos):
                    pai = z
        novas = []
        for tipo in ('uso', 'ativo'):
            its = [i for i in a['itens'] if i['tipo'] == tipo and i['difal'] > 0]
            if not its:
                continue
            if pai is None:
                if tipo not in usados:
                    cod, l460 = _cod_obs(obs460, tipo, set(usados.values()))
                    usados[tipo] = cod
                    if l460:
                        novos_0460.append(l460)
                novas.append(f'|C195|{usados[tipo]}||')
            for i in its:
                novas.append(f"|C197|{COD[tipo]}||{i['cod']}|{_f(i['base'])}|{_f(i['aliq_inter'])}|{_f(i['difal'])}||")
                delta[tipo] += Decimal(str(i['difal']))
        if not novas:
            continue
        # no lugar dos antigos quando o C195 deles já é o do DIFAL; senão, um C195 novo no fim da nota
        pos = antigos[0]['i'] if pai is not None else d['fim']
        insercoes.setdefault(pos, []).extend(novas)
        res['notas'] += 1
    docs_cst = set()
    # CST 90 (só item sem crédito; C190 da nota ajustado quando o grupo CST/CFOP/alíquota for só desses itens)
    for c in an['cst']:
        if c['bloqueado'] or c['id'] not in ids_cst:
            continue
        doc_id, n = c['id'].split('#', 1)
        d = por_id.get(doc_id)
        if not d:
            continue
        it = next((x for x in d['c170'] if x['num'] == n), None)
        if not it or it['icms'] > 0.004:
            continue
        mesmos = [x for x in d['c170'] if x['cst'] == it['cst'] and x['cfop'] == it['cfop'] and abs(x['aliq'] - it['aliq']) < 0.001]
        sel_mesmos = [x for x in mesmos if f"{doc_id}#{x['num']}" in ids_cst]
        g190 = [g for g in d['c190'] if g['cst'] == it['cst'] and g['cfop'] == it['cfop'] and abs(g['aliq'] - it['aliq']) < 0.001]
        if len(sel_mesmos) != len(mesmos) or len(g190) != 1:
            if not any(f"cst-misto:{doc_id}" in a for a in res['avisos']):
                res['avisos'].append(f"NF {d['num'].lstrip('0')}: o CST não foi trocado porque o resumo (C190) junta itens com e sem DIFAL "
                                     f"(cst-misto:{doc_id}).")
            continue
        novo = (it['cst'][:1] or '0') + '90'
        cc = linhas[it['i']].split('|')
        cc[10] = novo
        linhas[it['i']] = '|'.join(cc)
        g = g190[0]
        cg = linhas[g['i']].split('|')
        cg[2] = novo
        linhas[g['i']] = '|'.join(cg)
        res['cst'] += 1
        docs_cst.add(doc_id)
    for d in docs:
        if id_doc(d) in docs_cst:
            dr._junta_c190(linhas, d, remover)       # C190 não pode repetir CST + CFOP + alíquota
    # E110 campo 15 e E116 1641/1642
    total = delta['uso'] + delta['ativo']
    novas_e116 = []
    if total != 0:
        if not e110:
            return texto, {**res, 'erro': 'O SPED não tem o registro E110; não dá para lançar o DIFAL.'}
        c = linhas[e110['i']].split('|')
        c[15] = _f(max(Decimal('0'), Decimal(str(_n(c[15]))) + total))
        linhas[e110['i']] = '|'.join(c)
        mes_ref = (cab.get('dt_ini') or '')[2:]
        venc = vencimento(cab.get('dt_ini'))
        for tipo in ('uso', 'ativo'):
            dv = delta[tipo]
            if dv == 0:
                continue
            ex = [e for e in e116 if e['cod_rec'] == COD_REC[tipo] and e['i'] not in remover]
            if ex:
                ce = linhas[ex[0]['i']].split('|')
                nv = Decimal(str(_n(ce[3]))) + dv
                if nv <= 0:
                    remover.add(ex[0]['i'])
                else:
                    ce[3] = _f(nv)
                    linhas[ex[0]['i']] = '|'.join(ce)
            elif dv > 0:
                txt = 'DIFAL USO E CONSUMO' if tipo == 'uso' else 'DIFAL ATIVO IMOBILIZADO'
                novas_e116.append(f'|E116|090|{_f(dv)}|{venc}|{COD_REC[tipo]}||||{txt}|{mes_ref}|')
        res['difal'] = float(_d(total))
        res['e116'] = f"Vencimento {venc[:2]}/{venc[2:4]}/{venc[4:]} (dia 20 do mês seguinte, RICMS-AC, art. 93, IV, \"f\")." if venc else ''
    if not res['notas'] and not res['cst']:
        return texto, res
    novo = dr.monta_arquivo(linhas, remover, insercoes, novos_0460, [], novas_e116, quebra, final_vazio)
    return novo, res

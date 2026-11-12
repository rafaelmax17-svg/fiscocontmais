# -*- coding: utf-8 -*-
"""ICMS-ST na entrada × CFOP e CST do SPED (Corretor do SPED Fiscal · Análise Inteligente).

1) Produto da ST de RO lançado como tributado
   Produto que está na lista de substituição tributária de Rondônia — RICMS/RO (Dec. 22.721/2018), Anexo VI, Parte 2,
   lista vigente em st_ro_dados.py (sem itens revogados nem redações anteriores) — comprado para revenda (x.102) ou para
   insumo (x.101) com CST de ICMS tributado (x00 ou x20). Ex.: café torrado (NCM 0901.2x, Tabela XVII, CEST 17.096).
   Correção — SÓ quando o XML da nota mostra a ST retida pelo fornecedor (vICMSST, CST 10/30/60/70 ou CSOSN
   201/202/203/500): CFOP x.102 → x.403 e x.101 → x.401; CST → origem + 60 (ICMS cobrado anteriormente por ST); sem
   base, alíquota e ICMS — com a ST já paga, a venda sai sem débito e o crédito do ICMS próprio não cabe. O crédito
   retirado sai do campo 06 do E110 (e o E116 acompanha).
   Fornecedor que tributou normal, sem reter a ST (XML com CST 00/20): NÃO mexe. Nesse caso o ICMS destacado não é
   "crédito indevido" a estornar na apuração: ou a empresa paga a ST na entrada (antecipação, com o destacado abatendo
   no cálculo), ou vende com débito — tirar o crédito sem tirar o débito da venda cobra o imposto duas vezes. Esses
   itens aparecem só na descrição da etapa (quantos e quanto de ICMS). Sem XML: não mexe (pede os XMLs).
   Como o produto é reconhecido:
     • CEST do produto (0200 ou XML) que está na lista vigente; ou
     • NCM da lista, só nas tabelas em que o NCM identifica o produto sozinho: bebidas (III, IV), cigarros (V), cimento
       (VI), pneus (XVI), alimentícios (XVII), perfumaria e higiene (XIX), sorvetes (XXII) e tintas (XXIII). Nas demais —
       autopeças (II), lâmpadas (X), materiais de construção (XI), materiais elétricos (XIII), medicamentos e materiais
       hospitalares (XIV), veículos (XXIV, XXV) — só pelo CEST: ali o mesmo NCM serve para produtos fora da ST (ex.:
       abraçadeira de nylon, NCM 3926.90.90, cai na Tabela XIV pelo NCM). Plástico (capítulo 39) também só pelo CEST
       (balde, NCM 3924.90.00, cai na Tabela XIX pelo NCM). Combustíveis (VII, monofásico), energia (VIII)
       e porta a porta (XXVI) ficam de fora.
     • Café: só o torrado (0901.2x). Café cru (0901.1x) não é o café da Tabela XVII.
   Não entra: empresa industrial (0000 IND_ATIV = 0) comprando para insumo (x.101) — a ST não se aplica à mercadoria
   destinada a emprego em processo de industrialização (Convênio ICMS 142/2018, cláusula nona).

2) CFOP de ST (x.403 / x.401) com CST tributado (x00 / x20) — confere no XML da nota
   • XML sem ST no item (CST 00/20 ou CSOSN 101/102/103/300/400 e sem vICMSST) → é tributado de fato:
     x.403 → x.102 e x.401 → x.101 (o CST fica). Produto da lista de ST de RO fica fora: cai na regra 1.
   • XML com ST no item (CST 10/30/60/70, CSOSN 201/202/203/500 ou vICMSST) → o CST do SPED é que está errado:
     CST → origem + 60, sem crédito (o CFOP fica).
   • Despesa fica de fora: acumulador de despesa (COD_NAT 7xxx), produto de uso e consumo (0200 tipo 07 ou descrição
     "USO E CONSUMO").
   • Sem XML da nota não dá para saber: não é listado.
Gera arquivo NOVO; o original nunca é alterado.
"""
import re
from decimal import Decimal

import difal_ro as dr
import icms_xml as ix

CANC = {'02', '03', '04', '05'}
TRIBUTADO = ('00', '20')
TAB_NCM = {'III', 'IV', 'V', 'VI', 'XVI', 'XVII', 'XIX', 'XXII', 'XXIII'}      # nas outras, só pelo CEST
TAB_FORA = {'VII', 'VIII', 'XXVI'}
CSOSN_ST = {'201', '202', '203', '500'}
NOVO_ST = {'102': '403', '101': '401'}
NOVO_TRIB = {'403': '102', '401': '101'}


def _so_dig(s):
    return re.sub(r'\D', '', s or '')


_LISTA = None


def _lista():
    global _LISTA
    if _LISTA is None:
        import st_ro_dados as s
        vig = {c: dict(r) for c, r in s.VIGENTES.items()}
        for c, r in vig.items():          # subitem sem NCM no texto herda o NCM do item principal (xx.yyy.00)
            if not r['ncm']:
                pai = vig.get(c[:7] + '00')
                if pai and pai['ncm']:
                    r['ncm'] = list(pai['ncm'])
        vig = {c: r for c, r in vig.items() if r['tab'] not in TAB_FORA}
        _LISTA = (vig, {_so_dig(c): r for c, r in vig.items()})
    return _LISTA


def produto_st(ncm, cest):
    """-> (registro da lista, motivo) se o produto é da ST de RO; senão (None, '')."""
    vig, por_cest = _lista()
    n, ce = _so_dig(ncm), _so_dig(cest)
    if ce and ce in por_cest:
        r = por_cest[ce]
        if not n or any(n.startswith(p) for p in r['ncm']) or not r['ncm']:
            return r, f"CEST {r['cest']} (Tabela {r['tab']})"
    if not n or n.startswith(('09011',)):                 # café cru não é o café torrado da Tabela XVII
        return None, ''
    best, tam = None, 0
    for r in vig.values():
        if r['tab'] not in TAB_NCM:
            continue
        for p in r['ncm']:
            if len(p) >= 4 and not p.startswith('39') and n.startswith(p) and len(p) > tam:     # plástico (cap. 39): só pelo CEST
                best, tam = r, len(p)
    if best:
        return best, f"NCM {n} (Tabela {best['tab']}, CEST {best['cest']})"
    return None, ''


def _xml_st(it):
    if (it.get('vicmsst') or 0) > 0.009:
        return True
    return (it.get('cst') or '') in ('10', '30', '60', '70') or (it.get('csosn') or '') in CSOSN_ST


def _estrutura(linhas):
    cab, part, _, docs, e110, _ = dr._estrutura(linhas)
    p200 = {}
    ind_ativ = ''
    for l in linhas:
        c = l.split('|')
        if len(c) > 2 and c[1] == '0200':
            p200[c[2]] = {'descr': c[3], 'tipo': c[7] if len(c) > 7 else '', 'ncm': _so_dig(c[8] if len(c) > 8 else ''),
                          'cest': c[13] if len(c) > 13 else ''}
        elif len(c) > 15 and c[1] == '0000':
            ind_ativ = c[15]
    natz = {}
    for d in docs:
        for c in d['c170']:
            natz[c['i']] = linhas[c['i']].split('|')[12] if len(linhas[c['i']].split('|')) > 12 else ''
    return cab, part, docs, e110, p200, ind_ativ, natz


def _despesa(prod, cod_nat):
    import uso_consumo_cfop as uc
    return (cod_nat or '').startswith('7') or prod.get('tipo') == '07' or uc.eh_uso_consumo(prod.get('descr'))


def analisar_texto(texto, xmls=None):
    xmls = xmls or {}
    linhas, _, _ = dr.dividir(texto)
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), None)
    if fim is not None:
        linhas = linhas[:fim + 1]
    cab, part, docs, e110, p200, ind_ativ, natz = _estrutura(linhas)
    itens, fora_ind, sem_xml, st_sem_xml, sem_ret = [], 0, 0, 0, []
    for k, d in enumerate(docs):
        if d['oper'] != '0' or d['sit'] in CANC:
            continue
        x = xmls.get(_so_dig(d['chave'])) if d['chave'] else None
        par = ix._casar(d, x)[0] if x and x.get('itens') else {}
        forn = (part.get(d['part']) or {}).get('nome', d['part'])
        for c in d['c170']:
            cf, cst = c['cfop'] or '', (c['cst'] or '').zfill(3)
            if len(cf) != 4 or cf[:1] not in '12':
                continue
            prod = p200.get(c['item'], {})
            it = par.get(c['i'])
            base = {'doc': k, 'id': f"{k}:{c['num']}", 'num': d['num'], 'serie': d['serie'], 'forn': forn, 'data': d['dt'],
                    'item': c['num'], 'cod': c['item'], 'descr': prod.get('descr') or c['descr'], 'ncm': prod.get('ncm', ''),
                    'cfop_de': cf, 'cst_de': cst, 'valor': round(c['vl'], 2), 'icms': round(c['icms'], 2)}
            # 1) produto da ST lançado como tributado (revenda / insumo)
            if cf[1:] in NOVO_ST and cst[-2:] in TRIBUTADO:
                r, mot = produto_st(prod.get('ncm') or (it or {}).get('ncm'), prod.get('cest') or (it or {}).get('cest'))
                if not r:
                    continue
                if cf[1:] == '101' and ind_ativ == '0':
                    fora_ind += 1
                    continue
                if it is None:                      # sem o XML não dá para saber se a ST foi retida
                    st_sem_xml += 1
                    continue
                if not _xml_st(it):                 # fornecedor tributou normal, sem reter a ST: o crédito do destacado não sai
                    sem_ret.append({**base, 'motivo': f"produto da ST de RO ({mot}) comprado sem ST retida (CST {it.get('cst') or it.get('csosn')})"})
                    continue
                itens.append({**base, 'regra': 'st', 'cfop_para': cf[:1] + NOVO_ST[cf[1:]], 'cst_para': cst[:1] + '60',
                              'motivo': f"produto da ST de RO: {mot}; o XML traz a ST retida (CST {it.get('cst') or it.get('csosn')}"
                                        + (f", ICMS-ST R$ {it['vicmsst']:.2f}".replace('.', ',') if it.get('vicmsst') else '') + ')'})
            # 2) CFOP de ST com CST tributado — o XML decide
            elif cf[1:] in NOVO_TRIB and cst[-2:] in TRIBUTADO:
                if _despesa(prod, natz.get(c['i'])):
                    continue
                if it is None:
                    sem_xml += 1
                    continue
                r, mot = produto_st(prod.get('ncm') or it.get('ncm'), prod.get('cest') or it.get('cest'))
                if r and not _xml_st(it):           # produto da ST comprado sem retenção: fica como está (ver regra 1)
                    sem_ret.append({**base, 'motivo': f"produto da ST de RO ({mot}) comprado sem ST retida (CST {it.get('cst') or it.get('csosn')})"})
                    continue
                if _xml_st(it):
                    why = f"o XML traz ST no item (CST {it.get('cst') or it.get('csosn')}" + (
                        f", ICMS-ST R$ {it['vicmsst']:.2f}".replace('.', ',') if it.get('vicmsst') else '') + ')'
                    itens.append({**base, 'regra': 'cst', 'cfop_para': cf, 'cst_para': cst[:1] + '60', 'motivo': why})
                else:
                    itens.append({**base, 'regra': 'trib', 'cfop_para': cf[:1] + NOVO_TRIB[cf[1:]], 'cst_para': cst,
                                  'icms_xml': round(it.get('vicms') or 0, 2),
                                  'motivo': f"o XML traz o item tributado, sem ST (CST {it.get('cst') or it.get('csosn')}"
                                            + (f", ICMS destacado pelo fornecedor R$ {it['vicms']:.2f}".replace('.', ',') if it.get('vicms') else '') + ')'})
    notas = {i['doc'] for i in itens}
    return {'itens': itens,
            'resumo': {'itens': len(itens), 'notas': len(notas), 'valor': round(sum(i['valor'] for i in itens), 2),
                       'st': sum(1 for i in itens if i['regra'] == 'st'), 'cst': sum(1 for i in itens if i['regra'] == 'cst'),
                       'trib': sum(1 for i in itens if i['regra'] == 'trib'),
                       'credito': round(sum(i['icms'] for i in itens if i['regra'] in ('st', 'cst')), 2),
                       'fora_industria': fora_ind, 'sem_xml': sem_xml, 'st_sem_xml': st_sem_xml,
                       'sem_retencao': len(sem_ret), 'sem_retencao_icms': round(sum(x['icms'] for x in sem_ret), 2)},
            'sem_retencao': sem_ret}


def aplicar_texto(texto, ids, xmls=None, e116=None):
    """ids: 'doc:NUM_ITEM'. -> (texto_novo, resumo). Com resumo['erro'] quando o E110/E116 não pôde ser refeito
    (o texto devolvido já traz os itens e o C190 corrigidos, sem a apuração)."""
    linhas, quebra, final_vazio = dr.dividir(texto)
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), None)
    assinado = fim is not None and fim < len(linhas) - 1
    if assinado:
        linhas = linhas[:fim + 1]
        final_vazio = True
    an = analisar_texto(quebra.join(linhas) + quebra, xmls)
    sel = set(ids)
    por_doc = {}
    for it in an['itens']:
        if it['id'] in sel:
            por_doc.setdefault(it['doc'], {})[it['item']] = it
    cab, part, docs, e110, _, _, _ = _estrutura(linhas)
    res = {'itens': 0, 'notas': 0, 'credito_retirado': 0.0, 'st': 0, 'cst': 0, 'trib': 0, 'avisos': [], 'e110_antes': None, 'e110_depois': None, 'e116': ''}
    remover, insercoes = set(), {}
    d06 = Decimal('0')
    for k, escolha in por_doc.items():
        d = docs[k]
        mud = []
        for c in d['c170']:
            it = escolha.get(c['num'])
            if not it:
                continue
            zera = it['regra'] in ('st', 'cst')
            mud.append({'i': c['i'], 'old': c, 'txt': linhas[c['i']], 'novo': {'cst': it['cst_para'], 'cfop': it['cfop_para'],
                                                        'bc': 0.0 if zera else c['bc'], 'aliq': 0.0 if zera else c['aliq'],
                                                        'icms': 0.0 if zera else c['icms']}})
            res[it['regra']] += 1
        if not mud:
            continue
        antes_icms = Decimal(str(sum(g['vl_icms'] for g in d['c190'])))
        for m in mud:
            c = linhas[m['i']].split('|')
            c[10], c[11] = m['novo']['cst'], m['novo']['cfop']
            c[13], c[14], c[15] = dr._f(Decimal(str(m['novo']['bc']))), dr._f(Decimal(str(m['novo']['aliq']))), dr._f(Decimal(str(m['novo']['icms'])))
            linhas[m['i']] = '|'.join(c)
        r = ix._refaz_c190(linhas, d, mud, remover, insercoes)
        if r is None:
            res['avisos'].append(f"NF {d['num']}: o C190 não corresponde aos itens (C170); a nota ficou como estava.")
            for m in mud:                                    # desfaz os C170 desta nota
                linhas[m['i']] = m['txt']
            continue
        bc_t, icms_t = r
        c = linhas[d['i']].split('|')
        if len(c) > 22:
            c[21], c[22] = dr._f(bc_t), dr._f(icms_t)
            linhas[d['i']] = '|'.join(c)
        res['itens'] += len(mud)
        res['notas'] += 1
        d06 -= max(Decimal('0'), antes_icms - icms_t)
    res['credito_retirado'] = float(-d06)
    deltas = {6: float(d06)} if abs(d06) >= Decimal('0.005') else {}
    novas_e116, erro = dr.aplica_apuracao(linhas, e110, deltas, {'e116': e116 or {}}, cab, remover, res)
    if erro:
        res['erro'] = erro
        novas_e116 = []
    if assinado:
        res['avisos'].append('O arquivo estava assinado no PVA: a assinatura foi retirada (ela deixa de valer com a alteração). Valide e assine de novo no PVA.')
    novo = dr.monta_arquivo(linhas, remover, insercoes, [], [], novas_e116, quebra, final_vazio)
    return novo, res


# -*- coding: utf-8 -*-
"""Unidade do item × XML (Corretor do SPED Fiscal, só Admin).

Corrige a inconsistência do portal da Secretaria da Fazenda (aba Estoque) "[100] - [C170] erro de valor do produto ou
erro de incompatibilidade com sequência dos itens da NF-e": o portal compara cada C170 com o item da NF-e (sequência,
código, unidade, quantidade e valor). O Domínio exporta a unidade como CÓDIGO interno ("1", "5", "11"…) e a nota traz
o texto da unidade ("UN", "CX", "PT"…), então todo item aparece como divergente mesmo com quantidade e valor certos.

Como corrige (arquivo NOVO; o original nunca é alterado):
  • Lê o XML de cada nota que tem C170 (casando pela chave do C100 e pelo número do item) e descobre a que unidade
    cada código corresponde ("1" → "UN").
  • Código que corresponde sempre à mesma unidade da nota: o código é TROCADO pela unidade em todo o arquivo, nos
    registros que usam a unidade (0190, 0200 UNID_INV, 0220 UNID_CONV, C170, C321, C425, C470, C495, H010). Como é só o
    nome do código, o fator de conversão e as quantidades continuam valendo; se a unidade já existir no 0190 com outro
    código, os dois viram um só.
  • Código que aparece com unidades diferentes em notas diferentes: o código vira a unidade que as notas mais usam e
    só o item que foge dela recebe a unidade da própria nota; essa unidade entra no 0190 e, no produto em que ela é
    diferente da unidade de estoque (0200), entra o 0220 com o mesmo fator que o 0220 do código antigo tinha (ou 1,
    quando não havia — é o mesmo que o arquivo já dizia ao usar o código no C170).
  • Quantidade, valor ou sequência diferentes da nota NÃO são alterados: ficam como pendência, porque mexer nisso muda
    o C190 e a apuração.
Base: Guia Prático da EFD ICMS/IPI — registros 0190 (UNID), 0200 (UNID_INV), 0220 (UNID_CONV, FAT_CONV) e C170
(NUM_ITEM, COD_ITEM, QTD, UNID, VL_ITEM). Recalcula os fechamentos de bloco e o Bloco 9 quando entra linha nova.
"""
import os
import re
import json
from collections import Counter, defaultdict

import difal_ro as dr

CANC = {'02', '03', '04', '05'}
TOL_Q = 0.0001
TOL_V = 0.005
# campo da unidade (índice no split por "|") em cada registro que referencia o 0190
CAMPO_UNID = {'0190': 2, '0200': 6, '0220': 2, 'C170': 6, 'C321': 4, 'C425': 4, 'C470': 5, 'C495': 6, 'H010': 3}
DESCR = {'UN': 'UNIDADE', 'UND': 'UNIDADE', 'UNID': 'UNIDADE', 'CX': 'CAIXA', 'CXA': 'CAIXA', 'PT': 'PACOTE', 'PCT': 'PACOTE',
         'PC': 'PECA', 'CJ': 'CONJUNTO', 'CR': 'CARTELA', 'CT': 'CARTELA', 'FD': 'FARDO', 'FDO': 'FARDO', 'DZ': 'DUZIA',
         'KG': 'QUILOGRAMA', 'G': 'GRAMA', 'LT': 'LITRO', 'L': 'LITRO', 'ML': 'MILILITRO', 'M': 'METRO', 'M2': 'METRO QUADRADO',
         'M3': 'METRO CUBICO', 'PR': 'PAR', 'RL': 'ROLO', 'SC': 'SACO', 'GL': 'GALAO', 'TB': 'TUBO', 'FR': 'FRASCO',
         'BD': 'BALDE', 'LA': 'LATA', 'PT1': 'POTE', 'KIT': 'KIT', 'TON': 'TONELADA', 'DP': 'DISPLAY', 'BL': 'BLOCO'}


def _un(u):
    """Unidade como o portal compara: texto da nota, sem espaços nas pontas, até 6 caracteres (tamanho do campo)."""
    return (u or '').strip()[:6]


def _casa(c170s, itens):
    """{i_c170: item_xml}: pelo número do item; se não houver, pelo código do produto (uma única ocorrência)."""
    por_n = {}
    for it in itens:
        n = str(it.get('n') or '').strip()
        por_n[str(int(n)) if n.isdigit() else n] = it
    por_cod = defaultdict(list)
    for it in itens:
        por_cod[it.get('cprod') or ''].append(it)
    out = {}
    for c in c170s:
        it = por_n.get(c['num'])
        if it is None:
            cand = por_cod.get(c['item']) or []
            it = cand[0] if len(cand) == 1 else None
        if it is not None:
            out[c['i']] = it
    return out


def _docs(linhas):
    cab, part, _, docs, _, _ = dr._estrutura(linhas)
    return cab, part, docs


def analisar_texto(texto, xmls):
    linhas, _, _ = dr.dividir(texto)
    cab, part, docs = _docs(linhas)
    u0190 = {}
    for l in linhas:
        if l.startswith('|0190|'):
            c = l.split('|')
            if len(c) > 3:
                u0190[c[2]] = c[3]
    mapa = defaultdict(Counter)                      # código no SPED -> Counter(unidade da nota)
    itens_unid, pend, notas, sem_xml, sem_item, total_c170, ok = [], [], [], 0, 0, 0, 0
    cod_dif = 0
    for d in docs:
        if not d['c170'] or d['mod'] != '55' or d['sit'] in CANC:
            continue
        total_c170 += len(d['c170'])
        chave = re.sub(r'\D', '', d['chave'] or '')
        x = xmls.get(chave)
        if not x or x.get('tipo') not in (None, 'nfe') or 'erro' in x:
            sem_xml += 1
            continue
        par = _casa(d['c170'], x.get('itens') or [])
        n_unid = 0
        for c in d['c170']:
            it = par.get(c['i'])
            if it is None:
                sem_item += 1
                pend.append({'nota': d['num'], 'chave': chave, 'item': c['num'], 'cod': c['item'], 'motivo': 'item não encontrado na nota'})
                continue
            cc = linhas[c['i']].split('|')
            un_sped, un_xml = cc[6], _un(it.get('ucom'))
            qtd, vl = dr._n(cc[5]), dr._n(cc[7])
            if c['item'] != (it.get('cprod') or ''):
                cod_dif += 1
            if abs(qtd - (it.get('qcom') or 0)) > TOL_Q:
                pend.append({'nota': d['num'], 'chave': chave, 'item': c['num'], 'cod': c['item'], 'motivo': f'quantidade {cc[5]} no SPED × {it.get("qcom")} na nota'})
            if abs(vl - (it.get('vprod') or 0)) > TOL_V:
                pend.append({'nota': d['num'], 'chave': chave, 'item': c['num'], 'cod': c['item'], 'motivo': f'valor {cc[7]} no SPED × {dr._f(it.get("vprod") or 0)} na nota'})
            if un_xml and un_sped != un_xml:
                mapa[un_sped][un_xml] += 1
                n_unid += 1
                if len(itens_unid) < 300:
                    itens_unid.append({'nota': d['num'].lstrip('0') or d['num'], 'item': c['num'], 'cod': c['item'], 'descr': it.get('xprod') or c['descr'],
                                       'de': un_sped, 'para': un_xml, 'qtd': cc[5], 'valor': cc[7]})
            elif un_xml:
                ok += 1
        p = part.get(d['part'], {})
        notas.append({'num': d['num'].lstrip('0') or d['num'], 'chave': chave, 'data': d['dt'], 'part': p.get('nome', d['part']),
                      'oper': 'Entrada' if d['oper'] == '0' else 'Saída', 'itens': len(d['c170']), 'unid': n_unid})
    unidades = []
    for de, cnt in sorted(mapa.items(), key=lambda kv: -sum(kv[1].values())):
        para, n = cnt.most_common(1)[0]
        unidades.append({'de': de, 'descr_de': u0190.get(de, ''), 'para': para, 'descr_para': u0190.get(para) or DESCR.get(para.upper(), para),
                         'itens': sum(cnt.values()), 'conflito': len(cnt) > 1, 'destinos': dict(cnt)})
    n_unid = sum(u['itens'] for u in unidades)
    return {'empresa': {'nome': cab.get('nome', ''), 'cnpj': cab.get('cnpj', ''), 'uf': cab.get('uf', ''), 'dt_ini': cab.get('dt_ini', ''), 'dt_fin': cab.get('dt_fin', '')},
            'resumo': {'c170': total_c170, 'notas_conferidas': len(notas), 'notas_sem_xml': sem_xml, 'itens_unid': n_unid,
                       'itens_ja_ok': ok, 'pendencias': len(pend), 'codigos': len(unidades), 'conflitos': sum(1 for u in unidades if u['conflito']),
                       'codigo_diferente': cod_dif},
            'unidades': unidades, 'notas': sorted(notas, key=lambda z: -z['unid']), 'itens': itens_unid, 'pendencias': pend[:500]}


def aplicar_texto(texto, xmls):
    """-> (texto_novo, resumo). Troca as unidades conforme analisar_texto; pendências não são mexidas."""
    import fiscal_core as fc
    linhas, quebra, final_vazio = dr.dividir(texto)
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), None)
    assinado = fim is not None and fim < len(linhas) - 1
    if assinado:
        linhas = linhas[:fim + 1]
        final_vazio = True
        texto = quebra.join(linhas) + quebra
    an = analisar_texto(texto, xmls)
    res = {'itens': 0, 'renomeados': [], 'por_nota': 0, 'linhas_0190': 0, 'linhas_0220': 0, 'avisos': [], 'pendencias': an['resumo']['pendencias']}
    if not an['unidades']:
        return quebra.join(linhas) + (quebra if final_vazio else ''), res

    # 1) cada código vira a unidade que a nota mais usa para ele (troca global do nome do código)
    ren = {u['de']: u['para'] for u in an['unidades']}
    existentes = {l.split('|')[2] for l in linhas if l.startswith('|0190|') and len(l.split('|')) > 3}
    for de, para in ren.items():
        res['renomeados'].append({'de': de, 'para': para, 'junta': para in existentes and para not in ren})

    # 2) código que aparece com mais de uma unidade: o item que foge da principal recebe a unidade da própria nota
    conflito = {u['de'] for u in an['unidades'] if u['conflito']}
    por_linha = {}
    if conflito:
        _, _, docs = _docs(linhas)
        for d in docs:
            chave = re.sub(r'\D', '', d['chave'] or '')
            x = xmls.get(chave)
            if not d['c170'] or not x or d['sit'] in CANC:
                continue
            par = _casa(d['c170'], x.get('itens') or [])
            for c in d['c170']:
                it = par.get(c['i'])
                if it is None:
                    continue
                cc = linhas[c['i']].split('|')
                ux = _un(it.get('ucom'))
                if cc[6] in conflito and ux and ux != ren[cc[6]]:
                    por_linha[c['i']] = ux

    # troca nos registros que usam a unidade
    for i, l in enumerate(linhas):
        if not l.startswith('|'):
            continue
        reg = l[1:5]
        pos = CAMPO_UNID.get(reg)
        if pos is None:
            continue
        c = l.split('|')
        if len(c) <= pos:
            continue
        if i in por_linha:
            c[pos] = por_linha[i]
            res['itens'] += 1
            res['por_nota'] += 1
        elif c[pos] in ren:
            if reg == 'C170':
                res['itens'] += 1
            c[pos] = ren[c[pos]]
        else:
            continue
        linhas[i] = '|'.join(c)

    # 0190: um registro por código (o que virou repetido sai) + as unidades novas vindas das notas
    vistos, novo = set(), []
    for l in linhas:
        if l.startswith('|0190|'):
            cod = l.split('|')[2]
            if cod in vistos:
                res['linhas_0190'] -= 1
                continue
            vistos.add(cod)
        novo.append(l)
    linhas = novo
    faltam = sorted({u for u in por_linha.values() if u not in vistos})
    if faltam:
        ult = max(i for i, l in enumerate(linhas) if l.startswith('|0190|'))
        for k, u in enumerate(faltam):
            linhas.insert(ult + 1 + k, f'|0190|{u}|{DESCR.get(u.upper(), u)}|')
            res['linhas_0190'] += 1

    # 0220: tira repetidos (mesmo produto e mesma unidade) e inclui o fator onde o item passou a ter unidade de outra nota
    un_por_item = defaultdict(set)
    if por_linha:
        # produto -> unidades usadas no C170 (depois da troca)
        for l in linhas:
            if l.startswith('|C170|'):
                c = l.split('|')
                if len(c) > 6:
                    un_por_item[c[3]].add(c[6])
    novo, i, prod = [], 0, None
    while i < len(linhas):
        l = linhas[i]
        if l.startswith('|0200|'):
            c = l.split('|')
            prod, unid_inv = c[2], c[6] if len(c) > 6 else ''
            bloco = [l]
            j = i + 1
            convs, fat_antigo = {}, None
            while j < len(linhas) and linhas[j].startswith('|0220|'):
                cc = linhas[j].split('|')
                if cc[2] in convs:
                    res['linhas_0220'] -= 1
                else:
                    convs[cc[2]] = cc
                    bloco.append(linhas[j])
                    fat_antigo = fat_antigo or (cc[3] if len(cc) > 3 else None)
                j += 1
            if por_linha:
                for u in sorted(un_por_item.get(prod, ())):
                    if u and u != unid_inv and u not in convs:
                        n_campos = len(next(iter(convs.values()))) if convs else 5
                        nova = ['', '0220', u, fat_antigo or '1'] + [''] * max(0, n_campos - 5) + ['']
                        bloco.append('|'.join(nova))
                        res['linhas_0220'] += 1
            novo.extend(bloco)
            i = j
            continue
        novo.append(l)
        i += 1
    linhas = novo
    if res['linhas_0190'] or res['linhas_0220']:
        linhas = fc._recalcula_fechamentos_bloco(linhas)
        linhas = fc._recalcula_bloco9_global(linhas)
    if assinado:
        res['avisos'].append('O arquivo estava assinado no PVA: a assinatura foi retirada (ela deixa de valer com a alteração). Valide e assine de novo no PVA.')
    # confere: depois da troca, quantos C170 com XML ainda têm unidade diferente da nota
    depois = analisar_texto(quebra.join(linhas) + quebra, xmls)
    res['restantes'] = depois['resumo']['itens_unid']
    res['iguais'] = depois['resumo']['itens_ja_ok']
    return quebra.join(linhas) + (quebra if final_vazio else ''), res


def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    sped, js, xs = opt('--sped'), opt('--json'), opt('--xmls')
    if not sped or not js or not xs:
        print('uso: unidade-xml --sped ARQ.txt --xmls PASTA|ZIP --json saida.json [--aplicar --saida novo.txt]')
        return 1
    try:
        from xml_entradas import ler_xmls
        texto, enc = dr._ler(sped)
        xmls, lidos, _ = ler_xmls([p for p in xs.split(os.pathsep) if p])
        if '--aplicar' in argv:
            novo, res = aplicar_texto(texto, xmls)
            tmp = opt('--saida') + '.parcial'
            with open(tmp, 'w', encoding=enc, newline='') as fh:
                fh.write(novo)
            os.replace(tmp, opt('--saida'))
        else:
            res = analisar_texto(texto, xmls)
            res['xml_lidos'] = lidos
    except Exception as e:  # pragma: no cover
        res = {'erro': f'Falha ao processar: {e}'}
    tmp = js + '.parcial'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False)
    os.replace(tmp, js)
    return 0

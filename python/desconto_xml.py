# -*- coding: utf-8 -*-
"""Desconto × XML (Corretor do SPED Fiscal, só Admin) — desconto da nota de entrada no C100 e em cada item (C170).

Confere cada NF-e de entrada de terceiros (C100 modelo 55, não cancelada) que tem XML:
  • desconto do C100 (campo 14 VL_DESC) × vDesc do total do XML;
  • desconto de cada item (C170 campo 08 VL_DESC) × vDesc do item no XML;
  • valor do documento (C100 campo 12 VL_DOC) × vNF, quando a diferença é justamente o desconto que faltou.

De onde vem o desconto de cada item:
  1) do próprio item do XML (vDesc do det), quando o XML traz desconto por item;
  2) se o XML só tem o desconto no total da nota (ou os itens não casam), ele é dividido em PROPORÇÃO ao valor de cada
     item (VL_ITEM do C170); o centavo do arredondamento vai para o item de maior valor.

Ao aplicar: C170 campo 08, C100 campos 14 (e 12 quando VL_DOC − vNF é a diferença do desconto) e o VL_OPR do C190 é
refeito para somar o valor do documento (valor_xml._refaz_vl_opr). Base de cálculo e ICMS NÃO mudam (isso é do
"Valor e base × XML"). Gera arquivo NOVO; o original nunca é alterado.
Base: Guia Prático da EFD ICMS/IPI, registros C100 (VL_DOC, VL_DESC), C170 (VL_DESC) e C190 (VL_OPR).
"""
import os
import re
import json
from decimal import Decimal, ROUND_HALF_UP

import difal_ro as dr

TOL = Decimal('0.009')
CANC = {'02', '03', '04', '05'}


def _D(v):
    return Decimal(str(v or 0))


def _q(v):
    return _D(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _f(v):
    return f'{_q(v):.2f}'.replace('.', ',')


def _casar(c170s, itens):
    """{i_c170: item_xml} pelo número do item (VL_ITEM compatível com vProd) e, no que sobrar, pelo valor exato."""
    def bate(v, it, tol):
        alvos = (it['vprod'], it['vprod'] + it['vipi'], it['vprod'] + it['vicmsst'], it['vprod'] + it['vipi'] + it['vicmsst'],
                 it['vprod'] - it['vdesc'], it['valor_oper'])
        return any(abs(v - a) <= tol for a in alvos)
    por_n = {}
    for it in itens:
        n = it.get('n') or ''
        por_n[str(int(n)) if n.isdigit() else n] = it
    usados, par, sobra = set(), {}, []
    for c in c170s:
        it = por_n.get(c['num'])
        if it is not None and id(it) not in usados and bate(c['vl_item'], it, max(1.0, abs(c['vl_item']) * 0.01)):
            par[c['i']] = it
            usados.add(id(it))
        else:
            sobra.append(c)
    for c in sobra:
        cand = [it for it in itens if id(it) not in usados and bate(c['vl_item'], it, 0.02)]
        if len(cand) == 1:
            par[c['i']] = cand[0]
            usados.add(id(cand[0]))
    return par


def _proporcao(c170s, total):
    """Divide o desconto total em proporção ao VL_ITEM; o arredondamento vai para o item de maior valor."""
    soma = sum((_D(c['vl_item']) for c in c170s), Decimal('0'))
    if soma <= 0:
        return {}
    out = {c['i']: _q(_D(total) * _D(c['vl_item']) / soma) for c in c170s}
    resto = _q(_D(total)) - sum(out.values(), Decimal('0'))
    if resto:
        maior = max(c170s, key=lambda c: c['vl_item'])
        out[maior['i']] += resto
    return out


def _docs(linhas):
    """Notas de entrada com os campos necessários (VL_ITEM e VL_DESC do C170 lidos da linha)."""
    cab, part, _, docs, _, _ = dr._estrutura(linhas)
    for d in docs:
        for c in d['c170']:
            cc = linhas[c['i']].split('|')
            c['vl_item'] = dr._n(cc[7])
            c['vl_desc'] = dr._n(cc[8])
    return cab, part, docs


def analisar_texto(texto, xmls):
    linhas, _, _ = dr.dividir(texto)
    cab, part, docs = _docs(linhas)
    out, conferidas, sem_xml = [], 0, 0
    for d in docs:
        if d['oper'] != '0' or d['emit'] != '1' or d['mod'] != '55' or d['sit'] in CANC:
            continue
        chave = re.sub(r'\D', '', d['chave'] or '')
        x = xmls.get(chave)
        if not x or x.get('tipo') not in (None, 'nfe') or 'erro' in x:
            sem_xml += 1
            continue
        conferidas += 1
        c = linhas[d['i']].split('|')
        vl_doc, vl_desc = dr._n(c[12]), dr._n(c[14])
        xdesc, vnf = x.get('vdesc') or 0.0, x.get('vnf') or 0.0
        itens_xml = x.get('itens') or []
        tem_desc_item = any((it.get('vdesc') or 0) > 0 for it in itens_xml)
        novos, origem = {}, {}
        if d['c170']:
            par = _casar(d['c170'], itens_xml) if tem_desc_item else {}
            if tem_desc_item and len(par) == len(d['c170']):
                for it170 in d['c170']:
                    novos[it170['i']] = _q(par[it170['i']]['vdesc'])
                    origem[it170['i']] = 'item do XML'
            elif xdesc > 0 or any(it170['vl_desc'] > 0 for it170 in d['c170']):
                prop = _proporcao(d['c170'], xdesc)
                for it170 in d['c170']:
                    novos[it170['i']] = prop.get(it170['i'], Decimal('0'))
                    origem[it170['i']] = 'proporção' if not tem_desc_item else 'proporção (itens não casaram)'
        dif_c100 = abs(_D(vl_desc) - _D(xdesc)) > TOL
        dif_itens = [i for i in d['c170'] if i['i'] in novos and abs(_D(i['vl_desc']) - novos[i['i']]) > TOL]
        if not dif_c100 and not dif_itens:
            continue
        # VL_DOC: só acompanha quando a diferença com o vNF é exatamente a diferença do desconto
        dif_doc = _q(_D(vl_doc) - _D(vnf))
        corrige_doc = abs(dif_doc) > TOL and abs(dif_doc - _q(_D(xdesc) - _D(vl_desc))) <= Decimal('0.02')
        p = part.get(d['part'], {})
        soma = float(sum(novos.values(), Decimal('0')))
        out.append({
            'id': d['i'], 'chave': chave, 'num': d['num'].lstrip('0') or d['num'], 'data': d['dt'], 'fornecedor': p.get('nome', d['part']),
            'uf': x.get('emit_uf') or '', 'vl_doc': vl_doc, 'vnf': vnf, 'desc_sped': vl_desc, 'desc_xml': xdesc, 'corrige_doc': corrige_doc,
            'origem': 'item do XML' if tem_desc_item and all(o == 'item do XML' for o in origem.values()) and origem else
                      ('proporção' if origem else 'nota sem itens'),
            'desc_novo_total': soma if d['c170'] else xdesc,
            'itens': [{'i': it['i'], 'num': it['num'], 'cod': it['item'], 'descr': it['descr'], 'vl_item': it['vl_item'],
                       'desc_sped': it['vl_desc'], 'desc_xml': float(par[it['i']]['vdesc']) if tem_desc_item and it['i'] in (par or {}) else None,
                       'desc_novo': float(novos.get(it['i'], Decimal('0'))), 'origem': origem.get(it['i'], ''),
                       'pct': float(_D(it['vl_item']) / sum((_D(z['vl_item']) for z in d['c170']), Decimal('0')) * 100)
                       if any(z['vl_item'] for z in d['c170']) else 0.0} for it in d['c170']],
            'sugerido': True,
        })
    tot = float(sum((_q(_D(z['desc_xml']) - _D(z['desc_sped'])) for z in out), Decimal('0')))
    return {'docs': out, 'resumo': {'conferidas': conferidas, 'sem_xml': sem_xml, 'com_diferenca': len(out),
                                    'pelo_item': sum(1 for z in out if z['origem'] == 'item do XML'),
                                    'proporcao': sum(1 for z in out if z['origem'] != 'item do XML'),
                                    'itens': sum(len(z['itens']) for z in out), 'desconto_a_lancar': round(tot, 2)}}


def aplicar_texto(texto, xmls, selecao):
    """selecao = {'chaves': [chave, ...]} (ou {'docs': [id]}) -> (texto_novo, resumo)."""
    import valor_xml as vx
    linhas, quebra, final_vazio = dr.dividir(texto)
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), None)
    assinado = fim is not None and fim < len(linhas) - 1
    if assinado:
        linhas = linhas[:fim + 1]
        final_vazio = True
        texto = quebra.join(linhas) + quebra
    an = analisar_texto(texto, xmls)
    quer_ch = set((selecao or {}).get('chaves') or [])
    quer_id = set((selecao or {}).get('docs') or [])
    _, _, docs = _docs(linhas)
    por_i = {d['i']: d for d in docs}
    res = {'notas': 0, 'itens': 0, 'desconto': 0.0, 'vl_doc_corrigido': 0, 'detalhe': [], 'avisos': []}
    for a in an['docs']:
        if not ((quer_ch and a['chave'] in quer_ch) or (quer_id and a['id'] in quer_id)):
            continue
        d = por_i.get(a['id'])
        if not d:
            continue
        for it in a['itens']:
            if it['origem'] and abs(_D(it['desc_sped']) - _D(it['desc_novo'])) > TOL:
                c = linhas[it['i']].split('|')
                c[8] = _f(it['desc_novo'])
                linhas[it['i']] = '|'.join(c)
                res['itens'] += 1
        c = linhas[d['i']].split('|')
        c[14] = _f(a['desc_xml'])
        alvo = a['vl_doc']
        if a['corrige_doc']:
            c[12] = _f(a['vnf'])
            alvo = a['vnf']
            res['vl_doc_corrigido'] += 1
        linhas[d['i']] = '|'.join(c)
        _, _, docs2 = _docs(linhas)          # releitura: o C170 já com o desconto novo
        d2 = next(z for z in docs2 if z['i'] == d['i'])
        vx._refaz_vl_opr(linhas, d2, alvo, set())
        res['notas'] += 1
        res['desconto'] += a['desc_xml'] - a['desc_sped']
        res['detalhe'].append({'num': a['num'], 'fornecedor': a['fornecedor'], 'origem': a['origem'],
                               'desconto': round(a['desc_xml'], 2)})
    res['desconto'] = round(res['desconto'], 2)
    if assinado:
        res['avisos'].append('O arquivo estava assinado no PVA: a assinatura foi retirada (ela deixa de valer com a alteração). '
                             'Valide e assine de novo no PVA.')
    # nenhuma linha entra ou sai: o bloco 9 e os fechamentos ficam como estão
    return quebra.join(linhas) + (quebra if final_vazio else ''), res


def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    sped, js, xs = opt('--sped'), opt('--json'), opt('--xmls')
    if not sped or not js or not xs:
        print('uso: desconto-xml --sped ARQ.txt --xmls PASTA|ZIP --json saida.json [--aplicar sel.json --saida novo.txt]')
        return 1
    try:
        from xml_entradas import ler_xmls
        texto, enc = dr._ler(sped)
        xmls, lidos, _ = ler_xmls([xs])
        if opt('--aplicar'):
            with open(opt('--aplicar'), 'r', encoding='utf-8') as fh:
                sel = json.load(fh)
            novo, res = aplicar_texto(texto, xmls, sel)
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

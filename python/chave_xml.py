# -*- coding: utf-8 -*-
"""Chave de acesso × XML (Corretor do SPED Fiscal · Análise Inteligente · EM TESTE).

Confere a chave (C100 CHV_NFE) de cada NF-e (55) e NFC-e (65) do SPED — entradas e saídas — com os XMLs anexados.

Como acha o XML da nota: a chave é única, mas quando ela está errada no SPED o sistema procura o XML pela identidade da
nota, que também é única por lei: CNPJ/CPF do emitente + modelo + série + número (Ajuste SINIEF 07/2005, cláusula
primeira — numeração por série e por estabelecimento emitente).
  • emitente da nota de terceiros (C100 IND_EMIT 1) = CNPJ/CPF do participante (0150);
  • emitente da nota própria (IND_EMIT 0), inclusive NFC-e = CNPJ da empresa (0000).

Resultado por nota:
  • ok ................... a chave do SPED é a do XML (número e série conferem);
  • corrigir ............. a chave do SPED está errada, vazia ou é de outra nota: troca pela do XML (C100 campo 09);
  • duplicada ............ a chave certa já está em outro C100 do arquivo: nota lançada duas vezes — não troca;
  • sem XML .............. não há XML da nota: confere só a chave em si (dígito verificador e se o CNPJ, modelo,
                            série e número dentro dela batem com o C100) — se não bater, aparece para corrigir à mão;
  • XML sem nota ......... XML anexado (da empresa como emitente ou destinatária) que não está no SPED.
Só troca a chave; valores não mudam. Se o valor do XML for diferente do VL_DOC, avisa na linha.
Gera arquivo NOVO; o original nunca é alterado.
"""
import re

import difal_ro as dr

MODS = ('55', '65')
CANC = {'02', '03', '04', '05'}


def _dig(s):
    return re.sub(r'\D', '', s or '')


def dv_ok(ch):
    """Dígito verificador da chave (módulo 11, pesos 2 a 9)."""
    if len(ch) != 44 or not ch.isdigit():
        return False
    s, w = 0, 2
    for d in reversed(ch[:43]):
        s += int(d) * w
        w = w + 1 if w < 9 else 2
    r = s % 11
    return int(ch[43]) == (0 if r < 2 else 11 - r)


def _int(s):
    s = _dig(s)
    return int(s) if s else -1


def _brl(v):
    return f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _nome_mod(m):
    return 'NFC-e' if m == '65' else 'NF-e'


def _vl(d):
    try:
        return float((d['vl'] or '0').replace('.', '').replace(',', '.'))
    except ValueError:
        return 0.0


def _bate(d, ch):
    """A chave é desta nota? (modelo, série e número dentro da chave = os do C100)"""
    return len(ch) == 44 and ch[20:22] == d['mod'] and int(ch[22:25]) == _int(d['serie']) and int(ch[25:34]) == _int(d['num'])


def _buraco(docs, d):
    """Nota própria: número que falta na sequência perto desta (ex.: 115102 lançada duas vezes e a 115104 sumida)."""
    if d['emit'] != '0':
        return ''
    nums = {_int(x['num']) for x in docs if x['emit'] == '0' and x['mod'] == d['mod'] and _int(x['serie']) == _int(d['serie'])}
    n = _int(d['num'])
    faltam = [k for k in range(n - 5, n + 6) if k > 0 and k not in nums and min(nums) < k < max(nums)]
    return str(faltam[0]) if len(faltam) == 1 else ''


def _estrutura(linhas):
    cnpj, part, docs = '', {}, []
    for i, l in enumerate(linhas):
        c = l.split('|')
        if len(c) < 3:
            continue
        r = c[1]
        if r == '0000' and len(c) > 7:
            cnpj = _dig(c[7]) or _dig(c[8] if len(c) > 8 else '')
        elif r == '0150' and len(c) > 6:
            part[c[2]] = {'nome': c[3], 'doc': _dig(c[5]) or _dig(c[6])}
        elif r == 'C100' and len(c) > 12 and c[5] in MODS:
            docs.append({'i': i, 'oper': c[2], 'emit': c[3], 'part': c[4], 'mod': c[5], 'sit': c[6], 'serie': c[7],
                         'num': c[8], 'chave': _dig(c[9]), 'dt': c[10], 'vl': c[12]})
    return cnpj, part, docs


def _leitura(texto):
    linhas, quebra, final_vazio = dr.dividir(texto)
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), None)
    assinado = fim is not None and fim < len(linhas) - 1
    if fim is not None:
        linhas = linhas[:fim + 1]
        if assinado:
            final_vazio = True
    return linhas, quebra, final_vazio, assinado


def analisar_texto(texto, xmls=None):
    xmls = {k: v for k, v in (xmls or {}).items() if v.get('tipo', 'nfe') == 'nfe' and v.get('mod') in MODS}
    linhas, _, _, _ = _leitura(texto)
    cnpj, part, docs = _estrutura(linhas)
    por_id = {}
    for ch, x in xmls.items():
        por_id.setdefault((_dig(x.get('emit_cnpj')).zfill(14), x.get('mod'), _int(x.get('serie')), _int(x.get('num'))), []).append(ch)
    docs_i = {d['i']: d for d in docs}
    chaves_sped = {}
    for d in docs:
        if d['chave']:
            chaves_sped.setdefault(d['chave'], []).append(d['i'])
    itens, pend, cont = [], [], {'ok': 0, 'sem_xml': 0, 'entrada': 0, 'saida': 0}
    usados = set()
    for k, d in enumerate(docs):
        p = part.get(d['part'], {})
        emit_doc = (cnpj if d['emit'] == '0' else p.get('doc', '')).zfill(14)
        quem = 'saída' if d['oper'] == '1' else 'entrada'
        nome = 'NFC-e' if d['mod'] == '65' else ('NF-e própria' if d['emit'] == '0' else p.get('nome') or d['part'])
        try:
            vl = float((d['vl'] or '0').replace('.', '').replace(',', '.'))
        except ValueError:
            vl = 0.0
        base = {'doc': k, 'id': str(k), 'num': d['num'], 'serie': d['serie'], 'mod': d['mod'], 'quem': quem, 'nome': nome,
                'dt': d['dt'], 'valor': round(vl, 2), 'chave_sped': d['chave']}
        x = xmls.get(d['chave'])
        if x and _int(x.get('num')) == _int(d['num']) and _int(x.get('serie')) == _int(d['serie']):
            cont['ok'] += 1
            usados.add(d['chave'])
            continue
        cands = por_id.get((emit_doc, d['mod'], _int(d['serie']), _int(d['num'])), [])
        if len(cands) == 1:
            certa = cands[0]
            usados.add(certa)
            xc = xmls[certa]
            if certa in chaves_sped and any(i != d['i'] for i in chaves_sped[certa]):
                pend.append({**base, 'motivo': 'a chave certa (do XML) já está em outro C100: a nota está lançada duas vezes',
                             'chave_xml': certa})
                continue
            if not d['chave']:
                mot = 'chave vazia no SPED'
            elif x:
                mot = f"a chave do SPED é de outra nota (NF {_int(x.get('num'))}, série {_int(x.get('serie'))})"
            elif not dv_ok(d['chave']):
                mot = 'chave do SPED com dígito verificador inválido (erro de digitação)'
            else:
                mot = 'a chave do SPED não é a do XML desta nota'
            dif = round((xc.get('vnf') or 0) - vl, 2)
            if abs(dif) > 0.05 and d['sit'] not in CANC:
                mot += f" · atenção: valor no SPED R$ {_brl(vl)} × XML R$ {_brl(xc.get('vnf') or 0)}"
            itens.append({**base, 'chave_xml': certa, 'motivo': mot})
            cont['entrada' if quem == 'entrada' else 'saida'] += 1
            continue
        cont['sem_xml'] += 1
        # sem XML: confere a chave em si e de quem ela é dentro do próprio arquivo
        ch = d['chave']
        prob = ''
        outros = [o for o in chaves_sped.get(ch, []) if o != d['i']] if ch else []
        dono = next((docs_i[o] for o in outros if _bate(docs_i[o], ch)), None)
        canc = ' (nota cancelada)' if d['sit'] in CANC else ''
        if dono is not None and not _bate(d, ch):
            pend.append({**base, 'motivo': f"a chave é da {_nome_mod(dono['mod'])} {_int(dono['num'])} (linha {dono['i'] + 1}) e foi copiada "
                                            f"para esta nota{canc} — anexe o XML desta nota para pôr a chave certa", 'chave_xml': ''})
            continue
        if outros and _bate(d, ch) and any(_bate(docs_i[o], ch) for o in outros):
            prim = min([d['i']] + [o for o in outros if _bate(docs_i[o], ch)])
            if d['i'] != prim:
                falta = _buraco(docs, d)
                pend.append({**base, 'motivo': f"a mesma {_nome_mod(d['mod'])} {_int(d['num'])} está lançada duas vezes (linhas {prim + 1} e {d['i'] + 1})"
                                                + (f" com valores diferentes (R$ {_brl(_vl(docs_i[prim]))} × R$ {_brl(vl)})" if abs(_vl(docs_i[prim]) - vl) > 0.005 else ' com o mesmo valor')
                                                + (f"; pela sequência, esta deve ser a {falta}, que não aparece no arquivo" if falta else '')
                                                + ' — anexe o XML para conferir', 'chave_xml': ''})
            continue
        if d['mod'] == '55' and not ch and d['sit'] not in CANC:
            prob = 'chave vazia e sem XML da nota'
        elif ch and not dv_ok(ch):
            prob = 'dígito verificador inválido'
        elif ch:
            if ch[20:22] != d['mod']:
                prob = f'o modelo dentro da chave ({ch[20:22]}) não é o do C100 ({d["mod"]})'
            elif int(ch[22:25]) != _int(d['serie']) or int(ch[25:34]) != _int(d['num']):
                prob = f'série/número dentro da chave ({int(ch[22:25])}/{int(ch[25:34])}) não são os do C100'
            elif emit_doc.strip('0') and ch[6:20] != emit_doc and d['emit'] == '0':
                prob = 'o CNPJ dentro da chave não é o da empresa (nota própria)'
        if prob:
            pend.append({**base, 'motivo': prob + canc + ' — anexe o XML para corrigir', 'chave_xml': ''})
    sobra = []
    for ch, x in xmls.items():
        if ch in usados or ch in chaves_sped:
            continue
        if _dig(x.get('emit_cnpj')).zfill(14) == cnpj.zfill(14):
            sobra.append({'chave': ch, 'quem': 'saída', 'num': x.get('num'), 'mod': x.get('mod'), 'valor': x.get('vnf')})
        elif _dig(x.get('dest_doc') or x.get('dest_cnpj')).zfill(14) == cnpj.zfill(14):
            sobra.append({'chave': ch, 'quem': 'entrada', 'num': x.get('num'), 'mod': x.get('mod'), 'valor': x.get('vnf'), 'emit': x.get('emit_nome')})
    return {'itens': itens, 'pendencias': pend, 'xml_sem_nota': sobra,
            'resumo': {'corrigir': len(itens), 'entradas': cont['entrada'], 'saidas': cont['saida'], 'ok': cont['ok'],
                       'sem_xml': cont['sem_xml'], 'pendencias': len(pend), 'xml_sem_nota': len(sobra),
                       'xml_sem_nota_ent': sum(1 for s in sobra if s['quem'] == 'entrada'),
                       'xml_sem_nota_sai': sum(1 for s in sobra if s['quem'] == 'saída')}}


def aplicar_texto(texto, ids, xmls=None):
    """ids: índices das notas (id da análise). -> (texto_novo, resumo)."""
    linhas, quebra, final_vazio, assinado = _leitura(texto)
    an = analisar_texto(quebra.join(linhas) + quebra, xmls)
    sel = set(ids)
    _, _, docs = _estrutura(linhas)
    res = {'itens': 0, 'entradas': 0, 'saidas': 0, 'avisos': []}
    for it in an['itens']:
        if it['id'] not in sel:
            continue
        d = docs[it['doc']]
        c = linhas[d['i']].split('|')
        c[9] = it['chave_xml']
        linhas[d['i']] = '|'.join(c)
        res['itens'] += 1
        res['entradas' if it['quem'] == 'entrada' else 'saidas'] += 1
    if assinado:
        res['avisos'].append('O arquivo estava assinado no PVA: a assinatura foi retirada (ela deixa de valer com a alteração). Valide e assine de novo no PVA.')
    novo = quebra.join(linhas) + (quebra if final_vazio else '')
    return novo, res

# -*- coding: utf-8 -*-
"""ICMS creditado no SPED × ICMS destacado no XML da nota de entrada (Corretor do SPED Fiscal, só Admin).

O crédito de ICMS é o imposto cobrado e destacado no documento da operação anterior (LC 87/96, arts. 19, 20 e 23).
Nota isenta ou não tributada (CST 40, 41, 50…) não dá crédito; e o crédito não pode passar do valor destacado.
O erro típico é o Domínio aplicar a alíquota do cadastro do produto ou do acumulador na entrada, sem olhar a nota.

Confere cada NF-e de entrada (C100 de terceiros, modelo 55) que tem XML: item a item (C170 × det do XML) e no total
(C190 × ICMSTot). Corrige só para baixo, até o que o XML destaca: base, alíquota e ICMS do C170 (e o CST, quando a nota
é isenta/não tributada), refaz o C190 da nota e os totais do C100, diminui o campo 06 do E110, ajusta o E116 e reconta
o Bloco 9. Gera arquivo NOVO; o original nunca é alterado.

Fica de fora (outros módulos cuidam): fornecedor do Simples Nacional (crédito do Simples, C197), CFOP de uso e consumo e
ativo (x.556, x.407, x.551, x.406 — quadro de crédito do DIFAL) e crédito presumido/ajustes lançados em C197.
"""
import os
import re
import sys
import json
from decimal import Decimal

import difal_ro as dr

TOL = 0.01
CANC = {'02', '03', '04', '05'}
CST_SEM_CREDITO = {'40', '41', '50', '51', '60'}     # sem ICMS próprio destacado na nota


def _D(v):
    return Decimal(str(v))


def _q(v):
    return dr._d(v)


def _fora(cfop):
    """CFOP de uso e consumo / ativo: o crédito desses é conferido no quadro do DIFAL (LC 87/96, art. 33, I)."""
    return (cfop or '')[1:] in dr.TIPOS


def _casar(d, x):
    """Liga cada C170 ao item do XML: pelo número do item com o mesmo valor; senão, pelo valor (único).
    Devolve {i_c170: item_xml} e a lista de C170 que não casaram."""
    itens = x.get('itens') or []
    por_n = {str(int(it['n'])) if (it.get('n') or '').isdigit() else it.get('n'): it for it in itens}
    usados, par, sobra = set(), {}, []
    for c in d['c170']:
        it = por_n.get(c['num'])
        if it is not None and abs((it['vprod'] - it['vdesc']) - c['vl']) <= 0.02 and id(it) not in usados:
            par[c['i']] = it
            usados.add(id(it))
        else:
            sobra.append(c)
    resto = []
    for c in sobra:
        cand = [it for it in itens if id(it) not in usados and abs((it['vprod'] - it['vdesc']) - c['vl']) <= 0.02]
        if len(cand) == 1:
            par[c['i']] = cand[0]
            usados.add(id(cand[0]))
        else:
            resto.append(c)
    return par, resto


def _novo_item(c, it):
    """Valores que o C170 deve ter pelo XML, ou None se já está certo. Corrige só para baixo: crédito acima do destacado
    vai para o valor da nota; nota sem destaque zera base, alíquota e ICMS e leva o CST do XML (40, 41, 50, 51, 60)."""
    if it['vicms'] <= TOL:
        if c['icms'] > TOL or c['bc'] > TOL or c['aliq'] > 0:
            return {'bc': 0.0, 'aliq': 0.0, 'icms': 0.0, 'cst': _cst_xml(it) if it.get('cst') in CST_SEM_CREDITO else c['cst']}
        return None
    if c['icms'] > it['vicms'] + TOL:
        return {'bc': it['vbc'], 'aliq': it['picms'], 'icms': it['vicms'], 'cst': c['cst']}
    return None


def _cst_xml(it):
    return (it.get('orig') or '0') + (it.get('cst') or '')


def analisar_texto(texto, xmls):
    linhas, _, _ = dr.dividir(texto)
    cab, part, _, docs, e110, _ = dr._estrutura(linhas)
    out = []
    conferidas = sem_xml = 0
    for d in docs:
        if d['oper'] != '0' or d['emit'] != '1' or d['mod'] != '55' or d['sit'] in CANC:
            continue
        x = xmls.get(re.sub(r'\D', '', d['chave'] or ''))
        if not x or x.get('tipo') not in (None, 'nfe') or 'erro' in x:
            sem_xml += 1
            continue
        if x.get('simples'):
            continue                      # crédito do Simples: módulo próprio (C197 RO00000001)
        conferidas += 1
        p = part.get(d['part'], {})
        uf, _ = dr._uf_emitente(d, part)
        c190_cred = [c for c in d['c190'] if not _fora(c['cfop'])]
        icms_sped = float(_q(sum(c['vl_icms'] for c in c190_cred)))
        bc_sped = float(_q(sum(c['vl_bc'] for c in c190_cred)))
        itens, mudancas, obs = [], [], []
        excl = set()           # itens do XML que no SPED são uso e consumo / ativo (conferidos no quadro do DIFAL)
        casamento = 'item'
        if d['c170']:
            par, resto = _casar(d, x)
            for c in d['c170']:
                if _fora(c['cfop']):
                    if c['i'] in par:
                        excl.add(id(par[c['i']]))
                    continue
                it = par.get(c['i'])
                if it is None:
                    continue
                novo = _novo_item(c, it)
                if c['icms'] > it['vicms'] + TOL:
                    st = 'sem_destaque' if it['vicms'] <= TOL else 'maior'
                elif novo:
                    st = 'ajuste'           # sem crédito, mas com base/CST de tributado numa nota sem destaque
                elif it['vicms'] > TOL and c['icms'] < it['vicms'] - TOL:
                    st = 'menor'
                else:
                    st = 'ok'
                itens.append({'num': c['num'], 'descr': c['descr'], 'xprod': it['xprod'], 'ncm': it['ncm'], 'cfop': c['cfop'],
                              'cst_sped': c['cst'], 'cst_xml': _cst_xml(it) if it.get('cst') else (it.get('csosn') or ''),
                              'aliq_sped': c['aliq'], 'aliq_xml': it['picms'], 'bc_sped': c['bc'], 'bc_xml': it['vbc'],
                              'icms_sped': c['icms'], 'icms_xml': it['vicms'], 'status': st})
                if novo:
                    mudancas.append({'i': c['i'], 'old': c, 'novo': novo})
            resto = [c for c in resto if not _fora(c['cfop'])]
            if resto:
                casamento = 'nota'
                obs.append(f'{len(resto)} item(ns) do SPED não casaram com o XML (número ou valor diferente): conferido pelo total da nota.')
        else:
            casamento = 'nota'
            obs.append('Nota sem itens (C170): conferida pelo resumo (C190).')
        icms_xml = float(_q(sum(it['vicms'] for it in x.get('itens') or [] if id(it) not in excl)))
        dif = float(_q(icms_sped - icms_xml))
        cred_mud = [m for m in mudancas if m['old']['icms'] > m['novo']['icms'] + TOL]
        if casamento == 'item' and not cred_mud:
            if icms_sped < icms_xml - TOL:
                status = 'menor'
            elif dif > TOL:
                status = 'maior_sem_item'      # diferença fora dos itens (ex.: C190 com valor a mais)
            else:
                status = 'ok'
        elif casamento == 'item':
            status = 'sem_destaque' if icms_xml <= TOL else 'maior'
        else:                                   # pelo total da nota
            if dif > TOL:
                status = 'sem_destaque' if icms_xml <= TOL else 'maior_sem_item'
            elif icms_sped < icms_xml - TOL:
                status = 'menor'
            else:
                status = 'ok'
        if status == 'ok':
            continue
        corrigivel = status in ('sem_destaque', 'maior') and (bool(cred_mud) or (status == 'sem_destaque' and casamento == 'nota'))
        if status == 'maior_sem_item':
            obs.append('O SPED credita mais que a nota, mas a diferença não está em itens que casaram com o XML: corrija à mão.')
        if status == 'menor':
            obs.append('A nota destaca mais ICMS do que o SPED creditou. Pode estar certo (ex.: mercadoria sem direito a crédito) — só informativo.')
        if x.get('vicms_deson', 0) > 0 and status == 'sem_destaque':
            obs.append(f'A nota tem ICMS desonerado (R$ {dr._f(x["vicms_deson"])}): o imposto foi dispensado na origem, não destacado.')
        if casamento == 'nota':
            reducao = dif if corrigivel else 0.0
        else:
            reducao = float(_q(sum(m['old']['icms'] - m['novo']['icms'] for m in mudancas)))
        out.append({
            'id': d['i'], 'num': d['num'], 'serie': d['serie'], 'data': d['dt'], 'chave': d['chave'],
            'fornecedor': p.get('nome') or x.get('emit_nome', ''), 'cnpj': p.get('cnpj', '') or x.get('emit_cnpj', ''), 'uf': uf,
            'icms_sped': icms_sped, 'icms_xml': icms_xml, 'bc_sped': bc_sped, 'bc_xml': float(_q(x.get('vbc_icms', 0.0))),
            'diferenca': dif, 'reducao': reducao, 'status': status, 'casamento': casamento,
            'csts_xml': sorted({i['cst_xml'] for i in itens if i['cst_xml']}),
            'aliqs_sped': sorted({c['aliq'] for c in c190_cred if c['vl_icms'] > 0}),
            'itens': [i for i in itens if i['status'] not in ('ok', 'ajuste')][:60], 'itens_ok': sum(1 for i in itens if i['status'] == 'ok'),
            'itens_ajuste': sum(1 for i in itens if i['status'] == 'ajuste'),
            'obs': obs, 'sugerido': corrigivel,
        })
    apur = None
    if e110:
        c = e110['c']
        apur = {'cred': dr._n(c[6]), 'recolher': dr._n(c[13]), 'sld_transp': dr._n(c[14])}
    soma = lambda st, k: float(_q(sum(x[k] for x in out if x['status'] in st)))
    return {
        'empresa': {'nome': cab.get('nome', ''), 'cnpj': cab.get('cnpj', ''), 'uf': cab.get('uf', ''), 'dt_ini': cab.get('dt_ini', ''),
                    'dt_fin': cab.get('dt_fin', '')},
        'docs': out, 'e110': apur,
        'e116': [{'cod': c[2], 'valor': dr._n(c[3]), 'venc': c[4], 'cod_rec': c[5]}
                 for c in (ln.split('|') for ln in linhas if ln.startswith('|E116|')) if len(c) > 5],
        'resumo': {
            'notas_conferidas': conferidas, 'notas_sem_xml': sem_xml,
            'sem_destaque': sum(1 for x in out if x['status'] == 'sem_destaque'),
            'maior': sum(1 for x in out if x['status'] == 'maior'),
            'maior_sem_item': sum(1 for x in out if x['status'] == 'maior_sem_item'),
            'menor': sum(1 for x in out if x['status'] == 'menor'),
            'credito_indevido': soma(('sem_destaque', 'maior', 'maior_sem_item'), 'diferenca'),
            'credito_corrigivel': float(_q(sum(x['reducao'] for x in out if x['sugerido']))),
            'credito_nao_tomado': float(_q(-sum(x['diferenca'] for x in out if x['status'] == 'menor'))),
        },
    }


# ------------------------------------------------------------------ aplicação
def _refaz_c190(linhas, d, mudancas, remover, insercoes):
    """Refaz o C190 da nota depois de mudar o C170: tira base/ICMS do grupo antigo (CST+CFOP+alíquota), põe no grupo
    novo e leva junto, proporcional ao valor do item, a parte do VL_OPR, da ST, da redução e do IPI (o último item de um
    grupo que muda inteiro leva o resto exato). Grupo que fica sem valor sai; grupo novo entra depois do último C190 da
    nota. Devolve (base_total, icms_total) da nota, ou None se o C190 não corresponder aos itens."""
    from collections import defaultdict

    def chave(cst, cfop, aliq):
        return (cst, cfop, dr._f(_D(aliq)))
    grupos, ordem, ultimo = {}, [], None
    for g in d['c190']:
        if g['i'] in remover:
            continue
        c = linhas[g['i']].split('|')
        k = chave(c[2], c[3], dr._n(c[4]))
        ultimo = g['i']
        if k in grupos:
            for j in range(5, 12):
                grupos[k]['v'][j] += _D(dr._n(c[j]))
            remover.add(g['i'])
            continue
        grupos[k] = {'i': g['i'], 'c': c, 'v': {j: _D(dr._n(c[j])) for j in range(5, 12)}}
        ordem.append(k)
    todos, peso, por_grupo = defaultdict(int), defaultdict(Decimal), defaultdict(list)
    for c in d['c170']:
        k = chave(c['cst'], c['cfop'], c['aliq'])
        todos[k] += 1
        peso[k] += _D(c['vl'])
    for m in mudancas:
        o = m['old']
        por_grupo[chave(o['cst'], o['cfop'], o['aliq'])].append(m)
    for ko, ms in por_grupo.items():
        go = grupos.get(ko)
        if go is None:
            return None
        v0 = dict(go['v'])
        inteiro = len(ms) == todos[ko]
        acum = defaultdict(Decimal)
        for n_m, m in enumerate(ms):
            o, n = m['old'], m['novo']
            kn = chave(n['cst'], o['cfop'], n['aliq'])
            if kn not in grupos:
                c = list(go['c'])
                c[2], c[4] = n['cst'], dr._f(_D(n['aliq']))
                if len(c) > 12:
                    c[12] = ''
                grupos[kn] = {'i': None, 'c': c, 'v': {j: Decimal('0') for j in range(5, 12)}}
                ordem.append(kn)
            gn = grupos[kn]
            if kn != ko:
                for j in (5, 8, 9, 10, 11):
                    if inteiro and n_m == len(ms) - 1:
                        parte = v0[j] - acum[j]
                    else:
                        parte = _q(v0[j] * _D(o['vl']) / peso[ko]) if peso[ko] else Decimal('0')
                    acum[j] += parte
                    go['v'][j] -= parte
                    gn['v'][j] += parte
            go['v'][6] -= _D(o['bc'])
            go['v'][7] -= _D(o['icms'])
            gn['v'][6] += _D(n['bc'])
            gn['v'][7] += _D(n['icms'])
    bc_t = icms_t = Decimal('0')
    novas = []
    for k in ordem:
        g = grupos[k]
        for j in range(5, 12):
            if g['v'][j] < 0:
                g['v'][j] = Decimal('0')
        if abs(g['v'][5]) < Decimal('0.005'):           # grupo sem valor de operação: sai
            if g['i'] is not None:
                remover.add(g['i'])
            continue
        c = g['c']
        for j in range(5, 12):
            c[j] = dr._f(g['v'][j])
        bc_t += g['v'][6]
        icms_t += g['v'][7]
        if g['i'] is not None:
            linhas[g['i']] = '|'.join(c)
        else:
            novas.append('|'.join(c))
    if novas:
        insercoes.setdefault(ultimo if ultimo is not None else d['fim'], []).extend(novas)
    return bc_t, icms_t


def aplicar_texto(texto, xmls, selecao):
    """selecao = {'docs': [id, ...], 'e116': {...}} -> (texto_novo, resumo)"""
    linhas, quebra, final_vazio = dr.dividir(texto)
    an = analisar_texto(texto, xmls)
    por_id = {x['id']: x for x in an['docs']}
    cab, part, _, docs, e110, _ = dr._estrutura(linhas)
    docs_por_i = {d['i']: d for d in docs}
    resumo = {'notas': 0, 'c170': 0, 'credito_retirado': 0.0, 'detalhe': [], 'avisos': [], 'e110_antes': None, 'e110_depois': None, 'e116': ''}
    remover, insercoes = set(), {}
    d06 = Decimal('0')
    for i in selecao.get('docs', []):
        a, d = por_id.get(i), docs_por_i.get(i)
        if not a or not d or not a['sugerido']:
            continue
        x = xmls.get(re.sub(r'\D', '', d['chave'] or ''))
        mudancas = []
        if a['casamento'] == 'item':
            par, _ = _casar(d, x)
            for c in d['c170']:
                it = par.get(c['i'])
                if it is None or _fora(c['cfop']):
                    continue
                novo = _novo_item(c, it)
                if not novo:
                    continue
                mudancas.append({'i': c['i'], 'old': c, 'novo': novo})
        else:                                           # nota isenta inteira: zera os itens com crédito
            for c in d['c170']:
                if not _fora(c['cfop']) and (c['icms'] > TOL or c['bc'] > TOL):
                    mudancas.append({'i': c['i'], 'old': c, 'novo': {'bc': 0.0, 'aliq': 0.0, 'icms': 0.0, 'cst': c['cst']}})
        antes_icms = _D(sum(c['vl_icms'] for c in d['c190']))
        if mudancas:
            for m in mudancas:
                c = linhas[m['i']].split('|')
                c[10] = m['novo']['cst']
                c[13], c[14], c[15] = dr._f(_D(m['novo']['bc'])), dr._f(_D(m['novo']['aliq'])), dr._f(_D(m['novo']['icms']))
                linhas[m['i']] = '|'.join(c)
                resumo['c170'] += 1
            r = _refaz_c190(linhas, d, mudancas, remover, insercoes)
            if r is None:
                return texto, {'erro': f'NF {a["num"]}: o C190 da nota não bate com os itens (C170); corrija essa nota à mão.'}
            bc_t, icms_t = r
        elif not d['c170'] and a['casamento'] == 'nota':  # sem itens: zera o C190 de crédito
            bc_t = icms_t = Decimal('0')
            for g in d['c190']:
                c = linhas[g['i']].split('|')
                if not _fora(c[3]) and dr._n(c[7]) > TOL:
                    c[4] = c[6] = c[7] = '0,00'
                    linhas[g['i']] = '|'.join(c)
                bc_t += _D(dr._n(c[6]))
                icms_t += _D(dr._n(c[7]))
            dr._junta_c190(linhas, d, remover)
        else:
            continue
        c = linhas[d['i']].split('|')
        if len(c) > 22:
            c[21], c[22] = dr._f(bc_t), dr._f(icms_t)
            linhas[d['i']] = '|'.join(c)
        tirado = antes_icms - icms_t
        if tirado <= 0:
            continue
        d06 -= tirado
        resumo['notas'] += 1
        resumo['detalhe'].append({'num': a['num'], 'fornecedor': a['fornecedor'], 'retirado': float(_q(tirado))})
    resumo['credito_retirado'] = float(_q(-d06))
    deltas = {6: float(d06)} if abs(d06) >= Decimal('0.005') else {}
    novas_e116, erro = dr.aplica_apuracao(linhas, e110, deltas, selecao, cab, remover, resumo)
    if erro:
        return texto, {'erro': erro}
    novo = dr.monta_arquivo(linhas, remover, insercoes, [], [], novas_e116, quebra, final_vazio)
    return novo, resumo


# ------------------------------------------------------------------ CLI
def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    sped, js, xs = opt('--sped'), opt('--json'), opt('--xmls')
    if not sped or not js:
        print('uso: icms-xml --sped ARQ.txt --xmls "pasta;a.zip" --json saida.json [--aplicar selecao.json --saida novo.txt]')
        return 1
    try:
        from xml_entradas import ler_xmls
        texto, enc = dr._ler(sped)
        xmls, lidos, erros = ler_xmls([c for c in (xs or '').split(os.pathsep) if c])
        if opt('--aplicar'):
            with open(opt('--aplicar'), 'r', encoding='utf-8') as fh:
                sel = json.load(fh)
            novo, res = aplicar_texto(texto, xmls, sel)
            if not res.get('erro'):
                tmp = opt('--saida') + '.parcial'
                with open(tmp, 'w', encoding=enc, newline='') as fh:
                    fh.write(novo)
                os.replace(tmp, opt('--saida'))
        else:
            res = analisar_texto(texto, xmls)
            res['resumo'].update({'xml_lidos': lidos, 'xml_erros': erros})
    except Exception as e:  # pragma: no cover
        res = {'erro': f'Falha ao processar: {e}'}
    tmp = js + '.parcial'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False)
    os.replace(tmp, js)
    return 0


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main_cli(sys.argv[1:]))

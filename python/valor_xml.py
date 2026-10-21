# -*- coding: utf-8 -*-
"""Valor do documento e base de cálculo do ICMS no SPED × XML da nota de entrada (Corretor do SPED Fiscal, só Admin).

Confere cada NF-e de entrada de terceiros (C100 modelo 55) que tem XML, em três pontos:
  • Valor do documento (C100 campo 12) × vNF do XML — com o detalhe de onde está a diferença (mercadorias, desconto,
    frete, seguro, outras despesas). O C100 tem de repetir os totais da nota (Guia Prático da EFD ICMS/IPI, registro
    C100: VL_DOC, VL_DESC, VL_MERC, VL_FRT, VL_SEG, VL_OUT_DA) e a soma do VL_OPR do C190 tem de dar o VL_DOC.
  • Base de cálculo do ICMS (C170 / C190 / C100) × vBC do XML, item a item.
  • ICMS creditado × vICMS do XML (o crédito é o imposto destacado — LC 87/96, arts. 19, 20 e 23).

O que o sistema faz, sem decisão do usuário:
  • Valor do documento diferente: o C100 recebe os totais do XML (VL_DOC, VL_DESC, VL_MERC, VL_FRT, VL_SEG, VL_OUT_DA)
    e o VL_OPR do C190 é refeito para somar o vNF. Não mexe em base nem em ICMS (não muda a apuração).
  • Base maior que o XML: base, alíquota e ICMS do item vão para o que o XML destaca (nunca para cima), o C190 e o C100
    são refeitos e o campo 06 do E110 diminui o crédito retirado.
  • Base menor que o XML: só informativo (crédito que a empresa pode ter deixado de tomar) — não altera nada.

Ficam fora (listadas à parte, sem alteração): uso e consumo (x.556, x.407) e ativo (x.551, x.406, crédito pelo CIAP),
notas canceladas/denegadas e entradas sem XML. Itens com ICMS-ST retido, isentos e não tributados só são corrigidos
quando o SPED dá base/crédito que o XML não tem. Gera arquivo NOVO; o original nunca é alterado.
"""
import os
import re
import sys
import json
from decimal import Decimal

import difal_ro as dr
import icms_xml as ix

TOL = 0.01
TOL_DOC = 0.05                  # diferença mínima no valor do documento para corrigir
CANC = {'02', '03', '04', '05'}
CAMPOS_C100 = (('vl_doc', 12, 'vnf', 'Valor do documento'), ('vl_desc', 14, 'vdesc', 'Desconto'),
               ('vl_merc', 16, 'vprod', 'Mercadorias'), ('vl_frt', 18, 'vfrete', 'Frete'),
               ('vl_seg', 19, 'vseg', 'Seguro'), ('vl_out', 20, 'voutro', 'Outras despesas'))


def _D(v):
    return Decimal(str(v))


def _q(v):
    return dr._d(v)


def _f(v):
    return dr._f(v)


def _c100(linhas, d):
    c = linhas[d['i']].split('|')
    return {k: dr._n(c[i]) if len(c) > i else 0.0 for k, i, _, _ in CAMPOS_C100}


def _novo_item(c, it):
    """Base/alíquota/ICMS que o C170 deve ter pelo XML, ou None. Só corrige para baixo."""
    if it['vicms'] <= TOL:
        return ix._novo_item(c, it)          # nota sem destaque: zera e leva o CST do XML
    if c['bc'] > it['vbc'] + TOL or c['icms'] > it['vicms'] + TOL:
        icms = min(c['icms'], it['vicms'])
        aliq = it['picms'] if abs(icms - it['vicms']) <= TOL else c['aliq']
        return {'bc': min(c['bc'], it['vbc']), 'aliq': aliq, 'icms': icms, 'cst': c['cst']}
    return None


def _difs_c100(sped, x):
    """Campos do C100 diferentes do XML: [(campo, rótulo, sped, xml)]."""
    out = []
    for k, _, kx, rot in CAMPOS_C100:
        vx = float(x.get(kx) or 0.0)
        if abs(sped[k] - vx) > TOL:
            out.append({'campo': k, 'rotulo': rot, 'sped': sped[k], 'xml': vx})
    return out


def analisar_texto(texto, xmls):
    linhas, _, _ = dr.dividir(texto)
    cab, part, _, docs, e110, _ = dr._estrutura(linhas)
    out, fora = [], {'uso_ativo': [], 'canceladas': 0, 'sem_xml': []}
    conferidas = batem = 0
    for d in docs:
        if d['oper'] != '0' or d['emit'] != '1' or d['mod'] != '55':
            continue
        p = part.get(d['part'], {})
        if d['sit'] in CANC:
            fora['canceladas'] += 1
            continue
        cfops = {g['cfop'] for g in d['c190']}
        if cfops and all(ix._fora(cf) for cf in cfops):
            fora['uso_ativo'].append({'num': d['num'], 'data': d['dt'], 'fornecedor': p.get('nome', d['part']),
                                      'cfops': sorted(cfops), 'valor': float(_q(sum(g['vl_opr'] for g in d['c190'])))})
            continue
        x = xmls.get(re.sub(r'\D', '', d['chave'] or ''))
        sped = _c100(linhas, d)
        if not x or x.get('tipo') not in (None, 'nfe') or 'erro' in x:
            fora['sem_xml'].append({'num': d['num'], 'serie': d['serie'], 'data': d['dt'], 'chave': d['chave'],
                                    'fornecedor': p.get('nome', d['part']), 'cnpj': p.get('cnpj', ''), 'vl_doc': sped['vl_doc']})
            continue
        conferidas += 1
        uf, _ = dr._uf_emitente(d, part)
        obs, itens, mudancas = [], [], []
        # 1) valor do documento
        dif_doc = float(_q(sped['vl_doc'] - x['vnf']))
        doc_dif = abs(dif_doc) > TOL_DOC
        campos = _difs_c100(sped, x) if doc_dif else []
        if doc_dif:
            det = [c for c in campos if c['campo'] not in ('vl_doc', 'vl_out')]
            if det:
                obs.append('Diferença em: ' + '; '.join(f'{c["rotulo"].lower()} SPED R$ {_f(c["sped"])} × nota R$ {_f(c["xml"])}' for c in det) + '.')
            outras = next((c for c in campos if c['campo'] == 'vl_out'), None)
            if outras and outras['sped'] > outras['xml'] + TOL:
                obs.append(f'O SPED tem R$ {_f(outras["sped"] - outras["xml"])} de outras despesas que não existem na nota. '
                           'Custo pago à parte (frete de CT-e, por exemplo) não entra no C100 da NF-e.')
        # 2) base e ICMS, item a item (sem uso e consumo / ativo)
        casamento = 'item'
        excl = set()
        if d['c170']:
            par, resto = ix._casar(d, x)
            for c in d['c170']:
                if ix._fora(c['cfop']):
                    if c['i'] in par:
                        excl.add(id(par[c['i']]))
                    continue
                it = par.get(c['i'])
                if it is None:
                    continue
                novo = _novo_item(c, it)
                if novo:
                    st = 'base_maior' if c['bc'] > it['vbc'] + TOL else 'icms_maior'
                    mudancas.append({'i': c['i'], 'old': c, 'novo': novo})
                elif it['vicms'] > TOL and c['bc'] < it['vbc'] - TOL and not (ix._tem_st(it) and c['icms'] <= TOL) \
                        and c['cst'][-2:] != '60':
                    st = 'base_menor'
                else:
                    st = 'ok'
                if st != 'ok':
                    itens.append({'num': c['num'], 'descr': c['descr'], 'xprod': it['xprod'], 'cfop': c['cfop'],
                                  'cst_sped': c['cst'], 'cst_xml': ix._cst_xml(it) if it.get('cst') else (it.get('csosn') or ''),
                                  'bc_sped': c['bc'], 'bc_xml': it['vbc'], 'aliq_sped': c['aliq'], 'aliq_xml': it['picms'],
                                  'icms_sped': c['icms'], 'icms_xml': it['vicms'], 'status': st})
            resto = [c for c in resto if not ix._fora(c['cfop'])]
            if resto:
                casamento = 'nota'
                obs.append(f'{len(resto)} item(ns) do SPED não casaram com o XML (número ou valor diferente): base conferida pelo total.')
        else:
            casamento = 'nota'
        c190_cred = [g for g in d['c190'] if not ix._fora(g['cfop'])]
        bc_sped = float(_q(sum(g['vl_bc'] for g in c190_cred)))
        icms_sped = float(_q(sum(g['vl_icms'] for g in c190_cred)))
        xi = [it for it in x.get('itens') or [] if id(it) not in excl]
        bc_xml = float(_q(sum(it['vbc'] for it in xi)))
        icms_xml = float(_q(sum(it['vicms'] for it in xi)))
        st_it = {i['status'] for i in itens}
        if casamento == 'item':
            base = 'maior' if mudancas else ('menor' if 'base_menor' in st_it else 'ok')
        else:
            base = 'maior_sem_item' if bc_sped > bc_xml + TOL or icms_sped > icms_xml + TOL else (
                'menor' if bc_sped < bc_xml - TOL and icms_xml > TOL else 'ok')
        if base == 'maior_sem_item':
            obs.append('O SPED tem base ou crédito acima da nota, mas a diferença não está em itens que casaram com o XML: corrija à mão.')
        if base == 'menor':
            obs.append('A base do SPED é menor que a da nota. Pode estar certo (mercadoria sem direito a crédito) — só informativo.')
        if not doc_dif and base == 'ok':
            batem += 1
            continue
        reducao = float(_q(sum(m['old']['icms'] - m['novo']['icms'] for m in mudancas)))
        menor = float(_q(sum(max(0.0, i['icms_xml'] - i['icms_sped']) for i in itens if i['status'] == 'base_menor'))) \
            if casamento == 'item' else (float(_q(max(0.0, icms_xml - icms_sped))) if base == 'menor' else 0.0)
        out.append({
            'id': d['i'], 'num': d['num'], 'serie': d['serie'], 'data': d['dt'], 'chave': d['chave'],
            'fornecedor': p.get('nome') or x.get('emit_nome', ''), 'cnpj': p.get('cnpj', '') or x.get('emit_cnpj', ''), 'uf': uf,
            'vl_doc_sped': sped['vl_doc'], 'vl_doc_xml': x['vnf'], 'dif_doc': dif_doc, 'doc_dif': doc_dif, 'campos': campos,
            'bc_sped': bc_sped, 'bc_xml': bc_xml, 'icms_sped': icms_sped, 'icms_xml': icms_xml,
            'base': base, 'casamento': casamento, 'reducao': reducao, 'credito_nao_tomado': menor,
            'simples': bool(x.get('simples')),
            'itens': itens[:60], 'obs': obs,
            'sugerido': doc_dif or base == 'maior',
        })
    out.sort(key=lambda z: (not z['sugerido'], -(z['reducao'] or 0), -abs(z['dif_doc'])))
    apur = None
    if e110:
        c = e110['c']
        apur = {'cred': dr._n(c[6]), 'recolher': dr._n(c[13]), 'sld_transp': dr._n(c[14])}
    return {
        'empresa': {'nome': cab.get('nome', ''), 'cnpj': cab.get('cnpj', ''), 'uf': cab.get('uf', ''),
                    'dt_ini': cab.get('dt_ini', ''), 'dt_fin': cab.get('dt_fin', '')},
        'docs': out, 'e110': apur, 'fora': fora,
        'e116': [{'cod': c[2], 'valor': dr._n(c[3]), 'venc': c[4], 'cod_rec': c[5]}
                 for c in (ln.split('|') for ln in linhas if ln.startswith('|E116|')) if len(c) > 5],
        'resumo': {
            'notas_conferidas': conferidas, 'batem': batem,
            'doc_dif': sum(1 for z in out if z['doc_dif']),
            'doc_dif_total': float(_q(sum(abs(z['dif_doc']) for z in out if z['doc_dif']))),
            'base_maior': sum(1 for z in out if z['base'] == 'maior'),
            'base_maior_sem_item': sum(1 for z in out if z['base'] == 'maior_sem_item'),
            'credito_a_retirar': float(_q(sum(z['reducao'] for z in out if z['base'] == 'maior'))),
            'base_menor': sum(1 for z in out if z['base'] == 'menor'),
            'credito_nao_tomado': float(_q(sum(z['credito_nao_tomado'] for z in out))),
            'fora_uso_ativo': len(fora['uso_ativo']), 'fora_canceladas': fora['canceladas'], 'sem_xml': len(fora['sem_xml']),
        },
    }


# ------------------------------------------------------------------ aplicação
def _refaz_vl_opr(linhas, d, vnf, remover):
    """VL_OPR do C190 somando o vNF: cada grupo (CST+CFOP+alíquota) recebe o valor dos seus itens (VL_ITEM − VL_DESC +
    ICMS-ST + IPI do C170) e o frete/seguro/outras da nota proporcional; o último grupo leva o arredondamento.
    Sem itens ou com grupos que não batem com os itens: proporcional ao VL_OPR atual."""
    grupos = [g for g in d['c190'] if g['i'] not in remover]
    if not grupos:
        return
    linhas_g = {g['i']: linhas[g['i']].split('|') for g in grupos}
    k = lambda cst, cfop, aliq: (cst, cfop, _f(_D(aliq)))
    chaves = {g['i']: k(linhas_g[g['i']][2], linhas_g[g['i']][3], dr._n(linhas_g[g['i']][4])) for g in grupos}
    peso = {}
    if d['c170']:
        for c in d['c170']:
            cc = linhas[c['i']].split('|')
            kk = k(cc[10], cc[11], dr._n(cc[14]) if len(cc) > 14 else 0.0)
            v = _D(dr._n(cc[7])) - _D(dr._n(cc[8])) + _D(dr._n(cc[18]) if len(cc) > 18 else 0) + _D(dr._n(cc[24]) if len(cc) > 24 else 0)
            peso[kk] = peso.get(kk, Decimal('0')) + v
    if not peso or set(peso) != set(chaves.values()):
        peso = {}
        for g in grupos:
            peso[chaves[g['i']]] = peso.get(chaves[g['i']], Decimal('0')) + _D(dr._n(linhas_g[g['i']][5]))
    tot_p = sum(peso.values())
    alvo = _D(vnf)
    if tot_p <= 0:
        return
    resto = alvo - tot_p
    acum = Decimal('0')
    usados = set()
    for n, g in enumerate(grupos):
        kk = chaves[g['i']]
        if kk in usados:            # grupo repetido: o primeiro leva tudo
            linhas_g[g['i']][5] = _f(0)
            continue
        usados.add(kk)
        v = peso[kk] + _q(resto * peso[kk] / tot_p)
        ult = all(chaves[h['i']] in usados for h in grupos[n + 1:])
        if ult:
            v = alvo - acum
        acum += v
        linhas_g[g['i']][5] = _f(max(Decimal('0'), v))
    for i, c in linhas_g.items():
        linhas[i] = '|'.join(c)


def aplicar_texto(texto, xmls, selecao):
    """selecao = {'docs': [id, ...], 'e116': {...}} -> (texto_novo, resumo)"""
    linhas, quebra, final_vazio = dr.dividir(texto)
    an = analisar_texto(texto, xmls)
    por_id = {z['id']: z for z in an['docs']}
    cab, part, _, docs, e110, _ = dr._estrutura(linhas)
    docs_por_i = {d['i']: d for d in docs}
    resumo = {'notas': 0, 'notas_doc': 0, 'notas_base': 0, 'c170': 0, 'credito_retirado': 0.0, 'detalhe': [], 'avisos': [],
              'e110_antes': None, 'e110_depois': None, 'e116': ''}
    remover, insercoes = set(), {}
    d06 = Decimal('0')
    for i in selecao.get('docs', []):
        a, d = por_id.get(i), docs_por_i.get(i)
        if not a or not d or not a['sugerido']:
            continue
        x = xmls.get(re.sub(r'\D', '', d['chave'] or ''))
        feito = []
        # valor do documento primeiro (o VL_OPR passado entre grupos pelo ajuste de base já sai certo)
        if a['doc_dif']:
            _refaz_vl_opr(linhas, d, x['vnf'], remover)
            c = linhas[d['i']].split('|')
            soma_itens = sum((_D(dr._n(linhas[it['i']].split('|')[7])) for it in d['c170']), Decimal('0'))
            for _, idx, kx, _ in CAMPOS_C100:
                if len(c) > idx:
                    v = _D(x.get(kx) or 0.0)
                    if idx == 16 and v < soma_itens:      # PVA: VL_MERC ≥ soma dos VL_ITEM do C170
                        v = soma_itens
                    c[idx] = _f(v)
            linhas[d['i']] = '|'.join(c)
            resumo['notas_doc'] += 1
            feito.append(f'valor do documento R$ {_f(a["vl_doc_sped"])} → R$ {_f(x["vnf"])}')
        tirado = Decimal('0')
        if a['base'] == 'maior' and a['casamento'] == 'item':
            par, _ = ix._casar(d, x)
            mudancas = []
            for c170 in d['c170']:
                it = par.get(c170['i'])
                if it is None or ix._fora(c170['cfop']):
                    continue
                novo = _novo_item(c170, it)
                if novo:
                    mudancas.append({'i': c170['i'], 'old': c170, 'novo': novo})
            if mudancas:
                antes = _D(sum(g['vl_icms'] for g in d['c190']))
                for m in mudancas:
                    c = linhas[m['i']].split('|')
                    c[10] = m['novo']['cst']
                    c[13], c[14], c[15] = _f(_D(m['novo']['bc'])), _f(_D(m['novo']['aliq'])), _f(_D(m['novo']['icms']))
                    linhas[m['i']] = '|'.join(c)
                    resumo['c170'] += 1
                r = ix._refaz_c190(linhas, d, mudancas, remover, insercoes)
                if r is None:
                    return texto, {'erro': f'NF {a["num"]}: o C190 da nota não bate com os itens (C170); corrija essa nota à mão.'}
                bc_t, icms_t = r
                c = linhas[d['i']].split('|')
                if len(c) > 22:
                    c[21], c[22] = _f(bc_t), _f(icms_t)
                    linhas[d['i']] = '|'.join(c)
                tirado = antes - icms_t
                resumo['notas_base'] += 1
                feito.append(f'base/ICMS de {len(mudancas)} item(ns) pelo XML' + (f', crédito − R$ {_f(tirado)}' if tirado > 0 else ''))
        if tirado > 0:
            d06 -= tirado
        if feito:
            resumo['notas'] += 1
            resumo['detalhe'].append({'num': a['num'], 'fornecedor': a['fornecedor'], 'feito': feito,
                                      'retirado': float(_q(max(Decimal('0'), tirado)))})
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
        print('uso: valor-xml --sped ARQ.txt --xmls "pasta;a.zip" --json saida.json [--aplicar selecao.json --saida novo.txt]')
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

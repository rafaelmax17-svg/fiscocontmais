# -*- coding: utf-8 -*-
"""Corretor do SPED Fiscal (Admin) — Crédito presumido da Área de Livre Comércio de Guajará-Mirim (ALCGM) × XML.

Base legal (RICMS/RO, Decreto 22.721/2018, Anexo IV, Parte 2, item 01 — consolidado até o Dec. 31.616/26):
  • Caput: crédito igual ao ICMS que seria devido sem a isenção nas entradas de produtos industrializados de origem
    nacional destinados à comercialização ou industrialização na ALCGM (Convênios ICM 65/88 e ICMS 52/92).
  • Nota 1: alíquota da operação de entrada sobre o valor das mercadorias, deduzidos os descontos incondicionais;
    vale TAMBÉM para mercadoria com substituição tributária e para as sujeitas ao Antecipado.
  • Nota 2: não se soma valor que não represente custo suportado pelo destinatário → remessa por conta e ordem
    (o custo está na nota de venda) e bonificação não dão crédito (decisão do escritório: bonificação sem crédito).
  • Nota 3: o crédito tem de constar como desconto na NF-e, no valor do ICMS isentado → o valor certo é o
    vICMSDeson do XML (sem XML, o abatimento informado no C100, campo 15 VL_ABAT_NT, que repete esse desconto).
  • IN de escrituração de RO (item 5): C195 com a observação + UM C197 por documento, código RO10000036, base usada
    para o desconto. Guia Prático da EFD ICMS/IPI: o C197 soma no campo 07 (VL_AJ_CREDITOS) do E110.

O que faz (só nas notas de entrada interestaduais, modelo 55, empresa de Guajará-Mirim ou que já usa o RO10000036):
  • valor do C197 diferente do desconto do XML → acerta base, alíquota e valor;
  • nota com desconto e sem C197 → inclui C195 + C197;
  • 2.4.59: item com ICMS-ST (C170 com CST x60 ou CFOP x.401/x.403) fica FORA do C197: o crédito presumido dele é
    aproveitado no cálculo do ICMS-ST da entrada (Parecer GETRI 342/2009: "no cálculo do ICMS/ST ou em conta gráfica",
    nunca nos dois). Aparece só como informação, com o valor que foi para a ST;
  • bonificação (CFOP x.910) e remessa por conta e ordem (x.923) com C197 → retira o crédito;
  • sem XML e sem desconto no C100, mas com C197 → só "Verificar" (não altera).
E110 campo 07 refeito (11, 13 e 14 recalculados; obrigação 000 do E116 ajustada). Gera arquivo NOVO; o original nunca
é alterado.
"""
import os
import re
import json
import unicodedata
from decimal import Decimal

import difal_ro as dr
import desconto_xml as dx

COD_AJ = 'RO10000036'
MUN_GM = '1100106'                     # Guajará-Mirim (IBGE)
DESCR = 'Crédito Presumido Guajará-Mirim'
OBS_TXT = 'CRÉDITO PRESUMIDO GUAJARÁ-MIRIM'
CANC = {'02', '03', '04', '05'}
TOL = 0.01


def _norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().upper()
    return re.sub(r'\s+', ' ', s).strip()


def _ch(s):
    return re.sub(r'\D', '', s or '')


def _sel(d):
    return _ch(d.get('chave')) or f"{d.get('num', '')}|{d.get('serie', '')}|{d.get('part', '')}"


def _cod_mun(linhas):
    for l in linhas[:3]:
        if l.startswith('|0000|'):
            c = l.split('|')
            return c[11] if len(c) > 11 else ''
    return ''


def _aliq(valor, base):
    if base <= 0:
        return 0.0
    a = round(valor / base * 100, 2)
    for p in (4.0, 7.0, 12.0, 17.0, 19.5):
        if abs(a - p) <= 0.15:
            return p
    return a


def _venda_ref(x):
    m = re.search(r'NOTA\s+DE\s+VENDA\s*(?:N[RO]?\.?|Nº|NUM\w*)?\s*[:.]?\s*0*(\d+)', _norm(x.get('infcpl') or ''))
    return m.group(1) if m else ''


def _usa_alc(linhas):
    return _cod_mun(linhas) == MUN_GM or any(l.startswith(f'|C197|{COD_AJ}|') for l in linhas)


def analisar_texto(texto, xmls=None):
    xmls = xmls or {}
    linhas, _, _ = dr.dividir(texto)
    if not _usa_alc(linhas):
        return {'docs': [], 'resumo': {'aplica': False, 'notas': 0}, 'aplica': False}
    cab, part, obs460, docs, e110, _ = dr._estrutura(linhas)
    nums = {d['num'].lstrip('0'): d for d in docs if d['oper'] == '0'}
    out = []
    for d in docs:
        if d['oper'] != '0' or d['emit'] != '1' or d['mod'] != '55' or d['sit'] in CANC:
            continue
        cfops = {c['cfop'] for c in d['c190']} | {c['cfop'] for c in d['c170']}
        if not any(c.startswith('2') for c in cfops):
            continue                                      # só entrada interestadual
        lanc = [y for y in d['c197'] if y['cod'] == COD_AJ]
        lancado = round(sum(y['icms'] for y in lanc), 2)
        c100 = linhas[d['i']].split('|')
        abat = dr._n(c100[15]) if len(c100) > 15 else 0.0
        x = xmls.get(_ch(d['chave']))
        if x and (x.get('tipo') not in (None, 'nfe') or 'erro' in x):
            x = None
        eh_st = lambda cst, cfop: cst[-2:] in ('10', '30', '60', '70') or cfop[1:] in ('401', '403')
        st = any(eh_st(c['cst'], c['cfop']) for c in d['c190'])
        so_st = bool(d['c190']) and all(eh_st(c['cst'], c['cfop']) for c in d['c190'])
        motivo, ref, credito_st, st_verificar = '', '', 0.0, False
        if x:
            itens = x.get('itens') or []
            orig = {(it.get('cfop') or '')[1:] for it in itens}
            if orig and orig <= {'923'}:
                motivo = 'remessa'
                ref = _venda_ref(x)
            elif orig and orig <= {'910'}:
                motivo = 'bonificacao'
            ok = [it for it in itens if (it.get('cfop') or '')[1:] not in ('910', '923') and (it.get('vdeson') or 0) > 0]
            if st and ok:
                # item do XML × item do SPED: o CST/CFOP de ST está no C170 (o XML do fornecedor traz CST 40)
                c170s = []
                for c in d['c170']:
                    cc = linhas[c['i']].split('|')
                    c170s.append({'i': c['i'], 'num': c['num'], 'vl_item': dr._n(cc[7]), 'st': eh_st(c['cst'], c['cfop'])})
                if so_st:
                    fora = ok
                else:
                    par = dx._casar(c170s, itens)
                    st_ids = {id(par[c['i']]) for c in c170s if c['st'] and c['i'] in par}
                    if any(c['st'] and c['i'] not in par for c in c170s):
                        st_verificar = True          # item de ST sem par no XML: não dá para separar com segurança
                    fora = [it for it in ok if id(it) in st_ids]
                credito_st = round(sum(it['vdeson'] for it in fora), 2)
                ok = [it for it in ok if all(it is not z for z in fora)]
            certo = 0.0 if motivo else round(sum(it['vdeson'] for it in ok), 2)
            base = 0.0 if motivo else round(sum((it['vprod'] - (it.get('vdesc') or 0)) for it in ok), 2)
            fonte = 'XML'
        else:
            if cfops and cfops <= {'2910', '1910'}:
                motivo = 'bonificacao'
            elif cfops and cfops <= {'2923', '1923'}:
                motivo = 'remessa'
            certo = 0.0 if motivo else round(abat, 2)
            if st and not motivo:
                if so_st:
                    credito_st, certo = certo, 0.0
                elif certo:
                    st_verificar = True              # sem XML não dá para separar o desconto dos itens com ST
            base = 0.0
            if certo > 0:
                base = lanc[0]['bc'] if lanc and lanc[0]['bc'] > 0 else round(sum(c['vl_opr'] for c in d['c190'] if c['cfop'][1:] not in ('910', '923')), 2)
            fonte = 'C100 (sem XML)'
        aliq = _aliq(certo, base) if certo > 0 else 0.0
        if certo > 0 and not x and aliq not in (4.0, 7.0, 12.0):
            # sem XML: a base do C197 é a "usada para aplicar o desconto" (IN de RO) → alíquota interestadual mais
            # próxima e base = desconto ÷ alíquota (ex.: nota com "DESCONTO ICMS 7% 1.340,27")
            aliq = min((4.0, 7.0, 12.0), key=lambda p: abs(p - certo / base * 100)) if base > 0 else 7.0
            base = round(certo * 100 / aliq, 2)
        if (not x and not motivo and certo == 0 and lancado > 0 and not so_st) or (st_verificar and abs(certo - lancado) > TOL):
            status = 'verificar'
        elif abs(certo - lancado) <= TOL:
            status = 'confere'
        elif certo == 0:
            status = 'retirar'
        elif lancado == 0:
            status = 'falta'
        else:
            status = 'diferente'
        if status == 'confere' and lanc and len(lanc) == 1 and certo > 0 and (abs(lanc[0]['bc'] - base) > 0.02 or abs(lanc[0]['aliq'] - aliq) > 0.005) and x:
            status = 'base'                                 # valor certo, base/alíquota diferentes do XML
        p = part.get(d['part'], {})
        out.append({'id': d['i'], 'sel': _sel(d), 'num': d['num'], 'serie': d['serie'], 'data': d['dt'], 'chave': d['chave'],
                    'fornecedor': p.get('nome', d['part']), 'fonte': fonte, 'motivo': motivo, 'venda_ref': ref,
                    'venda_no_sped': bool(ref and ref in nums), 'st': st, 'lancado': lancado, 'certo': certo, 'base': base,
                    'aliq': aliq, 'status': status, 'dif': round(certo - lancado, 2), 'nat_op': (x or {}).get('nat_op', ''),
                    'credito_st': credito_st, 'so_st': so_st, 'st_verificar': st_verificar})
    corr = [z for z in out if z['status'] in ('diferente', 'falta', 'retirar', 'base')]
    resumo = {'aplica': True, 'notas': len(out), 'confere': sum(1 for z in out if z['status'] == 'confere'),
              'corrigir': len(corr), 'verificar': sum(1 for z in out if z['status'] == 'verificar'),
              'delta': round(sum(z['dif'] for z in corr), 2), 'sem_xml': sum(1 for z in out if z['fonte'] != 'XML'),
              'credito_st': round(sum(z['credito_st'] for z in out), 2), 'notas_st': sum(1 for z in out if z['credito_st'] > 0)}
    return {'docs': out, 'resumo': resumo, 'aplica': True, 'tem_e110': bool(e110)}


def descricao(z):
    """Texto curto da linha para o painel."""
    fm = lambda v: f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    if z['status'] == 'verificar' and z.get('st_verificar'):
        return (f"nota com itens de ST e itens normais sem XML (ou item de ST que não casou com o XML): não dá para separar o crédito da ST · "
                f"C197 hoje R$ {fm(z['lancado'])} · NÃO ALTERADO: confira")
    if z['status'] == 'verificar':
        return f"C197 de R$ {fm(z['lancado'])}, mas a nota não tem desconto do ICMS no C100 e não há XML · NÃO ALTERADO: confira o XML"
    if z['motivo'] == 'remessa':
        r = f" da NF de venda {z['venda_ref']}" if z['venda_ref'] else ''
        return (f"remessa por conta e ordem{r}: o crédito fica só na nota de venda (Nota 2) · retirar R$ {fm(z['lancado'])}"
                + ('' if not z['venda_ref'] or z['venda_no_sped'] else ' · a nota de venda não está neste SPED'))
    if z['motivo'] == 'bonificacao':
        return f"bonificação não tem crédito presumido · retirar R$ {fm(z['lancado'])}"
    st = (f" · itens com ST fora do C197 (R$ {fm(z['credito_st'])} usados no cálculo do ICMS-ST)" if z.get('credito_st') else '')
    if z['status'] == 'falta':
        return f"desconto do ICMS na nota sem C197 · incluir {fm(z['aliq'])}% sobre R$ {fm(z['base'])} = R$ {fm(z['certo'])}{st}"
    if z['status'] == 'base':
        return f"valor confere; base/alíquota pelo XML: {fm(z['aliq'])}% sobre R$ {fm(z['base'])}"
    if z['status'] == 'retirar':
        return f"o XML não tem desconto do ICMS (Nota 3) · retirar R$ {fm(z['lancado'])}"
    return f"lançado R$ {fm(z['lancado'])} → desconto do {z['fonte']} R$ {fm(z['certo'])}{st}"


def aplicar_texto(texto, xmls, selecao):
    """selecao = {'docs': [id, ...], 'e116': {...}} -> (texto_novo, resumo)"""
    linhas, quebra, final_vazio = dr.dividir(texto)
    an = analisar_texto(texto, xmls)
    por_id = {z['id']: z for z in an['docs']}
    cab, part, obs460, docs, e110, _ = dr._estrutura(linhas)
    docs_i = {d['i']: d for d in docs}
    n197 = dr.campos_c197(linhas, cab)
    quer = set(selecao.get('docs') or [])
    esc = [por_id[i] for i in quer if i in por_id and por_id[i]['status'] in ('diferente', 'falta', 'retirar', 'base')]
    resumo = {'notas': 0, 'incluidas': 0, 'retiradas': 0, 'acertadas': 0, 'credito_antes': 0.0, 'credito_depois': 0.0,
              'e110_antes': None, 'e110_depois': None, 'e116': '', 'avisos': [], 'detalhe': [], 'obs_0460_criados': []}
    if not esc:
        return texto, {**resumo, 'erro': 'Nenhuma nota marcada para corrigir.'}
    cod_obs = next((k for k, t in obs460.items() if 'GUAJAR' in _norm(t) and 'PRESUMID' in _norm(t)), None)
    novos_0460 = []
    if not cod_obs and any(z['status'] == 'falta' for z in esc):
        usados = set(obs460)
        n = 1
        while str(n) in usados:
            n += 1
        cod_obs = str(n)
        novos_0460.append(f'|0460|{cod_obs}|Crédito Presumido GUAJARÁ-MIRIM|')
        resumo['obs_0460_criados'].append(cod_obs)
    insercoes, remover = {}, set()
    d07 = Decimal('0')
    fq = lambda v: dr._f(v)
    for z in esc:
        d = docs_i.get(z['id'])
        if not d:
            continue
        lanc = [y for y in d['c197'] if y['cod'] == COD_AJ]
        velho = Decimal(str(z['lancado']))
        novo = Decimal(str(z['certo']))
        if novo > 0 and lanc:
            c = linhas[lanc[0]['i']].split('|')
            c[5], c[6], c[7] = fq(z['base']), fq(z['aliq']), fq(z['certo'])
            linhas[lanc[0]['i']] = '|'.join(c)
            for y in lanc[1:]:
                remover.add(y['i'])
            resumo['acertadas'] += 1
        elif novo > 0:
            alvo = None
            for k, c195 in enumerate(d['c195']):
                if c195['cod_obs'] == cod_obs:
                    alvo = c195['i']
            linha = dr.linha_c197(COD_AJ, DESCR, z['base'], z['aliq'], z['certo'], 0, n197)
            if alvo is not None:
                insercoes.setdefault(alvo, []).append(linha)
            else:
                insercoes.setdefault(d['fim'], []).extend([f'|C195|{cod_obs}|{OBS_TXT}|', linha])
            resumo['incluidas'] += 1
        else:
            for y in lanc:
                remover.add(y['i'])
            for k, c195 in enumerate(d['c195']):     # C195 que ficou sem filho sai junto
                prox = d['c195'][k + 1]['i'] if k + 1 < len(d['c195']) else d['fim'] + 1
                filhos = [y for y in d['c197'] if c195['i'] < y['i'] < prox]
                if filhos and all(y['i'] in remover for y in filhos):
                    remover.add(c195['i'])
            resumo['retiradas'] += 1
        d07 += novo - velho
        resumo['notas'] += 1
        resumo['credito_antes'] += float(velho)
        resumo['credito_depois'] += float(novo)
        resumo['detalhe'].append({'num': z['num'], 'fornecedor': z['fornecedor'], 'antes': float(velho), 'depois': float(novo),
                                  'motivo': z['motivo'] or z['status']})
    deltas = {7: float(d07)} if abs(d07) >= Decimal('0.005') else {}
    novas_e116, erro = dr.aplica_apuracao(linhas, e110, deltas, selecao, cab, remover, resumo)
    if erro:
        return texto, {**resumo, 'erro': erro}
    novo_txt = dr.monta_arquivo(linhas, remover, insercoes, novos_0460, [], novas_e116, quebra, final_vazio)
    resumo['credito_antes'] = round(resumo['credito_antes'], 2)
    resumo['credito_depois'] = round(resumo['credito_depois'], 2)
    resumo['delta_07'] = round(float(d07), 2)
    return novo_txt, resumo


def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    sped, js = opt('--sped'), opt('--json')
    if not sped or not js:
        print('uso: credito-alcgm --sped ARQ.txt --json saida.json [--xmls PASTA|ZIP] [--aplicar sel.json --saida novo.txt]')
        return 1
    try:
        texto, enc = dr._ler(sped)
        xmls = {}
        if opt('--xmls'):
            from xml_entradas import ler_xmls
            xmls = ler_xmls([opt('--xmls')])[0]
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
    except Exception as e:  # pragma: no cover
        res = {'erro': f'Falha ao processar: {e}'}
    tmp = js + '.parcial'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False)
    os.replace(tmp, js)
    return 0

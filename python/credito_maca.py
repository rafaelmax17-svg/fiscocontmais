# -*- coding: utf-8 -*-
"""Corretor do SPED Fiscal (Admin) — Crédito presumido de maçã e pera recebidas de outra UF com isenção (RO).

Base legal (RICMS/RO, Decreto 22.721/2018, anexos consolidados enviados pelo Rafael):
  • Anexo IV, Parte 2, item 19: crédito presumido "equivalente ao percentual da alíquota interestadual do imposto
    aplicado sobre o valor da operação do produto hortifrutigranjeiro constante no item 15 da Parte 2 do Anexo I, que
    esteja indicado com isenção do ICMS e não isento neste Estado" (Convênio ICM 44/75, cláusula primeira, § 2º).
  • Anexo I, Parte 2, item 15, Nota 4: assegura o crédito a quem recebe de outra UF pera e maçã (item 5 da Tabela 1
    da Parte 4) com indicação de isenção na operação interestadual (Convênio ICMS 94/05, cláusula segunda).
  • Anexo I, Parte 4, Tabela 1, item 5: frutas frescas isentas em RO, EXCETO pera e maçã.
  • Guia Prático da EFD ICMS/IPI: C197 com 3º caractere 0, 1 ou 2 soma no campo 07 (VL_AJ_CREDITOS) do E110.
Código de ajuste RO10000038 (Tabela 5.3 de RO: "Crédito Presumido - Item 19 - Parte 2 - Anexo IV - Valor a crédito").

Regra aplicada: entrada (C100 IND_OPER 0) de outra UF, CFOP 2.xxx, item com NCM 0808.10.00 (maçã) ou 0808.30.00
(pera) e CST ICMS x40. Crédito = (VL_ITEM − VL_DESC) × alíquota interestadual da origem: 7% para Sul e Sudeste, exceto
ES; 12% para as demais UFs. Mercadoria de origem estrangeira (CST 1xx, 2xx, 3xx, 8xx) fica "Verificar", sem cálculo.

Ao aplicar (só as notas marcadas): 0460 "Cred Presumido Maçãs - Interestadual" (código 99, ou o próximo livre),
C195 com essa observação e um C197 RO10000038 por nota e alíquota; o C197 RO10000038 que já existir na nota é
substituído. E110 campo 07 recalculado (11, 13 e 14) e obrigação 000 do E116 ajustada. Gera arquivo NOVO.
"""
import os
import json
from decimal import Decimal

import difal_ro as dr

COD_AJ = 'RO10000038'
NCM_FRUTA = {'08081000': 'maçã', '08083000': 'pera'}
UF_7 = {'SP', 'RJ', 'MG', 'PR', 'SC', 'RS'}
ORIG_ESTRANG = {'1', '2', '3', '8'}
OBS_COD = '99'


def aliq_inter(uf):
    return 7.0 if uf in UF_7 else 12.0


def _texto_obs(tem_pera, tem_maca=True):
    if tem_pera and tem_maca:
        return 'Cred Presumido Maçãs e Peras - Interestadual'
    if tem_pera:
        return 'Cred Presumido Peras - Interestadual'
    return 'Cred Presumido Maçãs - Interestadual'


def _ncm_0200(linhas):
    out = {}
    for l in linhas:
        if l.startswith('|0200|'):
            c = l.split('|')
            if len(c) > 8:
                out[c[2]] = c[8]
    return out


def _uf_doc(d, part):
    ch = d.get('chave') or ''
    if len(ch) == 44:
        return dr.UF_IBGE.get(ch[:2], '')
    p = part.get(d.get('part'), {})
    return dr.UF_IBGE.get((p.get('mun') or '')[:2], '')


def analisar_texto(texto):
    linhas, _, _ = dr.dividir(texto)
    cab, part, obs460, docs, e110, _ = dr._estrutura(linhas)
    ncm = _ncm_0200(linhas)
    uf_emp = cab.get('uf') or 'RO'
    out = []
    for d in docs:
        if d['oper'] != '0' or d['sit'] in ('02', '03', '04', '05'):
            continue
        uf = _uf_doc(d, part)
        itens = []
        for x in d['c170']:
            n = ncm.get(x['item'], '')
            fruta = NCM_FRUTA.get(n)
            if not fruta or not x['cst'].endswith('40') or not x['cfop'].startswith('2'):
                continue
            orig = x['cst'][:1] if len(x['cst']) == 3 else '0'
            it = {'num': x['num'], 'cod': x['item'], 'desc': x['descr'], 'ncm': n, 'fruta': fruta, 'cst': x['cst'],
                  'cfop': x['cfop'], 'valor': round(x['vl'], 2)}
            if orig in ORIG_ESTRANG:
                it.update(aliq=None, credito=0.0, verificar=f'origem {orig} (estrangeira): confira a isenção na origem')
            elif not uf or uf == uf_emp:
                it.update(aliq=None, credito=0.0, verificar='UF do fornecedor não identificada' if not uf else 'fornecedor do próprio estado')
            else:
                a = aliq_inter(uf)
                it.update(aliq=a, credito=float(dr._d(Decimal(str(x['vl'])) * Decimal(str(a)) / 100)), verificar='')
            itens.append(it)
        if not itens:
            continue
        grupos = {}
        for it in itens:
            if it['aliq'] is None:
                continue
            g = grupos.setdefault(it['aliq'], {'aliq': it['aliq'], 'base': Decimal('0')})
            g['base'] += Decimal(str(it['valor']))
        gl = []
        for a, g in sorted(grupos.items()):
            gl.append({'aliq': a, 'base': float(dr._d(g['base'])), 'credito': float(dr._d(g['base'] * Decimal(str(a)) / 100))})
        calc = round(sum(g['credito'] for g in gl), 2)
        lancado = round(sum(y['icms'] for y in d['c197'] if y['cod'] == COD_AJ), 2)
        verif = [it for it in itens if it['verificar']]
        if not gl:
            status = 'verificar'
        elif lancado == 0:
            status = 'falta'
        elif abs(lancado - calc) <= 0.01:
            status = 'confere'
        else:
            status = 'diferente'
        p = part.get(d['part'], {})
        out.append({'id': d['i'], 'num': d['num'], 'serie': d['serie'], 'data': d['dt'], 'chave': d['chave'], 'uf': uf,
                    'fornecedor': p.get('nome', ''), 'itens': itens, 'grupos': gl, 'credito': calc, 'lancado': lancado,
                    'status': status, 'tem_verificar': bool(verif)})
    resumo = {
        'notas': len(out), 'falta': sum(1 for x in out if x['status'] == 'falta'),
        'confere': sum(1 for x in out if x['status'] == 'confere'), 'diferente': sum(1 for x in out if x['status'] == 'diferente'),
        'verificar': sum(1 for x in out if x['status'] == 'verificar' or x['tem_verificar']),
        'a_incluir': round(sum(x['credito'] - x['lancado'] for x in out if x['status'] in ('falta', 'diferente')), 2),
        'tem_pera': any(it['fruta'] == 'pera' for x in out for it in x['itens']),
        'obs_existente': {k: v for k, v in obs460.items() if k == OBS_COD},
    }
    return {'docs': out, 'resumo': resumo, 'empresa': cab.get('nome', ''), 'periodo': f"{cab.get('dt_ini', '')}-{cab.get('dt_fin', '')}",
            'tem_e110': bool(e110)}


def aplicar_texto(texto, selecao):
    """selecao = {'docs': [id, ...], 'e116': {'cod_rec', 'venc'}} -> (texto_novo, resumo)"""
    linhas, quebra, final_vazio = dr.dividir(texto)
    an = analisar_texto(texto)
    por_id = {d['id']: d for d in an['docs']}
    cab, part, obs460, docs, e110, _ = dr._estrutura(linhas)
    docs_por_i = {d['i']: d for d in docs}
    n197 = dr.campos_c197(linhas, cab)
    escolhidos = [por_id[i] for i in (selecao.get('docs') or []) if i in por_id and por_id[i]['grupos']]
    resumo = {'notas': 0, 'c195_inseridos': 0, 'c197_inseridos': 0, 'c197_removidos': 0, 'credito': 0.0, 'credito_antes': 0.0,
              'obs_0460_criados': [], 'cod_obs': '', 'e110_antes': None, 'e110_depois': None, 'e116': '', 'avisos': [], 'detalhe': []}
    if not escolhidos:
        return texto, {**resumo, 'erro': 'Nenhuma nota marcada com crédito a lançar.'}
    tem_pera = any(it['fruta'] == 'pera' for a in escolhidos for it in a['itens'] if it['aliq'] is not None)
    tem_maca = any(it['fruta'] == 'maçã' for a in escolhidos for it in a['itens'] if it['aliq'] is not None)
    texto_obs = _texto_obs(tem_pera, tem_maca)
    cod_obs = next((k for k, t in obs460.items() if (t or '').strip().upper() == texto_obs.upper()), None)
    novos_0460 = []
    if not cod_obs:
        cod_obs = OBS_COD
        if cod_obs in obs460:
            n = 1
            while f'{OBS_COD}{n}' in obs460:
                n += 1
            cod_obs = f'{OBS_COD}{n}'
            resumo['avisos'].append(f'O código 99 do 0460 já é usado por "{obs460[OBS_COD]}". A observação foi criada com o código {cod_obs}.')
        novos_0460.append(f'|0460|{cod_obs}|{texto_obs}|')
        resumo['obs_0460_criados'].append(cod_obs)
    resumo['cod_obs'] = cod_obs
    insercoes, remover = {}, set()
    d07 = Decimal('0')
    for a in escolhidos:
        d = docs_por_i.get(a['id'])
        if not d:
            continue
        antigos = [y for y in d['c197'] if y['cod'] == COD_AJ]
        velho = Decimal(str(sum(y['icms'] for y in antigos)))
        for y in antigos:
            remover.add(y['i'])
            resumo['c197_removidos'] += 1
        for k, c195 in enumerate(d['c195']):        # C195 que ficou sem filho sai junto
            prox = d['c195'][k + 1]['i'] if k + 1 < len(d['c195']) else d['fim'] + 1
            filhos = [y for y in d['c197'] if c195['i'] < y['i'] < prox]
            if filhos and all(y['i'] in remover for y in filhos):
                remover.add(c195['i'])
        frutas = {it['fruta'] for it in a['itens'] if it['aliq'] is not None}
        descr = ('Cred Presumido Maçãs e Peras' if len(frutas) > 1 else
                 ('Cred Presumido Peras' if 'pera' in frutas else 'Cred Presumido Maçãs'))
        bloco = [f'|C195|{cod_obs}||']
        novo = Decimal('0')
        for g in a['grupos']:
            bloco.append(dr.linha_c197(COD_AJ, descr, g['base'], g['aliq'], g['credito'], None, n197))
            novo += Decimal(str(g['credito']))
            resumo['c197_inseridos'] += 1
        insercoes.setdefault(d['fim'], []).extend(bloco)
        resumo['c195_inseridos'] += 1
        resumo['notas'] += 1
        resumo['credito'] += float(novo)
        resumo['credito_antes'] += float(velho)
        d07 += novo - velho
        resumo['detalhe'].append({'num': a['num'], 'fornecedor': a['fornecedor'], 'credito': float(novo), 'antes': float(velho)})
    deltas = {7: float(d07)} if abs(d07) >= Decimal('0.005') else {}
    novas_e116, erro = dr.aplica_apuracao(linhas, e110, deltas, selecao, cab, remover, resumo)
    if erro:
        return texto, {**resumo, 'erro': erro}
    novo_txt = dr.monta_arquivo(linhas, remover, insercoes, novos_0460, [], novas_e116, quebra, final_vazio)
    resumo['credito'] = round(resumo['credito'], 2)
    resumo['credito_antes'] = round(resumo['credito_antes'], 2)
    resumo['delta_07'] = float(d07)
    return novo_txt, resumo


def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    sped, js = opt('--sped'), opt('--json')
    if not sped or not js:
        print('uso: credito-maca --sped ARQ.txt --json saida.json [--aplicar selecao.json --saida novo.txt]')
        return 1
    try:
        texto, enc = dr._ler(sped)
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
        import traceback
        traceback.print_exc()
        res = {'erro': f'Falha ao processar: {e}'}
    tmp = js + '.parcial'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False)
    os.replace(tmp, js)
    return 0

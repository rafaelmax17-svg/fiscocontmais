# -*- coding: utf-8 -*-
"""Crédito de ICMS de fornecedor do Simples Nacional no SPED Fiscal de Rondônia (Corretor do SPED, só Admin).
Gera arquivo NOVO; o original nunca é alterado.

Como RO manda escriturar (SEFIN/RO, IN 017/2016/GAB/CRE — Tabela 5.3 e manual da EFD, item 19):
  • C100/C170/C190 da nota do fornecedor optante pelo Simples: SEM o valor do ICMS.
  • Um C195 (observação do 0460) + um C197 por documento, código RO00000001
    ("Crédito de ICMS pela aquisição de mercadoria de ME/EPP optante pelo Simples Nacional — LC 123/2006, art. 23, §§ 1º a 5º"):
    VL_BC_ICMS = base da operação, ALIQ_ICMS = percentual do Simples informado na nota, VL_ICMS = crédito;
    COD_ITEM e VL_OUTROS em branco.
  • A soma desses C197 entra no campo 07 (VL_AJ_CREDITOS) do E110.

O percentual e o valor do crédito vêm do XML da nota (grupo ICMSSN101/201/900: pCredSN e vCredICMSSN).
"""
import os
import re
import sys
import json
from decimal import Decimal

import difal_ro as dr

COD_SN = 'RO00000001'
OBS_SN = ('CSN', 'CRÉDITO SIMPLES NACIONAL')
CANC = {'02', '03', '04', '05'}

# Final do CFOP de entrada SEM direito ao crédito do Simples. O crédito da LC 123/2006, art. 23, § 1º, só vale para
# mercadoria destinada à comercialização ou industrialização; uso e consumo também não dá crédito de ICMS até 2033
# (LC 87/1996, art. 33, I) e o ativo imobilizado não é comercialização nem industrialização.
CFOP_SEM_CREDITO = {
    '556': 'material de uso e consumo', '407': 'material de uso e consumo (com ST)',
    '653': 'combustível ou lubrificante para consumo próprio',
    '551': 'ativo imobilizado', '406': 'ativo imobilizado (com ST)',
    '128': 'uso na prestação de serviço sujeito ao ISS',
}
BASE_LEGAL_CFOP = ('O crédito do Simples só vale para mercadoria destinada à comercialização ou industrialização '
                   '(LC 123/2006, art. 23, § 1º); uso e consumo não dá crédito de ICMS até 2033 (LC 87/1996, art. 33, I).')


def _credito_por_cfop(d, x):
    """Crédito do XML só dos itens cujo CFOP de entrada (no SPED) dá direito.
    Retorna (credito, base, cfops_sem_direito, como): como = 'todos' | 'nenhum' | 'itens' | 'proporcao'."""
    sem = sorted({c['cfop'] for c in d['c190'] if c['cfop'][1:] in CFOP_SEM_CREDITO})
    if not sem:
        return x['credito'], x['base'], [], 'todos'
    com = [c for c in d['c190'] if c['cfop'][1:] not in CFOP_SEM_CREDITO]
    if not com:
        return 0.0, 0.0, sem, 'nenhum'
    itx = [it for it in x.get('itens', []) if it.get('csosn')]
    c170 = {c['num']: c['cfop'] for c in d['c170']}
    if c170 and len(c170) == len(x.get('itens', [])) and all(str(it['n']).lstrip('0') in c170 for it in itx):
        ok = [it for it in itx if c170[str(it['n']).lstrip('0')][1:] not in CFOP_SEM_CREDITO]
        cred = sum(it['vcredsn'] for it in ok)
        base = sum(it['valor_merc'] for it in ok if it['csosn'] in ('101', '201') or it['vcredsn'] > 0)
        return round(cred, 2), round(base, 2), sem, 'itens'
    tot = sum(c['vl_opr'] for c in d['c190']) or 1.0
    f = sum(c['vl_opr'] for c in com) / tot
    return round(x['credito'] * f, 2), round(x['base'] * f, 2), sem, 'proporcao'


# ------------------------------------------------------------------ XML (leitura compartilhada com o DIFAL)
from xml_entradas import ler_xml, ler_xmls  # noqa: E402,F401


# ------------------------------------------------------------------ análise
def _obs_simples(obs460):
    return next((k for k, t in obs460.items() if 'SIMPLES' in (t or '').upper()), None)


def analisar_texto(texto, xmls, n_lidos=0):
    linhas, _, _ = dr.dividir(texto)
    cab, part, obs460, docs, e110, _ = dr._estrutura(linhas)
    uf_emp = (cab.get('uf') or '').strip()
    avisos = []
    if uf_emp != 'RO':
        avisos.append(f'Este SPED é de {uf_emp or "UF não informada"}: o código RO00000001 e o modo de escriturar são os de Rondônia.')
    saida = []
    entradas = sem_xml = 0
    for d in docs:
        if d['oper'] != '0' or d['emit'] != '1' or d['mod'] not in ('55', '65'):
            continue
        entradas += 1
        x = xmls.get(re.sub(r'\D', '', d['chave'] or ''))
        c197 = [y for y in d['c197'] if y['cod'] == COD_SN]
        c197_v = float(dr._d(sum(y['icms'] for y in c197)))
        if not x:
            sem_xml += 1
            if c197:
                p = part.get(d['part'], {})
                saida.append(_linha(d, p, part, None, 0.0, c197, c197_v, 'sem_xml',
                                    ['Nota sem XML importado: o C197 já lançado não pôde ser conferido.']))
            continue
        if not x.get('simples'):
            continue
        p = part.get(d['part'], {})
        c190_icms = float(dr._d(sum(y['vl_icms'] for y in d['c190'])))
        obs = []
        if d['sit'] in CANC:
            continue
        perm, base_ok, cfop_sem, como = _credito_por_cfop(d, x)
        if como == 'nenhum':
            tipos = ', '.join(f'{c} ({CFOP_SEM_CREDITO[c[1:]]})' for c in cfop_sem)
            obs.append(f'CFOP {tipos}: sem direito ao crédito do Simples. {BASE_LEGAL_CFOP}')
            st = 'sem_direito' if (c190_icms > 0.004 or c197_v > 0.004) else 'uso_consumo'
            r = _linha(d, p, part, x, c190_icms, c197, c197_v, st, obs)
            r.update({'csosn': ', '.join(x['csosn']), 'base': x['base'], 'aliq': 0.0, 'credito': 0.0, 'aliq_fonte': 'cfop'})
            saida.append(r)
            continue
        if como in ('itens', 'proporcao'):
            obs.append(f'Parte da nota é {", ".join(CFOP_SEM_CREDITO[c[1:]] for c in cfop_sem)} (CFOP {", ".join(cfop_sem)}): '
                       f'o crédito considera só os itens para comercialização ou industrialização'
                       f'{"" if como == "itens" else ", na proporção do valor da operação no C190"}. {BASE_LEGAL_CFOP}')
        x = {**x, 'credito': perm, 'base': base_ok}
        aliq = x['aliqs'][0] if len(x['aliqs']) == 1 else (round(perm / x['base'] * 100, 2) if x['base'] and perm else 0.0)
        if len(x['aliqs']) > 1:
            obs.append(f'A nota tem mais de um percentual de crédito ({", ".join(str(a).replace(".", ",") for a in x["aliqs"])}%); '
                       'usado o percentual médio, que dá o mesmo crédito total.')
        if x['credito_previsto'] and perm <= 0:
            status = 'sem_aliq'
            obs.append('CSOSN com direito a crédito, mas o fornecedor não informou o percentual na nota. Informe a alíquota do Anexo dele.')
        elif c190_icms > 0.004 and perm > 0:
            status = 'lugar_errado'
        elif perm <= 0 and (c190_icms > 0.004 or c197_v > 0.004):
            status = 'sem_direito'
        elif perm > 0 and c197_v <= 0.004:
            status = 'incluir'
        elif perm > 0 and abs(c197_v - perm) > 0.01:
            status = 'divergente'
        else:
            status = 'ok'
        if x['base'] and perm and abs(x['base'] * aliq / 100 - perm) > 0.05:
            obs.append(f'O crédito informado na nota (R$ {dr._f(perm)}) não bate com base × percentual '
                       f'(R$ {dr._f(x["base"] * aliq / 100)}). Vale o valor da nota; confira.')
        r = _linha(d, p, part, x, c190_icms, c197, c197_v, status, obs)
        r.update({'csosn': ', '.join(x['csosn']), 'base': x['base'], 'aliq': aliq, 'credito': perm,
                  'aliq_fonte': 'xml' if perm > 0 else ''})
        saida.append(r)
    apur = None
    if e110:
        c = e110['c']
        apur = {k: dr._n(c[i]) for i, k in enumerate(['deb', 'aj_deb', 'tot_aj_deb', 'est_cred', 'cred', 'aj_cred', 'tot_aj_cred',
                                                       'est_deb', 'sld_ant', 'sld_apurado', 'ded', 'recolher', 'sld_transp', 'deb_esp'], start=2)}
    e116 = [{'cod': c[2], 'valor': dr._n(c[3]), 'venc': c[4], 'cod_rec': c[5]}
            for c in (ln.split('|') for ln in linhas if ln.startswith('|E116|')) if len(c) > 5]
    cont = {k: sum(1 for x in saida if x['status'] == k) for k in ('incluir', 'lugar_errado', 'sem_direito', 'divergente', 'ok', 'sem_aliq', 'sem_xml', 'uso_consumo')}
    soma = lambda st, campo: float(dr._d(sum(x[campo] for x in saida if x['status'] in st)))
    return {
        'empresa': {'nome': cab.get('nome', ''), 'cnpj': cab.get('cnpj', ''), 'uf': uf_emp, 'dt_ini': cab.get('dt_ini', ''),
                    'dt_fin': cab.get('dt_fin', ''), 'cod_ver': cab.get('cod_ver', '')},
        'docs': saida, 'avisos': avisos, 'e110': apur, 'e116': e116,
        'obs_existente': _obs_simples(obs460),
        'resumo': {
            'xml_lidos': n_lidos, 'entradas': entradas, 'entradas_sem_xml': sem_xml,
            'notas_simples': sum(1 for x in saida if x['status'] != 'sem_xml'),
            **cont,
            'credito_incluir': soma(('incluir',), 'credito'),
            'credito_c190': soma(('lugar_errado', 'sem_direito'), 'c190_icms'),
            'credito_permitido': soma(('incluir', 'lugar_errado', 'divergente', 'ok'), 'credito'),
            'divergencia': float(dr._d(sum(x['credito'] - x['c197'] for x in saida if x['status'] == 'divergente'))),
        },
    }


def _linha(d, p, part, x, c190_icms, c197, c197_v, status, obs):
    uf, _ = dr._uf_emitente(d, part)
    return {
        'id': d['i'], 'num': d['num'], 'serie': d['serie'], 'data': d['dt'], 'chave': d['chave'],
        'fornecedor': p.get('nome') or (x or {}).get('emit_nome') or d['part'], 'cnpj': p.get('cnpj', ''), 'uf': uf,
        'csosn': '', 'base': 0.0, 'aliq': 0.0, 'credito': 0.0, 'aliq_fonte': '',
        'c190_icms': c190_icms, 'c197': c197_v,
        'c197_aliq': c197[0]['aliq'] if c197 else 0.0,
        'status': status, 'obs': obs,
        'sug_zerar': c190_icms > 0.004 and status in ('lugar_errado', 'sem_direito'),
        'sug_c197': status in ('incluir', 'lugar_errado', 'divergente') or (status == 'sem_direito' and c197_v > 0.004),
    }


# ------------------------------------------------------------------ aplicação
def aplicar_texto(texto, xmls, selecao):
    """selecao = {'docs': [{'id', 'zerar': bool, 'c197': bool, 'aliq': float|None}], 'e116': {...}}"""
    linhas, quebra, final_vazio = dr.dividir(texto)
    an = analisar_texto(texto, xmls)
    por_id = {d['id']: d for d in an['docs']}
    cab, part, obs460, docs, e110, _ = dr._estrutura(linhas)
    docs_por_i = {d['i']: d for d in docs}
    n197 = dr.campos_c197(linhas, cab)
    resumo = {'notas': 0, 'zeradas': 0, 'c170_zerados': 0, 'c190_zerados': 0, 'credito_retirado_c190': 0.0,
              'c197_inseridos': 0, 'c197_removidos': 0, 'c195_inseridos': 0, 'credito_c197': 0.0, 'credito_c197_antes': 0.0,
              'obs_0460_criados': [], 'e110_antes': None, 'e110_depois': None, 'e116': '', 'avisos': [], 'detalhe': []}
    insercoes, remover = {}, set()
    d06 = d07 = Decimal('0')
    cod_obs = _obs_simples(obs460)
    novos_0460 = []
    for sel in selecao.get('docs', []):
        a, d = por_id.get(sel.get('id')), docs_por_i.get(sel.get('id'))
        if not a or not d or a['status'] == 'sem_xml':
            continue
        mexeu = False
        if sel.get('zerar'):
            for x in d['c170']:
                c = linhas[x['i']].split('|')
                if len(c) > 15 and dr._n(c[15]) > 0.004:
                    c[13] = c[14] = c[15] = '0,00'
                    linhas[x['i']] = '|'.join(c)
                    resumo['c170_zerados'] += 1
            bc = ic = Decimal('0')
            for x in d['c190']:
                c = linhas[x['i']].split('|')
                if len(c) > 7 and dr._n(c[7]) > 0.004:
                    bc += Decimal(str(dr._n(c[6])))
                    ic += Decimal(str(dr._n(c[7])))
                    c[4], c[6], c[7] = '0,00', '0,00', '0,00'
                    linhas[x['i']] = '|'.join(c)
                    resumo['c190_zerados'] += 1
            dr._junta_c190(linhas, d, remover)
            c = linhas[d['i']].split('|')
            if len(c) > 22:
                c[21] = dr._f(max(Decimal('0'), Decimal(str(dr._n(c[21]))) - bc))
                c[22] = dr._f(max(Decimal('0'), Decimal(str(dr._n(c[22]))) - ic))
                linhas[d['i']] = '|'.join(c)
            if ic > 0:
                resumo['zeradas'] += 1
                mexeu = True
            d06 -= ic
        if sel.get('c197'):
            aliq = sel.get('aliq')
            aliq = float(a['aliq']) if aliq in (None, '') else float(str(aliq).replace(',', '.'))
            if a['credito'] > 0 and abs(aliq - float(a['aliq'])) < 0.0001:
                cred = Decimal(str(a['credito']))
            else:
                cred = dr._d(Decimal(str(a['base'])) * Decimal(str(aliq)) / 100)
            antigos = [y for y in d['c197'] if y['cod'] == COD_SN]
            velho = Decimal(str(sum(y['icms'] for y in antigos)))
            for y in antigos:
                remover.add(y['i'])
                resumo['c197_removidos'] += 1
            for k, c195 in enumerate(d['c195']):
                prox = d['c195'][k + 1]['i'] if k + 1 < len(d['c195']) else d['fim'] + 1
                filhos = [y for y in d['c197'] if c195['i'] < y['i'] < prox]
                if filhos and all(y['i'] in remover for y in filhos):
                    remover.add(c195['i'])
            if cred > 0:
                if not cod_obs:
                    cod_obs = OBS_SN[0]
                    n = 1
                    while cod_obs in obs460:
                        cod_obs, n = f'{OBS_SN[0]}{n}', n + 1
                    obs460[cod_obs] = OBS_SN[1]
                    novos_0460.append(f'|0460|{cod_obs}|{OBS_SN[1]}|')
                    resumo['obs_0460_criados'].append(cod_obs)
                insercoes.setdefault(d['fim'], []).extend([
                    f'|C195|{cod_obs}||',
                    dr.linha_c197(COD_SN, f'CONFORME NF Nº {a["num"]}', a['base'], aliq, cred, None, n197)])
                resumo['c195_inseridos'] += 1
                resumo['c197_inseridos'] += 1
            resumo['credito_c197'] += float(cred)
            resumo['credito_c197_antes'] += float(velho)
            d07 += cred - velho
            mexeu = mexeu or cred != velho or bool(antigos)
        if mexeu:
            resumo['notas'] += 1
            resumo['detalhe'].append({'num': a['num'], 'fornecedor': a['fornecedor']})
    resumo['credito_retirado_c190'] = float(dr._d(-d06))
    deltas = {k: float(v) for k, v in ((6, d06), (7, d07)) if abs(v) >= Decimal('0.005')}
    novas_e116, erro = dr.aplica_apuracao(linhas, e110, deltas, selecao, cab, remover, resumo)
    if erro:
        return texto, {'erro': erro}
    novo = dr.monta_arquivo(linhas, remover, insercoes, novos_0460, [], novas_e116, quebra, final_vazio)
    resumo['credito_c197'] = float(dr._d(resumo['credito_c197']))
    resumo['credito_c197_antes'] = float(dr._d(resumo['credito_c197_antes']))
    resumo['delta_06'], resumo['delta_07'] = float(d06), float(d07)
    return novo, resumo


# ------------------------------------------------------------------ CLI
def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    sped, js, xs = opt('--sped'), opt('--json'), opt('--xmls')
    if not sped or not js:
        print('uso: simples-ro --sped ARQ.txt --xmls "a.zip;b.zip" --json saida.json [--aplicar selecao.json --saida novo.txt]')
        return 1
    try:
        texto, enc = dr._ler(sped)
        caminhos = [c for c in (xs or '').split(os.pathsep) if c]
        xmls, lidos, erros = ler_xmls(caminhos)
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
            res = analisar_texto(texto, xmls, lidos)
            res['resumo']['xml_erros'] = erros
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

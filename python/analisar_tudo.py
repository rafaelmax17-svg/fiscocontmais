# -*- coding: utf-8 -*-
"""🔎 Analisar tudo / Aplicar tudo — Corretor do SPED Fiscal (só Admin), um arquivo por vez.

Roda TODAS as conferências do Corretor sobre o mesmo SPED e devolve um painel único; nada muda até "Aplicar tudo".
Ordem (é também a ordem de aplicação, uma sobre a outra, no mesmo arquivo):
  1) Validação do PVA ............ fiscal_core.corrigir_sped_fiscal + ajusta_campos_c197 (sempre aplicada)
  2) Uso e consumo · DIFAL e crédito  difal_ro (CFOP pela UF, DIFAL, balcão, frete, crédito em uso e consumo)
  3) Desconto × XML .............. desconto_xml
  4) ICMS creditado × XML ......... icms_xml
  5) Valor e base × XML ........... valor_xml
  6) Crédito de fornecedor do Simples  simples_ro
  7) Acumulador 7000 .............. acumulador_despesa
  8) Cadastro de produtos (0200) .. cadastro_0200
  (Estoque de mercadoria que saiu da ST precisa da planilha do estoque: fica no botão próprio.)
O plano padrão é o mesmo do antigo "Automatizar correção" (lote_sped), agora com escolha nota a nota.

Escolhas (aplicar):
  {"etapas": {"difal": true, ...},                       etapa desmarcada não roda
   "difal": {"<id da decisão>": "incluir"|"nao"|..., "cfop:<id>": false, "cred:<id doc>": false, "cred_modo": "zerar"|"estorno"},
   "desconto": {"<chave>": false}, "icms": {"<chave>": false}, "valor": {"<chave>": false},
   "simples": {"<chave>": false},
   "acum": {"<COD_ITEM>": "70xx"|false}, "cad": {"<COD_ITEM>": "07"|"08"|false},
   "e116": {"venc": "ddmmaaaa", "cod_rec": "..."}}
Gera arquivo NOVO; o original nunca é alterado.
"""
import os
import re
import json

import fiscal_core as fc
import difal_ro as dr
import lote_sped as ls
import icms_xml as ix
import valor_xml as vx
import simples_ro as sr
import desconto_xml as dx
import acumulador_despesa as ad
import cadastro_0200 as c2
from xml_entradas import ler_xmls


def _ch(s):
    return re.sub(r'\D', '', s or '')


def _num(s):
    return (s or '').lstrip('0') or (s or '')


def _fm(v):
    return f'{float(v or 0):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _itens_sped(corr):
    """{linha do C100: [itens do C170 com descrição do 0200]} — para o "ver itens" das notas sem XML."""
    linhas, _, _ = dr.dividir(corr)
    _, _, _, docs, _, _ = dr._estrutura(linhas)
    p0200 = {c[2]: c[3] for c in (l.split('|') for l in linhas if l.startswith('|0200|')) if len(c) > 3}
    return {d['i']: [{'cod': c['item'], 'descr': p0200.get(c['item']) or c['descr'], 'valor': c['vl'], 'cfop': c['cfop']} for c in d['c170']]
            for d in docs}


def _base(sped, xml_dir):
    texto, enc = fc._ler_sped(sped)
    corr, rc = fc.corrigir_sped_fiscal(texto, [])
    corr, rc['c197_campos_ajustados'] = fc.ajusta_campos_c197(corr)
    xmls, lidos, erros = ler_xmls([xml_dir]) if xml_dir else ({}, 0, 0)
    return texto, enc, corr, rc, xmls, lidos, erros


# ------------------------------------------------------------------ análise
def analisar(sped, xml_dir):
    texto, enc, corr, rc, xmls, lidos, erros = _base(sped, xml_dir)
    cab = ls._cab(texto) or {}
    auto, dec, an, sn = ls.plano_empresa(corr, xmls, lidos)
    por_doc = {d['id']: d for d in an['docs']}
    itens_sped = _itens_sped(corr)
    etapas = []

    # 1) validação
    itens_val = [(k, rot) for k, rot in (('c191_removidos', 'C191 sem uso removidos'), ('e500_linhas_removidas', 'Linhas do E500 removidas'),
                                         ('gtin_limpos', 'GTIN inválido limpo'), ('cest_limpos', 'CEST inválido limpo'),
                                         ('cod_nat_corrigidos', 'COD_NAT corrigido'), ('c197_campos_ajustados', 'C197 com campo a mais'),
                                         ('c100_totais_corrigidos', 'Totais do C100'), ('vl_merc_corrigidos', 'VL_MERC do C100'),
                                         ('cod_sit_08', 'Situação 08 (regime especial)'))]
    linhas_val = [{'sel': k, 'txt': rot, 'qtd': rc.get(k) or 0} for k, rot in itens_val if rc.get(k)]
    if rc.get('registro_0400_criado'):
        linhas_val.append({'sel': 'r0400', 'txt': '0400 criado para COD_NAT usado', 'qtd': len(rc['registro_0400_criado'])})
    n_val = sum(x['qtd'] for x in linhas_val)
    etapas.append({'key': 'validacao', 'titulo': 'Validação do PVA', 'desc': 'C191, E500, GTIN, CEST, COD_NAT, C197 com campo a mais, totais do C100',
                   'qtd': f'{n_val} correção(ões)' if n_val else 'nada encontrado', 'valor': '', 'badge': 'aplica sozinho' if n_val else 'sem correção',
                   'tipo': 'auto' if n_val else 'zero', 'fixo': True, 'grupos': [{'id': 'val', 'titulo': 'Correções de validação', 'linhas': linhas_val}] if n_val else []})

    # 2) DIFAL e crédito
    g_cfop = [{'sel': f"cfop:{a['id']}", 'nota': a['nota'], 'det': f"{a['de']} → {a['para']}", 'valor': None, 'marcado': True}
              for a in auto['cfop']]
    g_dif, g_bal, g_fre, g_sna, g_snd = [], [], [], [], []
    cred = None
    for d in dec:
        rot0 = next((o['rot'] for o in d['opcoes'] if o['v'] not in ('nao', 'manter')), '')
        base = {'sel': d['id'], 'nota': d['nota'], 'det': ' · '.join(x for x in (d['titulo'], rot0, d['detalhe']) if x), 'valor': d['valor'],
                'opcoes': d['opcoes'], 'padrao': d['padrao'],
                'marcado': d['padrao'] not in ('nao', 'manter')}
        if d['tipo'] == 'difal':
            doc = por_doc.get(int(d['id'].split(':')[1]))
            if doc:
                its = [{'cod': '', 'descr': it.get('xprod', ''), 'valor': it.get('valor') or 0.0, 'cfop': ''} for it in (doc.get('itens_xml') or [])] \
                    or itens_sped.get(doc['id'], [])
                base['extra'] = {'uf': doc['uf_origem'], 'calculado': doc['difal_calculado'], 'lancado': doc['difal_lancado'], 'itens': its[:60]}
            base['titulo'] = d['titulo']
            g_dif.append(base)
        elif d['tipo'] == 'balcao':
            g_bal.append(base)
        elif d['tipo'] == 'frete':
            g_fre.append(base)
        elif d['tipo'] == 'credito':
            docs_c = [x for x in an['creditos']['docs'] if x['sugerido']]
            cred = {'d': d, 'linhas': [{'sel': f"cred:{x['id']}", 'nota': f"NF {x.get('num', '')} · {x.get('fornecedor', '')}",
                                        'det': ', '.join(x.get('cfops') or []) if isinstance(x.get('cfops'), list) else '',
                                        'valor': x['credito'], 'marcado': True} for x in docs_c]}
        elif d['tipo'] == 'simples_aliq':
            g_sna.append(base)
        elif d['tipo'] == 'simples_sem':
            g_snd.append(base)
    grupos = []
    if g_cfop:
        grupos.append({'id': 'cfop', 'titulo': 'CFOP pela UF do fornecedor (1.xxx × 2.xxx)', 'sugestao': 'corrigir (regra clara)', 'linhas': g_cfop})
    if g_dif:
        grupos.append({'id': 'difal', 'titulo': 'DIFAL faltando ou com valor diferente (C197 RO40000001/2)', 'sugestao': 'incluir / trocar pelo calculado',
                       'linhas': g_dif})
    if g_bal:
        grupos.append({'id': 'balcao', 'titulo': 'Compra no balcão em outro estado', 'sugestao': 'conforme o caso', 'linhas': g_bal, 'select': True})
    if g_fre:
        grupos.append({'id': 'frete', 'titulo': 'DIFAL do frete (CT-e)', 'sugestao': 'incluir', 'linhas': g_fre})
    if cred and cred['linhas']:
        grupos.append({'id': 'cred', 'titulo': 'Crédito de ICMS tomado em uso e consumo', 'sugestao': 'zerar o crédito', 'linhas': cred['linhas'],
                       'modo': {'opcoes': [o for o in cred['d']['opcoes'] if o['v'] != 'nao'], 'padrao': 'zerar'}})
    n_dif = sum(len(g['linhas']) for g in grupos)
    v_dif = sum((x.get('valor') or 0) for g in grupos if g['id'] in ('difal', 'frete') for x in g['linhas'] if x.get('marcado'))
    n_dec = sum(len(g['linhas']) for g in grupos if g['id'] != 'cfop')
    etapas.append({'key': 'difal', 'titulo': 'Uso e consumo · DIFAL e crédito', 'desc': 'CFOP pela UF do fornecedor · DIFAL de RO · balcão · frete · crédito em uso e consumo',
                   'qtd': f'{n_dif} nota(s)' if n_dif else 'nada encontrado', 'valor': (f"{'+' if v_dif > 0 else '−'} R$ {_fm(abs(v_dif))} DIFAL" if abs(v_dif) >= 0.01 else ''),
                   'badge': f'decidir {n_dec}' if n_dec else ('pode corrigir' if n_dif else 'sem correção'),
                   'tipo': 'decidir' if n_dec else ('auto' if n_dif else 'zero'), 'grupos': grupos})

    # 3) desconto (sobre o arquivo de validação; a aplicação reanalisa depois do DIFAL)
    if xmls:
        da = dx.analisar_texto(corr, xmls)
        lin = [{'sel': z['chave'], 'nota': f"NF {_num(z['num'])} · {z['fornecedor']}" + (f" · {z['uf']}" if z['uf'] else ''),
                'det': f"desconto SPED R$ {_fm(z['desc_sped'])} → XML R$ {_fm(z['desc_xml'])}" + (' · valor do documento acompanha' if z['corrige_doc'] else ''),
                'valor': z['desc_xml'] - z['desc_sped'], 'origem': z['origem'], 'marcado': True,
                'itens': [{'num': it['num'], 'cod': it['cod'], 'descr': it['descr'], 'vl_item': it['vl_item'], 'antes': it['desc_sped'],
                           'xml': it['desc_xml'], 'novo': it['desc_novo'], 'origem': it['origem'] or '—'} for it in z['itens']]} for z in da['docs']]
        r = da['resumo']
        etapas.append({'key': 'desconto', 'titulo': 'Desconto × XML', 'desc': 'desconto do C100 e dos itens (C170) pelo XML; sem desconto no item do XML, divide em proporção',
                       'qtd': f"{r['com_diferenca']} nota(s) · {r['itens']} item(ns)" if lin else 'nada encontrado',
                       'valor': f"R$ {_fm(r['desconto_a_lancar'])}" if lin else '', 'badge': 'pelo XML' if lin else 'sem correção',
                       'tipo': 'auto' if lin else 'zero', 'grupos': [{'id': 'desconto', 'titulo': 'Notas com desconto diferente do XML',
                                                                       'sugestao': f"{r['pelo_item']} pelo item do XML · {r['proporcao']} em proporção", 'linhas': lin}] if lin else []})
        base_x = dx.aplicar_texto(corr, xmls, {'chaves': [z['chave'] for z in da['docs']]})[0] if da['docs'] else corr
        ia = ix.analisar_texto(base_x, xmls)
        lin = [{'sel': _ch(z['chave']), 'nota': f"NF {_num(z['num'])} · {z['fornecedor']}",
                'det': f"ICMS creditado R$ {_fm(z['icms_sped'])} × destacado R$ {_fm(z['icms_xml'])}", 'valor': -z['reducao'], 'marcado': True}
               for z in ia['docs'] if z['sugerido']]
        v = sum(-x['valor'] for x in lin)
        etapas.append({'key': 'icms', 'titulo': 'ICMS creditado × XML', 'desc': 'crédito tomado maior que o destacado na nota',
                       'qtd': f'{len(lin)} nota(s)' if lin else 'nada encontrado', 'valor': f'− R$ {_fm(v)} crédito' if lin else '',
                       'badge': 'pelo XML' if lin else 'sem correção', 'tipo': 'auto' if lin else 'zero',
                       'grupos': [{'id': 'icms', 'titulo': 'Crédito acima do destacado', 'sugestao': 'reduzir ao XML', 'linhas': lin}] if lin else []})
        va = vx.analisar_texto(base_x, xmls)
        lin = []
        for z in va['docs']:
            if not z['sugerido']:
                continue
            o = []
            if z['doc_dif']:
                o.append(f"valor do documento R$ {_fm(z['vl_doc_sped'])} → R$ {_fm(z['vl_doc_xml'])}")
            if z['base'] == 'maior':
                o.append(f"base/ICMS pelo XML (− R$ {_fm(z.get('reducao') or 0)})")
            lin.append({'sel': _ch(z['chave']), 'nota': f"NF {_num(z['num'])} · {z['fornecedor']}", 'det': ' · '.join(o) or '; '.join(z['obs'][:1]),
                        'valor': -(z.get('reducao') or 0), 'marcado': True})
        v = sum(-x['valor'] for x in lin)
        etapas.append({'key': 'valor', 'titulo': 'Valor e base × XML', 'desc': 'valor do documento, base e ICMS de cada nota de entrada',
                       'qtd': f'{len(lin)} nota(s)' if lin else 'nada encontrado', 'valor': (f'− R$ {_fm(v)} crédito' if v else '') if lin else '',
                       'badge': 'pelo XML' if lin else 'sem correção', 'tipo': 'auto' if lin else 'zero',
                       'grupos': [{'id': 'valor', 'titulo': 'Notas diferentes do XML', 'sugestao': 'acertar pelo XML', 'linhas': lin}] if lin else []})
        lin = [{'sel': a['chave'], 'nota': a['nota'], 'det': {'incluir': 'incluir o crédito (C195 + C197)', 'lugar_errado': 'crédito no lugar errado',
                                                              'divergente': 'crédito diferente do XML'}.get(a['status'], a['status']),
                'valor': a['credito'], 'marcado': True} for a in auto['simples']]
        grupos_sn = []
        if lin:
            grupos_sn.append({'id': 'simples', 'titulo': 'Crédito informado no XML (CSOSN 101/201)', 'sugestao': 'lançar como no XML', 'linhas': lin})
        if g_snd:
            grupos_sn.append({'id': 'snd', 'titulo': 'Crédito de Simples sem direito', 'sugestao': 'retirar o crédito', 'linhas': g_snd})
        n_sna = len(g_sna)
        etapas.append({'key': 'simples', 'titulo': 'Crédito de fornecedor do Simples', 'desc': 'C195 + C197 RO00000001 pelo XML'
                       + (f' · {n_sna} nota(s) sem percentual: use o botão Simples' if n_sna else ''),
                       'qtd': f"{sum(len(g['linhas']) for g in grupos_sn)} nota(s)" if grupos_sn else 'nada encontrado',
                       'valor': f"R$ {_fm(sum(x['valor'] for x in lin))}" if lin else '', 'badge': 'pelo XML' if grupos_sn else 'sem correção',
                       'tipo': 'auto' if grupos_sn else 'zero', 'grupos': grupos_sn})
    else:
        for k, t in (('desconto', 'Desconto × XML'), ('icms', 'ICMS creditado × XML'), ('valor', 'Valor e base × XML'), ('simples', 'Crédito de fornecedor do Simples')):
            etapas.append({'key': k, 'titulo': t, 'desc': 'precisa dos XMLs de entrada', 'qtd': 'sem XML', 'valor': '', 'badge': 'anexe os XMLs',
                           'tipo': 'sem_xml', 'grupos': []})

    # 7) acumulador 7000
    aa = ad.analisar_texto(corr)
    nomes = {a['cod']: a['nome'] for a in aa['acumuladores']}
    lin = [{'sel': i['item'], 'nota': i['descr'] or i['item'], 'det': f"cód. {i['item']} · NCM {i['ncm'] or '—'} · {i['motivo']}", 'valor': i['valor'],
            'confianca': i['confianca'], 'padrao': i['sugestao'] or '', 'marcado': bool(i['sugestao'])} for i in aa['itens']]
    n_media = sum(1 for i in aa['itens'] if i['confianca'] != 'alta')
    etapas.append({'key': 'acum', 'titulo': 'Acumulador 7000', 'desc': 'acumulador de despesa certo (7001 a 7040) por produto',
                   'qtd': f'{len(lin)} produto(s)' if lin else 'nada encontrado', 'valor': f"R$ {_fm(aa['resumo']['valor'])}" if lin else '',
                   'badge': f'revisar {n_media}' if n_media else ('pode corrigir' if lin else 'sem correção'),
                   'tipo': 'decidir' if n_media else ('auto' if lin else 'zero'),
                   'grupos': [{'id': 'acum', 'titulo': 'Produtos no acumulador 7000', 'sugestao': 'acumulador sugerido (pode trocar)', 'linhas': lin,
                               'acumuladores': [{'cod': k, 'nome': v} for k, v in nomes.items()]}] if lin else []})

    # 8) cadastro 0200
    ca = c2.analisar_texto(corr)
    lin = [{'sel': i['cod'], 'nota': i['desc'], 'det': f"cód. {i['cod']} · NCM {i['ncm'] or '—'} · CFOP " + ', '.join(f'{c} ({n})' for c, n in i['cfops'])
            + ('' if i['pode'] else ' · NÃO ALTERAR: ' + '; '.join(i['motivos'])), 'valor': i['valor'], 'padrao': i['sugestao'],
            'marcado': i['pode'], 'bloqueado': not i['pode']} for i in ca['itens']]
    etapas.append({'key': 'cad', 'titulo': 'Cadastro de produtos (0200)', 'desc': 'tipo 00 que só entrou como uso e consumo / ativo → 07 / 08',
                   'qtd': f'{len(lin)} produto(s)' if lin else 'nada encontrado', 'valor': '',
                   'badge': 'pode corrigir' if ca['resumo']['podem'] else ('não alterar' if lin else 'sem correção'),
                   'tipo': 'auto' if ca['resumo']['podem'] else 'zero',
                   'grupos': [{'id': 'cad', 'titulo': 'Produtos tipo 00 usados como uso e consumo / ativo', 'sugestao': '07 uso e consumo / 08 ativo',
                               'linhas': lin}] if lin else []})
    etapas.append({'key': 'estoque', 'titulo': 'Estoque de mercadoria que saiu da ST', 'desc': 'precisa da planilha do estoque: use o botão "Estoque ST"',
                   'qtd': '—', 'valor': '', 'badge': 'botão próprio', 'tipo': 'fora', 'grupos': []})
    e110 = ls._e110(corr) or {}
    return {'arquivo': os.path.basename(sped), 'xmls': xml_dir, 'xml_lidos': lidos, 'xml_erros': erros,
            'empresa': {'nome': cab.get('nome', ''), 'cnpj': cab.get('cnpj', ''), 'dt_ini': cab.get('dt_ini', ''), 'dt_fin': cab.get('dt_fin', '')},
            'etapas': etapas, 'icms_antes': e110.get('recolher', 0.0),
            'avisos': list(an.get('avisos') or [])[:12]}


# ------------------------------------------------------------------ aplicação
def aplicar(sped, xml_dir, escolhas):
    esc = escolhas or {}
    liga = lambda k: (esc.get('etapas') or {}).get(k, True)
    texto, enc, corr, rc, xmls, lidos, erros = _base(sped, xml_dir)
    auto, dec, an, sn = ls.plano_empresa(corr, xmls, lidos)
    final, resumo, avisos = corr, {}, []
    e116 = esc.get('e116') if isinstance(esc.get('e116'), dict) else None
    resumo['validacao'] = {'feito': sum((rc.get(k) or 0) for k in ('c191_removidos', 'e500_linhas_removidas', 'gtin_limpos', 'cest_limpos',
                                                                        'cod_nat_corrigidos', 'c197_campos_ajustados', 'c100_totais_corrigidos',
                                                                        'vl_merc_corrigidos', 'cod_sit_08')) + len(rc.get('registro_0400_criado') or [])}

    def erro_de(r, etapa):
        if r.get('erro'):
            if 'E116' in r['erro'] and not e116:
                return {'precisa_e116': True, 'erro': 'Com a correção a empresa passa a ter ICMS a recolher e o SPED não tem guia (E116). '
                                                       'Informe o vencimento e o código de receita da guia.', 'etapa': etapa}
            return {'erro': f"{etapa}: {r['erro']}", 'etapa': etapa}
        return None

    # 2) DIFAL e crédito
    if liga('difal'):
        ed = esc.get('difal') or {}
        auto_f = dict(auto)
        auto_f['cfop'] = [a for a in auto['cfop'] if ed.get(f"cfop:{a['id']}", True) is not False]
        auto_f['simples'] = []
        dec_f, escolhas_l = [], {}
        for d in dec:
            if d['tipo'] in ('simples_aliq', 'simples_sem'):
                continue
            d2 = dict(d)
            if d['tipo'] == 'credito':
                fora = {int(k.split(':')[1]) for k, v in ed.items() if k.startswith('cred:') and v is False}
                d2['docs'] = [i for i in d['docs'] if i not in fora]
                escolhas_l[d['id']] = (ed.get('cred_modo') or d['padrao']) if d2['docs'] else 'nao'
            else:
                v = ed.get(d['id'])
                escolhas_l[d['id']] = d['padrao'] if v is None or v is True else ('nao' if d['tipo'] != 'balcao' else 'manter') if v is False else v
            dec_f.append(d2)
        if e116:
            escolhas_l['e116'] = e116
        sel_dif, _, _ = ls._selecoes(an, auto_f, dec_f, escolhas_l)
        if sel_dif['docs'] or sel_dif['fretes'] or sel_dif['creditos']:
            novo, rd = dr.aplicar_texto(final, sel_dif, xmls)
            e = erro_de(rd, 'DIFAL e crédito')
            if e:
                return None, enc, e
            final = novo
            resumo['difal'] = {'difal': rd.get('difal_total', 0.0), 'notas': rd.get('difal_incluidos', 0), 'cfop': rd.get('notas_cfop', 0),
                               'credito': rd.get('cred_total', 0.0), 'fretes': rd.get('fretes_incluidos', 0)}
            avisos += rd.get('avisos') or []
    if xmls:
        # 3) desconto
        if liga('desconto'):
            ex = esc.get('desconto') or {}
            da = dx.analisar_texto(final, xmls)
            chs = [z['chave'] for z in da['docs'] if ex.get(z['chave'], True) is not False]
            if chs:
                final, r = dx.aplicar_texto(final, xmls, {'chaves': chs})
                resumo['desconto'] = {'notas': r['notas'], 'itens': r['itens'], 'desconto': r['desconto'], 'vl_doc': r['vl_doc_corrigido']}
                avisos += r.get('avisos') or []
        # 4) ICMS × XML  /  5) valor e base × XML
        for key, mod, rot in (('icms', ix, 'ICMS creditado × XML'), ('valor', vx, 'Valor e base × XML')):
            if not liga(key):
                continue
            ex = esc.get(key) or {}
            a = mod.analisar_texto(final, xmls)
            ids = [z['id'] for z in a['docs'] if z['sugerido'] and ex.get(_ch(z['chave']), True) is not False]
            if ids:
                sel = {'docs': ids}
                if e116:
                    sel['e116'] = e116
                novo, r = mod.aplicar_texto(final, xmls, sel)
                e = erro_de(r, rot)
                if e:
                    return None, enc, e
                final = novo
                resumo[key] = {'notas': r.get('notas', 0), 'credito_retirado': r.get('credito_retirado', 0.0)}
                avisos += r.get('avisos') or []
        # 6) Simples
        if liga('simples'):
            ex = esc.get('simples') or {}
            ed = esc.get('difal') or {}
            sn_sel = {}
            for a in auto['simples']:
                if ex.get(a['chave'], True) is not False:
                    sn_sel[a['chave']] = {'zerar': a['zerar'], 'c197': True}
            for d in dec:
                if d['tipo'] == 'simples_sem' and ed.get(d['id'], True) is not False and (esc.get('simples') or {}).get(d['id'], True) is not False:
                    sn_sel[d['id'].split(':', 1)[1]] = {'zerar': d.get('zerar', True), 'c197': True}
            if sn_sel:
                s2 = sr.analisar_texto(final, xmls, lidos)
                ids = {ls._chave_doc(x): x['id'] for x in s2['docs']}
                docs = [{'id': ids[k], **v} for k, v in sn_sel.items() if k in ids]
                if docs:
                    sel = {'docs': docs}
                    if e116:
                        sel['e116'] = e116
                    novo, r = sr.aplicar_texto(final, xmls, sel)
                    e = erro_de(r, 'Crédito do Simples')
                    if e:
                        return None, enc, e
                    final = novo
                    resumo['simples'] = {'notas': r.get('notas', 0), 'credito': r.get('credito_c197', 0.0)}
                    avisos += r.get('avisos') or []
    # 7) acumulador 7000
    if liga('acum'):
        ea = esc.get('acum') or {}
        aa = ad.analisar_texto(final)
        mapa = {}
        for i in aa['itens']:
            v = ea.get(i['item'], i['sugestao'])
            if v and v is not False and v in ad.ACUM:
                mapa[i['item']] = v
        if mapa:
            final, r = ad.aplicar_texto(final, {'itens': mapa})
            resumo['acum'] = {'itens': r['alterados'], 'valor': r['valor'], 'acumuladores': r['acumuladores']}
            avisos += r.get('avisos') or []
    # 8) cadastro 0200
    if liga('cad'):
        ec = esc.get('cad') or {}
        ca = c2.analisar_texto(final)
        mapa = {}
        for i in ca['itens']:
            if not i['pode']:
                continue
            v = ec.get(i['cod'], i['sugestao'])
            if v and v is not False and v != '00':
                mapa[i['cod']] = v
        if mapa:
            final, r = c2.aplicar_texto(final, {'itens': mapa})
            resumo['cad'] = {'produtos': r['alterados'], 'por_tipo': r['por_tipo']}
            avisos += [a for a in r.get('avisos') or [] if 'assinado' not in a]
    antes = ls._e110(texto) or {}
    depois = ls._e110(final) or {}
    avisos2 = []
    for a in avisos:
        if a not in avisos2:
            avisos2.append(a)
    avisos2 += fc.confere_e110_ajustes(final)
    return final, enc, {'ok': True, 'resumo': resumo, 'avisos': avisos2[:30], 'icms_antes': antes.get('recolher', 0.0),
                        'icms_depois': depois.get('recolher', 0.0), 'credor_antes': antes.get('sld_transp', 0.0),
                        'credor_depois': depois.get('sld_transp', 0.0), 'alterado': final != texto}


# ------------------------------------------------------------------ CLI
def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    sped, js = opt('--sped'), opt('--json')
    if not sped or not js:
        print('uso: analisar-tudo --sped ARQ.txt [--xmls PASTA] [--regimes R.json] --json saida.json [--aplicar esc.json --saida novo.txt]')
        return 1
    dr.carrega_regimes(opt('--regimes'))
    try:
        if opt('--aplicar'):
            with open(opt('--aplicar'), 'r', encoding='utf-8') as fh:
                esc = json.load(fh)
            final, enc, res = aplicar(sped, opt('--xmls'), esc)
            if final is not None and res.get('ok'):
                fc._grava_sped(opt('--saida'), final, enc)
        else:
            res = analisar(sped, opt('--xmls'))
    except Exception as e:  # pragma: no cover
        import traceback
        res = {'erro': f'Falha ao processar: {e}', 'detalhe': traceback.format_exc()[-1500:]}
    tmp = js + '.parcial'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False)
    os.replace(tmp, js)
    return 0

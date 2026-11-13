# -*- coding: utf-8 -*-
"""✨ Análise Inteligente (antigo "Analisar tudo") — Corretor do SPED Fiscal, um arquivo por vez.

Roda TODAS as conferências do Corretor sobre o mesmo SPED e devolve um painel único; nada muda até "Aplicar tudo".
Ordem (é também a ordem de aplicação, uma sobre a outra, no mesmo arquivo):
  1) Validação do PVA ............ fiscal_core.corrigir_sped_fiscal + ajusta_campos_c197 (sempre aplicada)
  1·) Chave de acesso × XML ........ chave_xml (C100 CHV_NFE de NF-e/NFC-e, entradas e saídas, pela do XML da nota)
  1·) NCM × XML das entradas ....... ncm_xml (0200 COD_NCM pelo NCM do item na NF-e do fornecedor; antes da ICMS-ST)
  1a) Uso e consumo como revenda .. uso_consumo_cfop (produto "USO E CONSUMO" com CFOP de revenda/industrialização → x.556/x.407/x.557)
  1c) ICMS-ST na entrada .......... st_entrada_ro (produto da ST de RO lançado como tributado → x.403/x.401 e CST 60;
                                    x.403 com CST tributado → x.102 se o XML mostrar tributado de fato)
  1b) Combustível × uso e consumo  combustivel_cfop (x.556/x.407 → x.653; antes do DIFAL, que não vale para combustível)
  2) Uso e consumo · DIFAL e crédito  difal_ro (CFOP pela UF, DIFAL, balcão, frete, crédito em uso e consumo)
  3) Desconto × XML .............. desconto_xml
  4) ICMS creditado × XML ......... icms_xml
  5) Valor e base × XML ........... valor_xml
  6) Crédito de fornecedor do Simples  simples_ro
  6b) Crédito maçã e pera ......... credito_maca (C195 + C197 RO10000038; não precisa de XML)
  7) Acumulador 7000 .............. acumulador_despesa
  8) Cadastro de produtos (0200) .. cadastro_0200
  9) Unidade × XML ................ unidade_xml (troca o código da unidade pelo da nota; precisa dos XMLs)
  (Estoque de mercadoria que saiu da ST precisa da planilha do estoque: fica no botão próprio.)
O plano padrão é o mesmo do antigo "Automatizar correção" (lote_sped), agora com escolha nota a nota.

Equipe × Admin: "permitidas" (lista de chaves) limita as conferências — a equipe recebe só as que o Admin ligou no painel
"O que a equipe recebe na Análise Inteligente" (config_equipe/corretor no Firestore). Admin: None = todas.
A Validação do PVA é a base de todas e sempre roda.

IDs do DIFAL: são o índice da linha do C100/D100. Como o passo do combustível pode dividir C190 (linhas a mais), a análise
monta o plano do DIFAL sobre o arquivo com TODAS as sugestões de combustível aplicadas; na aplicação, se o combustível
foi aplicado diferente (item desmarcado, etapa desligada), os IDs são traduzidos pela nota (chave ou nº|série|participante).

Escolhas (aplicar):
  {"etapas": {"difal": true, ...},                       etapa desmarcada não roda
   "difal": {"<id da decisão>": "incluir"|"nao"|..., "cfop:<id>": false, "cred:<id doc>": false, "cred_modo": "zerar"|"estorno"},
   "desconto": {"<chave>": false}, "icms": {"<chave>": false}, "valor": {"<chave>": false},
   "simples": {"<chave>": false}, "maca": {"<chave da nota ou nº|série|fornecedor>": false},
   "acum": {"<COD_ITEM>": "70xx"|false}, "cad": {"<COD_ITEM>": "07"|"08"|false}, "comb": {"<doc:item>": false}, "ucons": {"<doc:item>": false},
   "stent": {"<doc:item>": false}, "chave": {"<nota>": false}, "ncm": {"<COD_ITEM>": "<NCM escolhido>"|false},
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
import credito_maca as cm
import combustivel_cfop as cc
import uso_consumo_cfop as uc
import chave_xml as ck
import ncm_xml as nx
import st_entrada_ro as se
import unidade_xml as ux
from xml_entradas import ler_xmls


def _ch(s):
    return re.sub(r'\D', '', s or '')


def _num(s):
    return (s or '').lstrip('0') or (s or '')


def _ch_maca(x):
    return _ch(x.get('chave')) or f"{x.get('num', '')}|{x.get('serie', '')}|{x.get('fornecedor', '')}"


def _fm(v):
    return f'{float(v or 0):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _pode(permitidas, k):
    return permitidas is None or k == 'validacao' or k in permitidas


def _todas(mod, texto, xmls):
    """Arquivo com todas as sugestões de uma troca de CFOP aplicadas (uso e consumo / combustível) — base das etapas seguintes."""
    a = mod.analisar_texto(texto, xmls)
    if not a['itens']:
        return texto, a
    return mod.aplicar_texto(texto, [i['id'] for i in a['itens']], xmls)[0], a


def _base_analise(corr, xmls, permitidas):
    """O arquivo que a análise usa depois das trocas de CFOP (uso e consumo, combustível)."""
    for k, mod in (('chave', ck), ('ncm', nx), ('ucons', uc), ('comb', cc), ('stent', se)):
        if _pode(permitidas, k):
            corr = _todas(mod, corr, xmls)[0]
    return corr


def _ids_notas(texto):
    """{índice da linha do C100/D100: identificação estável da nota}."""
    linhas, _, _ = dr.dividir(texto)
    _, part, _, docs, _, _ = dr._estrutura(linhas)
    m = {}
    for d in docs:
        m[d['i']] = 'C|' + (_ch(d['chave']) or f"{d['num']}|{d['serie']}|{d['part']}|{d['dt']}")
    for t in dr._estrutura_d(linhas):
        m[t['i']] = 'D|' + (_ch(t['chave']) or f"{t['num']}|{t['serie']}|{t['part']}|{t['dt']}")
    return m


def _traduz_ids(ed, de_texto, para_texto):
    """Escolhas do DIFAL ('pfx:ID') feitas sobre de_texto → IDs de para_texto."""
    if not ed or de_texto == para_texto:
        return ed
    a, b = _ids_notas(de_texto), _ids_notas(para_texto)
    inv = {}
    for i, k in b.items():
        inv.setdefault(k, i)
    out = {}
    for k, v in ed.items():
        m = re.match(r'^([a-z]+):(\d+)$', k)
        if m and int(m.group(2)) in a and a[int(m.group(2))] in inv:
            out[f"{m.group(1)}:{inv[a[int(m.group(2))]]}"] = v
        else:
            out[k] = v
    return out


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
def analisar(sped, xml_dir, permitidas=None):
    texto, enc, corr, rc, xmls, lidos, erros = _base(sped, xml_dir)
    cab = ls._cab(texto) or {}
    pode = lambda k: _pode(permitidas, k)
    corr_v = corr                                     # arquivo só com a validação (é o que a etapa 1 mostra)
    ca_uc = ca_comb = ca_ch = None
    if pode('chave'):
        corr, ca_ch = _todas(ck, corr, xmls)         # as demais etapas acham o XML pela chave já corrigida
    ca_ncm = None
    if pode('ncm') and xmls:
        corr, ca_ncm = _todas(nx, corr, xmls)        # a ICMS-ST na entrada usa o NCM já corrigido pelo XML
    if pode('ucons'):
        corr, ca_uc = _todas(uc, corr, xmls)         # as demais etapas olham o arquivo já com o CFOP de uso e consumo
    if pode('comb'):
        corr, ca_comb = _todas(cc, corr, xmls)       # … e com o combustível
    ca_st = None
    if pode('stent'):
        corr, ca_st = _todas(se, corr, xmls)         # … e com a ST da entrada
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

    # 1·) chave de acesso × XML (NF-e e NFC-e, entradas e saídas)
    if ca_ch is not None:
        r = ca_ch['resumo']
        lin = [{'sel': i['id'], 'nota': f"{'NFC-e' if i['mod'] == '65' else 'NF-e'} {_num(i['num'])} · série {i['serie']} · {i['quem']} · {i['nome']}",
                'det': f"chave {i['chave_sped'] or '(vazia)'} → {i['chave_xml']} · {i['motivo']}", 'valor': i['valor'], 'marcado': True}
               for i in ca_ch['itens']]
        lin += [{'sel': f"pend:{n}", 'nota': f"{'NFC-e' if p['mod'] == '65' else 'NF-e'} {_num(p['num'])} · série {p['serie']} · {p['quem']} · {p['nome']}",
                 'det': 'NÃO ALTERAR: ' + p['motivo'], 'valor': p['valor'], 'marcado': False, 'bloqueado': True}
                for n, p in enumerate(ca_ch['pendencias'])]
        extra = [f"{r['ok']} chave(s) conferem com o XML"]
        if r['sem_xml']:
            extra.append(f"{r['sem_xml']} nota(s) sem XML anexado")
        if r['xml_sem_nota']:
            extra.append(f"{r['xml_sem_nota']} XML(s) sem nota no SPED ({r['xml_sem_nota_ent']} de entrada, {r['xml_sem_nota_sai']} de saída)")
        etapas.append({'key': 'chave', 'titulo': 'Chave de acesso × XML', 'desc': 'NF-e e NFC-e, entradas e saídas: chave do C100 conferida com o XML da nota · ' + ' · '.join(extra),
                       'qtd': (f"{r['corrigir']} nota(s) ({r['entradas']} entrada · {r['saidas']} saída)" if r['corrigir'] else '')
                              + (f"{' · ' if r['corrigir'] else ''}{r['pendencias']} com chave errada sem XML" if r['pendencias'] else '')
                              or 'tudo confere',
                       'valor': '', 'badge': 'pode corrigir' if r['corrigir'] else ('precisa do XML' if r['pendencias'] else 'sem correção'),
                       'tipo': 'auto' if r['corrigir'] else 'zero',
                       'grupos': [{'id': 'chave', 'titulo': 'Notas com a chave errada', 'sugestao': 'chave do XML', 'linhas': lin}] if lin else []})

    # 1·) NCM × XML das entradas (0200 COD_NCM): SPED diferente do XML → opção de alterar para o NCM do XML
    if ca_ncm is not None:
        r = ca_ncm['resumo']
        lin = []
        for i in ca_ncm['itens']:
            det = (f"cód. {i['cod']} · NCM no SPED {i['ncm_sped'] or '(em branco)'} · no XML {i['ncm_xml']} · {i['notas']} nota(s)"
                   + (f" · em {i['notas_iguais']} nota(s) o XML traz o mesmo NCM do SPED" if i['notas_iguais'] else '')
                   + (f" · no XML: \"{i['xprod']}\" ({i['nota_ex']})" if i['xprod'] else ''))
            st = i['st'].get(i['opcoes'][0]['v'])
            lin.append({'sel': i['cod'], 'nota': i['descr'] or i['cod'], 'det': det + (f" · {st}" if st else ''), 'valor': i['valor'], 'marcado': False,
                        'opcoes': i['opcoes'], 'padrao': i['opcoes'][0]['v'], 'nfs': i['nfs'],
                        'busca': ' '.join(str(n['num']) for n in i['nfs']) + f" {i['ncm_xml']} {i['ncm_sped']}"})
        etapas.append({'key': 'ncm', 'titulo': 'NCM × XML das entradas',
                       'desc': f"NCM do cadastro do produto (0200, campo 08) diferente do NCM do item na NF-e: marque os que devem ficar com o NCM do XML · "
                               f"{r['conferidos']} item(ns) de entrada conferidos com o XML"
                               + (f" · {r['sem_xml']} nota(s) de entrada sem XML anexado" if r['sem_xml'] else '')
                               + ' · o 0200 vale para o arquivo inteiro (entradas, saídas e H010)',
                       'qtd': f"{r['produtos']} produto(s)" if r['produtos'] else ('tudo confere' if r['conferidos'] else 'nada encontrado'),
                       'valor': '', 'badge': 'marque o que alterar' if r['produtos'] else 'sem correção', 'tipo': 'decidir' if r['produtos'] else 'zero',
                       'grupos': [{'id': 'ncm', 'titulo': 'Produtos com NCM no SPED diferente do XML', 'sugestao': 'NCM do XML (marque os que quer alterar)', 'select': True, 'marcar_todos': True,
                                   'linhas': lin}] if lin else []})
    elif pode('ncm'):
        etapas.append({'key': 'ncm', 'titulo': 'NCM × XML das entradas', 'desc': 'precisa dos XMLs de entrada', 'qtd': 'sem XML', 'valor': '', 'badge': 'anexe os XMLs',
                       'tipo': 'sem_xml', 'grupos': []})

    # 1a) produto de uso e consumo lançado como revenda / industrialização → x.556 / x.407 / x.557 (antes do DIFAL)
    if ca_uc is not None:
        lin = [{'sel': i['id'], 'nota': f"NF {_num(i['num'])} · {i['forn']}",
                'det': f"{i['descr']} · CFOP {i['cfop_de']} → {i['cfop_para']} ({i['motivo']}, CST {i['cst']})"
                       + (f" · ICMS creditado R$ {_fm(i['icms'])}: sai em DIFAL e crédito" if i['icms'] > 0.004 else ''),
                'valor': i['valor'], 'marcado': True} for i in ca_uc['itens']]
        r = ca_uc['resumo']
        etapas.append({'key': 'ucons', 'titulo': 'Uso e consumo lançado como revenda', 'desc': 'produto "USO E CONSUMO" com CFOP de revenda ou industrialização → 1.556 / 2.556 (com ST: 1.407 / 2.407)',
                       'qtd': f"{r['itens']} item(ns) · {r['notas']} nota(s)" if r['itens'] else 'nada encontrado',
                       'valor': f"R$ {_fm(r['valor'])}" if r['itens'] else '', 'badge': 'pode corrigir' if r['itens'] else 'sem correção',
                       'tipo': 'auto' if r['itens'] else 'zero',
                       'grupos': [{'id': 'ucons', 'titulo': 'Itens de uso e consumo com CFOP de revenda ou industrialização', 'sugestao': 'CFOP de uso e consumo',
                                   'linhas': lin}] if lin else []})

    # 1c) ICMS-ST na entrada (RICMS/RO, Anexo VI, Parte 2)
    if ca_st is not None:
        rot = {'st': 'produto da ST lançado como tributado', 'cst': 'CFOP de ST com CST tributado: o XML traz ST', 'trib': 'CFOP de ST, mas o XML traz tributado'}
        lin = [{'sel': i['id'], 'nota': f"NF {_num(i['num'])} · {i['forn']}",
                'det': f"{i['descr']} · NCM {i['ncm'] or '—'} · CFOP {i['cfop_de']} → {i['cfop_para']} · CST {i['cst_de']} → {i['cst_para']} · {rot[i['regra']]}: {i['motivo']}"
                       + (f" · crédito de ICMS R$ {_fm(i['icms'])} sai" if i['regra'] in ('st', 'cst') and i['icms'] > 0.004 else '')
                       + ((f" · só muda o CFOP: o crédito de R$ {_fm(i['icms'])} do SPED fica" if i['icms'] > 0.004
                           else ' · só muda o CFOP: o SPED não tem crédito neste item e o sistema não lança') if i['regra'] == 'trib' else ''),
                'valor': i['valor'], 'marcado': True} for i in ca_st['itens']]
        r = ca_st['resumo']
        extra = []
        if r['fora_industria']:
            extra.append(f"{r['fora_industria']} item(ns) de insumo ficaram de fora: empresa industrial (Convênio ICMS 142/2018, cláusula nona)")
        if r['sem_retencao']:
            extra.append(f"{r['sem_retencao']} item(ns) de produto da ST comprados SEM a ST retida pelo fornecedor (ICMS destacado R$ {_fm(r['sem_retencao_icms'])}) "
                         "ficam como estão: o crédito só sai quando a ST já foi paga; sem retenção, a ST é recolhida na entrada (antecipação) ou a venda sai com débito")
        if r['sem_xml'] or r['st_sem_xml']:
            extra.append(f"{r['sem_xml'] + r['st_sem_xml']} item(ns) sem o XML da nota: anexe os XMLs para conferir")
        etapas.append({'key': 'stent', 'titulo': 'ICMS-ST na entrada', 'desc': 'produto da ST de RO (Anexo VI) lançado como tributado, com a ST retida no XML → 1.403 / 1.401 e CST 60, sem crédito; 1.403 com CST tributado → 1.102 quando o XML mostra tributado'
                       + (' · ' + ' · '.join(extra) if extra else ''),
                       'qtd': f"{r['itens']} item(ns) · {r['notas']} nota(s)" if r['itens'] else 'nada encontrado',
                       'valor': f"crédito − R$ {_fm(r['credito'])}" if r['credito'] else '', 'badge': 'pode corrigir' if r['itens'] else 'sem correção',
                       'tipo': 'auto' if r['itens'] else 'zero',
                       'grupos': [{'id': 'stent', 'titulo': 'Itens com CFOP / CST de ST para acertar', 'sugestao': 'CFOP e CST da ST', 'linhas': lin}] if lin else []})

    # 1b) combustível e lubrificante com CFOP de uso e consumo → x.653 (antes do DIFAL)
    if ca_comb is not None:
        lin = [{'sel': i['id'], 'nota': f"NF {_num(i['num'])} · {i['forn']}",
                'det': f"{i['descr']} · NCM {i['ncm'] or '—'} · CFOP {i['cfop_de']} → {i['cfop_para']}"
                       + (' · nota com DIFAL lançado: confira' if i['tem_difal'] else ''),
                'valor': i['valor'], 'marcado': True} for i in ca_comb['itens']]
        lin += [{'sel': f"pend:{n}", 'nota': f"NF {_num(p['num'])} · {p['forn']}", 'det': 'NÃO ALTERAR: ' + p['motivo'], 'valor': None,
                 'marcado': False, 'bloqueado': True} for n, p in enumerate(ca_comb['pendencias'])]
        r = ca_comb['resumo']
        etapas.append({'key': 'comb', 'titulo': 'Combustível × uso e consumo', 'desc': 'combustível e lubrificante com CFOP x.556 / x.407 → x.653 no C170 e no C190',
                       'qtd': f"{r['itens']} item(ns) · {r['notas']} nota(s)" if r['itens'] else ('nada a trocar' if lin else 'nada encontrado'),
                       'valor': f"R$ {_fm(r['valor'])}" if r['itens'] else '', 'badge': 'pode corrigir' if r['itens'] else ('não alterar' if lin else 'sem correção'),
                       'tipo': 'auto' if r['itens'] else 'zero',
                       'grupos': [{'id': 'comb', 'titulo': 'Itens de combustível e lubrificante como uso e consumo', 'sugestao': 'CFOP 1.653 / 2.653',
                                   'linhas': lin}] if lin else []})

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

    # 6b) crédito maçã e pera (RO10000038) — só pelo SPED, não precisa de XML
    ma = cm.analisar_texto(corr)
    lin = []
    for x in ma['docs']:
        if x['status'] == 'confere':
            continue
        nota = f"NF {_num(x['num'])} · {x['fornecedor']}" + (f" · {x['uf']}" if x['uf'] else '')
        frutas = sorted({it['fruta'] for it in x['itens']})
        if x['status'] == 'verificar' or not x['grupos']:
            mot = '; '.join(sorted({it['verificar'] for it in x['itens'] if it['verificar']}))
            lin.append({'sel': _ch_maca(x), 'nota': nota, 'det': f"{' e '.join(frutas)} · NÃO LANÇAR: {mot}", 'valor': 0.0,
                        'marcado': False, 'bloqueado': True})
            continue
        al = ' / '.join(f"{_fm(g['aliq'])}% sobre R$ {_fm(g['base'])}" for g in x['grupos'])
        det = (f"{' e '.join(frutas)} · {al} · " + ('crédito faltando' if x['status'] == 'falta' else f"lançado R$ {_fm(x['lancado'])} → R$ {_fm(x['credito'])}"))
        if x['tem_verificar']:
            det += ' · parte dos itens fica de fora (origem estrangeira ou UF não identificada)'
        lin.append({'sel': _ch_maca(x), 'nota': nota, 'det': det, 'valor': round(x['credito'] - x['lancado'], 2), 'marcado': True})
    n_ok = sum(1 for x in ma['docs'] if x['status'] == 'confere')
    a_lancar = sum(l['valor'] for l in lin if not l.get('bloqueado'))
    n_lin = sum(1 for l in lin if not l.get('bloqueado'))
    etapas.append({'key': 'maca', 'titulo': 'Crédito maçã e pera', 'desc': 'maçã e pera de outro estado com isenção: crédito presumido pela alíquota interestadual · C195 + C197 RO10000038'
                   + (f' · {n_ok} nota(s) já conferem' if n_ok else ''),
                   'qtd': f'{len(lin)} nota(s)' if lin else ('nada a lançar' if n_ok else 'nada encontrado'),
                   'valor': f"+ R$ {_fm(a_lancar)} crédito" if n_lin else '', 'badge': 'pode corrigir' if n_lin else ('não lançar' if lin else 'sem correção'),
                   'tipo': 'auto' if n_lin else 'zero',
                   'grupos': [{'id': 'maca', 'titulo': 'Notas de maçã e pera com crédito faltando ou diferente', 'sugestao': 'lançar o crédito presumido',
                               'linhas': lin}] if lin else []})

    # 7) acumulador 7000
    aa = ad.analisar_texto(corr)
    nomes = {a['cod']: a['nome'] for a in aa['acumuladores']}
    def _nfs(i):
        ns = [_num(n['num']) for n in (i.get('nfs') or [])]
        return ('NF ' + ', '.join(ns[:4]) + (f' (+{len(ns) - 4})' if len(ns) > 4 else '')) if ns else 'NF —'
    lin = [{'sel': i['item'], 'nota': i['descr'] or i['item'], 'det': f"{_nfs(i)} · cód. {i['item']} · NCM {i['ncm'] or '—'} · {i['motivo']}", 'valor': i['valor'],
            'confianca': i['confianca'], 'padrao': i['sugestao'] or '', 'marcado': bool(i['sugestao']), 'nfs': i.get('nfs') or [],
            'busca': ' '.join(_num(n['num']) for n in (i.get('nfs') or []))} for i in aa['itens']]
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

    # 9) unidade × XML (código da unidade do C170 pelo da nota; o 0190/0220 acompanha)
    if xmls:
        ua = ux.analisar_texto(corr, xmls)
        r = ua['resumo']
        lin = [{'sel': u['de'], 'txt': f"{u['de']}{' (' + u['descr_de'] + ')' if u['descr_de'] else ''} → {u['para']}{' (' + u['descr_para'] + ')' if u['descr_para'] else ''}"
                + (' · a nota usa mais de uma unidade para esse código: fica a mais comum' if u['conflito'] else ''), 'qtd': u['itens']} for u in ua['unidades']]
        etapas.append({'key': 'unid', 'titulo': 'Unidade × XML', 'desc': 'unidade do C170 diferente da NF-e: troca o código pelo da nota em todo o arquivo'
                       + (f" · {r['pendencias']} item(ns) com quantidade ou valor diferente ficam como estão" if r['pendencias'] else ''),
                       'qtd': f"{r['itens_unid']} item(ns) · {r['codigos']} unidade(s)" if lin else 'nada encontrado', 'valor': '',
                       'badge': 'pelo XML' if lin else 'sem correção', 'tipo': 'auto' if lin else 'zero',
                       'grupos': [{'id': 'unid', 'titulo': 'Unidades trocadas pela da nota', 'sugestao': 'unidade do XML', 'linhas': lin}] if lin else []})
    else:
        etapas.append({'key': 'unid', 'titulo': 'Unidade × XML', 'desc': 'precisa dos XMLs de entrada', 'qtd': 'sem XML', 'valor': '', 'badge': 'anexe os XMLs',
                       'tipo': 'sem_xml', 'grupos': []})
    if permitidas is None:
        etapas.append({'key': 'estoque', 'titulo': 'Estoque de mercadoria que saiu da ST', 'desc': 'precisa da planilha do estoque: use o botão "Estoque ST"',
                       'qtd': '—', 'valor': '', 'badge': 'botão próprio', 'tipo': 'fora', 'grupos': []})
    etapas = [e for e in etapas if e['key'] == 'estoque' or pode(e['key'])]
    ks = [e['key'] for e in etapas]                       # mesma ordem da aplicação: uso e consumo, combustível, ST da entrada
    if 'stent' in ks and 'comb' in ks and ks.index('stent') < ks.index('comb'):
        etapas.insert(ks.index('comb'), etapas.pop(ks.index('stent')))
    e110 = ls._e110(corr) or {}
    return {'arquivo': os.path.basename(sped), 'xmls': xml_dir, 'xml_lidos': lidos, 'xml_erros': erros,
            'empresa': {'nome': cab.get('nome', ''), 'cnpj': cab.get('cnpj', ''), 'dt_ini': cab.get('dt_ini', ''), 'dt_fin': cab.get('dt_fin', '')},
            'etapas': etapas, 'icms_antes': e110.get('recolher', 0.0),
            'avisos': list(an.get('avisos') or [])[:12]}


# ------------------------------------------------------------------ aplicação
def aplicar(sped, xml_dir, escolhas, permitidas=None):
    esc = escolhas or {}
    liga = lambda k: _pode(permitidas, k) and (esc.get('etapas') or {}).get(k, True) is not False
    texto, enc, corr, rc, xmls, lidos, erros = _base(sped, xml_dir)
    final, resumo, avisos = corr, {}, []
    base_an = _base_analise(corr, xmls, permitidas)                               # o que a análise usou
    # 1·) chave de acesso × XML
    if liga('chave'):
        ek = esc.get('chave') or {}
        ids = [i['id'] for i in ck.analisar_texto(final, xmls)['itens'] if ek.get(i['id'], True) is not False]
        if ids:
            final, r = ck.aplicar_texto(final, ids, xmls)
            resumo['chave'] = {'itens': r['itens'], 'entradas': r['entradas'], 'saidas': r['saidas']}
    # 1·) NCM × XML das entradas (antes da ICMS-ST, que usa o NCM)
    if xmls and liga('ncm'):
        en = esc.get('ncm') or {}
        cods = {i['cod']: (en.get(i['cod']) if isinstance(en.get(i['cod']), str) else i['opcoes'][0]['v'])
                for i in nx.analisar_texto(final, xmls)['itens'] if en.get(i['cod'], True) is not False}
        if cods:
            final, r = nx.aplicar_texto(final, cods, xmls)
            resumo['ncm'] = {'produtos': r['produtos']}
    # 1a) uso e consumo lançado como revenda (antes do DIFAL)
    if liga('ucons'):
        eu = esc.get('ucons') or {}
        ids = [i['id'] for i in uc.analisar_texto(final, xmls)['itens'] if eu.get(i['id'], True) is not False]
        if ids:
            final, r = uc.aplicar_texto(final, ids, xmls)
            resumo['ucons'] = {'itens': r['itens'], 'notas': r['notas'], 'c190': r['c190_divididos']}
            avisos += r.get('avisos') or []
    # 1b) combustível × uso e consumo (antes do DIFAL)
    if liga('comb'):
        ec = esc.get('comb') or {}
        ids = [i['id'] for i in cc.analisar_texto(final, xmls)['itens'] if ec.get(i['id'], True) is not False]
        if ids:
            final, r = cc.aplicar_texto(final, ids, xmls)
            resumo['comb'] = {'itens': r['itens'], 'notas': r['notas'], 'c190': r['c190_divididos']}
            avisos += r.get('avisos') or []
    e116 = esc.get('e116') if isinstance(esc.get('e116'), dict) else None
    # 1c) ICMS-ST na entrada (antes do DIFAL)
    if liga('stent'):
        es_ = esc.get('stent') or {}
        ids = [i['id'] for i in se.analisar_texto(final, xmls)['itens'] if es_.get(i['id'], True) is not False]
        if ids:
            novo, r = se.aplicar_texto(final, ids, xmls, e116)
            if r.get('erro'):
                if 'E116' in r['erro'] and not e116:
                    return None, enc, {'precisa_e116': True, 'etapa': 'ICMS-ST na entrada',
                                       'erro': 'Com a correção a empresa passa a ter ICMS a recolher e o SPED não tem guia (E116). Informe o vencimento e o código de receita da guia.'}
                return None, enc, {'erro': f"ICMS-ST na entrada: {r['erro']}", 'etapa': 'ICMS-ST na entrada'}
            final = novo
            resumo['stent'] = {'itens': r['itens'], 'notas': r['notas'], 'credito': round(r['credito_retirado'], 2), 'st': r['st'], 'cst': r['cst'], 'trib': r['trib']}
            avisos += r.get('avisos') or []
    auto, dec, an, sn = ls.plano_empresa(final, xmls, lidos)
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
        ed = _traduz_ids(esc.get('difal') or {}, base_an, final)
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
            sn_sel = {}
            for a in auto['simples']:
                if ex.get(a['chave'], True) is not False:
                    sn_sel[a['chave']] = {'zerar': a['zerar'], 'c197': True}
            for d in dec:
                if d['tipo'] == 'simples_sem' and _traduz_ids(esc.get('difal') or {}, base_an, final).get(d['id'], True) is not False and (esc.get('simples') or {}).get(d['id'], True) is not False:
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
    # 6b) crédito maçã e pera
    if liga('maca'):
        em = esc.get('maca') or {}
        ma = cm.analisar_texto(final)
        ids = [x['id'] for x in ma['docs'] if x['status'] in ('falta', 'diferente') and x['grupos'] and em.get(_ch_maca(x), True) is not False]
        if ids:
            sel = {'docs': ids}
            if e116:
                sel['e116'] = e116
            novo, r = cm.aplicar_texto(final, sel)
            e = erro_de(r, 'Crédito maçã e pera')
            if e:
                return None, enc, e
            final = novo
            resumo['maca'] = {'notas': r.get('notas', 0), 'credito': r.get('credito', 0.0)}
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
    # 9) unidade × XML
    if xmls and liga('unid'):
        novo, r = ux.aplicar_texto(final, xmls)
        if r.get('itens'):
            final = novo
            resumo['unid'] = {'itens': r['itens']}
            avisos += r.get('avisos') or []
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
    perm = opt('--etapas')
    perm = None if perm is None else {k for k in perm.split(',') if k}
    try:
        if opt('--aplicar'):
            with open(opt('--aplicar'), 'r', encoding='utf-8') as fh:
                esc = json.load(fh)
            final, enc, res = aplicar(sped, opt('--xmls'), esc, perm)
            if final is not None and res.get('ok'):
                fc._grava_sped(opt('--saida'), final, enc)
        else:
            res = analisar(sped, opt('--xmls'), perm)
    except Exception as e:  # pragma: no cover
        import traceback
        res = {'erro': f'Falha ao processar: {e}', 'detalhe': traceback.format_exc()[-1500:]}
    tmp = js + '.parcial'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False)
    os.replace(tmp, js)
    return 0

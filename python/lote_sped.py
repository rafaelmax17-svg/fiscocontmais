# -*- coding: utf-8 -*-
"""⚡ Automatizar correção — Correção do SPED Fiscal em lote (só Admin).

Pega todos os SPED Fiscais (EFD ICMS/IPI) de uma pasta do mês (MM-AAAA) e, para cada cliente, roda o MESMO motor do
corretor manual, na mesma ordem:
  1) "Corrigir SPED" (fiscal_core.corrigir_sped_fiscal: C191, E500, GTIN, CEST, COD_NAT, C197 com campo a mais);
  2) "Uso e consumo · DIFAL e crédito" (difal_ro) — CFOP 1.xxx × 2.xxx pela UF do fornecedor, DIFAL de RO, balcão,
     frete (CT-e) e crédito de ICMS tomado em uso e consumo;
  3) "Crédito Simples Nacional" (simples_ro) — só quando há XML de entrada.
Os XMLs de entrada são procurados em  MM-AAAA\\<CLIENTE>\\NF-e\\Entradas  (pastas e .zip). Sem XML, o DIFAL é calculado
pelo SPED e o crédito do Simples não roda.

O que é certo é aplicado sozinho (correções de validação, CFOP pela UF do fornecedor, crédito do Simples informado no
XML). O que depende de escolha vira "Decisão pendente" com a sugestão já marcada: incluir DIFAL, compra de balcão,
frete, crédito de uso e consumo (zerar ou estornar), Simples sem percentual, Simples sem direito e guia E116.
Notas faltantes NÃO fazem parte do lote (pedido do Rafael). Os originais nunca são alterados.

CLI:
  lote-sped analisar --pasta DIR [--pasta-xmls DIR] --json saida.json
  lote-sped aplicar  --plano plano.json --saida DIR --json saida.json
     plano = {"mes": "09-2026", "arquivos": [{"sped": caminho, "xmls": pasta|null, "decisoes": {id: valor}}]}
"""
import os
import re
import sys
import json
import zipfile
import unicodedata

import fiscal_core as fc
import difal_ro as dr
import simples_ro as sr
import icms_xml as ix
import valor_xml as vx
from xml_entradas import ler_xmls

PULAR_PASTAS = {'NFS-E', 'NF-E', 'CT-E', 'XML', 'PDF', 'RELATÓRIOS', 'RELATORIOS', 'OUTROS CNPJ', 'CORRIGIDOS'}
SUFIXOS = {'LTDA', 'ME', 'EPP', 'EIRELI', 'SA', 'S/A', 'LTDAME', 'LTDAEPP', 'MEI', 'SS', 'SLU'}


# ------------------------------------------------------------------ utilidades
def _norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().upper()
    pal = [p for p in re.split(r'[^A-Z0-9]+', s) if p and p not in SUFIXOS]
    return ''.join(pal)


def _mes_pasta(caminho):
    """'09-2026' se algum nível do caminho for uma pasta MM-AAAA."""
    for parte in reversed(os.path.normpath(caminho).split(os.sep)):
        if re.fullmatch(r'(0[1-9]|1[0-2])-\d{4}', parte or ''):
            return parte
    return None


def _cab(texto):
    c = texto[:600].split('\n', 1)[0].rstrip('\r').split('|')
    if len(c) < 10 or c[1] != '0000':
        return None
    return {'cod_ver': c[2], 'cod_fin': c[3], 'dt_ini': c[4], 'dt_fin': c[5], 'nome': c[6], 'cnpj': c[7] or c[8], 'uf': c[9]}


def _e110(texto):
    for ln in texto.splitlines():
        if ln.startswith('|E110|'):
            c = ln.split('|')
            return {'recolher': dr._n(c[13]) if len(c) > 13 else 0.0, 'sld_transp': dr._n(c[14]) if len(c) > 14 else 0.0}
    return None


def _f(v):
    return dr._f(dr._d(v))


def achar_speds(pasta):
    """SPED Fiscais (.txt com 0000 e Bloco E) dentro da pasta, ignorando as pastas de notas e os arquivos já corrigidos."""
    out = []
    for raiz, dirs, arqs in os.walk(pasta):
        dirs[:] = sorted(d for d in dirs if d.upper() not in PULAR_PASTAS)
        for a in sorted(arqs):
            if not a.lower().endswith('.txt') or re.search(r'corrigid', a, re.I):
                continue
            p = os.path.join(raiz, a)
            try:
                with open(p, 'rb') as fh:
                    ini = fh.read(8).decode('latin-1')
                if not ini.startswith('|0000|'):
                    continue
                texto, _ = fc._ler_sped(p)
            except Exception:
                continue
            if '\n|E001|' in texto or '\n|E110|' in texto:
                out.append(p)
    return out


def pastas_clientes(raiz):
    """{pasta do cliente: pasta NF-e\\Entradas} logo abaixo da pasta do mês."""
    out = {}
    if not raiz or not os.path.isdir(raiz):
        return out
    for d in sorted(os.listdir(raiz)):
        cli = os.path.join(raiz, d)
        if not os.path.isdir(cli):
            continue
        for nfe in ('NF-e', 'NF-E', 'NFe', 'NFE'):
            ent = os.path.join(cli, nfe, 'Entradas')
            if os.path.isdir(ent):
                out[cli] = ent
                break
    return out


def _cnpj_dest_xmls(pasta, limite=8):
    """CNPJs de destinatário/tomador dos primeiros XMLs da pasta (soltos ou dentro de .zip) — para casar cliente × SPED."""
    achados, lidos = set(), 0

    def olha(t):
        m = re.search(r'<dest>.*?<CNPJ>(\d{14})</CNPJ>', t, re.S) or re.search(r'<toma\d?>.*?<CNPJ>(\d{14})</CNPJ>', t, re.S)
        if m:
            achados.add(m.group(1))
    for raiz, _, arqs in os.walk(pasta):
        for a in sorted(arqs):
            p = os.path.join(raiz, a)
            try:
                if a.lower().endswith('.xml'):
                    with open(p, 'rb') as fh:
                        olha(fh.read(60000).decode('utf-8', 'ignore'))
                    lidos += 1
                elif a.lower().endswith('.zip'):
                    with zipfile.ZipFile(p) as z:
                        for n in [n for n in z.namelist() if n.lower().endswith('.xml')][:limite]:
                            olha(z.read(n)[:60000].decode('utf-8', 'ignore'))
                            lidos += 1
            except Exception:
                continue
            if lidos >= limite:
                return achados
    return achados


def achar_xmls(sped, cab, clientes):
    """(pasta de XMLs de entrada, como achou) do cliente desse SPED, ou (None, '').
    Ordem: SPED dentro da pasta do cliente → nome igual → nome parecido confirmado pelo CNPJ dos XMLs → CNPJ dos XMLs."""
    sp = os.path.normcase(os.path.abspath(sped))
    for cli, ent in clientes.items():
        if sp.startswith(os.path.normcase(os.path.abspath(cli)) + os.sep):
            return ent, 'SPED dentro da pasta do cliente'
    alvo = _norm(cab.get('nome'))
    cnpj = re.sub(r'\D', '', cab.get('cnpj') or '')
    cache = {}

    def cnpjs(ent):
        if ent not in cache:
            cache[ent] = _cnpj_dest_xmls(ent)
        return cache[ent]
    if alvo:
        for cli, ent in clientes.items():
            if _norm(os.path.basename(cli)) == alvo and (not cnpjs(ent) or cnpj in cnpjs(ent)):
                return ent, 'nome da pasta'
        parecidos = []
        for cli, ent in clientes.items():
            n = _norm(os.path.basename(cli))
            if n and min(len(n), len(alvo)) >= 6 and (n.startswith(alvo) or alvo.startswith(n)) and cnpj in cnpjs(ent):
                parecidos.append(ent)
        if len(parecidos) == 1:
            return parecidos[0], 'nome da pasta + CNPJ dos XMLs'
    if len(cnpj) == 14:
        achou = [ent for ent in clientes.values() if cnpj in cnpjs(ent)]
        if len(achou) == 1:
            return achou[0], 'CNPJ dos XMLs'
    return None, ''


# ------------------------------------------------------------------ uma empresa
def _base(sped, xml_dir):
    texto, enc = fc._ler_sped(sped)
    corr, rc = fc.corrigir_sped_fiscal(texto, [])
    corr, rc['c197_campos_ajustados'] = fc.ajusta_campos_c197(corr)
    xmls, lidos, erros = ler_xmls([xml_dir]) if xml_dir else ({}, 0, 0)
    return texto, enc, corr, rc, xmls, lidos, erros


def _chave_doc(d):
    return re.sub(r'\D', '', d.get('chave') or '') or f"{d.get('num')}|{d.get('serie')}|{d.get('data')}|{d.get('cnpj')}"


def _brl(v):
    return 'R$ ' + f'{float(dr._d(v)):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def plano_empresa(corr, xmls, lidos):
    """Separa o automático das decisões. Devolve (auto, decisoes, an_difal, an_simples)."""
    an = dr.analisar_texto(corr, xmls)
    sn = sr.analisar_texto(corr, xmls, lidos) if xmls else None
    uf_ro = an['empresa']['uf'] == 'RO'
    auto = {'cfop': [], 'simples': [], 'icms_xml': [], 'valor_xml': []}
    dec = []
    for d in an['docs']:
        nota = f"NF {d['num']} · {d['fornecedor']} ({d['uf_origem'] or 'UF ?'})"
        if d['sugerido_cfop']:
            auto['cfop'].append({'id': d['id'], 'nota': nota, 'de': ', '.join(x['de'] for x in d['correcoes_cfop']),
                                 'para': ', '.join(x['para'] for x in d['correcoes_cfop'])})
        if d['status'] == 'balcao':
            ops = []
            if d['difal_lancado'] > 0:
                ops += [{'v': 'retirar', 'rot': f"Retirar o DIFAL lançado ({_brl(d['difal_lancado'])})"},
                        {'v': 'retirar_cfop', 'rot': 'Retirar o DIFAL e passar o CFOP para 1.xxx'}]
            ops += [{'v': 'cfop1', 'rot': 'Passar o CFOP para 1.xxx'} ] if d['correcoes_cfop'] else []
            ops += [{'v': 'manter', 'rot': 'Deixar como está'}]
            dec.append({'id': f"bal:{d['id']}", 'tipo': 'balcao', 'titulo': 'Compra no balcão em outro estado', 'nota': nota,
                        'detalhe': (d['obs'] or [''])[0], 'valor': d['difal_lancado'],
                        'opcoes': ops, 'padrao': 'retirar' if d['difal_lancado'] > 0 else 'manter'})
            continue
        if (d['status'] in ('faltando', 'divergente') and d['interestadual'] and uf_ro and d['difal_calculado'] > 0
                and d['sit'] not in dr.CANC and d['sit'] not in dr.EXTEMP):
            sug = d['sugerido_difal']
            if d['status'] == 'faltando':
                tit, rot = 'DIFAL faltando', f"Incluir DIFAL de {_brl(d['difal_calculado'])}"
            else:
                tit, rot = 'DIFAL lançado com valor diferente', f"Trocar {_brl(d['difal_lancado'])} por {_brl(d['difal_calculado'])}"
            fonte = 'pelo XML' if d['fonte'] == 'xml' else 'pelo SPED (sem XML)'
            aliqs = ', '.join(f"{str(g['aliq_inter']).replace('.', ',')}%" for g in d['grupos'])
            obs = [o for o in d['obs'] if 'crédito de ICMS tomado' not in o]
            dec.append({'id': f"dif:{d['id']}", 'tipo': 'difal', 'titulo': tit, 'nota': nota,
                        'detalhe': f"Calculado {fonte}, alíquota interestadual {aliqs}." + (' ' + ' '.join(obs) if obs else ''),
                        'valor': d['difal_calculado'] - d['difal_lancado'],
                        'opcoes': [{'v': 'incluir', 'rot': rot}, {'v': 'nao', 'rot': 'Não mexer'}],
                        'padrao': 'incluir' if sug else 'nao'})
    for f in an.get('fretes') or []:
        if f['status'] not in ('faltando', 'divergente') or not uf_ro or f['difal_calculado'] <= 0:
            continue
        dec.append({'id': f"fre:{f['id']}", 'tipo': 'frete', 'titulo': 'DIFAL do frete (CT-e)',
                    'nota': f"CT-e {f['num']} · {f['transportadora']} ({f['uf_ini']} → {f['uf_fim']})",
                    'detalhe': f"Frete de uso e consumo/ativo contratado pela empresa (LC 87/96, art. 12, XIII). " + ' '.join(f['obs']),
                    'valor': f['difal_calculado'] - f['difal_lancado'],
                    'opcoes': [{'v': 'incluir', 'rot': f"Incluir DIFAL de {_brl(f['difal_calculado'])}"}, {'v': 'nao', 'rot': 'Não mexer'}],
                    'padrao': 'incluir' if f['sugerido'] else 'nao'})
    if xmls:      # ICMS creditado acima do destacado no XML: o XML é a prova, entra sozinho
        for x in ix.analisar_texto(corr, xmls)['docs']:
            if x['sugerido']:
                auto['icms_xml'].append({'nota': f"NF {x['num']} · {x['fornecedor']}", 'reducao': x['reducao'], 'status': x['status']})
        # valor do documento e base do ICMS × XML (roda depois do ICMS × XML, sobre o arquivo já ajustado)
        for x in vx.analisar_texto(corr, xmls)['docs']:
            if x['sugerido']:
                auto['valor_xml'].append({'nota': f"NF {x['num']} · {x['fornecedor']}", 'doc': x['doc_dif'], 'dif_doc': x['dif_doc'],
                                          'base': x['base']})
    cr = [x for x in an['creditos']['docs'] if x['sugerido']]
    if cr:
        tot = sum(x['credito'] for x in cr)
        notas = ', '.join(x['num'] for x in cr[:10]) + (f' e mais {len(cr) - 10}' if len(cr) > 10 else '')
        dec.append({'id': 'cred', 'tipo': 'credito', 'titulo': 'Crédito de ICMS tomado em uso e consumo',
                    'nota': f"{len(cr)} nota(s): {notas}",
                    'detalhe': 'Uso e consumo só dá crédito a partir de 01/01/2033 (LC 87/96, art. 33, I).'
                               + (f" Estorno pelo código {an['creditos']['cod_estorno_padrao']}." if an['creditos']['cod_estorno_padrao'] else ''),
                    'valor': tot,
                    'opcoes': [{'v': 'zerar', 'rot': f"Zerar o ICMS nas notas ({_brl(tot)})"},
                               {'v': 'estorno', 'rot': 'Manter as notas e estornar no E111'}, {'v': 'nao', 'rot': 'Não mexer'}],
                    'padrao': 'zerar', 'docs': [x['id'] for x in cr], 'cod_aj': an['creditos']['cod_estorno_padrao']})
    if sn:
        for x in sn['docs']:
            nota = f"NF {x['num']} · {x['fornecedor']}"
            if x['status'] in ('incluir', 'lugar_errado', 'divergente'):
                auto['simples'].append({'chave': _chave_doc(x), 'nota': nota, 'zerar': x['sug_zerar'], 'c197': True,
                                        'credito': x['credito'], 'status': x['status']})
            elif x['status'] == 'sem_aliq':
                dec.append({'id': f"sna:{_chave_doc(x)}", 'tipo': 'simples_aliq', 'titulo': 'Simples Nacional sem percentual na nota',
                            'nota': nota, 'detalhe': f"CSOSN {x['csosn']} dá direito a crédito, mas o fornecedor não informou o percentual. "
                                                     f"Base {_brl(x['base'])}. Informe a alíquota do Anexo do fornecedor ou deixe sem crédito.",
                            'valor': 0.0, 'entrada': 'aliq',
                            'opcoes': [{'v': 'aliq', 'rot': 'Lançar crédito com a alíquota'}, {'v': 'nao', 'rot': 'Sem crédito'}],
                            'padrao': 'nao', 'base': x['base']})
            elif x['status'] == 'sem_direito' and (x['sug_zerar'] or x['c197'] > 0.004):
                v = x['c190_icms'] + x['c197']
                dec.append({'id': f"snd:{_chave_doc(x)}", 'tipo': 'simples_sem', 'titulo': 'Crédito de Simples sem direito',
                            'nota': nota, 'detalhe': f"CSOSN {x['csosn']} não dá crédito (LC 123/2006, art. 23), mas o SPED tem ICMS creditado.",
                            'valor': v,
                            'opcoes': [{'v': 'retirar', 'rot': f"Retirar o crédito ({_brl(v)})"}, {'v': 'nao', 'rot': 'Não mexer'}],
                            'padrao': 'retirar', 'zerar': x['sug_zerar']})
    return auto, dec, an, sn


def _selecoes(an, auto, dec, escolhas):
    """Monta as seleções do difal_ro e do simples_ro a partir do automático + escolhas (ou sugestões)."""
    por_id = {d['id']: d for d in an['docs']}
    docs = {}
    for a in auto['cfop']:
        docs.setdefault(a['id'], {'id': a['id']})['corrigir_cfop'] = True
    fretes, cred, sn_sel = [], {}, {}
    for d in dec:
        esc = escolhas.get(d['id'], d['padrao'])
        val = esc.get('v') if isinstance(esc, dict) else esc
        if d['tipo'] == 'balcao':
            i = int(d['id'].split(':')[1])
            s = docs.setdefault(i, {'id': i})
            s['remover_difal'] = val in ('retirar', 'retirar_cfop')
            s['corrigir_cfop'] = val in ('retirar_cfop', 'cfop1')
        elif d['tipo'] == 'difal' and val == 'incluir':
            i = int(d['id'].split(':')[1])
            s = docs.setdefault(i, {'id': i})
            s['incluir_difal'] = True
            s['grupos'] = [{'tipo': g['tipo'], 'aliq_inter': g['aliq_inter'], 'aliq_interna': g['aliq_interna']} for g in por_id[i]['grupos']]
        elif d['tipo'] == 'frete' and val == 'incluir':
            fretes.append({'id': int(d['id'].split(':')[1]), 'incluir': True, 'grupos': []})
        elif d['tipo'] == 'credito' and val in ('zerar', 'estorno'):
            cred = {'modo': val, 'cod_aj': d.get('cod_aj') or '', 'docs': d['docs']}
        elif d['tipo'] == 'simples_aliq' and val == 'aliq':
            aliq = esc.get('aliq') if isinstance(esc, dict) else None
            if aliq not in (None, ''):
                sn_sel[d['id'].split(':', 1)[1]] = {'zerar': False, 'c197': True, 'aliq': aliq}
        elif d['tipo'] == 'simples_sem' and val == 'retirar':
            sn_sel[d['id'].split(':', 1)[1]] = {'zerar': d.get('zerar', True), 'c197': True}
    for a in auto['simples']:
        sn_sel.setdefault(a['chave'], {'zerar': a['zerar'], 'c197': True})
    e116 = escolhas.get('e116') if isinstance(escolhas.get('e116'), dict) else None
    sel_dif = {'docs': list(docs.values()), 'fretes': fretes, 'creditos': cred}
    if e116:
        sel_dif['e116'] = e116
    return sel_dif, sn_sel, e116


def processar(sped, xml_dir, escolhas=None, mes=None):
    """Analisa e simula (ou aplica, com as escolhas) um SPED. Devolve (texto_final|None, enc, resultado)."""
    escolhas = escolhas or {}
    texto, enc, corr, rc, xmls, lidos, erros = _base(sped, xml_dir)
    cab = _cab(texto) or {}
    auto, dec, an, sn = plano_empresa(corr, xmls, lidos)
    sel_dif, sn_sel, e116 = _selecoes(an, auto, dec, escolhas)
    erro, rd, rs = None, {}, {}
    final = corr
    tem_dif = sel_dif['docs'] or sel_dif['fretes'] or sel_dif['creditos']
    if tem_dif:
        final, rd = dr.aplicar_texto(corr, sel_dif, xmls)
        if rd.get('erro'):
            erro, final = rd['erro'], None
    ri = {}
    if final is not None and xmls and auto.get('icms_xml'):
        ia = ix.analisar_texto(final, xmls)
        ids = [x['id'] for x in ia['docs'] if x['sugerido']]
        if ids:
            sel = {'docs': ids}
            if e116:
                sel['e116'] = e116
            novo, ri = ix.aplicar_texto(final, xmls, sel)
            if ri.get('erro'):
                erro, final = ri['erro'], None
            else:
                final = novo
    rv = {}
    if final is not None and xmls and auto.get('valor_xml'):
        va = vx.analisar_texto(final, xmls)
        ids = [x['id'] for x in va['docs'] if x['sugerido']]
        if ids:
            sel = {'docs': ids}
            if e116:
                sel['e116'] = e116
            novo, rv = vx.aplicar_texto(final, xmls, sel)
            if rv.get('erro'):
                erro, final = rv['erro'], None
            else:
                final = novo
    if final is not None and sn_sel and xmls:
        sn2 = sr.analisar_texto(final, xmls, lidos)
        ids = {_chave_doc(x): x['id'] for x in sn2['docs']}
        docs = [{'id': ids[k], **v} for k, v in sn_sel.items() if k in ids]
        if docs:
            sel = {'docs': docs}
            if e116:
                sel['e116'] = e116
            novo, rs = sr.aplicar_texto(final, xmls, sel)
            if rs.get('erro'):
                erro, final = rs['erro'], None
            else:
                final = novo
    precisa_e116 = bool(erro and 'E116' in erro)
    e116_exist = [{'venc': c[4], 'cod_rec': c[5]} for c in (ln.split('|') for ln in texto.splitlines() if ln.startswith('|E116|')) if len(c) > 5]
    antes = _e110(texto) or {}
    depois = _e110(final) if final is not None else None
    avisos = list(an.get('avisos') or []) + list(rc.get('avisos_c100_e110') or [])
    if final is not None:
        avisos += fc.confere_e110_ajustes(final)
    if sn:
        avisos += [a for a in sn.get('avisos') or [] if a not in avisos]
    for r in (rd, ri, rv, rs):
        avisos += [a for a in r.get('avisos') or [] if a not in avisos]
    mes_sped = f"{cab.get('dt_ini', '')[2:4]}-{cab.get('dt_ini', '')[4:8]}" if len(cab.get('dt_ini', '')) == 8 else ''
    n_corr = sum(rc.get(k) or 0 for k in ('c191_removidos', 'e500_linhas_removidas', 'gtin_limpos', 'cest_limpos', 'cod_nat_corrigidos',
                                           'c197_campos_ajustados', 'c100_totais_corrigidos')) + len(rc.get('registro_0400_criado') or []) \
        + (1 if rc.get('e110_creditos') else 0)
    res = {
        'sped': sped, 'arquivo': os.path.basename(sped), 'xmls': xml_dir, 'xml_lidos': lidos, 'xml_erros': erros,
        'empresa': {'nome': cab.get('nome', ''), 'cnpj': cab.get('cnpj', ''), 'uf': cab.get('uf', ''), 'dt_ini': cab.get('dt_ini', ''),
                    'dt_fin': cab.get('dt_fin', ''), 'cod_fin': cab.get('cod_fin', '')},
        'mes_sped': mes_sped, 'outro_periodo': bool(mes and mes_sped and mes_sped != mes),
        'correcoes': {'c191': rc.get('c191_removidos') or 0, 'e500': rc.get('e500_linhas_removidas') or 0, 'gtin': rc.get('gtin_limpos') or 0,
                      'cest': rc.get('cest_limpos') or 0, 'cod_nat': rc.get('cod_nat_corrigidos') or 0,
                      'r0400': len(rc.get('registro_0400_criado') or []), 'c197': rc.get('c197_campos_ajustados') or 0, 'total': n_corr},
        'auto': auto, 'decisoes': dec,
        'precisa_e116': precisa_e116, 'e116_existente': e116_exist[0] if e116_exist else None,
        'erro': None if precisa_e116 and not e116 else erro,
        'icms_antes': antes.get('recolher', 0.0), 'credor_antes': antes.get('sld_transp', 0.0),
        'icms_depois': (depois or {}).get('recolher'), 'credor_depois': (depois or {}).get('sld_transp'),
        'difal': {'incluido': rd.get('difal_total', 0.0), 'removido': rd.get('difal_removido', 0.0), 'notas': rd.get('difal_incluidos', 0),
                  'fretes': rd.get('fretes_incluidos', 0), 'cfop_notas': rd.get('notas_cfop', 0), 'cred_total': rd.get('cred_total', 0.0),
                  'cred_modo': rd.get('cred_modo', '')},
        'icms_xml': {'notas': ri.get('notas', 0), 'credito_retirado': ri.get('credito_retirado', 0.0)},
        'valor_xml': {'notas': rv.get('notas', 0), 'notas_doc': rv.get('notas_doc', 0), 'notas_base': rv.get('notas_base', 0),
                      'credito_retirado': rv.get('credito_retirado', 0.0)},
        'simples': {'notas': rs.get('notas', 0), 'credito': rs.get('credito_c197', 0.0), 'retirado_c190': rs.get('credito_retirado_c190', 0.0)},
        'avisos': avisos,
        'alterado': final is not None and final != texto,
    }
    return final, enc, res


# ------------------------------------------------------------------ lote
def analisar_pasta(pasta, pasta_xmls=None):
    mes = _mes_pasta(pasta_xmls or pasta) or _mes_pasta(pasta)
    raiz_xml = pasta_xmls or pasta
    clientes = pastas_clientes(raiz_xml)
    speds = achar_speds(pasta)
    out, vistos = [], {}
    for p in speds:
        try:
            texto, _ = fc._ler_sped(p)
            cab = _cab(texto) or {}
            xml_dir, como = achar_xmls(p, cab, clientes)
            _, _, r = processar(p, xml_dir, None, mes)
            r['xmls_como'] = como
        except Exception as e:  # pragma: no cover
            r = {'sped': p, 'arquivo': os.path.basename(p), 'erro': f'Falha ao ler o SPED: {e}', 'decisoes': [], 'auto': {'cfop': [], 'simples': []},
                 'empresa': {}, 'correcoes': {}}
        k = (r.get('empresa', {}).get('cnpj'), r.get('empresa', {}).get('dt_ini'))
        if k[0] and k in vistos:
            r['duplicado'] = vistos[k]
        else:
            vistos[k] = r['arquivo']
        out.append(r)
    if not mes:
        meses = sorted({r.get('mes_sped') for r in out if r.get('mes_sped')})
        mes = meses[0] if len(meses) == 1 else None
    for r in out:
        r['outro_periodo'] = bool(mes and r.get('mes_sped') and r['mes_sped'] != mes)
    usados = {os.path.normcase(r.get('xmls') or '') for r in out}
    sem_sped = [os.path.basename(c) for c, e in clientes.items() if os.path.normcase(e) not in usados]
    return {'pasta': pasta, 'pasta_xmls': raiz_xml, 'mes': mes, 'empresas': out, 'clientes_sem_sped': sem_sped,
            'total': {'speds': len(out), 'decisoes': sum(len(r.get('decisoes') or []) for r in out if not r.get('outro_periodo')),
                      'com_xml': sum(1 for r in out if r.get('xmls'))}}


def aplicar_plano(plano, saida):
    os.makedirs(saida, exist_ok=True)
    mes = plano.get('mes')
    res, gerados = [], []
    for a in plano.get('arquivos') or []:
        try:
            final, enc, r = processar(a['sped'], a.get('xmls'), a.get('decisoes') or {}, mes)
        except Exception as e:  # pragma: no cover
            res.append({'sped': a['sped'], 'arquivo': os.path.basename(a['sped']), 'erro': f'Falha ao corrigir: {e}'})
            continue
        if r.get('precisa_e116') and not (a.get('decisoes') or {}).get('e116'):
            r['erro'] = ('Com a correção a empresa passa a ter ICMS a recolher e o SPED não tem guia (E116). '
                         'Informe o vencimento e o código de receita da guia.')
        if final is not None and not r.get('erro'):
            base = os.path.splitext(os.path.basename(a['sped']))[0]
            nome = f'{base}_corrigido.txt'
            n = 2
            while nome in {os.path.basename(g) for g in gerados}:
                nome, n = f'{base}_corrigido_{n}.txt', n + 1
            destino = os.path.join(saida, nome)
            fc._grava_sped(destino, final, enc)
            r['corrigido'] = destino
            gerados.append(destino)
        res.append(r)
    zipp = None
    if gerados:
        zipp = os.path.join(saida, f"SPEDs_corrigidos_{mes or 'lote'}.zip")
        with zipfile.ZipFile(zipp + '.parcial', 'w', zipfile.ZIP_DEFLATED) as z:
            for g in gerados:
                z.write(g, os.path.basename(g))
        os.replace(zipp + '.parcial', zipp)
    return {'mes': mes, 'empresas': res, 'zip': zipp, 'gerados': len(gerados)}


# ------------------------------------------------------------------ CLI
def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    modo, js = (argv[0] if argv else ''), opt('--json')
    if modo not in ('analisar', 'aplicar') or not js:
        print(__doc__)
        return 1
    dr.carrega_regimes(opt('--regimes'))          # regime (Simples × normal) de cada CNPJ, consultado pelo aplicativo
    try:
        if modo == 'analisar':
            pasta = opt('--pasta')
            if not pasta or not os.path.isdir(pasta):
                res = {'erro': 'Pasta não encontrada.'}
            else:
                res = analisar_pasta(pasta, opt('--pasta-xmls'))
                if not res['empresas']:
                    res['erro'] = 'Nenhum SPED Fiscal (.txt) encontrado nessa pasta.'
        else:
            with open(opt('--plano'), 'r', encoding='utf-8') as fh:
                plano = json.load(fh)
            res = aplicar_plano(plano, opt('--saida'))
    except Exception as e:  # pragma: no cover
        res = {'erro': f'Falha no lote: {e}'}
    tmp = js + '.parcial'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False)
    os.replace(tmp, js)
    return 0


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main_cli(sys.argv[1:]))

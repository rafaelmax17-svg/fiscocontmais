# -*- coding: utf-8 -*-
"""Análise ampla pelo POP — EFD ICMS/IPI (Corretor do SPED Fiscal · só Admin · EM TESTE).

Confere o SPED item a item do "Manual de Processo Operacional Padrão — EFD ICMS IPI" do escritório, pela mesma
numeração do manual. Cada item volta com:
    status  'ok' (conferido, sem apontamento) · 'x' (apontamento) · 'in' (anotar: entra no total por finalidade)
            'av' (faltou documento para conferir) · 'na' (não se aplica a este arquivo)
    resumo, linhas (notas/itens), valor envolvido, o caminho no Domínio copiado do POP e, quando existe, a etapa da
    Análise Inteligente que corrige no SPED.
Os números saem daqui (SPED + XMLs); a IA (Cloud Function analisePop) só lê o texto livre (rodapé do Simples
Nacional, descrição das bonificações), escreve a explicação de cada apontamento e o Word de observação ao cliente.
Nada aqui altera o SPED.

Entradas extras (JSON, opcional): {"pagos": [...DAREs pagos do mês da IE...], "fisconforme": [...notificações...],
"consultou_pagos": bool, "consultou_fisconforme": bool}.
"""
import json
import re
import sys
from collections import defaultdict

import difal_ro as dr

CANC = {'02', '03', '04', '05'}
TRIB = {'1102', '2102', '1152', '2152', '1202', '2202', '1101', '2101'}
ST = {'1403', '2403', '1409', '2409', '1411', '2411', '1401', '2401'}
PAR_ST = {'1102': '1403', '2102': '2403', '1152': '1409', '2152': '2409', '1202': '1411', '2202': '2411', '1101': '1401', '2101': '2401'}
PAR_TRIB = {v: k for k, v in PAR_ST.items()}
DESP = {'1556', '2556', '1407', '2407'}
IMOB = {'1551', '2551', '1406', '2406'}
COMB = {'1652', '2652', '1653', '2653', '1662', '2662', '1651', '2651'}
# combustíveis da tributação monofásica do ICMS (LC 192/2022; Convênios ICMS 199/2022 e 15/2023): gasolina, diesel, GLP e
# biodiesel. Etanol hidratado e lubrificantes não são monofásicos (seguem na ST, CST 60).
NCM_COMB = ('27101259', '27101251', '27101921', '27101922', '27111910', '27111100', '38260000')
TRIB_SAI = {'5102', '6102', '5101', '6101', '5108', '6108'}
ST_SAI = {'5405', '5403', '6403', '6404', '5401', '6401', '5402', '6402'}

# caminhos do Domínio, copiados do POP (31/10/2026)
CAM = {
    '1.2': 'Pedir ao cliente a fatura de energia legível (Lucro Real: obrigatório). Lançamento: Movimento > Entradas > Novo > Espécie 288 > Acumulador 7015 > CFOP 1.253 (POP 1.27).',
    '1.9': 'Fiscontech: Notas Fiscais > Documentos Fiscais > NF-e e CT-e de entrada > período > nº das notas > Exportar. Salvar em Drive > Regime > Empresa > Relatório > Ano > Mês.',
    '1.11': 'Domínio: Relatórios > Acompanhamentos > Notas não lançadas > período > Espécie 36 e 114. Nota faltante e não inutilizada: confirmar com o cliente (contingência: transmitir ou inutilizar).',
    '1.12': 'Domínio: Utilitários > Exclusão > período > Eliminar notas de Entradas > Código (o código do Domínio, não o nº da NF-e).',
    '1.13': 'Domínio: Utilitários > Alterar notas ou outros lançamentos > filtrar o nº do documento. Não escriturada: verificar desconhecimento da operação.',
    '1.15': 'Portal do Contribuinte (SEFIN) > Fisconforme. Ausência de saída / diferença de transporte de crédito: retificar o SPED anterior. Ausência de registro de entrada: escriturar como extemporânea. Demais: coordenadora.',
    '1.28': 'Domínio: Movimentos > Outros > Impostos Lançados > Estadual > data = vencimento do DARE > Ajuste 41 > Observação "ICMS Antecipado" > Ajuste RO020003 > Complementar: nº do lançamento do DARE, parcela 00, receita 1658.',
    '2.2': 'Domínio: Utilitários > Alterar Movimento de Produtos das Notas > Entrada > acumulador > ordenar por NCM > Alterar CFOP / CST. Tributado: 6000 (1.102/2.102), 6506 (1.152/2.152), 6700 (1.202/2.202). ST: 6001 (1.403/2.403), 6507 (1.409/2.409), 6701 (1.411/2.411). Anotar código do produto e nº da NF para o cliente.',
    '2.3': 'Domínio: Utilitários > Alterar Movimento de Produtos das Notas > Saída > 5000/5001 > ordenar por NCM. ST vendido como tributado: orientar o cliente. Tributado vendido como ST: coordenadora (denúncia espontânea / NF complementar).',
    '2.13': 'Domínio: Utilitários > Alterar Notas e Outros Lançamentos > Saídas. Compra 6000 → 5700 · 6001 → 5701 · 6007/7016 → 5703 · despesas 7000 → 5702. Erro de emissão: pedir Carta de Correção.',
    '2.15': 'Total do Domínio – Energia – NFS-e tomadas – CT-e – notas do mês anterior – antecipadas – extemporâneas + notas que ficaram para o próximo mês = total de entradas do Fiscontech.',
    '2.17': 'Conferir o CT-e e a NF referenciada (o frete acompanha a nota). Se necessário, pedir ao cliente que dê entrada.',
    '2.18': 'Domínio: Movimentos > Entradas > Listagem > nº do CT-e > Acumulador 6510 (revenda: CST 00 com crédito só se destacado) ou 7027 (uso e consumo: CST 90, sem crédito).',
    '2.20': 'Domínio: Utilitários > Alterar Impostos nas Notas > Alterar Dados de ICMS no movimento > Entradas > acumulador > CST, base "nenhuma" e alíquota 0,00 onde não há crédito.',
    '2.22': 'Domínio: Utilitários > Alterar Impostos nas Notas > Alterar Dados de ICMS no movimento > Entradas > acumulador > Informar dados para alteração > CST.',
    '2.34': 'Mesmo caminho do CST: origem 1 → 2 e 6 → 7; demais origens ficam como no documento.',
    '2.38': 'Domínio: Relatórios > Acompanhamentos > Entradas > acumulador 7000 > Utilitários > Alterar notas e outros lançamentos > Entradas > Acumulador/CFOP.',
    '2.42': 'Domínio: Utilitários > Alterar notas e outros lançamentos > Entradas. Revenda: 6500 · Uso e consumo: 7026 (CFOP 1.910/2.910). Uso e consumo interestadual: recolher DIFAL.',
    '2.43': 'Domínio: Movimentos > Entradas > Listagem > SIGLA DIFAL: base, alíquota e valor. Cálculo: (valor – ICMS destacado) / 0,805 × 19,5% – ICMS destacado. Conferir o valor gravado.',
    '2.46': 'Domínio: Relatórios > Acompanhamentos > Entradas > 6000/6700/6510/6506 > abrir a DANFE: só há crédito se destacado na nota.',
    '2.47': 'Domínio: Movimentos > Entradas > Listagem > zerar a SIGLA ICMS > aba Estadual > ICMS Simples Nacional: base dos tributados, alíquota do rodapé e valor do crédito > Gravar.',
    '2.61': 'Domínio: Relatórios > Informativos > Estaduais GIAM: saldo credor do período anterior × saldo a transportar do recibo do SPED da última competência.',
}

TIT = {
    '1.2': 'Fatura de energia elétrica', '1.8': 'Conferência minuciosa dos documentos (XML × SPED)',
    '1.9': 'Notas do mês que ficaram para o próximo', '1.11': 'Numeração faltante (emissão própria)',
    '1.12': 'Nota de entrada cancelada escriturada', '1.13': 'Notas de meses anteriores escrituradas neste mês',
    '1.14': 'Codificação e descrição dos produtos (0200 × XML)', '1.15': 'Fisconforme',
    '1.28': 'DARE 1658 pago × ajuste RO020003 (ICMS antecipado)',
    '2.2': 'Revenda ST × tributado (Anexo VI)', '2.3': 'Saídas: produto ST × tributado e base do 5000',
    '2.13': 'Devoluções × compra de origem', '2.15': 'Total de entradas por finalidade',
    '2.17': 'CT-e sem entrada', '2.18': 'Frete: custo × despesa e crédito', '2.20': 'Sem crédito: uso e consumo, imobilizado e ST',
    '2.22': 'CST pela natureza da operação', '2.29': 'Combustível (CST 61)', '2.34': 'Origem 1 → 2 e 6 → 7',
    '2.38': 'Despesas no 7000 / outras entradas', '2.42': 'Bonificações: revenda × uso e consumo',
    '2.43': 'DIFAL de uso e consumo e imobilizado', '2.46': 'Crédito só com destaque na nota',
    '2.47': 'Crédito de fornecedor do Simples Nacional', '2.61': 'Transporte de crédito do mês anterior',
    '3.4': 'Validação do PVA', '3.6': 'Conferência do SPED gerado (apuração)',
}
ETAPA = lambda n: int(n.split('.')[0])


def _so(s):
    return re.sub(r'\D', '', s or '')


def _n(s):
    try:
        return float((s or '0').replace(',', '.'))
    except ValueError:
        return 0.0


def _ord(d):
    """ddmmaaaa (SPED) ou aaaa-mm-dd (XML) -> aaaammdd"""
    d = d or ''
    if re.fullmatch(r'\d{8}', d):
        return d[4:] + d[2:4] + d[:2]
    if re.match(r'\d{4}-\d{2}-\d{2}', d):
        return d[:4] + d[5:7] + d[8:10]
    return ''


def _brl(v):
    s = f'{abs(v):,.2f}'.replace(',', '#').replace('.', ',').replace('#', '.')
    return ('-' if v < 0 else '') + 'R$ ' + s


def _br(o):
    return f'{o[6:8]}/{o[4:6]}/{o[:4]}' if len(o) == 8 else ''


def _fmt_cfop(c):
    return f'{c[0]}.{c[1:]}' if len(c or '') == 4 else (c or '')


def _item(n, status, resumo, linhas=None, valor=0.0, corretor=None, extra=None, cols=None):
    it = {'n': n, 'etapa': ETAPA(n), 'titulo': TIT.get(n, n), 'status': status, 'resumo': resumo, 'linhas': (linhas or [])[:300],
          'total_linhas': len(linhas or []), 'valor': round(valor or 0.0, 2), 'caminho': CAM.get(n, ''), 'corretor': corretor,
          'cols': cols or ['nota', 'data', 'forn', 'prod', 'obs', 'valor']}
    if extra:
        it.update(extra)
    return it


# ------------------------------------------------------------------ leitura
def _ler(sped):
    import fiscal_core as fc
    texto, _ = fc._ler_sped(sped)
    linhas, _, _ = dr.dividir(texto)
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), None)
    if fim is not None:
        linhas = linhas[:fim + 1]
    return texto, linhas


def _cab0000(linhas):
    for l in linhas[:3]:
        c = l.lstrip('\ufeff').split('|')
        if len(c) > 10 and c[1] == '0000':
            if any(x.startswith(('|0110|', '|0111|', '|0140|')) for x in linhas[:12]):
                raise ValueError('Este arquivo é uma EFD-Contribuições. A análise pelo POP é do SPED Fiscal (EFD ICMS/IPI).')
            return {'dt_ini': c[4], 'dt_fin': c[5], 'nome': c[6], 'cnpj': c[7], 'uf': c[9], 'ie': c[10]}
    return {}


def _p200(linhas):
    out = {}
    for l in linhas:
        if l.startswith('|0200|'):
            c = l.split('|')
            if len(c) > 8:
                out[c[2]] = {'descr': c[3], 'ncm': _so(c[8]), 'tipo': c[7], 'cest': c[13] if len(c) > 13 else ''}
    return out


def _registros(linhas, reg):
    return [l.split('|') for l in linhas if l.startswith(f'|{reg}|')]


def _eventos_cancel(xml_dir):
    """chaves com evento de cancelamento (110111) entre os arquivos anexados"""
    if not xml_dir:
        return set()
    from fiscal_core import coletar_xmls, _read_text
    out = set()
    for p in coletar_xmls([xml_dir] if isinstance(xml_dir, str) else xml_dir):
        try:
            t = _read_text(p)
        except Exception:
            continue
        if '110111' in t and '<tpEvento>110111</tpEvento>' in t.replace(' ', ''):
            m = re.search(r'<chNFe>(\d{44})</chNFe>', t)
            if m:
                out.add(m.group(1))
        elif '<cStat>101</cStat>' in t or '<cStat>135</cStat>' in t and 'Cancelamento' in t:
            m = re.search(r'<chNFe>(\d{44})</chNFe>', t)
            if m and '<procEventoNFe' in t:
                out.add(m.group(1))
    return out


# ------------------------------------------------------------------ conferências
def analisar(sped, xml_dir=None, sped_ant=None, extra=None):
    from xml_entradas import ler_xmls
    import st_entrada_ro as se
    extra = extra or {}
    texto, linhas = _ler(sped)
    cab = _cab0000(linhas)
    cnpj = _so(cab.get('cnpj'))
    ini, fim = _ord(cab.get('dt_ini')), _ord(cab.get('dt_fin'))
    _, part, _, docs, e110, _ = dr._estrutura(linhas)
    ctes = dr._estrutura_d(linhas)
    p200 = _p200(linhas)
    xmls, lidos, _ = ler_xmls([xml_dir]) if xml_dir else ({}, 0, 0)
    tem_xml = bool(xmls)
    forn = lambda d: (part.get(d['part']) or {}).get('nome', d['part'])
    no_sped = {_so(d['chave']) for d in docs if d['chave']} | {_so(c['chave']) for c in ctes if c['chave']}
    itens = []

    def x_de(d):
        return xmls.get(_so(d['chave'])) if d.get('chave') else None

    ent = [d for d in docs if d['oper'] == '0' and d['sit'] not in CANC]
    sai = [d for d in docs if d['oper'] == '1']
    x_ent = [x for x in xmls.values() if x.get('tipo') == 'nfe' and _so(x.get('dest_doc')) == cnpj]
    x_sai = [x for x in xmls.values() if x.get('tipo') == 'nfe' and _so(x.get('emit_cnpj')) == cnpj]
    x_cte = [x for x in xmls.values() if x.get('tipo') == 'cte']

    # 1.2 energia elétrica
    c500 = [c for c in _registros(linhas, 'C500') if len(c) > 2 and c[2] == '0']
    nf3e = [d for d in docs if d['mod'] == '66' and d['oper'] == '0']
    q = len(c500) + len(nf3e)
    if q:
        itens.append(_item('1.2', 'ok', f'{q} conta(s) de energia elétrica no SPED'))
    else:
        itens.append(_item('1.2', 'av', 'nenhuma conta de energia elétrica no SPED (C500 ou NF3-e modelo 66): pedir a fatura ao cliente, se ele tiver'))

    # 1.9 notas do período que ficaram fora do SPED (vão para o próximo mês) · 1.13 notas de meses anteriores
    if tem_xml and x_ent:
        fora = sorted((x for x in x_ent if ini <= _ord(x['dt']) <= fim and _so(x['chave']) not in no_sped and x.get('mod') in ('55', '')),
                      key=lambda x: _ord(x['dt']))
        lin = [{'nota': x['num'], 'data': _br(_ord(x['dt'])), 'forn': x.get('emit_nome', ''), 'obs': 'no XML e fora do SPED', 'valor': x['vnf'],
                'chave': x['chave']} for x in fora]
        v = sum(x['vnf'] for x in fora)
        itens.append(_item('1.9', 'in' if fora else 'ok',
                           f"{len(fora)} nota(s) de entrada emitidas no período e fora do SPED · {_brl(v)} — anotar para o total por finalidade e salvar o relatório" if fora else 'todas as NF-e de entrada do período estão no SPED', lin, v))
    else:
        fora, v = [], 0.0
        itens.append(_item('1.9', 'av', 'anexe os XMLs de entrada do período (DF-e) para achar as notas que ficaram para o próximo mês'
                           + (' — os XMLs anexados não são de entrada desta empresa' if tem_xml else '')))
    ant = [d for d in ent if d['mod'] == '55' and _ord(d['dt']) and _ord(d['dt']) < ini]
    ext = [d for d in ent if d['sit'] in ('01', '07')]
    lin = [{'nota': d['num'], 'data': _br(_ord(d['dt'])), 'forn': forn(d), 'obs': 'extemporânea' if d['sit'] in ('01', '07') else 'emitida em mês anterior',
            'valor': _vl_doc(linhas, d)} for d in sorted(ant + [e for e in ext if e not in ant], key=lambda d: _ord(d['dt']))]
    v_ant = sum(r['valor'] for r in lin)
    itens.append(_item('1.13', 'in' if lin else 'ok', f'{len(lin)} nota(s) de meses anteriores ou extemporâneas escrituradas neste mês — anotar para o total por finalidade'
                       if lin else 'nenhuma nota de mês anterior escriturada neste período', lin, v_ant))

    # 1.11 numeração faltante (emissão própria, por modelo e série; cancelada/inutilizada contam como presentes)
    seq = defaultdict(set)
    for d in docs:
        if d['oper'] == '1' and d['emit'] == '0' and d['mod'] in ('55', '65') and d['num'].isdigit():
            seq[(d['mod'], d['serie'])].add(int(d['num']))
    lin = []
    for (mod, ser), nums in seq.items():
        if len(nums) < 2:
            continue
        falt = [n for n in range(min(nums), max(nums) + 1) if n not in nums]
        for a, b in _faixas(falt):
            lin.append({'nota': f'{a}' if a == b else f'{a} a {b}', 'obs': f"{'NF-e' if mod == '55' else 'NFC-e'} série {ser} · {b - a + 1} número(s) sem C100 (nem cancelada/inutilizada)"})
    itens.append(_item('1.11', 'x' if lin else 'ok', f'{sum(_qtd(r["nota"]) for r in lin)} número(s) faltando na emissão própria — conferir inutilização no portal'
                       if lin else 'sem buraco na numeração da emissão própria', lin, cols=['nota', 'obs']))

    # 1.12 nota cancelada escriturada como normal
    canc = _eventos_cancel(xml_dir) if tem_xml else set()
    lin = []
    for d in docs:
        if d['chave'] and _so(d['chave']) in canc and d['sit'] not in CANC:
            lin.append({'nota': d['num'], 'data': _br(_ord(d['dt'])), 'forn': forn(d) if d['oper'] == '0' else 'emissão própria',
                        'obs': ('entrada' if d['oper'] == '0' else 'saída') + ' cancelada e escriturada como normal', 'valor': _vl_doc(linhas, d)})
    if tem_xml:
        itens.append(_item('1.12', 'x' if lin else 'ok', f'{len(lin)} nota(s) cancelada(s) escrituradas como normais — excluir'
                           if lin else (f'{len(canc)} evento(s) de cancelamento conferidos' if canc else 'nenhum evento de cancelamento entre os XMLs'), lin,
                           sum(r['valor'] for r in lin)))
    else:
        itens.append(_item('1.12', 'av', 'anexe os XMLs (com os eventos de cancelamento) para conferir'))

    # 1.15 Fisconforme
    itens.append(_fisconforme(extra))

    # 1.28 DARE 1658 pago × E111 RO020003
    itens.append(_antecipado(linhas, extra, ini, fim))

    # 2.2 revenda ST × tributado (entradas) — Anexo VI do RICMS/RO pelo NCM/CEST do 0200; XML diz se houve retenção
    grupo = defaultdict(lambda: {'n': 0, 'v': 0.0, 'notas': set()})
    for d in ent:
        x = x_de(d)
        par = _par(d, x) if x else {}
        for c in d['c170']:
            if c['cfop'] not in TRIB and c['cfop'] not in ST:
                continue
            p = p200.get(c['item']) or {}
            r, mot = se.produto_st(p.get('ncm'), p.get('cest'))
            it = par.get(c['i'])
            ret = se._xml_st(it) if it else None
            # como na etapa ICMS-ST na entrada: só é ST de fato quando o XML mostra a retenção
            if c['cfop'] in TRIB and r and ret is True:
                k = (c['item'], c['cfop'], 'st')
            elif c['cfop'] in ST and not r and ret is False:
                k = (c['item'], c['cfop'], 'trib')
            else:
                continue
            g = grupo[k]
            g['n'] += 1
            g['v'] += c['vl']
            g['notas'].add(d['num'])
            g['mot'] = mot
            g['ret'] = ret
    lin = []
    for (cod, cfop, tipo), g in sorted(grupo.items(), key=lambda kv: -kv[1]['v']):
        p = p200.get(cod) or {}
        para = PAR_ST.get(cfop) if tipo == 'st' else PAR_TRIB.get(cfop)
        obs = (f"produto da ST ({g['mot']}) com o ICMS-ST retido no XML, lançado no CFOP de tributado"
               if tipo == 'st' else 'produto fora do Anexo VI, sem ICMS-ST no XML, lançado no CFOP de ST')
        lin.append({'cod': cod, 'prod': p.get('descr', cod), 'ncm': p.get('ncm', ''), 'de': _fmt_cfop(cfop), 'para': _fmt_cfop(para or ''),
                    'nota': ', '.join(sorted(g['notas'], key=lambda s: int(s) if s.isdigit() else 0)[:6]) + (f" (+{len(g['notas']) - 6})" if len(g['notas']) > 6 else ''),
                    'obs': obs, 'valor': round(g['v'], 2)})
    nst = sum(1 for k in grupo if k[2] == 'st')
    itens.append(_item('2.2', 'x' if lin else 'ok', (f'{nst} produto(s) da ST em CFOP de tributado · {len(lin) - nst} tributado(s) em CFOP de ST')
                       if lin else 'acumuladores de revenda coerentes com o Anexo VI', lin, sum(r['valor'] for r in lin), corretor='stent',
                       cols=['prod', 'ncm', 'de', 'para', 'nota', 'obs', 'valor']))

    # 2.3 saídas: produto ST × tributado (XML das notas emitidas) e base do 5000
    itens.append(_saidas(x_sai, linhas, docs, se, tem_xml))

    # 2.13 devoluções × compra de origem
    itens.append(_devolucoes(x_sai, docs, tem_xml))

    # 2.15 total por finalidade (entradas): SPED – energia – CT-e – mês anterior – extemporâneas + ficaram = XML do período
    if tem_xml and x_ent:
        tot_sped = sum(_vl_doc(linhas, d) for d in ent if d['mod'] == '55')
        tot_xml = sum(x['vnf'] for x in x_ent if ini <= _ord(x['dt']) <= fim and x.get('mod') in ('55', ''))
        calc = tot_sped - v_ant + v
        # notas do período que estão no SPED e cujo XML não veio entre os anexados (não é diferença: falta o XML)
        sem_x = [d for d in ent if d['mod'] == '55' and _ord(d['dt']) >= ini and d['chave'] and _so(d['chave']) not in xmls
                 and _so(d['chave'])[6:20] != cnpj]
        v_sx = round(sum(_vl_doc(linhas, d) for d in sem_x), 2)
        # mesma nota com valor diferente no SPED e no XML (item 1.8)
        dv = [(d, _vl_doc(linhas, d) - xmls[_so(d['chave'])]['vnf']) for d in ent if d['mod'] == '55' and d['chave'] and _so(d['chave']) in xmls
              and ini <= _ord(xmls[_so(d['chave'])]['dt']) <= fim and abs(_vl_doc(linhas, d) - xmls[_so(d['chave'])]['vnf']) > 0.009]
        v_dv = round(sum(v_ for _, v_ in dv), 2)
        dif = round(calc - tot_xml - v_sx - v_dv, 2)
        lin = [{'obs': 'NF-e de entrada no SPED (modelo 55)', 'valor': round(tot_sped, 2)},
               {'obs': '– notas de meses anteriores / extemporâneas (1.13)', 'valor': -round(v_ant, 2)},
               {'obs': '+ notas do período que ficaram para o próximo mês (1.9)', 'valor': round(v, 2)},
               {'obs': '= total calculado', 'valor': round(calc, 2)},
               {'obs': 'NF-e de entrada do período nos XMLs anexados (DF-e)', 'valor': round(tot_xml, 2)}]
        if sem_x:
            lin.append({'obs': f'+ {len(sem_x)} nota(s) do período no SPED sem o XML entre os anexados', 'valor': v_sx})
        if dv:
            lin.append({'obs': f"+ {len(dv)} nota(s) com valor no SPED diferente do XML (NF {', '.join(d['num'] for d, _ in dv[:8])}{'…' if len(dv) > 8 else ''})", 'valor': v_dv})
        lin.append({'obs': 'diferença sem explicação', 'valor': dif})
        if abs(dif) < 0.05 and dv:
            st, rs = 'x', f'a diferença de {_brl(v_dv)} vem de {len(dv)} nota(s) lançadas com valor diferente do XML (ver 1.8)'
        elif abs(dif) < 0.05:
            st, rs = ('av', f'bate, mas {len(sem_x)} nota(s) do SPED ({_brl(v_sx)}) não têm o XML entre os anexados — anexe o lote completo do DF-e para confirmar') if sem_x \
                else ('ok', 'o total por finalidade bate com os XMLs do período')
        else:
            st, rs = 'x', f'diferença de {_brl(dif)} entre o total calculado e os XMLs do período'
        itens.append(_item('2.15', st, rs, lin, abs(dif), cols=['obs', 'valor']))
    else:
        itens.append(_item('2.15', 'av', 'anexe os XMLs de entrada do período para bater o total por finalidade'
                           + (' — os XMLs anexados não são de entrada desta empresa' if tem_xml else '')))

    # 2.17 CT-e sem entrada · 2.18 frete custo × despesa
    a, b = _fretes(x_cte, ctes, docs, cnpj, no_sped, part, tem_xml)
    itens += [a, b]

    # 2.22–2.33 CST pela natureza · 2.29 combustível · 2.34 origem
    itens += _cst(ent, x_de, p200, se, tem_xml, forn)

    # 2.42 bonificações
    lin = []
    for d in ent:
        x = x_de(d)
        par = _par(d, x) if x else {}
        for c in d['c170']:
            if c['cfop'] in ('1910', '2910'):
                it = par.get(c['i']) or {}
                lin.append({'id': f"{d['i']}:{c['num']}", 'nota': d['num'], 'data': _br(_ord(d['dt'])), 'forn': forn(d), 'prod': it.get('xprod') or c['descr'] or (p200.get(c['item']) or {}).get('descr', ''),
                            'ncm': it.get('ncm') or (p200.get(c['item']) or {}).get('ncm', ''), 'de': _fmt_cfop(c['cfop']), 'obs': 'a classificar', 'valor': round(c['vl'], 2),
                            'inter': c['cfop'].startswith('2')})
    itens.append(_item('2.42', 'in' if lin else 'ok', f'{len(lin)} item(ns) de bonificação para classificar (revenda 6500 × uso e consumo 7026)' if lin else 'nenhuma bonificação no período',
                       lin, sum(r['valor'] for r in lin), cols=['nota', 'forn', 'prod', 'ncm', 'de', 'obs', 'valor']))

    # 2.47 crédito do Simples Nacional (pCredSN ou rodapé da DANFE)
    itens.append(_simples(ent, x_de, forn, tem_xml))

    # 2.61 transporte de crédito
    itens.append(_transporte(e110, sped_ant))

    # Etapa 3 · apuração (E110/E111/E300/G110/C197/LMC)
    itens.append(_apuracao(linhas, e110))

    return {'cab': {k: cab.get(k) for k in ('dt_ini', 'dt_fin', 'nome', 'cnpj', 'ie', 'uf')}, 'periodo': f'{ini[4:6]}/{ini[:4]}' if ini else '',
            'xml_lidos': lidos, 'tem_xml': tem_xml, 'n_sai_xml': len(x_sai), 'n_ent_xml': len(x_ent), 'n_cte_xml': len(x_cte),
            'itens': itens, 'textos_simples': [], 'tem_sped_ant': bool(sped_ant)}


def _qtd(s):
    m = re.match(r'(\d+) a (\d+)', s)
    return int(m.group(2)) - int(m.group(1)) + 1 if m else 1


def _faixas(nums):
    out, a, b = [], None, None
    for n in nums:
        if a is None:
            a = b = n
        elif n == b + 1:
            b = n
        else:
            out.append((a, b))
            a = b = n
    if a is not None:
        out.append((a, b))
    return out


def _vl_doc(linhas, d):
    c = linhas[d['i']].split('|')
    return _n(c[12]) if len(c) > 12 else 0.0


def _par(d, x):
    import icms_xml as ix
    try:
        return ix._casar(d, x)[0]
    except Exception:
        return {}


def _fisconforme(extra):
    if not extra.get('consultou_fisconforme'):
        return _item('1.15', 'av', 'sem a consulta do Fisconforme desta inscrição na nuvem (módulo Fisconforme)')
    lin, bloq = [], 0
    for n in extra.get('fisconforme') or []:
        if (n.get('status') or '') == 'fora':
            continue
        d = (n.get('desc') or '').upper()
        import unicodedata
        d = ''.join(ch for ch in unicodedata.normalize('NFD', d) if unicodedata.category(ch) != 'Mn')
        if re.search(r'AUSENCIA DE SAIDA|OMISSAO DE SAIDA', d):
            acao, b = 'retificar o SPED anterior e corrigir o crédito transportado', True
        elif re.search(r'TRANSPORTE DE CREDITO|SALDO CREDOR', d):
            acao, b = 'retificar o SPED anterior: diferença no transporte de crédito', True
        elif re.search(r'(AUSENCIA|FALTA|OMISSAO).*(REGISTRO|ESCRITURA).*ENTRADA|ENTRADA.*NAO ESCRITURAD', d):
            acao, b = 'dar entrada no SPED desta competência como extemporânea', True
        elif re.search(r'MANIFESTACAO|DESTAQUE|LMC|RESSARCIMENTO', d):
            acao, b = 'não impede o SPED', False
        else:
            acao, b = 'pedir orientação à coordenadora', None
        bloq += 1 if b else 0
        lin.append({'nota': n.get('codigo', ''), 'data': (n.get('periodo') or ''), 'obs': n.get('desc', ''), 'para': acao, 'bloq': b, 'status_portal': n.get('status', '')})
    if not lin:
        return _item('1.15', 'ok', 'nenhuma notificação pendente no Fisconforme')
    return _item('1.15', 'x' if bloq else 'in', (f'{bloq} notificação(ões) precisam ser corrigidas antes do SPED · {len(lin)} no total' if bloq
                                                  else f'{len(lin)} notificação(ões) que não impedem o SPED'), lin, cols=['nota', 'data', 'obs', 'para'])


def _antecipado(linhas, extra, ini, fim):
    aj = [c for c in _registros(linhas, 'E111') if len(c) > 4 and c[2].upper() == 'RO020003']
    v_aj = round(sum(_n(c[4]) for c in aj), 2)
    if not extra.get('consultou_pagos'):
        return _item('1.28', 'av', (f'ajuste RO020003 no SPED: {_brl(v_aj)}' if aj else 'sem ajuste RO020003 no SPED')
                     + ' — consulte os DAREs pagos do mês no Débitos e DARE (aba Pagos) para conferir')
    pg = [p for p in extra.get('pagos') or [] if str(p.get('rec')) == '1658' and ini <= _ord(_iso(p.get('venc'))) <= fim]
    v_pg = round(sum(float(p.get('valorN') or 0) for p in pg), 2)
    lin = [{'nota': p.get('nr', ''), 'data': p.get('venc', ''), 'obs': f"parcela {p.get('parc', '00')} · pago em {p.get('pagoEm', '')}", 'valor': float(p.get('valorN') or 0)} for p in pg]
    lin.append({'nota': 'E111', 'obs': 'ajuste RO020003 – Crédito Fiscal Antecipado no SPED', 'valor': v_aj})
    dif = round(v_pg - v_aj, 2)
    if not pg and not aj:
        return _item('1.28', 'ok', 'nenhum DARE 1658 pago com vencimento no período e nenhum ajuste RO020003')
    st = 'ok' if abs(dif) < 0.05 else 'x'
    res = ('DAREs 1658 pagos batem com o ajuste RO020003' if st == 'ok' else
           (f'{len(pg)} DARE(s) 1658 pago(s) · {_brl(v_pg)} × ajuste RO020003 {_brl(v_aj)} · diferença {_brl(dif)}'))
    return _item('1.28', st, res, lin, abs(dif), cols=['nota', 'data', 'obs', 'valor'])


def _iso(d):
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})', d or '')
    return f'{m.group(3)}-{m.group(2)}-{m.group(1)}' if m else ''


def _saidas(x_sai, linhas, docs, se, tem_xml):
    lin = []
    if tem_xml and x_sai:
        g = defaultdict(lambda: {'n': 0, 'v': 0.0, 'notas': set()})
        for x in x_sai:
            if x.get('fin_nfe') == '4':
                continue
            for it in x['itens']:
                cf = it.get('cfop') or ''
                if cf not in TRIB_SAI and cf not in ST_SAI:
                    continue
                r, mot = se.produto_st(it.get('ncm'), it.get('cest'))
                if cf in TRIB_SAI and r:
                    k = (it.get('cprod'), 'st')
                elif cf in ST_SAI and not r:
                    k = (it.get('cprod'), 'trib')
                else:
                    continue
                a = g[k]
                a['n'] += 1
                a['v'] += it.get('vprod') or 0
                a['notas'].add(x['num'])
                a['prod'], a['ncm'], a['cfop'], a['mot'] = it.get('xprod'), it.get('ncm'), cf, mot
        for (cod, tipo), a in sorted(g.items(), key=lambda kv: -kv[1]['v'])[:200]:
            lin.append({'cod': cod, 'prod': a['prod'], 'ncm': a['ncm'], 'de': _fmt_cfop(a['cfop']), 'nota': f"{len(a['notas'])} nota(s)",
                        'obs': (f"produto da ST ({a['mot']}) vendido como tributado — orientar o cliente a corrigir o cadastro" if tipo == 'st'
                                else 'produto fora do Anexo VI vendido como ST — coordenadora (denúncia espontânea / NF complementar)'),
                        'tipo': tipo, 'valor': round(a['v'], 2)})
    # base do 5000 (venda tributada) = valor contábil, salvo CST 20
    for d in docs:
        if d['oper'] != '1' or d['sit'] in CANC:
            continue
        for r in d['c190']:
            if r['cfop'] in TRIB_SAI and r['cst'][-2:] == '00' and r['vl_bc'] < r['vl_opr'] - 0.05:
                lin.append({'nota': d['num'], 'de': _fmt_cfop(r['cfop']), 'prod': f"CST {r['cst']}", 'obs': f"base R$ {r['vl_bc']:.2f} menor que o valor da operação R$ {r['vl_opr']:.2f} sem CST 20".replace('.', ','),
                            'tipo': 'base', 'valor': round(r['vl_opr'] - r['vl_bc'], 2)})
    if not lin:
        return _item('2.3', 'ok' if (tem_xml and x_sai) else 'av', 'tributação das saídas coerente com o Anexo VI' if (tem_xml and x_sai)
                     else 'anexe os XMLs das notas emitidas (NF-e/NFC-e) para conferir as saídas', cols=['prod', 'ncm', 'de', 'nota', 'obs', 'valor'])
    n_st = sum(1 for r in lin if r.get('tipo') == 'st')
    n_tr = sum(1 for r in lin if r.get('tipo') == 'trib')
    n_b = sum(1 for r in lin if r.get('tipo') == 'base')
    partes = [f'{n_st} produto(s) da ST vendidos como tributados' if n_st else '', f'{n_tr} tributado(s) vendidos como ST' if n_tr else '',
              f'{n_b} venda(s) tributada(s) com base menor que o valor contábil' if n_b else '']
    return _item('2.3', 'x', ' · '.join(p for p in partes if p), lin, sum(r['valor'] for r in lin), cols=['prod', 'ncm', 'de', 'nota', 'obs', 'valor'])


def _cat_cfop(cf):
    s = cf[1:]
    if s in ('403', '409', '411', '401'):
        return 'st'
    if s in ('102', '152', '202', '101'):
        return 'trib'
    if s in ('556', '407', '551', '406'):
        return 'desp'
    if s in ('652', '653', '662', '651'):
        return 'comb'
    return ''


DEV_ESPERADO = {'st': ('5411', '6411', 'devolução de compra ST — acumulador 5701'), 'trib': ('5202', '6202', 'devolução de compra tributada — acumulador 5700'),
                'desp': ('5556', '6556', 'devolução de compra de uso e consumo — acumulador 5702'), 'comb': ('5661', '6661', 'devolução de compra de combustível — acumulador 5703')}


def _devolucoes(x_sai, docs, tem_xml):
    if not tem_xml or not x_sai:
        return _item('2.13', 'av', 'anexe os XMLs das notas emitidas para conferir as devoluções (nota referenciada)')
    por_chave = {_so(d['chave']): d for d in docs if d['chave']}
    lin, n = [], 0
    for x in x_sai:
        if x.get('fin_nfe') != '4':
            continue
        n += 1
        cfs = sorted({it.get('cfop') for it in x['itens'] if it.get('cfop')})
        tp = x.get('tp_nf')
        if tp == '1' and any(c[0] in '123' for c in cfs) or tp == '0' and any(c[0] in '567' for c in cfs):
            lin.append({'nota': x['num'], 'data': _br(_ord(x['dt'])), 'de': ', '.join(map(_fmt_cfop, cfs)),
                        'obs': f"tipo da nota ({'saída' if tp == '1' else 'entrada'}) não combina com o CFOP — pedir Carta de Correção ao cliente", 'valor': x['vnf']})
            continue
        if tp != '1':
            continue                                              # devolução de venda (entrada própria)
        for ref in x.get('refs') or []:
            o = por_chave.get(_so(ref))
            if not o or o['oper'] != '0':
                continue
            cats = {_cat_cfop(c['cfop']) for c in o['c170']} - {''} or {_cat_cfop(r['cfop']) for r in o['c190']} - {''}
            if len(cats) != 1:
                continue
            cat = cats.pop()
            e1, e2, txt = DEV_ESPERADO[cat]
            ruins = [c for c in cfs if c not in (e1, e2) and c[0] in '56']
            if ruins:
                lin.append({'nota': x['num'], 'data': _br(_ord(x['dt'])), 'de': ', '.join(map(_fmt_cfop, ruins)), 'para': _fmt_cfop(e1 if ruins[0][0] == '5' else e2),
                            'obs': f"devolve a NF {o['num']} (compra {cat.replace('trib', 'tributada').replace('st', 'ST').replace('desp', 'uso e consumo').replace('comb', 'combustível')}) — {txt}",
                            'valor': x['vnf']})
    if not n:
        return _item('2.13', 'ok', 'nenhuma devolução emitida no período')
    return _item('2.13', 'x' if lin else 'ok', f'{len(lin)} devolução(ões) com CFOP/acumulador diferente da compra de origem' if lin else f'{n} devolução(ões) conferidas com a compra de origem',
                 lin, sum(r['valor'] for r in lin), cols=['nota', 'data', 'de', 'para', 'obs', 'valor'])


def _fretes(x_cte, ctes, docs, cnpj, no_sped, part, tem_xml):
    if not tem_xml or not x_cte:
        av = 'anexe os XMLs de CT-e para conferir' if tem_xml else 'anexe os XMLs (CT-e) para conferir'
        return _item('2.17', 'av', av), _item('2.18', 'av', av)
    por_chave = {_so(d['chave']): d for d in docs if d['chave']}
    tomados = [x for x in x_cte if _so(x.get('toma_cnpj')) == cnpj]
    sem = [x for x in tomados if _so(x['chave']) not in no_sped]
    l17 = [{'nota': x['chave'][25:34].lstrip('0'), 'forn': x.get('emit_nome', ''), 'obs': 'NF transportada: ' + (', '.join(
        (por_chave[_so(k)]['num'] if _so(k) in por_chave else f'{k[25:34].lstrip("0")} (fora do SPED)') for k in x['nfes'][:4]) or '—'), 'valor': x['vtprest']} for x in sem]
    a = _item('2.17', 'x' if l17 else 'ok', f'{len(l17)} CT-e tomado(s) sem entrada no SPED' if l17 else f'{len(tomados)} CT-e tomado(s), todos escriturados', l17, sum(r['valor'] for r in l17))
    xc = {x['chave']: x for x in x_cte}
    l18 = []
    for c in ctes:
        if c['oper'] != '0' or c['sit'] in CANC:
            continue
        x = xc.get(_so(c['chave']))
        if not x:
            continue
        cats = set()
        for k in x['nfes']:
            d = por_chave.get(_so(k))
            if d:
                cats |= {_cat_cfop(i['cfop']) for i in d['c170']} | {_cat_cfop(r['cfop']) for r in d['c190']}
        cats -= {''}
        if not cats:
            continue
        cred = sum(r['vl_icms'] for r in c['d190'])
        fn = (part.get(c['part']) or {}).get('nome', c['part'])
        if cats <= {'desp', 'comb'} and cred > 0.009:
            l18.append({'nota': c['num'], 'forn': fn, 'obs': 'frete de mercadoria de uso e consumo com crédito — acumulador 7027, CST 90, sem crédito', 'valor': cred})
        elif cats <= {'st'} and cred > 0.009:
            l18.append({'nota': c['num'], 'forn': fn, 'obs': 'frete de mercadoria da ST com crédito — só há crédito se a mercadoria transportada for tributada', 'valor': cred})
        elif 'trib' in cats and cred < 0.009 and (x.get('vicms') or 0) > 0.009 and cats <= {'trib', 'st'}:
            l18.append({'nota': c['num'], 'forn': fn, 'obs': f"frete de mercadoria tributada com ICMS destacado (R$ {x['vicms']:.2f}) e sem crédito — acumulador 6510, CST 00".replace('.', ','),
                        'valor': x['vicms']})
    b = _item('2.18', 'x' if l18 else 'ok', f'{len(l18)} CT-e com crédito diferente do destino da mercadoria' if l18 else 'crédito dos fretes coerente com o destino da mercadoria',
              l18, sum(r['valor'] for r in l18), cols=['nota', 'forn', 'obs', 'valor'])
    return a, b


def _cst(ent, x_de, p200, se, tem_xml, forn):
    regra = defaultdict(list)
    orig = []
    comb = []
    for d in ent:
        x = x_de(d)
        sn = x.get('simples') if x else None
        par = _par(d, x) if x else {}
        for c in d['c170']:
            cst = (c['cst'] or '').zfill(3)
            o, t = cst[0], cst[1:]
            p = p200.get(c['item']) or {}
            if o in ('1', '6'):
                orig.append({'nota': d['num'], 'forn': forn(d), 'prod': p.get('descr', c['item']), 'de': cst, 'para': ('2' if o == '1' else '7') + t, 'valor': round(c['vl'], 2)})
            cat = _cat_cfop(c['cfop'])
            ncm = p.get('ncm') or ''
            if ncm.startswith(NCM_COMB):
                if t != '61':
                    comb.append({'nota': d['num'], 'forn': forn(d), 'prod': p.get('descr', c['item']), 'de': cst, 'para': o + '61', 'obs': f"{_fmt_cfop(c['cfop'])} · NCM {ncm}",
                                 'valor': round(c['vl'], 2)})
                continue
            if cat == 'comb':
                continue                                  # lubrificante, filtro, etanol hidratado: fora do CST 61
            esperado, txt = None, ''
            if cat == 'st' and t != '60':
                esperado, txt = '60', 'revenda da ST → CST 60'
            elif cat == 'trib':
                if sn is True and t not in ('90',):
                    esperado, txt = '90', 'revenda tributada de fornecedor do Simples Nacional → CST 90'
                elif sn is False and t not in ('00', '20', '40', '41'):
                    esperado, txt = '00', 'revenda tributada → CST 00 (isenta 40 e redução 20, conferindo)'
            elif cat == 'desp':
                r, _ = se.produto_st(ncm, p.get('cest'))
                it = par.get(c['i'])
                ret = se._xml_st(it) if it else None          # ST só com a retenção no XML
                if r and ret is True and t != '60':
                    esperado, txt = '60', 'despesa da ST (ICMS-ST retido no XML) → CST 60'
                elif not (r and ret is not False) and t not in ('90',) and not (t == '60' and ret is None):
                    esperado, txt = '90', 'despesa tributada, isenta, com redução ou do Simples → CST 90'
            if esperado:
                regra[txt].append({'nota': d['num'], 'forn': forn(d), 'prod': p.get('descr', c['item']), 'de': cst, 'para': o + esperado, 'obs': _fmt_cfop(c['cfop']),
                                   'valor': round(c['vl'], 2), 'regra': txt})
    lin = [r for k in sorted(regra, key=lambda k: -len(regra[k])) for r in regra[k]]
    res = ' · '.join(f'{len(v)} item(ns): {k}' for k, v in sorted(regra.items(), key=lambda kv: -len(kv[1]))[:3])
    out = [_item('2.22', 'x' if lin else 'ok', res if lin else 'CST coerente com a natureza das operações' + ('' if tem_xml else ' (sem XML: Simples Nacional não conferido)'),
                 lin, sum(r['valor'] for r in lin), cols=['nota', 'forn', 'prod', 'obs', 'de', 'para', 'valor']),
           _item('2.29', 'x' if comb else 'ok', f'{len(comb)} item(ns) de combustível fora do CST 61' if comb else 'combustível com CST 61', comb,
                 sum(r['valor'] for r in comb), corretor='comb', cols=['nota', 'forn', 'prod', 'obs', 'de', 'para', 'valor']),
           _item('2.34', 'x' if orig else 'ok', f'{len(orig)} item(ns) com origem 1 ou 6' if orig else 'nenhum item com origem 1 ou 6', orig,
                 sum(r['valor'] for r in orig), cols=['nota', 'forn', 'prod', 'de', 'para', 'valor'])]
    return out


RX_SN = [re.compile(r'aproveitamento\s+(?:do\s+)?cr[eé]dito[^.;]{0,120}?R\$\s*([\d.]+,\d{2})[^.;]{0,120}?al[ií]quota\s+(?:de\s+)?([\d]+[,.]?\d*)\s*%', re.I),
         re.compile(r'al[ií]quota\s+(?:de\s+)?([\d]+[,.]?\d*)\s*%[^.;]{0,120}?aproveitamento[^.;]{0,80}?R\$\s*([\d.]+,\d{2})', re.I)]


def _le_rodape(t):
    for k, rx in enumerate(RX_SN):
        m = rx.search(t or '')
        if m:
            v, a = (m.group(1), m.group(2)) if k == 0 else (m.group(2), m.group(1))
            try:
                return float(a.replace(',', '.')), float(v.replace('.', '').replace(',', '.'))
            except ValueError:
                return None
    return None


def _simples(ent, x_de, forn, tem_xml):
    if not tem_xml:
        return _item('2.47', 'av', 'anexe os XMLs de entrada para ler o crédito permitido no rodapé da DANFE')
    lin, ler = [], []
    for d in ent:
        x = x_de(d)
        if not x or not x.get('simples'):
            continue
        tribs = [c for c in d['c170'] if _cat_cfop(c['cfop']) == 'trib']
        if not tribs:
            continue
        tem_c197 = any((r['cod'] or '').upper().startswith('RO0000000') or r['icms'] > 0 for r in d['c197'])
        if tem_c197:
            continue
        base = round(sum(c['vl'] for c in tribs), 2)
        if x.get('credito') and x['credito'] > 0.009:
            aliq = x['aliqs'][0] if x.get('aliqs') else round(x['credito'] / max(x['base'], 0.01) * 100, 2)
            lin.append({'id': d['i'], 'nota': d['num'], 'data': _br(_ord(d['dt'])), 'forn': forn(d), 'obs': f'crédito informado no XML (pCredSN {aliq:.2f}%)'.replace('.', ','),
                        'rodape': '', 'aliq': aliq, 'base': base, 'valor': round(x['credito'], 2)})
            continue
        r = _le_rodape(x.get('infcpl'))
        if r:
            aliq, v = r
            lin.append({'id': d['i'], 'nota': d['num'], 'data': _br(_ord(d['dt'])), 'forn': forn(d), 'obs': 'crédito permitido no rodapé da DANFE',
                        'rodape': _trecho(x.get('infcpl')), 'aliq': aliq, 'base': base, 'valor': round(v, 2)})
        elif re.search(r'cr[eé]d|ICMS|LC\s*123|simples', x.get('infcpl') or '', re.I):
            ler.append({'id': str(d['i']), 'nota': d['num'], 'data': _br(_ord(d['dt'])), 'forn': forn(d), 'base': base, 'rodape': (x.get('infcpl') or '')[:700]})
    it = _item('2.47', 'x' if lin else ('in' if ler else 'ok'), f'{len(lin)} nota(s) de fornecedor do Simples com crédito permitido e não escriturado' if lin
               else (f'{len(ler)} rodapé(s) para ler' if ler else 'nenhum crédito do Simples Nacional deixado de lado'), lin, sum(r['valor'] for r in lin),
               corretor='simples', cols=['nota', 'data', 'forn', 'rodape', 'aliq', 'base', 'valor'])
    it['ler_rodape'] = ler[:40]
    return it


def _trecho(t):
    t = t or ''
    m = re.search(r'.{0,60}aproveitamento.{0,140}', t, re.I | re.S)
    return ('…' + m.group(0).strip() + '…') if m else t[:180]


def _transporte(e110, sped_ant):
    if not e110:
        return _item('2.61', 'na', 'SPED sem E110')
    atual = _n(e110['c'][10])
    if not sped_ant:
        return _item('2.61', 'av', f'saldo credor do período anterior no SPED: {_brl(atual)} — anexe o SPED do mês anterior para conferir')
    try:
        _, la = _ler(sped_ant)
        _, _, _, _, ea, _ = dr._estrutura(la)
    except Exception as e:
        return _item('2.61', 'av', f'não consegui ler o SPED anterior ({e})')
    if not ea:
        return _item('2.61', 'av', 'o SPED anterior não tem E110')
    trans = _n(ea['c'][14])
    dif = round(atual - trans, 2)
    lin = [{'obs': 'saldo credor a transportar no SPED anterior (E110)', 'valor': trans}, {'obs': 'saldo credor do período anterior neste SPED (E110)', 'valor': atual},
           {'obs': 'diferença', 'valor': dif}]
    return _item('2.61', 'ok' if abs(dif) < 0.05 else 'x', 'saldo credor transportado corretamente' if abs(dif) < 0.05 else
                 f'saldo credor transportado diferente do anterior · diferença {_brl(dif)}', lin, abs(dif), cols=['obs', 'valor'])


def _apuracao(linhas, e110):
    lin = []
    if e110:
        c = e110['c']
        for k, t in ((2, 'débitos por saídas'), (4, 'ajustes de débito'), (6, 'créditos por entradas'), (8, 'ajustes de crédito'), (10, 'saldo credor do período anterior'),
                     (13, 'ICMS a recolher'), (14, 'saldo credor a transportar')):
            lin.append({'obs': t, 'valor': _n(c[k])})
    aj = defaultdict(float)
    desc = {}
    for c in _registros(linhas, 'E111'):
        if len(c) > 4:
            aj[c[2]] += _n(c[4])
            desc[c[2]] = c[3]
    for k, v in sorted(aj.items()):
        lin.append({'obs': f'ajuste {k} · {desc.get(k, "")}'[:120], 'valor': round(v, 2)})
    dif = sum(_n(c[7]) for c in _registros(linhas, 'E310') if len(c) > 7)
    if dif:
        lin.append({'obs': 'DIFAL (E310)', 'valor': round(dif, 2)})
    g110 = _registros(linhas, 'G110')
    if g110:
        lin.append({'obs': 'parcela do CIAP (G110)', 'valor': sum(_n(c[-2]) for c in g110 if len(c) > 3)})
    sn = sum(_n(c[7]) for c in _registros(linhas, 'C197') if len(c) > 7 and c[2].upper().startswith('RO0000000'))
    if sn:
        lin.append({'obs': 'créditos do Simples Nacional (C197)', 'valor': round(sn, 2)})
    if _registros(linhas, '1300'):
        lin.append({'obs': f'LMC (1300): {len(_registros(linhas, "1300"))} registro(s)', 'valor': 0})
    return _item('3.6', 'in', 'resumo da apuração para a conferência final (débitos, créditos, ajustes, DIFAL, CIAP, Simples, a recolher)', lin, cols=['obs', 'valor'])


# ------------------------------------------------------------------ itens da Análise Inteligente que o POP pede
MAPA_AI = {'validacao': '3.4', 'chave': '1.8', 'desconto': '1.8', 'valor': '1.8', 'ncm': '1.14', 'unid': '1.14', 'ucons': '2.20', 'stent': '2.20',
           'icms': '2.46', 'difal': '2.43', 'acum': '2.38'}


def junta_inteligente(res, an):
    """Leva as etapas da Análise Inteligente para os itens do POP (mesma conferência, mesmos números)."""
    por = defaultdict(list)
    for e in an.get('etapas') or []:
        n = MAPA_AI.get(e['key'])
        if n:
            por[n].append(e)
    for n, es in por.items():
        com = [e for e in es if e.get('tipo') not in ('zero', 'fora', 'sem_xml') and e.get('grupos')]
        sem_xml = [e for e in es if e.get('tipo') == 'sem_xml']
        lin = []
        for e in com:
            for g in e['grupos']:
                for l in g.get('linhas') or []:
                    if l.get('bloqueado'):
                        continue
                    lin.append({'nota': str(l.get('nota', ''))[:60], 'obs': f"{e['titulo']}: " + str(l.get('det', ''))[:220], 'valor': l.get('valor') or 0})
        if com:
            st, resumo = 'x', ' · '.join(f"{e['titulo']}: {e['qtd']}" for e in com)
        elif sem_xml and len(sem_xml) == len(es):
            st, resumo = 'av', 'anexe os XMLs: ' + ', '.join(e['titulo'] for e in sem_xml)
        else:
            st, resumo = 'ok', ' · '.join(f"{e['titulo']}: {e['qtd']}" for e in es)
        val = sum(float(r['valor'] or 0) for r in lin if isinstance(r['valor'], (int, float)))
        res['itens'].append(_item(n, st, resumo, lin, val, corretor=com[0]['key'] if com else None, cols=['nota', 'obs', 'valor']))
    res['itens'].sort(key=lambda i: tuple(int(p) for p in i['n'].split('.')))
    return res


def contagens(res):
    c = defaultdict(int)
    for i in res['itens']:
        c[i['status']] += 1
    res['contagem'] = dict(c)
    res['valor_total'] = round(sum(i['valor'] for i in res['itens'] if i['status'] == 'x' and i['n'] not in ('2.15',)), 2)
    return res


# ------------------------------------------------------------------ dados para a IA (sem CNPJ, sem nomes)
def para_ia(res):
    apelido = {}

    def ap(nome):
        if not nome:
            return ''
        if nome == 'emissão própria':
            return nome
        if nome not in apelido:
            apelido[nome] = f'Fornecedor {len(apelido) + 1}'
        return apelido[nome]

    def limpa(s):
        s = re.sub(r'\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}', '[CNPJ]', str(s or ''))
        s = re.sub(r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}', '[CPF]', s)
        return re.sub(r'\b\d{9,14}\b', '[IE]', s)

    itens = []
    for i in res['itens']:
        amostra = []
        for l in i['linhas'][:25]:
            r = {k: (ap(v) if k == 'forn' else limpa(v)) for k, v in l.items() if k not in ('chave', 'id', 'cod') and v not in ('', None)}
            amostra.append(r)
        itens.append({'n': i['n'], 'titulo': i['titulo'], 'status': i['status'], 'resumo': limpa(i['resumo']), 'valor': i['valor'], 'total_linhas': i['total_linhas'],
                      'amostra': amostra})
    bonif = [{'id': l['id'], 'produto': l.get('prod', ''), 'ncm': l.get('ncm', ''), 'cfop': l.get('de', ''), 'valor': l.get('valor', 0)}
             for i in res['itens'] if i['n'] == '2.42' for l in i['linhas'][:80]]
    rod = [{'id': r['id'], 'rodape': limpa(r['rodape']), 'base': r['base']} for i in res['itens'] if i['n'] == '2.47' for r in i.get('ler_rodape') or []]
    return {'periodo': res.get('periodo'), 'uf': (res.get('cab') or {}).get('uf'), 'itens': itens, 'bonificacoes': bonif, 'rodapes_simples': rod}


def aplica_ia(res, ia):
    """Junta a resposta da IA (bonificações classificadas, rodapés lidos, explicações) ao resultado."""
    ia = ia or {}
    exp = ia.get('itens') or {}
    for i in res['itens']:
        if i['n'] in exp:
            i['ia'] = str(exp[i['n']])[:2500]
        if i['n'] == '2.42':
            cl = {str(b.get('id')): b for b in ia.get('bonificacoes') or []}
            uso = rev_n = 0
            for l in i['linhas']:
                b = cl.get(str(l.get('id')))
                if b:
                    rev = b.get('destino') == 'revenda'
                    l['obs'] = ('revenda → 6500' if rev else 'uso e consumo → 7026' + (' · recolher DIFAL' if l.get('inter') else '')) + (f" · {b.get('motivo')}" if b.get('motivo') else '')
                    uso += 0 if rev else 1
                    rev_n += 1 if rev else 0
            if cl:
                pend = len(i['linhas']) - uso - rev_n
                i['resumo'] = (f"{len(i['linhas'])} item(ns) de bonificação: {rev_n} revenda (6500) · {uso} uso e consumo (7026)"
                               + (f' · {pend} a classificar' if pend else ''))
                if uso and any(l.get('inter') and 'uso e consumo' in l['obs'] for l in i['linhas']):
                    i['status'] = 'x'
                    i['resumo'] += ' · uso e consumo interestadual: recolher DIFAL'
        if i['n'] == '2.47':
            lidos = {str(r.get('id')): r for r in ia.get('rodapes_simples') or []}
            for r in i.get('ler_rodape') or []:
                x = lidos.get(str(r['id']))
                if x and x.get('permite') and float(x.get('aliquota') or 0) > 0:
                    v = float(x.get('valor') or 0) or round(r['base'] * float(x['aliquota']) / 100, 2)
                    i['linhas'].append({'id': r['id'], 'nota': r['nota'], 'data': r['data'], 'forn': r['forn'], 'obs': 'crédito permitido no rodapé (lido pela IA)',
                                        'rodape': _trecho(r['rodape']), 'aliq': float(x['aliquota']), 'base': r['base'], 'valor': round(v, 2)})
            if i['linhas']:
                i['status'] = 'x'
                i['valor'] = round(sum(l['valor'] for l in i['linhas']), 2)
                i['resumo'] = f"{len(i['linhas'])} nota(s) de fornecedor do Simples com crédito permitido e não escriturado"
                i['total_linhas'] = len(i['linhas'])
            elif lidos:
                i['status'] = 'ok'
                i['resumo'] = 'rodapés lidos: nenhum crédito do Simples deixado de lado'
    res['parecer'] = str(ia.get('parecer') or '')[:6000]
    res['prioridades'] = [str(p) for p in (ia.get('prioridades') or [])][:12]
    res['word'] = ia.get('word') or {}
    return contagens(res)


# ------------------------------------------------------------------ Word de observação ao cliente (POP 2.1)
def gerar_word(res, saida):
    from docx import Document
    from docx.shared import Pt, RGBColor
    doc = Document()
    st = doc.styles['Normal']
    st.font.name = 'Calibri'
    st.font.size = Pt(10.5)
    cab = res.get('cab') or {}
    w = res.get('word') or {}
    doc.add_heading(w.get('titulo') or f"Observações do fechamento fiscal · {res.get('periodo', '')}", level=1)
    doc.add_paragraph(f"{cab.get('nome', '')} · competência {res.get('periodo', '')}")
    for p in w.get('paragrafos') or []:
        doc.add_paragraph(str(p))
    blocos = [('2.2', 'Produtos com a tributação do ICMS para corrigir no seu sistema (entradas)', ['prod', 'nota', 'de', 'para']),
              ('2.3', 'Produtos com a tributação para corrigir nas vendas', ['prod', 'ncm', 'de', 'obs']),
              ('1.12', 'Notas canceladas que estavam escrituradas', ['nota', 'data', 'forn']),
              ('1.9', 'Notas do mês que não vieram no SPED (ficam para o próximo mês)', ['nota', 'data', 'forn', 'valor']),
              ('2.13', 'Devoluções com CFOP a corrigir (Carta de Correção)', ['nota', 'de', 'para', 'obs']),
              ('2.17', 'CT-e sem entrada', ['nota', 'forn', 'valor'])]
    nomes = {'prod': 'Produto', 'nota': 'Nota', 'de': 'Está', 'para': 'Corrigir para', 'ncm': 'NCM', 'obs': 'Observação', 'data': 'Data', 'forn': 'Fornecedor', 'valor': 'Valor (R$)'}
    por = {i['n']: i for i in res['itens']}
    for n, tit, cols in blocos:
        i = por.get(n)
        if not i or i['status'] not in ('x', 'in') or not i['linhas']:
            continue
        doc.add_heading(tit, level=2)
        t = doc.add_table(rows=1, cols=len(cols))
        t.style = 'Light Grid Accent 1'
        for k, c in enumerate(cols):
            t.rows[0].cells[k].text = nomes[c]
        for l in i['linhas'][:150]:
            row = t.add_row().cells
            for k, c in enumerate(cols):
                v = l.get(c, '')
                row[k].text = (_brl(v).replace('R$ ', '') if isinstance(v, float) else str(v))
    if por.get('1.2', {}).get('status') == 'av':
        doc.add_heading('Documentos pendentes', level=2)
        doc.add_paragraph('Fatura de energia elétrica do período, legível.')
    for p in w.get('fechamento') or []:
        doc.add_paragraph(str(p))
    r = doc.add_paragraph().add_run('Liddera | Inteligência em Negócios')
    r.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
    doc.save(saida)
    return saida


# ------------------------------------------------------------------ CLI
def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    try:
        if '--word' in argv:
            with open(opt('--res'), encoding='utf-8') as fh:
                res = json.load(fh)
            out = {'ok': True, 'arquivo': gerar_word(res, opt('--word'))}
        elif '--ia' in argv:
            with open(opt('--res'), encoding='utf-8') as fh:
                res = json.load(fh)
            with open(opt('--ia'), encoding='utf-8') as fh:
                ia = json.load(fh)
            out = aplica_ia(res, ia)
        else:
            dr.carrega_regimes(opt('--regimes'))
            extra = {}
            if opt('--extra'):
                with open(opt('--extra'), encoding='utf-8') as fh:
                    extra = json.load(fh)
            res = analisar(opt('--sped'), opt('--xmls'), opt('--sped-ant'), extra)
            if '--sem-inteligente' not in argv:
                import analisar_tudo as at
                try:
                    an = at.analisar(opt('--sped'), opt('--xmls'))
                    junta_inteligente(res, an)
                except Exception as e:
                    res['aviso_inteligente'] = f'Análise Inteligente não rodou: {e}'
            out = contagens(res)
            out['para_ia'] = para_ia(res)
    except Exception as e:
        import traceback
        out = {'erro': str(e), 'detalhe': traceback.format_exc()[-3000:]}
    with open(opt('--json'), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False)
    return 0


if __name__ == '__main__':
    sys.exit(main_cli(sys.argv[1:]))

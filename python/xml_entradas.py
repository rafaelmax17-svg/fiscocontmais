# -*- coding: utf-8 -*-
"""Leitura dos XMLs de NF-e de entrada para o Corretor do SPED (DIFAL de RO e crédito do Simples Nacional).

De cada nota guarda, item a item: origem e CST/CSOSN do ICMS, alíquota e valor destacados, ICMS-ST retido, IPI e
valores que compõem o valor da operação (produto, frete, seguro, outras despesas, desconto); e, para fornecedor do
Simples Nacional, o percentual e o valor do crédito (pCredSN / vCredICMSSN).
"""
import re
import xml.etree.ElementTree as ET


def _t(el, tag):
    if el is None:
        return ''
    x = el.find(tag)
    return (x.text or '').strip() if x is not None and x.text else ''


def _fx(s):
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def ler_xml(texto):
    """Devolve os dados da NF-e ou None se o arquivo não for uma nota."""
    if '<infNFe' not in texto:
        return None
    m = re.search(r'<infNFe[^>]*Id="NFe(\d{44})"', texto)
    if not m:
        return None
    chave = m.group(1)
    limpo = re.sub(r'\sxmlns(:\w+)?="[^"]*"', '', texto)
    limpo = re.sub(r'<(/?)\w+:', r'<\1', limpo)
    try:
        raiz = ET.fromstring(re.sub(r'^\s*<\?xml[^>]*\?>', '', limpo.lstrip('﻿')))
    except ET.ParseError:
        return {'chave': chave, 'simples': False, 'itens': [], 'erro': 'XML ilegível'}
    inf = raiz if raiz.tag == 'infNFe' else raiz.find('.//infNFe')
    if inf is None:
        return None
    emit = inf.find('emit')
    itens, csosns = [], set()
    base_sn = cred_sn = 0.0
    aliqs_sn = set()
    credito_previsto = False
    for det in inf.findall('det'):
        prod = det.find('prod')
        imp = det.find('imposto')
        if prod is None or imp is None:
            continue
        icms = imp.find('ICMS')
        g = list(icms)[0] if icms is not None and len(list(icms)) else None
        ipi = imp.find('IPI/IPITrib')
        it = {
            'n': det.get('nItem', ''), 'cprod': _t(prod, 'cProd'), 'xprod': _t(prod, 'xProd'), 'ncm': _t(prod, 'NCM'),
            'cfop': _t(prod, 'CFOP'),
            'vprod': _fx(_t(prod, 'vProd')), 'vdesc': _fx(_t(prod, 'vDesc')), 'vfrete': _fx(_t(prod, 'vFrete')),
            'vseg': _fx(_t(prod, 'vSeg')), 'voutro': _fx(_t(prod, 'vOutro')), 'vipi': _fx(_t(ipi, 'vIPI')),
            'orig': _t(g, 'orig'), 'cst': _t(g, 'CST'), 'csosn': _t(g, 'CSOSN'),
            'picms': _fx(_t(g, 'pICMS')), 'vicms': _fx(_t(g, 'vICMS')), 'vbc': _fx(_t(g, 'vBC')), 'predbc': _fx(_t(g, 'pRedBC')),
            'vicmsst': _fx(_t(g, 'vICMSST')), 'pcredsn': _fx(_t(g, 'pCredSN')), 'vcredsn': _fx(_t(g, 'vCredICMSSN')),
        }
        it['valor_merc'] = round(it['vprod'] - it['vdesc'] + it['vfrete'] + it['vseg'] + it['voutro'], 2)
        it['valor_oper'] = round(it['valor_merc'] + it['vipi'], 2)     # base do DIFAL de uso/consumo inclui o IPI
        itens.append(it)
        if it['csosn']:
            csosns.add(it['csosn'])
            if it['csosn'] in ('101', '201') or it['vcredsn'] > 0:
                credito_previsto = True
                base_sn += it['valor_merc']
                cred_sn += it['vcredsn']
                if it['pcredsn'] > 0:
                    aliqs_sn.add(round(it['pcredsn'], 4))
    tot = inf.find('total/ICMSTot')
    return {
        'chave': chave, 'simples': bool(csosns), 'csosn': sorted(csosns),
        'crt': _t(emit, 'CRT'), 'emit_nome': _t(emit, 'xNome'), 'emit_uf': _t(emit, 'enderEmit/UF'),
        'vnf': _fx(_t(tot, 'vNF')), 'vst': _fx(_t(tot, 'vST')),
        'base': round(base_sn, 2), 'credito': round(cred_sn, 2), 'aliqs': sorted(aliqs_sn),
        'credito_previsto': credito_previsto, 'itens': itens,
    }


def ler_xmls(caminhos):
    """{chave: dados} de todos os XMLs (pastas, .xml ou .zip) — devolve (dict, lidos, erros)."""
    from fiscal_core import coletar_xmls, _read_text
    out, lidos, erros = {}, 0, 0
    for p in coletar_xmls(caminhos):
        try:
            x = ler_xml(_read_text(p))
        except Exception:
            erros += 1
            continue
        if x:
            lidos += 1
            out[x['chave']] = x
    return out, lidos, erros

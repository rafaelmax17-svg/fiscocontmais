# -*- coding: utf-8 -*-
"""Estoque de mercadoria excluída da substituição tributária — crédito do ICMS e inventário no SPED Fiscal (Admin).

Base legal (RICMS/RO, Decreto 22.721/2018, Anexo VI, Parte 1, Capítulo IV, Seção IV, redação do Dec. 29.184/2024):
  • art. 45: quem tem estoque de mercadoria que saiu da ST (CEST suprimido da Parte 2) segue esta seção;
  • art. 46 / 46-A: para cada mercadoria, a base de cálculo da ST (art. 14) do documento de entrada (ou da última
    entrada) × alíquota interna correspondente. Benefício usado no cálculo da ST vale também aqui (§ 2º);
  • art. 47: inventário na EFD ICMS/IPI só das mercadorias que mudaram de tributação (Guia Prático: H005 com
    MOT_INV = 02, H010 e H020 com CST, base e ICMS por unidade);
  • art. 48: o valor pode ser apropriado como crédito por código de ajuste específico — RO020033 "Crédito mudança
    de tributação - Art. 48 - anexo VI do RICMS" (tabela 5.1.1 de RO) —, limitado a 5.000 UPF/RO por mês.
Base de cálculo da ST (art. 14, I, b, 3): preço do remetente + frete, seguro, impostos (IPI) e encargos cobrados do
destinatário, mais a MVA da Parte 2. Em operação interestadual a MVA é a ajustada:
  MVA ajustada = [(1 + MVA original) × (1 − alíquota interestadual) ÷ (1 − alíquota interna)] − 1.

Entrada: o SPED Fiscal do mês, a planilha do estoque (código, descrição, quantidade, valor unitário) e os XMLs das
notas de entrada. Cada item da planilha é ligado a um item de XML pelo valor unitário (o da planilha é o preço da
nota por unidade, sem IPI — a nota vende em caixa/fardo de 6, 12…) e pela marca na descrição; do XML saem a alíquota
interestadual, o IPI, o frete/seguro/outras do item, o NCM e o CEST. Gera arquivo NOVO; o original nunca é alterado.
"""
import os
import re
import sys
import json
import unicodedata
from decimal import Decimal, ROUND_HALF_UP

import difal_ro as dr

TOL = Decimal('0.0005')
COD_AJUSTE = 'RO020033'
UPF_RO_PADRAO = None          # valor da UPF/RO do mês (opcional, para conferir o limite de 5.000 UPF)
# Parte 2 do Anexo VI (consolidado até o Dec. 31.963/26), Tabela III — bebidas alcoólicas, exceto cerveja e chope:
# MVA original 53,63% (NR do Dec. 28.385/23, efeitos a partir de 1º/09/23); item 24.0 (vinhos, CEST 02.024.00)
# revogado pelo Dec. 31.963/26 com efeitos a partir de 1º/09/2026. Alíquota interna de bebidas alcoólicas, exceto
# cerveja: 37% (Lei 688/96, art. 27, I, "h", redação da Lei 5.634/2023, a partir de 12/01/2024).
CEST_PADRAO = {
    '0202400': {'mva': Decimal('53.63'), 'aliq_interna': Decimal('37'), 'descr': 'Vinhos (Tabela III, item 24.0)',
                'mva_aj': {Decimal('4'): Decimal('134.10'), Decimal('7'): Decimal('126.78'), Decimal('12'): Decimal('114.59')},
                'excluido_em': '01092026', 'norma': 'Dec. 31.963/26'},
}


def _D(v):
    return Decimal(str(v if v not in (None, '') else 0))


def _q2(v):
    return Decimal(v).quantize(Decimal('0.01'), ROUND_HALF_UP)


def _q6(v):
    return Decimal(v).quantize(Decimal('0.000001'), ROUND_HALF_UP)


def _f(v, casas=2):
    return dr._f(v) if casas == 2 else format(Decimal(v).quantize(Decimal(10) ** -casas, ROUND_HALF_UP), 'f').replace('.', ',')


def _sem_acento(s):
    return ''.join(ch for ch in unicodedata.normalize('NFD', str(s or '').upper()) if unicodedata.category(ch) != 'Mn')


_ABREV = {'VHO': 'VINHO', 'TTO': 'TINTO', 'BCO': 'BRANCO', 'BDO': 'BORDO', 'BORDÔ': 'BORDO', 'RSE': 'ROSE', 'MSECO': 'MEIO'}


def _termos(s):
    return {_ABREV.get(w, w) for w in re.findall(r'[A-Z0-9,]+', _sem_acento(s))}


def _palavras(s):
    return {w for w in re.findall(r'[A-Z]{4,}', _sem_acento(s)) if w not in {'VINHO', 'VINHOS', 'SUAVE', 'SECO', 'TINTO', 'BRANCO'}}


# ------------------------------------------------------------------ planilha
def ler_planilha(caminho):
    """[(codigo, descricao, qtd, valor_unit)] da planilha do inventário (.xlsx ou .csv)."""
    linhas = []
    if caminho.lower().endswith('.csv'):
        import csv
        with open(caminho, newline='', encoding='utf-8-sig') as fh:
            linhas = [r for r in csv.reader(fh, delimiter=';')]
    else:
        import openpyxl
        wb = openpyxl.load_workbook(caminho, data_only=True, read_only=True)
        ws = wb.worksheets[0]
        linhas = [list(r) for r in ws.iter_rows(values_only=True)]
    cab_i, cols = None, {}
    for i, r in enumerate(linhas[:15]):
        nomes = [_sem_acento(c or '').strip() for c in r]
        if any('CODIGO' in n for n in nomes) and any('QUANT' in n for n in nomes):
            cab_i = i
            for j, n in enumerate(nomes):
                if 'CODIGO' in n and 'cod' not in cols:
                    cols['cod'] = j
                elif 'DESCR' in n:
                    cols['descr'] = j
                elif 'QUANT' in n:
                    cols['qtd'] = j
                elif 'UNIT' in n:
                    cols['vunit'] = j
            break
    if cab_i is None or not {'cod', 'descr', 'qtd', 'vunit'} <= set(cols):
        raise ValueError('A planilha precisa das colunas Código, Descrição, Quantidade e Valor Unitário.')
    out = []
    for r in linhas[cab_i + 1:]:
        cod = r[cols['cod']] if cols['cod'] < len(r) else None
        if cod in (None, '') or _sem_acento(cod).startswith('TOTAL'):
            continue
        num = lambda v: _D(str(v).replace('.', '').replace(',', '.')) if isinstance(v, str) else _D(v)
        cod = str(int(cod)) if isinstance(cod, float) and cod.is_integer() else str(cod).strip()
        out.append({'cod': cod, 'descr': str(r[cols['descr']] or '').strip(), 'qtd': num(r[cols['qtd']]), 'vunit': num(r[cols['vunit']])})
    return out


# ------------------------------------------------------------------ XMLs
def _itens_xml(xmls):
    """Itens das NF-e de entrada, com o valor por unidade de venda e por unidade interna (pacote de 6, 12…)."""
    import xml.etree.ElementTree as ET
    from fiscal_core import _read_text
    out = []
    for p in xmls:
        try:
            raiz = ET.fromstring(re.sub(r'\sxmlns="[^"]+"', '', _read_text(p), count=0))
        except ET.ParseError:
            continue
        inf = raiz.find('.//infNFe')
        if inf is None:
            continue
        t = lambda el, tag: (el.findtext(tag) or '').strip() if el is not None else ''
        ide, emit = inf.find('ide'), inf.find('emit')
        chave = (inf.get('Id') or '')[3:]
        for det in inf.findall('det'):
            prod, imp = det.find('prod'), det.find('imposto')
            icms = imp.find('ICMS') if imp is not None else None
            g = list(icms)[0] if icms is not None and len(list(icms)) else None
            ipi = imp.find('IPI/IPITrib') if imp is not None else None
            out.append({
                'arquivo': os.path.basename(p), 'chave': chave, 'num': t(ide, 'nNF'), 'data': t(ide, 'dhEmi')[:10],
                'emit': t(emit, 'xNome'), 'uf': t(emit, 'enderEmit/UF'), 'n': det.get('nItem'),
                'cprod': t(prod, 'cProd'), 'xprod': t(prod, 'xProd'), 'ncm': t(prod, 'NCM'), 'cest': t(prod, 'CEST'),
                'ucom': t(prod, 'uCom'), 'qcom': _D(t(prod, 'qCom')), 'vuncom': _D(t(prod, 'vUnCom')), 'vprod': _D(t(prod, 'vProd')),
                'vfrete': _D(t(prod, 'vFrete')), 'vseg': _D(t(prod, 'vSeg')), 'voutro': _D(t(prod, 'vOutro')), 'vdesc': _D(t(prod, 'vDesc')),
                'cst': t(g, 'CST'), 'picms': _D(t(g, 'pICMS')), 'vbcst': _D(t(g, 'vBCST')), 'vicmsst': _D(t(g, 'vICMSST')),
                'vipi': _D(t(ipi, 'vIPI')), 'pipi': _D(t(ipi, 'pIPI')),
            })
    return out


def _liga(item, itens):
    """Item do XML correspondente ao da planilha: valor unitário da planilha × unidades do pacote = vUnCom, com a
    mesma marca na descrição. Devolve (item_xml, unidades_por_pacote) ou (None, 0)."""
    marcas = _palavras(item['descr'])
    # tolerância: meia unidade da última casa decimal do valor unitário da planilha, vezes o tamanho do pacote
    casas = max(2, -item['vunit'].normalize().as_tuple().exponent) if item['vunit'] else 2
    meia = Decimal(5) * Decimal(10) ** -(casas + 1)
    cand = []
    for x in itens:
        if not (marcas & _palavras(x['xprod'])):
            continue
        for k in (1, 2, 3, 4, 6, 8, 10, 12, 15, 20, 24, 30, 36, 48):
            if abs(item['vunit'] * k - x['vuncom']) <= meia * k + Decimal('0.00001'):
                cand.append((x, k))
                break
    if not cand:
        return None, 0
    # a mesma garrafa pode estar em mais de uma nota: fica com a mais recente
    cand.sort(key=lambda c: c[0]['data'], reverse=True)
    # se houver itens diferentes da mesma marca com o mesmo preço, desempata pelas palavras da descrição
    melhores = [c for c in cand if c[0]['cprod'] == cand[0][0]['cprod']] if len({c[0]['cprod'] for c in cand}) == 1 else None
    if melhores is None:
        alvo = _termos(item['descr'])
        def nota(c):
            return len(alvo & _termos(c[0]['xprod']))
        cand.sort(key=lambda c: (nota(c), c[0]['data']), reverse=True)
        if len(cand) > 1 and nota(cand[0]) == nota(cand[1]) and cand[0][0]['cprod'] != cand[1][0]['cprod']:
            return None, 0
    return cand[0]


# ------------------------------------------------------------------ cálculo
def mva_ajustada(mva, aliq_inter, aliq_interna):
    m, ai, an = _D(mva) / 100, _D(aliq_inter) / 100, _D(aliq_interna) / 100
    if ai >= an:
        return _D(mva)
    return ((1 + m) * (1 - ai) / (1 - an) - 1) * 100


def calcular(planilha, itens_xml, params=None):
    params = params or {}
    linhas, avisos = [], []
    for it in planilha:
        x, k = _liga(it, itens_xml)
        if x is None:
            linhas.append({**_pub(it), 'status': 'sem_xml', 'obs': 'Nenhuma nota de entrada anexada tem este item pelo mesmo preço e marca.'})
            continue
        cest = x['cest'] or params.get('cest') or ''
        ref = CEST_PADRAO.get(cest, {})
        mva = _D(params.get('mva', ref.get('mva', 0)))
        an = _D(params.get('aliq_interna', ref.get('aliq_interna', 0)))
        if not mva or not an:
            linhas.append({**_pub(it), 'status': 'sem_regra', 'obs': f'CEST {cest or "?"} sem MVA/alíquota cadastradas: informe-as.'})
            continue
        ai = x['picms'] if x['uf'] != 'RO' else Decimal('0')
        tab = ref.get('mva_aj', {}) if 'mva' not in params else {}
        mva_aj = (tab.get(ai) or mva_ajustada(mva, ai, an)) if x['uf'] != 'RO' else mva
        qcom = x['qcom'] or Decimal('1')
        # por unidade do estoque: preço + IPI + frete/seguro/outras − desconto do item, dividido pelas unidades do pacote
        extras = (x['vipi'] + x['vfrete'] + x['vseg'] + x['voutro'] - x['vdesc']) / qcom / k
        base_op = it['vunit'] + extras
        if x['vbcst'] > 0:      # ST retida na nota: a base é a da nota
            bc_unit = x['vbcst'] / qcom / k
            fonte = 'base da ST destacada na nota'
        else:
            bc_unit = base_op * (1 + mva_aj / 100)
            fonte = f'preço + IPI × (1 + MVA ajustada {_f(_q2(mva_aj))}%)'
        icms_unit = bc_unit * an / 100
        linhas.append({
            **_pub(it), 'status': 'ok', 'cest': cest, 'ncm': x['ncm'], 'fornecedor': x['emit'], 'uf': x['uf'],
            'nota': x['num'], 'data_nota': x['data'], 'chave': x['chave'], 'item_xml': x['xprod'], 'pacote': k,
            'aliq_inter': float(ai), 'ipi_unit': float(_q6(x['vipi'] / qcom / k)), 'mva': float(mva), 'mva_aj': float(_q2(mva_aj)),
            'aliq_interna': float(an), 'bc_unit': float(_q6(bc_unit)), 'icms_unit': float(_q6(icms_unit)),
            'bc_total': float(_q2(bc_unit * it['qtd'])), 'credito': float(_q2(icms_unit * it['qtd'])), 'fonte': fonte,
            'st_retida': x['vbcst'] > 0, 'frete_nota': float(x['vfrete']),
        })
    ok = [l for l in linhas if l['status'] == 'ok']
    notas = _confere_notas(ok, itens_xml, params)
    tot = float(_q2(sum(_D(l['credito']) for l in ok)))
    upf = params.get('upf')
    limite = float(_q2(_D(upf) * 5000)) if upf else None
    if limite is not None and tot > limite:
        avisos.append(f'O crédito (R$ {_f(tot)}) passa do limite mensal de 5.000 UPF/RO (R$ {_f(limite)}): '
                      'o excedente fica para os meses seguintes (Anexo VI, art. 48, parágrafo único).')
    if any(l.get('st_retida') is False for l in ok):
        avisos.append('As notas vieram sem ICMS-ST retido (a ST foi paga na entrada, como antecipado): a base foi refeita pela '
                      'regra do art. 14 (preço + IPI + frete/encargos da nota, mais a MVA ajustada). Frete pago à parte em CT-e '
                      'não está incluído — se ele entrou no cálculo do antecipado, o crédito real é um pouco maior.')
    pend = [n for n in notas if n['st_pago'] is None]
    if pend:
        avisos.insert(0, 'Confira a ST paga (DARE) de ' + ', '.join(f"NF {n['nota']}" for n in pend) + ': o crédito só pode ir para o SPED '
                      'depois de informar o valor pago de cada nota (Anexo VI, art. 46, § 2º — benefício usado na ST vale também no crédito).')
    return {'itens': linhas, 'notas': notas, 'pendentes_dare': len(pend), 'credito_total': tot, 'credito_apropriado': min(tot, limite) if limite is not None else tot,
            'limite': limite, 'avisos': avisos,
            'resumo': {'itens': len(linhas), 'calculados': len(ok), 'sem_xml': sum(1 for l in linhas if l['status'] == 'sem_xml'),
                       'qtd': float(sum(_D(l['qtd']) for l in linhas)), 'valor_estoque': float(_q2(sum(_D(l['qtd']) * _D(l['vunit']) for l in linhas)))}}


def _confere_notas(ok, itens_xml, params):
    """Por nota de entrada: ST esperada pela regra (todos os itens da nota com o mesmo CEST, inclusive os que já não
    estão no estoque) × ST paga informada (DARE). Se a ST paga for diferente, o crédito dos itens dessa nota acompanha
    a proporção do que foi pago de verdade (ICMS da compra + ST paga) — art. 46, § 2º."""
    pagos = {str(k): v for k, v in (params.get('st_pago') or {}).items()}
    out = []
    for nota in sorted({l['nota'] for l in ok}):
        meus = [l for l in ok if l['nota'] == nota]
        ref = meus[0]
        an = _D(ref['aliq_interna']) / 100
        mva_aj = _D(ref['mva_aj']) / 100
        nf = [x for x in itens_xml if x['num'] == nota and x['chave'] == ref['chave'] and x['cest'] == ref['cest']]
        bc = sum((x['vprod'] + x['vipi'] + x['vfrete'] + x['vseg'] + x['voutro'] - x['vdesc']) for x in nf) * (1 + mva_aj)
        if any(x['vbcst'] > 0 for x in nf):
            bc = sum(x['vbcst'] for x in nf)
        icms_total = bc * an
        proprio = sum(x['vprod'] * x['picms'] / 100 for x in nf)
        esperado = icms_total - proprio
        pago = pagos.get(nota)
        pago = _D(str(pago).replace(',', '.')) if pago not in (None, '') else None
        fator = Decimal('1')
        if pago is not None and icms_total > 0:
            fator = (proprio + pago) / icms_total
            for l in meus:
                l['icms_unit'] = float(_q6(_D(l['icms_unit']) * fator))
                l['credito'] = float(_q2(_D(l['credito']) * fator))
                l['conferido'] = True
                if abs(fator - 1) > Decimal('0.001'):
                    l['fonte'] += f' · ajustado ao DARE ({_f(_q2(fator * 100))}% do calculado)'
        out.append({'nota': nota, 'chave': ref['chave'], 'fornecedor': ref['fornecedor'], 'uf': ref['uf'], 'data': ref['data_nota'],
                    'itens_nota': len(nf), 'itens_estoque': len(meus), 'bc_st': float(_q2(bc)), 'icms_total': float(_q2(icms_total)),
                    'icms_proprio': float(_q2(proprio)), 'st_esperado': float(_q2(esperado)),
                    'st_pago': float(pago) if pago is not None else None, 'fator': float(_q6(fator)),
                    'credito': float(_q2(sum(_D(l['credito']) for l in meus))),
                    'situacao': 'pendente' if pago is None else ('confere' if abs(pago - esperado) <= Decimal('1') else 'diferente')})
    return out


def _pub(it):
    return {'cod': it['cod'], 'descr': it['descr'], 'qtd': float(it['qtd']), 'vunit': float(it['vunit']),
            'valor': float(_q2(it['qtd'] * it['vunit']))}


# ------------------------------------------------------------------ SPED
def aplicar(texto, calc, params):
    """Inventário (H005 MOT_INV 02 + H010 + H020), 0200 que faltar, E111 RO020033 e apuração refeita."""
    from fiscal_core import _recalcula_bloco9_global, _recalcula_fechamentos_bloco
    linhas, quebra, final_vazio = dr.dividir(texto)
    linhas = [l for l in linhas if l != '']
    cab, _, _, _, e110, _ = dr._estrutura(linhas)
    itens = [l for l in calc['itens'] if l['status'] == 'ok']
    if not itens:
        return texto, {'erro': 'Nenhum item calculado para lançar.'}
    if calc.get('pendentes_dare'):
        return texto, {'erro': 'Informe a ST paga (DARE) de todas as notas de entrada antes de lançar o crédito no SPED.'}
    dt_inv = re.sub(r'\D', '', params.get('dt_inv') or '')
    if len(dt_inv) != 8:
        return texto, {'erro': 'Informe a data do inventário (dia anterior à exclusão da ST).'}
    unid = params.get('unid') or '1'
    cod_cta = params.get('cod_cta') or ''
    resumo = {'itens': len(itens), 'r0200_criados': [], 'credito': 0.0, 'avisos': list(calc.get('avisos') or []),
              'e110_antes': None, 'e110_depois': None, 'e116': ''}
    # 0200 dos itens que não existem no cadastro do SPED
    existentes = {l.split('|')[2] for l in linhas if l.startswith('|0200|')}
    unids = {l.split('|')[2] for l in linhas if l.startswith('|0190|')}
    if unid not in unids:
        return texto, {'erro': f'A unidade "{unid}" não existe no 0190 deste SPED. Escolha uma das cadastradas.'}
    novos_0200 = []
    for l in itens:
        if l['cod'] in existentes:
            continue
        aliq = _f(_D(l['aliq_interna']))
        novos_0200.append(f"|0200|{l['cod']}|{l['descr']}|||{unid}|00|{l['ncm']}||{l['ncm'][:2]}||{aliq}|{l['cest']}|")
        resumo['r0200_criados'].append(l['cod'])
    if novos_0200:
        ult = max(i for i, l in enumerate(linhas) if l.startswith('|0200|') or l.startswith('|0190|'))
        while ult + 1 < len(linhas) and linhas[ult + 1].split('|')[1] in ('0205', '0206', '0210', '0220', '0221'):
            ult += 1
        linhas[ult + 1:ult + 1] = novos_0200
    # Bloco H
    bloco_h = []
    vl_inv = sum(_q2(_D(l['qtd']) * _D(l['vunit'])) for l in itens)
    bloco_h.append(f'|H005|{dt_inv}|{_f(vl_inv)}|02|')
    for l in itens:
        vl_item = _q2(_D(l['qtd']) * _D(l['vunit']))
        bloco_h.append(f"|H010|{l['cod']}|{unid}|{_f(_D(l['qtd']), 3)}|{_f(_D(l['vunit']), 6)}|{_f(vl_item)}|0|||{cod_cta}|{_f(vl_item)}|")
        bloco_h.append(f"|H020|000|{_f(_D(l['bc_unit']))}|{_f(_D(l['icms_unit']))}|")
    ih1 = next((i for i, l in enumerate(linhas) if l.startswith('|H001|')), None)
    ih9 = next((i for i, l in enumerate(linhas) if l.startswith('|H990|')), None)
    if ih1 is None or ih9 is None:
        return texto, {'erro': 'O SPED não tem o Bloco H (H001/H990).'}
    if any(l.startswith('|H005|') for l in linhas[ih1:ih9]):
        resumo['avisos'].append('O SPED já tinha inventário no Bloco H: o inventário da mudança de tributação foi acrescentado depois dele.')
    linhas[ih1] = '|H001|0|'
    linhas[ih9:ih9] = bloco_h
    # crédito: E111 RO020033 (campo 08 do E110 — 3º caractere 0, 4º caractere 2: outros créditos)
    credito = _q2(_D(calc['credito_apropriado']))
    descr = params.get('descr_ajuste') or f'CREDITO MUDANCA DE TRIBUTACAO - ART. 48 ANEXO VI RICMS/RO - ESTOQUE EM {dt_inv[:2]}/{dt_inv[2:4]}/{dt_inv[4:]}'
    i110 = next(i for i, l in enumerate(linhas) if l.startswith('|E110|'))
    j = i110
    while j + 1 < len(linhas) and linhas[j + 1].split('|')[1] in ('E111', 'E112', 'E113'):
        j += 1
    linhas.insert(j + 1, f'|E111|{COD_AJUSTE}|{descr}|{_f(credito)}|')
    cab, _, _, _, e110, _ = dr._estrutura(linhas)
    remover = set()
    novas_e116, erro = dr.aplica_apuracao(linhas, e110, {8: float(credito)}, params, cab, remover, resumo)
    if erro:
        return texto, {'erro': erro}
    if novas_e116:
        i116 = max(i for i, l in enumerate(linhas) if l.split('|')[1] in ('E110', 'E111', 'E112', 'E113', 'E115'))
        linhas[i116 + 1:i116 + 1] = novas_e116
    linhas = [l for i, l in enumerate(linhas) if i not in remover]
    linhas = _recalcula_bloco9_global(linhas)
    linhas = _recalcula_fechamentos_bloco(linhas)
    resumo['credito'] = float(credito)
    novo = quebra.join(linhas) + (quebra if final_vazio else '')
    return novo, resumo


# ------------------------------------------------------------------ CLI
def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    sped, js, plan = opt('--sped'), opt('--json'), opt('--planilha')
    if not sped or not js or not plan:
        print('uso: estoque-st --sped ARQ.txt --planilha estoque.xlsx --xmls "a.xml;b.zip" --json saida.json '
              '[--params params.json] [--aplicar --saida novo.txt]')
        return 1
    try:
        from fiscal_core import coletar_xmls
        params = {}
        if opt('--params'):
            with open(opt('--params'), 'r', encoding='utf-8') as fh:
                params = json.load(fh)
        texto, enc = dr._ler(sped)
        planilha = ler_planilha(plan)
        itens = _itens_xml(coletar_xmls([c for c in (opt('--xmls') or '').split(os.pathsep) if c]))
        calc = calcular(planilha, itens, params)
        cab = dr._estrutura(texto.splitlines())[0]
        e110 = next((l.split('|') for l in texto.splitlines() if l.startswith('|E110|')), None)
        calc['empresa'] = {'nome': cab.get('nome', ''), 'cnpj': cab.get('cnpj', ''), 'uf': cab.get('uf', ''),
                           'dt_ini': cab.get('dt_ini', ''), 'dt_fin': cab.get('dt_fin', '')}
        calc['e110'] = {'cred_aj': dr._n(e110[8]), 'recolher': dr._n(e110[13]), 'sld_transp': dr._n(e110[14])} if e110 else None
        calc['unidades'] = [{'cod': l.split('|')[2], 'descr': l.split('|')[3]} for l in texto.splitlines() if l.startswith('|0190|')]
        calc['xml_itens'] = len(itens)
        res = calc
        if '--aplicar' in argv:
            novo, r = aplicar(texto, calc, params)
            res = {**calc, 'aplicado': r}
            if not r.get('erro'):
                tmp = opt('--saida') + '.parcial'
                with open(tmp, 'w', encoding=enc, newline='') as fh:
                    fh.write(novo)
                os.replace(tmp, opt('--saida'))
            else:
                res['erro'] = r['erro']
    except Exception as e:  # pragma: no cover
        res = {'erro': f'Falha ao processar: {e}'}
    tmp = js + '.parcial'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False, default=float)
    os.replace(tmp, js)
    return 0


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main_cli(sys.argv[1:]))

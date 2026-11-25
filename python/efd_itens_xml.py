# -*- coding: utf-8 -*-
"""
Itens das NF-e de saída pelos XMLs (2.4.56) — corretor da EFD-Contribuições.

Quando o Domínio não importa o cadastro de produtos de um estabelecimento, a NF-e de saída sai no C100 sem nenhum C170
e a receita dela fica fora da apuração. Com os XMLs das notas, este módulo:
  • liga cada XML ao C100 pela chave de acesso (só nota de saída, modelo 55, situação regular e SEM item no arquivo);
  • monta um C170 por item do XML (produto, NCM, quantidade, valores, CFOP, ICMS) e cadastra no 0200/0190 do próprio
    estabelecimento (na EFD-Contribuições o 0200 é filho do 0140) o que faltar;
  • define o CST de PIS/COFINS pelo NCM: 1º o tratamento que a própria empresa já dá ao mesmo NCM nas outras notas do
    arquivo; 2º a tabela do monofásico (CST 04); 3º tributado (CST 01). CFOP que não é receita → CST 49;
  • base de cálculo como o próprio arquivo faz: valor do item − desconto − ICMS próprio (Tema 69 do STF);
  • refaz o C100 (VL_PIS/VL_COFINS), o M210/M610 (receita bruta, base e contribuição), o M400/M410 e M800/M810
    (receita sem incidência por natureza), a redução linear da LC 224/2025 sobre o CST 06 (M220/M225 e M620/M625)
    e o M200/M600 com o M205/M605.
Nota sem XML, XML sem nota no arquivo e XML cancelado não mudam nada: só vão para o relatório.
"""
import re
from collections import Counter, defaultdict

from lxml import etree

import efd_corretor as ec
from oportunidades import _iter_xmls, _regra_ncm

try:
    from efd_lc224_excecoes import classifica_ncm, ZFM_ALC
except Exception:                                   # pragma: no cover
    classifica_ncm, ZFM_ALC = (lambda ncm: ('entra', '')), {}

NAT_REC = {'Produtos farmacêuticos': '002', 'Perfumaria, toucador e higiene pessoal': '002',
           'Pneumáticos (pneus novos e câmaras de ar)': '003', 'Combustíveis (diesel, GLP, gasolina)': '001',
           'Álcool para fins carburantes': '001'}
ALIQ = {'cum': (0.65, 3.00), 'nc': (1.65, 7.60)}
ALIQ_LC224 = {'cum': (0.065, 0.300), 'nc': (0.165, 0.760)}
_CST_SEM_RECEITA = {'49', '98', '99'}
_CST_FORA_C100 = {'05', '75'}


def _t(e, caminho):
    x = e.find(caminho) if e is not None else None
    return (x.text or '').strip() if x is not None and x.text else ''


def _f(e, caminho):
    v = _t(e, caminho)
    try:
        return float(v) if v else 0.0
    except ValueError:
        return 0.0


def _semns(raiz):
    for el in raiz.iter():
        if isinstance(el.tag, str) and '}' in el.tag:
            el.tag = el.tag.split('}', 1)[1]
    return raiz


def ler_xmls(caminhos):
    """{chave: nota}, {chaves canceladas}, quantidade de arquivos lidos."""
    notas, canc, lidos = {}, set(), 0
    for _nome, dados in _iter_xmls(caminhos or []):
        lidos += 1
        try:
            raiz = _semns(etree.fromstring(dados, etree.XMLParser(recover=True, huge_tree=True)))
        except Exception:
            continue
        if raiz is None:
            continue
        ev = raiz.find('.//infEvento')
        if raiz.tag in ('procEventoNFe', 'evento', 'retEnvEvento') or (ev is not None and raiz.find('.//infNFe') is None):
            if _t(raiz, './/infEvento/tpEvento') == '110111':
                ch = _t(raiz, './/infEvento/chNFe')
                st = _t(raiz, './/retEvento/infEvento/cStat')
                if ch and st in ('', '135', '136', '155'):
                    canc.add(ch)
            continue
        inf = raiz.find('.//infNFe')
        if inf is None:
            continue
        ch = _t(raiz, './/protNFe/infProt/chNFe') or (inf.get('Id') or '')[3:]
        if len(ch) != 44:
            continue
        st = _t(raiz, './/protNFe/infProt/cStat')
        ide = inf.find('ide')
        itens = []
        for det in inf.findall('det'):
            pr, im = det.find('prod'), det.find('imposto')
            icms = im.find('ICMS') if im is not None else None
            g = icms[0] if icms is not None and len(icms) else None
            pis = im.find('PIS') if im is not None else None
            gp = pis[0] if pis is not None and len(pis) else None
            itens.append({
                'n': det.get('nItem') or str(len(itens) + 1), 'cod': _t(pr, 'cProd'), 'ean': _t(pr, 'cEAN'), 'descr': _t(pr, 'xProd'),
                'ncm': re.sub(r'\D', '', _t(pr, 'NCM')), 'cfop': _t(pr, 'CFOP'), 'unid': _t(pr, 'uCom'), 'qtd': _f(pr, 'qCom'),
                'vprod': _f(pr, 'vProd'), 'vdesc': _f(pr, 'vDesc'), 'vfrete': _f(pr, 'vFrete'), 'vseg': _f(pr, 'vSeg'), 'voutro': _f(pr, 'vOutro'),
                'orig': _t(g, 'orig'), 'cst_icms': _t(g, 'CST') or _t(g, 'CSOSN'), 'vbc': _f(g, 'vBC'), 'picms': _f(g, 'pICMS'), 'vicms': _f(g, 'vICMS'),
                'vbcst': _f(g, 'vBCST'), 'picmsst': _f(g, 'pICMSST'), 'vicmsst': _f(g, 'vICMSST'),
                'vipi': _f(im, 'IPI/IPITrib/vIPI'), 'cst_pis_xml': _t(gp, 'CST'),
            })
        notas[ch] = {'chave': ch, 'mod': _t(ide, 'mod'), 'tp': _t(ide, 'tpNF'), 'num': _t(ide, 'nNF'), 'serie': _t(ide, 'serie'),
                     'data': (_t(ide, 'dhEmi') or _t(ide, 'dEmi'))[:10], 'emit': _t(inf, 'emit/CNPJ') or _t(inf, 'emit/CPF'),
                     'vnf': _f(inf, 'total/ICMSTot/vNF'), 'status': st, 'itens': itens,
                     'cfops': sorted({i['cfop'] for i in itens})}
    return notas, canc, lidos


def _cfop_receita(cfop):
    c = re.sub(r'\D', '', cfop or '')
    return len(c) == 4 and c[0] in '567' and (c[1] in '14' or c[1:] in ('651', '652', '653', '654', '655', '656', '667'))


def _regime(L):
    p = next((ec._partes(l['txt']) for l in L if ec._reg(l) == '0110'), None)
    cod = p[1] if p else '1'
    if cod == '2':
        return 'cum'
    if cod == '1':
        return 'nc'
    # 3 = os dois regimes: vale a alíquota que o próprio arquivo usa no CST 01
    al = Counter(ec._partes(l['txt'])[26] for l in L if ec._reg(l) == 'C170' and ec._partes(l['txt'])[24] == '01')
    a = al.most_common(1)[0][0] if al else ''
    return 'cum' if ec._num(a) and ec._num(a) < 1 else 'nc'


def _aprender(L):
    """Como a empresa já trata cada NCM nas notas de saída do arquivo: {ncm: Counter(cst)}; contas usadas por CST."""
    prod, est = {}, ''
    for l in L:
        r = ec._reg(l)
        if r == '0140':
            est = ec._partes(l['txt'])[3]
        elif r == '0200':
            p = ec._partes(l['txt'])
            prod[(est, p[1])] = re.sub(r'\D', '', p[7] if len(p) > 7 else '')
        elif r in ('C010', 'A010', 'D010', 'F010'):
            est = ec._partes(l['txt'])[1]
    ncm_cst, cta_cst, oper = defaultdict(Counter), defaultdict(Counter), ''
    for l in L:
        r = ec._reg(l)
        if r in ('C010', 'A010', 'D010', 'F010'):
            est = ec._partes(l['txt'])[1]
        elif r == 'C100':
            oper = ec._partes(l['txt'])[1]
        elif r == 'C170' and oper == '1':
            p = ec._partes(l['txt'])
            if len(p) < 37 or not _cfop_receita(p[10]) or p[24] in _CST_SEM_RECEITA:
                continue
            ncm = prod.get((est, p[2]), '')
            if ncm:
                ncm_cst[ncm][p[24]] += 1
            cta_cst[p[24]][p[36].strip()] += 1
    return ncm_cst, cta_cst


def _nat_por_cst(L):
    """natureza mais usada (por valor) em cada CST do M410: {cst: nat}"""
    out, cst = defaultdict(Counter), None
    for l in L:
        r = ec._reg(l)
        if r == 'M400':
            cst = ec._partes(l['txt'])[1]
        elif r == 'M410' and cst:
            p = ec._partes(l['txt'])
            out[cst][p[1]] += ec._num(p[2])
        elif r not in ('M400', 'M410'):
            cst = None if r[:1] == 'M' else cst
    return {k: v.most_common(1)[0][0] for k, v in out.items() if v}


def _cst_item(it, ncm_cst):
    """(cst, natureza ou '', origem da regra)"""
    if not _cfop_receita(it['cfop']):
        return '49', '', f"CFOP {it['cfop']} não é receita de venda"
    reg = _regra_ncm(it['ncm'])
    aprendido = ncm_cst.get(it['ncm'])
    if aprendido:
        cst = aprendido.most_common(1)[0][0]
        nat = NAT_REC.get(reg['grupo'], '') if (reg and cst == '04') else ''
        return cst, nat, 'mesmo NCM nas outras notas do arquivo'
    if reg and reg['grupo'] in NAT_REC and reg.get('confianca') in ('Alta', 'Média'):
        return '04', NAT_REC[reg['grupo']], f"monofásico — {reg['grupo']} ({reg['lei']})"
    return '01', '', 'tributado (NCM sem tratamento especial)'


_UNID_DESC = {'L': 'LITRO', 'LT': 'LITRO', 'UN': 'UNIDADE', 'UND': 'UNIDADE', 'KG': 'QUILOGRAMA', 'CX': 'CAIXA', 'PC': 'PECA',
              'M': 'METRO', 'M2': 'METRO QUADRADO', 'M3': 'METRO CUBICO', 'G': 'GRAMA', 'ML': 'MILILITRO', 'FD': 'FARDO', 'GL': 'GALAO'}


def _um(s, n=6):
    s = re.sub(r'[|]', '', (s or '').strip().upper())
    return (s or 'UN')[:n]


def aplicar(L, notas, canc, ctx, acoes, pend):
    """Monta os C170 das NF-e de saída sem item a partir dos XMLs. Devolve (L, resumo)."""
    res = {'lidos': ctx.get('xml_lidos', 0), 'notas_xml': len(notas), 'corrigidas': [], 'sem_xml': [], 'xml_sem_nota': [],
           'canceladas': [], 'divergentes': [], 'por_cst': {}, 'itens': 0, 'receita': 0.0, 'pis': 0.0, 'cofins': 0.0, 'regras': {}}
    if not notas and not canc:
        return L, res
    regime = _regime(L)
    a_p, a_c = ALIQ[regime]
    ncm_cst, cta_cst = _aprender(L)
    nat_cst = _nat_por_cst(L)
    # C100 do arquivo
    chaves_arq, alvos, est, part_mun = set(), [], '', {}
    for l in L:
        if ec._reg(l) == '0150':
            p = ec._partes(l['txt'])
            if len(p) > 7:
                part_mun[p[1]] = p[7].strip()
    for i, l in enumerate(L):
        r = ec._reg(l)
        if r in ('C010', 'A010', 'D010', 'F010'):
            est = ec._partes(l['txt'])[1]
        if r != 'C100':
            continue
        p = ec._partes(l['txt'])
        ch = p[8].strip() if len(p) > 8 else ''
        if ch:
            chaves_arq.add(ch)
        if p[1] != '1' or p[2] != '0' or p[4] != '55' or p[5] not in ('00', '01'):
            continue
        j = i + 1
        tem_item = False
        while j < len(L) and ec._reg(L[j]).startswith('C1') and ec._reg(L[j]) != 'C100':
            if ec._reg(L[j]) in ('C170', 'C175', 'C180'):
                tem_item = True
            j += 1
        if tem_item:
            continue
        info = {'i': i, 'chave': ch, 'num': p[7], 'data': p[9], 'valor': ec._num(p[11]), 'est': est, 'part': p[3]}
        if ch in canc:
            res['canceladas'].append({**info, 'motivo': 'o XML de cancelamento está no lote, mas a nota está como regular no arquivo'})
            pend.append({'cat': 'xml_itens', 'linha': L[i]['n'], 'titulo': f"NF-e {p[7]} cancelada no XML",
                         'detalhe': 'Há evento de cancelamento desta chave no lote de XMLs, mas o C100 está como regular (situação 00/01). Confira e, se for o caso, escriture como cancelada (situação 02).'})
            continue
        nf = notas.get(ch)
        if not nf:
            res['sem_xml'].append(info)
            continue
        if abs(nf['vnf'] - info['valor']) > 0.05:
            res['divergentes'].append({**info, 'vnf': nf['vnf']})
            pend.append({'cat': 'xml_itens', 'linha': L[i]['n'], 'titulo': f"NF-e {p[7]}: valor do XML diferente do C100",
                         'detalhe': f"XML R$ {ec._brl(nf['vnf'])} × C100 R$ {ec._brl(info['valor'])}. A nota ficou como estava — confira qual está certo."})
            continue
        alvos.append((info, nf))
    raiz_cnpj = (ec._partes(L[0]['txt'])[8] if L and ec._reg(L[0]) == '0000' else '')[:8]
    for ch, nf in notas.items():
        if ch in chaves_arq or nf['tp'] != '1' or nf['mod'] != '55' or (raiz_cnpj and nf['emit'][:8] != raiz_cnpj):
            continue
        cancelada = ch in canc or nf['status'] in ('101', '135', '151', '155')
        res['xml_sem_nota'].append({'chave': ch, 'num': nf['num'], 'data': nf['data'], 'valor': nf['vnf'], 'cfops': nf['cfops'],
                                    'emit': nf['emit'], 'cancelada': cancelada,
                                    'motivo': 'cancelada' if cancelada else ('NF-e de cupom fiscal / NFC-e (5929/6929): a receita já está na NFC-e'
                                                                             if all(c[1:] == '929' for c in nf['cfops']) else 'não está no arquivo')})
    if not alvos:
        return L, res

    blocos = ec._blocos_0140(L)
    # cadastros já existentes por estabelecimento
    cad = defaultdict(dict)        # est -> {cod: ncm}
    unids = defaultdict(set)
    for cnpj, (a, b) in blocos.items():
        for k in range(a, b + 1):
            r = ec._reg(L[k])
            if r == '0200':
                p = ec._partes(L[k]['txt'])
                cad[cnpj][p[1]] = re.sub(r'\D', '', p[7] if len(p) > 7 else '')
            elif r == '0190':
                unids[cnpj].add(ec._partes(L[k]['txt'])[1])
    novos_0200, novas_0190 = defaultdict(dict), defaultdict(dict)

    # 1) itens (de baixo para cima: incluir linhas não desloca as notas de cima)
    tot = defaultdict(float)
    m400 = defaultdict(float)            # (cst, nat) -> receita
    lc224 = []                           # (chave, data, base_pis, base_cof) — documentos com CST 06 na redução linear
    for info, nf in sorted(alvos, key=lambda x: -x[0]['i']):
        e = info['est']
        linhas, soma_p, soma_c, doc06 = [], 0.0, 0.0, 0.0
        regras = Counter()
        for it in nf['itens']:
            cod = re.sub(r'[|]', '', it['cod'] or it['descr'][:20]).strip()[:60] or f"ITEM{it['n']}"
            ja = cad[e].get(cod, novos_0200[e].get(cod, (None,))[0] if cod in novos_0200[e] else None)
            if ja is not None and ja != it['ncm']:
                cod = f"{cod[:50]}-{it['ncm']}"
                ja = cad[e].get(cod) if cod in cad[e] else (novos_0200[e][cod][0] if cod in novos_0200[e] else None)
            un = _um(it['unid'])
            if un not in unids[e] and un not in novas_0190[e]:
                novas_0190[e][un] = it['unid'] or un
            if ja is None:
                novos_0200[e][cod] = (it['ncm'], it)
            cst, nat, origem = _cst_item(it, ncm_cst)
            regras[(cst, origem)] += 1
            vitem, vdesc = round(it['vprod'], 2), round(it['vdesc'], 2)
            icms_proprio = it['vicms'] if it['cst_icms'] not in ('60', '61', '500') else 0.0
            if cst in _CST_SEM_RECEITA:
                base = 0.0
            else:
                base = round(max(0.0, vitem - vdesc - icms_proprio), 2)
            vp = round(base * a_p / 100, 2) if cst == '01' else 0.0
            vc = round(base * a_c / 100, 2) if cst == '01' else 0.0
            ap = ec._fmt(a_p, 4) if cst == '01' else '0,0000'
            ac = ec._fmt(a_c, 4) if cst == '01' else '0,0000'
            conta = (cta_cst.get(cst) or Counter({'': 1})).most_common(1)[0][0]
            cst_icms = (it['orig'] or '0') + (it['cst_icms'] or '90')[-2:] if len(it['cst_icms'] or '') <= 2 else it['cst_icms'][:3]
            item = ['C170', it['n'], cod, it['descr'][:255].replace('|', ' '), ec._fmt(it['qtd'], 5), un, ec._fmt(vitem), ec._fmt(vdesc), '0',
                    cst_icms, it['cfop'], '', ec._fmt(it['vbc']), ec._fmt(it['picms']), ec._fmt(it['vicms']),
                    ec._fmt(it['vbcst']), ec._fmt(it['picmsst']), ec._fmt(it['vicmsst']), '', '', '', '0,00', '0,00', ec._fmt(it['vipi']),
                    cst, ec._fmt(base), ap, '', '', ec._fmt(vp), cst, ec._fmt(base), ac, '', '', ec._fmt(vc), conta]
            linhas.append(ec._monta(item))
            if cst not in _CST_FORA_C100:
                soma_p += vp
                soma_c += vc
            if cst == '01':
                tot['rec01'] += vitem
                tot['base01'] += base
                tot['vp'] += vp
                tot['vc'] += vc
            elif cst not in _CST_SEM_RECEITA:
                n4 = nat or nat_cst.get(cst, '')
                m400[(cst, n4)] += vitem
                if cst == '06':
                    st, _ = classifica_ncm(it['ncm'])
                    if st != 'fora' and not ZFM_ALC.get(part_mun.get(info['part'], '')):
                        doc06 += base
            res['itens'] += 1
            res['por_cst'][cst] = round(res['por_cst'].get(cst, 0.0) + vitem, 2)
        for k, v in regras.items():
            res['regras'][f'{k[0]} · {k[1]}'] = res['regras'].get(f'{k[0]} · {k[1]}', 0) + v
        if doc06 > 0:
            lc224.append((info['chave'], info['data'], round(doc06, 2)))
        # posição: depois do C100 e dos filhos C110…C120
        j = info['i'] + 1
        while j < len(L) and ec._reg(L[j]) in ('C110', 'C111', 'C112', 'C113', 'C114', 'C115', 'C116', 'C120'):
            j += 1
        for k, t in enumerate(linhas):
            L.insert(j + k, {'n': L[info['i']]['n'], 'txt': t, 'novo': True})
        pc = ec._partes(L[info['i']]['txt'])
        antes = L[info['i']]['txt']
        pc[25], pc[26] = ec._fmt(round(soma_p, 2)), ec._fmt(round(soma_c, 2))
        L[info['i']]['txt'] = ec._monta(pc)
        res['corrigidas'].append({'linha': L[info['i']]['n'], 'num': info['num'], 'data': info['data'], 'valor': info['valor'],
                                  'itens': len(linhas), 'pis': round(soma_p, 2), 'cofins': round(soma_c, 2),
                                  'cst': dict(Counter(ec._partes(t)[24] for t in linhas))})
        acoes.append({'cat': 'xml_itens', 'tipo': 'incluido', 'linha': L[info['i']]['n'], 'registro': 'C170', 'antes': antes,
                      'depois': L[info['i']]['txt'], 'qtd': len(linhas),
                      'motivo': f"NF-e {info['num']}: {len(linhas)} item(ns) incluído(s) pelo XML"
                                + (f" · PIS R$ {ec._brl(soma_p)} · COFINS R$ {ec._brl(soma_c)}" if soma_p or soma_c else ' · sem PIS/COFINS a recolher')})
    res['corrigidas'].sort(key=lambda x: x['linha'] or 0)
    res['receita'] = round(sum(x['valor'] for x in res['corrigidas']), 2)
    res['pis'], res['cofins'] = round(tot['vp'], 2), round(tot['vc'], 2)

    # 2) cadastros 0190 e 0200 no bloco 0140 de cada estabelecimento (de baixo para cima)
    blocos = ec._blocos_0140(L)
    for cnpj in sorted(set(novos_0200) | set(novas_0190), key=lambda c: -(blocos.get(c, (0, 0))[0])):
        if cnpj not in blocos:
            pend.append({'cat': 'xml_itens', 'linha': None, 'titulo': f'Estabelecimento {cnpj} sem registro 0140',
                         'detalhe': 'Os produtos das notas não puderam ser cadastrados (0200). Confira o bloco 0.'})
            continue
        a, b = blocos[cnpj]
        regs = [ec._reg(L[k]) for k in range(a, b + 1)]
        # 0190 entra depois do último 0150/0190; 0200 depois do último 0150/0190/0200 (ordem do leiaute)
        pos190 = a + max([k for k, r in enumerate(regs) if r in ('0140', '0145', '0150', '0190')] or [0])
        novas = [ec._monta(['0190', u, _UNID_DESC.get(u, (d or u)[:60].upper().replace('|', ' '))]) for u, d in sorted(novas_0190.get(cnpj, {}).items())]
        for k, t in enumerate(novas):
            L.insert(pos190 + 1 + k, {'n': L[pos190]['n'], 'txt': t, 'novo': True})
            acoes.append({'cat': 'xml_itens', 'tipo': 'incluido', 'linha': L[pos190]['n'], 'registro': '0190', 'antes': '', 'depois': t,
                          'motivo': 'Unidade dos itens das NF-e (XML) que não existia neste estabelecimento.'})
        b += len(novas)
        regs = [ec._reg(L[k]) for k in range(a, b + 1)]
        pos200 = a + max([k for k, r in enumerate(regs) if r in ('0140', '0145', '0150', '0190', '0200', '0205', '0206', '0208')] or [0])
        novos = []
        for cod, (ncm, it) in sorted(novos_0200.get(cnpj, {}).items()):
            ean = it['ean'] if re.fullmatch(r'\d{8,14}', it['ean'] or '') else ''
            novos.append(ec._monta(['0200', cod, it['descr'][:255].replace('|', ' '), ean, '', _um(it['unid']), '00', ncm, '', ncm[:2], '', '']))
        for k, t in enumerate(novos):
            L.insert(pos200 + 1 + k, {'n': L[pos200]['n'], 'txt': t, 'novo': True})
            acoes.append({'cat': 'xml_itens', 'tipo': 'incluido', 'linha': L[pos200]['n'], 'registro': '0200', 'antes': '', 'depois': t,
                          'motivo': 'Produto das NF-e (XML) cadastrado no estabelecimento (o 0200 é de cada 0140).'})
        res.setdefault('cadastros', {})[cnpj] = {'produtos': len(novos), 'unidades': len(novas)}

    # 3) apuração
    cod_cont = '51' if regime == 'cum' else '01'
    if tot['rec01'] or tot['vp']:
        for r210, kv in (('M210', 'vp'), ('M610', 'vc')):
            i = next((i for i, l in enumerate(L) if ec._reg(l) == r210 and ec._partes(l['txt'])[1] == cod_cont), None)
            if i is None:
                pend.append({'cat': 'xml_itens', 'linha': None, 'titulo': f'{r210} com COD_CONT {cod_cont} não existe',
                             'detalhe': f'A contribuição dos itens tributados (R$ {ec._brl(tot[kv])}) não entrou na apuração: gere a apuração de novo no PVA.'})
                continue
            p = ec._partes(L[i]['txt'])
            antes = L[i]['txt']
            p[2] = ec._fmt(ec._num(p[2]) + tot['rec01'])
            p[3] = ec._fmt(ec._num(p[3]) + tot['base01'])
            p[6] = ec._fmt(ec._num(p[6]) + tot['base01'])
            p[10] = ec._fmt(ec._num(p[10]) + tot[kv])
            p[15] = ec._fmt(ec._num(p[15]) + tot[kv])
            L[i]['txt'] = ec._monta(p)
            acoes.append({'cat': 'xml_itens', 'tipo': 'alterado', 'linha': L[i]['n'], 'registro': r210, 'antes': antes, 'depois': L[i]['txt'],
                          'motivo': f'Receita tributada dos itens incluídos: + R$ {ec._brl(tot["rec01"])} de receita, + R$ {ec._brl(tot[kv])} de contribuição.'})
    # redução linear (LC 224/2025) sobre o CST 06
    comp = (ec._partes(L[0]['txt'])[5] if L and ec._reg(L[0]) == '0000' else '')
    if lc224 and comp[4:] + comp[2:4] >= '202604':
        ap, acf = ALIQ_LC224[regime]
        for trib, r210, r220, r225, aliq, cta_pad in (('PIS', 'M210', 'M220', 'M225', ap, ''), ('COFINS', 'M610', 'M620', 'M625', acf, '')):
            i210 = next((i for i, l in enumerate(L) if ec._reg(l) == r210 and ec._partes(l['txt'])[1] == cod_cont), None)
            if i210 is None:
                continue
            # M220 código 11 dentro do grupo deste M210
            j = i210 + 1
            i220 = None
            while j < len(L) and ec._reg(L[j])[:2] == r210[:2] and ec._reg(L[j])[2:] in ('11', '15', '20', '25', '30'):
                if ec._reg(L[j]) == r220 and ec._partes(L[j]['txt'])[3] == '11':
                    i220 = j
                j += 1
            ctas = Counter(ec._partes(l['txt'])[7].strip() for l in L if ec._reg(l) == r225)
            cta = ctas.most_common(1)[0][0] if ctas else cta_pad
            dets = [ec._monta([r225, ec._fmt(round(b * aliq / 100, 2)), '06', ec._fmt(b), ec._fmt(aliq, 3), d, f'Chave de acesso: {ch}', cta, ''])
                    for ch, d, b in sorted(lc224, key=lambda x: (x[1][4:] + x[1][2:4] + x[1][:2], x[0]))]
            soma = round(sum(round(b * aliq / 100, 2) for _, _, b in lc224), 2)
            if not soma:
                continue
            if i220 is None:
                fim = comp and ec._partes(L[0]['txt'])[6]
                pos = i210 + 1
                while pos < len(L) and ec._reg(L[pos])[:2] == r210[:2] and ec._reg(L[pos])[2:] in ('11', '15'):
                    pos += 1
                L.insert(pos, {'n': L[i210]['n'], 'txt': ec._monta([r220, '1', ec._fmt(soma), '11', '', 'Redução linear de benefícios fiscais - LC 224/2025', fim]), 'novo': True})
                i220 = pos
            else:
                p = ec._partes(L[i220]['txt'])
                p[2] = ec._fmt(ec._num(p[2]) + soma)
                L[i220]['txt'] = ec._monta(p)
            k = i220 + 1
            while k < len(L) and ec._reg(L[k]) == r225:
                k += 1
            for n_, t in enumerate(dets):
                L.insert(k + n_, {'n': L[i220]['n'], 'txt': t, 'novo': True})
            p = ec._partes(L[i210]['txt'])
            antes = L[i210]['txt']
            p[11] = ec._fmt(ec._num(p[11]) + soma)
            p[15] = ec._fmt(ec._num(p[15]) + soma)
            L[i210]['txt'] = ec._monta(p)
            res.setdefault('lc224', {})[trib] = soma
            acoes.append({'cat': 'xml_itens', 'tipo': 'alterado', 'linha': L[i210]['n'], 'registro': r220, 'antes': antes, 'depois': L[i210]['txt'],
                          'motivo': f'Redução linear da LC 224/2025 sobre a receita com CST 06 das notas incluídas: + R$ {ec._brl(soma)} ({len(dets)} detalhamento(s) {r225}).'})
    # M400/M410 e M800/M810
    for (cst, nat), v in sorted(m400.items()):
        for r400, r410, limite in (('M400', 'M410', 400), ('M800', 'M810', 800)):
            _soma_rec(L, r400, r410, limite, cst, nat, round(v, 2), acoes)
    for trib in ('PIS', 'COFINS'):
        ec._recalc_m200(L, trib, ctx, 'Recalculado depois da inclusão dos itens pelos XMLs.')
    _acerta_m205(L, regime)
    return L, res


def _soma_rec(L, r400, r410, limite, cst, nat, v, acoes):
    idx = [i for i, l in enumerate(L) if ec._reg(l) == r400 and ec._partes(l['txt'])[1] == cst]
    if not idx:
        pos = next((i for i, l in enumerate(L) if ec._reg(l)[:1] == 'M' and ec._reg(l)[1:].isdigit()
                    and int(ec._reg(l)[1:]) >= limite and ec._reg(l) not in (r400, r410)), None)
        if pos is None:
            return
        L.insert(pos, {'n': None, 'txt': ec._monta([r400, cst, ec._fmt(v), '', '']), 'novo': True})
        L.insert(pos + 1, {'n': None, 'txt': ec._monta([r410, nat, ec._fmt(v), '', '']), 'novo': True})
        acoes.append({'cat': 'xml_itens', 'tipo': 'incluido', 'linha': None, 'registro': r400, 'antes': '', 'depois': L[pos]['txt'],
                      'motivo': f'Receita com CST {cst} (natureza {nat or "—"}) das notas incluídas pelo XML.'})
        return
    # prefere o M400 deste CST que já tem a natureza (ou o primeiro, sem conta = como o C170 incluído)
    alvo = None
    for i400 in idx:
        j = i400 + 1
        while j < len(L) and ec._reg(L[j]) == r410:
            if ec._partes(L[j]['txt'])[1] == nat:
                alvo = (i400, j)
                break
            j += 1
        if alvo:
            break
    if alvo is None:
        i400 = next((i for i in idx if not ec._partes(L[i]['txt'])[3].strip()), idx[0])
        j = i400 + 1
        while j < len(L) and ec._reg(L[j]) == r410:
            j += 1
        cta = ec._partes(L[i400 + 1]['txt'])[3] if i400 + 1 < len(L) and ec._reg(L[i400 + 1]) == r410 else ''
        L.insert(j, {'n': L[i400]['n'], 'txt': ec._monta([r410, nat, ec._fmt(v), cta, '']), 'novo': True})
        alvo = (i400, None)
    i400, j410 = alvo
    p = ec._partes(L[i400]['txt'])
    antes = L[i400]['txt']
    p[2] = ec._fmt(ec._num(p[2]) + v)
    L[i400]['txt'] = ec._monta(p)
    if j410 is not None:
        q = ec._partes(L[j410]['txt'])
        q[2] = ec._fmt(ec._num(q[2]) + v)
        L[j410]['txt'] = ec._monta(q)
    acoes.append({'cat': 'xml_itens', 'tipo': 'alterado', 'linha': L[i400]['n'], 'registro': r400, 'antes': antes, 'depois': L[i400]['txt'],
                  'motivo': f'+ R$ {ec._brl(v)} de receita com CST {cst} (natureza {nat or "—"}) das notas incluídas pelo XML.'})


def _acerta_m205(L, regime):
    """M205/M605 acompanham o M200/M600 (campo 08 não cumulativo, 12 cumulativo), para mais ou para menos."""
    cods = {('PIS', '08'): '691201', ('PIS', '12'): '810902', ('COFINS', '08'): '585601', ('COFINS', '12'): '217201'}
    for trib, r200, r205 in (('PIS', 'M200', 'M205'), ('COFINS', 'M600', 'M605')):
        i200 = next((i for i, l in enumerate(L) if ec._reg(l) == r200), None)
        if i200 is None:
            continue
        m = ec._partes(L[i200]['txt'])
        for campo, pos in (('08', 7), ('12', 11)):
            novo = round(ec._num(m[pos]), 2)
            idxs = [i for i, l in enumerate(L) if ec._reg(l) == r205 and ec._partes(l['txt'])[1] == campo]
            atual = round(sum(ec._num(ec._partes(L[i]['txt'])[3]) for i in idxs), 2)
            dif = round(novo - atual, 2)
            if abs(dif) < 0.005:
                continue
            if dif > 0:
                if idxs:
                    p = ec._partes(L[idxs[0]]['txt'])
                    p[3] = ec._fmt(ec._num(p[3]) + dif)
                    L[idxs[0]]['txt'] = ec._monta(p)
                else:
                    k = i200 + 1
                    while k < len(L) and ec._reg(L[k]) == r205:
                        k += 1
                    L.insert(k, {'n': L[i200]['n'], 'txt': ec._monta([r205, campo, cods[(trib, campo)], ec._fmt(dif)]), 'novo': True})
            else:
                falta = -dif
                for i in sorted(idxs, key=lambda i: -ec._num(ec._partes(L[i]['txt'])[3])):
                    if falta <= 0.004:
                        break
                    p = ec._partes(L[i]['txt'])
                    v = ec._num(p[3])
                    tira = min(v, falta)
                    p[3] = ec._fmt(v - tira)
                    falta = round(falta - tira, 2)
                    L[i]['txt'] = ec._monta(p)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FiscoCont+ — Núcleo Fiscal
- Lê o SPED Fiscal (.txt, EFD ICMS/IPI) e monta os dados de apuração/CFOP/rankings.
- Lê XMLs de NF-e de entrada e concilia com o SPED (registro C100) pela chave de 44 dígitos.
- Gera dois relatórios HTML (animados, autocontidos):
    * Dashboard do cliente (apuração ICMS).
    * Conferência NF-e Entradas × SPED (uso interno).

CLI:
  fiscal_core.py sped ARQ.txt --json saida.json
  fiscal_core.py sped ARQ.txt --dashboard-html saida.html
  fiscal_core.py conferencia ARQ.txt --xmls PASTA_OU_ARQS --json saida.json
  fiscal_core.py conferencia ARQ.txt --xmls PASTA_OU_ARQS --html saida.html
"""
import sys, os, re, json, glob, base64, math, html as _html, zipfile, tempfile
import pdfplumber

# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _nome_exibicao(path):
    """Nome do arquivo pra exibição — trata o caminho virtual de dentro de
    zip ("zip::interno") separadamente, senão o basename ficava inconsistente
    conforme o XML tinha ou não subpasta dentro do zip."""
    if '::' in path:
        return os.path.basename(path.split('::', 1)[1])
    return os.path.basename(path)


def _read_text(path):
    # Se o caminho aponta pra dentro de um .zip (marcado com "::", ver
    # `coletar_xmls`), lê direto da memória sem nunca extrair o XML pro
    # disco — evita que o antivírus do Windows escaneie cada arquivinho
    # solto, que era o gargalo real em volumes grandes.
    if '::' in path:
        caminho_zip, nome_interno = path.split('::', 1)
        with zipfile.ZipFile(caminho_zip) as z:
            raw = z.read(nome_interno)
    else:
        raw = open(path, 'rb').read()
    for enc in ('utf-8-sig', 'utf-8', 'latin-1'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('latin-1', 'replace')

def _num(s):
    s = (s or '').strip()
    if not s:
        return 0.0
    try:
        return float(s.replace('.', '').replace(',', '.'))
    except ValueError:
        return 0.0

def _brl(v):
    return f'{(v or 0):,.2f}'.replace(',', '§').replace('.', ',').replace('§', '.')

def _brl0(v):
    return f'{(v or 0):,.0f}'.replace(',', '.')

def _esc(s):
    return _html.escape('' if s is None else str(s))

def _campo(bloco, tag):
    m = re.search(rf'<{tag}>(.*?)</{tag}>', bloco or '', re.S)
    return m.group(1).strip() if m else ''

def _numx(s):
    """Converte float no formato de XML (ponto decimal) — diferente de
    _num(), que é pra formato SPED (vírgula decimal)."""
    try:
        return float((s or '0').strip() or 0)
    except ValueError:
        return 0.0

def _fmt_cnpj(c):
    c = re.sub(r'\D', '', c or '')
    if len(c) != 14:
        return c
    return f'{c[0:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:14]}'

def _dt(s):
    s = (s or '').strip()
    return f'{s[0:2]}/{s[2:4]}/{s[4:8]}' if len(s) == 8 else s

_ENTRADA_CFOP = ('1', '2', '3')
_SAIDA_CFOP = ('5', '6', '7')

# --- Classificação de CFOP para Faturamento e VAF -------------------------- #
# Vendas (receita) — saídas de comercialização/produção/combustível e serviço.
_CFOP_VENDA = {
    '5101', '5102', '5103', '5104', '5105', '5106', '5109', '5110', '5111', '5112',
    '5113', '5114', '5115', '5116', '5117', '5118', '5119', '5120', '5122', '5123',
    '5124', '5125', '5401', '5402', '5403', '5405', '5651', '5652', '5653', '5654',
    '5655', '5656', '5667', '5933',
    '6101', '6102', '6103', '6104', '6105', '6106', '6107', '6108', '6109', '6110',
    '6111', '6112', '6113', '6114', '6115', '6116', '6117', '6118', '6119', '6120',
    '6122', '6123', '6124', '6125', '6401', '6403', '6404', '6651', '6652', '6653',
    '6654', '6655', '6656', '6667', '6933',
    '7101', '7102', '7105', '7106', '7127', '7651', '7667',
}
# Devoluções de venda (entram como entrada) — abatem as vendas
_CFOP_DEV_VENDA = {
    '1201', '1202', '1203', '1204', '1410', '1411', '1660', '1661', '1662',
    '2201', '2202', '2203', '2204', '2410', '2411', '2660', '2661', '2662',
}
# Compras de mercadoria/insumo/combustível PARA COMERCIALIZAÇÃO/INDUSTRIALIZAÇÃO
_CFOP_COMPRA_VAF = {
    '1101', '1102', '1111', '1113', '1116', '1117', '1118', '1121', '1122',
    '1401', '1403', '1651', '1652',
    '2101', '2102', '2111', '2113', '2116', '2117', '2118', '2121', '2122',
    '2401', '2403', '2651', '2652',
}
# Devoluções de compra (saem como saída) — abatem as compras
_CFOP_DEV_COMPRA = {'5201', '5202', '5210', '5410', '5411', '6201', '6202', '6210', '6410', '6411'}
# Uso e consumo / imobilizado — FORA do VAF
# 1407/2407 = "compra de mercadoria PARA USO OU CONSUMO sujeita a ST" — é uso/consumo,
# nunca revenda (confirmado em múltiplas fontes; o nome do próprio CFOP já diz isso).
_CFOP_USO_CONSUMO = {'1556', '2556', '1653', '2653', '1557', '2557', '1407', '2407'}
_CFOP_IMOBILIZADO = {'1551', '2551', '1552', '2552', '1406', '1604'}

def _classe_cfop(c):
    if c in _CFOP_VENDA: return 'venda'
    if c in _CFOP_DEV_VENDA: return 'dev_venda'
    if c in _CFOP_DEV_COMPRA: return 'dev_compra'
    if c in _CFOP_USO_CONSUMO: return 'uso_consumo'
    if c in _CFOP_IMOBILIZADO: return 'imobilizado'
    if c in _CFOP_COMPRA_VAF: return 'compra'
    first = c[0] if c else ''
    if first in _SAIDA_CFOP: return 'outra_saida'
    if first in _ENTRADA_CFOP: return 'outra_entrada'
    return 'outro'

_CFOP_DESC = {
    '1101': 'Compra p/ industrialização', '1102': 'Compra p/ comercialização',
    '1401': 'Compra p/ comerc. · ST', '1403': 'Compra comerc. c/ ret. ST',
    '1407': 'Compra p/ industr. · ST', '1556': 'Compra material uso/consumo',
    '1653': 'Combustível uso e consumo', '2101': 'Compra industr. (outra UF)',
    '2102': 'Compra comerc. (outra UF)', '2403': 'Compra comerc. ST (outra UF)',
    '5101': 'Venda de produção', '5102': 'Venda de mercadoria',
    '5405': 'Venda merc. c/ ST (subst.)', '5403': 'Venda merc. c/ ST (subst.)',
    '6101': 'Venda de produção (outra UF)', '6102': 'Venda de mercadoria (outra UF)',
    '5405 ': 'Venda merc. c/ ST',
}

def _cfop_desc(c):
    return _CFOP_DESC.get(c, 'CFOP ' + c)

# Tabela oficial de motivos de desoneração do ICMS (campo motDesICMS da NF-e)
_MOT_DESON = {
    '1': 'Táxi', '3': 'Produtor agropecuário', '4': 'Frotista/locadora',
    '5': 'Diplomático/consular', '6': 'Utilitários/motocicletas · Amazônia Ocidental',
    '7': 'SUFRAMA', '8': 'Venda a órgão público', '9': 'Outros',
    '10': 'Deficiente condutor', '11': 'Deficiente não condutor',
    '12': 'Órgão de fomento agropecuário', '13': 'Substituição tributária',
    '14': 'ICMS diferido', '15': 'Uso na agropecuária', '16': 'Recicláveis', '90': 'Outros',
}

def _mot_deson_desc(c):
    return _MOT_DESON.get(c, f'Motivo {c}')

# --------------------------------------------------------------------------- #
# Parser do SPED Fiscal
# --------------------------------------------------------------------------- #
def parse_sped(path):
    txt = _read_text(path)
    empresa = {}
    participantes = {}   # COD_PART -> {nome, cnpj}
    produtos = {}        # COD_ITEM -> descr
    ncm_por_item = {}    # COD_ITEM -> NCM (p/ Auditor de Classificação Fiscal)
    entradas = {}        # CHV -> {num, serie, cod_part, vl, dt, fornecedor}
    saidas_idx = {}       # CHV -> {num, serie, cod_part, vl, dt, cliente} (só NF-e/NFC-e de saída, C100 ind_oper=1)
    saidas_total = 0.0
    entradas_total = 0.0
    dev_venda = 0.0
    dev_compra = 0.0
    cfop = {}            # cfop -> {valor, docs:set, tipo}
    apur = {}
    ajustes = []
    forn_val = {}        # cod_part -> soma entradas
    prod_val = {}        # cod_item -> soma (entradas)
    cfop_por_chave = {}  # chave -> {cfop: valor} (do C170, item a item)
    cst_por_chave = {}   # chave -> {cst_2digitos: valor} (do C170, item a item)
    itens_c170 = []      # lista bruta de itens de entrada (p/ Auditor de Classificação Fiscal)
    documentos = []      # lista de documentos de ENTRADA (NF-e / CT-e / NF3-e)
    cfop_c190_por_chave = {}  # chave -> [(cfop, valor_operacao), ...] — entrada E saída, p/ Remessa×Retorno

    def _g(i):
        return f[i] if i < len(f) else ''

    cur = None           # C100 atual: (tipo, chave, cod_part, doc_key)
    for ln in txt.splitlines():
        if not ln or ln[0] != '|':
            continue
        f = ln.split('|')
        reg = f[1] if len(f) > 1 else ''

        if reg == '0000':
            empresa = {
                'periodo_ini': _dt(f[4]), 'periodo_fim': _dt(f[5]),
                'periodo': f'{_dt(f[4])} a {_dt(f[5])}',
                'empresa': f[6].strip(), 'cnpj': f[7].strip(), 'uf': f[9].strip(),
                'ie': f[10].strip(),
            }
        elif reg == '0150':
            participantes[f[2]] = {'nome': f[3].strip(), 'cnpj': (f[5] or f[6] or '').strip()}
        elif reg == '0200':
            produtos[f[2]] = f[3].strip()
            if len(f) > 8 and f[8].strip():
                ncm_por_item[f[2]] = f[8].strip()
        elif reg == 'C100':
            ind_oper = f[2]           # 0=entrada, 1=saída
            cod_mod = f[5]
            ser = f[7]
            num = f[8]
            chv = f[9].strip()
            vl = _num(f[12])
            cod_part = f[4]
            tipo = 'entrada' if ind_oper == '0' else 'saida'
            doc_key = chv or f'{cod_mod}-{ser}-{num}-{cod_part}'
            cur = (tipo, chv, cod_part, doc_key)
            if tipo == 'entrada':
                entradas_total += vl
                if chv:
                    entradas[chv] = {
                        'num': num, 'serie': ser, 'cod_part': cod_part, 'vl': vl,
                        'dt': _dt(f[10]), 'modelo': cod_mod,
                        'fornecedor': participantes.get(cod_part, {}).get('nome', cod_part),
                    }
                if cod_mod in ('55', '01', '1B', '04'):
                    documentos.append({
                        'tipo': 'NF-e', 'ordem': 1, 'data': _dt(f[10]), 'chave': chv,
                        'num': num, 'valor': vl,
                        'icms': _num(_g(22)),
                        'fornecedor': participantes.get(cod_part, {}).get('nome', cod_part),
                    })
                forn_val[cod_part] = forn_val.get(cod_part, 0.0) + vl
            else:
                saidas_total += vl
                if chv:
                    saidas_idx[chv] = {
                        'num': num, 'serie': ser, 'cod_part': cod_part, 'vl': vl,
                        'dt': _dt(f[10]), 'modelo': cod_mod,
                        'cliente': participantes.get(cod_part, {}).get('nome', cod_part),
                    }
        elif reg == 'C170':
            # item pertence ao C100 atual; soma só p/ entradas (ranking de compras)
            if cur and cur[0] == 'entrada':
                cod_item = f[3]
                vlit = _num(f[7])
                prod_val[cod_item] = prod_val.get(cod_item, 0.0) + vlit
                cfop_item = f[11].strip() if len(f) > 11 else ''
                cst_raw = f[10].strip() if len(f) > 10 else ''
                cst_item = cst_raw[-2:] if len(cst_raw) >= 2 else cst_raw  # campo vem "Origem+CST" (3 díg.)
                chv_atual = cur[1]
                if chv_atual and cfop_item:
                    dch = cfop_por_chave.setdefault(chv_atual, {})
                    dch[cfop_item] = dch.get(cfop_item, 0.0) + vlit
                if chv_atual and cst_item:
                    dcst = cst_por_chave.setdefault(chv_atual, {})
                    dcst[cst_item] = dcst.get(cst_item, 0.0) + vlit
                if chv_atual and cod_item and cfop_item:
                    itens_c170.append({
                        'cod_item': cod_item, 'cfop': cfop_item, 'cst': cst_item,
                        'valor': vlit, 'chave': chv_atual,
                    })
        elif reg == 'C190':
            c = f[3].strip()
            vlop = _num(f[5])
            if not c:
                continue
            d = cfop.setdefault(c, {'valor': 0.0, 'docs': set(), 'tipo': None})
            d['valor'] += vlop
            if cur:
                d['docs'].add(cur[3])
                if cur[1]:  # chave da nota atual — p/ Remessa×Retorno (funciona com ou sem C170 detalhado)
                    cfop_c190_por_chave.setdefault(cur[1], []).append((c, vlop))
            first = c[0] if c else ''
            d['tipo'] = 'entrada' if first in _ENTRADA_CFOP else ('saida' if first in _SAIDA_CFOP else 'outro')
        elif reg == 'D100':
            ind_oper = _g(2); cod_mod = _g(5)
            chv = _g(10).strip()
            cur = ('entrada' if ind_oper == '0' else 'saida', chv, _g(4),
                   chv or f'{cod_mod}-{_g(7)}-{_g(9)}-{_g(4)}')
            if ind_oper == '0':
                entradas_total += _num(_g(15))
                documentos.append({
                    'tipo': 'CT-e', 'ordem': 2, 'data': _dt(_g(11)), 'chave': chv,
                    'num': _g(9), 'valor': _num(_g(15)), 'icms': _num(_g(20)),
                    'fornecedor': participantes.get(_g(4), {}).get('nome', _g(4)),
                })
            else:
                saidas_total += _num(_g(15))
        elif reg == 'D190':
            c = _g(3).strip(); vlop = _num(_g(5))
            if c:
                d = cfop.setdefault(c, {'valor': 0.0, 'docs': set(), 'tipo': None})
                d['valor'] += vlop
                if cur:
                    d['docs'].add(cur[3])
                first = c[0] if c else ''
                d['tipo'] = 'entrada' if first in _ENTRADA_CFOP else ('saida' if first in _SAIDA_CFOP else 'outro')
        elif reg == 'C500':
            ind_oper = _g(2); cod_mod = _g(5)
            chv = _g(29).strip()
            cur = ('entrada' if ind_oper == '0' else 'saida', chv, _g(4),
                   chv or f'{cod_mod}-{_g(7)}-{_g(10)}-{_g(4)}')
            if ind_oper == '0':
                entradas_total += _num(_g(13))
                if cod_mod == '66':
                    tipo_doc = 'NF3-e'
                elif cod_mod == '62':
                    tipo_doc = 'NFCom'
                else:
                    tipo_doc = 'Energia/Com.'  # modelos antigos em papel (03/06/21/22/28)
                documentos.append({
                    'tipo': tipo_doc,
                    'ordem': 3, 'data': _dt(_g(11)), 'chave': chv,
                    'num': _g(10), 'valor': _num(_g(13)), 'icms': _num(_g(20)),
                    'fornecedor': participantes.get(_g(4), {}).get('nome', _g(4)),
                })
            else:
                saidas_total += _num(_g(13))
        elif reg == 'C590':
            c = _g(3).strip(); vlop = _num(_g(5))
            if c:
                d = cfop.setdefault(c, {'valor': 0.0, 'docs': set(), 'tipo': None})
                d['valor'] += vlop
                if cur:
                    d['docs'].add(cur[3])
                first = c[0] if c else ''
                d['tipo'] = 'entrada' if first in _ENTRADA_CFOP else ('saida' if first in _SAIDA_CFOP else 'outro')
        elif reg == 'E110':
            apur = {
                'debitos': _num(f[2]),
                'aj_debitos': _num(f[4]),
                'creditos': _num(f[6]),
                'aj_creditos': _num(f[8]),
                'saldo_apurado': _num(f[11]),
                'deducoes': _num(f[12]),
                'icms_recolher': _num(f[13]),
                'saldo_credor_transp': _num(f[14]),
            }
        elif reg == 'E111':
            v = _num(f[4])
            if v:
                ajustes.append({'codigo': f[2].strip(), 'descricao': f[3].strip(), 'valor': v})

    # ---- CFOP agregado (compras/vendas) ----
    compras = []
    vendas = []
    for c, d in cfop.items():
        row = {'cfop': c, 'desc': _cfop_desc(c), 'valor': round(d['valor'], 2), 'nfs': len(d['docs'])}
        if d['tipo'] == 'entrada':
            compras.append(row)
        elif d['tipo'] == 'saida':
            vendas.append(row)
    compras.sort(key=lambda r: -r['valor'])
    vendas.sort(key=lambda r: -r['valor'])

    # ---- rankings ----
    forn = sorted(
        ({'nome': participantes.get(cp, {}).get('nome', cp), 'valor': round(v, 2)}
         for cp, v in forn_val.items()), key=lambda r: -r['valor'])[:8]
    prod = sorted(
        ({'nome': produtos.get(ci, ci), 'valor': round(v, 2)}
         for ci, v in prod_val.items()), key=lambda r: -r['valor'])[:10]

    # ---- Faturamento e VAF por CLASSIFICAÇÃO de CFOP ----
    vl_venda = sum(d['valor'] for c, d in cfop.items() if c in _CFOP_VENDA)
    vl_dev_venda = sum(d['valor'] for c, d in cfop.items() if c in _CFOP_DEV_VENDA)
    vl_compra_vaf = sum(d['valor'] for c, d in cfop.items() if c in _CFOP_COMPRA_VAF)
    vl_dev_compra = sum(d['valor'] for c, d in cfop.items() if c in _CFOP_DEV_COMPRA)
    vl_uso_consumo = sum(d['valor'] for c, d in cfop.items() if c in _CFOP_USO_CONSUMO)
    vl_imobilizado = sum(d['valor'] for c, d in cfop.items() if c in _CFOP_IMOBILIZADO)

    faturamento = round(vl_venda, 2)                         # só CFOPs de venda
    vendas_liquidas = round(vl_venda - vl_dev_venda, 2)
    compras_liquidas = round(vl_compra_vaf - vl_dev_compra, 2)
    vaf = round(vendas_liquidas - compras_liquidas, 2)       # VAF = vendas líq. − compras líq.
    icms_rec = apur.get('icms_recolher', 0.0)
    aliq_efetiva = round((icms_rec / faturamento * 100) if faturamento else 0.0, 4)

    # ---- Lista de documentos de entrada (NF-e / CT-e / NF3-e) ----
    documentos.sort(key=lambda r: (r['ordem'], r['data'] or '', r['num'] or ''))
    resumo_tipo = {}
    for dcto in documentos:
        t = resumo_tipo.setdefault(dcto['tipo'], {'tipo': dcto['tipo'], 'ordem': dcto['ordem'],
                                                  'qtd': 0, 'valor': 0.0, 'icms': 0.0})
        t['qtd'] += 1
        t['valor'] += dcto['valor']
        t['icms'] += dcto['icms']
    resumo_tipo = sorted(resumo_tipo.values(), key=lambda r: r['ordem'])
    for t in resumo_tipo:
        t['valor'] = round(t['valor'], 2); t['icms'] = round(t['icms'], 2)
    tot_doc_valor = round(sum(d['valor'] for d in documentos), 2)
    tot_doc_icms = round(sum(d['icms'] for d in documentos), 2)

    return {
        'empresa': empresa,
        'faturamento_bruto': faturamento,
        'saidas_totais': round(saidas_total, 2),             # todas as saídas (referência)
        'entradas_brutas': round(vl_compra_vaf, 2),          # compras p/ VAF (sem uso/consumo/imob.)
        'entradas_totais': round(entradas_total, 2),         # todas as entradas (referência)
        'uso_consumo': round(vl_uso_consumo, 2),
        'imobilizado': round(vl_imobilizado, 2),
        'dev_vendas': round(vl_dev_venda, 2),
        'dev_compras': round(vl_dev_compra, 2),
        'valor_adicionado': vaf,
        'apuracao': {
            'debitos': apur.get('debitos', 0.0),
            'creditos': apur.get('creditos', 0.0),
            'ajuste_creditos': apur.get('aj_creditos', 0.0),
            'ajuste_debitos': apur.get('aj_debitos', 0.0),
            'icms_recolher': icms_rec,
            'saldo_credor_transp': apur.get('saldo_credor_transp', 0.0),
        },
        'aliquota_efetiva': aliq_efetiva,
        'ajustes_e111': ajustes,
        'compras_cfop': compras,
        'vendas_cfop': vendas,
        'saidas_cfop': vendas,
        'documentos_entrada': documentos,
        'resumo_tipo_doc': resumo_tipo,
        'total_doc_valor': tot_doc_valor,
        'total_doc_icms': tot_doc_icms,
        'top_fornecedores': forn,
        'top_produtos': prod,
        'entradas_index': entradas,      # p/ conferência (chave -> dados)
        'cfop_por_chave': cfop_por_chave,  # p/ Classificação de Frete (chave -> {cfop: valor})
        'cst_por_chave': cst_por_chave,    # p/ Classificação de Frete (chave -> {cst: valor})
        'itens_c170': itens_c170,          # p/ Auditor de Classificação Fiscal (lista bruta)
        'ncm_por_item': ncm_por_item,       # p/ Auditor de Classificação Fiscal (cod_item -> NCM)
        'produtos': produtos,                # cod_item -> descrição (p/ Auditor de Classificação Fiscal)
        'saidas_index': saidas_idx,      # p/ conferência de saídas (chave -> dados)
        'cfop_c190_por_chave': cfop_c190_por_chave,  # p/ Auditor — Remessa×Retorno (chave -> [(cfop, valor)])
        'qtd_entradas': len(entradas),
        'qtd_c100': None,
    }

# --------------------------------------------------------------------------- #
# Leitura de XMLs de NF-e
# --------------------------------------------------------------------------- #
def parse_xml(path):
    t = _read_text(path)
    chave = re.search(r'Id="NFe(\d{44})"', t)
    if not chave:
        chave = re.search(r'<chNFe>(\d{44})</chNFe>', t)
    ch = chave.group(1) if chave else ''
    vnf = re.search(r'<vNF>([\d.]+)</vNF>', t)
    nnf = re.search(r'<nNF>(\d+)</nNF>', t)
    ser = re.search(r'<serie>(\d+)</serie>', t)
    emit = re.search(r'<emit>.*?<xNome>(.*?)</xNome>', t, re.S)
    cnpj = re.search(r'<emit>.*?<CNPJ>(\d+)</CNPJ>', t, re.S)
    dest_nome = re.search(r'<dest>.*?<xNome>(.*?)</xNome>', t, re.S)
    dest_cnpj = re.search(r'<dest>.*?<CNPJ>(\d+)</CNPJ>', t, re.S)
    tp = re.search(r'<tpNF>(\d)</tpNF>', t)
    dh_emi = re.search(r'<dhEmi>(\d{4}-\d{2}-\d{2})T', t) or re.search(r'<dEmi>(\d{4}-\d{2}-\d{2})</dEmi>', t)
    data_doc = ''
    if dh_emi:
        y, m, d = dh_emi.group(1).split('-')
        data_doc = f'{d}/{m}/{y}'
    # É uma NF-e/NFC-e de verdade? (tem infNFe + emitente). Eventos/cancelamentos/
    # inutilizações apontam a chave mas não têm infNFe/emit -> não são nota.
    is_nota = bool(re.search(r'<infNFe\b', t) and emit and ch)
    modelo = ch[20:22] if len(ch) == 44 else ''
    # ICMS desonerado: pares (valor, motivo) por item — vICMSDeson sempre vem
    # seguido de motDesICMS dentro do mesmo grupo <ICMSxx>, então casar nessa
    # ordem dá o valor exato de cada motivo (sem aproximação/rateio).
    pares_deson = re.findall(r'<vICMSDeson>([\d.]+)</vICMSDeson>\s*<motDesICMS>(\d+)</motDesICMS>', t)
    vdeson_total = sum(float(v) for v, _ in pares_deson)
    motivos = sorted(set(m for _, m in pares_deson))
    return {
        'arquivo': _nome_exibicao(path),
        'chave': ch,
        'data': data_doc,
        'vnf': float(vnf.group(1)) if vnf else 0.0,
        'vdeson': round(vdeson_total, 2),
        'motivos_deson': motivos,
        'deson_pares': [(round(float(v), 2), m) for v, m in pares_deson],
        'nnf': nnf.group(1) if nnf else '',
        'serie': ser.group(1) if ser else '',
        'fornecedor': (emit.group(1).strip() if emit else ''),
        'cnpj': re.sub(r'\D', '', cnpj.group(1)) if cnpj else '',
        'destinatario': (dest_nome.group(1).strip() if dest_nome else ''),
        'dest_cnpj': re.sub(r'\D', '', dest_cnpj.group(1)) if dest_cnpj else '',
        'tp': tp.group(1) if tp else '',
        'modelo': modelo,
        'is_nota': is_nota,
    }

def parse_cte(path):
    """Lê um XML de CT-e (Conhecimento de Transporte Eletrônico): dados da
    transportadora, valor do frete, CST/ICMS do próprio CT-e, e a(s) chave(s)
    de NF-e referenciada(s) no rodapé (infNFe/chave)."""
    t = _read_text(path)
    chave = re.search(r'Id="CTe(\d{44})"', t)
    ch = chave.group(1) if chave else ''
    is_cte = bool(re.search(r'<infCte\b', t) and ch)
    nct = re.search(r'<nCT>(\d+)</nCT>', t)
    ser = re.search(r'<serie>(\d+)</serie>', t)
    dh_emi = re.search(r'<dhEmi>(\d{4}-\d{2}-\d{2})T', t)
    data_doc = ''
    if dh_emi:
        y, m, d = dh_emi.group(1).split('-')
        data_doc = f'{d}/{m}/{y}'
    emit = re.search(r'<emit>.*?<xNome>(.*?)</xNome>', t, re.S)
    cnpj = re.search(r'<emit>.*?<CNPJ>(\d+)</CNPJ>', t, re.S)
    vprest = re.search(r'<vTPrest>([\d.]+)</vTPrest>', t)
    cst = re.search(r'<CST>(\d+)</CST>', t)
    vicms = re.search(r'<vICMS>([\d.]+)</vICMS>', t)
    # chaves de NF-e referenciadas (pode ter mais de uma no mesmo CT-e)
    nfes_ref = re.findall(r'<infNFe>\s*<chave>(\d{44})</chave>', t)
    return {
        'arquivo': _nome_exibicao(path),
        'chave': ch,
        'is_cte': is_cte,
        'data': data_doc,
        'nct': nct.group(1) if nct else '',
        'serie': ser.group(1) if ser else '',
        'transportadora': (emit.group(1).strip() if emit else ''),
        'cnpj': re.sub(r'\D', '', cnpj.group(1)) if cnpj else '',
        'vprest': float(vprest.group(1)) if vprest else 0.0,
        'cst': cst.group(1) if cst else '',
        'vicms': float(vicms.group(1)) if vicms else 0.0,
        'nfes_ref': nfes_ref,
    }

def _traduz_cfop_saida_para_entrada(cfop_saida):
    """O CFOP do XML vem do lado do EMITENTE (saída dele) — pra registrar
    como ENTRADA no seu SPED, troca só o 1º dígito, mantendo os últimos 3
    (é a convenção oficial: 5.102 venda dentro do estado <-> 1.102 compra
    dentro do estado; 6xxx<->2xxx outro estado; 7xxx<->3xxx exterior).
    Confirmado nos 3 XMLs reais analisados (todos CFOP 5xxx, dentro do
    estado)."""
    if not cfop_saida or len(cfop_saida) != 4:
        return None
    mapa_primeiro_digito = {'5': '1', '6': '2', '7': '3'}
    novo_primeiro = mapa_primeiro_digito.get(cfop_saida[0])
    return (novo_primeiro + cfop_saida[1:]) if novo_primeiro else None


def parse_xml_itens(path):
    """Extrai os dados DE CADA ITEM da NF-e — usado pra gerar as linhas C170
    quando uma nota está faltando no SPED (o `parse_xml()` de cima só lê o
    total da nota, suficiente pra comparação simples, mas não pra montar o
    C170). CFOP já vem TRADUZIDO de saída (do emitente) pra entrada (seu
    lado) — ver `_traduz_cfop_saida_para_entrada`. CST do ICMS vem do nome
    do grupo (ex.: <ICMS60> → CST 60), não de um campo <CST> isolado, que
    também existe mas repete o mesmo valor com padding diferente conforme
    o grupo (origem+CST juntos em alguns casos) — usar o grupo é mais
    confiável, confirmado nos 3 XMLs reais."""
    t = _read_text(path)
    itens = []
    for bloco in re.findall(r'<det nItem="\d+">(.*?)</det>', t, re.S):
        cprod = re.search(r'<cProd>(.*?)</cProd>', bloco)
        xprod = re.search(r'<xProd>(.*?)</xProd>', bloco)
        ncm = re.search(r'<NCM>(\d+)</NCM>', bloco)
        cfop_xml = re.search(r'<CFOP>(\d+)</CFOP>', bloco)
        vprod = re.search(r'<vProd>([\d.]+)</vProd>', bloco)
        qcom = re.search(r'<qCom>([\d.]+)</qCom>', bloco)
        ucom = re.search(r'<uCom>(.*?)</uCom>', bloco)
        # CST_ICMS no SPED é ORIGEM+CST juntos (3 dígitos, ex.: "000") — achado
        # real comparando com C170 já existente num SPED seu — não é só o
        # CST sozinho.
        grupo_icms = re.search(r'<ICMS>\s*<ICMS(\d{2,3}|SN\d{3})>(.*?)</ICMS\1>', bloco, re.S)
        orig = re.search(r'<orig>(\d)</orig>', grupo_icms.group(2)) if grupo_icms else None
        cst_num = re.search(r'<CST>(\d{2,3})</CST>', grupo_icms.group(2)) if grupo_icms else None
        vbc_icms = re.search(r'<vBC>([\d.]+)</vBC>', grupo_icms.group(2)) if grupo_icms else None
        aliq_icms = re.search(r'<pICMS>([\d.]+)</pICMS>', grupo_icms.group(2)) if grupo_icms else None
        vicms = re.search(r'<vICMS>([\d.]+)</vICMS>', bloco)
        cfop_saida = cfop_xml.group(1) if cfop_xml else None
        cst_icms_completo = None
        if orig and cst_num:
            cst_icms_completo = orig.group(1) + cst_num.group(1).zfill(2)
        itens.append({
            'codigo_produto': cprod.group(1) if cprod else '',
            'descricao': xprod.group(1) if xprod else '',
            'ncm': ncm.group(1) if ncm else '',
            'unidade': ucom.group(1) if ucom else 'UN',
            'cfop_saida_xml': cfop_saida,
            'cfop_entrada': _traduz_cfop_saida_para_entrada(cfop_saida),
            'cst_icms': cst_icms_completo,
            'valor': float(vprod.group(1)) if vprod else 0.0,
            'quantidade': float(qcom.group(1)) if qcom else 0.0,
            'vl_bc_icms': float(vbc_icms.group(1)) if vbc_icms else 0.0,
            'aliq_icms': float(aliq_icms.group(1)) if aliq_icms else 0.0,
            'valor_icms': float(vicms.group(1)) if vicms else 0.0,
        })
    return itens


def _fmt_valor_sped(v, casas=2):
    """Formata número no padrão do SPED: vírgula decimal, sem separador de
    milhar (ex.: 1234.5 -> '1234,50')."""
    return f'{v:.{casas}f}'.replace('.', ',')


def gerar_linha_c170(num_item, item, cod_nat):
    """Monta uma linha C170 completa (38 campos) a partir de um item já
    extraído do XML (`parse_xml_itens`) + a Natureza já resolvida (CFOP
    conhecido ou confirmado manualmente). Layout confirmado campo a campo
    contra um C170 real de um SPED do Rafael — os campos de PIS/COFINS/IPI
    que o XML não define claramente ficam zerados (igual o padrão visto no
    exemplo real pra item sem incidência).
    Achado real comparando com o SPED de agosto exportado do Domínio: essa
    empresa (Simples Nacional) NUNCA preenche VL_BC_ICMS/ALIQ_ICMS/VL_ICMS
    no C170 — os 1.093 C170 reais do mês vieram todos com esses 3 campos
    zerados, mesmo em itens com CST_ICMS "tributado" — o ICMS não é
    destacado item a item nesse regime. Segue a MESMA convenção aqui (fica
    zerado), em vez de usar o valor calculado a partir do XML."""
    z = '0,00'
    campos = [
        'C170', str(num_item), item['codigo_produto'], '',
        _fmt_valor_sped(item['quantidade'], 4), item['unidade'],
        _fmt_valor_sped(item['valor']), z, '0',
        item['cst_icms'] or '', item['cfop_entrada'] or '', cod_nat or '',
        z, z, z, z, z, z, '0',
        '', '', z, z, z,
        '', z, '0,0000', '0,000', '0,0000', z,
        '', z, '0,0000', '0,000', '0,0000', z,
        '', z,
    ]
    return '|' + '|'.join(campos) + '|'


def gerar_linhas_c190(itens):
    """Monta as linhas C190 (Registro Analítico do Documento) — OBRIGATÓRIAS
    logo depois dos C170 de cada nota, uma por combinação (CST_ICMS, CFOP)
    presente nos itens. Achado real (comparando contagem de C190 antes/depois
    da inserção num SPED real): faltava gerar isso — o validador (PVA) acusa
    erro estrutural sem detalhar quando falta, porque o C190 é quem fecha a
    consistência entre os itens do C170 e o total do documento.
    VL_OPR = soma de VL_ITEM dos itens do grupo; os campos de ICMS ficam
    zerados, seguindo a mesma convenção confirmada no C170 (ver
    `gerar_linha_c170`)."""
    grupos = {}
    for it in itens:
        chave = (it['cst_icms'] or '', it['cfop_entrada'] or '')
        grupos.setdefault(chave, 0.0)
        grupos[chave] += it['valor']
    linhas = []
    for (cst, cfop), vl_opr in grupos.items():
        campos = ['C190', cst, cfop, '0,00', _fmt_valor_sped(vl_opr), '0,00', '0,00', '0,00', '0,00', '0,00', '0,00', '']
        linhas.append('|' + '|'.join(campos) + '|')
    return linhas


def gerar_linha_c100(nota, cod_part):
    """Monta a linha C100 (cabeçalho da nota) a partir dos dados já lidos
    por `parse_xml()` (nota) + o código do participante (achado no cadastro
    0150 pelo CNPJ, ou None se o fornecedor ainda não está cadastrado —
    nesse caso a nota fica pendente, não dá pra gerar C100 sem COD_PART).
    Layout confirmado contra um C100 real de SPED do Rafael."""
    if not cod_part:
        return None
    z = '0,00'
    data_sped = (nota.get('data') or '').replace('/', '')
    campos = [
        'C100', '0', '0', cod_part, '55', '00', nota.get('serie') or '1',
        nota.get('nnf') or '', nota.get('chave') or '',
        data_sped, data_sped,
        _fmt_valor_sped(nota.get('vnf') or 0), '0', z, z,
        _fmt_valor_sped(nota.get('vnf') or 0), '0', z, z, z,
        z, z, z, z, z, z, z, z, z,
    ]
    return '|' + '|'.join(campos) + '|'


def busca_cod_part_por_cnpj(texto_sped, cnpj):
    """Procura o código do participante (COD_PART) no cadastro 0150 do SPED
    pelo CNPJ do fornecedor. Devolve None se o fornecedor ainda não está
    cadastrado — nesse caso a nota fica pendente (sem COD_PART não dá pra
    montar C100 válido, precisaria criar um 0150 novo primeiro, o que fica
    de fora dessa 1ª versão)."""
    cnpj_limpo = re.sub(r'\D', '', cnpj or '')
    if not cnpj_limpo:
        return None
    for ln in texto_sped.splitlines():
        if ln.startswith('|0150|'):
            f = ln.split('|')
            if len(f) > 6:
                cnpj_linha = re.sub(r'\D', '', f[5] or f[6] or '')
                if cnpj_linha == cnpj_limpo:
                    return f[2]
    return None


def adicionar_notas_ao_sped(texto_sped, notas_para_incluir):
    """Insere no SPED as notas faltantes já confirmadas — recebe uma lista
    de {'nota': dict de parse_xml(), 'itens': lista de dict já com 'cod_nat'
    preenchido (confirmado, seja automático ou manual)}. Devolve
    (texto_corrigido, resumo). Reaproveita `_recalcula_bloco9_global` e
    `_recalcula_fechamentos_bloco` (mesma lógica já validada na Correção do
    SPED — qualquer inserção de linha exige recontar tudo).
    Nota SEM cod_part (fornecedor não cadastrado no 0150) é pulada e
    reportada em `resumo['puladas_sem_cadastro']` — não força um 0150 novo
    nessa 1ª versão, fica pra revisão manual."""
    linhas = texto_sped.replace('\r\n', '\n').split('\n')
    idx_c990 = next((i for i, l in enumerate(linhas) if l.startswith('|C990|')), None)
    if idx_c990 is None:
        return texto_sped, {'erro': 'Bloco C (C990) não encontrado no SPED — não deveria acontecer num SPED válido.'}

    resumo = {'notas_incluidas': 0, 'itens_incluidos': 0, 'puladas_sem_cadastro': []}
    novas_linhas = []
    for entrada in notas_para_incluir:
        nota, itens = entrada['nota'], entrada['itens']
        cod_part = busca_cod_part_por_cnpj(texto_sped, nota.get('cnpj', ''))
        if not cod_part:
            resumo['puladas_sem_cadastro'].append(nota.get('chave', nota.get('arquivo', '')))
            continue
        linha_c100 = gerar_linha_c100(nota, cod_part)
        if not linha_c100:
            resumo['puladas_sem_cadastro'].append(nota.get('chave', nota.get('arquivo', '')))
            continue
        novas_linhas.append(linha_c100)
        for i, item in enumerate(itens, start=1):
            novas_linhas.append(gerar_linha_c170(i, item, item.get('cod_nat')))
            resumo['itens_incluidos'] += 1
        novas_linhas.extend(gerar_linhas_c190(itens))
        resumo['notas_incluidas'] += 1

    if not novas_linhas:
        return texto_sped, resumo

    linhas = linhas[:idx_c990] + novas_linhas + linhas[idx_c990:]
    linhas = _recalcula_bloco9_global(linhas)
    linhas = _recalcula_fechamentos_bloco(linhas)
    return '\r\n'.join(linhas), resumo


def _expandir_zip(caminho_zip):
    """Lista os XMLs dentro de um .zip como caminhos virtuais
    "caminho_do_zip::nome_interno" — `_read_text` sabe ler isso direto da
    memória, sem nunca extrair pro disco (mais rápido: evita o antivírus do
    Windows escaneando um arquivo por vez)."""
    try:
        with zipfile.ZipFile(caminho_zip) as z:
            return [f'{caminho_zip}::{nome}' for nome in z.namelist()
                    if nome.lower().endswith('.xml') and not nome.endswith('/')]
    except zipfile.BadZipFile:
        return []


def coletar_xmls(caminhos):
    arqs = []
    for c in caminhos:
        if os.path.isdir(c):
            for ext in ('*.xml', '*.XML'):
                arqs += glob.glob(os.path.join(c, '**', ext), recursive=True)
            for ext in ('*.zip', '*.ZIP'):
                for z in glob.glob(os.path.join(c, '**', ext), recursive=True):
                    arqs += _expandir_zip(z)
        elif os.path.isfile(c):
            if c.lower().endswith('.zip'):
                arqs += _expandir_zip(c)
            else:
                arqs.append(c)
    # dedup
    vistos, out = set(), []
    for a in sorted(set(arqs)):
        out.append(a)
    return out

# --------------------------------------------------------------------------- #
# Conferência NF-e Entradas × SPED
# --------------------------------------------------------------------------- #
def conferencia(sped, xml_paths, tol=0.02):
    idx = sped.get('entradas_index', {})
    empresa_cnpj = re.sub(r'\D', '', (sped.get('empresa', {}).get('cnpj') or ''))
    faltantes, divergencias, conciliadas = [], [], []
    total_xml = 0.0
    total_sped = 0.0
    ignorados_evento = 0      # xml que não é nota (evento/cancelamento/inutilização)
    saidas = []               # notas de saída encontradas na pasta (não entram aqui)
    outra_empresa = []        # notas de entrada cujo DESTINATÁRIO não é a empresa do SPED
    chaves_com_xml = set()    # toda chave de entrada válida encontrada na pasta de XMLs
    for p in xml_paths:
        x = parse_xml(p)
        if not x['is_nota']:
            ignorados_evento += 1
            continue
        # entrada = modelo 55 emitido por terceiro; saída = NFC-e (65) ou emitido pela própria empresa
        eh_saida = (x['modelo'] == '65') or (empresa_cnpj and x['cnpj'] == empresa_cnpj)
        if eh_saida:
            saidas.append(x)
            continue
        # nota de entrada: o destinatário TEM que ser a empresa do SPED importado.
        # se vier CNPJ de destinatário diferente, é XML de outra empresa misturado na pasta.
        if empresa_cnpj and x['dest_cnpj'] and x['dest_cnpj'] != empresa_cnpj:
            outra_empresa.append(x)
            continue
        chaves_com_xml.add(x['chave'])
        total_xml += x['vnf']
        sp = idx.get(x['chave'])
        if not sp:
            faltantes.append({**x, 'caminho': p})
        else:
            total_sped += sp['vl']
            dif = round(x['vnf'] - sp['vl'], 2)
            if abs(dif) > tol:
                divergencias.append({**x, 'vl_sped': sp['vl'], 'dif': dif})
            else:
                conciliadas.append({**x, 'vl_sped': sp['vl']})
    importadas = len(conciliadas) + len(divergencias) + len(faltantes)
    # agrupa as notas de outra empresa por CNPJ/nome do destinatário encontrado, p/ o alerta
    outra_empresa_grp = {}
    for x in outra_empresa:
        k = x['dest_cnpj']
        g = outra_empresa_grp.setdefault(k, {'cnpj': k, 'nome': x['destinatario'], 'qtd': 0})
        g['qtd'] += 1
    # ---- direção inversa: nota ESCRITURADA no SPED sem XML correspondente na pasta ----
    sped_sem_xml = []
    for chave, dados in idx.items():
        if chave not in chaves_com_xml:
            sped_sem_xml.append({
                'chave': chave, 'nnf': dados.get('num', ''), 'fornecedor': dados.get('fornecedor', ''),
                'data': dados.get('dt', ''), 'vl': dados.get('vl', 0.0),
            })
    sped_sem_xml.sort(key=lambda r: (r['data'] or '', r['nnf'] or ''))
    return {
        'empresa': sped.get('empresa', {}),
        'importadas': importadas,
        'qtd_conciliadas': len(conciliadas),
        'qtd_faltantes': len(faltantes),
        'qtd_divergencias': len(divergencias),
        'encontradas': len(conciliadas) + len(divergencias),
        'total_xml': round(total_xml, 2),
        'total_sped_correspondente': round(total_sped, 2),
        'faltantes': faltantes,
        'divergencias': divergencias,
        'ignorados_evento': ignorados_evento,
        'qtd_saidas': len(saidas),
        'qtd_outra_empresa': len(outra_empresa),
        'outra_empresa_grupos': sorted(outra_empresa_grp.values(), key=lambda g: -g['qtd']),
        'sped_sem_xml': sped_sem_xml,
        'qtd_sped_sem_xml': len(sped_sem_xml),
        'total_sped_sem_xml': round(sum(r['vl'] for r in sped_sem_xml), 2),
        'pct_conciliado': round((len(conciliadas) / importadas * 100) if importadas else 0.0, 1),
        'compras_cfop': sped.get('compras_cfop', []),
    }

# --------------------------------------------------------------------------- #
# Logo + componentes visuais
# --------------------------------------------------------------------------- #
def _logo_uri():
    cand = os.environ.get('FISCOCONT_LOGO') or ''
    if not cand or not os.path.exists(cand):
        here = os.path.dirname(os.path.abspath(__file__))
        cand = os.path.join(here, '..', 'assets', 'liddera-logo.png')
    try:
        with open(cand, 'rb') as fh:
            return 'data:image/png;base64,' + base64.b64encode(fh.read()).decode('ascii')
    except Exception:
        return ''

def _donut(segs, cx=90, cy=90, r=66, sw=26, is_money=True):
    C = 2 * math.pi * r
    total = sum(v for _, v, _ in segs) or 1
    arcs = ''
    cum = 0.0
    for i, (label, val, color) in enumerate(segs):
        frac = (val / total) if total else 0
        seglen = max(frac * C, 0.6)
        gap = C - seglen
        rot = -90 + cum * 360
        pct = frac * 100
        val_fmt = f'R$ {_brl(val)}' if is_money else f'{int(val)}'
        arcs += (f'<circle class="donut-seg" cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{sw}" '
                 f'stroke-dasharray="{seglen:.2f} {gap:.2f}" transform="rotate({rot:.2f} {cx} {cy})" '
                 f'data-label="{_esc(label)}" data-value="{_esc(val_fmt)}" data-pct="{pct:.1f}%" '
                 f'style="--sl:{seglen:.2f};stroke-dashoffset:0;animation:draw .9s {0.12*i:.2f}s ease backwards"/>')
        cum += frac
    return arcs

_CSS = """
:root{--navy:#1f2a5a;--navy2:#2b3a72;--orange:#e8632b;--ink:#243056;--ink2:#6b7392;--line:#e7ebf3;--bg:#eef1f7;--pos:#0ea472;--neg:#e23d4c;--warn:#d4711a;--card:#fff}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:var(--ink);padding:26px}
.wrap{max-width:1120px;margin:0 auto}
@keyframes up{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes grow{from{width:0}to{width:var(--w)}}
@keyframes draw{from{stroke-dashoffset:var(--sl)}to{stroke-dashoffset:0}}
@keyframes sweep{from{stroke-dashoffset:339}}
.sec{opacity:0;animation:up .6s ease forwards}
header{display:flex;align-items:center;gap:14px;margin-bottom:16px}
header img{width:52px;height:52px;border-radius:12px;background:#fff;padding:5px;box-shadow:0 3px 10px rgba(31,42,90,.12)}
.h-txt b{font-size:19px;color:var(--navy);font-weight:800;letter-spacing:.2px}
.h-txt div{font-size:12.5px;color:var(--ink2)}
.h-right{margin-left:auto;text-align:right;font-size:12px;color:var(--ink2)}
.h-right b{color:var(--navy)}
.tagint{margin-left:auto;background:#eef1f7;color:var(--navy);border:1px solid var(--line);border-radius:999px;padding:6px 13px;font-size:12px;font-weight:700}
.band{background:linear-gradient(120deg,var(--navy),var(--navy2));border-radius:18px;padding:20px 24px;color:#fff;box-shadow:0 10px 28px rgba(31,42,90,.28);position:relative;overflow:hidden;display:flex;align-items:center;gap:16px}
.band::after{content:"";position:absolute;right:-40px;top:-40px;width:180px;height:180px;border-radius:50%;background:rgba(232,99,43,.22)}
.band h1{font-size:20px;font-weight:800;position:relative}
.band .meta{font-size:12.5px;opacity:.86;margin-top:4px;position:relative}
.band .imp{margin-left:auto;display:flex;gap:8px;position:relative}
.ibtn{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.22);color:#fff;border-radius:10px;padding:9px 13px;font-size:12.5px;font-weight:600}
.ibtn.on{background:var(--orange);border-color:var(--orange)}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:16px 0}
.kpi{background:var(--card);border-radius:14px;padding:15px 16px;box-shadow:0 4px 14px rgba(31,42,90,.06);border:1px solid var(--line)}
.kpi .l{font-size:10.5px;letter-spacing:.5px;text-transform:uppercase;color:var(--ink2);font-weight:700}
.kpi .v{font-size:20px;font-weight:800;margin-top:6px}
.kpi.big .v{color:var(--orange)}
.cstats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:14px}
.cstat{background:var(--card);border-radius:14px;padding:16px;text-align:center;border:1px solid var(--line);box-shadow:0 4px 14px rgba(31,42,90,.05)}
.cstat .v{font-size:30px;font-weight:800}.cstat .l{font-size:11.5px;color:var(--ink2);margin-top:2px}
.cstat.ok .v{color:var(--pos)}.cstat.f .v{color:var(--neg)}.cstat.d .v{color:var(--warn)}.cstat.t .v{color:var(--navy)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}
.card{background:var(--card);border-radius:16px;padding:18px 20px;box-shadow:0 4px 14px rgba(31,42,90,.06);border:1px solid var(--line)}
.card h3{font-size:14px;color:var(--navy);margin-bottom:14px;display:flex;align-items:center;gap:8px}
.card h3 .dot{width:8px;height:18px;border-radius:3px;background:var(--orange)}
.row{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px dashed var(--line);font-size:13.5px}
.row:last-child{border-bottom:0}.row .k{color:var(--ink2)}.row .val{font-weight:700}
.row.tot{margin-top:6px;background:var(--navy);color:#fff;border-radius:11px;padding:12px 14px;border:0}
.row.tot .k{color:#cdd6f5}.row.tot .val{color:#fff;font-size:16px}
.va{margin-top:6px;background:linear-gradient(120deg,var(--orange),#f08a3d);color:#fff;border-radius:11px;padding:12px 14px;display:flex;justify-content:space-between;font-weight:800}
.bar-item{margin-bottom:11px;opacity:0;animation:up .5s ease forwards}
.bar-head{display:flex;align-items:center;gap:8px;font-size:12px;margin-bottom:5px}
.cfop{background:var(--navy);color:#fff;border-radius:6px;padding:2px 7px;font-weight:700;font-size:11px}
.bar-desc{color:var(--ink);flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.bar-nfs{color:var(--ink2)}.bar-val{font-weight:700}
.bar{height:10px;background:#eef1f7;border-radius:6px;overflow:hidden}.bar.sm{height:8px}
.bar>span{display:block;height:100%;border-radius:6px;width:var(--w);animation:grow 1s ease forwards}
.rk{display:flex;gap:10px;align-items:center;margin-bottom:10px;opacity:0;animation:up .5s ease forwards}
.rk-n{width:22px;height:22px;border-radius:6px;background:var(--navy);color:#fff;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex:0 0 auto}
.rk-body{flex:1}.rk-top{display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px}
.rk-name{color:var(--ink);overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.rk-val{font-weight:700}
.donut-row{display:flex;align-items:center;gap:18px}
.donut{position:relative;width:180px;height:180px;flex:0 0 auto}
.donut-seg{cursor:pointer;transition:opacity .15s}
.donut:hover .donut-seg:not(:hover){opacity:.35}
.dtip{position:fixed;pointer-events:none;z-index:9999;background:var(--navy,#1f2a5a);color:#fff;
  font-size:11.5px;font-weight:600;padding:8px 11px;border-radius:9px;box-shadow:0 8px 22px rgba(0,0,0,.28);
  white-space:nowrap;opacity:0;transform:translate(-50%,-115%);transition:opacity .1s;top:0;left:0}
.dtip b{display:block;font-size:12.5px;margin-bottom:2px;font-weight:800}
.dtip.show{opacity:1}
.donut .center{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
.donut .center .big{font-size:24px;font-weight:800;color:var(--navy)}.donut .center .sm{font-size:11px;color:var(--ink2)}
.legend{flex:1;display:flex;flex-direction:column;gap:9px}
.lg{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--ink)}
.lg .dot{width:11px;height:11px;border-radius:3px;flex:0 0 auto}.lg b{margin-left:auto;font-weight:700}.lg .pc{color:var(--ink2);width:44px;text-align:right}
.valrec{display:flex;flex-direction:column;gap:12px}
.vr .top{display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:5px}
.vr-dif{background:rgba(212,113,26,.1);border:1px solid rgba(212,113,26,.25);border-radius:11px;padding:11px 14px;display:flex;justify-content:space-between;font-weight:700;color:var(--warn)}
.vr-ok{background:rgba(14,164,114,.1);border:1px solid rgba(14,164,114,.28);border-radius:11px;padding:11px 14px;display:flex;justify-content:space-between;font-weight:700;color:var(--pos)}
.conf{background:var(--card);border-radius:18px;padding:20px;border:1px solid var(--line);box-shadow:0 6px 18px rgba(31,42,90,.08);border-top:4px solid var(--orange)}
table.pend{width:100%;border-collapse:collapse;font-size:12.5px}
table.pend th{text-align:left;color:var(--ink2);font-size:10.5px;text-transform:uppercase;letter-spacing:.4px;padding:8px 10px;border-bottom:1px solid var(--line)}
table.pend td{padding:9px 10px;border-bottom:1px solid var(--line)}
table.pend td.chave{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:10px;letter-spacing:-.2px;color:#475069;word-break:break-all;max-width:200px}
.descarte{background:#f7f8fc;border:1px solid var(--line);border-radius:10px;padding:9px 14px;font-size:11.5px;color:var(--ink2);margin-bottom:14px}
.alerta-oe{background:#fff1f2;border:1.5px solid #f4a5ac;border-radius:14px;padding:16px 20px;margin-bottom:16px}
.alerta-oe-t{font-size:14px;font-weight:800;color:#c81e35;margin-bottom:6px}
.alerta-oe-s{font-size:12.5px;color:#8a3a42;line-height:1.5;margin-bottom:10px}
.alerta-oe-l{margin:0;padding-left:20px;font-size:12.5px;color:#7a2e35;line-height:1.7}
.tag{padding:3px 9px;border-radius:999px;font-size:10.5px;font-weight:700;white-space:nowrap}
.tag.f{background:rgba(226,61,76,.14);color:var(--neg)}.tag.d{background:rgba(212,113,26,.16);color:var(--warn)}
.tag.custo{background:rgba(14,164,114,.14);color:var(--pos)}.tag.desp{background:rgba(212,113,26,.16);color:var(--warn)}
.tag.imob{background:rgba(58,123,213,.14);color:#3a7bd5}.tag.na{background:#eef1f7;color:var(--ink2)}
.emptyok{padding:22px;text-align:center;color:var(--pos);font-weight:600}
footer{text-align:center;color:var(--ink2);font-size:11px;margin-top:18px}
.dz-grid{display:grid;grid-template-columns:1.15fr .85fr;gap:14px;margin-bottom:16px}
.dz-donut-card{padding:20px}
.dz-highlight-card{background:linear-gradient(150deg,var(--navy),#2b3a72);color:#fff;border-radius:16px;padding:22px 24px;
  box-shadow:0 12px 30px rgba(31,42,90,.22);display:flex;flex-direction:column;justify-content:center}
.dz-hl-t{font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:#c7cbe8;font-weight:800;margin-bottom:14px}
.dz-hl-row{display:flex;justify-content:space-between;gap:14px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.14);font-size:13.5px}
.dz-hl-row:last-of-type{border-bottom:0}
.dz-hl-row b{font-size:15px}
.dz-hl-note{margin-top:14px;font-size:11.5px;color:#c7cbe8;line-height:1.5}
.dz-empty{text-align:center;padding:54px 24px;background:#fff;border:1px solid var(--line);border-radius:16px;box-shadow:0 4px 14px rgba(31,42,90,.05)}
.dz-empty-ic{width:56px;height:56px;margin:0 auto 16px;border-radius:50%;background:#f3f5fb;display:flex;align-items:center;justify-content:center;color:var(--ink2)}
.dz-empty-ic svg{width:28px;height:28px}
.dz-empty h3{font-size:17px;color:var(--navy);margin-bottom:8px;font-weight:800}
.dz-empty p{color:var(--ink2);font-size:13.5px;max-width:480px;margin:0 auto;line-height:1.65}
.dz-grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:16px}
@media(max-width:820px){.dz-grid,.dz-grid2{grid-template-columns:1fr}}
"""

_COUNT_JS = """
<script>
function fmtBRL(n){return 'R$ ' + n.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});}
function fmtInt(n){return Math.round(n).toLocaleString('pt-BR');}
document.querySelectorAll('.cnt').forEach(function(el){
  var t=parseFloat(el.dataset.t), isInt=el.dataset.int==='1', dur=1100, t0=performance.now();
  function step(now){var p=Math.min(1,(now-t0)/dur);p=1-Math.pow(1-p,3);var v=t*p;
    el.textContent=isInt?fmtInt(v):fmtBRL(v); if(p<1)requestAnimationFrame(step);}
  requestAnimationFrame(step);
});
(function(){
  var segs = document.querySelectorAll('.donut-seg');
  if(!segs.length) return;
  var tip=document.createElement('div'); tip.className='dtip';
  var tb=document.createElement('b'); var ts=document.createElement('span');
  tip.appendChild(tb); tip.appendChild(ts); document.body.appendChild(tip);
  segs.forEach(function(seg){
    seg.addEventListener('mousemove', function(e){
      tb.textContent = seg.dataset.label;
      ts.textContent = seg.dataset.value + ' · ' + seg.dataset.pct;
      tip.style.left = e.clientX + 'px';
      tip.style.top = (e.clientY - 10) + 'px';
      tip.classList.add('show');
    });
    seg.addEventListener('mouseleave', function(){ tip.classList.remove('show'); });
  });
})();
</script>
"""

def _bars(rows, cor, maxv):
    out = ''
    for i, r in enumerate(rows):
        w = (r['valor'] / maxv * 100) if maxv else 0
        out += (f'<div class="bar-item" style="animation-delay:{0.05*i:.2f}s">'
                f'<div class="bar-head"><span class="cfop">{_esc(r["cfop"])}</span>'
                f'<span class="bar-desc">{_esc(r["desc"])}</span>'
                f'<span class="bar-nfs">{r["nfs"]} NF</span>'
                f'<span class="bar-val">R$ {_brl(r["valor"])}</span></div>'
                f'<div class="bar"><span style="--w:{w:.1f}%;background:{cor}"></span></div></div>')
    return out or '<div style="color:var(--ink2);font-size:12.5px">Sem dados.</div>'

def _rank(rows, cor):
    if not rows:
        return '<div style="color:var(--ink2);font-size:12.5px">Sem dados.</div>'
    mx = max(r['valor'] for r in rows) or 1
    out = ''
    for i, r in enumerate(rows):
        w = r['valor'] / mx * 100
        out += (f'<div class="rk" style="animation-delay:{0.05*i:.2f}s"><div class="rk-n">{i+1}</div>'
                f'<div class="rk-body"><div class="rk-top"><span class="rk-name">{_esc(r["nome"])}</span>'
                f'<span class="rk-val">R$ {_brl(r["valor"])}</span></div>'
                f'<div class="bar sm"><span style="--w:{w:.1f}%;background:{cor}"></span></div></div></div>')
    return out

# --------------------------------------------------------------------------- #
# Dashboard do cliente (SPED)
# --------------------------------------------------------------------------- #
def gerar_dashboard_sped_html(d):
    emp = d['empresa']
    ap = d['apuracao']
    logo = _logo_uri()
    logo_html = f'<img src="{logo}" alt="Liddera">' if logo else ''
    cmax = max((r['valor'] for r in d['compras_cfop']), default=1)
    vmax = max((r['valor'] for r in d['vendas_cfop']), default=1)
    ajustes_html = ''
    for a in d['ajustes_e111']:
        ajustes_html += (f'<div class="row"><span class="k">{_esc(a["codigo"])} · {_esc(a["descricao"])[:70]}</span>'
                         f'<span class="val" style="color:var(--pos)">R$ {_brl(a["valor"])}</span></div>')
    if not ajustes_html:
        ajustes_html = '<div style="color:var(--ink2);font-size:12.5px">Sem ajustes E111.</div>'

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Apuração ICMS · {_esc(emp.get('empresa',''))}</title>
<style>{_CSS}</style></head><body><div class="wrap">
  <header class="sec">{logo_html}
    <div class="h-txt"><b>Liddera | Inteligência em Negócios</b><div>Apuração ICMS · EFD-ICMS/IPI</div></div>
    <div class="h-right"><div>Período: <b>{_esc(emp.get('periodo',''))}</b></div><div>{_esc(emp.get('uf',''))}</div></div>
  </header>
  <div class="band sec" style="animation-delay:.05s"><div>
    <h1>{_esc(emp.get('empresa',''))}</h1>
    <div class="meta">CNPJ {_esc(emp.get('cnpj',''))} · IE {_esc(emp.get('ie',''))} · {_esc(emp.get('uf',''))} · Contribuinte do ICMS</div>
  </div></div>
  <div class="kpis sec" style="animation-delay:.1s">
    <div class="kpi"><div class="l">Faturamento bruto</div><div class="v cnt" data-t="{d['faturamento_bruto']}">R$ {_brl(d['faturamento_bruto'])}</div></div>
    <div class="kpi"><div class="l">ICMS débitos</div><div class="v cnt" data-t="{ap['debitos']}">R$ {_brl(ap['debitos'])}</div></div>
    <div class="kpi"><div class="l">ICMS créditos</div><div class="v" style="color:var(--ink2)">R$ {_brl(ap['creditos'])}</div></div>
    <div class="kpi big"><div class="l">ICMS a recolher</div><div class="v cnt" data-t="{ap['icms_recolher']}">R$ {_brl(ap['icms_recolher'])}</div></div>
    <div class="kpi"><div class="l">Alíquota efetiva</div><div class="v" style="color:var(--navy)">{_brl(d['aliquota_efetiva'])}%</div></div>
  </div>
  <div class="grid2">
    <div class="card sec" style="animation-delay:.15s"><h3><span class="dot"></span>Apuração do ICMS</h3>
      <div class="row"><span class="k">Débitos (ICMS s/ saídas)</span><span class="val">R$ {_brl(ap['debitos'])}</span></div>
      <div class="row"><span class="k">Créditos (ICMS s/ compras)</span><span class="val">R$ {_brl(ap['creditos'])}</span></div>
      <div class="row"><span class="k">Ajuste de créditos (E110/E111)</span><span class="val" style="color:var(--pos)">R$ {_brl(ap['ajuste_creditos'])}</span></div>
      <div class="row tot"><span class="k">ICMS a recolher</span><span class="val">R$ {_brl(ap['icms_recolher'])}</span></div>
    </div>
    <div class="card sec" style="animation-delay:.2s"><h3><span class="dot"></span>VAF Fiscal</h3>
      <div class="row"><span class="k">+ Vendas (CFOP de venda)</span><span class="val" style="color:var(--pos)">R$ {_brl(d['faturamento_bruto'])}</span></div>
      <div class="row"><span class="k">− Devolução de vendas</span><span class="val">R$ {_brl(d['dev_vendas'])}</span></div>
      <div class="row"><span class="k">− Compras p/ comercialização/industrialização</span><span class="val" style="color:var(--neg)">R$ {_brl(d['entradas_brutas'])}</span></div>
      <div class="row"><span class="k">+ Devolução de compras</span><span class="val">R$ {_brl(d['dev_compras'])}</span></div>
      <div class="va"><span>= Valor adicionado</span><span>R$ {_brl(d['valor_adicionado'])}</span></div>
      <div style="font-size:10.5px;color:var(--ink2);margin-top:8px;line-height:1.45">Não entram no VAF: uso e consumo (R$ {_brl(d.get('uso_consumo',0))}) e imobilizado (R$ {_brl(d.get('imobilizado',0))}).</div>
    </div>
  </div>
  <div class="grid2">
    <div class="card sec" style="animation-delay:.25s"><h3><span class="dot"></span>Entradas por CFOP</h3>{_bars(d['compras_cfop'][:8],'var(--navy)',cmax)}</div>
    <div class="card sec" style="animation-delay:.3s"><h3><span class="dot"></span>Saídas por CFOP</h3>{_bars(d['vendas_cfop'][:8],'var(--orange)',vmax)}</div>
  </div>
  <div class="grid2">
    <div class="card sec" style="animation-delay:.35s"><h3><span class="dot"></span>Top fornecedores</h3>{_rank(d['top_fornecedores'],'var(--navy)')}</div>
    <div class="card sec" style="animation-delay:.4s"><h3><span class="dot"></span>Top produtos em compras</h3>{_rank(d['top_produtos'],'var(--orange)')}</div>
  </div>
  <div class="card sec" style="animation-delay:.45s"><h3><span class="dot"></span>Ajustes da apuração (E111)</h3>{ajustes_html}</div>
  <footer>Gerado pelo FiscoCont+ · Liddera | Inteligência em Negócios Ltda · www.lidderacont.com.br</footer>
</div>{_COUNT_JS}</body></html>"""

# --------------------------------------------------------------------------- #
# Dashboard da Conferência (interno)
# --------------------------------------------------------------------------- #
def conferencia_desoneracao(xml_paths):
    """Conferência do ICMS desonerado nas notas de ENTRADA, a partir do que o
    fornecedor informou no XML (campos vICMSDeson/motDesICMS). Funciona só com
    os XMLs — não precisa de SPED. A empresa é descoberta pelo destinatário
    mais frequente entre os XMLs importados (assumindo que a pasta é de
    entradas de uma única empresa); NFC-e (modelo 65) e notas emitidas por
    essa empresa são sempre tratadas como saída, fora do escopo. Não compara
    com o SPED porque o registro C170 exportado pelo Domínio, nos arquivos
    testados, não traz esse campo — então não há com o que comparar ali."""
    notas = []
    ignorados_evento = 0
    for p in xml_paths:
        x = parse_xml(p)
        if not x['is_nota']:
            ignorados_evento += 1
            continue
        notas.append(x)

    # NFC-e (modelo 65) é sempre saída — não entra no cálculo de quem é "a empresa"
    saidas_nfce = [x for x in notas if x['modelo'] == '65']
    candidatos = [x for x in notas if x['modelo'] != '65']

    cnt_dest = {}
    for x in candidatos:
        if x['dest_cnpj']:
            cnt_dest[x['dest_cnpj']] = cnt_dest.get(x['dest_cnpj'], 0) + 1
    empresa_cnpj = max(cnt_dest, key=cnt_dest.get) if cnt_dest else ''
    empresa_nome = next((x['destinatario'] for x in candidatos if x['dest_cnpj'] == empresa_cnpj), '')

    com_deson, sem_deson = [], []
    saidas = len(saidas_nfce)
    outra_empresa = 0
    for x in candidatos:
        if empresa_cnpj and x['cnpj'] == empresa_cnpj:
            saidas += 1  # NF-e emitida pela própria empresa = saída, não entrada
            continue
        if empresa_cnpj and x['dest_cnpj'] and x['dest_cnpj'] != empresa_cnpj:
            outra_empresa += 1
            continue
        if x['vdeson'] > 0:
            com_deson.append(x)
        else:
            sem_deson.append(x)
    com_deson.sort(key=lambda r: -r['vdeson'])
    sem_deson.sort(key=lambda r: -r['vnf'])
    por_motivo = {}
    for x in com_deson:
        for valor, m in (x.get('deson_pares') or []):
            g = por_motivo.setdefault(m, {'motivo': m, 'qtd': 0, 'valor': 0.0})
            g['qtd'] += 1
            g['valor'] += valor
    for g in por_motivo.values():
        g['valor'] = round(g['valor'], 2)

    todas_datas = [x['data'] for x in (com_deson + sem_deson) if x.get('data')]
    periodo = ''
    if todas_datas:
        def _k(s):
            d, m, a = s.split('/')
            return (a, m, d)
        ds = sorted(todas_datas, key=_k)
        periodo = ds[0] if ds[0] == ds[-1] else f'{ds[0]} a {ds[-1]}'

    return {
        'empresa': {'empresa': empresa_nome, 'cnpj': empresa_cnpj, 'periodo': periodo},
        'identificado': len(com_deson) > 0,
        'qtd_com_deson': len(com_deson),
        'qtd_sem_deson': len(sem_deson),
        'qtd_total_entradas': len(com_deson) + len(sem_deson),
        'total_deson': round(sum(x['vdeson'] for x in com_deson), 2),
        'total_notas_valor': round(sum(x['vnf'] for x in com_deson), 2),
        'notas': com_deson,
        'notas_sem_deson': sem_deson,
        'por_motivo': sorted(por_motivo.values(), key=lambda g: -g['valor']),
        'ignorados_evento': ignorados_evento,
        'qtd_saidas': saidas,
        'qtd_outra_empresa': outra_empresa,
    }


def gerar_desoneracao_html(cf):
    md = cf['empresa']
    logo = _logo_uri()
    logo_html = f'<img src="{logo}" alt="Liddera">' if logo else ''

    # ALERTA (forte, no topo): notas de SAÍDA ou de outra empresa importadas por engano.
    # Este módulo é só de ENTRADAS — se aparecer saída aqui, é erro de seleção da pasta.
    alerta_html = ''
    if cf.get('qtd_saidas') or cf.get('qtd_outra_empresa'):
        itens = []
        if cf.get('qtd_saidas'):
            itens.append(f'<li><b>{cf["qtd_saidas"]} arquivo(s) de nota de SAÍDA</b> — este módulo é só de entradas; notas de saída não pertencem aqui.</li>')
        if cf.get('qtd_outra_empresa'):
            itens.append(f'<li><b>{cf["qtd_outra_empresa"]} arquivo(s) de outra empresa</b> — destinatário diferente da empresa do SPED importado.</li>')
        alerta_html = f"""<div class="alerta-oe">
          <div class="alerta-oe-t">⚠ Erro: arquivos fora do escopo desta conferência foram importados</div>
          <div class="alerta-oe-s">A <b>Conferência ICMS Desonerado</b> é exclusiva para XMLs de <b>entrada</b>. Os itens abaixo
          foram identificados na pasta importada e ficaram <b>de fora</b> do cálculo — confira se selecionou a pasta certa:</div>
          <ul class="alerta-oe-l">{''.join(itens)}</ul>
        </div>"""

    if not cf['identificado']:
        corpo = f"""<div class="dz-empty sec" style="animation-delay:.15s">
          <div class="dz-empty-ic">
            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.6"/>
            <path d="M9 9l6 6M15 9l-6 6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
          </div>
          <h3>Nenhum ICMS desonerado identificado</h3>
          <p>Não foi identificado ICMS desonerado nos documentos fiscais de entrada desta conferência
            ({cf['qtd_total_entradas']} nota(s) analisada(s)). Nenhum XML trouxe os campos
            <b>vICMSDeson</b>/<b>motDesICMS</b> preenchidos.</p>
        </div>"""
    else:
        pct_com = round((cf['qtd_com_deson'] / cf['qtd_total_entradas'] * 100) if cf['qtd_total_entradas'] else 0, 1)
        segs_cs = [('Com ICMS desonerado', cf['qtd_com_deson'], '#e8632b'),
                   ('Sem ICMS desonerado', cf['qtd_sem_deson'], '#e2e6f3')]
        arcs_cs = _donut(segs_cs, is_money=False)
        leg_cs = ''.join(
            f'<div class="lg"><span class="dot" style="background:{c}"></span>{_esc(l)}<b>{v}</b>'
            f'<span class="pc">{(v/cf["qtd_total_entradas"]*100 if cf["qtd_total_entradas"] else 0):.1f}%</span></div>'
            for l, v, c in segs_cs)
        rows = ''.join(
            f'<tr><td>{_esc(x["data"])}</td><td>{_esc(x["nnf"])}</td><td>{_esc(x["fornecedor"])[:40]}</td>'
            f'<td class="chave">{_esc(x["chave"])}</td><td>R$ {_brl(x["vnf"])}</td>'
            f'<td style="color:var(--pos);font-weight:700">R$ {_brl(x["vdeson"])}</td></tr>'
            for x in cf['notas'])
        rows_sem = ''.join(
            f'<tr><td>{_esc(x["data"])}</td><td>{_esc(x["nnf"])}</td><td>{_esc(x["fornecedor"])[:40]}</td>'
            f'<td class="chave">{_esc(x["chave"])}</td><td>R$ {_brl(x["vnf"])}</td></tr>'
            for x in cf.get('notas_sem_deson', []))
        corpo = f"""
  <div class="cstats sec" style="animation-delay:.1s">
    <div class="cstat t"><div class="v cnt" data-t="{cf['qtd_total_entradas']}" data-int="1">0</div><div class="l">Entradas analisadas</div></div>
    <div class="cstat ok"><div class="v cnt" data-t="{cf['qtd_com_deson']}" data-int="1">0</div><div class="l">Com ICMS desonerado</div></div>
    <div class="cstat"><div class="v cnt" data-t="{cf['qtd_sem_deson']}" data-int="1">0</div><div class="l">Sem ICMS desonerado</div></div>
    <div class="cstat"><div class="v" style="font-size:20px">R$ {_brl(cf['total_deson'])}</div><div class="l">Total desonerado</div></div>
    <div class="cstat"><div class="v" style="font-size:20px">R$ {_brl(cf['total_notas_valor'])}</div><div class="l">Valor das notas c/ deson.</div></div>
  </div>
  <div class="dz-grid sec" style="animation-delay:.15s">
    <div class="card dz-donut-card"><h3><span class="dot"></span>Notas com × sem ICMS desonerado</h3>
      <div class="donut-row"><div class="donut"><svg width="180" height="180" viewBox="0 0 180 180">
        <circle cx="90" cy="90" r="66" fill="none" stroke="#eef1f7" stroke-width="26"/>{arcs_cs}</svg>
        <div class="center"><div class="big">{_brl(pct_com)}%</div><div class="sm">c/ desoneração</div></div></div>
        <div class="legend">{leg_cs}</div></div></div>
    <div class="card dz-highlight-card">
      <div class="dz-hl-t">Resumo financeiro</div>
      <div class="dz-hl-row"><span>Valor total desonerado</span><b>R$ {_brl(cf['total_deson'])}</b></div>
      <div class="dz-hl-row"><span>Valor das notas com desoneração</span><b>R$ {_brl(cf['total_notas_valor'])}</b></div>
      <div class="dz-hl-row"><span>Notas analisadas nesta conferência</span><b>{cf['qtd_total_entradas']}</b></div>
      <div class="dz-hl-note">Reflete só o que os fornecedores informaram nos XMLs — sem comparação com o SPED.</div>
    </div>
  </div>
  <div class="card sec docwrap" style="animation-delay:.25s"><h3><span class="dot"></span>Notas com ICMS desonerado</h3>
    <table><thead><tr><th>Data</th><th>NF-e</th><th>Fornecedor</th><th>Chave de acesso (44 dígitos)</th>
      <th class="num">Valor da nota</th><th class="num">ICMS desonerado</th></tr></thead>
      <tbody>{rows}</tbody></table></div>
  <div class="card sec docwrap" style="animation-delay:.3s;margin-top:14px"><h3><span class="dot"></span>Notas sem ICMS desonerado</h3>
    <table><thead><tr><th>Data</th><th>NF-e</th><th>Fornecedor</th><th>Chave de acesso (44 dígitos)</th>
      <th class="num">Valor da nota</th></tr></thead>
      <tbody>{rows_sem}</tbody></table></div>"""

    descarte = []
    if cf.get('ignorados_evento'):
        descarte.append(f'{cf["ignorados_evento"]} arquivo(s) de evento/cancelamento')
    descarte_html = ('<div class="descarte">Ignorados nesta conferência: ' + ' · '.join(descarte) + '.</div>') if descarte else ''

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Conferência ICMS Desonerado · {_esc(md.get('empresa',''))}</title>
<style>{_CSS}</style></head><body><div class="wrap">
  <header class="sec">{logo_html}
    <div class="h-txt"><b>FiscoCont+ · Módulo Fiscal</b><div>Conferência ICMS Desonerado · notas de entrada, a partir dos XMLs</div></div>
    <span class="tagint">uso interno do escritório</span></header>
  {alerta_html}
  <div class="band sec" style="animation-delay:.05s"><div>
    <h1>{_esc(md.get('empresa',''))}</h1>
    <div class="meta">CNPJ {_esc(md.get('cnpj',''))} · {_esc(md.get('periodo',''))}</div>
  </div></div>
  {descarte_html}
  {corpo}
  <div class="nota" style="margin-top:16px">Esta conferência reflete o que os fornecedores informaram nos XMLs
    (campos vICMSDeson/motDesICMS). Não compara com o SPED porque o registro C170 exportado atualmente pelo
    Domínio não traz esse campo — não há, hoje, com o que comparar ali.</div>
  <footer style="text-align:center;color:var(--ink2);font-size:11px;margin-top:16px">Gerado pelo FiscoCont+ · Liddera | Inteligência em Negócios Ltda</footer>
</div>{_COUNT_JS}</body></html>"""


_CLASSE_FRETE_LABEL = {
    'compra': 'Custo (revenda/industr.)',
    'uso_consumo': 'Despesa (uso/consumo)',
    'imobilizado': 'Imobilizado',
}
_CLASSE_FRETE_TAG = {'compra': 'custo', 'uso_consumo': 'desp', 'imobilizado': 'imob'}

# CFOPs de compra já sujeitos à Substituição Tributária (dentro do conjunto
# de "compra" já usado no VAF) — o ICMS já foi cobrado antes, então o
# frete vinculado também não gera crédito.
_CFOP_COMPRA_ST = {'1401', '1403', '2401', '2403'}
# CST do ICMS (2 dígitos, já sem o dígito de origem) que indicam operação
# SEM débito de ICMS — isenta, não tributada ou em suspensão.
_CST_NAO_TRIBUTADA = {'40', '41', '50'}
# CST ambíguos p/ decidir sozinho (diferimento, "outras") — pede conferência.
_CST_CONFERIR = {'51', '90'}

def _credito_frete(cfop, csts, misto_cfop):
    """Decide se o ICMS do frete (CT-e) pode ser aproveitado, a partir do
    CFOP e do(s) CST(s) predominante(s) da NF-e referenciada no SPED.
    Regra: o crédito do frete segue a mesma sorte da mercadoria — só é
    creditável se a compra é p/ revenda/industrialização (sem ST) E a
    operação é tributada de fato."""
    if not cfop:
        return 'confira', 'NF-e não encontrada no SPED'
    classe = _classe_cfop(cfop)
    if classe == 'uso_consumo':
        return 'nao', 'Despesa (uso/consumo) — crédito vedado'
    if classe == 'imobilizado':
        return 'ciap', 'Imobilizado — regra do CIAP (crédito em 48 parcelas), não é simples sim/não'
    if classe != 'compra':
        return 'confira', 'CFOP fora da classificação de compra — confira manualmente'
    if misto_cfop:
        return 'confira', 'Nota com CFOPs mistos — confira manualmente'
    if cfop in _CFOP_COMPRA_ST:
        return 'nao', 'Compra com Substituição Tributária — crédito vedado'
    cst_predom = max(csts.items(), key=lambda kv: kv[1])[0] if csts else ''
    misto_cst = len(csts) > 1
    if misto_cst:
        return 'confira', 'Nota com CSTs mistos — confira manualmente'
    if cst_predom in _CST_NAO_TRIBUTADA:
        return 'nao', f'CST {cst_predom} — operação não tributada, sem débito de ICMS'
    if cst_predom in _CST_CONFERIR:
        return 'confira', f'CST {cst_predom} — confira manualmente'
    if not cst_predom:
        return 'confira', 'CST não encontrado — confira manualmente'
    return 'sim', f'CFOP {cfop} · CST {cst_predom} — tributada normalmente'

_CREDITO_TAG = {'sim': 'custo', 'nao': 'desp', 'ciap': 'imob', 'confira': 'na'}
_CREDITO_TXT = {'sim': 'Sim', 'nao': 'Não', 'ciap': 'CIAP (48x)', 'confira': 'Confira'}

def conferencia_frete(sped, xml_paths):
    """Classificação de Frete: cruza cada CT-e com a(s) NF-e(s) que ele
    referencia no rodapé, usando o CFOP e o CST já escriturados no SPED
    daquela nota, pra sugerir se o frete é Custo (revenda/industrialização),
    Despesa (uso/consumo) ou Imobilizado — e se o ICMS do próprio frete pode
    ser aproveitado como crédito — em vez de abrir CT-e por CT-e no Domínio
    pra descobrir manualmente."""
    cfop_idx = sped.get('cfop_por_chave', {})
    cst_idx = sped.get('cst_por_chave', {})
    entradas_idx = sped.get('entradas_index', {})
    linhas = []
    nao_cte = 0
    for p in xml_paths:
        c = parse_cte(p)
        if not c['is_cte']:
            nao_cte += 1
            continue
        nfes = []
        for chv in c['nfes_ref']:
            cfops = cfop_idx.get(chv, {})
            csts = cst_idx.get(chv, {})
            ent = entradas_idx.get(chv, {})
            predominante = max(cfops.items(), key=lambda kv: kv[1])[0] if cfops else ''
            misto = len(cfops) > 1
            classe = _classe_cfop(predominante) if predominante else ''
            label = _CLASSE_FRETE_LABEL.get(classe, 'Não identificado — confira manualmente')
            credito, credito_motivo = _credito_frete(predominante, csts, misto)
            nfes.append({
                'chave': chv, 'fornecedor': ent.get('fornecedor', ''),
                'valor': ent.get('vl', 0.0), 'cfop': predominante,
                'misto': misto, 'classe': classe, 'label': label,
                'credito': credito, 'credito_motivo': credito_motivo,
            })
        linhas.append({**c, 'nfes': nfes})

    qtd_custo = sum(1 for l in linhas for n in l['nfes'] if n['classe'] == 'compra')
    qtd_despesa = sum(1 for l in linhas for n in l['nfes'] if n['classe'] == 'uso_consumo')
    qtd_imob = sum(1 for l in linhas for n in l['nfes'] if n['classe'] == 'imobilizado')
    qtd_confuso = sum(1 for l in linhas for n in l['nfes'] if not n['classe'])
    qtd_sem_ref = sum(1 for l in linhas if not l['nfes'])
    qtd_credito_sim = sum(1 for l in linhas for n in l['nfes'] if n['credito'] == 'sim')
    qtd_credito_nao = sum(1 for l in linhas for n in l['nfes'] if n['credito'] == 'nao')

    return {
        'empresa': sped.get('empresa', {}),
        'ctes': linhas,
        'qtd_ctes': len(linhas),
        'valor_total_frete': round(sum(c['vprest'] for c in linhas), 2),
        'qtd_custo': qtd_custo, 'qtd_despesa': qtd_despesa, 'qtd_imobilizado': qtd_imob,
        'qtd_nao_identificado': qtd_confuso, 'qtd_sem_referencia': qtd_sem_ref,
        'qtd_credito_sim': qtd_credito_sim, 'qtd_credito_nao': qtd_credito_nao,
        'nao_cte': nao_cte,
    }


def gerar_frete_html(cf):
    md = cf['empresa']
    logo = _logo_uri()
    logo_html = f'<img src="{logo}" alt="Liddera">' if logo else ''

    alerta_html = ''
    if cf.get('nao_cte'):
        alerta_html = f"""<div class="alerta-oe">
          <div class="alerta-oe-t">⚠ Erro: {cf['nao_cte']} arquivo(s) que não são CT-e foram importados</div>
          <div class="alerta-oe-s">A <b>Classificação de Frete</b> é exclusiva para XMLs de <b>CT-e</b>. Esses arquivos
          ficaram <b>de fora</b> do cálculo — confira se selecionou a pasta certa.</div>
        </div>"""

    rows = ''
    for c in cf['ctes']:
        base = (f'<td>{_esc(c["data"])}</td><td>{_esc(c["nct"])}</td><td>{_esc(c["transportadora"])[:34]}</td>'
                f'<td>R$ {_brl(c["vprest"])}</td><td>{_esc(c["cst"]) or "—"}</td>')
        if not c['nfes']:
            rows += f'<tr>{base}<td colspan="5" style="color:var(--ink2)">Nenhuma NF-e referenciada no CT-e</td></tr>'
        for n in c['nfes']:
            tagcls = _CLASSE_FRETE_TAG.get(n['classe'], 'na')
            aviso_misto = ' <span style="color:var(--warn);font-size:10.5px">· CFOPs mistos, confira</span>' if n['misto'] else ''
            credtag = _CREDITO_TAG.get(n['credito'], 'na')
            credtxt = _CREDITO_TXT.get(n['credito'], '—')
            rows += (f'<tr>{base}<td>{_esc(n["fornecedor"])[:30] or "—"}</td>'
                      f'<td>{_esc(n["cfop"]) or "—"}{aviso_misto}</td>'
                      f'<td>R$ {_brl(n["valor"])}</td>'
                      f'<td><span class="tag {tagcls}">{_esc(n["label"])}</span></td>'
                      f'<td><span class="tag {credtag}" title="{_esc(n["credito_motivo"])}">{_esc(credtxt)}</span></td></tr>')

    if not cf['ctes']:
        corpo = '<div class="emptyok">Nenhum CT-e válido encontrado na pasta importada.</div>'
    else:
        # rosca 1: Custo x Despesa x Imobilizado x Nao identificado (por qtd de NF-e cruzadas)
        segs_cls = [('Custo (revenda/industr.)', cf['qtd_custo'], '#0ea472'),
                    ('Despesa (uso/consumo)', cf['qtd_despesa'], '#d4711a'),
                    ('Imobilizado', cf['qtd_imobilizado'], '#3a7bd5'),
                    ('Não identificado', cf['qtd_nao_identificado'], '#c7cbe8')]
        segs_cls = [s for s in segs_cls if s[1] > 0]
        arcs_cls = _donut(segs_cls, is_money=False) if segs_cls else ''
        leg_cls = ''.join(
            f'<div class="lg"><span class="dot" style="background:{c}"></span>{_esc(l)}<b>{v}</b></div>'
            for l, v, c in segs_cls)

        # rosca 2: Com credito x Sem credito (por qtd de NF-e cruzadas com CFOP identificado)
        segs_cred = [('Com crédito de ICMS', cf['qtd_credito_sim'], '#0ea472'),
                     ('Sem crédito', cf['qtd_credito_nao'], '#e23d4c')]
        segs_cred = [s for s in segs_cred if s[1] > 0]
        arcs_cred = _donut(segs_cred, is_money=False) if segs_cred else ''
        leg_cred = ''.join(
            f'<div class="lg"><span class="dot" style="background:{c}"></span>{_esc(l)}<b>{v}</b></div>'
            for l, v, c in segs_cred)

        graficos = ''
        if segs_cls or segs_cred:
            graficos = '<div class="dz-grid2 sec" style="animation-delay:.15s">'
            if segs_cls:
                graficos += f"""<div class="card dz-donut-card"><h3><span class="dot"></span>Custo × Despesa × Imobilizado</h3>
                  <div class="donut-row"><div class="donut"><svg width="180" height="180" viewBox="0 0 180 180">
                    <circle cx="90" cy="90" r="66" fill="none" stroke="#eef1f7" stroke-width="26"/>{arcs_cls}</svg></div>
                    <div class="legend">{leg_cls}</div></div></div>"""
            if segs_cred:
                graficos += f"""<div class="card dz-donut-card"><h3><span class="dot"></span>Crédito de ICMS no frete</h3>
                  <div class="donut-row"><div class="donut"><svg width="180" height="180" viewBox="0 0 180 180">
                    <circle cx="90" cy="90" r="66" fill="none" stroke="#eef1f7" stroke-width="26"/>{arcs_cred}</svg></div>
                    <div class="legend">{leg_cred}</div></div></div>"""
            graficos += '</div>'

        corpo = f"""
  <div class="cstats sec" style="animation-delay:.1s">
    <div class="cstat t"><div class="v cnt" data-t="{cf['qtd_ctes']}" data-int="1">0</div><div class="l">CT-e analisados</div></div>
    <div class="cstat"><div class="v" style="font-size:20px">R$ {_brl(cf['valor_total_frete'])}</div><div class="l">Valor total do frete</div></div>
    <div class="cstat ok"><div class="v cnt" data-t="{cf['qtd_custo']}" data-int="1">0</div><div class="l">Custo (revenda/industr.)</div></div>
    <div class="cstat d"><div class="v cnt" data-t="{cf['qtd_despesa']}" data-int="1">0</div><div class="l">Despesa (uso/consumo)</div></div>
    <div class="cstat"><div class="v cnt" data-t="{cf['qtd_imobilizado']}" data-int="1">0</div><div class="l">Imobilizado</div></div>
    <div class="cstat ok"><div class="v cnt" data-t="{cf['qtd_credito_sim']}" data-int="1">0</div><div class="l">Frete c/ crédito de ICMS</div></div>
    <div class="cstat f"><div class="v cnt" data-t="{cf['qtd_credito_nao']}" data-int="1">0</div><div class="l">Frete sem crédito</div></div>
    <div class="cstat f"><div class="v cnt" data-t="{cf['qtd_nao_identificado']}" data-int="1">0</div><div class="l">Não identificado</div></div>
  </div>
  {graficos}
  <div class="card sec docwrap" style="animation-delay:.2s"><h3><span class="dot"></span>CT-e × NF-e referenciada</h3>
    <table><thead><tr><th>Data</th><th>Nº CT-e</th><th>Transportadora</th><th>Valor frete</th><th>CST</th>
      <th>Fornecedor (NF-e)</th><th>CFOP</th><th>Valor NF-e</th><th>Classificação sugerida</th><th>Crédito ICMS no CT-e</th></tr></thead>
      <tbody>{rows}</tbody></table></div>"""

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Classificação de Frete · {_esc(md.get('empresa',''))}</title>
<style>{_CSS}</style></head><body><div class="wrap">
  <header class="sec">{logo_html}
    <div class="h-txt"><b>FiscoCont+ · Módulo Fiscal</b><div>Classificação de Frete (CT-e) · Custo × Despesa × Imobilizado</div></div>
    <span class="tagint">uso interno do escritório</span></header>
  {alerta_html}
  <div class="band sec" style="animation-delay:.05s"><div>
    <h1>{_esc(md.get('empresa',''))}</h1>
    <div class="meta">CNPJ {_esc(md.get('cnpj',''))} · {_esc(md.get('periodo',''))}</div>
  </div></div>
  {corpo}
  <div class="nota" style="margin-top:16px">A classificação Custo/Despesa/Imobilizado é sugerida a partir do CFOP já escriturado
    no SPED para a NF-e referenciada no CT-e — a mesma lógica já usada no cálculo do VAF Fiscal. O <b>Crédito ICMS no CT-e</b>
    segue a mesma sorte da mercadoria: só é "Sim" quando a compra é para revenda/industrialização, SEM Substituição Tributária
    e com CST indicando operação tributada; é "Não" para despesa, ST ou operação isenta/não tributada/suspensa; Imobilizado
    segue a regra própria do CIAP (crédito em 48 parcelas). Não altera nada no Domínio; confirme antes de aplicar,
    principalmente onde aparecer "CFOPs/CSTs mistos", "Confira" ou "Não identificado".</div>
  <footer style="text-align:center;color:var(--ink2);font-size:11px;margin-top:16px">Gerado pelo FiscoCont+ · Liddera | Inteligência em Negócios Ltda</footer>
</div>{_COUNT_JS}</body></html>"""


# --------------------------------------------------------------------------- #
# Auditor de Classificação Fiscal (CFOP × CST, item trocando de classe, combustível × NCM)
# --------------------------------------------------------------------------- #

# As 4 regras confirmadas: (CFOPs, CSTs incoerentes com esses CFOPs, motivo)
_REGRAS_CFOP_CST = [
    ({'1403', '2403'}, {'00'}, 'CFOP indica compra com Substituição Tributária, mas CST 00 (tributada integralmente) não reflete isso'),
    ({'1101', '2101'}, {'60'}, 'CST 60 indica ICMS já retido por ST, mas o CFOP não indica compra com ST'),
    ({'1102', '2102'}, {'60'}, 'CST 60 indica ICMS já retido por ST, mas o CFOP não indica compra com ST'),
]
_CFOP_USO_CONSUMO_ALVO = {'1556', '2556'}
_CST_USO_CONSUMO_ESPERADO = '90'

def _checar_cfop_cst(cfop, cst):
    for cfops, csts_incoerentes, motivo in _REGRAS_CFOP_CST:
        if cfop in cfops and cst in csts_incoerentes:
            return motivo
    if cfop in _CFOP_USO_CONSUMO_ALVO and cst and cst != _CST_USO_CONSUMO_ESPERADO:
        return f'Uso/consumo (CFOP {cfop}) costuma vir com CST 90 — este item veio com CST {cst}, vale conferir'
    return None

def _eh_combustivel_ncm(ncm):
    n = (ncm or '').replace('.', '')
    return n.startswith('2710') or n.startswith('2711')

# Combustível tem CFOPs próprios e específicos — tanto pra quem consome (posto
# usando pra frota própria etc.) quanto pra quem revende (posto de gasolina):
#   1653/2653 = compra de combustível/lubrificante PARA CONSUMO
#   1652/2652 = compra de combustível/lubrificante PARA COMERCIALIZAÇÃO (revenda)
# Não existe CFOP "genérico" correto pra combustível — nem o de uso/consumo
# comum (1556/2556) nem o de revenda comum (1101/1102) servem; combustível
# sempre deveria estar em um desses 4 códigos específicos. Qualquer outro CFOP
# junto de um NCM de combustível é sinalizado.
# (Nas SAÍDAS — não analisadas aqui, só entradas — os específicos são
# 5655/6655 e 5656/6656; guardado de referência pra um módulo futuro.)
_CFOP_COMBUSTIVEL_VALIDOS = {'1652', '1653', '2652', '2653'}
# Esses 4 são tentativas de lançar combustível como consumo final com o CFOP
# errado (genérico de uso/consumo, ou de uso/consumo com ST) — nesse caso a
# mensagem já aponta direto o CFOP certo (1653/2653), sem ambiguidade com revenda.
_CFOP_COMBUSTIVEL_CONSUMO_ERRADO = {'1556', '1407', '2556', '2407'}

def _checar_combustivel(cfop, ncm):
    if not _eh_combustivel_ncm(ncm):
        return None
    if cfop in _CFOP_COMBUSTIVEL_VALIDOS:
        return None
    if cfop in _CFOP_COMBUSTIVEL_CONSUMO_ERRADO:
        return f'NCM {ncm} é combustível para consumo final — o CFOP correto é 1653/2653, não {cfop}'
    return f'NCM {ncm} é de combustível — confira se é consumo (CFOP 1653/2653) ou revenda (1652/2652); veio com {cfop}'

def _analisar_mesmo_item(itens_c170):
    por_item = {}
    for it in itens_c170:
        por_item.setdefault(it['cod_item'], []).append(it)
    inconsistentes = []
    for cod_item, lista in sorted(por_item.items()):
        classes = {_classe_cfop(x['cfop']) for x in lista}
        classes_relevantes = classes & {'compra', 'uso_consumo', 'imobilizado'}
        if len(classes_relevantes) > 1:
            inconsistentes.append({
                'cod_item': cod_item, 'ocorrencias': lista,
                'classes': sorted(classes_relevantes),
                'valor_total': round(sum(x['valor'] for x in lista), 2),
            })
    return inconsistentes

_CFOP_REMESSA_VENDA_EXTERNA = {'5904', '6904'}
_CFOP_RETORNO_REMESSA_VENDA_EXTERNA = {'1904', '2904'}
_CFOP_VENDA_CANDIDATA_REMESSA = {'5104', '6104', '5102', '6102', '5405', '6403'}

def _dt_sort(dt_br):
    """'dd/mm/yyyy' -> 'yyyymmdd', só pra ordenar/comparar datas em string."""
    p = (dt_br or '').split('/')
    return f'{p[2]}{p[1]}{p[0]}' if len(p) == 3 else ''

def _conferencia_remessa_retorno(sped):
    """4ª checagem do Auditor: Remessa para venda fora do estabelecimento
    (CFOP 5904/6904) × Retorno da remessa (1904/2904) × Vendas emitidas no
    intervalo entre as duas (5104/6104/5102/6102/5405/6403). Remessa deveria
    = Retorno + Vendas do intervalo — sobrando diferença, é mercadoria que
    não voltou nem virou venda registrada. Achado real que validou essa regra
    (SPED conferido em set/2026): remessa de R$84.737,64, retorno de só
    R$14.749,17, vendas no intervalo de R$44.850,07 — R$25.138,40 sem
    explicação.

    Casa cada Remessa com o próximo Retorno do MESMO participante (assume que
    não há 2 remessas simultâneas em aberto pro mesmo participante — cenário
    mais comum). Vendas entram na soma pela DATA, dentro da janela
    remessa→retorno — não pelo participante, porque a venda vai pro cliente
    final, não pro participante genérico usado na remessa/retorno.

    LIMITAÇÃO avisada no próprio relatório: a venda decorrente da remessa sai
    pelo MESMO CFOP da venda normal de balcão (não tem CFOP próprio) — então
    "vendas no intervalo" pode incluir venda sem relação com essa remessa
    específica. Isso faz a divergência calculada ser um PISO: a real pode ser
    maior, nunca menor. Remessa sem retorno dentro deste SPED fica marcada
    como 'em_aberto' (pode ser ciclo ainda não fechado, ou retorno cai num
    mês seguinte fora deste arquivo) — não entra como divergência."""
    saidas_idx = sped.get('saidas_index', {})
    entradas_idx = sped.get('entradas_index', {})
    cfop_c190 = sped.get('cfop_c190_por_chave', {})

    remessas, retornos, vendas = [], [], []
    for chave, pares in cfop_c190.items():
        s = saidas_idx.get(chave)
        e = entradas_idx.get(chave)
        val_remessa = sum(v for c, v in pares if c in _CFOP_REMESSA_VENDA_EXTERNA)
        val_retorno = sum(v for c, v in pares if c in _CFOP_RETORNO_REMESSA_VENDA_EXTERNA)
        val_venda = sum(v for c, v in pares if c in _CFOP_VENDA_CANDIDATA_REMESSA)
        if val_remessa and s:
            remessas.append({'chave': chave, 'cod_part': s['cod_part'], 'participante': s['cliente'],
                              'num': s['num'], 'data': s['dt'], 'valor': round(val_remessa, 2)})
        if val_retorno and e:
            retornos.append({'chave': chave, 'cod_part': e['cod_part'], 'participante': e['fornecedor'],
                              'num': e['num'], 'data': e['dt'], 'valor': round(val_retorno, 2)})
        if val_venda and s:
            vendas.append({'chave': chave, 'num': s['num'], 'data': s['dt'], 'cliente': s['cliente'],
                            'valor': round(val_venda, 2)})

    remessas.sort(key=lambda r: _dt_sort(r['data']))
    retornos_por_part = {}
    for r in retornos:
        retornos_por_part.setdefault(r['cod_part'], []).append(r)
    for lst in retornos_por_part.values():
        lst.sort(key=lambda r: _dt_sort(r['data']))

    ciclos = []
    usados = set()
    for rem in remessas:
        candidatos = [r for r in retornos_por_part.get(rem['cod_part'], [])
                      if _dt_sort(r['data']) >= _dt_sort(rem['data']) and r['chave'] not in usados]
        ret = candidatos[0] if candidatos else None
        if ret:
            usados.add(ret['chave'])
            ini, fim = _dt_sort(rem['data']), _dt_sort(ret['data'])
            vendas_periodo = [v for v in vendas if ini <= _dt_sort(v['data']) <= fim]
            total_vendido = round(sum(v['valor'] for v in vendas_periodo), 2)
            esperado = round(rem['valor'] - ret['valor'], 2)
            diferenca = round(esperado - total_vendido, 2)
            ciclos.append({
                'participante': rem['participante'], 'cod_part': rem['cod_part'],
                'remessa': rem, 'retorno': ret,
                'vendas_periodo': vendas_periodo, 'total_vendido': total_vendido,
                'esperado_vendido': esperado, 'diferenca': diferenca,
                'divergente': abs(diferenca) > 0.01, 'em_aberto': False,
            })
        else:
            ciclos.append({
                'participante': rem['participante'], 'cod_part': rem['cod_part'],
                'remessa': rem, 'retorno': None,
                'vendas_periodo': [], 'total_vendido': 0.0,
                'esperado_vendido': None, 'diferenca': None, 'divergente': False,
                'em_aberto': True,
            })
    return ciclos

def conferencia_classificacao(sped):
    """Auditor de Classificação Fiscal: 4 checagens dentro do próprio SPED,
    sem precisar de XML nenhum — (1) CFOP × CST incoerentes; (2) o mesmo
    produto entrando ora como revenda, ora como uso/consumo/imobilizado no
    mesmo período; (3) NCM de combustível cujo CFOP não é uso/consumo;
    (4) Remessa para venda fora do estabelecimento × Retorno × Vendas do
    intervalo."""
    itens = sped.get('itens_c170', [])
    ncm_idx = sped.get('ncm_por_item', {})
    entradas_idx = sped.get('entradas_index', {})
    produtos = sped.get('produtos', {})

    viol_cfop_cst = []
    viol_combustivel = []
    for it in itens:
        ent = entradas_idx.get(it['chave'], {})
        base = {**it, 'fornecedor': ent.get('fornecedor', ''), 'data': ent.get('dt', ''),
                'descricao': produtos.get(it['cod_item'], '')}
        motivo1 = _checar_cfop_cst(it['cfop'], it['cst'])
        if motivo1:
            viol_cfop_cst.append({**base, 'motivo': motivo1})
        ncm = ncm_idx.get(it['cod_item'], '')
        motivo3 = _checar_combustivel(it['cfop'], ncm)
        if motivo3:
            viol_combustivel.append({**base, 'ncm': ncm, 'motivo': motivo3})

    mesmo_item = _analisar_mesmo_item(itens)
    for g in mesmo_item:
        g['descricao'] = produtos.get(g['cod_item'], '')
        for oc in g['ocorrencias']:
            ent = entradas_idx.get(oc['chave'], {})
            oc['num'] = ent.get('num', '')
            oc['fornecedor'] = ent.get('fornecedor', '')
            oc['data'] = ent.get('dt', '')

    remessa_retorno = _conferencia_remessa_retorno(sped)
    viol_remessa_retorno = [c for c in remessa_retorno if c.get('divergente')]

    return {
        'empresa': sped.get('empresa', {}),
        'total_itens': len(itens),
        'viol_cfop_cst': viol_cfop_cst,
        'qtd_cfop_cst': len(viol_cfop_cst),
        'mesmo_item': mesmo_item,
        'qtd_mesmo_item': len(mesmo_item),
        'viol_combustivel': viol_combustivel,
        'qtd_combustivel': len(viol_combustivel),
        'remessa_retorno': remessa_retorno,
        'viol_remessa_retorno': viol_remessa_retorno,
        'qtd_remessa_retorno': len(viol_remessa_retorno),
    }

_CLASSE_TXT = {'compra': 'Revenda/industr.', 'uso_consumo': 'Uso/consumo', 'imobilizado': 'Imobilizado'}
_CLASSE_TAG2 = {'compra': 'custo', 'uso_consumo': 'desp', 'imobilizado': 'imob'}

def gerar_classificacao_html(cf):
    md = cf['empresa']
    logo = _logo_uri()
    logo_html = f'<img src="{logo}" alt="Liddera">' if logo else ''
    total_ocorrencias = cf['qtd_cfop_cst'] + cf['qtd_mesmo_item'] + cf['qtd_combustivel'] + cf['qtd_remessa_retorno']
    score = round((1 - total_ocorrencias / cf['total_itens']) * 100, 1) if cf['total_itens'] else 100.0
    score_color = '#0ea472' if score >= 90 else ('#d4711a' if score >= 75 else '#e23d4c')
    score_color_light = '#3ddb9e' if score >= 90 else ('#f2a552' if score >= 75 else '#f2798a')
    score_bg = 'rgba(14,164,114,.18)' if score >= 90 else ('rgba(212,113,26,.18)' if score >= 75 else 'rgba(226,61,76,.18)')
    score_label = 'Excelente' if score >= 90 else ('Atenção' if score >= 75 else 'Crítico')

    rows_cc = ''.join(
        f'<tr><td>{_esc(x["data"])}</td><td>{_esc(x["fornecedor"])[:28] or "—"}</td>'
        f'<td>{_esc(x["cod_item"])} {("· " + _esc(x["descricao"])[:26]) if x["descricao"] else ""}</td>'
        f'<td>{_esc(x["cfop"])}</td><td>{_esc(x["cst"]) or "—"}</td>'
        f'<td>R$ {_brl(x["valor"])}</td><td style="color:var(--warn);font-size:12px">{_esc(x["motivo"])}</td></tr>'
        for x in cf['viol_cfop_cst'])
    tbl_cc = (f'<table><thead><tr><th>Data</th><th>Fornecedor</th><th>Item</th><th>CFOP</th><th>CST</th>'
              f'<th>Valor</th><th>Incoerência</th></tr></thead><tbody>{rows_cc}</tbody></table>') if rows_cc \
              else '<div class="emptyok">✓ Nenhuma incoerência de CFOP × CST encontrada.</div>'

    rows_mi = ''
    for g in cf['mesmo_item']:
        ocs = ''.join(
            f'<tr><td>{_esc(o.get("data",""))}</td><td>{_esc(o.get("fornecedor",""))[:28] or "—"}</td>'
            f'<td>{_esc(o.get("num","")) or "—"}</td><td>{_esc(o["cfop"])}</td>'
            f'<td><span class="tag {_CLASSE_TAG2.get(_classe_cfop(o["cfop"]),"na")}">{_esc(_CLASSE_TXT.get(_classe_cfop(o["cfop"]),"?"))}</span></td>'
            f'<td>R$ {_brl(o["valor"])}</td></tr>' for o in g['ocorrencias'])
        rows_mi += (f'<tr><td colspan="6" style="background:#f7f8fc;font-weight:700;padding-top:14px">'
                    f'{_esc(g["cod_item"])}{(" · " + _esc(g["descricao"])) if g["descricao"] else ""} '
                    f'<span style="font-weight:400;color:var(--ink2)">— apareceu como {", ".join(_CLASSE_TXT.get(c,c) for c in g["classes"])} '
                    f'no mesmo SPED, total R$ {_brl(g["valor_total"])}</span></td></tr>{ocs}')
    tbl_mi = (f'<table><thead><tr><th>Data</th><th>Fornecedor</th><th>Documento</th><th>CFOP</th><th>Classificação</th><th>Valor</th></tr></thead>'
              f'<tbody>{rows_mi}</tbody></table>') if rows_mi \
              else '<div class="emptyok">✓ Nenhum item mudou de classificação dentro deste SPED.</div>'

    rows_cb = ''.join(
        f'<tr><td>{_esc(x["data"])}</td><td>{_esc(x["fornecedor"])[:28] or "—"}</td>'
        f'<td>{_esc(x["cod_item"])} {("· " + _esc(x["descricao"])[:26]) if x["descricao"] else ""}</td>'
        f'<td>{_esc(x["ncm"])}</td><td>{_esc(x["cfop"])}</td>'
        f'<td>R$ {_brl(x["valor"])}</td></tr>'
        for x in cf['viol_combustivel'])
    tbl_cb = (f'<table><thead><tr><th>Data</th><th>Fornecedor</th><th>Item</th><th>NCM</th><th>CFOP</th>'
              f'<th>Valor</th></tr></thead><tbody>{rows_cb}</tbody></table>') if rows_cb \
              else '<div class="emptyok">✓ Nenhum item de combustível fora do padrão de uso/consumo.</div>'

    def _badge_rr(c):
        if c.get('em_aberto'):
            return '<span class="badge" style="background:rgba(212,113,26,.15);color:#d4711a">em aberto</span>'
        if c['divergente']:
            return '<span class="badge" style="background:rgba(226,61,76,.15);color:#e23d4c">divergente</span>'
        return '<span class="badge" style="background:rgba(14,164,114,.15);color:#0ea472">ok</span>'

    def _linha_rr(c):
        ret = c['retorno']
        sub = 'style="color:var(--ink2);font-size:11px"'
        ret_html = (f'{_esc(ret["data"])}<br><span {sub}>NF {_esc(ret["num"])} · R$ {_brl(ret["valor"])}</span>'
                    if ret else f'<span {sub}>— sem retorno neste SPED</span>')
        esperado_html = f'R$ {_brl(c["esperado_vendido"])}' if c['esperado_vendido'] is not None else '—'
        dif_html = f'R$ {_brl(c["diferenca"])}' if c['diferenca'] is not None else '—'
        dif_style = 'font-weight:700;color:var(--warn)' if c.get('divergente') else 'font-weight:700'
        qtd_notas = len({v['chave'] for v in c['vendas_periodo']})
        return (f'<tr><td>{_esc(c["participante"])[:26]}</td>'
                f'<td>{_esc(c["remessa"]["data"])}<br><span {sub}>NF {_esc(c["remessa"]["num"])} · R$ {_brl(c["remessa"]["valor"])}</span></td>'
                f'<td>{ret_html}</td>'
                f'<td>{qtd_notas} nota(s)<br><span {sub}>R$ {_brl(c["total_vendido"])}</span></td>'
                f'<td>{esperado_html}</td>'
                f'<td style="{dif_style}">{dif_html}</td>'
                f'<td>{_badge_rr(c)}</td></tr>')

    rows_rr = ''.join(_linha_rr(c) for c in cf['remessa_retorno'])
    tbl_rr = (f'<table><thead><tr><th>Participante</th><th>Remessa (5904/6904)</th><th>Retorno (1904/2904)</th>'
              f'<th>Vendas no intervalo</th><th>Deveria ter vendido</th><th>Diferença</th><th>Status</th></tr></thead>'
              f'<tbody>{rows_rr}</tbody></table>') if rows_rr \
              else '<div class="emptyok">✓ Nenhuma Remessa para venda fora do estabelecimento (CFOP 5904/6904) neste SPED.</div>'

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Auditor de Classificação Fiscal · {_esc(md.get('empresa',''))}</title>
<style>{_CSS}
.audit-grid{{display:grid;grid-template-columns:1fr 1.4fr;gap:16px;margin-bottom:16px}}
.gauge-card{{background:linear-gradient(160deg,var(--navy),#2b3a72);border-radius:16px;padding:24px 26px;
  color:#fff;box-shadow:0 12px 30px rgba(31,42,90,.22)}}
.gauge-title{{font-size:12px;font-weight:800;letter-spacing:.6px;text-transform:uppercase;color:#c7cbe8;margin-bottom:14px}}
.gauge-row{{display:flex;align-items:baseline;gap:10px;margin-bottom:16px;flex-wrap:wrap}}
.gauge-score{{font-size:44px;font-weight:800;line-height:1}}
.gauge-score .gauge-pct{{font-size:19px;font-weight:700;color:#c7cbe8}}
.gauge-badge{{font-size:12px;font-weight:800;padding:5px 12px;border-radius:999px}}
.gauge-track{{background:rgba(255,255,255,.12);border-radius:999px;height:24px;overflow:hidden}}
.gauge-fill{{height:100%;border-radius:999px;width:0%;transition:none}}
.gauge-scale{{display:flex;justify-content:space-between;font-size:11px;color:#8b95bd;margin-top:8px}}
.gauge-sub{{font-size:12px;color:#c7cbe8;margin-top:14px;text-align:center}}
.audit-checks{{display:grid;grid-template-rows:repeat(4,1fr);gap:12px}}
.achk{{display:flex;align-items:center;gap:16px;background:#fff;border-radius:14px;padding:14px 20px;
  box-shadow:0 4px 14px rgba(31,42,90,.06);border-left:5px solid var(--c)}}
.achk .num{{font-size:26px;font-weight:800;color:var(--c);min-width:44px;text-align:center}}
.achk .txt b{{display:block;font-size:14px;color:var(--navy)}}
.achk .txt span{{font-size:11.5px;color:var(--ink2)}}
.achk .badge{{margin-left:auto;font-size:10.5px;font-weight:700;padding:5px 10px;border-radius:999px;
  background:color-mix(in srgb, var(--c) 15%, white);color:var(--c);white-space:nowrap}}
@media(max-width:820px){{.audit-grid{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
  <header class="sec">{logo_html}
    <div class="h-txt"><b>FiscoCont+ · Módulo Fiscal</b><div>Auditor de Classificação Fiscal · CFOP × CST, itens, combustível e remessa/retorno</div></div>
    <span class="tagint">uso interno do escritório</span></header>
  <div class="band sec" style="animation-delay:.05s"><div>
    <h1>{_esc(md.get('empresa',''))}</h1>
    <div class="meta">CNPJ {_esc(md.get('cnpj',''))} · {_esc(md.get('periodo',''))}</div>
  </div></div>
  <div class="audit-grid sec" style="animation-delay:.1s">
    <div class="gauge-card">
      <div class="gauge-title">Índice de Conformidade</div>
      <div class="gauge-row">
        <span class="gauge-score"><span class="gauge-num" data-target="{score}">0,0</span><span class="gauge-pct">%</span></span>
        <span class="gauge-badge" style="background:{score_bg};color:{score_color}">{score_label}</span>
      </div>
      <div class="gauge-track"><div class="gauge-fill" id="gaugeFill" style="background:linear-gradient(90deg,{score_color},{score_color_light})"></div></div>
      <div class="gauge-scale"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div>
      <div class="gauge-sub">{cf['total_itens']} itens analisados · {total_ocorrencias} ocorrência(s) no total</div>
    </div>
    <div class="audit-checks">
      <div class="achk" style="--c:{'#0ea472' if cf['qtd_cfop_cst'] == 0 else '#d4711a'}">
        <div class="num cnt" data-t="{cf['qtd_cfop_cst']}" data-int="1">0</div>
        <div class="txt"><b>CFOP × CST incoerentes</b><span>Combinações que não fazem sentido juntas</span></div>
        <div class="badge">{'ok' if cf['qtd_cfop_cst'] == 0 else 'revisar'}</div>
      </div>
      <div class="achk" style="--c:{'#0ea472' if cf['qtd_mesmo_item'] == 0 else '#d4711a'}">
        <div class="num cnt" data-t="{cf['qtd_mesmo_item']}" data-int="1">0</div>
        <div class="txt"><b>Itens com classificação inconsistente</b><span>Mesmo produto, CFOPs diferentes no período</span></div>
        <div class="badge">{'ok' if cf['qtd_mesmo_item'] == 0 else 'revisar'}</div>
      </div>
      <div class="achk" style="--c:{'#0ea472' if cf['qtd_combustivel'] == 0 else '#e23d4c'}">
        <div class="num cnt" data-t="{cf['qtd_combustivel']}" data-int="1">0</div>
        <div class="txt"><b>Combustível fora do padrão</b><span>NCM de combustível com CFOP incorreto</span></div>
        <div class="badge">{'ok' if cf['qtd_combustivel'] == 0 else 'atenção'}</div>
      </div>
      <div class="achk" style="--c:{'#0ea472' if cf['qtd_remessa_retorno'] == 0 else '#e23d4c'}">
        <div class="num cnt" data-t="{cf['qtd_remessa_retorno']}" data-int="1">0</div>
        <div class="txt"><b>Remessa × Retorno × Vendas</b><span>Venda fora do estabelecimento que não fechou a conta</span></div>
        <div class="badge">{'ok' if cf['qtd_remessa_retorno'] == 0 else 'atenção'}</div>
      </div>
    </div>
  </div>
  <div class="card sec docwrap" style="animation-delay:.15s"><h3><span class="dot"></span>CFOP × CST incoerentes</h3>{tbl_cc}</div>
  <div class="card sec docwrap" style="animation-delay:.2s;margin-top:14px"><h3><span class="dot"></span>Mesmo item, classificação diferente no período</h3>{tbl_mi}</div>
  <div class="card sec docwrap" style="animation-delay:.25s;margin-top:14px"><h3><span class="dot"></span>Combustível (NCM 2710/2711) fora dos CFOPs específicos</h3>{tbl_cb}</div>
  <div class="card sec docwrap" style="animation-delay:.3s;margin-top:14px"><h3><span class="dot"></span>Remessa para venda fora do estabelecimento × Retorno × Vendas do intervalo</h3>{tbl_rr}</div>
  <div class="nota" style="margin-top:16px">As 4 checagens usam só o que já está no SPED (sem precisar de XML). A checagem de combustível espera
    o CFOP específico de combustível, seja pra consumo (1653/2653) ou pra revenda (1652/2652, caso de posto de gasolina) —
    qualquer outro CFOP (inclusive revenda genérica) é sinalizado, já que combustível deveria sempre usar um desses 4 códigos.
    "Mesmo item, classificação diferente" pode ser legítimo (o item às vezes é usado de um jeito, às vezes de outro) — sinalizamos
    pra vocês confirmarem, não é necessariamente erro. Na checagem de Remessa × Retorno × Vendas: como a venda decorrente da
    remessa sai pelo mesmo CFOP da venda normal (não tem CFOP próprio), a soma de "vendas no intervalo" pode incluir venda sem
    relação com aquela remessa específica — isso faz a diferença mostrada ser um PISO, a divergência real pode ser maior, nunca
    menor. Remessa sem retorno dentro deste SPED aparece como "em aberto" (ciclo ainda não fechado, ou retorno cai num mês
    seguinte fora deste arquivo) e não conta como divergência. Não altera nada no Domínio.</div>
  <footer style="text-align:center;color:var(--ink2);font-size:11px;margin-top:16px">Gerado pelo FiscoCont+ · Liddera | Inteligência em Negócios Ltda</footer>
</div>{_COUNT_JS}
<script>
(function(){{
  var fill = document.getElementById('gaugeFill');
  var numEl = document.querySelector('.gauge-num');
  if (!fill) return;
  var scoreTarget = parseFloat((numEl && numEl.dataset.target) || '0');
  var t0 = performance.now();
  var upDur = 650, holdDur = 180, downDur = 750;
  function easeOutCubic(t){{ return 1 - Math.pow(1 - t, 3); }}
  function fmt(v){{ return v.toLocaleString('pt-BR', {{minimumFractionDigits:1, maximumFractionDigits:1}}); }}
  function tick(now){{
    var el = now - t0, val;
    if (el < upDur) {{
      val = 100 * easeOutCubic(el / upDur);
    }} else if (el < upDur + holdDur) {{
      val = 100;
    }} else if (el < upDur + holdDur + downDur) {{
      var p = (el - upDur - holdDur) / downDur;
      val = 100 + (scoreTarget - 100) * easeOutCubic(p);
    }} else {{
      val = scoreTarget;
    }}
    fill.style.width = val + '%';
    if (numEl) numEl.textContent = fmt(val);
    if (el < upDur + holdDur + downDur) requestAnimationFrame(tick);
  }}
  requestAnimationFrame(tick);
}})();
</script>
</body></html>"""


def _tabela_pendencias_paginada(faltantes, divergencias, campo_nome_chave, vazio_msg, col_doc, col_nome):
    """Monta a tabela de Faltantes+Divergências PAGINADA via JS (200 por página)
    — achado real: com milhares de linhas (ex.: 11 mil XMLs de saída sem SPED
    correspondente), montar tudo de uma vez como HTML deixava o relatório
    demorando vários segundos só pra abrir. Mesmo padrão já usado e testado no
    visualizador de SPED (que caiu de 8,4s pra 0,17s com essa técnica)."""
    linhas = [
        [ 'Faltante', x.get('data') or '—', x['nnf'], (x[campo_nome_chave] or '')[:40],
          x['chave'], _brl(x['vnf']), '—', 'não escriturada' ]
        for x in faltantes
    ] + [
        [ 'Divergência', x.get('data') or '—', x['nnf'], (x[campo_nome_chave] or '')[:40],
          x['chave'], _brl(x['vnf']), _brl(x['vl_sped']), _brl(x['dif']) ]
        for x in divergencias
    ]
    if not linhas:
        return f'<div class="emptyok">✓ {vazio_msg}</div>'
    dados_json = json.dumps(linhas, ensure_ascii=False)
    return f'''<style>
    .pend-pag-wrap .sppag{{display:flex;align-items:center;gap:10px;justify-content:center;padding:12px;font-size:12.5px;color:var(--ink2)}}
    .pend-pag-wrap .sppag button{{background:#eef1f7;border:none;border-radius:7px;padding:6px 12px;font-size:12px;font-weight:700;color:var(--navy);cursor:pointer}}
    .pend-pag-wrap .sppag button:disabled{{opacity:.35;cursor:default}}
    </style>
    <div class="pend-pag-wrap">
      <table class="pend"><thead><tr><th>Situação</th><th>Data</th><th>{col_doc}</th><th>{col_nome}</th>
      <th>Chave de acesso (44 dígitos)</th><th>Valor XML</th><th>Valor SPED</th><th>Diferença</th></tr></thead>
      <tbody id="pendBody"></tbody></table>
      <div class="sppag"><button id="pendPrev" onclick="pendPagina(-1)">‹ Anterior</button>
      <span id="pendInfo"></span><button id="pendNext" onclick="pendPagina(1)">Próxima ›</button></div>
    </div>
    <script>
    (function(){{
      var DADOS = {dados_json};
      var PAG = 0, POR_PAG = 200;
      function render(){{
        var body = document.getElementById('pendBody');
        body.innerHTML = '';
        var inicio = PAG * POR_PAG;
        var frag = document.createDocumentFragment();
        DADOS.slice(inicio, inicio + POR_PAG).forEach(function(l){{
          var tr = document.createElement('tr');
          var tagCls = l[0] === 'Faltante' ? 'f' : 'd';
          var difStyle = l[0] === 'Faltante' ? 'color:var(--neg);font-weight:700' : 'color:var(--warn);font-weight:700';
          var difTxt = l[0] === 'Faltante' ? l[7] : ('R$ ' + l[7]);
          var valSpedTxt = l[6] === '—' ? '—' : ('R$ ' + l[6]);
          var celulas = [
            {{ html: true, val: '<span class="tag ' + tagCls + '">' + l[0] + '</span>' }},
            {{ val: l[1] }}, {{ val: l[2] }}, {{ val: l[3] }}, {{ cls: 'chave', val: l[4] }},
            {{ val: 'R$ ' + l[5] }}, {{ val: valSpedTxt }}, {{ style: difStyle, val: difTxt }},
          ];
          celulas.forEach(function(c){{
            var td = document.createElement('td');
            if (c.cls) td.className = c.cls;
            if (c.style) td.style.cssText = c.style;
            if (c.html) td.innerHTML = c.val; else td.textContent = c.val;
            tr.appendChild(td);
          }});
          frag.appendChild(tr);
        }});
        body.appendChild(frag);
        var totalPag = Math.max(1, Math.ceil(DADOS.length / POR_PAG));
        document.getElementById('pendInfo').textContent = 'Página ' + (PAG + 1) + ' de ' + totalPag + ' · ' + DADOS.length + ' registro(s)';
        document.getElementById('pendPrev').disabled = PAG === 0;
        document.getElementById('pendNext').disabled = PAG >= totalPag - 1;
      }}
      window.pendPagina = function(delta){{
        var totalPag = Math.max(1, Math.ceil(DADOS.length / POR_PAG));
        PAG = Math.max(0, Math.min(PAG + delta, totalPag - 1));
        render();
      }};
      render();
    }})();
    </script>'''


def gerar_conferencia_html(cf, compras_cfop=None, cliente=False):
    emp = cf['empresa']
    logo = _logo_uri()
    logo_html = f'<img src="{logo}" alt="Liddera">' if logo else ''
    status_segs = [('Conciliadas', cf['qtd_conciliadas'], '#0ea472'),
                   ('Divergências', cf['qtd_divergencias'], '#d4711a'),
                   ('Faltantes', cf['qtd_faltantes'], '#e23d4c')]
    arcs_status = _donut(status_segs, is_money=False)
    tot_s = cf['importadas'] or 1
    leg_status = ''.join(
        f'<div class="lg"><span class="dot" style="background:{c}"></span>{l}<b>{v}</b><span class="pc">{v/tot_s*100:.1f}%</span></div>'
        for l, v, c in status_segs)

    # rosca de entradas por CFOP (colorida)
    palette = ['#1f2a5a', '#e8632b', '#2aa9a0', '#3a7bd5', '#e0a92e', '#9aa3c0', '#7c3aed', '#0ea472']
    cc = (compras_cfop or cf.get('compras_cfop') or [])[:8]
    cfop_segs = [(r['cfop'], r['valor'], palette[i % len(palette)]) for i, r in enumerate(cc)]
    arcs_cfop = _donut(cfop_segs) if cfop_segs else ''
    tot_c = sum(v for _, v, _ in cfop_segs) or 1
    leg_cfop = ''.join(
        f'<div class="lg"><span class="dot" style="background:{c}"></span>{cod} · {_esc(_cfop_desc(cod))}<b>R$ {_brl(v)}</b><span class="pc">{v/tot_c*100:.0f}%</span></div>'
        for cod, v, c in cfop_segs)

    dif = round(cf['total_xml'] - cf['total_sped_correspondente'], 2)
    pend_table = _tabela_pendencias_paginada(
        cf['faltantes'], cf['divergencias'], 'fornecedor',
        'Todas as notas de entrada importadas estão no SPED com valores conferindo.',
        'NF-e', 'Fornecedor')

    # ---- direção inversa: nota ESCRITURADA no SPED sem o XML correspondente ----
    sped_sx_rows = ''.join(
        f'<tr><td>{_esc(r["data"])}</td><td>{_esc(r["nnf"])}</td><td>{_esc(r["fornecedor"])[:40]}</td>'
        f'<td class="chave">{_esc(r["chave"])}</td><td>R$ {_brl(r["vl"])}</td></tr>'
        for r in cf.get('sped_sem_xml', []))
    if not sped_sx_rows:
        sped_sx_table = '<div class="emptyok">✓ Toda nota de entrada escriturada no SPED tem o XML correspondente na pasta importada.</div>'
    else:
        sped_sx_table = ('<table class="pend"><thead><tr><th>Data</th><th>NF-e</th><th>Fornecedor</th>'
                         '<th>Chave de acesso (44 dígitos)</th><th>Valor no SPED</th></tr></thead>'
                         f'<tbody>{sped_sx_rows}</tbody></table>')

    # aviso do que foi descartado (eventos e saídas)
    descarte = []
    if cf.get('ignorados_evento'):
        descarte.append(f'{cf["ignorados_evento"]} arquivo(s) de evento/cancelamento (não são nota)')
    if cf.get('qtd_saidas'):
        descarte.append(f'{cf["qtd_saidas"]} nota(s) de saída (NFC-e/próprias) — não entram na conferência de entradas')
    descarte_html = ('<div class="descarte">Ignorados nesta conferência: ' + ' · '.join(descarte) + '.</div>') if descarte else ''

    # ALERTA: XMLs de entrada cujo destinatário não é a empresa do SPED importado (pasta errada/mesclada)
    alerta_outra_html = ''
    if cf.get('qtd_outra_empresa'):
        grupos = cf.get('outra_empresa_grupos', [])
        itens = ''.join(
            f'<li><b>{_esc(g["nome"] or "(sem nome)")}</b> — CNPJ {_esc(_fmt_cnpj(g["cnpj"]))} · {g["qtd"]} arquivo(s)</li>'
            for g in grupos)
        alerta_outra_html = f"""<div class="alerta-oe">
          <div class="alerta-oe-t">⚠ {cf['qtd_outra_empresa']} arquivo(s) XML pertencem a OUTRA EMPRESA — não foram incluídos na conferência</div>
          <div class="alerta-oe-s">O destinatário dessas notas não é <b>{_esc(emp.get('empresa',''))}</b> (CNPJ {_esc(_fmt_cnpj(re.sub(r'[^0-9]','',emp.get('cnpj','') or '')))}).
          Provavelmente vieram misturados na pasta de XMLs. Confira a origem antes de prosseguir:</div>
          <ul class="alerta-oe-l">{itens}</ul>
        </div>"""

    w_sped = (cf['total_sped_correspondente'] / cf['total_xml'] * 100) if cf['total_xml'] else 0
    dif_box = (f'<div class="vr-ok"><span>Valores conferem</span><span>R$ {_brl(dif)}</span></div>'
               if abs(dif) < 0.02 else
               f'<div class="vr-dif"><span>Diferença a resolver (notas pendentes)</span><span>R$ {_brl(dif)}</span></div>')

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Conferência NF-e × SPED · {_esc(emp.get('empresa',''))}</title>
<style>{_CSS}</style></head><body><div class="wrap">
  <header class="sec">{logo_html}
    <div class="h-txt"><b>{'Liddera | Inteligência em Negócios' if cliente else 'FiscoCont+ · Módulo Fiscal'}</b><div>{'Conferência de Notas Fiscais de Entrada' if cliente else 'Conferência NF-e Entradas × SPED Fiscal'}</div></div>
    {'' if cliente else '<span class="tagint">uso interno do escritório</span>'}</header>
  {alerta_outra_html}
  <div class="band sec" style="animation-delay:.05s"><div>
    <h1>{_esc(emp.get('empresa',''))}</h1>
    <div class="meta">CNPJ {_esc(emp.get('cnpj',''))} · {_esc(emp.get('periodo',''))}</div>
  </div><div class="imp"><span class="ibtn on">✓ SPED importado</span><span class="ibtn">✓ {cf['importadas']} XMLs</span></div></div>
  <div class="cstats sec" style="animation-delay:.1s">
    <div class="cstat t"><div class="v cnt" data-t="{cf['importadas']}" data-int="1">0</div><div class="l">NF-e importadas</div></div>
    <div class="cstat ok"><div class="v cnt" data-t="{cf['qtd_conciliadas']}" data-int="1">0</div><div class="l">Conciliadas (valor bate)</div></div>
    <div class="cstat f"><div class="v cnt" data-t="{cf['qtd_faltantes']}" data-int="1">0</div><div class="l">Faltantes no SPED</div></div>
    <div class="cstat d"><div class="v cnt" data-t="{cf['qtd_divergencias']}" data-int="1">0</div><div class="l">Divergência de valor</div></div>
    {'' if cliente else f'<div class="cstat f"><div class="v cnt" data-t="{cf.get("qtd_sped_sem_xml",0)}" data-int="1">0</div><div class="l">No SPED sem XML</div></div>'}
  </div>
  {descarte_html}
  <div class="grid2">
    <div class="card sec" style="animation-delay:.15s"><h3><span class="dot"></span>Status da conferência</h3>
      <div class="donut-row"><div class="donut"><svg width="180" height="180" viewBox="0 0 180 180">
        <circle cx="90" cy="90" r="66" fill="none" stroke="#eef1f7" stroke-width="26"/>{arcs_status}</svg>
        <div class="center"><div class="big">{_brl(cf['pct_conciliado'])}%</div><div class="sm">conciliado</div></div></div>
        <div class="legend">{leg_status}</div></div>
    </div>
    <div class="card sec" style="animation-delay:.2s"><h3><span class="dot"></span>Entradas por CFOP</h3>
      <div class="donut-row"><div class="donut"><svg width="180" height="180" viewBox="0 0 180 180">
        <circle cx="90" cy="90" r="66" fill="none" stroke="#eef1f7" stroke-width="26"/>{arcs_cfop}</svg>
        <div class="center"><div class="big">{cf['importadas']}</div><div class="sm">importadas</div></div></div>
        <div class="legend">{leg_cfop or '<div style=color:#6b7392;font-size:12.5px>Importe o SPED para ver por CFOP.</div>'}</div></div>
    </div>
  </div>
  <div class="grid2">
    <div class="card sec" style="animation-delay:.25s"><h3><span class="dot"></span>Conciliação de valores</h3>
      <div class="valrec">
        <div class="vr"><div class="top"><span>Total dos XMLs importados</span><b>R$ {_brl(cf['total_xml'])}</b></div><div class="bar"><span style="--w:100%;background:var(--navy)"></span></div></div>
        <div class="vr"><div class="top"><span>Correspondente no SPED</span><b>R$ {_brl(cf['total_sped_correspondente'])}</b></div><div class="bar"><span style="--w:{w_sped:.1f}%;background:var(--pos)"></span></div></div>
        {dif_box}
      </div>
    </div>
    <div class="conf sec" style="animation-delay:.3s"><h3 style="font-size:15px;color:var(--navy);display:flex;align-items:center;gap:8px;margin-bottom:6px"><span class="dot" style="background:var(--orange);width:8px;height:18px;border-radius:3px;display:inline-block"></span>Pendências</h3>{pend_table}</div>
  </div>
  {'' if cliente else f'<div class="conf sec" style="animation-delay:.35s"><h3 style="font-size:15px;color:var(--navy);display:flex;align-items:center;gap:8px;margin-bottom:6px"><span class="dot" style="background:var(--orange);width:8px;height:18px;border-radius:3px;display:inline-block"></span>Escriturado no SPED sem o XML correspondente</h3>{sped_sx_table}</div>'}
  <footer>{'Liddera | Inteligência em Negócios Ltda' if cliente else 'FiscoCont+ · Conferência interna · Liddera | Inteligência em Negócios Ltda'}</footer>
</div>{_COUNT_JS}</body></html>"""

# --------------------------------------------------------------------------- #
# Conferência NF-e/NFC-e de SAÍDA × SPED (espelho da de entradas)
# --------------------------------------------------------------------------- #
def conferencia_saidas(sped, xml_paths, tol=0.02):
    idx = sped.get('saidas_index', {})
    empresa_cnpj = re.sub(r'\D', '', (sped.get('empresa', {}).get('cnpj') or ''))
    faltantes, divergencias, conciliadas = [], [], []
    total_xml = 0.0
    total_sped = 0.0
    ignorados_evento = 0     # xml que não é nota (evento/cancelamento/inutilização)
    nao_pertence = []        # notas cujo EMITENTE não é a empresa do SPED (entrada, ou saída de outra empresa)
    for p in xml_paths:
        x = parse_xml(p)
        if not x['is_nota']:
            ignorados_evento += 1
            continue
        # numa nota de SAÍDA, quem emite tem que ser a própria empresa do SPED
        if not (empresa_cnpj and x['cnpj'] == empresa_cnpj):
            nao_pertence.append(x)
            continue
        total_xml += x['vnf']
        sp = idx.get(x['chave'])
        if not sp:
            faltantes.append({**x, 'caminho': p})
        else:
            total_sped += sp['vl']
            dif = round(x['vnf'] - sp['vl'], 2)
            if abs(dif) > tol:
                divergencias.append({**x, 'vl_sped': sp['vl'], 'dif': dif})
            else:
                conciliadas.append({**x, 'vl_sped': sp['vl']})
    importadas = len(conciliadas) + len(divergencias) + len(faltantes)
    nao_pertence_grp = {}
    for x in nao_pertence:
        k = x['cnpj'] or '(sem CNPJ)'
        g = nao_pertence_grp.setdefault(k, {'cnpj': k, 'nome': x['fornecedor'], 'qtd': 0})
        g['qtd'] += 1
    return {
        'empresa': sped.get('empresa', {}),
        'importadas': importadas,
        'qtd_conciliadas': len(conciliadas),
        'qtd_faltantes': len(faltantes),
        'qtd_divergencias': len(divergencias),
        'encontradas': len(conciliadas) + len(divergencias),
        'total_xml': round(total_xml, 2),
        'total_sped_correspondente': round(total_sped, 2),
        'faltantes': faltantes,
        'divergencias': divergencias,
        'ignorados_evento': ignorados_evento,
        'qtd_nao_pertence': len(nao_pertence),
        'nao_pertence_grupos': sorted(nao_pertence_grp.values(), key=lambda g: -g['qtd']),
        'pct_conciliado': round((len(conciliadas) / importadas * 100) if importadas else 0.0, 1),
        'vendas_cfop': sped.get('vendas_cfop', []),
    }


def gerar_conferencia_saidas_html(cf, vendas_cfop=None, cliente=False):
    emp = cf['empresa']
    logo = _logo_uri()
    logo_html = f'<img src="{logo}" alt="Liddera">' if logo else ''
    status_segs = [('Conciliadas', cf['qtd_conciliadas'], '#0ea472'),
                   ('Divergências', cf['qtd_divergencias'], '#d4711a'),
                   ('Faltantes', cf['qtd_faltantes'], '#e23d4c')]
    arcs_status = _donut(status_segs, is_money=False)
    tot_s = cf['importadas'] or 1
    leg_status = ''.join(
        f'<div class="lg"><span class="dot" style="background:{c}"></span>{l}<b>{v}</b><span class="pc">{v/tot_s*100:.1f}%</span></div>'
        for l, v, c in status_segs)

    palette = ['#e8632b', '#1f2a5a', '#2aa9a0', '#3a7bd5', '#e0a92e', '#9aa3c0', '#7c3aed', '#0ea472']
    vc = (vendas_cfop or cf.get('vendas_cfop') or [])[:8]
    cfop_segs = [(r['cfop'], r['valor'], palette[i % len(palette)]) for i, r in enumerate(vc)]
    arcs_cfop = _donut(cfop_segs) if cfop_segs else ''
    tot_c = sum(v for _, v, _ in cfop_segs) or 1
    leg_cfop = ''.join(
        f'<div class="lg"><span class="dot" style="background:{c}"></span>{cod} · {_esc(_cfop_desc(cod))}<b>R$ {_brl(v)}</b><span class="pc">{v/tot_c*100:.0f}%</span></div>'
        for cod, v, c in cfop_segs)

    dif = round(cf['total_xml'] - cf['total_sped_correspondente'], 2)
    pend_table = _tabela_pendencias_paginada(
        cf['faltantes'], cf['divergencias'], 'destinatario',
        'Todas as notas de saída importadas estão no SPED com valores conferindo.',
        'NF-e/NFC-e', 'Destinatário')

    descarte = []
    if cf.get('ignorados_evento'):
        descarte.append(f'{cf["ignorados_evento"]} arquivo(s) de evento/cancelamento (não são nota)')
    descarte_html = ('<div class="descarte">Ignorados nesta conferência: ' + ' · '.join(descarte) + '.</div>') if descarte else ''

    # ALERTA: XMLs cujo emitente não é a empresa do SPED (entrada misturada, ou saída de outra empresa)
    alerta_np_html = ''
    if cf.get('qtd_nao_pertence'):
        grupos = cf.get('nao_pertence_grupos', [])
        itens = ''.join(
            f'<li><b>{_esc(g["nome"] or "(sem nome)")}</b> — CNPJ {_esc(_fmt_cnpj(g["cnpj"]))} · {g["qtd"]} arquivo(s)</li>'
            for g in grupos)
        alerta_np_html = f"""<div class="alerta-oe">
          <div class="alerta-oe-t">⚠ {cf['qtd_nao_pertence']} arquivo(s) XML NÃO foram emitidos por esta empresa — não foram incluídos na conferência</div>
          <div class="alerta-oe-s">O emitente dessas notas não é <b>{_esc(emp.get('empresa',''))}</b> (CNPJ {_esc(_fmt_cnpj(re.sub(r'[^0-9]','',emp.get('cnpj','') or '')))}).
          Podem ser notas de ENTRADA (compra) misturadas na pasta, ou saídas de outra empresa. Confira antes de prosseguir:</div>
          <ul class="alerta-oe-l">{itens}</ul>
        </div>"""

    w_sped = (cf['total_sped_correspondente'] / cf['total_xml'] * 100) if cf['total_xml'] else 0
    dif_box = (f'<div class="vr-ok"><span>Valores conferem</span><span>R$ {_brl(dif)}</span></div>'
               if abs(dif) < 0.02 else
               f'<div class="vr-dif"><span>Diferença a resolver (notas pendentes)</span><span>R$ {_brl(dif)}</span></div>')

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Conferência de Saídas × SPED · {_esc(emp.get('empresa',''))}</title>
<style>{_CSS}</style></head><body><div class="wrap">
  <header class="sec">{logo_html}
    <div class="h-txt"><b>{'Liddera | Inteligência em Negócios' if cliente else 'FiscoCont+ · Módulo Fiscal'}</b><div>{'Conferência de Notas Fiscais de Saída' if cliente else 'Conferência NF-e/NFC-e de Saída × SPED Fiscal'}</div></div>
    {'' if cliente else '<span class="tagint">uso interno do escritório</span>'}</header>
  {alerta_np_html}
  <div class="band sec" style="animation-delay:.05s"><div>
    <h1>{_esc(emp.get('empresa',''))}</h1>
    <div class="meta">CNPJ {_esc(emp.get('cnpj',''))} · {_esc(emp.get('periodo',''))}</div>
  </div><div class="imp"><span class="ibtn on">✓ SPED importado</span><span class="ibtn">✓ {cf['importadas']} XMLs</span></div></div>
  <div class="cstats sec" style="animation-delay:.1s">
    <div class="cstat t"><div class="v cnt" data-t="{cf['importadas']}" data-int="1">0</div><div class="l">Notas de saída importadas</div></div>
    <div class="cstat ok"><div class="v cnt" data-t="{cf['qtd_conciliadas']}" data-int="1">0</div><div class="l">Conciliadas (valor bate)</div></div>
    <div class="cstat f"><div class="v cnt" data-t="{cf['qtd_faltantes']}" data-int="1">0</div><div class="l">Faltantes no SPED</div></div>
    <div class="cstat d"><div class="v cnt" data-t="{cf['qtd_divergencias']}" data-int="1">0</div><div class="l">Divergência de valor</div></div>
  </div>
  {descarte_html}
  <div class="grid2">
    <div class="card sec" style="animation-delay:.15s"><h3><span class="dot"></span>Status da conferência</h3>
      <div class="donut-row"><div class="donut"><svg width="180" height="180" viewBox="0 0 180 180">
        <circle cx="90" cy="90" r="66" fill="none" stroke="#eef1f7" stroke-width="26"/>{arcs_status}</svg>
        <div class="center"><div class="big">{_brl(cf['pct_conciliado'])}%</div><div class="sm">conciliado</div></div></div>
        <div class="legend">{leg_status}</div></div>
    </div>
    <div class="card sec" style="animation-delay:.2s"><h3><span class="dot"></span>Saídas por CFOP</h3>
      <div class="donut-row"><div class="donut"><svg width="180" height="180" viewBox="0 0 180 180">
        <circle cx="90" cy="90" r="66" fill="none" stroke="#eef1f7" stroke-width="26"/>{arcs_cfop}</svg>
        <div class="center"><div class="big">{cf['importadas']}</div><div class="sm">importadas</div></div></div>
        <div class="legend">{leg_cfop or '<div style=color:#6b7392;font-size:12.5px>Importe o SPED para ver por CFOP.</div>'}</div></div>
    </div>
  </div>
  <div class="grid2">
    <div class="card sec" style="animation-delay:.25s"><h3><span class="dot"></span>Conciliação de valores</h3>
      <div class="valrec">
        <div class="vr"><div class="top"><span>Total dos XMLs importados</span><b>R$ {_brl(cf['total_xml'])}</b></div><div class="bar"><span style="--w:100%;background:var(--navy)"></span></div></div>
        <div class="vr"><div class="top"><span>Correspondente no SPED</span><b>R$ {_brl(cf['total_sped_correspondente'])}</b></div><div class="bar"><span style="--w:{w_sped:.1f}%;background:var(--pos)"></span></div></div>
        {dif_box}
      </div>
    </div>
    <div class="conf sec" style="animation-delay:.3s"><h3 style="font-size:15px;color:var(--navy);display:flex;align-items:center;gap:8px;margin-bottom:6px"><span class="dot" style="background:var(--orange);width:8px;height:18px;border-radius:3px;display:inline-block"></span>Pendências</h3>{pend_table}</div>
  </div>
  <footer>{'Liddera | Inteligência em Negócios Ltda' if cliente else 'FiscoCont+ · Conferência interna · Liddera | Inteligência em Negócios Ltda'}</footer>
</div>{_COUNT_JS}</body></html>"""

# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def gerar_documentos_html(sped: dict) -> str:
    emp = sped.get('empresa', {})
    logo = _logo_uri()
    logo_html = f'<img src="{logo}" alt="Liddera">' if logo else ''
    docs = sped.get('documentos_entrada', [])
    resumo = sped.get('resumo_tipo_doc', [])
    compras = sped.get('compras_cfop', [])
    saidas = sped.get('saidas_cfop', [])
    tot_val = sped.get('total_doc_valor', 0.0)
    tot_icms = sped.get('total_doc_icms', 0.0)

    cor_tipo = {'NF-e': '#1f2a5a', 'CT-e': '#e8632b', 'NF3-e': '#14b8a6', 'NFCom': '#e0a92e', 'Energia/Com.': '#a855f7'}
    _PAL = ['#1f2a5a', '#e8632b', '#14b8a6', '#4f46e5', '#f59e0b', '#0ea5e9', '#a855f7', '#94a3b8']

    # KPIs por tipo
    chips = ''.join(
        f'<div class="cstat"><div class="v">{t["qtd"]}</div><div class="l">{_esc(t["tipo"])}</div></div>'
        for t in resumo)

    # Pizza por tipo (usa _donut com raio grande = pizza cheia)
    segs_tipo = [(t['tipo'], t['valor'], cor_tipo.get(t['tipo'], '#94a3b8')) for t in resumo]
    pie = _donut(segs_tipo, cx=90, cy=90, r=45, sw=90)
    leg_tipo = ''.join(
        f'<div class="lg"><span class="dot" style="background:{cor_tipo.get(t["tipo"],"#94a3b8")}"></span>{_esc(t["tipo"])}'
        f'<b>R$ {_brl(t["valor"])}</b></div>' for t in resumo)

    # Donut por CFOP (entradas)
    top_cfop = compras[:8]
    segs_cfop = [(c['cfop'], c['valor'], _PAL[i % len(_PAL)]) for i, c in enumerate(top_cfop)]
    donut_cfop = _donut(segs_cfop, cx=90, cy=90, r=66, sw=26)
    leg_cfop = ''.join(
        f'<div class="lg"><span class="dot" style="background:{_PAL[i%len(_PAL)]}"></span>{_esc(c["cfop"])} · {_esc(c["desc"])[:26]}'
        f'<b>R$ {_brl(c["valor"])}</b></div>' for i, c in enumerate(top_cfop))
    maxc = max((c['valor'] for c in compras), default=1)
    maxs = max((c['valor'] for c in saidas), default=1)

    # Tabela agrupada por tipo
    body = ''
    for t in resumo:
        tp = t['tipo']
        body += (f'<tr class="grp"><td colspan="5"><span class="gd" style="background:{cor_tipo.get(tp,"#94a3b8")}"></span>'
                 f'{_esc(tp)} · {t["qtd"]} documento(s) · R$ {_brl(t["valor"])}'
                 f'{" · ICMS R$ " + _brl(t["icms"]) if t["icms"] else ""}</td></tr>')
        for d in docs:
            if d['tipo'] != tp:
                continue
            icms = f'R$ {_brl(d["icms"])}' if d['icms'] else '<span class="muted">—</span>'
            body += (f'<tr><td>{_esc(d["data"])}</td><td>{_esc(d["num"])}</td>'
                     f'<td class="chave">{_esc(d["chave"])}</td><td class="num">R$ {_brl(d["valor"])}</td>'
                     f'<td class="num">{icms}</td></tr>')

    saidas_bars = _bars(saidas[:8], 'var(--orange)', maxs) if saidas else '<div class="muted" style="padding:14px">Sem saídas por CFOP no período.</div>'

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Documentos de entrada · {_esc(emp.get('empresa',''))}</title>
<style>{_CSS}
.docwrap table{{width:100%;border-collapse:collapse;font-size:12.5px}}
.docwrap thead th{{text-align:left;color:var(--ink2);font-size:10.5px;text-transform:uppercase;letter-spacing:.4px;padding:9px 10px;border-bottom:1px solid var(--line);position:sticky;top:0;background:#fff}}
.docwrap thead th.num,.docwrap td.num{{text-align:right}}
.docwrap td{{padding:8px 10px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}}
.docwrap td.chave{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:10px;color:#475069;word-break:break-all;max-width:230px}}
.docwrap tr.grp td{{background:#f3f5fb;font-weight:800;color:var(--navy);font-size:11.5px;letter-spacing:.3px;padding:9px 12px}}
.docwrap tr.grp .gd{{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:8px;vertical-align:middle}}
.muted{{color:var(--ink2)}}
.pie-wrap{{display:flex;align-items:center;gap:16px}}.pie-wrap .legend{{flex:1}}
</style></head><body><div class="wrap">
  <div class="toolbar no-print" style="display:flex;gap:10px;margin-bottom:14px;align-items:center">
    <span style="color:var(--orange);font-weight:800">LIDDERA · Documentos de entrada</span>
    <button onclick="window.print()" style="margin-left:auto;background:var(--orange);color:#fff;border:0;border-radius:9px;padding:9px 14px;font-size:13px;cursor:pointer">⬇ Exportar PDF</button>
  </div>
  <header class="sec">{logo_html}
    <div class="h-txt"><b>FiscoCont+ · Módulo Fiscal</b><div>Relação de documentos de entrada (NF-e · CT-e · NF3-e · NFCom)</div></div>
    <span class="tagint">a partir do SPED Fiscal</span></header>
  <div class="band sec" style="animation-delay:.05s"><div>
    <h1>{_esc(emp.get('empresa',''))}</h1>
    <div class="meta">CNPJ {_esc(emp.get('cnpj',''))} · {_esc(emp.get('periodo',''))}</div>
  </div><div class="imp"><span class="ibtn on">✓ {len(docs)} documentos</span><span class="ibtn">R$ {_brl(tot_val)}</span></div></div>

  <div class="cstats sec" style="animation-delay:.1s">
    <div class="cstat t"><div class="v">{len(docs)}</div><div class="l">Documentos de entrada</div></div>
    <div class="cstat ok"><div class="v" style="font-size:20px">R$ {_brl(tot_val)}</div><div class="l">Valor total</div></div>
    <div class="cstat d"><div class="v" style="font-size:20px">R$ {_brl(tot_icms)}</div><div class="l">ICMS destacado</div></div>
    {chips}
  </div>

  <div class="grid2 sec" style="animation-delay:.15s">
    <div class="card"><h3><span class="dot"></span>Documentos por tipo (pizza)</h3>
      <div class="pie-wrap"><svg width="180" height="180" viewBox="0 0 180 180">{pie}</svg>
      <div class="legend">{leg_tipo}</div></div></div>
    <div class="card"><h3><span class="dot"></span>Entradas por CFOP</h3>
      <div class="donut-row"><div class="donut"><svg width="180" height="180" viewBox="0 0 180 180">
        <circle cx="90" cy="90" r="66" fill="none" stroke="#eef1f7" stroke-width="26"/>{donut_cfop}</svg></div>
        <div class="legend">{leg_cfop}</div></div></div>
  </div>

  <div class="card sec docwrap" style="animation-delay:.2s"><h3><span class="dot"></span>Relação de documentos</h3>
    <table><thead><tr><th>Data</th><th>Nº</th><th>Chave de acesso (44 dígitos)</th><th class="num">Valor</th><th class="num">ICMS</th></tr></thead>
    <tbody>{body}</tbody></table></div>

  <div class="card sec" style="animation-delay:.25s"><h3><span class="dot"></span>Saídas por CFOP</h3>{saidas_bars}</div>

  <footer style="text-align:center;color:var(--ink2);font-size:11px;margin-top:16px">Gerado pelo FiscoCont+ · Liddera | Inteligência em Negócios Ltda · fonte: SPED Fiscal</footer>
</div>{_COUNT_JS}</body></html>"""


# --------------------------------------------------------------------------- #
# Painel do Simples Nacional — parser do Extrato do PGDAS-D
# --------------------------------------------------------------------------- #
# Tabelas oficiais dos Anexos I a V (LC 123/2006, valores vigentes desde jan/2018,
# sem alteração até 2027 por força da Reforma Tributária/LC 214-2025). Cada faixa:
# (limite superior do RBT12, alíquota nominal, parcela a deduzir).
_ANEXOS_SN = {
    'I': [  # Comércio
        (180000.00, 0.0400, 0.00),
        (360000.00, 0.0730, 5940.00),
        (720000.00, 0.0950, 13860.00),
        (1800000.00, 0.1070, 22500.00),
        (3600000.00, 0.1430, 87300.00),
        (4800000.00, 0.1900, 378000.00),
    ],
    'II': [  # Indústria
        (180000.00, 0.0450, 0.00),
        (360000.00, 0.0780, 5940.00),
        (720000.00, 0.1000, 13860.00),
        (1800000.00, 0.1120, 22500.00),
        (3600000.00, 0.1470, 85500.00),
        (4800000.00, 0.3000, 720000.00),
    ],
    'III': [  # Serviços (regra geral)
        (180000.00, 0.0600, 0.00),
        (360000.00, 0.1120, 9360.00),
        (720000.00, 0.1350, 17640.00),
        (1800000.00, 0.1600, 35640.00),
        (3600000.00, 0.2100, 125640.00),
        (4800000.00, 0.3300, 648000.00),
    ],
    'IV': [  # Serviços (construção, vigilância, limpeza, advocacia etc. — sem CPP no DAS)
        (180000.00, 0.0450, 0.00),
        (360000.00, 0.0900, 8100.00),
        (720000.00, 0.1020, 12420.00),
        (1800000.00, 0.1400, 39780.00),
        (3600000.00, 0.2200, 183780.00),
        (4800000.00, 0.3300, 828000.00),
    ],
    'V': [  # Serviços intelectuais (sujeitos ao Fator r)
        (180000.00, 0.1550, 0.00),
        (360000.00, 0.1800, 4500.00),
        (720000.00, 0.1950, 9900.00),
        (1800000.00, 0.2050, 17100.00),
        (3600000.00, 0.2300, 62100.00),
        (4800000.00, 0.3050, 540000.00),
    ],
}

def _detectar_anexo(descricao):
    """Identifica o Anexo a partir da descrição da atividade no PGDAS-D.
    Serviços (Anexos III/IV/V) sempre vêm com "Sujeitos ao Anexo X" explícito
    na descrição — mas Comércio (Anexo I) e Indústria (Anexo II) costumam vir
    SEM mencionar o Anexo, só pelo tipo da atividade ("Revenda de mercadorias",
    "Venda de mercadorias industrializadas") — achado real testando um extrato
    de comércio de verdade, onde a detecção por regex simples falhava."""
    m = re.search(r'Anexo\s+([IVX]+)', descricao)
    if m:
        return m.group(1)
    d = descricao.lower()
    if 'revenda de mercadoria' in d:
        return 'I'
    if 'venda de mercadoria' in d and 'industrializad' in d:
        return 'II'
    return None

def calcular_aliquota_efetiva(rbt12, anexo):
    """Fórmula oficial: aliq. efetiva = (RBT12 × aliq. nominal − parcela a deduzir) / RBT12.
    Retorna None se o Anexo não for reconhecido (ex.: MEI, ou string composta tipo "I e III"
    — nesses casos o cálculo depende de regra própria não coberta aqui)."""
    tabela = _ANEXOS_SN.get((anexo or '').strip().upper())
    if not tabela or rbt12 is None or rbt12 <= 0:
        return None
    faixa_n = None
    aliq_nominal = parcela_deduzir = 0.0
    limite_inf = 0.0
    for i, (limite_sup, aliq, parcela) in enumerate(tabela, start=1):
        if rbt12 <= limite_sup:
            faixa_n, aliq_nominal, parcela_deduzir = i, aliq, parcela
            break
        limite_inf = limite_sup
    if faixa_n is None:
        # acima do teto de R$4,8mi — fora do Simples, mantém a última faixa como referência
        faixa_n, aliq_nominal, parcela_deduzir = len(tabela), tabela[-1][1], tabela[-1][2]
    aliq_efetiva = ((rbt12 * aliq_nominal) - parcela_deduzir) / rbt12
    return {
        'anexo': anexo, 'faixa': faixa_n, 'aliquota_nominal': round(aliq_nominal * 100, 2),
        'parcela_deduzir': round(parcela_deduzir, 2), 'aliquota_efetiva': round(aliq_efetiva * 100, 4),
        'limite_inferior_faixa': limite_inf,
    }

_MONEY_RE = r'[\d.]+,\d{2}'
# Nomes de tributo reconhecidos na tabela do PGDAS-D — inclui CBS/IBS, que passam a
# aparecer nos extratos a partir de jan/2027 (Reforma Tributária, Resolução CGSN
# 190/2026): CBS substitui PIS+COFINS na partilha, IBS aparece como coluna nova.
# ATENÇÃO: até a data desta implementação (set/2026) a Receita ainda não publicou
# nenhum extrato real nesse formato novo — isso é preparação bem pesquisada, mas
# não testada contra um exemplo de verdade. Vale conferir assim que o 1º extrato
# de 2027 chegar.
_TRIB_NOMES_TODOS = ['IRPJ', 'CSLL', 'COFINS', 'PIS/Pasep', 'CBS', 'INSS/CPP', 'ICMS', 'IBS', 'IPI', 'ISS']
_TRIB_CHAVE = {'IRPJ': 'irpj', 'CSLL': 'csll', 'COFINS': 'cofins', 'PIS/Pasep': 'pis_pasep', 'CBS': 'cbs',
               'INSS/CPP': 'inss_cpp', 'ICMS': 'icms', 'IBS': 'ibs', 'IPI': 'ipi', 'ISS': 'iss'}
_TRIB_NOME_ALT = '|'.join(re.escape(n) for n in _TRIB_NOMES_TODOS)
_TRIB_HDR_RE = r'((?:(?:' + _TRIB_NOME_ALT + r')\s+)+)Total'
_TRIB_KEYS = list(_TRIB_CHAVE.values()) + ['total']  # todas as chaves POSSÍVEIS (velhas + novas)

def _secao(txt, ini, fim=None):
    i = txt.find(ini)
    if i == -1:
        return ''
    i += len(ini)
    if fim:
        j = txt.find(fim, i)
        if j != -1:
            return txt[i:j]
    return txt[i:]

def _tabela_tributos_pgdas(texto):
    """Extrai a tabela de tributos (IRPJ/CSLL/.../Total) logo à frente de `texto`,
    reconhecendo dinamicamente quais colunas aparecem (formato atual OU o formato
    com CBS/IBS da Reforma, a partir de 2027) — sempre devolve TODAS as chaves
    conhecidas, com 0.0 nas que não aparecerem nesse extrato específico."""
    mm = re.search(_TRIB_HDR_RE, texto, re.S)
    out = {k: 0.0 for k in _TRIB_KEYS}
    if not mm:
        return out
    nomes = mm.group(1).split()
    chaves = [_TRIB_CHAVE.get(n, n.lower()) for n in nomes] + ['total']
    vals = re.findall(_MONEY_RE, texto[mm.end():mm.end() + 200])[:len(chaves)]
    for k, v in zip(chaves, vals):
        out[k] = _num(v)
    return out

def parse_pgdas_extrato(pdf_path):
    """Lê o Extrato do Simples Nacional (PGDAS-D, documento oficial gerado pela
    Receita Federal) em PDF e devolve os dados estruturados para o Painel do
    Simples Nacional: contribuinte, apuração do período (RPA/RBT12/RBA/RBAA),
    histórico mensal de receita (18 meses, já vem pronto no próprio extrato),
    atividades tributadas (pode haver mais de uma no mesmo PA — ex.: serviço
    com e sem retenção de ISS), totais consolidados por tributo e o DAS gerado."""
    with pdfplumber.open(pdf_path) as pdf:
        paginas = [p.extract_text() or '' for p in pdf.pages]
    txt = '\n'.join(paginas)
    # concatena tudo numa linha só: o PGDAS-D quebra células de tabela em linhas
    # separadas de forma inconsistente entre extratos — colapsar evita depender
    # da posição exata da quebra.
    flat = re.sub(r'[ \t]*\n[ \t]*', ' ', txt)

    def _mmm(pat):
        mm = re.search(pat, flat, re.S)
        if not mm:
            return {'interno': 0.0, 'externo': 0.0, 'total': 0.0}
        return {'interno': _num(mm.group(1)), 'externo': _num(mm.group(2)), 'total': _num(mm.group(3))}

    out = {}

    # ---- Cabeçalho do extrato ----
    m = re.search(r'Gerado em ([\d/]+ [\d:]+)', flat)
    extrato = {'gerado_em': m.group(1) if m else ''}
    m = re.search(r'Apurado em ([\d/]+ [\d:]+)', flat)
    extrato['apurado_em'] = m.group(1) if m else ''
    m = re.search(r'Apura[çc][ãa]o (Original|Retificadora)', flat)
    extrato['tipo_apuracao'] = m.group(1) if m else ''
    m = re.search(r'PGDAS-D \d+ Vers[ãa]o ([\d.]+)', flat)
    extrato['pgdas_versao'] = m.group(1) if m else ''
    out['extrato'] = extrato

    # ---- 1) Contribuinte ----
    m = re.search(r'CNPJ B[áa]sico:\s*([\d.]+)\s+Nome Empresarial:\s*(.+?)\s+Data de Abertura:', flat)
    contribuinte = {
        'cnpj_basico': m.group(1) if m else '',
        'nome_empresarial': m.group(2).strip() if m else '',
    }
    m = re.search(r'Data de Abertura:\s*([\d/]+)\s+Regime de Apura[çc][ãa]o:\s*(.+?)\s+Optante pelo Simples Nacional:\s*(Sim|N[ãa]o)', flat)
    if m:
        contribuinte['data_abertura'] = m.group(1)
        contribuinte['regime_apuracao'] = m.group(2).strip()
        contribuinte['optante_simples'] = m.group(3) == 'Sim'
    out['contribuinte'] = contribuinte

    # ---- 2) Apuração ----
    m = re.search(r'Informa[çc][õo]es da Apura[çc][ãa]o\s*(\d+)', flat)
    m_pa = re.search(r'Per[íi]odo de Apura[çc][ãa]o \(PA\):\s*(\d{2}/\d{4})', flat)
    out['apuracao'] = {'numero': m.group(1) if m else '', 'pa': m_pa.group(1) if m_pa else ''}

    # ---- 2.1 Discriminativo de Receitas ----
    rpa = _mmm(r'Receita Bruta do PA \(RPA\) - Compet[êe]ncia\s+(' + _MONEY_RE + r')\s+(' + _MONEY_RE + r')\s+(' + _MONEY_RE + r')')
    rbt12 = _mmm(r'anteriores ao PA\s*(?:\(RBT12\)\s*)?(' + _MONEY_RE + r')\s+(' + _MONEY_RE + r')\s+(' + _MONEY_RE + r')(?:\s*\(RBT12\))?')
    rbt12p = _mmm(r'proporcionalizada\s*\(RBT12p\)\s+(' + _MONEY_RE + r')\s+(' + _MONEY_RE + r')\s+(' + _MONEY_RE + r')')
    rba = _mmm(r'ano-calend[áa]rio corrente \(RBA\)\s+(' + _MONEY_RE + r')\s+(' + _MONEY_RE + r')\s+(' + _MONEY_RE + r')')
    rbaa = _mmm(r'ano-calend[áa]rio anterior\s*(?:\(RBAA\)\s*)?(' + _MONEY_RE + r')\s+(' + _MONEY_RE + r')\s+(' + _MONEY_RE + r')(?:\s*\(RBAA\))?')
    m = re.search(r'Limite de receita bruta proporcionalizado\s+(' + _MONEY_RE + r')\s+(' + _MONEY_RE + r')(?:\s+(' + _MONEY_RE + r'))?', flat)
    if m:
        vals = [g for g in m.groups() if g]
        limite = {'interno': _num(vals[0]), 'total': _num(vals[-1])}
    else:
        limite = {'interno': 0.0, 'total': 0.0}
    out['receitas'] = {'rpa': rpa, 'rbt12': rbt12, 'rbt12p': rbt12p, 'rba': rba, 'rbaa': rbaa,
                        'limite_proporcionalizado': limite}

    # ---- 2.2 Receitas Brutas Anteriores (histórico mensal — já vem pronto no extrato) ----
    bloco22 = _secao(txt, '2.2) Receitas Brutas Anteriores', '2.3)')
    bloco_interno = _secao(bloco22, '2.2.1) Mercado Interno', '2.2.2) Mercado Externo')
    bloco_externo = _secao(bloco22, '2.2.2) Mercado Externo')
    hist_interno = {mm_: _num(v) for mm_, v in re.findall(r'(\d{2}/\d{4})\s+(' + _MONEY_RE + r')', bloco_interno)}
    hist_externo = {mm_: _num(v) for mm_, v in re.findall(r'(\d{2}/\d{4})\s+(' + _MONEY_RE + r')', bloco_externo)}
    out['receitas_anteriores'] = {'interno': hist_interno, 'externo': hist_externo}

    # ---- 2.4 Fator r ----
    m = re.search(r'Fator r\s*=\s*(.+?)(?:\n|\.)', txt)
    out['fator_r'] = m.group(1).strip() if m else None

    # ---- 3) Estabelecimento ----
    m = re.search(r'CNPJ Estabelecimento:\s*([\d./-]+)', flat)
    m_mun = re.search(r'Munic[íi]pio:\s*(.+?)\s+UF:\s*(\w+)', flat)
    m_sub = re.search(r'Sublimite de Receita Anual \(R\$\):\s*(' + _MONEY_RE + r')', flat)
    m_imp = re.search(r'Impedido de recolher ICMS/ISS no DAS:\s*(Sim|N[ãa]o)', flat)
    out['estabelecimento'] = {
        'cnpj': m.group(1) if m else '',
        'municipio': m_mun.group(1).strip() if m_mun else '',
        'uf': m_mun.group(2) if m_mun else '',
        'sublimite_anual': _num(m_sub.group(1)) if m_sub else 0.0,
        'impedido_icms_iss': (m_imp.group(1) == 'Sim') if m_imp else False,
    }

    # ---- Atividades tributadas (pode haver mais de um bloco no mesmo PA) ----
    atividades = []
    # Tolerância a "Página N": quando o bloco de atividade cai bem na quebra de
    # página do PDF, o pdfplumber injeta o rodapé "Página N" entre o valor da
    # Receita Bruta Informada e o cabeçalho de tributos — achado real com um
    # extrato de Anexo III de 1 única atividade (RD TERRAPLANAGEM, PA 08/2026)
    # onde a lista de atividades saía vazia por causa disso.
    pat_ativ_cab = (r'Valor do D[ée]bito por Tributo para a Atividade \(R\$\):\s*(.+?)\s*'
                     r'Receita Bruta Informada:\s*R\$\s*(' + _MONEY_RE + r')\s*(?:P[áa]gina\s*\d+\s*)?' + _TRIB_HDR_RE)
    for bloco_m in re.finditer(pat_ativ_cab, flat):
        descricao = bloco_m.group(1).strip()
        nomes = bloco_m.group(3).split()
        chaves = [_TRIB_CHAVE.get(n, n.lower()) for n in nomes] + ['total']
        resto = flat[bloco_m.end():bloco_m.end() + 400]
        vals = re.findall(_MONEY_RE, resto)[:len(chaves)]
        tributos = {k: 0.0 for k in _TRIB_KEYS}
        for k, v in zip(chaves, vals):
            tributos[k] = _num(v)
        parcelas = [_num(v) for v in re.findall(r'Parcela \d+:\s*R\$\s*(' + _MONEY_RE + r')', resto)]
        anexo_m = _detectar_anexo(descricao)
        atividades.append({
            'descricao': descricao,
            'anexo': anexo_m,
            'receita_bruta_informada': _num(bloco_m.group(2)),
            'tributos': tributos,
            'parcelas': parcelas,
        })
    out['atividades'] = atividades
    for a in atividades:
        a['aliquota_oficial'] = calcular_aliquota_efetiva(rbt12['total'], a['anexo']) if a['anexo'] else None
    out['anexos_identificados'] = sorted({a['anexo'] for a in atividades if a['anexo']})

    # ---- Totais por Estabelecimento e da Empresa (3 tabelas cada: Declarado/Suspenso/Exigível) ----
    def _totais_3tabelas(bloco):
        decl = _secao(bloco, 'Total do D\u00e9bito Declarado', 'Total do D\u00e9bito com Exigibilidade Suspensa')
        susp = _secao(bloco, 'Total do D\u00e9bito com Exigibilidade Suspensa', 'Total do D\u00e9bito Exig\u00edvel')
        exig = _secao(bloco, 'Total do D\u00e9bito Exig\u00edvel')
        return {'declarado': _tabela_tributos_pgdas(decl), 'suspenso': _tabela_tributos_pgdas(susp),
                'exigivel': _tabela_tributos_pgdas(exig)}

    bloco_estab = _secao(flat, 'Informa\u00e7\u00f5es por Estabelecimento', '4) Total Geral da Empresa')
    m = re.search(r'Valor Informado:\s*(' + _MONEY_RE + r')', bloco_estab)
    out['totais_estabelecimento'] = {'valor_informado': _num(m.group(1)) if m else 0.0, **_totais_3tabelas(bloco_estab)}

    bloco_emp = _secao(flat, '4) Total Geral da Empresa', '5) Este item')
    out['totais_empresa'] = _totais_3tabelas(bloco_emp)

    # ---- 6) DAS gerado ----
    bloco_das = _secao(flat, '6) Informa\u00e7\u00f5es sobre DAS Gerado')
    m = re.search(r'N[úu]mero:\s*(\d+)', bloco_das)
    das_numero = m.group(1) if m else ''
    datas = re.findall(r'(\d{2}/\d{2}/\d{4})', _secao(bloco_das, das_numero, '6.1)')) if das_numero else []
    das_vencimento = datas[0] if datas else ''
    das_acolhimento = datas[1] if len(datas) >= 2 else das_vencimento
    m2 = re.search(
        r'IRPJ\s+(' + _MONEY_RE + r')\s+CSLL\s+(' + _MONEY_RE + r')\s+COFINS\s+(' + _MONEY_RE + r')\s+PIS/PASEP\s+(' + _MONEY_RE + r')\s+'
        r'INSS/CPP\s+(' + _MONEY_RE + r')\s+ICMS\s+(' + _MONEY_RE + r')\s+IPI\s+(' + _MONEY_RE + r')\s+ISS\s+(' + _MONEY_RE + r')',
        bloco_das)
    das_tributos = {}
    if m2:
        for i, k in enumerate(['irpj', 'csll', 'cofins', 'pis_pasep', 'inss_cpp', 'icms', 'ipi', 'iss']):
            das_tributos[k] = _num(m2.group(1 + i))
    m3 = re.search(r'Principal\s+(' + _MONEY_RE + r')\s+Multa\s+(' + _MONEY_RE + r')\s+Juros\s+(' + _MONEY_RE + r')\s+Total\s+(' + _MONEY_RE + r')', bloco_das)
    principal, multa, juros, total_das = (_num(m3.group(1)), _num(m3.group(2)), _num(m3.group(3)), _num(m3.group(4))) if m3 else (0.0, 0.0, 0.0, 0.0)

    bloco_61 = _secao(flat, '6.1)', '6.2)')
    _TRIB_DESTINO_ALT = r'IRPJ|CSLL|COFINS|PIS/Pasep|PIS|INSS/CPP|ICMS|IPI|ISS|CBS|IBS'
    destino = [{'tributo': t, 'valor': _num(v), 'ente': e.strip()} for t, v, e in re.findall(
        r'(' + _TRIB_DESTINO_ALT + r')\s+(' + _MONEY_RE + r')\s+(.+?)(?=\s*(?:' + _TRIB_DESTINO_ALT + r'|P\u00e1gina|$))', bloco_61)]
    status_arrecadacao = _secao(flat, 'Informa\u00e7\u00f5es da Arrecada\u00e7\u00e3o do DAS gerado nesta apura\u00e7\u00e3o').split('P\u00e1gina')[0].strip()

    out['das'] = {
        'numero': das_numero, 'vencimento': das_vencimento, 'data_limite_acolhimento': das_acolhimento,
        'tributos': das_tributos, 'principal': principal, 'multa': multa, 'juros': juros, 'total': total_das,
        'destino': destino, 'status_arrecadacao': status_arrecadacao,
    }

    # ---- Alíquota efetiva ----
    # Oficial (fórmula da LC 123, por Anexo — usa o 1º Anexo identificado; na
    # prática quase sempre há um só por empresa. Se vier vazio, faltou reconhecer
    # o texto "Anexo X" na descrição da atividade.)
    # Anexo "principal" pra alíquota do topo do painel: o da atividade de MAIOR
    # receita no período (mais representativo que só pegar o 1º em ordem alfabética
    # — achado real testando uma empresa com Comércio + Serviços misturados, onde
    # o Anexo I aparecia primeiro na ordenação mas a maior parte da receita era
    # do Anexo III).
    atividades_com_anexo = [a for a in atividades if a.get('anexo')]
    anexo_principal = (max(atividades_com_anexo, key=lambda a: a['receita_bruta_informada'])['anexo']
                        if atividades_com_anexo else None)
    out['aliquota_oficial'] = calcular_aliquota_efetiva(rbt12['total'], anexo_principal)
    # Realizada neste PA especificamente (Débito Exigível ÷ RPA) — pode divergir da
    # oficial quando há retenção/substituição tributária (ex.: ISS retido pelo tomador
    # não entra no DAS, então o total pago no mês fica menor que o teórico).
    rpa_total = rpa['total'] or 0.0
    out['aliquota_realizada'] = round((out['totais_empresa']['exigivel']['total'] / rpa_total * 100), 4) if rpa_total else 0.0

    return out


def _out(path, content):
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(content)

def main(argv):
    if len(argv) < 1:
        print('uso: fiscal_core.py [sped|conferencia|desoneracao|pgdas] ARQ.txt ...'); return 1
    modo = argv[0]

    # "pgdas" não depende de SPED nenhum — só do Extrato do PGDAS-D (PDF).
    # "ler-certificado" — lê um .pfx e devolve CNPJ/razão social/validade.
    if modo == 'ler-certificado':
        if len(argv) < 2:
            print('uso: fiscal_core.py ler-certificado CERTIFICADO.pfx --senha SENHA'); return 1
        args = argv[2:]

        def optc(name, default=None):
            return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default
        senha = optc('--senha', '')
        try:
            info = ler_certificado_pfx(argv[1], senha)
        except Exception as e:
            info = {'erro': str(e)}
        if '--json' in args:
            _out(optc('--json', 'certificado.json'), json.dumps(info, ensure_ascii=False))
        print(json.dumps(info, ensure_ascii=False))
        return 0 if 'erro' not in info else 1

    # "ler-certificados-lote" — testa várias senhas candidatas em vários .pfx
    # de uma vez, num processo só. Entrada: JSON [{"caminho":..., "candidatas":[...]}].
    if modo == 'ler-certificados-lote':
        if len(argv) < 2:
            print('uso: fiscal_core.py ler-certificados-lote ENTRADA.json [--json SAIDA.json]'); return 1
        args = argv[2:]
        with open(argv[1], encoding='utf-8') as f:
            itens = json.load(f)
        resultados = testar_senhas_certificados(itens)
        if '--json' in args and args.index('--json') + 1 < len(args):
            _out(args[args.index('--json') + 1], json.dumps(resultados, ensure_ascii=False))
        print(json.dumps({'total': len(resultados), 'abertos': sum(1 for r in resultados if r['ok'])}))
        return 0

    # "baixar-nfse" — roda o download de NFS-e via ADN pra uma empresa/período.
    if modo == 'baixar-nfse':
        if len(argv) < 2:
            print('uso: fiscal_core.py baixar-nfse CERTIFICADO.pfx --senha SENHA --empresa NOME --cnpj CNPJ --pasta PASTA_BASE --inicio AAAA-MM-DD --fim AAAA-MM-DD [--nsu N] [--homologacao] [--json saida.json]'); return 1
        args = argv[2:]

        def optb(name, default=None):
            return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default
        resultado = baixar_nfse_adn(
            cert_path=argv[1], senha=optb('--senha', ''),
            data_inicial=optb('--inicio'), data_final=optb('--fim'),
            pasta_base=optb('--pasta'), nome_empresa=optb('--empresa'), cnpj_empresa=optb('--cnpj', ''),
            nsu_inicial=int(optb('--nsu', '0')), homologacao=('--homologacao' in args),
        )
        if '--json' in args:
            _out(optb('--json', 'resultado_nfse.json'), json.dumps(resultado, ensure_ascii=False))
        print(json.dumps(resultado, ensure_ascii=False))
        return 0 if not resultado.get('erro') else 1

    # "analisar-nfse" — lê os XMLs de NFS-e já baixados (recursivo) e monta
    # o painel de com×sem retenção e top parceiros.
    if modo == 'analisar-nfse':
        if len(argv) < 2:
            print('uso: fiscal_core.py analisar-nfse PASTA --cnpj CNPJ_EMPRESA [--empresa NOME] [--inicio AAAA-MM-DD] [--fim AAAA-MM-DD] [--painel-html saida.html] [--json saida.json]'); return 1
        args = argv[2:]

        def opta(name, default=None):
            return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default
        pasta = argv[1]
        caminhos = glob.glob(os.path.join(pasta, '**', '*.xml'), recursive=True)
        dados = analisar_nfse(caminhos, opta('--cnpj', ''), data_inicial=opta('--inicio'), data_final=opta('--fim'))
        empresa_nome = opta('--empresa', '')
        if '--json' in args:
            _out(opta('--json', 'analise_nfse.json'), json.dumps(dados, ensure_ascii=False))
        if '--painel-html' in args:
            _out(opta('--painel-html', 'painel_nfse.html'), gerar_painel_nfse_html(dados, empresa_nome))
        print(json.dumps({k: v for k, v in dados.items() if k not in ('notas_com_retencao', 'notas_sem_retencao')}, ensure_ascii=False))
        return 0

    if modo == 'pgdas':
        if len(argv) < 2:
            print('uso: fiscal_core.py pgdas EXTRATO.pdf [--json saida.json] [--html saida.html]'); return 1
        args = argv[2:]

        def optp(name, default=None):
            return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default
        dados = parse_pgdas_extrato(argv[1])
        if '--json' in args:
            _out(optp('--json', 'pgdas.json'), json.dumps(dados, ensure_ascii=False))
            print('JSON gerado')
        if '--html' in args:
            historico = None
            hist_path = optp('--historico')
            if hist_path and os.path.exists(hist_path):
                with open(hist_path, 'r', encoding='utf-8') as fh:
                    historico = json.load(fh)
            _out(optp('--html', 'pgdas.html'), gerar_pgdas_html(dados, historico))
            print('Painel do Simples Nacional HTML gerado')
        if '--json' not in args and '--html' not in args:
            print(json.dumps(dados, ensure_ascii=False, indent=2))
        return 0

    # "visualizar-sped" (Admin) — mostra TODOS os dados de um SPED (original ou
    # já corrigido), sem mexer em nada.
    if modo == 'visualizar-sped':
        if len(argv) < 2:
            print('uso: fiscal_core.py visualizar-sped SPED.txt --html visualizacao.html [--empresa "Nome"] [--periodo "08/2026"]'); return 1
        args = argv[2:]

        def optv(name, default=None):
            return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default
        with open(argv[1], 'r', encoding='utf-8', errors='replace', newline='') as fh:
            texto = fh.read()
        html = gerar_visualizacao_sped_html(texto, optv('--empresa', ''), optv('--periodo', ''))
        _out(optv('--html', 'visualizacao.html'), html)
        print('Visualização do SPED gerada')
        return 0

    # "corrigir" (módulo restrito ao Admin) também não precisa do parse_sped —
    # trabalha direto no texto bruto, porque precisa preservar tudo que não for
    # explicitamente corrigido, byte a byte (inclusive a quebra de linha \r\n).
    if modo == 'corrigir':
        if len(argv) < 2:
            print('uso: fiscal_core.py corrigir SPED.txt --saida CORRIGIDO.txt [--cest 1705500,0000000,...] [--json resumo.json]'); return 1
        args = argv[2:]

        def optc(name, default=None):
            return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default
        with open(argv[1], 'r', encoding='utf-8', errors='replace', newline='') as fh:
            texto = fh.read()
        cest_str = optc('--cest', '')
        cest_invalidos = [c.strip() for c in cest_str.split(',') if c.strip()]
        corrigido, resumo = corrigir_sped_fiscal(texto, cest_invalidos)
        saida = optc('--saida', 'sped_corrigido.txt')
        with open(saida, 'w', encoding='utf-8', newline='') as fh:
            fh.write(corrigido)
        if '--json' in args:
            _out(optc('--json', 'resumo.json'), json.dumps(resumo, ensure_ascii=False))
        print('SPED corrigido gerado:', saida)
        print('resumo:', json.dumps(resumo, ensure_ascii=False))
        return 0

    # "desoneracao" não depende de SPED nenhum — só dos XMLs de entrada.
    if modo == 'desoneracao':
        args = argv[1:]

        def optd(name, default=None):
            return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default
        xml_arg = optd('--xmls')
        caminhos = [c for c in xml_arg.split(os.pathsep) if c] if xml_arg else []
        xmls = coletar_xmls(caminhos)
        cf = conferencia_desoneracao(xmls)
        if '--json' in args:
            _out(optd('--json', 'deson.json'), json.dumps(cf, ensure_ascii=False))
            print('JSON gerado')
        if '--html' in args:
            _out(optd('--html', 'deson.html'), gerar_desoneracao_html(cf))
            print('Desoneração HTML gerada')
        return 0

    if len(argv) < 2:
        print('uso: fiscal_core.py [sped|conferencia] ARQ.txt ...'); return 1
    sped_path = argv[1]
    args = argv[2:]

    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default

    sped = parse_sped(sped_path)

    if modo == 'sped':
        if '--json' in args:
            data = {k: v for k, v in sped.items() if k not in ('entradas_index', 'saidas_index', 'cfop_por_chave', 'cst_por_chave', 'itens_c170', 'ncm_por_item', 'produtos')}
            _out(opt('--json', 'sped.json'), json.dumps(data, ensure_ascii=False))
            print('JSON gerado')
        if '--dashboard-html' in args:
            _out(opt('--dashboard-html', 'dashboard.html'), gerar_dashboard_sped_html(sped))
            print('Dashboard HTML gerado')
        if '--documentos-html' in args:
            _out(opt('--documentos-html', 'documentos.html'), gerar_documentos_html(sped))
            print('Documentos HTML gerado')
        return 0

    if modo == 'preparar-inclusao':
        with open(sped_path, 'r', encoding='utf-8', errors='replace', newline='') as fh:
            texto = fh.read()
        xml_arg = opt('--xmls')
        caminhos = [c for c in xml_arg.split(os.pathsep) if c] if xml_arg else []
        xmls = coletar_xmls(caminhos)
        cf = conferencia(sped, xmls)
        preparadas = []
        for falt in cf['faltantes']:
            nota = falt
            cod_part = busca_cod_part_por_cnpj(texto, nota.get('cnpj', ''))
            itens = parse_xml_itens(falt['caminho'])
            for it in itens:
                it['cod_nat'] = _MAPA_COD_NAT_POR_CFOP.get(it['cfop_entrada'])
            pronta = bool(cod_part) and all(it['cfop_entrada'] and it['cst_icms'] and it['cod_nat'] for it in itens)
            preparadas.append({
                'caminho': falt['caminho'], 'chave': nota.get('chave'), 'nnf': nota.get('nnf'),
                'fornecedor': nota.get('fornecedor'), 'cnpj': nota.get('cnpj'), 'data': nota.get('data'),
                'valor': nota.get('vnf'), 'cod_part': cod_part, 'itens': itens, 'pronta': pronta,
            })
        resultado = {'total': len(preparadas), 'notas': preparadas}
        if '--json' in args:
            _out(opt('--json', 'preparadas.json'), json.dumps(resultado, ensure_ascii=False))
            print('JSON gerado')
        else:
            print(json.dumps(resultado, ensure_ascii=False))
        return 0

    if modo == 'incluir-notas':
        with open(sped_path, 'r', encoding='utf-8', errors='replace', newline='') as fh:
            texto = fh.read()
        entrada_path = opt('--entrada')
        if not entrada_path:
            print('uso: fiscal_core.py incluir-notas SPED.txt --entrada notas.json --saida SAIDA.txt [--json resumo.json]'); return 1
        with open(entrada_path, 'r', encoding='utf-8') as fh:
            notas_entrada = json.load(fh)
        notas_para_incluir = []
        for ne in notas_entrada:
            nota = parse_xml(ne['caminho'])
            itens = parse_xml_itens(ne['caminho'])
            for it, override in zip(itens, ne.get('itens', [])):
                if override.get('cfop_entrada'):
                    it['cfop_entrada'] = override['cfop_entrada']
                if override.get('cst_icms'):
                    it['cst_icms'] = override['cst_icms']
                it['cod_nat'] = override.get('cod_nat') or _MAPA_COD_NAT_POR_CFOP.get(it['cfop_entrada'])
            notas_para_incluir.append({'nota': nota, 'itens': itens})
        texto_final, resumo = adicionar_notas_ao_sped(texto, notas_para_incluir)
        saida = opt('--saida', 'sped_com_notas.txt')
        with open(saida, 'w', encoding='utf-8', newline='') as fh:
            fh.write(texto_final)
        if '--json' in args:
            _out(opt('--json', 'resumo_inclusao.json'), json.dumps(resumo, ensure_ascii=False))
        print('SPED com notas incluídas gerado:', saida)
        print('resumo:', json.dumps(resumo, ensure_ascii=False))
        return 0

    if modo == 'conferencia':
        xml_arg = opt('--xmls')
        caminhos = []
        if xml_arg:
            caminhos = [c for c in xml_arg.split(os.pathsep) if c]
        xmls = coletar_xmls(caminhos)
        cf = conferencia(sped, xmls)
        cf['compras_cfop'] = sped['compras_cfop']
        if '--json' in args:
            _out(opt('--json', 'conf.json'), json.dumps(cf, ensure_ascii=False))
            print('JSON gerado')
        if '--html' in args:
            _out(opt('--html', 'conf.html'), gerar_conferencia_html(cf, sped['compras_cfop'], cliente='--cliente' in args))
            print('Conferência HTML gerada')
        return 0

    if modo == 'conferencia-saidas':
        xml_arg = opt('--xmls')
        caminhos = []
        if xml_arg:
            caminhos = [c for c in xml_arg.split(os.pathsep) if c]
        xmls = coletar_xmls(caminhos)
        cf = conferencia_saidas(sped, xmls)
        cf['vendas_cfop'] = sped['vendas_cfop']
        if '--json' in args:
            _out(opt('--json', 'conf_saidas.json'), json.dumps(cf, ensure_ascii=False))
            print('JSON gerado')
        if '--html' in args:
            _out(opt('--html', 'conf_saidas.html'), gerar_conferencia_saidas_html(cf, sped['vendas_cfop'], cliente='--cliente' in args))
            print('Conferência de saídas HTML gerada')
        return 0

    if modo == 'frete':
        xml_arg = opt('--xmls')
        caminhos = []
        if xml_arg:
            caminhos = [c for c in xml_arg.split(os.pathsep) if c]
        xmls = coletar_xmls(caminhos)
        cf = conferencia_frete(sped, xmls)
        if '--json' in args:
            _out(opt('--json', 'frete.json'), json.dumps(cf, ensure_ascii=False))
            print('JSON gerado')
        if '--html' in args:
            _out(opt('--html', 'frete.html'), gerar_frete_html(cf))
            print('Classificação de Frete HTML gerada')
        return 0

    if modo == 'classificacao':
        cf = conferencia_classificacao(sped)
        if '--json' in args:
            _out(opt('--json', 'classificacao.json'), json.dumps(cf, ensure_ascii=False))
            print('JSON gerado')
        if '--html' in args:
            _out(opt('--html', 'classificacao.html'), gerar_classificacao_html(cf))
            print('Auditor de Classificação Fiscal HTML gerado')
        return 0

    print('modo inválido:', modo)
    return 1

def gerar_pgdas_html(dados, historico=None):
    """Painel do Simples Nacional pro cliente ver a situação da empresa —
    conta por conta, sempre gerado a partir de um Extrato do PGDAS-D já
    parseado (`parse_pgdas_extrato`). `historico` (opcional): lista de
    {pa, aliquota_efetiva} de competências anteriores já salvas na nuvem,
    do mais antigo pro mais recente — usada só pra calcular o delta vs o
    mês anterior (a evolução do faturamento já vem de dentro do próprio
    extrato, não depende de histórico salvo)."""
    contrib = dados['contribuinte']
    apur = dados['apuracao']
    rec = dados['receitas']
    estab = dados['estabelecimento']
    atividades = dados.get('atividades', [])
    das = dados['das']
    aliq = dados.get('aliquota_oficial')
    logo = _logo_uri()
    logo_html = f'<img src="{logo}" alt="Liddera">' if logo else ''

    anexo_txt = '/'.join(dados.get('anexos_identificados') or ['?'])
    faixa_txt = f"{aliq['faixa']}ª faixa" if aliq else '—'
    aliq_efetiva = aliq['aliquota_efetiva'] if aliq else 0.0

    delta_html = ''
    if historico:
        anterior = historico[-1]
        d = round(aliq_efetiva - anterior.get('aliquota_efetiva', aliq_efetiva), 2)
        sinal = '+' if d >= 0 else ''
        cor = '#ff9d9d' if d > 0 else '#a8ffcf'
        delta_html = f'<div style="font-size:12.5px;font-weight:700;color:{cor}">{sinal}{_brl(d)} p.p. vs mês anterior</div>'

    hist_interno = dados.get('receitas_anteriores', {}).get('interno', {})
    def _chave_mes(mp):
        mm, yy = mp.split('/')
        return (yy, mm)
    meses_ordenados = sorted(hist_interno.items(), key=lambda kv: _chave_mes(kv[0]))
    ultimos12 = meses_ordenados[-12:] if len(meses_ordenados) >= 2 else []
    maxf = max((v for _, v in ultimos12), default=1) or 1
    bars = ''
    bw, gap = 48, 14
    x = 0
    for i, (mes, val) in enumerate(ultimos12):
        h = val / maxf * 190
        mm, yy = mes.split('/')
        rotulo = f'{mm}/{yy[2:]}'
        bars += (f'<div style="position:absolute;left:{x}px;bottom:0;width:{bw}px;height:{h:.0f}px;'
                 f'background:linear-gradient(180deg,#3a7bd5,var(--navy));border-radius:6px 6px 0 0;'
                 f'animation:growup .7s {0.05*i:.2f}s cubic-bezier(.22,1,.36,1) backwards"></div>'
                 f'<div style="position:absolute;left:{x}px;bottom:-22px;width:{bw}px;text-align:center;font-size:9.5px;color:var(--ink2)">{rotulo}</div>'
                 f'<div style="position:absolute;left:{x}px;bottom:{h+6:.0f}px;width:{bw}px;text-align:center;font-size:8.5px;font-weight:700;color:var(--navy);white-space:nowrap">{_brl(val)}</div>')
        x += bw + gap
    total_w = max(x - gap, bw)

    tot = dados['totais_empresa']['exigivel']
    labels_tributo = [('IRPJ', 'irpj', '#1f2a5a'), ('CSLL', 'csll', '#0ea472'), ('COFINS', 'cofins', '#e8632b'),
                       ('PIS/Pasep', 'pis_pasep', '#9aa3c0'), ('CBS', 'cbs', '#c0392b'), ('INSS/CPP', 'inss_cpp', '#3a7bd5'),
                       ('ICMS', 'icms', '#d4711a'), ('IBS', 'ibs', '#16a085'), ('IPI', 'ipi', '#7c3aed'), ('ISS', 'iss', '#e0a92e')]
    segs_das = [(l, tot.get(k, 0.0), c) for l, k, c in labels_tributo if tot.get(k, 0.0) > 0.005]
    arcs_das = _donut(segs_das, cx=100, cy=100, r=76, sw=30) if segs_das else ''
    tot_das = sum(v for _, v, _ in segs_das) or 1
    rows_das_tbl = ''.join(
        f'<tr><td><span class="dot" style="background:{c};width:9px;height:9px;border-radius:3px;display:inline-block;margin-right:7px"></span>{l}</td>'
        f'<td>{v/tot_das*100:.2f}%</td><td style="text-align:right">R$ {_brl(v)}</td></tr>'
        for l, v, c in segs_das)
    leg_das = ''.join(f'<div class="lg"><span class="dot" style="background:{c}"></span>{l}<b>{v/tot_das*100:.1f}%</b></div>' for l, v, c in segs_das)

    limite = 4_800_000.0
    pct_limite = min(rec['rbt12']['total'] / limite * 100, 100) if limite else 0
    falta_limite = max(limite - rec['rbt12']['total'], 0)

    # Composição por atividade — só quando há mais de um bloco de atividade no
    # período (ex.: Comércio + Serviços misturados, ou mesmo Anexo com/sem
    # retenção de ISS). Cada atividade usa SEU PRÓPRIO Anexo e tributos.
    ativ_cards = ''
    if len(atividades) > 1:
        for i, a in enumerate(atividades):
            segs_a = [(l, a['tributos'].get(k, 0.0), c) for l, k, c in labels_tributo if a['tributos'].get(k, 0.0) > 0.005]
            tot_a = sum(v for _, v, _ in segs_a) or 1
            arcs_a = _donut(segs_a, cx=64, cy=64, r=48, sw=20) if segs_a else ''
            leg_a = ''.join(f'<div class="lg" style="font-size:11.5px;padding:3px 0"><span class="dot" style="background:{c}"></span>{l}<b>{v/tot_a*100:.1f}%</b></div>' for l, v, c in segs_a)
            aliq_a = a['aliquota_oficial']['aliquota_efetiva'] if a.get('aliquota_oficial') else None
            anexo_a = f"Anexo {a['anexo']}" if a['anexo'] else 'Anexo não identificado'
            ativ_cards += f'''<div class="card sec" style="animation-delay:{0.22 + i*0.05:.2f}s">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:14px;flex-wrap:wrap">
          <div><h3 style="margin:0"><span class="dot"></span>Atividade {i+1}</h3>
            <div style="font-size:12px;color:var(--ink2);margin-top:4px;max-width:520px">{_esc(a["descricao"])}</div></div>
          <div style="text-align:right">
            <span class="tagint" style="background:#eef1f7;color:var(--navy)">{_esc(anexo_a)}</span>
            <div style="font-size:11px;color:var(--ink2);margin-top:4px">Receita: R$ {_brl(a["receita_bruta_informada"])}{f" · Alíquota efetiva {_brl(aliq_a)}%" if aliq_a is not None else ""}</div>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:16px">
          <svg width="128" height="128" viewBox="0 0 128 128"><circle cx="64" cy="64" r="48" fill="none" stroke="#eef1f7" stroke-width="20"/>{arcs_a}</svg>
          <div style="flex:1">{leg_a}</div>
        </div>
      </div>'''

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Painel do Simples Nacional · {_esc(contrib['nome_empresarial'])}</title>
<style>{_CSS}
@keyframes growup{{from{{height:0}}}}
.sn-track{{background:#eef0f7;border-radius:999px;height:26px;overflow:hidden;margin-top:10px}}
.sn-fill{{background:linear-gradient(90deg,#0ea472,#3ddb9e);height:100%;border-radius:999px;width:0%}}
.sn-scale{{display:flex;justify-content:space-between;font-size:11px;color:var(--ink2);margin-top:6px}}
.sn-insight{{background:#fff7ed;border-left:4px solid var(--orange);padding:12px 16px;border-radius:8px;font-size:12.5px;color:#7a4a1f;margin-bottom:16px}}
.sn-chartbox{{position:relative;height:240px;margin:20px 10px 26px}}
</style></head><body><div class="wrap">
  <header class="sec">{logo_html}
    <div class="h-txt"><b>Liddera | Inteligência em Negócios</b><div>Painel do Simples Nacional</div></div>
  </header>
  <div class="band sec" style="animation-delay:.05s;justify-content:space-between">
    <div><h1>{_esc(contrib['nome_empresarial'])}</h1>
      <div class="meta">CNPJ {_esc(estab['cnpj'])} · Competência {_esc(apur['pa'])}</div>
      <span class="tagint" style="background:#e8632b;color:#fff;font-weight:800;border-color:transparent;margin-top:8px;display:inline-block">Anexo {_esc(anexo_txt)} · {faixa_txt}</span></div>
    <div style="text-align:right">
      <div style="font-size:38px;font-weight:800;line-height:1">{_brl(aliq_efetiva)}<span style="font-size:17px">%</span></div>
      {delta_html}
      <div style="font-size:10.5px;color:#c7cbe8;text-transform:uppercase;letter-spacing:.4px;margin-top:2px">Alíquota efetiva{' (atividade principal)' if len(atividades) > 1 else ''}</div>
    </div>
  </div>

  <div class="kpis sec" style="animation-delay:.1s;grid-template-columns:repeat(4,1fr)">
    <div class="kpi"><div class="l">Faturamento (RBT12)</div><div class="v">R$ {_brl(rec['rbt12']['total'])}</div></div>
    <div class="kpi"><div class="l">Faturamento do mês</div><div class="v">R$ {_brl(rec['rpa']['total'])}</div></div>
    <div class="kpi big"><div class="l">DAS do mês</div><div class="v">R$ {_brl(das['total'])}</div></div>
    <div class="kpi"><div class="l">Faixa de enquadramento</div><div class="v">{faixa_txt}</div></div>
  </div>

  {'' if len(ultimos12) < 2 else f'''<div class="card sec" style="animation-delay:.15s">
    <h3><span class="dot"></span>Evolução do faturamento — últimos {len(ultimos12)} meses</h3>
    <div class="sn-chartbox"><div style="position:relative;width:{total_w}px;height:100%;margin:0 auto">{bars}</div></div>
  </div>'''}

  <div class="card sec" style="animation-delay:.2s;display:grid;grid-template-columns:1fr 1.3fr;gap:20px">
    <div><h3><span class="dot"></span>Composição do DAS{' — total da empresa' if len(atividades) > 1 else ''}</h3>
      <div style="display:flex;align-items:center;gap:18px">
        <svg width="190" height="190" viewBox="0 0 200 200"><circle cx="100" cy="100" r="76" fill="none" stroke="#eef1f7" stroke-width="30"/>{arcs_das}</svg>
        <div>{leg_das}</div>
      </div>
    </div>
    <div><h3><span class="dot"></span>Detalhamento do DAS — R$ {_brl(tot_das)}</h3>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr><th style="text-align:left;color:var(--ink2);font-size:10.5px;text-transform:uppercase;border-bottom:2px solid var(--line);padding:6px">Imposto</th>
        <th style="text-align:left;color:var(--ink2);font-size:10.5px;text-transform:uppercase;border-bottom:2px solid var(--line);padding:6px">%</th>
        <th style="text-align:right;color:var(--ink2);font-size:10.5px;text-transform:uppercase;border-bottom:2px solid var(--line);padding:6px">Valor</th></tr></thead>
        <tbody style="color:var(--navy)">{rows_das_tbl}</tbody>
      </table>
    </div>
  </div>

  {ativ_cards}

  <div class="card sec" style="animation-delay:.3s">
    <h3><span class="dot"></span>Proximidade do limite do Simples Nacional</h3>
    <div style="font-size:13px;color:var(--ink2)">R$ {_brl(rec['rbt12']['total'])} de R$ {_brl(limite)} (teto anual)</div>
    <div class="sn-track"><div class="sn-fill" id="snFill"></div></div>
    <div class="sn-scale"><span>0</span><span>R$ 1,2M</span><span>R$ 2,4M</span><span>R$ 3,6M (sublimite)</span><span>R$ 4,8M</span></div>
    <div style="margin-top:14px;font-size:12px;color:var(--ink2)">Faltam R$ {_brl(falta_limite)} pra atingir o teto{' — ainda dentro da faixa segura.' if pct_limite < 75 else '.'}</div>
  </div>

  <footer style="text-align:center;color:var(--ink2);font-size:11px;margin-top:16px">Liddera | Inteligência em Negócios Ltda</footer>
</div>{_COUNT_JS}
<script>
requestAnimationFrame(function(){{
  var f = document.getElementById('snFill');
  if (f) {{ f.style.transition = 'width 1.2s cubic-bezier(.22,1,.36,1)'; f.style.width = '{pct_limite:.1f}%'; }}
}});
</script>
</body></html>"""


_CST_C191_PERMITIDO = {'00', '10', '20', '51', '70', '90'}
# Lista de CEST conhecidos como inválidos (fora da Tabela CEST oficial) — cresce
# conforme o Rafael for repassando mais casos encontrados na validação.
_CEST_INVALIDOS_CONHECIDOS = {'1705500', '0000000', '2007910'}
_MAPA_COD_NAT_POR_CFOP = {
    '1102': '100', '2102': '100',
    '1403': '103', '2403': '103',
    '1556': '7005', '2556': '7005', '1407': '7005', '2407': '7005',
    '1653': '121', '2653': '121',
}
# Mapeamento alternativo — só usado quando a empresa JÁ TEM esse código de
# Natureza cadastrado no 0400 dela (o que o Rafael chama de "Acumuladores").
# Se não tiver cadastrado, cai pro mapeamento padrão acima (mesmo CFOP, quando
# existir ali). 1101/2101 é novo, não tinha entrada no mapeamento padrão.
_MAPA_COD_NAT_ACUMULADOR = {
    '1102': '6000', '2102': '6000',
    '1403': '6001', '2403': '6001',
    '1101': '6002', '2101': '6002',
}
_COD_NAT_NOVOS = {'7005': 'MATERIAL DE USO E CONSUMO'}


# Cada bloco do SPED EFD ICMS/IPI tem abertura (X001) e fechamento (X990) — o
# fechamento carrega SEU PRÓPRIO contador de linhas (QTD_LIN_X), contando do
# X001 até o X990 INCLUSIVE. É inteiramente separado do Bloco 9 (9900/9999, que
# conta o ARQUIVO TODO). O Bloco 9 tem essa mesma lógica pro PRÓPRIO fechamento
# (9990, contando do 9001 ao 9990) — por isso está na lista também.
_BLOCOS_FECHAMENTO = [
    ('0000', '0990', None),  # Bloco 0 conta a partir do 0000 (abertura do ARQUIVO, que também
                              # é onde o bloco 0 começa de fato) — não do 0001, que é só o
                              # indicador de movimento do bloco. Achado real, confirmado contra
                              # o relatório de erro (esperado 1176, eu calculava 1175 usando 0001).
    ('B001', 'B990', None), ('C001', 'C990', None), ('D001', 'D990', None),
    ('E001', 'E990', None), ('G001', 'G990', None), ('H001', 'H990', None), ('K001', 'K990', None),
    ('1001', '1990', None),
    ('9001', '9990', '9999'),  # CASO ESPECIAL: o 9990 conta até o 9999 (fechamento do
                                # ARQUIVO todo) inclusive, não até ele mesmo como todo
                                # resto — achado real, confirmado contra 2 arquivos ORIGINAIS
                                # diferentes (os dois batiam exato contando até o 9999, e
                                # ficavam sistematicamente 1 a menos contando só até o 9990).
]

def _recalcula_fechamentos_bloco(linhas):
    """Recalcula o campo de contagem (2º campo) de cada registro de fechamento
    de bloco (C990, E990, 9990 etc.), contando de verdade quantas linhas existem
    entre a abertura do bloco e o limite de contagem daquele bloco (normalmente
    o próprio fechamento, mas o Bloco 9 é exceção — ver acima) — necessário
    depois de qualquer remoção/inserção de linha DENTRO de um bloco (não é
    coberto pelo recálculo do Bloco 9 global, que só conta o total do arquivo)."""
    idx_por_reg = {}
    for i, l in enumerate(linhas):
        campos = l.split('|')
        if len(campos) > 1 and campos[1]:
            idx_por_reg.setdefault(campos[1], []).append(i)
    saida = list(linhas)
    for reg_abre, reg_fecha, reg_conta_ate in _BLOCOS_FECHAMENTO:
        idx_abre = idx_por_reg.get(reg_abre)
        idx_fecha = idx_por_reg.get(reg_fecha)
        idx_limite = idx_por_reg.get(reg_conta_ate or reg_fecha)
        if not idx_abre or not idx_fecha or not idx_limite:
            continue
        i_abre, i_fecha, i_limite = idx_abre[0], idx_fecha[0], idx_limite[0]
        if i_limite < i_abre:
            continue
        qtd = i_limite - i_abre + 1
        campos_fecha = saida[i_fecha].split('|')
        if len(campos_fecha) > 2:
            campos_fecha[2] = str(qtd)
            saida[i_fecha] = '|'.join(campos_fecha)
    return saida


def _recalcula_bloco9_global(linhas):
    """Reconstrói o Bloco 9 inteiro (9900 por tipo de registro + 9990 fechamento
    do próprio bloco + 9999 total do arquivo) — extraído de `corrigir_sped_fiscal`
    pra reaproveitar também na inserção de notas faltantes (mesma necessidade:
    qualquer inserção/remoção de linha exige recontar tudo isso do zero)."""
    linhas_sem_bloco9 = [l for l in linhas if not (l.startswith('|9900|') or l.startswith('|9999|') or l.startswith('|9990|'))]
    contagem = {}
    ordem = []
    for l in linhas_sem_bloco9:
        campos = l.split('|')
        if len(campos) > 1 and campos[1]:
            reg = campos[1]
            if reg not in contagem:
                ordem.append(reg)
            contagem[reg] = contagem.get(reg, 0) + 1

    linhas_9900 = [f'|9900|{r}|{contagem[r]}|' for r in ordem]
    linhas_9900.append('|9900|9999|1|')
    linhas_9900.append('|9900|9990|1|')
    qtd_9900_total = len(linhas_9900) + 1
    linhas_9900.append(f'|9900|9900|{qtd_9900_total}|')

    total_linhas_final = len(linhas_sem_bloco9) + len(linhas_9900) + 2
    linha_9999 = f'|9999|{total_linhas_final}|'
    return linhas_sem_bloco9 + linhas_9900 + ['|9990|0|'] + [linha_9999]


def corrigir_sped_fiscal(texto, cest_invalidos=None):
    """Corrige erros de validação comuns do SPED Fiscal (EFD ICMS/IPI) — MÓDULO
    RESTRITO AO ADMIN, altera o arquivo que será reenviado ao governo:
    1) Remove C191 cujo C190 pai tem CST fora de {00,10,20,51,70,90} (regra
       oficial: o campo VL_FCP_OP só pode ser preenchido nesses casos);
    2) Remove o bloco E500/E510.../E520 quando a empresa não é contribuinte de IPI;
    3) Limpa COD_BARRA (campo 4) do 0200 quando for literalmente "SEM GTIN";
    4) Limpa CEST (campo 13) do 0200 quando estiver na lista de CEST inválidos
       informada (lista que cresce conforme repassado pelo usuário — não há
       como validar contra a Tabela CEST oficial completa sem ela);
    5) Corrige COD_NAT (campo 12) do C170 quando for "0", baseado no CFOP
       (campo 11) — mapa por enquanto: 1102/2102→100, 1403/2403→103,
       1556/2556→106, 1653/2653→121. Cria o registro 0400 correspondente
       (só os que faltarem) se ainda não existir no arquivo.
    Recalcula o Bloco 9 (9900 por tipo de registro + 9999 total de linhas) no
    final — testado e validado linha a linha contra um SPED real: todas as
    contagens batem exatamente, e nenhuma linha fora do escopo é alterada.
    Devolve (texto_corrigido, resumo)."""
    cest_invalidos = _CEST_INVALIDOS_CONHECIDOS | set(cest_invalidos or [])
    quebra = '\r\n' if '\r\n' in texto else '\n'
    linhas = texto.split(quebra)
    tinha_linha_final_vazia = bool(linhas) and linhas[-1] == ''
    if tinha_linha_final_vazia:
        linhas = linhas[:-1]

    resumo = {
        'c191_removidos': 0, 'e500_linhas_removidas': 0,
        'gtin_limpos': 0, 'cest_limpos': 0, 'cod_nat_corrigidos': 0,
        'registro_0400_criado': [],
    }

    # 1) índices de C191 inválidos (olhando o CST do C190 logo anterior)
    indices_remover = set()
    ultimo_cst_c190 = None
    for i, l in enumerate(linhas):
        campos = l.split('|')
        if len(campos) < 2:
            continue
        reg = campos[1]
        if reg == 'C190':
            ultimo_cst_c190 = campos[2] if len(campos) > 2 else ''
        elif reg == 'C191':
            cst2 = (ultimo_cst_c190 or '')[-2:]
            if cst2 not in _CST_C191_PERMITIDO:
                indices_remover.add(i)
                resumo['c191_removidos'] += 1

    # 2) bloco E500...E520 inteiro
    i = 0
    while i < len(linhas):
        campos = linhas[i].split('|')
        if len(campos) > 1 and campos[1] == 'E500':
            j = i
            while j < len(linhas):
                c2 = linhas[j].split('|')
                if j not in indices_remover:
                    resumo['e500_linhas_removidas'] += 1
                indices_remover.add(j)
                if len(c2) > 1 and c2[1] == 'E520':
                    break
                j += 1
            i = j + 1
        else:
            i += 1

    # 3+4+5) edita campos em 0200 e C170, remove linhas marcadas
    codigos_0400_existentes = {
        l.split('|')[2] for l in linhas
        if l.startswith('|0400|') and len(l.split('|')) > 2
    }
    codigos_novos_usados = set()
    novas_linhas = []
    for i, l in enumerate(linhas):
        if i in indices_remover:
            continue
        campos = l.split('|')
        if len(campos) < 2:
            novas_linhas.append(l)
            continue
        reg = campos[1]
        alterado = False
        if reg == '0200' and len(campos) > 13:
            if campos[4] == 'SEM GTIN':
                campos[4] = ''
                resumo['gtin_limpos'] += 1
                alterado = True
            if campos[13] in cest_invalidos:
                campos[13] = ''
                resumo['cest_limpos'] += 1
                alterado = True
        elif reg == 'C170' and len(campos) > 12:
            if campos[12] == '0':
                cfop = campos[11] if len(campos) > 11 else ''
                cod_acumulador = _MAPA_COD_NAT_ACUMULADOR.get(cfop)
                if cod_acumulador and cod_acumulador in codigos_0400_existentes:
                    novo_cod = cod_acumulador
                else:
                    novo_cod = _MAPA_COD_NAT_POR_CFOP.get(cfop)
                if novo_cod:
                    campos[12] = novo_cod
                    codigos_novos_usados.add(novo_cod)
                    resumo['cod_nat_corrigidos'] += 1
                    alterado = True
        if alterado:
            l = '|'.join(campos)
        novas_linhas.append(l)
    linhas = novas_linhas

    # cria no 0400 só os códigos que FORAM DE FATO usados na correção e ainda não existiam
    codigos_a_criar = sorted(codigos_novos_usados - codigos_0400_existentes)
    if codigos_a_criar:
        pos_insercao = None
        for i, l in enumerate(linhas):
            campos = l.split('|')
            if len(campos) > 1 and campos[1] == '0400':
                pos_insercao = i + 1
        if pos_insercao is None:
            for i, l in enumerate(linhas):
                campos = l.split('|')
                if len(campos) > 1 and campos[1] == '0000':
                    pos_insercao = i + 1
                    break
        if pos_insercao is not None:
            for cod in codigos_a_criar:
                desc = _COD_NAT_NOVOS.get(cod, f'NATUREZA {cod}')
                linhas.insert(pos_insercao, f'|0400|{cod}|{desc}|')
                pos_insercao += 1
                resumo['registro_0400_criado'].append(cod)

    # recalcula bloco 9 (9900 por tipo + 9999 total de linhas do arquivo) —
    # ver `_recalcula_bloco9_global` (extraída daqui, reaproveitada também na
    # inserção de notas faltantes). Achado real preservado nela: 9990 fica
    # ANTES das linhas 9900 se não reposicionar — quebra a ordem que o
    # validador exige.
    linhas_finais = _recalcula_bloco9_global(linhas)

    # Cada bloco (C, E, e qualquer outro) tem seu PRÓPRIO contador de linhas no
    # registro de fechamento (ex.: C990 tem QTD_LIN_C, contando do C001 ao C990
    # inclusive) — é SEPARADO do Bloco 9 acima. Removi/inseri linha dentro de
    # blocos (C191 do bloco C, E500/E510/E520 do bloco E, e possivelmente um 0400
    # novo no bloco 0) sem atualizar esse contador próprio — achado real, confirmado
    # contra o relatório de erro do usuário (bateu exato: C990 errado em +1204,
    # E990 errado em +13 — exatamente a quantidade removida de cada bloco).
    linhas_finais = _recalcula_fechamentos_bloco(linhas_finais)

    if tinha_linha_final_vazia:
        linhas_finais.append('')
    texto_corrigido = quebra.join(linhas_finais)
    resumo['total_linhas_final'] = len(linhas_finais)
    return texto_corrigido, resumo


def gerar_visualizacao_sped_html(texto, nome_empresa='', periodo=''):
    """Visualização completa de TODOS os registros de um SPED Fiscal — agrupados
    por tipo (aba com contagem), tabela paginada (renderiza só a página atual via
    JS — testado contra um SPED real com 20 mil linhas num único tipo; renderizar
    tudo de uma vez travava o navegador por 8+ segundos) e com busca por texto.
    Usado no módulo de Correção do SPED (Admin), pra conferir o arquivo inteiro
    antes e depois de corrigir."""
    quebra = '\r\n' if '\r\n' in texto else '\n'
    linhas = [l for l in texto.split(quebra) if l.strip()]

    por_tipo = {}
    ordem_tipos = []
    for l in linhas:
        campos = l.split('|')
        if len(campos) < 2:
            continue
        tipo = campos[1]
        corpo = campos[2:-1] if campos and campos[-1] == '' else campos[2:]
        if tipo not in por_tipo:
            por_tipo[tipo] = []
            ordem_tipos.append(tipo)
        por_tipo[tipo].append(corpo)

    logo = _logo_uri()
    logo_html = f'<img src="{logo}" alt="Liddera">' if logo else ''

    botoes = ''.join(
        f'<button class="sptab{" on" if i == 0 else ""}" data-tipo="{_esc(t)}" onclick="mostrarTipo(\'{_esc(t)}\')">{_esc(t)} <span class="cnt">{len(por_tipo[t])}</span></button>'
        for i, t in enumerate(ordem_tipos)
    )

    # dados como JSON (bem mais compacto que <tr><td> repetido) — a tabela é
    # montada e paginada via JS, só a pagina atual vira DOM de verdade.
    dados_json = json.dumps(por_tipo, ensure_ascii=False)
    primeiro_tipo = ordem_tipos[0] if ordem_tipos else ''

    total_registros = len(linhas)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Todos os dados do SPED · {_esc(nome_empresa)}</title>
<style>{_CSS}
.sptabs{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}}
.sptab{{background:#eef1f7;border:none;border-radius:8px;padding:7px 12px;font-size:12px;font-weight:700;color:var(--navy);cursor:pointer}}
.sptab.on{{background:var(--navy);color:#fff}}
.sptab .cnt{{opacity:.7;font-weight:600;margin-left:3px}}
.spsearch{{width:100%;border:1px solid var(--line);border-radius:10px;padding:11px 14px;font-size:13.5px;margin-bottom:14px}}
.sptable-wrap{{overflow:auto;border:1px solid var(--line);border-radius:10px}}
table.sptable{{width:100%;border-collapse:collapse;font-size:11.5px;white-space:nowrap}}
table.sptable th{{position:sticky;top:0;background:#f7f8fc;text-align:left;padding:7px 10px;color:var(--ink2);font-size:10px;text-transform:uppercase;border-bottom:2px solid var(--line)}}
table.sptable td{{padding:6px 10px;border-top:1px solid #f3f4f9;color:var(--navy)}}
.sppag{{display:flex;align-items:center;gap:10px;justify-content:center;padding:12px;font-size:12.5px;color:var(--ink2)}}
.sppag button{{background:#eef1f7;border:none;border-radius:7px;padding:6px 12px;font-size:12px;font-weight:700;color:var(--navy);cursor:pointer}}
.sppag button:disabled{{opacity:.35;cursor:default}}
</style></head><body><div class="wrap">
  <header class="sec">{logo_html}
    <div class="h-txt"><b>FiscoCont+ · Módulo Admin</b><div>Todos os dados do SPED Fiscal</div></div>
    <span class="tagint" style="background:#e23d4c;color:#fff;border-color:transparent">acesso restrito</span></header>
  <div class="band sec" style="animation-delay:.05s"><div>
    <h1>{_esc(nome_empresa)}</h1>
    <div class="meta">Competência {_esc(periodo)} · {total_registros:,} registro(s) no total</div>
  </div></div>
  <input class="spsearch" id="spBusca" type="text" placeholder="Buscar dentro da tabela do tipo atual…" oninput="buscar()">
  <div class="sptabs">{botoes}</div>
  <div class="sptable-wrap"><table class="sptable"><thead><tr id="spHead"></tr></thead><tbody id="spBody"></tbody></table></div>
  <div class="sppag">
    <button id="spPrev" onclick="mudarPagina(-1)">‹ Anterior</button>
    <span id="spInfo"></span>
    <button id="spNext" onclick="mudarPagina(1)">Próxima ›</button>
  </div>
</div>
<script>
var DADOS = {dados_json};
var TIPO_ATUAL = '{primeiro_tipo}';
var FILTRADOS = DADOS[TIPO_ATUAL] || [];
var PAGINA = 0;
var POR_PAGINA = 100;

function mostrarTipo(tipo) {{
  TIPO_ATUAL = tipo;
  PAGINA = 0;
  document.querySelectorAll('.sptab').forEach(function(b) {{ b.classList.toggle('on', b.dataset.tipo === tipo); }});
  document.getElementById('spBusca').value = '';
  buscar();
}}
function buscar() {{
  var termo = document.getElementById('spBusca').value.toLowerCase();
  var base = DADOS[TIPO_ATUAL] || [];
  FILTRADOS = termo ? base.filter(function(linha) {{ return linha.join('|').toLowerCase().indexOf(termo) !== -1; }}) : base;
  PAGINA = 0;
  render();
}}
function mudarPagina(delta) {{
  PAGINA = Math.max(0, Math.min(PAGINA + delta, Math.ceil(FILTRADOS.length / POR_PAGINA) - 1));
  render();
}}
function render() {{
  var nCampos = 0;
  FILTRADOS.forEach(function(l) {{ if (l.length > nCampos) nCampos = l.length; }});
  var head = document.getElementById('spHead');
  head.innerHTML = '';
  for (var i = 0; i < nCampos; i++) {{
    var th = document.createElement('th'); th.textContent = 'Campo ' + (i + 1); head.appendChild(th);
  }}
  var inicio = PAGINA * POR_PAGINA;
  var pagina = FILTRADOS.slice(inicio, inicio + POR_PAGINA);
  var body = document.getElementById('spBody');
  body.innerHTML = '';
  pagina.forEach(function(linha) {{
    var tr = document.createElement('tr');
    for (var i = 0; i < nCampos; i++) {{
      var td = document.createElement('td'); td.textContent = linha[i] || ''; tr.appendChild(td);
    }}
    body.appendChild(tr);
  }});
  var totalPaginas = Math.max(1, Math.ceil(FILTRADOS.length / POR_PAGINA));
  document.getElementById('spInfo').textContent = 'Página ' + (PAGINA + 1) + ' de ' + totalPaginas + ' · ' + FILTRADOS.length + ' registro(s)';
  document.getElementById('spPrev').disabled = PAGINA === 0;
  document.getElementById('spNext').disabled = PAGINA >= totalPaginas - 1;
}}
render();
</script>
</body></html>"""


def ler_certificado_pfx(caminho, senha):
    """Lê um certificado A1 (.pfx) e devolve CNPJ, razão social e validade."""
    from cryptography.hazmat.primitives.serialization import pkcs12
    import re as _re

    with open(caminho, 'rb') as f:
        pfx_bytes = f.read()
    chave_privada, certificado, cadeia = pkcs12.load_key_and_certificates(pfx_bytes, senha.encode('utf-8'))
    if chave_privada is None or certificado is None:
        raise ValueError('Certificado sem chave privada ou sem certificado válido — senha errada ou arquivo corrompido.')

    titular = certificado.subject.rfc4514_string()
    m = _re.search(r':(\d{14})', titular)
    cnpj = m.group(1) if m else ''
    m2 = _re.search(r'CN=([^:,]+)', titular)
    razao_social = m2.group(1).strip() if m2 else titular
    return {
        'cnpj': cnpj, 'razao_social': razao_social,
        'validade': certificado.not_valid_after_utc.strftime('%Y-%m-%d'),
        'titular_completo': titular,
    }


def testar_senhas_certificados(itens):
    """Pra cada certificado, tenta as senhas candidatas (tiradas do nome do
    arquivo etc.) até uma abrir o .pfx. Devolve só o ÍNDICE da candidata que
    funcionou (não a senha), pra ela não ir parar num arquivo de saída."""
    resultados = []
    for it in itens:
        caminho = it.get('caminho', '')
        r = {'caminho': caminho, 'ok': False}
        if not os.path.isfile(caminho):
            r['detalhe'] = 'arquivo não encontrado'
            resultados.append(r)
            continue
        ultimo = ''
        for i, senha in enumerate(it.get('candidatas') or []):
            try:
                info = ler_certificado_pfx(caminho, senha)
            except Exception as e:
                ultimo = str(e)
                continue
            r.update({'ok': True, 'indice_senha': i, 'info': info})
            break
        if not r['ok'] and ultimo:
            r['detalhe'] = ultimo[:160]
        resultados.append(r)
    return resultados


def _extrair_cert_chave_temp(caminho_pfx, senha):
    """Extrai certificado + chave privada do .pfx pra arquivos PEM temporários."""
    from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption

    with open(caminho_pfx, 'rb') as f:
        pfx_bytes = f.read()
    chave_privada, certificado, cadeia = pkcs12.load_key_and_certificates(pfx_bytes, senha.encode('utf-8'))
    if chave_privada is None or certificado is None:
        raise ValueError('Certificado sem chave privada ou sem certificado válido — senha errada ou arquivo corrompido.')

    tmp_dir = tempfile.mkdtemp(prefix='fc_cert_')
    cert_path = os.path.join(tmp_dir, 'cert.pem')
    key_path = os.path.join(tmp_dir, 'key.pem')
    with open(cert_path, 'wb') as f:
        f.write(certificado.public_bytes(Encoding.PEM))
        for c in (cadeia or []):
            f.write(c.public_bytes(Encoding.PEM))
    with open(key_path, 'wb') as f:
        f.write(chave_privada.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    return cert_path, key_path, tmp_dir


def parse_nfse_xml(path):
    """Extrai os campos da NFS-e nacional (layout SPED/SEFIN Nacional)."""
    t = _read_text(path)
    bloco_emit = re.search(r'<emit>(.*?)</emit>', t, re.S)
    bloco_emit = bloco_emit.group(1) if bloco_emit else ''
    bloco_prest = re.search(r'<prest>(.*?)</prest>', t, re.S)
    bloco_prest = bloco_prest.group(1) if bloco_prest else ''
    bloco_toma = re.search(r'<toma>(.*?)</toma>', t, re.S)
    bloco_toma = bloco_toma.group(1) if bloco_toma else ''
    bloco_trib = re.search(r'<trib>(.*?)</trib>', t, re.S)
    bloco_trib = bloco_trib.group(1) if bloco_trib else ''

    chave_m = re.search(r'Id="NFS(\d{50})"', t)
    chave = chave_m.group(1) if chave_m else ''
    nnfse = _campo(t, 'nNFSe')
    dcompet = _campo(t, 'dCompet') or (_campo(t, 'dhProc')[:10] if _campo(t, 'dhProc') else '')

    prest_cnpj = _campo(bloco_emit, 'CNPJ') or _campo(bloco_prest, 'CNPJ')
    prest_cpf = _campo(bloco_emit, 'CPF') or _campo(bloco_prest, 'CPF')
    toma_cnpj = _campo(bloco_toma, 'CNPJ')
    toma_cpf = _campo(bloco_toma, 'CPF')
    toma_nome = _campo(bloco_toma, 'xNome')

    tp_ret_issqn = _campo(bloco_trib, 'tpRetISSQN')
    tp_ret_pis = _campo(bloco_trib, 'tpRetPisCofins')
    retido = (tp_ret_issqn == '2') or (tp_ret_pis not in ('', '0'))

    vserv_m = re.search(r'<vServ>([\d.]+)</vServ>', t)
    vserv = _numx(vserv_m.group(1)) if vserv_m else 0.0
    vliq_m = re.search(r'<valores><vBC>[\d.]+</vBC>.*?<vLiq>([\d.]+)</vLiq>', t, re.S)
    vliq = _numx(vliq_m.group(1)) if vliq_m else vserv
    vissqn_m = re.search(r'<vISSQN>([\d.]+)</vISSQN>', t)
    vissqn = _numx(vissqn_m.group(1)) if vissqn_m else 0.0

    v_ret_pis_cofins_csll = _numx(_campo(bloco_trib, 'vRetCSLL'))
    v_ret_irrf = _numx(_campo(bloco_trib, 'vRetIRRF'))
    v_ret_cp = _numx(_campo(bloco_trib, 'vRetCP'))
    v_iss_retido = vissqn if tp_ret_issqn == '2' else 0.0
    retencoes_detalhe = []
    if v_iss_retido:
        retencoes_detalhe.append({'tributo': 'ISS', 'valor': v_iss_retido})
    if v_ret_pis_cofins_csll:
        retencoes_detalhe.append({'tributo': 'PIS/COFINS/CSLL', 'valor': v_ret_pis_cofins_csll})
    if v_ret_irrf:
        retencoes_detalhe.append({'tributo': 'IRRF', 'valor': v_ret_irrf})
    if v_ret_cp:
        retencoes_detalhe.append({'tributo': 'INSS (Contrib. Previdenciária)', 'valor': v_ret_cp})
    total_retido = round(sum(r['valor'] for r in retencoes_detalhe), 2)

    return {
        'chave': chave, 'nnfse': nnfse, 'competencia': dcompet,
        'prestador_cnpj': prest_cnpj or prest_cpf, 'prestador_doc_tipo': 'CNPJ' if prest_cnpj else ('CPF' if prest_cpf else ''),
        'prestador_nome': _campo(bloco_emit, 'xNome') or '(não identificado)',
        'tomador_cnpj': toma_cnpj or toma_cpf, 'tomador_doc_tipo': 'CNPJ' if toma_cnpj else ('CPF' if toma_cpf else ''),
        'tomador_nome': toma_nome or ('(pessoa física sem nome informado)' if toma_cpf else '(destinatário não identificado)'),
        'descricao': _campo(t, 'xDescServ') or _campo(t, 'xTribNac'),
        'vserv': vserv, 'vliq': vliq, 'vissqn': vissqn,
        'retido': retido, 'tp_ret_issqn': tp_ret_issqn, 'tp_ret_pis': tp_ret_pis,
        'retencoes_detalhe': retencoes_detalhe, 'total_retido': total_retido,
    }


def baixar_nfse_adn(cert_path, senha, data_inicial, data_final, pasta_base, nome_empresa, cnpj_empresa,
                     nsu_inicial=0, homologacao=False, progresso=None):
    """Baixa NFS-e (emitidas e recebidas) via ADN, filtrando pelo período
    pedido. Salva em pasta_base/nome_empresa/NFS-e/Prestados|Tomados/AAAA-MM/chave.xml"""
    import gzip
    import re as _re
    import time as _time
    from datetime import datetime as _dt

    dt_ini = _dt.strptime(data_inicial, '%Y-%m-%d').date()
    dt_fim = _dt.strptime(data_final, '%Y-%m-%d').date()

    import requests

    def _get_com_retry(url, cert_tupla, tentativas=4):
        ultimo_erro = None
        for tentativa in range(1, tentativas + 1):
            try:
                return requests.get(
                    url, cert=cert_tupla,
                    headers={'Accept': 'application/json', 'Connection': 'close'},
                    timeout=45,
                )
            except requests.exceptions.RequestException as e:
                ultimo_erro = e
                if tentativa < tentativas:
                    _time.sleep(2 * tentativa)
        raise ultimo_erro

    cert_path_pem, key_path_pem, tmp_dir = _extrair_cert_chave_temp(cert_path, senha)
    base_url = 'https://adn.producaorestrita.nfse.gov.br' if homologacao else 'https://adn.nfse.gov.br'
    salvos, ignorados_fora_periodo, paginas = 0, 0, 0
    canceladas_qtd = 0
    nsu = int(nsu_inicial or 0)
    ultimo_nsu_visto = nsu
    erro = None

    # Duas passagens: primeiro junta tudo (notas + eventos) na memória, só
    # grava em disco no final — necessário porque o evento de cancelamento
    # pode chegar ANTES ou DEPOIS da nota original na sequência do NSU, não
    # dá pra decidir "salvar ou não" durante a própria varredura.
    notas_brutas = []       # (chave, xml_texto, item)
    chaves_canceladas = set()

    # Códigos numéricos de cancelamento vistos em fontes diferentes (a
    # documentação pública não é 100% consistente entre si sobre qual é o
    # "oficial") — checa todos, não só um, pra não depender de acertar
    # logo de cara qual a Receita realmente usa.
    _CODIGOS_EVENTO_CANCELAMENTO = ('e110001', 'e101101', 'e105101', 'e105102')

    def _talvez_chave_cancelada(item, xml_texto):
        """Acha a chave de uma nota referenciada por um evento de
        cancelamento — sem confiar num único campo (achado real: a doc
        pública não é 100% consistente sobre o nome exato desses campos
        pra NFS-e Nacional), checa várias pistas ao mesmo tempo: tanto o
        texto ("Cancelamento") quanto os códigos numéricos conhecidos —
        caso o XML do evento só traga o código, sem o texto por extenso
        (que pode ser só uma tradução feita pelo próprio portal na tela,
        não algo realmente presente no XML)."""
        tipo_evento = (item.get('TipoEvento') or '').lower()
        texto_evento = tipo_evento + ' ' + xml_texto[:2000]
        parece_cancelamento = (
            bool(_re.search(r'cancel', texto_evento, _re.I))
            or any(cod in texto_evento.lower() for cod in _CODIGOS_EVENTO_CANCELAMENTO)
        )
        if not parece_cancelamento:
            return None
        m = (_re.search(r'chNFSe["\s:>]+(\d{50})', xml_texto)
             or _re.search(r'chave["\s:>]+(\d{50})', xml_texto, _re.I)
             or _re.search(r'>(\d{50})<', xml_texto))
        return m.group(1) if m else None

    try:
        while True:
            try:
                resp = _get_com_retry(f'{base_url}/contribuintes/DFe/{nsu}', (cert_path_pem, key_path_pem))
            except requests.exceptions.SSLError as e:
                erro = ('Falha de conexão segura (TLS) com a Receita, mesmo tentando de novo várias vezes. '
                        'Costuma ser antivírus com "inspeção de HTTPS" ativada, VPN, ou instabilidade na rede — '
                        'tente desativar temporariamente a inspeção de HTTPS do antivírus pra esse programa, ou '
                        f'testar em outra rede. Detalhe técnico: {e}')
                break
            except requests.exceptions.RequestException as e:
                erro = f'Não consegui conectar com a Receita, mesmo tentando de novo: {e}'
                break
            try:
                dados = resp.json()
            except ValueError:
                dados = None
            sem_documentos = dados and any(
                e.get('Codigo') == 'E2220' for e in (dados.get('Erros') or [])
            )
            if sem_documentos:
                break
            if resp.status_code != 200:
                erro = f'A Receita respondeu {resp.status_code}: {resp.text[:300]}'
                break
            if dados is None:
                erro = 'A Receita respondeu algo que não consegui interpretar (não é JSON válido).'
                break
            if dados.get('Erros'):
                erro = f'A Receita retornou erro: {dados["Erros"]}'
                break

            lote = dados.get('LoteDFe') or []
            paginas += 1
            if progresso:
                try:
                    progresso(paginas, salvos)
                except Exception:
                    pass
            if not lote:
                break

            for item in lote:
                nsu_item = int(item.get('NSU', nsu))
                ultimo_nsu_visto = max(ultimo_nsu_visto, nsu_item)

                xml_b64 = item.get('ArquivoXml')
                if not xml_b64:
                    continue
                try:
                    xml_bytes = gzip.decompress(base64.b64decode(xml_b64))
                    xml_texto = xml_bytes.decode('utf-8')
                except Exception:
                    continue

                if (item.get('TipoDocumento') or '').upper() != 'NFSE':
                    # não é a nota em si — pode ser evento (cancelamento,
                    # manifestação etc.). Só nos interessa se for cancelamento.
                    # Guarda o bruto de QUALQUER evento não reconhecido como
                    # nota — mesmo quando minha detecção não identifica como
                    # cancelamento — pra eu poder conferir o formato real
                    # depois, sem precisar adivinhar de novo se um caso
                    # passar despercebido.
                    try:
                        pasta_diag = os.path.join(pasta_base, nome_empresa, 'NFS-e', '_eventos_brutos')
                        os.makedirs(pasta_diag, exist_ok=True)
                        with open(os.path.join(pasta_diag, f'evento_nsu_{nsu_item}.json'), 'w', encoding='utf-8') as f:
                            json.dump({'item_meta': {k: v for k, v in item.items() if k != 'ArquivoXml'},
                                       'xml_decodificado': xml_texto}, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                    chave_cancelada = _talvez_chave_cancelada(item, xml_texto)
                    if chave_cancelada:
                        chaves_canceladas.add(chave_cancelada)
                    continue

                dhger = item.get('DataHoraGeracao', '')
                data_doc = None
                if dhger:
                    try:
                        data_doc = _dt.strptime(dhger[:10], '%Y-%m-%d').date()
                    except ValueError:
                        pass
                if data_doc and not (dt_ini <= data_doc <= dt_fim):
                    ignorados_fora_periodo += 1
                    continue

                chave = item.get('ChaveAcesso') or f'nsu_{nsu_item}'
                competencia = data_doc.strftime('%Y-%m') if data_doc else 'sem-data'
                prest_cnpj_m = _re.search(r'<prest><CNPJ>(\d+)</CNPJ>', xml_texto)
                subpasta = 'Prestados' if (prest_cnpj_m and prest_cnpj_m.group(1) == cnpj_empresa) else 'Tomados'
                notas_brutas.append((chave, xml_texto, subpasta, competencia))

            nsu = ultimo_nsu_visto
    finally:
        for p in (cert_path_pem, key_path_pem):
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass

    # segunda passagem: só agora sabemos quais chaves foram canceladas
    # (o evento podia ter chegado antes OU depois da nota na sequência do
    # NSU) — grava com sufixo .CANCELADA no nome quando for o caso, pra
    # ficar visível no Explorer e a análise saber excluir dos totais.
    for chave, xml_texto, subpasta, competencia in notas_brutas:
        pasta_destino = os.path.join(pasta_base, nome_empresa, 'NFS-e', subpasta, competencia)
        os.makedirs(pasta_destino, exist_ok=True)
        if chave in chaves_canceladas:
            nome_arquivo = f'{chave}.CANCELADA.xml'
            canceladas_qtd += 1
        else:
            nome_arquivo = f'{chave}.xml'
        caminho_arquivo = os.path.join(pasta_destino, nome_arquivo)
        with open(caminho_arquivo, 'w', encoding='utf-8') as f:
            f.write(xml_texto)
        salvos += 1

    return {
        'erro': erro, 'salvos': salvos, 'ignorados_fora_periodo': ignorados_fora_periodo,
        'canceladas': canceladas_qtd,
        'paginas_lidas': paginas, 'ultimo_nsu': ultimo_nsu_visto,
        'pasta': os.path.join(pasta_base, nome_empresa, 'NFS-e'),
    }


def analisar_nfse(caminhos, cnpj_empresa, data_inicial=None, data_final=None):
    """Lê os XML de NFS-e já baixados e monta a análise agregada. Notas
    canceladas (sufixo .CANCELADA.xml no nome, posto na hora do download)
    aparecem juntas na lista, com um selo de status — mas ficam de fora dos
    totais em R$ (KPIs, valor total, top parceiros), com um total próprio
    separado, igual ao pedido do Rafael depois de ver como o Portal
    Nacional mostra (✓ Autorizada / ✗ Cancelada, na mesma listagem).

    Achado real (Rafael, 26/09): a pasta acumula downloads de vários
    períodos ao longo do tempo (é uma boa coisa, forma um arquivo
    histórico) — mas o painel não pode misturar tudo junto quando o
    pedido foi só de um mês específico. `data_inicial`/`data_final`,
    quando passados, filtram pela competência da própria nota (não pela
    pasta onde ela está salva) antes de somar qualquer coisa."""
    from datetime import datetime as _dt
    dt_ini = _dt.strptime(data_inicial, '%Y-%m-%d').date() if data_inicial else None
    dt_fim = _dt.strptime(data_final, '%Y-%m-%d').date() if data_final else None

    notas = []
    for p in caminhos:
        cancelada = p.upper().endswith('.CANCELADA.XML')
        try:
            d = parse_nfse_xml(p)
        except Exception:
            continue
        if not d['nnfse']:
            continue
        if dt_ini or dt_fim:
            try:
                data_nota = _dt.strptime(d['competencia'][:10], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                data_nota = None
            if data_nota:
                if dt_ini and data_nota < dt_ini:
                    continue
                if dt_fim and data_nota > dt_fim:
                    continue
        if d['prestador_cnpj'] == cnpj_empresa:
            papel, parc_cnpj, parc_nome, parc_doc = 'emitida', d['tomador_cnpj'], d['tomador_nome'], d['tomador_doc_tipo']
        elif d['tomador_cnpj'] == cnpj_empresa:
            papel, parc_cnpj, parc_nome, parc_doc = 'recebida', d['prestador_cnpj'], d['prestador_nome'], d['prestador_doc_tipo']
        else:
            papel, parc_cnpj, parc_nome, parc_doc = 'desconhecida', '', '', ''
        d['papel'] = papel
        d['parceiro_cnpj'] = parc_cnpj
        d['parceiro_nome'] = parc_nome
        d['parceiro_doc_tipo'] = parc_doc
        d['cancelada'] = cancelada
        notas.append(d)

    validas = [n for n in notas if not n['cancelada']]
    canceladas = [n for n in notas if n['cancelada']]
    com_ret = [n for n in notas if n['retido']]        # lista pra exibir: inclui canceladas (com o selo)
    sem_ret = [n for n in notas if not n['retido']]     # idem
    emitidas = sum(1 for n in validas if n['papel'] == 'emitida')
    recebidas = sum(1 for n in validas if n['papel'] == 'recebida')

    por_parceiro = {}
    for n in validas:  # cancelada não entra no ranking de parceiros
        chave = n['parceiro_cnpj'] or '?'
        g = por_parceiro.setdefault(chave, {'nome': n['parceiro_nome'] or 'Desconhecido', 'qtd': 0, 'valor': 0.0})
        g['qtd'] += 1
        g['valor'] += n['vserv']
    top_parceiros = sorted(por_parceiro.values(), key=lambda g: -g['valor'])

    return {
        'total_notas': len(validas), 'total_valor': round(sum(n['vserv'] for n in validas), 2),
        'qtd_com_retencao': sum(1 for n in com_ret if not n['cancelada']),
        'valor_com_retencao': round(sum(n['vserv'] for n in com_ret if not n['cancelada']), 2),
        'qtd_sem_retencao': sum(1 for n in sem_ret if not n['cancelada']),
        'valor_sem_retencao': round(sum(n['vserv'] for n in sem_ret if not n['cancelada']), 2),
        'emitidas': emitidas, 'recebidas': recebidas,
        'qtd_canceladas': len(canceladas), 'valor_canceladas': round(sum(n['vserv'] for n in canceladas), 2),
        'notas_com_retencao': sorted(com_ret, key=lambda n: n['competencia'], reverse=True),
        'notas_sem_retencao': sorted(sem_ret, key=lambda n: n['competencia'], reverse=True),
        'top_parceiros': top_parceiros[:10],
    }


_NFSE_CORES = ['#e8632b', '#1f2a5a', '#0ea472', '#8b5cf6', '#d4711a', '#2563eb', '#db2777', '#14b8a6']


def gerar_painel_nfse_html(dados, empresa_nome=''):
    """Painel único do Download de NFS-e — dashboard (KPIs, donut de
    com/sem retenção, top parceiros) e a lista completa, separada por
    Prestado/Tomado e com/sem retenção, com chave completa e "+" de
    detalhamento de retenção."""
    total = dados['total_notas']
    segs_ret = []
    if dados['qtd_sem_retencao']:
        segs_ret.append(('Sem retenção', dados['qtd_sem_retencao'], '#0ea472'))
    if dados['qtd_com_retencao']:
        segs_ret.append(('Com retenção', dados['qtd_com_retencao'], '#e8632b'))
    arcs_ret = _donut(segs_ret, is_money=False) if segs_ret else ''
    legend_ret = ''.join(
        f'<div class="lg"><span class="dot" style="background:{cor}"></span>{_esc(nome)}<b>{qtd}</b></div>'
        for nome, qtd, cor in segs_ret)

    top = dados['top_parceiros']
    maior = max((g['valor'] for g in top), default=1) or 1
    linhas_top = ''.join(
        f'<div style="margin-bottom:9px"><div style="display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:3px">'
        f'<span>{_esc(g["nome"])[:38]}</span><span style="color:var(--ink2)">R$ {_brl(g["valor"])} · {g["qtd"]} nota(s)</span></div>'
        f'<div style="height:6px;background:#eef0f6;border-radius:3px"><div style="width:{max(3, g["valor"] / maior * 100):.0f}%;height:100%;background:{_NFSE_CORES[i % len(_NFSE_CORES)]};border-radius:3px"></div></div></div>'
        for i, g in enumerate(top))

    def _doc(n):
        tipo = n.get('parceiro_doc_tipo', '') or ('CNPJ' if len(n.get('parceiro_cnpj', '') or '') == 14 else 'CPF')
        return f'{tipo}: {_esc(n["parceiro_cnpj"] or "—")}' if n.get('parceiro_cnpj') else ''

    def _selo_status(n):
        if n.get('cancelada'):
            return '<span style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:#fcebeb;color:#c92a2a;font-weight:800;font-size:12px" title="Cancelada">✗</span>'
        return '<span style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:#eaf3de;color:#3b6d11;font-weight:800;font-size:12px" title="Autorizada">✓</span>'

    def _linha_sem(n):
        opacidade = 'opacity:.6' if n.get('cancelada') else ''
        return (f'<tr style="{opacidade}"><td style="text-align:center">{_selo_status(n)}</td>'
                f'<td>{_esc(n["competencia"])}</td><td>NFS-e {_esc(n["nnfse"])}</td>'
                f'<td style="font-family:monospace;font-size:9.5px;word-break:break-all">{_esc(n["chave"])}</td>'
                f'<td>{_esc(n["parceiro_nome"])[:30]}<br><span style="font-size:10px;color:var(--ink2)">{_doc(n)}</span></td>'
                f'<td style="text-align:right;{"text-decoration:line-through" if n.get("cancelada") else ""}">R$ {_brl(n["vserv"])}</td></tr>')

    def _linha_com(n, prefixo, idx):
        det_id = f'ret-{prefixo}-{idx}'
        opacidade = 'opacity:.6' if n.get('cancelada') else ''
        det_rows = ''.join(
            f'<tr><td style="padding:6px 8px 6px 28px">{_esc(r["tributo"])}</td><td style="text-align:right;padding:6px 8px">R$ {_brl(r["valor"])}</td></tr>'
            for r in n['retencoes_detalhe']
        )
        detalhe_html = (
            f'<table style="width:100%;border-collapse:collapse;font-size:12px;background:var(--bg,#f4f6fb);border-radius:8px">'
            f'<tbody>{det_rows}'
            f'<tr style="font-weight:700;border-top:1px solid var(--line)"><td style="padding:6px 8px 6px 28px">Total retido</td>'
            f'<td style="text-align:right;padding:6px 8px">R$ {_brl(n["total_retido"])}</td></tr></tbody></table>'
        ) if det_rows else '<div style="padding:6px 8px 6px 28px;color:var(--ink2);font-size:12px">Sem detalhamento por tributo disponível nessa nota.</div>'
        return (
            f'<tr class="lb-ret" data-alvo="{det_id}" style="cursor:pointer;{opacidade}">'
            f'<td style="text-align:center">{_selo_status(n)}</td>'
            f'<td>{_esc(n["competencia"])}</td><td>NFS-e {_esc(n["nnfse"])}</td>'
            f'<td style="font-family:monospace;font-size:9.5px;word-break:break-all">{_esc(n["chave"])}</td>'
            f'<td>{_esc(n["parceiro_nome"])[:26]}<br><span style="font-size:10px;color:var(--ink2)">{_doc(n)}</span></td>'
            f'<td style="text-align:right;color:#e8632b;font-weight:700;{"text-decoration:line-through" if n.get("cancelada") else ""}">R$ {_brl(n["vserv"])}</td>'
            f'<td style="text-align:center"><span class="btn-mais" id="mais-{det_id}">+</span></td></tr>'
            f'<tr id="{det_id}" class="linha-detalhe" style="display:none"><td colspan="7" style="padding:4px 8px 12px">{detalhe_html}</td></tr>'
        )

    def _rodape_totais(validas, canceladas, colspan, extra=''):
        linhas = (f'<tr style="font-weight:700;border-top:2px solid var(--navy)"><td colspan="{colspan-1}" style="padding:9px 8px">Total autorizadas ({len(validas)} nota(s)){extra}</td>'
                  f'<td style="text-align:right;padding:9px 8px">R$ {_brl(sum(n["vserv"] for n in validas))}</td><td></td></tr>')
        if canceladas:
            linhas += (f'<tr style="color:#c92a2a;font-size:12px"><td colspan="{colspan-1}" style="padding:6px 8px">Total canceladas ({len(canceladas)} nota(s)) — não soma no total acima</td>'
                       f'<td style="text-align:right;padding:6px 8px">R$ {_brl(sum(n["vserv"] for n in canceladas))}</td><td></td></tr>')
        return linhas

    def _tabela_sem(notas):
        if not notas:
            return '<div class="emptyok">✓ Nenhuma nota sem retenção.</div>'
        rows = ''.join(_linha_sem(n) for n in notas)
        validas = [n for n in notas if not n.get('cancelada')]
        canceladas = [n for n in notas if n.get('cancelada')]
        return (f'<table style="width:100%;border-collapse:collapse;font-size:12.5px">'
                f'<thead><tr><th style="padding:8px;color:var(--ink2);font-size:9.5px;text-transform:uppercase">Sit.</th>'
                f'<th style="text-align:left;padding:8px;color:var(--ink2);font-size:9.5px;text-transform:uppercase">Compet.</th>'
                f'<th style="text-align:left;padding:8px;color:var(--ink2);font-size:9.5px;text-transform:uppercase">Nota</th>'
                f'<th style="text-align:left;padding:8px;color:var(--ink2);font-size:9.5px;text-transform:uppercase">Chave de acesso</th>'
                f'<th style="text-align:left;padding:8px;color:var(--ink2);font-size:9.5px;text-transform:uppercase">Parceiro</th>'
                f'<th style="text-align:right;padding:8px;color:var(--ink2);font-size:9.5px;text-transform:uppercase">Valor</th></tr></thead>'
                f'<tbody>{rows}</tbody>'
                f'<tfoot>{_rodape_totais(validas, canceladas, 5)}</tfoot></table>')

    def _tabela_com(notas, prefixo):
        if not notas:
            return '<div class="emptyok">✓ Nenhuma nota com retenção.</div>'
        rows = ''.join(_linha_com(n, prefixo, i) for i, n in enumerate(notas))
        validas = [n for n in notas if not n.get('cancelada')]
        canceladas = [n for n in notas if n.get('cancelada')]
        retido_str = f' · retido: R$ {_brl(sum(n["total_retido"] for n in validas))}'
        return (f'<table style="width:100%;border-collapse:collapse;font-size:12.5px">'
                f'<thead><tr><th style="padding:8px;color:var(--ink2);font-size:9.5px;text-transform:uppercase">Sit.</th>'
                f'<th style="text-align:left;padding:8px;color:var(--ink2);font-size:9.5px;text-transform:uppercase">Compet.</th>'
                f'<th style="text-align:left;padding:8px;color:var(--ink2);font-size:9.5px;text-transform:uppercase">Nota</th>'
                f'<th style="text-align:left;padding:8px;color:var(--ink2);font-size:9.5px;text-transform:uppercase">Chave de acesso</th>'
                f'<th style="text-align:left;padding:8px;color:var(--ink2);font-size:9.5px;text-transform:uppercase">Parceiro</th>'
                f'<th style="text-align:right;padding:8px;color:var(--ink2);font-size:9.5px;text-transform:uppercase">Valor</th>'
                f'<th style="text-align:center;padding:8px;color:var(--ink2);font-size:9.5px;text-transform:uppercase">Retenção</th></tr></thead>'
                f'<tbody>{rows}</tbody>'
                f'<tfoot>{_rodape_totais(validas, canceladas, 6, retido_str)}</tfoot></table>')

    prestados_com = [n for n in dados['notas_com_retencao'] if n['papel'] == 'emitida']
    prestados_sem = [n for n in dados['notas_sem_retencao'] if n['papel'] == 'emitida']
    tomados_com = [n for n in dados['notas_com_retencao'] if n['papel'] == 'recebida']
    tomados_sem = [n for n in dados['notas_sem_retencao'] if n['papel'] == 'recebida']

    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Painel de NFS-e{f" · {_esc(empresa_nome)}" if empresa_nome else ""}</title>
<style>
:root{{--navy:#1f2a5a;--ink:#232a3d;--ink2:#7a8199;--line:#eef0f6;--bg:#f4f6fb}}
*{{box-sizing:border-box}} body{{font-family:'Segoe UI',Arial,sans-serif;margin:0;background:#f4f5fa;color:var(--ink)}}
.hdr{{background:linear-gradient(120deg,#1f2a5a,#2b3a72);color:#fff;padding:18px 24px}}
.card{{background:#fff;border-radius:14px;padding:18px 20px;margin:14px 20px;box-shadow:0 4px 14px rgba(31,42,90,.06)}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:0;margin:0 20px}}
.grid2 .card{{margin:14px 10px}}
h3{{margin:0 0 12px;font-size:14px;display:flex;align-items:center;gap:8px}}
h2.secao{{margin:22px 20px 4px;font-size:16px;color:var(--navy);display:flex;align-items:center;gap:8px}}
.dot{{width:8px;height:8px;border-radius:50%;background:var(--navy);display:inline-block}}
.dot.sem{{background:#0ea472}}.dot.com{{background:#e8632b}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 20px}}
.kpi{{background:#fff;border-radius:14px;padding:16px;text-align:center;box-shadow:0 4px 14px rgba(31,42,90,.06)}}
.kpi b{{display:block;font-size:22px}}.kpi span{{font-size:10.5px;color:var(--ink2)}}
.donut-row{{display:flex;align-items:center;gap:18px}}
.donut{{position:relative;width:170px;height:170px;flex:0 0 auto}}
.donut-seg{{cursor:pointer;transition:opacity .15s,filter .15s}}
.donut:hover .donut-seg:not(:hover){{opacity:.35}}
.donut-seg:hover{{filter:drop-shadow(0 4px 8px rgba(31,42,90,.35))}}
.center{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}}
.center .big{{font-size:24px;font-weight:800;color:var(--navy)}}.center .sm{{font-size:10px;color:var(--ink2)}}
.legend{{flex:1;display:flex;flex-direction:column;gap:9px}}
.lg{{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--ink);border-radius:9px;padding:6px 8px;margin:0 -8px;transition:transform .15s,box-shadow .15s,background .15s}}
.lg:hover{{transform:translateX(4px);background:#fff;box-shadow:0 6px 16px rgba(31,42,90,.14)}}
.lg .dot{{width:11px;height:11px;border-radius:3px;flex:0 0 auto}}.lg b{{margin-left:auto;font-weight:700}}
td,th{{border-bottom:1px solid var(--line)}}
.emptyok{{color:#0ea472;font-size:12.5px}}
.lb-ret:hover{{background:#faf4f0}}
.btn-mais{{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;
  background:#e8632b;color:#fff;font-weight:800;font-size:13px;transition:transform .2s}}
.btn-mais.aberto{{transform:rotate(45deg)}}
.dtip{{position:fixed;pointer-events:none;z-index:9999;background:var(--navy,#1f2a5a);color:#fff;
  font-size:11.5px;font-weight:600;padding:8px 11px;border-radius:9px;box-shadow:0 8px 22px rgba(0,0,0,.28);
  white-space:nowrap;opacity:0;transform:translate(-50%,-115%);transition:opacity .1s;top:0;left:0}}
.dtip b{{display:block;font-size:12.5px;margin-bottom:2px;font-weight:800}}
.dtip.show{{opacity:1}}
</style></head><body>
<div class="hdr"><b>FiscoCont+ · Download de Documentos Fiscais</b><div>Painel de NFS-e{f" · {_esc(empresa_nome)}" if empresa_nome else ""}</div></div>
<div class="kpis">
  <div class="kpi"><b>{total}</b><span>Total de notas</span></div>
  <div class="kpi"><b>R$ {_brl(dados['total_valor'])}</b><span>Valor total</span></div>
  <div class="kpi"><b style="color:#0ea472">{dados['qtd_sem_retencao']}</b><span>Sem retenção</span></div>
  <div class="kpi"><b style="color:#e8632b">{dados['qtd_com_retencao']}</b><span>Com retenção</span></div>
</div>
{f'<div class="card" style="background:#fef3f2;border:1px solid #fecdca"><div style="font-size:12.5px;color:#7a1f1f">⚠ {dados["qtd_canceladas"]} nota(s) cancelada(s) foram baixadas mas ficaram de fora dos totais acima — arquivos salvos com .CANCELADA no nome, pra referência.</div></div>' if dados.get('qtd_canceladas') else ''}
<div class="grid2">
  <div class="card"><h3><span class="dot"></span>Com × sem retenção</h3>
    {"<div class='donut-row'><div class='donut'><svg width='170' height='170' viewBox='0 0 180 180'>" + arcs_ret + "</svg><div class='center'><div class='big'>" + str(total) + "</div><div class='sm'>notas</div></div></div><div class='legend'>" + legend_ret + "</div></div>" if segs_ret else "<div style='color:#0ea472;font-size:12.5px'>Nenhuma nota ainda.</div>"}
  </div>
  <div class="card"><h3><span class="dot"></span>Top parceiros por valor</h3>
    {linhas_top if linhas_top else "<div style='color:var(--ink2);font-size:12.5px'>Nenhuma nota ainda.</div>"}
  </div>
</div>

<h2 class="secao"><span class="dot"></span>Serviços Prestados <span style="font-size:12px;color:var(--ink2);font-weight:400">({dados['emitidas']} nota(s))</span></h2>
<div class="card"><h3><span class="dot com"></span>Com retenção <span style="font-size:11px;color:var(--ink2);font-weight:400">(clique numa linha pra ver o detalhamento)</span></h3>{_tabela_com(prestados_com, 'prest')}</div>
<div class="card"><h3><span class="dot sem"></span>Sem retenção</h3>{_tabela_sem(prestados_sem)}</div>

<h2 class="secao"><span class="dot"></span>Serviços Tomados <span style="font-size:12px;color:var(--ink2);font-weight:400">({dados['recebidas']} nota(s))</span></h2>
<div class="card"><h3><span class="dot com"></span>Com retenção <span style="font-size:11px;color:var(--ink2);font-weight:400">(clique numa linha pra ver o detalhamento)</span></h3>{_tabela_com(tomados_com, 'toma')}</div>
<div class="card"><h3><span class="dot sem"></span>Sem retenção</h3>{_tabela_sem(tomados_sem)}</div>

<div class="card"><div style="font-size:11.5px;color:var(--ink2)">"Com retenção" considera ISS (tpRetISSQN) e PIS/COFINS/CSLL/IRRF/INSS retidos na fonte.</div></div>
<script>
document.querySelectorAll('.lb-ret').forEach(function(tr){{
  tr.addEventListener('click', function(){{
    var alvo = document.getElementById(tr.dataset.alvo);
    var btn = document.getElementById('mais-' + tr.dataset.alvo);
    var abrindo = alvo.style.display === 'none';
    alvo.style.display = abrindo ? 'table-row' : 'none';
    btn.classList.toggle('aberto', abrindo);
  }});
}});
</script>
{_COUNT_JS}
</body></html>'''


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

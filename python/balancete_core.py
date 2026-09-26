"""
Núcleo de leitura e análise de Balancete do Domínio Sistemas (PDF).

Extrai:
  - Dados da empresa (nome, CNPJ, Insc. Junta Comercial)
  - Período do balancete
  - Resultado contábil do período (Lucro/Prejuízo)
  - Totais e conferência de fechamento (Ativo x Passivo x Resultado)
  - Saldos invertidos/virados por grupo, EXCETO contas redutoras "(-)"

API principal:
    dados = parse_balancete("arquivo.pdf")

Estratégia de parsing (robusta ao layout do Domínio):
  - As 4 colunas de valor (Saldo Anterior, Débito, Crédito, Saldo Atual)
    são ancoradas pela posição X (borda direita fixa).
  - Cada conta tem o rótulo duplicado no PDF. A cópia "código+descrição"
    (que começa com dígitos) é a boa; a cópia só-rótulo é descartada.
  - Conta SINTÉTICA => rótulo em fonte negrito (Tahoma,Bold).
    Conta ANALÍTICA => fonte normal. A análise foca nas analíticas.
  - Conta REDUTORA => descrição começa com "(-)".
"""

import re
import os
import math
import json
import html as _html_mod
from dataclasses import dataclass, field, asdict
from typing import Optional

import pdfplumber

# Bordas direitas (x1) das 4 colunas de valor no balancete Domínio (A4).
_COL_ANCHORS = [351.6, 422.3, 493.0, 563.8]
_COL_TOL = 14.0
_DESC_MAX_X = 300.0        # descrição fica à esquerda das colunas de valor
_LINE_TOL = 4.0            # agrupa a linha contábil inteira (cópias + valores)
_SUBROW_TOL = 0.35         # separa as duas cópias sobrepostas do rótulo

_MONEY = re.compile(r'^-?\d{1,3}(?:\.\d{3})*,\d{2}([DC])?$')
_CODE_PREFIX = re.compile(r'^(\d+)(.*)$', re.DOTALL)


def _esc_html(s):
    return _html_mod.escape('' if s is None else str(s))

def _to_float(tok: str) -> float:
    """'152.475.467,10' -> 152475467.10"""
    return float(tok.replace('.', '').replace(',', '.'))


def _parse_money(tok: str):
    """Retorna (valor_float, lado) onde lado in {'D','C',None}."""
    m = _MONEY.match(tok)
    if not m:
        return None
    lado = m.group(1)
    val = _to_float(tok[:-1] if lado else tok)
    return val, lado


@dataclass
class Conta:
    codigo: Optional[str]
    descricao: str
    sintetica: bool
    redutora: bool
    grupo: str                 # ATIVO / PASSIVO / PL / RESULTADO_DESP / RESULTADO_REC
    natureza: str              # 'D' ou 'C' (lado natural do grupo)
    saldo_anterior: float = 0.0
    lado_saldo_anterior: Optional[str] = None
    debito: float = 0.0
    credito: float = 0.0
    saldo_atual: float = 0.0
    lado_saldo_atual: Optional[str] = None
    invertido: bool = False
    subgrupo: Optional[str] = None   # 'CIRCULANTE' / 'NAO_CIRCULANTE' (quando o balancete traz)


# ---- Cabeçalho / metadados ------------------------------------------------

def _extrair_metadados(pdf) -> dict:
    md = {"empresa": None, "cnpj": None, "insc_junta": None,
          "data_abertura": None, "periodo": None,
          "periodo_ini": None, "periodo_fim": None}
    # Junta texto das linhas de cabeçalho da 1a página (reg + bold).
    chars = pdf.pages[0].chars
    linhas = {}
    for c in chars:
        if c['top'] < 90:  # zona do cabeçalho (tolerante a layouts)
            linhas.setdefault(round(c['top']), []).append(c)
    blob = ""
    linhas_txt = []
    for k in sorted(linhas):
        s = ''.join(ch['text'] for ch in sorted(linhas[k], key=lambda c: c['x0']))
        blob += s + "\n"
        linhas_txt.append(s.strip())

    m = re.search(r'Empresa:\s*(.+?)(?:Folha:|N[úu]mero|Insc\.|CNPJ|C\.N\.P\.J|$)', blob)
    if m:
        md["empresa"] = m.group(1).strip()
    if not md["empresa"]:
        # fallback: linha que parece razão social
        for s in linhas_txt:
            if re.search(r'\b(LTDA|EIRELI|EPP|S/?A|S\.A\.?|ME)\b', s, re.I) and len(s) > 6:
                md["empresa"] = re.sub(r'^(Empresa:?\s*)', '', s).strip()
                break
    m = re.search(r'C\.?N\.?P\.?J\.?:?\s*([\d./-]{14,20})', blob)
    if m:
        md["cnpj"] = m.group(1).strip()
    m = re.search(r'Insc\.?\s*Junta\s*Comercial:?\s*(\d+)', blob)
    if m:
        md["insc_junta"] = m.group(1).strip()
    m = re.search(r'Data:\s*(\d{2}/\d{2}/\d{4})', blob)
    if m:
        md["data_abertura"] = m.group(1)
    m = re.search(r'Per[ií]odo:?\s*(\d{2}/\d{2}/\d{4})\s*[-aà]+\s*(\d{2}/\d{2}/\d{4})', blob)
    if m:
        md["periodo_ini"], md["periodo_fim"] = m.group(1), m.group(2)
        md["periodo"] = f'{m.group(1)} - {m.group(2)}'
    return md


# ---- Linhas de conta ------------------------------------------------------

def _cluster_linhas(chars):
    """Agrupa chars numa linha contábil (tolerância _LINE_TOL)."""
    chars = sorted(chars, key=lambda c: c['top'])
    linhas, atual, base = [], [], None
    for c in chars:
        if base is None or abs(c['top'] - base) <= _LINE_TOL:
            atual.append(c)
            base = c['top'] if base is None else base
        else:
            linhas.append(atual)
            atual, base = [c], c['top']
    if atual:
        linhas.append(atual)
    return linhas


def _melhor_rotulo(desc_chars):
    """
    Dentre as cópias sobrepostas do rótulo, escolhe a cópia 'código+descrição'
    (a que começa com dígitos). Prioriza negrito (=> sintética).
    Retorna (codigo, descricao, sintetica).
    """
    # separa em sub-linhas por 'top' fino
    subs = {}
    for c in desc_chars:
        subs.setdefault(round(c['top'] / _SUBROW_TOL), []).append(c)
    candidatos = []
    for grp in subs.values():
        bold = any('Bold' in c['fontname'] for c in grp)
        s = ''.join(c['text'] for c in sorted(grp, key=lambda c: c['x0'])).strip()
        if s:
            candidatos.append((bold, s))
    if not candidatos:
        return None, "", False

    # 1) cópia com prefixo de código (dígitos no início)
    com_codigo = [(b, s) for (b, s) in candidatos if s[:1].isdigit()]
    if com_codigo:
        # prefere negrito (sintética) se houver
        com_codigo.sort(key=lambda x: (not x[0], -len(x[1])))
        bold, s = com_codigo[0]
        m = _CODE_PREFIX.match(s)
        codigo, desc = (m.group(1), m.group(2).strip()) if m else (None, s)
        return codigo, desc, bold
    # 2) sem código: pega a mais longa e limpa
    candidatos.sort(key=lambda x: -len(x[1]))
    bold, s = candidatos[0]
    return None, s.strip(), bold


_SECOES = [
    (re.compile(r'^ATIVO\b'),                         'ATIVO', 'D'),
    (re.compile(r'^PASSIVO\b'),                       'PASSIVO', 'C'),
    (re.compile(r'^PATRIM[ÔO]NIO\s+L[ÍI]QUIDO'),      'PL', 'C'),
    (re.compile(r'CUSTOS\s+E\s+DESPESAS'),            'RESULTADO_DESP', 'D'),
    (re.compile(r'^CUSTOS\b'),                        'RESULTADO_DESP', 'D'),
    (re.compile(r'^DESPESAS\b'),                      'RESULTADO_DESP', 'D'),
    (re.compile(r'RESULTADO\s*-\s*RECEITAS'),         'RESULTADO_REC', 'C'),
    (re.compile(r'^RECEITAS\b'),                      'RESULTADO_REC', 'C'),
]


def _classifica_secao(desc):
    d = desc.upper().strip()
    for rx, grupo, nat in _SECOES:
        if rx.search(d):
            return grupo, nat
    return None


def _detectar_colunas(page):
    """Detecta as bordas direitas (x1) das 4 colunas de valor pelo cabeçalho.
    Retorna [ant, deb, cred, atual] ou None se não achar o cabeçalho."""
    words = page.extract_words()

    def achar(alvos):
        for w in words:
            if w['text'].strip().lower() in alvos:
                return w
        return None

    ant = achar({'anterior'})
    deb = achar({'débito', 'debito'})
    cred = achar({'crédito', 'credito'})
    atu = achar({'atual'})
    achados = [w for w in (ant, deb, cred, atu) if w]
    if len(achados) == 4:
        xs = [ant['x1'], deb['x1'], cred['x1'], atu['x1']]
        # só aceita se estiverem em ordem crescente (layout coerente)
        if xs == sorted(xs):
            return xs
    return None


def parse_balancete(pdf_path: str) -> dict:
    contas = []
    md = None
    resultado = {"tipo": None, "valor": 0.0, "lado": None, "linha": None}
    totais = {}

    with pdfplumber.open(pdf_path) as pdf:
        md = _extrair_metadados(pdf)

        grupo_atual, nat_atual = None, None
        subgrupo_atual = None
        em_resumo = False
        anchors = list(_COL_ANCHORS)   # reserva; atualiza ao achar cabeçalho

        for page in pdf.pages:
            det = _detectar_colunas(page)
            if det:
                anchors = det
            for linha in _cluster_linhas(page.chars):
                # valores por coluna (ancorados por x1)
                valores = [None, None, None, None]
                val_x0s = []
                tops = [c['top'] for c in linha]
                lo, hi = min(tops) - 1, max(tops) + 3
                words = [w for w in page.extract_words()
                         if lo <= w['top'] <= hi]
                for w in words:
                    pm = _parse_money(w['text'])
                    if pm is None:
                        continue
                    for i, anchor in enumerate(anchors):
                        if abs(w['x1'] - anchor) <= _COL_TOL:
                            valores[i] = (w['text'], pm)
                            val_x0s.append(w['x0'])
                            break

                # descrição = tudo à esquerda do primeiro valor da linha
                desc_cut = (min(val_x0s) - 2) if val_x0s else _DESC_MAX_X
                desc_chars = [c for c in linha if c['x1'] < desc_cut]
                codigo, desc, sintetica = _melhor_rotulo(desc_chars)
                if not desc:
                    continue

                dU = desc.upper()

                # detecta início do RESUMO / apuração no fim do relatório
                if re.search(r'RESUMO DO BALANCETE', dU):
                    em_resumo = True
                if re.search(r'RESULTADO DO EXERC[ÍI]CIO', dU) and valores[3]:
                    v = valores[3][1]
                    resultado = {"valor": v[0], "lado": v[1],
                                 "tipo": "PREJUÍZO" if v[1] == 'D' else "LUCRO",
                                 "linha": desc}
                if re.search(r'RESULTADO DO M[ÊE]S', dU) and valores[3] and resultado["linha"] is None:
                    v = valores[3][1]
                    resultado = {"valor": v[0], "lado": v[1],
                                 "tipo": "PREJUÍZO" if v[1] == 'D' else "LUCRO",
                                 "linha": desc}

                # atualiza seção corrente (fora do resumo)
                sec = _classifica_secao(desc)
                if sec and not em_resumo:
                    grupo_atual, nat_atual = sec

                # detecta subgrupo circulante × não circulante (quando existir no plano)
                if not em_resumo and grupo_atual in ('ATIVO', 'PASSIVO'):
                    if 'CIRCULANTE' in dU and 'NÃO' not in dU and 'NAO' not in dU:
                        subgrupo_atual = 'CIRCULANTE'
                    elif any(k in dU for k in ('NÃO CIRCULANTE', 'NAO CIRCULANTE',
                             'REALIZÁVEL A LONGO', 'REALIZAVEL A LONGO', 'ATIVO PERMANENTE',
                             'EXIGÍVEL A LONGO', 'EXIGIVEL A LONGO')):
                        subgrupo_atual = 'NAO_CIRCULANTE'
                    elif sintetica and any(k == dU.strip() or dU.strip().startswith(k) for k in (
                             'INVESTIMENTOS', 'IMOBILIZADO', 'INTANGÍVEL', 'INTANGIVEL', 'DIFERIDO')):
                        subgrupo_atual = 'NAO_CIRCULANTE'
                elif grupo_atual in ('PL', 'RESULTADO_DESP', 'RESULTADO_REC'):
                    subgrupo_atual = None

                # captura totais do resumo final
                if em_resumo and valores[3]:
                    if re.fullmatch(r'ATIVO', dU):
                        totais['ativo'] = valores[3][1]
                    elif re.fullmatch(r'PASSIVO', dU):
                        totais['passivo'] = valores[3][1]
                    elif 'CUSTOS E DESPESAS' in dU:
                        totais['despesas'] = valores[3][1]
                    elif dU.endswith('RECEITAS') and 'DEVEDORAS' not in dU and 'CREDORAS' not in dU:
                        totais['receitas'] = valores[3][1]

                # é conta? precisa ter as 4 colunas de valor
                if not all(valores):
                    continue
                if em_resumo:
                    continue
                if grupo_atual is None:
                    continue
                # linha de total/seção "TOTAL ..." -> ignora como conta analítica
                if dU.startswith('TOTAL '):
                    continue

                sa = valores[0][1]   # (valor, lado)
                db = valores[1][1]
                cr = valores[2][1]
                st = valores[3][1]

                redutora = desc.strip().startswith('(-)')
                lado_st = st[1]
                invertido = (
                    not sintetica and not redutora and st[0] != 0.0
                    and lado_st is not None and lado_st != nat_atual
                )

                contas.append(Conta(
                    codigo=codigo, descricao=desc, sintetica=sintetica,
                    redutora=redutora, grupo=grupo_atual, natureza=nat_atual,
                    saldo_anterior=sa[0], lado_saldo_anterior=sa[1],
                    debito=db[0], credito=cr[0],
                    saldo_atual=st[0], lado_saldo_atual=lado_st,
                    invertido=invertido,
                    subgrupo=(subgrupo_atual if grupo_atual in ('ATIVO', 'PASSIVO') else None),
                ))

    invertidas = [c for c in contas if c.invertido]
    invertidas.sort(key=lambda c: -c.saldo_atual)

    dre = _montar_dre(contas, totais, resultado)
    dre["completa"], dre["despesas_por_tipo"] = _montar_dre_completa(contas)

    # conferência de fechamento
    conf = None
    if 'ativo' in totais and 'passivo' in totais:
        a = totais['ativo'][0]
        p = totais['passivo'][0]
        dif = round(abs(a - p), 2)
        bate_result = abs(dif - round(resultado['valor'], 2)) < 0.02
        conf = {
            "ativo": a, "passivo": p, "diferenca": dif,
            "fecha_com_resultado": bate_result,
        }

    return {
        "empresa": md,
        "resultado": resultado,
        "conferencia": conf,
        "totais_conta": len(contas),
        "analiticas": sum(1 for c in contas if not c.sintetica),
        "invertidas": [asdict(c) for c in invertidas],
        "todas": [asdict(c) for c in contas],
        "dre": dre,
    }


def _montar_dre(contas, totais, resultado) -> dict:
    """Extrai receitas/despesas e composição para o dashboard."""
    REC = ('RESULTADO_REC',)
    DESP = ('RESULTADO_DESP',)

    def find(rx, grupos=None, first=True):
        pat = re.compile(rx, re.I)
        pool = [c for c in contas if (grupos is None or c.grupo in grupos)]
        hits = [c.saldo_atual for c in pool if c.sintetica and pat.search(c.descricao)]
        if not hits:
            hits = [c.saldo_atual for c in pool if pat.search(c.descricao)]
        if not hits:
            return 0.0
        return hits[0] if first else max(hits)

    receita_bruta = find(r'RECEITA BRUTA DE VENDAS', REC)
    deducoes      = find(r'\(-\)\s*DEDU[ÇC]', REC)
    rec_fin       = find(r'^RECEITAS FINANCEIRAS', REC)
    rec_outras    = find(r'OUTRAS RECEITAS OPERACIONAIS', REC) + find(r'RESULTADOS? N[ÃA]O OPERACIONA', REC)
    combustivel   = find(r'VENDA DE COMBUST', REC)
    mercadorias   = find(r'^VENDA DE MERCADORIAS', REC)
    servicos      = find(r'PRESTA[ÇC][ÃA]O DE SERVI', REC)

    cmv        = find(r'MERCADORIAS VENDIDAS', DESP)
    d_pessoal  = find(r'DESPESAS COM PESSOAL', DESP)
    d_gerais   = find(r'^DESPESAS GERAIS', DESP)
    d_fin      = find(r'^DESPESAS FINANCEIRAS', DESP)
    d_trib     = find(r'IMPOSTOS,?\s*TAXAS', DESP)
    d_admin    = find(r'^DESPESAS ADMINISTRATIVAS', DESP) or find(r'DESPESAS OPERACIONAIS$', DESP)

    receita_total = totais.get('receitas', (0.0, 'C'))[0] or \
        (receita_bruta - deducoes + rec_fin + rec_outras)
    despesa_total = totais.get('despesas', (0.0, 'D'))[0] or (cmv + d_admin)

    receita_liquida = receita_bruta - deducoes
    lucro_bruto = receita_liquida - cmv

    res_val = resultado.get('valor', 0.0)
    res_signed = -res_val if resultado.get('lado') == 'D' else res_val

    # composição de despesas (garante fechamento com "Outras")
    comp_desp = []
    if cmv:      comp_desp.append(("Custo das mercadorias (CMV)", cmv))
    if d_gerais: comp_desp.append(("Despesas gerais", d_gerais))
    if d_pessoal:comp_desp.append(("Despesas com pessoal", d_pessoal))
    if d_fin:    comp_desp.append(("Despesas financeiras", d_fin))
    if d_trib:   comp_desp.append(("Impostos e taxas", d_trib))
    outras_desp = round(despesa_total - sum(v for _, v in comp_desp), 2)
    if outras_desp > 0.005:
        comp_desp.append(("Outras despesas", outras_desp))

    # composição da receita (bruta, por tipo — só contas do grupo Receitas)
    comp_rec = []
    if combustivel: comp_rec.append(("Vendas de combustível", combustivel))
    if mercadorias: comp_rec.append(("Vendas de mercadorias", mercadorias))
    if servicos:    comp_rec.append(("Serviços prestados", servicos))
    if rec_fin:     comp_rec.append(("Receitas financeiras", rec_fin))
    if rec_outras:  comp_rec.append(("Outras receitas", rec_outras))

    return {
        "receita_bruta": receita_bruta,
        "deducoes": deducoes,
        "receita_liquida": receita_liquida,
        "receita_total": receita_total,
        "cmv": cmv,
        "lucro_bruto": lucro_bruto,
        "despesa_total": despesa_total,
        "resultado": res_signed,
        "margem_bruta": (lucro_bruto / receita_liquida * 100) if receita_liquida else 0.0,
        "margem_liquida": (res_signed / receita_liquida * 100) if receita_liquida else 0.0,
        "peso_cmv": (cmv / receita_liquida * 100) if receita_liquida else 0.0,
        "composicao_despesas": comp_desp,
        "composicao_receitas": comp_rec,
    }


# Classifica cada CABEÇALHO (conta sintética) de RESULTADO_REC/RESULTADO_DESP
# num "macro" da DRE clássica. Primeira regra que bater vence; sem match cai
# no fallback (outras_receitas / despesas_administrativas).
_MACRO_REC = [
    ('receita_bruta', r'RECEITA BRUTA'),
    ('deducoes', r'DEDU[ÇC][ÃA]O|DEVOLU[ÇC][ÃA]O|CANCELAMENTO|IMPOSTOS SOBRE VENDAS'),
    ('receitas_financeiras', r'RECEITAS?\s*FINANCEIRA|JUROS E DESCONTOS'),
]
_MACRO_DESP = [
    ('cmv', r'MERCADORIAS VENDID|CUSTO.*VENDID|TRANSPORTE NA AQUISI'),
    ('despesas_pessoal', r'DESPESAS COM PESSOAL'),
    ('impostos_taxas', r'IMPOSTOS,?\s*TAXAS'),
    ('despesas_financeiras', r'^DESPESAS FINANCEIRAS'),
    ('tributos_lucro', r'\bIRPJ\b|IMPOSTO DE RENDA|\bCSLL\b|CONTRIBUI[ÇC][ÃA]O SOCIAL'),
]
MACRO_LABELS = {
    'receita_bruta': 'Receita Operacional Bruta', 'deducoes': '(−) Deduções da Receita Bruta',
    'receitas_financeiras': 'Receitas Financeiras', 'outras_receitas': 'Outras Receitas',
    'cmv': '(−) Custo das Mercadorias Vendidas', 'despesas_pessoal': 'Despesas com Pessoal',
    'impostos_taxas': 'Impostos, Taxas e Contribuições', 'despesas_financeiras': '(−) Despesas Financeiras',
    'despesas_administrativas': '(−) Despesas Administrativas', 'tributos_lucro': '(−) Tributos sobre o Lucro',
}
_ORDEM_MACRO = ['receita_bruta', 'deducoes', 'cmv', 'despesas_pessoal', 'impostos_taxas',
                'despesas_administrativas', 'despesas_financeiras', 'receitas_financeiras',
                'outras_receitas', 'tributos_lucro']

def _macro_de(desc, patterns, fallback):
    for nome, rx in patterns:
        if re.search(rx, desc, re.I):
            return nome
    return fallback

def _montar_dre_completa(contas):
    """DRE conta por conta, respeitando a ordem/hierarquia do próprio balancete
    (Domínio lista cabeçalho sintético seguido dos filhos analíticos, nessa ordem —
    quando aparecem cabeçalhos consecutivos sem filho no meio, só o ÚLTIMO deles
    antes das contas analíticas vira o "dono" delas, os anteriores eram só
    subtotais/rótulos redundantes). Devolve (grupos_para_tabela, despesas_por_tipo_donut)."""
    grupos = []
    current = None
    for c in contas:
        if c.grupo not in ('RESULTADO_REC', 'RESULTADO_DESP'):
            continue
        if c.sintetica:
            fallback = 'outras_receitas' if c.grupo == 'RESULTADO_REC' else 'despesas_administrativas'
            macro = _macro_de(c.descricao, _MACRO_REC if c.grupo == 'RESULTADO_REC' else _MACRO_DESP, fallback)
            current = {'macro': macro, 'rec_or_desp': c.grupo, 'titulo': c.descricao.strip(),
                       'valor': c.saldo_atual, 'filhos': []}
        else:
            if current is None:
                continue
            if not grupos or grupos[-1] is not current:
                grupos.append(current)
            current['filhos'].append({'descricao': c.descricao.strip(), 'valor': c.saldo_atual})

    grupos = [g for g in grupos if g['filhos']]
    grupos.sort(key=lambda g: _ORDEM_MACRO.index(g['macro']) if g['macro'] in _ORDEM_MACRO else 99)

    cores = {'cmv': '#1f2a5a', 'despesas_pessoal': '#e8632b', 'impostos_taxas': '#e0a92e',
             'despesas_administrativas': '#9aa3c0', 'despesas_financeiras': '#7c3aed'}
    soma_por_macro = {}
    for g in grupos:
        if g['rec_or_desp'] != 'RESULTADO_DESP' or g['macro'] == 'tributos_lucro':
            continue
        soma_por_macro[g['macro']] = soma_por_macro.get(g['macro'], 0.0) + g['valor']
    despesas_por_tipo = [
        {'macro': m, 'label': MACRO_LABELS.get(m, m), 'valor': round(v, 2), 'cor': cores.get(m, '#6b7290')}
        for m, v in soma_por_macro.items() if v > 0.005
    ]
    despesas_por_tipo.sort(key=lambda d: -d['valor'])
    return grupos, despesas_por_tipo


def _brl(v: float) -> str:
    s = f"{v:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _brl_compacto(v: float) -> str:
    """Versão abreviada (R$ 83,8 mi) pra espaços apertados, tipo o centro de
    um donut pequeno — achado real: o valor completo (R$ 83.815.567,33) não
    cabia e ficava com o primeiro dígito cortado pela borda do círculo."""
    a = abs(v)
    sinal = '-' if v < 0 else ''
    if a >= 1_000_000_000:
        return f"{sinal}R$ {a/1_000_000_000:.1f}".replace('.', ',') + " bi"
    if a >= 1_000_000:
        return f"{sinal}R$ {a/1_000_000:.1f}".replace('.', ',') + " mi"
    if a >= 1_000:
        return f"{sinal}R$ {a/1_000:.1f}".replace('.', ',') + " mil"
    return f"{sinal}R$ {_brl(a)}"


def _pct2(v):
    return f"{v:.2f}".replace(".", ",")


def _pct1(v):
    return f"{v:.1f}".replace(".", ",")


# Agrupamento de exibição: (chave interna) -> (rótulo, cor)
_GRUPOS_EXIBICAO = [
    ("ATIVO",  "Ativo",              ["ATIVO"]),
    ("PASSIVO","Passivo",            ["PASSIVO"]),
    ("PL",     "Patrimônio Líquido", ["PL"]),
    ("RESULT", "Contas de Resultado",["RESULTADO_DESP", "RESULTADO_REC"]),
]
_SUBGRUPO_NOME = {
    "ATIVO": "Ativo", "PASSIVO": "Passivo", "PL": "Patrim. Líquido",
    "RESULTADO_DESP": "Custo/Despesa", "RESULTADO_REC": "Receita",
}


def agrupar_invertidas(dados: dict) -> list:
    """Separa as contas invertidas por grupo de exibição (Ativo/Passivo/PL/Resultado)."""
    out = []
    for chave, rotulo, internos in _GRUPOS_EXIBICAO:
        itens = [c for c in dados["invertidas"] if c["grupo"] in internos]
        itens.sort(key=lambda c: -c["saldo_atual"])
        soma = sum(c["saldo_atual"] for c in itens)
        out.append({"chave": chave, "rotulo": rotulo, "itens": itens, "soma": soma})
    return out


def _donut_svg(itens, cores, size=168, stroke=30):
    total = sum(v for _, v in itens) or 1
    r = (size - stroke) / 2
    cx = cy = size / 2
    C = 2 * math.pi * r
    off = 0.0
    segs = ""
    for (label, v), cor in zip(itens, cores):
        dash = (v / total) * C
        segs += (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{cor}" '
                 f'stroke-width="{stroke}" stroke-dasharray="{dash:.2f} {C - dash:.2f}" '
                 f'stroke-dashoffset="{-off:.2f}" transform="rotate(-90 {cx} {cy})"/>')
        off += dash
    return (f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
            f'class="donut">{segs}</svg>')


_PALETA = ["#4f46e5", "#0ea5e9", "#14b8a6", "#f59e0b", "#94a3b8", "#a855f7"]


def calcular_indicadores(dados: dict) -> dict:
    """Índices contábeis a partir do balancete (grupos ATIVO/PASSIVO/PL) e da DRE.
    Contas de compensação/comodato ficam de fora do balanço. A separação
    circulante × não circulante é estimada pela descrição das contas."""
    todas = dados.get("todas", [])
    dre = dados.get("dre", {})
    res = dados.get("resultado", {})

    def is_comp(desc):
        return any(k in desc for k in ("COMPENSA", "COMODATO"))

    def natsign(c):
        s = c.get("saldo_atual", 0) or 0.0
        lado = c.get("lado_saldo_atual", "")
        g = c.get("grupo", "")
        natural = "D" if g == "ATIVO" else "C"   # passivo/PL naturais em C
        return s if lado == natural else -s

    IMOB_KW = ("IMOBILIZADO", "IMÓVEIS", "IMOVEIS", "VEÍCULO", "VEICULO", "MÁQUINA", "MAQUINA",
               "MÓVEIS", "MOVEIS", "INSTALA", "EQUIPAMENTO", "FERRAMENTA", "ELETRO", "COMPUTAD")

    ativo_total = passivo_terceiros = pl = 0.0
    estoques = imobilizado = 0.0
    ac = pc = 0.0
    n_nao_circ = 0
    for c in todas:
        if c.get("sintetica"):
            continue
        desc = (c.get("descricao") or "").upper()
        if is_comp(desc):
            continue
        g = c.get("grupo", "")
        sub = c.get("subgrupo")
        v = natsign(c)
        if g == "ATIVO":
            ativo_total += v
            if sub == "CIRCULANTE":
                ac += v
            elif sub == "NAO_CIRCULANTE":
                n_nao_circ += 1
            if any(k in desc for k in ("ESTOQUE", "MERCADORIA")):
                estoques += v
            if any(k in desc for k in IMOB_KW):
                imobilizado += v
        elif g == "PASSIVO":
            passivo_terceiros += v
            if sub == "CIRCULANTE":
                pc += v
        elif g == "PL":
            pl += v

    def div(a, b):
        return round(a / b, 4) if b else None

    receita_liq = dre.get("receita_liquida", 0.0)
    if res.get("tipo", "").upper().startswith("PREJU"):
        resultado = -abs(res.get("valor", 0.0))
    else:
        resultado = abs(res.get("valor", 0.0))

    # liquidez só quando há separação circulante real (achou não circulante e AC/PC > 0)
    tem_split = n_nao_circ > 0 and ac > 0 and pc > 0

    return {
        "balanco": {
            "ativo_total": round(ativo_total, 2),
            "ativo_circulante": round(ac, 2),
            "passivo_circulante": round(pc, 2),
            "estoques": round(estoques, 2),
            "imobilizado": round(imobilizado, 2),
            "passivo_terceiros": round(passivo_terceiros, 2),
            "patrimonio_liquido": round(pl, 2),
        },
        # Estrutura de capital / endividamento (confiáveis)
        "endividamento_geral": div(passivo_terceiros, ativo_total),
        "imobilizacao_pl": div(imobilizado, pl),
        "participacao_capital_proprio": div(pl, ativo_total),
        "composicao_endividamento": div(pc, passivo_terceiros) if tem_split else None,
        # Rentabilidade (confiáveis)
        "margem_bruta": dre.get("margem_bruta"),
        "margem_liquida": dre.get("margem_liquida"),
        "giro_ativo": div(receita_liq, ativo_total),
        "roa": div(resultado, ativo_total),
        "roe": div(resultado, pl),
        # Liquidez (quando o balancete traz a separação circulante)
        "liquidez_disponivel": tem_split,
        "liquidez_corrente": div(ac, pc) if tem_split else None,
        "liquidez_seca": div(ac - estoques, pc) if tem_split else None,
        "resultado": round(resultado, 2),
        "receita_liquida": round(receita_liq, 2),
    }


def gerar_indicadores_html(dados: dict) -> str:
    md = dados["empresa"]
    ind = calcular_indicadores(dados)
    b = ind["balanco"]
    logo = _logo_data_uri()
    logo_html = f'<img class="logo" src="{logo}" alt="Liddera">' if logo else '<div class="logo-fb">LIDDERA</div>'

    def money(v):
        return "R$ " + f"{(v or 0):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")

    def pctv(v, casas=2):
        return "—" if v is None else f"{v:.{casas}f}".replace(".", ",") + "%"

    def ratio(v):
        return "—" if v is None else f"{v:.2f}".replace(".", ",")

    at = b["ativo_total"] or 1
    p_terc = b["passivo_terceiros"]
    p_prop = b["patrimonio_liquido"]
    base = (p_terc + p_prop) or 1
    ang_terc = p_terc / base * 360

    # cartão de indicador com barra
    def card(titulo, valor, sub, frac, cor, faixa=""):
        frac = max(0.0, min(1.0, frac))
        return f"""<div class="ic">
          <div class="ic-t">{titulo}</div>
          <div class="ic-v" style="color:{cor}">{valor}</div>
          <div class="ic-bar"><span style="width:{frac*100:.1f}%;background:{cor}"></span></div>
          <div class="ic-s">{sub}{(' · ' + faixa) if faixa else ''}</div>
        </div>"""

    mb = ind["margem_bruta"] or 0
    ml = ind["margem_liquida"] or 0
    endiv = (ind["endividamento_geral"] or 0) * 100
    capp = (ind["participacao_capital_proprio"] or 0) * 100
    imob = (ind["imobilizacao_pl"] or 0) * 100
    giro = ind["giro_ativo"] or 0
    roa = (ind["roa"] or 0) * 100
    roe = (ind["roe"] or 0) * 100
    lc = ind["liquidez_corrente"]
    ls = ind["liquidez_seca"]
    verde, vermelho, azul, ambr, roxo = "#0ea472", "#e23d4c", "#4f46e5", "#d4711a", "#7c3aed"

    liq_nota = ("" if ind["liquidez_disponivel"] else
                '<div class="nota"><b>Liquidez corrente/seca:</b> não calculadas neste período — o '
                'balancete exportado não traz a separação <b>Circulante × Não Circulante</b>. '
                'Exportando o balancete do Domínio com essa classificação (ou me indicando quais grupos '
                'são circulantes), eu ligo esses índices.</div>')

    liq_secao = ""
    if ind["liquidez_disponivel"]:
        cor_lc = verde if (lc or 0) >= 1 else (ambr if (lc or 0) >= 0.8 else vermelho)
        cor_ls = verde if (ls or 0) >= 1 else (ambr if (ls or 0) >= 0.7 else vermelho)
        liq_secao = f"""
  <div class="h3 sec"><span class="dot"></span>Liquidez</div>
  <div class="grid sec">
    {card('Liquidez corrente', ratio(lc), 'Ativo circulante ÷ passivo circulante', (lc or 0)/1.5, cor_lc, ('confortável' if (lc or 0)>=1 else 'aperto de curto prazo'))}
    {card('Liquidez seca', ratio(ls), 'Sem estoques ÷ passivo circulante', (ls or 0)/1.5, cor_ls)}
    {card('Capital de giro', money((ind['balanco'].get('ativo_circulante',0)) - (ind['balanco'].get('passivo_circulante',0))), 'Ativo circ. − passivo circ.', 0.5, azul if (ind['balanco'].get('ativo_circulante',0)-ind['balanco'].get('passivo_circulante',0))>=0 else vermelho)}
  </div>"""

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Indicadores · {md.get('empresa','')}</title>
<style>
:root{{--navy:#1f2a5a;--orange:#e8632b;--ink:#243056;--ink2:#6b7392;--line:#e7ebf3;--bg:#eef1f7;--pos:#0ea472;--neg:#e23d4c;--card:#fff;--accent:#4f46e5}}
*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:var(--ink);padding:26px}}
.wrap{{max-width:1080px;margin:0 auto}}
@keyframes up{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:none}}}}
@keyframes grow{{from{{width:0}}}}@keyframes draw{{from{{stroke-dashoffset:var(--sl)}}}}
.sec{{opacity:0;animation:up .55s ease forwards}}
.toolbar{{display:flex;align-items:center;gap:10px;margin-bottom:16px}}
.toolbar .tt{{color:var(--accent);font-weight:800}}.toolbar .btn{{margin-left:auto;background:var(--accent);color:#fff;border:0;border-radius:9px;padding:9px 14px;font-size:13px;cursor:pointer}}
header{{display:flex;align-items:center;gap:14px;margin-bottom:16px}}.logo{{width:52px;height:52px;object-fit:contain;border-radius:10px;background:#fff;padding:5px;box-shadow:0 3px 10px rgba(31,42,90,.12)}}
.logo-fb{{font-weight:800;color:var(--accent)}}
.h-txt b{{font-size:18px;color:var(--navy);font-weight:800}}.h-txt div{{font-size:12.5px;color:var(--ink2)}}
.h-right{{margin-left:auto;text-align:right;font-size:12px;color:var(--ink2)}}.h-right b{{color:var(--navy)}}
.band{{background:linear-gradient(120deg,var(--navy),#2b3a72);border-radius:16px;padding:18px 22px;color:#fff;box-shadow:0 10px 28px rgba(31,42,90,.26);margin-bottom:16px}}
.band h1{{font-size:19px;font-weight:800}}.band .meta{{font-size:12px;opacity:.86;margin-top:3px}}
.h3{{font-size:13px;color:var(--navy);font-weight:800;text-transform:uppercase;letter-spacing:.4px;margin:6px 2px 10px;display:flex;align-items:center;gap:8px}}.h3 .dot{{width:8px;height:16px;border-radius:3px;background:var(--orange)}}
.top{{display:grid;grid-template-columns:1.2fr 1fr;gap:14px;margin-bottom:16px}}
.bpcard{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;box-shadow:0 4px 14px rgba(31,42,90,.05)}}
.bprow{{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px dashed var(--line);font-size:14px}}.bprow:last-child{{border-bottom:0}}
.bprow .k{{color:var(--ink2)}}.bprow .v{{font-weight:800}}
.donutwrap{{display:flex;align-items:center;gap:16px}}.donut{{position:relative;width:150px;height:150px;flex:0 0 auto}}
.donut .c{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}}.donut .c .b{{font-size:15px;font-weight:800;color:var(--navy)}}.donut .c .s{{font-size:10.5px;color:var(--ink2)}}
.lg{{display:flex;flex-direction:column;gap:8px;font-size:12.5px}}.lg div{{display:flex;align-items:center;gap:7px}}.lg .dot{{width:11px;height:11px;border-radius:3px}}.lg b{{margin-left:auto}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}}
.ic{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px 16px;box-shadow:0 4px 14px rgba(31,42,90,.05)}}
.ic-t{{font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:var(--ink2);font-weight:700}}
.ic-v{{font-size:24px;font-weight:800;margin:6px 0 8px}}
.ic-bar{{height:8px;background:#eef1f7;border-radius:5px;overflow:hidden}}.ic-bar>span{{display:block;height:100%;border-radius:5px;animation:grow 1s ease}}
.ic-s{{font-size:11.5px;color:var(--ink2);margin-top:7px;line-height:1.4}}
.nota{{background:#fff8f1;border:1px solid #f4d9be;border-radius:12px;padding:13px 16px;font-size:12.5px;color:#7a4a17;line-height:1.5;margin-bottom:14px}}
footer{{text-align:center;color:var(--ink2);font-size:11px;margin-top:18px}}
@media print{{.no-print{{display:none}}body{{padding:0;background:#fff}}.ic,.bpcard,.band{{box-shadow:none}}@page{{size:A4;margin:12mm}}}}
</style></head><body>
<div class="toolbar no-print"><span class="tt">LIDDERA · Indicadores</span><button class="btn" onclick="window.print()">⬇ Exportar PDF</button></div>
<div class="wrap">
  <header class="sec">{logo_html}<div class="h-txt"><b>Liddera | Inteligência em Negócios</b><div>Indicadores econômico-financeiros</div></div>
    <div class="h-right"><div>Período: <b>{md.get('periodo','—')}</b></div><div>CNPJ {md.get('cnpj','—')}</div></div></header>
  <div class="band sec" style="animation-delay:.05s"><h1>{md.get('empresa','—')}</h1><div class="meta">Índices de Liquidez Financeira do Período Atual</div></div>

  <div class="top">
    <div class="bpcard sec" style="animation-delay:.1s"><div class="h3"><span class="dot"></span>Balanço (resumo)</div>
      <div class="bprow"><span class="k">Ativo total</span><span class="v">{money(b['ativo_total'])}</span></div>
      <div class="bprow"><span class="k">Capital de terceiros (passivo)</span><span class="v" style="color:var(--neg)">{money(p_terc)}</span></div>
      <div class="bprow"><span class="k">Capital próprio (patrimônio líquido)</span><span class="v" style="color:var(--pos)">{money(p_prop)}</span></div>
      <div class="bprow"><span class="k">Estoques</span><span class="v">{money(b['estoques'])}</span></div>
      <div class="bprow"><span class="k">Imobilizado</span><span class="v">{money(b['imobilizado'])}</span></div>
    </div>
    <div class="bpcard sec" style="animation-delay:.15s"><div class="h3"><span class="dot"></span>De onde vem o capital</div>
      <div class="donutwrap"><div class="donut"><svg width="150" height="150" viewBox="0 0 150 150">
        <circle cx="75" cy="75" r="55" fill="none" stroke="#eef1f7" stroke-width="22"/>
        <circle cx="75" cy="75" r="55" fill="none" stroke="{vermelho}" stroke-width="22" stroke-dasharray="{ang_terc/360*345.6:.1f} 345.6" transform="rotate(-90 75 75)" style="--sl:{ang_terc/360*345.6:.1f};stroke-dashoffset:0;animation:draw .9s ease backwards"/>
      </svg><div class="c"><div class="b">{pctv(endiv,1)}</div><div class="s">de terceiros</div></div></div>
      <div class="lg"><div><span class="dot" style="background:{vermelho}"></span>Capital de terceiros<b>{pctv(endiv,1)}</b></div>
        <div><span class="dot" style="background:{verde}"></span>Capital próprio<b>{pctv(capp,1)}</b></div></div></div>
    </div>
  </div>

  {liq_secao}
  <div class="h3 sec" style="animation-delay:.2s"><span class="dot"></span>Rentabilidade</div>
  <div class="grid sec" style="animation-delay:.22s">
    {card('Margem bruta', pctv(mb), 'Lucro bruto sobre a receita líquida', mb/40, verde if mb>=0 else vermelho)}
    {card('Margem líquida', pctv(ml), 'Resultado sobre a receita líquida', abs(ml)/10, verde if ml>=0 else vermelho, ('saudável' if ml>=0 else 'resultado negativo'))}
    {card('Giro do ativo', ratio(giro) + '×', 'Receita líquida ÷ ativo total', giro/6, azul)}
    {card('ROA (retorno s/ ativo)', pctv(roa), 'Resultado ÷ ativo total', abs(roa)/15, verde if roa>=0 else vermelho)}
    {card('ROE (retorno s/ PL)', pctv(roe), 'Resultado ÷ patrimônio líquido', abs(roe)/40, verde if roe>=0 else vermelho)}
  </div>

  <div class="h3 sec" style="animation-delay:.28s"><span class="dot"></span>Estrutura de capital</div>
  <div class="grid sec" style="animation-delay:.3s">
    {card('Endividamento geral', pctv(endiv,1), 'Capital de terceiros ÷ ativo', endiv/100, ambr if endiv<80 else vermelho, ('alavancado' if endiv>=70 else 'moderado'))}
    {card('Participação de cap. próprio', pctv(capp,1), 'PL ÷ ativo total', capp/100, verde if capp>=30 else ambr)}
    {card('Imobilização do PL', pctv(imob,1), 'Imobilizado ÷ patrimônio líquido', imob/150, roxo if imob<100 else vermelho, ('acima do PL' if imob>100 else 'dentro do PL'))}
  </div>

  {liq_nota}
  <footer>Gerado pelo FiscoCont+ · Liddera | Inteligência em Negócios Ltda · www.lidderacont.com.br · contas de compensação/comodato fora do balanço</footer>
</div></body></html>"""


def gerar_relatorio_html(dados: dict) -> str:
    md = dados["empresa"]
    r = dados["resultado"]
    conf = dados["conferencia"]
    dre = dados["dre"]
    grupos = agrupar_invertidas(dados)
    total_inv = len(dados["invertidas"])

    res_prej = r["lado"] == "D"

    # ---------- DASHBOARD ----------
    rl = dre["receita_liquida"]
    desp = dre["despesa_total"]
    escala = max(rl, desp) or 1
    barra_rec = rl / escala * 100
    barra_desp = desp / escala * 100

    kpis = f"""
    <div class="kpi"><div class="kl">Receita líquida</div>
      <div class="kv pos">R$ {_brl(rl)}</div><div class="ks">no período</div></div>
    <div class="kpi"><div class="kl">Custos + despesas</div>
      <div class="kv neg">R$ {_brl(desp)}</div>
      <div class="ks">CMV representa {_pct1(dre['peso_cmv'])}% da receita</div></div>
    <div class="kpi"><div class="kl">Resultado</div>
      <div class="kv {'neg' if res_prej else 'pos'}">R$ {_brl(abs(dre['resultado']))}</div>
      <div class="ks">{r['tipo'] or '—'}</div></div>
    <div class="kpi"><div class="kl">Margem líquida</div>
      <div class="kv {'neg' if dre['margem_liquida'] < 0 else 'pos'}">{_pct2(dre['margem_liquida'])}%</div>
      <div class="ks">margem bruta {_pct2(dre['margem_bruta'])}%</div></div>"""

    # composição da receita (donut)
    comp_rec = dre["composicao_receitas"]
    donut = _donut_svg(comp_rec, _PALETA)
    tot_rec = sum(v for _, v in comp_rec) or 1
    leg_rec = ""
    for (label, v), cor in zip(comp_rec, _PALETA):
        leg_rec += (f'<tr><td class="swtd"><span class="sw" style="background:{cor}"></span></td>'
                    f'<td class="ln">{label}</td>'
                    f'<td class="lv">R$ {_brl(v)}</td>'
                    f'<td class="lp">{_pct1(v/tot_rec*100)}%</td></tr>')

    # composição das despesas (barras)
    comp_desp = dre["composicao_despesas"]
    tot_desp = sum(v for _, v in comp_desp) or 1
    bars_desp = ""
    for i, (label, v) in enumerate(comp_desp):
        pct = v / tot_desp * 100
        cor = "#dc3856" if i == 0 else _PALETA[(i) % len(_PALETA)]
        bars_desp += (f'<div class="brow"><div class="brow-top">'
                      f'<span class="bl">{label}</span>'
                      f'<span class="bmeta">R$ {_brl(v)} · {_pct1(pct)}%</span></div>'
                      f'<div class="btrack"><div class="bfill" style="width:{pct:.1f}%;background:{cor}"></div></div></div>')

    dashboard = f"""
  <section class="block">
    <h2 class="btitle">Dashboard — Receitas × Despesas</h2>
    <div class="kpis">{kpis}</div>

    <div class="cmp">
      <div class="cmp-row">
        <span class="cmp-lbl">Receita líquida</span>
        <div class="cmp-track"><div class="cmp-fill pos" style="width:{barra_rec:.1f}%"></div></div>
        <span class="cmp-val">R$ {_brl(rl)}</span>
      </div>
      <div class="cmp-row">
        <span class="cmp-lbl">Custos + despesas</span>
        <div class="cmp-track"><div class="cmp-fill neg" style="width:{barra_desp:.1f}%"></div></div>
        <span class="cmp-val">R$ {_brl(desp)}</span>
      </div>
      <div class="cmp-net {'neg' if res_prej else 'pos'}">
        {r['tipo'] or 'Resultado'} do período: <b>R$ {_brl(abs(dre['resultado']))}</b>
      </div>
    </div>

    <table class="two"><tbody><tr>
      <td class="pane">
        <div class="ptitle">Composição da receita</div>
        <div class="donut-wrap"><div class="donut-c">{donut}</div><table class="legt">{leg_rec}</table></div>
      </td>
      <td class="pane">
        <div class="ptitle">Composição de custos e despesas</div>
        <div class="bart">{bars_desp}</div>
      </td>
    </tr></tbody></table>
  </section>"""

    # ---------- BALANCETE COMPLETO ----------
    grp_nome = {"ATIVO": "Ativo", "PASSIVO": "Passivo", "PL": "Patrimônio Líquido",
                "RESULTADO_DESP": "Custos e Despesas", "RESULTADO_REC": "Receitas"}
    ordem = ["ATIVO", "PASSIVO", "PL", "RESULTADO_DESP", "RESULTADO_REC"]
    linhas_bal = ""
    atual = None
    for c in dados["todas"]:
        if c["grupo"] != atual:
            atual = c["grupo"]
            linhas_bal += (f'<tr class="grh"><td colspan="6">{grp_nome.get(atual, atual)}</td></tr>')
        cls = "sint" if c["sintetica"] else "anal"
        def cell(v, lado):
            if not v:
                return '<td class="num z">0,00</td>'
            dc = f'<span class="dc dc-{lado}">{lado}</span>' if lado else ''
            return f'<td class="num">{_brl(v)}{dc}</td>'
        linhas_bal += (
            f'<tr class="{cls}">'
            f'<td class="cod">{c["codigo"] or ""}</td>'
            f'<td class="nm">{c["descricao"]}</td>'
            f'{cell(c["saldo_anterior"], c["lado_saldo_anterior"])}'
            f'{cell(c["debito"], None)}'
            f'{cell(c["credito"], None)}'
            f'{cell(c["saldo_atual"], c["lado_saldo_atual"])}'
            f'</tr>')

    balancete = f"""
  <section class="block page-break">
    <h2 class="btitle">Balancete completo</h2>
    <table class="bal">
      <thead><tr>
        <th>Cód.</th><th>Descrição da conta</th>
        <th class="num">Saldo anterior</th><th class="num">Débito</th>
        <th class="num">Crédito</th><th class="num">Saldo atual</th>
      </tr></thead>
      <tbody>{linhas_bal}</tbody>
    </table>
  </section>"""

    # ---------- CONFERÊNCIA INTERNA (não sai no PDF) ----------
    secoes_inv = ""
    for g in grupos:
        cor = g["chave"].lower()
        n = len(g["itens"])
        if n:
            rows = ""
            for c in g["itens"]:
                lado = c["lado_saldo_atual"]
                esperado = "Devedor (D)" if c["natureza"] == "D" else "Credor (C)"
                rows += (f'<tr><td class="mono cod">{c["codigo"] or "—"}</td>'
                         f'<td>{c["descricao"]}</td>'
                         f'<td class="mono num"><span class="dc dc-{lado}">{lado}</span>{_brl(c["saldo_atual"])}</td>'
                         f'<td class="mono muted">{esperado}</td></tr>')
            corpo = (f'<table class="inv"><thead><tr><th>Cód.</th><th>Conta</th>'
                     f'<th class="num">Saldo atual</th><th>Lado esperado</th></tr></thead>'
                     f'<tbody>{rows}</tbody></table>')
            resumo = f'<span class="count">{n}</span><span class="soma">Σ R$ {_brl(g["soma"])}</span>'
        else:
            corpo = '<div class="vazio">Nenhuma conta com saldo invertido neste grupo.</div>'
            resumo = '<span class="count zero">0</span>'
        secoes_inv += (f'<div class="grp g-{cor}"><div class="grp-head"><span class="bar"></span>'
                       f'<h3>{g["rotulo"]}</h3>{resumo}</div>{corpo}</div>')

    interna = f"""
  <section class="block no-print internal">
    <h2 class="btitle">Conferência interna — saldos invertidos <span class="uso">uso interno · não incluído no PDF do cliente</span></h2>
    {secoes_inv}
  </section>"""

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Balancete — {md['empresa'] or ''}</title>
<style>
:root{{--bg:#eef1f6;--panel:#fff;--ink:#141b2d;--ink2:#5a6785;--line:#e4e8f0;
--accent:#4f46e5;--pos:#0ea472;--posbg:#e6f7ef;--neg:#dc3856;--negbg:#fdecf0;
--warn:#d4711a;--warnbg:#fdf0e3;--blue:#2563eb;--green:#0ea472;--violet:#7c3aed;
--shadow:0 1px 2px rgba(20,30,60,.05),0 10px 30px rgba(20,30,60,.06);}}
*{{box-sizing:border-box}}html{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
body{{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;padding:0}}
.toolbar{{position:sticky;top:0;z-index:10;background:rgba(255,255,255,.85);backdrop-filter:blur(8px);
border-bottom:1px solid var(--line);padding:12px 24px;display:flex;justify-content:space-between;align-items:center}}
.toolbar .tt{{font-weight:700;color:var(--accent);letter-spacing:.02em}}
.btn{{background:var(--accent);color:#fff;border:0;border-radius:10px;padding:10px 18px;font-size:14px;
font-weight:600;cursor:pointer;box-shadow:0 4px 14px rgba(79,70,229,.3)}}
.btn:hover{{filter:brightness(1.06)}}
.wrap{{max-width:1120px;margin:0 auto;padding:28px 24px 60px}}
.cap{{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:26px}}
.cap h1{{font-size:23px;font-weight:750;letter-spacing:-.01em;margin:0 0 9px}}
.chips{{display:flex;flex-wrap:wrap;gap:8px}}
.chip{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:5px 11px;font-size:12.5px;color:var(--ink2)}}
.chip b{{color:var(--ink);font-weight:600}}
.cap .brand{{text-align:right;font-size:12px;color:var(--ink2)}}.cap .brand .t{{font-weight:800;color:var(--accent);font-size:15px}}
.cap .brand-logo{{width:46px;height:46px;object-fit:contain;display:inline-block;margin-bottom:4px}}
.block{{margin-bottom:30px}}
.btitle{{font-size:16px;font-weight:750;margin:0 0 15px;padding-bottom:9px;border-bottom:2px solid var(--line)}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:13px;margin-bottom:20px}}
.kpi{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px 16px;box-shadow:var(--shadow)}}
.kl{{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink2);font-weight:600;margin-bottom:6px}}
.kv{{font-size:21px;font-weight:800;letter-spacing:-.02em;font-variant-numeric:tabular-nums}}
.kv.pos{{color:var(--pos)}}.kv.neg{{color:var(--neg)}}
.ks{{font-size:11.5px;color:var(--ink2);margin-top:3px}}
.cmp{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;box-shadow:var(--shadow);margin-bottom:16px}}
.cmp-row{{display:grid;grid-template-columns:150px 1fr 160px;align-items:center;gap:14px;margin-bottom:12px}}
.cmp-lbl{{font-size:13px;color:var(--ink2);font-weight:600}}
.cmp-track{{background:#f1f4f9;border-radius:8px;height:26px;overflow:hidden}}
.cmp-fill{{height:100%;border-radius:8px}}.cmp-fill.pos{{background:linear-gradient(90deg,#0ea472,#34d399)}}
.cmp-fill.neg{{background:linear-gradient(90deg,#dc3856,#fb7185)}}
.cmp-val{{text-align:right;font-weight:700;font-variant-numeric:tabular-nums}}
.cmp-net{{margin-top:6px;padding-top:12px;border-top:1px dashed var(--line);font-size:14px;color:var(--ink2)}}
.cmp-net b{{font-size:17px}}.cmp-net.neg b{{color:var(--neg)}}.cmp-net.pos b{{color:var(--pos)}}
.two{{width:100%;border-collapse:separate;border-spacing:16px 0;table-layout:fixed}}
.two>tbody>tr>td.pane{{width:50%;vertical-align:top;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:var(--shadow)}}
.pane{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:var(--shadow)}}
.ptitle{{font-size:13px;font-weight:700;color:var(--ink);margin-bottom:14px}}
.donut-wrap{{display:block}}
.donut-c{{text-align:center;margin-bottom:10px}}
.legt{{width:100%;border-collapse:collapse}}
.legt td{{padding:5px 4px;font-size:12.5px;vertical-align:middle;border:0}}
.legt .swtd{{width:16px}}
.sw{{display:inline-block;width:11px;height:11px;border-radius:3px}}
.legt .ln{{color:var(--ink)}}
.legt .lv{{font-variant-numeric:tabular-nums;color:var(--ink2);text-align:right;white-space:nowrap;padding-right:12px}}
.legt .lp{{font-weight:700;font-variant-numeric:tabular-nums;text-align:right;width:52px}}
.bart{{display:block}}
.brow{{margin-bottom:11px}}
.brow-top{{display:flex;justify-content:space-between;align-items:baseline;font-size:12.5px;margin-bottom:5px}}
.brow .bl{{color:var(--ink)}}
.brow .bmeta{{color:var(--ink2);font-variant-numeric:tabular-nums;white-space:nowrap}}
.btrack{{background:#f1f4f9;border-radius:6px;height:14px;overflow:hidden}}
.bfill{{height:100%;border-radius:6px}}
table{{width:100%;border-collapse:collapse}}
.bal th,.bal td{{padding:6px 10px;font-size:12px;border-bottom:1px solid #eef1f6;text-align:left}}
.bal thead th{{position:sticky;top:56px;background:#f8fafc;color:var(--ink2);font-size:10.5px;
text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--line)}}
.bal .num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.bal .cod{{color:var(--ink2);width:52px;font-variant-numeric:tabular-nums}}
.bal .grh td{{background:var(--accent);color:#fff;font-weight:700;font-size:12px;letter-spacing:.03em;
text-transform:uppercase;padding:7px 10px}}
.bal tr.sint td{{background:#f6f8fc;font-weight:700}}
.bal tr.anal .nm{{padding-left:22px}}
.bal .z{{color:#c4ccdb}}
.dc{{display:inline-block;font-size:9px;font-weight:800;width:13px;height:13px;line-height:13px;text-align:center;
border-radius:3px;margin-left:6px;vertical-align:1px}}
.dc-D{{background:#e6effe;color:var(--blue)}}.dc-C{{background:var(--warnbg);color:var(--warn)}}
.grp{{background:var(--panel);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);margin-bottom:14px;overflow:hidden}}
.grp-head{{display:flex;align-items:center;gap:11px;padding:12px 16px;border-bottom:1px solid var(--line)}}
.grp-head h3{{font-size:14px;margin:0;font-weight:700}}.grp-head .bar{{width:4px;height:16px;border-radius:3px;background:var(--accent)}}
.g-ativo .bar{{background:var(--blue)}}.g-passivo .bar{{background:var(--warn)}}.g-pl .bar{{background:var(--green)}}.g-result .bar{{background:var(--violet)}}
.count{{margin-left:auto;background:#eef1f8;font-weight:700;font-size:12px;padding:2px 10px;border-radius:999px}}
.count.zero{{background:var(--posbg);color:var(--pos)}}.soma{{font-size:12px;color:var(--ink2)}}
.inv th,.inv td{{padding:8px 16px;font-size:13px;border-bottom:1px solid var(--line);text-align:left}}
.inv th{{background:#f8fafc;color:var(--ink2);font-size:10.5px;text-transform:uppercase}}
.inv .num{{text-align:right}}.mono{{font-variant-numeric:tabular-nums}}.muted{{color:var(--ink2)}}
.vazio{{padding:14px 16px;color:var(--ink2)}}
.uso{{font-size:11px;font-weight:500;color:var(--warn);background:var(--warnbg);padding:2px 9px;border-radius:999px;margin-left:8px}}
@media print{{
  .no-print{{display:none!important}}
  body{{background:#fff}}.wrap{{padding:0;max-width:none}}
  .kpi,.cmp,.pane,.grp{{box-shadow:none}}
  .page-break{{break-before:page}}
  .bal thead th{{top:0}}
  @page{{size:A4;margin:12mm}}
}}
</style></head><body>
<div class="toolbar no-print">
  <span class="tt">LIDDERA · Análise de Balancete</span>
  <button class="btn" onclick="window.print()">⬇ Exportar PDF</button>
</div>
<div class="wrap">
  <div class="cap">
    <div>
      <h1>{md['empresa'] or '—'}</h1>
      <div class="chips">
        <span class="chip">CNPJ <b>{md['cnpj'] or '—'}</b></span>
        <span class="chip">Insc. Junta <b>{md['insc_junta'] or '—'}</b></span>
        <span class="chip">Período <b>{md['periodo'] or '—'}</b></span>
      </div>
    </div>
    <div class="brand">{('<img class="brand-logo" src="' + _logo_data_uri() + '" alt="Liddera">') if _logo_data_uri() else '<div class="t">LIDDERA</div>'}<div class="t">LIDDERA</div>Contabilidade<br>Análise de Balancete</div>
  </div>
  {dashboard}
  {balancete}
  {interna}
</div></body></html>"""


def _logo_data_uri() -> str:
    """Logo da Liddera como data URI (embutida no PDF)."""
    import os, base64
    cand = os.environ.get("FISCOCONT_LOGO") or ""
    if not cand or not os.path.exists(cand):
        here = os.path.dirname(os.path.abspath(__file__))
        cand = os.path.join(here, "..", "assets", "liddera-logo.png")
    try:
        with open(cand, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return ""


def gerar_relatorio_invertidas_html(dados: dict) -> str:
    """Relatório dedicado (A4) apenas dos saldos invertidos, com a logo da Liddera."""
    md = dados["empresa"]
    grupos = agrupar_invertidas(dados)
    total = len(dados["invertidas"])
    logo = _logo_data_uri()
    logo_html = (f'<img class="logo" src="{logo}" alt="Liddera">' if logo
                 else '<div class="logo-fb">LIDDERA</div>')

    secoes = ""
    algum = False
    for g in grupos:
        itens = g["itens"]
        if not itens:
            continue
        algum = True
        rows = ""
        for c in itens:
            lado = c["lado_saldo_atual"] or ""
            esperado = "Devedor (D)" if c["natureza"] == "D" else "Credor (C)"
            rows += (f'<tr><td class="cod">{c["codigo"] or "—"}</td>'
                     f'<td class="desc">{c["descricao"]}</td>'
                     f'<td class="num"><span class="dc dc-{lado}">{lado}</span> R$ {_brl(c["saldo_atual"])}</td>'
                     f'<td class="esp">{esperado}</td></tr>')
        secoes += (f'<section class="grp g-{g["chave"].lower()}">'
                   f'<div class="grp-head"><span class="bar"></span><h2>{g["rotulo"]}</h2>'
                   f'<span class="badge">{len(itens)} conta(s)</span>'
                   f'<span class="soma">Σ R$ {_brl(g["soma"])}</span></div>'
                   f'<table class="inv"><thead><tr><th>Cód.</th><th>Conta</th>'
                   f'<th class="num">Saldo atual</th><th>Lado esperado</th></tr></thead>'
                   f'<tbody>{rows}</tbody></table></section>')
    if not algum:
        secoes = ('<div class="vazio">Nenhuma conta analítica com saldo invertido '
                  'neste balancete (contas redutoras "(-)" são desconsideradas).</div>')

    per = md.get("periodo") or "—"
    cnpj = md.get("cnpj") or "—"
    empresa = md.get("empresa") or "—"

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Saldos invertidos — {empresa}</title>
<style>
  :root{{--ink:#26305c;--ink2:#5b6486;--orange:#e8632b;--line:#e6e9f2;--bg:#fff;
    --ativo:#2563eb;--passivo:#e8632b;--pl:#7c3aed;--resultado:#0ea472;}}
  *{{box-sizing:border-box}}
  body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
    color:var(--ink);background:var(--bg);font-size:12px;line-height:1.45}}
  .page{{max-width:820px;margin:0 auto;padding:26px 30px 40px}}
  header{{display:flex;align-items:center;gap:16px;border-bottom:3px solid var(--orange);
    padding-bottom:14px;margin-bottom:6px}}
  .logo{{width:56px;height:56px;object-fit:contain;border-radius:8px}}
  .logo-fb{{font-weight:800;color:var(--orange);font-size:22px;letter-spacing:1px}}
  .htxt h1{{margin:0;font-size:19px;letter-spacing:.2px}}
  .htxt .sub{{color:var(--ink2);font-size:12px;margin-top:2px}}
  .meta{{margin-left:auto;text-align:right;font-size:11.5px;color:var(--ink2)}}
  .meta b{{color:var(--ink)}}
  .intro{{background:#f7f8fc;border:1px solid var(--line);border-radius:10px;
    padding:10px 13px;margin:14px 0 6px;color:var(--ink2)}}
  .intro b{{color:var(--ink)}}
  .kpis{{display:flex;gap:10px;margin:12px 0 4px}}
  .kpi{{flex:1;border:1px solid var(--line);border-radius:10px;padding:10px 12px}}
  .kpi .n{{font-size:20px;font-weight:800}}
  .kpi .l{{font-size:10.5px;color:var(--ink2);text-transform:uppercase;letter-spacing:.4px}}
  .grp{{margin-top:16px;break-inside:avoid}}
  .grp-head{{display:flex;align-items:center;gap:10px;margin-bottom:6px}}
  .grp-head .bar{{width:5px;height:18px;border-radius:3px;background:var(--ink)}}
  .g-ativo .bar{{background:var(--ativo)}} .g-passivo .bar{{background:var(--passivo)}}
  .g-pl .bar{{background:var(--pl)}} .g-resultado .bar{{background:var(--resultado)}}
  .grp-head h2{{margin:0;font-size:14px}}
  .badge{{background:#eef1f8;color:var(--ink2);border-radius:999px;padding:2px 9px;font-size:11px;font-weight:600}}
  .soma{{margin-left:auto;font-weight:700;font-size:12px}}
  table.inv{{width:100%;border-collapse:collapse}}
  table.inv th,table.inv td{{padding:6px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
  table.inv th{{background:#f4f6fb;font-size:10.5px;text-transform:uppercase;letter-spacing:.4px;color:var(--ink2)}}
  table.inv td.cod{{font-family:ui-monospace,Menlo,monospace;color:var(--ink2);white-space:nowrap;width:52px}}
  table.inv td.num,table.inv th.num{{text-align:right;font-family:ui-monospace,Menlo,monospace;white-space:nowrap}}
  table.inv td.esp{{color:var(--ink2);white-space:nowrap;width:110px}}
  .dc{{display:inline-block;min-width:16px;text-align:center;font-weight:800;border-radius:4px;
    padding:0 4px;margin-right:6px;font-size:10.5px}}
  .dc-D{{background:#fde8e8;color:#c0392b}} .dc-C{{background:#e6f4ee;color:#0a7a4b}}
  .vazio{{padding:26px;text-align:center;color:var(--ink2);border:1px dashed var(--line);border-radius:10px;margin-top:16px}}
  footer{{margin-top:26px;padding-top:10px;border-top:1px solid var(--line);
    color:var(--ink2);font-size:10.5px;display:flex;justify-content:space-between}}
  @media print{{.page{{padding:0}} @page{{margin:14mm}}}}
</style></head><body><div class="page">
  <header>
    {logo_html}
    <div class="htxt"><h1>Relatório de Saldos Invertidos</h1>
      <div class="sub">{empresa}</div></div>
    <div class="meta"><div>CNPJ: <b>{cnpj}</b></div><div>Período: <b>{per}</b></div></div>
  </header>
  <div class="intro">Um <b>saldo invertido</b> é uma conta analítica cujo saldo atual está no
    lado oposto à sua natureza (ex.: conta do Ativo com saldo credor). Contas redutoras
    <b>"(-)"</b> são desconsideradas. Vale conferir cada uma antes do fechamento.</div>
  <div class="kpis">
    <div class="kpi"><div class="n">{total}</div><div class="l">Contas invertidas</div></div>
    <div class="kpi"><div class="n">{sum(1 for g in grupos if g["itens"])}</div><div class="l">Grupos afetados</div></div>
  </div>
  {secoes}
  <footer><span>Gerado pelo FiscoCont+ · Liddera | Inteligência em Negócios</span><span>Conferência interna</span></footer>
</div></body></html>"""


def gerar_balancete_completo_html(dados: dict) -> str:
    """Relatório dedicado (A4) do Balancete Completo — todas as contas, com os
    4 valores (saldo anterior/débito/crédito/saldo atual), agrupadas. Faltava
    um export próprio pra essa tela (achado real, reportado pelo Rafael) —
    mesmo estilo visual do relatório de Saldos Invertidos, adaptado pra tabela
    maior com mais colunas."""
    md = dados["empresa"]
    logo = _logo_data_uri()
    logo_html = (f'<img class="logo" src="{logo}" alt="Liddera">' if logo
                 else '<div class="logo-fb">LIDDERA</div>')
    grp_nome = {"ATIVO": "Ativo", "PASSIVO": "Passivo", "PL": "Patrimônio Líquido",
                "RESULTADO_DESP": "Custos e Despesas", "RESULTADO_REC": "Receitas"}

    def cel(v, lado):
        if not v:
            return '<td class="num z">0,00</td>'
        dc = f'<span class="dc dc-{lado}">{lado}</span>' if lado else ''
        return f'<td class="num">{_brl(v)}{dc}</td>'

    rows = ""
    atual = None
    for c in dados.get("todas", []):
        if c["grupo"] != atual:
            atual = c["grupo"]
            rows += f'<tr class="grh"><td colspan="6">{grp_nome.get(atual, atual)}</td></tr>'
        cls = "sint" if c.get("sintetica") else "anal"
        rows += (f'<tr class="{cls}"><td class="cod">{c.get("codigo") or ""}</td>'
                  f'<td class="desc">{c["descricao"]}</td>'
                  f'{cel(c.get("saldo_anterior"), c.get("lado_saldo_anterior"))}'
                  f'{cel(c.get("debito"), None)}{cel(c.get("credito"), None)}'
                  f'{cel(c.get("saldo_atual"), c.get("lado_saldo_atual"))}</tr>')

    per = md.get("periodo") or "—"
    cnpj = md.get("cnpj") or "—"
    empresa = md.get("empresa") or "—"

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Balancete completo — {empresa}</title>
<style>
  :root{{--ink:#26305c;--ink2:#5b6486;--orange:#e8632b;--line:#e6e9f2;--bg:#fff;}}
  *{{box-sizing:border-box}}
  body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
    color:var(--ink);background:var(--bg);font-size:11px;line-height:1.4}}
  .page{{max-width:980px;margin:0 auto;padding:26px 30px 40px}}
  header{{display:flex;align-items:center;gap:16px;border-bottom:3px solid var(--orange);
    padding-bottom:14px;margin-bottom:14px}}
  .logo{{width:56px;height:56px;object-fit:contain;border-radius:8px}}
  .logo-fb{{font-weight:800;color:var(--orange);font-size:22px;letter-spacing:1px}}
  .htxt h1{{margin:0;font-size:19px;letter-spacing:.2px}}
  .htxt .sub{{color:var(--ink2);font-size:12px;margin-top:2px}}
  .meta{{margin-left:auto;text-align:right;font-size:11.5px;color:var(--ink2)}}
  .meta b{{color:var(--ink)}}
  table.bal{{width:100%;border-collapse:collapse}}
  table.bal th,table.bal td{{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
  table.bal th{{background:#f4f6fb;font-size:9.5px;text-transform:uppercase;letter-spacing:.3px;color:var(--ink2)}}
  table.bal td.cod{{font-family:ui-monospace,Menlo,monospace;color:var(--ink2);white-space:nowrap;width:52px}}
  table.bal td.num,table.bal th.num{{text-align:right;font-family:ui-monospace,Menlo,monospace;white-space:nowrap}}
  table.bal td.num.z{{color:#b8bdd0}}
  tr.grh td{{background:#eef1f8;font-weight:800;color:var(--ink);padding-top:10px}}
  tr.sint td{{font-weight:700}}
  .dc{{display:inline-block;min-width:14px;text-align:center;font-weight:800;border-radius:4px;
    padding:0 4px;margin-left:5px;font-size:9.5px}}
  .dc-D{{background:#fde8e8;color:#c0392b}} .dc-C{{background:#e6f4ee;color:#0a7a4b}}
  footer{{margin-top:22px;padding-top:10px;border-top:1px solid var(--line);
    color:var(--ink2);font-size:10.5px;display:flex;justify-content:space-between}}
  @media print{{.page{{padding:0}} @page{{size:A4 landscape;margin:12mm}} tr.grh{{break-after:avoid}}}}
</style></head><body><div class="page">
  <header>
    {logo_html}
    <div class="htxt"><h1>Balancete Completo</h1>
      <div class="sub">{empresa}</div></div>
    <div class="meta"><div>CNPJ: <b>{cnpj}</b></div><div>Período: <b>{per}</b></div>
      <div>{dados.get("totais_conta", 0)} contas ({dados.get("analiticas", 0)} analíticas)</div></div>
  </header>
  <table class="bal"><thead><tr>
    <th>Cód.</th><th>Descrição da conta</th><th class="num">Saldo anterior</th>
    <th class="num">Débito</th><th class="num">Crédito</th><th class="num">Saldo atual</th>
  </tr></thead><tbody>{rows}</tbody></table>
  <footer><span>Gerado pelo FiscoCont+ · Liddera | Inteligência em Negócios</span><span>Conferência interna</span></footer>
</div></body></html>"""



    """Gera os <circle> de um donut a partir de [{'valor','cor'}], em ordem —
    mesmo padrão comprovado do _donut() do fiscal_core.py: dasharray final fixo
    desde o início, animação de "desenhar" via CSS puro (--sl + @keyframes),
    não JS (JS com getTotalLength() tem um problema sutil nesse ambiente)."""
    import math
    total = sum(i["valor"] for i in itens) or 1.0
    C = 2 * math.pi * r
    arcs = ""
    cum = 0.0
    for i, item in enumerate(itens):
        frac = item["valor"] / total
        seglen = max(frac * C, 0.6)
        gap = C - seglen
        rot = -90 + cum * 360
        arcs += (f'<circle class="dseg" data-i="{i}" cx="{cx}" cy="{cy}" r="{r}" fill="none" '
                 f'stroke="{item["cor"]}" stroke-width="{sw}" '
                 f'stroke-dasharray="{seglen:.2f} {gap:.2f}" '
                 f'transform="rotate({rot:.2f} {cx} {cy})" '
                 f'style="animation:dpop .8s {0.14*i:.2f}s cubic-bezier(.22,1.4,.36,1) backwards"/>')
        cum += frac
    return arcs


def _donut_arcs_svg(itens, cx=90, cy=90, r=66, sw=26):
    """Gera só os <circle> (arcos) de um donut a partir de [{'valor','cor'}] —
    usado pelo par Receitas×Despesas da DRE completa (`class="dseg" data-i`,
    compatível com o hover de escopo por grupo). NUNCA existia nesse arquivo —
    achado real: as chamadas abaixo já existiam desde a v0.9.7, apontando pra
    uma função que nunca foi criada aqui (só existe uma parecida, com nome e
    assinatura diferentes, `_donut_svg`, usada em outro lugar) — quebrava
    100% das exportações de DRE (HTML/PDF/Cliente) com NameError."""
    import math as _math
    total = sum(i["valor"] for i in itens) or 1.0
    C = 2 * _math.pi * r
    arcs = ""
    cum = 0.0
    for i, item in enumerate(itens):
        frac = item["valor"] / total
        seglen = max(frac * C, 0.6)
        gap = C - seglen
        rot = -90 + cum * 360
        arcs += (f'<circle class="dseg" data-i="{i}" cx="{cx}" cy="{cy}" r="{r}" fill="none" '
                 f'stroke="{item["cor"]}" stroke-width="{sw}" '
                 f'stroke-dasharray="{seglen:.2f} {gap:.2f}" '
                 f'transform="rotate({rot:.2f} {cx} {cy})" '
                 f'style="animation:dpop .8s {0.14*i:.2f}s cubic-bezier(.22,1.4,.36,1) backwards"/>')
        cum += frac
    return arcs


def gerar_dre_completa_html(dados: dict, cliente: bool = False) -> str:
    """DRE completa, conta por conta, com dashboard de despesas por tipo
    (donut grande, animado, com destaque ao passar o mouse e percentuais).
    `cliente=True`: remove a marca do sistema (FiscoCont+), mostra só
    Liddera | Inteligência em Negócios + o nome da empresa — mesmo padrão já usado nas
    Conferências de Entradas/Saídas."""
    md = dados["empresa"]
    dre = dados["dre"]
    completa = dre.get("completa", [])
    desp_tipo = dre.get("despesas_por_tipo", [])
    logo = _logo_data_uri()
    logo_html = f'<img class="logo" src="{logo}" alt="Liddera">' if logo else '<div class="logo-fb">LIDDERA</div>'

    total_desp = sum(i["valor"] for i in desp_tipo) or 1.0
    arcs = _donut_arcs_svg(desp_tipo)
    segmentos_js = json.dumps([
        {"label": it["label"], "valor": f'R$ {_brl(it["valor"])}', "pct": _pct1(it["valor"] / total_desp * 100) + "%"}
        for it in desp_tipo
    ], ensure_ascii=False)
    legenda = "".join(
        f'<div class="dre2-leg" data-i="{i}"><span class="sw" style="background:{it["cor"]}"></span>'
        f'<span class="lbl">{it["label"]}</span>'
        f'<span class="val">R$ {_brl(it["valor"])}</span>'
        f'<span class="pc" style="background:{it["cor"]}26;color:{it["cor"]}">{_pct1(it["valor"]/total_desp*100)}%</span></div>'
        for i, it in enumerate(desp_tipo)
    )

    # Receitas por tipo — mesmo padrão do despesas acima, reaproveitando o
    # MESMO `_donut_arcs_svg()` (animação idêntica), com paleta verde pra
    # diferenciar visualmente. Dado já vinha pronto em `composicao_receitas`
    # (tuplas label/valor), só faltava cor + virar dict pro donut.
    _cores_receita = ['#0ea472', '#3ddb9e', '#1f9e6e', '#7cd9b5', '#b8ecd8', '#d7f5e8']
    rec_tipo = [
        {"label": label, "valor": round(valor, 2), "cor": _cores_receita[i % len(_cores_receita)]}
        for i, (label, valor) in enumerate(dre.get("composicao_receitas", []))
        if valor > 0.005
    ]
    total_rec = sum(i["valor"] for i in rec_tipo) or 1.0
    arcs_rec = _donut_arcs_svg(rec_tipo)
    segmentos_rec_js = json.dumps([
        {"label": it["label"], "valor": f'R$ {_brl(it["valor"])}', "pct": _pct1(it["valor"] / total_rec * 100) + "%"}
        for it in rec_tipo
    ], ensure_ascii=False)
    legenda_rec = "".join(
        f'<div class="dre2-leg" data-i="{i}" data-grupo="rec"><span class="sw" style="background:{it["cor"]}"></span>'
        f'<span class="lbl">{it["label"]}</span>'
        f'<span class="val">R$ {_brl(it["valor"])}</span>'
        f'<span class="pc" style="background:{it["cor"]}26;color:{it["cor"]}">{_pct1(it["valor"]/total_rec*100)}%</span></div>'
        for i, it in enumerate(rec_tipo)
    )

    SINAL = {"receita_bruta": 1, "deducoes": -1, "receitas_financeiras": 1, "outras_receitas": 1,
             "cmv": -1, "despesas_pessoal": -1, "impostos_taxas": -1, "despesas_administrativas": -1,
             "despesas_financeiras": -1, "tributos_lucro": -1}

    def fmt(v):
        return f'({_brl(abs(v))})' if v < 0 else _brl(v)

    por_macro = []
    for g in completa:
        if not por_macro or por_macro[-1]["macro"] != g["macro"]:
            por_macro.append({"macro": g["macro"], "titulo": MACRO_LABELS.get(g["macro"], g["macro"]), "grupos": [], "total": 0.0})
        por_macro[-1]["grupos"].append(g)
        por_macro[-1]["total"] += g["valor"]

    linhas = ""
    for m in por_macro:
        sinal = SINAL.get(m["macro"], 1)
        linhas += f'<tr class="dre2-macro"><td>{m["titulo"]}</td><td>{fmt(sinal*m["total"])}</td></tr>'
        for g in m["grupos"]:
            if len(m["grupos"]) > 1:
                linhas += f'<tr class="dre2-sub"><td>{g["titulo"]}</td><td>{fmt(sinal*g["valor"])}</td></tr>'
            for f in g["filhos"]:
                linhas += f'<tr class="dre2-acc"><td>{f["descricao"]}</td><td>{fmt(sinal*f["valor"])}</td></tr>'

    res = dre["resultado"]
    prej = res < 0
    margem = dre.get("margem_liquida", 0.0)

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DRE completa · {md["empresa"]}</title>
<style>
*{{box-sizing:border-box;font-family:-apple-system,"Segoe UI",Roboto,Arial,sans-serif}}
body{{background:#eef0f7;margin:0;padding:28px;color:#1f2a5a}}
.wrap{{max-width:1180px;margin:0 auto}}
.hdr{{display:flex;align-items:center;gap:12px;margin-bottom:16px}}
.hdr .logo{{width:40px;height:40px;border-radius:10px}}
.hdr .logo-fb{{width:40px;height:40px;border-radius:10px;background:#1f2a5a;color:#fff;display:flex;
  align-items:center;justify-content:center;font-size:9px;font-weight:800}}
.hdr b{{font-size:15px}}
.hdr div.sub{{font-size:12px;color:#6b7290}}
.band{{background:linear-gradient(120deg,#1f2a5a,#2b3a72);border-radius:16px;padding:20px 26px;color:#fff;margin-bottom:16px}}
.band h1{{margin:0;font-size:18px}}
.band .m{{font-size:12px;color:#c7cbe8;margin-top:3px}}
.card{{background:#fff;border-radius:16px;padding:22px;box-shadow:0 8px 24px rgba(31,42,90,.07);margin-bottom:16px}}
.card h3{{font-size:13px;color:#1f2a5a;margin:0 0 16px}}
.donut-row{{display:flex;align-items:center;gap:30px}}
@keyframes dwrap{{from{{opacity:0;transform:scale(.82)}}to{{opacity:1;transform:scale(1)}}}}
.donut-wrap{{position:relative;flex:0 0 auto;animation:dwrap .65s cubic-bezier(.22,1.4,.36,1) backwards}}
.dseg{{transition:stroke-width .18s, filter .18s;cursor:pointer}}
@keyframes dpop{{from{{opacity:0}}to{{opacity:1}}}}
.dseg.on{{stroke-width:38;filter:brightness(1.08) drop-shadow(0 2px 6px rgba(31,42,90,.35))}}
.dre2-dtip{{position:fixed;pointer-events:none;z-index:9999;background:#1f2a5a;color:#fff;
  font-size:11.5px;font-weight:600;padding:8px 11px;border-radius:9px;box-shadow:0 8px 22px rgba(0,0,0,.28);
  white-space:nowrap;opacity:0;transform:translate(-50%,-115%);transition:opacity .1s;top:0;left:0}}
.dre2-dtip b{{display:block;font-size:12.5px;margin-bottom:2px;font-weight:800}}
.dre2-dtip.show{{opacity:1}}
.donut-total{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
  text-align:center;pointer-events:none;padding:0 30px}}
.donut-total b{{font-size:16px;color:#1f2a5a;line-height:1.2}}
.donut-total span{{font-size:10px;color:#6b7290;margin-top:2px}}
.dre2-2col{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.dre2-tag{{font-size:10.5px;font-weight:800;letter-spacing:.3px;padding:4px 10px;border-radius:999px;display:inline-block;margin-bottom:12px}}
.donut-wrap-sm .dseg.on{{stroke-width:30}}
.donut-total-sm b{{font-size:13px}}
.donut-total-sm span{{font-size:9px}}
@media(max-width:900px){{.dre2-2col{{grid-template-columns:1fr}}
  .donut-group[data-grupo="desp"]{{border-left:none!important;padding-left:0!important;border-top:1px solid var(--line,#eef0f7);padding-top:20px;margin-top:4px}}}}
.dre2-leg{{display:flex;align-items:center;gap:9px;font-size:13px;color:#3a4160;padding:8px 10px;border-radius:9px;
  cursor:pointer;transition:background .15s}}
.dre2-leg.on{{background:#f3f4f9}}
.dre2-leg .sw{{width:11px;height:11px;border-radius:3px;flex:0 0 auto}}
.dre2-leg .lbl{{flex:1}}
.dre2-leg .val{{color:#6b7290;font-weight:600;font-size:12px;white-space:nowrap;margin-left:auto;padding-left:14px}}
.dre2-leg .pc{{font-weight:800;font-size:13px;min-width:54px;text-align:center;padding:4px 10px;border-radius:999px;
  white-space:nowrap;margin-left:10px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
td{{padding:5px 6px}}
tr.dre2-macro td{{font-weight:800;color:#fff;background:#1f2a5a;padding:9px 8px;font-size:11px;text-transform:uppercase;letter-spacing:.3px}}
tr.dre2-macro td:last-child{{text-align:right}}
tr.dre2-sub td{{font-weight:700;color:#1f2a5a;padding:6px 8px 6px 18px;background:#f3f4f9;font-size:10.5px;text-transform:uppercase}}
tr.dre2-sub td:last-child{{text-align:right}}
tr.dre2-acc td:first-child{{padding-left:32px;color:#3a4160}}
tr.dre2-acc td:last-child{{text-align:right;color:#3a4160;font-variant-numeric:tabular-nums}}
tr.dre2-res td{{font-weight:800;color:#fff;background:linear-gradient(120deg,{"#e23d4c" if prej else "#0ea472"},{"#c22e3c" if prej else "#0c8a61"});padding:12px 8px}}
tr.dre2-res td:last-child{{text-align:right;font-size:15px}}
.foot{{text-align:center;color:#6b7290;font-size:11px;margin-top:14px}}
@media(max-width:820px){{.donut-row{{flex-direction:column;align-items:flex-start}}}}
</style></head><body>
<div class="wrap">
  <div class="hdr">{logo_html}<div><b>{'Liddera | Inteligência em Negócios' if cliente else 'FiscoCont+ · Módulo Contábil'}</b><div class="sub">DRE completa, conta por conta</div></div></div>
  <div class="band"><h1>{md["empresa"]}</h1><div class="m">CNPJ {md["cnpj"]} · {md["periodo"]}</div></div>

  <div class="card"><h3>Receitas e despesas por tipo</h3>
    <div class="dre2-2col">
      <div class="donut-group" data-grupo="rec">
        <span class="dre2-tag" style="background:#e6f7f0;color:#0ea472">RECEITAS</span>
        <div class="donut-row">
          <div class="donut-wrap donut-wrap-sm"><svg width="150" height="150" viewBox="0 0 180 180">
            <circle cx="90" cy="90" r="66" fill="none" stroke="#eef1f7" stroke-width="26"/>{arcs_rec}</svg>
            <div class="donut-total donut-total-sm"><b>{_brl_compacto(total_rec)}</b><span>receitas</span></div></div>
          <div style="flex:1">{legenda_rec}</div>
        </div>
      </div>
      <div class="donut-group" data-grupo="desp" style="border-left:1px solid var(--line,#eef0f7);padding-left:20px">
        <span class="dre2-tag" style="background:#fde8ea;color:#e23d4c">DESPESAS</span>
        <div class="donut-row">
          <div class="donut-wrap donut-wrap-sm"><svg width="150" height="150" viewBox="0 0 180 180">
            <circle cx="90" cy="90" r="66" fill="none" stroke="#eef1f7" stroke-width="26"/>{arcs}</svg>
            <div class="donut-total donut-total-sm"><b>{_brl_compacto(total_desp)}</b><span>despesas</span></div></div>
          <div style="flex:1">{legenda}</div>
        </div>
      </div>
    </div>
  </div>

  <div class="card"><h3>Demonstração completa do resultado — todas as contas do balancete</h3>
    <table><tbody>
      {linhas}
      <tr class="dre2-res"><td>{"Prejuízo" if prej else "Lucro"} Líquido do Exercício</td><td>R$ {_brl(abs(res))}</td></tr>
    </tbody></table>
    <div class="foot">Margem líquida: {_pct1(margem)} · {'Liddera | Inteligência em Negócios Ltda' if cliente else 'Gerado pelo FiscoCont+ · Liddera | Inteligência em Negócios Ltda'}</div>
  </div>
</div>
<script>
(function(){{
  var GRUPOS = {{ desp: {segmentos_js}, rec: {segmentos_rec_js} }};
  var tip = document.createElement('div');
  tip.className = 'dre2-dtip';
  tip.innerHTML = '<b></b><span></span>';
  document.body.appendChild(tip);
  var tipB = tip.querySelector('b'), tipS = tip.querySelector('span');
  document.querySelectorAll('.donut-group').forEach(function(group){{
    var dados = GRUPOS[group.dataset.grupo] || [];
    function destaca(i, on){{
      var s = group.querySelector('.dseg[data-i="'+i+'"]');
      var l = group.querySelector('.dre2-leg[data-i="'+i+'"]');
      if (s) s.classList.toggle('on', on);
      if (l) l.classList.toggle('on', on);
    }}
    group.querySelectorAll('.dseg').forEach(function(s){{
      var it = dados[+s.dataset.i];
      s.addEventListener('mouseenter', function(){{ destaca(s.dataset.i, true); }});
      s.addEventListener('mouseleave', function(){{ destaca(s.dataset.i, false); tip.classList.remove('show'); }});
      s.addEventListener('mousemove', function(e){{
        if (!it) return;
        tipB.textContent = it.label;
        tipS.textContent = it.valor + ' · ' + it.pct;
        tip.style.left = e.clientX + 'px';
        tip.style.top = (e.clientY - 10) + 'px';
        tip.classList.add('show');
      }});
    }});
    group.querySelectorAll('.dre2-leg').forEach(function(l){{
      l.addEventListener('mouseenter', function(){{ destaca(l.dataset.i, true); }});
      l.addEventListener('mouseleave', function(){{ destaca(l.dataset.i, false); }});
    }});
  }});
}})();
</script>
</body></html>"""


def gerar_lote_html(resultados: list) -> str:
    """Conferência do Balancete em lote — recebe uma lista de
    {'arquivo': caminho, 'dados': dict (saída de parse_balancete) ou None,
    'erro': str ou None} e monta um painel consolidado, pra escanear rápido
    quais empresas têm pendência num fechamento com várias empresas de uma vez.
    Cada item de sucesso já vem do MESMO `parse_balancete()` usado no import
    individual — não há lógica de parsing nova aqui, só agregação."""
    logo = _logo_data_uri()
    logo_html = f'<img class="logo" src="{logo}" alt="Liddera">' if logo else '<div class="logo-fb">LIDDERA</div>'

    def money(v):
        return "R$ " + f"{(v or 0):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")

    ok = [r for r in resultados if r.get('dados')]
    falhas = [r for r in resultados if not r.get('dados')]
    fecham = [r for r in ok if r['dados'].get('conferencia', {}).get('fecha_com_resultado')]
    nao_fecham = [r for r in ok if r not in fecham]
    com_invertidas = [r for r in ok if len(r['dados'].get('invertidas', [])) > 0]

    total = len(resultados)
    qtd_ok_geral = len([r for r in ok if r in fecham and r not in com_invertidas])
    qtd_atencao = total - qtd_ok_geral

    def status_empresa(r):
        if not r.get('dados'):
            return ('erro', '#e23d4c', 'Falha ao processar')
        d = r['dados']
        fecha = d.get('conferencia', {}).get('fecha_com_resultado')
        qtd_inv = len(d.get('invertidas', []))
        if not fecha:
            return ('atencao', '#e23d4c', 'Não fecha')
        if qtd_inv > 0:
            return ('atencao', '#d4711a', f'{qtd_inv} invertida(s)')
        return ('ok', '#0ea472', 'OK')

    linhas_tabela = ''
    for r in resultados:
        nome_arq = os.path.basename(r.get('arquivo', ''))
        if not r.get('dados'):
            linhas_tabela += (f'<tr><td colspan="6" style="color:#e23d4c">'
                               f'<b>{_esc_html(nome_arq)}</b> — {_esc_html(r.get("erro") or "erro desconhecido")}</td></tr>')
            continue
        d = r['dados']
        md = d['empresa']
        res = d.get('resultado', {})
        conf = d.get('conferencia', {})
        qtd_inv = len(d.get('invertidas', []))
        tipo_sit, cor_sit, txt_sit = status_empresa(r)
        cor_resultado = '#0ea472' if res.get('tipo') == 'LUCRO' else '#e23d4c'
        linhas_tabela += f'''<tr>
          <td><b>{_esc_html(md.get("empresa",""))}</b><div style="font-size:10.5px;color:#8b95bd">{_esc_html(md.get("cnpj",""))}</div></td>
          <td>{_esc_html(md.get("periodo",""))}</td>
          <td style="color:{cor_resultado};font-weight:700">{_esc_html(res.get("tipo","—"))}<br>{money(res.get("valor",0))}</td>
          <td style="text-align:center">{"✓" if conf.get("fecha_com_resultado") else "✗"}</td>
          <td style="text-align:center">{qtd_inv}</td>
          <td><span class="stag" style="background:{cor_sit}1a;color:{cor_sit}">{txt_sit}</span></td>
        </tr>'''

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conferência de Balancetes em Lote · Liddera</title>
<style>
*{{box-sizing:border-box;font-family:-apple-system,"Segoe UI",Roboto,Arial,sans-serif}}
body{{background:#eef0f7;margin:0;padding:26px}}
.wrap{{max-width:1180px;margin:0 auto}}
header{{display:flex;align-items:center;gap:12px;margin-bottom:16px}}
.logo{{width:40px;height:40px;border-radius:10px}}
.logo-fb{{width:40px;height:40px;border-radius:10px;background:#1f2a5a;color:#fff;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800}}
header .h-txt b{{font-size:15px;color:#1f2a5a;display:block}}
header .h-txt div{{font-size:12px;color:#6b7290}}
.band{{background:linear-gradient(120deg,#1f2a5a,#2b3a72);border-radius:16px;padding:24px 28px;color:#fff;margin-bottom:16px;
  display:flex;justify-content:space-between;align-items:center}}
.band h1{{margin:0;font-size:19px}}
.band .sub{{font-size:12.5px;color:#c7cbe8;margin-top:4px}}
.band .total{{text-align:right}}
.band .total .v{{font-size:38px;font-weight:800;line-height:1}}
.band .total .l{{font-size:10.5px;color:#c7cbe8;text-transform:uppercase;letter-spacing:.4px;margin-top:4px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}}
.kpi{{background:#fff;border-radius:14px;padding:16px;box-shadow:0 6px 18px rgba(31,42,90,.06);border-top:3px solid var(--c);text-align:center}}
.kpi .v{{font-size:26px;font-weight:800;color:#1f2a5a}}
.kpi .l{{font-size:10.5px;color:#6b7290;margin-top:3px;text-transform:uppercase;letter-spacing:.3px}}
.card{{background:#fff;border-radius:16px;padding:22px;box-shadow:0 8px 24px rgba(31,42,90,.07)}}
.card h3{{font-size:13px;color:#1f2a5a;margin:0 0 16px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th{{text-align:left;color:#6b7290;font-size:10px;text-transform:uppercase;padding:8px 10px;border-bottom:2px solid #eef0f7}}
td{{padding:10px;border-top:1px solid #f3f4f9;color:#1f2a5a;vertical-align:top}}
.stag{{display:inline-block;font-size:11px;font-weight:700;padding:4px 10px;border-radius:999px}}
.sec{{animation:fadeUp .5s cubic-bezier(.22,1,.36,1) backwards}}
@keyframes fadeUp{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:none}}}}
</style></head><body><div class="wrap">
  <header class="sec">{logo_html}<div class="h-txt"><b>Liddera | Inteligência em Negócios</b><div>Conferência de Balancetes em Lote</div></div></header>
  <div class="band sec" style="animation-delay:.05s">
    <div><h1>{total} balancete(s) processado(s)</h1>
      <div class="sub">{len(ok)} lidos com sucesso{f" · {len(falhas)} com erro" if falhas else ""}</div></div>
    <div class="total"><div class="v" id="numOk">0</div><div class="l">sem pendência</div></div>
  </div>
  <div class="kpis sec" style="animation-delay:.1s">
    <div class="kpi" style="--c:#1f2a5a"><div class="v">{total}</div><div class="l">Total de empresas</div></div>
    <div class="kpi" style="--c:#0ea472"><div class="v">{len(fecham)}</div><div class="l">Fecham (Ativo=Passivo)</div></div>
    <div class="kpi" style="--c:#e23d4c"><div class="v">{len(nao_fecham)}</div><div class="l">Não fecham</div></div>
    <div class="kpi" style="--c:#d4711a"><div class="v">{len(com_invertidas)}</div><div class="l">Com saldo invertido</div></div>
  </div>
  <div class="card sec" style="animation-delay:.15s">
    <h3>Detalhamento por empresa</h3>
    <table><thead><tr><th>Empresa</th><th>Período</th><th>Resultado</th><th>Fecha?</th><th>Invertidas</th><th>Status</th></tr></thead>
    <tbody>{linhas_tabela}</tbody></table>
  </div>
</div>
<script>
(function(){{
  var alvo = {qtd_ok_geral};
  var el = document.getElementById('numOk');
  var t0 = performance.now(), dur = 900;
  function tick(now){{
    var p = Math.min(1, (now-t0)/dur);
    var e = 1-Math.pow(1-p,3);
    el.textContent = Math.round(alvo*e);
    if (p<1) requestAnimationFrame(tick);
  }}
  requestAnimationFrame(tick);
}})();
</script>
</body></html>"""


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) > 1 and sys.argv[1] == "--lote":
        # Conferência em lote: recebe um JSON com a lista de resultados já
        # processados (um por PDF, cada um já rodado individualmente pelo
        # Electron) e só monta o painel consolidado — não reprocessa PDF aqui.
        args = sys.argv[2:]
        i_in = args.index("--entrada")
        with open(args[i_in + 1], "r", encoding="utf-8") as f:
            resultados = json.load(f)
        i_out = args.index("--html")
        out = args[i_out + 1] if i_out + 1 < len(args) else "lote.html"
        with open(out, "w", encoding="utf-8") as f:
            f.write(gerar_lote_html(resultados))
        print("Lote HTML gerado:", out)
        sys.exit(0)

    _src = sys.argv[1]
    if _src.lower().endswith(".json"):
        # já foi parseado antes (ex.: na importação) — reaproveita, sem reabrir o PDF de novo
        with open(_src, "r", encoding="utf-8") as _f:
            d = json.load(_f)
    else:
        d = parse_balancete(_src)
    args = sys.argv[2:]
    try:
        if "indicadores" not in d:
            d["indicadores"] = calcular_indicadores(d)
    except Exception:
        pass
    if "--indicadores-html" in args:
        i = args.index("--indicadores-html")
        out = args[i + 1] if i + 1 < len(args) else "indicadores.html"
        with open(out, "w", encoding="utf-8") as f:
            f.write(gerar_indicadores_html(d))
        print("Indicadores HTML gerado:", out)
        sys.exit(0)
    if "--json" in args:
        # saída de dados para a interface (stdout ou arquivo)
        payload = json.dumps(d, ensure_ascii=False)
        i = args.index("--json")
        out = args[i + 1] if i + 1 < len(args) else None
        if out and not out.startswith("--"):
            with open(out, "w", encoding="utf-8") as f:
                f.write(payload)
        else:
            sys.stdout.write(payload)
        sys.exit(0)
    if "--html" in args:
        i = args.index("--html")
        out = args[i + 1] if i + 1 < len(args) else "relatorio.html"
        with open(out, "w", encoding="utf-8") as f:
            f.write(gerar_relatorio_html(d))
        print("HTML gerado:", out)
        sys.exit(0)
    if "--invertidas-html" in args:
        i = args.index("--invertidas-html")
        out = args[i + 1] if i + 1 < len(args) else "invertidos.html"
        with open(out, "w", encoding="utf-8") as f:
            f.write(gerar_relatorio_invertidas_html(d))
        print("HTML invertidos gerado:", out)
        sys.exit(0)
    if "--balancete-completo-html" in args:
        i = args.index("--balancete-completo-html")
        out = args[i + 1] if i + 1 < len(args) else "balancete-completo.html"
        with open(out, "w", encoding="utf-8") as f:
            f.write(gerar_balancete_completo_html(d))
        print("HTML balancete completo gerado:", out)
        sys.exit(0)
    if "--dre-completa-html" in args:
        i = args.index("--dre-completa-html")
        out = args[i + 1] if i + 1 < len(args) else "dre-completa.html"
        with open(out, "w", encoding="utf-8") as f:
            f.write(gerar_dre_completa_html(d, cliente="--cliente" in args))
        print("HTML DRE completa gerado:", out)
        sys.exit(0)
    md = d["empresa"]
    print("EMPRESA :", md["empresa"])
    print("CNPJ    :", md["cnpj"])
    print("JUNTA   :", md["insc_junta"], "| Abertura:", md["data_abertura"])
    print("PERÍODO :", md["periodo"])
    r = d["resultado"]
    print(f"RESULTADO: {r['tipo']} de R$ {r['valor']:,.2f} ({r['lado']})")
    if d["conferencia"]:
        c = d["conferencia"]
        print(f"CONFERÊNCIA: Ativo {c['ativo']:,.2f} x Passivo {c['passivo']:,.2f} "
              f"| dif {c['diferenca']:,.2f} | fecha c/ resultado: {c['fecha_com_resultado']}")
    print(f"CONTAS: {d['totais_conta']} ({d['analiticas']} analíticas) | "
          f"INVERTIDAS (analíticas, exceto redutoras): {len(d['invertidas'])}")
    print("\nTOP SALDOS INVERTIDOS:")
    for c in d["invertidas"][:25]:
        print(f"  {c['codigo'] or '-':>6}  {c['descricao'][:52]:52} "
              f"{c['saldo_atual']:>16,.2f}{c['lado_saldo_atual']}  [{c['grupo']}]")

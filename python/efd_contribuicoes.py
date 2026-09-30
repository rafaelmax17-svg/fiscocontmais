# -*- coding: utf-8 -*-
"""
Conferência de EFD-Contribuições — lê o arquivo texto (layout SPED, campos
separados por "|") e monta um painel com dashboards e o detalhamento
completo do bloco M (apuração de PIS/COFINS).

Todos os campos abaixo foram conferidos contra um arquivo real (ELTON
DISTRIBUIDORA ATACADISTA LTDA, competência 08/2026, 29-30/09) — os nomes e
posições batem exatamente com o que a Receita gerou, não são só o que a
documentação descreve. Onde a doc pública tem variação (ex.: os últimos
campos de M210/M610, ligados a diferimento — regime pouco comum), o campo
aparece no detalhamento mesmo assim, só sem um rótulo mais específico.
"""
import html as _html
import re


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


def _esc(s):
    return _html.escape('' if s is None else str(s))


def _fmt_data(s):
    m = re.match(r'(\d{2})(\d{2})(\d{4})', s or '')
    return f'{m.group(1)}/{m.group(2)}/{m.group(3)}' if m else (s or '-')


_CST_DESCRICAO = {
    '01': 'Operação Tributável (alíquota básica)', '02': 'Operação Tributável (alíquota diferenciada)',
    '03': 'Operação Tributável (alíquota por unidade de medida)', '04': 'Operação Tributável (monofásica - revenda a alíquota zero)',
    '05': 'Operação Tributável (substituição tributária)', '06': 'Operação Tributável (alíquota zero)',
    '07': 'Operação Isenta da Contribuição', '08': 'Operação sem Incidência da Contribuição',
    '09': 'Operação com Suspensão da Contribuição', '31': 'Não Incidência - Receita Financeira Decreto nº 8.426/2015',
    '49': 'Outras Operações de Saída', '50': 'Op. Geradora de Crédito - Vinculada Exclusivamente a Receita Tributada',
    '51': 'Op. Geradora de Crédito - Vinculada Exclusivamente a Receita Não-Tributada', '52': 'Op. Geradora de Crédito - Vinculada Exclusivamente a Receita de Exportação',
    '53': 'Op. Geradora de Crédito - Vinculada a Receitas Tributadas e Não-Tributadas', '54': 'Op. Geradora de Crédito - Vinculada a Receitas Tributadas e de Exportação',
    '55': 'Op. Geradora de Crédito - Vinculada a Receitas Não-Tributadas e de Exportação', '56': 'Op. Geradora de Crédito - Vinculada a Receitas Tributadas, Não-Tributadas e de Exportação',
    '60': 'Crédito Presumido - Vinculado Exclusivamente a Receita Tributada', '61': 'Crédito Presumido - Vinculado Exclusivamente a Receita Não-Tributada',
    '62': 'Crédito Presumido - Vinculado Exclusivamente a Receita de Exportação', '63': 'Crédito Presumido - Vinculado a Receitas Tributadas e Não-Tributadas',
    '64': 'Crédito Presumido - Vinculado a Receitas Tributadas e de Exportação', '65': 'Crédito Presumido - Vinculado a Receitas Não-Tributadas e de Exportação',
    '66': 'Crédito Presumido - Vinculado a Receitas Tributadas, Não-Tributadas e de Exportação', '67': 'Crédito Presumido - Outras Operações',
    '70': 'Operação de Aquisição sem Direito a Crédito', '71': 'Operação de Aquisição com Isenção',
    '72': 'Operação de Aquisição com Suspensão', '73': 'Operação de Aquisição a Alíquota Zero',
    '74': 'Operação de Aquisição sem Incidência da Contribuição', '75': 'Operação de Aquisição por Substituição Tributária',
    '98': 'Outras Operações de Entrada', '99': 'Outras Operações',
}
_NATUREZA_CREDITO = {
    '01': 'Aquisição de Bens para Revenda', '02': 'Aquisição de Bens Utilizados como Insumo',
    '03': 'Aquisição de Serviços Utilizados como Insumo', '04': 'Energia Elétrica e Térmica',
    '05': 'Aluguéis de Prédios', '06': 'Aluguéis de Máquinas e Equipamentos',
    '07': 'Armazenagem de Mercadoria e Frete na Operação de Venda', '08': 'Contraprestações de Arrendamento Mercantil',
    '09': 'Máquinas e Equipamentos (Ativo Imobilizado)', '10': 'Amortização e Depreciação (Ativo Imobilizado)',
    '11': 'Devolução de Vendas Sujeitas à Incidência Não-Cumulativa', '12': 'Outras Operações com Direito a Crédito',
    '13': 'Atividade de Transporte de Cargas - Subcontratação', '14': 'Atividade Imobiliária - Custo Incorrido de Unidade Construída',
    '15': 'Atividade Imobiliária - Custo Orçado de Unidade Não Concluída', '16': 'Atividade de Prestação de Serviços de Limpeza e Manutenção',
}
_CODIGO_VINCULACAO_CREDITO = {
    '101': 'Vinculado Exclusivamente a Receita Tributada no Mercado Interno', '102': 'Vinculado Exclusivamente a Receita Não-Tributada no Mercado Interno',
    '103': 'Vinculado Exclusivamente a Receita de Exportação', '104': 'Vinculado a Receitas Tributadas e Não-Tributadas no Mercado Interno',
    '105': 'Vinculado a Receitas Tributadas no Mercado Interno e de Exportação', '106': 'Vinculado a Receitas Não-Tributadas no Mercado Interno e de Exportação',
    '107': 'Vinculado a Receitas Tributadas, Não-Tributadas no Mercado Interno e de Exportação', '199': 'Outros Créditos',
    '201': 'Presumido - Vinculado Exclusivamente a Receita Tributada no Mercado Interno', '202': 'Presumido - Vinculado Exclusivamente a Receita Não-Tributada no Mercado Interno',
    '203': 'Presumido - Vinculado Exclusivamente a Receita de Exportação', '299': 'Outros Créditos Presumidos',
}
# Natureza da receita (M410/M810): cada CST usa uma tabela oficial DIFERENTE
# (CST 02/04 -> 4.3.10, 05 -> 4.3.12, 06 -> 4.3.13, 07 -> 4.3.14, 08 -> 4.3.15,
# 09 -> 4.3.16) e o mesmo número significa coisa diferente em cada uma — por isso
# a descrição é SEMPRE procurada pelo par (CST, código). As tabelas vêm da
# Receita (Portal SPED) e são carregadas de efd_tabelas_natureza_dados.py,
# gerado por tools/gerar_tabelas_natureza.py. Código que não existir na tabela
# aparece como "não catalogado" — nunca uma descrição chutada.
try:
    from efd_tabelas_natureza_dados import TABELAS as _TABELAS_NATUREZA
except Exception:
    _TABELAS_NATUREZA = {}
_CST_PARA_TABELA = {'02': '4.3.10', '04': '4.3.10', '05': '4.3.12', '06': '4.3.13', '07': '4.3.14', '08': '4.3.15', '09': '4.3.16'}


def _nat_receita(cod, cst=''):
    """Devolve (texto, detalhe): texto = "código — descrição"; detalhe = tabela/NCM/vigência (tooltip)."""
    cod = cod or ''
    tab = _CST_PARA_TABELA.get((cst or '').zfill(2))
    if not tab or tab not in _TABELAS_NATUREZA:
        return f'{cod or "-"} — (sem tabela oficial carregada para o CST {cst or "?"})', ''
    tb = _TABELAS_NATUREZA[tab]
    it = tb['itens'].get(cod)
    if not it:
        return f'{cod or "-"} — código não catalogado na tabela {tab} carregada ({tb["rotulo"]})', ''
    vig = f"{it['i'] or '-'} a {it['t'] or 'atual'}"
    return f'{cod} — {it["d"]}', f"Tabela {tab} ({tb['rotulo']}) · NCM: {it['n'] or '—'} · Vigência: {vig}"


_IND_DESC_CRED = {'0': 'Desconto da contribuição apurada no próprio período', '1': 'Ressarcimento', '2': 'Compensação'}


def _cst(cod):
    d = _CST_DESCRICAO.get((cod or '').zfill(2), '')
    return f'{cod} — {d}' if d else (cod or '-')


def _natureza(cod):
    d = _NATUREZA_CREDITO.get((cod or '').zfill(2), '')
    return f'{cod} — {d}' if d else (cod or '-')


def _vinculacao(cod):
    d = _CODIGO_VINCULACAO_CREDITO.get(cod, '')
    return f'{cod} — {d}' if d else (cod or '-')


def parse_efd_contribuicoes(caminho):
    """Lê o arquivo (tenta utf-8, cai pra latin-1 — é o padrão do SPED) e
    devolve um dicionário com o cabeçalho e todos os registros do bloco M,
    pra PIS e COFINS, prontos pra virar o painel."""
    for cod in ('utf-8', 'latin-1'):
        try:
            with open(caminho, encoding=cod) as f:
                linhas = [l.rstrip('\r\n') for l in f if l.strip()]
            break
        except UnicodeDecodeError:
            continue

    def registros(prefixo):
        return [l.strip('|').split('|')[1:] for l in linhas if l.startswith(f'|{prefixo}|')]

    def um(prefixo):
        r = registros(prefixo)
        return r[0] if r else []

    def val(campos, i, padrao=''):
        return campos[i] if len(campos) > i else padrao

    c0000 = um('0000')
    empresa = {
        'nome': val(c0000, 6), 'cnpj': val(c0000, 7),
        'periodo_ini': _fmt_data(val(c0000, 4)), 'periodo_fim': _fmt_data(val(c0000, 5)),
    }

    c0111 = um('0111')
    receita_0111 = {
        'mercado_interno': _num(val(c0111, 0)), 'mercado_interno_st': _num(val(c0111, 1)),
        'mercado_interno_monofasica': _num(val(c0111, 2)), 'exportacao': _num(val(c0111, 3)),
        'total': _num(val(c0111, 4)),
    }

    def bloco_credito(pref_credito, pref_detalhe, pref_ajuste_cab, pref_ajuste_det):
        creditos = [{
            'codigo': val(r, 0), 'vinculacao': _vinculacao(val(r, 0)),
            'base_calculo': _num(val(r, 2)), 'aliquota': val(r, 3),
            'valor_credito': _num(val(r, 6)), 'ajuste_acrescimo': _num(val(r, 7)),
            'ajuste_reducao': _num(val(r, 8)), 'credito_diferido': _num(val(r, 9)),
            'credito_disponivel': _num(val(r, 10)),
            'indicador_desconto': _IND_DESC_CRED.get(val(r, 11), val(r, 11)),
            'credito_descontado': _num(val(r, 12)), 'saldo_a_transportar': _num(val(r, 13)),
        } for r in registros(pref_credito)]
        detalhes = [{
            'natureza': val(r, 0), 'natureza_desc': _natureza(val(r, 0)),
            'cst': val(r, 1), 'cst_desc': _cst(val(r, 1)),
            'base_total': _num(val(r, 2)), 'base_cumulativa': _num(val(r, 3)),
            'base_nao_cumulativa': _num(val(r, 4)), 'base_credito': _num(val(r, 5)),
            'base_tributada_mi': _num(val(r, 6)), 'base_nao_tributada_mi': _num(val(r, 7)),
            'base_exportacao': _num(val(r, 8)),
        } for r in registros(pref_detalhe)]
        ajustes = [{
            'tipo': 'Acréscimo' if val(r, 0) == '1' else 'Redução', 'valor': _num(val(r, 1)) * (1 if val(r, 0) == '1' else -1),
            'codigo': val(r, 2), 'documento': val(r, 3), 'descricao': val(r, 4), 'data': _fmt_data(val(r, 5)),
        } for r in registros(pref_ajuste_cab)]
        ajustes_detalhe = [{
            'valor': _num(val(r, 0)), 'cst': val(r, 1), 'base_calculo': _num(val(r, 2)),
            'aliquota': val(r, 3), 'data': _fmt_data(val(r, 4)), 'descricao': val(r, 5),
        } for r in registros(pref_ajuste_det)]
        return creditos, detalhes, ajustes, ajustes_detalhe

    def bloco_debito(pref_consolidacao, pref_codrec, pref_cst, pref_ajuste_cab, pref_ajuste_det):
        c = um(pref_consolidacao)
        consolidacao = {
            'apurado_nao_cumulativo': _num(val(c, 0)), 'credito_descontado': _num(val(c, 1)),
            'credito_descontado_periodo_anterior': _num(val(c, 2)), 'devido_nao_cumulativo': _num(val(c, 3)),
            'retencao_nao_cumulativo': _num(val(c, 4)), 'outras_deducoes_nao_cumulativo': _num(val(c, 5)),
            'a_recolher_nao_cumulativo': _num(val(c, 6)), 'apurado_cumulativo': _num(val(c, 7)),
            'retencao_cumulativo': _num(val(c, 8)), 'outras_deducoes_cumulativo': _num(val(c, 9)),
            'a_recolher_cumulativo': _num(val(c, 10)), 'total_a_recolher': _num(val(c, 11)),
        }
        codigos_receita = [{'codigo_darf': val(r, 1), 'valor': _num(val(r, 2))} for r in registros(pref_codrec)]
        por_cst = [{
            'cst': val(r, 0), 'cst_desc': _cst(val(r, 0)), 'receita_bruta': _num(val(r, 1)),
            'base_calculo': _num(val(r, 2)), 'ajuste_acrescimo_base': _num(val(r, 3)), 'ajuste_reducao_base': _num(val(r, 4)),
            'base_ajustada': _num(val(r, 5)), 'aliquota': val(r, 6), 'contribuicao_apurada': _num(val(r, 9)),
            'ajuste_acrescimo': _num(val(r, 10)), 'ajuste_reducao': _num(val(r, 11)), 'contribuicao_periodo': _num(val(r, 12)),
        } for r in registros(pref_cst)]
        ajustes = [{
            'tipo': 'Acréscimo' if val(r, 0) == '1' else 'Redução', 'valor': _num(val(r, 1)) * (1 if val(r, 0) == '1' else -1),
            'codigo': val(r, 2), 'documento': val(r, 3), 'descricao': val(r, 4), 'data': _fmt_data(val(r, 5)),
        } for r in registros(pref_ajuste_cab)]
        ajustes_detalhe = [{
            'valor': _num(val(r, 0)), 'cst': val(r, 1), 'base_calculo': _num(val(r, 2)),
            'aliquota': val(r, 3), 'data': _fmt_data(val(r, 4)), 'descricao': val(r, 5),
        } for r in registros(pref_ajuste_det)]
        return consolidacao, codigos_receita, por_cst, ajustes, ajustes_detalhe

    def bloco_nao_tributada(pref_cst, pref_natureza):
        por_cst = [{'cst': val(r, 0), 'cst_desc': _cst(val(r, 0)), 'valor': _num(val(r, 1)), 'conta': val(r, 2)} for r in registros(pref_cst)]
        por_natureza, cst_atual = [], ''
        for l in linhas:
            if l.startswith(f'|{pref_cst}|'):
                cst_atual = val(l.strip('|').split('|')[1:], 0)
            elif l.startswith(f'|{pref_natureza}|'):
                r = l.strip('|').split('|')[1:]
                txt, info = _nat_receita(val(r, 0), cst_atual)
                por_natureza.append({'cst': cst_atual, 'natureza': val(r, 0), 'natureza_desc': txt, 'natureza_info': info,
                                     'valor': _num(val(r, 1)), 'conta': val(r, 2)})
        return por_cst, por_natureza

    pis_creditos, pis_detalhe_credito, pis_ajustes_credito, pis_ajustes_credito_det = bloco_credito('M100', 'M105', 'M110', 'M115')
    cofins_creditos, cofins_detalhe_credito, cofins_ajustes_credito, cofins_ajustes_credito_det = bloco_credito('M500', 'M505', 'M510', 'M515')
    pis_consolidacao, pis_codigos_receita, pis_por_cst, pis_ajustes_debito, pis_ajustes_debito_det = bloco_debito('M200', 'M205', 'M210', 'M220', 'M225')
    cofins_consolidacao, cofins_codigos_receita, cofins_por_cst, cofins_ajustes_debito, cofins_ajustes_debito_det = bloco_debito('M600', 'M605', 'M610', 'M620', 'M625')
    pis_nt_cst, pis_nt_natureza = bloco_nao_tributada('M400', 'M410')
    cofins_nt_cst, cofins_nt_natureza = bloco_nao_tributada('M800', 'M810')

    return {
        'empresa': empresa, 'receita_0111': receita_0111,
        'pis': {
            'creditos': pis_creditos, 'detalhe_credito': pis_detalhe_credito,
            'ajustes_credito': pis_ajustes_credito, 'ajustes_credito_detalhe': pis_ajustes_credito_det,
            'consolidacao': pis_consolidacao, 'codigos_receita': pis_codigos_receita, 'por_cst': pis_por_cst,
            'ajustes_debito': pis_ajustes_debito, 'ajustes_debito_detalhe': pis_ajustes_debito_det,
            'nao_tributada_cst': pis_nt_cst, 'nao_tributada_natureza': pis_nt_natureza,
        },
        'cofins': {
            'creditos': cofins_creditos, 'detalhe_credito': cofins_detalhe_credito,
            'ajustes_credito': cofins_ajustes_credito, 'ajustes_credito_detalhe': cofins_ajustes_credito_det,
            'consolidacao': cofins_consolidacao, 'codigos_receita': cofins_codigos_receita, 'por_cst': cofins_por_cst,
            'ajustes_debito': cofins_ajustes_debito, 'ajustes_debito_detalhe': cofins_ajustes_debito_det,
            'nao_tributada_cst': cofins_nt_cst, 'nao_tributada_natureza': cofins_nt_natureza,
        },
    }


# ------------------------------------------------------------------ painel
_CSS = """
:root{--navy:#1f2a5a;--ink:#232a3d;--ink2:#7a8199;--line:#eef0f6}
*{box-sizing:border-box}
body{font-family:'Segoe UI',Arial,sans-serif;margin:0;background:#f4f5fa;color:var(--ink)}
.hdr{background:linear-gradient(120deg,#1f2a5a,#2b3a72);color:#fff;padding:18px 24px;box-shadow:0 6px 16px rgba(31,42,90,.25)}
.card{background:#fff;border:1px solid #eef0f6;border-radius:16px;padding:18px 20px;margin:16px 20px;box-shadow:0 12px 26px rgba(31,42,90,.10),0 2px 6px rgba(31,42,90,.06);overflow-x:auto}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:0;margin:0 20px}
.grid2 .card{margin:16px 10px}
.chart{transition:transform .2s ease,box-shadow .2s ease}
.chart:hover{transform:translateY(-4px);box-shadow:0 18px 34px rgba(31,42,90,.16),0 3px 8px rgba(31,42,90,.08)}
h3{margin:0 0 12px;font-size:14px;display:flex;align-items:center;flex-wrap:wrap;gap:0 10px}
h3::before{content:'';display:inline-block;width:5px;height:17px;border-radius:3px;background:linear-gradient(180deg,#4f62b5,#1f2a5a)}
h3 small{font-size:11px;font-weight:400;color:var(--ink2)}
h2.secao{margin:30px 20px 4px;font-size:17px;color:var(--navy);display:flex;align-items:center;gap:10px}
.dot{width:11px;height:11px;border-radius:50%;display:inline-block;box-shadow:0 3px 6px rgba(31,42,90,.3)}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:24px 20px 14px}
.kpi{position:relative;overflow:hidden;border-radius:14px;padding:21px 12px 15px;text-align:center;background:linear-gradient(180deg,#fff,#f1f4fb);box-shadow:0 1px 0 #fff inset,0 8px 18px rgba(31,42,90,.13),0 2px 4px rgba(31,42,90,.08);transition:transform .2s ease,box-shadow .2s ease}
.kpi::before{content:'';position:absolute;left:0;right:0;top:0;height:4px;background:var(--acc,#1f2a5a)}
.kpi:hover{transform:translateY(-4px);box-shadow:0 1px 0 #fff inset,0 16px 28px rgba(31,42,90,.18),0 3px 6px rgba(31,42,90,.10)}
.kpi b{display:block;font-size:20px;font-weight:800}
.kpi span{font-size:10.5px;color:var(--ink2)}
.kpi.verde{--acc:#0f6e56;background:linear-gradient(180deg,#fff,#eef8f4)}
.kpi.laranja{--acc:#e8632b;background:linear-gradient(180deg,#fff,#fdf1ea)}
.kpi.destaque{--acc:#f5a524;background:linear-gradient(135deg,#1f2a5a,#33469a);transform:translateY(-4px);box-shadow:0 2px 0 rgba(255,255,255,.22) inset,0 16px 28px rgba(31,42,90,.42),0 4px 8px rgba(31,42,90,.25)}
.kpi.destaque b{color:#fff}.kpi.destaque span{color:#c9d0f0}
.kpi.destaque:hover{transform:translateY(-8px)}
.pizza-wrap{filter:drop-shadow(0 14px 12px rgba(31,42,90,.32));flex:0 0 auto}
#efdPizza{display:block;transition:transform 1.1s cubic-bezier(.2,.8,.2,1);transform-origin:110px 110px}
.leg{font-size:13.5px;display:flex;flex-direction:column;gap:13px;min-width:250px;white-space:nowrap}
.leg i{display:inline-block;width:13px;height:13px;border-radius:4px;margin-right:9px;vertical-align:-2px}
.chip{background:#fff;border-radius:999px;padding:4px 13px;font-weight:800;font-size:14px;box-shadow:0 4px 10px rgba(31,42,90,.2);margin-bottom:10px}
.barra{border-radius:10px 10px 4px 4px;height:0;transition:height 1.1s cubic-bezier(.2,.8,.2,1)}
.b-pis{width:108px;background:linear-gradient(90deg,#0f1638 0%,#2b3a72 26%,#4457a8 44%,#1f2a5a 70%,#0f1638 100%);box-shadow:0 12px 18px rgba(31,42,90,.38),inset 0 3px 0 rgba(255,255,255,.3)}
.b-cof{width:108px;background:linear-gradient(90deg,#a93a0a 0%,#e8632b 26%,#ff9f66 44%,#e8632b 70%,#a93a0a 100%);box-shadow:0 12px 18px rgba(232,99,43,.4),inset 0 3px 0 rgba(255,255,255,.35);transition-delay:.15s}
.chao{height:12px;width:132px;border-radius:50%;margin-top:-2px}
.pill{display:inline-block;border-radius:999px;padding:1px 9px;font-size:11px;font-weight:700;color:#fff;margin-right:8px;background:linear-gradient(180deg,#3b4d96,#1f2a5a);box-shadow:0 3px 6px rgba(31,42,90,.28)}
.pill.am{background:linear-gradient(180deg,#f8b955,#e08a0b);box-shadow:0 3px 6px rgba(224,138,11,.35)}
.pill.vd{background:linear-gradient(180deg,#2aa37f,#0f6e56);box-shadow:0 3px 6px rgba(15,110,86,.3)}
.pill.cz{background:linear-gradient(180deg,#9aa1b8,#6b7392);box-shadow:0 3px 6px rgba(107,115,146,.3)}
table.t{width:100%;border-collapse:collapse;font-size:12px;min-width:520px}
.t thead tr{background:linear-gradient(180deg,#2f4090,#1f2a5a)}
.t th{color:#fff;font-size:10px;letter-spacing:.06em;text-transform:uppercase;font-weight:600;padding:9px 10px;white-space:nowrap}
.t th:first-child{border-top-left-radius:8px}.t th:last-child{border-top-right-radius:8px}
.t td{padding:8px 10px;border-bottom:1px solid #eef0f6;vertical-align:middle}
.t tbody tr:nth-child(even){background:#f7f8fc}
.t tbody tr:hover{background:#eef2ff}
.t td.neg{color:#b42318}.t td.zero{color:#a3a9bd}
.t td.cst{min-width:230px}
.t td.vazio{text-align:center;color:var(--ink2);padding:12px}
.t tbody tr.sub{background:linear-gradient(90deg,#e4ebff,#f1f5ff)}
.t tbody tr.sub td{background:transparent;font-weight:700;border-bottom:1px solid #d6e0fb}
.t tbody tr.sub td:first-child{border-left:4px solid #1f2a5a}
.t tbody tr.rec{background:linear-gradient(90deg,#ffe3cf,#fff1e6)}
.t tbody tr.rec td{background:transparent;font-weight:800;color:#8f3a0d;font-size:13.5px;padding:11px 10px}
.t tbody tr.rec td:first-child{border-left:5px solid #e8632b}
.t tbody tr.tot{background:linear-gradient(180deg,#e4ebff,#d3def9)}
.t tbody tr.tot td{background:transparent;border-top:2px solid #1f2a5a;font-weight:800;color:#1f2a5a}
"""

_JS = """
(function(){
  var CX=110, CY=110, R=92, pctNT=__PCTNT__, pctT=__PCTT__;
  function pt(d,r){var a=(d-90)*Math.PI/180;return [CX+(r||R)*Math.cos(a), CY+(r||R)*Math.sin(a)];}
  function fatia(a0,a1){var p0=pt(a0),p1=pt(a1),g=(a1-a0)>180?1:0;
    return 'M'+CX+' '+CY+' L'+p0[0].toFixed(2)+' '+p0[1].toFixed(2)+' A'+R+' '+R+' 0 '+g+' 1 '+p1[0].toFixed(2)+' '+p1[1].toFixed(2)+' Z';}
  var t=document.getElementById('efdFatiaT'), n=document.getElementById('efdFatiaNT'), ang=pctNT/100*360;
  if (pctNT<=0){ document.getElementById('efdCircT').style.display=''; t.style.display='none'; n.style.display='none'; }
  else if (pctNT>=100){ document.getElementById('efdCircNT').style.display=''; t.style.display='none'; n.style.display='none'; }
  else {
    t.setAttribute('d', fatia(ang,360)); n.setAttribute('d', fatia(0,ang));
    var m=(ang/2-90)*Math.PI/180;
    n.setAttribute('transform','translate('+(7*Math.cos(m)).toFixed(2)+','+(7*Math.sin(m)).toFixed(2)+')');
  }
  var lp=pt((ang+360)/2, R*0.55), pct=document.getElementById('efdPct');
  pct.setAttribute('x', lp[0].toFixed(1)); pct.setAttribute('y', (lp[1]+9).toFixed(1));
  requestAnimationFrame(function(){ setTimeout(function(){
    document.getElementById('efdPizza').style.transform='rotate(360deg)';
    var a=document.getElementById('efdColPis'), b=document.getElementById('efdColCofins');
    a.style.height=a.dataset.alvo+'px'; b.style.height=b.dataset.alvo+'px';
  },150); });
  function contar(id, alvo, atraso){
    var el=document.getElementById(id), ini=null;
    function passo(ts){ if(!ini) ini=ts; var p=Math.min(1,(ts-ini)/1100), f=1-Math.pow(1-p,3);
      el.textContent='R$ '+(alvo*f).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});
      if(p<1) requestAnimationFrame(passo); }
    setTimeout(function(){ requestAnimationFrame(passo); }, atraso);
  }
  contar('efdNumPis', __VPIS__, 150);
  contar('efdNumCofins', __VCOF__, 300);
})();
"""


def _cst_pill(cod, curto=False):
    c = (cod or '').strip()
    if not c:
        return '-'
    c = c.zfill(2)
    if c in ('01', '02', '03'):
        cls = ''
    elif c in ('04', '05', '06', '07', '08', '09') or c[:1] == '3':
        cls = ' am'
    elif c[:1] in ('5', '6'):
        cls = ' vd'
    else:
        cls = ' cz'
    desc = _CST_DESCRICAO.get(c, '')
    pill = f'<span class="pill{cls}" title="CST {_esc(c)} — {_esc(desc)}">{_esc(c)}</span>'
    return pill if curto else pill + _esc(desc)


def _linhas_tabela(cabecalhos, linhas, alinhamentos=None, classes=None):
    """<table> do painel. As células já chegam prontas (texto escapado ou HTML);
    negativo vira vermelho, 0,00 vira cinza, e `classes` marca linhas de
    destaque ('sub' = subtotal, 'rec' = a recolher, 'tot' = total)."""
    alinhamentos = alinhamentos or ['l'] * len(cabecalhos)
    mapa = {'l': 'left', 'r': 'right', 'c': 'center'}
    th = ''.join(f'<th style="text-align:{mapa[a]}">{_esc(c)}</th>' for c, a in zip(cabecalhos, alinhamentos))

    def cel(v, a):
        cls = ''
        if isinstance(v, str):
            if re.match(r'^-\d', v):
                cls = ' class="neg"'
            elif v == '0,00':
                cls = ' class="zero"'
            elif v.startswith('<span class="pill'):
                cls = ' class="cst"'
        return f'<td{cls} style="text-align:{mapa[a]}">{v}</td>'

    if linhas:
        corpo = ''
        for i, linha in enumerate(linhas):
            c = classes[i] if classes and classes[i] else ''
            corpo += (f'<tr class="{c}">' if c else '<tr>') + ''.join(cel(v, a) for v, a in zip(linha, alinhamentos)) + '</tr>'
    else:
        corpo = f'<tr><td colspan="{len(cabecalhos)}" class="vazio">Nenhum registro.</td></tr>'
    return f'<table class="t"><thead><tr>{th}</tr></thead><tbody>{corpo}</tbody></table>'


def _secao_tributo(t, nome_tributo, cor):
    cons = t['consolidacao']
    linhas_cons = [
        ('Contribuição apurada (não cumulativa)', cons['apurado_nao_cumulativo']),
        ('Crédito descontado no período', -cons['credito_descontado']),
        ('Crédito descontado de período anterior', -cons['credito_descontado_periodo_anterior']),
        ('Contribuição devida (não cumulativa)', cons['devido_nao_cumulativo']),
        ('Retenções (não cumulativa)', -cons['retencao_nao_cumulativo']),
        ('Outras deduções (não cumulativa)', -cons['outras_deducoes_nao_cumulativo']),
        ('A recolher (não cumulativa)', cons['a_recolher_nao_cumulativo']),
        ('Contribuição apurada (cumulativa)', cons['apurado_cumulativo']),
        ('Retenções (cumulativa)', -cons['retencao_cumulativo']),
        ('Outras deduções (cumulativa)', -cons['outras_deducoes_cumulativo']),
        ('A recolher (cumulativa)', cons['a_recolher_cumulativo']),
    ]
    cls_cons = ['sub' if d.startswith('Contribuição devida') else ('rec' if d.startswith('A recolher') else '') for d, _ in linhas_cons]
    html_cons = _linhas_tabela(['Item', 'Valor (R$)'], [[_esc(d), _brl(v)] for d, v in linhas_cons], ['l', 'r'], cls_cons)
    html_darf = _linhas_tabela(['Código DARF', 'Valor a recolher (R$)'],
                                [[_esc(c['codigo_darf']), _brl(c['valor'])] for c in t['codigos_receita']], ['l', 'r'])
    html_creditos = _linhas_tabela(
        ['Vinculação do crédito', 'Base de cálculo', 'Alíquota', 'Crédito apurado', 'Ajuste (+)', 'Ajuste (-)', 'Disponível', 'Descontado', 'Saldo a transportar'],
        [[_esc(c['vinculacao']), _brl(c['base_calculo']), f"{_esc(c['aliquota'])}%", _brl(c['valor_credito']),
          _brl(c['ajuste_acrescimo']), _brl(c['ajuste_reducao']), _brl(c['credito_disponivel']),
          _brl(c['credito_descontado']), _brl(c['saldo_a_transportar'])] for c in t['creditos']],
        ['l', 'r', 'r', 'r', 'r', 'r', 'r', 'r', 'r'])
    html_detalhe_credito = _linhas_tabela(
        ['Natureza da base de cálculo', 'CST', 'Base total', 'Base não cumulativa', 'Base tributada MI', 'Base não tributada MI', 'Base exportação'],
        [[_esc(d['natureza_desc']), _cst_pill(d['cst']), _brl(d['base_total']), _brl(d['base_nao_cumulativa']),
          _brl(d['base_tributada_mi']), _brl(d['base_nao_tributada_mi']), _brl(d['base_exportacao'])] for d in t['detalhe_credito']],
        ['l', 'l', 'r', 'r', 'r', 'r', 'r'])
    html_ajustes_credito = _linhas_tabela(
        ['Tipo', 'Valor', 'Código', 'Documento', 'Descrição', 'Data'],
        [[a['tipo'], _brl(abs(a['valor'])), _esc(a['codigo']), _esc(a['documento']), _esc(a['descricao']), a['data']] for a in t['ajustes_credito']],
        ['l', 'r', 'l', 'l', 'l', 'l'])

    linhas_cst = [[_cst_pill(c['cst']), _brl(c['receita_bruta']), _brl(c['base_calculo']), _brl(c['ajuste_acrescimo_base']),
                   _brl(c['ajuste_reducao_base']), _brl(c['base_ajustada']), f"{_esc(c['aliquota'])}%", _brl(c['contribuicao_apurada']),
                   _brl(c['ajuste_acrescimo']), _brl(c['ajuste_reducao'])] for c in t['por_cst']]
    cls_cst = None
    if len(t['por_cst']) > 1:
        s = lambda k: sum(c[k] for c in t['por_cst'])
        linhas_cst.append(['Total', _brl(s('receita_bruta')), _brl(s('base_calculo')), _brl(s('ajuste_acrescimo_base')),
                           _brl(s('ajuste_reducao_base')), _brl(s('base_ajustada')), '—', _brl(s('contribuicao_apurada')),
                           _brl(s('ajuste_acrescimo')), _brl(s('ajuste_reducao'))])
        cls_cst = [''] * len(t['por_cst']) + ['tot']
    html_cst = _linhas_tabela(
        ['CST', 'Receita bruta', 'Base de cálculo', 'Ajuste base (+)', 'Ajuste base (-)', 'Base ajustada', 'Alíquota', 'Contribuição apurada', 'Ajuste (+)', 'Ajuste (-)'],
        linhas_cst, ['l', 'r', 'r', 'r', 'r', 'r', 'r', 'r', 'r', 'r'], cls_cst)

    html_ajustes_debito = _linhas_tabela(
        ['Tipo', 'Valor', 'Código', 'Documento', 'Descrição', 'Data'],
        [[a['tipo'], _brl(abs(a['valor'])), _esc(a['codigo']), _esc(a['documento']), _esc(a['descricao']), a['data']] for a in t['ajustes_debito']],
        ['l', 'r', 'l', 'l', 'l', 'l'])

    # detalhamento por documento (M225/M625): pode ter milhares de linhas —
    # resume por CST (o 2º campo desse registro é o CST, não um "código de ajuste")
    det = t['ajustes_debito_detalhe']
    por_cst_aj = {}
    for a in det:
        g = por_cst_aj.setdefault(a['cst'], {'qtd': 0, 'total': 0.0})
        g['qtd'] += 1
        g['total'] += a['valor']
    html_resumo_det = _linhas_tabela(
        ['CST', 'Quantidade de notas', 'Total (R$)'],
        [[_cst_pill(c), str(g['qtd']), _brl(g['total'])] for c, g in sorted(por_cst_aj.items(), key=lambda x: -x[1]['total'])],
        ['l', 'r', 'r'])
    top10 = sorted(det, key=lambda a: -a['valor'])[:10]
    html_top10_det = _linhas_tabela(
        ['Valor', 'CST', 'Base de cálculo', 'Alíquota', 'Data', 'Nota/observação'],
        [[_brl(a['valor']), _esc(a['cst']), _brl(a['base_calculo']), f"{_esc(a['aliquota'])}%", a['data'], _esc(a['descricao'])[:70]] for a in top10],
        ['r', 'l', 'r', 'r', 'l', 'l'])

    linhas_nt = [[_cst_pill(n['cst']), _brl(n['valor']), _esc(n['conta'])] for n in t['nao_tributada_cst']]
    cls_nt = None
    if len(t['nao_tributada_cst']) > 1:
        linhas_nt.append(['Total', _brl(sum(n['valor'] for n in t['nao_tributada_cst'])), ''])
        cls_nt = [''] * len(t['nao_tributada_cst']) + ['tot']
    html_nt_cst = _linhas_tabela(['CST', 'Valor total', 'Conta contábil'], linhas_nt, ['l', 'r', 'l'], cls_nt)

    def cel_nat(n):
        txt = _esc(n['natureza_desc'])
        return f'<span title="{_esc(n["natureza_info"])}">{txt}</span>' if n.get('natureza_info') else txt
    html_nt_nat = _linhas_tabela(
        ['CST', 'Natureza da receita', 'Valor', 'Conta contábil'],
        [[_cst_pill(n['cst'], True), cel_nat(n), _brl(n['valor']), _esc(n['conta'])] for n in t['nao_tributada_natureza']],
        ['l', 'l', 'r', 'l'])

    return f'''
<h2 class="secao"><span class="dot" style="background:{cor}"></span>{nome_tributo}</h2>
<div class="card"><h3>Consolidação da apuração</h3>{html_cons}</div>
<div class="card"><h3>Código de receita (DARF)</h3>{html_darf}</div>
<div class="card"><h3>Créditos apurados, por vinculação</h3>{html_creditos}</div>
<div class="card"><h3>Detalhamento do crédito — por natureza da base e CST</h3>{html_detalhe_credito}</div>
<div class="card"><h3>Ajustes de crédito</h3>{html_ajustes_credito}</div>
<div class="card"><h3>Débito apurado, por CST</h3>{html_cst}</div>
<div class="card"><h3>Ajustes de débito</h3>{html_ajustes_debito}</div>
<div class="card"><h3>Ajustes de débito por nota — resumo por CST {f"<small>({len(det)} nota(s) no total)</small>" if det else ""}</h3>{html_resumo_det}</div>
{f'<div class="card"><h3>10 maiores ajustes de débito por nota</h3>{html_top10_det}</div>' if det else ''}
<div class="card"><h3>Receita não tributada — por CST</h3>{html_nt_cst}</div>
<div class="card"><h3>Receita não tributada — por natureza <small>(descrição conforme as tabelas oficiais da Receita carregadas no sistema — passe o mouse pra ver NCM e vigência)</small></h3>{html_nt_nat}</div>
'''


def _versoes_tabelas_natureza():
    if not _TABELAS_NATUREZA:
        return 'nenhuma tabela oficial de natureza da receita carregada'
    return '; '.join(f"{tab} (CST {'/'.join(v['csts'])}): {v['rotulo']}" for tab, v in sorted(_TABELAS_NATUREZA.items()))


def gerar_painel_efd_html(dados, empresa_nome=''):
    """Painel completo: KPIs, dashboards animados com relevo (pizza tributada ×
    não tributada, colunas PIS × COFINS) e o detalhamento completo do bloco M
    pros dois tributos. É um HTML único e autônomo (vale igual no arquivo exportado)."""
    e = dados['empresa']
    pis, cofins = dados['pis'], dados['cofins']
    receita_total = dados['receita_0111']['total']
    receita_tributada = sum(c['receita_bruta'] for c in pis['por_cst'])
    receita_nao_tributada = sum(n['valor'] for n in pis['nao_tributada_cst'])
    total_credito = sum(c['credito_descontado'] for c in pis['creditos']) + sum(c['credito_descontado'] for c in cofins['creditos'])
    total_debito = (pis['consolidacao']['apurado_nao_cumulativo'] + pis['consolidacao']['apurado_cumulativo']
                    + cofins['consolidacao']['apurado_nao_cumulativo'] + cofins['consolidacao']['apurado_cumulativo'])
    total_a_recolher = pis['consolidacao']['total_a_recolher'] + cofins['consolidacao']['total_a_recolher']

    soma_rec = receita_tributada + receita_nao_tributada
    pct_trib = round(100 * receita_tributada / soma_rec) if soma_rec else 0
    pct_nt = (100 - pct_trib) if soma_rec else 0

    v_pis, v_cof = pis['consolidacao']['total_a_recolher'], cofins['consolidacao']['total_a_recolher']
    maior = max(v_pis, v_cof, 1)
    alt_pis = max(6, round(200 * v_pis / maior)) if v_pis else 0
    alt_cof = max(6, round(200 * v_cof / maior)) if v_cof else 0

    js = (_JS.replace('__PCTNT__', str(pct_nt)).replace('__PCTT__', str(pct_trib))
          .replace('__VPIS__', repr(float(v_pis))).replace('__VCOF__', repr(float(v_cof))))
    titulo = f" · {_esc(empresa_nome)}" if empresa_nome else ""
    cnpj = f" · CNPJ {_esc(e['cnpj'])}" if e['cnpj'] else ''

    corpo = f'''<div class="hdr"><b>FiscoCont+ · Conferência EFD-Contribuições</b><div>{_esc(e['nome'])}{cnpj} · Competência {e['periodo_ini']} a {e['periodo_fim']}</div></div>

<div class="kpis">
  <div class="kpi"><b>R$ {_brl(receita_total)}</b><span>Receita bruta total (reg. 0111)</span></div>
  <div class="kpi verde"><b style="color:#0f6e56">R$ {_brl(total_credito)}</b><span>Crédito total (PIS+COFINS)</span></div>
  <div class="kpi laranja"><b style="color:#e8632b">R$ {_brl(total_debito)}</b><span>Débito total (PIS+COFINS)</span></div>
  <div class="kpi destaque"><b>R$ {_brl(total_a_recolher)}</b><span>Total a recolher</span></div>
</div>

<div class="grid2">
  <div class="card chart"><h3>Receita tributada × não tributada</h3>
    <div style="display:flex;align-items:center;justify-content:center;gap:20px 30px;flex-wrap:wrap;padding:6px 0 4px">
      <div class="pizza-wrap">
        <svg id="efdPizza" width="220" height="220" viewBox="0 0 220 220">
          <defs>
            <radialGradient id="efdgN" cx="38%" cy="30%" r="82%"><stop offset="0" stop-color="#4f62b5"/><stop offset="55%" stop-color="#1f2a5a"/><stop offset="100%" stop-color="#101738"/></radialGradient>
            <radialGradient id="efdgO" cx="60%" cy="22%" r="88%"><stop offset="0" stop-color="#ffb27f"/><stop offset="55%" stop-color="#e8632b"/><stop offset="100%" stop-color="#b3400d"/></radialGradient>
            <radialGradient id="efdgL" cx="34%" cy="24%" r="58%"><stop offset="0" stop-color="#fff" stop-opacity=".38"/><stop offset="100%" stop-color="#fff" stop-opacity="0"/></radialGradient>
          </defs>
          <circle id="efdCircT" cx="110" cy="110" r="92" fill="url(#efdgN)" style="display:none"/>
          <circle id="efdCircNT" cx="110" cy="110" r="92" fill="url(#efdgO)" style="display:none"/>
          <path id="efdFatiaT" d="" fill="url(#efdgN)" stroke="#fff" stroke-width="2.5" stroke-linejoin="round"/>
          <path id="efdFatiaNT" d="" fill="url(#efdgO)" stroke="#fff" stroke-width="2.5" stroke-linejoin="round"/>
          <circle cx="110" cy="110" r="92" fill="url(#efdgL)" style="pointer-events:none"/>
          <text id="efdPct" x="110" y="118" text-anchor="middle" font-size="28" font-weight="800" fill="#fff" stroke="rgba(0,0,0,.28)" stroke-width="3" paint-order="stroke">{pct_trib}%</text>
        </svg>
      </div>
      <div class="leg">
        <div><i style="background:linear-gradient(135deg,#4f62b5,#1f2a5a);box-shadow:0 2px 4px rgba(31,42,90,.35)"></i>Tributada<br><b>R$ {_brl(receita_tributada)}</b></div>
        <div><i style="background:linear-gradient(135deg,#ffb27f,#e8632b);box-shadow:0 2px 4px rgba(232,99,43,.4)"></i>Não tributada<br><b>R$ {_brl(receita_nao_tributada)}</b></div>
      </div>
    </div>
  </div>
  <div class="card chart"><h3>PIS × COFINS — total a recolher</h3>
    <div style="display:flex;align-items:flex-end;justify-content:center;gap:64px;height:292px;padding-top:8px">
      <div style="display:flex;flex-direction:column;align-items:center;height:100%;justify-content:flex-end">
        <span id="efdNumPis" class="chip" style="color:#1f2a5a">R$ 0,00</span>
        <div id="efdColPis" class="barra b-pis" data-alvo="{alt_pis}"></div>
        <div class="chao" style="background:radial-gradient(ellipse at center,rgba(31,42,90,.38),rgba(31,42,90,0) 70%)"></div>
        <span style="font-size:13px;color:var(--ink2);margin-top:4px">PIS</span>
      </div>
      <div style="display:flex;flex-direction:column;align-items:center;height:100%;justify-content:flex-end">
        <span id="efdNumCofins" class="chip" style="color:#e8632b;box-shadow:0 4px 10px rgba(232,99,43,.25)">R$ 0,00</span>
        <div id="efdColCofins" class="barra b-cof" data-alvo="{alt_cof}"></div>
        <div class="chao" style="background:radial-gradient(ellipse at center,rgba(232,99,43,.4),rgba(232,99,43,0) 70%)"></div>
        <span style="font-size:13px;color:var(--ink2);margin-top:4px">COFINS</span>
      </div>
    </div>
  </div>
</div>

{_secao_tributo(pis, 'PIS/PASEP', '#1f2a5a')}
{_secao_tributo(cofins, 'COFINS', '#e8632b')}

<div class="card"><div style="font-size:11px;color:var(--ink2);line-height:1.6">Gerado a partir do arquivo EFD-Contribuições — campos conferidos contra o layout oficial da Receita Federal.<br>Natureza da receita (M410/M810): descrições das tabelas oficiais da Receita carregadas no sistema — {_esc(_versoes_tabelas_natureza())}.</div></div>'''

    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>Conferência EFD-Contribuições{titulo}</title>'
            f'<style>{_CSS}</style></head><body>{corpo}<script>{js}</script></body></html>')

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
from datetime import date, timedelta


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

    c0110 = um('0110')
    regime = {'1': 'não cumulativo', '2': 'cumulativo', '3': 'não cumulativo e cumulativo'}.get(val(c0110, 0), '')

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
        # cada M105/M505 pertence ao M100/M500 que vem antes dele: guarda a alíquota do pai (usada pra
        # estimar o crédito por natureza no relatório do cliente)
        aliq_pai, atual = [], ''
        for l in linhas:
            if l.startswith(f'|{pref_credito}|'):
                campos = l.strip('|').split('|')[1:]
                atual = campos[3] if len(campos) > 3 else ''
            elif l.startswith(f'|{pref_detalhe}|'):
                aliq_pai.append(atual)
        for d_, a_ in zip(detalhes, aliq_pai):
            d_['aliquota'] = a_
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
        'empresa': empresa, 'receita_0111': receita_0111, 'regime': regime,
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
.res-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:4px 0 16px}
.res{background:linear-gradient(180deg,#fff,#f6f8fd);border:1px solid #eef0f6;border-left:5px solid var(--acc,#0f6e56);border-radius:12px;padding:12px 14px;box-shadow:0 6px 14px rgba(31,42,90,.08)}
.res small{display:block;font-size:11px;color:var(--ink2)}
.res b{display:block;font-size:15px;margin:2px 0}
.res.am{--acc:#e8632b}.res.cz{--acc:#888780}
.st{display:inline-block;border-radius:999px;padding:2px 11px;font-size:11px;font-weight:700;white-space:nowrap}
.st.ok{background:#e1f5ee;color:#085041}.st.dif{background:#faeeda;color:#854f0b}.st.fora{background:#f1efe8;color:#444441}.st.so{background:#e6f1fb;color:#0c447c}
.nota{background:linear-gradient(90deg,#fdf1dc,#fff8ea);border:1px solid #efc98f;border-radius:12px;padding:11px 14px;font-size:12px;color:#633806;line-height:1.55;margin:12px 0 0}
.aviso{background:#fcebeb;border:1px solid #f0a5a5;border-radius:12px;padding:11px 14px;font-size:12px;color:#501313;margin:10px 20px;line-height:1.55}
.t td.vazio{text-align:center;color:var(--ink2);padding:12px}
.t tbody tr.sub{background:linear-gradient(90deg,#e4ebff,#f1f5ff)}
.t tbody tr.sub td{background:transparent;font-weight:700;border-bottom:1px solid #d6e0fb}
.t tbody tr.sub td:first-child{border-left:4px solid #1f2a5a}
.t tbody tr.rec{background:linear-gradient(90deg,#ffe3cf,#fff1e6)}
.t tbody tr.rec td{background:transparent;font-weight:800;color:#8f3a0d;font-size:13.5px;padding:11px 10px}
.t tbody tr.rec td:first-child{border-left:5px solid #e8632b}
.t tbody tr.tot{background:linear-gradient(180deg,#e4ebff,#d3def9)}
.t tbody tr.tot td{background:transparent;border-top:2px solid #1f2a5a;font-weight:800;color:#1f2a5a}
/* painel da apuração (bento de vidro claro) */
.bx{position:relative;overflow:hidden;margin:20px 20px 6px;border-radius:22px;padding:20px;background:#f6f8fc;border:1px solid #e2e8f0}
.bx-au{position:absolute;inset:-20%;background:radial-gradient(circle at 12% 18%,#dbe4ff 0,transparent 40%),radial-gradient(circle at 88% 25%,#ffe8d6 0,transparent 36%),radial-gradient(circle at 50% 105%,#e0f2fe 0,transparent 45%);pointer-events:none}
.bx-top{position:relative;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px}
.bx-top b{display:block;font-size:17px;font-weight:800;color:#0f172a}.bx-top small{font-size:12px;color:#64748b}
.bx-tag{font-size:11px;color:#64748b;border:1px solid #e2e8f0;background:#fff;border-radius:8px;padding:5px 10px}
.bx-g{position:relative;display:grid;grid-template-columns:1.3fr 1fr 1fr;gap:12px}
.bx-c{background:rgba(255,255,255,.74);border:1px solid rgba(255,255,255,.95);border-radius:16px;padding:16px 18px;box-shadow:0 1px 2px rgba(15,23,42,.04),0 8px 24px rgba(30,58,138,.06);opacity:0;animation:bxUp .7s cubic-bezier(.2,.8,.2,1) forwards;transition:transform .2s ease,box-shadow .2s ease}
.bx-c:hover{transform:translateY(-3px);box-shadow:0 2px 4px rgba(15,23,42,.05),0 14px 30px rgba(30,58,138,.12)}
.bx-c.w2{grid-column:2 / 4}
.bx-l{font-size:11.5px;color:#64748b;font-weight:600;letter-spacing:.04em;text-transform:uppercase;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.bx-src{font-size:10.5px;color:#94a3b8;background:#f1f5f9;border-radius:6px;padding:2px 6px;text-transform:none;letter-spacing:0;font-weight:600}
.bx-v{font-weight:800;letter-spacing:-.02em;font-variant-numeric:tabular-nums;color:#0f172a;margin-top:4px;white-space:nowrap}
.bx-s{font-size:12px;color:#64748b;margin-top:4px}
.bx-tr{height:6px;border-radius:4px;background:#e2e8f0;margin-top:12px;display:flex;overflow:hidden;gap:3px}
.bx-tr.duo{height:8px;background:none}
.bx-b{height:100%;border-radius:4px;clip-path:inset(0 100% 0 0);animation:bxGrow 1.1s .55s cubic-bezier(.2,.8,.2,1) forwards}
.bx-venc{font-size:11px;font-weight:700;color:#047857;background:#ecfdf5;border-radius:999px;padding:3px 10px;white-space:nowrap;text-transform:none;letter-spacing:0}
.bx-venc.nada{color:#475569;background:#f1f5f9}
.bx-leg{display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;font-size:12px;color:#475569}
.bx-leg i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px}
.bx-dc{display:flex;gap:18px;flex-wrap:wrap;margin-top:10px;padding-top:10px;border-top:1px solid #eef2f7;font-size:12px;color:#64748b}
.bx-dc b{color:#0f172a;font-variant-numeric:tabular-nums}
@keyframes bxUp{from{opacity:0;transform:translateY(18px) scale(.98);filter:blur(5px)}to{opacity:1;transform:none;filter:none}}
@keyframes bxGrow{from{clip-path:inset(0 100% 0 0)}to{clip-path:inset(0 0 0 0)}}
@media (max-width:900px){.bx-g{grid-template-columns:1fr 1fr}.bx-c.w2{grid-column:1 / 3}}
@media (prefers-reduced-motion:reduce){.bx-c{animation:none;opacity:1}.bx-b{animation:none;clip-path:none}}
@media print{.bx-c{animation:none;opacity:1;box-shadow:none}.bx-b{animation:none;clip-path:none}}
"""

_JS = """
(function(){
  var reduz = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.querySelectorAll('.bx-cnt').forEach(function(el, i){
    var alvo = parseFloat(el.getAttribute('data-v')) || 0, ini = null;
    function fmt(v){ return 'R$ ' + v.toLocaleString('pt-BR', {minimumFractionDigits:2, maximumFractionDigits:2}); }
    if (reduz) { el.textContent = fmt(alvo); return; }
    el.textContent = fmt(0);
    function passo(ts){ if(!ini) ini=ts; var p=Math.min(1,(ts-ini)/1300), f=1-Math.pow(1-p,3);
      el.textContent = fmt(p < 1 ? alvo*f : alvo); if(p<1) requestAnimationFrame(passo); }
    setTimeout(function(){ requestAnimationFrame(passo); }, 200 + i*60);
  });
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


def _pascoa(a):
    g = a % 19; c = a // 100; h = (c - c // 4 - (8 * c + 13) // 25 + 19 * g + 15) % 30
    i = h - (h // 28) * (1 - (h // 28) * (29 // (h + 1)) * ((21 - g) // 11))
    j = (a + a // 4 + i + 2 - c + c // 4) % 7
    m = 3 + (i - j + 40) // 44
    return date(a, m, i - j + 28 - 31 * (m // 4))


def _vencimento_darf(periodo_fim):
    """PIS e COFINS: até o dia 25 do mês seguinte ao da apuração; se não for dia útil,
    antecipa para o dia útil anterior (Lei 10.637/2002 art. 10 e Lei 10.833/2003 art. 11).
    Considera fins de semana e feriados nacionais (não conta feriado estadual/municipal)."""
    try:
        d_, m_, a_ = (int(x) for x in periodo_fim.split('/'))
    except (ValueError, AttributeError):
        return ''
    m_ += 1
    if m_ > 12:
        m_, a_ = 1, a_ + 1
    v = date(a_, m_, 25)
    p = _pascoa(a_)
    feriados = {date(a_, mm, dd) for mm, dd in ((1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25))}
    feriados |= {p - timedelta(days=48), p - timedelta(days=47), p - timedelta(days=2), p + timedelta(days=60)}
    while v.weekday() >= 5 or v in feriados:
        v -= timedelta(days=1)
    return v.strftime('%d/%m/%Y')


def gerar_painel_efd_html(dados, empresa_nome='', conferencia_html=''):
    """Painel completo: painel da apuração animado (cartões de vidro com receita, PIS, COFINS,
    tributada × não tributada, total a recolher e vencimento) e o detalhamento completo do bloco M
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
    pct_trib = (100 * receita_tributada / soma_rec) if soma_rec else 0
    v_pis, v_cof = pis['consolidacao']['total_a_recolher'], cofins['consolidacao']['total_a_recolher']
    soma_ar = v_pis + v_cof
    pct_pis = (100 * v_pis / soma_ar) if soma_ar else 0
    pct_cof = (100 * v_cof / soma_ar) if soma_ar else 0
    pctf = lambda v: f'{v:.1f}'.replace('.', ',')
    larg = lambda v: f'{max(v, 1.5):.2f}' if v > 0 else '0'

    js = _JS
    titulo = f" · {_esc(empresa_nome)}" if empresa_nome else ""
    cnpj = f" · CNPJ {_esc(e['cnpj'])}" if e['cnpj'] else ''
    regime = dados.get('regime', '')
    comp = e['periodo_fim'][3:] if len(e['periodo_fim']) == 10 else e['periodo_fim']
    venc = _vencimento_darf(e['periodo_fim'])
    if total_a_recolher <= 0:
        selo = '<span class="bx-venc nada">Nada a recolher</span>'
    elif venc:
        selo = f'<span class="bx-venc" title="Dia 25 do mês seguinte; antecipa se não for dia útil (Lei 10.637/2002 art. 10 e Lei 10.833/2003 art. 11). Feriados estaduais e municipais não são considerados.">● Vencimento {venc}</span>'
    else:
        selo = ''
    cnt = lambda v: f'<span class="bx-cnt" data-v="{float(v)!r}">R$ {_brl(v)}</span>'
    atraso = lambda i: f' style="animation-delay:{i * 0.1:.1f}s"'

    corpo = f'''<div class="hdr"><b>FiscoCont+ · Conferência EFD-Contribuições</b><div>{_esc(e['nome'])}{cnpj} · Competência {e['periodo_ini']} a {e['periodo_fim']}</div></div>

<div class="bx"><div class="bx-au"></div>
  <div class="bx-top"><div><b>Painel da apuração</b><small>EFD-Contribuições · competência {_esc(comp)}{(' · regime ' + _esc(regime)) if regime else ''}</small></div><span class="bx-tag">Valores do arquivo importado</span></div>
  <div class="bx-g">
    <div class="bx-c"{atraso(0)}><div class="bx-l">Receita bruta<span class="bx-src">reg. 0111</span></div>
      <div class="bx-v" style="font-size:30px">{cnt(receita_total)}</div>
      <div class="bx-tr"><div class="bx-b" style="width:{larg(pct_trib)}%;background:#1e3a8a"></div></div>
      <div class="bx-s">{pctf(pct_trib)}% tributada</div></div>
    <div class="bx-c"{atraso(1)}><div class="bx-l">PIS<span class="bx-src">M200</span></div>
      <div class="bx-v" style="font-size:24px;color:#1e3a8a">{cnt(v_pis)}</div>
      <div class="bx-s">{pctf(pct_pis)}% do total a recolher</div></div>
    <div class="bx-c"{atraso(2)}><div class="bx-l">COFINS<span class="bx-src">M600</span></div>
      <div class="bx-v" style="font-size:24px;color:#ea580c">{cnt(v_cof)}</div>
      <div class="bx-s">{pctf(pct_cof)}% do total a recolher</div></div>
    <div class="bx-c"{atraso(3)}>
      <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap">
        <div><div class="bx-l">Tributada<span class="bx-src">M210</span></div><div class="bx-v" style="font-size:19px">{cnt(receita_tributada)}</div></div>
        <div style="text-align:right"><div class="bx-l" style="justify-content:flex-end">Não tributada<span class="bx-src">M400</span></div><div class="bx-v" style="font-size:19px">{cnt(receita_nao_tributada)}</div></div>
      </div>
      <div class="bx-tr" style="background:#cbd5e1"><div class="bx-b" style="width:{larg(pct_trib)}%;background:#1e3a8a"></div></div>
      <div class="bx-leg" style="justify-content:space-between"><span><i style="background:#1e3a8a"></i>{pctf(pct_trib)}% tributada</span><span><i style="background:#cbd5e1"></i>{pctf(100 - pct_trib) if soma_rec else '0,0'}% não tributada</span></div>
      <div class="bx-dc"><span>Total das receitas <b>R$ {_brl(soma_rec)}</b></span></div></div>
    <div class="bx-c w2"{atraso(4)}>
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap"><div class="bx-l">Total a recolher<span class="bx-src">M200 + M600</span></div>{selo}</div>
      <div class="bx-v" style="font-size:38px;margin-top:2px">{cnt(total_a_recolher)}</div>
      <div class="bx-tr duo">{f'<div class="bx-b" style="flex:{v_pis:.2f};background:#1e3a8a"></div>' if v_pis > 0 else ''}{f'<div class="bx-b" style="flex:{v_cof:.2f};background:#ea580c;animation-delay:.7s"></div>' if v_cof > 0 else ''}</div>
      <div class="bx-leg"><span><i style="background:#1e3a8a"></i>PIS R$ {_brl(v_pis)}</span><span><i style="background:#ea580c"></i>COFINS R$ {_brl(v_cof)}</span></div>
      <div class="bx-dc"><span>Débito apurado <b>R$ {_brl(total_debito)}</b></span><span>Crédito descontado <b>R$ {_brl(total_credito)}</b></span></div></div>
  </div>
</div>

{conferencia_html}

{_secao_tributo(pis, 'PIS/PASEP', '#1f2a5a')}
{_secao_tributo(cofins, 'COFINS', '#e8632b')}

<div class="card"><div style="font-size:11px;color:var(--ink2);line-height:1.6">Gerado a partir do arquivo EFD-Contribuições — campos conferidos contra o layout oficial da Receita Federal.<br>Natureza da receita (M410/M810): descrições das tabelas oficiais da Receita carregadas no sistema — {_esc(_versoes_tabelas_natureza())}.</div></div>'''

    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>Conferência EFD-Contribuições{titulo}</title>'
            f'<style>{_CSS}</style></head><body>{corpo}<script>{js}</script></body></html>')

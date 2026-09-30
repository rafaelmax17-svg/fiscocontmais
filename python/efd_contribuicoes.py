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
_NATUREZA_RECEITA = {
    # achado real (pesquisa, 30/09): ao contrário da natureza do crédito
    # (M105, uma tabela só), a natureza da receita em M410/M810 usa tabelas
    # DIFERENTES dependendo do CST (4.3.10 p/ CST04, 4.3.13 p/ CST06, 4.3.14
    # p/ CST07 etc.), cada uma com dezenas de códigos por produto/NCM — não
    # dá pra resumir numa tabela pequena sem arriscar mostrar descrição
    # errada. Por isso mostra só o código mesmo — mais honesto que chutar.
}
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


def _nat_receita(cod):
    d = _NATUREZA_RECEITA.get((cod or '').zfill(3), '')
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
            'valor': _num(val(r, 0)), 'codigo': val(r, 1), 'base_calculo': _num(val(r, 2)),
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
            'valor': _num(val(r, 0)), 'codigo': val(r, 1), 'base_calculo': _num(val(r, 2)),
            'aliquota': val(r, 3), 'data': _fmt_data(val(r, 4)), 'descricao': val(r, 5),
        } for r in registros(pref_ajuste_det)]
        return consolidacao, codigos_receita, por_cst, ajustes, ajustes_detalhe

    def bloco_nao_tributada(pref_cst, pref_natureza):
        por_cst = [{'cst': val(r, 0), 'cst_desc': _cst(val(r, 0)), 'valor': _num(val(r, 1)), 'conta': val(r, 2)} for r in registros(pref_cst)]
        por_natureza = [{'natureza': val(r, 0), 'natureza_desc': _nat_receita(val(r, 0)), 'valor': _num(val(r, 1)), 'conta': val(r, 2)} for r in registros(pref_natureza)]
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
def _linhas_tabela(cabecalhos, linhas, alinhamentos=None):
    """Monta uma <table> simples — cabecalhos: lista de textos; linhas: lista
    de listas de textos já formatados; alinhamentos: 'l'/'r'/'c' por coluna."""
    alinhamentos = alinhamentos or ['l'] * len(cabecalhos)
    mapa = {'l': 'left', 'r': 'right', 'c': 'center'}
    th = ''.join(f'<th style="text-align:{mapa[a]};padding:7px 8px;color:var(--ink2);font-size:9.5px;text-transform:uppercase;white-space:nowrap">{_esc(c)}</th>' for c, a in zip(cabecalhos, alinhamentos))
    corpo = ''.join(
        '<tr>' + ''.join(f'<td style="text-align:{mapa[a]};padding:6px 8px;border-top:1px solid var(--line)">{v}</td>' for v, a in zip(linha, alinhamentos)) + '</tr>'
        for linha in linhas
    ) if linhas else f'<tr><td colspan="{len(cabecalhos)}" style="padding:10px 8px;color:var(--ink2);text-align:center">Nenhum registro.</td></tr>'
    return f'<table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr>{th}</tr></thead><tbody>{corpo}</tbody></table>'


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
    html_cons = _linhas_tabela(['Item', 'Valor (R$)'], [[d, _brl(v)] for d, v in linhas_cons], ['l', 'r'])
    html_darf = _linhas_tabela(['Código DARF', 'Valor a recolher (R$)'],
                                [[c['codigo_darf'], _brl(c['valor'])] for c in t['codigos_receita']], ['l', 'r'])

    html_creditos = _linhas_tabela(
        ['Vinculação do crédito', 'Base de cálculo', 'Alíquota', 'Crédito apurado', 'Ajuste (+)', 'Ajuste (-)', 'Disponível', 'Descontado', 'Saldo a transportar'],
        [[_esc(c['vinculacao']), _brl(c['base_calculo']), f"{c['aliquota']}%", _brl(c['valor_credito']),
          _brl(c['ajuste_acrescimo']), _brl(c['ajuste_reducao']), _brl(c['credito_disponivel']),
          _brl(c['credito_descontado']), _brl(c['saldo_a_transportar'])] for c in t['creditos']],
        ['l', 'r', 'r', 'r', 'r', 'r', 'r', 'r', 'r'])

    html_detalhe_credito = _linhas_tabela(
        ['Natureza da base de cálculo', 'CST', 'Base total', 'Base não cumulativa', 'Base tributada MI', 'Base não tributada MI', 'Base exportação'],
        [[_esc(d['natureza_desc']), _esc(d['cst_desc']), _brl(d['base_total']), _brl(d['base_nao_cumulativa']),
          _brl(d['base_tributada_mi']), _brl(d['base_nao_tributada_mi']), _brl(d['base_exportacao'])] for d in t['detalhe_credito']],
        ['l', 'l', 'r', 'r', 'r', 'r', 'r'])

    ajustes_cred = t['ajustes_credito']
    html_ajustes_credito = _linhas_tabela(
        ['Tipo', 'Valor', 'Código', 'Documento', 'Descrição', 'Data'],
        [[a['tipo'], _brl(abs(a['valor'])), a['codigo'], _esc(a['documento']), _esc(a['descricao']), a['data']] for a in ajustes_cred],
        ['l', 'r', 'l', 'l', 'l', 'l'])

    html_cst = _linhas_tabela(
        ['CST', 'Receita bruta', 'Base de cálculo', 'Ajuste base (+)', 'Ajuste base (-)', 'Base ajustada', 'Alíquota', 'Contribuição apurada', 'Ajuste (+)', 'Ajuste (-)'],
        [[_esc(c['cst_desc']), _brl(c['receita_bruta']), _brl(c['base_calculo']), _brl(c['ajuste_acrescimo_base']),
          _brl(c['ajuste_reducao_base']), _brl(c['base_ajustada']), f"{c['aliquota']}%", _brl(c['contribuicao_apurada']),
          _brl(c['ajuste_acrescimo']), _brl(c['ajuste_reducao'])] for c in t['por_cst']],
        ['l', 'r', 'r', 'r', 'r', 'r', 'r', 'r', 'r', 'r'])

    ajustes_deb = t['ajustes_debito']
    html_ajustes_debito = _linhas_tabela(
        ['Tipo', 'Valor', 'Código', 'Documento', 'Descrição', 'Data'],
        [[a['tipo'], _brl(abs(a['valor'])), a['codigo'], _esc(a['documento']), _esc(a['descricao']), a['data']] for a in ajustes_deb],
        ['l', 'r', 'l', 'l', 'l', 'l'])

    # o detalhamento por documento (M225/M625) pode ter centenas/milhares de
    # linhas — em vez de despejar tudo, resume por código de ajuste e
    # destaca os 10 maiores individualmente, com a contagem total visível
    det = t['ajustes_debito_detalhe']
    por_codigo = {}
    for a in det:
        g = por_codigo.setdefault(a['codigo'], {'qtd': 0, 'total': 0.0})
        g['qtd'] += 1
        g['total'] += a['valor']
    html_resumo_det = _linhas_tabela(
        ['Código do ajuste', 'Quantidade de notas', 'Total (R$)'],
        [[cod, str(g['qtd']), _brl(g['total'])] for cod, g in sorted(por_codigo.items(), key=lambda x: -x[1]['total'])],
        ['l', 'r', 'r'])
    top10 = sorted(det, key=lambda a: -a['valor'])[:10]
    html_top10_det = _linhas_tabela(
        ['Valor', 'Código', 'Base de cálculo', 'Alíquota', 'Data', 'Nota/observação'],
        [[_brl(a['valor']), a['codigo'], _brl(a['base_calculo']), f"{a['aliquota']}%", a['data'], _esc(a['descricao'])[:70]] for a in top10],
        ['r', 'l', 'r', 'r', 'l', 'l'])

    html_nt_cst = _linhas_tabela(
        ['CST', 'Valor total', 'Conta contábil'],
        [[_esc(n['cst_desc']), _brl(n['valor']), _esc(n['conta'])] for n in t['nao_tributada_cst']], ['l', 'r', 'l'])
    html_nt_nat = _linhas_tabela(
        ['Natureza da receita (código)', 'Valor', 'Conta contábil'],
        [[_esc(n['natureza_desc']), _brl(n['valor']), _esc(n['conta'])] for n in t['nao_tributada_natureza']], ['l', 'r', 'l'])

    return f'''
<h2 class="secao"><span class="dot" style="background:{cor}"></span>{nome_tributo}</h2>
<div class="card"><h3>Consolidação da apuração</h3>{html_cons}</div>
<div class="card"><h3>Código de receita (DARF)</h3>{html_darf}</div>
<div class="card"><h3>Créditos apurados, por vinculação</h3>{html_creditos}</div>
<div class="card"><h3>Detalhamento do crédito — por natureza da base e CST</h3>{html_detalhe_credito}</div>
<div class="card"><h3>Ajustes de crédito</h3>{html_ajustes_credito}</div>
<div class="card"><h3>Débito apurado, por CST</h3>{html_cst}</div>
<div class="card"><h3>Ajustes de débito</h3>{html_ajustes_debito}</div>
<div class="card"><h3>Ajustes de débito por nota — resumo por código {f"({len(det)} nota(s) no total)" if det else ""}</h3>{html_resumo_det}</div>
{f'<div class="card"><h3>10 maiores ajustes de débito por nota</h3>{html_top10_det}</div>' if det else ''}
<div class="card"><h3>Receita não tributada — por CST</h3>{html_nt_cst}</div>
<div class="card"><h3>Receita não tributada — por natureza <span style="font-size:11px;font-weight:400;color:var(--ink2)">(código conforme tabelas 4.3.10 a 4.3.16 da Receita — ainda não catalogadas no sistema, por isso só o código)</span></h3>{html_nt_nat}</div>
'''


def gerar_painel_efd_html(dados, empresa_nome=''):
    """Painel completo: KPIs, dashboards animados (pizza tributada×não
    tributada, colunas PIS×COFINS) e o detalhamento completo do bloco M
    pros dois tributos. Layout e paleta seguem o mesmo padrão do painel de
    NFS-e do Baixas DF-e, pra manter a identidade visual do FiscoCont+."""
    e = dados['empresa']
    pis, cofins = dados['pis'], dados['cofins']
    receita_total = dados['receita_0111']['total']
    receita_tributada = sum(c['receita_bruta'] for c in pis['por_cst'])
    receita_nao_tributada = sum(n['valor'] for n in pis['nao_tributada_cst'])
    total_credito = sum(c['credito_descontado'] for c in pis['creditos']) + sum(c['credito_descontado'] for c in cofins['creditos'])
    total_debito = pis['consolidacao']['apurado_nao_cumulativo'] + pis['consolidacao']['apurado_cumulativo'] + \
        cofins['consolidacao']['apurado_nao_cumulativo'] + cofins['consolidacao']['apurado_cumulativo']
    total_a_recolher = pis['consolidacao']['total_a_recolher'] + cofins['consolidacao']['total_a_recolher']

    maior_receita = max(receita_tributada, receita_nao_tributada, 1)
    pct_trib = round(100 * receita_tributada / maior_receita) if receita_tributada >= receita_nao_tributada else round(100 * receita_tributada / (receita_tributada + receita_nao_tributada or 1))
    pct_trib = round(100 * receita_tributada / (receita_tributada + receita_nao_tributada or 1))
    pct_nt = 100 - pct_trib

    maior_pc = max(pis['consolidacao']['total_a_recolher'], cofins['consolidacao']['total_a_recolher'], 1)
    alt_pis = max(6, round(160 * pis['consolidacao']['total_a_recolher'] / maior_pc)) if pis['consolidacao']['total_a_recolher'] else 0
    alt_cofins = max(6, round(160 * cofins['consolidacao']['total_a_recolher'] / maior_pc)) if cofins['consolidacao']['total_a_recolher'] else 0

    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Conferência EFD-Contribuições{f" · {_esc(empresa_nome)}" if empresa_nome else ""}</title>
<style>
:root{{--navy:#1f2a5a;--ink:#232a3d;--ink2:#7a8199;--line:#eef0f6;--bg:#f4f6fb}}
*{{box-sizing:border-box}} body{{font-family:'Segoe UI',Arial,sans-serif;margin:0;background:#f4f5fa;color:var(--ink)}}
.hdr{{background:linear-gradient(120deg,#1f2a5a,#2b3a72);color:#fff;padding:18px 24px}}
.card{{background:#fff;border-radius:14px;padding:18px 20px;margin:14px 20px;box-shadow:0 4px 14px rgba(31,42,90,.06);overflow-x:auto}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:0;margin:0 20px}}
.grid2 .card{{margin:14px 10px}}
h3{{margin:0 0 12px;font-size:14px}}
h2.secao{{margin:26px 20px 4px;font-size:16px;color:var(--navy);display:flex;align-items:center;gap:8px}}
.dot{{width:9px;height:9px;border-radius:50%;background:var(--navy);display:inline-block}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 20px}}
.kpi{{background:#fff;border-radius:14px;padding:16px;text-align:center;box-shadow:0 4px 14px rgba(31,42,90,.06)}}
.kpi b{{display:block;font-size:20px}}.kpi span{{font-size:10.5px;color:var(--ink2)}}
table{{min-width:520px}}
</style></head><body>
<div class="hdr"><b>FiscoCont+ · Conferência EFD-Contribuições</b><div>{_esc(e['nome'])}{f" · CNPJ {_esc(e['cnpj'])}" if e['cnpj'] else ''} · Competência {e['periodo_ini']} a {e['periodo_fim']}</div></div>

<div class="kpis">
  <div class="kpi"><b>R$ {_brl(receita_total)}</b><span>Receita bruta total (reg. 0111)</span></div>
  <div class="kpi"><b style="color:#0f6e56">R$ {_brl(total_credito)}</b><span>Crédito total (PIS+COFINS)</span></div>
  <div class="kpi"><b style="color:#e8632b">R$ {_brl(total_debito)}</b><span>Débito total (PIS+COFINS)</span></div>
  <div class="kpi"><b>R$ {_brl(total_a_recolher)}</b><span>Total a recolher</span></div>
</div>

<div class="grid2">
  <div class="card"><h3>Receita tributada × não tributada</h3>
    <div style="display:flex;align-items:center;gap:20px">
      <svg id="efdPizza" width="150" height="150" viewBox="0 0 150 150" style="transform-origin:75px 75px;transition:transform 1.1s cubic-bezier(.2,.8,.2,1);flex:0 0 auto">
        <circle cx="75" cy="75" r="62" fill="#1f2a5a"/>
        <path id="efdFatiaNT" d="M75 75 L75 13 A62 62 0 0 1 75 13 Z" fill="#e8632b"/>
        <text x="60" y="70" font-size="16" font-weight="700" fill="#fff">{pct_trib}%</text>
      </svg>
      <div style="font-size:12.5px;display:flex;flex-direction:column;gap:9px">
        <span style="display:flex;align-items:center;gap:7px"><span style="width:11px;height:11px;border-radius:3px;background:#1f2a5a"></span>Tributada<b style="margin-left:auto;padding-left:16px">R$ {_brl(receita_tributada)}</b></span>
        <span style="display:flex;align-items:center;gap:7px"><span style="width:11px;height:11px;border-radius:3px;background:#e8632b"></span>Não tributada<b style="margin-left:auto;padding-left:16px">R$ {_brl(receita_nao_tributada)}</b></span>
      </div>
    </div>
  </div>
  <div class="card"><h3>PIS × COFINS — total a recolher</h3>
    <div style="display:flex;align-items:flex-end;justify-content:center;gap:48px;height:200px;padding-top:10px">
      <div style="display:flex;flex-direction:column;align-items:center;gap:8px;height:100%;justify-content:flex-end">
        <span id="efdNumPis" style="font-size:15px;font-weight:800;color:var(--navy)">R$ 0,00</span>
        <div id="efdColPis" style="width:80px;height:0px;background:#1f2a5a;border-radius:8px 8px 0 0;transition:height 1.1s cubic-bezier(.2,.8,.2,1)" data-alvo="{alt_pis}"></div>
        <span style="font-size:12px;color:var(--ink2)">PIS</span>
      </div>
      <div style="display:flex;flex-direction:column;align-items:center;gap:8px;height:100%;justify-content:flex-end">
        <span id="efdNumCofins" style="font-size:15px;font-weight:800;color:#e8632b">R$ 0,00</span>
        <div id="efdColCofins" style="width:80px;height:0px;background:#e8632b;border-radius:8px 8px 0 0;transition:height 1.1s cubic-bezier(.2,.8,.2,1) .15s" data-alvo="{alt_cofins}"></div>
        <span style="font-size:12px;color:var(--ink2)">COFINS</span>
      </div>
    </div>
  </div>
</div>

{_secao_tributo(pis, 'PIS/PASEP', '#1f2a5a')}
{_secao_tributo(cofins, 'COFINS', '#e8632b')}

<div class="card"><div style="font-size:11px;color:var(--ink2)">Gerado a partir do arquivo EFD-Contribuições — campos conferidos contra o layout oficial da Receita Federal. A "natureza da receita" (M410/M810) usa tabelas específicas por CST que ainda não estão catalogadas no sistema; por isso aparece só o código.</div></div>

<script>
(function(){{
  var pctNT = {pct_nt};
  if (pctNT > 0) {{
    var CX=75, CY=75, R=62;
    var ang = pctNT/100*360;
    var rad = (ang-90)*Math.PI/180;
    var x = CX + R*Math.cos(rad), y = CY + R*Math.sin(rad);
    var grandeArco = ang > 180 ? 1 : 0;
    var d = ang >= 359.9
      ? 'M '+CX+' '+(CY-R)+' A '+R+' '+R+' 0 1 1 '+(CX-0.01)+' '+(CY-R)+' Z'
      : 'M '+CX+' '+CY+' L '+CX+' '+(CY-R)+' A '+R+' '+R+' 0 '+grandeArco+' 1 '+x.toFixed(2)+' '+y.toFixed(2)+' Z';
    document.getElementById('efdFatiaNT').setAttribute('d', d);
  }} else {{
    document.getElementById('efdFatiaNT').setAttribute('d', '');
  }}
  requestAnimationFrame(function(){{ setTimeout(function(){{
    document.getElementById('efdPizza').style.transform = 'rotate(360deg)';
  }}, 150); }});

  function contar(id, alvo, atraso){{
    var el = document.getElementById(id), inicio = null;
    function passo(ts){{
      if (!inicio) inicio = ts;
      var p = Math.min(1, (ts - inicio) / 1100);
      var facil = 1 - Math.pow(1 - p, 3);
      el.textContent = 'R$ ' + (alvo*facil).toLocaleString('pt-BR', {{minimumFractionDigits:2, maximumFractionDigits:2}});
      if (p < 1) requestAnimationFrame(passo);
    }}
    setTimeout(function(){{ requestAnimationFrame(passo); }}, atraso);
  }}
  requestAnimationFrame(function(){{ setTimeout(function(){{
    document.getElementById('efdColPis').style.height = document.getElementById('efdColPis').dataset.alvo + 'px';
    document.getElementById('efdColCofins').style.height = document.getElementById('efdColCofins').dataset.alvo + 'px';
  }}, 150); }});
  contar('efdNumPis', {pis['consolidacao']['total_a_recolher']}, 150);
  contar('efdNumCofins', {cofins['consolidacao']['total_a_recolher']}, 300);
}})();
</script>
</body></html>'''

# -*- coding: utf-8 -*-
"""
Relatório consolidado da baixa de NFS-e em lote (todas as empresas cadastradas).

Recebe um dicionário (montado pelo Electron) com o período, o horário e o resultado de cada
empresa, e devolve um HTML único e autônomo, com dashboards animados no mesmo estilo dos
outros painéis. Cada empresa tem um link RELATIVO para o painel individual salvo na pasta
dela (…/NFS-e/Relatórios/<período>/…), então os links funcionam no mesmo computador ou numa
pasta de rede, desde que as pastas não sejam movidas.
"""
import html as _html
import re
from urllib.parse import quote

STATUS = {
    'concluida': ('Concluída', 'ok', '#1f8a69'),
    'sem_notas': ('Sem notas', 'fora', '#6b7392'),
    'pulada': ('Não baixada', 'dif', '#e8632b'),
    'erro': ('Erro', 'dif', '#b42318'),
    'nao_iniciada': ('Não iniciada', 'so', '#8b5cf6'),
}


def _esc(s):
    return _html.escape('' if s is None else str(s))


def _brl(v):
    return f'{(v or 0):,.2f}'.replace(',', '§').replace('.', ',').replace('§', '.')


def _cnpj(c):
    c = re.sub(r'\D', '', c or '')
    return f'{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}' if len(c) == 14 else (c or '')


def _data(iso):
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', iso or '')
    return f'{m.group(3)}/{m.group(2)}/{m.group(1)}' if m else (iso or '')


def _href(rel):
    """Caminho relativo (a partir da subpasta _Relatorios em lote) para o painel individual."""
    return '../' + '/'.join(quote(seg) for seg in (rel or '').split('/'))


def resumo_lote(d):
    emp = d.get('empresas', [])
    cont = {k: sum(1 for e in emp if e.get('status') == k) for k in STATUS}
    return {
        'total': len(emp), 'concluidas': cont['concluida'], 'sem_notas': cont['sem_notas'], 'puladas': cont['pulada'], 'erros': cont['erro'],
        'nao_iniciadas': cont['nao_iniciada'], 'salvos': sum(e.get('salvos', 0) for e in emp),
        'inconsistencias': sum(e.get('inconsistencias', 0) for e in emp),
    }


def gerar_relatorio_lote_html(d):
    from efd_contribuicoes import _CSS, _linhas_tabela  # noqa: F401  (estilos compartilhados com os outros painéis)
    from efd_corretor import _CSS_CORR, _JS_CORR, _grad_barra
    emp = d.get('empresas', [])
    r = resumo_lote(d)
    per = d.get('periodo', {})
    processadas = r['concluidas'] + r['sem_notas']
    nao_baixadas = r['puladas'] + r['erros']

    cab = (f'<div class="hdr"><b>FiscoCont+ · Baixa em lote de NFS-e</b><div>Período {_data(per.get("ini"))} a {_data(per.get("fim"))} · iniciada em {_esc(d.get("inicio"))}'
           f' · concluída em {_esc(d.get("fim_exec"))} · {r["total"]} empresa(s) cadastrada(s) · PDF (DANFSe): {"sim" if d.get("gerar_pdf") else "não"}</div></div>')
    aviso_cancel = ''
    if d.get('cancelado'):
        aviso_cancel = (f'<div class="aviso2"><b>Lote cancelado pelo usuário.</b> {r["nao_iniciadas"]} empresa(s) não chegaram a ser processadas e aparecem como "Não iniciada". '
                        f'As empresas já concluídas ficaram salvas normalmente.</div>')
    kpis = (f'<div class="kpis">'
            f'<div class="kpi"><b><span class="cnt" data-alvo="{processadas}" style="font-size:inherit;color:inherit">0</span> de {r["total"]}</b><span>Empresas processadas</span></div>'
            f'<div class="kpi destaque"><b class="cnt" data-alvo="{r["salvos"]}">0</b><span>NFS-e baixadas</span></div>'
            f'<div class="kpi laranja"><b class="cnt" data-alvo="{nao_baixadas}" style="color:#e8632b">0</b><span>Empresas não baixadas / com erro</span></div>'
            f'<div class="kpi" style="--acc:#f5a524;background:linear-gradient(180deg,#fff,#fbf3dc)"><b class="cnt" data-alvo="{r["inconsistencias"]}" style="color:#b8780a">0</b><span>Inconsistências de retenção</span></div></div>')

    # pizza: situação das empresas
    graf = [{'n': STATUS[k][0], 'c': STATUS[k][2], 'a': q} for k, q in
            (('concluida', r['concluidas']), ('sem_notas', r['sem_notas']), ('pulada', r['puladas']), ('erro', r['erros']), ('nao_iniciada', r['nao_iniciadas'])) if q]
    if not graf:
        graf = [{'n': 'Sem empresas', 'c': '#6b7392', 'a': 1}]
    leg = ''.join(f'<div><i style="background:{g["c"]};box-shadow:0 2px 4px rgba(31,42,90,.3)"></i>{_esc(g["n"])}<br><b>{g["a"]}</b></div>' for g in graf)
    pizza = ('<div class="card chart"><h3>Situação das empresas</h3><div style="display:flex;align-items:center;justify-content:center;gap:20px 30px;flex-wrap:wrap;padding:6px 0 4px">'
             '<div class="pizza-wrap"><svg id="corrPizza" width="220" height="220" viewBox="0 0 220 220" style="display:block;transition:transform 1.1s cubic-bezier(.2,.8,.2,1);transform-origin:110px 110px">'
             '<defs><radialGradient id="corrGl" cx="34%" cy="24%" r="58%"><stop offset="0" stop-color="#fff" stop-opacity=".38"/><stop offset="100%" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>'
             f'<g id="corrSlices"></g><circle cx="110" cy="110" r="92" fill="url(#corrGl)" style="pointer-events:none"/></svg></div><div class="leg" style="min-width:170px;gap:9px">{leg}</div></div></div>')

    # colunas: prestadas × tomadas das empresas com mais notas
    com_notas = sorted([e for e in emp if e.get('prestadas', 0) + e.get('tomadas', 0) > 0], key=lambda e: -(e.get('prestadas', 0) + e.get('tomadas', 0)))
    top = com_notas[:12]
    mx = max([max(e.get('prestadas', 0), e.get('tomadas', 0)) for e in top] + [1])
    cols = ''
    for e in top:
        hp = max(6, round(190 * e.get('prestadas', 0) / mx)) if e.get('prestadas') else 0
        ht = max(6, round(190 * e.get('tomadas', 0) / mx)) if e.get('tomadas') else 0
        nome = (e.get('nome') or '')[:18]
        cols += (f'<div class="bar-grp"><div class="bar-par"><div style="display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%"><span class="val-bar" style="color:#1f2a5a">{e.get("prestadas", 0)}</span>'
                 f'<div class="b2" data-alvo="{hp}" style="background:{_grad_barra("#1f2a5a")};box-shadow:0 10px 16px #1f2a5a55,inset 0 3px 0 rgba(255,255,255,.3)"></div></div>'
                 f'<div style="display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%"><span class="val-bar" style="color:#e8632b">{e.get("tomadas", 0)}</span>'
                 f'<div class="b2" data-alvo="{ht}" style="background:{_grad_barra("#e8632b")};box-shadow:0 10px 16px #e8632b55,inset 0 3px 0 rgba(255,255,255,.3)"></div></div></div>'
                 f'<div class="rot-bar">{_esc(nome)}</div></div>')
    if not cols:
        cols = '<div style="color:var(--ink2);font-size:12.5px;padding:40px 0">Nenhuma empresa teve notas no período.</div>'
    extra = f' — mostrando as {len(top)} com mais notas' if len(com_notas) > len(top) else ''
    colunas = (f'<div class="card chart"><h3>Notas por empresa <small>(azul = prestadas · laranja = tomadas{extra})</small></h3>'
               f'<div style="overflow-x:auto"><div style="display:flex;align-items:flex-end;gap:18px;padding-top:6px;margin:0 auto;width:max-content">{cols}</div></div></div>')
    grid = f'<div class="grid2"{" style=\"grid-template-columns:1fr\"" if len(top) > 4 else ""}>{pizza}{colunas}</div>'

    # tabela por empresa
    def th(txt, al='right'):
        return f'<th style="text-align:{al}">{txt}</th>'
    linhas = ''
    for e in emp:
        rot, cls, _cor = STATUS.get(e.get('status'), ('?', 'fora', '#6b7392'))
        nome = f'<b>{_esc(e.get("nome"))}</b><br><span style="color:var(--ink2);font-size:11px">{_esc(_cnpj(e.get("cnpj")))}</span>'
        if e.get('relatorio_rel'):
            nome += f'<br><a href="{_esc(_href(e["relatorio_rel"]))}" target="_blank" style="color:#2f4090;font-weight:700;font-size:11px">Abrir painel da empresa →</a>'
        if e.get('aviso'):
            nome += f'<br><span class="bad" style="font-size:11px">{_esc(e["aviso"])}</span>'
        pill = f'<span class="st {cls}">{rot}</span>'
        if e.get('status') in ('pulada', 'erro'):
            linhas += f'<tr class="rec"><td>{nome}</td><td style="text-align:center">{pill}</td><td colspan="8">{_esc(e.get("motivo"))}</td></tr>'
        elif e.get('status') == 'nao_iniciada':
            linhas += f'<tr><td>{nome}</td><td style="text-align:center">{pill}</td><td colspan="8" style="color:var(--ink2)">{_esc(e.get("motivo"))}</td></tr>'
        else:
            semnota = e.get('status') == 'sem_notas'
            zero = ' class="zero"' if semnota else ''
            ret = '—' if semnota else f'{e.get("qtd_com_ret", 0)} com / {e.get("qtd_sem_ret", 0)} sem'
            inc = (f'<span class="st dif">{e["inconsistencias"]}</span>' if e.get('inconsistencias') else '—')
            pdfs = '—' if (semnota or not d.get('gerar_pdf')) else f'{e.get("pdfs_gerados", 0)}/{e.get("salvos", 0)}' + (f' <span class="bad">({e["pdfs_erro"]} erro)</span>' if e.get('pdfs_erro') else '')
            linhas += (f'<tr><td>{nome}</td><td style="text-align:center">{pill}</td><td{zero} style="text-align:right">{e.get("prestadas", 0)}</td><td{zero} style="text-align:right">{e.get("tomadas", 0)}</td>'
                       f'<td{zero} style="text-align:right">{e.get("canceladas", 0)}</td><td{zero} style="text-align:right">{_brl(e.get("valor_prestado"))}</td><td{zero} style="text-align:right">{_brl(e.get("valor_tomado"))}</td>'
                       f'<td style="text-align:right">{pdfs}</td><td style="text-align:right">{ret}</td><td style="text-align:center">{inc}</td></tr>')
    soma = lambda k: sum(e.get(k, 0) for e in emp if e.get('status') in ('concluida', 'sem_notas'))
    linhas += (f'<tr class="tot"><td>Total do lote</td><td></td><td style="text-align:right">{soma("prestadas")}</td><td style="text-align:right">{soma("tomadas")}</td><td style="text-align:right">{soma("canceladas")}</td>'
               f'<td style="text-align:right">{_brl(soma("valor_prestado"))}</td><td style="text-align:right">{_brl(soma("valor_tomado"))}</td><td style="text-align:right">{soma("pdfs_gerados") if d.get("gerar_pdf") else "—"}</td>'
               f'<td style="text-align:right">{soma("qtd_com_ret")} com / {soma("qtd_sem_ret")} sem</td><td style="text-align:center">{r["inconsistencias"]}</td></tr>')
    tabela = ('<table class="t" style="min-width:900px"><thead><tr>' + th('Empresa', 'left') + th('Situação', 'center') + th('Prestadas') + th('Tomadas') + th('Canc.') + th('Valor prestado') +
              th('Valor tomado') + th('PDFs') + th('Retenção') + th('Inconsist.', 'center') + f'</tr></thead><tbody>{linhas}</tbody></table>')
    tab_card = f'<div class="card"><h3>Resultado por empresa</h3>{tabela}</div>'

    # ocorrências
    oc = [e for e in emp if e.get('status') in ('pulada', 'erro')]
    oc_html = ''
    if oc:
        oc_html = ('<h2 class="secao"><span class="dot" style="background:#e8632b"></span>Ocorrências — empresas que não foram baixadas</h2><div class="card" style="border-top:4px solid #e8632b">' +
                   ''.join(f'<div class="nota"><b>{_esc(e.get("nome"))}</b> ({_esc(_cnpj(e.get("cnpj")))}) — {_esc(e.get("motivo"))}</div>' for e in oc) +
                   '<div class="txt" style="margin-top:10px">Resolva o motivo (certificado, senha ou conexão) e baixe só essa empresa pela tela normal, com o mesmo período. O relatório individual dela é salvo do mesmo jeito.</div></div>')
    inc_html = ''
    if r['inconsistencias']:
        inc_html = (f'<div class="aviso2"><b>{r["inconsistencias"]} nota(s) com inconsistência de retenção de PIS/COFINS/CSLL</b> no lote (a situação do documento contradiz o valor retido). '
                    f'O detalhe de cada nota está no painel individual da empresa (link "Abrir painel da empresa").</div>')
    pasta_rel = d.get('pasta_relatorios', '')
    rodape = ('<div class="card"><div style="font-size:11.5px;color:var(--ink2);line-height:1.7">'
              f'<b>Este relatório foi salvo automaticamente em:</b><br><span style="font-family:Consolas,monospace">{_esc(d.get("caminho"))}</span><br>'
              f'<b>Painel individual de cada empresa:</b> <span style="font-family:Consolas,monospace">{_esc(pasta_rel)}</span><br>'
              'Os links "Abrir painel da empresa" são caminhos relativos: funcionam enquanto as pastas não forem movidas.</div></div>')
    corpo = cab + kpis + grid + aviso_cancel + inc_html + tab_card + oc_html + rodape
    import json
    js = _JS_CORR.replace('__DADOS__', json.dumps(graf, ensure_ascii=False))
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>Baixa em lote de NFS-e · {_data(per.get("ini"))} a {_data(per.get("fim"))}</title><style>{_CSS}{_CSS_CORR}</style></head><body>{corpo}<script>{js}</script></body></html>')

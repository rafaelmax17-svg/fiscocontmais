# -*- coding: utf-8 -*-
"""Conferência de ICMS do Crédito (XML × SPED) — Documentos de Entrada (só leitura, não altera o SPED).

Usa a mesma conferência do corretor (icms_xml.analisar_texto): para cada NF-e de entrada escriturada que tem XML,
compara o ICMS creditado no SPED com o destacado na nota. O relatório mostra o que diverge, o que confere, as notas
do .zip que não estão no SPED (ignoradas: isso é conferido em Notas Faltantes) e as entradas com crédito sem XML.
Cada nota tem o botão "PDF", que pede à janela do sistema o DANFE daquela chave (postMessage 'gerarDanfe').
A correção do SPED fica no Admin › Correção do SPED Fiscal › ICMS creditado × XML.
"""
import os
import re
import sys
import json
import html as _html

import difal_ro as dr
import icms_xml as ix
import fiscal_core as fc
from xml_entradas import ler_xmls

ROT = {
    'sem_destaque': ('Crédito sem destaque na nota', '#b3261e', '#fdecee'),
    'maior': ('Crédito maior que o destacado', '#b3261e', '#fdecee'),
    'maior_sem_item': ('Crédito maior que o destacado', '#b3261e', '#fdecee'),
    'st_sem_retencao': ('Escriturado como ST, nota sem ST', '#4f46e5', '#eef0ff'),
    'menor': ('Crédito menor que o destacado', '#5a6785', '#f2f3f7'),
}


def _f(v):
    return dr._f(dr._d(v))


def conferir(sped, caminhos):
    texto, _ = dr._ler(sped)
    xmls, lidos, erros = ler_xmls(caminhos)
    an = ix.analisar_texto(texto, xmls)
    linhas, _, _ = dr.dividir(texto)
    _, part, _, docs, _, _ = dr._estrutura(linhas)
    chaves_sped = {re.sub(r'\D', '', d['chave'] or '') for d in docs}
    ignoradas = [x for k, x in xmls.items() if x.get('tipo') in (None, 'nfe') and k not in chaves_sped]
    rs = an['resumo']
    div = [d for d in an['docs'] if d['status'] in ('sem_destaque', 'maior', 'maior_sem_item')]
    info = [d for d in an['docs'] if d['status'] in ('st_sem_retencao', 'menor')]
    return {
        'empresa': an['empresa'], 'docs': an['docs'], 'sem_xml_credito': an.get('sem_xml_credito', []),
        'qtd_divergentes': len(div), 'qtd_informativas': len(info),
        'qtd_corretas': max(0, rs['notas_conferidas'] - len(div) - len(info)),
        'qtd_ignoradas': len(ignoradas), 'total_divergencia': rs['credito_indevido'],
        'nao_creditado': float(dr._d(rs.get('st_sem_retencao_valor', 0) + rs.get('credito_nao_tomado', 0))),
        'xml_lidos': lidos, 'xml_erros': erros, 'notas_conferidas': rs['notas_conferidas'],
        'sem_xml_com_credito': rs.get('sem_xml_com_credito', 0), 'sem_xml_credito_valor': rs.get('sem_xml_credito_valor', 0.0),
        'ignoradas': [{'num': x.get('num', ''), 'emitente': x.get('emit_nome', ''), 'chave': x['chave'], 'valor': x.get('vnf', 0.0)} for x in ignoradas][:300],
    }


def gerar_html(res, logo=''):
    esc = _html.escape
    e = res['empresa']
    dt = lambda s: f'{s[:2]}/{s[2:4]}/{s[4:]}' if len(s or '') == 8 else (s or '')
    pdf = lambda ch: (f'<button class="pdf" onclick="parent.postMessage({{acao:\'gerarDanfe\',chave:\'{esc(ch)}\'}},\'*\')">PDF</button>' if ch else '')
    linhas = ''
    for d in res['docs']:
        rot, cor, fundo = ROT.get(d['status'], (d['status'], '#5a6785', '#f2f3f7'))
        dif = d['icms_sped'] - d['icms_xml']
        itens = ''.join(f'<tr><td>{esc(i["num"])}</td><td>{esc(i["descr"])}<small>XML: {esc(i["xprod"])} · NCM {esc(i["ncm"])}</small></td><td>{esc(i["cfop"])}</td>'
                        f'<td>{esc(i["cst_sped"])} → {esc(i["cst_xml"])}</td><td class="n">{_f(i["aliq_sped"])}% → {_f(i["aliq_xml"])}%</td>'
                        f'<td class="n">R$ {_f(i["icms_sped"])} → R$ {_f(i["icms_xml"])}</td></tr>' for i in d.get('itens') or [])
        obs = ''.join(f'<small>{esc(o)}</small>' for o in d.get('obs') or [])
        linhas += f'''<tr><td><b>{esc(d["num"])}</b><small>{dt(d["data"])}</small></td><td>{esc(d["fornecedor"])}{' <span class="tag">Simples</span>' if d.get('simples') else ''}<small>{esc(d["cnpj"])} · {esc(d.get("uf") or "")}</small></td>
          <td class="n">R$ {_f(d["icms_xml"])}</td><td class="n"><b>R$ {_f(d["icms_sped"])}</b></td><td class="n" style="color:{cor}"><b>{"+" if dif > 0 else ""}R$ {_f(dif)}</b></td>
          <td><span class="st" style="color:{cor};background:{fundo}">{rot}</span>{obs}</td><td>{pdf(d.get("chave"))}</td></tr>'''
        if itens:
            linhas += f'<tr class="det"><td colspan="7"><details><summary>ver itens ({len(d["itens"])})</summary><table class="in"><thead><tr><th>Item</th><th>Produto no SPED / no XML</th><th>CFOP</th><th>CST SPED → XML</th><th class="n">Alíquota</th><th class="n">ICMS</th></tr></thead><tbody>{itens}</tbody></table></details></td></tr>'
    semx = ''.join(f'<tr><td><b>{esc(z["num"])}</b><small>{dt(z["data"])}</small></td><td>{esc(z["fornecedor"])}<small>{esc(z["cnpj"])}</small></td><td class="mono">{esc(z["chave"])}</td><td class="n">R$ {_f(z["icms_sped"])}</td></tr>'
                   for z in res.get('sem_xml_credito') or [])
    ign = ''.join(f'<tr><td><b>{esc(z["num"])}</b></td><td>{esc(z["emitente"])}</td><td class="mono">{esc(z["chave"])}</td><td class="n">R$ {_f(z["valor"])}</td><td>{pdf(z["chave"])}</td></tr>'
                  for z in res.get('ignoradas') or [])
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Conferência de ICMS do Crédito</title><style>
body{{margin:0;padding:22px;background:#f4f5fa;font-family:Inter,Segoe UI,system-ui,sans-serif;color:#141b2d;font-size:13px}}
.hd{{display:flex;justify-content:space-between;align-items:center;background:linear-gradient(120deg,#1f2a5a,#2f4090);color:#fff;border-radius:16px;padding:18px 22px}}
.hd h1{{margin:4px 0 2px;font-size:20px}}.hd small{{color:#dfe5ff}}.hd .k{{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#cdd6ff}}
.hd img{{height:38px;background:#fff;border-radius:8px;padding:4px 8px}}
.kp{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:16px 0}}.kp div{{background:#fff;border-radius:14px;padding:12px 14px;box-shadow:0 4px 14px rgba(20,27,45,.06);border-top:4px solid #c9cfdc}}
.kp .r{{border-top-color:#e34948}}.kp .g{{border-top-color:#1baf7a}}.kp .y{{border-top-color:#eda100}}
.kp span{{display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:#5a6785}}.kp b{{font-size:22px}}.kp small{{display:block;color:#5a6785;font-size:11.5px}}
.box{{background:#fff;border-radius:16px;padding:14px 16px;margin-top:14px;box-shadow:0 4px 14px rgba(20,27,45,.06)}}
.box h2{{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#2f4090;margin:0 0 8px}}
table{{border-collapse:collapse;width:100%}}th{{text-align:left;font-size:10.5px;text-transform:uppercase;color:#5a6785;padding:7px 8px;border-bottom:1px solid #e8ebf3;background:#f6f7fb}}
td{{padding:8px;border-bottom:1px solid #eef0f6;vertical-align:top}}td small{{display:block;color:#8a93a8;font-size:11px;margin-top:2px}}.n{{text-align:right;white-space:nowrap}}
.st{{font-size:11px;font-weight:700;border-radius:20px;padding:2px 9px;white-space:nowrap}}.tag{{font-size:10px;font-weight:700;background:#fff3d6;color:#8a5a06;border-radius:20px;padding:1px 7px}}
.mono{{font-family:monospace;font-size:11.5px}}.det td{{background:#fbfbfe;padding-top:0}}details summary{{cursor:pointer;color:#2f4090;font-weight:600;font-size:12px}}
.in{{margin-top:6px}}.in td,.in th{{font-size:11.5px;padding:5px 7px}}
.pdf{{border:1px solid #2f4090;color:#2f4090;background:#fff;border-radius:7px;padding:3px 9px;font-weight:700;font-size:11.5px;cursor:pointer}}
.ok{{background:#f1fbf6;border:1px solid #bfe8d5;color:#0b6b4f;border-radius:12px;padding:10px 14px}}
.nota{{color:#5a6785;font-size:12px;margin-top:10px}}
</style></head><body>
<div class="hd"><div><div class="k">Documentos de entrada · Conferência de ICMS do Crédito (XML × SPED)</div><h1>{esc(e.get("nome", ""))}</h1>
<small>CNPJ {esc(e.get("cnpj", ""))} · período {dt(e.get("dt_ini"))} a {dt(e.get("dt_fin"))} · {res["xml_lidos"]} XMLs lidos</small></div>{f'<img src="{logo}">' if logo else ''}</div>
<div class="kp"><div><span>Notas conferidas</span><b>{res["notas_conferidas"]}</b><small>entradas com XML</small></div>
<div class="g"><span>Conferem</span><b>{res["qtd_corretas"]}</b><small>crédito = destacado</small></div>
<div class="r"><span>Crédito acima da nota</span><b>{res["qtd_divergentes"]}</b><small>R$ {_f(res["total_divergencia"])} a mais</small></div>
<div class="y"><span>Crédito abaixo da nota</span><b>{res["qtd_informativas"]}</b><small>R$ {_f(res["nao_creditado"])} não creditado</small></div>
<div><span>Sem XML / fora do SPED</span><b>{res["sem_xml_com_credito"]} / {res["qtd_ignoradas"]}</b><small>entradas com crédito sem XML / XMLs não escriturados</small></div></div>
<div class="box"><h2>Notas com diferença</h2>{f'<table><thead><tr><th>Nota</th><th>Fornecedor</th><th class="n">ICMS na nota</th><th class="n">Creditado no SPED</th><th class="n">Diferença</th><th>Situação</th><th></th></tr></thead><tbody>{linhas}</tbody></table>' if linhas else '<div class="ok">O ICMS creditado no SPED confere com o destacado em todas as notas com XML.</div>'}
<div class="nota">A correção do SPED é feita em <b>Admin › Correção do SPED Fiscal › ICMS creditado × XML</b>. Base legal: o crédito é o imposto cobrado e destacado na nota da operação anterior (LC 87/96, arts. 19, 20 e 23).</div></div>
{f'<div class="box"><h2>Entradas com crédito e sem XML ({res["sem_xml_com_credito"]} · R$ {_f(res["sem_xml_credito_valor"])})</h2><table><thead><tr><th>Nota</th><th>Fornecedor</th><th>Chave</th><th class="n">ICMS creditado</th></tr></thead><tbody>{semx}</tbody></table></div>' if semx else ''}
{f'<div class="box"><h2>XMLs do .zip que não estão no SPED ({res["qtd_ignoradas"]}) — conferidos em Notas Faltantes</h2><table><thead><tr><th>Nota</th><th>Emitente</th><th>Chave</th><th class="n">Valor</th><th></th></tr></thead><tbody>{ign}</tbody></table></div>' if ign else ''}
</body></html>'''


def listar(caminhos):
    xmls, _, _ = ler_xmls(caminhos)
    out = [{'chave': k, 'tipo': x.get('tipo') or 'nfe', 'num': x.get('num', ''), 'emitente': x.get('emit_nome', ''),
            'emit_cnpj': x.get('emit_cnpj', ''), 'emit_uf': x.get('emit_uf', ''), 'dest_cnpj': x.get('dest_cnpj', ''),
            'valor': x.get('vnf', x.get('vtprest', 0.0)), 'icms': x.get('vicms', 0.0)} for k, x in xmls.items()]
    return sorted(out, key=lambda z: (z['emitente'], z['num']))


def main_cli(argv):
    """icms-credito SPED.txt --xmls XMLS --json r.json --html r.html   |   listar-notas-xml XMLS --json r.json"""
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    modo = argv[0]
    if modo == 'listar-notas-xml':
        if len(argv) < 2 or not opt('--json'):
            print(main_cli.__doc__, file=sys.stderr)
            return 1
        fc._out(opt('--json'), json.dumps(listar([c for c in argv[1].split(os.pathsep) if c]), ensure_ascii=False))
        return 0
    if len(argv) < 2 or not opt('--xmls') or not (opt('--json') or opt('--html')):
        print(main_cli.__doc__, file=sys.stderr)
        return 1
    try:
        res = conferir(argv[1], [c for c in opt('--xmls').split(os.pathsep) if c])
        html = gerar_html(res, fc._logo_uri())
    except Exception as e:  # pragma: no cover
        res = {'erro': f'Falha na conferência: {e}', 'qtd_divergentes': 0, 'qtd_corretas': 0, 'qtd_ignoradas': 0, 'total_divergencia': 0}
        html = f'<html><body style="font-family:sans-serif;padding:24px"><h3>Não foi possível conferir</h3><p>{_html.escape(res["erro"])}</p></body></html>'
    if opt('--json'):                       # o JSON antes: a tela espera pelo HTML e depois lê o resumo
        fc._out(opt('--json'), json.dumps(res, ensure_ascii=False))
    if opt('--html'):
        fc._out(opt('--html'), html)
    return 0


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main_cli(sys.argv[1:]))

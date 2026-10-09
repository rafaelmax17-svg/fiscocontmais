# -*- coding: utf-8 -*-
"""Dashboard animado do Corretor do SPED Fiscal (módulo Admin).

Compara o arquivo original com o corrigido e mostra, em painel: quantas correções de cada tipo, quais registros mudaram,
os itens/notas afetados e a apuração do ICMS do arquivo corrigido. Usado na tela (iframe) e na exportação HTML/PDF.
"""
import html as _html
import json
import math

PALETA = {'c191': '#2a78d6', 'e500': '#eb6834', 'gtin': '#1baf7a', 'cest': '#eda100', 'nat': '#4a3aa7', 'r0400': '#e87ba4'}
TIPOS = [
    ('c191', 'C191 removidos', 'FCP informado em C190 com CST que não admite FCP',
     'O C191 (FCP) só pode existir quando o CST do C190 pai é 00, 10, 20, 51, 70 ou 90 (Guia Prático da EFD, registro C191).'),
    ('e500', 'Linhas do bloco de IPI removidas', 'E500/E510/E520 sem ser contribuinte de IPI',
     'Os registros de apuração do IPI (E500 e filhos) só existem para estabelecimento contribuinte do IPI (industrial ou equiparado).'),
    ('gtin', 'GTIN limpos', 'Código de barras "SEM GTIN" no cadastro do item (0200)',
     'O campo COD_BARRA do 0200 deve ser o GTIN válido ou ficar vazio; o texto "SEM GTIN" é usado só na NF-e.'),
    ('cest', 'CEST limpos', 'CEST fora da tabela oficial no cadastro do item (0200)',
     'O CEST informado no 0200 deve existir na tabela do Convênio ICMS 142/2018; códigos inválidos são retirados.'),
    ('nat', 'COD_NAT corrigidos', 'Natureza da operação "0" no item da nota (C170)',
     'O COD_NAT do C170 deve apontar para um 0400 existente; o sistema preenche pelo CFOP e cria o 0400 que faltar.'),
    ('r0400', 'Registros 0400 criados', 'Naturezas de operação que faltavam no bloco 0',
     'Todo COD_NAT usado no C170 precisa do seu registro 0400 (código e descrição da natureza).'),
]


def _e(s):
    return _html.escape('' if s is None else str(s))


def _n(s):
    s = (s or '').strip()
    if not s:
        return 0.0
    try:
        return float(s.replace('.', '').replace(',', '.')) if ',' in s else float(s)
    except ValueError:
        return 0.0


def _brl(v):
    return 'R$ ' + f'{(v or 0):,.2f}'.replace(',', '§').replace('.', ',').replace('§', '.')


def _int(v):
    return f'{int(v or 0):,}'.replace(',', '.')


def _dt(d):
    return f'{d[:2]}/{d[2:4]}/{d[4:]}' if d and len(d) == 8 else (d or '')


def _linhas(texto):
    q = '\r\n' if '\r\n' in texto else '\n'
    ls = texto.split(q)
    return ls[:-1] if ls and ls[-1] == '' else ls


def _reg(l):
    return l.split('|')[1] if l.count('|') >= 2 else ''


def coletar(texto_orig, texto_corr, resumo):
    lo, lc = _linhas(texto_orig), _linhas(texto_corr)
    emp = {}
    for l in lo[:3]:
        c = l.split('|')
        if len(c) > 9 and c[1] == '0000':
            emp = {'nome': c[6], 'cnpj': c[7], 'uf': c[9], 'dt_ini': c[4], 'dt_fin': c[5]}
    cont_o, cont_c = {}, {}
    for l in lo:
        r = _reg(l); cont_o[r] = cont_o.get(r, 0) + 1
    for l in lc:
        r = _reg(l); cont_c[r] = cont_c.get(r, 0) + 1
    regs = sorted({r for r in set(cont_o) | set(cont_c) if r and cont_o.get(r, 0) != cont_c.get(r, 0) and not r.startswith('9')})
    mudados = [{'reg': r, 'antes': cont_o.get(r, 0), 'depois': cont_c.get(r, 0)} for r in regs]

    # C191 removidos: CST do C190 pai
    c191 = {}
    cst = ''
    for l in lo:
        c = l.split('|')
        if len(c) < 3:
            continue
        if c[1] == 'C190':
            cst = c[2]
        elif c[1] == 'C191' and cst[-2:] not in ('00', '10', '20', '51', '70', '90'):
            g = c191.setdefault(cst, {'cst': cst, 'qtd': 0, 'fcp': 0.0})
            g['qtd'] += 1
            g['fcp'] += _n(c[2]) + (_n(c[3]) if len(c) > 3 else 0) + (_n(c[4]) if len(c) > 4 else 0)
    # bloco de IPI removido
    e500 = [{'reg': r, 'qtd': cont_o.get(r, 0) - cont_c.get(r, 0)} for r in ('E500', 'E510', 'E520', 'E530', 'E531')
            if cont_o.get(r, 0) - cont_c.get(r, 0) > 0]
    # 0200: GTIN e CEST (casados pelo código do item)
    p_o = {c[2]: c for c in (l.split('|') for l in lo if l.startswith('|0200|')) if len(c) > 2}
    gtin, cest = [], []
    for l in lc:
        if not l.startswith('|0200|'):
            continue
        c = l.split('|')
        o = p_o.get(c[2])
        if not o:
            continue
        if len(o) > 4 and len(c) > 4 and o[4] != c[4]:
            gtin.append({'cod': c[2], 'descr': c[3], 'antes': o[4]})
        if len(o) > 13 and len(c) > 13 and o[13] != c[13]:
            cest.append({'cod': c[2], 'descr': c[3], 'antes': o[13], 'ncm': c[8] if len(c) > 8 else ''})
    # C170: COD_NAT por CFOP (as linhas do C170 não são removidas; casam pela ordem)
    c170_o = [l.split('|') for l in lo if l.startswith('|C170|')]
    c170_c = [l.split('|') for l in lc if l.startswith('|C170|')]
    nat = {}
    if len(c170_o) == len(c170_c):
        for o, c in zip(c170_o, c170_c):
            if len(o) > 12 and len(c) > 12 and o[12] != c[12]:
                k = (o[11], c[12])
                nat[k] = nat.get(k, 0) + 1
    nat_l = [{'cfop': k[0], 'para': k[1], 'qtd': v} for k, v in sorted(nat.items(), key=lambda x: -x[1])]
    r0400 = []
    criados = set(resumo.get('registro_0400_criado') or [])
    for l in lc:
        c = l.split('|')
        if len(c) > 3 and c[1] == '0400' and c[2] in criados:
            r0400.append({'cod': c[2], 'descr': c[3]})
    # apuração do arquivo corrigido
    apur = None
    for l in lc:
        c = l.split('|')
        if len(c) > 15 and c[1] == 'E110':
            apur = {'deb': _n(c[2]), 'aj_deb': _n(c[3]) + _n(c[4]), 'cred': _n(c[6]), 'aj_cred': _n(c[7]) + _n(c[8]),
                    'sld_ant': _n(c[10]), 'recolher': _n(c[13]), 'sld_transp': _n(c[14]), 'deb_esp': _n(c[15])}
            break
    valores = {
        'c191': resumo.get('c191_removidos', 0), 'e500': resumo.get('e500_linhas_removidas', 0),
        'gtin': resumo.get('gtin_limpos', 0), 'cest': resumo.get('cest_limpos', 0),
        'nat': resumo.get('cod_nat_corrigidos', 0), 'r0400': len(resumo.get('registro_0400_criado') or []),
    }
    return {
        'empresa': emp, 'valores': valores, 'total': sum(valores.values()),
        'linhas_antes': len(lo), 'linhas_depois': len(lc), 'mudados': mudados,
        'c191': sorted(c191.values(), key=lambda x: -x['qtd']), 'e500': e500, 'gtin': gtin, 'cest': cest,
        'nat': nat_l, 'r0400': r0400, 'apur': apur,
    }


def _donut(itens, total):
    r, sw = 70, 26
    C = 2 * math.pi * r
    cum, arcs = 0.0, ''
    for i, (k, v) in enumerate(itens):
        if v <= 0:
            continue
        frac = v / total
        arcs += (f'<circle class="cd-arc" cx="95" cy="95" r="{r}" fill="none" stroke="{PALETA[k]}" stroke-width="{sw}" '
                 f'stroke-dasharray="{frac * C:.2f} {C:.2f}" stroke-dashoffset="{-cum * C:.2f}" '
                 f'style="--d:{frac * C:.2f};animation-delay:{0.15 + i * 0.12:.2f}s" transform="rotate(-90 95 95)"/>')
        cum += frac
    return (f'<svg viewBox="0 0 190 190" class="cd-donut"><circle cx="95" cy="95" r="{r}" fill="none" stroke="#eef0f6" stroke-width="{sw}"/>'
            f'{arcs}<text x="95" y="92" text-anchor="middle" class="cd-dc" data-n="{total}">0</text>'
            f'<text x="95" y="113" text-anchor="middle" class="cd-ds">correções</text></svg>')


def gerar_html(texto_orig, texto_corr, resumo, logo_uri=''):
    d = coletar(texto_orig, texto_corr, resumo)
    emp, v, tot = d['empresa'], d['valores'], d['total']
    mx = max(1, max(v.values()))
    rotulo = {k: n for k, n, _, _ in TIPOS}

    kpis = ''.join(
        f'<div class="cd-kpi" style="--c:{PALETA[k]};--i:{i + 1}"><span>{_e(n)}</span><b data-n="{v[k]}">0</b><small>{_e(s)}</small></div>'
        for i, (k, n, s, _) in enumerate(TIPOS))
    barras = ''.join(
        f'<div class="cd-bar" style="--i:{i}"><span>{_e(rotulo[k])}</span>'
        f'<i class="cd-bt"><i style="--w:{v[k] / mx * 100:.1f}%;background:{PALETA[k]}"></i></i><b data-n="{v[k]}">0</b></div>'
        for i, (k, *_r) in enumerate(TIPOS))
    leg = ''.join(f'<div><i style="background:{PALETA[k]}"></i>{_e(rotulo[k])}<b>{_int(v[k])}</b><small>{(v[k] / tot * 100 if tot else 0):.1f}%</small></div>'
                  for k, *_r in TIPOS if v[k])

    mx_reg = max([1] + [max(m['antes'], m['depois']) for m in d['mudados']])
    regs = ''.join(
        f'<tr><td><b>{_e(m["reg"])}</b></td><td class="n">{_int(m["antes"])}</td><td class="n">{_int(m["depois"])}</td>'
        f'<td class="n {"neg" if m["depois"] < m["antes"] else "pos"}">{"+" if m["depois"] > m["antes"] else ""}{_int(m["depois"] - m["antes"])}</td>'
        f'<td class="cd-mini"><i style="--w:{m["antes"] / mx_reg * 100:.1f}%" class="a"></i><i style="--w:{m["depois"] / mx_reg * 100:.1f}%" class="d"></i></td></tr>'
        for m in d['mudados'])

    def tabela(cab, linhas, limite=12):
        if not linhas:
            return ''
        corpo = ''.join('<tr>' + ''.join(f'<td class="{cls}">{val}</td>' for cls, val in ln) + '</tr>' for ln in linhas[:limite])
        mais = f'<p class="cd-mais">e mais {_int(len(linhas) - limite)} linha(s).</p>' if len(linhas) > limite else ''
        ths = ''.join('<th class="%s">%s</th>' % (c, t) for c, t in cab)
        return f'<table class="cd-tab"><thead><tr>{ths}</tr></thead><tbody>{corpo}</tbody></table>{mais}'

    detalhes = {
        'c191': tabela([('', 'CST do C190 pai'), ('n', 'C191 removidos'), ('n', 'FCP informado')],
                       [[('', _e(x['cst'])), ('n', _int(x['qtd'])), ('n', _brl(x['fcp']))] for x in d['c191']]),
        'e500': tabela([('', 'Registro'), ('n', 'Linhas removidas')], [[('', _e(x['reg'])), ('n', _int(x['qtd']))] for x in d['e500']]),
        'gtin': tabela([('', 'Item'), ('', 'Descrição'), ('', 'Antes')],
                       [[('', _e(x['cod'])), ('', _e(x['descr'])), ('', f'<s>{_e(x["antes"])}</s>')] for x in d['gtin']]),
        'cest': tabela([('', 'Item'), ('', 'Descrição'), ('', 'NCM'), ('', 'CEST retirado')],
                       [[('', _e(x['cod'])), ('', _e(x['descr'])), ('', _e(x['ncm'])), ('', f'<s>{_e(x["antes"])}</s>')] for x in d['cest']]),
        'nat': tabela([('', 'CFOP'), ('', 'COD_NAT aplicado'), ('n', 'Itens (C170)')],
                      [[('', _e(x['cfop'])), ('', _e(x['para'])), ('n', _int(x['qtd']))] for x in d['nat']]),
        'r0400': tabela([('', 'Código'), ('', 'Natureza da operação')], [[('', _e(x['cod'])), ('', _e(x['descr']))] for x in d['r0400']]),
    }
    cards = ''.join(
        f'<section class="cd-card cd-det" style="--c:{PALETA[k]}"><div class="cd-dh"><h3>{_e(n)}</h3><b>{_int(v[k])}</b></div>'
        f'<p class="cd-why">{_e(por)}</p>{detalhes[k] or ""}</section>'
        for k, n, _, por in TIPOS if v[k])

    ap = d['apur']
    apur = ''
    if ap:
        itens = [('Débitos das saídas', ap['deb'], '#2a78d6'), ('Ajustes a débito', ap['aj_deb'], '#eb6834'),
                 ('Créditos das entradas', ap['cred'], '#1baf7a'), ('Ajustes a crédito', ap['aj_cred'], '#008300'),
                 ('Saldo credor anterior', ap['sld_ant'], '#8a93a8'), ('ICMS a recolher', ap['recolher'], '#1f2a5a'),
                 ('Saldo credor a transportar', ap['sld_transp'], '#4a3aa7')]
        apur = ('<section class="cd-card"><h3>Apuração do ICMS no arquivo corrigido (E110)</h3><div class="cd-ap">' +
                ''.join(f'<div style="--c:{c};--i:{i}"><span>{_e(t)}</span><b data-n="{val:.2f}" data-fmt="brl">R$ 0,00</b></div>'
                        for i, (t, val, c) in enumerate(itens)) +
                '</div><p class="cd-nota">O Corretor não altera valores da apuração: as correções acima são de cadastro e estrutura.</p></section>')

    vazio = '' if tot else ('<section class="cd-card cd-ok"><h3>Nenhuma correção necessária</h3>'
                            '<p>O arquivo não tinha nenhum dos erros que o Corretor trata. O SPED corrigido é igual ao original (só o Bloco 9 recontado).</p></section>')
    corpo_graf = '' if not tot else f'''
    <div class="cd-duo">
      <section class="cd-card"><h3>Correções por tipo</h3><div class="cd-bars">{barras}</div></section>
      <section class="cd-card"><h3>Participação de cada correção</h3><div class="cd-dw">{_donut([(k, v[k]) for k, *_r in TIPOS], tot)}<div class="cd-leg">{leg}</div></div></section>
    </div>'''
    regs_sec = '' if not d['mudados'] else f'''
    <section class="cd-card"><h3>Registros do arquivo: antes × depois</h3>
      <table class="cd-tab cd-regs"><thead><tr><th>Registro</th><th class="n">Antes</th><th class="n">Depois</th><th class="n">Diferença</th><th></th></tr></thead><tbody>{regs}</tbody></table>
      <div class="cd-l2"><span><i class="a"></i>Antes</span><span><i class="d"></i>Depois</span></div>
    </section>'''
    logo = f'<img src="{logo_uri}" alt="">' if logo_uri else ''
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Corretor do SPED Fiscal · Dashboard</title><style>{CSS}</style></head><body><main class="cd">
  <header class="cd-hero">
    <div class="cd-top">{logo}<div><div class="cd-k">FiscoCont+ · Corretor do SPED Fiscal · Admin</div>
      <h1>{_e(emp.get("nome", ""))}</h1>
      <div class="cd-sub">CNPJ {_e(emp.get("cnpj", ""))} · {_e(emp.get("uf", ""))} · período {_dt(emp.get("dt_ini"))} a {_dt(emp.get("dt_fin"))}</div></div></div>
    <div class="cd-hk">
      <div><span>Correções aplicadas</span><b data-n="{tot}">0</b></div>
      <div><span>Linhas do arquivo</span><b><em data-n="{d["linhas_antes"]}">0</em> → <em data-n="{d["linhas_depois"]}">0</em></b></div>
      <div><span>Arquivo original</span><b class="cd-pres">preservado</b></div>
    </div>
  </header>
  <div class="cd-kpis">{kpis}</div>
  {vazio}{corpo_graf}{regs_sec}
  {cards}
  {apur}
  <footer class="cd-rod">Gerado pelo FiscoCont+ · Liddera | Inteligência em Negócios · o SPED corrigido é um arquivo novo; o original não é alterado.
    Bloco 9 e totais de bloco recontados. Base: Guia Prático da EFD ICMS/IPI.</footer>
</main><script>{JS}</script></body></html>'''


CSS = '''
*{box-sizing:border-box}body{margin:0;background:#f4f6fb;color:#141b2d;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.cd{max-width:1280px;margin:0 auto;padding:24px;display:grid;gap:18px}
.cd-hero{background:linear-gradient(120deg,#1f2a5a,#2f4090);color:#fff;border-radius:22px;padding:26px 30px;box-shadow:0 18px 40px rgba(31,42,90,.3);display:grid;gap:20px;animation:up .6s ease both}
.cd-top{display:flex;gap:18px;align-items:center}.cd-top img{width:64px;height:64px;border-radius:14px;background:#fff;padding:6px;object-fit:contain}
.cd-k{font-size:12.5px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;opacity:.8}
.cd-hero h1{margin:4px 0 2px;font-size:28px;letter-spacing:-.01em}.cd-sub{font-size:14px;opacity:.88}
.cd-hk{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.cd-hk>div{background:rgba(255,255,255,.12);border-radius:16px;padding:14px 18px}
.cd-hk span{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.06em;opacity:.8}
.cd-hk b{display:block;font-size:30px;margin-top:4px;font-variant-numeric:tabular-nums}.cd-hk em{font-style:normal}
.cd-pres{font-size:22px!important;color:#9ff0c9}
.cd-kpis{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.cd-kpi{background:#fff;border-radius:18px;padding:18px 20px;box-shadow:0 8px 22px rgba(20,27,45,.07);border-top:5px solid var(--c);animation:up .55s ease both;animation-delay:calc(var(--i)*70ms)}
.cd-kpi span{display:block;font-size:12.5px;text-transform:uppercase;letter-spacing:.05em;color:#5a6785}
.cd-kpi b{display:block;font-size:38px;margin:4px 0 2px;color:#141b2d;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.cd-kpi small{font-size:13px;color:#5a6785}
.cd-card{background:#fff;border-radius:18px;padding:20px 22px;box-shadow:0 8px 22px rgba(20,27,45,.07);min-width:0;animation:up .6s ease both;animation-delay:.2s}
.cd-card h3{margin:0 0 14px;font-size:18px;color:#1f2a5a}
.cd-duo{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:18px}
.cd-bars{display:grid;gap:14px}
.cd-bar{display:grid;grid-template-columns:230px minmax(0,1fr) 70px;gap:12px;align-items:center;font-size:14.5px;animation:up .5s ease both;animation-delay:calc(var(--i)*80ms + .25s)}
.cd-bar b{text-align:right;font-size:20px;font-variant-numeric:tabular-nums}
.cd-bt{display:block;height:20px;background:#eef0f6;border-radius:10px;overflow:hidden}
.cd-bt i{display:block;height:100%;width:var(--w);border-radius:10px;animation:grow 1.1s cubic-bezier(.2,.8,.2,1) both;animation-delay:.35s}
.cd-dw{display:flex;gap:20px;align-items:center;flex-wrap:wrap}
.cd-donut{width:220px;height:220px;flex:none}
.cd-arc{animation:arc 1.1s cubic-bezier(.2,.8,.2,1) both}
.cd-dc{font-size:34px;font-weight:800;fill:#141b2d}.cd-ds{font-size:13px;fill:#5a6785}
.cd-leg{flex:1;min-width:220px;display:grid;gap:8px;font-size:14px}
.cd-leg div{display:grid;grid-template-columns:14px 1fr auto 56px;gap:8px;align-items:center}
.cd-leg i{width:12px;height:12px;border-radius:3px}.cd-leg small{color:#5a6785;text-align:right}
.cd-tab{width:100%;border-collapse:collapse;font-size:14px}
.cd-tab th{text-align:left;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:#5a6785;padding:9px 10px;border-bottom:1px solid #e8ebf3;background:#f6f7fb}
.cd-tab td{padding:9px 10px;border-bottom:1px solid #eef0f6;vertical-align:top}
.cd-tab .n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.cd-tab td.neg{color:#b3261e;font-weight:800}.cd-tab td.pos{color:#0b6b4f;font-weight:800}
.cd-tab s{color:#b3261e}
.cd-mini{width:34%;min-width:160px}
.cd-mini i{display:block;height:8px;border-radius:4px;width:var(--w);margin:2px 0;animation:grow 1s ease both;animation-delay:.3s}
.cd-mini i.a,.cd-l2 i.a{background:#c9cfdc}.cd-mini i.d,.cd-l2 i.d{background:#1f2a5a}
.cd-l2{display:flex;gap:16px;font-size:13px;color:#5a6785;margin-top:10px}.cd-l2 i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.cd-det{border-left:6px solid var(--c)}
.cd-dh{display:flex;justify-content:space-between;align-items:baseline;gap:12px}.cd-dh h3{margin:0}.cd-dh b{font-size:28px;color:var(--c);font-variant-numeric:tabular-nums}
.cd-why{margin:6px 0 12px;font-size:14px;color:#3a4566;line-height:1.6}
.cd-mais{margin:8px 0 0;font-size:13px;color:#8a93a8}
.cd-ap{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.cd-ap div{background:#f6f7fb;border-radius:14px;padding:14px 16px;border-left:5px solid var(--c);animation:up .5s ease both;animation-delay:calc(var(--i)*60ms + .3s)}
.cd-ap span{display:block;font-size:12.5px;color:#5a6785;text-transform:uppercase;letter-spacing:.04em}
.cd-ap b{display:block;font-size:22px;margin-top:4px;font-variant-numeric:tabular-nums;white-space:nowrap}
.cd-nota{font-size:13px;color:#8a93a8;margin:12px 0 0}
.cd-ok{border-left:6px solid #1baf7a}.cd-ok p{margin:0;font-size:15px;color:#3a4566}
.cd-rod{font-size:12.5px;color:#8a93a8;text-align:center;line-height:1.6;padding:4px 20px 10px}
@keyframes up{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
@keyframes grow{from{width:0}}
@keyframes arc{from{stroke-dasharray:0 1000}}
@media (max-width:1000px){.cd-duo{grid-template-columns:1fr}.cd-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.cd-bar{grid-template-columns:150px minmax(0,1fr) 56px}}
@media print{body{background:#fff}.cd *{animation:none!important}.cd-card,.cd-kpi,.cd-hero{box-shadow:none;break-inside:avoid}}
@media (prefers-reduced-motion:reduce){.cd *{animation:none!important}}
'''

JS = '''
(function(){
  var br=function(v){return 'R$ '+v.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});};
  var it=function(v){return Math.round(v).toLocaleString('pt-BR');};
  var els=document.querySelectorAll('[data-n]');
  var ani=!(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  els.forEach(function(el){
    var alvo=parseFloat(el.getAttribute('data-n'))||0, f=el.getAttribute('data-fmt')==='brl'?br:it;
    if(!ani){el.textContent=f(alvo);return;}
    var t0=null,dur=1100;
    function passo(t){if(t0===null)t0=t;var k=Math.min(1,(t-t0)/dur),e=1-Math.pow(1-k,3);el.textContent=f(alvo*e);if(k<1)requestAnimationFrame(passo);else el.textContent=f(alvo);}
    requestAnimationFrame(passo);
  });
})();
'''


if __name__ == '__main__':  # teste manual: python corretor_dash.py original.txt corrigido.txt resumo.json saida.html
    import sys
    o = open(sys.argv[1], encoding='utf-8', errors='replace', newline='').read()
    c = open(sys.argv[2], encoding='utf-8', errors='replace', newline='').read()
    r = json.load(open(sys.argv[3], encoding='utf-8'))
    open(sys.argv[4], 'w', encoding='utf-8').write(gerar_html(o, c, r))

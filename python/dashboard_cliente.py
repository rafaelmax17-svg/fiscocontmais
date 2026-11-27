"""Dashboard SPED (EFD ICMS/IPI) para o CLIENTE — modelo exportado em HTML/PDF.

A tela do sistema continua com o dashboard de fiscal_core.gerar_dashboard_sped_html; este modelo é só o
arquivo que vai para o cliente. Recebe o dicionário de fiscal_core.parse_sped e devolve o HTML completo
(autocontido, com animações em CSS que ficam desligadas na impressão/PDF).
"""
import html as _html
import math
import re

# ----------------------------------------------------------------------------------------------------------- #
# Formatação
# ----------------------------------------------------------------------------------------------------------- #
def _brl(v):
    return f'{(v or 0):,.2f}'.replace(',', '§').replace('.', ',').replace('§', '.')


def _R(v):
    return 'R$ ' + _brl(v)


def _esc(s):
    return _html.escape('' if s is None else str(s))


def _pct(a, b):
    return (a / b * 100) if b else 0.0


def _mil(v):
    v = abs(v or 0)
    if v >= 10000:
        return f'{v / 1000:,.0f}'.replace(',', '.') + ' mil'
    if v >= 1000:
        return f'{v / 1000:.1f}'.replace('.', ',') + ' mil'
    return _brl(v)


def _cnpj(c):
    d = re.sub(r'\D', '', c or '')
    return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}' if len(d) == 14 else (c or '')


_MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro',
          'Novembro', 'Dezembro']


def _competencia(emp):
    ini, fim = (emp.get('periodo_ini') or ''), (emp.get('periodo_fim') or '')
    a, b = ini.split('/'), fim.split('/')
    if len(a) == 3 and len(b) == 3 and a[1:] == b[1:] and a[1].isdigit() and 1 <= int(a[1]) <= 12:
        return f'{_MESES[int(a[1]) - 1]}/{a[2]}', f'{a[0]}/{a[1]} a {b[0]}/{b[1]}/{b[2]}'
    return emp.get('periodo', ''), ''


# ----------------------------------------------------------------------------------------------------------- #
# CFOP — descrição curta para o cliente (Convênio s/nº de 1970, Anexo: códigos fiscais de operações)
# A descrição vale para o grupo interno (1/5) e para o interestadual (2/6), que recebe "(outra UF)".
# ----------------------------------------------------------------------------------------------------------- #
_ENT = {
    '101': 'Compra p/ industrialização', '102': 'Compra p/ comercialização',
    '116': 'Compra p/ industrialização (entrega futura)', '117': 'Compra p/ comercialização (entrega futura)',
    '118': 'Compra p/ comercialização (venda à ordem)', '120': 'Compra p/ industrialização (venda à ordem)',
    '121': 'Compra p/ comercialização (venda à ordem)', '124': 'Industrialização feita por outra empresa',
    '151': 'Transferência p/ industrialização', '152': 'Transferência p/ comercialização',
    '153': 'Transferência de energia elétrica', '201': 'Devolução de venda de produção',
    '202': 'Devolução de venda de mercadoria', '203': 'Devolução de venda de produção p/ ZFM/ALC',
    '204': 'Devolução de venda de mercadoria p/ ZFM/ALC', '208': 'Devolução de transferência de produção',
    '209': 'Devolução de transferência de mercadoria', '251': 'Compra de energia elétrica p/ distribuição',
    '252': 'Compra de energia elétrica (estab. industrial)', '253': 'Compra de energia elétrica (estab. comercial)',
    '302': 'Serviço de comunicação (estab. industrial)', '303': 'Serviço de comunicação (estab. comercial)',
    '352': 'Frete (estab. industrial)', '353': 'Frete (estab. comercial)',
    '401': 'Compra p/ industrialização c/ ST', '403': 'Compra p/ comercialização c/ ST',
    '406': 'Compra de ativo imobilizado c/ ST', '407': 'Compra de uso e consumo c/ ST',
    '408': 'Transferência p/ industrialização c/ ST', '409': 'Transferência c/ ST',
    '410': 'Devolução de venda de produção c/ ST', '411': 'Devolução de venda de mercadoria c/ ST',
    '551': 'Compra de ativo imobilizado', '552': 'Transferência de ativo imobilizado',
    '553': 'Devolução de venda de ativo imobilizado', '556': 'Compra de material de uso e consumo',
    '557': 'Transferência de material de uso e consumo', '602': 'Saldo credor de ICMS recebido de outro estab.',
    '605': 'Saldo devedor de ICMS recebido de outro estab.', '651': 'Compra de combustível p/ industrialização',
    '652': 'Compra de combustível p/ comercialização', '653': 'Combustível p/ uso e consumo',
    '658': 'Transferência de combustível p/ comercialização', '659': 'Transferência de combustível p/ industrialização',
    '901': 'Entrada p/ industrialização por encomenda', '902': 'Retorno de remessa p/ industrialização',
    '904': 'Retorno de remessa p/ venda fora do estabelecimento', '908': 'Entrada de bem em comodato',
    '909': 'Retorno de bem em comodato', '910': 'Entrada de bonificação, doação ou brinde',
    '911': 'Entrada de amostra grátis', '912': 'Entrada p/ demonstração', '913': 'Retorno de demonstração',
    '915': 'Entrada p/ conserto ou reparo', '916': 'Retorno de conserto ou reparo',
    '920': 'Entrada de vasilhame ou sacaria', '921': 'Retorno de vasilhame ou sacaria',
    '922': 'Simples faturamento (compra p/ entrega futura)', '923': 'Mercadoria recebida em venda à ordem',
    '926': 'Reclassificação de mercadoria (kit)', '933': 'Serviço tributado pelo ISSQN',
    '949': 'Outra entrada não especificada',
}
_SAI = {
    '101': 'Venda de produção', '102': 'Venda de mercadoria', '109': 'Venda de produção p/ ZFM / Área de Livre Comércio',
    '110': 'Venda p/ ZFM / Área de Livre Comércio', '116': 'Venda de produção (entrega futura)',
    '117': 'Venda de mercadoria (entrega futura)', '118': 'Venda de produção (venda à ordem)',
    '119': 'Venda de mercadoria (venda à ordem)', '120': 'Venda de mercadoria entregue pelo remetente (venda à ordem)',
    '124': 'Industrialização p/ outra empresa', '151': 'Transferência de produção', '152': 'Transferência de mercadoria',
    '201': 'Devolução de compra p/ industrialização', '202': 'Devolução de compra p/ comercialização',
    '208': 'Devolução de transferência p/ industrialização', '209': 'Devolução de transferência p/ comercialização',
    '353': 'Serviço de transporte (estab. comercial)',
    '401': 'Venda de produção c/ ST (substituto)', '403': 'Venda de mercadoria c/ ST (substituto)',
    '405': 'Venda c/ ST (substituído)', '408': 'Transferência de produção c/ ST', '409': 'Transferência c/ ST',
    '410': 'Devolução de compra p/ industrialização c/ ST', '411': 'Devolução de compra p/ comercialização c/ ST',
    '413': 'Devolução de compra de uso e consumo c/ ST', '551': 'Venda de ativo imobilizado',
    '552': 'Transferência de ativo imobilizado', '553': 'Devolução de compra de ativo imobilizado',
    '556': 'Devolução de compra de uso e consumo', '557': 'Transferência de material de uso e consumo',
    '601': 'Transferência de crédito acumulado de ICMS', '602': 'Transferência de saldo credor de ICMS',
    '605': 'Transferência de saldo devedor de ICMS', '655': 'Venda de combustível p/ comercialização',
    '656': 'Venda de combustível a consumidor final', '659': 'Transferência de combustível',
    '901': 'Remessa p/ industrialização por encomenda', '902': 'Retorno de industrialização por encomenda',
    '904': 'Remessa p/ venda fora do estabelecimento', '908': 'Remessa de bem em comodato',
    '909': 'Retorno de bem em comodato', '910': 'Remessa em bonificação, doação ou brinde',
    '911': 'Remessa de amostra grátis', '912': 'Remessa p/ demonstração', '913': 'Retorno de demonstração',
    '915': 'Remessa p/ conserto ou reparo', '916': 'Retorno de conserto ou reparo',
    '917': 'Remessa em consignação mercantil', '920': 'Remessa de vasilhame ou sacaria',
    '921': 'Devolução de vasilhame ou sacaria', '922': 'Simples faturamento (venda p/ entrega futura)',
    '923': 'Remessa por conta e ordem de terceiros', '927': 'Baixa de estoque (perda/deterioração)',
    '929': 'Lançamento de operação já registrada em cupom fiscal', '933': 'Serviço tributado pelo ISSQN',
    '949': 'Outra saída não especificada',
}
_ESPEC = {'1932': 'Frete iniciado em outra UF', '2932': 'Frete iniciado em outra UF',
          '6107': 'Venda de produção a não contribuinte (outra UF)', '6108': 'Venda a não contribuinte (outra UF)'}
_TRANSF = {'151', '152', '153', '208', '209', '408', '409', '552', '557', '602', '658', '659'}


def cfop_desc(c, fallback=''):
    c = (c or '').strip()
    if c in _ESPEC:
        return _ESPEC[c]
    if len(c) == 4:
        g, s = c[0], c[1:]
        if g in '12' and s in _ENT:
            return _ENT[s] + (' (outra UF)' if g == '2' else '')
        if g in '56' and s in _SAI:
            return _SAI[s] + (' (outra UF)' if g == '6' else '')
        if g == '3':
            return 'Importação' if s not in _ENT else _ENT[s] + ' (importação)'
        if g == '7':
            return 'Exportação' if s not in _SAI else _SAI[s] + ' (exportação)'
    return fallback or ('CFOP ' + c)


def _eh_transf(c):
    return len(c or '') == 4 and c[1:] in _TRANSF


# ----------------------------------------------------------------------------------------------------------- #
# Gráficos (SVG)
# ----------------------------------------------------------------------------------------------------------- #
_NAVY, _NAVY2, _OR2 = '#1f2a5a', '#2b3a72', '#e8611c'


def _waterfall(w, h, passos):
    """passos: (rótulo, valor, tipo) — tipo: total | pos (soma) | neg (abate) | res (resultado)."""
    passos = [p for p in passos if p[1] or p[2] in ('total', 'res', 'cred')]
    if not passos:
        return ''
    pl, pb, pt = 6, 40, 30
    n = len(passos)
    bw = (w - pl * 2) / n
    run, topo = 0.0, 0.0
    for _, v, k in passos:
        if k == 'total':
            run = v
        elif k == 'pos':
            run += v
        elif k == 'neg':
            run -= v
        topo = max(topo, run, v if k in ('total', 'res', 'cred') else 0)
    sc = (h - pb - pt) / (topo or 1)
    cores = {'total': (_NAVY2, _NAVY), 'pos': ('#ff7b80', '#e5484d'), 'neg': ('#34d399', '#0ea472'),
             'res': ('#ff9a56', _OR2), 'cred': ('#34d399', '#0ea472')}
    o, run = [], 0.0
    for i, (lab, v, k) in enumerate(passos):
        x = pl + i * bw + bw * .18
        ww = bw * .64
        if k == 'total':
            y0, y1, run = 0, v, v
        elif k == 'pos':
            y0, y1 = run, run + v
            run = y1
        elif k == 'neg':
            y0, y1 = run - v, run
            run = y0
        else:
            y0, y1 = 0, v
        y0, y1 = max(y0, 0), max(y1, 0)
        yy = h - pb - y1 * sc
        hh = max((y1 - y0) * sc, 3)
        c1, c2 = cores[k]
        o.append(f'<defs><linearGradient id="wf{i}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{c1}"/>'
                 f'<stop offset="1" stop-color="{c2}"/></linearGradient></defs>')
        o.append(f'<rect class="wfb" style="animation-delay:{.35 + i * .12:.2f}s" x="{x:.1f}" y="{yy:.1f}" width="{ww:.1f}" '
                 f'height="{hh:.1f}" rx="6" fill="url(#wf{i})"/>')
        if i < n - 1:
            ny = h - pb - max(run, 0) * sc
            o.append(f'<line x1="{x + ww:.1f}" x2="{x + bw:.1f}" y1="{ny:.1f}" y2="{ny:.1f}" stroke="#aab3cc" stroke-dasharray="3 3"/>')
        sg = {'neg': '− ', 'pos': '+ '}.get(k, '')
        o.append(f'<text x="{x + ww / 2:.1f}" y="{yy - 7:.1f}" text-anchor="middle" font-size="11.5" font-weight="700" '
                 f'fill="{_NAVY}">{sg}{_mil(v)}</text>')
        o.append(f'<text x="{x + ww / 2:.1f}" y="{h - pb + 17:.1f}" text-anchor="middle" font-size="11" fill="#5b6488">{_esc(lab)}</text>')
    return f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}">{"".join(o)}</svg>'


def _donut(partes, topo, grande, sub, size=196, r=74, th=26):
    c = size / 2
    L = 2 * math.pi * r
    tot = sum(v for _, v, _ in partes) or 1
    o = [f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="#eef1f7" stroke-width="{th}"/>']
    off = 0.0
    for i, (_, v, cor) in enumerate(partes):
        seg = L * v / tot
        if seg <= 0:
            continue
        gap = 3 if seg > 8 else 0
        o.append(f'<circle class="dseg" style="--L:{L:.1f};animation-delay:{.4 + i * .18:.2f}s" cx="{c}" cy="{c}" r="{r}" fill="none" '
                 f'stroke="{cor}" stroke-width="{th}" stroke-dasharray="{max(seg - gap, .5):.1f} {L:.1f}" '
                 f'stroke-dashoffset="{-off:.1f}" transform="rotate(-90 {c} {c})"/>')
        off += seg
    o.append(f'<text x="{c}" y="{c - 14}" text-anchor="middle" font-size="10.5" letter-spacing=".06em" fill="#7a83a6">{_esc(topo)}</text>')
    o.append(f'<text x="{c}" y="{c + 10}" text-anchor="middle" font-size="23" font-weight="800" fill="{_NAVY}">{_esc(grande)}</text>')
    o.append(f'<text x="{c}" y="{c + 27}" text-anchor="middle" font-size="10.5" fill="#7a83a6">{_esc(sub)}</text>')
    return f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}">{"".join(o)}</svg>'


def _gauge(pct, w=220):
    mx = max(12.0, math.ceil(pct * 1.3))
    h = w * .62
    cx, cy, r, th = w / 2, h - 14, w * .40, 18
    def pt(a):
        return cx + r * math.cos(a), cy - r * math.sin(a)
    x0, y0 = pt(math.pi)
    x1, y1 = pt(0)
    xa, ya = pt(math.pi - math.pi * min(max(pct, 0) / mx, 1))
    arco = (f'<path class="gval" pathLength="100" d="M{x0:.1f},{y0:.1f} A{r},{r} 0 0 1 {xa:.1f},{ya:.1f}" fill="none" '
            f'stroke="url(#gg)" stroke-width="{th}" stroke-linecap="round"/>' if pct > 0 else '')
    return (f'<svg viewBox="0 0 {w} {h:.0f}" width="{w}" height="{h:.0f}"><defs><linearGradient id="gg" x1="0" x2="1">'
            f'<stop offset="0" stop-color="#ffb37a"/><stop offset="1" stop-color="{_OR2}"/></linearGradient></defs>'
            f'<path d="M{x0:.1f},{y0:.1f} A{r},{r} 0 0 1 {x1:.1f},{y1:.1f}" fill="none" stroke="#eef1f7" stroke-width="{th}" stroke-linecap="round"/>'
            f'{arco}<circle class="gdot" cx="{xa:.1f}" cy="{ya:.1f}" r="7" fill="#fff" stroke="{_OR2}" stroke-width="3"/>'
            f'<text x="{cx}" y="{cy - 22}" text-anchor="middle" font-size="34" font-weight="800" fill="{_NAVY}">{_brl(pct)}%</text>'
            f'<text x="{cx}" y="{cy}" text-anchor="middle" font-size="11" fill="#7a83a6">do faturamento</text></svg>')


# ----------------------------------------------------------------------------------------------------------- #
# Estilo
# ----------------------------------------------------------------------------------------------------------- #
_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#eef1f7;font-family:Inter,'Segoe UI',system-ui,-apple-system,sans-serif;color:#1f2a5a;-webkit-font-smoothing:antialiased}
.num{font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.band{background:radial-gradient(700px 300px at 85% 0%,#f07a2e40,transparent 60%),radial-gradient(600px 400px at 10% 120%,#4f6bd860,transparent 60%),linear-gradient(135deg,#161d45,#25336b);padding:30px 0 92px;color:#fff}
.in,.wrap,.bento{width:1180px;margin:0 auto}
.top{display:flex;justify-content:space-between;align-items:center}
.brand{display:flex;gap:14px;align-items:center}.brand img{width:50px;height:50px;border-radius:14px;background:#fff;padding:6px}
.brand b{font-size:18px;display:block}.brand span{font-size:12.5px;color:#aab4dd}
.per{text-align:right;font-size:12.5px;color:#aab4dd}.per b{display:block;color:#fff;font-size:15px}
.emp{margin:30px 0 10px;display:flex;align-items:flex-end;justify-content:space-between;gap:24px}
.emp h1{margin:0;font-size:30px;letter-spacing:-.02em}.emp p{margin:6px 0 0;color:#aab4dd;font-size:13px}
.fat{text-align:right;flex-shrink:0}.fat small{display:block;font-size:11px;letter-spacing:.1em;color:#aab4dd;font-weight:600}
.fat b{display:block;font-size:30px;font-weight:800;letter-spacing:-.02em;margin-top:2px}
.tag{display:inline-block;margin-bottom:12px;background:#10b98126;color:#5eead4;border:1px solid #10b98155;border-radius:999px;padding:6px 12px;font-size:12px;font-weight:600}
.bento{margin-top:-64px;display:grid;grid-template-columns:repeat(12,1fr);gap:16px}
.c{background:#fff;border-radius:22px;padding:22px 24px;box-shadow:0 10px 30px #1f2a5a12}
.c h3{margin:0;font-size:15px}.c .sub{font-size:12px;color:#8a92b2;margin:3px 0 14px}
.lg{display:flex;flex-direction:column;gap:10px;font-size:12.5px;color:#46507a}.lg i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:8px}
.lg b{float:right;color:#1f2a5a;margin-left:12px}
.gnote{font-size:12px;color:#8a92b2;margin-top:4px;text-align:center}.gnote b{color:#1f2a5a}
.wrap{padding:6px 0 30px}
.sec{display:flex;align-items:center;gap:12px;margin:26px 0 14px}.sec span{font-size:12px;font-weight:800;color:#fff;background:#1f2a5a;border-radius:8px;padding:4px 8px}
.sec h2{margin:0;font-size:18px;letter-spacing:-.01em}.sec em{font-style:normal;color:#8a92b2;font-size:12.5px;margin-left:4px}
.flow{display:grid;align-items:stretch}
.st{background:#fff;border:1px solid #e6eaf3;border-radius:18px;padding:16px 18px;box-shadow:0 8px 24px #1f2a5a0d}
.st small{font-size:11px;font-weight:700;letter-spacing:.08em;color:#8a92b2}.st b{display:block;font-size:19px;margin:6px 0 4px;letter-spacing:-.02em}.st p{margin:0;font-size:12px;color:#7a83a6}
.st .m{height:6px;background:#eef1f7;border-radius:9px;margin-top:12px;overflow:hidden}.st .m i{display:block;height:100%;border-radius:9px}
.arr{display:flex;align-items:center;justify-content:center;color:#b6bdd6;font-size:20px;font-weight:300}
.st.res{background:linear-gradient(135deg,#e8611c,#ff9a56);color:#fff;border:0;box-shadow:0 14px 30px #e8611c40}.st.res small,.st.res p{color:#fff3ea}.st.res b{font-size:24px}
.st.cred{background:linear-gradient(135deg,#0ea472,#34d399);color:#fff;border:0;box-shadow:0 14px 30px #0ea47240}.st.cred small,.st.cred p{color:#eafff6}.st.cred b{font-size:24px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.card{background:#fff;border:1px solid #e6eaf3;border-radius:20px;padding:20px 22px;box-shadow:0 8px 24px #1f2a5a0d}
.card h4{margin:0 0 12px;font-size:14px}
.stack{display:flex;height:34px;border-radius:10px;overflow:hidden;gap:2px;margin:4px 0 14px}.stack div{height:100%}
table{width:100%;border-collapse:collapse;font-size:12.5px}td{padding:7px 0;border-bottom:1px solid #f1f3f8;color:#46507a}tr:last-child td{border:0}
td.v{text-align:right;font-weight:700;color:#1f2a5a;white-space:nowrap}td.p{text-align:right;color:#9aa2bf;width:62px;padding-right:10px;white-space:nowrap}
.sw{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:8px}
.cfb{font-weight:700;color:#1f2a5a;margin-right:6px}
.tr{font-size:9.5px;font-weight:700;color:#6b55d6;background:#efeaff;border-radius:5px;padding:1px 6px;margin-left:6px}
.vafb{display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1.25fr;gap:10px}
.vb{border-radius:16px;padding:14px 16px;background:#f7f9fd}.vb small{font-size:11.5px;color:#7a83a6}.vb b{display:block;font-size:17px;margin-top:4px}
.vb.r{background:linear-gradient(135deg,#1f2a5a,#2b3a72);color:#fff}.vb.r small{color:#c9d1ee}.vb.r b{font-size:21px}
.note{font-size:11.5px;color:#8a92b2;margin-top:8px}
.inl{display:flex;align-items:center}.inl .bar{flex:1;height:6px;border-radius:9px;background:#f1f3f8;overflow:hidden;margin:0 12px}.inl .bar i{display:block;height:100%;border-radius:9px}
.trf td{background:#f6f3ff;color:#6b55d6;font-weight:600;padding:9px 10px}
.aj3{font-size:9.5px;font-weight:800;border-radius:5px;padding:2px 6px;margin-right:8px}
.vazio{font-size:12.5px;color:#8a92b2}
.subh{display:flex;justify-content:space-between;align-items:center;margin:6px 0 2px;padding:6px 10px;border-radius:9px;background:#fff4ec;font-size:12px;font-weight:700;color:#c2410c}
.subh.o{background:#f3f0ff;color:#6b55d6;margin-top:14px}
.foot{text-align:center;font-size:11.5px;color:#8a92b2;margin-top:24px}
/* animações: o estado final é o estilo normal; as animações só partem do estado inicial */
@keyframes up{from{opacity:0;transform:translateY(14px)}}
@keyframes grow{from{width:0}}
@keyframes rise{from{transform:scaleY(0)}}
@keyframes dseg{from{stroke-dasharray:0 var(--L)}}
@keyframes gdraw{from{stroke-dashoffset:100}}
@keyframes pop{from{opacity:0;transform:scale(.4)}}
.anim{animation:up .6s cubic-bezier(.2,.8,.2,1) both}
.m i,.bar i,.stack div{animation:grow 1.1s cubic-bezier(.2,.8,.2,1) .45s both}
.wfb{transform-box:fill-box;transform-origin:50% 100%;animation:rise .7s cubic-bezier(.2,.8,.2,1) both}
.dseg{animation:dseg .9s cubic-bezier(.2,.8,.2,1) both}
.gval{stroke-dasharray:100;animation:gdraw 1.2s cubic-bezier(.2,.8,.2,1) .4s both}
.gdot{transform-box:fill-box;transform-origin:center;animation:pop .4s ease 1.4s both}
@media print{*{animation:none!important}body{zoom:.92}.c,.card,.st,.sec,tr{break-inside:avoid}.wrap{padding-bottom:0}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""

_JS = """<script>
(function(){
  function fmt(n){return 'R$ '+n.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});}
  document.querySelectorAll('.cnt').forEach(function(el){
    var t=parseFloat(el.dataset.t); if(!isFinite(t)) return; var t0=performance.now(), dur=1200;
    function st(now){var p=Math.min(1,(now-t0)/dur); p=1-Math.pow(1-p,3); el.textContent=fmt(t*p); if(p<1) requestAnimationFrame(st);}
    requestAnimationFrame(st);
  });
})();
</script>"""

_PAL_E = ['#1f2a5a', '#2b3a72', '#3d55c4', '#5470d6', '#7088e0', '#91a3ea', '#b3c0f1', '#d2dbf7']
_PAL_O = ['#6b55d6', '#8b78e0', '#a597ea', '#bdb3f0', '#d2cbf5', '#e2ddf8', '#ece9fa', '#f3f1fc']
_PAL_S = ['#c2410c', '#e8611c', '#f08a3c', '#f4a261', '#f7bc8a', '#f9cfa9', '#fbe0c7', '#fdeee0']


def _cnt(v, extra=''):
    return f'<b class="num cnt"{extra} data-t="{(v or 0):.2f}">{_R(v)}</b>'


# ----------------------------------------------------------------------------------------------------------- #
# HTML
# ----------------------------------------------------------------------------------------------------------- #
def gerar(d, logo=''):
    emp = d.get('empresa') or {}
    ap = d.get('apuracao') or {}

    def g(k):
        return float(ap.get(k, 0.0) or 0.0)

    fat = float(d.get('faturamento_bruto') or 0)
    deb = g('debitos')
    aj_deb = g('ajuste_debitos_doc') + g('ajuste_debitos') + g('estornos_cred')
    cred = g('creditos')
    aj_cred = g('ajuste_creditos_doc') + g('ajuste_creditos') + g('estornos_deb')
    sc_ant, ded = g('saldo_credor_ant'), g('deducoes')
    rec, sc_tr = g('icms_recolher'), g('saldo_credor_transp')
    deb_tot = deb + aj_deb
    aliq = float(d.get('aliquota_efetiva') or 0)
    credor = rec <= 0 and sc_tr > 0
    comp, per_txt = _competencia(emp)
    uf = _esc(emp.get('uf', ''))

    # ---- topo ----
    logo_html = f'<img src="{logo}" alt="Liddera">' if logo else ''
    band = f"""<div class="band"><div class="in">
<div class="top anim"><div class="brand">{logo_html}<div><b>Liddera | Inteligência em Negócios</b><span>Relatório mensal do ICMS</span></div></div>
<div class="per">Período<b>{_esc(comp)}</b>{_esc(per_txt)}{' · ' + uf if uf else ''}</div></div>
<div class="emp anim" style="animation-delay:.08s"><div><h1>{_esc(emp.get('empresa', ''))}</h1><p>CNPJ {_esc(_cnpj(emp.get('cnpj')))} · IE {_esc(emp.get('ie', ''))}{' · ' + uf if uf else ''}</p></div>
<div class="fat"><span class="tag">● Contribuinte do ICMS</span><small>FATURAMENTO BRUTO DO MÊS</small>{_cnt(fat)}</div></div></div></div>"""

    # ---- linha de gráficos ----
    if credor:
        cred_tot = cred + aj_cred + sc_ant
        dn = _donut([('u', deb_tot, '#3d55c4'), ('s', sc_tr, '#10b981')], 'CRÉDITOS', _mil(cred_tot), _R(cred_tot))
        lg = (f'<div class="lg"><div><i style="background:#3d55c4"></i>Usado p/ abater os débitos<b>{_brl(_pct(deb_tot, cred_tot))}%</b></div>'
              f'<div><i style="background:#10b981"></i>Saldo credor p/ o próximo mês<b>{_brl(_pct(sc_tr, cred_tot))}%</b></div></div>')
        d_tit, d_sub = 'Créditos do mês × débitos', f'Créditos, ajustes e saldo anterior ({_R(cred_tot)})'
    else:
        partes = [('Créditos de compras', cred, '#3d55c4'), ('Ajustes a crédito', aj_cred, '#10b981'),
                  ('Saldo credor anterior', sc_ant, '#14b8a6'), ('Deduções', ded, '#8b6fe0'), ('A recolher', rec, _OR2)]
        partes = [p for p in partes if p[1] > 0]
        base = sum(p[1] for p in partes) or 1
        dn = _donut(partes, 'DÉBITOS', _mil(deb_tot), _R(deb_tot))
        lg = '<div class="lg">' + ''.join(f'<div><i style="background:{c}"></i>{_esc(n)}<b>{_brl(_pct(v, base))}%</b></div>'
                                         for n, v, c in partes) + '</div>'
        d_tit = 'Para onde foi o ICMS dos débitos'
        d_sub = f'Débitos + ajustes a débito ({_R(deb_tot)})' if aj_deb else f'Débitos do mês ({_R(deb_tot)})'
    passos = [('Débitos', deb, 'total'), ('Aj. déb.', aj_deb, 'pos'), ('Créditos', cred, 'neg'), ('Aj. créd.', aj_cred, 'neg'),
              ('Saldo ant.', sc_ant, 'neg'), ('Deduções', ded, 'neg')]
    passos.append(('Saldo credor', sc_tr, 'cred') if credor else ('Recolher', rec, 'res'))
    wf = _waterfall(330, 205, passos)
    nota_g = f'A cada R$ 100 vendidos, <b>R$ {_brl(aliq)}</b> de ICMS' if fat else ''
    bento = f"""<div class="bento">
<div class="c anim" style="grid-column:span 5;animation-delay:.15s"><h3>{d_tit}</h3><div class="sub">{d_sub}</div>
<div style="display:flex;gap:22px;align-items:center">{dn}<div style="flex:1">{lg}</div></div></div>
<div class="c anim" style="grid-column:span 3;animation-delay:.22s"><h3>Alíquota efetiva</h3><div class="sub">ICMS a recolher ÷ faturamento</div>
<div style="text-align:center">{_gauge(aliq)}</div><div class="gnote">{nota_g}</div></div>
<div class="c anim" style="grid-column:span 4;animation-delay:.29s"><h3>Apuração</h3><div class="sub">Do débito ao valor {'do saldo credor' if credor else 'a recolher'}</div>{wf}</div>
</div>"""

    # ---- 01 apuração passo a passo ----
    def st(tit, v, txt, cor=None, barra=None, bcor=None):
        b = f'<div class="m"><i style="width:{max(min(barra, 100), 1.5):.1f}%;background:{bcor}"></i></div>' if barra is not None else ''
        return f'<div class="st"><small>{tit}</small><b class="num" style="color:{cor or _NAVY}">{_R(v)}</b><p>{txt}</p>{b}</div>'
    cards = [('', st('DÉBITOS', deb, 'ICMS destacado nas saídas', barra=100, bcor=_NAVY2))]
    if aj_deb:
        cards.append(('+', st('AJUSTES A DÉBITO', aj_deb, 'Aumentam o imposto · detalhe na seção 05', '#d93b41', _pct(aj_deb, deb_tot), '#e5484d')))
    cards.append(('−', st('CRÉDITOS', cred, f'ICMS das compras · {_brl(_pct(cred, deb_tot))}%', '#0a8a5f', _pct(cred, deb_tot), '#10b981')))
    if aj_cred:
        cards.append(('−', st('AJUSTES A CRÉDITO', aj_cred, f'Reduzem o imposto · {_brl(_pct(aj_cred, deb_tot))}%', '#0a8a5f', _pct(aj_cred, deb_tot), '#10b981')))
    if sc_ant:
        cards.append(('−', st('SALDO CREDOR ANTERIOR', sc_ant, 'Sobra do mês anterior', '#0a8a5f')))
    if ded:
        cards.append(('−', st('DEDUÇÕES', ded, 'Abatimentos do imposto apurado', '#0a8a5f')))
    if credor:
        res = f'<div class="st cred"><small>SALDO CREDOR A TRANSPORTAR</small><b class="num">{_R(sc_tr)}</b><p>Não há ICMS a recolher; a sobra vai para o próximo mês</p></div>'
    else:
        res = f'<div class="st res"><small>ICMS A RECOLHER</small><b class="num">{_R(rec)}</b><p>{_brl(_pct(rec, deb_tot))}% dos débitos</p></div>'
    cards.append(('=', res))
    cols, flow = [], []
    for i, (sinal, h) in enumerate(cards):
        if i:
            cols.append('22px')
            flow.append(f'<div class="arr">{sinal}</div>')
        cols.append('1.1fr' if i == len(cards) - 1 else '1fr')
        flow.append(h)
    sec01 = (f'<div class="sec anim"><span>01</span><h2>Apuração do ICMS</h2><em>como chegamos ao valor {"do saldo credor" if credor else "a recolher"}</em></div>'
             f'<div class="flow anim" style="grid-template-columns:{" ".join(cols)}">{"".join(flow)}</div>')

    # ---- 02 VAF ----
    vr = d.get('vaf_ro')
    if vr:   # Rondônia: Decreto 11.908/2005, art. 8º, § 3º (red. Decreto 22.533/2018) — ΣVS − ΣVE da EFD
        vaf_box = (f'<div class="vafb" style="grid-template-columns:1fr 1fr 1fr 1fr 1.25fr">'
                   f'<div class="vb"><small>+ Vendas</small><b class="num" style="color:#0a8a5f">{_R(vr["vendas"])}</b></div>'
                   f'<div class="vb"><small>+ Transferências e demais saídas</small><b class="num" style="color:#0a8a5f">{_R(vr["saidas"] - vr["vendas"])}</b></div>'
                   f'<div class="vb"><small>− Compras e demais entradas</small><b class="num" style="color:#d93b41">{_R(vr["entradas"] - vr["transf_entradas"])}</b></div>'
                   f'<div class="vb"><small>− Transferências recebidas</small><b class="num" style="color:#d93b41">{_R(vr["transf_entradas"])}</b></div>'
                   f'<div class="vb r"><small>= Valor adicionado</small>{_cnt(vr["vaf"])}</div></div>'
                   f'<div class="note">Regra de Rondônia (Decreto 11.908/2005, art. 8º, § 3º): todas as saídas menos todas as entradas da escrituração fiscal, '
                   f'inclusive transferências entre estabelecimentos. Ficam fora ativo imobilizado, uso e consumo, bonificações, remessas e '
                   f'outros CFOPs listados no decreto (saídas {_R(vr["excl_saidas"])} · entradas {_R(vr["excl_entradas"])}). '
                   f'O VAF compõe o índice de participação do município no ICMS.</div>')
    else:
        vaf_box = f"""<div class="vafb"><div class="vb"><small>+ Vendas</small><b class="num" style="color:#0a8a5f">{_R(fat)}</b></div>
<div class="vb"><small>− Devolução de vendas</small><b class="num" style="color:#d93b41">{_R(d.get('dev_vendas'))}</b></div>
<div class="vb"><small>− Compras p/ comercialização/industrialização</small><b class="num" style="color:#d93b41">{_R(d.get('entradas_brutas'))}</b></div>
<div class="vb"><small>+ Devolução de compras</small><b class="num">{_R(d.get('dev_compras'))}</b></div>
<div class="vb r"><small>= Valor adicionado</small>{_cnt(d.get('valor_adicionado'))}</div></div>
<div class="note">Não entram no VAF: uso e consumo ({_R(d.get('uso_consumo'))}) e imobilizado ({_R(d.get('imobilizado'))}). O VAF compõe o índice de participação do município no ICMS.</div>"""
    sec02 = (f'<div class="sec anim"><span>02</span><h2>VAF Fiscal</h2><em>valor adicionado no período</em></div>'
             f'<div class="card anim">{vaf_box}</div>')

    # ---- 03 CFOP ----
    def bloco_cfop(lista, pal, tit):
        lista = [r for r in (lista or []) if (r.get('valor') or 0) > 0][:8]
        if not lista:
            return f'<div class="card"><h4>{tit}</h4><div class="vazio">Sem movimento no período.</div></div>'
        tot = sum(r['valor'] for r in lista)
        stack = ''.join(f'<div style="width:{_pct(r["valor"], tot):.2f}%;background:{pal[i]};animation-delay:{.45 + i * .06:.2f}s"></div>'
                        for i, r in enumerate(lista))
        linhas = ''.join(
            f'<tr><td><span class="sw" style="background:{pal[i]}"></span><span class="cfb">{_esc(r["cfop"])}</span>'
            f'{_esc(cfop_desc(r["cfop"], r.get("desc")))}{"<span class=tr>TRANSF.</span>" if _eh_transf(r["cfop"]) else ""}</td>'
            f'<td class="p">{r.get("nfs", 0)} NF</td><td class="v num">{_R(r["valor"])}</td><td class="p">{_brl(_pct(r["valor"], tot))}%</td></tr>'
            for i, r in enumerate(lista))
        return f'<div class="card"><h4>{tit} · {_R(tot)}</h4><div class="stack">{stack}</div><table>{linhas}</table></div>'
    def bloco_saidas(lista):
        lista = [r for r in (lista or []) if (r.get('valor') or 0) > 0]
        if not lista:
            return '<div class="card"><h4>Saídas</h4><div class="vazio">Sem movimento no período.</div></div>'
        vend = [r for r in lista if r.get('venda')]
        outr = [r for r in lista if not r.get('venda')]
        tv, to = sum(r['valor'] for r in vend), sum(r['valor'] for r in outr)
        mostra_o = outr[:6]
        tot = tv + to
        cores_v = {r['cfop']: _PAL_S[min(i, 7)] for i, r in enumerate(vend)}
        cores_o = {r['cfop']: _PAL_O[min(i, 7)] for i, r in enumerate(outr)}
        stack = ''.join(f'<div style="width:{_pct(r["valor"], tot):.2f}%;background:{cores_v[r["cfop"]]}"></div>' for r in vend)
        stack += ''.join(f'<div style="width:{_pct(r["valor"], tot):.2f}%;background:{cores_o[r["cfop"]]}"></div>' for r in outr)
        def linhas(rs, cores):
            return ''.join(
                f'<tr><td><span class="sw" style="background:{cores[r["cfop"]]}"></span><span class="cfb">{_esc(r["cfop"])}</span>'
                f'{_esc(cfop_desc(r["cfop"], r.get("desc")))}{"<span class=tr>TRANSF.</span>" if _eh_transf(r["cfop"]) else ""}</td>'
                f'<td class="p">{r.get("nfs", 0)} NF</td><td class="v num">{_R(r["valor"])}</td><td class="p">{_brl(_pct(r["valor"], tot))}%</td></tr>'
                for r in rs)
        h = f'<div class="card"><h4>Saídas · {_R(tot)}</h4><div class="stack">{stack}</div>'
        h += f'<div class="subh"><span>Vendas</span><b class="num">{_R(tv)}</b></div>'
        h += f'<table>{linhas(vend, cores_v)}</table>' if vend else '<div class="vazio">Nenhuma venda no período.</div>'
        if outr:
            extra = f' · {len(outr) - len(mostra_o)} outro(s) CFOP somam {_R(sum(r["valor"] for r in outr[6:]))}' if len(outr) > 6 else ''
            h += (f'<div class="subh o"><span>Outras saídas (não são venda)</span><b class="num">{_R(to)}</b></div>'
                  f'<table>{linhas(mostra_o, cores_o)}</table>' + (f'<div class="note">{extra[3:]}</div>' if extra else ''))
        return h + '</div>'
    sec03 = (f'<div class="sec anim"><span>03</span><h2>Movimentação por CFOP</h2><em>entradas e saídas, com as vendas separadas</em></div>'
             f'<div class="two anim">{bloco_cfop(d.get("compras_cfop"), _PAL_E, "Entradas")}{bloco_saidas(d.get("vendas_cfop"))}</div>')

    # ---- 04 compras ----
    raiz = re.sub(r'\D', '', emp.get('cnpj') or '')[:8]
    forn = d.get('top_fornecedores') or []
    transf = [f for f in forn if raiz and re.sub(r'\D', '', f.get('cnpj') or '')[:8] == raiz]
    outros = [f for f in forn if f not in transf]
    mxf = max((f['valor'] for f in outros), default=0) or 1
    ft = ''.join(f'<tr class="trf"><td colspan="2">Transferência entre estabelecimentos · {_esc(f["nome"])}</td>'
                 f'<td class="v num">{_R(f["valor"])}</td></tr>' for f in transf)
    ft += ''.join(f'<tr><td style="width:50%;padding-right:6px">{_esc(f["nome"])}</td><td style="width:26%"><div class="inl"><div class="bar"><i style="width:{_pct(f["valor"], mxf):.1f}%;'
                  f'background:#3d55c4"></i></div></div></td><td class="v num">{_R(f["valor"])}</td></tr>' for f in outros)
    prods = d.get('top_produtos') or []
    mxp = max((p['valor'] for p in prods), default=0) or 1
    pt = ''.join(f'<tr><td style="width:50%;padding-right:6px"><b style="color:{_OR2 if i < 3 else "#9aa2bf"};margin-right:8px">{i + 1:02d}</b>{_esc(p["nome"])}</td>'
                 f'<td style="width:26%"><div class="inl"><div class="bar"><i style="width:{_pct(p["valor"], mxp):.1f}%;background:{_OR2}"></i></div></div></td>'
                 f'<td class="v num">{_R(p["valor"])}</td></tr>' for i, p in enumerate(prods))
    sec04 = (f'<div class="sec anim"><span>04</span><h2>Compras</h2><em>de quem e o quê</em></div><div class="two anim">'
             f'<div class="card"><h4>Top fornecedores</h4>{"<table>" + ft + "</table>" if ft else "<div class=vazio>Sem compras no período.</div>"}</div>'
             f'<div class="card"><h4>Top produtos em compras</h4>{"<table>" + pt + "</table>" if pt else "<div class=vazio>Sem itens de compra no período.</div>"}</div></div>')

    # ---- 05 ajustes ----
    ajs = list(d.get('ajustes_e111') or []) + list(d.get('ajustes_doc') or [])
    ajs.sort(key=lambda a: a.get('natureza') != 'debito')
    linhas = ''
    for a in ajs:
        db = a.get('natureza') == 'debito'
        cor = '#d93b41' if db else '#0a8a5f'
        desc = a.get('descricao') or a.get('tipo') or ''
        # sem nome de registro do SPED (E111, C197...): o cliente não precisa disso
        q = a.get('qtd', 0)
        orig = (f' <span style="color:#9aa2bf">· lançado em {q} {"notas fiscais" if q != 1 else "nota fiscal"}</span>'
                if a.get('origem') == 'documento' else '')
        linhas += (f'<tr><td><span class="aj3" style="background:{"#fde8e9" if db else "#e7f8f1"};color:{cor}">{"DÉBITO" if db else "CRÉDITO"}</span>'
                   f'<span class="cfb" style="color:{cor}">{_esc(a.get("codigo"))}</span>{_esc(desc)[:90]}{orig}</td>'
                   f'<td class="v num" style="color:{cor}">{"+ " if db else "− "}{_R(a.get("valor"))}</td></tr>')
    if linhas:
        sd = sum(a.get('valor') or 0 for a in ajs if a.get('natureza') == 'debito')
        sc = sum(a.get('valor') or 0 for a in ajs if a.get('natureza') != 'debito')
        liq = sc - sd
        linhas += (f'<tr><td style="font-weight:700;color:{_NAVY}">Saldo dos ajustes ({"reduz" if liq >= 0 else "aumenta"} o imposto)</td>'
                   f'<td class="v num" style="color:{"#0a8a5f" if liq >= 0 else "#d93b41"};font-size:15px">{"− " if liq >= 0 else "+ "}{_R(abs(liq))}</td></tr>')
        corpo = f'<table>{linhas}</table>'
    else:
        corpo = '<div class="vazio">Sem ajustes na apuração.</div>'
    sec05 = (f'<div class="sec anim"><span>05</span><h2>Ajustes da apuração</h2><em>vermelho soma ao imposto · verde abate</em></div>'
             f'<div class="card anim">{corpo}</div>')

    secs = [sec01, sec02, sec03, sec04, sec05]
    corpo_secs = ''.join(s.replace('class="sec anim"', f'class="sec anim" style="animation-delay:{.35 + i * .08:.2f}s"', 1)
                         for i, s in enumerate(secs))
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Apuração ICMS · {_esc(emp.get('empresa', ''))} · {_esc(comp)}</title><style>{_CSS}</style></head><body>
{band}{bento}<div class="wrap">{corpo_secs}
<div class="foot">Gerado pelo FiscoCont+ · Liddera | Inteligência em Negócios Ltda · www.lidderacont.com.br</div></div>{_JS}</body></html>"""

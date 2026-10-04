# -*- coding: utf-8 -*-
"""
Relatório para o CLIENTE — EFD-Contribuições (PIS/COFINS).

Explica, em linguagem simples, o que foi apurado no mês, e cada explicação vem com o seu gráfico.
Princípios:
 - o texto NÃO é gerado livremente: são frases revisadas, escolhidas conforme os dados e
   preenchidas com os números do arquivo (nada de "inventar" tributação);
 - casos tratados: a pagar, saldo credor (nada a pagar e sobra crédito), misto (um tributo a
   pagar e o outro com saldo credor) e sem movimento;
 - o relatório explica o que foi DECLARADO; por isso deve ser gerado depois da correção/validação;
 - duas saídas do mesmo conteúdo: HTML animado e HTML estático (usado para o PDF).
"""
import html as _html
import json
import re
from collections import defaultdict

from efd_contribuicoes import _NATUREZA_CREDITO

MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
_EPS = 0.005

# nomes em linguagem simples para as naturezas de crédito (tabela oficial conferida do módulo)
_CRED_SIMPLES = {
    '01': 'Compras de mercadorias para revenda', '02': 'Compras de materiais usados na atividade (insumos)',
    '03': 'Serviços contratados usados na atividade (insumos)', '04': 'Energia elétrica', '05': 'Aluguel de prédios',
    '06': 'Aluguel de máquinas e equipamentos', '07': 'Armazenagem e frete nas vendas', '08': 'Arrendamento mercantil (leasing)',
    '09': 'Compra de máquinas e equipamentos', '10': 'Depreciação de máquinas e equipamentos', '11': 'Devoluções de vendas',
    '12': 'Outras operações com direito a crédito', '13': 'Transporte de cargas (subcontratação)',
    '14': 'Atividade imobiliária', '15': 'Atividade imobiliária', '16': 'Serviços de limpeza e manutenção',
}
_CST_GRUPO = {
    '04': ('Imposto já pago na indústria (monofásico)', '#2f4090'), '05': ('Imposto cobrado antes (substituição tributária)', '#8b5cf6'),
    '06': ('Alíquota zero', '#e8632b'), '07': ('Isento por lei', '#0ea5a4'), '08': ('Sem incidência', '#6b7392'),
    '09': ('Suspenso', '#d4a017'), '49': ('Outras operações', '#8a90a8'), '99': ('Outras operações', '#8a90a8'),
}


# ------------------------------------------------------------------ utilidades
def _esc(s):
    return _html.escape('' if s is None else str(s))


def _brl(v):
    return f'{(v or 0):,.2f}'.replace(',', '§').replace('.', ',').replace('§', '.')


def _rs(v):
    return 'R$ ' + _brl(v)


def _int(v):
    return f'{round(v or 0):,}'.replace(',', '.')


def _pct(v, casas=1):
    return f'{v:.{casas}f}'.replace('.', ',') + '%'


def _rs_curto(v):
    v = abs(v or 0)
    if v >= 1e6:
        m = v / 1e6
        return 'R$ ' + f'{m:.2f}'.replace('.', ',') + (' milhão' if m < 2 else ' milhões')
    return _rs(v)


def _mix(hexc, alvo, f):
    h = hexc.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return '#%02x%02x%02x' % (int(r + (alvo[0] - r) * f), int(g + (alvo[1] - g) * f), int(b + (alvo[2] - b) * f))


def _grad(cor):
    return f'linear-gradient(90deg,{_mix(cor, (0, 0, 0), .32)} 0%,{cor} 30%,{_mix(cor, (255, 255, 255), .35)} 48%,{cor} 72%,{_mix(cor, (0, 0, 0), .32)} 100%)'


def _competencia(d):
    ini = (d.get('empresa') or {}).get('periodo_ini', '')
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})', ini)
    if not m:
        return '', '', 0, 0
    mes, ano = int(m.group(2)), int(m.group(3))
    return MESES[mes - 1], str(ano), mes, ano


def _nome_simples(desc):
    """Nome curto e legível de uma natureza da receita (a descrição oficial é longa e cheia de NCM)."""
    t = (desc or '').strip()
    if ' — ' in t:
        t = t.split(' — ', 1)[1]
    t = re.sub(r'^Receita decorrente d[ae]( venda| revenda)? d[eao]s? ', '', t, flags=re.I)
    for corte in (', classificad', ' classificad', ' – ', ' - ', ' (', ';', ', conforme', ' conforme', ', quando', ' quando '):
        i = t.lower().find(corte.lower())
        if i > 0:
            t = t[:i]
    t = t.strip(' .,')
    if sum(1 for w in t.split() if w[:1].isupper()) >= 2:      # "Etanol Não Combustível" -> "Etanol não combustível"
        t = t[:1] + t[1:].lower()
    return (t[:1].upper() + t[1:])[:72] or 'Outras receitas'


# ------------------------------------------------------------------ números do mês
def _tributo(t):
    c = t['consolidacao']
    debito = c['apurado_nao_cumulativo'] + c['apurado_cumulativo']
    cred = c['credito_descontado'] + c['credito_descontado_periodo_anterior']
    pagar = c['total_a_recolher']
    return {
        'debito': debito, 'cred': cred, 'pagar': pagar, 'anterior': c['credito_descontado_periodo_anterior'],
        'saldo': sum(x['saldo_a_transportar'] for x in t['creditos']), 'gerado': sum(x['valor_credito'] for x in t['creditos']),
        'outras': round(debito - cred - pagar, 2), 'darf': t['codigos_receita'],
    }


def calcular(d):
    pis, cof = _tributo(d['pis']), _tributo(d['cofins'])
    trib = sum(c['receita_bruta'] for c in d['pis']['por_cst'])
    nao = sum(x['valor'] for x in d['pis']['nao_tributada_cst'])
    receita = trib + nao or (d.get('receita_0111') or {}).get('total', 0.0)
    tot = {k: pis[k] + cof[k] for k in ('debito', 'cred', 'pagar', 'saldo', 'gerado', 'outras', 'anterior')}
    n = {'receita': receita, 'trib': trib, 'nao_trib': nao, 'pis': pis, 'cofins': cof, 'tot': tot}
    if tot['pagar'] > _EPS:
        misto = any(n[k]['pagar'] <= _EPS and n[k]['saldo'] > _EPS for k in ('pis', 'cofins'))
        n['caso'] = 'misto' if misto else 'normal'
    elif tot['saldo'] > _EPS:
        n['caso'] = 'credor'
    else:
        n['caso'] = 'nada'
    n['por100'] = {k: (100.0 * tot[k] / receita if receita else 0.0) for k in ('debito', 'cred', 'pagar', 'saldo')}
    return n


# ------------------------------------------------------------------ explicações (frases revisadas)
def _texto_resumo(d, n):
    mes, ano, _, _ = _competencia(d)
    t = n['tot']
    base = f'Em <b>{mes} de {ano}</b>, sua empresa teve <b>{_rs_curto(n["receita"])}</b> em receitas. '
    if n['caso'] == 'nada':
        return base + 'Neste mês <b>não houve PIS/COFINS a pagar</b> nem crédito para guardar.'
    txt = base + f'Sobre as receitas que a lei manda tributar, o PIS e a COFINS somaram <b>{_rs(t["debito"])}</b>. '
    if n['caso'] == 'credor':
        txt += (f'Como você também comprou mercadorias e serviços que dão direito a desconto, você tem <b>{_rs(t["cred"] + t["saldo"])} em créditos</b> neste mês, '
                f'valor maior que o imposto das vendas. Por isso <b style="color:#0f6e56">não há PIS/COFINS a pagar</b> — '
                f'e ainda sobraram <b style="color:#0f6e56">{_rs(t["saldo"])} de crédito</b> para usar nos próximos meses.')
        return txt
    if t['cred'] > _EPS:
        txt += (f'Como você também comprou mercadorias e serviços que dão direito a desconto, parte desse imposto volta como '
                f'<b>créditos: {_rs(t["cred"])}</b>. ')
    else:
        txt += 'Neste mês não houve créditos para descontar. '
    if t['outras'] > _EPS:
        txt += f'Também foram descontados <b>{_rs(t["outras"])}</b> de retenções e outros ajustes. '
    if n['caso'] == 'normal':
        txt += (f'O resultado foi <b style="color:#c2500f">{_rs(t["pagar"])} a pagar</b>, ou seja, '
                f'<b>R$ {_brl(n["por100"]["pagar"])} para cada R$ 100 vendidos</b>.')
    else:   # misto
        ps = [(nome, n[k]) for nome, k in (('PIS', 'pis'), ('COFINS', 'cofins'))]
        a_pagar = [f'{nome}: {_rs(x["pagar"])}' for nome, x in ps if x['pagar'] > _EPS]
        credor = [f'{"No" if nome == "PIS" else "Na"} {nome} não há nada a pagar e ainda sobraram <b>{_rs(x["saldo"])}</b> de crédito para os próximos meses'
                  for nome, x in ps if x['pagar'] <= _EPS and x['saldo'] > _EPS]
        txt += (f'O resultado foi <b style="color:#c2500f">{_rs(t["pagar"])} a pagar</b> ({"; ".join(a_pagar)}). {". ".join(credor)}.')
    return txt


def _texto_cascata(n):
    if n['caso'] == 'credor':
        return ('Primeiro calculamos o imposto das vendas. Depois descontamos os créditos a que você tem direito pelas compras. '
                'Como os créditos foram maiores, <b>não sobrou nada para pagar</b> e a diferença fica guardada como saldo credor.')
    return ('Primeiro calculamos o imposto das vendas. Depois descontamos os créditos a que você tem direito pelas compras. '
            'O que sobra é o que vai para a guia.')


def _texto_cem(n):
    p = n['por100']
    if n['caso'] == 'credor':
        return (f'O imposto das vendas seria <b>R$ {_brl(p["debito"])}</b> para cada R$ 100,00 vendidos. Seus créditos cobriram tudo e ainda sobraram '
                f'<b>R$ {_brl(p["saldo"])}</b>.')
    return (f'O imposto das vendas seria <b>R$ {_brl(p["debito"])}</b>. Seus créditos devolvem <b>R$ {_brl(p["cred"])}</b>, '
            f'e sobram <b>R$ {_brl(p["pagar"])}</b> para pagar.')


# ------------------------------------------------------------------ peças visuais
def _cascata(n):
    t = n['tot']
    H = 170.0
    caso = n['caso']
    topo = max(t['debito'], (t['cred'] + t['saldo']) if caso == 'credor' else 0, 1.0)

    def px(v):
        return H * max(v, 0) / topo

    def coluna(titulo, sub, barras):
        return ('<div class="col"><div class="pilha">' + ''.join(barras) + f'</div><div class="rot"><b>{titulo}</b><br>{sub}</div></div>')

    def barra(cls, bottom, altura, chip, extra=''):
        return (f'<div class="barra {cls}" style="bottom:{bottom:.1f}px;height:{max(altura, 3):.1f}px;{extra}">'
                f'<span class="chip">{chip}</span></div>')
    seta = '<div class="conx"><svg width="52" height="26" viewBox="0 0 52 26"><path d="M3 13h38M32 4l11 9-11 9" stroke="#8a90a8" stroke-width="3.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg><span>menos</span></div>'

    def igual(cor):
        return f'<div class="conx"><span class="eq" style="color:{cor};border-color:{cor}">=</span></div>'
    cols = [coluna('Imposto das vendas', 'PIS + COFINS', [barra('azul', 0, px(t['debito']), _rs(t['debito']))])]
    if caso == 'credor':
        usado, saldo = t['cred'], t['saldo']
        cols.append(seta)
        cols.append(coluna('Créditos disponíveis', 'das suas compras', [
            barra('verde', 0, px(usado), '', ''),
            barra('verde-claro', px(usado), px(saldo), _rs(usado + saldo), 'border-radius:10px 10px 4px 4px'),
        ]))
        cols.append(igual('#0f9d6e'))
        cols.append(coluna('Saldo credor', 'fica para os próximos meses', [barra('verde', 0, px(saldo), _rs(saldo))]))
        return '<div class="casc">' + ''.join(cols) + '</div>'
    nivel = t['debito']
    if t['cred'] > _EPS:
        novo = nivel - t['cred']
        cols.append(seta)
        cols.append(coluna('Créditos das compras', 'descontados', [barra('verde', px(novo), px(nivel) - px(novo), '− ' + _rs(t['cred']))]))
        nivel = novo
    if abs(t['outras']) > _EPS:
        cols.append(seta)
        if t['outras'] > 0:
            novo = nivel - t['outras']
            cols.append(coluna('Retenções e ajustes', 'descontados', [barra('cinza', px(novo), px(nivel) - px(novo), '− ' + _rs(t['outras']))]))
            nivel = novo
        else:
            novo = nivel - t['outras']
            cols.append(coluna('Outros ajustes', 'somados', [barra('cinza', px(nivel), px(novo) - px(nivel), '+ ' + _rs(-t['outras']))]))
            nivel = novo
    cols.append(igual('#e8632b'))
    cols.append(coluna('Você paga', 'nas guias', [barra('laranja', 0, px(t['pagar']), _rs(t['pagar']))]))
    return '<div class="casc">' + ''.join(cols) + '</div>'


def _donut_e_ranking(d, n):
    if n['nao_trib'] <= _EPS or n['receita'] <= _EPS:
        return ''
    pct_nao = 100.0 * n['nao_trib'] / n['receita']
    C = 2 * 3.14159265 * 62
    arco = C * pct_nao / 100
    grupos = defaultdict(float)
    cst_do_nome = {}
    for x in d['pis']['nao_tributada_natureza']:
        nome = _nome_simples(x['natureza_desc'])
        if 'não catalogado' in x['natureza_desc'] or 'sem tabela' in x['natureza_desc']:
            nome = f'Outras receitas sem PIS/COFINS (código {x["natureza"]})'
        grupos[(x['cst'], nome)] += x['valor']
        cst_do_nome[(x['cst'], nome)] = x['cst']
    if not grupos:
        for x in d['pis']['nao_tributada_cst']:
            grupos[(x['cst'], _CST_GRUPO.get(x['cst'], ('Outras receitas', ''))[0])] += x['valor']
    ordenado = sorted(grupos.items(), key=lambda kv: -kv[1])
    top, resto = ordenado[:6], ordenado[6:]
    linhas = list(top)
    if resto:
        linhas.append((('--', 'Outros'), sum(v for _, v in resto)))
    mx = max(v for _, v in linhas) or 1
    csts_usados = []
    barras = ''
    for (cst, nome), v in linhas:
        cor = _CST_GRUPO.get(cst, ('', '#8a90a8'))[1]
        if cst != '--' and cst not in csts_usados:
            csts_usados.append(cst)
        barras += (f'<div class="hlinha"><span>{_esc(nome)}</span><span class="htrilho"><span class="hfill" style="width:{100 * v / mx:.1f}%;background:linear-gradient(90deg,{cor},{_mix(cor, (255, 255, 255), .35)})"></span></span>'
                   f'<b>{_int(v)}</b></div>')
    leg = ' &nbsp; '.join(f'<span class="ponto" style="background:{_CST_GRUPO[c][1]}"></span>{_CST_GRUPO[c][0].lower()}' for c in csts_usados if c in _CST_GRUPO)
    top3 = [nome for (_, nome), _v in linhas[:3] if nome != 'Outros']
    lista = ', '.join(x.lower() if i else x.lower() for i, x in enumerate(top3[:-1])) + (' e ' if len(top3) > 1 else '') + (top3[-1].lower() if top3 else '')
    mes = _competencia(d)[0]
    donut = (f'<div class="card"><h3>Suas receitas</h3><div class="donutbox"><svg width="170" height="170" viewBox="0 0 160 160">'
             f'<circle cx="80" cy="80" r="62" fill="none" stroke="#2f4090" stroke-width="24"/>'
             f'<circle class="arco" cx="80" cy="80" r="62" fill="none" stroke="#e8632b" stroke-width="24" stroke-dasharray="{arco:.2f} {C:.2f}" transform="rotate(-90 80 80)"/>'
             f'<text x="80" y="78" text-anchor="middle" font-size="26" font-weight="800" fill="#232a3d">{round(pct_nao)}%</text>'
             f'<text x="80" y="95" text-anchor="middle" font-size="9.5" fill="#7a8199">sem PIS/COFINS</text></svg></div>'
             f'<div class="legenda"><span class="ponto" style="background:#2f4090"></span>Tributadas: <b>{_rs_curto(n["trib"])}</b> ({round(100 - pct_nao)}%)<br>'
             f'<span class="ponto" style="background:#e8632b"></span>Sem PIS/COFINS na venda: <b>{_rs_curto(n["nao_trib"])}</b> ({round(pct_nao)}%)</div></div>')
    rank = (f'<div class="card"><h3>Por que {round(pct_nao)}% das receitas não pagaram PIS/COFINS?</h3>'
            f'<p class="sub">Alguns produtos têm tratamento especial na lei: ou o imposto já foi pago antes (na indústria ou por substituição tributária), ou a alíquota é zero, ou há isenção. '
            f'Em {mes}, isso aconteceu principalmente com {_esc(lista)}.</p><div class="hlista">{barras}</div>'
            f'<div class="nota-pq">{leg} · valores em R$</div></div>')
    return f'<div class="duo">{donut}{rank}</div>'


def _creditos_origem(d, n):
    t = n['tot']
    if t['cred'] + t['saldo'] <= _EPS:
        return ''
    # crédito de cada natureza = base do crédito × alíquota do M100; escalado para fechar com o que o cliente vê na cascata
    por_nat = defaultdict(float)
    for chave in ('pis', 'cofins'):
        alvo = n[chave]['cred'] - n[chave]['anterior'] + n[chave]['saldo']
        brutos = {}
        for x in d[chave]['detalhe_credito']:
            aliq = float((x.get('aliquota') or '0').replace(',', '.') or 0)
            v = x['base_credito'] * aliq / 100.0
            if v > 0:
                brutos[x['natureza']] = brutos.get(x['natureza'], 0) + v
        soma = sum(brutos.values())
        if soma > _EPS and alvo > _EPS:
            for k, v in brutos.items():
                por_nat[k] += v * alvo / soma
    linhas = [(_CRED_SIMPLES.get(k) or _NATUREZA_CREDITO.get(k.zfill(2), f'Natureza {k}'), v) for k, v in por_nat.items()]
    if t['anterior'] > _EPS:
        linhas.append(('Saldo de créditos de meses anteriores', t['anterior']))
    linhas = sorted([x for x in linhas if x[1] > _EPS], key=lambda kv: -kv[1])
    if not linhas:
        return ''
    total = sum(v for _, v in linhas)
    mx = linhas[0][1]
    barras = ''.join(
        f'<div class="hlinha"><span>{_esc(nome)}</span><span class="htrilho"><span class="hfill" style="width:{100 * v / mx:.1f}%;background:linear-gradient(90deg,#0f9d6e,#5ed1a8)"></span></span><b>{_int(v)}</b></div>'
        for nome, v in linhas)
    principal = linhas[0]
    exp = {'Compras de mercadorias para revenda': 'Toda mercadoria que você compra para revender gera crédito de PIS/COFINS.',
           'Energia elétrica': 'A energia elétrica usada na empresa também gera crédito.',
           'Outras operações com direito a crédito': 'São operações previstas na lei que também dão direito a crédito.'}.get(principal[0], '')
    return (f'<div class="card"><h3>De onde vêm os seus créditos</h3>'
            f'<p class="sub">Crédito é o desconto a que você tem direito sobre o PIS/COFINS pago embutido nas suas compras. Dos <b>{_rs(total)}</b> de créditos deste mês, '
            f'<b>{_pct(100 * principal[1] / total, 0)}</b> vêm de <b>{_esc(principal[0].lower())}</b>. {exp}</p>'
            f'<div class="hlista">{barras}</div><div class="nota-pq">valores em R$</div></div>')


def _por_100(n):
    p = n['por100']
    if n['receita'] <= _EPS or p['debito'] <= _EPS:
        return ''
    if n['caso'] == 'credor':
        a, b = p['debito'], p['saldo']
        seg = (f'<div class="seg" style="width:100%;background:linear-gradient(180deg,#3fc596,#0f9d6e)">Créditos cobriram 100% do imposto</div>')
        chips = f'<span class="pilula verde">Sobraram R$ {_brl(b)} de crédito para cada R$ 100 vendidos</span>'
    else:
        total = p['debito']
        wc = 100.0 * p['cred'] / total
        seg = (f'<div class="seg" style="width:{wc:.1f}%;background:linear-gradient(180deg,#3fc596,#0f9d6e)">R$ {_brl(p["cred"])} voltam como crédito</div>'
               f'<div class="seg" style="width:{100 - wc:.1f}%;background:linear-gradient(180deg,#ff9f66,#e8632b)">R$ {_brl(p["pagar"])} você paga</div>')
        chips = ''
    pis, cof = n['pis'], n['cofins']
    if n['tot']['pagar'] > _EPS:
        for nome, x in (('COFINS', cof), ('PIS', pis)):
            if x['pagar'] > _EPS:
                chips += f'<span class="pilula azul">{nome}: {_rs(x["pagar"])} ({round(100 * x["pagar"] / n["tot"]["pagar"])}% do valor a pagar)</span>'
        if n['tot']['debito'] > _EPS and n['tot']['cred'] > _EPS:
            chips += f'<span class="pilula verde">{round(100 * n["tot"]["cred"] / n["tot"]["debito"])}% do imposto foi compensado por créditos</span>'
    return (f'<div class="card"><h3>Para cada R$ 100,00 que você vendeu</h3><p class="sub">{_texto_cem(n)}</p>'
            f'<div class="empilhada">{seg}</div><div class="pilulas">{chips}</div></div>')


def _por_tributo(n):
    def linha(rot, a, b, cor=''):
        return f'<tr><td>{rot}</td><td style="text-align:right;{cor}">{_rs(a)}</td><td style="text-align:right;{cor}">{_rs(b)}</td></tr>'
    pis, cof = n['pis'], n['cofins']
    corpo = (linha('Imposto sobre as vendas', pis['debito'], cof['debito']) + linha('Créditos descontados', pis['cred'], cof['cred'], 'color:#0f6e56')
             + linha('Valor a pagar', pis['pagar'], cof['pagar'], 'color:#c2500f;font-weight:800'))
    if n['tot']['saldo'] > _EPS:
        corpo += linha('Saldo credor (fica para os próximos meses)', pis['saldo'], cof['saldo'], 'color:#0f6e56;font-weight:800')
    return f'<div class="card"><h3>PIS e COFINS separados</h3><table class="tb"><thead><tr><th></th><th>PIS</th><th>COFINS</th></tr></thead><tbody>{corpo}</tbody></table></div>'


def _guias(n, op):
    if n['tot']['pagar'] <= _EPS:
        return ''
    linhas = ''
    for nome, x in (('COFINS', n['cofins']), ('PIS', n['pis'])):
        if x['pagar'] > _EPS:
            cods = ', '.join(c['codigo_darf'] for c in x['darf']) or '—'
            linhas += f'<div class="guia"><span><b>{nome}</b> · código {_esc(cods)}</span><b>{_rs(x["pagar"])}</b></div>'
    linhas += f'<div class="guia total"><span>Total</span><span>{_rs(n["tot"]["pagar"])}</span></div>'
    venc = f'<div class="nota-pq" style="margin-top:8px">Vencimento: <b>{_esc(op.get("vencimento"))}</b></div>' if op.get('vencimento') else ''
    return f'<div class="card"><h3>Para pagar</h3><div class="guias">{linhas}</div>{venc}</div>'


def _bloco_credor(n):
    if n['caso'] not in ('credor', 'misto'):
        return ''
    t = n['tot']
    partes = [(nome, n[k]['saldo']) for nome, k in (('PIS', 'pis'), ('COFINS', 'cofins')) if n[k]['saldo'] > _EPS]
    detalhe = ' e '.join(f'{nome}: <b>{_rs(v)}</b>' for nome, v in partes)
    titulo = 'Nada a pagar neste mês' if n['caso'] == 'credor' else 'Há saldo credor em um dos tributos'
    return (f'<div class="caixa-credor"><div class="credor-ico">✓</div><div><div class="credor-t">{titulo}</div>'
            f'<div class="credor-x">Seus créditos foram maiores que o imposto, e <b>sobrou {_rs(t["saldo"])} de crédito</b> ({detalhe}). '
            f'Esse é o <b>saldo credor</b>: um crédito a que a empresa tem direito e que ainda não foi usado, porque não havia imposto suficiente para descontar. '
            f'Ele fica guardado para reduzir o imposto dos próximos meses, e o escritório acompanha esse saldo. '
            f'<span class="peq">Valor conforme a EFD-Contribuições entregue.</span></div></div></div>')


def _comparativo(d, n, da, na, avisos):
    cnpj_a, cnpj_b = (d.get('empresa') or {}).get('cnpj'), (da.get('empresa') or {}).get('cnpj')
    if cnpj_a != cnpj_b:
        avisos.append('O SPED do mês anterior é de outro CNPJ; o comparativo não foi incluído.')
        return ''
    _, _, m1, a1 = _competencia(da)
    _, _, m2, a2 = _competencia(d)
    if (a1, m1) >= (a2, m2):
        avisos.append('O SPED escolhido como mês anterior não é de um período anterior ao atual; o comparativo não foi incluído.')
        return ''
    mes_ant = _competencia(da)[0]
    mes = _competencia(d)[0]
    itens = [('Receitas', n['receita'], na['receita'], '#2f4090', True), ('Imposto sobre as vendas', n['tot']['debito'], na['tot']['debito'], '#4f62b5', False),
             ('Créditos usados', n['tot']['cred'], na['tot']['cred'], '#0f9d6e', True), ('Valor a pagar', n['tot']['pagar'], na['tot']['pagar'], '#e8632b', False)]
    grupos = ''
    for nome, v, va, cor, alta_boa in itens:
        mx = max(v, va, 1)
        h1, h2 = (max(4, round(120 * va / mx)) if va > 0 else 0), (max(4, round(120 * v / mx)) if v > 0 else 0)
        if va > _EPS:
            var = 100 * (v - va) / va
            seta = '▲' if var > 0 else ('▼' if var < 0 else '=')
            favoravel = (var >= 0) == alta_boa
            chip = f'<span class="var {"bom" if favoravel else "atencao"}">{seta} {_pct(abs(var))}</span>' if abs(var) >= 0.05 else '<span class="var">igual</span>'
        else:
            chip = '<span class="var">—</span>'
        grupos += (f'<div class="cgrp"><div class="cpar"><div class="cbar"><span class="cv">{_int(va)}</span><div class="barra2" style="height:{h1}px;background:{_grad("#9aa6d4")}"></div></div>'
                   f'<div class="cbar"><span class="cv" style="color:{cor}">{_int(v)}</span><div class="barra2" style="height:{h2}px;background:{_grad(cor)}"></div></div></div>'
                   f'<div class="crot"><b>{nome}</b>{chip}</div></div>')
    frases = []
    if na['receita'] > _EPS:
        var = 100 * (n['receita'] - na['receita']) / na['receita']
        if abs(var) < 0.05:
            frases.append(f'Suas receitas ficaram praticamente iguais às de {mes_ant} ({_rs_curto(n["receita"])}).')
        else:
            frases.append(f'Suas receitas {"cresceram" if var >= 0 else "caíram"} <b>{_pct(abs(var))}</b> em relação a {mes_ant} (de {_rs_curto(na["receita"])} para {_rs_curto(n["receita"])}).')
    if na['tot']['pagar'] > _EPS and n['tot']['pagar'] > _EPS:
        var = 100 * (n['tot']['pagar'] - na['tot']['pagar']) / na['tot']['pagar']
        if abs(var) < 0.05:
            frases.append(f'O valor a pagar ficou igual ao de {mes_ant} ({_rs(n["tot"]["pagar"])}).')
        else:
            frases.append(f'O valor a pagar {"subiu" if var >= 0 else "caiu"} <b>{_pct(abs(var))}</b> (de {_rs(na["tot"]["pagar"])} para {_rs(n["tot"]["pagar"])}).')
    elif na['tot']['pagar'] > _EPS and n['tot']['pagar'] <= _EPS:
        frases.append(f'Em {mes_ant} havia {_rs(na["tot"]["pagar"])} a pagar; em {mes}, não há nada a pagar.')
    elif n['tot']['pagar'] > _EPS and na['tot']['pagar'] <= _EPS:
        frases.append(f'Em {mes_ant} não havia valor a pagar; em {mes}, há {_rs(n["tot"]["pagar"])}.')
    if na['receita'] > _EPS and n['receita'] > _EPS:
        frases.append(f'O PIS/COFINS pago equivale a <b>{_pct(n["por100"]["pagar"], 2)}</b> das receitas (em {mes_ant}: {_pct(na["por100"]["pagar"], 2)}).')
    return (f'<div class="card"><h3>Comparando com {mes_ant}</h3><p class="sub">{" ".join(frases)}</p>'
            f'<div class="cgrupos">{grupos}</div><div class="nota-pq"><span class="ponto" style="background:#9aa6d4"></span>{mes_ant} &nbsp; <span class="ponto" style="background:#e8632b"></span>{mes} · valores em R$ · cada grupo usa a sua própria escala</div></div>')


def _glossario(d, n):
    termos = [('Crédito', 'Desconto sobre o PIS/COFINS pago nas suas compras. Ele reduz o imposto que sobra para pagar.')]
    csts = {x['cst'] for x in d['pis']['nao_tributada_cst']}
    if '04' in csts:
        termos.append(('Imposto já pago na indústria (monofásico)', 'Em alguns produtos, o PIS/COFINS é cobrado só do fabricante ou importador. Quem revende não paga de novo.'))
    if '06' in csts:
        termos.append(('Alíquota zero', 'A lei fixou a alíquota em zero para o produto: há venda, mas o imposto é R$ 0,00.'))
    if '05' in csts:
        termos.append(('Substituição tributária', 'O imposto é cobrado antes, de um participante da cadeia, no lugar de quem vende ao consumidor.'))
    if n['tot']['saldo'] > _EPS:
        termos.append(('Saldo credor', 'Crédito que sobrou porque não havia imposto suficiente para descontar. Fica guardado para os meses seguintes.'))
    if n['tot']['pagar'] > _EPS:
        termos.append(('Guia (DARF)', 'Documento usado para pagar o PIS e a COFINS. Cada tributo tem o seu código.'))
    return ('<div class="card"><h3>O que significam estas palavras</h3><div class="gloss">' +
            ''.join(f'<div><b>{_esc(a)}</b><br><span>{_esc(b)}</span></div>' for a, b in termos) + '</div></div>')


def _anexo_tecnico(d, n):
    def linhas_nat():
        return ''.join(f'<tr><td>{_esc(x["cst"])}</td><td>{_esc(x["natureza_desc"])}</td><td style="text-align:right">{_rs(x["valor"])}</td></tr>' for x in d['pis']['nao_tributada_natureza'])

    def linhas_cred():
        out = ''
        for nome, k in (('PIS', 'pis'), ('COFINS', 'cofins')):
            for x in d[k]['detalhe_credito']:
                out += f'<tr><td>{nome}</td><td>{_esc(x["natureza_desc"])}</td><td>{_esc(x["cst"])}</td><td style="text-align:right">{_rs(x["base_credito"])}</td></tr>'
        return out
    return ('<div class="card"><h3>Anexo técnico</h3><p class="sub">Códigos e descrições oficiais da EFD-Contribuições, para conferência do seu contador.</p>'
            '<table class="tb"><thead><tr><th>CST</th><th>Natureza da receita sem PIS/COFINS</th><th>Valor</th></tr></thead><tbody>' + linhas_nat() + '</tbody></table>'
            '<div style="height:12px"></div><table class="tb"><thead><tr><th>Tributo</th><th>Natureza do crédito</th><th>CST</th><th>Base do crédito</th></tr></thead><tbody>' + linhas_cred() + '</tbody></table></div>')


# ------------------------------------------------------------------ estilo e animação
_CSS = """
:root{--ink:#232a3d;--ink2:#5a6280;--ink3:#8a90a8}
*{box-sizing:border-box}
body{margin:0;font-family:'Segoe UI',Arial,sans-serif;background:#f3f5fb;color:var(--ink);-webkit-print-color-adjust:exact;print-color-adjust:exact}
.wrap{max-width:800px;margin:0 auto;padding:18px 16px 40px;display:flex;flex-direction:column;gap:16px}
.hero{border-radius:16px;padding:18px 22px;color:#fff;box-shadow:0 10px 22px rgba(31,42,90,.28)}
.hero .topo{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap}
.hero .marca{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#d5daf3;font-weight:600;display:flex;align-items:center;gap:8px}
.hero .marca img{height:26px}
.hero .comp{font-size:11px;background:rgba(255,255,255,.16);border-radius:999px;padding:3px 12px}
.hero h1{font-size:21px;font-weight:800;margin:10px 0 0}
.hero .emp{font-size:12px;color:#d5daf3;margin-top:3px}
.resumo{background:linear-gradient(180deg,#fff,#f3faf7);border:1px solid #d6eee4;border-left:6px solid #0f9d6e;border-radius:14px;padding:16px 20px;box-shadow:0 8px 18px rgba(15,157,110,.10)}
.resumo .t{font-size:12px;font-weight:700;color:#0f6e56;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}
.resumo .x{font-size:14px;line-height:1.7}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.kpi{position:relative;overflow:hidden;background:linear-gradient(180deg,#fff,#f1f4fb);border-radius:14px;padding:18px 10px 13px;text-align:center;box-shadow:0 8px 18px rgba(31,42,90,.13)}
.kpi::before{content:'';position:absolute;left:0;right:0;top:0;height:4px;background:var(--acc,#1f2a5a)}
.kpi b{display:block;font-size:16px;font-weight:800}
.kpi span{font-size:10.5px;color:#7a8199;display:block;margin-top:3px}
.kpi.azul{--acc:#4f62b5;background:linear-gradient(180deg,#fff,#eef3fb)}.kpi.azul b{color:#2f4090}
.kpi.verde{--acc:#0f9d6e;background:linear-gradient(180deg,#fff,#eef8f4)}.kpi.verde b{color:#0f6e56}
.kpi.laranja{--acc:#f5c04a;background:linear-gradient(135deg,#e8632b,#f08a4b);transform:translateY(-4px);box-shadow:0 16px 26px rgba(232,99,43,.38)}
.kpi.laranja b{color:#fff;font-size:17px}.kpi.laranja span{color:#ffe9dc}
.kpi.credor{--acc:#f5c04a;background:linear-gradient(135deg,#0f9d6e,#3fc596);transform:translateY(-4px);box-shadow:0 16px 26px rgba(15,157,110,.38)}
.kpi.credor b{color:#fff;font-size:17px}.kpi.credor span{color:#e2f7ee}
.card{background:#fff;border:1px solid #eef0f6;border-radius:16px;padding:18px 22px;box-shadow:0 12px 26px rgba(31,42,90,.10),0 2px 6px rgba(31,42,90,.06)}
.card h3{margin:0;font-size:14px;font-weight:700}
.sub{font-size:12.5px;color:var(--ink2);line-height:1.6;margin:4px 0 10px}
.duo{display:grid;grid-template-columns:1fr 1.25fr;gap:16px}
.casc{display:flex;justify-content:center;align-items:flex-start;gap:6px;margin-top:6px;flex-wrap:nowrap}
.col{text-align:center}
.pilha{position:relative;width:118px;height:215px}
.barra{position:absolute;left:10px;right:10px;border-radius:10px 10px 4px 4px;transition:height 1.1s cubic-bezier(.2,.8,.2,1)}
.barra.azul{background:linear-gradient(90deg,#26336f,#4457a8 30%,#6a7dc6 48%,#3a4c96 72%,#26336f);box-shadow:0 12px 18px rgba(31,42,90,.35),inset 0 3px 0 rgba(255,255,255,.3)}
.barra.verde{background:linear-gradient(90deg,#0b6b4f,#0f9d6e 30%,#3fc596 48%,#0f9d6e 72%,#0b6b4f);box-shadow:0 12px 18px rgba(15,157,110,.35),inset 0 3px 0 rgba(255,255,255,.3)}
.barra.verde-claro{background:repeating-linear-gradient(135deg,#bfeedd 0 7px,#9fe3cb 7px 14px);border:2px dashed #0f9d6e;box-shadow:0 8px 14px rgba(15,157,110,.2)}
.barra.laranja{background:linear-gradient(90deg,#a93a0a,#e8632b 30%,#ff9f66 48%,#e8632b 72%,#a93a0a);box-shadow:0 12px 18px rgba(232,99,43,.4),inset 0 3px 0 rgba(255,255,255,.35)}
.barra.cinza{background:linear-gradient(90deg,#555d7d,#8a90a8 30%,#b4b9cc 48%,#8a90a8 72%,#555d7d);box-shadow:0 10px 16px rgba(85,93,125,.35),inset 0 3px 0 rgba(255,255,255,.3)}
.chip{position:absolute;left:50%;transform:translateX(-50%);top:-31px;background:#fff;border-radius:999px;padding:3px 11px;font-weight:800;font-size:12.5px;box-shadow:0 4px 10px rgba(31,42,90,.2);white-space:nowrap;color:var(--ink)}
.barra.azul .chip{color:#2f4090}.barra.verde .chip,.barra.verde-claro .chip{color:#0f6e56}.barra.laranja .chip{color:#c2500f}
.rot{font-size:12px;color:var(--ink2);line-height:1.4;margin-top:2px}
.conx{display:flex;flex-direction:column;align-items:center;width:62px;padding-top:112px;font-size:10px;color:var(--ink3)}
.eq{display:flex;align-items:center;justify-content:center;width:40px;height:40px;border:3px solid;border-radius:50%;font-size:26px;font-weight:800;line-height:1;background:#fff;box-shadow:0 6px 12px rgba(31,42,90,.15)}
.donutbox{display:flex;justify-content:center;margin:8px 0;filter:drop-shadow(0 10px 8px rgba(31,42,90,.25))}
.arco{transition:stroke-dasharray 1.2s cubic-bezier(.2,.8,.2,1)}
.legenda{font-size:12px;line-height:1.9}
.ponto{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:7px;vertical-align:-1px}
.hlista{display:flex;flex-direction:column;gap:7px;font-size:11.5px}
.hlinha{display:grid;grid-template-columns:150px 1fr 78px;gap:8px;align-items:center}
.htrilho{height:12px;border-radius:6px;background:#eef0f6;overflow:hidden;display:block}
.hfill{display:block;height:100%;box-shadow:inset 0 2px 0 rgba(255,255,255,.35);transition:width 1.1s cubic-bezier(.2,.8,.2,1)}
.hlinha b{text-align:right}
.nota-pq{font-size:10.5px;color:#7a8199;margin-top:9px}
.empilhada{display:flex;height:34px;border-radius:12px;overflow:hidden;box-shadow:0 8px 14px rgba(31,42,90,.18),inset 0 2px 0 rgba(255,255,255,.3)}
.seg{display:flex;align-items:center;justify-content:center;color:#fff;font-size:12px;font-weight:800;white-space:nowrap;overflow:hidden;transition:width 1.2s cubic-bezier(.2,.8,.2,1)}
.pilulas{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px;font-size:12px}
.pilula{border-radius:999px;padding:4px 12px;font-weight:700}.pilula.azul{background:#eef3fb;color:#2f4090}.pilula.verde{background:#e1f5ee;color:#085041}
.tb{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:8px}
.tb th{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:#7a8199;padding:6px 8px;border-bottom:2px solid #eef0f6}
.tb th:not(:first-child){text-align:right}
.tb td{padding:8px;border-bottom:1px solid #eef0f6}
.guias{display:flex;flex-direction:column;gap:8px;font-size:12.5px;margin-top:10px}
.guia{display:flex;justify-content:space-between;background:#f7f8fc;border-radius:10px;padding:9px 12px}
.guia.total{background:linear-gradient(90deg,#ffe3cf,#fff1e6);border-left:5px solid #e8632b;font-weight:800;color:#8f3a0d}
.caixa-credor{display:flex;gap:14px;align-items:flex-start;background:linear-gradient(180deg,#f2fbf7,#e4f7ee);border:2px solid #0f9d6e;border-radius:16px;padding:16px 20px;box-shadow:0 10px 20px rgba(15,157,110,.15)}
.credor-ico{flex:0 0 42px;height:42px;border-radius:50%;background:linear-gradient(135deg,#0f9d6e,#3fc596);color:#fff;font-size:24px;font-weight:800;display:flex;align-items:center;justify-content:center;box-shadow:0 6px 12px rgba(15,157,110,.35)}
.credor-t{font-size:15px;font-weight:800;color:#0b6b4f}
.credor-x{font-size:12.5px;line-height:1.65;color:#1d4a3b;margin-top:3px}.peq{color:#6b8f81;font-size:11px}
.recado{background:linear-gradient(180deg,#fffaf0,#fff4dc);border:1px solid #efc98f;border-left:6px solid #f5a524;border-radius:16px;padding:16px 20px;box-shadow:0 8px 18px rgba(245,165,36,.15)}
.recado .t{font-size:12px;font-weight:700;color:#8a5a06;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}
.recado .x{font-size:12.5px;line-height:1.65;color:#5a4410}
.gloss{display:grid;grid-template-columns:1fr 1fr;gap:10px 18px;font-size:12px;margin-top:8px}.gloss span{color:var(--ink2)}
.cgrupos{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;align-items:end}
.cpar{display:flex;align-items:flex-end;justify-content:center;gap:6px;height:160px}
.cbar{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%}
.cv{font-size:10.5px;font-weight:800;color:#6b7392;margin-bottom:3px}
.barra2{width:30px;border-radius:7px 7px 3px 3px;box-shadow:0 8px 12px rgba(31,42,90,.22),inset 0 3px 0 rgba(255,255,255,.3);transition:height 1.1s cubic-bezier(.2,.8,.2,1)}
.crot{text-align:center;font-size:11.5px;margin-top:6px;line-height:1.5}.crot b{display:block}
.var{display:inline-block;font-size:11px;font-weight:700;border-radius:999px;padding:1px 9px;background:#eef0f6;color:#5a6280}.var.bom{background:#e1f5ee;color:#085041}.var.atencao{background:#faeeda;color:#854f0b}
.rodape{font-size:10.5px;color:var(--ink3);text-align:center;line-height:1.6;padding:0 16px}
.pre .barra,.pre .barra2{height:0!important}.pre .hfill,.pre .seg{width:0!important}.pre .arco{stroke-dasharray:0 400}
@media print{body{background:#fff}.wrap{max-width:none;padding:0}.card,.resumo,.caixa-credor,.recado,.kpi{box-shadow:none!important;break-inside:avoid;page-break-inside:avoid}.kpis{break-inside:avoid}}
@page{size:A4;margin:10mm}
@media (max-width:640px){.kpis{grid-template-columns:repeat(2,1fr)}.duo{grid-template-columns:1fr}.hlinha{grid-template-columns:110px 1fr 64px}.cgrupos{grid-template-columns:repeat(2,1fr)}.gloss{grid-template-columns:1fr}.casc{overflow-x:auto}}
"""

_JS = """
(function(){
  function fmt(v,t){ if(t==='int') return Math.round(v).toLocaleString('pt-BR');
    return 'R$ '+v.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2}); }
  var cs=document.querySelectorAll('.cnt');
  Array.prototype.forEach.call(cs,function(el,i){
    var alvo=parseFloat(el.dataset.alvo), t=el.dataset.fmt||'brl', ini=null;
    el.textContent=fmt(0,t);
    function passo(ts){ if(!ini) ini=ts; var p=Math.min(1,(ts-ini)/1100), f=1-Math.pow(1-p,3); el.textContent=fmt(alvo*f,t); if(p<1) requestAnimationFrame(passo); }
    setTimeout(function(){ requestAnimationFrame(passo); }, 150+90*i);
  });
  setTimeout(function(){ document.body.classList.remove('pre'); }, 140);
})();
"""


# ------------------------------------------------------------------ montagem
def _montar(d, n, anterior, na, op, animar, avisos):
    mes, ano, _, _ = _competencia(d)
    e = d['empresa']
    cor = op.get('cor') or '#1f2a5a'
    escritorio = op.get('escritorio') or 'Liddera | Inteligência em Negócios'
    logo = f'<img src="{_esc(op["logo"])}" alt="">' if op.get('logo') else ''
    cnpj = re.sub(r'\D', '', e.get('cnpj', ''))
    cnpj_f = f'{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}' if len(cnpj) == 14 else cnpj
    t = n['tot']
    hero = (f'<div class="hero" style="background:linear-gradient(120deg,{cor},#2f4090)"><div class="topo"><div class="marca">{logo}{_esc(escritorio)}</div>'
            f'<div class="comp">Competência {mes}/{ano}</div></div><h1>Seu PIS e COFINS de {mes} de {ano}</h1><div class="emp">{_esc(e.get("nome"))} · CNPJ {_esc(cnpj_f)}</div></div>')
    resumo = f'<div class="resumo"><div class="t">Em resumo</div><div class="x">{_texto_resumo(d, n)}</div></div>'

    def cnt(v):
        return f'<b class="cnt" data-alvo="{v:.2f}">{_rs(v)}</b>'
    if n['caso'] == 'credor':
        k4 = f'<div class="kpi credor">{cnt(t["saldo"])}<span>Saldo credor — nada a pagar</span></div>'
    elif n['caso'] == 'nada':
        k4 = f'<div class="kpi laranja">{cnt(0)}<span>Valor a pagar</span></div>'
    else:
        k4 = f'<div class="kpi laranja">{cnt(t["pagar"])}<span>Valor a pagar</span></div>'
    kpis = (f'<div class="kpis"><div class="kpi">{cnt(n["receita"])}<span>Suas receitas no mês</span></div>'
            f'<div class="kpi azul">{cnt(t["debito"])}<span>Imposto sobre as vendas</span></div>'
            f'<div class="kpi verde">{cnt(t["cred"])}<span>Créditos das suas compras</span></div>{k4}</div>')
    casc = ''
    if n['caso'] != 'nada':
        casc = f'<div class="card"><h3>{"Por que não há nada a pagar" if n["caso"] == "credor" else "Como chegamos ao valor a pagar"}</h3><p class="sub">{_texto_cascata(n)}</p>{_cascata(n)}</div>'
    comp = _comparativo(d, n, anterior, na, avisos) if (anterior is not None and na is not None) else ''
    recado = ''
    if (op.get('recado') or '').strip():
        recado = f'<div class="recado"><div class="t">Recado do escritório</div><div class="x">{_esc(op["recado"].strip()).replace(chr(10), "<br>")}</div></div>'
    guias = _guias(n, op)
    lado = f'<div class="duo" style="grid-template-columns:1fr 1fr">{guias}{recado}</div>' if (guias and recado) else (guias or recado)
    partes = [hero, resumo, kpis, _bloco_credor(n), casc, _por_tributo(n) if n['caso'] != 'nada' else '', _donut_e_ranking(d, n),
              _creditos_origem(d, n) if op.get('creditos', True) else '', _por_100(n), comp, lado, _glossario(d, n),
              _anexo_tecnico(d, n) if op.get('tecnico') else '']
    rodape = (f'<div class="rodape">Relatório gerado automaticamente a partir da EFD-Contribuições entregue de {mes}/{ano}. Ele explica o que foi apurado e declarado. '
              f'Em caso de dúvida, fale com o seu contador. · {_esc(escritorio)}</div>')
    corpo = '<div class="wrap">' + ''.join(p for p in partes if p) + rodape + '</div>'
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>PIS e COFINS de {mes}/{ano} · {_esc(e.get("nome"))}</title><style>{_CSS}</style></head>'
            f'<body{" class=pre" if animar else ""}>{corpo}{("<script>" + _JS + "</script>") if animar else ""}</body></html>')


def gerar_relatorio_cliente(dados, anterior=None, opcoes=None):
    """Devolve {'html': animado, 'html_estatico': p/ PDF, 'avisos': [...], 'resumo': {...}}."""
    op = dict(opcoes or {})
    n = calcular(dados)
    na = calcular(anterior) if anterior is not None else None
    avisos = []
    html_anim = _montar(dados, n, anterior, na, op, True, avisos)
    html_est = _montar(dados, n, anterior, na, op, False, [])
    mes, ano, _, _ = _competencia(dados)
    resumo = {'empresa': dados['empresa'].get('nome'), 'competencia': f'{mes}/{ano}', 'caso': n['caso'], 'receita': round(n['receita'], 2),
              'debito': round(n['tot']['debito'], 2), 'creditos': round(n['tot']['cred'], 2), 'pagar': round(n['tot']['pagar'], 2),
              'saldo_credor': round(n['tot']['saldo'], 2), 'comparativo': bool(anterior is not None and not avisos)}
    return {'html': html_anim, 'html_estatico': html_est, 'avisos': avisos, 'resumo': resumo}

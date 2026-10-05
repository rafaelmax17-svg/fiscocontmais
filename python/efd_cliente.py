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
    '01': 'Aquisição de mercadorias para revenda', '02': 'Aquisição de bens utilizados como insumo',
    '03': 'Serviços utilizados como insumo', '04': 'Energia elétrica e térmica', '05': 'Aluguéis de prédios',
    '06': 'Aluguéis de máquinas e equipamentos', '07': 'Armazenagem e frete nas vendas', '08': 'Arrendamento mercantil (leasing)',
    '09': 'Aquisição de máquinas e equipamentos', '10': 'Depreciação de máquinas e equipamentos', '11': 'Devoluções de vendas',
    '12': 'Outras operações com direito a crédito', '13': 'Subcontratação de transporte de cargas',
    '14': 'Atividade imobiliária', '15': 'Atividade imobiliária', '16': 'Serviços de limpeza e manutenção',
}
# como a natureza do crédito aparece dentro de uma frase
_CRED_DESCR = {
    '01': 'aquisições de mercadorias para revenda', '02': 'aquisições de bens aplicados na atividade (insumos)',
    '03': 'serviços contratados aplicados na atividade (insumos)', '04': 'despesas com energia elétrica e térmica', '05': 'aluguéis de prédios',
    '06': 'aluguéis de máquinas e equipamentos', '07': 'armazenagem e fretes nas operações de venda', '08': 'contraprestações de arrendamento mercantil',
    '09': 'aquisições de máquinas e equipamentos', '10': 'depreciação de máquinas e equipamentos', '11': 'devoluções de vendas',
    '12': 'outras operações com direito a crédito', '13': 'subcontratação de transporte de cargas', '14': 'atividade imobiliária',
    '15': 'atividade imobiliária', '16': 'serviços de limpeza e manutenção',
}
_CST_GRUPO = {
    '04': ('Tributação Monofásica (Indústria)', '#2f4090'), '05': ('Substituição Tributária', '#8b5cf6'),
    '06': ('Alíquota Zero', '#e8632b'), '07': ('Isenção', '#0ea5a4'), '08': ('Sem Incidência', '#6b7392'),
    '09': ('Suspensão', '#d4a017'), '49': ('Outras Operações', '#8a90a8'), '99': ('Outras Operações', '#8a90a8'),
}
_CST_ROTULO = {'04': 'Monofásico', '05': 'Substituição Tributária', '06': 'Alíquota Zero', '07': 'Isenção', '08': 'Sem Incidência',
               '09': 'Suspensão', '49': 'Outras Hipóteses', '99': 'Outras Hipóteses'}
_CST_FORMA = {'04': 'pela tributação concentrada na indústria (regime monofásico)', '05': 'pela substituição tributária',
              '06': 'pela aplicação de alíquota zero', '07': 'por isenção', '08': 'pela não incidência',
              '09': 'pela suspensão da exigibilidade', '49': 'por outras hipóteses legais', '99': 'por outras hipóteses legais'}
_CST_ORDEM = ['04', '05', '06', '07', '08', '09', '49', '99']
# nomes curtos (a descrição oficial é longa e vem cortada da própria tabela)
_NOMES_CURTOS = [
    (r'gen[ée]rico', 'Outras Mercadorias Desoneradas'),
    (r'^carnes\b.*origem animal', 'Carnes e derivados'),
    (r'^[áa]guas minerais', 'Águas minerais'),
    (r'^queijos', 'Queijos'),
    (r'^leite\b', 'Leite'),
    (r'^pr[ée]-misturas.*p[aã]o', 'Pré-misturas para pão'),
]


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
    """Nome curto e legível de uma natureza da receita (a descrição oficial é longa e cheia de NCM). Nunca corta no meio da palavra."""
    t = (desc or '').strip()
    if ' — ' in t:
        t = t.split(' — ', 1)[1]
    t = re.sub(r'^Receita decorrente d[ae]( venda| revenda)? d[eao]s? ', '', t, flags=re.I)
    for padrao, nome in _NOMES_CURTOS:
        if re.search(padrao, t, re.I):
            return nome
    for corte in (', classificad', ' classificad', ' – ', ' - ', ' (', ';', ', conforme', ' conforme', ', quando', ' quando '):
        i = t.lower().find(corte.lower())
        if i > 0:
            t = t[:i]
    t = t.strip(' .,')
    if sum(1 for w in t.split() if w[:1].isupper()) >= 2:      # "Etanol Não Combustível" -> "Etanol não combustível"
        t = t[:1] + t[1:].lower()
    t = t[:1].upper() + t[1:]
    if len(t) > 58:                                              # abrevia só entre palavras
        t = t[:58].rsplit(' ', 1)[0].rstrip(' ,;:-') + '…'
    return t or 'Outras Mercadorias Desoneradas'


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
        'cum': c['apurado_cumulativo'], 'nc': c['apurado_nao_cumulativo'],
    }


def calcular(d):
    pis, cof = _tributo(d['pis']), _tributo(d['cofins'])
    trib = sum(c['receita_bruta'] for c in d['pis']['por_cst'])
    nao = sum(x['valor'] for x in d['pis']['nao_tributada_cst'])
    receita = trib + nao or (d.get('receita_0111') or {}).get('total', 0.0)
    tot = {k: pis[k] + cof[k] for k in ('debito', 'cred', 'pagar', 'saldo', 'gerado', 'outras', 'anterior')}
    n = {'receita': receita, 'trib': trib, 'nao_trib': nao, 'pis': pis, 'cofins': cof, 'tot': tot}
    n['cumulativo'] = (pis['cum'] + cof['cum'] > _EPS) and (pis['nc'] + cof['nc'] <= _EPS)
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
    ef = _pct(n['por100']['pagar'], 2)
    txt = f'Em <b>{mes} de {ano}</b>, sua empresa registrou faturamento de <b>{_rs(n["receita"])}</b>. '
    if n['caso'] == 'nada':
        return txt + 'No período, <b>não houve PIS/COFINS a recolher</b> nem saldo de créditos a transportar.'
    txt += f'Sobre as operações tributadas, o PIS e a COFINS totalizaram <b>{_rs(t["debito"])}</b>. '
    if n['caso'] == 'credor':
        return txt + (f'Os créditos fiscais apurados (<b>{_rs(t["cred"] + t["saldo"])}</b>) superaram os débitos do período: não há saldo a recolher e '
                      f'permanece <b style="color:#0f6e56">saldo credor de {_rs(t["saldo"])}</b>, a ser transportado para as competências seguintes.')
    aj = ''
    if t['outras'] > _EPS:
        aj = f' e as deduções por retenções e demais ajustes (<b>{_rs(t["outras"])}</b>)'
    elif t['outras'] < -_EPS:
        aj = f' e os acréscimos por demais ajustes (<b>{_rs(-t["outras"])}</b>)'
    if t['cred'] > _EPS:
        txt += f'Com os créditos fiscais apurados sobre compras e despesas operacionais (<b>{_rs(t["cred"])}</b>){aj}, o saldo líquido a recolher foi de '
    else:
        motivo = 'No regime cumulativo não há apropriação de créditos fiscais' if n.get('cumulativo') else 'Não houve créditos fiscais a apropriar no período'
        txt += f'{motivo}{"; foram consideradas, ainda, as deduções por retenções e demais ajustes (<b>" + _rs(t["outras"]) + "</b>)" if t["outras"] > _EPS else ""}. O saldo a recolher foi de '
    if n['caso'] == 'normal':
        return txt + f'<b style="color:#c2500f">{_rs(t["pagar"])}</b>, representando uma <b>alíquota efetiva de {ef}</b> sobre a receita bruta.'
    ps = [(nome, n[k]) for nome, k in (('PIS', 'pis'), ('COFINS', 'cofins'))]
    a_pagar = '; '.join(f'{nome}: {_rs(x["pagar"])}' for nome, x in ps if x['pagar'] > _EPS)
    credor = ' '.join(f'{"No" if nome == "PIS" else "Na"} {nome}, os créditos superaram os débitos, remanescendo saldo credor de <b>{_rs(x["saldo"])}</b> a transportar.'
                      for nome, x in ps if x['pagar'] <= _EPS and x['saldo'] > _EPS)
    return txt + f'<b style="color:#c2500f">{_rs(t["pagar"])}</b> ({a_pagar}), representando uma <b>alíquota efetiva de {ef}</b> sobre a receita bruta. {credor}'


def _texto_cascata(n):
    if n['caso'] == 'credor':
        return ('Apuração líquida do período: os créditos fiscais admitidos por lei superaram os débitos tributários gerados pelas vendas; '
                '<b>não há saldo a recolher</b> e a diferença constitui saldo credor a transportar.')
    if n.get('cumulativo'):
        return 'Apuração no regime cumulativo: o saldo a recolher corresponde aos débitos tributários gerados pelas vendas, sem apropriação de créditos fiscais.'
    return 'Apuração líquida do período: dedução dos créditos fiscais admitidos por lei sobre os débitos tributários gerados pelas vendas.'


def _texto_cem(n):
    return ''


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
    cols = [coluna('Débitos Apurados', 'Vendas e Saídas', [barra('azul', 0, px(t['debito']), _rs(t['debito']))])]
    if caso == 'credor':
        usado, saldo = t['cred'], t['saldo']
        cols.append(seta)
        cols.append(coluna('Créditos Fiscais', 'Disponíveis no período', [
            barra('verde', 0, px(usado), '', ''),
            barra('verde-claro', px(usado), px(saldo), _rs(usado + saldo), 'border-radius:10px 10px 4px 4px'),
        ]))
        cols.append(igual('#0f9d6e'))
        cols.append(coluna('Saldo Credor', 'A transportar', [barra('verde', 0, px(saldo), _rs(saldo))]))
        return '<div class="casc">' + ''.join(cols) + '</div>'
    nivel = t['debito']
    if t['cred'] > _EPS:
        novo = nivel - t['cred']
        cols.append(seta)
        cols.append(coluna('Créditos Fiscais', 'Insumos e Entradas', [barra('verde', px(novo), px(nivel) - px(novo), '− ' + _rs(t['cred']))]))
        nivel = novo
    if abs(t['outras']) > _EPS:
        cols.append(seta)
        if t['outras'] > 0:
            novo = nivel - t['outras']
            cols.append(coluna('Retenções e Ajustes', 'Deduções do período', [barra('cinza', px(novo), px(nivel) - px(novo), '− ' + _rs(t['outras']))]))
            nivel = novo
        else:
            novo = nivel - t['outras']
            cols.append(coluna('Outros Ajustes', 'Acréscimos do período', [barra('cinza', px(nivel), px(novo) - px(nivel), '+ ' + _rs(-t['outras']))]))
            nivel = novo
    cols.append(igual('#e8632b'))
    cols.append(coluna('Saldo a Recolher', 'Guias de DARF', [barra('laranja', 0, px(t['pagar']), _rs(t['pagar']))]))
    return '<div class="casc">' + ''.join(cols) + '</div>'


def _juntar(itens, ult=' e '):
    itens = list(itens)
    return itens[0] if len(itens) == 1 else ', '.join(itens[:-1]) + ult + itens[-1]


def _donut_e_ranking(d, n):
    if n['nao_trib'] <= _EPS or n['receita'] <= _EPS:
        return ''
    pct_nao = 100.0 * n['nao_trib'] / n['receita']
    C = 2 * 3.14159265 * 62
    arco = C * pct_nao / 100
    grupos = defaultdict(float)
    completo = defaultdict(list)
    for x in d['pis']['nao_tributada_natureza']:
        bruto = re.sub(r'^\s*\d+\s*—\s*', '', x['natureza_desc'] or '').strip()
        nome = _nome_simples(x['natureza_desc'])
        if 'não catalogado' in x['natureza_desc'] or 'sem tabela' in x['natureza_desc']:
            nome = f'Outras Mercadorias Desoneradas (cód. {x["natureza"]})'
            bruto = f'Natureza da receita {x["natureza"]}: sem descrição na tabela oficial vigente'
        grupos[(x['cst'], nome)] += x['valor']
        if bruto and bruto not in completo[(x['cst'], nome)]:
            completo[(x['cst'], nome)].append(bruto)
    if not grupos:
        for x in d['pis']['nao_tributada_cst']:
            grupos[(x['cst'], _CST_GRUPO.get(x['cst'], ('Outras Operações', ''))[0])] += x['valor']
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
        tip = _esc('; '.join(completo.get((cst, nome), [])) or nome)
        barras += (f'<div class="hlinha"><span title="{tip}">{_esc(nome)}</span><span class="htrilho"><span class="hfill" style="width:{100 * v / mx:.1f}%;background:linear-gradient(90deg,{cor},{_mix(cor, (255, 255, 255), .35)})"></span></span>'
                   f'<b>{_int(v)}</b></div>')
    leg = ' &nbsp; '.join(f'<span class="ponto" style="background:{_CST_GRUPO[c][1]}"></span>{_CST_GRUPO[c][0]}' for c in csts_usados if c in _CST_GRUPO)
    presentes = [c for c in _CST_ORDEM if c in {x['cst'] for x in d['pis']['nao_tributada_cst']}] or [c for c in _CST_ORDEM if c in csts_usados]
    formas = []
    rotulos = []
    for c in presentes:
        if _CST_FORMA[c] not in formas:
            formas.append(_CST_FORMA[c])
        if _CST_ROTULO[c] not in rotulos:
            rotulos.append(_CST_ROTULO[c])
    alias = {'Carnes e derivados': 'carnes'}      # nomes curtos só para a frase
    nomes = [alias.get(nome, nome[:1].lower() + nome[1:]) for (_, nome), _v in linhas[:3] if nome != 'Outros' and not nome.startswith('Outras Mercadorias')]
    sub = ('Determinadas operações contam com previsão legal de desoneração tributária — seja ' + _juntar(formas, ' ou ') + '.'
           + (f' No período, destacaram-se produtos como {_esc(_juntar(nomes))}.' if nomes else ''))
    donut = (f'<div class="card"><h3>Composição da Receita Bruta</h3><div class="donutbox"><svg width="170" height="170" viewBox="0 0 160 160">'
             f'<circle cx="80" cy="80" r="62" fill="none" stroke="#2f4090" stroke-width="24"/>'
             f'<circle class="arco" cx="80" cy="80" r="62" fill="none" stroke="#e8632b" stroke-width="24" stroke-dasharray="{arco:.2f} {C:.2f}" transform="rotate(-90 80 80)"/>'
             f'<text x="80" y="78" text-anchor="middle" font-size="26" font-weight="800" fill="#232a3d">{round(pct_nao)}%</text>'
             f'<text x="80" y="95" text-anchor="middle" font-size="9.5" fill="#7a8199">Desoneradas</text></svg></div>'
             f'<div class="legenda"><span class="ponto" style="background:#2f4090"></span>Tributadas: <b>{_rs(n["trib"])}</b> ({round(100 - pct_nao)}%)<br>'
             f'<span class="ponto" style="background:#e8632b"></span>Receitas Desoneradas ({" / ".join(rotulos)}): <b>{_rs(n["nao_trib"])}</b> ({round(pct_nao)}%)</div></div>')
    rank = (f'<div class="card"><h3>Detalhamento das Receitas Desoneradas ({round(pct_nao)}%)</h3>'
            f'<p class="sub">{sub}</p><div class="hlista">{barras}</div>'
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
    linhas = [(k, _CRED_SIMPLES.get(k) or _NATUREZA_CREDITO.get(k.zfill(2), f'Natureza {k}'), v) for k, v in por_nat.items()]
    if t['anterior'] > _EPS:
        linhas.append(('ant', 'Saldo de créditos de períodos anteriores', t['anterior']))
    linhas = sorted([x for x in linhas if x[2] > _EPS], key=lambda kv: -kv[2])
    if not linhas:
        return ''
    total = sum(v for _, _, v in linhas)
    mx = linhas[0][2]
    barras = ''.join(
        f'<div class="hlinha"><span title="{_esc(nome)}">{_esc(nome)}</span><span class="htrilho"><span class="hfill" style="width:{100 * v / mx:.1f}%;background:linear-gradient(90deg,#0f9d6e,#5ed1a8)"></span></span><b>{_int(v)}</b></div>'
        for _, nome, v in linhas)
    cod, nome, v = linhas[0]
    descr = _CRED_DESCR.get(cod) or ('saldo de créditos de períodos anteriores' if cod == 'ant' else nome[:1].lower() + nome[1:])
    return (f'<div class="card"><h3>Composição dos Créditos Fiscais</h3>'
            f'<p class="sub">No regime não cumulativo, a aquisição de insumos operacionais, serviços essenciais e mercadorias gera créditos tributários compensatórios. '
            f'Dos <b>{_rs(total)}</b> apurados no mês, <b>{_pct(100 * v / total, 0)}</b> decorrem de <b>{_esc(descr)}</b>.</p>'
            f'<div class="hlista">{barras}</div><div class="nota-pq">valores em R$</div></div>')


def _por_100(n):
    p, t = n['por100'], n['tot']
    if n['receita'] <= _EPS or p['debito'] <= _EPS:
        return ''
    bruta, abat, efet = p['debito'], p['cred'], p['pagar']
    pis, cof = n['pis'], n['cofins']
    chips = ''
    if t['pagar'] > _EPS:
        for nome, x in (('COFINS', cof), ('PIS', pis)):
            if x['pagar'] > _EPS:
                chips += f'<span class="pilula azul">{nome} a recolher: {_rs(x["pagar"])} ({round(100 * x["pagar"] / t["pagar"])}% do saldo)</span>'
    if n['caso'] == 'credor':
        sub = (f'A alíquota bruta calculada sobre as operações seria de <b>{_pct(bruta, 2)}</b>. Os créditos fiscais do mês superaram os débitos, '
               f'de modo que a <b>alíquota efetiva recolhida foi de 0,00%</b> sobre a receita total.')
        seg = '<div class="seg" style="width:100%;background:linear-gradient(180deg,#3fc596,#0f9d6e)">Créditos Fiscais superaram 100% dos débitos</div>'
        chips = f'<span class="pilula verde">Saldo credor a transportar: {_rs(t["saldo"])}</span>'
    elif n.get('cumulativo') or t['cred'] <= _EPS:
        sub = f'A alíquota efetiva recolhida foi de <b>{_pct(efet, 2)}</b> sobre a receita total, sem apropriação de créditos fiscais no período.'
        seg = f'<div class="seg" style="width:100%;background:linear-gradient(180deg,#ff9f66,#e8632b)">{_pct(efet, 2)} Alíquota Efetiva Recolhida (100%)</div>'
    else:
        wc = 100.0 * t['cred'] / t['debito']
        wo = max(t['outras'], 0.0) / t['debito'] * 100.0
        wp = max(100.0 - wc - wo, 0.0)
        ret = f' e de <b>{_pct(100 * max(t["outras"], 0) / n["receita"], 2)}</b> por retenções e demais ajustes' if wo > 0.05 else ''
        sub = (f'A alíquota bruta calculada sobre as operações seria de <b>{_pct(bruta, 2)}</b>. Com o abatimento de <b>{_pct(abat, 2)}</b> decorrente dos créditos fiscais do mês{ret}, '
               f'a <b>alíquota efetiva recolhida foi de {_pct(efet, 2)}</b> sobre a receita total.')
        seg = (f'<div class="seg" title="{_pct(abat, 2)} Abatidos em Créditos" style="width:{wc:.1f}%;background:linear-gradient(180deg,#3fc596,#0f9d6e)">{_pct(abat, 2)} Abatidos em Créditos ({_pct(wc, 1)})</div>')
        if wo > 0.05:
            seg += f'<div class="seg" style="width:{wo:.1f}%;background:linear-gradient(180deg,#9aa1b8,#6b7392)"></div>'
        seg += f'<div class="seg" title="{_pct(efet, 2)} Alíquota Efetiva Recolhida" style="width:{wp:.1f}%;background:linear-gradient(180deg,#ff9f66,#e8632b)">{_pct(efet, 2)} Alíquota Efetiva Recolhida ({_pct(wp, 1)})</div>'
        chips += f'<span class="pilula verde">{_pct(wc, 1)} do imposto bruto foi absorvido por créditos fiscais</span>'
    return (f'<div class="card"><h3>Análise da Carga Tributária Efetiva</h3><p class="sub">{sub}</p>'
            f'<div class="empilhada">{seg}</div><div class="pilulas">{chips}</div></div>')


def _por_tributo(n):
    def linha(rot, a, b, cor=''):
        return f'<tr><td>{rot}</td><td style="text-align:right;{cor}">{_rs(a)}</td><td style="text-align:right;{cor}">{_rs(b)}</td></tr>'
    pis, cof = n['pis'], n['cofins']
    corpo = (linha('Débitos sobre Saídas', pis['debito'], cof['debito']) + linha('Créditos sobre Entradas', pis['cred'], cof['cred'], 'color:#0f6e56')
             + linha('Saldo a Recolher', pis['pagar'], cof['pagar'], 'color:#c2500f;font-weight:800'))
    if n['tot']['saldo'] > _EPS:
        corpo += linha('Saldo Credor (a transportar)', pis['saldo'], cof['saldo'], 'color:#0f6e56;font-weight:800')
    return f'<div class="card"><h3>PIS e COFINS separados</h3><table class="tb"><thead><tr><th></th><th>PIS</th><th>COFINS</th></tr></thead><tbody>{corpo}</tbody></table></div>'


def _darf(c):
    s = re.sub(r'\D', '', str(c or ''))
    return f'{s[:4]}-{s[4:]}' if len(s) == 6 else (str(c) if c else '—')


def _guias(n, op):
    if n['tot']['pagar'] <= _EPS:
        return ''
    linhas = ''
    for nome, x in (('COFINS', n['cofins']), ('PIS', n['pis'])):
        if x['pagar'] > _EPS:
            cods = ', '.join(_darf(c['codigo_darf']) for c in x['darf']) or '—'
            linhas += f'<div class="guia"><span><b>{nome}</b> · Código {_esc(cods)}</span><b>{_rs(x["pagar"])}</b></div>'
    linhas += f'<div class="guia total"><span>Total a Recolher</span><span>{_rs(n["tot"]["pagar"])}</span></div>'
    venc = f'<div class="nota-pq" style="margin-top:8px">Vencimento: <b>{_esc(op.get("vencimento"))}</b></div>' if op.get('vencimento') else ''
    return f'<div class="card"><h3>Guias de Recolhimento (DARF)</h3><div class="guias">{linhas}</div>{venc}</div>'


def _bloco_credor(n):
    t = n['tot']
    if n['caso'] == 'nada' or t['saldo'] <= _EPS:
        return ''
    partes = [(nome, n[k]['saldo']) for nome, k in (('PIS', 'pis'), ('COFINS', 'cofins')) if n[k]['saldo'] > _EPS]
    detalhe = ' e '.join(f'{nome}: <b>{_rs(v)}</b>' for nome, v in partes)
    if n['caso'] == 'credor':
        titulo = 'Sem saldo a recolher no período'
        intro = f'Os créditos fiscais superaram os débitos apurados, resultando em <b>saldo credor de {_rs(t["saldo"])}</b> ({detalhe}). '
    elif n['caso'] == 'misto':
        titulo = 'Saldo credor em um dos tributos'
        intro = f'Em um dos tributos, os créditos fiscais superaram os débitos apurados, resultando em <b>saldo credor de {_rs(t["saldo"])}</b> ({detalhe}). '
    else:
        titulo = 'Saldo credor a transportar'
        intro = f'Além do saldo a recolher, permanece <b>saldo credor de {_rs(t["saldo"])}</b> ({detalhe}). '
    return (f'<div class="caixa-credor"><div class="credor-ico">✓</div><div><div class="credor-t">{titulo}</div>'
            f'<div class="credor-x">{intro}'
            f'O saldo credor corresponde à parcela do crédito fiscal que excede o débito do período e permanece disponível para compensação nas competências seguintes, '
            f'sempre com o próprio tributo. O escritório acompanha esse saldo. '
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
    itens = [('Faturamento Bruto', n['receita'], na['receita'], '#2f4090', True), ('Débitos de PIS/COFINS', n['tot']['debito'], na['tot']['debito'], '#4f62b5', False),
             ('Créditos de Entradas', n['tot']['cred'], na['tot']['cred'], '#0f9d6e', True), ('Saldo a Recolher', n['tot']['pagar'], na['tot']['pagar'], '#e8632b', False)]
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
            frases.append(f'O faturamento bruto manteve-se praticamente estável em relação a {mes_ant} ({_rs(n["receita"])}).')
        else:
            frases.append(f'O faturamento bruto {"cresceu" if var >= 0 else "reduziu"} <b>{_pct(abs(var))}</b> em relação a {mes_ant} (de {_rs(na["receita"])} para {_rs(n["receita"])}).')
    if na['tot']['pagar'] > _EPS and n['tot']['pagar'] > _EPS:
        var = 100 * (n['tot']['pagar'] - na['tot']['pagar']) / na['tot']['pagar']
        if abs(var) < 0.05:
            frases.append(f'O saldo a recolher manteve-se igual ao de {mes_ant} ({_rs(n["tot"]["pagar"])}).')
        else:
            frases.append(f'O saldo a recolher {"aumentou" if var >= 0 else "reduziu"} <b>{_pct(abs(var))}</b> (de {_rs(na["tot"]["pagar"])} para {_rs(n["tot"]["pagar"])}).')
    elif na['tot']['pagar'] > _EPS and n['tot']['pagar'] <= _EPS:
        frases.append(f'Em {mes_ant} havia saldo a recolher de {_rs(na["tot"]["pagar"])}; em {mes}, não há saldo a recolher.')
    elif n['tot']['pagar'] > _EPS and na['tot']['pagar'] <= _EPS:
        frases.append(f'Em {mes_ant} não havia saldo a recolher; em {mes}, o saldo a recolher é de {_rs(n["tot"]["pagar"])}.')
    if na['receita'] > _EPS and n['receita'] > _EPS:
        frases.append(f'A alíquota efetiva recolhida foi de <b>{_pct(n["por100"]["pagar"], 2)}</b> sobre a receita bruta (em {mes_ant}: {_pct(na["por100"]["pagar"], 2)}).')
    return (f'<div class="card"><h3>Comparativo com {mes_ant}</h3><p class="sub">{" ".join(frases)}</p>'
            f'<div class="cgrupos">{grupos}</div><div class="nota-pq"><span class="ponto" style="background:#9aa6d4"></span>{mes_ant} &nbsp; <span class="ponto" style="background:#e8632b"></span>{mes} · valores em R$ · cada grupo usa a sua própria escala</div></div>')


def _glossario(d, n):
    csts = {x['cst'] for x in d['pis']['nao_tributada_cst']}
    termos = []
    if n['tot']['cred'] + n['tot']['saldo'] > _EPS:
        termos.append(('Crédito Tributário', 'Direito creditório decorrente de aquisições de insumos, serviços e custos admitidos pela legislação no regime não cumulativo, utilizado para abater o imposto devido sobre as saídas.'))
    if n.get('cumulativo'):
        termos.append(('Regime Cumulativo', 'Sistemática em que o PIS (0,65%) e a COFINS (3%) incidem diretamente sobre a receita, sem direito a créditos sobre as aquisições.'))
    if '04' in csts:
        termos.append(('Regime Monofásico', 'Mecanismo em que a tributação de PIS/COFINS é concentrada no fabricante ou importador em alíquota única maior, desonerando a venda nas etapas subsequentes (atacadistas e varejistas).'))
    if '06' in csts:
        termos.append(('Alíquota Zero', 'Disposição legal que reduz a alíquota a 0% sobre determinados produtos essenciais ou incentivados, desonerando a venda na apuração do imposto.'))
    if '05' in csts:
        termos.append(('Substituição Tributária', 'Mecanismo em que a responsabilidade pelo recolhimento do tributo devido nas etapas seguintes é atribuída a um participante anterior da cadeia, que o recolhe antecipadamente.'))
    if n['tot']['saldo'] > _EPS:
        termos.append(('Saldo Credor', 'Parcela do crédito fiscal que excede o débito do período e permanece disponível para compensação nas competências seguintes, sempre com o próprio tributo (o crédito de PIS compensa PIS; o de COFINS, COFINS).'))
    if n['tot']['pagar'] > _EPS:
        termos.append(('DARF (Documento de Arrecadação)', 'Guia oficial emitida para o recolhimento dos tributos federais apurados junto à Receita Federal do Brasil.'))
    return ('<div class="card"><h3>Glossário e Conceitos Tributários</h3><div class="gloss">' +
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
.hlinha{display:grid;grid-template-columns:minmax(150px,38%) 1fr 84px;gap:10px;align-items:center}
.hlinha>span:first-child{min-width:0;line-height:1.3;overflow-wrap:break-word;word-break:normal;hyphens:auto}
.htrilho{height:12px;border-radius:6px;background:#eef0f6;overflow:hidden;display:block}
.hfill{display:block;height:100%;box-shadow:inset 0 2px 0 rgba(255,255,255,.35);transition:width 1.1s cubic-bezier(.2,.8,.2,1)}
.hlinha b{text-align:right}
.nota-pq{font-size:10.5px;color:#7a8199;margin-top:9px}
.empilhada{display:flex;height:34px;border-radius:12px;overflow:hidden;box-shadow:0 8px 14px rgba(31,42,90,.18),inset 0 2px 0 rgba(255,255,255,.3)}
.seg{display:flex;align-items:center;justify-content:center;color:#fff;font-size:12px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 8px;transition:width 1.2s cubic-bezier(.2,.8,.2,1)}
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
@media (max-width:640px){.kpis{grid-template-columns:repeat(2,1fr)}.duo{grid-template-columns:1fr}.hlinha{grid-template-columns:minmax(110px,40%) 1fr 70px}.cgrupos{grid-template-columns:repeat(2,1fr)}.gloss{grid-template-columns:1fr}.casc{overflow-x:auto}}
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
        k4 = f'<div class="kpi credor">{cnt(t["saldo"])}<span>Saldo Credor a Transportar</span></div>'
    elif n['caso'] == 'nada':
        k4 = f'<div class="kpi laranja">{cnt(0)}<span>Saldo a Recolher</span></div>'
    else:
        k4 = f'<div class="kpi laranja">{cnt(t["pagar"])}<span>Saldo a Recolher</span></div>'
    cred_kpi = (f'<div class="kpi verde">{cnt(t["cred"] + t["saldo"])}<span>Créditos Disponíveis</span></div>' if n['caso'] == 'credor'
                else f'<div class="kpi verde">{cnt(t["cred"])}<span>Créditos de Entradas</span></div>')
    kpis = (f'<div class="kpis"><div class="kpi">{cnt(n["receita"])}<span>Faturamento Bruto</span></div>'
            f'<div class="kpi azul">{cnt(t["debito"])}<span>Débitos de PIS/COFINS</span></div>'
            f'{cred_kpi}{k4}</div>')
    casc = ''
    if n['caso'] != 'nada':
        casc = f'<div class="card"><h3>{"Por que não há saldo a recolher" if n["caso"] == "credor" else "Como chegamos ao valor a pagar"}</h3><p class="sub">{_texto_cascata(n)}</p>{_cascata(n)}</div>'
    comp = _comparativo(d, n, anterior, na, avisos) if (anterior is not None and na is not None) else ''
    recado = ''
    if (op.get('recado') or '').strip():
        recado = f'<div class="recado"><div class="t">Recado do escritório</div><div class="x">{_esc(op["recado"].strip()).replace(chr(10), "<br>")}</div></div>'
    guias = _guias(n, op)
    lado = f'<div class="duo" style="grid-template-columns:1fr 1fr">{guias}{recado}</div>' if (guias and recado) else (guias or recado)
    partes = [hero, resumo, kpis, _bloco_credor(n), casc, _por_tributo(n) if n['caso'] != 'nada' else '', _donut_e_ranking(d, n),
              _creditos_origem(d, n) if op.get('creditos', True) else '', _por_100(n), comp, lado, _glossario(d, n),
              _anexo_tecnico(d, n) if op.get('tecnico') else '']
    rodape = (f'<div class="rodape">Relatório gerencial elaborado a partir das informações declaradas na EFD-Contribuições referente à competência {mes}/{ano}. '
              f'Documento destinado ao acompanhamento e controle tributário da empresa. Em caso de dúvidas sobre a apuração, consulte sua equipe contábil. · {_esc(escritorio)}</div>')
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

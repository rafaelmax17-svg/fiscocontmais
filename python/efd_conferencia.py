# -*- coding: utf-8 -*-
"""
Conferência EFD-Contribuições × relatórios do Domínio ("Acompanhamento de
Entradas" / "Acompanhamento de Saídas", por acumulador).

Descobertas (conferidas contra um SPED real + os dois relatórios, 30/09):
 - o acumulador do Domínio vai no campo COD_NAT dos itens (C170);
 - nas NFC-e (C175) só vem o CFOP — o acumulador é aprendido dos C170 de saída
   (CFOP -> acumulador) e, se faltar, associado pelo valor (e avisado);
 - o Domínio exporta a exclusão do ICMS da base dentro do campo "desconto" das
   linhas C175 (desconto real + ICMS), então NÃO se pode tratar esse campo como
   desconto comercial;
 - regra conferida: BC do PIS/COFINS = valor contábil − ICMS destacado
   − (valor, líquido de ICMS, dos itens sem BC, ex.: ST/sem crédito).
O que não bater é só sinalizado — a decisão contábil é do usuário.
"""
import html as _html
import re
from collections import Counter, defaultdict

TOL_ACUM = 0.05      # tolerância por acumulador (R$)
TOL_DOC = 0.02       # tolerância por documento (R$)
_SIT_EXCLUIDAS = ('02', '03', '04', '05')   # cancelado / denegado / inutilizado
_NAO_LIDOS = ('A100', 'C400', 'C490', 'C500', 'C600', 'C800', 'C860', 'D100', 'D200', 'D500', 'D600')


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


# ------------------------------------------------------------------ relatório do Domínio
_V = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
_TIPOS = r'(ICMS|DIFALI|IRRF|PIS-RET|COFINS-R|CSOC-RET|INSS-RET)'
_RE_PRIMEIRA = re.compile(_V + r'\s*' + _TIPOS + r'\s+' + _V + r'\s+' + _V + r'\s+' + _V + r'(?:\s+' + _V + r')?')
_RE_DEMAIS = re.compile(r'\b' + _TIPOS + r'\s+' + _V + r'\s+' + _V + r'\s+' + _V + r'(?:\s+' + _V + r')?')


def ler_relatorio_dominio(caminho):
    """Lê o PDF "Acompanhamento de Entradas/Saídas". Devolve tipo, CNPJ, período,
    acumuladores e total — e confere se a soma dos acumuladores fecha com o
    "Total Geral" do próprio relatório (se não fechar, a leitura é recusada)."""
    import pdfplumber
    with pdfplumber.open(caminho) as pdf:
        texto = '\n'.join((p.extract_text() or '') for p in pdf.pages)
    if re.search(r'ACOMPANHAMENTO DE ENTRADAS', texto, re.I):
        tipo = 'ENTRADAS'
    elif re.search(r'ACOMPANHAMENTO DE SA[ÍI]DAS', texto, re.I):
        tipo = 'SAIDAS'
    else:
        raise ValueError('esse PDF não parece ser um "Acompanhamento de Entradas" ou "de Saídas" do Domínio')
    m = re.search(r'CNPJ:\s*([\d./-]+)', texto)
    cnpj = re.sub(r'\D', '', m.group(1)) if m else ''
    m = re.search(r'Per[ií]odo:\s*(\d{2}/\d{2}/\d{4})\s*at[ée]\s*(\d{2}/\d{2}/\d{4})', texto)
    periodo = (m.group(1), m.group(2)) if m else ('', '')

    acum, total, atual, em_total = {}, {}, None, False
    for linha in texto.split('\n'):
        m = re.search(r'Acumulador:\s*(\d+)\s*-\s*(.+)$', linha)
        if m:
            atual = m.group(1)
            acum[atual] = {'nome': m.group(2).strip(), 'valor_contabil': 0.0, 'tipos': {}}
            em_total = False
            continue
        if 'Total Geral' in linha:
            em_total, atual = True, None
            continue
        alvo = total if em_total else (acum[atual] if atual else None)
        if alvo is None:
            continue
        tipos = alvo.setdefault('tipos', {})
        m = _RE_PRIMEIRA.search(linha)
        if m:
            alvo['valor_contabil'] = _num(m.group(1))
            tipos[m.group(2)] = [_num(x) for x in m.groups()[2:] if x]
            continue
        m = _RE_DEMAIS.search(linha)
        if m:
            tipos[m.group(1)] = [_num(x) for x in m.groups()[1:] if x]
    if not acum or 'valor_contabil' not in total:
        raise ValueError('não consegui localizar os acumuladores ou o Total Geral nesse relatório')

    soma_vc = sum(a['valor_contabil'] for a in acum.values())
    soma_icms = sum(a['tipos'].get('ICMS', [0, 0])[1] for a in acum.values())
    soma_bc = sum(a['tipos'].get('ICMS', [0])[0] for a in acum.values())
    t_icms = total['tipos'].get('ICMS', [0, 0])
    ok = (abs(soma_vc - total['valor_contabil']) < 0.005 and abs(soma_icms - t_icms[1]) < 0.005 and abs(soma_bc - t_icms[0]) < 0.005)
    if not ok:
        raise ValueError(f'a leitura não fecha com o Total Geral do relatório (valor contábil lido {_brl(soma_vc)} × total {_brl(total["valor_contabil"])}) — '
                         'por segurança a conferência não foi feita')
    return {'tipo': tipo, 'cnpj': cnpj, 'periodo': periodo, 'acumuladores': acum, 'total': total}


# ------------------------------------------------------------------ SPED
def agregar_sped(caminho):
    for enc in ('utf-8', 'latin-1'):
        try:
            with open(caminho, encoding=enc) as f:
                linhas = [l.rstrip('\r\n') for l in f if l.strip()]
            break
        except UnicodeDecodeError:
            continue
    docs, doc, cab, f100, nao_lidos = [], None, {}, defaultdict(float), Counter()
    for l in linhas:
        p = l.strip('|').split('|')
        reg, f = p[0], p[1:]

        def g(i):
            return f[i] if len(f) > i else ''
        if reg == '0000':
            cab = {'nome': g(6), 'cnpj': g(7), 'ini': g(4), 'fim': g(5)}
        elif reg == 'C100':
            doc = {'oper': g(0), 'mod': g(3), 'sit': g(4), 'ser': g(5), 'num': g(6), 'chv': g(7), 'dt': g(8),
                   'vl_doc': _num(g(10)), 'icms': _num(g(20)), 'linhas': []}
            docs.append(doc)
        elif reg == 'C170' and doc is not None:
            doc['linhas'].append({'o': 'C170', 'nat': g(10), 'cfop': g(9), 'valor': _num(g(5)), 'desc': _num(g(6)),
                                  'icms': _num(g(13)), 'bc': _num(g(24))})
        elif reg == 'C175' and doc is not None:
            doc['linhas'].append({'o': 'C175', 'nat': '', 'cfop': g(0), 'valor': _num(g(1)), 'desc': _num(g(2)),
                                  'icms': 0.0, 'bc': _num(g(4))})
        elif reg == 'F100':
            f100[g(0)] += _num(g(6))
        elif reg in _NAO_LIDOS:
            nao_lidos[reg] += 1
    return {'cab': cab, 'docs': docs, 'f100': dict(f100), 'nao_lidos': dict(nao_lidos)}


def _agrupar(docs, mapa):
    grupos = defaultdict(lambda: {'bc': 0.0, 'sem_bc': 0.0, 'icms': 0.0, 'icms_linhas': False, 'tem_175': False, 'n': 0, 'cfops': set()})
    for d in docs:
        for ln in d['linhas']:
            if ln['nat']:
                chave = ln['nat']
            elif ln['o'] == 'C175':
                chave = mapa.get(ln['cfop']) or '?' + ln['cfop']
            else:
                chave = '(sem natureza)'
            a = grupos[chave]
            a['bc'] += ln['bc']
            a['n'] += 1
            a['cfops'].add(ln['cfop'])
            if ln['o'] == 'C170':
                a['icms'] += ln['icms']
                a['icms_linhas'] = True
            else:
                a['tem_175'] = True
            if ln['bc'] == 0:
                a['sem_bc'] += ln['valor'] - ln['desc'] - ln['icms']
    return grupos


def _docs_fora(docs):
    out = []
    for d in docs:
        if not d['linhas']:
            continue
        bc = sum(l['bc'] for l in d['linhas'])
        sem = sum(l['valor'] - l['desc'] - l['icms'] for l in d['linhas'] if l['bc'] == 0)
        dif = bc - (d['vl_doc'] - d['icms'] - sem)
        if abs(dif) > TOL_DOC:
            out.append({'mod': d['mod'], 'ser': d['ser'], 'num': d['num'], 'dt': d['dt'], 'vl_doc': d['vl_doc'],
                        'icms': d['icms'], 'bc': bc, 'dif': dif, 'chv': d['chv']})
    return sorted(out, key=lambda x: -abs(x['dif']))


def _fmt_data(s):
    m = re.match(r'(\d{2})(\d{2})(\d{4})', s or '')
    return f'{m.group(1)}/{m.group(2)}/{m.group(3)}' if m else (s or '-')


def _conferir_oper(ag, oper, rel):
    docs = [d for d in ag['docs'] if d['oper'] == oper and d['sit'] not in _SIT_EXCLUIDAS]
    dom = rel['acumuladores']
    mapa = {}
    if oper == '1':       # CFOP -> acumulador, aprendido dos itens C170 de saída
        cont = defaultdict(Counter)
        for d in docs:
            for ln in d['linhas']:
                if ln['o'] == 'C170' and ln['nat']:
                    cont[ln['cfop']][ln['nat']] += 1
        mapa = {cfop: c.most_common(1)[0][0] for cfop, c in cont.items()}
    grupos = _agrupar(docs, mapa)

    # CFOP que só existe nas NFC-e: associa ao acumulador do Domínio sem lançamento que fechar em valor
    livres = [c for c in dom if c not in grupos]
    associacoes = []
    for k in [k for k in grupos if k.startswith('?')]:
        cand = []
        for c in livres:
            icms_d = dom[c]['tipos'].get('ICMS', [0, 0])[1]
            if abs(grupos[k]['bc'] - (dom[c]['valor_contabil'] - icms_d - grupos[k]['sem_bc'])) <= TOL_ACUM:
                cand.append(c)
        if len(cand) == 1:
            grupos[cand[0]] = grupos.pop(k)
            livres.remove(cand[0])
            associacoes.append((k[1:], cand[0]))

    linhas = []
    for cod in sorted(set(dom) | set(grupos), key=lambda x: (x.startswith('?') or x.startswith('('), x)):
        d, g = dom.get(cod), grupos.get(cod)
        if d is None:
            linhas.append({'cod': cod, 'nome': 'não consta no relatório do Domínio', 'status': 'so_sped', 'bc_sped': g['bc'],
                           'cfops': sorted(g['cfops'])})
            continue
        icms_d = d['tipos'].get('ICMS', [0, 0, 0, 0])
        item = {'cod': cod, 'nome': d['nome'], 'vc': d['valor_contabil'], 'icms_dom': icms_d[1],
                'outras': icms_d[3] if len(icms_d) > 3 else 0.0}
        if g is None:
            item['status'] = 'fora'
        else:
            item['icms_sped'] = g['icms'] if (g['icms_linhas'] and not g['tem_175']) else None   # NFC-e (C175) não traz ICMS por linha
            item['bc_sped'] = g['bc']
            item['sem_bc'] = g['sem_bc']
            item['bc_esp'] = d['valor_contabil'] - icms_d[1] - g['sem_bc']
            item['dif'] = round(item['bc_sped'] - item['bc_esp'], 2) + 0.0   # evita "-0,00"
            ok_icms = item['icms_sped'] is None or abs(item['icms_sped'] - icms_d[1]) <= TOL_ACUM
            item['status'] = 'ok' if abs(item['dif']) <= TOL_ACUM and ok_icms else 'dif'
            if item['outras'] > d['valor_contabil'] + TOL_ACUM and abs(item['bc_sped'] - (item['outras'] - g['sem_bc'])) <= TOL_ACUM:
                item['nota'] = (f"A BC no SPED coincide com a coluna \"Outras\" do Domínio (R$ {_brl(item['outras'])}) menos os itens sem BC "
                                f"(R$ {_brl(g['sem_bc'])}). Só que, no mesmo relatório, o valor contábil é R$ {_brl(d['valor_contabil'])}, "
                                f"ou seja, R$ {_brl(item['outras'] - d['valor_contabil'])} a menos que \"Outras\". Qual base vale é decisão contábil.")
        linhas.append(item)

    fora = [x for x in linhas if x['status'] == 'fora']
    t_icms = rel['total']['tipos'].get('ICMS', [0, 0])
    vc_dom, icms_dom = rel['total']['valor_contabil'], t_icms[1]
    vc_fora, icms_fora = sum(x['vc'] for x in fora), sum(x['icms_dom'] for x in fora)
    vc_sped = sum(d['vl_doc'] for d in docs)
    icms_sped = sum(d['icms'] for d in docs)
    bc_sped = sum(x['bc_sped'] for x in linhas if 'bc_sped' in x)
    bc_esp = sum(x['bc_esp'] for x in linhas if 'bc_esp' in x)
    f100 = sum(v for k, v in ag['f100'].items() if (k == '0') == (oper == '0'))
    comparaveis = [x for x in linhas if x['status'] in ('ok', 'dif')]
    return {
        'tipo': rel['tipo'], 'linhas': linhas, 'associacoes': associacoes,
        'totais': {'vc_dom': vc_dom, 'vc_fora': vc_fora, 'vc_esp': vc_dom - vc_fora, 'vc_sped': vc_sped,
                   'icms_dom': icms_dom, 'icms_fora': icms_fora, 'icms_esp': icms_dom - icms_fora, 'icms_sped': icms_sped,
                   'bc_esp': bc_esp, 'bc_sped': bc_sped, 'bc_f100': f100},
        'n_ok': sum(1 for x in comparaveis if x['status'] == 'ok'), 'n_comp': len(comparaveis),
        'docs_fora': _docs_fora(docs), 'n_docs': len([d for d in docs if d['linhas']]),
    }


def conferir(sped_path, dominio_entradas=None, dominio_saidas=None):
    ag = agregar_sped(sped_path)
    res = {'avisos': [], 'erros': [], 'saidas': None, 'entradas': None, 'nao_lidos': ag['nao_lidos']}
    cnpj_sped = re.sub(r'\D', '', ag['cab'].get('cnpj', ''))
    for oper, caminho, rotulo in (('1', dominio_saidas, 'Saídas'), ('0', dominio_entradas, 'Entradas')):
        if not caminho:
            continue
        try:
            rel = ler_relatorio_dominio(caminho)
            esperado = 'SAIDAS' if oper == '1' else 'ENTRADAS'
            if rel['tipo'] != esperado:
                raise ValueError(f'esse PDF é um "Acompanhamento de {"Saídas" if rel["tipo"] == "SAIDAS" else "Entradas"}", mas foi escolhido como {rotulo}')
            if rel['cnpj'] and cnpj_sped and rel['cnpj'] != cnpj_sped:
                res['avisos'].append(f'O relatório de {rotulo} do Domínio é de outro CNPJ ({rel["cnpj"]}) — o SPED é de {cnpj_sped}.')
            ini, fim = ag['cab'].get('ini', ''), ag['cab'].get('fim', '')
            ini_f, fim_f = _fmt_data(ini), _fmt_data(fim)
            if rel['periodo'][0] and (rel['periodo'][0] != ini_f or rel['periodo'][1] != fim_f):
                res['avisos'].append(f'O período do relatório de {rotulo} ({rel["periodo"][0]} a {rel["periodo"][1]}) é diferente do SPED ({ini_f} a {fim_f}).')
            res['saidas' if oper == '1' else 'entradas'] = _conferir_oper(ag, oper, rel)
        except Exception as e:
            res['erros'].append(f'Relatório de {rotulo} do Domínio: {e}')
    return res


# ------------------------------------------------------------------ HTML (usa as classes do painel da EFD-Contribuições)
_STATUS = {'ok': ('ok', 'Bate'), 'dif': ('dif', 'Diferença'), 'fora': ('fora', 'Fora do SPED'), 'so_sped': ('so', 'Só no SPED')}


def _bloco_oper(o, titulo):
    L = o['linhas']
    t = o['totais']
    saidas = o['tipo'] == 'SAIDAS'
    fora = [x for x in L if x['status'] == 'fora']
    icms_ok = abs(t['icms_sped'] - t['icms_esp']) <= TOL_ACUM
    cards = (
        f'<div class="res-grid">'
        f'<div class="res {"" if icms_ok else "am"}"><small>ICMS (total)</small><b>{"Bate" if icms_ok else "Diferença"}</b>'
        f'<small>SPED R$ {_brl(t["icms_sped"])} × Domínio R$ {_brl(t["icms_esp"])}'
        f'{" (já sem os acumuladores fora do SPED)" if fora else ""}</small></div>'
        f'<div class="res {"" if o["n_ok"] == o["n_comp"] else "am"}"><small>BC do PIS/COFINS</small>'
        f'<b>{o["n_ok"]} de {o["n_comp"]} acumuladores batem</b><small>diferença total R$ {_brl(t["bc_sped"] - t["bc_esp"])}</small></div>'
        f'<div class="res cz"><small>Sem lançamento no SPED</small><b>R$ {_brl(t["vc_fora"])}</b>'
        f'<small>{len(fora)} acumulador(es) do Domínio</small></div></div>')
    linhas = []
    for x in L:
        cls, rot = _STATUS[x['status']]
        st = f'<span class="st {cls}">{rot}</span>'
        nome = f'<b>{_esc(x["cod"])}</b> {_esc(x["nome"])}'
        if x['status'] == 'so_sped':
            linhas.append([nome + f' <small>(CFOP {_esc(", ".join(x["cfops"]))})</small>', '—', '—', '—', '—', _brl(x['bc_sped']), '—', st])
        elif x['status'] == 'fora':
            linhas.append([nome, _brl(x['vc']), _brl(x['icms_dom']), '—', '—', '—', '—', st])
        else:
            icms_s = _brl(x['icms_sped']) if x['icms_sped'] is not None else '—'
            dif = _brl(x['dif'])
            linhas.append([nome, _brl(x['vc']), _brl(x['icms_dom']), icms_s, _brl(x['bc_esp']), _brl(x['bc_sped']),
                           dif if abs(x['dif']) <= TOL_ACUM else f'<b style="color:#b8480f">{"+" if x["dif"] > 0 else ""}{dif}</b>', st])
    from efd_contribuicoes import _linhas_tabela
    tabela = _linhas_tabela(['Acumulador', 'Valor contábil Domínio', 'ICMS Domínio', 'ICMS SPED', 'BC esperada', 'BC no SPED', 'Diferença', 'Situação'],
                            linhas, ['l', 'r', 'r', 'r', 'r', 'r', 'r', 'c'])
    tot = [
        ['Valor contábil', _brl(t['vc_dom']), f'− {_brl(t["vc_fora"])}', _brl(t['vc_esp']), _brl(t['vc_sped']), _brl(t['vc_sped'] - t['vc_esp'])],
        ['ICMS destacado', _brl(t['icms_dom']), f'− {_brl(t["icms_fora"])}', _brl(t['icms_esp']), _brl(t['icms_sped']), _brl(t['icms_sped'] - t['icms_esp'])],
    ]
    totais = _linhas_tabela(['Totais', 'Domínio', 'Sem lançamento no SPED', 'Esperado no SPED', 'SPED (soma dos documentos)', 'Diferença'],
                            tot, ['l', 'r', 'r', 'r', 'r', 'r'])
    notas = ''
    for x in L:
        if x.get('nota'):
            notas += f'<div class="nota"><b>Acumulador {_esc(x["cod"])}</b> — {_esc(x["nota"])}</div>'
    if o['associacoes']:
        notas += ('<div class="nota">CFOP encontrado só nas NFC-e foi associado ao acumulador pelo valor (confira): ' +
                  '; '.join(f'CFOP {_esc(c)} → acumulador {_esc(a)}' for c, a in o['associacoes']) + '.</div>')
    if t['bc_f100']:
        notas += f'<div class="nota">Além dos documentos, há receitas/créditos lançados sem documento (F100) com BC de R$ {_brl(t["bc_f100"])}, que não aparecem no relatório do Domínio.</div>'
    docs = o['docs_fora']
    if docs:
        topo = docs[:15]
        tdocs = _linhas_tabela(
            ['Documento', 'Data', 'Valor contábil', 'ICMS', 'BC declarada', 'Diferença', 'Chave (final)'],
            [[f'mod {_esc(d["mod"])} · série {_esc(d["ser"])} · nº {_esc(d["num"])}', _fmt_data(d['dt']), _brl(d['vl_doc']), _brl(d['icms']), _brl(d['bc']),
              f'<b style="color:#b8480f">{"+" if d["dif"] > 0 else ""}{_brl(d["dif"])}</b>', '…' + _esc(d['chv'][-8:])] for d in topo],
            ['l', 'l', 'r', 'r', 'r', 'r', 'l'])
        extra = f' — mostrando os {len(topo)} maiores' if len(docs) > len(topo) else ''
        aviso_docs = (f'<div class="aviso"><b>{len(docs)} de {o["n_docs"]} documento(s)</b> não fecham pela regra '
                      f'<i>BC = valor contábil − ICMS − itens sem BC</i> (tolerância R$ {_brl(TOL_DOC)}){extra}. '
                      f'Diferenças pequenas costumam vir de arredondamento; maiores, de frete/seguro/outras despesas rateados ou de lançamento diferente.</div>'
                      f'<div class="card" style="margin:10px 0 0">{tdocs}</div>')
    else:
        aviso_docs = '<div class="nota" style="background:linear-gradient(90deg,#e1f5ee,#f0faf6);border-color:#a8dcc8;color:#085041">Todos os documentos fecham pela regra BC = valor contábil − ICMS − itens sem BC.</div>'
    return (f'<div class="card"><h3>{titulo}</h3>{cards}{tabela}<div style="height:12px"></div>{totais}{notas}</div>'
            f'<div style="margin:0 20px 16px">{aviso_docs}</div>')


def html_conferencia(res):
    """Seção "Conferência com o Domínio" (vazia se nenhum relatório foi anexado)."""
    if not (res['saidas'] or res['entradas'] or res['erros'] or res['avisos']):
        return ''
    partes = ['<h2 class="secao"><span class="dot" style="background:#0f6e56"></span>Conferência com o Domínio — valor contábil × BC do PIS/COFINS</h2>']
    for e in res['erros']:
        partes.append(f'<div class="aviso"><b>Não foi possível conferir.</b> {_esc(e)}</div>')
    for a in res['avisos']:
        partes.append(f'<div class="aviso">{_esc(a)}</div>')
    if res['nao_lidos']:
        partes.append('<div class="aviso">Este SPED tem registros que a conferência ainda não lê (' +
                      ', '.join(f'{k}: {v}' for k, v in sorted(res['nao_lidos'].items())) +
                      ') — a receita/crédito lançados neles pode aparecer como diferença.</div>')
    if res['saidas']:
        partes.append(_bloco_oper(res['saidas'], 'Saídas — acumuladores do Domínio × SPED'))
    if res['entradas']:
        partes.append(_bloco_oper(res['entradas'], 'Entradas — acumuladores do Domínio × SPED'))
    partes.append('<div class="card"><div style="font-size:11px;color:var(--ink2);line-height:1.6">'
                  'Regra: BC esperada = valor contábil (Domínio) − ICMS destacado (Domínio) − itens sem BC no SPED (ex.: substituição tributária, sem crédito). '
                  'Nas NFC-e o campo "desconto" do SPED traz o desconto real mais o ICMS, por isso não é usado como desconto. '
                  'O que não bate é apenas sinalizado; a decisão contábil é do usuário.</div></div>')
    return '\n'.join(partes)

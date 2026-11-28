# -*- coding: utf-8 -*-
"""CST × CFOP × ICMS (C190) — combinações que não fecham.

  • trib_sem_icms (decidir): saída com CST de tributação integral (x00) ou com redução (x20), sem base e sem ICMS.
    Ou o CST está errado (a operação é isenta/não tributada → x40/x41) ou faltou o débito. A troca de CST é por
    escolha da equipe; o débito que faltar não é lançado aqui (precisa da nota).
  • isento_com_icms (verificar): CST x40/x41/x50/x60 com ICMS no C190.
  • cfop_st_trib (verificar): CFOP de operação com ST (x.401/x.403/x.405/x.409/x.410/x.411) com CST tributado (x00/x20).
  • venda_cst60 (verificar): venda x.101/x.102 com CST x60 — mercadoria com ST já retida sai em x.405.
O id de cada linha é estável entre a análise e a correção: chave (ou modelo/série/número) + CST + CFOP + alíquota.
"""
from decimal import Decimal

import difal_ro as dr

CFOP_ST = ('401', '403', '405', '409', '410', '411')


def _n(s):
    try:
        return float(str(s or '0').replace(',', '.'))
    except ValueError:
        return 0.0


def _fm(v):
    return f'{v:,.2f}'.replace(',', '§').replace('.', ',').replace('§', '.')


def _docs(linhas):
    """[(C100 f, índice, [índices dos filhos])] — só C100 (o C190 é dele)."""
    out, cur = [], None
    for i, l in enumerate(linhas):
        reg = l[1:5] if l.startswith('|') else ''
        if reg == 'C100':
            cur = (l.split('|'), i, [])
            out.append(cur)
        elif cur and reg[:2] == 'C1' and reg > 'C100' and reg[1:4].isdigit() and int(reg[1:4]) < 200:
            cur[2].append(i)
        else:
            cur = None
    return out


def _doc_id(f):
    ch = f[9].strip() if len(f) > 9 else ''
    return ch if len(ch) == 44 else f'{f[5]}-{f[7]}-{f[8]}-{f[2]}-{f[4]}'


def analisar_texto(texto):
    linhas, _, _ = dr.dividir(texto)
    nomes = {}
    for l in linhas:
        if l.startswith('|0150|'):
            f = l.split('|')
            nomes[f[2]] = f[3]
    grupos = {'trib_sem_icms': [], 'isento_com_icms': [], 'cfop_st_trib': [], 'venda_cst60': []}
    for f, i, filhos in _docs(linhas):
        if len(f) < 10 or f[6] not in ('00', '01', '06', '07', '08'):
            continue
        for j in filhos:
            c = linhas[j].split('|')
            if c[1] != 'C190' or len(c) < 8:
                continue
            cst, cfop, aliq = c[2].strip(), c[3].strip(), c[4].strip()
            trib = cst[-2:]
            vopr, bc, icms = _n(c[5]), _n(c[6]), _n(c[7])
            if not cfop:
                continue
            regra = None
            if trib in ('00', '20') and icms == 0 and bc == 0 and vopr > 0 and cfop[0] in '567':
                regra = 'trib_sem_icms'
            elif trib in ('40', '41', '50', '60') and icms > 0:
                regra = 'isento_com_icms'
            elif cfop[1:] in CFOP_ST and trib in ('00', '20'):
                regra = 'cfop_st_trib'
            elif cfop[1:] in ('101', '102') and cfop[0] in '567' and trib == '60':
                regra = 'venda_cst60'
            if not regra:
                continue
            grupos[regra].append({
                'id': f'{_doc_id(f)}|{cst}|{cfop}|{aliq}', 'num': f[8], 'mod': f[5], 'oper': f[2],
                'part': nomes.get(f[4], f[4]), 'cst': cst, 'cfop': cfop, 'aliq': aliq, 'vopr': vopr, 'bc': bc, 'icms': icms})
    return grupos


def aplicar_texto(texto, escolhas):
    """escolhas = {id: '40' | '41'} (só o grupo trib_sem_icms). Troca o CST no C190 e nos C170 da mesma combinação."""
    linhas, quebra, final_vazio = dr.dividir(texto)
    res = {'linhas': 0, 'notas': 0}
    if not escolhas:
        return texto, res
    remover = set()
    for f, i, filhos in _docs(linhas):
        if len(f) < 10:
            continue
        did = _doc_id(f)
        mexeu = False
        for j in filhos:
            c = linhas[j].split('|')
            if c[1] != 'C190':
                continue
            novo = escolhas.get(f'{did}|{c[2].strip()}|{c[3].strip()}|{c[4].strip()}')
            if novo not in ('40', '41') or _n(c[7]) != 0:
                continue
            velho = c[2].strip()
            novo_cst = (velho[:-2] or '0') + novo
            for k in filhos:                     # itens (C170) da mesma combinação, sem ICMS
                g = linhas[k].split('|')
                if g[1] == 'C170' and len(g) > 15 and g[10].strip() == velho and g[11].strip() == c[3].strip() and _n(g[15]) == 0:
                    g[10] = novo_cst
                    g[13], g[14], g[15] = '0', '0', '0'      # isenta / não tributada: sem base, alíquota e ICMS
                    linhas[k] = '|'.join(g)
            c[2] = novo_cst
            c[4] = '0'
            linhas[j] = '|'.join(c)
            res['linhas'] += 1
            mexeu = True
        if mexeu:
            res['notas'] += 1
            # não pode repetir CST + CFOP + alíquota no C190 da nota: junta as repetidas
            vistos = {}
            for j in filhos:
                c = linhas[j].split('|')
                if c[1] != 'C190' or j in remover:
                    continue
                k = (c[2], c[3], f'{_n(c[4]):.2f}')
                if k in vistos:
                    alvo = linhas[vistos[k]].split('|')
                    for x in range(5, min(len(c), len(alvo)) - 1):
                        if x <= 11:
                            alvo[x] = f'{Decimal(str(_n(alvo[x]))) + Decimal(str(_n(c[x]))):.2f}'.replace('.', ',')
                    linhas[vistos[k]] = '|'.join(alvo)
                    remover.add(j)
                else:
                    vistos[k] = j
    if not res['linhas']:
        return texto, res
    return dr.monta_arquivo(linhas, remover, {}, [], [], [], quebra, final_vazio), res


def etapa(texto):
    g = analisar_texto(texto)
    tot = sum(len(v) for v in g.values())
    if not tot:
        return {'key': 'cstcf', 'titulo': 'CST × CFOP × ICMS', 'desc': 'nenhuma combinação de CST, CFOP e ICMS que não feche',
                'qtd': 'nada encontrado', 'valor': '', 'badge': 'sem correção', 'tipo': 'zero', 'grupos': []}
    grupos = []

    def lin(x, extra='', bloq=True):
        tipo = 'saída' if x['oper'] == '1' else 'entrada'
        nf = ('NFC-e ' if x['mod'] == '65' else 'NF-e ' if x['mod'] == '55' else f"mod {x['mod']} ") + (x['num'].lstrip('0') or '0')
        d = {'sel': x['id'], 'nota': nf, 'valor': x['vopr'], 'marcado': False,
             'det': f"{x['part'][:44]} · {tipo} · CFOP {x['cfop']} · CST {x['cst']} · base {_fm(x['bc'])} · ICMS {_fm(x['icms'])}{extra}",
             'busca': x['id']}
        if bloq:
            d['bloqueado'] = True
        return d
    if g['trib_sem_icms']:
        ls = []
        for x in g['trib_sem_icms']:
            d = lin(x, bloq=False)
            d['opcoes'] = [{'v': '40', 'rot': 'trocar para CST 40 (isenta)'}, {'v': '41', 'rot': 'trocar para CST 41 (não tributada)'}]
            d['padrao'] = '40'
            ls.append(d)
        grupos.append({'id': 'cstcf', 'titulo': 'Saída com CST tributado (x00/x20) sem base e sem ICMS', 'select': True,
                       'sugestao': 'se a operação é isenta ou não tributada, marque e escolha o CST; se é tributada, falta o débito (corrija na nota)',
                       'linhas': ls})
    for k, tit, sug in (('isento_com_icms', 'CST isento / não tributado / ST (x40, x41, x50, x60) com ICMS', 'verificar: ou o CST está errado, ou o ICMS não deveria estar ali'),
                        ('cfop_st_trib', 'CFOP de ST com CST tributado (x00/x20)', 'verificar: com ST o CST costuma ser x10, x30, x60 ou x70'),
                        ('venda_cst60', 'Venda x.101/x.102 com CST x60 (ST já retida)', 'verificar: com ST retida a venda sai em x.405')):
        if g[k]:
            grupos.append({'id': f'cstcf_{k}', 'titulo': tit, 'sugestao': sug, 'linhas': [lin(x) for x in g[k]]})
    v = sum(x['vopr'] for x in g['trib_sem_icms'])
    return {'key': 'cstcf', 'titulo': 'CST × CFOP × ICMS',
            'desc': 'Combinações de CST, CFOP e ICMS no C190 que não fecham. Em teste: só troca o CST do que você marcar; o resto é para conferir.',
            'qtd': f'{tot} linha(s)', 'valor': f'R$ {_fm(v)} sem ICMS' if v else '',
            'badge': 'decidir' if g['trib_sem_icms'] else 'verificar', 'tipo': 'decidir', 'grupos': grupos}

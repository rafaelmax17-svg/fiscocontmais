# -*- coding: utf-8 -*-
"""Notas emitidas pela própria empresa (NF-e/NFC-e) × SPED Fiscal × SEFAZ.

Toda nota emitida tem que estar na EFD, inclusive cancelada (COD_SIT 02), denegada (04) e numeração inutilizada (05)
— Guia Prático da EFD ICMS/IPI, registro C100 (exceções 1 e 2). Duas conferências:
  1) buracos na numeração de cada modelo/série emitida no mês (entre o menor e o maior número escriturado):
       • com o XML (anexado ao Corretor) e a situação na SEFAZ:
           autorizada → falta escriturar (informativo: a nota precisa entrar com itens e ICMS);
           cancelada / denegada → o Corretor inclui o C100 só com os campos da exceção (COD_SIT 02 / 04);
       • sem XML → verificar no emissor (pode ser inutilizada: COD_SIT 05, que precisa do número do protocolo).
  2) saída escriturada como regular e cancelada/denegada na SEFAZ → vira COD_SIT 02/04, sem filhos, e o débito
     (E110 campo 02) e os ajustes das notas (campos 03/07) saem da apuração.
"""
from decimal import Decimal

import difal_ro as dr
from cancel_entradas import SIT_REGULAR

C100_CAMPOS = 29         # REG .. VL_COFINS_ST


def _n(s):
    try:
        return float(str(s or '0').replace(',', '.'))
    except ValueError:
        return 0.0


def _fm(v):
    return f'{v:,.2f}'.replace(',', '§').replace('.', ',').replace('§', '.')


def _blocos_c100(linhas):
    out, cur = [], None
    for i, l in enumerate(linhas):
        reg = l[1:5] if l.startswith('|') else ''
        if reg == 'C100':
            cur = {'i': i, 'fim': i, 'f': l.split('|')}
            out.append(cur)
        elif cur and reg[:2] == 'C1' and reg[1:4].isdigit() and 100 < int(reg[1:4]) < 200:
            cur['fim'] = i
        else:
            cur = None
    return out


def _cnpj(linhas):
    for l in linhas:
        if l.startswith('|0000|'):
            return l.split('|')[7]
    return ''


def _emitidas(linhas):
    """notas emitidas pela empresa (IND_EMIT 0), modelo 55/65, por (modelo, série)."""
    por = {}
    for b in _blocos_c100(linhas):
        f = b['f']
        if len(f) < 10 or f[3] != '0' or f[5] not in ('55', '65') or not f[8].strip().isdigit():
            continue
        k = (f[5], int(f[7] or 0))
        por.setdefault(k, {'ser': f[7], 'nums': set()})['nums'].add(int(f[8]))
    return por


def _xml_da(xmls, cnpj, mod, ser, num):
    for ch, x in (xmls or {}).items():
        if ch[6:20] == cnpj and ch[20:22] == mod and int(ch[22:25]) == ser and int(ch[25:34]) == num:
            return ch, x
    return None, None


def chaves_para_consulta(texto, xmls):
    linhas, _, _ = dr.dividir(texto)
    cnpj = _cnpj(linhas)
    out = []
    for b in _blocos_c100(linhas):
        f = b['f']
        if len(f) > 9 and f[2] == '1' and f[3] == '0' and f[5] in ('55', '65') and f[6] in SIT_REGULAR and len(f[9].strip()) == 44:
            out.append(f[9].strip())
    for (mod, ser), d in _emitidas(linhas).items():
        for num in range(min(d['nums']), max(d['nums']) + 1):
            if num not in d['nums']:
                ch, _ = _xml_da(xmls, cnpj, mod, ser, num)
                if ch:
                    out.append(ch)
    return list(dict.fromkeys(out))


def analisar_texto(texto, situ, xmls):
    linhas, _, _ = dr.dividir(texto)
    cnpj = _cnpj(linhas)
    nomes = {}
    for l in linhas:
        if l.startswith('|0150|'):
            f = l.split('|')
            nomes[f[2]] = f[3]
    buracos, faixas = [], []
    for (mod, ser), d in sorted(_emitidas(linhas).items()):
        a, b = min(d['nums']), max(d['nums'])
        falt = [n for n in range(a, b + 1) if n not in d['nums']]
        faixas.append({'mod': mod, 'ser': d['ser'], 'de': a, 'ate': b, 'faltam': len(falt)})
        for num in falt:
            ch, x = _xml_da(xmls, cnpj, mod, ser, num)
            st = ((situ or {}).get(ch) or {}).get('situacao') if ch else None
            itens = (x or {}).get('itens') or []
            oper = '0' if itens and str(itens[0].get('cfop', ''))[:1] in '123' else '1'
            buracos.append({'id': ch or f'{mod}-{d["ser"]}-{num}', 'mod': mod, 'ser': d['ser'], 'num': num, 'chave': ch or '',
                            'situacao': st or ('sem_consulta' if ch else 'sem_xml'), 'oper': oper,
                            'valor': (x or {}).get('vnf', 0.0), 'icms': (x or {}).get('vicms', 0.0),
                            'motivo': ((situ or {}).get(ch) or {}).get('motivo', '') if ch else ''})
    canceladas = []
    for b in _blocos_c100(linhas):
        f = b['f']
        if len(f) < 23 or f[2] != '1' or f[3] != '0' or f[5] not in ('55', '65') or f[6] not in SIT_REGULAR:
            continue
        ch = f[9].strip()
        s = (situ or {}).get(ch) or {}
        if s.get('situacao') not in ('cancelada', 'denegada'):
            continue
        deb = c197c = c197d = 0.0
        for j in range(b['i'] + 1, b['fim'] + 1):
            g = linhas[j].split('|')
            if g[1] == 'C190' and len(g) > 7 and g[3][:1] in '567':
                deb += _n(g[7])
            elif g[1] == 'C197' and len(g) > 7:
                cod = g[2].strip()
                if len(cod) >= 4 and cod[3] in '0345678':
                    if cod[2] in '345':
                        c197d += _n(g[7])
                    elif cod[2] in '012':
                        c197c += _n(g[7])
        canceladas.append({'id': ch, 'chave': ch, 'mod': f[5], 'num': f[8], 'situacao': s['situacao'], 'quando': s.get('quando', ''),
                           'part': nomes.get(f[4], f[4]), 'valor': _n(f[12]), 'deb': round(deb, 2), 'c197c': round(c197c, 2), 'c197d': round(c197d, 2)})
    return {'faixas': faixas, 'buracos': buracos, 'canceladas': canceladas,
            'conferidas': sum(1 for b in _blocos_c100(linhas) if len(b['f']) > 9 and b['f'][2] == '1' and b['f'][3] == '0'
                              and ((situ or {}).get(b['f'][9].strip()) or {}).get('situacao') not in (None, 'erro'))}


def aplicar_texto(texto, situ, xmls, ids, e116=None):
    linhas, quebra, final_vazio = dr.dividir(texto)
    an = analisar_texto(texto, situ, xmls)
    ids = set(ids)
    res = {'incluidas': 0, 'canceladas': 0, 'debito': 0.0, 'avisos': [], 'e116': ''}
    remover, insercoes = set(), {}
    d02 = d03 = d07 = Decimal('0')
    blocos = {b['f'][9].strip(): b for b in _blocos_c100(linhas) if len(b['f']) > 9}
    for c in an['canceladas']:
        if c['id'] not in ids or c['chave'] not in blocos:
            continue
        b = blocos[c['chave']]
        f = b['f']
        novo = [''] * len(f)
        for k in (1, 2, 3, 5, 7, 8, 9):
            novo[k] = f[k]
        novo[6] = '04' if c['situacao'] == 'denegada' else '02'
        linhas[b['i']] = '|'.join(novo)
        remover.update(range(b['i'] + 1, b['fim'] + 1))
        d02 -= Decimal(str(c['deb']))
        d03 -= Decimal(str(c['c197d']))
        d07 -= Decimal(str(c['c197c']))
        res['canceladas'] += 1
        res['debito'] += c['deb']
    # notas canceladas/denegadas que faltavam: entram depois do último C100 (com os filhos)
    novas = []
    for x in an['buracos']:
        if x['id'] in ids and x['situacao'] in ('cancelada', 'denegada') and x['chave']:
            campos = [''] * (C100_CAMPOS + 2)
            campos[1], campos[2], campos[3], campos[5] = 'C100', x['oper'], '0', x['mod']
            campos[6] = '04' if x['situacao'] == 'denegada' else '02'
            campos[7], campos[8], campos[9] = x['ser'], str(x['num']), x['chave']
            novas.append('|'.join(campos))
            res['incluidas'] += 1
    if novas:
        bl = _blocos_c100(linhas)
        if not bl:
            res['erro'] = 'O SPED não tem C100 para servir de posição às notas que faltam.'
            return texto, res
        insercoes[bl[-1]['fim']] = novas
    if not (res['incluidas'] or res['canceladas']):
        return texto, res
    deltas = {k: float(v) for k, v in ((2, d02), (3, d03), (7, d07)) if abs(v) >= Decimal('0.005')}
    e110, cab = None, {}
    for i, l in enumerate(linhas):
        if l.startswith('|0000|'):
            cab['dt_ini'] = l.split('|')[4]
        elif l.startswith('|E110|'):
            e110 = {'i': i}
    novas_e116, erro = dr.aplica_apuracao(linhas, e110, deltas, {'e116': e116 or {}}, cab, remover, res)
    if erro:
        res['erro'] = erro
        return texto, res
    res['debito'] = round(res['debito'], 2)
    return dr.monta_arquivo(linhas, remover, insercoes, [], [], novas_e116, quebra, final_vazio), res


def etapa(texto, situ, xmls):
    a = analisar_texto(texto, situ, xmls)
    if not a['faixas']:
        return {'key': 'saisef', 'titulo': 'Saídas × SEFAZ (notas emitidas)', 'desc': 'nenhuma NF-e/NFC-e emitida pela empresa no arquivo',
                'qtd': 'nada encontrado', 'valor': '', 'badge': 'sem correção', 'tipo': 'zero', 'grupos': []}
    grupos = []
    rot = {'55': 'NF-e', '65': 'NFC-e'}
    if a['buracos']:
        ls = []
        for x in a['buracos']:
            nf = f"{rot.get(x['mod'], x['mod'])} {x['num']}"
            if x['situacao'] in ('cancelada', 'denegada'):
                ls.append({'sel': x['id'], 'nota': nf, 'valor': x['valor'], 'marcado': True,
                           'det': f"não está no SPED · {x['situacao'].upper()} na SEFAZ → entra só como COD_SIT {'04' if x['situacao'] == 'denegada' else '02'}",
                           'busca': x['chave']})
                continue
            det = {'autorizada': f"não está no SPED · AUTORIZADA na SEFAZ (R$ {_fm(x['valor'])}, ICMS R$ {_fm(x['icms'])}) → falta escriturar a nota",
                   'sem_consulta': 'não está no SPED · XML encontrado, ainda não conferido: clique em "Conferir saídas na SEFAZ"',
                   'nao_encontrada': 'não está no SPED · XML encontrado, mas a SEFAZ não conhece a chave (verificar)',
                   'sem_xml': 'não está no SPED e não há XML anexado → verificar no emissor (se foi inutilizada: COD_SIT 05)',
                   'erro': 'não está no SPED · a SEFAZ não respondeu (confira de novo)'}.get(x['situacao'], 'não está no SPED')
            ls.append({'sel': x['id'], 'nota': nf, 'valor': x['valor'] or 0.0, 'marcado': False, 'bloqueado': True, 'det': det, 'busca': x['chave']})
        fx = ' · '.join(f"{rot.get(f['mod'], f['mod'])} série {f['ser']} ({f['de']} a {f['ate']}): {f['faltam']}" for f in a['faixas'] if f['faltam'])
        grupos.append({'id': 'saisef', 'titulo': f'Números faltando na sequência · {fx}', 'sugestao': 'incluir as canceladas/denegadas; as demais, conferir',
                       'linhas': ls})
    if a['canceladas']:
        ls = []
        for c in a['canceladas']:
            q = (c['quando'] or '')[:10]
            q = f' em {q[8:10]}/{q[5:7]}/{q[:4]}' if len(q) == 10 else ''
            ls.append({'sel': c['id'], 'nota': f"{rot.get(c['mod'], c['mod'])} {c['num'].lstrip('0')}", 'valor': c['valor'], 'marcado': True,
                       'det': f"{c['part'][:44]} · {c['situacao'].upper()} na SEFAZ{q} · vira COD_SIT {'04' if c['situacao'] == 'denegada' else '02'}"
                              + (f" · débito de R$ {_fm(c['deb'])} sai da apuração" if c['deb'] else ''), 'busca': c['chave']})
        grupos.append({'id': 'saisefc', 'titulo': 'Escrituradas como regulares, mas canceladas/denegadas na SEFAZ', 'sugestao': 'marcar como canceladas', 'linhas': ls})
    falt = sum(f['faltam'] for f in a['faixas'])
    deb = sum(c['deb'] for c in a['canceladas'])
    auto = any(not l.get('bloqueado') for g in grupos for l in g['linhas'])
    desc = (f"{falt} número(s) faltando na sequência das notas emitidas"
            + (f" · {a['conferidas']} saída(s) conferida(s) na SEFAZ" if a['conferidas'] else ' · saídas ainda não conferidas na SEFAZ (botão "Conferir saídas na SEFAZ")')
            + '. Nota cancelada, denegada ou inutilizada também tem que estar no SPED.')
    return {'key': 'saisef', 'titulo': 'Saídas × SEFAZ (notas emitidas)', 'desc': desc,
            'qtd': f"{falt} faltando · {len(a['canceladas'])} cancelada(s) como regular",
            'valor': f'− R$ {_fm(deb)} débito' if deb else '',
            'badge': 'pode corrigir' if auto else ('verificar' if grupos else 'sem correção'),
            'tipo': 'auto' if auto else ('decidir' if grupos else 'zero'), 'grupos': grupos}

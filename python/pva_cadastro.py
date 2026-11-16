# -*- coding: utf-8 -*-
"""Corretor do SPED Fiscal — Validação do PVA · cadastro e ajustes (EM TESTE).

Quatro erros do validador (PVA) que a Validação do PVA ainda não corrigia, achados no SPED real do Auto Posto Patrão
(10/2026, 30 erros):

1) "Não podem ser informados GTINs iguais para fatores de conversão de produtos" — o fator de conversão (0220, campo 04
   COD_BARRA) repete o código de barras do próprio produto (0200, campo 04), ou outro 0220 do mesmo produto. O Domínio
   grava o 0220 da unidade "UNIDADE" (fator 1) com o mesmo GTIN da unidade do 0200: é a mesma embalagem, não existe
   outro código. Correção: o código de barras do 0220 fica vazio (o campo é preenchido só "se houver"); o GTIN do 0200,
   que está certo, não muda — ele é obrigatório quando algum 0220 tem código de barras.
2) "Não informar item, se não referenciado em pelo menos um dos demais blocos" — produto do 0200 sem uso em nenhum
   registro do arquivo. Correção: sai o 0200 com os registros filhos (0205, 0206, 0210, 0220, 0221). A unidade (0190)
   que só ele usava sai junto (senão o PVA acusa unidade sem uso).
3) "O valor informado deve existir na Tabela de Código Especificador da Substituição Tributária - CEST" — CEST do 0200
   que não existe (ou não vale no período) na tabela COD_CEST do próprio PVA (cest_tabela.py, baixada do serviço oficial
   de tabelas do SPED). Correção: o CEST do NCM; com mais de um possível, decide pela descrição só na água mineral
   (Convênio ICMS 142/2018, Anexo IV: 03.002.00 embalagem de 5 litros ou mais; 03.024.00 retornável de 10 a menos de 20
   litros; 03.025.00 retornável de 20 litros ou mais); nos demais casos o campo fica vazio. O NCM de cada CEST vem das
   listas do RICMS/RO (Anexo VI) e da Lei 6.108/2022 do AM já no sistema (texto oficial).
4) "Se preenchido este registro, pelo menos um dos campos: VL_BC_ICMS, ALIQ_ICMS, VL_ICMS, VL_OUTROS deve ser maior que
   ZERO" — ajuste C197 todo zerado. Correção: sai o C197; o C195 que ficar sem ajuste sai junto, e a observação (0460)
   que ficar sem uso também. Exceção: DIFAL (RO40000001/2) zerado em compra de OUTRO estado não é retirado — o DIFAL
   pode ser devido e deve ser calculado na conferência "Uso e consumo · DIFAL e crédito"; em compra dentro do estado não
   há DIFAL, e o ajuste zerado sai.

Gera arquivo NOVO; o original nunca é alterado. Base: Guia Prático da EFD ICMS/IPI (registros 0190, 0200, 0220, 0460,
C195 e C197) e as mensagens do próprio PVA.
"""
import re
from collections import defaultdict

FILHOS_0200 = ('0205', '0206', '0210', '0220', '0221')
# onde cada registro guarda o código do item (posição no split por '|', com o '' inicial)
POS_ITEM = {'C170': [3], 'C180': [], 'C185': [4], 'C186': [3], 'C181': [4], 'C321': [2], 'C330': [3], 'C380': [3],
            'C425': [2], 'C470': [2], 'C495': [2], 'C610': [3], 'C810': [3], 'C870': [3], 'C880': [3], 'D': [],
            'G140': [3], 'H010': [2], 'H030': [], 'K200': [3], 'K210': [4], 'K215': [2], 'K220': [3, 4], 'K230': [4],
            'K235': [3, 5], 'K250': [3], 'K255': [3, 5], 'K260': [3], 'K265': [2], 'K270': [4], 'K275': [2], 'K280': [3],
            'K291': [2], 'K292': [2], 'K301': [2], 'K302': [2], '1105': [3], '1300': [2], '1391': [3], '0210': [2]}
# onde cada registro guarda a unidade (0190)
POS_UNID = {'0200': [6], '0220': [2], 'C170': [6], 'C321': [4], 'C425': [4], 'C470': [5], 'C495': [6], 'H010': [3],
            'C181': [6], 'C185': [6], 'C330': [5], 'C380': [5], 'C810': [5], 'C870': [5], 'C880': [5], 'G140': [5],
            '1105': [6]}
COD_DIFAL = {'RO40000001', 'RO40000002'}
TIPO_TXT = {'gtin': 'GTIN repetido no fator de conversão', 'semuso': 'Produto sem uso no mês',
            'cest': 'CEST inexistente na tabela', 'c197': 'Ajuste C197 zerado'}


def _n(s):
    try:
        return float((s or '').replace('.', '').replace(',', '.')) if (s or '').strip() else 0.0
    except ValueError:
        return 0.0


def _linhas(texto):
    quebra = '\r\n' if '\r\n' in texto else '\n'
    final_vazio = texto.endswith(quebra)
    linhas = texto.split(quebra)
    if final_vazio:
        linhas.pop()
    return linhas, quebra, final_vazio


def _cest_tabela():
    """{CEST sem pontos: [NCMs/prefixos]} — listas oficiais já no sistema (RO e AM)."""
    tab = defaultdict(set)
    try:
        import st_ro_dados as ro
        for v in (getattr(ro, n) for n in dir(ro)):
            if isinstance(v, dict) and len(v) > 100:
                for k, x in v.items():
                    if isinstance(x, dict) and re.fullmatch(r'\d\d\.\d{3}\.\d\d', str(k)):
                        tab[k.replace('.', '')].update(x.get('ncm') or [])
    except Exception:
        pass
    try:
        import st_am_dados as am
        for k, x in am.LEI_6108_ST.items():
            tab[k.replace('.', '')].update(x[2] or [])
    except Exception:
        pass
    return tab


_TAB = None


def _tab():
    global _TAB
    if _TAB is None:
        _TAB = _cest_tabela()
    return _TAB


def _volume_litros(desc):
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*(ML|L|LT|LTS|LITROS?)\b', (desc or '').upper())
    if not m:
        return None
    v = float(m.group(1).replace(',', '.'))
    return v / 1000 if m.group(2) == 'ML' else v


def _vale(cest, dt):
    """CEST existe na tabela do PVA e vale na data (ddmmaaaa) do período?"""
    import cest_tabela as ct
    x = ct.CEST.get(cest)
    if not x:
        return False
    if len(dt or '') != 8:
        return True
    d = dt[4:] + dt[2:4] + dt[:2]
    return any(i[4:] + i[2:4] + i[:2] <= d and (not f or d <= f[4:] + f[2:4] + f[:2]) for i, f in x[1])


def _cest_certo(ncm, desc, dt=''):
    """(CEST novo ou '', motivo) para um 0200 cujo CEST não existe na tabela."""
    tab = _tab()
    cands = sorted(c for c, ncms in tab.items() if any(ncm.startswith(p) for p in ncms if p) and _vale(c, dt))
    if not cands:
        return None, ''
    if len(cands) == 1:
        return cands[0], 'único CEST do NCM na tabela'
    if ncm.startswith('22011000') or ncm.startswith('220110'):
        v = _volume_litros(desc)
        if v is not None and v >= 20 and _vale('0302500', dt):
            return '0302500', f'água mineral em embalagem retornável de 20 litros ou mais ({v:g} L na descrição) — Conv. ICMS 142/2018, Anexo IV, CEST 03.025.00'
        if v is not None and 10 <= v < 20 and _vale('0302400', dt):
            return '0302400', f'água mineral em embalagem retornável de 10 a menos de 20 litros ({v:g} L) — CEST 03.024.00'
        if v is not None and 5 <= v < 10 and _vale('0300200', dt):
            return '0300200', f'água mineral em embalagem de 5 litros ou mais ({v:g} L) — CEST 03.002.00'
    return '', f'o NCM tem {len(cands)} CEST possíveis e a descrição não define qual: o campo fica vazio (aceito no cadastro)'


def _fmt_cest(c):
    return f'{c[:2]}.{c[2:5]}.{c[5:]}' if c and len(c) == 7 else (c or '')


def analisar_texto(texto, xmls=None):
    linhas, _, _ = _linhas(texto)
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), len(linhas) - 1)
    linhas = linhas[:fim + 1]
    reg = [l.split('|') for l in linhas]
    uf_emp = dt_ini = ''
    for c in reg:
        if len(c) > 9 and c[1] == '0000':
            uf_emp, dt_ini = c[9], c[4]
            break
    # ---- itens usados fora do cadastro
    usados = set()
    for c in reg:
        if len(c) < 3:
            continue
        r = c[1]
        for p in POS_ITEM.get(r, []):
            if len(c) > p and c[p]:
                usados.add(c[p])
    itens = []
    # ---- 0200 e filhos
    i = 0
    while i < len(reg):
        c = reg[i]
        if len(c) > 2 and c[1] == '0200':
            cod, desc = c[2], c[3] if len(c) > 3 else ''
            gtin = c[4] if len(c) > 4 else ''
            j = i + 1
            vistos = {}
            while j < len(reg) and len(reg[j]) > 1 and reg[j][1] in FILHOS_0200:
                f = reg[j]
                if f[1] == '0220' and len(f) > 5 and f[4]:
                    if gtin and f[4] == gtin:
                        itens.append({'id': f'gtin:{cod}:{f[2]}', 'tipo': 'gtin', 'cod': cod, 'desc': desc,
                                      'det': f'fator de conversão da unidade {f[2]} (fator {f[3]}) com o mesmo código de barras do produto {gtin}',
                                      'de': f[4], 'para': '', 'motivo': 'o código de barras do fator de conversão fica vazio; o GTIN do produto continua no cadastro'})
                    elif f[4] in vistos:
                        itens.append({'id': f'gtin:{cod}:{f[2]}', 'tipo': 'gtin', 'cod': cod, 'desc': desc,
                                      'det': f'fator de conversão da unidade {f[2]} repete o código de barras da unidade {vistos[f[4]]} ({f[4]})',
                                      'de': f[4], 'para': '', 'motivo': 'o código de barras repetido fica vazio'})
                    vistos.setdefault(f[4], f[2])
                j += 1
            if cod not in usados:
                itens.append({'id': f'semuso:{cod}', 'tipo': 'semuso', 'cod': cod, 'desc': desc,
                              'det': 'não aparece em nenhuma nota, cupom, inventário, produção ou movimentação de combustível do mês',
                              'de': '', 'para': '', 'motivo': f'sai do cadastro com os registros filhos ({j - i - 1})' if j - i - 1 else 'sai do cadastro'})
            cest = c[13] if len(c) > 13 else ''
            ncm = c[8] if len(c) > 8 else ''
            if cest and not _vale(cest, dt_ini):
                novo, mot = _cest_certo(ncm, desc, dt_ini) if ncm else (None, '')
                if novo is None:
                    novo, mot = '', 'nenhum CEST da tabela corresponde ao NCM: o campo fica vazio (aceito no cadastro)'
                import cest_tabela as ct
                nao = 'não existe na tabela do PVA' if cest not in ct.CEST else 'não vale no período (revogado)'
                itens.append({'id': f'cest:{cod}', 'tipo': 'cest', 'cod': cod, 'desc': desc,
                              'det': f'CEST {cest} {nao} (NCM {ncm})', 'de': cest, 'para': novo,
                              'motivo': (f'CEST {_fmt_cest(novo)}: ' if novo else '') + mot})
            i = j
            continue
        i += 1
    # ---- C197 zerado
    doc, cfops = None, set()
    for k, c in enumerate(reg):
        if len(c) < 2:
            continue
        if c[1] == 'C100':
            doc, cfops = c, set()
        elif c[1] == 'C170' and len(c) > 11:
            cfops.add(c[11])
        elif c[1] == 'C197' and len(c) > 8 and all(_n(x) == 0 for x in c[5:9]):
            num = doc[8] if doc and len(doc) > 8 else ''
            chave = doc[9] if doc and len(doc) > 9 else ''
            uf_nota = {'11': 'RO', '12': 'AC', '13': 'AM', '14': 'RR', '15': 'PA', '16': 'AP', '17': 'TO', '21': 'MA', '22': 'PI',
                       '23': 'CE', '24': 'RN', '25': 'PB', '26': 'PE', '27': 'AL', '28': 'SE', '29': 'BA', '31': 'MG', '32': 'ES',
                       '33': 'RJ', '35': 'SP', '41': 'PR', '42': 'SC', '43': 'RS', '50': 'MS', '51': 'MT', '52': 'GO',
                       '53': 'DF'}.get(chave[:2], '')
            interna = (uf_nota and uf_emp and uf_nota == uf_emp) or (cfops and all(cf[:1] in '15' for cf in cfops))
            bloq = c[2] in COD_DIFAL and not interna
            ref = re.sub(r'\D', '', chave) or f"{num}|{doc[7] if doc and len(doc) > 7 else ''}|{doc[4] if doc and len(doc) > 4 else ''}"
            n_aj = sum(1 for x in itens if x['tipo'] == 'c197' and x['id'].startswith(f'c197:{ref}:{c[2]}:'))
            itens.append({'id': f'c197:{ref}:{c[2]}:{n_aj}', '_linha': k, 'tipo': 'c197', 'cod': c[2], 'desc': (c[3] if len(c) > 3 else '')[:90],
                          'det': f"NF-e {num.lstrip('0')}" + (f" · fornecedor de {uf_nota}" if uf_nota else ''),
                          'de': 'todos os valores zerados', 'para': '', 'bloqueado': bool(bloq),
                          'motivo': ('DIFAL zerado em compra de outro estado: calcule na conferência "Uso e consumo · DIFAL e crédito" (não é retirado aqui)'
                                     if bloq else ('compra dentro do estado não tem DIFAL: o ajuste zerado sai' if c[2] in COD_DIFAL
                                                   else 'ajuste sem valor: sai') + '; o C195 e a observação (0460) sem uso saem junto')})
    ordem = {'gtin': 0, 'semuso': 1, 'cest': 2, 'c197': 3}
    itens.sort(key=lambda x: (ordem[x['tipo']], x['cod']))
    resumo = {t: sum(1 for x in itens if x['tipo'] == t) for t in TIPO_TXT}
    return {'itens': itens, 'resumo': resumo, 'tipos': TIPO_TXT}


def aplicar_texto(texto, ids, xmls=None):
    import fiscal_core as fc
    linhas, quebra, final_vazio = _linhas(texto)
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), None)
    assinado = fim is not None and fim < len(linhas) - 1
    if assinado:
        linhas = linhas[:fim + 1]
        final_vazio = True
    an = analisar_texto(quebra.join(linhas))
    sel = {i['id']: i for i in an['itens'] if i['id'] in set(ids or []) and not i.get('bloqueado')}
    res = {t: 0 for t in TIPO_TXT}
    res['unidades_removidas'], res['obs_removidas'] = [], []
    remover = set()
    reg = [l.split('|') for l in linhas]
    unid_tiradas = set()
    # 0200 / 0220
    i = 0
    while i < len(reg):
        c = reg[i]
        if len(c) > 2 and c[1] == '0200':
            cod = c[2]
            j = i + 1
            while j < len(reg) and len(reg[j]) > 1 and reg[j][1] in FILHOS_0200:
                j += 1
            if f'semuso:{cod}' in sel:
                remover.update(range(i, j))
                for x in range(i, j):
                    for p in POS_UNID.get(reg[x][1], []):
                        if len(reg[x]) > p and reg[x][p]:
                            unid_tiradas.add(reg[x][p])
                res['semuso'] += 1
            else:
                for x in range(i + 1, j):
                    f = reg[x]
                    if f[1] == '0220' and f'gtin:{cod}:{f[2]}' in sel and len(f) > 5 and f[4]:
                        f[4] = ''
                        linhas[x] = '|'.join(f)
                        res['gtin'] += 1
                it = sel.get(f'cest:{cod}')
                if it and len(c) > 13 and c[13] == it['de']:
                    c[13] = it['para']
                    linhas[i] = '|'.join(c)
                    res['cest'] += 1
            i = j
            continue
        i += 1
    # C197 zerados (+ C195 sem filho)
    obs_tiradas = set()
    for k in sorted(it['_linha'] for x, it in sel.items() if x.startswith('c197:')):
        remover.add(k)
        res['c197'] += 1
        p = k - 1
        while p >= 0 and reg[p][1] == 'C197':
            p -= 1
        if p >= 0 and reg[p][1] == 'C195':
            q = p + 1
            filhos = []
            while q < len(reg) and reg[q][1] == 'C197':
                filhos.append(q)
                q += 1
            if all(f in remover for f in filhos):
                remover.add(p)
                obs_tiradas.add(reg[p][2])
    novas = [l for x, l in enumerate(linhas) if x not in remover]
    # unidade (0190) e observação (0460) que ficaram sem uso
    reg2 = [l.split('|') for l in novas]
    unid_usadas = {c[p] for c in reg2 if len(c) > 1 for p in POS_UNID.get(c[1], []) if len(c) > p}
    obs_usadas = {c[2] for c in reg2 if len(c) > 2 and c[1] in ('C195', 'D195')}
    fora = set()
    for x, c in enumerate(reg2):
        if len(c) > 2 and c[1] == '0190' and c[2] in unid_tiradas and c[2] not in unid_usadas:
            fora.add(x)
            res['unidades_removidas'].append(f'{c[2]} – {c[3] if len(c) > 3 else ""}')
        if len(c) > 2 and c[1] == '0460' and c[2] in obs_tiradas and c[2] not in obs_usadas:
            fora.add(x)
            res['obs_removidas'].append(c[2])
    novas = [l for x, l in enumerate(novas) if x not in fora]
    if remover or fora:
        novas = fc._recalcula_bloco9_global(novas)
        novas = fc._recalcula_fechamentos_bloco(novas)
    avisos = []
    if res['gtin']:
        avisos.append('O fator de conversão com o mesmo código de barras do produto vem do cadastro do Domínio: ajuste lá para o erro não voltar no próximo SPED.')
    if assinado:
        avisos.insert(0, 'O arquivo estava assinado no PVA: a assinatura foi retirada (ela deixa de valer com a alteração). Valide e assine de novo no PVA.')
    res['avisos'] = avisos
    return quebra.join(novas) + (quebra if final_vazio else ''), res


def main_cli(argv):
    import json
    import fiscal_core as fc

    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    texto, enc = fc._ler_sped(opt('--sped'))
    an = analisar_texto(texto)
    if opt('--saida'):
        novo, res = aplicar_texto(texto, [i['id'] for i in an['itens']])
        fc._grava_sped(opt('--saida'), novo, enc)
        an['aplicado'] = res
    with open(opt('--json'), 'w', encoding='utf-8') as fh:
        json.dump(an, fh, ensure_ascii=False, indent=1)
    return 0

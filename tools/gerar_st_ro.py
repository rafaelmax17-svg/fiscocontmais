# -*- coding: utf-8 -*-
"""Gera python/st_ro_dados.py a partir do texto do RICMS/RO, Anexo VI, Parte 2 (Produtos sujeitos à ST).

Uso:  pdftotext -layout ANEXO-VI---ST---Consolid.-ate-Dec.-31963-26.pdf anexo6.txt
      python tools/gerar_st_ro.py anexo6.txt "Dec. 31.963/26"

Regras (pedido do Rafael: sempre descartar o que está revogado e as redações anteriores):
  • só a Parte 2 (entre "PARTE 2" e "PARTE 3");
  • cada TABELA vale só na versão atual: os blocos "Redação anterior / Redação original: TABELA ..." são ignorados;
  • tabela inteira "REVOGADA" (ex.: XX eletrônicos, XXI rações) fica fora;
  • item cuja célula começa com "REVOGADO PELO DEC. ..." vai para REVOGADOS (com a data de efeitos), não para a lista vigente;
  • quando o mesmo CEST aparece duas vezes (redação atual + anterior na mesma linha da tabela), vale a primeira e o item
    é marcado como DUPLICADO para conferência da MVA.
"""
import re
import sys
import json


def gerar(texto, versao):
    T = texto.split('\n')
    ini = next(i for i, l in enumerate(T) if l.strip() == 'PARTE 2')
    fim = next(i for i, l in enumerate(T) if i > ini and l.strip() == 'PARTE 3')
    T = T[ini:fim]
    H = []
    for i, l in enumerate(T):
        m = re.match(r'^\s*(?:Reda\S+\s+(?:anterior|original)\s*:?\s*)?TABELA\s+([IVXL]+)\s*$', l, re.I)
        if m:
            velha = any(re.search(r'Reda\S+\s+(anterior|original)', T[k], re.I) for k in range(max(0, i - 3), i + 1))
            nome = next((T[k].strip() for k in range(i + 1, min(i + 4, len(T))) if T[k].strip()), '')
            H.append((i, m.group(1), velha, nome))
    CEST = re.compile(r'(?<![\d.])(\d{2}\.\d{3}\.\d{2})(?![\d.])')
    NCM = re.compile(r'(?<![\d.,%/º])(\d{4}(?:\.\d{1,2}){0,2}|\d{2}\.\d{2})(?![\d,%/º]|\.\d)')
    SKIP = re.compile(r'\b(Dec|DEC|Conv|CONV|Prot|PROT)\.|\bDecreto\b|\bLei\b|\bLEI\b|\b[Ee]feitos\b|\bEFEITOS\b|D\.O\.E')
    vig, rev, dup = {}, [], set()
    tabelas = {}
    for k, (a, tab, velha, nome) in enumerate(H):
        b = H[k + 1][0] if k + 1 < len(H) else len(T)
        if velha or tab == 'I':
            continue
        L = T[a:b]
        tab_revogada = any('REVOGADA' in x.upper() for x in L[:6])
        tabelas[tab] = {'nome': nome.capitalize() if nome.isupper() else nome, 'revogada': tab_revogada}
        anc = [(j, m.group(1)) for j, x in enumerate(L) for m in CEST.finditer(x)]
        for q, (j, c) in enumerate(anc):
            lo = (anc[q - 1][0] + j) // 2 + 1 if q else 0
            hi = (j + anc[q + 1][0]) // 2 if q + 1 < len(anc) else len(L) - 1
            if q + 1 < len(anc) and anc[q + 1][0] == j:
                hi = j
            if q and anc[q - 1][0] == j:
                lo = j
            ncms = []
            for x in L[lo:hi + 1]:
                if SKIP.search(x):
                    continue
                for m in NCM.finditer(CEST.sub(' ', x)):
                    v = m.group(1).replace('.', '')
                    if 4 <= len(v) <= 8:
                        ncms.append(v)
            ini_cel = anc[q - 1][0] + 1 if q else 0
            if q and anc[q - 1][0] == j:
                ini_cel = j
            cel = ' '.join(L[ini_cel:j + 1]).upper()
            revogado = tab_revogada or 'REVOGAD' in cel
            mva = re.findall(r'(\d{1,3}(?:,\d{1,2})?)\s*%', L[j])
            item = {'cest': c, 'tab': tab, 'ncm': sorted(set(ncms)), 'mva': mva[0] if mva else ''}
            if revogado:
                mm = re.findall(r'EFEITOS\s+A\s+PARTIR\s+D[EO]\s+([0-9º./]+)', cel)
                item['revogado_em'] = mm[-1].rstrip('.') if mm else ''
                rev.append(item)
            elif c in vig:
                dup.add(c)
            else:
                vig[c] = item
    rev = [r for r in rev if r['cest'] not in vig]
    return {'versao': versao, 'tabelas': tabelas, 'vigentes': vig, 'revogados': rev, 'duplicados': sorted(dup)}


if __name__ == '__main__':
    d = gerar(open(sys.argv[1], encoding='utf-8').read(), sys.argv[2] if len(sys.argv) > 2 else '')
    out = ('# -*- coding: utf-8 -*-\n# GERADO por tools/gerar_st_ro.py — não editar à mão.\n'
           f'# Fonte: RICMS/RO (Dec. 22.721/2018), Anexo VI, Parte 2 — texto consolidado até o {d["versao"]}.\n'
           '# Revogados e redações anteriores ficam fora de VIGENTES. Tabela XXVI = só venda porta a porta.\n'
           f'VERSAO = {d["versao"]!r}\nTABELAS = {json.dumps(d["tabelas"], ensure_ascii=False)}\n'
           f'VIGENTES = {json.dumps(d["vigentes"], ensure_ascii=False, indent=0)}\n'
           f'REVOGADOS = {json.dumps(d["revogados"], ensure_ascii=False, indent=0)}\n'
           f'DUPLICADOS = {json.dumps(d["duplicados"])}\n').replace(': true', ': True').replace(': false', ': False')
    open('python/st_ro_dados.py', 'w', encoding='utf-8').write(out)
    print(len(d['vigentes']), 'vigentes ·', len(d['revogados']), 'revogados ·', len(d['duplicados']), 'duplicados ·',
          sum(1 for v in d['vigentes'].values() if not v['ncm']), 'sem NCM')

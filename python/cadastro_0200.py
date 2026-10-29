# -*- coding: utf-8 -*-
"""Corretor do SPED Fiscal (Admin) — Cadastro de produtos (0200): tipo do item × uso nas entradas.

Produto cadastrado como mercadoria para revenda (0200, campo 07 TIPO_ITEM = 00) que, no período, só entrou como uso e
consumo ou ativo (CFOP final 556, 407, 653 → 07; 551, 406 → 08) recebe a sugestão do tipo certo. Só os produtos marcados
na tela mudam. Gera arquivo NOVO; o original nunca é alterado.

Proteção: produto que também aparece em saída (C170 de saída, C321, C425, C470), no inventário (H010), no controle da
produção e do estoque (K200) ou em entrada para revenda/industrialização fica "Não alterar" — o mesmo código serve para
mais de um uso e o tipo depende da atividade principal.

Base: Guia Prático da EFD ICMS/IPI, registro 0200, campo 07 (TIPO_ITEM: 00 mercadoria para revenda, 07 material de uso e
consumo, 08 ativo imobilizado). Como nenhuma linha é criada ou apagada, as contagens do bloco 9 não mudam.
"""
import os
import json
from collections import defaultdict, Counter

TIPOS = {'00': 'Mercadoria para revenda', '01': 'Matéria-prima', '02': 'Embalagem', '03': 'Produto em processo',
         '04': 'Produto acabado', '05': 'Subproduto', '06': 'Produto intermediário', '07': 'Material de uso e consumo',
         '08': 'Ativo imobilizado', '09': 'Serviços', '10': 'Outros insumos', '99': 'Outras'}
FIM_USO = {'556', '407', '653'}
FIM_ATIVO = {'551', '406'}
CANC = {'02', '03', '04', '05'}


def _n(s):
    s = (s or '').strip()
    try:
        return float(s.replace(',', '.')) if s else 0.0
    except ValueError:
        return 0.0


def _corte(linhas):
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), None)
    return linhas[:fim + 1] if fim is not None else linhas


def _levantar(linhas):
    p0200 = {}
    entradas = defaultdict(Counter)
    valor = defaultdict(float)
    outros = defaultdict(set)
    c100 = None
    for i, l in enumerate(linhas):
        c = l.split('|')
        if len(c) < 3:
            continue
        r = c[1]
        if r == '0200':
            p0200[c[2]] = {'i': i, 'desc': c[3], 'tipo': c[7] if len(c) > 7 else '', 'ncm': c[8] if len(c) > 8 else ''}
        elif r == 'C100':
            c100 = c if (len(c) > 6 and c[6] not in CANC) else None
        elif r == 'C170' and c100 is not None and len(c) > 11:
            if c100[2] == '0':
                entradas[c[3]][c[11]] += 1
                valor[c[3]] += _n(c[7]) - _n(c[8])
            else:
                outros[c[3]].add('saída (C170)')
        elif r in ('C321', 'C425', 'C470') and len(c) > 2:
            outros[c[2]].add(f'saída ({r})')
        elif r == 'H010' and len(c) > 2:
            outros[c[2]].add('inventário (H010)')
        elif r == 'K200' and len(c) > 3:
            outros[c[3]].add('estoque (K200)')
    return p0200, entradas, valor, outros


def analisar_texto(texto):
    linhas = _corte(texto.replace('\r\n', '\n').split('\n'))
    p0200, entradas, valor, outros = _levantar(linhas)
    itens = []
    for cod, p in p0200.items():
        if p['tipo'] != '00' or cod not in entradas:
            continue
        cfops = entradas[cod]
        fins = {cf[1:] for cf in cfops}
        if not fins & (FIM_USO | FIM_ATIVO):
            continue
        motivos = sorted(outros.get(cod, set()))
        outros_fins = fins - FIM_USO - FIM_ATIVO
        if outros_fins:
            motivos.append('também entra como ' + ', '.join(sorted(c for c in cfops if c[1:] in outros_fins)))
        sug = '08' if fins & FIM_ATIVO and not fins & FIM_USO else '07'
        if fins & FIM_ATIVO and fins & FIM_USO:
            motivos.append('entra como uso e consumo e como ativo')
        itens.append({'cod': cod, 'desc': p['desc'], 'ncm': p['ncm'], 'tipo': p['tipo'], 'sugestao': sug,
                      'cfops': [[k, v] for k, v in sorted(cfops.items())], 'valor': round(valor[cod], 2),
                      'pode': not motivos, 'motivos': motivos})
    itens.sort(key=lambda x: (not x['pode'], -x['valor']))
    return {'itens': itens, 'tipos': TIPOS,
            'resumo': {'encontrados': len(itens), 'podem': sum(1 for x in itens if x['pode']),
                       'nao_alterar': sum(1 for x in itens if not x['pode'])}}


def aplicar_texto(texto, selecao):
    """selecao = {'itens': {COD_ITEM: '07' | '08' | ...}} -> (texto_novo, resumo)."""
    quebra = '\r\n' if '\r\n' in texto else '\n'
    final_vazio = texto.endswith(quebra)
    linhas = texto.split(quebra)
    if final_vazio:
        linhas.pop()
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), None)
    assinado = fim is not None and fim < len(linhas) - 1
    if assinado:          # assinatura do PVA vem depois do |9999| e deixa de valer com a alteração
        linhas = linhas[:fim + 1]
        final_vazio = True
    mapa = {str(k): str(v) for k, v in ((selecao or {}).get('itens') or {}).items() if str(v) in TIPOS}
    alterados, por_tipo = [], Counter()
    for i, l in enumerate(linhas):
        if not l.startswith('|0200|'):
            continue
        c = l.split('|')
        novo = mapa.get(c[2])
        if not novo or len(c) < 8 or c[7] == novo:
            continue
        alterados.append({'cod': c[2], 'desc': c[3], 'de': c[7], 'para': novo})
        por_tipo[novo] += 1
        c[7] = novo
        linhas[i] = '|'.join(c)
    # só o campo 07 do 0200 muda: nenhuma linha entra ou sai, então o bloco 9 e os fechamentos ficam como estão
    avisos = ['Corrija também o tipo desses produtos no cadastro do Domínio; senão o tipo 00 volta no próximo SPED.']
    if assinado:
        avisos.insert(0, 'O arquivo estava assinado no PVA: a assinatura foi retirada (ela deixa de valer com a alteração). '
                         'Valide e assine de novo no PVA.')
    resumo = {'alterados': len(alterados), 'por_tipo': dict(por_tipo), 'lista': alterados[:2000], 'avisos': avisos}
    return quebra.join(linhas) + (quebra if final_vazio else ''), resumo


def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    sped, js = opt('--sped'), opt('--json')
    if not sped or not js:
        print('uso: cad-0200 --sped ARQ.txt --json saida.json [--aplicar selecao.json --saida novo.txt]')
        return 1
    try:
        import difal_ro as dr
        texto, enc = dr._ler(sped)
        if opt('--aplicar'):
            with open(opt('--aplicar'), 'r', encoding='utf-8') as fh:
                sel = json.load(fh)
            novo, res = aplicar_texto(texto, sel)
            tmp = opt('--saida') + '.parcial'
            with open(tmp, 'w', encoding=enc, newline='') as fh:
                fh.write(novo)
            os.replace(tmp, opt('--saida'))
        else:
            res = analisar_texto(texto)
    except Exception as e:  # pragma: no cover
        res = {'erro': f'Falha ao processar: {e}'}
    tmp = js + '.parcial'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False)
    os.replace(tmp, js)
    return 0

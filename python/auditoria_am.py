# -*- coding: utf-8 -*-
"""Auditoria de itens do SPED Fiscal (EFD ICMS/IPI) para o Amazonas — módulo restrito ao Admin.

Duas famílias de verificação, que NUNCA se misturam na tela:

  A) Verificações com BASE LEGAL LIDA NO TEXTO OFICIAL (SILT/SEFAZ-AM, lido em 06/10/2026):
       - LC 19/97 art. 12 (alíquotas) e RICMS/AM art. 12 (Decreto 20.686/99);
       - Lei 6.108/2022, Anexos III a XXVI (mercadorias da Substituição Tributária, com CEST/NCM).
     Cada achado traz o dispositivo, o link oficial e o que foi (e o que NÃO foi) conferido.

  B) Verificações de CONSISTÊNCIA DO ARQUIVO (somas, cálculo da base × alíquota, CFOP × operação).
     Não afirmam infração: são divergências matemáticas/estruturais do próprio SPED e
     NÃO têm base legal associada (rotulado assim de propósito).

O que sai daqui são HIPÓTESES para análise do contador. IA, quando usada, só explica; nunca é base legal.
"""
import os
import re
import sys
import json
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from st_am_dados import LEI_6108_ST
except Exception:  # pragma: no cover
    LEI_6108_ST = {}

URL_LC19 = 'https://sistemas.sefaz.am.gov.br/silt/norma/lei-complementar/ac5497ab-4fbd-4bc8-a51b-32405f61dc30/lei-complementar-n-19-de-29-de-dezembro-de-1997'
URL_RICMS = 'https://sistemas.sefaz.am.gov.br/get/Normas.do?metodo=viewDoc&uuidDoc=cc3888c0-e1b9-4433-b513-3c0f29cc625a'
URL_CV142 = 'https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18'
URL_L6108 = 'https://sistemas.sefaz.am.gov.br/get/Normas.do?metodo=viewDoc&uuidDoc=84be7172-451e-4ca0-802e-1a0303e5f0b2'

BASE = {
    'aliq_interna': {
        'status': 'lida',
        'norma': 'LC 19/97 (Código Tributário do AM), art. 12, I, alíneas "a" e "b"; RICMS/AM (Decreto 20.686/99), art. 12, I',
        'resumo': 'Alíquotas internas: 25% (automóveis de luxo, armas, joias, combustíveis, energia etc.), 20% para as demais '
                  'mercadorias e serviços (desde 01/04/2023, LC 244/23), 18% para GLP, 12% para produtos agrícolas comestíveis '
                  'produzidos/beneficiados no Estado e 30% para fumo, bebidas alcoólicas e comunicação (RICMS art. 12, I, "e").',
        'links': [URL_LC19, URL_RICMS],
        'nao_conferido': 'Reduções de base de cálculo, isenções e benefícios (RICMS art. 13 e Anexos) não foram aplicados: '
                         'uma alíquota "fora da lista" pode ter justificativa em benefício específico.',
    },
    'aliq_interestadual': {
        'status': 'lida',
        'norma': 'LC 19/97, art. 12, II; RICMS/AM, art. 12, II',
        'resumo': 'Interestadual: 12% como regra; 4% para transporte aéreo e para bens/mercadorias importados (Resolução do Senado).',
        'links': [URL_LC19, URL_RICMS],
        'nao_conferido': 'A alíquota de 7% (destino S/SE) decorre de Resolução do Senado que NÃO foi lida; por isso 7% não é apontado.',
    },
    'st_normal': {
        'status': 'lida',
        'norma': 'Lei 6.108/2022, arts. 1º e 2º e Anexos III a XXVI (lista por CEST/NCM)',
        'resumo': 'As mercadorias dos Anexos II a XXVI sujeitam-se ao ICMS por substituição tributária (operações subsequentes) '
                  'e antecipação com encerramento de tributação.',
        'links': [URL_L6108],
        'nao_conferido': 'O art. 4º autoriza o Poder Executivo a excluir mercadorias da ST (ato não pesquisado), e a regra pode '
                         'não alcançar quem é o próprio substituto/industrial. Confirme a vigência do item antes de agir.',
    },
    'st_cadastro': {
        'status': 'lida',
        'norma': 'Convênio ICMS 142/2018, cláusula vigésima, I e §3º (CONFAZ); Lei 6.108/2022, Anexos III a XXVI (CEST/NCM)',
        'resumo': 'O documento fiscal com mercadoria listada nos anexos deve informar o CEST de cada item, mesmo que a operação não seja de ST; '
                  'a inobservância implica exigência do imposto nos termos da legislação do destino. Os anexos da Lei 6.108/2022 relacionam cada mercadoria por CEST e NCM.',
        'links': [URL_CV142, URL_L6108],
        'nao_conferido': 'Um mesmo NCM pode ter vários CEST (por tipo de embalagem, por exemplo); o sistema só indica o(s) candidato(s).',
    },
    'st_fora_lista': {
        'status': 'lida',
        'norma': 'Lei 6.108/2022, art. 1º e Anexos III a XXVI',
        'resumo': 'Item com CST de ST (010/030/060/070) cujo CEST/NCM não aparece nos anexos lidos da Lei 6.108/2022.',
        'links': [URL_L6108],
        'nao_conferido': 'A ST também pode decorrer de Convênio/Protocolo ICMS (CONFAZ — não lido) e 15 linhas do texto oficial '
                         'não foram lidas automaticamente. Por isso é só "verificar".',
    },
}

CST_TRIB = {'00', '10', '20', '70', '90'}
CST_ST = {'10', '30', '60', '70'}
CANC = {'02', '03', '04', '05'}
ALIQ_INT_OK = {12.0, 18.0, 20.0, 25.0, 30.0}
ALIQ_EST_OK = {4.0, 7.0, 12.0}


def _n(s):
    try:
        return float(str(s).replace('.', '').replace(',', '.')) if ',' in str(s) else float(str(s) or 0)
    except Exception:
        return 0.0


def _brl(v):
    s = f'{abs(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('-' if v < 0 else '') + 'R$ ' + s


def _lin(path):
    for enc in ('utf-8', 'latin-1'):
        try:
            with open(path, 'r', encoding=enc) as fh:
                return fh.read().splitlines()
        except UnicodeDecodeError:
            continue
    return []


def _ncm_st(ncm):
    """CEST candidatos cujo NCM (ou prefixo) cobre o NCM do item."""
    out = []
    for cest, (anexo, seg, ncms) in LEI_6108_ST.items():
        for p in ncms:
            if p and ncm.startswith(p):
                out.append(cest)
                break
    return out


class Achado:
    def __init__(self, regra, familia, titulo, gravidade, descricao, base=None, como=None):
        self.d = {'regra': regra, 'familia': familia, 'titulo': titulo, 'gravidade': gravidade, 'descricao': descricao,
                  'base_legal': base, 'como_verificar': como, 'qtd': 0, 'valor': 0.0, 'exemplos': []}

    def add(self, valor, ex):
        self.d['qtd'] += 1
        self.d['valor'] += valor
        if len(self.d['exemplos']) < 25:
            self.d['exemplos'].append(ex)


def _periodo(dt):
    return f'{dt[2:4]}/{dt[4:]}' if dt and len(dt) == 8 else ''


def analisar(caminhos):
    prod = {}      # cod_item -> dict(descr, ncm, cest)
    cab = {}
    ach = {}
    tot = defaultdict(float)
    cob = defaultdict(int)

    def A(regra, familia, titulo, grav, desc, base=None, como=None):
        if regra not in ach:
            ach[regra] = Achado(regra, familia, titulo, grav, desc, BASE.get(base) if base else None, como)
        return ach[regra]

    c190_saida = defaultdict(float)   # (cst,cfop,aliq) -> [bc, icms]
    c190 = {}
    c170_soma = defaultdict(lambda: [0.0, 0.0])
    nota = {}

    for path in caminhos:
        linhas = _lin(path)
        # 1ª passada: cadastro de itens e cabeçalho
        for ln in linhas:
            c = ln.split('|')
            if len(c) < 3:
                continue
            if c[1] == '0000' and len(c) > 9:
                cab = {'dt_ini': c[4], 'dt_fin': c[5], 'nome': c[6], 'cnpj': c[7], 'uf': c[9]}
            elif c[1] == '0200' and len(c) > 8:
                prod[c[2]] = {'descr': c[3], 'ncm': re.sub(r'\D', '', c[8]), 'cest': re.sub(r'\D', '', c[13]) if len(c) > 13 else ''}
        per = _periodo(cab.get('dt_fin', ''))
        pos_2023 = cab.get('dt_fin', '')[4:] + cab.get('dt_fin', '')[2:4] >= '202304' if len(cab.get('dt_fin', '')) == 8 else True
        ind_oper = cod_sit = num = ''
        for ln in linhas:
            c = ln.split('|')
            if len(c) < 3:
                continue
            r = c[1]
            if r == 'C100':
                ind_oper = c[2] if len(c) > 2 else ''
                cod_sit = c[6] if len(c) > 6 else ''
                num = c[8] if len(c) > 8 else ''
                cob['notas'] += 1
                if cod_sit in CANC:
                    cob['canceladas'] += 1
                nota = {'num': num, 'oper': ind_oper, 'sit': cod_sit}
                continue
            if cod_sit in CANC:
                continue
            if r == 'C170' and len(c) > 15:
                cob['itens'] += 1
                cod = c[3]
                cst, cfop = c[10][-2:], c[11]
                vl_item, bc, aliq, icms = _n(c[7]) - _n(c[8]), _n(c[13]), _n(c[14]), _n(c[15])
                p = prod.get(cod, {})
                ncm, cest = p.get('ncm', ''), p.get('cest', '')
                ex = {'nota': num, 'item': c[2], 'cod': cod, 'descr': (p.get('descr') or '')[:60], 'ncm': ncm, 'cest': cest,
                      'cst': c[10], 'cfop': cfop, 'bc': bc, 'aliq': aliq, 'icms': icms, 'valor_item': round(vl_item, 2)}
                # chave de soma para cruzar com C190
                k = (c[10], cfop, aliq)
                c170_soma[k][0] += bc
                c170_soma[k][1] += icms
                saida = ind_oper == '1' or cfop[:1] in '567'
                interna = cfop[:1] in '15'
                # B1: cálculo
                if aliq > 0 and bc > 0 and abs(round(bc * aliq / 100, 2) - icms) > max(0.05, bc * 0.0005):
                    a = A('arq_calculo', 'B', 'ICMS do item diferente de base × alíquota', 'Média',
                          'No registro C170 o valor do ICMS não bate com a base multiplicada pela alíquota (tolerância de centavos).',
                          None, 'Confira no sistema de origem a base e a alíquota do item.')
                    a.add(abs(round(bc * aliq / 100, 2) - icms), dict(ex, esperado=round(bc * aliq / 100, 2)))
                # B2: CST × valores
                if cst in CST_TRIB and cst not in ('90',) and icms == 0 and bc == 0 and vl_item > 0:
                    a = A('arq_cst_sem_valor', 'B', 'CST tributado sem base e sem ICMS', 'Média',
                          'O CST indica tributação (00/10/20/70) mas base e ICMS estão zerados.', None,
                          'Verifique se o CST correto seria isento/não tributado/ST (40, 41, 60...) ou se faltou preencher o ICMS.')
                    a.add(vl_item, ex)
                if cst in ('40', '41', '50', '51', '60') and icms > 0 and cst != '51':
                    a = A('arq_cst_com_icms', 'B', 'CST sem tributação própria, mas com ICMS destacado', 'Média',
                          'CST 40/41/50/60 (isenta, não tributada, suspensa, ICMS cobrado antes) com valor de ICMS no item.', None,
                          'Revise o CST ou o valor de ICMS lançado.')
                    a.add(icms, ex)
                # B3: CFOP × operação
                if (ind_oper == '0' and cfop[:1] in '567') or (ind_oper == '1' and cfop[:1] in '123'):
                    a = A('arq_cfop_oper', 'B', 'CFOP incompatível com entrada/saída da nota', 'Alta',
                          'O primeiro dígito do CFOP (1/2/3 = entrada; 5/6/7 = saída) não combina com o IND_OPER da nota (C100).', None,
                          'Corrija o CFOP ou o indicador de operação.')
                    a.add(0.0, ex)
                # A1: alíquota interna
                if saida and interna and cst in ('00', '10', '20', '70') and aliq > 0 and aliq not in ALIQ_INT_OK:
                    ant = aliq == 17.0 and pos_2023
                    a = A('aliq_interna', 'A', 'Alíquota interna fora das alíquotas previstas em lei', 'Alta' if ant else 'Média',
                          'Saída interna com alíquota que não é nenhuma das previstas no art. 12, I (12%, 18%, 20%, 25%, 30%).'
                          + (' Há itens com 17%, alíquota geral ANTERIOR a 01/04/2023.' if ant else ''), 'aliq_interna',
                          'Confira se há benefício/redução que justifique; se não, a alíquota geral é 20% a partir de 01/04/2023.')
                    a.add(max(0.0, bc * (20 - aliq) / 100) if ant else 0.0, ex)
                # A2: interestadual
                if saida and cfop[:1] == '6' and cst in ('00', '10', '20', '70') and aliq > 0 and aliq not in ALIQ_EST_OK:
                    a = A('aliq_interestadual', 'A', 'Alíquota interestadual fora de 4%, 7% ou 12%', 'Alta',
                          'Saída interestadual tributada com alíquota diferente das previstas (12% regra; 4% importados/aéreo; 7% não conferido).',
                          'aliq_interestadual', 'Confira a UF de destino e a origem (importado) do item.')
                    a.add(0.0, ex)
                # A3: ST — item da lista vendido com tributação normal
                cests = [cest] if cest in LEI_6108_ST else (_ncm_st(ncm) if ncm else [])
                na_lista = bool(cests)
                if saida and na_lista and cst in ('00', '20') and cfop in ('5101', '5102', '5108'):
                    seg = LEI_6108_ST[cests[0]][1] if cests[0] in LEI_6108_ST else ''
                    a = A('st_normal', 'A', 'Item da lista de ST vendido com tributação normal', 'Média',
                          'CEST/NCM do item consta nos Anexos da Lei 6.108/2022 (ST), mas a saída foi tributada normalmente (CST 00/20).',
                          'st_normal', 'Confirme se o contribuinte é o substituído (então a venda deveria sair com CST 60 / CFOP 5.405) '
                                       'ou se há exclusão/regra que mantenha a tributação normal.')
                    a.add(icms, dict(ex, anexo=LEI_6108_ST[cests[0]][0], segmento=seg, cest_lista=cests[0]))
                # A5: ST no CST mas fora da lista
                if cst in ('60', '10', '30', '70') and ncm and not na_lista and not cest:
                    a = A('st_fora_lista', 'A', 'CST de ST em item que não está na lista da Lei 6.108/2022', 'Baixa',
                          'O item usa CST de substituição tributária, mas seu NCM não aparece nos anexos lidos e o CEST não está no cadastro.',
                          'st_fora_lista', 'Confirme a origem da ST (Convênio/Protocolo) e preencha o CEST no cadastro.')
                    a.add(0.0, ex)
            elif r == 'C190' and len(c) > 7:
                cob['c190'] += 1
                k = (c[2], c[3], _n(c[4]))
                v = c190.setdefault(k, [0.0, 0.0, 0.0, 0.0])
                v[0] += _n(c[5]); v[1] += _n(c[6]); v[2] += _n(c[7]); v[3] += 1
                cfop = c[3]
                aliq = _n(c[4]); cst = c[2][-2:]
                if ind_oper == '1' or cfop[:1] in '567':
                    # A1/A2 também sobre C190 (notas de saída sem C170)
                    if cfop[:1] == '5' and cst in ('00', '10', '20', '70') and aliq > 0 and aliq not in ALIQ_INT_OK:
                        ant = aliq == 17.0 and pos_2023
                        a = A('aliq_interna_c190', 'A', 'Saídas internas (C190) com alíquota fora das previstas em lei',
                              'Alta' if ant else 'Média',
                              'Resumo de saídas internas com alíquota diferente de 12/18/20/25/30%.'
                              + (' Inclui alíquota de 17% (geral até 31/03/2023).' if ant else ''), 'aliq_interna',
                              'Abra as notas do período no sistema de origem e confira o cadastro tributário dos itens.')
                        a.add(_n(c[6]) * (20 - aliq) / 100 if ant else 0.0, {'nota': num, 'cst': c[2], 'cfop': cfop, 'aliq': aliq, 'bc': _n(c[6]), 'icms': _n(c[7])})
                    if cfop[:1] == '6' and cst in ('00', '10', '20', '70') and aliq > 0 and aliq not in ALIQ_EST_OK:
                        a = A('aliq_interestadual', 'A', 'Alíquota interestadual fora de 4%, 7% ou 12%', 'Alta',
                              'Saída interestadual tributada com alíquota diferente das previstas (12% regra; 4% importados/aéreo; 7% não conferido).',
                              'aliq_interestadual', 'Confira a UF de destino e a origem (importado) do item.')
                        a.add(0.0, {'nota': num, 'cst': c[2], 'cfop': cfop, 'aliq': aliq, 'bc': _n(c[6]), 'icms': _n(c[7])})
                    tot['deb_c190'] += _n(c[7]) if cfop[:1] in '567' else 0
                else:
                    tot['cred_c190'] += _n(c[7]) if cfop[:1] in '123' else 0
            elif r == '0200' and len(c) > 8:
                pass
            elif r == 'E110' and len(c) > 14:
                tot['e110_deb'] = _n(c[2]); tot['e110_cred'] = _n(c[6]); tot['e110_saldo_cred'] = _n(c[14])
            elif r == 'E111' and len(c) > 4:
                cob['e111'] += 1

    # A4: cadastro de item sem CEST, NCM na lista
    sem_cest = 0
    for cod, p in prod.items():
        if not p['cest'] and p['ncm']:
            cands = _ncm_st(p['ncm'])
            if cands:
                sem_cest += 1
                a = A('st_cadastro', 'A', 'Item cujo NCM está na lista de ST, mas sem CEST no cadastro', 'Baixa',
                      'O registro 0200 não informa CEST e o NCM consta nos anexos da Lei 6.108/2022.', 'st_cadastro',
                      'Preencha o CEST correto no cadastro do produto.')
                a.add(0.0, {'cod': cod, 'descr': p['descr'][:60], 'ncm': p['ncm'], 'cest_candidatos': cands[:4], 'qtd_candidatos': len(cands)})

    # B4: C170 × C190 por (CST, CFOP, alíquota)
    for k, (bc, icms) in c170_soma.items():
        v = c190.get(k)
        if v is not None and (abs(v[1] - bc) > 0.10 or abs(v[2] - icms) > 0.10):
            a = A('arq_c170_c190', 'B', 'Soma dos itens (C170) diferente do resumo (C190)', 'Alta',
                  'Para a mesma combinação CST × CFOP × alíquota, as somas de base e ICMS dos itens não fecham com o resumo analítico.', None,
                  'Revise a geração do arquivo: itens e totais devem fechar.')
            a.add(abs(v[2] - icms), {'cst': k[0], 'cfop': k[1], 'aliq': k[2], 'bc_itens': round(bc, 2), 'bc_c190': round(v[1], 2),
                                     'icms_itens': round(icms, 2), 'icms_c190': round(v[2], 2)})
    # B5: E110 × C190
    info = []
    if 'e110_deb' in tot:
        dd = tot['e110_deb'] - tot['deb_c190']
        info.append({'titulo': 'Débitos: E110 × saídas (C190)', 'e110': round(tot['e110_deb'], 2), 'c190': round(tot['deb_c190'], 2),
                     'dif': round(dd, 2), 'nota': 'A diferença pode ser ajuste/ICMS próprio de outros registros (E111, D, E3). Só indica onde olhar.'})
        dc = tot['e110_cred'] - tot['cred_c190']
        info.append({'titulo': 'Créditos: E110 × entradas (C190)', 'e110': round(tot['e110_cred'], 2), 'c190': round(tot['cred_c190'], 2),
                     'dif': round(dc, 2), 'nota': 'Idem; diferenças são esperadas quando há crédito extemporâneo ou ajustes.'})

    achados = sorted((a.d for a in ach.values()), key=lambda d: ({'Alta': 0, 'Média': 1, 'Baixa': 2}[d['gravidade']], -d['qtd']))
    return {
        'cliente': {'cnpj': cab.get('cnpj', ''), 'nome': cab.get('nome', ''), 'uf': cab.get('uf', ''),
                    'periodo': _periodo(cab.get('dt_ini', '')) + (' a ' + _periodo(cab.get('dt_fin', '')) if cab.get('dt_fin') != cab.get('dt_ini') else '')},
        'achados': achados,
        'conciliacao': info,
        'cobertura': dict(cob, itens_cadastrados=len(prod), st_lista=len(LEI_6108_ST)),
        'avisos': (['Este arquivo não é de AM (UF ' + cab.get('uf', '?') + '): regras de alíquota e ST do Amazonas não se aplicam.'] if cab.get('uf') not in ('AM', '', None) else [])
                  + (['Registros C170 inexistentes: arquivo sem itens (só resumo C190). A auditoria de itens de saída exige os XMLs das notas.'] if not cob.get('itens') else []),
        'bases': {k: v for k, v in BASE.items()},
    }


def main_cli(argv):
    args = argv
    jo = args[args.index('--json') + 1] if '--json' in args else None
    arqs = []
    i = 0
    while i < len(args):
        if args[i] == '--sped':
            i += 1
            while i < len(args) and not args[i].startswith('--'):
                arqs.append(args[i]); i += 1
        else:
            i += 2 if args[i] == '--json' else 1
    if not arqs:
        print('uso: auditoria-icms-am --sped ARQ.txt [ARQ2.txt ...] --json saida.json'); return 1
    try:
        res = analisar(arqs)
    except Exception as e:
        res = {'erro': f'Falha ao ler o SPED: {e}'}
    if jo:
        with open(jo, 'w', encoding='utf-8') as fh:
            json.dump(res, fh, ensure_ascii=False)
    else:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main_cli(sys.argv[1:]))

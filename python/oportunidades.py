# -*- coding: utf-8 -*-
"""Radar de Oportunidades Fiscais (uso interno — módulo restrito ao Admin).

Lê arquivos de EFD-Contribuições (e, opcionalmente, de EFD ICMS/IPI) de UM cliente e procura
valores que podem ser recuperados ou economizados. Cada achado traz o fundamento legal, como foi
apurado, o prazo e os pontos de atenção.

IMPORTANTE: o que sai daqui são HIPÓTESES para análise do contador. Nada é pedido ou
compensado automaticamente, e a base legal deve ser revalidada antes de qualquer proposta.

Detectores implementados (todos calculados só com o que está nos arquivos):
  1. PIS/COFINS monofásico na revenda  — itens vendidos com CST 01/02 cujo NCM está nas listas
     da Tabela 4.3.10 da EFD-Contribuições (farmacêuticos, perfumaria/higiene, pneus, combustíveis).
  2. ICMS na base do PIS/COFINS (Tema 69/STF) — itens cuja base de PIS/COFINS ainda inclui o ICMS.
  3. CIAP não escriturado (EFD ICMS/IPI) — entradas de ativo imobilizado com ICMS destacado e sem
     movimentação de imobilização (G125/IM) no arquivo.
"""
import re
import io
import os
import json
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict, OrderedDict

# ----------------------------------------------------------------------------- utilidades
def _num(s):
    try:
        return float(str(s).replace('.', '').replace(',', '.')) if ',' in str(s) and '.' in str(s) else float(str(s).replace(',', '.'))
    except Exception:
        return 0.0


def _pl(n, sing, plur):
    return f'{n} {sing if n == 1 else plur}'


def _brl(v):
    s = f'{abs(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('-' if v < 0 else '') + 'R$ ' + s


def _data(s):
    s = (s or '').strip()
    if len(s) == 8 and s.isdigit():
        return f'{s[0:2]}/{s[2:4]}/{s[4:8]}'
    return s


def _iso(s):
    s = (s or '').strip()
    if len(s) == 8 and s.isdigit():
        return f'{s[4:8]}-{s[2:4]}-{s[0:2]}'
    return ''


def _ler(caminho):
    with open(caminho, 'rb') as f:
        bruto = f.read()
    try:
        texto = bruto.decode('utf-8')
    except UnicodeDecodeError:
        texto = bruto.decode('latin-1')
    return [l for l in texto.split('\n') if l.startswith('|')]


def _campos(linha):
    return linha.rstrip('\r').split('|')


# ----------------------------------------------------------------------------- regras de NCM (Tabela 4.3.10)
# Cada regra: (rótulo, código na tabela oficial, lei, lista de prefixos, exceções, confiança, observação)
# Os prefixos e exceções vêm do texto da própria Tabela 4.3.10 (EFD-Contribuições) carregada no FiscoCont+.
REGRAS_MONOFASICO = [
    {'grupo': 'Produtos farmacêuticos', 'tabela': '201', 'lei': 'Lei 10.147/2000, arts. 1º e 2º',
     'prefixos': ['3001', '3003', '3004', '30021', '30022', '300290', '300510', '300630', '300660'],
     'excecoes': ['30039056', '30049046'], 'confianca': 'Alta',
     'obs': 'Posições 30.01, 30.03 (exceto 3003.90.56), 30.04 (exceto 3004.90.46) e itens da Tabela 4.3.10, código 201.'},
    {'grupo': 'Perfumaria, toucador e higiene pessoal', 'tabela': '202', 'lei': 'Lei 10.147/2000, arts. 1º e 2º',
     'prefixos': ['3303', '3304', '3305', '3306', '3307', '34011190', '34012010', '96032100'],
     'excecoes': [], 'confianca': 'Alta',
     'obs': 'Posições 33.03 a 33.07 e códigos 3401.11.90, 3401.20.10 e 9603.21.00 (Tabela 4.3.10, código 202).'},
    {'grupo': 'Pneumáticos (pneus novos e câmaras de ar)', 'tabela': '304', 'lei': 'Lei 10.485/2002',
     'prefixos': ['4011', '4013'], 'excecoes': [], 'confianca': 'Média',
     'obs': 'Posições 40.11 e 40.13 (Tabela 4.3.10, código 304). Conferir o artigo da Lei 10.485/2002 aplicável à revenda.'},
    {'grupo': 'Combustíveis (diesel, GLP, gasolina)', 'tabela': '101/102/103', 'lei': 'Lei 9.718/1998, art. 4º',
     'prefixos': ['27101921', '27111910', '271012'], 'excecoes': [], 'confianca': 'Média',
     'obs': 'Na revenda por varejista, PIS/COFINS têm alíquota zero. A tabela oficial traz NCM de gasolina em código antigo; o prefixo 2710.12 é usado por aproximação.'},
    {'grupo': 'Álcool para fins carburantes', 'tabela': '112/113', 'lei': 'Lei 9.718/1998, art. 5º',
     'prefixos': ['22071000', '22072010'], 'excecoes': [], 'confianca': 'Média',
     'obs': 'Álcool vendido por comerciante varejista tem alíquota zero (art. 5º). Confirmar a modalidade da venda.'},
    {'grupo': 'Bebidas frias (águas, refrigerantes, cervejas)', 'tabela': '4xx (bebidas frias)', 'lei': 'Lei 13.097/2015, art. 28',
     'prefixos': ['2201', '2202', '2203'], 'excecoes': [], 'confianca': 'Baixa',
     'obs': 'Posições 22.01 (águas), 22.02 (refrigerantes, refrescos, isotônicos) e 22.03 (cervejas). A própria Tabela 4.3.10 cita o art. 28 da Lei 13.097/2015 para a revenda a alíquota zero por pessoas jurídicas varejistas. O texto da lei não foi conferido nesta versão e há ex-tarifários (por exemplo, águas minerais naturais) e regras por embalagem: conferir antes de qualquer pedido.'},
]


def _regra_ncm(ncm):
    ncm = re.sub(r'\D', '', ncm or '')
    if len(ncm) < 4:
        return None
    for r in REGRAS_MONOFASICO:
        if any(ncm.startswith(e) for e in r['excecoes']):
            continue
        if any(ncm.startswith(p) for p in r['prefixos']):
            return r
    return None


# ----------------------------------------------------------------------------- base legal (texto exibido na tela)
LEGAL = {
    'monofasico': {
        'titulo': 'PIS/COFINS monofásico pago na revenda',
        'fundamento': [
            {'norma': 'Lei 10.147/2000, arts. 1º e 2º', 'fonte': 'Texto oficial (Planalto), lido em 05/10/2026',
             'texto': 'Fabricantes e importadores de produtos farmacêuticos e de perfumaria/higiene recolhem PIS/COFINS em alíquotas diferenciadas. A receita da venda desses produtos por quem não é industrial nem importador tem alíquota zero.'},
            {'norma': 'Lei 9.718/1998, arts. 4º e 5º', 'fonte': 'Texto oficial (Planalto), lido em 05/10/2026',
             'texto': 'Combustíveis derivados de petróleo e álcool: a tributação é concentrada em produtores e importadores, e o revendedor varejista tem alíquota zero.'},
            {'norma': 'Lei 13.097/2015, art. 28 (bebidas frias)', 'fonte': 'Citada na observação do código 004 da Tabela 4.3.10; texto da lei não lido',
             'texto': 'Revenda de bebidas frias (águas, refrigerantes, cervejas) por pessoa jurídica varejista a alíquota zero de PIS/COFINS, conforme a observação da própria Tabela 4.3.10. Vigência e enquadramento a conferir.'},
            {'norma': 'Lei 10.485/2002 (veículos, autopeças e pneus)', 'fonte': 'Citada pela Tabela 4.3.10; artigo a conferir',
             'texto': 'Regime monofásico para veículos, autopeças e pneumáticos, com alíquota zero na revenda.'},
            {'norma': 'Tabela 4.3.10 da EFD-Contribuições', 'fonte': 'Tabelas oficiais carregadas no FiscoCont+ (30/09/2026)',
             'texto': 'Lista oficial de produtos de incidência monofásica (CST 02 e 04), usada para as listas de NCM deste detector.'}],
        'prazo': 'O direito de pedir a restituição se extingue em 5 anos contados do pagamento indevido (CTN, art. 168, I). A recuperação costuma ser feita por compensação (PER/DCOMP, Lei 9.430/1996, art. 74, e IN RFB 2.055/2021: conferir o texto vigente).',
        'atencao': ['Só vale se o cliente for revendedor. Se for industrial ou importador, a regra é outra.',
                    'Ex-tarifários e exceções de NCM mudam o resultado: conferir o NCM do cadastro do produto.',
                    'NFC-e (registro C175) não traz NCM, então essas vendas não são analisadas aqui.',
                    'Verificar se o cliente já pediu restituição ou compensação dessas competências.'],
    },
    'tema69': {
        'titulo': 'ICMS na base de cálculo do PIS/COFINS (Tema 69 do STF)',
        'fundamento': [
            {'norma': 'STF, RE 574.706 (Tema 69)', 'fonte': 'Tese conferida em fontes secundárias (o portal do STF bloqueou a consulta)',
             'texto': '"O ICMS não compõe a base de cálculo para a incidência do PIS e da COFINS." O ICMS a ser excluído é o destacado na nota fiscal.'},
            {'norma': 'Embargos de declaração no RE 574.706 (maio/2021)', 'fonte': 'Fontes secundárias',
             'texto': 'Modulou os efeitos a partir de 15/03/2017, ressalvadas as ações judiciais e os procedimentos administrativos anteriores a essa data.'}],
        'prazo': 'Pedido de restituição ou compensação em até 5 anos do pagamento (CTN, art. 168, I). Fatos geradores anteriores a 15/03/2017 só entram se houver ação ou procedimento anterior.',
        'atencao': ['Verificar se há ação judicial, coisa julgada ou compensação já feita para as mesmas competências.',
                    'O detector só vê itens de NF-e (C170) com ICMS destacado. NFC-e e consolidações ficam de fora.',
                    'Compensações de valor alto costumam ser fiscalizadas. Guardar a memória de cálculo.'],
    },
    'ciap': {
        'titulo': 'CIAP: crédito de ICMS do ativo imobilizado',
        'fundamento': [
            {'norma': 'LC 87/1996, art. 20, §5º', 'fonte': 'Texto lido em 05/10/2026 (cópia online)',
             'texto': 'O crédito do ICMS de bens do ativo permanente é apropriado à razão de 1/48 por mês, com a primeira fração no mês da entrada, e proporcional às saídas tributadas.'},
            {'norma': 'RICMS/RO (Decreto 22.721/2018)', 'fonte': 'Artigos a conferir',
             'texto': 'Regras estaduais sobre escrituração do CIAP e sobre crédito extemporâneo.'}],
        'prazo': 'O crédito extemporâneo depende da regra do RICMS de Rondônia. Conferir o artigo e o prazo vigentes antes de lançar.',
        'atencao': ['Confirmar que o bem é usado na atividade do estabelecimento e que não é bem de uso e consumo.',
                    'O valor mostrado é o ICMS destacado nas notas de entrada de ativo, não o crédito já aproveitado.',
                    'O coeficiente de saídas tributadas reduz o crédito do mês.'],
    },
}

EM_DESENVOLVIMENTO = [
    {'titulo': 'Crédito de insumos de PIS/COFINS', 'norma': 'Leis 10.637/2002 e 10.833/2003, art. 3º; STJ, REsp 1.221.170 (Tema 779); Parecer Normativo Cosit 5/2018',
     'texto': 'Insumo se define por essencialidade ou relevância no processo produtivo. Vale só no regime não cumulativo. Depende de análise caso a caso.'},
    {'titulo': 'ICMS-ST pago a maior', 'norma': 'STF, RE 593.849/MG (Tema 201); LC 87/1996, art. 10',
     'texto': 'Restituição quando a base efetiva da venda é menor que a presumida. O procedimento depende da legislação de cada estado.'},
    {'titulo': 'Revisão do regime tributário', 'norma': 'LC 123/2006, arts. 3º, 16, 17 e 18; Lei 9.249/1995',
     'texto': 'Comparação entre Simples, Presumido e Real com os números do cliente. Precisa de folha de pagamento e faturamento de 12 meses.'},
]


# CFOP (sem o 1º dígito) de revenda de combustível e de mercadoria com ICMS-ST
CFOP_COMBUSTIVEL = ('651', '652', '653', '654', '655', '656', '667')
CFOP_ST = ('405', '404', '403')


# ----------------------------------------------------------------------------- EFD-Contribuições
def _analisar_efdc(caminho):
    linhas = _ler(caminho)
    cab = {'nome': '', 'cnpj': '', 'ini': '', 'fim': ''}
    ncm_item, desc_item = {}, {}
    for l in linhas:
        c = _campos(l)
        if c[1] == '0000' and len(c) > 9:
            # EFD-Contribuições: c[9] é o CNPJ (14 dígitos). Na EFD ICMS/IPI essa posição é a UF.
            if re.fullmatch(r'\d{14}', c[9].strip()):
                cab = {'ini': c[6], 'fim': c[7], 'nome': c[8], 'cnpj': c[9].strip()}
            else:
                cab = {'nome': c[6] if len(c) > 6 else '', 'cnpj': '', 'ini': '', 'fim': '', 'parece_fiscal': True}
        elif c[1] == '0200' and len(c) > 8:
            ncm_item[c[2]] = c[8]
            desc_item[c[2]] = c[3]
    comp = _iso(cab['ini'])[:7]
    mono = defaultdict(lambda: {'itens': 0, 'base': 0.0, 'pis': 0.0, 'cofins': 0.0, 'exemplos': []})
    t69 = {'itens': 0, 'icms': 0.0, 'valor': 0.0, 'ja_excluido': 0, 'indef': 0, 'exemplos': []}
    oper, sit, nota, dt = None, '', '', ''
    # Cobertura: o que foi lido, para o resultado "nenhuma oportunidade" poder ser conferido.
    cob = {'regs': defaultdict(int), 'c100_saida': 0, 'c170_saida': 0, 'c170_icms_cst01': 0, 'c170_com_ncm': 0,
           'c180_itens': 0, 'c180_com_ncm': 0, 'mono_itens': 0, 'mono_cst': defaultdict(int), 'mono_ok': 0,
           'cst_saida': defaultdict(int), 'c175_linhas': 0, 'st_cst01_linhas': 0, 'st_cst01_valor': 0.0,
           'st_cst01_base': 0.0, 'mod65_saida': 0,
           'notas': {}, 'c170_chaves': set(), 'c175_ev': defaultdict(list)}
    chave_atual = ''
    c180 = None            # item consolidado corrente (C180) para somar C181/C185
    for l in linhas:
        c = _campos(l)
        r = c[1]
        cob['regs'][r] += 1
        if r == 'C100' and len(c) > 10:
            oper, sit, nota, dt = c[2], c[6], c[8], c[10]
            chave_atual = c[9].strip() if len(c) > 9 else ''
            if oper == '1' and sit not in ('02', '03', '04', '05'):
                cob['c100_saida'] += 1
                if c[5] == '65':
                    cob['mod65_saida'] += 1
                if len(chave_atual) == 44:
                    cob['notas'][chave_atual] = {'mod': c[5], 'dt': dt, 'nota': nota}
            continue
        if r == 'C175' and oper == '1' and sit not in ('02', '03', '04', '05') and len(c) > 16:
            # NFC-e: o registro é analítico por CFOP/CST e NÃO traz NCM. Só dá para agir pelo CFOP.
            cfop = c[2]
            if not cfop or cfop[0] not in '567':
                continue
            cob['c175_linhas'] += 1
            cst_p, cst_c = c[5], c[11]
            v_p, v_c = _num(c[10]), _num(c[16])
            cob['cst_saida'][cst_p] += 1
            if cfop[1:] in CFOP_COMBUSTIVEL and cst_p in ('01', '02') and (v_p > 0 or v_c > 0):
                reg = REGRAS_MONOFASICO[3]
                g = mono[(reg['grupo'], reg['tabela'], reg['lei'], reg['confianca'], reg['obs'] + ' Identificado pelo CFOP de combustível (NFC-e, registro C175, sem NCM).')]
                g['itens'] += 1
                g['base'] += _num(c[6])
                g['pis'] += v_p
                g['cofins'] += v_c
                if len(g['exemplos']) < 6:
                    g['exemplos'].append({'nota': nota, 'data': _data(dt), 'produto': 'NFC-e, CFOP ' + cfop, 'ncm': '(sem NCM no C175)',
                                          'cst': cst_p, 'valor': round(v_p + v_c, 2)})
                cob['c175_ev'][chave_atual].append(('comb', (reg['grupo'], reg['tabela'], reg['lei'], reg['confianca'], reg['obs'] + ' Identificado pelo CFOP de combustível (NFC-e, registro C175, sem NCM).'), _num(c[6]), v_p, v_c))
            elif cfop[1:] in CFOP_ST and cst_p in ('01', '02') and (v_p > 0 or v_c > 0):
                cob['st_cst01_linhas'] += 1
                cob['st_cst01_valor'] += v_p + v_c
                cob['st_cst01_base'] += _num(c[6])
                cob['c175_ev'][chave_atual].append(('st', None, _num(c[6]), v_p, v_c))
            continue
        if r == 'C180' and len(c) > 8:
            cod, ncm180 = c[5], re.sub(r'\D', '', c[6] or '') or ncm_item.get(c[5], '')
            c180 = {'cod': cod, 'ncm': ncm180, 'ini': c[3], 'fim': c[4]}
            cob['c180_itens'] += 1
            if ncm180:
                cob['c180_com_ncm'] += 1
            continue
        if r in ('C181', 'C185') and c180 and len(c) > 10:
            cfop = c[3]
            if not cfop or cfop[0] not in '567':
                continue
            cst, v_trib = c[2], _num(c[10])
            cob['cst_saida'][cst] += 1 if r == 'C181' else 0
            reg = _regra_ncm(c180['ncm'])
            if reg:
                if r == 'C181':
                    cob['mono_itens'] += 1
                    cob['mono_cst'][cst] += 1
                if cst in ('01', '02') and v_trib > 0:
                    g = mono[(reg['grupo'], reg['tabela'], reg['lei'], reg['confianca'], reg['obs'])]
                    if r == 'C181':
                        g['itens'] += 1
                        g['base'] += _num(c[6])
                        g['pis'] += v_trib
                        if len(g['exemplos']) < 6:
                            g['exemplos'].append({'nota': 'consolidado (C180)', 'data': _data(c180['ini']) + ' a ' + _data(c180['fim']),
                                                  'produto': desc_item.get(c180['cod'], c180['cod'])[:48], 'ncm': c180['ncm'],
                                                  'cst': cst, 'valor': round(v_trib, 2)})
                    else:
                        g['cofins'] += v_trib
                        if g['exemplos'] and g['exemplos'][-1].get('nota') == 'consolidado (C180)' and g['exemplos'][-1].get('ncm') == c180['ncm']:
                            g['exemplos'][-1]['valor'] = round(g['exemplos'][-1]['valor'] + v_trib, 2)
                elif r == 'C181':
                    cob['mono_ok'] += 1
            continue
        if r != 'C170' or oper != '1' or sit in ('02', '03', '04', '05') or len(c) < 37:
            continue
        cfop = c[11]
        if not cfop or cfop[0] not in '567':
            continue
        cob['c170_saida'] += 1
        if chave_atual:
            cob['c170_chaves'].add(chave_atual)
        cob['cst_saida'][c[25]] += 1
        if ncm_item.get(c[3]):
            cob['c170_com_ncm'] += 1
        if c[25] in ('01', '02') and _num(c[15]) > 0:
            cob['c170_icms_cst01'] += 1
        _reg_diag = _regra_ncm(ncm_item.get(c[3], ''))
        if _reg_diag:
            cob['mono_itens'] += 1
            cob['mono_cst'][c[25]] += 1
            if not (c[25] in ('01', '02') and (_num(c[30]) > 0 or _num(c[36]) > 0)):
                cob['mono_ok'] += 1
        cst_pis, cst_cof = c[25], c[31]
        vl_item, vl_desc, vl_icms = _num(c[7]), _num(c[8]), _num(c[15])
        bc_pis, al_pis, v_pis = _num(c[26]), _num(c[27]), _num(c[30])
        al_cof, v_cof = _num(c[33]), _num(c[36])
        cod = c[3]
        ncm = ncm_item.get(cod, '')
        if cst_pis in ('01', '02') and (v_pis > 0 or v_cof > 0):
            reg = _regra_ncm(ncm)
            if reg:
                g = mono[(reg['grupo'], reg['tabela'], reg['lei'], reg['confianca'], reg['obs'])]
                g['itens'] += 1
                g['base'] += bc_pis
                g['pis'] += v_pis
                g['cofins'] += v_cof
                if len(g['exemplos']) < 6:
                    g['exemplos'].append({'nota': nota, 'data': _data(dt), 'produto': desc_item.get(cod, cod)[:48],
                                          'ncm': ncm, 'cst': cst_pis, 'valor': round(v_pis + v_cof, 2)})
        if cst_pis in ('01', '02') and vl_icms > 0:
            liquido = vl_item - vl_desc
            if abs(bc_pis - liquido) < 0.02:
                t69['itens'] += 1
                t69['icms'] += vl_icms
                t69['valor'] += vl_icms * (al_pis + al_cof) / 100.0
                if len(t69['exemplos']) < 6:
                    t69['exemplos'].append({'nota': nota, 'data': _data(dt), 'produto': desc_item.get(cod, cod)[:48],
                                            'icms': round(vl_icms, 2), 'valor': round(vl_icms * (al_pis + al_cof) / 100.0, 2)})
            elif abs(bc_pis - (liquido - vl_icms)) < 0.02:
                t69['ja_excluido'] += 1
            else:
                t69['indef'] += 1
    return cab, comp, mono, t69, cob



# ----------------------------------------------------------------------------- XML de NF-e / NFC-e
def _tag(e):
    return e.tag.split('}')[-1]


def _filho(e, nome):
    if e is None:
        return None
    for x in e:
        if _tag(x) == nome:
            return x
    return None


def _txt(e, nome, padrao=''):
    x = _filho(e, nome)
    return (x.text or '').strip() if x is not None and x.text else padrao


def _iter_xmls(caminhos):
    """Gera (nome, bytes) de arquivos .xml, de pastas (recursivo) e de .zip (inclusive zip dentro de zip)."""
    def do_zip(origem, nome, nivel=0):
        try:
            with zipfile.ZipFile(origem if isinstance(origem, str) else io.BytesIO(origem)) as z:
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    n = info.filename
                    low = n.lower()
                    if low.endswith('.xml'):
                        yield n, z.read(info)
                    elif low.endswith('.zip') and nivel < 2:
                        yield from do_zip(z.read(info), n, nivel + 1)
        except zipfile.BadZipFile:
            return
    for c in caminhos:
        if os.path.isdir(c):
            for raiz, _, arqs in os.walk(c):
                for a in arqs:
                    low = a.lower()
                    cam = os.path.join(raiz, a)
                    if low.endswith('.xml'):
                        with open(cam, 'rb') as f:
                            yield a, f.read()
                    elif low.endswith('.zip'):
                        yield from do_zip(cam, a)
        elif c.lower().endswith('.zip'):
            yield from do_zip(c, c)
        elif c.lower().endswith('.xml') and os.path.exists(c):
            with open(c, 'rb') as f:
                yield os.path.basename(c), f.read()


def _ler_nfe(dados):
    """Lê um XML de NF-e/NFC-e. Devolve ('nota', dict) ou ('cancelamento', chave) ou None."""
    try:
        raiz = ET.fromstring(dados)
    except ET.ParseError:
        return None
    tr = _tag(raiz)
    if tr in ('procEventoNFe', 'envEvento', 'evento'):
        for e in raiz.iter():
            if _tag(e) == 'infEvento':
                if _txt(e, 'tpEvento') == '110111':
                    return ('cancelamento', _txt(e, 'chNFe'))
        return None
    inf = None
    for e in raiz.iter():
        if _tag(e) == 'infNFe':
            inf = e
            break
    if inf is None:
        return None
    chave = (inf.get('Id') or '').replace('NFe', '')
    ide, emit = _filho(inf, 'ide'), _filho(inf, 'emit')
    status = ''
    for e in raiz.iter():
        if _tag(e) == 'infProt':
            status = _txt(e, 'cStat')
    itens = []
    for det in inf:
        if _tag(det) != 'det':
            continue
        prod, imp = _filho(det, 'prod'), _filho(det, 'imposto')
        if prod is None or imp is None:
            continue
        icms = _filho(imp, 'ICMS')
        v_icms = 0.0
        if icms is not None and len(icms):
            v_icms = _num(_txt(list(icms)[0], 'vICMS', '0'))
        def trib(nome, sub):
            bloco = _filho(imp, nome)
            if bloco is None or not len(bloco):
                return '', 0.0, 0.0, 0.0
            b = list(bloco)[0]
            return _txt(b, 'CST'), _num(_txt(b, 'vBC', '0')), _num(_txt(b, 'p' + sub, '0')), _num(_txt(b, 'v' + sub, '0'))
        cst_p, bc_p, al_p, v_p = trib('PIS', 'PIS')
        cst_c, bc_c, al_c, v_c = trib('COFINS', 'COFINS')
        itens.append({
            'cod': _txt(prod, 'cProd'), 'produto': _txt(prod, 'xProd'), 'ncm': re.sub(r'\D', '', _txt(prod, 'NCM')),
            'cfop': _txt(prod, 'CFOP'), 'v_prod': _num(_txt(prod, 'vProd', '0')), 'v_desc': _num(_txt(prod, 'vDesc', '0')),
            'v_acess': _num(_txt(prod, 'vFrete', '0')) + _num(_txt(prod, 'vSeg', '0')) + _num(_txt(prod, 'vOutro', '0')),
            'v_icms': v_icms, 'cst_pis': cst_p, 'bc_pis': bc_p, 'al_pis': al_p, 'v_pis': v_p,
            'cst_cof': cst_c, 'al_cof': al_c, 'v_cof': v_c})
    return ('nota', {'chave': chave, 'mod': _txt(ide, 'mod'), 'tp': _txt(ide, 'tpNF', '1'), 'num': _txt(ide, 'nNF'),
                     'emissao': (_txt(ide, 'dhEmi') or _txt(ide, 'dEmi'))[:10], 'cnpj': _txt(emit, 'CNPJ'), 'status': status,
                     'itens': itens})


# ----------------------------------------------------------------------------- EFD ICMS/IPI (CIAP)
CFOP_ATIVO = ('1551', '2551', '1552', '2552', '1406', '2406')
CST_CREDITO = ('00', '10', '20', '51', '70', '90')


def _analisar_fiscal(caminho):
    linhas = _ler(caminho)
    cab = {'nome': '', 'cnpj': '', 'ini': '', 'fim': ''}
    descr = {}
    ativo, g110, g125_im, oper, sit, nota, dt = [], 0, 0, None, '', '', ''
    for l in linhas:
        c = _campos(l)
        r = c[1]
        if r == '0000' and len(c) > 7:
            cab = {'ini': c[4], 'fim': c[5], 'nome': c[6], 'cnpj': c[7]}
        elif r == '0200' and len(c) > 3:
            descr[c[2]] = c[3]
        elif r == 'G110':
            g110 += 1
        elif r == 'G125' and len(c) > 4 and c[4] == 'IM':
            g125_im += 1
        elif r == 'C100' and len(c) > 10:
            oper, sit, nota, dt = c[2], c[6], c[8], c[10]
        elif r == 'C170' and oper == '0' and sit not in ('02', '03', '04', '05') and len(c) > 15:
            cfop, cst, v_icms = c[11], c[10], _num(c[15])
            if cfop in CFOP_ATIVO and cst[-2:] in CST_CREDITO and v_icms > 0:
                ativo.append({'nota': nota, 'data': _data(dt), 'produto': descr.get(c[3], c[3])[:48], 'cfop': cfop,
                              'icms': round(v_icms, 2)})
    return cab, _iso(cab['ini'])[:7], ativo, g110, g125_im


# ----------------------------------------------------------------------------- consolidação
def _mes(comp):
    return f'{comp[5:7]}/{comp[0:4]}' if len(comp) == 7 else comp


def analisar(efdc, fiscal=None, xmls=None):
    """efdc: caminhos da EFD-Contribuições; fiscal: caminhos da EFD ICMS/IPI; xmls: arquivos .xml/.zip ou pastas com NF-e/NFC-e."""
    fiscal = fiscal or []
    xmls = xmls or []
    notas_efd, chaves_c170, c175_ev = {}, set(), defaultdict(list)
    aviso = []
    cliente = {'nome': '', 'cnpj': ''}
    periodos, mono_tot, t69_tot = [], OrderedDict(), {'itens': 0, 'icms': 0.0, 'valor': 0.0, 'ja_excluido': 0, 'indef': 0, 'exemplos': [], 'por_mes': {}, 'fora': 0.0, 'fora_meses': []}
    mono_mes = defaultdict(float)
    cnpjs = set()
    cobt = {'c175_linhas': 0, 'st_cst01_linhas': 0, 'st_cst01_valor': 0.0, 'st_cst01_base': 0.0, 'mod65_saida': 0, 'arquivos': 0, 'c100_saida': 0, 'c170_saida': 0, 'c170_com_ncm': 0, 'c170_icms_cst01': 0, 'c180_itens': 0,
            'c180_com_ncm': 0, 'mono_itens': 0, 'mono_ok': 0, 'c175': 0, 'c400': 0, 'cst': defaultdict(int), 'mono_cst': defaultdict(int)}
    for p in efdc:
        nome_arq = p.split('/')[-1].split(chr(92))[-1]
        try:
            cab, comp, mono, t69, cob = _analisar_efdc(p)
        except Exception as e:
            aviso.append(f'Não consegui ler {nome_arq}: {e}')
            continue
        if not cab['cnpj']:
            if cab.get('parece_fiscal'):
                aviso.append(f'{nome_arq}: este arquivo parece ser a EFD ICMS/IPI (SPED Fiscal), não a EFD-Contribuições. Coloque-o no campo da EFD ICMS/IPI.')
            else:
                aviso.append(f'{nome_arq}: não parece uma EFD-Contribuições (sem registro 0000 válido).')
            continue
        cobt['arquivos'] += 1
        notas_efd.update(cob['notas'])
        chaves_c170 |= cob['c170_chaves']
        for k, v in cob['c175_ev'].items():
            c175_ev[k].extend(v)
        for k in ('c100_saida', 'c170_saida', 'c170_com_ncm', 'c170_icms_cst01', 'c180_itens', 'c180_com_ncm', 'mono_itens', 'mono_ok'):
            cobt[k] += cob[k]
        for k in ('c175_linhas', 'st_cst01_linhas', 'st_cst01_valor', 'st_cst01_base', 'mod65_saida'):
            cobt[k] += cob[k]
        cobt['c175'] += cob['regs'].get('C175', 0)
        cobt['c400'] += cob['regs'].get('C400', 0) + cob['regs'].get('C490', 0)
        for k, v in cob['cst_saida'].items():
            cobt['cst'][k] += v
        for k, v in cob['mono_cst'].items():
            cobt['mono_cst'][k] += v
        cnpjs.add(cab['cnpj'])
        cliente = {'nome': cab['nome'], 'cnpj': cab['cnpj']}
        periodos.append(comp)
        for k, v in mono.items():
            d = mono_tot.setdefault(k, {'itens': 0, 'base': 0.0, 'pis': 0.0, 'cofins': 0.0, 'exemplos': [], 'meses': set()})
            for f in ('itens', 'base', 'pis', 'cofins'):
                d[f] += v[f]
            d['meses'].add(comp)
            for ex in v['exemplos']:
                if len(d['exemplos']) < 8:
                    d['exemplos'].append(ex)
            mono_mes[comp] += v['pis'] + v['cofins']
        fora = comp < '2017-03'
        if fora:
            t69_tot['fora'] += t69['valor']
            if t69['valor'] > 0:
                t69_tot['fora_meses'].append(comp)
        else:
            for f in ('itens', 'icms', 'valor', 'ja_excluido', 'indef'):
                t69_tot[f] += t69[f]
            t69_tot['por_mes'][comp] = t69_tot['por_mes'].get(comp, 0.0) + t69['valor']
            for ex in t69['exemplos']:
                if len(t69_tot['exemplos']) < 8:
                    t69_tot['exemplos'].append(ex)
    if len(cnpjs) > 1:
        aviso.append('Os arquivos são de mais de um CNPJ. Analise um cliente por vez para o resultado fazer sentido.')


    # ---- XML das notas (NF-e / NFC-e): traz o NCM que a EFD não tem nas NFC-e
    xml_info = None
    if xmls:
        xml_info = {'lidos': 0, 'nota_ok': 0, 'sem_efd': 0, 'ja_c170': 0, 'outro_emit': 0, 'cancelada': 0, 'dup': 0,
                    'invalidos': 0, 'itens': 0, 'itens_ncm_mono': 0, 'por_mes': defaultdict(int)}
        cnpj_cli = next(iter(cnpjs)) if len(cnpjs) == 1 else ''
        vistos, cancel = set(), set()
        pendentes = []
        for nome_x, dados in _iter_xmls(xmls):
            xml_info['lidos'] += 1
            r = _ler_nfe(dados)
            if not r:
                xml_info['invalidos'] += 1
                continue
            if r[0] == 'cancelamento':
                cancel.add(r[1])
                continue
            pendentes.append(r[1])
        for n in pendentes:
            ch = n['chave']
            if ch in vistos:
                xml_info['dup'] += 1
                continue
            vistos.add(ch)
            if ch in cancel or (n['status'] and n['status'] not in ('100', '150')):
                xml_info['cancelada'] += 1
                continue
            if cnpj_cli and n['cnpj'] != cnpj_cli:
                xml_info['outro_emit'] += 1
                continue
            if n['tp'] != '1':
                continue
            # só vale a nota que a EFD declarou como saída: é o que de fato foi tributado no período
            if ch not in notas_efd:
                xml_info['sem_efd'] += 1
                continue
            if ch in chaves_c170:
                xml_info['ja_c170'] += 1
                continue
            xml_info['nota_ok'] += 1
            comp = n['emissao'][:7]
            xml_info['por_mes'][comp] += 1
            # a nota sai da leitura por C175 (sem NCM) e passa a valer pelo XML
            for tipo_ev, chave_g, base_ev, v_p_ev, v_c_ev in c175_ev.get(ch, []):
                if tipo_ev == 'comb' and chave_g in mono_tot:
                    d = mono_tot[chave_g]
                    d['itens'] -= 1; d['base'] -= base_ev; d['pis'] -= v_p_ev; d['cofins'] -= v_c_ev
                    d['exemplos'] = [e for e in d['exemplos'] if e.get('nota') != notas_efd[ch]['nota']]
                    if d['itens'] <= 0 or d['pis'] + d['cofins'] < 0.01:
                        del mono_tot[chave_g]
                elif tipo_ev == 'st':
                    cobt['st_cst01_linhas'] -= 1
                    cobt['st_cst01_valor'] -= v_p_ev + v_c_ev
                    cobt['st_cst01_base'] -= base_ev
            for it in n['itens']:
                if not it['cfop'] or it['cfop'][0] not in '567':
                    continue
                xml_info['itens'] += 1
                reg = _regra_ncm(it['ncm'])
                if reg:
                    xml_info['itens_ncm_mono'] += 1
                    cobt['mono_itens'] += 1
                    cobt['mono_cst'][it['cst_pis']] += 1
                    if it['cst_pis'] in ('01', '02') and (it['v_pis'] > 0 or it['v_cof'] > 0):
                        g = mono_tot.setdefault((reg['grupo'], reg['tabela'], reg['lei'], reg['confianca'], reg['obs']),
                                                {'itens': 0, 'base': 0.0, 'pis': 0.0, 'cofins': 0.0, 'exemplos': [], 'meses': set()})
                        g['itens'] += 1
                        g['base'] += it['bc_pis']
                        g['pis'] += it['v_pis']
                        g['cofins'] += it['v_cof']
                        g['meses'].add(comp)
                        if len(g['exemplos']) < 8:
                            g['exemplos'].append({'nota': n['num'] + (' (NFC-e)' if n['mod'] == '65' else ''), 'data': '/'.join([n['emissao'][8:10], n['emissao'][5:7], n['emissao'][:4]]),
                                                  'produto': it['produto'][:48], 'ncm': it['ncm'], 'cst': it['cst_pis'], 'valor': round(it['v_pis'] + it['v_cof'], 2)})
                        mono_mes[comp] += it['v_pis'] + it['v_cof']
                    else:
                        cobt['mono_ok'] += 1
                # Tema 69: ICMS ainda dentro da base do PIS/COFINS
                if it['cst_pis'] in ('01', '02') and it['v_icms'] > 0:
                    liquido = it['v_prod'] - it['v_desc'] + it['v_acess']
                    valor69 = it['v_icms'] * (it['al_pis'] + it['al_cof']) / 100.0
                    cobt['c170_icms_cst01'] += 1
                    if comp < '2017-03':
                        if abs(it['bc_pis'] - liquido) < 0.02:
                            t69_tot['fora'] += valor69
                            if comp not in t69_tot['fora_meses']:
                                t69_tot['fora_meses'].append(comp)
                    elif abs(it['bc_pis'] - liquido) < 0.02:
                        t69_tot['itens'] += 1
                        t69_tot['icms'] += it['v_icms']
                        t69_tot['valor'] += valor69
                        t69_tot['por_mes'][comp] = t69_tot['por_mes'].get(comp, 0.0) + valor69
                        if len(t69_tot['exemplos']) < 8:
                            t69_tot['exemplos'].append({'nota': n['num'] + (' (NFC-e)' if n['mod'] == '65' else ''), 'data': '/'.join([n['emissao'][8:10], n['emissao'][5:7], n['emissao'][:4]]),
                                                        'produto': it['produto'][:48], 'icms': round(it['v_icms'], 2), 'valor': round(valor69, 2)})
                    elif abs(it['bc_pis'] - (liquido - it['v_icms'])) < 0.02:
                        t69_tot['ja_excluido'] += 1
                    else:
                        t69_tot['indef'] += 1
        if not cnpj_cli and len(cnpjs) > 1:
            aviso.append('XML: como há mais de um CNPJ nas EFD, o emitente dos XMLs não foi conferido.')

    oportunidades = []
    meses_txt = lambda ms: ', '.join(_mes(m) for m in sorted(ms))

    # 1) monofásico
    for (grupo, tabela, lei, conf, obs), d in mono_tot.items():
        valor = d['pis'] + d['cofins']
        if valor < 0.01:
            continue
        oportunidades.append({
            'tipo': 'monofasico', 'titulo': 'PIS/COFINS monofásico na revenda: ' + grupo,
            'valor': round(valor, 2), 'confianca': conf, 'base_legal_status': 'conferida' if conf == 'Alta' else 'revalidar',
            'resumo': f'{_pl(d["itens"], "item vendido", "itens vendidos")} com CST 01/02 em ' + ('CFOP de combustível (NFC-e, sem NCM)' if any(str(e.get('ncm', '')).startswith('(sem') for e in d['exemplos']) else 'NCM de incidência monofásica') + f'. PIS {_brl(d["pis"])} e COFINS {_brl(d["cofins"])}.',
            'periodos': sorted(d['meses']),
            'como': f'Percorri os itens de saída (C170) e separei os que têm NCM de {grupo.lower()} e CST de PIS 01 ou 02 com tributo destacado. {obs}',
            'evidencias': d['exemplos'], 'lei_regra': lei,
        })
    # 2) Tema 69
    if t69_tot['valor'] >= 0.01:
        oportunidades.append({
            'tipo': 'tema69', 'titulo': 'ICMS na base do PIS/COFINS', 'valor': round(t69_tot['valor'], 2), 'confianca': 'Alta',
            'base_legal_status': 'conferida',
            'resumo': f'{_pl(t69_tot["itens"], "item de venda em que a base", "itens de venda em que a base")} de PIS/COFINS ainda inclui o ICMS ({_brl(t69_tot["icms"])} de ICMS destacado).',
            'periodos': sorted(t69_tot['por_mes'].keys()),
            'como': 'Para cada item de saída com CST 01/02 e ICMS destacado, comparei a base de PIS/COFINS com o valor do item. Se a base é igual ao valor líquido do item, o ICMS não foi excluído. O valor é o ICMS multiplicado pelas alíquotas de PIS e COFINS do item.'
                    + (' Não entram no valor: ' + ' e '.join(x for x in [
                        (f'{_pl(t69_tot["ja_excluido"], "item que já tinha", "itens que já tinham")} o ICMS excluído' if t69_tot['ja_excluido'] else ''),
                        (f'{_pl(t69_tot["indef"], "item com base", "itens com base")} diferente das duas formas' if t69_tot['indef'] else '')] if x) + '.'
                       if (t69_tot['ja_excluido'] or t69_tot['indef']) else ''),
            'evidencias': t69_tot['exemplos'], 'lei_regra': 'STF, RE 574.706 (Tema 69)',
            'por_mes': {m: round(v, 2) for m, v in sorted(t69_tot['por_mes'].items())},
        })
    elif t69_tot['ja_excluido'] and not t69_tot['itens']:
        aviso.append(f'Tema 69: nos arquivos analisados o ICMS já está excluído da base de PIS/COFINS em {t69_tot["ja_excluido"]} itens. Nada a recuperar por este caminho.')
    if t69_tot['fora'] >= 0.01:
        aviso.append(f'Tema 69: {_brl(t69_tot["fora"])} são de competências anteriores a 03/2017 ({meses_txt(t69_tot["fora_meses"])}) e ficam de fora da modulação, salvo ação ou procedimento anterior.')

    # 3) CIAP
    ciap_ativo, ciap_flag = [], False
    for p in fiscal:
        try:
            cab, comp, ativo, g110, g125 = _analisar_fiscal(p)
        except Exception as e:
            aviso.append(f'Não consegui ler {p.split("/")[-1].split(chr(92))[-1]}: {e}')
            continue
        if not cab['cnpj']:
            aviso.append(f'{p.split("/")[-1].split(chr(92))[-1]}: não parece uma EFD ICMS/IPI.')
            continue
        if cnpjs and cab['cnpj'] not in cnpjs:
            aviso.append(f'{cab["nome"]}: CNPJ diferente da EFD-Contribuições, ignorado no CIAP.')
            continue
        if not cliente['cnpj']:
            cliente = {'nome': cab['nome'], 'cnpj': cab['cnpj']}
        if ativo and g125 == 0:
            ciap_ativo.append((comp, ativo, g110))
        elif ativo and g125 > 0:
            aviso.append(f'CIAP {_mes(comp)}: há entradas de ativo e {g125} movimentos de imobilização (G125). Confira se todos os bens foram escriturados.')
    if ciap_ativo:
        total = sum(i['icms'] for _, at, _ in ciap_ativo for i in at)
        exemplos = [dict(i, competencia=_mes(c)) for c, at, _ in ciap_ativo for i in at][:8]
        oportunidades.append({
            'tipo': 'ciap', 'titulo': 'CIAP: ICMS de ativo imobilizado sem escrituração', 'valor': round(total, 2), 'confianca': 'Média',
            'base_legal_status': 'revalidar',
            'resumo': f'{_pl(sum(len(a) for _, a, _ in ciap_ativo), "entrada de ativo", "entradas de ativo")} com ICMS destacado e nenhum movimento de imobilização (G125/IM) no mesmo arquivo. Crédito mensal de referência: {_brl(total / 48)} (1/48).',
            'periodos': [c for c, _, _ in ciap_ativo],
            'como': 'Procurei entradas com CFOP de ativo imobilizado (1.551, 2.551, 1.552, 2.552, 1.406, 2.406), CST com direito a crédito e ICMS destacado. Depois verifiquei se o arquivo tem movimento de imobilização no CIAP (registro G125, tipo IM).',
            'evidencias': exemplos, 'lei_regra': 'LC 87/1996, art. 20, §5º',
        })
    elif not fiscal:
        aviso.append('CIAP não analisado: nenhuma EFD ICMS/IPI foi selecionada.')

    # Cobertura: mostra o que foi lido, para o "nenhuma oportunidade" poder ser conferido.
    cobertura = []
    if cobt['arquivos']:
        itens_saida = cobt['c170_saida'] + cobt['c180_itens']
        cobertura.append(f'{_pl(cobt["arquivos"], "EFD-Contribuições lida", "EFD-Contribuições lidas")}, com {_pl(cobt["c100_saida"], "nota de saída", "notas de saída")} detalhadas (C100) e {_pl(cobt["c170_saida"], "item de venda", "itens de venda")} (C170).')
        if cobt['c180_itens']:
            cobertura.append(f'{_pl(cobt["c180_itens"], "item", "itens")} de vendas consolidadas (C180/C181/C185) também foram lidos.')
        if cobt['c170_saida']:
            cobertura.append(f'NCM identificado em {cobt["c170_com_ncm"]} de {cobt["c170_saida"]} itens de venda (C170).' + (' Itens sem NCM no cadastro (registro 0200) não podem ser avaliados.' if cobt['c170_com_ncm'] < cobt['c170_saida'] else ''))
        if cobt['mono_itens']:
            csts = ', '.join(f'CST {k}: {v}' for k, v in sorted(cobt['mono_cst'].items()))
            cobertura.append(f'{_pl(cobt["mono_itens"], "item de venda tem", "itens de venda têm")} NCM de incidência monofásica ({csts}). {cobt["mono_ok"]} já estão com tratamento correto (sem tributo).')
        else:
            cobertura.append('Nenhum item de venda tem NCM de produto monofásico (farmacêutico, perfumaria, pneus, combustíveis, bebidas frias).')
        if cobt['c170_icms_cst01']:
            cobertura.append(f'{_pl(cobt["c170_icms_cst01"], "item de venda tem", "itens de venda têm")} CST 01/02 e ICMS destacado (base do Tema 69).')
        else:
            cobertura.append('Nenhum item de venda com CST 01/02 e ICMS destacado foi encontrado para o Tema 69.')
        if not itens_saida:
            aviso.append('Nenhum item de venda foi encontrado (registros C170 ou C180). Se o cliente declara as vendas de outra forma, o Radar ainda não cobre esse caso.')
        if cobt['mod65_saida']:
            cobertura.append(f'{cobt["mod65_saida"]} das notas de saída são NFC-e (modelo 65). Na EFD-Contribuições a NFC-e vem só resumida por CFOP e CST (C175), sem NCM nem ICMS. Por isso o produto não pode ser identificado e as vendas dessas notas só são analisadas pelo CFOP de combustível.')
        if xml_info is not None:
            xi = xml_info
            partes = [f'{xi["lidos"]} arquivos XML lidos']
            partes.append(f'{xi["nota_ok"]} notas analisadas pelo XML (NCM, CST e valores por item) em {len(xi["por_mes"])} {"mês" if len(xi["por_mes"]) == 1 else "meses"}')
            if xi['ja_c170']:
                partes.append(f'{xi["ja_c170"]} já detalhadas na EFD (C170) e mantidas como estão na EFD')
            if xi['sem_efd']:
                partes.append(f'{xi["sem_efd"]} sem correspondência nas EFD enviadas (outro período ou não declaradas) e ignoradas')
            if xi['cancelada']:
                partes.append(f'{xi["cancelada"]} canceladas/não autorizadas ignoradas')
            if xi['outro_emit']:
                partes.append(f'{xi["outro_emit"]} de outro emitente ignoradas')
            if xi['dup']:
                partes.append(f'{xi["dup"]} repetidas')
            if xi['invalidos']:
                partes.append(f'{xi["invalidos"]} arquivos que não eram NF-e (eventos, resumos ou outros)')
            cobertura.append('XML: ' + '; '.join(partes) + '.')
            cobertura.append(f'Nos XMLs: {xi["itens"]} itens de venda, dos quais {xi["itens_ncm_mono"]} têm NCM monofásico. Só entram os XMLs de notas que a EFD declara como saída, porque o valor só é recuperável se foi realmente tributado na EFD.')
        if cobt['c400']:
            cobertura.append(f'{cobt["c400"]} linhas de cupom/ECF (C400/C490) não foram analisadas por falta de NCM no registro.')
        if cobt['st_cst01_linhas']:
            aviso.append(f'Indício (não entra no total): em NFC-e, {_pl(cobt["st_cst01_linhas"], "linha", "linhas")} com CFOP de mercadoria com ICMS-ST e CST 01 pagaram {_brl(cobt["st_cst01_valor"])} de PIS/COFINS sobre {_brl(cobt["st_cst01_base"])} de vendas. Produtos com ST (bebidas, higiene, medicamentos, pneus) costumam ser monofásicos, mas o NCM não está na EFD. ' + ('Os XMLs enviados já foram descontados deste valor; para as demais notas, envie os XMLs das NFC-e do período.' if xml_info is not None else 'Para confirmar, é preciso analisar os XMLs das NFC-e do período (botão 3 do Radar).'))
    legal_usado = {t: LEGAL[t] for t in {o['tipo'] for o in oportunidades}}
    return {
        'cliente': cliente, 'periodos': sorted(set(periodos)), 'arquivos_efdc': len(efdc), 'arquivos_fiscal': len(fiscal),
        'oportunidades': oportunidades, 'legal': LEGAL, 'em_desenvolvimento': EM_DESENVOLVIMENTO,
        'cobertura': cobertura, 'com_xml': xml_info is not None, 'avisos': aviso, 'total': round(sum(o['valor'] for o in oportunidades), 2),
    }


def main_cli(argv):
    """fiscal_core.py radar-oportunidades --efdc a.txt b.txt [--fiscal c.txt ...] --json saida.json"""
    def grupo(nome):
        if nome not in argv:
            return []
        i = argv.index(nome) + 1
        out = []
        while i < len(argv) and not argv[i].startswith('--'):
            out.append(argv[i]); i += 1
        return out
    efdc, fiscal, xmls, js = grupo('--efdc'), grupo('--fiscal'), grupo('--xml'), (grupo('--json') or [''])[0]
    if not efdc or not js:
        print('uso: radar-oportunidades --efdc ARQ.txt [ARQ2.txt ...] [--fiscal SPED.txt ...] [--xml ARQ.xml|PASTA|ARQ.zip ...] --json saida.json')
        return 1
    try:
        res = analisar(efdc, fiscal, xmls)
    except Exception as e:
        res = {'erro': str(e)}
    with open(js, 'w', encoding='utf-8') as f:
        f.write(json.dumps(res, ensure_ascii=False))
    print(json.dumps({'oportunidades': len(res.get('oportunidades', [])), 'total': res.get('total', 0)}))
    return 0 if 'erro' not in res else 1

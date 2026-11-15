# -*- coding: utf-8 -*-
"""Identificador de reduções do IBS e da CBS pelo NCM do produto (LC 214/2025, texto em vigor em 11/2026).

Serve para achar o produto que TEM direito à redução e saiu sem ela (cClassTrib 000001 ou sem o grupo IBS/CBS), e o
contrário: redução aplicada a um NCM que não está no anexo correspondente.

Fontes (texto oficial; conferido o texto atualizado da LC 214/2025 na Câmara dos Deputados em 11/2026):
  • Art. 125 + Anexo I (Cesta Básica Nacional) ........ alíquota zero (100%) · cClassTrib 200003 — lista em efd_lc224_excecoes
  • Art. 148 + Anexo XV (hortícolas, frutas e ovos) .... alíquota zero (100%) · cClassTrib 200014 — lista em efd_lc224_excecoes
  • Art. 147 (tampões, absorventes e coletores menstruais, NCM 9619.00.00) ... alíquota zero · 200013
  • Art. 135 + Anexo VII (alimentos) ................... redução de 60% · 200034
  • Art. 136 + Anexo VIII (higiene pessoal e limpeza) .. redução de 60% · 200035
  • Art. 133 (medicamentos registrados na Anvisa) ...... redução de 60% · 200032; alíquota zero (art. 146, redação da LC
    227/2026) depende da finalidade do medicamento (doenças raras, oncologia, diabetes etc.), não do NCM — por isso o NCM
    garante no mínimo os 60%.
  • Art. 138 + Anexo IX (insumos agropecuários) ........ redução de 60% · 200038 — só os itens em que o NCM é específico;
    a redução vale para o destino agropecuário (não alcança animais domésticos), condição mostrada na tela.
Nos arts. 125, 133, 135, 136 e 148 não há alteração da LC 227/2026. A inclusão de bebidas vegetais no Anexo VII foi vetada
na LC 227/2026 e não está em vigor. Quando a lei mudar, revisar estas listas contra o texto oficial.
"""
import re

import efd_lc224_excecoes as E

_I, _XV, _COND = E._I, E._XV, E._COND

# Anexo VII (60%): (item, nome, prefixos de NCM, exceções por prefixo, condição)
ANEXO_VII = [
    (1, 'Crustáceos e moluscos', ('03061', '03063', '03073100', '03073200', '03074200', '030743', '03075100', '03075200', '03079100', '03079200'),
     ('030611', '03061500', '03063100', '03063400', '03063910'), ''),
    (2, 'Leite fermentado, bebidas e compostos lácteos', ('04032000', '04039000', '22029900'), (), 'lacteo'),
    (3, 'Mel natural', ('04090000',), (), ''),
    (4, 'Farinhas', ('110100', '1102', '1105', '1106', '1208'), (), ''),
    (5, 'Grumos e sêmolas de cereais', ('11031100', '11031900'), (), ''),
    (6, 'Grãos de cereais trabalhados', ('11041', '11042'), (), ''),
    (7, 'Amido de milho', ('11081200',), (), ''),
    (8, 'Óleos vegetais', ('150790', '1508', '1511', '1512', '1513', '1514', '1515'), (), ''),
    (9, 'Massas alimentícias', ('19022000', '19023000'), (), ''),
    (10, 'Sucos naturais de fruta ou hortícola', ('2009',), (), 'sem adição de açúcar e de conservantes'),
    (11, 'Polpas de fruta ou hortícola', ('2008',), (), 'sem adição de açúcar e de conservantes'),
    (12, 'Pão de forma', ('19059010',), (), ''),
    (13, 'Extrato de tomate', ('20029000',), (), ''),
    (14, 'Frutas, hortícolas e demais vegetais', ('07', '08'), ('0711', '0802', '0812', '08140000'), ''),
    (15, 'Cereais, sementes e frutos oleaginosos', ('10', '12'), (), ''),
    (16, 'Hortícolas cozidos ou pré-cozidos', ('2004', '2005', '20021000'), (), ''),
    (17, 'Frutas de casca rija regionais, amendoins e sementes torrados ou cozidos', ('20081',), (), ''),
]
# Anexo VIII (60%) — NCM exato
ANEXO_VIII = {'34011190': (1, 'Sabões de toucador'), '33061000': (2, 'Dentifrícios'), '96032100': (3, 'Escovas de dentes'),
              '48181000': (4, 'Papel higiênico'), '38089419': (5, 'Água sanitária'), '34011900': (6, 'Sabões em barra'),
              '96190000': (7, 'Fraldas e artigos higiênicos semelhantes')}
# Anexo IX (60%) — só os itens com NCM específico; a condição vai junto
ANEXO_IX = [
    (1, 'Biofertilizantes', ('31010000',), 'conforme a legislação específica'),
    (2, 'Fertilizantes (adubos)', ('31', '38249977', '38249979', '38249989'), 'conforme a legislação específica'),
    (6, 'Defensivos agropecuários (fungicidas e herbicidas)', ('380892', '380893'), 'destinados diretamente ao uso agropecuário'),
    (13, 'Aves de um dia', ('01051',), 'exceto ornamentais'),
    (14, 'Embriões e sêmen', ('05111000', '05119'), ''),
    (16, 'Ovos fertilizados', ('04071',), ''),
    (18, 'Rações, suplementos, aditivos, premix ou núcleo', ('230990',), 'não se aplica a animais domésticos'),
]
RX_PEIXE_FORA = re.compile(r'SALM[AÃ]O|SALMON|TRUTA|ATUM|BACALH|HADOQUE|SAITHE', re.I)
RX_NAO_LACTEO = re.compile(r'ENERG|MONST|RED\s*BULL|ISOT[OÔ]N|GATORADE|POWERADE|\bCH[AÁ]\b|REFRI|\bAGUA\b|\bSODA\b|T[OÔ]NICA|GUARAN|COLA\b|H2O', re.I)
RX_LACTEO = re.compile(r'LEIT|LACT|IOGU|YOGU|COALHAD|KEFIR|FERMENT', re.I)
RX_MENSTRUAL = re.compile(r'ABSORV|TAMP[AÃ]O|COLETOR\s+MENST|MENSTRU', re.I)
RX_PAO_FRANCES = re.compile(r'P[AÃ]O\s+(FRANC|DE\s+SAL|CARIOCA)', re.I)


def _so(s):
    return re.sub(r'\D', '', s or '')


def _beneficio(red, anexo, item, nome, artigo, cclass, cond='', certo=None):
    lei = f"LC 214/2025, art. {artigo}" + (f", Anexo {anexo}, item {item}" if anexo and item else (f", Anexo {anexo}" if anexo else ''))
    # certo=False: a redução depende de algo que o NCM não mostra (destino, açúcar, tipo da bebida) — não aponta falta,
    # só aceita a redução quando ela vier no XML
    if certo is None:
        certo = not cond or anexo == '' and artigo == '133'
    return {'red': red, 'anexo': anexo, 'item': item, 'nome': nome, 'artigo': artigo, 'cclass': cclass, 'lei': lei, 'cond': cond, 'certo': certo}


def classifica(ncm, desc=''):
    """Redução que o produto tem pelo NCM (e, em poucos NCM, pela descrição). None = sem redução pelo NCM."""
    n = _so(ncm)
    if len(n) != 8:
        return None
    d = desc or ''
    if n in _I:
        return _beneficio(100, 'I', None, f'Cesta Básica Nacional — {_I[n]}', '125', '200003')
    if E.peixe_0304(n) and not RX_PEIXE_FORA.search(d):
        return _beneficio(100, 'I', None, 'Cesta Básica Nacional — Peixes e carnes de peixe (03.04)', '125', '200003')
    if n in _COND and n == '19059090' and RX_PAO_FRANCES.search(d):
        return _beneficio(100, 'I', None, 'Cesta Básica Nacional — pão francês', '125', '200003')
    if n in _XV:
        return _beneficio(100, 'XV', None, f'Hortícolas, frutas e ovos — {_XV[n]}', '148', '200014')
    if n == '96190000' and RX_MENSTRUAL.search(d):
        return _beneficio(100, '', None, 'Tampões, absorventes e coletores menstruais', '147', '200013')
    if n in ANEXO_VIII:
        it, nome = ANEXO_VIII[n]
        return _beneficio(60, 'VIII', it, f'Higiene pessoal e limpeza — {nome}', '136', '200035')
    for it, nome, pref, exc, cond in ANEXO_VII:
        if n.startswith(pref) and not n.startswith(exc):
            if cond == 'lacteo':
                if n == '22029900' and RX_NAO_LACTEO.search(d) and not RX_LACTEO.search(d):
                    continue                                   # energético, isotônico, chá, refrigerante: fora do Anexo VII
                if n == '22029900' and not RX_LACTEO.search(d):
                    return _beneficio(60, 'VII', it, f'Alimentos — {nome}', '135', '200034', 'só bebidas e compostos lácteos', certo=False)
                cond = ''
            return _beneficio(60, 'VII', it, f'Alimentos — {nome}', '135', '200034', cond)
    if n.startswith(('3003', '3004')):
        return _beneficio(60, '', None, 'Medicamentos registrados na Anvisa (zero se estiver nos critérios do art. 146)', '133', '200032',
                          'registrado na Anvisa ou de farmácia de manipulação')
    for it, nome, pref, cond in ANEXO_IX:
        if n.startswith(pref):
            return _beneficio(60, 'IX', it, f'Insumos agropecuários — {nome}', '138', '200038', cond or 'destino agropecuário')
    return None


# cClassTrib cujos anexos esta tabela cobre: redução nesses códigos com NCM fora do anexo = redução indevida
COBERTOS = {'200003': ('I', 'XV'), '200014': ('XV',), '200034': ('VII',), '200035': ('VIII',), '200013': ('',), '200032': ('',),
            '200038': ('IX',)}


def faixa(red):
    """Faixa da redução para os quadros da tela."""
    r = round(float(red or 0))
    return {0: 'Sem redução', 100: 'Alíquota zero (100%)'}.get(r, f'Redução de {r}%')


if __name__ == '__main__':
    import sys
    for a in sys.argv[1:]:
        print(a, classifica(a))

# -*- coding: utf-8 -*-
"""Auditoria de itens do SPED Fiscal (EFD ICMS/IPI) para o Amazonas — módulo restrito ao Admin.

Duas famílias de verificação, que NUNCA se misturam na tela:

  A) BASE LEGAL (lei, regulamento, Resolução do Senado, Convênio/Ajuste): LC 19/97 art. 12, Res. Senado 22/89 e 13/12,
     Tabela A de origem (Ajustes SINIEF 20/12 e 15/13), Lei 6.108/2022 e Convênio ICMS 142/18.
  B) REGRA OFICIAL DE ESCRITURAÇÃO: Guia Prático da EFD ICMS/IPI (Ato COTEPE/ICMS 44/2018) e RICMS/AM art. 209.

Cada achado traz os dispositivos com o TEXTO LITERAL lido no site oficial (data em LIDO_EM), e cada ocorrência
traz o "motivo" concreto (o que a norma exige × o que o arquivo mostra).
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
CEST_NORM = {re.sub(r'\D', '', k): k for k in LEI_6108_ST}   # '0100100' -> '01.001.00'

LIDO_EM = '07/10/2026'
URL_LC19 = 'https://sistemas.sefaz.am.gov.br/silt/norma/lei-complementar/ac5497ab-4fbd-4bc8-a51b-32405f61dc30/lei-complementar-n-19-de-29-de-dezembro-de-1997'
URL_RICMS = 'https://sistemas.sefaz.am.gov.br/get/Normas.do?metodo=viewDoc&uuidDoc=cc3888c0-e1b9-4433-b513-3c0f29cc625a'
URL_CV142 = 'https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18'
URL_L6108 = 'https://sistemas.sefaz.am.gov.br/get/Normas.do?metodo=viewDoc&uuidDoc=84be7172-451e-4ca0-802e-1a0303e5f0b2'
URL_RS22 = 'https://www2.camara.leg.br/legin/fed/ressen/1989/resolucao-22-19-maio-1989-481183-publicacaooriginal-1-pl.html'
URL_RS13 = 'https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/Congresso/RSF-13-2012.htm'
URL_AJ20_12 = 'https://www.confaz.fazenda.gov.br/legislacao/ajustes/2012/AJ_020_12'
URL_AJ15_13 = 'https://www.confaz.fazenda.gov.br/legislacao/ajustes/2013/AJ_015_13'
URL_AJ07_01 = 'https://www.confaz.fazenda.gov.br/legislacao/ajustes/2001/AJ_007_01'
URL_GUIA = ('https://www.gov.br/sped/pt-br/assuntos/escrituracoes-digitais/efd-icms-ipi/manuais-e-documentos-tecnicos/'
            'guia-pratico-efd-versao-3-2-4.pdf/@@display-file/file')
GUIA = 'Guia Prático da EFD ICMS/IPI v3.2.4 (Ato COTEPE/ICMS 44/2018; Ajuste SINIEF 02/2009)'

# Trechos transcritos LITERALMENTE dos textos oficiais (lidos em LIDO_EM). Texto de lei não tem
# proteção autoral (Lei 9.610/98, art. 8º, IV). Só a redação VIGENTE de cada dispositivo.
D = {
    'lc19_12_I_a': ('LC 19/97, art. 12, I, "a" (redação da LC 116/13)', URL_LC19,
        'a) 25% (vinte e cinco por cento) para automóveis de luxo definidos em Regulamento; iates e outras embarcações ou aeronaves '
        'de esporte, recreação e lazer; armas e munições; jóias e outros artigos de joalheria; álcoois carburantes, gasolinas e gás '
        'natural em qualquer estado ou fase de industrialização, exceto o GLGN; querosene de aviação e energia elétrica;'),
    'lc19_12_I_b': ('LC 19/97, art. 12, I, "b" (redação da LC 244/23, efeitos a partir de 01/04/2023)', URL_LC19,
        'b) 20% (vinte por cento) para as demais mercadorias e serviços, inclusive para o gás liquefeito derivado de gás natural - GLGN, '
        'exceto para o gás liquefeito de petróleo - GLP cuja alíquota é de 18% (dezoito por cento);'),
    'lc19_12_I_c': ('LC 19/97, art. 12, I, "c" (redação da LC 156/15)', URL_LC19,
        'c) 12% (doze por cento) para produtos agrícolas comestíveis produzidos no Estado;'),
    'lc19_12_I_e': ('LC 19/97, art. 12, I, "e" (redação da LC 116/13)', URL_LC19,
        'e) 30% (trinta por cento) para fumo e seus derivados; bebidas alcoólicas, inclusive cervejas e chopes; e serviços de comunicação;'),
    'lc19_12_1_II': ('LC 19/97, art. 12, § 1º, II', URL_LC19,
        '§ 1º Além das hipóteses previstas neste artigo, as alíquotas internas são aplicadas quando: [...] II - o remetente ou o '
        'prestador e o destinatário da mercadoria, bens ou serviços estiverem situados neste Estado;'),
    'lc19_12_II': ('LC 19/97, art. 12, II (redação da LC 156/15)', URL_LC19,
        'II - nas operações e prestações interestaduais, 12% (doze por cento);'),
    'lc19_12_III': ('LC 19/97, art. 12, III (acrescentado pela LC 112/12)', URL_LC19,
        'III - nas operações interestaduais com bens e mercadorias importados do exterior, 4% (quatro por cento), nos termos '
        'estabelecidos em Resolução do Senado Federal.'),
    'lc19_13_I': ('LC 19/97, art. 13, I', URL_LC19,
        'Art. 13. A base de cálculo do imposto é: I - na saída de mercadoria prevista nos incisos I, III e IV do art. 7º, o valor da operação;'),
    'rs22_1': ('Resolução do Senado Federal nº 22/1989, art. 1º e parágrafo único', URL_RS22,
        'Art. 1º. A alíquota do Imposto [...] nas operações e prestações interestaduais, será de doze por cento. Parágrafo único. '
        'Nas operações e prestações realizadas nas Regiões Sul e Sudeste, destinadas às Regiões Norte, Nordeste e Centro-Oeste e ao '
        'Estado do Espírito Santo, as alíquotas serão: I - em 1989, oito por cento; II - a partir de 1990, sete por cento.'),
    'rs13_1': ('Resolução do Senado Federal nº 13/2012, art. 1º, caput e § 1º', URL_RS13,
        'Art. 1º A alíquota do [ICMS], nas operações interestaduais com bens e mercadorias importados do exterior, será de 4% (quatro '
        'por cento). § 1º O disposto neste artigo aplica-se aos bens e mercadorias importados do exterior que, após seu desembaraço '
        'aduaneiro: I - não tenham sido submetidos a processo de industrialização; II - ainda que submetidos a qualquer processo de '
        'transformação, beneficiamento, montagem, acondicionamento, reacondicionamento, renovação ou recondicionamento, resultem em '
        'mercadorias ou bens com Conteúdo de Importação superior a 40% (quarenta por cento).'),
    'rs13_4': ('Resolução do Senado Federal nº 13/2012, art. 1º, § 4º, e art. 2º', URL_RS13,
        '§ 4º O disposto nos §§ 1º e 2º não se aplica: I - aos bens e mercadorias importados do exterior que não tenham similar '
        'nacional, a serem definidos em lista a ser editada pelo Conselho de Ministros da Câmara de Comércio Exterior (Camex) para os '
        'fins desta Resolução; II - aos bens produzidos em conformidade com os processos produtivos básicos de que tratam o '
        'Decreto-Lei nº 288, de 28 de fevereiro de 1967, e as Leis nºs 8.248 [...], 8.387 [...], 10.176 [...] e 11.484 [...]. '
        'Art. 2º O disposto nesta Resolução não se aplica às operações que destinem gás natural importado do exterior a outros Estados.'),
    'aj20_12': ('Ajuste SINIEF 20/2012 e Ajuste SINIEF 15/2013 — Tabela A (Origem) do Convênio s/nº de 1970', URL_AJ20_12,
        '0 - Nacional, exceto as indicadas nos códigos 3, 4, 5 e 8; 1 - Estrangeira - Importação direta, exceto a indicada no código 6; '
        '2 - Estrangeira - Adquirida no mercado interno, exceto a indicada no código 7; 3 - Nacional, mercadoria ou bem com Conteúdo de '
        'Importação superior a 40% (quarenta por cento) e inferior ou igual a 70% (setenta por cento); 4 - Nacional, cuja produção tenha '
        'sido feita em conformidade com os processos produtivos básicos de que tratam o Decreto-Lei nº 288/67, e as Leis nºs 8.248/91, '
        '8.387/91, 10.176/01 e 11.484/07; 5 - Nacional, mercadoria ou bem com Conteúdo de Importação inferior ou igual a 40% (quarenta '
        'por cento); 6 - Estrangeira - Importação direta, sem similar nacional, constante em lista de Resolução CAMEX; 7 - Estrangeira - '
        'Adquirida no mercado interno, sem similar nacional, constante em lista de Resolução CAMEX; 8 - Nacional, mercadoria ou bem com '
        'Conteúdo de Importação superior a 70% (setenta por cento).'),
    'l6108_1': ('Lei 6.108/2022 (AM), art. 1º', URL_L6108,
        'Art. 1º A exigência de recolhimento do ICMS devido por substituição tributária em relação às operações subsequentes e por '
        'antecipação com encerramento de tributação, na forma estabelecida no inciso II do caput do artigo 25 e no artigo 25-C da Lei '
        'Complementar nº 19, de 29 de dezembro de 1997, que instituiu o Código Tributário do Estado do Amazonas, se aplica às '
        'mercadorias relacionadas nos Anexos II a XXVI desta Lei.'),
    'l6108_4': ('Lei 6.108/2022 (AM), art. 4º, I', URL_L6108,
        'Art. 4º Fica o Poder Executivo autorizado a: I - excluir do regime de substituição tributária e de antecipação com '
        'encerramento de tributação quaisquer das mercadorias constantes nos Anexos II a XXVI desta Lei;'),
    'cv142_20': ('Convênio ICMS 142/2018 (CONFAZ), cláusula vigésima, I, e § 3º', URL_CV142,
        'Cláusula vigésima O documento fiscal emitido nas operações com bens e mercadorias listados nos Anexos II a XXVI deste convênio, '
        'conterá, além das demais indicações exigidas pela legislação, as seguintes informações: I - o CEST de cada bem e mercadoria, '
        'ainda que a operação não esteja sujeita ao regime de substituição tributária; [...] § 3º A inobservância do disposto no caput '
        'desta cláusula implica exigência do imposto nos termos que dispuser a legislação da unidade federada de destino.'),
    'ricms_209': ('RICMS/AM (Decreto 20.686/99), art. 209 (redação do Decreto 33.055/12)', URL_RICMS,
        'Art. 209. Ficam adotados o Código de Situação Tributária - CST e o Código Fiscal de Operação e Prestação - CFOP, constantes dos '
        'anexos do Convênio s/nº, de 15 de dezembro de 1970, para serem aplicados aos documentos fiscais conforme sejam exigidos.'),
    'aj07_01': ('Ajuste SINIEF 07/2001 — Tabela CFOP do Convênio s/nº de 1970 (grupos)', URL_AJ07_01,
        '1.000 - ENTRADAS OU AQUISIÇÕES DE SERVIÇOS DO ESTADO [...] 2.000 - ENTRADAS OU AQUISIÇÕES DE SERVIÇOS DE OUTROS ESTADOS [...] '
        '3.000 - ENTRADAS OU AQUISIÇÕES DE SERVIÇOS DO EXTERIOR [...] 5.000 - SAÍDAS OU PRESTAÇÕES DE SERVIÇOS PARA O ESTADO [...] '
        '6.000 - SAÍDAS OU PRESTAÇÕES DE SERVIÇOS PARA OUTROS ESTADOS [...] 7.000 - SAÍDAS OU PRESTAÇÕES DE SERVIÇOS PARA O EXTERIOR'),
    'guia_c170_11': (GUIA + ', Registro C170, Campo 11 (CFOP)', URL_GUIA,
        'Se o campo IND_OPER do registro C100 for igual a “0” (zero), então o primeiro caractere do CFOP deve ser igual a 1, 2 ou 3. '
        'Se campo IND_OPER do registro C100 for igual a “1” (um), então o primeiro caractere do CFOP deve ser igual a 5, 6 ou 7. '
        'O primeiro caractere deve ser o mesmo para todos os itens de um documento fiscal.'),
    'guia_c170_10a': (GUIA + ', Registro C170, Campo 10 (CST_ICMS), regra "a"', URL_GUIA,
        'Outras regras a serem executadas somente nas operações de saídas: ICMS Normal: a) se os dois últimos dígitos deste campo forem '
        'iguais a 30, 40, 41, 50, ou 60, então os valores dos campos VL_BC_ICMS, ALIQ_ICMS e VL_ICMS deverão ser iguais a “0” (zero);'),
    'guia_c170_10b': (GUIA + ', Registro C170, Campo 10 (CST_ICMS), regras "b" e "c"', URL_GUIA,
        'b) se os dois últimos dígitos deste campo forem diferentes de 30, 40, 41, 50, e 60, então os valores dos campos VL_BC_ICMS, '
        'ALIQ_ICMS e VL_ICMS deverão ser maiores que “0” (zero); c) se os dois últimos dígitos deste campo forem iguais a 20, 51 ou 90, '
        'então os valores dos campos VL_BC_ICMS, ALIQ_ICMS e VL_ICMS deverão ser maiores ou iguais a “0” (zero).'),
    'guia_c190_6_7': (GUIA + ', Registro C190, Campos 06 e 07', URL_GUIA,
        'Campo 06 (VL_BC_ICMS) [...] Validação: o valor constante neste campo deve corresponder à soma dos valores do Campo VL_BC_ICMS '
        'dos registros C170 (itens), se existirem, que possuam a mesma combinação de CST, CFOP e Alíquota deste registro. Campo 07 '
        '(VL_ICMS) [...] Validação: o valor constante neste campo deve corresponder à soma dos valores do campo VL_ICMS do registro C170 '
        '(itens), se existirem, que possuam a mesma combinação de CST, CFOP e Alíquota deste registro.'),
    'guia_e110_2': (GUIA + ', Registro E110, Campo 02 (VL_TOT_DEBITOS)', URL_GUIA,
        'Validação: o valor informado deve corresponder ao somatório de todos os documentos fiscais de saída que geram débito de ICMS. '
        '[...] O valor neste campo deve ser igual à soma dos VL_ICMS de todos os registros C190, C320, C390, C490, C590, C690, C790, '
        'C850, C890, D190, D300, D390, D410, D590, D690, D696, D730, D760 [...]'),
    'guia_e110_6': (GUIA + ', Registro E110, Campo 06 (VL_TOT_CREDITOS)', URL_GUIA,
        'Validação: o valor informado deve corresponder ao somatório de todos os documentos fiscais de entrada que geram crédito de ICMS. '
        'O valor neste campo deve ser igual à soma dos VL_ICMS de todos os registros C190, C590, D190, D590, D730. [...]'),
}


def _disp(*chaves):
    return [{'ref': D[k][0], 'url': D[k][1], 'texto': D[k][2]} for k in chaves]


def _base(norma, resumo, chaves, nao_conferido, status='lida'):
    disp = _disp(*chaves)
    links = []
    for d in disp:
        if d['url'] not in links:
            links.append(d['url'])
    return {'status': status, 'norma': norma, 'resumo': resumo, 'dispositivos': disp, 'links': links,
            'lido_em': LIDO_EM, 'nao_conferido': nao_conferido}


NC_BENEF = ('Reduções de base de cálculo, isenções e benefícios do RICMS/AM e de Convênios ICMS ainda não foram cruzados item a item: '
            'uma alíquota "fora da lista" pode ter justificativa em benefício específico. Empresas do Simples Nacional usam CSOSN nas saídas.')

BASE = {
    'aliq_interna': _base(
        'LC 19/97 (Código Tributário do AM), art. 12, I, alíneas "a", "b", "c" e "e", e § 1º, II',
        'Nas operações internas a lei só prevê 12%, 18% (GLP), 20% (regra geral desde 01/04/2023), 25% e 30%. '
        'Uma saída interna tributada com outra alíquota não encontra amparo no art. 12, I.',
        ['lc19_12_I_b', 'lc19_12_I_a', 'lc19_12_I_c', 'lc19_12_I_e', 'lc19_12_1_II'], NC_BENEF),
    'aliq_est_fora': _base(
        'LC 19/97, art. 12, II e III',
        'Nas saídas interestaduais a lei do AM prevê 12% (regra) e 4% (importados, nos termos da Resolução do Senado). '
        'Qualquer outra alíquota não encontra amparo no art. 12.',
        ['lc19_12_II', 'lc19_12_III'], NC_BENEF),
    'aliq_est_7': _base(
        'Resolução do Senado Federal nº 22/1989, art. 1º, parágrafo único; LC 19/97, art. 12, II',
        'A alíquota de 7% só existe para remetentes das Regiões Sul e Sudeste que vendem para Norte, Nordeste, Centro-Oeste e ES. '
        'O Amazonas está na Região Norte: a saída interestadual de um estabelecimento do AM é de 12% (ou 4% para importados).',
        ['rs22_1', 'lc19_12_II'], NC_BENEF),
    'aliq_est_4_nacional': _base(
        'Resolução do Senado Federal nº 13/2012, art. 1º e § 4º; Tabela A de origem (Ajustes SINIEF 20/2012 e 15/2013); LC 19/97, art. 12, III',
        'A alíquota de 4% é só para importados (origem 1 ou 2) ou para nacionais com Conteúdo de Importação acima de 40% (origem 3 ou 8). '
        'Origens 0, 4 e 5 são nacionais; 6 e 7 (sem similar, lista CAMEX) e os bens de PPB/Zona Franca (Decreto-Lei 288/67) estão fora '
        'da regra pelo § 4º. Item nessas origens com 4% indica alíquota menor que a devida (12%).',
        ['rs13_1', 'rs13_4', 'aj20_12', 'lc19_12_III'],
        'A origem é a informada no próprio arquivo (1º dígito do CST). Se a origem estiver errada no cadastro, o erro é a origem, não a alíquota.'),
    'aliq_est_12_importado': _base(
        'Resolução do Senado Federal nº 13/2012, art. 1º; Tabela A de origem (Ajustes SINIEF 20/2012 e 15/2013); LC 19/97, art. 12, III',
        'Item com origem 1, 2, 3 ou 8 (importado ou com Conteúdo de Importação acima de 40%) em saída interestadual deveria sair a 4%. '
        'Com 12% o contribuinte pagou a mais (e o destinatário pode ter crédito glosado no destino).',
        ['rs13_1', 'rs13_4', 'aj20_12', 'lc19_12_III'],
        'Exceções do art. 2º (gás natural) e conferência da FCI/Conteúdo de Importação não foram feitas; a origem é a informada no arquivo.'),
    'st_normal': _base(
        'Lei 6.108/2022 (AM), art. 1º e Anexos II a XXVI (lista por CEST/NCM)',
        'Mercadoria relacionada nos Anexos II a XXVI está sujeita à ST com encerramento de tributação no AM. '
        'Venda interna dessa mercadoria com CST 00/20 (tributação normal) sugere que a ST não foi observada.',
        ['l6108_1', 'l6108_4'],
        'O art. 4º autoriza o Executivo a excluir mercadorias da ST (atos de exclusão não pesquisados), e a regra pode não alcançar '
        'quem é o próprio substituto/industrial. Convênios e Protocolos ICMS específicos ainda não foram cruzados.'),
    'st_cadastro': _base(
        'Convênio ICMS 142/2018, cláusula vigésima, I e § 3º; Lei 6.108/2022, Anexos II a XXVI (CEST/NCM)',
        'O documento fiscal com mercadoria listada deve informar o CEST de cada item, mesmo fora da ST; sem ele, o destino pode exigir o imposto.',
        ['cv142_20', 'l6108_1'],
        'Um mesmo NCM pode ter vários CEST (por embalagem, por exemplo); o sistema só indica o(s) candidato(s). O Convênio ICMS 52/17 não foi lido.'),
    'st_fora_lista': _base(
        'Lei 6.108/2022 (AM), art. 1º e Anexos II a XXVI',
        'Item com CST de ST (10/30/60/70) cujo NCM não aparece nos anexos da Lei 6.108/2022 e sem CEST no cadastro.',
        ['l6108_1'],
        'A ST também pode decorrer de Convênio/Protocolo ICMS (ainda não cruzados). Por isso é só "verificar".'),
    'arq_cfop_oper': _base(
        GUIA + ', Registro C170, Campo 11; RICMS/AM, art. 209; Ajuste SINIEF 07/2001',
        'O 1º dígito do CFOP define a direção (1/2/3 entrada; 5/6/7 saída) e precisa bater com o IND_OPER da nota.',
        ['guia_c170_11', 'ricms_209', 'aj07_01'],
        'Regra de escrituração (o validador oficial também a aplica). Não avalia se o CFOP escolhido é o adequado à natureza da operação.'),
    'arq_cst_com_icms': _base(
        GUIA + ', Registro C170, Campo 10 (CST_ICMS), regra "a"; RICMS/AM, art. 209',
        'Nas saídas, CST terminado em 30, 40, 41, 50 ou 60 não pode ter base, alíquota nem ICMS.',
        ['guia_c170_10a', 'ricms_209'],
        'Só saídas (como manda o Guia). Não avalia se o CST escolhido é o correto para o produto.'),
    'arq_cst_sem_valor': _base(
        GUIA + ', Registro C170, Campo 10 (CST_ICMS), regras "b" e "c"; RICMS/AM, art. 209',
        'Nas saídas, CST terminado em 00, 10 ou 70 exige base, alíquota e ICMS maiores que zero (20, 51 e 90 podem ser zero).',
        ['guia_c170_10b', 'ricms_209'],
        'Só saídas (como manda o Guia). Empresa do Simples Nacional usa CSOSN e não entra nesta regra.'),
    'arq_c170_c190': _base(
        GUIA + ', Registro C190, Campos 06 e 07',
        'Para cada combinação CST × CFOP × alíquota, a base e o ICMS do C190 devem ser a soma exata dos itens (C170) da nota.',
        ['guia_c190_6_7'], 'Tolerância de R$ 0,10 por arredondamento.'),
    'arq_calculo': _base(
        'LC 19/97, art. 12 (alíquota) e art. 13, I (base de cálculo)',
        'O imposto do item resulta da alíquota do art. 12 aplicada sobre a base do art. 13. ICMS diferente de base × alíquota '
        'indica erro de cálculo ou de preenchimento.',
        ['lc19_13_I', 'lc19_12_I_b'],
        'A lei não traz a fórmula em uma frase só: é a aplicação direta dos arts. 12 e 13. Tolerância de centavos por arredondamento.',
        status='indireta'),
    'conc_debitos': _base(GUIA + ', Registro E110, Campo 02', 'Total de débitos do E110 = soma do ICMS dos C190 de saída (e demais registros listados).',
                          ['guia_e110_2'], 'Só os C190 entram nesta conferência; D190, C590 etc. explicam diferenças.'),
    'conc_creditos': _base(GUIA + ', Registro E110, Campo 06', 'Total de créditos do E110 = soma do ICMS dos C190 de entrada (e demais registros listados).',
                           ['guia_e110_6'], 'Só os C190 entram nesta conferência; D190, C590 etc. explicam diferenças.'),
}
BASE['aliq_interestadual'] = BASE['aliq_est_fora']   # compatibilidade

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



def _pct(v):
    return (f'{v:.2f}'.rstrip('0').rstrip('.').replace('.', ',')) + '%'


ORIG_IMPORT = {'1', '2', '3', '8'}
ORIG_DESC = {'0': 'nacional', '1': 'estrangeira, importação direta', '2': 'estrangeira, adquirida no mercado interno',
             '3': 'nacional com Conteúdo de Importação > 40% e ≤ 70%', '4': 'nacional produzida conforme PPB (DL 288/67 e leis)',
             '5': 'nacional com Conteúdo de Importação ≤ 40%', '6': 'estrangeira sem similar (CAMEX), importação direta',
             '7': 'estrangeira sem similar (CAMEX), mercado interno', '8': 'nacional com Conteúdo de Importação > 70%'}


def _aliq_interna(A, aliq, bc, pos_2023, ex, c190=False):
    ant = aliq == 17.0 and pos_2023
    regra = 'aliq_interna_c190' if c190 else 'aliq_interna'
    titulo = ('Saídas internas (C190) com alíquota fora das previstas em lei' if c190
              else 'Alíquota interna fora das alíquotas previstas em lei')
    a = A(regra, 'A', titulo, 'Alta' if ant else 'Média',
          'Saída interna tributada com alíquota que não é nenhuma das previstas no art. 12, I, da LC 19/97 (12%, 18%, 20%, 25%, 30%).'
          + (' Há itens com 17%, alíquota geral ANTERIOR a 01/04/2023.' if ant else ''), 'aliq_interna',
          'Confira se há benefício/redução que justifique; se não houver, a alíquota geral é 20% (art. 12, I, "b").')
    dif = max(0.0, bc * (20 - aliq) / 100) if ant else 0.0
    mot = (f'Saída interna com {_pct(aliq)}; o art. 12, I, da LC 19/97 só prevê 12%, 18%, 20%, 25% ou 30%.'
           + (f' Pela regra geral de 20% (alínea "b"), a diferença seria {_brl(dif)}.' if ant else ''))
    a.add(dif, dict(ex, motivo=mot))


def _aliq_interestadual(A, aliq, bc, orig, ex):
    if aliq == 7.0:
        a = A('aliq_est_7', 'A', 'Saída interestadual a 7% por estabelecimento do Amazonas', 'Alta',
              'A alíquota de 7% é exclusiva de remetentes do Sul/Sudeste (Res. Senado 22/89). Para quem está no AM a saída '
              'interestadual é 12% (ou 4% para importados).', 'aliq_est_7',
              'Confira a origem do item: se importado, a alíquota é 4%; se nacional, 12%.')
        dev = 4.0 if orig in ORIG_IMPORT else 12.0
        dif = max(0.0, bc * (dev - aliq) / 100)
        a.add(dif, dict(ex, motivo=f'Remetente no AM (Região Norte) usou 7%. Com origem {orig or "?"} '
                                   f'({ORIG_DESC.get(orig, "não informada")}), a alíquota legal seria {_pct(dev)}'
                                   + (f'; diferença de {_brl(dif)}.' if dif else '.')))
    elif aliq not in (4.0, 12.0):
        a = A('aliq_est_fora', 'A', 'Alíquota interestadual fora de 4% ou 12%', 'Alta',
              'Saída interestadual tributada com alíquota que não é 12% (art. 12, II) nem 4% (art. 12, III, importados).',
              'aliq_est_fora', 'Confira a UF de destino, a origem do item e se a operação é mesmo interestadual.')
        a.add(0.0, dict(ex, motivo=f'Saída interestadual com {_pct(aliq)}; a LC 19/97 só prevê 12% (art. 12, II) ou 4% (art. 12, III).'))
    elif aliq == 4.0 and orig and orig not in ORIG_IMPORT:
        dif = max(0.0, bc * 8 / 100)
        a = A('aliq_est_4_nacional', 'A', 'Alíquota de 4% em item que não é importado', 'Alta',
              'A alíquota de 4% só cabe a importados (origem 1/2) ou com Conteúdo de Importação acima de 40% (origem 3/8). '
              'O item tem origem nacional, sem similar (CAMEX) ou de PPB.', 'aliq_est_4_nacional',
              'Confira a origem no cadastro do produto e a FCI. Se a origem estiver certa, a alíquota é 12%.')
        a.add(dif, dict(ex, motivo=f'4% com origem {orig} ({ORIG_DESC.get(orig, "?")}); a Res. Senado 13/2012 não alcança essa origem. '
                                   f'A 12%, a diferença seria {_brl(dif)}.'))
    elif aliq == 12.0 and orig in ORIG_IMPORT:
        a = A('aliq_est_12_importado', 'A', 'Item importado em saída interestadual a 12% (deveria ser 4%)', 'Média',
              'Item com origem estrangeira ou com Conteúdo de Importação acima de 40% saiu para outra UF a 12%, '
              'quando a Res. Senado 13/2012 fixa 4%.', 'aliq_est_12_importado',
              'Confira a origem e a FCI. Se o item for de fato importado, a alíquota correta é 4% (o contribuinte pagou a mais).')
        a.add(0.0, dict(ex, motivo=f'Origem {orig} ({ORIG_DESC.get(orig, "?")}) com 12%; a Res. Senado 13/2012, art. 1º, fixa 4% '
                                   f'(ICMS a maior de {_brl(bc * 8 / 100)}).'))

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
        c170_na_nota = False
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
                c170_na_nota = False
                continue
            if cod_sit in CANC:
                continue
            if r == 'C170' and len(c) > 15:
                cob['itens'] += 1
                c170_na_nota = True
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
                orig = c[10][:1] if len(c[10]) == 3 else ''
                ex['origem'] = orig
                trib = cst in ('00', '10', '20', '70')
                # B1: cálculo (LC 19/97 arts. 12 e 13)
                if aliq > 0 and bc > 0 and abs(round(bc * aliq / 100, 2) - icms) > max(0.05, bc * 0.0005):
                    esp = round(bc * aliq / 100, 2)
                    a = A('arq_calculo', 'B', 'ICMS do item diferente de base × alíquota', 'Média',
                          'No registro C170 o valor do ICMS não bate com a base multiplicada pela alíquota (tolerância de centavos).',
                          'arq_calculo', 'Confira no sistema de origem a base e a alíquota do item.')
                    a.add(abs(esp - icms), dict(ex, esperado=esp, motivo=f'{_brl(bc)} × {_pct(aliq)} = {_brl(esp)}, mas o item traz ICMS de {_brl(icms)}.'))
                # B2: CST × valores (Guia Prático, C170 campo 10, regras a/b/c — só saídas)
                if saida and cst in ('00', '10', '70') and vl_item > 0 and (bc <= 0 or aliq <= 0 or icms <= 0):
                    a = A('arq_cst_sem_valor', 'B', 'CST tributado (00/10/70) sem base, alíquota ou ICMS', 'Média',
                          'Saída com CST 00, 10 ou 70 em que base, alíquota ou ICMS está zerado. O Guia Prático exige os três maiores que zero.',
                          'arq_cst_sem_valor', 'Verifique se o CST correto seria isento/não tributado/ST (40, 41, 60...) ou se faltou preencher o ICMS.')
                    a.add(vl_item, dict(ex, motivo=f'CST {cst} na saída exige base, alíquota e ICMS > 0; o item tem base {_brl(bc)}, alíquota {_pct(aliq)} e ICMS {_brl(icms)}.'))
                if saida and cst in ('30', '40', '41', '50', '60') and (bc > 0 or aliq > 0 or icms > 0):
                    a = A('arq_cst_com_icms', 'B', 'CST sem tributação própria (30/40/41/50/60) com base ou ICMS', 'Média',
                          'Saída com CST 30, 40, 41, 50 ou 60 trazendo base, alíquota ou ICMS. O Guia Prático exige os três iguais a zero.',
                          'arq_cst_com_icms', 'Revise o CST ou os valores de ICMS lançados no item.')
                    a.add(icms, dict(ex, motivo=f'CST {cst} na saída exige base, alíquota e ICMS = 0; o item tem base {_brl(bc)}, alíquota {_pct(aliq)} e ICMS {_brl(icms)}.'))
                # B3: CFOP × operação (Guia Prático, C170 campo 11)
                if (ind_oper == '0' and cfop[:1] in '567') or (ind_oper == '1' and cfop[:1] in '123'):
                    a = A('arq_cfop_oper', 'B', 'CFOP incompatível com entrada/saída da nota', 'Alta',
                          'O primeiro dígito do CFOP (1/2/3 = entrada; 5/6/7 = saída) não combina com o IND_OPER da nota (C100).',
                          'arq_cfop_oper', 'Corrija o CFOP ou o indicador de operação.')
                    a.add(0.0, dict(ex, motivo=f'Nota de {"entrada" if ind_oper == "0" else "saída"} (IND_OPER {ind_oper}) com CFOP {cfop}, que é de {"saída" if cfop[:1] in "567" else "entrada"}.'))
                # A1: alíquota interna (LC 19/97, art. 12, I)
                if saida and interna and trib and aliq > 0 and aliq not in ALIQ_INT_OK:
                    _aliq_interna(A, aliq, bc, pos_2023, ex)
                # A2: interestadual (LC 19/97 art. 12 II/III; Res. Senado 22/89 e 13/12)
                if saida and cfop[:1] == '6' and trib and aliq > 0:
                    _aliq_interestadual(A, aliq, bc, orig, ex)
                # A3: ST — item da lista vendido com tributação normal (Lei 6.108/2022)
                cests = [CEST_NORM[cest]] if cest in CEST_NORM else (_ncm_st(ncm) if ncm else [])
                na_lista = bool(cests)
                if saida and na_lista and cst in ('00', '20') and cfop in ('5101', '5102', '5108'):
                    anexo, seg = (LEI_6108_ST[cests[0]][0], LEI_6108_ST[cests[0]][1]) if cests[0] in LEI_6108_ST else ('', '')
                    a = A('st_normal', 'A', 'Item da lista de ST vendido com tributação normal', 'Média',
                          'CEST/NCM do item consta nos Anexos da Lei 6.108/2022 (ST), mas a saída foi tributada normalmente (CST 00/20).',
                          'st_normal', 'Confirme se o contribuinte é o substituído (então a venda deveria sair com CST 60 / CFOP 5.405) '
                                       'ou se há exclusão/regra que mantenha a tributação normal.')
                    a.add(icms, dict(ex, anexo=anexo, segmento=seg, cest_lista=cests[0],
                                     motivo=f'NCM {ncm or "-"} / CEST {cests[0]} está no Anexo {anexo} da Lei 6.108/2022 ({seg}); saída com CST {cst} e CFOP {cfop}.'))
                # A5: ST no CST mas fora da lista
                if cst in ('60', '10', '30', '70') and ncm and not na_lista and not cest:
                    a = A('st_fora_lista', 'A', 'CST de ST em item que não está na lista da Lei 6.108/2022', 'Baixa',
                          'O item usa CST de substituição tributária, mas seu NCM não aparece nos anexos lidos e o CEST não está no cadastro.',
                          'st_fora_lista', 'Confirme a origem da ST (Convênio/Protocolo) e preencha o CEST no cadastro.')
                    a.add(0.0, dict(ex, motivo=f'CST {cst} (ST) com NCM {ncm}, que não consta nos Anexos II a XXVI da Lei 6.108/2022.'))
            elif r == 'C190' and len(c) > 7:
                cob['c190'] += 1
                k = (c[2], c[3], _n(c[4]))
                v = c190.setdefault(k, [0.0, 0.0, 0.0, 0.0])
                v[0] += _n(c[5]); v[1] += _n(c[6]); v[2] += _n(c[7]); v[3] += 1
                cfop = c[3]
                aliq = _n(c[4]); cst = c[2][-2:]
                if ind_oper == '1' or cfop[:1] in '567':
                    # A1/A2 também sobre C190 (notas de saída sem C170)
                    exr = {'nota': num, 'cst': c[2], 'origem': c[2][:1] if len(c[2]) == 3 else '', 'cfop': cfop, 'aliq': aliq,
                           'bc': _n(c[6]), 'icms': _n(c[7])}
                    if cfop[:1] == '5' and cst in ('00', '10', '20', '70') and aliq > 0 and aliq not in ALIQ_INT_OK and not c170_na_nota:
                        _aliq_interna(A, aliq, _n(c[6]), pos_2023, exr, c190=True)
                    if cfop[:1] == '6' and cst in ('00', '10', '20', '70') and aliq > 0 and not c170_na_nota:
                        _aliq_interestadual(A, aliq, _n(c[6]), exr['origem'], exr)
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
                a.add(0.0, {'cod': cod, 'descr': p['descr'][:60], 'ncm': p['ncm'], 'cest_candidatos': cands[:4], 'qtd_candidatos': len(cands),
                           'motivo': f'NCM {p["ncm"]} consta nos Anexos da Lei 6.108/2022 (CEST possível: {", ".join(cands[:3])}); o 0200 não traz CEST.'})

    # B4: C170 × C190 por (CST, CFOP, alíquota)
    for k, (bc, icms) in c170_soma.items():
        v = c190.get(k)
        if v is not None and (abs(v[1] - bc) > 0.10 or abs(v[2] - icms) > 0.10):
            a = A('arq_c170_c190', 'B', 'Soma dos itens (C170) diferente do resumo (C190)', 'Alta',
                  'Para a mesma combinação CST × CFOP × alíquota, as somas de base e ICMS dos itens não fecham com o resumo analítico.', 'arq_c170_c190',
                  'Revise a geração do arquivo: itens e totais devem fechar.')
            a.add(abs(v[2] - icms), {'cst': k[0], 'cfop': k[1], 'aliq': k[2], 'bc_itens': round(bc, 2), 'bc_c190': round(v[1], 2),
                                     'icms_itens': round(icms, 2), 'icms_c190': round(v[2], 2),
                                     'motivo': f'CST {k[0]} × CFOP {k[1]} × {_pct(k[2])}: itens somam base {_brl(bc)} e ICMS {_brl(icms)}; '
                                               f'o C190 declara base {_brl(v[1])} e ICMS {_brl(v[2])}.'})
    # B5: E110 × C190
    info = []
    if 'e110_deb' in tot:
        dd = tot['e110_deb'] - tot['deb_c190']
        info.append({'titulo': 'Débitos: E110 × saídas (C190)', 'e110': round(tot['e110_deb'], 2), 'c190': round(tot['deb_c190'], 2),
                     'dif': round(dd, 2), 'base_legal': BASE['conc_debitos'],
                     'nota': 'O Guia manda somar também C590, D190, D590 e outros: a diferença pode estar nesses registros (ou em extemporâneos). Só indica onde olhar.'})
        dc = tot['e110_cred'] - tot['cred_c190']
        info.append({'titulo': 'Créditos: E110 × entradas (C190)', 'e110': round(tot['e110_cred'], 2), 'c190': round(tot['cred_c190'], 2),
                     'dif': round(dc, 2), 'base_legal': BASE['conc_creditos'],
                     'nota': 'Idem: C590, D190, D590 e D730 também compõem o total; extemporâneos entram no primeiro período.'})

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
        'lido_em': LIDO_EM,
        'fontes': [{'ref': v[0], 'url': v[1]} for v in D.values()],
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

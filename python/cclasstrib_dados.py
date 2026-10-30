# -*- coding: utf-8 -*-
"""Tabela oficial cClassTrib do IBS/CBS (Informe Técnico 2025.002, v1.70, atualizada em 2026-10-01).
Gerado por tools/gerar_cclasstrib.py — não editar à mão."""
VERSAO = 'v1.70'
ATUALIZACAO = '2026-10-01'
CST = {'000': 'Tributação integral',
 '010': 'Tributação com alíquotas uniformes',
 '011': 'Tributação com alíquotas uniformes reduzidas',
 '200': 'Alíquota reduzida',
 '220': 'Alíquota fixa',
 '221': 'Alíquota fixa proporcional',
 '222': 'Redução de base de cálculo',
 '400': 'Isenção',
 '410': 'Imunidade e não incidência',
 '510': 'Diferimento',
 '515': 'Diferimento com redução de alíquota',
 '550': 'Suspensão',
 '620': 'Tributação monofásica',
 '800': 'Transferência de crédito',
 '810': 'Ajuste de IBS na ZFM',
 '811': 'Ajustes',
 '820': 'Tributação em documento específico',
 '830': 'Exclusão de base de cálculo'}
CCLASS = {'000001': {'artigo': '',
            'cst': '000',
            'cst_desc': 'Tributação integral',
            'cte': 1,
            'desc': 'Situações tributadas integralmente pelo IBS e CBS.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Situações tributadas integralmente pelo IBS e CBS.',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': '',
            'tipo': 'Padrão'},
 '000002': {'artigo': 'Art. 11, VIII',
            'cst': '000',
            'cst_desc': 'Tributação integral',
            'cte': 0,
            'desc': 'Exploração de via, observado o art. 11 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Exploração de via',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 11. Considera-se local da operação com: VIII - serviço de exploração de via, mediante cobrança de valor a '
                     'qualquer título, incluindo tarifas, pedágios e quaisquer outras formas de cobrança, o território de cada Município e '
                     'Estado, ou do Distrito Federal, proporcionalmente à correspondente extensão da via explorada',
            'tipo': 'Padrão'},
 '000003': {'artigo': 'Art. 311',
            'cst': '000',
            'cst_desc': 'Tributação integral',
            'cte': 0,
            'desc': 'Regime automotivo - projetos incentivados, observado o art. 311 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Regime automotivo - projetos incentivados (art. 311)',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 311. Em relação aos projetos habilitados à fruição dos benefícios estabelecidos pelo art. 11-C da Lei nº 9.440, '
                     'de 14 de março de 1997, o crédito presumido de que trata o art. 309 desta Lei Complementar será calculado mediante a '
                     'aplicação dos seguintes percentuais sobre o valor das vendas no mercado interno, em cada mês, dos produtos '
                     'constantes nos projetos de que trata o art. 309, fabricados ou montados nos estabelecimentos incentivados:',
            'tipo': 'Padrão'},
 '000004': {'artigo': 'Art. 312',
            'cst': '000',
            'cst_desc': 'Tributação integral',
            'cte': 0,
            'desc': 'Regime automotivo - projetos incentivados, observado o art. 312 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Regime automotivo - projetos incentivados (art. 312)',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 312. Em relação aos projetos habilitados à fruição dos benefícios estabelecidos pelos arts. 1º a 4º da Lei nº '
                     '9.826, de 23 de agosto de 1999, o crédito presumido de que trata o art. 309 desta Lei Complementar corresponderá ao '
                     'produto da multiplicação dos seguintes fatores:',
            'tipo': 'Padrão'},
 '000005': {'artigo': 'Art. 179, I',
            'cst': '000',
            'cst_desc': 'Tributação integral',
            'cte': 0,
            'desc': 'Operação com EAC destinado à mistura com gasolina A, mas com saída do biocombustível com destinação diversa, '
                    'observado o art. 179 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Operação com EAC destinado à mistura com gasolina A, mas com saída do biocombustível com destinação diversa',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 179. Nas operações com EAC: I - o adquirente de EAC destinado à mistura com gasolina A que realizar a saída dos '
                     'biocombustíveis com destinação diversa fica obrigado a recolher o IBS e a CBS incidentes sobre o biocombustível;',
            'tipo': 'Padrão'},
 '000006': {'artigo': '',
            'cst': '000',
            'cst_desc': 'Tributação integral',
            'cte': 0,
            'desc': 'Situações tributadas integralmente pelo IBS e CBS.realizadas por autônomo',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Situações tributadas integralmente pelo IBS e CBS realizadas por autônomo',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': '',
            'tipo': 'Padrão'},
 '010001': {'artigo': 'Art. 212',
            'cst': '010',
            'cst_desc': 'Tributação com alíquotas uniformes - operações do FGTS',
            'cte': 0,
            'desc': 'Operações do FGTS não realizadas pela Caixa Econômica Federal, observado o art. 212 da Lei Complementar nº 214, de '
                    '2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Operações do FGTS não realizadas pela Caixa Econômica Federal',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 212. As operações relacionadas ao Fundo de Garantia do Tempo de Serviço (FGTS) são sujeitas à incidência do IBS '
                     'e da CBS, por alíquotas nacionalmente uniformes, calculadas nos termos do inciso II do § 1º do art. 10 da Emenda '
                     'Constitucional nº 132, de 20 de dezembro de 2023. § 3º Ficam sujeitas: II - no caso das operações previstas nos '
                     'incisos II e III do § 2º deste artigo, às alíquotas do IBS e da CBS que serão fixadas de modo que a soma das '
                     'alíquotas corresponda: (Redação dada pela Lei Complementar nº 227, de 2026) a) em 2027 a 1,0% (um inteiro por '
                     'cento); b) em 2028 a 1,0% (um inteiro por cento); c) em 2029 a 1,2% (um inteiro e dois décimos por cento); d) em '
                     '2030 a 1,4% (um inteiro e quatro décimos por cento); e) em 2031 a 1,6% (um inteiro e seis décimos por cento); f) em '
                     '2032 a 1,8% (um inteiro e oito décimos por cento); e g) a partir de 2033, a 3,0% (três inteiros por cento).',
            'tipo': 'Uniforme setorial'},
 '010002': {'artigo': 'Art. 233',
            'cst': '010',
            'cst_desc': 'Tributação com alíquotas uniformes - operações setor financeiro',
            'cte': 0,
            'desc': 'Operações do serviço financeiro',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Operações do serviço financeiro',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 233. De 2027 a 2033, a soma das alíquotas do IBS e da CBS incidentes sobre os serviços financeiros de que trata '
                     'o art. 189 desta Lei Complementar, calculada nos termos do inciso II do § 1º do art. 10 da Emenda Constitucional nº '
                     '132, de 20 de dezembro de 2023, corresponderá: I - em 2027 e 2028, a 10,85% (dez inteiros e oitenta e cinco '
                     'centésimos por cento); II - em 2029, a 11,00% (onze por cento); III - em 2030, a 11,15% (onze inteiros e quinze '
                     'centésimos por cento); IV - em 2031, a 11,30% (onze inteiros e trinta centésimos por cento); V - em 2032, a 11,50% '
                     '(onze inteiros e cinquenta centésimos por cento); e VI - em 2033, a 12,50% (doze inteiros e cinquenta centésimos por '
                     'cento).',
            'tipo': 'Uniforme setorial'},
 '011001': {'artigo': 'Art. 236',
            'cst': '011',
            'cst_desc': 'Tributação com alíquotas uniformes reduzidas em 60%',
            'cte': 0,
            'desc': 'Planos de assistência funerária, observado o art. 236 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Planos de assistência funerária.',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 236. Os planos de assistência funerária ficam sujeitos ao disposto nos arts. 234 a 242 desta Lei Complementar.',
            'tipo': 'Uniforme nacional (referência)'},
 '011002': {'artigo': 'Art. 237',
            'cst': '011',
            'cst_desc': 'Tributação com alíquotas uniformes reduzidas em 60%',
            'cte': 0,
            'desc': 'Planos de assistência à saúde, observado o art. 237 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Planos de assistência à saúde',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 237. As alíquotas de IBS e de CBS no regime específico de planos de assistência à saúde são nacionalmente '
                     'uniformes e correspondem às alíquotas de referência de cada esfera federativa, reduzidas em 60% (sessenta por '
                     'cento).',
            'tipo': 'Uniforme nacional (referência)'},
 '011003': {'artigo': 'Art. 240',
            'cst': '011',
            'cst_desc': 'Tributação com alíquotas uniformes reduzidas em 60%',
            'cte': 0,
            'desc': 'Intermediação de planos de assistência à saúde, observado o art. 240 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Intermediação de planos de assistência à saúde',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 240. Os serviços de intermediação de planos de assistência à saúde ficam sujeitos à incidência do IBS e da CBS '
                     'sobre o valor da operação pela mesma alíquota aplicável ao plano de assistência à saúde.',
            'tipo': 'Uniforme nacional (referência)'},
 '011004': {'artigo': 'Art. 246',
            'cst': '011',
            'cst_desc': 'Tributação com alíquotas uniformes',
            'cte': 0,
            'desc': 'Concursos e prognósticos, observado o art. 246 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Concursos e prognósticos',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 246. As alíquotas do IBS e da CBS sobre concursos de prognósticos são nacionalmente uniformes e correspondem à '
                     'soma das alíquotas de referência das esferas federativas.',
            'tipo': 'Uniforme nacional (referência)'},
 '011005': {'artigo': 'Art. 243',
            'cst': '011',
            'cst_desc': 'Tributação com alíquotas uniformes reduzidas em 30%',
            'cte': 0,
            'desc': 'Planos de assistência à saúde de animais domésticos, observado o art. 243 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Planos de assistência à saúde de animais domésticos',
            'pred_cbs': 30.0,
            'pred_ibs': 30.0,
            'texto': 'Art. 243. Os planos de assistência à saúde de animais domésticos ficam sujeitos ao disposto nos arts. 234 a 242 '
                     'desta Lei Complementar, com exceção das alíquotas aplicáveis, que serão nacionalmente uniformes e corresponderão à '
                     'soma das alíquotas de referência de cada esfera federativa, reduzidas em 30% (trinta por cento), vedado o crédito ao '
                     'adquirente.',
            'tipo': 'Uniforme nacional (referência)'},
 '200001': {'artigo': 'Art. 103',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 1,
            'desc': 'Serviços de transporte de bens até as zonas de processamento de exportação e bens exportados a partir das zonas de '
                    'processamento de exportação, observado o art. 103 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Serviços de transporte de bens até as zonas de processamento de exportação e bens exportados a partir das zonas de '
                    'processamento de exportação',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 103. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre os serviços de transporte: I - dos '
                     'bens de que tratam os arts. 99 e 100 desta Lei Complementar, até as zonas de processamento de exportação; e II - dos '
                     'bens exportados a partir das zonas de processamento de exportação.',
            'tipo': 'Padrão'},
 '200002': {'artigo': 'Art. 110',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Fornecimento ou importação de tratores, máquinas e implementos agrícolas, destinados a produtor rural não '
                    'contribuinte, e de veículos de transporte de carga destinados a transportador autônomo de carga pessoa física não '
                    'contribuinte, observado o art. 110 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento ou importação para produtor rural não contribuinte ou TAC',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 110. Ficam reduzidas a zero as alíquotas do IBS e da CBS no fornecimento e na importação: I - de tratores, '
                     'máquinas e implementos agrícolas, destinados a produtor rural não contribuinte de que trata o art. 164; e II - de '
                     'veículos de transporte de carga destinados a transportador autônomo de carga pessoa física não contribuinte de que '
                     'trata o art. 169.',
            'tipo': 'Padrão'},
 '200003': {'artigo': 'Art. 125',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Vendas de produtos destinados à alimentação humana relacionados no Anexo I da Lei Complementar nº 214, de 2025, com a '
                    'especificação das respectivas classificações da NCM/SH, que compõem a Cesta Básica Nacional de Alimentos, criada nos '
                    'termos do art. 8º da Emenda Constitucional nº 132, de 20 de dezembro de 2023, observado o art. 125 da Lei '
                    'Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Vendas de produtos destinados à alimentação humana (Anexo I)',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 125. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre as vendas de produtos destinados à '
                     'alimentação humana relacionados no Anexo I desta Lei Complementar, com a especificação das respectivas '
                     'classificações da NCM/SH, que compõem a Cesta Básica Nacional de Alimentos, criada nos termos do art. 8º da Emenda '
                     'Constitucional nº 132, de 20 de dezembro de 2023.',
            'tipo': 'Padrão'},
 '200004': {'artigo': 'Art. 144, I',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Fornecimento de dispositivos médicos com a especificação das respectivas classificações da NCM/SH previstas no Anexo '
                    'XII da Lei Complementar nº 214, de 2025, observado o art. 144 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento de dispositivos médicos (Anexo XII)',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 144. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre o fornecimento dos dispositivos '
                     'médicos relacionados: I - no Anexo XII desta Lei Complementar, com a especificação das respectivas classificações da '
                     'NCM/SH; e',
            'tipo': 'Padrão'},
 '200005': {'artigo': 'Art. 144, II',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Fornecimento de dispositivos médicos com a especificação das respectivas classificações da NCM/SH previstas no Anexo '
                    'IV da Lei Complementar nº 214, de 2025, quando adquiridos por órgãos da administração pública direta, autarquias, '
                    'fundações públicas e entidades de saúde imunes, observado o art. 144 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Fornecimento de dispositivos médicos para órgãos da administração pública e entidades de saúde imunes (Anexo IV)',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 144. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre o fornecimento dos dispositivos '
                     'médicos relacionados: II - no Anexo IV desta Lei Complementar, com a especificação das respectivas classificações da '
                     'NCM/SH, caso adquiridos por: a) órgãos da administração pública direta, autarquias e fundações públicas; e b) as '
                     'entidades de saúde imunes ao IBS e à CBS que possuam Certificação de Entidade Beneficente de Assistência Social '
                     '(CEBAS) por comprovarem a prestação de serviços ao SUS, nos termos dos arts. 9º a 11 da Lei Complementar nº 187, de '
                     '16 de dezembro de 2021.',
            'tipo': 'Padrão'},
 '200006': {'artigo': 'Art. 144, § 3º',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Situação de emergência de saúde pública reconhecida pelo Poder Legislativo federal, estadual, distrital ou municipal '
                    'competente, ato conjunto do Ministro da Fazenda e do Comitê Gestor do IBS poderá ser editado, a qualquer momento, '
                    'para incluir dispositivos não listados no Anexo XII da Lei Complementar nº 214, de 2025, limitada a vigência do '
                    'benefício ao período e à localidade da emergência de …',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Situação de emergência de saúde pública reconhecida pelo Poder público',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 144. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre o fornecimento dos dispositivos '
                     'médicos relacionados: § 3º Em caso de emergência de saúde pública reconhecida pelo Poder Legislativo federal, '
                     'estadual, distrital ou municipal competente, ato conjunto do Ministro de Estado da Fazenda e do Comitê Gestor do IBS '
                     'poderá ser editado, a qualquer momento, para incluir dispositivos não listados no Anexo XII desta Lei Complementar, '
                     'limitada a vigência do benefício ao período e à localidade da emergência de saúde pública.',
            'tipo': 'Padrão'},
 '200007': {'artigo': 'Art. 145, I',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Fornecimento dos dispositivos de acessibilidade próprios para pessoas com deficiência relacionados no Anexo XIII da '
                    'Lei Complementar nº 214, de 2025, com a especificação das respectivas classificações da NCM/SH, observado o art. 145 '
                    'da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento dos dispositivos de acessibilidade próprios para pessoas com deficiência (Anexo XIII)',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 145. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre o fornecimento dos dispositivos de '
                     'acessibilidade próprios para pessoas com deficiência relacionados: I - no Anexo XIII desta Lei Complementar, com a '
                     'especificação das respectivas classificações da NCM/SH; e',
            'tipo': 'Padrão'},
 '200008': {'artigo': 'Art. 145, II',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Fornecimento dos dispositivos de acessibilidade próprios para pessoas com deficiência relacionados no Anexo V da Lei '
                    'Complementar nº 214, de 2025, com a especificação das respectivas classificações da NCM/SH, quando adquiridos por '
                    'órgãos da administração pública direta, autarquias, fundações públicas e entidades imunes, observado o art. 145 da '
                    'Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Fornecimento dos dispositivos de acessibilidade próprios para pessoas com deficiência adquiridos por órgãos da '
                    'administração pública (Anexo V)',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 145. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre o fornecimento dos dispositivos de '
                     'acessibilidade próprios para pessoas com deficiência relacionados: II - no Anexo V desta Lei Complementar, com a '
                     'especificação das respectivas classificações da NCM/SH, quando adquiridos por: a) órgãos da administração pública '
                     'direta, autarquias e fundações públicas; e b) as entidades de saúde imunes ao IBS e à CBS que possuam CEBAS por '
                     'comprovarem a prestação de serviços ao SUS, nos termos dos arts. 9º a 11 da Lei Complementar nº 187, de 2021.',
            'tipo': 'Padrão'},
 '200009': {'artigo': 'Art. 146',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Fornecimento dos medicamentos registrados na Anvisa, observado o art. 146 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento dos medicamentos registrados na Anvisa',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 146. São reduzidas a zero as alíquotas do IBS e da CBS sobre o fornecimento dos medicamentos registrados na '
                     'Anvisa, desde que destinados, de acordo com o registro sanitário, a: I – doenças raras; II – doenças negligenciadas; '
                     'III – oncologia; IV – diabetes; V – HIV/aids e outras infecções sexualmente transmissíveis (IST); VI – doenças '
                     'cardiovasculares; e VII – Programa Farmácia Popular do Brasil ou equivalente',
            'tipo': 'Padrão'},
 '200010': {'artigo': 'Art. 146, § 1º, I e II',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Fornecimento dos medicamentos registrados na Anvisa, quando adquiridos por órgãos da administração pública direta, '
                    'autarquias, fundações públicas e entidades imunes, observado o art. 146 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento dos medicamentos registrados na Anvisa, adquiridos por órgãos da administração pública',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 146. § 1º São também reduzidas a zero as alíquotas do IBS e da CBS sobre o fornecimento de medicamentos '
                     'registrados na Anvisa quando: I – adquiridos por órgãos da administração pública direta, por autarquias e por '
                     'fundações públicas; II – adquiridos por entidades de saúde imunes ao IBS e à CBS que possuam Cebas por comprovarem a '
                     'prestação de serviços ao SUS, nos termos dos arts. 9º a 11 da Lei Complementar nº 187, de 16 de dezembro de 2021;',
            'tipo': 'Padrão'},
 '200011': {'artigo': 'Art. 146, § 2º',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Fornecimento das composições para nutrição enteral e parenteral, composições especiais e fórmulas nutricionais '
                    'destinadas às pessoas com erros inatos do metabolismo relacionadas no Anexo VI da Lei Complementar nº 214, de 2025, '
                    'com a especificação das respectivas classificações da NCM/SH, quando adquiridas por órgãos da administração pública '
                    'direta, autarquias e fundações públicas, observado o …',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Fornecimento das composições para nutrição enteral e parenteral quando adquiridas por órgãos da administração pública '
                    '(Anexo VI)',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 146. § 2º A redução de alíquotas de que trata o caput deste artigo aplica-se também ao fornecimento de '
                     'composições para nutrição enteral e parenteral, composições especiais e fórmulas nutricionais destinadas às pessoas '
                     'com erros inatos do metabolismo relacionadas no Anexo VI desta Lei Complementar, com a especificação das respectivas '
                     'classificações da NCM/ SH, quando adquiridas por órgãos e entidades mencionados nos incisos I e II do § 1º deste '
                     'artigo.',
            'tipo': 'Padrão'},
 '200012': {'artigo': 'Art. 146, § 4º',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Situação de emergência de saúde pública reconhecida pelo Poder Legislativo federal, estadual, distrital ou municipal '
                    'competente, ato conjunto do Ministro da Fazenda e do Comitê Gestor do IBS poderá ser editado, a qualquer momento, '
                    'limitada a vigência do benefício ao período e à localidade da emergência de saúde pública, observado o art. 146 da '
                    'Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Situação de emergência de saúde pública reconhecida pelo Poder público',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 146. § 4º Em caso de emergência de saúde pública reconhecida pelo Poder Legislativo federal, estadual, '
                     'distrital ou municipal competente, ato conjunto do Ministro da Fazenda, do Ministério da Saúde e do CGIBS poderá ser '
                     'editado, a qualquer momento, tão somente para incluir medicamentos e linhas de cuidado não contemplados na redução '
                     'de alíquota a que se refere este artigo, limitada a vigência do benefício ao período da respectiva emergência de '
                     'saúde pública',
            'tipo': 'Padrão'},
 '200013': {'artigo': 'Art. 147',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Fornecimento de tampões higiênicos, absorventes higiênicos internos ou externos, descartáveis ou reutilizáveis, '
                    'calcinhas absorventes e coletores menstruais, observado o art. 147 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento de tampões higiênicos, absorventes higiênicos internos ou externos',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 147. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre o fornecimento dos seguintes produtos '
                     'de cuidados básicos à saúde menstrual: I - tampões higiênicos classificados no código 9619.00.00 da NCM/SH; II - '
                     'absorventes higiênicos internos ou externos, descartáveis ou reutilizáveis, e calcinhas absorventes classificados no '
                     'código 9619.00.00 da NCM/SH; e III - coletores menstruais classificados no código 9619.00.00 da NCM/SH.',
            'tipo': 'Padrão'},
 '200014': {'artigo': 'Art. 148',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Fornecimento dos produtos hortícolas, frutas e ovos, relacionados no Anexo XV da Lei Complementar nº 214 , de 2025, '
                    'com a especificação das respectivas classificações da NCM/SH e desde que não cozidos, observado o art. 148 da Lei '
                    'Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento dos produtos hortícolas, frutas e ovos (Anexo XV)',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 148. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre o fornecimento dos produtos '
                     'hortícolas, frutas e ovos relacionados no Anexo XV desta Lei Complementar, com a especificação das respectivas '
                     'classificações da NCM/SH.',
            'tipo': 'Padrão'},
 '200015': {'artigo': 'Art. 149',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Venda de automóveis de passageiros de fabricação nacional de, no mínimo, 4 (quatro) portas, inclusive a de acesso ao '
                    'bagageiro, quando adquiridos por motoristas profissionais que exerçam, comprovadamente, em automóvel de sua '
                    'propriedade, atividade de condutor autônomo de passageiros, na condição de titular de autorização, permissão ou '
                    'concessão do poder público, e que destinem o automóvel à …',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Venda de automóveis de passageiros de fabricação nacional adquiridos por motoristas profissionais ou pessoas com '
                    'deficiência',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 149. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre a venda de automóveis de passageiros '
                     'de fabricação nacional de, no mínimo, 4 (quatro) portas, inclusive a de acesso ao bagageiro, quando adquiridos por:',
            'tipo': 'Padrão'},
 '200016': {'artigo': 'Art. 156',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Prestação de serviços de pesquisa e desenvolvimento por Instituição Científica, Tecnológica e de Inovação (ICT) sem '
                    'fins lucrativos para a administração pública direta, autarquias e fundações públicas ou para o contribuinte sujeito '
                    'ao regime regular do IBS e da CBS, observado o disposto no art. 156 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Prestação de serviços de pesquisa e desenvolvimento por Instituição Científica, Tecnológica e de Inovação (ICT)',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 156. São reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre a prestação de serviços de pesquisa e '
                     'desenvolvimento por Instituição Científica, Tecnológica e de Inovação (ICT) sem fins lucrativos, bem como por '
                     'fundações de apoio credenciadas na forma da lei, para: I - a administração pública direta, autarquias e fundações '
                     'públicas; ou II - contribuinte sujeito ao regime regular do IBS e da CBS.',
            'tipo': 'Padrão'},
 '200017': {'artigo': 'Art. 212, § 3º, I',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Operações relacionadas ao FGTS, considerando aquelas necessárias à aplicação da Lei nº 8.036, de 1990, realizadas '
                    'pelo Conselho Curador ou Secretaria Executiva do FGTS, observado o art. 212 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Operações relacionadas ao FGTS',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 212. As operações relacionadas ao Fundo de Garantia do Tempo de Serviço (FGTS) são sujeitas à incidência do IBS '
                     'e da CBS, por alíquotas nacionalmente uniformes, calculadas nos termos do inciso II do § 1º do art. 10 da Emenda '
                     'Constitucional nº 132, de 20 de dezembro de 2023. § 2º As operações relacionadas ao FGTS são aquelas necessárias à '
                     'aplicação da Lei nº 8.036, de 11 de maio de 1990, realizadas: I – pelo agente operador do FGTS; § 3º Ficam sujeitas: '
                     'I - no caso das operações previstas no inciso I do § 2º deste artigo, à alíquota zero do IBS e da CBS;',
            'tipo': 'Padrão'},
 '200018': {'artigo': 'Art. 223, § 4º',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Operações de resseguro e retrocessão ficam sujeitas à incidência à alíquota zero, inclusive quando os prêmios de '
                    'resseguro e retrocessão forem cedidos ao exterior, observado o art. 223 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Operações de resseguro e retrocessão',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 223. Para fins de determinação da base de cálculo, nas operações de seguros e resseguros de que tratam, '
                     'respectivamente, os incisos XI e XII do caput do art. 182 desta Lei Complementar: § 4º As operações de resseguro e '
                     'retrocessão ficam sujeitas à incidência à alíquota zero, inclusive quando os prêmios de resseguro e retrocessão '
                     'forem cedidos ao exterior.',
            'tipo': 'Padrão'},
 '200019': {'artigo': 'Art. 231, § 1º, II',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Importador dos serviços financeiros que seja contribuinte e tenha direito de apropriação de créditos na aquisição do '
                    'mesmo serviço financeiro no País, observado o art. 231 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Importador dos serviços financeiros contribuinte',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 231. Os serviços financeiros de que trata o art. 182 desta Lei Complementar, quando forem considerados '
                     'importados, nos termos da Seção II do Capítulo IV do Título I deste Livro, ficam sujeitos à incidência do IBS e da '
                     'CBS pela mesma alíquota aplicável aos respectivos serviços financeiros adquiridos de fornecedores domiciliados no '
                     'País. § 1º Na importação de serviços financeiros: II - nas hipóteses em que o importador dos serviços financeiros '
                     'seja contribuinte do IBS e da CBS sujeito ao regime regular e tenha direito de apropriação de créditos desses '
                     'tributos na aquisição do mesmo serviço financeiro no País, de acordo com o disposto neste Capítulo, será aplicada '
                     'alíquota zero na importação, e não serão apropriados créditos do IBS e da CBS; e',
            'tipo': 'Padrão'},
 '200020': {'artigo': 'Art. 271',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 1,
            'desc': 'Operação praticada por sociedades cooperativas optantes por regime específico do IBS e CBS, quando o associado '
                    'destinar bem ou serviço à cooperativa de que participa, e a cooperativa fornecer bem ou serviço ao associado sujeito '
                    'ao regime regular do IBS e da CBS, observado o art. 271 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Operação praticada por sociedades cooperativas optantes por regime específico do IBS e CBS',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 271. As sociedades cooperativas poderão optar por regime específico do IBS e da CBS no qual ficam reduzidas a '
                     'zero as alíquotas do IBS e da CBS incidentes na operação em que: I - o associado fornece bem ou serviço à '
                     'cooperativa de que participa; e II - a cooperativa fornece bem ou serviço a associado sujeito ao regime regular do '
                     'IBS e da CBS. § 1º O disposto no caput deste artigo aplica-se também: I - às operações realizadas entre cooperativas '
                     'singulares, centrais, federações, confederações e às originárias dos seus respectivos bancos cooperativos de que as '
                     'cooperativas participam;',
            'tipo': 'Padrão'},
 '200021': {'artigo': 'Art. 285, I',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Serviços de transporte público coletivo de passageiros ferroviário e hidroviário urbanos, semiurbanos e '
                    'metropolitanos, observado o art. 285 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Serviços de transporte público coletivo de passageiros ferroviário e hidroviário',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 285. Em relação aos serviços de transporte público coletivo de passageiros ferroviário e hidroviário de caráter '
                     'urbano, semiurbano e metropolitano: I - ficam reduzidas em 100% (cem por cento) as alíquotas do IBS e da CBS '
                     'incidentes sobre o fornecimento desses serviços;',
            'tipo': 'Padrão'},
 '200022': {'artigo': 'Art. 445',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Operação originada fora da Zona Franca de Manaus que destine bem material industrializado de origem nacional a '
                    'contribuinte estabelecido na Zona Franca de Manaus que seja habilitado nos termos do art. 442 da Lei Complementar nº '
                    '214, de 2025, e sujeito ao regime regular do IBS e da CBS ou optante pelo regime do Simples Nacional de que trata o '
                    'art. 12 da Lei Complementar nº 123, de 2006, observado …',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Operação originada fora da ZFM que destine bem material industrializado a contribuinte estabelecido na ZFM',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 445. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre operação originada fora da Zona '
                     'Franca de Manaus que destine bem material industrializado de origem nacional a contribuinte estabelecido na Zona '
                     'Franca de Manaus que seja:',
            'tipo': 'Padrão'},
 '200023': {'artigo': 'Art. 448',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Operação realizada por indústria incentivada que destine bem material intermediário para outra indústria incentivada '
                    'na Zona Franca de Manaus, desde que a entrega ou disponibilização dos bens ocorra dentro da referida área, observado '
                    'o art. 448 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Operação realizada por indústria incentivada que destine bem material intermediário para outra indústria incentivada '
                    'na ZFM',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 448. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre operação realizada por indústria '
                     'incentivada que destine bem material intermediário para outra indústria incentivada na Zona Franca de Manaus, desde '
                     'que a entrega ou disponibilização dos bens ocorra dentro da referida área.',
            'tipo': 'Padrão'},
 '200024': {'artigo': 'Art. 463',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Operação originada fora das Áreas de Livre Comércio que destine bem material industrializado de origem nacional a '
                    'contribuinte estabelecido nas Áreas de Livre Comércio que seja habilitado nos termos do art. 456 da Lei Complementar '
                    'nº 214, de 2025, e sujeito ao regime regular do IBS e da CBS ou optante pelo regime do Simples Nacional de que trata '
                    'o art. 12 da Lei Complementar nº 123, de 2006, …',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Operação originada fora das Áreas de Livre Comércio destinadas a contribuinte estabelecido nas Áreas de Livre '
                    'Comércio',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 463. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre operação originada fora da área de '
                     'livre comércio que destine bem material industrializado de origem nacional a contribuinte estabelecido na área de '
                     'livre comércio que seja:',
            'tipo': 'Padrão'},
 '200025': {'artigo': 'Art. 308',
            'cst': '200',
            'cst_desc': 'Alíquota zero apenas CBS e reduzida em 60% para IBS',
            'cte': 0,
            'desc': 'Fornecimento dos serviços de educação relacionados ao Programa Universidade para Todos (Prouni), instituído pela Lei '
                    'nº 11.096, de 13 de janeiro de 2005, observado o art. 308 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Fornecimento dos serviços de educação relacionados ao Programa Universidade para Todos (Prouni)',
            'pred_cbs': 100.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 308. Fica reduzida a zero a alíquota da CBS incidente sobre o fornecimento de serviços de educação de ensino '
                     'superior por instituição privada de ensino, com ou sem fins lucrativos, durante o período de adesão e vinculação ao '
                     'Programa Universidade para Todos - Prouni, instituído pela Lei nº 11.096, de 13 de janeiro de 2005.',
            'tipo': 'Padrão'},
 '200026': {'artigo': 'Art. 158, parágrafo único',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 80%',
            'cte': 0,
            'desc': 'Locação de imóveis localizados nas zonas reabilitadas, pelo prazo de 5 (cinco) anos, contado da data de expedição do '
                    'habite-se, e relacionados a projetos de reabilitação urbana de zonas históricas e de áreas críticas de recuperação e '
                    'reconversão urbanística dos Municípios ou do Distrito Federal, a serem delimitadas por lei municipal ou distrital, '
                    'observado o art. 158 da Lei Complementar nº 214, …',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Locação de imóveis localizados nas zonas reabilitadas',
            'pred_cbs': 80.0,
            'pred_ibs': 80.0,
            'texto': 'Art. 158. Observado o disposto neste Capítulo, ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da '
                     'CBS sobre operações relacionadas a projetos de reabilitação urbana de zonas históricas e de áreas críticas de '
                     'recuperação e reconversão urbanística dos Municípios ou do Distrito Federal, a serem delimitadas por lei municipal '
                     'ou distrital. Parágrafo único. Na hipótese de locação de imóveis prevista no inciso VI do caput do art. 162 desta '
                     'Lei Complementar, a redução de alíquotas de que trata o caput deste artigo será de 80% (oitenta por cento).',
            'tipo': 'Padrão'},
 '200027': {'artigo': 'Art. 261, parágrafo único',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 70%',
            'cte': 0,
            'desc': 'Operações de locação, cessão onerosa e arrendamento de bens imóveis, observado o art. 261 da Lei Complementar nº 214, '
                    'de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Operações de locação, cessão onerosa e arrendamento de bens imóveis',
            'pred_cbs': 70.0,
            'pred_ibs': 70.0,
            'texto': 'Art. 261. Parágrafo único. As alíquotas do IBS e da CBS relativas às operações de locação, cessão onerosa e '
                     'arrendamento de bens imóveis ficam reduzidas em 70% (setenta por cento).',
            'tipo': 'Padrão'},
 '200028': {'artigo': 'Art. 129',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Fornecimento dos serviços de educação relacionados no Anexo II da Lei Complementar nº 214, de 2025, com a '
                    'especificação das respectivas classificações da Nomenclatura Brasileira de Serviços, Intangíveis e Outras Operações '
                    'que Produzam Variações no Patrimônio (NBS), observado o art. 129 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Fornecimento dos serviços de educação (Anexo II)',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 129. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS incidentes sobre o fornecimento '
                     'dos serviços de educação relacionados no Anexo II desta Lei Complementar, com a especificação das respectivas '
                     'classificações da Nomenclatura Brasileira de Serviços, Intangíveis e Outras Operações que Produzam Variações no '
                     'Patrimônio (NBS).',
            'tipo': 'Padrão'},
 '200029': {'artigo': 'Art. 130',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Fornecimento dos serviços de saúde humana relacionados no Anexo III da Lei Complementar nº 214, de 2025, com a '
                    'especificação das respectivas classificações da NBS, observado o art. 130 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Fornecimento dos serviços de saúde humana (Anexo III)',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 130. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS incidentes sobre o fornecimento '
                     'dos serviços de saúde relacionados no Anexo III desta Lei Complementar, com a especificação das respectivas '
                     'classificações da NBS.',
            'tipo': 'Padrão'},
 '200030': {'artigo': 'Art. 131',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Venda dos dispositivos médicos relacionados no Anexo IV da Lei Complementar nº 214, de 2025, com a especificação das '
                    'respectivas classificações da NCM/SH, observado o art. 131 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Venda dos dispositivos médicos (Anexo IV)',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 131. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS incidentes sobre o fornecimento '
                     'dos dispositivos médicos relacionados no Anexo IV desta Lei Complementar, com a especificação das respectivas '
                     'classificações da NCM/SH.',
            'tipo': 'Padrão'},
 '200031': {'artigo': 'Art. 132',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Fornecimento dos dispositivos de acessibilidade próprios para pessoas com deficiência relacionados no Anexo V da Lei '
                    'Complementar nº 214, de 2025, com a especificação das respectivas classificações da NCM/SH, observado o art. 132 da '
                    'Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento dos dispositivos de acessibilidade próprios para pessoas com deficiência (Anexo V)',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 132. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS incidentes sobre o fornecimento '
                     'dos dispositivos de acessibilidade próprios para pessoas com deficiência relacionados no Anexo V desta Lei '
                     'Complementar, com a especificação das respectivas classificações da NCM/SH.',
            'tipo': 'Padrão'},
 '200032': {'artigo': 'Art. 133',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Fornecimento dos medicamentos registrados na Anvisa ou produzidos por farmácias de manipulação, ressalvados os '
                    'medicamentos sujeitos à alíquota zero de que trata o art. 146 da Lei Complementar nº 214, de 2025, observado o art. '
                    '133 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento dos medicamentos registrados na Anvisa ou produzidos por farmácias de manipulação, ressalvados os '
                    'medicamentos sujeitos à alíquota zero',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 133. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS incidentes sobre o fornecimento '
                     'dos medicamentos registrados na Anvisa ou produzidos por farmácias de manipulação, ressalvados os medicamentos '
                     'sujeitos à alíquota zero de que trata o art. 146 desta Lei Complementar.',
            'tipo': 'Padrão'},
 '200033': {'artigo': 'Art. 133, § 1º',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Fornecimento das composições para nutrição enteral e parenteral, composições especiais e fórmulas nutricionais '
                    'destinadas às pessoas com erros inatos do metabolismo relacionadas no Anexo VI da Lei Complementar nº 214, de 2025, '
                    'com a especificação das respectivas classificações da NCM/SH, observado o art. 133 da Lei Complementar nº 214, de '
                    '2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento das composições para nutrição enteral e parenteral (Anexo VI)',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 133. § 1º A redução de alíquotas prevista no caput deste artigo aplica-se também às operações de fornecimento '
                     'das composições para nutrição enteral e parenteral, composições especiais e fórmulas nutricionais destinadas às '
                     'pessoas com erros inatos do metabolismo relacionadas no Anexo VI desta Lei Complementar, com a especificação das '
                     'respectivas classificações da NCM/SH.',
            'tipo': 'Padrão'},
 '200034': {'artigo': 'Art. 135',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Fornecimento dos alimentos destinados ao consumo humano relacionados no Anexo VII da Lei Complementar nº 214, de '
                    '2025, com a especificação das respectivas classificações da NCM/SH, observado o art. 135 da Lei Complementar nº 214, '
                    'de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento dos alimentos destinados ao consumo humano (Anexo VII)',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 135. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS incidentes sobre o fornecimento '
                     'dos alimentos destinados ao consumo humano relacionados no Anexo VII desta Lei Complementar, com a especificação das '
                     'respectivas classificações da NCM/SH.',
            'tipo': 'Padrão'},
 '200035': {'artigo': 'Art. 136',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Fornecimento dos produtos de higiene pessoal e limpeza relacionados no Anexo VIII da Lei Complementar nº 214, de '
                    '2025, com a especificação das respectivas classificações da NCM/SH, observado o art. 136 da Lei Complementar nº 214, '
                    'de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento dos produtos de higiene pessoal e limpeza (Anexo VIII)',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 136. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS incidentes sobre o fornecimento '
                     'dos produtos de higiene pessoal e limpeza relacionados no Anexo VIII desta Lei Complementar, com a especificação das '
                     'respectivas classificações da NCM/SH.',
            'tipo': 'Padrão'},
 '200036': {'artigo': 'Art. 137',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Fornecimento de produtos agropecuários, aquícolas, pesqueiros, florestais e extrativistas vegetais in natura, '
                    'observado o art. 137 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento de produtos agropecuários, aquícolas, pesqueiros, florestais e extrativistas vegetais in natura',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 137. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS incidentes sobre o fornecimento '
                     'de produtos agropecuários, aquícolas, pesqueiros, florestais e extrativistas vegetais in natura.',
            'tipo': 'Padrão'},
 '200037': {'artigo': 'Art. 137, § 3º',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Fornecimento de serviços ambientais de conservação ou recuperação da vegetação nativa, mesmo que fornecidos sob a '
                    'forma de manejo sustentável de sistemas agrícolas, agroflorestais e agrossilvopastoris, em conformidade com as '
                    'definições e requisitos da legislação específica, observado o art. 137 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Fornecimento de serviços ambientais de conservação ou recuperação da vegetação nativa',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 137. § 3º Para fins do disposto no caput deste artigo, considera-se fornecimento de produto florestal inclusive '
                     'o fornecimento dos serviços ambientais de conservação ou recuperação da vegetação nativa, mesmo que fornecidos sob a '
                     'forma de manejo sustentável de sistemas agrícolas, agroflorestais e agrossilvopastoris, em conformidade com as '
                     'definições e requisitos da legislação específica.',
            'tipo': 'Padrão'},
 '200038': {'artigo': 'Art. 138',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Fornecimento dos insumos agropecuários e aquícolas relacionados no Anexo IX da Lei Complementar nº 214, de 2025, com '
                    'a especificação das respectivas classificações da NCM/SH e da NBS, observado o art. 138 da Lei Complementar nº 214, '
                    'de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento dos insumos agropecuários e aquícolas (Anexo IX)',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 138. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS incidentes sobre o fornecimento '
                     'dos insumos agropecuários e aquícolas relacionados no Anexo IX desta Lei Complementar, com a especificação das '
                     'respectivas classificações da NCM/SH e da NBS.',
            'tipo': 'Padrão'},
 '200039': {'artigo': 'Art. 139',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Fornecimento dos bens e serviços listados no Anexo X da Lei Complementar nº 214, de 2025, com a especificação das '
                    'respectivas classificações da NCM/SH e NBS, nos casos relacionados com produções nacionais artísticas, culturais, de '
                    'eventos, jornalísticas e audiovisuais, observado o art. 139 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Fornecimento dos bens e serviços relacionados com produções nacionais artísticas, culturais, de eventos, '
                    'jornalísticas e audiovisuais (Anexo X)',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 139. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS incidentes sobre o fornecimento '
                     'dos bens e serviços listados no Anexo X desta Lei Complementar, com a especificação das respectivas classificações '
                     'da NCM/SH e NBS, nos casos relacionados com as seguintes produções nacionais artísticas, culturais, de eventos, '
                     'jornalísticas e audiovisuais:',
            'tipo': 'Padrão'},
 '200040': {'artigo': 'Art. 140',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Fornecimento dos seguintes serviços de comunicação institucional à administração pública direta, autarquias e '
                    'fundações públicas: serviços direcionados ao planejamento, criação, programação e manutenção de páginas eletrônicas '
                    'da administração pública, ao monitoramento e gestão de suas redes sociais e à otimização de páginas e canais digitais '
                    'para mecanismos de buscas e produção de mensagens, …',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Fornecimento de serviços de comunicação institucional à administração pública',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 140. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS incidentes sobre o fornecimento '
                     'dos seguintes serviços de comunicação institucional à administração pública direta, autarquias e fundações públicas:',
            'tipo': 'Padrão'},
 '200041': {'artigo': 'Art. 141, I',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Operações relacionadas às seguintes atividades desportivas: fornecimento de serviço de educação desportiva, '
                    'classificado no código 1.2205.12.00 da NBS, observado o art. 141 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Fornecimento de serviço de educação desportiva (art. 141. I)',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 141. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS incidentes sobre as seguintes '
                     'operações relacionadas a atividades desportivas: I - fornecimento de serviço de educação desportiva, classificado no '
                     'código 1.2205.12.00 da NBS;',
            'tipo': 'Padrão'},
 '200042': {'artigo': 'Art. 141, II',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Operações relacionadas às seguintes atividades desportivas: gestão e exploração do desporto por associações e clubes '
                    'esportivos filiados ao órgão estadual ou federal responsável pela coordenação dos desportos, observado o art. 141 da '
                    'Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Fornecimento de serviço de gestão e exploração do desporto (art. 141. II)',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 141. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS incidentes sobre as seguintes '
                     'operações relacionadas a atividades desportivas: II - gestão e exploração do desporto por associações e clubes '
                     'esportivos filiados ao órgão estadual ou federal responsável pela coordenação dos desportos, inclusive por meio de '
                     'venda de ingressos para eventos desportivos, fornecimento oneroso ou não de bens e serviços, inclusive ingressos, '
                     'por meio de programas de sócio-torcedor, cessão dos direitos desportivos dos atletas e transferência de atletas para '
                     'outra entidade desportiva ou seu retorno à atividade em outra entidade desportiva.',
            'tipo': 'Padrão'},
 '200043': {'artigo': 'Art. 142, I',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Fornecimento à administração pública direta, autarquias e fundações púbicas dos serviços e dos bens relativos à '
                    'soberania e à segurança nacional, à segurança da informação e à segurança cibernética relacionados no Anexo XI da Lei '
                    'Complementar nº 214, de 2025, com a especificação das respectivas classificações da NBS e da NCM/SH, observado o art. '
                    '142 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Fornecimento à administração pública dos serviços e dos bens relativos à soberania (Anexo XI)',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 142. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS sobre: I - fornecimento à '
                     'administração pública direta, autarquias e fundações púbicas dos serviços e dos bens relativos à soberania e à '
                     'segurança nacional, à segurança da informação e à segurança cibernética relacionados no Anexo XI desta Lei '
                     'Complementar, com a especificação das respectivas classificações da NBS e da NCM/SH; e',
            'tipo': 'Padrão'},
 '200044': {'artigo': 'Art. 142, II',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Operações e prestações de serviços de segurança da informação e segurança cibernética desenvolvidos por sociedade que '
                    'tenha sócio brasileiro com o mínimo de 20% (vinte por cento) do seu capital social, relacionados no Anexo XI da Lei '
                    'Complementar nº 214, de 2025, com a especificação das respectivas classificações da NBS e da NCM/SH, observado o art. '
                    '142 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Operações e prestações de serviços de segurança da informação e segurança cibernética desenvolvidos por sociedade que '
                    'tenha sócio brasileiro (Anexo XI)',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 142. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS sobre: II – fornecimento de '
                     'serviços de segurança da informação e segurança cibernética desenvolvidos por sociedade que tenha sócio brasileiro '
                     'com o mínimo de 20% (vinte por cento) do seu capital social, relacionados no Anexo XI desta Lei Complementar, com a '
                     'especificação das respectivas classificações da NBS.',
            'tipo': 'Padrão'},
 '200045': {'artigo': 'Art. 158',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Operações relacionadas a projetos de reabilitação urbana de zonas históricas e de áreas críticas de recuperação e '
                    'reconversão urbanística dos Municípios ou do Distrito Federal, a serem delimitadas por lei municipal ou distrital, '
                    'observado o art. 158 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Operações relacionadas a projetos de reabilitação urbana de zonas históricas e de áreas críticas de recuperação e '
                    'reconversão urbanística',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 158. Observado o disposto neste Capítulo, ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da '
                     'CBS sobre operações relacionadas a projetos de reabilitação urbana de zonas históricas e de áreas críticas de '
                     'recuperação e reconversão urbanística dos Municípios ou do Distrito Federal, a serem delimitadas por lei municipal '
                     'ou distrital.',
            'tipo': 'Padrão'},
 '200046': {'artigo': 'Art. 261',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 50%',
            'cte': 0,
            'desc': 'Operações com bens imóveis, observado o art. 261 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Operações com bens imóveis',
            'pred_cbs': 50.0,
            'pred_ibs': 50.0,
            'texto': 'Art. 261. As alíquotas do IBS e da CBS relativas às operações de que trata este Capítulo ficam reduzidas em 50% '
                     '(cinquenta por cento).',
            'tipo': 'Padrão'},
 '200047': {'artigo': 'Art. 275',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 40%',
            'cte': 0,
            'desc': 'Bares e Restaurantes, observado o art. 275 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Bares e Restaurantes',
            'pred_cbs': 40.0,
            'pred_ibs': 40.0,
            'texto': 'Art. 275. As alíquotas do IBS e da CBS relativas às operações de que trata este Capítulo ficam reduzidas em 40% '
                     '(quarenta por cento).',
            'tipo': 'Padrão'},
 '200048': {'artigo': 'Art. 281',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 40%',
            'cte': 0,
            'desc': 'Hotelaria, Parques de Diversão e Parques Temáticos, observado o art. 281 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Hotelaria, Parques de Diversão e Parques Temáticos',
            'pred_cbs': 40.0,
            'pred_ibs': 40.0,
            'texto': 'Art. 281. As alíquotas do IBS e da CBS relativas às operações de que trata este Capítulo ficam reduzidas em 40% '
                     '(quarenta por cento).',
            'tipo': 'Padrão'},
 '200049': {'artigo': 'Art. 286',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 40%',
            'cte': 0,
            'desc': 'Transporte coletivo de passageiros rodoviário, ferroviário e hidroviário intermunicipais e interestaduais, observado '
                    'o art. 286 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Transporte coletivo de passageiros rodoviário, ferroviário e hidroviário',
            'pred_cbs': 40.0,
            'pred_ibs': 40.0,
            'texto': 'Art. 286. Em relação aos serviços de transporte coletivo de passageiros rodoviário, ferroviário e hidroviário '
                     'intermunicipais e interestaduais, as alíquotas do IBS e da CBS do regime específico de que trata essa Seção ficam '
                     'reduzidas em 40% (quarenta por cento).',
            'tipo': 'Padrão'},
 '200050': {'artigo': 'Art. 287',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 40%',
            'cte': 1,
            'desc': 'Serviços de transporte aéreo regional coletivo de passageiros ou de carga, observado o art. 287 da Lei Complementar '
                    'nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Serviços de transporte aéreo regional coletivo de passageiros ou de carga',
            'pred_cbs': 40.0,
            'pred_ibs': 40.0,
            'texto': 'Art. 287. Ficam reduzidas em 40% (quarenta por cento) as alíquotas do IBS e da CBS incidentes sobre o fornecimento '
                     'do serviço de transporte aéreo regional coletivo de passageiros ou de carga.',
            'tipo': 'Padrão'},
 '200051': {'artigo': 'Art. 289, II',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 40%',
            'cte': 0,
            'desc': 'Agências de Turismo, observado o art. 289 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Agências de Turismo',
            'pred_cbs': 40.0,
            'pred_ibs': 40.0,
            'texto': 'Art. 289. Na intermediação de serviços turísticos realizada por agências de turismo: II - a alíquota é a mesma '
                     'aplicável aos serviços de hotelaria, parques de diversão e parques temáticos;',
            'tipo': 'Padrão'},
 '200052': {'artigo': 'Art. 127, I a XVIII',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 30%',
            'cte': 0,
            'desc': 'Prestação de serviços das seguintes profissões intelectuais de natureza científica, literária ou artística, '
                    'submetidas à fiscalização por conselho profissional: administradores, advogados, arquitetos e urbanistas, assistentes '
                    'sociais, bibliotecários, biólogos, contabilistas, economistas, economistas domésticos, profissionais de educação '
                    'física, engenheiros e agrônomos, estatísticos, médicos …',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Prestação de serviços de profissões intelectuais',
            'pred_cbs': 30.0,
            'pred_ibs': 30.0,
            'texto': 'Art. 127. Ficam reduzidas em 30% (trinta por cento) as alíquotas do IBS e da CBS incidentes sobre a prestação de '
                     'serviços pelos seguintes profissionais, que exercerem atividades intelectuais de natureza científica, literária ou '
                     'artística, submetidas à fiscalização por conselho profissional: I – administradores; II – advogados; III – '
                     'arquitetos e urbanistas; IV – assistentes sociais; V – bibliotecários; VI – biólogos; VII – contabilistas; VIII – '
                     'economistas; IX – economistas domésticos; X – profissionais de educação física; XI – engenheiros e agrônomos; XII – '
                     'estatísticos; XIII - médicos veterinários e zootecnistas; XIV – museólogos; XV – químicos; XVI – profissionais de '
                     'relações públicas; XVII – técnicos industriais; e XVIII – técnicos agrícolas;',
            'tipo': 'Padrão'},
 '200053': {'artigo': 'Art. 146, § 1º, III',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Fornecimento de medicamentos registrados na Anvisa, quando classificados como soros ou vacinas, observado o art. 146 '
                    'da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento de medicamentos registrados na Anvisa, quando classificados como soros ou vacinas',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 146. § 1º São também reduzidas a zero as alíquotas do IBS e da CBS sobre o fornecimento de medicamentos '
                     'registrados na Anvisa quando: III – classificados como soros ou vacinas, conforme regulamentação sanitária '
                     'específica',
            'tipo': 'Padrão'},
 '200054': {'artigo': 'Art. 271, § 1º, II',
            'cst': '200',
            'cst_desc': 'Alíquota zero',
            'cte': 0,
            'desc': 'Fornecimento de bem material pela cooperativa de produção agropecuária a associado não sujeito ao regime regular do '
                    'IBS e da CBS com anulação de créditos referentes ao bem fornecido, observado o art. 271 da Lei Complementar nº 214, '
                    'de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento de bem material pela cooperativa de produção agropecuária a associado não sujeito ao regime regular do '
                    'IBS e da CBS',
            'pred_cbs': 100.0,
            'pred_ibs': 100.0,
            'texto': 'Art. 271. As sociedades cooperativas poderão optar por regime específico do IBS e da CBS no qual ficam reduzidas a '
                     'zero as alíquotas do IBS e da CBS incidentes na operação em que: § 1º O disposto no caput deste artigo aplica-se '
                     'também: II - à operação de fornecimento de bem material pela cooperativa de produção agropecuária a associado não '
                     'sujeito ao regime regular do IBS e da CBS, desde que anulados os créditos por ela apropriados referentes ao bem '
                     'fornecido.',
            'tipo': 'Padrão'},
 '200055': {'artigo': 'Art. 128, I, II, VIII, IX, X, XI, XII e XIII',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 60%',
            'cte': 0,
            'desc': 'Fornecimento dos serviços com redução de alíquota de 60% realizado por autônomo, observado o art. 128 da Lei '
                    'Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Fornecimento dos serviços com redução de alíquota de 60% realizado por autônomo',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 128. Desde que observadas as definições e demais disposições deste Capítulo, ficam reduzidas em 60% (sessenta '
                     'por cento) as alíquotas do IBS e da CBS incidentes sobre operações com: I - serviços de educação; II - serviços de '
                     'saúde; VIII - produtos agropecuários, aquícolas, pesqueiros, florestais e extrativistas vegetais in natura; IX - '
                     'insumos agropecuários e aquícolas; X - produções nacionais artísticas, culturais, de eventos, jornalísticas e '
                     'audiovisuais; XI - comunicação institucional; XII - atividades desportivas; e XIII - bens e serviços relacionados à '
                     'soberania e à segurança nacional, à segurança da informação e à segurança cibernética.',
            'tipo': 'Padrão'},
 '200056': {'artigo': 'Art. 127',
            'cst': '200',
            'cst_desc': 'Alíquota reduzida em 30%',
            'cte': 0,
            'desc': 'Fornecimento dos serviços com redução de alíquota de 30% realizado por autônomo, observado o art. 127 da Lei '
                    'Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Fornecimento dos serviços com redução de alíquota de 30% realizado por autônomo',
            'pred_cbs': 30.0,
            'pred_ibs': 30.0,
            'texto': 'Art. 127. Ficam reduzidas em 30% (trinta por cento) as alíquotas do IBS e da CBS incidentes sobre a prestação de '
                     'serviços pelos seguintes profissionais, que exercerem atividades intelectuais de natureza científica, literária ou '
                     'artística, submetidas à fiscalização por conselho profissional: I – administradores; II – advogados; III – '
                     'arquitetos e urbanistas; IV – assistentes sociais; V – bibliotecários; VI – biólogos; VII – contabilistas; VIII – '
                     'economistas; IX – economistas domésticos; X – profissionais de educação física; XI – engenheiros e agrônomos; XII – '
                     'estatísticos; XIII - médicos veterinários e zootecnistas; XIV – museólogos; XV – químicos; XVI – profissionais de '
                     'relações públicas; XVII – técnicos industriais; e XVIII – técnicos agrícolas;',
            'tipo': 'Padrão'},
 '220001': {'artigo': 'Art. 485, I',
            'cst': '220',
            'cst_desc': 'Alíquota fixa',
            'cte': 0,
            'desc': 'Incorporação imobiliária submetida ao regime especial de tributação, observado o art. 485 da Lei Complementar nº 214, '
                    'de 2025.',
            'fim': '2026-01-01',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Incorporação imobiliária submetida ao regime especial de tributação',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 485. O contribuinte que realizar incorporação imobiliária submetida ao patrimônio de afetação, nos termos dos '
                     'artigos 31-A a 31-E da Lei nº 4.591, de 16 de dezembro de 1964, que tenha realizado o pedido de opção pelo regime '
                     'específico instituído pelo art. 1º e tenha o pedido efetivado nos termos do art. 2º, ambos da Lei Federal nº 10.931 '
                     'de 2004, antes de 1º de janeiro de 2029, pode optar pelo recolhimento de CBS, da seguinte forma: I - a incorporação '
                     'imobiliária submetida ao regime especial de tributação prevista nos arts. 4º e 8º da Lei Federal nº 10.931/2004 '
                     'ficará sujeita ao pagamento de CBS em montante equivalente a 2,08% da receita mensal recebida;',
            'tipo': 'Fixa'},
 '220002': {'artigo': 'Art. 485, II',
            'cst': '220',
            'cst_desc': 'Alíquota fixa',
            'cte': 0,
            'desc': 'Incorporação imobiliária submetida ao regime especial de tributação, observado o art. 485 da Lei Complementar nº 214, '
                    'de 2025.',
            'fim': '2026-01-01',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Incorporação imobiliária submetida ao regime especial de tributação',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 485. O contribuinte que realizar incorporação imobiliária submetida ao patrimônio de afetação, nos termos dos '
                     'artigos 31-A a 31-E da Lei nº 4.591, de 16 de dezembro de 1964, que tenha realizado o pedido de opção pelo regime '
                     'específico instituído pelo art. 1º e tenha o pedido efetivado nos termos do art. 2º, ambos da Lei Federal nº 10.931 '
                     'de 2004, antes de 1º de janeiro de 2029, pode optar pelo recolhimento de CBS, da seguinte forma: II - a incorporação '
                     'imobiliária submetida ao regime especial de tributação prevista no § 6º e § 8º do art. 4º e parágrafo único do art. '
                     '8º da Lei Federal nº 10.931/2004 ficará sujeita ao pagamento de CBS em montante equivalente a 0,53% da receita '
                     'mensal recebida.',
            'tipo': 'Fixa'},
 '220003': {'artigo': 'Art. 486',
            'cst': '220',
            'cst_desc': 'Alíquota fixa',
            'cte': 0,
            'desc': 'Alienação de imóvel decorrente de parcelamento do solo, observado o art. 486 da Lei Complementar nº 214, de 2025.',
            'fim': '2026-01-01',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Alienação de imóvel decorrente de parcelamento do solo',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 486. O contribuinte que realizar alienação de imóvel decorrente de parcelamento do solo, que tenha o pedido de '
                     'registro do parcelamento, nos termos da Lei Federal nº 6.766, de 19 de dezembro de 1979, efetivado antes de 1º de '
                     'janeiro de 2029, pode optar pelo recolhimento de CBS com base na receita bruta recebida. § 1º As operações sujeitas '
                     'ao regime de que trata este artigo estarão sujeitas ao pagamento de CBS em montante equivalente a 3,65% da receita '
                     'bruta recebida.',
            'tipo': 'Fixa'},
 '221001': {'artigo': 'Art. 487, § 2º',
            'cst': '221',
            'cst_desc': 'Alíquota fixa proporcional',
            'cte': 0,
            'desc': 'Locação, cessão onerosa ou arrendamento de bem imóvel com alíquota sobre a receita bruta, observado o art. 487 da Lei '
                    'Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Locação, cessão onerosa ou arrendamento de bem imóvel com alíquota sobre a receita bruta',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 487. O contribuinte que realizar locação, cessão onerosa ou arrendamento de bem imóvel decorrente de contratos '
                     'firmados por prazo determinado poderá optar pelo recolhimento de IBS e CBS com base na receita bruta recebida. § 2º '
                     'As operações sujeitas ao regime de que trata este artigo estarão sujeitas ao pagamento de IBS e CBS em montante '
                     'equivalente a 3,65% da receita bruta recebida.',
            'tipo': 'Fixa'},
 '221002': {'artigo': 'Art. 485, I',
            'cst': '221',
            'cst_desc': 'Alíquota fixa proporcional',
            'cte': 0,
            'desc': 'Incorporação imobiliária submetida ao regime especial de tributação, observado o art. 485 da Lei Complementar nº 214, '
                    'de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Incorporação imobiliária submetida ao regime especial de tributação',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 485. O contribuinte que realizar incorporação imobiliária submetida ao patrimônio de afetação, nos termos dos '
                     'arts. 31-A a 31-E da Lei nº 4.591, de 16 de dezembro de 1964, que tenha realizado o pedido de opção pelo regime '
                     'específico instituído pelo art. 1º e tenha o pedido efetivado nos termos do art. 2º, ambos da Lei nº 10.931 de 2 de '
                     'agosto de 2004, antes de 1º de janeiro de 2029, pode optar pelo recolhimento de IBS e de CBS, da seguinte forma: I - '
                     'a incorporação imobiliária submetida ao regime especial de tributação prevista nos arts. 4º e 8º da Lei nº 10.931, '
                     'de 2 de agosto de 2004, será sujeita ao pagamento de IBS e de CBS em montante equivalente a 2,08% (dois inteiros e '
                     'oito centésimos por cento) da receita mensal recebida;',
            'tipo': 'Fixa'},
 '221003': {'artigo': 'Art. 485, II',
            'cst': '221',
            'cst_desc': 'Alíquota fixa proporcional',
            'cte': 0,
            'desc': 'Incorporação imobiliária submetida ao regime especial de tributação, observado o art. 485 da Lei Complementar nº 214, '
                    'de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Incorporação imobiliária submetida ao regime especial de tributação',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 485. O contribuinte que realizar incorporação imobiliária submetida ao patrimônio de afetação, nos termos dos '
                     'arts. 31-A a 31-E da Lei nº 4.591, de 16 de dezembro de 1964, que tenha realizado o pedido de opção pelo regime '
                     'específico instituído pelo art. 1º e tenha o pedido efetivado nos termos do art. 2º, ambos da Lei nº 10.931 de 2 de '
                     'agosto de 2004, antes de 1º de janeiro de 2029, pode optar pelo recolhimento de IBS e de CBS, da seguinte forma: II '
                     '- a incorporação imobiliária submetida ao regime especial de tributação prevista nos §§ 6º e 8º do art. 4º e no '
                     'parágrafo único do art. 8º da Lei nº 10.931, de 2 de agosto de 2004, será sujeita ao pagamento de IBS e de CBS em '
                     'montante equivalente a 0,53% (cinquenta e três centésimos por cento) da receita mensal recebida.',
            'tipo': 'Fixa'},
 '221004': {'artigo': 'Art. 486',
            'cst': '221',
            'cst_desc': 'Alíquota fixa proporcional',
            'cte': 0,
            'desc': 'Alienação de imóvel decorrente de parcelamento do solo, observado o art. 486 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Alienação de imóvel decorrente de parcelamento do solo',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 486. O contribuinte que realizar alienação de imóvel decorrente de parcelamento do solo, que tenha o pedido de '
                     'registro do parcelamento, nos termos da Lei nº 6.766, de 19 de dezembro de 1979, efetivado antes de 1º de janeiro de '
                     '2029, pode optar pelo recolhimento de IBS e de CBS com base na receita bruta recebida. § 1º As operações sujeitas ao '
                     'regime de que trata este artigo estarão sujeitas ao pagamento de IBS e de CBS em montante equivalente a 3,65% (três '
                     'inteiros e sessenta e cinco centésimos por cento) da receita bruta recebida.',
            'tipo': 'Fixa'},
 '222001': {'artigo': 'Art. 12 § 8º',
            'cst': '222',
            'cst_desc': 'Redução de Base de Cálculo',
            'cte': 0,
            'desc': 'Transporte internacional de passageiros, caso os trechos de ida e volta sejam vendidos em conjunto, a base de cálculo '
                    'será a metade do valor cobrado, observado o Art. 12 § 8º da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Transporte internacional de passageiros, caso os trechos de ida e volta sejam vendidos em conjunto',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 12. § 8º No transporte internacional de passageiros, caso os trechos de ida e volta sejam vendidos em conjunto, '
                     'a base de cálculo será a metade do valor cobrado.',
            'tipo': 'Padrão'},
 '400001': {'artigo': 'Art. 157',
            'cst': '400',
            'cst_desc': 'Isenção',
            'cte': 0,
            'desc': 'Fornecimento de serviços de transporte público coletivo de passageiros rodoviário e metroviário de caráter urbano, '
                    'semiurbano e metropolitano, sob regime de autorização, permissão ou concessão pública, observado o art. 157 da Lei '
                    'Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Fornecimento de serviços de transporte público coletivo de passageiros rodoviário e metroviário',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 157. Fica isento do IBS e da CBS o fornecimento de serviços de transporte público coletivo de passageiros '
                     'rodoviário e metroviário de caráter urbano, semiurbano e metropolitano, sob regime de autorização, permissão ou '
                     'concessão pública.',
            'tipo': 'Sem alíquota'},
 '400002': {'artigo': 'Art. 157',
            'cst': '400',
            'cst_desc': 'Isenção',
            'cte': 0,
            'desc': 'Fornecimento de serviços de transporte público coletivo de passageiros rodoviário e metroviário de caráter urbano, '
                    'semiurbano e metropolitano, sob regime de autorização, permissão ou concessão pública, com medição por quilômetro '
                    'rodado, observado o art. 157 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Fornecimento de serviços de transporte público coletivo de passageiros rodoviário e metroviário com medição por '
                    'quilômetro rodado',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 157. Fica isento do IBS e da CBS o fornecimento de serviços de transporte público coletivo de passageiros '
                     'rodoviário e metroviário de caráter urbano, semiurbano e metropolitano, sob regime de autorização, permissão ou '
                     'concessão pública.',
            'tipo': 'Sem alíquota'},
 '400003': {'artigo': 'Art. 94 I',
            'cst': '400',
            'cst_desc': 'Isenção',
            'cte': 0,
            'desc': 'Bagagens de viajantes e de tripulantes, acompanhadas ou desacompanhadas, observado o art. 94 da Lei Complementar nº '
                    '214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Bagagens',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 94. São isentas do pagamento do IBS e da CBS na importação de bens materiais: I - bagagens de viajantes e de '
                     'tripulantes, acompanhadas ou desacompanhadas; e',
            'tipo': 'Sem alíquota'},
 '400004': {'artigo': 'Art. 94 II',
            'cst': '400',
            'cst_desc': 'Isenção',
            'cte': 0,
            'desc': 'Remessas internacionais, observado o art. 94 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Remessas internacionais',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 94. São isentas do pagamento do IBS e da CBS na importação de bens materiais: II - remessas internacionais, '
                     'desde que: a) sejam isentas do Imposto sobre a Importação; b) o remetente e o destinatário sejam pessoas físicas; e '
                     'c) não tenha ocorrido a intermediação de plataforma digital.',
            'tipo': 'Sem alíquota'},
 '410001': {'artigo': 'Art. 5º, § 1º, I',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 1,
            'desc': 'Fornecimento de bonificações quando constem do respectivo documento fiscal e que não dependam de evento posterior, '
                    'observado o art. 5º da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento de bonificações quando constem no documento fiscal e que não dependam de evento posterior',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 5º O IBS e a CBS também incidem sobre as seguintes operações: II – fornecimento de brindes e bonificações; § 1º '
                     'O disposto no inciso II do caput deste artigo: I – não se aplica às bonificações que constem do respectivo documento '
                     'fiscal e que não dependam de evento posterior;',
            'tipo': 'Sem alíquota'},
 '410002': {'artigo': 'Art. 6º, II',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Transferências entre estabelecimentos pertencentes ao mesmo contribuinte, observado o art. 6º da Lei Complementar nº '
                    '214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Transferências entre estabelecimentos pertencentes ao mesmo contribuinte',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 6º O IBS e a CBS não incidem sobre: II - transferência de bens entre estabelecimentos pertencentes ao mesmo '
                     'contribuinte, observada a obrigatoriedade de emissão de documento fiscal eletrônico, nos termos do inciso II do § 2º '
                     'do art. 60 desta Lei Complementar;',
            'tipo': 'Sem alíquota'},
 '410003': {'artigo': 'Art. 6º, VIII',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 1,
            'desc': 'Doações que não tenham por objeto bens ou serviços que tenham permitido a apropriação de créditos pelo doador, '
                    'observado o art. 6º da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Doações sem contraprestação em benefício do doador',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 6º O IBS e a CBS não incidem sobre: VIII – doações sem contraprestação em benefício do doador;',
            'tipo': 'Sem alíquota'},
 '410004': {'artigo': 'Art. 8º',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 1,
            'desc': 'Exportações de bens e serviços, observado o art. 8º da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Exportações de bens e serviços',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 8º São imunes ao IBS e à CBS as exportações de bens e de serviços, nos termos do Capítulo V deste Título.',
            'tipo': 'Sem alíquota'},
 '410005': {'artigo': 'Art. 9º, I e § 1º',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Fornecimentos realizados pela União, pelos Estados, pelo Distrito Federal e pelos Municípios, observado o art. 9º da '
                    'Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimentos realizados pela União, pelos Estados, pelo Distrito Federal e pelos Municípios',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 9º São imunes também ao IBS e à CBS os fornecimentos: I – realizados pela União, pelos Estados, pelo Distrito '
                     'Federal e pelos Municípios; § 1º A imunidade prevista no inciso I do caput deste artigo é extensiva às autarquias e '
                     'às fundações instituídas e mantidas pelo poder público e à empresa pública prestadora de serviço postal, bem como:',
            'tipo': 'Sem alíquota'},
 '410006': {'artigo': 'Art. 9º, II',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Fornecimentos realizados por entidades religiosas e templos de qualquer culto, inclusive suas organizações '
                    'assistenciais e beneficentes, observado o art. 9º da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimentos realizados por entidades religiosas e templos de qualquer culto',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 9º São imunes também ao IBS e à CBS os fornecimentos: II - realizados por entidades religiosas e templos de '
                     'qualquer culto, inclusive suas organizações assistenciais e beneficentes;',
            'tipo': 'Sem alíquota'},
 '410007': {'artigo': 'Art. 9º, III',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Fornecimentos realizados por partidos políticos, inclusive suas fundações, entidades sindicais dos trabalhadores e '
                    'instituições de educação e de assistência social, sem fins lucrativos, observado o art. 9º da Lei Complementar nº '
                    '214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimentos realizados por partidos políticos, entidades sindicais e instituições de educação e de assistência '
                    'social',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 9º São imunes também ao IBS e à CBS os fornecimentos: III - realizados por partidos políticos, inclusive seus '
                     'institutos e fundações, entidades sindicais dos trabalhadores e instituições de educação e de assistência social, '
                     'sem fins lucrativos;',
            'tipo': 'Sem alíquota'},
 '410008': {'artigo': 'Art. 9º, IV',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Fornecimentos de livros, jornais, periódicos e do papel destinado a sua impressão, observado o art. 9º da Lei '
                    'Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimentos de livros, jornais, periódicos e do papel destinado a sua impressão',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 9º São imunes também ao IBS e à CBS os fornecimentos: IV – de livros, jornais, periódicos e do papel destinado '
                     'a sua impressão;',
            'tipo': 'Sem alíquota'},
 '410009': {'artigo': 'Art. 9º, V',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Fornecimentos de fonogramas e videofonogramas musicais produzidos no Brasil contendo obras musicais ou literomusicais '
                    'de autores brasileiros e/ou obras em geral interpretadas por artistas brasileiros, bem como os suportes materiais ou '
                    'arquivos digitais que os contenham, salvo na etapa de replicação industrial de mídias ópticas de leitura a laser, '
                    'observado o art. 9º da Lei Complementar nº 214, de …',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimentos de fonogramas e videofonogramas musicais produzidos no Brasil',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 9º São imunes também ao IBS e à CBS os fornecimentos: V - de fonogramas e videofonogramas musicais produzidos '
                     'no Brasil contendo obras musicais ou literomusicais de autores brasileiros e/ou obras em geral interpretadas por '
                     'artistas brasileiros, bem como os suportes materiais ou arquivos digitais que os contenham, salvo na etapa de '
                     'replicação industrial de mídias ópticas de leitura a laser;',
            'tipo': 'Sem alíquota'},
 '410010': {'artigo': 'Art. 9º, VI',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Fornecimentos de serviço de comunicação nas modalidades de radiodifusão sonora e de sons e imagens de recepção livre '
                    'e gratuita, observado o art. 9º da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Fornecimentos de serviço de comunicação nas modalidades de radiodifusão sonora e de sons e imagens de recepção livre '
                    'e gratuita',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 9º São imunes também ao IBS e à CBS os fornecimentos: VI - de serviço de comunicação nas modalidades de '
                     'radiodifusão sonora e de sons e imagens de recepção livre e gratuita; e',
            'tipo': 'Sem alíquota'},
 '410011': {'artigo': 'Art. 9º, VII',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Fornecimentos de ouro, quando definido em lei como ativo financeiro ou instrumento cambial, observado o art. 9º da '
                    'Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Fornecimentos de ouro, quando definido em lei como ativo financeiro ou instrumento cambial',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 9º São imunes também ao IBS e à CBS os fornecimentos: VII - de ouro, quando definido em lei como ativo '
                     'financeiro ou instrumento cambial.',
            'tipo': 'Sem alíquota'},
 '410012': {'artigo': 'Art. 26, § 2º, II',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Fornecimento de condomínio edilício não optante pelo regime regular, observado o art. 26 da Lei Complementar nº 214, '
                    'de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento de condomínio edilício não optante pelo regime regular',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 26. Não são contribuintes do IBS e da CBS, ressalvado o disposto no inciso II do § 1º do art. 156-A da '
                     'Constituição Federal: I – condomínio edilício; § 2º Em relação ao condomínio edilício de que trata o inciso I do '
                     'caput deste artigo: I - caso exerça a opção pelo regime regular, nos termos do § 1º deste artigo, o IBS e a CBS '
                     'incidirão sobre todas as taxas e demais valores cobrados pelo condomínio dos seus condôminos e de terceiros; e II – '
                     'caso não exerça a opção pelo regime regular e desde que as taxas e demais valores condominiais cobrados de seus '
                     'condôminos representem menos de 80% (oitenta por cento) da receita total do condomínio: a) ficará sujeito à '
                     'incidência do IBS e da CBS sobre as operações com bens e com serviços que realizar de acordo com o disposto no '
                     'inciso I do caput do art. 21 desta Lei Complementar; e b) apropriará créditos na proporção da receita decorrente das '
                     '…',
            'tipo': 'Sem alíquota'},
 '410013': {'artigo': 'Art. 98',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Exportações de combustíveis, observado o art. 98 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Exportações de combustíveis',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 98. Considera-se exportação o fornecimento de combustível ou lubrificante para abastecimento de aeronaves em '
                     'tráfego internacional e com destino ao exterior.',
            'tipo': 'Sem alíquota'},
 '410014': {'artigo': 'Art. 164',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Fornecimento de produtor rural não contribuinte, observado o art. 164 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento de produtor rural não contribuinte',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 164. O produtor rural pessoa física ou jurídica que auferir receita inferior a R$ 3.600.000,00 (três milhões e '
                     'seiscentos mil reais) no ano-calendário e o produtor rural integrado não serão considerados contribuintes do IBS e '
                     'da CBS.',
            'tipo': 'Sem alíquota'},
 '410015': {'artigo': 'Art. 169',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 1,
            'desc': 'Fornecimento por transportador autônomo não contribuinte, observado o art. 169 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Fornecimento por transportador autônomo não contribuinte',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 169. O contribuinte de IBS e de CBS sujeito ao regime regular poderá apropriar créditos presumidos dos '
                     'referidos tributos relativos às aquisições de serviço de transporte de carga de transportador autônomo pessoa física '
                     'que não seja contribuinte dos referidos tributos ou que seja inscrito como MEI.',
            'tipo': 'Sem alíquota'},
 '410016': {'artigo': 'Art. 170',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Fornecimento ou aquisição de resíduos sólidos, observado o art. 170 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Fornecimento ou aquisição de resíduos sólidos',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 170. O contribuinte de IBS e de CBS sujeito ao regime regular poderá apropriar créditos presumidos dos '
                     'referidos tributos relativos às aquisições de resíduos sólidos de coletores incentivados para utilização em processo '
                     'de destinação final ambientalmente adequada.',
            'tipo': 'Sem alíquota'},
 '410017': {'artigo': 'Art. 171',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Aquisição de bem móvel com crédito presumido sob condição de revenda realizada, observado o art. 171 da Lei '
                    'Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Aquisição de bem móvel com crédito presumido sob condição de revenda realizada',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 171. O contribuinte de IBS e de CBS sujeito ao regime regular poderá apropriar créditos presumidos dos '
                     'referidos tributos relativos às aquisições, para revenda, de bem móvel usado de pessoa física que não seja '
                     'contribuinte dos referidos tributos ou que seja inscrita como MEI.',
            'tipo': 'Sem alíquota'},
 '410018': {'artigo': 'Art. 213',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Operações relacionadas aos fundos garantidores e executores de políticas públicas, inclusive de habitação, previstos '
                    'em lei, assim entendidas os serviços prestados ao fundo pelo seu agente operador e por entidade encarregada da sua '
                    'administração, observado o art. 213 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Operações relacionadas aos fundos garantidores e executores de políticas públicas',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 213. Não ficam sujeitas à incidência do IBS e da CBS as operações relacionadas aos demais fundos garantidores e '
                     'executores de políticas públicas, inclusive de habitação e de desenvolvimento regional, previstos em lei.',
            'tipo': 'Sem alíquota'},
 '410019': {'artigo': 'Art. 274, I',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Exclusão da gorjeta na base de cálculo no fornecimento de alimentação, observado o art. 274 da Lei Complementar nº '
                    '214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Exclusão da gorjeta na base de cálculo no fornecimento de alimentação',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 274. A base de cálculo do IBS e da CBS é o valor da operação de fornecimento de alimentação e das bebidas de '
                     'que trata o § 1o do art. 273 desta Lei Complementar. Parágrafo único. Ficam excluídos da base de cálculo: I - a '
                     'gorjeta incidente no fornecimento de alimentação, desde que: a) seja repassada integralmente ao empregado, sem '
                     'prejuízo dos valores da gorjeta que forem retidos pelo empregador em virtude de determinação legal; e b) seu valor '
                     'não exceda a 15% (quinze por cento) do valor total do fornecimento de alimento e bebidas;',
            'tipo': 'Sem alíquota'},
 '410020': {'artigo': 'Art. 274, II',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Exclusão do valor de intermediação na base de cálculo no fornecimento de alimentação, observado o art. 274 da Lei '
                    'Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Exclusão do valor de intermediação na base de cálculo no fornecimento de alimentação',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 274. A base de cálculo do IBS e da CBS é o valor da operação de fornecimento de alimentação e das bebidas de '
                     'que trata o § 1º do art. 273 desta Lei Complementar. Parágrafo único. Ficam excluídos da base de cálculo: II - os '
                     'valores não repassados aos bares e restaurantes pelo serviço de entrega e intermediação de pedidos de alimentação e '
                     'bebidas por plataforma digital.',
            'tipo': 'Sem alíquota'},
 '410021': {'artigo': 'Art. 12 § 2º',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Contribuição de que trata o art. 149-A da Constituição Federal, observado o art. 12 da Lei Complementar nº 214, de '
                    '2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Contribuição de que trata o art. 149-A da Constituição Federal',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 12 § 2º Não integram a base de cálculo do IBS e da CBS: VI - a contribuição de que trata o art. 149-A da '
                     'Constituição Federal.',
            'tipo': 'Sem alíquota'},
 '410022': {'artigo': 'Art. 200, I',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Consolidação da propriedade pelo credor de bens móveis ou imóveis que tenham sido objeto de garantia, observado o '
                    'art. 200 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Consolidação da propriedade do bem pelo credor',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 200. Na alienação de bens móveis ou imóveis que tenham sido objeto de garantia constituída em favor de credor '
                     'sujeito ao regime específico desta Seção, cuja propriedade tenha sido por ele consolidada ou a ele transmitida em '
                     'pagamento da dívida, deverá ser observado o seguinte: I - a consolidação da propriedade do bem pelo credor não '
                     'estará sujeita à incidência do IBS e da CBS;',
            'tipo': 'Sem alíquota'},
 '410023': {'artigo': 'Art. 200, II, a',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Alienação de bens móveis ou imóveis que tenham sido objeto de garantia constituída em favor de credor em que o '
                    'prestador da garantia não seja contribuinte, observado o art. 200 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Alienação de bens móveis ou imóveis que tenham sido objeto de garantia em que o prestador da garantia não seja '
                    'contribuinte',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 200. Na alienação de bens móveis ou imóveis que tenham sido objeto de garantia constituída em favor de credor '
                     'sujeito ao regime específico desta Seção, cuja propriedade tenha sido por ele consolidada ou a ele transmitida em '
                     'pagamento da dívida, deverá ser observado o seguinte: II - na alienação do bem pelo credor: a) não haverá incidência '
                     'do IBS e da CBS, se o prestador da garantia não for contribuinte desses tributos;',
            'tipo': 'Sem alíquota'},
 '410024': {'artigo': 'Art. 204, § 3º, I',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Consolidação da propriedade pelo grupo de consórcio de bem que tenha sido objeto de garantia, observado o art. 204 da '
                    'Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Consolidação da propriedade do bem pelo grupo de consórcio',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 204. Na administração de consórcio de que trata o inciso VII do caput do art. 182 desta Lei Complementar, para '
                     'fins de determinação da base de cálculo, as receitas dos serviços compreendem todas as tarifas, comissões e taxas, '
                     'bem como os respectivos encargos, multas e juros, decorrentes de contrato de participação em grupo de consórcio, '
                     'efetivamente pagas, pelo regime de caixa. § 3º Na execução de garantia de consorciado, com recebimento dos valores '
                     'pelo grupo de consórcio, deverá ser observado o seguinte: I - a consolidação da propriedade do bem pelo grupo de '
                     'consórcio não estará sujeita à incidência do IBS e da CBS;',
            'tipo': 'Sem alíquota'},
 '410025': {'artigo': 'Art. 204, § 3º II, a',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Alienação de bem que tenha sido objeto de garantia constituída em favor do grupo de consórcio em que o prestador da '
                    'garantia não seja contribuinte, observado o art. 204 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Alienação de bem que tenha sido objeto de garantia em que o prestador da garantia não seja contribuinte',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 204. Na administração de consórcio de que trata o inciso VII do caput do art. 182 desta Lei Complementar, para '
                     'fins de determinação da base de cálculo, as receitas dos serviços compreendem todas as tarifas, comissões e taxas, '
                     'bem como os respectivos encargos, multas e juros, decorrentes de contrato de participação em grupo de consórcio, '
                     'efetivamente pagas, pelo regime de caixa. § 3º Na execução de garantia de consorciado, com recebimento dos valores '
                     'pelo grupo de consórcio, deverá ser observado o seguinte: II - na alienação do bem pelo grupo de consórcio: a) não '
                     'haverá incidência do IBS e da CBS, se o consorciado não for contribuinte do IBS e da CBS;',
            'tipo': 'Sem alíquota'},
 '410026': {'artigo': 'Art. 6º, § 2º II',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 1,
            'desc': 'Doações sem contraprestação em benefício do doador, com anulação de crédito apropriados pelo doador referente ao '
                    'fornecimento doado, observado o art. 6º da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Doação com anulação de crédito',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 6º O IBS e a CBS não incidem sobre: VIII - doações sem contraprestação em benefício do doador; § 2º Caso as '
                     'doações de que trata o inciso VIII do caput deste artigo tenham por objeto bens ou serviços que tenham permitido a '
                     'apropriação de créditos pelo doador, inclusive na produção: II - por opção do contribuinte, os créditos serão '
                     'anulados.',
            'tipo': 'Sem alíquota'},
 '410027': {'artigo': 'Art. 80 II',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 1,
            'desc': 'Fornecimento de bens e serviços, desde que vinculados direta e exclusivamente à exportação de bens materiais ou '
                    'associados à entrega no exterior de bens materiais, observado o art. 6º da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Exportação de serviço ou de bem imaterial',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 80. Para fins do disposto no art. 79 desta Lei Complementar, considera-se exportação de serviço ou de bem '
                     'imaterial, inclusive direitos, o fornecimento para residente ou domiciliado no exterior e consumo no exterior. II - '
                     'o fornecimento dos seguintes bens e serviços, desde que vinculados direta e exclusivamente à exportação de bens '
                     'materiais ou associados à entrega no exterior de bens materiais: a) intermediação na distribuição de mercadorias no '
                     'exterior (comissão de agente); b) seguro de cargas; c) despacho aduaneiro; d) armazenagem de mercadorias; e) '
                     'transporte rodoviário, ferroviário, aéreo, aquaviário ou multimodal de cargas; f) manuseio de cargas; g) manuseio de '
                     'contêineres; h) unitização ou desunitização de cargas; i) consolidação ou desconsolidação documental de cargas; j) '
                     'agenciamento de transporte de cargas; k) remessas expressas; l) pesagem e medição de cargas; m) …',
            'tipo': 'Sem alíquota'},
 '410028': {'artigo': 'Art. 251, § 1º',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Operações com bens imóveis realizadas por pessoas físicas não consideradas contribuintes do regime regular do IBS e '
                    'da CBS, observado o art. 251 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Operações com bens imóveis realizadas por pessoas físicas não consideradas contribuintes',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 251. As operações com bens imóveis realizadas por contribuintes que apurarem o IBS e a CBS no regime regular '
                     'ficam sujeitas ao regime específico previsto neste Capítulo. § 1º As pessoas físicas que realizarem operações com '
                     'bens imóveis serão consideradas contribuintes do regime regular do IBS e da CBS e sujeitas ao regime de que trata '
                     'este Capítulo, nos casos de:',
            'tipo': 'Sem alíquota'},
 '410029': {'artigo': 'Art. 4º',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Operações não sujeitas à incidência de IBS e de CBS, alcançadas apenas por obrigação acessória do ICMS, observado o '
                    'art. 4º da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Operações acobertadas somente pelo ICMS',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 4º O IBS e a CBS incidem sobre operações onerosas com bens ou com serviços. § 2º Para fins do disposto neste '
                     'artigo, considera-se operação onerosa com bens ou com serviços qualquer fornecimento com contraprestação, incluindo '
                     'o decorrente de: I - compra e venda, troca ou permuta, dação em pagamento e demais espécies de alienação; II - '
                     'locação; III - licenciamento, concessão, cessão; IV - mútuo oneroso; V - doação com contraprestação em benefício do '
                     'doador; VI - instituição onerosa de direitos reais; VII - arrendamento, inclusive mercantil; e VIII - prestação de '
                     'serviços.',
            'tipo': 'Sem alíquota'},
 '410030': {'artigo': 'Art. 47, § 6º',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Estorno de crédito apropriado de bens adquiridos e venham a perecer, deteriorar-se ou ser objeto de roubo, furto ou '
                    'extravio, observado o art. 47 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Estorno de crédito por perecimento, deteriorização, roubo, furto ou extravio.',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 47. O contribuinte sujeito ao regime regular poderá apropriar créditos do IBS e da CBS quando ocorrer a '
                     'extinção por qualquer das modalidades previstas no art. 27 dos débitos relativos às operações em que seja '
                     'adquirente, excetuadas exclusivamente aquelas consideradas de uso ou consumo pessoal, nos termos do art. 57 desta '
                     'Lei Complementar, e as demais hipóteses previstas nesta Lei Complementar. § 6º O adquirente deverá estornar o '
                     'crédito apropriado caso o bem adquirido venha a perecer, deteriorar-se ou ser objeto de roubo, furto ou extravio.',
            'tipo': 'Sem alíquota'},
 '410031': {'artigo': 'Art. 544, VI',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Fornecimento em período anterior ao início de vigência de incidências de CBS e IBS, observado o art. 544 da Lei '
                    'Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Fornecimento em período anterior ao início de vigência de incidências de CBS e IBS',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 544. Esta Lei Complementar entra em vigor na data de sua publicação, produzindo efeitos: VI - a partir de 1º de '
                     'janeiro de 2026, em relação aos demais dispositivos.',
            'tipo': 'Sem alíquota'},
 '410032': {'artigo': 'Art. 12, §2º V',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Tributos incidentes na operação que não integram a base de cálculo do IBS e da CBS, observado o art. 12 da Lei '
                    'Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Tributos incidentes na operação que não integram a base de cálculo do IBS e da CBS',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 12. § 2º Não integram a base de cálculo do IBS e da CBS: V - o montante incidente na operação dos tributos a '
                     'que se referem o inciso II do caput do art. 155, o inciso III do caput do art. 156 e a alínea “b” do inciso I e o '
                     'inciso IV do caput do art. 195 da Constituição Federal, e da Contribuição para os Programas de Integração Social e '
                     'de Formação do Patrimônio do Servidor Público (Contribuição para o PIS/Pasep) a que se refere o art. 239 da '
                     'Constituição Federal, de 1º de janeiro de 2026 a 31 de dezembro de 2032;',
            'tipo': 'Sem alíquota'},
 '410033': {'artigo': 'Art. 26, § 5º-A, I e II',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Operações com bens imóveis, inclusive operações com direitos reais sobre bens imóveis, realizadas por Fundos de '
                    'Investimento Imobiliário (FII) e Fundos de Investimento nas Cadeias Produtivas do Agronegócio (Fiagro), observado o '
                    'art. 26 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Operações de Fundos de Investimento Imobiliário (FII) e Fundos de Investimento nas Cadeias Produtivas do Agronegócio '
                    '(Fiagro)',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 26. § 5º-A. Para fins do disposto no inciso V do caput deste artigo, não são contribuintes do IBS e da CBS: I – '
                     'os Fundos de Investimento Imobiliário (FII) e os Fundos de Investimento nas Cadeias Produtivas do Agronegócio '
                     '(Fiagro), de que trata a Lei nº 8.668, de 25 de junho de 1993, que realizem operações com bens imóveis, inclusive '
                     'operações com direitos reais sobre bens imóveis, e que, cumulativamente: (...) II – os FII e os Fiagro que realizem '
                     'operações com bens imóveis, inclusive operações com direitos reais sobre bens imóveis, e que não atendam às '
                     'condições estabelecidas no inciso I deste parágrafo, cujas cotas sejam detidas, direta ou indiretamente, em mais de '
                     '95% (noventa e cinco por cento), por:',
            'tipo': 'Sem alíquota'},
 '410034': {'artigo': 'Art. 26, § 5º-A, III',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Fundos de investimento cujo patrimônio seja constituído exclusivamente por aplicações em participações societárias, '
                    'certificados, direitos, títulos, valores mobiliários e demais ativos financeiros permitidos pela Comissão de Valores '
                    'Mobiliários, observado o art. 26 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Operações de fundos de investimento',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 26. § 5º-A. Para fins do disposto no inciso V do caput deste artigo, não são contribuintes do IBS e da CBS: III '
                     '– os demais fundos de investimento cujo patrimônio seja constituído exclusivamente por aplicações em participações '
                     'societárias, certificados, direitos, títulos, valores mobiliários e demais ativos financeiros permitidos pela '
                     'Comissão de Valores Mobiliários, observado o disposto no § 6º-A e no § 8º-A deste artigo.',
            'tipo': 'Sem alíquota'},
 '410035': {'artigo': 'Art. 26, IV',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 1,
            'desc': 'Fornecimento realizado por nanoempreendedor, observado o art. 26 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Fornecimento realizado por nanoempreendedor',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 26. Não são contribuintes do IBS e da CBS, ressalvado o disposto no inciso II do § 1º do art. 156-A da '
                     'Constituição Federal: IV - nanoempreendedor, assim entendido a pessoa física que tenha auferido receita bruta '
                     'inferior a 50% (cinquenta por cento) do limite estabelecido para adesão ao regime do MEI previsto no § 1º do art. '
                     '18-A observado ainda o disposto nos §§ 4º e 4º-B do referido artigo da Lei Complementar nº 123, de 14 de dezembro de '
                     '2006, e não tenha aderido a esse regime',
            'tipo': 'Sem alíquota'},
 '410036': {'artigo': 'Art. 12, §2º III',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Descontos financeiros em nota fatura, observado o art. 12 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Descontos financeiros em nota fatura',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 12. A base de cálculo do IBS e da CBS é o valor da operação, salvo disposição em contrário prevista nesta Lei '
                     'Complementar. § 2º Não integram a base de cálculo do IBS e da CBS: III - os descontos incondicionais;',
            'tipo': 'Sem alíquota'},
 '410037': {'artigo': 'Art. 66, I,III e VII',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 0,
            'desc': 'Importação os bens materiais sem incidência de IBS e CBS, observado o art. 66 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Importação os bens materiais sem incidência de IBS e CBS',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 66. Não constituem fatos geradores do IBS e da CBS sobre a importação os bens materiais: I - que retornem ao '
                     'País nas seguintes hipóteses: a) enviados em consignação e não vendidos no prazo autorizado; b) devolvidos por '
                     'motivo de defeito técnico, para reparo ou para substituição; c) por motivo de modificações na sistemática de '
                     'importação por parte do país importador; d) por motivo de guerra ou de calamidade pública; ou e) por outros fatores '
                     'alheios à vontade do exportador; III - que sejam idênticos, em igual quantidade e valor, e que se destinem à '
                     'reposição de outros anteriormente importados que se tenham revelado, após sua liberação pela autoridade aduaneira, '
                     'defeituosos ou imprestáveis para o fim a que se destinavam, nos termos do regulamento;e regulam a atividade '
                     'pesqueira; VII - aos quais tenha sido aplicado o regime de exportação temporária;',
            'tipo': 'Sem alíquota'},
 '410999': {'artigo': 'Art. 4º, § 1º',
            'cst': '410',
            'cst_desc': 'Imunidade e não incidência',
            'cte': 1,
            'desc': 'Operações não onerosas sem previsão de tributação, não especificadas anteriormente, observado o art. 4º da Lei '
                    'Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Operações não onerosas sem previsão de tributação, não especificadas anteriormente',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 4º O IBS e a CBS incidem sobre operações onerosas com bens ou com serviços. § 1º As operações não onerosas com '
                     'bens ou com serviços serão tributadas nas hipóteses expressamente previstas nesta Lei Complementar.',
            'tipo': 'Sem alíquota'},
 '510001': {'artigo': 'Art. 28, § 1º',
            'cst': '510',
            'cst_desc': 'Diferimento',
            'cte': 0,
            'desc': 'Operações, sujeitas a diferimento, com energia elétrica ou com direitos a ela relacionados, relativas à importação, '
                    'geração, comercialização, distribuição e transmissão, observado o art. 28 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Operações, sujeitas a diferimento, com energia elétrica, relativas à importação, geração, comercialização, '
                    'distribuição e transmissão',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 28. Nas operações com energia elétrica ou com direitos a ela relacionados, o recolhimento do IBS e da CBS '
                     'relativo a importação, geração, comercialização, distribuição e transmissão será realizado exclusivamente: § 1º O '
                     'recolhimento do IBS e da CBS incidentes nas operações com energia elétrica, ou com direitos a ela relacionados, '
                     'relativas a importação, geração, comercialização, distribuição e transmissão ocorrerá somente no fornecimento: I - '
                     'para consumo; ou II - para contribuinte não sujeito ao regime regular do IBS e da CBS.',
            'tipo': 'Sem alíquota'},
 '515001': {'artigo': 'Art. 138, § 2º',
            'cst': '515',
            'cst_desc': 'Diferimento com redução de alíquota',
            'cte': 0,
            'desc': 'Operações, sujeitas a diferimento, com insumos agropecuários e aquícolas, observado o art. 138 da Lei Complementar nº '
                    '214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Operações, sujeitas a diferimento, com insumos agropecuários e aquícolas (Anexo IX)',
            'pred_cbs': 60.0,
            'pred_ibs': 60.0,
            'texto': 'Art. 138. Ficam reduzidas em 60% (sessenta por cento) as alíquotas do IBS e da CBS incidentes sobre o fornecimento '
                     'dos insumos agropecuários e aquícolas relacionados no Anexo IX desta Lei Complementar, com a especificação das '
                     'respectivas classificações da NCM/SH e da NBS. § 2º Fica diferido o recolhimento do IBS e da CBS incidentes nas '
                     'seguintes operações com insumos agropecuários e aquícolas de que trata o caput:',
            'tipo': 'Padrão'},
 '550001': {'artigo': 'Art. 82',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Exportações de bens materiais, observado o art. 82 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Exportações de bens materiais',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 82. Poderá ser suspenso o pagamento do IBS e da CBS no fornecimento de bens materiais com o fim específico de '
                     'exportação a empresa comercial exportadora que atenda cumulativamente aos seguintes requisitos:',
            'tipo': 'Sem alíquota'},
 '550002': {'artigo': 'Art. 84',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Regime de Trânsito, observado o art. 84 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Regime de Trânsito',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 84. Fica suspenso o pagamento do IBS e da CBS incidentes na importação enquanto os bens materiais estiverem '
                     'submetidos ao regime aduaneiro especial de trânsito aduaneiro, em qualquer de suas modalidades, observada a '
                     'disciplina estabelecida na legislação aduaneira.',
            'tipo': 'Sem alíquota'},
 '550003': {'artigo': 'Art. 85',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Regimes de Depósito, observado o art. 85 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Regimes de Depósito (art. 85)',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 85. Fica suspenso o pagamento do IBS e da CBS incidentes na importação enquanto os bens materiais estiverem '
                     'submetidos a regime aduaneiro especial de depósito, observada a disciplina estabelecida na legislação aduaneira.',
            'tipo': 'Sem alíquota'},
 '550004': {'artigo': 'Art. 87',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Regimes de Depósito, observado o art. 87 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Regimes de Depósito (art. 87)',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 87. Fica suspenso o pagamento do IBS e da CBS incidentes na importação e na aquisição no mercado interno de '
                     'bens materiais submetidos a regime aduaneiro especial de lojas franca, observada a disciplina estabelecida na '
                     'legislação aduaneira.',
            'tipo': 'Sem alíquota'},
 '550005': {'artigo': 'Art. 87, parágrafo único',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Regimes de Depósito, observado o art. 87 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Regimes de Depósito (art. 87, Parágrafo único)',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 87. Parágrafo único. Aplica-se o regime previsto no caput ao fornecimento de bens materiais destinados ao uso '
                     'ou consumo de bordo, em aeronaves exclusivamente em tráfego internacional com destino ao exterior e entregues em '
                     'zona primária alfandegada ou área de porto organizado alfandegado.',
            'tipo': 'Sem alíquota'},
 '550006': {'artigo': 'Art. 88',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Regimes de Permanência Temporária com suspensão total, observado o art. 88 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Regimes de Permanência Temporária com suspensão total',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 88. Fica suspenso o pagamento do IBS e da CBS incidentes na importação enquanto os bens materiais estiverem '
                     'submetidos a regime aduaneiro especial de permanência temporária no País ou de saída temporária do País, observada a '
                     'disciplina estabelecida na legislação aduaneira.',
            'tipo': 'Sem alíquota'},
 '550007': {'artigo': 'Art. 90',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Regimes de Aperfeiçoamento (Recof), observado o art. 90 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Regimes de Aperfeiçoamento (Recof)',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 90. Fica suspenso o pagamento do IBS e da CBS incidentes na importação enquanto os bens materiais estiverem '
                     'submetidos a regime aduaneiro especial de aperfeiçoamento, observada a disciplina estabelecida na legislação '
                     'aduaneira.',
            'tipo': 'Sem alíquota'},
 '550008': {'artigo': 'Art. 93, I',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Importação de bens para o Regime de Repetro-Temporário, de que tratam o inciso I do art. 93 da Lei Complementar nº '
                    '214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Importação de bens para o Regime de Repetro-Temporário',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 93. Observada a disciplina estabelecida na legislação aduaneira, fica suspenso o pagamento do IBS e da CBS nas '
                     'seguintes operações: I - importação de bens destinados às atividades de exploração, de desenvolvimento e de produção '
                     'de petróleo, de gás natural e de outros hidrocarbonetos fluidos previstas na legislação específica, cuja permanência '
                     'no País seja de natureza temporária, constantes de relação especificada no regulamento (Repetro- Temporário);',
            'tipo': 'Sem alíquota'},
 '550009': {'artigo': 'Art. 93, II',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'GNL-Temporário, de que trata o inciso II do art. 93 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'GNL-Temporário',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 93. Observada a disciplina estabelecida na legislação aduaneira, fica suspenso o pagamento do IBS e da CBS nas '
                     'seguintes operações: II - importação de bens destinados às atividades de transporte, movimentação, transferência, '
                     'armazenamento ou regaseificação de gás natural liquefeito constantes de relação especificada no regulamento '
                     '(GNL-Temporário);',
            'tipo': 'Sem alíquota'},
 '550010': {'artigo': 'Art. 93, III',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Repetro-Permanente, de que trata o inciso III do art. 93 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Repetro-Permanente',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 93. Observada a disciplina estabelecida na legislação aduaneira, fica suspenso o pagamento do IBS e da CBS nas '
                     'seguintes operações: III - importação de bens constantes de relação especificada no regulamento cuja permanência no '
                     'País seja definitiva e que sejam destinados às atividades a que se refere o inciso I deste caput '
                     '(Repetro-Permanente);',
            'tipo': 'Sem alíquota'},
 '550011': {'artigo': 'Art. 93, IV e Art. 93, § 4º',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Repetro-Industrialização, de que trata o inciso IV do art. 93 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Repetro-Industrialização',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 93. Observada a disciplina estabelecida na legislação aduaneira, fica suspenso o pagamento do IBS e da CBS nas '
                     'seguintes operações: IV - importação ou aquisição no mercado interno de matérias-primas, produtos intermediários e '
                     'materiais de embalagem para ser utilizados integralmente no processo produtivo de produto final a ser fornecido a '
                     'empresa que o destine às atividades a que se refere o inciso I deste caput (Repetro-Industrialização); § 4º Fica '
                     'também suspenso o pagamento do IBS e da CBS na importação ou na aquisição de bens no mercado interno por empresa '
                     'denominada fabricante intermediário para a industrialização de produto intermediário a ser fornecido a empresa que o '
                     'utilize no processo produtivo de que trata o inciso IV do caput deste artigo.',
            'tipo': 'Sem alíquota'},
 '550012': {'artigo': 'Art. 93, V',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Repetro-Nacional, de que trata o inciso V do art. 93 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Repetro-Nacional',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 93. Observada a disciplina estabelecida na legislação aduaneira, fica suspenso o pagamento do IBS e da CBS nas '
                     'seguintes operações: V - aquisição de produto final a que se refere o inciso IV deste caput (Repetro-Nacional);',
            'tipo': 'Sem alíquota'},
 '550013': {'artigo': 'Art. 93, VI',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Repetro-Entreposto, de que trata o inciso VI do art. 93 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Repetro-Entreposto',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 93. Observada a disciplina estabelecida na legislação aduaneira, fica suspenso o pagamento do IBS e da CBS nas '
                     'seguintes operações: VI - importação ou aquisição no mercado interno de bens constantes de relação especificada no '
                     'regulamento, para conversão ou construção de outros bens no País, contratada por empresa sediada no exterior, cujo '
                     'produto final deverá ser destinado às atividades a que se refere o inciso I deste caput (Repetro- Entreposto).',
            'tipo': 'Sem alíquota'},
 '550014': {'artigo': 'Arts. 99 e 100',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Zona de Processamento de Exportação, observado os arts. 99 e 100 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Zona de Processamento de Exportação',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 99. As importações ou as aquisições no mercado interno de máquinas, de aparelhos, de instrumentos e de '
                     'equipamentos realizadas por empresa autorizada a operar em zonas de processamento de exportação serão efetuadas com '
                     'suspensão do pagamento do IBS e da CBS. Art. 100. As importações ou as aquisições no mercado interno de '
                     'matérias-primas, de produtos intermediários e de materiais de embalagem realizadas por empresa autorizada a operar '
                     'em zonas de processamento de exportação serão efetuadas com suspensão do pagamento do IBS e da CBS.',
            'tipo': 'Sem alíquota'},
 '550015': {'artigo': 'Art. 105',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Regime Tributário para Incentivo à Modernização e à Ampliação da Estrutura Portuária - Reporto, observado o art. 105 '
                    'da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Regime Tributário para Incentivo à Modernização e à Ampliação da Estrutura Portuária',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 105. Observada a disciplina estabelecida na legislação específica, serão efetuadas com suspensão do pagamento '
                     'do IBS e da CBS as importações e as aquisições no mercado interno de máquinas, equipamentos, peças de reposição e '
                     'outros bens realizadas diretamente pelos beneficiários do Regime Tributário para Incentivo à Modernização e à '
                     'Ampliação da Estrutura Portuária (Reporto) e destinadas ao seu ativo imobilizado para utilização exclusiva na '
                     'execução de serviços de:',
            'tipo': 'Sem alíquota'},
 '550016': {'artigo': 'Art. 106',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Regime Especial de Incentivos para o Desenvolvimento da Infraestrutura - Reidi, observado o art. 106 da Lei '
                    'Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Regime Especial de Incentivos para o Desenvolvimento da Infraestrutura',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 106. Observada a disciplina estabelecida na legislação específica, serão efetuadas com suspensão do pagamento '
                     'do IBS e da CBS as importações e as aquisições no mercado interno de máquinas, aparelhos, instrumentos e '
                     'equipamentos, novos, e de materiais de construção, realizadas diretamente pelos beneficiários do Regime Especial de '
                     'Incentivos para o Desenvolvimento da Infraestrutura (Reidi) para utilização ou incorporação em obras de '
                     'infraestrutura destinadas ao ativo imobilizado.',
            'tipo': 'Sem alíquota'},
 '550017': {'artigo': 'Art. 107, I',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Fornecimentos de embarcações registradas ou pré-registradas no Registro Especial Brasileiro - REB para incorporação '
                    'ao ativo imobilizado de adquirente sujeito ao regime regular do IBS e da CBS, observado o art. 107 da Lei '
                    'Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Regime Tributário para Incentivo à Atividade Naval - Renaval (Art. 107, I)',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 107. O Regime Tributário para Incentivo à Atividade Econômica Naval – Renaval permite aos beneficiários '
                     'previamente habilitados suspensão do pagamento de IBS e CBS: I - nos fornecimentos de embarcações registradas ou '
                     'pré-registradas no Registro Especial Brasileiro - REB instituído pelo art. 11 da Lei nº 9.432, de 8 de janeiro de '
                     '1997, para incorporação ao ativo imobilizado de adquirente sujeito ao regime regular do IBS e da CBS;',
            'tipo': 'Sem alíquota'},
 '550018': {'artigo': 'Art. 109',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Desoneração da aquisição de bens de capital, observado o art. 109 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Desoneração da aquisição de bens de capital',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 109. Ato conjunto do Poder Executivo da União e do Comitê Gestor do IBS poderá definir hipóteses em que '
                     'importações e aquisições no mercado interno de bens de capital por contribuinte no regime regular serão realizadas '
                     'com suspensão do pagamento do IBS e da CBS, não se aplicando o disposto no art. 108 desta Lei Complementar.',
            'tipo': 'Sem alíquota'},
 '550019': {'artigo': 'Art. 443',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Importação de bem material por indústria incentivada para utilização na Zona Franca de Manaus, observado o art. 443 '
                    'da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Importação de bem material por indústria incentivada para utilização na ZFM',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 443. Fica suspensa a incidência do IBS e da CBS na importação de bem material realizada por indústria '
                     'incentivada para utilização na Zona Franca de Manaus.',
            'tipo': 'Sem alíquota'},
 '550020': {'artigo': 'Art. 461',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Áreas de livre comércio, observado o art. 461 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Áreas de livre comércio',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 461. Fica suspensa a incidência do IBS e da CBS na importação de bem material realizada por indústria '
                     'habilitada na forma do inciso II do caput do art. 460 desta Lei Complementar e sujeita ao regime regular do IBS e da '
                     'CBS para incorporação em seu processo produtivo.',
            'tipo': 'Sem alíquota'},
 '550021': {'artigo': 'Art. 82, § 11',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Fornecimento de produtos agropecuários in natura para contribuinte do regime regular que promova industrialização '
                    'destinada a exportação, observado o art. 82 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Industrialização destinada a exportações',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 82. § 11. Também fica suspenso o pagamento do IBS e da CBS no fornecimento de produtos agropecuários in natura '
                     'para contribuinte do regime regular que promova industrialização destinada a exportação para o exterior:',
            'tipo': 'Sem alíquota'},
 '550022': {'artigo': 'Art. 106, § 7º',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Regime Especial de Incentivos para a Produção de Hidrogênio de Baixa Emissão de Carbono (Rehidro), observado o art. '
                    '106 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Regime Especial de Incentivos para a Produção de Hidrogênio de Baixa Emissão de Carbono (Rehidro)',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 106. § 7º Os benefícios fiscais do regime especial de que trata este artigo aplicam-se também aos beneficiários '
                     'do Regime Especial de Incentivos para a Produção de Hidrogênio de Baixa Emissão de Carbono (Rehidro), instituído '
                     'pela Lei nº 14.948, de 2 de agosto de 2024, observada a disciplina estabelecida na legislação específica',
            'tipo': 'Sem alíquota'},
 '550023': {'artigo': 'Art. 172, § 2º',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Operações com hidrocarbonetos líquidos derivados de petróleo não combustíveis ou de gás natural, inclusive nafta, '
                    'observado o art. 172 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Operações com hidrocarbonetos líquidos derivados de petróleo não combustíveis ou de gás natural, inclusive nafta',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 172. § 2º Ato conjunto da RFB e do CGIBS preverá hipóteses de suspensão do IBS e da CBS incidentes nas '
                     'operações com hidrocarbonetos líquidos derivados de petróleo não combustíveis ou de gás natural, inclusive nafta, '
                     'desde que: I – os adquirentes sejam centrais petroquímicas devidamente autorizadas pela ANP; II – sejam utilizados '
                     'como insumo pela indústria petroquímica; e III – obedeçam a critérios e condições estabelecidos no referido ato '
                     'conjunto.',
            'tipo': 'Sem alíquota'},
 '550024': {'artigo': 'Art. 107, II',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Importações e nas aquisições no mercado interno de máquinas, equipamentos e veículos destinados a utilização nas '
                    'atividades de que trata o inciso IIIdo art. 107 efetuadas para incorporação a seu ativo imobilizado, observado o art. '
                    '107 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Regime Tributário para Incentivo à Atividade Naval - Renaval (Art. 107, II)',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 107. O Regime Tributário para Incentivo à Atividade Econômica Naval – Renaval permite aos beneficiários '
                     'previamente habilitados suspensão do pagamento de IBS e CBS: II - nas importações e nas aquisições no mercado '
                     'interno de máquinas, equipamentos e veículos destinados a utilização nas atividades de que trata o inciso III '
                     'efetuadas para incorporação a seu ativo imobilizado;',
            'tipo': 'Sem alíquota'},
 '550025': {'artigo': 'Art. 107, III',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Importações e nas aquisições no mercado interno de matérias-primas, produtos intermediários, partes, peças e '
                    'componentes para utilização na construção, conservação, modernização e reparo de embarcações pré-registradas ou '
                    'registradas no REB, observado o art. 107 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Regime Tributário para Incentivo à Atividade Naval - Renaval (Art. 107, III)',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 107. O Regime Tributário para Incentivo à Atividade Econômica Naval – Renaval permite aos beneficiários '
                     'previamente habilitados suspensão do pagamento de IBS e CBS: III - nas importações e nas aquisições no mercado '
                     'interno de matérias-primas, produtos intermediários, partes, peças e componentes para utilização na construção, '
                     'conservação, modernização e reparo de embarcações pré-registradas ou registradas no REB.',
            'tipo': 'Sem alíquota'},
 '550026': {'artigo': 'Art. 89, § 3º, II',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Regimes de admissão temporária com suspensão total do pagamento dos tributos durante o período de sua permanência na '
                    'Zona Franca de Manaus, observado o art. 89 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Regimes de admissão temporária com suspensão total do pagamento dos tributos (ZFM)',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 89. § 3º O disposto no caput deste artigo não se aplica: II - até a data estabelecida pelo art. 92-A do Ato das '
                     'Disposições Constitucionais Transitórias, aos bens importados temporariamente e para utilização econômica por '
                     'empresas que se enquadrem nas disposições do Decreto-Lei nº 288, de 28 de fevereiro de 1967, durante o período de '
                     'sua permanência na Zona Franca de Manaus, os quais serão submetidos ao regime de admissão temporária com suspensão '
                     'total do pagamento dos tributos.',
            'tipo': 'Sem alíquota'},
 '550027': {'artigo': 'Art. 90',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Regimes de Aperfeiçoamento (Drawback), observado o art. 90 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Regimes de Aperfeiçoamento (Drawback)',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 90. Fica suspenso o pagamento do IBS e da CBS incidentes na importação enquanto os bens materiais estiverem '
                     'submetidos a regime aduaneiro especial de aperfeiçoamento, observada a disciplina estabelecida na legislação '
                     'aduaneira.',
            'tipo': 'Sem alíquota'},
 '550028': {'artigo': 'Art. 90',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Regimes de Aperfeiçoamento (Admissão temporária), observado o art. 90 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Regimes de Aperfeiçoamento (Admissão temporária)',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 90. Fica suspenso o pagamento do IBS e da CBS incidentes na importação enquanto os bens materiais estiverem '
                     'submetidos a regime aduaneiro especial de aperfeiçoamento, observada a disciplina estabelecida na legislação '
                     'aduaneira.',
            'tipo': 'Sem alíquota'},
 '550029': {'artigo': 'Art. 102',
            'cst': '550',
            'cst_desc': 'Suspensão',
            'cte': 0,
            'desc': 'Zona de Processamento de Exportação, observado os art. 102 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Zona de Processamento de Exportação',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 102. Aplica-se o tratamento estabelecido nos arts. 99 e 100 desta Lei Complementar às aquisições de máquinas, '
                     'de aparelhos, de instrumentos, de equipamentos, de matérias-primas, de produtos intermediários e de materiais de '
                     'embalagem realizadas entre empresas autorizadas a operar em zonas de processamento de exportação.',
            'tipo': 'Sem alíquota'},
 '620001': {'artigo': 'Art. 172',
            'cst': '620',
            'cst_desc': 'Tributação monofásica',
            'cte': 0,
            'desc': 'Tributação monofásica sobre combustíveis, observados os art. 172 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Tributação monofásica sobre combustíveis',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 172. O IBS e a CBS incidirão uma única vez sobre as operações, ainda que iniciadas no exterior, com os '
                     'seguintes combustíveis, qualquer que seja a sua finalidade.',
            'tipo': 'Uniforme setorial'},
 '620002': {'artigo': 'Art. 178',
            'cst': '620',
            'cst_desc': 'Tributação monofásica',
            'cte': 0,
            'desc': 'Tributação monofásica com responsabilidade pela retenção sobre combustíveis, observado o art. 178 da Lei Complementar '
                    'nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Tributação monofásica com responsabilidade pela retenção sobre combustíveis',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 178. Fica atribuída à refinaria de petróleo ou suas bases, à CPQ, ao formulador de combustíveis e ao '
                     'importador, relativamente ao percentual de biocombustível utilizado na mistura, nas operações com gasolina A, a '
                     'responsabilidade pela retenção e pelo recolhimento do IBS e da CBS incidentes nas importações de EAC ou sobre as '
                     'saídas do estabelecimento produtor de EAC.',
            'tipo': 'Uniforme setorial'},
 '620003': {'artigo': 'Art. 178',
            'cst': '620',
            'cst_desc': 'Tributação monofásica',
            'cte': 0,
            'desc': 'Tributação monofásica com responsabilidade de retenção de tributos por terceiros, observado o art. 178 da Lei '
                    'Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Tributação monofásica com responsabilidade de retenção de tributos por terceiros',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 178. Fica atribuída à refinaria de petróleo ou suas bases, à CPQ, ao formulador de combustíveis e ao '
                     'importador, relativamente ao percentual de biocombustível utilizado na mistura, nas operações com gasolina A, a '
                     'responsabilidade pela retenção e pelo recolhimento do IBS e da CBS incidentes nas importações de EAC ou sobre as '
                     'saídas do estabelecimento produtor de EAC.',
            'tipo': 'Uniforme setorial'},
 '620004': {'artigo': 'Art. 179, II, a',
            'cst': '620',
            'cst_desc': 'Tributação monofásica',
            'cte': 0,
            'desc': 'Tributação monofásica sobre mistura de EAC com gasolina A em percentual superior ou inferior ao obrigatório, '
                    'observado o art. 179 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Tributação monofásica sobre mistura de EAC com gasolina A em percentual superior ao obrigatório',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 179. Nas operações com EAC: II - a distribuidora de combustíveis que realizar mistura de EAC com gasolina A em '
                     'percentual: a) superior ao obrigatório, fica obrigada a recolher o IBS e a CBS de que trata o art. 172 desta Lei '
                     'Complementar em relação ao volume de biocombustível correspondente ao que exceder ao percentual obrigatório de '
                     'mistura; e',
            'tipo': 'Uniforme setorial'},
 '620005': {'artigo': 'Art. 179, II, b',
            'cst': '620',
            'cst_desc': 'Tributação monofásica',
            'cte': 0,
            'desc': 'Tributação monofásica sobre mistura de EAC com gasolina A em percentual superior ou inferior ao obrigatório, '
                    'observado o art. 179 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Tributação monofásica sobre mistura de EAC com gasolina A em percentual inferior ao obrigatório',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 179. Nas operações com EAC: II - a distribuidora de combustíveis que realizar mistura de EAC com gasolina A em '
                     'percentual: b) inferior ao obrigatório, terá direito ao ressarcimento do IBS e da CBS de que trata o art. 172 desta '
                     'Lei Complementar em relação ao volume de biocombustível correspondente ao misturado a menor do que o percentual '
                     'obrigatório de mistura.',
            'tipo': 'Uniforme setorial'},
 '620006': {'artigo': 'Art. 180',
            'cst': '620',
            'cst_desc': 'Tributação monofásica',
            'cte': 0,
            'desc': 'Tributação monofásica sobre combustíveis cobrada anteriormente, observador o art. 180 da Lei Complementar nº 214, de '
                    '2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 1,
            'nfe': 1,
            'nome': 'Tributação monofásica sobre combustíveis cobrada anteriormente',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 180. É vedada a apropriação de créditos em relação às aquisições de combustíveis sujeitos à incidência única do '
                     'IBS e da CBS, quando destinadas à distribuição, à comercialização ou à revenda.',
            'tipo': 'Uniforme setorial'},
 '620007': {'artigo': 'Art. 47, § 6º',
            'cst': '620',
            'cst_desc': 'Tributação monofásica',
            'cte': 0,
            'desc': 'Perecimento, deteriorização, roubo, furto ou extravio no regime monofásico sem estorno de crédito, observado o art. '
                    '47 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Perecimento, deteriorização, roubo, furto ou extravio no regime monofásico',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 47. O contribuinte sujeito ao regime regular poderá apropriar créditos do IBS e da CBS quando ocorrer a '
                     'extinção por qualquer das modalidades previstas no art. 27 dos débitos relativos às operações em que seja '
                     'adquirente, excetuadas exclusivamente aquelas consideradas de uso ou consumo pessoal, nos termos do art. 57 desta '
                     'Lei Complementar, e as demais hipóteses previstas nesta Lei Complementar. § 6º O adquirente deverá estornar o '
                     'crédito apropriado caso o bem adquirido venha a perecer, deteriorar-se ou ser objeto de roubo, furto ou extravio.',
            'tipo': 'Sem alíquota'},
 '800001': {'artigo': 'Art. 55',
            'cst': '800',
            'cst_desc': 'Transferência de crédito',
            'cte': 0,
            'desc': 'Fusão, cisão ou incorporação, observado o art. 55 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Fusão, cisão ou incorporação',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 55. É vedada a transferência, a qualquer título, para outra pessoa ou entidade sem personalidade jurídica, de '
                     'créditos do IBS e da CBS. Parágrafo único. Na hipótese de fusão, cisão ou incorporação, os créditos apropriados e '
                     'ainda não utilizados poderão ser transferidos para a pessoa jurídica sucessora, ficando preservada a data original '
                     'da apropriação dos créditos para efeitos da contagem do prazo de que trata o art. 54 desta Lei Complementar.',
            'tipo': 'Sem alíquota'},
 '800002': {'artigo': 'Art. 272',
            'cst': '800',
            'cst_desc': 'Transferência de crédito',
            'cte': 0,
            'desc': 'Transferência de crédito do associado, inclusive as cooperativas singulares, para cooperativa de que participa das '
                    'operações antecedentes às operações em que fornece bens e serviços e os créditos presumidos, observado o art. 272 da '
                    'Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Transferência de crédito do associado, inclusive as cooperativas singulares',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 272. O associado sujeito ao regime regular do IBS e da CBS, inclusive as cooperativas singulares, que realizar '
                     'operações com a redução de alíquota de que trata o inciso I do caput do art. 271 poderá transferir os créditos das '
                     'operações antecedentes às operações em que fornece bens e serviços e os créditos presumidos à cooperativa de que '
                     'participa, não se aplicando o disposto no art. 55 desta Lei Complementar.',
            'tipo': 'Sem alíquota'},
 '810001': {'artigo': 'Art. 450, § 1º',
            'cst': '810',
            'cst_desc': 'Ajuste de IBS na ZFM',
            'cte': 0,
            'desc': 'Crédito presumido de IBS sobre o valor apurado nos fornecimentos a partir da Zona Franca de Manaus, observado o art. '
                    '450 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Crédito presumido de IBS sobre o valor apurado nos fornecimentos a partir da ZFM',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 450. São concedidos à indústria incentivada na Zona Franca de Manaus créditos presumidos de IBS e de CBS '
                     'relativos à operação que destine ao território nacional, inclusive para a própria Zona Franca de Manaus, bem '
                     'material produzido pela própria indústria incentivada na referida área nos termos do projeto econômico aprovado, '
                     'exceto em relação às operações previstas no art. 448 desta Lei Complementar. § 1º O crédito presumido de IBS de que '
                     'trata o caput será calculado mediante a aplicação dos seguintes percentuais sobre o saldo devedor do IBS no período '
                     'de apuração:',
            'tipo': 'Sem alíquota'},
 '811001': {'artigo': 'Art. 51',
            'cst': '811',
            'cst_desc': 'Ajustes',
            'cte': 0,
            'desc': 'Anulação de crédito proporcional ao valor das operações imunes e isentas, observado o art. 51 da Lei Complementar nº '
                    '214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Anulação de Crédito por Saídas Imunes/Isentas',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 51. A imunidade e a isenção acarretarão a anulação dos créditos relativos às operações anteriores. § 1º A '
                     'anulação dos créditos de que trata o caput deste artigo será proporcional ao valor das operações imunes e isentas '
                     'sobre o valor de todas as operações do fornecedor.',
            'tipo': 'Sem alíquota'},
 '811002': {'artigo': 'Art. 45',
            'cst': '811',
            'cst_desc': 'Ajustes',
            'cte': 0,
            'desc': 'Débitos de notas fiscais não processadas na apuração, observado o art. 45 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Débitos de notas fiscais não processadas na apuração',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 45. Para cada período de apuração, o contribuinte deverá apurar, separadamente, o saldo do IBS e da CBS, que '
                     'corresponderá à diferença entre os valores: § 1º O contribuinte poderá realizar ajustes positivos ou negativos no '
                     'saldo apurado na forma do caput deste artigo, nos termos previstos no regulamento.',
            'tipo': 'Sem alíquota'},
 '811003': {'artigo': 'Art. 41',
            'cst': '811',
            'cst_desc': 'Ajustes',
            'cte': 0,
            'desc': 'Débitos apurados após o desenquadramento do regime Simples Nacional, observado o art. 41 da Lei Complementar nº 214, '
                    'de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Desenquadramento do Simples Nacional',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 41. O regime regular do IBS e da CBS compreende todas as regras de incidência e de apuração previstas nesta Lei '
                     'Complementar, incluindo aquelas aplicáveis aos regimes diferenciados e aos regimes específicos. § 2º Os '
                     'contribuintes optantes pelo Simples Nacional ou pelo MEI ficam sujeitos às regras desses regimes.',
            'tipo': 'Sem alíquota'},
 '820001': {'artigo': 'Art. 234',
            'cst': '820',
            'cst_desc': 'Tributação em documento específico',
            'cte': 0,
            'desc': 'Documento com informações de fornecimento de serviços de planos de assistência à saúde elencados no art. 234 da Lei '
                    'Complementar nº 214, de 2025, mas com tributação realizada por outro meio',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Documento com informações de fornecimento de serviços de planos de assistência à saúde elencados no art. 234 da Lei '
                    'Complementar nº214, de 2025',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 234. Os planos de assistência à saúde ficam sujeitos a regime específico de incidência do IBS e da CBS, de '
                     'acordo com o disposto neste Capítulo, nos casos em que esses serviços sejam prestados por:',
            'tipo': 'Sem alíquota'},
 '820002': {'artigo': 'Art. 236',
            'cst': '820',
            'cst_desc': 'Tributação em documento específico',
            'cte': 0,
            'desc': 'Documento com informações de fornecimento de serviços de planos de assinstência funerária, mas com tributação '
                    'realizada por outro meio, observado o art. 236 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Documento com informações de fornecimento de serviços de planos de assistência funerária',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 236. Os planos de assistência funerária ficam sujeitos ao disposto nos arts. 234 a 242 desta Lei Complementar.',
            'tipo': 'Sem alíquota'},
 '820003': {'artigo': 'Art. 243',
            'cst': '820',
            'cst_desc': 'Tributação em documento específico',
            'cte': 0,
            'desc': 'Documento com informações de fornecimento de serviços de planos de assinstência à saúde de animais domésticos, mas '
                    'com tributação realizada por outro meio, observado o art. 243 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Documento com informações de fornecimento de serviços de planos de assistência à saúde de animais domésticos',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 243. Os planos de assistência à saúde de animais domésticos ficam sujeitos ao disposto nos arts. 234 a 242 '
                     'desta Lei Complementar, com exceção das alíquotas aplicáveis, que serão nacionalmente uniformes e corresponderão à '
                     'soma das alíquotas de referência de cada esfera federativa, reduzidas em 30% (trinta por cento), vedado o crédito ao '
                     'adquirente.',
            'tipo': 'Sem alíquota'},
 '820004': {'artigo': 'Art. 248',
            'cst': '820',
            'cst_desc': 'Tributação em documento específico',
            'cte': 0,
            'desc': 'Documento com informações de prestação de serviços de consursos de prognósticos, mas com tributação realizada por '
                    'outro meio, observado o art. 248 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Documento com informações de prestação de serviços de consursos de prognósticos',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 248. A empresa que opera concursos de prognósticos deverá apresentar obrigação acessória, na forma do '
                     'regulamento, contendo, no mínimo, informações sobre o local onde a aposta é efetuada e os valores das apostas e das '
                     'premiações pagas.',
            'tipo': 'Sem alíquota'},
 '820005': {'artigo': 'Art. 254, § 1º',
            'cst': '820',
            'cst_desc': 'Tributação em documento específico',
            'cte': 0,
            'desc': 'Documento com informações de alienação de bens imóveis, mas com tributação realizada por outro meio, observado o art. '
                    '254 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Documento com informações de alienação de bens imóveis',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 254. Considera-se ocorrido o fato gerador do IBS e da CBS: I - na alienação de bem imóvel, no momento do ato de '
                     'alienação; § 1º Para fins do disposto no inciso I do caput deste artigo, considera-se alienação a adjudicação, a '
                     'celebração, inclusive de quaisquer ajustes posteriores, do contrato de alienação, ainda que mediante instrumento de '
                     'promessa, carta de reserva com princípio de pagamento ou qualquer outro documento representativo de compromisso, ou '
                     'quando implementada a condição suspensiva a que estiver sujeita a alienação.',
            'tipo': 'Sem alíquota'},
 '820006': {'artigo': 'Art. 11, VIII',
            'cst': '820',
            'cst_desc': 'Tributação em documento específico',
            'cte': 0,
            'desc': 'Documento com informações de fornecimento de serviços de exploração de via, mas com tributação realizada por outro '
                    'meio, observado o art. 11 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Documento com informações de fornecimento de serviços de exploração de via',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 11. Considera-se local da operação com: VIII - serviço de exploração de via, mediante cobrança de valor a '
                     'qualquer título, incluindo tarifas, pedágios e quaisquer outras formas de cobrança, o território de cada Município e '
                     'Estado, ou do Distrito Federal, proporcionalmente à correspondente extensão da via explorada;',
            'tipo': 'Sem alíquota'},
 '820007': {'artigo': 'Art. 181',
            'cst': '820',
            'cst_desc': 'Tributação em documento específico',
            'cte': 0,
            'desc': 'Documento com informações de fornecimento de serviços financeiros, mas com tributação realizada por outro meio, '
                    'observado o art. 181 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Documento com informações de fornecimento de serviços financeiros',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 181. Os serviços financeiros ficam sujeitos a regime específico de incidência do IBS e da CBS, de acordo com o '
                     'disposto neste Capítulo.',
            'tipo': 'Sem alíquota'},
 '820008': {'artigo': 'Art. 10, § 3º',
            'cst': '820',
            'cst_desc': 'Tributação em documento específico',
            'cte': 0,
            'desc': 'Documento com informações de fornecimento de serviço continuado, mas com tributação realizada em fatura anterior, '
                    'observado o art. 10 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Documento com informações de fornecimento de serviço continuado, mas com tributação realizada em fatura anterior',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 10. Considera-se ocorrido o fato gerador do IBS e da CBS no momento do fornecimento nas operações com bens ou '
                     'com serviços, ainda que de execução continuada ou fracionada. § 3º Nas operações de execução continuada ou '
                     'fracionada, considera-se ocorrido o fato gerador na primeira entre as seguintes ocorrências: I - quando se torna '
                     'exigível a parte da contraprestação correspondente a cada pagamento; ou II - pagamento da obrigação decorrente do '
                     'fornecimento.',
            'tipo': 'Sem alíquota'},
 '820009': {'artigo': 'Art. 60',
            'cst': '820',
            'cst_desc': 'Tributação em documento específico',
            'cte': 0,
            'desc': 'Fornecimentos declarados e tributados em outro documento, observado o art. 60 da Lei Complementar nº 214, de 2025.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 0,
            'nome': 'Fornecimentos declarados e tributados em outro documento',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 60. O sujeito passivo do IBS e da CBS, ao realizar operações com bens ou com serviços, inclusive exportações, e '
                     'importações, deverá emitir documento fiscal eletrônico. § 1º As informações prestadas pelo sujeito passivo nos '
                     'termos deste artigo possuem caráter declaratório e constituem confissão do valor devido de IBS e de CBS consignados '
                     'no documento fiscal. § 2º A obrigação de emissão de documentos fiscais eletrônicos aplica-se inclusive: III - a '
                     'outras hipóteses previstas no regulamento.',
            'tipo': 'Sem alíquota'},
 '830001': {'artigo': 'Art. 28, parágrafos 3° e 4°',
            'cst': '830',
            'cst_desc': 'Exclusão de base de cálculo',
            'cte': 0,
            'desc': 'Documento com exclusão da base de cálculo da CBS e do IBS refrente à energia elétrica fornecida pela distribuidora à '
                    'unidade consumidora, conforme Art 28, parágrafos 3° e 4°.',
            'fim': '',
            'ini': '2026-01-01',
            'nfce': 0,
            'nfe': 1,
            'nome': 'Documento com exclusão da BC da CBS e do IBS de energia elétrica fornecida pela distribuidora à UC',
            'pred_cbs': 0.0,
            'pred_ibs': 0.0,
            'texto': 'Art. 28. § 3º Exclui-se da base de cálculo da CBS e do IBS a energia elétrica fornecida pela distribuidora à unidade '
                     'consumidora, na quantidade correspondente à energia injetada na rede de distribuição pela mesma unidade consumidora, '
                     'acrescidos dos créditos de energia elétrica originados na própria unidade consumidora no mesmo mês, em meses '
                     'anteriores ou em outra unidade consumidora do mesmo titular. § 4º A exclusão de que trata o § 3º deste artigo: I - '
                     'aplica-se somente a consumidores participantes do Sistema de Compensação de Energia Elétrica, de que trata a Lei nº '
                     '14.300, de 6 de janeiro de 2022; II - aplica-se somente à compensação de energia elétrica produzida por microgeração '
                     'e minigeração, cuja potência instalada seja, respectivamente, menor ou igual a 75 kW e superior a 75 kW e menor ou '
                     'igual a 1 MW; e III - não se aplica ao custo de disponibilidade, à energia reativa, à demanda …',
            'tipo': 'Sem alíquota'}}

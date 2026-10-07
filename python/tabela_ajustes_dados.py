# -*- coding: utf-8 -*-
"""Tabelas oficiais do SPED Fiscal usadas pela Evolução Tributária.

Fonte: serviço oficial de Tabelas Externas do Sped (sped.fazenda.gov.br/spedtabelas), baixadas em 07/10/2026.
  - 5.1.1 Tabela de Códigos de Ajustes da Apuração do ICMS — Amazonas (id 220, versão 51)
  - 5.1.1 Tabela de Códigos de Ajustes da Apuração do ICMS — Rondônia (id 53, versão 69)
  - 5.4   Tabela de Códigos das Obrigações do ICMS a Recolher (id 5, versão 1)

Ficaram só códigos de ICMS próprio, ST, DIFAL e FCP (3º caractere 0 a 3) ainda vigentes em 2021 ou depois.
Para as demais UFs o FiscoCont+ baixa a tabela oficial da UF no próprio computador (ver main.js) e,
sem internet, usa a descrição complementar do E111 e a natureza do código (4º caractere).
Formato de cada linha: CODIGO|DESCRICAO|DT_FIM (vazio = vigente).
"""

TABELA_5_4 = {
    '000': 'ICMS a recolher',
    '001': 'ICMS da substituição tributária pelas entradas',
    '002': 'ICMS da substituição tributária pelas saídas para o Estado',
    '003': 'Antecipação do diferencial de alíquotas do ICMS',
    '004': 'Antecipação do ICMS da importação',
    '005': 'Antecipação tributária',
    '006': 'ICMS resultante da alíquota adicional dos itens incluídos no Fundo de Combate à Pobreza',
    '090': 'Outras obrigações do ICMS',
    '999': 'ICMS da substituição tributária pelas saídas para outro Estado',
}

VERSOES = {'AM': 'id 220, versão 51', 'RO': 'id 53, versão 69'}

_AM = r"""AM000002|Recebimento de saldo devedor transferido por outro estabelecimento do sujeito passivo localizado no Estado – Decreto Estadual nº 20.686/1999, art. 102|
AM009999|Outros débitos para ajuste de apuração do ICMS - operações próprias - descrever no registro E111 ou 1921|
AM010001|Estorno de crédito – Decreto Estadual nº 20.686/1999, arts. 31 e 32|
AM010002|Estorno de crédito – Diferimento – Lei Estadual nº 2.826/2003, art. 14, §§ 5º e 6º|
AM010003|Estorno de crédito – saída de bem de consumo final incentivado com carga tributária reduzida de 7% - Decreto Estadual nº 23.994/2003, art. 22, § 20|
AM019999|Outros estornos de crédito – operações próprias - descrever no registro E111 ou 1921|
AM020002|Recebimento de saldo credor transferido por outro estabelecimento do sujeito passivo localizado no Estado – Decreto Estadual nº 20.686/1999, art. 102|
AM020003|Antecipação tributária – aquisição de mercadoria em outra unidade da federação – Decreto Estadual nº 20.686/1999, art. 20, X, e art. 118|
AM020004|CIAP – Ativo Permanente – Decreto Estadual nº 20.686/1999, art. 20, IX|
AM020005|Parcela mensal da Estimativa Fixa – Decreto Estadual nº 20.686/1999, art. 46|
AM020006|Repetição de Indébito – Decreto Estadual nº 20.686/1999, art. 20, VI|
AM020007|Importação de mercadoria estrangeira – Decreto Estadual nº 20.686/1999, art. 20, XI|
AM020011|Parcelamento – direito a crédito do imposto recolhido|
AM020012|AINF – direito a crédito do imposto lançado e recolhido|
AM020013|Energia Elétrica – Decreto Estadual nº 20.686/1999, art. 20, VIII|
AM029999|Outros créditos para ajuste de apuração do ICMS - operações próprias - descrever no registro E111 ou 1921|
AM039999|Outros estornos de débito – operações próprias - descrever no registro E111 ou 1921|
AM040001|Crédito Estímulo do ICMS – 90,25% – Lei Estadual nº 2.826/2003, art. 13, I|
AM040002|Crédito Estímulo do ICMS – 75% – Lei Estadual nº 2.826/2003, art. 13, II|
AM040003|Crédito Estímulo do ICMS – 55% – Lei Estadual nº 2.826/2003, art. 13, III|
AM040004|Crédito Estímulo do ICMS – 100% – Lei Estadual nº 2.826/2003, art. 13, § 3º|
AM040005|Crédito Estímulo do ICMS – 55% – Adicional de 20% – Lei Estadual nº 2.826/2003, art. 13, § 4º|
AM040006|Crédito Estímulo do ICMS – 75% – Adicional de regionalização – Lei Estadual nº 2.826/2003, art. 13, §§ 5º, 6º, 7º e 8º|
AM040007|Crédito Estímulo do ICMS – 55% – Adicional de regionalização – Lei Estadual nº 2.826/2003, art. 13, §§ 9º, 10, 11 e 12|
AM040008|Crédito Estímulo do ICMS – 100% – Lei Estadual nº 2.826/2003, art. 13, § 13|
AM040009|Crédito Estímulo do ICMS – 55% – Adicional de 5% – Lei Estadual nº 2.826/2003, art. 13, § 14|
AM040010|Crédito Estímulo do ICMS – 75% – Lei Estadual nº 2.826/2003, art. 13, § 15|
AM040011|Crédito Estímulo do ICMS – 100% – Lei Estadual nº 2.826/2003, art. 13, § 18|
AM040012|Crédito Estímulo do ICMS – nível concedido na forma da Lei Estadual nº 2.826/2003, art. 16|
AM040013|Regime de Estimativa – saldo devedor apurado a transportar para o mês seguinte do trimestre de apuração – Decreto Estadual nº 20.686/1999, art. 46, caput e § 1º|
AM049999|Outras deduções do ICMS apurado – operações próprias - descrever no registro E111 ou 1921|
AM050001|Cesta Básica – mercadorias procedentes de outra Unidade da Federação – Decreto Estadual nº 23.994/2003, art. 38, caput e § 1º, I|
AM050002|ICMS Antecipação Tributária – Mercadoria Nacional – Decreto Estadual nº 20.686/1999, art. 118|
AM050003|ICMS Antecipação Tributária com encerramento da tributação – gado em pé destinado ao abate, as carnes, vísceras, frango e produtos de sua matança, in natura – Decreto Estadual nº 20.686/1999, art. 118, § 4º|
AM050004|ICMS Antecipação Tributária com encerramento da tributação – bebidas alcóolicas de posições NCM 2204 e 2208, farinha de trigo ou semolina – Decreto Estadual nº 20.686/1999, art. 118, § 5º|
AM050005|ICMS Antecipação Tributária com encerramento da tributação – café – Decreto Estadual nº 20.686/1999, art. 118, § 5º|
AM050006|ICMS Antecipação Tributária com encerramento da tributação – mercadorias sujeitas ao regime de substituição tributária provenientes de Estado não signatário de Convênio – Decreto Estadual nº 20.686/1999, art. 120|
AM050007|ICMS Mercadoria Importada do Exterior – Insumo Industrial – Decreto Estadual nº 20.686/1999, art. 2º, § 1º, I, e art. 107, I, “a”|
AM050008|ICMS Mercadorias Importada do Exterior – Comercialização – Decreto Estadual nº 20.686/1999, art. 2º, § 1º, I, e art. 107, I, “a”|
AM050009|ICMS Mercadorias ou Bens importados do exterior – uso e consumo – Decreto Estadual nº 20.686/1999, art. 2º, § 1º, I, e art. 107, I, “a”|
AM050010|ICMS Mercadorias ou bens importados do exterior – Ativo Permanente – Decreto Estadual nº 20.686/1999, art. 2º, § 1º, I, e art. 107, I, “a”|
AM050011|ICMS sobre Despesas Aduaneiras – insumos industriais – Decreto Estadual nº 20.686/1999, art. 13, V, “e”, e art. 107, § 1º, I|
AM050012|ICMS sobre Despesas Aduaneiras – outras importações – Decreto Estadual nº 20.686/1999, art. 13, V, “e”, e art. 107, § 1º, II, “b”|
AM050013|ICMS Diferencial de alíquotas – mercadorias ou bens para uso e consumo – Decreto Estadual nº 20.686/1999, art. 3º, XIV|
AM050014|ICMS Diferencial de alíquotas – bens para o ativo permanente do contribuinte – Decreto Estadual nº 20.686/1999, art. 3º, XIV|
AM050015|ICMS Diferido a Recolher – Produtos Agrícolas – Decreto Estadual nº 20.686/1999, art. 109, § 4º, II, “b”|
AM050016|ICMS Estorno de Crédito – Entrada Incentivada – Decreto Estadual nº 20.686/1999, art. 31, art. 35 e art. 107, V|
AM050017|ICMS Estorno de Crédito – Saída Incentivada – Decreto Estadual nº 20.686/1999, art. 13, V, “e”, e art. 107, § 1º, I|
AM050018|ICMS Estorno de Crédito – Álcool Anidro e Biodiesel – Conv. ICMS nº 110/2007, cláusula vigésima primeira, § 10, e Decreto Estadual nº 20.686/1999, art. 13, V, “e”, e art. 107, § 1º, I|
AM050019|ICMS Estorno de Crédito – Outros – Decreto Estadual nº 20.686/1999, art. 13, V, “e”, e art. 107, § 1º, I|
AM050020|ICMS Excesso Cota LCD – Decreto Estadual nº 32.297/2012, art. 3º, § 4º|
AM050021|ICMS Energia Elétrica – Produção Própria – Decreto Estadual nº 20.686/1999, art. 2º, § 3º, II, “f”|
AM050022|Simples Nacional – valor do ICMS a recolher apurado no Programa Gerador do Documento de Arrecadação do Simples Nacional – Declaratório – PGDAS-D|
AM050023|Regime de estimativa - parcela mensal fixa – Decreto Estadual nº 20.686/1999, art. 107, II, “b”, 1|
AM050024|ICMS Diferido a Recolher – refeições prontas adquiridas por estabelecimento industrial – Decreto Estadual nº 20.686/1999, art. 109, § 4º, II, “c”|
AM051001|Contribuição à UEA|
AM051002|Contribuição ao FTI|
AM051003|Contribuição ao FMPES|
AM059999|Outros débitos especiais – operações próprias - descrever no registro E111 ou 1921|
AM099999|Controle do ICMS extra-apuração|
AM109999|Outros débitos - operações com ICMS-ST - descrever no registro E220|
AM119999|Outros estornos de crédito - operações com ICMS-ST - descrever no registro E220|
AM129999|Outros créditos - operações com ICMS-ST - descrever no registro E220|
AM139999|Outros estornos de débito - operações com ICMS-ST - descrever no registro E220|
AM149999|Outras deduções do ICMS-ST apurado - descrever no registro E220|
AM159999|Outros débitos especiais - operações com ICMS-ST - descrever no registro E220|
AM000001|Transferência de saldo credor para o estabelecimento centralizador pelo estabelecimento não centralizador do sujeito passivo localizado no Estado – Decreto Estadual nº 20.686/1999, art. 102|
AM000003|Regime de Estimativa – saldo devedor apurado até o mês anterior – Decreto Estadual nº 20.686/1999, art. 46, caput e § 1º|
AM020001|Transferência de saldo devedor para o estabelecimento centralizador pelo estabelecimento não centralizador do sujeito passivo localizado no Estado – Decreto Estadual nº 20.686/1999, art. 102|
AM000004|Recebimento de saldo devedor do DIFAL – operação não incentivada|
AM000005|Recebimento de saldo devedor do DIFAL – operação incentivada|
AM000006|Recebimento de saldo devedor pelo estabelecimento centralizador do sujeito passivo – Decreto Estadual nº 35.756/2015, art. 2º, II, “a”|
AM000007|Transferência de saldo credor para o estabelecimento centralizador pelo o estabelecimento não centralizador do sujeito passivo – Decreto Estadual nº 35.756/2015, art. 2º, I “b”|
AM020014|Recebimento de saldo credor do DIFAL – operação não incentivada|
AM020015|Recebimento de saldo credor do DIFAL – operação incentivada|
AM020016|Transferência de saldo devedor para o estabelecimento centralizador pelo o estabelecimento não centralizador do sujeito passivo – Decreto Estadual nº 35.756/2015, art. 2º, I, “a”|
AM020017|Recebimento de saldo credor pelo o estabelecimento centralizador do sujeito passivo – Decreto Estadual nº 35.756/2015, art. 2º, II, “b”|
AM200001|Transferência de saldo credor do DIFAL – operação não incentivada|
AM200002|Transferência de saldo credor do DIFAL – operação incentivada|
AM220001|Transferência de saldo devedor do DIFAL – operação não incentivada|
AM220002|Transferência de saldo devedor do DIFAL – operação incentivada|
AM220003|Recolhimento antecipado do DIFAL|
AM209999|Outros débitos para ajuste de apuração ICMS Difal para a UF AM|
AM219999|Estorno de créditos para ajuste de apuração ICMS Difal para a UF AM|
AM229999|Outros créditos para ajuste de apuração ICMS Difal para a UF AM|
AM239999|Estorno de débitos para ajuste de apuração ICMS Difal para a UF AM|
AM249999|Deduções do imposto apurado na apuração ICMS Difal para a UF AM|
AM259999|Débito especial de ICMS Difal para a UF AM|
AM309999|Outros débitos para ajuste de apuração ICMS FCP para a UF AM|
AM319999|Estorno de créditos para ajuste de apuração ICMS FCP para a UF AM|
AM329999|Outros créditos para ajuste de apuração ICMS FCP para a UF AM|
AM339999|Estorno de débitos para ajuste de apuração ICMS FCP para a UF AM|
AM349999|Deduções do imposto apurado na apuração ICMS FCP para a UF AM|
AM359999|Débito especial de ICMS FCP para a UF AM|
AM020018|Crédito presumido de até 3% sobre faturamento das empresas prestadoras de serviço de comunicação - Decreto 37.464/2016|
AM020019|Crédito Presumido de 20% na prestação de serviço de transporte - Decreto Estadual nº 20.686/199, art. 20, § 17|
AM050028|FPS - artigo 2º, inciso III do Decreto Estadual nº 36.306/2015|
AM020020|Antecipação tributária - aquisição de mercadoria em outra unidade da federação - Decreto Estadual nº 20.686/1999, art. 20, X, e art. 118 - Crédito Extemporâneo|
AM020021|Importação de mercadoria estrangeira - Decreto Estadual nº 20.686/1999, art. 20, XI - Crédito Extemporâneo|
AM020022|Crédito presumido de 1% do valor dos débitos de ICMS relacionados à prestação de serviços de telecomunicação - Conv. ICMS 56/2012 e Decreto nº 32.775/2012|
AM020023|Crédito fiscal presumido - operação de transferência interestadual ou saída para comercialização de mercadorias provenientes de outras unidades da Federação adquiridas para emprego em virtude de garantia - Decreto Estadual nº 20.686/99, art. 310-F, § 1º|
AM020024|Retenção de ICMS Fornecedores do Estado - Decreto Estadual nº 22.061/2001, art. 3º|
AM020025|Retenção de ICMS Fonecedores da Prefeitura de Manaus - Decreto Estadual nº 22.361/2001, at. 2º.|
AM050029|ICMS Substituição Tributária sobre estoque de mercadorias - Regulamento do ICMS, art. 117-A, II, "a".|
AM020008|Despesas Aduaneiras – Decreto Estadual nº 20.686/1999, Regulamento do ICMS, art. 13, V e § 1º, e art. 98, VI|
AM020010|Recuperação de crédito de ICMS de mercadoria considerada “já tributada” – Pedido de Ressarcimento – Decreto Estadual nº 20.686/1999, Regulamento do ICMS, art. 373|
AM050025|FPS Entrada de Mercadoria Nacional – Decreto Estadual nº 38.006/17, art. 3º, I|
AM050026|FPS Mercadoria Importada do Exterior – Decreto Estadual nº 38.006/17, art. 3º, II|
AM150001|FPS – Operação Interestadual Substituição Tributária - Decreto Estadual nº 38.006/17, art. 3º, IV|
AM050027|FPS – Serviço de Comunicação de Televisão por Assinatura – Decreto Estadual nº 38.006/17, art. 3º, VII|
AM020026|Recuperação de crédito de ICMS de mercadoria considerada “já tributada” – levantamento de estoque – Decreto Estadual nº 20.686/1999, Regulamento do ICMS, art. 117-A, II, “b”|
AM020027|Recuperação de crédito de ICMS de mercadoria considerada “já tributada” – entrada de mercadoria (documento fiscal) – Decreto Estadual nº 20.686/1999, Regulamento do ICMS, art. 20, § 11|
AM020028|Crédito pelo pagamento de ICMS não diferido nos termos do Decreto 20.686/1999, Regulamento do ICMS, § 21, do art.109|
AM020029|Crédito pelo pagamento de ICMS não diferido – Decreto Estadual nº 20.686/1999, Regulamento do ICMS, art. 109, § 25|
AM020030|Crédito de ICMS relativo à mercadoria em estoque na data da exclusão de contribuinte do Simples Nacional, exceto mercadoria adquirida com substituição tributária ou com pagamento antecipado do imposto com encerramento de fase de tributação – Decreto Estadual nº 20.686/1999, Regulamento do ICMS, art. 20, caput, incisos I e II e art. 112|
AM040014|Crédito Estímulo do ICMS – 75% – Lei Estadual nº 2.826/2003, art. 13, caput, inciso III, combinado com Decreto Estadual nº 32.297/12, art. 3º, inciso II|
AM150002|ICMS Substituição Tributária sobre estoque de mercadorias – Decreto Estadual nº 20.686/1999, Regulamento do ICMS, art. 117-A, II, "a"|
AM020033|Ajuste a crédito decorrente de Regimes Especiais concedidos pelo Poder Executivo Estadual ou, de Convênios e Protocolos celebrados no âmbito do Confaz.|
AM010004|Estorno de crédito – optante pelo crédito presumido da Lei Complementar Estadual nº 202/2019|
AM020031|Crédito Presumido – extração de petróleo e gás natural e processamento de gás natural – Lei Complementar Estadual nº 202/2019, Art. 1º, § 1º, I|
AM020032|Crédito Presumido – fabricação de produtos do refino de petróleo e de gás natural – Lei Complementar Estadual nº 202/2019, Art. 1º, § 1º, II|
AM020034|Crédito de ICMS relativo à regularização de estoque (exceto mercadoria sujeita à substituição tributária), de acordo com o Decreto Estadual nº 20.686/1999, Regulamento do ICMS, art. 225, inciso VI e §3º|
AM040015|Cesta Básica – Lei nº 6.107/22 – dedução de 5% do ICMS que seria devido para apuração da contrapartida ao FPS a recolher|
AM020035|Crédito de ICMS relativo ao excesso de cota de LCD (Liquid Crystal Display), nos termos do Decreto 32.297/12, art. 3º, § 4°, inciso I; § 6º e § 7º|
AM030001|Estorno de débito de CT-e decorrente de emissão de CT-e substituto, nos termos do Ajuste Sinief 09/07, cláusula décima sétima, inciso III, alínea “c”.|
AM020036|Crédito de ICMS relativo a operações com álcool etílico hidratado combustível - AEHC e álcool para fins não-combustíveis nos termos do Protocolo ICMS 17/04, cláusula segunda.|
AM020037|Crédito pelo pagamento de ICMS relativo ao desembaraço não notificado, com permissão legal de crédito.|
AM020038|Crédito fiscal presumido conforme artigo 5º da Lei nº 6257/2023 e Resolução GSEFAZ nº 22/2023|"""

_RO = r"""RO010001|Estorno de créditos . Processo Administrativo ou Judicial|
RO020003|Crédito Fiscal - Antecipado|
RO020004|PIT - Crédito Presumido – implantação|
RO020005|PIT - Crédito Presumido - ampliação ou modernização|
RO030001|Estorno de débitos. Precesso Administrativo ou Judicial|
RO109999|Outros débitos para ajuste de apuração ICMS ST|
RO119999|Estorno de créditos para ajuste de apuração ICMS ST|
RO129999|Outros créditos para ajuste de apuração ICMS ST;|
RO139999|Estorno de débitos para ajuste de apuração ICMS ST|
RO149999|Deduções do imposto apurado na apuração ICMS ST|
RO059999|Outros Débitos Especiais|
RO010002|Estorno de Crédito Presumido Guajará-Mirim - Desinternamento Exportação|
RO010003|Estorno de Crédito Presumido Guajará-Mirim - desinternamento (exceto exportação)|
RO009999|Outros débitos para ajuste de apuração ICMS|
RO200001|Outros débitos para ajuste de apuração ICMS Difal para a UF RO - EC 87/2015|
RO211001|Estorno de créditos para ajuste de apuração ICMS Difal para a UF RO - EC 87/2015|
RO220001|Outros créditos para ajuste de apuração ICMS Difal para a UF RO – EC 87/2015|
RO231001|Estorno de débitos para ajuste de apuração ICMS Difal para a UF RO - EC 87/2015|
RO240001|Deduções do imposto apurado na apuração ICMS Difal para a UF RO - EC 87/2015|
RO250001|Débito especial de ICMS Difal para a UF RO - EC 87/2015|
RO030002|Estorno de débito para ajuste de apuração do ICMS - Remessa de mercadoria para venda fora do estabelecimento|
RO030003|Estorno de débito para ajuste de apuração do ICMS - Devolução de bilhetes de passagens empresa de transporte de passageiros|
RO000008|Débito para ajuste da apuração de ICMS referente ao DIFAL/EC-87|
RO000009|Débito para ajuste da apuração de ICMS referente ao FECOEP|
RO050010|Débito Especial à apuração do FECOEP|
RO030004|Estorno de Débito Referente ao FECOEP pago fora da apuração|
RO020009|Restituição de ICMS (Artigos 901 a 908 do RICMS/RO) - Valor a crédito|
RO050002|Contribuição para o FITHA - Fundo para a infraestrutura de transporte e habitação|
RO050003|Contribuição para o FIDER - Fundo de planejamento e desenvolvimento industrial de Rondônia|
RO050004|Fundo PROLEITE|
RO150001|Débito especial de ICMS-ST|
RO200002|Outros débitos para ajuste de apuração ICMS Difal para a UF RO|
RO211002|Estorno de créditos para ajuste de apuração ICMS Difal para a UF RO|
RO220002|Outros créditos para ajuste de apuração ICMS Difal para a UF RO|
RO231002|Estorno de débitos para ajuste de apuração ICMS Difal para a UF RO|
RO240002|Deduções do imposto apurado na apuração ICMS Difal para a UF RO|
RO250002|Débito especial de ICMS Difal para a UF RO|
RO300002|Outros débitos para ajuste de apuração ICMS FECOEP para a UF RO|
RO311002|Estorno de créditos para ajuste de apuração ICMS FECOEP para a UF RO|
RO320002|Outros créditos para ajuste de apuração ICMS FECOEP para a UF RO|
RO331002|Estorno de débitos para ajuste de apuração ICMS FECOEP para a UF RO|
RO340002|Deduções do imposto apurado na apuração ICMS FECOEP para a UF RO|
RO350002|Débito especial de ICMS FECOEP para a UF RO|
RO030005|PIT – Estorno de débito referente atividade industrial incentivada – somente atividade industrial e comercial|
RO020010|PIT – Crédito Presumido – atividade industrial e comercial – implantação|
RO020011|PIT – Crédito Presumido – atividade industrial e comercial – ampliação ou modernização|
RO050005|FUNCAFÉ/RO – Fundo de Apoio à Cultura do café em Rondônia|
RO050006|FGPPP/RO – Fundo Garantidor de Parcerias Público-Privadas|
RO010010|Estorno do crédito presumido ref. atividade industrial incentivada|
RO000010|Telecomunicações – ICMS proporcional às saídas isentas, não tributadas ou com redução de base de cálculo (§ 1º, Cláusula terceira, Convênio ICMS 17/2013) – Valor a débito|
RO000011|Telecomunicações – ICMS proporcional às cessões de meio destinadas a consumo próprio (§ 1º Cláusula terceira, Convênio ICMS 17/2013) – Valor a débito|
RO000012|Telecomunicações – ICMS complementar, na condição de responsável tributário (§ 2º, Cláusula terceira, Convênio 17/2013) – Valor a débito|
RO000013|Telecomunicações – ICMS COBILLING (Convênio ICMS 126/1998) - Valor a débito|
RO010011|ANULAÇÃO/ESTORNO DE CRÉDITO FISCAL|
RO020020|Crédito Presumido - Item 14 - Parte 2 - Anexo IV do RICMS - Valor a Crédito|
RO020015|Crédito Presumido - Item 3 - Parte 2 - Anexo IV do RICMS - Valor a Crédito|
RO020016|Crédito Presumido - Item 13 - Parte 2 - Anexo IV do RICMS - Valor a Crédito|
RO020017|Crédito Presumido - Item 15 - Parte 2 - Anexo IV do RICMS - Valor a Crédito|
RO020018|Crédito Presumido - Item 12 - Parte 2 - Anexo IV do RICMS - Valor a Crédito|
RO010017|Estorno de créditos para ajuste de apuração ICMS - Art. 47, Inciso I do RICMS/RO|
RO010012|Estorno de créditos para ajuste de apuração ICMS - Art. 47, Inciso III do RICMS/RO|
RO010013|Estorno de créditos para ajuste de apuração ICMS - Art. 47, Inciso IV do RICMS/RO|
RO010014|Estorno de créditos para ajuste de apuração ICMS - Art. 47, Inciso V do RICMS/RO|
RO010015|Estorno de créditos para ajuste de apuração ICMS - Art. 47, Inciso VI do RICMS/RO|
RO010016|Estorno de crédito - Contribuinte enquadrado no Simples Nacional|
RO020019|Crédito sujeito a homologação - RC 003/2018|
RO010018|Estorno de créditos para ajuste de apuração ICMS - Art. 47, Inciso II do RICMS/RO|
RO020014|CRÉDITO PRESUMIDO - ITEM 9 - PARTE 2 - ANEXO 4 DO RICMS/RO (Somente NFC-e)|
RO020021|Crédito referente à apuração CIAP - Ativo Permanente|
RO020022|Ressarcimento de Substituição Tributária em conta gráfica – Inciso I, Art. 21, parte I do Anexo IV do RICMS|31102024
RO020023|Ressarcimento – Crédito referente à operação própria do substituto tributário|31102024
RO020024|Ressarcimento Extemporâneo de Substituição Tributária em conta gráfica – Inciso I, Art. 21, parte I do Anexo IV do RICMS|31102024
RO020025|Ressarcimento Extemporâneo– Crédito referente à operação própria do substituto tributário|31102024
RO020033|Crédito mudança de tributação - Art. 48 - anexo VI do RICMS|
RO150002|Débito especial de ICMS-ST referente à apuração do FECOEP|
RO030006|Estorno de Débito para ajuste de apuração do ICMS - Serviços não medidos de televisão por assinatura, via satélite (art. 11, §6º, LC 87/96)|
RO020034|Crédito sujeito a rito especial de controle - inciso III, RC 01/2020.|
RO020035|Crédito sujeito a rito especial de controle - inciso IV, RC 01/2020.|
RO020036|Crédito sujeito a rito especial de controle - inciso V, RC 01/2020.|
RO020037|Crédito sujeito a rito especial de controle - inciso VI, RC 01/2020|
RO020038|Crédito sujeito a rito especial de controle - Parágrafo Único – Art. 4º - RC 01/2020.|
RO010019|Estorno de crédito – Saídas isentas ou não tributadas – RC 01/2020.|
RO120001|Ressarcimento de imposto retido por substituição tributária operações com gasolina, óleo diesel e álcool etílico hidratado carburante.|01022022
RO100001|Complementação de imposto retido por substituição tributária operações com gasolina, óleo diesel e álcool etílico hidratado carburante.|01022022
RO020039|Crédito fiscal de estoque remanescente – exclusão do Simples Nacional|
RO000015|Ato Concessório – Transferência de Créditos Fiscais, Art. 28 - Anexo IX – Valor a débito|
RO000014|Ajuste a Débito lançado pelo produtor de Biodiesel B100 optante pelo tratamento diferenciado, conforme Convênio ICMS 206/2021, correspondente ao valor do imposto nas operações com B100|
RO040002|Ajuste de Dedução do ICMS apurado oriundo dos créditos apropriados no Registro 1200, utilizado por produtor de biodiesel B100 optante pelo tratamento diferenciado, conforme Convênio ICMS 206/2021|
RO090001|Controle de Crédito Extra-Apuração a ser lançado pelo produtor optante pelo tratamento diferenciado conforme, Convênio ICMS 206/2021, correspondente ao imposto retido pelo substituto tributário nas operações com B100|
RO120002|Ajuste a Crédito ST da refinaria referente ao ressarcimento de ICMS concedido ao produtor de biodiesel B100 optante pelo tratamento diferenciado, conforme Convênio ICMS 206/2021|
RO020040|Crédito FITHA Serviço Telefônico fixo comutado Art.2°-B Parágrafo único LC.292/2003|
RO030007|Estorno de débito – Rondônia Rural Show|31072023
RO020041|Crédito – Guia DAS – Desenquadramento Simples Nacional|
RO020042|Crédito – Diferencial de Alíquota – Desenquadramento Simples Nacional|
RO000016|Débito NFe – Desenquadramento Simples Nacional|
RO000017|DÉBITO PARA AJUSTE NA APURAÇÃO DE ICMS DECORRENTE DE PENDÊNCIA NO FISCONFORME|
RO030008|PIT - Estorno de débito referente a arrecadação de ICMS MONOFÁSICO – PRODUTOR DE BIODISEL - Convênio ICMS n. 199/22, cláusula décima, III|
RO050007|DÉBITO NOTA FISCAL COMPLEMENTAR|
RO000018|Débito em razão de diferença de alíquota interestadual e interna - remessas entre estabelecimentos da mesma pessoa jurídica|30062024
RO020043|Crédito em razão de diferença de alíquota interestadual e interna - remessas entre estabelecimentos da mesma pessoa jurídica|30062024
RO030009|Estorno de débito – Rondônia Rural Show|31082024
RO020044|Crédito Presumido - Decreto 29.251/2024 (Convênio ICMS 198/2023)|
RO020045|Crédito Presumido - Atacadista na ALCGM – Decreto 28662/2023|
RO020046|Crédito Presumido – Atacadista - Decreto 28662/2023|
RO010020|Estorno de Crédito - produtos importados – art.10, inciso I, Decreto 28662/2023|
RO010021|Estorno de Crédito – demais operações – art.10, inciso II, Decreto 28662/2023|
RO050008|CONTRIBUIÇÃO PARA O FUNDAT|
RO020047|Ressarcimento de Substituição Tributária em conta gráfica - Inciso I, Art. 21, parte 1 do Anexo VI do RICMS.|
RO020048|Ressarcimento Extemporâneo de Substituição Tributária em conta gráfica - Inciso I, Art. 21, parte 1 do Anexo VI do RICMS.|
RO020049|Ressarcimento – Crédito referente à operação própria do substituto tributário.|
RO020050|Ressarcimento Extemporâneo – Crédito referente à operação própria do substituto tributário.|
RO010022|Estorno de Crédito Presumido (Estoque – Convênio ICM 65/88) – Art. 11, III, Decreto 28.662/2023|
RO030010|Estorno de débito – Rondônia Rural Show|31082025
RO010023|Estorno de crédito referente a mercadoria remetida com isenção para ZFM ou ALC|
RO120003|Ressarcimento de Substituição Tributária em conta gráfica - § 5° do Art. 24-A do Anexo VI do RICMS/RO|
RO100002|Complemento de Substituição Tributária em conta gráfica - § 5° do Art. 24-A do Anexo VI do RICMS/RO|
RO010024|Estorno de crédito presumido do estoque decorrente do Convênio ICM 65/88 - contribuintes detentores do regime especial da Lei 5.710/23 estabelecidos na ALCGM - Art. 7º, II, Decreto 29.232/2024.|
RO030011|Estorno de débito – Rondônia Rural Show|31082026"""


def _parse(txt):
    out = {}
    for ln in txt.splitlines():
        c = ln.split('|')
        if len(c) >= 2 and len(c[0].strip()) == 8:
            out[c[0].strip()] = c[1].strip()
    return out


TABELA_5_1_1 = {'AM': _parse(_AM), 'RO': _parse(_RO)}


def carregar_tabela_externa(caminho):
    """Lê uma tabela 5.1.1 baixada do serviço oficial (1ª linha = 'versão=…', depois COD|DESC|DT_INI|DT_FIM)."""
    try:
        with open(caminho, 'r', encoding='utf-8') as fh:
            return _parse(fh.read())
    except Exception:
        return {}

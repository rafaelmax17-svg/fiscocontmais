# Fechamento Fiscal (Admin) — plano (PAUSADO em 24/10/2026)

Módulo só do Admin. Retomar quando o Rafael pedir. Telas aprovadas em imagem: Painel · 1 Importar · 2 Análises e correções ·
3 Notas e acumuladores · 4 CFOPs · 5 Produtos · 6 Serviços tomados · 7 Apuração e SPED.

## Entrada de dados (três tipos de cliente)
- SPED Fiscal do cliente: ao importar, escolher **Entradas**, **Saídas** ou **Completo** (há cliente que manda só as entradas).
- XMLs (.zip): NF-e, NFC-e, CT-e, NFCom e NFS-e; entrada/saída identificada sozinha (CNPJ da empresa × emitente/destinatário, tpNF);
  canceladas pelo evento de cancelamento no ZIP ou consulta na SEFAZ com o certificado (situação 02).
- Lançamento fiscal avulso (documento sem XML).
- Botão **Salvar dados** (local, por empresa e competência), para continuar depois.

## Análises automáticas (reaproveitar o Corretor do SPED)
- Combustível pelo NCM: produto que não é combustível com CFOP de combustível → CFOP certo; combustível para consumo 1653/2653 sem crédito (LC 192/2022).
- Uso e consumo: 1556/2556 (1407/2407 com ST), CST x90, BC/ICMS zerados (LC 87/96, art. 33, I).
- ST (Anexo VI RICMS/RO, NCM/CEST ou ICMS-ST no XML): 1403/2403, CST x60. 1º dígito do CST (origem) vem do XML.
- ICMS × XML, valor/base × XML, crédito do Simples (só revenda/industrialização), DIFAL, VL_MERC, COD_SIT 08.
- Sem regra objetiva → "confirmar" (nunca decidir sozinho). Cada correção com antes/depois e base legal.

## Saídas e dashboards
- CFOPs **todos, um por um** (nunca "Outros"), com a descrição oficial, notas, valor, ICMS e acumulador.
- Acumulador (código do Domínio) aprendido por empresa; revenda × consumo aprendido por fornecedor/produto.
- Produtos: NCM (TIPI), CEST (Conv. ICMS 142/2018), ST/alíquota em RO, mudanças mês a mês, vínculo 0220.
- NFS-e tomadas: retenções (ISS, IRRF, INSS, PIS/COFINS/CSLL) lidas do XML padrão nacional.
- Apuração E110/E111/E116, E200, E300; gerar SPED (fases: 0, C, D, E, 9 → depois H, K, G, 1).

## Para começar
Caso real: SPED de cliente que manda só as entradas + ZIP de XMLs do mesmo mês; e um mês já entregue (XMLs + SPED transmitido) para comparar registro a registro.

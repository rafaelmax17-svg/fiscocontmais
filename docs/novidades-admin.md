# Novidades do Admin (privativo)

Itens de administração que **não** entram nas "Novidades" mostradas a todos no sistema.
As notas em `release-notes/` são vistas por toda a equipe: nelas vai só o que muda para quem usa o sistema no dia a dia.

## 2.1.33

- **Corretor do SPED Fiscal · Cadastro de produtos (0200):** botão novo. Lista os produtos cadastrados como mercadoria para revenda (TIPO_ITEM 00) que no período só entraram como uso e consumo (CFOP x556, x407, x653 → sugestão 07) ou ativo (x551, x406 → 08). Dá para trocar a sugestão e só os marcados mudam (campo 07 do 0200). Produto que também aparece em saída (C170 de saída, C321, C425, C470), inventário (H010), K200 ou entrada para revenda fica em "Não alterar". Nenhuma linha entra ou sai, então o bloco 9 fica igual; arquivo assinado perde a assinatura (assinar de novo no PVA). Corrigir também o cadastro no Domínio. Base: Guia Prático da EFD ICMS/IPI, registro 0200, campo 07.

## 2.1.32

- **Auditoria Interna · Excel:** aba nova **"Acumulador 7000 por NF"**. Para cada nota com itens no acumulador genérico 7000 (COD_NAT do C170), três níveis com o agrupamento do Excel (botões 1/2/3): nota → acumulador de despesa sugerido (7001 a 7040, mesmas regras do corretor: descrição, NCM e CFOP) com descrição, valor e % da nota → produtos daquele acumulador (item, código, descrição, NCM, CFOP, motivo e confiança). Nota com produtos de naturezas diferentes fica em laranja como **Mista**: o sistema só destaca, não escolhe. O número da nota se repete em todas as linhas para o filtro trazer a nota inteira. Valores líquidos de desconto (VL_ITEM − VL_DESC).

## 2.1.31

- **Auditoria Interna (novo módulo de teste, só Admin):** escolha o SPED Fiscal e clique em "Auditar entradas". Abre uma página com duas abas:
  - **Relatório de tributação:** entradas por produto (código, descrição, NCM, CFOP, CST, alíquota, base, ICMS, ICMS-ST, IPI), gráficos por CFOP, CST, alíquota e fornecedor, filtros, busca e as notas de cada produto. Nota sem C170 entra pelos totais do C190, marcada "nota sem item".
  - **Auditoria de tributação** por produto (Confere / Divergente / Verificar / Informativo, sempre com a base legal): ICMS-ST pela lista vigente do RICMS/RO, Anexo VI, Parte 2 (consolidado até o Dec. 31.963/26: 477 CEST vigentes; revogados e redações anteriores fora; Tabela XXVI só porta a porta); alíquota interna pela Lei 688/96, art. 27 e 27-A (Fecoep), e interestadual pelas Res. do Senado 22/89 e 13/12; crédito de ICMS em uso e consumo/ativo e CST × crédito; DIFAL sem C197; combustível monofásico (CST 61/60); crédito de PIS/COFINS em monofásico; tipo do produto no 0200 × CFOP.
  - Exporta **HTML animado** e **Excel detalhado** (abas Resumo, Itens das notas, Por produto, Auditoria, Por CFOP, Por CST, Por alíquota, Por fornecedor).
  - Ainda fora: benefícios de RO (Anexos I e II, isenção e redução de base). Por isso, alíquota menor que a interna aparece como "Verificar".
  - A lista de ST é gerada por `tools/gerar_st_ro.py` a partir do texto do Anexo VI (rodar de novo quando sair decreto novo).
  - Depois de testado, a ideia é levar para o Auditor de Classificação (botão separado).

## 2.1.30

- **Corretor do SPED Fiscal · Acumulador 7000:** botão novo "Acumulador 7000". Lê os C170 com COD_NAT 7000 (DESPESAS), agrupa por produto e sugere o acumulador de despesa certo (7001 a 7040) pela descrição e pelo NCM; CFOP x910/x911 → 7026, x922 → 7028, x116/x117 → 7029. Revenda lançada no 7000 é tratada como despesa. Alimentos vão para 7003 (arroz, feijão, óleo, macarrão) e 7009 (café, açúcar, coador).
  - Confiança alta (descrição e NCM concordam) ou média (só um dos dois). Toda sugestão pode ser trocada na tela; só os produtos marcados mudam.
  - Ao aplicar: troca o COD_NAT dos itens marcados, cadastra no 0400 os acumuladores novos (sem acento), tira o 0400 do 7000 se ficar sem uso e recalcula os totais dos blocos e o bloco 9. Gera arquivo novo; o original não muda.
  - Arquivo assinado no PVA: a assinatura é retirada e o arquivo precisa ser assinado de novo no PVA.
  - Para não voltar no mês seguinte, trocar também o acumulador padrão do produto no Domínio.

## 2.1.29

- **Correção da EFD-Contribuições · notas sem item:** nova opção na tela "Notas sem item: incluir item (entrada CST 70 · saída CST 49)". Ligada, cada C100 sem C170 recebe um item único (código DOCSEMITEM, cadastrado no 0200 como tipo 99) sem PIS/COFINS: entrada com CST 70; saída com CST 49 (CST de entrada não é aceito em nota de saída). CFOP 5929 quando há NFC-e do mesmo cliente, dia e valor; senão 5949/1949 (a conferir no XML). Conta: entrada → conta das demais entradas; saída → conta das NFC-e (ex.: 408). Desligada, só aponta como antes.

## 2.1.28

- **Correção da EFD-Contribuições · conta dos itens de entrada:** C170 de entrada (C100 com IND_OPER 0) com COD_CTA em branco recebe a conta de uso e consumo (CFOP 1556, 1407, 2556, 2407 → padrão 359) ou a conta das demais entradas (padrão 55). As duas contas ficam em campos novos na tela e só são usadas se forem analíticas no 0500; itens que já têm conta não mudam.
- **M400/M800 com conta sintética:** troca pela conta analítica usada nos M410/M810 do mesmo CST (ex.: 405 sintética → 408 Venda de mercadorias).
- **C100 sem C170:** passa a ser apontado como pendência (não cria item sozinho). Quando há NFC-e do mesmo cliente, dia e valor, avisa que pode ser NF-e emitida para acobertar a NFC-e (CFOP 5929/6929), cuja receita já está no C175.

## 2.1.27

- Consulta Manifestação NF-e retirada temporariamente (botão escondido e IPC bloqueado por MANIF_ATIVA = false no renderer/app.js e no electron/main.js). Motivo: a consulta na SEFAZ do estado devolveu "não consta" (217) numa chave de RO; a ideia é refazer usando o Ambiente Nacional (NFeDistribuicaoDFe) como fonte principal. O código continua no sistema para religar depois.

## 2.1.25

- Consulta Manifestação NF-e liberada para toda a equipe (deixou de ser só do Admin).

## 2.1.24

- **Consulta Manifestação NF-e (Baixas DF-e, só Admin por enquanto):** botão laranja nas Baixas DF-e abre uma tela cheia. Escolha a empresa destinatária (o certificado cadastrado nas Baixas DF-e) e cole as chaves (ou importe .txt/.xlsx); chaves inválidas (tamanho ou dígito verificador) e repetidas são apontadas antes. Se a empresa não tem certificado (ou está vencido), aparece o aviso com "Cadastrar certificado desta empresa", e depois de salvar o sistema volta para a consulta com as chaves.
  - Só consulta: NfeConsultaProtocolo 4.00 na SEFAZ autorizadora (pela UF da chave; se falhar, tenta SVRS e SVAN) e resumo da nota no Ambiente Nacional (DistDFe por chave) para emitente, valor e emissão. Sem resumo, o nome do emitente vem pelo CNPJ; o valor fica "—".
  - Dashboards: cartões por tipo (confirmada, só ciência, sem manifestação, desconhecida, operação não realizada), rosca, situação na SEFAZ com alerta de canceladas, prazo do evento conclusivo (180 dias da autorização), tabela com filtros, exportar Excel/HTML.
  - Resultados guardados em manifestacao-cache.json: manifestação conclusiva e nota cancelada não são consultadas de novo; as demais só depois de 1 hora (a SEFAZ bloqueia consulta repetida). Consulta em partes de 100 chaves.
  - Para testar: ver se a SEFAZ devolve os eventos de manifestação em cada estado.

## 2.1.21

- **Manual do Fiscal · Publicar manual e Acessos:** na tela do manual, só o Admin vê "Publicar manual" (escolhe a pasta com manual.json + imagens das páginas; troca o manual para todos na hora) e "Acessos" (quem abriu, quando e por quanto tempo). Dados no Firestore: manual_fiscal (leitura: equipe ativa; gravação: Admin) e manual_acessos (cada pessoa grava o próprio registro; só o Admin lê). O conteúdo não vai no instalador nem no repositório.

## 2.1.6

- **Fechamento da equipe · Inativar:** o botão "Inativar" (no lugar do excluir) mantém a empresa no mês aberto, com a etiqueta "inativa a partir de …", e tira ela do mês seguinte em diante (inclusive de meses já abertos). "Reativar" desfaz: ela volta nos próximos meses.

## 2.1.4

- **Fechamento da equipe (Simples Nacional):** só o Admin cadastra empresa (CNPJ com busca na Receita, analista e mês de início), altera nome ou analista (✎) e exclui (🗑, a partir da competência aberta; os meses anteriores continuam com ela). As 97 empresas da planilha de setembro/2026 entram na primeira vez que o Admin abre a aba. Dados no Firestore em fechamento_sn (cadastro: só Admin grava; competências AAAA-MM: equipe ativa).
- **Correção da EFD-Contribuições · conta contábil dos ajustes:** M115/M225/M515/M625 com COD_CTA em branco (erro do PVA "O campo é de preenchimento obrigatório... conta contábil analítica... registro 0500") passam a ser preenchidos com a conta dos itens da nota cuja chave está na descrição do ajuste (mesmo CST); se não houver, com a mesma conta dos outros ajustes do arquivo; ou com a conta digitada no novo campo "Conta dos ajustes" da tela. A conta precisa ser analítica no 0500; senão fica pendência.
- **Corretor do SPED · crédito do Simples:** nota de uso e consumo (CFOP 1556/2556/1407/2407/1653/2653), ativo imobilizado (1551/2551/1406/2406) ou uso em serviço do ISS (1128/2128) não gera mais "Crédito a incluir": aparece como "Uso e consumo · sem crédito", com a base legal (LC 123/2006, art. 23, § 1º; LC 87/1996, art. 33, I). Se já houver C197 ou ICMS no C190, a nota vai para "Sem direito a crédito" com a opção de retirar. Nota mista: o crédito conta só os itens de comercialização ou industrialização.

## 2.1.2

- **Trava por inatividade do Admin:** passou de 15 para 40 minutos sem uso (os demais continuam com 60).
- Seções "Admin" nas Novidades ficam escondidas para quem não é Admin.

## 2.1.1

- **Cadastro com senha provisória:** na tela Usuários, "Cadastrar e gerar senha" cria a pessoa e mostra uma senha provisória para copiar e enviar. No primeiro acesso ela é obrigada a criar a própria senha.
- **Gerar nova senha:** quem esqueceu a senha fala com o Admin; na tela Usuários, "Gerar nova senha" cria outra provisória e derruba as sessões abertas da pessoa.
- **Módulos por usuário:** o Admin escolhe quais módulos cada pessoa vê (colunas Fiscal, Contábil e Administração). Usuários e Licenças continuam só do Admin.
- **Admin principal protegido:** o usuário rafael.max17@gmail.com não pode ser bloqueado, ter o perfil, os módulos ou a senha alterados por ninguém (tela, funções do servidor e regras do Firestore).
- **Servidor:** cadastro de usuários, nova senha e chat de ajuda tributária rodam em funções no Google (southamerica-east1). A chave da IA e a credencial de administrador não ficam em nenhum computador.

## 2.1.0

- **Tela "Usuários"** (menu Administração): cadastrar, bloquear, ativar e mudar perfil.
- **Licenças de acesso:** funciona em qualquer computador do Admin, sem a credencial administrativa da nuvem, e mostra a versão instalada e o usuário de cada máquina.
- A credencial administrativa antiga da nuvem é apagada dos computadores.
- A nuvem (histórico de balancetes) e a chave da IA só abrem para usuário logado e ativo.
- As atualizações passam a ser baixadas do repositório de instaladores (fiscocontmais-releases).
- **Corretor do SPED Fiscal · "Estoque que saiu da ST"** (RICMS/RO, Anexo VI, arts. 46 a 48): planilha do estoque + XMLs de entrada → crédito item a item (MVA ajustada × alíquota interna), Bloco H com motivo 02, 0200 que faltavam, ajuste RO020033 e apuração refeita; confere o limite de 5.000 UPF/RO quando a UPF é informada; ST paga por nota é opcional.
- **Corretor do SPED Fiscal · dois erros do PVA no "Corrigir SPED":** VL_MERC menor que a soma dos itens (C170) → VL_MERC passa a ser a soma; CNPJ da chave diferente do participante → situação 08.

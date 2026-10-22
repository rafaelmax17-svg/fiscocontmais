# FiscoCont+ 2.1 — passo a passo para ativar a segurança (só o Admin)

Faça na ordem. Os passos 1 a 4 são feitos uma única vez.

## 1. Repositório público só de instaladores
1. No GitHub, crie o repositório **rafaelmax17-svg/fiscocontmais-releases**, **Público**, marcando **"Add a README file"** (ele não pode ficar vazio).
2. Crie um token: GitHub > Settings > Developer settings > Personal access tokens > **Fine-grained tokens** > Generate new token.
   - Repository access: *Only select repositories* > **fiscocontmais-releases**.
   - Permissions > Repository permissions > **Contents: Read and write**.
3. No repositório **fiscocontmais**: Settings > Secrets and variables > Actions > New repository secret.
   - Name: `RELEASES_TOKEN` · Secret: o token criado.

## 2. Firebase: login por e-mail e senha
Console do Firebase (projeto fiscocontmais) > **Authentication** > Sign-in method > **E-mail/senha** > Ativar > Salvar.
(Deixe o "Anônimo" também ativado: ele continua sendo usado pela licença de cada máquina.)

## 3. Gerar e publicar a 2.1.0
1. Rode o release da **v2.1.0** como sempre.
2. A release aparece como rascunho em **dois lugares**: no fiscocontmais e no fiscocontmais-releases.
   - **Publique as duas.** As máquinas que estão na 2.0.0 ainda procuram atualização no fiscocontmais; a partir da 2.1 elas procuram no fiscocontmais-releases.

## 4. Regras de Segurança do Firestore (no mesmo dia da 2.1)
Console do Firebase > Firestore Database > **Regras** > apague tudo, cole o conteúdo do arquivo `firestore.rules` (raiz do projeto) e clique em **Publicar**.
- Depois disso, versões antigas (2.0.0 ou anteriores) deixam de sincronizar balancetes até atualizar. Por isso publique as regras logo depois da 2.1.

## 5. Primeiro acesso do Admin
1. Abra o FiscoCont+ 2.1, digite **rafael.max17@gmail.com** e a senha que quer usar (mínimo 6 caracteres, de preferência uma senha NOVA) e clique em **Entrar**.
2. Como a conta ainda não existe, o sistema cria a conta e avisa que mandou um e-mail de confirmação. Abra o e-mail (confira o spam) e clique no link.
3. Volte ao sistema e clique em **Entrar** de novo com o mesmo e-mail e senha. Você entra como Admin.
(Não existe link de "primeiro acesso" na tela: isso só funciona para o e-mail do Admin.)

## 6. Cadastrar a equipe
Administração > **Usuários** > nome, e-mail e perfil > **Cadastrar e enviar convite**. Cada pessoa recebe o e-mail para criar a senha.

## 7. Tornar o código privado
No painel **Licenças de acesso**, a coluna **Versão** mostra a versão de cada computador. Quando todos estiverem na 2.1 ou acima:
GitHub > fiscocontmais > Settings > General > Danger Zone > **Change visibility** > Private.
- Daqui para a frente, publique só o rascunho do **fiscocontmais-releases** (é dele que as atualizações vêm).

## Observações
- O sistema só abre com internet (não há mais entrada offline). A opção "Salvar meus dados" guarda e-mail e senha no cofre do Windows daquele usuário; quem desmarcar apaga.
- A chave da IA continua no Firestore (`config/chat_ia`), agora legível só para usuário logado e ativo. Como não há plano Blaze (Cloud Functions), ela ainda passa pela memória do computador durante o uso. Mantenha um **limite de gastos** na conta da Anthropic.
- As senhas antigas (fixas no código) deixam de funcionar na 2.1. Como elas ficaram no histórico do GitHub, não as reutilize em lugar nenhum.

## A partir da 2.1.1: publicação automática
- Quando uma versão fica pronta, o Claude envia a tag (ex.: v2.1.2) e o GitHub gera o instalador e PUBLICA sozinho em fiscocontmais-releases. Não há mais rascunho para publicar a mão, nem release no fiscocontmais.
- As funções e as regras do Firebase também são publicadas sozinhas quando mudam (workflow "Publicar funções e regras no Firebase").

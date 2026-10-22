# Novidades do Admin (privativo)

Itens de administração que **não** entram nas "Novidades" mostradas a todos no sistema.
As notas em `release-notes/` são vistas por toda a equipe: nelas vai só o que muda para quem usa o sistema no dia a dia.

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

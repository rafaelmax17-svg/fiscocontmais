# App Android do FiscoCont+ — plano (PAUSADO em 24/10/2026)

Retomar quando o Rafael pedir. Telas aprovadas em imagem: Login · Clientes · Cliente (publicações) · Dashboard · Fechamento da equipe · Admin.

## O que o app faz
- Consulta dos dados importados no PC. No FiscoCont+ (PC), um botão **pequeno** (ícone de celular, ao lado de "Exportar HTML")
  "Publicar no app" envia só os números/gráficos do painel (SPED Fiscal, EFD-Contribuições, Painel do Simples) para a nuvem,
  ligados ao cliente (CNPJ) e à competência; republicar substitui. Arquivos (SPED/XML) ficam no computador.
- No app: login (mesmo usuário; digital), lista de clientes, publicações por módulo/mês, dashboards **animados** (mesmos painéis HTML,
  animação repete ao voltar à tela), Fechamento da equipe ao vivo (já está no Firestore), área Admin (usuários, licenças, avisos).
- Permissões iguais às do sistema (módulos por usuário; Admin só para o Admin).

## Técnica prevista
- App com Capacitor reaproveitando os painéis HTML; publicação em Firebase Storage + índice no Firestore; regras por perfil/módulo.
- APK gerado pelo GitHub Actions (o ambiente do Claude não tem SDK Android).
- Pendente decidir: quem publica no PC (padrão: só o Admin).

## Distribuição (regra do Google no Brasil desde 30/09/2026)
- APK instalado direto exige desenvolvedor verificado. Conta gratuita de distribuição limitada (~20 instalações/aparelhos, sem taxa)
  ou verificação completa (US$ 25 única + documento; empresa pede D-U-N-S). Registrar o pacote `br.com.liddera.fiscocont` e a
  impressão digital da chave de assinatura.

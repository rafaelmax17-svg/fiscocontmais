'use strict';
// Menu agrupado (2.4.19) — pedido do Rafael, 22/11/2026 ("modelo B": menu curto + página do grupo com cartões).
//
// Os botões antigos do menu continuam no HTML e continuam sendo a fonte de tudo: permissões por usuário (role-hidden),
// selos NOVO, contadores (Fisconforme, DAREs, GIAM), resumos e a abertura de cada tela (switchView). Este arquivo só:
//   • esconde esses botões e coloca no lugar um botão por GRUPO;
//   • clicando no grupo, abre a página do grupo com um cartão por módulo liberado; o cartão clica o botão antigo;
//   • o grupo só aparece se tiver pelo menos um módulo liberado; contador vermelho = soma dos contadores dos módulos.
// Os cartões SEFIN-RO (Fisconforme, DARE, GIAM) e EFD-Reinf continuam na lateral exatamente como estão (pedido do Rafael).
// Ícones dos grupos: Microsoft Fluent Emoji 3D (licença MIT, img/menu/LICENSE-fluent-emoji.txt), guardados no programa.
// Volta ao menu antigo a qualquer momento pelo link "Menu clássico" no rodapé do menu (guardado neste computador).

(() => {
  const CHAVE = 'fc_menu';
  const GRUPOS = [
    { id: 'painel', sec: 'Fiscal', nome: 'Painel do SPED', sub: 'visão do SPED Fiscal importado', views: ['fiscal-dash', 'manual-fiscal'], reset: true,
      ic: '<path d="M4 13h6V4H4zM14 20h6V4h-6zM4 20h6v-4H4z"/>' },
    { id: 'conf', sec: 'Fiscal', nome: 'Conferências', sub: 'compara XMLs e SPED, nota por nota', views: ['fiscal-conf', 'fiscal-docs', 'fiscal-confs', 'fiscal-deson', 'fiscal-frete', 'fiscal-inut'],
      ic: '<path d="M9 11l3 3 8-8M4 12a8 8 0 108-8"/>' },
    { id: 'analise', sec: 'Fiscal', nome: 'Análise e Apuração', sub: 'classificação, tributação e Reforma Tributária', views: ['fiscal-audit', 'fiscal-atrib', 'fiscal-rtc'],
      ic: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8M8 11h2M12 11h2M16 11h0M8 15h2M12 15h2M8 18h8"/>' },
    { id: 'notas', sec: 'Fiscal', nome: 'Notas e documentos', sub: 'baixa automática e consulta de documentos', views: ['fiscal-downloads', 'fiscal-nfechave'],
      ic: '<path d="M12 4v11M7.5 11.5L12 16l4.5-4.5M5 20h14"/>' },
    { id: 'federais', sec: 'Fiscal', nome: 'Obrigações federais', sub: 'PIS/Cofins, MIT e Simples Nacional', views: ['fiscal-efd-contrib', 'fiscal-mit', 'fiscal-pgdas'],
      ic: '<path d="M3 10l9-6 9 6M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 21h18"/>' },
    { id: 'contabil', sec: 'Contábil', nome: 'Balancete e DRE', sub: 'análise do balancete do Domínio', views: ['overview', 'dre', 'balancete', 'invertidas', 'indicadores', 'historico', 'lote-balancetes', 'conciliacao'],
      ic: '<path d="M4 19V5m0 14h16M8 15l3-4 3 2 4-6"/>' },
    { id: 'admin', sec: 'Administração', nome: 'Administração', sub: 'usuários, correções e módulos em teste', views: ['admin-usuarios', 'admin-lic', 'admin-integra', 'admin-corrigir-sped', 'admin-corrigir-efd', 'admin-lmc',
      'admin-radar', 'admin-audam', 'admin-evo', 'admin-legal', 'admin-frete-pis', 'admin-planilhas', 'admin-bi'],
      ic: '<path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/>' },
  ];
  const DESC = {
    'fiscal-dash': 'faturamento, ICMS, entradas e saídas do mês', 'manual-fiscal': 'passo a passo do fechamento',
    'fiscal-conf': 'XMLs que faltam ou sobram no SPED', 'fiscal-docs': 'todas as entradas por fornecedor e CFOP', 'fiscal-confs': 'NF-e e NFC-e de saída × SPED',
    'fiscal-deson': 'desoneração dos XMLs × SPED', 'fiscal-frete': 'classificação e crédito do frete', 'fiscal-inut': 'numeração inutilizada × escrita',
    'fiscal-audit': 'CFOP × CST e itens com tributação diferente', 'fiscal-atrib': 'tributação por produto nas entradas e saídas', 'fiscal-rtc': 'simulação de IBS e CBS',
    'fiscal-downloads': 'NF-e, NFC-e, CT-e e NFS-e de cada empresa', 'fiscal-nfechave': 'XML e DANFE pela chave de acesso',
    'fiscal-reinf': 'retenções, fechamento, guia e transmissão da DCTFWeb', 'fiscal-efd-contrib': 'conferência de PIS e Cofins', 'fiscal-mit': 'envio do MIT pela EFD-Contribuições, guia e DCTFWeb', 'fiscal-pgdas': 'fechamento e painel do cliente (PGDAS)',
    'fiscal-fisconforme': 'notificações de todas as empresas', 'fiscal-dare': 'débitos, guias e extratos', 'fiscal-giam': 'recibos de entrega e produtor rural',
    overview: 'resumo do balancete importado', dre: 'DRE com receitas × despesas', balancete: 'todas as contas, com exportação', invertidas: 'contas com saldo do lado errado',
    indicadores: 'liquidez, margens e endividamento', historico: 'balancetes já analisados', 'lote-balancetes': 'vários balancetes de uma vez', conciliacao: 'extrato × fornecedores → TXT do Domínio',
    'admin-usuarios': 'cadastro, módulos e senhas', 'admin-lic': 'computadores liberados', 'admin-integra': 'chave e computador da Receita', 'admin-corrigir-sped': 'Corretor completo',
    'admin-corrigir-efd': 'erros do PVA', 'admin-lmc': 'combustíveis', 'admin-radar': 'monofásico, Tema 69, CIAP', 'admin-audam': 'ICMS do Amazonas', 'admin-evo': 'faturamento e tributos no período',
    'admin-legal': 'dados cadastrais e certidões', 'admin-frete-pis': 'crédito do frete FOB', 'admin-planilhas': 'planilhas do cliente', 'admin-bi': 'indicadores da empresa',
  };
  // ícone colorido de cada módulo (img/menu/m-<view>.png); sem ícone próprio, usa o do botão antigo
  const IMG = new Set(['fiscal-mit', 'admin-audam', 'admin-bi', 'admin-corrigir-efd', 'admin-corrigir-sped', 'admin-evo', 'admin-frete-pis', 'admin-integra', 'admin-legal', 'admin-lic', 'admin-lmc', 'admin-planilhas', 'admin-radar', 'admin-usuarios', 'balancete', 'conciliacao', 'dre', 'fiscal-atrib', 'fiscal-audit', 'fiscal-conf', 'fiscal-confs', 'fiscal-dash', 'fiscal-deson', 'fiscal-docs', 'fiscal-downloads', 'fiscal-efd-contrib', 'fiscal-frete', 'fiscal-inut', 'fiscal-nfechave', 'fiscal-pgdas', 'fiscal-rtc', 'historico', 'indicadores', 'invertidas', 'lote-balancetes', 'manual-fiscal', 'nova', 'overview']);
  const ADM_TESTE = new Set(['admin-radar', 'admin-audam', 'admin-evo', 'admin-legal', 'admin-frete-pis', 'admin-planilhas', 'admin-bi']);

  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let nav = null, hub = null, aberto = '', ligado = false, obs = null, agenda = 0;

  const modoGrupos = () => { try { return localStorage.getItem(CHAVE) !== 'classico'; } catch (_) { return true; } };
  const botao = (v) => (nav ? nav.querySelector(`.nav-item[data-view="${v}"]`) : null);
  const visivel = (b) => !!b && !b.classList.contains('role-hidden') && !b.hidden;
  const nomeDe = (b) => { const s = b.querySelector('.nc-tx span') || b.querySelector('span'); return s ? s.innerHTML : ''; };
  const textoDe = (b) => { const s = b.querySelector('.nc-tx span') || b.querySelector('span'); return s ? s.textContent.trim() : ''; };
  const cont = (b) => { const c = b.querySelector('.nc-cnt, .pill'); return c && !c.hidden && c.textContent.trim() ? c.textContent.trim() : ''; };
  const novo = (b) => { const n = b.querySelector('.nav-new'); return n && !n.hidden ? n.textContent.trim() : ''; };
  const resumo = (b) => { const s = b.querySelector('.nc-tx small'); return s ? s.textContent.trim() : ''; };
  function icone(b) {
    const img = b.querySelector('.nc-ic img');
    if (img) return `<img src="${esc(img.getAttribute('src'))}" alt="">`;
    const svg = b.querySelector('svg.ic');
    return svg ? svg.outerHTML : '';
  }

  // ---------------------------------------------------------------- lateral
  const html = (lista) => {
    let sec = '';
    return lista.map((g) => {
      const t = g.sec !== sec && g.sec !== 'Fiscal' ? `<div class="mg-sec" data-mgsec="${esc(g.sec)}">${esc(g.sec)}</div>` : '';
      sec = g.sec;
      return `${t}<button class="mg-item" data-mg="${g.id}"><b class="mg-ic"><img src="img/menu/g-${g.id}.png" alt=""></b><span>${esc(g.nome)}</span><i class="mg-cnt" hidden></i><em class="mg-novo" hidden>NOVO</em></button>`;
    }).join('');
  };
  function montaLateral() {
    if (nav.querySelector('.mg-lista')) return;
    // Fiscal antes dos cartões SEFIN-RO; Contábil e Administração depois do cartão da REINF
    const fiscais = GRUPOS.filter((g) => g.sec === 'Fiscal'), resto = GRUPOS.filter((g) => g.sec !== 'Fiscal');
    const a = document.createElement('div'); a.className = 'mg-lista'; a.innerHTML = html(fiscais);
    const b = document.createElement('div'); b.className = 'mg-lista'; b.innerHTML = html(resto);
    const sefin = nav.querySelector('.nav-group-sefin');
    const contabil = nav.querySelector('.nav-group[data-group="contabil"]');
    if (sefin) nav.insertBefore(a, sefin); else nav.prepend(a);
    if (contabil) nav.insertBefore(b, contabil); else nav.appendChild(b);
    [a, b].forEach((box) => box.addEventListener('click', (ev) => { const bt = ev.target.closest('[data-mg]'); if (bt) abrir(bt.dataset.mg); }));
  }
  // grupos visíveis, contadores e qual está ativo (agrupa as mudanças num só redesenho)
  function atualiza() {
    if (agenda) return;
    agenda = requestAnimationFrame(() => {
      agenda = 0;
      if (!ligado) return;
      const ativoView = (nav.querySelector('.nav-item.active') || {}).dataset;
      const secOk = {};
      GRUPOS.forEach((g) => {
        const bt = nav.querySelector(`[data-mg="${g.id}"]`); if (!bt) return;
        const membros = g.views.map(botao).filter(visivel);
        bt.hidden = !membros.length;
        if (membros.length) secOk[g.sec] = true;
        const soma = membros.reduce((s, b) => s + (parseInt(String(cont(b)).replace(/\D/g, ''), 10) || 0), 0);
        const ci = bt.querySelector('.mg-cnt'); ci.hidden = !soma; ci.textContent = soma.toLocaleString('pt-BR');
        bt.querySelector('.mg-novo').hidden = !!soma || !membros.some((b) => novo(b));
        const ativo = aberto ? aberto === g.id : !!(ativoView && g.views.includes(ativoView.view) && (!hub || hub.hidden));
        bt.classList.toggle('on', ativo);
      });
      nav.querySelectorAll('[data-mgsec]').forEach((s) => { s.hidden = !secOk[s.dataset.mgsec]; });
      if (aberto && hub && !hub.hidden) desenha(aberto);
    });
  }

  // ---------------------------------------------------------------- página do grupo
  function garanteHub() {
    if (hub) return hub;
    const ref = document.getElementById('view-fiscal-dash');
    hub = document.createElement('div');
    hub.className = 'view mg-hub';
    hub.id = 'view-grupo';
    hub.hidden = true;
    ref.parentNode.insertBefore(hub, ref);
    hub.addEventListener('click', (ev) => {
      const c = ev.target.closest('[data-abre]'); if (!c) return;
      if (c.dataset.abre === '__reset') { const r = document.getElementById('btnNovaAnalise'); if (r) r.click(); return; }
      const b = botao(c.dataset.abre); if (!b) return;
      aberto = '';
      b.click();
      atualiza();
    });
    return hub;
  }
  function desenha(id) {
    const g = GRUPOS.find((x) => x.id === id); if (!g) return;
    const membros = g.views.map((v) => [v, botao(v)]).filter(([, b]) => visivel(b));
    const reset = g.reset && visivel(document.getElementById('btnNovaAnalise'));
    const cards = membros.map(([v, b]) => {
      const n = cont(b), nv = novo(b), rs = resumo(b);
      const vermelho = n && ['fiscal-fisconforme', 'invertidas'].includes(v);
      const chip = n ? `<span class="mg-chip ${vermelho ? 'r' : 'a'}">${esc(n)}</span>` : nv ? `<span class="mg-chip n">${esc(nv)}</span>`
        : ADM_TESTE.has(v) ? '<span class="mg-chip z">teste</span>' : v === 'fiscal-rtc' ? '<span class="mg-chip o">REFORMA</span>' : '';
      const travado = b.classList.contains('locked-em-breve');
      return `<button class="mg-card${vermelho ? ' dest' : ''}${travado ? ' trav' : ''}" data-abre="${esc(v)}" title="${esc(textoDe(b))}">
        <span class="mg-top"><span class="mg-ico">${IMG.has(v) ? `<img src="img/menu/m-${v}.png" alt="">` : icone(b)}</span>${travado ? '<span class="mg-chip z">EM BREVE</span>' : chip}</span>
        <b>${nomeDe(b)}</b><small>${esc(DESC[v] || '')}</small>${rs ? `<span class="mg-rs">${esc(rs)}</span>` : ''}
        <span class="mg-ft">Abrir ›</span></button>`;
    }).join('') + (reset ? `<button class="mg-card" data-abre="__reset"><span class="mg-top"><span class="mg-ico"><img src="img/menu/m-nova.png" alt=""></span></span>
        <b>Nova análise</b><small>trocar o SPED importado</small><span class="mg-ft">Abrir ›</span></button>` : '');
    const html = `<div class="mg-bc">${g.sec === g.nome ? '' : `${esc(g.sec)} › `}${esc(g.nome)}</div><h1 class="mg-h1">${esc(g.nome)}</h1><p class="mg-sub">${esc(g.sub)}</p>
      <div class="mg-grid">${cards || '<div class="mg-vz">Nenhum módulo deste grupo está liberado para você.</div>'}</div>`;
    if (hub.dataset.html !== html) { hub.innerHTML = html; hub.dataset.html = html; }
  }
  function abrir(id) {
    garanteHub();
    if (window._manualSair) { try { window._manualSair(); } catch (_) {} }
    document.querySelectorAll('.view').forEach((v) => { v.hidden = true; });
    const vazio = document.getElementById('empty'); if (vazio) vazio.hidden = true;
    const stg = document.querySelector('.stage'); if (stg) stg.classList.remove('stage-cheia');
    document.body.dataset.areaContabil = '';
    const exp = document.getElementById('btnExport'); if (exp) exp.style.display = 'none';
    aberto = id;
    hub.dataset.html = '';
    desenha(id);
    hub.hidden = false;
    hub.classList.remove('mg-anim'); void hub.offsetWidth; hub.classList.add('mg-anim');
    atualiza();
  }

  // ---------------------------------------------------------------- liga / desliga
  function liga() {
    nav = document.querySelector('.nav'); if (!nav) return;
    ligado = true;
    document.body.classList.add('menu-grupos');
    montaLateral();
    if (!obs) {
      obs = new MutationObserver((muts) => {
        if (muts.some((m) => m.type === 'attributes' && m.attributeName === 'class' && m.target.classList && m.target.classList.contains('nav-item') && m.target.classList.contains('active'))) aberto = '';
        atualiza();
      });
      obs.observe(nav, { subtree: true, attributes: true, attributeFilter: ['class', 'hidden'], childList: true, characterData: true });
    }
    atualiza();
  }
  function desliga() {
    ligado = false;
    document.body.classList.remove('menu-grupos');
    if (hub && !hub.hidden) {
      hub.hidden = true;
      const a = document.querySelector('.nav .nav-item.active:not(.role-hidden)') || document.querySelector('.nav .nav-item:not(.role-hidden)');
      if (a) a.click();
    }
    aberto = '';
  }
  function linkModo() {
    const pe = document.querySelector('.side-foot'); if (!pe) return;
    let a = document.getElementById('menuModoLink');
    if (!a) {
      a = document.createElement('a'); a.id = 'menuModoLink'; a.className = 'cloud-link';
      pe.appendChild(document.createElement('br')); pe.appendChild(a);
      a.addEventListener('click', () => {
        const grupos = !modoGrupos();
        try { localStorage.setItem(CHAVE, grupos ? 'grupos' : 'classico'); } catch (_) {}
        if (grupos) liga(); else desliga();
        linkModo();
      });
    }
    a.textContent = modoGrupos() ? '☰ Menu clássico' : '☰ Menu agrupado';
    a.title = modoGrupos() ? 'Voltar ao menu com todos os módulos na lateral' : 'Menu com os módulos agrupados';
  }

  function inicia() {
    linkModo();
    if (modoGrupos()) liga();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', inicia); else inicia();
  window._menuGrupos = { abrir, atualiza };
})();

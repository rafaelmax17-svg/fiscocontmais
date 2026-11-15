// ✦ Análise ampla pelo POP — EFD ICMS/IPI (Corretor do SPED Fiscal · só Admin · EM TESTE)
// Só roda quando o Admin clica em "Analisar com IA". Os números vêm da conferência do sistema (python/analise_pop.py);
// a IA (função analisePop na nuvem) escreve a explicação de cada apontamento, o parecer e o Word de observação.
(function () {
  const $ = (s) => document.querySelector(s);
  const e = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const brl = (v) => (Number(v) || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  const num = (v) => (Number(v) || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const P = { res: null, sel: null, ant: null, antTxt: '', pop: null, mais: 0, aviso: '' };
  const ETAPAS = { 1: 'Etapa 1 · Coleta e escrituração', 2: 'Etapa 2 · Conferência', 3: 'Etapa 3 · Conferência do SPED gerado' };
  const SIMB = { ok: '✓', x: '✕', av: '!', in: 'i', na: '–' };
  const COLS = { nota: 'Nota', data: 'Data', forn: 'Fornecedor', prod: 'Produto', ncm: 'NCM', de: 'Está', para: 'Correto', obs: 'Observação',
    valor: 'Valor', rodape: 'Rodapé da DANFE', aliq: 'Alíquota', base: 'Base' };
  const ORDEM = { x: 0, av: 1, in: 2, ok: 3, na: 4 };

  function toastP(m, erro) { if (window.toast) window.toast(m, erro); }

  async function estadoPop() {
    const r = await window.fiscocont.pop.estado();
    if (r && r.error) { $('#popInfo').textContent = 'POP: sem acesso'; return; }
    P.pop = r.pop;
    $('#popInfo').innerHTML = P.pop ? `POP: <b>${e(P.pop.nome)}</b> (${P.pop.paginas} pág.)` : '<b style="color:#b45309">POP ainda não carregado</b>';
    $('#popTrocar').textContent = P.pop ? 'trocar o POP' : 'carregar o POP';
  }

  window._popEntrar = (adm) => {
    $('#corrPopCard').hidden = !adm;
    if (adm) estadoPop();
  };

  $('#popTrocar').addEventListener('click', async (ev) => {
    ev.preventDefault();
    const r = await window.fiscocont.pop.carregar();
    if (!r || r.canceled) return;
    if (r.error) { toastP(r.error, true); return; }
    toastP('POP carregado na nuvem (só o Admin acessa).');
    estadoPop();
  });
  $('#popAnt').addEventListener('click', async (ev) => {
    ev.preventDefault();
    const r = await window.fiscocont.pop.pickSpedAnt();
    if (!r || r.canceled) return;
    if (r.error) { toastP(r.error, true); return; }
    P.ant = r.path; P.antTxt = r.periodo;
    $('#popAntInfo').textContent = `✓ ${r.periodo}`;
  });
  window.fiscocont.pop.onProgresso((t) => { const o = $('#ovTxt'); if (o) o.textContent = t; });

  async function analisar() {
    const c = window._corrCtx ? window._corrCtx() : {};
    if (!c.sped) { toastP('Escolha o SPED Fiscal primeiro.', true); return; }
    if (!P.pop) { await estadoPop(); if (!P.pop) { toastP('Carregue o POP antes (link "carregar o POP").', true); return; } }
    if (!c.xmls && !(await c.pedirXmls())) { /* segue sem XML: os itens que dependem dele ficam como "faltou documento" */ }
    const x = window._corrCtx();
    c.soMostra('#corrPop');
    window.overlay && window.overlay(true, 'Conferindo o SPED item a item do POP…');
    const r = await window.fiscocont.pop.analisar({ spedPath: x.sped, usarCorrigido: x.feito, xmls: x.xmls, spedAnt: P.ant });
    window.overlay && window.overlay(false);
    if (r.error) { toastP(r.error, true); $('#corrPop').hidden = true; return; }
    P.res = r.res; P.aviso = r.avisoIa || '';
    const pri = (P.res.prioridades || []).find((n) => P.res.itens.some((i) => i.n === n && i.status === 'x'));
    P.sel = pri || (P.res.itens.find((i) => i.status === 'x') || P.res.itens[0] || {}).n;
    P.mais = 0;
    desenhar();
    $('#corrPop').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  $('#btnPopIA').addEventListener('click', analisar);

  function celula(k, v) {
    if (k === 'valor' || k === 'base') return `<td class="pop-n">${typeof v === 'number' ? num(v) : e(v)}</td>`;
    if (k === 'aliq') return `<td class="pop-n">${typeof v === 'number' ? num(v) + '%' : e(v)}</td>`;
    if (k === 'rodape') return `<td class="pop-q">${e(v)}</td>`;
    if (k === 'de') return `<td><s>${e(v)}</s></td>`;
    if (k === 'para') return `<td><b class="pop-ok">${e(v)}</b></td>`;
    if (k === 'nota') return `<td><b>${e(v)}</b></td>`;
    return `<td>${e(v)}</td>`;
  }

  function detalhe(i) {
    if (!i) return '';
    const lim = 60 + P.mais * 100;
    const lin = (i.linhas || []).slice(0, lim);
    const cols = (i.cols || []).filter((k) => lin.some((l) => l[k] !== undefined && l[k] !== ''));
    return `<div class="pop-dt"><span class="pop-it">POP · ${e(ETAPAS[i.etapa] || '')} · item ${e(i.n)}</span>
      <h2><span class="pop-s ${i.status}">${SIMB[i.status]}</span>${e(i.titulo)}</h2><p class="pop-rs">${e(i.resumo)}${i.valor && i.status === 'x' ? ` · <b>${brl(i.valor)}</b>` : ''}</p>
      ${i.ia ? `<div class="pop-ia"><b>✦ ANÁLISE</b>${e(i.ia)}</div>` : ''}
      ${lin.length ? `<div class="pop-tw"><table><thead><tr>${cols.map((k) => `<th${['valor', 'base', 'aliq'].includes(k) ? ' class="pop-n"' : ''}>${COLS[k] || k}</th>`).join('')}</tr></thead>
        <tbody>${lin.map((l) => `<tr>${cols.map((k) => celula(k, l[k])).join('')}</tr>`).join('')}</tbody></table></div>
        ${(i.total_linhas || 0) > lin.length ? `<a href="#" class="pop-mais" id="popMais">mostrar mais (${i.total_linhas - lin.length} restantes)</a>` : ''}` : ''}
      ${i.caminho ? `<div class="pop-cm"><b>Como fazer no Domínio (POP ${e(i.n)}):</b> ${e(i.caminho)}</div>` : ''}
      ${i.corretor ? '<div class="pop-bt"><button class="pop-b p" id="popCorr">Corrigir no SPED (Análise Inteligente)</button></div>' : ''}</div>`;
  }

  function desenhar() {
    const r = P.res, ct = r.contagem || {};
    const conf = r.itens.filter((i) => i.status !== 'na').length;
    const porEt = {};
    r.itens.forEach((i) => { (porEt[i.etapa] = porEt[i.etapa] || []).push(i); });
    const sel = r.itens.find((i) => i.n === P.sel);
    const c = window._corrCtx ? window._corrCtx() : {};
    $('#corrPop').innerHTML = `
      <div class="pop-hd"><div class="pop-ic sm" aria-hidden="true"><span class="pop-ic-r"></span><span class="pop-ic-c"><svg viewBox="0 0 32 32"><path d="M16 3.5l2.6 7.9 7.9 2.6-7.9 2.6L16 24.5l-2.6-7.9L5.5 14l7.9-2.6z" fill="#fff"/></svg></span></div>
        <div><h1>Análise ampla pelo POP — EFD ICMS/IPI <em>EM TESTE</em></h1><p>${e((r.cab || {}).nome)} · ${e(r.periodo)} · ${e(P.pop ? P.pop.nome : '')}</p></div>
        <span class="pop-sp"></span><button class="pop-b w" id="popWord">📝 Word de observação ao cliente</button><button class="pop-b" id="popDe">✦ Analisar de novo</button><button class="pop-b" id="popFechar">Fechar</button></div>
      <div class="pop-fs"><span class="${'ok'}">SPED · ${e(r.periodo)}</span><span class="${r.tem_xml ? 'ok' : 'no'}">XMLs · ${r.xml_lidos || 0} lido(s): ${r.n_ent_xml} de entrada · ${r.n_sai_xml} emitidos · ${r.n_cte_xml} CT-e</span>
        <span class="${(r.itens.find((i) => i.n === '1.28') || {}).status === 'av' ? 'no' : 'ok'}">DAREs pagos</span><span class="${(r.itens.find((i) => i.n === '1.15') || {}).status === 'av' ? 'no' : 'ok'}">Fisconforme</span>
        <span class="${r.tem_sped_ant ? 'ok' : 'no'}">SPED do mês anterior${P.antTxt ? ' · ' + e(P.antTxt) : ''}</span></div>
      ${P.aviso ? `<div class="pop-av">A conferência rodou, mas a parte da IA não respondeu: ${e(P.aviso)}. Os apontamentos abaixo são do sistema; clique em "Analisar de novo" para tentar a IA outra vez.</div>` : ''}
      <div class="pop-ks"><div style="--c:#4338ca"><span>Itens do POP conferidos</span><b>${conf}</b><i>os outros são telas do Domínio</i></div>
        <div style="--c:#16a34a"><span>Sem apontamento</span><b>${ct.ok || 0}</b><i>conferidos e corretos</i></div>
        <div style="--c:#dc2626"><span>Com apontamento</span><b>${ct.x || 0}</b><i>${(ct.in || 0)} para anotar</i></div>
        <div style="--c:#f59e0b"><span>Faltou documento</span><b>${ct.av || 0}</b><i>XML, SPED anterior, consultas</i></div>
        <div style="--c:#7c3aed"><span>Valor nos apontamentos</span><b>${brl(r.valor_total)}</b><i>soma dos itens com ✕</i></div></div>
      ${r.parecer ? `<div class="pop-par"><b>✦ PARECER</b>${e(r.parecer)}${(r.prioridades || []).length ? `<div class="pop-pri">Prioridade: ${r.prioridades.map((n) => `<a href="#" data-n="${e(n)}">${e(n)}</a>`).join('')}</div>` : ''}</div>` : ''}
      <div class="pop-g"><div class="pop-cl">${Object.keys(porEt).sort().map((et) => `<div class="pop-et">${e(ETAPAS[et] || 'Etapa ' + et)}</div>
        ${porEt[et].map((i) => `<a href="#" class="pop-li ${i.status}${i.n === P.sel ? ' on' : ''}" data-n="${e(i.n)}"><span class="pop-s ${i.status}">${SIMB[i.status]}</span>
          <div><span class="pop-nn">${e(i.n)}</span>${e(i.titulo)}<small>${e(i.resumo)}</small></div></a>`).join('')}`).join('')}</div>
        <div>${detalhe(sel)}</div></div>`;
    $('#corrPop').hidden = false;
    $('#corrPop').querySelectorAll('[data-n]').forEach((a) => a.addEventListener('click', (ev) => { ev.preventDefault(); P.sel = a.dataset.n; P.mais = 0; desenhar(); }));
    const m = $('#popMais'); if (m) m.addEventListener('click', (ev) => { ev.preventDefault(); P.mais++; desenhar(); });
    const cr = $('#popCorr'); if (cr) cr.addEventListener('click', () => c.abrirTudo && c.abrirTudo());
    $('#popDe').addEventListener('click', analisar);
    $('#popFechar').addEventListener('click', () => { $('#corrPop').hidden = true; });
    $('#popWord').addEventListener('click', async () => {
      const w = await window.fiscocont.pop.word(P.res);
      if (!w || w.canceled) return;
      if (w.error) toastP(w.error, true); else toastP('Word de observação salvo.');
    });
  }
})();

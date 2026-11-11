'use strict';
// Adaptação de planilhas — SÓ ADMIN. Escolhe a planilha de auditoria de itens, mostra o que o sistema encontrou e
// gera um NOVO Excel (Modelo B) ao lado do original. O original nunca é alterado.
(function () {
  const e = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const n = (x) => Number(x || 0).toLocaleString('pt-BR');
  const P = { arq: null, res: null, rodando: false };
  const GR = [
    ['st_indevido', '✖ Saiu como ST, mas o produto é tributado', '#b91c1c'],
    ['trib_indevido', '✖ Tributou produto que já tem ICMS-ST', '#c2410c'],
    ['isento_div', '✖ CST não combina com produto isento', '#a16207'],
    ['condicional', '◆ Depende da finalidade da venda', '#4338ca'],
    ['ok', '✔ Corretos', '#15803d'],
    ['entrada', 'Entradas (informativo)', '#64748b'],
    ['sem_legenda', 'Sem legenda', '#64748b'],
  ];

  function desenhar() {
    const raiz = $('#plRaiz');
    if (typeof ROLE === 'undefined' || ROLE !== 'admin') { raiz.innerHTML = '<div class="lic-empty">Acesso restrito ao Admin.</div>'; return; }
    const a = P.arq;
    const c = a ? a.contagem || {} : {};
    const prob = (c.st_indevido || 0) + (c.trib_indevido || 0) + (c.isento_div || 0);
    raiz.innerHTML = `
      <div class="pl-hero"><div><span class="pl-tag">MÓDULO ADMIN · ADAPTAÇÃO DE PLANILHAS</span><h1>Planilha profissional para a equipe</h1>
        <p>Escolha a planilha de auditoria de itens (colunas NF, DESCRICAO, NCM, CST, CFOP, LEGENDA e CONDICIONAL). O sistema confere se o CST de cada item combina com o tratamento do produto e devolve um <b>novo Excel</b>, fácil de ler: os problemas primeiro, cada grupo com a explicação, e os corretos recolhidos no fim. O arquivo original não é alterado.</p></div>
        <div class="pl-bt"><button class="p" id="plEsc">📂 Escolher planilha</button></div></div>
      ${a ? `<div class="fc-card pl-res">
        <div class="pl-arq"><b>${e(a.nome)}</b><small>${n(a.itens)} itens · ${n(a.notas)} notas · aba “${e(a.aba)}”</small></div>
        <div class="pl-gr">${GR.filter(([k]) => c[k]).map(([k, t, cor]) => `<div style="--c:${cor}"><span>${e(t)}</span><b>${n(c[k])}</b></div>`).join('')}</div>
        <div class="pl-msg ${prob ? 'ruim' : 'bom'}">${prob ? `<b>${n(prob)}</b> ${prob === 1 ? 'item com CST que não combina' : 'itens com CST que não combina'} com o tratamento do produto.` : 'Nenhum item com CST divergente.'}${c.condicional ? ` <b>${n(c.condicional)}</b> dependem da finalidade da venda.` : ''}</div>
        <label class="pl-lb">Título da planilha (aparece no topo)</label>
        <input id="plTit" class="pl-in" value="${e(a.tituloEd ?? a.titulo)}">
        <div class="pl-bt"><button class="p" id="plGerar"${P.rodando ? ' disabled' : ''}>${P.rodando ? 'Gerando…' : '✨ Gerar planilha profissional'}</button></div>
        ${P.res ? `<div class="pl-ok"><div><b>Planilha pronta</b><small>${e(P.res.saida)}</small></div><button class="p" data-ab="${e(P.res.saida)}">Abrir no Excel</button><button data-pa="${e(P.res.saida)}">Abrir pasta</button></div>` : ''}
      </div>` : '<div class="fc-card pl-vazio">Nenhuma planilha escolhida ainda.</div>'}`;
    $('#plEsc').onclick = escolher;
    const g = $('#plGerar'); if (g) g.onclick = gerar;
    const t = $('#plTit'); if (t) t.oninput = () => { P.arq.tituloEd = t.value; };
    document.querySelectorAll('#plRaiz [data-ab]').forEach((b) => b.onclick = async () => { const r = await window.fiscocont.plan.abrir(b.dataset.ab, false); if (r && r.error) toast(r.error, true); });
    document.querySelectorAll('#plRaiz [data-pa]').forEach((b) => b.onclick = async () => { const r = await window.fiscocont.plan.abrir(b.dataset.pa, true); if (r && r.error) toast(r.error, true); });
  }

  async function escolher() {
    const b = $('#plEsc'); b.disabled = true; b.textContent = 'Lendo a planilha…';
    const r = await window.fiscocont.plan.escolher();
    b.disabled = false;
    if (!r || r.cancelado) { desenhar(); return; }
    if (r.error) { toast(r.error, true); desenhar(); return; }
    P.arq = r; P.res = null;
    desenhar();
  }

  async function gerar() {
    if (!P.arq || P.rodando) return;
    P.rodando = true; desenhar();
    const r = await window.fiscocont.plan.gerar({ arquivo: P.arq.arquivo, titulo: (P.arq.tituloEd ?? P.arq.titulo) || '' });
    P.rodando = false;
    if (r && r.error) { toast(r.error, true); desenhar(); return; }
    P.res = r;
    toast('Planilha profissional gerada ao lado da original.');
    desenhar();
  }

  window._planEntrar = desenhar;
})();

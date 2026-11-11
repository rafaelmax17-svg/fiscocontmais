'use strict';
// Adaptação de planilhas — SÓ ADMIN. Escolhe uma ou várias planilhas de auditoria de itens (ou uma pasta), mostra o que
// o sistema encontrou em cada uma e gera um NOVO Excel (Modelo 4) ao lado de cada original: "<nome> - OK.xlsx".
// Os originais nunca são alterados.
(function () {
  const e = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const n = (x) => Number(x || 0).toLocaleString('pt-BR');
  const P = { lista: [], rodando: false, prog: null, feito: false };

  const validos = () => P.lista.filter((x) => !x.erro && x.marcado !== false);

  function desenhar() {
    const raiz = $('#plRaiz');
    if (typeof ROLE === 'undefined' || ROLE !== 'admin') { raiz.innerHTML = '<div class="lic-empty">Acesso restrito ao Admin.</div>'; return; }
    const ok = validos();
    const div = ok.reduce((s, x) => s + (x.divergentes || 0), 0);
    const itens = ok.reduce((s, x) => s + (x.itens || 0), 0);
    raiz.innerHTML = `
      <div class="pl-hero"><div><span class="pl-tag">MÓDULO ADMIN · ADAPTAÇÃO DE PLANILHAS</span><h1>Planilhas prontas para a equipe</h1>
        <p>Escolha uma ou várias planilhas de auditoria de itens (colunas NF, DESCRICAO, NCM, CST, CFOP, LEGENDA e CONDICIONAL), ou uma pasta inteira. Para cada uma, o sistema gera um <b>novo Excel</b> com a mesma planilha (mesmas colunas, mesma ordem e os mesmos dados) com acabamento profissional e a coluna <b>Conferência</b>, que aponta o CST divergente. O novo arquivo fica ao lado do original, com <b>“ - OK”</b> no nome. Os originais não são alterados.</p></div>
        <div class="pl-bt"><button class="p" id="plEsc"${P.rodando ? ' disabled' : ''}>📂 Escolher planilhas</button><button id="plPasta"${P.rodando ? ' disabled' : ''}>🗂 Escolher pasta</button></div></div>
      ${P.lista.length ? `<div class="fc-card pl-res">
        <div class="pl-top"><div><b>${P.lista.length} planilha${P.lista.length > 1 ? 's' : ''}</b><small>${ok.length} para gerar · ${n(itens)} itens · <span class="${div ? 'pl-r' : ''}">${n(div)} com CST divergente</span>${P.lista.length - P.lista.filter((x) => !x.erro).length ? ` · ${P.lista.filter((x) => x.erro).length} fora do formato` : ''}</small></div>
          ${P.feito ? '' : `<button class="p" id="plGerar"${P.rodando || !ok.length ? ' disabled' : ''}>${P.rodando ? 'Gerando…' : `✨ Gerar ${ok.length > 1 ? `as ${ok.length} planilhas` : 'a planilha'}`}</button>`}</div>
        ${P.rodando && P.prog ? `<div class="pl-prog"><i style="width:${P.prog.total ? (P.prog.feitas / P.prog.total * 100).toFixed(1) : 0}%"></i><span>Gerando ${P.prog.feitas} de ${P.prog.total}${P.prog.atual ? ` · ${e(P.prog.atual)}` : ''}…</span></div>` : ''}
        <table class="pl-t"><thead><tr><th></th><th>Planilha</th><th>Título (aparece no topo)</th><th>Itens</th><th>CST divergente</th><th>${P.feito ? 'Resultado' : ''}</th></tr></thead><tbody>
        ${P.lista.map((x, i) => `<tr class="${x.erro ? 'pl-x' : ''}">
          <td>${x.erro ? '' : `<input type="checkbox" data-mk="${i}"${x.marcado !== false ? ' checked' : ''}${P.rodando || P.feito ? ' disabled' : ''}>`}</td>
          <td><b>${e(x.nome)}</b>${x.erro ? '' : `<small>${n(x.notas)} notas · aba “${e(x.aba)}”</small>`}</td>
          <td>${x.erro ? `<span class="pl-er">Fora do formato · ${e(String(x.erro).replace(/^Formato não reconhecido:\s*/, ''))}</span>` : `<input class="pl-in" data-ti="${i}" value="${e(x.tituloEd ?? x.titulo)}"${P.rodando || P.feito ? ' disabled' : ''}>`}</td>
          <td>${x.erro ? '' : n(x.itens)}</td>
          <td>${x.erro ? '' : `<b class="${x.divergentes ? 'pl-r' : 'pl-g'}">${n(x.divergentes)}</b>`}</td>
          <td>${x.saida ? `<button class="p sm" data-ab="${e(x.saida)}">Abrir</button><button class="sm" data-pa="${e(x.saida)}">Pasta</button>` : x.erroGerar ? `<span class="pl-er">${e(x.erroGerar)}</span>` : ''}</td></tr>`).join('')}
        </tbody></table>
        ${P.feito ? `<div class="pl-ok"><div><b>${P.lista.filter((x) => x.saida).length} planilha${P.lista.filter((x) => x.saida).length === 1 ? ' pronta' : 's prontas'}</b><small>Cada uma foi salva ao lado da original, com “ - OK” no nome.</small></div><button id="plNovo">Adaptar outras</button></div>` : ''}
      </div>` : '<div class="fc-card pl-vazio">Nenhuma planilha escolhida ainda. Use <b>Escolher planilhas</b> (dá para marcar várias com Ctrl ou Shift) ou <b>Escolher pasta</b>.</div>'}`;
    $('#plEsc').onclick = () => escolher('escolher');
    $('#plPasta').onclick = () => escolher('pasta');
    const g = $('#plGerar'); if (g) g.onclick = gerar;
    const nv = $('#plNovo'); if (nv) nv.onclick = () => { P.lista = []; P.feito = false; desenhar(); };
    const q = (s) => document.querySelectorAll('#plRaiz ' + s);
    q('[data-ti]').forEach((t) => t.oninput = () => { P.lista[+t.dataset.ti].tituloEd = t.value; });
    q('[data-mk]').forEach((c) => c.onchange = () => { P.lista[+c.dataset.mk].marcado = c.checked; desenhar(); });
    q('[data-ab]').forEach((b) => b.onclick = async () => { const r = await window.fiscocont.plan.abrir(b.dataset.ab, false); if (r && r.error) toast(r.error, true); });
    q('[data-pa]').forEach((b) => b.onclick = async () => { const r = await window.fiscocont.plan.abrir(b.dataset.pa, true); if (r && r.error) toast(r.error, true); });
  }

  async function escolher(modo) {
    const b = $(modo === 'pasta' ? '#plPasta' : '#plEsc'); b.disabled = true; b.textContent = 'Lendo…';
    const r = await window.fiscocont.plan[modo]();
    if (!r || r.cancelado) { desenhar(); return; }
    if (r.error) { toast(r.error, true); desenhar(); return; }
    P.lista = r.itens || []; P.feito = false;
    const fora = P.lista.filter((x) => x.erro).length;
    if (fora) toast(`${fora} planilha(s) fora do formato da auditoria ficaram de fora.`, true);
    desenhar();
  }

  async function gerar() {
    const ok = validos();
    if (!ok.length || P.rodando) return;
    P.rodando = true; P.prog = { feitas: 0, total: ok.length };
    window.fiscocont.plan.onProgresso((p) => { P.prog = p; if (P.rodando) desenhar(); });
    desenhar();
    const r = await window.fiscocont.plan.gerar({ itens: ok.map((x) => ({ arquivo: x.arquivo, titulo: (x.tituloEd ?? x.titulo) || '' })) });
    P.rodando = false;
    if (r && r.error) { toast(r.error, true); desenhar(); return; }
    for (const g of r.itens || []) {
      const x = P.lista.find((y) => y.arquivo === g.arquivo);
      if (!x) continue;
      if (g.erro) x.erroGerar = g.erro; else x.saida = g.saida;
    }
    P.feito = true;
    const feitas = (r.itens || []).filter((g) => !g.erro).length;
    toast(`${feitas} planilha(s) gerada(s) ao lado das originais.`);
    desenhar();
  }

  window._planEntrar = desenhar;
})();

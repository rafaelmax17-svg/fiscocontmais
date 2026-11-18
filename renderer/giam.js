'use strict';
// Recibos GIAM/SPED Fiscal (SEFIN-RO): o recibo de processamento de cada inscrição na competência, salvo na pasta do
// cliente (Relatórios › AAAA › MM). Sem recibo: "Não processado". Simples Nacional sem recibo fica fora da conferência.
// O sistema verifica sozinho 1x por dia útil às 08:00 (um computador com o e-CPF do contador) ou no botão.
(function () {
  const e = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const compBr = (c) => (c ? `${c.slice(5, 7)}/${c.slice(0, 4)}` : '');
  const ieFmt = (ie) => String(ie || '').replace(/\D/g, '').padStart(14, '0');
  const curta = (s) => { const d = new Date(s); if (isNaN(d)) return s || ''; return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };
  const ST = { processado: ['ok', 'Processado'], nao_processado: ['er', 'Não processado'], simples: ['nm', 'Simples Nacional · sem recibo'], erro: ['ab', 'Erro na verificação'] };
  const G = { comp: '', d: null, ie: '', prog: null, anim: true };
  let ligado = false;
  const raiz = () => document.getElementById('gmRaiz');

  async function entrar() {
    if (!ligado) {
      ligado = true;
      window.fiscocont.giam.onProgresso((p) => { G.prog = p.fim ? null : p; const el = document.getElementById('gmProg'); if (el) { el.hidden = !G.prog; el.querySelector('span').textContent = (p && p.txt) || ''; if (p && p.n) el.querySelector('i').style.width = `${Math.round((p.i || 0) / p.n * 100)}%`; }
        const b = document.getElementById('gmLer'); if (b) b.disabled = !!G.prog; if (p.fim) carregar(true); });
      let t = null; window.fiscocont.giam.onEmpresa(() => { clearTimeout(t); t = setTimeout(() => carregar(true), 1500); });
    }
    if (!G.d) raiz().innerHTML = '<div class="lic-empty">Carregando os recibos da GIAM/SPED…</div>';
    await carregar();
  }
  async function carregar(quieto) {
    const d = await window.fiscocont.giam.dados(G.comp || null);
    if (d && d.error) { raiz().innerHTML = `<div class="lic-empty">${e(d.error)}</div>`; return; }
    G.d = d; G.comp = d.comp; G.anim = !quieto;
    if (d.rodando && !G.prog) G.prog = { txt: 'Verificação em andamento…' };
    desenhar(); menu();
  }
  function meses() { const out = []; const d = new Date(); for (let i = 1; i <= 14; i++) { const x = new Date(d.getFullYear(), d.getMonth() - i, 1); out.push(`${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}`); } return out; }
  function desenhar() {
    const todas = (G.d.emps || []).slice().sort((a, b) => (a.status === b.status ? a.nome.localeCompare(b.nome, 'pt-BR') : ['nao_processado', 'erro', 'processado', 'simples'].indexOf(a.status) - ['nao_processado', 'erro', 'processado', 'simples'].indexOf(b.status)));
    const emps = G.ie ? todas.filter((x) => x.ie === G.ie) : todas;
    const n = (s) => todas.filter((x) => x.status === s).length;
    const conf = todas.filter((x) => x.status !== 'simples').length;
    const ret = todas.filter((x) => x.retificadora).length;
    const m = G.d.meta || {};
    const pct = (v, t) => `${t ? Math.round(v / t * 100) : 0}%`;
    raiz().innerHTML = `
      <div class="rf-hero"><div>
        <h1>Recibos GIAM/SPED Fiscal</h1>
        <div class="rf-s">SEFIN-RO · Portal do Contribuinte · competência ${compBr(G.comp)} · ${m.ultimaLeitura ? `verificado em ${curta(m.ultimaLeitura)}${m.por ? ` (${e(m.por)})` : ''}` : 'ainda não verificado'}${G.d.proxima ? ` · próxima verificação automática ${curta(G.d.proxima)}` : ''}</div>
        <div class="rf-big"><div><small>Recibos de processamento</small><b>${n('processado')} / ${conf}</b></div>
          <div class="rf-mini"><div><b>${n('processado')}</b><small>processados</small></div><div><b>${n('nao_processado')}</b><small>não processados</small></div><div><b>${ret}</b><small>retificadora(s)</small></div><div><b>${n('simples')}</b><small>Simples (fora)</small></div></div></div>
        <div class="rf-prog" id="gmProg" ${G.prog ? '' : 'hidden'}><i></i><span>${e((G.prog || {}).txt || '')}</span></div>
      </div><div class="rf-ctl"><div><select class="rf-pill rf-sel" id="gmComp">${meses().map((c) => `<option value="${c}" ${c === G.comp ? 'selected' : ''}>Competência ${compBr(c)}</option>`).join('')}</select>
        <select class="rf-pill rf-sel" id="gmEmp"><option value="">🔍 Empresa: Todas</option>${todas.map((x) => `<option value="${e(x.ie)}" ${x.ie === G.ie ? 'selected' : ''}>${e(x.nome)}</option>`).join('')}</select></div>
        <div><button class="rf-pill g" id="gmLer" ${G.prog ? 'disabled' : ''}>${G.ie ? 'Verificar esta empresa' : 'Verificar recibos agora'}</button></div></div></div>
      <div class="rf-kp">
        <div class="rf-k" style="--c:#16a34a"><div class="ic">✓</div><small>Processados</small><b>${n('processado')}</b><div class="bar"><i style="--w:${pct(n('processado'), conf)}"></i></div><span>recibo salvo na pasta do cliente</span></div>
        <div class="rf-k" style="--c:#dc2626"><div class="ic">!</div><small>Não processados</small><b>${n('nao_processado')}</b><div class="bar"><i style="--w:${pct(n('nao_processado'), conf)}"></i></div><span>a SEFIN não tem recibo da competência</span></div>
        <div class="rf-k" style="--c:#7c3aed"><div class="ic">↻</div><small>Retificadoras</small><b>${ret}</b><div class="bar"><i style="--w:${pct(ret, conf)}"></i></div><span>recibo da última entrega</span></div>
        <div class="rf-k" style="--c:#64748b"><div class="ic">SN</div><small>Simples Nacional</small><b>${n('simples')}</b><div class="bar"><i style="--w:${pct(n('simples'), todas.length)}"></i></div><span>sem recibo · fora da conferência</span></div></div>
      <div class="rf-card rf-tab"><h3>Empresas · recibo de processamento da GIAM/SPED <small>${emps.length ? 'clique em "Abrir recibo" para ver o PDF salvo' : ''}</small></h3>
        ${emps.length ? `<table><thead><tr><th>Empresa</th><th>Inscrição estadual</th><th>Regime</th><th>Situação</th><th>Entrega</th><th>Retificadora</th><th>Recibo</th></tr></thead><tbody>
        ${emps.map((x) => `<tr><td><b>${e(x.nome)}</b></td><td>${e(ieFmt(x.ie))}</td><td>${e(x.regime || '—')}</td><td><span class="rf-chip ${(ST[x.status] || ST.erro)[0]}">● ${e((ST[x.status] || ST.erro)[1])}</span></td>
          <td>${e(x.entrega || '—')}</td><td>${x.status === 'processado' ? (x.retificadora ? 'SIM' : 'NÃO') : '—'}</td>
          <td>${x.status === 'processado' ? `<button class="gm-ab" data-arq="${e(x.arquivo)}">📄 Abrir recibo</button><small title="${e(x.arquivo)}">${x.cliente ? 'pasta do cliente · Relatórios' : 'pasta da empresa não encontrada · Notas Automáticas'}</small>`
            : x.status === 'nao_processado' ? '<span class="gm-np">a SEFIN não tem recibo desta competência</span>' : x.status === 'erro' ? `<span class="gm-np">${e(x.erro || 'erro')}</span>` : '—'}</td></tr>`).join('')}</tbody></table>`
          : `<div class="rf-vz">${m.ultimaLeitura ? 'Nenhuma inscrição na lista.' : 'Clique em "Verificar recibos agora" — o sistema também verifica sozinho todo dia útil às 8h.'}</div>`}</div>`;
    ligar(); animar();
  }
  function animar() {
    const bars = raiz().querySelectorAll('.bar i');
    if (!G.anim) { bars.forEach((i) => { i.style.width = i.style.getPropertyValue('--w'); }); return; }
    G.anim = false;
    bars.forEach((i) => { i.style.width = '0'; requestAnimationFrame(() => requestAnimationFrame(() => { i.style.width = i.style.getPropertyValue('--w'); })); });
    raiz().querySelectorAll('.rf-big>div>b, .rf-k b').forEach((b) => { const m = b.textContent.match(/^(\d+)(.*)$/); if (!m) return; const alvo = +m[1], resto = m[2], t0 = performance.now();
      const p = (now) => { const k = Math.min(1, (now - t0) / 900); b.textContent = `${Math.round(alvo * (1 - Math.pow(1 - k, 3)))}${resto}`; if (k < 1) requestAnimationFrame(p); }; requestAnimationFrame(p); });
  }
  function ligar() {
    document.getElementById('gmComp').onchange = (ev) => { G.comp = ev.target.value; G.ie = ''; carregar(); };
    document.getElementById('gmEmp').onchange = (ev) => { G.ie = ev.target.value; G.anim = true; desenhar(); };
    document.getElementById('gmLer').onclick = async () => {
      G.prog = { txt: 'Iniciando a verificação…' }; desenhar();
      const r = await window.fiscocont.giam.ler({ comp: G.comp, ie: G.ie || undefined });
      G.prog = null;
      if (r && r.error) toast(r.error, true);
      else if (r) toast(`Recibos verificados: ${r.processado || 0} processado(s), ${r.nao_processado || 0} não processado(s)${r.erro ? `, ${r.erro} com erro` : ''}.`);
      carregar();
    };
    raiz().querySelectorAll('[data-arq]').forEach((b) => b.addEventListener('click', async () => { const x = await window.fiscocont.giam.abrir({ caminho: b.dataset.arq }); if (x && x.error) toast(x.error, true); }));
  }
  function menu() {
    const s = document.getElementById('giamResumo'), c = document.getElementById('giamCnt');
    if (!s || !G.d) return;
    const np = (G.d.emps || []).filter((x) => x.status === 'nao_processado').length;
    s.textContent = !(G.d.emps || []).length ? `Recibo ${compBr(G.comp)}` : np ? `${np} não processado(s) · ${compBr(G.comp)}` : `todos processados · ${compBr(G.comp)}`;
    if (c) { c.hidden = !np; c.textContent = np; }
  }
  window._giamEntrar = entrar;
  setTimeout(async () => { try { if (window.fiscocont.giam && document.querySelector('[data-view="fiscal-giam"]:not(.role-hidden)')) { const d = await window.fiscocont.giam.dados(null); if (d && !d.error) { G.d = d; G.comp = d.comp; menu(); } } } catch (_) {} }, 9000);
})();

'use strict';
// Simples Nacional · Fechamento da equipe — planilha editável em tempo real (Firestore), com anéis de progresso
// por analista e exportação em HTML. Usa os utilitários do app.js ($, toast, ROLE).
(function () {
  const MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
  const INICIO = '2026-09';                       // primeira competência controlada no sistema (planilha da equipe)
  const COR_FIXA = { 'heloisa': '#7c3aed', 'hemily': '#0ea5e9', 'thawani': '#14b8a6', 'cauane': '#f59e0b', 'hotoniel': '#0ea472', 'valéria': '#e23d4c', 'valeria': '#e23d4c' };
  const PALETA = ['#6366f1', '#ec4899', '#84cc16', '#06b6d4', '#f97316', '#8b5cf6', '#10b981', '#ef4444'];
  const ST = {
    concluida: { rot: 'Concluída', cor: '#0ea472' },
    transmitida: { rot: 'PGDAS transmitido', cor: '#4f46e5' },
    escriturada: { rot: 'Escriturada, falta transmitir', cor: '#f59e0b' },
    alerta: { rot: 'Inconsistente', cor: '#b42318' },
    pendente: { rot: 'Pendente', cor: '#e23d4c' },
  };
  const FS = { comp: '', linhas: [], admin: false, analista: '', busca: '', chip: 'todas', iniciado: false, aberto: false, anel: null, kpiAnt: {} };

  const e = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const ok = (v) => v === 'Sim' || v === 'N/A';
  function status(r) {
    if (ok(r.esc) && ok(r.pgdas) && ok(r.das)) return 'concluida';
    if (r.pgdas === 'Sim' && !ok(r.esc)) return 'alerta';
    if (ok(r.pgdas)) return 'transmitida';
    if (ok(r.esc)) return 'escriturada';
    return 'pendente';
  }
  const feito = (st) => st === 'transmitida' || st === 'concluida';
  function corAnalista(nome, idx) { return COR_FIXA[String(nome || '').trim().toLowerCase()] || PALETA[idx % PALETA.length]; }
  function iniciais(n) { const p = String(n || '?').trim().split(/\s+/); return (p[0][0] + (p[1] ? p[1][0] : (p[0][1] || ''))).toUpperCase(); }
  function compRot(c) { const [a, m] = c.split('-'); return `${MESES[+m - 1]}/${a}`; }
  function compAnterior() { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; }
  function listaComps() {
    const d = new Date(); const fim = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    const out = []; let [a, m] = INICIO.split('-').map(Number);
    for (;;) { const c = `${a}-${String(m).padStart(2, '0')}`; out.push(c); if (c >= fim) break; m++; if (m > 12) { m = 1; a++; } }
    return out.reverse();
  }
  function prazo(c) {                                   // PGDAS-D e DAS: dia 20 do mês seguinte (LC 123/2006, art. 21, III)
    let [a, m] = c.split('-').map(Number); m++; if (m > 12) { m = 1; a++; }
    return new Date(a, m - 1, 20, 23, 59, 59);
  }
  const fmtData = (d) => `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;

  // ------------------------------------------------------------------ números
  function resumo(linhas) {
    const tot = { n: linhas.length, concluida: 0, transmitida: 0, escriturada: 0, alerta: 0, pendente: 0, semMov: 0 };
    const por = new Map();
    for (const r of linhas) {
      const st = status(r); tot[st]++; if (r.semMovimento) tot.semMov++;
      const k = r.analista || '(sem analista)';
      if (!por.has(k)) por.set(k, { nome: k, n: 0, feitas: 0, concluida: 0, transmitida: 0, escriturada: 0, alerta: 0, pendente: 0 });
      const a = por.get(k); a.n++; a[st]++; if (feito(st)) a.feitas++;
    }
    tot.feitas = tot.transmitida + tot.concluida;
    const nomes = [...por.keys()].sort((x, y) => x.localeCompare(y));
    const analistas = [...por.values()].sort((x, y) => y.n - x.n || x.nome.localeCompare(y.nome))
      .map((a) => ({ ...a, cor: corAnalista(a.nome, nomes.indexOf(a.nome)), pct: a.n ? Math.round(a.feitas / a.n * 100) : 0 }));
    const usadas = new Set();                       // iniciais sem repetir (Heloisa e Hemily não podem ser "HE" as duas)
    for (const a of analistas) {
      let ini = iniciais(a.nome);
      if (usadas.has(ini)) {
        const letras = String(a.nome).toUpperCase().normalize('NFD').replace(/[^A-Z]/g, '');
        ini = [...letras.slice(1)].map((c) => letras[0] + c).find((x) => !usadas.has(x)) || ini;
      }
      usadas.add(ini); a.ini = ini;
    }
    return { tot, analistas };
  }

  // ------------------------------------------------------------------ esqueleto da tela
  function montar() {
    const box = $('#fechSN');
    const comps = listaComps();
    if (!FS.comp) FS.comp = comps.includes(compAnterior()) ? compAnterior() : comps[comps.length - 1];
    box.innerHTML = `
      <div class="fs-head">
        <div><h2>Fechamento do Simples Nacional</h2><div class="fs-sub" id="fsSub"></div></div>
        <span class="fs-live" id="fsLive"><i></i>ao vivo</span>
      </div>
      <div class="fs-kpis" id="fsKpis"></div>
      <div class="fs-alert" id="fsAlert" hidden></div>
      <div class="fs-card fs-rings-card"><div class="fs-card-h"><b>Por analista · % com PGDAS transmitido</b><small id="fsRingsSub"></small></div>
        <div class="fs-rings"><svg id="fsRings" viewBox="0 0 300 300" width="300" height="300"></svg><div class="fs-rleg" id="fsRLeg"></div></div></div>
      <div class="fs-bar">
        <select id="fsComp" class="fs-in">${comps.map((c) => `<option value="${c}" ${c === FS.comp ? 'selected' : ''}>${compRot(c)}</option>`).join('')}</select>
        <select id="fsAn" class="fs-in"><option value="">Todas as analistas</option></select>
        <input id="fsBusca" class="fs-in fs-busca" placeholder="Buscar empresa…">
        <div class="fs-chips" id="fsChips"></div>
        <span style="flex:1"></span>
        <button class="act inv-export" id="fsHtml">Exportar HTML</button>
        <button class="act inv-export fs-prim" id="fsNova" hidden>+ Cadastrar empresa</button>
      </div>
      <div class="fs-card fs-tab-wrap"><table class="fs-tab"><thead><tr>
        <th>#</th><th class="l">Empresa</th><th class="l">Analista responsável</th><th>Escrituração concluída</th><th>PGDAS transmitido</th>
        <th>DAS/DARE enviado ao cliente</th><th>Data finalização</th><th class="l">Observações</th><th class="fs-adm-col" hidden></th></tr></thead>
        <tbody id="fsBody"></tbody></table>
        <div class="fs-foot" id="fsFoot"></div></div>
      <div class="fs-modal" id="fsModal" hidden><div class="fs-mbox" id="fsMBox"></div></div>`;
    $('#fsComp').addEventListener('change', (ev) => { FS.comp = ev.target.value; abrir(); });
    $('#fsAn').addEventListener('change', (ev) => { FS.analista = ev.target.value; desenhaTabela(true); });
    $('#fsBusca').addEventListener('input', (ev) => { FS.busca = ev.target.value; desenhaTabela(true); });
    $('#fsHtml').addEventListener('click', exportar);
    $('#fsNova').addEventListener('click', () => modalEmpresa());
    $('#fsBody').addEventListener('change', onCelula);
    $('#fsBody').addEventListener('click', onAcao);
    $('#fsModal').addEventListener('click', (ev) => { if (ev.target.id === 'fsModal') fechaModal(); });
  }

  async function abrir() {
    FS.linhas = []; FS.anel = null; FS.kpiAnt = {};
    $('#fsRings').innerHTML = ''; $('#fsRLeg').innerHTML = ''; $('#fsBody').innerHTML = '';
    $('#fsFoot').textContent = 'Carregando…';
    const r = await window.fiscocont.fechamento.abrir(FS.comp);
    if (r && r.error) { $('#fsFoot').textContent = r.error; toast(r.error, true); }
  }

  function aoMudar(d) {
    if (!d || d.comp !== FS.comp) return;
    FS.linhas = d.linhas || []; FS.admin = !!d.admin;
    const live = $('#fsLive'); if (live) { live.classList.remove('pulse'); void live.offsetWidth; live.classList.add('pulse'); }
    desenhaTudo();
  }

  // ------------------------------------------------------------------ desenho
  function desenhaTudo() {
    const { tot, analistas } = resumo(FS.linhas);
    const pz = prazo(FS.comp), venc = Date.now() > pz.getTime(), falta = tot.n - tot.feitas;
    $('#fsSub').innerHTML = `Competência <b>${compRot(FS.comp)}</b> · prazo do PGDAS-D e do DAS: <b class="${venc && falta ? 'neg' : ''}">${fmtData(pz)}</b>${venc && falta ? ' · <span class="neg">vencido</span>' : ''}`;
    const k = [
      ['n', 'Empresas', tot.n, '', ''],
      ['f', 'PGDAS transmitido', tot.feitas, '#4f46e5', tot.n ? ` · ${Math.round(tot.feitas / tot.n * 100)}%` : ''],
      ['e', 'Falta transmitir', tot.escriturada, '#f59e0b', ''],
      ['p', 'Pendentes', tot.pendente, '#e23d4c', ''],
      ['a', 'Inconsistentes', tot.alerta, '#b42318', ''],
      ['c', 'Concluídas (DAS enviado)', tot.concluida, '#0ea472', ''],
    ];
    $('#fsKpis').innerHTML = k.map(([id, rot, v, cor, extra]) => `<div class="fs-kpi"><small>${rot}</small><b style="color:${cor || 'var(--ink)'}"><span data-k="${id}">${FS.kpiAnt[id] ?? 0}</span><em>${extra}</em></b></div>`).join('');
    k.forEach(([id, , v]) => conta($(`[data-k="${id}"]`), FS.kpiAnt[id] ?? 0, v));
    k.forEach(([id, , v]) => { FS.kpiAnt[id] = v; });
    const al = FS.linhas.filter((r) => status(r) === 'alerta');
    const avisos = [];
    if (al.length) avisos.push(`<b>${al.length} inconsistência(s):</b> PGDAS transmitido sem a escrituração concluída — ${al.slice(0, 3).map((r) => e(r.nome)).join(', ')}${al.length > 3 ? '…' : ''}.`);
    if (venc && falta) avisos.push(`<b>Prazo vencido:</b> ${falta} empresa(s) ainda sem PGDAS transmitido.`);
    $('#fsAlert').hidden = !avisos.length; $('#fsAlert').innerHTML = avisos.join(' ');
    desenhaAneis(tot, analistas);
    const sel = $('#fsAn'), atual = FS.analista;
    sel.innerHTML = '<option value="">Todas as analistas</option>' + analistas.map((a) => `<option ${a.nome === atual ? 'selected' : ''}>${e(a.nome)}</option>`).join('');
    const chips = [['todas', 'Todas', tot.n], ['pendente', 'Pendentes', tot.pendente + tot.escriturada], ['alerta', 'Inconsistentes', tot.alerta],
      ['semmov', 'Sem movimento', tot.semMov], ['concluida', 'Concluídas', tot.concluida]];
    $('#fsChips').innerHTML = chips.map(([id, rot, n]) => `<button class="fs-chip ${FS.chip === id ? 'on' : ''}" data-chip="${id}">${rot} <b>${n}</b></button>`).join('');
    $('#fsChips').querySelectorAll('.fs-chip').forEach((b) => b.addEventListener('click', () => { FS.chip = b.dataset.chip; desenhaTudo(); }));
    $('#fsNova').hidden = !FS.admin;
    document.querySelectorAll('.fs-adm-col').forEach((x) => { x.hidden = !FS.admin; });
    desenhaTabela(false);
  }

  function conta(el, de, ate) {
    if (!el) return;
    const t0 = performance.now(), dur = 900;
    const passo = (t) => { const p = Math.min(1, (t - t0) / dur), f = 1 - Math.pow(1 - p, 3); el.textContent = Math.round(de + (ate - de) * f); if (p < 1) requestAnimationFrame(passo); };
    requestAnimationFrame(passo);
  }

  // Anéis de progresso: um por analista, de fora para dentro. Na primeira vez enchem do zero; depois, só avançam.
  function desenhaAneis(tot, analistas) {
    const svg = $('#fsRings'), leg = $('#fsRLeg');
    const n = analistas.length, passo = n > 1 ? Math.min(16, (138 - 58) / (n - 1)) : 16, larg = Math.max(6, passo - 4);
    const chave = analistas.map((a) => a.nome).join('|');
    const novo = !FS.anel || FS.anel.chave !== chave;
    if (novo) {
      svg.innerHTML = analistas.map((a, i) => {
        const r = 138 - i * passo, L = 2 * Math.PI * r;
        return `<circle cx="150" cy="150" r="${r}" fill="none" stroke="${a.cor}" stroke-opacity=".14" stroke-width="${larg}"/>
          <circle class="fs-ring" data-i="${i}" cx="150" cy="150" r="${r}" fill="none" stroke="${a.cor}" stroke-width="${larg}" stroke-linecap="round"
            stroke-dasharray="0 ${L.toFixed(1)}" transform="rotate(-90 150 150)" style="transition-delay:${(i * 0.12).toFixed(2)}s"><title>${e(a.nome)}</title></circle>`;
      }).join('') + '<text id="fsRTot" x="150" y="148" text-anchor="middle" class="fs-rtot">0%</text><text x="150" y="171" text-anchor="middle" class="fs-rtot-s">equipe</text>';
      FS.anel = { chave, pct: analistas.map(() => 0), tot: 0 };
    }
    const pctTot = tot.n ? Math.round(tot.feitas / tot.n * 100) : 0;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      svg.querySelectorAll('.fs-ring').forEach((c) => {
        const a = analistas[+c.dataset.i], L = 2 * Math.PI * +c.getAttribute('r');
        c.setAttribute('stroke-dasharray', `${(L * (a.n ? a.feitas / a.n : 0)).toFixed(1)} ${L.toFixed(1)}`);
      });
    }));
    const tEl = $('#fsRTot'); const de = FS.anel.tot;
    const t0 = performance.now(); const anima = (t) => { const p = Math.min(1, (t - t0) / 1500), f = 1 - Math.pow(1 - p, 3); tEl.textContent = Math.round(de + (pctTot - de) * f) + '%'; if (p < 1) requestAnimationFrame(anima); };
    requestAnimationFrame(anima);
    leg.innerHTML = analistas.map((a, i) => `<div class="fs-rl ${novo ? 'in' : 'on'}" style="animation-delay:${(0.25 + i * 0.1).toFixed(2)}s">
      <span class="fs-av" style="background:${a.cor}">${e(a.ini)}</span><b class="fs-rn">${e(a.nome)}</b>
      <span class="fs-rp" style="color:${a.cor}" data-rp="${i}">${FS.anel.pct[i] || 0}%</span>
      <small>${a.feitas}/${a.n} transmitidas${a.pendente + a.escriturada ? ` · ${a.pendente + a.escriturada} faltam` : ''}${a.alerta ? ` · <span class="neg">${a.alerta} ⚠</span>` : ''}</small></div>`).join('');
    analistas.forEach((a, i) => { const el = leg.querySelector(`[data-rp="${i}"]`); const de2 = FS.anel.pct[i] || 0; const t1 = performance.now();
      const an = (t) => { const p = Math.min(1, (t - t1) / 1500), f = 1 - Math.pow(1 - p, 3); el.textContent = Math.round(de2 + (a.pct - de2) * f) + '%'; if (p < 1) requestAnimationFrame(an); }; requestAnimationFrame(an); });
    FS.anel.pct = analistas.map((a) => a.pct); FS.anel.tot = pctTot;
    $('#fsRingsSub').textContent = `${tot.feitas} de ${tot.n} empresas`;
  }

  function filtradas() {
    const b = FS.busca.trim().toUpperCase();
    return FS.linhas.filter((r) => {
      if (FS.analista && r.analista !== FS.analista) return false;
      if (b && !r.nome.toUpperCase().includes(b) && !(r.cnpj || '').includes(b.replace(/\D/g, '') || '~')) return false;
      const st = status(r);
      if (FS.chip === 'pendente') return st === 'pendente' || st === 'escriturada';
      if (FS.chip === 'alerta') return st === 'alerta';
      if (FS.chip === 'semmov') return r.semMovimento;
      if (FS.chip === 'concluida') return st === 'concluida';
      return true;
    });
  }

  const selEtapa = (r, campo) => {
    const v = r[campo] || '';
    const cls = v === 'Sim' ? 'v-sim' : v === 'Não' ? 'v-nao' : v === 'N/A' ? 'v-na' : 'v-vz';
    return `<select class="fs-sel ${cls}" data-c="${campo}" data-id="${r.id}">${['', 'Sim', 'Não', 'N/A'].map((o) => `<option value="${o}" ${o === v ? 'selected' : ''}>${o || '—'}</option>`).join('')}</select>`;
  };
  function linhaHtml(r, i) {
    const st = status(r);
    return `<td class="fs-n">${i + 1}</td>
      <td class="l"><span class="fs-dot" style="background:${ST[st].cor}" title="${ST[st].rot}"></span><b>${e(r.nome)}</b>${r.semMovimento ? '<span class="fs-tag">sem movimento</span>' : ''}${r.cnpj ? `<small>${e(r.cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5'))}</small>` : ''}</td>
      <td class="l">${e(r.analista || '—')}</td>
      <td>${selEtapa(r, 'esc')}</td><td>${selEtapa(r, 'pgdas')}</td><td>${selEtapa(r, 'das')}</td>
      <td class="fs-fin" title="Preenchida sozinha quando as três etapas ficam Sim ou N/A">${r.fin ? e(r.fin) : '—'}</td>
      <td class="l"><input class="fs-obs" data-c="obs" data-id="${r.id}" value="${e(r.obs)}" placeholder="—">${st === 'alerta' ? '<small class="neg">⚠ PGDAS transmitido sem escrituração concluída</small>' : ''}</td>
      <td class="fs-adm-col" ${FS.admin ? '' : 'hidden'}><button class="fs-ic" data-a="editar" data-id="${r.id}" title="Alterar nome ou analista">✎</button><button class="fs-ic del" data-a="excluir" data-id="${r.id}" title="Excluir da lista a partir desta competência">🗑</button></td>`;
  }
  function desenhaTabela(forcar) {
    const body = $('#fsBody'); if (!body) return;
    const lst = filtradas();
    const foco = document.activeElement && body.contains(document.activeElement) ? document.activeElement.dataset.id : null;
    const existentes = new Map([...body.children].map((tr) => [tr.dataset.id, tr]));
    const ordem = lst.map((r) => r.id).join('|');
    if (forcar || body.dataset.ordem !== ordem) {
      body.innerHTML = lst.map((r, i) => `<tr data-id="${r.id}" data-sig="${sig(r, i)}">${linhaHtml(r, i)}</tr>`).join('');
      body.dataset.ordem = ordem;
    } else {
      lst.forEach((r, i) => {
        const tr = existentes.get(r.id); const s = sig(r, i);
        if (tr && tr.dataset.sig !== s && r.id !== foco) { tr.innerHTML = linhaHtml(r, i); tr.dataset.sig = s; tr.classList.remove('fs-flash'); void tr.offsetWidth; tr.classList.add('fs-flash'); }
      });
    }
    $('#fsFoot').textContent = `Mostrando ${lst.length} de ${FS.linhas.length} empresas · clique na célula para escolher Sim, Não ou N/A · a data de finalização é preenchida sozinha quando as três etapas ficam Sim ou N/A`;
  }
  const sig = (r, i) => [i, r.nome, r.analista, r.esc, r.pgdas, r.das, r.fin, r.obs, r.cnpj, FS.admin].join('¦');

  async function onCelula(ev) {
    const el = ev.target; const campo = el.dataset.c, id = el.dataset.id;
    if (!campo || !id) return;
    const valor = el.value;
    if (el.tagName === 'SELECT') el.className = 'fs-sel ' + (valor === 'Sim' ? 'v-sim' : valor === 'Não' ? 'v-nao' : valor === 'N/A' ? 'v-na' : 'v-vz');
    const r = await window.fiscocont.fechamento.salvar(FS.comp, id, campo, valor);
    if (r && r.error) toast(r.error, true);
  }

  async function onAcao(ev) {
    const b = ev.target.closest('[data-a]'); if (!b) return;
    const r = FS.linhas.find((x) => x.id === b.dataset.id); if (!r) return;
    if (b.dataset.a === 'editar') modalEmpresa(r);
    if (b.dataset.a === 'excluir') {
      if (!confirm(`Excluir "${r.nome}" do fechamento a partir de ${compRot(FS.comp)}? Os meses anteriores continuam com ela.`)) return;
      const x = await window.fiscocont.fechamento.excluir(FS.comp, r.id);
      if (x && x.error) toast(x.error, true); else toast('Empresa excluída do fechamento.');
    }
  }

  // ------------------------------------------------------------------ cadastro / edição (Admin)
  function fechaModal() { $('#fsModal').hidden = true; }
  function modalEmpresa(r) {
    const nomes = [...new Set(FS.linhas.map((x) => x.analista).filter(Boolean))].sort();
    const comps = listaComps();
    const box = $('#fsMBox');
    box.innerHTML = `<h3>${r ? 'Alterar empresa' : 'Cadastrar empresa no fechamento'}</h3>
      ${r ? '' : `<label>CNPJ (opcional)</label><div class="fs-row"><input id="fsMCnpj" class="fs-in" placeholder="00.000.000/0000-00"><button class="act inv-export" id="fsMBusca">Buscar na Receita</button></div>`}
      <label>Razão social</label><input id="fsMNome" class="fs-in" value="${r ? e(r.nome) : ''}">
      <label>Analista responsável</label><input id="fsMAn" class="fs-in" list="fsMAnList" value="${r ? e(r.analista) : ''}" placeholder="Escolha ou digite um nome">
      <datalist id="fsMAnList">${nomes.map((n) => `<option value="${e(n)}">`).join('')}</datalist>
      ${r ? '' : `<label>A partir de</label><select id="fsMDesde" class="fs-in">${comps.map((c) => `<option value="${c}" ${c === FS.comp ? 'selected' : ''}>${compRot(c)}</option>`).join('')}</select><small class="fs-hint">Entra nessa competência e nas próximas.</small>`}
      <div class="fs-mact"><button class="act inv-export" id="fsMCanc">Cancelar</button><button class="act inv-export fs-prim" id="fsMOk">${r ? 'Salvar' : 'Cadastrar'}</button></div>`;
    $('#fsModal').hidden = false;
    $('#fsMCanc').onclick = fechaModal;
    if (!r) $('#fsMBusca').onclick = async () => {
      const bt = $('#fsMBusca'); bt.disabled = true; bt.textContent = 'Buscando…';
      const x = await window.fiscocont.fechamento.cnpj($('#fsMCnpj').value);
      bt.disabled = false; bt.textContent = 'Buscar na Receita';
      if (x.error) { toast(x.error, true); return; }
      $('#fsMNome').value = x.nome;
    };
    $('#fsMOk').onclick = async () => {
      const bt = $('#fsMOk'); bt.disabled = true;
      const x = r
        ? await window.fiscocont.fechamento.alterar(FS.comp, r.id, { nome: $('#fsMNome').value, analista: $('#fsMAn').value })
        : await window.fiscocont.fechamento.cadastrar(FS.comp, { nome: $('#fsMNome').value, cnpj: $('#fsMCnpj').value, analista: $('#fsMAn').value, desde: $('#fsMDesde').value });
      bt.disabled = false;
      if (x && x.error) { toast(x.error, true); return; }
      fechaModal(); toast(r ? 'Empresa alterada.' : 'Empresa cadastrada.');
    };
    setTimeout(() => (r ? $('#fsMNome') : $('#fsMCnpj')).focus(), 30);
  }

  // ------------------------------------------------------------------ HTML exportado (números, anéis e tabela, animados)
  function exportar() {
    if (!FS.linhas.length) { toast('Nada para exportar nessa competência.', true); return; }
    const { tot, analistas } = resumo(FS.linhas);
    const n = analistas.length, passo = n > 1 ? Math.min(16, (138 - 58) / (n - 1)) : 16, larg = Math.max(6, passo - 4);
    const aneis = analistas.map((a, i) => { const r = 138 - i * passo, L = 2 * Math.PI * r;
      return `<circle cx="150" cy="150" r="${r}" fill="none" stroke="${a.cor}" stroke-opacity=".14" stroke-width="${larg}"/><circle class="rg" data-v="${(L * (a.n ? a.feitas / a.n : 0)).toFixed(1)}" data-l="${L.toFixed(1)}" cx="150" cy="150" r="${r}" fill="none" stroke="${a.cor}" stroke-width="${larg}" stroke-linecap="round" stroke-dasharray="0 ${L.toFixed(1)}" transform="rotate(-90 150 150)" style="transition:stroke-dasharray 1.6s cubic-bezier(.2,.8,.2,1) ${(i * 0.12).toFixed(2)}s"/>`; }).join('');
    const pctTot = tot.n ? Math.round(tot.feitas / tot.n * 100) : 0;
    const leg = analistas.map((a) => `<div class="rl"><span class="av" style="background:${a.cor}">${e(a.ini)}</span><b>${e(a.nome)}</b><span class="rp cnt" data-v="${a.pct}" data-s="%" style="color:${a.cor}">0%</span><small>${a.feitas} de ${a.n} transmitidas</small></div>`).join('');
    const pill = (v) => `<span class="pl ${v === 'Sim' ? 's' : v === 'Não' ? 'x' : v === 'N/A' ? 'na' : 'vz'}">${e(v || '—')}</span>`;
    const linhas = [...FS.linhas].map((r, i) => { const st = status(r);
      return `<tr><td>${i + 1}</td><td class="l"><i class="dot" style="background:${ST[st].cor}"></i><b>${e(r.nome)}</b></td><td class="l">${e(r.analista)}</td><td>${pill(r.esc)}</td><td>${pill(r.pgdas)}</td><td>${pill(r.das)}</td><td>${e(r.fin || '—')}</td><td class="l">${e(r.obs)}${st === 'alerta' ? ' <span class="neg">⚠ PGDAS sem escrituração</span>' : ''}</td></tr>`; }).join('');
    const kp = [['Empresas', tot.n, '#141b2d'], ['PGDAS transmitido', tot.feitas, '#4f46e5'], ['Escrituradas, falta transmitir', tot.escriturada, '#f59e0b'], ['Pendentes', tot.pendente, '#e23d4c'], ['Inconsistentes', tot.alerta, '#b42318'], ['Concluídas', tot.concluida, '#0ea472']]
      .map(([t, v, c]) => `<div class="k"><small>${t}</small><b class="cnt" data-v="${v}" style="color:${c}">0</b></div>`).join('');
    const quem = (typeof SESSAO !== 'undefined' && SESSAO.info && SESSAO.info.nome) || '';
    const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fechamento do Simples Nacional · ${compRot(FS.comp)}</title><style>
*{box-sizing:border-box;margin:0;padding:0}body{font-family:'Segoe UI',Inter,Arial,sans-serif;background:#f4f6fb;color:#141b2d;padding:28px;font-size:13px}
.wrap{max-width:1240px;margin:0 auto}.hd{background:linear-gradient(90deg,#141733,#1c2148);color:#fff;border-radius:16px;padding:22px 26px;margin-bottom:18px}
.hd h1{font-size:22px}.hd p{color:#c7cbe6;margin-top:4px}.card{background:#fff;border:1px solid #e5e9f1;border-radius:14px;padding:18px;margin-bottom:16px;box-shadow:0 10px 30px rgba(20,30,60,.06)}
.card h2{font-size:14px;margin-bottom:10px}.ks{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:16px}.k{background:#fff;border:1px solid #e5e9f1;border-radius:12px;padding:12px 14px}
.k small{color:#5a6785;font-size:11.5px}.k b{display:block;font-size:24px;margin-top:3px}.rings{display:flex;align-items:center;gap:30px;flex-wrap:wrap}
.rl{display:flex;align-items:center;gap:10px;margin:8px 0;opacity:0;transform:translateX(14px);transition:all .5s}.go .rl{opacity:1;transform:none}
.av{width:30px;height:30px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:11.5px;flex:0 0 auto}
.rl b{width:90px}.rp{font-size:20px;font-weight:800;width:62px}.rl small,.cr small{color:#5a6785}
.cr{display:flex;align-items:center;gap:12px;margin:10px 0}.cr>b{width:90px}.cr .p{width:46px;text-align:right}.bar{flex:1;height:20px;border-radius:7px;background:#eef0f6;overflow:hidden;display:flex}
.bar i{display:block;height:100%;width:0;transition:width 1.4s cubic-bezier(.2,.8,.2,1)}
table{width:100%;border-collapse:collapse}th{font-size:10.5px;color:#5a6785;text-transform:uppercase;letter-spacing:.04em;padding:8px;border-bottom:1px solid #e5e9f1;text-align:center}
td{padding:8px;border-bottom:1px solid #f0f2f7;text-align:center}.l{text-align:left}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px}
.pl{display:inline-block;min-width:44px;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700}.s{background:#e6f7ef;color:#0a7a52}.x{background:#fdecf0;color:#c22b45}.na{background:#eef0f6;color:#5a6785}.vz{color:#b7bdcc}
.neg{color:#c22b45;font-weight:600}.leg{display:flex;gap:16px;flex-wrap:wrap;margin-top:6px;font-size:12px;color:#5a6785}.leg i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px}
@media(max-width:800px){.ks{grid-template-columns:repeat(2,1fr)}}
</style></head><body><div class="wrap">
<div class="hd"><h1>Fechamento do Simples Nacional · ${compRot(FS.comp)}</h1><p>Prazo do PGDAS-D e do DAS: ${fmtData(prazo(FS.comp))} · gerado em ${fmtData(new Date())}${quem ? ' por ' + e(quem) : ''} · FiscoCont+</p></div>
<div class="ks">${kp}</div>
<div class="card"><h2>Por analista · % com PGDAS transmitido</h2><div class="rings"><svg viewBox="0 0 300 300" width="300" height="300">${aneis}<text x="150" y="148" text-anchor="middle" font-size="28" font-weight="800" fill="#141b2d" class="cnt" data-v="${pctTot}" data-s="%">0%</text><text x="150" y="171" text-anchor="middle" font-size="12" fill="#5a6785">equipe</text></svg><div>${leg}</div></div></div>
<div class="card"><h2>Empresas</h2><table><thead><tr><th>#</th><th class="l">Empresa</th><th class="l">Analista</th><th>Escrituração</th><th>PGDAS</th><th>DAS/DARE ao cliente</th><th>Finalização</th><th class="l">Observações</th></tr></thead><tbody>${linhas}</tbody></table></div>
</div><script>
setTimeout(function(){document.body.classList.add('go');
document.querySelectorAll('.rg').forEach(function(c){c.setAttribute('stroke-dasharray',c.dataset.v+' '+c.dataset.l)});
var t0=performance.now();document.querySelectorAll('.cnt').forEach(function(el){var v=+el.dataset.v,s=el.dataset.s||'';(function f(t){var p=Math.min(1,(t-t0)/1500),q=1-Math.pow(1-p,3);el.textContent=Math.round(v*q)+s;if(p<1)requestAnimationFrame(f)})(t0)});
},250);
</script></body></html>`;
    window.fiscocont.fiscal.nfseExportarHtml(html, 'fech-sn', compRot(FS.comp).replace('/', '-')).then((r) => {
      if (!r || r.canceled) return; if (r.error) { toast(r.error, true); return; }
      toast('Fechamento exportado.'); window.fiscocont.openPath(r.path);
    });
  }

  // ------------------------------------------------------------------ entrada
  function abas(qual) {
    document.querySelectorAll('.sn-tab').forEach((b) => b.classList.toggle('on', b.dataset.sntab === qual));
    $('#fechSN').hidden = qual !== 'fech';
    $('#pgdasPainel').hidden = qual !== 'painel';
    if (qual === 'fech') entrar();
  }
  function entrar() {
    if (!FS.iniciado) {
      FS.iniciado = true;
      montar();
      window.fiscocont.fechamento.onMudou(aoMudar);
    }
    if (!FS.aberto) { FS.aberto = true; abrir(); return; }
    // voltou para a tela: os anéis enchem e os números contam de novo
    FS.anel = null; FS.kpiAnt = {};
    if (FS.linhas.length) desenhaTudo();
  }
  window.fechEntrar = function () {
    const aba = document.querySelector('.sn-tab.on');
    abas(aba ? aba.dataset.sntab : 'fech');
  };
  window.fechSair = function () { FS.aberto = false; FS.iniciado = false; window.fiscocont.fechamento.parar(); const b = $('#fechSN'); if (b) b.innerHTML = ''; };
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.sn-tab').forEach((b) => b.addEventListener('click', () => abas(b.dataset.sntab)));
  });
})();

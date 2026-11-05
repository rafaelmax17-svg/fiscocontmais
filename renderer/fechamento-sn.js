'use strict';
// Simples Nacional · Fechamento da equipe — planilha editável em tempo real (Firestore), com o painel de
// acompanhamento (etapas, por analista, não concluídas) e exportação em HTML. Usa os utilitários do app.js ($, toast, ROLE).
(function () {
  const MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
  const INICIO = '2026-09';                       // primeira competência controlada no sistema (planilha da equipe)
  const COR_FIXA = { 'heloisa': '#7c3aed', 'hemily': '#0ea5e9', 'thawani': '#14b8a6', 'cauane': '#f59e0b', 'hotoniel': '#db2777', 'valéria': '#e23d4c', 'valeria': '#e23d4c', 'taynara': '#d946ef' };
  const PALETA = ['#6366f1', '#ec4899', '#84cc16', '#06b6d4', '#f97316', '#8b5cf6', '#10b981', '#ef4444'];
  const ST = {
    concluida: { rot: 'Concluída', cor: '#0ea472' },
    transmitida: { rot: 'PGDAS transmitido', cor: '#4f46e5' },
    escriturada: { rot: 'Escriturada, falta transmitir', cor: '#f59e0b' },
    alerta: { rot: 'Inconsistente', cor: '#b42318' },
    pendente: { rot: 'Pendente', cor: '#e23d4c' },
  };
  const FS = { ig: { ativo: false }, comp: '', linhas: [], listaAn: [], admin: false, analista: '', busca: '', chip: 'todas', iniciado: false, aberto: false, anel: null, kpiAnt: {} };

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
  function compProx(c) { let [a, m] = c.split('-').map(Number); m++; if (m > 12) { m = 1; a++; } return `${a}-${String(m).padStart(2, '0')}`; }
  function compAnterior() { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; }
  function listaComps() {
    const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() + 3);       // até 3 meses à frente do mês atual
    const fim = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
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
    const tot = { n: linhas.length, concluida: 0, transmitida: 0, escriturada: 0, alerta: 0, pendente: 0, semMov: 0, esc: 0 };
    const por = new Map();
    for (const r of linhas) {
      const st = status(r); tot[st]++; if (r.semMovimento) tot.semMov++; if (ok(r.esc)) tot.esc++;
      const k = r.analista || '(sem analista)';
      if (!por.has(k)) por.set(k, { nome: k, n: 0, feitas: 0, esc: 0, concluida: 0, transmitida: 0, escriturada: 0, alerta: 0, pendente: 0 });
      const a = por.get(k); a.n++; a[st]++; if (feito(st)) a.feitas++; if (ok(r.esc)) a.esc++;
    }
    tot.feitas = tot.transmitida + tot.concluida;
    const nomes = [...por.keys()].sort((x, y) => x.localeCompare(y));
    const analistas = [...por.values()].sort((x, y) => y.n - x.n || x.nome.localeCompare(y.nome))
      .map((a) => ({ ...a, cor: corAnalista(a.nome, nomes.indexOf(a.nome)), pct: a.n ? Math.round(a.feitas / a.n * 100) : 0, pctEsc: a.n ? Math.round(a.esc / a.n * 100) : 0 }));
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
      <div class="fs-steps" id="fsSteps"></div>
      <div class="fs-alert" id="fsAlert" hidden></div>
      <div class="fs-pgrid">
        <div class="fs-card fs-pcard"><div class="fs-ph"><b>Por analista</b><small>da maior carteira para a menor</small></div><div id="fsPAn"></div></div>
        <div class="fs-card fs-pcard"><div class="fs-ph"><b>Ainda não concluídas</b><small id="fsNcTot"></small></div>
          <div class="fs-nctabs" id="fsNcTabs"></div><div class="fs-nclist" id="fsNcList"></div></div>
      </div>
      <div class="fs-bar">
        <select id="fsComp" class="fs-in">${comps.map((c) => `<option value="${c}" ${c === FS.comp ? 'selected' : ''}>${compRot(c)}</option>`).join('')}</select>
        <select id="fsAn" class="fs-in"><option value="">Todas as analistas</option></select>
        <input id="fsBusca" class="fs-in fs-busca" placeholder="Buscar empresa…">
        <div class="fs-chips" id="fsChips"></div>
        <span style="flex:1"></span>
        <span class="fs-robo" id="fsRobo" hidden></span>
        <button class="act inv-export fs-rec" id="fsReceita" hidden title="O robô consulta na Receita Federal (Integra Contador) as empresas ainda não confirmadas">🔎 Conferir na Receita</button>
        <button class="act inv-export" id="fsHtml">Exportar HTML</button>
        <button class="act inv-export" id="fsAnalistas" hidden>Analistas</button>
        <button class="act inv-export fs-prim" id="fsNova" hidden>+ Cadastrar empresa</button>
      </div>
      <div class="fs-recbox" id="fsRecBox" hidden></div>
      <div class="fs-card fs-tab-wrap"><table class="fs-tab"><thead><tr>
        <th>#</th><th class="l">Empresa</th><th class="l">Analista responsável</th><th>Escrituração concluída</th><th>PGDAS transmitido</th><th class="l fs-rf-col" hidden>Receita Federal</th>
        <th>DAS/DARE enviado ao cliente</th><th>Data finalização</th><th class="l">Observações</th><th class="fs-adm-col" hidden></th></tr></thead>
        <tbody id="fsBody"></tbody></table>
        <div class="fs-foot" id="fsFoot"></div></div>
      <div class="fs-modal" id="fsModal" hidden><div class="fs-mbox" id="fsMBox"></div></div>`;
    $('#fsComp').addEventListener('change', (ev) => { FS.comp = ev.target.value; abrir(); });
    $('#fsAn').addEventListener('change', (ev) => { FS.analista = ev.target.value; desenhaTabela(true); });
    $('#fsBusca').addEventListener('input', (ev) => { FS.busca = ev.target.value; desenhaTabela(true); });
    $('#fsHtml').addEventListener('click', exportar);
    $('#fsReceita').addEventListener('click', conferirReceita);
    $('#fsNova').addEventListener('click', () => modalEmpresa());
    $('#fsAnalistas').addEventListener('click', modalAnalistas);
    $('#fsBody').addEventListener('change', onCelula);
    $('#fsBody').addEventListener('click', onAcao);
    $('#fsModal').addEventListener('click', (ev) => { if (ev.target.id === 'fsModal') fechaModal(); });
  }

  async function abrir() {
    FS.linhas = []; FS.anel = null; FS.kpiAnt = {};
    $('#fsSteps').innerHTML = ''; $('#fsPAn').innerHTML = ''; $('#fsNcList').innerHTML = ''; $('#fsBody').innerHTML = '';
    $('#fsBody').dataset.ordem = '';        // achado real: mesmas empresas no mês novo = mesma "ordem", e a tabela não era redesenhada
    $('#fsFoot').textContent = 'Carregando…';
    const r = await window.fiscocont.fechamento.abrir(FS.comp);
    if (r && r.error) { $('#fsFoot').textContent = r.error; toast(r.error, true); }
  }

  function aoMudar(d) {
    if (!d || d.comp !== FS.comp) return;
    FS.linhas = d.linhas || []; FS.admin = !!d.admin; FS.listaAn = d.analistas || []; FS.ig = d.integra || { ativo: false };
    if (!$('#fsModal').hidden && $('#fsMBox').dataset.tipo === 'an') modalAnalistas();
    const live = $('#fsLive'); if (live) { live.classList.remove('pulse'); void live.offsetWidth; live.classList.add('pulse'); }
    desenhaTudo();
  }

  // ------------------------------------------------------------------ desenho
  function desenhaTudo() {
    const { tot, analistas } = resumo(FS.linhas);
    const pz = prazo(FS.comp), venc = Date.now() > pz.getTime(), falta = tot.n - tot.feitas;
    $('#fsSub').innerHTML = `Competência <b>${compRot(FS.comp)}</b> · prazo do PGDAS-D e do DAS: <b class="${venc && falta ? 'neg' : ''}">${fmtData(pz)}</b>${venc && falta ? ' · <span class="neg">vencido</span>' : ''}`;
    const al = FS.linhas.filter((r) => status(r) === 'alerta');
    const avisos = [];
    if (al.length) avisos.push(`<b>${al.length} inconsistência(s):</b> PGDAS transmitido sem a escrituração concluída — ${al.slice(0, 3).map((r) => e(r.nome)).join(', ')}${al.length > 3 ? '…' : ''}.`);
    if (venc && falta) avisos.push(`<b>Prazo vencido:</b> ${falta} empresa(s) ainda sem PGDAS transmitido.`);
    $('#fsAlert').hidden = !avisos.length; $('#fsAlert').innerHTML = avisos.join(' ');
    desenhaPainel(tot, analistas);
    const sel = $('#fsAn'), atual = FS.analista;
    sel.innerHTML = '<option value="">Todas as analistas</option>' + analistas.map((a) => `<option ${a.nome === atual ? 'selected' : ''}>${e(a.nome)}</option>`).join('');
    const chips = [['todas', 'Todas', tot.n], ['pendente', 'Pendentes', tot.pendente + tot.escriturada], ['alerta', 'Inconsistentes', tot.alerta],
      ['semmov', 'Sem movimento', tot.semMov], ['concluida', 'Concluídas', tot.concluida]];
    if (FS.ig.ativo) chips.splice(3, 0, ['verificar', 'Verificar (Receita)', FS.linhas.filter((r) => recSit(r).k === 'verificar').length]);
    $('#fsChips').innerHTML = chips.map(([id, rot, n]) => `<button class="fs-chip ${FS.chip === id ? 'on' : ''}" data-chip="${id}">${rot} <b>${n}</b></button>`).join('');
    $('#fsChips').querySelectorAll('.fs-chip').forEach((b) => b.addEventListener('click', () => { FS.chip = b.dataset.chip; desenhaTudo(); }));
    $('#fsNova').hidden = !FS.admin; $('#fsAnalistas').hidden = !FS.admin;
    desenhaReceita();
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
  // Painel de acompanhamento: etapas em sequência, barra por analista e as empresas que ainda não foram concluídas,
  // separadas pelo que falta. Os números contam do valor anterior até o novo (entrar de novo na tela anima de novo).
  const NC = [['esc', 'falta escrituração', '#0ea5e9'], ['pgdas', 'falta PGDAS', '#6366f1'], ['das', 'falta enviar o DAS', '#10b981']];
  function faltaDe(r) {
    if (status(r) === 'concluida') return null;
    if (!ok(r.esc)) return 'esc';                 // inclui a inconsistente (PGDAS transmitido sem a escrituração)
    if (!ok(r.pgdas)) return 'pgdas';
    return 'das';
  }
  function desenhaPainel(tot, analistas) {
    const N = tot.n || 0;
    const pg = FS.linhas.filter((r) => ok(r.pgdas)).length, dasOk = FS.linhas.filter((r) => ok(r.das)).length;
    const etapas = [['s', 'Escrituração concluída', tot.esc, '#0ea5e9', '📒'], ['f', 'PGDAS transmitido', pg, '#6366f1', '📤'], ['d', 'DAS enviado ao cliente', dasOk, '#10b981', '✅']];
    $('#fsSteps').innerHTML = etapas.map(([id, t, v, cor, ic], i) => `${i ? '<div class="fs-seta">›</div>' : ''}<div class="fs-st" style="--c:${cor};animation-delay:${(i * 0.1).toFixed(2)}s">
      <div class="fs-sti">${ic}</div><small>${t}</small><div class="fs-stv"><b data-k="${id}">${FS.kpiAnt[id] ?? 0}</b><span>de ${N}</span></div>
      <div class="fs-pb"><i style="--w:${N ? (v / N * 100).toFixed(1) : 0}%"></i></div><em>${N ? Math.round(v / N * 100) : 0}%</em></div>`).join('');
    etapas.forEach(([id, , v]) => { conta($(`[data-k="${id}"]`), FS.kpiAnt[id] ?? 0, v); FS.kpiAnt[id] = v; });
    // por analista: barra dividida em concluída (DAS enviado), PGDAS transmitido e só escriturada
    $('#fsPAn').innerHTML = analistas.map((a, i) => {
      const n = a.n || 1, seg = [['concluida', '#10b981'], ['transmitida', a.cor], ['escriturada', a.cor + '55']].filter(([k]) => a[k]);
      const pgA = FS.linhas.filter((r) => (r.analista || '(sem analista)') === a.nome && ok(r.pgdas)).length;
      return `<div class="fs-ar" style="animation-delay:${(0.15 + i * 0.06).toFixed(2)}s"><span class="fs-av2" style="background:linear-gradient(135deg,${a.cor},${a.cor}cc)">${e(a.ini)}</span>
        <div class="fs-am"><div class="fs-at"><b>${e(a.nome)}</b><span>${a.n} empresa${a.n > 1 ? 's' : ''}</span></div>
          <div class="fs-sb">${seg.map(([k, c]) => `<i style="--w:${(a[k] / n * 100).toFixed(2)}%;background:${c}"></i>`).join('')}</div>
          <div class="fs-ac"><span><i style="background:${a.cor}55"></i>${a.esc} escrit.</span><span><i style="background:${a.cor}"></i>${pgA} PGDAS</span><span><i style="background:#10b981"></i>${a.concluida} DAS</span>${a.alerta ? `<span class="neg">⚠ ${a.alerta} inconsistente${a.alerta > 1 ? 's' : ''}</span>` : ''}</div></div>
        <div class="fs-ap" style="color:${a.cor}"><b>${a.n ? Math.round(a.concluida / a.n * 100) : 0}%</b><small>concluídas</small></div></div>`;
    }).join('') || '<div class="fs-vz">Nenhuma empresa nesta competência.</div>';
    // ainda não concluídas, pelo que falta
    const grupos = { esc: [], pgdas: [], das: [] };
    FS.linhas.forEach((r) => { const f = faltaDe(r); if (f) grupos[f].push(r); });
    if (!FS.ncTab || (!grupos[FS.ncTab].length && NC.some(([k]) => grupos[k].length))) FS.ncTab = (NC.find(([k]) => grupos[k].length) || NC[0])[0];
    const totNc = grupos.esc.length + grupos.pgdas.length + grupos.das.length;
    $('#fsNcTot').textContent = `${totNc} empresa${totNc === 1 ? '' : 's'}`;
    $('#fsNcTabs').innerHTML = NC.map(([k, t, c]) => `<button class="fs-nct ${FS.ncTab === k ? 'on' : ''}" data-nc="${k}" style="--c:${c}"><b>${grupos[k].length}</b>${t}</button>`).join('');
    $('#fsNcTabs').querySelectorAll('[data-nc]').forEach((b) => b.addEventListener('click', () => { FS.ncTab = b.dataset.nc; desenhaPainel(tot, analistas); }));
    const corDe = new Map(analistas.map((a) => [a.nome, a]));
    const lista = grupos[FS.ncTab].slice().sort((x, y) => (x.analista || '').localeCompare(y.analista || '') || x.nome.localeCompare(y.nome));
    $('#fsNcList').innerHTML = lista.map((r) => { const a = corDe.get(r.analista || '(sem analista)') || { cor: '#6366f1', ini: '?' };
      return `<div class="fs-li"><span class="fs-mini2" style="background:${a.cor}" title="${e(r.analista || '')}">${e(a.ini)}</span><b>${e(r.nome)}</b>${status(r) === 'alerta' ? '<span class="neg" title="PGDAS transmitido sem a escrituração concluída">⚠</span>' : ''}</div>`; }).join('')
      || '<div class="fs-vz ok">✓ Nenhuma empresa nesta etapa.</div>';
  }

  // ------------------------------------------------------------------ Receita Federal (robô do Integra Contador)
  // Só aparece depois que o Admin cadastrar a chave do Serpro. O robô nunca desmarca o que a analista marcou:
  // quando a Receita discorda da marcação, a linha mostra "Verificar".
  function recSit(r) {
    const rc = r.receita;
    if (!rc || !rc.st) return { k: '', rot: '' };
    if (rc.st === 'ok' && r.pgdas === 'N/A') return { k: 'verificar', rot: 'marcado “N/A”, mas a Receita tem declaração do período' };
    if (rc.st === 'ok') return { k: 'ok', rot: rc.msg || 'Transmitido' };
    if (rc.st === 'nao' && r.pgdas === 'Sim') return { k: 'verificar', rot: 'marcado “Sim”, mas a Receita não tem declaração do período' };
    if (rc.st === 'nao') return { k: 'nao', rot: 'Ainda não transmitido' };
    if (rc.st === 'semproc') return { k: 'semproc', rot: 'cliente precisa autorizar a Liddera no e-CAC' };
    if (rc.st === 'semcnpj') return { k: 'semcnpj', rot: 'cadastre o CNPJ da empresa' };
    return { k: 'erro', rot: rc.msg || 'falha na consulta' };
  }
  const ROT_DOC = { Declaracao: 'Declaração', Recibo: 'Recibo', DAS: 'DAS', Extrato: 'Extrato' };
  function celReceita(r) {
    if (!FS.ig.ativo) return '';
    const s = recSit(r), rc = r.receita || {};
    if (!s.k) return '<span class="fs-rf-vz">—</span>';
    const tt = rc.em ? ` title="Conferido na Receita Federal em ${e(rc.em)}"` : '';
    const docs = Object.keys(rc.arquivos || {});
    const docsHtml = docs.length ? `<button class="fs-rf-docs" data-a="pasta" data-id="${r.id}" title="${e(rc.pasta || '')}">📄 ${docs.map((d) => ROT_DOC[d] || d).join(' · ')}${rc.dasValor ? ` · R$ ${Number(rc.dasValor).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}` : ''}</button>` : '';
    const av = [rc.pastaAviso, rc.dasAviso].filter(Boolean).map((x) => `<small class="fs-rf-av">⚠ ${e(x)}</small>`).join('');
    if (s.k === 'ok') return `<div class="fs-rf ok"${tt}>✓ ${e(s.rot)}${docsHtml}${av}</div>`;
    if (s.k === 'verificar') return `<div class="fs-rf"${tt}><span class="fs-rf-b vf">⚠ Verificar</span><small class="fs-rf-t vf">${e(s.rot)}</small></div>`;
    if (s.k === 'semproc') return `<div class="fs-rf"><span class="fs-rf-b sp">Sem procuração</span><small class="fs-rf-t sp">${e(s.rot)}</small></div>`;
    if (s.k === 'semcnpj') return `<div class="fs-rf"><span class="fs-rf-b sc">Sem CNPJ</span><small class="fs-rf-t">${e(s.rot)}</small></div>`;
    if (s.k === 'nao') return `<div class="fs-rf nao"${tt}>${e(s.rot)}</div>`;
    return `<div class="fs-rf"><span class="fs-rf-b er">Falha</span><small class="fs-rf-t" title="${e(s.rot)}">${e(String(s.rot).slice(0, 110))}</small></div>`;
  }
  function desenhaReceita() {
    const ig = FS.ig || {};
    document.querySelectorAll('.fs-rf-col').forEach((x) => { x.hidden = !ig.ativo; });
    $('#fsRobo').hidden = !ig.ativo; $('#fsReceita').hidden = !ig.ativo;
    const box = $('#fsRecBox');
    if (!ig.ativo) { box.hidden = true; return; }
    const u = ig.ultimo;
    $('#fsRobo').className = 'fs-robo ' + (ig.online ? 'on' : 'off');
    $('#fsRobo').textContent = ig.online ? `Robô online${u && u.emBr ? ' · última conferência ' + u.emBr.replace(',', '').slice(0, 16) : ''}` : 'Robô offline';
    $('#fsRobo').title = ig.online ? `Computador do robô: ${ig.roboNome}` : `O computador do robô (${ig.roboNome || '—'}) está desligado ou com o FiscoCont+ fechado. O pedido fica guardado e roda quando ele ligar.`;
    const rd = ig.rodando && ig.rodando.comp === FS.comp ? ig.rodando : null;
    $('#fsReceita').disabled = !!rd || ig.pendente;
    $('#fsReceita').textContent = rd ? 'Conferindo…' : ig.pendente ? 'Pedido na fila…' : '🔎 Conferir na Receita';
    const c = { ok: 0, nao: 0, verificar: 0, semproc: 0, semcnpj: 0, erro: 0 };
    FS.linhas.forEach((r) => { const k = recSit(r).k; if (k) c[k]++; });
    const algum = Object.values(c).some(Boolean);
    let prog = '';
    if (rd) prog = `<div class="fs-rprog"><span>Conferindo na Receita · ${rd.feito} de ${rd.total} empresas</span><div class="fs-rbar"><i style="width:${rd.total ? Math.round(rd.feito / rd.total * 100) : 0}%"></i></div></div>`;
    else if (ig.pendente) prog = `<div class="fs-rprog"><span>${ig.online ? 'Pedido enviado ao robô…' : 'Pedido guardado: roda quando o computador do robô ligar.'}</span></div>`;
    else if (u && u.comp === FS.comp) prog = `<div class="fs-rprog ${u.erro ? 'er' : ''}"><span>${u.erro ? '⚠ ' + e(u.erro) : `✓ Conferência concluída · ${u.total} empresa(s) consultada(s)${u.resumo && u.resumo.arquivos ? ` · ${u.resumo.arquivos} documento(s) salvo(s)` : ''}`}</span><small>${e(u.emBr || '')}${u.por ? ' · ' + e(u.por) : ''}</small></div>`;
    if (!algum && !prog) { box.hidden = true; return; }
    const t = [['ok', 'PGDAS confirmados na Receita', '#059669'], ['nao', 'Ainda não transmitidos', '#6366f1'], ['verificar', 'Verificar (divergência)', '#d97706'],
      ['semproc', 'Sem procuração no e-CAC', '#dc2626'], ['semcnpj', 'Sem CNPJ no cadastro', '#64748b'], ['erro', 'Falha na consulta', '#9f1239']].filter(([k], i) => i < 4 || c[k]);
    box.hidden = false;
    box.innerHTML = prog + (algum ? `<div class="fs-rtiles">${t.map(([k, rot, cor]) => `<button class="fs-rt" style="--c:${cor}" data-rk="${k}"><b>${c[k]}</b>${rot}</button>`).join('')}</div>` : '');
    box.querySelectorAll('[data-rk="verificar"]').forEach((b) => b.addEventListener('click', () => { FS.chip = 'verificar'; desenhaTudo(); }));
  }
  async function conferirReceita() {
    const filtro = FS.analista || FS.busca.trim() || FS.chip !== 'todas';
    const ids = filtro ? filtradas().map((r) => r.id) : null;
    if (ids && !ids.length) { toast('Nenhuma empresa no filtro atual.', true); return; }
    const bt = $('#fsReceita'); bt.disabled = true;
    const x = await window.fiscocont.fechamento.conferirReceita(FS.comp, ids);
    if (x && x.error) { bt.disabled = false; toast(x.error, true); return; }
    toast(`Pedido enviado ao robô${ids ? ` (${ids.length} empresa${ids.length > 1 ? 's' : ''} do filtro)` : ''}. Só são consultadas as que ainda não foram confirmadas.`);
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
      if (FS.chip === 'verificar') return recSit(r).k === 'verificar';
      return true;
    });
  }

  const selEtapa = (r, campo) => {
    const v = r[campo] || '';
    const cls = v === 'Sim' ? 'v-sim' : v === 'Não' ? 'v-nao' : v === 'N/A' ? 'v-na' : 'v-vz';
    return `<select class="fs-sel ${cls}" data-c="${campo}" data-id="${r.id}">${['', 'Sim', 'Não', 'N/A'].map((o) => `<option value="${o}" ${o === v ? 'selected' : ''}>${o || '—'}</option>`).join('')}</select>`;
  };
  const chaveAn = (n) => String(n || '').trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  // Admin: troca a analista direto na linha (vale para este mês e para os próximos; os meses anteriores ficam como estavam).
  function selAnalista(r) {
    const k = chaveAn(r.analista); const nomes = [...FS.listaAn];
    if (r.analista && !nomes.some((n) => chaveAn(n) === k)) nomes.push(r.analista);
    return `<select class="fs-ansel" data-an="${r.id}" title="Trocar a analista responsável">${r.analista ? '' : '<option value="">—</option>'}${nomes.map((n) => `<option value="${e(n)}" ${chaveAn(n) === k ? 'selected' : ''}>${e(n)}</option>`).join('')}</select>`;
  }
  function linhaHtml(r, i) {
    const st = status(r);
    return `<td class="fs-n">${i + 1}</td>
      <td class="l"><span class="fs-dot" style="background:${ST[st].cor}" title="${ST[st].rot}"></span><b>${e(r.nome)}</b>${r.semMovimento ? '<span class="fs-tag">sem movimento</span>' : ''}${r.inativa && r.saida > FS.comp ? `<span class="fs-tag fs-tag-in">inativa a partir de ${e(compRot(r.saida))}</span>` : ''}${r.cnpj ? `<small>${e(r.cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5'))}</small>` : ''}</td>
      <td class="l">${FS.admin ? selAnalista(r) : e(r.analista || '—')}</td>
      <td>${selEtapa(r, 'esc')}</td><td>${selEtapa(r, 'pgdas')}${r.pgdasRobo && r.pgdas === 'Sim' ? '<small class="fs-robotag" title="Marcado pelo robô depois de confirmar na Receita Federal">robô</small>' : ''}</td>
      <td class="l fs-rf-col" ${FS.ig.ativo ? '' : 'hidden'}>${celReceita(r)}</td><td>${selEtapa(r, 'das')}</td>
      <td class="fs-fin" title="Preenchida sozinha quando as três etapas ficam Sim ou N/A">${r.fin ? e(r.fin) : '—'}</td>
      <td class="l"><input class="fs-obs" data-c="obs" data-id="${r.id}" value="${e(r.obs)}" placeholder="—">${st === 'alerta' ? '<small class="neg">⚠ PGDAS transmitido sem escrituração concluída</small>' : ''}</td>
      <td class="fs-adm-col" ${FS.admin ? '' : 'hidden'}><button class="fs-ic" data-a="editar" data-id="${r.id}" title="Alterar nome, CNPJ ou analista">✎</button>${r.inativa ? `<button class="fs-mini" data-a="reativar" data-id="${r.id}" title="Volta a aparecer nos próximos meses">Reativar</button>` : `<button class="fs-mini del" data-a="inativar" data-id="${r.id}" title="Continua neste mês e some a partir do próximo">Inativar</button>`}</td>`;
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
  const sig = (r, i) => [i, FS.ig.ativo, JSON.stringify(r.receita || ''), r.pgdasRobo, FS.listaAn.join(','), r.nome, r.analista, r.esc, r.pgdas, r.das, r.fin, r.obs, r.cnpj, FS.admin, r.inativa, r.saida].join('¦');

  async function onCelula(ev) {
    if (ev.target.dataset.an) return trocaAnalista(ev.target);
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
    if (b.dataset.a === 'pasta') {
      const x = await window.fiscocont.fechamento.abrirPasta(r.receita && r.receita.pasta);
      if (x && x.error) toast(x.error, true);
    }
    if (b.dataset.a === 'inativar') {
      const prox = compProx(FS.comp);
      if (!confirm(`Inativar "${r.nome}"?\n\nEla continua em ${compRot(FS.comp)} para terminar o fechamento e não aparece mais a partir de ${compRot(prox)}.`)) return;
      const x = await window.fiscocont.fechamento.inativar(FS.comp, r.id);
      if (x && x.error) toast(x.error, true); else toast(`Empresa inativada a partir de ${compRot(prox)}.`);
    }
    if (b.dataset.a === 'reativar') {
      const x = await window.fiscocont.fechamento.reativar(FS.comp, r.id);
      if (x && x.error) toast(x.error, true); else toast('Empresa reativada: volta a aparecer nos próximos meses.');
    }

  }

  async function trocaAnalista(el) {
    const r = FS.linhas.find((x) => x.id === el.dataset.an); if (!r) return;
    const nova = el.value, antes = r.analista;
    if (!nova || nova === antes) return;
    el.disabled = true;
    const x = await window.fiscocont.fechamento.alterar(FS.comp, r.id, { analista: nova });
    el.disabled = false;
    if (x && x.error) { toast(x.error, true); el.value = antes; return; }
    toast(`${r.nome}: analista ${antes ? `trocada de ${antes} para ${nova}` : `definida como ${nova}`} (de ${compRot(FS.comp)} em diante).`);
  }

  // ------------------------------------------------------------------ analistas (Admin)
  function modalAnalistas() {
    const box = $('#fsMBox'); box.dataset.tipo = 'an';
    const { analistas } = resumo(FS.linhas);
    const porNome = new Map(analistas.map((a) => [chaveAn(a.nome), a]));
    const nomes = [...FS.listaAn].sort((a, b) => a.localeCompare(b, 'pt-BR'));
    const idx = nomes.map((n) => n).sort((x, y) => x.localeCompare(y));
    box.innerHTML = `<h3>Analistas do fechamento</h3>
      <div class="fs-anl">${nomes.map((n, i) => { const a = porNome.get(chaveAn(n)); const q = a ? a.n : 0;
        const cor = a ? a.cor : corAnalista(n, idx.indexOf(n));
        return `<div class="fs-anr" style="animation-delay:${(i * 0.04).toFixed(2)}s"><span class="fs-av" style="background:${cor}">${e(a ? a.ini : iniciais(n))}</span><b>${e(n)}</b>
          <small>${q ? `${q} empresa${q > 1 ? 's' : ''} em ${compRot(FS.comp)}` : 'sem empresas ainda'}</small>
          <button class="fs-mini del" data-rm="${e(n)}" ${q ? 'disabled title="Troque a analista das empresas dela antes de remover"' : 'title="Tirar da lista"'}>Remover</button></div>`; }).join('') || '<small class="fs-hint">Nenhuma analista cadastrada.</small>'}</div>
      <label>Nova analista</label><div class="fs-row"><input id="fsANome" class="fs-in" maxlength="40" placeholder="Nome"><button class="act inv-export fs-prim" id="fsAOk">Cadastrar</button></div>
      <small class="fs-hint">Para passar uma empresa para outra analista, escolha o nome na coluna "Analista responsável". A troca vale de ${compRot(FS.comp)} em diante; os meses anteriores ficam como estavam.</small>
      <div class="fs-mact"><button class="act inv-export" id="fsMCanc">Fechar</button></div>`;
    $('#fsModal').hidden = false;
    $('#fsMCanc').onclick = fechaModal;
    const cad = async () => {
      const inp = $('#fsANome'); const bt = $('#fsAOk'); bt.disabled = true;
      const x = await window.fiscocont.fechamento.analistaNova(inp.value);
      bt.disabled = false;
      if (x && x.error) { toast(x.error, true); return; }
      toast(`${x.nome} cadastrada.`);
    };
    $('#fsAOk').onclick = cad;
    $('#fsANome').addEventListener('keydown', (ev) => { if (ev.key === 'Enter') cad(); });
    box.querySelectorAll('[data-rm]').forEach((b) => { b.onclick = async () => {
      if (!confirm(`Tirar ${b.dataset.rm} da lista de analistas?`)) return;
      const x = await window.fiscocont.fechamento.analistaRemover(b.dataset.rm);
      if (x && x.error) toast(x.error, true); else toast(`${b.dataset.rm} removida da lista.`);
    }; });
    setTimeout(() => $('#fsANome') && $('#fsANome').focus(), 30);
  }

  // ------------------------------------------------------------------ cadastro / edição (Admin)
  function fechaModal() { $('#fsModal').hidden = true; $('#fsMBox').dataset.tipo = ''; }
  function modalEmpresa(r) {
    const nomes = [...FS.listaAn];
    if (r && r.analista && !nomes.some((n) => chaveAn(n) === chaveAn(r.analista))) nomes.push(r.analista);
    const comps = listaComps();
    const box = $('#fsMBox'); box.dataset.tipo = 'emp';
    box.innerHTML = `<h3>${r ? 'Alterar empresa' : 'Cadastrar empresa no fechamento'}</h3>
      <label>CNPJ${r ? '' : ' (opcional)'}</label><div class="fs-row"><input id="fsMCnpj" class="fs-in" placeholder="00.000.000/0000-00" value="${r && r.cnpj ? e(r.cnpj) : ''}"><button class="act inv-export" id="fsMBusca">Buscar na Receita</button></div>
      ${r ? '<small class="fs-hint">O robô da Receita (Integra Contador) usa o CNPJ para conferir o PGDAS-D.</small>' : ''}
      <label>Razão social</label><input id="fsMNome" class="fs-in" value="${r ? e(r.nome) : ''}">
      <label>Analista responsável</label><select id="fsMAn" class="fs-in">${r ? '' : '<option value="">Escolha…</option>'}${nomes.map((n) => `<option value="${e(n)}" ${r && chaveAn(n) === chaveAn(r.analista) ? 'selected' : ''}>${e(n)}</option>`).join('')}</select>
      <small class="fs-hint">Analista nova: cadastre antes no botão "Analistas".</small>
      ${r ? '' : `<label>A partir de</label><select id="fsMDesde" class="fs-in">${comps.map((c) => `<option value="${c}" ${c === FS.comp ? 'selected' : ''}>${compRot(c)}</option>`).join('')}</select><small class="fs-hint">Entra nessa competência e nas próximas.</small>`}
      <div class="fs-mact"><button class="act inv-export" id="fsMCanc">Cancelar</button><button class="act inv-export fs-prim" id="fsMOk">${r ? 'Salvar' : 'Cadastrar'}</button></div>`;
    $('#fsModal').hidden = false;
    $('#fsMCanc').onclick = fechaModal;
    $('#fsMBusca').onclick = async () => {
      const bt = $('#fsMBusca'); bt.disabled = true; bt.textContent = 'Buscando…';
      const x = await window.fiscocont.fechamento.cnpj($('#fsMCnpj').value);
      bt.disabled = false; bt.textContent = 'Buscar na Receita';
      if (x.error) { toast(x.error, true); return; }
      $('#fsMNome').value = x.nome;
    };
    $('#fsMOk').onclick = async () => {
      const bt = $('#fsMOk'); bt.disabled = true;
      const x = r
        ? await window.fiscocont.fechamento.alterar(FS.comp, r.id, { nome: $('#fsMNome').value, analista: $('#fsMAn').value, cnpj: $('#fsMCnpj').value })
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
    const N = tot.n, pct = (v) => (N ? Math.round(v / N * 100) : 0);
    const pg = FS.linhas.filter((r) => ok(r.pgdas)).length, dasOk = FS.linhas.filter((r) => ok(r.das)).length;
    const etapas = [['Escrituração concluída', tot.esc, '#0ea5e9', '📒'], ['PGDAS transmitido', pg, '#6366f1', '📤'], ['DAS enviado ao cliente', dasOk, '#10b981', '✅']];
    const steps = etapas.map(([t, v, c, ic], i) => `${i ? '<div class="seta">›</div>' : ''}<div class="st" style="--c:${c};animation-delay:${(i * 0.1).toFixed(2)}s"><div class="sti">${ic}</div><small>${t}</small>
      <div class="stv"><b class="cnt" data-v="${v}">0</b><span>de ${N}</span></div><div class="pb"><i style="--w:${N ? (v / N * 100).toFixed(1) : 0}%"></i></div><em>${pct(v)}%</em></div>`).join('');
    const anHtml = analistas.map((a, i) => {
      const n = a.n || 1, seg = [['concluida', '#10b981'], ['transmitida', a.cor], ['escriturada', a.cor + '55']].filter(([k]) => a[k]);
      const pgA = FS.linhas.filter((r) => (r.analista || '(sem analista)') === a.nome && ok(r.pgdas)).length;
      return `<div class="ar" style="animation-delay:${(0.15 + i * 0.06).toFixed(2)}s"><span class="av2" style="background:linear-gradient(135deg,${a.cor},${a.cor}cc)">${e(a.ini)}</span>
        <div><div class="at"><b>${e(a.nome)}</b><span>${a.n} empresa${a.n > 1 ? 's' : ''}</span></div><div class="sb">${seg.map(([k, c]) => `<i style="--w:${(a[k] / n * 100).toFixed(2)}%;background:${c}"></i>`).join('')}</div>
        <div class="ac"><span><i style="background:${a.cor}55"></i>${a.esc} escrit.</span><span><i style="background:${a.cor}"></i>${pgA} PGDAS</span><span><i style="background:#10b981"></i>${a.concluida} DAS</span>${a.alerta ? `<span class="neg">⚠ ${a.alerta} inconsistente${a.alerta > 1 ? 's' : ''}</span>` : ''}</div></div>
        <div class="ap" style="color:${a.cor}"><b>${a.n ? Math.round(a.concluida / a.n * 100) : 0}%</b><small>concluídas</small></div></div>`;
    }).join('');
    const grupos = { esc: [], pgdas: [], das: [] };
    FS.linhas.forEach((r) => { const f = faltaDe(r); if (f) grupos[f].push(r); });
    const totNc = grupos.esc.length + grupos.pgdas.length + grupos.das.length;
    const corDe = new Map(analistas.map((a) => [a.nome, a]));
    const tab1 = (NC.find(([k]) => grupos[k].length) || NC[0])[0];
    const tabs = NC.map(([k, t, c]) => `<button class="nct ${k === tab1 ? 'on' : ''}" data-nc="${k}" style="--c:${c}"><b>${grupos[k].length}</b>${t}</button>`).join('');
    const listas = NC.map(([k]) => `<div class="ncl" data-l="${k}" ${k === tab1 ? '' : 'hidden'}>${grupos[k].slice().sort((x, y) => (x.analista || '').localeCompare(y.analista || '') || x.nome.localeCompare(y.nome)).map((r) => {
      const a = corDe.get(r.analista || '(sem analista)') || { cor: '#6366f1', ini: '?' };
      return `<div class="li"><span class="mini" style="background:${a.cor}" title="${e(r.analista || '')}">${e(a.ini)}</span><b>${e(r.nome)}</b>${status(r) === 'alerta' ? ' <span class="neg">⚠</span>' : ''}</div>`; }).join('') || '<div class="vz">✓ Nenhuma empresa nesta etapa.</div>'}</div>`).join('');
    const pill = (v) => `<span class="pl ${v === 'Sim' ? 's' : v === 'Não' ? 'x' : v === 'N/A' ? 'na' : 'vz'}">${e(v || '—')}</span>`;
    const linhas = [...FS.linhas].map((r, i) => { const st = status(r);
      return `<tr><td>${i + 1}</td><td class="l"><i class="dot" style="background:${ST[st].cor}"></i><b>${e(r.nome)}</b></td><td class="l">${e(r.analista)}</td><td>${pill(r.esc)}</td><td>${pill(r.pgdas)}</td><td>${pill(r.das)}</td><td>${e(r.fin || '—')}</td><td class="l">${e(r.obs)}${st === 'alerta' ? ' <span class="neg">⚠ PGDAS sem escrituração</span>' : ''}</td></tr>`; }).join('');
    const quem = (typeof SESSAO !== 'undefined' && SESSAO.info && SESSAO.info.nome) || '';
    const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fechamento do Simples Nacional · ${compRot(FS.comp)}</title><style>
*{box-sizing:border-box;margin:0;padding:0}body{font-family:'Segoe UI',Inter,Arial,sans-serif;background:#f3f5fb;color:#141b2d;padding:28px;font-size:13px}
.wrap{max-width:1280px;margin:0 auto}.hd{background:linear-gradient(90deg,#141733,#1c2148);color:#fff;border-radius:18px;padding:22px 26px;margin-bottom:16px}.hd h1{font-size:22px}.hd p{color:#c7cbe6;margin-top:4px}
@keyframes up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}@keyframes w{to{width:var(--w)}}
.steps{display:flex;gap:10px;margin-bottom:16px}.seta{align-self:center;font-size:32px;color:#c3c9de;font-weight:300}
.st{flex:1;position:relative;background:#fff;border-radius:18px;padding:16px 18px 14px;box-shadow:0 1px 0 #e9ecf4,0 16px 36px -18px rgba(30,40,90,.25);overflow:hidden;animation:up .55s both}
.st:before{content:"";position:absolute;inset:0 0 auto 0;height:4px;background:var(--c)}.sti{position:absolute;right:14px;top:12px;width:38px;height:38px;border-radius:12px;display:grid;place-items:center;font-size:18px;background:color-mix(in srgb,var(--c) 14%,white)}
.st small{font-size:12.5px;color:#5a6785;font-weight:600}.stv{display:flex;align-items:baseline;gap:6px;margin:6px 0 11px}.stv b{font-size:36px;line-height:1;color:var(--c)}.stv span{color:#8a93ad}
.pb{height:8px;border-radius:6px;background:#eef0f6;overflow:hidden}.pb i{display:block;height:100%;width:0;border-radius:6px;background:linear-gradient(90deg,color-mix(in srgb,var(--c) 65%,white),var(--c));animation:w 1.3s cubic-bezier(.2,.8,.2,1) .25s forwards}
.st em{position:absolute;right:18px;bottom:26px;font-style:normal;font-weight:800;font-size:14px}
.g{display:grid;grid-template-columns:1.15fr 1fr;gap:14px;margin-bottom:16px}.card{background:#fff;border-radius:18px;padding:18px 20px;box-shadow:0 1px 0 #e9ecf4,0 16px 36px -18px rgba(30,40,90,.25);animation:up .55s both}
.ph{display:flex;justify-content:space-between;margin-bottom:10px}.ph b{font-size:14.5px}.ph small{color:#8a93ad}
.ar{display:grid;grid-template-columns:40px 1fr 74px;gap:13px;align-items:center;padding:10px 0;border-bottom:1px solid #f0f2f7;animation:up .45s both}.ar:last-child{border:0}
.av2{width:40px;height:40px;border-radius:13px;display:grid;place-items:center;color:#fff;font-weight:800;font-size:12.5px}.at{display:flex;justify-content:space-between;font-size:13.5px}.at span{color:#8a93ad;font-size:12px}
.sb{display:flex;gap:3px;height:11px;margin:7px 0 6px;background:#eef0f6;border-radius:8px;overflow:hidden}.sb i{display:block;height:100%;width:0;border-radius:6px;animation:w 1.3s cubic-bezier(.2,.8,.2,1) .35s forwards}
.ac{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:11.5px;color:#5a6785}.ac i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}.ap{text-align:right}.ap b{display:block;font-size:21px}.ap small{font-size:10.5px;color:#8a93ad}
.nctabs{display:flex;gap:8px;margin-bottom:10px}.nct{flex:1;text-align:left;border-radius:14px;padding:9px 12px;background:#f5f7fc;border:1.5px solid transparent;font:inherit;font-size:12px;color:#5a6785;font-weight:600;cursor:pointer}
.nct b{display:block;font-size:21px;color:var(--c)}.nct.on{background:#fff;border-color:var(--c);box-shadow:0 10px 20px -12px var(--c)}
.ncl{max-height:430px;overflow:auto}.li{display:flex;align-items:center;gap:10px;padding:7px 10px;border-radius:11px;font-size:12.8px}.li:nth-child(odd){background:#f8f9fd}.li b{font-weight:600}
.mini{width:26px;height:24px;border-radius:8px;display:grid;place-items:center;color:#fff;font-size:9.5px;font-weight:800;flex:0 0 auto}.vz{color:#0a7a52;padding:12px}
table{width:100%;border-collapse:collapse}th{font-size:10.5px;color:#5a6785;text-transform:uppercase;letter-spacing:.04em;padding:8px;border-bottom:1px solid #e5e9f1;text-align:center}
td{padding:8px;border-bottom:1px solid #f0f2f7;text-align:center}.l{text-align:left}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px}
.pl{display:inline-block;min-width:44px;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700}.s{background:#e6f7ef;color:#0a7a52}.x{background:#fdecf0;color:#c22b45}.na{background:#eef0f6;color:#5a6785}.pl.vz{color:#b7bdcc;padding:3px 9px}
.neg{color:#c22b45;font-weight:600}@media(max-width:900px){.g,.steps{grid-template-columns:1fr;flex-direction:column}}
</style></head><body><div class="wrap">
<div class="hd"><h1>Fechamento do Simples Nacional · ${compRot(FS.comp)}</h1><p>Prazo do PGDAS-D e do DAS: ${fmtData(prazo(FS.comp))} · ${N} empresas · gerado em ${fmtData(new Date())}${quem ? ' por ' + e(quem) : ''} · FiscoCont+</p></div>
<div class="steps">${steps}</div>
<div class="g"><div class="card" style="animation-delay:.2s"><div class="ph"><b>Por analista</b><small>da maior carteira para a menor</small></div>${anHtml}</div>
<div class="card" style="animation-delay:.3s"><div class="ph"><b>Ainda não concluídas</b><small>${totNc} empresa${totNc === 1 ? '' : 's'}</small></div><div class="nctabs">${tabs}</div>${listas}</div></div>
<div class="card"><div class="ph"><b>Empresas</b></div><table><thead><tr><th>#</th><th class="l">Empresa</th><th class="l">Analista</th><th>Escrituração</th><th>PGDAS</th><th>DAS/DARE ao cliente</th><th>Finalização</th><th class="l">Observações</th></tr></thead><tbody>${linhas}</tbody></table></div>
</div><script>
document.querySelectorAll('.nct').forEach(function(b){b.addEventListener('click',function(){document.querySelectorAll('.nct').forEach(function(x){x.classList.toggle('on',x===b)});document.querySelectorAll('.ncl').forEach(function(l){l.hidden=l.dataset.l!==b.dataset.nc})})});
var t0=performance.now();document.querySelectorAll('.cnt').forEach(function(el){var v=+el.dataset.v;(function f(t){var p=Math.min(1,(t-t0)/1300),q=1-Math.pow(1-p,3);el.textContent=Math.round(v*q);if(p<1)requestAnimationFrame(f)})(t0)});
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
    abas(aba ? aba.dataset.sntab : 'painel');      // primeira vez no módulo: Painel do cliente
  };
  window.fechSair = function () { FS.aberto = false; FS.iniciado = false; window.fiscocont.fechamento.parar(); const b = $('#fechSN'); if (b) b.innerHTML = ''; };
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.sn-tab').forEach((b) => b.addEventListener('click', () => abas(b.dataset.sntab)));
  });
})();

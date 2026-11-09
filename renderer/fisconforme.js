'use strict';
// Fisconforme · SEFIN-RO — painel das notificações de todas as empresas (equipe; navegador do robô e portal só para o Admin).
// Ao entrar, confere se o e-CPF do contador está instalado no Windows ANTES de qualquer leitura.
(function () {
  const e = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const ST = { pendente: ['Pendente', 'pe'], contestado: ['Contestada', 'co'], indeferido: ['Indeferida', 'in'], resolvido: ['Resolvida', 'ok'], fora: ['Saiu das listas', 'fo'] };
  const F = { est: null, d: null, filtro: 'pendente', emp: '', malha: '', busca: '', aberto: '', mostrar: 120 };
  const fmtCnpj = (c) => String(c || '').replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
  const fmtCpf = (c) => String(c || '').replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4');
  const per = (p) => /^\d{6}$/.test(p || '') ? `${p.slice(4)}/${p.slice(0, 4)}` : (p || '');
  const dBr = (iso) => iso ? iso.slice(0, 10).split('-').reverse().join('/') : '';
  const dias = (iso) => iso ? Math.max(0, Math.round((Date.now() - new Date(iso.slice(0, 10) + 'T12:00:00')) / 864e5)) : 0;
  let desliga = null;
  const ehAdm = () => typeof ROLE !== 'undefined' && ROLE === 'admin';

  async function entrar() {
    const raiz = $('#fcRaiz');
    raiz.innerHTML = '<div class="lic-empty">Conferindo o certificado do contador…</div>';
    const est = await window.fiscocont.fisconforme.estado();
    if (est && est.error) { raiz.innerHTML = `<div class="lic-empty">${e(est.error)}</div>`; return; }
    F.est = est; F.semCert = false;
    if (!est.certs.length) {
      // sem o e-CPF neste computador: não consulta nada no portal, mas mostra a última leitura salva (se houver)
      const d = await window.fiscocont.fisconforme.dados();
      if (d && !d.error && d.meta) { F.semCert = true; F.d = d; desenhar(); return; }
      semCertificado(); return;
    }
    if (!est.escolhido) { semCertificado(); return; }
    if (!desliga) desliga = window.fiscocont.fisconforme.onProgresso((p) => {
      const el = $('#fcProg'); if (!el) return;
      el.hidden = !!p.fim; el.querySelector('span').textContent = p.txt || '';
    });
    await carregar();
  }

  // ------------------------------------------------------------------ sem certificado: avisa antes de qualquer coisa
  function semCertificado() {
    const est = F.est;
    $('#fcRaiz').innerHTML = `<div class="fc-hd"><div><span class="fc-tag">SEFIN-RO · FISCONFORME</span><h2>Notificações do Fisconforme</h2></div></div>
      <div class="fc-alerta"><b>${est.certs.length ? 'Escolha o certificado do contador' : 'Certificado do contador não encontrado neste computador'}</b>
      ${est.certs.length
        ? `<p>Há mais de um e-CPF instalado no Windows. Escolha o do contador que acessa o Fisconforme:</p>
           <div class="fc-certs">${est.certs.map((c) => `<button class="fc-cert" data-cpf="${e(c.cpf)}"><b>${e(c.nome)}</b><small>CPF ${fmtCpf(c.cpf)} · vence ${dBr(c.vence)}${c.vencido ? ' · <em>vencido</em>' : ''}</small></button>`).join('')}</div>`
        : `<p>O robô entra no portal da SEFIN com o <b>e-CPF do contador</b> instalado no Windows (certificado A1). Nenhum e-CPF foi encontrado aqui${est.aviso ? ` (${e(est.aviso)})` : ''}.</p>
           <p>Instale o certificado neste computador (duplo clique no arquivo .pfx → “Usuário atual”) e abra o módulo de novo. Nada foi consultado.</p>`}
      <button class="act inv-export" id="fcRever">Conferir de novo</button></div>`;
    $('#fcRever').onclick = entrar;
    document.querySelectorAll('.fc-cert').forEach((b) => b.onclick = async () => {
      const c = F.est.certs.find((x) => x.cpf === b.dataset.cpf);
      if (c && c.vencido) { toast('Esse certificado está vencido.', true); return; }
      await window.fiscocont.fisconforme.escolherCert(b.dataset.cpf); entrar();
    });
  }

  async function carregar() {
    const d = await window.fiscocont.fisconforme.dados();
    if (d && d.error) { toast(d.error, true); return; }
    F.d = d; desenhar();
  }

  function contar(notif, meta) {
    const c = { pendente: 0, contestado: 0, indeferido: 0, resolvido: 0, fora: 0, novas: 0, resMes: 0 };
    const mes = new Date().toISOString().slice(0, 7);
    const ult = meta ? meta.ultimaLeitura : '';
    const prim = meta ? meta.primeiraLeituraGeral : '';
    notif.forEach((n) => {
      c[n.status] = (c[n.status] || 0) + 1;
      if (ult && n.primeiraLeitura === ult && ult !== prim && n.status !== 'fora') c.novas++;
      if ((n.status === 'resolvido' || n.status === 'fora') && (n.statusDesde || '').slice(0, 7) === mes && n.primeiraVez !== n.statusDesde) c.resMes++;
    });
    return c;
  }
  const ehNova = (n) => F.d.meta && n.primeiraLeitura === F.d.meta.ultimaLeitura && F.d.meta.ultimaLeitura !== F.d.meta.primeiraLeituraGeral;

  function desenhar() {
    const { notif, meta } = F.d;
    const est = F.est.escolhido || (meta && meta.contador) || { nome: 'contador', cpf: '' };
    const adm = ehAdm();
    const c = contar(notif, meta);
    const pend = notif.filter((n) => n.status === 'pendente');
    const empsPend = new Set(pend.map((n) => n.cnpj || n.nome)).size;
    const porMalha = {}; pend.forEach((n) => { porMalha[n.desc] = (porMalha[n.desc] || 0) + 1; });
    const malhasOrd = Object.entries(porMalha).sort((a, b) => b[1] - a[1]);
    const topM = malhasOrd.slice(0, 6), resto = malhasOrd.slice(6).reduce((s, x) => s + x[1], 0);
    const mx = Math.max(1, ...malhasOrd.map((x) => x[1]));
    const porEmp = {};
    notif.forEach((n) => { if (n.status === 'fora' || n.status === 'resolvido') return; const k = n.cnpj || n.nome;
      const g = porEmp[k] = porEmp[k] || { nome: n.nome, cnpj: n.cnpj, ie: n.ie, pe: 0, co: 0, in: 0, nv: 0 };
      if (n.status === 'pendente') g.pe++; if (n.status === 'contestado') g.co++; if (n.status === 'indeferido') g.in++; if (ehNova(n)) g.nv++; });
    const topE = Object.values(porEmp).sort((a, b) => (b.pe + b.in) - (a.pe + a.in)).slice(0, 6);
    const empresas = [...new Map(notif.map((n) => [n.cnpj || n.nome, n.nome])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
    const malhas = [...new Set(notif.map((n) => n.desc))].sort();
    const t = F.busca.toLowerCase();
    const vis = notif.filter((n) => (F.filtro === 'novas' ? ehNova(n) : n.status === F.filtro)
      && (!F.emp || (n.cnpj || n.nome) === F.emp) && (!F.malha || n.desc === F.malha)
      && (!t || `${n.nome} ${n.cnpj} ${n.ie} ${n.codigo} ${n.desc}`.toLowerCase().includes(t)))
      .sort((a, b) => (a.primeiraVez || '').localeCompare(b.primeiraVez || '') || a.nome.localeCompare(b.nome));
    const chip = (k, rot, n) => `<button class="fc-f${F.filtro === k ? ' on' : ''}" data-f="${k}">${rot} (${n})</button>`;
    $('#fcRaiz').innerHTML = `
      <div class="fc-hd"><div><span class="fc-tag">SEFIN-RO · FISCONFORME</span><h2>Notificações do Fisconforme</h2>
        <p>Todas as empresas vinculadas ao contador · ${e(est.nome || 'contador')}${est.cpf ? ` (e-CPF ${fmtCpf(est.cpf)})` : ''} · o robô lê só as listas, sem abrir a notificação</p></div>
        <div class="fc-acts">${meta ? `<span class="fc-pill">● Última leitura ${e(new Date(meta.ultimaLeitura).toLocaleString('pt-BR').slice(0, 17).replace(',', ''))}${meta.por ? ' · ' + e(meta.por) : ''}</span>` : ''}
          ${adm ? `<label class="fc-chk" title="Abre a janela do navegador do robô para acompanhar a entrada no portal (ajuda no primeiro uso)"><input type="checkbox" id="fcVer"${F.est.mostrarJanela ? ' checked' : ''}> Mostrar o navegador do robô</label>
          <button class="act inv-export" id="fcPortal">Abrir o portal ↗</button>` : ''}
          ${meta ? '<button class="act inv-export" id="fcHtml">Exportar HTML</button><button class="act inv-export" id="fcPdf">Exportar PDF</button>' : ''}
          <button class="act inv-export fc-go" id="fcLer"${F.semCert ? ' disabled title="Precisa do e-CPF do contador instalado neste computador"' : ''}>▶ Ler notificações</button></div></div>
      ${F.semCert ? `<div class="fc-alerta"><b>O certificado do contador não está instalado neste computador.</b> Você está vendo a última leitura salva. Para ler de novo ou visualizar uma notificação no portal, use um computador com o e-CPF do contador instalado. Nada foi consultado.</div>` : ''}
      <div class="fc-prog" id="fcProg" hidden><i></i><span></span></div>
      ${!meta ? `<div class="fc-vazio"><b>Nenhuma leitura ainda.</b> Clique em “Ler notificações”: o robô entra no portal com o e-CPF do contador e lê as listas de pendentes, contestadas, indeferidas e resolvidas de todas as empresas (leva alguns minutos).</div>` : `
      <div class="fc-k">
        <div style="--c:#d97706"><b>${c.pendente}</b><span>Pendentes</span><small>em ${empsPend} empresa(s)</small></div>
        <div style="--c:#0e7490"><b>${c.novas}</b><span>Novas na última leitura</span><small>apareceram desde a leitura anterior</small></div>
        <div style="--c:#4338ca"><b>${c.contestado}</b><span>Contestadas</span><small>aguardando decisão da SEFIN</small></div>
        <div style="--c:#dc2626"><b>${c.indeferido}</b><span>Indeferidas</span><small>contestação negada · regularizar</small></div>
        <div style="--c:#059669"><b>${c.resMes}</b><span>Resolvidas no mês</span><small>saíram de pendente este mês</small></div>
      </div>
      <div class="fc-g2">
        <div class="fc-card"><h3>Pendentes por malha</h3>${topM.map(([m, n]) => `<div class="fc-br" data-m="${e(m)}"><span>${e(m)}</span><i><em style="width:${(n / mx * 100).toFixed(1)}%"></em></i><b>${n}</b></div>`).join('') || '<p class="fc-sub">Nenhuma pendente.</p>'}
          ${resto ? `<div class="fc-br"><span>Outras (${malhasOrd.length - 6} malhas)</span><i><em style="width:${(resto / mx * 100).toFixed(1)}%"></em></i><b>${resto}</b></div>` : ''}</div>
        <div class="fc-card"><h3>Empresas com mais pendências</h3>${topE.map((g) => `<div class="fc-emp" data-e="${e(g.cnpj || g.nome)}"><div><b>${e(g.nome)}</b><small>${g.cnpj ? 'CNPJ ' + fmtCnpj(g.cnpj) + ' · ' : ''}IE ${e(g.ie)}</small></div>
          <div class="fc-chips">${g.pe ? `<span class="fc-c pe">${g.pe} pendente(s)</span>` : ''}${g.nv ? `<span class="fc-c nv">${g.nv} nova(s)</span>` : ''}${g.co ? `<span class="fc-c co">${g.co} contestada(s)</span>` : ''}${g.in ? `<span class="fc-c in">${g.in} indeferida(s)</span>` : ''}</div></div>`).join('') || '<p class="fc-sub">Nenhuma empresa com pendência.</p>'}</div>
      </div>
      <div class="fc-card">
        <h3>Notificações</h3>
        <div class="fc-flt">${chip('pendente', 'Pendentes', c.pendente)}${chip('novas', 'Novas', c.novas)}${chip('contestado', 'Contestadas', c.contestado)}${chip('indeferido', 'Indeferidas', c.indeferido)}${chip('resolvido', 'Resolvidas', c.resolvido)}${c.fora ? chip('fora', 'Saíram das listas', c.fora) : ''}
          <select id="fcEmp" class="fc-sel"><option value="">Todas as empresas</option>${empresas.map(([k, n]) => `<option value="${e(k)}"${F.emp === k ? ' selected' : ''}>${e(n)}</option>`).join('')}</select>
          <select id="fcMalha" class="fc-sel"><option value="">Todas as malhas</option>${malhas.map((m) => `<option${F.malha === m ? ' selected' : ''}>${e(m)}</option>`).join('')}</select>
          <input id="fcBusca" class="fc-sel" placeholder="Buscar empresa, CNPJ, IE ou código" value="${e(F.busca)}"></div>
        <table class="fc-tab"><thead><tr><th>Empresa</th><th>Malha / descrição</th><th>Período</th><th>Código</th><th>Situação</th><th>Encontrada pelo robô</th><th></th></tr></thead><tbody>
        ${vis.slice(0, F.mostrar).map((n) => linha(n)).join('') || '<tr><td colspan="7" class="fc-sub" style="text-align:center;padding:18px">Nada neste filtro.</td></tr>'}
        </tbody></table>
        ${vis.length > F.mostrar ? `<button class="act inv-export" id="fcMais" style="margin:10px auto;display:block">Mostrar mais (${vis.length - F.mostrar})</button>` : ''}
        <div class="fc-aviso">⚠ O robô lê só as listas do portal e <b>nunca abre a notificação sozinho</b>: abrir o conteúdo conta como ciência e começa o prazo (Decreto 23.856/2019, art. 3º, § 3º). “Entenda esta malha” explica sem abrir nada. “Visualizar” abre a notificação no portal — <b>dá ciência</b> — e só roda depois da sua confirmação.</div>
      </div>`}`;
    ligar(vis);
  }

  function linha(n) {
    const [rot, cls] = ST[n.status] || [n.status, ''];
    const nova = ehNova(n) ? '<span class="fc-c nv">Nova</span> ' : '';
    const d = dias(n.primeiraVez);
    const ab = F.aberto === n.codigo;
    const expl = (F.d.explicMalha[(n.malha || '')] || {}).texto;
    return `<tr class="${ab ? 'fc-on' : ''}"><td><b>${e(n.nome)}</b><small>${n.cnpj ? 'CNPJ ' + fmtCnpj(n.cnpj) + ' · ' : ''}IE ${e(n.ie)}</small></td>
      <td>${e(n.desc)}${n.cienciaEm ? `<small class="fc-ci">Ciência em ${dBr(n.cienciaEm)}${n.prazo ? ` · prazo ${e(n.prazo)}` : ''}</small>` : ''}</td>
      <td>${per(n.periodo)}</td><td>${e(n.codigo)}</td><td>${nova}<span class="fc-c ${cls}">${rot}</span></td>
      <td>${dBr(n.primeiraVez)}<small>${d === 0 ? 'hoje' : `há ${d} dia${d > 1 ? 's' : ''}`}</small></td>
      <td class="fc-ac"><button class="fc-b" data-x="${e(n.codigo)}">${ab ? 'Fechar' : 'Entenda esta malha'}</button>
        ${n.detalhe ? `<button class="fc-b" data-v="${e(n.codigo)}" data-ja="1">Ver notificação</button>` : `<button class="fc-b fc-bv" data-v="${e(n.codigo)}"${F.semCert ? ' disabled title="Precisa do e-CPF do contador instalado neste computador"' : ''}>Visualizar</button>`}</td></tr>
      ${ab ? `<tr class="fc-det"><td colspan="7">
        ${n.detalhe ? `<div class="fc-box"><h4>Notificação (aberta em ${e(n.cienciaEm || '')}${n.cienciaPor ? ' por ' + e(n.cienciaPor) : ''})</h4><pre>${e(n.detalhe)}</pre></div>` : ''}
        <div class="fc-box"><h4>${n.explicacao ? 'Explicação desta notificação' : 'Entenda esta malha'}</h4><div class="fc-ex" id="fcEx">${n.explicacao ? fmt(n.explicacao) : (expl ? fmt(expl) : '<span class="fc-sub">Preparando a explicação…</span>')}</div></div>
      </td></tr>` : ''}`;
  }
  const fmt = (t) => e(t).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\n{2,}/g, '<br><br>').replace(/\n/g, '<br>');

  function ligar(vis) {
    const q = (s) => $('#fcRaiz').querySelectorAll(s);
    $('#fcLer').onclick = ler;
    if ($('#fcPortal')) $('#fcPortal').onclick = () => window.fiscocont.fisconforme.abrirPortal();
    if ($('#fcVer')) $('#fcVer').onchange = async (ev) => { await window.fiscocont.fisconforme.mostrarJanela(ev.target.checked); F.est.mostrarJanela = ev.target.checked; };
    if (!F.d.meta) return;
    $('#fcHtml').onclick = () => exportar('html');
    $('#fcPdf').onclick = () => exportar('pdf');
    q('.fc-f').forEach((b) => b.onclick = () => { F.filtro = b.dataset.f; F.mostrar = 120; desenhar(); });
    $('#fcEmp').onchange = (ev) => { F.emp = ev.target.value; desenhar(); };
    $('#fcMalha').onchange = (ev) => { F.malha = ev.target.value; desenhar(); };
    $('#fcBusca').onchange = (ev) => { F.busca = ev.target.value; desenhar(); };
    q('.fc-br[data-m]').forEach((b) => b.onclick = () => { F.malha = b.dataset.m; F.filtro = 'pendente'; desenhar(); });
    q('.fc-emp').forEach((b) => b.onclick = () => { F.emp = b.dataset.e; desenhar(); });
    const mais = $('#fcMais'); if (mais) mais.onclick = () => { F.mostrar += 200; desenhar(); };
    q('[data-x]').forEach((b) => b.onclick = () => abrir(b.dataset.x));
    q('[data-v]').forEach((b) => b.onclick = () => (b.dataset.ja ? abrir(b.dataset.v) : visualizar(b.dataset.v)));
  }

  async function abrir(cod) {
    if (F.aberto === cod) { F.aberto = ''; desenhar(); return; }
    F.aberto = cod; desenhar();
    const n = F.d.notif.find((x) => x.codigo === cod);
    if (!n || n.explicacao || (F.d.explicMalha[n.malha] || {}).texto) return;
    const r = await window.fiscocont.fisconforme.explicarMalha(n.malha, n.desc);
    if (r && r.error) { const el = $('#fcEx'); if (el) el.innerHTML = `<span class="fc-sub">${e(r.error)}</span>`; return; }
    F.d.explicMalha[n.malha || ''] = { texto: r.texto };
    if (F.aberto === cod) desenhar();
  }

  async function visualizar(cod) {
    const n = F.d.notif.find((x) => x.codigo === cod);
    if (!n) return;
    if (!confirm(`Abrir a notificação ${cod} no portal da SEFIN?\n\n${n.nome}\n${n.desc} · ${per(n.periodo)}\n\n`
      + 'ATENÇÃO: abrir o conteúdo conta como CIÊNCIA da notificação e o prazo para regularizar começa a contar a partir de hoje '
      + '(Decreto 23.856/2019, art. 3º, § 3º).\n\nContinuar?')) return;
    const prog = $('#fcProg'); prog.hidden = false; prog.querySelector('span').textContent = 'Abrindo a notificação no portal…';
    const r = await window.fiscocont.fisconforme.visualizar(cod);
    prog.hidden = true;
    if (r && r.error) { toast(r.error, true); return; }
    Object.assign(n, { detalhe: r.detalhe, cienciaEm: r.cienciaEm, prazo: r.prazo, explicacao: r.explicacao });
    F.aberto = cod; desenhar();
  }

  // ------------------------------------------------------------------ relatório (HTML com movimento ou PDF)
  // Respeita os filtros de empresa e malha da tela. Traz pendentes, contestadas e indeferidas.
  function relatorio() {
    const { notif, meta } = F.d;
    const base = notif.filter((n) => (!F.emp || (n.cnpj || n.nome) === F.emp) && (!F.malha || n.desc === F.malha));
    const ativos = base.filter((n) => ['pendente', 'contestado', 'indeferido'].includes(n.status));
    const c = { pendente: 0, contestado: 0, indeferido: 0 };
    ativos.forEach((n) => { c[n.status]++; });
    const novas = ativos.filter(ehNova).length;
    const porM = {}; ativos.forEach((n) => { porM[n.desc] = (porM[n.desc] || 0) + 1; });
    const ms = Object.entries(porM).sort((a, b) => b[1] - a[1]);
    const mx = Math.max(1, ...ms.map((x) => x[1]));
    const porE = new Map();
    ativos.forEach((n) => { const k = n.cnpj || n.nome; if (!porE.has(k)) porE.set(k, { nome: n.nome, cnpj: n.cnpj, ie: n.ie, l: [] }); porE.get(k).l.push(n); });
    const emps = [...porE.values()].sort((a, b) => b.l.length - a.l.length || a.nome.localeCompare(b.nome));
    const so1 = emps.length === 1 ? emps[0] : null;
    const titulo = so1 ? so1.nome : 'Todas as empresas';
    const quando = meta ? new Date(meta.ultimaLeitura).toLocaleString('pt-BR').slice(0, 17).replace(',', '') : '';
    const rotST = { pendente: 'Pendente', contestado: 'Contestada', indeferido: 'Indeferida' };
    const css = `*{box-sizing:border-box}body{margin:0;font-family:'Segoe UI',Inter,Arial,sans-serif;background:#f3f5fb;color:#141b2d;padding:28px 32px}
      .hd{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:3px solid #0369a1;padding-bottom:14px;margin-bottom:18px}
      .tag{font-size:11px;font-weight:800;letter-spacing:.08em;color:#0369a1;background:#e0f2fe;padding:3px 10px;border-radius:20px}
      h1{margin:8px 0 2px;font-size:22px}.sub{color:#5a6785;font-size:12.5px}.esc{text-align:right;font-size:12px;color:#5a6785}.esc b{display:block;font-size:14px;color:#1f2a5a}
      .k{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}
      .k div{background:#fff;border-radius:14px;padding:14px 16px;border-top:4px solid var(--c);box-shadow:0 10px 26px -18px rgba(30,40,90,.35);animation:sobe .6s both}
      .k div:nth-child(2){animation-delay:.08s}.k div:nth-child(3){animation-delay:.16s}.k div:nth-child(4){animation-delay:.24s}
      .k b{display:block;font-size:28px;color:var(--c)}.k span{font-size:12.5px;font-weight:600;color:#5a6785}
      .card{background:#fff;border-radius:16px;padding:16px 18px;margin-bottom:16px;box-shadow:0 10px 26px -18px rgba(30,40,90,.35);animation:sobe .6s .2s both;break-inside:avoid}
      h2{font-size:15px;margin:0 0 10px;color:#0c4a6e}
      .br{display:grid;grid-template-columns:320px 1fr 40px;gap:10px;align-items:center;font-size:12.5px;margin:7px 0}
      .br i{height:10px;background:#eef0f6;border-radius:6px;overflow:hidden;display:block}.br em{display:block;height:100%;border-radius:6px;background:linear-gradient(90deg,#38bdf8,#0369a1);animation:enche 1.1s .3s ease-out both}
      .br b{text-align:right}
      .emp{margin-top:14px}.emp h3,.emp small{display:block;break-after:avoid}tr{break-inside:avoid}thead{display:table-header-group}.lista{break-inside:auto}.emp h3{margin:0;font-size:13.5px}.emp small{color:#5a6785;font-size:11.5px}
      table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px;margin-top:6px}th{text-align:left;font-size:10.5px;color:#8a93ad;text-transform:uppercase;padding:6px;border-bottom:1.5px solid #e5e9f1}
      td{padding:7px 6px;border-bottom:1px solid #eef0f6}
      .s{font-weight:800;font-size:11px;padding:2px 8px;border-radius:7px}.s.pendente{background:#fff7e6;color:#9a5b00}.s.contestado{background:#eef2ff;color:#4338ca}.s.indeferido{background:#fef2f2;color:#b91c1c}
      .nv{background:#ecfeff;color:#0e7490;font-weight:800;font-size:11px;padding:2px 8px;border-radius:7px;margin-left:4px}
      .rod{margin-top:18px;font-size:11px;color:#8a93ad;line-height:1.5}
      @keyframes sobe{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}@keyframes enche{from{width:0}}
      @media print{body{background:#fff;padding:0}.card,.k div{box-shadow:none;border:1px solid #e5e9f1}}`;
    const conta = `<script>document.querySelectorAll('[data-n]').forEach(function(el){if(document.body.dataset.pdf){return}var f=+el.dataset.n,t0=null;
      function p(t){if(!t0)t0=t;var k=Math.min(1,(t-t0)/900);el.textContent=Math.round(f*(1-Math.pow(1-k,3)));if(k<1)requestAnimationFrame(p)}el.textContent='0';requestAnimationFrame(p)})<\/script>`;
    return `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Fisconforme · ${e(titulo)}</title><style>${css}</style></head><body>
      <div class="hd"><div><span class="tag">SEFIN-RO · FISCONFORME</span><h1>Notificações do Fisconforme · ${e(titulo)}</h1>
        <div class="sub">${so1 ? `${so1.cnpj ? 'CNPJ ' + fmtCnpj(so1.cnpj) + ' · ' : ''}IE ${e(so1.ie)} · ` : `${emps.length} empresa(s) · `}${F.malha ? 'Malha: ' + e(F.malha) + ' · ' : ''}posição de ${e(quando)}</div></div>
        <div class="esc"><b>Liddera | Inteligência em Negócios</b>Decreto 23.856/2019 (SEFIN-RO)</div></div>
      <div class="k"><div style="--c:#d97706"><b data-n="${c.pendente}">${c.pendente}</b><span>Pendentes</span></div><div style="--c:#0e7490"><b data-n="${novas}">${novas}</b><span>Novas na última leitura</span></div>
        <div style="--c:#4338ca"><b data-n="${c.contestado}">${c.contestado}</b><span>Contestadas</span></div><div style="--c:#dc2626"><b data-n="${c.indeferido}">${c.indeferido}</b><span>Indeferidas</span></div></div>
      ${ms.length ? `<div class="card"><h2>Por malha</h2>${ms.map(([m, n]) => `<div class="br"><span>${e(m)}</span><i><em style="width:${(n / mx * 100).toFixed(1)}%"></em></i><b>${n}</b></div>`).join('')}</div>` : ''}
      <div class="card lista"><h2>Notificações por empresa</h2>${emps.map((g) => `<div class="emp"><h3>${e(g.nome)}</h3><small>${g.cnpj ? 'CNPJ ' + fmtCnpj(g.cnpj) + ' · ' : ''}IE ${e(g.ie)} · ${g.l.length} notificação(ões)</small>
        <table><colgroup><col style="width:9%"><col style="width:37%"><col style="width:9%"><col style="width:14%"><col style="width:12%"><col style="width:19%"></colgroup><thead><tr><th>Código</th><th>Malha / descrição</th><th>Período</th><th>Situação</th><th>Encontrada em</th><th>Ciência / prazo</th></tr></thead>
        ${g.l.sort((a, b) => (a.periodo || '').localeCompare(b.periodo || '')).map((n) => `<tr><td>${e(n.codigo)}</td><td>${e(n.desc)}</td><td>${per(n.periodo)}</td>
          <td><span class="s ${n.status}">${rotST[n.status]}</span>${ehNova(n) ? '<span class="nv">Nova</span>' : ''}</td><td>${dBr(n.primeiraVez)}</td>
          <td>${n.cienciaEm ? dBr(n.cienciaEm) + (n.prazo ? ' · prazo ' + e(n.prazo) : '') : '—'}</td></tr>`).join('')}</table></div>`).join('') || '<p>Nenhuma notificação ativa.</p>'}</div>
      <div class="rod">Pagar ou regularizar dentro do prazo exclui a notificação e afasta a multa moratória (Decreto 23.856/2019, art. 3º, §§ 1º e 2º). A notificação é considerada recebida quando o conteúdo é aberto no portal ou 15 dias após o aviso no Domicílio Eletrônico Tributário (art. 3º, §§ 3º e 4º).<br>Gerado pelo FiscoCont+ em ${new Date().toLocaleString('pt-BR').slice(0, 17).replace(',', '')}.</div>
      ${conta}</body></html>`;
  }
  async function exportar(fmt) {
    const html = relatorio();
    const nomeEmp = F.emp ? ((F.d.notif.find((n) => (n.cnpj || n.nome) === F.emp) || {}).nome || 'empresa') : 'todas as empresas';
    const r = await window.fiscocont.fisconforme.exportar(html, fmt, `Fisconforme - ${nomeEmp} - ${new Date().toLocaleDateString('pt-BR').replace(/\//g, '-')}`);
    if (r && r.error) toast(r.error, true); else if (r && r.ok) toast(fmt === 'pdf' ? 'PDF salvo.' : 'HTML salvo.');
  }

  async function ler() {
    const b = $('#fcLer'); b.disabled = true; b.textContent = 'Lendo…';
    const prog = $('#fcProg'); if (prog) { prog.hidden = false; prog.querySelector('span').textContent = 'Iniciando…'; }
    const r = await window.fiscocont.fisconforme.ler();
    b.disabled = false; b.textContent = '▶ Ler notificações';
    if (prog) prog.hidden = true;
    if (r && r.error) {
      toast(r.error, true);
      if (/fisconforme_log/.test(r.error) && ehAdm() && confirm('Abrir a pasta com o print e o passo a passo do robô?')) window.fiscocont.fisconforme.pastaDados();
      return;
    }
    toast(`Leitura concluída: ${r.contagens.pendente} pendente(s)${r.novas ? ` · ${r.novas} nova(s)` : ''}.`);
    await carregar();
  }

  window._fiscEntrar = entrar;
})();

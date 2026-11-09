'use strict';
// Débitos e DARE · SEFIN-RO — débitos em aberto do exercício de todas as empresas vinculadas ao contador, com a geração do
// DARE (data de pagamento escolhida aqui) e do extrato, salvos na pasta da empresa. A tela fala sempre em "o sistema".
// Usa o mesmo e-CPF do contador escolhido no Fisconforme.
(function () {
  const e = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const R = { ano: String(new Date().getFullYear()), d: null, filtro: 'todos', emp: '', rec: '', busca: '', dia: '', grp: '', anim: false, sel: new Set(), mostrar: 150, semCert: false, est: null };
  const brl = (v) => (Number(v) || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  const fmtCnpj = (c) => String(c || '').replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
  const hoje0 = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
  const dt = (br) => { const m = String(br || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/); return m ? new Date(+m[3], +m[2] - 1, +m[1]) : null; };
  const br = (d) => `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;
  const DSEM = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];
  const MES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
  const chave = (x) => `${x.ie}|${x.nr}|${x.parc || '00'}`;
  const ICONE = '<svg viewBox="0 0 24 24"><rect x="4" y="3" width="16" height="18" rx="2.5" fill="#fff"/><path d="M8 8h8M8 12h5M8 16h8" stroke="#1d4ed8" stroke-width="1.8" stroke-linecap="round"/></svg>';
  let desliga = null;

  // ------------------------------------------------------------------ entrada
  async function entrar() {
    const raiz = $('#drRaiz');
    raiz.innerHTML = '<div class="lic-empty">Conferindo o certificado do contador…</div>';
    const est = await window.fiscocont.fisconforme.estado();
    if (est && est.error) { raiz.innerHTML = `<div class="lic-empty">${e(est.error)}</div>`; return; }
    R.est = est; R.semCert = !est.escolhido;
    if (!desliga) desliga = window.fiscocont.dare.onProgresso((p) => {
      const el = $('#drProg'); if (!el) return;
      el.hidden = !!p.fim; el.querySelector('span').textContent = p.txt || '';
      const mb = $('#drMProg'); if (mb && p.txt) mb.textContent = p.txt;
    });
    await carregar();
  }

  async function carregar() {
    const d = await window.fiscocont.dare.dados(R.ano);
    if (d && d.error) { $('#drRaiz').innerHTML = `<div class="lic-empty">${e(d.error)}</div>`; return; }
    R.d = d; R.anim = true;
    badge();
    if (R.semCert && !d.meta) { semCertificado(); return; }
    desenhar();
  }

  function cabecalho(dir) {
    const est = (R.est && R.est.escolhido) || (R.d && R.d.meta && R.d.meta.contador) || { nome: 'contador' };
    return `<div class="fc-hd"><div class="fc-tit"><div class="dr-logo">${ICONE}</div><div><span class="fc-tag">SEFIN-RO · PORTAL DO CONTRIBUINTE</span><h2>Débitos e DARE</h2>
      <p>Débitos em aberto de todas as empresas vinculadas ao contador · ${e(est.nome || 'contador')} (e-CPF) · exercício ${e(R.ano)}</p></div></div>${dir || ''}</div>`;
  }

  function semCertificado() {
    const est = R.est;
    $('#drRaiz').innerHTML = `${cabecalho()}<div class="fc-alerta"><b>${est.certs.length ? 'Escolha o certificado do contador no Fisconforme' : 'Certificado do contador não encontrado neste computador'}</b>
      <p>${est.certs.length ? 'Há mais de um e-CPF instalado. Abra o módulo Fisconforme, escolha o do contador e volte aqui.'
        : 'O sistema consulta o Portal do Contribuinte com o <b>e-CPF do contador</b> instalado no Windows. Instale o certificado neste computador e abra o módulo de novo.'} Nada foi consultado.</p>
      <button class="act inv-export" id="drRever">Conferir de novo</button></div>`;
    $('#drRever').onclick = entrar;
  }

  // ------------------------------------------------------------------ dados → linhas
  function linhas() {
    const out = [];
    const h = hoje0();
    (R.d.emps || []).forEach((m) => (m.debitos || []).forEach((x) => {
      const v = dt(x.venc);
      const dias = v ? Math.round((v - h) / 864e5) : null;
      const g = (m.gerados || {})[`${x.nr}_${x.parc || '00'}`] || null;
      out.push({ ...x, ie: m.ie, nome: m.nome, razao: m.razao, cnpj: m.cnpj, ano: m.ano, dias, ger: g });
    }));
    return out.sort((a, b) => (a.dias ?? 9e9) - (b.dias ?? 9e9) || a.nome.localeCompare(b.nome));
  }
  const sit = (x) => x.dias == null ? ['—', 'fo'] : x.dias < 0 ? [`Vencido · ${-x.dias} dia${x.dias === -1 ? '' : 's'}`, 'in']
    : x.dias === 0 ? ['Vence hoje', 'in'] : x.dias <= 7 ? [`Vence em ${x.dias} dia${x.dias === 1 ? '' : 's'}`, 'pe'] : ['A vencer', 'ok'];
  const passa = (x) => {
    if (R.filtro === 'venc' && !(x.dias < 0)) return false;
    if (R.filtro === 'sete' && !(x.dias >= 0 && x.dias <= 7)) return false;
    if (R.filtro === 'avencer' && !(x.dias > 7)) return false;
    if (R.filtro === 'gerados' && !x.ger) return false;
    if (R.dia && x.venc !== R.dia) return false;
    if (R.grp && R._raiz && R._raiz(x) !== R.grp) return false;
    if (R.emp && x.ie !== R.emp) return false;
    if (R.rec && x.rec !== R.rec) return false;
    if (R.busca) { const b = R.busca.toLowerCase(); if (![x.nome, x.ie, x.nr, x.comp, x.cnpj].join(' ').toLowerCase().includes(b)) return false; }
    return true;
  };

  // ------------------------------------------------------------------ painel
  function desenhar() {
    const { meta, emps } = R.d;
    const L = linhas();
    const soma = (a) => a.reduce((s, x) => s + (x.valorN || 0), 0);
    const venc = L.filter((x) => x.dias < 0), sete = L.filter((x) => x.dias >= 0 && x.dias <= 7), avencer = L.filter((x) => x.dias > 7);
    const empsDeb = new Set(L.map((x) => x.ie));
    const mesAt = new Date().toISOString().slice(0, 7);
    const gerMes = L.filter((x) => x.ger && String(x.ger.em || '').slice(0, 7) === mesAt).length;
    const falhas = (emps || []).filter((m) => m.erro);
    const quando = meta ? new Date(meta.ultimaLeitura).toLocaleString('pt-BR').slice(0, 17).replace(',', '') : '';
    const anos = [0, 1, 2].map((k) => String(new Date().getFullYear() - k));
    const vis = L.filter(passa);
    const recs = [...new Set(L.map((x) => x.rec))].sort();
    const listaEmp = [...new Map(L.map((x) => [x.ie, x.nome])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
    const selTot = soma(L.filter((x) => R.sel.has(chave(x))));
    const podeSefin = !R.semCert;
    const anima = R.anim; R.anim = false;                      // movimento só ao abrir/atualizar, não a cada filtro
    const est = (R.est && R.est.escolhido) || (meta && meta.contador) || { nome: 'contador' };

    // vencidos por tempo de atraso
    const faixas = [['até 30 dias', 0, 30, '#fbbf24'], ['31 a 60 dias', 31, 60, '#fb923c'], ['61 a 90 dias', 61, 90, '#f43f5e'], ['mais de 90 dias', 91, 1e9, '#9f1239']]
      .map(([t, a, b, c]) => { const l = venc.filter((x) => -x.dias >= a && -x.dias <= b); return { t, c, v: soma(l), n: l.length, a, b }; });
    const totV = Math.max(0.01, soma(venc));

    // ranking: matriz e filiais juntas (mesma raiz de CNPJ; sem CNPJ, mesmo nome)
    const raiz = (x) => (x.cnpj && x.cnpj.length >= 8 ? x.cnpj.slice(0, 8) : 'N' + String(x.nome || '').toUpperCase().replace(/[^A-Z0-9]/g, ''));
    const grupos = new Map();
    L.forEach((x) => {
      const k = raiz(x);
      if (!grupos.has(k)) grupos.set(k, { k, nome: x.nome, ies: new Set(), v: 0, n: 0, vencido: 0, prox: null });
      const g = grupos.get(k); g.ies.add(x.ie); g.v += x.valorN || 0; g.n++;
      if (x.dias < 0) g.vencido += x.valorN || 0;
      else if (x.dias != null && (!g.prox || x.dias < g.prox.dias)) g.prox = x;
      if (/^\d{8}0001/.test(x.cnpj || '')) g.nome = x.nome;      // nome da matriz
    });
    const topG = [...grupos.values()].sort((a, b) => b.v - a.v).slice(0, 8);
    const mxG = Math.max(1, ...topG.map((g) => g.v));

    // próximos 30 dias: valor por dia de vencimento
    const h0 = hoje0();
    const dias30 = Array.from({ length: 30 }, (_, i) => { const d = new Date(h0.getTime() + i * 864e5); return { d, s: br(d), v: 0, n: 0 }; });
    const porDia = new Map(dias30.map((x) => [x.s, x]));
    L.forEach((x) => { const o = porDia.get(x.venc); if (o) { o.v += x.valorN || 0; o.n++; } });
    const mxD = Math.max(1, ...dias30.map((x) => x.v));
    const picos = new Set([...dias30].filter((x) => x.v > 0).sort((a, b) => b.v - a.v).slice(0, 3).map((x) => x.s));
    const tot30 = dias30.reduce((s, x) => s + x.v, 0);

    const cnt = (v, moeda = true) => anima ? `data-cnt="${v}"${moeda ? '' : ' data-int="1"'}` : '';
    const heroTopo = `<div class="dr-hero${anima ? ' dr-in' : ''}">
      <div class="dr-hl"><div class="dr-ht"><div class="dr-hico">${ICONE}</div><div><span>SEFIN-RO · DÉBITOS E DARE · EXERCÍCIO ${e(R.ano)}</span>
        <p>${meta ? `Total em aberto nas ${meta.empresas || (emps || []).length} empresas consultadas` : 'Débitos em aberto das empresas vinculadas ao contador'} · ${e(est.nome || 'contador')} (e-CPF)</p></div></div>
        ${meta ? `<div class="dr-big"><b ${cnt(soma(L))}>${brl(soma(L))}</b><small>${L.length} débito(s) · ${empsDeb.size} empresa(s)</small></div>
        <div class="dr-hk">
          <button data-f="venc" class="${R.filtro === 'venc' ? 'on' : ''}"><b ${cnt(soma(venc))}>${brl(soma(venc))}</b><span>Vencidos · ${venc.length}</span></button>
          <button data-f="sete" class="${R.filtro === 'sete' ? 'on' : ''}"><b ${cnt(soma(sete))}>${brl(soma(sete))}</b><span>Vencem em 7 dias · ${sete.length}</span></button>
          <button data-f="avencer" class="${R.filtro === 'avencer' ? 'on' : ''}"><b ${cnt(soma(avencer))}>${brl(soma(avencer))}</b><span>A vencer · ${avencer.length}</span></button>
          <button data-f="gerados" class="${R.filtro === 'gerados' ? 'on' : ''}"><b ${cnt(gerMes, false)}>${gerMes}</b><span>DARE${gerMes === 1 ? '' : 's'} gerado${gerMes === 1 ? '' : 's'} no mês</span></button>
        </div>` : ''}</div>
      <div class="dr-hr"><div class="dr-hb"><select id="drAno">${anos.map((a) => `<option ${a === R.ano ? 'selected' : ''}>${a}</option>`).join('')}</select>
        ${meta ? '<button id="drPdf">Exportar PDF</button>' : ''}
        <button class="g" id="drLer"${podeSefin ? '' : ' disabled title="Precisa do e-CPF do contador instalado neste computador"'}>▶ Consultar débitos</button></div>
        ${meta ? `<div class="dr-ag"><h4>Vencidos por tempo de atraso</h4>
          <div class="dr-stk">${faixas.map((f, i) => `<i style="width:${(f.v / totV * 100).toFixed(2)}%;background:${f.c};animation-delay:${0.25 + i * 0.12}s" title="${f.t}: ${brl(f.v)} · ${f.n} débito(s)"></i>`).join('')}</div>
          <div class="dr-lg">${faixas.map((f) => `<div><span><i style="background:${f.c}"></i>${f.t}</span><b>${brl(f.v)}</b></div>`).join('')}</div>
          <small>Última consulta ${e(quando)}${meta.por ? ' · ' + e(meta.por) : ''}</small></div>` : ''}</div></div>`;

    $('#drRaiz').innerHTML = `${heroTopo}
      <div class="fc-prog" id="drProg" hidden><i></i><span></span></div>
      ${R.semCert ? '<div class="fc-alerta" style="margin-bottom:12px"><b>O certificado do contador não está instalado neste computador.</b> Você está vendo a última consulta salva. Para consultar de novo ou gerar DARE e extrato, use um computador com o e-CPF do contador instalado.</div>' : ''}
      ${!meta ? `<div class="fc-vazio"><b>Nenhuma consulta em ${e(R.ano)} ainda.</b> Clique em “Consultar débitos”: o sistema entra no Portal do Contribuinte com o e-CPF do contador e consulta o exercício de todas as empresas da lista (leva alguns minutos).</div>` : `
      ${falhas.length ? `<div class="fc-aviso" style="margin:0 0 12px">Não consegui consultar ${falhas.length} empresa(s) na última consulta: ${falhas.slice(0, 6).map((m) => e(m.nome)).join(', ')}${falhas.length > 6 ? '…' : ''}. Elas entram de novo na próxima consulta.</div>` : ''}
      ${L.length ? `<div class="dr-g2${anima ? ' dr-in' : ''}">
        <div class="fc-card"><h3>Maiores valores em aberto <small>· matriz e filiais juntas</small></h3>
          ${topG.map((g, i) => `<div class="dr-rk" data-grp="${e(g.k)}" style="animation-delay:${0.15 + i * 0.06}s"><span class="dr-rn">${i + 1}</span>
            <div><b>${e(g.nome)}</b><small>${g.ies.size} inscriç${g.ies.size === 1 ? 'ão' : 'ões'} · ${g.n} débito(s)${g.vencido ? ` · <em>${brl(g.vencido)} vencido</em>` : g.prox ? ` · próximo ${e(g.prox.venc.slice(0, 5))}` : ''}</small></div>
            <i class="dr-rb"><em style="width:${(g.v / mxG * 100).toFixed(1)}%;animation-delay:${0.3 + i * 0.06}s"></em></i><strong>${brl(g.v)}</strong></div>`).join('')}</div>
        <div class="fc-card"><h3>Próximos 30 dias <small>· ${brl(tot30)} por dia de vencimento</small></h3>
          <div class="dr-tl">${dias30.map((x, i) => `<button class="${picos.has(x.s) ? 'pico' : ''} ${i === 0 ? 'hj' : ''} ${R.dia === x.s ? 'on' : ''}" data-dia="${x.s}" title="${x.s} · ${x.n ? `${brl(x.v)} · ${x.n} débito(s)` : 'nenhum vencimento'}">
            <i style="height:${x.v ? Math.max(4, x.v / mxD * 100) : 2}%;animation-delay:${0.2 + i * 0.025}s"></i></button>`).join('')}</div>
          <div class="dr-tlx">${dias30.map((x, i) => `<span>${i === 0 ? 'hoje' : (i % 5 === 0 || i === 29) ? x.s.slice(0, 5) : ''}</span>`).join('')}</div>
          <div class="fc-sub" style="margin-top:8px">Laranja: dias de maior valor · clique num dia para ver só os débitos daquele vencimento.</div></div>
      </div>` : ''}
      <div class="fc-card">
        <div class="fc-flt">
          ${[['todos', `Todos · ${L.length}`], ['venc', `Vencidos · ${venc.length}`], ['sete', `Vencem em 7 dias · ${sete.length}`], ['avencer', `A vencer · ${avencer.length}`], ['gerados', `DARE gerado · ${L.filter((x) => x.ger).length}`]]
            .map(([k, t]) => `<button class="fc-f ${R.filtro === k && !R.dia && !R.grp ? 'on' : ''}" data-f="${k}">${t}</button>`).join('')}
          ${R.dia ? `<button class="fc-f on" id="drDiaX">Vencimento ${e(R.dia)} ✕</button>` : ''}
          ${R.grp ? `<button class="fc-f on" id="drGrpX">${e((grupos.get(R.grp) || {}).nome || 'empresa')} ✕</button>` : ''}
          <select class="fc-sel" id="drEmp"><option value="">Todas as empresas</option>${listaEmp.map(([ie, n]) => `<option value="${e(ie)}" ${R.emp === ie ? 'selected' : ''}>${e(n)} · IE ${e(ie)}</option>`).join('')}</select>
          <select class="fc-sel" id="drRec"><option value="">Todas as receitas</option>${recs.map((r) => `<option ${R.rec === r ? 'selected' : ''}>${e(r)}</option>`).join('')}</select>
          <input class="fc-sel" id="drBusca" placeholder="Buscar empresa, IE ou nº do lançamento" value="${e(R.busca)}">
        </div>
        ${R.sel.size ? `<div class="dr-lote"><span>${R.sel.size} débito(s) selecionado(s) · ${brl(selTot)}</span><span><button class="fc-b" id="drLimpa">Limpar</button><button class="act inv-export fc-go" id="drLote"${podeSefin ? '' : ' disabled'}>Gerar DARE dos selecionados</button></span></div>` : ''}
        ${vis.length ? `<table class="fc-tab dr-tab"><thead><tr><th><input type="checkbox" id="drTodos" ${vis.length && vis.every((x) => R.sel.has(chave(x))) ? 'checked' : ''}></th><th>Empresa</th><th>Lançamento / parc.</th><th>Referência</th><th>Receita</th><th>Vencimento</th><th class="dr-n">Valor</th><th>Situação</th><th>DARE</th><th>Extrato</th></tr></thead><tbody>
          ${vis.slice(0, R.mostrar).map((x) => { const [st, cl] = sit(x); const k = chave(x); return `<tr class="${R.sel.has(k) ? 'fc-on' : ''}">
            <td><input type="checkbox" data-sel="${e(k)}" ${R.sel.has(k) ? 'checked' : ''}${x.temDare === false ? ' disabled' : ''}></td>
            <td><b>${e(x.nome)}</b><small>IE ${e(x.ie)}${x.cnpj ? ' · CNPJ ' + fmtCnpj(x.cnpj) : ''}</small></td>
            <td>${e(x.nr)}<small>parcela ${e(x.parc || '00')}</small></td><td>${e(x.ref)}</td><td>${e(x.rec)}</td><td>${e(x.venc)}</td>
            <td class="dr-n"><b>${brl(x.valorN)}</b>${x.valorAtuN ? `<small>atualizado ${brl(x.valorAtuN)}</small>` : ''}</td>
            <td><span class="fc-c ${cl}">${st}</span>${x.sit && !/n[aã]o pago/i.test(x.sit) ? `<small>${e(x.sit)}</small>` : ''}</td>
            <td>${x.temDare === false ? '<span class="fc-sub">—</span>' : `<button class="dr-bt" data-dare="${e(k)}"${podeSefin ? '' : ' disabled'}>Gerar DARE</button>`}
              ${x.ger && x.ger.arquivo ? `<small class="dr-ok"><a href="#" data-abrir="${e(x.ger.arquivo)}">✓ gerado ${e(String(x.ger.em || '').slice(8, 10) + '/' + String(x.ger.em || '').slice(5, 7))} · p/ ${e(String(x.ger.data || '').slice(0, 5))}</a></small>` : ''}</td>
            <td>${x.temExt === false ? '<span class="fc-sub">—</span>' : `<button class="dr-bt ex" data-ext="${e(k)}"${podeSefin ? '' : ' disabled'}>Extrato</button>`}
              ${x.ger && x.ger.extrato ? `<small class="dr-ok"><a href="#" data-abrir="${e(x.ger.extrato)}">✓ salvo</a></small>` : ''}</td></tr>`; }).join('')}
        </tbody></table>${vis.length > R.mostrar ? `<button class="fc-b" id="drMais" style="margin-top:10px">Mostrar mais ${Math.min(150, vis.length - R.mostrar)}</button>` : ''}`
        : `<div class="fc-sub" style="padding:14px 4px">${L.length ? 'Nenhum débito com esses filtros.' : `Nenhum débito em aberto em ${e(R.ano)} nas empresas consultadas.`}</div>`}
        <div class="fc-sub dr-pasta">📁 Os DAREs e extratos são salvos em <b>${e(R.d.pasta)}</b>\\&lt;empresa&gt; - IE &lt;inscrição&gt;</div>
      </div>`}`;
    if (anima) contar();
    ligar(L, raiz);
  }

  // números do topo contando até o valor (só na abertura)
  function contar() {
    document.querySelectorAll('#drRaiz [data-cnt]').forEach((el) => {
      const fim = +el.dataset.cnt, inteiro = !!el.dataset.int; let t0 = null;
      const fmt = (v) => inteiro ? String(Math.round(v)) : brl(v);
      const passo = (t) => { if (!t0) t0 = t; const k = Math.min(1, (t - t0) / 1100); el.textContent = fmt(fim * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(passo); };
      el.textContent = fmt(0); requestAnimationFrame(passo);
    });
  }

  function ligar(L, raiz) {
    $('#drLer').onclick = consultar;
    $('#drAno').onchange = (ev) => { R.ano = ev.target.value; R.sel.clear(); carregar(); };
    if (!R.d.meta) return;
    if ($('#drPdf')) $('#drPdf').onclick = exportar;
    R._raiz = raiz;
    const rola = () => { const t = document.querySelector('#drRaiz .dr-tab, #drRaiz .fc-flt'); if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' }); };
    document.querySelectorAll('[data-f]').forEach((b) => b.onclick = () => { const no = b.closest('.dr-hk'); R.filtro = no && R.filtro === b.dataset.f ? 'todos' : b.dataset.f; R.dia = ''; R.grp = ''; R.mostrar = 150; desenhar(); if (no) rola(); });
    document.querySelectorAll('[data-dia]').forEach((b) => b.onclick = () => { R.dia = R.dia === b.dataset.dia ? '' : b.dataset.dia; R.filtro = 'todos'; R.grp = ''; R.mostrar = 150; desenhar(); if (R.dia) rola(); });
    document.querySelectorAll('[data-grp]').forEach((b) => b.onclick = () => { R.grp = R.grp === b.dataset.grp ? '' : b.dataset.grp; R.filtro = 'todos'; R.dia = ''; R.mostrar = 150; desenhar(); if (R.grp) rola(); });
    if ($('#drDiaX')) $('#drDiaX').onclick = () => { R.dia = ''; desenhar(); };
    if ($('#drGrpX')) $('#drGrpX').onclick = () => { R.grp = ''; desenhar(); };
    if ($('#drEmp')) $('#drEmp').onchange = (ev) => { R.emp = ev.target.value; desenhar(); };
    if ($('#drRec')) $('#drRec').onchange = (ev) => { R.rec = ev.target.value; desenhar(); };
    const bu = $('#drBusca');
    if (bu) { let t; bu.oninput = () => { clearTimeout(t); t = setTimeout(() => { R.busca = bu.value.trim(); desenhar(); const n = $('#drBusca'); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }, 250); }; }
    const por = new Map(L.map((x) => [chave(x), x]));
    document.querySelectorAll('[data-sel]').forEach((c) => c.onchange = () => { c.checked ? R.sel.add(c.dataset.sel) : R.sel.delete(c.dataset.sel); desenhar(); });
    if ($('#drTodos')) $('#drTodos').onchange = (ev) => { L.filter(passa).filter((x) => x.temDare !== false).forEach((x) => ev.target.checked ? R.sel.add(chave(x)) : R.sel.delete(chave(x))); desenhar(); };
    if ($('#drLimpa')) $('#drLimpa').onclick = () => { R.sel.clear(); desenhar(); };
    if ($('#drLote')) $('#drLote').onclick = () => gerar([...R.sel].map((k) => por.get(k)).filter(Boolean));
    if ($('#drMais')) $('#drMais').onclick = () => { R.mostrar += 150; desenhar(); };
    document.querySelectorAll('[data-dare]').forEach((b) => b.onclick = () => gerar([por.get(b.dataset.dare)]));
    document.querySelectorAll('[data-ext]').forEach((b) => b.onclick = () => baixarExtrato(por.get(b.dataset.ext)));
    document.querySelectorAll('[data-abrir]').forEach((a) => a.onclick = async (ev) => { ev.preventDefault(); const r = await window.fiscocont.dare.abrir(a.dataset.abrir); if (r && r.error) toast(r.error, true); });
  }

  async function consultar() {
    if (R.semCert) return;
    const btn = $('#drLer'); btn.disabled = true;
    const prog = $('#drProg'); if (prog) { prog.hidden = false; prog.querySelector('span').textContent = 'Entrando no portal da SEFIN…'; }
    const r = await window.fiscocont.dare.ler(R.ano);
    btn.disabled = false; if (prog) prog.hidden = true;
    if (r && r.error) { toast(r.error, true); return; }
    toast(`Consulta concluída: ${r.comDebito} empresa(s) com débito · ${brl(r.total)}${r.falhas ? ` · ${r.falhas} sem resposta` : ''}.`);
    await carregar();
  }

  async function baixarExtrato(x) {
    if (!x) return;
    const prog = $('#drProg'); if (prog) { prog.hidden = false; prog.querySelector('span').textContent = 'Baixando o extrato…'; }
    const r = await window.fiscocont.dare.extrato({ ie: x.ie, nome: x.nome, nr: x.nr, parc: x.parc || '00', rec: x.rec, ano: x.ano });
    if (prog) prog.hidden = true;
    if (r && r.error) { toast(r.error, true); return; }
    toast('Extrato salvo na pasta da empresa.');
    window.fiscocont.dare.abrir(r.arquivo);
    carregar();
  }

  // ------------------------------------------------------------------ gerar DARE (um ou vários)
  const M = { lista: [], i: 0, data: '', comExt: true, abrir: false, feitos: [], p: null };
  const fecha = () => { const o = $('#drOv'); if (o) o.remove(); };
  function moldura(x, corpo, rodape) {
    let o = $('#drOv');
    if (!o) { o = document.createElement('div'); o.id = 'drOv'; o.className = 'dr-ov'; document.body.appendChild(o); }
    const n = M.lista.length;
    o.innerHTML = `<div class="dr-md"><div class="dr-mh"><small>GERAR DARE · SEFIN-RO${n > 1 ? ` · ${M.i + 1} DE ${n}` : ''}</small><h2>${e(x.nome)}</h2>
      <p>IE ${e(x.ie)} · Lançamento ${e(x.nr)} · parcela ${e(x.parc || '00')} · Receita ${e(x.rec)} · Ref. ${e(x.ref)}</p></div>
      <div class="dr-mb">${corpo}</div><div class="dr-mf">${rodape}</div></div>`;
    return o;
  }
  function carregando(x, txt) {
    moldura(x, `<div class="dr-esp"><i></i><span id="drMProg">${e(txt)}</span></div>`, '<button class="act inv-export" id="drCan">Cancelar</button>');
    $('#drCan').onclick = cancelarTudo;
  }
  async function cancelarTudo() { await window.fiscocont.dare.cancelar(); fecha(); if (M.feitos.length) resumoFinal(); carregar(); }

  async function gerar(lista) {
    lista = (lista || []).filter(Boolean);
    if (!lista.length || R.semCert) return;
    Object.assign(M, { lista, i: 0, data: '', feitos: [], p: null });
    abrirAtual();
  }
  async function abrirAtual() {
    const x = M.lista[M.i];
    carregando(x, 'Abrindo o DARE na SEFIN…');
    const p = await window.fiscocont.dare.preparar({ ie: x.ie, nome: x.nome, nr: x.nr, parc: x.parc || '00', rec: x.rec, ano: x.ano, ref: x.ref });
    if (!$('#drOv')) return;                                   // cancelado no meio
    if (p && p.error) { erroModal(x, p.error); return; }
    M.p = p;
    const hoje = br(hoje0());
    if (!M.data || (p.datas.length && !p.datas.includes(M.data))) M.data = p.datas.includes(hoje) ? hoje : (p.datas[0] || p.atual || hoje);
    // nos seguintes do lote, sem código de segurança e com a mesma data: segue direto
    if (M.i > 0 && !p.temCaptcha && (!p.datas.length || p.datas.includes(M.data))) { emitir(); return; }
    formulario(x);
  }
  function atalhos(x) {
    const p = M.p, h = hoje0();
    const amanha = new Date(h.getTime() + 864e5);
    const sexta = new Date(h); sexta.setDate(h.getDate() + ((5 - h.getDay() + 7) % 7 || 7));
    const cand = [['Hoje', h], ['Amanhã', amanha], ['Sexta', sexta], ['No vencimento', dt(x.venc)]].filter(([, d]) => d && d >= h);
    const vistos = new Set();
    return cand.map(([t, d]) => [t, br(d), d]).filter(([, s]) => (!p.datas.length || p.datas.includes(s)) && !vistos.has(s) && vistos.add(s));
  }
  function formulario(x, msg) {
    const p = M.p;
    const at = atalhos(x);
    const [st, cl] = sit(x);
    const corpo = `<div class="dr-res"><div>Vencimento<b>${e(x.venc)}</b></div><div>Valor lançado<b>${brl(x.valorN)}</b></div><div>Situação<b class="dr-${cl}">${st}</b></div></div>
      <div class="dr-q">Para qual data você quer o DARE?</div>
      ${at.length ? `<div class="dr-ds">${at.map(([t, s, d]) => `<button class="dr-d ${M.data === s ? 'on' : ''}" data-d="${s}">${t}<b>${s.slice(0, 5)} · ${DSEM[d.getDay()]}</b></button>`).join('')}</div>` : ''}
      <div class="dr-cal">${p.datas.length ? `ou escolha a data: <select id="drData">${p.datas.map((s) => `<option ${M.data === s ? 'selected' : ''}>${s}</option>`).join('')}</select>`
        : `data de pagamento: <input type="date" id="drDataLivre" value="${M.data.split('/').reverse().join('-')}">`}</div>
      ${p.temCaptcha ? `<div class="dr-q" style="margin-bottom:6px">Código de segurança da SEFIN</div>
        <div class="dr-cap">${p.captcha ? `<img src="${p.captcha}" alt="código">` : '<span class="fc-sub">a imagem não carregou · clique em ↻</span>'}<input id="drCod" autocomplete="off" spellcheck="false" placeholder="digite o código da imagem"><button class="dr-rf" id="drRf" title="Outro código">↻</button></div>` : ''}
      ${msg ? `<div class="dr-msg">${e(msg)}</div>` : ''}
      <div class="dr-arq"><b>Onde vai salvar</b><br>📁 <code>${e(p.dir)}</code><br>📄 <code>${e(p.dare.split(/[\\/]/).pop())}</code>${M.comExt && x.temExt !== false ? `<br>📄 <code>${e(p.extrato.split(/[\\/]/).pop())}</code>` : ''}</div>
      <label class="dr-op"><input type="checkbox" id="drExt" ${M.comExt ? 'checked' : ''}${x.temExt === false ? ' disabled' : ''}> Baixar também o extrato do lançamento</label>
      <label class="dr-op"><input type="checkbox" id="drAbr" ${M.abrir ? 'checked' : ''}> Abrir o PDF depois de gerar</label>
      <div class="dr-inf">O portal recalcula multa e juros para a data escolhida; o valor final é o que vier no DARE. Se o pagamento ficar para depois dessa data, gere um DARE novo.</div>`;
    moldura(x, corpo, `<button class="act inv-export" id="drCan">${M.lista.length > 1 ? 'Parar' : 'Cancelar'}</button><button class="act inv-export fc-go" id="drOk">Gerar DARE para ${e(M.data)}</button>`);
    document.querySelectorAll('.dr-d').forEach((b) => b.onclick = () => { M.data = b.dataset.d; formulario(x); });
    if ($('#drData')) $('#drData').onchange = (ev) => { M.data = ev.target.value; formulario(x); };
    if ($('#drDataLivre')) $('#drDataLivre').onchange = (ev) => { M.data = ev.target.value.split('-').reverse().join('/'); formulario(x); };
    $('#drExt').onchange = (ev) => { M.comExt = ev.target.checked; formulario(x); };
    $('#drAbr').onchange = (ev) => { M.abrir = ev.target.checked; };
    $('#drCan').onclick = cancelarTudo;
    if ($('#drRf')) $('#drRf').onclick = async () => { const r = await window.fiscocont.dare.novoCodigo(); if (r && r.error) { toast(r.error, true); return; } M.p.captcha = r.captcha; formulario(x); };
    const cod = $('#drCod');
    if (cod) { cod.focus(); cod.onkeydown = (ev) => { if (ev.key === 'Enter') emitir(); }; }
    $('#drOk').onclick = emitir;
  }
  async function emitir() {
    const x = M.lista[M.i];
    const cod = $('#drCod') ? $('#drCod').value.trim() : null;
    if (M.p.temCaptcha && !cod) { toast('Digite o código de segurança da imagem.', true); return; }
    carregando(x, 'Gerando o DARE na SEFIN…');
    const r = await window.fiscocont.dare.emitir({ data: M.data, codigo: cod, comExtrato: M.comExt && x.temExt !== false });
    if (!$('#drOv')) return;
    if (r && r.error) { erroModal(x, r.error); return; }
    if (r && r.codigoErrado) { M.p.captcha = r.captcha; formulario(x, r.msg); return; }
    M.feitos.push({ x, ...r });
    if (r.aviso) toast(r.aviso, true);
    if (M.abrir) window.fiscocont.dare.abrir(r.arquivo);
    M.i++;
    if (M.i < M.lista.length) { abrirAtual(); return; }
    resumoFinal();
    R.sel.clear(); carregar();
  }
  function erroModal(x, msg) {
    moldura(x, `<div class="dr-msg">Não consegui gerar este DARE: ${e(msg)}</div>`,
      `<button class="act inv-export" id="drCan">Fechar</button>${M.lista.length > M.i + 1 ? '<button class="act inv-export" id="drPula">Pular este</button>' : ''}<button class="act inv-export fc-go" id="drDeNovo">Tentar de novo</button>`);
    $('#drCan').onclick = cancelarTudo;
    $('#drDeNovo').onclick = abrirAtual;
    if ($('#drPula')) $('#drPula').onclick = () => { M.i++; abrirAtual(); };
  }
  function resumoFinal() {
    const x = M.lista[Math.min(M.i, M.lista.length - 1)];
    const o = moldura(x, `<div class="dr-q">${M.feitos.length} DARE(s) gerado(s) e salvo(s)</div>
      ${M.feitos.map((f) => `<div class="dr-fe"><div><b>${e(f.x.nome)}</b><small>Lançamento ${e(f.x.nr)} · para ${e(f.ateDia || M.data)}${f.total ? ' · ' + e('R$ ' + f.total) : ''}</small></div>
        <span><button class="fc-b" data-abrir="${e(f.arquivo)}">DARE</button>${f.extrato ? `<button class="fc-b" data-abrir="${e(f.extrato)}">Extrato</button>` : ''}</span></div>`).join('')}`,
      '<button class="act inv-export fc-go" id="drFim">Concluir</button>');
    o.querySelector('.dr-mh h2').textContent = M.feitos.length > 1 ? 'DAREs gerados' : 'DARE gerado';
    o.querySelectorAll('[data-abrir]').forEach((b) => b.onclick = async () => { const r = await window.fiscocont.dare.abrir(b.dataset.abrir); if (r && r.error) toast(r.error, true); });
    $('#drFim').onclick = fecha;
  }

  // ------------------------------------------------------------------ PDF do painel (filtros da tela)
  async function exportar() {
    const L = linhas().filter(passa);
    const porE = new Map();
    L.forEach((x) => { if (!porE.has(x.ie)) porE.set(x.ie, { nome: x.nome, ie: x.ie, cnpj: x.cnpj, l: [] }); porE.get(x.ie).l.push(x); });
    const tot = L.reduce((s, x) => s + (x.valorN || 0), 0), venc = L.filter((x) => x.dias < 0);
    const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><style>*{box-sizing:border-box}body{margin:0;font-family:'Segoe UI',Arial,sans-serif;color:#141b2d;padding:6px 4px}
      .hd{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:3px solid #1d4ed8;padding-bottom:10px;margin-bottom:14px}.tag{font-size:10px;font-weight:800;letter-spacing:.08em;color:#1d4ed8}
      h1{margin:4px 0 2px;font-size:20px}.sub{color:#5a6785;font-size:11.5px}.esc{text-align:right;font-size:11px;color:#5a6785}.esc b{display:block;font-size:13px;color:#1f2a5a}
      .k{display:flex;gap:10px;margin-bottom:12px}.k div{flex:1;border:1px solid #e5e9f1;border-top:4px solid var(--c);border-radius:10px;padding:8px 12px}.k b{display:block;font-size:18px;color:var(--c)}.k span{font-size:11px;color:#5a6785}
      h3{margin:12px 0 2px;font-size:13px;break-after:avoid}small{color:#5a6785;font-size:10.5px;display:block;break-after:avoid}
      table{width:100%;border-collapse:collapse;font-size:10.8px;margin-top:4px}th{text-align:left;font-size:9.5px;color:#8a93ad;text-transform:uppercase;padding:5px;border-bottom:1.5px solid #e5e9f1}
      td{padding:5px;border-bottom:1px solid #eef0f6}tr{break-inside:avoid}thead{display:table-header-group}.n{text-align:right}.v{color:#b91c1c;font-weight:700}</style></head><body>
      <div class="hd"><div><div class="tag">SEFIN-RO · PORTAL DO CONTRIBUINTE</div><h1>Débitos em aberto · exercício ${e(R.ano)}</h1><div class="sub">${porE.size} empresa(s) · posição de ${e(R.d.meta ? new Date(R.d.meta.ultimaLeitura).toLocaleString('pt-BR').slice(0, 17).replace(',', '') : '')}</div></div>
      <div class="esc"><b>Liddera | Inteligência em Negócios</b>Gerado pelo FiscoCont+ em ${new Date().toLocaleDateString('pt-BR')}</div></div>
      <div class="k"><div style="--c:#1d4ed8"><b>${brl(tot)}</b><span>Total em aberto · ${L.length} débito(s)</span></div><div style="--c:#dc2626"><b>${brl(venc.reduce((s, x) => s + x.valorN, 0))}</b><span>Vencidos · ${venc.length}</span></div></div>
      ${[...porE.values()].map((g) => `<h3>${e(g.nome)}</h3><small>IE ${e(g.ie)}${g.cnpj ? ' · CNPJ ' + fmtCnpj(g.cnpj) : ''} · ${brl(g.l.reduce((s, x) => s + x.valorN, 0))}</small>
        <table><thead><tr><th>Lançamento</th><th>Parc.</th><th>Referência</th><th>Receita</th><th>Vencimento</th><th class="n">Valor</th><th>Situação</th></tr></thead><tbody>
        ${g.l.map((x) => `<tr><td>${e(x.nr)}</td><td>${e(x.parc)}</td><td>${e(x.ref)}</td><td>${e(x.rec)}</td><td>${e(x.venc)}</td><td class="n">${brl(x.valorN)}</td><td class="${x.dias < 0 ? 'v' : ''}">${sit(x)[0]}</td></tr>`).join('')}</tbody></table>`).join('')}
      </body></html>`;
    const nome = `Débitos SEFIN-RO ${R.ano}${R.emp ? ' - ' + ((L[0] || {}).nome || '') : ''} - ${new Date().toLocaleDateString('pt-BR').replace(/\//g, '-')}`;
    const r = await window.fiscocont.dare.exportar(html, nome);
    if (r && r.error) toast(r.error, true); else if (r && r.ok) toast('PDF salvo.');
  }

  // cartão do menu: quantos débitos vencem nos próximos 7 dias (hoje incluído); pulsa quando há vencido
  async function badge() {
    const el = document.getElementById('dareCnt'), rs = document.getElementById('dareResumo'); if (!el) return;
    const nav = el.closest('.nav-item');
    if (nav && nav.classList.contains('role-hidden')) { el.hidden = true; return; }
    const r = await window.fiscocont.dare.resumo(String(new Date().getFullYear())).catch(() => null);
    if (!r || r.error || !Array.isArray(r.vencs)) { el.hidden = true; if (rs) rs.textContent = 'Débitos da SEFIN'; return; }
    const h = hoje0();
    let sete = 0, vencN = 0, vencV = 0;
    r.vencs.forEach((x) => { const d = dt(x.v); if (!d) return; const n = Math.round((d - h) / 864e5); if (n >= 0 && n <= 7) sete++; else if (n < 0) { vencN++; vencV += x.x || 0; } });
    el.textContent = sete.toLocaleString('pt-BR'); el.hidden = !sete;
    el.classList.toggle('nova', vencN > 0);
    el.title = `${sete} vencem em 7 dias${vencN ? ` · ${vencN} vencido(s)` : ''}`;
    if (rs) rs.textContent = sete ? `${sete} vence${sete === 1 ? '' : 'm'} em 7 dias` : vencN ? `${vencN} vencido${vencN === 1 ? '' : 's'}` : 'Nenhum vencimento próximo';
  }
  window._dareBadge = badge;

  window._dareEntrar = entrar;
})();

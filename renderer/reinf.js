'use strict';
// Conferência da EFD-Reinf (2.4.6; serviço oficial de consulta desde a 2.4.14) — o que chegou na Receita depois do envio pelo Domínio: retenções separadas por
// imposto, recibo de envio de cada empresa, fechamentos R-4099/R-2099 com o totalizador (PDF + XML na pasta do cliente),
// pizza animada e a visão de uma empresa só. O sistema confere sozinho às 12h (um computador) ou no botão.
(function () {
  const e = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const brl = (v) => (Number(v) || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  const num = (v) => (Number(v) || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtCnpj = (c) => String(c || '').replace(/\D/g, '').replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
  const fmtDoc = (c) => { const d = String(c || '').replace(/\D/g, ''); return d.length === 14 ? fmtCnpj(d) : d.length === 11 ? d.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4') : c; };
  const compBr = (c) => (c ? `${c.slice(5, 7)}/${c.slice(0, 4)}` : '');
  const KS = ['irrf', 'csll', 'cofins', 'pis', 'agreg', 'inss', 'funrural'];
  const COR = { irrf: '#2563eb', csll: '#0d9488', cofins: '#7c3aed', pis: '#d97706', agreg: '#db2777', inss: '#ea580c', funrural: '#65a30d' };
  const NOME = { irrf: 'IRRF', csll: 'CSLL', cofins: 'Cofins', pis: 'PIS/Pasep', agreg: 'Retenção agregada (CSRF)', inss: 'INSS (R-2010)', funrural: 'Funrural (R-2055)' };
  const CURTO = { irrf: 'IRRF', csll: 'CSLL', cofins: 'Cofins', pis: 'PIS/Pasep', agreg: 'Agregada (CSRF)', inss: 'INSS retido', funrural: 'Funrural' };
  const SIG = { irrf: 'IR', csll: 'CS', cofins: 'CO', pis: 'PI', agreg: 'AG', inss: 'IN', funrural: 'FR' };
  const ST = { fechado: ['ok', 'Fechado'], tarde: ['er', 'Fechado após o dia 15'], aberto: ['ab', 'Aberto (sem fechamento)'], sem_movimento: ['nm', 'Sem movimento'],
    nada_enviado: ['nm', 'Nada enviado'], sem_fechamento: ['nm', 'Sem fechamento'], sem_procuracao: ['er', 'Sem procuração'], erro: ['er', 'Erro na conferência'], nao: ['nm', 'Não conferida'] };
  const R = { comp: '', d: null, emp: '', busca: '', prog: null, anim: true, aba: 'ret', dc: null, dcSel: '' };
  const NOVO_DCTF = new Date(2026, 10, 25, 23, 59, 59) > new Date();         // aba nova: selo NOVO por 7 dias
  let desliga = null, recarga = null;
  const raiz = () => document.getElementById('rfRaiz');

  // ------------------------------------------------------------------ datas e situação
  const dtBr = (s) => { const m = String(s || '').match(/(\d{2})\/(\d{2})\/(\d{4})(?:\D+(\d{2}):(\d{2}))?/); if (m) return new Date(+m[3], +m[2] - 1, +m[1], +(m[4] || 0), +(m[5] || 0));
    const i = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/); return i ? new Date(+i[1], +i[2] - 1, +i[3], +(i[4] || 0), +(i[5] || 0)) : null; };
  const curta = (s) => { const d = dtBr(s); return d ? `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` : (s || ''); };
  // prazo: até o dia 15 do mês seguinte à competência (o sistema só marca o envio feito DEPOIS do dia 15)
  const depoisDo15 = (comp, s) => { const d = dtBr(s); if (!d) return false; const lim = new Date(+comp.slice(0, 4), +comp.slice(5, 7), 15, 23, 59, 59); return d > lim; };
  function situacao(doc) {
    if (!doc) return 'nao';
    if (doc.status === 'fechado' && depoisDo15(R.comp, (doc.fech4099 || {}).dhProcess || (doc.fech4099 || {}).recepcao || (doc.fech2099 || {}).dhProcess)) return 'tarde';
    return ST[doc.status] ? doc.status : 'erro';
  }
  const chip = (s) => `<span class="rf-chip ${ST[s][0]}">● ${e(ST[s][1])}</span>`;
  const totDoc = (doc) => KS.reduce((a, k) => a + ((doc && doc.totais && doc.totais[k]) || 0), 0);
  function recibo(doc) {
    if (!doc) return '<span class="rf-rec vz">não conferida</span>';
    const f4 = doc.fech4099 || {}, f2 = doc.fech2099 || {};
    const out = [];
    if (f4.fechado) out.push(`<span class="rf-rec">${e(f4.recibo)}</span><small>fechamento R-4099${f4.dhProcess || f4.recepcao ? ` · ${e(curta(f4.dhProcess || f4.recepcao))}` : ''}</small>`);
    if (f2.fechado) out.push(`<span class="rf-rec">${e(f2.recibo)}</span><small>fechamento R-2099${f2.dhProcess || f2.recepcao ? ` · ${e(curta(f2.dhProcess || f2.recepcao))}` : ''}</small>`);
    [[f4, '4099'], [f2, '2099']].forEach(([f, n]) => { if (!f.fechado && (f.reaberto || f.recusado || f.processando)) out.push(`<span class="rf-rec">${e(f.recibo || f.protocolo || '—')}</span><small>R-${n} ${f.reaberto ? 'reaberto' : f.recusado ? 'recusado pela Receita' : 'em processamento'}${f.recepcao ? ` · ${e(curta(f.recepcao))}` : ''}</small>`); });
    if (!out.length && doc.fonte === 'api') return '<span class="rf-rec vz">sem fechamento na Receita</span>';
    if (!out.length) {
      const ev = (doc.eventos || []).filter((x) => x.recibo).sort((a, b) => (dtBr(b.recepcao) || 0) - (dtBr(a.recepcao) || 0))[0];
      if (ev) out.push(`<span class="rf-rec">${e(ev.recibo)}</span><small>último evento enviado${ev.recepcao ? ` · ${e(curta(ev.recepcao))}` : ''} · sem fechamento</small>`);
    }
    return out.join('') || '<span class="rf-rec vz">não enviada</span>';
  }

  // ------------------------------------------------------------------ entrada
  async function entrar() {
    const r = raiz(); if (!r) return;
    if (!R.d) r.innerHTML = '<div class="lic-empty">Carregando a conferência da EFD-Reinf…</div>';
    if (!desliga) {
      desliga = window.fiscocont.reinf.onProgresso((p) => { R.prog = p.fim ? null : p; const el = document.getElementById('rfProg'); if (el) { el.hidden = !R.prog; el.querySelector('span').textContent = (p && p.txt) || ''; if (p && p.total) el.querySelector('i').style.width = `${Math.round((p.feitas || 0) / p.total * 100)}%`; }
        const bt = document.getElementById('rfConferir'); if (bt) bt.outerHTML = botaoConferir(); ligaConferir(); if (p.fim) carregar(); });
      window.fiscocont.reinf.onEmpresa(() => { clearTimeout(recarga); recarga = setTimeout(() => carregar(true), 1200); });
      window.fiscocont.reinf.onAuto(() => carregar());
      if (window.fiscocont.reinf.onDctf) window.fiscocont.reinf.onDctf(() => { if (R.aba === 'dctf') carregarDctf(true); });
    }
    await carregar();
  }
  async function carregar(quieto) {
    const d = await window.fiscocont.reinf.dados(R.comp || null);
    if (d && d.error) { raiz().innerHTML = `<div class="lic-empty">${e(d.error)}</div>`; return; }
    R.d = d; R.comp = d.comp; R.anim = !quieto;
    if (d.rodando && !R.prog) R.prog = { txt: 'Conferência em andamento…' };
    if (R.aba === 'dctf') { await carregarDctf(quieto, true); } else desenhar();
    menu();
  }
  const docDe = (cnpj) => (R.d.docs || []).find((x) => x.cnpj === cnpj);
  function linhas() {
    const emps = (R.d.empresas || []).filter((x) => x.ativa !== false);
    const vistos = new Set(emps.map((x) => x.cnpj));
    (R.d.docs || []).forEach((x) => { if (!vistos.has(x.cnpj)) emps.push({ cnpj: x.cnpj, nome: x.nome }); });
    return emps.map((x) => ({ ...x, doc: docDe(x.cnpj), sit: situacao(docDe(x.cnpj)) }));
  }
  function totais(ls) { const t = Object.fromEntries(KS.map((k) => [k, 0])); ls.forEach((l) => KS.forEach((k) => { t[k] += (l.doc && l.doc.totais && l.doc.totais[k]) || 0; })); return t; }

  // ------------------------------------------------------------------ desenho
  function meses() { const out = []; const d = new Date(); for (let i = 1; i <= 14; i++) { const x = new Date(d.getFullYear(), d.getMonth() - i, 1); out.push(`${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}`); } return out; }
  const botaoConferir = () => (R.prog ? '<button class="rf-pill" id="rfConferir" data-parar="1">Parar a conferência</button>'
    : `<button class="rf-pill g" id="rfConferir">${R.emp ? 'Conferir esta empresa' : 'Realizar a conferência'}</button>`);
  function topo(ls) {
    const sel = `<select class="rf-pill rf-sel" id="rfComp">${meses().map((m) => `<option value="${m}" ${m === R.comp ? 'selected' : ''}>Competência ${compBr(m)}</option>`).join('')}</select>`;
    const emp = `<div class="rf-busca"><input class="rf-pill" id="rfEmp" list="rfEmpLista" placeholder="🔍 Empresa: Todas" value="${e(R.emp ? (ls.find((l) => l.cnpj === R.emp) || {}).nome || '' : '')}"><datalist id="rfEmpLista">${ls.map((l) => `<option value="${e(l.nome)}">${e(fmtCnpj(l.cnpj))}</option>`).join('')}</datalist></div>`;
    const m = R.d.meta || {};
    const quando = m.fim ? `conferida em ${curta(m.fim)}${m.por ? ` por ${e(m.por)}` : ''}${m.auto ? ' (automática)' : ''}` : 'ainda não conferida';
    return { sel, emp, quando };
  }
  function desenhar() {
    const ls = linhas();
    if (R.emp && !ls.find((l) => l.cnpj === R.emp)) R.emp = '';
    if (R.emp) { desenharEmpresa(ls.find((l) => l.cnpj === R.emp), ls); return; }
    if (R.aba === 'dctf') { desenharDctf(ls); return; }
    const t = totais(ls), T = KS.reduce((a, k) => a + t[k], 0);
    const conf = ls.filter((l) => l.doc), fech = ls.filter((l) => ['fechado', 'tarde'].includes(l.sit)).length;
    const nEv = conf.reduce((a, l) => a + ((l.doc.eventos || []).length), 0), nRet = conf.reduce((a, l) => a + (l.doc.eventos || []).filter((x) => x.tipo === 'Retificador').length, 0);
    const tp = topo(ls);
    const mx = Math.max(...KS.map((k) => t[k]), 1);
    const porEmp = ls.filter((l) => totDoc(l.doc) > 0).sort((a, b) => totDoc(b.doc) - totDoc(a.doc)).slice(0, 8);
    const mxE = Math.max(...porEmp.map((l) => totDoc(l.doc)), 1);
    raiz().innerHTML = `
      <div class="rf-hero"><div>
        <h1><img src="img/efd-reinf.png" alt="">Conferência da EFD-Reinf</h1>
        <div class="rf-s">Competência ${compBr(R.comp)} · ${tp.quando}${R.d.meta && R.d.meta.fonte === 'api' ? ' · serviço oficial da EFD-Reinf' : ''}${R.d.proxima ? ` · próxima conferência automática ${curta(R.d.proxima)}` : ''}</div>
        ${abas()}
        <div class="rf-big"><div><small>Total retido no mês</small><b data-cont="${T}">${brl(T)}</b></div>
          <div class="rf-mini"><div><b>${conf.length} / ${ls.length}</b><small>empresas conferidas</small></div><div><b>${fech}</b><small>fechadas</small></div>${nEv ? `<div><b>${nEv}</b><small>eventos</small></div><div><b>${nRet}</b><small>retificadores</small></div>`
            : `<div><b>${ls.filter((l) => ['sem_fechamento', 'nada_enviado', 'aberto'].includes(l.sit)).length}</b><small>sem fechamento</small></div><div><b>${ls.filter((l) => l.sit === 'sem_procuracao').length}</b><small>sem procuração</small></div>`}</div></div>
        <div class="rf-prog" id="rfProg" ${R.prog ? '' : 'hidden'}><i></i><span>${e((R.prog || {}).txt || '')}</span></div>
      </div><div class="rf-ctl"><div>${tp.sel}${tp.emp}</div><div><button class="rf-pill" id="rfEmps" title="Escolher as empresas conferidas">Empresas</button><span class="rf-menu-w"><button class="rf-pill" id="rfLista">Gerar lista ▾</button><span class="rf-menu" id="rfListaMenu" hidden><button data-l="pdf">PDF</button><button data-l="xlsx">Excel</button></span></span>${botaoConferir()}</div></div></div>
      ${R.d.certificadoAqui === false ? `<div class="rf-aviso">O certificado do escritório (e-CNPJ ${e(fmtCnpj(R.d.certificado))}) não está instalado neste computador: aqui você vê a conferência feita pela equipe; para conferir agora, use um computador com o certificado.</div>` : ''}
      <div class="rf-kp">${KS.map((k) => `<div class="rf-k" style="--c:${COR[k]}"><div class="ic">${SIG[k]}</div><small>${NOME[k]}</small><b data-cont="${t[k]}">${brl(t[k])}</b><div class="bar"><i style="--w:${t[k] / mx * 100}%"></i></div><span>${ls.filter((l) => l.doc && l.doc.totais && l.doc.totais[k]).length} empresa(s)</span></div>`).join('')}</div>
      <div class="rf-g2">
        <div class="rf-card"><h3>Retenções por imposto</h3><div class="rf-pz">${T ? `<svg viewBox="0 0 300 300" class="rf-pizza" data-vals='${JSON.stringify(t)}'></svg>` : '<div class="rf-vz">Nenhuma retenção na competência.</div>'}${legenda(t)}</div></div>
        <div class="rf-card"><h3>Conferências</h3>${conferencias(ls)}</div>
      </div>
      <div class="rf-card rf-mt"><h3>Retido por empresa <small>clique para abrir a empresa</small></h3>${porEmp.map((l) => `<button class="rf-be" data-emp="${e(l.cnpj)}"><span>${e(l.nome)}</span><div>${KS.map((k) => (l.doc.totais[k] ? `<i style="--w:${l.doc.totais[k] / mxE * 100}%;background:${COR[k]}"></i>` : '')).join('')}</div><b>${brl(totDoc(l.doc)).replace(/,\d\d$/, '')}</b></button>`).join('') || '<div class="rf-vz">Sem valores retidos ainda.</div>'}</div>
      <div class="rf-card rf-tab"><h3>Empresas · retenção separada por imposto <small>clique na empresa para ver eventos, recibos e valores</small></h3>
        <table><thead><tr><th>Empresa</th>${KS.map((k) => `<th class="n"><i style="background:${COR[k]}"></i>${k === 'agreg' ? 'Agregada' : k === 'inss' ? 'INSS' : k === 'funrural' ? 'Funrural' : NOME[k]}</th>`).join('')}<th class="n">Total</th><th>Situação</th><th>Recibo de envio</th></tr></thead><tbody>
        ${ls.map((l) => linhaEmp(l)).join('')}
        <tr class="tot"><td><b>Total</b></td>${KS.map((k) => `<td class="n"><b>${num(t[k])}</b></td>`).join('')}<td class="n"><b>${brl(T)}</b></td><td></td><td></td></tr></tbody></table></div>`;
    ligar();
    animar();
  }
  function linhaEmp(l) {
    const d = l.doc;
    const sub = [fmtCnpj(l.cnpj), d && (d.eventos || []).length ? `${d.eventos.length} evento(s)` : '', d && (d.eventos || []).filter((x) => x.tipo === 'Retificador').length ? `${d.eventos.filter((x) => x.tipo === 'Retificador').length} retificador(es)` : ''].filter(Boolean).join(' · ');
    const meio = !d ? `<td colspan="8" class="rf-cin">ainda não conferida nesta competência</td>`
      : l.sit === 'sem_procuracao' ? `<td colspan="8" class="rf-erl">A Liddera não tem procuração eletrônica desta empresa com poderes da EFD-Reinf. Peça ao cliente a procuração no eCAC.</td>`
        : d.fonte === 'api' && l.sit !== 'erro' && !d.totaisDe ? `<td colspan="8" class="rf-cin">${['fechado', 'tarde'].includes(l.sit) ? 'valores por imposto chegam com a leitura da DCTFWeb (Integra Contador)' : l.sit === 'aberto' ? e(d.msg || 'fechamento pendente na Receita') : 'sem fechamento R-4099/R-2099 nesta competência'}</td>`
        : l.sit === 'erro' ? `<td colspan="8" class="rf-erl">${e(d.msg || 'erro na conferência')}</td>`
          : KS.map((k) => `<td class="n">${d.totais && d.totais[k] ? num(d.totais[k]) : '<span class="rf-cin">—</span>'}</td>`).join('') + `<td class="n"><b>${brl(totDoc(d))}</b></td>`;
    return `<tr data-emp="${e(l.cnpj)}"><td><b>${e(l.nome)}</b><small>${e(sub)}</small></td>${meio}<td>${chip(l.sit)}</td><td class="rf-rc">${['sem_procuracao', 'erro'].includes(l.sit) ? '<span class="rf-rec vz">—</span>' : recibo(d)}</td></tr>`;
  }
  function legenda(t) { return `<div class="rf-leg">${KS.filter((k) => t[k]).map((k) => `<div><i style="background:${COR[k]}"></i><span>${CURTO[k]}</span><b>${brl(t[k])}</b></div>`).join('')}</div>`; }

  function conferencias(ls) {
    const it = [];
    const nomes = (arr) => arr.slice(0, 4).map((l) => l.nome).join(' · ') + (arr.length > 4 ? ` · +${arr.length - 4}` : '');
    const semP = ls.filter((l) => l.sit === 'sem_procuracao'); if (semP.length) it.push(['er', '!', 'Sem procuração', nomes(semP)]);
    const err = ls.filter((l) => l.sit === 'erro'); if (err.length) it.push(['er', '×', 'Erro na conferência', nomes(err)]);
    const tarde = ls.filter((l) => l.sit === 'tarde'); if (tarde.length) it.push(['er', '⏰', 'Fechado depois do dia 15', tarde.map((l) => `${l.nome} · recibo ${(l.doc.fech4099 || l.doc.fech2099 || {}).recibo || ''}`).slice(0, 3).join(' · ')]);
    const ab = ls.filter((l) => l.sit === 'aberto'); if (ab.length) it.push(['ab', '!', 'Período aberto (sem fechamento)', `${nomes(ab)}. Sem o fechamento, os valores não seguem para a DCTFWeb.`]);
    const ret = ls.filter((l) => l.doc && (l.doc.eventos || []).some((x) => x.tipo === 'Retificador'));
    if (ret.length) it.push(['in', '↻', `${ret.reduce((a, l) => a + l.doc.eventos.filter((x) => x.tipo === 'Retificador').length, 0)} retificador(es)`, ret.slice(0, 4).map((l) => `${l.nome} (${l.doc.eventos.filter((x) => x.tipo === 'Retificador').length})`).join(' · ')]);
    // soma dos eventos × totalizador (só onde os dois existem)
    const cmp = ls.filter((l) => l.doc && (l.doc.fech4099 || {}).fechado && ((l.doc.fech4099 || {}).porCodigo || []).length && (l.doc.eventos || []).some((x) => /^R-40[12]0$/.test(x.evento)));
    const dif = cmp.filter((l) => { const ev = l.doc.eventos.filter((x) => /^R-40/.test(x.evento)).reduce((a, x) => a + (x.irrf || 0) + (x.csll || 0) + (x.cofins || 0) + (x.pis || 0) + (x.agreg || 0), 0);
      const tt = l.doc.fech4099.porCodigo.reduce((a, x) => a + (x.enviado || 0), 0); return Math.abs(ev - tt) > 0.05; });
    if (cmp.length) it.push(dif.length ? ['er', '≠', 'Soma dos eventos diferente do totalizador', nomes(dif)] : ['ok', '✓', 'Soma dos eventos = totalizador', `${cmp.length} de ${cmp.length} empresa(s) conferem com o totalizador do R-4099`]);
    // enviou no mês passado e não neste
    const antes = new Set((R.d.docsAnterior || []).filter((x) => x.nEventos > 0 || x.fechado).map((x) => x.cnpj));
    const sumiu = ls.filter((l) => antes.has(l.cnpj) && l.doc && ['nada_enviado', 'sem_fechamento'].includes(l.sit));
    it.push(sumiu.length ? ['ab', '↓', 'Fechou no mês passado e não fechou neste', nomes(sumiu)] : ['ok', '✓', 'Quem fechou no mês passado fechou neste', `comparado com ${compBr(R.d.anterior)}`]);
    // CSRF fora de 4,65% (só aviso para conferir)
    const csrf = [];
    ls.forEach((l) => (l.doc && l.doc.eventos || []).forEach((x) => { const c = (x.agreg || 0) + (x.csll || 0) + (x.cofins || 0) + (x.pis || 0); if (c > 0 && x.bruto > 0 && Math.abs(c / x.bruto * 100 - 4.65) > 0.05) csrf.push(l.nome); }));
    if (csrf.length) it.push(['ab', '%', 'Retenção de PIS/Cofins/CSLL diferente de 4,65% do bruto (conferir)', [...new Set(csrf)].slice(0, 4).join(' · ')]);
    return it.map(([c, i, t, s]) => `<div class="rf-al"><span class="i ${c}">${i}</span><div><b>${e(t)}</b><span>${e(s)}</span></div></div>`).join('');
  }

  // ------------------------------------------------------------------ uma empresa
  function desenharEmpresa(l, ls) {
    const d = l.doc || {}, t = d.totais || Object.fromEntries(KS.map((k) => [k, 0])), T = totDoc(d);
    const f4 = d.fech4099 || {}, f2 = d.fech2099 || {};
    const ev = (d.eventos || []).slice().sort((a, b) => (dtBr(a.recepcao) || 0) - (dtBr(b.recepcao) || 0));
    const tp = topo(ls);
    const mx = Math.max(...KS.map((k) => t[k] || 0), 1);
    const imp = (cod, serie) => (serie === '2000' ? 'inss' : ({ 6228: 'csll', 5987: 'csll', 6230: 'pis', 5979: 'pis', 6243: 'cofins', 5960: 'cofins', 5952: 'agreg' }[String(cod).slice(0, 4)] || 'irrf'));
    const dctf = d.fonte === 'api' ? (d.dctfCodigos || []).map((x) => ({ ...x, serie: ['inss', 'funrural'].includes(x.imposto) ? '2000' : '4000' }))
      : [...(f4.porCodigo || []).map((x) => ({ ...x, serie: '4000' })), ...(f2.porCodigo || []).map((x) => ({ ...x, serie: '2000' }))];
    const bt = (f, ev2) => (f.fechado && f.pdf ? `<button class="rf-pill" data-tot="${ev2}">${f.pdf ? '📄' : '⬇'} Totalizador R-${ev2}</button>` : '');
    raiz().innerHTML = `
      <div class="rf-hero"><div>
        <div class="rf-s"><a href="#" id="rfVolta">Conferência da EFD-Reinf</a> ›</div>
        <h1><img src="img/efd-reinf.png" alt="">${e(l.nome)}</h1>
        <div class="rf-s">${e(fmtCnpj(l.cnpj))} · competência ${compBr(R.comp)} · ${l.doc ? `conferida em ${curta(d.em)}${d.por ? ` por ${e(d.por)}` : ''}` : 'ainda não conferida'}</div>
        <div class="rf-big"><div><small>Total retido no mês</small><b data-cont="${T}">${brl(T)}</b></div>
          <div class="rf-mini"><div><b>${ev.length}</b><small>eventos</small></div><div><b>${ev.filter((x) => x.tipo === 'Retificador').length}</b><small>retificadores</small></div><div><b style="font-size:13px;margin-top:4px">${chip(l.sit)}</b><small>${f4.fechado ? `R-4099 ${e(curta(f4.dhProcess || f4.recepcao))}` : f4.reaberto ? 'R-4099 reaberto' : 'sem fechamento R-4099'}</small></div></div></div>
        ${f4.fechado || f2.fechado ? `<div class="rf-s" style="margin-top:12px">Recibo de envio do fechamento ${f4.fechado ? `<span class="rf-rec h">${e(f4.recibo)}</span>` : ''}${f2.fechado ? ` R-2099 <span class="rf-rec h">${e(f2.recibo)}</span>` : ''}</div>` : ''}
        ${d.msg ? `<div class="rf-s" style="margin-top:10px;color:#fecaca">${e(d.msg)}</div>` : ''}
        <div class="rf-prog" id="rfProg" ${R.prog ? '' : 'hidden'}><i></i><span>${e((R.prog || {}).txt || '')}</span></div>
      </div><div class="rf-ctl"><div>${tp.sel}${tp.emp}</div><div>${bt(f4, '4099')}${bt(f2, '2099')}${d.pasta ? '<button class="rf-pill" id="rfPasta">Abrir pasta</button>' : ''}${botaoConferir()}</div></div></div>
      <div class="rf-kp">${KS.map((k) => `<div class="rf-k" style="--c:${COR[k]}"><div class="ic">${SIG[k]}</div><small>${NOME[k]}</small><b data-cont="${t[k] || 0}">${brl(t[k] || 0)}</b><div class="bar"><i style="--w:${(t[k] || 0) / mx * 100}%"></i></div><span>${d.fonte === 'api' ? (d.totaisDe ? 'débito na DCTFWeb' : 'aguarda a DCTFWeb') : f4.fechado && !['inss', 'funrural'].includes(k) ? 'enviado à DCTFWeb' : f2.fechado && ['inss', 'funrural'].includes(k) ? 'enviado à DCTFWeb' : 'soma dos eventos'}</span></div>`).join('')}</div>
      <div class="rf-g2">
        <div class="rf-card"><h3>Retenções da empresa</h3><div class="rf-pz">${T ? `<svg viewBox="0 0 300 300" class="rf-pizza" data-vals='${JSON.stringify(t)}'></svg>` : '<div class="rf-vz">Nenhuma retenção na competência.</div>'}${legenda(t)}</div></div>
        <div class="rf-card"><h3>Totais que vão para a DCTFWeb <small>${d.fonte === 'api' ? 'débitos da REINF na DCTFWeb (Integra Contador)' : 'totalizador do fechamento'}</small></h3>
          ${dctf.length ? `<div class="rf-dctf">${dctf.map((x) => `<div><span><b>${e(x.cod)}</b> · ${({ 1656: 'Funrural · contribuição', 1646: 'Funrural · GILRAT', 1213: 'Senar' })[String(x.cod).slice(0, 4)] || CURTO[x.imposto || imp(x.cod, x.serie)]} <small>R-${x.serie === '2000' ? '2099' : '4099'}</small></span><b>${brl(x.enviado)}</b></div>`).join('')}
            <div class="rf-dt"><span>Total</span><b>${brl(dctf.reduce((a, x) => a + (x.enviado || 0), 0))}</b></div></div>`
            : `<div class="rf-vz">${d.fonte === 'api' && (f4.fechado || f2.fechado) ? (d.totaisDe ? 'A DCTFWeb não tem débitos vindos da REINF (fechamento sem movimento?).' : 'Os valores aparecem quando o computador do Integra Contador ler a DCTFWeb do período.') : f4.fechado || f2.fechado ? 'O totalizador não trouxe códigos de receita.' : 'Sem fechamento na competência: os valores ainda não seguem para a DCTFWeb.'}</div>`}
          ${f4.fechado ? `<div class="rf-fx"><span>R-4099 · recibo <span class="rf-rec">${e(f4.recibo)}</span></span><small>processado ${e(curta(f4.dhProcess || f4.recepcao))}${f4.semMovimento ? ' · sem movimento' : ''}</small></div>` : ''}
          ${f2.fechado ? `<div class="rf-fx"><span>R-2099 · recibo <span class="rf-rec">${e(f2.recibo)}</span></span><small>processado ${e(curta(f2.dhProcess || f2.recepcao))}</small></div>` : ''}</div>
      </div>
      <div class="rf-card rf-tab"><h3>Eventos enviados <small>cada linha com o seu recibo</small></h3>
          ${ev.length ? `<table><thead><tr><th>Evento</th><th>Beneficiário / prestador</th><th>Natureza</th><th class="n">Bruto</th><th class="n">IRRF</th><th class="n">CSRF</th><th class="n">INSS</th><th>Tipo</th><th>Recibo de envio</th></tr></thead><tbody>
          ${ev.map((x) => `<tr><td><b>${e(x.evento)}</b></td><td>${e(fmtDoc(x.benef))}</td><td>${e((x.natRend || []).join(', '))}</td><td class="n">${x.semXml ? '—' : num(x.bruto)}</td><td class="n">${x.irrf ? num(x.irrf) : '—'}</td>
            <td class="n">${(x.agreg || x.csll || x.cofins || x.pis) ? num((x.agreg || 0) + (x.csll || 0) + (x.cofins || 0) + (x.pis || 0)) : '—'}</td><td class="n">${x.inss ? num(x.inss) : '—'}</td>
            <td>${x.tipo === 'Retificador' ? '<span class="rf-chip in">Retificador</span>' : '<span class="rf-chip nm">Original</span>'}</td><td class="rf-rc"><span class="rf-rec">${e(x.recibo)}</span><small>recebido ${e(curta(x.recepcao))}</small></td></tr>`).join('')}</tbody></table>`
            : `<div class="rf-vz">${d.fonte === 'api' ? 'A consulta oficial da Receita informa o recibo do fechamento; os eventos de cada beneficiário ou produtor (R-4010/R-4020/R-2010/R-2055) ficam no Domínio.' : l.doc ? 'Nenhum evento enviado nesta competência.' : 'Clique em "Conferir esta empresa".'}</div>`}</div>`;
    ligar();
    animar();
  }


  // ------------------------------------------------------------------ REINF × DCTFWeb (Integra Contador)
  const abas = () => `<div class="rf-abas"><button class="${R.aba === 'ret' ? 'on' : ''}" data-aba="ret">Retenções</button><button class="${R.aba === 'dctf' ? 'on' : ''}" data-aba="dctf">REINF × DCTFWeb${NOVO_DCTF ? '<em class="nav-new">NOVO</em>' : ''}</button></div>`;
  const CMP = { recebida: ['ok', '✓ Recebida na DCTFWeb'], sem_dctf: ['ab', '! Sem DCTFWeb no período'], confere: ['ok', '✓ Confere'], diverge: ['er', '✕ Diverge'], nao_apareceu: ['ab', '! Não apareceu'], aguarda: ['nm', 'aguarda fechar a REINF'], sem_debito: ['nm', 'sem débito da REINF'], erro: ['er', 'Erro na consulta'] };
  const SDC = { em_andamento: ['ab', 'Em andamento'], transmitida: ['in', 'Transmitida'], sem_declaracao: ['nm', 'Sem declaração'], semproc: ['er', 'Sem procuração'], erro: ['er', 'Erro'] };
  const RST = { fechado: ['ok', 'Fechada'], aberto: ['ab', 'Aberta'], sem_fechamento: ['nm', 'Sem fechamento'], sem_movimento: ['nm', 'Sem movimento'], nada_enviado: ['nm', 'Nada enviado'], sem_procuracao: ['er', 'Sem procuração'], erro: ['er', 'Erro'] };
  const NOMECR = { 1708: 'IRRF · serviços PJ', 5952: 'CSRF (PIS/Cofins/CSLL)', 1162: 'INSS retido (cessão de mão de obra)', '0561': 'IRRF · trabalho assalariado', '0588': 'IRRF · trabalho sem vínculo', 3208: 'IRRF · aluguéis e royalties PF', 8045: 'IRRF · comissões e corretagens', 3280: 'IRRF · cooperativas', 1656: 'Funrural · contribuição previdenciária (aquisição de produção rural)', 1646: 'Funrural · GILRAT (aquisição de produção rural)', 1213: 'Senar (aquisição de produção rural)', 5960: 'Cofins retida', 5979: 'PIS retido', 5987: 'CSLL retida', 6228: 'CSLL · órgão público', 6230: 'PIS · órgão público', 6243: 'Cofins · órgão público', 1141: 'INSS retido · serviços com aposentadoria especial' };
  const ch2 = (m, k) => (m[k] ? `<span class="rf-chip ${m[k][0]}">${e(m[k][1])}</span>` : '<span class="rf-chip nm">—</span>');
  const hm = (ms) => { const d = new Date(ms); return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };
  const somaM = (m) => Object.values(m || {}).reduce((a, v) => a + (Number(v) || 0), 0);
  let pollDc = null;
  async function carregarDctf(quieto, semRe) {
    const d = await window.fiscocont.reinf.dctfDados(R.comp);
    R.dc = d && !d.error ? d : { erro: (d && d.error) || 'falha', docs: [], pedidos: [], robo: {} };
    if (!quieto) R.anim = true;
    desenhar();
    clearTimeout(pollDc);
    if ((R.dc.pedidos || []).some((p) => ['novo', 'rodando'].includes(p.status)) && R.aba === 'dctf') pollDc = setTimeout(() => carregarDctf(true), 6000);
  }
  function linhasDctf(ls) {
    const by = new Map((R.dc && R.dc.docs || []).map((x) => [x.cnpj, x]));
    return ls.filter((l) => l.doc && !['nao'].includes(l.sit)).map((l) => {
      const x = by.get(l.cnpj) || null;
      const tReinf = x && Object.keys(x.esperado || {}).length ? somaM(x.esperado) : KS.reduce((a, k) => a + ((l.doc.totais || {})[k] || 0), 0);
      return { ...l, dc: x, tReinf, tDctf: x && x.naDctf ? somaM(x.naDctf) : null, cmp: x ? x.comparacao : l.doc.status === 'aberto' ? 'aguarda' : '' };
    }).sort((a, b) => ['diverge', 'nao_apareceu', 'erro', 'confere', 'aguarda', 'sem_debito', ''].indexOf(a.cmp) - ['diverge', 'nao_apareceu', 'erro', 'confere', 'aguarda', 'sem_debito', ''].indexOf(b.cmp) || a.nome.localeCompare(b.nome, 'pt-BR'));
  }
  function desenharDctf(ls) {
    if (!R.dc) { raiz().innerHTML = '<div class="lic-empty">Carregando a DCTFWeb…</div>'; carregarDctf(); return; }
    const L = linhasDctf(ls);
    if (R.dcSel && !L.find((l) => l.cnpj === R.dcSel)) R.dcSel = '';
    if (!R.dcSel) { const pri = L.find((l) => l.dc && l.dc.podeTransmitir) || L.find((l) => l.dc); R.dcSel = pri ? pri.cnpj : ''; }
    const n = (c) => L.filter((l) => l.cmp === c).length, ntr = L.filter((l) => l.dc && l.dc.situacao === 'transmitida').length;
    const tp = topo(ls), rb = R.dc.robo || {};
    const fila = (R.dc.pedidos || []).filter((p) => ['novo', 'rodando'].includes(p.status));
    const ult = (R.dc.pedidos || []).find((p) => p.tipo === 'conferir' && ['feito', 'erro'].includes(p.status));
    const nomeDe = (c) => (ls.find((l) => l.cnpj === c) || {}).nome || c;
    const sel = L.find((l) => l.cnpj === R.dcSel);
    raiz().innerHTML = `
      <div class="rf-hero"><div>
        <h1><img src="img/efd-reinf.png" alt="">Conferência da EFD-Reinf</h1>
        <div class="rf-s">Competência ${compBr(R.comp)} · DCTFWeb pelo Integra Contador · ${rb.ativo ? `computador do escritório ${rb.online ? 'online' : '<b style="color:#fecaca">offline</b>'}` : '<b style="color:#fecaca">Integra Contador não configurado</b>'}${ult ? ` · última conferência ${e(hm(ult.fimMs || ult.emMs))}` : ''}</div>
        ${abas()}
        <div class="rf-big"><div class="dc-k"><small>Confere</small><b data-n="${n('confere')}">${n('confere')}</b></div><div class="dc-k"><small>Diverge</small><b data-n="${n('diverge')}">${n('diverge')}</b></div><div class="dc-k"><small>Não apareceu</small><b data-n="${n('nao_apareceu')}">${n('nao_apareceu')}</b></div><div class="dc-k"><small>Transmitidas</small><b data-n="${ntr}">${ntr}</b></div></div>
        ${fila.length ? `<div class="rf-prog dc-fila"><i style="width:100%"></i><span>${fila.map((p) => `${p.tipo === 'transmitir' ? `Transmitindo ${e(nomeDe(p.cnpjs[0]))}` : 'Conferindo a DCTFWeb'}${p.status === 'novo' ? ' (na fila)' : '…'}`).join(' · ')}</span></div>` : ''}
      </div><div class="rf-ctl"><div>${tp.sel}</div><div><button class="rf-pill g" id="dcAtualizar" ${fila.some((p) => p.tipo === 'conferir') || !rb.ativo ? 'disabled' : ''}>Atualizar DCTFWeb</button></div></div></div>
      ${R.dc.erro ? `<div class="rf-aviso">${e(R.dc.erro)}</div>` : ''}
      ${rb.ativo && !rb.online ? '<div class="rf-aviso">O computador do escritório que fala com o Integra Contador está desligado ou com o FiscoCont+ fechado: os pedidos ficam na fila e são atendidos quando ele voltar.</div>' : ''}
      <div class="dc-g">
        <div class="rf-card rf-tab"><h3>Débitos da REINF na DCTFWeb <small>por código de receita · clique na empresa</small></h3>
          ${L.length ? `<table><thead><tr><th>Empresa</th><th class="n">Débitos REINF</th><th class="n">Na DCTFWeb</th><th>DCTFWeb</th><th>Situação</th></tr></thead><tbody>
          ${L.map((l) => `<tr data-dc="${e(l.cnpj)}" class="${l.cnpj === R.dcSel ? 'sel' : ''}"><td class="dc-emp"><b>${e(l.nome)}</b><small>${e(fmtCnpj(l.cnpj))} · <i class="dc-rs ${(RST[l.doc.status] || ['nm'])[0]}">REINF ${e(((RST[l.doc.status] || ['', l.doc.status])[1] || '').toLowerCase())}</i></small></td>
            <td class="n">${brl(l.tReinf)}</td><td class="n">${l.tDctf == null ? '—' : brl(l.tDctf)}</td>
            <td>${l.cmp === 'diverge' ? `<span class="rf-chip er">✕ Diverge ${e(brl(Math.abs(l.dc.diferenca || 0)))}</span>` : l.cmp ? ch2(CMP, l.cmp) : '<span class="rf-chip nm">ainda não conferida</span>'}</td>
            <td>${l.dc && l.dc.situacao ? ch2(SDC, l.dc.situacao) : '<span class="rf-chip nm">—</span>'}</td></tr>`).join('')}</tbody></table>`
            : '<div class="rf-vz">Nenhuma empresa conferida na REINF nesta competência. Faça a conferência na aba Retenções.</div>'}</div>
        <div class="rf-card dc-lado">${painelDctf(sel, fila)}</div>
      </div>`;
    ligarDctf(sel);
    if (R.anim) { R.anim = false; raiz().querySelectorAll('[data-n]').forEach((b) => { const alvo = +b.dataset.n, t0 = performance.now(); const p = (now) => { const k = Math.min(1, (now - t0) / 800); b.textContent = Math.round(alvo * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(p); }; requestAnimationFrame(p); }); }
  }
  function painelDctf(l, fila) {
    if (!l) return '<div class="rf-vz">Escolha uma empresa na lista.</div>';
    const x = l.dc;
    if (!x) return `<h3><span>${e(l.nome)}</span>${ch2(RST, l.doc.status)}</h3><div class="rf-vz">${l.doc.status === 'aberto' ? 'A REINF está aberta: feche o período (R-4099/R-2099) para os débitos irem para a DCTFWeb.' : 'Ainda não conferida na DCTFWeb. Clique em "Atualizar DCTFWeb".'}</div>`;
    const cods = [...new Set([...Object.keys(x.esperado || {}), ...Object.keys(x.naDctf || {})])].sort();
    const [a, m] = R.comp.split('-').map(Number);
    let venc = new Date(a, m + 1, 0); while ([0, 6].includes(venc.getDay())) venc.setDate(venc.getDate() - 1);
    const naFila = fila.some((p) => p.tipo === 'transmitir' && p.cnpjs.includes(l.cnpj));
    const orig = x.origens || {}, outras = Object.entries(orig).filter(([k, v]) => !/^REINF/.test(k) && v > 0);
    return `<h3><span>${e(l.nome)}</span>${x.comparacao === 'diverge' ? `<span class="rf-chip er">✕ Diverge ${e(brl(Math.abs(x.diferenca || 0)))}</span>` : ch2(CMP, x.comparacao)}</h3>
      <div class="dc-sub">DCTFWeb ${compBr(R.comp)} · categoria Geral · <b>${e((SDC[x.situacao] || ['', x.situacao || '—'])[1].toLowerCase())}</b> · vence ${venc.toLocaleDateString('pt-BR')} (último dia útil)</div>
      ${x.msg && ['erro', 'semproc', 'sem_declaracao'].includes(x.situacao) ? `<div class="dc-msg">${e(x.msg)}</div>` : ''}
      ${cods.length && x.fonte === 'api' ? `<table class="dc-cmp"><thead><tr><th>Código de receita</th><th class="n">Débito na DCTFWeb</th></tr></thead><tbody>
        ${cods.map((c) => `<tr><td>${e(c)} · ${e(NOMECR[c] || NOMECR[+c] || 'código de receita')}</td><td class="n">${(x.naDctf || {})[c] == null ? '—' : brl(x.naDctf[c])}</td></tr>`).join('')}
        <tr class="tot"><td>Total</td><td class="n">${x.naDctf ? brl(somaM(x.naDctf)) : '—'}</td></tr></tbody></table>
        <div class="dc-sub">REINF fechada na Receita${l.doc.fech4099 && l.doc.fech4099.recibo ? ` · R-4099 recibo ${e(l.doc.fech4099.recibo)}` : ''}${l.doc.fech2099 && l.doc.fech2099.recibo ? ` · R-2099 recibo ${e(l.doc.fech2099.recibo)}` : ''}</div>`
      : cods.length ? `<table class="dc-cmp"><thead><tr><th>Código de receita</th><th class="n">REINF</th><th class="n">DCTFWeb</th></tr></thead><tbody>
        ${cods.map((c) => { const r = (x.esperado || {})[c] || 0, d = (x.naDctf || {})[c]; const ok = d != null && Math.abs(r - d) <= 0.01;
          return `<tr><td>${e(c)} · ${e(NOMECR[c] || NOMECR[+c] || 'código de receita')}</td><td class="n">${brl(r)}</td><td class="n ${ok ? '' : 'dif'}">${d == null ? '—' : brl(d)} ${ok ? '✓' : '✕'}</td></tr>`; }).join('')}
        <tr class="tot"><td>Total</td><td class="n">${brl(somaM(x.esperado))}</td><td class="n">${x.naDctf ? brl(somaM(x.naDctf)) : '—'}</td></tr></tbody></table>` : ''}
      ${outras.length ? `<div class="dc-orig">A declaração também tem débitos de: ${outras.map(([k, v]) => `<b>${e(k)}</b> ${e(brl(v))}`).join(' · ')}${x.situacao === 'em_andamento' ? '. Com eSocial ou MIT na declaração, o sistema não transmite: a DCTFWeb é transmitida pelo e-CAC depois que a folha e o MIT estiverem fechados.' : ''}</div>` : ''}
      ${x.situacao === 'transmitida'
        ? `<div class="dc-ok">✓ Transmitida${x.transmitidaEm ? ` em ${e(curta(x.transmitidaEm))}` : ''}${x.transmitidaPor ? ` por ${e(x.transmitidaPor)}` : ''}${x.recibo ? `<br>Recibo ${e(x.recibo)}` : ''}</div>${x.arquivo ? '<button class="btn-dc sec" id="dcRecibo">📄 Abrir o recibo</button>' : ''}${x.reciboAviso ? `<div class="dc-msg">${e(x.reciboAviso)}</div>` : ''}`
        : x.podeTransmitir ? `<button class="btn-dc go" id="dcTransmitir" ${naFila ? 'disabled' : ''}>${naFila ? 'Transmissão na fila…' : `Transmitir DCTFWeb ${compBr(R.comp)}`}</button>`
          : `<button class="btn-dc off" disabled>${x.comparacao === 'sem_dctf' ? 'Sem DCTFWeb no período' : x.comparacao === 'diverge' || x.comparacao === 'nao_apareceu' ? 'Diverge / não apareceu: transmissão bloqueada' : x.reinfStatus !== 'fechado' ? 'Transmissão bloqueada até fechar a REINF' : outras.length && x.situacao === 'em_andamento' ? 'Tem eSocial/MIT: transmitir pelo e-CAC' : 'Nada a transmitir'}</button>`}
      ${x.ultimoErro ? `<div class="dc-msg">Última tentativa: ${e(x.ultimoErro)}</div>` : ''}
      <div class="dc-nota"><b>Como funciona</b>
        <div><span>1</span><p>O botão só fica ativo quando a REINF está <b>fechada</b> na Receita, a DCTFWeb está <b>em andamento</b> ${x.fonte === 'api' ? 'com os débitos que vieram da REINF' : 'e todos os códigos <b>conferem</b>'} e a declaração só tem débitos da REINF (sem eSocial nem MIT).</p></div>
        <div><span>2</span><p>Você confirma; o pedido vai para o computador do escritório que tem o Integra Contador, que confere de novo e transmite.</p></div>
        <div><span>3</span><p>Transmitida: o recibo fica na linha e o PDF vai para a pasta do cliente (Relatórios › ${R.comp.slice(0, 4)} › ${R.comp.slice(5, 7)}).</p></div></div>`;
  }
  function confirmar(l) {
    return new Promise((ok) => {
      const x = l.dc, orig = x.origens || {};
      const outras = Object.entries(orig).filter(([k, v]) => !/^REINF/.test(k) && v > 0);
      const m = document.createElement('div'); m.className = 'rf-modal';
      m.innerHTML = `<div class="rf-mc dc-conf"><h3>Transmitir a DCTFWeb ${compBr(R.comp)}?</h3>
        <p><b>${e(l.nome)}</b> · ${e(fmtCnpj(l.cnpj))}<br>Débitos da REINF: <b>${e(brl(somaM(x.esperado)))}</b> (${x.fonte === 'api' ? 'os que estão na DCTFWeb, vindos do fechamento da REINF' : 'conferem com o fechamento'}).</p>
        <p>A declaração só tem os débitos da REINF. Se ainda entrar folha (eSocial) ou MIT nesta competência, a DCTFWeb terá de ser retificada.</p>
        <p class="dc-irr">A transmissão é feita na Receita Federal e não pode ser desfeita por aqui.</p>
        <div class="rf-mb"><button class="rf-pill" id="dcNao">Cancelar</button><button class="rf-pill g" id="dcSim">Transmitir</button></div></div>`;
      m.querySelector('#dcNao').onclick = () => { m.remove(); ok(false); };
      m.querySelector('#dcSim').onclick = () => { m.remove(); ok(true); };
      document.body.appendChild(m);
    });
  }
  function ligarDctf(sel) {
    const r = raiz();
    r.querySelectorAll('[data-aba]').forEach((b) => b.addEventListener('click', () => { R.aba = b.dataset.aba; R.anim = true; if (R.aba === 'dctf') carregarDctf(); else { clearTimeout(pollDc); desenhar(); } }));
    const c = document.getElementById('rfComp'); if (c) c.onchange = () => { R.comp = c.value; R.dc = null; R.dcSel = ''; carregar(); };
    r.querySelectorAll('[data-dc]').forEach((t) => t.addEventListener('click', () => { R.dcSel = t.dataset.dc; desenhar(); }));
    const at = document.getElementById('dcAtualizar');
    if (at) at.onclick = async () => { at.disabled = true; const x = await window.fiscocont.reinf.dctfPedir({ tipo: 'conferir', comp: R.comp });
      if (x && x.error) toast(x.error, true); else toast(x.roboOnline ? 'Conferência da DCTFWeb pedida: o resultado aparece aqui em instantes.' : 'Pedido na fila: o computador do Integra Contador está offline e confere quando voltar.'); carregarDctf(true); };
    const tr = document.getElementById('dcTransmitir');
    if (tr && sel) tr.onclick = async () => { if (!(await confirmar(sel))) return; tr.disabled = true;
      const x = await window.fiscocont.reinf.dctfPedir({ tipo: 'transmitir', comp: R.comp, cnpj: sel.cnpj });
      if (x && x.error) toast(x.error, true); else toast('Transmissão pedida: acompanhe aqui.'); carregarDctf(true); };
    const rc = document.getElementById('dcRecibo');
    if (rc && sel) rc.onclick = async () => { const x = await window.fiscocont.reinf.dctfAbrir({ caminho: sel.dc.arquivo }); if (x && x.error) toast(x.error, true); };
  }

  // ------------------------------------------------------------------ animação (pizza abrindo, números contando, barras)
  function animar() {
    const r = raiz();
    if (!R.anim) { r.querySelectorAll('.rf-pizza').forEach((s) => pizza(s, 1)); r.querySelectorAll('.bar i, .rf-be i').forEach((i) => { i.style.width = i.style.getPropertyValue('--w'); }); return; }
    R.anim = false;
    const t0 = performance.now(), dur = 1100, ease = (x) => 1 - Math.pow(1 - x, 3);
    const conts = [...r.querySelectorAll('[data-cont]')].map((el) => ({ el, v: +el.dataset.cont }));
    const pz = [...r.querySelectorAll('.rf-pizza')];
    r.querySelectorAll('.bar i, .rf-be i').forEach((i) => { i.style.width = '0'; requestAnimationFrame(() => { i.style.width = i.style.getPropertyValue('--w'); }); });
    const passo = (now) => {
      const p = ease(Math.min(1, (now - t0) / dur));
      conts.forEach(({ el, v }) => { el.textContent = brl(v * p); });
      pz.forEach((s) => pizza(s, p));
      if (p < 1) requestAnimationFrame(passo); else conts.forEach(({ el, v }) => { el.textContent = brl(v); });
    };
    requestAnimationFrame(passo);
  }
  function pizza(svg, p) {
    const vals = JSON.parse(svg.dataset.vals || '{}');
    const tot = KS.reduce((a, k) => a + (vals[k] || 0), 0); if (!tot) return;
    const R0 = 118, cx = 150, cy = 150;
    const mx = KS.reduce((a, k) => ((vals[k] || 0) > (vals[a] || 0) ? k : a), KS[0]);
    let a0 = -Math.PI / 2 + (1 - p) * -1.2, out = '', labs = '', defs = '';
    for (const k of KS) {
      const v = vals[k] || 0; if (!v) continue;
      const f = v / tot * p, a1 = a0 + f * 2 * Math.PI, mid = (a0 + a1) / 2, ex = k === mx ? 9 * p : 0;
      const dx = Math.cos(mid) * ex, dy = Math.sin(mid) * ex;
      const x0 = cx + dx + R0 * Math.cos(a0), y0 = cy + dy + R0 * Math.sin(a0), x1 = cx + dx + R0 * Math.cos(a1), y1 = cy + dy + R0 * Math.sin(a1);
      defs += `<radialGradient id="rfg${k}" cx="35%" cy="30%" r="90%"><stop offset="0" stop-color="${COR[k]}" stop-opacity=".75"/><stop offset="1" stop-color="${COR[k]}"/></radialGradient>`;
      out += f >= 0.9999 ? `<circle cx="${cx}" cy="${cy}" r="${R0}" fill="url(#rfg${k})"/>` : `<path d="M${cx + dx},${cy + dy} L${x0},${y0} A${R0},${R0} 0 ${f > 0.5 ? 1 : 0} 1 ${x1},${y1} Z" fill="url(#rfg${k})" stroke="var(--panel,#fff)" stroke-width="3"/>`;
      if (p > 0.85 && v / tot > 0.045) labs += `<text x="${cx + dx + R0 * 0.64 * Math.cos(mid)}" y="${cy + dy + R0 * 0.64 * Math.sin(mid) + 4}" text-anchor="middle" font-size="13" font-weight="800" fill="#fff" opacity="${(p - 0.85) / 0.15}">${Math.round(v / tot * 100)}%</text>`;
      a0 = a1;
    }
    svg.innerHTML = `<defs>${defs}<filter id="rfsh"><feDropShadow dx="0" dy="8" stdDeviation="9" flood-color="#1e293b" flood-opacity=".18"/></filter></defs><g filter="url(#rfsh)">${out}</g>${labs}`;
  }

  // ------------------------------------------------------------------ ações
  function ligaConferir() {
    const bt = document.getElementById('rfConferir'); if (!bt) return;
    bt.onclick = async () => {
      if (bt.dataset.parar) { await window.fiscocont.reinf.parar(); return; }
      R.prog = { txt: 'Iniciando a conferência…' };
      const p = document.getElementById('rfProg'); if (p) { p.hidden = false; p.querySelector('span').textContent = R.prog.txt; }
      bt.outerHTML = botaoConferir(); ligaConferir();
      const r = await window.fiscocont.reinf.conferir({ comp: R.comp, cnpjs: R.emp ? [R.emp] : null });
      R.prog = null;
      if (r && r.error) toast(r.error, true); else if (r) toast(`Conferência concluída: ${r.ok} empresa(s)${r.erros ? `, ${r.erros} com erro` : ''}.`);
      carregar();
    };
  }
  function ligar() {
    const r = raiz();
    const c = document.getElementById('rfComp'); if (c) c.onchange = () => { R.comp = c.value; R.dc = null; R.dcSel = ''; carregar(); };
    const em = document.getElementById('rfEmp');
    if (em) em.onchange = () => { const v = em.value.trim(); const l = linhas().find((x) => x.nome === v || x.cnpj === v.replace(/\D/g, '')); R.emp = l ? l.cnpj : ''; R.anim = true; desenhar(); };
    r.querySelectorAll('[data-emp]').forEach((b) => b.addEventListener('click', () => { R.emp = b.dataset.emp; R.anim = true; desenhar(); r.scrollIntoView({ block: 'start' }); }));
    const v = document.getElementById('rfVolta'); if (v) v.onclick = (ev) => { ev.preventDefault(); R.emp = ''; R.anim = true; desenhar(); };
    r.querySelectorAll('[data-aba]').forEach((b) => b.addEventListener('click', () => { R.aba = b.dataset.aba; R.anim = true; if (R.aba === 'dctf') carregarDctf(); else desenhar(); }));
    ligaConferir();
    const doc = R.emp ? docDe(R.emp) : null;
    r.querySelectorAll('[data-tot]').forEach((b) => b.addEventListener('click', async () => {
      const f = doc && (b.dataset.tot === '4099' ? doc.fech4099 : doc.fech2099);
      const x = f && f.pdf ? await window.fiscocont.reinf.abrir({ caminho: f.pdf }) : { error: 'x' };
      if (x && x.error) toast('O PDF do totalizador não está neste computador.', true);
    }));
    const ps = document.getElementById('rfPasta');
    if (ps) ps.onclick = async () => { const f = doc && (doc.fech4099 || {}).pdf ? doc.fech4099.pdf : doc && doc.pasta; const x = await window.fiscocont.reinf.abrir({ caminho: f, pasta: true }); if (x && x.error) toast(x.error, true); };
    const bl = document.getElementById('rfLista'), mn = document.getElementById('rfListaMenu');
    if (bl) { bl.onclick = (ev) => { ev.stopPropagation(); mn.hidden = !mn.hidden; };
      mn.querySelectorAll('[data-l]').forEach((b) => b.addEventListener('click', () => gerarLista(b.dataset.l))); }
    const be = document.getElementById('rfEmps'); if (be) be.onclick = empresasModal;
  }

  function dadosLista() {
    const ls = linhas();
    return { comp: R.comp, sub: `Conferido na Receita Federal${R.d.meta && R.d.meta.fim ? ` em ${curta(R.d.meta.fim)}` : ''} · ${ls.length} empresas`,
      empresas: ls.map((l) => ({ nome: l.nome, cnpj: l.cnpj, cnpjFmt: fmtCnpj(l.cnpj), totais: l.doc && !['sem_procuracao', 'erro'].includes(l.sit) ? l.doc.totais : null, nEventos: l.doc ? (l.doc.eventos || []).length : 0,
        situacao: ST[l.sit][1], recibo: l.doc ? ((l.doc.fech4099 || {}).fechado ? l.doc.fech4099.recibo : (l.doc.fech2099 || {}).fechado ? l.doc.fech2099.recibo : '') : '',
        enviado: l.doc ? curta((l.doc.fech4099 || {}).dhProcess || (l.doc.fech4099 || {}).recepcao || '') : '', eventos: l.doc ? (l.doc.eventos || []) : [] })) };
  }
  async function gerarLista(tipo) {
    const dd = dadosLista(), nome = `EFD-Reinf retenções ${R.comp.slice(5, 7)}${R.comp.slice(0, 4)}`;
    if (tipo === 'xlsx') { const r = await window.fiscocont.reinf.listaXlsx({ dados: dd, nome }); if (r && r.error) toast(r.error, true); return; }
    let logo = '';
    try { const b = await (await fetch('img/liddera-logo.png')).blob(); logo = await new Promise((ok) => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.readAsDataURL(b); }); } catch (_) {}
    const ks = KS, T = {};
    ks.forEach((k) => { T[k] = dd.empresas.reduce((a, x) => a + ((x.totais && x.totais[k]) || 0), 0); });
    const TT = ks.reduce((a, k) => a + T[k], 0);
    const html = `<!doctype html><html><head><meta charset="utf-8"><style>
      body{font:11px/1.4 "Segoe UI",Inter,Arial,sans-serif;color:#0f172a;margin:0;padding:6px}.hd{display:flex;align-items:center;gap:14px;border-bottom:3px solid #e8632b;padding-bottom:10px;margin-bottom:12px}
      .hd img{width:48px;height:48px;border-radius:50%}.hd h2{margin:0;font-size:17px}.hd small{color:#64748b}.sp{flex:1}.tt{text-align:right}.tt b{display:block;font-size:18px}
      table{width:100%;border-collapse:collapse}th{text-align:left;color:#64748b;font-size:9.5px;text-transform:uppercase;border-bottom:1px solid #e2e8f0;padding:5px}td{padding:5px;border-bottom:1px solid #f1f5f9;vertical-align:top}
      .n{text-align:right;font-variant-numeric:tabular-nums}td small{display:block;color:#94a3b8}.tot td{background:#f1f5f9;font-weight:700}.er{color:#b91c1c;font-weight:600}.rec{font-family:Consolas,monospace;font-size:9.5px}
      p{color:#64748b;font-size:9.5px;margin-top:10px}tr{page-break-inside:avoid}</style></head><body>
      <div class="hd">${logo ? `<img src="${logo}">` : ''}<div><h2>EFD-Reinf · retenções por empresa</h2><small>Competência ${compBr(R.comp)} · ${e(dd.sub)}</small></div><div class="sp"></div><div class="tt"><small>Total retido</small><b>${brl(TT)}</b></div></div>
      <table><thead><tr><th>Empresa</th>${ks.map((k) => `<th class="n">${k === 'agreg' ? 'Agregada' : k === 'inss' ? 'INSS' : k === 'funrural' ? 'Funrural' : NOME[k]}</th>`).join('')}<th class="n">Total</th><th>Situação</th><th>Recibo de envio</th></tr></thead><tbody>
      ${dd.empresas.map((x) => `<tr><td><b>${e(x.nome)}</b><small>${e(x.cnpjFmt)}</small></td>${x.totais ? ks.map((k) => `<td class="n">${x.totais[k] ? num(x.totais[k]) : '—'}</td>`).join('') + `<td class="n"><b>${num(ks.reduce((a, k) => a + (x.totais[k] || 0), 0))}</b></td>`
        : `<td colspan="8" class="${/procura/i.test(x.situacao) ? 'er' : ''}">${/procura/i.test(x.situacao) ? 'Sem procuração eletrônica para a EFD-Reinf' : e(x.situacao)}</td>`}<td>${e(x.situacao)}</td><td>${x.recibo ? `<span class="rec">${e(x.recibo)}</span><small>${e(x.enviado)}</small>` : '—'}</td></tr>`).join('')}
      <tr class="tot"><td>Total</td>${ks.map((k) => `<td class="n">${num(T[k])}</td>`).join('')}<td class="n">${num(TT)}</td><td></td><td></td></tr></tbody></table>
      <p>Situação e recibo do fechamento (R-4099/R-2099) consultados no serviço oficial da EFD-Reinf; valores por imposto: débitos da REINF na DCTFWeb do período. Liddera | Inteligência em Negócios.</p></body></html>`;
    const r = await window.fiscocont.reinf.listaPdf({ html, nome });
    if (r && r.error) toast(r.error, true);
  }

  // empresas conferidas (lista na nuvem): marcar/desmarcar e incluir
  async function empresasModal() {
    const r = await window.fiscocont.reinf.empresas();
    if (r && r.error) { toast(r.error, true); return; }
    const lista = r.lista || [];
    const m = document.createElement('div'); m.className = 'rf-modal';
    const pinta = () => {
      m.innerHTML = `<div class="rf-mc"><h3>Empresas da conferência <small>${lista.filter((x) => x.ativa !== false).length} de ${lista.length} marcadas</small></h3>
        <input class="rf-in" id="rfMBusca" placeholder="Buscar"><div class="rf-ml">${lista.map((x, i) => `<label data-n="${e((x.nome + ' ' + x.cnpj).toUpperCase())}"><input type="checkbox" data-i="${i}" ${x.ativa !== false ? 'checked' : ''}> ${e(x.nome)} <small>${e(fmtCnpj(x.cnpj))}</small></label>`).join('')}</div>
        <div class="rf-madd"><input class="rf-in" id="rfMNome" placeholder="Nome da empresa"><input class="rf-in" id="rfMCnpj" placeholder="CNPJ"><button class="rf-pill" id="rfMAdd">Incluir</button></div>
        <div class="rf-mb"><button class="rf-pill" id="rfMCanc">Cancelar</button><button class="rf-pill g" id="rfMOk">Salvar</button></div></div>`;
      m.querySelector('#rfMBusca').oninput = (ev) => { const q = ev.target.value.toUpperCase(); m.querySelectorAll('.rf-ml label').forEach((l) => { l.hidden = q && !l.dataset.n.includes(q) && !l.dataset.n.includes(q.replace(/\D/g, '') || '§'); }); };
      m.querySelectorAll('[data-i]').forEach((c) => { c.onchange = () => { lista[+c.dataset.i].ativa = c.checked; }; });
      m.querySelector('#rfMAdd').onclick = () => { const n = m.querySelector('#rfMNome').value.trim(), c = m.querySelector('#rfMCnpj').value.replace(/\D/g, ''); if (!n || c.length !== 14) { toast('Informe o nome e os 14 números do CNPJ.', true); return; } lista.push({ nome: n, cnpj: c, ativa: true }); lista.sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR')); pinta(); };
      m.querySelector('#rfMCanc').onclick = () => m.remove();
      m.querySelector('#rfMOk').onclick = async () => { const x = await window.fiscocont.reinf.empresas(lista); if (x && x.error) { toast(x.error, true); return; } m.remove(); toast('Empresas da conferência salvas.'); carregar(true); };
    };
    pinta();
    document.body.appendChild(m);
  }

  // cartão do menu: situação da competência padrão
  function menu() {
    const s = document.getElementById('reinfResumo'); if (!s || !R.d) return;
    const ls = linhas();
    const ab = ls.filter((l) => ['aberto', 'sem_procuracao', 'erro', 'tarde'].includes(l.sit)).length;
    s.textContent = !ls.some((l) => l.doc) ? `Conferência ${compBr(R.comp)}` : ab ? `${ab} empresa(s) para olhar` : 'todas conferidas';
  }
  document.addEventListener('click', () => { const mn = document.getElementById('rfListaMenu'); if (mn) mn.hidden = true; });
  window._reinfEntrar = entrar;
  // resumo do menu ao abrir o sistema (sem abrir a tela)
  setTimeout(async () => { try { if (window.fiscocont.reinf && document.querySelector('[data-view="fiscal-reinf"]:not(.role-hidden)')) { const d = await window.fiscocont.reinf.dados(null); if (d && !d.error) { R.d = d; R.comp = d.comp; menu(); } } } catch (_) {} }, 8000);
})();

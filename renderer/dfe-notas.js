'use strict';
// Baixas DF-e · NF-e Entradas, NF-e Saídas, NFC-e Saídas e CT-e Entradas — nos mesmos botões da tela "Baixar NFS-e".
//   Entradas (todas as empresas): NF-e e CT-e pelo Ambiente Nacional, com o certificado cadastrado; Ciência da Operação
//   automática só nas notas que vierem como resumo (nota já manifestada vem completa e é só baixada).
//   Saídas (só empresas de RO): NF-e e NFC-e pelo DFe-Download da SEFIN, reaproveitando o pedido do mês já feito. A página da
//   SEFIN fica escondida: só a imagem do código aparece aqui, a pessoa digita e o sistema baixa todas as partes do arquivo.
// Os botões "Baixar NFS-e" e "Baixar em lote" passam a baixar o que estiver marcado: NFS-e continua no fluxo de sempre.
(function () {
  const NOVO_ATE = '2026-11-24T23:59:59';
  const X = { iniciado: false, rodando: false, emps: [], pasta: '', repassa: false, comp: '' };
  const q = (s) => document.querySelector(s);
  const e = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const brl = (v) => Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const aviso = (m, erro) => { if (typeof toast === 'function') toast(m, erro); };
  const ehAdmin = () => typeof ROLE !== 'undefined' && ROLE === 'admin';
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const CSS = `
  .dl-tipos{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-start}
  .dl-tipo{position:relative;flex:0 0 auto;width:auto;min-width:0;height:auto;line-height:1.3;font:inherit;font-size:12px;padding:6px 13px;border-radius:16px;border:1.5px solid var(--line);background:var(--bg,#f4f6fb);color:var(--ink2);cursor:pointer;transition:all .15s}
  .dl-tipo:hover{border-color:#e8632b}
  .dl-tipo.on{background:#faeeda;color:#854f0b;border-color:#f0c078;font-weight:600}
  .dl-novo{font-style:normal;font-size:8.5px;font-weight:800;letter-spacing:.06em;color:#fff;background:linear-gradient(90deg,#e8632b,#ff9860);border-radius:8px;padding:1px 5px;margin-left:6px;vertical-align:2px;box-shadow:0 2px 6px rgba(232,99,43,.35)}
  .dfe-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-top:14px}
  .dfe-h{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.dfe-h b{font-size:14px}.dfe-h .sp{flex:1}
  .dfe-prog{font-size:12.5px;color:#2f4090;margin-top:8px;min-height:18px}.dfe-prog.esp{color:#c2410c;font-weight:700}
  .dfe-t{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:8px}
  .dfe-t th{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--ink2);padding:7px 8px;border-bottom:1.5px solid var(--line)}
  .dfe-t td{padding:8px;border-bottom:1px solid var(--line);vertical-align:top}.dfe-t td small{display:block;color:var(--ink2);font-size:11px;margin-top:3px;line-height:1.35}
  .dfe-st{display:inline-block;border-radius:20px;padding:3px 9px;font-size:11px;font-weight:700;white-space:nowrap}
  .dfe-ok{background:#e3f7ee;color:#0f7a52}.dfe-ag{background:#fff4dd;color:#9a6200}.dfe-pr{background:#e8f0ff;color:#2f4090}.dfe-er{background:#fdeaea;color:#b42323}.dfe-nr{background:#eef0f6;color:#475569}
  .dfe-lk{color:#2f4090;font-weight:700;font-size:11.5px;cursor:pointer;background:none;border:none;padding:0;margin-top:3px}
  .dfe-uf{font-size:10.5px;font-weight:800;border-radius:6px;padding:2px 6px;background:#eef0f6;color:#475569}.dfe-uf.ro{background:#e8f0ff;color:#2f4090}
  .dfe-pasta{font-size:11.5px;color:var(--ink2);margin-top:10px}
  .dfe-rel{display:inline-flex;align-items:center;gap:6px;margin-top:6px;font:inherit;font-size:11.5px;font-weight:700;color:#fff;background:linear-gradient(90deg,#2f4090,#4f46e5);border:none;border-radius:8px;padding:4px 10px;cursor:pointer;box-shadow:0 3px 10px rgba(79,70,229,.25)}
  .dfe-rel svg{width:13px;height:13px}
  .dfe-rel:hover{filter:brightness(1.08)}
  .dfe-rel-q{display:block;color:var(--ink2);font-size:10.5px;margin-top:3px}
  .dfe-cod-bg{position:fixed;inset:0;background:rgba(20,24,50,.55);z-index:9700;display:flex;align-items:center;justify-content:center;animation:dfeIn .18s ease}
  @keyframes dfeIn{from{opacity:0}to{opacity:1}}
  .dfe-cod{background:#fff;border-radius:18px;width:min(440px,92vw);overflow:hidden;box-shadow:0 24px 70px rgba(0,0,0,.35)}
  .dfe-cod-h{background:linear-gradient(120deg,#1f2a5a,#2b3a72);color:#fff;padding:15px 20px;display:flex;align-items:flex-start;gap:10px}
  .dfe-cod-h b{font-size:14px;display:block}.dfe-cod-h small{font-size:11.5px;color:#c7cbe8;display:block;margin-top:3px;line-height:1.35}
  .dfe-cod-h .x{margin-left:auto;background:none;border:none;color:#fff;font-size:20px;cursor:pointer;line-height:1}
  .dfe-cod-b{padding:18px 20px 6px}
  .dfe-cod-img{display:flex;align-items:center;justify-content:center;background:#f4f6fb;border:1px solid #e3e6f0;border-radius:12px;min-height:84px;padding:10px}
  .dfe-cod-img img{max-width:100%;max-height:120px;image-rendering:auto}
  .dfe-cod-parte{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0 4px;font-size:11.5px;color:#475569}
  .dfe-cod-parte span{background:#eef0f6;border-radius:12px;padding:2px 9px}.dfe-cod-parte span.on{background:#e8f0ff;color:#2f4090;font-weight:700}
  .dfe-cod-erro{background:#fdeaea;color:#b42323;border-radius:10px;padding:7px 10px;font-size:12px;margin-top:10px}
  .dfe-cod-erro b{font-weight:700}
  .dfe-cod-av{background:#fff4dd;color:#8a5a00;border-radius:10px;padding:7px 10px;font-size:12px;margin-top:10px}
  .dfe-cod-b label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#8890ab;margin:14px 0 5px}
  .dfe-cod-b input{width:100%;box-sizing:border-box;font:inherit;font-size:20px;letter-spacing:.18em;text-align:center;padding:10px 12px;border:1.5px solid #d6dae8;border-radius:12px;outline:none}
  .dfe-cod-b input:focus{border-color:#e8632b;box-shadow:0 0 0 4px rgba(232,99,43,.12)}
  .dfe-cod-f{display:flex;gap:10px;align-items:center;padding:14px 20px 18px}
  .dfe-cod-f .sp{flex:1}.dfe-cod-f .lk{background:none;border:none;color:#8890ab;font:inherit;font-size:12px;cursor:pointer;padding:0}
  .dfe-cod-f .ok{background:linear-gradient(90deg,#e8632b,#ff9860);color:#fff;border:none;font-weight:700;border-radius:10px;padding:10px 22px;font:inherit;font-size:13.5px;font-weight:700;cursor:pointer}
  .dfe-cod-f .ok:disabled{opacity:.5;cursor:default}`;

  const tipos = () => [...document.querySelectorAll('#dlTipos .dl-tipo.on')].map((b) => b.dataset.tipo);
  const novos = () => tipos().filter((t) => t !== 'nfse');
  const ent = () => ['nfe-e', 'cte-e'].filter((t) => tipos().includes(t)).map((t) => t.split('-')[0]);
  const sai = () => ['nfe-s', 'nfce-s'].filter((t) => tipos().includes(t)).map((t) => t.split('-')[0]);
  function meses() {
    const ini = (q('#dlDataInicial').value || '').slice(0, 7), fim = (q('#dlDataFinal').value || '').slice(0, 7) || ini;
    if (!ini) return [];
    const out = []; let [a, m] = ini.split('-').map(Number);
    for (let i = 0; i < 6; i++) { const c = `${a}-${String(m).padStart(2, '0')}`; out.push(c); if (c >= fim) break; m++; if (m > 12) { m = 1; a++; } }
    return out;
  }
  const compRot = (c) => c ? c.split('-').reverse().join('/') : '';

  function ajustaTela() {
    const t = tipos();
    const so = t.length === 1 && t[0] === 'nfse';
    const b = q('#btnDlBaixar'); if (b) b.textContent = so || !t.length ? 'Baixar NFS-e' : 'Baixar notas';
    const cb = q('#dlCienciaBox'); if (cb) cb.hidden = !(ehAdmin() && t.includes('nfe-e'));
    const pdf = q('#dlGerarPdf');
    if (pdf) {
      const lab = pdf.closest('label'), docs = [];
      if (t.includes('nfse')) docs.push('DANFSe');
      if (t.includes('nfe-e') || t.includes('nfe-s')) docs.push('DANFE');
      if (t.includes('cte-e')) docs.push('DACTE');
      lab.hidden = !docs.length;
      const tx = [...lab.childNodes].find((n) => n.nodeType === 3 && n.textContent.trim());
      if (tx) tx.textContent = ` Gerar também o PDF de cada nota (${docs.join(' · ')})`;
    }
    const card = q('#dfeCard');
    if (card) { card.hidden = !novos().length && !X.mostrou; if (!card.hidden) { montarCard(); atualizar(); } }
  }

  function montarCard() {
    const box = q('#dfeCard');
    if (box.dataset.ok) return;
    box.dataset.ok = '1';
    box.innerHTML = `
      <div class="dfe-h"><b>NF-e, NFC-e e CT-e · situação</b><span id="dfeComp" style="font-size:12px;color:var(--ink2)"></span><span class="sp"></span>
        <button class="act inv-export" id="dfeGeraRel" title="Gera de novo o relatório (e os PDFs que faltarem) com os XMLs que já estão na pasta">Gerar relatório</button>
        <button class="act inv-export" id="dfeAtualiza">Atualizar</button>
        <button class="act inv-export" id="dfeLog" title="Abre a pasta de dados: dfe_ro_log.txt (passo a passo no site da SEFIN) e dfe_ro_ultima.png">Passo a passo</button></div>
      <div class="dfe-prog" id="dfeProg"></div>
      <table class="dfe-t" id="dfeTab" hidden><thead><tr><th>Empresa</th><th>UF</th><th>NF-e Entradas</th><th>CT-e Entradas</th><th>NF-e Saídas</th><th>NFC-e Saídas</th></tr></thead><tbody id="dfeBody"></tbody></table>
      <div class="dfe-pasta" id="dfePasta"></div>`;
    q('#dfeAtualiza').addEventListener('click', atualizar);
    q('#dfeGeraRel').addEventListener('click', async () => {
      if (X.rodando) return;
      const ms = meses(); if (!ms.length) { aviso('Escolha o período (data inicial e final).', true); return; }
      const id = q('#dlSelectEmpresa') ? q('#dlSelectEmpresa').value : '';
      X.rodando = true;
      try { await gerarRelatorios(X.todas || !id ? null : [id], ms); } finally { X.rodando = false; }
    });
    q('#dfeLog').addEventListener('click', () => window.fiscocont.dfe.log());
    q('#dfeBody').addEventListener('click', (ev) => { const r = ev.target.closest('[data-rel]'); if (r) window.fiscocont.dfe.relatorioAbrir({ id: r.dataset.rel, competencia: X.comp }).then((x) => x && x.error && aviso(x.error, true)); });
    q('#dfeBody').addEventListener('click', (ev) => { const b = ev.target.closest('[data-pasta]'); if (b) window.fiscocont.dfe.abrir(b.dataset.pasta).then((r) => r && r.error && aviso(r.error, true)); });
    window.fiscocont.dfe.onProgresso((d) => { const p = q('#dfeProg'); if (p) { p.textContent = d.txt || ''; p.classList.toggle('esp', !!d.espera); } });
  }

  const ICO_REL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/></svg>';
  const chip = (cls, t) => `<span class="dfe-st ${cls}">${e(t)}</span>`;
  const pastaBt = (p) => p ? `<button class="dfe-lk" data-pasta="${e(p)}">Abrir pasta</button>` : '';
  function celEntrada(x, tipo) {
    if (!x) return chip('dfe-nr', 'não buscado');
    if (x.erro) return chip('dfe-er', 'erro') + `<small>${e(x.erro)}</small>`;
    const det = [];
    if (x.mes && x.mes.qtd) det.push(`${x.mes.qtd} ${tipo === 'cte' ? 'CT-e' : 'nota(s)'} de ${compRot(X.comp)} · R$ ${brl(x.mes.valor)}`);
    // a SEFAZ entrega por sequência (todos os meses): cada nota vai para a pasta do mês de emissão
    const outros = Object.entries(x.meses || {}).filter(([m]) => m !== X.comp).sort((a, b) => b[0].localeCompare(a[0]));
    if (outros.length) det.push(`${x.mes && x.mes.qtd ? 'Também vieram' : `Nenhuma de ${compRot(X.comp)} nesta busca. Vieram`} ${outros.map(([m, n]) => `${n} de ${m === 'sem-data' ? 'sem data' : compRot(m)}`).join(', ')}, salvas na pasta do mês de emissão`);
    const extra = [x.resumos && `${x.resumos} só resumo`, x.ciencias && `${x.ciencias} ciência(s) feita(s)`, x.canceladas && `${x.canceladas} cancelada(s)`].filter(Boolean);
    if (extra.length) det.push(extra.join(' · '));
    if (x.resumos && x.ciencias) det.push('o XML que falta chega na próxima busca (depois de 1 hora)');
    else if (x.resumos && tipo === 'nfe') det.push('o XML completo sai depois da Ciência da Operação');
    if (/libera nova consulta|aguardar/.test(x.aviso || '')) det.push(x.aviso.replace(/ \(regra da SEFAZ[^)]*\)/, ''));
    const c = x.baixadas ? chip('dfe-ok', '✓ baixado') : x.resumos ? chip('dfe-ag', 'só resumo') : /libera nova consulta|aguardar/.test(x.aviso || '') ? chip('dfe-nr', 'aguardando 1 h') : chip('dfe-nr', 'nada novo');
    return c + (det.length ? `<small>${det.map(e).join('<br>')}</small>` : '') + pastaBt(x.pasta);
  }
  const SAI = { baixado: ['dfe-ok', '✓ baixado'], aguardando: ['dfe-ag', '◷ SEFIN preparando'], solicitado: ['dfe-pr', 'pedido feito'], sem_notas: ['dfe-nr', 'nenhuma nota no período'],
    aguardando_codigo: ['dfe-pr', 'falta digitar o código'], parcial: ['dfe-ag', 'falta parte do arquivo'], cancelado: ['dfe-nr', 'cancelado'], erro: ['dfe-er', 'erro'] };
  function celSaida(x, uf) {
    if (uf && uf !== 'RO') return chip('dfe-nr', 'fora de RO: só entradas');
    if (!x) return chip('dfe-nr', 'não buscado');
    const [c, t] = SAI[x.status] || ['dfe-nr', x.status || '—'];
    const det = [];
    if (x.status === 'baixado' || (x.status === 'parcial' && x.qtd)) det.push(`${x.qtd || 0} nota(s) · R$ ${brl(x.valor)}${x.canceladas ? ` · ${x.canceladas} cancelada(s)` : ''}`);
    if (x.msg) det.push(x.msg);
    return chip(c, t) + (det.length ? `<small>${det.map(e).join('<br>')}</small>` : '') + pastaBt(x.pasta);
  }
  function desenhar() {
    const id = q('#dlSelectEmpresa') ? q('#dlSelectEmpresa').value : '';
    const lst = X.todas || !id ? X.emps : X.emps.filter((m) => m.id === id);
    q('#dfeComp').textContent = X.comp ? `· ${compRot(X.comp)}` : '';
    q('#dfeTab').hidden = !lst.length;
    q('#dfeBody').innerHTML = lst.map((m) => {
      const en = m.entradas || {}, sa = m.saidas || {};
      const rel = m.relatorio ? `<button class="dfe-rel" data-rel="${e(m.id)}" title="Abre o relatório com o painel do mês (arquivo HTML salvo na pasta da empresa)">${ICO_REL}Abrir relatório</button>`
        + `<span class="dfe-rel-q">gerado em ${new Date(m.relatorio.quando).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}${m.relatorio.pdfTotal ? ' · PDFs na pasta' : ''}</span>` : '';
      return `<tr><td><b>${e(m.nome)}</b>${m.vencido ? '<small style="color:#b42323">certificado vencido</small>' : ''}${rel}</td>
        <td><span class="dfe-uf ${m.uf === 'RO' ? 'ro' : ''}">${e(m.uf || '?')}</span></td>
        <td>${celEntrada(en.nfe, 'nfe')}</td><td>${celEntrada(en.cte, 'cte')}</td><td>${celSaida(sa.nfe, m.uf)}</td><td>${celSaida(sa.nfce, m.uf)}</td></tr>`;
    }).join('') || '';
    q('#dfePasta').innerHTML = X.pasta ? `Pastas: <b>${e(X.pasta)}</b> › MM-AAAA › empresa › <b>NF-e Entradas</b> · <b>CT-e Entradas</b> · <b>NF-e Saídas</b> · <b>NFC-e Saídas</b> (XML)` : '';
  }
  async function atualizar() {
    X.comp = meses()[0] || X.comp || '';
    if (!X.comp) { q('#dfeTab').hidden = true; q('#dfePasta').textContent = 'Informe a Data inicial e a Data final acima.'; return; }
    const r = await window.fiscocont.dfe.estado({ competencia: X.comp });
    if (!r || r.error) { if (r && r.error) aviso(r.error, true); return; }
    X.emps = r.empresas || []; X.pasta = r.pasta || '';
    desenhar();
  }

  // baixa os tipos novos (entradas e saídas) de uma empresa (id) ou de todas (null)
  async function baixarNovos(ids) {
    const ms = meses();
    if (!ms.length) { aviso('Escolha o período (data inicial e final).', true); return; }
    X.mostrou = true; montarCard(); q('#dfeCard').hidden = false;
    X.todas = !ids; X.comp = ms[0];
    const ciencia = ehAdmin() ? q('#dlCiencia').checked : true;
    if (ent().length) {
      const r = await window.fiscocont.dfe.entradas({ ids, competencia: ms[0], tipos: ent(), ciencia });
      if (r && r.error) aviso(r.error, true);
      await atualizar();
    }
    if (sai().length) {
      await atualizar();
      const alvo = ids ? X.emps.filter((m) => ids.includes(m.id)) : X.emps;
      if (!alvo.some((m) => m.uf === 'RO')) aviso('Saídas: nenhuma empresa de Rondônia na seleção (o DFe-Download da SEFIN é só para RO).', true);
      else {
        for (const c of ms) {
          aviso(`Saídas de ${compRot(c)}: quando a SEFIN pedir, o código da imagem aparece aqui para você digitar.`);
          const r = await window.fiscocont.dfe.saidas({ ids, competencia: c, tipos: sai() });
          if (r && r.error) { aviso(r.error, true); break; }
        }
        await atualizar();
      }
    }
    if (ent().length || sai().length) await gerarRelatorios(ids, ms);
    q('#dfeProg').textContent = '';
  }

  // relatório (HTML) e PDF das NF-e/CT-e, a partir dos XMLs já salvos na pasta de cada empresa
  const querPdf = () => { const c = q('#dlGerarPdf'); return !!(c && c.checked && !c.closest('label').hidden); };
  async function gerarRelatorios(ids, ms) {
    const r = await window.fiscocont.dfe.relatorio({ ids, competencias: ms, pdf: querPdf() });
    if (r && r.error) { aviso(r.error, true); return; }
    const ok = (r.empresas || []).filter((x) => x.ok), pdfs = ok.reduce((s, x) => s + (x.pdfs || 0), 0), errosPdf = ok.reduce((s, x) => s + (x.pdf_erros || 0), 0);
    if (ok.length) aviso(`Relatório gerado para ${ok.length} empresa(s)${pdfs ? ` · ${pdfs} PDF(s) novos` : ''}${errosPdf ? ` · ${errosPdf} XML(s) sem PDF` : ''}. Use "Abrir relatório" no quadro.`);
    else if ((r.empresas || []).length && ids) aviso(r.empresas[0].erro || 'Nenhum XML para o relatório.', true);
    await atualizar();
  }

  function ligarBotoes() {
    const b = q('#btnDlBaixar'), lote = q('#btnNflBaixar');
    // "Baixar NFS-e"/"Baixar notas": empresa escolhida. NFS-e segue o fluxo de sempre; os tipos novos vêm depois.
    b.addEventListener('click', async (ev) => {
      if (X.repassa || !novos().length) {
        if (!tipos().length) { ev.stopImmediatePropagation(); aviso('Marque pelo menos um tipo de documento.', true); }
        return;
      }
      ev.stopImmediatePropagation();
      if (X.rodando || b.disabled) return;
      const id = q('#dlSelectEmpresa').value;
      if (!id) { aviso('Escolha uma empresa.', true); return; }
      X.rodando = true;
      try {
        if (tipos().includes('nfse')) {
          X.repassa = true; b.click(); X.repassa = false;
          await sleep(300);
          while (b.disabled) await sleep(500);              // espera a NFS-e terminar
        }
        b.disabled = true;
        await baixarNovos([id]);
      } finally { X.rodando = false; X.repassa = false; b.disabled = false; ajustaTela(); }
    }, true);
    // "Baixar em lote (todas as empresas)": tipos novos de todas as empresas; NFS-e abre a janela do lote de sempre.
    if (lote) lote.addEventListener('click', async (ev) => {
      if (X.repassa || !novos().length) return;
      ev.stopImmediatePropagation();
      if (X.rodando) return;
      X.rodando = true; lote.disabled = true;
      try { await baixarNovos(null); } finally { X.rodando = false; lote.disabled = false; }
      if (tipos().includes('nfse')) { X.repassa = true; lote.click(); X.repassa = false; }
    }, true);
  }


  // Código da imagem da SEFIN: a página do DFe-Download fica escondida; a imagem vem para cá, a pessoa digita e o sistema envia.
  function pedirCodigo(d) {
    const velho = q('#dfeCodBg'); if (velho) velho.remove();
    const partes = d.partes > 1 ? `<div class="dfe-cod-parte">${Array.from({ length: d.partes }, (_, i) => `<span class="${i + 1 === d.parte ? 'on' : ''}">Parte ${i + 1}${i + 1 < d.parte ? ' ✓' : ''}</span>`).join('')}</div>` : '';
    const bg = document.createElement('div');
    bg.className = 'dfe-cod-bg'; bg.id = 'dfeCodBg';
    bg.innerHTML = `<div class="dfe-cod" role="dialog" aria-label="Código da imagem">
      <div class="dfe-cod-h"><div><b>Digite o código da imagem</b><small>${e(d.empresa)} · ${e(d.doc)} Saídas · SEFIN-RO</small></div><button class="x" id="dfeCodX" title="Parar a busca das saídas">×</button></div>
      <div class="dfe-cod-b">
        <div class="dfe-cod-img"><img alt="Código de verificação" src="${e(d.img)}"></div>
        ${partes}
        ${d.msgSefin ? `<div class="dfe-cod-erro"><b>Mensagem da SEFIN:</b> ${e(d.msgSefin)}</div>` : ''}
        ${d.aviso ? `<div class="dfe-cod-av">${e(d.aviso)}</div>` : ''}
        <label for="dfeCodIn">Código</label>
        <input id="dfeCodIn" autocomplete="off" spellcheck="false" maxlength="12">
      </div>
      <div class="dfe-cod-f"><button class="lk" id="dfeCodPula">Pular esta parte</button><span class="sp"></span><button class="ok" id="dfeCodOk" disabled>Enviar</button></div>
    </div>`;
    document.body.appendChild(bg);
    const inp = q('#dfeCodIn'), ok = q('#dfeCodOk');
    let foi = false;
    const fecha = (texto) => { if (foi) return; foi = true; bg.remove(); return window.fiscocont.dfe.codigo(d.id, texto); };
    inp.addEventListener('input', () => { ok.disabled = !inp.value.trim(); });
    inp.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' && inp.value.trim()) fecha(inp.value.trim()); if (ev.key === 'Escape') fecha(null); });
    ok.addEventListener('click', () => fecha(inp.value.trim()));
    q('#dfeCodPula').addEventListener('click', () => fecha(null));
    q('#dfeCodX').addEventListener('click', () => { if (foi) return; foi = true; bg.remove(); window.fiscocont.dfe.cancelar(); });
    setTimeout(() => inp.focus(), 50);
  }

  function iniciar() {
    if (X.iniciado || !q('#dlTipos')) return;
    X.iniciado = true;
    const st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st);
    if (Date.now() > Date.parse(NOVO_ATE)) document.querySelectorAll('.dl-novo').forEach((x) => x.remove());
    q('#dlTipos').addEventListener('click', (ev) => { const t = ev.target.closest('.dl-tipo'); if (!t) return; t.classList.toggle('on'); ajustaTela(); });
    ['#dlDataInicial', '#dlDataFinal', '#dlSelectEmpresa'].forEach((s) => { const el = q(s); if (el) el.addEventListener('change', () => { X.todas = false; if (!q('#dfeCard').hidden) atualizar(); }); });
    ligarBotoes();
    if (window.fiscocont && window.fiscocont.dfe && window.fiscocont.dfe.onCodigo) window.fiscocont.dfe.onCodigo(pedirCodigo);
    ajustaTela();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
  window.dfeNotasIniciar = iniciar;
})();

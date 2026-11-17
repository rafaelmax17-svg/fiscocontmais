'use strict';
// Baixas DF-e · NF-e Entradas, NF-e Saídas, NFC-e Saídas e CT-e Entradas — nos mesmos botões da tela "Baixar NFS-e".
//   Entradas (todas as empresas): NF-e e CT-e pelo Ambiente Nacional, com o certificado cadastrado; Ciência da Operação
//   automática só nas notas que vierem como resumo (nota já manifestada vem completa e é só baixada).
//   Saídas (só empresas de RO): NF-e e NFC-e pelo DFe-Download da SEFIN, reaproveitando o pedido do mês já feito; a pessoa
//   digita o código da imagem na janela da SEFIN.
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
  .dfe-pasta{font-size:11.5px;color:var(--ink2);margin-top:10px}`;

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
    const pdf = q('#dlGerarPdf'); if (pdf) pdf.closest('label').hidden = !t.includes('nfse');
    const card = q('#dfeCard');
    if (card) { card.hidden = !novos().length && !X.mostrou; if (!card.hidden) { montarCard(); atualizar(); } }
  }

  function montarCard() {
    const box = q('#dfeCard');
    if (box.dataset.ok) return;
    box.dataset.ok = '1';
    box.innerHTML = `
      <div class="dfe-h"><b>NF-e, NFC-e e CT-e · situação</b><span id="dfeComp" style="font-size:12px;color:var(--ink2)"></span><span class="sp"></span>
        <button class="act inv-export" id="dfeAtualiza">Atualizar</button>
        <button class="act inv-export" id="dfeLog" title="Abre a pasta de dados: dfe_ro_log.txt (passo a passo no site da SEFIN) e dfe_ro_ultima.png">Passo a passo</button></div>
      <div class="dfe-prog" id="dfeProg"></div>
      <table class="dfe-t" id="dfeTab" hidden><thead><tr><th>Empresa</th><th>UF</th><th>NF-e Entradas</th><th>CT-e Entradas</th><th>NF-e Saídas</th><th>NFC-e Saídas</th></tr></thead><tbody id="dfeBody"></tbody></table>
      <div class="dfe-pasta" id="dfePasta"></div>`;
    q('#dfeAtualiza').addEventListener('click', atualizar);
    q('#dfeLog').addEventListener('click', () => window.fiscocont.dfe.log());
    q('#dfeBody').addEventListener('click', (ev) => { const b = ev.target.closest('[data-pasta]'); if (b) window.fiscocont.dfe.abrir(b.dataset.pasta).then((r) => r && r.error && aviso(r.error, true)); });
    window.fiscocont.dfe.onProgresso((d) => { const p = q('#dfeProg'); if (p) { p.textContent = d.txt || ''; p.classList.toggle('esp', !!d.espera); } });
  }

  const chip = (cls, t) => `<span class="dfe-st ${cls}">${e(t)}</span>`;
  const pastaBt = (p) => p ? `<button class="dfe-lk" data-pasta="${e(p)}">Abrir pasta</button>` : '';
  function celEntrada(x, tipo) {
    if (!x) return chip('dfe-nr', 'não buscado');
    if (x.erro) return chip('dfe-er', 'erro') + `<small>${e(x.erro)}</small>`;
    const det = [];
    if (x.mes && x.mes.qtd) det.push(`${x.mes.qtd} nota(s) do mês · R$ ${brl(x.mes.valor)}`);
    const extra = [x.resumos && `${x.resumos} só resumo`, x.ciencias && `${x.ciencias} ciência(s) feita(s)`, x.canceladas && `${x.canceladas} cancelada(s)`].filter(Boolean);
    if (extra.length) det.push(extra.join(' · '));
    if (x.resumos && x.ciencias) det.push('o XML que falta chega na próxima busca (depois de 1 hora)');
    else if (x.resumos && tipo === 'nfe') det.push('o XML completo sai depois da Ciência da Operação');
    if (/libera nova consulta|aguardar/.test(x.aviso || '')) det.push(x.aviso.replace(/ \(regra da SEFAZ[^)]*\)/, ''));
    const c = x.baixadas ? chip('dfe-ok', '✓ baixado') : x.resumos ? chip('dfe-ag', 'só resumo') : /libera nova consulta|aguardar/.test(x.aviso || '') ? chip('dfe-nr', 'aguardando 1 h') : chip('dfe-nr', 'nada novo');
    return c + (det.length ? `<small>${det.map(e).join('<br>')}</small>` : '') + pastaBt(x.pasta);
  }
  const SAI = { baixado: ['dfe-ok', '✓ baixado'], aguardando: ['dfe-ag', '◷ SEFIN preparando'], solicitado: ['dfe-pr', 'pedido feito'], sem_notas: ['dfe-nr', 'nenhuma nota no período'],
    aguardando_codigo: ['dfe-pr', 'falta digitar o código'], cancelado: ['dfe-nr', 'cancelado'], erro: ['dfe-er', 'erro'] };
  function celSaida(x, uf) {
    if (uf && uf !== 'RO') return chip('dfe-nr', 'fora de RO: só entradas');
    if (!x) return chip('dfe-nr', 'não buscado');
    const [c, t] = SAI[x.status] || ['dfe-nr', x.status || '—'];
    const det = [];
    if (x.status === 'baixado') det.push(`${x.qtd || 0} nota(s) · R$ ${brl(x.valor)}${x.canceladas ? ` · ${x.canceladas} cancelada(s)` : ''}`);
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
      return `<tr><td><b>${e(m.nome)}</b>${m.vencido ? '<small style="color:#b42323">certificado vencido</small>' : ''}</td>
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
          aviso(`Saídas de ${compRot(c)}: a janela da SEFIN abre para cada empresa de RO. Quando pedir, digite o código da imagem.`);
          const r = await window.fiscocont.dfe.saidas({ ids, competencia: c, tipos: sai() });
          if (r && r.error) { aviso(r.error, true); break; }
        }
        await atualizar();
      }
    }
    q('#dfeProg').textContent = '';
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

  function iniciar() {
    if (X.iniciado || !q('#dlTipos')) return;
    X.iniciado = true;
    const st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st);
    if (Date.now() > Date.parse(NOVO_ATE)) document.querySelectorAll('.dl-novo').forEach((x) => x.remove());
    q('#dlTipos').addEventListener('click', (ev) => { const t = ev.target.closest('.dl-tipo'); if (!t) return; t.classList.toggle('on'); ajustaTela(); });
    ['#dlDataInicial', '#dlDataFinal', '#dlSelectEmpresa'].forEach((s) => { const el = q(s); if (el) el.addEventListener('change', () => { X.todas = false; if (!q('#dfeCard').hidden) atualizar(); }); });
    ligarBotoes();
    ajustaTela();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
  window.dfeNotasIniciar = iniciar;
})();

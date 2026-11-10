'use strict';
// Consulta NF-e por chave · XML e PDF — SÓ ADMIN (em teste). Situação na SEFAZ, eventos, XML pelo Ambiente Nacional
// (quando a empresa escolhida participa da nota) e DANFE. "Ciência da operação" só vai à SEFAZ se a caixa estiver marcada.
(function () {
  const e = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmtCnpj = (c) => String(c || '').replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
  const fmtCh = (c) => String(c || '').replace(/(\d{4})(?=\d)/g, '$1 ');
  const dBr = (iso) => iso ? iso.slice(0, 10).split('-').reverse().join('/') : '';
  const dhBr = (iso) => { if (!iso) return ''; const d = new Date(iso); return isNaN(d) ? dBr(iso) : d.toLocaleString('pt-BR').slice(0, 17).replace(',', ''); };
  const brl = (v) => { const n = Number(v); return v === '' || v == null || isNaN(n) ? '' : n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }); };
  const SIT = { autorizada: ['Autorizada', 'ok'], cancelada: ['Cancelada', 'ca'], denegada: ['Denegada', 'de'], nao_encontrada: ['Não encontrada', 'nf'], erro: ['Erro na consulta', 'er'] };
  const EV = { cancelamento: 'Cancelamento', carta_correcao: 'Carta de correção', ciencia: 'Ciência da operação', confirmada: 'Confirmação da operação',
    desconhecida: 'Desconhecimento', nao_realizada: 'Operação não realizada' };
  const MOD = { 55: 'NF-e', 65: 'NFC-e' };
  const N = { empresas: [], pasta: '', empId: '', texto: '', baixar: true, ciencia: false, res: null, filtro: 'todas', sel: '', rodando: false };

  // ------------------------------------------------------------------ chaves (confere tamanho e dígito antes de ir à SEFAZ)
  function dvOk(ch) {
    let s = 0, p = 2;
    for (let i = 42; i >= 0; i--) { s += +ch[i] * p; p = p === 9 ? 2 : p + 1; }
    const dv = 11 - (s % 11);
    return +ch[43] === (dv >= 10 ? 0 : dv);
  }
  function lerChaves(txt) {
    const ok = [], ruins = [], vistos = new Set();
    String(txt || '').split(/\r?\n/).forEach((linha, i) => {
      const lim = linha.replace(/[\s.\-/]/g, '');
      const achou = lim.match(/(?<!\d)\d{44}(?!\d)/g);
      if (!achou) { const d = linha.replace(/\D/g, ''); if (d) ruins.push({ linha: i + 1, motivo: `${d.length} dígitos (a chave tem 44)` }); return; }
      achou.forEach((ch) => {
        if (vistos.has(ch)) return; vistos.add(ch);
        if (dvOk(ch)) ok.push(ch); else ruins.push({ linha: i + 1, motivo: 'dígito verificador não confere' });
      });
    });
    return { ok, ruins };
  }

  async function entrar() {
    const raiz = $('#ncRaiz');
    if (typeof ROLE === 'undefined' || ROLE !== 'admin') { raiz.innerHTML = '<div class="lic-empty">Acesso restrito ao Admin.</div>'; return; }
    const r = await window.fiscocont.nfech.empresas();
    if (r && r.error) { raiz.innerHTML = `<div class="lic-empty">${e(r.error)}</div>`; return; }
    N.empresas = r.empresas || []; N.pasta = r.pasta || '';
    if (!N.empId || !N.empresas.some((x) => x.id === N.empId)) N.empId = (N.empresas.find((x) => x.tipo !== 'procuracao' && !x.vencido) || {}).id || '';
    window.fiscocont.nfech.onProgresso((p) => {
      const el = $('#ncProg'); if (!el) return;
      el.hidden = false;
      el.querySelector('span').textContent = `Consultando ${p.feitas} de ${p.total}${p.guardadas ? ` · ${p.guardadas} já estavam guardadas` : ''}…`;
      el.querySelector('i').style.width = `${p.total ? (p.feitas / p.total * 100).toFixed(1) : 100}%`;
    });
    desenhar();
  }

  function contar(itens) {
    const c = { todas: itens.length, autorizada: 0, cancelada: 0, denegada: 0, nao_encontrada: 0, erro: 0, xml: 0 };
    itens.forEach((i) => { c[i.situacao] = (c[i.situacao] || 0) + 1; if (i.xml) c.xml++; });
    return c;
  }

  const contTxt = (ok, ruins) => `${ok.length ? `<b>${ok.length}</b> chave${ok.length > 1 ? 's' : ''} válida${ok.length > 1 ? 's' : ''}` : 'Nenhuma chave ainda'}${ruins.length ? ` · <em title="${e(ruins.slice(0, 15).map((r) => `linha ${r.linha}: ${r.motivo}`).join('\n'))}">${ruins.length} com problema (passe o mouse)</em>` : ''}`;
  const rotGo = (n) => `🔎 Consultar ${n || ''} chave${n === 1 ? '' : 's'}`;

  function desenhar() {
    const { ok, ruins } = lerChaves(N.texto);
    const emp = N.empresas.find((x) => x.id === N.empId);
    const itens = N.res ? N.res.itens : [];
    const c = contar(itens);
    const opts = N.empresas.map((x) => `<option value="${e(x.id)}"${x.id === N.empId ? ' selected' : ''}${x.tipo === 'procuracao' || x.vencido ? ' disabled' : ''}>${e(x.nome)} · ${fmtCnpj(x.cnpj)}${x.tipo === 'procuracao' ? ' (procuração: só NFS-e)' : x.vencido ? ' (certificado vencido)' : ''}</option>`).join('');
    const k = (n, t) => `<div><b>${n}</b><span>${t}</span></div>`;
    $('#ncRaiz').innerHTML = `
      <div class="nc-hero">
        <div><span class="nc-tag">SEFAZ · NF-e E NFC-e <em>SÓ ADMIN · EM TESTE</em></span><h1>Consulta NF-e por chave · XML e PDF</h1>
          <p>Cole uma ou várias chaves (44 dígitos). O sistema confere a chave, descobre a SEFAZ da nota e traz a situação oficial: autorizada, cancelada ou denegada, com o protocolo e os eventos. Quando a empresa escolhida participa da nota, baixa o XML completo e gera o PDF (DANFE).</p>
          <div class="nc-ks">${k(c.autorizada, 'Autorizadas')}${k(c.cancelada, 'Canceladas')}${k(c.denegada, 'Denegadas')}${k(c.nao_encontrada + c.erro, 'Não encontradas / erro')}</div></div>
        <div class="nc-in">
          <label>Chaves de acesso <small>(uma por linha · pode colar com espaços ou pontos)</small></label>
          <textarea id="ncTxt" spellcheck="false" placeholder="1126 1012 3456 7800 0190 5500 1000 0482 1310 0048 2135">${e(N.texto)}</textarea>
          <div class="nc-cont" id="ncCont">${contTxt(ok, ruins)}</div>
          <div class="nc-op">
            <div><label>Baixar XML e PDF como</label><select id="ncEmp">${opts || '<option value="">Cadastre o certificado nas Baixas DF-e</option>'}</select></div>
            <label class="nc-cb"><input type="checkbox" id="ncBaixar"${N.baixar ? ' checked' : ''}> Baixar XML e gerar PDF (DANFE)</label>
            <label class="nc-cb" title="Evento enviado à SEFAZ em nome da empresa escolhida. Não confirma nem recusa a operação, mas fica registrado na nota."><input type="checkbox" id="ncCien"${N.ciencia ? ' checked' : ''}${N.baixar ? '' : ' disabled'}> Registrar “Ciência da operação” quando a SEFAZ exigir</label>
          </div>
          <div class="nc-bt"><button class="p" id="ncGo"${!ok.length || !emp || N.rodando ? ' disabled' : ''}>${rotGo(ok.length)}</button>
            <button id="ncImp">Importar do SPED / Excel / XML</button>${itens.length ? '<button id="ncExp">Exportar Excel</button>' : ''}
            <small>${N.pasta ? `Salva em ${e(N.pasta)}\\&lt;mês&gt;\\&lt;empresa&gt;\\NF-e\\XML e PDF` : '<b>Escolha a pasta nas Baixas DF-e para salvar XML e PDF.</b>'}</small></div>
          <div class="nc-prog" id="ncProg" hidden><i></i><span></span></div>
        </div>
      </div>
      ${N.res ? resultado(itens, c) : '<div class="fc-card nc-vazio">Cole as chaves e clique em <b>Consultar</b>. A empresa escolhida é a do certificado usado para baixar o XML: ela precisa ser destinatária, transportadora ou autorizada na nota.</div>'}`;
    ligar();
  }

  function linhaXml(i) {
    if (i.xml) return `<span class="nc-fx ok" data-ab="${e(i.xml)}">XML</span>${i.pdf ? `<span class="nc-fx ok" data-ab="${e(i.pdf)}">PDF</span>` : ''}${i.situacao === 'cancelada' && i.pdf ? '<small>PDF com tarja de cancelada</small>' : ''}`;
    if (i.download) return `<span class="nc-fx no">só consulta</span><small title="${e(i.download)}">${e(i.download.length > 70 ? i.download.slice(0, 67) + '…' : i.download)}</small>`;
    return '<small>—</small>';
  }

  function resultado(itens, c) {
    const vis = itens.filter((i) => N.filtro === 'todas' || (N.filtro === 'nao_encontrada' ? ['nao_encontrada', 'erro'].includes(i.situacao) : N.filtro === 'xml' ? !!i.xml : i.situacao === N.filtro));
    const ch = (f, t, n) => `<button class="${N.filtro === f ? 'on' : ''}" data-fl="${f}">${t} ${n}</button>`;
    const sel = itens.find((i) => i.chave === N.sel) || vis[0];
    if (sel) N.sel = sel.chave;
    return `<div class="nc-row">
      <div class="fc-card"><div class="nc-h3"><h3>Resultado <small>${e(N.res.empresa.nome)} · ${N.res.consultadas} consultada${N.res.consultadas === 1 ? '' : 's'} agora${itens.length - N.res.consultadas ? ` · ${itens.length - N.res.consultadas} já guardada${itens.length - N.res.consultadas === 1 ? '' : 's'}` : ''}</small></h3>
        <div class="nc-ch">${ch('todas', 'Todas', c.todas)}${ch('autorizada', 'Autorizadas', c.autorizada)}${ch('cancelada', 'Canceladas', c.cancelada)}${ch('denegada', 'Denegadas', c.denegada)}${ch('nao_encontrada', 'Não encontradas', c.nao_encontrada + c.erro)}${ch('xml', 'Com XML', c.xml)}</div></div>
        <div class="nc-tw"><table class="nc-t"><thead><tr><th>Chave</th><th>Nota</th><th>Situação</th><th>Eventos</th><th>XML / PDF</th></tr></thead><tbody>
        ${vis.map((i) => { const s = SIT[i.situacao] || [i.situacao || '—', 'nf'];
          return `<tr data-ch="${i.chave}"${i.chave === N.sel ? ' class="sel"' : ''}><td class="nc-k">${fmtCh(i.chave.slice(0, 20))}<br>${fmtCh(i.chave.slice(20))}</td>
            <td><b>${e(i.emitente || '—')}</b><small>${MOD[i.modelo] || 'mod. ' + e(i.modelo)} ${Number(i.numero).toLocaleString('pt-BR')} · série ${e(i.serie)} · ${i.dh_emissao ? dBr(i.dh_emissao) : e(i.aamm)}${i.valor ? ' · ' + brl(i.valor) : ''}</small><small>${fmtCnpj(i.cnpj_emit)} · ${e(i.uf)}</small></td>
            <td><span class="nc-st ${s[1]}">${s[0]}</span><small>${i.situacao === 'cancelada' ? 'em ' + dhBr((i.eventos || []).find((x) => x.tipo === '110111')?.quando) : i.situacao === 'erro' || i.situacao === 'nao_encontrada' ? e(i.motivo || '') : ''}</small></td>
            <td>${(i.eventos || []).map((x) => `<span class="nc-ev">${e(EV[x.nome] || x.nome)}</span>`).join('') || '<small>sem eventos</small>'}</td>
            <td>${linhaXml(i)}</td></tr>`; }).join('') || '<tr><td colspan="5" class="nc-nada">Nada neste filtro.</td></tr>'}
        </tbody></table></div>
        <div class="nc-nota">Chave com dígito errado é apontada antes de consultar (não gasta consulta na SEFAZ). Nota já baixada, cancelada ou denegada não é consultada de novo.</div></div>
      ${sel ? detalhe(sel) : ''}</div>`;
  }

  function detalhe(i) {
    const s = SIT[i.situacao] || [i.situacao || '—', 'nf'];
    const tl = [];
    if (i.dh_autorizacao) tl.push(['#16a34a', 'Autorizada', dhBr(i.dh_autorizacao)]);
    (i.eventos || []).slice().sort((a, b) => (a.quando || '').localeCompare(b.quando || ''))
      .forEach((x) => tl.push([x.tipo === '110111' ? '#dc2626' : x.tipo === '110110' ? '#f59e0b' : '#6366f1', EV[x.nome] || x.nome, dhBr(x.quando)]));
    return `<div class="fc-card nc-dt"><div class="nc-h3"><h3>Detalhes da nota <small>${MOD[i.modelo] || ''} ${e(i.numero)}</small></h3></div>
      <dl><dt>Situação</dt><dd><span class="nc-st ${s[1]}">${s[0]}</span></dd>
        <dt>Emitente</dt><dd>${e(i.emitente || '—')}<small>CNPJ ${fmtCnpj(i.cnpj_emit)}</small></dd>
        <dt>SEFAZ</dt><dd>${e(i.uf)}${i.autorizador ? ` · ${e(i.autorizador)}` : ''}</dd>
        <dt>Modelo / série</dt><dd>${MOD[i.modelo] || ''} (${e(i.modelo)}) · série ${e(i.serie)}</dd>
        <dt>Emissão</dt><dd>${i.dh_emissao ? dhBr(i.dh_emissao) : e(i.aamm)}</dd>
        ${i.valor ? `<dt>Valor</dt><dd>${brl(i.valor)}</dd>` : ''}
        ${i.motivo && i.situacao !== 'autorizada' ? `<dt>SEFAZ disse</dt><dd>${e(i.cstat || '')} ${e(i.motivo)}</dd>` : ''}
        <dt>Consultada</dt><dd>${dhBr(i.consultadoEm)}</dd></dl>
      ${tl.length ? `<h4>Linha do tempo</h4><div class="nc-tl">${tl.map(([cor, t, q]) => `<div style="--c:${cor}"><b>${e(t)}</b><small>${e(q)}</small></div>`).join('')}</div>` : ''}
      ${i.xml ? `<div class="nc-bt">${i.pdf ? `<button class="p" data-ab="${e(i.pdf)}">Abrir PDF (DANFE)</button>` : ''}<button data-ab="${e(i.xml)}">Abrir XML</button><button data-pa="${e(i.xml)}">Abrir pasta</button></div>`
        : i.download ? `<div class="nc-aviso">${e(i.download)}</div>` : ''}
      ${i.ciencia && !i.ciencia.ok ? `<div class="nc-aviso er">Ciência recusada pela SEFAZ: ${e(i.ciencia.cstat)} · ${e(i.ciencia.motivo)}</div>` : ''}
      ${i.situacao === 'cancelada' ? '<div class="nc-aviso er">⚠ Nota cancelada: se foi escriturada no SPED, precisa ser retirada.</div>' : ''}
      <div class="nc-bt"><button data-cp="${i.chave}">Copiar chave</button></div></div>`;
  }

  function ligar() {
    const q = (s) => document.querySelectorAll('#ncRaiz ' + s);
    const txt = $('#ncTxt');
    let t = null;
    const conta = () => {
      const l = lerChaves(N.texto);
      $('#ncCont').innerHTML = contTxt(l.ok, l.ruins);
      const g = $('#ncGo'); g.textContent = rotGo(l.ok.length); g.disabled = !l.ok.length || !N.empId || N.rodando;
    };
    txt.oninput = () => { N.texto = txt.value; clearTimeout(t); t = setTimeout(conta, 250); };
    $('#ncEmp').onchange = (ev) => { N.empId = ev.target.value; conta(); };
    $('#ncBaixar').onchange = (ev) => { N.baixar = ev.target.checked; if (!N.baixar) N.ciencia = false; desenhar(); };
    $('#ncCien').onchange = (ev) => {
      if (ev.target.checked && !confirm('A "Ciência da operação" é um evento enviado à SEFAZ em nome da empresa escolhida e fica registrado na nota.\n\nEla não confirma nem recusa a operação. Só será enviada nas notas em que a SEFAZ mandar apenas o resumo.\n\nMarcar?')) { ev.target.checked = false; return; }
      N.ciencia = ev.target.checked;
    };
    $('#ncGo').onclick = () => consultar(lerChaves(N.texto).ok);
    $('#ncImp').onclick = importar;
    const ex = $('#ncExp'); if (ex) ex.onclick = exportar;
    q('[data-fl]').forEach((b) => b.onclick = () => { N.filtro = b.dataset.fl; desenhar(); });
    q('tr[data-ch]').forEach((tr) => tr.onclick = (ev) => { if (ev.target.closest('[data-ab]')) return; N.sel = tr.dataset.ch; desenhar(); });
    q('[data-ab]').forEach((b) => b.onclick = async (ev) => { ev.stopPropagation(); const r = await window.fiscocont.nfech.abrir(b.dataset.ab, false); if (r && r.error) toast(r.error, true); });
    q('[data-pa]').forEach((b) => b.onclick = async () => { const r = await window.fiscocont.nfech.abrir(b.dataset.pa, true); if (r && r.error) toast(r.error, true); });
    q('[data-cp]').forEach((b) => b.onclick = () => { navigator.clipboard.writeText(b.dataset.cp); toast('Chave copiada.'); });
  }

  async function consultar(ok) {
    if (!ok.length || N.rodando) return;
    N.rodando = true;
    const b = $('#ncGo'); b.disabled = true; b.textContent = 'Consultando…';
    const p = $('#ncProg'); p.hidden = false; p.querySelector('span').textContent = 'Iniciando…'; p.querySelector('i').style.width = '0%';
    const r = await window.fiscocont.nfech.consultar({ empresaId: N.empId, chaves: ok, baixar: N.baixar, ciencia: N.ciencia, pdf: N.baixar });
    N.rodando = false;
    if (r && r.error) { toast(r.error, true); desenhar(); return; }
    N.res = r; N.filtro = 'todas'; N.sel = '';
    const c = contar(r.itens);
    toast(`Consulta concluída: ${c.autorizada} autorizada(s), ${c.cancelada} cancelada(s)${c.xml ? ` · ${c.xml} XML salvo(s)` : ''}.`);
    desenhar();
  }

  async function importar() {
    const r = await window.fiscocont.nfech.importar();
    if (!r || r.cancelado) return;
    if (r.error) { toast(r.error, true); return; }
    if (!r.chaves.length) { toast('Nenhuma chave de acesso encontrada no arquivo.', true); return; }
    const atuais = lerChaves(N.texto).ok;
    N.texto = [...new Set([...atuais, ...r.chaves])].join('\n');
    const emp = r.cnpjArquivo && N.empresas.find((x) => x.cnpj === r.cnpjArquivo && x.tipo !== 'procuracao');
    if (emp) N.empId = emp.id;
    toast(`${r.chaves.length} chave(s) importada(s) de ${r.arquivo}${emp ? ` · empresa do arquivo: ${emp.nome}` : ''}.`);
    desenhar();
  }

  async function exportar() {
    const r = await window.fiscocont.nfech.exportar({ itens: N.res.itens, titulo: `Consulta NF-e por chave · ${N.res.empresa.nome} · ${dhBr(N.res.quando)}`,
      nome: `Consulta NF-e - ${N.res.empresa.nome}` });
    if (r && r.error) toast(r.error, true);
  }

  window._nfechEntrar = entrar;
})();

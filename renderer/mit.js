'use strict';
// MIT · PIS e COFINS (2.4.26) — importa a EFD-Contribuições, confere e pede o envio do MIT pela Receita (Liddera como
// procuradora); depois gera a guia só do MIT e transmite a DCTFWeb. Quem fala com a Receita é o computador do Admin.
(function () {
  const e = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (v) => (Number(v) || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtCnpj = (c) => String(c || '').replace(/\D/g, '').replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
  const compBr = (c) => (c ? `${c.slice(5, 7)}/${c.slice(0, 4)}` : '');
  const dataBr = (s) => { const d = s ? new Date(s) : null; return d && !isNaN(d) ? d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''; };
  const ymdBr = (s) => (/^\d{8}$/.test(s || '') ? `${s.slice(6)}/${s.slice(4, 6)}/${s.slice(0, 4)}` : s || '');
  const TRIB = { 1: 'Lucro Real Anual', 2: 'Lucro Real Trimestral', 3: 'Lucro Presumido', 4: 'Lucro Arbitrado', 5: 'Imune do IRPJ', 6: 'Isenta do IRPJ' };
  const REG = { 1: 'PIS/COFINS não cumulativo', 2: 'PIS/COFINS cumulativo', 3: 'PIS/COFINS não cumulativo e cumulativo' };
  const COD = {
    Irpj: [['236201', 'IRPJ · estimativa mensal (Lucro Real anual)'], ['022001', 'IRPJ · Lucro Real trimestral'], ['208901', 'IRPJ · Lucro Presumido']],
    Csll: [['248401', 'CSLL · estimativa mensal (Lucro Real anual)'], ['601201', 'CSLL · Lucro Real trimestral'], ['237201', 'CSLL · Lucro Presumido']],
  };
  const SIT = { a_enviar: ['pe', 'A enviar'], saldo_credor: ['cr', 'Sem débito · vai sem movimento'], em_curso: ['pe', 'Encerramento em curso'],
    enviado: ['ok', 'MIT enviado'], sem_movimento: ['en', 'Sem movimento enviado'], dispensado: ['en', 'MIT não precisa'] };
  const SELECIONAVEL = (d) => ['a_enviar', 'saldo_credor', 'dispensado'].includes(d.sit) && !fila(d.cnpj);
  const PED = { consultar: 'Consulta na Receita', enviar: 'Envio do MIT', guia: 'Guia do MIT', transmitir: 'Transmissão da DCTFWeb', recibo: 'Recibo da DCTFWeb' };
  const M = { comp: '', d: null, sel: new Set(), conf: new Set(), irAberto: '', semMov: '', trans: '', filtro: 'todas', animou: '' };
  let desliga = null, recarga = null;
  const raiz = () => document.getElementById('mtRaiz');
  const api = () => window.fiscocont.mit;
  const compAnterior = () => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; };

  async function carregar() {
    const r = await api().dados(M.comp);
    if (!r || r.error) { raiz().innerHTML = `<div class="lic-empty">${e((r && r.error) || 'Falha ao carregar.')}</div>`; return; }
    M.d = r;
    desenhar();
    // pedido na fila: confere de novo em 15 s (o robô avisa quando termina, mas pode estar em outro computador)
    clearTimeout(recarga);
    if ((r.pedidos || []).some((p) => ['novo', 'rodando'].includes(p.status))) recarga = setTimeout(carregar, 15000);
  }

  const totalLinha = (d) => (Number(d.total) || 0) + (d.extras || []).reduce((s, x) => s + (Number(x.valor) || 0), 0);
  const fila = (cnpj, tipo) => (M.d.pedidos || []).find((p) => ['novo', 'rodando'].includes(p.status) && (p.cnpjs || []).includes(cnpj) && (!tipo || p.tipo === tipo));

  function linhaDebitos(d) {
    const l = [...(d.extras || []).map((x) => `<div>${e(x.cod)} ${e(x.grupo === 'Csll' ? 'CSLL' : 'IRPJ')} · R$ ${num(x.valor)} <span class="sm">(digitado)</span>${['a_enviar', 'saldo_credor'].includes(d.sit) ? ` <button class="mt-x" data-rmx="${e(d.cnpj)}" data-cod="${e(x.cod)}" title="Tirar">×</button>` : ''}</div>`),
      ...(d.pis || []).map((x) => `<div>${e(x.cod)} PIS · R$ ${num(x.valor)}</div>`), ...(d.cofins || []).map((x) => `<div>${e(x.cod)} COFINS · R$ ${num(x.valor)}</div>`)];
    let h = l.length ? l.join('') : `<div>Sem débito de PIS/COFINS</div>`;
    if (d.saldoPis || d.saldoCofins) h += `<div class="sm">saldo credor: ${d.saldoPis ? `PIS R$ ${num(d.saldoPis)}` : ''}${d.saldoPis && d.saldoCofins ? ' · ' : ''}${d.saldoCofins ? `COFINS R$ ${num(d.saldoCofins)}` : ''}</div>`;
    if (['a_enviar', 'saldo_credor'].includes(d.sit)) {
      if (M.irAberto === d.cnpj) {
        h += `<div class="mt-ir"><select class="mt-mini" id="mtIrG"><option value="Irpj">IRPJ</option><option value="Csll">CSLL</option></select>
          <select class="mt-mini" id="mtIrC"></select><input class="mt-mini" id="mtIrO" placeholder="outro código" maxlength="7" style="width:92px" hidden>
          <input class="mt-mini" id="mtIrV" placeholder="valor" style="width:100px"><button class="act mt-b" id="mtIrOk">Incluir</button><button class="act mt-b" id="mtIrX">Cancelar</button></div>`;
      } else h += `<button class="mt-lk" data-ir="${e(d.cnpj)}">+ IRPJ / CSLL</button>`;
    }
    return h;
  }

  // 2.4.53: andamento de cada empresa em 4 etapas (MIT · guia · DCTFWeb · recibo)
  const hm = (s) => { const x = s ? new Date(s) : null; return x && !isNaN(x) ? x.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).replace(',', '') : ''; };
  function etapas(d) {
    const a = d.auto && d.auto.pendente ? d.auto.etapa : '', pf = fila(d.cnpj), dc = d.dctf || {};
    const mitFeito = ['enviado', 'sem_movimento', 'dispensado'].includes(d.sit), semGuia = ['sem_movimento', 'saldo_credor', 'dispensado'].includes(d.sit);
    const temGuia = (d.guias || []).length > 0, transm = dc.situacao === 'transmitida' && !!(dc.recibo || dc.arquivo);
    const mit = d.sit === 'dispensado' ? ['na', 'MIT não<br>precisa'] : mitFeito ? ['ok', d.sit === 'sem_movimento' ? 'MIT sem<br>movimento' : `MIT<br>${e(hm(d.mit && d.mit.enviadoEm))}`]
      : (pf && pf.tipo === 'enviar') || d.sit === 'em_curso' ? ['ru', 'MIT<br>enviando…'] : d.sit === 'saldo_credor' ? ['cr', 'Sem<br>débito'] : ['pe', 'MIT<br>pendente'];
    // 2.4.55: ordem MIT → DCTFWeb → recibo → guia (a guia só depois da DCTFWeb entregue)
    const espera = ['dctf', 'transmitir', 'recibo'].includes(a) || (d.auto && d.auto.etapa === 'confirmar' && !temGuia);
    const guia = temGuia ? ['ok', `Guia<br>${e(hm((d.guias || []).slice(-1)[0].em))}`] : semGuia ? ['na', 'Guia<br>não tem']
      : (pf && pf.tipo === 'guia') || a === 'guia' ? ['ru', 'Guia<br>gerando…'] : espera ? ['no', 'Guia<br>depois da DCTFWeb'] : mitFeito ? ['pe', 'Guia<br>falta gerar'] : ['no', 'Guia'];
    const dctf = transm ? ['ok', `DCTFWeb<br>transmitida${dc.retificadora ? ' <span class="mt-rt">retif.</span>' : ''}`]
      : (pf && pf.tipo === 'transmitir') || a === 'transmitir' ? ['ru', 'DCTFWeb<br>transmitindo…'] : a === 'dctf' ? ['ru', 'DCTFWeb<br>esperando a Receita']
      : dc.situacao === 'em_andamento' ? ['pe', 'DCTFWeb<br>falta transmitir'] : ['no', 'DCTFWeb'];
    const rec = dc.arquivo ? ['ok', 'Recibo<br>na pasta'] : (pf && pf.tipo === 'recibo') || a === 'recibo' ? ['ru', 'Recibo<br>baixando…']
      : dc.recibo && dc.reciboAviso ? ['pe', 'Recibo<br>não salvo'] : transm ? ['pe', 'Recibo<br>falta baixar'] : ['no', 'Recibo'];
    return [mit, dctf, rec, guia];
  }
  const ICO = { ok: '✓', ru: '↻', pe: '!', no: '', na: '–', cr: '≡' };
  function stepper(d) {
    const ets = etapas(d);
    return `<div class="mt-stp">${ets.map(([st, txt], i) => `${i ? `<span class="mt-ln ${st === 'ok' || st === 'ru' ? st : ''}"></span>` : ''}<div class="mt-et ${st}"><i>${ICO[st] || i + 1}</i><small>${txt}</small></div>`).join('')}</div>`;
  }
  function grupoDe(d) {
    const dc = d.dctf || {};
    if (d.sit === 'a_enviar' || d.sit === 'em_curso') return 'mit';
    if (dc.situacao === 'transmitida' && (dc.recibo || dc.arquivo)) return 'ok';
    if (d.sit === 'enviado' && !(d.guias || []).length) return 'guia';
    if (dc.situacao === 'em_andamento') return 'dctf';
    if (d.sit === 'saldo_credor') return 'cred';
    return 'outras';
  }

  function colSituacao(d) {
    let h = stepper(d);
    const pf = fila(d.cnpj);
    if (d.auto && d.auto.pendente) h += `<div class="mt-auto-l"><span class="mt-pulse"></span>Automático: ${e(d.auto.msg || 'em andamento')}</div>`;
    else if (d.auto && d.auto.etapa === 'confirmar') h += `<div class="mt-warn">${e(d.auto.msg || 'DCTFWeb original: confirme a folha e a REINF e transmita')}. </div>`;
    else if (d.auto && d.auto.etapa === 'erro') h += `<div class="mt-err">O automático parou: ${e(d.auto.msg || '')}. Continue pelos botões.</div>`;
    if (pf) h += `<div class="sm">${e(PED[pf.tipo] || pf.tipo)} ${pf.status === 'rodando' ? 'em andamento…' : 'na fila…'}</div>`;
    if (d.ultimoErro) h += `<div class="mt-err">${e(d.ultimoErro)}</div>`;
    const dcx = d.dctf || {};
    if (dcx.recibo && !dcx.arquivo && dcx.reciboAviso && !pf) h += `<div class="mt-warn">Recibo nº ${e(dcx.recibo)} existe na Receita, mas o PDF não foi salvo: ${e(dcx.reciboAviso)}.</div>`;
    if (d.mudouDepoisDoEnvio) h += `<div class="mt-warn">A EFD importada agora tem valores diferentes do MIT enviado: confira se é preciso retificar o MIT no portal.</div>`;
    if (d.sit === 'a_enviar' && !pf) h += `<label class="mt-ck"><input type="checkbox" data-conf="${e(d.cnpj)}" ${M.conf.has(d.cnpj) ? 'checked' : ''}> confere com a EFD</label>`;
    // 2.4.57: sem débito entra no mesmo lote do "Enviar MIT selecionados" (vai sem movimento; se a DCTFWeb já tiver
    // débitos da folha/REINF, o sistema registra "MIT não precisa" e não envia nada)
    if (['saldo_credor', 'dispensado'].includes(d.sit) && !pf) h += `<div class="sm">Sem débito de PIS/COFINS: marque e use "Enviar MIT selecionados" — vai como MIT sem movimento; se a DCTFWeb tiver débitos da folha/REINF, ela é transmitida depois com eles.</div>`;
    if (false && d.sit === 'dispensado' && d.mitDispensado) h += `<div class="sm">${e(d.mitDispensado.motivo || 'Sem débito e a DCTFWeb já tem débitos da folha/REINF: o MIT não precisa ser enviado.')}</div>`;
    if (['enviado', 'sem_movimento', 'em_curso'].includes(d.sit) && d.mit) {
      h += `<div class="sm">${d.mit.id ? `apuração nº ${e(d.mit.id)} · ` : ''}${e(dataBr(d.mit.enviadoEm) || ymdBr(d.mit.data))}${d.mit.enviadoPor ? ` · ${e(d.mit.enviadoPor)}` : ''}</div>`;
      (d.mit.avisos || []).slice(0, 2).forEach((a) => {
        // a Receita manda ir ao eCAC; aqui a transmissão é pelo botão abaixo
        if (/transmiss[aã]o imediata/i.test(a)) a = 'A Receita encerrou o MIT, mas não transmitiu a DCTFWeb sozinha. Use "Transmitir DCTFWeb" abaixo.';
        h += `<div class="sm">${e(a)}</div>`;
      });
    }
    if (['enviado', 'saldo_credor', 'sem_movimento', 'dispensado'].includes(d.sit) && d.dctf) {
      if (d.dctf.situacao === 'sem_declaracao') h += `<div class="sm">Sem DCTFWeb no mês</div>`;
      else if (d.dctf.retificadora && d.dctf.situacao === 'em_andamento') h += `<div class="sm"><span class="mt-retif" title="A original já tinha sido transmitida (normalmente pela folha). Os débitos dela continuam os mesmos; esta só acrescenta os do MIT.">retificadora</span></div>`;
    }
    if (d.sit === 'enviado' && !pf && !(d.auto && d.auto.pendente)) {
      h += `<div class="mt-acs"><button class="act mt-b" data-guia="${e(d.cnpj)}">Gerar guia do MIT</button>`;
      if (!d.dctf || d.dctf.situacao !== 'transmitida') h += `<button class="act mt-b" data-tr="${e(d.cnpj)}">Transmitir DCTFWeb</button>`;
      h += '</div>';
    }
    // sem movimento: se a Receita não transmitiu sozinha, a DCTFWeb fica em andamento — transmite por aqui
    if (['sem_movimento', 'dispensado'].includes(d.sit) && !pf && d.dctf && d.dctf.situacao === 'em_andamento') h += `<div class="mt-acs"><button class="act mt-b" data-tr="${e(d.cnpj)}">Transmitir DCTFWeb</button></div>`;
    const lk = [];
    const ug = (d.guias || []).slice(-1)[0];
    if (ug && ug.arquivo) lk.push(`<a href="#" class="mt-ab" data-arq="${e(ug.arquivo)}">guia PDF</a>`);
    if (d.dctf && d.dctf.arquivo) lk.push(`<a href="#" class="mt-ab" data-arq="${e(d.dctf.arquivo)}">recibo DCTFWeb</a>${d.dctf.recibo ? ` <span class="sm">nº ${e(d.dctf.recibo)}</span>` : ''}`);
    if (lk.length) h += `<div class="mt-lks">${lk.join('')}</div>`;
    if (ug && ug.aviso) h += `<div class="sm">${e(ug.aviso)}</div>`;
    if (!(d.dctf && d.dctf.arquivo) && ['enviado', 'saldo_credor', 'sem_movimento', 'dispensado'].includes(d.sit) && !pf && !(d.dctf && d.dctf.situacao === 'em_andamento')) h += `<div class="mt-acs"><button class="act mt-b" data-rec="${e(d.cnpj)}" title="Busca na Receita o recibo da DCTFWeb do mês (transmitida pelo sistema ou por fora) e salva na pasta do cliente">Baixar recibo da DCTFWeb</button></div>`;
    if (M.trans === d.cnpj) {
      h += `<div class="mt-trbox">${d.dctf && d.dctf.retificadora ? '<div class="mt-warn">Esta DCTFWeb é <b>retificadora</b>: a original já foi transmitida (normalmente pela folha). Os débitos que já estavam na original (folha e REINF) continuam os mesmos; a retificadora só acrescenta os do MIT. Dentro do prazo, retificar não gera multa.</div>' : ''}<b>Antes de transmitir, confirme:</b>
        <label class="mt-ck"><input type="checkbox" id="mtCf1"> a folha (eSocial) do mês está fechada e conferida</label>
        <label class="mt-ck"><input type="checkbox" id="mtCf2"> a EFD-Reinf do mês está fechada (ou não tem)</label>
        <label class="mt-ck"><input type="checkbox" id="mtCf3"> os débitos do MIT conferem com a EFD-Contribuições</label>
        <div class="mt-acs"><button class="act mt-b" id="mtTrOk">Transmitir agora</button><button class="act mt-b" id="mtTrX">Cancelar</button></div></div>`;
    }
    return h;
  }

  function desenhar() {
    const R = M.d;
    const docs = R.docs || [];
    const comDeb = docs.filter((d) => d.sit === 'a_enviar'), cred = docs.filter((d) => d.sit === 'saldo_credor');
    const totalDeclarar = comDeb.reduce((s, d) => s + totalLinha(d), 0);
    const semRecibo = docs.filter((d) => ['enviado', 'saldo_credor', 'sem_movimento', 'dispensado'].includes(d.sit) && !(d.dctf && d.dctf.arquivo) && !fila(d.cnpj));
    const comps = new Set([M.comp, compAnterior()]); for (let i = 1; i <= 6; i++) { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - i); comps.add(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`); }
    const rs = R.resp;
    const robo = R.robo || {};
    const sitDe = (c) => ((docs.find((d) => d && d.cnpj === c) || {}).sit);
    const podeEnviar = [...M.sel].filter((c) => (sitDe(c) === 'a_enviar' && M.conf.has(c)) || sitDe(c) === 'saldo_credor').length;
    const selDeb = [...M.sel].filter((c) => sitDe(c) === 'a_enviar');
    raiz().innerHTML = `
      <div class="fiscal-bar adm-bar">
        <button class="act inv-export adm-btn" id="mtEfd">EFD-Contribuições (.txt)</button>
        <select class="rtc-sel" id="mtComp">${[...comps].sort().reverse().map((c) => `<option value="${c}" ${c === M.comp ? 'selected' : ''}>Competência ${compBr(c)}</option>`).join('')}</select>
        <span class="fiscal-spacer"></span>
        <button class="act inv-export" id="mtRecs" ${semRecibo.length ? '' : 'disabled'} title="Recibo da DCTFWeb de todas as empresas da competência que ainda não têm o recibo na pasta">Baixar recibos da DCTFWeb${semRecibo.length ? ` (${semRecibo.length})` : ''}</button>
        <button class="act inv-export" id="mtCons" ${docs.length ? '' : 'disabled'}>Consultar situação na Receita</button>
        <button class="act adm-go" id="mtEnv" ${podeEnviar ? '' : 'disabled'} title="Envia as empresas marcadas: com débito (precisam do 'confere com a EFD') e sem débito (vão sem movimento)">Enviar MIT selecionados${podeEnviar ? ` (${podeEnviar})` : ''}</button>
      </div>
      <div class="mt-w">
        <h1 class="mt-h1">MIT · PIS e COFINS</h1>
        <div class="mt-s">Débitos lidos dos registros M205 (PIS) e M605 (COFINS) da EFD-Contribuições · envio pela Receita com a Liddera como procuradora${robo.ativo ? '' : ' · <b style="color:var(--neg)">envio ainda não configurado pelo Admin</b>'}</div>
        ${robo.ativo && !robo.online ? `<div class="mt-warn" style="margin:-4px 0 14px">⏸ <b>Os envios estão parados:</b> quem fala com a Receita é o computador do Admin que tem o certificado da Liddera${robo.nome ? ` (<b>${e(robo.nome.split(' · ')[0])}</b>)` : ''}, com o FiscoCont+ aberto e o Admin logado — e ele está sem sinal${robo.visto ? ` desde ${e(new Date(robo.visto).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }))}` : ''}. Os pedidos ficam guardados na fila e são enviados sozinhos assim que esse computador abrir o FiscoCont+ com o Admin.</div>` : ''}
        ${robo.ativo && window._ehAdminSessao && window._ehAdminSessao() ? `<label class="mt-autobar"><span class="mt-sw ${R.auto && R.auto.ligado ? 'on' : ''}"><input type="checkbox" id="mtAuto" ${R.auto && R.auto.ligado ? 'checked' : ''} ><i></i></span>
          <span><b>Envio automático ${R.auto && R.auto.ligado ? 'ligado' : 'desligado'}:</b> ao enviar o MIT com movimento, o robô transmite a DCTFWeb (retificadora, ou original de empresa marcada "sem folha e sem REINF"), baixa o recibo e só então gera a guia do MIT, salvando os dois na pasta da competência (${compBr(M.comp)}).${R.auto && R.auto.por ? ` <span class="sm">· ${R.auto.ligado ? 'ligado' : 'desligado'} por ${e(R.auto.por)}</span>` : ''}</span></label>` : ''}
        ${painel(docs, totalDeclarar)}
        ${docs.length ? chips(docs) : ''}
        ${selDeb.length ? `<label class="mt-ck mt-conflote"><input type="checkbox" id="mtConfTodos" ${selDeb.every((c) => M.conf.has(c)) ? 'checked' : ''}> <b>Confere com a EFD</b> — marcar nas ${selDeb.length} empresa(s) com débito selecionada(s)</label>` : ''}
        ${docs.length ? `<table class="mt-t"><thead><tr><th style="width:26px"><input type="checkbox" id="mtTodos" title="Marcar todas a enviar (com débito e sem débito)"></th><th>Empresa</th><th>Tributação</th><th>Débitos (código · valor)</th><th class="n">Total</th><th style="width:34%">Situação</th></tr></thead><tbody>
          ${docs.filter((d) => M.filtro === 'todas' || grupoDe(d) === M.filtro).map((d) => {
            const trava = !['a_enviar', 'saldo_credor'].includes(d.sit);
            return `<tr><td>${SELECIONAVEL(d) ? `<input type="checkbox" data-sel="${e(d.cnpj)}" ${M.sel.has(d.cnpj) ? 'checked' : ''}>` : ''}</td>
              <td><b>${e(d.nome)}</b><div class="sm">CNPJ ${e(fmtCnpj(d.cnpj))} · ${e(compBr(d.comp))}${d.retificadora ? ' · <b>EFD retificadora</b>' : ''}</div><div class="sm">${e(d.arquivo || '')}</div></td>
              <td><select class="mt-mini" data-trib="${e(d.cnpj)}" ${trava ? 'disabled' : ''}>${Object.entries(TRIB).map(([k, v]) => `<option value="${k}" ${+k === +d.tributacao ? 'selected' : ''}>${v}</option>`).join('')}</select><div class="sm">${e(REG[d.regime] || '')}</div>${+d.tributacao === 1 && !trava ? `<label class="mt-ck" title="Lucro Real Anual: como o IRPJ/CSLL do mês foi apurado (campo obrigatório do MIT)"><input type="checkbox" data-bal="${e(d.cnpj)}" ${d.balanco ? 'checked' : ''} ${trava ? 'disabled' : ''}> IRPJ/CSLL por balancete de suspensão/redução</label><div class="sm">${d.balanco ? '' : 'desmarcado = estimativa sobre a receita bruta'}</div>` : ''}${window._ehAdminSessao && window._ehAdminSessao() ? `<label class="mt-ck mt-sf" title="Só para empresa que NUNCA tem folha (eSocial) nem EFD-Reinf. Marcada, o envio automático transmite a DCTFWeb original sozinho. Só o Admin vê esta opção."><input type="checkbox" data-sf="${e(d.cnpj)}" ${d.semFolha ? 'checked' : ''}> Admin: sem folha e sem REINF</label>` : d.semFolha ? '<div class="sm mt-sfb" title="Marcada pelo Admin: a DCTFWeb original desta empresa é transmitida sozinha pelo envio automático">sem folha e sem REINF</div>' : ''}</td>
              <td>${linhaDebitos(d)}</td>
              <td class="n"><b>${num(totalLinha(d))}</b></td>
              <td>${colSituacao(d)}</td></tr>`;
          }).join('')}</tbody></table>`
          : `<div class="mt-vz">Nenhuma EFD-Contribuições importada em ${compBr(M.comp)}. Clique em <b>EFD-Contribuições (.txt)</b> e escolha os arquivos — pode ser de várias empresas de uma vez; a competência vem do próprio arquivo.</div>`}
        <div class="mt-resp"><b>Responsável pela apuração</b> (vai em todos os MIT): ${rs && rs.cpf ? `${e(rs.nome || '')} · CPF ${e(rs.cpf)}${rs.crc ? ` · CRC ${e(rs.crc)}` : ''}${rs.email ? ` · ${e(rs.email)}` : ''}${rs.tel ? ` · ${e(rs.tel)}` : ''} · enviado com a Liddera como procuradora` : '<b style="color:var(--neg)">não configurado</b> (Admin › Integra Contador)'}</div>
        ${(R.pedidos || []).length ? `<div class="mt-ped"><b>Últimos pedidos${window._ehAdminSessao && window._ehAdminSessao() ? ' <button class="mt-lk" id="mtLimpar" style="float:right">Limpar histórico</button>' : ''}</b>${robo.ativo && robo.nome ? `<div class="sm" style="margin:-2px 0 6px">Quem atende a fila: <b>${e(robo.nome.split(' · ')[0])}</b>${robo.visto ? ` · último sinal ${e(new Date(robo.visto).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }))}` : ''}${robo.online ? '' : ' · <b style="color:var(--neg)">sem sinal</b>'}</div>` : ''}${R.pedidos.slice(0, 6).map((p) => `<div><span class="mt-tg ${p.status === 'feito' ? 'ok' : p.status === 'erro' ? 'er' : p.status === 'aviso' ? 'nm' : 'pe'}">${e({ novo: 'Na fila', rodando: 'Em andamento', feito: 'Feito', erro: 'Erro', aviso: 'Aviso' }[p.status] || p.status)}</span> ${e(PED[p.tipo] || p.tipo)} · ${e(p.por)} · ${e(dataBr(p.emMs))}${p.msg ? ` — ${e(p.msg)}` : ''}</div>`).join('')}</div>` : ''}
        <div class="mt-lei"><b>Como funciona:</b> o valor de cada código é o "a recolher" da EFD (M205/M605), já depois dos créditos, das retenções e das deduções. Empresa sem débito vai no mesmo lote como MIT sem movimento; se a DCTFWeb do mês já tiver débitos da folha (eSocial) ou da EFD-Reinf, ela continua com esses débitos e é transmitida em seguida (retificadora, se a original já foi entregue), com o recibo na pasta da competência. O MIT vence no último dia útil do mês seguinte (o mesmo prazo da DCTFWeb); a EFD-Contribuições precisa estar gerada e validada antes, mesmo que ainda não transmitida. Depois do MIT, a guia só do MIT e a transmissão da DCTFWeb saem daqui (sozinhas, com o envio automático ligado) e guia e recibo vão para a pasta da competência — a assinatura da DCTFWeb é feita pelo próprio sistema com o certificado do escritório, sem o assinador do portal.</div>
      </div>`;
    ligar();
    animar();
  }

  // 2.4.53: painel do mês — anéis e números animados na primeira vez que a competência abre
  function anel(partes, total, rotulo) {
    let ac = 0;
    const arcos = partes.map(([v, cor]) => { const k = total ? (v / total) * 100 : 0; const h = `<circle cx="21" cy="21" r="15.915" fill="none" stroke="${cor}" stroke-width="5" stroke-linecap="round" stroke-dasharray="0 100" data-arco="${k}" stroke-dashoffset="${25 - ac}"/>`; ac += k; return h; }).join('');
    return `<svg class="mt-ring" viewBox="0 0 42 42"><circle cx="21" cy="21" r="15.915" fill="none" stroke="var(--line)" stroke-width="5"/>${arcos}<text x="21" y="23.6" text-anchor="middle">${rotulo}</text></svg>`;
  }
  function painel(docs, totalDeclarar) {
    const n = docs.length;
    const cm = docs.filter((d) => d.sit === 'enviado').length, sm = docs.filter((d) => ['sem_movimento', 'dispensado'].includes(d.sit)).length;
    const pe = docs.filter((d) => ['a_enviar', 'em_curso'].includes(d.sit)).length, cr = docs.filter((d) => d.sit === 'saldo_credor').length;
    const tr = docs.filter((d) => d.dctf && d.dctf.situacao === 'transmitida' && (d.dctf.recibo || d.dctf.arquivo));
    const rt = tr.filter((d) => d.dctf.retificadora).length;
    const and = docs.filter((d) => d.dctf && d.dctf.situacao === 'em_andamento').length;
    const sem = n - tr.length - and;
    const precisa = docs.filter((d) => d.sit === 'enviado'), comG = precisa.filter((d) => (d.guias || []).length).length;
    const decl = docs.filter((d) => ['enviado', 'em_curso'].includes(d.sit)).reduce((s, d) => s + totalLinha(d), 0);
    const pis = docs.filter((d) => d.sit === 'enviado').reduce((s, d) => s + (d.pis || []).reduce((t, x) => t + (Number(x.valor) || 0), 0), 0);
    const cof = docs.filter((d) => d.sit === 'enviado').reduce((s, d) => s + (d.cofins || []).reduce((t, x) => t + (Number(x.valor) || 0), 0), 0);
    const pct = totalDeclarar + decl ? Math.round((decl / (totalDeclarar + decl)) * 100) : 0;
    return `<div class="mt-dash">
      <div class="mt-dc"><span class="mt-gl" style="background:#6366f1"></span><small>MIT</small><div class="mt-rw">${anel([[cm, '#6366f1'], [sm, '#a78bfa']], n, `<tspan data-cnt="${cm + sm}">0</tspan>/${n}`)}
        <div class="mt-lg"><div><i style="background:#6366f1"></i>Com movimento enviado <b>${cm}</b></div><div><i style="background:#a78bfa"></i>Sem débito resolvido <b>${sm}</b></div><div><i style="background:#f59e0b"></i>Pendentes <b>${pe}</b></div>${cr ? `<div><i style="background:#38bdf8"></i>Sem débito a enviar <b>${cr}</b></div>` : ''}</div></div></div>
      <div class="mt-dc"><span class="mt-gl" style="background:#16a34a"></span><small>DCTFWeb</small><div class="mt-rw">${anel([[tr.length, '#16a34a'], [and, '#f59e0b']], n, `<tspan data-cnt="${tr.length}">0</tspan>/${n}`)}
        <div class="mt-lg"><div><i style="background:#16a34a"></i>Transmitidas <b>${tr.length}</b>${rt ? ` <span class="sm">(${rt} retif.)</span>` : ''}</div><div><i style="background:#f59e0b"></i>Falta transmitir <b>${and}</b></div><div><i style="background:#cbd5e1"></i>Ainda sem DCTFWeb <b>${Math.max(0, sem)}</b></div></div></div></div>
      <div class="mt-dc"><span class="mt-gl" style="background:#0ea5e9"></span><small>Guias do MIT</small><div class="mt-kv"><b data-cnt="${comG}">0</b> <span>de ${precisa.length}</span></div>
        <div class="sm">${precisa.length - comG ? `${precisa.length - comG} sem guia` : precisa.length ? 'todas as guias geradas' : 'nenhum MIT com débito enviado'}</div><div class="mt-br"><i data-w="${precisa.length ? (comG / precisa.length) * 100 : 0}" style="background:linear-gradient(90deg,#38bdf8,#0284c7)"></i></div></div>
      <div class="mt-dc"><span class="mt-gl" style="background:#f59e0b"></span><small>Declarado no MIT</small><div class="mt-kv"><b data-cnt="${decl}" data-brl="1">R$ 0,00</b></div>
        <div class="sm">PIS R$ ${num(pis)} · COFINS R$ ${num(cof)}${totalDeclarar ? ` · falta declarar R$ ${num(totalDeclarar)}` : ''}</div><div class="mt-br"><i data-w="${pct}"></i></div></div>
    </div>`;
  }
  function chips(docs) {
    const c = { todas: docs.length, mit: 0, guia: 0, dctf: 0, ok: 0, cred: 0 };
    docs.forEach((d) => { const g = grupoDe(d); if (c[g] !== undefined) c[g]++; });
    const L = [['todas', 'Todas'], ['mit', 'MIT pendente'], ['guia', 'Sem guia'], ['dctf', 'Falta transmitir DCTFWeb'], ['ok', 'Concluídas'], ['cred', 'Sem débito']];
    return `<div class="mt-chips">${L.filter(([k]) => k === 'todas' || c[k]).map(([k, t]) => `<button class="mt-chip ${M.filtro === k ? 'on' : ''}" data-fil="${k}">${t}<em>${c[k]}</em></button>`).join('')}</div>`;
  }
  function animar() {
    const r = raiz(), novo = M.animou !== M.comp;
    M.animou = M.comp;
    const dur = novo ? 1100 : 0, t0 = performance.now(), ez = (x) => 1 - Math.pow(1 - Math.min(1, x), 3);
    const cnt = [...r.querySelectorAll('[data-cnt]')];
    const passo = (now) => {
      const k = dur ? ez((now - t0) / dur) : 1;
      cnt.forEach((x) => { const v = Number(x.dataset.cnt) * k; x.textContent = x.dataset.brl ? `R$ ${num(v)}` : String(Math.round(v)); });
      if (k < 1) requestAnimationFrame(passo);
    };
    requestAnimationFrame(passo);
    const fim = () => {
      r.querySelectorAll('[data-arco]').forEach((x) => x.setAttribute('stroke-dasharray', `${x.dataset.arco} 100`));
      r.querySelectorAll('[data-w]').forEach((x) => { x.style.width = `${x.dataset.w}%`; });
    };
    if (novo) { r.querySelector('.mt-dash') && r.querySelector('.mt-dash').classList.add('anim'); requestAnimationFrame(() => requestAnimationFrame(fim)); }
    else { r.querySelector('.mt-dash') && r.querySelector('.mt-dash').classList.add('sem-trans'); fim(); }
  }

  async function pedir(o, ok) {
    const r = await api().pedir({ comp: M.comp, ...o });
    if (!r || r.error) { toast((r && r.error) || 'Falha no pedido.', true); return false; }
    toast(ok + (r.roboOnline ? '' : ' O computador de envio está offline: o pedido fica na fila.'));
    await carregar();
    return true;
  }
  async function salvar(cnpj, campos) {
    const r = await api().salvarEmpresa({ comp: M.comp, cnpj, ...campos });
    if (!r || r.error) { toast((r && r.error) || 'Falha ao salvar.', true); return false; }
    await carregar();
    return true;
  }

  function ligar() {
    const q = (s) => raiz().querySelectorAll(s);
    $('#mtEfd').onclick = async () => {
      const a = await api().escolherEfd();
      if (!a || !a.paths) return;
      overlay(true, 'Lendo a EFD-Contribuições…');
      const r = await api().importar(a.paths);
      overlay(false);
      if (!r || r.error) { toast((r && r.error) || 'Falha na leitura.', true); return; }
      if (r.comps && r.comps.length) M.comp = r.comps[r.comps.length - 1];
      toast(`${r.importadas} empresa(s) importada(s)${r.erros.length ? ` · ${r.erros.length} arquivo(s) com problema: ${r.erros.join(' · ')}` : ''}`, !!r.erros.length && !r.importadas);
      M.sel.clear(); M.conf.clear();
      carregar();
    };
    $('#mtComp').onchange = (ev) => { M.comp = ev.target.value; M.sel.clear(); M.conf.clear(); carregar(); };
    $('#mtCons').onclick = () => pedir({ tipo: 'consultar', cnpjs: (M.d.docs || []).map((d) => d.cnpj) }, 'Consulta pedida.');
    $('#mtRecs').onclick = () => {
      const lista = (M.d.docs || []).filter((d) => ['enviado', 'saldo_credor', 'sem_movimento', 'dispensado'].includes(d.sit) && !(d.dctf && d.dctf.arquivo) && !fila(d.cnpj)).map((d) => d.cnpj);
      if (lista.length) pedir({ tipo: 'recibo', cnpjs: lista }, `Recibos pedidos (${lista.length}): vão para a pasta de cada cliente.`);
    };
    q('[data-rec]').forEach((x) => { x.onclick = () => pedir({ tipo: 'recibo', cnpjs: [x.dataset.rec] }, 'Recibo pedido: vai para a pasta do cliente.'); });
    $('#mtEnv').onclick = async () => {
      const todosDocs = M.d.docs || [];
      const deb = todosDocs.filter((d) => M.sel.has(d.cnpj) && d.sit === 'a_enviar' && M.conf.has(d.cnpj));
      const sem = todosDocs.filter((d) => M.sel.has(d.cnpj) && d.sit === 'saldo_credor');
      const lista = [...deb, ...sem].map((d) => d.cnpj);
      const tot = deb.reduce((s, d) => s + totalLinha(d), 0);
      const txt = [deb.length ? `COM DÉBITO (${deb.length}) · total R$ ${num(tot)}\n${deb.map((d) => `• ${d.nome}: R$ ${num(totalLinha(d))}`).join('\n')}` : '',
        sem.length ? `SEM DÉBITO (${sem.length}) · vão como MIT sem movimento\n${sem.map((d) => `• ${d.nome}`).join('\n')}\n(se a DCTFWeb do mês já tiver débitos da folha ou da EFD-Reinf, ela continua com eles e é transmitida em seguida — retificadora, se a original já foi entregue — e o recibo vai para a pasta)` : ''].filter(Boolean).join('\n\n');
      if (!confirm(`Enviar o MIT de ${lista.length} empresa(s) para a Receita?\n\n${txt}\n\nO MIT é encerrado na Receita (os débitos entram na DCTFWeb do mês).`)) return;
      if (await pedir({ tipo: 'enviar', cnpjs: lista }, 'Envio pedido.')) { M.sel.clear(); M.conf.clear(); }
    };
    const todos = $('#mtTodos');
    if (todos) todos.onchange = () => { (M.d.docs || []).filter(SELECIONAVEL).forEach((d) => (todos.checked ? M.sel.add(d.cnpj) : M.sel.delete(d.cnpj))); desenhar(); };
    q('[data-sel]').forEach((x) => { x.onchange = () => { x.checked ? M.sel.add(x.dataset.sel) : M.sel.delete(x.dataset.sel); desenhar(); }; });
    q('[data-conf]').forEach((x) => { x.onchange = () => { if (x.checked) { M.conf.add(x.dataset.conf); M.sel.add(x.dataset.conf); } else M.conf.delete(x.dataset.conf); desenhar(); }; });
    q('[data-trib]').forEach((x) => { x.onchange = () => salvar(x.dataset.trib, { tributacao: +x.value }); });
    q('[data-bal]').forEach((x) => { x.onchange = () => salvar(x.dataset.bal, { balanco: x.checked }); });
    const ct = $('#mtConfTodos');
    if (ct) ct.onchange = () => { (M.d.docs || []).filter((d) => M.sel.has(d.cnpj) && d.sit === 'a_enviar').forEach((d) => (ct.checked ? M.conf.add(d.cnpj) : M.conf.delete(d.cnpj))); desenhar(); };
    q('[data-ir]').forEach((x) => { x.onclick = () => { M.irAberto = x.dataset.ir; desenhar(); }; });
    const g = $('#mtIrG');
    if (g) {
      const cods = () => { $('#mtIrC').innerHTML = COD[g.value].map(([c, r]) => `<option value="${c}">${c.slice(0, 4)}-${c.slice(4)} · ${e(r)}</option>`).join('') + '<option value="outro">outro código…</option>'; $('#mtIrO').hidden = true; };
      cods(); g.onchange = cods;
      $('#mtIrC').onchange = () => { $('#mtIrO').hidden = $('#mtIrC').value !== 'outro'; };
      $('#mtIrX').onclick = () => { M.irAberto = ''; desenhar(); };
      $('#mtIrOk').onclick = () => {
        const d = (M.d.docs || []).find((y) => y.cnpj === M.irAberto);
        const cod = ($('#mtIrC').value === 'outro' ? $('#mtIrO').value : $('#mtIrC').value).replace(/\D/g, '');
        const valor = Number(String($('#mtIrV').value).replace(/\./g, '').replace(',', '.'));
        if (cod.length !== 6) { toast('Código com 6 dígitos (ex.: 2362-01 → 236201).', true); return; }
        if (!(valor > 0)) { toast('Informe o valor.', true); return; }
        const rot = (COD[g.value].find((c) => c[0] === cod) || [])[1] || '';
        const extras = [...(d.extras || []), { grupo: g.value, cod, valor, rotulo: rot }];
        M.irAberto = '';
        salvar(d.cnpj, { extras });
      };
    }
    q('[data-rmx]').forEach((x) => { x.onclick = () => {
      const d = (M.d.docs || []).find((y) => y.cnpj === x.dataset.rmx);
      salvar(d.cnpj, { extras: (d.extras || []).filter((y) => y.cod !== x.dataset.cod) });
    }; });
    q('[data-guia]').forEach((x) => { x.onclick = () => pedir({ tipo: 'guia', cnpjs: [x.dataset.guia] }, `Guia pedida: o PDF vai para a pasta do cliente (competência ${compBr(M.comp)}).`); });
    q('[data-fil]').forEach((x) => { x.onclick = () => { M.filtro = x.dataset.fil; desenhar(); }; });
    q('[data-sf]').forEach((x) => { x.onchange = () => {
      const d = (M.d.docs || []).find((y) => y.cnpj === x.dataset.sf);
      if (x.checked && !confirm(`Marcar ${d.nome} como SEM FOLHA E SEM REINF?\n\nSó marque se a empresa nunca tem empregados (eSocial) nem EFD-Reinf.\n\nCom isso, o envio automático transmite a DCTFWeb ORIGINAL sozinho, só com o MIT. Se a empresa tiver folha, a DCTFWeb vai antes da folha fechar e depois vira retificadora.\n\nA marcação vale para os próximos meses também.`)) { x.checked = false; return; }
      salvar(d.cnpj, { semFolha: x.checked });
    }; });
    const au = $('#mtAuto');
    if (au) au.onchange = async () => {
      const r = await api().auto(au.checked);
      if (!r || r.error) { toast((r && r.error) || 'Falha.', true); au.checked = !au.checked; return; }
      toast(r.ligado ? 'Envio automático ligado: depois do MIT, o robô transmite a DCTFWeb, baixa o recibo e gera a guia.' : 'Envio automático desligado.');
      carregar();
    };
    q('[data-tr]').forEach((x) => { x.onclick = () => { M.trans = x.dataset.tr; desenhar(); }; });
    if ($('#mtTrX')) $('#mtTrX').onclick = () => { M.trans = ''; desenhar(); };
    if ($('#mtTrOk')) $('#mtTrOk').onclick = () => {
      if (!$('#mtCf1').checked || !$('#mtCf2').checked || !$('#mtCf3').checked) { toast('Marque as três confirmações.', true); return; }
      const cnpj = M.trans; M.trans = '';
      pedir({ tipo: 'transmitir', cnpjs: [cnpj], confirmado: { folha: true, reinf: true, mit: true } }, 'Transmissão pedida.');
    };
    if ($('#mtLimpar')) $('#mtLimpar').onclick = async () => {
      if (!confirm(`Apagar o histórico de pedidos de ${compBr(M.comp)} e os avisos de erro das empresas?\n\nO que já foi enviado à Receita não muda; os pedidos que ainda estão na fila continuam.`)) return;
      const r = await api().limparHistorico(M.comp);
      if (!r || r.error) { toast((r && r.error) || 'Falha.', true); return; }
      toast(`${r.apagados} registro(s) apagado(s).`); carregar();
    };
    q('.mt-ab').forEach((x) => { x.onclick = async (ev) => { ev.preventDefault(); const r = await api().abrir({ caminho: x.dataset.arq }); if (r && r.error) toast(r.error, true); }; });
  }

  async function entrar() {
    if (!M.comp) M.comp = compAnterior();
    if (!desliga && api().onMudou) desliga = api().onMudou((d) => { if (!d || d.comp === M.comp) carregar(); });
    raiz().innerHTML = '<div class="lic-empty">Carregando…</div>';
    carregar();
  }
  window._mitEntrar = entrar;
})();

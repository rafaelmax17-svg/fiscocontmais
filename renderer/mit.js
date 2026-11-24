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
  const SIT = { a_enviar: ['pe', 'A enviar'], saldo_credor: ['cr', 'Saldo credor · MIT não necessário'], em_curso: ['pe', 'Encerramento em curso'],
    enviado: ['ok', 'MIT enviado'], sem_movimento: ['en', 'Sem movimento enviado'] };
  const PED = { consultar: 'Consulta na Receita', enviar: 'Envio do MIT', guia: 'Guia do MIT', transmitir: 'Transmissão da DCTFWeb', recibo: 'Recibo da DCTFWeb' };
  const M = { comp: '', d: null, sel: new Set(), conf: new Set(), irAberto: '', semMov: '', trans: '' };
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

  function colSituacao(d) {
    const [cls, txt] = SIT[d.sit] || ['nm', d.sit];
    let h = `<span class="mt-tg ${cls}">${e(txt)}</span>`;
    const pf = fila(d.cnpj);
    if (pf) h += `<div class="sm">${e(PED[pf.tipo] || pf.tipo)} ${pf.status === 'rodando' ? 'em andamento…' : 'na fila…'}</div>`;
    if (d.ultimoErro) h += `<div class="mt-err">${e(d.ultimoErro)}</div>`;
    if (d.mudouDepoisDoEnvio) h += `<div class="mt-warn">A EFD importada agora tem valores diferentes do MIT enviado: confira se é preciso retificar o MIT no portal.</div>`;
    if (d.sit === 'a_enviar' && !pf) h += `<label class="mt-ck"><input type="checkbox" data-conf="${e(d.cnpj)}" ${M.conf.has(d.cnpj) ? 'checked' : ''}> confere com a EFD</label>`;
    if (d.sit === 'saldo_credor' && !pf) {
      h += `<label class="mt-ck"><input type="checkbox" data-sm="${e(d.cnpj)}" ${M.semMov === d.cnpj ? 'checked' : ''}> enviar MIT sem movimento mesmo assim</label>`;
      if (M.semMov === d.cnpj) h += `<div class="mt-warn">"Sem movimento" é para o mês sem fato gerador (IN RFB 2.237/2024, art. 6º, § 2º): com saldo credor a empresa teve movimento. Antes de enviar, o sistema confere se a DCTFWeb do mês tem débito de eSocial ou da EFD-Reinf — se tiver, não envia. Com o sem movimento, a DCTFWeb sem movimento é transmitida logo em seguida.</div>
        <button class="act mt-b" data-env-sm="${e(d.cnpj)}">Enviar MIT sem movimento</button>`;
    }
    if (['enviado', 'sem_movimento', 'em_curso'].includes(d.sit) && d.mit) {
      h += `<div class="sm">${d.mit.id ? `apuração nº ${e(d.mit.id)} · ` : ''}${e(dataBr(d.mit.enviadoEm) || ymdBr(d.mit.data))}${d.mit.enviadoPor ? ` · ${e(d.mit.enviadoPor)}` : ''}</div>`;
      (d.mit.avisos || []).slice(0, 2).forEach((a) => {
        // a Receita manda ir ao eCAC; aqui a transmissão é pelo botão abaixo
        if (/transmiss[aã]o imediata/i.test(a)) a = 'A Receita encerrou o MIT, mas não transmitiu a DCTFWeb sozinha. Use "Transmitir DCTFWeb" abaixo.';
        h += `<div class="sm">${e(a)}</div>`;
      });
    }
    if (['enviado', 'saldo_credor', 'sem_movimento'].includes(d.sit) && d.dctf) {
      const sd = { em_andamento: 'DCTFWeb em andamento — falta transmitir', transmitida: 'DCTFWeb transmitida ✓', sem_declaracao: 'Sem DCTFWeb no mês' }[d.dctf.situacao] || d.dctf.situacao;
      h += `<div class="sm">${e(sd)}${d.dctf.retificadora ? ' · <span class="mt-retif" title="A original já tinha sido transmitida (normalmente pela folha). Os débitos dela continuam os mesmos; esta só acrescenta os do MIT.">retificadora</span>' : ''}${d.dctf.recibo ? ` · recibo ${e(d.dctf.recibo)}` : ''}</div>`;
    }
    if (d.sit === 'enviado' && !pf) {
      h += `<div class="mt-acs"><button class="act mt-b" data-guia="${e(d.cnpj)}">Gerar guia do MIT</button>`;
      if (!d.dctf || d.dctf.situacao !== 'transmitida') h += `<button class="act mt-b" data-tr="${e(d.cnpj)}">Transmitir DCTFWeb</button>`;
      h += '</div>';
    }
    // sem movimento: se a Receita não transmitiu sozinha, a DCTFWeb fica em andamento — transmite por aqui
    if (d.sit === 'sem_movimento' && !pf && d.dctf && d.dctf.situacao === 'em_andamento') h += `<div class="mt-acs"><button class="act mt-b" data-tr="${e(d.cnpj)}">Transmitir DCTFWeb</button></div>`;
    // transmitida por fora (eCAC): confere de novo na Receita e baixa o recibo da que está valendo
    if (['enviado', 'saldo_credor', 'sem_movimento'].includes(d.sit) && !pf && d.dctf && d.dctf.situacao === 'em_andamento') h += `<div class="sm"><button type="button" class="mt-lk" data-rec="${e(d.cnpj)}">Transmitiu por fora? Buscar o recibo</button></div>`;
    (d.guias || []).slice(-2).forEach((g) => { h += `<div class="sm">Guia ${e(dataBr(g.em))}${g.arquivo ? ` · <a href="#" class="mt-ab" data-arq="${e(g.arquivo)}">abrir PDF</a>` : ''}${g.aviso ? ` · ${e(g.aviso)}` : ''}</div>`; });
    if (d.dctf && d.dctf.arquivo) h += `<div class="sm">📄 <a href="#" class="mt-ab" data-arq="${e(d.dctf.arquivo)}">abrir recibo da DCTFWeb</a>${d.dctf.recibo ? ` · nº ${e(d.dctf.recibo)}` : ''}</div>`;
    else if (['enviado', 'saldo_credor', 'sem_movimento'].includes(d.sit) && !pf && !(d.dctf && d.dctf.situacao === 'em_andamento')) h += `<div class="mt-acs"><button class="act mt-b" data-rec="${e(d.cnpj)}" title="Busca na Receita o recibo da DCTFWeb do mês (transmitida pelo sistema ou por fora) e salva na pasta do cliente">Baixar recibo da DCTFWeb</button></div>`;
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
    const semRecibo = docs.filter((d) => ['enviado', 'saldo_credor', 'sem_movimento'].includes(d.sit) && !(d.dctf && d.dctf.arquivo) && !fila(d.cnpj));
    const comps = new Set([M.comp, compAnterior()]); for (let i = 1; i <= 6; i++) { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - i); comps.add(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`); }
    const rs = R.resp;
    const robo = R.robo || {};
    const podeEnviar = [...M.sel].filter((c) => M.conf.has(c)).length;
    raiz().innerHTML = `
      <div class="fiscal-bar adm-bar">
        <button class="act inv-export adm-btn" id="mtEfd">EFD-Contribuições (.txt)</button>
        <select class="rtc-sel" id="mtComp">${[...comps].sort().reverse().map((c) => `<option value="${c}" ${c === M.comp ? 'selected' : ''}>Competência ${compBr(c)}</option>`).join('')}</select>
        <span class="fiscal-spacer"></span>
        <button class="act inv-export" id="mtRecs" ${semRecibo.length ? '' : 'disabled'} title="Recibo da DCTFWeb de todas as empresas da competência que ainda não têm o recibo na pasta">Baixar recibos da DCTFWeb${semRecibo.length ? ` (${semRecibo.length})` : ''}</button>
        <button class="act inv-export" id="mtCons" ${docs.length ? '' : 'disabled'}>Consultar situação na Receita</button>
        <button class="act adm-go" id="mtEnv" ${podeEnviar ? '' : 'disabled'} title="Envia as empresas marcadas com 'confere com a EFD'">Enviar MIT selecionados${podeEnviar ? ` (${podeEnviar})` : ''}</button>
      </div>
      <div class="mt-w">
        <h1 class="mt-h1">MIT · PIS e COFINS</h1>
        <div class="mt-s">Débitos lidos dos registros M205 (PIS) e M605 (COFINS) da EFD-Contribuições · envio pela Receita com a Liddera como procuradora${robo.ativo ? '' : ' · <b style="color:var(--neg)">envio ainda não configurado pelo Admin</b>'}</div>
        ${robo.ativo && !robo.online ? `<div class="mt-warn" style="margin:-4px 0 14px">⏸ <b>Os envios estão parados:</b> quem fala com a Receita é o computador do Admin que tem o certificado da Liddera${robo.nome ? ` (<b>${e(robo.nome.split(' · ')[0])}</b>)` : ''}, com o FiscoCont+ aberto e o Admin logado — e ele está sem sinal${robo.visto ? ` desde ${e(new Date(robo.visto).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }))}` : ''}. Os pedidos ficam guardados na fila e são enviados sozinhos assim que esse computador abrir o FiscoCont+ com o Admin.</div>` : ''}
        <div class="mt-k">
          <div class="mt-c"><small>Empresas</small><b>${docs.length}</b></div>
          <div class="mt-c"><small>Com débito</small><b>${comDeb.length}</b></div>
          <div class="mt-c"><small>Saldo credor</small><b>${cred.length}</b></div>
          <div class="mt-c"><small>Total a declarar</small><b>R$ ${num(totalDeclarar)}</b></div>
        </div>
        ${docs.length ? `<table class="mt-t"><thead><tr><th style="width:26px"><input type="checkbox" id="mtTodos" title="Marcar todas a enviar"></th><th>Empresa</th><th>Tributação</th><th>Débitos (código · valor)</th><th class="n">Total</th><th style="width:34%">Situação</th></tr></thead><tbody>
          ${docs.map((d) => {
            const trava = !['a_enviar', 'saldo_credor'].includes(d.sit);
            return `<tr><td>${d.sit === 'a_enviar' && !fila(d.cnpj) ? `<input type="checkbox" data-sel="${e(d.cnpj)}" ${M.sel.has(d.cnpj) ? 'checked' : ''}>` : ''}</td>
              <td><b>${e(d.nome)}</b><div class="sm">CNPJ ${e(fmtCnpj(d.cnpj))} · ${e(compBr(d.comp))}${d.retificadora ? ' · <b>EFD retificadora</b>' : ''}</div><div class="sm">${e(d.arquivo || '')}</div></td>
              <td><select class="mt-mini" data-trib="${e(d.cnpj)}" ${trava ? 'disabled' : ''}>${Object.entries(TRIB).map(([k, v]) => `<option value="${k}" ${+k === +d.tributacao ? 'selected' : ''}>${v}</option>`).join('')}</select><div class="sm">${e(REG[d.regime] || '')}</div>${+d.tributacao === 1 && !trava ? `<label class="mt-ck" title="Lucro Real Anual: como o IRPJ/CSLL do mês foi apurado (campo obrigatório do MIT)"><input type="checkbox" data-bal="${e(d.cnpj)}" ${d.balanco ? 'checked' : ''} ${trava ? 'disabled' : ''}> IRPJ/CSLL por balancete de suspensão/redução</label><div class="sm">${d.balanco ? '' : 'desmarcado = estimativa sobre a receita bruta'}</div>` : ''}</td>
              <td>${linhaDebitos(d)}</td>
              <td class="n"><b>${num(totalLinha(d))}</b></td>
              <td>${colSituacao(d)}</td></tr>`;
          }).join('')}</tbody></table>`
          : `<div class="mt-vz">Nenhuma EFD-Contribuições importada em ${compBr(M.comp)}. Clique em <b>EFD-Contribuições (.txt)</b> e escolha os arquivos — pode ser de várias empresas de uma vez; a competência vem do próprio arquivo.</div>`}
        <div class="mt-resp"><b>Responsável pela apuração</b> (vai em todos os MIT): ${rs && rs.cpf ? `${e(rs.nome || '')} · CPF ${e(rs.cpf)}${rs.crc ? ` · CRC ${e(rs.crc)}` : ''}${rs.email ? ` · ${e(rs.email)}` : ''}${rs.tel ? ` · ${e(rs.tel)}` : ''} · enviado com a Liddera como procuradora` : '<b style="color:var(--neg)">não configurado</b> (Admin › Integra Contador)'}</div>
        ${(R.pedidos || []).length ? `<div class="mt-ped"><b>Últimos pedidos${window._ehAdminSessao && window._ehAdminSessao() ? ' <button class="mt-lk" id="mtLimpar" style="float:right">Limpar histórico</button>' : ''}</b>${R.pedidos.slice(0, 6).map((p) => `<div><span class="mt-tg ${p.status === 'feito' ? 'ok' : p.status === 'erro' ? 'er' : 'pe'}">${e({ novo: 'Na fila', rodando: 'Em andamento', feito: 'Feito', erro: 'Erro' }[p.status] || p.status)}</span> ${e(PED[p.tipo] || p.tipo)} · ${e(p.por)} · ${e(dataBr(p.emMs))}${p.msg ? ` — ${e(p.msg)}` : ''}</div>`).join('')}</div>` : ''}
        <div class="mt-lei"><b>Como funciona:</b> o valor de cada código é o "a recolher" da EFD (M205/M605), já depois dos créditos, das retenções e das deduções. Com saldo credor não há débito a declarar e o MIT não é necessário. O MIT vence no último dia útil do mês seguinte (o mesmo prazo da DCTFWeb); a EFD-Contribuições precisa estar gerada e validada antes, mesmo que ainda não transmitida. Depois do MIT, a guia só do MIT e a transmissão da DCTFWeb saem daqui — a assinatura da DCTFWeb é feita pelo próprio sistema com o certificado do escritório, sem o assinador do portal.</div>
      </div>`;
    ligar();
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
      const lista = (M.d.docs || []).filter((d) => ['enviado', 'saldo_credor', 'sem_movimento'].includes(d.sit) && !(d.dctf && d.dctf.arquivo) && !fila(d.cnpj)).map((d) => d.cnpj);
      if (lista.length) pedir({ tipo: 'recibo', cnpjs: lista }, `Recibos pedidos (${lista.length}): vão para a pasta de cada cliente.`);
    };
    q('[data-rec]').forEach((x) => { x.onclick = () => pedir({ tipo: 'recibo', cnpjs: [x.dataset.rec] }, 'Recibo pedido: vai para a pasta do cliente.'); });
    $('#mtEnv').onclick = async () => {
      const lista = [...M.sel].filter((c) => M.conf.has(c));
      const docs = (M.d.docs || []).filter((d) => lista.includes(d.cnpj));
      const tot = docs.reduce((s, d) => s + totalLinha(d), 0);
      if (!confirm(`Enviar o MIT de ${docs.length} empresa(s) para a Receita?\n\nTotal declarado: R$ ${num(tot)}\n\n${docs.map((d) => `• ${d.nome}: R$ ${num(totalLinha(d))}`).join('\n')}\n\nO MIT é encerrado na Receita (os débitos entram na DCTFWeb do mês).`)) return;
      if (await pedir({ tipo: 'enviar', cnpjs: lista }, 'Envio pedido.')) { M.sel.clear(); M.conf.clear(); }
    };
    const todos = $('#mtTodos');
    if (todos) todos.onchange = () => { (M.d.docs || []).filter((d) => d.sit === 'a_enviar' && !fila(d.cnpj)).forEach((d) => (todos.checked ? M.sel.add(d.cnpj) : M.sel.delete(d.cnpj))); desenhar(); };
    q('[data-sel]').forEach((x) => { x.onchange = () => { x.checked ? M.sel.add(x.dataset.sel) : M.sel.delete(x.dataset.sel); desenhar(); }; });
    q('[data-conf]').forEach((x) => { x.onchange = () => { if (x.checked) { M.conf.add(x.dataset.conf); M.sel.add(x.dataset.conf); } else M.conf.delete(x.dataset.conf); desenhar(); }; });
    q('[data-trib]').forEach((x) => { x.onchange = () => salvar(x.dataset.trib, { tributacao: +x.value }); });
    q('[data-bal]').forEach((x) => { x.onchange = () => salvar(x.dataset.bal, { balanco: x.checked }); });
    q('[data-sm]').forEach((x) => { x.onchange = () => { M.semMov = x.checked ? x.dataset.sm : ''; desenhar(); }; });
    q('[data-env-sm]').forEach((x) => { x.onclick = () => {
      const d = (M.d.docs || []).find((y) => y.cnpj === x.dataset.envSm);
      if (!confirm(`Enviar o MIT SEM MOVIMENTO de ${d.nome} (${compBr(M.comp)})?\n\nA empresa teve saldo credor, não ausência de fato gerador. A decisão fica registrada com o seu nome.`)) return;
      pedir({ tipo: 'enviar', cnpjs: [d.cnpj], semMovimento: true }, 'Envio sem movimento pedido.').then(() => { M.semMov = ''; });
    }; });
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
    q('[data-guia]').forEach((x) => { x.onclick = () => pedir({ tipo: 'guia', cnpjs: [x.dataset.guia] }, 'Guia pedida: o PDF vai para a pasta do cliente (mês do pagamento).'); });
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

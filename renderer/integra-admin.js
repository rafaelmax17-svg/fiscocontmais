'use strict';
// Admin › Integra Contador · Serpro — cadastro da chave (uma vez, só neste computador, cifrada pelo Windows),
// certificado da Liddera, pastas onde o robô salva Declaração, Recibo, DAS e Extrato, e o andamento do robô.
(function () {
  const e = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const PRECO = { consulta: 0.24, emissao: 0.32 };          // 1ª faixa do contrato (por requisição)
  const fmtR = (v) => 'R$ ' + Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtCnpj = (c) => String(c || '').replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
  let EST = null;

  async function carregar() {
    const raiz = $('#igRaiz');
    raiz.innerHTML = '<div class="lic-empty">Carregando…</div>';
    const [r, certs] = await Promise.all([window.fiscocont.integra.estado(), window.fiscocont.fiscal.procProcuradores().catch(() => [])]);
    if (r && r.error) { raiz.innerHTML = `<div class="lic-empty">${e(r.error)}</div>`; return; }
    EST = r; desenhar(certs || []);
  }

  function desenhar(certs) {
    const L = EST.local, N = EST.nuvem || {};
    const liddera = certs.filter((c) => String(c.cnpj).slice(0, 8) === L.contratante.slice(0, 8));
    const certSel = L.certId || (liddera[0] && liddera[0].id) || '';
    const opts = certs.map((c) => `<option value="${e(c.id)}" ${c.id === certSel ? 'selected' : ''}>${e(c.razaoSocial)} · ${e(fmtCnpj(c.cnpj))}${c.validade ? ' · válido até ' + e(c.validade.split('-').reverse().join('/')) : ''}</option>`).join('');
    const custo = (N.consumo ? N.consumo.consulta * PRECO.consulta + N.consumo.emissao * PRECO.emissao : 0);
    const u = N.ultimo;
    const exemplo = L.pastaEmpresas ? `${L.pastaEmpresas}\\<pasta da empresa>${L.subpasta ? '\\' + L.subpasta.replace(/\{AAAA\}/g, '2026').replace(/\{MM\}/g, '10').replace(/\{MES\}/g, 'Outubro').replace(/\{AA\}/g, '26') : ''}`
      : (L.fallback ? `${L.fallback}\\10-2026\\<empresa>\\Simples Nacional` : '— escolha a pasta das empresas —');
    $('#igRaiz').innerHTML = `
      <div class="ig-hd"><div><h2>🔐 Integra Contador · Serpro</h2><p>Contrato 598158 · LIDDERA CONTABILIDADE LTDA · ${e(fmtCnpj(L.contratante))}</p></div>
        <span class="ig-pill ${N.ativo && N.online ? 'on' : 'off'}">${N.ativo ? (N.online ? 'Robô online' : 'Robô offline') : 'Não configurado'}</span></div>
      <div class="ig-g">
        <div class="ig-card">
          <h3>Chave de acesso do Serpro</h3>
          <p class="ig-hint">Gerada na Área do Cliente do Serpro (cliente.serpro.gov.br). Fica guardada <b>só neste computador</b>, cifrada pelo Windows — não vai para a nuvem nem para o código. Só é pedida de novo se a chave for trocada no Serpro.</p>
          <label>Consumer Key</label><input id="igKey" class="fs-in" type="password" autocomplete="off" spellcheck="false" placeholder="${L.configurado ? '••••••••••••••••' + e(L.finalKey) + '  (cadastrada — cole outra só para trocar)' : 'Cole aqui o Consumer Key'}">
          <label>Consumer Secret</label><input id="igSecret" class="fs-in" type="password" autocomplete="off" spellcheck="false" placeholder="${L.configurado ? '••••••••••••••••' + e(L.finalSecret) + '  (cadastrado)' : 'Cole aqui o Consumer Secret'}">
          <label>Certificado do procurador (e-CNPJ da Liddera)</label>
          <select id="igCert" class="fs-in">${opts || '<option value="">Cadastre o e-CNPJ da Liddera nas Baixas DF-e</option>'}</select>
          ${liddera.length ? '' : '<small class="neg">O e-CNPJ da Liddera não está cadastrado nas Baixas DF-e deste computador.</small>'}
          <div class="ig-act">
            <button class="act inv-export fs-prim" id="igSalvar">${L.configurado ? 'Testar e salvar' : 'Testar conexão e salvar'}</button>
            ${L.configurado ? '<button class="act inv-export" id="igTestar">Testar conexão</button><button class="act inv-export ig-del" id="igRemover">Remover</button>' : ''}
          </div>
          <div id="igMsg"></div>
        </div>
        <div class="ig-card">
          <h3>Situação</h3>
          ${L.configurado ? `<div class="ig-ok"><b>✓ Chave cadastrada neste computador</b>${L.testadoEm ? `Último teste: ${e(new Date(L.testadoEm).toLocaleString('pt-BR'))}` : ''}</div>` : '<div class="ig-off">Ainda sem chave. Enquanto ela não for cadastrada, o Fechamento do Simples continua igual para a equipe.</div>'}
          <div class="ig-inf">
            <div><b>Robô do Fechamento:</b> ${N.ativo ? (N.esteComputador ? 'este computador' : e(N.roboNome || 'outro computador')) : '—'}</div>
            <div><b>Conferência automática:</b> 1× por dia, a partir das 08:00, só das empresas já escrituradas e ainda não confirmadas</div>
            <div><b>Botão “Conferir na Receita”:</b> disponível para toda a equipe</div>
            <div><b>Consumo neste mês:</b> ${N.consumo ? `${N.consumo.consulta} consulta(s) · ${N.consumo.emissao} emissão(ões) de DAS · ≈ ${fmtR(custo)}` : '—'}</div>
            ${u ? `<div><b>Última conferência:</b> ${e(u.emBr || '')} · ${e(u.comp || '')} · ${e(u.por || '')}${u.erro ? ` · <span class="neg">${e(u.erro)}</span>` : ` · ${u.total || 0} empresa(s)`}</div>` : ''}
          </div>
          <small class="ig-hint">O robô usa a chave junto com o e-CNPJ da Liddera, como procurador. Cada cliente precisa ter dado procuração eletrônica no e-CAC para a Liddera (Simples Nacional); sem ela, a empresa aparece como “Sem procuração”.</small>
        </div>
      </div>
      <div class="ig-card" ${L.configurado ? '' : 'hidden'}>
        <h3>Onde salvar Declaração, Recibo, DAS e Extrato</h3>
        <p class="ig-hint">O robô procura a pasta de cada empresa pelos primeiros nomes da razão social. Se achar nenhuma ou mais de uma parecida, ele não escolhe: a empresa entra na lista abaixo para você apontar a pasta uma vez. Nenhum arquivo existente é sobrescrito.</p>
        <label>Pasta das empresas</label>
        <div class="fs-row"><input id="igBase" class="fs-in" value="${e(L.pastaEmpresas)}" placeholder="Ex.: G:\\Drives compartilhados\\Clientes"><button class="act inv-export" id="igBaseEsc">Escolher…</button></div>
        <label>Subpasta dentro da pasta da empresa</label>
        <input id="igSub" class="fs-in" value="${e(L.subpasta)}" placeholder="Ex.: Fiscal\\{AAAA}\\{MM}-{AAAA}">
        <small class="ig-hint">Use {AAAA} para o ano, {MM} para o mês com 2 dígitos, {MES} para o nome do mês e {AA} para o ano com 2 dígitos. As subpastas que faltarem são criadas.</small>
        <div class="ig-ex">Exemplo para Outubro/2026: <code>${e(exemplo)}</code></div>
        <div class="ig-act"><button class="act inv-export fs-prim" id="igPastas">Salvar pastas</button></div>
        ${L.pendPastas.length ? `<h3 class="ig-h3b">Empresas com pasta a verificar <small>${L.pendPastas.length}</small></h3>
        <div class="ig-pend">${L.pendPastas.map((p) => `<div class="ig-pr"><div><b>${e(p.nome)}</b><small>${e(p.aviso)}</small>
          ${(p.candidatos || []).length ? `<div class="ig-cands">${p.candidatos.map((c) => `<button class="ig-cand" data-id="${e(p.id)}" data-p="${e(c)}">${e(c.split(/[\\/]/).pop())}</button>`).join('')}</div>` : ''}</div>
          <button class="act inv-export" data-esc="${e(p.id)}" data-nome="${e(p.nome)}">Escolher pasta…</button></div>`).join('')}</div>
        <small class="ig-hint">Depois de apontar, clique em “Conferir na Receita” no Fechamento: os documentos dessas empresas são salvos.</small>` : ''}
      </div>`;
    ligar();
  }

  function msg(t, erro) { const m = $('#igMsg'); if (m) m.innerHTML = t ? `<div class="${erro ? 'ig-er' : 'ig-ok2'}">${e(t)}</div>` : ''; }

  function ligar() {
    $('#igSalvar').onclick = async () => {
      const bt = $('#igSalvar'); bt.disabled = true; bt.textContent = 'Testando no Serpro…'; msg('');
      const r = await window.fiscocont.integra.salvarChave({ key: $('#igKey').value, secret: $('#igSecret').value, certId: $('#igCert').value });
      bt.disabled = false;
      if (r && r.error) { bt.textContent = 'Testar e salvar'; msg(r.error, true); return; }
      toast('Chave do Serpro testada e salva neste computador.'); carregar();
    };
    if ($('#igTestar')) $('#igTestar').onclick = async () => {
      const bt = $('#igTestar'); bt.disabled = true; bt.textContent = 'Testando…';
      const r = await window.fiscocont.integra.testar();
      bt.disabled = false; bt.textContent = 'Testar conexão';
      if (r && r.error) { msg(r.error, true); return; }
      msg('✓ Conexão com o Serpro funcionando.');
    };
    if ($('#igRemover')) $('#igRemover').onclick = async () => {
      if (!confirm('Remover a chave do Serpro deste computador?\n\nO robô para e o botão "Conferir na Receita" some para a equipe. O que já foi conferido continua no Fechamento.')) return;
      const r = await window.fiscocont.integra.remover();
      if (r && r.error) { toast(r.error, true); return; }
      toast('Chave removida.'); carregar();
    };
    const esc = $('#igBaseEsc');
    if (esc) esc.onclick = async () => {
      const r = await window.fiscocont.integra.escolherPasta('Pasta onde ficam as pastas das empresas');
      if (r && r.pasta) $('#igBase').value = r.pasta;
    };
    const sp = $('#igPastas');
    if (sp) sp.onclick = async () => {
      const r = await window.fiscocont.integra.salvarPastas({ pastaEmpresas: $('#igBase').value, subpasta: $('#igSub').value });
      if (r && r.error) { toast(r.error, true); return; }
      toast('Pastas salvas.'); carregar();
    };
    document.querySelectorAll('#igRaiz [data-esc]').forEach((b) => { b.onclick = async () => {
      const r = await window.fiscocont.integra.escolherPasta(`Pasta da empresa ${b.dataset.nome}`);
      if (!r || !r.pasta) return;
      const x = await window.fiscocont.integra.definirPasta(b.dataset.esc, r.pasta);
      if (x && x.error) { toast(x.error, true); return; }
      toast('Pasta gravada para as próximas competências.'); carregar();
    }; });
    document.querySelectorAll('#igRaiz .ig-cand').forEach((b) => { b.onclick = async () => {
      if (!confirm(`Usar esta pasta?\n\n${b.dataset.p}`)) return;
      const x = await window.fiscocont.integra.definirPasta(b.dataset.id, b.dataset.p);
      if (x && x.error) { toast(x.error, true); return; }
      toast('Pasta gravada para as próximas competências.'); carregar();
    }; });
  }

  window._integraEntrar = carregar;
})();

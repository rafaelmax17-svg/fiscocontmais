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
    const SUB_PADRAO = 'Simples Nacional\\{AAAA}\\{PERIODO}';
    const baseVal = L.pastaEmpresas || L.sugestaoBase || '';
    const subVal = L.subpasta || SUB_PADRAO;
    const exemplo = baseVal ? `${baseVal}\\<pasta da empresa>\\${subVal.replace(/\{AAAA\}/g, '2026').replace(/\{PERIODO\}/g, '10 (ou 102026, 10-2026… a que já existir)').replace(/\{MM\}/g, '10').replace(/\{MES\}/g, 'Outubro').replace(/\{AA\}/g, '26')}`
      : '— escolha a pasta das empresas —';
    $('#igRaiz').innerHTML = `
      <div class="ig-hd"><div><h2>🔐 Integra Contador · Serpro</h2><p>Contrato 598158 · LIDDERA CONTABILIDADE LTDA · ${e(fmtCnpj(L.contratante))}</p></div>
        <span class="ig-pill ${N.ativo && N.online ? 'on' : 'off'}">${N.ativo ? (N.online ? 'Robô online' : 'Robô offline') : 'Não configurado'}</span></div>
      <div class="ig-g">
        <div class="ig-card">
          <h3>Chave de acesso do Serpro</h3>
          ${L.configurado && !L.temCert ? '<p class="ig-hint"><b>Este computador não tem o e-CNPJ da Liddera nas Baixas DF-e</b>, então ele não consulta o Serpro (não pode ser o robô). A chave continua valendo nos computadores que têm o certificado.</p>' : ''}
          <div id="igForm">
          <p class="ig-hint">Gerada na Área do Cliente do Serpro (cliente.serpro.gov.br). Fica gravada na nuvem, num cadastro que <b>só o Admin enxerga</b> — a equipe não vê nem recebe a chave, e ela não vai para o código nem para o instalador. Vale para todos os computadores em que o Admin entrar: só é pedida de novo se a chave for trocada no Serpro.</p>
          <label>Consumer Key</label><input id="igKey" class="fs-in" type="password" autocomplete="off" spellcheck="false" placeholder="${L.configurado ? '••••••••••••••••' + e(L.finalKey) + '  (cadastrada — cole outra só para trocar)' : 'Cole aqui o Consumer Key'}">
          <label>Consumer Secret</label><input id="igSecret" class="fs-in" type="password" autocomplete="off" spellcheck="false" placeholder="${L.configurado ? '••••••••••••••••' + e(L.finalSecret) + '  (cadastrado)' : 'Cole aqui o Consumer Secret'}">
          <label>Certificado do procurador (e-CNPJ da Liddera)</label>
          <select id="igCert" class="fs-in">${opts || '<option value="">Cadastre o e-CNPJ da Liddera nas Baixas DF-e</option>'}</select>
          ${liddera.length ? '' : '<small class="neg">O e-CNPJ da Liddera não está cadastrado nas Baixas DF-e deste computador.</small>'}
          <div class="ig-act">
            <button class="act inv-export fs-prim" id="igSalvar">${L.configurado ? 'Testar e salvar' : 'Testar conexão e salvar'}</button>
            ${L.configurado ? '<button class="act inv-export" id="igTestar">Testar conexão</button><button class="act inv-export ig-del" id="igRemover">Remover</button>' : ''}
          </div>
          </div>
          <div id="igMsg"></div>
        </div>
        <div class="ig-card">
          <h3>Situação</h3>
          ${L.configurado ? `<div class="ig-ok"><b>✓ Chave cadastrada · vale para todos os computadores do Admin</b>${L.testadoEm ? `Último teste: ${e(new Date(L.testadoEm).toLocaleString('pt-BR'))}` : ''}${L.configuradoPor ? ` · por ${e(L.configuradoPor)}` : ''}</div>` : '<div class="ig-off">Ainda sem chave. Enquanto ela não for cadastrada, o Fechamento do Simples continua igual para a equipe.</div>'}
          <div class="ig-inf">
            <div><b>Robô do Fechamento:</b> ${N.ativo ? (N.esteComputador ? 'este computador' : e(N.roboNome || 'outro computador')) : '—'} <span class="ig-hint" style="display:inline">(qualquer computador do Admin com o e-CNPJ da Liddera e o FiscoCont+ aberto; se o robô desligar, outro assume sozinho)</span></div>
            <div><b>Quando roda:</b> só quando você clica em <b>“▶ Iniciar robô”</b> no Fechamento do Simples (sem conferência automática)</div>
            <div><b>Quem vê:</b> só o Admin — a equipe não vê o botão, a coluna “Receita Federal” nem esta tela</div>
            <div><b>Quem é consultado:</b> só empresas com <b>Escrituração concluída = Sim</b> e ainda não confirmadas na Receita</div>
            <div><b>Consumo neste mês:</b> ${N.consumo ? `${N.consumo.consulta} consulta(s) · ${N.consumo.emissao} emissão(ões) de DAS · ≈ ${fmtR(custo)}` : '—'}</div>
            ${u ? `<div><b>Última conferência:</b> ${e(u.emBr || '')} · ${e(u.comp || '')} · ${e(u.por || '')}${u.erro ? ` · <span class="neg">${e(u.erro)}</span>` : ` · ${u.total || 0} empresa(s)`}</div>` : ''}
          </div>
          <small class="ig-hint">O robô usa a chave junto com o e-CNPJ da Liddera, como procurador. Cada cliente precisa ter dado procuração eletrônica no e-CAC para a Liddera (Simples Nacional); sem ela, a empresa aparece como “Sem procuração”.</small>
        </div>
      </div>
      <div class="ig-card" ${L.configurado ? '' : 'hidden'}>
        <h3>Onde salvar Declaração, Recibo, DAS e Extrato</h3>
        <p class="ig-hint">O robô procura a pasta de cada empresa pelos primeiros nomes da razão social e, dentro dela, a pasta do Simples Nacional, do ano e da competência — a da competência é reconhecida em qualquer formato usual (09, 092026, 09-2026, 09.2026, 2026-09, Setembro…). Se a pasta do ano ou da competência ainda não existir, ele cria no mesmo formato das que já existem. Se achar nenhuma ou mais de uma parecida, ele não escolhe: a empresa entra na lista abaixo para você apontar a pasta uma vez. Nenhum arquivo existente é sobrescrito.</p>
        <label>Pasta das empresas</label>
        <div class="fs-row"><input id="igBase" class="fs-in" value="${e(baseVal)}" placeholder="Ex.: G:\\Drives compartilhados\\Fiscal - Simples Nacional"><button class="act inv-export" id="igBaseEsc">Escolher…</button></div>
        <label>Subpasta dentro da pasta da empresa</label>
        <input id="igSub" class="fs-in" value="${e(subVal)}" placeholder="${e(SUB_PADRAO)}">
        <small class="ig-hint">{AAAA} = pasta do ano · {PERIODO} = pasta da competência (acha a que existir, em qualquer formato; se não houver, cria). O padrão “Simples Nacional\\{AAAA}\\{PERIODO}” serve para a estrutura atual das pastas.</small>${L.pastaEmpresas ? '' : '<small class="ig-hint"><b>Ainda não salvo</b> — confira e clique em “Salvar pastas”.</small>'}
        <div class="ig-ex">Exemplo para Outubro/2026: <code>${e(exemplo)}</code></div>
        <div class="ig-act"><button class="act inv-export fs-prim" id="igPastas">Salvar pastas</button></div>
        ${L.pendPastas.length ? `<h3 class="ig-h3b">Empresas com pasta a verificar <small>${L.pendPastas.length}</small></h3>
        <div class="ig-pend">${L.pendPastas.map((p) => `<div class="ig-pr"><div><b>${e(p.nome)}</b><small>${e(p.aviso)}</small>
          ${(p.candidatos || []).length ? `<div class="ig-cands">${p.candidatos.map((c) => `<button class="ig-cand" data-id="${e(p.chave || p.id)}" data-p="${e(c)}">${e(c.split(/[\\/]/).pop())}</button>`).join('')}</div>` : ''}</div>
          <button class="act inv-export" data-esc="${e(p.chave || p.id)}" data-nome="${e(p.nome)}">Escolher pasta…</button></div>`).join('')}</div>
        <small class="ig-hint">Depois de apontar, clique em “▶ Iniciar robô” no Fechamento: os documentos dessas empresas são salvos.</small>` : ''}
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
      if (!confirm('Remover a chave do Serpro?\n\nEla é apagada da nuvem (vale para todos os computadores) e o robô para. O que já foi conferido continua no Fechamento.')) return;
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

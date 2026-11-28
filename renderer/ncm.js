'use strict';
// Consulta de NCM (menu Fiscal, toda a equipe): descrição oficial (Siscomex/Classif), PIS/COFINS (tabelas oficiais da
// EFD-Contribuições) e IBS/CBS (LC 214/2025). A partir de 24/12/2026 avisa a extinção do PIS e da COFINS em 2027.
(function () {
  const e = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pc = (v) => `${Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
  const S = { q: '', res: null, lista: null, busy: false, tabelaEm: '' };

  function css() {
    if (document.getElementById('ncmCss')) return;
    const st = document.createElement('style');
    st.id = 'ncmCss';
    st.textContent = `
.ncm{padding:22px 26px;max-width:1180px}
.ncm-top{display:flex;gap:12px;align-items:center;margin-bottom:16px}.ncm-top h2{margin:0 14px 0 0;font-size:20px;color:#1f2a5a;white-space:nowrap}
.ncm-top input{flex:1;border:1px solid #d6dbe8;border-radius:12px;padding:11px 14px;font-size:14px;color:#1f2a5a;background:#fff;outline:none}
.ncm-top input:focus{border-color:#e8611c;box-shadow:0 0 0 3px #e8611c22}
.ncm-top button{border:0;cursor:pointer;background:linear-gradient(135deg,#e8611c,#ff9a56);color:#fff;border-radius:11px;padding:11px 18px;font-weight:700;font-size:13.5px}
.ncm-av{border-radius:14px;padding:12px 16px;margin-bottom:14px;font-size:13.5px;font-weight:600;display:flex;gap:10px;align-items:center}
.ncm-av.contagem{background:#fff4e5;color:#9a4a00;border:1px solid #f6c98f}.ncm-av.vigente{background:#e9edfb;color:#24307a;border:1px solid #c4cdf3}
.ncm-hd{background:linear-gradient(120deg,#1a2350,#2b3a72);color:#fff;border-radius:18px;padding:18px 22px;display:flex;justify-content:space-between;gap:16px;align-items:flex-start}
.ncm-hd .n{font-size:28px;font-weight:800;letter-spacing:.02em}.ncm-hd .d{font-size:14.5px;color:#eef1ff;margin-top:4px;max-width:820px}
.ncm-hd .tr{font-size:11.5px;color:#aab4dd;margin-top:8px;line-height:1.55}.ncm-hd .tr b{color:#fff;font-weight:600}
.ncm-src{font-size:11px;background:#ffffff1a;border:1px solid #ffffff30;border-radius:999px;padding:5px 11px;color:#dfe5ff;white-space:nowrap}
.ncm-g{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
.ncm-c{background:#fff;border-radius:16px;padding:16px 18px;box-shadow:0 8px 22px #1f2a5a0d;color:#1f2a5a}
.ncm-c h3{margin:0 0 2px;font-size:15px}.ncm-c .s{font-size:11.5px;color:#8a92b2;margin-bottom:12px}
.ncm-big{font-size:22px;font-weight:800;margin:4px 0}
.ncm-t{display:inline-block;font-size:11px;font-weight:700;border-radius:6px;padding:3px 8px;margin:0 6px 4px 0}
.ncm-t.ok{background:#e7f8f1;color:#0a8a5f}.ncm-t.nv{background:#e9edfb;color:#3d55c4}.ncm-t.wa{background:#fff4e5;color:#b45309}.ncm-t.gy{background:#f1f3f8;color:#6b7393}
.ncm-r{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-top:1px solid #f0f2f7;font-size:12.5px}.ncm-r span{color:#5b6488}.ncm-r b{text-align:right}
.ncm-lei{font-size:11px;color:#7a83a6;background:#f7f9fd;border-radius:8px;padding:7px 9px;margin-top:8px;line-height:1.45}
.ncm-it{border:1px solid #eef0f6;border-radius:12px;padding:10px 12px;margin-top:8px}
.ncm-it b{font-size:12.5px}.ncm-it p{margin:4px 0 0;font-size:12px;color:#5b6488;line-height:1.45}
.ncm-ls{background:#fff;border-radius:16px;box-shadow:0 8px 22px #1f2a5a0d;overflow:hidden}
.ncm-ls div{display:flex;gap:14px;padding:10px 16px;border-top:1px solid #f0f2f7;cursor:pointer;font-size:13px;color:#46507a}
.ncm-ls div:hover{background:#fff6ef}.ncm-ls div b{color:#1f2a5a;min-width:92px}
.ncm-vazio{color:#8a92b2;font-size:13px;padding:30px 0;text-align:center}
.ncm-foot{font-size:11px;color:#8a92b2;margin-top:12px}`;
    document.head.appendChild(st);
  }

  function hierarquia(h) {
    return (h || []).filter((x) => x.nivel === 'Capítulo' || x.nivel === 'Posição')
      .map((x) => `${e(x.nivel)} ${e(x.codigo)} · <b>${e(x.descricao)}</b>`).join('<br>');
  }

  function cardPis(r) {
    const p = r.pis_cofins || {};
    if (p.extinto) {
      return `<div class="ncm-c"><h3>PIS e COFINS</h3><div class="s">Extintos em 01/01/2027</div>
        <div class="ncm-big">—</div><span class="ncm-t gy">não existem mais</span>
        <div class="ncm-lei">Desde 01/01/2027 o PIS e a COFINS deixaram de existir: a operação passa a ter a CBS (quadro ao lado). LC 214/2025.</div></div>`;
    }
    let h = `<div class="ncm-c"><h3>PIS e COFINS</h3><div class="s">Tabelas oficiais da EFD-Contribuições · até 31/12/2026</div>`;
    if (p.basica) {
      h += `<div class="ncm-big">Tributação básica</div><span class="ncm-t nv">CST 01</span>
        <div class="ncm-r"><span>Lucro Presumido (cumulativo)</span><b>PIS 0,65% · COFINS 3%</b></div>
        <div class="ncm-r"><span>Lucro Real (não cumulativo)</span><b>PIS 1,65% · COFINS 7,6%</b></div>
        <div class="ncm-lei">O NCM não está nas tabelas de monofásico, ST, alíquota zero, isenção, sem incidência ou suspensão (4.3.10 a 4.3.16).
        Lei 9.718/1998 (cumulativo) · Leis 10.637/2002 e 10.833/2003 (não cumulativo).</div>`;
      if (p.aviso_sem_ncm) h += `<div class="ncm-lei" style="background:#fff8ef;color:#9a4a00">Algumas linhas da Tabela 4.3.13 (alíquota zero) descrevem o produto sem NCM — por exemplo, leite e queijos. Para alimentos, confira a descrição do produto na tabela.</div>`;
      return h + '</div>';
    }
    const a0 = p.achados[0];
    h += `<div class="ncm-big">${e(a0.regime)}</div>`;
    p.achados.forEach((a) => {
      h += `<div class="ncm-it"><span class="ncm-t ${a.tabela === '4.3.13' || a.tabela === '4.3.14' ? 'ok' : 'nv'}">${e(a.regime)}</span><span class="ncm-t nv">CST ${e(a.cst)}</span><span class="ncm-t gy">Tabela ${e(a.tabela)} · código ${e(a.codigo)}</span>
        ${a.condicao ? `<span class="ncm-t wa">${e(a.condicao.replace(/;\s*$/, ''))}</span>` : ''}
        <p>${e(a.descricao)}</p>
        ${a.natureza_revenda ? `<p><b>Revenda (quem não fabrica nem importa):</b> alíquota zero, CST 04, natureza da receita ${e(a.natureza_revenda)}.</p>` : ''}
        ${a.ncm_tabela ? `<p style="color:#8a92b2">NCM na tabela: ${e(a.ncm_tabela)}${a.desde ? ` · desde ${e(a.desde)}` : ''}</p>` : ''}</div>`;
    });
    return h + '</div>';
  }

  function cardIbs(r) {
    const b = r.ibs_cbs || {};
    const red = Number(b.reducao || 0);
    const at = b.ano_teste;
    return `<div class="ncm-c"><h3>IBS e CBS</h3><div class="s">Reforma Tributária · LC 214/2025</div>
      <div class="ncm-big">${red >= 100 ? 'Alíquota zero' : red ? `Redução de ${red.toLocaleString('pt-BR')}%` : 'Tributação integral'}</div>
      <span class="ncm-t ${red ? 'ok' : 'gy'}">${red ? 'com redução' : 'sem redução pelo NCM'}</span><span class="ncm-t nv">CST ${e(b.cst)}</span><span class="ncm-t nv">cClassTrib ${e(b.cclasstrib)}</span>
      ${b.condicao ? `<span class="ncm-t wa">${e(b.condicao)}</span>` : ''}
      <div class="ncm-r"><span>Enquadramento</span><b>${e(b.enquadramento)}</b></div>
      ${at ? `<div class="ncm-r"><span>2026 (ano de teste)</span><b>CBS ${pc(at.cbs)} · IBS ${pc(at.ibs)}</b></div>` : ''}
      ${b.art57 ? '<div class="ncm-r"><span>Uso e consumo pessoal</span><b>art. 57: crédito só se for revenda ou insumo da atividade</b></div>' : ''}
      <div class="ncm-lei">${e(b.lei)}${at ? ' · em 2026: CBS 0,9% e IBS 0,1% (valores de teste)' : ''}</div></div>`;
  }

  function desenha() {
    const raiz = $('#ncmRaiz');
    if (!raiz) return;
    css();
    let corpo = '';
    if (S.busy) corpo = '<div class="ncm-vazio">Consultando…</div>';
    else if (S.lista) {
      const L = S.lista;
      if (!L.tabela) corpo = '<div class="ncm-vazio">A tabela de NCM do Siscomex ainda não foi baixada (sem internet?). Consulte pelo código de 8 dígitos.</div>';
      else if (!L.itens.length) corpo = '<div class="ncm-vazio">Nenhum NCM com essas palavras na descrição.</div>';
      else corpo = `<div class="ncm-foot" style="margin:0 0 8px">${L.total} NCM encontrado(s)${L.total > L.itens.length ? ` · mostrando ${L.itens.length}` : ''} — clique para consultar</div>
        <div class="ncm-ls">${L.itens.map((x) => `<div data-ncm="${e(x.ncm)}"><b>${e(x.ncm)}</b><span>${e(x.descricao)}</span></div>`).join('')}</div>`;
    } else if (S.res) {
      const r = S.res;
      if (r.erro) corpo = `<div class="ncm-vazio">${e(r.erro)}</div>`;
      else {
        const aviso = r.aviso ? `<div class="ncm-av ${e(r.aviso.tipo)}">⚠ ${e(r.aviso.texto)}</div>` : '';
        const naoExiste = r.tabela && r.existe === false;
        corpo = `${aviso}<div class="ncm-hd"><div><div class="n">${e(r.ncm)}</div>
          <div class="d">${naoExiste ? '⚠ Este código não existe na tabela NCM vigente do Siscomex — confira o NCM.' : e(r.descricao || 'Descrição indisponível (tabela do Siscomex não baixada).')}</div>
          <div class="tr">${hierarquia(r.hierarquia)}</div></div>
          <div class="ncm-src">${r.tabela ? 'Descrição oficial · Siscomex/Classif' : 'Sem a tabela do Siscomex'}</div></div>
          <div class="ncm-g">${cardPis(r)}${cardIbs(r)}</div>
          <div class="ncm-foot">Tabela NCM do Siscomex${S.tabelaEm ? ` atualizada em ${new Date(S.tabelaEm).toLocaleDateString('pt-BR')}` : ''} · tabelas da EFD-Contribuições e reduções da LC 214/2025 carregadas no FiscoCont+.</div>`;
      }
    } else corpo = '<div class="ncm-vazio">Digite um NCM (ex.: 4818.10.00) ou palavras da descrição (ex.: papel higiênico).</div>';
    raiz.innerHTML = `<div class="ncm"><div class="ncm-top"><h2>Consulta de NCM</h2>
      <input id="ncmQ" placeholder="NCM (4818.10.00) ou descrição (papel higiênico)" value="${e(S.q)}" autocomplete="off">
      <button id="ncmGo">Consultar</button></div>${corpo}</div>`;
    const inp = $('#ncmQ');
    inp.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') ir(); });
    $('#ncmGo').addEventListener('click', ir);
    raiz.querySelectorAll('[data-ncm]').forEach((d) => d.addEventListener('click', () => { S.q = d.dataset.ncm; ir(); }));
    if (!S.busy) inp.focus();
  }

  async function ir() {
    const inp = $('#ncmQ');
    if (inp) S.q = inp.value.trim();
    if (!S.q || S.busy) return;
    const dig = S.q.replace(/\D/g, '');
    const porCodigo = dig.length >= 4 && /^[\d.\s-]+$/.test(S.q);
    S.busy = true; S.res = null; S.lista = null; desenha();
    try {
      if (porCodigo && dig.length !== 8) {
        const r = await window.fiscocont.ncm.buscar({ texto: S.q });
        S.lista = r.error ? { itens: [], tabela: true } : r.res;
        if (S.lista && S.lista.tabela) S.lista.itens = S.lista.itens.filter((x) => x.ncm.replace(/\D/g, '').startsWith(dig));
        if (r.error) toast(r.error, true);
      } else if (porCodigo) {
        const r = await window.fiscocont.ncm.consultar({ ncm: dig });
        if (r.error) { toast(r.error, true); S.res = { erro: r.error }; } else { S.res = r.res; S.tabelaEm = r.tabelaEm; }
      } else {
        const r = await window.fiscocont.ncm.buscar({ texto: S.q });
        if (r.error) toast(r.error, true);
        S.lista = r.error ? null : r.res;
      }
    } catch (err) { toast('Falha na consulta: ' + (err.message || err), true); }
    S.busy = false; desenha();
  }

  window._ncmEntrar = desenha;
})();

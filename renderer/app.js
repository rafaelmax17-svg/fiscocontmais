'use strict';

// ------------------------------------------------------------------ helpers
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const nf = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const brl = (v) => 'R$ ' + nf.format(v || 0);
function brlCompacto(v) {
  const a = Math.abs(v || 0), sinal = v < 0 ? '-' : '';
  if (a >= 1e9) return sinal + 'R$ ' + (a / 1e9).toFixed(1).replace('.', ',') + ' bi';
  if (a >= 1e6) return sinal + 'R$ ' + (a / 1e6).toFixed(1).replace('.', ',') + ' mi';
  if (a >= 1e3) return sinal + 'R$ ' + (a / 1e3).toFixed(1).replace('.', ',') + ' mil';
  return sinal + brl(a);
}
const pct = (v, d = 1) =>
  new Intl.NumberFormat('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d }).format(v || 0) + '%';
const esc = (s) => String(s == null ? '' : s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const PALETA = ['#4f46e5', '#0ea5e9', '#14b8a6', '#f59e0b', '#94a3b8', '#a855f7'];

let DATA = null;

// ------------------------------------------------------------------ donut
// segments: [{label, value, color}], opts: {size, stroke, centerTop, centerSub, centerColor}
function donutSVG(segments, opts = {}) {
  const size = opts.size || 190, stroke = opts.stroke || 30;
  const r = (size - stroke) / 2, cx = size / 2, cy = size / 2, C = 2 * Math.PI * r;
  const total = segments.reduce((a, s) => a + s.value, 0) || 1;
  let start = 0, arcs = '';
  segments.forEach((s, i) => {
    const dash = (s.value / total) * C;
    // posiciona por rotação (SVG), anima apenas o dashoffset
    arcs += `<circle class="arc" r="${r}" cx="${cx}" cy="${cy}" fill="none"
      stroke="${s.color}" stroke-width="${stroke}" stroke-linecap="butt"
      stroke-dasharray="${dash.toFixed(2)} ${(C - dash).toFixed(2)}"
      stroke-dashoffset="${dash.toFixed(2)}"
      data-off="${dash.toFixed(2)}"
      transform="rotate(${(start * 360).toFixed(3)} ${cx} ${cy})"
      style="transition-delay:${(i * 0.12).toFixed(2)}s"/>`;
    start += s.value / total;
  });
  const rot = `transform="rotate(-90 ${cx} ${cy})"`;
  let center = '';
  if (opts.centerTop) {
    center = `<text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="17" font-weight="800"
        fill="${opts.centerColor || '#141b2d'}" style="font-variant-numeric:tabular-nums">${esc(opts.centerTop)}</text>`;
    if (opts.centerSub)
      center += `<text x="${cx}" y="${cy + 16}" text-anchor="middle" font-size="10.5"
        fill="#5a6785" letter-spacing="0.04em">${esc(opts.centerSub)}</text>`;
  }
  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">
    <g ${rot}>${arcs}</g>${center}</svg>`;
}

// dispara a animação (offset -> 0) após inserir no DOM
function animateArcs(root) {
  requestAnimationFrame(() => {
    $$('.arc', root).forEach((c) => (c.style.strokeDashoffset = '0'));
  });
}
function animateBars(root) {
  requestAnimationFrame(() => {
    $$('.bfill,.cmp-fill', root).forEach((b) => (b.style.width = b.dataset.w || '0%'));
  });
}

// ------------------------------------------------------------------ views
function agruparInvertidas(d) {
  const map = {
    ATIVO: { rot: 'Ativo', cls: 'ativo', keys: ['ATIVO'] },
    PASSIVO: { rot: 'Passivo', cls: 'passivo', keys: ['PASSIVO'] },
    PL: { rot: 'Patrimônio Líquido', cls: 'pl', keys: ['PL'] },
    RESULT: { rot: 'Contas de Resultado', cls: 'result', keys: ['RESULTADO_DESP', 'RESULTADO_REC'] },
  };
  return Object.values(map).map((g) => {
    const itens = d.invertidas.filter((c) => g.keys.includes(c.grupo)).sort((a, b) => b.saldo_atual - a.saldo_atual);
    return { ...g, itens, soma: itens.reduce((a, c) => a + c.saldo_atual, 0) };
  });
}

function renderOverview(d) {
  const dre = d.dre, r = d.resultado, prej = r.lado === 'D';
  const rl = dre.receita_liquida, desp = dre.despesa_total;

  // rosca receita x despesa (arcos proporcionais, resultado no centro)
  const heroSegs = [
    { label: 'Receita líquida', value: rl, color: '#0ea472' },
    { label: 'Custos + despesas', value: desp, color: '#dc3856' },
  ];
  const hero = donutSVG(heroSegs, {
    size: 220, stroke: 34,
    centerTop: (prej ? '−' : '') + brl(Math.abs(dre.resultado)).replace('R$ ', ''),
    centerSub: (r.tipo || 'RESULTADO'),
    centerColor: prej ? '#dc3856' : '#0ea472',
  });
  const heroLegend = heroSegs.map((s) =>
    `<div class="dl-item"><span class="dl-sw" style="background:${s.color}"></span>
      <span class="dl-name">${s.label}</span><span class="dl-val">${brl(s.value)}</span></div>`).join('');

  // composição da receita (donut)
  const cr = dre.composicao_receitas.map((x, i) => ({ label: x[0], value: x[1], color: PALETA[i % PALETA.length] }));
  const totRec = cr.reduce((a, s) => a + s.value, 0) || 1;
  const recDonut = donutSVG(cr, { size: 150, stroke: 26 });
  const recLeg = cr.map((s) =>
    `<tr><td style="width:16px"><span class="sw" style="background:${s.color}"></span></td>
      <td>${esc(s.label)}</td><td class="lv">${brl(s.value)}</td><td class="lp">${pct(s.value / totRec * 100)}</td></tr>`).join('');

  // composição das despesas (barras)
  const cd = dre.composicao_despesas;
  const totDesp = cd.reduce((a, x) => a + x[1], 0) || 1;
  const bars = cd.map((x, i) => {
    const p = x[1] / totDesp * 100, cor = i === 0 ? '#dc3856' : PALETA[i % PALETA.length];
    return `<div class="brow"><div class="brow-top"><span>${esc(x[0])}</span>
      <span class="bmeta">${brl(x[1])} · ${pct(p)}</span></div>
      <div class="btrack"><div class="bfill" data-w="${p.toFixed(1)}%" style="background:${cor}"></div></div></div>`;
  }).join('');

  const el = $('#view-overview');
  el.innerHTML = `
    <h2 class="vtitle">Visão geral — Receitas × Custos e Despesas</h2>
    <div class="kpis">
      <div class="kpi"><div class="kl">Receita líquida</div><div class="kv pos">${brl(rl)}</div><div class="ks">no período</div></div>
      <div class="kpi"><div class="kl">Custos + despesas</div><div class="kv neg">${brl(desp)}</div><div class="ks">CMV = ${pct(dre.peso_cmv)} da receita</div></div>
      <div class="kpi"><div class="kl">Resultado</div><div class="kv ${prej ? 'neg' : 'pos'}">${brl(Math.abs(dre.resultado))}</div><div class="ks">${esc(r.tipo || '—')}</div></div>
      <div class="kpi"><div class="kl">Margem líquida</div><div class="kv ${dre.margem_liquida < 0 ? 'neg' : 'pos'}">${pct(dre.margem_liquida, 2)}</div><div class="ks">margem bruta ${pct(dre.margem_bruta, 2)}</div></div>
    </div>
    <div class="panes">
      <div class="pane wide">
        <div class="ptitle">Receitas × Custos e Despesas</div>
        <div class="donut-hero">
          <div class="donut-fig">${hero}</div>
          <div class="donut-legend">${heroLegend}
            <div class="dl-item" style="border-top:1px dashed var(--line);padding-top:10px;margin-top:2px">
              <span class="dl-name">${prej ? 'Prejuízo' : 'Lucro'} do período</span>
              <span class="dl-val ${prej ? 'val neg' : 'val pos'}">${brl(Math.abs(dre.resultado))}</span></div>
          </div>
        </div>
      </div>
      <div class="pane">
        <div class="ptitle">Composição da receita</div>
        <div style="text-align:center;margin-bottom:10px">${recDonut}</div>
        <table class="legt">${recLeg}</table>
      </div>
      <div class="pane">
        <div class="ptitle">Composição de custos e despesas</div>
        ${bars}
      </div>
    </div>`;
  animateArcs(el); animateBars(el);
}

const MACRO_LABELS_JS = {
  receita_bruta: 'Receita Operacional Bruta', deducoes: '(−) Deduções da Receita Bruta',
  receitas_financeiras: 'Receitas Financeiras', outras_receitas: 'Outras Receitas',
  cmv: '(−) Custo das Mercadorias Vendidas', despesas_pessoal: 'Despesas com Pessoal',
  impostos_taxas: 'Impostos, Taxas e Contribuições', despesas_financeiras: '(−) Despesas Financeiras',
  despesas_administrativas: '(−) Despesas Administrativas', tributos_lucro: '(−) Tributos sobre o Lucro',
};
const SINAL_MACRO_JS = {
  receita_bruta: 1, deducoes: -1, receitas_financeiras: 1, outras_receitas: 1,
  cmv: -1, despesas_pessoal: -1, impostos_taxas: -1, despesas_administrativas: -1,
  despesas_financeiras: -1, tributos_lucro: -1,
};

function _donutSvgNativo(itens, cx, cy, r, sw) {
  const total = itens.reduce((s, i) => s + i.valor, 0) || 1;
  const C = 2 * Math.PI * r;
  let cum = 0, arcs = '';
  itens.forEach((it, i) => {
    const frac = it.valor / total;
    const seglen = Math.max(frac * C, 0.6);
    const gap = C - seglen;
    const rot = -90 + cum * 360;
    arcs += `<circle class="dseg" data-i="${i}" cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${it.cor}" stroke-width="${sw}" `
      + `stroke-dasharray="${seglen.toFixed(2)} ${gap.toFixed(2)}" transform="rotate(${rot.toFixed(2)} ${cx} ${cy})" `
      + `style="animation:dpop .8s ${(0.14 * i).toFixed(2)}s cubic-bezier(.22,1.4,.36,1) backwards"></circle>`;
    cum += frac;
  });
  return arcs;
}

function renderDRE(d) {
  const dre = d.dre;
  const completa = dre.completa || [];
  const despTipo = dre.despesas_por_tipo || [];
  if (!completa.length) { renderDRE_resumo(d); return; }

  const porMacro = [];
  completa.forEach((g) => {
    const last = porMacro[porMacro.length - 1];
    if (!last || last.macro !== g.macro) porMacro.push({ macro: g.macro, titulo: MACRO_LABELS_JS[g.macro] || g.macro, grupos: [g], total: g.valor });
    else { last.grupos.push(g); last.total += g.valor; }
  });

  const fmt2 = (v) => (v < 0 ? '(' + nf.format(Math.abs(v)) + ')' : nf.format(v));
  let linhas = '';
  porMacro.forEach((m) => {
    const sinal = SINAL_MACRO_JS[m.macro] ?? 1;
    linhas += `<tr class="dre2-macro"><td>${esc(m.titulo)}</td><td>${fmt2(sinal * m.total)}</td></tr>`;
    m.grupos.forEach((g) => {
      if (m.grupos.length > 1) linhas += `<tr class="dre2-sub"><td>${esc(g.titulo)}</td><td>${fmt2(sinal * g.valor)}</td></tr>`;
      g.filhos.forEach((f) => { linhas += `<tr class="dre2-acc"><td>${esc(f.descricao)}</td><td>${fmt2(sinal * f.valor)}</td></tr>`; });
    });
  });

  // Receitas por tipo — mesmo padrão do relatório exportado (HTML/PDF), que já
  // tinha essa comparação lado a lado. Achado real (Rafael reportou "não
  // identifiquei"): isso nunca tinha sido levado pra tela AO VIVO, só existia
  // no arquivo exportado — só mostrava despesas aqui. Corrigindo agora.
  const PALETA_RECEITA = ['#0ea472', '#3ddb9e', '#1f9e6e', '#7cd9b5', '#b8ecd8', '#d7f5e8'];
  const recTipo = (dre.composicao_receitas || [])
    .filter((x) => x[1] > 0.005)
    .map((x, i) => ({ label: x[0], valor: x[1], cor: PALETA_RECEITA[i % PALETA_RECEITA.length] }));

  const totalDesp = despTipo.reduce((s, x) => s + x.valor, 0) || 1;
  const totalRec = recTipo.reduce((s, x) => s + x.valor, 0) || 1;
  const arcsDesp = _donutSvgNativo(despTipo, 90, 90, 66, 26);
  const arcsRec = _donutSvgNativo(recTipo, 90, 90, 66, 26);

  const montaLegenda = (itens, total) => itens.map((it, i) => `
    <div class="dre2-leg" data-i="${i}"><span class="sw" style="background:${it.cor}"></span>
      <span class="lbl">${esc(it.label)}</span>
      <span class="val">${brl(it.valor)}</span>
      <span class="pc" style="background:${it.cor}26;color:${it.cor}">${pct(it.valor / total * 100, 1)}</span>
    </div>`).join('');

  const prej = dre.resultado < 0;

  $('#view-dre').innerHTML = `
    <div class="vtitle-row">
      <h2 class="vtitle">DRE completa, conta por conta</h2>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <button class="act inv-export" id="btnDreHtml">Exportar HTML</button>
        <button class="act inv-export" id="btnDrePdf">Exportar PDF</button>
        <button class="act inv-export" id="btnDreCliente" style="background:linear-gradient(90deg,#e8632b,#ff9860);color:#fff;border-color:transparent">Gerar para o Cliente</button>
      </div>
    </div>
    <div class="dre2-card">
      <h3>Receitas e despesas por tipo</h3>
      <div class="dre2-2col">
        <div class="donut-group" data-grupo="rec">
          <span class="dre2-tag" style="background:#e6f7f0;color:#0ea472">RECEITAS</span>
          <div class="dre2-donut-row">
            <div class="dre2-donut-wrap dre2-donut-wrap-sm"><svg width="150" height="150" viewBox="0 0 180 180">
              <circle cx="90" cy="90" r="66" fill="none" stroke="#eef1f7" stroke-width="26"></circle>${arcsRec}</svg>
              <div class="dre2-donut-total dre2-donut-total-sm"><b>${brlCompacto(totalRec)}</b><span>receitas</span></div></div>
            <div class="dre2-legend">${montaLegenda(recTipo, totalRec)}</div>
          </div>
        </div>
        <div class="donut-group" data-grupo="desp" style="border-left:1px solid var(--line);padding-left:20px">
          <span class="dre2-tag" style="background:#fde8ea;color:#e23d4c">DESPESAS</span>
          <div class="dre2-donut-row">
            <div class="dre2-donut-wrap dre2-donut-wrap-sm"><svg width="150" height="150" viewBox="0 0 180 180">
              <circle cx="90" cy="90" r="66" fill="none" stroke="#eef1f7" stroke-width="26"></circle>${arcsDesp}</svg>
              <div class="dre2-donut-total dre2-donut-total-sm"><b>${brlCompacto(totalDesp)}</b><span>despesas</span></div></div>
            <div class="dre2-legend">${montaLegenda(despTipo, totalDesp)}</div>
          </div>
        </div>
      </div>
    </div>
    <div class="dre2-card">
      <h3>Demonstração completa do resultado — todas as contas do balancete</h3>
      <table class="dre2-table"><tbody>
        ${linhas}
        <tr class="dre2-res ${prej ? 'neg' : 'pos'}"><td>${prej ? 'Prejuízo' : 'Lucro'} Líquido do Exercício</td><td>${nf.format(Math.abs(dre.resultado))}</td></tr>
      </tbody></table>
      <div class="dre2-foot">Margem líquida: ${pct(dre.margem_liquida, 1)}</div>
    </div>`;

  const btnH = $('#btnDreHtml'), btnP = $('#btnDrePdf');
  const sugestao = ((d.empresa || {}).empresa || 'dre-completa').toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 40);
  if (btnH) btnH.addEventListener('click', async () => {
    overlay(true, 'Gerando HTML…');
    const r = await window.fiscocont.exportDreCompleta('html', sugestao);
    overlay(false);
    if (r.error) { toast(r.error, true); return; }
    if (!r.canceled) { toast('HTML salvo.'); window.fiscocont.openPath(r.path); }
  });
  if (btnP) btnP.addEventListener('click', async () => {
    overlay(true, 'Gerando PDF…');
    const r = await window.fiscocont.exportDreCompleta('pdf', sugestao);
    overlay(false);
    if (r.error) { toast(r.error, true); return; }
    if (!r.canceled) { toast('PDF salvo.'); window.fiscocont.openPath(r.path); }
  });
  const btnC = $('#btnDreCliente');
  if (btnC) btnC.addEventListener('click', async () => {
    const fmt = await perguntarFormato('Gerar DRE para o Cliente', 'Sem a marca do sistema — só a empresa e a Liddera | Inteligência em Negócios.');
    if (!fmt) return;
    overlay(true, fmt === 'pdf' ? 'Gerando PDF para o cliente…' : 'Gerando HTML para o cliente…');
    const r = await window.fiscocont.exportDreCompleta(fmt, sugestao, true);
    overlay(false);
    if (r.error) { toast(r.error, true); return; }
    if (!r.canceled) { toast((fmt === 'pdf' ? 'PDF' : 'HTML') + ' pro cliente salvo.'); window.fiscocont.openPath(r.path); }
  });

  // Hover com ESCOPO POR GRUPO — sem isso, passar o mouse na legenda de
  // Receitas destacaria por engano a fatia de mesmo índice em Despesas
  // (os dois donuts têm índices começando em 0). Mesmo fix já aplicado antes
  // no relatório exportado.
  const GRUPOS_DONUT = { rec: recTipo, desp: despTipo };
  let tip = document.querySelector('.dre2-dtip');
  if (!tip) {
    tip = document.createElement('div');
    tip.className = 'dre2-dtip';
    tip.innerHTML = '<b></b><span></span>';
    document.body.appendChild(tip);
  }
  const tipB = tip.querySelector('b'), tipS = tip.querySelector('span');
  document.querySelectorAll('.donut-group').forEach((group) => {
    const dados = GRUPOS_DONUT[group.dataset.grupo] || [];
    const total = dados.reduce((s, x) => s + x.valor, 0) || 1;
    const destaca = (i, on) => {
      const s = group.querySelector(`.dseg[data-i="${i}"]`);
      const l = group.querySelector(`.dre2-leg[data-i="${i}"]`);
      if (s) s.classList.toggle('on', on);
      if (l) l.classList.toggle('on', on);
    };
    group.querySelectorAll('.dseg').forEach((s) => {
      const it = dados[+s.dataset.i];
      s.addEventListener('mouseenter', () => destaca(s.dataset.i, true));
      s.addEventListener('mouseleave', () => { destaca(s.dataset.i, false); tip.classList.remove('show'); });
      s.addEventListener('mousemove', (e) => {
        if (!it) return;
        tipB.textContent = it.label;
        tipS.textContent = brl(it.valor) + ' · ' + pct(it.valor / total * 100, 1);
        tip.style.left = e.clientX + 'px';
        tip.style.top = (e.clientY - 10) + 'px';
        tip.classList.add('show');
      });
    });
    group.querySelectorAll('.dre2-leg').forEach((l) => {
      l.addEventListener('mouseenter', () => destaca(l.dataset.i, true));
      l.addEventListener('mouseleave', () => destaca(l.dataset.i, false));
    });
  });
}

function renderDRE_resumo(d) {
  const dre = d.dre, prej = dre.resultado < 0;
  const despOp = dre.despesa_total - dre.cmv;               // despesas oper. (inclui financeiras)
  const outrasRec = dre.receita_total - dre.receita_liquida; // outras receitas (inclui financeiras)

  const isCMV = (n) => /cmv|custo/i.test(n);
  const isFin = (n) => /financeir/i.test(n);

  // componentes de despesa (sem o CMV) — somam exatamente despOp
  const comps = (dre.composicao_despesas || []).filter((x) => !isCMV(x[0]));
  const despFin = comps.filter((x) => isFin(x[0])).reduce((s, x) => s + x[1], 0);
  const opItens = comps.filter((x) => !isFin(x[0]));         // gerais, pessoal, impostos, outras
  const somaOp = opItens.reduce((s, x) => s + x[1], 0);
  const ajusteOp = despOp - despFin - somaOp;                // resíduo p/ fechar exatamente

  // receitas abaixo da linha (financeiras + outras) — somam outrasRec
  const recFinRaw = (dre.composicao_receitas || []).filter((x) => isFin(x[0])).reduce((s, x) => s + x[1], 0);
  const recFin = Math.max(0, Math.min(recFinRaw, outrasRec));
  const recOutras = Math.max(0, outrasRec - recFin);

  const despOpNonFin = despOp - despFin;
  const resultadoOperacional = dre.lucro_bruto - despOpNonFin;
  const resultadoFinanceiro = recFin - despFin;

  const paren = (v) => '(' + nf.format(Math.abs(v)) + ')';
  const money = (v) => (v < 0 ? paren(v) : brl(v));
  const row = (lbl, val, cls = '', meta = '', vcls = '') =>
    `<div class="dre-row ${cls}"><div class="lbl">${esc(lbl)}${meta ? `<span class="tagm">${meta}</span>` : ''}</div><div class="val ${vcls}">${val}</div></div>`;
  const sub = (lbl, val) => `<div class="dre-row sub"><div class="lbl">${esc(lbl)}</div><div class="val muted">${val}</div></div>`;

  let despSubs = '';
  opItens.forEach((x) => { if (Math.abs(x[1]) > 0.005) despSubs += sub(x[0], paren(x[1])); });
  if (Math.abs(ajusteOp) > 0.5) despSubs += sub('Outras despesas operacionais', paren(ajusteOp));

  const temFin = recFin > 0.005 || despFin > 0.005;
  const finBloco = temFin ? `
      ${row('Resultado financeiro', money(resultadoFinanceiro), 'head', '', resultadoFinanceiro < 0 ? 'neg' : 'pos')}
      ${recFin > 0.005 ? sub('(+) Receitas financeiras', brl(recFin)) : ''}
      ${despFin > 0.005 ? sub('(−) Despesas financeiras', paren(despFin)) : ''}` : '';

  $('#view-dre').innerHTML = `
    <h2 class="vtitle">Demonstração de resultado do exercício (DRE)</h2>
    <div class="dre">
      ${row('Receita operacional bruta', brl(dre.receita_bruta), 'head')}
      ${row('(−) Deduções da receita bruta', paren(dre.deducoes), 'op')}
      ${row('= Receita operacional líquida', brl(dre.receita_liquida), 'sum')}
      ${row('(−) Custo das mercadorias / serviços (CMV/CPV)', paren(dre.cmv), 'op', pct(dre.peso_cmv) + ' da receita')}
      ${row('= Lucro bruto', brl(dre.lucro_bruto), 'sum', 'margem bruta ' + pct(dre.margem_bruta, 2), dre.lucro_bruto < 0 ? 'neg' : 'pos')}
      ${row('(−) Despesas operacionais', paren(despOpNonFin), 'head')}
      ${despSubs}
      ${row('= Resultado operacional', money(resultadoOperacional), 'sum', '', resultadoOperacional < 0 ? 'neg' : 'pos')}
      ${finBloco}
      ${recOutras > 0.005 ? row('(+) Outras receitas operacionais', brl(recOutras), 'op') : ''}
      ${row('= Resultado antes do IRPJ/CSLL', money(dre.resultado), 'sum', '', prej ? 'neg' : 'pos')}
      ${row((prej ? 'Prejuízo' : 'Lucro') + ' líquido do período', brl(Math.abs(dre.resultado)), 'total', 'margem líquida ' + pct(dre.margem_liquida, 2), prej ? 'neg' : 'pos')}
    </div>
    <p class="dre-nota">DRE apurada a partir do balancete. Os itens de despesa e o resultado financeiro fecham exatamente com o resultado do período. Quando IRPJ/CSLL não estão provisionados na escrita, o resultado antes e depois dos tributos coincide.</p>`;
}

function renderBalancete(d) {
  const grpNome = { ATIVO: 'Ativo', PASSIVO: 'Passivo', PL: 'Patrimônio Líquido', RESULTADO_DESP: 'Custos e Despesas', RESULTADO_REC: 'Receitas' };
  const cell = (v, lado) => {
    if (!v) return '<td class="num z">0,00</td>';
    const dc = lado ? `<span class="dc dc-${lado}">${lado}</span>` : '';
    return `<td class="num">${nf.format(v)}${dc}</td>`;
  };
  let rows = '', atual = null;
  d.todas.forEach((c) => {
    if (c.grupo !== atual) { atual = c.grupo; rows += `<tr class="grh"><td colspan="6">${grpNome[atual] || atual}</td></tr>`; }
    rows += `<tr class="${c.sintetica ? 'sint' : 'anal'}">
      <td class="cod">${esc(c.codigo || '')}</td><td class="nm">${esc(c.descricao)}</td>
      ${cell(c.saldo_anterior, c.lado_saldo_anterior)}${cell(c.debito, null)}${cell(c.credito, null)}${cell(c.saldo_atual, c.lado_saldo_atual)}</tr>`;
  });
  $('#view-balancete').innerHTML = `
    <div class="vtitle-row">
      <h2 class="vtitle">Balancete completo <span class="tagm">${d.totais_conta} contas (${d.analiticas} analíticas)</span></h2>
      <button class="act inv-export" id="btnExportBalCompl">Exportar PDF</button>
    </div>
    <table class="bal"><thead><tr>
      <th>Cód.</th><th>Descrição da conta</th><th class="num">Saldo anterior</th>
      <th class="num">Débito</th><th class="num">Crédito</th><th class="num">Saldo atual</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
  const btnBc = $('#btnExportBalCompl');
  if (btnBc) btnBc.addEventListener('click', async () => {
    const nome = ((d.empresa && d.empresa.empresa) || 'balancete-completo').replace(/[\\/:*?"<>|]+/g, ' ').trim().slice(0, 60);
    overlay(true, 'Gerando PDF do balancete completo…');
    const r = await window.fiscocont.exportBalanceteCompleto(nome);
    overlay(false);
    if (r.canceled) return;
    if (r.error) { toast(r.error, true); return; }
    toast('PDF salvo.');
    window.fiscocont.openPath(r.path);
  });
}

function renderInvertidas(d) {
  const grupos = agruparInvertidas(d);
  const total = d.invertidas.length;
  const secoes = grupos.map((g) => {
    let corpo, resumo;
    if (g.itens.length) {
      const rows = g.itens.map((c) => {
        const esp = c.natureza === 'D' ? 'Devedor (D)' : 'Credor (C)';
        return `<tr><td class="cod">${esc(c.codigo || '—')}</td><td>${esc(c.descricao)}</td>
          <td class="num"><span class="dc dc-${c.lado_saldo_atual}">${c.lado_saldo_atual}</span>${nf.format(c.saldo_atual)}</td>
          <td class="muted">${esp}</td></tr>`;
      }).join('');
      corpo = `<table class="itab"><thead><tr><th>Cód.</th><th>Conta</th><th class="num">Saldo atual</th><th>Lado esperado</th></tr></thead><tbody>${rows}</tbody></table>`;
      resumo = `<span class="count">${g.itens.length}</span><span class="soma">Σ ${brl(g.soma)}</span>`;
    } else {
      corpo = '<div class="vazio">Nenhuma conta com saldo invertido neste grupo.</div>';
      resumo = '<span class="count zero">0</span>';
    }
    return `<div class="grp g-${g.cls}"><div class="grp-head"><span class="bar"></span><h3>${g.rot}</h3>${resumo}</div>${corpo}</div>`;
  }).join('');
  $('#view-invertidas').innerHTML = `
    <div class="vtitle-row">
      <h2 class="vtitle">Saldos invertidos — conferência interna <span class="tagm">${total} conta(s) · uso interno, fora do PDF do cliente</span></h2>
      <button class="act inv-export" id="btnExportInv" ${total ? '' : 'disabled'}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 2h9l3 3v17H6z M9 12h6M9 16h4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Exportar invertidos (PDF)
      </button>
    </div>
    ${secoes}`;
  const btn = $('#btnExportInv');
  if (btn) btn.addEventListener('click', doExportInvertidas);
}

async function updateCloudBadge() {
  const link = $('#cloudLink');
  if (!link || !window.fiscocont.cloud) return;
  try {
    const s = await window.fiscocont.cloud.status();
    if (s.configured) {
      link.textContent = '☁ nuvem: ligada' + (s.projectId ? ' (' + s.projectId + ')' : '');
      link.classList.add('on');
    } else {
      link.textContent = '☁ nuvem: configurar';
      link.classList.remove('on');
    }
  } catch (_) {}
}

function showLastSync(d) {
  const el = $('#cloudLast');
  if (!el || !d) return;
  const hora = d.quando ? new Date(d.quando).toLocaleTimeString('pt-BR') : '';
  if (d.ok) {
    el.textContent = '✓ enviado ' + (hora ? '(' + hora + ')' : '') + ': ' + (d.empresa || '');
    el.className = 'cloud-last ok';
  } else {
    el.textContent = '✕ erro no envio: ' + (d.error || '');
    el.className = 'cloud-last err';
  }
}

function bindCloud() {
  const link = $('#cloudLink');
  if (!link || !window.fiscocont.cloud) return;
  link.addEventListener('click', async () => {
    const s = await window.fiscocont.cloud.status();
    if (s.configured) {
      // travado: já conectado, não permite trocar por engano
      toast('Nuvem conectada a ' + (s.projectId || 'Firebase') + ' · configuração bloqueada.');
      return;
    }
    const r = await window.fiscocont.cloud.setup();
    if (r && r.ok) { toast('Nuvem conectada: ' + (r.projectId || '')); updateCloudBadge(); }
    else if (r && r.error) { toast(r.error, true); }
  });
  window.fiscocont.cloud.onSynced((d) => {
    if (d.ok) toast('Enviado à nuvem: ' + (d.empresa || '') + (d.periodo ? ' · ' + d.periodo : ''));
    else toast('Falha ao enviar à nuvem: ' + (d.error || ''), true);
    showLastSync(d);
  });
  updateCloudBadge();
  window.fiscocont.cloud.lastSync().then((d) => d && showLastSync(d)).catch(() => {});
}

async function doExportInvertidas() {
  if (!DATA) return;
  const base = (DATA.empresa.empresa || 'saldos-invertidos').replace(/[\\/:*?"<>|]+/g, ' ').trim().slice(0, 55);
  const nome = 'Saldos invertidos - ' + base;
  try {
    overlay(true, 'Gerando PDF dos saldos invertidos…');
    const res = await window.fiscocont.exportInvertidas(nome);
    overlay(false);
    if (res.canceled) return;
    if (res.error) { toast(res.error, true); return; }
    toast('PDF dos saldos invertidos salvo.');
    window.fiscocont.openPath(res.path);
  } catch (e) { overlay(false); toast('Falha ao exportar: ' + e.message, true); }
}

// ------------------------------------------------------------------ nav
function switchView(name) {
  $$('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.view === name));
  const hasData = !!DATA;
  const contabil = ['overview', 'dre', 'balancete', 'invertidas', 'indicadores'];
  $('#empty').hidden = !(contabil.includes(name) && !hasData);
  // "Exportar PDF" do topo sempre exporta o resumo geral (Visão Geral) — fora
  // dessa tela ele confundia, parecendo que ia exportar a tela atual (DRE,
  // Indicadores etc.), quando cada uma já tem seu próprio botão de exportar
  // certo. "Trocar balancete" continua em toda tela, é uma ação global.
  const btnExp = $('#btnExport');
  if (btnExp) btnExp.style.display = (name === 'overview') ? '' : 'none';
  $$('.view').forEach((v) => (v.hidden = true));
  if (name === 'fiscal-dash') { $('#view-fiscal-dash').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'fiscal-conf') { $('#view-fiscal-conf').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'fiscal-docs') { $('#view-fiscal-docs').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'fiscal-confs') { $('#view-fiscal-confs').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'fiscal-deson') { $('#view-fiscal-deson').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'fiscal-frete') { $('#view-fiscal-frete').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'fiscal-audit') { $('#view-fiscal-audit').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'fiscal-pgdas') { $('#view-fiscal-pgdas').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'fiscal-downloads') { $('#view-fiscal-downloads').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'fiscal-efd-contrib') { $('#view-fiscal-efd-contrib').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'admin-lic') { $('#view-admin-lic').hidden = false; $('#empty').hidden = true; loadLicensePanel(); return; }
  if (name === 'admin-corrigir-sped') { $('#view-admin-corrigir-sped').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'admin-lmc') { $('#view-admin-lmc').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'historico') { $('#view-historico').hidden = false; $('#empty').hidden = true; loadHistoricoEmpresas(); return; }
  if (name === 'lote-balancetes') { $('#view-lote-balancetes').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'conciliacao') { $('#view-conciliacao').hidden = false; $('#empty').hidden = true; return; }
  if (contabil.includes(name) && hasData) {
    $('#view-' + name).hidden = false;
    if (name === 'indicadores') loadIndicadores();
    if (name === 'dre') _replayDreDonut();
  }
}

// Todas as telas do Contábil são renderizadas de uma vez na importação (não sob
// demanda), então a animação do donut da DRE já teria terminado antes do usuário
// clicar pra ver essa tela. Reinicia a animação toda vez que a tela é aberta.
function _replayDreDonut() {
  const wrap = document.querySelector('#view-dre .dre2-donut-wrap');
  if (wrap) {
    wrap.style.animation = 'none';
    wrap.getBoundingClientRect();
    wrap.style.animation = '';
  }
  document.querySelectorAll('#view-dre .dseg').forEach((s) => {
    const anim = s.style.animation;
    if (!anim) return;
    s.style.animation = 'none';
    s.getBoundingClientRect(); // força o navegador a "esquecer" o estado anterior
    s.style.animation = anim;
  });
}

function bindNav() {
  $$('.nav-item').forEach((b) => {
    if (b.classList.contains('disabled')) return;
    b.addEventListener('click', () => {
      if (b.dataset.view === 'conciliacao' && ROLE !== 'admin') {
        toast('Em breve! Esse módulo ainda está em teste.');
        return;
      }
      switchView(b.dataset.view);
    });
  });
  const btnReset = $('#btnNovaAnalise');
  if (btnReset) btnReset.addEventListener('click', resetSpedGlobal);
}

// ------------------------------------------------------------- módulos fiscais
const FISCAL = { spedAtual: null, spedPath: null, confSped: null, confXmls: null, docsSped: null, confsSped: null, confsXmls: null, desonXmls: null, freteSped: null, freteXmls: null, auditSped: null, corrSpedPath: null, lmcSemPath: null, lmcComPath: null, icmsCredXmls: null };

// SPED é compartilhado entre módulos: importou uma vez, os outros que também
// precisam dele já ficam prontos (passo 1 marcado), sem pedir de novo.
async function applySpedToAllModules(path) {
  FISCAL.spedAtual = path;
  FISCAL.spedPath = path;
  FISCAL.confSped = path;
  FISCAL.confsSped = path;
  FISCAL.docsSped = path;
  FISCAL.freteSped = path;
  FISCAL.auditSped = path;
  const pares = [
    ['#btnConfSped', '#btnConfXmls'],
    ['#btnConfSSped', '#btnConfSXmls'],
    ['#btnFreteSped', '#btnFreteXmls'],
  ];
  for (const [b1, b2] of pares) {
    const el1 = $(b1), el2 = $(b2);
    if (el1) el1.classList.add('ok');
    if (el2) el2.disabled = false;
  }
  const btnReset = $('#btnNovaAnalise');
  if (btnReset) btnReset.hidden = false;

  // Auditor de Classificação não precisa de XML — roda sozinho em segundo plano
  // sempre que o SPED muda, não importa em qual módulo foi importado.
  let auditResumo = null;
  try {
    const res = await window.fiscocont.fiscal.classificacao(path);
    if (res && res.ok) {
      const fr = $('#auditFrame');
      if (fr) {
        fr.srcdoc = res.html;
        fr.hidden = false;
        const em = $('#auditEmpty'); if (em) em.hidden = true;
        const bh = $('#btnAuditHtml'); if (bh) bh.disabled = false;
        const bp = $('#btnAuditPdf'); if (bp) bp.disabled = false;
      }
      auditResumo = res.resumo || {};
    }
  } catch (_) { /* silencioso: se falhar aqui, o botão do Auditor continua disponível manualmente */ }
  return auditResumo;
}
async function pickOrReuseSped() {
  if (FISCAL.spedAtual) return { path: FISCAL.spedAtual, reused: true };
  const pick = await window.fiscocont.fiscal.pickSped();
  if (pick.canceled || !pick.path) return { canceled: true };
  await applySpedToAllModules(pick.path);
  return { path: pick.path, reused: false };
}

// Limpa o SPED compartilhado e todos os módulos, liberando pra importar um
// arquivo diferente (ex.: trocar de empresa/cliente).
function resetSpedGlobal() {
  FISCAL.spedAtual = null; FISCAL.spedPath = null;
  FISCAL.confSped = null; FISCAL.confXmls = null;
  FISCAL.confsSped = null; FISCAL.confsXmls = null;
  FISCAL.docsSped = null;
  FISCAL.freteSped = null; FISCAL.freteXmls = null;
  FISCAL.auditSped = null;

  const pares = [
    ['#btnConfSped', '#btnConfXmls'],
    ['#btnConfSSped', '#btnConfSXmls'],
    ['#btnFreteSped', '#btnFreteXmls'],
  ];
  for (const [b1, b2] of pares) {
    const el1 = $(b1), el2 = $(b2);
    if (el1) el1.classList.remove('ok');
    if (el2) el2.disabled = true;
  }
  const twoStep = [
    ['#confFrame', '#confEmpty', ['#btnConfHtml', '#btnConfPdf', '#btnConfCliente']],
    ['#confSFrame', '#confSEmpty', ['#btnConfSHtml', '#btnConfSPdf', '#btnConfSCliente']],
    ['#freteFrame', '#freteEmpty', ['#btnFreteHtml', '#btnFretePdf']],
  ];
  const single = [
    ['#spedFrame', '#spedEmpty', ['#btnSpedHtml', '#btnSpedPdf']],
    ['#docsFrame', '#docsEmpty', ['#btnDocsHtml', '#btnDocsPdf']],
    ['#auditFrame', '#auditEmpty', ['#btnAuditHtml', '#btnAuditPdf']],
  ];
  for (const [frameId, emptyId, btnIds] of [...twoStep, ...single]) {
    const fr = $(frameId), em = $(emptyId);
    if (fr) { fr.hidden = true; fr.srcdoc = ''; }
    if (em) em.hidden = false;
    for (const bid of btnIds) { const b = $(bid); if (b) b.disabled = true; }
  }
  const btnReset = $('#btnNovaAnalise');
  if (btnReset) btnReset.hidden = true;
  toast('Pronto — importe o novo SPED em qualquer módulo.');
}

function bindFiscal() {
  const btnInd = $('#btnIndPdf');
  if (btnInd) btnInd.addEventListener('click', async () => {
    overlay(true, 'Gerando PDF dos indicadores…');
    const res = await window.fiscocont.exportIndicadores((DATA && DATA.empresa && DATA.empresa.empresa ? 'indicadores-' + DATA.empresa.empresa.split(' ')[0] : 'indicadores'));
    overlay(false);
    if (res && res.canceled) return;
    if (res && res.error) { toast(res.error, true); return; }
    if (res && res.ok) { toast('PDF salvo.'); window.fiscocont.openPath(res.path); }
  });
  if (!window.fiscocont.fiscal) return;

  // ---- Dashboard (SPED) ----
  $('#btnSpedImport').addEventListener('click', async () => {
    const pick = await pickOrReuseSped();
    if (pick.canceled) return;
    overlay(true, 'Lendo o SPED e montando o dashboard…');
    const res = await window.fiscocont.fiscal.dashboard(pick.path);
    if (res.error) { overlay(false); toast(res.error, true); return; }
    await applySpedToAllModules(pick.path);
    const fr = $('#spedFrame');
    fr.srcdoc = res.html;
    fr.hidden = false; $('#spedEmpty').hidden = true;
    $('#btnSpedHtml').disabled = false; $('#btnSpedPdf').disabled = false;

    // Mesmo SPED: já carrega a relação de Documentos de entrada junto, sem precisar importar de novo
    overlay(true, 'Montando a relação de documentos de entrada…');
    const docsRes = await window.fiscocont.fiscal.documentos(pick.path);
    overlay(false);
    if (!docsRes.error) {
      FISCAL.docsSped = pick.path;
      const docsFr = $('#docsFrame');
      if (docsFr) {
        docsFr.srcdoc = docsRes.html;
        docsFr.hidden = false;
        const de = $('#docsEmpty'); if (de) de.hidden = true;
        const bh = $('#btnDocsHtml'); if (bh) bh.disabled = false;
        const bp = $('#btnDocsPdf'); if (bp) bp.disabled = false;
      }
    }
    toast('Dashboard gerado: ' + (res.empresa || ''));
  });
  $('#btnSpedHtml').addEventListener('click', () => exportFiscal('dashboard', 'html'));
  $('#btnSpedPdf').addEventListener('click', () => exportFiscal('dashboard', 'pdf'));

  // ---- Conferência ----
  $('#btnConfSped').addEventListener('click', async () => {
    const pick = await pickOrReuseSped();
    if (pick.canceled) return;
    FISCAL.confSped = pick.path;
    $('#btnConfSped').classList.add('ok');
    $('#btnConfXmls').disabled = false;
    toast(pick.reused ? 'Usando o SPED já carregado.' : 'SPED carregado. Agora selecione o(s) .zip das notas.');
  });
  $('#btnConfXmls').addEventListener('click', async () => {
    if (!FISCAL.confSped) { toast('Importe o SPED primeiro.', true); return; }
    const pick = await window.fiscocont.fiscal.pickXmlsFolder();
    if (pick.canceled || !pick.path) return;
    FISCAL.confXmls = pick.path;
    overlay(true, 'Cruzando XMLs com o SPED… (com milhares de arquivos, pode levar alguns minutos — o antivírus do Windows escaneando cada um conta mais que o processamento em si)');
    const res = await window.fiscocont.fiscal.conferencia(FISCAL.confSped, pick.path);
    overlay(false);
    if (res.error) { toast(res.error, true); return; }
    const fr = $('#confFrame');
    fr.srcdoc = res.html;
    fr.hidden = false; $('#confEmpty').hidden = true;
    $('#btnConfHtml').disabled = false; $('#btnConfPdf').disabled = false; $('#btnConfCliente').disabled = false;
    const r = res.resumo || {};
    toast(`Conferência: ${r.importadas || 0} notas · ${r.faltantes || 0} faltante(s) · ${r.divergencias || 0} divergência(s)`);
    const btnFalt = $('#btnConfNotasFaltantes');
    btnFalt.hidden = !(r.faltantes > 0);
    btnFalt.disabled = !(r.faltantes > 0);
  });
  $('#btnConfHtml').addEventListener('click', () => exportFiscal('conf', 'html'));
  $('#btnConfPdf').addEventListener('click', () => exportFiscal('conf', 'pdf'));
  $('#btnConfCliente').addEventListener('click', () => exportFiscal('conf', 'html', true));

  // ---- Conferência de Saídas ----
  const bConfS = $('#btnConfSSped');
  if (bConfS) {
    bConfS.addEventListener('click', async () => {
      const pick = await pickOrReuseSped();
      if (pick.canceled) return;
      FISCAL.confsSped = pick.path;
      $('#btnConfSSped').classList.add('ok');
      $('#btnConfSXmls').disabled = false;
      toast(pick.reused ? 'Usando o SPED já carregado.' : 'SPED carregado. Agora selecione o(s) .zip das notas de saída.');
    });
    $('#btnConfSXmls').addEventListener('click', async () => {
      if (!FISCAL.confsSped) { toast('Importe o SPED primeiro.', true); return; }
      const pick = await window.fiscocont.fiscal.pickXmlsFolder();
      if (pick.canceled || !pick.path) return;
      FISCAL.confsXmls = pick.path;
      overlay(true, 'Cruzando XMLs de saída com o SPED… (com milhares de arquivos, pode levar alguns minutos — o antivírus do Windows escaneando cada um conta mais que o processamento em si)');
      const res = await window.fiscocont.fiscal.conferenciaSaidas(FISCAL.confsSped, pick.path);
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      const fr = $('#confSFrame');
      fr.srcdoc = res.html;
      fr.hidden = false; $('#confSEmpty').hidden = true;
      $('#btnConfSHtml').disabled = false; $('#btnConfSPdf').disabled = false; $('#btnConfSCliente').disabled = false;
      const r = res.resumo || {};
      toast(`Conferência de saídas: ${r.importadas || 0} notas · ${r.faltantes || 0} faltante(s) · ${r.divergencias || 0} divergência(s)`);
    });
    $('#btnConfSHtml').addEventListener('click', () => exportFiscal('confSaidas', 'html'));
    $('#btnConfSPdf').addEventListener('click', () => exportFiscal('confSaidas', 'pdf'));
    $('#btnConfSCliente').addEventListener('click', () => exportFiscal('confSaidas', 'html', true));
  }

  // ---- Conferência ICMS Desonerado (só XMLs, sem SPED) ----
  const bDeson = $('#btnDesonXmls');
  if (bDeson) {
    bDeson.addEventListener('click', async () => {
      const pick = await window.fiscocont.fiscal.pickXmlsFolder();
      if (pick.canceled || !pick.path) return;
      FISCAL.desonXmls = pick.path;
      overlay(true, 'Analisando ICMS desonerado nos XMLs de entrada…');
      const res = await window.fiscocont.fiscal.desoneracao(pick.path);
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      const fr = $('#desonFrame');
      fr.srcdoc = res.html;
      fr.hidden = false; $('#desonEmpty').hidden = true;
      $('#btnDesonHtml').disabled = false; $('#btnDesonPdf').disabled = false;
      const r = res.resumo || {};
      toast(r.identificado ? `ICMS desonerado identificado em ${r.comDeson} nota(s) · R$ ${(r.totalDeson || 0).toFixed(2)}` : 'Nenhum ICMS desonerado identificado nas entradas.');
    });
    $('#btnDesonHtml').addEventListener('click', () => exportFiscal('desoneracao', 'html'));
    $('#btnDesonPdf').addEventListener('click', () => exportFiscal('desoneracao', 'pdf'));
  }

  // ---- Classificação de Frete (CT-e) ----
  const bFrete = $('#btnFreteSped');
  if (bFrete) {
    bFrete.addEventListener('click', async () => {
      const pick = await pickOrReuseSped();
      if (pick.canceled) return;
      FISCAL.freteSped = pick.path;
      $('#btnFreteSped').classList.add('ok');
      $('#btnFreteXmls').disabled = false;
      toast(pick.reused ? 'Usando o SPED já carregado.' : 'SPED carregado. Agora selecione o(s) .zip dos CT-e.');
    });
    $('#btnFreteXmls').addEventListener('click', async () => {
      if (!FISCAL.freteSped) { toast('Importe o SPED primeiro.', true); return; }
      const pick = await window.fiscocont.fiscal.pickXmlsFolder();
      if (pick.canceled || !pick.path) return;
      FISCAL.freteXmls = pick.path;
      overlay(true, 'Cruzando CT-e com as NF-e do SPED…');
      const res = await window.fiscocont.fiscal.frete(FISCAL.freteSped, pick.path);
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      const fr = $('#freteFrame');
      fr.srcdoc = res.html;
      fr.hidden = false; $('#freteEmpty').hidden = true;
      $('#btnFreteHtml').disabled = false; $('#btnFretePdf').disabled = false;
      const r = res.resumo || {};
      toast(`${r.qtdCtes || 0} CT-e · ${r.custo || 0} custo · ${r.despesa || 0} despesa${r.naoCte ? ` · ${r.naoCte} fora do escopo` : ''}`);
    });
    $('#btnFreteHtml').addEventListener('click', () => exportFiscal('frete', 'html'));
    $('#btnFretePdf').addEventListener('click', () => exportFiscal('frete', 'pdf'));
  }

  // ---- Auditor de Classificação Fiscal (só SPED, roda direto) ----
  const bAudit = $('#btnAuditSped');
  if (bAudit) {
    bAudit.addEventListener('click', async () => {
      const pick = await pickOrReuseSped();
      if (pick.canceled) return;
      overlay(true, 'Conferindo CFOP × CST, itens e combustível…');
      const r = (await applySpedToAllModules(pick.path)) || {};
      overlay(false);
      const total = (r.cfopCst || 0) + (r.mesmoItem || 0) + (r.combustivel || 0) + (r.remessaRetorno || 0);
      toast(total > 0 ? `${total} ocorrência(s) encontrada(s) pra revisar` : 'Nenhuma incoerência encontrada.');
    });
    $('#btnAuditHtml').addEventListener('click', () => exportFiscal('classificacao', 'html'));
    $('#btnAuditPdf').addEventListener('click', () => exportFiscal('classificacao', 'pdf'));
  }

  // ---- Download de Documentos Fiscais (NFS-e via ADN) ----
  let DL_EMPRESAS = [];
  let DL_BAIXADAS_SESSAO = 0;

  function _fmtCnpjJs(cnpj) {
    if (!cnpj || cnpj.length !== 14) return cnpj || '';
    return `${cnpj.slice(0, 2)}.${cnpj.slice(2, 5)}.${cnpj.slice(5, 8)}/${cnpj.slice(8, 12)}-${cnpj.slice(12)}`;
  }

  // período/empresa usados no último painel montado — pra avisar quando
  // os campos da tela mudarem depois (evita achar que o painel na tela é
  // do período novo quando ainda é do antigo).
  let DL_PAINEL_PERIODO = null;

  // "Ver painel" só libera com empresa + Data inicial + Data final válidas
  // (pedido do Rafael, 26/09).
  function dlAtualizarBotaoPainel() {
    const btn = $('#btnDlVerPainel');
    if (!btn) return;
    const empresaId = $('#dlSelectEmpresa').value;
    const ini = $('#dlDataInicial').value;
    const fim = $('#dlDataFinal').value;
    let motivo = '';
    if (!empresaId) motivo = 'Cadastre e escolha uma empresa para liberar o painel.';
    else if (!ini || !fim) motivo = 'Informe a Data inicial e a Data final acima para liberar o painel.';
    else if (ini > fim) motivo = 'A Data inicial não pode ser depois da Data final.';
    btn.disabled = !!motivo;
    const dica = $('#dlPainelDica');
    dica.textContent = motivo;
    dica.hidden = !motivo;
    const desat = $('#dlPainelDesatualizado');
    desat.hidden = !(DL_PAINEL_PERIODO && (DL_PAINEL_PERIODO.empresaId !== empresaId
      || DL_PAINEL_PERIODO.ini !== ini || DL_PAINEL_PERIODO.fim !== fim));
  }

  function dlAtualizarBotaoBaixar() {
    const temEmpresa = DL_EMPRESAS.length > 0;
    const temPasta = $('#dlPastaTexto').textContent !== 'Nenhuma pasta escolhida ainda';
    $('#btnDlBaixar').disabled = !(temEmpresa && temPasta);
    dlAtualizarBotaoPainel();
  }

  async function dlCarregarEmpresas() {
    DL_EMPRESAS = await window.fiscocont.fiscal.certListar();
    $('#dlKpiEmpresas').textContent = DL_EMPRESAS.length;

    const agora = new Date();
    const em30dias = new Date(agora.getTime() + 30 * 24 * 60 * 60 * 1000);
    const vencendo = DL_EMPRESAS.filter((e) => {
      const val = new Date(e.validade);
      return val >= agora && val <= em30dias;
    }).length;
    $('#dlKpiVencendo').textContent = vencendo;

    const semEmpresas = $('#dlSemEmpresas');
    const tabela = $('#dlTabelaEmpresas');
    const corpo = $('#dlTabelaEmpresasBody');
    const select = $('#dlSelectEmpresa');

    if (!DL_EMPRESAS.length) {
      semEmpresas.hidden = false;
      tabela.hidden = true;
      select.innerHTML = '<option value="">Cadastre uma empresa primeiro</option>';
      dlAtualizarBotaoBaixar();
      return;
    }
    semEmpresas.hidden = true;
    tabela.hidden = false;

    corpo.innerHTML = DL_EMPRESAS.map((e) => {
      const val = new Date(e.validade);
      const diasRestantes = Math.floor((val - agora) / (24 * 60 * 60 * 1000));
      let corBadge = 'background:#eaf3de;color:#27500a';
      if (diasRestantes < 0) corBadge = 'background:#fcebeb;color:#791f1f';
      else if (diasRestantes <= 30) corBadge = 'background:#faeeda;color:#854f0b';
      const validadeTexto = diasRestantes < 0 ? `${e.validade} · vencido` : (diasRestantes <= 30 ? `${e.validade} · vence em ${diasRestantes} dias` : e.validade);
      const ultimoTexto = e.ultimoDownload ? new Date(e.ultimoDownload).toLocaleString('pt-BR') : 'nunca';
      return `<tr style="border-top:1px solid var(--line)">
        <td style="padding:9px 8px">${_esc(e.razaoSocial)}</td>
        <td style="padding:9px 8px;color:var(--ink2)">${_esc(_fmtCnpjJs(e.cnpj))}</td>
        <td style="padding:9px 8px"><span style="${corBadge};font-size:11px;padding:2px 9px;border-radius:6px">${_esc(validadeTexto)}</span></td>
        <td style="padding:9px 8px;color:var(--ink2)">${_esc(ultimoTexto)}</td>
        <td style="padding:9px 8px;text-align:right"><button class="act inv-export" data-remover="${_esc(e.id)}" style="padding:3px 10px;font-size:11px">Remover</button></td>
      </tr>`;
    }).join('');
    corpo.querySelectorAll('button[data-remover]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        if (!confirm('Remover essa empresa? Vai precisar cadastrar o certificado de novo se quiser usar de novo.')) return;
        const res = await window.fiscocont.fiscal.certRemover(btn.dataset.remover);
        if (res.error) { toast(res.error, true); return; }
        toast('Empresa removida.');
        dlCarregarEmpresas();
      });
    });

    select.innerHTML = DL_EMPRESAS.map((e) => `<option value="${_esc(e.id)}">${_esc(e.razaoSocial)} — ${_esc(_fmtCnpjJs(e.cnpj))}</option>`).join('');
    dlAtualizarBotaoBaixar();
  }

  async function dlCarregarPasta() {
    const pasta = await window.fiscocont.fiscal.pastaBaseGet();
    $('#dlPastaTexto').textContent = pasta || 'Nenhuma pasta escolhida ainda';
    dlAtualizarBotaoBaixar();
  }

  const btnDlCadastrarCert = $('#btnDlCadastrarCert');
  if (btnDlCadastrarCert) {
    let dlCertPfxPath = null;
    let dlCertInfo = null;

    btnDlCadastrarCert.addEventListener('click', () => {
      dlCertPfxPath = null;
      dlCertInfo = null;
      $('#dlCertArquivoTexto').value = '';
      $('#dlCertSenha').value = '';
      $('#dlCertErro').hidden = true;
      $('#dlCertPreview').hidden = true;
      $('#btnDlCertSalvar').hidden = true;
      $('#dlModalCert').hidden = false;
    });
    $('#btnDlCertCancelar').addEventListener('click', () => { $('#dlModalCert').hidden = true; });

    $('#btnDlCertProcurar').addEventListener('click', async () => {
      const pick = await window.fiscocont.fiscal.pickPfx();
      if (pick.canceled) return;
      dlCertPfxPath = pick.path;
      $('#dlCertArquivoTexto').value = pick.path.split(/[\\/]/).pop();
    });

    $('#btnDlCertVerificar').addEventListener('click', async () => {
      if (!dlCertPfxPath) { toast('Escolha o arquivo do certificado primeiro.', true); return; }
      const senha = $('#dlCertSenha').value;
      if (!senha) { toast('Digite a senha do certificado.', true); return; }
      overlay(true, 'Lendo o certificado…');
      const res = await window.fiscocont.fiscal.certValidar(dlCertPfxPath, senha);
      overlay(false);
      if (res.error) {
        $('#dlCertErro').textContent = res.error;
        $('#dlCertErro').hidden = false;
        $('#dlCertPreview').hidden = true;
        $('#btnDlCertSalvar').hidden = true;
        return;
      }
      $('#dlCertErro').hidden = true;
      dlCertInfo = res.info;
      $('#dlCertPreviewNome').textContent = res.info.razao_social;
      $('#dlCertPreviewDetalhe').textContent = `CNPJ ${_fmtCnpjJs(res.info.cnpj)} · válido até ${res.info.validade}`;
      $('#dlCertPreview').hidden = false;
      $('#btnDlCertSalvar').hidden = false;
    });

    $('#btnDlCertSalvar').addEventListener('click', async () => {
      if (!dlCertInfo || !dlCertPfxPath) return;
      const senha = $('#dlCertSenha').value;
      overlay(true, 'Salvando…');
      const res = await window.fiscocont.fiscal.certSalvar(dlCertPfxPath, senha, dlCertInfo);
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      toast('Empresa cadastrada.');
      $('#dlModalCert').hidden = true;
      dlCarregarEmpresas();
    });
  }

  const btnDlImportarLote = $('#btnDlImportarLote');
  if (btnDlImportarLote) {
    let dlLoteResultados = [];

    function dlLoteRenderizar() {
      const wrap = $('#dlLoteTabelaWrap');
      const vazio = $('#dlLoteVazio');
      const body = $('#dlLoteTabelaBody');
      if (!dlLoteResultados.length) { wrap.hidden = true; vazio.hidden = false; return; }
      vazio.hidden = true; wrap.hidden = false;
      body.innerHTML = dlLoteResultados.map((r, i) => {
        if (r.ok) {
          return `<tr>
            <td style="padding:7px 8px">${_esc(r.nomeArquivo)}</td>
            <td style="padding:7px 8px">${_esc(r.info.razao_social)}<br><span style="font-size:10.5px;color:var(--ink2)">CNPJ ${_esc(_fmtCnpjJs(r.info.cnpj))}</span></td>
            <td style="padding:7px 8px;color:#0ea472;font-weight:600">✓ Identificada</td>
            <td></td></tr>`;
        }
        return `<tr>
          <td style="padding:7px 8px">${_esc(r.nomeArquivo)}<br><span style="font-size:10.5px;color:#854f0b">${_esc(r.erro || 'Precisa de senha')}${r.detalhe && !/password/i.test(r.detalhe) ? ' (detalhe técnico: ' + _esc(r.detalhe) + ')' : ''}</span></td>
          <td style="padding:7px 8px;color:var(--ink2);font-size:11px">${r.qtdTentadas ? 'tentei ' + r.qtdTentadas + ' palpite(s) do nome' : '(nenhum palpite no nome)'}</td>
          <td style="padding:7px 8px"><input type="password" data-idx="${i}" class="dl-lote-senha" value="${_esc(r.senhaTentativa || '')}" style="width:130px"></td>
          <td style="padding:7px 8px"><button class="act inv-export dl-lote-tentar" data-idx="${i}" style="padding:3px 10px;font-size:11px">Tentar</button></td></tr>`;
      }).join('');
      body.querySelectorAll('.dl-lote-tentar').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const idx = Number(btn.dataset.idx);
          const senha = body.querySelector(`.dl-lote-senha[data-idx="${idx}"]`).value;
          if (!senha) { toast('Digite uma senha pra tentar.', true); return; }
          overlay(true, 'Verificando…');
          const res = await window.fiscocont.fiscal.certValidar(dlLoteResultados[idx].caminho, senha);
          overlay(false);
          if (res.error) { toast(res.error, true); return; }
          dlLoteResultados[idx] = { ...dlLoteResultados[idx], ok: true, info: res.info, senhaTentativa: senha };
          dlLoteRenderizar();
        });
      });
      const okCount = dlLoteResultados.filter((r) => r.ok).length;
      $('#dlLoteResumo').textContent = `${okCount} de ${dlLoteResultados.length} identificada(s)`;
      $('#btnDlLoteSalvarTodos').disabled = okCount === 0;
    }

    btnDlImportarLote.addEventListener('click', async () => {
      const pick = await window.fiscocont.fiscal.pickPfxLote();
      if (pick.canceled) return;
      dlLoteResultados = [];
      dlLoteRenderizar();
      $('#dlModalLote').hidden = false;
      overlay(true, `Testando a senha de ${pick.paths.length} certificado(s)…`);
      const res = await window.fiscocont.fiscal.certImportarLote(pick.paths);
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      dlLoteResultados = res.resultados;
      dlLoteRenderizar();
    });
    $('#btnDlLoteFechar').addEventListener('click', () => { $('#dlModalLote').hidden = true; });
    $('#btnDlLoteSalvarTodos').addEventListener('click', async () => {
      const validos = dlLoteResultados.filter((r) => r.ok);
      overlay(true, `Cadastrando ${validos.length} empresa(s)…`);
      let salvos = 0, comErro = [];
      for (const r of validos) {
        const res = await window.fiscocont.fiscal.certSalvar(r.caminho, r.senhaTentativa, r.info);
        if (res.error) comErro.push(`${r.info.razao_social}: ${res.error}`);
        else salvos++;
      }
      overlay(false);
      $('#dlModalLote').hidden = true;
      toast(comErro.length ? `${salvos} cadastrada(s), ${comErro.length} com erro.` : `${salvos} empresa(s) cadastrada(s).`, comErro.length > 0);
      dlCarregarEmpresas();
    });
  }

  const btnDlEscolherPasta = $('#btnDlEscolherPasta');
  if (btnDlEscolherPasta) {
    btnDlEscolherPasta.addEventListener('click', async () => {
      const res = await window.fiscocont.fiscal.pickPastaBase();
      if (res.canceled) return;
      $('#dlPastaTexto').textContent = res.path;
      dlAtualizarBotaoBaixar();
    });
  }

  const btnDlBaixar = $('#btnDlBaixar');
  if (btnDlBaixar) {
    btnDlBaixar.addEventListener('click', async () => {
      if (btnDlBaixar.disabled) return; // achado real: clique duplo enquanto já está baixando pode disparar 2 downloads ao mesmo tempo e confundir a contagem
      const empresaId = $('#dlSelectEmpresa').value;
      const dataInicial = $('#dlDataInicial').value;
      const dataFinal = $('#dlDataFinal').value;
      const gerarPdf = $('#dlGerarPdf').checked;
      if (!empresaId) { toast('Escolha uma empresa.', true); return; }
      if (!dataInicial || !dataFinal) { toast('Escolha o período (data inicial e final).', true); return; }
      btnDlBaixar.disabled = true;
      overlay(true, 'Baixando NFS-e — pode levar um tempo dependendo do volume…');
      let res;
      try {
        res = await window.fiscocont.fiscal.nfseBaixar(empresaId, dataInicial, dataFinal, gerarPdf);
      } finally {
        overlay(false);
        btnDlBaixar.disabled = false;
      }
      if (res.error) { toast(res.error, true); return; }
      const r = res.resultado;
      DL_BAIXADAS_SESSAO += r.salvos;
      $('#dlKpiDocs').textContent = DL_BAIXADAS_SESSAO;
      const box = $('#dlResultado');
      box.hidden = false;
      box.innerHTML = `
        <div style="font-size:14px;font-weight:600;margin-bottom:10px">Resultado</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;font-size:13px">
          <div><b style="font-size:18px;color:#0ea472">${r.salvos}</b><br>notas salvas</div>
          <div><b style="font-size:18px">${r.ignorados_fora_periodo}</b><br>fora do período (ignoradas)</div>
          <div><b style="font-size:18px">${r.paginas_lidas}</b><br>páginas consultadas</div>
        </div>
        ${gerarPdf ? `<div style="margin-top:10px;font-size:12px;color:var(--ink2)">PDFs (DANFSe) gerados: <b>${r.pdfs_gerados || 0}</b>${r.pdfs_erro ? ` · <span style="color:#c92a2a">${r.pdfs_erro} com erro ao gerar</span>` : ''}</div>` : ''}
        <div style="margin-top:6px;font-size:12px;color:var(--ink2)">Salvo em: ${_esc(r.pasta)}</div>
        <button class="act inv-export" id="btnDlAbrirPasta" style="margin-top:10px">Abrir pasta</button>`;
      $('#btnDlAbrirPasta').addEventListener('click', () => window.fiscocont.openPath(r.pasta));
      toast(`${r.salvos} nota(s) baixada(s).`);
      dlCarregarEmpresas();
      dlAnalisar(); // mostra o painel sozinho assim que termina de baixar
    });
    dlCarregarEmpresas();
    dlCarregarPasta();

    // botão "PDF" de cada nota, clicado dentro do iframe do painel — o
    // próprio iframe manda um postMessage (não dá pra addEventListener
    // direto num elemento de dentro de um srcdoc de outra origem)
    window.addEventListener('message', async (ev) => {
      if (!ev.data || ev.data.tipo !== 'fiscocont-nfse-pdf') return;
      const empresaId = $('#dlSelectEmpresa').value;
      if (!empresaId) return;
      overlay(true, 'Abrindo o PDF (gera na hora se ainda não existir)…');
      const res = await window.fiscocont.fiscal.nfsePdfAbrir(empresaId, ev.data.chave);
      overlay(false);
      if (res.error) toast(res.error, true);
    });

    // ---- Painel das notas já baixadas (dashboard + lista, tudo numa tela) ----
    let DL_ULTIMO_PAINEL_HTML = null;

    // Gera a pizza (não donut) de com×sem retenção em JS, e troca no HTML
    // que o Python devolve — evita precisar recompilar o núcleo Python só
    // por causa do gráfico (o resto do painel continua vindo do núcleo já
    // testado e funcionando). % dentro da fatia, giro na entrada, realce
    // no hover — igual ao que foi combinado.
    function _pizzaComSemRetencao(comQtd, semQtd) {
      const total = comQtd + semQtd;
      if (total === 0) return null; // mantém a mensagem "Nenhuma nota ainda" original
      const R = 130, CX = 140, CY = 140;
      function fatia(valor, inicioAng) {
        const frac = valor / total;
        const angFim = inicioAng + frac * 360;
        const rad1 = (inicioAng - 90) * Math.PI / 180, rad2 = (angFim - 90) * Math.PI / 180;
        const x1 = CX + R * Math.cos(rad1), y1 = CY + R * Math.sin(rad1);
        const x2 = CX + R * Math.cos(rad2), y2 = CY + R * Math.sin(rad2);
        const grandeArco = frac > 0.5 ? 1 : 0;
        const meio = (inicioAng + angFim) / 2, radM = (meio - 90) * Math.PI / 180;
        const lx = CX + R * 0.62 * Math.cos(radM), ly = CY + R * 0.62 * Math.sin(radM);
        // fatia única (100%) não fecha com arco - usa círculo cheio
        const d = frac >= 0.999
          ? `M ${CX} ${CY - R} A ${R} ${R} 0 1 1 ${CX - 0.01} ${CY - R} Z`
          : `M ${CX} ${CY} L ${x1.toFixed(2)} ${y1.toFixed(2)} A ${R} ${R} 0 ${grandeArco} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`;
        return { d, angFim, lx, ly, pct: Math.round(frac * 100) };
      }
      let ang = 0;
      const partes = [];
      if (semQtd > 0) { const f = fatia(semQtd, ang); partes.push({ ...f, cor: '#0ea472' }); ang = f.angFim; }
      if (comQtd > 0) { const f = fatia(comQtd, ang); partes.push({ ...f, cor: '#e8632b' }); ang = f.angFim; }
      const paths = partes.map((p) => `<path d="${p.d}" fill="${p.cor}" class="fatia-pizza"/>`).join('');
      const labels = partes.map((p) => p.pct >= 6 ? `<text x="${p.lx.toFixed(1)}" y="${p.ly.toFixed(1)}" text-anchor="middle" font-size="22" font-weight="600" fill="#fff">${p.pct}%</text>` : '').join('');
      const legenda = [
        semQtd > 0 ? `<div class="lg"><span class="dot" style="background:#0ea472"></span>Sem retenção<b>${semQtd}</b></div>` : '',
        comQtd > 0 ? `<div class="lg"><span class="dot" style="background:#e8632b"></span>Com retenção<b>${comQtd}</b></div>` : '',
      ].join('');
      return `<div class='donut-row'><svg id="pizzaRetSvg" width="260" height="260" viewBox="0 0 280 280" style="transform-origin:140px 140px;transition:transform 1.1s cubic-bezier(.2,.8,.2,1);flex:0 0 auto">${paths}${labels}</svg><div class='legend'>${legenda}</div></div>
      <style>.fatia-pizza{transition:filter .15s,opacity .15s}.donut-row:hover .fatia-pizza:not(:hover){opacity:.75}.fatia-pizza:hover{filter:drop-shadow(0 4px 10px rgba(31,42,90,.4))}</style>
      <script>requestAnimationFrame(function(){setTimeout(function(){var el=document.getElementById('pizzaRetSvg');if(el)el.style.transform='rotate(360deg)';},100);});</script>`;
    }

    async function dlAnalisar() {
      const empresaId = $('#dlSelectEmpresa').value;
      if (!empresaId) { toast('Escolha uma empresa.', true); return; }
      const dataInicial = $('#dlDataInicial').value;
      const dataFinal = $('#dlDataFinal').value;
      if (!dataInicial || !dataFinal) { toast('Informe a Data inicial e a Data final antes de ver o painel.', true); return; }
      if (dataInicial > dataFinal) { toast('A Data inicial não pode ser depois da Data final.', true); return; }
      overlay(true, 'Montando o painel…');
      const res = await window.fiscocont.fiscal.nfseAnalise(empresaId, dataInicial, dataFinal);
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      let painelHtml = res.painelHtml;
      const novaPizza = _pizzaComSemRetencao(res.resumo.qtd_com_retencao, res.resumo.qtd_sem_retencao);
      if (novaPizza) {
        painelHtml = painelHtml.replace(
          /<h3><span class="dot"><\/span>Com × sem retenção<\/h3>[\s\S]*?(?=<div class="card"><h3><span class="dot"><\/span>Top parceiros por valor<\/h3>)/,
          `<h3><span class="dot"></span>Com × sem retenção</h3>\n    ${novaPizza}\n  </div>\n  `
        );
      }
      DL_ULTIMO_PAINEL_HTML = painelHtml;
      DL_PAINEL_PERIODO = { empresaId, ini: dataInicial, fim: dataFinal };
      $('#btnDlExportarPainel').disabled = false;
      const fr = $('#dlAnaliseFrame');
      fr.srcdoc = painelHtml;
      fr.hidden = false;
      dlAtualizarBotaoPainel();
    }
    $('#btnDlVerPainel').addEventListener('click', () => dlAnalisar());
    ['#dlSelectEmpresa', '#dlDataInicial', '#dlDataFinal'].forEach((sel) => {
      $(sel).addEventListener('input', dlAtualizarBotaoPainel);
      $(sel).addEventListener('change', dlAtualizarBotaoPainel);
    });
    dlAtualizarBotaoPainel();
    $('#btnDlExportarPainel').addEventListener('click', async () => {
      if (!DL_ULTIMO_PAINEL_HTML) return;
      const nomeEmpresa = $('#dlSelectEmpresa').selectedOptions[0]?.textContent || '';
      const res = await window.fiscocont.fiscal.nfseExportarHtml(DL_ULTIMO_PAINEL_HTML, 'painel', nomeEmpresa);
      if (res.canceled) return;
      if (res.error) { toast(res.error, true); return; }
      toast('Painel exportado.');
      window.fiscocont.openPath(res.path);
    });
  }

  // ---- Painel do Simples Nacional (Extrato do PGDAS-D) ----
  const bPgdas = $('#btnPgdasPick');
  if (bPgdas) {
    bPgdas.addEventListener('click', async () => {
      const pick = await window.fiscocont.fiscal.pickPgdas();
      if (pick.canceled || !pick.path) return;
      FISCAL.pgdasPath = pick.path;
      overlay(true, 'Lendo o Extrato do PGDAS-D…');
      const res = await window.fiscocont.fiscal.pgdas(pick.path);
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      const fr = $('#pgdasFrame');
      fr.srcdoc = res.html;
      fr.hidden = false; $('#pgdasEmpty').hidden = true;
      $('#btnPgdasHtml').disabled = false; $('#btnPgdasPdf').disabled = false;
      const r = res.resumo || {};
      toast(r.empresa ? `${r.empresa} · PA ${r.pa} · alíquota efetiva ${(r.aliquota || 0).toFixed(2).replace('.', ',')}%` : 'Extrato importado.');
    });
    $('#btnPgdasHtml').addEventListener('click', () => exportFiscal('pgdas', 'html'));
    $('#btnPgdasPdf').addEventListener('click', () => exportFiscal('pgdas', 'pdf'));
  }

  // ---- Correção do SPED Fiscal (restrito ao Admin) ----
  const bCorrPick = $('#btnCorrSpedPick');
  if (bCorrPick) {
    let corrSpedPath = null;
    bCorrPick.addEventListener('click', async () => {
      const pick = await window.fiscocont.fiscal.pickSped();
      if (pick.canceled || !pick.path) return;
      corrSpedPath = pick.path;
      FISCAL.corrSpedPath = pick.path;
      $('#btnCorrSpedVerOriginal').disabled = false;
      $('#btnCorrSpedRodar').disabled = false;
      $('#corrSpedResumo').hidden = true;
      toast('SPED selecionado: ' + pick.path.split(/[\\/]/).pop());
    });

    $('#btnCorrSpedVerOriginal').addEventListener('click', async () => {
      if (!corrSpedPath) return;
      overlay(true, 'Lendo todos os dados do SPED…');
      const res = await window.fiscocont.fiscal.visualizarSped(corrSpedPath);
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      const fr = $('#corrSpedFrame');
      fr.srcdoc = res.html;
      fr.hidden = false; $('#corrSpedEmpty').hidden = true; $('#corrSpedResumo').hidden = true;
    });

    $('#btnCorrSpedRodar').addEventListener('click', async () => {
      if (!corrSpedPath) return;
      overlay(true, 'Corrigindo o SPED (C191, E500, GTIN, CEST, COD_NAT)…');
      const res = await window.fiscocont.fiscal.corrigirSped(corrSpedPath, []);
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      const r = res.resumo || {};
      const box = $('#corrSpedResumo');
      box.hidden = false;
      box.innerHTML = `
        <div class="card" style="border-left:4px solid #e23d4c;margin-bottom:16px">
          <h3 style="margin:0 0 12px">Correções aplicadas</h3>
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;font-size:13px">
            <div><b style="font-size:20px;color:#1f2a5a">${r.c191_removidos ?? 0}</b><br>C191 removidos</div>
            <div><b style="font-size:20px;color:#1f2a5a">${r.e500_linhas_removidas ?? 0}</b><br>Linhas do E500 removidas</div>
            <div><b style="font-size:20px;color:#1f2a5a">${r.gtin_limpos ?? 0}</b><br>GTIN limpos</div>
            <div><b style="font-size:20px;color:#1f2a5a">${r.cest_limpos ?? 0}</b><br>CEST limpos</div>
            <div><b style="font-size:20px;color:#1f2a5a">${r.cod_nat_corrigidos ?? 0}</b><br>COD_NAT corrigidos</div>
            <div><b style="font-size:20px;color:#1f2a5a">${(r.registro_0400_criado || []).length}</b><br>Registros 0400 criados</div>
          </div>
          <div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap">
            <button class="act inv-export" id="btnCorrSpedVerCorrigido">Ver todos os dados (corrigido)</button>
            <button class="act inv-export" id="btnCorrSpedVerDashboard" style="background:#1f2a5a;color:#fff;border-color:transparent">Ver dashboard animado</button>
            <button class="act inv-export" id="btnCorrSpedHtml">Exportar HTML</button>
            <button class="act inv-export" id="btnCorrSpedPdf">Exportar PDF</button>
            <button class="act inv-export" id="btnCorrSpedBaixar" style="background:#0ea472;color:#fff;border-color:transparent">Baixar SPED corrigido</button>
          </div>
        </div>`;
      $('#btnCorrSpedVerDashboard').addEventListener('click', async () => {
        overlay(true, 'Montando o dashboard…');
        const resD = await window.fiscocont.fiscal.corrigirSpedDashboard(corrSpedPath);
        overlay(false);
        if (resD.error) { toast(resD.error, true); return; }
        const fr = $('#corrSpedFrame');
        fr.srcdoc = resD.html;
        fr.hidden = false; $('#corrSpedEmpty').hidden = true;
      });
      $('#btnCorrSpedHtml').addEventListener('click', () => exportFiscal('corretor', 'html'));
      $('#btnCorrSpedPdf').addEventListener('click', () => exportFiscal('corretor', 'pdf'));
      $('#btnCorrSpedVerCorrigido').addEventListener('click', async () => {
        overlay(true, 'Lendo todos os dados do SPED corrigido…');
        const res2 = await window.fiscocont.fiscal.visualizarSpedCorrigido();
        overlay(false);
        if (res2.error) { toast(res2.error, true); return; }
        const fr = $('#corrSpedFrame');
        fr.srcdoc = res2.html;
        fr.hidden = false; $('#corrSpedEmpty').hidden = true;
      });
      $('#btnCorrSpedBaixar').addEventListener('click', async () => {
        const res3 = await window.fiscocont.fiscal.baixarSpedCorrigido();
        if (res3.canceled) return;
        if (res3.error) { toast(res3.error, true); return; }
        toast('SPED corrigido salvo.');
        window.fiscocont.openPath(res3.path);
      });
      toast('Correção concluída — confira o resumo.');
    });
  }

  // ---- Substituir LMC de Combustíveis (Admin) ----
  const bLmcSemPick = $('#btnLmcSemPick');
  if (bLmcSemPick) {
    bLmcSemPick.addEventListener('click', async () => {
      const pick = await window.fiscocont.fiscal.pickSped();
      if (pick.canceled || !pick.path) return;
      FISCAL.lmcSemPath = pick.path;
      $('#btnLmcComPick').disabled = false;
      $('#lmcResumo').hidden = true;
      toast('SPED do Domínio selecionado: ' + pick.path.split(/[\\/]/).pop());
    });

    $('#btnLmcComPick').addEventListener('click', async () => {
      const pick = await window.fiscocont.fiscal.pickSped();
      if (pick.canceled || !pick.path) return;
      FISCAL.lmcComPath = pick.path;
      $('#btnLmcRodar').disabled = false;
      $('#lmcResumo').hidden = true;
      toast('SPED do cliente selecionado: ' + pick.path.split(/[\\/]/).pop());
    });

    $('#btnLmcRodar').addEventListener('click', async () => {
      if (!FISCAL.lmcSemPath || !FISCAL.lmcComPath) return;
      overlay(true, 'Trocando o bloco de LMC (1300‑1390)…');
      const res = await window.fiscocont.fiscal.substituirLmc(FISCAL.lmcSemPath, FISCAL.lmcComPath);
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      const r = res.resumo || {};
      const box = $('#lmcResumo');
      box.hidden = false;
      box.innerHTML = `
        <div class="card" style="border-left:4px solid #e23d4c;margin-bottom:16px">
          <h3 style="margin:0 0 12px">LMC substituído</h3>
          <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:12px;font-size:13px">
            <div><b style="font-size:20px;color:#e23d4c">${r.registros_removidos ?? 0}</b><br>registros removidos (Domínio)</div>
            <div><b style="font-size:20px;color:#0ea472">${r.registros_incluidos ?? 0}</b><br>registros incluídos (cliente)</div>
          </div>
          <div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap">
            <button class="act inv-export" id="btnLmcVerDashboard" style="background:#1f2a5a;color:#fff;border-color:transparent">Ver dashboard animado</button>
            <button class="act inv-export" id="btnLmcHtml">Exportar HTML</button>
            <button class="act inv-export" id="btnLmcPdf">Exportar PDF</button>
            <button class="act inv-export" id="btnLmcBaixar" style="background:#0ea472;color:#fff;border-color:transparent">Baixar SPED corrigido</button>
          </div>
        </div>`;
      $('#btnLmcVerDashboard').addEventListener('click', async () => {
        overlay(true, 'Montando o dashboard…');
        const resD = await window.fiscocont.fiscal.lmcDashboard(FISCAL.lmcSemPath, FISCAL.lmcComPath);
        overlay(false);
        if (resD.error) { toast(resD.error, true); return; }
        const fr = $('#lmcFrame');
        fr.srcdoc = resD.html;
        fr.hidden = false; $('#lmcEmpty').hidden = true;
      });
      $('#btnLmcHtml').addEventListener('click', () => exportFiscal('lmc', 'html'));
      $('#btnLmcPdf').addEventListener('click', () => exportFiscal('lmc', 'pdf'));
      $('#btnLmcBaixar').addEventListener('click', async () => {
        const res3 = await window.fiscocont.fiscal.baixarSpedLmc();
        if (res3.canceled) return;
        if (res3.error) { toast(res3.error, true); return; }
        toast('SPED com LMC substituído salvo.');
        window.fiscocont.openPath(res3.path);
      });
      toast('LMC substituído — confira o resumo.');
    });
  }

  // ---- Documentos de entrada ----
  const bDocs = $('#btnDocsSped');
  if (bDocs) {
    bDocs.addEventListener('click', async () => {
      const pick = await pickOrReuseSped();
      if (pick.canceled) return;
      overlay(true, 'Lendo o SPED e montando a relação de documentos…');
      const res = await window.fiscocont.fiscal.documentos(pick.path);
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      await applySpedToAllModules(pick.path);
      const fr = $('#docsFrame');
      fr.srcdoc = res.html;
      fr.hidden = false; $('#docsEmpty').hidden = true;
      $('#btnDocsHtml').disabled = false; $('#btnDocsPdf').disabled = false;
      toast('Documentos listados: ' + (res.empresa || ''));
    });
    $('#btnDocsHtml').addEventListener('click', () => exportFiscal('documentos', 'html'));
    $('#btnDocsPdf').addEventListener('click', () => exportFiscal('documentos', 'pdf'));
  }

  // ---- Conferência de ICMS do Crédito (XML × SPED), dentro de Documentos de Entrada ----
  const bIcmsCredXmls = $('#btnIcmsCredXmls');
  if (bIcmsCredXmls) {
    bIcmsCredXmls.addEventListener('click', async () => {
      const spedPath = FISCAL.docsSped || FISCAL.spedAtual;
      if (!spedPath) { toast('Importe o SPED primeiro (Dashboard ou o botão acima).', true); return; }
      const pick = await window.fiscocont.fiscal.pickXmlsFolder();
      if (pick.canceled || !pick.path) return;
      FISCAL.icmsCredXmls = pick.path;
      overlay(true, 'Comparando o ICMS do crédito (XML × SPED)…');
      const res = await window.fiscocont.fiscal.icmsCredito(spedPath, pick.path);
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      const fr = $('#icmsCredFrame');
      fr.srcdoc = res.html;
      fr.hidden = false; $('#icmsCredEmpty').hidden = true;
      $('#btnIcmsCredHtml').disabled = false; $('#btnIcmsCredPdf').disabled = false;
      const r = res.resumo || {};
      toast(`ICMS do crédito: ${r.divergentes ?? 0} divergente(s), ${r.corretas ?? 0} confere(m)`);
    });
    $('#btnIcmsCredHtml').addEventListener('click', () => exportFiscal('icmsCredito', 'html'));
    $('#btnIcmsCredPdf').addEventListener('click', () => exportFiscal('icmsCredito', 'pdf'));

    // O botão "PDF" de cada linha do relatório vive dentro do iframe (srcdoc)
    // da Conferência de ICMS do Crédito — não tem como ele chamar a API do
    // Electron direto, então avisa aqui por postMessage (mesma técnica usada
    // por qualquer iframe pra falar com a janela que o carregou).
    window.addEventListener('message', async (ev) => {
      if (!ev.data || ev.data.acao !== 'gerarDanfe') return;
      if (!FISCAL.icmsCredXmls) { toast('Não sei mais qual .zip foi importado — importe de novo.', true); return; }
      const res = await window.fiscocont.fiscal.gerarDanfe(FISCAL.icmsCredXmls, ev.data.chave);
      if (res.canceled) return;
      if (res.error) { toast(res.error, true); return; }
      toast('DANFE gerado.');
      window.fiscocont.openPath(res.path);
    });
  }
}

async function exportFiscal(kind, fmt, cliente = false) {
  const payload = kind === 'dashboard'
    ? { kind, spedPath: FISCAL.spedPath }
    : kind === 'documentos'
    ? { kind, spedPath: FISCAL.docsSped }
    : kind === 'confSaidas'
    ? { kind, spedPath: FISCAL.confsSped, xmlsPath: FISCAL.confsXmls }
    : kind === 'desoneracao'
    ? { kind, xmlsPath: FISCAL.desonXmls }
    : kind === 'frete'
    ? { kind, spedPath: FISCAL.freteSped, xmlsPath: FISCAL.freteXmls }
    : kind === 'classificacao'
    ? { kind, spedPath: FISCAL.auditSped }
    : kind === 'pgdas'
    ? { kind, pgdasPath: FISCAL.pgdasPath }
    : kind === 'corretor'
    ? { kind, spedPath: FISCAL.corrSpedPath }
    : kind === 'lmc'
    ? { kind, spedPath: FISCAL.lmcSemPath, comLmcPath: FISCAL.lmcComPath }
    : kind === 'icmsCredito'
    ? { kind, spedPath: FISCAL.docsSped, xmlsPath: FISCAL.icmsCredXmls }
    : { kind, spedPath: FISCAL.confSped, xmlsPath: FISCAL.confXmls };
  if (cliente) payload.cliente = true;
  const faltaDado = kind === 'desoneracao' ? !payload.xmlsPath : kind === 'pgdas' ? !payload.pgdasPath
    : kind === 'lmc' ? (!payload.spedPath || !payload.comLmcPath)
    : kind === 'icmsCredito' ? (!payload.spedPath || !payload.xmlsPath) : !payload.spedPath;
  if (faltaDado) { toast('Importe os dados antes de exportar.', true); return; }
  overlay(true, cliente ? 'Gerando relatório para o cliente…' : 'Gerando ' + fmt.toUpperCase() + '…');
  const res = await window.fiscocont.fiscal.export(fmt, payload);
  overlay(false);
  if (res.canceled) return;
  if (res.error) { toast(res.error, true); return; }
  toast(cliente ? 'Relatório para o cliente salvo.' : fmt.toUpperCase() + ' salvo.');
  window.fiscocont.openPath(res.path);
}

let NOTAS_FALTANTES_ATUAIS = [];

function bindNotasFaltantes() {
  const btnAbrir = $('#btnConfNotasFaltantes');
  const modal = $('#modalNotasFaltantes');
  if (!btnAbrir) return;

  btnAbrir.addEventListener('click', async () => {
    overlay(true, 'Preparando notas faltantes…');
    const res = await window.fiscocont.fiscal.prepararInclusao(FISCAL.confSped, FISCAL.confXmls);
    overlay(false);
    if (res.error) { toast(res.error, true); return; }
    NOTAS_FALTANTES_ATUAIS = res.notas || [];
    renderModalNotasFaltantes();
    modal.hidden = false;
  });

  $('#btnFecharModalNotas').addEventListener('click', () => { modal.hidden = true; });

  $('#btnIncluirNotasSelecionadas').addEventListener('click', async () => {
    const linhas = $$('#tabelaNotasFaltantes tr[data-idx]');
    const selecionadas = [];
    linhas.forEach((tr) => {
      const idx = Number(tr.dataset.idx);
      const chk = tr.querySelector('.sel-nota');
      if (!chk || !chk.checked) return;
      const nota = NOTAS_FALTANTES_ATUAIS[idx];
      const itensEditados = nota.itens.map((it, i) => {
        const cfopInput = $(`.edit-cfop[data-nota-idx="${idx}"][data-item="${i}"]`);
        const cstInput = $(`.edit-cst[data-nota-idx="${idx}"][data-item="${i}"]`);
        return {
          cfop_entrada: cfopInput ? cfopInput.value.trim() : it.cfop_entrada,
          cst_icms: cstInput ? cstInput.value.trim() : it.cst_icms,
          cod_nat: it.cod_nat,
        };
      });
      selecionadas.push({ caminho: nota.caminho, itens: itensEditados });
    });
    if (!selecionadas.length) { toast('Selecione ao menos uma nota.', true); return; }
    overlay(true, 'Incluindo notas no SPED…');
    const r = await window.fiscocont.fiscal.incluirNotas(FISCAL.confSped, selecionadas, 'sped-com-notas');
    overlay(false);
    if (r.canceled) return;
    if (r.error) { toast(r.error, true); return; }
    modal.hidden = true;
    toast(`${r.resumo.notas_incluidas} nota(s) incluída(s) no SPED.`);
    window.fiscocont.openPath(r.path);
  });
}

function renderModalNotasFaltantes() {
  const tbody = $('#tabelaNotasFaltantes');
  const qtdPronta = NOTAS_FALTANTES_ATUAIS.filter((n) => n.pronta).length;
  $('#msgNotasFaltantes').textContent = `${qtdPronta} pronta(s) · ${NOTAS_FALTANTES_ATUAIS.length - qtdPronta} precisam de revisão`;
  tbody.innerHTML = NOTAS_FALTANTES_ATUAIS.map((n, idx) => {
    const valorTxt = `R$ ${(n.valor || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;
    const statusBadge = n.pronta
      ? '<span style="font-size:10.5px;font-weight:700;padding:4px 9px;border-radius:999px;background:#e6f7f0;color:#0ea472">✓ Pronta</span>'
      : `<span style="font-size:10.5px;font-weight:700;padding:4px 9px;border-radius:999px;background:#fdf0e3;color:#c07a10">⚠ ${n.cod_part ? 'Revisar CFOP/CST' : 'Fornecedor não cadastrado'}</span>`;
    let linhaDetalhe = '';
    if (!n.pronta) {
      const itensRevisar = n.itens.map((it, i) => `
        <div style="display:flex;gap:8px;align-items:center;padding:4px 0;font-size:11px;color:var(--ink2)">
          <span style="flex:1">${_esc(it.descricao || '')}</span>
          <input class="edit-cfop" data-nota-idx="${idx}" data-item="${i}" value="${_esc(it.cfop_entrada || '')}" placeholder="CFOP" style="width:60px;font-size:11px;border:1px solid #f0c078;border-radius:6px;padding:4px 6px">
          <input class="edit-cst" data-nota-idx="${idx}" data-item="${i}" value="${_esc(it.cst_icms || '')}" placeholder="CST" style="width:50px;font-size:11px;border:1px solid #f0c078;border-radius:6px;padding:4px 6px">
        </div>`).join('');
      linhaDetalhe = `<tr><td></td><td colspan="4" style="padding:0 10px 10px;border-top:none">${itensRevisar}</td></tr>`;
    }
    return `<tr data-idx="${idx}">
      <td style="padding:10px;border-top:1px solid #f3f4f9"><input type="checkbox" class="sel-nota" ${n.cod_part ? 'checked' : ''}></td>
      <td style="padding:10px;border-top:1px solid #f3f4f9;font-size:12px">NF-e ${_esc(n.nnf || '')}</td>
      <td style="padding:10px;border-top:1px solid #f3f4f9;font-size:12px">${_esc(n.fornecedor || '')}</td>
      <td style="padding:10px;border-top:1px solid #f3f4f9;font-size:12px;text-align:right;font-weight:700">${valorTxt}</td>
      <td style="padding:10px;border-top:1px solid #f3f4f9">${statusBadge}</td>
    </tr>${linhaDetalhe}`;
  }).join('');
}

// ------------------------------------------------------------------ ações
function toast(msg, err = false) {
  const t = $('#toast'); t.textContent = msg; t.classList.toggle('err', err); t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 4200);
}
function overlay(on, txt) { $('#ovTxt').textContent = txt || 'Processando…'; $('#overlay').hidden = !on; }

// Modal genérico "HTML animado × PDF" — usado no "Gerar para o Cliente".
// Devolve uma Promise com 'html', 'pdf', ou null se cancelado.
function perguntarFormato(titulo, subtitulo) {
  return new Promise((resolve) => {
    const ov = document.createElement('div');
    ov.className = 'fmt-overlay';
    ov.innerHTML = `
      <div class="fmt-modal">
        <h3>${titulo}</h3>
        <p>${subtitulo || 'Como você quer gerar esse relatório?'}</p>
        <div class="fmt-opts">
          <button class="fmt-opt" data-fmt="html">
            <span class="ic">▶</span>
            <span><b>HTML</b><span>Abre no navegador, com gráficos interativos</span></span>
          </button>
          <button class="fmt-opt" data-fmt="pdf">
            <span class="ic">▤</span>
            <span><b>PDF</b><span>Documento estático, pronto pra imprimir/anexar</span></span>
          </button>
        </div>
        <button class="fmt-cancel">Cancelar</button>
      </div>`;
    document.body.appendChild(ov);
    const fechar = (valor) => { ov.remove(); resolve(valor); };
    ov.querySelectorAll('.fmt-opt').forEach((b) => b.addEventListener('click', () => fechar(b.dataset.fmt)));
    ov.querySelector('.fmt-cancel').addEventListener('click', () => fechar(null));
    ov.addEventListener('click', (e) => { if (e.target === ov) fechar(null); });
  });
}

function applyData(res) {
  DATA = res.data;
  const md = DATA.empresa;
  $('#topInfo').hidden = false;
  $('#empNome').textContent = md.empresa || '—';
  $('#chCnpj').textContent = 'CNPJ ' + (md.cnpj || '—');
  $('#chJunta').textContent = 'Junta ' + (md.insc_junta || '—');
  $('#chPer').textContent = md.periodo || '—';
  $('#topFile').textContent = res.arquivo || '';
  $('#btnExport').disabled = false;
  const inv = DATA.invertidas.length;
  const badge = $('#invBadge'); badge.hidden = inv === 0; badge.textContent = inv;

  renderOverview(DATA); renderDRE(DATA); renderBalancete(DATA); renderInvertidas(DATA);
  IND_LOADED = false;
  const indFr = $('#indFrame'); if (indFr) { indFr.hidden = true; indFr.srcdoc = ''; }
  const indEm = $('#indEmpty'); if (indEm) indEm.hidden = false;
  switchView('overview');
}

let IND_LOADED = false;
async function loadIndicadores() {
  if (IND_LOADED) return;
  const fr = $('#indFrame'), em = $('#indEmpty');
  if (!fr || !window.fiscocont.indicadoresHtml) return;
  const res = await window.fiscocont.indicadoresHtml();
  if (res && res.ok) {
    fr.srcdoc = res.html; fr.hidden = false; if (em) em.hidden = true;
    IND_LOADED = true;
  } else if (res && res.error) {
    toast(res.error, true);
  }
}

function showImportError(msg) {
  $('#empty').hidden = false;
  $$('.view').forEach((v) => (v.hidden = true));
  const box = $('#importErr');
  if (box) { box.textContent = msg; box.hidden = false; }
}

async function processPath(pdfPath) {
  const box = $('#importErr'); if (box) box.hidden = true;
  overlay(true, 'Analisando o balancete…');
  const hint = setTimeout(() => overlay(true, 'Ainda analisando… a 1ª execução pode demorar (antivírus/descompactação).'), 7000);
  try {
    const res = await window.fiscocont.processPdf(pdfPath);
    clearTimeout(hint);
    overlay(false);
    if (res.error) { showImportError(res.error); toast('Falha ao ler o PDF', true); return; }
    applyData(res);
    toast('Balancete importado: ' + (res.data.empresa.empresa || res.arquivo));
  } catch (e) {
    clearTimeout(hint); overlay(false);
    showImportError(String(e && e.message ? e.message : e));
  }
}

async function doImport() {
  try {
    const pick = await window.fiscocont.pickPdf();      // sem overlay durante a escolha
    if (pick.canceled || !pick.path) return;
    await processPath(pick.path);
  } catch (e) {
    overlay(false);
    showImportError(String(e && e.message ? e.message : e));
  }
}

function bindDropzone() {
  const dz = $('#dropZone');
  if (!dz) return;
  const stop = (e) => { e.preventDefault(); e.stopPropagation(); };
  ['dragenter', 'dragover'].forEach((ev) => dz.addEventListener(ev, (e) => { stop(e); dz.classList.add('dragging'); }));
  ['dragleave', 'dragend'].forEach((ev) => dz.addEventListener(ev, (e) => { stop(e); dz.classList.remove('dragging'); }));
  dz.addEventListener('drop', (e) => {
    stop(e); dz.classList.remove('dragging');
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (!f) return;
    if (!/\.pdf$/i.test(f.name)) { showImportError('Solte um arquivo PDF do balancete (extensão .pdf).'); return; }
    const p = f.path;
    if (p) processPath(p);
    else showImportError('Não consegui obter o caminho do arquivo. Use o botão "Selecionar balancete".');
  });
  // evita que soltar o arquivo fora da area troque a tela pelo PDF
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => e.preventDefault());
}

async function doExport() {
  if (!DATA) return;
  const nome = (DATA.empresa.empresa || 'analise-balancete').replace(/[\\/:*?"<>|]+/g, ' ').trim().slice(0, 60);
  try {
    overlay(true, 'Gerando PDF do cliente…');
    const res = await window.fiscocont.exportPdf(nome);
    overlay(false);
    if (res.canceled) return;
    if (res.error) { toast(res.error, true); return; }
    toast('PDF salvo com sucesso.');
    window.fiscocont.openPath(res.path);
  } catch (e) { overlay(false); toast('Falha ao exportar: ' + e.message, true); }
}

// ------------------------------------------------------------------ janela
function bindWindow() {
  const min = $('#winMin'), max = $('#winMax'), close = $('#winClose'), drag = $('.tb-drag');
  if (min) min.addEventListener('click', () => window.fiscocont.win.minimize());
  if (max) max.addEventListener('click', () => window.fiscocont.win.maximize());
  if (close) close.addEventListener('click', () => window.fiscocont.win.close());
  if (drag) drag.addEventListener('dblclick', () => window.fiscocont.win.maximize());
  const setMaxIcon = (isMax) => {
    const a = $('.ic-max'), b = $('.ic-restore');
    if (a) a.hidden = isMax; if (b) b.hidden = !isMax;
    if (max) max.title = isMax ? 'Restaurar' : 'Maximizar';
  };
  window.fiscocont.win.onMaximize(setMaxIcon);
  window.fiscocont.win.isMaximized().then(setMaxIcon).catch(() => {});
}

async function startupCheck() {
  try {
    const d = await window.fiscocont.diag();
    if (d.packaged && !d.coreExists) {
      showImportError(
        'Núcleo de leitura não encontrado no aplicativo instalado:\n' + d.cmd +
        '\n\nO instalador foi gerado sem o balancete_core.exe (a etapa do PyInstaller no build.bat não concluiu). ' +
        'Rode o build.bat novamente até o fim e reinstale.'
      );
    }
  } catch (_) {}
}

// ------------------------------------------------------------------ init
let ROLE = null;

function applyRole(role) {
  ROLE = role;
  const hideFiscal = role === 'contabil';
  const hideContabil = role === 'fiscal';
  const hideAdmin = role !== 'admin';
  $$('[data-group="fiscal"]').forEach((el) => el.classList.toggle('role-hidden', hideFiscal));
  $$('[data-group="contabil"]').forEach((el) => el.classList.toggle('role-hidden', hideContabil));
  $$('[data-group="admin-only"]').forEach((el) => el.classList.toggle('role-hidden', hideAdmin));
  // Conciliação de Fornecedores: liberada só pro Admin por enquanto (ainda
  // testando com o Rafael) — os outros papéis veem o item, mas travado com
  // o selo "EM BREVE" em vez de sumir, diferente do admin-only comum.
  const navConc = $('#navConciliacao');
  if (navConc) {
    const travado = role !== 'admin';
    navConc.classList.toggle('locked-em-breve', travado);
    $('#badgeEmBreveConc').hidden = !travado;
  }
  const activeBtn = document.querySelector('.nav-item.active');
  if (!activeBtn || activeBtn.classList.contains('role-hidden')) {
    const firstVisible = document.querySelector('.nav-item:not(.role-hidden)');
    if (firstVisible) {
      $$('.nav-item').forEach((b) => b.classList.remove('active'));
      firstVisible.classList.add('active');
      switchView(firstVisible.dataset.view);
    }
  }
}

function bindLogin() {
  const gate = $('#loginGate');
  const form = $('#loginForm');
  const pass = $('#loginPass');
  const err = $('#loginErr');
  const card = document.querySelector('.login-card');
  if (!form) return;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const res = await window.fiscocont.login(pass.value);
    pass.value = '';
    if (res && res.ok) {
      err.hidden = true;
      gate.style.display = 'none';
      applyRole(res.role);
      verificarNovidades();
    } else {
      err.hidden = false;
      card.classList.remove('login-shake'); void card.offsetWidth; card.classList.add('login-shake');
      pass.focus();
    }
  });
  const logoutLink = $('#logoutLink');
  if (logoutLink) logoutLink.addEventListener('click', (e) => {
    e.preventDefault();
    ROLE = null;
    err.hidden = true;
    gate.style.display = 'flex';
    pass.value = '';
    pass.focus();
  });
}

// ------------------------------------------------------------- novidades da versão
// Busca (via main process) o texto da release atual no GitHub — o mesmo
// texto escrito na hora de publicar cada versão — e mostra num modal só
// quando a versão mudou desde a última vez que a pessoa viu.
function _notasParaHtml(notas) {
  const itens = notas.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => l.replace(/^[-*]\s*/, ''));
  return '<ul style="margin:0;padding-left:20px">' + itens.map((i) => `<li style="margin-bottom:8px">${_esc(i)}</li>`).join('') + '</ul>';
}
function mostrarNovidades(info) {
  const modal = $('#modalNovidades');
  if (!modal) return;
  $('#novidadesVersao').textContent = `Novidades da versão ${info.versao}`;
  $('#novidadesCorpo').innerHTML = _notasParaHtml(info.notas);
  modal.hidden = false;
  $('#btnFecharNovidades').onclick = () => {
    modal.hidden = true;
    window.fiscocont.changelog.marcarVisto(info.versao);
  };
}
async function verificarNovidades() {
  if (!window.fiscocont.changelog) return;
  try {
    const info = await window.fiscocont.changelog.check();
    if (info && info.notas) mostrarNovidades(info);
  } catch (_) { /* silencioso: sem internet ou GitHub fora do ar não deve atrapalhar o login */ }
}

// ------------------------------------------------------------- bloqueio remoto (licença)
function showLicenseBlock(res) {
  const loginCard = document.querySelector('.login-card');
  const licCard = $('#licenseCard');
  const gate = $('#loginGate');
  if (loginCard) loginCard.hidden = true;
  if (licCard) licCard.hidden = false;
  if (gate) gate.style.display = 'flex';
  const title = $('#licenseTitle'), sub = $('#licenseSub'), hint = $('#licenseHint'), codeEl = $('#licenseCode');
  if (codeEl) codeEl.textContent = res.codigo || '----';
  if (res.status === 'pendente') {
    if (title) title.textContent = 'Aguardando liberação';
    if (sub) sub.textContent = 'Este computador ainda não foi aprovado pela Liddera.';
    if (hint) hint.textContent = 'Envie o código acima para liberar o acesso.';
  } else if (res.status === 'bloqueado') {
    if (title) title.textContent = 'Acesso bloqueado';
    if (sub) sub.textContent = 'Este computador foi bloqueado pelo administrador.';
    if (hint) hint.textContent = 'Entre em contato com a Liddera para mais informações.';
  } else {
    if (title) title.textContent = 'Sem conexão';
    if (sub) sub.textContent = 'Não foi possível confirmar a liberação deste computador agora.';
    if (hint) hint.textContent = 'Verifique a internet e tente novamente.';
  }
}
function hideLicenseBlock() {
  const loginCard = document.querySelector('.login-card');
  const licCard = $('#licenseCard');
  const gate = $('#loginGate');
  if (licCard) licCard.hidden = true;
  if (loginCard) loginCard.hidden = false;
  // Achado real: essa função nunca escondia o #loginGate, só trocava qual
  // card aparecia dentro dele — então depois de bloquear e reativar, o app
  // ficava preso pedindo senha de novo mesmo já reativado. Se já havia uma
  // sessão ativa (ROLE definido) quando a liberação chegou, o usuário só
  // estava interrompido, não deslogado — some com o gate inteiro e devolve
  // ele pra tela onde estava, sem pedir senha de novo.
  if (gate && ROLE) gate.style.display = 'none';
}
async function checkLicenseGate() {
  if (!window.fiscocont.license) return true;
  let res;
  try { res = await window.fiscocont.license.check(); } catch (_) { res = { status: 'offline', codigo: '' }; }
  if (!res || res.configurado === false || res.status === 'ativo') {
    hideLicenseBlock();
    return true;
  }
  showLicenseBlock(res);
  return false;
}

// Indicador de conexão do bloqueio em tempo real — pra dar pra ver, no
// próprio painel de Licenças, se o listener realmente conectou ou se falhou
// silenciosamente (achado real: antes não tinha como saber isso sem abrir o
// DevTools).
function renderLicRealtimeStatus(status) {
  const el = $('#licRealtimeStatus');
  if (!el) return;
  if (status && status.ok) {
    el.textContent = '● Bloqueio em tempo real: conectado';
    el.style.color = '#0ea472';
  } else if (status) {
    el.textContent = `● Bloqueio em tempo real: desconectado${status.motivo ? ` (${status.motivo})` : ''} — a checagem a cada 15 min continua funcionando normalmente`;
    el.style.color = '#e23d4c';
  } else {
    el.textContent = '';
  }
}

// ------------------------------------------------------------- painel admin: licenças
async function loadLicensePanel() {
  if (window.fiscocont.license && window.fiscocont.license.getRealtimeStatus) {
    window.fiscocont.license.getRealtimeStatus().then(renderLicRealtimeStatus).catch(() => {});
  }
  const box = $('#licTableBox'), warnBox = $('#licWarnBox');
  if (!box) return;
  box.innerHTML = '<div class="lic-empty">Carregando…</div>';
  if (warnBox) warnBox.innerHTML = '';
  const res = await window.fiscocont.license.listAll();
  if (res.error) {
    if (warnBox) warnBox.innerHTML = `<div class="lic-warn">Não consegui carregar: ${_esc(res.error)}. Configure a nuvem (☁, no rodapé) nesta máquina para gerenciar licenças por aqui — ou use o Firebase Console.</div>`;
    box.innerHTML = '';
    return;
  }
  const itens = res.itens || [];
  if (!itens.length) { box.innerHTML = '<div class="lic-empty">Nenhuma máquina registrada ainda.</div>'; return; }
  const fmtDt = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  };
  let rows = '';
  for (const it of itens) {
    rows += `<tr>
      <td class="code">${_esc(it.codigo)}</td>
      <td>${_esc(it.hostname || '—')}<br><span style="color:var(--ink2);font-size:11px">${_esc(it.plataforma || '')}</span></td>
      <td><span class="lic-badge ${_esc(it.status)}">${_esc(it.status)}</span></td>
      <td>${fmtDt(it.primeiroAcesso)}</td>
      <td>${fmtDt(it.ultimoAcesso)}</td>
      <td class="lic-actions">
        <button class="on" data-code="${_esc(it.codigo)}" data-status="ativo">Ativar</button>
        <button class="off" data-code="${_esc(it.codigo)}" data-status="bloqueado">Bloquear</button>
      </td>
    </tr>`;
  }
  box.innerHTML = `<table class="lic-table"><thead><tr><th>Código</th><th>Computador</th><th>Status</th><th>1º acesso</th><th>Último acesso</th><th>Ação</th></tr></thead><tbody>${rows}</tbody></table>`;
  box.querySelectorAll('button[data-code]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      const r = await window.fiscocont.license.setStatus(btn.dataset.code, btn.dataset.status);
      if (r.error) { toast(r.error, true); btn.disabled = false; return; }
      toast('Licença atualizada.');
      loadLicensePanel();
    });
  });
}

// ---- Histórico de balancetes (nuvem) ----
let HIST_EMPRESAS_CARREGADAS = false;
async function loadHistoricoEmpresas(force) {
  const sel = $('#histEmpresaSelect');
  if (!sel) return;
  if (HIST_EMPRESAS_CARREGADAS && !force) return;
  sel.innerHTML = '<option value="">Carregando…</option>';
  const res = await window.fiscocont.cloud.listEmpresas();
  if (res.error) {
    sel.innerHTML = '<option value="">Selecione a empresa...</option>';
    toast('Não consegui carregar a lista de empresas: ' + res.error, true);
    return;
  }
  const itens = res.itens || [];
  sel.innerHTML = '<option value="">Selecione a empresa...</option>' +
    itens.map((e) => `<option value="${_esc(e.cnpj)}">${_esc(e.empresa)}</option>`).join('');
  HIST_EMPRESAS_CARREGADAS = true;
}

function _fmtDtHist(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

async function loadHistoricoDaEmpresa(cnpj) {
  const box = $('#histListBox');
  const empty = $('#histEmpty');
  if (!box) return;
  if (!cnpj) { box.innerHTML = ''; if (empty) empty.hidden = false; return; }
  if (empty) empty.hidden = true;
  box.innerHTML = '<div class="lic-empty">Carregando…</div>';
  const res = await window.fiscocont.cloud.listHistorico(cnpj);
  if (res.error) { box.innerHTML = ''; toast(res.error, true); return; }
  const itens = res.itens || [];
  if (!itens.length) { box.innerHTML = '<div class="lic-empty">Nenhum balancete salvo pra essa empresa ainda.</div>'; return; }
  const rows = itens.map((h) => `
    <tr>
      <td>${_esc(h.periodo)}</td>
      <td style="color:${h.resultadoTipo === 'lucro' ? 'var(--pos)' : 'var(--neg)'};font-weight:700">
        R$ ${(h.resultadoValor || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </td>
      <td>${(h.margemLiquida || 0).toFixed(1)}%</td>
      <td>${_fmtDtHist(h.atualizadoEm)}</td>
      <td class="lic-actions">
        <button class="on hist-open" data-cnpj="${_esc(cnpj)}" data-id="${_esc(h.id)}">Abrir</button>
        <button class="off hist-del" data-cnpj="${_esc(cnpj)}" data-id="${_esc(h.id)}" data-periodo="${_esc(h.periodo)}">Excluir</button>
      </td>
    </tr>`).join('');
  box.innerHTML = `<table class="lic-table"><thead><tr><th>Competência</th><th>Resultado</th><th>Margem líquida</th><th>Importado em</th><th>Ação</th></tr></thead><tbody>${rows}</tbody></table>`;
  box.querySelectorAll('.hist-open').forEach((btn) => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      overlay(true, 'Carregando balancete da nuvem…');
      const r = await window.fiscocont.cloud.getHistoricoItem(btn.dataset.cnpj, btn.dataset.id);
      overlay(false);
      btn.disabled = false;
      if (r.error) { toast(r.error, true); return; }
      applyData({ data: r.data, arquivo: 'Histórico · ' + ((r.data.empresa || {}).periodo || '') });
      toast('Balancete carregado: ' + ((r.data.empresa || {}).empresa || ''));
    });
  });
  box.querySelectorAll('.hist-del').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const ok = confirm(`Excluir o balancete de "${btn.dataset.periodo}" do histórico? Essa ação não pode ser desfeita.`);
      if (!ok) return;
      btn.disabled = true;
      overlay(true, 'Excluindo do histórico…');
      const r = await window.fiscocont.cloud.deleteHistoricoItem(btn.dataset.cnpj, btn.dataset.id);
      overlay(false);
      if (r.error) { toast(r.error, true); btn.disabled = false; return; }
      toast('Removido do histórico.');
      loadHistoricoDaEmpresa(btn.dataset.cnpj);
    });
  });
}

// Balão de notícias contábeis — não intrusivo: 1 por vez (fila se chegar
// outra enquanto uma está na tela), some sozinho em 10s, clique abre o
// link, "Desativar notícias" pra quem não quiser ver mais (por máquina).
// Conferência de EFD-Contribuições — seleciona o arquivo, manda pro núcleo
// Python processar e mostra o painel retornado no iframe.
function bindEfdContrib() {
  const btn = $('#btnEfdPick');
  if (!btn) return;
  let ultimoHtml = null, ultimaEmpresa = '';
  btn.addEventListener('click', async () => {
    const pick = await window.fiscocont.fiscal.pickEfdContrib();
    if (pick.canceled) return;
    $('#efdArquivoNome').textContent = pick.path.split(/[\\/]/).pop();
    overlay(true, 'Lendo a EFD-Contribuições…');
    const res = await window.fiscocont.fiscal.efdContrib(pick.path);
    overlay(false);
    if (res.error) { toast(res.error, true); return; }
    $('#efdVazio').hidden = true;
    const frame = $('#efdFrame');
    frame.hidden = false;
    frame.srcdoc = res.painelHtml;
    ultimoHtml = res.painelHtml;
    ultimaEmpresa = res.resumo?.empresa?.nome || '';
    $('#btnEfdExportar').disabled = false;
  });
  $('#btnEfdExportar').addEventListener('click', async () => {
    if (!ultimoHtml) return;
    const res = await window.fiscocont.fiscal.nfseExportarHtml(ultimoHtml, 'efd-contrib', ultimaEmpresa);
    if (res.canceled) return;
    if (res.error) { toast(res.error, true); return; }
    toast('Conferência exportada.');
    window.fiscocont.openPath(res.path);
  });
}

function bindNewsToast() {
  const elBalao = $('#newsToast');
  if (!elBalao || !window.fiscocont.news) return;
  const cat = $('#newsCat'), titulo = $('#newsTitle'), barra = $('#newsBar');
  const fila = [];
  let mostrando = false, timerSumir = null;

  const CLASSE_CAT = { 'Tributário': 'trib', 'Contábil': 'cont', 'Empresarial': 'emp' };

  function esconder() {
    clearTimeout(timerSumir);
    elBalao.hidden = true;
    barra.classList.remove('correndo');
    mostrando = false;
    if (fila.length) setTimeout(mostrarProxima, 400);
  }

  function mostrarProxima() {
    if (mostrando || !fila.length) return;
    const item = fila.shift();
    mostrando = true;
    cat.textContent = item.categoria;
    cat.className = 'nt-cat ' + (CLASSE_CAT[item.categoria] || 'trib');
    titulo.textContent = item.titulo;
    elBalao.dataset.link = item.link;
    elBalao.hidden = false;
    barra.classList.remove('correndo');
    void barra.offsetWidth; // força reiniciar a animação a cada notícia
    requestAnimationFrame(() => barra.classList.add('correndo'));
    timerSumir = setTimeout(esconder, 10000);
  }

  window.fiscocont.news.onNovo((item) => { fila.push(item); mostrarProxima(); });
  // avisa o main process que já pode começar a checar — sem isso, ele usava
  // um tempo fixo chutado (achado real, 30/09): numa rede mais lenta, o
  // aviso de licença podia demorar mais que esse tempo, e a notícia era
  // "enviada" antes da tela estar ouvindo, se perdendo de vez.
  window.fiscocont.news.avisarPronto();

  elBalao.addEventListener('click', (ev) => {
    if (ev.target.id === 'newsClose' || ev.target.id === 'newsDesativar') return;
    if (elBalao.dataset.link) window.fiscocont.news.abrirLink(elBalao.dataset.link);
    esconder();
  });
  $('#newsClose').addEventListener('click', (ev) => { ev.stopPropagation(); esconder(); });
  $('#newsDesativar').addEventListener('click', async (ev) => {
    ev.stopPropagation();
    await window.fiscocont.news.desativar();
    fila.length = 0;
    esconder();
    atualizarLinkRodape();
    elBalao.hidden = false;
    cat.textContent = ''; cat.className = 'nt-cat';
    barra.classList.remove('correndo');
    titulo.textContent = 'Notícias desativadas — pode reativar no rodapé do menu, a qualquer momento.';
    setTimeout(() => { elBalao.hidden = true; }, 5000);
  });

  // Link no rodapé do menu: sempre visível, pra reativar sem precisar
  // esperar aparecer outra notícia.
  const linkRodape = $('#newsToggleLink');
  async function atualizarLinkRodape() {
    if (!linkRodape) return;
    const status = await window.fiscocont.news.status();
    linkRodape.textContent = status === 'desativado' ? '📰 notícias: desativadas (reativar)' : '📰 notícias: ativas (desativar)';
  }
  if (linkRodape) {
    linkRodape.addEventListener('click', async () => {
      const status = await window.fiscocont.news.status();
      if (status === 'desativado') await window.fiscocont.news.ativar();
      else await window.fiscocont.news.desativar();
      await atualizarLinkRodape();
    });
    atualizarLinkRodape();
  }
}

function bindChatIA() {
  const bubble = $('#iaBubble');
  const panel = $('#iaPanel');
  const body = $('#iaBody');
  const input = $('#iaInput');
  const send = $('#iaSend');
  if (!bubble || !panel) return;

  let historicoIA = [];
  let enviando = false;

  function abrir() { bubble.classList.add('hide'); panel.hidden = false; input.focus(); }
  function fechar() { panel.hidden = true; bubble.classList.remove('hide'); }
  function addBolha(texto, tipo) {
    const div = document.createElement('div');
    div.className = tipo === 'user' ? 'ia-user' : 'ia-bot';
    div.textContent = texto;
    body.appendChild(div);
    body.scrollTop = body.scrollHeight;
    return div;
  }

  async function enviar() {
    const texto = input.value.trim();
    if (!texto || enviando) return;
    input.value = '';
    addBolha(texto, 'user');
    const pensando = addBolha('Pesquisando na fonte oficial…', 'bot');
    pensando.classList.add('think');
    enviando = true;
    send.disabled = true;
    try {
      const res = await window.fiscocont.enviarMensagemIA(texto, historicoIA);
      pensando.remove();
      if (res.error) {
        addBolha('Não consegui responder: ' + res.error, 'bot');
      } else {
        addBolha(res.texto || '(sem resposta)', 'bot');
        historicoIA.push({ role: 'user', content: texto });
        historicoIA.push(res.resposta);
      }
    } catch (e) {
      pensando.remove();
      addBolha('Erro: ' + e.message, 'bot');
    } finally {
      enviando = false;
      send.disabled = false;
    }
  }

  bubble.addEventListener('click', abrir);
  $('#iaClose').addEventListener('click', fechar);
  send.addEventListener('click', enviar);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') enviar(); });
}

function bindHistorico() {
  const sel = $('#histEmpresaSelect');
  const btnRefresh = $('#btnHistRefresh');
  if (sel) sel.addEventListener('change', () => loadHistoricoDaEmpresa(sel.value));
  if (btnRefresh) btnRefresh.addEventListener('click', () => loadHistoricoEmpresas(true));
}

function bindLoteBalancetes() {
  const btn = $('#btnLotePick');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    const pick = await window.fiscocont.pickMultiplePdf();
    if (pick.canceled || !pick.paths || !pick.paths.length) return;
    $('#loteContagem').textContent = `Processando ${pick.paths.length} arquivo(s)…`;
    overlay(true, `Processando ${pick.paths.length} balancete(s)…`);
    const res = await window.fiscocont.processLote(pick.paths);
    overlay(false);
    if (res.error) { toast(res.error, true); $('#loteContagem').textContent = ''; return; }
    const fr = $('#loteFrame');
    fr.srcdoc = res.html;
    fr.hidden = false; $('#loteEmpty').hidden = true;
    $('#loteContagem').textContent = `${res.total} processado(s)${res.falhas ? ` · ${res.falhas} com erro` : ''}`;
    toast(res.falhas ? `Lote concluído com ${res.falhas} erro(s).` : 'Lote concluído sem erros.');
  });
}

let CONC_RESULTADO = null;
const CODIGO_FORNECEDOR_GENERICO = '506';

function bindConciliacao() {
  const btnPlano = $('#btnConcPlano');
  const btnExtrato = $('#btnConcExtrato');
  const btnExportar = $('#btnConcExportarTxt');
  const selectBanco = $('#concBancoSelect');
  if (!btnPlano) return;

  btnPlano.addEventListener('click', async () => {
    const r = await window.fiscocont.conciliacao.pickPlanoContas();
    if (r.canceled) return;
    if (r.error) { toast(r.error, true); return; }
    $('#concPlanoLabel').textContent = `${r.arquivo} (${r.total} fornecedores)`;
    toast(`Plano de contas importado: ${r.total} fornecedores encontrados.`);
  });

  btnExtrato.addEventListener('click', async () => {
    const banco = selectBanco.value;
    if (!banco) { toast('Selecione o banco antes.', true); return; }
    const pick = await window.fiscocont.conciliacao.pickExtrato();
    if (pick.canceled) return;
    overlay(true, 'Conciliando extrato…');
    const ano = new Date().getFullYear();
    const res = await window.fiscocont.conciliacao.conciliar(banco, pick.path, ano);
    overlay(false);
    if (res.error) { toast(res.error, true); return; }
    CONC_RESULTADO = res;
    renderConciliacao(res);
    btnExportar.disabled = false;
    toast(res.precisa_reforco_ia
      ? `Atenção: ${res.motivo_reforco_ia || 'esse extrato pode precisar de revisão manual.'}`
      : `${res.total_transacoes} transações lidas.`);
  });

  btnExportar.addEventListener('click', async () => {
    if (!CONC_RESULTADO) return;
    const pickTxt = await window.fiscocont.conciliacao.pickTxtOriginal();
    if (pickTxt.canceled) return;
    const mapa = {};
    CONC_RESULTADO.transacoes.forEach((t, i) => {
      mapa[i] = t.fornecedor_sugerido ? t.fornecedor_sugerido.codigo : CODIGO_FORNECEDOR_GENERICO;
    });
    overlay(true, 'Gerando TXT conciliado…');
    const r = await window.fiscocont.conciliacao.exportarTxt(pickTxt.path, mapa, `lancamento-${CONC_RESULTADO.banco}`);
    overlay(false);
    if (r.canceled) return;
    if (r.error) { toast(r.error, true); return; }
    toast('TXT conciliado salvo.');
    window.fiscocont.openPath(r.path);
  });
}

function renderConciliacao(res) {
  $('#concEmpty').hidden = true;
  $('#concResumo').hidden = false;
  $('#concTabela').hidden = false;
  const comFornecedor = res.transacoes.filter((t) => t.fornecedor_sugerido).length;
  const semFornecedor = res.total_transacoes - comFornecedor;
  $('#concQtdCasadas').textContent = comFornecedor;
  $('#concQtdRevisar').textContent = semFornecedor;
  $('#concBarra').style.width = res.total_transacoes ? `${Math.round(comFornecedor / res.total_transacoes * 100)}%` : '0%';

  const tbody = $('#concTabelaBody');
  tbody.innerHTML = res.transacoes.map((t) => {
    const valorCor = t.valor < 0 ? '#e23d4c' : '#0ea472';
    const valorTxt = t.valor == null ? '—' : `R$ ${Math.abs(t.valor).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;
    const forn = t.fornecedor_sugerido
      ? `<span style="display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;padding:5px 11px;border-radius:8px;background:#e6f7f0;color:#0ea472">✓ ${_esc(t.fornecedor_sugerido.nome)}</span>`
      : `<span style="display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;padding:5px 11px;border-radius:8px;background:#fdf0e3;color:#c07a10">⚠ Fornecedor Modelo (${CODIGO_FORNECEDOR_GENERICO}) — revisar</span>`;
    return `<tr>
      <td style="padding:10px 14px;border-top:1px solid #f3f4f9;font-size:12.5px">${_esc(t.data || '—')}</td>
      <td style="padding:10px 14px;border-top:1px solid #f3f4f9;font-size:12.5px;color:var(--ink2)">${_esc(t.descricao || '')}</td>
      <td style="padding:10px 14px;border-top:1px solid #f3f4f9;font-size:12.5px;text-align:right;font-weight:700;color:${valorCor}">${valorTxt}</td>
      <td style="padding:10px 14px;border-top:1px solid #f3f4f9">${forn}</td>
    </tr>`;
  }).join('');
}

// ------------------------------------------------------------- tema de cores
const _TEMAS = {
  padrao:    { side: '#141733', side2: '#1c2148', accent: '#4f46e5', accent2: '#7c3aed', bg: '#f4f6fb' },
  esmeralda: { side: '#0f2e1f', side2: '#153d29', accent: '#10b981', accent2: '#059669', bg: '#f2faf6' },
  grafite:   { side: '#1e2530', side2: '#28303d', accent: '#2563eb', accent2: '#1d4ed8', bg: '#f5f6f8' },
  vinho:     { side: '#2b0f18', side2: '#3a1420', accent: '#e8632b', accent2: '#d4551f', bg: '#faf4f2' },
  rosa:      { side: '#2e0f22', side2: '#3d1530', accent: '#db2777', accent2: '#be185d', bg: '#fdf2f8' },
};
function aplicarTema(nome) {
  const t = _TEMAS[nome] || _TEMAS.padrao;
  const root = document.documentElement.style;
  root.setProperty('--side', t.side);
  root.setProperty('--side2', t.side2);
  root.setProperty('--accent', t.accent);
  root.setProperty('--accent2', t.accent2);
  root.setProperty('--bg', t.bg);
  $$('.theme-dot').forEach((b) => { b.style.border = b.dataset.theme === nome ? '1.5px solid rgba(255,255,255,.7)' : '1.5px solid transparent'; });
}
async function iniciarTema() {
  let nome = 'padrao';
  if (window.fiscocont.tema) {
    try { nome = await window.fiscocont.tema.get(); } catch (_) {}
  }
  aplicarTema(nome);
  $$('.theme-dot').forEach((b) => {
    b.addEventListener('click', () => {
      aplicarTema(b.dataset.theme);
      if (window.fiscocont.tema) window.fiscocont.tema.set(b.dataset.theme);
    });
  });
}

function _esc(s) {
  const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML;
}

window.addEventListener('DOMContentLoaded', async () => {
  iniciarTema();

  // Selo "NOVO" do módulo Simples Nacional — some sozinho depois de 5 dias
  // do lançamento (data fixa, não depende de quando cada PC abre o app pela 1ª vez).
  (function () {
    const badge = $('#pgdasNewBadge');
    if (!badge) return;
    const expira = new Date('2026-09-11T23:59:59');
    if (new Date() <= expira) badge.hidden = false;
  })();

  // Selo "NOVO" do módulo Download de Documentos Fiscais — 7 dias a partir
  // do lançamento (25/09/2026), data fixa como o de cima.
  (function () {
    const badge = $('#downloadsNewBadge');
    if (!badge) return;
    const expira = new Date('2026-10-02T23:59:59');
    if (new Date() <= expira) badge.hidden = false;
  })();
  await checkLicenseGate();
  const retryBtn = $('#licenseRetry');
  if (retryBtn) retryBtn.addEventListener('click', () => checkLicenseGate());
  // Reação em tempo real: quando o Admin ativa/bloqueia esta máquina, o main
  // process escuta o Firestore e avisa na hora — não precisa esperar o polling.
  if (window.fiscocont.license && window.fiscocont.license.onChanged) {
    window.fiscocont.license.onChanged((data) => {
      if (!data) return;
      if (data.status === 'ativo') hideLicenseBlock();
      else showLicenseBlock(data);
    });
  }
  // Indicador de conexão do bloqueio em tempo real, pra dar pra ver, no
  // painel de Licenças, se o listener realmente conectou ou falhou.
  if (window.fiscocont.license && window.fiscocont.license.onRealtimeStatus) {
    window.fiscocont.license.onRealtimeStatus(renderLicRealtimeStatus);
  }
  // Consulta ativa também, pro caso do evento acima ter chegado ANTES desse
  // listener existir (corrida possível bem no início da abertura do app).
  if (window.fiscocont.license && window.fiscocont.license.getRealtimeStatus) {
    window.fiscocont.license.getRealtimeStatus().then(renderLicRealtimeStatus).catch(() => {});
  }
  setInterval(checkLicenseGate, 15 * 60 * 1000); // rede de segurança, caso o listener em tempo real caia sem avisar
  const licRefresh = $('#btnLicRefresh');
  if (licRefresh) licRefresh.addEventListener('click', loadLicensePanel);
  const adminCred = $('#btnAdminCred');
  if (adminCred) adminCred.addEventListener('click', async () => {
    const r = await window.fiscocont.cloud.setup();
    if (r && r.canceled) return;
    if (r && r.ok) { toast('Credencial administrativa configurada (' + (r.projectId || '') + '). Os botões Ativar/Bloquear já funcionam nesta máquina.'); loadLicensePanel(); }
    else if (r && r.error) { toast(r.error, true); }
  });

  if (window.fiscocont.updater) {
    window.fiscocont.updater.onAvailable((d) => toast('Baixando atualização v' + d.versao + '…'));
    window.fiscocont.updater.onReady((d) => {
      const bt = $('#updateBannerText'); if (bt) bt.textContent = `Nova versão v${d.versao} pronta para instalar.`;
      const b = $('#updateBanner'); if (b) b.hidden = false;
    });
  }
  const ubBtn = $('#updateBannerBtn');
  if (ubBtn) ubBtn.addEventListener('click', () => window.fiscocont.updater.installNow());
  const ubClose = $('#updateBannerClose');
  if (ubClose) ubClose.addEventListener('click', () => { $('#updateBanner').hidden = true; });

  bindLogin();
  bindWindow();
  bindNav();
  bindDropzone();
  bindCloud();
  bindFiscal();
  bindHistorico();
  bindLoteBalancetes();
  bindConciliacao();
  bindNotasFaltantes();
  bindChatIA();
  bindNewsToast();
  bindEfdContrib();
  $('#btnImport').addEventListener('click', doImport);
  $('#btnImport2').addEventListener('click', doImport);
  $('#btnExport').addEventListener('click', doExport);
  const dl = $('#diagLink');
  if (dl) dl.addEventListener('click', async () => {
    try {
      const d = await window.fiscocont.diag();
      alert('Diagnóstico FiscoCont+\n\n' +
        'Empacotado (.exe instalado): ' + d.packaged + '\n' +
        'Núcleo: ' + d.cmd + '\n' +
        (d.script ? 'Script: ' + d.script + '\n' : '') +
        'Núcleo encontrado: ' + d.coreExists + '\n' +
        'Dados do app: ' + d.userData);
    } catch (e) { alert('Diagnóstico indisponível: ' + e.message); }
  });
  try { $('#verTag').textContent = 'v' + (await window.fiscocont.version()); } catch (_) {}
  switchView('overview'); // mostra estado vazio
  startupCheck();
});
